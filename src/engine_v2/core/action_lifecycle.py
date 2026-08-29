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
from typing import Any, Final

from pydantic import JsonValue

from src.engine_v2.core.actions import ActionLifecycleStatus, ActiveAction
from src.engine_v2.core.clock import SchedulerError, rebuild_runtime
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.ids import ActionInstanceId
from src.engine_v2.core.state import RuntimeState, ScheduledEvent

__all__ = [
    "LifecycleEvent",
    "LIFECYCLE_TRANSITIONS",
    "LifecycleTransition",
    "transition_action",
    "IllegalTransitionError",
    # P3-T04（同文件串行追加，§3.10）将本表补全至 12 项：progress_of /
    # apply_checkpoint / start_action / resume_action / abort_action /
    # complete_action / fail_action（§3.6 下半）。
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
