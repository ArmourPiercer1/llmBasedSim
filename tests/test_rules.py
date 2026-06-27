from src.game.rules import check_action_feasibility, _text_matches_rule


def _test_state():
    player = {
        "attributes": {
            "sanity": {"value": 35},
            "storm_tolerance": {"value": 45},
        },
        "physical_profile": {
            "strength": 0.4,
            "body_width_cm": 60.0,
        },
        "capabilities": {
            "blocked_common_actions": [],
            "allowed_extraordinary_actions": [],
            "skill_levels": {"lockpicking": 0.2},
        },
    }
    objects = {
        "banquet_table": {
            "id": "banquet_table",
            "name": "长餐桌",
            "properties": {"weight_kg": 120.0},
        },
        "study_lock": {
            "id": "study_lock",
            "name": "书房门锁",
            "properties": {"lock_difficulty": 0.8},
        },
    }
    locations = {
        "rose_garden": {
            "id": "rose_garden",
            "name": "玫瑰花园",
            "properties": {"width_cm": 80.0},
        }
    }
    return {}, player, objects, locations


# ── Existing tests ──

def test_strength_rule_blocks_heavy_table():
    _, player, objects, locations = _test_state()
    result = check_action_feasibility({
        "action_type": "interact",
        "action_description": "把长餐桌推到墙边",
        "target_object_id": "banquet_table",
    }, player, objects, locations)

    assert result is not None
    assert result["matched_rule"] == "strength_vs_weight"
    assert result["feasibility"] == "blocked"


def test_lock_rule_returns_uncertain_probability():
    _, player, objects, locations = _test_state()
    result = check_action_feasibility({
        "action_type": "interact",
        "action_description": "试着打开书房门锁",
        "target_object_id": "study_lock",
    }, player, objects, locations)

    assert result is not None
    assert result["matched_rule"] == "skill_vs_lock"
    assert result["feasibility"] == "uncertain"
    assert result["requires_roll"] is True
    assert 0 < result["success_probability"] < 1


def test_no_rule_returns_none():
    _, player, objects, locations = _test_state()
    result = check_action_feasibility({
        "action_type": "observe",
        "action_description": "观察吊灯",
    }, player, objects, locations)

    assert result is None


# ── Expanded tests ──

def test_body_width_blocks_fat_player_thin_passage():
    _, player, objects, locations = _test_state()
    player["physical_profile"]["body_width_cm"] = 100.0
    locations["rose_garden"]["properties"] = {"width_cm": 30.0}
    result = check_action_feasibility({
        "action_type": "move",
        "action_description": "穿过狭窄的玫瑰花园入口",
        "target_position": {"x": 7, "y": 0, "z": -7},
    }, player, objects, locations)

    assert result is not None
    assert result["matched_rule"] == "body_width_vs_passage"
    assert result["feasibility"] == "blocked"


def test_body_width_allows_thin_player_slim_passage():
    _, player, objects, locations = _test_state()
    player["physical_profile"]["body_width_cm"] = 30.0
    locations["rose_garden"]["properties"] = {"width_cm": 80.0}
    result = check_action_feasibility({
        "action_type": "move",
        "action_description": "穿过玫瑰花园",
    }, player, objects, locations)

    assert result is not None
    assert result["matched_rule"] == "body_width_vs_passage"
    assert result["feasibility"] == "allowed"


def test_extraordinary_action_allows_superhuman():
    state, player, objects, locations = _test_state()
    player["capabilities"]["allowed_extraordinary_actions"] = [
        "通晓庄园所有秘密通道和暗门的精确位置",
    ]
    result = check_action_feasibility({
        "action_type": "move",
        "action_description": "找到一个秘密通道并走进去",
    }, player, objects, locations)

    assert result is not None
    assert result["matched_rule"] == "extraordinary"
    assert result["feasibility"] == "allowed"


def test_blocked_common_action_blocks_player():
    state, player, objects, locations = _test_state()
    player["capabilities"]["blocked_common_actions"] = [
        "对任何人说出真诚的感谢或道歉",
    ]
    result = check_action_feasibility({
        "action_type": "speak",
        "action_description": "向对方真诚道歉",
        "speech_content": "对不起，是我错了",
    }, player, objects, locations)

    assert result is not None
    assert result["matched_rule"] == "blocked_common"
    assert result["feasibility"] == "blocked"


def test_skill_vs_lock_allows_high_skill():
    _, player, objects, locations = _test_state()
    player["capabilities"]["skill_levels"]["lockpicking"] = 0.9
    result = check_action_feasibility({
        "action_type": "interact",
        "action_description": "打开书房门锁",
        "target_object_id": "study_lock",
    }, player, objects, locations)

    assert result is not None
    assert result["matched_rule"] == "skill_vs_lock"
    assert result["feasibility"] == "allowed"


def test_strength_rule_uncertain_when_close():
    _, player, objects, locations = _test_state()
    player["physical_profile"]["strength"] = 0.5  # 25kg capacity
    result = check_action_feasibility({
        "action_type": "interact",
        "action_description": "把长餐桌推到墙边",
        "target_object_id": "banquet_table",           # 120kg
    }, player, objects, locations)

    assert result is not None
    assert result["matched_rule"] == "strength_vs_weight"
    assert result["feasibility"] == "blocked"
    # With strength 2.5, capacity=125kg which is > 120kg but < 180kg
    player["physical_profile"]["strength"] = 2.5
    result2 = check_action_feasibility({
        "action_type": "interact",
        "action_description": "把长餐桌推到墙边",
        "target_object_id": "banquet_table",
    }, player, objects, locations)
    assert result2 is not None
    assert result2["feasibility"] == "uncertain"
    assert result2["requires_roll"] is True


# ── Deterministic world rules ──

def test_world_rules_with_no_deterministic_key_are_noop():
    _, player, objects, locations = _test_state()
    result = check_action_feasibility({
        "action_type": "interact",
        "action_description": "把长餐桌推到墙边",
        "target_object_id": "banquet_table",
    }, player, objects, locations, {"physics": {"disable": [1]}})

    assert result is not None
    assert result["matched_rule"] == "strength_vs_weight"


def test_custom_regex_blocked_takes_priority_over_extraordinary():
    _, player, objects, locations = _test_state()
    player["capabilities"]["allowed_extraordinary_actions"] = ["集中精神"]
    world_rules = {
        "deterministic": {
            "append": [{
                "id": "warp_madness",
                "description": "亚空间低语干扰心智集中",
                "match_action": "集中精神",
                "feasibility": "blocked",
            }]
        }
    }

    result = check_action_feasibility({
        "action_type": "observe",
        "action_description": "集中精神分析低语",
    }, player, objects, locations, world_rules)

    assert result is not None
    assert result["matched_rule"] == "custom:warp_madness"
    assert result["feasibility"] == "blocked"


def test_custom_regex_allowed_takes_priority_over_blocked_common():
    _, player, objects, locations = _test_state()
    player["capabilities"]["blocked_common_actions"] = ["道歉"]
    world_rules = {
        "deterministic": {
            "append": [{
                "id": "honor_duel_exception",
                "description": "荣誉决斗允许正式致歉",
                "match_action": "道歉",
                "feasibility": "allowed",
            }]
        }
    }

    result = check_action_feasibility({
        "action_type": "speak",
        "action_description": "向对手道歉",
    }, player, objects, locations, world_rules)

    assert result is not None
    assert result["matched_rule"] == "custom:honor_duel_exception"
    assert result["feasibility"] == "allowed"


def test_custom_condition_blocks_action():
    _, player, objects, locations = _test_state()
    player["attributes"]["sanity"]["value"] = 15
    world_rules = {
        "deterministic": {
            "append": [{
                "id": "sanity_gate",
                "description": "精神崩溃时多数行动受限",
                "condition": "if(player.sanity < 20, blocked; allowed)",
            }]
        }
    }

    result = check_action_feasibility({
        "action_type": "observe",
        "action_description": "观察房间",
    }, player, objects, locations, world_rules)

    assert result is not None
    assert result["matched_rule"] == "custom:sanity_gate"
    assert result["feasibility"] == "blocked"


def test_custom_condition_returns_uncertain_probability():
    _, player, objects, locations = _test_state()
    world_rules = {
        "deterministic": {
            "append": [{
                "id": "sanity_gate",
                "description": "精神不稳时行动不确定",
                "condition": "if(player.sanity < 40, uncertain:0.3; allowed)",
            }]
        }
    }

    result = check_action_feasibility({
        "action_type": "observe",
        "action_description": "观察房间",
    }, player, objects, locations, world_rules)

    assert result is not None
    assert result["feasibility"] == "uncertain"
    assert result["success_probability"] == 0.3
    assert result["requires_roll"] is True


def test_custom_match_action_plus_condition_requires_both():
    _, player, objects, locations = _test_state()
    world_rules = {
        "deterministic": {
            "append": [{
                "id": "storm_heavy_lift",
                "description": "暴风中搬运重物",
                "match_action": "搬运|推动|抬起",
                "condition": "if(player.storm_tolerance < 50, blocked; allowed)",
            }]
        }
    }

    no_match = check_action_feasibility({
        "action_type": "observe",
        "action_description": "观察长餐桌",
        "target_object_id": "banquet_table",
    }, player, objects, locations, world_rules)
    match = check_action_feasibility({
        "action_type": "interact",
        "action_description": "推动长餐桌",
        "target_object_id": "banquet_table",
    }, player, objects, locations, world_rules)

    assert no_match is None
    assert match is not None
    assert match["matched_rule"] == "custom:storm_heavy_lift"
    assert match["feasibility"] == "blocked"


def test_disable_strength_rule():
    _, player, objects, locations = _test_state()
    result = check_action_feasibility({
        "action_type": "interact",
        "action_description": "把长餐桌推到墙边",
        "target_object_id": "banquet_table",
    }, player, objects, locations, {"deterministic": {"disable": [3]}})

    assert result is None


def test_disable_body_width_rule():
    _, player, objects, locations = _test_state()
    player["physical_profile"]["body_width_cm"] = 100.0
    locations["rose_garden"]["properties"] = {"width_cm": 30.0}
    result = check_action_feasibility({
        "action_type": "move",
        "action_description": "穿过玫瑰花园",
    }, player, objects, locations, {"deterministic": {"disable": [5]}})

    assert result is None


def test_invalid_regex_is_skipped_and_builtin_rules_continue():
    _, player, objects, locations = _test_state()
    result = check_action_feasibility({
        "action_type": "interact",
        "action_description": "把长餐桌推到墙边",
        "target_object_id": "banquet_table",
    }, player, objects, locations, {"deterministic": {"append": [{
        "id": "bad_regex",
        "description": "坏正则",
        "match_action": "[",
        "feasibility": "blocked",
    }]}})

    assert result is not None
    assert result["matched_rule"] == "strength_vs_weight"


def test_invalid_condition_is_skipped_and_builtin_rules_continue():
    _, player, objects, locations = _test_state()
    result = check_action_feasibility({
        "action_type": "interact",
        "action_description": "把长餐桌推到墙边",
        "target_object_id": "banquet_table",
    }, player, objects, locations, {"deterministic": {"append": [{
        "id": "bad_condition",
        "description": "坏条件",
        "condition": "if(player.missing < 1, blocked; allowed)",
    }]}})

    assert result is not None
    assert result["matched_rule"] == "strength_vs_weight"


def test_first_matching_custom_rule_wins():
    _, player, objects, locations = _test_state()
    world_rules = {"deterministic": {"append": [
        {"id": "first", "description": "第一条", "match_action": "观察", "feasibility": "blocked"},
        {"id": "second", "description": "第二条", "match_action": "观察", "feasibility": "allowed"},
    ]}}

    result = check_action_feasibility({
        "action_type": "observe",
        "action_description": "观察房间",
    }, player, objects, locations, world_rules)

    assert result is not None
    assert result["matched_rule"] == "custom:first"
    assert result["feasibility"] == "blocked"


class TestTextMatchesRule:
    def test_exact_match(self):
        assert _text_matches_rule("道歉", "道歉") is True

    def test_substring_match(self):
        assert _text_matches_rule("向对方真诚道歉", "道歉") is True

    def test_comma_separated_keywords(self):
        assert _text_matches_rule("我想开锁", "开锁，撬锁，门锁") is True

    def test_no_match(self):
        assert _text_matches_rule("走路", "开锁") is False

    def test_empty_inputs(self):
        assert _text_matches_rule("", "rule") is False
        assert _text_matches_rule("text", "") is False
