"""engine_v2 core 层 Authority 契约、选择器层与求值层（P2-T02/T03）。

依据 ``docs/v2/contracts/P2-kernel-pipeline-design.md``（下称 "P2 设计规范"）
§3 与任务包 P2-T02（selector 层与模型结构）/ P2-T03（求值器深化与 Trace
协同）目标：

- §3.1 :class:`AuthoritySelector` —— Spec §17.2 selector。任务包口径取**五维**
  （``component_type`` / ``field`` / ``domain_tag`` / ``effect_type`` /
  ``entity_tag``）：**未指定维度 = 通配**，指定维度全部命中才算匹配。全空
  selector 匹配一切效果——合法但有风险，policy 侧通常配合低 priority 规则使用
  （文档化警示，P2 设计规范 §3.1）；
- §3.2 :func:`match_selector` —— selector 层核心纯函数：逐维判定（顺序固定，
  短路）；维度不可判定（无 state / 无 registry / 组件未注册等）→ **不匹配**
  （不可判定 ≠ 默认放行，K3/K4）；
- §3.3 :class:`AuthorityRule` / :class:`AuthorityPolicy` —— 规则（selector +
  ``allowed_writers``（≥1，``model_validator`` 强制）+ ``priority`` +
  ``description`` + 可选 ``rule_id``）与策略（``rules`` +
  ``default_decision``）。**default DENY，closed-by-default**（D-P2-09）：
  无匹配规则严格回落 ``default_decision``（缺省即 DENY）；**首条匹配规则
  拍板**，不 fall-through；
- §3.4 :class:`ProducerRegistry` / :class:`ProducerInfo` /
  :class:`ProducerConflictError` —— producer 运行时注册表（P1 设计 §2.2
  "producer 注册表落位属 Plan P2" 的落位；与 ``ComponentRegistry`` 同款
  纪律：运行时对象、非契约模型、不进 round-trip）；
- §3.5 :func:`check_authority` —— authority 求值入口（P2-T03 求值层）：
  返回 :class:`AuthorityEvaluationResult`（decision + reason_code + 拍板规则
  id/description/index/priority + evaluated_rules_count + advisory 字段）。
  求值序确定性：rules 按 ``(priority 降序, specificity 降序, 注册序升序)``
  稳定排序，**首条** :func:`match_selector` 命中规则拍板——``effect.source ∈
  rule.allowed_writers`` → ALLOW，否则 DENY，**不 fall-through**；无匹配规则
  → 严格回落 ``policy.default_decision``（缺省 DENY，closed-by-default）。
  reason_code 词表冻结于 :data:`AUTHORITY_REASON_CODES`；纯函数、deny 不抛
  异常（过滤语义在管道层，P2 设计规范 §7.3）；
- §3.6 :data:`KERNEL_STATE_DOMAINS` —— Kernel 声明的内置状态域（P1 设计
  §5.3 "词表由 P2 authority 配置声明" 的落位）；validation（T04）拒绝该集合
  之外的 domain；
- §3.7 / D-P2-17: ``ProposedEffect.authority_scope`` **不参与**任何判定
  （K4 不变量：声明/prompt 不能定义世界权限）——求值器仅将其原样透传至
  ``AuthorityEvaluationResult.authority_scope`` 供 advisory 咨询与日志标记，
  该字段仅随 ``proposed_effect`` trace 记录原样入档供审计（P2 设计规范
  §3.7/§9）；
- :class:`AuthorityDecision`（ALLOW / DENY）——权限判定决策词表。枚举一律
  ``class Xxx(str, Enum)``（P1 设计 §0.1），JSON 值为字符串字面量；取值
  词表对齐 P1 ``trace.py`` 的 decision 词表（``allow`` / ``deny``：P1 §4.4
  "decision 词表 P2 定义：allow/deny/…" 与 P2 设计规范 §3.5/§9），Trace
  payload 直接落值、无映射层；
- :class:`AuthorityError` —— authority 模块异常基类（派生 ``ValueError``，
  与 ``components.ComponentConflictError`` 同款纪律）：求值正常路径不抛
  异常（deny 是返回值，过滤语义在管道层）；:class:`ProducerConflictError`
  为其派生类（§3.4 注册冲突）。

Trace 协同（P2 任务包目标 3 / P2 设计规范 §9）：
:meth:`AuthorityEvaluationResult.to_trace_payload` 将求值结果转换为
``authority_decision`` trace payload 格式——恰为 P1 冻结约定键
（``trace.py`` :data:`DECISION_PAYLOAD_KEYS`）三个键 ``effect_id`` /
``decision`` / ``reason``，其中 ``decision`` ∈ {allow, deny}、``reason`` =
reason_code（规则拍板时附拍板规则下标：``rule_allow[rule#<i>]`` 形态，P2
设计规范 §9 "reason = reason_code[+rule index]"）。TraceRecord 本体装配
（record_id / kind / revision-tick 坐标填充）归管道层（T07 cascade）——
本方法只产出 payload 形态且保持确定性（不生成 ID）。

配置入口（D-P2-08）：``AuthorityPolicy.model_validate(<dict/JSON>)``，与
Spec §17.1 YAML 示例同构；YAML 解析归 P5 content 层——core import 边界只
允许 stdlib + pydantic + 同包 ``src.engine_v2``，不引入 yaml 依赖。

本模块只 import 标准库、pydantic 与同包 ``src.engine_v2``（P1 设计 §0.3
import 边界白名单），不触碰 v1。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from pydantic import Field, model_validator

from src.engine_v2.core.components import ComponentRegistry, ComponentTypeId
from src.engine_v2.core.effects import (
    EffectTypeId,
    EntityTarget,
    ProposedEffect,
    StateDomainId,
)
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.ids import EffectId, PRODUCER_ID_PATTERN, ProducerId
from src.engine_v2.core.provenance import OriginKind
from src.engine_v2.core.state import WorldState

__all__ = [
    "AUTHORITY_REASON_CODES",
    "AuthorityDecision",
    "AuthorityError",
    "AuthorityEvaluationResult",
    "AuthorityPolicy",
    "AuthorityRule",
    "AuthoritySelector",
    "KERNEL_STATE_DOMAINS",
    "ProducerConflictError",
    "ProducerInfo",
    "ProducerRegistry",
    "check_authority",
    "match_selector",
]


# —— 决策词表与异常 ——


class AuthorityDecision(str, Enum):
    """权限判定决策词表（P2 设计规范 §3.5；P1 trace.py §4.4 decision 词表）。

    - ``ALLOW``：授予——首条命中规则显式授权该 effect 的 producer
      （``effect.source ∈ rule.allowed_writers``）；
    - ``DENY``：拒绝——无匹配规则（回落 ``AuthorityPolicy.default_decision``，
      缺省即 DENY），或命中规则的 producer 不在 ``allowed_writers``
      （closed-by-default，D-P2-09）。

    取值词表冻结为 P1 ``DECISION_PAYLOAD_KEYS`` 的 decision 词表
    （``allow`` / ``deny``）：``authority_decision`` trace payload 直接落值、
    无映射层（P2-T03 Trace 协同；T02 首段的 ``"permit"`` 字面量已废止）。
    枚举一律 ``class Xxx(str, Enum)``（P1 设计 §0.1）：JSON 值为字符串
    字面量（``"allow"`` / ``"deny"``），序列化后仍可与裸字符串比较。
    """

    ALLOW = "allow"
    DENY = "deny"


class AuthorityError(ValueError):
    """Authority 模块异常基类（任务包 P2-T02；P2-T03 沿用）。

    派生 ``ValueError``：与 P1 词法/数据校验错误族统一（``ComponentConflictError``
    同款纪律），调用方可按 ``ValueError`` 一类捕获。

    角色：求值接口 :func:`check_authority` 的**输入契约守卫**（传入不符合
    契约的类型——非 ``ProposedEffect`` / 非 ``AuthorityPolicy``——时抛出）与
    :class:`ProducerRegistry` 注册侧的词法/类型守卫（§3.4）。求值正常路径
    **不抛异常**：deny 是返回值而非异常（过滤语义在管道层，P2 设计规范
    §7.3）。
    """


class ProducerConflictError(AuthorityError):
    """Producer 注册冲突（P2 设计规范 §3.4；``ValueError`` 族）。

    同一 ``ProducerId`` 重复注册且 info 不一致时抛出；相同 info 重复注册
    幂等（见 :meth:`ProducerRegistry.register`）。
    """


# —— 选择器（§3.1）——


class AuthoritySelector(ContractModel):
    """Authority 选择器（Spec §17.2；P2 设计规范 §3.1；任务包五维口径）。

    匹配语义：**未指定的维度 = 通配**；指定维度**全部命中**才算匹配。
    全空 selector 匹配一切效果——合法但有风险，policy 侧通常配合低 priority
    规则使用（文档化警示，P2 设计规范 §3.1）。

    五个维度（对应任务包 "各维选择器（5 种目标类型）"）：

    - ``component_type``：effect 目标的组件类型（全等匹配）；
    - ``field``：``component_type`` 之下的字段级细化（全等匹配，单段标识符；
      P1 设计 §3.2：field_path 仅供 schema 已注册的组件使用，词法合法性
      由 T04 validation 承担）；
    - ``domain_tag``：domain tag 维度——``EntityTarget`` 经组件注册表的
      ``ComponentSchema.authority_domain`` 判定，``StateDomainTarget`` 与
      ``target.domain`` 直接全等（P2 设计规范 §3.2）；
    - ``effect_type``：effect 类型（全等匹配，**不做前缀/层级匹配**——
      确定性优先）；
    - ``entity_tag``：entity tag 维度——需要当前 state 的实体记录（实体存在
      且其 ``tags`` 含该 tag；实体维度不可判定即不放行）。
    """

    component_type: ComponentTypeId | None = None
    field: str | None = None
    domain_tag: StateDomainId | None = None
    effect_type: EffectTypeId | None = None
    entity_tag: str | None = None

    def specificity(self) -> int:
        """指定维度计数（0–5；越大越具体）。

        规则求值序的 tiebreak 输入（P2 设计规范 §3.3：priority 降序 →
        specificity 降序 → 注册序升序）。
        """
        return sum(
            1
            for value in (
                self.component_type,
                self.field,
                self.domain_tag,
                self.effect_type,
                self.entity_tag,
            )
            if value is not None
        )


# —— 规则与策略（§3.3）——


class AuthorityRule(ContractModel):
    """Authority 规则（Spec §17.1；P2 设计规范 §3.3）。

    - ``selector``：本规则约束的 effect（未指定维度 = 通配）；
    - ``allowed_writers``：对命中 selector 的 effect 拥有写权限的 producer，
      **至少一个**（``model_validator`` 强制——closed-by-default 语义下无
      writer 的规则无意义）；
    - ``priority``：求值优先级，越大越先求值（缺省 0；同分先比 specificity，
      再按注册序——确定性，P2 设计规范 §3.3）；
    - ``description``：规则描述（审计/解释用，不参与判定）；
    - ``rule_id``：可选规则标识（审计/解释用，自由字符串；缺省时求值结果
      的 ``matched_rule_id`` 为 None，以 ``matched_rule_index`` 定位拍板
      规则）。
    """

    selector: AuthoritySelector
    allowed_writers: list[ProducerId]
    priority: int = 0
    description: str = ""
    rule_id: str | None = None

    @model_validator(mode="after")
    def _check_allowed_writers_nonempty(self) -> AuthorityRule:
        if not self.allowed_writers:
            raise ValueError(
                "allowed_writers 必须至少一个 writer：closed-by-default 语义下"
                "无 writer 的规则无意义（P2 设计规范 §3.3）"
            )
        return self

    @model_validator(mode="after")
    def _check_rule_id_nonempty(self) -> AuthorityRule:
        if self.rule_id is not None and self.rule_id == "":
            raise ValueError("rule_id 指定时必须为非空字符串（空串等同缺省）")
        return self


class AuthorityPolicy(ContractModel):
    """Authority 策略（Spec §17.1；P2 设计规范 §3.3；closed-by-default D-P2-09）。

    - **配置入口**：``AuthorityPolicy.model_validate(<dict/JSON>)``，与 Spec
      §17.1 YAML 示例同构（YAML 解析归 P5 content 层，D-P2-08：core 不引入
      yaml 依赖）；
    - ``rules``：规则列表（空列表 = 完全封闭——任何 effect 都无法被授权）；
    - ``default_decision``：无匹配规则时的**严格回落**决策，**缺省 DENY**
      （closed-by-default：写权限只能由 engine authority system 显式授予，
      K3/K4）。显式配置为 ALLOW 属于 policy 的显式声明（配置侧行为），
      与提案侧 ``authority_scope`` 声明提权（K4 禁止）无关；
    - 整体为 ``ContractModel``（frozen + extra=forbid），可 JSON round-trip。
    """

    rules: list[AuthorityRule] = Field(default_factory=list)
    default_decision: AuthorityDecision = AuthorityDecision.DENY


# —— 内置状态域词表（§3.6）——

#: Kernel 内置状态域（P2 设计规范 §3.6；P1 设计 §5.3 "词表由 P2 authority
#: 配置声明" 的落位）：与 WorldState 字段对应的两个域。validation 阶段
#: （T04）拒绝该集合之外的 domain；未来扩展经 Gate review 追加本常量
#: （public contract 变更纪律）。实体相关变更永远经 ``EntityTarget``，
#: 不存在第三个实体域。
KERNEL_STATE_DOMAINS: Final[frozenset[StateDomainId]] = frozenset(
    {StateDomainId("world_variables"), StateDomainId("scenario")}
)


# —— producer 注册表（§3.4）——


@dataclass(frozen=True)
class ProducerInfo:
    """已注册 producer 的运行时元数据（P2 设计规范 §3.4）。

    运行时对象（frozen dataclass，非契约模型、不进 round-trip），与
    ``ComponentRegistry`` / ``ComponentSchema`` 同款纪律：

    - ``producer_id``：producer 标识（名字型，P1 设计 §2.2 D-4）；
    - ``origin``：K6 "谁提出" 来源词表（P1 ``provenance.OriginKind``）；
    - ``priority``：冲突解析 "producer priority" 策略的输入（P2 设计规范
      §5.4）；
    - ``description``：注册描述（审计用，不参与任何判定）。
    """

    producer_id: ProducerId
    origin: OriginKind
    priority: int = 0
    description: str = ""


class ProducerRegistry:
    """Producer 注册表（P1 设计 §2.2 "producer 注册表落位属 Plan P2" 落位；
    P2 设计规范 §3.4）。

    运行时对象（**非**契约模型、不进 round-trip），与 ``ComponentRegistry``
    同款纪律：注册时校验 + 幂等/冲突纪律。未注册 producer ≠ 错误
    （:meth:`get` 返回 None）——与 closed-by-default 一致：未注册 producer
    无任何显式授予，其权限判定完全由 policy 规则拍板（无匹配规则 → 回落
    ``default_decision``，缺省 DENY）。
    """

    __slots__ = ("_producers",)

    def __init__(self) -> None:
        self._producers: dict[ProducerId, ProducerInfo] = {}

    def register(self, info: ProducerInfo) -> None:
        """注册 producer 元数据（P2 设计规范 §3.4）。

        - 注册时校验 ``ProducerId`` 词法（``PRODUCER_ID_PATTERN`` fullmatch）：
          ``_TypedId`` 构造函数不做词法校验（P1 设计 §2.2"测试可用确定性
          构造"），注册侧作为公共入口复检（纵深防御，C7 检查器同款哲学）；
        - 重复注册：同 info 幂等；冲突 → :class:`ProducerConflictError`。

        Raises:
            AuthorityError: ``info`` 不是 ``ProducerInfo``，或其
                ``producer_id`` 词法非法。
            ProducerConflictError: 同 ``ProducerId`` 已注册不同 info。
        """
        if not isinstance(info, ProducerInfo):
            raise AuthorityError(
                f"ProducerRegistry.register 需要 ProducerInfo，得到 {type(info).__name__}"
            )
        producer_id = info.producer_id
        if not PRODUCER_ID_PATTERN.fullmatch(str(producer_id)):
            raise AuthorityError(
                f"ProducerId 词法非法（须匹配 {PRODUCER_ID_PATTERN.pattern!r}）："
                f"{str(producer_id)!r}"
            )
        existing = self._producers.get(producer_id)
        if existing is not None:
            if existing == info:
                return
            raise ProducerConflictError(
                f"producer {str(producer_id)!r} 已注册不同 info："
                f"existing={existing!r}，new={info!r}"
            )
        self._producers[producer_id] = info

    def get(self, producer_id: ProducerId) -> ProducerInfo | None:
        """查询 producer 元数据；未注册返回 None（未注册 ≠ 错误）。"""
        return self._producers.get(producer_id)

    def origin_of(
        self, producer_id: ProducerId, default: OriginKind = OriginKind.SYSTEM
    ) -> OriginKind:
        """查询 producer 的 origin；未注册返回 ``default``（缺省 SYSTEM）。"""
        info = self._producers.get(producer_id)
        return info.origin if info is not None else default

    def priority_of(self, producer_id: ProducerId, default: int = 0) -> int:
        """查询 producer 的冲突优先级；未注册返回 ``default``（缺省 0）。"""
        info = self._producers.get(producer_id)
        return info.priority if info is not None else default


# —— 选择器匹配（§3.2，P2-T02 核心纯函数）——


def match_selector(
    selector: AuthoritySelector,
    effect: ProposedEffect,
    state: WorldState | None = None,
    component_registry: ComponentRegistry | None = None,
) -> bool:
    """selector 匹配纯函数（P2 设计规范 §3.2；逐维判定，顺序固定，短路）。

    逐维判定：

    1. ``effect_type``：与 ``effect.effect_type`` 全等（不做前缀/层级匹配——
       确定性优先）；两种 target 种类通用；
    2. target 分派：

       - ``EntityTarget``：
         - ``component_type`` 维：与 ``target.component_type`` 全等；selector
           指定而 effect 未指定 → 不匹配；
         - ``field`` 维：与 ``target.field_path`` 全等；selector 指定而 effect
           ``field_path is None`` → 不匹配；
         - ``domain_tag`` 维：经 ``component_registry`` 查
           ``target.component_type`` 的 ``ComponentSchema.authority_domain``
           （P1 设计 §3.3 预留字段）与之全等；组件未注册或无
           ``authority_domain`` → 不匹配（域不可判定 ≠ 默认放行）；
         - ``entity_tag`` 维：需要 ``state``——查
           ``state.entities[target.entity_id]`` 的 ``tags``（P1 设计 §3.1
           预留字段）；``state is None`` 或实体不存在 → 不匹配（实体维度
           不可判定即不放行）。
       - ``StateDomainTarget``：``domain_tag`` 维与 ``target.domain`` 全等；
         ``component_type`` / ``field`` / ``entity_tag`` 维若被 selector
         指定 → 不匹配（维度与目标种类不相容）。

    Args:
        selector: 待匹配的选择器。
        effect: 待匹配的拟议效果。
        state: 当前世界状态（仅 ``entity_tag`` 维需要；``None`` 时该维度
            不可判定——selector 未指定 ``entity_tag`` 则不受影响）。
        component_registry: 组件注册表（仅 ``EntityTarget`` 的
            ``domain_tag`` 维需要；``None`` 时该维度不可判定）。

    Returns:
        ``True`` = 匹配（全部指定维度命中）；``False`` = 不匹配。
    """
    # 1. effect_type 维（两种 target 种类通用；全等，不做前缀/层级匹配）
    if selector.effect_type is not None and selector.effect_type != effect.effect_type:
        return False

    target = effect.target
    if isinstance(target, EntityTarget):
        # 2a. component_type 维：selector 指定而 effect 未指定 → 不匹配
        if selector.component_type is not None:
            if target.component_type is None or selector.component_type != target.component_type:
                return False
        # 2b. field 维：selector 指定而 effect field_path is None → 不匹配
        if selector.field is not None:
            if target.field_path is None or selector.field != target.field_path:
                return False
        # 2c. domain_tag 维：经 registry 查 authority_domain；不可判定 → 不匹配
        if selector.domain_tag is not None:
            schema = (
                component_registry.get(target.component_type)
                if component_registry is not None and target.component_type is not None
                else None
            )
            if (
                schema is None
                or schema.authority_domain is None
                or selector.domain_tag != schema.authority_domain
            ):
                return False
        # 2d. entity_tag 维：需要 state 的实体记录；不可判定 → 不匹配
        if selector.entity_tag is not None:
            record = state.entities.get(target.entity_id) if state is not None else None
            if record is None or selector.entity_tag not in record.tags:
                return False
    else:
        # 2e. StateDomainTarget：component_type/field/entity_tag 维不相容
        if (
            selector.component_type is not None
            or selector.field is not None
            or selector.entity_tag is not None
        ):
            return False
        if selector.domain_tag is not None and selector.domain_tag != target.domain:
            return False
    return True


# —— 求值层（P2-T03；P2 设计规范 §3.3/§3.5/§3.7/§9）——


#: reason_code 冻结词表（P2 设计规范 §3.5 可解释性字段；P2 任务包 P2-T03
#: 输出结构约定）：
#:
#: - ``rule_allow``：首条匹配规则命中且 producer 在 ``allowed_writers`` 内；
#: - ``rule_deny``：首条匹配规则命中但 producer 不在 ``allowed_writers`` 内
#:   （不 fall-through，后续规则不被参考）；
#: - ``no_matching_rule``：无匹配规则——严格回落
#:   ``AuthorityPolicy.default_decision``（缺省 DENY）。
AUTHORITY_REASON_CODES: Final[tuple[str, ...]] = (
    "rule_allow",
    "rule_deny",
    "no_matching_rule",
)


def _ordered_rules(policy: AuthorityPolicy) -> list[AuthorityRule]:
    """按求值序稳定排序规则列表（P2 设计规范 §3.3）。

    排序键：``(priority 降序, specificity 降序)``；Python ``sorted`` 为稳定
    排序，两者同分时注册序（原列表顺序）自然保持——求值序完全确定性。
    """
    return sorted(
        policy.rules,
        key=lambda rule: (-rule.priority, -rule.selector.specificity()),
    )


@dataclass(frozen=True)
class AuthorityEvaluationResult:
    """Authority 求值结果结构（P2 任务包 P2-T03；P2 设计规范 §3.5 可解释性）。

    运行时结果对象（frozen dataclass，非契约模型、不进 round-trip）——承载
    管道层过滤（``decision``）、冲突解析（``rule_priority`` →
    AuthorityPriorityStrategy 输入，P2 设计规范 §5.4）与 trace 归档
    （:meth:`to_trace_payload`）所需的全部解释：

    - ``decision``：ALLOW / DENY（取值词表即 P1 trace decision 词表）；
    - ``reason_code``：:data:`AUTHORITY_REASON_CODES` 词表；
    - ``matched_rule_id`` / ``matched_rule_description``：拍板规则的
      ``rule_id`` 与 ``description``（无规则匹配时均为 None；规则
      description 为空串时规整为 None）；
    - ``matched_rule_index``：拍板规则在**求值序排序后** rules 列表中的下标
      （无规则匹配时 None；P2 设计规范 §3.5 可解释性字段）；
    - ``rule_priority``：拍板规则的 priority（冲突解析策略 1 的输入；无规则
      匹配时 None）；
    - ``evaluated_rules_count``：本次求值实际遍历的规则数——规则拍板时 =
      命中位置 + 1（首条命中即拍板，后续规则不再求值）；无规则匹配时 =
      policy 规则总数；
    - ``effect_id`` / ``producer``：求值对象坐标（``effect_id`` 为 trace
      payload 约定键值；``producer`` = ``effect.source``，因果关联与
      可解释性）；
    - ``selector``：拍板规则的 selector（无规则匹配时 None）；
    - ``authority_scope``：``effect.authority_scope`` 原样透传（D-P2-17
      **仅咨询**：不参与任何判定，仅供审计/日志标记——K4 不变量）。
    """

    effect_id: EffectId
    producer: ProducerId
    decision: AuthorityDecision
    reason_code: str
    evaluated_rules_count: int
    matched_rule_id: str | None = None
    matched_rule_description: str | None = None
    matched_rule_index: int | None = None
    rule_priority: int | None = None
    selector: AuthoritySelector | None = None
    authority_scope: str | None = None

    def to_trace_payload(self) -> dict[str, str]:
        """转换为 ``authority_decision`` trace payload 格式（P2 设计规范 §9）。

        符合 P1 冻结子约定（``trace.py`` :data:`DECISION_PAYLOAD_KEYS`）：
        恰为三个约定键 ``effect_id`` / ``decision`` / ``reason``——

        - ``effect_id``：被求值 effect ID 的字符串形态；
        - ``decision``：``allow`` / ``deny``（P1 decision 词表，枚举值
          直接落值、无映射层）；
        - ``reason``：``reason_code``；规则拍板时附拍板规则下标
          （``rule_allow[rule#<i>]`` / ``rule_deny[rule#<i>]``，P2 设计规范
          §9 "reason = reason_code[+rule index]"）。

        ``authority_scope`` 不入本 payload（D-P2-17：advisory 字段仅随
        ``proposed_effect`` 记录原样入档，P2 设计规范 §3.7）。TraceRecord
        本体装配（record_id / kind / revision-tick 坐标填充）归管道层
        （T07 cascade）。
        """
        reason = self.reason_code
        if self.matched_rule_index is not None:
            reason = f"{reason}[rule#{self.matched_rule_index}]"
        return {
            "effect_id": str(self.effect_id),
            "decision": self.decision.value,
            "reason": reason,
        }


def check_authority(
    effect: ProposedEffect,
    policy: AuthorityPolicy,
    state: WorldState | None = None,
    *,
    component_registry: ComponentRegistry | None = None,
) -> AuthorityEvaluationResult:
    """Authority 求值入口（P2 设计规范 §3.5 签名；P2-T03 求值层完善）。

    求值序（确定性）：rules 按 ``(priority 降序, specificity 降序, 注册序
    升序)`` 稳定排序；顺序遍历，**首条** :func:`match_selector` 命中的规则
    拍板——``effect.source ∈ rule.allowed_writers`` → ALLOW
    （``reason_code=rule_allow``），否则 DENY（``reason_code=rule_deny``）；
    **不 fall-through**（被一条显式规则命中后不再看后续规则，语义可解释、
    无叠加歧义，D-P2-09）。无匹配规则 → 严格回落
    ``policy.default_decision``（缺省 DENY，closed-by-default；
    ``reason_code=no_matching_rule``）。

    ``ProposedEffect.authority_scope`` **不参与**判定（D-P2-17：
    声明/prompt 不能定义世界权限，K4 不变量）——结果结构仅将其原样透传至
    ``AuthorityEvaluationResult.authority_scope`` 供 advisory 咨询与日志
    标记。

    纯函数；deny 不抛异常（过滤语义在管道层，P2 设计规范 §7.3）。

    Args:
        effect: 待判定的拟议效果。
        policy: 权限策略（规则集 + 默认决策）。
        state: 当前世界状态（透传给 :func:`match_selector`，供
            ``entity_tag`` 维判定；``None`` 时该维度不可判定）。
        component_registry: 组件注册表（透传给 :func:`match_selector`，供
            ``EntityTarget`` 的 ``domain_tag`` 维判定）。

    Returns:
        :class:`AuthorityEvaluationResult`——decision + reason code + 拍板
        规则解释 + 求值计数 + advisory 字段。

    Raises:
        AuthorityError: ``effect`` 不是 ``ProposedEffect`` 或 ``policy`` 不是
            ``AuthorityPolicy``（输入契约守卫）。
    """
    if not isinstance(effect, ProposedEffect):
        raise AuthorityError(
            f"check_authority 需要 ProposedEffect，得到 {type(effect).__name__}"
        )
    if not isinstance(policy, AuthorityPolicy):
        raise AuthorityError(
            f"check_authority 需要 AuthorityPolicy，得到 {type(policy).__name__}"
        )
    for index, rule in enumerate(_ordered_rules(policy)):
        if not match_selector(rule.selector, effect, state, component_registry):
            continue
        granted = effect.source in rule.allowed_writers
        decision = AuthorityDecision.ALLOW if granted else AuthorityDecision.DENY
        return AuthorityEvaluationResult(
            effect_id=effect.effect_id,
            producer=effect.source,
            decision=decision,
            reason_code="rule_allow" if granted else "rule_deny",
            evaluated_rules_count=index + 1,
            matched_rule_id=rule.rule_id,
            matched_rule_description=rule.description or None,
            matched_rule_index=index,
            rule_priority=rule.priority,
            selector=rule.selector,
            authority_scope=effect.authority_scope,
        )
    # 无匹配规则 → closed-by-default 严格回落（D-P2-09）
    return AuthorityEvaluationResult(
        effect_id=effect.effect_id,
        producer=effect.source,
        decision=policy.default_decision,
        reason_code="no_matching_rule",
        evaluated_rules_count=len(policy.rules),
        authority_scope=effect.authority_scope,
    )
