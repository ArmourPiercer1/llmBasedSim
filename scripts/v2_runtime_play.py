#!/usr/bin/env python
"""v2 runtime closure 实玩验收（H-closure）：真 LLM 交互式驱动 reference game。

对象 = `examples/complex_minimal`（锅炉房值守）经 **production-only 装配**
（`src.engine_v2.runtime.assemble_project`，零 tests 面）：玩家回合制操作
锅炉（add heat / cool / toggle），每回合末夜班看火人（LLM NPC）经 P6
LLMPolicy 自主决策并走同一提交管道——你同时看到 NPC 的"台词"（LLM 原始
输出文本，trace sink `output://` artifact 直读）与世界的数值后果。

用法
----
确定性冒烟（零 API Key，脚本化后端按调用次序产 NPC 动作）::

    PYTHONPATH=. .venv/bin/python scripts/v2_runtime_play.py --fake

真 LLM（任意 OpenAI 兼容 /chat/completions 端点；凭据只经 env 变量名传，
脚本永不读/打凭据值）::

    export DEEPSEEK_API_KEY=sk-...
    PYTHONPATH=. .venv/bin/python scripts/v2_runtime_play.py \
        --model deepseek-chat --base-url https://api.deepseek.com \
        --api-key-env DEEPSEEK_API_KEY

回合命令：heat（添热）/ cool（降温）/ toggle（开关机器）/ wait（观望）/
scene（详查）/ llm（看 NPC 最近一次原始输出）/ quit（收尾结算）。

验收清单（gate report §7 H-closure 面）
----------------------------------------
1. 玩家动作全部走显式管道（committed / 显式 failure 诊断，无静默写）；
2. NPC 每回合经 LLM 产提案并可见"台词"+ 数值后果（温度积分响应功率）；
3. 模型输出坏格式时引擎不崩（诊断通道显式，世界不变）；
4. 双跑确定性仍成立（--fake 时：同输入序列 → 同世界）。
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Final

from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.reducer import guard
from src.engine_v2.llm.adapter import HttpxInferenceBackend, InferenceResponse
from src.engine_v2.llm.deployment import DeploymentEntry, DeploymentProfile
from src.engine_v2.llm.player_intent import build_player_intent_context
from src.engine_v2.llm.profiles import ModelCapabilityProfile
from src.engine_v2.runtime import assemble_project
from src.engine_v2.runtime.llm_binding import bind_player_intent

# —— 实体 id（= ent_authoring_<authoring slug>，materialize 命名契约）——
PLAYER: Final[str] = "ent_authoring_operator"
WATCHMAN: Final[str] = "ent_authoring_watchman"
BOILER: Final[str] = "ent_authoring_boiler"
ROOM: Final[str] = "ent_authoring_boiler_room"

# —— 玩家命令 → 动作 id（= actions/boiler_machine.yaml 声明面）——
PLAYER_ACTIONS: Final[dict[str, str]] = {
    "heat": "inject_heat",
    "cool": "cool",
    "toggle": "toggle_machine",
}

HELP_TEXT = (
    "命令：heat=添热  cool=降温  toggle=开关机器  wait=观望  "
    "scene=详查  llm=看最近推理输出  quit=结算退出\n"
    "其他输入 = 玩家自然语言（真实面经意图解释器 → 结构化动作；"
    "--fake 面走脚本化关键词映射）"
)


class _ScriptedSmokeBackend:
    """冒烟脚本化后端：按调用次序产响应（对 base_revision 不敏感）。

    FakeInferenceBackend 的脚本键 = (capability, base_revision, 全局调用
    序号)——base 随玩家输入漂移，无法预键；本面按纯调用次序脚本化
    （确定性不变：同输入序列 → 同调用序列 → 同输出）。前 4 次
    inject_heat（功率爬到上限 4 后，executor 显式 failure 诊断 = 验收
    清单第 1 项演示面）、5–6 次 cool（回落）、其余 null no-op。
    """

    def __init__(self) -> None:
        self._seq = 0
        self.calls: tuple = ()

    def generate(self, request) -> InferenceResponse:
        self._seq += 1
        seq = self._seq
        if seq <= 4:
            text = '{"action_id": "inject_heat"}'
        elif seq <= 6:
            text = '{"action_id": "cool"}'
        else:
            text = '{"action_id": null}'
        self.calls = self.calls + (request,)
        return InferenceResponse(
            text=text,
            model=request.model,
            latency_ms=5.0,
            input_tokens=None,
            output_tokens=None,
        )


def _build_deployment(
    *,
    model: str,
    base_url: str,
    api_key_env: str | None,
    temperature: float,
) -> DeploymentProfile:
    """真 LLM 部署面：单 model（tier 2，满足 game.yaml npc_policy /
    player_intent min_tier=1 / ideal_tier=2）+ 双 capability 条目
    （审计 R3：player_intent 与 npc_policy 走同一 deployment 系统，
    可配不同模型——本轮同 model 简化面）。"""
    profile = ModelCapabilityProfile(
        model_id=model,
        tier=2,
        context_length=65536,
        max_output=8192,
        structured_output=True,
        reasoning_class="standard",
    )
    return DeploymentProfile(
        models={model: profile},
        inference_profiles={
            "npc_policy": DeploymentEntry(
                provider="openai-compatible",
                model=model,
                base_url=base_url,
                api_key_env=api_key_env,
                temperature=temperature,
            ),
            "player_intent": DeploymentEntry(
                provider="openai-compatible",
                model=model,
                base_url=base_url,
                api_key_env=api_key_env,
                temperature=temperature,
            ),
        },
    )


def _component(inst, entity_id: str, name: str) -> dict | None:
    """权威世界读组件（游戏内读数唯一合法面 = committed world）。"""
    entity = inst.world.entities.get(EntityId(entity_id))
    if entity is None:
        return None
    component = entity.components.get(name)
    return component if isinstance(component, dict) else None


def _room_temp(inst) -> float | None:
    component = _component(inst, ROOM, "temperature")
    if component is None:  # 首 tick dynamics 落位前缺位
        return None
    value = component.get("celsius")
    return value if isinstance(value, (int, float)) else None


def _boiler_power(inst) -> int | None:
    component = _component(inst, BOILER, "machine")
    if component is None:
        return None
    value = component.get("power")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _temp_label(temp: float | None) -> str:
    if temp is None:
        return "未测（首 tick 由 dynamics 落位）"
    if temp < 10:
        return "严寒 ⚠"
    if temp < 20:
        return "偏冷"
    if temp <= 45:
        return "正常"
    if temp <= 60:
        return "偏热"
    return "过热 ⚠（安全区间 20–60℃）"


def _game_clock(tick: int) -> str:
    """游戏时钟：scenario 起点 02:00，1 tick = 0.5 分钟（ticks_per_game_minute=0.5）。"""
    minutes = 2 * 60 + int(round(tick * 0.5))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _print_scene(inst, tick: int, *, detailed: bool = False) -> None:
    temp = _room_temp(inst)
    power = _boiler_power(inst)
    temp_text = "—" if temp is None else f"{temp:.1f}℃（{_temp_label(temp)}）"
    power_text = "—" if power is None else f"{power} 档（{'停机' if power == 0 else '运转'}）"
    print(f"  [刻 {tick} | 时钟 {_game_clock(tick)}]  锅炉房 {temp_text}   锅炉 {power_text}")
    if detailed:
        for entity_id in (PLAYER, WATCHMAN, BOILER, ROOM):
            entity = inst.world.entities.get(EntityId(entity_id))
            if entity is None:
                continue
            parts = [
                f"{key}={value}" for key, value in sorted(entity.components.items())
            ]
            print(f"    - {entity_id}: " + (", ".join(parts) or "（无组件）"))


def _print_player_result(engine_result) -> None:
    if engine_result is None:
        return
    ok, diagnostics = engine_result.ok, engine_result.diagnostics
    if ok and not diagnostics:
        print("  ▶ 玩家动作已提交（COMMITTED）。")
    else:
        print(f"  ▶ 玩家动作未提交：ok={ok}")
        for diagnostic in diagnostics:
            print(f"    ! {diagnostic}")


def _npc_turn(engine, inst, tick: int) -> None:
    """NPC 回合：唤醒看火人 → advance(1) → 打印 LLM 原始输出 + 后果。"""
    engine.wake(EntityId(WATCHMAN), reason=f"第 {tick} 刻玩家回合结束，例行巡检")
    step = engine.advance(1)
    sink = inst.trace_sink
    output_artifact: dict | None = None
    has_llm_call = False
    for event in reversed(sink.records):
        if event.kind == "llm_call":
            has_llm_call = True
            # llm_call payload 直接携带 output_ref 句柄（P6 面，零重建）；
            # no-op 分支不落 artifact → get 为 None（见下方显示分支）
            ref = event.payload.get("output_ref")
            artifact = sink.artifacts.get(ref) if isinstance(ref, str) else None
            if isinstance(artifact, dict):
                output_artifact = artifact
            break
    if output_artifact is not None:
        print(f"  ● 看火人（LLM）说：\n    {str(output_artifact.get('text', ''))[:600]}")
    elif has_llm_call:
        # P6 冻结面口径：no-op 分支（action_id=null）只记 llm_call、不落
        # output artifact（artifact 属提案分支）——NPC 考虑后决定不动作。
        print("  ● 看火人（LLM）考虑后本轮决定不动作（action_id=null，合法 no-op）。")
    else:
        print("  ● 看火人本轮未产生推理调用（policy 缺席或提前终止）。")
    if step.diagnostics:
        print("  ● 引擎诊断（NPC 侧，世界可能未变）：")
        for diagnostic in step.diagnostics:
            print(f"    ! {diagnostic}")
    else:
        committed = sum(
            1 for txn in step.transactions if str(txn.status).endswith("COMMITTED")
        )
        if committed:
            print(
                f"  ● 本 tick 世界更新（{committed} 笔事务提交，"
                f"revision {step.world_revision}；NPC 动作笔以 effect.source="
                "complex_minimal.actions 可辨）。"
            )


def _llm_review(inst) -> None:
    sink = inst.trace_sink
    for event in reversed(sink.records):
        if event.kind == "llm_call":
            ref = event.payload.get("output_ref")
            artifact = sink.artifacts.get(ref) if isinstance(ref, str) else None
            if isinstance(artifact, dict):
                print(f"  —— 最近一次 LLM 输出（ref={ref}）：\n{str(artifact.get('text', ''))[:800]}")
            else:
                print(f"  —— 最近一次 LLM 调用（ref={ref}）为 no-op（action_id=null；"
                      "P6 冻结面：no-op 分支不落 output artifact）。")
            return
    print("  （尚无任何 LLM 调用记录）")


def _final_summary(inst, total_llm_calls: int) -> None:
    print("\n══ 结算 ══")
    _print_scene(inst, int(inst.world.world_revision), detailed=True)
    print(f"  世界 revision = {int(inst.world.world_revision)}；LLM 调用 = {total_llm_calls} 次")
    print("  确定性注记：同 GameProject + 同部署 + 同输入序列 → 同世界（K7）。")


# —— 玩家自然语言面（0.1.0-alpha.1 发布前修复 R4）——

#: fake 面脚本化意图关键词 → 动作 id（宿主级 demo 便利面：--fake 时玩家
#: NL 零 LLM 调用、零 backend 序号消费——与 _ScriptedSmokeBackend 的 NPC
#: 脚本序正交；确定性 = 源码序遍历）。真 backend 面走
#: PlayerIntentInterpreter（不消费本表）。
_FAKE_PLAYER_INTENT_KEYWORDS: Final[dict[str, str]] = {
    "添热": "inject_heat",
    "加煤": "inject_heat",
    "炉火": "inject_heat",
    "加热": "inject_heat",
    "降温": "cool",
    "冷却": "cool",
    "太热": "cool",
    "开关": "toggle_machine",
    "切换": "toggle_machine",
    "启停": "toggle_machine",
}


def _fake_player_intent(line: str) -> dict:
    """--fake 脚本化玩家意图（关键词 → 动作 id；未命中 = 合法 no-op）。"""
    lowered = line.casefold()
    for keyword, action_id in _FAKE_PLAYER_INTENT_KEYWORDS.items():
        if keyword in lowered:
            return {
                "action_id": action_id,
                "arguments": {},
                "intent": f"脚本化意图（fake 面关键词 {keyword!r}）",
            }
    return {"action_id": None, "arguments": {}, "intent": None}


def _submit_player_intent(
    engine,
    inst,
    action_id: str | None,
    arguments: dict,
    intent: str | None,
) -> None:
    """[result] 面：no-op / 显式拒绝（幻觉 action，未提交）/ 提交同管道。"""
    if action_id is None:
        print("  [result] 无对应动作（no-op，世界零变更）")
        return
    if action_id not in inst.action_registry.specs:
        print(
            f"  [result] 显式拒绝：未知动作 {action_id!r}"
            "（未提交，世界零变更；引擎 unknown_action 为最终门）"
        )
        return
    step = engine.submit_action(
        EntityId(PLAYER), action_id, dict(arguments), intent=intent
    )
    _print_player_result(step)


def _player_natural_language(
    engine,
    inst,
    line: str,
    pi_binding,
    player_name: str,
) -> None:
    """真实 LLM 玩家意图面（R4 debug 面：[input]/[interpreted]/[result]）。

    世界每刻重取（不可变状态机：WorldState 对象每 commit 替换）；只读面
    经 guard() 门面投影（与 executor 面同款 K2 纪律）。
    """
    world = engine.instance.world
    ctx = build_player_intent_context(
        guard(world), PLAYER, player_name=player_name
    )
    result = pi_binding.interpreter.interpret(
        text=line, context=ctx, base_revision=int(world.world_revision)
    )
    print(f"  [input] {line}")
    print(
        f"  [interpreted] action_id={result.action_id} "
        f"arguments={result.arguments} intent={result.intent!r} "
        f"confidence={result.confidence}"
    )
    for diagnostic in result.diagnostics:
        print(f"  [interpreted] ! {diagnostic.code}: {diagnostic.message}")
    _submit_player_intent(
        engine, inst, result.action_id, result.arguments, result.intent
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v2 runtime closure 实玩验收（H-closure）")
    parser.add_argument("--root", default="examples/complex_minimal", help="GameProject 根目录")
    parser.add_argument("--fake", action="store_true", help="确定性冒烟：FakeInferenceBackend（零 API Key）")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "deepseek-chat"))
    parser.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "https://api.deepseek.com"))
    parser.add_argument("--api-key-env", default=os.environ.get("LLM_API_KEY_ENV", "DEEPSEEK_API_KEY"))
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-turns", type=int, default=24, help="玩家回合上限（默认 = scenario max_ticks）")
    args = parser.parse_args(argv)

    if args.fake:
        # 冒烟模式也需 deployment（capability→model 绑定面）；wire 不触网
        # （_ScriptedSmokeBackend），base_url 空串 = resolve 期合法、调用期
        # 永不读取。
        backend = _ScriptedSmokeBackend()
        deployment = _build_deployment(
            model="fake-model", base_url="", api_key_env=None,
            temperature=args.temperature,
        )
    else:
        if not os.environ.get(args.api_key_env):
            print(
                f"错误：凭据 env 变量 {args.api_key_env} 未设置（脚本只经变量名传递，"
                "不读取值）。先 export 再运行，或用 --fake 做零 Key 冒烟。",
                file=sys.stderr,
            )
            return 2
        backend = HttpxInferenceBackend()
        deployment = _build_deployment(
            model=args.model, base_url=args.base_url,
            api_key_env=args.api_key_env, temperature=args.temperature,
        )

    print(f"装配 {args.root}（trust_python=True"
          f"{'，脚本化后端冒烟' if args.fake else f'，真 LLM {args.model}@{args.base_url}'}）…")
    result = assemble_project(
        args.root,
        trust_python=True,
        deployment=deployment,
        inference_backend=backend,
    )
    if result.engine is None:
        print("装配失败（致命诊断）：", file=sys.stderr)
        for diagnostic in result.diagnostics:
            print(f"  ! {diagnostic.code}: {diagnostic.message}", file=sys.stderr)
        return 1
    engine = result.engine
    inst = result.instance
    # 玩家意图面（R4）：真实 backend 才绑 PlayerIntentInterpreter；--fake
    # 走脚本化关键词映射（零 LLM 调用、不消费 _ScriptedSmokeBackend 序号）。
    pi_binding = None
    if not args.fake:
        pi_binding = bind_player_intent(
            inst.ir,
            deployment=deployment,
            backend=backend,
            sink=inst.trace_sink,
        )
        if pi_binding.interpreter is None:
            print(
                "注意：玩家意图面不可用（绑定诊断）："
                + "; ".join(f"{d.code}: {d.message}" for d in pi_binding.diagnostics)
            )
        else:
            print(
                f"玩家意图面：已绑定（capability=player_intent，"
                f"model={pi_binding.resolved_model}）——直接输入自然语言。"
            )
    else:
        print("玩家意图面：--fake 脚本化关键词映射（零 LLM 调用）。")
    print("装配成功。" + HELP_TEXT + "\n")

    llm_calls = 0
    try:
        for turn in range(1, args.max_turns + 1):
            _print_scene(inst, turn - 1)
            line = input(f"值班员 [刻 {turn}] > ").strip().lower()
            if not line:
                line = "wait"
            if line in ("quit", "q", "exit"):
                break
            if line == "scene":
                _print_scene(inst, turn - 1, detailed=True)
                continue
            if line == "llm":
                _llm_review(inst)
                continue
            if line == "wait":
                _print_player_result(None)
            elif line in PLAYER_ACTIONS:
                step = engine.submit_action(
                    EntityId(PLAYER), PLAYER_ACTIONS[line], {}
                )
                _print_player_result(step)
            else:
                # 自然语言输入（R4）：fake = 脚本化映射；真实面 = 意图解释器。
                if args.fake:
                    fake_res = _fake_player_intent(line)
                    print(f"  [input] {line}")
                    print(
                        f"  [interpreted]（fake 脚本面）action_id="
                        f"{fake_res['action_id']} intent={fake_res['intent']!r}"
                    )
                    _submit_player_intent(
                        engine,
                        inst,
                        fake_res["action_id"],
                        fake_res["arguments"],
                        fake_res["intent"],
                    )
                elif pi_binding is not None and pi_binding.interpreter is not None:
                    _player_natural_language(
                        engine, inst, line, pi_binding, inst.ir.player.name
                    )
                else:
                    print(f"  未知命令：{line!r}。" + HELP_TEXT)
                    continue
            before_calls = len(
                [e for e in inst.trace_sink.records if e.kind == "llm_call"]
            )
            _npc_turn(engine, inst, turn)
            after_calls = len(
                [e for e in inst.trace_sink.records if e.kind == "llm_call"]
            )
            llm_calls += after_calls - before_calls
    except (KeyboardInterrupt, EOFError):
        print()
    _final_summary(inst, llm_calls)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
