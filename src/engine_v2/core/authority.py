"""engine_v2 core 层 Authority 契约与选择器层（P2-T02 第一阶段）。

依据 ``docs/v2/contracts/P2-kernel-pipeline-design.md``（下称 "P2 设计规范"）
§3 与任务包 P2-T02 目标（selector 层与模型结构；求值器由 P2-T03 在本文件
串行完善）：

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
  ``description``）与策略（``rules`` + ``default_decision``）。**default
  DENY，closed-by-default**（D-P2-09）：无匹配规则回落到
  ``default_decision``（缺省即 DENY）；**首条匹配规则拍板**，不 fall-through；
- §3.6 :data:`KERNEL_STATE_DOMAINS` —— Kernel 声明的内置状态域（P1 设计
  §5.3 "词表由 P2 authority 配置声明" 的落位）；validation（T04）拒绝该集合
  之外的 domain；
- :class:`AuthorityDecision`（PERMIT / DENY）——权限判定决策词表。枚举一律
  ``class Xxx(str, Enum)``（P1 设计 §0.1），JSON 值为字符串字面量；
- :class:`AuthorityError` —— authority 模块异常基类（派生 ``ValueError``，
  与 ``components.ComponentConflictError`` 同款纪律）。第一阶段角色：求值
  接口的输入契约守卫；求值正常路径不抛异常（deny 是返回值，过滤语义在管道
  层，P2 设计规范 §7.3）。T03 完善求值器时可派生具体子类；
- :func:`check_authority` —— **预留求值接口签名**（P2 设计规范 §3.5）。
  本阶段提供确定性首段实现（规则按 ``priority 降序 → specificity 降序 →
  注册序升序`` 稳定排序，首条命中拍板，无匹配 → ``default_decision``），
  纯函数、deny 不抛异常；P2-T03 在本文件串行完善求值器（reason code、trace
  协同等扩展，签名保持）。

配置入口（D-P2-08）：``AuthorityPolicy.model_validate(<dict/JSON>)``，与
Spec §17.1 YAML 示例同构；YAML 解析归 P5 content 层——core import 边界只
允许 stdlib + pydantic + 同包 ``src.engine_v2``，不引入 yaml 依赖。

``ProposedEffect.authority_scope`` **不参与**任何判定（D-P2-17：
声明/prompt 不能定义世界权限），仅随 trace 原样入档供审计。

本模块只 import 标准库、pydantic 与同包 ``src.engine_v2``（P1 设计 §0.3
import 边界白名单），不触碰 v1。
"""

from __future__ import annotations

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
from src.engine_v2.core.ids import ProducerId
from src.engine_v2.core.state import WorldState

__all__ = [
    "AuthorityDecision",
    "AuthorityError",
    "AuthorityPolicy",
    "AuthorityRule",
    "AuthoritySelector",
    "KERNEL_STATE_DOMAINS",
    "check_authority",
    "match_selector",
]


# —— 决策词表与异常 ——


class AuthorityDecision(str, Enum):
    """权限判定决策（任务包 P2-T02；P2 设计规范 §3.5 决策词表）。

    - ``PERMIT``：授予——首条命中规则显式授权该 effect 的 producer
      （``effect.source ∈ rule.allowed_writers``）；
    - ``DENY``：拒绝——无匹配规则（回落 ``AuthorityPolicy.default_decision``，
      缺省即 DENY），或命中规则的 producer 不在 ``allowed_writers``
      （closed-by-default，D-P2-09）。

    枚举一律 ``class Xxx(str, Enum)``（P1 设计 §0.1）：JSON 值为字符串
    字面量（``"permit"`` / ``"deny"``），序列化后仍可与裸字符串比较。
    """

    PERMIT = "permit"
    DENY = "deny"


class AuthorityError(ValueError):
    """Authority 模块异常基类（任务包 P2-T02）。

    派生 ``ValueError``：与 P1 词法/数据校验错误族统一（``ComponentConflictError``
    同款纪律），调用方可按 ``ValueError`` 一类捕获。

    第一阶段角色：求值接口 :func:`check_authority` 的**输入契约守卫**——
    传入不符合契约的类型（非 ``ProposedEffect`` / 非 ``AuthorityPolicy``）
    时抛出。求值正常路径**不抛异常**：deny 是返回值而非异常（过滤语义在
    管道层，P2 设计规范 §7.3）。P2-T03 完善求值器时可按需派生具体子类
    （如政策运行时不一致、selector 组合非法等）。
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
    - ``description``：规则描述（审计/解释用，不参与判定）。
    """

    selector: AuthoritySelector
    allowed_writers: list[ProducerId]
    priority: int = 0
    description: str = ""

    @model_validator(mode="after")
    def _check_allowed_writers_nonempty(self) -> AuthorityRule:
        if not self.allowed_writers:
            raise ValueError(
                "allowed_writers 必须至少一个 writer：closed-by-default 语义下"
                "无 writer 的规则无意义（P2 设计规范 §3.3）"
            )
        return self


class AuthorityPolicy(ContractModel):
    """Authority 策略（Spec §17.1；P2 设计规范 §3.3；closed-by-default D-P2-09）。

    - **配置入口**：``AuthorityPolicy.model_validate(<dict/JSON>)``，与 Spec
      §17.1 YAML 示例同构（YAML 解析归 P5 content 层，D-P2-08：core 不引入
      yaml 依赖）；
    - ``rules``：规则列表（空列表 = 完全封闭——任何 effect 都无法被授权）；
    - ``default_decision``：无匹配规则时的回落决策，**缺省 DENY**
      （closed-by-default：写权限只能由 engine authority system 显式授予，
      K3/K4）；
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


# —— 求值接口（§3.5 签名；T03 串行完善）——


def _ordered_rules(policy: AuthorityPolicy) -> list[AuthorityRule]:
    """按求值序稳定排序规则列表（P2 设计规范 §3.3）。

    排序键：``(priority 降序, specificity 降序)``；Python ``sorted`` 为稳定
    排序，两者同分时注册序（原列表顺序）自然保持——求值序完全确定性。
    """
    return sorted(
        policy.rules,
        key=lambda rule: (-rule.priority, -rule.selector.specificity()),
    )


def check_authority(
    effect: ProposedEffect,
    policy: AuthorityPolicy,
    state: WorldState | None = None,
    *,
    component_registry: ComponentRegistry | None = None,
) -> AuthorityDecision:
    """Authority 求值入口（P2 设计规范 §3.5 签名；预留求值接口）。

    求值序（确定性）：rules 按 ``(priority 降序, specificity 降序, 注册序
    升序)`` 稳定排序；顺序遍历，**首条** :func:`match_selector` 命中的规则
    拍板——``effect.source ∈ rule.allowed_writers`` → :attr:`AuthorityDecision.
    PERMIT`，否则 :attr:`AuthorityDecision.DENY`；**不 fall-through**（被一条
    显式规则命中后不再看后续规则，语义可解释、无叠加歧义，D-P2-09）。
    无匹配规则 → ``policy.default_decision``（缺省 DENY，closed-by-default）。

    纯函数；deny 不抛异常（过滤语义在管道层，P2 设计规范 §7.3）。
    ``ProposedEffect.authority_scope`` **不参与**判定（D-P2-17：
    声明/prompt 不能定义世界权限）。

    Args:
        effect: 待判定的拟议效果。
        policy: 权限策略（规则集 + 默认决策）。
        state: 当前世界状态（透传给 :func:`match_selector`，供
            ``entity_tag`` 维判定；``None`` 时该维度不可判定）。
        component_registry: 组件注册表（透传给 :func:`match_selector`，供
            ``EntityTarget`` 的 ``domain_tag`` 维判定）。

    Returns:
        :class:`AuthorityDecision`——PERMIT 或 DENY。

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
    for rule in _ordered_rules(policy):
        if match_selector(rule.selector, effect, state, component_registry):
            if effect.source in rule.allowed_writers:
                return AuthorityDecision.PERMIT
            return AuthorityDecision.DENY
    return policy.default_decision
