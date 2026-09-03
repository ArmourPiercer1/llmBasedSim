"""G10 S11 人工面验收驱动（galgame 样例世界源，只读）。

用途 = 人工面验收前置（docs/v2/gates/G10-test-acceptance-plan.md
Step 4）：加载 P9 galgame 样例项目 → 装配 WorldState（P9 宿主侧
装配面，tests 树复用，零 src 改动）→ SessionManager（最小宿主
TickDriver + DeterministicImageBackend，K5 零真实 LLM / 零真实
图像 backend）→ stdlib 薄壳 web 服务。

打印面（机器可读）：
- ``SESSION_ID=<32 位 hex>`` 单独一行（run.sh / 人工面消费）；
- 地址行（人工面消费）。

运行 = ``PYTHONPATH=. .venv/bin/python scripts/v2_g10_acceptance.py
[--port 8000]``（阻塞；Ctrl-C 停）。
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
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
    manager = SessionManager(
        driver_factory=lambda: HostTickDriver(world),
        image_backend_factory=DeterministicImageBackend,
    )
    session_id = manager.create_session(world)
    print(f"SESSION_ID={session_id}", flush=True)
    print(
        f"open http://{args.host}:{args.port}/ （会话 ID 填入页面输入框）",
        flush=True,
    )
    try:
        run_web_server(manager, host=args.host, port=args.port)
    except KeyboardInterrupt:
        print("stopped", flush=True)


if __name__ == "__main__":
    main()
