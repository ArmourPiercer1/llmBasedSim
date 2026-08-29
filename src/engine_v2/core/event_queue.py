"""engine_v2 core 层调度队列 kind 词表、payload 契约与队列操作纯函数（P3-T01）。

依据 ``docs/v2/contracts/P3-scheduler-time-action-design.md``（下称"设计文档"）：

- §2.5 / D-P3-04：**复用 P1 冻结** ``ScheduledEvent``（``state.py:143-155``，
  零改动；任务书"新类型"预期按 P1 零改动最高约束裁定为复用，§8.5-D1），P3
  新增只有三样——**kind 封闭词表**（:data:`SCHEDULED_EVENT_KINDS`，§2.5 表
  为唯一定义处，7 kind）、**逐 kind payload 契约**（:func:`make_scheduled_event`
  在入队点强制校验——可检查不静默）、**队列操作纯函数**（本模块）；
- §2.5 / D-P3-05 队列有序性三条不变量（``enqueue_scheduled_event`` 维护）：
  1. **写时稳定排序**：入队后按 ``due_tick`` 单键稳定重排（相等 tick 保持
     插入相对序）——队列任意时刻可检（K7），``take_due`` 无需运行时排序；
  2. **同刻序 = 稳定 FIFO**：同 ``due_tick`` 批内按列表位置（插入序）处理，
     调度器永不重排（重排 = 不确定性源）；
  3. **禁止过去调度**：``due_tick < runtime.logical_tick`` →
     :class:`QueueInvariantError`（时间只能向前，与 D-P3-02 单调性同源）；
  4. **身份唯一**：``entry_id`` 由 ``new_scheduled_entry_id()``（``sch_``
     前缀，``ids.py`` 工厂）签发，重复 ``entry_id`` 入队 →
     :class:`QueueInvariantError`（构造点拒绝，KBC-2 同款去重纪律）。
- ``kind="event"`` payload 两种形态都是**声明式**（K7 / 不得 3），且
  ``trigger_id`` 与 ``effects`` **恰居其一**（互斥，唯一口径，R7-S4 风险 3）：
  ``{"trigger_id": "scenario.encounter_12"}`` 引用命名的 P2
  ``CascadeTrigger``（注册表持有）；``{"effects": [ProposedEffect JSON…],
  "producer": "…"}`` 携带显式预声明效果批——payload 内禁止可执行物；缺
  ``trigger_id`` 且无 ``effects``，或两者同时存在 →
  :class:`QueueInvariantError`；
- ``kind="wakeup"`` payload 仅携带 ``actor_id``（§2.5 尾注双记录口径：
  ``ActorWakeup.reason``（``state.py:166``，可空）仅存于 ``actor_wakeups``
  侧，``reason`` 不入队列条目 payload）。

纪律（§0.3 继承 / §8.3 P3 专项）：只 import stdlib + pydantic + 同包
``src.engine_v2`` core 既有模块；P3 专项黑名单 ``datetime`` / ``time`` /
``random`` / ``asyncio`` 对本模块生效。:class:`QueueInvariantError` 继承
``clock.SchedulerError``（D-P3-16 错误基类族宿主置依赖叶 ``clock.py``，
依赖无环，§3.2）。
"""

from __future__ import annotations

from typing import Final

from pydantic import JsonValue

from src.engine_v2.core.clock import SchedulerError, rebuild_runtime
from src.engine_v2.core.ids import ScheduledEntryId, new_scheduled_entry_id
from src.engine_v2.core.state import RuntimeState, ScheduledEvent

__all__ = [
    "SCHEDULED_EVENT_KINDS",
    "make_scheduled_event",
    "enqueue_scheduled_event",
    "take_due",
    "QueueInvariantError",
]


class QueueInvariantError(SchedulerError):
    """调度队列不变量违例（设计文档 §3.4 / D-P3-05 / D-P3-16）。

    于构造点/入队点抛出（可检查不静默）：kind 词表外、逐 kind 必填 payload
    键缺失、``kind="event"`` 的 ``trigger_id`` / ``effects`` 未恰居其一
    （互斥）、``due_tick < 0``、过去调度（``due_tick < logical_tick``）、
    重复 ``entry_id`` 入队。
    """


#: kind 封闭词表（§2.5 表 kind 列，唯一定义处）：7 kind。
SCHEDULED_EVENT_KINDS: Final[frozenset[str]] = frozenset(
    {
        "action_start",
        "action_checkpoint",
        "action_end",
        "deadline",
        "wakeup",
        "decision_boundary",
        "event",
    }
)

#: 逐 kind 必填 payload 键（§2.5 表"必填 payload 键"列；"必填"语义——缺失即
#: 违例，多余键不违例：``kind="event"`` effects 形态本就携带额外 ``producer``
#: 键，§2.5 注）。``kind="event"`` 不在本表——其契约是 ``trigger_id`` /
#: ``effects`` 恰居其一的互斥规则，由 :func:`_validate_payload` 单独校验。
_REQUIRED_PAYLOAD_KEYS: Final[dict[str, frozenset[str]]] = {
    "action_start": frozenset({"instance_id"}),
    "action_checkpoint": frozenset({"instance_id"}),
    "action_end": frozenset({"instance_id"}),
    "deadline": frozenset({"instance_id"}),
    "wakeup": frozenset({"actor_id"}),
    "decision_boundary": frozenset({"boundary_id", "actor_id"}),
}


def _validate_payload(kind: str, payload: dict[str, JsonValue]) -> None:
    """逐 kind payload 契约校验（§2.5 表）；违例抛 :class:`QueueInvariantError`。

    - 一般 kind：§2.5 表必填键必须全部存在（缺失 → 报错，信息含缺失键集）；
    - ``kind="event"``：``trigger_id`` 与 ``effects`` **恰居其一**（互斥，
      唯一口径）——两者同时存在、或均缺失 → 报错。
    """
    if kind == "event":
        has_trigger = "trigger_id" in payload
        has_effects = "effects" in payload
        if has_trigger == has_effects:
            raise QueueInvariantError(
                "kind='event' payload 要求 trigger_id/effects 恰居其一（互斥），"
                f"实际：trigger_id={has_trigger} effects={has_effects}"
            )
        return
    missing = sorted(_REQUIRED_PAYLOAD_KEYS[kind] - payload.keys())
    if missing:
        raise QueueInvariantError(f"kind={kind!r} payload 缺必填键：{missing}")


def make_scheduled_event(
    kind: str,
    due_tick: int,
    *,
    payload: dict[str, JsonValue] | None = None,
    entry_id: ScheduledEntryId | None = None,
) -> ScheduledEvent:
    """构造队列条目（P1 冻结 ``ScheduledEvent`` 复用，D-P3-04；不新建条目类型）。

    校验顺序（任一违例 → :class:`QueueInvariantError`，可检查不静默）：

    1. ``kind`` ∈ :data:`SCHEDULED_EVENT_KINDS` 封闭词表（§2.5 表唯一定义处）；
    2. ``due_tick >= 0``（tick 非负，与 D-P3-02 单调性同源）；
    3. 逐 kind 必填 payload 键（§2.5 表）；``kind="event"`` 为
       ``trigger_id`` / ``effects`` 恰居其一互斥（唯一口径）；``payload=None``
       视同空 dict；
    4. ``entry_id`` 缺省 ``new_scheduled_entry_id()``（``sch_`` 前缀，
       ``ids.py`` 冻结工厂）。
    """
    if kind not in SCHEDULED_EVENT_KINDS:
        raise QueueInvariantError(
            f"队列条目 kind 词表外：{kind!r}（词表：{sorted(SCHEDULED_EVENT_KINDS)}）"
        )
    if due_tick < 0:
        raise QueueInvariantError(f"队列条目 due_tick 必须 >= 0，实际：{due_tick}")
    data = {} if payload is None else payload
    _validate_payload(kind, data)
    return ScheduledEvent(
        entry_id=entry_id if entry_id is not None else new_scheduled_entry_id(),
        due_tick=due_tick,
        kind=kind,
        payload=data,
    )


def enqueue_scheduled_event(runtime: RuntimeState, event: ScheduledEvent) -> RuntimeState:
    """入队（§3.4 / D-P3-05 写时稳定排序）：追加 + 按 ``due_tick`` 单键稳定重排
    （相等 tick 保持插入相对序），返回新 ``RuntimeState``（self 不变）。

    - ``event.due_tick < runtime.logical_tick`` →
      :class:`QueueInvariantError`（禁止过去调度：时间只能向前，与 D-P3-02
      单调性同源）；``due_tick == logical_tick`` 合法（§2.4 边界情形：同刻
      新入队条目追加至同刻批尾部，稳定 FIFO 自然覆盖，仍在同一刻内处理完）；
    - 队列中已存在相同 ``entry_id`` → :class:`QueueInvariantError`（身份唯一；
      构造点拒绝，KBC-2 同款去重纪律——重复判定针对**当前队列**，条目被
      ``take_due`` 抽走后同一 ``entry_id`` 可再次入队）。
    """
    if event.due_tick < runtime.logical_tick:
        raise QueueInvariantError(
            f"禁止过去调度：due_tick={event.due_tick} < logical_tick={runtime.logical_tick}"
        )
    if any(entry.entry_id == event.entry_id for entry in runtime.scheduler_queue):
        raise QueueInvariantError(f"重复 entry_id 入队：{event.entry_id!r}")
    queue = [*runtime.scheduler_queue, event]
    queue.sort(key=lambda entry: entry.due_tick)
    return rebuild_runtime(runtime, scheduler_queue=queue)


def take_due(runtime: RuntimeState) -> tuple[RuntimeState, list[ScheduledEvent]] | None:
    """抽走最小 ``due_tick`` 的整批（§3.4 / §2.4）：返回 ``(新 RuntimeState,
    同刻批)``；队列空 → ``None``（fast-forward 终点判据，§2.4）。

    批序 = 队列序 = 插入序（稳定 FIFO，D-P3-05；写时稳定排序保证"先入队
    先处理"，调度器永不重排）；批内序与 ``batch[0].due_tick`` 即本刻
    ``t``（§2.4 主循环口径）。``due_tick == t`` 的新入队条目追加同刻批尾部，
    仍在同一刻内处理完（§2.4 边界情形）。
    """
    queue = runtime.scheduler_queue
    if not queue:
        return None
    due = min(entry.due_tick for entry in queue)
    batch = [entry for entry in queue if entry.due_tick == due]
    rest = [entry for entry in queue if entry.due_tick != due]
    return rebuild_runtime(runtime, scheduler_queue=rest), batch
