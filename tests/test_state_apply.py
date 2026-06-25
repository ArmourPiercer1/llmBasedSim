from unittest.mock import patch

from src.game.state_apply import apply_player_action, apply_npc_actions, _emotion_delta


# ── Player action tests ──

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


def test_none_action_returns_unchanged():
    player = {"position": {"x": 1, "y": 2, "z": 3}}
    new_player, new_objects, events = apply_player_action(player, None, {})
    assert new_player == player
    assert events == []


def test_allowed_interact_picks_up_portable_item():
    player = {"position": {"x": 0, "y": 0, "z": 0}, "inventory": []}
    objects = {
        "key": {"name": "钥匙", "state": {}, "properties": {"portable": True}}
    }
    action = {
        "feasibility": "allowed",
        "action_type": "interact",
        "action_description": "捡起钥匙",
        "target_object_id": "key",
    }
    new_player, new_objects, events = apply_player_action(player, action, objects)
    assert "key" in new_player["inventory"]
    assert new_objects["key"]["state"]["held_by"] == "player"
    assert any("拾取" in e for e in events)


def test_allowed_interact_non_portable_marks_interacted():
    player = {"inventory": []}
    objects = {
        "lever": {"name": "拉杆", "state": {}, "properties": {}}
    }
    action = {
        "feasibility": "allowed",
        "action_type": "interact",
        "action_description": "拉动拉杆",
        "target_object_id": "lever",
    }
    _, new_objects, events = apply_player_action(player, action, objects)
    assert new_objects["lever"]["state"]["interacted_by_player"] is True


def test_allowed_use_item_consumes_from_inventory():
    player = {
        "position": {"x": 0, "y": 0, "z": 0},
        "inventory": ["potion"],
    }
    objects = {
        "potion": {"name": "药水", "state": {}, "properties": {"consumable": True}}
    }
    action = {
        "feasibility": "allowed",
        "action_type": "use_item",
        "action_description": "喝下药水",
        "target_object_id": "potion",
    }
    new_player, new_objects, events = apply_player_action(player, action, objects)
    assert "potion" not in new_player["inventory"]
    assert new_objects["potion"]["state"]["consumed"] is True


def test_allowed_speak_records_event():
    player = {"position": {"x": 0, "y": 0, "z": 0}, "inventory": []}
    action = {
        "feasibility": "allowed",
        "action_type": "speak",
        "action_description": "向管家打招呼",
        "speech_content": "你好，塞巴斯蒂安。",
    }
    _, _, events = apply_player_action(player, action, {})
    assert any("向管家打招呼" in e for e in events)


def test_uncertain_no_roll_records_pending():
    player = {"inventory": []}
    action = {
        "feasibility": "uncertain",
        "requires_roll": False,
        "success_probability": 0.6,
        "action_type": "interact",
        "action_description": "试着打开锁",
    }
    new_player, _, events = apply_player_action(player, action, {})
    assert new_player == player
    assert any("待定" in e for e in events)


# ── NPC action tests ──

def test_npc_interact_picks_up_portable():
    chars = {"npc1": {"name": "Bob", "inventory": []}}
    positions = {"npc1": {"x": 0, "y": 0, "z": 0}}
    objects = {"gem": {"name": "宝石", "state": {}, "properties": {"portable": True}}}
    intents = [{
        "character_id": "npc1",
        "action_type": "interact",
        "action_description": "捡起宝石",
        "target_object_id": "gem",
    }]
    new_chars, _, new_objs, events = apply_npc_actions(chars, positions, intents, objects)
    assert "gem" in new_chars["npc1"]["inventory"]
    assert new_objs["gem"]["state"]["held_by"] == "npc1"


def test_npc_use_item_consumes():
    chars = {"npc1": {"name": "Bob", "inventory": ["scroll"]}}
    positions = {"npc1": {"x": 0, "y": 0, "z": 0}}
    objects = {"scroll": {"name": "卷轴", "state": {}, "properties": {"consumable": True}}}
    intents = [{
        "character_id": "npc1",
        "action_type": "use_item",
        "action_description": "阅读卷轴",
        "target_object_id": "scroll",
    }]
    new_chars, _, new_objs, _ = apply_npc_actions(chars, positions, intents, objects)
    assert "scroll" not in new_chars["npc1"]["inventory"]
    assert new_objs["scroll"]["state"]["consumed"] is True


def test_npc_sets_current_action():
    chars = {"npc1": {"name": "Bob"}}
    positions = {"npc1": {"x": 0, "y": 0, "z": 0}}
    intents = [{
        "character_id": "npc1",
        "action_type": "wait",
        "action_description": "站在原地，警惕地环顾四周",
    }]
    new_chars, _, _, _ = apply_npc_actions(chars, positions, intents, {})
    assert "站在原地" in new_chars["npc1"]["current_action"]


# ── Emotion delta ──

class TestEmotionDelta:
    def test_friendly_emotion_positive(self):
        assert _emotion_delta("友好") > 0

    def test_hostile_emotion_negative(self):
        assert _emotion_delta("愤怒") < 0

    def test_neutral_emotion_zero(self):
        assert _emotion_delta("中性") == 0.0

    def test_empty_emotion_zero(self):
        assert _emotion_delta("") == 0.0
