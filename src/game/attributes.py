from __future__ import annotations

from copy import deepcopy
from typing import Any


def _clamp(value: float, attr: dict[str, Any]) -> float:
    minimum = attr.get("min")
    maximum = attr.get("max")
    if minimum is not None:
        value = max(float(minimum), value)
    if maximum is not None:
        value = min(float(maximum), value)
    return value


def _attribute_name(key: str, attr: dict[str, Any]) -> str:
    return str(attr.get("name") or key)


def _apply_delta(attr: dict[str, Any], delta: float) -> tuple[dict[str, Any], float, float] | None:
    if attr.get("locked"):
        return None
    current = float(attr.get("value", 0.0))
    updated = _clamp(current + delta, attr)
    new_attr = {**attr, "value": updated}
    return new_attr, current, updated


def _normalize_attributes(entity: dict[str, Any]) -> dict[str, dict[str, Any]]:
    attrs = entity.get("attributes", {}) if isinstance(entity, dict) else {}
    if not isinstance(attrs, dict):
        return {}
    normalized = {}
    for key, value in attrs.items():
        if isinstance(value, dict):
            normalized[str(key)] = {**value}
        else:
            normalized[str(key)] = {"name": str(key), "value": float(value)}
    return normalized


def apply_natural_attribute_deltas(
    player: dict[str, Any],
    characters: dict[str, dict[str, Any]],
    tick_duration_minutes: float = 5.0,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    new_player = deepcopy(player)
    new_characters = deepcopy(characters)
    events: list[str] = []

    def apply_for_entity(entity: dict[str, Any], label: str) -> None:
        attrs = _normalize_attributes(entity)
        for key, attr in attrs.items():
            delta = float(attr.get("natural_delta_per_minute") or 0.0) * tick_duration_minutes
            if delta == 0.0:
                continue
            applied = _apply_delta(attr, delta)
            if not applied:
                continue
            new_attr, old, new = applied
            attrs[key] = new_attr
            if old != new:
                events.append(f"[属性] {label}的{_attribute_name(key, attr)}自然变化 {old:g} → {new:g}")
        entity["attributes"] = attrs

    apply_for_entity(new_player, new_player.get("name", "玩家"))
    for cid, char in new_characters.items():
        if isinstance(char, dict):
            apply_for_entity(char, char.get("name", cid))

    return new_player, new_characters, events


def apply_attribute_changes(
    player: dict[str, Any],
    characters: dict[str, dict[str, Any]],
    changes: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    new_player = deepcopy(player)
    new_characters = deepcopy(characters)
    events: list[str] = []

    for change in changes:
        entity_type = change.get("entity_type")
        entity_id = str(change.get("entity_id") or "")
        attr_key = str(change.get("attribute_key") or "")
        if not attr_key:
            continue

        if entity_type == "player":
            entity = new_player
            label = new_player.get("name", "玩家")
        elif entity_type == "character" and entity_id in new_characters:
            entity = new_characters[entity_id]
            label = entity.get("name", entity_id)
        else:
            continue

        attrs = _normalize_attributes(entity)
        if attr_key not in attrs:
            events.append(f"[警告] 属性更新忽略了不存在的属性：{entity_id or entity_type}.{attr_key}")
            entity["attributes"] = attrs
            continue

        attr = attrs[attr_key]
        applied = _apply_delta(attr, float(change.get("delta") or 0.0))
        if not applied:
            entity["attributes"] = attrs
            continue
        new_attr, old, new = applied
        attrs[attr_key] = new_attr
        entity["attributes"] = attrs
        if old != new:
            reason = str(change.get("reason") or "属性事件")
            events.append(f"[属性] {label}的{_attribute_name(attr_key, attr)} {old:g} → {new:g}（{reason}）")

    return new_player, new_characters, events


def summarize_attributes_for_prompt(
    player: dict[str, Any],
    characters: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    def summarize_entity(entity: dict[str, Any]) -> dict[str, Any]:
        attrs = _normalize_attributes(entity)
        result = {}
        for key, attr in attrs.items():
            if attr.get("locked"):
                continue
            result[key] = {
                "name": attr.get("name") or key,
                "value": attr.get("value", 0.0),
                "min": attr.get("min"),
                "max": attr.get("max"),
                "natural_delta_per_minute": attr.get("natural_delta_per_minute", 0.0),
                "description": attr.get("description", ""),
                "hidden": bool(attr.get("hidden", False)),
            }
        return result

    return {
        "player": {
            "entity_id": str(player.get("player_id", "player_1")),
            "name": player.get("name", "玩家"),
            "attributes": summarize_entity(player),
        },
        "characters": {
            cid: {
                "entity_id": cid,
                "name": char.get("name", cid),
                "attributes": summarize_entity(char),
            }
            for cid, char in characters.items()
            if isinstance(char, dict)
        },
    }


def visible_player_attributes(player: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        key: attr
        for key, attr in _normalize_attributes(player).items()
        if not attr.get("hidden")
    }
