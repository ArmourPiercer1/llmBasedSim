"""P0-T03: game_graph.py 单节点 characterization 测试（隔离执行）。

从编译后的图中提取节点原始函数（见 char_helpers.get_node），锁定：
- 每个节点的输入/输出字段契约（对照 P0-T01 报告 §3 节点表）；
- 确定性节点（tick_speed_resolve / state_apply / natural_attribute_delta /
  post_narrative_update）在无 LLM 下的精确行为；
- physics_resolve F821（game_graph.py:475 未定义名称 `fallback`）路径的当前行为；
- 各 LLM 节点在 FakeLLM 抛异常 / 返回垃圾 JSON 时的降级行为。

Characterization 纪律：只记录 v1 当前行为。看起来像 bug 的行为按现状断言，
并在注释中标记 ``known-bug-candidate``（由人工 H1 决定是否作为兼容契约）。
禁止修改 src/ 来"修复"任何行为。

运行方式（无网络、无 API key、无真实 LLM）：
    .venv/bin/python -m pytest tests/test_char_nodes.py -q
"""

from __future__ import annotations

import random as random_module

import pytest

from tests.char_helpers import (
    GARBAGE,
    M_ATTR,
    M_INTENT,
    M_NARRATIVE,
    M_PHYSICS,
    M_RESOLVE,
    M_SENSORY,
    FakeLLM,
    attr_update_json,
    build_test_graph,
    char_marker_for,
    get_node,
    intent_json,
    make_base_state,
    make_char,
    narrative_json,
    percept_json,
    player_action_json,
)

# 所有节点名（T01 报告 §3）
ALL_NODES = [
    "player_intent_process",
    "player_action_resolve",
    "characters_all_decide",
    "tick_speed_resolve",
    "physics_resolve",
    "state_apply",
    "natural_attribute_delta",
    "attribute_update",
    "sensory_filter",
    "narrative_stylize",
    "post_narrative_update",
]


def _graph_and_node(name: str, routes=None):
    llm = FakeLLM(routes or {})
    graph = build_test_graph(llm)
    return llm, get_node(graph, name)


# ══════════════════════════════════════════════════════════════════════════
# 0. 图结构与节点提取契约
# ══════════════════════════════════════════════════════════════════════════

def test_graph_contains_exactly_11_nodes():
    """图拓扑锁定：START 之后恰好 11 个具名节点（对照 T01 报告 §2.2/§3）。"""
    llm = FakeLLM({})
    graph = build_test_graph(llm)
    names = [n for n in graph.nodes if n != "__start__"]
    assert sorted(names) == sorted(ALL_NODES)


# ══════════════════════════════════════════════════════════════════════════
# 1. player_intent_process
# ══════════════════════════════════════════════════════════════════════════

async def test_intent_no_input_returns_none_fields_without_event_log():
    """无输入：返回 player_action/action_continuation=None。

    Characterization：此分支的返回 dict 不含 event_log 键（不写日志）。
    """
    _, node = _graph_and_node("player_intent_process")
    out = await node({"player": {}})
    assert out == {"player_action": None, "action_continuation": None}


async def test_intent_c_continues_long_task():
    """continuation 存在且输入为 /c：原样延续（输入经 strip().lower() 归一）。"""
    _, node = _graph_and_node("player_intent_process")
    continuation = {
        "raw_input": "旧长任务",
        "action_type": "interact",
        "action_description": "持续搜查",
        "duration_minutes": 9.0,
        "continue_until": "done",
    }
    state = {"player_input": "  /C ", "action_continuation": continuation, "player": {}}
    out = await node(state)
    assert out["player_action"] == continuation
    assert out["action_continuation"] == continuation
    assert out["event_log"] == ["[系统] 继续长任务。"]


async def test_intent_stop_clears_continuation():
    _, node = _graph_and_node("player_intent_process")
    continuation = {"action_type": "move", "action_description": "赶路", "duration_minutes": 5.0}
    out = await node({"player_input": "/stop", "action_continuation": continuation, "player": {}})
    assert out["player_action"] is None
    assert out["action_continuation"] is None
    assert out["event_log"] == ["[系统] 行动已终止。"]


async def test_intent_success_sets_raw_input_and_interrupts_continuation():
    """正常输入：LLM 解析成功；raw_input 被覆写为原始输入；continuation 被打断清空。"""
    routes = {M_INTENT: [player_action_json(
        interpreted_intent="环顾四周", action_type="observe", action_description="环顾四周",
    )]}
    llm, node = _graph_and_node("player_intent_process", routes)
    state = make_base_state(player_input="看看周围", action_continuation={"action_description": "旧任务"})
    out = await node(state)
    assert out["player_action"]["raw_input"] == "看看周围"
    assert out["player_action"]["action_description"] == "环顾四周"
    assert out["action_continuation"] is None
    assert out["event_log"] == ["[系统] 长任务已被新输入打断。", "[玩家意图] 环顾四周"]
    assert llm.call_count(M_INTENT) == 1


async def test_intent_llm_exception_degrades():
    """LLM 抛异常（T01 报告 §3：player_action=None，记录错误事件，忽略本轮输入）。"""
    routes = {M_INTENT: [RuntimeError("boom")]}
    llm, node = _graph_and_node("player_intent_process", routes)
    out = await node(make_base_state(player_input="做点什么"))
    assert out == {
        "player_action": None,
        "action_continuation": None,
        "event_log": ["[错误] 玩家输入处理失败，本轮输入被忽略。"],
    }
    assert llm.call_count(M_INTENT) == 1


async def test_intent_garbage_json_exhausts_retries_then_degrades():
    """垃圾 JSON：generate_structured 重试 max_retries=2（共 3 次尝试）后抛 ValueError → 节点降级。"""
    routes = {M_INTENT: [GARBAGE]}  # sticky：永远返回垃圾
    llm, node = _graph_and_node("player_intent_process", routes)
    out = await node(make_base_state(player_input="做点什么"))
    assert out["player_action"] is None
    assert out["event_log"] == ["[错误] 玩家输入处理失败，本轮输入被忽略。"]
    assert llm.call_count(M_INTENT) == 3  # 1 次初始 + 2 次重试


async def test_intent_garbage_then_valid_recovers_via_retry():
    """前两次垃圾、第三次合法 JSON：重试路径恢复成功（解析重试契约）。"""
    valid = player_action_json(interpreted_intent="休息", action_type="wait", action_description="原地休息")
    routes = {M_INTENT: [GARBAGE, GARBAGE, valid]}
    llm, node = _graph_and_node("player_intent_process", routes)
    out = await node(make_base_state(player_input="休息一下"))
    assert out["player_action"]["action_description"] == "原地休息"
    assert llm.call_count(M_INTENT) == 3


# ══════════════════════════════════════════════════════════════════════════
# 2. player_action_resolve
# ══════════════════════════════════════════════════════════════════════════

async def test_resolve_no_action_returns_empty_dict():
    _, node = _graph_and_node("player_action_resolve")
    assert await node({"player_action": None, "player": {}}) == {}


async def test_resolve_preserves_intent_fields_and_keeps_llm_feasibility():
    """LLM 复核仅补充可行性字段：意图节点产出的行动字段被保留（preserved_action_fields）。"""
    routes = {M_RESOLVE: [player_action_json(
        interpreted_intent="LLM 改写后的意图",          # 应被原值覆盖
        action_type="move",                             # 应被原值覆盖
        action_description="LLM 改写后的描述",          # 应被原值覆盖
        feasibility="uncertain",
        feasibility_reason="看起来有风险",
        success_probability=0.4,
        requires_roll=True,
        duration_minutes=99.0,                          # 应被原值覆盖
    )]}
    _, node = _graph_and_node("player_action_resolve", routes)
    original = {
        "raw_input": "推箱子",
        "interpreted_intent": "推动木箱",
        "action_type": "interact",
        "action_description": "推动木箱",
        "duration_minutes": 7.0,
        "continue_until": "",
    }
    state = make_base_state(player_action=original)
    out = await node(state)
    pa = out["player_action"]
    assert pa["interpreted_intent"] == "推动木箱"
    assert pa["action_type"] == "interact"
    assert pa["action_description"] == "推动木箱"
    assert pa["duration_minutes"] == 7.0
    # 可行性字段不在保留清单内 → 采用 LLM 输出（无规则预判时）
    assert pa["feasibility"] == "uncertain"
    assert pa["feasibility_reason"] == "看起来有风险"
    assert pa["success_probability"] == 0.4
    assert pa["requires_roll"] is True
    assert out["action_continuation"] is None
    assert out["event_log"] == ["[玩家行动] 推动木箱（uncertain: 看起来有风险）"]


async def test_resolve_rule_result_fills_when_llm_leaves_null():
    """确定性规则（力量对比）在 LLM 未给可行性时回填 feasibility/reason。"""
    routes = {M_RESOLVE: [player_action_json(
        interpreted_intent="搬箱子", action_type="interact", action_description="搬起大石头",
    )]}  # feasibility=None
    _, node = _graph_and_node("player_action_resolve", routes)
    state = make_base_state(
        player_action={
            "interpreted_intent": "搬箱子",
            "action_type": "interact",
            "action_description": "搬起大石头",
            "target_object_id": "boulder",
            "duration_minutes": 0.0,
            "continue_until": "",
        },
        objects={
            "boulder": {
                "object_id": "boulder", "name": "大石头", "description": "非常重",
                "position": {"x": 1, "y": 0, "z": 0},
                "properties": {"weight_kg": 500},
            },
        },
    )
    # player physical_profile.strength=1 → capacity 50kg < 500kg → blocked
    state["player"]["physical_profile"] = {"strength": 1.0}
    out = await node(state)
    pa = out["player_action"]
    assert pa["feasibility"] == "blocked"
    assert "系统规则预判" in pa["feasibility_reason"]
    assert out["event_log"][0].startswith("[玩家行动] 搬起大石头（blocked: 系统规则预判")


async def test_resolve_long_move_fallback_is_broken_degrades():
    """known-bug-candidate：超长移动确定性回退实际不可达。

    源码意图（game_graph.py:257-275）：无时长的大距离 move（>30 单位）估算
    duration=dist*0.5 并置 continue_until='blocked'。但 ``resolved.target_position``
    是 Pydantic ``Position`` 模型，没有 ``.get`` 方法 → 抛 AttributeError →
    被节点外层 try/except 捕获 → **该类行动一律走降级路径**（保留原始行动、
    追加错误事件），"超长移动" 文案从不出现。记录现状，不修复。
    """
    routes = {M_RESOLVE: [player_action_json(
        interpreted_intent="去远处", action_type="move", action_description="走向远方",
        feasibility="allowed", feasibility_reason="可以",
    )]}
    _, node = _graph_and_node("player_action_resolve", routes)
    original = {
        "interpreted_intent": "去远处",
        "action_type": "move",
        "action_description": "走向远方",
        "target_position": {"x": 100, "y": 0, "z": 0},
        "duration_minutes": 0.0,
        "continue_until": "",
    }
    state = make_base_state(player_action=original)
    out = await node(state)
    assert out["player_action"] == original  # 保留原始行动（降级契约）
    assert out["action_continuation"] is None
    assert out["event_log"] == ["[错误] 玩家行动可行性判断失败，跳过可行性检查。"]


async def test_resolve_multi_step_forces_uncertain_to_allowed():
    """continue_until 非空且 uncertain：强制改为 allowed（多步行动自动延续），缺省时长 5.0。"""
    routes = {M_RESOLVE: [player_action_json(
        interpreted_intent="持续搜查", action_type="interact", action_description="搜查房间",
        feasibility="uncertain", feasibility_reason="不确定",
        success_probability=0.5, requires_roll=True,
    )]}
    _, node = _graph_and_node("player_action_resolve", routes)
    state = make_base_state(player_action={
        "interpreted_intent": "持续搜查",
        "action_type": "interact",
        "action_description": "搜查房间",
        "duration_minutes": 0.0,
        "continue_until": "done",
    })
    out = await node(state)
    pa = out["player_action"]
    assert pa["feasibility"] == "allowed"
    assert pa["requires_roll"] is False
    assert pa["success_probability"] is None
    assert pa["feasibility_reason"] == "多步行动：每步单独执行，直到目标达成或被阻止"
    assert pa["duration_minutes"] == 5.0
    assert out["event_log"][0].endswith("（多步行动，自动延续）")


async def test_resolve_llm_exception_keeps_original_action():
    """LLM 失败（T01 报告 §3：保留原始 player_action，跳过 LLM 综合判断）。"""
    routes = {M_RESOLVE: [RuntimeError("boom")]}
    _, node = _graph_and_node("player_action_resolve", routes)
    original = {"action_type": "observe", "action_description": "环顾四周"}
    out = await node(make_base_state(player_action=original))
    assert out["player_action"] == original
    assert out["action_continuation"] is None
    assert out["event_log"] == ["[错误] 玩家行动可行性判断失败，跳过可行性检查。"]


# ══════════════════════════════════════════════════════════════════════════
# 3. characters_all_decide
# ══════════════════════════════════════════════════════════════════════════

async def test_chars_no_characters_returns_empty_lists():
    _, node = _graph_and_node("characters_all_decide")
    assert await node({"characters": {}}) == {"action_intents": [], "event_log": []}


async def test_chars_intent_character_id_forced_and_event_emitted():
    """canned intent 的 character_id 会被强制覆写为实际 NPC id；事件以 NPC 名字开头。"""
    routes = {char_marker_for("艾拉"): [intent_json(
        "WRONG_ID", action_type="observe", action_description="打量四周",
    )]}
    llm, node = _graph_and_node("characters_all_decide", routes)
    state = make_base_state(characters={"npc1": make_char("npc1", "艾拉", {"x": 2, "y": 0, "z": 0})},
                            character_positions={"npc1": {"x": 2, "y": 0, "z": 0}})
    out = await node(state)
    assert len(out["action_intents"]) == 1
    assert out["action_intents"][0]["character_id"] == "npc1"
    assert out["event_log"] == ["[角色] 艾拉: 打量四周"]
    assert llm.call_count(char_marker_for("艾拉")) == 1


async def test_chars_one_fails_other_succeeds():
    """单 NPC 失败不影响其他 NPC（T01 报告 §3 降级策略）。"""
    routes = {
        char_marker_for("艾拉"): [intent_json("npc1", action_type="wait", action_description="等待")],
        char_marker_for("布鲁诺"): [RuntimeError("boom")],
    }
    _, node = _graph_and_node("characters_all_decide", routes)
    out = await node(make_base_state())
    assert [i["character_id"] for i in out["action_intents"]] == ["npc1"]
    assert "[角色] 艾拉: 等待" in out["event_log"]
    assert "[错误] 布鲁诺 决策失败，本轮跳过。" in out["event_log"]


async def test_chars_missing_position_key_degrades():
    """known-bug-candidate：character_user.j2 直接访问 char.position.x。

    邻近（<=20m）NPC 的 character dict 若缺 ``position`` 键，模板渲染抛
    UndefinedError，该 NPC 决策整体降级。真实剧本经 agents/init.py 加载时
    character dict 保留 YAML 的 position 键故通常不触发；但 NPC 移动后
    character_positions 更新而 character dict 的 position 永不更新（陈旧坐标），
    见 test_char_graph.py 的 E2E 断言。
    """
    routes = {
        char_marker_for("艾拉"): [intent_json("npc1")],
        char_marker_for("布鲁诺"): [intent_json("npc2")],
    }
    llm, node = _graph_and_node("characters_all_decide", routes)
    char_a = make_char("npc1", "艾拉", {"x": 0, "y": 0, "z": 0})
    char_b = make_char("npc2", "布鲁诺", {"x": 1, "y": 0, "z": 0})
    del char_a["position"]
    del char_b["position"]
    state = make_base_state(characters={"npc1": char_a, "npc2": char_b},
                            character_positions={"npc1": {"x": 0, "y": 0, "z": 0},
                                                 "npc2": {"x": 1, "y": 0, "z": 0}})
    out = await node(state)
    assert out["action_intents"] == []
    assert "[错误] 艾拉 决策失败，本轮跳过。" in out["event_log"]
    assert "[错误] 布鲁诺 决策失败，本轮跳过。" in out["event_log"]
    assert llm.call_count(char_marker_for("艾拉")) == 0  # 渲染失败发生在 LLM 调用前


# ══════════════════════════════════════════════════════════════════════════
# 4. tick_speed_resolve（确定性，无 LLM）
# ══════════════════════════════════════════════════════════════════════════

async def test_tick_output_contract_keys():
    """输出字段契约（T01 报告 §3）。"""
    _, node = _graph_and_node("tick_speed_resolve")
    out = await node({"player_action": None, "action_intents": [], "ticks_per_game_minute": 0.2})
    assert set(out) == {"tick_duration_minutes", "player_action", "action_intents",
                        "action_continuation", "event_log"}


async def test_tick_default_fallback_without_world_rules():
    """无 tick_speed 规则：fallback = 1 / max(ticks_per_game_minute, 0.01)。"""
    _, node = _graph_and_node("tick_speed_resolve")
    out = await node({"player_action": None, "action_intents": [], "ticks_per_game_minute": 0.2})
    assert out["tick_duration_minutes"] == pytest.approx(5.0)  # 1/0.2
    assert out["event_log"] == ["[时间] 本 tick 推进 5.0 分钟"]


async def test_tick_min_of_npc_durations():
    """默认策略：有 NPC 耗时 → 取最小值（即使 world_rules.default 更大）。"""
    _, node = _graph_and_node("tick_speed_resolve")
    state = make_base_state(
        player_action=None,
        action_intents=[
            {"character_id": "npc1", "action_type": "speak", "duration_minutes": 3.0},
            {"character_id": "npc2", "action_type": "move", "duration_minutes": 1.5},
        ],
    )
    out = await node(state)
    assert out["tick_duration_minutes"] == pytest.approx(1.5)


async def test_tick_player_duration_when_no_npc_durations():
    _, node = _graph_and_node("tick_speed_resolve")
    state = make_base_state(
        player_action={"action_type": "interact", "duration_minutes": 7.0},
        action_intents=[],
    )
    out = await node(state)
    assert out["tick_duration_minutes"] == pytest.approx(7.0)


async def test_tick_clamps_to_min_and_max():
    _, node = _graph_and_node("tick_speed_resolve")
    base = make_base_state(world_rules={"tick_speed": {"default": 2.0, "min_minutes": 1.0, "max_minutes": 4.0}})
    out = await node({**base, "player_action": None,
                      "action_intents": [{"character_id": "n", "duration_minutes": 0.2}]})
    assert out["tick_duration_minutes"] == pytest.approx(1.0)  # 0.2 被 min_minutes 抬升
    out = await node({**base, "player_action": None,
                      "action_intents": [{"character_id": "n", "duration_minutes": 100.0}]})
    assert out["tick_duration_minutes"] == pytest.approx(4.0)  # 被 max_minutes 截断


async def test_tick_expression_path():
    """world_rules.tick_speed.rule 表达式求值（tick_eval.py；表达式必须以 if(...) 开头）。"""
    _, node = _graph_and_node("tick_speed_resolve")
    state = make_base_state(
        player_action={"action_type": "move", "duration_minutes": 1.0},
        action_intents=[],
        world_rules={"tick_speed": {"default": 2.0,
                                    "rule": "if(player_action.action_type = move, max(player_duration, 4.0); default)"}},
    )
    out = await node(state)
    assert out["tick_duration_minutes"] == pytest.approx(4.0)


async def test_tick_expression_error_falls_back_to_default():
    """表达式求值失败 → 降级为 default（T01 报告 §3）。"""
    _, node = _graph_and_node("tick_speed_resolve")
    state = make_base_state(
        player_action=None,
        action_intents=[],
        world_rules={"tick_speed": {"default": 2.5, "rule": "this is (( not valid"}},
    )
    out = await node(state)
    assert out["tick_duration_minutes"] == pytest.approx(2.5)


async def test_tick_player_truncation_creates_continuation():
    """玩家行动超时被截断；continue_until 非空时生成剩余时长的 continuation。

    注意：默认策略下 tick 跟随玩家行动时长，需 max_minutes 压低 tick 才触发截断。
    """
    _, node = _graph_and_node("tick_speed_resolve")
    state = make_base_state(
        player_action={
            "action_type": "interact", "action_description": "持续搜查",
            "duration_minutes": 10.0, "continue_until": "done", "target_object_id": "crate",
        },
        action_intents=[],
        world_rules={"tick_speed": {"default": 2.0, "min_minutes": 0.1, "max_minutes": 2.0}},
    )
    out = await node(state)
    assert out["tick_duration_minutes"] == pytest.approx(2.0)
    assert out["player_action"]["duration_minutes"] == pytest.approx(2.0)
    cont = out["action_continuation"]
    assert cont is not None
    assert cont["duration_minutes"] == pytest.approx(8.0)
    assert cont["continue_until"] == "done"
    assert cont["action_description"] == "持续搜查"


async def test_tick_player_truncation_without_continue_until_has_no_continuation():
    """超时但 continue_until 为空：只截断，不产生 continuation。"""
    _, node = _graph_and_node("tick_speed_resolve")
    state = make_base_state(
        player_action={"action_type": "interact", "duration_minutes": 10.0, "continue_until": ""},
        action_intents=[],
        world_rules={"tick_speed": {"default": 2.0, "max_minutes": 2.0}},
    )
    out = await node(state)
    assert out["player_action"]["duration_minutes"] == pytest.approx(2.0)
    assert out["action_continuation"] is None


async def test_tick_speak_wait_observe_not_truncated():
    """speak/wait/observe 不参与截断（玩家与 NPC 同规则）。"""
    _, node = _graph_and_node("tick_speed_resolve")
    state = make_base_state(
        player_action={"action_type": "speak", "duration_minutes": 10.0, "continue_until": "done"},
        action_intents=[
            {"character_id": "npc1", "action_type": "wait", "duration_minutes": 9.0},
            {"character_id": "npc2", "action_type": "observe", "duration_minutes": 8.0},
        ],
        world_rules={"tick_speed": {"default": 2.0, "max_minutes": 2.0}},
    )
    out = await node(state)
    assert out["tick_duration_minutes"] == pytest.approx(2.0)
    assert out["player_action"]["duration_minutes"] == pytest.approx(10.0)  # 未截断
    assert out["action_continuation"] is None
    durations = [i["duration_minutes"] for i in out["action_intents"]]
    assert durations == [9.0, 8.0]  # 均未截断


async def test_tick_npc_move_truncated():
    """NPC 的 move/interact/use_item 超过 tick 跨度被截断（speak 不截断）。

    注意：默认策略下 tick = min(npc_durations)，因此需要 max_minutes 把 tick
    压到小于 NPC 耗时才能观察到截断。
    """
    _, node = _graph_and_node("tick_speed_resolve")
    state = make_base_state(
        player_action=None,
        action_intents=[
            {"character_id": "npc1", "action_type": "move", "duration_minutes": 30.0},
            {"character_id": "npc2", "action_type": "speak", "duration_minutes": 30.0},
        ],
        world_rules={"tick_speed": {"default": 2.0, "max_minutes": 4.0}},
    )
    out = await node(state)
    assert out["tick_duration_minutes"] == pytest.approx(4.0)  # min(30,30)=30 → clamp 4.0
    by_id = {i["character_id"]: i for i in out["action_intents"]}
    assert by_id["npc1"]["duration_minutes"] == pytest.approx(4.0)
    assert by_id["npc2"]["duration_minutes"] == pytest.approx(30.0)


# ══════════════════════════════════════════════════════════════════════════
# 5. physics_resolve — F821（game_graph.py:475）当前行为
# ══════════════════════════════════════════════════════════════════════════

async def test_physics_f821_degrades_even_with_tick_duration_present():
    """known-bug-candidate（P0-T02 基线报告 §5.2 #15 的实测刻画）。

    game_graph.py:475 ``state.get("tick_duration_minutes", fallback)`` 中
    ``fallback`` 在 physics_resolve 作用域内未定义。Python 会先求值 .get 的
    默认参数，因此 **无论 state 是否包含 tick_duration_minutes**，节点都会抛
    NameError 并被外层 try/except 吞掉 → 物理模拟恒降级为空结果。
    即：v1 当前物理节点从不实际调用 LLM（本测试断言 call_count == 0）。
    T01/T02 报告描述为"state 缺该键时触发"，实测影响面更大（总是触发）。
    记录现状，不修复。
    """
    routes = {M_PHYSICS: ["不应被调用"]}
    llm, node = _graph_and_node("physics_resolve", routes)
    state = make_base_state(tick_duration_minutes=2.0)
    out = await node(state)
    assert out == {
        "physics_outcomes": [],
        "event_log": ["[错误] 物理模拟失败，本轮跳过物理结果。"],
    }
    assert llm.call_count(M_PHYSICS) == 0


async def test_physics_f821_degrades_without_tick_duration_key():
    """state 完全缺失 tick_duration_minutes：行为与上一测试完全一致。"""
    routes = {M_PHYSICS: ["不应被调用"]}
    llm, node = _graph_and_node("physics_resolve", routes)
    state = make_base_state()
    assert "tick_duration_minutes" not in state  # 工厂状态本身不含该键
    out = await node(state)
    assert out["physics_outcomes"] == []
    assert out["event_log"] == ["[错误] 物理模拟失败，本轮跳过物理结果。"]
    assert llm.call_count(M_PHYSICS) == 0


# ══════════════════════════════════════════════════════════════════════════
# 6. state_apply（确定性，无 LLM）
# ══════════════════════════════════════════════════════════════════════════

def _state_apply_state(**overrides):
    defaults = dict(
        player_action={
            "action_type": "move", "action_description": "走向木箱",
            "target_position": {"x": 1, "y": 0, "z": 0}, "feasibility": "allowed",
        },
        action_intents=[
            {"character_id": "npc1", "action_type": "speak", "action_description": "问好",
             "target_character_id": "npc2", "emotion": "友好", "duration_minutes": 1.0},
        ],
        physics_outcomes=[],
        tick_duration_minutes=2.0,
    )
    defaults.update(overrides)
    return make_base_state(**defaults)


def test_state_apply_output_contract_keys():
    """输出字段契约（T01 报告 §3）。"""
    _, node = _graph_and_node("state_apply")
    out = node(_state_apply_state())
    assert set(out) == {"character_positions", "objects", "characters", "player",
                        "tick", "player_input", "game_time", "environment", "event_log"}


def test_state_apply_physics_outcomes_movement_state_destruction():
    """物理结果应用：movement 位移叠加、state_change 状态合并、destruction 标记 broken。"""
    _, node = _graph_and_node("state_apply")
    state = _state_apply_state(
        player_action=None,
        action_intents=[],
        objects={
            "crate": {"object_id": "crate", "name": "木箱", "position": {"x": 1, "y": 0, "z": 0},
                      "state": {}, "properties": {}},
            "door": {"object_id": "door", "name": "门", "position": {"x": 3, "y": 0, "z": 0},
                     "state": {"open": False}, "properties": {}},
            "vase": {"object_id": "vase", "name": "花瓶", "position": {"x": 2, "y": 0, "z": 0},
                     "state": {"value": "完好"}, "properties": {}},  # str state → {"value": str}
        },
        physics_outcomes=[
            {"outcome_type": "movement", "subject_object_id": "crate",
             "position_delta": {"x": 0.5, "y": 0, "z": 0}, "description": "木箱滑动"},
            {"outcome_type": "state_change", "subject_object_id": "door",
             "new_state": {"open": True}, "description": "门开了"},
            {"outcome_type": "destruction", "subject_object_id": "vase",
             "new_state": {"shards": 3}, "description": "花瓶碎了"},
        ],
    )
    out = node(state)
    assert out["objects"]["crate"]["position"] == {"x": 1.5, "y": 0, "z": 0}
    assert out["objects"]["door"]["state"] == {"open": True}
    # destruction：str state 先包成 {"value": ...} 再加 broken=True 与 new_state
    assert out["objects"]["vase"]["state"] == {"value": "完好", "broken": True, "shards": 3}


def test_state_apply_tick_fields_and_game_time_day_drop():
    """tick+1、player_input 清空、时间推进；known-bug-candidate：game_time 的 day 键被丢弃。"""
    _, node = _graph_and_node("state_apply")
    state = _state_apply_state(player_action=None, action_intents=[],
                               game_time={"day": 3, "hour": 23, "minute": 59},
                               tick_duration_minutes=2.0)
    out = node(state)
    assert out["tick"] == 1
    assert out["player_input"] is None
    # 23:59 + 2 分钟 → 次日 00:01，但 advance_game_time 只返回 hour/minute
    assert out["game_time"] == {"hour": 0, "minute": 1}
    assert "day" not in out["game_time"]  # known-bug-candidate：day 信息丢失
    assert out["environment"]["time_of_day"] == "深夜"  # time_of_day_from_hour(0)


def test_state_apply_tick_dur_fallback_when_missing():
    """tick_duration_minutes 缺失/<=0 时回退 1/max(ticks_per_game_minute, 0.01)=5.0。"""
    _, node = _graph_and_node("state_apply")
    state = _state_apply_state(player_action=None, action_intents=[],
                               game_time={"hour": 8, "minute": 0})
    state.pop("tick_duration_minutes", None)
    out = node(state)
    assert out["game_time"] == {"hour": 8, "minute": 5}


def test_state_apply_player_move_and_blocked_events():
    _, node = _graph_and_node("state_apply")
    out = node(_state_apply_state())
    assert out["player"]["position"] == {"x": 1.0, "y": 0.0, "z": 0.0}
    assert "[玩家状态] 玩家移动到 {'x': 1.0, 'y': 0.0, 'z': 0.0}" in out["event_log"]

    blocked_state = _state_apply_state(player_action={
        "action_type": "interact", "action_description": "撬锁",
        "feasibility": "blocked", "feasibility_reason": "没有工具",
    })
    out = node(blocked_state)
    assert out["event_log"] == ["[玩家行动被阻止] 撬锁：没有工具"]


def test_state_apply_uncertain_roll_both_outcomes(monkeypatch):
    """uncertain + requires_roll：随机掷骰（monkeypatch random 固定两个分支）。"""
    _, node = _graph_and_node("state_apply")
    action = {
        "action_type": "move", "action_description": "跳过沟渠",
        "target_position": {"x": 5, "y": 0, "z": 0},
        "feasibility": "uncertain", "requires_roll": True, "success_probability": 0.5,
    }
    monkeypatch.setattr(random_module, "random", lambda: 0.1)  # 0.1 < 0.5 → 成功
    out = node(_state_apply_state(player_action=action))
    assert out["event_log"][0].startswith("[检定成功] 跳过沟渠（成功概率: 50%）")
    assert out["player"]["position"] == {"x": 5.0, "y": 0.0, "z": 0.0}

    monkeypatch.setattr(random_module, "random", lambda: 0.9)  # 0.9 >= 0.5 → 失败
    out = node(_state_apply_state(player_action=action))
    assert out["event_log"] == ["[检定失败] 跳过沟渠（成功概率: 50%）"]
    assert out["player"]["position"] == {"x": 0, "y": 0, "z": 0}  # 未移动


def test_state_apply_npc_speak_and_move():
    """NPC speak：双向 conversation_target、last_spoken_to、情绪好感度 +0.05；move 更新坐标。"""
    _, node = _graph_and_node("state_apply")
    state = _state_apply_state(
        player_action=None,
        action_intents=[
            {"character_id": "npc1", "action_type": "speak", "action_description": "问好",
             "target_character_id": "npc2", "emotion": "友好", "duration_minutes": 1.0},
            {"character_id": "npc2", "action_type": "move", "action_description": "走向木箱",
             "target_position": {"x": 1, "y": 0, "z": 0}, "duration_minutes": 1.0},
        ],
    )
    out = node(state)
    npc1, npc2 = out["characters"]["npc1"], out["characters"]["npc2"]
    assert npc1["last_spoken_to"] == "npc2"
    assert npc1["conversation_target"] == "npc2"
    assert npc1["relationships"]["npc2"] == pytest.approx(0.05)
    # npc2 随后被 move 处理：conversation_target 被 pop（characterization）
    assert "conversation_target" not in npc2
    assert npc2["last_spoken_to"] == "npc1"
    assert out["character_positions"]["npc2"] == {"x": 1.0, "y": 0.0, "z": 0.0}
    assert "[NPC状态] 布鲁诺 移动到 {'x': 1.0, 'y': 0.0, 'z': 0.0}" in out["event_log"]


def test_state_apply_memory_receives_recent_events_capped_at_50():
    """每个 NPC memory 追加 event_log 最近 10 条，总长上限 50。"""
    _, node = _graph_and_node("state_apply")
    state = _state_apply_state(player_action=None, action_intents=[],
                               event_log=[f"[角色] 旧事件{i}" for i in range(15)])
    state["characters"]["npc1"]["memory"] = [f"m{i}" for i in range(48)]
    out = node(state)
    mem = out["characters"]["npc1"]["memory"]
    assert len(mem) == 50
    # 追加的是最近 10 条旧事件（state_apply 时本轮事件尚未写入）
    assert mem[-10:] == [f"[角色] 旧事件{i}" for i in range(5, 15)]


def test_state_apply_compaction_appends_summary_line():
    """known-behavior：event_log>100 时，state_apply 只把压缩摘要行作为新事件追加。

    由于 event_log 是 operator.add reducer 通道，节点无法原地替换历史；
    原始事件全部保留，摘要行被追加（日志只增不减）。
    """
    _, node = _graph_and_node("state_apply")
    state = _state_apply_state(player_action=None, action_intents=[],
                               event_log=[f"[角色] 闲聊{i}" for i in range(120)])
    out = node(state)
    assert out["event_log"] == [
        "[摘要] 前 70 条事件：角色对话 70 次，物理变化 0 次，玩家行动 0 次，NPC状态 0 次。"
    ]


# ══════════════════════════════════════════════════════════════════════════
# 7. natural_attribute_delta（确定性，无 LLM）
# ══════════════════════════════════════════════════════════════════════════

def test_natural_delta_output_contract_keys():
    _, node = _graph_and_node("natural_attribute_delta")
    state = make_base_state(tick_duration_minutes=1.0)
    out = node(state)
    assert set(out) == {"player", "characters", "event_log", "attribute_deltas",
                        "deferred_natural_deltas", "deferred_locked_rules"}


def test_natural_delta_applies_and_reports_diff():
    """按 tick 时长应用每分钟自然增减；attribute_deltas 输出结构化 diff（含 hidden 标记）。"""
    _, node = _graph_and_node("natural_attribute_delta")
    state = make_base_state(tick_duration_minutes=3.0)
    state["player"]["attributes"]["stamina"]["natural_delta_per_minute"] = -1.0
    state["player"]["attributes"]["sanity"]["natural_delta_per_minute"] = 0.5
    out = node(state)
    assert out["player"]["attributes"]["stamina"]["value"] == pytest.approx(77.0)
    assert out["player"]["attributes"]["sanity"]["value"] == pytest.approx(51.5)
    assert out["event_log"] == [
        "[属性] 测试者的体力自然变化 80 → 77",
        "[属性] 测试者的理智自然变化 50 → 51.5",
    ]
    by_key = {d["attribute_key"]: d for d in out["attribute_deltas"]}
    assert by_key["stamina"]["delta"] == pytest.approx(-3.0)
    assert by_key["stamina"]["old_value"] == 80
    assert by_key["stamina"]["new_value"] == pytest.approx(77.0)
    assert by_key["stamina"]["hidden"] is False
    assert by_key["sanity"]["hidden"] is True
    assert out["deferred_natural_deltas"] == []


def test_natural_delta_locked_attribute_skipped():
    """locked=true 属性不受自然增减影响（_apply_delta 返回 None）。"""
    _, node = _graph_and_node("natural_attribute_delta")
    state = make_base_state(tick_duration_minutes=5.0)
    state["player"]["attributes"]["stamina"].update({"locked": True, "natural_delta_per_minute": -1.0})
    out = node(state)
    assert out["player"]["attributes"]["stamina"]["value"] == 80
    assert out["event_log"] == []
    assert out["attribute_deltas"] == []


def test_natural_delta_defers_post_narrative_attributes():
    """update_position=post_narrative 的自然增减被延迟到 post_narrative_update。"""
    _, node = _graph_and_node("natural_attribute_delta")
    state = make_base_state(tick_duration_minutes=4.0)
    state["player"]["attributes"]["calm"] = {
        "name": "平静", "value": 10, "max": 100,
        "natural_delta_per_minute": 2.0, "update_position": "post_narrative",
    }
    out = node(state)
    assert out["player"]["attributes"]["calm"]["value"] == 10  # 未应用
    assert out["deferred_natural_deltas"] == [
        {"entity_type": "player", "entity_id": "player_1", "attribute_key": "calm"},
    ]
    assert out["attribute_deltas"] == []


def test_natural_delta_deterministic_rules_split_pre_post():
    """locked_attributes 规则：pre_narrative 立即执行，post_narrative 进入 deferred_locked_rules。"""
    _, node = _graph_and_node("natural_attribute_delta")
    state = make_base_state(tick_duration_minutes=2.0)
    state["player"]["attributes"].update({
        "danger": {"name": "危险", "value": 1},
        "alert_timer": {"name": "警报计时", "value": 0, "locked": True},
        "calm_timer": {"name": "平静计时", "value": 0, "locked": True},
    })
    state["world_rules"] = {
        "locked_attributes": [
            {"type": "timer", "timer_key": "alert_timer", "condition": "danger > 0"},
            {"type": "timer", "timer_key": "calm_timer", "condition": "danger > 0",
             "update_position": "post_narrative"},
        ],
    }
    out = node(state)
    assert out["player"]["attributes"]["alert_timer"]["value"] == pytest.approx(2.0)
    assert out["player"]["attributes"]["calm_timer"]["value"] == 0  # 延迟
    assert len(out["deferred_locked_rules"]) == 1
    assert out["deferred_locked_rules"][0]["timer_key"] == "calm_timer"


# ══════════════════════════════════════════════════════════════════════════
# 8. attribute_update（LLM 语义属性）
# ══════════════════════════════════════════════════════════════════════════

async def test_attr_update_skips_when_no_attributes_defined():
    """玩家与 NPC 均无属性：直接跳过（{}），不调用 LLM（T01 报告 §3）。"""
    routes = {M_ATTR: ["不应被调用"]}
    llm, node = _graph_and_node("attribute_update", routes)
    state = make_base_state()
    state["player"]["attributes"] = {}
    state["characters"] = {"npc1": make_char("npc1", "艾拉", {"x": 2, "y": 0, "z": 0}, attributes={})}
    out = await node(state)
    assert out == {}
    assert llm.call_count(M_ATTR) == 0


async def test_attr_update_applies_delta_changes():
    routes = {M_ATTR: [attr_update_json(changes=[
        {"entity_type": "player", "attribute_key": "stamina", "delta": -2.0, "reason": "累了"},
        {"entity_type": "character", "entity_id": "npc1", "attribute_key": "mood", "delta": 5.0, "reason": "开心"},
    ])]}
    llm, node = _graph_and_node("attribute_update", routes)
    out = await node(make_base_state())
    assert out["player"]["attributes"]["stamina"]["value"] == pytest.approx(78.0)
    assert out["characters"]["npc1"]["attributes"]["mood"]["value"] == pytest.approx(55.0)
    assert "[属性] 测试者的体力 80 → 78（累了）" in out["event_log"]
    assert "[属性] 艾拉的心情 50 → 55（开心）" in out["event_log"]


async def test_attr_update_new_value_mode_and_unknown_key_warning():
    """new_value 直接赋值（事件格式带冒号）；不存在的 key 产生 [警告] 事件。"""
    routes = {M_ATTR: [attr_update_json(changes=[
        {"entity_type": "player", "attribute_key": "stamina", "new_value": 30, "reason": "重置"},
        {"entity_type": "player", "attribute_key": "nonexistent"},
    ])]}
    _, node = _graph_and_node("attribute_update", routes)
    out = await node(make_base_state())
    assert out["player"]["attributes"]["stamina"]["value"] == 30
    assert "[属性] 测试者的体力: 80 → 30（重置）" in out["event_log"]
    assert "[警告] 属性更新忽略了不存在的属性：player.nonexistent" in out["event_log"]


async def test_attr_update_llm_exception_degrades():
    """LLM 失败：忽略本轮属性更新，只留错误日志（T01 报告 §3）。"""
    routes = {M_ATTR: [RuntimeError("boom")]}
    _, node = _graph_and_node("attribute_update", routes)
    out = await node(make_base_state())
    assert out == {"event_log": ["[错误] 属性更新失败，已跳过本轮属性事件更新。"]}


# ══════════════════════════════════════════════════════════════════════════
# 9. sensory_filter（LLM 感官过滤）
# ══════════════════════════════════════════════════════════════════════════

async def test_sensory_success_contract_visible_attrs_and_self_action():
    """成功路径：player_percept 附加 self_action_summary 与可见属性（hidden 被过滤）。"""
    routes = {M_SENSORY: [percept_json(
        senses=[{"sense": "sight", "description": "看到广场"}], summary="广场很安静",
    )]}
    llm, node = _graph_and_node("sensory_filter", routes)
    state = make_base_state(player_action={
        "action_type": "observe", "action_description": "环顾四周",
        "feasibility": "allowed", "speech_content": None, "subconscious_adjustment": None,
    })
    out = await node(state)
    assert set(out) == {"player_percept"}  # 成功路径不写 event_log（characterization）
    percept = out["player_percept"]
    assert percept["summary"] == "广场很安静"
    assert percept["self_action_summary"] == "你环顾四周"
    assert list(percept["player_attributes"]) == ["stamina"]  # hidden 的 sanity 被过滤
    assert llm.call_count(M_SENSORY) == 1


async def test_sensory_self_action_summary_blocked_speech_subconscious():
    """self_action_summary 组装顺序：[内心] → 行动（blocked 文案）→ 说话。"""
    routes = {M_SENSORY: [percept_json(summary="x")]}
    llm, node = _graph_and_node("sensory_filter", routes)
    state = make_base_state(player_action={
        "action_type": "interact",
        "action_description": "推开大门",
        "feasibility": "blocked",
        "feasibility_reason": "门被锁住了",
        "speech_content": "有人吗？",
        "subconscious_adjustment": "有点不安",
    })
    await node(state)
    prompt = llm.user_prompt_of(M_SENSORY)
    expected = '[内心] 有点不安\n你试图推开大门，但未能成功：门被锁住了\n你说："有人吗？"'
    assert expected in prompt


async def test_sensory_radius_filters_far_entities_from_prompt():
    """视野半径（默认取 capabilities.sight_range_m）外的物体/角色不进入感官 prompt。"""
    routes = {M_SENSORY: [percept_json(summary="x")]}
    llm, node = _graph_and_node("sensory_filter", routes)
    state = make_base_state(
        player_action=None,
        objects={
            "near_cup": {"object_id": "near_cup", "name": "近处茶杯", "description": "d",
                         "position": {"x": 3, "y": 0, "z": 0}},
            "far_tower": {"object_id": "far_tower", "name": "远处高塔", "description": "d",
                          "position": {"x": 200, "y": 0, "z": 0}},
        },
        characters={"npc1": make_char("npc1", "远方的旅人", {"x": 300, "y": 0, "z": 0})},
        character_positions={"npc1": {"x": 300, "y": 0, "z": 0}},
    )
    await node(state)
    prompt = llm.user_prompt_of(M_SENSORY)
    assert "近处茶杯" in prompt
    assert "远处高塔" not in prompt
    assert "远方的旅人" not in prompt


async def test_sensory_llm_exception_default_percept():
    """LLM 失败（T01 报告 §3：降级为默认感知结构）。"""
    routes = {M_SENSORY: [RuntimeError("boom")]}
    _, node = _graph_and_node("sensory_filter", routes)
    state = make_base_state(player_action={
        "action_type": "observe", "action_description": "环顾四周",
        "feasibility": "allowed", "speech_content": None, "subconscious_adjustment": None,
    })
    out = await node(state)
    percept = out["player_percept"]
    assert percept["summary"] == "你暂时无法感知周围环境。"
    assert percept["senses"] == []
    assert percept["hidden_event_count"] == 0
    assert percept["self_action_summary"] == "你环顾四周"
    assert list(percept["player_attributes"]) == ["stamina"]
    assert out["event_log"] == ["[错误] 感官过滤失败，使用默认感知。"]


# ══════════════════════════════════════════════════════════════════════════
# 10. narrative_stylize（LLM 叙事润色）
# ══════════════════════════════════════════════════════════════════════════

async def test_narrative_empty_percept_returns_empty_without_llm():
    """player_percept 为空/无 senses 且无 summary：跳过（{}），不调用 LLM。"""
    routes = {M_NARRATIVE: ["不应被调用"]}
    llm, node = _graph_and_node("narrative_stylize", routes)
    assert await node({"player_percept": None}) == {}
    assert await node({"player_percept": {}}) == {}
    assert await node({"player_percept": {"senses": [], "summary": ""}}) == {}
    assert llm.call_count(M_NARRATIVE) == 0


async def test_narrative_success_enriches_percept_and_appends_history():
    routes = {M_NARRATIVE: [narrative_json("文学化叙事文本")]}
    llm, node = _graph_and_node("narrative_stylize", routes)
    state = make_base_state(
        # senses 带 confidence：真实流程中 percept 来自 SenseDetail.model_dump()，必含该字段。
        # （narrative_user.j2 无防护地访问 s.confidence，缺失会导致叙事降级——模板脆弱点，
        #  真实管线上因模型默认值而不触发。）
        player_percept={"summary": "广场很安静",
                        "senses": [{"sense": "sight", "description": "x", "confidence": 1.0}]},
        tick=3,
        game_time={"hour": 9, "minute": 30},
        narrative_history=[{"tick": 2, "narrative": "上一回合", "game_time": {"hour": 9, "minute": 0}}],
    )
    out = await node(state)
    assert out["player_percept"]["narrative"] == "文学化叙事文本"
    assert out["player_percept"]["summary"] == "广场很安静"  # 原 percept 字段保留
    # 节点单次只返回本回合一条历史；operator.add 累加发生在图通道层
    assert out["narrative_history"] == [
        {"tick": 3, "narrative": "文学化叙事文本", "game_time": {"hour": 9, "minute": 30}},
    ]
    # 上一回合叙事被注入 prompt 以保持连贯
    assert "上一回合" in llm.user_prompt_of(M_NARRATIVE)


async def test_narrative_llm_exception_backfills_summary():
    """LLM 失败（T01 报告 §3：player_percept.summary 回填为叙事并记入历史）。"""
    routes = {M_NARRATIVE: [RuntimeError("boom")]}
    _, node = _graph_and_node("narrative_stylize", routes)
    state = make_base_state(
        player_percept={"summary": "原始感知摘要",
                        "senses": [{"sense": "sight", "description": "x", "confidence": 1.0}]},
        tick=1,
        game_time={"hour": 8, "minute": 5},
    )
    out = await node(state)
    assert out["player_percept"]["narrative"] == "原始感知摘要"
    assert out["narrative_history"] == [
        {"tick": 1, "narrative": "原始感知摘要", "game_time": {"hour": 8, "minute": 5}},
    ]
    assert out["event_log"] == ["[错误] 叙事渲染失败，使用原始感知文本。"]


# ══════════════════════════════════════════════════════════════════════════
# 11. post_narrative_update（确定性，无 LLM）
# ══════════════════════════════════════════════════════════════════════════

def test_post_narrative_no_deferred_returns_empty():
    _, node = _graph_and_node("post_narrative_update")
    assert node(make_base_state()) == {}


def test_post_narrative_applies_deferred_natural_deltas():
    """延迟自然增减在叙事后应用：数值变化、事件带（叙事后）后缀、deferred 清空。"""
    _, node = _graph_and_node("post_narrative_update")
    state = make_base_state(tick_duration_minutes=3.0)
    state["player"]["attributes"]["calm"] = {
        "name": "平静", "value": 10, "max": 100,
        "natural_delta_per_minute": 2.0, "update_position": "post_narrative",
    }
    state["deferred_natural_deltas"] = [
        {"entity_type": "player", "entity_id": "player_1", "attribute_key": "calm"},
    ]
    out = node(state)
    assert out["player"]["attributes"]["calm"]["value"] == pytest.approx(16.0)
    assert out["event_log"] == ["[属性] 测试者的平静自然变化 10 → 16（叙事后）"]
    assert out["deferred_natural_deltas"] == []
    assert out["deferred_locked_rules"] == []


def test_post_narrative_applies_deferred_character_deltas():
    _, node = _graph_and_node("post_narrative_update")
    state = make_base_state(tick_duration_minutes=2.0)
    state["characters"]["npc1"]["attributes"]["mood"]["natural_delta_per_minute"] = -1.0
    state["characters"]["npc1"]["attributes"]["mood"]["update_position"] = "post_narrative"
    state["deferred_natural_deltas"] = [
        {"entity_type": "character", "entity_id": "npc1", "attribute_key": "mood"},
    ]
    out = node(state)
    assert out["characters"]["npc1"]["attributes"]["mood"]["value"] == pytest.approx(48.0)
    assert out["event_log"] == ["[属性] 艾拉的心情自然变化 50 → 48（叙事后）"]


def test_post_narrative_applies_deferred_locked_rules_with_tag():
    """延迟 locked 规则执行后事件前缀被改写为 [属性](叙事后)。"""
    _, node = _graph_and_node("post_narrative_update")
    state = make_base_state(tick_duration_minutes=2.0)
    state["player"]["attributes"].update({
        "danger": {"name": "危险", "value": 1},
        "calm_timer": {"name": "平静计时", "value": 0, "locked": True},
    })
    state["deferred_locked_rules"] = [
        {"type": "timer", "timer_key": "calm_timer", "condition": "danger > 0",
         "update_position": "post_narrative"},
    ]
    out = node(state)
    assert out["player"]["attributes"]["calm_timer"]["value"] == pytest.approx(2.0)
    assert out["deferred_locked_rules"] == []
    # timer 无 threshold → 无事件；补一个带 warning 的规则验证事件标签
    state2 = make_base_state(tick_duration_minutes=2.0)
    state2["player"]["attributes"].update({
        "danger": {"name": "危险", "value": 1},
        "alert_timer": {"name": "警报计时", "value": 9.0, "locked": True},
    })
    state2["deferred_locked_rules"] = [
        {"type": "timer", "timer_key": "alert_timer", "condition": "danger > 0",
         "thresholds": [10], "warning": "警报已持续{threshold}分钟。",
         "update_position": "post_narrative"},
    ]
    out2 = node(state2)
    assert out2["event_log"] == ["[属性](叙事后) 测试者: 警报已持续10.0分钟。"]
