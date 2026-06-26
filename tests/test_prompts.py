from src.prompts.loader import (
    ATTRIBUTE_DEFAULT_REFERENCES,
    ATTRIBUTE_DEFAULT_RULES,
    PHYSICS_DEFAULT_RULES,
    PromptLoader,
    build_rules_context,
)


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
            "player": {"name": "测试", "attributes": {"stamina": {"name": "体力", "value": 80, "max": 100}}},
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
            "player": {"capabilities": {}, "physical_profile": {}, "attributes": {}},
            "capabilities": {},
            "physical_profile": {},
            "attributes": {},
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
            "attributes": {"mood": {"name": "心情", "value": 10, "max": 100}},
            "memory": [],
        })
        assert "测试角色" in result

    def test_character_user_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("character_user.j2", {
            "environment": {"time_of_day": "清晨", "weather": "晴朗", "temperature_c": 20.0},
            "current_location": {"name": "广场", "description": "一个开阔的广场", "ambient_light": "明亮", "ambient_sound": "安静"},
            "nearby_objects": [],
            "nearby_chars": [{
                "character_id": "npc",
                "name": "NPC",
                "personality": {"background": "测试背景"},
                "position": {"x": 1, "y": 0, "z": 0},
                "current_action": "等待",
                "attributes": {"mood": {"name": "心情", "value": 5, "max": 100}},
            }],
            "char_position": {"x": 0, "y": 0, "z": 0},
            "inventory": [],
            "player_action": None,
        })
        assert isinstance(result, str)

    def test_physics_system_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("physics_system.j2", {
            "rules": build_rules_context(PHYSICS_DEFAULT_RULES, None),
        })
        assert len(result) > 0
        assert "重力" in result

    def test_physics_user_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("physics_user.j2", {
            "environment": {"time_of_day": "清晨", "weather": "晴朗", "temperature_c": 20.0},
            "world_context": "测试场景",
            "player_action_summary": "玩家走向门口",
            "npc_actions_summary": "守卫注视着玩家",
        })
        assert isinstance(result, str)

    def test_attribute_update_system_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("attribute_update_system.j2", {
            "rules": build_rules_context(
                ATTRIBUTE_DEFAULT_RULES,
                None,
                extra_sections=[("常见参考", ATTRIBUTE_DEFAULT_REFERENCES)],
            ),
        })
        assert len(result) > 0
        assert "自然恢复" in result

    def test_attribute_update_user_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("attribute_update_user.j2", {
            "attribute_summary": {
                "player": {"entity_id": "player_1", "name": "测试", "attributes": {"stamina": {"name": "体力", "value": 80}}},
                "characters": {},
            },
            "player_action": {"action_type": "move", "action_description": "跑步"},
            "action_intents": [],
            "physics_outcomes": [],
            "recent_events": [],
            "environment": {"time_of_day": "清晨"},
            "game_time": {"hour": 8, "minute": 0},
        })
        assert "体力" in result

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
            "player_attributes": {"stamina": {"name": "体力", "value": 80, "max": 100}},
            "current_location": {"name": "广场", "description": "开阔广场", "ambient_light": "明亮", "ambient_sound": "安静"},
            "visible_objects": [],
            "visible_characters": {},
            "visible_exits": [],
            "recent_events": [],
            "event_log": [],
            "character_positions": {},
        })
        assert isinstance(result, str)

    def test_narrative_system_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("narrative_system.j2", {
            "style_description": "哥特式恐怖风格",
            "style_example": "寒风如刀...",
        })
        assert isinstance(result, str)
        assert "哥特式恐怖风格" in result
        assert "寒风如刀" in result

    def test_narrative_system_renders_with_defaults(self):
        loader = PromptLoader("prompts")
        result = loader.render("narrative_system.j2", {
            "style_description": "",
            "style_example": "",
        })
        assert isinstance(result, str)
        assert "默认文风" in result

    def test_narrative_user_renders(self):
        loader = PromptLoader("prompts")
        result = loader.render("narrative_user.j2", {
            "player_name": "洛肯",
            "player_persona": "阿斯塔特连长",
            "time_of_day": "清晨",
            "weather": "严寒",
            "temperature_c": -15.0,
            "game_time": {"hour": 5, "minute": 15},
            "self_action_summary": "你走向石桥",
            "senses": [
                {"sense": "sight", "description": "石桥横跨深渊", "confidence": 1.0},
                {"sense": "sound", "description": "寒风呼啸", "confidence": 0.8},
            ],
            "summary": "前方是天然石桥",
            "player_attributes": {"stamina": {"name": "体力", "value": 95, "max": 100}},
        })
        assert isinstance(result, str)
        assert "洛肯" in result
        assert "石桥横跨深渊" in result


class TestBuildRulesContext:
    def test_returns_default_rules_when_no_config(self):
        result = build_rules_context(["1. 规则A", "2. 规则B"], None)
        assert "默认规则" in result
        assert "规则A" in result
        assert "规则B" in result
        assert "自定义规则" not in result

    def test_disables_specified_indices(self):
        result = build_rules_context(["1. 规则A", "2. 规则B", "3. 规则C"], {"disable": [2]})
        assert "规则A" in result
        assert "规则B" not in result
        assert "规则C" in result

    def test_appends_custom_rules(self):
        result = build_rules_context(["1. 规则A"], {"append": ["附加规则X"]})
        assert "规则A" in result
        assert "自定义规则" in result
        assert "2. 附加规则X" in result

    def test_combined_disable_and_append(self):
        result = build_rules_context(
            ["1. 规则A", "2. 规则B", "3. 规则C"],
            {"disable": [1, 3], "append": ["新增规则"]},
        )
        assert "规则A" not in result
        assert "规则B" in result
        assert "规则C" not in result
        assert "自定义规则" in result
        assert "新增规则" in result

    def test_preserves_custom_rule_number_prefix(self):
        result = build_rules_context(["1. X"], {"append": ["5. 已有编号的规则"]})
        assert "5. 已有编号的规则" in result

    def test_extra_sections_included(self):
        result = build_rules_context(
            ["1. 规则A"],
            None,
            extra_sections=[("常见参考", ["- 参考项1", "- 参考项2"])],
        )
        assert "常见参考" in result
        assert "参考项1" in result
        assert "规则A" in result

    def test_empty_config_handled(self):
        result = build_rules_context([], {"disable": [1], "append": ["X"]})
        assert "默认规则" not in result
        assert "X" in result

    def test_physics_default_rules_has_expected_count(self):
        assert len(PHYSICS_DEFAULT_RULES) == 10

    def test_attribute_default_rules_has_expected_count(self):
        assert len(ATTRIBUTE_DEFAULT_RULES) == 7
