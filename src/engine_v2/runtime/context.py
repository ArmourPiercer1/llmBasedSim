"""Runtime Closure T4：ActorDecisionContext 构建 + 感知物化（contract §4 T4 行）。

冻结契约（``docs/plans/runtime_closure_contract.md``）：本文件为 T4 owned file，
公共面 = :func:`build_actor_context`（主入口）+ :func:`build_actor_context_for_wakeup`
（带 wake_reason / tick 参数的下层函数；主入口是其薄包装）。``WorldInstance``
唯一 import 面 = ``src.engine_v2.runtime.world_instance``（contract §1 字段冻结）。

**主路径 = 复用 P4 冻结实现，不重做设计**：
:class:`~src.engine_v2.core.context_provider.DefaultContextProvider`
.build(:class:`~src.engine_v2.core.context_provider.ContextBuildInput`)，输入逐字段
取自 ``WorldInstance``——

- ``state`` = ``guard(instance.world)``（core/reducer.py:1590；GuardedWorldState
  深冻结只读门面，构建期只读、绝不进入结果，D-P4-05）；
- ``registry`` = ``instance.action_registry``；
- ``capability_table`` = 本模块构造（见下，不扩 schema）；
- ``space_registry`` = ``instance.spaces``；
- ``tick`` = ``instance.runtime.logical_tick``（主入口；下层函数可显式覆盖）；
- ``wake_reason`` = ``None``（主入口；下层函数可显式覆盖）。

**capability_table（不扩 schema；标准构造面 = core/capability.py
``CapabilityTable(grants=..., action_requirements=...)`` + Capability 8 token
闭集词表）**：

- 每世界实体（entities 插入序，确定性）× 每默认 capability 恰 1 条 grant
  （``(actor_id, capability)`` 零重复，C-INV-1 合规）；
- 普通 NPC = **固定 runtime 默认** :data:`_NPC_DEFAULT_CAPABILITIES`（最小集：
  observation.read / knowledge.read / memory.read / world.read.local；
  **无 world.read.global**——全局读不授予，context 的 ``global_entity_views``
  恒 None，结果钉）；
- player（``ent_authoring_<ir.player.player_id>`` 内容侧确定性命名，ids.py:68
  约定 + presentation/view.py 同款前缀）= 同一默认集；若 IR
  ``player.capabilities`` 开放 dict（content/schemas.py:241，D-P5-05 豁免面）
  已有**数值声明**（键 ``sight_m`` / ``hearing_m``，int/float，bool 拒绝）则
  消费为该 actor 的感知半径；否则回落固定 runtime 常量
  :data:`_DEFAULT_SIGHT_RADIUS` / :data:`_DEFAULT_HEARING_RADIUS`。skill
  等级类声明不映射任何 core Capability token（8 token 闭集，不扩 schema），
  本轮不消费；
- world.read.local grant 的 scope = ``{"radius": ceil(sight)}``（D-P4-06
  int ≥ 1；负半径退化面经 ``max(1, ...)`` 钳制）——local 物化半径与感知
  视觉半径同参（单一"半径"口径，Gate 1/2 的半径即此值）；
- ``action_requirements`` = ``{}``（WorldInstance 无 action 能力要求面；空要求
  = 恒满足，capability.py:144 语义，candidate_actions = registry 全项 casefold
  排序）；
- 高级覆盖（per-actor / per-project capability 投影）后续走 custom context
  provider，本轮不做（契约 T4 卡明示）。

**感知物化（:func:`src.engine_v2.modules.perception.build_observations`，
P9 冻结纯函数）**：

- 逐 ``instance.spaces`` 已注册域（``domain_ids()`` 排序序，确定性）；域内
  位置 = 实体 spaces 组件 ``decode_spaces`` 投影（core/space.py:492；与
  tests P9Host.world_positions 参考语义同形——读权威状态 ``instance.world``
  只读访问，K2 零写）；
- ``world_positions`` = ``{实体规范 id: 该域位置}``（仅该域有 Mapping 位置
  的实体；无 mapping 域缺席不入表，参考语义）；``observers`` =
  ``{str(actor_id): PerceptionRange(sight, hearing)}``（单观察者映射 = 单
  批次，build_observations 签名面）；``entities`` = 同一实体集的最小映射
  ``{实体 id: {}}``（build_observations 值面不消费，perception.py:156-158）；
  ``source`` = ``ObservationSource(observer_id, domain=域, tick)``；
- 位置非 Mapping（graph 节点 id 面）→ 该域零贡献（本轮感知 = grid Mapping
  位置面；不崩溃，确定性）；actor 该域无位置 → 零记录（build_observations
  缺席面，perception.py:151）；
- 记录按域序主序追加（build_observations 内部 ``observer/entity/kind`` 全序
  原样保留）；自排除（entity == observer）/ 两感官分类 / 距离 = 曼哈顿 L1
  全部承继 P9 冻结语义，本模块零投影逻辑；
- 位置越界（非法 grid 坐标）不做 backend 复检——build_observations 是纯
  距离函数面（数据层退化面，确定性零崩溃）。

**结果钉（ActorDecisionContext 13 字段）**：

- ``self_view`` = actor 自身 EntityView（P4 第 1 步，CX-INV-1 不产半截
  context）；
- ``observations`` = **build_observations 产物**（本 tick 感知批；结果钉
  口径，覆盖 P4 组件载荷解码面——P4 的三组件物化仅继续服务 knowledge /
  memory 两字段）；
- ``visible_entities`` = 感知结果并集口径（**DefaultContextProvider 语义**：
  self ∪ 感知记录 observed_entity_ids ∪ knowledge 参照（∩ 世界实存）∪ local
  键集；存储前经 CX-INV-2 同口径重算两侧断言，P4 同纪律）；
- ``local_entity_views`` = P4 local 物化（含 actor 自身，距离 0 ≤ 半径；
  只含 visible——键集并入并集）；
- ``global_entity_views`` = **None**（默认表不授予 world.read.global，
  P4 第 4 步未授权 → None 非 {}）；
- ``knowledge`` / ``memory`` / ``candidate_actions`` / ``granted_capabilities``
  = P4 六步物化原值透传（candidate = registry 中能力全满足项，casefold
  排序元组，CX-INV-7）。

**错误面**：actor 不存在于世界 → P4
:class:`~src.engine_v2.core.context_provider.ActorUnknownError` 原样传播
（LookupError 族，CX-INV-1 显式错误，不静默）。

纪律（contract §0）：零 WorldState 写（只读权威状态）；零 LLM / plugin；
零 schema 扩展；import 风格一律 ``from src.engine_v2...``；零 import tests；
标准库仅 ``math``（ceil 半径钳制，§3.4 黑名单外）。
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Final

from src.engine_v2.core.capability import Capability, CapabilityGrant, CapabilityTable
from src.engine_v2.core.context_provider import (
    ActorDecisionContext,
    ContextBuildInput,
    ContextInvariantError,
    DefaultContextProvider,
)
from src.engine_v2.core.entity import EntityView
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.knowledge import KnowledgeState, ObservationRecord
from src.engine_v2.core.reducer import guard
from src.engine_v2.core.space import SPACES_COMPONENT, decode_spaces
from src.engine_v2.modules.perception import (
    ObservationSource,
    PerceptionRange,
    build_observations,
)
from src.engine_v2.runtime.world_instance import WorldInstance

__all__ = [
    "build_actor_context",
    "build_actor_context_for_wakeup",
]

#: 内容侧确定性实体 id 命名前缀（ids.py:68 ``ent_authoring_<slug>`` 约定；
#: presentation/view.py:85 同款）。
_AUTHORING_ENTITY_PREFIX = "ent_authoring_"

#: 缺省感知视觉半径（grid 格 / 曼哈顿距离；固定 runtime 常量——PerceptionRange
#: 投影宿主职责面，本模块零投影逻辑的常量落位）。
_DEFAULT_SIGHT_RADIUS: Final[float] = 5.0

#: 缺省感知听觉半径（同口径）。
_DEFAULT_HEARING_RADIUS: Final[float] = 3.0

#: 普通 NPC（及 player 回落）固定 runtime 默认 capability 集——最小集：
#: observation / knowledge / memory 读 + world.read.local（本地感知）；
#: **无 world.read.global**（全局读不授予 → global_entity_views 恒 None）。
_NPC_DEFAULT_CAPABILITIES: Final[frozenset[Capability]] = frozenset(
    {
        Capability.OBSERVATION_READ,
        Capability.KNOWLEDGE_READ,
        Capability.MEMORY_READ,
        Capability.WORLD_READ_LOCAL,
    }
)


# —— 私有助手（capability 表 / 感知半径 / 域位置 / 感知物化）——


def _player_entity_id(instance: WorldInstance) -> EntityId:
    """player 的世界实体 id（内容侧确定性命名，ids.py:68 约定）。"""
    return EntityId(f"{_AUTHORING_ENTITY_PREFIX}{instance.ir.player.player_id}")


def _numeric_radius(value: object, default: float) -> float:
    """开放 dict 数值声明 → float 半径；缺席 / 非数值 / bool → 默认常量。

    bool 显式拒绝（house 纪律：bool 是 int 子类，必须显式排除）。
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _perception_range(instance: WorldInstance, actor_id: EntityId) -> PerceptionRange:
    """actor 感知半径：player 消费 IR 数值声明（sight_m / hearing_m），
    否则（及全部 NPC）= 固定 runtime 常量（assumption 记录面）。"""
    if actor_id == _player_entity_id(instance):
        caps = instance.ir.player.capabilities
        return PerceptionRange(
            sight_m=_numeric_radius(caps.get("sight_m"), _DEFAULT_SIGHT_RADIUS),
            hearing_m=_numeric_radius(caps.get("hearing_m"), _DEFAULT_HEARING_RADIUS),
        )
    return PerceptionRange(
        sight_m=_DEFAULT_SIGHT_RADIUS,
        hearing_m=_DEFAULT_HEARING_RADIUS,
    )


def _local_radius(range_: PerceptionRange) -> int:
    """world.read.local scope 半径 = ceil(sight)（D-P4-06 int ≥ 1；
    负半径退化面钳至 1——local 物化半径与感知视觉半径同参）。"""
    return max(1, math.ceil(range_.sight_m))


def _build_capability_table(instance: WorldInstance) -> CapabilityTable:
    """逐实体构造 grant 表（不扩 schema；C-INV-1 合规：每
    ``(actor_id, capability)`` 恰 1 条；grant 序 = 实体插入序 ×
    capability 值排序，确定性）。"""
    grants: list[CapabilityGrant] = []
    for eid in instance.world.entities:
        radius = _local_radius(_perception_range(instance, eid))
        for capability in sorted(_NPC_DEFAULT_CAPABILITIES, key=lambda c: c.value):
            scope = (
                {"radius": radius}
                if capability == Capability.WORLD_READ_LOCAL
                else None
            )
            grants.append(
                CapabilityGrant(actor_id=eid, capability=capability, scope=scope)
            )
    return CapabilityTable(grants=tuple(grants), action_requirements={})


def _domain_positions_map(
    instance: WorldInstance, domain_id: str
) -> dict[str, Mapping[str, int]]:
    """单域世界位置面（P9Host.world_positions 参考语义同形，只读）：
    实体规范 id → 该域位置；无该域 mapping / 位置非 Mapping 的实体缺席
    不入表。读权威状态（K2 零写）；S-INV-3 保证一域至多一 mapping。"""
    positions: dict[str, Mapping[str, int]] = {}
    for entity_id, record in instance.world.entities.items():
        payload = record.components.get(SPACES_COMPONENT)
        if payload is None:
            continue
        for mapping in decode_spaces(payload):
            if mapping.domain_id == domain_id and isinstance(mapping.position, Mapping):
                positions[str(entity_id)] = mapping.position
    return positions


def _materialize_observations(
    instance: WorldInstance, actor_id: EntityId, tick: int
) -> tuple[ObservationRecord, ...]:
    """感知物化：逐注册域 build_observations 批次，域序主序追加（确定性）；
    actor 该域无 Mapping 位置 → 该域零贡献（不崩溃）。"""
    range_ = _perception_range(instance, actor_id)
    actor_key = str(actor_id)
    records: list[ObservationRecord] = []
    for domain_id in instance.spaces.domain_ids():  # 排序元组（确定性）
        world_positions = _domain_positions_map(instance, domain_id)
        if actor_key not in world_positions:
            continue
        source = ObservationSource(observer_id=actor_key, domain=domain_id, tick=tick)
        result = build_observations(
            world_positions=world_positions,
            observers={actor_key: range_},
            entities={entity_id: {} for entity_id in world_positions},
            source=source,
        )
        records.extend(result.records)
    return tuple(records)


def _visible_union(
    actor_id: EntityId,
    observations: tuple[ObservationRecord, ...],
    knowledge: KnowledgeState | None,
    local_entity_views: Mapping[EntityId, EntityView],
    world_keys: set,
) -> frozenset[EntityId]:
    """可见集并集（DefaultContextProvider 语义，CX-INV-2 四来源）：
    self ∪ 感知记录 observed_entity_ids ∪ knowledge 参照（∩ 世界实存）
    ∪ local 键集。"""
    visible = frozenset({actor_id})
    for record in observations:
        visible |= frozenset(record.observed_entity_ids)
    if knowledge is not None:
        visible |= frozenset(
            EntityId(eid) for eid in knowledge.reference_entity_ids() if eid in world_keys
        )
    visible |= frozenset(local_entity_views.keys())
    return visible


# —— 公共面（冻结 API；主入口 + wake 下层函数）——


def build_actor_context_for_wakeup(
    instance: WorldInstance,
    actor_id: str,
    *,
    wake_reason: str | None = None,
    tick: int | None = None,
) -> ActorDecisionContext:
    """构建 actor 当刻决策上下文（P4 冻结实现主路径 + 感知物化 + 结果钉）。

    - ``wake_reason``：唤醒原因透传（缺省 None = 主入口口径）；
    - ``tick``：逻辑刻（缺省 = ``instance.runtime.logical_tick``）；
    - actor 不存在 → :class:`ActorUnknownError`（LookupError 族，
      CX-INV-1 显式错误，不产半截 context）。

    结果钉：``self_view`` = actor 自身视图；``observations`` = build_observations
    产物；``visible_entities`` = 感知结果并集口径（DefaultContextProvider 语义）；
    ``local_entity_views`` 只含 visible；``global_entity_views`` = None（无
    world.read.global 授权）；``candidate_actions`` = registry 中能力全满足项
    （casefold 排序）。
    """
    resolved_tick = instance.runtime.logical_tick if tick is None else tick
    resolved_actor_id = EntityId(actor_id)
    state = guard(instance.world)
    table = _build_capability_table(instance)
    base = DefaultContextProvider().build(
        ContextBuildInput(
            actor_id=resolved_actor_id,
            state=state,
            registry=instance.action_registry,
            capability_table=table,
            space_registry=instance.spaces,
            tick=resolved_tick,
            wake_reason=wake_reason,
        )
    )
    observations = _materialize_observations(instance, resolved_actor_id, resolved_tick)
    world_keys = set(state.entities.keys())
    visible_entities = _visible_union(
        resolved_actor_id,
        observations,
        base.knowledge,
        base.local_entity_views,
        world_keys,
    )
    # CX-INV-2 同口径自检：从存储字段重算并集，两侧断言相等（实现漂移防线，
    # P4 同纪律）
    recomputed = frozenset({base.actor_id})
    for record in observations:
        recomputed |= frozenset(record.observed_entity_ids)
    if base.knowledge is not None:
        recomputed |= frozenset(
            EntityId(eid)
            for eid in base.knowledge.reference_entity_ids()
            if eid in world_keys
        )
    recomputed |= frozenset(base.local_entity_views.keys())
    if recomputed != visible_entities:
        raise ContextInvariantError(
            "CX-INV-2 违反：visible_entities 与已物化字段重算并集不等（实现漂移）"
        )
    return ActorDecisionContext(
        actor_id=base.actor_id,
        tick=base.tick,
        base_world_revision=base.base_world_revision,
        wake_reason=base.wake_reason,
        self_view=base.self_view,
        visible_entities=visible_entities,
        local_entity_views=base.local_entity_views,
        global_entity_views=base.global_entity_views,
        observations=observations,
        knowledge=base.knowledge,
        memory=base.memory,
        candidate_actions=base.candidate_actions,
        granted_capabilities=base.granted_capabilities,
    )


def build_actor_context(instance: WorldInstance, actor_id: str) -> ActorDecisionContext:
    """主入口：actor 当刻（``instance.runtime.logical_tick``、wake_reason=None）
    决策上下文（:func:`build_actor_context_for_wakeup` 的缺省参数包装）。

    actor 不存在 → :class:`ActorUnknownError`（显式错误，不静默）。
    """
    return build_actor_context_for_wakeup(instance, actor_id)
