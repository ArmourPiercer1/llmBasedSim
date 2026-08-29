"""engine_v2 core 层 GameplayMode 游戏模式：模式操作词表、模式叠加层、不可变注册表、
per-property 合并语义与动作可用性判定（P4-T08 上半，§3.10；下半 T09 同文件末尾串行追加）。

依据 ``docs/v2/contracts/P4-actor-context-space-mode-design.md``（下称"设计文档"）：

- **§3.10 上半（P4-T08 范围）**：本模块 7 个导出符号（按 §3.10 代码块条目序）——
  :class:`ModeOperationKind` / :class:`ModeOperation` / :class:`ModeOverlay` /
  :class:`ModeOverlayRegistry` / :class:`MergedModeConfiguration` /
  :func:`merge_modes` / :func:`is_action_available`；:class:`ModeInvariantError`
  由上半先行定义（账本行归 T09，同文件单 Owner 串行，下半复用不重定义）；
- **Spec:1398-1409（"Mode 是 overlay，不是另一个 world"）**：:class:`ModeOverlay`
  （priority / action_filter_kind / action_ids / systems / time_policy /
  checkpoint_interval / input_policy / context）；
- **Spec:1424-1431（合并表）/ D-P4-14（模式合并规则，每字段单一胜者）**：
  :func:`merge_modes` 纯函数——胜者 = priority 最大，平手 → casefold 较小
  ``mode_id``；``time_policy`` / ``checkpoint_interval`` / ``input_policy`` /
  ``action_filter`` 单一胜者，``winner_by_field`` 逐字段记录（Spec:1433 冲突策略
  MUST 可检查）；``activated_systems`` 并集（Spec:1426）；``context`` 浅合并，
  高 priority 逐键胜；P4 取 allow 交集 = 保守侧（D-P4-14b）；
- **Spec:1424-1425 / D-P4-14（available_actions 判定序）**：:func:`is_action_available`
  —— deny 大于 allow 交集 大于 无约束：任一激活模式 deny 集含该 action ⇒
  不可用；否则必须属于每个持 allow 集的激活模式的 allow 集 ⇒ 可用；
- **M-INV-1（§3.10 逐字）**：``mode_id`` 匹配 ``^[a-z][a-z0-9_]*$``；
  ``action_filter_kind == "none"`` ⇒ ``action_ids == ()``；allow/deny ⇒
  ``action_ids`` 非空（构造期拒绝）——跨字段部分构造期落位（house 模式精确参照
  ``space.py`` :class:`SpatialDomain` 与 ``capability.py`` :class:`CapabilityTable`
  已提交实现）：直接构造路径抛具名 :class:`ModeInvariantError`（
  :meth:`ModeOverlay.__init__` 覆盖），pydantic 校验路径（``model_validate`` /
  ``model_validate_json``）由 pydantic 重抛为 ``ValidationError``（ValueError
  子类，同族口径，D-P4-17），M-INV-1 文案保留；
- **INV-P4-3**：:class:`ModeOverlayRegistry` 为构造期注入的不可变注册表
  （零公开 mutator；键必须 == ``overlay.mode_id``，违例 →
  :class:`ModeInvariantError`）；
- **D-P4-17（错误分类两族）**：:class:`ModeInvariantError` 归 ValueError 族
  （M-INV-1 跨字段 / 注册表键违反 = 输入/配置违反不变式）；LookupError 族
  ``UnknownModeError`` 属下半 T09。

**T08/T09 分工**（设计文档 §3.12 同文件单 Owner 串行交付）：下半 6 导出
（``ModeChangeRequest`` / ``ModeChangeResolution`` / ``ModePolicy`` /
``DefaultModePolicy`` / ``apply_mode_change`` / ``UnknownModeError``）将由
P4-T09（Wave C）于本文件**末尾追加**；``__all__`` 现为上半 8 项（任务书给定
名称顺序），T09 追加 6 项补全至 14（名称集与设计文档 §8.3 账本 gameplay_mode
行完全一致；模块内顺序允许与代码块顺序不同，口径同 space.py）。本文件上半不
import state / clock / effects / provenance（§3.3 依赖图该行余下 import 名归
下半 T09 地盘），与 capability / knowledge / space / context_provider /
behavior_policy 零 import 边（§3.3 零边条款）。

Import 边界（设计文档 §3.3 依赖图 / §3.4 黑名单 / §5.5 M1）：本模块只 import
标准库、pydantic 与同包 ``src.engine_v2``（entity → ContractModel；scheduler →
**仅 TimePolicy 类型**——类型级依赖，运行时零调用，M1③：本文件对 scheduler 的
import 名集 ⊆ {TimePolicy}）；asyncio / random / datetime / time / uuid /
json 直接 import / os / subprocess / 网络栈全部缺席；无云模型 / 网络 / 随机性；
M1④ 封闭 12 标识符集 0 命中。
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any, Literal

from pydantic import Field, JsonValue, ValidationError, model_validator

from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.scheduler import TimePolicy

__all__ = [
    "ModeOperationKind",
    "ModeOperation",
    "ModeOverlay",
    "ModeOverlayRegistry",
    "MergedModeConfiguration",
    "merge_modes",
    "is_action_available",
    "ModeInvariantError",
]


class ModeOperationKind(str, Enum):
    """模式操作种类词表（str-Enum 保证 JSON/比较透明；值逐字 §3.10 代码块）。"""

    ACTIVATE = "activate"
    DEACTIVATE = "deactivate"


class ModeOperation(ContractModel):
    """单条模式操作（Spec:1448-1449 统一输出的元素；
    ``ModeChangeRequest.operations`` 的元素类型，下半 T09）。

    ``mode_id`` 本处**无** pattern 校验——注册表成员资格在解析期校验（下半
    M-INV-2 / D-P4-15 原子预校验；``mode_id`` 词表由 :class:`ModeOverlay`
    构造期 pattern 约束）。
    """

    operation_kind: ModeOperationKind
    mode_id: str


def _check_m_inv_1(overlay: ModeOverlay) -> None:
    """M-INV-1 跨字段：``action_filter_kind`` 与 ``action_ids`` 一致性（构造期拒绝）。

    - ``"none"`` ⇒ ``action_ids == ()``；
    - ``"allow"`` / ``"deny"`` ⇒ ``action_ids`` 非空。
    """
    kind = overlay.action_filter_kind
    if kind == "none":
        if overlay.action_ids:
            raise ModeInvariantError(
                "M-INV-1 违反：action_filter_kind 'none' 要求 action_ids 为空，"
                f"实际 {overlay.action_ids!r}"
            )
    elif not overlay.action_ids:
        raise ModeInvariantError(
            f"M-INV-1 违反：action_filter_kind {kind!r} 要求 action_ids 非空"
        )


def _m_inv_1_message(exc: ValidationError) -> str | None:
    """从 pydantic 重抛的 ``ValidationError`` 中取出 M-INV-1 原文；其余校验错误返回 None。"""
    for error in exc.errors():
        if error.get("type") == "value_error" and "M-INV-1" in str(error.get("msg", "")):
            msg = str(error.get("msg", ""))
            return msg.removeprefix("Value error, ") or msg
    return None


class ModeOverlay(ContractModel):
    """模式叠加层（Spec:1398-1409 "Mode 是 overlay，不是另一个 world"）。

    - ``priority``：≥ 0（Spec:1428/1429 winner 语义的排序键；D-P4-14）；
    - ``action_filter_kind``：none | allow | deny（Spec:1424-1425 "available_actions
      → union/intersection" 的可检查落位；P4 取交集 = 保守侧，D-P4-14b）；
    - ``systems``：系统激活名（Spec:1426 "system_activation → union"）；
    - ``time_policy``：**整对象** TimePolicy（scheduler.py:251-271）——winner 全量
      替换，不做字段级 merge（Spec:1428 "time_policy → priority winner"）；
    - ``checkpoint_interval``：模式建议 checkpoint 粒度（winner 取值；P4 簿记面，
      执行语义 = P5/scheduler 扩展位）；与 ``TimePolicy.checkpoint_interval_ticks``
      （scheduler.py:1584 读 time_policy 侧）数值分歧时，执行语义 = P5 义务
      （P4 纯簿记）；
    - ``input_policy``：不透明 JsonValue（M-INV-6；P4 直通不解释，P8 表现层消费）；
    - ``context``：per-mode 上下文 → ``mode_context[mode_id]``（Spec:1413 侧）。
    **M-INV-1**：``mode_id`` 匹配 ``^[a-z][a-z0-9_]*$``；``action_filter_kind ==
    "none"`` ⇒ ``action_ids == ()``；allow/deny ⇒ ``action_ids`` 非空（构造期拒绝）。
    """

    mode_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    # priority 必填无缺省（设计文档 §3.10 L613；排序键语义见 D-P4-14）。
    priority: int = Field(ge=0)
    action_filter_kind: Literal["none", "allow", "deny"] = "none"
    action_ids: tuple[str, ...] = ()
    systems: tuple[str, ...] = ()
    time_policy: TimePolicy | None = None
    checkpoint_interval: int | None = Field(default=None, ge=1)
    input_policy: JsonValue | None = None
    context: dict[str, JsonValue] = {}

    @model_validator(mode="after")
    def _validate_m_inv_1(self) -> ModeOverlay:
        """M-INV-1 跨字段：none ⇒ action_ids 空；allow/deny ⇒ 非空（全部构造路径）。"""
        _check_m_inv_1(self)
        return self

    def __init__(self, /, **data: Any) -> None:
        """直接构造：M-INV-1 抛具名 :class:`ModeInvariantError`（不静默、不包裹）。

        校验器在 ``super().__init__`` 的校验内运行，其抛出的
        :class:`ModeInvariantError`（ValueError 族）会被 pydantic 重抛为
        ``ValidationError``——本覆盖将其还原为具名类型（其余校验错误原样
        穿透，不转换）。
        """
        try:
            super().__init__(**data)
        except ValidationError as exc:
            message = _m_inv_1_message(exc)
            if message is not None:
                raise ModeInvariantError(message) from exc
            raise


class ModeOverlayRegistry:
    """mode_id → ModeOverlay 不可变注册表（INV-P4-3；构造期核对键 ==
    overlay.mode_id，违例 → :class:`ModeInvariantError`）。

    ``get(mode_id) -> ModeOverlay | None``；``mode_ids() -> tuple[str, ...]``
    casefold 排序。零公开 mutator（配置面构造期注入，K7）。
    """

    def __init__(self, entries: Mapping[str, ModeOverlay]) -> None:
        """构造期逐条核验键 == overlay.mode_id，通过后保留不可变快照（INV-P4-3）。"""
        snapshot: dict[str, ModeOverlay] = {}
        for key, overlay in entries.items():
            if key != overlay.mode_id:
                raise ModeInvariantError(
                    f"ModeOverlayRegistry 键 {key!r} != overlay.mode_id {overlay.mode_id!r}"
                )
            snapshot[key] = overlay
        self._entries = snapshot

    def get(self, mode_id: str) -> ModeOverlay | None:
        """已注册 → overlay；未注册 → None（查找点不抛；"未知模式"拒绝语义
        归下半 T09 解析期原子预校验 → ``UnknownModeError``）。"""
        return self._entries.get(mode_id)

    def mode_ids(self) -> tuple[str, ...]:
        """全部已注册 mode 名（casefold 排序元组）。"""
        return tuple(sorted(self._entries, key=str.casefold))


class ModeInvariantError(ValueError):
    """模式域构造期 / 注册表不变式违反：M-INV-1 跨字段（action_filter_kind 与
    action_ids 一致性）/ ModeOverlayRegistry 键与 overlay.mode_id 不匹配。

    D-P4-17 ValueError 族（输入/配置违反不变式）的 P4 模式域落位；测试按族
    断言基类。
    """


class MergedModeConfiguration(ContractModel):
    """per-property 合并结果（Spec:1422-1433；"所有冲突策略 MUST 可检查"
    Spec:1433（MUST 可检查）经 ``winner_by_field`` 逐字段胜者记录落地）。

    - ``winner_by_field``：字段 ∈ {"time_policy", "checkpoint_interval",
      "input_policy", "action_filter"} → 胜者 mode_id（仅非空值在场时收录）；
    - ``time_policy`` / ``checkpoint_interval`` / ``input_policy``：胜者整值（缺 → None）；
    - ``action_filter_kind`` / ``action_ids``：deny 优先——任一 deny 在场 →
      kind="deny"、ids = 各 deny 集并集（排序）；否则任一 allow 在场 →
      kind="allow"、ids = 各 allow 集**交集**（排序）；否则 none/()；
    - ``activated_systems``：各 overlay systems **并集**（Spec:1426）；
    - ``context``：浅合并——按 (-priority, casefold(mode_id)) 逆序应用
      ``update``（低优先先写、胜者后写覆盖；平手 → casefold 较小 id 胜，D-P4-14）。
    """

    winner_by_field: dict[str, str]
    time_policy: TimePolicy | None
    checkpoint_interval: int | None
    input_policy: JsonValue | None
    action_filter_kind: Literal["none", "allow", "deny"]
    action_ids: tuple[str, ...]
    activated_systems: frozenset[str]
    context: dict[str, JsonValue]


def merge_modes(overlays: Mapping[str, ModeOverlay]) -> MergedModeConfiguration:
    """纯函数合并（输入 = 当前 active 的 overlay 映射；空输入 → 全缺省）。

    算法（确定性，P4 自设纪律，§3.4）：1. 排序键 (-priority, casefold(mode_id))；
    2. 单胜者字段 = 排序首现非空值（D-P4-14）；3. action_filter 三段判定
    （deny 并集 > allow 交集 > 无约束）；4. systems 并集；5. context 逆序
    update（低优先先写、高优先后写覆盖；平手 → casefold 较小 id 后写获胜）。
    平手裁定 = casefold 较小 id（G4-5 断言面；A4 排列不变性对抗）。
    """
    ordered = sorted(
        overlays.values(),
        key=lambda ov: (-ov.priority, ov.mode_id.casefold()),
    )

    winner_by_field: dict[str, str] = {}
    time_policy: TimePolicy | None = None
    checkpoint_interval: int | None = None
    input_policy: JsonValue | None = None
    # 单胜者字段：排序首现非空值（仅非空值在场时收录 winner_by_field 键）。
    for ov in ordered:
        if time_policy is None and ov.time_policy is not None:
            time_policy = ov.time_policy
            winner_by_field["time_policy"] = ov.mode_id
        if checkpoint_interval is None and ov.checkpoint_interval is not None:
            checkpoint_interval = ov.checkpoint_interval
            winner_by_field["checkpoint_interval"] = ov.mode_id
        if input_policy is None and ov.input_policy is not None:
            input_policy = ov.input_policy
            winner_by_field["input_policy"] = ov.mode_id

    # action_filter 三段判定（D-P4-14：deny 优先，安全默认；allow 取交集 = 保守侧）。
    denys = [ov for ov in ordered if ov.action_filter_kind == "deny"]
    allows = [ov for ov in ordered if ov.action_filter_kind == "allow"]
    if denys:
        action_filter_kind: Literal["none", "allow", "deny"] = "deny"
        action_ids = tuple(sorted({action_id for ov in denys for action_id in ov.action_ids}))
    elif allows:
        action_filter_kind = "allow"
        common = frozenset(allows[0].action_ids)
        for ov in allows[1:]:
            common &= frozenset(ov.action_ids)
        action_ids = tuple(sorted(common))
    else:
        action_filter_kind = "none"
        action_ids = ()
    if action_filter_kind != "none":
        # Leader 裁定：单胜者记录 = 排序首现的 kind 等于最终 kind 的 overlay
        # （确定性且排列不变；设计文档对多过滤集情形的单胜者记录有歧义，
        # 见报告 deviations）。
        for ov in ordered:
            if ov.action_filter_kind == action_filter_kind:
                winner_by_field["action_filter"] = ov.mode_id
                break

    activated_systems = frozenset(system for ov in ordered for system in ov.systems)

    # context 浅合并：排序逆序（低 priority 先写、高 priority 后写覆盖；
    # 平手 → casefold 较小 id 后写获胜）。
    context: dict[str, JsonValue] = {}
    for ov in reversed(ordered):
        context.update(ov.context)

    return MergedModeConfiguration(
        winner_by_field=winner_by_field,
        time_policy=time_policy,
        checkpoint_interval=checkpoint_interval,
        input_policy=input_policy,
        action_filter_kind=action_filter_kind,
        action_ids=action_ids,
        activated_systems=activated_systems,
        context=context,
    )


def is_action_available(merged: MergedModeConfiguration, action_id: str) -> bool:
    """D-P4-14 判定序：deny（不在 deny 并集）> allow（在 allow 交集）> none（恒真）。

    任一激活模式的 deny 集含该 action ⇒ 不可用；否则该 action 必须属于
    **每个**持 allow 集的激活模式的 allow 集（无 allow 集的模式不约束）⇒
    可用。
    """
    if merged.action_filter_kind == "deny":
        return action_id not in merged.action_ids
    if merged.action_filter_kind == "allow":
        return action_id in merged.action_ids
    return True
