#!/usr/bin/env python3
"""record_transcript.py — v1 reference transcript 记录器（任务包 P0-T04）。

用途
----
以与 ``src/main.py`` **完全相同**的加载/构图路径
（``ConfigLoader -> ChatOpenAI -> PromptLoader -> load_init_file /
init_file_to_game_state -> build_game_graph``）加载指定剧本与脚本化玩家
输入序列，逐 tick 执行，并把（输入、player_percept 摘要、event_log 增量、
关键 state diff）记录为 JSON transcript，写入
``docs/v2/reference/transcripts/<scenario>.json``。

v1 CLI 命令（/status、/save、/see 等）与 ``src/main.py`` 行为一致：由
主循环外壳处理、**不触发图 tick**，在本 transcript 中记为 ``kind:
"command"`` 条目。其中 ``/save <name>`` 的存档内容（与 v1
``saves/<name>.json`` 完全相同的 ``strip_transient_state`` 格式）会落盘到
``docs/v2/reference/transcripts/saves/``（只写任务允许目录，不碰仓库
``saves/``）。

用法（在仓库根目录下，只允许使用 .venv/bin/python）
----------------------------------------------------
    .venv/bin/python docs/v2/reference/record_transcript.py --help
    .venv/bin/python docs/v2/reference/record_transcript.py --selfcheck
    .venv/bin/python docs/v2/reference/record_transcript.py --scenario whisperheads
    .venv/bin/python docs/v2/reference/record_transcript.py --all

退出码
------
    0  成功（含 selfcheck 通过）
    1  运行时错误（加载失败 / LLM 或图执行异常 / transcript 写入失败）
    2  参数错误
    3  DEEPSEEK_API_KEY 缺失或仍为占位符（sk-your-...）——不得运行真实对局
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent            # <repo>/docs/v2/reference
REPO_ROOT = SCRIPT_DIR.parents[2]                       # <repo>
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 与 src/main.py 相同：从仓库根 .env 加载环境变量
from dotenv import load_dotenv  # noqa: E402

_ENV_PATH = REPO_ROOT / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)

# 与 src/main.py 相同的加载/构图路径
from src.agents.init import init_file_to_game_state, load_init_file  # noqa: E402
from src.config.loader import ConfigLoader  # noqa: E402
from src.graph.game_graph import build_game_graph  # noqa: E402
from src.graph.game_state import reset_tick_transients, strip_transient_state  # noqa: E402
from src.prompts.loader import PromptLoader  # noqa: E402

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BAD_ARGS = 2
EXIT_NO_API_KEY = 3

DEFAULT_OUT_DIR = SCRIPT_DIR / "transcripts"
INPUTS_DIR = SCRIPT_DIR / "inputs"
SCENARIOS: tuple[str, ...] = ("whisperheads", "murder", "test_empty")

# v1 主循环命令（见 src/main.py::collect_next_player_input）
V1_COMMANDS = {"/quit", "/exit", "/help", "/status", "/idid", "/see", "/hear", "/feel"}
SAVE_RE = re.compile(r"/save\s+([A-Za-z0-9_-]+)\Z")

_PLACEHOLDER_MARKERS = (
    "sk-your", "your-", "placeholder", "changeme", "xxxx",
    "todo", "fixme", "dummy", "example",
)


# ──────────────────────────────────────────────────────────────────────────
# 基础工具
# ──────────────────────────────────────────────────────────────────────────

def rel(path: Path) -> str:
    """相对仓库根的路径（用于 transcript 内引用）。"""
    try:
        return os.path.relpath(str(path), str(REPO_ROOT))
    except ValueError:
        return str(path)


def resolve_repo_path(p: str | Path) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


def classify_api_key(value: str | None) -> str:
    """返回 missing / placeholder / ok。只用于判定，绝不回显 key 内容。"""
    v = (value or "").strip()
    if not v:
        return "missing"
    low = v.lower()
    if any(m in low for m in _PLACEHOLDER_MARKERS):
        return "placeholder"
    return "ok"


def build_llm(sim_config: Any) -> Any:
    """与 src/main.py 完全一致的 ChatOpenAI 构造方式。"""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=sim_config.llm.model,
        base_url=sim_config.llm.base_url,
        api_key=os.environ.get(sim_config.llm.api_key_env),
        temperature=sim_config.llm.temperature,
        max_tokens=sim_config.llm.max_tokens,
    )


# ──────────────────────────────────────────────────────────────────────────
# transcript 摘要 / diff 工具
# ──────────────────────────────────────────────────────────────────────────

def _attr_value(attr: Any) -> Any:
    if isinstance(attr, dict):
        return attr.get("value", attr)
    return attr


def _attr_values(attributes: Any) -> dict[str, Any]:
    if not isinstance(attributes, dict):
        return {}
    return {k: _attr_value(v) for k, v in attributes.items()}


def summarize_percept(percept: Any) -> dict[str, Any] | None:
    """player_percept 摘要：保留 summary / self_action / senses / 属性快照。"""
    if not isinstance(percept, dict):
        return None
    return {
        "summary": percept.get("summary", ""),
        "self_action_summary": percept.get("self_action_summary", ""),
        "hidden_event_count": percept.get("hidden_event_count", 0),
        "senses": [
            {
                "sense": s.get("sense"),
                "description": s.get("description"),
                "source_object_id": s.get("source_object_id"),
                "confidence": s.get("confidence"),
            }
            for s in (percept.get("senses") or [])
        ],
        "player_attributes": percept.get("player_attributes") or {},
    }


def _attr_diff(before: Any, after: Any) -> dict[str, dict[str, Any]]:
    before = before if isinstance(before, dict) else {}
    after = after if isinstance(after, dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for k in set(before) | set(after):
        bv = _attr_value(before.get(k))
        av = _attr_value(after.get(k))
        if bv != av:
            out[k] = {"before": bv, "after": av}
    return out


def compute_state_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """关键 state diff：玩家/NPC 位置、玩家与 NPC 属性变化、背包、物体 state、时间。"""
    bp = (before.get("player") or {}).get("position")
    ap = (after.get("player") or {}).get("position")
    bcp = before.get("character_positions") or {}
    acp = after.get("character_positions") or {}
    moved = {
        cid: {"before": bcp.get(cid), "after": acp.get(cid)}
        for cid in set(bcp) | set(acp)
        if bcp.get(cid) != acp.get(cid)
    }
    bchars = before.get("characters") or {}
    achar = after.get("characters") or {}
    char_attr_changed = {
        cid: _attr_diff((bchars.get(cid) or {}).get("attributes"),
                        (achar.get(cid) or {}).get("attributes"))
        for cid in set(bchars) | set(achar)
    }
    char_attr_changed = {k: v for k, v in char_attr_changed.items() if v}
    bi = list((before.get("player") or {}).get("inventory") or [])
    ai = list((after.get("player") or {}).get("inventory") or [])
    bobjs = before.get("objects") or {}
    aobjs = after.get("objects") or {}
    obj_changed = {
        oid: {
            "before": (bobjs.get(oid) or {}).get("state"),
            "after": (aobjs.get(oid) or {}).get("state"),
        }
        for oid in set(bobjs) | set(aobjs)
        if (bobjs.get(oid) or {}).get("state") != (aobjs.get(oid) or {}).get("state")
    }
    return {
        "player_position": {"before": bp, "after": ap, "changed": bp != ap},
        "character_positions_moved": moved,
        "game_time": {"before": before.get("game_time"), "after": after.get("game_time")},
        "tick_duration_minutes": after.get("tick_duration_minutes"),
        "player_attributes_changed": _attr_diff(
            (before.get("player") or {}).get("attributes"),
            (after.get("player") or {}).get("attributes"),
        ),
        "character_attributes_changed": char_attr_changed,
        "inventory": {
            "added": [x for x in ai if x not in bi],
            "removed": [x for x in bi if x not in ai],
        },
        "object_state_changed": obj_changed,
        "action_continuation": after.get("action_continuation"),
    }


def build_status_payload(state: dict[str, Any]) -> dict[str, Any]:
    """/status 命令的确定性载荷（对应 src/main.py 中 renderer 的数据来源）。"""
    player = state.get("player") or {}
    positions = state.get("character_positions") or {}
    characters = state.get("characters") or {}
    return {
        "tick": state.get("tick"),
        "game_phase": state.get("game_phase"),
        "game_time": state.get("game_time"),
        "world_name": state.get("world_name"),
        "player": {
            "name": player.get("name"),
            "position": player.get("position"),
            "attributes": _attr_values(player.get("attributes")),
            "inventory": player.get("inventory") or [],
        },
        "characters": {
            cid: {
                "name": c.get("name"),
                "position": positions.get(cid),
                "attributes": _attr_values(c.get("attributes")),
            }
            for cid, c in characters.items()
        },
        "last_tick_duration_minutes": state.get("tick_duration_minutes"),
    }


_SENSE_CATEGORIES = {
    "see": ("sight",),
    "hear": ("sound",),
    "feel": ("touch", "smell"),
}


def handle_command(
    raw_input: str,
    scenario: str,
    current: dict[str, Any],
    out_dir: Path,
    index: int,
) -> dict[str, Any]:
    """按 src/main.py 的命令语义处理 CLI 命令（不触发图 tick）。"""
    cmd = raw_input.strip()
    lower = cmd.lower()
    record: dict[str, Any] = {
        "index": index,
        "tick_at_command": current.get("tick"),
        "kind": "command",
        "input": raw_input,
        "note": "v1 CLI 命令：由主循环外壳（src/main.py::collect_next_player_input）处理，不触发图 tick",
    }
    if lower in ("/quit", "/exit"):
        record["command"] = lower
        record["payload"] = {"action": "end_session"}
        return record
    if lower == "/help":
        record["command"] = lower
        record["payload"] = {"help": "命令: /quit 退出, /help 帮助, /save <name> 保存, /status 查看状态, /idid 查看本回合行为, /see 看到的信息, /hear 听到的信息, /feel 触到/闻到的信息, /stop 停止长行动"}
        return record
    if lower == "/status":
        record["command"] = lower
        record["payload"] = build_status_payload(current)
        return record
    if lower == "/idid":
        record["command"] = lower
        p = current.get("player_percept") or {}
        record["payload"] = {"self_action_summary": p.get("self_action_summary", "")}
        return record
    if lower in ("/see", "/hear", "/feel"):
        record["command"] = lower
        p = current.get("player_percept") or {}
        cats = _SENSE_CATEGORIES[lower.lstrip("/")]
        record["payload"] = {
            "senses": [
                {
                    "sense": s.get("sense"),
                    "description": s.get("description"),
                    "source_object_id": s.get("source_object_id"),
                    "confidence": s.get("confidence"),
                }
                for s in (p.get("senses") or [])
                if s.get("sense") in cats
            ]
        }
        return record
    m = SAVE_RE.match(cmd)
    if m:
        save_name = m.group(1)
        record["command"] = f"/save {save_name}"
        payload = strip_transient_state(current)
        save_dir = out_dir / "saves"
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / f"{scenario}__{save_name}.json"
        save_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        record["payload"] = {
            "save_file": rel(save_path),
            "json_bytes": save_path.stat().st_size,
            "tick": payload.get("tick"),
            "game_time": payload.get("game_time"),
            "world_name": payload.get("world_name"),
            "top_level_keys": sorted(payload.keys()),
            "note": "与 v1 saves/<name>.json 相同格式（strip_transient_state）；本脚本只写 docs/v2/reference/transcripts/saves/，不碰仓库 saves/ 目录",
        }
        return record
    record["command"] = cmd
    record["payload"] = {"error": f"未识别的命令 {cmd!r}；v1 中会作为普通玩家输入进入图"}
    return record


def _is_v1_command(raw_input: str) -> bool:
    lower = raw_input.strip().lower()
    return lower in V1_COMMANDS or lower.startswith("/save ")


def make_tick_record(
    tick_num: int,
    raw_input: str,
    before: dict[str, Any],
    result: dict[str, Any],
    elapsed: float,
    index: int,
    entry: dict[str, Any],
) -> dict[str, Any]:
    before_log = list(before.get("event_log") or [])
    after_log = list(result.get("event_log") or [])
    if len(after_log) >= len(before_log) and after_log[: len(before_log)] == before_log:
        event_delta: list[str] = after_log[len(before_log):]
        compacted = False
    else:
        # 日志被 compact_event_log 压缩/重写：报告完整尾部并标记
        event_delta, compacted = after_log, True

    before_hist = list(before.get("narrative_history") or [])
    after_hist = list(result.get("narrative_history") or [])
    if len(after_hist) >= len(before_hist) and after_hist[: len(before_hist)] == before_hist:
        narrative_appended = after_hist[len(before_hist):]
    else:
        narrative_appended = after_hist[-1:]

    pa = result.get("player_action") or {}
    return {
        "index": index,
        "tick": tick_num,
        "kind": "action",
        "category": entry.get("category"),
        "input": raw_input,
        "player_action": {
            "raw_input": pa.get("raw_input"),
            "interpreted_intent": pa.get("interpreted_intent"),
            "subconscious_adjustment": pa.get("subconscious_adjustment"),
            "action_type": pa.get("action_type"),
            "action_description": pa.get("action_description"),
            "speech_content": pa.get("speech_content"),
            "target_character_id": pa.get("target_character_id"),
            "target_object_id": pa.get("target_object_id"),
            "target_position": pa.get("target_position"),
            "emotion": pa.get("emotion"),
            "feasibility": pa.get("feasibility"),
            "feasibility_reason": pa.get("feasibility_reason"),
            "success_probability": pa.get("success_probability"),
            "confidence": pa.get("confidence"),
            "duration_minutes": pa.get("duration_minutes"),
            "continue_until": pa.get("continue_until"),
        },
        "percept_summary": summarize_percept(result.get("player_percept")),
        "event_log_delta": event_delta,
        "event_log_compacted": compacted,
        "state_diff": compute_state_diff(before, result),
        "narrative_appended": narrative_appended,
        "game_phase": result.get("game_phase"),
        "elapsed_s": round(elapsed, 1),
    }


# ──────────────────────────────────────────────────────────────────────────
# 记录主流程（需要真实 API key）
# ──────────────────────────────────────────────────────────────────────────

async def record_scenario(
    args: argparse.Namespace,
    llm: Any,
    prompt_loader: PromptLoader,
    inputs_path: Path,
    out_dir: Path,
) -> dict[str, Any]:
    scenario = inputs_path.stem
    spec = json.loads(inputs_path.read_text(encoding="utf-8"))
    init_path = resolve_repo_path(spec.get("init_file", f"public_start/{scenario}.yaml"))
    if not init_path.exists():
        raise RuntimeError(f"init 文件不存在: {rel(init_path)}")

    # ── 与 src/main.py 相同的加载路径 ──
    raw = load_init_file(init_path)
    game_state = init_file_to_game_state(raw)
    # 每个场景独立构图（等价于对 main.py 起三次独立进程），thread_id 与 main.py 一致
    graph = build_game_graph(llm, prompt_loader, status=None)

    entries = spec.get("entries", [])
    records: list[dict[str, Any]] = []
    current = game_state
    start_tick = int(game_state.get("tick", 0))
    action_count = 0
    interrupted_reason: str | None = None

    for idx, entry in enumerate(entries, start=1):
        raw_input = str(entry.get("input", ""))
        if entry.get("kind") == "command" or _is_v1_command(raw_input):
            records.append(handle_command(raw_input, scenario, current, out_dir, idx))
            continue

        tick_num = start_tick + action_count
        thread_cfg = {"configurable": {"thread_id": f"tick_{tick_num}"}}
        state_in = reset_tick_transients(current, raw_input)
        t0 = time.monotonic()
        try:
            result = await asyncio.wait_for(
                graph.ainvoke(state_in, thread_cfg), timeout=args.timeout_per_tick
            )
        except asyncio.TimeoutError:
            interrupted_reason = f"tick {tick_num} 超时（>{args.timeout_per_tick:.0f}s）"
            records.append({
                "index": idx, "tick": tick_num, "kind": "action", "input": raw_input,
                "error": interrupted_reason,
            })
            break
        except Exception as e:  # 图节点已有降级；这里是最后防线
            interrupted_reason = f"tick {tick_num} 图执行异常: {e!r}"
            records.append({
                "index": idx, "tick": tick_num, "kind": "action", "input": raw_input,
                "error": interrupted_reason,
            })
            break

        elapsed = time.monotonic() - t0
        records.append(make_tick_record(tick_num, raw_input, current, result, elapsed, idx, entry))
        current = result
        action_count += 1
        if result.get("game_phase") == "ended":
            interrupted_reason = "game_phase=ended，提前结束"
            break

    transcript: dict[str, Any] = {
        "transcript_version": 1,
        "scenario": scenario,
        "init_file": rel(init_path),
        "inputs_file": rel(inputs_path),
        "world_name": game_state.get("world_name"),
        "player_name": (game_state.get("player") or {}).get("name"),
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runtime": {
            "python": sys.version.split()[0],
            "repo_root": str(REPO_ROOT),
            "branch_note": "architecture-v2（任务纪律禁止 git 命令，故不记录 commit hash）",
            "v1_loading_path": (
                "src/agents/init.py::load_init_file -> init_file_to_game_state; "
                "src/graph/game_graph.py::build_game_graph; graph.ainvoke(thread_id=tick_N)"
                "——与 src/main.py 相同"
            ),
        },
        "llm": {
            "model": _MODEL_HOLDER["model"],
            "base_url": _MODEL_HOLDER["base_url"],
            "temperature": _MODEL_HOLDER["temperature"],
            "max_tokens": _MODEL_HOLDER["max_tokens"],
            "api_key": "REDACTED（按任务纪律不写入任何交付文件）",
        },
        "tick_count": action_count,
        "command_count": sum(1 for r in records if r["kind"] == "command"),
        "status": "interrupted:" + interrupted_reason if interrupted_reason else "completed",
        "entries": records,
    }

    out_path = out_dir / f"{scenario}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(transcript, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"[{scenario}] transcript 已写入: {rel(out_path)} "
        f"(action ticks={action_count}, commands={transcript['command_count']}, "
        f"status={transcript['status']})"
    )
    return transcript


# 记录 llm 参数（避免把 key 放进 transcript）
_MODEL_HOLDER: dict[str, Any] = {}


async def run_record(args: argparse.Namespace) -> int:
    sim_config = ConfigLoader(str(REPO_ROOT / "config")).load_simulation()
    key_env = sim_config.llm.api_key_env
    _MODEL_HOLDER.update({
        "model": sim_config.llm.model,
        "base_url": sim_config.llm.base_url,
        "temperature": sim_config.llm.temperature,
        "max_tokens": sim_config.llm.max_tokens,
    })

    key_status = classify_api_key(os.environ.get(key_env))
    if key_status != "ok":
        shown = "未设置" if key_status == "missing" else "仍为占位符（sk-your-...）"
        print(f"[record_transcript] 错误: {key_env} {shown}，不能运行真实对局。")
        print("请在仓库根 .env 中填入真实的 DeepSeek API key 后重新执行：")
        print("    .venv/bin/python docs/v2/reference/record_transcript.py --all")
        print(f"退出码 {EXIT_NO_API_KEY}：无 API key / 占位符——reference transcript 处于待执行状态")
        print("（见 docs/v2/reference/transcripts/PENDING.md 与 docs/v2/reference/README.md）。")
        return EXIT_NO_API_KEY

    llm = build_llm(sim_config)
    prompt_loader = PromptLoader(str(REPO_ROOT / "prompts"))
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir

    if args.all:
        targets = [INPUTS_DIR / f"{s}.json" for s in SCENARIOS]
    elif args.scenario:
        targets = [INPUTS_DIR / f"{args.scenario}.json"]
    else:
        targets = [resolve_repo_path(args.inputs)]

    rc = EXIT_OK
    for inputs_path in targets:
        if not inputs_path.exists():
            print(f"[record_transcript] 输入序列文件不存在: {inputs_path}")
            rc = EXIT_ERROR
            continue
        try:
            await record_scenario(args, llm, prompt_loader, inputs_path, out_dir)
        except Exception as e:
            print(f"[record_transcript] 场景 {inputs_path.stem} 记录失败: {e!r}")
            rc = EXIT_ERROR
    return rc


# ──────────────────────────────────────────────────────────────────────────
# selfcheck（不需要 API key、不调用 LLM）
# ──────────────────────────────────────────────────────────────────────────

def run_selfcheck(args: argparse.Namespace) -> int:
    print("=== record_transcript.py 自检（不依赖 API key，不调用 LLM）===")
    ok = True
    print("[1] 仓库模块导入: src.agents.init / src.config.loader / src.graph.game_graph / "
          "src.graph.game_state / src.prompts.loader —— OK（导入发生在模块顶层）")

    try:
        sim_config = ConfigLoader(str(REPO_ROOT / "config")).load_simulation()
        print(f"[2] config/simulation.yaml 加载: model={sim_config.llm.model} "
              f"base_url={sim_config.llm.base_url} api_key_env={sim_config.llm.api_key_env} "
              f"temperature={sim_config.llm.temperature} max_tokens={sim_config.llm.max_tokens}")
    except Exception as e:
        print(f"[2] config/simulation.yaml 加载失败: {e!r}")
        return EXIT_ERROR

    for scenario in SCENARIOS:
        inputs_path = INPUTS_DIR / f"{scenario}.json"
        if not inputs_path.exists():
            print(f"[3] {scenario}: 输入序列文件缺失 {rel(inputs_path)}")
            ok = False
            continue
        try:
            spec = json.loads(inputs_path.read_text(encoding="utf-8"))
            entries = spec.get("entries", [])
            init_path = resolve_repo_path(spec.get("init_file", f"public_start/{scenario}.yaml"))
            if not init_path.exists():
                print(f"[3] {scenario}: init 文件缺失 {rel(init_path)}")
                ok = False
                continue
            # 与 src/main.py 相同的加载路径（纯确定性，无 LLM 调用）
            raw = load_init_file(init_path)
            gs = init_file_to_game_state(raw)
            n_actions = sum(1 for e in entries if e.get("kind", "action") != "command")
            issues: list[str] = []
            if not 5 <= len(entries) <= 10:
                issues.append(f"条目数 {len(entries)} 不在 [5,10]")
            for e in entries:
                if e.get("kind") == "command":
                    low = str(e.get("input", "")).strip().lower()
                    if low in V1_COMMANDS:
                        continue
                    if low.startswith("/save"):
                        if not SAVE_RE.match(str(e.get("input", "")).strip()):
                            issues.append(f"非法 /save 名: {e.get('input')!r}")
                        continue
                    issues.append(f"未知命令: {e.get('input')!r}")
            player_pos = (gs.get("player") or {}).get("position")
            line = (
                f"[3] {scenario}: init={rel(init_path)} world={gs.get('world_name')!r} "
                f"locations={len(gs.get('locations') or {})} objects={len(gs.get('objects') or {})} "
                f"characters={len(gs.get('characters') or {})} max_ticks={gs.get('max_ticks')} "
                f"entries={len(entries)} (action={n_actions}, command={len(entries) - n_actions}) "
                f"player_pos={player_pos}"
            )
            if issues:
                line += " 问题: " + "; ".join(issues)
                ok = False
            print(line)
        except Exception as e:
            print(f"[3] {scenario}: 校验失败: {e!r}")
            ok = False

    key_status = classify_api_key(os.environ.get(sim_config.llm.api_key_env))
    if key_status == "ok":
        print(f"[4] {sim_config.llm.api_key_env}: 已设置且非占位符 → 可运行真实对局（--all / --scenario <name>）")
    else:
        shown = "未设置" if key_status == "missing" else "仍为占位符（sk-your-...）"
        print(f"[4] {sim_config.llm.api_key_env}: {shown} → 不能运行真实对局；"
              f"填入真实 key 后重跑 --all（届时退出码 {EXIT_NO_API_KEY} 路径不会触发）")

    print("SELF-CHECK " + ("PASSED" if ok else "FAILED"))
    return EXIT_OK if ok else EXIT_ERROR


# ──────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="record_transcript.py",
        description="在 v1 LangGraph 管道上回放脚本化玩家输入序列，记录 JSON transcript（详见 docs/v2/reference/README.md）。",
        epilog=(
            "退出码: 0 成功/自检通过; 1 运行时错误; 2 参数错误; "
            "3 DEEPSEEK_API_KEY 缺失或为占位符。"
        ),
    )
    parser.add_argument(
        "--selfcheck", action="store_true",
        help="自检：导入仓库模块、加载 config、校验 3 个输入序列与 init 文件、报告 API key 状态（不调用 LLM、不需要 key）",
    )
    parser.add_argument(
        "--scenario", choices=list(SCENARIOS),
        help="记录单个场景（读取 docs/v2/reference/inputs/<name>.json）",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="依次记录全部 3 个场景",
    )
    parser.add_argument(
        "--inputs",
        help="指定输入序列 JSON 路径（与 --all/--scenario 互斥）",
    )
    parser.add_argument(
        "--out-dir", default=str(DEFAULT_OUT_DIR),
        help="transcript 输出目录（默认 docs/v2/reference/transcripts）",
    )
    parser.add_argument(
        "--timeout-per-tick", type=float, default=600.0,
        help="单个 tick 的超时秒数（默认 600）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.selfcheck:
            return run_selfcheck(args)
        if args.inputs and (args.all or args.scenario):
            print("错误: --inputs 不能与 --all / --scenario 同时使用")
            return EXIT_BAD_ARGS
        if not (args.all or args.scenario or args.inputs):
            print("错误: 请指定 --selfcheck / --scenario <name> / --all / --inputs <path> 之一（见 --help）")
            return EXIT_BAD_ARGS
        return asyncio.run(run_record(args))
    except KeyboardInterrupt:
        print("\n[record_transcript] 用户中断")
        return 130


if __name__ == "__main__":
    sys.exit(main())
