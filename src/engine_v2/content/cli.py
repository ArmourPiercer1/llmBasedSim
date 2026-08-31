"""engine_v2 content 层 P5 命令行入口 ``llmsim validate``（P5-T09 / W6，
设计文档 §3.7）。

依据 ``docs/v2/contracts/P5-project-format-module-plugin-dsl-design.md``（P5-DESIGN
冻结态）§3.7 字段级规格（4 导出，§8.2 L899 台账逐名逐序）：

- **定位**：``llmsim validate`` 入口。导入面 = ``argparse`` / ``sys`` /
  ``loader`` / ``project_ir`` / ``validator`` + 渲染用 stdlib（``json`` /
  ``pathlib`` / ``typing``）（§3.7 L450 定位条款）；``schemas.Diagnostic`` 仅
  类型标注面（``TYPE_CHECKING`` 守卫，零运行时导入）；
- **never-raise**（main 面，K2 / P5-INV-2 的 CLI 投影）：``main`` 任何输入零
  抛出——usage 错自捕获 → stderr 一行 → 返回 2（A4：不 raise SystemExit，
  console wrapper 以返回值退出）；``-h/--help`` → 帮助文本 stdout → 返回 0
  （argparse 标准路径；SOT 静默 → 最保守解读，偏差台账 D-02）；
- **stdout 纪律**（D-P5-12）：``--json`` 模式 stdout = 且仅 = ``render_json``
  输出（4 键封闭 envelope）；human 模式 = ``render_human`` 每诊断一行 + 1 行
  汇总 ``llmsim validate: {e} error(s), {w} warning(s)``；任何模式下零其他
  stdout（usage 消息只走 stderr）；
- **退出码**：0 = 无 error 级诊断；1 = 任一 error 级诊断；2 = usage 错
  （无子命令 / 未知子命令 / 未知参数 / 缺参，全部自捕获）。

私有面（不入 ``__all__``）：``_UsageError`` / ``_HelpExit`` /
``_CollectingParser`` / ``_build_parser`` / ``_result_from_diagnostics``。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from src.engine_v2.content.loader import load_project
from src.engine_v2.content.project_ir import build_ir
from src.engine_v2.content.validator import (
    ValidationResult,
    sort_diagnostics,
    validate_project,
)

if TYPE_CHECKING:  # 仅类型标注面（§3.7 运行时导入面不含 schemas）
    from src.engine_v2.content.schemas import Diagnostic

__all__ = ["main", "run_validate", "render_human", "render_json"]

#: 程序名（argparse prog + usage 消息前缀；pyproject ``[project.scripts]``
#: 键同名，Leader 侧添加，本文件不触 pyproject）。
_PROGRAM = "llmsim"


# —— 私有：argparse 消息收集面（A4：usage 错零 SystemExit）——


class _UsageError(Exception):
    """收集后的 argparse usage 错（消息捕获；main 渲染 stderr 后返回 2）。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class _HelpExit(Exception):
    """帮助路径标记（argparse ``exit(0)``：帮助已渲染 stdout，main 返回 0）。"""


class _CollectingParser(argparse.ArgumentParser):
    """argparse 子类：``error`` / ``exit`` 全部转为内部异常（never-raise）。

    - ``error(message)`` → ``_UsageError(message)``（不写 stderr、不退出）；
    - ``exit(0)`` → ``_HelpExit``（argparse 标准帮助路径：帮助文本由
      HelpAction 先行渲染 stdout，本处不重复输出）；
    - ``exit(非 0)`` → ``_UsageError``（防御分支；正常路径不经过）。
    """

    def error(self, message: str) -> argparse.ArgumentError:  # noqa: ARG002
        raise _UsageError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        if status == 0:
            raise _HelpExit()
        raise _UsageError(message if message is not None else f"exit status {status}")


def _build_parser() -> argparse.ArgumentParser:
    """装配 ``llmsim validate <project_root> [--json]`` 命令树（§3.7 L454）。"""
    parser = _CollectingParser(prog=_PROGRAM)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser(
        "validate",
        help="校验项目（loader → build_ir → validate_project 全链）",
    )
    validate_parser.add_argument(
        "project_root",
        help="项目根目录（须含 game.yaml）",
    )
    validate_parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="stdout 输出 4 键封闭 JSON envelope（{ok, project, diagnostics, exit_code}）",
    )
    return parser


def _result_from_diagnostics(diagnostics: Sequence[Diagnostic]) -> ValidationResult:
    """加载 / IR 级失败 → ``ir=None`` 的 ValidationResult（尾部仍排序，D-P5-12）。"""
    ordered = sort_diagnostics(diagnostics)
    ok = all(d.severity != "error" for d in ordered)
    return ValidationResult(ok=ok, diagnostics=tuple(ordered), ir=None)


# —— 公共面（4 导出，§8.2 L899 台账逐名逐序）——


def main(argv: Sequence[str] | None = None) -> int:
    """``llmsim`` CLI 入口（§3.7 L454）。

    - ``argv=None`` → ``sys.argv[1:]``（console script 口径：pyproject
      ``[project.scripts] llmsim = "src.engine_v2.content.cli:main"``，
      Leader 侧添加）；
    - usage 错（无子命令 / 未知子命令 / 未知参数 / 缺参）= 自捕获 →
      stderr 一行 ``llmsim: usage error: {message}`` → 返回 2（A4：零
      SystemExit；stderr 纪律不受 D-P5-12 stdout 条款约束）；
    - ``-h/--help`` = 帮助文本 → stdout，返回 0（argparse 标准路径）；
    - 正常路径 → ``run_validate``（返回 0/1）。
    """
    if argv is None:
        argv = sys.argv[1:]
    parser = _build_parser()
    try:
        args = parser.parse_args(list(argv))
    except _UsageError as exc:
        sys.stderr.write(f"{_PROGRAM}: usage error: {exc.message}\n")
        return 2
    except _HelpExit:
        return 0
    if args.command != "validate":
        sys.stderr.write(f"{_PROGRAM}: usage error: missing command\n")
        return 2
    return run_validate(args.project_root, as_json=args.as_json)


def run_validate(project_root: str | Path, as_json: bool = False) -> int:
    """执行全链校验并渲染输出（§3.7 L456；A5 分支序 = SOT 字面序）。

    - ``load_project`` → ``raw=None``（加载失败：root 不存在 / v1 形状 /
      YAML 级失败）→ 以 raw 级诊断成 ``ValidationResult(ir=None)``；
    - 否则 ``build_ir`` → ``ir=None``（IR 构建失败）→ 同上；
    - 否则 ``validate_project(ir, raw)``（全 8 导出编排面）；
    - 输出（D-P5-12）：``--json`` → stdout = 且仅 = ``render_json``；human →
      ``render_human`` 每诊断一行 + 末行汇总
      ``llmsim validate: {e} error(s), {w} warning(s)``；
    - 退出码 = 任一 error 级诊断则 1，否则 0（usage 退出码 2 只在 main 面）。
    """
    loaded = load_project(Path(project_root))
    if loaded.raw is None:
        result = _result_from_diagnostics(loaded.diagnostics)
    else:
        built = build_ir(loaded.raw)
        if built.ir is None:
            result = _result_from_diagnostics(built.diagnostics)
        else:
            result = validate_project(built.ir, loaded.raw)

    errors = sum(1 for d in result.diagnostics if d.severity == "error")
    warnings = sum(1 for d in result.diagnostics if d.severity == "warning")

    if as_json:
        sys.stdout.write(render_json(result, str(project_root)))
    else:
        human = render_human(result.diagnostics)
        if human:
            sys.stdout.write(human + "\n")
        sys.stdout.write(f"llmsim validate: {errors} error(s), {warnings} warning(s)\n")
    return 1 if errors else 0


def render_human(diagnostics: Sequence[Diagnostic]) -> str:
    """人读行渲染（§3.7 L457）：每诊断一行 ``[ERROR|WARNING] {code} {path}: {message}``。

    行序 = ``sort_diagnostics`` 排序后序（D-P5-12）；返回纯行内容（``\\n`` 拼接、
    无尾部换行）——汇总行由 ``run_validate`` 渲染（A6）；空输入 → 空串（human
    模式此时 stdout 仅 1 行汇总）。
    """
    return "\n".join(
        f"[{'ERROR' if d.severity == 'error' else 'WARNING'}] {d.code} {d.path}: {d.message}"
        for d in sort_diagnostics(diagnostics)
    )


def render_json(result: ValidationResult, project: str) -> str:
    """JSON envelope 渲染（§3.7 L458，D-P5-12 4 键封闭集）。

    ``json.dumps`` 对象 = ``ok``（= ``result.ok``）、``project``（= 入参）、
    ``diagnostics``（= 各 ``d.model_dump()`` 之 list，已排序）、``exit_code``
    （= 0 if ``result.ok`` else 1；``result`` 的纯函数——usage 退出码 2 永不
    到达本函数）；参数 = ``ensure_ascii=False, indent=2, sort_keys=True``；
    尾部换行。纯 stdout 可 ``json.loads``（断言 #13 / #2）。
    """
    envelope = {
        "ok": result.ok,
        "project": project,
        "diagnostics": [d.model_dump() for d in result.diagnostics],
        "exit_code": 0 if result.ok else 1,
    }
    return json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":  # §6.5 三态冒烟面（gate ⑥ 降级条款）：python -m 入口
    raise SystemExit(main())
