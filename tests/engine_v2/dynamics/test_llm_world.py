"""P7-W3 test_llm_world.py（SOT §6.1 t1–t14 逐文件编号，14 平铺函数，零 test class）。

契约面：脚本化推理世界动力学 backend ``LLMWorldDynamics``（SOT §3.5）——
wire → ``ProposedEffect`` 全字段映射面、确定性 effect_id、K6/ERR-P7-06
``cause_ids`` 恒空 + source = producer id、请求面/prompt 双跑 byte-identical
（A16）、解析败 → 修复成功流（P11 形态）、解析/schema 终败诊断面
（D-P7-05；P4 层边界 / P5 severity / P6 path / P7 refs）、wire 模型
``extra="forbid"`` + JSON-clean + effect_type 词法拒绝、预算 calls=0 耗尽
零调用、metadata 9 字段面、L0 契约常量机械钉死（sha256 + 逐字 K4 条款）、
canonical 世界事实稳定（正例 + 负例）、D-P7-15 诊断 last-run 视图。

夹具：消费 W1 conftest ``make_p7_world`` / ``_det_entity_id``（SOT §6.2；
夹具只装配，不断言）+ session 夹具 ``scripted_wire_response`` /
``stim_support_removed``；``FakeInferenceBackend`` / ``Revision`` 为测试侧
合法 import（P6 测试先例）；不 import 网络侧 backend（P7-INV-3）。
"""

from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError

from src.engine_v2.content.schemas import DiagnosticSeverity
from src.engine_v2.core.effects import ProposedEffect
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.state import WorldState
from src.engine_v2.dynamics.backend import (
    DynamicsContext,
    InferenceBudget,
    WorldSnapshot,
    _FixedMonotonicClock,
    new_deterministic_effect_id,
)
from src.engine_v2.dynamics.llm_world import (
    DYNAMICS_L0_CONTRACT,
    DynamicsEffectWire,
    DynamicsProposalWire,
    LLMWorldDynamics,
    LLMWorldDynamicsConfig,
)
from src.engine_v2.llm.adapter import FakeInferenceBackend
from tests.engine_v2.dynamics.conftest import _det_entity_id, make_p7_world

_WSI = "wsi_p7_llm_world_test"

#: SOT §5.1 L0 契约逐字 K4 条款（t12 断言子串；机械钉死面）。
_L0_K4_CLAUSE = (
    "All outputs are PROPOSALS subject to the kernel's authority check, "
    "validation and conflict resolution. You never mutate world state and "
    "never declare authority."
)


def _snapshot(world: WorldState) -> WorldSnapshot:
    """``WorldSnapshot`` 直构（推理测试不需要完整 core Snapshot 信封）。"""
    return WorldSnapshot(
        world_state=world,
        world_revision=world.world_revision,
        logical_tick=0,
        world_instance_id=_WSI,
    )


def _driver(backend: FakeInferenceBackend, **config_kw: object) -> LLMWorldDynamics:
    """driver 直构（config 缺省 = brief §3 缺省面；``_FixedMonotonicClock`` 直构）。"""
    config = LLMWorldDynamicsConfig(
        capability_id="world_dynamics",
        prompt_ref="prompt://p7/gem",
        **config_kw,
    )
    return LLMWorldDynamics(backend=backend, config=config, clock=_FixedMonotonicClock())


def _effects_json(effects: tuple[ProposedEffect, ...]) -> str:
    """效果组规范化 JSON（K7/A16 字节比较面；模块内私有，纯序列化不重跑）。"""
    return json.dumps(
        [effect.model_dump(mode="json") for effect in effects],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def test_llm_single_call_wire_to_effect(
    scripted_wire_response: str, stim_support_removed
) -> None:
    """t1：scripted 单答 wire → 恰 1 ``ProposedEffect``（全字段映射面 + 单调用 + 零诊断）。"""
    gem = _det_entity_id("gem")
    fake = FakeInferenceBackend(
        script={("world_dynamics", Revision(0), 1): scripted_wire_response}
    )
    driver = _driver(fake)
    effects = driver.simulate(
        _snapshot(make_p7_world()),
        (stim_support_removed,),
        DynamicsContext(base_revision=0),
    )
    assert len(effects) == 1
    effect = effects[0]
    assert effect.effect_type == "gem.moved"
    assert effect.target.entity_id == gem
    assert effect.source == "llm_world_dynamics"
    assert effect.payload == {}
    assert effect.base_revision == 0
    assert effect.cause_ids == []
    assert effect.authority_scope is None
    assert effect.priority_hint is None
    assert effect.target.component_type is None
    assert effect.target.field_path is None
    assert effect.effect_id == new_deterministic_effect_id(
        "inference", 0, 0, "gem.moved", str(gem)
    )
    assert len(fake.calls) == 1
    assert driver.diagnostics == ()


def test_llm_effect_id_deterministic(
    scripted_wire_response: str, stim_support_removed
) -> None:
    """t2：同 wire / 同 base_revision 两独立实例 effect_id 相等；改 base_revision=5 则不等。"""

    def run_once(rev: int):
        fake = FakeInferenceBackend(
            script={("world_dynamics", Revision(rev), 1): scripted_wire_response}
        )
        effects = _driver(fake).simulate(
            _snapshot(make_p7_world()),
            (stim_support_removed,),
            DynamicsContext(base_revision=rev),
        )
        assert len(effects) == 1
        return effects[0].effect_id

    id_a = run_once(0)
    id_b = run_once(0)
    assert id_a == id_b
    id_c = run_once(5)
    assert id_c != id_a


def test_llm_cause_ids_empty_origin_source(
    scripted_wire_response: str, stim_support_removed
) -> None:
    """t3（K6 / ERR-P7-06）：每个 effect ``cause_ids == []`` 且 ``source == config.producer_id``。"""
    gem = _det_entity_id("gem")
    fake = FakeInferenceBackend(
        script={("world_dynamics", Revision(0), 1): scripted_wire_response}
    )
    config = LLMWorldDynamicsConfig(
        capability_id="world_dynamics", prompt_ref="prompt://p7/gem"
    )
    driver = LLMWorldDynamics(
        backend=fake, config=config, clock=_FixedMonotonicClock()
    )
    effects = driver.simulate(
        _snapshot(make_p7_world()),
        (stim_support_removed,),
        DynamicsContext(base_revision=0),
    )
    assert len(effects) == 1
    for effect in effects:
        assert effect.cause_ids == []
        assert effect.source == config.producer_id
        assert effect.target.entity_id == gem


def test_llm_prompt_deterministic(
    scripted_wire_response: str, stim_support_removed
) -> None:
    """t4：两独立实例同输入 → prompt content byte-identical + 11 字段请求面逐项相等。"""
    fake_a = FakeInferenceBackend(
        script={("world_dynamics", Revision(0), 1): scripted_wire_response}
    )
    fake_b = FakeInferenceBackend(
        script={("world_dynamics", Revision(0), 1): scripted_wire_response}
    )
    _driver(fake_a).simulate(
        _snapshot(make_p7_world()),
        (stim_support_removed,),
        DynamicsContext(base_revision=0),
    )
    _driver(fake_b).simulate(
        _snapshot(make_p7_world()),
        (stim_support_removed,),
        DynamicsContext(base_revision=0),
    )
    req_a = fake_a.calls[0]
    req_b = fake_b.calls[0]
    assert req_a.messages[0].content == req_b.messages[0].content
    # 11 字段请求面逐项相等（全字段 dump 比较 = 10 非消息字段 + messages 的超集面）。
    assert req_a.model_dump(mode="json") == req_b.model_dump(mode="json")


def test_llm_parse_failure_repair_success(
    scripted_wire_response: str, stim_support_removed
) -> None:
    """t5：seq1 无花括号散文（no-json-object）→ 修复 → seq2 scripted 成功；恰 1 effect、2 调用、零诊断。"""
    gem = _det_entity_id("gem")
    fake = FakeInferenceBackend(
        script={
            ("world_dynamics", Revision(0), 1): "the model is still thinking about the gem",
            ("world_dynamics", Revision(0), 2): scripted_wire_response,
        }
    )
    driver = _driver(fake)
    effects = driver.simulate(
        _snapshot(make_p7_world()),
        (stim_support_removed,),
        DynamicsContext(base_revision=0),
    )
    assert len(effects) == 1
    effect = effects[0]
    assert effect.effect_type == "gem.moved"
    assert effect.target.entity_id == gem
    assert effect.source == "llm_world_dynamics"
    assert effect.payload == {}
    assert effect.base_revision == 0
    assert effect.cause_ids == []
    assert len(fake.calls) == 2
    assert driver.diagnostics == ()


def test_llm_parse_failure_twice_diagnostic(stim_support_removed) -> None:
    """t6：seq1 无花括号散文 + seq2 ``{not json}``（json_invalid 层）→ 终败诊断面（P4/P5/P6/P7）。"""
    fake = FakeInferenceBackend(
        script={
            ("world_dynamics", Revision(0), 1): "the model is still thinking about the gem",
            ("world_dynamics", Revision(0), 2): "{not json",
        }
    )
    driver = _driver(fake)
    effects = driver.simulate(
        _snapshot(make_p7_world()),
        (stim_support_removed,),
        DynamicsContext(base_revision=0),
    )
    assert effects == ()
    assert len(fake.calls) == 2
    assert len(driver.diagnostics) == 1
    diag = driver.diagnostics[0]
    assert diag.code == "p7.wire_parse_failed"
    assert diag.severity == DiagnosticSeverity.ERROR
    assert diag.path == "llm_world_dynamics"
    assert diag.refs[0].startswith("elapsed_ms=")


def test_llm_wire_extra_forbid() -> None:
    """t7：wire 模型多余键拒绝（effect / proposal 两层）+ JSON-clean 面（set 值拒）。"""
    with pytest.raises(ValidationError):
        DynamicsEffectWire(
            effect_type="gem.moved", entity_id="ent_x", authority_scope=True
        )
    with pytest.raises(ValidationError):
        DynamicsProposalWire.model_validate_json(
            '{"effects": [], "reasoning": "r", "authority": "all"}'
        )
    with pytest.raises(ValidationError):
        DynamicsEffectWire(
            effect_type="gem.moved", entity_id="ent_x", payload={"k": {1, 2, 3}}
        )


def test_llm_wire_bad_effect_type_lexical() -> None:
    """t8：``effect_type="GEM MOVED"`` 词法违规拒绝；对照 ``"gem.moved"`` 构造成功。"""
    with pytest.raises(ValidationError):
        DynamicsEffectWire(effect_type="GEM MOVED", entity_id="ent_x")
    good = DynamicsEffectWire(effect_type="gem.moved", entity_id="ent_x")
    assert good.effect_type == "gem.moved"


def test_llm_budget_zero_exhausted(stim_support_removed) -> None:
    """t9：预算 ``max_calls=0`` → 空元组 + 恰 1 条 ``p7.budget_exhausted`` + 零调用。"""
    fake = FakeInferenceBackend()
    driver = _driver(fake)
    effects = driver.simulate(
        _snapshot(make_p7_world()),
        (stim_support_removed,),
        DynamicsContext(base_revision=0, budget=InferenceBudget(max_calls=0)),
    )
    assert effects == ()
    assert len(driver.diagnostics) == 1
    diag = driver.diagnostics[0]
    assert diag.code == "p7.budget_exhausted"
    assert diag.severity == DiagnosticSeverity.ERROR
    assert diag.path == "llm_world_dynamics"
    assert fake.calls == ()


def test_llm_metadata() -> None:
    """t10：``metadata()`` 9 字段逐项钉死（config 缺省面）。"""
    driver = _driver(FakeInferenceBackend())
    meta = driver.metadata()
    assert meta.backend_id == "llm_world_dynamics"
    assert meta.producer_id == "llm_world_dynamics"
    assert meta.domains == ()
    assert meta.determinism == "nondeterministic"
    assert meta.implementation_type == "inference"
    assert meta.fidelity == "semantic"
    assert meta.checkpointable is True
    assert meta.restorable is True
    assert meta.replayable is False


def test_llm_double_run_byte_identical_scripted(
    scripted_wire_response: str, stim_support_removed
) -> None:
    """t11（A16）：两全独立装配（新 fake/driver/context/world ×2，stim 单例）→ 双跑 byte-identical。"""

    def run_once():
        fake = FakeInferenceBackend(
            script={("world_dynamics", Revision(0), 1): scripted_wire_response}
        )
        driver = _driver(fake)
        effects = driver.simulate(
            _snapshot(make_p7_world()),
            (stim_support_removed,),
            DynamicsContext(base_revision=0),
        )
        assert len(effects) == 1
        return _effects_json(effects), fake.calls[0].messages[0].content

    effects_a, content_a = run_once()
    effects_b, content_b = run_once()
    assert effects_a == effects_b
    assert content_a == content_b


def test_llm_l0_contract_k4_clause(
    scripted_wire_response: str, stim_support_removed
) -> None:
    """t12：L0 常量含逐字 K4 条款 + sha256 机械钉死 + 实发 prompt content 含该条款。"""
    assert _L0_K4_CLAUSE in DYNAMICS_L0_CONTRACT
    assert hashlib.sha256(DYNAMICS_L0_CONTRACT.encode("utf-8")).hexdigest() == (
        "a7875d80f484a6356015c7ddb94a194083656edceb97016ba7020e336879de84"
    )
    fake = FakeInferenceBackend(
        script={("world_dynamics", Revision(0), 1): scripted_wire_response}
    )
    _driver(fake).simulate(
        _snapshot(make_p7_world()),
        (stim_support_removed,),
        DynamicsContext(base_revision=0),
    )
    content = fake.calls[0].messages[0].content
    assert _L0_K4_CLAUSE in content


def test_llm_canonical_world_facts_stable(stim_support_removed) -> None:
    """t13：测试内重算期望 L1 facts（P1 形状）canonical JSON ⊆ 实发 content；双装配相等；改世界面必变（负例）。"""
    world = make_p7_world()
    gem = _det_entity_id("gem")
    expected_l1 = {
        "entities": {
            str(gem): {
                "components": {
                    "rigid": {"acc": 0.0, "pos": 0.0, "vel": 0.0},
                    "gem_state": {"moved": False},
                }
            }
        },
        "world_variables": {"gravity": 9.8, "support": "present"},
    }
    l1_json = json.dumps(
        expected_l1, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )

    def run_once(world_state: WorldState) -> str:
        fake = FakeInferenceBackend()
        _driver(fake).simulate(
            _snapshot(world_state),
            (stim_support_removed,),
            DynamicsContext(base_revision=0),
        )
        return fake.calls[0].messages[0].content

    content_a = run_once(world)
    assert l1_json in content_a
    content_b = run_once(world)
    assert content_a == content_b
    mutated = world.model_copy(
        update={"world_variables": {**world.world_variables, "magic": 3.14}}
    )
    content_c = run_once(mutated)
    assert content_c != content_a


def test_llm_diagnostics_last_run_reset(
    scripted_wire_response: str, stim_support_removed
) -> None:
    """t14（D-P7-15）：同实例 run A 预算 0 诊断 → run B 成功后 ``diagnostics == ()``（last-run 视图）。"""
    fake = FakeInferenceBackend(
        script={("world_dynamics", Revision(0), 1): scripted_wire_response}
    )
    driver = _driver(fake)
    run_a = driver.simulate(
        _snapshot(make_p7_world()),
        (stim_support_removed,),
        DynamicsContext(base_revision=0, budget=InferenceBudget(max_calls=0)),
    )
    assert run_a == ()
    assert len(driver.diagnostics) == 1
    assert driver.diagnostics[0].code == "p7.budget_exhausted"
    run_b = driver.simulate(
        _snapshot(make_p7_world()),
        (stim_support_removed,),
        DynamicsContext(base_revision=0),
    )
    assert len(run_b) == 1
    assert driver.diagnostics == ()
