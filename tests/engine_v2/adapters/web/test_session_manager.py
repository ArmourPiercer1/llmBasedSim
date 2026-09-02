"""P10 web 会话层测试（SOT §6.1 test_session_manager t1–t6 逐字面）。

- t1 = create_session → get → list → close → get →
  SessionNotFoundError；
- t2 = 双会话：A step 推进 tick → B state_snapshot 逐键不变
  （A12；G10-3 行为面）；
- t3 = state_snapshot JSON-clean（json.dumps 零失败，P10-INV-10）+
  键集 == SESSION_SNAPSHOT_KEYS（断言键集 == 常量，零硬编码清单）；
- t4 = P8 dump_persistence_snapshot → load_session 往返：
  world_revision/tick 等价 + check_persistence_versions 零冲突；
- t5 = 缺失会话 id → SessionNotFoundError（AD-P10-1 面）；
- t6 = SESSION_COMMANDS == 8 名逐字 + /status 数值 modal 面 + /stop
  暂停 + step-while-paused → 409 信封（AD-P10-1 面）。

纪律：全部显式 session_id（DEV-P10-05）；零 socket / 零墙钟（D6）；
12 名闭集零命中（K8）。
"""

from __future__ import annotations

import json

import pytest

from src.engine_v2.adapters.web.api import handle_web_request
from src.engine_v2.adapters.web.session import (
    SESSION_COMMANDS,
    SESSION_SNAPSHOT_KEYS,
    SessionExistsError,
    SessionManager,
    SessionNotFoundError,
    SessionPausedError,
)
from src.engine_v2.persistence.snapshot import (
    check_persistence_versions,
    load_persistence_snapshot,
)
from src.engine_v2.presentation.image.backend import DeterministicImageBackend
from tests.engine_v2.adapters.web.conftest import HostTickDriver
from tests.engine_v2.presentation.conftest import make_p10_world


def test_session_manager_t1_lifecycle(manager: SessionManager) -> None:
    """t1：create → get → list → close → get → SessionNotFoundError。"""
    world = make_p10_world()
    session_id = manager.create_session(
        world, session_id="sess_life", driver=HostTickDriver(world)
    )
    assert session_id == "sess_life"
    assert manager.get(session_id) is not None
    assert manager.list_sessions() == ("sess_life",)
    manager.close(session_id)
    assert manager.list_sessions() == ()
    with pytest.raises(SessionNotFoundError) as excinfo:
        manager.get(session_id)
    assert excinfo.value.session_id == "sess_life"


def test_session_manager_t2_multi_session_isolation(
    manager: SessionManager,
) -> None:
    """t2：A step 推进 tick → B state_snapshot 逐键不变（A12 隔离；
    G10-3 行为面）。"""
    world_a = make_p10_world()
    world_b = make_p10_world()
    sid_a = manager.create_session(
        world_a,
        session_id="sess_iso_a",
        driver=HostTickDriver(world_a),
        image_backend=DeterministicImageBackend(),
    )
    sid_b = manager.create_session(
        world_b,
        session_id="sess_iso_b",
        driver=HostTickDriver(world_b),
        image_backend=DeterministicImageBackend(),
    )
    session_a = manager.get(sid_a)
    session_b = manager.get(sid_b)
    snap_b_before = session_b.state_snapshot()
    snap_a_after = session_a.step("你好，那个摆锤钟")
    assert snap_a_after["tick"] == 1
    assert snap_a_after["view_revision"] == 1
    snap_b_after = session_b.state_snapshot()
    assert snap_b_before == snap_b_after
    assert set(snap_b_after) == set(SESSION_SNAPSHOT_KEYS)


def test_session_manager_t3_snapshot_json_clean(session) -> None:
    """t3：JSON-clean（json.dumps 零失败，P10-INV-10）+ 键集 ==
    SESSION_SNAPSHOT_KEYS（零硬编码清单）。"""
    snapshot = session.state_snapshot()
    assert set(snapshot) == set(SESSION_SNAPSHOT_KEYS)
    assert len(SESSION_SNAPSHOT_KEYS) == 24
    json.dumps(snapshot)
    json.dumps(snapshot, ensure_ascii=False)
    # step 后新快照同样 JSON-clean + 键集不变
    snapshot2 = session.step("随便说一句")
    assert set(snapshot2) == set(SESSION_SNAPSHOT_KEYS)
    json.dumps(snapshot2)


def test_session_manager_t4_load_from_p8_snapshot() -> None:
    """t4：/save → P8 dump → load_session 往返：world_revision/tick
    等价 + check_persistence_versions 零冲突。"""
    sink: dict[str, str] = {}
    manager_a = SessionManager(
        driver_factory=lambda: HostTickDriver(),
        image_backend_factory=lambda: DeterministicImageBackend(),
    )
    sid_a = manager_a.create_session(
        make_p10_world(),
        session_id="sess_save",
        driver=HostTickDriver(make_p10_world()),
        image_backend=DeterministicImageBackend(),
        save_sink=sink,
    )
    session_a = manager_a.get(sid_a)
    session_a.step("那个摆锤钟还能修吗？")
    session_a.step("/save w4_check")
    assert set(sink) == {"w4_check"}
    assert session_a.save_names == ("w4_check",)
    payload = sink["w4_check"]
    manager_b = SessionManager(
        driver_factory=lambda: HostTickDriver(),
        image_backend_factory=lambda: DeterministicImageBackend(),
    )
    sid_b = manager_b.load_session("sess_loaded", payload)
    session_b = manager_b.get(sid_b)
    snap_a = session_a.state_snapshot()
    snap_b = session_b.state_snapshot()
    assert snap_b["view_revision"] == snap_a["view_revision"]
    assert snap_b["tick"] == snap_a["tick"]
    assert set(snap_b) == set(SESSION_SNAPSHOT_KEYS)
    envelope = load_persistence_snapshot(payload)
    assert check_persistence_versions(envelope) == ()


def test_session_manager_t5_not_found(manager: SessionManager) -> None:
    """t5：缺失会话 id → SessionNotFoundError（AD-P10-1 面）；重复 id
    → SessionExistsError（同族 409 面）。"""
    with pytest.raises(SessionNotFoundError) as excinfo:
        manager.get("missing")
    assert excinfo.value.session_id == "missing"
    with pytest.raises(SessionNotFoundError):
        manager.close("missing")
    manager.create_session(
        make_p10_world(), session_id="sess_dup", driver=HostTickDriver()
    )
    with pytest.raises(SessionExistsError) as excinfo:
        manager.create_session(
            make_p10_world(), session_id="sess_dup", driver=HostTickDriver()
        )
    assert excinfo.value.session_id == "sess_dup"


def test_session_manager_t6_commands_closed(manager: SessionManager) -> None:
    """t6：SESSION_COMMANDS == 8 名逐字 + /status 数值 modal 面 +
    /stop 暂停 + step-while-paused → 409 信封（AD-P10-1 面）。"""
    assert SESSION_COMMANDS == (
        "/help",
        "/status",
        "/idid",
        "/see",
        "/hear",
        "/feel",
        "/save",
        "/stop",
    )
    session_id = manager.create_session(
        make_p10_world(),
        session_id="sess_cmd",
        driver=HostTickDriver(make_p10_world()),
        image_backend=DeterministicImageBackend(),
    )
    session = manager.get(session_id)
    snap = session.step("/status")
    assert "modal" in snap
    modal = snap["modal"]
    assert modal["title"] == "数值状态"
    assert modal["items"] == [
        {"key": "curiosity", "value": 3},
        {"key": "energy", "value": 7},
    ]
    stopped = session.step("/stop")
    assert stopped["can_continue"] is False
    with pytest.raises(SessionPausedError) as excinfo:
        session.step("你好")
    assert excinfo.value.session_id == "sess_cmd"
    # 409 信封面（AD-P10-1）：handler 层同一面
    response = handle_web_request(
        "POST",
        f"/api/sessions/{session_id}/action",
        {"text": "你好"},
        manager=manager,
    )
    assert response.status == 409
    payload = json.loads(response.payload)
    assert payload["ok"] is False
    assert payload["error_code"] == "session_paused"
