"""P7-W5 test_g7_scenarios.py（SOT §5.1/§5.2/§5.3，A1–A14 逐行）。

G7 三场景验收面（一场景一函数，t1–t14 = §5.3 表 A1–A14 逐行，零跨行断言）：

- Case A（t1–t4）：单推理 turn（S3/S8）——恰 1 effect / 提交与 revision /
  终态 moved / provenance 链（K6 origin + source + cause_ids 恒空）；
- Case B（t5–t9）：组合双 backend fan-out（S5）——2 effects 可见 /
  detect_conflicts 恰 1 组 / 缺省四策链 1 WINNER（producer_priority 拍板，
  dropped 承载 REJECT 语义）/ WINNER = 物理 effect / 终态 stay；
- t10：G7 逐字条款场景侧机械像（A10，§0.2 逐字条款 + §3.9 第 4 法 (a) 规格；S5 装配后扫 core）；
- Case C（t11–t14）：纯数值 backend——checkpoint JSON-clean / restore 续跑 /
  两条独立续跑 byte-identical / metadata 五值面。

装配（冻结 W4 test_host_driver t8 逐字镜像，wsi 字面量除外）：policy = 单条
通配规则并集放行（ERR-P7-09(b)：whole-entity target 在组件级 selector 下不
匹配冻结 match_selector，故场景 turn 用通配单规则；**不**用 make_p7_policy()）；
Case A origin producer = llm_world_dynamics；Case B origin producer =
composite_dynamics；world_instance_id = 本地 _WSI 字面量。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.engine_v2.core.authority import (
    AuthorityPolicy,
    AuthorityRule,
    AuthoritySelector,
    check_authority,
)
from src.engine_v2.core.cascade import CascadeExecutor
from src.engine_v2.core.conflicts import (
    ConflictAction,
    ResolutionContext,
    detect_conflicts,
    resolve_conflicts,
)
from src.engine_v2.core.ids import ProducerId
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.reducer import uninstall_write_barrier
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.serialization import assert_json_clean
from src.engine_v2.core.state import WorldState
from src.engine_v2.core.transaction import TransactionStatus
from src.engine_v2.dynamics import (
    authority as _m_authority,
    backend as _m_backend,
    composite as _m_composite,
    diagnostic as _m_diagnostic,
    host as _m_host,
    llm_world as _m_llm_world,
    rule as _m_rule,
    toy_rigid as _m_toy_rigid,
)
from src.engine_v2.dynamics.backend import (
    DynamicsContext,
    WorldSnapshot,
    _FixedMonotonicClock,
)
from src.engine_v2.dynamics.composite import CompositeDynamics
from src.engine_v2.dynamics.host import run_dynamics_turn
from src.engine_v2.dynamics.llm_world import LLMWorldDynamics, LLMWorldDynamicsConfig
from src.engine_v2.dynamics.toy_rigid import ToyRigidDynamics
from src.engine_v2.llm.adapter import FakeInferenceBackend
from tests.engine_v2.dynamics.conftest import (
    _det_entity_id,
    gem_effect_handlers,
    make_p7_component_registry,
    make_p7_producer_registry,
    make_p7_world,
)

_WSI = "wsi_p7_g7_scenarios_test"
_CAUSAL_ROOT_ID = "turn_p7_case_a"
_S5_WIRE = json.dumps(
    {
        "effects": [
            {
                "effect_type": "gem.fell",
                "entity_id": str(_det_entity_id("gem")),
                "payload": {},
            }
        ],
        "reasoning": "support removed",
    },
    ensure_ascii=False,
    separators=(",", ":"),
)

#: A10 的 35 个 P7 export 名——运行时自 8 模块 __all__ 派生（§3.9 第 4 法 (a) 规格；
#: 模块序 = §8.2 账本序；不硬编码名字面量，35 名与 §8.2 自动同步）。
_P7_EXPORTS: tuple[str, ...] = tuple(
    name
    for mod in (
        _m_backend,
        _m_diagnostic,
        _m_rule,
        _m_toy_rigid,
        _m_llm_world,
        _m_composite,
        _m_authority,
        _m_host,
    )
    for name in mod.__all__
)


@pytest.fixture(autouse=True)
def _barrier_isolation() -> None:
    """写屏障 opt-in 纪律（W4 test_host_driver 同形）：CascadeExecutor 构造即
    武装屏障，测试前后各还原一次全局未武装态。"""
    uninstall_write_barrier()
    yield
    uninstall_write_barrier()


def _snapshot(world: WorldState) -> WorldSnapshot:
    """WorldSnapshot 直构（W4 t8 同形；host 测试不需要完整 core Snapshot 信封）。"""
    return WorldSnapshot(
        world_state=world,
        world_revision=world.world_revision,
        logical_tick=0,
        world_instance_id=_WSI,
    )


def _g7_policy() -> AuthorityPolicy:
    """g7 host turn 标准 policy（ERR-P7-09(b) 通配单规则并集放行；W4 t8 镜像）。"""
    return AuthorityPolicy(
        rules=[
            AuthorityRule(
                selector=AuthoritySelector(),
                allowed_writers=[
                    ProducerId("rule_dynamics"),
                    ProducerId("rigid_body"),
                    ProducerId("llm_world_dynamics"),
                    ProducerId("composite_dynamics"),
                ],
                priority=100,
            )
        ]
    )


def _g7_executor() -> CascadeExecutor:
    """g7 执行器（W4 t8 同款接线；handlers = 冻结 conftest gem 语义 handler）。"""
    return CascadeExecutor(
        policy=_g7_policy(),
        component_registry=make_p7_component_registry(),
        producer_registry=make_p7_producer_registry(),
        handlers=gem_effect_handlers(),
    )


def _llm_backend(wire: str) -> LLMWorldDynamics:
    """推理子 backend（W3/W4 冻结形态；scripted fake + 固定时钟，base_revision=0）。"""
    fake = FakeInferenceBackend(script={("world_dynamics", Revision(0), 1): wire})
    return LLMWorldDynamics(
        backend=fake,
        config=LLMWorldDynamicsConfig(
            capability_id="world_dynamics", prompt_ref="prompt://p7/gem"
        ),
        clock=_FixedMonotonicClock(),
    )


def _case_a_turn(scripted_wire_response: str, stim_support_removed: Any) -> Any:
    """Case A host turn 标准装配（S3 wire；origin producer = llm_world_dynamics）。"""
    world = make_p7_world()
    origin = Provenance(
        producer_id=ProducerId("llm_world_dynamics"),
        origin=OriginKind.DYNAMICS_BACKEND,
    )
    return run_dynamics_turn(
        backend=_llm_backend(scripted_wire_response),
        snapshot=_snapshot(world),
        stimuli=(stim_support_removed,),
        context=DynamicsContext(base_revision=0),
        state=world,
        executor=_g7_executor(),
        causal_root_id=_CAUSAL_ROOT_ID,
        origin=origin,
    )


def _case_b_backend() -> CompositeDynamics:
    """Case B 组合 backend（声明序 = 到达序：toy 先、推理子后；wire = _S5_WIRE）。"""
    return CompositeDynamics(children=(ToyRigidDynamics(), _llm_backend(_S5_WIRE)))


def _s5_batch(stim_support_removed: Any) -> tuple[Any, ...]:
    """S5 双 backend 批：组合体 simulate（同 snapshot/刺激/context，§3.6）。"""
    world = make_p7_world()
    return _case_b_backend().simulate(
        _snapshot(world), (stim_support_removed,), DynamicsContext(base_revision=0)
    )


def _s5_resolution(stim_support_removed: Any) -> tuple[Any, Any]:
    """S5 冲突面装配（A6/A7/A8 共用）：S5 批 + check_authority + 缺省四策链 report。"""
    effects = _s5_batch(stim_support_removed)
    world = make_p7_world()
    decisions = {
        effect.effect_id: check_authority(
            effect,
            _g7_policy(),
            state=world,
            component_registry=make_p7_component_registry(),
        )
        for effect in effects
    }
    ctx = ResolutionContext.from_batch(
        effects,
        authority_decisions=decisions,
        producer_registry=make_p7_producer_registry(),
    )
    return effects, resolve_conflicts(effects, ctx)


def _canonical_effects(effects: tuple[Any, ...]) -> str:
    """canonical JSON（逐 effect model_dump(mode=\"json\") + sort_keys + 紧凑分隔符；
    W1 test_toy_rigid t10 同形读法）。"""
    return json.dumps(
        [effect.model_dump(mode="json") for effect in effects],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def test_g7_case_a_single_effect(scripted_wire_response: str, stim_support_removed) -> None:
    """t1：A1：S3 simulate 面——scripted 推理恰产 1 个 ProposedEffect（gem.moved /
    整实体 / source=llm_world_dynamics）。"""
    world = make_p7_world()
    effects = _llm_backend(scripted_wire_response).simulate(
        _snapshot(world), (stim_support_removed,), DynamicsContext(base_revision=0)
    )
    assert len(effects) == 1
    effect = effects[0]
    assert effect.effect_type == "gem.moved"
    assert effect.target.component_type is None
    assert effect.source == "llm_world_dynamics"


def test_g7_case_a_commit_and_revision(
    scripted_wire_response: str, stim_support_removed
) -> None:
    """t2：A2：Case A host turn——authority rule_allow + validation 通过 → 恰 1 个
    COMMITTED；final_state.world_revision == base + 1（== 1）；deferred 恒空。"""
    turn = _case_a_turn(scripted_wire_response, stim_support_removed)
    assert len(turn.result.transactions) == 1
    assert turn.result.transactions[0].status == TransactionStatus.COMMITTED
    assert turn.result.final_state.world_revision == 1
    assert turn.result.deferred == ()


def test_g7_case_a_final_state_moved(scripted_wire_response: str, stim_support_removed) -> None:
    """t3：A3：Case A host turn——final_state 中 gem 的 gem_state.moved is True（handler 应用）。"""
    turn = _case_a_turn(scripted_wire_response, stim_support_removed)
    record = turn.result.final_state.entities[_det_entity_id("gem")]
    assert record.components["gem_state"]["moved"] is True


def test_g7_case_a_provenance_chain(
    scripted_wire_response: str, stim_support_removed
) -> None:
    """t4：A4：Case A host turn——origin DYNAMICS_BACKEND 贯穿；effect source =
    llm_world_dynamics；effect cause_ids 恒空（K6）。"""
    turn = _case_a_turn(scripted_wire_response, stim_support_removed)
    assert turn.result.transactions[0].provenance.origin == OriginKind.DYNAMICS_BACKEND
    assert turn.effects[0].source == "llm_world_dynamics"
    assert turn.effects[0].cause_ids == []


def test_g7_case_b_two_effects_visible(stim_support_removed) -> None:
    """t5：A5：S5 批——恰 2 个 ProposedEffect：core.set_component（rigid_body，
    gem + rigid 组件）与 gem.fell（llm_world_dynamics，整实体）；序 = 声明序。"""
    effects = _s5_batch(stim_support_removed)
    assert len(effects) == 2
    toy_effect, inference_effect = effects
    assert toy_effect.effect_type == "core.set_component"
    assert toy_effect.source == "rigid_body"
    assert toy_effect.target.entity_id == _det_entity_id("gem")
    assert toy_effect.target.component_type == "rigid"
    assert toy_effect.metadata == {}
    assert inference_effect.effect_type == "gem.fell"
    assert inference_effect.source == "llm_world_dynamics"
    assert inference_effect.target.entity_id == _det_entity_id("gem")
    assert inference_effect.target.component_type is None
    assert inference_effect.metadata == {}
    assert inference_effect.cause_ids == []


def test_g7_case_b_conflict_group(stim_support_removed) -> None:
    """t6：A6：detect_conflicts——恰 1 个 ConflictGroup，成员 == 该 2 effect
    （整实体锁 ∩ 整组件锁相交）。"""
    effects = _s5_batch(stim_support_removed)
    groups = detect_conflicts(effects)
    assert len(groups) == 1
    group = groups[0]
    assert len(group.effects) == 2
    assert tuple(e.effect_id for e in group.effects) == tuple(
        e.effect_id for e in effects
    )


def test_g7_case_b_resolution_winner_reject(stim_support_removed) -> None:
    """t7：A7：缺省四策链——rule_priority 并列弃权、timestamp 弃权、
    producer_priority 100 > 50 拍板；恰 1 条 WINNER resolution，
    accepted ∪ dropped 全部可见。"""
    effects, report = _s5_resolution(stim_support_removed)
    assert len(report.resolutions) == 1
    resolution = report.resolutions[0]
    assert resolution.action == ConflictAction.WINNER
    assert resolution.strategy == "producer_priority"
    toy_id, inference_id = tuple(e.effect_id for e in effects)
    assert resolution.accepted == (toy_id,)
    assert resolution.dropped == (inference_id,)
    assert set(report.accepted) | set(report.dropped) == {toy_id, inference_id}


def test_g7_case_b_winner_is_physics(stim_support_removed) -> None:
    """t8：A8：WINNER accepted 对应物理 effect——source == "rigid_body"
    （registry priority 100 唯一最大 > 50）。"""
    effects, report = _s5_resolution(stim_support_removed)
    winner_id = report.resolutions[0].accepted[0]
    winner = next(e for e in effects if e.effect_id == winner_id)
    assert winner.source == "rigid_body"


def test_g7_case_b_final_state_stay(stim_support_removed) -> None:
    """t9：A9：Case B host turn（composite，origin=composite_dynamics）→ rigid 三值
    不变（pos/vel/acc == 0.0；acc 键被整组件替换 payload 丢弃，按 byte-truth
    以 .get("acc", 0.0) 断言）；gem_state.moved is False（REJECT handler 未执行）。"""
    world = make_p7_world()
    origin = Provenance(
        producer_id=ProducerId("composite_dynamics"),
        origin=OriginKind.DYNAMICS_BACKEND,
    )
    turn = run_dynamics_turn(
        backend=_case_b_backend(),
        snapshot=_snapshot(world),
        stimuli=(stim_support_removed,),
        context=DynamicsContext(base_revision=0),
        state=world,
        executor=_g7_executor(),
        causal_root_id=_CAUSAL_ROOT_ID,
        origin=origin,
    )
    record = turn.result.final_state.entities[_det_entity_id("gem")]
    rigid = record.components["rigid"]
    assert rigid["pos"] == 0.0
    assert rigid["vel"] == 0.0
    assert rigid.get("acc", 0.0) == 0.0
    assert record.components["gem_state"]["moved"] is False


def test_g7_kernel_no_backend_if_elif(stim_support_removed) -> None:
    """t10：A10：G7 逐字条款场景侧机械像——S5 装配后扫 core，token 闭集
    （包路径 / if-elif 字面 / 35 export 名）全部零命中。"""
    effects = _s5_batch(stim_support_removed)
    assert len(effects) == 2
    root = Path(__file__).resolve().parents[3]
    core_files = sorted((root / "src" / "engine_v2" / "core").rglob("*.py"))
    assert core_files
    tokens = ("engine_v2.dynamics", "if backend is", "elif backend is", *_P7_EXPORTS)
    for file in core_files:
        text = file.read_text(encoding="utf-8")
        for token in tokens:
            assert token not in text, f"core 文件 {file.name} 含 {token!r}"


def test_g7_case_c_checkpoint_json_clean() -> None:
    """t11：A11：toy checkpoint() == {"version": 1, "seed": 0} 且过 assert_json_clean。"""
    toy = ToyRigidDynamics()
    checkpoint = toy.checkpoint()
    assert checkpoint == {"version": 1, "seed": 0}
    assert_json_clean(checkpoint)


def test_g7_case_c_restore_continues() -> None:
    """t12：A12：restore(cp) 新实例——同 snapshot/刺激/context simulate →
    输出与 checkpoint 前实例 byte-identical（确定性续跑）。"""
    toy = ToyRigidDynamics()
    world = make_p7_world()
    snapshot = _snapshot(world)
    effects_before = toy.simulate(snapshot, (), DynamicsContext(base_revision=0))
    cp = toy.checkpoint()
    effects_after = toy.restore(cp).simulate(
        snapshot, (), DynamicsContext(base_revision=0)
    )
    assert _canonical_effects(effects_before) == _canonical_effects(effects_after)


def test_g7_case_c_two_independent_continuations() -> None:
    """t13：A13：同一 cp dict 两次独立 restore 到两个新实例——两条 continuation
    输出 byte-identical（branch 语义；无 P8 fork）。"""
    cp = ToyRigidDynamics().checkpoint()
    world = make_p7_world()
    snapshot = _snapshot(world)
    effects_c = ToyRigidDynamics().restore(cp).simulate(
        snapshot, (), DynamicsContext(base_revision=0)
    )
    effects_d = ToyRigidDynamics().restore(cp).simulate(
        snapshot, (), DynamicsContext(base_revision=0)
    )
    assert _canonical_effects(effects_c) == _canonical_effects(effects_d)


def test_g7_case_c_metadata_correct() -> None:
    """t14：A14：toy metadata——checkpointable/restorable/replayable 三布尔全 True，
    implementation_type == "numerical"，determinism == "deterministic"。"""
    metadata = ToyRigidDynamics().metadata()
    assert metadata.checkpointable is True
    assert metadata.restorable is True
    assert metadata.replayable is True
    assert metadata.implementation_type == "numerical"
    assert metadata.determinism == "deterministic"
