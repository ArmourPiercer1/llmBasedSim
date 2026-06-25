from src.agents.init import init_file_to_game_state, load_init_file
from src.game.rules import check_action_feasibility


def _test_state():
    state = init_file_to_game_state(load_init_file("config/init_test.yaml"))
    return state, state["player"], state["objects"], state["locations"]


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
