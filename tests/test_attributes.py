from src.game.attributes import (
    apply_attribute_changes,
    apply_natural_attribute_deltas,
    summarize_attributes_for_prompt,
    visible_player_attributes,
)


def test_natural_delta_applies_and_clamps_player_attribute():
    player = {
        "name": "玩家",
        "attributes": {
            "stamina": {"name": "体力", "value": 99, "min": 0, "max": 100, "natural_delta_per_tick": 5}
        },
    }

    new_player, new_chars, events = apply_natural_attribute_deltas(player, {})

    assert new_player["attributes"]["stamina"]["value"] == 100
    assert new_chars == {}
    assert any("体力" in event for event in events)


def test_natural_delta_skips_locked_attribute():
    player = {
        "attributes": {
            "curse": {"name": "诅咒", "value": 10, "natural_delta_per_tick": -1, "locked": True}
        }
    }

    new_player, _, events = apply_natural_attribute_deltas(player, {})

    assert new_player["attributes"]["curse"]["value"] == 10
    assert events == []


def test_attribute_change_updates_existing_player_attribute():
    player = {
        "player_id": "player_1",
        "name": "艾琳",
        "attributes": {
            "mood": {"name": "心情", "value": 0, "min": -100, "max": 100}
        },
    }
    changes = [{"entity_type": "player", "entity_id": "player_1", "attribute_key": "mood", "delta": -15, "reason": "被嘲讽"}]

    new_player, _, events = apply_attribute_changes(player, {}, changes)

    assert new_player["attributes"]["mood"]["value"] == -15
    assert any("被嘲讽" in event for event in events)


def test_attribute_change_updates_existing_npc_attribute():
    chars = {
        "alice": {
            "name": "Alice",
            "attributes": {"mood": {"name": "心情", "value": 20, "min": -100, "max": 100}},
        }
    }
    changes = [{"entity_type": "character", "entity_id": "alice", "attribute_key": "mood", "delta": 10, "reason": "被鼓励"}]

    _, new_chars, _ = apply_attribute_changes({}, chars, changes)

    assert new_chars["alice"]["attributes"]["mood"]["value"] == 30


def test_attribute_change_ignores_missing_attribute():
    player = {"name": "玩家", "attributes": {}}
    changes = [{"entity_type": "player", "entity_id": "player_1", "attribute_key": "mana", "delta": -5, "reason": "施法"}]

    new_player, _, events = apply_attribute_changes(player, {}, changes)

    assert "mana" not in new_player["attributes"]
    assert any("不存在的属性" in event for event in events)


def test_summarize_attributes_for_prompt_includes_player_and_characters():
    player = {"player_id": "p", "name": "玩家", "attributes": {"stamina": {"name": "体力", "value": 80}}}
    chars = {"alice": {"name": "Alice", "attributes": {"mood": {"name": "心情", "value": 20}}}}

    summary = summarize_attributes_for_prompt(player, chars)

    assert summary["player"]["attributes"]["stamina"]["value"] == 80
    assert summary["characters"]["alice"]["attributes"]["mood"]["value"] == 20


def test_visible_player_attributes_filters_hidden_attributes():
    player = {
        "attributes": {
            "stamina": {"name": "体力", "value": 80},
            "secret": {"name": "秘密", "value": 1, "hidden": True},
        }
    }

    visible = visible_player_attributes(player)

    assert "stamina" in visible
    assert "secret" not in visible
