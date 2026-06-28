"""Tests for src/game/tick_eval.py — dynamic tick speed expression evaluator."""

import pytest

from src.game.tick_eval import TickEvalError, evaluate_tick_expression


def _context(**overrides):
    ctx = {
        "player_duration": 0.0,
        "npc_durations": [],
        "player": {
            "status_effects": {},
            "attributes": {
                "speed": {"value": 1.0},
            },
        },
        "player_action": {
            "action_type": "wait",
            "duration_minutes": 0.0,
        },
        "default": 5.0,
    }
    ctx.update(overrides)
    return ctx


# ── Basic if/else ──


def test_simple_if_else():
    ctx = _context(default=5.0)
    result = evaluate_tick_expression("if(player_duration > 2.0, 1.0; 5.0)", ctx)
    assert result == 5.0


def test_multi_branch_chain():
    ctx = _context(player_duration=3.0)
    result = evaluate_tick_expression(
        "if(player_duration < 1.0, 0.5; player_duration < 5.0, 3.0; 10.0)", ctx
    )
    assert result == 3.0


def test_else_branch_when_no_conditions_match():
    ctx = _context(player_duration=10.0)
    result = evaluate_tick_expression(
        "if(player_duration < 1.0, 0.5; player_duration < 5.0, 3.0; 10.0)", ctx
    )
    assert result == 10.0


def test_default_variable():
    ctx = _context(default=7.5)
    result = evaluate_tick_expression("if(player_duration > 10.0, 1.0; default)", ctx)
    assert result == 7.5


# ── Comparison operators ──


def test_less_than():
    ctx = _context(player_duration=1.0)
    assert evaluate_tick_expression("if(player_duration < 2.0, 1.0; 5.0)", ctx) == 1.0


def test_greater_than():
    ctx = _context(player_duration=3.0)
    assert evaluate_tick_expression("if(player_duration > 2.0, 1.0; 5.0)", ctx) == 1.0


def test_equals():
    ctx = _context(player_duration=3.0)
    assert evaluate_tick_expression("if(player_duration = 3.0, 1.0; 5.0)", ctx) == 1.0


def test_less_or_equal():
    ctx = _context(player_duration=3.0)
    assert evaluate_tick_expression("if(player_duration <= 3.0, 1.0; 5.0)", ctx) == 1.0
    assert evaluate_tick_expression("if(player_duration <= 4.0, 1.0; 5.0)", ctx) == 1.0
    assert evaluate_tick_expression("if(player_duration <= 2.0, 1.0; 5.0)", ctx) == 5.0


def test_greater_or_equal():
    ctx = _context(player_duration=3.0)
    assert evaluate_tick_expression("if(player_duration >= 3.0, 1.0; 5.0)", ctx) == 1.0
    assert evaluate_tick_expression("if(player_duration >= 2.0, 1.0; 5.0)", ctx) == 1.0
    assert evaluate_tick_expression("if(player_duration >= 4.0, 1.0; 5.0)", ctx) == 5.0


def test_not_equal():
    ctx = _context(player_duration=3.0)
    assert evaluate_tick_expression("if(player_duration != 4.0, 1.0; 5.0)", ctx) == 1.0
    assert evaluate_tick_expression("if(player_duration != 3.0, 1.0; 5.0)", ctx) == 5.0


# ── Contains operator ──


def test_contains_dict_key():
    ctx = _context(
        player={"status_effects": {"fighting": True}},
        npc_durations=[1.0, 5.0, 10.0],
    )
    result = evaluate_tick_expression(
        "if(player.status_effects contains fighting, min(npc_durations); 5.0)", ctx
    )
    assert result == 1.0


def test_contains_list_item():
    ctx = _context(player={"status_effects": ["fighting", "poisoned"]})
    result = evaluate_tick_expression(
        "if(player.status_effects contains fighting, 1.0; 5.0)", ctx
    )
    assert result == 1.0


def test_contains_string():
    ctx = _context(player={"status": "fighting_mode"})
    result = evaluate_tick_expression(
        "if(player.status contains fighting, 1.0; 5.0)", ctx
    )
    assert result == 1.0


def test_contains_not_found():
    ctx = _context(player={"status_effects": {"calm": True}})
    result = evaluate_tick_expression(
        "if(player.status_effects contains fighting, 1.0; 5.0)", ctx
    )
    assert result == 5.0


# ── Arithmetic ──


def test_addition():
    ctx = _context(player_duration=2.0)
    result = evaluate_tick_expression("if(player_duration + 1.0 < 4.0, 3.0; 10.0)", ctx)
    assert result == 3.0


def test_subtraction():
    ctx = _context(player_duration=5.0)
    result = evaluate_tick_expression("if(player_duration - 1.0 > 3.0, 3.0; 10.0)", ctx)
    assert result == 3.0


def test_multiplication():
    ctx = _context(player={"attributes": {"speed": {"value": 2.0}}})
    result = evaluate_tick_expression(
        "if(player.attributes.speed.value * 2.0 > 3.0, 1.0; 5.0)", ctx
    )
    assert result == 1.0


def test_division():
    ctx = _context(player_duration=10.0)
    result = evaluate_tick_expression(
        "if(player_duration / 2.0 < 6.0, 1.0; 5.0)", ctx
    )
    assert result == 1.0


def test_negation():
    ctx = _context(player_duration=-5.0)
    result = evaluate_tick_expression("if(-player_duration > 3.0, 1.0; 5.0)", ctx)
    assert result == 1.0


def test_parentheses():
    ctx = _context(player_duration=2.0)
    result = evaluate_tick_expression(
        "if((player_duration + 1.0) * 2.0 < 5.0, 1.0; 5.0)", ctx
    )
    assert result == 5.0


# ── Aggregate functions (list form) ──


def test_min_aggregate():
    ctx = _context(player_duration=2.0, npc_durations=[1.0, 5.0, 10.0])
    result = evaluate_tick_expression(
        "if(player_duration < 1.0, min(npc_durations); 5.0)", ctx
    )
    assert result == 5.0


def test_max_aggregate():
    ctx = _context(npc_durations=[1.0, 5.0, 10.0])
    result = evaluate_tick_expression(
        "if(player_duration > 10.0, max(npc_durations); default)", ctx
    )
    assert result == 5.0


def test_avg_aggregate():
    ctx = _context(player_duration=1.0, npc_durations=[2.0, 4.0, 6.0])
    result = evaluate_tick_expression(
        "if(player_duration > 0.0, avg(npc_durations); default)", ctx
    )
    assert result == 4.0


def test_min_two_arg_scalar():
    ctx = _context(player_duration=3.0)
    result = evaluate_tick_expression(
        "if(min(player_duration, 5.0) < 4.0, 1.0; 5.0)", ctx
    )
    assert result == 1.0


def test_max_two_arg_scalar():
    ctx = _context(player_duration=3.0)
    result = evaluate_tick_expression(
        "if(max(player_duration, 5.0) > 4.0, 1.0; 5.0)", ctx
    )
    assert result == 1.0


def test_aggregate_uses_npc_durations_in_value():
    ctx = _context(npc_durations=[1.0, 5.0, 10.0])
    result = evaluate_tick_expression(
        "if(player_duration > 10.0, 10.0; min(npc_durations))", ctx
    )
    assert result == 1.0


# ── Dotted path resolution ──


def test_player_action_field():
    ctx = _context(player_action={"action_type": "move", "duration_minutes": 3.0})
    result = evaluate_tick_expression(
        "if(player_action.action_type = move, 1.0; 5.0)", ctx
    )
    assert result == 1.0


def test_player_action_duration():
    ctx = _context(player_action={"action_type": "move", "duration_minutes": 3.0})
    result = evaluate_tick_expression(
        "if(player_action.duration_minutes > 2.0, 2.0; 5.0)", ctx
    )
    assert result == 2.0


def test_nested_player_attribute():
    ctx = _context(player={"attributes": {"speed": {"value": 1.5}}})
    result = evaluate_tick_expression(
        "if(player.attributes.speed.value > 1.0, 2.0; 5.0)", ctx
    )
    assert result == 2.0


# ── Complex real-world patterns ──


def test_fighting_tick_uses_min_npc_time():
    ctx = _context(
        player={"status_effects": {"fighting": True}},
        npc_durations=[0.5, 1.0, 0.3],
    )
    result = evaluate_tick_expression(
        "if(player.status_effects contains fighting, min(npc_durations); 5.0)", ctx
    )
    assert result == 0.3


def test_move_action_uses_max_of_player_and_min_npc():
    ctx = _context(
        player_action={"action_type": "move", "duration_minutes": 15.0},
        player_duration=15.0,
        npc_durations=[2.0, 5.0],
    )
    result = evaluate_tick_expression(
        "if(player_action.action_type = move, max(player_duration, min(npc_durations)); 5.0)",
        ctx,
    )
    assert result == 15.0


def test_default_when_no_conditions_match():
    ctx = _context(
        player_action={"action_type": "wait", "duration_minutes": 0.0},
        npc_durations=[],
    )
    result = evaluate_tick_expression(
        "if(player_action.action_type = move, 30.0; player.status_effects contains fighting, 0.5; default)",
        ctx,
    )
    assert result == 5.0


# ── Error cases ──


def test_missing_variable_raises():
    with pytest.raises(TickEvalError):
        evaluate_tick_expression("if(player.unknown > 1.0, 1.0; 5.0)", _context())


def test_division_by_zero_raises():
    with pytest.raises(TickEvalError):
        evaluate_tick_expression("if(player_duration / 0.0 > 1.0, 1.0; 5.0)", _context())


def test_invalid_syntax_raises():
    with pytest.raises(TickEvalError):
        evaluate_tick_expression("player_duration < 30", _context())


def test_trailing_content_raises():
    with pytest.raises(TickEvalError):
        evaluate_tick_expression("if(player_duration < 1.0, 1.0; 5.0) extra", _context())


def test_empty_list_aggregate_raises():
    with pytest.raises(TickEvalError):
        evaluate_tick_expression("if(player_duration > 10.0, min(npc_durations); 5.0)", _context(npc_durations=[]))


def test_unknown_expression_start_raises():
    with pytest.raises(TickEvalError):
        evaluate_tick_expression("42", _context())
