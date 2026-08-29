"""engine_v2 core 层行动生命周期状态机：迁移表、唯一迁移入口、迁移记录（P3-T03，§3.6 上半）。

依据 ``docs/v2/contracts/P3-scheduler-time-action-design.md``（下称"设计文档"）：

- **§3.6 上半（P3-T03 范围）**：:class:`LifecycleEvent`（P3 语义层事件词表，
  9 事件）、:data:`LIFECYCLE_TRANSITIONS`（六态迁移表，D-P3-07）、
  :class:`LifecycleTransition`（迁移记录，ContractModel，trace 可用）、
  :func:`transition_action`（唯一迁移入口，纯函数）、
  :class:`IllegalTransitionError`（表外迁移，D-P3-16 ①）；
- **D-P3-07**（六态 + 9 事件迁移表 + RESUMED 边）：P1 冻结
  ``ActionLifecycleStatus``（``actions.py:191-204``）零改动；返回边
  ``INTERRUPTED → ACTIVE``（RESUMED）为语义层裁定（Plan Gate "action may
  resume / abort" 为 G3 判据来源）；表外（含终态下任何事件）→
  :class:`IllegalTransitionError`（携带 from/to/event，不静默）；终态
  （COMPLETED/FAILED）无出边——迁移不可逆、可断言；
- **D-P3-08**（progress 纯派生）：INTERRUPTED 与 RESUMED 迁移在 updates 中
  同步更新 ``progress`` 镜像字段（经 :func:`_derived_progress` 推导：
  ``expected_end_tick is None → None``（事件驱动）；否则
  ``min(1.0, max(0.0, (clock_tick - start_tick) /
  (expected_end_tick - start_tick)))``）——纯派生、不累加、不可被任何
  effect 篡改（E-P3-28）；运行时权威值恒为派生，镜像供快照/restore/trace
  观察（G3-1 断言 4：t=12 INTERRUPTED 迁移后 ``act_1.progress == 0.4``）；
- **INTERRUPTED re-anchor**（依据 §5.2 S7、G3-1 断言 6）：INTERRUPTED 边将
  ``base_world_revision`` re-anchor 至当前世界 revision——数值**由调用方
  （Scheduler）经 ``updates`` 携带**（``updates={'base_world_revision':
  world.world_revision}``，§2.4 刻后求值伪代码）；本函数只做合并、不做推导
  （纯函数入参面不携带 world 引用，与 apply_checkpoint / resume_action 的
  re-anchor 口径对齐，D-P3-08）；
- **D-P3-25 ①**（剪除仅终态，全文唯一剪除点）：进入终态（COMPLETED/
  FAILED）时剪除该实例剩余队列条目（kind ∈ {action_checkpoint,
  action_end, deadline} 且 payload ``instance_id`` 命中，确定性簿记）；
  INTERRUPTED 为**非终态**，不剪除任何条目（条目留在队列，§5.2 S8 断言 7 /
  §6.3 A1 口径）；
- **D-P3-16 ①**（错误与诊断分类）：表外 / 实例不存在 / 状态不符一律抛
  :class:`IllegalTransitionError`（继承 :class:`~src.engine_v2.core.clock.
  SchedulerError` 基类族，宿主置依赖叶 ``clock.py``，§3.2/§3.3，依赖无环）。

**T03/T04 分工**（§3.10 同文件单 Owner 纪律）：§3.6 下半（``progress_of`` /
``apply_checkpoint`` / ``start_action`` / ``resume_action`` / ``abort_action``
/ ``complete_action`` / ``fail_action``）由 P3-T04 于本文件**末尾追加**；
:data:`__all__` 最终由 P3-T04 补全至 12 项（本任务仅落本范围 5 符号）。

纪律（设计文档 §0.3 继承 / §8.3 P3 专项）：

- **纯函数 + 重建模式**：RuntimeState 簿记变更唯一缝隙为
  :func:`~src.engine_v2.core.clock.rebuild_runtime`（``clock.py``，P1
  ``state.py:213-214`` 授权的行为侧实现）——返回新实例、输入不变
  （ContractModel frozen）；纯函数不消费 P2 符号（§3.2 依赖图）；
- **无墙钟 / 无随机**：只 import stdlib + pydantic + 同包 ``src.engine_v2``
  core 既有模块；P3 专项黑名单 ``datetime`` / ``time`` / ``random`` /
  ``asyncio`` 对本模块生效（§8.3）；:func:`transition_action` **不是**时钟
  写点（唯一时钟写点 ``set_logical_tick``，D-P3-02）——``at_tick`` 只记录
  于迁移记录与审计字段；
- **last_transition_tick 审计字段**（``actions.py:243``）：逐迁移自动置
  ``at_tick``（D-P3-07 一致性）；
- **revision 解耦**（P1 D-5）：本模块只写 ``RuntimeState`` 簿记，不推进
  ``world_revision``。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Final, Sequence

from pydantic import JsonValue

from src.engine_v2.core.actions import ActionLifecycleStatus, ActiveAction
from src.engine_v2.core.clock import SchedulerError, rebuild_runtime
from src.engine_v2.core.effects import ProposedEffect
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.event_queue import enqueue_scheduled_event, make_scheduled_event
from src.engine_v2.core.ids import ActionInstanceId, new_trace_record_id
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.state import RuntimeState, ScheduledEvent, WorldState
from src.engine_v2.core.trace import TraceKind, TraceRecord

__all__ = [
    # —— §3.6 上半（P3-T03 已落）——
    "LifecycleEvent",
    "LIFECYCLE_TRANSITIONS",
    "LifecycleTransition",
    "transition_action",
    "IllegalTransitionError",
    # —— §3.6 下半（P3-T04 同文件串行追加，§3.10）：Leader 裁定补全至设计全量 12 项 ——
    "progress_of",
    "apply_checkpoint",  # T04a2 已落（Leader 裁定 E-P3-40：checkpoint_interval 间隔通道）
    # T04a 未落：Leader 裁定范围划归 T04b
    "start_action",  # noqa: F822
    "resume_action",
    "abort_action",
    "complete_action",
    "fail_action",
]


class LifecycleEvent(str, Enum):
    """P3 语义层生命周期事件词表（设计文档 §3.6；D-P3-07 九事件边）。

    :data:`LIFECYCLE_TRANSITIONS` 边的数据词表——与 P1 冻结
    ``ActionLifecycleStatus``（``actions.py:191-204``，零改动）正交：
    状态是节点，事件是边触发器。
    """

    VALIDATION_ACCEPTED = "validation_accepted"
    VALIDATION_REJECTED = "validation_rejected"
    SCHEDULED = "scheduled"  # VALIDATING → ACTIVE（预约开跑确认）
    CHECKPOINT = "checkpoint"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    RESUMED = "resumed"  # INTERRUPTED → ACTIVE（D-P3-07，Plan Gate 授权）
    ABORTED = "aborted"


#: 迁移表（D-P3-07，状态机唯一权威）：from 状态 → 合法边集合
#: ``frozenset{(event, to 状态)}``。表外（含终态下任何事件）=
#: :class:`IllegalTransitionError`；终态出边集为空（迁移不可逆、可断言）。
LIFECYCLE_TRANSITIONS: Final[
    dict[ActionLifecycleStatus, frozenset[tuple[LifecycleEvent, ActionLifecycleStatus]]]
] = {
    ActionLifecycleStatus.PROPOSED: frozenset(
        {
            (LifecycleEvent.VALIDATION_ACCEPTED, ActionLifecycleStatus.VALIDATING),
            (LifecycleEvent.VALIDATION_REJECTED, ActionLifecycleStatus.FAILED),
        }
    ),
    ActionLifecycleStatus.VALIDATING: frozenset(
        {
            (LifecycleEvent.SCHEDULED, ActionLifecycleStatus.ACTIVE),
            (LifecycleEvent.VALIDATION_REJECTED, ActionLifecycleStatus.FAILED),
        }
    ),
    ActionLifecycleStatus.ACTIVE: frozenset(
        {
            (LifecycleEvent.CHECKPOINT, ActionLifecycleStatus.ACTIVE),
            (LifecycleEvent.INTERRUPTED, ActionLifecycleStatus.INTERRUPTED),
            (LifecycleEvent.COMPLETED, ActionLifecycleStatus.COMPLETED),
            (LifecycleEvent.FAILED, ActionLifecycleStatus.FAILED),
        }
    ),
    ActionLifecycleStatus.INTERRUPTED: frozenset(
        {
            (LifecycleEvent.RESUMED, ActionLifecycleStatus.ACTIVE),
            (LifecycleEvent.ABORTED, ActionLifecycleStatus.FAILED),
        }
    ),
    ActionLifecycleStatus.COMPLETED: frozenset(),  # 终态：表外 = IllegalTransitionError
    ActionLifecycleStatus.FAILED: frozenset(),
}


class LifecycleTransition(ContractModel):
    """生命周期迁移记录（设计文档 §3.6，trace 可用；计数口径 D-P3-19）。

    - ``instance_id``：发生迁移的行动实例（键与 ``active_actions`` 一致，
      P1 键一致性纪律同款）；
    - ``from_status`` / ``to_status``：迁移前后状态（= :data:`LIFECYCLE_TRANSITIONS`
      的一条边）；
    - ``event``：触发迁移的语义层事件（表边第一元）；
    - ``at_tick``：迁移发生的逻辑刻（= :func:`transition_action` 的
      ``at_tick`` 入参；归属口径 D-P3-20——逻辑时刻由迁移记录承载，
      不打戳于事务/事件）；
    - ``reason``：可空自由文本（编排层诊断信息，如边界 reason，原样透传）。

    ContractModel（frozen / extra="forbid"）：可序列化、可断言、可进 trace。
    """

    instance_id: ActionInstanceId
    from_status: ActionLifecycleStatus
    to_status: ActionLifecycleStatus
    event: LifecycleEvent
    at_tick: int
    reason: str | None = None


class IllegalTransitionError(SchedulerError):
    """表外生命周期迁移（设计文档 §3.6 / D-P3-07 / D-P3-16 ①）。

    于迁移点抛出（可检查不静默）：信息携带 from/to/event 三要素（实例不存在
    / 状态不符与表外迁移同类，统一本型）——无静默跳过或静默修正的第三条路
    （D-P3-16）。
    """


#: 可剪除的队列条目 kind 集（D-P3-25 ①：全文唯一剪除点 = 进入终态；该决策
#: 正文明确列举三 kind）。此三 kind 的 payload 契约必填 ``instance_id``
#: （``event_queue.py``，§2.5 表）——匹配按 kind + payload 双条件。
_PRUNABLE_ENTRY_KINDS: Final[frozenset[str]] = frozenset(
    {"action_checkpoint", "action_end", "deadline"}
)

#: :func:`transition_action` 同步写 ``progress`` 镜像的两个事件（E-P3-28）。
_PROGRESS_MIRROR_EVENTS: Final[frozenset[LifecycleEvent]] = frozenset(
    {LifecycleEvent.INTERRUPTED, LifecycleEvent.RESUMED}
)

#: 终态集（D-P3-07 无出边；D-P3-25 ① 唯一剪除点的判定面）。
_TERMINAL_STATUSES: Final[frozenset[ActionLifecycleStatus]] = frozenset(
    {ActionLifecycleStatus.COMPLETED, ActionLifecycleStatus.FAILED}
)


def _derived_progress(action: ActiveAction, clock_tick: int) -> float | None:
    """D-P3-08 progress 纯推导（私有辅助；公共符号 ``progress_of`` 属 P3-T04
    范围，公式与 §3.6 代码块逐字一致）。

    ``expected_end_tick is None`` → ``None``（事件驱动，无时长语义）；否则
    ``min(1.0, max(0.0, (clock_tick - start_tick) /
    (expected_end_tick - start_tick)))``。纯派生、不累加——存储
    ``progress`` 仅作快照镜像，不可被任何 effect 篡改。正常构造路径（T04
    ``start_action``：``expected_end_tick = at_tick + duration``，duration ≥ 1，
    D-P3-01 钳制）保证分母为正。
    """
    if action.expected_end_tick is None:
        return None
    span = action.expected_end_tick - action.start_tick
    ratio = (clock_tick - action.start_tick) / span
    return min(1.0, max(0.0, ratio))


def _rebuild_action(action: ActiveAction, updates: dict[str, Any]) -> ActiveAction:
    """rebuild 模式合并 updates 进 :class:`ActiveAction` 字段（设计文档 §3.6
    "rebuild 模式，与 P1 冻结字段逐字对齐"）。

    ``model_dump()`` → dict 更新 → ``model_validate()``——与
    :func:`~src.engine_v2.core.clock.rebuild_runtime` 同路径（P1 唯一合法
    序列化路径）；updates 键须为 P1 冻结字段名（未知键 → pydantic
    ``ValidationError``，ContractModel extra="forbid"，可检查不静默）；
    不修改输入（frozen）。
    """
    payload = action.model_dump()
    payload.update(updates)
    return ActiveAction.model_validate(payload)


def _prune_instance_entries(
    queue: list[ScheduledEvent], instance_id: ActionInstanceId
) -> list[ScheduledEvent]:
    """剪除该实例剩余队列条目（D-P3-25 ① 确定性簿记，全文唯一剪除点）。

    仅匹配 kind ∈ :data:`_PRUNABLE_ENTRY_KINDS`（action_checkpoint /
    action_end / deadline）**且** payload ``instance_id`` 命中的条目——
    其余 kind（action_start / wakeup / decision_boundary / event）与其他
    实例的条目永不剪除。返回新列表；输入不可变。
    """
    return [
        entry
        for entry in queue
        if not (
            entry.kind in _PRUNABLE_ENTRY_KINDS
            and entry.payload.get("instance_id") == instance_id
        )
    ]


def transition_action(
    runtime: RuntimeState,
    instance_id: ActionInstanceId,
    event: LifecycleEvent,
    *,
    at_tick: int,
    reason: str | None = None,
    updates: dict[str, JsonValue] | None = None,
) -> tuple[RuntimeState, LifecycleTransition]:
    """唯一迁移入口（设计文档 §3.6 / D-P3-07）。

    语义（逐条）：

    1. **查表**（:data:`LIFECYCLE_TRANSITIONS` 为状态机唯一权威）：实例不存在
       或 (from, event) 表外（含终态下任何事件）→
       :class:`IllegalTransitionError`（携带 from/to/event，不静默）；
    2. **updates 合并**（rebuild 模式，与 P1 冻结字段逐字对齐）：``updates``
       字段合并进该实例的 :class:`ActiveAction` 记录；
    3. **受管字段**（本函数无条件写入，优先于调用方同名值）：``status`` =
       表边 to 状态（D-P3-07：目标态由表推导，非调用方指定）；
       ``last_transition_tick = at_tick``（``actions.py:243`` 审计字段）；
    4. **progress 镜像**（E-P3-28）：INTERRUPTED 与 RESUMED 迁移在 updates 中
       同步更新 ``progress`` 镜像字段——``_derived_progress(action, at_tick)``
       （D-P3-08：纯派生、不累加、不可被 effect 篡改）；运行时权威值恒为
       派生，镜像供快照/restore/trace 观察（G3-1 断言 4：t=12 INTERRUPTED
       迁移后 ``act_1.progress == 0.4``）；
    5. **INTERRUPTED re-anchor**：INTERRUPTED 边将 ``base_world_revision``
       re-anchor 至当前世界 revision——数值由调用方（Scheduler）经 ``updates``
       携带（``updates={'base_world_revision': world.world_revision}``，
       §2.4 刻后求值伪代码；依据 §5.2 S7、G3-1 断言 6）；
    6. **剪除仅终态**（D-P3-25 ①，全文唯一剪除点）：进入终态
       （COMPLETED/FAILED）时剪除该实例剩余队列条目（action_checkpoint /
       action_end / deadline 且 payload ``instance_id`` 命中）；INTERRUPTED
       为非终态，不剪除任何条目（条目留在队列，§5.2 S8 断言 7 / §6.3 A1）。

    返回 ``(新 RuntimeState, 迁移记录)``：rebuild 模式、输入不可变；不推进
    时钟（唯一写点 ``set_logical_tick``，D-P3-02），不推进
    ``world_revision``（P1 D-5：RuntimeState 簿记不推进 revision）。
    """
    action = runtime.active_actions.get(instance_id)
    if action is None:
        raise IllegalTransitionError(
            f"illegal transition: from=<missing> to=<illegal> event={event.value} "
            f"(instance={instance_id} 不存在于 active_actions)"
        )
    from_status = action.status
    allowed = LIFECYCLE_TRANSITIONS[from_status]
    to_status = next((to for ev, to in allowed if ev == event), None)
    if to_status is None:
        legal = ", ".join(sorted({ev.value for ev, _ in allowed})) or "<none>"
        raise IllegalTransitionError(
            f"illegal transition: from={from_status.value} to=<illegal> "
            f"event={event.value} (instance={instance_id}; "
            f"{from_status.value} 对 event {event.value} 无合法迁移；"
            f"合法事件：{legal})"
        )
    merged: dict[str, Any] = dict(updates) if updates is not None else {}
    if event in _PROGRESS_MIRROR_EVENTS:
        merged["progress"] = _derived_progress(action, at_tick)
    merged["status"] = to_status
    merged["last_transition_tick"] = at_tick
    new_action = _rebuild_action(action, merged)
    rebuild_updates: dict[str, Any] = {
        "active_actions": {**runtime.active_actions, instance_id: new_action}
    }
    if to_status in _TERMINAL_STATUSES:
        pruned = _prune_instance_entries(runtime.scheduler_queue, instance_id)
        if len(pruned) != len(runtime.scheduler_queue):
            rebuild_updates["scheduler_queue"] = pruned
    new_runtime = rebuild_runtime(runtime, **rebuild_updates)
    transition = LifecycleTransition(
        instance_id=instance_id,
        from_status=from_status,
        to_status=to_status,
        event=event,
        at_tick=at_tick,
        reason=reason,
    )
    return new_runtime, transition


# ======================================================================
# §3.6 下半（P3-T04a：progress / resume / abort / complete / fail）——
# 同文件串行追加（§3.10 单 Owner 纪律；T03 已落迁移表层，本段全部复用
# :func:`transition_action` 唯一迁移入口，不重复实现迁移/剪除/镜像簿记）。
#
# T04a 范围（Leader 裁定）：``progress_of`` / ``resume_action`` /
# ``abort_action`` / ``complete_action`` / ``fail_action``。同属 §3.6 下半
# 的 ``apply_checkpoint`` / ``start_action`` 不在本任务落盘：前者存在
# checkpoint 间隔传输缝隙待 Leader 裁定（固定签名不携带间隔，P1 冻结
# ActiveAction 无间隔字段——详 .review-drafts/p3-impl-t04a-report.json）；
# 后者按 Leader 裁定范围划归 T04b。
# ======================================================================


def _has_checkpoint_entry(queue: list[ScheduledEvent], instance_id: ActionInstanceId) -> bool:
    """队列是否仍含该实例的 ``action_checkpoint`` 条目（存在性口径）。

    D-P3-25 ① resume 不重复入队的检查面：``kind == "action_checkpoint"``
    且 payload ``instance_id`` 命中（与 :data:`_PRUNABLE_ENTRY_KINDS` 剪除
    匹配同款双条件）。正常流程中断不剪除（INTERRUPTED 非终态），resume 时
    下一 checkpoint 条目必然仍在队列（§5.3 A1）；缺陷缺失时的补入队判定
    以本存在性检查为唯一口径。
    """
    return any(
        entry.kind == "action_checkpoint" and entry.payload.get("instance_id") == instance_id
        for entry in queue
    )


def progress_of(action: ActiveAction, clock_tick: int) -> float | None:
    """D-P3-08 progress 纯派生（公共符号；设计文档 §3.6 下半）。

    公式与 §3.6 代码块逐字一致：``expected_end_tick is None → None``
    （事件驱动，无时长语义）；否则 ``min(1.0, max(0.0, (clock_tick -
    start_tick) / (expected_end_tick - start_tick)))``。纯派生、不累加——
    progress 不可被任何 effect 篡改（存储 ``progress`` 仅作快照镜像，
    E-P3-28；"不得 2"的数学保证：位置/进度只能在完成刻经事务移动）。
    运行时权威值恒为派生，本函数即该权威值。

    委托本模块私有 :func:`_derived_progress`（T03 已落，公式同源）——
    复用、不重复实现。
    """
    return _derived_progress(action, clock_tick)


def resume_action(
    world: WorldState,
    runtime: RuntimeState,
    instance_id: ActionInstanceId,
    *,
    at_tick: int,
    current_revision: Revision,
) -> tuple[WorldState, RuntimeState, LifecycleTransition]:
    """INTERRUPTED→ACTIVE（RESUMED 边，设计文档 §3.6 下半；D-P3-07 / D-P3-25）。

    语义（逐条）：

    1. **时间预算不变**：``start_tick`` / ``expected_end_tick`` **不变**
       （progress 连续，暂停不消耗逻辑时间——§2.3 / D-P3-08）——本函数不写
       该两字段；
    2. **re-anchor**：``base_world_revision`` re-anchor 至 ``current_revision``
       （经 :func:`transition_action` ``updates`` 携带，D-P3-08 口径；与
       INTERRUPTED 边 re-anchor 口径对齐）；
    3. **progress 镜像**：RESUMED 迁移同步更新 ``progress`` 镜像
       （``progress_of(action, at_tick)``，E-P3-28：纯派生、不累加、不可被
       effect 篡改）——由 :func:`transition_action` 落地（T03），本函数不
       重复推导；
    4. **中断不剪除**（D-P3-25 ①）：INTERRUPTED 为非终态，全部队列条目
       保留（迁移不触发剪除——:func:`transition_action` 终态分支口径）；
       resume 从原条目继续求值、**不重复入队**（与 §5.3 A1 "cp@20 已在
       队列 → 不重复入队"同口径）；
    5. **防御分支**（D-P3-25 ①，正常流程不应发生；发生即簿记缺陷，可观察、
       可修复）：实例在队列中缺失 ``action_checkpoint`` 条目且
       ``next_checkpoint_tick`` 非空（周期 checkpoint 行动）→ 按
       ``next_checkpoint_tick`` 补入队（:func:`make_scheduled_event`，
       ``entry_id`` 经 ids.py 冻结工厂签发），迁移记录 ``reason`` 承载诊断
       串 ``checkpoint_requeued_after_defect``；事件驱动行动
       （``next_checkpoint_tick is None``）本无周期 checkpoint，条目缺失不
       构成缺陷——不补入队、无诊断（``reason`` 保持 None）。

    纯函数纪律：``world`` 原样返回（本函数不写世界——re-anchor 是
    ``ActiveAction`` 字段簿记，由 ``current_revision`` 入参驱动）；不推进
    逻辑时钟（唯一写点 ``set_logical_tick``，D-P3-02）；不推进
    ``world_revision``（P1 D-5：RuntimeState 簿记不推进 revision）。表外
    （非 INTERRUPTED 源状态 / 实例不存在）→ :class:`IllegalTransitionError`
    （复用 :func:`transition_action`，D-P3-16 ①）。
    """
    action = runtime.active_actions.get(instance_id)
    requeue = (
        action is not None
        and action.next_checkpoint_tick is not None
        and not _has_checkpoint_entry(runtime.scheduler_queue, instance_id)
    )
    new_runtime, transition = transition_action(
        runtime,
        instance_id,
        LifecycleEvent.RESUMED,
        at_tick=at_tick,
        reason="checkpoint_requeued_after_defect" if requeue else None,
        updates={"base_world_revision": current_revision},
    )
    if requeue:
        entry = make_scheduled_event(
            "action_checkpoint",
            action.next_checkpoint_tick,
            payload={"instance_id": str(instance_id)},
        )
        new_runtime = enqueue_scheduled_event(new_runtime, entry)
    return world, new_runtime, transition


def abort_action(
    runtime: RuntimeState,
    instance_id: ActionInstanceId,
    *,
    at_tick: int,
    reason: str = "aborted",
) -> RuntimeState:
    """INTERRUPTED→FAILED（ABORTED 边，设计文档 §3.6 下半；D-P3-25 收敛路径）。

    语义（逐条）：

    - ``result_summary = {"reason": <reason>, "tick": <at_tick>,
      "progress": progress_of(action, at_tick)}``——progress 取**中止刻**
      的 D-P3-08 纯派生值（事件驱动行动为 None；中断刻与中止刻之间的时钟
      推进体现在派生值中，不依赖存储镜像）；
    - **剪除剩余队列条目**（进入终态——D-P3-25 ① 全文唯一剪除点，由
      :func:`transition_action` 终态分支落地）；
    - **无完成 effect**：返回类型仅 ``RuntimeState``——迁移记录为内部簿记
      （不返回给调用方）；不涉世界、不推进 ``world_revision``（P1 D-5）。

    表外（ABORTED 边仅出自 INTERRUPTED——ACTIVE 无直接 ABORTED 边，
    E-P3-29 ②；非 INTERRUPTED 源状态 / 实例不存在）→
    :class:`IllegalTransitionError`（D-P3-16 ①）。
    """
    action = runtime.active_actions.get(instance_id)
    updates = {
        "result_summary": {
            "reason": reason,
            "tick": at_tick,
            "progress": progress_of(action, at_tick) if action is not None else None,
        }
    }
    new_runtime, _transition = transition_action(
        runtime,
        instance_id,
        LifecycleEvent.ABORTED,
        at_tick=at_tick,
        updates=updates,
    )
    return new_runtime


def complete_action(
    world: WorldState,
    runtime: RuntimeState,
    instance_id: ActionInstanceId,
    *,
    at_tick: int,
    completion_effects: Sequence[ProposedEffect],
) -> tuple[WorldState, RuntimeState, LifecycleTransition]:
    """ACTIVE→COMPLETED（COMPLETED 边，设计文档 §3.6 下半；D-P3-08 完成语义）。

    语义（逐条）：

    - ``result_summary = {"completed_at": at_tick}``；
    - **纯函数只出 effect、不写世界**：``completion_effects``（由
      ``spec.completion_trigger`` 在 COMPLETED 刻求值所得，如位置 effect）
      由调用方（Scheduler）经 P2 管道（CascadeExecutor）提交——本函数不触碰
      ``world``（输入 world 原样返回，同一对象）、不推进 ``world_revision``
      （P1 D-5）；无 ``completion_effects`` 时仍提交生命周期簿记（终态迁移
      + 剪除）；位置/进度只在此刻经事务移动（"不得 2"数学保证）；
    - **终态迁移剪除**该实例剩余队列条目（D-P3-25 ① 全文唯一剪除点，由
      :func:`transition_action` 终态分支落地）。

    表外（非 ACTIVE 源状态 / 实例不存在）→ :class:`IllegalTransitionError`
    （D-P3-16 ①）。
    """
    new_runtime, transition = transition_action(
        runtime,
        instance_id,
        LifecycleEvent.COMPLETED,
        at_tick=at_tick,
        updates={"result_summary": {"completed_at": at_tick}},
    )
    return world, new_runtime, transition


def fail_action(
    runtime: RuntimeState,
    instance_id: ActionInstanceId,
    *,
    at_tick: int,
    reason: str,
) -> RuntimeState:
    """ACTIVE→FAILED（FAILED 边，设计文档 §3.6 下半；E-P3-05 口径）。

    语义（逐条）：

    - ``result_summary = {"reason": reason, "tick": at_tick}``；
    - **FAILED 边仅出自 ACTIVE**（迁移表唯一 FAILED 源状态）：VALIDATING
      被拒经 ``VALIDATION_REJECTED`` 边，属 submit_proposal REJECT 轨迹
      路径，不经本函数——对 VALIDATING / PROPOSED 实例调用本函数为表外
      → :class:`IllegalTransitionError`（E-P3-05：文档串限定仅
      ACTIVE→FAILED）；
    - 调用方典型诊断串：``deadline`` 条目命中仍 ACTIVE 的行动 →
      ``fail_action(..., reason="deadline_missed")``（§2.4 match 分支口径）；
    - **终态迁移剪除**该实例剩余队列条目（D-P3-25 ① 全文唯一剪除点，由
      :func:`transition_action` 终态分支落地）；
    - 返回类型仅 ``RuntimeState``——迁移记录为内部簿记（不返回给调用方）；
      不涉世界、不推进 ``world_revision``（P1 D-5）。

    表外（非 ACTIVE 源状态 / 实例不存在）→ :class:`IllegalTransitionError`
    （D-P3-16 ①）。
    """
    new_runtime, _transition = transition_action(
        runtime,
        instance_id,
        LifecycleEvent.FAILED,
        at_tick=at_tick,
        updates={"result_summary": {"reason": reason, "tick": at_tick}},
    )
    return new_runtime


# ======================================================================
# §3.6 下半（P3-T04a2：apply_checkpoint）——
# 同文件串行追加（§3.10 单 Owner 纪律）；全部复用 T03
# :func:`transition_action`（唯一迁移入口）与 T04a :func:`progress_of`
# （D-P3-08 纯派生），不重复实现迁移 / 镜像 / 队列簿记。
#
# 间隔通道（Leader 裁定 E-P3-40）：签名增关键字
# ``checkpoint_interval: int | None = None``（Scheduler 透传
# ``time_policy.checkpoint_interval_ticks``，D-P3-13；None → 不入队下一
# checkpoint）——与同文件 ``start_action`` 的 ``checkpoint_interval``
# 关键字同款先例。T04a 阻塞的"固定签名不携带间隔"缝隙由本条闭合（P1
# 冻结 ``ActiveAction`` 无间隔字段、§3.2 依赖图禁止 action_lifecycle
# 反向 import scheduler——间隔由调用方显式携带，纯函数入参面不扩大至
# 策略对象）。
# ======================================================================


def apply_checkpoint(
    runtime: RuntimeState,
    instance_id: ActionInstanceId,
    *,
    at_tick: int,
    current_revision: Revision,
    checkpoint_interval: int | None = None,
) -> tuple[RuntimeState, TraceRecord | None]:
    """CHECKPOINT 自迁移（设计文档 §3.6 下半；D-P3-07/08/13，E-P3-12 ②，
    E-P3-40 间隔通道）。

    语义（逐条）：

    1. **CHECKPOINT 自迁移**（ACTIVE → ACTIVE，D-P3-07 表边）：经
       :func:`transition_action`（唯一迁移入口，T03）——
       ``last_transition_tick = at_tick``（``actions.py:243`` 审计字段，
       自动）；本函数不重复实现迁移簿记；
    2. **progress 重算**（D-P3-08）：``progress`` 镜像同步至 checkpoint
       刻的纯派生值（``progress_of(action, at_tick)``）——CHECKPOINT
       事件不在 T03 镜像事件集（仅 INTERRUPTED/RESUMED 自动镜像），由
       本函数经 ``updates`` 携带；
    3. **re-anchor**：``base_world_revision`` re-anchor 至
       ``current_revision``（经 ``updates`` 携带，D-P3-08 口径；与
       INTERRUPTED 边 / :func:`resume_action` 的 re-anchor 口径对齐，
       依据 §5.2 S7、G3-1 断言 6）；
    4. **入队下一 checkpoint**（D-P3-13；间隔通道 E-P3-40）：
       ``checkpoint_interval`` 非 None → 经 :func:`make_scheduled_event`
       + :func:`enqueue_scheduled_event` 入队（``kind="action_checkpoint"``、
       ``due_tick = at_tick + checkpoint_interval``、payload
       ``{"instance_id": …}``、``entry_id`` 经 ``new_scheduled_entry_id()``
       工厂——``make_scheduled_event`` 缺省签发），``next_checkpoint_tick``
       镜像同推进至该刻（§6.1 "next_checkpoint_tick 前进"口径；§5.2 S4 /
       §5.3 A2 两刻推演：同一公式在 t=10 → cp@20、t=20 → cp@30，与
       Gate 表逐字一致）；``None`` → 不入队下一 checkpoint，且
       ``next_checkpoint_tick`` 镜像置 ``None``（下一 checkpoint 不存在——
       该字段语义为"下一 scheduled checkpoint 的刻"，保留刚处理完的刻
       即过去值，会诱导 :func:`resume_action` 防御补入队分支按过去刻
       补入 → ``QueueInvariantError``，故显式清空）；
    5. **非 ACTIVE 守卫（F2-02，第二道防线，E-P3-12 ② / D-P3-25）**：
       实例 status 为 INTERRUPTED 或终态（COMPLETED/FAILED）→ **不查
       迁移表、不调 :func:`transition_action`、不入队下一 checkpoint**，
       返回 ``(未变更 runtime, 一条诊断 :class:`TraceRecord`)``——由调用
       方（Scheduler）追加进本次调用 ``outcome.trace_records``：
       ``kind = TraceKind.SYSTEM``（``trace.py:110`` 既有词表值，
       ``trace.py:113-139`` 开放信封），开放 ``payload`` 携带诊断串 +
       实例（终态 → ``checkpoint_skipped_terminal``；INTERRUPTED →
       ``checkpoint_skipped_interrupted``），记录坐标按产生时权威序填充
       （``logical_tick = at_tick``、``world_revision = current_revision``）；
       跳过该条目、时钟继续（玩家暂停场景由 D-P3-24 入口首检第一道
       拦截，§2.4）；
    6. **表外 / 实例缺失**：实例不存在于 ``active_actions``，或 status
       为 PROPOSED/VALIDATING（checkpoint 条目只可能在 SCHEDULED 迁移后
       入队——该状态 + cp 条目 = 簿记不变量违例，不属第 5 条守卫口径）
       → :class:`IllegalTransitionError`（可检查不静默，D-P3-16 ①；与
       直接调 :func:`transition_action` 的表外行为同型——守卫仅对两个
       具名 skip 族短路，其余一律不静默）。

    纯 ``RuntimeState`` 簿记（P1 D-5）：不提交世界事务、不推进
    ``world_revision``（本函数入参面不携带 world——re-anchor 由
    ``current_revision`` 驱动）；不推进逻辑时钟（唯一写点
    ``set_logical_tick``，D-P3-02——条目 due_tick 即当前刻，时钟跳变由
    调用方于本函数之前完成）。正常路径返回 ``(新 runtime, None)``。
    """
    action = runtime.active_actions.get(instance_id)
    if action is None:
        raise IllegalTransitionError(
            "illegal transition: from=<missing> to=<illegal> event=checkpoint "
            f"(instance={instance_id} 不存在于 active_actions)"
        )
    status = action.status
    if status is not ActionLifecycleStatus.ACTIVE:
        if status is ActionLifecycleStatus.INTERRUPTED:
            diagnostic = "checkpoint_skipped_interrupted"
        elif status in _TERMINAL_STATUSES:
            diagnostic = "checkpoint_skipped_terminal"
        else:
            raise IllegalTransitionError(
                f"illegal transition: from={status.value} to=<illegal> "
                f"event=checkpoint (instance={instance_id}; checkpoint 条目仅可能"
                f"存在于 SCHEDULED 迁移之后，{status.value} + cp 条目 = 簿记不变量违例)"
            )
        record = TraceRecord(
            record_id=new_trace_record_id(),
            kind=TraceKind.SYSTEM,
            world_revision=current_revision,
            logical_tick=at_tick,
            payload={
                "diagnostic": diagnostic,
                "instance_id": str(instance_id),
            },
        )
        return runtime, record
    next_tick = (
        at_tick + checkpoint_interval if checkpoint_interval is not None else None
    )
    updates: dict[str, Any] = {
        "progress": progress_of(action, at_tick),
        "base_world_revision": current_revision,
        "next_checkpoint_tick": next_tick,
    }
    new_runtime, _transition = transition_action(
        runtime,
        instance_id,
        LifecycleEvent.CHECKPOINT,
        at_tick=at_tick,
        updates=updates,
    )
    if checkpoint_interval is not None:
        entry = make_scheduled_event(
            "action_checkpoint",
            at_tick + checkpoint_interval,
            payload={"instance_id": str(instance_id)},
        )
        new_runtime = enqueue_scheduled_event(new_runtime, entry)
    return new_runtime, None
