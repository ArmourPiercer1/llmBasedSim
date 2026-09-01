#!/usr/bin/env python3
"""v2 v1 迁移器 CLI 入口（薄壳；逻辑面 = src/engine_v2/modules/
v1_migration.py；SOT §3.15.4 L954 薄壳先例 scripts/v2_devcontrol.py）。

用法（两模式互斥）：

- 项目模式：  python scripts/v2_migrate_v1.py <v1.yaml> <out_dir>
- 仿真模式：  python scripts/v2_migrate_v1.py --simulation <yaml>

stdout = JSON report（``json.dumps``，ensure_ascii=False；
``MigrationReport`` 4 字段；diagnostics = 4 键 dict 列表
code/severity/path/message；output_files = 相对路径列表）。

退出码（钉死，SOT §3.15.1 L874–875）：0 = status migrated；
2 = status incompatible；1 = 用法错误。

DEV-W5-8 裁决：argparse 默认 usage 错退出 = 2，与 SOT「1 = 用法错误」
冲突 → ``_MigratingArgumentParser.error`` 覆盖 exit 1；``--help`` = 0
（argparse 标准面，不覆盖）。输入前置条件（输入缺失 / 根非 dict /
YAML 解析失败——模块面 ``FileNotFoundError`` / ``TypeError``）→
stderr 消息 + exit 1（用法错误族，零诊断码）。
备选（否）：维持 argparse 默认 usage 错 exit 2（否因：SOT
§3.15.1 L874–875 钉死 1 = 用法错误，默认 2 与之冲突）。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import asdict
from typing import NoReturn

from src.engine_v2.modules.v1_migration import (
    MigrationReport,
    migrate_project,
    migrate_simulation,
)

_PROG = "v2_migrate_v1.py"


class _MigratingArgumentParser(argparse.ArgumentParser):
    """usage 错 exit = 1（DEV-W5-8 裁决；argparse 默认 exit 2 覆盖）。"""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(1, f"{_PROG}: error: {message}\n")


def _report_to_dict(report: MigrationReport) -> dict[str, object]:
    """报告 JSON 面（4 字段；diagnostics = 4 键 dict 列表）。"""
    payload = asdict(report)
    return {
        "input_path": payload["input_path"],
        "status": payload["status"],
        "diagnostics": [
            {
                "code": d["code"],
                "severity": d["severity"],
                "path": d["path"],
                "message": d["message"],
            }
            for d in payload["diagnostics"]
        ],
        "output_files": list(payload["output_files"]),
    }


def _run(
    factory: Callable[[], MigrationReport],
    parser: _MigratingArgumentParser,
) -> MigrationReport:
    """入口调用 + 前置条件出口面（exit 1 = 用法错误族）。"""
    try:
        return factory()
    except (FileNotFoundError, TypeError) as exc:
        print(f"{_PROG}: error: {exc}", file=sys.stderr)
        parser.exit(1)


def main(argv: list[str]) -> int:
    """CLI 主面（退出码 0/2/1 钉死；SOT §3.15.1 L874–875）。"""
    parser = _MigratingArgumentParser(
        prog=_PROG,
        description=(
            "v1 单文件项目 / simulation.yaml → v2 分节项目迁移（薄壳；"
            "逻辑面 = src/engine_v2/modules/v1_migration.py）"
        ),
    )
    parser.add_argument(
        "v1_yaml",
        nargs="?",
        help="v1 单文件项目 yaml 路径（项目模式）",
    )
    parser.add_argument(
        "out_dir",
        nargs="?",
        help="v2 输出目录（项目模式；自动创建 exist_ok）",
    )
    parser.add_argument(
        "--simulation",
        metavar="YAML",
        help="simulation.yaml 路径（仿真模式；与项目模式互斥）",
    )
    args = parser.parse_args(argv)

    if args.simulation and (args.v1_yaml is not None or args.out_dir is not None):
        parser.error("--simulation 与项目模式（v1.yaml + out_dir）互斥")
    if args.simulation is not None:
        report = _run(lambda: migrate_simulation(args.simulation), parser)
    elif args.v1_yaml is not None and args.out_dir is not None:
        report = _run(lambda: migrate_project(args.v1_yaml, args.out_dir), parser)
    else:
        parser.error(
            "用法: v2_migrate_v1.py <v1.yaml> <out_dir> "
            "| --simulation <yaml>"
        )
    print(json.dumps(_report_to_dict(report), ensure_ascii=False))
    return 0 if report.status == "migrated" else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
