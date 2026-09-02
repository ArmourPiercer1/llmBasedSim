"""P10 web 运行时 inspector 数据面测试（SOT §6.1 test_inspector t1–t4
逐字面）。

- t1 = build_inspector_view 12 节键集 == INSPECTOR_SECTIONS（12 名
  闭集逐字，序钉）+ json.dumps 零失败（P10-INV-10）；
- t2 = 因果链端到端（fixture 已知事件 → inspect_event 全量投影六
  字段：event 非空 + transaction 非 None + effects ≥ 1 + producers
  非空 + action_refs 非空；事件缺席 → TraceQueryError 透传——404
  信封面 AD-P10-1）；
- t3 = revision_timeline 严格单调（world_revision 升序唯一）；
- t4 = authority_decision 节 ≥ 1 条 + producer 非空（K6 面）。

纪律：数据源 = known_event_sequence 世界 + 五面 trace 注入会话——
测试函数内局部构造（合法面：W4 web conftest trace_manager_session
同构构造；conftest 跨树 fixture 引用面不解析——零 conftest 修改）；
事件 id = P1 核心 uuid4 身份标签（既有 core 面，本波零新增）→ 经
公开 ``state_snapshot()["recent_events"]`` 面取，零字面量钉；显式
session_id（DEV-P10-05）；零墙钟 / 零随机（D6）；12 名闭集零命中
（K8）。
"""

from __future__ import annotations

import json

import pytest

from src.engine_v2.adapters.web.inspector import (
    INSPECTOR_SECTIONS,
    build_inspector_view,
    inspect_event,
)
from src.engine_v2.adapters.web.session import SessionManager
from src.engine_v2.devtools.trace_query import TraceQueryError
from src.engine_v2.presentation.image.backend import DeterministicImageBackend
from tests.engine_v2.adapters.web.conftest import HostTickDriver
from tests.engine_v2.presentation.conftest import (
    _run_known_sequence,
    make_p10_world,
)

#: 局部构造会话 id（显式钉，DEV-P10-05 纪律）。
_SESSION_ID = "sess_w5_inspector"


def _trace_session():
    """known_event_sequence 世界 + trace_records 注入会话（SOT §6.2
    同构面；测试函数内局部构造 = 合法面）。"""
    sequence = _run_known_sequence(make_p10_world())
    manager = SessionManager(
        driver_factory=lambda: HostTickDriver(),
        image_backend_factory=lambda: DeterministicImageBackend(),
    )
    session_id = manager.create_session(
        sequence.world,
        session_id=_SESSION_ID,
        driver=HostTickDriver(sequence.world),
        trace_records=sequence.trace_records,
    )
    return manager.get(session_id)


def test_inspector_t1_twelve_sections() -> None:
    """t1：12 节键集 == INSPECTOR_SECTIONS 逐字（序钉）+ JSON-clean。"""
    view = build_inspector_view(_trace_session())
    assert set(view) == set(INSPECTOR_SECTIONS)
    assert len(view) == 12
    assert list(view) == list(INSPECTOR_SECTIONS)
    json.dumps(view, ensure_ascii=False)  # P10-INV-10 零失败


def test_inspector_t2_causal_chain_end_to_end() -> None:
    """t2：因果链端到端（A4：event → transaction → effect →
    producer）+ 事件缺席 TraceQueryError 透传。"""
    session = _trace_session()
    recent_events = session.state_snapshot()["recent_events"]
    assert len(recent_events) >= 1
    event_id = recent_events[-1]["event_id"]
    chain = inspect_event(session, event_id)
    assert set(chain) == {
        "event",
        "transaction",
        "effects",
        "producers",
        "action_refs",
        "intervention_refs",
    }
    assert chain["event"]["event_id"] == event_id
    assert chain["transaction"] is not None
    assert len(chain["effects"]) >= 1
    assert len(chain["producers"]) >= 1
    assert len(chain["action_refs"]) >= 1
    with pytest.raises(TraceQueryError):
        inspect_event(session, "evt_inspector_missing")


def test_inspector_t3_revision_timeline_monotonic() -> None:
    """t3：revision_timeline 严格单调（world_revision 升序唯一）。"""
    view = build_inspector_view(_trace_session())
    rows = view["revision_timeline"]
    assert len(rows) >= 2
    revisions = [row["world_revision"] for row in rows]
    assert all(
        revisions[index] < revisions[index + 1]
        for index in range(len(revisions) - 1)
    )


def test_inspector_t4_authority_decisions_present() -> None:
    """t4：authority_decision 节 ≥ 1 条 + producer 非空（K6 面）。"""
    view = build_inspector_view(_trace_session())
    rows = view["authority_decision"]
    assert len(rows) >= 1
    for row in rows:
        assert row["producer_id"]
