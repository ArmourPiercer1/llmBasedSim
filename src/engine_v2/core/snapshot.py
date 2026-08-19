"""engine_v2 core 层快照信封、版本标记与 immutable read view（P1-T05）。

依据 ``docs/v2/contracts/P1-core-data-contracts.md``（下称"设计文档"）
§6.2 / §6.3 与 §1.1 文件清单（snapshot.py：快照信封、版本标记、immutable
read view，归属 P1-T05）：

- :data:`SNAPSHOT_FORMAT_VERSION` —— 信封格式版本（§6.3）；
- :data:`CONTRACT_SCHEMA_VERSION` —— **不自定义、从 ``state.py`` import
  复用并 re-export**（T02 已确立：常量定义于 state.py，其
  ``WorldState.schema_version`` / ``RuntimeState.schema_version`` 缺省值
  引用之；本模块严禁双源复写，两值恒为同一对象）；
- :class:`Snapshot` —— 快照信封（§6.3 字段逐项）；
- :func:`snapshot` / :func:`restore_snapshot` —— 纯函数构造/还原（§6.3：
  不含 IO，持久化介质属 P8 PersistenceBackend）；
- :func:`check_snapshot_versions` —— 三层版本标记一致性校验（§6.3 版本
  标记策略；T06 口径 J6"P1 至少给出校验函数"，迁移行为属 P8）；
- :func:`freeze_view` —— 深冻结只读视图（§6.2 决策 D-15：A 为基础 +
  B 为视图层；实现单一来源为 ``entity.py`` 的 ``_freeze_value``，本模块
  按 §1.1 归属表将其作为公开入口 re-expose，不复制第二份实现）。

§4.3 snapshot/trace 归属总表的程序化落位（守卫见 T05 测试）：Snapshot
收 **WorldState / RuntimeState 全字段**（含 ``backend_refs``——BackendState
只以"引用 + 三项能力声明"进快照，真实 checkpoint 外置，决策 D-10），
**不收 trace**（trace 记录"变化"，不复制状态本体；TraceRecord 独立成流，
§4.4）。

决策落位：

- **D-9**：``world_instance_id`` 在**信封层**（:class:`Snapshot` 字段），
  不在 ``WorldState`` 内——状态实例无关，snapshot 可载入新实例/分支实例
  而无需改写（§4.1）；
- **D-15 第 4 条**：快照固化走 :func:`~src.engine_v2.core.serialization.
  deep_copy_via_roundtrip`——:func:`snapshot` 产物内的 world_state /
  runtime_state 与运行时活数据**零别名**；:func:`restore_snapshot` 产物
  与快照本体亦零别名（T06 口径 J4 双向隔离）。

本模块只 import 标准库、pydantic 与同包 ``src.engine_v2``（§0.3 import
边界白名单），不触碰 v1。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final

from pydantic import Field

from src.engine_v2.core.entity import ContractModel, _freeze_value
from src.engine_v2.core.serialization import deep_copy_via_roundtrip
from src.engine_v2.core.state import (
    CONTRACT_SCHEMA_VERSION,
    RuntimeState,
    WorldState,
)

__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "SNAPSHOT_FORMAT_VERSION",
    "Snapshot",
    "snapshot",
    "restore_snapshot",
    "check_snapshot_versions",
    "freeze_view",
]

#: 信封格式版本（设计文档 §6.3）：Snapshot 信封自身的格式代次。
#: 任何信封结构变更必须 +1 并过 Gate（与 :data:`CONTRACT_SCHEMA_VERSION`
#: 分属不同迁移维度，见模块 docstring 与 §6.3 版本标记策略）。
SNAPSHOT_FORMAT_VERSION: Final[int] = 1


class Snapshot(ContractModel):
    """快照信封（设计文档 §6.3；Spec §30.2 snapshot 内容逐项落位）。

    字段逐项（顺序与 §6.3 一致，public contract 冻结）：

    - ``snapshot_format_version``：信封格式版本（:data:`SNAPSHOT_FORMAT_VERSION`）；
    - ``contract_schema_version``：全局契约代（:data:`CONTRACT_SCHEMA_VERSION`，
      从 ``state.py`` 复用）；
    - ``world_instance_id``：**D-9**——instance 身份在信封层，不在
      ``WorldState`` 内；
    - ``world_state`` / ``runtime_state``：**§4.3 归属总表**——WorldState /
      RuntimeState **全部字段**进快照（含 ``backend_refs`` 的引用与能力
      声明，决策 D-10）；**不收 trace**（TraceRecord 独立成流，§4.4）；
    - ``created_logical_tick``：快照固化时的逻辑刻（权威序用整型，§0.2
      铁律 3）；
    - ``created_wall_time``：墙钟仅诊断用（ISO-8601，§0.2 铁律 3）；
    - ``project_version`` / ``module_versions``：Spec §30.2 Project /
      Module versions（P5 起填充真实值；P1 只落信封字段）。

    本模型是 frozen ContractModel：字段级不可再赋值（§0.1）；嵌套可变
    容器的咨询性深度只读由 :func:`freeze_view`（D-15 视图层）承担，快照
    固化零别名由 :func:`snapshot` / :func:`restore_snapshot` 走
    :func:`deep_copy_via_roundtrip` 保证（D-15 第 4 条）。
    """

    snapshot_format_version: int = SNAPSHOT_FORMAT_VERSION
    contract_schema_version: int = CONTRACT_SCHEMA_VERSION
    #: D-9：instance 身份在信封层，不在 WorldState 内
    world_instance_id: str
    world_state: WorldState
    runtime_state: RuntimeState
    created_logical_tick: int
    created_wall_time: datetime | None = None
    project_version: str | None = None
    module_versions: dict[str, str] = Field(default_factory=dict)


def snapshot(
    world_state: WorldState,
    runtime_state: RuntimeState,
    world_instance_id: str,
    *,
    created_logical_tick: int | None = None,
    created_wall_time: datetime | None = None,
    project_version: str | None = None,
    module_versions: Mapping[str, str] | None = None,
) -> Snapshot:
    """纯函数：``(WorldState, RuntimeState, 信封参数) -> Snapshot``（设计文档 §6.3）。

    语义：

    - **零别名固化**（D-15 第 4 条）：入参的两个状态先经
      :func:`deep_copy_via_roundtrip` 固化再入信封——Snapshot 内数据与
      运行时活数据不共享任何可变容器（T06 口径 J4：修改恢复/快照产物
      不影响活状态，反之亦然）；直接以模型实例入 :class:`Snapshot` 构造
      会因 Pydantic 对嵌套实例默认不重校验而引入别名，故此处必须显式
      round-trip；
    - **D-9**：``world_instance_id`` 由调用方显式给出并落信封层（状态本体
      不含 instance 身份，可载入新实例/分支实例）；
    - ``created_logical_tick`` 缺省取 ``runtime_state.logical_tick``（快照
      固化时刻的逻辑时钟读数，决策 D-6：单一单调计数）；
    - **纯函数、不含 IO**（§6.3）：持久化介质属 P8 PersistenceBackend
      （Spec §30.3）；JSON 出入口走 ``serialization.py``（§6.1）。
    """
    return Snapshot(
        world_instance_id=world_instance_id,
        world_state=deep_copy_via_roundtrip(world_state),
        runtime_state=deep_copy_via_roundtrip(runtime_state),
        created_logical_tick=(
            runtime_state.logical_tick if created_logical_tick is None else created_logical_tick
        ),
        created_wall_time=created_wall_time,
        project_version=project_version,
        module_versions=dict(module_versions) if module_versions is not None else {},
    )


def restore_snapshot(snap: Snapshot) -> tuple[WorldState, RuntimeState]:
    """纯函数：``Snapshot -> (WorldState, RuntimeState)``（设计文档 §6.3）。

    - **零别名还原**（D-15 第 4 条）：产物经 :func:`deep_copy_via_roundtrip`
      重建——与快照本体不共享任何可变容器（T06 口径 J4：修改恢复产物不
      影响快照，反之亦然）；类型重建保持 typed ID / Revision / 枚举（§2.1）；
    - **纯函数、不含 IO**：从何处读取快照文本（文件/对象存储）属 P8
      PersistenceBackend；版本不匹配的**迁移/回退行为**属 P8
      （Spec §44 ``content/migrations.py``），P1 只以
      :func:`check_snapshot_versions` 报告不匹配（T06 口径 J6），本函数
      本身不做版本门禁、不抛版本相关异常；
    - 信封的元数据字段（instance id / 版本 / project / module versions）
      不进入返回的状态——它们是信封层事实（D-9），由 P8 迁移器与运行时
      容器消费。
    """
    return (
        deep_copy_via_roundtrip(snap.world_state),
        deep_copy_via_roundtrip(snap.runtime_state),
    )


def check_snapshot_versions(snap: Snapshot) -> tuple[str, ...]:
    """三层版本标记一致性校验（设计文档 §6.3 版本标记策略；T06 口径 J6）。

    检查四枚版本字段（三层：信封 / 状态模型 / 全局契约代）：

    1. ``snap.snapshot_format_version`` == :data:`SNAPSHOT_FORMAT_VERSION`
       （信封层：信封格式代次）；
    2. ``snap.world_state.schema_version`` == :data:`CONTRACT_SCHEMA_VERSION`
       （状态模型层：WorldState 内嵌版本）；
    3. ``snap.runtime_state.schema_version`` == :data:`CONTRACT_SCHEMA_VERSION`
       （状态模型层：RuntimeState 内嵌版本）；
    4. ``snap.contract_schema_version`` == :data:`CONTRACT_SCHEMA_VERSION`
       （全局契约代：信封层，与 2/3 交叉验证）。

    返回不匹配问题列表（结构化字符串，每条注明字段名、快照值与当前期望
    值）；**空元组 = 全部匹配**。纯函数，无副作用；P1 只报告不处置——
    迁移/回退行为属 P8（Spec §44 ``content/migrations.py`` 依三层标记分别
    处理"信封变化 / 状态模型变化 / 契约语义变化"）。
    """
    issues: list[str] = []
    if snap.snapshot_format_version != SNAPSHOT_FORMAT_VERSION:
        issues.append(
            "信封版本不匹配：snapshot.snapshot_format_version="
            f"{snap.snapshot_format_version} != 当前 {SNAPSHOT_FORMAT_VERSION}"
        )
    if snap.world_state.schema_version != CONTRACT_SCHEMA_VERSION:
        issues.append(
            "状态模型版本不匹配：snapshot.world_state.schema_version="
            f"{snap.world_state.schema_version} != 当前契约 {CONTRACT_SCHEMA_VERSION}"
        )
    if snap.runtime_state.schema_version != CONTRACT_SCHEMA_VERSION:
        issues.append(
            "状态模型版本不匹配：snapshot.runtime_state.schema_version="
            f"{snap.runtime_state.schema_version} != 当前契约 {CONTRACT_SCHEMA_VERSION}"
        )
    if snap.contract_schema_version != CONTRACT_SCHEMA_VERSION:
        issues.append(
            "全局契约代不匹配：snapshot.contract_schema_version="
            f"{snap.contract_schema_version} != 当前 {CONTRACT_SCHEMA_VERSION}"
        )
    return tuple(issues)


def freeze_view(value: Any) -> Any:
    """深冻结只读视图（设计文档 §6.2 决策 D-15：A 为基础 + B 为视图层）。

    把嵌套 ``dict``/``list`` 递归转为 :class:`~types.MappingProxyType` /
    ``tuple``：标量与 ``None`` 原样返回。用于**交给消费者**（P3/P4 的
    policy、P10 的 view 派生）的只读视图——视图层（方案 B）在 frozen
    ContractModel（方案 A）之上提供真正的深度只读。

    实现单一来源为 ``entity.py`` 的 ``_freeze_value``（T03 已落盘，§3.2
    ``EntityView`` 的组件视图即用它构造）：本函数按 §1.1 归属表将
    ``freeze_view()`` 作为**公开入口** re-expose，不复制第二份实现。

    不变量是**咨询性**（advisory）的（D-15 第 3 条）：恶意代码可绕过
    （Python 语言限度），强制性由 P2 写屏障 + reducer-only 公共 API 承担
    （§3.5）。对产物的写操作（``view["k"] = v`` / ``tup[0] = v`` 等）
    抛 ``TypeError``（T06 口径 J5：赋值抛错、嵌套层同样抛错）。
    """
    return _freeze_value(value)
