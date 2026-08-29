"""engine_v2 core 层 Scheduler 门面、TimePolicy 与编排层纯函数（P3-T04b/T05/T06：
§3.10 同文件单 Owner 串行交付）。

依据 ``docs/v2/contracts/P3-scheduler-time-action-design.md``（下称"设计文档"）：

- **§3.8（全量）**：本模块 11 个导出符号（§3.8 的 10 项 + ``start_action`` 经
  D6 裁定落位本模块，设计 §3.6 落点偏离见 E-P3-41）——:class:`TimePolicy` /
  :class:`PauseReason` / :class:`SchedulerOutcome` / :class:`WakeupHook` /
  :class:`WakeupHookRegistry` / :func:`enqueue_actor_wakeup` /
  :func:`scheduler_fingerprint` / :class:`Scheduler`（门面：``fast_forward`` /
  ``step`` / ``submit_proposal`` / ``resume_action`` / ``abort_action``）/
  :class:`SchedulerConfigurationError` / :class:`SchedulerWakeupError` /
  :func:`start_action`；
- **§2.4（主循环伪代码，权威）**：入口首检（D-P3-24，未响应暂停幂等重报——
  纯 (WorldState, RuntimeState, config) 派生、重入零副作用、置于循环前播种
  之前）→ 循环前播种（D-P3-22，幂等去重）→ ``take_due`` 批循环 → 时钟跳变
  （唯一写点 :func:`set_logical_tick`，D-P3-03）→ 逐 kind match 分支（§2.5
  词表）→ 刻后边界求值（T05 已接线：``interrupt.evaluate_boundaries`` +
  INTERRUPTED 迁移 / npc wakeup 双记录 / 玩家 blocking 暂停，Leader 裁定见
  下）→ 暂停/terminal 返回；
  单刻处理中任何 P3 错误 → 返回刻前状态对 + 错误 outcome（D-P3-24④，不崩溃、
  部分提交不可见）；
- **§3.6（``start_action``）**：PROPOSED→VALIDATING→ACTIVE 两跳复合恒 2 条
  迁移记录（D-P3-19）；Leader 裁定本函数归 T04b（``action_lifecycle.py``
  同任务窗口冻结，本模块为落位）；观察出口 = 模块级直调返回元组第 3 位
  （F2-16/E-P3-23④）；
- **§3.9（revalidation 口径）**：``Scheduler._revalidate`` 委托
  ``revalidation.revalidate_proposal``（T07 落位，Leader 裁定 (F) 接线替换）——
  任意 producer 单一实现（G2 移交 3）；``allow_rebase`` 缺省关（调用方
  ``submit_proposal`` 决定何时允许 REBASE，§3.9 ``rebase_proposal`` 注记）；
- **§4 决策**：D-P3-16（错误双轨：7 异常型 + 数据结果型）、D-P3-18
  （SchedulerOutcome 按调用聚合、承载级联管道完整产出）、D-P3-19（start 两跳
  2 记录）、D-P3-20（事务/事件不打戳逻辑时刻）、D-P3-21（条件求值 tick 入参，
  T05 面）、D-P3-22（scheduled 边界循环前播种）、D-P3-23（AuthorityPolicy 必填
  装配、唯一 CascadeExecutor）、D-P3-24（入口首检 + 原子刻错误路径）、
  D-P3-26（``named_triggers`` 必填、点名求值唯一数据来源）、D-P3-27
  （``trigger_registry=None`` 缺省 = 空注册表，级联再求值面为空）；
- **§5.1/§5.2**（Gate fixture 与 S0–S8 时序，行为参照）；
- **勘误**：E-P3-13（D-P3-24 全文）、E-P3-23（触发器点名映射 / 提交参数钉死
  F2-15 / start 迁移观察出口 F2-16）、E-P3-30（Gate 单路化）、E-P3-31
  （D-P3-24③ 重报保证限定 + ⑥ 边缘一次性）、E-P3-34（run()-级 origin
  OriginKind 钉死）、E-P3-39（③ 指纹签名与输入面、⑤ wakeup 缺省、⑥ 门面
  返回类型对齐、⑧ submit_proposal 次序）、E-P3-40（``apply_checkpoint``
  间隔通道 + ``Scheduler.__init__`` 必填 ``origin``）。

Leader 预裁定（T04b，按裁定实现、报告 notes 标注"Leader 裁定"）：

- **(A)** ``Scheduler.__init__`` 必填 ``origin: Provenance``（E-P3-40 已入
  文档签名草图）；内部所有 ``run()`` 提交 ``origin=self._origin``；
- **(B)** 边界类型与刻后求值：T04b 时 ``interrupt.py`` 未交付，``DecisionBoundary``
  等类型用字符串前向注解 + ``if TYPE_CHECKING`` 块（运行时零 import）；D-P3-24
  入口首检完整实现（纯派生、对边界对象仅鸭子式属性读
  ``blocking`` / ``actor_id`` / ``boundary_id``，与 T05 实际
  ``DecisionBoundary`` 兼容）。**T05 已接线**：``interrupt.py`` 交付
  （§3.7 全量），刻后边界求值段（§2.4 "边界求值"块）落位于
  ``_maybe_evaluate_boundaries``（返回 5 元组：new_runtime / paused /
  pause_reason / report / trace 记录）——全部中断经
  ``transition_action(INTERRUPTED)`` 唯一迁移入口（无并行中断函数）、
  ``npc_notices`` 逐对 ``enqueue_actor_wakeup`` 双记录（不受
  ``pause_on_player_boundary`` 辖制）、fired 报告两路（record-only 与正常）
  均经 ``TraceKind.SYSTEM`` 记录留痕；``condition_resolvers`` 缺省落位
  ``BUILTIN_CONDITION_RESOLVERS`` 共享缺省实例（E-P3-39④）。
  **T06 已接线**：``kind="wakeup"`` 分支经 ``_drain_wakeup`` 消费（D-P3-14）——
  payload 仅 ``actor_id``，hook 的 ``reason`` 实参经 ``runtime.actor_wakeups``
  的 ``(actor_id, due_tick)`` 记录查得（F5-02 双记录口径）；无 hook 命中 →
  仅诊断 TraceRecord（SYSTEM）、不崩溃、簿记零影响（E-P3-39⑤）；hook 存在 →
  ``on_wakeup(actor_id, guard(world), LogicalClock.of(runtime), reason)``，抛
  任何异常 → :class:`SchedulerWakeupError`（携带 actor_id）→ 单刻原子错误
  路径；hook 返回提案逐条经 ``submit_proposal`` 全管道（含 ``_revalidate``
  revalidation，不绕过）；条目消费即同步移除该 ``(actor_id, due_tick)`` 记录
  （无论有无 hook 命中，条目消费是唯一移除触发）；同刻多条 wakeup 确定序
  = 队列序（take_due 同刻批序，不重排）。
- **(C)** ``run()`` 提交参数：``causal_root_id`` = 驱动该批的队列条目
  ``entry_id`` 字符串（本刻批首条 entry，F2-15/E-P3-38）；提交后
  ``CascadeResult`` 的 transactions（含 ABORTED，commit 序）/ events /
  trace_records 全部承接进 outcome（D-P3-18）；
- **(D)** kind 分支本任务实现：``action_start``（start_action 两跳 2 迁移，
  submit 路径共用）、``action_checkpoint``（``apply_checkpoint`` 透传
  ``checkpoint_interval=time_policy.checkpoint_interval_ticks`` + 诊断
  TraceRecord 入 ``outcome.trace_records``）、``action_end``（到点且 ACTIVE →
  ``complete_action``，含"若仍 ACTIVE"守卫；完成 effect 经
  ``completion_trigger`` 点名求值后经 P2 管道提交）、``deadline``
  （到点且 ACTIVE → ``fail_action("deadline_missed")``）、``event``
  （``_commit_scheduled``：named_triggers 按 payload ``trigger_id`` 点名求值
  → stub 产出 ProposedEffect 序列经 ``CascadeExecutor.run(initial_proposals=…)``
  提交——空注册表 → 级联再求值面为空，D-P3-27）；``decision_boundary`` 分支
  为时钟停靠点（no payload effect，fired 判定属刻后求值——T05 已接线）、
  ``wakeup``（T06 已接线：``_drain_wakeup`` → WakeupHook 求值 + 提案经
  ``submit_proposal`` 全管道，D-P3-14；见 (B) 尾段）；
- **(E)** 循环前播种（D-P3-22）：``kind="scheduled"`` 边界中 ``due_tick``
  大于当前刻者幂等补入 ``kind="decision_boundary"`` 队列条目
  （``boundary_id`` 去重，条目只是时钟停靠点，无 payload effect）；
- **(F)** ``submit_proposal`` 次序（E-P3-39⑧）：1) registry 查找（未注册 →
  ``UnknownActionError`` → FAILED 轨迹 reason="unknown_action"，不创建
  PROPOSED 记录）；2) ``_revalidate(proposal)``（委托
  ``revalidation.revalidate_proposal``，§3.9 口径）；
  3) ACCEPT → PROPOSED 记录 + pending_proposals + start_action 复合 2 迁移
  （成功时移出 pending，F2-12）；
- **(G)** :func:`scheduler_fingerprint(registry, time_policy, boundaries)`：
  各 Pydantic 模型按 ``model_fields`` 顺序纯 dict 投影 →
  ``json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))``
  → sha256 hex；``named_triggers`` / ``trigger_registry`` 不入指纹
  （E-P3-39③）。

纪律（§0.3 继承 / §8.3 P3 专项）：只 import stdlib + pydantic + 同包
``src.engine_v2.core`` 既有模块；P3 专项黑名单 ``datetime`` / ``time`` /
``random`` / ``asyncio`` 对本模块生效；无 LLM / 网络 / 随机性（uuid 只经
``ids.py`` 工厂——本模块自身不签发 ID，一律经 ``make_scheduled_event`` 等
既有工厂）；全部世界写入经内部唯一 :class:`CascadeExecutor`（D-P3-11① /
D-P3-23），scheduler 自身不产世界 effect（迁移至 COMPLETED 等是簿记、非世界
effect、不经 authority，§5.3 A4）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from src.engine_v2.core.action_lifecycle import (
    IllegalTransitionError,
    LifecycleEvent,
    LifecycleTransition,
    abort_action,
    apply_checkpoint,
    complete_action,
    fail_action,
    resume_action,
    transition_action,
)
from src.engine_v2.core.action_registry import (
    ActionRegistry,
    ActionSpec,
    UnknownActionError,
)
from src.engine_v2.core.actions import (
    ActionLifecycleStatus,
    ActionProposal,
    ActionTiming,
    ActiveAction,
)
from src.engine_v2.core.authority import AuthorityPolicy, ProducerRegistry
from src.engine_v2.core.cascade import (
    CascadeExecutor,
    CascadeResult,
    CascadeTrigger,
    CascadeTriggerRegistry,
)
from src.engine_v2.core.clock import (
    LogicalClock,
    SchedulerError,
    rebuild_runtime,
    set_logical_tick,
)
from src.engine_v2.core.components import ComponentRegistry
from src.engine_v2.core.effects import ProposedEffect
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.event_queue import (
    QueueInvariantError,
    enqueue_scheduled_event,
    make_scheduled_event,
    take_due,
)
from src.engine_v2.core.events import DomainEvent
from src.engine_v2.core.ids import (
    ActionInstanceId,
    EntityId,
    new_trace_record_id,
)
from src.engine_v2.core.interrupt import (
    BUILTIN_CONDITION_RESOLVERS,
    BoundaryReport,
    ConditionResolverRegistry,
    DecisionBoundary,
    evaluate_boundaries,
)
from src.engine_v2.core.provenance import Provenance
from src.engine_v2.core.reducer import guard, write_barrier_installed
from src.engine_v2.core.revalidation import RevalidationDecision, revalidate_proposal
from src.engine_v2.core.revision import RevalidationOutcome
from src.engine_v2.core.state import (
    ActorWakeup,
    RuntimeState,
    ScheduledEvent,
    WorldState,
)
from src.engine_v2.core.trace import TraceKind, TraceRecord
from src.engine_v2.core.transaction import Transaction

if TYPE_CHECKING:  # 仅注解用（GuardedWorldState 为 P2 只读视图类型；本模块运行时对 reducer 仅 import guard/write_barrier_installed 纯函数，§3.2 依赖图）
    from src.engine_v2.core.reducer import GuardedWorldState

__all__ = [
    "TimePolicy",
    "PauseReason",
    "SchedulerOutcome",
    "WakeupHook",
    "WakeupHookRegistry",
    "enqueue_actor_wakeup",
    "scheduler_fingerprint",
    "Scheduler",
    "SchedulerConfigurationError",
    "SchedulerWakeupError",
    "start_action",  # Leader 裁定归 T04b 落位于本模块（设计 §3.6 落点偏离，偏差登记 D6）
]


# —— 错误族（D-P3-16：基类 SchedulerError 宿主在 clock.py 依赖叶，无环）——


class SchedulerConfigurationError(SchedulerError):
    """Scheduler 装配期配置错误（设计文档 §3.8 / D-P3-16 / F2-06）。

    于 ``Scheduler.__init__`` 构造点抛出（可检查不静默）：

    - **R1 未武装断言失败**（D-P3-11② / F2-06 检查次序钉死）：
      ``assert_barrier_armed=True`` 且 ``write_barrier_installed() is False``
      → 本错误，且 ``__init__`` **不构造**内部唯一 ``CascadeExecutor``
      （``CascadeExecutor.__init__`` 自身会幂等武装屏障，"先构造执行器后检查"
      将使检查时刻屏障必已武装、该错误成死代码）；
    - ``named_triggers`` 中重复 ``trigger_id``（映射键冲突 = 配置错误；
      确定性纪律 K7：frozenset 迭代序含对象哈希，同键异触发器时"后者胜"
      跨运行不确定，故构造点拒绝，不静默）。
    """


class SchedulerWakeupError(SchedulerError):
    """WakeupHook 求值错误（设计文档 §3.8 / D-P3-16 / D-P3-14；T06 已接线）。

    hook 在 ``kind="wakeup"`` 条目处理中抛任何异常 → ``_drain_wakeup`` 包装
    为本错误（携带 ``actor_id`` + 原始异常 ``cause``）→ 经单刻原子错误路径
    返回刻前状态对（D-P3-24④，伴随整刻原子回退、部分提交不可见，G3-4 顺序
    一致性不被污染；§6.1 对抗口径）。
    """

    def __init__(self, actor_id: EntityId, *, cause: Exception) -> None:
        self.actor_id = EntityId(actor_id)
        self.cause: Exception = cause
        super().__init__(
            f"WakeupHook 求值错误：actor_id={str(self.actor_id)!r}，"
            f"cause={type(cause).__name__}: {cause}"
        )


# —— §3.8 值类型（D-P3-13 / D-P3-18 / D-P3-14）——


class TimePolicy(ContractModel):
    """TimePolicy 的 P3 落地形态（设计文档 §3.8 / D-P3-13，Spec §50 Spec B）。

    - ``fast_forward_enabled``：事件驱动跳变总开关（缺省 True）；
    - ``checkpoint_interval_ticks``：周期 checkpoint 间隔（None → 无周期
      checkpoint；``start_action`` / ``apply_checkpoint`` 经本值透传间隔，
      E-P3-40 间隔通道，D-P3-13）；
    - ``max_ticks_per_step``：``step()`` 单步跳变上限（开发单步语义）；
    - ``pause_on_player_boundary``：True 缺省（现口径、Gate）：玩家 blocking
      边界命中 → 中断被命中的可中断行动（INTERRUPTED）并返回 paused 待
      resume/abort（D-P3-24）；False（R5/F4-03；R6/F5-03 重裁 record-only，
      E-P3-36）：玩家 blocking 边界命中仍 fired（fired 记录 + trace 留痕）
      但**不中断**可中断行动、不返回暂停、继续推进至本次调用终点；D-P3-24
      入口重报规则不生效（以本标志为前置）；NPC 边界中断/wakeup 不受本标志
      辖制（D-P3-10/D-P3-25 口径不变）。
    """

    fast_forward_enabled: bool = True
    checkpoint_interval_ticks: int | None = Field(default=None, ge=1)
    max_ticks_per_step: int | None = Field(default=None, ge=1)
    pause_on_player_boundary: bool = True


class PauseReason(ContractModel):
    """暂停/终点原因（设计文档 §3.8）。

    ``kind`` 词表：``"decision_boundary"``（玩家 blocking 边界命中暂停）/
    ``"bounded"``（``max_tick`` 边界或 ``step()`` 强制暂停）/ ``"terminal"``
    （队列耗尽确定性终点——该情形 ``paused`` 为 False，本记录仅作终点刻
    水位标记，§5.3 A5 口径）。
    """

    kind: str
    boundary_id: str | None = None
    tick: int


class SchedulerOutcome(ContractModel):
    """一次 fast_forward/step 的结构化结果（设计文档 §3.8 / D-P3-18）。

    按调用聚合：作用域 = 本次调用（从本次 fast_forward/step 开始至其返回，
    与 §5.3 A5 ``transactions=[txn_2]`` 口径一致），不累计历次调用；承载
    级联管道完整产出（``CascadeResult`` 对应面，cascade.py:678-702）。调度器
    **不存储**事件（K1：事件不是世界状态组成部分）——outcome 是调用观察值，
    不落 WorldState/RuntimeState。

    原子刻错误路径（F2-03/D-P3-24④）：单刻处理中任何 P3 错误 → 返回刻前
    状态对 + 本 outcome（``paused=False``、``pause_reason=None``、
    ``ticks_processed=<刻前 logical_tick>``、``transactions``/``events``/
    ``trace_records``/``transitions`` 全空、``errors`` 非空诊断串）——不崩溃、
    部分提交不可见（不可变值 = 天然回滚）。
    """

    paused: bool
    pause_reason: PauseReason | None = None
    ticks_processed: int  # 本次调用达到的 tick 水位（= 结果 RuntimeState.logical_tick）
    transactions: tuple[Transaction, ...] = ()  # 完整对象、含 ABORTED、commit 序
    events: tuple[DomainEvent, ...] = ()  # 本次调用全部发射事件（1:1 于已提交 effect）
    trace_records: tuple[TraceRecord, ...] = ()  # 本次调用全部决策/诊断记录（追加序）
    transitions: tuple[LifecycleTransition, ...] = ()
    # 本次调用产出的迁移记录（start_action 的 2 条复合记录在 submit_proposal
    # 侧产出，不属于任何 fast_forward 调用的 outcome，D-P3-18/19）
    errors: tuple[str, ...] = ()


class WakeupHook(Protocol):
    """Actor 唤醒 hook 协议（设计文档 §3.8 / D-P3-14；Spec §50 BehaviorPolicy
    的唤醒侧接缝）。

    同步纯函数：只读 guard 视图（``GuardedWorldState``），返回新提案（不写
    世界、不直接调度）；确定性顺序由调用方（队列序）保证，hook 本体无内部
    时钟/随机。hook 实例须携带 ``actor_id`` 属性（注册键——
    :meth:`WakeupHookRegistry.register` 读取，鸭子式契约）。接线（T06）：
    ``_drain_wakeup`` 在 ``kind="wakeup"`` 条目消费时以
    ``(actor_id, view=guard(world), clock=LogicalClock.of(runtime),
    reason=actor_wakeups 记录 reason)`` 调用，抛错包装
    :class:`SchedulerWakeupError`（D-P3-14）。
    """

    def on_wakeup(
        self,
        actor_id: EntityId,
        view: "GuardedWorldState",  # reducer.guard 产物（TYPE_CHECKING 导入）
        clock: LogicalClock,
        reason: str | None,
    ) -> Sequence[ActionProposal]: ...


class WakeupHookRegistry:
    """WakeupHook 注册表（设计文档 §3.8 / D-P3-14；普通类，配置非状态）。

    - :meth:`register`：按 hook 实例的 ``actor_id`` 属性注册（缺失/非字符串
      → :class:`SchedulerConfigurationError`，配置错误可检查不静默）；同 actor
      重复注册 → 本错误（确定性配置面，不静默覆盖）；
    - :meth:`hook_for`：按 actor 查找；无 → ``None``（wakeup 条目命中时无
      hook 可调 → 仅输出诊断（TraceRecord，SYSTEM）、不崩溃、不影响簿记，
      E-P3-39⑤——诊断点在 ``_drain_wakeup``，T06 已接线）。
    """

    __slots__ = ("_hooks",)

    def __init__(self) -> None:
        self._hooks: dict[EntityId, WakeupHook] = {}

    def register(self, hook: WakeupHook) -> None:
        """注册 hook（actor_id 鸭子式契约 + 同 actor 唯一，见类 docstring）。"""
        actor_id = getattr(hook, "actor_id", None)
        if not isinstance(actor_id, str) or actor_id == "":
            raise SchedulerConfigurationError(
                f"WakeupHookRegistry.register 需要携带 actor_id 字符串属性的 hook，"
                f"得到 {type(hook).__name__}（actor_id={actor_id!r}）"
            )
        if EntityId(actor_id) in self._hooks:
            raise SchedulerConfigurationError(
                f"WakeupHookRegistry.register 同 actor 重复注册：{actor_id!r}"
            )
        self._hooks[EntityId(actor_id)] = hook

    def hook_for(self, actor_id: EntityId) -> WakeupHook | None:
        """按 actor 查找 hook；未注册 → ``None``。"""
        return self._hooks.get(actor_id)


def enqueue_actor_wakeup(
    runtime: RuntimeState,
    actor_id: EntityId,
    due_tick: int,
    reason: str | None = None,
) -> RuntimeState:
    """Actor 唤醒双记录写入（设计文档 §3.8 / §2.5 尾注双记录口径）。

    写 ``actor_wakeups``（稳定序：``due_tick`` 单键，稳定排序保持同刻插入
    相对序）+ 同步入队 ``kind="wakeup"`` 条目（payload 仅 ``{"actor_id":
    …}``）；两条记录 ``(actor_id, due_tick)`` 一致，``reason`` 仅存
    ``ActorWakeup`` 记录、不入 payload（``ActorWakeup.reason``，state.py:166）。

    - ``due_tick < runtime.logical_tick`` → :class:`QueueInvariantError`
      （过去调度禁止，经 ``enqueue_scheduled_event``，D-P3-05）；
    - 纯函数：返回新 ``RuntimeState``，self 不变（经 ``rebuild_runtime`` /
      ``enqueue_scheduled_event`` 既有写点）。
    """
    wakeup = ActorWakeup(actor_id=actor_id, due_tick=due_tick, reason=reason)
    wakeups = [*runtime.actor_wakeups, wakeup]
    wakeups.sort(key=lambda item: item.due_tick)
    entry = make_scheduled_event("wakeup", due_tick, payload={"actor_id": str(actor_id)})
    new_runtime = rebuild_runtime(runtime, actor_wakeups=wakeups)
    return enqueue_scheduled_event(new_runtime, entry)


# —— 确定性指纹（D-P3-15 / E-P3-39③）——


def _fingerprint_project(value: object) -> object:
    """递归纯 dict 投影（E-P3-39③ 规范化 JSON 的前置投影）。

    - Pydantic 模型：按 ``model_fields`` 声明顺序投影为 dict（嵌套递归；
      ``DecisionBoundary`` 实际对象经此路，interrupt.py T05 交付）；
    - 其他对象：按 ``vars()`` 投影（测试侧鸭子对象经此路）；
    - 映射：按键投影（值递归）；列表/元组：逐项投影（序保持）；
    - JSON 标量（None/str/int/float/bool）：原样；其余（不可序列化兜底）：
      ``str()``（确定性）。
    """
    if isinstance(value, BaseModel):
        return {
            name: _fingerprint_project(getattr(value, name))
            for name in type(value).model_fields
        }
    if isinstance(value, Mapping):
        return {str(key): _fingerprint_project(value[key]) for key in value.keys()}
    if isinstance(value, (list, tuple)):
        return [_fingerprint_project(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "__dict__"):
        return {key: _fingerprint_project(val) for key, val in vars(value).items()}
    return str(value)


def scheduler_fingerprint(
    registry: ActionRegistry,
    time_policy: TimePolicy,
    boundaries: tuple[DecisionBoundary, ...],
) -> str:
    """调度器配置确定性指纹（设计文档 §3.8 / D-P3-15；E-P3-39③ 签名与输入面）。

    输入面钉死 = ``registry`` + ``time_policy`` + ``boundaries`` 三项；各
    Pydantic 模型按 ``model_fields`` 顺序做纯 dict 投影 →
    ``json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))``
    → sha256 hex（唯一、确定性，K7）——回放时校验 config 同构，不一致 →
    回放拒绝（不静默）。

    排除面（已披露设计选择，E-P3-39③）：``named_triggers`` /
    ``trigger_registry``（callable/SyncTrigger 闭包，非可序列化）不入指纹
    ——Gate fixture 触发器为确定性纯函数，G3-4 判据在测试层机械可验证。
    """
    payload = {
        "registry": _fingerprint_project(registry),
        "time_policy": _fingerprint_project(time_policy),
        "boundaries": [_fingerprint_project(b) for b in boundaries],
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# —— start_action（§3.6；Leader 裁定归 T04b 落位于本模块）——


def _resolve_duration(spec: ActionSpec, timing: ActionTiming) -> int | None:
    """时长解析单一来源（§3.5 / D-P3-01 子 tick 钳制规则）：委托
    :meth:`ActionRegistry.resolve_duration`（规范实现，不重复公式）。

    §3.6 钉死签名不携带 registry——经单键临时 registry 委托（``specs`` 键 =
    ``spec.action_id``，键一致性天然成立）；数据模型构造开销可忽略，纯度不变。
    """
    return ActionRegistry(specs={spec.action_id: spec}).resolve_duration(spec, timing)


def start_action(
    world: WorldState,
    runtime: RuntimeState,
    proposal: ActionProposal,
    spec: ActionSpec,
    *,
    at_tick: int,
    checkpoint_interval: int | None,
) -> tuple[WorldState, RuntimeState, tuple[LifecycleTransition, ...]]:
    """PROPOSED→VALIDATING→ACTIVE 两跳复合（设计文档 §3.6 / D-P3-19）。

    按迁移表查两次，落 **2 条** :class:`LifecycleTransition` 记录
    （``VALIDATION_ACCEPTED@at_tick`` + ``SCHEDULED@at_tick``，顺序 = 迁移序，
    返回元组第 3 位——F2-16/E-P3-23④ 观察出口：模块级直调返回可断言 2 条；
    不入任何 ``fast_forward`` 调用的 outcome，D-P3-18）；写 ``ActiveAction``
    记录（``start_tick=at_tick``、``expected_end_tick=at_tick+duration``
    （可空）、``interruptible=spec.interruptible``、
    ``base_world_revision=proposal.base_world_revision``，经第二跳
    ``updates`` 携带）+ 入队 checkpoint/end/deadline 条目（§2.5 表）：

    - ``checkpoint_interval`` 非 None → ``action_checkpoint`` @
      ``at_tick + checkpoint_interval``（``next_checkpoint_tick`` 镜像同推进）；
    - ``duration`` 非 None（``resolve_duration``，§3.5）→ ``action_end`` @
      ``at_tick + duration``；
    - ``proposal.timing.deadline_tick`` 非 None → ``deadline`` @ 该刻。

    开始时刻**无世界 effect**（位置不动，不得 2）——本函数不触碰
    ``world``（输入原样返回、同一对象）、不推进 ``world_revision``（P1 D-5）。

    表外（实例不存在 / 非 PROPOSED 源状态——start 条目只可能由
    ``submit_proposal`` ACCEPT 路径与 PROPOSED 记录成对产生）→
    :class:`IllegalTransitionError`（D-P3-16 ①，经
    :func:`transition_action` 唯一迁移入口）。
    """
    instance_id = proposal.proposal_id
    duration = _resolve_duration(spec, proposal.timing)
    expected_end_tick = at_tick + duration if duration is not None else None
    next_checkpoint_tick = (
        at_tick + checkpoint_interval if checkpoint_interval is not None else None
    )
    # 第一跳：PROPOSED → VALIDATING（VALIDATION_ACCEPTED，D-P3-19）
    new_runtime, transition_1 = transition_action(
        runtime, instance_id, LifecycleEvent.VALIDATION_ACCEPTED, at_tick=at_tick
    )
    # 第二跳：VALIDATING → ACTIVE（SCHEDULED）：写开始字段（§3.6 逐字）
    updates: dict[str, Any] = {
        "start_tick": at_tick,
        "expected_end_tick": expected_end_tick,
        "progress": 0.0 if duration is not None else None,
        "interruptible": spec.interruptible,
        "base_world_revision": proposal.base_world_revision,
        "next_checkpoint_tick": next_checkpoint_tick,
    }
    new_runtime, transition_2 = transition_action(
        new_runtime, instance_id, LifecycleEvent.SCHEDULED, at_tick=at_tick, updates=updates
    )
    # 入队 checkpoint/end/deadline 条目（§2.5 表；entry_id 经 make_scheduled_event
    # 缺省 new_scheduled_entry_id() 工厂签发，sch_ 前缀）
    if checkpoint_interval is not None:
        entry = make_scheduled_event(
            "action_checkpoint",
            at_tick + checkpoint_interval,
            payload={"instance_id": str(instance_id)},
        )
        new_runtime = enqueue_scheduled_event(new_runtime, entry)
    if expected_end_tick is not None:
        entry = make_scheduled_event(
            "action_end", expected_end_tick, payload={"instance_id": str(instance_id)}
        )
        new_runtime = enqueue_scheduled_event(new_runtime, entry)
    deadline_tick = proposal.timing.deadline_tick
    if deadline_tick is not None:
        entry = make_scheduled_event(
            "deadline", deadline_tick, payload={"instance_id": str(instance_id)}
        )
        new_runtime = enqueue_scheduled_event(new_runtime, entry)
    return world, new_runtime, (transition_1, transition_2)


# —— 门面（K7：不是真相——编排层，全部状态在 (WorldState, RuntimeState)）——


class Scheduler:
    """调度器门面（设计文档 §3.8；D-P3-11 / D-P3-23 / E-P3-40）。

    **不是真相**（K7）：门面只持配置（registry / 策略 / 边界 / 触发器映射）
    与内部唯一 :class:`CascadeExecutor`——全部世界写入经它（D-P3-11①）；
    全部调度事实显式存于 (WorldState, RuntimeState)（Spec §23.3 "Scheduler
    state 必须显式"）。

    装配（R1 落地 G2 移交 1 + 权威/执行器装配 D-P3-23）：

    - **检查次序钉死（F2-06）**：``assert_barrier_armed=True`` 时，
      ``write_barrier_installed()`` 检查为 ``__init__`` **第一步**，先于内部
      唯一 ``CascadeExecutor`` 构造——未武装 → 抛
      :class:`SchedulerConfigurationError`（**不构造执行器**）；
    - 随后内部构造**唯一** ``CascadeExecutor``（policy=authority_policy、
      triggers=trigger_registry（None 缺省 = 空注册表，cascade.py:852，
      R5/D-P3-27）、component_registry/producer_registry 透传）；
      AuthorityPolicy closed-by-default（D-P2-09）——装配方必须显式授予实际
      产 effect 的 producer 写域（Gate fixture 见 §5.1）；
    - **触发器名称解析（F2-13 / D-P3-26）**：scheduler 自持
      ``trigger_id → trigger`` 映射，由**必填**构造参数
      ``named_triggers: frozenset[tuple[str, CascadeTrigger]]`` 建立
      （不可变、确定性、零私有访问——``CascadeTriggerRegistry`` 公开 API 无
      按名单个查询，不得以私有字段访问补位）；``kind="event"`` 的
      ``trigger_id`` payload 与 ``completion_trigger`` 到点时经该映射点名求值。

    run()-级 origin（E-P3-34/F5-01 / E-P3-40，Leader 裁定 (A)）：必填构造
    参数 ``origin: Provenance``（provenance.py:71-72 双必填构造；Gate fixture
    = ``Provenance(producer_id=origin_scenario, origin=OriginKind.SCENARIO)``）
    ——Scheduler 内部全部 ``CascadeExecutor.run`` 提交统一用它；``causal_root_id``
    = 驱动该批的队列条目 ``entry_id`` 字符串（本刻批首条 entry，F2-15/E-P3-38）。

    刻后边界求值（§2.4）已接线（T05，Leader 裁定见模块头 (B)）：
    ``_maybe_evaluate_boundaries`` 于每刻提交后以当刻新 ``guard()`` 视图求值
    （G2 移交 2）——INTERRUPTED 迁移经 :func:`transition_action` 唯一入口、
    npc wakeup 双记录、玩家 blocking 暂停（受 ``pause_on_player_boundary``
    门控）。``kind="wakeup"`` 已接线（T06，D-P3-14）：``_drain_wakeup`` 消费
    条目——无 hook → 诊断 TraceRecord（SYSTEM）；hook → ``on_wakeup`` 求值 +
    提案经 ``submit_proposal`` 全管道；hook 异常 →
    :class:`SchedulerWakeupError` → 单刻原子错误路径；actor_wakeups 记录随
    条目消费同步移除（F5-02）。
    """

    __slots__ = (
        "_registry",
        "_origin",
        "_time_policy",
        "_boundaries",
        "_condition_resolvers",
        "_wakeup_hooks",
        "_trigger_registry",
        "_named_triggers",
        "_player_actor_ids",
        "_executor",
    )

    def __init__(
        self,
        registry: ActionRegistry,
        *,
        authority_policy: AuthorityPolicy,
        origin: Provenance,
        time_policy: TimePolicy = TimePolicy(),
        boundaries: Sequence[DecisionBoundary] = (),
        condition_resolvers: ConditionResolverRegistry | None = None,
        wakeup_hooks: WakeupHookRegistry | None = None,
        trigger_registry: CascadeTriggerRegistry | None = None,
        named_triggers: frozenset[tuple[str, CascadeTrigger]],
        component_registry: ComponentRegistry | None = None,
        producer_registry: ProducerRegistry | None = None,
        player_actor_ids: frozenset[EntityId] = frozenset(),
        assert_barrier_armed: bool = True,
    ) -> None:
        """装配（检查次序 F2-06 钉死；参数语义见类 docstring 与 §3.8 签名草图）。

        ``condition_resolvers`` 缺省口径（E-P3-39④，T05 落位）：缺省取
        ``BUILTIN_CONDITION_RESOLVERS`` 共享缺省实例（interrupt.py，内置 4
        kind 纯实现）；对该共享缺省实例调用 ``register`` 属配置错误
        （``register`` 直接拒绝）——自定义 kind 请自建
        ``ConditionResolverRegistry`` 传入。
        """
        # 第一步（F2-06，先于执行器构造）：R1 写屏障武装断言（D-P3-11②）
        if assert_barrier_armed and not write_barrier_installed():
            raise SchedulerConfigurationError(
                "Scheduler 装配 R1 断言失败：写屏障未武装（write_barrier_installed() "
                "is False）——__init__ 第一步检查先于内部唯一 CascadeExecutor 构造"
                "（F2-06；先构造将使检查时刻屏障必已武装、该错误成死代码）"
            )
        # 触发器点名映射（D-P3-26：必填、不可变、确定性、零私有访问）
        pairs = sorted(named_triggers, key=lambda pair: pair[0])
        named: dict[str, CascadeTrigger] = {}
        for trigger_id, trigger in pairs:
            if trigger_id in named:
                raise SchedulerConfigurationError(
                    f"named_triggers 重复 trigger_id：{trigger_id!r}"
                    "（映射键冲突 = 配置错误；确定性纪律 K7，构造点拒绝）"
                )
            named[trigger_id] = trigger
        # 内部唯一 CascadeExecutor（D-P3-23；构造期幂等武装屏障，cascade.py:810）
        self._executor = CascadeExecutor(
            policy=authority_policy,
            component_registry=component_registry,
            producer_registry=producer_registry,
            triggers=trigger_registry,
        )
        self._registry = registry
        self._origin = origin
        self._time_policy = time_policy
        self._boundaries: tuple[DecisionBoundary, ...] = tuple(boundaries)
        self._condition_resolvers: ConditionResolverRegistry = (
            condition_resolvers
            if condition_resolvers is not None
            else BUILTIN_CONDITION_RESOLVERS
        )
        self._wakeup_hooks = wakeup_hooks if wakeup_hooks is not None else WakeupHookRegistry()
        self._trigger_registry = trigger_registry
        self._named_triggers = named
        self._player_actor_ids = frozenset(player_actor_ids)

    # —— D-P3-24 入口首检（纯派生，置于循环前播种之前，重入零副作用）——

    def _unanswered_pause(self, runtime: RuntimeState) -> PauseReason | None:
        """未响应暂停幂等重报判据（D-P3-24①；E-P3-13；E-P3-31③/⑥）。

        纯 (RuntimeState, self._boundaries, self._player_actor_ids,
        TimePolicy) 派生（active_actions 状态 + boundaries 注册 +
        player_actor_ids），不引入任何新持久状态：

        - 前置：``TimePolicy.pause_on_player_boundary=True``（False 时规则不
          生效——R5/F4-03；R6/F5-03 重裁 record-only，E-P3-36）；
        - 条件：∃ a ∈ active_actions：``a.status == INTERRUPTED`` 且
          ``a.actor_id ∈ player_actor_ids``，且 ∃ b ∈ boundaries（注册序）：
          ``b.blocking`` 且 ``b.actor_id == a.actor_id``；
        - 命中 → 返回**按注册序首个命中边界**的暂停（boundary_id 重新推导，
          多边界命中仍唯一）；resume/abort（status 离开 INTERRUPTED）后规则
          自动失效（D-P3-24③，重报保证限定于该行动仍处 INTERRUPTED 期间）。

        边界对象按鸭子式属性读（``blocking`` / ``actor_id`` /
        ``boundary_id``）——与 T05 交付的 ``DecisionBoundary``（interrupt.py）
        及测试侧鸭子替身双向兼容。
        """
        if not self._time_policy.pause_on_player_boundary:
            return None
        interrupted_players = {
            action.actor_id
            for action in runtime.active_actions.values()
            if action.status is ActionLifecycleStatus.INTERRUPTED
            and action.actor_id in self._player_actor_ids
        }
        if not interrupted_players:
            return None
        for boundary in self._boundaries:
            if getattr(boundary, "blocking", False) and getattr(
                boundary, "actor_id"
            ) in interrupted_players:
                return PauseReason(
                    kind="decision_boundary",
                    boundary_id=str(getattr(boundary, "boundary_id", "")),
                    tick=runtime.logical_tick,
                )
        return None

    # —— D-P3-22 循环前播种（幂等）——

    def _seed_boundary_entries(self, runtime: RuntimeState) -> RuntimeState:
        """scheduled 边界的确定性入队（D-P3-22；Leader 裁定 (E)）。

        对 ``kind=="scheduled"`` 且 ``due_tick`` 大于当前刻的边界，补入一条
        ``kind="decision_boundary"`` 队列条目（payload
        ``{"boundary_id", "actor_id"}``，§2.5 表）——条目只是时钟停靠点（无
        payload effect，match 分支 no-op）；按 ``boundary_id`` 去重（查队列中
        既有条目，已存在即跳过），重复调用幂等不重复补入；``entry_id`` 经
        ``make_scheduled_event`` 缺省 ``new_scheduled_entry_id()`` 工厂签发。
        边界是否 fired 仍由刻后求值判定（T05 已接线：
        ``_maybe_evaluate_boundaries``）——机制层与语义层分离。
        """
        existing: set[str] = {
            str(entry.payload["boundary_id"])
            for entry in runtime.scheduler_queue
            if entry.kind == "decision_boundary" and "boundary_id" in entry.payload
        }
        for boundary in self._boundaries:
            if getattr(boundary, "kind", None) != "scheduled":
                continue
            due_tick = getattr(boundary, "due_tick", None)
            if due_tick is None or due_tick <= runtime.logical_tick:
                continue
            boundary_id = str(getattr(boundary, "boundary_id", ""))
            if not boundary_id or boundary_id in existing:
                continue
            entry = make_scheduled_event(
                "decision_boundary",
                due_tick,
                payload={
                    "boundary_id": boundary_id,
                    "actor_id": str(getattr(boundary, "actor_id", "")),
                },
            )
            runtime = enqueue_scheduled_event(runtime, entry)
            existing.add(boundary_id)
        return runtime

    # —— 刻后边界求值（T05 接线，Leader 裁定：5 元组返回、不扰 except 结构）——

    def _maybe_evaluate_boundaries(
        self,
        world: WorldState,
        runtime: RuntimeState,
        *,
        tick: int,
        tick_events: Sequence[DomainEvent],
        transitions: list[LifecycleTransition],
        skip_boundary_ids: frozenset[str] = frozenset(),
    ) -> tuple[
        RuntimeState,
        bool,
        PauseReason | None,
        BoundaryReport,
        TraceRecord | None,
    ]:
        """每刻提交后的边界求值与处置（§2.4 刻后求值块，顺序固定，D-P3-09/10）。

        次序钉死（伪代码 §2.4 L174-194 逐行对应）：

        1. ``view = guard(world)``——每刻提交后**重新** guard（G2 移交 2；
           视图为 guard() 时刻深冻结快照、零权威引用泄漏）；
        2. ``report = evaluate_boundaries(...)``——注册序求值（interrupt.py，
           纯函数、不迁移不入队）；``registry`` 缺省 BUILTIN（E-P3-39④）、
           ``tick`` 显式传当前刻（D-P3-21）；``skip_boundary_ids`` 为同一
           逻辑刻内**已 fired** 的边界 id（活络守卫，见下）；
        3. fired 逐对处置：玩家 blocking 命中且
           ``pause_on_player_boundary=False`` → continue（record-only，
           E-P3-36：fired 记录 + trace 照常、不中断）；否则对 action_ids 中
           **当前** ``status==ACTIVE`` 且 ``interruptible`` 者
           ``transition_action(INTERRUPTED, at_tick=tick,
           updates={'base_world_revision': world.world_revision})``——唯一
           迁移入口（Leader 裁定：无并行中断函数）、re-anchor 至当前世界
           revision（§2.4 中断分支 / D-P3-08）、边界 ``reason`` 原样透传、
           迁移记录 append 进 ``transitions``（outcome 按调用聚合，D-P3-18；
           §5.2 S8 断言 transitions=[S7] 一条）；同刻多边界命中同一实例时
           前序迁移已离开 ACTIVE → 后序防御性复查跳过（确定性、不重入）；
        4. npc_notices 逐对 ``enqueue_actor_wakeup(due_tick=tick,
           reason=boundary_id)``——双记录口径（§2.5 尾注：payload 仅
           actor_id、reason 仅存 ActorWakeup 记录）；**不受**
           ``pause_on_player_boundary`` 辖制（D-P3-10 选 B）；
        5. fired 或 npc_notices 非空 → ``TraceKind.SYSTEM`` 记录（F2-12
           系统事件模式：``record_id`` 经 ``new_trace_record_id()`` 工厂、
           ``world_revision`` / ``logical_tick`` 权威序坐标、payload 承载
           fired 报告）——record-only 与正常两路均留痕（Leader 裁定 D；
           D-P3-24⑥ 一次性暂停的"已送达"留痕同口径）；两者皆空 → ``None``
           （无噪声记录）；
        6. 暂停判定：``report.player_blocking 且 pause_on_player_boundary``
           → ``paused=True`` + ``pause_reason=PauseReason(kind=
           "decision_boundary", boundary_id=<注册序首个玩家 blocking 命中>,
           tick=tick)``（D-P3-10）；否则 False + None。

        返回 5 元组 ``(new_runtime, paused, pause_reason, report, trace)``
        （Leader 裁定）：``report`` 供调用方观察（fired 判定纯派生、无持久
        状态）；本方法不返回 outcome、不触碰 ``world``、不推进时钟；错误
        （含 :class:`UnknownConditionError`、表外迁移
        :class:`IllegalTransitionError`）向上抛——由调用方 try 内的原子刻
        ``except SchedulerError`` 承接（D-P3-24④：刻前状态对 + 错误
        outcome，不崩溃、部分提交不可见）。

        **活络守卫（同刻 fired 去重）**：``skip_boundary_ids`` 内的边界本刻
        已求值过（已 fired）→ 本次整体跳过。依据：§2.4 边界情形注——同刻
        新入队条目（本方法 npc_notices 路径的 wakeup 即其一）"追加至同刻批
        尾部、仍在同一 ``t`` 内处理完"，主循环因此可能于同一逻辑刻重入本
        方法；若同一边界于同刻二次 fired，将再入队一个 ``due_tick == t``
        的 wakeup → 无限再生（scheduled 边界 ``due_tick <= tick`` 恒参评、
        状态型 condition 恒真时尤甚），§2.4 "队列耗尽终点" 不可达。守卫仅
        限"同刻"（跨刻重评不受辖制——条件可能因提交而变），只跳过已
        fired 者（本刻未命中者照常重评，T06 hook 同刻提交后新命中仍须
        可见），注册序稳定性与 fired 内容不受影响。
        """
        boundaries = [
            boundary
            for boundary in self._boundaries
            if boundary.boundary_id not in skip_boundary_ids
        ]
        if not boundaries:
            return runtime, False, None, BoundaryReport(tick=tick, fired=[]), None
        view = guard(world)  # 每刻提交后重新 guard（G2 移交 2）
        report = evaluate_boundaries(
            view,
            runtime,
            tick=tick,
            events=tick_events,
            boundaries=boundaries,
            registry=self._condition_resolvers,
            player_actor_ids=self._player_actor_ids,
        )
        boundaries_by_id: dict[str, DecisionBoundary] = {
            boundary.boundary_id: boundary for boundary in boundaries
        }
        new_runtime = runtime
        # 3. fired 逐对处置（§2.4 中断分支；record-only 门控 E-P3-36）
        record_only = not self._time_policy.pause_on_player_boundary
        for boundary_id, action_ids in report.fired:
            boundary = boundaries_by_id[boundary_id]
            player_hit = boundary.blocking and (
                boundary.actor_id in self._player_actor_ids
            )
            if player_hit and record_only:
                continue  # record-only（E-P3-36）：不中断可中断行动
            for instance_id in action_ids:
                action = new_runtime.active_actions.get(instance_id)
                if (
                    action is None
                    or action.status is not ActionLifecycleStatus.ACTIVE
                    or not action.interruptible
                ):
                    # 防御性复查：同刻前序边界可能已迁移该实例（离开 ACTIVE）
                    continue
                new_runtime, transition = transition_action(
                    new_runtime,
                    instance_id,
                    LifecycleEvent.INTERRUPTED,
                    at_tick=tick,
                    reason=boundary.reason,
                    updates={"base_world_revision": world.world_revision},
                )
                transitions.append(transition)
        # 4. npc_notices 逐对 wakeup 双记录（不受标志辖制）
        for boundary_id, actor_id in report.npc_notices:
            new_runtime = enqueue_actor_wakeup(
                new_runtime, actor_id, due_tick=tick, reason=boundary_id
            )
        # 5. fired 报告留痕（两路均记录，F2-12 / D-P3-24⑥）
        trace: TraceRecord | None = None
        if report.fired or report.npc_notices:
            trace = TraceRecord(
                record_id=new_trace_record_id(),
                kind=TraceKind.SYSTEM,
                world_revision=world.world_revision,
                logical_tick=tick,
                payload={
                    "diagnostic": "decision_boundary_fired",
                    "fired": [
                        [bid, [str(iid) for iid in instance_ids]]
                        for bid, instance_ids in report.fired
                    ],
                    "player_blocking": report.player_blocking,
                    "npc_notices": [
                        [bid, str(actor)] for bid, actor in report.npc_notices
                    ],
                },
            )
        # 6. 暂停判定（注册序首个玩家 blocking 命中，D-P3-10）
        paused = report.player_blocking and (
            self._time_policy.pause_on_player_boundary
        )
        pause_reason: PauseReason | None = None
        if paused:
            for boundary_id, _instance_ids in report.fired:
                boundary = boundaries_by_id[boundary_id]
                if boundary.blocking and boundary.actor_id in self._player_actor_ids:
                    pause_reason = PauseReason(
                        kind="decision_boundary",
                        boundary_id=boundary_id,
                        tick=tick,
                    )
                    break
        return new_runtime, paused, pause_reason, report, trace

    # —— 提交管道（Leader 裁定 (C)：提交参数与聚合承接）——

    def _run_pipeline(
        self,
        world: WorldState,
        effects: Sequence[ProposedEffect],
        batch: list[ScheduledEvent],
    ) -> tuple[WorldState, CascadeResult]:
        """经内部唯一 CascadeExecutor 提交（D-P3-11①；F2-15/E-P3-38 提交参数钉死）。

        ``causal_root_id`` = 驱动该批的队列条目 ``entry_id`` 字符串（本刻批首
        条 entry——entry_id 覆盖全部条目 kind，kind=event 无 action 实例可指，
        E-P3-38 偏离披露）；``origin`` = ``self._origin``（E-P3-40/F5-01，
        Leader 裁定 (A)）。经管道提交的事务/事件 ``logical_tick`` 恒 None
        （P2 不拥有时钟，D-P2-18/D-P3-20 归属口径）。
        """
        result = self._executor.run(
            effects,
            world,
            causal_root_id=str(batch[0].entry_id),
            origin=self._origin,
        )
        return result.final_state, result

    def _commit_into_outcome(
        self,
        world: WorldState,
        effects: Sequence[ProposedEffect],
        batch: list[ScheduledEvent],
        txs: list[Transaction],
        events: list[DomainEvent],
        traces: list[TraceRecord],
    ) -> WorldState:
        """提交并把 CascadeResult 全部承接进按调用聚合的 outcome 列表（D-P3-18）。

        transactions（**含 ABORTED**，commit 序）/ events / trace_records
        逐字承接（追加序）；空 effect 批不提交（零回合 = 零事务）。
        """
        if not effects:
            return world
        world, result = self._run_pipeline(world, effects, batch)
        txs.extend(result.transactions)
        events.extend(result.events)
        traces.extend(result.trace_records)
        return world

    def _evaluate_named_trigger(
        self,
        trigger_id: str,
        world: WorldState,
        tick_events: Sequence[DomainEvent],
    ) -> list[ProposedEffect]:
        """点名求值（D-P3-26）：经 ``named_triggers`` 映射按名求值单一触发器。

        求值入参：本刻已提交事件流（批内序，确定性）+ 当前世界 guard 视图
        （G2 移交 2：每刻提交后重新 guard）+ depth 0（根级求值）。映射未命中
        → :class:`QueueInvariantError`（可检查不静默；经原子刻错误路径返回，
        §2.4 论证 5 / F2-03 / D-P3-26 空集口径）。
        """
        trigger = self._named_triggers.get(trigger_id)
        if trigger is None:
            raise QueueInvariantError(
                f"trigger_id 不可解析（不在 named_triggers 点名映射中）：{trigger_id!r}"
                "（D-P3-26：named_triggers 为点名求值唯一数据来源）"
            )
        view = guard(world)
        return list(trigger.evaluate(tuple(tick_events), view, 0))

    # —— kind 分支处理（§2.4 match；§2.5 词表）——

    @staticmethod
    def _payload_instance_id(entry: ScheduledEvent) -> ActionInstanceId:
        """逐 kind payload 契约（§2.5 表）：``instance_id`` 必填且为字符串。"""
        raw = entry.payload.get("instance_id")
        if not isinstance(raw, str):
            raise QueueInvariantError(
                f"kind={entry.kind!r} payload 缺必填键 instance_id 或非字符串：{raw!r}"
            )
        return ActionInstanceId(raw)

    def _handle_action_start(
        self,
        world: WorldState,
        runtime: RuntimeState,
        entry: ScheduledEvent,
        at_tick: int,
    ) -> tuple[WorldState, RuntimeState]:
        """``kind="action_start"``（§2.5：提案已验收、预约开跑）。

        PROPOSED 记录 + pending_proposals 提案成对命中 → :func:`start_action`
        两跳复合（PROPOSED→VALIDATING→ACTIVE，2 条迁移记录，D-P3-19；成功时
        移出 pending_proposals，F2-12）。簿记不变量违例（记录缺失 / 非
        PROPOSED / 提案缺失——start 条目只可能由 submit_proposal ACCEPT 路径
        成对产生）→ 表外型错误（可检查不静默，经原子刻错误路径）。

        迁移记录去向（D-P3-18 调用作用域 / D-P3-19 / F2-16）：start 的 2 条
        复合记录**不入任何 fast_forward outcome**（SchedulerOutcome.transitions
        契约，§2.3）——观察出口仅模块级 :func:`start_action` 直调返回；本方法
        在内部丢弃第 3 元，仅回传 (world, runtime)。
        """
        instance_id = self._payload_instance_id(entry)
        action = runtime.active_actions.get(instance_id)
        if action is None:
            raise IllegalTransitionError(
                f"illegal transition: from=<missing> to=<illegal> event=scheduled "
                f"(instance={instance_id} 不存在于 active_actions；action_start 条目与 "
                "PROPOSED 记录由 submit_proposal 成对产生)"
            )
        if action.status is not ActionLifecycleStatus.PROPOSED:
            raise IllegalTransitionError(
                f"illegal transition: from={action.status.value} to=<illegal> event=scheduled "
                f"(instance={instance_id}; action_start 条目仅可能命中 PROPOSED 记录)"
            )
        proposal = next(
            (p for p in runtime.pending_proposals if p.proposal_id == instance_id), None
        )
        if proposal is None:
            raise IllegalTransitionError(
                f"illegal transition: from={action.status.value} to=<illegal> event=scheduled "
                f"(instance={instance_id}; pending_proposals 缺失提案，F2-12 簿记不变量违例)"
            )
        spec = self._require_spec(proposal.action_id)
        world, runtime, _start_transitions = start_action(
            world,
            runtime,
            proposal,
            spec,
            at_tick=at_tick,
            checkpoint_interval=self._time_policy.checkpoint_interval_ticks,
        )
        # D-P3-18/19（F2-16 观察出口）：2 条复合迁移记录不入 ff outcome——
        # 此处显式丢弃（_start_transitions），观察仅模块级 start_action 直调
        return (
            world,
            rebuild_runtime(
                runtime,
                pending_proposals=[
                    p for p in runtime.pending_proposals if p.proposal_id != instance_id
                ],
            ),
        )

    def _handle_action_end(
        self,
        world: WorldState,
        runtime: RuntimeState,
        entry: ScheduledEvent,
        batch: list[ScheduledEvent],
        at_tick: int,
        tick_events: list[DomainEvent],
        txs: list[Transaction],
        events: list[DomainEvent],
        traces: list[TraceRecord],
    ) -> tuple[WorldState, RuntimeState, LifecycleTransition | None]:
        """``kind="action_end"``（§2.4：到点且 ACTIVE → ``complete_action``）。

        "若仍 ACTIVE"守卫（§2.5 表处理动作列）：实例缺失或非 ACTIVE（如 NPC
        非阻塞中断后残留条目，D-P3-25 收敛边界）→ no-op（不查迁移表、不剪
        除）——玩家暂停场景由 D-P3-24 入口首检第一道拦截。ACTIVE 到点：
        ``spec.completion_trigger`` 点名求值（D-P3-26 单路，§5.3 A4 口径）→
        完成 effect 经 P2 管道提交（D-P3-11①）→ ``complete_action`` 终态迁移
        + 剪除剩余条目（D-P3-25①，经 transition_action 终态分支）→ 迁移记录
        进 outcome.transitions。
        """
        instance_id = self._payload_instance_id(entry)
        action = runtime.active_actions.get(instance_id)
        if action is None or action.status is not ActionLifecycleStatus.ACTIVE:
            return world, runtime, None
        effects: list[ProposedEffect] = []
        spec = self._registry.lookup(action.action_id)
        if spec is not None and spec.completion_trigger is not None:
            effects = self._evaluate_named_trigger(
                spec.completion_trigger, world, tick_events
            )
        world = self._commit_into_outcome(world, effects, batch, txs, events, traces)
        _world, runtime, transition = complete_action(
            world, runtime, instance_id, at_tick=at_tick, completion_effects=effects
        )
        return _world, runtime, transition

    def _commit_scheduled(
        self,
        world: WorldState,
        runtime: RuntimeState,
        entry: ScheduledEvent,
        batch: list[ScheduledEvent],
        at_tick: int,
        tick_events: list[DomainEvent],
        txs: list[Transaction],
        events: list[DomainEvent],
        traces: list[TraceRecord],
    ) -> WorldState:
        """``kind="event"``（§2.5：通用外部事件；声明式 payload，K7/不得 3）。

        两种形态（恰居其一，互斥——``make_scheduled_event`` 入队点已强制）：

        - ``{"trigger_id": …}``：named_triggers 点名求值（D-P3-26 单路；空
          注册表 → 级联回合再求值面为空，D-P3-27）→ stub 产出 ProposedEffect
          序列经 CascadeExecutor 提交（Leader 裁定 (C) 提交参数/聚合承接）；
        - ``{"effects": [ProposedEffect JSON…], "producer": "…"}``：显式预声明
          效果批（逐项 ``model_validate`` 为 ``ProposedEffect``；非法 JSON →
          :class:`QueueInvariantError`，可检查不静默）→ 同上提交。

        空产出（触发器幂等守卫命中 / 空批）→ 零提交（无事务、无事件）。
        """
        payload = entry.payload
        if "trigger_id" in payload:
            trigger_id = payload["trigger_id"]
            if not isinstance(trigger_id, str):
                raise QueueInvariantError(
                    f"kind='event' payload trigger_id 非字符串：{trigger_id!r}"
                )
            effects = self._evaluate_named_trigger(trigger_id, world, tick_events)
        else:
            raw_effects = payload.get("effects")
            if not isinstance(raw_effects, list):
                raise QueueInvariantError(
                    f"kind='event' payload effects 非列表：{type(raw_effects).__name__}"
                )
            effects = []
            for item in raw_effects:
                try:
                    effects.append(ProposedEffect.model_validate(item))
                except ValidationError as exc:
                    raise QueueInvariantError(
                        f"kind='event' payload effects 项非合法 ProposedEffect JSON："
                        f"{exc}"
                    ) from exc
        world = self._commit_into_outcome(world, effects, batch, txs, events, traces)
        return world

    def _drain_wakeup(
        self,
        world: WorldState,
        runtime: RuntimeState,
        entry: ScheduledEvent,
        t: int,
        traces: list[TraceRecord],
    ) -> tuple[WorldState, RuntimeState]:
        """``kind="wakeup"`` 条目消费（设计文档 §2.4 主循环 / §3.8 / D-P3-14；
        T06 接线）。

        次序钉死：

        1. payload 仅携带 ``actor_id``（§2.5 表，``make_scheduled_event`` 入队
           点已强制必填键）；hook 的 ``reason`` 实参经 ``runtime.actor_wakeups``
           的 ``(actor_id, due_tick=t)`` 记录查得（``ActorWakeup.reason``，
           state.py:166，可空）——双记录口径：两条记录 ``(actor_id, due_tick)``
           一致、``reason`` 仅存 actor_wakeups 记录侧、不入 payload（E-P3-35）；
        2. 簿记：条目消费即从 ``runtime.actor_wakeups`` 同步移除该
           ``(actor_id, due_tick=t)`` 记录（首个匹配；F5-02 双记录一致——
           无论有无 hook 命中，条目消费是唯一移除触发；队列侧条目已由
           ``take_due`` 移除，列表侧同步移除）；
        3. :meth:`WakeupHookRegistry.hook_for` 为 ``None`` → 输出诊断
           :class:`TraceRecord`（``TraceKind.SYSTEM``，
           ``diagnostic="wakeup_no_hook"``）、不崩溃、簿记零影响（E-P3-39⑤）；
        4. hook 存在 → ``hook.on_wakeup(actor_id, view, clock, reason)``，其中
           ``view = guard(world)``（当刻 guard 视图，G2 移交 2）、
           ``clock = LogicalClock.of(runtime)``（当刻逻辑刻值类型，D-P3-02），
           以 :class:`WakeupHook` 协议签名为准；hook 抛任何异常 → 包装
           :class:`SchedulerWakeupError`（携带 actor_id）→ 单刻原子错误路径
           （调用点位于主循环既有 try/except 内，D-P3-24④：返回刻前状态对 +
           错误 outcome，不崩溃、部分提交不可见）；
        5. hook 返回的提案逐条经既有 :meth:`submit_proposal` 全管道
           （D-P3-14：含 ``_revalidate``（委托
           ``revalidation.revalidate_proposal``），不绕过、不内联重实现
           revalidation 逻辑）。

        同刻多条 wakeup 的确定序 = 队列序（``take_due`` 同刻批序，D-P3-05；
        D-P3-14"确定性顺序 = actor_wakeups 队列序"）——调用方按批序逐条处理，
        本方法不重排。纯函数簿记：返回新 ``(WorldState, RuntimeState)``；
        诊断记录 append 进 ``traces``（outcome.trace_records 按调用聚合通道，
        D-P3-18）。
        """
        actor_id = EntityId(str(entry.payload["actor_id"]))
        reason: str | None = None
        for record in runtime.actor_wakeups:
            if record.actor_id == actor_id and record.due_tick == t:
                reason = record.reason
                break
        # —— 簿记：条目消费即同步移除 (actor_id, due_tick) 记录（F5-02）——
        remaining = list(runtime.actor_wakeups)
        for index, record in enumerate(remaining):
            if record.actor_id == actor_id and record.due_tick == t:
                del remaining[index]
                break
        runtime = rebuild_runtime(runtime, actor_wakeups=remaining)
        hook = self._wakeup_hooks.hook_for(actor_id)
        if hook is None:
            # 无 hook 命中 → 仅诊断（TraceRecord，SYSTEM）、不崩溃、簿记零影响
            # （E-P3-39⑤）
            traces.append(
                TraceRecord(
                    record_id=new_trace_record_id(),
                    kind=TraceKind.SYSTEM,
                    world_revision=world.world_revision,
                    logical_tick=t,
                    payload={
                        "diagnostic": "wakeup_no_hook",
                        "actor_id": str(actor_id),
                    },
                )
            )
            return world, runtime
        view = guard(world)  # 当刻 guard 视图（G2 移交 2）
        clock = LogicalClock.of(runtime)  # 当刻逻辑刻值类型（D-P3-02）
        try:
            proposals = hook.on_wakeup(actor_id, view, clock, reason)
        except Exception as exc:  # 任何异常 → 包装（D-P3-14 失败处置）
            raise SchedulerWakeupError(actor_id, cause=exc) from exc
        for proposal in proposals:
            world, runtime, _decision = self.submit_proposal(
                world, runtime, proposal
            )
        return world, runtime

    # —— 主循环（§2.4 权威伪代码）——

    @staticmethod
    def _build_outcome(
        paused: bool,
        pause_reason: PauseReason | None,
        ticks_processed: int,
        txs: list[Transaction],
        events: list[DomainEvent],
        traces: list[TraceRecord],
        transitions: list[LifecycleTransition],
        errors: tuple[str, ...] = (),
    ) -> SchedulerOutcome:
        """按调用聚合的 outcome 装配（D-P3-18；errors 默认空）。"""
        return SchedulerOutcome(
            paused=paused,
            pause_reason=pause_reason,
            ticks_processed=ticks_processed,
            transactions=tuple(txs),
            events=tuple(events),
            trace_records=tuple(traces),
            transitions=tuple(transitions),
            errors=errors,
        )

    def _advance(
        self,
        world: WorldState,
        runtime: RuntimeState,
        *,
        max_tick: int | None,
        single_batch: bool,
    ) -> tuple[WorldState, RuntimeState, SchedulerOutcome]:
        """§2.4 主循环（fast_forward 与 step 的共享实现，D-P3-24⑤ 同口径）。

        次序钉死：入口首检（D-P3-24，置于循环前播种之前）→ 循环前播种
        （D-P3-22）→ ``take_due`` 批循环（同刻批稳定 FIFO，D-P3-05）→ 时钟
        跳变（D-P3-03，唯一写点）→ 批内逐条 kind 分支 → 刻后边界求值
        （T05 已接线：``_maybe_evaluate_boundaries``）→ 暂停/terminal 返回；
        单刻原子性（D-P3-24④）：批处理中
        任何 P3 错误 → 返回刻前状态对 + 错误 outcome。
        """
        # —— 入口首检（未响应暂停幂等重报，D-P3-24；重入零副作用）——
        pause = self._unanswered_pause(runtime)
        if pause is not None:
            return (
                world,
                runtime,
                self._build_outcome(True, pause, runtime.logical_tick, [], [], [], []),
            )
        # —— 循环前播种（幂等，D-P3-22）——
        runtime = self._seed_boundary_entries(runtime)

        txs: list[Transaction] = []
        events: list[DomainEvent] = []
        traces: list[TraceRecord] = []
        transitions: list[LifecycleTransition] = []
        # 活络守卫簿记（本次运行局部，跨运行不残留）：boundary_id → 最近
        # fired 的逻辑刻；同刻重入时据此跳过已 fired 边界（§2.4 边界情形注）
        boundary_fired_at: dict[str, int] = {}
        while True:
            batch_opt = take_due(runtime)
            if batch_opt is None:
                # 队列空 = 无更多调度工作（确定性终点，§2.4）
                return (
                    world,
                    runtime,
                    self._build_outcome(
                        False,
                        PauseReason(kind="terminal", tick=runtime.logical_tick),
                        runtime.logical_tick,
                        txs,
                        events,
                        traces,
                        transitions,
                    ),
                )
            runtime, batch = batch_opt
            t = batch[0].due_tick
            if max_tick is not None and t > max_tick:
                # step/测试边界：批整体还队（§6.1"队列保留"；批序 = 队列序，
                # 逐条重入队经写时稳定排序复原原队列）
                for entry in batch:
                    runtime = enqueue_scheduled_event(runtime, entry)
                return (
                    world,
                    runtime,
                    self._build_outcome(
                        True,
                        PauseReason(kind="bounded", tick=runtime.logical_tick),
                        runtime.logical_tick,
                        txs,
                        events,
                        traces,
                        transitions,
                    ),
                )
            # —— 原子刻：刻前状态对捕获（D-P3-24④）——
            pre_tick_world, pre_tick_runtime = world, runtime
            if t > LogicalClock.of(runtime).tick:
                runtime = set_logical_tick(runtime, t)  # 跳变（不逐 tick 迭代，D-P3-03）
            tick_events: list[DomainEvent] = []
            try:
                for entry in batch:
                    # 同刻批按队列序＝插入序 FIFO（D-P3-05）
                    n_events_before = len(events)
                    if entry.kind == "action_start":
                        # D-P3-18/19：start 的 2 条复合迁移记录不入 ff outcome
                        # （观察出口仅模块级 start_action 直调，F2-16）
                        world, runtime = self._handle_action_start(
                            world, runtime, entry, t
                        )
                    elif entry.kind == "action_checkpoint":
                        # re-anchor（D-P3-08）；非 ACTIVE 实例守卫 no-op +
                        # 诊断 TraceRecord（F2-02/D-P3-25，§3.6）
                        runtime, record = apply_checkpoint(
                            runtime,
                            self._payload_instance_id(entry),
                            at_tick=t,
                            current_revision=world.world_revision,
                            checkpoint_interval=self._time_policy.checkpoint_interval_ticks,
                        )
                        if record is not None:
                            traces.append(record)
                    elif entry.kind == "action_end":
                        world, runtime, end_transition = self._handle_action_end(
                            world, runtime, entry, batch, t, tick_events, txs, events, traces
                        )
                        if end_transition is not None:
                            transitions.append(end_transition)
                    elif entry.kind == "deadline":
                        # 到点且 ACTIVE → fail_action（§2.5 表；非 ACTIVE no-op）
                        deadline_id = self._payload_instance_id(entry)
                        deadline_action = runtime.active_actions.get(deadline_id)
                        if (
                            deadline_action is not None
                            and deadline_action.status is ActionLifecycleStatus.ACTIVE
                        ):
                            runtime = fail_action(
                                runtime, deadline_id, at_tick=t, reason="deadline_missed"
                            )
                    elif entry.kind == "event":
                        world = self._commit_scheduled(
                            world, runtime, entry, batch, t, tick_events, txs, events, traces
                        )
                    elif entry.kind == "wakeup":
                        # _drain_wakeup（WakeupHook，§3.8/D-P3-14）：payload 仅
                        # actor_id、reason 经 (actor_id, due_tick) 记录查得；
                        # 无 hook → 诊断；hook 异常 → SchedulerWakeupError →
                        # 本 try 的原子刻错误路径；提案经 submit_proposal 全
                        # 管道；actor_wakeups 记录随条目消费同步移除（F5-02）
                        world, runtime = self._drain_wakeup(
                            world, runtime, entry, t, traces
                        )
                    elif entry.kind == "decision_boundary":
                        # 预注册边界（刻到即视为候选，参与刻后求值；条目由循环前
                        # 播种入队，D-P3-22）——条目本身无 payload effect（no-op）
                        pass
                    else:  # 防御：构造点已强制词表（make_scheduled_event）
                        raise QueueInvariantError(f"未知队列条目 kind：{entry.kind!r}")
                    # 本刻事件流统一维护：逐条 dispatch 后收集本条新增事件
                    # （完成/事件提交经 outcome 列表承接，供刻后边界求值与
                    # 同刻后续触发器求值共用）
                    tick_events.extend(events[n_events_before:])
                # —— 刻后求值（顺序固定，D-P3-09/10；T05 接线，Leader 裁定）——
                # 每刻提交后以当刻新 guard() 视图求值（G2 移交 2）；INTERRUPTED
                # 迁移经 transition_action 唯一入口、npc wakeup 双记录、玩家
                # blocking 暂停（受 pause_on_player_boundary 门控，E-P3-36
                # record-only 两路留痕）；fired 报告经 TraceKind.SYSTEM 记录
                # 入 outcome.trace_records（F2-12 系统事件模式）。活络守卫：
                # 同一逻辑刻内已 fired 的边界（本刻 npc_notices 派生的同刻
                # wakeup 重入时）跳过，防无限再生（§2.4 边界情形注）。任何
                # P3 错误落入下方原子刻 except（D-P3-24④）。
                skip_ids = frozenset(
                    bid for bid, fired_tick in boundary_fired_at.items() if fired_tick == t
                )
                runtime, boundary_paused, boundary_pause, _report, boundary_trace = (
                    self._maybe_evaluate_boundaries(
                        world,
                        runtime,
                        tick=t,
                        tick_events=tick_events,
                        transitions=transitions,
                        skip_boundary_ids=skip_ids,
                    )
                )
                for _bid, _instance_ids in _report.fired:
                    boundary_fired_at[_bid] = t
                if boundary_trace is not None:
                    traces.append(boundary_trace)
                if boundary_paused:
                    # 玩家 blocking 边界命中 → 暂停（§2.4 末行；D-P3-10）
                    return (
                        world,
                        runtime,
                        self._build_outcome(
                            True,
                            boundary_pause,
                            t,
                            txs,
                            events,
                            traces,
                            transitions,
                        ),
                    )
            except SchedulerError as exc:
                # 原子刻错误路径（D-P3-24④）：刻前状态对 + 非空诊断（不崩溃、
                # 部分提交不可见，§2.4 确定性论证 5）
                return (
                    pre_tick_world,
                    pre_tick_runtime,
                    self._build_outcome(
                        False,
                        None,
                        pre_tick_runtime.logical_tick,
                        [],
                        [],
                        [],
                        [],
                        (f"{type(exc).__name__}: {exc}",),
                    ),
                )
            if single_batch:
                # step()：单批 + 刻后求值后强制暂停（§3.8 形态钉死：kind="bounded"）
                return (
                    world,
                    runtime,
                    self._build_outcome(
                        True,
                        PauseReason(kind="bounded", tick=runtime.logical_tick),
                        runtime.logical_tick,
                        txs,
                        events,
                        traces,
                        transitions,
                    ),
                )

    # —— 门面公开面（§3.8）——

    def fast_forward(
        self,
        world: WorldState,
        runtime: RuntimeState,
        *,
        max_tick: int | None = None,
    ) -> tuple[WorldState, RuntimeState, SchedulerOutcome]:
        """事件驱动跳变主循环（设计文档 §3.8 / §2.4 权威伪代码）。

        入口首检＝未响应暂停幂等重报（D-P3-24，重报保证**限定于该行动仍处
        INTERRUPTED（玩家未响应）期间**、无 INTERRUPTED 背书的边缘暂停仅返回
        一次且重入正常推进，D-P3-24⑥，R5/F4-02）；含循环前 scheduled 边界
        播种（幂等去重，D-P3-22）；重报规则以
        ``TimePolicy.pause_on_player_boundary=True`` 为前置（False 时玩家边界
        命中仍 fired 但不中断可中断行动、不返回 paused、重报规则不生效，
        R5/F4-03；R6/F5-03 重裁 record-only，E-P3-36）；全部世界写入统一经
        内部唯一 CascadeExecutor（G2 移交 1 / D-P3-11①）；producer 归属统一
        口径（F2-01/D-P3-11）：凡触发器（含 completion_trigger）求值产生的
        effect → producer = 该触发器注册时声明的 producer（stub ``evaluate``
        写入 ``ProposedEffect.source``，§5.1）；kind="event" 显式 effects
        形态以逐项 JSON 声明的 ``source`` 为准（producer 身份与
        authority_policy 放行面对齐，D-P3-23）；scheduler 自身不产世界
        effect（迁移至 COMPLETED 是簿记、非世界 effect、不经 authority，
        §5.3 A4）。

        提交参数钉死（F2-15/Leader 裁定 (C)）：每次 ``CascadeExecutor.run``
        提交，``causal_root_id`` = 驱动该批的队列条目 ``entry_id`` 字符串
        （本刻批首条 entry），``origin`` = ``self._origin``（E-P3-40/F5-01）。

        返回 outcome 为按调用聚合（D-P3-18）；原子刻错误路径（F2-03）：单刻
        处理中任何 P3 错误 → 返回刻前状态对 +
        ``SchedulerOutcome(paused=False, pause_reason=None,
        ticks_processed=<刻前 logical_tick>, 空元组, errors=<非空诊断串>)``。
        """
        return self._advance(world, runtime, max_tick=max_tick, single_batch=False)

    def step(
        self, world: WorldState, runtime: RuntimeState
    ) -> tuple[WorldState, RuntimeState, SchedulerOutcome]:
        """开发单步（RuntimeLifecycle.STEPPING 语义，state.py:115-127）。

        推进至下一边界（单批 + 刻后求值）后强制暂停。**强制暂停 outcome 形态
        钉死**：``paused=True``、``pause_reason = PauseReason(kind="bounded",
        tick = 本步到达刻)``、``ticks_processed = 本步到达刻``。入口首检与
        原子刻错误路径与 ``fast_forward`` 同口径（D-P3-24⑤）；队列空（无批可
        推进）→ terminal 口径（同 fast_forward）。
        """
        return self._advance(world, runtime, max_tick=None, single_batch=True)

    def submit_proposal(
        self, world: WorldState, runtime: RuntimeState, proposal: ActionProposal
    ) -> tuple[WorldState, RuntimeState, RevalidationDecision]:
        """外部提案入口（玩家/devtools/P4；设计文档 §3.8 / §3.9）。

        revalidation（§3.9）→ ACCEPT 则入 pending_proposals 并按 timing 调度
        （earliest_start_tick 未到 → kind="action_start" 预约；已到/无 → 当刻
        立即 start_action）；REJECT 则记录 FAILED 生命周期轨迹 + 诊断。

        **内部次序钉死（E-P3-39⑧ / Leader 裁定 (F)）**：

        1. registry 查找——未注册 action_id → ``UnknownActionError``（查找点
           抛出，D-P3-16 双轨）→ 编排层捕获转 FAILED 轨迹
           （``result_summary.reason="unknown_action"``，诊断串含
           action_id，A5 口径）——该错误路径**不创建 PROPOSED ActiveAction
           记录**（无悬空 PROPOSED，F2-12 纪律）；世界/队列零变更；
        2. :meth:`_revalidate`（委托 ``revalidation.revalidate_proposal``，
           §3.9 口径）→ 非 ACCEPT（REJECT）：FAILED 生命周期轨迹 + 诊断
           （``decision.details``）；
           pending_proposals 簿记（F2-12）：提案留在列表（移除仅发生于
           start_action 成功时）；
        3. ACCEPT → 创建 PROPOSED ActiveAction 记录 + 入 pending_proposals +
           start_action 复合 2 条迁移（D-P3-19；成功时移出
           pending_proposals，F2-12）。

        **start 迁移记录观察出口（F2-16）**：2 条 LifecycleTransition 在
        :func:`start_action` 模块级直调返回中可观察；本门面签名
        ``(WorldState, RuntimeState, RevalidationDecision)`` 不携带（17 条
        Gate 断言亦不引用）。
        """
        tick = runtime.logical_tick
        try:
            spec = self._require_spec(proposal.action_id)  # 1) registry 查找
            decision = self._revalidate(world, proposal)  # 2) revalidation（§3.9）
        except UnknownActionError as exc:
            # 双轨（D-P3-16 / A5 / E-P3-39⑧）：查找点异常被编排层捕获转 FAILED
            # 轨迹；不创建 PROPOSED 记录（错误路径直接落 FAILED 终态记录，
            # 无 PROPOSED 中间态——"不创建 PROPOSED ActiveAction 记录"逐字）
            runtime = self._record_failed(
                runtime, proposal, "unknown_action", tick, extra={"action_id": str(proposal.action_id)}
            )
            decision = RevalidationDecision(
                proposal_id=proposal.proposal_id,
                outcome=RevalidationOutcome.REJECT,
                reason="unknown_action",
                details=(str(exc),),
                at_revision=world.world_revision,
            )
            return world, runtime, decision
        if decision.outcome is not RevalidationOutcome.ACCEPT:
            # REJECT：记录 FAILED 生命周期轨迹 + 诊断（details）；世界/队列零变更
            runtime = self._record_failed(runtime, proposal, decision.reason, tick)
            return world, runtime, decision
        # 3) ACCEPT：PROPOSED 记录 + pending_proposals + 按 timing 调度
        runtime = self._record_proposed(runtime, proposal, spec, tick)
        earliest = proposal.timing.earliest_start_tick
        if earliest is None or earliest <= tick:
            # 立即开跑（§5.2 S1/S2 口径）：当刻 start_action（两跳复合 2 迁移）
            world, runtime, _transitions = start_action(
                world,
                runtime,
                proposal,
                spec,
                at_tick=tick,
                checkpoint_interval=self._time_policy.checkpoint_interval_ticks,
            )
            runtime = self._drop_pending(runtime, proposal.proposal_id)
        else:
            # 延迟开跑（§2.5 kind="action_start"）：预约 earliest_start_tick
            entry = make_scheduled_event(
                "action_start", earliest, payload={"instance_id": str(proposal.proposal_id)}
            )
            runtime = enqueue_scheduled_event(runtime, entry)
        return world, runtime, decision

    def resume_action(
        self,
        world: WorldState,
        runtime: RuntimeState,
        instance_id: ActionInstanceId,
    ) -> tuple[WorldState, RuntimeState, LifecycleTransition]:
        """玩家恢复（Gate 分支 A；返回类型与模块级签名对齐，§3.6，E-P3-39⑥）。

        委托 :func:`action_lifecycle.resume_action`（INTERRUPTED→ACTIVE，
        RESUMED 边，D-P3-07）：当前刻 = ``runtime.logical_tick``、re-anchor
        revision = ``world.world_revision``（D-P3-08 口径；§5.3 A1）。
        """
        return resume_action(
            world,
            runtime,
            instance_id,
            at_tick=runtime.logical_tick,
            current_revision=world.world_revision,
        )

    def abort_action(
        self, world: WorldState, runtime: RuntimeState, instance_id: ActionInstanceId
    ) -> RuntimeState:
        """玩家中止（Gate 分支 B；返回类型与模块级签名对齐，§3.6，E-P3-39⑥）。

        委托 :func:`action_lifecycle.abort_action`（INTERRUPTED→FAILED，
        ABORTED 边，D-P3-25 收敛路径）；``world`` 不变（纯 RuntimeState
        簿记，P1 D-5）——模块级签名不返回 world，本门面同口径。
        """
        return abort_action(runtime, instance_id, at_tick=runtime.logical_tick)

    # —— 私有接线点 ——

    def _require_spec(self, action_id: object) -> ActionSpec:
        """registry 查找（submit_proposal 次序第 1 步，E-P3-39⑧）：未注册 →
        :class:`UnknownActionError`（查找点抛出，D-P3-16 双轨的异常侧）。"""
        spec = self._registry.lookup(action_id)  # type: ignore[arg-type]
        if spec is None:
            raise UnknownActionError(f"未注册行动类型：{str(action_id)!r}")
        return spec

    def _revalidate(
        self, world: WorldState, proposal: ActionProposal
    ) -> RevalidationDecision:
        """revalidation 接线（设计文档 §3.9；T07 落位、Leader 裁定 (F)）。

        委托 :func:`revalidation.revalidate_proposal`（任意 producer 单一
        实现，G2 移交 3）——5 步判定顺序与原因词表见其 docstring：
        1) ``is_stale`` 陈旧 → REJECT（**REJECT 原因优先级钉死（F2-05，
        过期优先）**：``valid_until_expired`` > ``stale_revision``）；
        2) actor 存在性 → REJECT ``actor_missing``；3) ``actor_alive_check``
        （P4/P5 钩子；缺省恒真——本门面未接线钩子）→ REJECT
        ``actor_not_alive``；4) 仅 details 诊断（``actor_state_revision``
        陈旧 D-12 口径 / ``observation_id`` 记录，不作 REJECT 依据）；
        5) 全过 → ACCEPT。

        接线参数（§3.9 口径钉死）：``current`` = 当前世界 revision
        （``world.world_revision``，即 §3.9 ``current`` 缺省
        ``state.world_revision`` 的显式传参）；``allow_rebase=False``——
        调用方 :meth:`submit_proposal` 决定何时允许 REBASE，缺省关闭
        （§3.9 ``rebase_proposal`` 注记）；``actor_alive_check`` 缺省
        （恒真，P4/P5 钩子未接线）。

        P3 结果域 = {ACCEPT, REBASE, REJECT}（REBASE 在 allow_rebase 关闭时
        不可达；REPAIR 不产生于 P3 同步 tick 循环，R4/E-P3-26）。
        """
        return revalidate_proposal(
            world, proposal, current=world.world_revision, allow_rebase=False
        )

    @staticmethod
    def _drop_pending(runtime: RuntimeState, instance_id: ActionInstanceId) -> RuntimeState:
        """pending_proposals 簿记（F2-12）：start_action 成功时移出提案。"""
        return rebuild_runtime(
            runtime,
            pending_proposals=[
                p for p in runtime.pending_proposals if p.proposal_id != instance_id
            ],
        )

    @staticmethod
    def _record_proposed(
        runtime: RuntimeState, proposal: ActionProposal, spec: ActionSpec, tick: int
    ) -> RuntimeState:
        """ACCEPT 簿记（E-P3-39⑧ 第 3 步）：创建 PROPOSED ActiveAction 记录
        （start_tick=提交刻占位——start_action 第二跳覆写为实际开跑刻）+
        提案入 pending_proposals（F2-12）。"""
        record = ActiveAction(
            instance_id=proposal.proposal_id,
            action_id=proposal.action_id,
            actor_id=proposal.actor_id,
            status=ActionLifecycleStatus.PROPOSED,
            start_tick=tick,
            interruptible=spec.interruptible,
            base_world_revision=proposal.base_world_revision,
            provenance=proposal.provenance,
        )
        return rebuild_runtime(
            runtime,
            active_actions={**runtime.active_actions, record.instance_id: record},
            pending_proposals=[*runtime.pending_proposals, proposal],
        )

    @staticmethod
    def _record_failed(
        runtime: RuntimeState,
        proposal: ActionProposal,
        reason: str,
        tick: int,
        extra: dict[str, object] | None = None,
    ) -> RuntimeState:
        """REJECT/unknown 簿记（§3.8"REJECT 则记录 FAILED 生命周期轨迹 +
        诊断"；F2-12 留痕口径）：直接落 **FAILED 终态记录**（
        ``result_summary.reason`` = 判定原因；错误路径不创建 PROPOSED
        ActiveAction 记录——记录首态即 FAILED，无 PROPOSED 中间态、无悬空
        PROPOSED）+ 提案留在 pending_proposals 列表（留痕 = 仍在列表 +
        RevalidationDecision 的 REJECT 记录——ActionProposal 无 status
        字段，留痕不依赖状态字段）。

        世界/调度队列零变更（A5 口径）。
        """
        summary: dict[str, object] = {"reason": reason}
        if extra is not None:
            summary.update(extra)
        record = ActiveAction(
            instance_id=proposal.proposal_id,
            action_id=proposal.action_id,
            actor_id=proposal.actor_id,
            status=ActionLifecycleStatus.FAILED,
            start_tick=tick,
            base_world_revision=proposal.base_world_revision,
            provenance=proposal.provenance,
            result_summary={str(key): value for key, value in summary.items()},
        )
        return rebuild_runtime(
            runtime,
            active_actions={**runtime.active_actions, record.instance_id: record},
            pending_proposals=[*runtime.pending_proposals, proposal],
        )
