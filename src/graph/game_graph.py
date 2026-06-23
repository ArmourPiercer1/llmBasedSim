"""Build and compile the LangGraph StateGraph for the game simulation."""

import asyncio
import math
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from src.graph.game_state import GameState
from src.llm.parser import generate_structured
from src.models.events import ActionIntent, PhysicsResolution, PlayerAction, PlayerPercept
from src.prompts.loader import PromptLoader


def _distance(pos1: dict, pos2: dict) -> float:
    dx = pos1.get("x", 0) - pos2.get("x", 0)
    dy = pos1.get("y", 0) - pos2.get("y", 0)
    dz = pos1.get("z", 0) - pos2.get("z", 0)
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _find_nearby_objects(state: GameState, position: dict | None, radius: float) -> list[dict]:
    objects = state.get("objects", {})
    if not position:
        return list(objects.values())
    result = []
    for obj in objects.values():
        obj_pos = obj.get("position", {}) if isinstance(obj, dict) else {}
        if _distance(position, obj_pos) <= radius:
            result.append(obj)
    return result


def _find_nearby_chars(state: GameState, char_id: str, radius: float) -> list[dict]:
    character_positions = state.get("character_positions", {})
    ref_pos = character_positions.get(char_id)
    if not ref_pos:
        return []
    result = []
    for cid, char in state.get("characters", {}).items():
        if cid == char_id:
            continue
        char_pos = character_positions.get(cid)
        if char_pos and _distance(ref_pos, char_pos) <= radius:
            result.append(char)
    return result


def _find_nearby_chars_by_pos(state: GameState, position: dict, radius: float) -> list[dict]:
    result = []
    character_positions = state.get("character_positions", {})
    for cid, char in state.get("characters", {}).items():
        char_pos = character_positions.get(cid)
        if char_pos and _distance(position, char_pos) <= radius:
            result.append(char)
    return result


def _find_location(state: GameState, char_id: str) -> dict | None:
    pos = state.get("character_positions", {}).get(char_id)
    if not pos:
        return None
    objects = state.get("objects", {})
    for loc in state.get("locations", {}).values():
        for obj_id in loc.get("objects", []):
            obj = objects.get(obj_id)
            if obj and _distance(pos, obj.get("position", {})) < 30:
                return loc
    return next(iter(state.get("locations", {}).values()), None)


def _add_positions(p1: dict, p2: dict) -> dict:
    return {
        "x": p1.get("x", 0) + p2.get("x", 0),
        "y": p1.get("y", 0) + p2.get("y", 0),
        "z": p1.get("z", 0) + p2.get("z", 0),
    }


def build_game_graph(
    llm: ChatOpenAI,
    prompt_loader: PromptLoader,
    checkpointer: InMemorySaver | None = None,
):
    """Build and compile the game simulation StateGraph."""

    # ── Node: player_intent_process ──

    async def player_intent_process(state: GameState) -> dict[str, Any]:
        player_input = state.get("player_input")
        if not player_input:
            return {"player_action": None}

        player = state.get("player", {})
        system_prompt = prompt_loader.render("player_intent_system.j2", {})
        user_prompt = prompt_loader.render("player_intent_user.j2", {
            "player_input": player_input,
            "player": player,
            "characters": state.get("characters", {}),
            "objects": state.get("objects", {}),
            "locations": state.get("locations", {}),
            "environment": state.get("environment", {}),
            "recent_events": state.get("event_log", [])[-10:],
        })

        action = await generate_structured(llm, [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ], PlayerAction)
        action.raw_input = player_input

        return {
            "player_action": action.model_dump(),
            "event_log": [f"[玩家意图] {action.action_description or action.interpreted_intent}"],
        }

    # ── Node: player_action_resolve ──

    async def player_action_resolve(state: GameState) -> dict[str, Any]:
        player_action = state.get("player_action")
        if not player_action:
            return {}

        player = state.get("player", {})
        system_prompt = prompt_loader.render("player_action_resolve_system.j2", {})
        user_prompt = prompt_loader.render("player_action_resolve_user.j2", {
            "player_action": player_action,
            "capabilities": player.get("capabilities", {}) if isinstance(player, dict) else {},
            "physical_profile": player.get("physical_profile", {}) if isinstance(player, dict) else {},
            "objects": state.get("objects", {}),
            "locations": state.get("locations", {}),
            "environment": state.get("environment", {}),
        })

        resolved = await generate_structured(llm, [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ], PlayerAction)

        event = f"[玩家行动] {resolved.action_description}"
        if resolved.feasibility:
            event += f"（{resolved.feasibility}: {resolved.feasibility_reason or '无说明'}）"

        return {
            "player_action": resolved.model_dump(),
            "event_log": [event],
        }

    # ── Node: characters_all_decide ──

    async def _decide_one_char(
        state: GameState, char_id: str
    ) -> tuple[dict | None, str | None]:
        char = state.get("characters", {}).get(char_id)
        if not char:
            return None, None

        char_pos = state.get("character_positions", {}).get(char_id, {"x": 0, "y": 0, "z": 0})
        current_location = _find_location(state, char_id)
        nearby_objects = _find_nearby_objects(state, char_pos, radius=20.0)
        nearby_chars_list = _find_nearby_chars(state, char_id, radius=20.0)

        system_prompt = prompt_loader.render("character_system.j2", {
            "name": char.get("name", char_id),
            "personality": char.get("personality", {}),
            "memory": char.get("memory", [])[-20:],
        })
        user_prompt = prompt_loader.render("character_user.j2", {
            "environment": state.get("environment", {}),
            "current_location": current_location or {},
            "nearby_objects": nearby_objects,
            "nearby_chars": nearby_chars_list,
            "char_position": char_pos,
            "inventory": char.get("inventory", []),
            "player_action": state.get("player_action"),
        })

        intent = await generate_structured(llm, [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ], ActionIntent)
        intent.character_id = char_id

        return (
            intent.model_dump(),
            f"[角色] {char.get('name', char_id)}: {intent.action_description}",
        )

    async def characters_all_decide(state: GameState) -> dict[str, Any]:
        char_ids = list(state.get("characters", {}).keys())
        if not char_ids:
            return {"action_intents": [], "event_log": []}

        results = await asyncio.gather(*(_decide_one_char(state, cid) for cid in char_ids))
        all_intents = [intent for intent, _ in results if intent]
        all_events = [event for _, event in results if event]

        return {
            "action_intents": all_intents,
            "event_log": all_events,
        }

    # ── Node: physics_resolve ──

    async def physics_resolve(state: GameState) -> dict[str, Any]:
        system_prompt = prompt_loader.render("physics_system.j2", {})
        user_prompt = prompt_loader.render("physics_user.j2", {
            "objects": state.get("objects", {}),
            "character_positions": state.get("character_positions", {}),
            "action_intents": state.get("action_intents", []),
            "player_action": state.get("player_action"),
            "environment": state.get("environment", {}),
        })

        resolution = await generate_structured(llm, [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ], PhysicsResolution)

        outcomes = [o.model_dump() for o in resolution.outcomes]
        return {
            "physics_outcomes": outcomes,
            "event_log": [f"[物理] {o.get('description', '')}" for o in outcomes],
        }

    # ── Node: state_apply (deterministic, no LLM) ──

    def state_apply(state: GameState) -> dict[str, Any]:
        new_positions = dict(state.get("character_positions", {}))
        new_objects = {
            k: {**v} if isinstance(v, dict) else v
            for k, v in state.get("objects", {}).items()
        }
        new_chars = {
            k: {**v} if isinstance(v, dict) else v
            for k, v in state.get("characters", {}).items()
        }

        def _ensure_state_dict(o: dict) -> None:
            if isinstance(o.get("state"), str):
                o["state"] = {"value": o["state"]}

        for outcome in state.get("physics_outcomes", []):
            outcome_type = outcome.get("outcome_type", "")
            obj_id = outcome.get("subject_object_id")

            if outcome_type == "movement" and obj_id and obj_id in new_objects:
                obj = new_objects[obj_id]
                if isinstance(obj, dict):
                    old_pos = obj.get("position", {"x": 0, "y": 0, "z": 0})
                    delta = outcome.get("position_delta")
                    if delta:
                        obj["position"] = _add_positions(old_pos, delta)

            elif outcome_type == "destruction" and obj_id and obj_id in new_objects:
                obj = new_objects[obj_id]
                if isinstance(obj, dict):
                    _ensure_state_dict(obj)
                    obj["state"]["broken"] = True
                    ns = outcome.get("new_state")
                    if ns:
                        obj["state"].update(ns)

            elif outcome_type == "state_change" and obj_id and obj_id in new_objects:
                obj = new_objects[obj_id]
                if isinstance(obj, dict):
                    _ensure_state_dict(obj)
                    ns = outcome.get("new_state")
                    if ns:
                        obj["state"].update(ns)

        recent = state.get("event_log", [])[-10:]
        for cid in new_chars:
            char = new_chars[cid]
            if isinstance(char, dict):
                mem = list(char.get("memory", []))
                mem.extend(recent)
                if len(mem) > 50:
                    mem = mem[-50:]
                char["memory"] = mem

        return {
            "character_positions": new_positions,
            "objects": new_objects,
            "characters": new_chars,
            "tick": state.get("tick", 0) + 1,
            "action_intents": [],
            "physics_outcomes": [],
            "player_input": None,
        }

    # ── Node: sensory_filter ──

    async def sensory_filter(state: GameState) -> dict[str, Any]:
        player = state.get("player", {})
        player_pos = player.get("position") if isinstance(player, dict) else None
        if not player_pos:
            player_pos = {"x": 0, "y": 0, "z": 0}

        capabilities = player.get("capabilities", {}) if isinstance(player, dict) else {}
        sight_range = capabilities.get("sight_range_m", 50) if capabilities else 50

        nearby_objects = _find_nearby_objects(state, player_pos, radius=sight_range)
        nearby_chars = _find_nearby_chars_by_pos(state, player_pos, radius=sight_range)

        # Build self-action summary deterministically from player_action
        player_action = state.get("player_action") or {}
        self_action_parts = []
        if player_action:
            if player_action.get("subconscious_adjustment"):
                self_action_parts.append(f"[内心] {player_action['subconscious_adjustment']}")
            act_desc = player_action.get("action_description", "")
            speech = player_action.get("speech_content", "")
            feasibility = player_action.get("feasibility", "")
            feasibility_reason = player_action.get("feasibility_reason", "")

            if act_desc:
                if feasibility == "blocked":
                    self_action_parts.append(f"你试图{act_desc}，但未能成功：{feasibility_reason or '当前的状况不允许'}")
                else:
                    self_action_parts.append(f"你{act_desc}")
            if speech:
                self_action_parts.append(f"你说：\"{speech}\"")
        self_action_summary = "\n".join(self_action_parts) if self_action_parts else ""

        system_prompt = prompt_loader.render("sensory_system.j2", {
            "player_capabilities": capabilities,
        })
        user_prompt = prompt_loader.render("sensory_user.j2", {
            "player_position": player_pos,
            "player_action": player_action,
            "self_action_summary": self_action_summary,
            "nearby_objects": nearby_objects,
            "nearby_chars": nearby_chars,
            "recent_events": state.get("event_log", [])[-10:],
            "environment": state.get("environment", {}),
        })

        percept = await generate_structured(llm, [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ], PlayerPercept)
        percept.self_action_summary = self_action_summary

        return {"player_percept": percept.model_dump()}

    # ── Build the graph ──

    builder = StateGraph(GameState)

    builder.add_node("player_intent_process", player_intent_process)
    builder.add_node("player_action_resolve", player_action_resolve)
    builder.add_node("characters_all_decide", characters_all_decide)
    builder.add_node("physics_resolve", physics_resolve)
    builder.add_node("state_apply", state_apply)
    builder.add_node("sensory_filter", sensory_filter)

    builder.add_edge(START, "player_intent_process")
    builder.add_edge("player_intent_process", "player_action_resolve")
    builder.add_edge("player_action_resolve", "characters_all_decide")
    builder.add_edge("characters_all_decide", "physics_resolve")
    builder.add_edge("physics_resolve", "state_apply")
    builder.add_edge("state_apply", "sensory_filter")
    builder.add_edge("sensory_filter", END)

    if checkpointer is None:
        checkpointer = InMemorySaver()
    return builder.compile(checkpointer=checkpointer)
