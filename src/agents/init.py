"""Initialization agent: dialogue-driven and file-driven game setup."""

from pathlib import Path
from typing import Any

import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.graph.game_state import GameState, make_initial_state
from src.config.loader import ConfigLoader
from src.llm.parser import generate_structured
from src.models.events import InitialGameConfig
from src.prompts.loader import PromptLoader


async def init_game(
    llm: ChatOpenAI,
    prompt_loader: PromptLoader,
    ui,  # GameUI protocol
) -> GameState:
    """Run dialogue-driven initialization, return initial GameState."""

    ui.display_title("=== LLM 互动模拟游戏 ===\n")

    questions = [
        (
            "你希望游戏发生在什么样的世界？\n"
            "例如：中世纪的村庄、赛博朋克城市、太空殖民地..."
        ),
        (
            "你想扮演什么角色？\n"
            "例如：一个路过的旅行者、村庄的守卫、寻找宝藏的冒险者..."
        ),
        (
            "这个世界里有哪些 NPC？请描述他们的性格。\n"
            "例如：Alice是个笨拙但热心的面包师女儿；Bob是个沉默寡言的神秘酒馆常客..."
        ),
        (
            "你希望开场时是怎样的场景？\n"
            "例如：一个宁静的早晨，你来到了村庄的广场..."
        ),
    ]

    answers = {}
    for i, q in enumerate(questions):
        ui.display(f"\n[bold cyan]问题 {i + 1}/{len(questions)}[/bold cyan]")
        ui.display(q)
        answer = await ui.collect_input("\n你的回答: ")
        answers[f"q{i}"] = answer

    ui.display("\n[dim]正在生成游戏世界...[/dim]\n")

    system_prompt = prompt_loader.render("init_system.j2", {})
    user_prompt = "玩家对游戏设定的回答:\n\n" + "\n\n".join(
        f"问题 {i + 1}: {q}\n回答: {answers[f'q{i}']}"
        for i, q in enumerate(questions)
    )

    config = await generate_structured(llm, [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ], InitialGameConfig)

    return _config_to_game_state(config)


def _config_to_game_state(config: InitialGameConfig) -> GameState:
    """Convert InitialGameConfig to a GameState ready for the simulation."""

    w = config.world
    locations = {}
    for loc_id, loc_data in w.locations.items():
        loc = loc_data if isinstance(loc_data, dict) else loc_data.model_dump()
        if "id" not in loc:
            loc["id"] = loc_id
        # Normalize connections: LLM may output list instead of dict
        conns = loc.get("connections", {})
        if isinstance(conns, list):
            conns = {c: c for c in conns}
            loc["connections"] = conns
        locations[loc["id"]] = loc

    objects = {}
    for obj_id, obj_data in w.objects.items():
        obj = obj_data if isinstance(obj_data, dict) else obj_data.model_dump()
        if "object_id" not in obj:
            obj["object_id"] = obj_id
        objects[obj["object_id"]] = obj

    characters = {}
    character_positions = {}
    for char in config.characters:
        cd = char if isinstance(char, dict) else char.model_dump()
        cid = cd["character_id"]
        characters[cid] = cd
        pos_data = cd.get("position", {})
        character_positions[cid] = {
            "x": pos_data.get("x", 0),
            "y": pos_data.get("y", 0),
            "z": pos_data.get("z", 0),
        }

    player = config.player if isinstance(config.player, dict) else config.player.model_dump()

    env = w.environment
    environment = env if isinstance(env, dict) else env.model_dump()

    return make_initial_state(
        tick=0,
        max_ticks=100,
        game_phase="running",
        world_name=w.name,
        world_description=w.description,
        locations=locations,
        objects=objects,
        character_positions=character_positions,
        environment=environment,
        characters=characters,
        player=player,
        event_log=[f"[系统] 游戏开始: {config.starting_scene_description}"],
    )


def load_init_file(filepath: str | Path) -> dict[str, Any]:
    """Read a single YAML init file and return raw dict."""
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _position_near(position: dict[str, Any], dx: float = 1.0) -> dict[str, float]:
    return {
        "x": float(position.get("x", 0)) + dx,
        "y": float(position.get("y", 0)),
        "z": float(position.get("z", 0)),
    }


def infer_player_start_position(
    player_raw: dict[str, Any],
    locations: dict[str, dict],
    objects: dict[str, dict],
    character_positions: dict[str, dict],
    starting_location_id: str | None = None,
) -> tuple[dict[str, float], list[str]]:
    """Infer a reasonable player start position and return warning events."""
    for key in ("position", "starting_position"):
        pos = player_raw.get(key)
        if pos:
            return {
                "x": float(pos.get("x", 0)),
                "y": float(pos.get("y", 0)),
                "z": float(pos.get("z", 0)),
            }, []

    if starting_location_id and starting_location_id in locations:
        for obj_id in locations[starting_location_id].get("objects", []):
            obj = objects.get(obj_id)
            if obj and obj.get("position"):
                return _position_near(obj["position"]), []

    for loc in locations.values():
        for obj_id in loc.get("objects", []):
            obj = objects.get(obj_id)
            if obj and obj.get("position"):
                return _position_near(obj["position"]), []

    first_char_position = next(iter(character_positions.values()), None)
    if first_char_position:
        return _position_near(first_char_position, dx=-1.0), []

    return {"x": 0.0, "y": 0.0, "z": 0.0}, ["[警告] 玩家初始位置缺失，已使用世界原点兜底。"]


def init_file_to_game_state(raw: dict[str, Any]) -> GameState:
    """Convert a raw init-file dict into a GameState ready for simulation."""
    w = raw.get("world", {})
    env_raw = w.get("environment", {}) or {}
    environment = {
        "time_of_day": env_raw.get("time_of_day", "morning"),
        "weather": env_raw.get("weather", "clear"),
        "temperature_c": float(env_raw.get("temperature_c", 20.0)),
    }

    locations: dict[str, dict] = {}
    for loc in w.get("locations", []) or []:
        lid = loc.get("id", loc.get("name", ""))
        loc["id"] = lid
        conns = loc.get("connections", {})
        if isinstance(conns, list):
            loc["connections"] = {c: c for c in conns}
        locations[lid] = dict(loc)

    objects: dict[str, dict] = {}
    for obj in w.get("objects", []) or []:
        oid = obj.get("id", obj.get("object_id", obj.get("name", "")))
        obj["id"] = oid
        obj["object_id"] = oid
        pos = obj.get("position", {}) or {}
        obj["position"] = {"x": pos.get("x", 0), "y": pos.get("y", 0), "z": pos.get("z", 0)}
        objects[oid] = dict(obj)

    characters: dict[str, dict] = {}
    character_positions: dict[str, dict[str, float]] = {}
    for char in raw.get("characters", []) or []:
        cid = char.get("id", char.get("character_id", ""))
        char["character_id"] = cid
        pos = char.get("position", char.get("starting_position", {})) or {}
        character_positions[cid] = {"x": pos.get("x", 0), "y": pos.get("y", 0), "z": pos.get("z", 0)}
        characters[cid] = dict(char)
        characters[cid].setdefault("attributes", {})

    player_raw = raw.get("player", {}) or {}
    player_caps = player_raw.get("capabilities", {}) or {}
    player: dict[str, Any] = {
        "player_id": player_raw.get("player_id", "player_1"),
        "name": player_raw.get("name", "玩家"),
        "persona": player_raw.get("persona", ""),
        "capabilities": {
            "sight_range_m": float(player_caps.get("sight_range_m", 50.0)),
            "hearing_range_m": float(player_caps.get("hearing_range_m", 100.0)),
            "field_of_view_degrees": float(player_caps.get("field_of_view_degrees", 120.0)),
            "special_senses": player_caps.get("special_senses", []) or [],
            "allowed_extraordinary_actions": player_caps.get("allowed_extraordinary_actions", []) or [],
            "blocked_common_actions": player_caps.get("blocked_common_actions", []) or [],
            "skill_levels": player_caps.get("skill_levels", {}) or {},
        },
        "physical_profile": player_raw.get("physical_profile", {}) or {},
        "knowledge": player_raw.get("knowledge", {}) or {},
        "inventory": player_raw.get("inventory", player_raw.get("starting_inventory", [])) or [],
        "status_effects": player_raw.get("status_effects", {}) or {},
        "attributes": player_raw.get("attributes", {}) or {},
        "subconscious_rules": player_raw.get("subconscious_rules", []) or [],
        "subconscious_memory": player_raw.get("subconscious_memory", []) or [],
        "speech_examples": player_raw.get("speech_examples", []) or [],
    }
    player_position, position_events = infer_player_start_position(
        player_raw,
        locations,
        objects,
        character_positions,
        raw.get("starting_location_id"),
    )
    player["position"] = player_position

    starting_desc = raw.get("starting_scene_description", "游戏开始。")
    event_log = [f"[系统] 游戏开始: {starting_desc}", *position_events]

    return make_initial_state(
        tick=0,
        max_ticks=raw.get("max_ticks", 100),
        game_phase="running",
        world_name=w.get("name", ""),
        world_description=w.get("description", ""),
        locations=locations,
        objects=objects,
        character_positions=character_positions,
        environment=environment,
        characters=characters,
        player=player,
        world_rules=raw.get("world_rules", {}) or {},
        narrative_style=raw.get("narrative_style", {}) or {},
        game_time=raw.get("game_time", {"hour": 18, "minute": 0}),
        ticks_per_game_minute=float(raw.get("ticks_per_game_minute", 0.2)),
        event_log=event_log,
    )


def config_loader_to_game_state(config_loader: ConfigLoader) -> GameState:
    world_config = config_loader.load_world().world
    player_config = config_loader.load_player().player
    character_configs = config_loader.load_all_characters()

    locations: dict[str, dict] = {}
    for loc in world_config.locations:
        loc_dict = loc.model_dump()
        locations[loc.id] = loc_dict

    objects: dict[str, dict] = {}
    for obj in world_config.objects:
        obj_dict = obj.model_dump()
        obj_dict["object_id"] = obj.id
        objects[obj.id] = obj_dict

    characters: dict[str, dict] = {}
    character_positions: dict[str, dict] = {}
    for char_config in character_configs:
        char = char_config.character
        char_dict = {
            "character_id": char.id,
            "id": char.id,
            "name": char.name,
            "personality": char.personality.model_dump(),
            "position": char.starting_position.model_dump(),
            "inventory": list(char.starting_inventory),
            "relationships": dict(char.relationships),
            "attributes": {
                key: value.model_dump() if hasattr(value, "model_dump") else value
                for key, value in char.attributes.items()
            },
            "speech_examples": list(char.speech_examples),
            "memory": [],
            "status_effects": {},
            "current_action": None,
        }
        characters[char.id] = char_dict
        character_positions[char.id] = char.starting_position.model_dump()

    player_raw = player_config.model_dump()
    player_position, position_events = infer_player_start_position(
        player_raw,
        locations,
        objects,
        character_positions,
    )
    player = {
        "player_id": "player_1",
        "name": player_config.name,
        "persona": player_config.persona,
        "position": player_position,
        "capabilities": player_config.capabilities.model_dump(),
        "physical_profile": player_config.physical_profile.model_dump(),
        "knowledge": {},
        "inventory": list(player_config.starting_inventory),
        "status_effects": {},
        "attributes": {
            key: value.model_dump() if hasattr(value, "model_dump") else value
            for key, value in player_config.attributes.items()
        },
        "subconscious_rules": list(player_config.subconscious_rules),
        "subconscious_memory": list(player_config.subconscious_memory),
        "speech_examples": list(player_config.speech_examples),
    }

    return make_initial_state(
        tick=0,
        max_ticks=100,
        game_phase="running",
        world_name=world_config.name,
        world_description=world_config.description,
        locations=locations,
        objects=objects,
        character_positions=character_positions,
        environment=world_config.environment.model_dump(),
        characters=characters,
        player=player,
        world_rules={},
        narrative_style={},
        game_time={"hour": 18, "minute": 0},
        ticks_per_game_minute=0.2,
        event_log=["[系统] 从配置文件开始游戏。", *position_events],
    )


def load_init_file_set(dir_path: str | Path) -> GameState:
    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"目录不存在: {dir_path}")
    loader = ConfigLoader(str(dir_path))
    state = config_loader_to_game_state(loader)

    settings_path = dir_path / "settings.yaml"
    if settings_path.exists():
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = yaml.safe_load(f) or {}
        if isinstance(settings, dict):
            if "world_rules" in settings:
                state["world_rules"] = settings["world_rules"] or {}
            if "narrative_style" in settings:
                state["narrative_style"] = settings["narrative_style"] or {}
            if "max_ticks" in settings:
                state["max_ticks"] = int(settings["max_ticks"])
            if "game_time" in settings:
                state["game_time"] = dict(settings["game_time"])
            if "ticks_per_game_minute" in settings:
                state["ticks_per_game_minute"] = float(settings["ticks_per_game_minute"])

    return state
