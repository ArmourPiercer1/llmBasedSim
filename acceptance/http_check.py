"""G10 验收 HTTP 面检查（stdlib urllib；对运行中验收服务）。

运行 = ``.venv/bin/python acceptance/http_check.py --port 8000
--session <id>``（仓库根；服务须已启动）。
报告 = ``acceptance/http-report.json``；退出码 0 全绿 / 1 有红项。

核验面（= 计划 Step 4.7/4.8 自动化）：
- 路由闭集：index 页 / 会话列表 / state / action / image /
  inspector 404 保留面 / workbench 404 保留面 / 未知路由 404 /
  静态 3 名 200 / 静态穿越 400；
- 信封形状：ok=true 成功面 + {"ok": false, error_code,
  error_message} 错误面（AD-P10-1）；
- 推进面：action → tick +1 + view_revision 递增 + 快照 24 键闭集；
- 图像面：200 + image/x-ppm + P3 头钉（64 32 255）+ 字节长 ==
  槽 byte_length + 同图重取字节相等（确定性）。
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

SNAPSHOT_KEYS = {
    "started", "world_name", "world_description", "tick",
    "view_revision", "scene_id", "game_phase", "game_time",
    "time_of_day", "weather", "narrative", "summary", "senses",
    "self_action_summary", "hidden_event_count", "player",
    "player_attributes", "npc_dynamics", "recent_events",
    "narrative_history", "can_continue", "tick_duration_minutes",
    "has_long_image_task", "image_slot",
}
# 24 键闭集 = SESSION_SNAPSHOT_KEYS（session.py:111 逐字；t3 钉）。


def get(base: str, path: str) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(base + path)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return (
                resp.status,
                dict(resp.headers),
                resp.read(),
            )
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def post(base: str, path: str, payload: object) -> tuple[int, bytes]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base + path, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    base = f"http://127.0.0.1:{args.port}"
    sid = args.session
    checks: dict[str, dict[str, object]] = {}

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks[name] = {"ok": ok, "detail": detail}
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
              + (f" — {detail}" if detail else ""))

    status, _headers, body = get(base, "/")
    html = body.decode("utf-8", "replace")
    record(
        "index_page",
        status == 200 and 'id="play"' in html and 'id="inspector"'
        in html and 'id="workbench"' in html,
        f"status={status}",
    )

    # 静态引用可解析面（ERR-P10-16 机械面：GET / 页的 src/href 本地
    # 引用必须全部 200——相对/绝对钉面与路由闭集矛盾的回归钉）。
    for page_path in ("/", "/static/index.html"):
        _s, _h, _b = get(base, page_path)
        page_html = _b.decode("utf-8", "replace")
        refs = re.findall(
            r"(?:src|href)=\"([^\"]+)\"", page_html
        )
        local_refs = [
            r for r in refs
            if not r.startswith(("#", "http://", "https://", "//"))
        ]
        bad = []
        for ref in local_refs:
            resolved = urllib.parse.urljoin(base + page_path, ref)
            code, _bh, _bb = get(base, urllib.parse.urlparse(resolved).path)
            if code != 200:
                bad.append(f"{ref}→{code}")
        record(
            f"page_refs_resolvable{page_path}",
            not bad,
            f"refs={local_refs}" + (f" bad={bad}" if bad else ""),
        )

    status, body = post(base, "/api/sessions", {})
    try:
        env = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        env = {}
    record(
        "create_missing_world_400",
        status == 400 and env.get("ok") is False
        and "error_code" in env and "error_message" in env,
        f"status={status}",
    )

    status, _headers, body = get(base, "/api/sessions")
    env = json.loads(body.decode("utf-8"))
    listed = env.get("sessions") or env.get("ids") or []
    if not isinstance(listed, list):
        listed = [listed]
    record(
        "sessions_list",
        status == 200 and env.get("ok") is True and sid in listed,
        f"listed={listed}",
    )

    status, _headers, body = get(base, f"/api/sessions/{sid}/state")
    env = json.loads(body.decode("utf-8"))
    snap = env.get("snapshot", {})
    keys_match = set(snap) == SNAPSHOT_KEYS
    record(
        "state_snapshot",
        status == 200 and env.get("ok") is True and keys_match
        and snap.get("started") is True
        and str(snap.get("scene_id", "")).startswith("scene:")
        and isinstance(snap.get("tick"), int),
        f"status={status} keys={len(snap)} "
        f"24键闭集={keys_match} tick={snap.get('tick')} "
        f"scene={snap.get('scene_id', '')[:24]}…",
    )
    tick0 = int(snap.get("tick", -1))
    rev0 = int(snap.get("view_revision", -1))

    status, body = post(
        base, f"/api/sessions/{sid}/action", {"text": "验收动作（自动）"}
    )
    env = json.loads(body.decode("utf-8"))
    snap1 = env.get("snapshot", {})
    tick1 = int(snap1.get("tick", -1))
    rev1 = int(snap1.get("view_revision", -1))
    record(
        "action_advances",
        status == 200 and env.get("ok") is True and tick1 == tick0 + 1
        and rev1 > rev0,
        f"tick {tick0}→{tick1} rev {rev0}→{rev1}",
    )

    status, body = post(
        base, f"/api/sessions/{sid}/action", "not-a-dict"
    )
    try:
        env_bad = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        env_bad = {}
    record(
        "action_bad_body_400",
        status == 400 and env_bad.get("ok") is False
        and "error_code" in env_bad,
        f"status={status}",
    )

    status, headers, img1 = get(base, f"/api/sessions/{sid}/image")
    ctype = headers.get("Content-Type", "")
    head = img1[:16].decode("ascii", "replace")
    slot = snap1.get("image_slot") or {}
    length_ok = (
        isinstance(slot, dict) and slot.get("byte_length") == len(img1)
    )
    record(
        "image_endpoint",
        status == 200 and "image/x-ppm" in ctype
        and head.startswith("P3\n64 32\n255\n")
        and length_ok,
        f"status={status} ctype={ctype} head={head!r} "
        f"bytes={len(img1)} slot.byte_length={slot.get('byte_length')}",
    )

    _s2, _h2, img2 = get(base, f"/api/sessions/{sid}/image")
    record("image_determinism", img1 == img2, "同图重取字节相等")

    for name, path in (
        ("inspector_404_retained", f"/api/inspector/{sid}"),
        ("workbench_404_retained", f"/api/workbench/{sid}"),
        ("unknown_route_404", "/api/nope"),
    ):
        status, _headers, body = get(base, path)
        try:
            env = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            env = {}
        record(
            name,
            status == 404 and env.get("ok") is False
            and "error_code" in env and "error_message" in env,
            f"status={status} code={env.get('error_code')}",
        )

    for name in ("app.js", "index.html", "styles.css"):
        status, _headers, _body = get(base, f"/static/{name}")
        record(f"static_{name}", status == 200, f"status={status}")

    status, _headers, body = get(base, "/static/../session.py")
    try:
        env = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        env = {}
    record(
        "static_traversal_400",
        status == 400 and env.get("ok") is False,
        f"status={status}",
    )

    status, _headers, body = get(base, f"/api/sessions/missing/state")
    try:
        env = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        env = {}
    record(
        "missing_session_404",
        status == 404 and env.get("ok") is False
        and "error_code" in env,
        f"status={status} code={env.get('error_code')}",
    )

    all_ok = all(c["ok"] for c in checks.values())
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "port": args.port,
        "session": sid,
        "all_ok": all_ok,
        "checks": checks,
    }
    out = _ROOT / "acceptance" / "http-report.json"
    out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"总体 = {'PASS' if all_ok else 'FAIL'}（报告 = {out}）")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
