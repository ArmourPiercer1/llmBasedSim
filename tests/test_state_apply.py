from unittest.mock import patch

from src.game.state_apply import apply_player_action


def test_allowed_move_updates_player_position():
    player = {"position": {"x": 0, "y": 0, "z": 0}, "inventory": []}
    action = {
        "feasibility": "allowed",
        "action_type": "move",
        "action_description": "走到露台",
        "target_position": {"x": 3, "y": 0, "z": 4},
    }

    new_player, _, events = apply_player_action(player, action, {})

    assert new_player["position"] == {"x": 3.0, "y": 0.0, "z": 4.0}
    assert events


def test_blocked_action_does_not_mutate_state():
    player = {"position": {"x": 0, "y": 0, "z": 0}, "inventory": []}
    action = {
        "feasibility": "blocked",
        "action_type": "interact",
        "action_description": "推桌子",
        "feasibility_reason": "太重",
    }

    new_player, _, events = apply_player_action(player, action, {})

    assert new_player == player
    assert "被阻止" in events[0]


def test_roll_success_applies_action():
    player = {"position": {"x": 0, "y": 0, "z": 0}, "inventory": []}
    action = {
        "feasibility": "uncertain",
        "requires_roll": True,
        "success_probability": 0.5,
        "action_type": "move",
        "action_description": "冒险穿过窄门",
        "target_position": {"x": 5, "y": 0, "z": 0},
    }

    with patch("random.random", return_value=0.1):
        new_player, _, events = apply_player_action(player, action, {})

    assert new_player["position"] == {"x": 5.0, "y": 0.0, "z": 0.0}
    assert any("检定成功" in e for e in events)


def test_roll_failure_does_not_apply_action():
    player = {"position": {"x": 0, "y": 0, "z": 0}, "inventory": []}
    action = {
        "feasibility": "uncertain",
        "requires_roll": True,
        "success_probability": 0.5,
        "action_type": "move",
        "action_description": "冒险穿过窄门",
        "target_position": {"x": 5, "y": 0, "z": 0},
    }

    with patch("random.random", return_value=0.9):
        new_player, _, events = apply_player_action(player, action, {})

    assert new_player == player
    assert any("检定失败" in e for e in events)
