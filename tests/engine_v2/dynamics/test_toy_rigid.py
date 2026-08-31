"""P7-W1 test_toy_rigid.py（SOT §6.1 t1–t13（逐文件编号），13 平铺函数，零 test class）。

契约面：toy 数值后端 ``ToyRigidDynamics``（SOT §3.4）——欧拉积分 payload
面、效果词法/确定性（K7）、元数据、checkpoint/restore 语义与失败诊断
（``p7.checkpoint_restore_failed``）、无随机 / 无模块级可变状态（AST 自证）。
"""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import re

import pytest

from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.effects import EntityTarget
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.serialization import assert_json_clean
from src.engine_v2.core.state import WorldState
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.content.schemas import DiagnosticSeverity
from src.engine_v2.dynamics.backend import (
    DynamicsContext,
    DynamicsError,
    WorldSnapshot,
    new_deterministic_effect_id,
)
from src.engine_v2.dynamics.toy_rigid import (
    RIGID_COMPONENT,
    TOY_CHECKPOINT_VERSION,
    ToyRigidDynamics,
)

_WSI = "wsi_p7_toy_test"


def _eid(name: str) -> EntityId:
    """确定性测试实体 id（与 conftest 同一词法；模块内私有）。"""
    return EntityId("ent_" + hashlib.sha256(name.encode()).hexdigest()[:32])


def _toy_world(components_by_name: dict[str, dict[str, ComponentTypeId, dict]]) -> WorldState:
    """按名装配 WorldState（实体按名排序插入，验证面独立于构造序）。"""
    entities: dict[EntityId, EntityRecord] = {}
    for name in components_by_name:
        eid = _eid(name)
        entities[eid] = EntityRecord(entity_id=eid, components=components_by_name[name])
    return WorldState(world_revision=0, entities=entities)


def _snapshot(world: WorldState) -> WorldSnapshot:
    """``WorldSnapshot`` 直构（toy 测试不需要完整 core Snapshot）。"""
    return WorldSnapshot(
        world_state=world,
        world_revision=world.world_revision,
        logical_tick=0,
        world_instance_id=_WSI,
    )


def _effects_json(ty: ToyRigidDynamics, snap: WorldSnapshot, ctx: DynamicsContext) -> str:
    """规范化 JSON 序列化（K7 字节比较面；模块内私有）。"""
    return json.dumps(
        [e.model_dump(mode="json") for e in ty.simulate(snap, (), ctx)],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def test_toy_constant_velocity_integration() -> None:
    """t13：匀速积分（acc=0）——payload 恰含 pos/vel 两键（无 acc）。"""
    world = _toy_world({"a": {RIGID_COMPONENT: {"pos": 0.0, "vel": 2.0, "acc": 0.0}}})
    ctx = DynamicsContext(base_revision=0, dt=0.5)
    effects = ToyRigidDynamics().simulate(_snapshot(world), (), ctx)
    assert len(effects) == 1
    assert effects[0].payload == {"pos": 1.0, "vel": 2.0}


def test_toy_acceleration_integration() -> None:
    """t14：加速积分（acc=9.8, dt=0.5）——vel 端点取半步值。"""
    world = _toy_world({"a": {RIGID_COMPONENT: {"pos": 0.0, "vel": 0.0, "acc": 9.8}}})
    ctx = DynamicsContext(base_revision=0, dt=0.5)
    effects = ToyRigidDynamics().simulate(_snapshot(world), (), ctx)
    assert len(effects) == 1
    assert effects[0].payload == {"pos": 0.0, "vel": 9.8 * 0.5}


def test_toy_multi_entity_sorted_order() -> None:
    """t15：多实体 → 效果按 entity_id 字典序（K7 确定性排序面）。"""
    world = _toy_world(
        {
            "b": {RIGID_COMPONENT: {"pos": 1.0, "vel": 1.0, "acc": 0.0}},
            "a": {RIGID_COMPONENT: {"pos": 2.0, "vel": 1.0, "acc": 0.0}},
            "c": {RIGID_COMPONENT: {"pos": 3.0, "vel": 1.0, "acc": 0.0}},
        }
    )
    ctx = DynamicsContext(base_revision=0, dt=1.0)
    effects = ToyRigidDynamics().simulate(_snapshot(world), (), ctx)
    expected_order = sorted(_eid(name) for name in ("a", "b", "c"))
    assert [e.target.entity_id for e in effects] == expected_order


def test_toy_no_rigid_component_empty() -> None:
    """t16：无 ``rigid`` 组件实体 / 空世界 → 空效果元组。"""
    world = _toy_world({"g": {ComponentTypeId("gem_state"): {"moved": False}}})
    assert ToyRigidDynamics().simulate(_snapshot(world), (), DynamicsContext(base_revision=0)) == ()
    assert ToyRigidDynamics().simulate(_snapshot(WorldState()), (), DynamicsContext(base_revision=0)) == ()


def test_toy_effect_shape_set_component() -> None:
    """t17：效果形状——``core.set_component`` + EntityTarget(rigid) + 2 键 payload。"""
    world = _toy_world({"a": {RIGID_COMPONENT: {"pos": 0.5, "vel": -1.0, "acc": 0.0}}})
    ctx = DynamicsContext(base_revision=7, dt=1.0)
    effects = ToyRigidDynamics().simulate(_snapshot(world), (), ctx)
    (effect,) = effects
    assert effect.effect_type == "core.set_component"
    assert isinstance(effect.target, EntityTarget)
    assert effect.target.component_type == RIGID_COMPONENT
    assert set(effect.payload) == {"pos", "vel"}
    assert effect.source == "rigid_body"
    assert effect.base_revision == 7
    assert effect.cause_ids == []


def test_toy_effect_id_deterministic() -> None:
    """t18：效果 id = ``new_deterministic_effect_id("rigid", eid, base_revision)``。"""
    world = _toy_world({"a": {RIGID_COMPONENT: {"pos": 0.0, "vel": 1.0, "acc": 0.0}}})
    ctx = DynamicsContext(base_revision=3, dt=1.0)
    toy = ToyRigidDynamics()
    expected = new_deterministic_effect_id("rigid", _eid("a"), 3)
    (first,) = toy.simulate(_snapshot(world), (), ctx)
    (second,) = toy.simulate(_snapshot(world), (), DynamicsContext(base_revision=3, dt=1.0))
    assert first.effect_id == expected
    assert first.effect_id == second.effect_id
    assert re.fullmatch(r"eff_[0-9a-f]{32}", str(first.effect_id)) is not None


def test_toy_double_run_byte_identical() -> None:
    """t19：双跑字节一致（K7 铁律：同一上下文两次 simulate 输出规范化同字节）。"""
    world = _toy_world(
        {
            "a": {RIGID_COMPONENT: {"pos": 0.0, "vel": 2.0, "acc": 1.5}},
            "b": {RIGID_COMPONENT: {"pos": 4.0, "vel": -1.0, "acc": 0.0}},
        }
    )
    toy = ToyRigidDynamics(seed=99)
    snap = _snapshot(world)
    ctx = DynamicsContext(base_revision=0, dt=0.5)
    assert _effects_json(toy, snap, ctx) == _effects_json(toy, snap, DynamicsContext(base_revision=0, dt=0.5))


def test_toy_metadata() -> None:
    """t20：元数据 9 字段面（SOT §3.4 钉死值）。"""
    meta = ToyRigidDynamics().metadata()
    assert meta.backend_id == "rigid_body"
    assert meta.producer_id == "rigid_body"
    assert meta.domains == ("rigid",)
    assert meta.determinism == "deterministic"
    assert meta.implementation_type == "numerical"
    assert meta.fidelity == "rigid_1d"
    assert meta.checkpointable is True
    assert meta.restorable is True
    assert meta.replayable is True


def test_toy_checkpoint_json_clean() -> None:
    """t21：checkpoint 载荷 = {version, seed}，JSON-clean（版本常量联动）。"""
    default_cp = ToyRigidDynamics().checkpoint()
    assert default_cp == {"version": 1, "seed": 0}
    assert default_cp == {"version": TOY_CHECKPOINT_VERSION, "seed": 0}
    assert_json_clean(default_cp)
    assert ToyRigidDynamics(seed=42).checkpoint() == {"version": TOY_CHECKPOINT_VERSION, "seed": 42}


def test_toy_restore_roundtrip_continues() -> None:
    """t22：restore 返回新实例、保持 checkpoint、双跑输出字节一致。"""
    original = ToyRigidDynamics(seed=7)
    cp = original.checkpoint()
    restored = original.restore(cp)
    assert restored is not original
    assert restored.checkpoint() == cp
    world = _toy_world({"a": {RIGID_COMPONENT: {"pos": 1.0, "vel": 1.0, "acc": 2.0}}})
    snap = _snapshot(world)
    ctx = DynamicsContext(base_revision=0, dt=0.5)
    assert _effects_json(original, snap, ctx) == _effects_json(restored, snap, DynamicsContext(base_revision=0, dt=0.5))


def test_toy_restore_rejects_wrong_version() -> None:
    """t23：版本不符 → DynamicsError + 记录 ``p7.checkpoint_restore_failed`` 诊断。"""
    toy = ToyRigidDynamics()
    with pytest.raises(DynamicsError):
        toy.restore({"version": TOY_CHECKPOINT_VERSION + 1, "seed": 0})
    diags = toy.diagnostics
    assert len(diags) == 1
    assert diags[0].code == "p7.checkpoint_restore_failed"
    assert diags[0].severity == DiagnosticSeverity.ERROR


def test_toy_restore_rejects_non_json_clean() -> None:
    """t24：非 JSON-clean checkpoint → DynamicsError + 诊断记录。"""
    toy = ToyRigidDynamics()
    with pytest.raises(DynamicsError):
        toy.restore({"version": TOY_CHECKPOINT_VERSION, "seed": float("nan")})
    diags = toy.diagnostics
    assert len(diags) == 1
    assert diags[0].code == "p7.checkpoint_restore_failed"
    assert diags[0].severity == DiagnosticSeverity.ERROR


def _is_final_annotation(annotation: ast.expr) -> bool:
    """判定 AnnAssign 注解是否为 ``Final`` / ``Final[...]``（AD-4 豁免面）。"""
    node = annotation
    if isinstance(node, ast.Subscript):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id == "Final"
    if isinstance(node, ast.Attribute):
        return node.attr == "Final"
    return False


def test_toy_no_random_no_module_mutable_state() -> None:
    """t25：AST 自证——无 ``random`` 导入；无模块级可变字面量（AD-4 豁免面）。"""
    src_path = (
        pathlib.Path(__file__).resolve().parents[3] / "src" / "engine_v2" / "dynamics" / "toy_rigid.py"
    )
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "random"
        elif isinstance(node, ast.ImportFrom):
            assert node.module != "random"
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(node, ast.AnnAssign):
            if node.value is not None:
                assert _is_final_annotation(node.annotation), f"模块级 AnnAssign 非 Final: {ast.dump(node)}"
            continue
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                if node.targets[0].id == "__all__":
                    continue
                raise AssertionError(f"模块级 Assign 目标: {ast.dump(node)}")
            value = node.value
            is_bytes = isinstance(value, ast.Constant) and isinstance(value.value, bytes)
            assert not isinstance(value, (ast.List, ast.Dict, ast.Set)) and not is_bytes, (
                f"模块级可变字面量: {ast.dump(node)}"
            )
