"""engine_v2 core 层 Conflict Resolution（P2 设计规范 §5；P2-T05 实现载体）。

**职责**（P2 设计规范 §1.2 / §5；任务包 P2-T05 目标 1–3）：

- **冲突定义与锁提取**（D-P2-11 前段）：:class:`ConflictKey` 细粒度排他锁
  （``entity:<id>[:comp:<ct>[:field:<fp>]]`` / ``domain:<domain>`` 两种
  kind）+ :func:`extract_effect_locks` 锁推导（§5.1 五行锁规则表：整实体 /
  整组件 / 字段 / 域锁 + ``core.create_entity`` / ``core.remove_entity``
  结构动词**升级锁级别**）+ :func:`conflict_key` 单代表键 +
  :func:`conflicts_with` 相交判定（None = 通配）；
- **冲突图与分组**（D-P2-11 中端）：:func:`detect_conflicts` 以 effects 为
  顶点、锁相交为边建冲突图，取**连通分量**（size ≥ 2 即
  :class:`ConflictGroup`）；BFS 按到达序遍历、组内按到达序、返回按组内
  最小到达序排序——确定性，O(n²) 锁比较（MVP 可接受，P1-T07 §D.6 同款
  性能注记）；**批内暂存依赖豁免**（P2-REMEDIATION B1）：先到达的
  ``core.create_entity`` 与后到达的对同一实体的 ``core.set_component``
  （初始化挂载）不建冲突边（顺序依赖而非互斥竞争）；
- **策略协议与默认四策**（D-P2-11 后端；§5.3/§5.4）：:class:`ConflictStrategy`
  协议（``resolve`` 返回 None = 弃权，必须纯函数）+ :class:`ResolutionContext`
  （到达序为唯一权威序）+ :class:`ConflictResolution`；固定顺序
  **Authority Priority → Timestamp → Producer Priority → Entity FIFO**
  （:data:`DEFAULT_STRATEGIES`，顺序即求值序）；:class:`DefaultConflictResolver`
  顺序求策略、首个非 None 拍板，全部弃权（理论不可达——FIFO 永不弃权）→
  保守裁决 REJECT 全组；默认策略链**只产出 WINNER/REJECT**，MERGE/DEFER/
  REPAIR 为 domain resolver 扩展位（:data:`DomainResolverFactory` 注入点，
  §5.5，P2 不内置任何域解析器）；
- **任务包目标 3**：:class:`ConflictResolutionReport` 批级仲裁报告（逐组
  resolution + 批级 accepted/dropped，均到达序）与
  :meth:`DefaultConflictResolver.resolve_all` / :func:`resolve_conflicts`
  便捷入口；
- **Trace 协同**（P2 设计规范 §9）：:meth:`ConflictResolution.to_trace_payload`
  恰为 P1 冻结约定键（``trace.py`` :data:`DECISION_PAYLOAD_KEYS`）三个键
  ``effect_id`` / ``decision`` / ``reason``——``decision`` ∈ {winner, merge,
  defer, reject, repair} 直接落值、无映射层；``reason`` = 策略名 + detail。
  TraceRecord 本体装配（record_id / kind / revision-tick 坐标）归管道层
  （T07 cascade）。

``TIMESTAMP_METADATA_KEY: Final = "producer_timestamp_ms"``（D-P2-16）——
墙钟仅诊断（P1 §0.2 铁律 3），timestamp 策略仅作启发式平局破解，权威序
始终是 revision + 到达序。

依赖面（§1.3 依赖图注记）：P1 冻结契约（effects/ids/components/trace）+
``authority.py`` 的求值结果数据形状（``AuthorityEvaluationResult`` 承载
策略 1 的 ``rule_priority`` 输入，§3.5；``ProducerRegistry`` 承载策略 3 的
``priority_of`` 输入，§3.4）+ ``reducer.py`` 的 ``core.create_entity`` /
``core.remove_entity`` 常量（单一来源，严禁本模块复写字面量——D-P2-04
词表由 reducer 唯一定义）。依赖单向、无环。

Import 边界（P1 设计 §0.3 继承）：只允许 stdlib + pydantic + 同包
``src.engine_v2``，不触碰 v1。
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Final, Protocol

from src.engine_v2.core.authority import AuthorityEvaluationResult, ProducerRegistry
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.effects import (
    EffectTypeId,
    EntityTarget,
    ProposedEffect,
    StateDomainId,
    StateDomainTarget,
)
from src.engine_v2.core.ids import EffectId, EntityId
from src.engine_v2.core.reducer import (
    EFFECT_CREATE_ENTITY,
    EFFECT_REMOVE_ENTITY,
    EFFECT_SET_COMPONENT,
)

__all__ = [
    "AuthorityPriorityStrategy",
    "ConflictAction",
    "ConflictError",
    "ConflictGroup",
    "ConflictKey",
    "ConflictResolution",
    "ConflictResolutionReport",
    "ConflictStrategy",
    "DEFAULT_STRATEGIES",
    "DefaultConflictResolver",
    "DomainResolverFactory",
    "EntityFifoStrategy",
    "ProducerPriorityStrategy",
    "ResolutionContext",
    "TIMESTAMP_METADATA_KEY",
    "TimestampStrategy",
    "conflict_key",
    "conflicts_with",
    "detect_conflicts",
    "effect_locks",
    "extract_effect_locks",
    "resolve_conflicts",
]

#: 冲突图顶点锁种类的冻结词表（§5.1 ``ConflictKey.kind``）。
_CONFLICT_KEY_KINDS: Final[frozenset[str]] = frozenset({"entity", "domain"})

#: 结构动词升级锁级别（§5.1 锁规则表末行）：创建/删除与同实体**任何**变更
#: 冲突，恒取整实体锁。常量单一来源为 ``reducer.py``（D-P2-04），此处仅
#: 引用、不复写字面量。
_STRUCTURAL_ENTITY_VERBS: Final[frozenset[EffectTypeId]] = frozenset(
    {EFFECT_CREATE_ENTITY, EFFECT_REMOVE_ENTITY}
)

#: 全策略弃权（理论不可达——EntityFifoStrategy 永不弃权）时保守 REJECT 的
#: 拍板策略名（trace ``CONFLICT_RESOLUTION`` 的 reason 前缀，§9）。
_FALLBACK_STRATEGY_NAME: Final[str] = "fallback"

#: timestamp 策略约定键（D-P2-16）：producer 侧自报的产生时刻（毫秒，int）。
#: **仅当组内全体成员均携带（且为 int）时**生效（最大者胜，
#: last-writer-wins），否则策略弃权——权威序仍以 revision/到达序为准
#: （P1 §0.2 铁律 3：墙钟仅诊断）。
TIMESTAMP_METADATA_KEY: Final[str] = "producer_timestamp_ms"


class ConflictError(ValueError):
    """Conflict 模块异常基类（任务包 P2-T05；``ValueError`` 族）。

    派生 ``ValueError``：与词法/数据校验错误族统一（``AuthorityError`` /
    ``ReducerError`` 同款纪律），调用方可按 ``ValueError`` 一类捕获。

    角色：**输入契约守卫**——正常仲裁路径**不抛异常**（裁决是返回值，
    可解释性字段自足）；异常仅用于输入违反确定性契约（非契约类型、
    冲突组 <2 effects、批内重复 ``effect_id``、``ctx.arrival`` 未全覆盖
    等——"不可判定 ≠ 默认放行"哲学，K3/K4 同源）。
    """


# —— 冲突键与锁推导（§5.1；D-P2-11 前段）——


@dataclass(frozen=True)
class ConflictKey:
    """细粒度排他锁（P2 设计规范 §5.1；可哈希、参与集合运算）。

    两种 kind（:data:`_CONFLICT_KEY_KINDS`）：

    - ``"entity"``：entity 定位键——``entity_id`` 必填；``component_type``
      为 None = **整实体级锁**；``field_path`` 为 None = **整组件级锁**
      （字段锁必携带 component_type，``__post_init__`` 强制）。同一
      entity 下，粗粒度锁与任何细粒度锁相交（None = 通配，见
      :func:`conflicts_with`）；
    - ``"domain"``：状态域锁（``domain`` 必填，entity 定位键必须为
      None）——域级粗粒度、保守（域内键级细化需要 payload 语义推断，
      kernel 不做，§5.1 锁规则表）。

    frozen + 字段全等：同一锁位置的多个键实例互等且同哈希（集合/字典
    语义正确性）。:meth:`render` 提供规范化字符串形态（trace 可解释性，
    如 ``entity:ent_1:comp:health`` / ``domain:world_variables``）。
    """

    kind: str  # "entity" | "domain"
    entity_id: EntityId | None = None
    component_type: ComponentTypeId | None = None  # None = 整实体级锁
    field_path: str | None = None  # None = 整组件级锁
    domain: StateDomainId | None = None

    def __post_init__(self) -> None:
        if self.kind not in _CONFLICT_KEY_KINDS:
            raise ConflictError(
                f"ConflictKey.kind 必须是 {'/'.join(sorted(_CONFLICT_KEY_KINDS))} 之一，得到 {self.kind!r}"
            )
        if self.kind == "entity":
            if self.entity_id is None:
                raise ConflictError("entity 类 ConflictKey 必须携带 entity_id")
            if self.domain is not None:
                raise ConflictError("entity 类 ConflictKey 不得携带 domain")
            if self.field_path is not None and self.component_type is None:
                raise ConflictError("字段锁必须携带 component_type（field_path 不可悬空）")
        else:
            if self.domain is None:
                raise ConflictError("domain 类 ConflictKey 必须携带 domain")
            if self.entity_id is not None or self.component_type is not None or self.field_path is not None:
                raise ConflictError("domain 类 ConflictKey 不得携带 entity 定位键")

    def render(self) -> str:
        """规范化字符串形态（trace/日志/组键可解释性）。

        - 整实体锁：``entity:<entity_id>``
        - 整组件锁：``entity:<entity_id>:comp:<component_type>``
        - 字段锁：``entity:<entity_id>:comp:<component_type>:field:<field_path>``
        - 域锁：``domain:<domain>``
        """
        if self.kind == "entity":
            text = f"entity:{self.entity_id}"
            if self.component_type is not None:
                text += f":comp:{self.component_type}"
                if self.field_path is not None:
                    text += f":field:{self.field_path}"
            return text
        return f"domain:{self.domain}"


def conflict_key(effect: ProposedEffect) -> ConflictKey:
    """推导单个 effect 的代表锁键（P2 设计规范 §5.1）。

    锁规则（§5.1 表；当前规则下 :func:`extract_effect_locks` 恰返回单元素
    集合，本函数即其唯一成员）：

    - ``EntityTarget``（无 component_type）→ 整实体锁；
    - ``EntityTarget``（有 component_type，无 field_path）→ 整组件锁；
    - ``EntityTarget``（有 field_path）→ 字段锁；
    - ``StateDomainTarget`` → 域锁（域级粗粒度，保守）；
    - ``core.create_entity`` / ``core.remove_entity`` → **整实体锁**
      （结构动词升级锁级别：创建/删除与同实体任何变更冲突，target 上
      附带的 component_type/field_path 被升级抹平）。

    Args:
        effect: 待推导锁的拟议效果。

    Returns:
        该 effect 的 :class:`ConflictKey`。

    Raises:
        ConflictError: ``effect`` 不是 ``ProposedEffect``（输入契约守卫）。
    """
    if not isinstance(effect, ProposedEffect):
        raise ConflictError(f"conflict_key 需要 ProposedEffect，得到 {type(effect).__name__}")
    target = effect.target
    if isinstance(target, EntityTarget):
        if effect.effect_type in _STRUCTURAL_ENTITY_VERBS:
            return ConflictKey(kind="entity", entity_id=target.entity_id)
        return ConflictKey(
            kind="entity",
            entity_id=target.entity_id,
            component_type=target.component_type,
            field_path=target.field_path,
        )
    if not isinstance(target, StateDomainTarget):
        raise ConflictError(
            f"conflict_key 不支持的目标种类 {type(target).__name__}"
            "（EffectTarget tagged union 应仅含 entity/state_domain 两支）"
        )
    return ConflictKey(kind="domain", domain=target.domain)


def extract_effect_locks(effect: ProposedEffect) -> frozenset[ConflictKey]:
    """提取单个 effect 的细粒度排他锁集合（任务包 P2-T05 目标 1；§5.1）。

    当前锁规则下每个 effect 恰持**一把**锁（:func:`conflict_key` 的代表
    键）；以 ``frozenset`` 返回是为锁相交集合运算（:func:`detect_conflicts`
    的边判定）与未来更细粒度锁（P5+ 域细化，不改签名）预留——
    "效果与锁"之间保留集合关系。

    例：``core.set_component(ent_1, health, field=hp)`` →
    ``{entity:ent_1:comp:health:field:hp}``；
    ``core.set_world_variable(world_variables)`` → ``{domain:world_variables}``。

    Args:
        effect: 待提取锁的拟议效果。

    Returns:
        该 effect 的锁集合（当前恒为单元素 frozenset）。

    Raises:
        ConflictError: ``effect`` 不是 ``ProposedEffect``（输入契约守卫）。
    """
    return frozenset({conflict_key(effect)})


# 设计文档 §5.1 代码块的命名（任务包口径为 ``extract_effect_locks``）；
# 二者同一函数对象（re-export 同一性断言对两名字同时成立，closeout 机械化
# 覆盖）。
effect_locks = extract_effect_locks


def conflicts_with(a: ConflictKey, b: ConflictKey) -> bool:
    """两把锁是否相交（P2 设计规范 §5.1 相交判定；冲突图的边谓词）。

    同 kind 且——

    - entity 类：``entity_id`` 相等，``component_type`` 相等**或任一为
      None**，且 ``field_path`` 相等**或任一为 None**（None = 通配：整实体
      锁与同实体任何组件/字段锁相交，整组件锁与同组件任何字段锁相交；
      同组件不同字段不相交）；
    - domain 类：``domain`` 相等（域锁之间只有全域相交，无更细粒度）。

    不同 kind（entity vs domain）永不相交——实体相关变更永远经
    ``EntityTarget``，状态域变更永远经 ``StateDomainTarget``（§3.6 末行，
    不存在交叉写路径）。

    纯函数；对称、非自反于不同锁位置（同锁位置两实例相交，自反由相等
    蕴含）。
    """
    if a.kind != b.kind:
        return False
    if a.kind == "entity":
        if a.entity_id != b.entity_id:
            return False
        if a.component_type != b.component_type and None not in (a.component_type, b.component_type):
            return False
        if a.field_path != b.field_path and None not in (a.field_path, b.field_path):
            return False
        return True
    return a.domain == b.domain


# —— 冲突组与连通分量分组（§5.2；D-P2-11 中端）——


def _is_staged_init_dependency(earlier: ProposedEffect, later: ProposedEffect) -> bool:
    """同批次暂存依赖判定（P2-REMEDIATION B1 修复）。

    同一批次内**先到达**的 ``core.create_entity`` 与**后到达**的对同一
    实体的 ``core.set_component``（初始化挂载组件）是合法的暂存依赖，
    不是互斥冲突——reducer 暂存（``_WorkingWorld``）按 sequence 顺序
    应用：先创建实体，随后组件挂载方可成立。仅 ``create → set_component``
    这一方向/组合豁免：倒序到达、双创建、``remove_entity`` / 其余动词
    与同实体变更的组合仍按锁相交正常成组（保守裁决不放宽其余语义）。

    纯函数；不读状态（冲突检测层对基线状态无感知——创建目标已存在的
    病态批次由 validation/reducer 前置条件原子拒绝，冲突层无需重复判定）。
    """
    if earlier.effect_type != EFFECT_CREATE_ENTITY:
        return False
    if later.effect_type != EFFECT_SET_COMPONENT:
        return False
    earlier_target = earlier.target
    later_target = later.target
    return (
        isinstance(earlier_target, EntityTarget)
        and isinstance(later_target, EntityTarget)
        and earlier_target.entity_id == later_target.entity_id
    )


@dataclass(frozen=True)
class ConflictGroup:
    """冲突组（P2 设计规范 §5.2；连通分量的交付形态）。

    - ``effects``：组成员（**≥2**，按到达序）——冲突图中同一连通分量的
      全部顶点；
    - ``keys``：组内成员锁集合出现过的全部冲突键（去重；成员到达序 +
      成员内 :meth:`ConflictKey.render` 序——确定性）。含未与他者相交的
      键：可解释性优先（trace 侧可看到每个成员锁了什么），"相交键"是
      本元组的子集、可由 :func:`conflicts_with` 重算。
    """

    effects: tuple[ProposedEffect, ...]
    keys: tuple[ConflictKey, ...]


def _ordered_group_keys(lock_sets: Sequence[frozenset[ConflictKey]]) -> tuple[ConflictKey, ...]:
    """组成员锁键去重并序（成员到达序 + 成员内 render 序；确定性）。"""
    seen: set[ConflictKey] = set()
    ordered: list[ConflictKey] = []
    for lock_set in lock_sets:
        for key in sorted(lock_set, key=lambda candidate: candidate.render()):
            if key not in seen:
                seen.add(key)
                ordered.append(key)
    return tuple(ordered)


def detect_conflicts(effects: Sequence[ProposedEffect]) -> list[ConflictGroup]:
    """冲突检测：锁重叠建图 + 连通分量分组（P2 设计规范 §5.2；任务包目标 1）。

    算法：以 effects（按输入到达序编号 0..n-1）为顶点、
    :func:`conflicts_with`（任意锁对相交）为边建冲突图，取**连通分量**——
    size ≥ 2 的分量即 :class:`ConflictGroup`。连通分量口径保证"A 与 B
    冲突、B 与 C 冲突"时 A/B/C 同组**一次性解析**（传递闭包，避免逐对
    解析的顺序敏感歧义）。

    确定性：BFS 从到达序最小顶点出发、邻接扫描按顶点编号升序——组内
    effects 按到达序、返回 list 按组内最小到达序升序。复杂度 O(n²) 锁
    比较——MVP 可接受（P1-T07 §D.6 同款性能注记；P3+ 若有性能诉求可换
    索引，不改签名）。

    **批内暂存依赖豁免**（P2-REMEDIATION B1）：先到达的
    ``core.create_entity`` 与后到达的对同一实体的 ``core.set_component``
    （初始化挂载）之间**不建冲突边**（:func:`_is_staged_init_dependency`）
    ——锁相交虽成立（整实体锁 × 组件锁），语义上却是顺序依赖而非互斥
    竞争；二者均存活、按到达序经 reducer 暂存顺序应用。

    Args:
        effects: round 内的拟议效果批次（输入序 = 到达序；
            ``effect_id`` 批内唯一由 validation L1 ``duplicated_effect_id``
            上游保证，本函数按位置处理、不做 ID 去重）。

    Returns:
        冲突组列表（无冲突 → 空列表；单元素"组"不存在——直通语义在管道
        层，P2 设计规范 §7.3 步骤 4）。

    Raises:
        ConflictError: 任一元素不是 ``ProposedEffect``（输入契约守卫）。
    """
    lock_sets: list[frozenset[ConflictKey]] = []
    for effect in effects:
        lock_sets.append(extract_effect_locks(effect))
    count = len(lock_sets)

    def _linked(i: int, j: int) -> bool:
        lo, hi = (i, j) if i < j else (j, i)
        if _is_staged_init_dependency(effects[lo], effects[hi]):
            # 批内暂存依赖（先 create 后 set_component 初始化挂载）：
            # 锁相交成立但语义为顺序依赖，不建冲突边（P2-REMEDIATION B1）
            return False
        for key in lock_sets[i]:
            for other in lock_sets[j]:
                if conflicts_with(key, other):
                    return True
        return False

    visited: set[int] = set()
    groups: list[ConflictGroup] = []
    for start in range(count):
        if start in visited:
            continue
        component: list[int] = [start]
        visited.add(start)
        index = 0
        while index < len(component):
            current = component[index]
            index += 1
            for neighbor in range(count):
                if neighbor not in visited and _linked(current, neighbor):
                    visited.add(neighbor)
                    component.append(neighbor)
        if len(component) < 2:
            continue  # 单顶点分量 = 无冲突，直通
        order = sorted(component)  # 到达序
        groups.append(
            ConflictGroup(
                effects=tuple(effects[i] for i in order),
                keys=_ordered_group_keys([lock_sets[i] for i in order]),
            )
        )
    return groups


# —— 策略协议与解析上下文（§5.3）——


class ConflictAction(str, Enum):
    """冲突裁决动作词表（P2 设计规范 §5.3；Spec §19 五种裁决）。

    枚举一律 ``class Xxx(str, Enum)``（P1 设计 §0.1），JSON 值为字符串
    字面量。默认策略链只产出 ``WINNER`` / ``REJECT``（D-P2-11）；
    ``MERGE`` / ``DEFER`` / ``REPAIR`` 为 domain resolver 扩展位
    （§5.5，P5+ 模块提供）——``ConflictResolution`` 数据结构对五值全
    兼容（trace decision 词表即本枚举值集，P2 设计规范 §9）。
    """

    WINNER = "winner"
    MERGE = "merge"
    DEFER = "defer"
    REJECT = "reject"
    REPAIR = "repair"


@dataclass(frozen=True)
class ResolutionContext:
    """冲突仲裁上下文（P2 设计规范 §5.3）。

    - ``arrival``：round 内到达序（**唯一权威序**）——``effect_id → 到达
      下标``（小 = 早）。管道层（cascade ``run_round``）以 round 输入序
      构造；:meth:`from_batch` 为同源确定性构造器（下标 0..n-1）。
      EntityFifoStrategy 的输入；
    - ``authority_decisions``：逐 effect 的 authority 求值结果
      （:func:`check_authority` 返回的 :class:`AuthorityEvaluationResult`
      ——P2 设计规范 §5.3 占位注解 ``AuthorityDecision`` 的数据形状
      载体：策略 1 的 ``rule_priority`` 输入由求值结果承载，§3.5
      "rule_priority：拍板规则的 priority（冲突解析策略 1 的输入）"）。
      None → 策略 1 弃权；裸 :class:`~src.engine_v2.core.authority.
      AuthorityDecision` 值亦被容错处理（无 ``rule_priority`` 属性 →
      视为无可排序优先级，策略弃权）；
    - ``producer_registry``：producer 注册表（策略 3 的
      ``priority_of`` 输入，§3.4）。None → 策略 3 弃权。
    """

    arrival: Mapping[EffectId, int]
    authority_decisions: Mapping[EffectId, AuthorityEvaluationResult] | None = None
    producer_registry: ProducerRegistry | None = None

    @classmethod
    def from_batch(
        cls,
        effects: Sequence[ProposedEffect],
        authority_decisions: Mapping[EffectId, AuthorityEvaluationResult] | None = None,
        producer_registry: ProducerRegistry | None = None,
    ) -> ResolutionContext:
        """从提案批构造上下文：arrival = 批内到达序（0..n-1）。

        批内重复 ``effect_id`` 时后到者覆盖先到者的下标——调用方应经
        validation L1（``duplicated_effect_id`` 过滤）后再构造；
        :meth:`DefaultConflictResolver.resolve_all` 入口对重复 ID 显式
        抛 :class:`ConflictError`（双重防御，KBC-2）。
        """
        return cls(
            arrival={effect.effect_id: index for index, effect in enumerate(effects)},
            authority_decisions=authority_decisions,
            producer_registry=producer_registry,
        )


class ConflictStrategy(Protocol):
    """冲突解析策略协议（P2 设计规范 §5.3；结构化子类型）。

    实现须为**纯函数**：同一 ``(group, ctx)`` 恒返回同一结果（或 None），
    无副作用、不依赖墙钟/随机数（确定性管道纪律）。``name`` 为策略名
    （trace 可解释性，拍板结果落 ``ConflictResolution.strategy``）。
    """

    name: str

    def resolve(self, group: ConflictGroup, ctx: ResolutionContext) -> ConflictResolution | None:
        """解析一个冲突组。

        Returns:
            非 None = 本策略拍板；None = 弃权，交给下一策略。
        """
        ...


# —— 仲裁结果与批级报告（§5.3/§5.5 + 任务包目标 2/3）——


@dataclass(frozen=True)
class ConflictResolution:
    """单个冲突组的仲裁结果（P2 设计规范 §5.3）。

    - ``action``：裁决动作（:class:`ConflictAction`；默认链只产出
      WINNER / REJECT，D-P2-11）；
    - ``strategy``：拍板策略名（trace 可解释性，§9 "reason = 策略名 +
      detail"）；
    - ``accepted``：被接受的 effect id——WINNER → **唯一**胜出者；
      REJECT → 空；MERGE/DEFER/REPAIR（扩展位）语义由域解析器约定；
    - ``dropped``：被丢弃的 effect id（WINNER → 全部落选者，进 trace
      ``conflict_resolution`` 记录；REJECT → 全组）；
    - ``reason``：裁决细节（与 ``strategy`` 拼接后落 trace ``reason``）。
    """

    action: ConflictAction
    strategy: str
    accepted: tuple[EffectId, ...]
    dropped: tuple[EffectId, ...]
    reason: str

    def to_trace_payload(self) -> dict[str, str]:
        """转换为 ``conflict_resolution`` trace payload 格式（P2 设计规范 §9）。

        符合 P1 冻结子约定（``trace.py`` :data:`DECISION_PAYLOAD_KEYS`）：
        恰为三个约定键 ``effect_id`` / ``decision`` / ``reason``——

        - ``effect_id``：WINNER → 唯一胜出者 id；REJECT（全组丢弃）→
          组成员（dropped）id 分号串接（§9 "胜者（或组成员串）"）；
        - ``decision``：:class:`ConflictAction` 词表直接落值（winner /
          merge / defer / reject / repair，无映射层）；
        - ``reason``：策略名 + detail（``<strategy>:<reason>``）。

        TraceRecord 本体装配（record_id / kind / revision-tick 坐标填充）
        归管道层（T07 cascade）——本方法只产出 payload 形态且保持确定性
        （不生成 ID）。
        """
        primary = self.accepted if self.accepted else self.dropped
        return {
            "effect_id": ";".join(str(effect_id) for effect_id in primary),
            "decision": self.action.value,
            "reason": f"{self.strategy}:{self.reason}",
        }


@dataclass(frozen=True)
class ConflictResolutionReport:
    """批级冲突仲裁报告（任务包 P2-T05 目标 3）。

    一次 ``resolve_all`` 的批级汇总——管道层（cascade ``run_round`` 步骤
    4）以 ``resolutions`` 逐组产 trace（``CONFLICT_RESOLUTION``），以
    ``accepted`` 装配事务（到达序，含非冲突直通 effects）：

    - ``resolutions``：逐冲突组的仲裁结果（组序 = 各组分量的最小到达序
      升序，与 :func:`detect_conflicts` 返回序一致）；无冲突组 → 空元组；
    - ``accepted``：批级存活的 effect id——**非冲突直通 + 各组
      ``accepted``**，到达序（事务装配直接输入）；
    - ``dropped``：批级被丢弃的 effect id——各组 ``dropped`` 之并，到达
      序（trace 可解释性）。
    """

    resolutions: tuple[ConflictResolution, ...]
    accepted: tuple[EffectId, ...]
    dropped: tuple[EffectId, ...]

    @property
    def has_conflicts(self) -> bool:
        """批内是否存在冲突组（resolutions 非空）。"""
        return bool(self.resolutions)

    def resolution_for(self, effect_id: EffectId) -> ConflictResolution | None:
        """该 effect 所属冲突组的仲裁结果；None = 直通（未卷入任何冲突组）。"""
        for resolution in self.resolutions:
            if effect_id in resolution.accepted or effect_id in resolution.dropped:
                return resolution
        return None


# —— 默认四策（§5.4；固定顺序，Spec §19 "Resolver MAY use" 的确定性具体化）——


def _dropped_except(group: ConflictGroup, winner: EffectId) -> tuple[EffectId, ...]:
    """组内全部落选者（到达序；winner 除外）。"""
    return tuple(effect.effect_id for effect in group.effects if effect.effect_id != winner)


class AuthorityPriorityStrategy:
    """策略 1：authority 规则优先级（P2 设计规范 §5.4 序 1）。

    输入：``ctx.authority_decisions``（逐 effect 求值结果）。判定：组内
    ``rule_priority`` **最大且唯一**者胜（authority 规则越具体/越高优先级，
    裁决权越强）。无求值结果、或求值结果无拍板规则（``rule_priority is
    None``——如 closed-by-default 回落 ALLOW，D-P2-09）的 effect 无可排序
    优先级，不参与排序（但仍可能落选进 dropped）。

    弃权条件：组内无可排序决策（``ctx.authority_decisions`` 为 None /
    全缺失 / 全 ``rule_priority is None``），或并列最大值 ≥2。

    纯函数（无状态，``name`` 为类属性）。
    """

    name: str = "authority_priority"

    def resolve(self, group: ConflictGroup, ctx: ResolutionContext) -> ConflictResolution | None:
        decisions = ctx.authority_decisions
        if decisions is None:
            return None
        ranked: dict[EffectId, int] = {}
        for effect in group.effects:
            decision = decisions.get(effect.effect_id)
            if decision is None:
                continue
            # 容错裸 AuthorityDecision 值（§5.3 占位注解口径）：无
            # rule_priority 属性 → 视为无可排序优先级。
            priority = getattr(decision, "rule_priority", None)
            if isinstance(priority, int):
                ranked[effect.effect_id] = priority
        if not ranked:
            return None
        top = max(ranked.values())
        winners = [
            effect.effect_id for effect in group.effects if ranked.get(effect.effect_id) == top
        ]
        if len(winners) > 1:
            return None
        winner = winners[0]
        return ConflictResolution(
            action=ConflictAction.WINNER,
            strategy=self.name,
            accepted=(winner,),
            dropped=_dropped_except(group, winner),
            reason=f"rule_priority={top} 最大且唯一（winner={winner}）",
        )


class TimestampStrategy:
    """策略 2：producer 时间戳（P2 设计规范 §5.4 序 2；D-P2-16）。

    输入：``effect.metadata[TIMESTAMP_METADATA_KEY]``（``"producer_
    timestamp_ms"``，int）。判定：**全体成员均携带（且值为 int）时**，
    最大者胜（last-writer-wins）。

    弃权条件：任一成员缺失键（含值为非 int——bool 显式排除，JSON 口径
    下 bool 是 int 子类但无时刻语义）或并列最大值。

    定位（P1 §0.2 铁律 3）：墙钟仅诊断——本策略只是启发式平局破解，
    权威序始终是 revision + 到达序。

    纯函数（无状态，``name`` 为类属性）。
    """

    name: str = "timestamp"

    def resolve(self, group: ConflictGroup, ctx: ResolutionContext) -> ConflictResolution | None:
        timestamps: dict[EffectId, int] = {}
        for effect in group.effects:
            value = effect.metadata.get(TIMESTAMP_METADATA_KEY)
            if isinstance(value, bool) or not isinstance(value, int):
                return None  # 任一成员缺失键（或非 int）→ 弃权（D-P2-16）
            timestamps[effect.effect_id] = value
        top = max(timestamps.values())
        winners = [effect.effect_id for effect in group.effects if timestamps[effect.effect_id] == top]
        if len(winners) > 1:
            return None
        winner = winners[0]
        return ConflictResolution(
            action=ConflictAction.WINNER,
            strategy=self.name,
            accepted=(winner,),
            dropped=_dropped_except(group, winner),
            reason=f"producer_timestamp_ms={top} 最大且唯一（last-writer-wins；winner={winner}）",
        )


class ProducerPriorityStrategy:
    """策略 3：producer 优先级（P2 设计规范 §5.4 序 3）。

    输入：``ctx.producer_registry.priority_of(effect.source)``（未注册
    producer 由 ``priority_of`` 缺省纪律归 0，§3.4）；并列时比
    ``effect.priority_hint``（None 视为 0）。判定：
    ``(producer_priority, hint)`` 字典序**最大且唯一**者胜。

    弃权条件：``ctx.producer_registry`` 为 None，或并列（含 hint 后仍
    并列）。

    纯函数（无状态，``name`` 为类属性）。
    """

    name: str = "producer_priority"

    def resolve(self, group: ConflictGroup, ctx: ResolutionContext) -> ConflictResolution | None:
        registry = ctx.producer_registry
        if registry is None:
            return None
        ranks: dict[EffectId, tuple[int, int]] = {}
        for effect in group.effects:
            producer_priority = registry.priority_of(effect.source)
            hint = effect.priority_hint if effect.priority_hint is not None else 0
            ranks[effect.effect_id] = (producer_priority, hint)
        top = max(ranks.values())
        winners = [effect.effect_id for effect in group.effects if ranks[effect.effect_id] == top]
        if len(winners) > 1:
            return None
        winner = winners[0]
        producer_priority, hint = top
        return ConflictResolution(
            action=ConflictAction.WINNER,
            strategy=self.name,
            accepted=(winner,),
            dropped=_dropped_except(group, winner),
            reason=(
                f"producer_priority={producer_priority}（hint={hint}）"
                f"最大且唯一（winner={winner}）"
            ),
        )


class EntityFifoStrategy:
    """策略 4：到达序 FIFO（P2 设计规范 §5.4 序 4；确定性兜底）。

    输入：``ctx.arrival``。判定：到达序**最小**者胜（先来先赢）。
    **永不弃权**——默认策略链的全部弃权情形最终都落到本策略。

    防御：``ctx.arrival`` 缺失的 effect 记 ``+inf``（永不胜出）——正常
    管道不会触发（:meth:`DefaultConflictResolver.resolve_all` 入口强制
    全覆盖）。到达序并列（调用方传入非唯一序）时以组内位置破平（到达
    序 = 组内序，结果不变）。

    纯函数（无状态，``name`` 为类属性）。
    """

    name: str = "entity_fifo"

    def resolve(self, group: ConflictGroup, ctx: ResolutionContext) -> ConflictResolution | None:
        position, winner = min(
            enumerate(group.effects),
            key=lambda pair: (ctx.arrival.get(pair[1].effect_id, math.inf), pair[0]),
        )
        order = ctx.arrival.get(winner.effect_id, math.inf)
        return ConflictResolution(
            action=ConflictAction.WINNER,
            strategy=self.name,
            accepted=(winner.effect_id,),
            dropped=_dropped_except(group, winner.effect_id),
            reason=f"arrival={order} 最早（先至先赢；winner={winner.effect_id}，组内位置={position}）",
        )


#: 默认策略链（§5.4 固定顺序；顺序即求值序——:class:`DefaultConflictResolver`
#: 的缺省参数）。Authority Priority → Timestamp → Producer Priority →
#: Entity FIFO。
DEFAULT_STRATEGIES: Final[tuple[ConflictStrategy, ...]] = (
    AuthorityPriorityStrategy(),
    TimestampStrategy(),
    ProducerPriorityStrategy(),
    EntityFifoStrategy(),
)


# —— 默认解析器与批级入口（§5.3/§5.5）——


class DefaultConflictResolver:
    """ConflictResolver 策略链（P2 设计规范 §5.3/§5.4；任务包目标 2）。

    顺序求 ``strategies``（缺省 :data:`DEFAULT_STRATEGIES` 固定四策），
    **首个非 None** 结果拍板本组；全部弃权（理论不可达——
    :class:`EntityFifoStrategy` 永不弃权）→ 保守裁决 **REJECT 全组**
    （``strategy="fallback"``，reason 注明全策略弃权）。

    默认策略链**只产出 WINNER/REJECT**（D-P2-11）：MERGE/REPAIR 需要域
    语义、DEFER 需要调度语义，均属 domain-specific resolver（Spec §19
    末条）——经自定义 ``strategies``（或管道层的
    :data:`DomainResolverFactory` 注入点）挂入的域解析器可产出五值全
    域，本解析器对策略返回值**透传不裁剪**（扩展位机制正确性）。
    """

    def __init__(self, strategies: Sequence[ConflictStrategy] = DEFAULT_STRATEGIES) -> None:
        """以固定策略元组构造解析器（求值序 = 元组序）。"""
        self._strategies = tuple(strategies)

    @property
    def strategies(self) -> tuple[ConflictStrategy, ...]:
        """本解析器的策略链（求值序 = 元组序；只读视图）。"""
        return self._strategies

    def resolve_group(self, group: ConflictGroup, ctx: ResolutionContext) -> ConflictResolution:
        """解析单个冲突组（策略链序贯；首个非 None 拍板）。

        Args:
            group: 冲突组（≥2 effects）。
            ctx: 解析上下文。

        Returns:
            本组的 :class:`ConflictResolution`（WINNER/REJECT；全部弃权
            时保守 REJECT 全组）。

        Raises:
            ConflictError: ``group`` 不是 :class:`ConflictGroup` 或成员
                <2（单元素"组"直通语义在管道层，P2 设计规范 §7.3 步骤 4）。
        """
        if not isinstance(group, ConflictGroup):
            raise ConflictError(
                f"resolve_group 需要 ConflictGroup，得到 {type(group).__name__}"
            )
        if len(group.effects) < 2:
            raise ConflictError(
                f"冲突组必须含 ≥2 effects（得到 {len(group.effects)}；"
                "单元素'组'直通归管道层，P2 设计规范 §7.3）"
            )
        for strategy in self._strategies:
            resolution = strategy.resolve(group, ctx)
            if resolution is not None:
                return resolution
        all_ids = tuple(effect.effect_id for effect in group.effects)
        return ConflictResolution(
            action=ConflictAction.REJECT,
            strategy=_FALLBACK_STRATEGY_NAME,
            accepted=(),
            dropped=all_ids,
            reason="全部策略弃权（理论不可达——FIFO 永不弃权），保守 REJECT 全组",
        )

    def resolve_all(
        self,
        effects: Sequence[ProposedEffect],
        ctx: ResolutionContext,
    ) -> ConflictResolutionReport:
        """批级冲突解析：detect_conflicts + 逐组策略链 + 报告装配。

        管道层（cascade ``run_round`` 步骤 4）的单一入口：

        1. 输入守卫（确定性纪律，"不可判定 ≠ 默认放行"哲学）：
           批内 ``effect_id`` 唯一（KBC-2；validation L1 上游已过滤，
           双重防御）；``ctx.arrival`` 全覆盖批内 effects（到达序是
           唯一权威序）——违反 → :class:`ConflictError`；
        2. :func:`detect_conflicts` 连通分量分组；
        3. 逐组 :meth:`resolve_group`（组序 = 最小到达序升序）；
        4. 装配 :class:`ConflictResolutionReport`——未卷入任何冲突组的
           effect **直通**（不进任何 resolution，计入 ``accepted``）。

        Args:
            effects: round 内已授权且通过 L1 校验的拟议效果批次
                （输入序 = 到达序）。
            ctx: 解析上下文（``arrival`` 必须覆盖全部 effects）。

        Returns:
            批级仲裁报告（``accepted`` / ``dropped`` 均到达序）。

        Raises:
            ConflictError: 输入违反确定性契约（见上）。
        """
        effect_ids = [effect.effect_id for effect in effects]
        if len(set(effect_ids)) != len(effect_ids):
            raise ConflictError(
                "resolve_all 输入批含重复 effect_id（KBC-2；应由 validation L1 "
                "'duplicated_effect_id' 上游过滤）"
            )
        missing = [effect_id for effect_id in effect_ids if effect_id not in ctx.arrival]
        if missing:
            raise ConflictError(
                "ctx.arrival 未覆盖批内全部 effects（到达序是唯一权威序）："
                + ", ".join(str(effect_id) for effect_id in missing)
            )
        groups = detect_conflicts(effects)
        resolutions = tuple(self.resolve_group(group, ctx) for group in groups)
        dropped_ids = {
            effect_id for resolution in resolutions for effect_id in resolution.dropped
        }
        return ConflictResolutionReport(
            resolutions=resolutions,
            accepted=tuple(effect_id for effect_id in effect_ids if effect_id not in dropped_ids),
            dropped=tuple(effect_id for effect_id in effect_ids if effect_id in dropped_ids),
        )


def resolve_conflicts(
    effects: Sequence[ProposedEffect],
    ctx: ResolutionContext,
    resolver: DefaultConflictResolver | None = None,
) -> ConflictResolutionReport:
    """批级冲突解析便捷入口（:meth:`DefaultConflictResolver.resolve_all` 的
    模块级门面）。

    Args:
        effects: round 内已授权且通过 L1 校验的拟议效果批次（输入序 =
            到达序）。
        ctx: 解析上下文（``arrival`` 必须覆盖全部 effects）。
        resolver: 解析器实例；None → 缺省四策默认解析器（每次新建，
            无状态、无跨批影响）。

    Returns:
        批级仲裁报告（:class:`ConflictResolutionReport`）。

    Raises:
        ConflictError: 输入违反确定性契约（同 ``resolve_all``）。
    """
    if resolver is None:
        resolver = DefaultConflictResolver()
    return resolver.resolve_all(effects, ctx)


# —— 域解析器注入点类型（§5.5 扩展位）——


#: cascade.py 的依赖注入点类型（P2 设计规范 §5.5）：按 domain/
#: component_type 选择性挂域解析器——工厂收 ``(group, ctx)``，返回本组
#: 专用策略或 None（弃权，回落默认链）。**P5+ 模块提供实现；P2 不内置
#: 任何域解析器**（MERGE/DEFER/REPAIR 的语义落位归域层，Spec §19 末条）。
DomainResolverFactory = Callable[[ConflictGroup, ResolutionContext], ConflictStrategy | None]
