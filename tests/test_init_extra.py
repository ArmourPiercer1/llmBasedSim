from src.agents.init import (
    init_file_to_game_state,
    load_init_file,
    infer_player_start_position,
)


class TestInferPlayerStartPosition:
    def test_returns_explicit_position_when_set(self):
        pos, warnings = infer_player_start_position(
            {"position": {"x": 10, "y": 0, "z": 5}},
            {}, {}, {},
        )
        assert pos == {"x": 10.0, "y": 0.0, "z": 5.0}
        assert warnings == []

    def test_uses_starting_position_key(self):
        pos, _ = infer_player_start_position(
            {"starting_position": {"x": 7, "y": 1, "z": 3}},
            {}, {}, {},
        )
        assert pos == {"x": 7.0, "y": 1.0, "z": 3.0}

    def test_falls_back_to_origin_when_no_position(self):
        pos, warnings = infer_player_start_position({}, {}, {}, {})
        assert pos == {"x": 0.0, "y": 0.0, "z": 0.0}
        assert len(warnings) == 1

    def test_near_starting_location_object(self):
        locations = {
            "start": {
                "id": "start",
                "objects": ["nearby_obj"],
            }
        }
        objects = {
            "nearby_obj": {
                "id": "nearby_obj",
                "position": {"x": 5, "y": 0, "z": 5},
            }
        }
        pos, warnings = infer_player_start_position(
            {}, locations, objects, {},
            starting_location_id="start",
        )
        assert pos["x"] > 5.0  # offset applied

    def test_falls_back_to_first_character_position(self):
        char_positions = {"npc1": {"x": 20, "y": 0, "z": 30}}
        pos, warnings = infer_player_start_position(
            {}, {}, {}, char_positions,
        )
        assert pos["x"] < 20.0  # offset dx=-1.0
        assert warnings == []


class TestInitFileEdgeCases:
    def test_connections_list_normalized_to_dict(self):
        state = init_file_to_game_state({
            "world": {
                "name": "Test",
                "description": "Test",
                "locations": [
                    {"id": "room1", "name": "Room1", "description": "A room",
                     "connections": ["room2", "room3"]},
                ],
                "objects": [],
            },
            "player": {"name": "Test"},
            "characters": [],
            "starting_scene_description": "Start",
        })
        loc = state["locations"]["room1"]
        assert isinstance(loc["connections"], dict)
        assert loc["connections"]["room2"] == "room2"

    def test_game_time_set_from_raw(self):
        state = init_file_to_game_state({
            "world": {"name": "T", "description": "T", "locations": [], "objects": []},
            "player": {"name": "T"},
            "characters": [],
            "starting_scene_description": "S",
            "game_time": {"hour": 8, "minute": 30},
            "ticks_per_game_minute": 1.0,
        })
        assert state["game_time"] == {"hour": 8, "minute": 30}
        assert state["ticks_per_game_minute"] == 1.0

    def test_character_id_resolved_from_both_keys(self):
        state = init_file_to_game_state({
            "world": {"name": "T", "description": "T", "locations": [], "objects": []},
            "player": {"name": "T"},
            "characters": [
                {"id": "ch1", "name": "Bob", "personality": {"traits": ["brave"]},
                 "position": {"x": 1, "y": 0, "z": 1}},
            ],
            "starting_scene_description": "S",
        })
        assert "ch1" in state["characters"]
        assert state["characters"]["ch1"]["character_id"] == "ch1"
