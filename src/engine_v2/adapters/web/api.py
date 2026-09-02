"""P10 无状态请求 handler 层（T05；SOT §3.8；导出 5 名）。

来源 = Spec §35（web adapter 协议翻译）+ v1 ``src/web/app.py`` 路由
（:230–258）/ 错误信封（WebUIError:38）/ 路径安全（_safe_*_path）
**语义参照**（文字参照，零 import；v1 = 冻结对照锚，P10 零 v1 import）
+ D-P10-03（handler 层 = 无状态纯函数；stdlib http.server 薄壳 =
server.py，测试零调用，D-P10-03 socket 面隔离）。

纪律（P10-INV-4/10，D6，K8）：

- ``handle_web_request`` = 纯函数（对 manager 而言：零 socket / 零
  线程 / 零模块级状态，A3 AST）；请求 = (method, path, body) →
  :class:`WebResponse`；
- :data:`WEB_ROUTES` = 9 行闭集逐字（SOT §3.8 表；t1 逐字钉）；
  ``/api/inspector/{id}`` / ``/api/workbench/{id}`` = W5 数据面
  保留行（W4 零委托 → 404 信封；W5 落点 = inspector/workbench
  模块函数直调消费 + S11 人工面，api 路由面零改——白名单行 13–14
  不含 api.py）；
- 错误信封 = ``{"ok": false, "error_code", "error_message"}``（AD-P10-1
  面；error_code 闭集 = 私有常量 :data:`WEB_ERROR_CODES`；status 闭集
  = 私有常量 :data:`WEB_ERROR_STATUSES` = {400, 404, 409, 500}；
  信封恰 3 键，t4/t5 钉）；
- 成功信封 = ``{"ok": true, ...}``（JSON-clean，P10-INV-10；
  ``sort_keys=True`` 确定性序列化）；
- :func:`resolve_static_name` = 闭集 3 名守卫（index.html / app.js /
  styles.css；越界 / 路径穿越 → 400 面；v1 路径安全思想承接 = 闭集
  成员判定唯一合法面）；
- 错误映射（AD-P10-1）：WebApiError → 自身 status；
  SessionNotFoundError → 404；SessionExistsError / SessionPausedError
  → 409；CommandError → 400；其余异常 → 500（fail-loud，零静默吞）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from src.engine_v2.adapters.web.session import (
    CommandError,
    SessionExistsError,
    SessionManager,
    SessionNotFoundError,
    SessionPausedError,
)
from src.engine_v2.adapters.web.views import render_page
from src.engine_v2.core.state import WorldState

__all__ = [
    "WEB_ROUTES",
    "WebApiError",
    "WebResponse",
    "handle_web_request",
    "resolve_static_name",
]

#: 路由闭集 9 行（SOT §3.8 逐字；t1 逐字钉；序钉）。
WEB_ROUTES: Final[tuple[tuple[str, str], ...]] = (
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

#: status 闭集（私有常量；AD-P10-1 面钉；t5 钉）。
WEB_ERROR_STATUSES: Final[frozenset[int]] = frozenset({400, 404, 409, 500})

#: error_code 闭集（私有常量；AD-P10-1 面钉；t5 钉）。
WEB_ERROR_CODES: Final[frozenset[str]] = frozenset(
    {
        "bad_request",
        "route_not_found",
        "session_not_found",
        "session_exists",
        "session_paused",
        "image_not_found",
        "internal_error",
    }
)

#: WebApiError 未显式给 code 时 = status 默认映射（私有常量；
#: 409 双义面（exists / paused）由显式 code 区分，本映射只兜底）。
_STATUS_CODE_FALLBACK: Final[dict[int, str]] = {
    400: "bad_request",
    404: "route_not_found",
    409: "session_paused",
    500: "internal_error",
}

#: static 闭集 3 名（SOT §3.8：resolve_static_name 守卫）+ 目录 +
#: content_type 面（SOT §3.8 content_type 闭集逐字：application/json /
#: text/html; charset=utf-8 / image/x-ppm / text/plain; charset=utf-8 /
#: text/css——JS 类型不在闭集 → app.js = text/plain 面，披露面）。
_STATIC_CLOSED_SET: Final[frozenset[str]] = frozenset(
    {"index.html", "app.js", "styles.css"}
)
_STATIC_BASE_DIR: Final[Path] = Path(__file__).resolve().parent / "static"
_STATIC_CONTENT_TYPES: Final[dict[str, str]] = {
    "index.html": "text/html; charset=utf-8",
    "app.js": "text/plain; charset=utf-8",
    "styles.css": "text/css",
}


class WebApiError(Exception):
    """API 层单一错误族（v1 WebUIError:38 先例；SOT §3.8 两属性面
    ``status_code`` / ``detail`` 逐字）。

    - ``status_code`` ∈ :data:`WEB_ERROR_STATUSES`（构造器闭集校验；
      越界 → ValueError——编程错误面，非 P10 运行时错误面，
      PresentationError 先例同族 fail-loud）；
    - ``detail`` = 人读描述（error_message 信封面）；
    - ``code`` = error_code 信封面（可选；缺省 →
      :data:`_STATUS_CODE_FALLBACK` status 默认映射；非缺省须 ∈
      :data:`WEB_ERROR_CODES`，否则 ValueError）。
    """

    def __init__(self, status_code: int, detail: str, *, code: str | None = None) -> None:
        if status_code not in WEB_ERROR_STATUSES:
            raise ValueError(
                f"WebApiError.status_code {status_code} 不在 "
                f"WEB_ERROR_STATUSES 闭集：{sorted(WEB_ERROR_STATUSES)}"
            )
        if code is not None and code not in WEB_ERROR_CODES:
            raise ValueError(f"WebApiError.code {code!r} 不在 WEB_ERROR_CODES 闭集")
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.code = code

    def __str__(self) -> str:
        return f"[{self.status_code}] {self.detail}"


@dataclass(frozen=True)
class WebResponse:
    """响应信封（SOT §3.8；frozen；JSON 面 = 信封 dict 文本，图像面 =
    原始 bytes payload）。

    ``content_type`` 闭集 = SOT §3.8 逐字 5 值（见
    :data:`_STATIC_CONTENT_TYPES` docstring 注；image 路由 =
    image/x-ppm）。
    """

    status: int
    content_type: str
    payload: str | bytes


def resolve_static_name(name: str) -> str:
    """static 名 → 闭集 3 名（index.html / app.js / styles.css）。

    越界 / 路径穿越（``../`` 等）/ 非 str → WebApiError(400)（v1
    _safe_*_path 路径安全思想承接：闭集成员判定 = 唯一合法面，
    零路径拼接）。
    """
    if not isinstance(name, str) or name not in _STATIC_CLOSED_SET:
        raise WebApiError(400, f"static 名越界：{name!r}（闭集 = 3 名）")
    return name


def _segments(value: str) -> list[str]:
    """路径 → 非空段列表（``/api/sessions/x`` → 3 段；``/`` → 0 段）。"""
    return [segment for segment in value.split("/") if segment]


def _placeholder_or_equal(part: str, segment: str) -> bool:
    """段匹配：``{id}`` / ``{name}`` 占位段 = 任意非空段；固定段 =
    逐字相等。"""
    return (part.startswith("{") and part.endswith("}")) or part == segment


def _match_route(method: str, path: str) -> str | None:
    """路由闭集匹配（段级：逐段占位 / 逐字）；返回匹配到的模式
    串（None = 未知路由 → 404 信封）。"""
    wanted = _segments(path)
    for route_method, pattern in WEB_ROUTES:
        if route_method != method:
            continue
        parts = _segments(pattern)
        if len(parts) != len(wanted):
            continue
        if all(
            _placeholder_or_equal(part, segment)
            for part, segment in zip(parts, wanted)
        ):
            return pattern
    return None


def _capture(pattern: str, path: str, placeholder: str) -> str:
    """占位段取值（模式 / 路径段对齐；编程错误 → AssertionError
    fail-loud，非运行时面）。"""
    for part, segment in zip(_segments(pattern), _segments(path)):
        if part == placeholder:
            return segment
    raise AssertionError(f"占位段 {placeholder!r} 不在模式 {pattern!r}")


def _json_response(payload: dict, status: int = 200) -> WebResponse:
    """JSON 信封序列化（sort_keys 确定性；JSON-clean 由构造保证，
    P10-INV-10）。"""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return WebResponse(status=status, content_type="application/json", payload=text)


def _error_response(status_code: int, code: str, message: str) -> WebResponse:
    """错误信封（AD-P10-1 面；恰 3 键：ok / error_code /
    error_message）。"""
    payload = {"ok": False, "error_code": code, "error_message": message}
    return _json_response(payload, status=status_code)


def _require_body_dict(body: object) -> dict:
    """请求体必须 JSON 对象（body=None = 无体 / 坏体（server 层 JSON
    解析失败面）→ 400）。"""
    if not isinstance(body, dict):
        raise WebApiError(400, "请求体必须是 JSON 对象")
    return body


def _create_body(body: object) -> tuple[WorldState, str | None]:
    """POST /api/sessions 体面：``{"world": WorldState JSON,
    "session_id"?: 非空 str}``（v1 无建会路由，v2 新面；world 契约
    校验失败 → 400）。"""
    data = _require_body_dict(body)
    world_payload = data.get("world")
    if not isinstance(world_payload, dict):
        raise WebApiError(400, "world 缺失或非对象")
    try:
        world = WorldState.model_validate(world_payload)
    except (ValidationError, ValueError) as exc:
        raise WebApiError(400, f"world 契约校验失败：{exc}") from exc
    session_id = data.get("session_id")
    if session_id is not None and (
        not isinstance(session_id, str) or not session_id
    ):
        raise WebApiError(400, "session_id 必须为非空字符串")
    return world, (session_id if isinstance(session_id, str) else None)


def _action_body(body: object) -> str:
    """POST /api/sessions/{id}/action 体面：``{"text": 非空 str}``
    （v1 handle_command 入口面；空串 → 400，会话 step 空输入 no-op
    面不经 api）。"""
    data = _require_body_dict(body)
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        raise WebApiError(400, "text 缺失或空串")
    return text.strip()


def _dispatch(
    method: str, path: str, body: object, manager: SessionManager
) -> WebResponse:
    """路由分派（WEB_ROUTES 闭集；未知路由 → 404 信封）。

    static 行特例：闭集行 ``/static/{name}`` = 前缀捕获（``/static/``
    后原文整体入 :func:`resolve_static_name`——穿越面（``../`` 等）
    经闭集成员判定拒绝 → 400 信封；段级匹配会把穿越段拆散成未知
    路由，故前缀面先行）。
    """
    if (
        method == "GET"
        and path.startswith("/static/")
        and len(path) > len("/static/")
    ):
        name = path[len("/static/"):]
        safe_name = resolve_static_name(name)
        raw = (_STATIC_BASE_DIR / safe_name).read_bytes()
        return WebResponse(200, _STATIC_CONTENT_TYPES[safe_name], raw.decode("utf-8"))
    route = _match_route(method, path)
    if route is None:
        raise WebApiError(404, f"未知路由：{method} {path}")
    if route == "/":
        html_text = render_page("index", title="P10 Web · 玩法页")
        return WebResponse(200, "text/html; charset=utf-8", html_text)
    if route == "/api/sessions":
        if method == "GET":
            return _json_response(
                {"ok": True, "sessions": list(manager.list_sessions())}
            )
        world, session_id = _create_body(body)
        new_id = manager.create_session(world, session_id=session_id)
        return _json_response({"ok": True, "session_id": new_id})
    if route == "/api/sessions/{id}/state":
        session_id = _capture("/api/sessions/{id}/state", path, "{id}")
        session = manager.get(session_id)
        return _json_response(
            {
                "ok": True,
                "session_id": session_id,
                "snapshot": session.state_snapshot(),
            }
        )
    if route == "/api/sessions/{id}/action":
        session_id = _capture("/api/sessions/{id}/action", path, "{id}")
        session = manager.get(session_id)
        text = _action_body(body)
        snapshot = session.step(text)
        return _json_response(
            {
                "ok": True,
                "session_id": session_id,
                "snapshot": snapshot,
            }
        )
    if route == "/api/sessions/{id}/image":
        session_id = _capture("/api/sessions/{id}/image", path, "{id}")
        artifact = manager.get(session_id).image()
        if artifact is None:
            raise WebApiError(404, "会话尚无图像 artifact", code="image_not_found")
        return WebResponse(200, "image/x-ppm", artifact.payload)
    # /api/inspector/{id} + /api/workbench/{id} = W5 数据面保留行
    # （W4 零委托 → 404 信封；SOT §3.10/§3.11 数据面经模块函数直调
    # 消费，路由面零改）。
    raise WebApiError(404, f"数据面保留（W5 落点）：{route}")


def handle_web_request(
    method: str, path: str, body: object, *, manager: SessionManager
) -> WebResponse:
    """协议无关请求 handler（SOT §3.8；对 manager 纯函数：零 socket /
    零线程 / 零模块级状态，A3 AST）。

    路由语义（:data:`WEB_ROUTES` 9 行闭集）：

    - ``GET /`` → render_page("index")（text/html；W4 路由面 = index
      页，3 段导航壳内联；inspector / workbench 页模板 = render_page
      可调面，路由闭集无页路由——S4 人工面 pending 的披露面）；
    - ``GET /api/sessions`` → 会话 id 列表（排序）；
    - ``POST /api/sessions`` → 建会（体 = {"world", "session_id"?}）；
    - ``GET /api/sessions/{id}/state`` → 成功信封 + state_snapshot；
    - ``POST /api/sessions/{id}/action`` → 体 = {"text"} →
      session.step → 成功信封 + 新 snapshot；
    - ``GET /api/sessions/{id}/image`` → 200 + image/x-ppm + 原始
      payload；无图 → 404 信封（image_not_found）；
    - ``GET /api/inspector/{id}`` / ``GET /api/workbench/{id}`` →
      W5 数据面保留（404 信封）；
    - ``GET /static/{name}`` → 闭集 3 名静态文件（穿越 → 400 信封）。

    错误映射（AD-P10-1，见模块 docstring）；查询串（``?`` 后）在
    薄壳层剥除（v1 urlparse 先例），handler 层只认路径。
    """
    try:
        return _dispatch(method, path, body, manager)
    except WebApiError as exc:
        code = exc.code or _STATUS_CODE_FALLBACK[exc.status_code]
        return _error_response(exc.status_code, code, exc.detail)
    except SessionNotFoundError as exc:
        return _error_response(
            404, "session_not_found", f"会话缺失：{exc.session_id}"
        )
    except SessionExistsError as exc:
        return _error_response(
            409, "session_exists", f"会话已存在：{exc.session_id}"
        )
    except SessionPausedError as exc:
        return _error_response(
            409, "session_paused", f"会话已暂停：{exc.session_id}"
        )
    except CommandError as exc:
        return _error_response(400, "bad_request", str(exc))
    except Exception as exc:  # 500 面（fail-loud，零静默吞）
        return _error_response(500, "internal_error", f"{type(exc).__name__}: {exc}")
