"""engine_v2 core 层 Space 空间语义：空间形态词表、空间域、后端协议、注册表与
后端工厂（P4-T05，§3.7 上半）。

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

**T05/T06/T07 分工**（设计文档 §3.12 同文件单 Owner 串行交付）：下半 8 导出
（``SpacePosition`` / ``GraphSpace`` / ``GridSpace`` / ``SpaceMapping`` /
``SPACES_COMPONENT`` / ``encode_spaces`` / ``decode_spaces`` /
``entity_domain_positions``）由 P4-T06/T07（Wave B）于本文件**末尾追加**；
:class:`SpaceBackend` 协议签名引用 ``SpacePosition``（``from __future__ import
annotations`` 下标注为字符串，导入期不解析），:func:`make_backend` 的
graph/grid 分派体与 :class:`SpaceRegistry` 的 S-INV-5 isinstance 核对引用
``GraphSpace`` / ``GridSpace``——均为**调用期**名称解析、导入期不执行，本文件
导入性不受影响；顶部 ``if TYPE_CHECKING`` 自导入块（运行时零 import，口径同
``scheduler.py`` / ``components.py`` 前向引用）令 Wave A 窗口内静态检查可解析，
Wave B 追加后由模块内定义天然收编、无需改动。:data:`__all__` 由 T06/T07
补全至 18 项（本任务仅落本范围 10 符号）。

Import 边界（设计文档 §3.3 依赖图 / §3.4 黑名单 / §5.5 M1）：本模块只 import
标准库、pydantic 与同包 ``src.engine_v2``（entity → ContractModel）；asyncio /
random / datetime / time / uuid / json 直接 import / os / subprocess / 网络栈
全部缺席；无云模型 / 网络 / 随机性；M1④ 封闭 12 标识符集 0 命中。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final, Protocol

from pydantic import Field, JsonValue, ValidationError, field_validator

from src.engine_v2.core.entity import ContractModel

if TYPE_CHECKING:  # Wave B（T06/T07）同文件末尾追加段的调用期/类型期前向引用：
    # 协议签名（SpacePosition）与分派/isinstance 核对（GraphSpace/GridSpace）；
    # 运行时零 import，Wave B 追加后由模块内定义收编（§3.12 同文件单 Owner）。
    from src.engine_v2.core.space import GraphSpace, GridSpace, SpacePosition

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
