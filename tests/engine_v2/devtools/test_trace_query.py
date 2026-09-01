"""P8 T07 trace_query 面测试（SOT §6.1 t1–t12）。

钉死面（§6.1 表逐项对应）：

- t1 输入序保持（含反向输入序断言）；
- t2 kind 投影计数（全 kind 枚举投影 == 源流计数）；
- t3 ``domain_events()`` 解析字段与源记录一致；
- t4 全量事务（含 ABORTED 探针记录）/ COMMITTED 子集；
- t5 authority 决策行面 4 键 + payload 三键透传；
- t6 ``by_producer("p8.rule")`` 行面（SC-1 确定性计数 + kind 序）；
- t7 revision 时间线 4 行升序（kinds/计数/逻辑刻面）；
- t8 干预历史仅 ``DEV_INTERVENTION``（record_id 字面量钉死）；
- t9 合成 PROPOSAL/ACTION 因果 → ``action_refs`` 保序；
- t10 **A13**：SC-1 首个域事件因果链含 turn-1 干预
  ``trc_00000000000000000000000000000042``；
- t11 未知 ``event_id`` → ``TraceQueryError``（码 ``schema_invalid``）；
- t12 ``CausalChain.to_dict`` JSON-clean + ``trace_query.py`` 零 IO AST
  （D4）。

纪律：扁平函数（零 class / 零 subprocess / 零跨函数状态）；确定性（D6：
不钉 uuid 派生 id——SC-1 管线中仅干预 record_id / effect_id / command_id
为 host 字面量，事件 / 事务 / 其余记录 id 每跑一次变化，测试一律从运行
结果取）。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.engine_v2.core import (
    CauseKind,
    CauseRef,
    DomainEvent,
    OriginKind,
    PAYLOAD_RECORD_KEY,
    Provenance,
    TraceKind,
    TraceRecord,
    Transaction,
    TransactionStatus,
    assert_json_clean,
)
from src.engine_v2.devtools.trace_query import TraceQuery, TraceQueryError
from tests.engine_v2.devtools.conftest import run_p8_script

# —— record_id / event_id / id 字面量（K7 零 uuid4；host 给出，D6）——

_ABORTED_TXN_ID = "txn_p8_w4_aborted_1"
_ABORTED_RECORD_ID = "trc_p8_w4_aborted_1"
_PROBE_EVENT_ID = "evt_p8_w4_probe_1"
_PROBE_RECORD_ID = "trc_p8_w4_probe_1"
_UNKNOWN_EVENT_ID = "evt_p8_w4_unknown_1"
_PROPOSAL_REF = "action_p8_w4_probe_a"
_ACTION_REF = "action_p8_w4_probe_b"
_INTERVENTION_REF = "trc_p8_w4_probe_int_1"
_PROBE_PRODUCER = "p8.w4.test"


def _make_event_record(
    event_id: str,
    record_id: str,
    *,
    transaction_id: str | None = None,
    causes: tuple[CauseRef, ...] = (),
    source_system: str = _PROBE_PRODUCER,
) -> TraceRecord:
    """合成 ``DOMAIN_EVENT`` 记录（合法构造；零管线依赖）。"""
    event = DomainEvent(
        event_id=event_id,
        event_type="core.w4_probe",
        world_revision=0,
        logical_tick=1,
        transaction_id=transaction_id,
        payload={},
        cause_ids=list(causes),
        source_system=source_system,
        provenance=Provenance(producer_id=source_system, origin=OriginKind.RULE),
    )
    return TraceRecord(
        record_id=record_id,
        kind=TraceKind.DOMAIN_EVENT,
        world_revision=0,
        logical_tick=1,
        producer_id=source_system,
        transaction_id=transaction_id,
        payload={PAYLOAD_RECORD_KEY: event.model_dump(mode="json")},
    )


def test_query_records_preserve_input_order() -> None:
    """t1：``records()`` 输入序原样（正向 + 反向输入双断言）。"""
    run = run_p8_script()
    query = TraceQuery(run.trace_records)
    assert [r.record_id for r in query.records()] == [r.record_id for r in run.trace_records]
    reversed_query = TraceQuery(list(reversed(run.trace_records)))
    assert [r.record_id for r in reversed_query.records()] == [
        r.record_id for r in reversed(run.trace_records)
    ]


def test_by_kind_projection() -> None:
    """t2：全 kind 枚举投影计数 == 源流计数（SC-1 确定性计数钉死）。"""
    run = run_p8_script()
    query = TraceQuery(run.trace_records)
    assert len(query.records()) == len(run.trace_records) == 17
    kind_counts: dict[TraceKind, int] = {}
    for record in run.trace_records:
        kind_counts[record.kind] = kind_counts.get(record.kind, 0) + 1
    for kind in TraceKind:
        assert len(query.by_kind(kind)) == kind_counts.get(kind, 0)
    assert len(query.by_kind(TraceKind.DEV_INTERVENTION)) == 2
    assert len(query.by_kind(TraceKind.TRANSACTION)) == 3
    assert len(query.by_kind(TraceKind.DOMAIN_EVENT)) == 3


def test_domain_events_parsed() -> None:
    """t3：解析字段与源记录一致（event_id/type/transaction_id/revision）。"""
    run = run_p8_script()
    query = TraceQuery(run.trace_records)
    events = query.domain_events()
    records = [r for r in run.trace_records if r.kind is TraceKind.DOMAIN_EVENT]
    assert len(events) == len(records) == 3
    for event, record in zip(events, records):
        raw = record.payload[PAYLOAD_RECORD_KEY]
        assert event.event_id == raw["event_id"]
        assert event.event_type == raw["event_type"]
        assert event.transaction_id == record.transaction_id
        assert event.world_revision == record.world_revision
    assert events[0].event_type == "core.set_world_variable"


def test_transactions_and_committed_projection() -> None:
    """t4：全量（含 ABORTED 探针）/ COMMITTED 子集（SC-1 3 提交 + 1 探针）。"""
    run = run_p8_script()
    aborted = Transaction(
        transaction_id=_ABORTED_TXN_ID,
        status=TransactionStatus.ABORTED,
        base_revision=3,
        commit_revision=None,
        effects=[],
        event_ids=[],
        abort_reason="p8.w4 test probe",
    )
    probe = TraceRecord(
        record_id=_ABORTED_RECORD_ID,
        kind=TraceKind.TRANSACTION,
        world_revision=3,
        producer_id=_PROBE_PRODUCER,
        transaction_id=_ABORTED_TXN_ID,
        payload={PAYLOAD_RECORD_KEY: aborted.model_dump(mode="json")},
    )
    query = TraceQuery(list(run.trace_records) + [probe])
    txns = query.transactions()
    assert len(txns) == 4
    assert sum(1 for t in txns if t.status is TransactionStatus.ABORTED) == 1
    assert txns[-1].transaction_id == _ABORTED_TXN_ID
    committed = query.committed_transactions()
    assert len(committed) == 3
    assert all(t.status is TransactionStatus.COMMITTED for t in committed)


def test_authority_decisions_rows() -> None:
    """t5：行面 4 键 + payload = to_trace_payload() 三键原样透传（SC-1 共 3 行）。"""
    run = run_p8_script()
    query = TraceQuery(run.trace_records)
    rows = query.authority_decisions()
    assert len(rows) == 3
    for row in rows:
        assert set(row) == {"record_id", "world_revision", "producer_id", "payload"}
        assert isinstance(row["payload"], dict)
        assert set(row["payload"]) == {"effect_id", "decision", "reason"}
        assert isinstance(row["producer_id"], str) and row["producer_id"]


def test_producer_activity() -> None:
    """t6：``by_producer("p8.rule")``（SC-1 确定性 5 行 + kind 序钉死）。"""
    run = run_p8_script()
    query = TraceQuery(run.trace_records)
    rule = query.by_producer("p8.rule")
    assert len(rule) == 5
    assert all(r.producer_id == "p8.rule" for r in rule)
    assert [r.kind for r in rule] == [
        TraceKind.PROPOSED_EFFECT,
        TraceKind.AUTHORITY_DECISION,
        TraceKind.VALIDATION_DECISION,
        TraceKind.TRANSACTION,
        TraceKind.DOMAIN_EVENT,
    ]
    assert query.by_producer("nonexistent.producer") == ()


def test_revision_timeline_rows() -> None:
    """t7：4 行升序（kinds / 计数 / 逻辑刻 / wall_time 全 None）。"""
    run = run_p8_script()
    query = TraceQuery(run.trace_records)
    rows = query.revision_timeline()
    assert [r["world_revision"] for r in rows] == [0, 1, 2, 3]
    by_rev = {r["world_revision"]: r for r in rows}
    assert by_rev[0]["kinds"] == (
        "authority_decision",
        "dev_intervention",
        "proposed_effect",
        "validation_decision",
    )
    assert by_rev[0]["logical_tick"] == 1
    assert by_rev[0]["transaction_count"] == 0
    assert by_rev[0]["event_count"] == 0
    assert by_rev[1]["kinds"] == (
        "authority_decision",
        "domain_event",
        "proposed_effect",
        "transaction",
        "validation_decision",
    )
    assert by_rev[1]["logical_tick"] is None
    assert by_rev[1]["transaction_count"] == 1
    assert by_rev[1]["event_count"] == 1
    assert by_rev[2]["kinds"] == (
        "authority_decision",
        "dev_intervention",
        "domain_event",
        "proposed_effect",
        "transaction",
        "validation_decision",
    )
    assert by_rev[2]["logical_tick"] == 3
    assert by_rev[3]["kinds"] == ("domain_event", "transaction")
    assert by_rev[3]["transaction_count"] == 1
    assert by_rev[3]["event_count"] == 1
    assert all(r["wall_time"] is None for r in rows)


def test_intervention_history_surface() -> None:
    """t8：仅 ``DEV_INTERVENTION``（record_id / 逻辑刻字面量钉死）。"""
    run = run_p8_script()
    query = TraceQuery(run.trace_records)
    history = query.intervention_history()
    assert len(history) == 2
    assert all(r.kind is TraceKind.DEV_INTERVENTION for r in history)
    assert [r.record_id for r in history] == [
        "trc_00000000000000000000000000000042",
        "trc_00000000000000000000000000000043",
    ]
    assert [r.logical_tick for r in history] == [1, 3]


def test_causal_chain_with_proposal_cause() -> None:
    """t9：合成 PROPOSAL/ACTION/INTERVENTION 因果 → refs 保序；无事务链。"""
    record = _make_event_record(
        _PROBE_EVENT_ID,
        _PROBE_RECORD_ID,
        causes=(
            CauseRef(kind=CauseKind.PROPOSAL, ref_id=_PROPOSAL_REF),
            CauseRef(kind=CauseKind.ACTION, ref_id=_ACTION_REF),
            CauseRef(kind=CauseKind.INTERVENTION, ref_id=_INTERVENTION_REF),
        ),
    )
    query = TraceQuery([record])
    chain = query.causal_chain(_PROBE_EVENT_ID)
    assert chain.event.event_id == _PROBE_EVENT_ID
    assert chain.transaction is None
    assert chain.effects == ()
    assert chain.producers == (_PROBE_PRODUCER,)
    assert chain.action_refs == (_PROPOSAL_REF, _ACTION_REF)
    assert chain.intervention_refs == (_INTERVENTION_REF,)


def test_causal_chain_includes_action_intervention_refs() -> None:
    """t10（**A13**）：SC-1 首个域事件因果链回指 turn-1 干预记录。"""
    run = run_p8_script()
    query = TraceQuery(run.trace_records)
    first = query.domain_events()[0]
    assert first.event_type == "core.set_world_variable"
    chain = query.causal_chain(first.event_id)
    assert chain.intervention_refs == ("trc_00000000000000000000000000000042",)
    assert chain.action_refs == ()
    assert chain.transaction is not None
    assert chain.transaction.status is TransactionStatus.COMMITTED
    assert chain.effects[0].effect.effect_id == "eff_p8_dev_patch_1"
    assert chain.producers == ("devtools.developer",)


def test_causal_chain_unknown_event_raises() -> None:
    """t11：未知 ``event_id`` → ``TraceQueryError``（码 ``schema_invalid``）。"""
    run = run_p8_script()
    query = TraceQuery(run.trace_records)
    with pytest.raises(TraceQueryError) as excinfo:
        query.causal_chain(_UNKNOWN_EVENT_ID)
    assert excinfo.value.code == "schema_invalid"


def test_chain_surface_clean_and_zero_io() -> None:
    """t12：``to_dict`` JSON-clean + ``trace_query.py`` 零 IO AST（D4）。"""
    run = run_p8_script()
    query = TraceQuery(run.trace_records)
    chain = query.causal_chain(query.domain_events()[0].event_id)
    payload = chain.to_dict()
    assert isinstance(payload, dict)
    assert set(payload) == {
        "event",
        "transaction",
        "effects",
        "producers",
        "action_refs",
        "intervention_refs",
    }
    assert_json_clean(payload)

    # D4 零 IO AST 扫描：禁 os / pathlib 导入与名称引用、禁 open 调用。
    module_path = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "engine_v2"
        / "devtools"
        / "trace_query.py"
    )
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
    assert "os" not in imported
    assert "pathlib" not in imported
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id not in {"os", "pathlib", "open"}
        elif isinstance(node, ast.Attribute):
            assert node.attr != "open"
