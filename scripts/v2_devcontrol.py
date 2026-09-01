#!/usr/bin/env python3
"""v2 dev control plane CLI 入口（薄壳；逻辑面 = src/engine_v2/devtools/cli.py）。"""
import sys
from src.engine_v2.devtools.cli import run_devcontrol_cli

if __name__ == "__main__":
    sys.exit(run_devcontrol_cli(sys.argv[1:]))
