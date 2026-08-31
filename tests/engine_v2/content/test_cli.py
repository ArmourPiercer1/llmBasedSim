"""P5-T09（W6）``content/cli.py`` 单测（设计文档 §6.1 L746 / §3.7；单元，
无子进程——子进程三态冒烟归 ``test_p5_integration.py``，§6.5）。

用例族（§6.1 L746 行逐条落地）：

- **退出码三态**（断言 #15）：clean fixture → 0；broken fixture → 1；
  usage 错（无子命令 / 未知子命令 / 缺参 / 未知参数）→ 2（A4：自捕获，
  零 SystemExit，stderr 一行）；
- **--json stdout 纯 JSON + 键集封闭**（断言 #13）：stdout 整体可
  ``json.loads``（纯 stdout 纪律 D-P5-12），键集 = 4 键封闭 envelope
  ``{ok, project, diagnostics, exit_code}``；
- **双跑字节相等**（断言 #14）：broken ``--json`` 两次运行 stdout 字节
  相等 ∧ diagnostics 序列已按 (code, path, message) 排序；
- **usage = 2**：stderr 渲染 + stdout 零输出；
- **run_validate 无 sys.exit 面**：返回 int 可单测（0/1 两态 + 加载失败
  1 态），零抛出。

hermetic：零网络、零大模型调用；stdout/stderr 全部捕获（不污染测试输出）。
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

from src.engine_v2.content import cli as cli_module
from src.engine_v2.content.cli import (
    main,
    render_human,
    render_json,
    run_validate,
)
from src.engine_v2.content.validator import validate_project
from src.engine_v2.content.loader import load_project
from src.engine_v2.content.project_ir import build_ir
from tests.engine_v2.content.conftest import (
    make_character,
    make_diagnostic,
    make_ir,
    make_plugin_descriptor,
    make_raw_project,
)

#: 4 键封闭 envelope（§3.7 L458，断言 #13 键集面）。
_JSON_KEYS = frozenset({"ok", "project", "diagnostics", "exit_code"})


# —— 私有 helper ——


def _run_main(argv: list[str]) -> tuple[int, str, str]:
    """main(argv) 带 stdout/stderr 捕获（返回 rc, stdout, stderr）。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(argv)
    return rc, out.getvalue(), err.getvalue()


def _run_validate(root: Path, as_json: bool = False) -> tuple[int, str]:
    """run_validate(root) 带 stdout 捕获（返回 rc, stdout）。"""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = run_validate(root, as_json=as_json)
    return rc, out.getvalue()


# —— 公共面（扁平测试函数，零测试类）——


def test_cli_all_ledger_order() -> None:
    """__all__ = 4 名，§8.2 L899 台账逐名逐序（W6 交付物面钉死）。"""
    assert cli_module.__all__ == ["main", "run_validate", "render_human", "render_json"]


def test_exit_code_three_state(
    zero_python_project: Path, broken_project: Path
) -> None:
    """退出码三态（断言 #15 / §6.5）：clean=0 / broken=1 / usage=2。"""
    rc_clean, out_clean, _ = _run_main(["validate", str(zero_python_project)])
    assert rc_clean == 0
    # human 模式 stdout 纪律：零诊断 → 仅 1 行汇总（D-P5-12）
    assert out_clean == "llmsim validate: 0 error(s), 0 warning(s)\n"

    rc_broken, _, _ = _run_main(["validate", str(broken_project)])
    assert rc_broken == 1

    for argv in ([], ["frobnicate"], ["validate"], ["validate", "x", "--bogus"]):
        rc, out, err = _run_main(argv)
        assert rc == 2, f"usage 错 {argv} 应返回 2，实际 {rc}"
        assert out == "", f"usage 错 {argv} 的 stdout 必须为空"
        assert err.startswith("llmsim: usage error: "), f"usage 错 {argv} 的 stderr 前缀"


def test_json_stdout_pure_json_key_set_closed(
    zero_python_project: Path, broken_project: Path
) -> None:
    """--json stdout = 且仅 = render_json 输出；4 键封闭 envelope（断言 #13）。"""
    rc_broken, out_broken, _ = _run_main(
        ["validate", str(broken_project), "--json"]
    )
    assert rc_broken == 1
    # 纯 stdout：整个 stdout 可 json.loads（零非 JSON 字节，D-P5-12）
    data: dict[str, Any] = json.loads(out_broken)
    assert set(data.keys()) == _JSON_KEYS
    assert data["ok"] is False
    assert data["exit_code"] == 1
    assert data["project"] == str(broken_project)
    assert isinstance(data["diagnostics"], list)
    assert data["diagnostics"], "broken 项目诊断集非空"

    rc_clean, out_clean, _ = _run_main(
        ["validate", str(zero_python_project), "--json"]
    )
    assert rc_clean == 0
    data_clean = json.loads(out_clean)
    assert set(data_clean.keys()) == _JSON_KEYS
    assert data_clean["ok"] is True
    assert data_clean["exit_code"] == 0
    assert data_clean["diagnostics"] == []


def test_json_double_run_byte_equal(broken_project: Path) -> None:
    """双跑字节相等（断言 #14）：确定性输出（D-P5-15）+ 排序后序（D-P5-12）。"""
    _, first, _ = _run_main(["validate", str(broken_project), "--json"])
    _, second, _ = _run_main(["validate", str(broken_project), "--json"])
    assert first == second, "两次 --json 运行 stdout 必须字节相等"
    data = json.loads(first)
    keys = [
        (d["code"], d["path"], d["message"]) for d in data["diagnostics"]
    ]
    assert keys == sorted(keys), "diagnostics 序列必须已按 (code, path, message) 排序"


def test_run_validate_returns_int_no_sys_exit(
    zero_python_project: Path, broken_project: Path, tmp_path: Path
) -> None:
    """run_validate 无 sys.exit 面：返回 int（0/1），加载失败 = 1，零抛出。"""
    rc_clean, _ = _run_validate(zero_python_project)
    assert rc_clean == 0
    assert isinstance(rc_clean, int)

    rc_broken, out_broken = _run_validate(broken_project)
    assert rc_broken == 1
    # human 汇总行 = 末行（A6：render_human 仅行，汇总行由 run_validate 渲染）
    lines = out_broken.splitlines()
    assert lines[-1] == "llmsim validate: 6 error(s), 1 warning(s)"

    # 加载失败（root 不存在）→ FILE_MISSING error → 返回 1（零抛出）
    rc_missing, _ = _run_validate(tmp_path / "does_not_exist")
    assert rc_missing == 1

    # --json 面同样返回 int
    rc_json, out_json = _run_validate(broken_project, as_json=True)
    assert rc_json == 1
    json.loads(out_json)


def test_render_human_line_shape() -> None:
    """render_human：每诊断一行 [ERROR|WARNING] {code} {path}: {message}（排序后序）。"""
    diags = [
        make_diagnostic("LLMSIM_SCHEMA", "b.yaml", "乙"),
        make_diagnostic(
            "LLMSIM_PLUGIN_ENTRY_UNRESOLVED", "ghost", "未注册", severity="warning"
        ),
        make_diagnostic("LLMSIM_SCHEMA", "a.yaml", "甲"),
    ]
    rendered = render_human(diags)
    lines = rendered.split("\n")
    assert len(lines) == 3
    # 排序后序：LLMSIM_PLUGIN_ENTRY_UNRESOLVED < LLMSIM_SCHEMA（code 序）
    assert lines[0] == "[WARNING] LLMSIM_PLUGIN_ENTRY_UNRESOLVED ghost: 未注册"
    assert lines[1] == "[ERROR] LLMSIM_SCHEMA a.yaml: 甲"
    assert lines[2] == "[ERROR] LLMSIM_SCHEMA b.yaml: 乙"
    assert not rendered.endswith("\n")  # 纯行内容，无尾部换行
    assert render_human([]) == ""


def test_render_json_envelope_shape() -> None:
    """render_json：4 键封闭 + ensure_ascii=False/indent=2/sort_keys=True + 尾部换行。"""
    ir = make_ir(plugin_descriptors=(make_plugin_descriptor(id="ghost"),))
    result = validate_project(ir, make_raw_project(files={}))
    text = render_json(result, "proj_label")

    assert text.endswith("\n")
    data = json.loads(text)
    assert set(data.keys()) == _JSON_KEYS
    # 仅 warning → ok=True，exit_code = 0（result 的纯函数）
    assert data["ok"] is True
    assert data["exit_code"] == 0
    assert data["project"] == "proj_label"
    assert data["diagnostics"][0]["code"] == "LLMSIM_PLUGIN_ENTRY_UNRESOLVED"
    assert data["diagnostics"][0]["severity"] == "warning"

    # 排序键：indent=2 + sort_keys=True 的字节面（前 2 行锁定缩进与首键序）
    first_two = text.split("\n")[:2]
    assert first_two[0] == "{"
    assert first_two[1].startswith('  "diagnostics"')

    # 非 ASCII 不转义（ensure_ascii=False）：中文 message 原样出现
    assert "未在注册表" in text

    # exit_code = 1 面（error 级存在时）：DUPLICATE_ID 经 characters 池
    ir_err = make_ir(
        characters=(make_character(id="npc_x"), make_character(id="npc_x"))
    )
    result_err = validate_project(ir_err)
    data_err = json.loads(render_json(result_err, "p"))
    assert data_err["ok"] is False
    assert data_err["exit_code"] == 1


def test_full_chain_round_trip_through_cli(
    zero_python_project: Path, plugin_project: Path
) -> None:
    """CLI 面全链消费：两个参考 fixture 经 main 均零诊断（#2 同源数据，单元面）。"""
    for root in (zero_python_project, plugin_project):
        loaded = load_project(root)
        assert loaded.raw is not None
        built = build_ir(loaded.raw)
        assert built.ir is not None
        result = validate_project(built.ir, loaded.raw)
        assert result.diagnostics == ()
        rc, out, _ = _run_main(["validate", str(root), "--json"])
        assert rc == 0
        data = json.loads(out)
        assert data["ok"] is True
        assert data["exit_code"] == 0


def test_help_path_returns_zero() -> None:
    """-h/--help = argparse 标准帮助路径：stdout 帮助文本 + 返回 0（SOT 静默，
    最保守解读，偏差台账 D-02）。"""
    rc_top, out_top, err_top = _run_main(["--help"])
    assert rc_top == 0
    assert "usage:" in out_top
    assert err_top == ""

    rc_sub, out_sub, _ = _run_main(["validate", "--help"])
    assert rc_sub == 0
    assert "project_root" in out_sub
