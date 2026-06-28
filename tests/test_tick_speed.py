"""Tests for tick_speed_resolve node logic.

The tick_speed_resolve node is defined as a closure inside build_game_graph()
in game_graph.py, so it cannot be directly imported. Instead, these tests
validate the core algorithm by testing evaluate_tick_expression with realistic
game-state contexts and testing the default/min/max/truncation logic inline.
"""

from src.game.tick_eval import evaluate_tick_expression


# ── Helper: simulate tick_speed_resolve core logic ──


def _resolve_tick_duration(
    player_duration: float = 0.0,
    npc_durations: list[float] | None = None,
    default: float = 5.0,
    min_minutes: float = 0.1,
    max_minutes: float = 50.0,
    expression: str = "",
    player: dict | None = None,
    player_action: dict | None = None,
) -> float:
    """Replicates the core tick duration decision logic from tick_speed_resolve."""
    npc_durations = npc_durations or []

    if expression:
        tick_duration = evaluate_tick_expression(expression, {
            "player_duration": player_duration,
            "npc_durations": npc_durations,
            "player": player or {},
            "player_action": player_action or {},
            "default": default,
        })
    else:
        # Default strategy: min NPC, else player, else default
        tick_duration = (
            min(npc_durations) if npc_durations
            else (player_duration if player_duration > 0 else default)
        )

    return max(min_minutes, min(tick_duration, max_minutes))


def _truncate_actions(
    player_duration: float, tick_duration: float, action_type: str
) -> bool:
    """Returns True if action should be truncated."""
    return player_duration > tick_duration and action_type not in ("speak", "wait", "observe")


def test_default_strategy_min_of_npc():
    dur = _resolve_tick_duration(npc_durations=[1.0, 5.0, 10.0])
    assert dur == 1.0


def test_default_strategy_no_npc_use_player():
    dur = _resolve_tick_duration(player_duration=3.0, npc_durations=[])
    assert dur == 3.0


def test_default_strategy_no_npc_no_player_fallback():
    dur = _resolve_tick_duration(player_duration=0.0, npc_durations=[], default=7.5)
    assert dur == 7.5


def test_default_strategy_no_npc_no_player_fallback_default_default():
    dur = _resolve_tick_duration(player_duration=0.0, npc_durations=[])
    assert dur == 5.0


# ── Expression evaluation with realistic contexts ──


def test_expression_fighting():
    dur = _resolve_tick_duration(
        npc_durations=[0.5, 1.0, 0.3],
        player={"status_effects": {"fighting": True}},
        expression="if(player.status_effects contains fighting, min(npc_durations); default)",
    )
    assert dur == 0.3


def test_expression_move_action():
    dur = _resolve_tick_duration(
        player_duration=15.0,
        npc_durations=[2.0, 5.0],
        player_action={"action_type": "move", "duration_minutes": 15.0},
        expression="if(player_action.action_type = move, max(player_duration, min(npc_durations)); default)",
    )
    assert dur == 15.0


def test_expression_speak_action_uses_default():
    dur = _resolve_tick_duration(
        player_duration=1.0,
        player_action={"action_type": "speak", "duration_minutes": 1.0},
        expression="if(player_action.action_type = move, 30.0; default)",
    )
    assert dur == 5.0


def test_expression_custom_default():
    dur = _resolve_tick_duration(
        default=2.0,
        expression="if(player_duration > 10.0, 10.0; default)",
    )
    assert dur == 2.0


# ── Bounds clamping ──


def test_min_clamp():
    dur = _resolve_tick_duration(
        npc_durations=[0.01],
        min_minutes=0.5,
    )
    assert dur == 0.5


def test_max_clamp():
    dur = _resolve_tick_duration(
        player_duration=100.0,
        npc_durations=[],
        max_minutes=30.0,
    )
    assert dur == 30.0


def test_clamp_respected_when_in_bounds():
    dur = _resolve_tick_duration(
        npc_durations=[5.0],
        min_minutes=1.0,
        max_minutes=10.0,
    )
    assert dur == 5.0


# ── Action truncation ──


def test_truncate_move_action():
    assert _truncate_actions(10.0, 5.0, "move") is True


def test_truncate_interact_action():
    assert _truncate_actions(10.0, 5.0, "interact") is True


def test_truncate_use_item_action():
    assert _truncate_actions(10.0, 5.0, "use_item") is True


def test_no_truncate_speak():
    assert _truncate_actions(10.0, 5.0, "speak") is False


def test_no_truncate_wait():
    assert _truncate_actions(10.0, 5.0, "wait") is False


def test_no_truncate_observe():
    assert _truncate_actions(10.0, 5.0, "observe") is False


def test_no_truncate_when_within_bounds():
    assert _truncate_actions(3.0, 5.0, "move") is False


def test_no_truncate_when_exact():
    assert _truncate_actions(5.0, 5.0, "move") is False


# ── Real-world integration scenarios ──


def test_scenario_idle_town_tick():
    """No combat, no long moves — use default."""
    dur = _resolve_tick_duration(
        player_duration=0.0,
        npc_durations=[3.0, 5.0],
        player_action={"action_type": "wait"},
        expression="",
    )
    assert dur == 3.0  # min NPC


def test_scenario_combat_tick():
    """Fighting — use fastest NPC action time."""
    dur = _resolve_tick_duration(
        player_duration=2.0,
        npc_durations=[0.3, 0.5, 1.0],
        player={"status_effects": {"fighting": True}},
        player_action={"action_type": "attack"},
        expression="if(player.status_effects contains fighting, min(npc_durations); default)",
    )
    assert dur == 0.3


def test_scenario_long_travel_tick():
    """Player moving long distance with NPCs following — use player time."""
    dur = _resolve_tick_duration(
        player_duration=30.0,
        npc_durations=[15.0, 20.0],
        player_action={"action_type": "move", "duration_minutes": 30.0},
        expression="if(player_action.action_type = move, max(player_duration, min(npc_durations)); default)",
    )
    assert dur == 30.0
