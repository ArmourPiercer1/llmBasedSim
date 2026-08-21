"""engine_v2 core 层 Effect Validation（P2 设计规范 §4；P2-T04 实现载体）。

**职责**（P2 设计规范 §1.2 / §4）：

- **L1 单 effect 校验**（D-P2-10 第一层，round 内、冲突解析前）：
  :class:`EffectValidator` 的**七阶段固定管道**——(1) ID 种类与前缀
  （D-P2-15，:func:`check_effect_id_kinds`）；(2) 类型标识符词法；
  (3) domain 词表与 payload schema（含 ComponentRegistry 校验）；
  (4) 实体存在性（``core.create_entity`` 与批内已创建实体豁免）；(5) field_path 合法性
  （§4.6）；(6) 陈旧性（``is_stale`` 单向语义 + 未来版本拒绝）；
  (7) 结构前置条件 + handler 存在性（D-P2-05）。阶段固定顺序、前序不
  短路后续——一次性收齐全部问题（trace 可解释性最大化）。失败 effect
  被**过滤**（``validate_batch`` 返回 :class:`ValidationReport`），其余
  effect 继续；
- **L2 事务终检**（D-P2-10 第二层，事务装配后、reducer 应用前）：
  :func:`check_transaction_references`——P1 设计 §10.1 义务 **C2 晋升**
  （逐字迁移，见下方溯源行）；失败 → 整事务原子失败（ABORTED，
  revision 不动，Plan 必须测试 3）；
- **任务包表面**：:func:`validate_proposed_effect`（L1 单效果基础校验器，
  ``(effect, state, component_registry) -> (bool, str | None)``）、
  :class:`ValidationPipeline`（组合类：EffectValidator 全量行为 + 严格
  模式入口 :meth:`ValidationPipeline.run`）、:class:`ValidationError`
  （严格模式异常，携带全量 :class:`ValidationIssue`）。

**C2 晋升溯源（P1 设计 §10.1 义务 C2 / P2 设计规范 §4.5）**：
:func:`check_transaction_references` 由 P2-T04 按 C2 晋升——实现体从
``tests/engine_v2/core/test_transaction_references.py``（P1-T06 测试侧
落位）**逐字移入**本模块：签名 ``(state, txn) -> tuple[str, ...]`` 与
问题串格式 ``kind:effect_id:详情``、单向 stale 语义（``base > current``
不报）、ABORTED 事务空转、state_domain 分支不查实体、只报告不处置
（纯函数、不抛异常）全部保持不变；``ISSUE_KINDS`` 随之升格为本模块
常量 :data:`TRANSACTION_REFERENCE_ISSUE_KINDS`。测试文件 15 例断言
逐条保留、改从本模块 import（验收口径不变，只换被测对象来源）。

**L1 阶段间分工（避免同一事实双报告）**：实体存在性（含
``core.remove_component`` 的组件挂载检查）由阶段 4 以专属 kind
（``missing_entity`` / ``missing_component``）报告；阶段 7 的结构
前置条件复检（"与 reducer 同规则，提前过滤"）**不再重复**阶段 4 已
覆盖的"entity 不存在 / 组件未挂载"事实，只报告其余前置条件（create
目标已存在、world variable 键缺失、目标种类/domain/component_type
不匹配等）。同一 effect 被过滤是两层语义的共同结果，报告不重叠。

**P2-REMEDIATION（B1 修复）**：``core.create_entity`` 的目标实体按
定义不在基线状态中——两层校验均引入**批内已创建实体集合**
``created_in_batch`` 语义：L1 :meth:`EffectValidator.validate_batch`
按到达序累积已被接受的创建效果（经 ``ValidationContext.
created_in_batch`` 派生逐 effect 上下文），L2
:func:`check_transaction_references` 按 ``sequence`` 序登记创建效果
目标——同批次后续效果引用批内创建的实体视为合法暂存依赖，不报
``missing_entity``（先创建后 ``core.set_component`` 初始化挂载由此
全链路放行；顺序语义与 reducer 暂存按 sequence 应用一致）。

Import 边界（P1 设计 §0.3 继承）：只允许 stdlib + pydantic + 同包
``src.engine_v2``（依赖单向指向 reducer/authority 契约与行为件，§1.3
依赖图无环）。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any, Final

from pydantic import ValidationError as PydanticValidationError

from src.engine_v2.core.authority import KERNEL_STATE_DOMAINS
from src.engine_v2.core.components import ComponentRegistry, parse_component_type_id
from src.engine_v2.core.effects import (
    EntityTarget,
    ProposedEffect,
    StateDomainTarget,
    parse_effect_type_id,
    parse_state_domain_id,
)
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.ids import EntityId, parse_id
from src.engine_v2.core.provenance import CauseKind
from src.engine_v2.core.reducer import (
    EFFECT_CREATE_ENTITY,
    EFFECT_REMOVE_COMPONENT,
    EFFECT_REMOVE_ENTITY,
    EFFECT_REMOVE_WORLD_VARIABLE,
    EFFECT_SET_COMPONENT,
    EFFECT_SET_SCENARIO_DATA,
    EFFECT_SET_WORLD_VARIABLE,
    CreateEntityPayload,
    EffectHandlerRegistry,
    EmptyPayload,
    RemoveWorldVariablePayload,
    SetScenarioDataPayload,
    SetWorldVariablePayload,
    STRUCTURAL_EFFECT_TYPES,
)
from src.engine_v2.core.revision import is_stale
from src.engine_v2.core.state import WorldState
from src.engine_v2.core.transaction import Transaction

__all__ = [
    "EffectValidator",
    "TRANSACTION_REFERENCE_ISSUE_KINDS",
    "VALIDATION_ISSUE_KINDS",
    "ValidationError",
    "ValidationContext",
    "ValidationIssue",
    "ValidationPipeline",
    "ValidationReport",
    "check_effect_id_kinds",
    "check_transaction_references",
    "validate_proposed_effect",
]


# —— 问题 kind 词表（§4.2；冻结词表）——

#: 单 effect 校验问题 kind 冻结词表（P2 设计规范 §4.2）。其中
#: ``missing_entity`` / ``stale_revision`` / ``duplicated_effect_id``
#: 与 C7 检查器（:data:`TRANSACTION_REFERENCE_ISSUE_KINDS`）逐字对齐。
VALIDATION_ISSUE_KINDS: Final[frozenset[str]] = frozenset(
    {
        "bad_id_kind",
        "bad_type_id",
        "bad_payload",
        "bad_field_path",
        "missing_entity",
        "missing_component",
        "stale_revision",
        "future_base_revision",
        "unknown_domain",
        "no_handler",
        "precondition_failed",
        "duplicated_effect_id",
    }
)

#: 事务终检（C2 晋升）问题 kind（P1 设计 §7.4 C7 三项；由测试侧
#: ``ISSUE_KINDS`` 升格，值逐字不变）。
TRANSACTION_REFERENCE_ISSUE_KINDS: Final[tuple[str, ...]] = (
    "missing_entity",
    "stale_revision",
    "duplicated_effect_id",
)

#: field_path 词法（§4.6）：单段标识符（P2 只支持单层字段名；嵌套路径
#: 语法归 P5 内容 DSL）。
_FIELD_PATH_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]*")

#: CauseRef.ref_id 按 CauseKind 的期望 ID 种类（§4.4 末行；INTERVENTION
#: 按 D-P2-20 以 TraceRecordId 词法校验——开发干预在 trace 中以
#: ``dev_intervention`` 记录承载，无独立 ID 族）。
_CAUSE_REF_EXPECTED_KIND: Final[dict[CauseKind, str]] = {
    CauseKind.EVENT: "EventId",
    CauseKind.ACTION: "ActionInstanceId",
    CauseKind.EFFECT: "EffectId",
    CauseKind.PROPOSAL: "ActionInstanceId",
    CauseKind.INTERVENTION: "TraceRecordId",
}

#: 结构效果 payload 模型表（§2.1；``core.set_component`` 的 payload 即
#: 完整组件数据 dict，单独处理，不在本表）。
_STRUCTURAL_PAYLOAD_MODELS: Final[dict[Any, type[ContractModel]]] = {
    EFFECT_CREATE_ENTITY: CreateEntityPayload,
    EFFECT_REMOVE_ENTITY: EmptyPayload,
    EFFECT_REMOVE_COMPONENT: EmptyPayload,
    EFFECT_SET_WORLD_VARIABLE: SetWorldVariablePayload,
    EFFECT_REMOVE_WORLD_VARIABLE: RemoveWorldVariablePayload,
    EFFECT_SET_SCENARIO_DATA: SetScenarioDataPayload,
}


# —— 数据形状（§4.2）——


@dataclass(frozen=True)
class ValidationContext:
    """单 effect 校验上下文（P2 设计规范 §4.2）。

    - ``state``：校验对照的权威世界状态；
    - ``component_registry``：组件 schema 注册表；None → 跳过
      ``core.set_component`` / ``core.create_entity``（components 逐项）
      的 registry schema 校验与 field_path 的 schema 语义检查
      （field_path 合法性不可判定 → 保守拒绝，§4.6）；
    - ``handlers``：handler 注册表；None → 跳过 no_handler 阶段
      （纯数据校验场景）。
    - ``created_in_batch``：同批次**前序**已被接受的
      ``core.create_entity`` 效果创建的实体 ID 集合（P2-REMEDIATION B1
      修复：批内暂存依赖）——引用这些实体的后续效果不报
      ``missing_entity``。缺省空集 = 仅对照基线状态；
      :meth:`EffectValidator.validate_batch` 按到达序自动累积并以
      ``replace`` 派生逐 effect 上下文，单 effect 调用方无需感知。
    """

    state: WorldState
    component_registry: ComponentRegistry | None = None
    handlers: EffectHandlerRegistry | None = None
    created_in_batch: frozenset[EntityId] = frozenset()


@dataclass(frozen=True)
class ValidationIssue:
    """单条校验问题（P2 设计规范 §4.2）。

    ``kind`` 取 :data:`VALIDATION_ISSUE_KINDS` 词表；``to_trace_str``
    产出 ``kind:effect_id:detail`` 串（与 C7 报告串同构，trace
    ``VALIDATION_DECISION`` 的 reason 分号串接即用此形态，§9）。
    """

    kind: str
    effect_id: str
    detail: str

    def to_trace_str(self) -> str:
        """``"kind:effect_id:detail"``（与 C7 报告串同构）。"""
        return f"{self.kind}:{self.effect_id}:{self.detail}"


@dataclass(frozen=True)
class ValidationReport:
    """:meth:`EffectValidator.validate_batch` 的批级报告（§4.2）。

    - ``accepted``：通过全部七阶段且未卷入批级重复 ID 的 effect（到达序）；
    - ``issues``：全量问题（逐 effect 阶段序 + 批级重复 ID 问题殿后）。
    """

    accepted: tuple[ProposedEffect, ...]
    issues: tuple[ValidationIssue, ...]

    def issues_for(self, effect_id: str) -> tuple[ValidationIssue, ...]:
        """指定 effect_id 的全部问题（原序）。"""
        return tuple(issue for issue in self.issues if issue.effect_id == effect_id)

    @property
    def ok(self) -> bool:
        """零问题（accepted 覆盖全部输入）当且仅当 True。"""
        return not self.issues


class ValidationError(ValueError):
    """严格校验失败异常（P2-T04 任务包表面）。

    由 :meth:`ValidationPipeline.run` 在检测到任何问题时抛出——携带全量
    问题列表（``issues`` 属性，:class:`ValidationIssue` 元组）；消息为
    各问题 :meth:`ValidationIssue.to_trace_str` 的分号串接。

    派生自 ``ValueError``：与词法/数据校验错误族统一，调用方可按
    ``ValueError`` 一类捕获。**管道 L1 不抛本异常**——D-P2-10 过滤
    语义下 ``validate_batch`` 返回 :class:`ValidationReport`，异常
    仅供管道外的严格模式调用方（直接校验、fail-fast 装配）。
    """

    def __init__(self, issues: Sequence[ValidationIssue]) -> None:
        self.issues: tuple[ValidationIssue, ...] = tuple(issues)
        super().__init__("validation failed: " + "; ".join(i.to_trace_str() for i in self.issues))


# —— 阶段 1：ID 种类与前缀（D-P2-15 / D-P2-20；§4.4）——


def _id_kind_violations(effect: ProposedEffect) -> tuple[tuple[str, str, str, str], ...]:
    """§4.4 期望种类表的全量 ID 复检（阶段 1 内部数据源）。

    返回 ``(field, expected_kind, got_kind_or_lexErr, value)`` 四元组
    序列（检查序：effect_id / source / target.entity_id /
    target.component_type / target.domain / effect_type /
    cause_ids[*].ref_id）。``parse_id`` 对错误种类的 typed ID 实例同样
    有效：种类与值前缀双重不一致时以 parse 结果为准报告（§4.4 末段）。
    词法型字段（component_type / domain / effect_type）非法时 got 为
    ``"lexErr"``。
    """
    violations: list[tuple[str, str, str, str]] = []

    def _id_field(field: str, expected_kind: str, value: object) -> None:
        text = str(value)
        try:
            kind, _ = parse_id(text)
        except ValueError:
            kind = "lexErr"
        if kind != expected_kind:
            violations.append((field, expected_kind, kind, text))

    def _type_field(field: str, expected_kind: str, value: object, parse: Any) -> None:
        text = str(value)
        try:
            parse(text)
        except ValueError:
            violations.append((field, expected_kind, "lexErr", text))

    _id_field("effect_id", "EffectId", effect.effect_id)
    _id_field("source", "ProducerId", effect.source)
    target = effect.target
    if isinstance(target, EntityTarget):
        _id_field("target.entity_id", "EntityId", target.entity_id)
        if target.component_type is not None:
            _type_field(
                "target.component_type",
                "ComponentTypeId",
                target.component_type,
                parse_component_type_id,
            )
    elif isinstance(target, StateDomainTarget):
        _type_field("target.domain", "StateDomainId", target.domain, parse_state_domain_id)
    _type_field("effect_type", "EffectTypeId", effect.effect_type, parse_effect_type_id)
    for index, cause in enumerate(effect.cause_ids):
        _id_field(f"cause_ids[{index}].ref_id", _CAUSE_REF_EXPECTED_KIND[cause.kind], cause.ref_id)
    return tuple(violations)


def check_effect_id_kinds(effect: ProposedEffect) -> tuple[str, ...]:
    """跨种类 ID 词法与前缀严格校验（P2 设计规范 §4.4；D-P2-15）。

    纯函数；对 effect 的全量 ID（effect_id / source / target 定位键 /
    effect_type / cause_ids[*].ref_id）做种类 + 前缀复检。typed ID 的
    pydantic 路径（AfterValidator 重建）不校验前缀词法——``EffectId``
    实例或错误前缀串落入 ``EntityId`` 字段会被静默重建（P1-T07 §D.2
    实测），本函数在 L1 校验期显式拒绝（P1 §10.1 义务 3）。

    Returns:
        问题串元组，格式
        ``'bad_id_kind:<field>:expected=<kind> got=<kind|lexErr>:value=<v>'``；
        空元组 = 全部 ID 种类与前缀合法。
    """
    return tuple(
        f"bad_id_kind:{field}:expected={expected} got={got}:value={value}"
        for field, expected, got, value in _id_kind_violations(effect)
    )


# —— 阶段 2–7（私有纯函数；签名 (effect[, ctx]) -> tuple[ValidationIssue, ...]）——


def _stage_type_lexical(effect: ProposedEffect) -> tuple[ValidationIssue, ...]:
    """阶段 2：类型标识符词法（``bad_type_id``）。

    ``effect_type``（``parse_effect_type_id``）；StateDomainTarget 的
    ``domain``（``parse_state_domain_id``）。与阶段 1 的 ``bad_id_kind``
    并行收齐（阶段不短路，§4.3）——词法非法的类型标识符两个阶段各报一
    条，kind 不同（ID 面 vs 类型面），trace 两侧皆可解释。
    """
    issues: list[ValidationIssue] = []
    effect_id = str(effect.effect_id)
    try:
        parse_effect_type_id(str(effect.effect_type))
    except ValueError:
        issues.append(
            ValidationIssue(
                "bad_type_id",
                effect_id,
                f"effect_type={str(effect.effect_type)!r} 不匹配 EffectTypeId 词法",
            )
        )
    if isinstance(effect.target, StateDomainTarget):
        try:
            parse_state_domain_id(str(effect.target.domain))
        except ValueError:
            issues.append(
                ValidationIssue(
                    "bad_type_id",
                    effect_id,
                    f"target.domain={str(effect.target.domain)!r} 不匹配 StateDomainId 词法",
                )
            )
    return tuple(issues)


def _stage_domain_payload(
    effect: ProposedEffect, ctx: ValidationContext
) -> tuple[ValidationIssue, ...]:
    """阶段 3：domain 词表与 payload schema（``unknown_domain`` / ``bad_payload``）。

    - StateDomainTarget 的 ``domain`` ∈ ``KERNEL_STATE_DOMAINS``（§3.6；
      词表之外的域拒绝，未来扩展经 Gate review 追加常量）；
    - 结构效果 payload 按 §2.1 模型校验（``extra="forbid"`` 拒绝多余
      键）；``core.create_entity`` 的 components 键做 ComponentTypeId
      词法复检，``component_registry`` 在场时对
      ``core.set_component`` 与 ``core.create_entity``（components 逐项）
      执行 ``validate_payload``（D-8 校验点，与 reducer 同规则）；
    - 语义效果 payload 由 handler 约定，本阶段不查（§4.3 阶段 3 末行）。
    """
    issues: list[ValidationIssue] = []
    effect_id = str(effect.effect_id)
    target = effect.target

    if isinstance(target, StateDomainTarget) and target.domain not in KERNEL_STATE_DOMAINS:
        issues.append(
            ValidationIssue(
                "unknown_domain",
                effect_id,
                f"domain={str(target.domain)!r} 不在 KERNEL_STATE_DOMAINS"
                "（world_variables/scenario）内",
            )
        )

    effect_type = effect.effect_type
    if effect_type not in STRUCTURAL_EFFECT_TYPES:
        return tuple(issues)

    if effect_type == EFFECT_SET_COMPONENT:
        if not isinstance(effect.payload, dict):
            issues.append(
                ValidationIssue(
                    "bad_payload",
                    effect_id,
                    "core.set_component payload 必须为完整 JSON 对象（dict，整体替换）",
                )
            )
            return tuple(issues)
        if (
            ctx.component_registry is not None
            and isinstance(target, EntityTarget)
            and target.component_type is not None
        ):
            try:
                ctx.component_registry.validate_payload(target.component_type, effect.payload)
            except PydanticValidationError as err:
                issues.append(
                    ValidationIssue(
                        "bad_payload",
                        effect_id,
                        f"组件 {str(target.component_type)} 数据不符合已注册 schema：{err}",
                    )
                )
        return tuple(issues)

    model = _STRUCTURAL_PAYLOAD_MODELS[effect_type]
    try:
        payload = model.model_validate(effect.payload)
    except PydanticValidationError as err:
        issues.append(
            ValidationIssue(
                "bad_payload", effect_id, f"payload 不符合 {model.__name__}：{err}"
            )
        )
        return tuple(issues)

    if effect_type == EFFECT_CREATE_ENTITY:
        for raw_type, data in payload.components.items():
            try:
                component_type = parse_component_type_id(raw_type)
            except ValueError:
                issues.append(
                    ValidationIssue(
                        "bad_payload",
                        effect_id,
                        f"payload.components 键 {raw_type!r} 不是合法 ComponentTypeId",
                    )
                )
                continue
            if ctx.component_registry is not None:
                try:
                    ctx.component_registry.validate_payload(component_type, data)
                except PydanticValidationError as err:
                    issues.append(
                        ValidationIssue(
                            "bad_payload",
                            effect_id,
                            f"组件 {raw_type} 数据不符合已注册 schema：{err}",
                        )
                    )
    return tuple(issues)


def _stage_entity_existence(
    effect: ProposedEffect, ctx: ValidationContext
) -> tuple[ValidationIssue, ...]:
    """阶段 4：实体存在性（``missing_entity`` / ``missing_component``）。

    - ``EntityTarget.entity_id`` 存在（``ctx.state.has_entity``）；
      ``core.create_entity`` **豁免**（其 target 是新 ID，前置条件
      "尚不存在"归阶段 7 的 ``precondition_failed``）；
    - **批内暂存依赖豁免**（P2-REMEDIATION B1）：实体不在基线状态但属于
      ``ctx.created_in_batch``（同批次前序已被接受的
      ``core.create_entity`` 创建）→ 合法引用，不报 ``missing_entity``
      （与 L2 :func:`check_transaction_references` 的 ``created_in_batch``
      语义、reducer 暂存按 sequence 应用的顺序语义一致）；
    - ``core.remove_component`` 额外要求组件已挂载（显式拒绝空操作歧
      义，§2.1 前置条件表）。
    """
    issues: list[ValidationIssue] = []
    target = effect.target
    if not isinstance(target, EntityTarget):
        return ()
    effect_id = str(effect.effect_id)
    if not ctx.state.has_entity(target.entity_id):
        if effect.effect_type != EFFECT_CREATE_ENTITY and (
            target.entity_id not in ctx.created_in_batch
        ):
            issues.append(
                ValidationIssue(
                    "missing_entity",
                    effect_id,
                    f"target={str(target.entity_id)} 不存在于 WorldState",
                )
            )
        return tuple(issues)
    if effect.effect_type == EFFECT_REMOVE_COMPONENT and target.component_type is not None:
        if ctx.state.component_view(target.entity_id, target.component_type) is None:
            issues.append(
                ValidationIssue(
                    "missing_component",
                    effect_id,
                    f"entity={str(target.entity_id)} 未挂载组件 {str(target.component_type)}",
                )
            )
    return tuple(issues)


def _stage_field_path(
    effect: ProposedEffect, ctx: ValidationContext
) -> tuple[ValidationIssue, ...]:
    """阶段 5：field_path 合法性（``bad_field_path``，§4.6）。

    - 词法：单段标识符 ``[a-z][a-z0-9_]*``（P2 只支持单层字段名）；
    - 语义：``component_type`` 必须已注册且 ``payload_model`` 非 None
      （P1 §3.2"field_path 仅供 schema 已注册的组件使用"），且字段名 ∈
      ``payload_model.model_fields``；三条任一不满足 → 拒绝。registry
      缺席时合法性不可判定 → 保守拒绝（同 authority"域不可判定 ≠ 默认
      放行"纪律）。Kernel 结构效果不使用 field_path（整体替换）。
    """
    target = effect.target
    if not isinstance(target, EntityTarget) or target.field_path is None:
        return ()
    effect_id = str(effect.effect_id)
    field_path = target.field_path
    if not _FIELD_PATH_PATTERN.fullmatch(field_path):
        return (
            ValidationIssue(
                "bad_field_path",
                effect_id,
                f"field_path={field_path!r} 词法非法（要求单段标识符 [a-z][a-z0-9_]*）",
            ),
        )
    if target.component_type is None:
        return (
            ValidationIssue(
                "bad_field_path", effect_id, "field_path 要求 target.component_type 非 None"
            ),
        )
    schema = ctx.component_registry.get(target.component_type) if ctx.component_registry else None
    if schema is None or schema.payload_model is None:
        return (
            ValidationIssue(
                "bad_field_path",
                effect_id,
                f"组件 {str(target.component_type)} 未注册 schema 或 payload_model 为空，"
                "field_path 不可用",
            ),
        )
    if field_path not in schema.payload_model.model_fields:
        return (
            ValidationIssue(
                "bad_field_path",
                effect_id,
                f"字段 {field_path!r} 不在组件 {str(target.component_type)} "
                "的 payload_model.model_fields 中",
            ),
        )
    return ()


def _stage_staleness(effect: ProposedEffect, ctx: ValidationContext) -> tuple[ValidationIssue, ...]:
    """阶段 6：陈旧性（``stale_revision`` / ``future_base_revision``）。

    ``is_stale(effect.base_revision, ctx.state.world_revision)`` 单向语
    义（与 C7 一致：``base < current`` 陈旧，``base == current`` 新鲜）；
    ``base > current`` → ``future_base_revision``（未来版本不存在，确定
    性管道不可接受，Plan 必须测试 7.5）。
    """
    base = effect.base_revision
    current = ctx.state.world_revision
    if base > current:
        return (
            ValidationIssue(
                "future_base_revision",
                str(effect.effect_id),
                f"base={int(base)} current={int(current)}",
            ),
        )
    if is_stale(base, current):
        return (
            ValidationIssue(
                "stale_revision", str(effect.effect_id), f"base={int(base)} current={int(current)}"
            ),
        )
    return ()


def _stage_preconditions(
    effect: ProposedEffect, ctx: ValidationContext
) -> tuple[ValidationIssue, ...]:
    """阶段 7：结构前置条件 + handler 存在性（``precondition_failed`` / ``no_handler``）。

    结构效果按 §2.1 前置条件表做**数据级**预判（与 reducer 同规则，提
    前过滤）；与阶段 4 的分工见模块 docstring"阶段间分工"（entity 不
    存在 / 组件未挂载由阶段 4 专属 kind 报告，本阶段不重复）。
    ``ctx.handlers`` 非 None 且 effect_type 未注册 → ``no_handler``
    （D-P2-05：不静默推断语义；结构效果恒预注册，实际只命中语义型）。
    """
    issues: list[ValidationIssue] = []
    effect_id = str(effect.effect_id)
    effect_type = effect.effect_type
    target = effect.target

    if ctx.handlers is not None and not ctx.handlers.has(effect_type):
        issues.append(
            ValidationIssue(
                "no_handler",
                effect_id,
                f"effect_type={str(effect_type)!r} 未注册 handler（D-P2-05：不推断）",
            )
        )

    if effect_type not in STRUCTURAL_EFFECT_TYPES:
        return tuple(issues)

    if effect_type in (
        EFFECT_CREATE_ENTITY,
        EFFECT_REMOVE_ENTITY,
        EFFECT_SET_COMPONENT,
        EFFECT_REMOVE_COMPONENT,
    ):
        if not isinstance(target, EntityTarget):
            issues.append(
                ValidationIssue(
                    "precondition_failed",
                    effect_id,
                    f"{str(effect_type)} 要求 target 为 EntityTarget，"
                    f"实际为 {type(target).__name__}",
                )
            )
            return tuple(issues)
        if effect_type == EFFECT_CREATE_ENTITY and ctx.state.has_entity(target.entity_id):
            issues.append(
                ValidationIssue(
                    "precondition_failed",
                    effect_id,
                    f"core.create_entity 前置条件不满足：entity 已存在：{str(target.entity_id)}",
                )
            )
        if effect_type in (EFFECT_SET_COMPONENT, EFFECT_REMOVE_COMPONENT) and (
            target.component_type is None
        ):
            issues.append(
                ValidationIssue(
                    "precondition_failed",
                    effect_id,
                    f"{str(effect_type)} 要求 target.component_type 非 None",
                )
            )
        return tuple(issues)

    if effect_type in (
        EFFECT_SET_WORLD_VARIABLE,
        EFFECT_REMOVE_WORLD_VARIABLE,
        EFFECT_SET_SCENARIO_DATA,
    ):
        expected_domain = (
            "scenario" if effect_type == EFFECT_SET_SCENARIO_DATA else "world_variables"
        )
        if not isinstance(target, StateDomainTarget):
            issues.append(
                ValidationIssue(
                    "precondition_failed",
                    effect_id,
                    f"{str(effect_type)} 要求 target 为 StateDomainTarget，"
                    f"实际为 {type(target).__name__}",
                )
            )
            return tuple(issues)
        if str(target.domain) != expected_domain:
            issues.append(
                ValidationIssue(
                    "precondition_failed",
                    effect_id,
                    f"{str(effect_type)} 要求 target.domain == {expected_domain!r}，"
                    f"实际为 {str(target.domain)!r}",
                )
            )
            return tuple(issues)
        if effect_type == EFFECT_REMOVE_WORLD_VARIABLE:
            try:
                payload = RemoveWorldVariablePayload.model_validate(effect.payload)
            except PydanticValidationError:
                return tuple(issues)  # payload 缺键已由阶段 3 报告 bad_payload
            if payload.key not in ctx.state.world_variables:
                issues.append(
                    ValidationIssue(
                        "precondition_failed",
                        effect_id,
                        f"core.remove_world_variable 前置条件不满足：键 {payload.key!r} "
                        "不存在于 world_variables",
                    )
                )
    return tuple(issues)


# —— L1 固定阶段管道（§4.3）——


class EffectValidator:
    """Effect Validation 固定阶段管道（P2 设计规范 §4.3；D-P2-10 第一层）。

    阶段按固定顺序执行，前序阶段**不短路**后续——一次性收齐全部问题
    （trace 可解释性最大化）：

    | # | 阶段 | issue kind |
    |---|---|---|
    | 1 | ID 种类与前缀（§4.4，:func:`check_effect_id_kinds` 同源） | ``bad_id_kind`` |
    | 2 | 类型标识符词法 | ``bad_type_id`` |
    | 3 | domain 词表与 payload schema | ``unknown_domain`` / ``bad_payload`` |
    | 4 | 实体存在性（``core.create_entity`` 与批内创建豁免） | ``missing_entity`` / ``missing_component`` |
    | 5 | field_path 合法性（§4.6） | ``bad_field_path`` |
    | 6 | 陈旧性（单向 stale + 未来版本拒绝） | ``stale_revision`` / ``future_base_revision`` |
    | 7 | 结构前置条件 + handler 存在性 | ``precondition_failed`` / ``no_handler`` |

    批级 :meth:`validate_batch` 追加 ``duplicated_effect_id`` 检查（同批
    同 ID 的全部副本被拒——KBC-2 防线；与 Transaction 构造期不变量互为
    纵深防御）。
    """

    def __init__(self) -> None:
        """固定管道，无配置（确定性；扩展走 P5+ Gate）。"""

    def validate(
        self, effect: ProposedEffect, ctx: ValidationContext
    ) -> tuple[ValidationIssue, ...]:
        """单 effect 七阶段校验；空元组 = 通过（D-P2-10：调用方据此过滤）。"""
        issues: list[ValidationIssue] = [
            ValidationIssue(
                "bad_id_kind",
                str(effect.effect_id),
                f"{field}:expected={expected} got={got}:value={value}",
            )
            for field, expected, got, value in _id_kind_violations(effect)
        ]
        issues.extend(_stage_type_lexical(effect))
        issues.extend(_stage_domain_payload(effect, ctx))
        issues.extend(_stage_entity_existence(effect, ctx))
        issues.extend(_stage_field_path(effect, ctx))
        issues.extend(_stage_staleness(effect, ctx))
        issues.extend(_stage_preconditions(effect, ctx))
        return tuple(issues)

    def validate_batch(
        self, effects: Sequence[ProposedEffect], ctx: ValidationContext
    ) -> ValidationReport:
        """批级校验：逐 effect :meth:`validate` + 批级重复 ID 检查（§4.3 末段）。

        同批同 ``effect_id`` 的**全部副本**被拒（KBC-2 防线；计数对全批
        生效，含已被其他阶段拒绝的副本）；问题串与 C7 检查器同构
        （``duplicated_effect_id:<id>:count=<k>``）。

        **批内暂存依赖**（P2-REMEDIATION B1）：按到达序累积"已被接受的
        ``core.create_entity`` 创建的实体 ID 集合"（``created_in_batch``），
        经 ``dataclasses.replace`` 派生逐 effect 上下文——后续效果引用
        批内创建的实体不报 ``missing_entity``（顺序敏感：引用先于创建
        到达时创建尚未登记，仍报缺失；被拒的创建不登记）。
        """
        accepted: list[ProposedEffect] = []
        issues: list[ValidationIssue] = []
        created_in_batch: set[EntityId] = set()
        for effect in effects:
            effect_ctx = ctx
            if created_in_batch:
                effect_ctx = replace(ctx, created_in_batch=frozenset(created_in_batch))
            effect_issues = self.validate(effect, effect_ctx)
            if effect_issues:
                issues.extend(effect_issues)
            else:
                accepted.append(effect)
                target = effect.target
                if (
                    effect.effect_type == EFFECT_CREATE_ENTITY
                    and isinstance(target, EntityTarget)
                ):
                    created_in_batch.add(target.entity_id)
        counts: dict[str, int] = {}
        first_seen: dict[str, int] = {}
        for index, effect in enumerate(effects):
            effect_id = str(effect.effect_id)
            counts[effect_id] = counts.get(effect_id, 0) + 1
            first_seen.setdefault(effect_id, index)
        rejected_ids = [effect_id for effect_id, count in counts.items() if count > 1]
        if rejected_ids:
            rejected_set = set(rejected_ids)
            accepted = [effect for effect in accepted if str(effect.effect_id) not in rejected_set]
            for effect_id in sorted(rejected_ids, key=first_seen.get):
                issues.append(
                    ValidationIssue(
                        "duplicated_effect_id", effect_id, f"count={counts[effect_id]}"
                    )
                )
        return ValidationReport(accepted=tuple(accepted), issues=tuple(issues))


class ValidationPipeline(EffectValidator):
    """ValidationPipeline 组合类（P2-T04 任务包表面）。

    组合 = :class:`EffectValidator` 七阶段固定管道（L1 过滤语义，
    D-P2-10）+ **严格模式入口** :meth:`run`：批内任何问题 → 抛
    :class:`ValidationError`（all-or-nothing 处置，交由调用方决定拒绝
    语义）；零问题 → 返回 accepted 元组。管道 L1 本体保持**不抛异常**
    的过滤语义（cascade run_round 步骤 3 依赖之），严格模式仅供管道外
    的 fail-fast 装配场景。
    """

    def run(
        self, effects: Sequence[ProposedEffect], ctx: ValidationContext
    ) -> tuple[ProposedEffect, ...]:
        """严格批校验：有 issue → :class:`ValidationError`；零 issue → accepted。"""
        report = self.validate_batch(effects, ctx)
        if report.issues:
            raise ValidationError(report.issues)
        return report.accepted


# —— L1 单效果基础校验器（P2-T04 任务包表面）——


def validate_proposed_effect(
    effect: ProposedEffect,
    state: WorldState,
    component_registry: ComponentRegistry | None = None,
    *,
    handlers: EffectHandlerRegistry | None = None,
) -> tuple[bool, str | None]:
    """L1 单效果基础校验器（P2-T04 任务包口径）。

    对单个 :class:`ProposedEffect` 运行 :class:`EffectValidator` 全量
    七阶段管道（跨种类 ID 词法与前缀严格校验 / 实体存在性
    （``core.create_entity`` 豁免）/ 组件 Schema·Registry 校验 /
    base_revision stale 判定（``is_stale``）+ 未来版本拒绝 / domain
    词表 / field_path / 结构前置条件 / handler 存在性）。

    Args:
        effect: 待校验提案。
        state: 校验对照的权威世界状态。
        component_registry: 组件 schema 注册表；None → 跳过 registry
            schema 校验（field_path 语义检查保守拒绝）。
        handlers: handler 注册表；None → 跳过 no_handler 阶段。

    Returns:
        ``(True, None)`` 通过；失败 ``（False, reason）``——reason 为全部
        问题 ``to_trace_str`` 的分号串接（C7 报告串同构），永不抛异常。
    """
    ctx = ValidationContext(
        state=state, component_registry=component_registry, handlers=handlers
    )
    issues = EffectValidator().validate(effect, ctx)
    if not issues:
        return True, None
    return False, "; ".join(issue.to_trace_str() for issue in issues)


# —— L2 事务终检（C2 晋升；§4.5）——


def check_transaction_references(state: WorldState, txn: Transaction) -> tuple[str, ...]:
    """事务终检数据级引用检查器（P1 设计 §7.4 C7；由 P2-T04 按 C2 晋升）。

    空元组 = 无数据级问题。**拒绝行为属管道层**（D-P2-10：L2 失败 →
    整事务原子失败，``transaction_executor.commit_transaction`` 装配后
    调用本函数，P2 设计规范 §6.2 步骤 6），本函数只报告，不修改
    ``state`` / ``txn``，不抛异常。

    检查项与问题串格式（``kind:effect_id:详情``）：

    - ``missing_entity:<effect_id>:target=<entity_id>``——entity 分支
      target 指向 state 中不存在的 entity；
    - ``stale_revision:<effect_id>:base=<n> current=<m>``——
      ``is_stale(base_revision, state.world_revision)`` 成立（单向语
      义——``base > current`` 不报）；
    - ``duplicated_effect_id:<effect_id>:count=<k>``——事务内同一
      effect_id 出现 k 次（KBC-2 防线，构造期之外的数据级复检）。

    **``core.create_entity`` 与批内暂存依赖**（P2-REMEDIATION B1 修复）：

    - 效果为 ``core.create_entity`` 时，其目标实体按定义在基线状态中
      **尚不存在**——不报 ``missing_entity``（目标已存在时由 reducer
      结构前置条件报错"entity 已存在"，亦非 missing_entity 语义）；
      同时将该 ``entity_id`` 登记入本批次已创建实体集合
      ``created_in_batch``；
    - 检查按 ``sequence`` 序（与 reducer 暂存应用序一致）进行：同批次
      **后续**效果引用的实体若不在基线状态但属于
      ``created_in_batch``，视为合法暂存依赖引用，不报
      ``missing_entity``（先 ``core.create_entity`` 后
      ``core.set_component`` 的初始化挂载即此形态）。

    不检查（明确边界）：state_domain 分支的 domain 词表（P2 authority
    配置声明，L1 阶段 3 判定）；``event_ids`` / ``cascade`` 引用。
    """
    issues: list[str] = []
    seen: dict[str, int] = {}
    # 本批次已创建实体集合（P2-REMEDIATION B1）：按 sequence 序登记，
    # 后续效果引用批内创建的实体为合法暂存依赖
    created_in_batch: set[EntityId] = set()
    ordered = sorted(txn.effects, key=lambda committed: committed.sequence)
    for committed in ordered:
        effect = committed.effect
        effect_id = str(effect.effect_id)
        target = effect.target
        if isinstance(target, EntityTarget):
            if effect.effect_type == EFFECT_CREATE_ENTITY:
                # 创建效果的目标实体在基线中不应存在：尚不存在 → 登记
                # created_in_batch；已存在 → 由 reducer 前置条件报错，
                # 不报 missing_entity
                if not state.has_entity(target.entity_id):
                    created_in_batch.add(target.entity_id)
            elif (
                not state.has_entity(target.entity_id)
                and target.entity_id not in created_in_batch
            ):
                issues.append(f"missing_entity:{effect_id}:target={str(target.entity_id)}")
        if is_stale(effect.base_revision, state.world_revision):
            issues.append(
                f"stale_revision:{effect_id}:base={int(effect.base_revision)}"
                f" current={int(state.world_revision)}"
            )
        seen[effect_id] = seen.get(effect_id, 0) + 1
    for effect_id, count in seen.items():
        if count > 1:
            issues.append(f"duplicated_effect_id:{effect_id}:count={count}")
    return tuple(issues)
