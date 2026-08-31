"""P7-W2 test_rule_dynamics.py（SOT §6.1 t1–t10 逐文件编号，10 平铺函数，零 test class）。

契约面：声明式规则 backend ``RuleDynamics`` + 纯数据规则 ``WorldRule``
（SOT §3.3）——条件算子 3 闭集匹配、声明序确定性（K7）、``@field`` 引用
求值与其契约违规（``DynamicsError``）、双跑 byte-identical（A15）、
metadata 9 字段面（SOT §3.3 钉死值）、构造期词法/闭集违规拒绝。

夹具：消费 W1 conftest ``make_p7_world`` / ``_det_entity_id``（SOT §6.2；
夹具只装配，不断言）；零 test class、零 subprocess。
"""

from __future__ import annotations

import json

import pytest

from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.effects import EntityTarget, ProposedEffect
from src.engine_v2.core.state import WorldState
from src.engine_v2.dynamics.backend import (
    DynamicsContext,
    DynamicsError,
    WorldSnapshot,
    new_deterministic_effect_id,
)
from src.engine_v2.dynamics.rule import RuleDynamics, WorldRule
from tests.engine_v2.dynamics.conftest import _det_entity_id, make_p7_world

_WSI = "wsi_p7_rule_test"


def _snapshot(world: WorldState) -> WorldSnapshot:
    """``WorldSnapshot`` 直构（规则测试不需要完整 core Snapshot 信封）。"""
    return WorldSnapshot(
        world_state=world,
        world_revision=world.world_revision,
        logical_tick=0,
        world_instance_id=_WSI,
    )


def _effects_json(effects: tuple[ProposedEffect, ...]) -> str:
    """效果组规范化 JSON（K7/A15 字节比较面；模块内私有，纯序列化不重跑）。"""
    return json.dumps(
        [effect.model_dump(mode="json") for effect in effects],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def test_rule_world_variable_equals_fires() -> None:
    """t1：``world_variable_equals`` 命中（SOT §5.1 S1 r_gravity 逐字）→ 恰 1 effect 全字段面。"""
    gem = _det_entity_id("gem")
    rule = WorldRule(
        rule_id="r_gravity",
        when={"world_variable_equals": {"key": "gravity", "value": 9.8}},
        emit_effect_type="gem.fell",
        emit_target_entity=gem,
        emit_component_type=None,
        emit_field_path=None,
        emit_payload={"moved": True},
    )
    context = DynamicsContext(base_revision=4)
    effects = RuleDynamics(rules=(rule,)).simulate(_snapshot(make_p7_world()), (), context)
    assert len(effects) == 1
    (effect,) = effects
    assert effect.effect_type == "gem.fell"
    assert effect.source == "rule_dynamics"
    assert isinstance(effect.target, EntityTarget)
    assert effect.target.entity_id == gem
    assert effect.target.component_type is None
    assert effect.target.field_path is None
    assert effect.payload == {"moved": True}
    assert effect.base_revision == 4
    assert effect.cause_ids == []
    assert effect.effect_id == new_deterministic_effect_id("rule", "r_gravity", 4, 0)


def test_rule_component_field_equals_with_field_ref() -> None:
    """t2：``component_field_equals`` 命中 + payload ``@field`` 引用自目标实体组件求值。"""
    gem = _det_entity_id("gem")
    rule = WorldRule(
        rule_id="r_nudge",
        when={
            "component_field_equals": {
                "entity": gem,
                "component": "gem_state",
                "field": "moved",
                "value": False,
            }
        },
        emit_effect_type="gem.nudge",
        emit_target_entity=gem,
        emit_component_type="gem_state",
        emit_field_path="moved",
        emit_payload={"snapshot_moved": "@field:gem_state.moved"},
    )
    effects = RuleDynamics(rules=(rule,)).simulate(
        _snapshot(make_p7_world()), (), DynamicsContext(base_revision=0)
    )
    assert len(effects) == 1
    (effect,) = effects
    assert effect.effect_type == "gem.nudge"
    assert effect.payload == {"snapshot_moved": False}
    assert isinstance(effect.target, EntityTarget)
    assert effect.target.component_type == ComponentTypeId("gem_state")
    assert effect.target.field_path == "moved"


def test_rule_entity_exists_fires() -> None:
    """t3：``entity_exists`` 命中（实体在快照 entities 中）→ 恰 1 effect。"""
    gem = _det_entity_id("gem")
    rule = WorldRule(
        rule_id="r_present",
        when={"entity_exists": {"entity": gem}},
        emit_effect_type="gem.present",
        emit_target_entity=gem,
        emit_component_type=None,
        emit_field_path=None,
        emit_payload={"present": True},
    )
    effects = RuleDynamics(rules=(rule,)).simulate(
        _snapshot(make_p7_world()), (), DynamicsContext(base_revision=0)
    )
    assert len(effects) == 1
    (effect,) = effects
    assert effect.effect_type == "gem.present"
    assert effect.payload == {"present": True}


def test_rule_no_match_no_emit() -> None:
    """t4：各条件未命中形态（值不等/键缺/实体缺/组件缺/实体不存在）→ 零 effect。"""
    world = make_p7_world()
    gem = _det_entity_id("gem")
    mismatches: dict[str, dict[str, object]] = {
        "wrong_value": {"world_variable_equals": {"key": "gravity", "value": 9.9}},
        "missing_variable": {"world_variable_equals": {"key": "ghost_var", "value": 1}},
        "missing_entity": {
            "component_field_equals": {
                "entity": "ghost",
                "component": "gem_state",
                "field": "moved",
                "value": False,
            }
        },
        "missing_component": {
            "component_field_equals": {
                "entity": gem,
                "component": "nonexistent",
                "field": "moved",
                "value": False,
            }
        },
        "missing_entity_exists": {"entity_exists": {"entity": "ghost"}},
    }
    for label, when in mismatches.items():
        rule = WorldRule(
            rule_id="r_nomatch",
            when=when,
            emit_effect_type="gem.nomatch",
            emit_target_entity=gem,
            emit_component_type=None,
            emit_field_path=None,
            emit_payload={},
        )
        effects = RuleDynamics(rules=(rule,)).simulate(
            _snapshot(world), (), DynamicsContext(base_revision=0)
        )
        assert effects == (), label


def test_rule_declaration_order_deterministic() -> None:
    """t5：输出序 = ``rules`` 元组声明序（双命中；effect_id index = 声明位）。"""
    gem = _det_entity_id("gem")
    first = WorldRule(
        rule_id="r_decl_first",
        when={"entity_exists": {"entity": gem}},
        emit_effect_type="decl.first",
        emit_target_entity=gem,
        emit_component_type=None,
        emit_field_path=None,
        emit_payload={"order": "first"},
    )
    second = WorldRule(
        rule_id="r_decl_second",
        when={"world_variable_equals": {"key": "gravity", "value": 9.8}},
        emit_effect_type="decl.second",
        emit_target_entity=gem,
        emit_component_type=None,
        emit_field_path=None,
        emit_payload={"order": "second"},
    )
    world = make_p7_world()
    swapped = RuleDynamics(rules=(second, first)).simulate(
        _snapshot(world), (), DynamicsContext(base_revision=1)
    )
    assert [effect.effect_type for effect in swapped] == ["decl.second", "decl.first"]
    assert swapped[0].effect_id == new_deterministic_effect_id("rule", "r_decl_second", 1, 0)
    assert swapped[1].effect_id == new_deterministic_effect_id("rule", "r_decl_first", 1, 1)
    ordered = RuleDynamics(rules=(first, second)).simulate(
        _snapshot(world), (), DynamicsContext(base_revision=1)
    )
    assert [effect.effect_type for effect in ordered] == ["decl.first", "decl.second"]


def test_rule_field_ref_missing_component_raises() -> None:
    """t6：条件命中但 payload ``@field`` 引用组件缺失 → simulate 期 DynamicsError。"""
    gem = _det_entity_id("gem")
    rule = WorldRule(
        rule_id="r_bad_ref",
        when={"entity_exists": {"entity": gem}},
        emit_effect_type="gem.bad_ref",
        emit_target_entity=gem,
        emit_component_type=None,
        emit_field_path=None,
        emit_payload={"v": "@field:nonexistent_component.f"},
    )
    backend = RuleDynamics(rules=(rule,))
    with pytest.raises(DynamicsError):
        backend.simulate(_snapshot(make_p7_world()), (), DynamicsContext(base_revision=0))


def test_rule_double_run_byte_identical() -> None:
    """t7（A15）：同快照/刺激/context 两次 simulate → 两组效果规范化 JSON 逐字节一致（真实重跑比对）。"""
    gem = _det_entity_id("gem")
    rules = (
        WorldRule(
            rule_id="r_gravity",
            when={"world_variable_equals": {"key": "gravity", "value": 9.8}},
            emit_effect_type="gem.fell",
            emit_target_entity=gem,
            emit_component_type=None,
            emit_field_path=None,
            emit_payload={"moved": True},
        ),
        WorldRule(
            rule_id="r_nudge",
            when={
                "component_field_equals": {
                    "entity": gem,
                    "component": "gem_state",
                    "field": "moved",
                    "value": False,
                }
            },
            emit_effect_type="gem.nudge",
            emit_target_entity=gem,
            emit_component_type="gem_state",
            emit_field_path="moved",
            emit_payload={"snapshot_moved": "@field:gem_state.moved", "note": "fixed"},
        ),
    )
    backend = RuleDynamics(rules=rules)
    snap = _snapshot(make_p7_world())
    context = DynamicsContext(base_revision=0)
    first_run = backend.simulate(snap, (), context)
    second_run = backend.simulate(snap, (), context)
    assert len(first_run) == 2
    assert len(second_run) == 2
    assert _effects_json(first_run) == _effects_json(second_run)


def test_rule_metadata() -> None:
    """t8：metadata 9 字段面（SOT §3.3 钉死值；domains = 各规则触碰组件/域排序去重）。"""
    gem = _det_entity_id("gem")
    rules = (
        WorldRule(
            rule_id="r_meta_wv",
            when={"world_variable_equals": {"key": "gravity", "value": 9.8}},
            emit_effect_type="gem.fell",
            emit_target_entity=gem,
            emit_component_type=None,
            emit_field_path=None,
            emit_payload={"moved": True},
        ),
        WorldRule(
            rule_id="r_meta_ref",
            when={
                "component_field_equals": {
                    "entity": gem,
                    "component": "gem_state",
                    "field": "moved",
                    "value": False,
                }
            },
            emit_effect_type="gem.nudge",
            emit_target_entity=gem,
            emit_component_type="rigid",
            emit_field_path="pos",
            emit_payload={"p": "@field:rigid.pos"},
        ),
    )
    meta = RuleDynamics(rules=rules).metadata()
    assert meta.backend_id == "rule_dynamics"
    assert meta.producer_id == "rule_dynamics"
    assert meta.domains == ("gem_state", "rigid", "world_variables")
    assert meta.determinism == "deterministic"
    assert meta.implementation_type == "rule"
    assert meta.fidelity == "abstract"
    assert meta.checkpointable is True
    assert meta.restorable is True
    assert meta.replayable is True


def test_rule_id_lexical_rejected() -> None:
    """t9：``rule_id`` 词法违规（大写/数字开头/连字符/空格/空串）→ 构造期 DynamicsError。"""
    for bad in ("R_ID", "9id", "r-id", "r id", ""):
        with pytest.raises(DynamicsError):
            WorldRule(
                rule_id=bad,
                when={"entity_exists": {"entity": "gem"}},
                emit_effect_type="gem.fell",
                emit_target_entity="gem",
                emit_component_type=None,
                emit_field_path=None,
                emit_payload={},
            )


def test_rule_unknown_operator_rejected() -> None:
    """t10：``when`` 键不属 ``RULE_CONDITION_OPERATORS`` 闭集（拼写漂移/杜撰）→ 构造期 DynamicsError。"""
    for bad_op in ("world_variable_equal", "componentFieldEquals", "entity_exists_x"):
        with pytest.raises(DynamicsError):
            WorldRule(
                rule_id="r_bogus",
                when={bad_op: {"entity": "gem"}},
                emit_effect_type="gem.fell",
                emit_target_entity="gem",
                emit_component_type=None,
                emit_field_path=None,
                emit_payload={},
            )
