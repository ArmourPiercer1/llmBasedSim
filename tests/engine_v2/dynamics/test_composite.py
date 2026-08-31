"""P7-W4 test_composite.py（SOT §6.1 t1–t8 逐文件编号，8 平铺函数，零
test class）。

契约面：fan-out 组合 dynamics backend ``CompositeDynamics``（SOT §3.6，T04）
——S6 标准装配 fan-out 子序拼接 + source 归属 + eff_ 前缀（t1）/ 空 children
面（t2，P1 钉死）/ ``determinism_join`` 格恒等元面（t3）/ 交换律采样面
（t4）/ 最差吸收 + 非法输入 ValueError（t5，P3 钉死）/ metadata domains
排序去重并集（t6）/ 三布尔 and 折叠 + backend_id/implementation_type/
fidelity 逐字（t7）/ 全独立双装配双跑 effects byte-identical（t8，K7 A 面）。

夹具：消费 W1 conftest ``make_p7_world`` / ``_det_entity_id``（SOT §6.2；
夹具只装配，不断言）；S6 标准装配 = ``CompositeDynamics(children=(
RuleDynamics(S1 规则集), ToyRigidDynamics()))``（S6 场景行逐字；双确定性、
零 fake）。
"""

from __future__ import annotations

import json

import pytest

from src.engine_v2.core.effects import ProposedEffect
from src.engine_v2.core.state import WorldState
from src.engine_v2.dynamics.backend import (
    DETERMINISM_CLASSES,
    BackendMetadata,
    DynamicsContext,
    WorldSnapshot,
)
from src.engine_v2.dynamics.composite import CompositeDynamics, determinism_join
from src.engine_v2.dynamics.diagnostic import DynamicsDiagnostic
from src.engine_v2.dynamics.rule import RuleDynamics, WorldRule
from src.engine_v2.dynamics.toy_rigid import ToyRigidDynamics
from tests.engine_v2.dynamics.conftest import _det_entity_id, make_p7_world

_WSI = "wsi_p7_composite_test"


def _snapshot(world: WorldState) -> WorldSnapshot:
    """``WorldSnapshot`` 直构（组合测试不需要完整 core Snapshot 信封）。"""
    return WorldSnapshot(
        world_state=world,
        world_revision=world.world_revision,
        logical_tick=0,
        world_instance_id=_WSI,
    )


def _effects_json(effects: tuple[ProposedEffect, ...]) -> str:
    """效果组规范化 JSON（K7 字节比较面；模块内私有，纯序列化不重跑）。"""
    return json.dumps(
        [effect.model_dump(mode="json") for effect in effects],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _s1_rule() -> WorldRule:
    """S1 场景规则（SOT §5.1 行逐字）：gravity==9.8 命中 → emit gem.fell（整实体）。"""
    return WorldRule(
        rule_id="r_gravity",
        when={"world_variable_equals": {"key": "gravity", "value": 9.8}},
        emit_effect_type="gem.fell",
        emit_target_entity=str(_det_entity_id("gem")),
        emit_component_type=None,
        emit_field_path=None,
        emit_payload={"moved": True},
    )


def _standard_composite() -> CompositeDynamics:
    """S6 标准装配（S6 行逐字）：(RuleDynamics(S1 规则集), ToyRigidDynamics())。"""
    return CompositeDynamics(
        children=(RuleDynamics(rules=(_s1_rule(),)), ToyRigidDynamics())
    )


def _component_rule(rule_id: str, component_type: str) -> WorldRule:
    """metadata 面测试规则（不要求命中）：emit 目标声明指定组件。"""
    return WorldRule(
        rule_id=rule_id,
        when={"entity_exists": {"entity": str(_det_entity_id("gem"))}},
        emit_effect_type="gem.fell",
        emit_target_entity=str(_det_entity_id("gem")),
        emit_component_type=component_type,
        emit_field_path=None,
        emit_payload={"moved": True},
    )


class _NoReplayBackend:
    """构造面自定 backend 子（t7 布尔 and 假值面）：replayable=False，simulate 恒空。"""

    __slots__ = ()

    def metadata(self) -> BackendMetadata:
        return BackendMetadata(
            backend_id="fake_noreplay",
            producer_id="fake_noreplay",
            domains=("fake_domain",),
            determinism="deterministic",
            implementation_type="rule",
            fidelity="fake",
            checkpointable=True,
            restorable=True,
            replayable=False,
        )

    def simulate(
        self,
        snapshot: WorldSnapshot,
        stimuli,
        context: DynamicsContext,
    ) -> tuple[ProposedEffect, ...]:
        return ()

    @property
    def diagnostics(self) -> tuple[DynamicsDiagnostic, ...]:
        return ()


def test_composite_fanout_child_order() -> None:
    """t1：S6 标准装配 fan-out → effects = 子序拼接（rule 子在前、toy 子在后）+ source 归属 + eff_ 确定性前缀。"""
    composite = _standard_composite()
    effects = composite.simulate(
        _snapshot(make_p7_world()), (), DynamicsContext(base_revision=0, dt=0.5)
    )
    assert len(effects) == 2
    assert effects[0].effect_type == "gem.fell"
    assert effects[0].source == "rule_dynamics"
    assert effects[1].effect_type == "core.set_component"
    assert effects[1].source == "rigid_body"
    assert effects[0].effect_id.startswith("eff_")
    assert effects[1].effect_id.startswith("eff_")
    assert composite.diagnostics == ()


def test_composite_empty_children() -> None:
    """t2：空 children → simulate () + 零诊断；metadata 9 字段 = P1 钉死值。"""
    composite = CompositeDynamics(children=())
    effects = composite.simulate(
        _snapshot(make_p7_world()), (), DynamicsContext(base_revision=0)
    )
    assert effects == ()
    assert composite.diagnostics == ()
    meta = composite.metadata()
    assert meta.backend_id == "composite_dynamics"
    assert meta.producer_id == "composite_dynamics"
    assert meta.domains == ()
    assert meta.determinism == "deterministic"
    assert meta.implementation_type == "composite"
    assert meta.fidelity == "composite"
    assert meta.checkpointable is True
    assert meta.restorable is True
    assert meta.replayable is True


def test_determinism_join_det_det() -> None:
    """t3：join(deterministic, deterministic) = deterministic（格单位元 + 恒等律采样）。"""
    assert determinism_join("deterministic", "deterministic") == "deterministic"
    assert determinism_join("deterministic", "deterministic") in DETERMINISM_CLASSES
    for value in DETERMINISM_CLASSES:
        assert determinism_join("deterministic", value) == value
    assert DETERMINISM_CLASSES == ("deterministic", "seeded", "nondeterministic")


def test_determinism_join_det_seeded() -> None:
    """t4：join(det, seeded) 与 join(seeded, det) 皆 seeded（格交换律采样面 + 幂等面）。"""
    assert determinism_join("deterministic", "seeded") == "seeded"
    assert determinism_join("seeded", "deterministic") == "seeded"
    assert (
        determinism_join("deterministic", "seeded")
        == determinism_join("seeded", "deterministic")
    )
    assert determinism_join("seeded", "seeded") == "seeded"


def test_determinism_join_seeded_nondet() -> None:
    """t5：join(seeded, nondeterministic) → nondeterministic（最差吸收）；非法输入 → ValueError（P3）。"""
    assert determinism_join("seeded", "nondeterministic") == "nondeterministic"
    assert determinism_join("nondeterministic", "seeded") == "nondeterministic"
    assert (
        determinism_join("nondeterministic", "nondeterministic") == "nondeterministic"
    )
    with pytest.raises(ValueError):
        determinism_join("bogus", "seeded")
    with pytest.raises(ValueError):
        determinism_join("deterministic", "Bogus")
    with pytest.raises(ValueError):
        determinism_join("", "deterministic")


def test_composite_metadata_domains_union() -> None:
    """t6：子 domains 交集/重复（rigid 同时被 rule 子与 toy 子声明）→ 排序去重并集，逐项 = sorted(set(union))。"""
    rule_backend = RuleDynamics(
        rules=(_component_rule("r_gem_state", "gem_state"), _component_rule("r_rigid", "rigid"))
    )
    toy_backend = ToyRigidDynamics()
    composite = CompositeDynamics(children=(rule_backend, toy_backend))
    expected = tuple(
        sorted(set(rule_backend.metadata().domains) | set(toy_backend.metadata().domains))
    )
    assert composite.metadata().domains == expected
    assert composite.metadata().domains == ("gem_state", "rigid")
    assert len(composite.metadata().domains) == len(set(composite.metadata().domains))


def test_composite_metadata_booleans_and() -> None:
    """t7：全真 → 全真（标准装配）；一子 replayable=False（构造面自定子）→ and 折叠正确；backend_id/implementation_type/fidelity 逐字。"""
    standard = _standard_composite()
    meta = standard.metadata()
    assert meta.checkpointable is True
    assert meta.restorable is True
    assert meta.replayable is True
    assert meta.backend_id == "composite_dynamics"
    assert meta.implementation_type == "composite"
    assert meta.fidelity == "composite.abstract.rigid_1d"
    mixed = CompositeDynamics(children=(RuleDynamics(rules=()), _NoReplayBackend()))
    mixed_meta = mixed.metadata()
    assert mixed_meta.replayable is False
    assert mixed_meta.checkpointable is True
    assert mixed_meta.restorable is True
    assert mixed_meta.fidelity == "composite.abstract.fake"


def test_composite_double_run_byte_identical() -> None:
    """t8：两全独立装配（新 composite×2、world×2）→ effects canonical JSON byte-identical（K7 A 面）。"""
    effects_a = _standard_composite().simulate(
        _snapshot(make_p7_world()), (), DynamicsContext(base_revision=0, dt=0.5)
    )
    effects_b = _standard_composite().simulate(
        _snapshot(make_p7_world()), (), DynamicsContext(base_revision=0, dt=0.5)
    )
    json_a = _effects_json(effects_a)
    json_b = _effects_json(effects_b)
    assert json_a == json_b
    assert len(effects_a) == len(effects_b) == 2
    assert json_a.startswith("[{")
