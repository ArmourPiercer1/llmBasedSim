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


# ── boolean logic ──


def _ctx_with_lists():
    return {
        "player": {
            "attributes": {
                "sanity": {"value": 35},
                "resolve": {"value": 70},
                "flags": {"value": ["alert", "danger"]},
                "tags": {"value": ["safe", "calm"]},
                "inventory": {"value": ["a", "b", "c"]},
                "stage": {"value": "active"},
            },
            "physical_profile": {
                "strength": 2.0,
                "body_width_cm": 60,
            },
            "capabilities": {
                "skill_levels": {"lockpicking": 0.4},
            },
            "status_effects": {"fighting": True},
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


def test_and_operator():
    outcome = evaluate_condition(
        "if(player.sanity < 40 and player.resolve > 60, blocked; allowed)", _context()
    )
    assert outcome.feasibility == "blocked"


def test_and_operator_false():
    outcome = evaluate_condition(
        "if(player.sanity < 40 and player.resolve < 60, blocked; allowed)", _context()
    )
    assert outcome.feasibility == "allowed"


def test_or_operator():
    outcome = evaluate_condition(
        "if(a < 1 or a > 2, blocked; allowed)", _context()
    )
    assert outcome.feasibility == "blocked"


def test_not_operator():
    outcome = evaluate_condition(
        "if(not (player.sanity > 80), blocked; allowed)", _context()
    )
    assert outcome.feasibility == "blocked"


def test_compound_boolean():
    outcome = evaluate_condition(
        "if((a < 1 or a > 2) and player.resolve > 60, blocked; allowed)", _context()
    )
    assert outcome.feasibility == "blocked"


# ── set operations ──


def test_in_operator():
    outcome = evaluate_condition(
        'if("alert" in player.flags, blocked; allowed)', _ctx_with_lists()
    )
    assert outcome.feasibility == "blocked"


def test_in_operator_false():
    outcome = evaluate_condition(
        'if("boss" in player.flags, blocked; allowed)', _ctx_with_lists()
    )
    assert outcome.feasibility == "allowed"


def test_not_in_operator():
    outcome = evaluate_condition(
        'if("boss" not in player.flags, blocked; allowed)', _ctx_with_lists()
    )
    assert outcome.feasibility == "blocked"


def test_subset_operator():
    outcome = evaluate_condition(
        "if(player.tags subset player.flags, blocked; allowed)", _ctx_with_lists()
    )
    # flags=["alert","danger"], tags=["safe","calm"] — tags is not subset of flags
    assert outcome.feasibility == "allowed"


def test_subset_operator_true():
    ctx = {
        "player": {"attributes": {
            "required": {"value": ["a"]},
            "inventory": {"value": ["a", "b", "c"]},
        }},
    }
    outcome = evaluate_condition(
        "if(player.required subset player.inventory, blocked; allowed)", ctx
    )
    assert outcome.feasibility == "blocked"


def test_intersects_operator():
    # flags=["alert","danger"], tags=["safe","calm"] → no intersection
    outcome = evaluate_condition(
        "if(player.flags intersects player.tags, blocked; allowed)", _ctx_with_lists()
    )
    assert outcome.feasibility == "allowed"


def test_intersects_operator_true():
    outcome = evaluate_condition(
        "if(player.flags intersects player.flags, blocked; allowed)", _ctx_with_lists()
    )
    assert outcome.feasibility == "blocked"


def test_disjoint_operator():
    # tags=["safe","calm"], flags=["alert","danger"] → disjoint
    outcome = evaluate_condition(
        "if(player.tags disjoint player.flags, blocked; allowed)", _ctx_with_lists()
    )
    assert outcome.feasibility == "blocked"


def test_contains_operator():
    ctx = {
        "player": {"status_effects": {"fighting": True}},
    }
    outcome = evaluate_condition(
        "if(player.status_effects contains fighting, blocked; allowed)", ctx
    )
    assert outcome.feasibility == "blocked"


def test_len_function():
    outcome = evaluate_condition(
        "if(len(player.flags) > 1, blocked; allowed)", _ctx_with_lists()
    )
    assert outcome.feasibility == "blocked"


# ── string comparison ──


def test_string_comparison_equals():
    outcome = evaluate_condition(
        'if(player.stage = "active", blocked; allowed)', _ctx_with_lists()
    )
    assert outcome.feasibility == "blocked"


def test_string_comparison_not_equals():
    outcome = evaluate_condition(
        'if(player.stage != "latent", blocked; allowed)', _ctx_with_lists()
    )
    assert outcome.feasibility == "blocked"


# ── nested if ──


def test_nested_if_as_branch_value():
    outcome = evaluate_condition(
        "if(a < 1, if(player.sanity < 40, blocked; uncertain:0.3); allowed)", _context()
    )
    assert outcome.feasibility == "allowed"  # a=3 ≥ 1, takes else


def test_nested_if_as_branch_value_matched():
    outcome = evaluate_condition(
        "if(a > 1, if(player.sanity < 40, blocked; uncertain:0.3); allowed)", _context()
    )
    assert outcome.feasibility == "blocked"  # a > 1, inner: sanity < 40 → blocked


def test_nested_if_as_default():
    outcome = evaluate_condition(
        "if(a < 1, blocked; if(player.sanity > 80, uncertain:0.3; allowed))", _context()
    )
    assert outcome.feasibility == "allowed"  # a=3 ≥ 1 → default: sanity=35 ≤ 80 → allowed


def test_nested_if_deep():
    outcome = evaluate_condition(
        "if(a < 1, blocked; if(a < 2, uncertain:0.1; if(a < 5, uncertain:0.5; allowed)))",
        _context(),
    )
    assert outcome.feasibility == "uncertain"
    assert outcome.probability == 0.5


# ── combined operations ──


def test_set_and_bool_combined():
    outcome = evaluate_condition(
        'if("alert" in player.flags and len(player.flags) > 1, blocked; allowed)',
        _ctx_with_lists(),
    )
    assert outcome.feasibility == "blocked"


def test_boolean_with_set():
    outcome = evaluate_condition(
        'if(not ("boss" in player.flags) and player.sanity < 50, blocked; allowed)',
        _ctx_with_lists(),
    )
    assert outcome.feasibility == "blocked"


# ── error cases ──


def test_in_with_nonlist_rhs_raises():
    with pytest.raises(ConditionEvalError):
        evaluate_condition('if("alert" in player.sanity, blocked; allowed)', _ctx_with_lists())


def test_subset_with_string_raises():
    with pytest.raises(ConditionEvalError):
        evaluate_condition("if(player.stage subset player.flags, blocked; allowed)", _ctx_with_lists())


def test_len_on_number_raises():
    with pytest.raises(ConditionEvalError):
        evaluate_condition("if(len(player.sanity) > 0, blocked; allowed)", _ctx_with_lists())


# ── Random function tests ──


def test_rand_comparison():
    outcome = evaluate_condition(
        "if(rand() < 1.0, allowed; blocked)", _context()
    )
    assert outcome.feasibility == "allowed"


def test_rand_range_comparison():
    outcome = evaluate_condition(
        "if(rand(0, 100) >= 0, allowed; blocked)", _context()
    )
    assert outcome.feasibility == "allowed"


def test_randint_comparison():
    outcome = evaluate_condition(
        "if(randint(1, 6) >= 1, allowed; blocked)", _context()
    )
    assert outcome.feasibility == "allowed"


def test_rand_with_boolean_input():
    outcome = evaluate_condition(
        "if(rand(), uncertain:0.5; allowed)", _context()
    )
    assert outcome.feasibility == "uncertain"
