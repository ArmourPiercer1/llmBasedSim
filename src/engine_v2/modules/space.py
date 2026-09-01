"""P9 W6 官方模块：space（T13；SOT §3.11 L767–789；导出 4 名）。

来源 = Spec §40 space 模块 + G9「Grid/**Hex-like** Space」条款：kernel
``GridSpace``（core space.py:350，方格 4 邻 + 曼哈顿，冻结）不含 hex →
本模块纯函数生成 hex 邻接，映射入冻结 ``GraphSpace``（core
space.py:256）。v1 无对应物（v2 新模块）。

冻结消费（SOT §2.1/§2.4）：core ``space``（``SpaceBackend``:150 /
``SpaceRegistry``:175 / ``SpatialDomain``:112 / ``GraphSpace``:256 /
``GridSpace``:350）；模块公共面 ``modules.base``。

必备解释 (b)（DEV-W6-2，预裁决——odd-r 邻表与立方坐标公式）：SOT 仅钉
「6 邻（offset 修正；出界裁剪）」，未钉邻表。采用标准 odd-r offset
惯例（奇数行右移半格；Red Blob 惯例）：

- 偶数行 ``r % 2 == 0``：邻 = ``(c+1,r) (c-1,r) (c,r-1) (c-1,r-1)
  (c,r+1) (c-1,r+1)``；
- 奇数行 ``r % 2 == 1``：邻 = ``(c+1,r) (c-1,r) (c,r-1) (c+1,r-1)
  (c,r+1) (c+1,r+1)``；
- ``even-r`` = 镜像惯例（偶数行右移半格）：偶数行邻表 = odd-r 奇数行
  公式，奇数行邻表 = odd-r 偶数行公式；
- 立方坐标（odd-r）：``x = c - (r - (r & 1)) // 2``、``z = r``、
  ``y = -x - z``；（even-r）：``x = c - (r + (r & 1)) // 2``、``z = r``、
  ``y = -x - z``；``distance_between = max(|dx|, |dy|, |dz|)``。
- 自证（开发期 python 证据，DEV-W6-2 验证面）：3×3 odd-r 网格无向边
  = 16 / 有向 = 32；对角 hex 步数 = 2（``hex_0_0``→``hex_1_2`` 与
  ``hex_0_1``→``hex_2_0`` 均 = 2）；全节点对 BFS 跳数与立方距离逐一
  相等（几何一致性）。
- 备选（否）：无可枚举备选（SOT 仅钉「6 邻（offset 修正；出界裁剪）」
  未钉邻表；实现设计面，A12 钉值 + 全节点对 BFS==cube 交叉核验约束）。

DEV-W6-8 披露（``register_standard_space`` 签名面）：SOT §3.11 表行 4
签名 = ``(registry: SpaceRegistry, domain: str, backend: SpaceBackend)
-> None``；但 core ``SpaceRegistry``（space.py:175）为不可变注册表
（零公共 mutator，唯一构造入口 = 条目映射 space.py:185）→ 按字面签名
不可实现。最小改动：参数 = 宿主条目映射
``dict[str, tuple[SpatialDomain, SpaceBackend]]``（宿主累积后经
``SpaceRegistry(entries)`` 构造），函数职责 = 文法/种类核验 + 幂等写入。
  备选（否）：SOT 字面签名（否因：SpaceRegistry 零公共 mutator，
  不可实现）；私有 ``_entries`` 突变（否因：绕冻结面契约，违 D5）；
  注册函数返回新 registry（否因：双写 / 别名风险）。

纪律（K2/D6/K8）：全纯函数 / 零直写（条目映射写入 = 宿主构造期装配
面，同 W4 ``register_standard_actions`` 先例）；零 wall-clock / 全局
RNG；零推理消费；12 名闭集零命中。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from src.engine_v2.core.space import (
    GraphSpace,
    GridSpace,
    SpaceBackend,
    SpatialDomain,
)
from src.engine_v2.modules.base import OFFICIAL_MODULE_VERSION, ModuleIdentity

__all__ = [
    "HexGrid",
    "hex_adjacency",
    "distance_between",
    "register_standard_space",
]

#: 模块身份（SOT §3.1.2 requires 表 L489：space 自足（kernel
#: SpaceRegistry 为 kernel 根）→ requires = ()）。
IDENTITY: Final[ModuleIdentity] = ModuleIdentity(
    "llmsim-standard-space", OFFICIAL_MODULE_VERSION, (),
)

#: offset 闭集（SOT §3.11 表行 1；文法违例 → ValueError）。
_OFFSET_CLOSED_SET: Final[frozenset[str]] = frozenset({"odd-r", "even-r"})

#: 节点 id 文法 ``hex_<c>_<r>``（c/r = 0 基十进制非负整数）。
_NODE_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"hex_(\d+)_(\d+)")

#: 空间域 id 文法（core S-INV-1 同款，space.py:119）。
_DOMAIN_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z0-9_]*")


@dataclass(frozen=True)
class HexGrid:
    """hex 网格参数（SOT §3.11 表行 1）。

    ``offset`` 闭集 = ``odd-r`` / ``even-r``（Red Blob offset 惯例；邻表
    与立方坐标公式 = 模块 docstring 必备解释 (b)）。构造期校验
    （AD-P9-4 辅助面，确定性拒绝）：

    - ``cols <= 0`` / ``rows <= 0`` → ``ValueError``；
    - ``offset`` 不在闭集 → ``ValueError``。
    """

    cols: int
    rows: int
    offset: str = "odd-r"

    def __post_init__(self) -> None:
        if self.cols <= 0:
            raise ValueError(f"HexGrid.cols 必须 > 0：{self.cols!r}")
        if self.rows <= 0:
            raise ValueError(f"HexGrid.rows 必须 > 0：{self.rows!r}")
        if self.offset not in _OFFSET_CLOSED_SET:
            raise ValueError(
                f"HexGrid.offset 必须在闭集 {sorted(_OFFSET_CLOSED_SET)} "
                f"内：{self.offset!r}"
            )


def _node_id(col: int, row: int) -> str:
    """节点 id = ``hex_<c>_<r>``（SOT §3.11 表行 2；c/r 0 基）。"""
    return f"hex_{col}_{row}"


def _neighbor_cells(
    grid: HexGrid, col: int, row: int,
) -> tuple[tuple[int, int], ...]:
    """6 邻（offset 修正；出界裁剪）——必备解释 (b) 邻表；确定性行内序。"""
    if grid.offset == "odd-r":
        if row % 2 == 0:
            deltas = ((1, 0), (-1, 0), (0, -1), (-1, -1), (0, 1), (-1, 1))
        else:
            deltas = ((1, 0), (-1, 0), (0, -1), (1, -1), (0, 1), (1, 1))
    else:  # even-r（镜像惯例）
        if row % 2 == 0:
            deltas = ((1, 0), (-1, 0), (0, -1), (1, -1), (0, 1), (1, 1))
        else:
            deltas = ((1, 0), (-1, 0), (0, -1), (-1, -1), (0, 1), (-1, 1))
    cells: list[tuple[int, int]] = []
    for dc, dr in deltas:
        nc, nr = col + dc, row + dr
        if 0 <= nc < grid.cols and 0 <= nr < grid.rows:
            cells.append((nc, nr))
    return tuple(cells)


def hex_adjacency(grid: HexGrid) -> tuple[tuple[str, str], ...]:
    """纯函数：hex 6 邻 → 对称边表（SOT §3.11 表行 2；A12 主面）。

    - 节点 id = ``hex_<c>_<r>``（c/r 0 基）；
    - 每条无向边产出双向两条：逐格枚举 6 邻（出界裁剪），以
      ``a < b`` 字典序去重后同写 (a, b) 与 (b, a)；
    - 返回值 = sorted 有向边表（确定性；3×3 odd-r = 32 条，
      对偶无向边集 = 16 条）；
    - 消费侧 = ``GraphSpace(nodes, edges)``（core space.py:256）——
      G-INV 拒绝重复无向边，宿主须先按无向集去重（conftest 世界
      构建面，同 W4 注册面惯例）。
    """
    directed: set[tuple[str, str]] = set()
    for row in range(grid.rows):
        for col in range(grid.cols):
            source = _node_id(col, row)
            for ncol, nrow in _neighbor_cells(grid, col, row):
                target = _node_id(ncol, nrow)
                if source < target:
                    directed.add((source, target))
                    directed.add((target, source))
    return tuple(sorted(directed))


def _parse_node(grid: HexGrid, node: str) -> tuple[int, int]:
    """节点 id → (col, row)；非网格节点（文法不符 / 出界）→ KeyError。"""
    match = _NODE_ID_PATTERN.fullmatch(node)
    if match is None:
        raise KeyError(f"非网格节点（id 不匹配 hex_<int>_<int>）：{node!r}")
    col, row = int(match.group(1)), int(match.group(2))
    if not (0 <= col < grid.cols and 0 <= row < grid.rows):
        raise KeyError(
            f"节点出界：{node!r}（网格 {grid.cols}x{grid.rows}）"
        )
    return col, row


def _to_cube(grid: HexGrid, node: str) -> tuple[int, int, int]:
    """(col, row) → 立方坐标 (x, y, z)（必备解释 (b) 公式）。"""
    col, row = _parse_node(grid, node)
    if grid.offset == "odd-r":
        x = col - (row - (row & 1)) // 2
    else:
        x = col - (row + (row & 1)) // 2
    z = row
    return (x, -x - z, z)


def distance_between(grid: HexGrid, a: str, b: str) -> int:
    """纯函数：hex 立方坐标步数（SOT §3.11 表行 3）。

    非网格节点（id 不匹配 ``hex_<int>_<int>`` 或出界）→ ``KeyError``
    （查找点抛出，D-P3-16 双轨同纪律）。公式 = 模块 docstring 必备
    解释 (b)：``max(|dx|, |dy|, |dz|)``。
    """
    (ax, ay, az) = _to_cube(grid, a)
    (bx, by, bz) = _to_cube(grid, b)
    return max(abs(ax - bx), abs(ay - by), abs(az - bz))


def register_standard_space(
    entries: dict[str, tuple[SpatialDomain, SpaceBackend]],
    domain: str,
    backend: SpaceBackend,
) -> None:
    """宿主注册入口（SOT §3.11 表行 4；DEV-W6-8 签名面，模块 docstring
    披露）：把 ``GraphSpace``（hex 邻接构造）或 ``GridSpace``（方格
    对照）注册入宿主条目映射（幂等），宿主随后经
    ``SpaceRegistry(entries)``（core space.py:185 构造面）装配。

    核验序（确定性，失败零写入）：

    1. ``domain`` 不匹配 ``^[a-z][a-z0-9_]*$``（S-INV-1 同款文法）→
       ``ValueError``；
    2. ``backend`` 非 ``GraphSpace`` / ``GridSpace`` → ``ValueError``
       （S-INV-5 种类一致语义：graph→GraphSpace / grid→GridSpace）；
    3. 写入 ``entries[domain] = (SpatialDomain, backend)``：同域重注册
       = 幂等覆盖（同 backend 再注册零状态变化）。
    """
    if _DOMAIN_ID_PATTERN.fullmatch(domain) is None:
        raise ValueError(
            f"空间域 id 文法违例（^[a-z][a-z0-9_]*$）：{domain!r}"
        )
    if isinstance(backend, GraphSpace):
        backend_kind = "graph"
    elif isinstance(backend, GridSpace):
        backend_kind = "grid"
    else:
        raise ValueError(
            f"register_standard_space 仅接受 GraphSpace / GridSpace："
            f"{type(backend).__name__!r}"
        )
    entries[domain] = (
        SpatialDomain(domain_id=domain, backend_kind=backend_kind),
        backend,
    )
