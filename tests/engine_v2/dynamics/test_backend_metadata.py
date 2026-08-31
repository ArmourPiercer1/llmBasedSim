"""P7-W1 test_backend_metadata.py（SOT §6.1 t1–t12，12 平铺函数，零 test class）。

契约面：``WorldSnapshot`` 投影/冻结（D-P7-14）、``Stimulus`` /
``DynamicsContext`` / ``InferenceBudget`` 构造校验（JSON-clean 铁律）、
``BackendMetadata`` 闭集词表 + 双构造稳定（A17）、``new_deterministic_
effect_id`` 词法与稳定性（K7）。
"""

from __future__ import annotations

import dataclasses
import json
import re

import pytest

from src.engine_v2.core.ids import EffectId
from src.engine_v2.core.serialization import assert_json_clean
from src.engine_v2.core.snapshot import Snapshot
from src.engine_v2.core.state import RuntimeState, WorldState
from src.engine_v2.dynamics.backend import (
    BackendMetadata,
    DETERMINISM_CLASSES,
    DynamicsContext,
    DynamicsError,
    FIDELITY_PATTERN,
    IMPLEMENTATION_TYPES,
    InferenceBudget,
    STIMULUS_KINDS,
    Stimulus,
    WorldSnapshot,
    new_deterministic_effect_id,
)

_WSI = "wsi_p7_backend_test"


def _make_backend_metadata(**overrides: object) -> BackendMetadata:
    """合法基线元数据（t8–t11 共用装配；闭集成员取 12 名 token 安全面）。"""
    base: dict[str, object] = {
        "backend_id": "rigid_body",
        "producer_id": "rigid_body",
        "domains": ("rigid",),
        "determinism": "deterministic",
        "implementation_type": "numerical",
        "fidelity": "rigid_1d",
        "checkpointable": True,
        "restorable": True,
        "replayable": True,
    }
    base.update(overrides)
    return BackendMetadata(**base)  # type: ignore[arg-type]


def test_world_snapshot_from_snapshot_projects() -> None:
    """t1：``from_snapshot`` 投影 core ``Snapshot``（丢墙钟，D-P7-14）。"""
    world = WorldState(
        world_revision=7,
        world_variables={"gravity": 9.8},
    )
    snap = Snapshot(
        world_instance_id=_WSI,
        world_state=world,
        runtime_state=RuntimeState(),
        created_logical_tick=42,
    )
    proj = WorldSnapshot.from_snapshot(snap)
    assert proj.world_state == world
    assert proj.world_revision == 7
    assert proj.logical_tick == 42
    assert proj.world_instance_id == _WSI
    assert not hasattr(proj, "created_wall_time")


def test_world_snapshot_frozen_revision_consistent() -> None:
    """t2：``world_revision`` 一致性断言 + 冻结（字段赋值 → FrozenInstanceError）。"""
    world = WorldState(world_revision=3)
    ok = WorldSnapshot(
        world_state=world,
        world_revision=world.world_revision,
        logical_tick=0,
        world_instance_id=_WSI,
    )
    assert ok.world_revision == 3
    with pytest.raises(DynamicsError):
        WorldSnapshot(
            world_state=world,
            world_revision=world.world_revision + 1,
            logical_tick=0,
            world_instance_id=_WSI,
        )
    with pytest.raises(dataclasses.FrozenInstanceError):
        ok.world_revision = 4


def test_stimulus_valid_construction() -> None:
    """t3：合法构造（``external`` / ``event`` 两 kind；entity_id 可空）。"""
    s = Stimulus(
        stimulus_id="stim_support_removed",
        kind="external",
        source="anvil",
        entity_id="ent_" + "ab" * 16,
        payload={"support": "removed"},
    )
    assert s.kind in STIMULUS_KINDS
    assert s.payload == {"support": "removed"}
    s2 = Stimulus(
        stimulus_id="stim_event_1",
        kind="event",
        source="world",
        entity_id=None,
        payload={},
    )
    assert s2.entity_id is None
    assert s2.payload == {}


def test_stimulus_rejects_unknown_kind() -> None:
    """t4：``kind`` 闭集外 → 构造期拒绝（DynamicsError）。"""
    with pytest.raises(DynamicsError):
        Stimulus(
            stimulus_id="stim_x",
            kind="nonsense",
            source="anvil",
            entity_id=None,
            payload={},
        )


def test_stimulus_rejects_non_json_clean_payload() -> None:
    """t5：payload 非 JSON-clean → 构造期拒绝（P7-INV-4 机械面）。"""
    with pytest.raises(DynamicsError):
        Stimulus(
            stimulus_id="stim_x",
            kind="external",
            source="anvil",
            entity_id=None,
            payload={"k": object()},
        )
    with pytest.raises(DynamicsError):
        Stimulus(
            stimulus_id="stim_x",
            kind="external",
            source="anvil",
            entity_id=None,
            payload={"k": float("nan")},
        )


def test_dynamics_context_defaults() -> None:
    """t6：缺省面（dt=1.0 / seed=None / budget=None / 确定性固定时钟 0 起）。"""
    with pytest.raises(TypeError):
        DynamicsContext()  # type: ignore[call-arg]
    ctx = DynamicsContext(base_revision=3)
    assert ctx.base_revision == 3
    assert ctx.dt == 1.0
    assert ctx.seed is None
    assert ctx.budget is None
    first = ctx.clock.now_ms()
    second = ctx.clock.now_ms()
    assert (first, second) == (0, 1)


def test_inference_budget_validation() -> None:
    """t7：预算构造校验（缺省 1/1；0 合法；非 int / 负值 / bool → 拒绝）。"""
    default = InferenceBudget()
    assert (default.max_calls, default.max_repair_retries) == (1, 1)
    zero = InferenceBudget(max_calls=0, max_repair_retries=5)
    assert (zero.max_calls, zero.max_repair_retries) == (0, 5)
    for bad in ("3", -1, True, 1.0):
        with pytest.raises(DynamicsError):
            InferenceBudget(max_calls=bad)  # type: ignore[arg-type]
        with pytest.raises(DynamicsError):
            InferenceBudget(max_repair_retries=bad)  # type: ignore[arg-type]


def test_metadata_determinism_closed_set() -> None:
    """t8：``determinism`` 闭集 = {deterministic, seeded, nondeterministic}。"""
    assert set(DETERMINISM_CLASSES) == {"deterministic", "seeded", "nondeterministic"}
    for value in DETERMINISM_CLASSES:
        _make_backend_metadata(determinism=value)
    with pytest.raises(DynamicsError):
        _make_backend_metadata(determinism="chaotic")


def test_metadata_implementation_type_closed_set() -> None:
    """t9：``implementation_type`` 闭集 4 元；异名拒绝（token 安全写法）。"""
    assert len(IMPLEMENTATION_TYPES) == 4
    for value in ("rule", "numerical", "composite"):
        assert value in IMPLEMENTATION_TYPES
        _make_backend_metadata(implementation_type=value)
    with pytest.raises(DynamicsError):
        _make_backend_metadata(implementation_type="hybrid")


def test_metadata_fidelity_pattern() -> None:
    """t10：``FIDELITY_PATTERN`` fullmatch 接受/拒绝面 + 元数据校验联动。"""
    for ok_value in ("rigid_1d", "a.b.c"):
        assert re.fullmatch(FIDELITY_PATTERN, ok_value) is not None
    for bad_value in ("", "1abc", "Abc", "a..b", ".a", "a."):
        assert re.fullmatch(FIDELITY_PATTERN, bad_value) is None
    with pytest.raises(DynamicsError):
        _make_backend_metadata(fidelity="Bad Id")


def test_metadata_double_construct_stable_json_clean() -> None:
    """t11（A17）：双构造 domains 归一 + ``to_dict()`` 字节稳定 + JSON-clean。"""
    m1 = _make_backend_metadata(domains=("zeta", "alpha"))
    m2 = _make_backend_metadata(domains=("zeta", "alpha"))
    assert m1.domains == ("alpha", "zeta")
    d1 = m1.to_dict()
    d2 = m2.to_dict()
    blob1 = json.dumps(d1, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    blob2 = json.dumps(d2, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert blob1 == blob2
    assert_json_clean(d1)


def test_deterministic_effect_id_pattern_and_stability() -> None:
    """t12：``new_deterministic_effect_id`` 词法 + 同参稳定 + 异参不同（K7）。"""
    eid1 = new_deterministic_effect_id("rigid", "ent_ab", 3)
    eid2 = new_deterministic_effect_id("rigid", "ent_ab", 3)
    assert isinstance(eid1, EffectId)
    assert eid1 == eid2
    assert re.fullmatch(r"eff_[0-9a-f]{32}", str(eid1)) is not None
    other = new_deterministic_effect_id("rigid", "ent_ab", 4)
    assert other != eid1
