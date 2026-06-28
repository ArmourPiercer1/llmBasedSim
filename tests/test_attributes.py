from src.game.attributes import (
    _eval_locked_condition,
    apply_attribute_changes,
    apply_deterministic_attributes,
    apply_natural_attribute_deltas,
    summarize_attributes_for_prompt,
    visible_player_attributes,
)


def test_natural_delta_applies_and_clamps_player_attribute():
    player = {
        "name": "玩家",
        "attributes": {
            "stamina": {"name": "体力", "value": 99, "min": 0, "max": 100, "natural_delta_per_minute": 1}
        },
    }

    new_player, new_chars, events = apply_natural_attribute_deltas(player, {})

    assert new_player["attributes"]["stamina"]["value"] == 100
    assert new_chars == {}
    assert any("体力" in event for event in events)


def test_natural_delta_skips_locked_attribute():
    player = {
        "attributes": {
            "curse": {"name": "诅咒", "value": 10, "natural_delta_per_minute": -1, "locked": True}
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


# ── _eval_locked_condition tests ──


def test_eval_simple_numeric_comparison():
    attrs = {"hp": {"name": "HP", "value": 50}}
    assert _eval_locked_condition("hp < 100", attrs) is True
    assert _eval_locked_condition("hp > 100", attrs) is False
    assert _eval_locked_condition("hp <= 50", attrs) is True
    assert _eval_locked_condition("hp >= 50", attrs) is True
    assert _eval_locked_condition("hp == 50", attrs) is True
    assert _eval_locked_condition("hp != 50", attrs) is False


def test_eval_or_logic():
    attrs = {"x": {"name": "X", "value": 50}}
    assert _eval_locked_condition("x < 30 or x > 40", attrs) is True
    assert _eval_locked_condition("x < 30 or x > 60", attrs) is False


def test_eval_and_logic():
    attrs = {"x": {"name": "X", "value": 50}}
    assert _eval_locked_condition("x > 30 and x < 60", attrs) is True
    assert _eval_locked_condition("x > 30 and x < 40", attrs) is False


def test_eval_abs_function():
    attrs = {"a": {"name": "A", "value": 5}, "b": {"name": "B", "value": 7}}
    assert _eval_locked_condition("abs(a - b) < 3", attrs) is True
    assert _eval_locked_condition("abs(a - b) < 2", attrs) is False


def test_eval_arithmetic_comparison():
    attrs = {"x": {"name": "X", "value": 10}, "y": {"name": "Y", "value": 3}}
    assert _eval_locked_condition("x - y < 8", attrs) is True
    assert _eval_locked_condition("x - y < 7", attrs) is False


def test_eval_boolean_comparison():
    attrs = {"flag": {"name": "FLAG", "value": True}}
    assert _eval_locked_condition("flag == true", attrs) is True
    assert _eval_locked_condition("flag == false", attrs) is False


def test_eval_string_comparison():
    attrs = {"stage": {"name": "Stage", "value": "latent"}}
    assert _eval_locked_condition('stage == "latent"', attrs) is True
    assert _eval_locked_condition('stage == "active"', attrs) is False


def test_eval_nonexistent_attr_raises():
    attrs = {}
    try:
        _eval_locked_condition("nonexistent < 100", attrs)
        assert False, "should have raised"
    except Exception:
        pass


# ── apply_deterministic_attributes tests ──


def test_deterministic_noop_without_rules():
    """Empty rules → returns unchanged player."""
    player = {"name": "玩家", "attributes": {"hp": {"name": "HP", "value": 80}}}
    new_player, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=[])
    assert events == []
    assert new_player["attributes"]["hp"]["value"] == 80


def test_deterministic_noop_with_none_rules():
    """None rules → returns unchanged player."""
    player = {"name": "玩家", "attributes": {"hp": {"name": "HP", "value": 80}}}
    new_player, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=None)
    assert events == []
    assert new_player["attributes"]["hp"]["value"] == 80


def test_deterministic_noop_when_attrs_missing():
    """Rule references non-existent attrs → skipped gracefully."""
    player = {"name": "玩家", "attributes": {}}
    rules = [{"type": "timer", "timer_key": "nonexistent", "condition": "x < 1"}]
    new_player, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert events == []


# ── timer rule tests ──


def test_timer_accumulates_when_condition_true():
    player = {
        "name": "玩家",
        "attributes": {
            "danger": {"name": "危险", "value": 1},
            "alert_timer": {"name": "警报计时", "value": 0},
        },
    }
    rules = [{
        "type": "timer",
        "timer_key": "alert_timer",
        "condition": "danger > 0",
        "thresholds": [10, 30],
        "warning": "警报已持续{threshold}分钟。",
    }]
    new_player, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["alert_timer"]["value"] == 5.0
    assert events == []  # no threshold crossed yet


def test_timer_resets_when_condition_false():
    player = {
        "name": "玩家",
        "attributes": {
            "danger": {"name": "危险", "value": 0},
            "alert_timer": {"name": "警报计时", "value": 100},
        },
    }
    rules = [{
        "type": "timer",
        "timer_key": "alert_timer",
        "condition": "danger > 0",
        "thresholds": [10],
        "warning": "阈值{threshold}。",
    }]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["alert_timer"]["value"] == 0.0


def test_timer_threshold_warning():
    player = {
        "name": "玩家",
        "attributes": {
            "danger": {"name": "危险", "value": 1},
            "alert_timer": {"name": "警报计时", "value": 9},
        },
    }
    rules = [{
        "type": "timer",
        "timer_key": "alert_timer",
        "condition": "danger > 0",
        "thresholds": [10],
        "warning": "已超过{threshold}分钟。",
    }]
    _, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=2.0, rules=rules)
    assert any("10" in e for e in events)


def test_timer_no_threshold_warning_on_already_crossed():
    """Threshold not triggered if old value already above it."""
    player = {
        "name": "玩家",
        "attributes": {
            "danger": {"name": "危险", "value": 1},
            "alert_timer": {"name": "警报计时", "value": 15},
        },
    }
    rules = [{
        "type": "timer",
        "timer_key": "alert_timer",
        "condition": "danger > 0",
        "thresholds": [10],
        "warning": "已超过{threshold}分钟。",
    }]
    _, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    # old=15, new=20 — 10 was already crossed before this tick
    assert not any("10" in e for e in events)


# ── stage rule tests ──


def test_stage_progression():
    player = {
        "name": "玩家",
        "attributes": {
            "phase": {"name": "阶段", "value": "one"},
            "progress": {"name": "进度", "value": 60},
        },
    }
    rules = [{
        "type": "stage",
        "stage_key": "phase",
        "stages": ["one", "two", "three"],
        "rules": [
            {"condition": "progress >= 80", "stage": "three"},
            {"condition": "progress >= 50", "stage": "two"},
            {"stage": "one"},
        ],
    }]
    new_player, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["phase"]["value"] == "two"
    assert any("two" in e for e in events)


def test_stage_monotonic():
    """Stage never regresses."""
    player = {
        "name": "玩家",
        "attributes": {
            "phase": {"name": "阶段", "value": "three"},
            "progress": {"name": "进度", "value": 10},
        },
    }
    rules = [{
        "type": "stage",
        "stage_key": "phase",
        "stages": ["one", "two", "three"],
        "rules": [
            {"condition": "progress >= 80", "stage": "three"},
            {"condition": "progress >= 50", "stage": "two"},
            {"stage": "one"},
        ],
    }]
    new_player, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    # progress=10 would suggest "one", but already at "three"
    assert new_player["attributes"]["phase"]["value"] == "three"
    assert events == []


def test_stage_no_change():
    """Same stage → no event."""
    player = {
        "name": "玩家",
        "attributes": {
            "phase": {"name": "阶段", "value": "two"},
            "progress": {"name": "进度", "value": 60},
        },
    }
    rules = [{
        "type": "stage",
        "stage_key": "phase",
        "stages": ["one", "two", "three"],
        "rules": [
            {"condition": "progress >= 80", "stage": "three"},
            {"condition": "progress >= 50", "stage": "two"},
            {"stage": "one"},
        ],
    }]
    _, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert events == []


def test_stage_default_fallback():
    """Fallback rule (no condition) is selected when no condition matches."""
    player = {
        "name": "玩家",
        "attributes": {
            "phase": {"name": "阶段", "value": "start"},
            "progress": {"name": "进度", "value": 0},
        },
    }
    rules = [{
        "type": "stage",
        "stage_key": "phase",
        "stages": ["start", "mid", "end"],
        "rules": [
            {"condition": "progress >= 80", "stage": "end"},
            {"condition": "progress >= 50", "stage": "mid"},
            {"stage": "start"},
        ],
    }]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["phase"]["value"] == "start"


# ── snapshot rule tests ──


def test_snapshot_copies_value():
    player = {
        "name": "玩家",
        "attributes": {
            "position": {"name": "位置", "value": 2.5},
            "_prev_position": {"name": "上次位置", "value": 2.0},
        },
    }
    rules = [{"type": "snapshot", "source_key": "position", "snapshot_key": "_prev_position"}]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["_prev_position"]["value"] == 2.5


def test_snapshot_creates_if_missing():
    """Snapshot creates the target attribute if it doesn't exist."""
    player = {
        "name": "玩家",
        "attributes": {
            "position": {"name": "位置", "value": 3.0},
        },
    }
    rules = [{"type": "snapshot", "source_key": "position", "snapshot_key": "_prev_position"}]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["_prev_position"]["value"] == 3.0


# ── list_constraint rule tests ──


def test_list_constraint_appends():
    player = {
        "name": "玩家",
        "attributes": {
            "flags": {"name": "标记", "value": []},
            "threshold": {"name": "阈值", "value": 5},
        },
    }
    rules = [{
        "type": "list_constraint",
        "list_key": "flags",
        "condition": "threshold > 3",
        "value": "alert",
    }]
    new_player, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert "alert" in new_player["attributes"]["flags"]["value"]
    assert any("alert" in e for e in events)


def test_list_constraint_no_duplicate():
    player = {
        "name": "玩家",
        "attributes": {
            "flags": {"name": "标记", "value": ["alert"]},
            "threshold": {"name": "阈值", "value": 5},
        },
    }
    rules = [{
        "type": "list_constraint",
        "list_key": "flags",
        "condition": "threshold > 3",
        "value": "alert",
    }]
    new_player, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["flags"]["value"].count("alert") == 1
    assert events == []


def test_list_constraint_not_triggered():
    player = {
        "name": "玩家",
        "attributes": {
            "flags": {"name": "标记", "value": []},
            "threshold": {"name": "阈值", "value": 1},
        },
    }
    rules = [{
        "type": "list_constraint",
        "list_key": "flags",
        "condition": "threshold > 3",
        "value": "alert",
    }]
    new_player, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert "alert" not in new_player["attributes"]["flags"]["value"]
    assert events == []


# ── rule ordering test ──


def test_snapshot_before_timer():
    """Snapshot must run before timer that references its target attr."""
    player = {
        "name": "玩家",
        "attributes": {
            "val": {"name": "值", "value": 5.0},
            "_prev_val": {"name": "上次值", "value": 5.0},
            "stall_timer": {"name": "停滞计时", "value": 0},
        },
    }
    rules = [
        {"type": "snapshot", "source_key": "val", "snapshot_key": "_prev_val"},
        {
            "type": "timer",
            "timer_key": "stall_timer",
            "condition": "abs(val - _prev_val) < 0.001",
            "thresholds": [10],
            "warning": "停滞{threshold}分钟。",
        },
    ]
    # val == _prev_val so stall_timer should accumulate
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["stall_timer"]["value"] == 5.0
