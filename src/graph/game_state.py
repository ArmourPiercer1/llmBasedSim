import operator
from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import BaseModel
from typing_extensions import TypedDict


class GameState(TypedDict, total=False):
    tick: int
    max_ticks: int
    game_phase: str

    world_name: str
    world_description: str
    locations: dict[str, Any]
    objects: dict[str, Any]
    character_positions: dict[str, dict[str, Any]]
    environment: dict[str, Any]

    characters: dict[str, Any]
    player: dict[str, Any]
    world_rules: dict[str, Any]
    narrative_style: dict[str, str]

    action_intents: Annotated[list[dict[str, Any]], operator.add]
    physics_outcomes: list[dict[str, Any]]
    player_percept: dict[str, Any] | None
    player_input: str | None
    player_action: dict[str, Any] | None
    action_continuation: dict[str, Any] | None

    game_time: dict[str, int]
    ticks_per_game_minute: float
    tick_duration_minutes: float

    event_log: Annotated[list[str], operator.add]


def _plain(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def normalize_state(raw: Mapping[str, Any] | BaseModel) -> GameState:
    data = _plain(raw)
    if not isinstance(data, Mapping):
        data = {}

    return {
        "tick": int(data.get("tick", 0)),
        "max_ticks": int(data.get("max_ticks", 100)),
        "game_phase": data.get("game_phase", "init"),
        "world_name": data.get("world_name", ""),
        "world_description": data.get("world_description", ""),
        "locations": data.get("locations", {}) or {},
        "objects": data.get("objects", {}) or {},
        "character_positions": data.get("character_positions", {}) or {},
        "environment": data.get("environment", {}) or {},
        "characters": data.get("characters", {}) or {},
        "player": data.get("player", {}) or {},
        "world_rules": data.get("world_rules", {}) or {},
        "narrative_style": data.get("narrative_style", {}) or {},
        "action_intents": data.get("action_intents", []) or [],
        "physics_outcomes": data.get("physics_outcomes", []) or [],
        "player_percept": data.get("player_percept"),
        "player_input": data.get("player_input"),
        "player_action": data.get("player_action"),
        "action_continuation": data.get("action_continuation"),
        "game_time": data.get("game_time", {"hour": 18, "minute": 0}),
        "ticks_per_game_minute": float(data.get("ticks_per_game_minute", 0.2)),
        "tick_duration_minutes": float(data.get("tick_duration_minutes", 0.0)),
        "event_log": data.get("event_log", []) or [],
    }


def make_initial_state(**values: Any) -> GameState:
    return normalize_state(values)


def reset_tick_transients(state: Mapping[str, Any], player_input: str | None) -> GameState:
    next_state = normalize_state(state)
    next_state["player_input"] = player_input
    next_state["player_action"] = None
    next_state["player_percept"] = None
    next_state["action_intents"] = []
    next_state["physics_outcomes"] = []
    next_state["tick_duration_minutes"] = 0.0
    return next_state


def advance_game_time(current: dict[str, Any] | None, minutes_to_add: float) -> dict[str, int]:
    c = current or {"hour": 18, "minute": 0}
    total = int(c.get("hour", 18)) * 60 + int(c.get("minute", 0)) + max(0.05, minutes_to_add)
    total = total % (24 * 60)
    return {"hour": int(total // 60), "minute": int(total % 60)}


def time_of_day_from_hour(hour: int) -> str:
    if 5 <= hour < 8:
        return "清晨"
    if 8 <= hour < 12:
        return "上午"
    if 12 <= hour < 14:
        return "中午"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 20:
        return "傍晚"
    if 20 <= hour < 24:
        return "夜晚"
    return "深夜"


def strip_transient_state(state: Mapping[str, Any]) -> dict[str, Any]:
    transient = {"player_input", "player_action", "action_intents", "physics_outcomes", "tick_duration_minutes"}
    normalized = normalize_state(state)
    return {k: v for k, v in normalized.items() if k not in transient}
