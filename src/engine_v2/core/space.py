"""engine_v2 core 层 Space 空间语义：空间形态词表、空间域、后端协议、注册表与
后端工厂、实体-空间映射编解码（P4-T05/T06/T07，§3.7 全量：T05 上半 + T06/T07 下半）。

依据 ``docs/v2/contracts/P4-actor-context-space-mode-design.md``（下称"设计文档"）：

- **§3.7 上半（P4-T05 范围）**：本模块 10 个导出符号（按 §3.7 代码块条目序）——
  :data:`SPATIAL_BACKEND_KINDS` / :class:`SpatialDomain` / :class:`SpaceBackend` /
  :data:`INF_DISTANCE` / :class:`SpaceRegistry` / :func:`make_backend` /
  :class:`UnknownDomainError` / :class:`UnknownBackendError` /
  :class:`InvalidPositionError` / :class:`SpaceInvariantError`；
- **Spec:1354-1361（§24 空间形态词表）**：6 种空间形态 →
  :data:`SPATIAL_BACKEND_KINDS`（小写 token 化逐字；P4 实现 graph/grid，余为
  reserved 扩展位）；
- **Spec:1365-1372（§24.2）**：多 named spatial domains → :class:`SpatialDomain`
  （domain_id 命名 + backend_kind + parameters）；
- **Spec:1345 / 1348-1350（"空间 MUST 可替换"）**：:class:`SpaceBackend` 协议
  （四方法纯函数契约）+ :func:`make_backend` 构造侧；reserved kind 显式拒绝
  （不静默降级）→ :class:`UnknownBackendError`；
- **S-INV-1 / S-INV-2（§3.7 构造期不变量）**：``domain_id`` 匹配
  ``^[a-z][a-z0-9_]*$``（pydantic pattern → ValidationError）；``backend_kind`` ∈
  :data:`SPATIAL_BACKEND_KINDS`（validator → :class:`SpaceInvariantError`）——
  均在构造期拒绝；S-INV-2 直接构造路径抛具名类型（
  :meth:`SpatialDomain.__init__` 覆盖），pydantic 校验路径
  （``model_validate`` / ``model_validate_json``）由 pydantic 重抛为
  ``ValidationError``（ValueError 子类，同族口径，D-P4-17），S-INV-2 文案保留；
- **S-INV-4 / S-INV-5（§3.7 :class:`SpaceRegistry`）**：键必须 == ``domain_id``
  + backend_kind ↔ backend isinstance 核对（graph→GraphSpace / grid→GridSpace），
  违反 → :class:`SpaceInvariantError`；未注册查找 →
  :class:`UnknownDomainError`（查找点抛出，D-P3-16 双轨同纪律）；
- **D-P4-11（backend 只读配置 / INV-P4-3）**：无公开变更 API——
  :class:`SpaceRegistry` / backend 全部几何构造期注入，运行期零状态变更，
  四方法全纯；
- **D-P4-12（距离语义）**：BFS 跳数（float）/ 曼哈顿；:data:`INF_DISTANCE =
  float("inf")` 是纯函数返回值，**永不**写入任何组件/事件（inf 永不入 JSON，
  P1 §0.2 铁律 1 的落位）；
- **D-P4-17（错误分类两族）**：LookupError 族 =
  :class:`UnknownDomainError` / :class:`UnknownBackendError`；ValueError 族 =
  :class:`InvalidPositionError` / :class:`SpaceInvariantError`；测试按族断言
  基类。

**T05/T06/T07 分工（已完成）**（设计文档 §3.12 同文件单 Owner 串行交付）：下半 8 导出
（``SpacePosition`` / ``GraphSpace`` / ``GridSpace`` / ``SpaceMapping`` /
``SPACES_COMPONENT`` / ``encode_spaces`` / ``decode_spaces`` /
``entity_domain_positions``）已由 P4-T06/T07（Wave B）于本文件**末尾追加**；
:class:`SpaceBackend` 协议签名引用 ``SpacePosition``，:func:`make_backend` 的
graph/grid 分派体与 :class:`SpaceRegistry` 的 S-INV-5 isinstance 核对引用
``GraphSpace`` / ``GridSpace``——均为**调用期**名称解析，现全部为模块内定义；
Wave A 窗口内存在的顶部 ``if TYPE_CHECKING`` 自导入块（运行时零 import，口径同
``scheduler.py`` / ``components.py`` 前向引用）因下半名称由模块内定义收编而成为
死重，已删除。:data:`__all__` 已补全至 18 项（上半 10 项保持原序，下半 8 项按其
代码块条目序末尾追加；名称集与设计文档 §8.3 账本 space 行完全一致，模块内顺序
允许与代码块顺序不同）。

Import 边界（设计文档 §3.3 依赖图 / §3.4 黑名单 / §5.5 M1）：本模块只 import
标准库、pydantic 与同包 ``src.engine_v2``（entity → ContractModel, EntityView）；asyncio /
random / datetime / time / uuid / json 直接 import / os / subprocess / 网络栈
全部缺席；无云模型 / 网络 / 随机性；M1④ 封闭 12 标识符集 0 命中。
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any, Final, Protocol

from pydantic import Field, JsonValue, ValidationError, field_validator
from pydantic import model_validator

from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.entity import EntityView

__all__ = [
    "SPATIAL_BACKEND_KINDS",
    "SpatialDomain",
    "SpaceBackend",
    "INF_DISTANCE",
    "SpaceRegistry",
    "make_backend",
    "UnknownDomainError",
    "UnknownBackendError",
    "InvalidPositionError",
    "SpaceInvariantError",
    "SpacePosition",
    "GraphSpace",
    "GridSpace",
    "SpaceMapping",
    "SPACES_COMPONENT",
    "encode_spaces",
    "decode_spaces",
    "entity_domain_positions",
]


SPATIAL_BACKEND_KINDS: Final[frozenset[str]] = frozenset(
    {"graph", "grid", "hex", "continuous2d", "continuous3d", "custom"}
)
#: 6 种空间形态（Spec:1354-1361 词表小写 token 化；P4 实现 graph/grid，
#: 余为 reserved 扩展位 → make_backend 拒绝，P5+ 落地）


def _s_inv_2_message(exc: ValidationError) -> str | None:
    """从 pydantic 重抛的 ``ValidationError`` 中取出 S-INV-2 原文；其余校验错误返回 None。"""
    for error in exc.errors():
        if error.get("type") == "value_error" and "S-INV-2" in str(error.get("msg", "")):
            msg = str(error.get("msg", ""))
            return msg.removeprefix("Value error, ") or msg
    return None


class SpatialDomain(ContractModel):
    """named spatial domain（Spec:1365-1372：overworld/city/tavern/…）。

    **S-INV-1**：``domain_id`` 匹配 ``^[a-z][a-z0-9_]*$``（构造期拒绝）；
    **S-INV-2**：``backend_kind`` ∈ :data:`SPATIAL_BACKEND_KINDS`（构造期拒绝）。
    """

    domain_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    backend_kind: str
    parameters: dict[str, JsonValue] = {}

    @field_validator("backend_kind")
    @classmethod
    def _check_backend_kind(cls, value: str) -> str:
        """S-INV-2：backend_kind 词表外拒绝（D-P4-17 ValueError 族，全部构造路径）。"""
        if value not in SPATIAL_BACKEND_KINDS:
            raise SpaceInvariantError(
                f"S-INV-2 违反：backend_kind {value!r} 不在 SPATIAL_BACKEND_KINDS 词表"
            )
        return value

    def __init__(self, /, **data: Any) -> None:
        """直接构造：S-INV-2 抛具名 :class:`SpaceInvariantError`（不静默、不包裹）。

        校验器在 ``super().__init__`` 的校验内运行，其抛出的
        :class:`SpaceInvariantError`（ValueError 族）会被 pydantic 重抛为
        ``ValidationError``——本覆盖将其还原为具名类型（其余校验错误原样
        穿透，不转换）。
        """
        try:
            super().__init__(**data)
        except ValidationError as exc:
            message = _s_inv_2_message(exc)
            if message is not None:
                raise SpaceInvariantError(message) from exc
            raise


class SpaceBackend(Protocol):
    """空间后端协议（Spec:1348-1350 "空间 MUST 可替换" Spec:1345）。

    实现纪律（D-P4-11 / INV-P4-3）：不可变配置对象——全部几何数据构造期
    注入，运行期零状态变更；四方法全纯。
    """

    def validate_position(self, position: SpacePosition) -> None:
        """非法位置 → :class:`InvalidPositionError`（含 domain 无关诊断）。"""

    def neighbors(self, position: SpacePosition) -> tuple[SpacePosition, ...]:
        """邻接位置（**确定性序**：grid 上/右/下/左，D-P4-12；graph 排序节点序）。"""

    def distance(self, a: SpacePosition, b: SpacePosition) -> float:
        """距离（graph = BFS 跳数，grid = 曼哈顿；不可达 → INF_DISTANCE）。"""

    def positions(self) -> tuple[SpacePosition, ...]:
        """全位置枚举（确定性序：grid 行主序 y→x；graph 节点 casefold 排序）。"""


INF_DISTANCE: Final[float] = float("inf")
#: 不可达距离哨兵（D-P4-12：计算值、永不入 JSON——P1 §0.2 铁律 1 的落位：
#: 距离不是持久化字段；测试中禁止对其 dump_json）


class SpaceRegistry:
    """domain 名 → (SpatialDomain, SpaceBackend) 不可变注册表（INV-P4-3）。

    构造：``SpaceRegistry(entries: Mapping[str, tuple[SpatialDomain, SpaceBackend]])``。
    **S-INV-4**：键必须 == ``entry[0].domain_id``，否则 :class:`SpaceInvariantError`；
    **S-INV-5**：``entry[0].backend_kind`` 必须与 backend 实际种类一致
    （graph→GraphSpace / grid→GridSpace isinstance 核对），否则同错。
    零公共 mutator；``domain_ids()`` 返回排序元组。
    """

    def __init__(self, entries: Mapping[str, tuple[SpatialDomain, SpaceBackend]]) -> None:
        """构造期逐条核验 S-INV-4/S-INV-5，通过后保留不可变快照（INV-P4-3）。"""
        snapshot: dict[str, tuple[SpatialDomain, SpaceBackend]] = {}
        for key, (domain, backend) in entries.items():
            if key != domain.domain_id:
                raise SpaceInvariantError(
                    f"S-INV-4 违反：注册表键 {key!r} != domain_id {domain.domain_id!r}"
                )
            # S-INV-5：graph/grid 为 P4 已实现 kind（reserved 无参考类，不核对）；
            # GraphSpace/GridSpace 由 Wave B 追加于本文件末尾，调用期解析。
            if domain.backend_kind == "graph" and not isinstance(backend, GraphSpace):
                raise SpaceInvariantError(
                    f"S-INV-5 违反：domain {domain.domain_id!r} backend_kind 'graph' "
                    f"与 backend 实际种类 {type(backend).__name__!r} 不一致"
                )
            if domain.backend_kind == "grid" and not isinstance(backend, GridSpace):
                raise SpaceInvariantError(
                    f"S-INV-5 违反：domain {domain.domain_id!r} backend_kind 'grid' "
                    f"与 backend 实际种类 {type(backend).__name__!r} 不一致"
                )
            snapshot[key] = (domain, backend)
        self._entries = snapshot

    def domain(self, domain_id: str) -> SpatialDomain:
        """未注册 → :class:`UnknownDomainError`（查找点抛出，D-P3-16 双轨同纪律）。"""
        try:
            entry = self._entries[domain_id]
        except KeyError:
            raise UnknownDomainError(f"未注册空间域：{domain_id!r}") from None
        return entry[0]

    def backend(self, domain_id: str) -> SpaceBackend:
        """未注册 → :class:`UnknownDomainError`（查找点抛出，D-P3-16 双轨同纪律）。"""
        try:
            entry = self._entries[domain_id]
        except KeyError:
            raise UnknownDomainError(f"未注册空间域：{domain_id!r}") from None
        return entry[1]

    def domain_ids(self) -> tuple[str, ...]:
        """全部已注册 domain 名（排序元组）。"""
        return tuple(sorted(self._entries))


def make_backend(kind: str, parameters: dict[str, JsonValue]) -> SpaceBackend:
    """工厂（Spec:1345 可替换性的构造侧）：graph → GraphSpace（parameters:
    ``nodes``/``edges``）、grid → GridSpace（``width``/``height``）；
    其余 kind（hex/continuous2d/continuous3d/custom）→
    :class:`UnknownBackendError`（reserved 显式拒绝，不静默降级）。"""
    if kind == "graph":
        return GraphSpace(nodes=parameters["nodes"], edges=parameters["edges"])
    if kind == "grid":
        return GridSpace(width=parameters["width"], height=parameters["height"])
    raise UnknownBackendError(
        f"reserved 空间形态未实现：kind {kind!r}（P4 仅实现 graph/grid，余为 P5+ 扩展位）"
    )


class UnknownDomainError(LookupError): ...
class UnknownBackendError(LookupError): ...
class InvalidPositionError(ValueError): ...
class SpaceInvariantError(ValueError): ...


# —— §3.7 下半（P4-T06/T07；末尾追加，设计文档 §3.12 同文件单 Owner 串行交付）——


SpacePosition = JsonValue
#: 位置值类型（D-P4-10：格式由 backend 自校验，P4 无全局位置校验器）


class GraphSpace:
    """无向图空间参考实现（P4-T06）。

    构造：``GraphSpace(nodes: Sequence[str], edges: Sequence[tuple[str, str]])``。
    **G-INV**（构造期拒绝，:class:`SpaceInvariantError`）：节点 id 非空串；
    重复节点 id 拒绝（Leader 扩展裁定，确定性不静默，列入 deviations）；
    自环边（a==b）拒绝；重复边（无向，(a,b)≡(b,a)）拒绝；边端点未声明拒绝。
    距离 = BFS 跳数（float）；不可达 → :data:`INF_DISTANCE`。

    不可变纪律（D-P4-11 / INV-P4-3）：无公开 mutator，四方法全纯，
    运行期零状态变更。
    """

    def __init__(self, nodes: Sequence[str], edges: Sequence[tuple[str, str]]) -> None:
        """构造期 G-INV 逐条核验，通过后保留只读节点/邻接快照（INV-P4-3）。"""
        declared: set[str] = set()
        for node in nodes:
            if not isinstance(node, str) or node == "":
                raise SpaceInvariantError(
                    f"G-INV 违反：节点 id 必须为非空串：{node!r}"
                )
            if node in declared:
                raise SpaceInvariantError(
                    f"G-INV 违反：重复节点 id {node!r} 拒绝（确定性不静默，Leader 扩展裁定）"
                )
            declared.add(node)
        adjacency: dict[str, set[str]] = {node: set() for node in declared}
        seen_edges: set[frozenset[str]] = set()
        for index, edge in enumerate(edges):
            try:
                (source, target) = edge
            except (TypeError, ValueError):
                raise SpaceInvariantError(
                    f"G-INV 违反：edges[{index}] 必须为 (str, str) 二元组：{edge!r}"
                ) from None
            if not isinstance(source, str) or not isinstance(target, str):
                raise SpaceInvariantError(
                    f"G-INV 违反：边端点必须为 str：edges[{index}]={edge!r}"
                )
            if source == target:
                raise SpaceInvariantError(f"G-INV 违反：自环边 {source!r} 拒绝（a==b）")
            if source not in declared or target not in declared:
                raise SpaceInvariantError(
                    f"G-INV 违反：边端点未声明：edges[{index}]={edge!r}"
                )
            edge_key = frozenset((source, target))
            if edge_key in seen_edges:
                raise SpaceInvariantError(
                    f"G-INV 违反：重复无向边拒绝：edges[{index}]={edge!r}（(a,b)≡(b,a)）"
                )
            seen_edges.add(edge_key)
            adjacency[source].add(target)
            adjacency[target].add(source)
        self._nodes = frozenset(declared)
        self._adjacency = {node: frozenset(nbrs) for node, nbrs in adjacency.items()}

    def validate_position(self, position: SpacePosition) -> None:
        """非法位置 → :class:`InvalidPositionError`（D-P4-10：必须为已声明节点 id）。"""
        if not isinstance(position, str) or position not in self._nodes:
            raise InvalidPositionError(
                f"GraphSpace 非法位置：{position!r} 必须为 str 且是已声明节点 id"
            )

    def neighbors(self, position: SpacePosition) -> tuple[SpacePosition, ...]:
        """邻接节点 id（确定性序：casefold 排序节点序，D-P4-12）。"""
        self.validate_position(position)
        return tuple(sorted(self._adjacency[position], key=str.casefold))

    def distance(self, a: SpacePosition, b: SpacePosition) -> float:
        """BFS 跳数（float）；不可达 → :data:`INF_DISTANCE`（纯函数返回值，永不入 JSON）。"""
        self.validate_position(a)
        self.validate_position(b)
        if a == b:
            return 0.0
        frontier: deque[str] = deque([a])
        visited: set[str] = {a}
        hops = 0
        while frontier:
            hops += 1
            for _ in range(len(frontier)):
                current = frontier.popleft()
                for neighbor in self._adjacency[current]:
                    if neighbor == b:
                        return float(hops)
                    if neighbor not in visited:
                        visited.add(neighbor)
                        frontier.append(neighbor)
        return INF_DISTANCE

    def positions(self) -> tuple[SpacePosition, ...]:
        """全节点枚举（确定性序：casefold 排序）。"""
        return tuple(sorted(self._nodes, key=str.casefold))


class GridSpace:
    """二维网格参考实现（P4-T06）。

    构造：``GridSpace(width: int, height: int)``；w/h ≤ 0 →
    :class:`SpaceInvariantError`；非 int 的 w/h（含 bool）→
    :class:`SpaceInvariantError`（Leader 裁定，确定性不静默，列入 deviations）。
    位置 = 恰含 x/y 两键的 int 字典，x ∈ [0, width)、y ∈ [0, height)
    （5 类拒绝：缺键 / 多键 / 非 int 值 / 负值 / 越界 →
    :class:`InvalidPositionError`）；4 邻 = 上/右/下/左（D-P4-12 固定序，
    出界裁剪）；距离 = 曼哈顿；``positions()`` = 行主序（y 外层、x 内层）。

    不可变纪律（D-P4-11 / INV-P4-3）：无公开 mutator，四方法全纯，
    运行期零状态变更。
    """

    def __init__(self, width: int, height: int) -> None:
        """构造期守卫：width/height 必须为正 int（bool 拒绝），否则
        :class:`SpaceInvariantError`。"""
        for name, value in (("width", width), ("height", height)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise SpaceInvariantError(
                    f"GridSpace {name} 必须为 int（bool 拒绝）：{value!r}"
                )
            if value <= 0:
                raise SpaceInvariantError(f"GridSpace {name} 必须 > 0：{value!r}")
        self._width = width
        self._height = height

    def validate_position(self, position: SpacePosition) -> None:
        """5 类拒绝（缺键 / 多键 / 非 int 值 / 负值 / 越界）→
        :class:`InvalidPositionError`（D-P4-10 自校验）。"""
        if not isinstance(position, Mapping):
            raise InvalidPositionError(
                f"GridSpace 非法位置：{position!r} 必须为恰含 x/y 两键的字典"
            )
        if set(position) != {"x", "y"}:
            raise InvalidPositionError(
                f"GridSpace 非法位置：必须恰含 x/y 两键：{dict(position)!r}"
            )
        x, y = position["x"], position["y"]
        if (
            isinstance(x, bool)
            or not isinstance(x, int)
            or isinstance(y, bool)
            or not isinstance(y, int)
        ):
            raise InvalidPositionError(
                f"GridSpace 非法位置：x/y 必须均为 int（float/bool 拒绝）：{dict(position)!r}"
            )
        if x < 0 or y < 0:
            raise InvalidPositionError(
                f"GridSpace 非法位置：x/y 不得为负：{dict(position)!r}"
            )
        if x >= self._width or y >= self._height:
            raise InvalidPositionError(
                f"GridSpace 非法位置：越界 x∈[0,{self._width}) y∈[0,{self._height})：{dict(position)!r}"
            )

    def neighbors(self, position: SpacePosition) -> tuple[SpacePosition, ...]:
        """四邻（D-P4-12 固定序 上/右/下/左 = (x,y-1),(x+1,y),(x,y+1),(x-1,y)，出界裁剪）。"""
        self.validate_position(position)
        x, y = position["x"], position["y"]
        result: list[dict[str, int]] = []
        for nx, ny in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if 0 <= nx < self._width and 0 <= ny < self._height:
                result.append({"x": nx, "y": ny})
        return tuple(result)

    def distance(self, a: SpacePosition, b: SpacePosition) -> float:
        """曼哈顿 |dx|+|dy|（float；网格全可达，:data:`INF_DISTANCE` 永不出现）。"""
        self.validate_position(a)
        self.validate_position(b)
        return float(abs(a["x"] - b["x"]) + abs(a["y"] - b["y"]))

    def positions(self) -> tuple[SpacePosition, ...]:
        """全位置枚举（行主序：y 外层 0..height-1，x 内层 0..width-1）。"""
        return tuple(
            {"x": x, "y": y} for y in range(self._height) for x in range(self._width)
        )


class SpaceMapping(ContractModel):
    """单条 entity × domain 映射（Spec:1384-1392 "每个 mapping 必须明确
    所属 spatial domain" 的数据表达）。

    ``domain_id`` 无 pattern 约束（S-INV-1 只约束 :class:`SpatialDomain`）；
    ``position`` = 不透明 :data:`SpacePosition`（D-P4-10，backend 自校验）。
    """

    domain_id: str
    position: SpacePosition
    entered_tick: int = 0


#: 组件类型 ID（P1 无内置 spaces 类组件；槽位锚定 state.py:258
#  "persistent gameplay state → 组件 + world_variables"；空间映射 = spaces 组件、
#  域内唯一（D-P4-13）；P9 必须复用、不得重复注册；设计文档 §8.5 偏离 D6）
SPACES_COMPONENT = ComponentTypeId("spaces")


def encode_spaces(mappings: tuple[SpaceMapping, ...]) -> dict[str, JsonValue]:
    """→ ``{"mappings": [各 mapping 全字段 JSON, ...]}``（载荷序，
    ``model_dump(mode="json")``）。"""
    return {"mappings": [mapping.model_dump(mode="json") for mapping in mappings]}


def _s_inv_3_message(exc: ValidationError) -> str | None:
    """从 pydantic 重抛的 ``ValidationError`` 中取出 S-INV-3 原文；其余校验错误返回 None。"""
    for error in exc.errors():
        if error.get("type") == "value_error" and "S-INV-3" in str(error.get("msg", "")):
            msg = str(error.get("msg", ""))
            return msg.removeprefix("Value error, ") or msg
    return None


class _SpacesPayload(ContractModel):
    """解码信封（私有，不导出）：``spaces`` 组件载荷形状 ``{"mappings": [...]}``。

    信封级校验统一走 pydantic（缺 ``mappings`` 键 / 多余键 / 记录字段畸形 →
    ``ValidationError``，不吞、不降级）；**S-INV-3**（一实体同一域至多一个映射）
    由信封 model_validator 执行：同一 ``domain_id`` 出现两次 → 抛带 S-INV-3
    标记的 ValueError，:func:`decode_spaces` 捕获还原为具名
    :class:`SpaceInvariantError`（house 模式，与 :meth:`SpatialDomain.__init__`
    + :func:`_s_inv_2_message` 同纪律）。
    """

    mappings: tuple[SpaceMapping, ...]

    @model_validator(mode="after")
    def _check_domain_unique(self) -> _SpacesPayload:
        """S-INV-3 数据层执行：同一 ``domain_id`` 出现两次显式拒绝（构造失败）。"""
        seen: set[str] = set()
        for mapping in self.mappings:
            if mapping.domain_id in seen:
                raise ValueError(
                    f"S-INV-3 违反：mappings 中 domain {mapping.domain_id!r} 出现两次"
                    "（一 domain 一 position，D-P4-13）"
                )
            seen.add(mapping.domain_id)
        return self


def decode_spaces(payload: Mapping[str, JsonValue]) -> tuple[SpaceMapping, ...]:
    """载荷 → 映射序列（载荷序）；**S-INV-3**：同一 domain 出现两次 →
    :class:`SpaceInvariantError`（具名）；字段畸形 → pydantic ``ValidationError``
    （不吞、原样透传）。"""
    try:
        return _SpacesPayload.model_validate(payload).mappings
    except ValidationError as exc:
        message = _s_inv_3_message(exc)
        if message is not None:
            raise SpaceInvariantError(message) from exc
        raise


def entity_domain_positions(view: EntityView) -> dict[str, SpacePosition]:
    """EntityView 的 spaces 组件 → ``{domain_id: position}``（载荷序）；
    组件缺失 → ``{}``。"""
    payload = view.get_component(SPACES_COMPONENT)
    if payload is None:
        return {}
    return {mapping.domain_id: mapping.position for mapping in decode_spaces(payload)}
