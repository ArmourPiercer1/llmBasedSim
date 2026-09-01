"""P9 W3 官方模块：perception（T06；SOT §3.6；导出 4 名）。

来源 = v1 ``sensory_filter``（src/graph/game_graph.py:591，§43.3 第 7
项重写：v1 = 推理感知节点 → v2 = 纯函数，K5 重写面）+ 43.1-9
（perception/knowledge 分离思想）；**43.2-6（global event text copied
to NPC memory）移除**——本模块零全局事件消费（P9-INV-7）。

冻结消费（SOT §3.0 导入闭集）：stdlib + core ``knowledge``
（``ObservationRecord``:109）+ core ``ids``（``ObservationId``:150）
+ 模块公共面 ``modules.base``（``ModuleIdentity`` /
``OFFICIAL_MODULE_VERSION``）。距离语义对齐 kernel 冻结面 core
``space``（``SpaceBackend.distance``:163 docstring "grid = 曼哈顿"）；
本模块**不 import** ``modules.space``（W6 交付；声明面 = SOT §3.1.2
表 requires = ("llmsim-standard-space",)）。

纪律（K2/K5/D6）：``build_observations`` = 纯函数——输入不含
event_log / 全局状态（P9-INV-7 签名级保证）；零模块级可变对象；零
uuid / random / wall-clock（observation_id = 确定性派生，D6）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from src.engine_v2.core.ids import ObservationId
from src.engine_v2.core.knowledge import ObservationRecord
from src.engine_v2.modules.base import OFFICIAL_MODULE_VERSION, ModuleIdentity

__all__ = [
    "PerceptionRange",
    "ObservationSource",
    "PerceptionResult",
    "build_observations",
]

#: 模块身份（SOT §3.1.2 MODULE_REQUIRES 表：perception 声明
#: requires = ("llmsim-standard-space",)——距离查询经空间域 = 声明面；
#: 本模块距离语义对齐 kernel core/space.py，不 import ``modules/
#: space.py``（W6 交付，本波不存在））。
IDENTITY: Final[ModuleIdentity] = ModuleIdentity(
    "llmsim-standard-perception", OFFICIAL_MODULE_VERSION,
    ("llmsim-standard-space",),
)


@dataclass(frozen=True)
class PerceptionRange:
    """观察者感知半径（SOT §3.6 表行 1）。

    来源段 = 宿主从 ``PlayerSpec.capabilities``（content/schemas.py:227）
    / NPC 能力表（core capability.py:106 ``CapabilityTable``）投影——本
    模块零投影逻辑（宿主职责）。
    """

    sight_m: float
    hearing_m: float


@dataclass(frozen=True)
class ObservationSource:
    """一次感知批次的来源标记（SOT §3.6 表行 2）。

    ``domain`` = 空间域 id（来源标记透传；本模块不建 backend，零拓扑
    消费）。
    """

    observer_id: str
    domain: str
    tick: int


@dataclass(frozen=True)
class PerceptionResult:
    """感知输出 = 仅 ``ObservationRecord`` 元组（SOT §3.6 表行 3；
    零 knowledge 直写）。"""

    source: ObservationSource
    records: tuple[ObservationRecord, ...]


def _manhattan_distance(
    pos_a: Mapping[str, int],
    pos_b: Mapping[str, int],
) -> int:
    """曼哈顿 L1 距离（kernel 网格语义，core ``SpaceBackend.distance``
    :163 docstring "grid = 曼哈顿"）。

    对齐 v1 src/graph/game_graph.py:50（``_distance``，:50–54；v1 =
    欧氏 3D → v2 = 曼哈顿 L1，§43.3 第 7 项重写披露面）：两位置映射
    全部键并集，缺键取 0（v1 ``.get(key, 0)`` 默认面，:51–53）。
    """
    keys = set(pos_a) | set(pos_b)
    return sum(abs(pos_a.get(key, 0) - pos_b.get(key, 0)) for key in keys)


def _make_record(
    observer_id: str,
    entity_id: str,
    kind: str,
    distance: int,
    source: ObservationSource,
) -> ObservationRecord:
    """单条观察记录（确定性构造；D6：零 uuid / 零随机）。

    ``observation_id`` = ``obs_<observer>_<entity>_<kind>_<tick>``
    （``ObservationId``，core ids.py:150；构造不做词法校验 = 确定性构造
    合法，``_TypedId`` docstring（ids.py:83–85）§2.2 通用规则；正文文法
    ``[a-z0-9_]+``（ids.py:70 ``PREFIX_BODY_PATTERN``））——含 observer/
    entity/感官/tick 因子，保证跨 tick 唯一。
    """
    return ObservationRecord(
        observation_id=ObservationId(
            f"obs_{observer_id}_{entity_id}_{kind}_{source.tick}"
        ),
        actor_id=observer_id,
        tick=source.tick,
        payload={
            "kind": kind,
            "entity_id": entity_id,
            "distance_m": distance,
        },
        observed_entity_ids=(entity_id,),
        cause_event_id=None,
    )


def build_observations(
    world_positions: Mapping[str, Mapping[str, int]],
    observers: Mapping[str, PerceptionRange],
    entities: Mapping[str, Mapping[str, object]],
    source: ObservationSource,
) -> PerceptionResult:
    """对齐 v1 src/graph/game_graph.py:591（``sensory_filter`` 节点；
    §43.3 第 7 项重写：v1 = 推理感知节点 → v2 = 纯函数，K5 重写面）。

    纯函数：每观察者 × 每可感知实体，距离 ≤ 半径 →
    ``ObservationRecord``（sight/hearing 分类）；**输入不含
    event_log / 全局状态**（签名级保证 P9-INV-7；43.2-6 移除）。
    ``observers`` 映射驱动（宿主可传单观察者映射 = 单批次；
    ``source`` = 批次来源标记：记录 tick/domain 统一取自 ``source``）。

    语义（确定性；W3 测试钉面）：

    - 距离 = 曼哈顿 L1（整数坐标 Mapping；对齐 kernel
      ``SpaceBackend.distance`` 网格语义，core space.py:163）；v1
      ``_distance``（game_graph.py:50）= 欧氏 3D → v2 曼哈顿 =
      §43.3 第 7 项重写披露面；
    - 观察者无位置 → 该观察者零记录（v1 ``_find_nearby_chars`` 参考
      位置缺席面，game_graph.py:72 ``if not ref_pos: return []``）；
    - 自排除：``entity_id == observer_id`` 不感知（v1 self-skip，
      game_graph.py:76–77）；
    - ``entities`` 有 id 而 ``world_positions`` 无 → 不可感知（零
      记录；v1 ``if char_pos and ...`` 面，game_graph.py:79）；
    - ``entities`` 值面不消费（v1 将 char dict 附入结果列表；v2 记录
      payload = JSON-native 最小面，实体属性数据由宿主经 entity id
      回查）；
    - 判定：``distance <= sight_m`` → 产 1 条 sight 记录；
      ``distance <= hearing_m`` → 产 1 条 hearing 记录；两半径同中 =
      2 条记录（每感官各 1）；
    - 记录全序 = ``(observer_id, entity_id, kind 串值)`` 升序
      （``"hearing"`` < ``"sight"`` 字母序）；
    - 每条记录：``actor_id`` = 观察者 id；``tick`` = ``source.tick``；
      ``observed_entity_ids`` = ``(entity_id,)``；``cause_event_id`` =
      None；``payload`` = ``{"kind": <感官>, "entity_id": <实体 id>,
      "distance_m": <曼哈顿距离>}``（JSON-native 最小面：感官分类 +
      所观测实体引用 + 距离值）。
    """
    records: list[ObservationRecord] = []
    for observer_id in sorted(observers):
        observer_range = observers[observer_id]
        observer_pos = world_positions.get(observer_id)
        if observer_pos is None:
            continue
        for entity_id in sorted(entities):
            if entity_id == observer_id:
                continue
            entity_pos = world_positions.get(entity_id)
            if entity_pos is None:
                continue
            distance = _manhattan_distance(observer_pos, entity_pos)
            if distance <= observer_range.sight_m:
                records.append(
                    _make_record(
                        observer_id, entity_id, "sight", distance, source,
                    ),
                )
            if distance <= observer_range.hearing_m:
                records.append(
                    _make_record(
                        observer_id, entity_id, "hearing", distance, source,
                    ),
                )
    records.sort(
        key=lambda record: (
            record.actor_id,
            record.observed_entity_ids[0],
            str(record.payload["kind"]),
        ),
    )
    return PerceptionResult(source=source, records=tuple(records))
