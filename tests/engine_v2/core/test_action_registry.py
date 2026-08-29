"""P3-T02 收尾验收：action_registry（P3 设计规范 §3.5 全量行为）。

依据 ``docs/v2/contracts/P3-scheduler-time-action-design.md``（下称"P3
设计规范"）§3.5 代码块契约与 §6.1 单测要点：

- 构造期词表/必填不变量（K7 可检查不静默）：``ParameterSpec.type`` ∈
  ``PARAMETER_TYPES``；``DurationPolicy.kind`` ∈ fixed/hint/none；
  ``fixed`` ⇒ ``duration_ticks >= 1`` 必填；``hint`` ⇒ ``hint_scale`` 必填
  （``gt=0.0`` 字段约束）；
- ``ActionRegistry.specs`` 键一致性（``spec.action_id != key`` → 构造期
  拒绝，P1 RuntimeState 键一致性同款纪律）；
- ``lookup``：已注册 → spec；未注册 → ``None``；
- ``validate_arguments`` 矩阵（§6.1）：缺必填 / 未知键 / ``entity`` 型给
  字符串 / ``number`` 越界 min/max / ``enum_values`` 不匹配 → 各自 issue
  串；未注册 ``action_id`` → ``UnknownActionError``（D-P3-16；基类
  ``SchedulerError`` 宿主于 ``clock.py``，D-P3-12/D-P3-16）；
- ``resolve_duration``（§6.1）：fixed 直出 / hint 缺失 → None /
  ``hint_scale×30`` 取整 / 结果 0.2 → 钳 1（D-P3-01 子 tick 规则，D3 披露，
  §8.5）/ none → None；
- ``validate_timing``（§6.1）：deadline < earliest → issue；hint 0 → issue；
- ``ActionRegistry`` round-trip 恒等（dump_json/assert_json_clean/load_json；
  键与嵌套 typed 类型保持）。

布局（P2 勘误 E4 沿袭）：位于 ``tests/engine_v2/core/``；直接从子模块
import，不经包级导出；全部用例无网络、无 LLM、无 API key。
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from src.engine_v2.core.action_registry import (
    PARAMETER_TYPES,
    ActionRegistry,
    ActionSpec,
    DurationPolicy,
    ParameterSpec,
    UnknownActionError,
    validate_timing,
)
from src.engine_v2.core.actions import ActionTiming, ActionTypeId
from src.engine_v2.core.clock import SchedulerError
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.serialization import assert_json_clean, dump_json, load_json

# —— 样本工厂（自包含、确定性构造）——


def _travel_spec(**overrides: Any) -> ActionSpec:
    data: dict[str, Any] = {
        "action_id": "travel",
        "executor": "npc.brain",
        "parameters": {
            "dest": {"type": "entity", "required": True},
            "speed": {
                "type": "number",
                "required": False,
                "min_value": 0.5,
                "max_value": 10.0,
            },
            "mode": {
                "type": "string",
                "required": False,
                "enum_values": ["walk", "sneak", "dash"],
            },
            "level": {
                "type": "number",
                "required": False,
                "enum_values": [1, 2, 3],
            },
            "carried": {"type": "boolean", "required": False},
        },
        "duration_policy": {"kind": "fixed", "duration_ticks": 30},
        "interruptible": True,
        "completion_trigger": "travel_arrival",
        "tags": ["movement", "player"],
    }
    data.update(overrides)
    return ActionSpec.model_validate(data)


def _rest_spec() -> ActionSpec:
    return ActionSpec(
        action_id=ActionTypeId("rest"),
        executor="npc.brain",
        parameters={"quality": {"type": "number", "required": True, "min_value": 1.0}},
        duration_policy=DurationPolicy(kind="hint", hint_scale=0.5, description="按提示折算"),
        interruptible=False,
        tags=["recovery"],
    )


def _registry() -> ActionRegistry:
    return ActionRegistry(
        specs={
            "travel": _travel_spec(),
            "rest": _rest_spec(),
            "idle": ActionSpec(action_id="idle", executor="npc.brain"),
        }
    )


# —— PARAMETER_TYPES 词表 ——


class TestParameterTypesVocabulary:
    def test_vocabulary_content(self) -> None:
        assert PARAMETER_TYPES == frozenset({"entity", "number", "string", "boolean"})

    @pytest.mark.parametrize("type_name", sorted(PARAMETER_TYPES))
    def test_each_valid_type_accepted(self, type_name: str) -> None:
        spec = ParameterSpec(type=type_name)
        assert spec.type == type_name

    @pytest.mark.parametrize("type_name", ["dict", "list", "id", "", "ENTITY"])
    def test_invalid_type_rejected_at_construction(self, type_name: str) -> None:
        with pytest.raises(ValidationError):
            ParameterSpec(type=type_name)


# —— ParameterSpec 契约 ——


class TestParameterSpecContract:
    def test_defaults(self) -> None:
        spec = ParameterSpec(type="string")
        assert spec.required is True
        assert spec.enum_values is None
        assert spec.min_value is None
        assert spec.max_value is None
        assert spec.description is None

    def test_full_fields(self) -> None:
        spec = ParameterSpec(
            type="number",
            required=False,
            enum_values=[1, 2, 3],
            min_value=0.0,
            max_value=100.0,
            description="体力（0..100）",
        )
        assert spec.required is False
        assert spec.enum_values == [1, 2, 3]
        assert spec.min_value == 0.0
        assert spec.max_value == 100.0
        assert spec.description == "体力（0..100）"


# —— DurationPolicy 契约 ——


class TestDurationPolicyContract:
    def test_none_kind_defaults(self) -> None:
        policy = DurationPolicy(kind="none")
        assert policy.duration_ticks is None
        assert policy.hint_scale is None
        assert policy.description is None

    def test_kind_vocabulary_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DurationPolicy(kind="auto")

    def test_fixed_requires_duration(self) -> None:
        with pytest.raises(ValidationError):
            DurationPolicy(kind="fixed")

    @pytest.mark.parametrize("ticks", [0, -1])
    def test_fixed_rejects_below_one(self, ticks: int) -> None:
        with pytest.raises(ValidationError):
            DurationPolicy(kind="fixed", duration_ticks=ticks)

    @pytest.mark.parametrize("ticks", [1, 30])
    def test_fixed_accepts_one_and_up(self, ticks: int) -> None:
        assert DurationPolicy(kind="fixed", duration_ticks=ticks).duration_ticks == ticks

    def test_hint_requires_scale(self) -> None:
        with pytest.raises(ValidationError):
            DurationPolicy(kind="hint")

    @pytest.mark.parametrize("scale", [0.0, -0.5])
    def test_hint_rejects_nonpositive_scale(self, scale: float) -> None:
        with pytest.raises(ValidationError):
            DurationPolicy(kind="hint", hint_scale=scale)

    def test_hint_accepts_positive_scale(self) -> None:
        policy = DurationPolicy(kind="hint", hint_scale=0.5)
        assert policy.hint_scale == 0.5


# —— ActionSpec 契约 ——


class TestActionSpecContract:
    def test_defaults(self) -> None:
        spec = ActionSpec(action_id="travel", executor="npc.brain")
        assert spec.parameters == {}
        assert spec.duration_policy == DurationPolicy(kind="none")
        assert spec.interruptible is True
        assert spec.completion_trigger is None
        assert spec.tags == []

    def test_action_id_type_preserved(self) -> None:
        spec = ActionSpec(action_id="interaction.knock", executor="npc.brain")
        assert type(spec.action_id) is ActionTypeId
        assert spec.action_id == "interaction.knock"

    def test_model_validate_from_plain_dict(self) -> None:
        spec = ActionSpec.model_validate({"action_id": "travel", "executor": "npc.brain"})
        assert type(spec.action_id) is ActionTypeId
        assert spec.executor == "npc.brain"


# —— ActionRegistry 键一致性（构造期拒绝）——


class TestRegistryKeyConsistency:
    def test_matching_keys_accepted(self) -> None:
        registry = _registry()
        assert set(registry.specs) == {"travel", "rest", "idle"}
        for key, spec in registry.specs.items():
            assert spec.action_id == key

    def test_mismatched_key_rejected_at_construction(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ActionRegistry(
                specs={"travel": ActionSpec(action_id="walk", executor="npc.brain")}
            )
        message = str(exc_info.value)
        assert "travel" in message
        assert "walk" in message

    def test_empty_registry_ok(self) -> None:
        assert ActionRegistry().specs == {}


# —— lookup ——


class TestLookup:
    def test_registered_returns_spec(self) -> None:
        registry = _registry()
        spec = registry.lookup(ActionTypeId("travel"))
        assert spec is not None
        assert spec.action_id == "travel"
        assert spec.completion_trigger == "travel_arrival"

    def test_unregistered_returns_none(self) -> None:
        assert _registry().lookup(ActionTypeId("nope")) is None


# —— validate_arguments（§6.1 矩阵）——


class TestValidateArguments:
    def test_unregistered_action_id_raises_unknown(self) -> None:
        registry = _registry()
        with pytest.raises(UnknownActionError) as exc_info:
            registry.validate_arguments(ActionTypeId("nope"), {})
        # D-P3-16：异常族归 SchedulerError 基类（可捕获、可分类）
        assert isinstance(exc_info.value, SchedulerError)
        assert isinstance(exc_info.value, ValueError)
        assert "nope" in str(exc_info.value)

    def test_unregistered_is_subclass_of_scheduler_error(self) -> None:
        assert issubclass(UnknownActionError, SchedulerError)

    def test_valid_arguments_pass(self) -> None:
        registry = _registry()
        issues = registry.validate_arguments(
            ActionTypeId("travel"),
            {"dest": "ent_player_1", "speed": 3.0, "mode": "walk", "carried": True},
        )
        assert issues == ()

    def test_missing_required(self) -> None:
        issues = _registry().validate_arguments(ActionTypeId("travel"), {"speed": 3.0})
        assert issues == ("missing_required:dest",)

    def test_missing_optional_ok(self) -> None:
        assert _registry().validate_arguments(ActionTypeId("travel"), {"dest": "ent_a"}) == ()

    def test_unknown_key(self) -> None:
        issues = _registry().validate_arguments(
            ActionTypeId("travel"), {"dest": "ent_a", "foo": 1}
        )
        assert issues == ("unknown_argument:foo",)

    def test_entity_plain_string_rejected(self) -> None:
        issues = _registry().validate_arguments(ActionTypeId("travel"), {"dest": "bob"})
        assert issues == ("type_mismatch:dest",)

    def test_entity_producer_style_name_rejected(self) -> None:
        # ProducerId 名字型字符串不是 EntityId 词法（parse_id kind 分流）
        issues = _registry().validate_arguments(ActionTypeId("travel"), {"dest": "npc.brain"})
        assert issues == ("type_mismatch:dest",)

    def test_entity_valid_id_accepted(self) -> None:
        assert _registry().validate_arguments(ActionTypeId("travel"), {"dest": "ent_a_1"}) == ()

    def test_entity_typed_instance_accepted(self) -> None:
        issues = _registry().validate_arguments(
            ActionTypeId("travel"), {"dest": EntityId("ent_authoring_x")}
        )
        assert issues == ()

    @pytest.mark.parametrize("value", [42, 3.5, None, ["ent_a"], {"id": "ent_a"}])
    def test_entity_non_string_rejected(self, value: object) -> None:
        issues = _registry().validate_arguments(
            ActionTypeId("travel"), {"dest": value}  # type: ignore[dict-item]
        )
        assert issues == ("type_mismatch:dest",)

    @pytest.mark.parametrize("value", [0.0, 0.4])
    def test_number_below_min(self, value: float) -> None:
        issues = _registry().validate_arguments(
            ActionTypeId("travel"), {"dest": "ent_a", "speed": value}
        )
        assert issues == ("out_of_range:speed",)

    def test_number_above_max(self) -> None:
        issues = _registry().validate_arguments(
            ActionTypeId("travel"), {"dest": "ent_a", "speed": 10.5}
        )
        assert issues == ("out_of_range:speed",)

    def test_number_at_bounds_accepted(self) -> None:
        for value in (0.5, 10.0):
            assert (
                _registry().validate_arguments(
                    ActionTypeId("travel"), {"dest": "ent_a", "speed": value}
                )
                == ()
            )

    def test_number_bool_rejected(self) -> None:
        # bool 是 int 子类，number 型必须显式排除
        issues = _registry().validate_arguments(
            ActionTypeId("travel"), {"dest": "ent_a", "speed": True}
        )
        assert issues == ("type_mismatch:speed",)

    def test_string_type_mismatch(self) -> None:
        issues = _registry().validate_arguments(
            ActionTypeId("travel"), {"dest": "ent_a", "mode": 5}
        )
        assert issues == ("type_mismatch:mode",)

    def test_string_enum_mismatch(self) -> None:
        issues = _registry().validate_arguments(
            ActionTypeId("travel"), {"dest": "ent_a", "mode": "run"}
        )
        assert issues == ("enum_violation:mode",)

    def test_string_enum_match_ok(self) -> None:
        assert (
            _registry().validate_arguments(
                ActionTypeId("travel"), {"dest": "ent_a", "mode": "sneak"}
            )
            == ()
        )

    def test_number_enum_mismatch(self) -> None:
        issues = _registry().validate_arguments(
            ActionTypeId("travel"), {"dest": "ent_a", "level": 5}
        )
        assert issues == ("enum_violation:level",)

    def test_number_enum_match_ok(self) -> None:
        assert (
            _registry().validate_arguments(ActionTypeId("travel"), {"dest": "ent_a", "level": 2})
            == ()
        )

    def test_boolean_type_mismatch(self) -> None:
        issues = _registry().validate_arguments(
            ActionTypeId("travel"), {"dest": "ent_a", "carried": "yes"}
        )
        assert issues == ("type_mismatch:carried",)

    def test_multiple_issues_deterministic_order(self) -> None:
        # 逐参数（spec 插入序：dest, speed, mode, carried）先于未知键（arguments 插入序）
        issues = _registry().validate_arguments(
            ActionTypeId("travel"), {"speed": "fast", "zeta": 1, "alpha": 2}
        )
        assert issues == (
            "missing_required:dest",
            "type_mismatch:speed",
            "unknown_argument:zeta",
            "unknown_argument:alpha",
        )

    def test_type_mismatch_short_circuits_range_and_enum(self) -> None:
        # 类型不符时跳过该参数的界/枚举检查（单参数一条 issue）
        issues = _registry().validate_arguments(
            ActionTypeId("travel"), {"dest": "ent_a", "mode": 5}
        )
        assert issues == ("type_mismatch:mode",)

    def test_empty_parameter_spec(self) -> None:
        registry = _registry()
        assert registry.validate_arguments(ActionTypeId("idle"), {}) == ()
        issues = registry.validate_arguments(ActionTypeId("idle"), {"x": 1})
        assert issues == ("unknown_argument:x",)


# —— resolve_duration（§6.1）——


class TestResolveDuration:
    def test_fixed_direct(self) -> None:
        registry = _registry()
        spec = registry.lookup(ActionTypeId("travel"))
        assert spec is not None
        assert registry.resolve_duration(spec, ActionTiming()) == 30

    def test_fixed_one_tick(self) -> None:
        spec = ActionSpec(
            action_id="blink",
            executor="npc.brain",
            duration_policy=DurationPolicy(kind="fixed", duration_ticks=1),
        )
        assert ActionRegistry(specs={}).resolve_duration(spec, ActionTiming()) == 1

    def test_hint_rounding_scale_times_30(self) -> None:
        spec = _rest_spec()  # hint_scale=0.5
        registry = ActionRegistry(specs={})
        assert registry.resolve_duration(spec, ActionTiming(duration_hint_ticks=30)) == 15
        # round(0.33 × 30) = round(9.9) = 10（Python round 口径）
        scaled = ActionSpec(
            action_id="s",
            executor="npc.brain",
            duration_policy=DurationPolicy(kind="hint", hint_scale=0.33),
        )
        assert registry.resolve_duration(scaled, ActionTiming(duration_hint_ticks=30)) == 10
        # 放大路径：2.0 × 30 = 60
        doubled = ActionSpec(
            action_id="d",
            executor="npc.brain",
            duration_policy=DurationPolicy(kind="hint", hint_scale=2.0),
        )
        assert registry.resolve_duration(doubled, ActionTiming(duration_hint_ticks=30)) == 60

    def test_hint_missing_is_event_driven(self) -> None:
        registry = ActionRegistry(specs={})
        assert registry.resolve_duration(_rest_spec(), ActionTiming()) is None

    def test_none_kind_is_event_driven(self) -> None:
        spec = ActionSpec(action_id="idle2", executor="npc.brain")  # 缺省 kind="none"
        registry = ActionRegistry(specs={})
        assert registry.resolve_duration(spec, ActionTiming(duration_hint_ticks=30)) is None

    @pytest.mark.parametrize(
        ("scale", "hint"),
        [(0.01, 20), (1.0, 0), (1.0, -5)],
        ids=["0.2-clamped", "zero-clamped", "negative-clamped"],
    )
    def test_subtick_result_clamped_to_one(self, scale: float, hint: int) -> None:
        # D-P3-01 子 tick 钳制规则（D3 披露，§8.5）：结果 < 1 → 1 tick（确定性）
        spec = ActionSpec(
            action_id="short",
            executor="npc.brain",
            duration_policy=DurationPolicy(kind="hint", hint_scale=scale),
        )
        registry = ActionRegistry(specs={})
        assert registry.resolve_duration(spec, ActionTiming(duration_hint_ticks=hint)) == 1


# —— validate_timing（§6.1）——


class TestValidateTiming:
    def test_deadline_before_earliest(self) -> None:
        timing = ActionTiming(earliest_start_tick=10, deadline_tick=5)
        assert validate_timing(timing) == ("deadline_before_earliest",)

    def test_deadline_equal_earliest_ok(self) -> None:
        assert validate_timing(ActionTiming(earliest_start_tick=10, deadline_tick=10)) == ()

    def test_deadline_after_earliest_ok(self) -> None:
        assert validate_timing(ActionTiming(earliest_start_tick=10, deadline_tick=20)) == ()

    def test_partial_fields_ok(self) -> None:
        assert validate_timing(ActionTiming(earliest_start_tick=10)) == ()
        assert validate_timing(ActionTiming(deadline_tick=5)) == ()
        assert validate_timing(ActionTiming()) == ()

    @pytest.mark.parametrize("hint", [0, -3])
    def test_duration_hint_below_one(self, hint: int) -> None:
        assert validate_timing(ActionTiming(duration_hint_ticks=hint)) == (
            "duration_hint_below_one",
        )

    def test_duration_hint_one_ok(self) -> None:
        assert validate_timing(ActionTiming(duration_hint_ticks=1)) == ()

    def test_combined_issues_ordered(self) -> None:
        timing = ActionTiming(earliest_start_tick=10, deadline_tick=5, duration_hint_ticks=0)
        assert validate_timing(timing) == ("deadline_before_earliest", "duration_hint_below_one")


# —— round-trip 恒等（§6.1）——


class TestRoundTrip:
    def test_registry_roundtrip_identity(self) -> None:
        registry = _registry()
        assert_json_clean(registry.model_dump(mode="json"))
        text = dump_json(registry)
        assert isinstance(text, str)
        restored = load_json(ActionRegistry, text)
        assert restored == registry

    def test_registry_roundtrip_type_preservation(self) -> None:
        restored = load_json(ActionRegistry, dump_json(_registry()))
        assert set(restored.specs) == {"travel", "rest", "idle"}
        for key, spec in restored.specs.items():
            assert type(key) is ActionTypeId
            assert type(spec) is ActionSpec
            assert type(spec.action_id) is ActionTypeId
            for param in spec.parameters.values():
                assert type(param) is ParameterSpec
            assert type(spec.duration_policy) is DurationPolicy
        assert restored.specs["travel"].duration_policy == DurationPolicy(
            kind="fixed", duration_ticks=30
        )
        assert restored.specs["rest"].duration_policy.hint_scale == 0.5
        assert restored.specs["travel"].parameters["mode"].enum_values == [
            "walk",
            "sneak",
            "dash",
        ]

    def test_empty_registry_roundtrip(self) -> None:
        empty = ActionRegistry()
        restored = load_json(ActionRegistry, dump_json(empty))
        assert restored == empty
        assert restored.specs == {}

    def test_roundtrip_is_stable(self) -> None:
        registry = _registry()
        once = load_json(ActionRegistry, dump_json(registry))
        twice = load_json(ActionRegistry, dump_json(once))
        assert twice == once


# —— extra=forbid / frozen（ContractModel 基类约定，house 口径）——


class TestContractModelInvariants:
    @pytest.mark.parametrize(
        ("cls", "data"),
        [
            (ParameterSpec, {"type": "string"}),
            (DurationPolicy, {"kind": "none"}),
            (ActionSpec, {"action_id": "travel", "executor": "npc.brain"}),
            (ActionRegistry, {"specs": {}}),
        ],
        ids=["ParameterSpec", "DurationPolicy", "ActionSpec", "ActionRegistry"],
    )
    def test_extra_forbid(self, cls: type, data: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            cls.model_validate({**data, "__bogus__": 1})

    @pytest.mark.parametrize(
        ("cls", "data", "field_name", "value"),
        [
            (ParameterSpec, {"type": "string"}, "required", False),
            (DurationPolicy, {"kind": "none"}, "kind", "fixed"),
            (ActionSpec, {"action_id": "travel", "executor": "npc.brain"}, "interruptible", False),
            (ActionRegistry, {"specs": {}}, "specs", {}),
        ],
        ids=["ParameterSpec", "DurationPolicy", "ActionSpec", "ActionRegistry"],
    )
    def test_frozen_blocks_assignment(
        self, cls: type, data: dict[str, Any], field_name: str, value: Any
    ) -> None:
        model = cls.model_validate(data)
        with pytest.raises((ValidationError, TypeError)):
            setattr(model, field_name, value)
