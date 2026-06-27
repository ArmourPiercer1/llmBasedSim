from src.agents.init import init_file_to_game_state
from src.game.state_apply import apply_npc_actions, compact_event_log
from src.graph.game_state import advance_game_time, time_of_day_from_hour


def _test_state():
    return init_file_to_game_state({
        "world": {
            "name": "测试世界",
            "locations": [],
            "objects": [],
        },
        "player": {"name": "艾琳"},
        "characters": [
            {
                "id": "victoria",
                "name": "艾琳",
                "relationships": {},
            },
            {
                "id": "knight_rain",
                "name": "雷恩",
                "starting_position": {"x": 0, "y": 0, "z": 0},
                "relationships": {"victoria": 0.0},
            },
        ],
        "starting_scene_description": "开场",
    })


def test_npc_move_updates_position():
    state = _test_state()
    chars = state["characters"]
    positions = dict(state["character_positions"])
    intents = [{
        "character_id": "knight_rain",
        "action_type": "move",
        "action_description": "快步走向艾琳",
        "target_position": {"x": 5, "y": 0, "z": 1},
    }]

    _, new_positions, _, events = apply_npc_actions(chars, positions, intents, state["objects"])
    assert new_positions["knight_rain"] == {"x": 5.0, "y": 0.0, "z": 1.0}
    assert any("移动到" in e for e in events)


def test_npc_speak_sets_conversation_target():
    state = _test_state()
    chars = state["characters"]
    positions = state["character_positions"]
    intents = [{
        "character_id": "knight_rain",
        "action_type": "speak",
        "action_description": "向艾琳打招呼",
        "target_character_id": "victoria",
        "emotion": "友善",
    }]

    new_chars, _, _, _ = apply_npc_actions(chars, positions, intents, state["objects"])
    assert new_chars["knight_rain"]["conversation_target"] == "victoria"
    assert new_chars["victoria"]["conversation_target"] == "knight_rain"


def test_npc_other_action_clears_conversation():
    state = _test_state()
    chars = state["characters"]
    chars["knight_rain"]["conversation_target"] = "victoria"
    positions = state["character_positions"]
    intents = [{
        "character_id": "knight_rain",
        "action_type": "observe",
        "action_description": "环顾四周",
    }]

    new_chars, _, _, _ = apply_npc_actions(chars, positions, intents, state["objects"])
    assert "conversation_target" not in new_chars["knight_rain"]


def test_relationship_increases_on_friendly_speech():
    state = _test_state()
    chars = state["characters"]
    positions = state["character_positions"]
    initial = chars["knight_rain"].get("relationships", {}).get("victoria", 0.0)
    intents = [{
        "character_id": "knight_rain",
        "action_type": "speak",
        "action_description": "温柔地对艾琳说话",
        "target_character_id": "victoria",
        "emotion": "友好",
    }]

    new_chars, _, _, _ = apply_npc_actions(chars, positions, intents, state["objects"])
    updated = new_chars["knight_rain"]["relationships"]["victoria"]
    assert updated > initial, f"expected {updated} > {initial}"


def test_advance_game_time():
    result = advance_game_time({"hour": 23, "minute": 59}, 0.2)
    assert result["hour"] == 0
    assert result["minute"] == 4  # 1/0.2 = 5 min per tick


def test_time_of_day_from_hour():
    assert time_of_day_from_hour(6) == "清晨"
    assert time_of_day_from_hour(10) == "上午"
    assert time_of_day_from_hour(13) == "中午"
    assert time_of_day_from_hour(16) == "下午"
    assert time_of_day_from_hour(19) == "傍晚"
    assert time_of_day_from_hour(22) == "夜晚"
    assert time_of_day_from_hour(3) == "深夜"


def test_event_compaction():
    events = [f"[角色] event {i}" for i in range(80)] + [
        "[系统] 重要事件",
        "[检定成功] 开锁",
    ] + [f"[物理] event {i}" for i in range(50)]

    result = compact_event_log(events, max_events=100, keep_recent=50)
    assert len(result) < len(events)
    assert any("[摘要]" in e for e in result)
    assert "[系统] 重要事件" in result
