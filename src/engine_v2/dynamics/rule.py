"""P7-W2 声明式规则 backend（SOT §3.3，T02；3 exports，账本序 §8.2 钉死）。

``WorldRule`` 是**纯数据、零代码**规则（K8：规则永不是项目内 ``.py`` lambda）：
``when`` = 恰一个条件算子（``RULE_CONDITION_OPERATORS`` 3 元闭集）+ 逐算子
参数闭形状；``emit_*`` = 命中时产出**恰 1 个** ``ProposedEffect`` 的声明。
``RuleDynamics`` 按 ``rules`` 元组序逐条求值（**声明序 = 确定性序**，K7）：
命中 → 产 effect；未命中 → 跳过；**无内部状态（纯函数于 snapshot）**。

纪律（SOT §0.5/§3.0）：

- JSON-clean 铁律（P7-INV-4）：``WorldRule.when`` / ``emit_payload`` 模板构造期
  过 ``assert_json_clean`` 机械断言；模板标量值可含
  ``@field:<component>.<field>`` 引用，求值期从目标实体组件取 **JSON 标量**
  （组件/字段缺失、值非 JSON 标量 → :class:`DynamicsError`）；求值后 payload
  亦 JSON-clean（机械断言复核）；
- 二分纪律（镜像 P5/P6）：构造期违规（rule_id / emit_effect_type 词法、
  条件算子闭集、when 参数形状、字段配对）走 :class:`DynamicsError`；
  simulate 期契约违规（目标实体缺失、@field 引用解析失败）同样走异常——
  规则 backend 无非致命运行面，last-run 诊断通道（D-P7-15）恒空；
- K2/K5：零 WorldState 直写——世界写入唯一形式 = ``simulate`` 返回
  ``ProposedEffect``（payload 必填）；P7 零 conflict 逻辑；
- K7：零 random、零墙钟、零模块级可变状态；effect ID =
  ``new_deterministic_effect_id("rule", rule.rule_id, base_revision, index)``
  确定性工厂（零 uuid4）；
- ``emit_effect_type`` 词法直接消费 core ``EFFECT_TYPE_ID_PATTERN``
  （core/effects.py L67 @ e816a64；SOT §2.1 表已补列，ERR-P7-05）：
  EffectTypeId 小写点分名（SOT §3.3 L426）。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.effects import (
    EFFECT_TYPE_ID_PATTERN,
    EntityTarget,
    ProposedEffect,
)
from src.engine_v2.core.ids import PRODUCER_ID_PATTERN
from src.engine_v2.core.serialization import assert_json_clean
from src.engine_v2.core.state import WorldState
from src.engine_v2.dynamics.backend import (
    BackendMetadata,
    DynamicsContext,
    DynamicsError,
    FIDELITY_PATTERN,
    Stimulus,
    WorldSnapshot,
    new_deterministic_effect_id,
)
from src.engine_v2.dynamics.diagnostic import DynamicsDiagnostic

__all__ = ["WorldRule", "RuleDynamics", "RULE_CONDITION_OPERATORS"]

#: 条件算子闭集（SOT §3.3 逐字钉死）：``when`` 的键必须恰一个且属于本闭集。
RULE_CONDITION_OPERATORS: Final = (
    "world_variable_equals",
    "component_field_equals",
    "entity_exists",
)

#: ``@field:`` 引用前缀（SOT §3.3：``@field:<component>.<field>``）。
_FIELD_REF_PREFIX: Final[str] = "@field:"

#: ``when`` 逐算子参数闭形状（SOT §3.3 表行；构造期精确集校验，
#: 多余/缺失参数 → :class:`DynamicsError`）。
_WHEN_PARAM_KEYS: Final = {
    "world_variable_equals": frozenset({"key", "value"}),
    "component_field_equals": frozenset({"entity", "component", "field", "value"}),
    "entity_exists": frozenset({"entity"}),
}

#: ``when`` 参数中的 str 型参数名（JSON 值 ``value`` 不受 str 约束）。
_WHEN_STR_KEYS: Final = frozenset({"key", "entity", "component", "field"})


@dataclass(frozen=True)
class WorldRule:
    """声明式世界规则（SOT §3.3 字段表逐字；纯数据、零代码——K8）。

    - ``rule_id`` 名字型（FIDELITY_PATTERN 词法，复用 SOT §3.1 常量）；
    - ``when`` **恰一个**键 ∈ ``RULE_CONDITION_OPERATORS``：
      ``world_variable_equals`` = {key, value}；
      ``component_field_equals`` = {entity, component, field, value}；
      ``entity_exists`` = {entity}（参数闭形状逐字，多余/缺失 → 构造期
      :class:`DynamicsError`）；
    - ``emit_effect_type`` EffectTypeId 词法（小写点分名）；
    - ``emit_target_entity`` 目标实体（必须存在于快照，否则 simulate 期
      :class:`DynamicsError`）；
    - ``emit_component_type`` / ``emit_field_path`` EntityTarget 组件 /
      字段路径（None = 整实体目标；字段路径必须配组件，SOT §3.3 L429）；
    - ``emit_payload`` JSON-clean 模板（构造期机械断言）；标量值可含
      ``@field:<component>.<field>`` 引用（求值期从目标实体组件取 JSON 标量）；
    - ``cause_ids`` 默认 ()（可链式指上游）。
    """

    rule_id: str
    when: Mapping[str, object]
    emit_effect_type: str
    emit_target_entity: str
    emit_component_type: str | None
    emit_field_path: str | None
    emit_payload: Mapping[str, object]
    cause_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, str) or re.fullmatch(FIDELITY_PATTERN, self.rule_id) is None:
            raise DynamicsError(f"WorldRule.rule_id 词法非法（名字型点分）：{self.rule_id!r}")
        self._validate_when()
        if (
            not isinstance(self.emit_effect_type, str)
            or EFFECT_TYPE_ID_PATTERN.fullmatch(self.emit_effect_type) is None
        ):
            raise DynamicsError(
                f"WorldRule.emit_effect_type 词法非法（EffectTypeId 小写点分名）："
                f"{self.emit_effect_type!r}"
            )
        if not isinstance(self.emit_target_entity, str) or not self.emit_target_entity:
            raise DynamicsError(
                f"WorldRule.emit_target_entity 必须为非空 str：{self.emit_target_entity!r}"
            )
        if self.emit_component_type is not None and not isinstance(self.emit_component_type, str):
            raise DynamicsError(
                f"WorldRule.emit_component_type 必须为 str 或 None：{self.emit_component_type!r}"
            )
        if self.emit_field_path is not None:
            if not isinstance(self.emit_field_path, str) or not self.emit_field_path:
                raise DynamicsError(
                    f"WorldRule.emit_field_path 必须为非空 str 或 None：{self.emit_field_path!r}"
                )
            if self.emit_component_type is None:
                raise DynamicsError(
                    "WorldRule.emit_field_path 必须配 emit_component_type"
                    "（SOT §3.3：字段路径配组件）"
                )
        if not isinstance(self.cause_ids, tuple) or any(
            not isinstance(cause, str) for cause in self.cause_ids
        ):
            raise DynamicsError(f"WorldRule.cause_ids 必须为 tuple[str, ...]：{self.cause_ids!r}")
        try:
            assert_json_clean(self.when)
            assert_json_clean(self.emit_payload)
        except AssertionError as exc:
            raise DynamicsError(f"WorldRule 数据面（when/emit_payload）非 JSON-clean：{exc}") from exc

    def _validate_when(self) -> None:
        """``when`` 构造期校验：恰一个键 ∈ 闭集 + 逐算子参数闭形状（SOT §3.3）。"""
        if not isinstance(self.when, Mapping) or len(self.when) != 1:
            raise DynamicsError(
                f"WorldRule.when 必须恰一个键（∈ RULE_CONDITION_OPERATORS）：{self.when!r}"
            )
        (operator, params) = next(iter(self.when.items()))
        if operator not in RULE_CONDITION_OPERATORS:
            raise DynamicsError(
                f"WorldRule.when 算子必须属于 RULE_CONDITION_OPERATORS 闭集，得到 {operator!r}"
            )
        if not isinstance(params, Mapping):
            raise DynamicsError(f"WorldRule.when[{operator!r}] 参数必须为 Mapping：{params!r}")
        expected = _WHEN_PARAM_KEYS[operator]
        if set(params) != expected:
            raise DynamicsError(
                f"WorldRule.when[{operator!r}] 参数闭形状必须为 {sorted(expected)}，"
                f"得到 {sorted(params)}"
            )
        for name in sorted(expected & _WHEN_STR_KEYS):
            value = params[name]
            if not isinstance(value, str) or not value:
                raise DynamicsError(
                    f"WorldRule.when[{operator!r}].{name} 必须为非空 str：{value!r}"
                )


def _json_equal(left: object, right: object) -> bool:
    """JSON 值相等：bool 与数值严格区分（规避 Python ``True == 1`` 陷阱）。

    非 bool 面直接 ``==``（数值跨 int/float 按值相等，与 JSON 数值语义一致）。
    """
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    return left == right


def _is_json_scalar(value: object) -> bool:
    """JSON 标量 = None / str / int / bool / float（list / dict 不计）。"""
    return value is None or isinstance(value, (str, int, bool, float))


def _condition_matches(when: Mapping[str, object], world_state: WorldState) -> bool:
    """``when`` 条件求值（纯读、零写；缺失 = 未命中而非错误，SOT §3.3）。

    - ``world_variable_equals``：变量键存在且值 JSON 相等（键缺失 = 未命中）；
    - ``component_field_equals``：实体 / 组件 / 字段任一缺失 = 未命中；
    - ``entity_exists``：实体在快照 entities 中。
    """
    (operator, params) = next(iter(when.items()))
    if operator == "world_variable_equals":
        key = str(params["key"])
        variables = world_state.world_variables
        return key in variables and _json_equal(variables[key], params["value"])
    if operator == "component_field_equals":
        record = world_state.entities.get(str(params["entity"]))
        if record is None:
            return False
        component = record.components.get(str(params["component"]))
        if component is None:
            return False
        field = str(params["field"])
        return field in component and _json_equal(component[field], params["value"])
    if operator == "entity_exists":
        return world_state.entities.get(str(params["entity"])) is not None
    return False


def _resolve_field_ref(ref: str, rule: WorldRule, record: EntityRecord) -> object:
    """求值 ``@field:<component>.<field>`` → JSON 标量（SOT §3.3 L430）。

    首个点切分：前 = 组件类型，后 = 字段名（组件 dict 平面查，不嵌套）；
    引用形状非法 / 组件缺失 / 字段缺失 / 值非 JSON 标量 →
    :class:`DynamicsError`（simulate 期契约违规）。
    """
    body = ref[len(_FIELD_REF_PREFIX):]
    component_name, dot, field = body.partition(".")
    if not dot or not component_name or not field:
        raise DynamicsError(f"rule {rule.rule_id!r} @field 引用形状非法：{ref!r}")
    component = record.components.get(component_name)
    if component is None:
        raise DynamicsError(
            f"rule {rule.rule_id!r} @field 引用组件缺失："
            f"entity={rule.emit_target_entity!r} component={component_name!r}"
        )
    if field not in component:
        raise DynamicsError(
            f"rule {rule.rule_id!r} @field 引用字段缺失："
            f"entity={rule.emit_target_entity!r} component={component_name!r} field={field!r}"
        )
    value = component[field]
    if not _is_json_scalar(value):
        raise DynamicsError(
            f"rule {rule.rule_id!r} @field 引用必须解析为 JSON 标量："
            f"entity={rule.emit_target_entity!r} component={component_name!r} field={field!r}"
        )
    return value


def _evaluate_payload(rule: WorldRule, record: EntityRecord) -> dict[str, object]:
    """payload 模板求值：``@field`` 引用 → JSON 标量，其余值原样透传。

    求值结果 JSON-clean（模板构造期已 JSON-clean + 引用值受 JSON 标量约束，
    此处机械断言复核，K1 铁律同源）。
    """
    evaluated: dict[str, object] = {}
    for key, value in rule.emit_payload.items():
        if isinstance(value, str) and value.startswith(_FIELD_REF_PREFIX):
            evaluated[key] = _resolve_field_ref(value, rule, record)
        else:
            evaluated[key] = value
    assert_json_clean(evaluated)
    return evaluated


class RuleDynamics:
    """声明式规则 backend（SOT §3.3；``WorldDynamicsBackend`` 结构化满足）。

    构造仅存 ``rules`` 元组（声明序 = 求值序）+ ``producer_id``（D-P7-08
    词表成员，缺省 ``rule_dynamics``；词法 fullmatch ``PRODUCER_ID_PATTERN``）
    + 空 last-run 诊断通道（D-P7-15；规则 backend 违规全走异常路径 → 恒空）。
    无内部状态（纯函数于 snapshot）：双跑同输入 → 输出 byte-identical（K7/A15）。
    """

    __slots__ = ("_rules", "_producer_id", "_diagnostics")

    def __init__(self, *, rules: tuple[WorldRule, ...], producer_id: str = "rule_dynamics") -> None:
        if not isinstance(rules, tuple) or any(not isinstance(rule, WorldRule) for rule in rules):
            raise DynamicsError(f"RuleDynamics.rules 必须为 tuple[WorldRule, ...]：{rules!r}")
        if not isinstance(producer_id, str) or PRODUCER_ID_PATTERN.fullmatch(producer_id) is None:
            raise DynamicsError(f"RuleDynamics.producer_id 词法非法：{producer_id!r}")
        self._rules = rules
        self._producer_id = producer_id
        # last-run 诊断通道（D-P7-15）：simulate 入口重置；规则 backend 恒空
        self._diagnostics: list[DynamicsDiagnostic] = []

    # —— WorldDynamicsBackend 协议（同步，D-P7-01）——

    def metadata(self) -> BackendMetadata:
        """自描述元数据（SOT §3.3 钉死值；domains = 各规则触碰的组件/域）。

        ``producer_id`` 缺省构造下逐字 = ``rule_dynamics``；host 以
        ``producer_id`` 参数覆写时自描述随实例（与 ``simulate`` 产 effect 的
        ``source`` 同源，D-P7-08）。
        """
        return BackendMetadata(
            backend_id="rule_dynamics",
            producer_id=self._producer_id,
            domains=self._touched_domains(),
            determinism="deterministic",
            implementation_type="rule",
            fidelity="abstract",
            checkpointable=True,
            restorable=True,
            replayable=True,
        )

    def simulate(
        self,
        snapshot: WorldSnapshot,
        stimuli: tuple[Stimulus, ...],
        context: DynamicsContext,
    ) -> tuple[ProposedEffect, ...]:
        """按 ``rules`` 元组序逐条求值（声明序 = 确定性序，K7）。

        - 未命中 → 跳过（条件为纯匹配守卫：实体/组件/字段缺失 = 未命中）；
        - 命中 → 产恰 1 个 ``ProposedEffect``：
          ``effect_id = new_deterministic_effect_id("rule", rule.rule_id,
          context.base_revision, index)``（index = 声明位）；
          ``source = producer_id``；``target = EntityTarget(entity,
          component_type, field_path)``；``payload`` = 模板 ``@field`` 求值
          结果；``base_revision = context.base_revision``；``cause_ids`` 透传；
        - 目标实体不在快照 → :class:`DynamicsError`（SOT §3.3：必须存在）；
        - ``stimuli`` 为协议统一面（host 恒传），规则 backend 不消费。
        """
        self._diagnostics = []
        world_state = snapshot.world_state
        effects: list[ProposedEffect] = []
        for index, rule in enumerate(self._rules):
            if not _condition_matches(rule.when, world_state):
                continue
            record = world_state.entities.get(rule.emit_target_entity)
            if record is None:
                raise DynamicsError(
                    f"rule {rule.rule_id!r} 目标实体不在快照："
                    f"{rule.emit_target_entity!r}"
                )
            effects.append(
                ProposedEffect(
                    effect_id=new_deterministic_effect_id(
                        "rule", rule.rule_id, context.base_revision, index
                    ),
                    effect_type=rule.emit_effect_type,
                    source=self._producer_id,
                    target=EntityTarget(
                        entity_id=rule.emit_target_entity,
                        component_type=rule.emit_component_type,
                        field_path=rule.emit_field_path,
                    ),
                    payload=_evaluate_payload(rule, record),
                    base_revision=context.base_revision,
                    cause_ids=list(rule.cause_ids),
                )
            )
        return tuple(effects)

    @property
    def diagnostics(self) -> tuple[DynamicsDiagnostic, ...]:
        """last-run 诊断视图（D-P7-15：simulate 入口重置；规则 backend 恒空）。"""
        return tuple(self._diagnostics)

    # —— 私有面 ——

    def _touched_domains(self) -> tuple[str, ...]:
        """各规则触碰的组件/域（SOT §3.3：排序去重）。

        触面口径：``component_field_equals`` 条件的 component、
        ``world_variable_equals`` 条件的 ``world_variables`` 域、
        ``emit_component_type``、payload 模板 ``@field`` 引用的组件部分
        （读/写皆计触碰）；``entity_exists`` 不触碰组件/域。
        """
        domains: set[str] = set()
        for rule in self._rules:
            (operator, params) = next(iter(rule.when.items()))
            if operator == "component_field_equals":
                domains.add(str(params["component"]))
            elif operator == "world_variable_equals":
                domains.add("world_variables")
            if rule.emit_component_type is not None:
                domains.add(rule.emit_component_type)
            for value in rule.emit_payload.values():
                if isinstance(value, str) and value.startswith(_FIELD_REF_PREFIX):
                    component = value[len(_FIELD_REF_PREFIX):].partition(".")[0]
                    if component:
                        domains.add(component)
        return tuple(sorted(domains))
