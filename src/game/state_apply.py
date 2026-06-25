from __future__ import annotations

from copy import deepcopy
import random
from typing import Any


def _ensure_state_dict(obj: dict[str, Any]) -> None:
    if isinstance(obj.get("state"), str):
        obj["state"] = {"value": obj["state"]}
    elif obj.get("state") is None:
        obj["state"] = {}


def _copy_position(position: dict[str, Any]) -> dict[str, float]:
    return {
        "x": float(position.get("x", 0)),
        "y": float(position.get("y", 0)),
        "z": float(position.get("z", 0)),
    }


def _apply_allowed_player_action(
    player: dict[str, Any],
    player_action: dict[str, Any],
    objects: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    new_player = deepcopy(player)
    new_objects = deepcopy(objects)
    events: list[str] = []

    action_type = player_action.get("action_type")
    action_description = player_action.get("action_description", "")

    if action_type == "move":
        target_position = player_action.get("target_position")
        if target_position:
            new_player["position"] = _copy_position(target_position)
            events.append(f"[玩家状态] 玩家移动到 {new_player['position']}")

    elif action_type == "interact":
        obj_id = player_action.get("target_object_id")
        if obj_id and obj_id in new_objects:
            obj = new_objects[obj_id]
            _ensure_state_dict(obj)
            props = obj.get("properties", {})
            if props.get("portable"):
                inventory = list(new_player.get("inventory", []))
                if obj_id not in inventory:
                    inventory.append(obj_id)
                new_player["inventory"] = inventory
                obj["state"]["held_by"] = "player"
                events.append(f"[玩家状态] 玩家拾取了 {obj.get('name', obj_id)}")
            else:
                obj["state"]["interacted_by_player"] = True
                events.append(f"[玩家状态] 玩家与 {obj.get('name', obj_id)} 互动")

    elif action_type == "use_item":
        obj_id = player_action.get("target_object_id")
        if obj_id:
            new_player["last_used_item"] = obj_id
            if obj_id in new_objects:
                obj = new_objects[obj_id]
                props = obj.get("properties", {})
                if props.get("consumable"):
                    inventory = list(new_player.get("inventory", []))
                    if obj_id in inventory:
                        inventory.remove(obj_id)
                    new_player["inventory"] = inventory
                    _ensure_state_dict(obj)
                    obj["state"]["consumed"] = True
            events.append(f"[玩家状态] 玩家使用了 {obj_id}")

    elif action_description:
        events.append(f"[玩家状态] 玩家执行了：{action_description}")

    return new_player, new_objects, events


def apply_player_action(
    player: dict[str, Any],
    player_action: dict[str, Any] | None,
    objects: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    new_player = deepcopy(player)
    new_objects = deepcopy(objects)
    if not player_action:
        return new_player, new_objects, []

    feasibility = player_action.get("feasibility")
    action_description = player_action.get("action_description", "")
    reason = player_action.get("feasibility_reason") or "没有说明原因"

    if feasibility == "blocked":
        return new_player, new_objects, [f"[玩家行动被阻止] {action_description}：{reason}"]

    if feasibility == "uncertain":
        probability = float(player_action.get("success_probability") or 0.5)
        probability = max(0.0, min(1.0, probability))
        if player_action.get("requires_roll"):
            if random.random() < probability:
                allowed_action = {**player_action, "feasibility": "allowed"}
                rolled_player, rolled_objects, rolled_events = _apply_allowed_player_action(new_player, allowed_action, new_objects)
                return rolled_player, rolled_objects, [
                    f"[检定成功] {action_description}（成功概率: {probability:.0%}）",
                    *rolled_events,
                ]
            return new_player, new_objects, [f"[检定失败] {action_description}（成功概率: {probability:.0%}）"]
        return new_player, new_objects, [f"[玩家行动待定] {action_description}（成功概率: {probability:.0%}）"]

    if feasibility == "allowed" or feasibility is None:
        return _apply_allowed_player_action(new_player, player_action, new_objects)

    return new_player, new_objects, []


_POSITIVE_EMOTIONS = {"友好", "友善", "开心", "温柔", "感激", "关心", "热情", "温暖", "喜爱", "仰慕", "敬佩"}
_NEGATIVE_EMOTIONS = {"愤怒", "敌意", "厌恶", "冷漠", "嫉妒", "蔑视", "嘲讽", "不耐烦", "轻蔑", "怨恨"}


def _emotion_delta(emotion: str) -> float:
    em = str(emotion or "").strip()
    if any(p in em for p in _POSITIVE_EMOTIONS):
        return 0.05
    if any(n in em for n in _NEGATIVE_EMOTIONS):
        return -0.05
    return 0.0


def _npc_inventory_key(char: dict[str, Any]) -> str:
    return "inventory"


def apply_npc_actions(
    characters: dict[str, dict[str, Any]],
    character_positions: dict[str, dict[str, float]],
    action_intents: list[dict[str, Any]],
    objects: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, float]], dict[str, dict[str, Any]], list[str]]:
    new_characters: dict[str, dict[str, Any]] = {k: {**v} for k, v in characters.items() if isinstance(v, dict)}
    new_positions: dict[str, dict[str, float]] = {k: {**v} for k, v in character_positions.items()}
    new_objects: dict[str, dict[str, Any]] = {k: {**v} for k, v in objects.items()}
    events: list[str] = []

    for intent in action_intents:
        cid = intent.get("character_id", "")
        if not cid or cid not in new_characters:
            continue
        char = new_characters[cid]
        action_type = intent.get("action_type", "")
        action_description = intent.get("action_description", "")

        # ── Clear conversation target by default; speak re-sets it ──
        char.pop("conversation_target", None)

        char["current_action"] = action_description

        if action_type == "move":
            target_position = intent.get("target_position")
            if target_position:
                new_positions[cid] = {
                    "x": float(target_position.get("x", 0)),
                    "y": float(target_position.get("y", 0)),
                    "z": float(target_position.get("z", 0)),
                }
                events.append(f"[NPC状态] {char.get('name', cid)} 移动到 {new_positions[cid]}")

        elif action_type == "interact":
            obj_id = intent.get("target_object_id")
            if obj_id and obj_id in new_objects:
                obj = new_objects[obj_id]
                _ensure_state_dict(obj)
                props = obj.get("properties", {})
                if props.get("portable"):
                    inventory = list(char.get("inventory", []))
                    if obj_id not in inventory:
                        inventory.append(obj_id)
                    char["inventory"] = inventory
                    obj["state"]["held_by"] = cid
                    events.append(f"[NPC状态] {char.get('name', cid)} 拾取了 {obj.get('name', obj_id)}")
                else:
                    obj["state"]["interacted_by_npc"] = cid
                    events.append(f"[NPC状态] {char.get('name', cid)} 与 {obj.get('name', obj_id)} 互动")

            delta = _emotion_delta(intent.get("emotion", ""))
            if delta != 0.0:
                rels = char.setdefault("relationships", {})
                target_char = intent.get("target_character_id")
                if target_char:
                    prev = float(rels.get(target_char, 0.0))
                    rels[target_char] = max(-1.0, min(1.0, prev + delta))

        elif action_type == "speak":
            target_char = intent.get("target_character_id")
            if target_char:
                char["last_spoken_to"] = target_char
                char["conversation_target"] = target_char
                if target_char in new_characters:
                    new_characters[target_char]["conversation_target"] = cid
                    new_characters[target_char]["last_spoken_to"] = cid
                delta = _emotion_delta(intent.get("emotion", ""))
                if delta != 0.0:
                    rels = char.setdefault("relationships", {})
                    prev = float(rels.get(target_char, 0.0))
                    rels[target_char] = max(-1.0, min(1.0, prev + delta))

        elif action_type == "use_item":
            obj_id = intent.get("target_object_id")
            if obj_id:
                char["last_used_item"] = obj_id
                if obj_id in new_objects:
                    obj = new_objects[obj_id]
                    props = obj.get("properties", {})
                    if props.get("consumable"):
                        inventory = list(char.get("inventory", []))
                        if obj_id in inventory:
                            inventory.remove(obj_id)
                        char["inventory"] = inventory
                        _ensure_state_dict(obj)
                        obj["state"]["consumed"] = True
                events.append(f"[NPC状态] {char.get('name', cid)} 使用了 {obj_id}")

        elif action_description:
            events.append(f"[NPC状态] {char.get('name', cid)}：{action_description}")

    return new_characters, new_positions, new_objects, events


def compact_event_log(event_log: list[str], max_events: int = 100, keep_recent: int = 50) -> list[str]:
    if len(event_log) <= max_events:
        return event_log

    old = event_log[:len(event_log) - keep_recent]
    recent = event_log[-keep_recent:]

    important = [e for e in old if any(tag in e for tag in (
        "[系统]", "[检定成功]", "[检定失败]", "[玩家行动被阻止]",
        "[警告]", "[错误]",
    ))]

    char_count = sum(1 for e in old if "[角色]" in e)
    physics_count = sum(1 for e in old if "[物理]" in e)
    player_count = sum(1 for e in old if "[玩家" in e)
    npc_count = sum(1 for e in old if "[NPC状态]" in e)
    total_old = len(old)

    summary = (
        f"[摘要] 前 {total_old} 条事件："
        f"角色对话 {char_count} 次，物理变化 {physics_count} 次，"
        f"玩家行动 {player_count} 次，NPC状态 {npc_count} 次。"
    )

    return [summary, *important[-20:], *recent]
