#!/usr/bin/env python3
"""0.1.0-alpha.1 最小 alpha runner（M4.1；production-only，零 tests 依赖）。

用法：
    PYTHONPATH=. .venv/bin/python scripts/v2_alpha_run.py \
        --root tests/fixtures/alpha_contract \
        --action "adjust_reading:ent_authoring_operator" \
        --ticks 2

确定性输入序列 = 声明序动作（每动作一步调度）+ 尾部纯 advance tick 数；
同一 (root, 动作序列, ticks) 双跑 → 世界字节相等（K7；E2E a12 机械断言）。

退出码：0 正常 / 1 装配 fatal（诊断显式打印）/ 2 参数错。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.engine_v2.content.schemas import DiagnosticSeverity
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.serialization import dump_json
from src.engine_v2.runtime import assemble_project


def _parse_action(spec: str) -> tuple[str, str]:
    action_id, _, entity_id = spec.partition(":")
    if not action_id or not entity_id:
        raise ValueError(f"--action 形状须为 'action_id:entity_id'（收到 {spec!r}）")
    return action_id, entity_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="0.1.0-alpha.1 最小 production runner")
    parser.add_argument("--root", required=True, help="GameProject 根目录")
    parser.add_argument(
        "--action",
        action="append",
        default=[],
        metavar="ACTION_ID:ENTITY_ID",
        help="脚本动作（可重复；执行序 = 声明序）",
    )
    parser.add_argument("--ticks", type=int, default=3, help="尾部 advance tick 数（缺省 3）")
    parser.add_argument("--dump", metavar="FILE", help="最终世界 dump_json 写文件（可选）")
    parser.add_argument("--no-trust-python", action="store_true", help="禁用受信 Python 扩展")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not (root / "game.yaml").is_file():
        print(f"[runner] root 下无 game.yaml：{root}", file=sys.stderr)
        return 2
    if args.ticks < 0:
        print("[runner] --ticks 须 >= 0", file=sys.stderr)
        return 2
    try:
        actions = [_parse_action(a) for a in args.action]
    except ValueError as exc:
        print(f"[runner] {exc}", file=sys.stderr)
        return 2

    # —— 装配（production 单入口）——
    result = assemble_project(str(root), trust_python=not args.no_trust_python)
    for d in result.diagnostics:
        if d.severity is DiagnosticSeverity.ERROR:
            print(f"[assembly] ERROR {d.code} {d.path}: {d.message}", file=sys.stderr)
        else:
            print(f"[assembly] warning {d.code} {d.path}: {d.message}", file=sys.stderr)
    if result.engine is None:
        print("[runner] 装配 fatal——无引擎，退出 1。", file=sys.stderr)
        return 1
    engine = result.engine
    world = engine.instance.world
    print(f"[runner] 装配完成：entities={len(world.entities)} revision={int(world.world_revision)}")

    # —— 确定性输入序列：动作（声明序）——
    # 注：WorldInstance.world 每次提交后返回**新** WorldState 对象（不可变
    # 状态机）——每行输出前重新取引用，杜绝 stale 投影。
    for action_id, entity_id in actions:
        r = engine.submit_action(EntityId(entity_id), action_id, {})
        committed = sum(
            len(t.effects) for t in r.transactions if t.status.name == "COMMITTED"
        )
        print(
            f"[action] {action_id} @ {entity_id}: ok={r.ok} "
            f"committed_effects={committed} revision={r.world_revision}"
        )
        for d in r.diagnostics:
            print(f"[action-diag] {d}")

    # —— 尾部 advance ——
    for i in range(args.ticks):
        r = engine.advance(1)
        world = engine.instance.world
        print(
            f"[tick] +1: ok={r.ok} revision={r.world_revision} "
            f"world_variables={json.dumps(world.world_variables, sort_keys=True, ensure_ascii=False)}"
        )
        for d in r.diagnostics:
            print(f"[tick-diag] {d}")

    # —— 终态摘要 ——
    world = engine.instance.world
    print(f"[final] revision={int(world.world_revision)}")
    for eid in sorted(world.entities):
        comps = {str(ct): data for ct, data in world.entities[eid].components.items()}
        print(f"[entity] {eid} components={json.dumps(comps, sort_keys=True, ensure_ascii=False)}")
    if args.dump:
        Path(args.dump).write_text(dump_json(world), encoding="utf-8")
        print(f"[dump] 写 {args.dump}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
