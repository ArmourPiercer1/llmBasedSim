"""G10 UI 面自动检查（Playwright；对运行中验收服务，headless）。

运行 = ``.venv-acceptance/bin/python acceptance/ui_check.py --port
8000 --session <id>``（仓库根；服务须已启动）。
报告 = ``acceptance/ui-report.json``；截图 =
``docs/v2/gates/evidence-g10/ui-*.png``；退出码 0 全绿 / 1 红。

自动核验（机械面；视觉判断面 = 人工，截图供人工面复用）：
- index 页 3 段壳（play / inspector / workbench）+ 静态 JS 加载；
- 连接会话 → state-box 出 24 键快照 JSON（started=true / scene_id
  前缀 / tick 整数）；
- 动作推进 → tick +1 + view_revision 递增 + 图像槽注记 + canvas
  出图（app.js PPM→canvas 解码面）；
- 连续动作 → revision 单调（稳定性机械面）；
- 错误面：不存在会话 → 「错误：」透传（404 信封 error_message）；
- 保留面：inspector / workbench 按钮 → 「错误：」披露（404 保留
  数据面，S4/S11 pending）。
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = _ROOT / "docs" / "v2" / "gates" / "evidence-g10"
CHROME = (
    Path.home() / ".cache" / "ms-playwright" / "chromium-1234"
    / "chrome-linux64" / "chrome"
)
SNAPSHOT_KEYS = {
    "started", "world_name", "world_description", "tick",
    "view_revision", "scene_id", "game_phase", "game_time",
    "time_of_day", "weather", "narrative", "summary", "senses",
    "self_action_summary", "hidden_event_count", "player",
    "player_attributes", "npc_dynamics", "recent_events",
    "narrative_history", "can_continue", "tick_duration_minutes",
    "has_long_image_task", "image_slot",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    base = f"http://127.0.0.1:{args.port}"
    sid = args.session
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    checks: dict[str, dict[str, object]] = {}

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks[name] = {"ok": ok, "detail": detail}
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
              + (f" — {detail}" if detail else ""))

    def snap_text(page) -> dict:
        try:
            return json.loads(page.text_content("#state-box"))
        except (ValueError, TypeError):
            return {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=str(CHROME), headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 1000})

        # 网络层 = Playwright route 拦截 + stdlib urllib 供给（沙箱内
        # chromium 直连 localhost 被拦截的环境对策：浏览器零真实网络
        # 连接，页面 JS 完整执行；HTTP 面本体由 http_check.py 真实
        # socket 核验，本层只核 UI 逻辑 / 渲染 / 存证）。
        def _fulfill(route) -> None:
            req = route.request
            url = req.url
            try:
                headers = {
                    k: v for k, v in req.headers.items()
                    if k.lower() not in ("host", "content-length")
                }
                data = req.post_data_buffer if req.post_data else None
                with urllib.request.urlopen(
                    urllib.request.Request(
                        url, data=data, headers=headers,
                        method=req.method,
                    ),
                    timeout=10,
                ) as resp:
                    route.fulfill(
                        status=resp.status,
                        content_type=resp.headers.get(
                            "Content-Type", "application/octet-stream"
                        ),
                        body=resp.read(),
                    )
            except urllib.error.HTTPError as exc:
                route.fulfill(
                    status=exc.code,
                    content_type=exc.headers.get(
                        "Content-Type", "application/json"
                    ),
                    body=exc.read(),
                )
            except Exception:  # noqa: BLE001
                route.fulfill(
                    status=502, content_type="text/plain",
                    body=b"acceptance-route-fetch-failed",
                )

        page.route("**/*", _fulfill)
        page.goto(base, wait_until="load")

        # 1) index 页 3 段壳 + 静态 JS
        for sec in ("play", "inspector", "workbench"):
            if not page.locator(f"#{sec}").count():
                break
        else:
            sections_ok = True
        script_ok = page.locator(
            'script[src="/static/app.js"]'
        ).count() == 1
        record(
            "ui_index_shell",
            sections_ok and script_ok,
            f"3 段壳={sections_ok} app.js={script_ok}",
        )
        page.screenshot(path=str(EVIDENCE / "ui-01-index.png"))

        # 2) 连接会话
        page.fill("#session-input", sid)
        page.click("#connect-btn")
        page.wait_for_function(
            "document.getElementById('state-box').textContent"
            ".includes('\"started\": true')",
            timeout=15000,
        )
        snap = snap_text(page)
        keys_match = set(snap) == SNAPSHOT_KEYS
        scene_ok = str(snap.get("scene_id", "")).startswith("scene:")
        record(
            "ui_connect_snapshot",
            keys_match and snap.get("started") is True and scene_ok,
            f"keys={len(snap)}/24 tick={snap.get('tick')} "
            f"rev={snap.get('view_revision')}",
        )
        tick0 = int(snap.get("tick", -1))
        page.screenshot(path=str(EVIDENCE / "ui-02-connected.png"))

        # 3) 动作推进 ×3（tick / rev 单调 + 图像槽 + canvas）
        actions = [
            "和身边的角色打个招呼",
            "看看周围的场景",
            "继续当前场景的行动",
        ]
        steps_ok = True
        detail_parts: list[str] = []
        page.wait_for_timeout(400)
        for i, text in enumerate(actions, 1):
            done = False
            for _attempt in range(2):
                page.fill("#action-input", text)
                page.click("#action-btn")
                try:
                    page.wait_for_function(
                        "(tick) => document.getElementById('state-box')"
                        ".textContent.includes('\"tick\": ' + tick)",
                        arg=tick0 + i, timeout=12000,
                    )
                    done = True
                    break
                except Exception:  # noqa: BLE001
                    page.wait_for_timeout(500)
            snap = snap_text(page)
            rev = int(snap.get("view_revision", -1))
            note = page.text_content("#image-slot") or ""
            img_src = page.get_attribute("#image-view", "src") or ""
            ok_step = (
                int(snap.get("tick", -1)) == tick0 + i
                and rev > 0 and "artifact" in note
                and img_src.startswith("data:image/")
            )
            steps_ok = steps_ok and ok_step and done
            detail_parts.append(
                f"a{i}:tick={snap.get('tick')} rev={rev} "
                f"img={'yes' if img_src else 'no'}"
            )
            page.screenshot(
                path=str(EVIDENCE / f"ui-0{i + 2}-action-{i}.png")
            )
        record("ui_action_advances", steps_ok, " ".join(detail_parts))

        # 4) 错误面：不存在会话
        page.fill("#session-input", "f" * 32)
        page.click("#connect-btn")
        try:
            page.wait_for_function(
                "document.getElementById('state-box').textContent"
                ".startsWith('错误：')",
                timeout=10000,
            )
            bad_ok = True
        except Exception:  # noqa: BLE001
            bad_ok = False
        record("ui_bad_session_error", bad_ok, "404 信封 error_message 透传")
        page.screenshot(path=str(EVIDENCE / "ui-06-bad-session.png"))

        # 5) 保留面：inspector / workbench 404 披露
        page.fill("#session-input", sid)
        page.click("#connect-btn")
        page.wait_for_function(
            "document.getElementById('state-box').textContent"
            ".includes('\"started\": true')",
            timeout=15000,
        )
        page.click("#inspector-btn")
        try:
            page.wait_for_function(
                "document.getElementById('state-box').textContent"
                ".startsWith('错误：')",
                timeout=10000,
            )
            insp_ok = True
        except Exception:  # noqa: BLE001
            insp_ok = False
        record("ui_inspector_404_disclosed", insp_ok, "保留数据面披露")
        page.screenshot(path=str(EVIDENCE / "ui-07-inspector-404.png"))

        page.click("#workbench-btn")
        try:
            page.wait_for_function(
                "document.getElementById('workbench-view')"
                ".textContent.startsWith('错误：')",
                timeout=10000,
            )
            wb_ok = True
        except Exception:  # noqa: BLE001
            wb_ok = False
        record("ui_workbench_404_disclosed", wb_ok, "保留数据面披露")
        page.screenshot(path=str(EVIDENCE / "ui-08-workbench-404.png"))

        browser.close()

    all_ok = all(c["ok"] for c in checks.values())
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "port": args.port,
        "session": sid,
        "all_ok": all_ok,
        "screenshots": sorted(
            str(x.name) for x in EVIDENCE.glob("ui-*.png")
        ),
        "checks": checks,
    }
    out = _ROOT / "acceptance" / "ui-report.json"
    out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"总体 = {'PASS' if all_ok else 'FAIL'}（报告 = {out}）")
    print(f"截图 = {EVIDENCE}（ui-*.png）")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
