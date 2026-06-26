from src.agents.init import config_loader_to_game_state, init_file_to_game_state, load_init_file
from src.config.loader import ConfigLoader
from src.graph.game_state import normalize_state, strip_transient_state


def test_init_file_loads_full_test_scene():
    state = init_file_to_game_state(load_init_file("config/init_test.yaml"))

    assert state["world_name"] == "蔷薇庄园"
    assert len(state["locations"]) == 7
    assert len(state["objects"]) == 8
    assert len(state["characters"]) == 4
    assert state["player"]["position"] is not None
    assert "stamina" in state["player"]["attributes"]
    assert "composure" in state["characters"]["knight_rain"]["attributes"]
    assert len(state["player"]["subconscious_rules"]) == 4


def test_split_config_loads_state_with_position():
    state = config_loader_to_game_state(ConfigLoader("config"))

    assert state["world_name"]
    assert state["player"]["position"] is not None
    assert state["characters"]
    assert "stamina" in state["player"]["attributes"]
    assert "mood" in state["characters"]["alice"]["attributes"]


def test_strip_transient_state_round_trip_preserves_attributes():
    state = init_file_to_game_state(load_init_file("config/init_test.yaml"))
    state["player_input"] = "test"
    state["player_action"] = {"raw_input": "test"}
    state["action_intents"] = [{"character_id": "x"}]
    state["physics_outcomes"] = [{"outcome_type": "sound"}]
    state["player_percept"] = {"summary": "test"}

    saved = strip_transient_state(state)
    for key in ("player_input", "player_action", "action_intents", "physics_outcomes"):
        assert key not in saved
    assert saved["player_percept"] == {"summary": "test"}

    loaded = normalize_state(saved)
    assert loaded["world_name"] == state["world_name"]
    assert loaded["player"]["attributes"]["stamina"]["value"] == 70
    assert loaded["characters"]["knight_rain"]["attributes"]["composure"]["value"] == 40
    assert loaded["player_input"] is None
    assert loaded["player_action"] is None
    assert loaded["action_intents"] == []


def test_init_file_preserves_world_rules():
    state = init_file_to_game_state(load_init_file("config/init_test.yaml"))
    assert state["world_rules"] == {}


def test_world_rules_survive_save_load_round_trip():
    from src.agents.init import init_file_to_game_state
    raw = {
        "world": {"name": "T", "description": "T", "locations": [], "objects": []},
        "player": {"name": "T"},
        "characters": [],
        "starting_scene_description": "S",
        "world_rules": {
            "physics": {"disable": [3, 8], "append": ["11. 自定义规则"]},
            "attribute": {"disable": [2]},
        },
    }
    state = init_file_to_game_state(raw)
    assert state["world_rules"]["physics"]["disable"] == [3, 8]
    assert state["world_rules"]["attribute"]["disable"] == [2]
    assert any("自定义规则" in r for r in state["world_rules"]["physics"]["append"])

    saved = strip_transient_state(state)
    reloaded = normalize_state(saved)
    assert reloaded["world_rules"]["physics"]["disable"] == [3, 8]
    assert reloaded["world_rules"]["attribute"]["disable"] == [2]


def test_narrative_style_survive_save_load_round_trip():
    from src.agents.init import init_file_to_game_state
    raw = {
        "world": {"name": "T", "description": "T", "locations": [], "objects": []},
        "player": {"name": "T"},
        "characters": [],
        "starting_scene_description": "S",
        "narrative_style": {
            "style_description": "哥特式军事科幻",
            "style_example": "寒风如刀...",
        },
    }
    state = init_file_to_game_state(raw)
    assert state["narrative_style"]["style_description"] == "哥特式军事科幻"
    assert state["narrative_style"]["style_example"] == "寒风如刀..."

    saved = strip_transient_state(state)
    reloaded = normalize_state(saved)
    assert reloaded["narrative_style"]["style_description"] == "哥特式军事科幻"
    assert reloaded["narrative_style"]["style_example"] == "寒风如刀..."

    # Default empty
    raw_no_style = {
        "world": {"name": "T", "description": "T", "locations": [], "objects": []},
        "player": {"name": "T"},
        "characters": [],
        "starting_scene_description": "S",
    }
    state2 = init_file_to_game_state(raw_no_style)
    assert state2["narrative_style"] == {}
