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


# ── _eval_locked_condition: set operations ──


def test_eval_in_operator_list():
    attrs = {"flags": {"name": "Flags", "value": ["alert", "danger", "boss"]}}
    assert _eval_locked_condition('"alert" in flags', attrs) is True
    assert _eval_locked_condition('"hidden" in flags', attrs) is False


def test_eval_in_operator_string():
    attrs = {"name": {"name": "Name", "value": "hello world"}}
    assert _eval_locked_condition('"hello" in name', attrs) is True
    assert _eval_locked_condition('"xyz" in name', attrs) is False


def test_eval_not_in_operator():
    attrs = {"flags": {"name": "Flags", "value": ["alert", "danger"]}}
    assert _eval_locked_condition('"boss" not in flags', attrs) is True
    assert _eval_locked_condition('"alert" not in flags', attrs) is False


def test_eval_not_in_with_string():
    attrs = {"name": {"name": "Name", "value": "hello"}}
    assert _eval_locked_condition('"xyz" not in name', attrs) is True
    assert _eval_locked_condition('"hel" not in name', attrs) is False


def test_eval_in_with_number():
    attrs = {"nums": {"name": "Nums", "value": [1, 2, 3]}}
    assert _eval_locked_condition("2 in nums", attrs) is True
    assert _eval_locked_condition("5 in nums", attrs) is False


def test_eval_subset():
    attrs = {
        "required": {"name": "Required", "value": ["a", "b"]},
        "inventory": {"name": "Inventory", "value": ["a", "b", "c", "d"]},
    }
    assert _eval_locked_condition("required subset inventory", attrs) is True
    assert _eval_locked_condition("inventory subset required", attrs) is False


def test_eval_superset():
    attrs = {
        "inventory": {"name": "Inventory", "value": ["a", "b", "c"]},
        "required": {"name": "Required", "value": ["a", "b"]},
    }
    assert _eval_locked_condition("inventory superset required", attrs) is True
    assert _eval_locked_condition("required superset inventory", attrs) is False


def test_eval_intersects():
    attrs = {
        "tags": {"name": "Tags", "value": ["alert", "danger"]},
        "danger_tags": {"name": "Danger", "value": ["danger", "boss"]},
    }
    assert _eval_locked_condition("tags intersects danger_tags", attrs) is True


def test_eval_intersects_false():
    attrs = {
        "tags": {"name": "Tags", "value": ["safe", "calm"]},
        "danger_tags": {"name": "Danger", "value": ["danger", "boss"]},
    }
    assert _eval_locked_condition("tags intersects danger_tags", attrs) is False


def test_eval_disjoint():
    attrs = {
        "tags": {"name": "Tags", "value": ["safe", "calm"]},
        "blocked_tags": {"name": "Blocked", "value": ["danger", "boss"]},
    }
    assert _eval_locked_condition("tags disjoint blocked_tags", attrs) is True


def test_eval_disjoint_false():
    attrs = {
        "tags": {"name": "Tags", "value": ["safe", "danger"]},
        "blocked_tags": {"name": "Blocked", "value": ["danger", "boss"]},
    }
    assert _eval_locked_condition("tags disjoint blocked_tags", attrs) is False


# ── _eval_locked_condition: boolean not and len() ──


def test_eval_not_boolean_true_to_false():
    attrs = {"flag": {"name": "Flag", "value": True}}
    assert _eval_locked_condition("not flag", attrs) is False


def test_eval_not_boolean_false_to_true():
    attrs = {"flag": {"name": "Flag", "value": False}}
    assert _eval_locked_condition("not flag", attrs) is True


def test_eval_not_with_comparison():
    attrs = {"x": {"name": "X", "value": 50}}
    assert _eval_locked_condition("not (x > 100)", attrs) is True
    assert _eval_locked_condition("not (x < 100)", attrs) is False


def test_eval_len_list():
    attrs = {"flags": {"name": "Flags", "value": ["alert", "danger", "boss"]}}
    assert _eval_locked_condition("len(flags) > 2", attrs) is True
    assert _eval_locked_condition("len(flags) == 3", attrs) is True
    assert _eval_locked_condition("len(flags) < 3", attrs) is False


def test_eval_len_empty_list():
    attrs = {"flags": {"name": "Flags", "value": []}}
    assert _eval_locked_condition("len(flags) == 0", attrs) is True


def test_eval_len_string():
    attrs = {"name": {"name": "Name", "value": "hello"}}
    assert _eval_locked_condition("len(name) == 5", attrs) is True


# ── _eval_locked_condition: error cases ──


def test_eval_in_with_nonlist_rhs_raises():
    attrs = {"x": {"name": "X", "value": 42}}
    try:
        _eval_locked_condition('"alert" in x', attrs)
        assert False, "should have raised"
    except Exception:
        pass


def test_eval_subset_with_nonlist_raises():
    attrs = {
        "a": {"name": "A", "value": "hello"},
        "b": {"name": "B", "value": ["x", "y"]},
    }
    try:
        _eval_locked_condition("a subset b", attrs)
        assert False, "should have raised"
    except Exception:
        pass


def test_eval_len_on_number_raises():
    attrs = {"x": {"name": "X", "value": 42}}
    try:
        _eval_locked_condition("len(x) > 0", attrs)
        assert False, "should have raised"
    except Exception:
        pass


# ── _eval_locked_condition: combined operations ──


def test_eval_combined_set_and_bool():
    attrs = {"flags": {"name": "Flags", "value": ["alert", "danger"]}}
    assert _eval_locked_condition('"alert" in flags and len(flags) > 1', attrs) is True
    assert _eval_locked_condition('"boss" in flags or len(flags) == 2', attrs) is True
    assert _eval_locked_condition('"boss" in flags and len(flags) == 2', attrs) is False


def test_eval_combined_not_and_set():
    attrs = {"flags": {"name": "Flags", "value": ["alert"]}}
    assert _eval_locked_condition('not ("boss" in flags)', attrs) is True
    assert _eval_locked_condition('not ("alert" in flags)', attrs) is False


def test_eval_combined_set_and_disjoint():
    attrs = {
        "flags": {"name": "Flags", "value": ["safe"]},
        "danger": {"name": "Danger", "value": ["boss"]},
    }
    assert _eval_locked_condition("flags disjoint danger", attrs) is True
    assert _eval_locked_condition("flags disjoint danger and len(flags) == 1", attrs) is True


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


# ── compute rule tests ──


def test_compute_numeric():
    player = {
        "name": "玩家",
        "attributes": {
            "danger": {"name": "危险", "value": 60},
            "threat": {"name": "威胁", "value": 0},
        },
    }
    rules = [{
        "type": "compute",
        "target_key": "threat",
        "expression": "if(danger > 80, 100; danger > 50, 50; 0)",
    }]
    new_player, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["threat"]["value"] == 50
    assert len(events) == 1


def test_compute_string():
    player = {
        "name": "玩家",
        "attributes": {
            "hp": {"name": "HP", "value": 25},
            "status": {"name": "状态", "value": "healthy"},
        },
    }
    rules = [{
        "type": "compute",
        "target_key": "status",
        "expression": 'if(hp <= 0, "dead"; hp < 30, "wounded"; "healthy")',
    }]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["status"]["value"] == "wounded"


def test_compute_boolean():
    player = {
        "name": "玩家",
        "attributes": {
            "hp": {"name": "HP", "value": 50},
            "alive": {"name": "存活", "value": False},
        },
    }
    rules = [{
        "type": "compute",
        "target_key": "alive",
        "expression": "if(hp > 0, true; false)",
    }]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["alive"]["value"] is True


def test_compute_with_arithmetic():
    player = {
        "name": "玩家",
        "attributes": {
            "hp": {"name": "HP", "value": 50},
            "base": {"name": "基础", "value": 10},
            "result": {"name": "结果", "value": 0},
        },
    }
    rules = [{
        "type": "compute",
        "target_key": "result",
        "expression": "if(hp > 40, base + 20; base)",
    }]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["result"]["value"] == 30


def test_compute_with_attribute_ref():
    player = {
        "name": "玩家",
        "attributes": {
            "hp": {"name": "HP", "value": 50},
            "max_hp": {"name": "最大HP", "value": 100},
            "result": {"name": "结果", "value": 0},
        },
    }
    rules = [{
        "type": "compute",
        "target_key": "result",
        "expression": "if(hp > 80, max_hp; hp)",
    }]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["result"]["value"] == 50


def test_compute_multi_branch():
    player = {
        "name": "玩家",
        "attributes": {
            "danger": {"name": "危险", "value": 30},
            "level": {"name": "等级", "value": 0},
        },
    }
    rules = [{
        "type": "compute",
        "target_key": "level",
        "expression": "if(danger > 80, 100; danger > 50, 50; danger > 20, 20; 0)",
    }]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["level"]["value"] == 20


def test_compute_default():
    player = {
        "name": "玩家",
        "attributes": {
            "danger": {"name": "危险", "value": 5},
            "level": {"name": "等级", "value": 0},
        },
    }
    rules = [{
        "type": "compute",
        "target_key": "level",
        "expression": "if(danger > 80, 100; danger > 50, 50; 0)",
    }]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["level"]["value"] == 0


def test_compute_with_and_or():
    player = {
        "name": "玩家",
        "attributes": {
            "hp": {"name": "HP", "value": 50},
            "stamina": {"name": "体力", "value": 80},
            "result": {"name": "结果", "value": 0},
        },
    }
    rules = [{
        "type": "compute",
        "target_key": "result",
        "expression": "if(hp > 30 and stamina > 50, 100; 0)",
    }]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["result"]["value"] == 100


def test_compute_with_set_operation():
    player = {
        "name": "玩家",
        "attributes": {
            "flags": {"name": "标记", "value": ["alert", "danger"]},
            "result": {"name": "结果", "value": 0},
        },
    }
    rules = [{
        "type": "compute",
        "target_key": "result",
        "expression": 'if("alert" in flags, 1; 0)',
    }]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["result"]["value"] == 1


def test_compute_nested_if():
    player = {
        "name": "玩家",
        "attributes": {
            "hp": {"name": "HP", "value": 50},
            "strategy": {"name": "策略", "value": ""},
        },
    }
    rules = [{
        "type": "compute",
        "target_key": "strategy",
        "expression": 'if(hp > 80, "aggressive"; if(hp > 30, "balanced"; "defensive"))',
    }]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["strategy"]["value"] == "balanced"


def test_compute_nested_if_deep():
    player = {
        "name": "玩家",
        "attributes": {
            "val": {"name": "数值", "value": 8},
            "result": {"name": "结果", "value": 0},
        },
    }
    rules = [{
        "type": "compute",
        "target_key": "result",
        "expression": "if(val < 1, 1; if(val < 5, 2; if(val < 10, 3; 4)))",
    }]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["result"]["value"] == 3


def test_compute_list_literal():
    player = {
        "name": "玩家",
        "attributes": {
            "flags": {"name": "标记", "value": ["alert", "danger", "boss"]},
        },
    }
    rules = [{
        "type": "compute",
        "target_key": "flags",
        "expression": 'if(len(flags) > 2, ["overloaded"]; flags)',
    }]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["flags"]["value"] == ["overloaded"]


def test_compute_list_operations():
    player = {
        "name": "玩家",
        "attributes": {
            "tags": {"name": "标签", "value": ["safe"]},
            "danger": {"name": "危险标签", "value": ["boss"]},
            "result": {"name": "结果", "value": []},
        },
    }
    rules = [{
        "type": "compute",
        "target_key": "result",
        "expression": 'if(tags disjoint danger, ["no_threat"]; ["threat"])',
    }]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["result"]["value"] == ["no_threat"]


def test_compute_missing_target_key():
    player = {
        "name": "玩家",
        "attributes": {
            "hp": {"name": "HP", "value": 50},
        },
    }
    rules = [{
        "type": "compute",
        "target_key": "nonexistent",
        "expression": "if(hp > 30, 1; 0)",
    }]
    new_player, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert events == []
    assert "nonexistent" not in new_player["attributes"]


def test_compute_type_preservation():
    player = {
        "name": "玩家",
        "attributes": {
            "hp": {"name": "HP", "value": 50},
            "num_val": {"name": "数值", "value": 0},
            "str_val": {"name": "字符串", "value": ""},
            "bool_val": {"name": "布尔", "value": False},
        },
    }
    rules = [
        {"type": "compute", "target_key": "num_val", "expression": "if(hp > 30, 99; 0)"},
        {"type": "compute", "target_key": "str_val", "expression": 'if(hp > 30, "high"; "low")'},
        {"type": "compute", "target_key": "bool_val", "expression": "if(hp > 30, true; false)"},
    ]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert isinstance(new_player["attributes"]["num_val"]["value"], (int, float))
    assert isinstance(new_player["attributes"]["str_val"]["value"], str)
    assert isinstance(new_player["attributes"]["bool_val"]["value"], bool)


# ── Random function tests ──


def test_locked_condition_rand():
    attrs = {"x": {"value": 5}}
    from src.game.attributes import _eval_locked_condition
    assert _eval_locked_condition("rand() >= 0.0", attrs) is True
    assert _eval_locked_condition("rand() < 1.0", attrs) is True
    assert _eval_locked_condition("rand() < 0.0", attrs) is False


def test_locked_condition_rand_range():
    attrs = {}
    from src.game.attributes import _eval_locked_condition
    assert _eval_locked_condition("rand(10, 20) >= 10", attrs) is True
    assert _eval_locked_condition("rand(10, 20) < 20", attrs) is True


def test_locked_condition_randint():
    attrs = {}
    from src.game.attributes import _eval_locked_condition
    assert _eval_locked_condition("randint(1, 6) >= 1", attrs) is True
    assert _eval_locked_condition("randint(1, 6) <= 6", attrs) is True


def test_compute_rand():
    player = {
        "name": "玩家",
        "attributes": {"hp": {"name": "HP", "value": 50}, "roll": {"name": "骰子", "value": 0}},
    }
    rules = [{"type": "compute", "target_key": "roll", "expression": "if(true, rand(1, 10); 0)"}]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    val = new_player["attributes"]["roll"]["value"]
    assert 1 <= val < 10


def test_compute_randint():
    player = {
        "name": "玩家",
        "attributes": {"hp": {"name": "HP", "value": 50}, "d6": {"name": "D6", "value": 0}},
    }
    rules = [{"type": "compute", "target_key": "d6", "expression": "if(true, randint(1, 6); 0)"}]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    val = new_player["attributes"]["d6"]["value"]
    assert isinstance(val, int)
    assert 1 <= val <= 6


def test_compute_rand_in_condition():
    player = {
        "name": "玩家",
        "attributes": {"hp": {"name": "HP", "value": 50}, "result": {"name": "结果", "value": 0}},
    }
    rules = [{"type": "compute", "target_key": "result", "expression": "if(rand() < 1.0, 100; 0)"}]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["result"]["value"] == 100


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


# ── defer_post tests ──


def test_defer_natural_delta_pre():
    """update_position: pre_narrative (default) applies normally."""
    player = {
        "name": "玩家",
        "attributes": {
            "hp": {"name": "HP", "value": 100, "natural_delta_per_minute": -1.0},
        },
    }
    deferred: list[dict] = []
    new_player, _, events = apply_natural_attribute_deltas(
        player, {},
        tick_duration_minutes=5.0,
        defer_post=True,
        deferred=deferred,
    )
    assert new_player["attributes"]["hp"]["value"] == 95.0
    assert len(deferred) == 0
    assert len(events) == 1


def test_defer_natural_delta_post():
    """update_position: post_narrative is skipped and deferred."""
    player = {
        "name": "玩家",
        "attributes": {
            "counter": {"name": "计数器", "value": 0, "natural_delta_per_minute": 0.5,
                        "update_position": "post_narrative"},
        },
    }
    deferred: list[dict] = []
    new_player, _, events = apply_natural_attribute_deltas(
        player, {},
        tick_duration_minutes=5.0,
        defer_post=True,
        deferred=deferred,
    )
    assert new_player["attributes"]["counter"]["value"] == 0  # unchanged
    assert len(events) == 0
    assert len(deferred) == 1
    assert deferred[0]["attribute_key"] == "counter"


def test_defer_natural_delta_replay():
    """Applying deferred deltas with defer_post=False applies them."""
    player = {
        "name": "玩家",
        "attributes": {
            "counter": {"name": "计数器", "value": 0, "natural_delta_per_minute": 0.5,
                        "update_position": "post_narrative"},
        },
    }
    # First pass: defer
    deferred: list[dict] = []
    new_player, _, _ = apply_natural_attribute_deltas(
        player, {},
        tick_duration_minutes=5.0,
        defer_post=True,
        deferred=deferred,
    )
    assert new_player == player  # unchanged
    # Replay: apply deferred
    replayed, _, events = apply_natural_attribute_deltas(
        new_player, {},
        tick_duration_minutes=5.0,
        defer_post=False,
    )
    assert replayed["attributes"]["counter"]["value"] == 2.5


def test_defer_locked_rule_pre():
    """Locked rule without update_position (default pre) executes."""
    player = {
        "name": "玩家",
        "attributes": {
            "hp": {"name": "HP", "value": 50},
            "result": {"name": "结果", "value": 0},
        },
    }
    rules = [{"type": "compute", "target_key": "result", "expression": "if(hp > 30, 1; 0)"}]
    deferred: list[dict] = []
    new_player, _, events = apply_deterministic_attributes(
        player, {},
        tick_duration_minutes=5.0,
        rules=rules,
        defer_post=True,
        deferred=deferred,
    )
    assert new_player["attributes"]["result"]["value"] == 1
    assert len(deferred) == 0
    assert len(events) == 1


def test_defer_locked_rule_post():
    """Locked rule with update_position: post_narrative is deferred."""
    player = {
        "name": "玩家",
        "attributes": {
            "hp": {"name": "HP", "value": 50},
            "result": {"name": "结果", "value": 0},
        },
    }
    rules = [{
        "type": "compute",
        "target_key": "result",
        "expression": "if(hp > 30, 1; 0)",
        "update_position": "post_narrative",
    }]
    deferred: list[dict] = []
    new_player, _, events = apply_deterministic_attributes(
        player, {},
        tick_duration_minutes=5.0,
        rules=rules,
        defer_post=True,
        deferred=deferred,
    )
    assert new_player["attributes"]["result"]["value"] == 0  # unchanged
    assert len(events) == 0
    assert len(deferred) == 1
    assert deferred[0]["type"] == "compute"


def test_defer_locked_rule_replay():
    """Applying deferred rules with defer_post=False executes them."""
    player = {
        "name": "玩家",
        "attributes": {
            "hp": {"name": "HP", "value": 50},
            "result": {"name": "结果", "value": 0},
        },
    }
    deferred_rules = [{
        "type": "compute",
        "target_key": "result",
        "expression": "if(hp > 30, 1; 0)",
    }]
    new_player, _, events = apply_deterministic_attributes(
        player, {},
        tick_duration_minutes=5.0,
        rules=deferred_rules,
        defer_post=False,
    )
    assert new_player["attributes"]["result"]["value"] == 1


def test_defer_mixed_pre_and_post():
    """Mixed pre and post rules: pre apply, post defer."""
    player = {
        "name": "玩家",
        "attributes": {
            "hp": {"name": "HP", "value": 100, "natural_delta_per_minute": -1.0},
            "counter": {"name": "计数器", "value": 0, "natural_delta_per_minute": 0.5,
                        "update_position": "post_narrative"},
        },
    }
    deferred: list[dict] = []
    new_player, _, events = apply_natural_attribute_deltas(
        player, {},
        tick_duration_minutes=5.0,
        defer_post=True,
        deferred=deferred,
    )
    assert new_player["attributes"]["hp"]["value"] == 95.0  # pre: applied
    assert new_player["attributes"]["counter"]["value"] == 0  # post: skipped
    assert len(deferred) == 1


def test_defer_default_is_pre():
    """Omitting update_position defaults to pre_narrative."""
    player = {
        "name": "玩家",
        "attributes": {
            "hp": {"name": "HP", "value": 100, "natural_delta_per_minute": -1.0},
        },
    }
    deferred: list[dict] = []
    new_player, _, _ = apply_natural_attribute_deltas(
        player, {},
        tick_duration_minutes=5.0,
        defer_post=True,
        deferred=deferred,
    )
    assert new_player["attributes"]["hp"]["value"] == 95.0
    assert len(deferred) == 0
