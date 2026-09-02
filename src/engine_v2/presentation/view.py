"""P10 presentation 层公共派生面：SceneView（T01；SOT §3.1；导出 5 名）。

来源 = Spec §8.5（L626–638，ViewState = derived data / MUST NOT
authoritative）+ §32.1（L1680–1696，View/Scene Context → Narrator +
VisualDirector 平行结构）+ §45 主流程末端（L2257–2268，View derivation
分叉）；G10-2「结构化 View」唯一来源。

冻结消费面（只读）：core ``state``（``WorldState``:246 /
``world_revision``:276 / ``ScenarioState``:102 / ``EntityRecord``.
``components`` 原始字段面）/ core ``space``（``decode_spaces``:492 /
``SPACES_COMPONENT``:447）/ core ``components``（``ComponentTypeId``）。
位置面注记：``entity_domain_positions``（space.py:505）消费
``EntityView`` 深冻结载荷，其对 grid 域 dict 位置的
``decode_spaces`` pydantic 复校验拒绝 ``MappingProxyType``（core
潜在面坑，P9 纯 hex 字符串位置掩盖；Leader 裁决转 P10 SOT §9
勘误链 ERR-P10-08）——本模块改经
``decode_spaces`` 冻结 codec 消费 ``WorldState.entities[...]
.components`` 原始字段面（P9 conftest 同模式，modules/conftest.py:607）。

纪律（P10-INV-1/2/10，D6，K8）：纯派生零反作用（WorldState 只读；
返回容器与 WorldState 零别名，嵌套 dict 全部新建）；``view_revision``
= ``world.world_revision`` 投影；tick 取自 world 组件面——
``world_variables["logical_tick"]``（缺省 0；P1 D-6：WorldState 无时钟
字段，世界时间事实归 ``world_variables``，state.py:27–34 /
interrupt.py:174 实测口径）；SceneView = JSON-clean 纯 dict
（``json.dumps`` 零失败）；零 clock/RNG 参数、零 wall-clock / 零随机
（同输入恒同输出）；12 名闭集零命中。
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final, TypedDict

from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.space import SPACES_COMPONENT, decode_spaces
from src.engine_v2.core.state import WorldState
from src.engine_v2.presentation.tactical.layout import build_tactical_layout

if TYPE_CHECKING:
    from src.engine_v2.core.entity import EntityView

__all__ = [
    "PresentationError",
    "VIEW_SCHEMA_VERSION",
    "SceneView",
    "scene_id_of",
    "derive_scene_view",
]

#: code 闭集（SOT §3.1；P8 ``P8_ERROR_CODES`` ctor 闭集校验先例）。
PRESENTATION_ERROR_CODES: Final[frozenset[str]] = frozenset(
    {
        "presentation_invalid",
        "scene_key_invalid",
        "intent_schema_invalid",
        "image_backend_error",
    }
)

#: 可见 actor / location 的 tag 面（world 组件面；Kernel 不定义词表，
#: 本模块取 fixture 词表同串约定）。
_ACTOR_TAG: Final[str] = "actor"
_LOCATION_TAG: Final[str] = "location"

#: display 组件 = 世界展示面（D-8 不透明 JSON payload；键 = ``name`` /
#: ``mood`` / ``description``）；缺失时回落确定性缺省值。
_DISPLAY_COMPONENT: Final[ComponentTypeId] = ComponentTypeId("display")

#: 确定性缺省常量（场景标识 / 展示名 / 情绪 / 天气 / 时段）。
_FALLBACK_SCENE_IDENTIFIER: Final[str] = "world"
_FALLBACK_LOCATION_NAME: Final[str] = "unknown"
_FALLBACK_MOOD: Final[str] = "calm"
_FALLBACK_WEATHER: Final[str] = "unknown"
_FALLBACK_TIME_OF_DAY: Final[str] = "unknown"

#: 世界侧逻辑刻 / 日历时间 / 天气的 ``world_variables`` 键名
#: （P1 D-6 世界时间事实面，state.py:27–34）。
_WORLD_VARIABLE_LOGICAL_TICK: Final[str] = "logical_tick"
_WORLD_VARIABLE_GAME_TIME: Final[str] = "game_time"
_WORLD_VARIABLE_WEATHER: Final[str] = "weather"

_AUTHORING_PREFIX: Final[str] = "ent_authoring_"


class PresentationError(Exception):
    """presentation + adapters/web 单一错误族（P8 ``PersistenceError`` 先例）。

    - ``code`` ∈ :data:`PRESENTATION_ERROR_CODES`（ctor 闭集校验；闭集外
      → ``ValueError``——编程错误，不属 P10 错误面）；
    - ``str(exc) = "[code] message"``（稳定面）。
    """

    def __init__(self, message: str, *, code: str = "presentation_invalid") -> None:
        if code not in PRESENTATION_ERROR_CODES:
            raise ValueError(
                f"PresentationError.code {code!r} 不在 PRESENTATION_ERROR_CODES "
                f"闭集：{sorted(PRESENTATION_ERROR_CODES)}"
            )
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


VIEW_SCHEMA_VERSION: Final[int] = 1


class SceneView(TypedDict, total=False):
    """P10 结构化 ViewState（SOT §3.1；10 键逐字，JSON-clean 纯 dict）。

    派生数据（Spec §8.5：MUST NOT authoritative）；``derive_scene_view``
    返回与 WorldState 零别名共享的新容器（P10-INV-1）。顶层 ``clock``
    与 ``narrative.clock`` 双存合法（后者 = P9 5 键逐字兼容面 A7/t6 钉，
    前者 = P10 顶层面；Leader 终审注记）。
    """

    schema: int
    view_revision: int
    scene_id: str
    tick: int
    narrative: dict
    actors: list[dict]
    environment: dict
    tactical_overlay: dict | None
    image_slot: dict | None
    clock: dict


def scene_id_of(scene_key: tuple[str, ...]) -> str:
    """纯函数：``"scene:" + sha256("|".join(scene_key)).hexdigest()[:12]``。

    scene_key = (世界/场景标识, 可见 actor id 排序元组)（D-P10-12；
    T08 连续性面）。空 key / 非 str 元素 →
    :class:`PresentationError`（code="scene_key_invalid"）。
    """
    if not scene_key or any(not isinstance(part, str) for part in scene_key):
        raise PresentationError(
            f"scene_key 必须为非空 str 元组，得到 {scene_key!r}",
            code="scene_key_invalid",
        )
    digest = hashlib.sha256("|".join(scene_key).encode("utf-8")).hexdigest()
    return "scene:" + digest[:12]


def _slug(entity_id: str) -> str:
    """实体 id → 展示 slug（去 ``ent_authoring_`` 前缀；确定性）。"""
    if entity_id.startswith(_AUTHORING_PREFIX):
        return entity_id[len(_AUTHORING_PREFIX) :]
    return entity_id


def _display_field(view: EntityView, key: str) -> str | None:
    """display 组件的 str 值（缺失 / 非 str / 空串 → None）。"""
    payload = view.get_component(_DISPLAY_COMPONENT)
    if payload is None:
        return None
    value = payload.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _primary_location(world: WorldState) -> tuple[str, EntityView] | None:
    """主 location = tags 含 ``location`` 的实体（排序最小 id；零则 None）。"""
    for entity_id, record in sorted(world.entities.items(), key=lambda p: str(p[0])):
        if _LOCATION_TAG in record.tags:
            return str(entity_id), world.entity_view(entity_id)
    return None


def _scene_identifier(world: WorldState) -> str:
    """世界/场景标识（D-P10-12）：主 location id → scenario_id → 兜底。"""
    location = _primary_location(world)
    if location is not None:
        return location[0]
    scenario_id = world.scenario_state.scenario_id
    if scenario_id:
        return scenario_id
    return _FALLBACK_SCENE_IDENTIFIER


def _sorted_actor_ids(world: WorldState) -> tuple[str, ...]:
    """可见 actor id 排序元组（tags 含 ``actor``；world 无可见性子系统，
    表现层取全部 actor-tag 实体——确定性）。"""
    return tuple(
        sorted(
            str(entity_id)
            for entity_id, record in world.entities.items()
            if _ACTOR_TAG in record.tags
        )
    )


def _as_int(value: Any) -> int | None:
    """JsonValue → 非 bool int（否则 None）。"""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _logical_tick(world: WorldState) -> int:
    """当前逻辑刻 = ``world_variables["logical_tick"]`` 投影（缺省 0）。"""
    return _as_int(world.world_variables.get(_WORLD_VARIABLE_LOGICAL_TICK)) or 0


def _game_time(world: WorldState) -> dict[str, Any] | None:
    """日历时间（结构化世界事实）；dict 值新建容器（零别名）。"""
    value = world.world_variables.get(_WORLD_VARIABLE_GAME_TIME)
    if isinstance(value, Mapping):
        return dict(value)
    return None


def _time_of_day(game_time: dict[str, Any] | None) -> str:
    """日历 hour → 时段词（确定性分桶：[5,12) 上午 / [12,18) 下午 /
    [18,22) 晚间 / 其余 夜间；hour 缺失或越界 → 缺省）。"""
    hour = _as_int(game_time.get("hour") if game_time is not None else None)
    if hour is None or not 0 <= hour <= 23:
        return _FALLBACK_TIME_OF_DAY
    if 5 <= hour < 12:
        return "上午"
    if 12 <= hour < 18:
        return "下午"
    if 18 <= hour < 22:
        return "晚间"
    return "夜间"


def _environment(world: WorldState) -> dict[str, str]:
    """环境描述面（v1 snapshot():442 环境键语义参照）：location /
    description / time_of_day / weather，全部确定性投影。"""
    location = _primary_location(world)
    location_name = _FALLBACK_LOCATION_NAME
    description = ""
    if location is not None:
        location_id, view = location
        location_name = _display_field(view, "name") or _slug(location_id)
        description = _display_field(view, "description") or ""
    weather_value = world.world_variables.get(_WORLD_VARIABLE_WEATHER)
    weather = (
        weather_value
        if isinstance(weather_value, str) and weather_value
        else _FALLBACK_WEATHER
    )
    return {
        "location": location_name,
        "description": description,
        "time_of_day": _time_of_day(_game_time(world)),
        "weather": weather,
    }


def _position_projection(record: EntityRecord) -> dict[str, Any]:
    """位置按空间域投影（core ``decode_spaces``:492 冻结 codec；载荷 =
    ``EntityRecord.components`` 原始字段面；dict 位置新建容器，零别名；
    无 spaces 组件 → ``{}``）。"""
    payload = record.components.get(SPACES_COMPONENT)
    if payload is None:
        return {}
    positions: dict[str, Any] = {}
    for mapping in decode_spaces(payload):
        position = mapping.position
        if isinstance(position, Mapping):
            positions[mapping.domain_id] = dict(position)
        else:
            positions[mapping.domain_id] = position
    return positions


def derive_scene_view(
    world: WorldState, *, tactical_domain_id: str | None = None
) -> SceneView:
    """纯派生：WorldState 只读 → SceneView（SOT §3.1；P10-INV-1）。

    键面（10 键逐字）：

    - ``schema`` = :data:`VIEW_SCHEMA_VERSION`；
    - ``view_revision`` = ``world.world_revision`` 投影（P10-INV-2）；
    - ``scene_id`` = ``scene_id_of((场景标识, actor 排序元组))``
      （D-P10-12）；
    - ``tick`` = 世界侧逻辑刻投影（缺省 0；零 clock 参数，D6）；
    - ``narrative`` = P9 NarrativeView 5 键兼容面
      （tick / scene_text / frames / actors_visible / clock）P10 自派生
      投影（零 P9 函数调用，D-P10-01）；frames = []（W1 期 world 面无
      帧源，帧为宿主事件流面）；
    - ``actors`` = 可见 actor 面（id 排序；``{"id", "name", "position",
      "mood", "tags"}``，position 按空间域投影）；
    - ``environment`` = 环境描述面（4 键）；
    - ``tactical_overlay``：``tactical_domain_id`` 非 None 时经
      ``build_tactical_layout(world, domain_id=tactical_domain_id)``
      填充（SOT §3.1/§3.6；ERR-P10-11 闭集增行，单向依赖零环）；
      None → None（W1 默认分支不变，test_view t4 钉面零影响）；
    - ``image_slot``：None（纯函数钉；回投 = 会话层槽唯一写入点，W4）；
    - ``clock`` = ``{"logical_tick", "game_time"}``（P9 NarrativeView.
      clock 同形）。

    零反作用：返回容器与 WorldState 零别名（嵌套 dict 全部新建）；
    同输入恒同输出（D6 双跑字节相等）。
    """
    if tactical_domain_id is not None:
        tactical_overlay = build_tactical_layout(world, domain_id=tactical_domain_id)
    else:
        tactical_overlay = None
    tick = _logical_tick(world)
    actor_ids = _sorted_actor_ids(world)
    environment = _environment(world)
    actors: list[dict[str, Any]] = []
    for entity_id in actor_ids:
        view = world.entity_view(entity_id)
        record = world.entities[entity_id]
        actors.append(
            {
                "id": str(entity_id),
                "name": _display_field(view, "name") or _slug(str(entity_id)),
                "position": _position_projection(record),
                "mood": _display_field(view, "mood") or _FALLBACK_MOOD,
                "tags": list(record.tags),
            }
        )
    narrative: dict[str, Any] = {
        "tick": tick,
        "scene_text": (
            f"{environment['location']}（{environment['time_of_day']}"
            f"，{environment['weather']}）"
        ),
        "frames": [],
        "actors_visible": list(actor_ids),
        "clock": {"tick": tick},
    }
    clock: dict[str, Any] = {
        "logical_tick": tick,
        "game_time": _game_time(world),
    }
    return SceneView(
        schema=VIEW_SCHEMA_VERSION,
        view_revision=int(world.world_revision),
        scene_id=scene_id_of((_scene_identifier(world), *actor_ids)),
        tick=tick,
        narrative=narrative,
        actors=actors,
        environment=environment,
        tactical_overlay=tactical_overlay,
        image_slot=None,
        clock=clock,
    )
