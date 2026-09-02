"""P10 presentation 层 tactical 最小面：结构化布局（T04 波；SOT §3.6；
导出 3 名）。

来源 = Plan §19 目标「Text / Image / Tactical presentation 平行结构」
+ Spec §44 L2201（presentation/tactical/）；G10 无 tactical 专属自动
判据（简报 §8.4）→ 最小面 = 结构化布局 dict（JSON-clean，无渲染）
（D-P10-04）。

冻结消费面（只读，SOT §2.1/§3.6）：core ``space``（``SPACES_COMPONENT``
:447 / ``decode_spaces``:492 / ``GraphSpace``:256 / ``GridSpace``:350）。
位置面注记（F2 core 坑规避，W1 先例同形）：经
``EntityRecord.components`` 原始字段面 + 冻结 codec ``decode_spaces``
消费；禁 ``entity_domain_positions(EntityView)``（space.py:505）——
其对 grid 域 dict 位置的 pydantic 复校验拒绝 ``MappingProxyType``
（core 坑本身已转 SOT §9 勘误链，ERR-P10-08 候选）。

几何事实面（宿主镜像，本模块 docstring 钉 = 宿主契约面）：
``WorldState.world_variables`` 保留键 ``spatial_domains`` =
``{domain_id: 几何事实}``（宿主 = conftest / 会话层把 SpaceRegistry
域几何持久化为 JSON 世界事实；P1 D-6 世界事实载体面先例 =
``logical_tick`` / ``game_time`` / ``weather``，state.py:253/278）：

- graph 域（GraphSpace 既有边表，P9 已映射）：``{"kind": "graph",
  "nodes": [str, ...], "edges": [[str, str], ...]}``——布局先做无向
  规范化（(min, max) 去重排序）再经 core 冻结构造器 G-INV 校验；
- grid 域（GridSpace）：``{"kind": "grid", "cols": int, "rows":
  int}``——经 core 冻结构造器 S-INV 校验（w/h ≤ 0 / 非 int → 拒绝）。

域在位判定（SOT §3.6「域缺席」语义面，本模块 docstring 钉）：几何
事实在位或任一实体在该域有位置映射 → 在位；两者皆无 → 域缺席（
:class:`_TacticalLayoutError`，code="scene_key_invalid"）。几何事实
缺席但域内存在位置映射 → ``grid = None``（cells / actors 仍投影——
宿主未镜像几何事实的降级面）。

mode 面（SOT §3.6）：``world_variables`` 保留键 ``active_modes`` =
[str, ...]（宿主镜像 RuntimeState 活跃模式 id 面；缺失 → None）。

错误族注记（Leader 裁决转 P10 SOT §9 勘误链 ERR-P10-13 已裁定）：
SOT §3.6 原钉名
``PresentationError(code="scene_key_invalid")`` 的类定义于
``presentation/view.py``——自本模块顶层 import 之与 §3.0 闭集
（tactical/* = stdlib + engine_v2.core）+ ERR-P10-11「单向依赖零
环」裁定构成 view↔tactical import 环（两种 import 序顶层 import 均
ImportError，W3 dev 实测，报告证据在案）→ 本波按闭集落码 =
ValueError 族私有具名错误（``code`` 属性面保留 §3.6 钉值）。

纪律（P10-INV-1/10，D6，K8）：纯函数 WorldState 只读（零反作用，
A11/t3）；JSON-clean（``json.dumps`` 零失败）；零 wall-clock / 零
随机（同输入恒同输出）；12 名闭集零命中；零 modules/space.py import
（SOT §3.6：hex 几何 = 域内 GraphSpace 既有边表，P9 已映射）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, TypedDict

from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.space import (
    GraphSpace,
    GridSpace,
    SPACES_COMPONENT,
    SpaceInvariantError,
    decode_spaces,
)
from src.engine_v2.core.state import WorldState

__all__ = [
    "TACTICAL_LAYOUT_SCHEMA_VERSION",
    "TacticalLayout",
    "build_tactical_layout",
]

TACTICAL_LAYOUT_SCHEMA_VERSION: Final[int] = 1

#: world_variables 保留键 = 域几何事实宿主镜像（docstring 钉；宿主契约面）。
_SPACES_FACT_KEY: Final[str] = "spatial_domains"

#: world_variables 保留键 = 活跃模式 id 宿主镜像（docstring 钉；宿主契约面）。
_MODES_FACT_KEY: Final[str] = "active_modes"

#: actor tag 面（view.py 同形约定；Kernel 不定义词表）。
_ACTOR_TAG: Final[str] = "actor"

#: 几何事实 kind 闭集（core ``SPATIAL_BACKEND_KINDS`` 的 P4 已实现两值）。
_KIND_GRAPH: Final[str] = "graph"
_KIND_GRID: Final[str] = "grid"


class TacticalLayout(TypedDict):
    """JSON-clean 布局面（SOT §3.6；7 键，无渲染）。

    - ``grid`` = 域网格参数（GraphSpace 域 = {"nodes","edges"} 规范化
      摘要；GridSpace 域 = {"cols","rows"}；几何事实缺席 → None）；
    - ``cells`` = 占据单元格（actor id 排序序、单元格去重保首现；
      graph 域 = {"node": 节点 id}，grid 域 = 位置 dict 同形）；
    - ``actors`` = 域内 actor 位置面（{"id","position"}，actor id
      排序序）；
    - ``mode`` = 活跃模式 id 镜像（{"active_modes": [...]}；缺失 →
      None）。
    """

    schema: int
    view_revision: int
    domain_id: str
    grid: dict | None
    cells: list[dict]
    actors: list[dict]
    mode: dict | None


class _TacticalLayoutError(ValueError):
    """tactical 布局构造错误（域缺席 / 几何事实面违例）。

    SOT §3.6 钉名 = PresentationError(code="scene_key_invalid")——该
    类定义于 presentation/view.py，自本模块顶层 import 之构成
    view↔tactical import 环（§3.0 闭集 + ERR-P10-11 零环裁定下两
    import 序均 ImportError，W3 dev 实测；Leader 裁决转 P10 SOT
    §9 勘误链 ERR-P10-13 已裁定）→
    按闭集落码为 ValueError 族私有具名错误；``code`` 属性面保留
    §3.6 钉值。``str(exc) = "[code] message"``（PresentationError
    同形稳定面）。
    """

    def __init__(self, message: str, *, code: str = "scene_key_invalid") -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


def _fact_error(message: str) -> _TacticalLayoutError:
    """几何事实面违例（code="presentation_invalid"；P10 错误族 code
    闭集同面值）。"""
    return _TacticalLayoutError(message, code="presentation_invalid")


def _geometry_facts(world: WorldState) -> dict[str, Any]:
    """world_variables 域几何事实面（缺失 → 空映射；非对象 → 事实面
    错误）。"""
    value = world.world_variables.get(_SPACES_FACT_KEY)
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise _fact_error(
            f"world_variables[{_SPACES_FACT_KEY!r}] 必须为对象（域 → "
            f"几何事实）：{type(value).__name__}"
        )
    return dict(value)


def _graph_summary(fact: Mapping[str, Any]) -> dict[str, Any]:
    """graph 域几何事实 → 规范化摘要 {"nodes","edges"}（SOT §3.6）。

    键面闭集 {"kind","nodes","edges"}（P9 MAPPING_RULES 严格口径）；
    无向规范化 = (min, max) 去重排序（宿主持久化有向 32 边或无向
    16 边均收敛同面）→ core ``GraphSpace`` 冻结构造器 G-INV 校验
    （重复节点 / 重复无向边 / 自环 → 拒绝，fail-loud 零静默降级）。
    """
    if set(fact) != {"kind", "nodes", "edges"}:
        raise _fact_error(
            f"graph 几何事实键面必须为 {['kind', 'nodes', 'edges']}：{sorted(fact)}"
        )
    nodes = fact["nodes"]
    edges = fact["edges"]
    if not isinstance(nodes, list) or not all(
        isinstance(node, str) for node in nodes
    ):
        raise _fact_error("graph 几何事实 nodes 必须为 str 列表")
    if not isinstance(edges, list) or not all(
        isinstance(edge, (list, tuple))
        and len(edge) == 2
        and all(isinstance(endpoint, str) for endpoint in edge)
        for edge in edges
    ):
        raise _fact_error("graph 几何事实 edges 必须为 [str, str] 列表")
    canonical = sorted({(min(a, b), max(a, b)) for a, b in edges})
    try:
        GraphSpace(nodes=list(nodes), edges=[(a, b) for a, b in canonical])
    except SpaceInvariantError as exc:
        raise _fact_error(f"graph 几何事实未过 core G-INV 校验：{exc}") from exc
    return {
        "nodes": sorted(nodes),
        "edges": [[a, b] for a, b in canonical],
    }


def _grid_summary(fact: Mapping[str, Any]) -> dict[str, Any]:
    """grid 域几何事实 → {"cols","rows"}（SOT §3.6；键面闭集
    {"kind","cols","rows"}；core ``GridSpace`` 冻结构造器 S-INV 校验
    同形：w/h ≤ 0 / 非 int（含 bool）→ 拒绝）。"""
    if set(fact) != {"kind", "cols", "rows"}:
        raise _fact_error(
            f"grid 几何事实键面必须为 {['kind', 'cols', 'rows']}：{sorted(fact)}"
        )
    cols = fact["cols"]
    rows = fact["rows"]
    for name, value in (("cols", cols), ("rows", rows)):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise _fact_error(f"grid 几何事实 {name} 必须为正 int：{value!r}")
    GridSpace(width=cols, height=rows)
    return {"cols": cols, "rows": rows}


def _mode_projection(world: WorldState) -> dict[str, list[str]] | None:
    """活跃模式 id 镜像面（SOT §3.6 mode 键；缺失 → None；非 str 列表
    → 事实面错误）。"""
    value = world.world_variables.get(_MODES_FACT_KEY)
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, str) for item in value
    ):
        raise _fact_error(
            f"world_variables[{_MODES_FACT_KEY!r}] 必须为 str 列表（宿主镜像面）"
        )
    return {"active_modes": [str(item) for item in value]}


def _domain_position(record: EntityRecord, domain_id: str) -> Any | None:
    """实体在该域的位置映射（W1 规避模式：``components`` 原始字段面 +
    冻结 codec ``decode_spaces``；S-INV-3 保证一域至多一映射）；无
    spaces 组件 / 无该域映射 → None。"""
    payload = record.components.get(SPACES_COMPONENT)
    if payload is None:
        return None
    for mapping in decode_spaces(payload):
        if mapping.domain_id == domain_id:
            return mapping.position
    return None


def _domain_occupancy(
    world: WorldState, domain_id: str, *, grid_domain: bool
) -> tuple[list[dict], list[dict]]:
    """(cells, actors) = 域内占据单元格 + actor 位置面（actor id 排序
    序；单元格去重保首现序；位置容器零别名——Mapping 新建 dict，
    W1 同形纪律）。"""
    cells: list[dict] = []
    actors: list[dict] = []
    seen: set[str] = set()
    for entity_id, record in sorted(world.entities.items(), key=lambda p: str(p[0])):
        if _ACTOR_TAG not in record.tags:
            continue
        position = _domain_position(record, domain_id)
        if position is None:
            continue
        if isinstance(position, Mapping):
            cloned: Any = dict(position)
        else:
            cloned = position
        actors.append({"id": str(entity_id), "position": cloned})
        if grid_domain and isinstance(cloned, Mapping):
            cell = dict(cloned)
        elif grid_domain:
            # 防御面（非钉面）：grid 域位置应为 x/y 对象，异型原样
            # 包封保持 JSON-clean。
            cell = {"cell": cloned}
        else:
            cell = {"node": cloned}
        key = repr(cell)
        if key not in seen:
            seen.add(key)
            cells.append(cell)
    return cells, actors


def build_tactical_layout(
    world: WorldState, *, domain_id: str = "default"
) -> TacticalLayout:
    """纯函数：WorldState 只读 → TacticalLayout（SOT §3.6；P10-INV-1/
    10；A11）。

    键面（7 键逐字序）：

    - ``schema`` = :data:`TACTICAL_LAYOUT_SCHEMA_VERSION`；
    - ``view_revision`` = ``world.world_revision`` 投影；
    - ``domain_id`` = 入参面值回显；
    - ``grid`` = 域网格参数（graph 域 = {"nodes","edges"} 规范化摘要；
      grid 域 = {"cols","rows"}；几何事实缺席 → None）；
    - ``cells`` = 占据单元格（actor id 排序、去重）；
    - ``actors`` = 域内 actor 位置面（{"id","position"}，actor id
      排序）；
    - ``mode`` = 活跃模式 id 镜像（缺失 → None）。

    域缺席（几何事实与域内位置映射皆无）→
    :class:`_TacticalLayoutError`（code="scene_key_invalid"，§3.6 钉
    面）。零反作用：返回容器与 WorldState 零别名；同输入恒同输出
    （D6）。
    """
    facts = _geometry_facts(world)
    fact = facts.get(domain_id)
    if fact is not None and not isinstance(fact, Mapping):
        raise _fact_error(
            f"空间域 {domain_id!r} 几何事实必须为对象：{type(fact).__name__}"
        )
    grid: dict[str, Any] | None = None
    grid_domain = False
    if fact is not None:
        kind = fact.get("kind")
        if kind == _KIND_GRAPH:
            grid = _graph_summary(fact)
        elif kind == _KIND_GRID:
            grid = _grid_summary(fact)
            grid_domain = True
        else:
            raise _fact_error(
                f"空间域 {domain_id!r} 几何事实 kind 必须为 graph/grid：{kind!r}"
            )
    cells, actors = _domain_occupancy(world, domain_id, grid_domain=grid_domain)
    if grid is None and not actors:
        raise _TacticalLayoutError(
            f"域缺席：空间域 {domain_id!r} 无几何事实且无实体位置映射"
        )
    return TacticalLayout(
        schema=TACTICAL_LAYOUT_SCHEMA_VERSION,
        view_revision=int(world.world_revision),
        domain_id=domain_id,
        grid=grid,
        cells=cells,
        actors=actors,
        mode=_mode_projection(world),
    )
