"""Build and compile the LangGraph StateGraph for the game simulation."""

import asyncio
import math
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from src.game.attributes import (
    apply_attribute_changes,
    apply_natural_attribute_deltas,
    summarize_attributes_for_prompt,
    visible_player_attributes,
)
from src.graph.game_state import GameState, advance_game_time, time_of_day_from_hour
from src.game.rules import check_action_feasibility
from src.game.state_apply import apply_npc_actions, apply_player_action, compact_event_log
from src.llm.parser import generate_structured
from src.models.events import (
    ActionIntent,
    AttributeUpdateResolution,
    PhysicsResolution,
    PlayerAction,
    PlayerPercept,
)
from src.prompts.loader import (
    ATTRIBUTE_DEFAULT_REFERENCES,
    ATTRIBUTE_DEFAULT_RULES,
    PHYSICS_DEFAULT_RULES,
    PromptLoader,
    build_rules_context,
)
from src.ui.status import TurnStatus


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
    status: TurnStatus | None = None,
    checkpointer: InMemorySaver | None = None,
):
    """Build and compile the game simulation StateGraph."""

    # ── Node: player_intent_process ──

    async def player_intent_process(state: GameState) -> dict[str, Any]:
        player_input = state.get("player_input")
        continuation = state.get("action_continuation")

        if continuation and (not player_input or player_input.strip().lower() != "/stop"):
            if status:
                status.update("正在延续上一轮行动...")
            return {"player_action": continuation, "action_continuation": continuation, "event_log": []}

        if continuation and player_input and player_input.strip().lower() == "/stop":
            return {"player_action": None, "action_continuation": None, "event_log": ["[系统] 行动已终止。"]}

        if not player_input:
            if status:
                status.update("本轮无玩家输入，跳过意图解析")
            return {"player_action": None}

        player = state.get("player", {})
        try:
            if status:
                status.update("正在理解你的意图...")
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
        except Exception:
            return {
                "player_action": None,
                "event_log": ["[错误] 玩家输入处理失败，本轮输入被忽略。"],
            }

    # ── Node: player_action_resolve ──

    async def player_action_resolve(state: GameState) -> dict[str, Any]:
        player_action = state.get("player_action")
        if not player_action:
            if status:
                status.update("无玩家行动，跳过可行性判断")
            return {}

        player = state.get("player", {})
        try:
            if status:
                status.update("正在预判行动可行性...")
            rule_result = check_action_feasibility(
                player_action,
                player if isinstance(player, dict) else {},
                state.get("objects", {}),
                state.get("locations", {}),
            )
            system_prompt = prompt_loader.render("player_action_resolve_system.j2", {})
            user_prompt = prompt_loader.render("player_action_resolve_user.j2", {
                "player_action": player_action,
                "rule_result": rule_result,
                "capabilities": player.get("capabilities", {}) if isinstance(player, dict) else {},
                "physical_profile": player.get("physical_profile", {}) if isinstance(player, dict) else {},
                "attributes": player.get("attributes", {}) if isinstance(player, dict) else {},
                "objects": state.get("objects", {}),
                "locations": state.get("locations", {}),
                "environment": state.get("environment", {}),
            })

            if status:
                status.update("正在综合判断行动可行性...")
            resolved = await generate_structured(llm, [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ], PlayerAction)

            if rule_result:
                if resolved.feasibility is None:
                    resolved.feasibility = rule_result.get("feasibility")
                if resolved.feasibility_reason is None:
                    resolved.feasibility_reason = rule_result.get("feasibility_reason")
                if resolved.success_probability is None:
                    resolved.success_probability = rule_result.get("success_probability")
                if not resolved.requires_roll:
                    resolved.requires_roll = bool(rule_result.get("requires_roll", False))

            event = f"[玩家行动] {resolved.action_description}"
            if resolved.feasibility:
                event += f"（{resolved.feasibility}: {resolved.feasibility_reason or '无说明'}）"

            # ── Action duration / truncation ──
            tick_duration_minutes = 1.0 / max(state.get("ticks_per_game_minute", 0.2), 0.01)
            max_tick_duration = tick_duration_minutes * 3
            action_duration = resolved.duration_minutes
            action_continuation = None

            # Deterministic fallback: long-distance move
            if (not action_duration
                    and resolved.action_type == "move"
                    and resolved.target_position
                    and resolved.feasibility != "blocked"):
                player_pos = (state.get("player", {}) or {}).get("position") if isinstance(state.get("player"), dict) else None
                if player_pos and resolved.target_position:
                    tp = resolved.target_position
                    pp = player_pos
                    dist = math.sqrt(
                        (float(tp.get("x", pp.get("x", 0))) - float(pp.get("x", 0))) ** 2
                        + (float(tp.get("y", pp.get("y", 0))) - float(pp.get("y", 0))) ** 2
                        + (float(tp.get("z", pp.get("z", 0))) - float(pp.get("z", 0))) ** 2
                    )
                    max_move = 30.0
                    if dist > max_move:
                        action_duration = tick_duration_minutes * (dist / max_move)
                        resolved.duration_minutes = action_duration
                        resolved.continue_until = "blocked"
                        event += f"（超长移动 {dist:.0f} 单位，自动截断）"

            # If continue_until is set, always treat as multi-tick action
            if resolved.continue_until:
                if resolved.feasibility == "uncertain":
                    resolved.feasibility = "allowed"
                    resolved.requires_roll = False
                    resolved.success_probability = None
                    resolved.feasibility_reason = "多步行动：每步单独执行，直到目标达成或被阻止"
                    event += "（多步行动，自动延续）"
                action_duration = action_duration or tick_duration_minutes
                resolved.duration_minutes = action_duration

            if action_duration and action_duration > max_tick_duration:
                resolved.duration_minutes = tick_duration_minutes
                remaining = action_duration - tick_duration_minutes
                action_continuation = {
                    **(resolved.model_dump()),
                    "duration_minutes": remaining,
                }

            return {
                "player_action": resolved.model_dump(),
                "action_continuation": action_continuation,
                "event_log": [event],
            }
        except Exception:
            return {
                "player_action": player_action,
                "event_log": ["[错误] 玩家行动可行性判断失败，跳过可行性检查。"],
            }

    # ── Node: characters_all_decide ──

    async def _decide_one_char(
        state: GameState, char_id: str
    ) -> tuple[dict | None, str | None]:
        char = state.get("characters", {}).get(char_id)
        if not char:
            return None, None

        try:
            char_pos = state.get("character_positions", {}).get(char_id, {"x": 0, "y": 0, "z": 0})
            current_location = _find_location(state, char_id)
            nearby_objects = _find_nearby_objects(state, char_pos, radius=20.0)
            nearby_chars_list = _find_nearby_chars(state, char_id, radius=20.0)

            system_prompt = prompt_loader.render("character_system.j2", {
                "name": char.get("name", char_id),
                "personality": char.get("personality", {}),
                "speech_examples": char.get("speech_examples", []),
                "conversation_target": char.get("conversation_target"),
                "last_spoken_to": char.get("last_spoken_to"),
                "relationships": char.get("relationships", {}),
                "attributes": char.get("attributes", {}),
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

            if status:
                status.update(f"NPC 正在思考中...", sub_count=0, sub_total=0)
            intent = await generate_structured(llm, [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ], ActionIntent)
            intent.character_id = char_id

            return (
                intent.model_dump(),
                f"[角色] {char.get('name', char_id)}: {intent.action_description}",
            )
        except Exception:
            return None, f"[错误] {char.get('name', char_id)} 决策失败，本轮跳过。"

    async def characters_all_decide(state: GameState) -> dict[str, Any]:
        char_ids = list(state.get("characters", {}).keys())
        if not char_ids:
            return {"action_intents": [], "event_log": []}

        if status:
            status.update("NPC 正在思考中...", sub_total=len(char_ids))

        async def _decide_with_counter(cid: str, idx: int):
            result = await _decide_one_char(state, cid)
            if status:
                status.update("NPC 正在思考中...", sub_count=idx + 1, sub_total=len(char_ids))
            return result

        results = await asyncio.gather(*(_decide_with_counter(cid, i) for i, cid in enumerate(char_ids)))
        all_intents = [intent for intent, _ in results if intent]
        all_events = [event for _, event in results if event]

        return {
            "action_intents": all_intents,
            "event_log": all_events,
        }

    # ── Node: physics_resolve ──

    async def physics_resolve(state: GameState) -> dict[str, Any]:
        try:
            if status:
                status.update("正在计算物理变化...")
            system_prompt = prompt_loader.render("physics_system.j2", {
                "rules": build_rules_context(
                    PHYSICS_DEFAULT_RULES,
                    state.get("world_rules", {}).get("physics") if isinstance(state.get("world_rules"), dict) else None,
                ),
            })
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
        except Exception:
            return {
                "physics_outcomes": [],
                "event_log": ["[错误] 物理模拟失败，本轮跳过物理结果。"],
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

        new_player, new_objects, player_events = apply_player_action(
            state.get("player", {}),
            state.get("player_action"),
            new_objects,
        )

        new_chars, new_positions, new_objects, npc_events = apply_npc_actions(
            new_chars,
            new_positions,
            state.get("action_intents", []),
            new_objects,
        )

        recent = state.get("event_log", [])[-10:]
        for cid in new_chars:
            char = new_chars[cid]
            if isinstance(char, dict):
                mem = list(char.get("memory", []))
                mem.extend(recent)
                if len(mem) > 50:
                    mem = mem[-50:]
                char["memory"] = mem

        # Compact event log if needed
        current_log = state.get("event_log", [])
        compacted = compact_event_log(current_log)
        compaction_event = []
        if len(compacted) < len(current_log):
            compaction_event = [compacted[0]]  # The summary line

        new_game_time = advance_game_time(state.get("game_time"), state.get("ticks_per_game_minute", 0.2))
        new_environment = dict(state.get("environment", {}))
        new_environment["time_of_day"] = time_of_day_from_hour(new_game_time["hour"])

        return {
            "character_positions": new_positions,
            "objects": new_objects,
            "characters": new_chars,
            "player": new_player,
            "tick": state.get("tick", 0) + 1,
            "player_input": None,
            "game_time": new_game_time,
            "environment": new_environment,
            "event_log": [*player_events, *npc_events, *compaction_event],
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

        try:
            if status:
                status.update("正在感知周围环境...")
            system_prompt = prompt_loader.render("sensory_system.j2", {
                "player_capabilities": capabilities,
            })
            user_prompt = prompt_loader.render("sensory_user.j2", {
                "player_position": player_pos,
                "player_attributes": visible_player_attributes(player) if isinstance(player, dict) else {},
                "player_action": player_action,
                "self_action_summary": self_action_summary,
                "nearby_objects": nearby_objects,
                "nearby_chars": nearby_chars,
                "recent_events": state.get("event_log", [])[-10:],
                "environment": state.get("environment", {}),
                "game_time": state.get("game_time"),
            })

            percept = await generate_structured(llm, [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ], PlayerPercept)
            percept.self_action_summary = self_action_summary
            percept_dict = percept.model_dump()
            percept_dict["player_attributes"] = visible_player_attributes(player) if isinstance(player, dict) else {}

            return {"player_percept": percept_dict}
        except Exception:
            return {
                "player_percept": {
                    "summary": "你暂时无法感知周围环境。",
                    "senses": [],
                    "hidden_event_count": 0,
                    "self_action_summary": self_action_summary,
                    "player_attributes": visible_player_attributes(player) if isinstance(player, dict) else {},
                },
                "event_log": ["[错误] 感官过滤失败，使用默认感知。"],
            }

    # ── Node: attribute_update ──

    async def attribute_update(state: GameState) -> dict[str, Any]:
        player = state.get("player", {}) if isinstance(state.get("player"), dict) else {}
        characters = state.get("characters", {}) if isinstance(state.get("characters"), dict) else {}
        natural_player, natural_characters, natural_events = apply_natural_attribute_deltas(player, characters)

        attribute_summary = summarize_attributes_for_prompt(natural_player, natural_characters)
        has_attributes = bool(attribute_summary.get("player", {}).get("attributes")) or any(
            bool(char.get("attributes"))
            for char in attribute_summary.get("characters", {}).values()
        )
        if not has_attributes:
            return {"player": natural_player, "characters": natural_characters, "event_log": natural_events}

        try:
            if status:
                status.update("正在更新角色属性...")
            system_prompt = prompt_loader.render("attribute_update_system.j2", {
                "rules": build_rules_context(
                    ATTRIBUTE_DEFAULT_RULES,
                    state.get("world_rules", {}).get("attribute") if isinstance(state.get("world_rules"), dict) else None,
                    extra_sections=[("常见参考", ATTRIBUTE_DEFAULT_REFERENCES)],
                ),
            })
            user_prompt = prompt_loader.render("attribute_update_user.j2", {
                "attribute_summary": attribute_summary,
                "player_action": state.get("player_action"),
                "action_intents": state.get("action_intents", []),
                "physics_outcomes": state.get("physics_outcomes", []),
                "recent_events": state.get("event_log", [])[-10:],
                "environment": state.get("environment", {}),
                "game_time": state.get("game_time"),
            })
            resolution = await generate_structured(llm, [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ], AttributeUpdateResolution)
            changes = [change.model_dump() for change in resolution.changes]
            updated_player, updated_characters, change_events = apply_attribute_changes(
                natural_player,
                natural_characters,
                changes,
            )
            return {
                "player": updated_player,
                "characters": updated_characters,
                "event_log": [*natural_events, *change_events],
            }
        except Exception:
            return {
                "player": natural_player,
                "characters": natural_characters,
                "event_log": [*natural_events, "[错误] 属性更新失败，已跳过本轮属性事件更新。"],
            }

    # ── Build the graph ──

    builder = StateGraph(GameState)

    builder.add_node("player_intent_process", player_intent_process)
    builder.add_node("player_action_resolve", player_action_resolve)
    builder.add_node("characters_all_decide", characters_all_decide)
    builder.add_node("physics_resolve", physics_resolve)
    builder.add_node("state_apply", state_apply)
    builder.add_node("attribute_update", attribute_update)
    builder.add_node("sensory_filter", sensory_filter)

    builder.add_edge(START, "player_intent_process")
    builder.add_edge("player_intent_process", "player_action_resolve")
    builder.add_edge("player_action_resolve", "characters_all_decide")
    builder.add_edge("characters_all_decide", "physics_resolve")
    builder.add_edge("physics_resolve", "state_apply")
    builder.add_edge("state_apply", "attribute_update")
    builder.add_edge("state_apply", "sensory_filter")
    builder.add_edge("attribute_update", END)
    builder.add_edge("sensory_filter", END)

    if checkpointer is None:
        checkpointer = InMemorySaver()
    return builder.compile(checkpointer=checkpointer)
