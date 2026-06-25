from __future__ import annotations

from typing import Any

STRENGTH_TO_KG_FACTOR = 50.0


def _text_matches_rule(text: str, rule: str) -> bool:
    if not text or not rule:
        return False
    normalized_text = text.lower()
    normalized_rule = rule.lower()
    if normalized_rule in normalized_text:
        return True
    parts = [part.strip() for part in normalized_rule.replace("，", ",").replace("、", ",").split(",")]
    if any(part and part in normalized_text for part in parts):
        return True
    keywords = [
        token for token in (
            "道歉", "感谢", "不会跳舞", "秘密通道", "暗门", "命令", "仆人",
            "开锁", "门锁", "撬锁", "推", "搬", "拿起", "穿过", "通过",
        )
        if token in normalized_rule
    ]
    return bool(keywords) and any(token in normalized_text for token in keywords)


def _action_text(player_action: dict[str, Any]) -> str:
    return "\n".join(
        str(player_action.get(key, ""))
        for key in ("raw_input", "interpreted_intent", "action_description", "speech_content")
        if player_action.get(key)
    )


def _target_object(player_action: dict[str, Any], objects: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    obj_id = player_action.get("target_object_id")
    if obj_id and obj_id in objects:
        return objects[obj_id]
    text = _action_text(player_action)
    for obj in objects.values():
        if not isinstance(obj, dict):
            continue
        name = obj.get("name", "")
        object_id = obj.get("object_id") or obj.get("id", "")
        if (name and name in text) or (object_id and object_id in text):
            return obj
    return None


def _target_width(player_action: dict[str, Any], objects: dict[str, dict[str, Any]], locations: dict[str, dict[str, Any]]) -> float | None:
    target = _target_object(player_action, objects)
    if target:
        props = target.get("properties", {}) if isinstance(target, dict) else {}
        width = props.get("effective_width_cm", props.get("width_cm"))
        if width is not None:
            return float(width)

    text = _action_text(player_action)
    for loc in locations.values():
        if not isinstance(loc, dict):
            continue
        loc_id = loc.get("id", "")
        loc_name = loc.get("name", "")
        if (loc_id and loc_id in text) or (loc_name and loc_name in text):
            props = loc.get("properties", {})
            width = props.get("effective_width_cm", props.get("width_cm"))
            if width is not None:
                return float(width)
    return None


def _rule_result(
    feasibility: str,
    reason: str,
    matched_rule: str,
    success_probability: float | None = None,
    requires_roll: bool = False,
) -> dict[str, Any]:
    return {
        "feasibility": feasibility,
        "feasibility_reason": reason,
        "success_probability": success_probability,
        "requires_roll": requires_roll,
        "matched_rule": matched_rule,
    }


def check_action_feasibility(
    player_action: dict[str, Any],
    player: dict[str, Any],
    objects: dict[str, dict[str, Any]],
    locations: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    action_text = _action_text(player_action)
    capabilities = player.get("capabilities", {}) if isinstance(player, dict) else {}

    for rule in capabilities.get("blocked_common_actions", []) or []:
        if _text_matches_rule(action_text, str(rule)):
            return _rule_result(
                "blocked",
                f"系统规则预判：玩家人设限制不允许执行该行动（{rule}）。",
                "blocked_common",
            )

    for rule in capabilities.get("allowed_extraordinary_actions", []) or []:
        if _text_matches_rule(action_text, str(rule)):
            return _rule_result(
                "allowed",
                f"系统规则预判：玩家具备可执行该行动的特殊能力（{rule}）。",
                "extraordinary",
            )

    target = _target_object(player_action, objects)
    action_type = player_action.get("action_type")

    if action_type == "interact" and target:
        props = target.get("properties", {})
        weight = props.get("weight_kg")
        if weight is not None:
            strength = (player.get("physical_profile", {}) or {}).get("strength")
            if strength is not None:
                capacity = float(strength) * STRENGTH_TO_KG_FACTOR
                weight_value = float(weight)
                if capacity < weight_value:
                    return _rule_result(
                        "blocked",
                        f"系统规则预判：玩家力量约可移动 {capacity:.1f}kg，但目标物体重约 {weight_value:.1f}kg。",
                        "strength_vs_weight",
                    )
                if capacity < weight_value * 1.5:
                    return _rule_result(
                        "uncertain",
                        f"系统规则预判：玩家力量接近目标物体重量，行动可能成功但不稳定。",
                        "strength_vs_weight",
                        success_probability=max(0.1, min(0.9, capacity / (weight_value * 1.5))),
                        requires_roll=True,
                    )

        lock_difficulty = props.get("lock_difficulty")
        if lock_difficulty is not None:
            skill = float((capabilities.get("skill_levels", {}) or {}).get("lockpicking", 0.0))
            difficulty = float(lock_difficulty)
            if skill < difficulty:
                probability = max(0.05, min(0.95, skill / difficulty if difficulty else 0.05))
                return _rule_result(
                    "uncertain",
                    f"系统规则预判：开锁技能 {skill:.2f} 低于锁难度 {difficulty:.2f}。",
                    "skill_vs_lock",
                    success_probability=probability,
                    requires_roll=True,
                )
            return _rule_result(
                "allowed",
                f"系统规则预判：开锁技能 {skill:.2f} 不低于锁难度 {difficulty:.2f}。",
                "skill_vs_lock",
            )

    if action_type == "move":
        width = _target_width(player_action, objects, locations)
        body_width = (player.get("physical_profile", {}) or {}).get("body_width_cm")
        if width is not None and body_width is not None:
            body_width_value = float(body_width)
            if body_width_value > width:
                return _rule_result(
                    "blocked",
                    f"系统规则预判：玩家身体宽度 {body_width_value:.1f}cm 大于通道宽度 {width:.1f}cm。",
                    "body_width_vs_passage",
                )
            return _rule_result(
                "allowed",
                f"系统规则预判：玩家身体宽度 {body_width_value:.1f}cm 可以通过宽度 {width:.1f}cm 的空间。",
                "body_width_vs_passage",
            )

    return None
