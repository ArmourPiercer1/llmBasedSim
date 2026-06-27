import pytest

from src.game.condition_eval import ConditionEvalError, evaluate_condition


def _context():
    return {
        "player": {
            "attributes": {
                "sanity": {"value": 35},
                "resolve": {"value": 70},
            },
            "physical_profile": {
                "strength": 2.0,
                "body_width_cm": 60,
            },
            "capabilities": {
                "skill_levels": {"lockpicking": 0.4},
            },
        },
        "target": {
            "properties": {
                "weight_kg": 120,
                "lock_difficulty": 0.8,
                "width_cm": 80,
            },
        },
        "a": 3,
    }


def test_simple_comparison_returns_blocked():
    outcome = evaluate_condition("if(player.sanity < 40, blocked; allowed)", _context())

    assert outcome.feasibility == "blocked"
    assert outcome.probability is None


def test_ifelse_chain_returns_uncertain_with_probability():
    outcome = evaluate_condition("if(a < 1, blocked; a < 5, uncertain:0.4; allowed)", _context())

    assert outcome.feasibility == "uncertain"
    assert outcome.probability == 0.4


def test_arithmetic_and_target_weight_alias():
    outcome = evaluate_condition("if(player.strength * 50 >= target.weight, allowed; blocked)", _context())

    assert outcome.feasibility == "blocked"


def test_parentheses_and_precedence():
    outcome = evaluate_condition("if((player.strength + 0.5) * 50 >= target.weight, allowed; blocked)", _context())

    assert outcome.feasibility == "allowed"


def test_min_max_functions():
    outcome = evaluate_condition("if(min(player.sanity, player.resolve) < max(20, 30), blocked; allowed)", _context())

    assert outcome.feasibility == "allowed"


def test_skill_level_lookup():
    outcome = evaluate_condition("if(player.lockpicking < target.lock_difficulty, uncertain:0.25; allowed)", _context())

    assert outcome.feasibility == "uncertain"
    assert outcome.probability == 0.25


def test_missing_variable_raises():
    with pytest.raises(ConditionEvalError):
        evaluate_condition("if(player.missing < 1, blocked; allowed)", _context())


def test_division_by_zero_raises():
    with pytest.raises(ConditionEvalError):
        evaluate_condition("if(player.sanity / 0 < 1, blocked; allowed)", _context())


def test_invalid_syntax_raises():
    with pytest.raises(ConditionEvalError):
        evaluate_condition("player.sanity < 30", _context())


def test_invalid_outcome_raises():
    with pytest.raises(ConditionEvalError):
        evaluate_condition("if(player.sanity < 40, impossible; allowed)", _context())


def test_uncertain_without_probability_defaults_to_half():
    outcome = evaluate_condition("if(player.sanity < 40, uncertain; allowed)", _context())

    assert outcome.feasibility == "uncertain"
    assert outcome.probability == 0.5
