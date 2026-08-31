"""P7-W4 test_host_driver.py（SOT §6.1 t1–t10 逐文件编号，10 平铺函数，零
test class）。

契约面：host driver ``run_dynamics_turn``（SOT §3.8，D-P7-09；P7 自持组装
点）——S1 规则 turn 提交面（t1）/ 事件 1:1 派发（t2）/ K6 origin
DYNAMICS_BACKEND 贯穿（t3）/ state 纯函数不被触碰（t4）/ S7 rogue 权限
拒绝零变更（t5，P6 装配）/ 空 effects 无事务（t6）/ DynamicsTurn frozen +
summary JSON-clean 三键面（t7，P5 钉死）/ S8 Case A 端到端（t8，S3 输入 +
A7 单规则并集 policy）/ causal_root 贯穿（t9，P4 钉死）/ 双独立装配
summary byte-identical（t10，K7 host 面；uuid4 原始值按 D-P3-15①/② 前缀 +
位置同构投影，不跨运行比原始值）。

通用装配（P8/P4 钉死）：state = ``make_p7_world()``；snapshot = 本地
``_snapshot``（``world_instance_id`` 定死字面量）；context =
``DynamicsContext(base_revision=0)``；executor = ``make_p7_executor()``；
``causal_root_id = "turn_p7_case_a"``；origin = host 构造
（producer = 本 turn backend 的 producer id，``OriginKind.DYNAMICS_BACKEND``）。
"""

from __future__ import annotations

import json
import re
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from src.engine_v2.core.authority import AuthorityPolicy, AuthorityRule, AuthoritySelector
from src.engine_v2.core.cascade import CascadeExecutor
from src.engine_v2.core.ids import ProducerId
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.reducer import uninstall_write_barrier
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.serialization import assert_json_clean
from src.engine_v2.core.state import WorldState
from src.engine_v2.core.transaction import TransactionStatus
from src.engine_v2.dynamics.authority import default_dynamics_policy
from src.engine_v2.dynamics.backend import DynamicsContext, WorldSnapshot, _FixedMonotonicClock
from src.engine_v2.dynamics.host import DynamicsTurn, run_dynamics_turn
from src.engine_v2.dynamics.llm_world import LLMWorldDynamics, LLMWorldDynamicsConfig
from src.engine_v2.dynamics.rule import RuleDynamics, WorldRule
from src.engine_v2.llm.adapter import FakeInferenceBackend
from tests.engine_v2.dynamics.conftest import (
    _det_entity_id,
    gem_effect_handlers,
    make_p7_component_registry,
    make_p7_executor,
    make_p7_producer_registry,
    make_p7_world,
)

_WSI = "wsi_p7_host_driver_test"

_CAUSAL_ROOT_ID = "turn_p7_case_a"

#: D-P3-15①/②：core 冻结 ID 工厂（ids.py L227–244）为 uuid4 面——原始值不跨
#: 运行比较（数量/运行内唯一性/前缀/位置同构）；确定性面（eff_/ent_/wsi_）
#: 不在此列，跨运行 raw byte 比较。
_UUID4_ID_RE = re.compile(r"(?:txn|evt|csc|trc)_[0-9a-f]{32}")
_UUID4_PREFIXES = ("txn", "evt", "csc", "trc")


@pytest.fixture(autouse=True)
def _barrier_isolation() -> None:
    """写屏障 opt-in 纪律（core §2.6.2；test_scheduler._barrier_isolation /
    core conftest ``p3_barrier_isolation`` 同款 autouse 口径）：每用例前后全局
    复原为未武装态，不跨文件受染——``CascadeExecutor.__init__`` 构造期武装
    屏障，冻结 W3 推理测试的 ``model_copy`` 负例依赖未武装态。
    """
    uninstall_write_barrier()
    yield
    uninstall_write_barrier()


def _snapshot(world: WorldState) -> WorldSnapshot:
    """``WorldSnapshot`` 直构（host 测试不需要完整 core Snapshot 信封）。"""
    return WorldSnapshot(
        world_state=world,
        world_revision=world.world_revision,
        logical_tick=0,
        world_instance_id=_WSI,
    )


def _gem_state_moved(state: WorldState) -> bool:
    """final_state 面读取：gem 实体 gem_state.moved（t1/t8 handler 落点断言）。"""
    return state.entities[_det_entity_id("gem")].components["gem_state"]["moved"] is True


def _s1_rule_on_gem_state() -> WorldRule:
    """S1 条件（gravity==9.8）+ emit gem.fell 于 gem_state 组件。

    注：SOT §5.1 S1 行目标 = 整实体；host 通用装配的 ``make_p7_policy()``
    为组件级 selector 声明（rigid/gem_state），冻结 core ``match_selector``
    语义下整实体 target 不匹配组件级 selector（→ no_matching_rule DENY），
    故 host 侧规则目标钉死 gem_state（S1 条件/effect_type/payload 逐字不变）
    ——交付报告偏差清单申报。
    """
    return WorldRule(
        rule_id="r_gravity",
        when={"world_variable_equals": {"key": "gravity", "value": 9.8}},
        emit_effect_type="gem.fell",
        emit_target_entity=str(_det_entity_id("gem")),
        emit_component_type="gem_state",
        emit_field_path=None,
        emit_payload={"moved": True},
    )


def _run_rule_turn(
    *,
    rules: tuple[WorldRule, ...],
    producer_id: str,
    state: WorldState | None = None,
    executor: CascadeExecutor | None = None,
    causal_root_id: str = _CAUSAL_ROOT_ID,
) -> DynamicsTurn:
    """规则系 turn 通用装配（P4 origin 钉死：producer = 本 turn backend producer）。"""
    world = state if state is not None else make_p7_world()
    backend = RuleDynamics(rules=rules, producer_id=producer_id)
    origin = Provenance(
        producer_id=ProducerId(producer_id),
        origin=OriginKind.DYNAMICS_BACKEND,
    )
    return run_dynamics_turn(
        backend=backend,
        snapshot=_snapshot(world),
        stimuli=(),
        context=DynamicsContext(base_revision=0),
        state=world,
        executor=executor if executor is not None else make_p7_executor(),
        causal_root_id=causal_root_id,
        origin=origin,
    )


def _rule_turn(state: WorldState | None = None, executor: CascadeExecutor | None = None) -> DynamicsTurn:
    """S1 规则 turn（t1–t4/t6/t7/t9/t10 缺省装配）。"""
    return _run_rule_turn(
        rules=(_s1_rule_on_gem_state(),),
        producer_id="rule_dynamics",
        state=state,
        executor=executor,
    )


def _state_json(state: WorldState) -> str:
    """世界状态 canonical JSON（纯函数比较面）。"""
    return json.dumps(
        state.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _uuid4_prefix_tokens(summary: dict[str, Any]) -> dict[str, list[str]]:
    """按前缀收集 summary 中全部 uuid4 形态 ID 原始 token（D-P3-15① 计数面）。"""
    found: dict[str, list[str]] = {prefix: [] for prefix in _UUID4_PREFIXES}

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for child in value.values():
                _walk(child)
        elif isinstance(value, list):
            for child in value:
                _walk(child)
        elif isinstance(value, str) and _UUID4_ID_RE.fullmatch(value) is not None:
            found[value.split("_", 1)[0]].append(value)

    _walk(summary)
    return found


def _normalize_cross_run(value: Any, counters: dict[str, int]) -> Any:
    """D-P3-15①/② 跨运行投影：uuid4 原始值 → 前缀 + 位置同构占位符；
    ``wall_time`` 值 → 占位（P9：不比较、不钉值；冻结 cascade 实证恒 None）。"""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, child in value.items():
            if key == "wall_time":
                out[key] = "WALL_TIME" if child is not None else None
            else:
                out[key] = _normalize_cross_run(child, counters)
        return out
    if isinstance(value, list):
        return [_normalize_cross_run(child, counters) for child in value]
    if isinstance(value, str) and _UUID4_ID_RE.fullmatch(value) is not None:
        prefix = value.split("_", 1)[0]
        counters[prefix] = counters.get(prefix, 0) + 1
        return f"{prefix}#{counters[prefix]}"
    return value


def _cross_run_json(summary: dict[str, Any]) -> str:
    """跨运行 canonical JSON（sort_keys；K7 host 面字节比较面）。"""
    return json.dumps(
        _normalize_cross_run(summary, {}),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def test_turn_happy_path_commit() -> None:
    """t1：S1 规则 turn → effects 恰 1；transactions 恰 1 COMMITTED；revision = base+1；gem_state.moved=True（经 handler）。"""
    turn = _rule_turn()
    assert len(turn.effects) == 1
    assert turn.effects[0].effect_type == "gem.fell"
    assert turn.effects[0].source == "rule_dynamics"
    assert len(turn.result.transactions) == 1
    assert turn.result.transactions[0].status == TransactionStatus.COMMITTED
    assert turn.result.final_state.world_revision == 1
    assert _gem_state_moved(turn.result.final_state)
    assert turn.result.deferred == ()


def test_turn_events_one_to_one() -> None:
    """t2：1:1 派发——len(events) == COMMITTED 事务 effects 总数；event.transaction_id 与 tx.event_ids 双向 1:1。"""
    turn = _rule_turn()
    committed = [
        tx for tx in turn.result.transactions if tx.status == TransactionStatus.COMMITTED
    ]
    committed_effect_count = sum(len(tx.effects) for tx in committed)
    assert committed_effect_count == 1
    assert len(turn.result.events) == committed_effect_count
    event = turn.result.events[0]
    assert event.transaction_id == committed[0].transaction_id
    assert tuple(committed[0].event_ids) == (event.event_id,)
    assert str(event.cause_ids[0].ref_id) == turn.effects[0].effect_id


def test_turn_origin_dynamics_backend() -> None:
    """t3：K6——每 COMMITTED 事务 + 每事件 provenance.origin = DYNAMICS_BACKEND（host 构造 origin 贯穿）。"""
    turn = _rule_turn()
    committed = [
        tx for tx in turn.result.transactions if tx.status == TransactionStatus.COMMITTED
    ]
    assert len(committed) == 1
    assert committed[0].provenance.origin == OriginKind.DYNAMICS_BACKEND
    assert str(committed[0].provenance.producer_id) == "rule_dynamics"
    assert len(turn.result.events) == 1
    assert turn.result.events[0].provenance.origin == OriginKind.DYNAMICS_BACKEND
    assert str(turn.result.events[0].provenance.producer_id) == "rule_dynamics"


def test_turn_state_not_mutated() -> None:
    """t4：turn 前后 state model_dump byte-identical（纯函数面——state 不被触碰）+ 输入 revision 不变。"""
    world = make_p7_world()
    before = _state_json(world)
    turn = _rule_turn(state=world)
    after = _state_json(world)
    assert before == after
    assert world.world_revision == 0
    assert turn.result.final_state.world_revision == 1


def test_turn_authority_deny_no_change() -> None:
    """t5：S7 面——P6 装配（rogue producer + gem_state 未声明）→ effects 恰 1（backend 产出）但零事务、零状态变更、backend 零诊断。"""
    policy = default_dynamics_policy(component_types=("rigid",))
    executor = CascadeExecutor(
        policy=policy,
        component_registry=make_p7_component_registry(),
        producer_registry=make_p7_producer_registry(),
        handlers=gem_effect_handlers(),
    )
    rogue_rule = WorldRule(
        rule_id="r_rogue",
        when={"world_variable_equals": {"key": "gravity", "value": 9.8}},
        emit_effect_type="gem.moved",
        emit_target_entity=str(_det_entity_id("gem")),
        emit_component_type="gem_state",
        emit_field_path=None,
        emit_payload={"moved": True},
    )
    world = make_p7_world()
    before = _state_json(world)
    turn = _run_rule_turn(
        rules=(rogue_rule,),
        producer_id="rogue",
        state=world,
        executor=executor,
    )
    assert len(turn.effects) == 1
    assert turn.effects[0].source == "rogue"
    assert turn.result.transactions == ()
    assert turn.result.events == ()
    assert turn.result.final_state.world_revision == 0
    assert _state_json(turn.result.final_state) == before
    assert _state_json(world) == before
    assert turn.diagnostics == ()


def test_turn_empty_effects_no_transactions() -> None:
    """t6：规则不命中（support=="absent" ≠ 世界 "present"）→ effects () + transactions () + events () + revision 不变。"""
    miss_rule = WorldRule(
        rule_id="r_miss",
        when={"world_variable_equals": {"key": "support", "value": "absent"}},
        emit_effect_type="gem.fell",
        emit_target_entity=str(_det_entity_id("gem")),
        emit_component_type="gem_state",
        emit_field_path=None,
        emit_payload={"moved": True},
    )
    world = make_p7_world()
    turn = _run_rule_turn(
        rules=(miss_rule,),
        producer_id="rule_dynamics",
        state=world,
    )
    assert turn.effects == ()
    assert turn.result.transactions == ()
    assert turn.result.events == ()
    assert turn.result.final_state.world_revision == 0
    assert turn.result.deferred == ()
    assert turn.diagnostics == ()


def test_turn_frozen_summary_json_clean() -> None:
    """t7：DynamicsTurn frozen（改字段 → FrozenInstanceError）；summary_dict 顶层 3 键 + result 6 键；assert_json_clean 过；同 turn 双 summary 确定性（同输入同 dict）。"""
    turn = _rule_turn()
    with pytest.raises(FrozenInstanceError):
        turn.effects = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        turn.diagnostics = turn.diagnostics  # type: ignore[misc]
    summary = turn.summary_dict()
    assert set(summary.keys()) == {"effects", "result", "diagnostics"}
    assert set(summary["result"].keys()) == {
        "final_state",
        "transactions",
        "events",
        "trace_records",
        "deferred",
        "diagnostics",
    }
    assert_json_clean(summary)
    summary_again = turn.summary_dict()
    assert json.dumps(summary, sort_keys=True, ensure_ascii=False) == json.dumps(
        summary_again, sort_keys=True, ensure_ascii=False
    )


def test_turn_case_a_end_to_end(
    scripted_wire_response: str, stim_support_removed
) -> None:
    """t8：S8——scripted 推理（S3 wire，S3 输入）经 ``run_dynamics_turn`` → revision+1、1 COMMITTED、事件 1:1、origin DYNAMICS_BACKEND；effects 恰 1 gem.moved（A1–A4 面）。"""
    world = make_p7_world()
    fake = FakeInferenceBackend(
        script={("world_dynamics", Revision(0), 1): scripted_wire_response}
    )
    backend = LLMWorldDynamics(
        backend=fake,
        config=LLMWorldDynamicsConfig(
            capability_id="world_dynamics", prompt_ref="prompt://p7/gem"
        ),
        clock=_FixedMonotonicClock(),
    )
    # A7 弃权序 policy（SOT §3.7 引文块"单条 priority=100 规则"形态）：S3 wire
    # 整实体 target 在组件级 selector 下不匹配（冻结 core match_selector 语义），
    # S8 钉死面（1 COMMITTED / rule_allow）要求通配单规则并集放行——交付报告
    # 偏差清单申报。
    policy = AuthorityPolicy(
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
    executor = CascadeExecutor(
        policy=policy,
        component_registry=make_p7_component_registry(),
        producer_registry=make_p7_producer_registry(),
        handlers=gem_effect_handlers(),
    )
    origin = Provenance(
        producer_id=ProducerId("llm_world_dynamics"),
        origin=OriginKind.DYNAMICS_BACKEND,
    )
    turn = run_dynamics_turn(
        backend=backend,
        snapshot=_snapshot(world),
        stimuli=(stim_support_removed,),
        context=DynamicsContext(base_revision=0),
        state=world,
        executor=executor,
        causal_root_id=_CAUSAL_ROOT_ID,
        origin=origin,
    )
    assert len(turn.effects) == 1
    assert turn.effects[0].effect_type == "gem.moved"
    assert turn.effects[0].source == "llm_world_dynamics"
    assert turn.effects[0].target.component_type is None
    assert turn.effects[0].cause_ids == []
    committed = [
        tx for tx in turn.result.transactions if tx.status == TransactionStatus.COMMITTED
    ]
    assert len(turn.result.transactions) == 1
    assert len(committed) == 1
    assert turn.result.final_state.world_revision == 1
    assert len(turn.result.events) == 1
    assert committed[0].provenance.origin == OriginKind.DYNAMICS_BACKEND
    assert turn.result.events[0].provenance.origin == OriginKind.DYNAMICS_BACKEND
    assert _gem_state_moved(turn.result.final_state)
    assert turn.result.deferred == ()
    assert len(fake.calls) == 1


def test_turn_causal_root_in_events() -> None:
    """t9：``causal_root_id="turn_p7_case_a"`` 贯穿——每 COMMITTED tx.cascade.causal_root_id + 每 event.cascade.causal_root_id 逐字。"""
    turn = _rule_turn()
    committed = [
        tx for tx in turn.result.transactions if tx.status == TransactionStatus.COMMITTED
    ]
    assert len(committed) == 1
    assert committed[0].cascade is not None
    assert committed[0].cascade.causal_root_id == "turn_p7_case_a"
    assert len(turn.result.events) == 1
    assert turn.result.events[0].cascade is not None
    assert turn.result.events[0].cascade.causal_root_id == "turn_p7_case_a"
    assert turn.result.events[0].cascade.cascade_id == committed[0].cascade.cascade_id


def test_turn_double_run_byte_identical() -> None:
    """t10：两全独立装配（新 executor 面同参、world×2）→ summary_dict() 全量 JSON byte-identical（K7 host 面；uuid4 原始值按 D-P3-15①/② 前缀 + 位置同构投影，确定性面 raw 比较）。"""
    turn_a = _rule_turn()
    turn_b = _rule_turn()
    summary_a = turn_a.summary_dict()
    summary_b = turn_b.summary_dict()
    assert _cross_run_json(summary_a) == _cross_run_json(summary_b)
    # 确定性面 raw byte 比较（零归一化）：effects（eff_ 确定性工厂）+ final_state
    assert json.dumps(
        summary_a["effects"], sort_keys=True, ensure_ascii=False
    ) == json.dumps(summary_b["effects"], sort_keys=True, ensure_ascii=False)
    assert json.dumps(
        summary_a["result"]["final_state"], sort_keys=True, ensure_ascii=False
    ) == json.dumps(
        summary_b["result"]["final_state"], sort_keys=True, ensure_ascii=False
    )
    # D-P3-15①/②：uuid4 面——跨运行计数一致（引用总数 + 唯一 ID 数，同 txn 可被
    # 多位置合法引用）+ 前缀集合一致
    tokens_a = _uuid4_prefix_tokens(summary_a)
    tokens_b = _uuid4_prefix_tokens(summary_b)
    assert set(tokens_a.keys()) == set(tokens_b.keys()) == set(_UUID4_PREFIXES)
    assert {prefix: len(ids) for prefix, ids in tokens_a.items()} == {
        prefix: len(ids) for prefix, ids in tokens_b.items()
    }
    assert {prefix: len(set(ids)) for prefix, ids in tokens_a.items()} == {
        prefix: len(set(ids)) for prefix, ids in tokens_b.items()
    }
