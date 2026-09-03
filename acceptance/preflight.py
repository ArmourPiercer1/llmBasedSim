"""G10 验收机械前置（preflight）：环境 + 套件 + 纪律面自动判定。

运行 = ``PYTHONPATH=. .venv/bin/python acceptance/preflight.py``
（仓库根）。报告 = ``acceptance/preflight-report.json``。
退出码 = 0 全绿 / 1 有红项。
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
VENV_PY = _ROOT / ".venv" / "bin" / "python"
EVIDENCE = _ROOT / "docs" / "v2" / "gates" / "evidence-g10"

EXPECTED_FULL = 3205

TARGETED = {
    "S1 T01 view": "tests/engine_v2/presentation/test_view.py",
    "S2 T02 narrator": "tests/engine_v2/presentation/test_narrator.py",
    "S3 T03 render_intent": "tests/engine_v2/presentation/test_render_intent.py",
    "S4 T04 image_backend": "tests/engine_v2/presentation/test_image_backend.py",
    "S5 tactical": "tests/engine_v2/presentation/test_tactical_layout.py",
    "S6 T05 session+api": "tests/engine_v2/adapters/web/test_session_manager.py tests/engine_v2/adapters/web/test_web_api.py",
    "S7 T06 inspector": "tests/engine_v2/adapters/web/test_inspector.py",
    "S8 T07 workbench": "tests/engine_v2/adapters/web/test_workbench.py",
    "S9 G10 gate": "tests/engine_v2/adapters/web/test_g10_gate.py",
    "S10 face": "tests/engine_v2/adapters/web/test_p10_face.py",
    "S11 boundary": "tests/engine_v2/core/test_import_boundary.py",
}
EXPECTED_TARGETED = {
    "S1 T01 view": 7,
    "S2 T02 narrator": 5,
    "S3 T03 render_intent": 5,
    "S4 T04 image_backend": 8,
    "S5 tactical": 3,
    "S6 T05 session+api": 11,
    "S7 T06 inspector": 4,
    "S8 T07 workbench": 4,
    "S9 G10 gate": 4,
    "S10 face": 6,
    "S11 boundary": 44,
}

#: P10 src 19 文件（= test_p10_face.py::_P10_SRC_FILES 逐字；占位
#: presentation/__init__.py 属 P10 前冻结面，face t1 明确剔除）。
P10_SRC_FILES: tuple[str, ...] = (
    "src/engine_v2/presentation/view.py",
    "src/engine_v2/presentation/text/__init__.py",
    "src/engine_v2/presentation/text/narrator.py",
    "src/engine_v2/presentation/image/__init__.py",
    "src/engine_v2/presentation/image/contract.py",
    "src/engine_v2/presentation/image/director.py",
    "src/engine_v2/presentation/image/backend.py",
    "src/engine_v2/presentation/tactical/__init__.py",
    "src/engine_v2/presentation/tactical/layout.py",
    "src/engine_v2/adapters/web/__init__.py",
    "src/engine_v2/adapters/web/session.py",
    "src/engine_v2/adapters/web/api.py",
    "src/engine_v2/adapters/web/inspector.py",
    "src/engine_v2/adapters/web/workbench.py",
    "src/engine_v2/adapters/web/views.py",
    "src/engine_v2/adapters/web/server.py",
    "src/engine_v2/adapters/web/static/index.html",
    "src/engine_v2/adapters/web/static/app.js",
    "src/engine_v2/adapters/web/static/styles.css",
)

#: K8 12 名闭集（= test_p10_face.py::_K8_BLACKLIST 逐字，P4 同源口径）。
K8_BLACKLIST: tuple[str, ...] = (
    "openai", "anthropic", "langchain", "litellm", "ollama", "gemini",
    "gpt", "claude", "llm", "provider", "api_key", "base_url",
)
#: t3 唯一允许命中（ERR-P10-10：narrator.py TEXT_SOURCES 钉元组）。
K8_ALLOWED_HIT = (
    "src/engine_v2/presentation/text/narrator.py", "llm", "llm",
)
_K8_WB = chr(92) + "b"


def sh(args: list[str]) -> str:
    proc = subprocess.run(
        args, cwd=_ROOT, capture_output=True, text=True
    )
    return proc.stdout.strip() + proc.stderr.strip()


def parse_passed(tail: str) -> tuple[int, int]:
    m = re.search(r"(\d+) passed", tail)
    passed = int(m.group(1)) if m else 0
    failed = len(re.findall(r"\d+ failed", tail))
    failed = int(re.search(r"(\d+) failed", tail).group(1)) if failed else 0
    return passed, failed


def main() -> int:
    checks: dict[str, dict[str, object]] = {}

    head = sh(["git", "rev-parse", "HEAD"])
    branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    dirty = sh(["git", "status", "--porcelain"])
    tracked_dirty = [
        line for line in dirty.splitlines() if not line.startswith("??")
    ]
    checks["env_head"] = {
        "head": head,
        "branch": branch,
        "ok": branch == "architecture-v2" and not tracked_dirty,
        "detail": f"tracked 未提交 = {tracked_dirty or '零'}",
    }

    tail = sh([
        str(VENV_PY), "-m", "pytest", "tests/", "-q",
        "-p", "no:cacheprovider",
    ])
    passed, failed = parse_passed(tail)
    checks["full_suite"] = {
        "passed": passed, "failed": failed,
        "expected": EXPECTED_FULL,
        "ok": passed == EXPECTED_FULL and failed == 0,
        "tail": tail.splitlines()[-1] if tail else "",
    }

    targeted: dict[str, object] = {}
    for name, paths in TARGETED.items():
        t = sh([
            str(VENV_PY), "-m", "pytest", *paths.split(), "-q",
            "-p", "no:cacheprovider",
        ])
        p, f = parse_passed(t)
        exp = EXPECTED_TARGETED[name]
        targeted[name] = {
            "passed": p, "failed": f, "expected": exp,
            "ok": p == exp and f == 0,
        }
    checks["targeted"] = targeted

    wide = []
    for rel in P10_SRC_FILES:
        for lineno, line in enumerate(
            (_ROOT / rel).read_text(encoding="utf-8").splitlines(), 1
        ):
            if len(line) > 100:
                wide.append(f"{rel}:{lineno}")
    checks["line_width"] = {
        "ok": not wide, "hits": wide[:10],
    }

    control = [rel for rel in P10_SRC_FILES
               if "\x5c\x62" in (_ROOT / rel).read_text("utf-8")]
    checks["control_bytes"] = {"ok": not control, "hits": control}

    k8_hits: set[tuple[str, str, str]] = set()

    def _scan(rel: str, text: str) -> None:
        folded = text.casefold()
        for name in K8_BLACKLIST:
            if re.search(_K8_WB + re.escape(name) + _K8_WB, folded):
                k8_hits.add((rel, name, text))

    for rel in P10_SRC_FILES:
        path = _ROOT / rel
        if rel.endswith(".py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(
                    node.value, str
                ):
                    _scan(rel, node.value)
        else:
            _scan(rel, path.read_text(encoding="utf-8"))
    checks["k8_scan"] = {
        "ok": k8_hits == {K8_ALLOWED_HIT},
        "hits": sorted(k8_hits),
        "expected": [list(K8_ALLOWED_HIT)],
    }

    all_ok = all(
        c.get("ok") if isinstance(c, dict) else c
        for c in checks.values()
        if not isinstance(c, dict) or "ok" in c
    )
    all_ok = all_ok and all(v["ok"] for v in targeted.values())

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "all_ok": all_ok,
        "checks": checks,
    }
    (_ROOT / "acceptance").mkdir(exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = _ROOT / "acceptance" / "preflight-report.json"
    out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"== G10 preflight ==  head={head[:9]} branch={branch}")
    for name, val in checks.items():
        if name == "targeted":
            for tname, tv in val.items():
                mark = "PASS" if tv["ok"] else "FAIL"
                print(f"  [{mark}] {tname}: {tv['passed']}/{tv['expected']}")
            continue
        mark = "PASS" if val["ok"] else "FAIL"
        detail = val.get("tail") or val.get("detail") or ""
        print(f"  [{mark}] {name}: {detail}")
    print(f"总体 = {'PASS' if all_ok else 'FAIL'}（报告 = {out}）")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
