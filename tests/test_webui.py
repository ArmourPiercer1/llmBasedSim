import pytest

from src.web.app import GameSession, StartRequest, WebTurnStatus, WebUIError, _safe_init_file_path, attribute_items, list_init_files, save_game, sense_items, snapshot


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


def test_list_init_files_includes_public_start_files():
    data = list_init_files()
    paths = {item["path"] for item in data["init_files"]}

    assert "public_start/whisperheads.yaml" in paths
    assert "public_start/murder.yaml" in paths


def test_game_session_start_only_returns_opening_scene_without_building_graph():
    session = GameSession()

    data = session.start(StartRequest(init_file="public_start/whisperheads.yaml"))

    assert data["started"] is True
    assert data["tick"] == 0
    assert data["world_name"] == "耳语山"
    assert "寒风如刀" in data["narrative"]
    assert session.graph is None
    assert session.busy is False


def test_safe_init_file_path_allows_absolute_yaml_outside_project(tmp_path):
    path = tmp_path / "custom_start.yaml"
    path.write_text("world:\n  name: 自定义\n", encoding="utf-8")

    assert _safe_init_file_path(str(path)) == path.resolve()


def test_safe_init_file_path_rejects_non_yaml(tmp_path):
    path = tmp_path / "custom_start.txt"
    path.write_text("world", encoding="utf-8")

    with pytest.raises(WebUIError):
        _safe_init_file_path(str(path))


def test_web_turn_status_snapshots_step_and_sub_progress():
    status = WebTurnStatus()
    status.update("NPC 正在思考中...", sub_count=2, sub_total=5)

    assert status.snapshot(busy=True) == {
        "busy": True,
        "step": "NPC 正在思考中...",
        "sub_count": 2,
        "sub_total": 5,
    }

    status.reset()
    assert status.snapshot(busy=False)["step"] == "等待中..."
