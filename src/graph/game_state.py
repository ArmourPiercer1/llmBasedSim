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

    action_intents: Annotated[list[dict[str, Any]], operator.add]
    physics_outcomes: list[dict[str, Any]]
    player_percept: dict[str, Any] | None
    player_input: str | None
    player_action: dict[str, Any] | None

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
        "action_intents": data.get("action_intents", []) or [],
        "physics_outcomes": data.get("physics_outcomes", []) or [],
        "player_percept": data.get("player_percept"),
        "player_input": data.get("player_input"),
        "player_action": data.get("player_action"),
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
    return next_state
