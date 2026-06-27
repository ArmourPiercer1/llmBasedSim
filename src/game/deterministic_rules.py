from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


VALID_FEASIBILITIES = {"allowed", "blocked", "uncertain"}


@dataclass(frozen=True)
class DeterministicRule:
    id: str
    description: str
    match_pattern: re.Pattern[str] | None
    condition: str | None
    feasibility: str | None
    probability: float | None


def parse_deterministic_rules(config: Any) -> tuple[set[int], list[DeterministicRule], list[str]]:
    warnings: list[str] = []
    if config is None:
        return set(), [], warnings
    if not isinstance(config, dict):
        return set(), [], [f"deterministic rules config must be a dict, got {type(config).__name__}"]

    disabled = _parse_disabled(config.get("disable"), warnings)
    rules = _parse_rules(config.get("append"), warnings)
    return disabled, rules, warnings


def _parse_disabled(value: Any, warnings: list[str]) -> set[int]:
    if value is None:
        return set()
    if not isinstance(value, list):
        warnings.append(f"deterministic.disable must be a list, got {type(value).__name__}")
        return set()

    disabled: set[int] = set()
    for item in value:
        try:
            index = int(item)
        except (TypeError, ValueError):
            warnings.append(f"deterministic.disable item {item!r} is not an integer")
            continue
        if not 1 <= index <= 5:
            warnings.append(f"deterministic.disable index {index} is out of range 1-5")
            continue
        disabled.add(index)
    return disabled


def _parse_rules(value: Any, warnings: list[str]) -> list[DeterministicRule]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(f"deterministic.append must be a list, got {type(value).__name__}")
        return []

    rules: list[DeterministicRule] = []
    seen_ids: set[str] = set()
    for item in value:
        rule = _parse_rule(item, seen_ids, warnings)
        if rule is not None:
            seen_ids.add(rule.id)
            rules.append(rule)
    return rules


def _parse_rule(item: Any, seen_ids: set[str], warnings: list[str]) -> DeterministicRule | None:
    if not isinstance(item, dict):
        warnings.append(f"deterministic.append item {item!r} is not a dict")
        return None

    rule_id = str(item.get("id", "")).strip()
    if not rule_id:
        warnings.append("deterministic rule missing id")
        return None
    if rule_id in seen_ids:
        warnings.append(f"deterministic rule id {rule_id!r} is duplicated")
        return None

    description = str(item.get("description", "")).strip()
    if not description:
        warnings.append(f"deterministic rule {rule_id!r} missing description")
        return None

    match_pattern = _parse_match_pattern(rule_id, item.get("match_action"), warnings)
    if item.get("match_action") is not None and match_pattern is None:
        return None

    condition = _parse_condition(rule_id, item.get("condition"), warnings)
    if item.get("condition") is not None and condition is None:
        return None

    if match_pattern is None and condition is None:
        warnings.append(f"deterministic rule {rule_id!r} must define match_action or condition")
        return None

    feasibility: str | None = None
    probability: float | None = None
    if condition is None:
        feasibility = str(item.get("feasibility", "")).strip().lower()
        if feasibility not in VALID_FEASIBILITIES:
            warnings.append(f"deterministic rule {rule_id!r} has invalid feasibility {feasibility!r}")
            return None
        probability = _parse_probability(rule_id, feasibility, item.get("probability"), warnings)
        if feasibility == "uncertain" and probability is None:
            return None

    return DeterministicRule(
        id=rule_id,
        description=description,
        match_pattern=match_pattern,
        condition=condition,
        feasibility=feasibility,
        probability=probability,
    )


def _parse_match_pattern(rule_id: str, value: Any, warnings: list[str]) -> re.Pattern[str] | None:
    if value is None:
        return None
    pattern = str(value).strip()
    if not pattern:
        warnings.append(f"deterministic rule {rule_id!r} has empty match_action")
        return None
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        warnings.append(f"deterministic rule {rule_id!r} has invalid regex: {exc}")
        return None


def _parse_condition(rule_id: str, value: Any, warnings: list[str]) -> str | None:
    if value is None:
        return None
    condition = str(value).strip()
    if not condition:
        warnings.append(f"deterministic rule {rule_id!r} has empty condition")
        return None
    if not condition.startswith("if(") or not condition.endswith(")"):
        warnings.append(f"deterministic rule {rule_id!r} condition must be if(...)")
        return None
    return condition


def _parse_probability(rule_id: str, feasibility: str, value: Any, warnings: list[str]) -> float | None:
    if feasibility != "uncertain":
        return None
    if value is None:
        warnings.append(f"deterministic rule {rule_id!r} with uncertain feasibility needs probability")
        return None
    try:
        probability = float(value)
    except (TypeError, ValueError):
        warnings.append(f"deterministic rule {rule_id!r} has invalid probability {value!r}")
        return None
    if not 0 < probability < 1:
        warnings.append(f"deterministic rule {rule_id!r} probability must be between 0 and 1")
        return None
    return probability
