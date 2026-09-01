"""P8 T03 replay 引擎测试（SOT §6.1 t1–t13；SC-1 结构 + SC-2 动力学 flavor）。

钉死面（§6.1 表逐项对应）：

- t1 SC-1 结构 replay 终态相等 + A4 双跑字节一致；
- t2 SC-2：注入 P7 ``gem_effect_handlers()``（测试侧）→ 语义 replay 终态
  相等（D-P7-13 评估锚）；
- t3 A21：ABORTED 事务不驱动状态；
- t4 空 trace → 原样、计数 0；
- t5 首笔 base ≠ 当前 → ``ReplayError``（message 含两侧 revision，A16）；
- t6 同 commit_revision 两笔 → ``ReplayError``；
- t7 未注册语义型（registry 未注册）→ ``ReplayError``（wrap
  ``ReducerError``，不静默跳过）；
- t8 ``result.events`` ids/序 == 管道 events；
- t9 非 TRANSACTION 记录不驱动状态；
- t10 ``to_dict`` JSON-clean；
- t11 字段名闭集（6 字段 + ``to_dict``）；
- t12 ``replay.py`` AST：无 ``open`` / ``os`` / ``pathlib``（D4）；
- t13 输入 state replay 后 dump 不变（零别名）。

纪律：扁平函数（零 class / 零 subprocess / 零跨函数状态，P7 §6.1 同族）；
确定性（D6：同一双跑字节一致，A4）。
"""

from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path

import pytest

from src.engine_v2.core import (
    DomainEvent,
    PAYLOAD_RECORD_KEY,
    ProducerId,
    Revision,
    TraceKind,
    TraceRecord,
    TraceRecordId,
    Transaction,
    TransactionId,
    TransactionStatus,
    assert_json_clean,
)
from src.engine_v2.persistence.replay import ReplayError, ReplayResult, replay_committed
from tests.engine_v2.persistence.conftest import (
    build_p8_dynamics_save,
    make_p8_backend,
    make_p8_world,
    run_p8_script,
)

def _transaction_records(run) -> tuple[TraceRecord, ...]:
    """SC-1 trace 中 TRANSACTION 记录子序列（文件序保序）。"""
    return tuple(r for r in run.trace_records if r.kind is TraceKind.TRANSACTION)


def test_replay_reconstructs_committed_state() -> None:
    """t1：SC-1 结构 replay 终态相等（K2 同面）+ A4 双跑字节一致。"""
    run = run_p8_script()
    result = replay_committed(make_p8_world(), run.trace_records)
    assert result.final_state == run.final_state
    assert result.base_revision == 0
    assert result.final_revision == 3
    assert result.transactions_applied == 3
    # 恒等：final == base + transactions_applied（§8.3）
    assert result.final_revision == result.base_revision + result.transactions_applied
    assert len(result.applied_transaction_ids) == 3
    # A4：同一 (world_state, trace_records, handlers) 双跑字节一致
    second = replay_committed(make_p8_world(), run.trace_records)
    assert json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True) == json.dumps(
        second.to_dict(), ensure_ascii=False, sort_keys=True
    )


def test_replay_dynamics_flavor_semantic_handler(tmp_path: Path) -> None:
    """t2：SC-2 动力学 flavor——注入 P7 语义 handler（测试侧）→ 终态相等。

    save 面经 ``build_p8_dynamics_save`` 落盘 + ``load`` 回读（与正常管道
    同 trace 面）；初始世界 = P7 夹具 ``make_p7_world()``（SC-2 管道起态）。
    """
    from tests.engine_v2.dynamics.conftest import (
        gem_effect_handlers,
        make_p7_component_registry,
        make_p7_world,
    )

    build_p8_dynamics_save(tmp_path)
    bundle = make_p8_backend(tmp_path).load(save_id="save_p8_dyn")
    initial = make_p7_world()
    handlers = gem_effect_handlers()
    component_registry = make_p7_component_registry()
    result = replay_committed(
        initial,
        bundle.trace_records,
        handlers=handlers,
        component_registry=component_registry,
    )
    assert result.final_state == bundle.envelope.snapshot.world_state
    assert result.base_revision == 0
    assert result.final_revision == 1
    assert result.transactions_applied == 1
    # A4 双跑字节一致（语义 handler 面）
    second = replay_committed(
        initial,
        bundle.trace_records,
        handlers=handlers,
        component_registry=component_registry,
    )
    assert json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True) == json.dumps(
        second.to_dict(), ensure_ascii=False, sort_keys=True
    )


def test_replay_skips_aborted_transactions() -> None:
    """t3（A21）：ABORTED 事务不驱动状态（审计存在性由 trace 面保留）。"""
    run = run_p8_script()
    aborted = Transaction(
        transaction_id=TransactionId("txn_p8_aborted_1"),
        status=TransactionStatus.ABORTED,
        base_revision=Revision(1),
        abort_reason="validation_failed",
    )
    record = TraceRecord(
        record_id=TraceRecordId("trc_p8_aborted_1"),
        kind=TraceKind.TRANSACTION,
        world_revision=Revision(1),
        logical_tick=3,
        producer_id=ProducerId("p8.rule"),
        payload={PAYLOAD_RECORD_KEY: aborted.model_dump(mode="json")},
    )
    result = replay_committed(make_p8_world(), (*run.trace_records, record))
    assert result.final_state == run.final_state
    assert result.transactions_applied == 3
    assert "txn_p8_aborted_1" not in result.applied_transaction_ids
    # ABORTED 无事件（原子失败：event_ids 空）——事件面与纯 SC-1 相同
    baseline = replay_committed(make_p8_world(), run.trace_records)
    assert [str(e.event_id) for e in result.events] == [
        str(e.event_id) for e in baseline.events
    ]
    assert len(result.events) == 3


def test_replay_empty_trace_noop() -> None:
    """t4：空 trace → 原样（输入状态对象本身）、计数 0。"""
    world = make_p8_world()
    result = replay_committed(world, ())
    assert result.final_state is world
    assert result.base_revision == 0
    assert result.final_revision == 0
    assert result.transactions_applied == 0
    assert result.applied_transaction_ids == ()
    assert result.events == ()


def test_replay_base_revision_mismatch_raises() -> None:
    """t5（A16）：首笔 base ≠ 当前 world_revision → ``ReplayError``。

    message 含两侧 revision（AD-4 面）：从回 2 起放（base_revision=1）对
    revision 0 的初始世界。
    """
    run = run_p8_script()
    tail = _transaction_records(run)[1:]
    assert len(tail) == 2
    with pytest.raises(ReplayError) as excinfo:
        replay_committed(make_p8_world(), tail)
    assert excinfo.value.code == "replay_mismatch"
    message = str(excinfo.value)
    assert "base_revision=1" in message
    assert "world_revision=0" in message


def test_replay_duplicate_revision_raises() -> None:
    """t6：同 commit_revision 两笔 COMMITTED → ``ReplayError``。

    同一事务体以第二 record_id 再呈一次：``(record_id, transaction_id)``
    对去重通过（对不重复），revision 唯一性门命中（commit_revision=1 ×2）。
    """
    run = run_p8_script()
    first = _transaction_records(run)[0]
    duplicate = TraceRecord(
        record_id=TraceRecordId("trc_p8_dup_rev_1"),
        kind=TraceKind.TRANSACTION,
        world_revision=first.world_revision,
        logical_tick=first.logical_tick,
        producer_id=first.producer_id,
        transaction_id=first.transaction_id,
        cascade_id=first.cascade_id,
        payload=first.payload,
    )
    with pytest.raises(ReplayError) as excinfo:
        replay_committed(make_p8_world(), (*run.trace_records, duplicate))
    assert excinfo.value.code == "replay_mismatch"
    assert "commit_revision" in str(excinfo.value)


def test_replay_unknown_effect_type_raises(tmp_path: Path) -> None:
    """t7：未注册语义型（默认 registry 无 ``gem.moved``）→ ``ReplayError``。

    wrap ``ReducerError``（不静默跳过，AD-5 面）；SC-2 trace 的
    ``gem.moved`` 效果在默认结构 registry 下无 handler 可解析。
    """
    from tests.engine_v2.dynamics.conftest import make_p7_world

    build_p8_dynamics_save(tmp_path)
    bundle = make_p8_backend(tmp_path).load(save_id="save_p8_dyn")
    with pytest.raises(ReplayError) as excinfo:
        replay_committed(make_p7_world(), bundle.trace_records)
    assert excinfo.value.code == "replay_mismatch"
    message = str(excinfo.value)
    assert "未注册 effect_type" in message
    assert "gem.moved" in message


def test_replay_events_reconstructed_ordered() -> None:
    """t8：``result.events`` ids/序 == 管道 events（序 =
    ``(commit_revision, 事务内 event_ids 序)``）。"""
    run = run_p8_script()
    result = replay_committed(make_p8_world(), run.trace_records)
    pipeline_event_ids = [
        str(DomainEvent.model_validate(r.payload[PAYLOAD_RECORD_KEY]).event_id)
        for r in run.trace_records
        if r.kind is TraceKind.DOMAIN_EVENT
    ]
    assert [str(event.event_id) for event in result.events] == pipeline_event_ids
    assert len(result.events) == 3
    # 序钉死：SC-1 每笔恰 1 事件，序 == commit_revision 升序
    assert [int(event.world_revision) for event in result.events] == [1, 2, 3]


def test_replay_ignores_non_transaction_kinds() -> None:
    """t9：非 TRANSACTION 记录不驱动状态（计数 0 / 终态 = 初始）。"""
    run = run_p8_script()
    non_transaction = tuple(
        r for r in run.trace_records if r.kind is not TraceKind.TRANSACTION
    )
    # SC-1 trace 确含非事务记录（dev_intervention / authority /
    # validation / domain_event 族）——防空集假阳性
    assert non_transaction
    assert any(r.kind is TraceKind.DOMAIN_EVENT for r in non_transaction)
    result = replay_committed(make_p8_world(), non_transaction)
    assert result.transactions_applied == 0
    assert result.final_revision == 0
    assert result.final_state == make_p8_world()
    # 未应用事务的事件不重建（transaction_id ∉ 应用集）
    assert result.events == ()


def test_replay_result_to_dict_json_clean() -> None:
    """t10：``to_dict`` JSON-clean（D3 断言面）。"""
    run = run_p8_script()
    result = replay_committed(make_p8_world(), run.trace_records)
    payload = result.to_dict()
    assert isinstance(payload["final_state"], dict)
    assert payload["base_revision"] == 0
    assert payload["final_revision"] == 3
    assert payload["transactions_applied"] == 3
    assert len(payload["applied_transaction_ids"]) == 3
    assert len(payload["events"]) == 3
    assert_json_clean(payload)
    # 可 JSON 序列化（json.dumps 不抛 = 面级证明）
    json.dumps(payload, ensure_ascii=False, sort_keys=True)


def test_replay_result_fields_exact() -> None:
    """t11：字段名闭集（6 字段 + ``to_dict``；frozen）。"""
    field_names = {field.name for field in dataclasses.fields(ReplayResult)}
    assert field_names == {
        "final_state",
        "base_revision",
        "final_revision",
        "transactions_applied",
        "applied_transaction_ids",
        "events",
    }
    assert callable(ReplayResult.to_dict)
    run = run_p8_script()
    result = replay_committed(make_p8_world(), run.trace_records)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.transactions_applied = 0  # type: ignore[misc]


def test_replay_zero_io_ast() -> None:
    """t12（D4）：``replay.py`` AST 无 ``open`` / ``os`` / ``pathlib`` 引用。"""
    module_path = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "engine_v2"
        / "persistence"
        / "replay.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    forbidden = {"open", "os", "pathlib"}
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in forbidden:
            hits.append(f"Name {node.id} @ L{node.lineno}")
        elif isinstance(node, ast.Attribute) and node.attr in forbidden:
            hits.append(f"Attribute {node.attr} @ L{node.lineno}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in forbidden:
                    hits.append(f"Import {alias.name} @ L{node.lineno}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in forbidden:
                hits.append(f"ImportFrom {node.module} @ L{node.lineno}")
    assert not hits, hits


def test_replay_base_state_untouched() -> None:
    """t13：输入 state replay 后 dump 不变（零别名，K7）。"""
    world = make_p8_world()
    before = json.dumps(world.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    run = run_p8_script()
    result = replay_committed(world, run.trace_records)
    after = json.dumps(world.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    assert before == after
    assert world.world_revision == 0
    # 终态与输入零别名（新状态对象）
    assert result.final_state is not world
