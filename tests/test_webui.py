import pytest

from src.web.app import WebUIError, attribute_items, save_game, sense_items, snapshot


def _web_state():
    return {
        "tick": 3,
        "max_ticks": 10,
        "game_phase": "running",
        "world_name": "测试世界",
        "world_description": "黑暗中的测试场景",
        "environment": {"time_of_day": "夜晚", "weather": "雪", "temperature_c": -5},
        "player": {
            "name": "艾琳",
            "attributes": {
                "stamina": {"name": "体力", "value": 70, "max": 100},
                "secret": {"name": "秘密", "value": 1, "hidden": True},
            },
        },
        "characters": {
            "npc_1": {"name": "雷恩", "current_action": "注视着石桥"},
        },
        "player_percept": {
            "narrative": "雪落在石桥上。",
            "summary": "你看到石桥。",
            "senses": [
                {"sense": "sight", "description": "石桥横跨深渊", "confidence": 1.0},
                {"sense": "sound", "description": "寒风呼啸", "confidence": 0.7},
                {"sense": "touch", "description": "扶手冰冷", "confidence": 1.0},
            ],
            "self_action_summary": "你踏上石桥。",
            "hidden_event_count": 1,
        },
        "event_log": ["a", "b"],
    }


def test_snapshot_exposes_webui_display_fields():
    data = snapshot(_web_state())

    assert data["started"] is True
    assert data["world_name"] == "测试世界"
    assert data["narrative"] == "雪落在石桥上。"
    assert data["player"]["name"] == "艾琳"
    assert data["player_attributes"] == [{"key": "stamina", "name": "体力", "value": 70, "max": 100, "unit": "", "hidden": False}]
    assert data["all_player_attributes"][1]["name"] == "秘密"
    assert data["npc_dynamics"] == [{"id": "npc_1", "name": "雷恩", "action": "注视着石桥"}]


def test_attribute_items_hide_hidden_by_default():
    attrs = _web_state()["player"]["attributes"]

    visible = attribute_items(attrs, include_hidden=False)
    all_items = attribute_items(attrs, include_hidden=True)

    assert [item["key"] for item in visible] == ["stamina"]
    assert [item["key"] for item in all_items] == ["stamina", "secret"]


def test_sense_items_filters_multiple_types_and_marks_uncertain():
    state = _web_state()

    assert sense_items(state, {"sight"}) == ["石桥横跨深渊"]
    assert sense_items(state, {"sound"}) == ["寒风呼啸（不太确定）"]
    assert sense_items(state, {"touch", "smell"}) == ["扶手冰冷"]


def test_save_game_rejects_invalid_save_name():
    with pytest.raises(WebUIError):
        save_game(_web_state(), "../bad")
