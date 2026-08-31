"""P5 集成测试：SOT §6.5 CLI 子进程冒烟 + 两 fixture 端到端 + K7 往返。

- SOT 锚：``docs/v2/contracts/P5-project-format-module-plugin-dsl-design.md``
  §6.5 L801-807（``test_cli.py`` 单元无子进程；本文件 = 子进程冒烟）；
- 子进程调用面 = ``[sys.executable, "-m", "src.engine_v2.content.cli", ...]``
  （console script 装配等价面；A8：cwd = 仓库根。gate 运行序 ⑥ 降级条款：
  本环境 ``llmsim`` console script 未装配（Leader 域：pyproject.toml
  [project.scripts]），冒烟按 SOT 降级为 ``-m`` 面，报告披露）；
- 端到端：load_project → build_ir → validate_project → cli.main，参考
  fixture 两例（zero_python / plugin_local 净面）+ broken（诊断面）；
- K7 往返：canonical_yaml → safe_load → model_validate == ir（断言 #20 同源）。
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import yaml

from src.engine_v2.content.cli import main
from src.engine_v2.content.loader import load_project
from src.engine_v2.content.project_ir import ProjectIR, build_ir, canonical_yaml
from src.engine_v2.content.validator import validate_project
from src.engine_v2.plugins.registry import discover_local_plugins

_REPO_ROOT = Path(__file__).resolve().parents[3]

# broken fixture 全链 7 条诊断的码多重集（§3.12 #38/#39 设计面）。
_BROKEN_EXPECTED_CODES = (
    "LLMSIM_DEPLOYMENT_FIELD",
    "LLMSIM_DEPLOYMENT_FIELD",
    "LLMSIM_DEPLOYMENT_FIELD",
    "LLMSIM_DEPLOYMENT_FIELD",
    "LLMSIM_DUPLICATE_ID",
    "LLMSIM_PLUGIN_ENTRY_UNRESOLVED",
    "LLMSIM_UNRESOLVED_REF",
)


def _chain(root: Path) -> tuple[object, object, object]:
    """load_project → build_ir → validate_project（raw/ir 非 None 断言内置）。"""
    loaded = load_project(root)
    assert loaded.raw is not None, f"raw is None: {loaded.diagnostics}"
    built = build_ir(loaded.raw)
    assert built.ir is not None, f"ir is None: {built.diagnostics}"
    result = validate_project(built.ir, loaded.raw)
    return loaded, built, result


def _subprocess_cli(*argv: str) -> subprocess.CompletedProcess[str]:
    """``-m`` 面子进程调用（A8：cwd = 仓库根，console script 装配等价面）。"""
    return subprocess.run(
        [sys.executable, "-m", "src.engine_v2.content.cli", *argv],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_e2e_zero_python_clean_chain(zero_python_project: Path) -> None:
    """端到端（净）：zero_python 全链零诊断，main validate 退出码 0。"""
    _loaded, _built, result = _chain(zero_python_project)
    assert result.diagnostics == ()
    assert result.ok is True
    code = main(["validate", str(zero_python_project)])
    assert code == 0


def test_e2e_plugin_local_clean_chain(plugin_project: Path) -> None:
    """端到端（净）：plugin_local 全链零诊断，本地插件已注册，main 退出码 0。"""
    loaded, _built, result = _chain(plugin_project)
    assert result.diagnostics == ()
    assert result.ok is True
    registry, diags = discover_local_plugins(loaded.raw)
    assert diags == ()
    assert set(registry.plugins) == {"infection"}
    code = main(["validate", str(plugin_project)])
    assert code == 0


def test_e2e_broken_diagnostic_face(broken_project: Path) -> None:
    """端到端（坏）：broken 全链恰 7 条诊断（码多重集精确），main 退出码 1。"""
    _loaded, _built, result = _chain(broken_project)
    assert result.ok is False
    assert sorted(d.code for d in result.diagnostics) == sorted(_BROKEN_EXPECTED_CODES)
    errors = [d for d in result.diagnostics if d.severity == "error"]
    warnings = [d for d in result.diagnostics if d.severity == "warning"]
    assert len(errors) == 6
    assert len(warnings) == 1
    assert warnings[0].code == "LLMSIM_PLUGIN_ENTRY_UNRESOLVED"
    code = main(["validate", str(broken_project)])
    assert code == 1

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["validate", str(broken_project), "--json"])
    data = json.loads(buf.getvalue())
    assert rc == 1
    assert data["exit_code"] == 1
    assert len(data["diagnostics"]) == 7


def test_canonical_yaml_round_trip_both_fixtures(
    zero_python_project: Path, plugin_project: Path
) -> None:
    """K7 往返（断言 #20 同源）：两参考 fixture 规范化 YAML 往返等值 + 双 dump 稳。"""
    for root in (zero_python_project, plugin_project):
        _loaded, built, _result = _chain(root)
        ir = built.ir
        text1 = canonical_yaml(ir)
        ir2 = ProjectIR.model_validate(yaml.safe_load(text1))
        assert ir2 == ir
        assert canonical_yaml(ir2) == text1


def test_subprocess_three_state_smoke(
    zero_python_project: Path, broken_project: Path
) -> None:
    """子进程三态冒烟（§6.5 / A8）：``-m`` 面退出码 0（净）/ 1（坏）/ 2（用法错）。"""
    clean = _subprocess_cli("validate", str(zero_python_project))
    assert clean.returncode == 0
    assert clean.stderr == ""
    assert clean.stdout.endswith("llmsim validate: 0 error(s), 0 warning(s)\n")

    broken = _subprocess_cli("validate", str(broken_project))
    assert broken.returncode == 1
    assert broken.stderr == ""
    assert broken.stdout.endswith("llmsim validate: 6 error(s), 1 warning(s)\n")

    usage = _subprocess_cli()
    assert usage.returncode == 2
    assert usage.stdout == ""
    assert usage.stderr.startswith("llmsim: usage error: ")
