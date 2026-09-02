"""P10 web 无状态 handler 层测试（SOT §6.1 test_web_api t1–t5 逐字面）。

- t1 = WEB_ROUTES == 9 行闭集逐字（method + path pattern）；
- t2 = POST /api/sessions/{id}/action（自由文本）→ 响应 tick == 前值
  + 1 + view_revision 递增；
- t3 = GET image：200 + content-type image/x-ppm + payload 长 ==
  slot.byte_length；无图 → 404 信封；
- t4 = 未知 path → 404 + ok==false 信封（code 闭集）；
- t5 = WebApiError 面 → (status ∈ {400,404,409,500}, {"ok": false,
  "error_code", "error_message"}) 形状钉（AD-P10-1）。

纪律：全部显式 session_id（DEV-P10-05）；零 socket / 零墙钟（D6，
handler 层纯函数面，D-P10-03）；12 名闭集零命中（K8）。
"""

from __future__ import annotations

import json

from src.engine_v2.adapters.web.api import WEB_ROUTES, handle_web_request
from src.engine_v2.adapters.web.session import SessionManager
from src.engine_v2.presentation.image.backend import DeterministicImageBackend
from tests.engine_v2.adapters.web.conftest import HostTickDriver
from tests.engine_v2.presentation.conftest import make_p10_world


def _create_session(manager: SessionManager, session_id: str) -> str:
    """显式 session_id 建会（driver + DeterministicImageBackend 注入）。"""
    world = make_p10_world()
    return manager.create_session(
        world,
        session_id=session_id,
        driver=HostTickDriver(world),
        image_backend=DeterministicImageBackend(),
    )


def _state_snapshot(manager: SessionManager, session_id: str) -> dict:
    """GET state → 成功信封 snapshot 面。"""
    response = handle_web_request(
        "GET", f"/api/sessions/{session_id}/state", None, manager=manager
    )
    assert response.status == 200
    payload = json.loads(response.payload)
    assert payload["ok"] is True
    return payload["snapshot"]


def test_web_api_t1_routes_closed(manager: SessionManager) -> None:
    """t1：WEB_ROUTES == 9 行闭集逐字（method + path pattern，序钉）。"""
    assert WEB_ROUTES == (
        ("GET", "/"),
        ("GET", "/api/sessions"),
        ("POST", "/api/sessions"),
        ("GET", "/api/sessions/{id}/state"),
        ("POST", "/api/sessions/{id}/action"),
        ("GET", "/api/sessions/{id}/image"),
        ("GET", "/api/inspector/{id}"),
        ("GET", "/api/workbench/{id}"),
        ("GET", "/static/{name}"),
    )
    assert len(WEB_ROUTES) == 9
    # 路由面抽查（闭集语义锚）：GET / = 200 html；static 3 名 = 200
    index = handle_web_request("GET", "/", None, manager=manager)
    assert index.status == 200
    assert index.content_type == "text/html; charset=utf-8"
    for name in ("index.html", "app.js", "styles.css"):
        static = handle_web_request("GET", f"/static/{name}", None, manager=manager)
        assert static.status == 200
        assert len(static.payload) > 0
    sessions = handle_web_request("GET", "/api/sessions", None, manager=manager)
    assert sessions.status == 200
    assert json.loads(sessions.payload)["ok"] is True


def test_web_api_t2_action_advances_tick(manager: SessionManager) -> None:
    """t2：POST action（自由文本）→ tick == 前值 + 1 + view_revision
    递增。"""
    session_id = _create_session(manager, "sess_api_t2")
    before = _state_snapshot(manager, session_id)
    response = handle_web_request(
        "POST",
        f"/api/sessions/{session_id}/action",
        {"text": "那个摆锤钟还能修吗？"},
        manager=manager,
    )
    assert response.status == 200
    payload = json.loads(response.payload)
    assert payload["ok"] is True
    after = payload["snapshot"]
    assert after["tick"] == before["tick"] + 1
    assert after["view_revision"] == before["view_revision"] + 1


def test_web_api_t3_image_endpoint(manager: SessionManager) -> None:
    """t3：GET image = 200 + image/x-ppm + payload 长 ==
    slot.byte_length；无图 → 404 信封。"""
    session_id = _create_session(manager, "sess_api_t3")
    missing = handle_web_request(
        "GET", f"/api/sessions/{session_id}/image", None, manager=manager
    )
    assert missing.status == 404
    missing_payload = json.loads(missing.payload)
    assert missing_payload["ok"] is False
    assert missing_payload["error_code"] == "image_not_found"
    action = handle_web_request(
        "POST",
        f"/api/sessions/{session_id}/action",
        {"text": "你好"},
        manager=manager,
    )
    assert action.status == 200
    slot = _state_snapshot(manager, session_id)["image_slot"]
    assert slot is not None
    image = handle_web_request(
        "GET", f"/api/sessions/{session_id}/image", None, manager=manager
    )
    assert image.status == 200
    assert image.content_type == "image/x-ppm"
    assert isinstance(image.payload, bytes)
    assert len(image.payload) == slot["byte_length"]


def test_web_api_t4_unknown_route_404(manager: SessionManager) -> None:
    """t4：未知 path → 404 + ok==false 信封（code 闭集）。"""
    response = handle_web_request("GET", "/api/nope", None, manager=manager)
    assert response.status == 404
    payload = json.loads(response.payload)
    assert payload["ok"] is False
    assert payload["error_code"] == "route_not_found"
    assert isinstance(payload["error_message"], str)
    assert payload["error_message"]
    # 动词不匹配 → 同族 404 信封
    mismatch = handle_web_request("DELETE", "/", None, manager=manager)
    assert mismatch.status == 404
    mismatch_payload = json.loads(mismatch.payload)
    assert mismatch_payload["ok"] is False


def test_web_api_t5_error_envelope(manager: SessionManager) -> None:
    """t5：WebApiError 面 → (status ∈ {400,404,409,500}, 3 键错误
    信封) 形状钉（AD-P10-1）。"""
    session_id = _create_session(manager, "sess_api_t5")
    cases = [
        ("GET", "/api/sessions/missing/state", None, 404, "session_not_found"),
        ("POST", f"/api/sessions/{session_id}/action", {"no_text": 1}, 400, "bad_request"),
        ("GET", "/static/../index.html", None, 400, "bad_request"),
        ("POST", "/api/sessions", "not-a-dict", 400, "bad_request"),
        ("POST", "/api/sessions", {"world": "not-a-dict"}, 400, "bad_request"),
        ("POST", f"/api/sessions/{session_id}/action", {"text": "  "}, 400, "bad_request"),
    ]
    for method, path, body, status, code in cases:
        response = handle_web_request(method, path, body, manager=manager)
        assert response.status == status
        assert response.status in {400, 404, 409, 500}
        payload = json.loads(response.payload)
        assert set(payload) == {"ok", "error_code", "error_message"}
        assert payload["ok"] is False
        assert payload["error_code"] == code
        assert isinstance(payload["error_message"], str)
    # 409 双义面：重复建会（session_exists）与暂停会话（session_paused）
    duplicate = handle_web_request(
        "POST",
        "/api/sessions",
        {"world": make_p10_world().model_dump(mode="json"), "session_id": session_id},
        manager=manager,
    )
    assert duplicate.status == 409
    assert json.loads(duplicate.payload)["error_code"] == "session_exists"
    handle_web_request(
        "POST",
        f"/api/sessions/{session_id}/action",
        {"text": "/stop"},
        manager=manager,
    )
    paused = handle_web_request(
        "POST",
        f"/api/sessions/{session_id}/action",
        {"text": "你好"},
        manager=manager,
    )
    assert paused.status == 409
    assert json.loads(paused.payload)["error_code"] == "session_paused"
