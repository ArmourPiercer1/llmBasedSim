from src.agents.init import init_file_to_game_state, load_init_file
from src.game.rules import check_action_feasibility, _text_matches_rule


def _test_state():
    state = init_file_to_game_state(load_init_file("config/init_test.yaml"))
    return state, state["player"], state["objects"], state["locations"]


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
