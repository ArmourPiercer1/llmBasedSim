from src.prompts.loader import PromptLoader


class TestPromptLoader:
    """Test that all templates can be loaded and rendered with the correct context variables.

    Variable names must match what the game graph passes at render time (see src/graph/game_graph.py).
    """

    def test_init_system_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("init_system.j2", {})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_player_intent_system_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("player_intent_system.j2", {})
        assert len(result) > 0

    def test_player_intent_user_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("player_intent_user.j2", {
            "player_input": "测试输入",
            "player": {"name": "测试"},
            "characters": {},
            "objects": {},
            "locations": {},
            "environment": {"time_of_day": "清晨", "weather": "晴朗", "temperature_c": 20.0},
            "recent_events": [],
        })
        assert "测试输入" in result

    def test_player_action_resolve_system_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("player_action_resolve_system.j2", {})
        assert len(result) > 0

    def test_player_action_resolve_user_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("player_action_resolve_user.j2", {
            "player_action": {},
            "player": {"capabilities": {}, "physical_profile": {}},
            "objects": {},
            "locations": {},
            "environment": {},
            "rule_result": None,
        })
        assert isinstance(result, str)

    def test_character_system_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("character_system.j2", {
            "name": "测试角色",
            "personality": {
                "traits": ["勇敢"],
                "motivations": ["冒险"],
                "speech_style": "随意",
                "background": "无",
            },
            "speech_examples": [],
            "conversation_target": None,
            "last_spoken_to": None,
            "relationships": {},
            "memory": [],
        })
        assert "测试角色" in result

    def test_character_user_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("character_user.j2", {
            "environment": {"time_of_day": "清晨", "weather": "晴朗", "temperature_c": 20.0},
            "current_location": {"name": "广场", "description": "一个开阔的广场", "ambient_light": "明亮", "ambient_sound": "安静"},
            "nearby_objects": [],
            "nearby_chars": [],
            "char_position": {"x": 0, "y": 0, "z": 0},
            "inventory": [],
            "player_action": None,
        })
        assert isinstance(result, str)

    def test_physics_system_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("physics_system.j2", {})
        assert len(result) > 0

    def test_physics_user_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("physics_user.j2", {
            "environment": {"time_of_day": "清晨", "weather": "晴朗", "temperature_c": 20.0},
            "world_context": "测试场景",
            "player_action_summary": "玩家走向门口",
            "npc_actions_summary": "守卫注视着玩家",
        })
        assert isinstance(result, str)

    def test_sensory_system_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("sensory_system.j2", {
            "player_name": "测试",
            "player_persona": "",
            "player_capabilities": {
                "sight_range_m": 50.0,
                "hearing_range_m": 100.0,
                "field_of_view_degrees": 120.0,
                "special_senses": [],
            },
            "player_position": {"x": 0, "y": 0, "z": 0},
            "self_action_summary": "你走向门口",
        })
        assert isinstance(result, str)

    def test_sensory_user_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("sensory_user.j2", {
            "self_action_summary": "你观察四周",
            "environment": {"time_of_day": "清晨", "weather": "晴朗", "temperature_c": 20.0},
            "player_position": {"x": 0, "y": 0, "z": 0},
            "current_location": {"name": "广场", "description": "开阔广场", "ambient_light": "明亮", "ambient_sound": "安静"},
            "visible_objects": [],
            "visible_characters": {},
            "visible_exits": [],
            "recent_events": [],
            "event_log": [],
            "character_positions": {},
        })
        assert isinstance(result, str)
