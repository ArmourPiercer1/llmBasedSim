"""Browser-based UI server for the simulation game."""

import asyncio
import json
import mimetypes
import os
import re
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import uuid4

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from src.agents.init import init_file_to_game_state, load_init_file, load_init_file_set
from src.config.loader import ConfigLoader
from src.graph.game_graph import build_game_graph
from src.graph.game_state import GameState, normalize_state, reset_tick_transients, strip_transient_state
from src.prompts.loader import PromptLoader

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = PROJECT_ROOT / "web"
STATIC_ROOT = WEB_ROOT / "static"
SAVES_DIR = PROJECT_ROOT / "saves"
START_DIRS = (PROJECT_ROOT / "public_start", PROJECT_ROOT / "private_start")
DEFAULT_INIT_FILE = PROJECT_ROOT / "public_start" / "whisperheads.yaml"

_load_dotenv_path = PROJECT_ROOT / ".env"
if _load_dotenv_path.exists():
    load_dotenv(_load_dotenv_path)


class WebUIError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class WebTurnStatus:
    def __init__(self) -> None:
        self.step = "等待中..."
        self.sub_count = 0
        self.sub_total = 0
        self.lock = threading.Lock()

    def update(self, step: str, sub_count: int = 0, sub_total: int = 0) -> None:
        with self.lock:
            self.step = step
            self.sub_count = sub_count
            self.sub_total = sub_total

    def reset(self) -> None:
        self.update("等待中...")

    def snapshot(self, busy: bool) -> dict[str, Any]:
        with self.lock:
            return {
                "busy": busy,
                "step": self.step,
                "sub_count": self.sub_count,
                "sub_total": self.sub_total,
            }


@dataclass
class StartRequest:
    mode: str = "init_file"
    init_file: str | None = None
    init_dir: str | None = None
    save_path: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "StartRequest":
        return cls(
            mode=str(payload.get("mode") or "init_file"),
            init_file=payload.get("init_file"),
            init_dir=payload.get("init_dir"),
            save_path=payload.get("save_path"),
        )


@dataclass
class ActionRequest:
    input: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ActionRequest":
        return cls(input=str(payload.get("input") or ""))


@dataclass
class SaveRequest:
    name: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "SaveRequest":
        return cls(name=str(payload.get("name") or ""))


class GameSession:
    def __init__(self) -> None:
        self.id = uuid4().hex
        self.state: GameState | None = None
        self.graph = None
        self.llm: ChatOpenAI | None = None
        self.prompt_loader: PromptLoader | None = None
        self.tick_thread = 0
        self.lock = threading.Lock()
        self.status = WebTurnStatus()
        self.busy = False

    def configure_services(self) -> None:
        if self.graph is not None:
            return
        config_loader = ConfigLoader(str(PROJECT_ROOT / "config"))
        sim_config = config_loader.load_simulation()
        api_key = os.environ.get(sim_config.llm.api_key_env)
        if not api_key:
            raise WebUIError(500, f"环境变量 {sim_config.llm.api_key_env} 未设置")
        self.llm = ChatOpenAI(
            model=sim_config.llm.model,
            base_url=sim_config.llm.base_url,
            api_key=api_key,
            temperature=sim_config.llm.temperature,
            max_tokens=sim_config.llm.max_tokens,
        )
        self.prompt_loader = PromptLoader(str(PROJECT_ROOT / "prompts"))
        self.graph = build_game_graph(self.llm, self.prompt_loader, status=self.status)

    def start(self, request: StartRequest) -> dict[str, Any]:
        if request.mode == "save":
            if not request.save_path:
                raise WebUIError(400, "读取存档需要 save_path")
            save_path = _safe_existing_path(request.save_path, SAVES_DIR)
            with open(save_path, "r", encoding="utf-8") as f:
                state = normalize_state(json.load(f))
        elif request.mode == "init_dir":
            if not request.init_dir:
                raise WebUIError(400, "选择开局文件组需要 init_dir")
            dir_path = _safe_init_dir(request.init_dir)
            state = load_init_file_set(dir_path)
        else:
            init_file = request.init_file or str(DEFAULT_INIT_FILE)
            init_path = _safe_init_file_path(init_file)
            state = init_file_to_game_state(load_init_file(init_path))
        self.state = state
        self.tick_thread = int(state.get("tick", 0))
        self.busy = False
        self.status.reset()
        return snapshot(state)

    async def step(self, player_input: str) -> dict[str, Any]:
        with self.lock:
            if self.state is None:
                raise WebUIError(400, "游戏尚未开始")
            command_result = self.handle_command(player_input)
            if command_result is not None:
                return command_result
            if self.busy:
                raise WebUIError(409, "上一轮推演尚未结束")
            self.status.update("准备开始推演...")
            self.busy = True
            self.configure_services()
            current_state = reset_tick_transients(self.state, player_input)
            thread_config = {"configurable": {"thread_id": f"web_{self.id}_{self.tick_thread}"}}
            self.tick_thread += 1
        try:
            result = await self.graph.ainvoke(current_state, thread_config)
            with self.lock:
                self.status.update("推演完成")
                self.state = normalize_state(result)
                return snapshot(self.state)
        finally:
            with self.lock:
                self.busy = False

    def handle_command(self, command: str) -> dict[str, Any] | None:
        stripped = command.strip()
        lowered = stripped.lower()
        if lowered == "/help":
            data = snapshot(self.state or {})
            data["message"] = "命令: /help, /status, /idid, /see, /hear, /feel, /save <name>, /stop"
            return data
        if lowered == "/status":
            data = snapshot(self.state or {})
            data["modal"] = {"title": "数值状态", "items": all_player_attribute_items(self.state or {})}
            return data
        if lowered == "/idid":
            percept = (self.state or {}).get("player_percept") or {}
            data = snapshot(self.state or {})
            data["modal"] = {"title": "你做了什么", "items": [percept.get("self_action_summary") or "你本回合没有特别的行为。"]}
            return data
        if lowered == "/see":
            return self.sense_command("sight", "你看到的")
        if lowered == "/hear":
            return self.sense_command("sound", "你听到的")
        if lowered == "/feel":
            data = snapshot(self.state or {})
            data["modal"] = {"title": "你感觉到的", "items": sense_items(self.state or {}, {"touch", "smell"})}
            return data
        if lowered.startswith("/save "):
            save_name = stripped[6:].strip()
            save_game(self.state or {}, save_name)
            data = snapshot(self.state or {})
            data["message"] = f"已保存到 saves/{save_name}.json"
            return data
        return None

    def sense_command(self, sense_type: str, title: str) -> dict[str, Any]:
        data = snapshot(self.state or {})
        data["modal"] = {"title": title, "items": sense_items(self.state or {}, {sense_type})}
        return data


session = GameSession()


class WebUIRequestHandler(BaseHTTPRequestHandler):
    server_version = "LLMSimWebUI/0.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/":
                self._send_file(WEB_ROOT / "index.html")
            elif path == "/api/state":
                self._send_json(get_state())
            elif path == "/api/progress":
                self._send_json(get_progress())
            elif path == "/api/saves":
                self._send_json(list_saves())
            elif path == "/api/init-files":
                self._send_json(list_init_files())
            elif path.startswith("/static/"):
                relative = unquote(path.removeprefix("/static/"))
                self._send_static(relative)
            else:
                raise WebUIError(404, "未找到资源")
        except WebUIError as exc:
            self._send_error(exc.status_code, exc.detail)
        except Exception as exc:
            self._send_error(500, str(exc))

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._read_json_body()
            if path == "/api/start":
                self._send_json(start_game(StartRequest.from_payload(payload)))
            elif path == "/api/action":
                self._send_json(asyncio.run(submit_action(ActionRequest.from_payload(payload))))
            elif path == "/api/save":
                self._send_json(save_current(SaveRequest.from_payload(payload)))
            else:
                raise WebUIError(404, "未找到接口")
        except WebUIError as exc:
            self._send_error(exc.status_code, exc.detail)
        except json.JSONDecodeError:
            self._send_error(400, "请求体不是有效 JSON")
        except Exception as exc:
            self._send_error(500, str(exc))

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise WebUIError(400, "请求体必须是 JSON 对象")
        return payload

    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_error(self, status: int, detail: str) -> None:
        self._send_json({"detail": detail}, status=status)

    def _send_static(self, relative_path: str) -> None:
        resolved = (STATIC_ROOT / relative_path).resolve()
        try:
            resolved.relative_to(STATIC_ROOT.resolve())
        except ValueError as exc:
            raise WebUIError(400, "静态资源路径无效") from exc
        self._send_file(resolved)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            raise WebUIError(404, "文件不存在")
        raw = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif path.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif path.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def create_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), WebUIRequestHandler)


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = create_server(host, port)
    print(f"WebUI running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def get_state() -> dict[str, Any]:
    if session.state is None:
        return {
            "started": False,
            "default_init_file": str(DEFAULT_INIT_FILE.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "init_files": list_init_files()["init_files"],
        }
    return snapshot(session.state)


def get_progress() -> dict[str, Any]:
    return session.status.snapshot(session.busy)


def list_init_files() -> dict[str, Any]:
    files = []
    for start_dir in START_DIRS:
        if not start_dir.exists():
            continue
        for path in sorted(start_dir.glob("*.yml")) + sorted(start_dir.glob("*.yaml")):
            files.append(init_file_item(path, start_dir.name))
        for subdir in sorted(start_dir.iterdir()):
            if subdir.is_dir() and (subdir / "world.yaml").exists():
                files.append(init_dir_item(subdir, start_dir.name))
    files.sort(key=lambda item: (item["source"], item.get("type", ""), item["name"], item["path"]))
    return {"init_files": files}


def init_file_item(path: Path, source: str) -> dict[str, Any]:
    rel_path = path.relative_to(PROJECT_ROOT).as_posix()
    world_name = ""
    description = ""
    try:
        raw = load_init_file(path)
        world = raw.get("world", {}) if isinstance(raw, dict) else {}
        world_name = str(world.get("name") or "")
        description = str(world.get("description") or "")
    except Exception:
        pass
    return {
        "name": world_name or path.stem,
        "path": rel_path,
        "source": source,
        "description": description,
    }


def init_dir_item(dir_path: Path, source: str) -> dict[str, Any]:
    rel_path = dir_path.relative_to(PROJECT_ROOT).as_posix()
    world_name = dir_path.name
    description = ""
    try:
        world_path = dir_path / "world.yaml"
        raw = load_init_file(world_path)
        world = raw.get("world", {}) if isinstance(raw, dict) else {}
        world_name = str(world.get("name") or dir_path.name)
        description = str(world.get("description") or "")
    except Exception:
        pass
    return {
        "name": world_name,
        "path": rel_path,
        "source": source,
        "description": description,
        "type": "dir_set",
    }


def list_saves() -> dict[str, Any]:
    SAVES_DIR.mkdir(exist_ok=True)
    saves = []
    for path in sorted(SAVES_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            saves.append({
                "name": path.stem,
                "path": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "world_name": raw.get("world_name", ""),
                "tick": raw.get("tick", 0),
                "game_time": raw.get("game_time", {}),
                "modified_at": int(path.stat().st_mtime),
            })
        except Exception:
            continue
    return {"saves": saves}


def start_game(request: StartRequest) -> dict[str, Any]:
    return session.start(request)


async def submit_action(request: ActionRequest) -> dict[str, Any]:
    text = request.input.strip()
    if not text:
        raise WebUIError(400, "请输入行动或命令")
    return await session.step(text)


def save_current(request: SaveRequest) -> dict[str, Any]:
    if session.state is None:
        raise WebUIError(400, "游戏尚未开始")
    path = save_game(session.state, request.name)
    data = snapshot(session.state)
    data["message"] = f"已保存到 {path.relative_to(PROJECT_ROOT).as_posix()}"
    return data


def snapshot(state: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_state(state)
    percept = normalized.get("player_percept") or {}
    return {
        "started": bool(state),
        "world_name": normalized.get("world_name", ""),
        "world_description": normalized.get("world_description", ""),
        "tick": normalized.get("tick", 0),
        "max_ticks": normalized.get("max_ticks", 100),
        "game_phase": normalized.get("game_phase", "init"),
        "game_time": normalized.get("game_time", {}),
        "time_of_day": (normalized.get("environment") or {}).get("time_of_day", ""),
        "weather": (normalized.get("environment") or {}).get("weather", ""),
        "temperature_c": (normalized.get("environment") or {}).get("temperature_c"),
        "narrative": percept.get("narrative") or percept.get("summary") or starting_scene(normalized),
        "summary": percept.get("summary", ""),
        "senses": percept.get("senses", []),
        "self_action_summary": percept.get("self_action_summary", ""),
        "hidden_event_count": percept.get("hidden_event_count", 0),
        "player": public_player(normalized.get("player", {})),
        "player_attributes": visible_attribute_items((normalized.get("player", {}) or {}).get("attributes", {})),
        "all_player_attributes": all_player_attribute_items(normalized),
        "npc_dynamics": npc_dynamics(normalized),
        "recent_events": normalized.get("event_log", [])[-8:],
        "narrative_history": normalized.get("narrative_history", []),
        "can_continue": normalized.get("game_phase") != "ended" and normalized.get("tick", 0) < normalized.get("max_ticks", 100),
        "tick_duration_minutes": normalized.get("tick_duration_minutes", 0.0),
    }


def starting_scene(state: dict[str, Any]) -> str:
    for event in state.get("event_log", []):
        if isinstance(event, str) and event.startswith("[系统] 游戏开始: "):
            return event.replace("[系统] 游戏开始: ", "")
    return state.get("world_description", "")


def public_player(player: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(player, dict):
        return {}
    return {
        "name": player.get("name", "玩家"),
        "persona": player.get("persona", ""),
        "inventory": player.get("inventory", []),
        "status_effects": player.get("status_effects", {}),
    }


def visible_attribute_items(attributes: dict[str, Any]) -> list[dict[str, Any]]:
    return attribute_items(attributes, include_hidden=False)


def all_player_attribute_items(state: dict[str, Any]) -> list[dict[str, Any]]:
    player = state.get("player", {}) if isinstance(state, dict) else {}
    attributes = player.get("attributes", {}) if isinstance(player, dict) else {}
    return attribute_items(attributes, include_hidden=True)


def attribute_items(attributes: dict[str, Any], include_hidden: bool) -> list[dict[str, Any]]:
    items = []
    if not isinstance(attributes, dict):
        return items
    for key, attr in attributes.items():
        if not isinstance(attr, dict):
            continue
        if attr.get("hidden") and not include_hidden:
            continue
        items.append({
            "key": key,
            "name": attr.get("name") or key,
            "value": attr.get("value", 0),
            "max": attr.get("max"),
            "unit": attr.get("unit", ""),
            "hidden": bool(attr.get("hidden")),
        })
    return items


def npc_dynamics(state: dict[str, Any]) -> list[dict[str, str]]:
    dynamics = []
    characters = state.get("characters", {}) if isinstance(state, dict) else {}
    if not isinstance(characters, dict):
        return dynamics
    for cid, char in characters.items():
        if not isinstance(char, dict):
            continue
        dynamics.append({
            "id": cid,
            "name": char.get("name", cid),
            "action": char.get("current_action") or "暂时没有明显动作",
        })
    return dynamics


def sense_items(state: dict[str, Any], sense_types: set[str]) -> list[str]:
    percept = state.get("player_percept") or {}
    items = []
    for sense in percept.get("senses", []) or []:
        if isinstance(sense, dict) and sense.get("sense") in sense_types:
            text = sense.get("description", "")
            if text:
                if float(sense.get("confidence", 1.0) or 1.0) < 1.0:
                    text = f"{text}（不太确定）"
                items.append(text)
    return items or ["没有对应的感官信息。"]


def save_game(state: dict[str, Any], save_name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", save_name):
        raise WebUIError(400, "存档名只能包含字母、数字、下划线和短横线")
    SAVES_DIR.mkdir(exist_ok=True)
    path = SAVES_DIR / f"{save_name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(strip_transient_state(state), f, ensure_ascii=False, indent=2)
    return path


def _safe_init_file_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_file():
        raise WebUIError(404, f"文件不存在: {raw_path}")
    if resolved.suffix.lower() not in {".yaml", ".yml"}:
        raise WebUIError(400, "开局文件必须是 .yaml 或 .yml 文件")
    return resolved


def _safe_init_dir(raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise WebUIError(404, f"目录不存在: {raw_path}")
    if not (resolved / "world.yaml").exists():
        raise WebUIError(400, "开局文件组目录必须包含 world.yaml")
    return resolved


def _safe_existing_path(raw_path: str, base: Path) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    resolved = path.resolve()
    base_resolved = base.resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError as exc:
        raise WebUIError(400, "路径必须位于项目目录内") from exc
    if not resolved.exists():
        raise WebUIError(404, f"文件不存在: {raw_path}")
    return resolved
