"""G10 S11 人工面验收驱动（galgame 样例世界源，只读）。

用途 = 人工面验收前置（docs/v2/gates/G10-test-acceptance-plan.md
Step 4）：加载 P9 galgame 样例项目 → 装配 WorldState（P9 宿主侧
装配面，tests 树复用，零 src 改动）→ SessionManager（最小宿主
TickDriver + DeterministicImageBackend，K5 零真实 LLM / 零真实
图像 backend）→ stdlib 薄壳 web 服务。

宿主面（K5：宿主 = Policy；本脚本侧选择，零 src 改动）：

- 缺省 = ``HostTickDriver``（静态场景面：只推进 logical_tick +
  world_revision，世界内容不变 → RenderIntent 恒等 → 图像字节
  恒等（D6）。用于机械验收 / 连续性基线。）
- ``--living`` = :class:`LivingTickDriver`（活世界面：每次 advance
  推进世界时钟 +3h〔时段桶 上午→下午→晚间→夜间 轮转〕、每 4 刻
  切换天气、玩家网格位置步进、NPC display.mood 轮转——全部确定性
 〔零随机 / 零墙钟，D6〕，只走宿主合法缝隙
  〔world_variables / 实体组件副本 / revision〕）。用于人工面
  观察「世界变化 → 视图/图像跟随」：environment 变化 → 图像背景
  色 + narrative scene_text 变化；位置 / mood 进入快照 actor 面
  （P10 参考图像 backend 的 subject 投影 = id 级，位置 / mood 不
  进入图像 seed——参考面定位，真实图像 backend = P11+/S4）。

打印面（机器可读）：
- ``SESSION_ID=<32 位 hex>`` 单独一行（run.sh / 人工面消费）；
- 地址行（人工面消费）。

运行 = ``PYTHONPATH=. .venv/bin/python scripts/v2_g10_acceptance.py
[--port 8000] [--living]``（阻塞；Ctrl-C 停）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.engine_v2.adapters.web.server import run_web_server  # noqa: E402
from src.engine_v2.adapters.web.session import SessionManager  # noqa: E402
from src.engine_v2.content.loader import load_project  # noqa: E402
from src.engine_v2.content.project_ir import build_ir  # noqa: E402
from src.engine_v2.content.schemas import ProjectIR  # noqa: E402
from src.engine_v2.core.entity import EntityId, EntityRecord  # noqa: E402
from src.engine_v2.core.revision import INITIAL_WORLD_REVISION  # noqa: E402
from src.engine_v2.core.space import GridSpace  # noqa: E402
from src.engine_v2.presentation.image.backend import (  # noqa: E402
    DeterministicImageBackend,
)
from tests.engine_v2.adapters.web.conftest import HostTickDriver  # noqa: E402
from tests.engine_v2.modules.conftest import _build_world  # noqa: E402

GALGAME_DIR = _ROOT / "tests" / "fixtures" / "v2_project_galgame"

_DISPLAY = "display"


def _retag(record: EntityRecord, tags: list[str], name: str) -> EntityRecord:
    """副本记录（零别名；self 不变）：补 actor 标签 + display 展示面
    （P10 view 的 actor / 展示投影面，view.py:65–75 面）。"""
    components = dict(record.components)
    components[_DISPLAY] = {"name": name, "mood": "calm"}
    return EntityRecord(
        entity_id=record.entity_id,
        entity_class=record.entity_class,
        tags=tags,
        created_revision=record.created_revision,
        components=components,
    )


def _augment_p10_surface(world, ir: ProjectIR):
    """P9 宿主装配 → P10 表现面可投影（宿主侧增强；零 src 改动）。

    - character / player 实体：tags 补 ``actor`` + display 组件
      （name 自 ProjectIR；mood = 确定性缺省 calm）；
    - location 实体：ir.world.locations 首条（排序序）或 ir.world 名
      兜底（P10 主 location 投影面，view.py:168）；
    - world_variables：game_time / weather 确定性缺省（P10 环境
      投影面；logical_tick 由 HostTickDriver 持有）。
    """
    names = {
        f"ent_authoring_{char.id}": char.name for char in ir.characters
    }
    names[f"ent_authoring_{ir.player.player_id}"] = ir.player.name
    entities: dict = {}
    for entity_id, record in world.entities.items():
        if record.entity_class in ("character", "player") and str(
            entity_id
        ) in names:
            entities[entity_id] = _retag(
                record, ["actor"], names[str(entity_id)]
            )
        else:
            entities[entity_id] = record
    location_id: str | None = None
    location_name = ""
    location_desc = ""
    if ir.world is not None:
        if ir.world.locations:
            loc = sorted(ir.world.locations, key=lambda l: l.id)[0]
            location_id, location_name = loc.id, loc.name
            location_desc = loc.description
        else:
            location_id, location_name = "world", ir.world.name
            location_desc = ir.world.description
    if location_id is not None:
        entities[EntityId(f"ent_location_{location_id}")] = EntityRecord(
            entity_id=EntityId(f"ent_location_{location_id}"),
            entity_class="location",
            tags=["location"],
            created_revision=INITIAL_WORLD_REVISION,
            components={
                _DISPLAY: {
                    "name": location_name, "description": location_desc
                }
            },
        )
    world = world._with_entities(entities)
    variables = dict(world.world_variables)
    variables.setdefault("game_time", {"day": 1, "hour": 10, "minute": 0})
    variables.setdefault("weather", "晴朗")
    return world._with_world_variables(variables)


class LivingTickDriver:
    """活世界宿主（scripts 侧人工面观察用；``--living`` 选用）。

    一次 advance = HostTickDriver 同构相位（logical_tick +1 +
    world_revision +1，整体替换世界槽）之上追加世界推进——

    - ``game_time.hour += 3``（%24；时段桶 上午[5,12)/下午[12,18)/
      晚间[18,22)/夜间 轮转 → view 环境投影 → 图像背景色 +
      narrative scene_text 变化）；
    - 每 4 刻切换 ``weather``（晴朗 ↔ 薄雨 → 环境投影变化）；
    - 玩家实体网格位置 (x+1, y+1) % 10 步进（进入快照
      ``player.position`` / actor 面；**不**进入 P10 参考图像
      seed——subject 投影 = id 级，参考面定位）；
    - 角色实体 ``display.mood`` 轮转（calm/happy/tense/sad →
      快照 ``npc_dynamics`` / actor 面；同上不进图像 seed——
      场景 mood 源 = 叙事帧面，world 面无帧 → 恒 calm）。

    纪律：零随机 / 零墙钟（D6）；只走 core 合法缝隙
    （``_with_world_variables`` / ``_with_entities`` 整体替换 /
    ``_with_world_revision``，HostTickDriver 同族先例）；
    不 import 任何 P10 冻结面之外的新机制。
    """

    _MOODS = ("calm", "happy", "tense", "sad")
    _WEATHERS = ("晴朗", "薄雨")

    def __init__(self, world=None) -> None:
        self._world = world
        self._step = 0

    @property
    def world(self):
        """权威世界槽（HostTickDriver 同形面）。"""
        return self._world

    def advance(self, world) -> None:
        """一次活世界相位（世界推进 + 相位推进；整体替换）。"""
        self._step += 1
        tick = int(world.world_variables.get("logical_tick") or 0) + 1
        variables = dict(world.world_variables)
        game_time = dict(
            variables.get("game_time") or {"day": 1, "hour": 10, "minute": 0}
        )
        game_time["hour"] = (int(game_time.get("hour", 10)) + 3) % 24
        variables["logical_tick"] = tick
        variables["game_time"] = game_time
        variables["weather"] = self._WEATHERS[1 if self._step % 4 == 0 else 0]
        entities: dict = {}
        for entity_id, record in world.entities.items():
            if record.entity_class == "player":
                record = self._step_player(record, tick)
            elif record.entity_class == "character":
                record = self._cycle_mood(record)
            entities[entity_id] = record
        world = world._with_world_variables(variables)._with_entities(entities)
        self._world = world._with_world_revision(world.world_revision.next())

    def _step_player(self, record, tick):
        """玩家 spaces 组件 (x+1, y+1) % 10 步进（副本；self 不变）。"""
        components = dict(record.components)
        payload = components.get("spaces")
        if not isinstance(payload, dict) or not isinstance(
            payload.get("mappings"), list
        ):
            return record
        mappings = []
        for mapping in payload["mappings"]:
            mapping = dict(mapping)
            position = dict(mapping.get("position") or {})
            if isinstance(position.get("x"), (int, float)):
                position["x"] = (float(position["x"]) + 1.0) % 10.0
                if isinstance(position.get("y"), (int, float)):
                    position["y"] = (float(position["y"]) + 1.0) % 10.0
            mapping["position"] = position
            mapping["entered_tick"] = tick
            mappings.append(mapping)
        components["spaces"] = {"mappings": mappings}
        return _copy_record(record, components)

    def _cycle_mood(self, record):
        """角色 display.mood 按宿主步序轮转（副本；self 不变）。"""
        components = dict(record.components)
        display = dict(components.get(_DISPLAY) or {})
        display["mood"] = self._MOODS[self._step % len(self._MOODS)]
        components[_DISPLAY] = display
        return _copy_record(record, components)


def _copy_record(record: EntityRecord, components: dict) -> EntityRecord:
    """实体记录副本（零别名；字段全量回灌，tags 复制）。"""
    return EntityRecord(
        entity_id=record.entity_id,
        entity_class=record.entity_class,
        tags=list(record.tags),
        created_revision=record.created_revision,
        components=components,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--living",
        action="store_true",
        help="活世界宿主（世界时钟/天气/位置/mood 随动作推进；"
        "人工面观察「世界变化 → 视图跟随」；缺省 = 静态宿主）",
    )
    args = parser.parse_args()

    load = load_project(GALGAME_DIR)
    if load.raw is None:
        raise SystemExit(f"load_project 失败: {load.diagnostics}")
    ir_res = build_ir(load.raw)
    if ir_res.ir is None:
        raise SystemExit(f"build_ir 失败: {ir_res.diagnostics}")
    world, _spaces, _rels, _attrs = _build_world(
        ir_res.ir, "world", GridSpace(width=10, height=10)
    )
    world = _augment_p10_surface(world, ir_res.ir)
    driver_cls = LivingTickDriver if args.living else HostTickDriver
    manager = SessionManager(
        driver_factory=lambda: driver_cls(world),
        image_backend_factory=DeterministicImageBackend,
    )
    session_id = manager.create_session(world)
    host_note = "活世界宿主（--living）" if args.living else "静态宿主"
    print(f"SESSION_ID={session_id}", flush=True)
    print(
        f"open http://{args.host}:{args.port}/ （会话 ID 填入页面输入框）"
        f"　宿主面 = {host_note}",
        flush=True,
    )
    try:
        run_web_server(manager, host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("stopped", flush=True)


if __name__ == "__main__":
    main()
