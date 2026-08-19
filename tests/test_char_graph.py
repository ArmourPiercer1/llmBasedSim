"""P0-T03: game_graph.py 11 节点流程端到端 characterization 测试（图级）。

用 FakeLLM（ainvoke 层替身）驱动编译后的完整 LangGraph，锁定 v1 当前真实行为：
- 全图端到端：player 输入 → 11 节点 → player_percept / narrative 与关键 state 字段；
- Fan-out 分支（attribute_update 与 sensory_filter→narrative_stylize→post_narrative_update）
  都执行且结果合并的确定性语义；
- 三个 reducer 通道（event_log / action_intents / narrative_history）的累加行为，
  含 action_intents 重复累加、event_log 压缩摘要追加等 known-bug-candidate；
- 各 LLM 节点失败时的降级路径在完整流水线中的传播；
- action_continuation 长行动延续（/c）、终止（/stop）与打断；
- 多回合运行契约（main.py 模式：每回合新 thread_id + reset_tick_transients）。

Characterization 纪律：只记录 v1 当前行为。看起来像 bug 的行为按现状断言，
并在注释中标记 ``known-bug-candidate``（由人工 H1 决定是否作为兼容契约）。

运行方式（无网络、无 API key、无真实 LLM）：
    .venv/bin/python -m pytest tests/test_char_graph.py -q
"""

from __future__ import annotations

import pytest

from src.graph.game_state import reset_tick_transients
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
    default_routes,
    make_base_state,
    make_char,
    narrative_json,
    new_thread_id,
    percept_json,
    player_action_json,
)


async def _run(routes, state):
    llm = FakeLLM(routes)
    graph = build_test_graph(llm)
    result = await graph.ainvoke(state, {"configurable": {"thread_id": new_thread_id()}})
    return llm, result


# ══════════════════════════════════════════════════════════════════════════
# a. 全图端到端（11 节点）+ b. 关键字段契约
# ══════════════════════════════════════════════════════════════════════════

async def test_e2e_full_flow_characterization():
    """全图端到端基线：默认 happy-path 场景的完整行为刻画（断言全部来自真实运行）。

    场景：玩家"环顾四周"（observe），艾拉向布鲁诺问好（speak 1min，情绪友好），
    布鲁诺走向木箱（move 3min → 被截断为 1min）。
    """
    llm, res = await _run(default_routes(), make_base_state())

    # ── 基础回合字段 ──
    assert res["tick"] == 1
    assert res["player_input"] is None
    assert res["tick_duration_minutes"] == pytest.approx(1.0)  # min(npc_durations)=min(1,3)

    # ── 时间推进；known-bug-candidate：advance_game_time 丢弃 day 键 ──
    assert res["game_time"] == {"hour": 8, "minute": 1}
    assert res["environment"]["time_of_day"] == "上午"

    # ── LLM 调用账目：物理节点因 F821 从不被调用（见 test_char_nodes.py）──
    assert llm.call_count(M_INTENT) == 1
    assert llm.call_count(M_RESOLVE) == 1
    assert llm.call_count(char_marker_for("艾拉")) == 1
    assert llm.call_count(char_marker_for("布鲁诺")) == 1
    assert llm.call_count(M_ATTR) == 1
    assert llm.call_count(M_SENSORY) == 1
    assert llm.call_count(M_NARRATIVE) == 1
    assert llm.call_count(M_PHYSICS) == 0  # known-bug-candidate（F821）

    # ── 玩家行动契约：意图字段保留 + LLM 可行性字段 ──
    pa = res["player_action"]
    assert pa["action_description"] == "环顾四周"
    assert pa["raw_input"] == "环顾四周"
    assert pa["feasibility"] == "allowed"
    assert pa["feasibility_reason"] == "可以"

    # ── known-bug-candidate：action_intents reducer 重复累加 ──
    # characters_all_decide 写入原始列表，tick_speed_resolve 以 operator.add 再追加
    # 截断后的完整列表 → 每个 intent 出现两次（原始 + 截断副本）。
    assert len(res["action_intents"]) == 4
    assert [(i["character_id"], i["duration_minutes"]) for i in res["action_intents"]] == [
        ("npc1", 1.0), ("npc2", 3.0),   # characters_all_decide 原始输出
        ("npc1", 1.0), ("npc2", 1.0),   # tick_speed_resolve 截断后重写（npc2 3.0→1.0）
    ]

    # ── 物理恒降级（F821）：canned 的 sound outcome 不会出现 ──
    assert res["physics_outcomes"] == []

    # ── state_apply 效果 ──
    assert res["player"]["position"] == {"x": 0, "y": 0, "z": 0}  # observe 不移位
    # npc2 权威坐标更新；known-bug-candidate：char dict 内 position 永不更新（陈旧）
    assert res["character_positions"]["npc2"] == {"x": 1.0, "y": 0.0, "z": 0.0}
    assert res["characters"]["npc2"]["position"] == {"x": 5, "y": 0, "z": 0}
    # npc1 speak：双向会话标记 + 好感度；重复 intent 导致好感度 +0.05×2（known-bug-candidate）
    npc1, npc2 = res["characters"]["npc1"], res["characters"]["npc2"]
    assert npc1["last_spoken_to"] == "npc2"
    assert npc1["conversation_target"] == "npc2"
    assert npc1["relationships"]["npc2"] == pytest.approx(0.10)
    assert npc2["last_spoken_to"] == "npc1"
    assert "conversation_target" not in npc2  # npc2 随后被自己的 move intent 清掉
    # memory = state_apply 时刻 event_log 最近 10 条（此时共 7 条）
    assert npc1["memory"] == [
        "[初始] 游戏开始",
        "[玩家意图] 环顾四周",
        "[玩家行动] 环顾四周（allowed: 可以）",
        "[角色] 艾拉: 向布鲁诺问好",
        "[角色] 布鲁诺: 走向木箱",
        "[时间] 本 tick 推进 1.0 分钟",
        "[错误] 物理模拟失败，本轮跳过物理结果。",
    ]

    # ── Fan-out 分支 A：attribute_update 的 LLM 属性变更生效 ──
    assert res["player"]["attributes"]["stamina"]["value"] == pytest.approx(78.0)

    # ── Fan-out 分支 B：sensory → narrative → post_narrative ──
    percept = res["player_percept"]
    assert set(percept) == {"hidden_event_count", "narrative", "player_attributes",
                            "self_action_summary", "senses", "summary"}
    assert percept["summary"] == "广场很安静"
    assert percept["self_action_summary"] == "你环顾四周"
    assert percept["narrative"] == "叙事文本E2E"
    assert list(percept["player_attributes"]) == ["stamina"]  # hidden 的 sanity 被过滤
    assert res["narrative_history"] == [
        {"tick": 1, "narrative": "叙事文本E2E", "game_time": {"hour": 8, "minute": 1}},
    ]
    assert res["deferred_natural_deltas"] == []
    assert res["deferred_locked_rules"] == []

    # ── event_log：reducer 全量累加 + 各节点提交顺序（真实运行刻画）──
    assert res["event_log"] == [
        "[初始] 游戏开始",
        "[玩家意图] 环顾四周",
        "[玩家行动] 环顾四周（allowed: 可以）",
        "[角色] 艾拉: 向布鲁诺问好",
        "[角色] 布鲁诺: 走向木箱",
        "[时间] 本 tick 推进 1.0 分钟",
        "[错误] 物理模拟失败，本轮跳过物理结果。",   # F821 恒降级
        "[玩家状态] 玩家执行了：环顾四周",
        "[NPC状态] 布鲁诺 移动到 {'x': 1.0, 'y': 0.0, 'z': 0.0}",
        "[NPC状态] 布鲁诺 移动到 {'x': 1.0, 'y': 0.0, 'z': 0.0}",  # 重复 intent 重复执行
        "[属性] 测试者的体力 80 → 78（累了）",
    ]


# ══════════════════════════════════════════════════════════════════════════
# d. Fan-out 分支合并语义
# ══════════════════════════════════════════════════════════════════════════

def _fanout_state():
    state = make_base_state(
        player_input="休息",
        characters={},
        character_positions={},
        world_rules={"tick_speed": {"default": 3.0}},
    )
    state["player"]["attributes"] = {
        # pre_narrative 自然增减：+1/min
        "mood": {"name": "心情", "value": 50, "max": 100, "natural_delta_per_minute": 1.0},
        # post_narrative 自然增减：+2/min（延迟到叙事后）
        "calm": {"name": "平静", "value": 10, "max": 100,
                 "natural_delta_per_minute": 2.0, "update_position": "post_narrative"},
    }
    return state


def _fanout_routes():
    return {
        M_INTENT: [player_action_json(interpreted_intent="休息", action_type="wait",
                                      action_description="原地休息")],
        M_RESOLVE: [player_action_json(interpreted_intent="休息", action_type="wait",
                                       action_description="原地休息",
                                       feasibility="allowed", feasibility_reason="可以")],
        M_ATTR: ["placeholder"],  # 各测试覆盖
        M_SENSORY: [percept_json(summary="平静")],
        M_NARRATIVE: [narrative_json("N")],
    }


async def test_e2e_fanout_both_branches_merge_deterministically():
    """Fan-out 合并刻画（重复运行 3 次验证确定性）：

    - 分支 A（attribute_update）与分支 B（sensory→narrative→post_narrative）都执行；
    - LangGraph 超步语义：attribute_update 与 sensory_filter 同超步，分支 B 的后续
      节点在更晚超步执行，读取状态包含分支 A 的写入；最终 player 写入来自
      post_narrative_update（其读取时已含 LLM 属性变更）→ 两类变更都保留；
    - deferred 列表执行后清空。
    """
    for _ in range(3):
        routes = _fanout_routes()
        routes[M_ATTR] = [attr_update_json(changes=[
            {"entity_type": "player", "attribute_key": "mood", "delta": 7.0, "reason": "事件"},
        ])]
        llm, res = await _run(routes, _fanout_state())

        attrs = res["player"]["attributes"]
        # mood = 50 + 自然 3×1（pre） + LLM +7 = 60；calm = 10 + 2×3（post 延迟） = 16
        assert attrs["mood"]["value"] == pytest.approx(60.0)
        assert attrs["calm"]["value"] == pytest.approx(16.0)
        assert res["deferred_natural_deltas"] == []
        # 两个分支的事件都出现，且提交顺序稳定：自然(pre) → LLM属性 → 自然(post 叙事后)
        attr_events = [e for e in res["event_log"] if e.startswith("[属性]")]
        assert attr_events == [
            "[属性] 测试者的心情自然变化 50 → 53",
            "[属性] 测试者的心情 53 → 60（事件）",
            "[属性] 测试者的平静自然变化 10 → 16（叙事后）",
        ]
        # 分支 B 的产物同样存在
        assert res["player_percept"]["narrative"] == "N"


async def test_e2e_attribute_update_skipped_when_no_attributes():
    """玩家与 NPC 均无属性：attribute_update 跳过，不调用 LLM。"""
    routes = default_routes()
    routes[M_ATTR] = ["不应被调用"]
    state = make_base_state()
    state["player"]["attributes"] = {}
    for char in state["characters"].values():
        char["attributes"] = {}
    llm, res = await _run(routes, state)
    assert llm.call_count(M_ATTR) == 0
    assert not any(e.startswith("[属性]") for e in res["event_log"])
    assert res["player_percept"]["narrative"] == "叙事文本E2E"  # 其余流程不受影响


# ══════════════════════════════════════════════════════════════════════════
# e. 各 LLM 节点失败降级路径（完整流水线内）
# ══════════════════════════════════════════════════════════════════════════

async def test_e2e_intent_failure_degrades_and_flow_continues():
    routes = default_routes()
    routes[M_INTENT] = [RuntimeError("boom")]
    llm, res = await _run(routes, make_base_state())
    # characterization：intent 节点写入 None，但 tick_speed_resolve 会把
    # player_action 以 `state.get("player_action") or {}` 重写为空 dict → 最终为 {}
    assert res["player_action"] == {}
    assert "[错误] 玩家输入处理失败，本轮输入被忽略。" in res["event_log"]
    assert not any("[玩家意图]" in e for e in res["event_log"])
    # 后续节点继续：NPC 照常决策、叙事照常产出
    assert "[角色] 艾拉: 向布鲁诺问好" in res["event_log"]
    assert res["player_percept"]["narrative"] == "叙事文本E2E"


async def test_e2e_resolve_failure_keeps_intent_action():
    routes = default_routes()
    routes[M_RESOLVE] = [RuntimeError("boom")]
    llm, res = await _run(routes, make_base_state())
    assert "[错误] 玩家行动可行性判断失败，跳过可行性检查。" in res["event_log"]
    # 保留意图节点产出的行动（feasibility=None → state_apply 按 allowed 处理）
    assert res["player_action"]["action_description"] == "环顾四周"
    assert res["player_action"]["feasibility"] is None
    assert "[玩家状态] 玩家执行了：环顾四周" in res["event_log"]


async def test_e2e_npc_partial_failure():
    """单个 NPC 失败不影响其他 NPC，也不中断流水线。"""
    routes = default_routes()
    routes[char_marker_for("布鲁诺")] = [RuntimeError("boom")]
    llm, res = await _run(routes, make_base_state())
    assert "[错误] 布鲁诺 决策失败，本轮跳过。" in res["event_log"]
    assert "[角色] 艾拉: 向布鲁诺问好" in res["event_log"]
    # 仅 npc1 的 intent（原始 + tick_speed 重写副本；speak 不被截断）
    assert [(i["character_id"], i["duration_minutes"]) for i in res["action_intents"]] == [
        ("npc1", 1.0), ("npc1", 1.0),
    ]
    assert res["characters"]["npc1"]["last_spoken_to"] == "npc2"
    assert res["player_percept"]["narrative"] == "叙事文本E2E"


async def test_e2e_sensory_failure_default_percept_flows_to_narrative():
    """sensory 降级产出的默认感知继续流入 narrative_stylize。"""
    routes = default_routes()
    routes[M_SENSORY] = [RuntimeError("boom")]
    llm, res = await _run(routes, make_base_state())
    percept = res["player_percept"]
    assert percept["summary"] == "你暂时无法感知周围环境。"
    assert percept["senses"] == []
    assert percept["narrative"] == "叙事文本E2E"  # 叙事节点仍用默认感知调 LLM
    assert "[错误] 感官过滤失败，使用默认感知。" in res["event_log"]


async def test_e2e_narrative_failure_backfills_summary():
    routes = default_routes()
    routes[M_NARRATIVE] = [RuntimeError("boom")]
    llm, res = await _run(routes, make_base_state())
    percept = res["player_percept"]
    assert percept["narrative"] == "广场很安静"  # summary 回填
    assert res["narrative_history"] == [
        {"tick": 1, "narrative": "广场很安静", "game_time": {"hour": 8, "minute": 1}},
    ]
    assert "[错误] 叙事渲染失败，使用原始感知文本。" in res["event_log"]


async def test_e2e_attribute_update_failure_keeps_natural_state():
    routes = default_routes()
    routes[M_ATTR] = [RuntimeError("boom")]
    llm, res = await _run(routes, make_base_state())
    assert "[错误] 属性更新失败，已跳过本轮属性事件更新。" in res["event_log"]
    assert res["player"]["attributes"]["stamina"]["value"] == 80  # LLM 变更未应用
    assert res["player_percept"]["narrative"] == "叙事文本E2E"


async def test_e2e_intent_garbage_json_retries_then_succeeds():
    """解析重试在完整流水线中恢复：前 2 次垃圾 JSON，第 3 次成功。"""
    routes = default_routes()
    routes[M_INTENT] = [GARBAGE, GARBAGE, player_action_json(
        interpreted_intent="环顾四周", action_type="observe", action_description="环顾四周",
    )]
    llm, res = await _run(routes, make_base_state())
    assert llm.call_count(M_INTENT) == 3
    assert res["player_action"]["action_description"] == "环顾四周"
    assert res["player_percept"]["narrative"] == "叙事文本E2E"


# ══════════════════════════════════════════════════════════════════════════
# h. event_log reducer 累加与压缩
# ══════════════════════════════════════════════════════════════════════════

async def test_e2e_event_log_compaction_appends_summary():
    """known-behavior：event_log>100 时仅追加摘要行，原始事件因 reducer 语义全部保留。

    初始 121 条（1 条 [初始] + 120 条 [角色] 闲聊）。state_apply 时刻新增 6 条
    节点事件 → 共 127 条 → old=前 77 条（[初始] + 76 条闲聊），recent=后 50 条。
    """
    initial = ["[初始] 游戏开始"] + [f"[角色] 闲聊{i}" for i in range(120)]
    llm, res = await _run(default_routes(), make_base_state(event_log=initial))
    summaries = [e for e in res["event_log"] if e.startswith("[摘要]")]
    assert summaries == [
        "[摘要] 前 77 条事件：角色对话 76 次，物理变化 0 次，玩家行动 0 次，NPC状态 0 次。"
    ]
    # reducer append-only：初始事件一条不少
    assert all(e in res["event_log"] for e in initial)
    # 总数 = 121 初始 + 6（state_apply 前各节点）+ 4（state_apply：玩家1+NPC2+摘要1）
    #        + 1（attribute_update 分支的属性事件）
    assert len(res["event_log"]) == 132


# ══════════════════════════════════════════════════════════════════════════
# reducer 重复累加聚焦测试（known-bug-candidate）
# ══════════════════════════════════════════════════════════════════════════

async def test_e2e_action_intents_reducer_duplication_single_npc():
    """known-bug-candidate：tick_speed_resolve 的输出经 operator.add 叠加到
    characters_all_decide 的输出上 → intent 重复；state_apply 因此对同一 NPC
    行动执行两次（move 幂等但事件与好感度类副作用会翻倍）。
    """
    routes = default_routes()
    state = make_base_state(
        characters={"npc2": make_char("npc2", "布鲁诺", {"x": 5, "y": 0, "z": 0}, ["沉稳"])},
        character_positions={"npc2": {"x": 5, "y": 0, "z": 0}},
        world_rules={"tick_speed": {"default": 2.0, "max_minutes": 2.0}},
    )
    llm, res = await _run(routes, state)
    assert [(i["character_id"], i["duration_minutes"]) for i in res["action_intents"]] == [
        ("npc2", 3.0),  # 原始
        ("npc2", 2.0),  # 截断副本
    ]
    assert res["event_log"].count("[NPC状态] 布鲁诺 移动到 {'x': 1.0, 'y': 0.0, 'z': 0.0}") == 2


# ══════════════════════════════════════════════════════════════════════════
# tick_speed 表达式（图级）
# ══════════════════════════════════════════════════════════════════════════

async def test_e2e_tick_expression_from_world_rules():
    routes = default_routes()
    state = make_base_state(world_rules={
        "tick_speed": {"default": 2.0,
                       "rule": "if(player_action.action_type = observe, 4.0; default)"},
    })
    llm, res = await _run(routes, state)
    assert res["tick_duration_minutes"] == pytest.approx(4.0)
    assert "[时间] 本 tick 推进 4.0 分钟" in res["event_log"]
    assert res["game_time"] == {"hour": 8, "minute": 4}


# ══════════════════════════════════════════════════════════════════════════
# g. action_continuation 长行动延续与打断
# ══════════════════════════════════════════════════════════════════════════

def _continuation():
    return {
        "raw_input": "持续搜查",
        "interpreted_intent": "持续搜查木箱",
        "action_type": "interact",
        "action_description": "持续搜查木箱",
        "target_object_id": "crate",
        "feasibility": "allowed",
        "duration_minutes": 10.0,
        "continue_until": "done",
    }


async def test_e2e_c_command_continues_and_tick_truncates_with_remainder():
    """/c 延续长行动：意图节点复用 continuation；tick_speed 截断并把剩余时长
    写回 action_continuation（每回合推进 tick 跨度）。
    """
    routes = default_routes()
    state = make_base_state(
        player_input="/c",
        action_continuation=_continuation(),
        characters={},
        character_positions={},
        world_rules={"tick_speed": {"default": 2.0, "max_minutes": 2.0}},
    )
    llm, res = await _run(routes, state)
    assert "[系统] 继续长任务。" in res["event_log"]
    assert llm.call_count(M_INTENT) == 0  # /c 分支不调用 LLM
    assert res["player_action"]["duration_minutes"] == pytest.approx(2.0)
    cont = res["action_continuation"]
    assert cont is not None
    assert cont["duration_minutes"] == pytest.approx(8.0)
    assert cont["continue_until"] == "done"
    assert cont["action_description"] == "持续搜查木箱"
    assert res["player_percept"]["narrative"] == "叙事文本E2E"


async def test_e2e_stop_command_clears_continuation():
    routes = default_routes()
    state = make_base_state(
        player_input="/stop",
        action_continuation=_continuation(),
        characters={},
        character_positions={},
    )
    llm, res = await _run(routes, state)
    assert "[系统] 行动已终止。" in res["event_log"]
    # characterization：同 intent-failure 路径，tick_speed_resolve 把 None 重写为 {}
    assert res["player_action"] == {}
    assert res["action_continuation"] is None
    assert llm.call_count(M_INTENT) == 0
    assert not any("[玩家行动]" in e for e in res["event_log"])
    assert res["player_percept"]["narrative"] == "叙事文本E2E"  # 流水线继续


async def test_e2e_new_input_interrupts_continuation():
    routes = default_routes()
    state = make_base_state(player_input="换个事情做", action_continuation=_continuation())
    llm, res = await _run(routes, state)
    assert "[系统] 长任务已被新输入打断。" in res["event_log"]
    assert "[玩家意图] 环顾四周" in res["event_log"]
    assert res["action_continuation"] is None
    assert llm.call_count(M_INTENT) == 1


# ══════════════════════════════════════════════════════════════════════════
# 多回合（main.py 模式：每回合新 thread_id + reset_tick_transients）
# ══════════════════════════════════════════════════════════════════════════

async def test_e2e_multi_turn_narrative_history_and_event_log_continuity():
    """两个连续回合刻画：
    - narrative_history（reducer）每回合追加一条，跨回合累积；
    - event_log 通过状态传递保持连续（每回合新 thread_id，无检查点累加）；
    - 第 2 回合叙事 prompt 注入第 1 回合叙事（前回合叙事上下文）。
    """
    routes = default_routes()
    llm = FakeLLM(routes)
    graph = build_test_graph(llm)

    state1 = make_base_state(player_input="第一回合输入")
    res1 = await graph.ainvoke(state1, {"configurable": {"thread_id": new_thread_id()}})
    assert res1["tick"] == 1
    assert len(res1["narrative_history"]) == 1

    state2 = reset_tick_transients(res1, "第二回合输入")
    res2 = await graph.ainvoke(state2, {"configurable": {"thread_id": new_thread_id()}})

    assert res2["tick"] == 2
    # narrative_history reducer：初始(1 条) + 第 2 回合(1 条)
    assert len(res2["narrative_history"]) == 2
    assert [h["tick"] for h in res2["narrative_history"]] == [1, 2]
    assert res2["narrative_history"][1]["narrative"] == "叙事文本E2E"
    # 第 2 回合叙事 prompt 携带第 1 回合叙事作为连贯上下文
    prompt2 = llm.user_prompt_of(M_NARRATIVE, call_index=1)
    assert "前回合叙事" in prompt2
    assert "叙事文本E2E" in prompt2
    # event_log 连续性：第 1 回合事件仍在（经状态传递）
    assert "[玩家意图] 环顾四周" in res2["event_log"]
    assert res2["event_log"].count("[初始] 游戏开始") == 1
    # 瞬态字段重置后重新产出
    assert res2["player_input"] is None
    assert res2["player_percept"]["narrative"] == "叙事文本E2E"
    # 第 2 回合时间继续推进（1.0 分钟 × 2）
    assert res2["game_time"] == {"hour": 8, "minute": 2}
