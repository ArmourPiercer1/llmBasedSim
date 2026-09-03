"""engine_v2 runtime 层 EngineInstance：production Engine runtime loop（T2）。

依据 ``docs/plans/runtime_closure_contract.md`` §2（方法集冻结）：本模块
**消费**已装配 :class:`~src.engine_v2.runtime.world_instance.WorldInstance`
（contract §1，T1 materialize / T9 assembly 产出），不构造 ProjectIR /
policies / executors / dynamics——装配归 T9，引擎只做运行时循环。

公开面（冻结方法集）：

- :meth:`EngineInstance.instance`：装配后的 WorldInstance（只读属性）；
- :meth:`EngineInstance.submit_proposal`：``ActionProposal`` 直接进
  「executor → effects → cascade → commit」管道；
- :meth:`EngineInstance.submit_action`：玩家侧构造 ``ActionProposal``
  （``new_action_instance_id()`` + 玩家 provenance + 当前
  ``world_revision`` base）再同管道；未注册 action（``registry.specs``
  无）→ ``StepResult(ok=False, diagnostics=("unknown_action:<id>",))``
  （显式诊断，不抛异常不静默）；
- :meth:`EngineInstance.wake`：追加 :class:`~src.engine_v2.core.state.ActorWakeup`
  入 ``runtime.actor_wakeups``（``due_tick`` 缺省 = 当前 logical_tick
  即刻到期）；
- :meth:`EngineInstance.advance`：每 tick 五相位（contract §2）：
  1. due wakeups（``due_tick <=`` 本刻）→
  2. 逐 wakeup：policy（缺 → 诊断+跳过）→ context_builder →
     ``run_policy_decide``（None 跳过）→ executor（缺 → 诊断）→
     ``ExecutorResult``（failure → 诊断；committed → 提交管道）→
  3. dynamics：每 backend ``simulate(WorldSnapshot, (), DynamicsContext)``
     → 返回 effects 走**同一**提交管道 →
  4. action lifecycle 完成（短动作本刻内联完成；长动作 = follow-up，
     见下 assumptions）→
  5. ``logical_tick + 1``（RuntimeState 重建；``world_revision`` **只**经
     提交管道 commit 推进——空 effect 批次不 commit）。
- :meth:`EngineInstance.view`：``presentation.view.derive_scene_view(world)``
  纯派生（presentation 层，零反作用）。

提交管道（K2 写授权纪律：一切世界写只能经此，引擎层零直写 WorldState；
复用 core、不自写 reducer）：``CascadeExecutor(policy=
instance.authority_policy, component_registry=…, producer_registry=…)``
——authority（closed-by-default：DENY 的 effect 被级联过滤 = 世界不变，
预期语义）→ validation → conflicts → 内部 ``commit_transaction``
（``transaction_executor.py``，空批次零事务、不消耗 revision）；
结果 :class:`~src.engine_v2.core.cascade.CascadeResult` 的
final_state / transactions（含 ABORTED）/ 诊断（authority deny 与
validation fail 经 trace_records 决策记录投影为 StepResult.diagnostics
串）全部承接。

Assumptions（T2 冻结面披露，Leader 可 follow-up 收编）：

1. **actor_wakeups 直消费**：引擎相位 1 直接消费 ``runtime.actor_wakeups``
   （``due_tick <=`` 当前刻即到期；稳定队列序），不消费 scheduler queue、
   不使用 P3 Scheduler 状态机（短动作路径不需要 ``start_action`` /
   ``complete_action`` 簿记）；``wake`` 单记录 ActorWakeup（不入队
   ``kind="wakeup"`` 双记录——引擎循环以 actor_wakeups 为唯一数据源）；
   到期条目无论处理成败均被消费（移除），与 P3 调度器"条目消费是唯一
   移除触发"同口径。
2. **长动作生命周期 = follow-up**：``ExecutorResult.duration_ticks > 0``
   的长动作，本波同样内联提交其 committed effects，但不做
   ActiveAction 簿记 / 完成效果（相位 4 对长动作为 no-op）；
   ``duration_ticks == 0`` = 短动作本刻内联完成。
3. **事务 logical_tick = None**：管道提交的事务不携带逻辑刻
   （P2 不拥有时钟，D-P2-18/D-P3-20 归属口径；P3 Scheduler 同面先例——
   ``_run_pipeline`` 不透传 logical_tick）；逻辑刻权威 =
   ``RuntimeState.logical_tick``，快照/trace 面各自对齐。
4. **单点失败 → 诊断 + 跳过**：单个 wakeup 的 context/policy/executor
   异常或单个 dynamics backend 异常 → ``StepResult.diagnostics`` 记录
   （K7 可检查不静默）+ 继续本刻（引擎无 P3 调度器单刻原子回退语义）。
5. **context_builder seam**：缺省 = 函数级 lazy import
   ``runtime.context.build_actor_context``（T4 并行开发；lazy 使引擎
   模块 import 期零 T4 依赖，T4 未就位时仅首次使用缺省构建器报错）；
   注入的构建器签名 = ``(WorldInstance, EntityId) -> ActorDecisionContext``。
6. **trace_sink 本波零调用**：``instance.trace_sink``（T8 协议）由
   T8 交付 / T9 装配侧接线，引擎方法面（contract §2）不含 trace 写。
7. **引擎级事务 provenance** = ``ProducerId("engine")`` /
   ``OriginKind.SYSTEM``（事务级装配者；各 effect 提案者仍为
   ``effect.source``，分层语义见 transaction_executor §6.4 注）。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from src.engine_v2.core.actions import ActionProposal, ActionTypeId
from src.engine_v2.core.behavior_policy import run_policy_decide
from src.engine_v2.core.cascade import CascadeExecutor
from src.engine_v2.core.clock import rebuild_runtime, set_logical_tick
from src.engine_v2.core.effects import ProposedEffect
from src.engine_v2.core.ids import EntityId, ProducerId, new_action_instance_id
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.snapshot import snapshot
from src.engine_v2.core.state import ActorWakeup, WorldState
from src.engine_v2.core.trace import TraceKind
from src.engine_v2.core.transaction import Transaction, TransactionStatus
from src.engine_v2.dynamics.backend import (
    DynamicsContext,
    WorldDynamicsBackend,
    WorldSnapshot,
)
from src.engine_v2.presentation.view import SceneView, derive_scene_view
from src.engine_v2.runtime.world_instance import WorldInstance

if TYPE_CHECKING:  # 仅注解用（house 模式；运行时零 import）
    from src.engine_v2.core.context_provider import ActorDecisionContext

__all__ = ["EngineInstance", "StepResult"]

#: 引擎级事务装配者 provenance（assumption 7：事务级与 effect 提案者分层）。
_ENGINE_PROVENANCE: Final[Provenance] = Provenance(
    producer_id=ProducerId("engine"), origin=OriginKind.SYSTEM
)

#: 玩家侧提交 provenance（``submit_action``：玩家输入 = 显式 developer
#: 家族干预面，Spec §22 origin=developer 同族标记）。
_PLAYER_PROVENANCE: Final[Provenance] = Provenance(
    producer_id=ProducerId("player"), origin=OriginKind.DEVELOPER
)


@dataclass(frozen=True)
class StepResult:
    """一次引擎操作（submit_proposal / submit_action / advance）的结果。

    - ``ok``：无诊断即 True——任何诊断串（unknown_action / no_policy /
      no_executor / action_failed / executor_error / authority_denied /
      validation_failed / transaction_aborted / cascade_* / wakeup_failed /
      dynamics_failed）→ False（可检查不静默，K7）；
    - ``world_revision``：操作结束后的权威 ``world_revision``（只随
      COMMITTED 事务推进，D-5）；
    - ``diagnostics``：诊断串（追加序；空元组 = 干净操作）；
    - ``transactions``：管道提交的全部事务（**含 ABORTED**，commit 序；
      空批次零事务——contract §2 三字段面之外的 additive 观察面，
      供 COMMITTED/ABORTED 断言，缺省空元组保持三字段构造兼容）。
    """

    ok: bool
    world_revision: Revision
    diagnostics: tuple[str, ...]
    transactions: tuple[Transaction, ...] = ()


class EngineInstance:
    """Production Engine runtime loop（contract §2；消费 WorldInstance）。

    装配方 = T9（``runtime.assembly.assemble_project``）或测试直构最小
    WorldInstance；引擎自身零装配（不构造 ProjectIR / policies /
    executors / dynamics / authority）。全部世界写入经内部唯一
    :class:`~src.engine_v2.core.cascade.CascadeExecutor`（K2 管道；
    引擎层零直写 WorldState——``instance.world`` / ``instance.runtime``
    只在管道提交与运行时簿记后做字段级整体替换）。
    """

    __slots__ = ("_instance", "_context_builder", "_cascade")

    def __init__(
        self,
        instance: WorldInstance,
        *,
        context_builder: Callable[
            [WorldInstance, EntityId], "ActorDecisionContext"
        ]
        | None = None,
    ) -> None:
        """装配（可检查不静默）：``instance`` 必填 WorldInstance。

        ``context_builder`` = 唤醒侧决策上下文构建器（seam，assumption 5）；
        缺省 None → 首次使用时函数级 lazy import T4
        ``runtime.context.build_actor_context``。
        """
        if not isinstance(instance, WorldInstance):
            raise TypeError(
                f"EngineInstance 需要 WorldInstance，得到 {type(instance).__name__}"
            )
        self._instance = instance
        self._context_builder = context_builder
        # K2 管道：引擎层唯一世界写入口（构造期幂等武装写屏障）
        self._cascade = CascadeExecutor(
            policy=instance.authority_policy,
            component_registry=instance.component_registry,
            producer_registry=instance.producer_registry,
        )

    @property
    def instance(self) -> WorldInstance:
        """装配后的 WorldInstance（权威状态 + 依赖闭包）。"""
        return self._instance

    # —— 公开方法面（contract §2 冻结）——

    def submit_proposal(self, proposal: ActionProposal) -> StepResult:
        """提案直接进「executor → effects → cascade → commit」管道。

        前置守卫（显式诊断不静默）：action 未注册（``registry.specs``
        无）→ ``unknown_action:<id>``；无注册执行器 → ``no_executor:<id>``。
        执行失败面（``ExecutorResult.failure`` 非 None）→ ``action_failed``
        诊断 + 零世界变更。
        """
        return self._execute_proposal(proposal)

    def submit_action(
        self,
        actor_id: str,
        action_id: str,
        arguments: Mapping[str, object],
        *,
        intent: str | None = None,
    ) -> StepResult:
        """玩家侧动作提交：构造 ActionProposal 再走 ``submit_proposal`` 同管道。

        构造面钉死：``proposal_id`` = ``new_action_instance_id()``；
        ``action_id`` = ``ActionTypeId(<action_id>)``；``arguments`` 原样
        承载；``base_world_revision`` = 当前 ``world.world_revision``；
        ``provenance`` = 玩家侧（``producer_id="player"`` /
        ``OriginKind.DEVELOPER``）。未注册 action →
        ``StepResult(ok=False, diagnostics=("unknown_action:<id>",))``
        （不抛异常不静默，contract §2）。
        """
        typed_action_id = ActionTypeId(action_id)
        if typed_action_id not in self._instance.action_registry.specs:
            return StepResult(
                False,
                self._instance.world.world_revision,
                (f"unknown_action:{action_id}",),
            )
        proposal = ActionProposal(
            proposal_id=new_action_instance_id(),
            actor_id=EntityId(actor_id),
            action_id=typed_action_id,
            arguments=dict(arguments),
            intent=intent,
            base_world_revision=self._instance.world.world_revision,
            provenance=_PLAYER_PROVENANCE,
        )
        return self._execute_proposal(proposal)

    def wake(
        self,
        actor_id: str,
        *,
        reason: str | None = None,
        due_tick: int | None = None,
    ) -> None:
        """追加 ActorWakeup 入 ``runtime.actor_wakeups``（assumption 1）。

        ``due_tick`` 缺省 = 当前 ``logical_tick``（即刻到期：下一次
        ``advance`` 的相位 1 处理）；``reason`` 仅存 ActorWakeup 记录
        （双记录口径的 reason 承载位，state.py:166）。
        """
        instance = self._instance
        wakeup = ActorWakeup(
            actor_id=EntityId(actor_id),
            due_tick=instance.runtime.logical_tick if due_tick is None else due_tick,
            reason=reason,
        )
        instance.runtime = rebuild_runtime(
            instance.runtime,
            actor_wakeups=[*instance.runtime.actor_wakeups, wakeup],
        )

    def advance(self, ticks: int = 1) -> StepResult:
        """推进 ``ticks`` 个逻辑刻（每刻五相位，contract §2；相位序冻结）。

        单刻 = 相位 1（due wakeups）→ 2（policy → proposal → executor →
        提交管道）→ 3（dynamics 每 backend simulate → 同一提交管道）→
        4（action lifecycle：短动作内联完成、长动作 follow-up no-op，
        assumption 2）→ 5（``set_logical_tick`` 唯一时钟写点 +
        actor_wakeups 重建）。``world_revision`` 只经提交管道推进；
        空 effect 批次不 commit（零事务零 revision 消耗）。
        """
        if not isinstance(ticks, int) or isinstance(ticks, bool) or ticks < 1:
            raise ValueError(f"advance(ticks) 必须为 >= 1 的 int，得到 {ticks!r}")
        instance = self._instance
        diagnostics: list[str] = []
        transactions: list[Transaction] = []
        for _ in range(ticks):
            tick = instance.runtime.logical_tick
            # —— 相位 1：due wakeups（due_tick <= 本刻；稳定队列序）——
            due = [w for w in instance.runtime.actor_wakeups if w.due_tick <= tick]
            remaining = [w for w in instance.runtime.actor_wakeups if w.due_tick > tick]
            # —— 相位 2：逐 wakeup 决策 + 执行（到期条目无论成败均消费）——
            for wakeup in due:
                diagnostics.extend(self._process_wakeup(wakeup, tick, transactions))
            # —— 相位 3：dynamics（注册序；每 backend 独立快照 + 提交）——
            for backend in instance.dynamics:
                diagnostics.extend(self._run_dynamics(backend, tick, transactions))
            # —— 相位 4：action lifecycle 完成（短动作已在相位 2 内联完成；
            #    长动作生命周期 = follow-up no-op，assumption 2）——
            # —— 相位 5：logical_tick + 1（RuntimeState 重建；唯一时钟写点）——
            instance.runtime = rebuild_runtime(
                set_logical_tick(instance.runtime, tick + 1),
                actor_wakeups=remaining,
            )
        return StepResult(
            not diagnostics,
            instance.world.world_revision,
            tuple(diagnostics),
            tuple(transactions),
        )

    def view(self) -> SceneView:
        """呈现层纯派生：``derive_scene_view(world)``（零反作用）。"""
        return derive_scene_view(self._instance.world)

    # —— 私有管道（K2：全部世界写经 _apply_effects → CascadeExecutor）——

    def _process_wakeup(
        self, wakeup: ActorWakeup, tick: int, transactions: list[Transaction]
    ) -> list[str]:
        """相位 2 单 wakeup：policy → context → decide → executor → 管道。

        失败口径（assumption 4，K7 可检查不静默）：无 policy 绑定 →
        ``no_policy:<actor>`` 诊断 + 跳过；context/policy 异常 →
        ``wakeup_failed`` 诊断 + 跳过；proposal 为 None = 合法 no-op。
        """
        instance = self._instance
        actor_id = wakeup.actor_id
        policy = instance.policies.get(str(actor_id))
        if policy is None:
            return [f"no_policy:{actor_id}"]
        try:
            context = self._build_context(actor_id)
            proposal = run_policy_decide(policy, context)
        except Exception as exc:  # 单点失败不中断本刻（assumption 4）
            return [f"wakeup_failed:{actor_id}:{type(exc).__name__}: {exc}"]
        if proposal is None:
            return []
        result = self._execute_proposal(proposal, at_tick=tick, transactions=transactions)
        return list(result.diagnostics)

    def _build_context(self, actor_id: EntityId) -> "ActorDecisionContext":
        """唤醒侧决策上下文构建（seam，assumption 5：T4 lazy import）。"""
        builder = self._context_builder
        if builder is None:
            # seam：T4 runtime/context.build_actor_context 并行开发中——
            # 函数级 lazy import 使引擎模块 import 期零 T4 依赖（T4 未
            # 就位时仅首次使用缺省构建器报错，注入构建器路径不受影响）。
            from src.engine_v2.runtime.context import build_actor_context

            builder = build_actor_context
            self._context_builder = builder
        return builder(self._instance, actor_id)

    def _run_dynamics(
        self,
        backend: "WorldDynamicsBackend",
        tick: int,
        transactions: list[Transaction],
    ) -> list[str]:
        """相位 3 单 backend：simulate → 返回 effects 走同一提交管道。

        快照面（core/snapshot.py）：``snapshot(world, runtime,
        world_instance_id, created_logical_tick=tick)`` →
        ``WorldSnapshot.from_snapshot``（丢弃墙钟，K7）；
        ``DynamicsContext(base_revision=当前 world_revision, dt=1.0)``。
        backend 异常 → ``dynamics_failed`` 诊断 + 跳过（assumption 4）；
        空 effects = 零提交（不消耗 revision）。
        """
        instance = self._instance
        backend_id = backend.metadata().backend_id
        try:
            core_snapshot = snapshot(
                instance.world,
                instance.runtime,
                instance.world_instance_id,
                created_logical_tick=tick,
            )
            effects = backend.simulate(
                WorldSnapshot.from_snapshot(core_snapshot),
                (),
                DynamicsContext(
                    base_revision=int(instance.world.world_revision), dt=1.0
                ),
            )
        except Exception as exc:  # 单点失败不中断本刻（assumption 4）
            return [f"dynamics_failed:{backend_id}:{type(exc).__name__}: {exc}"]
        effects = tuple(effects)
        if not effects:
            return []
        return self._apply_effects(
            list(effects),
            causal_root_id=f"dyn_{tick}_{backend_id}",
            transactions=transactions,
        )

    def _execute_proposal(
        self,
        proposal: ActionProposal,
        *,
        at_tick: int | None = None,
        transactions: list[Transaction] | None = None,
    ) -> StepResult:
        """「executor → effects → cascade → commit」管道（提交前置守卫）。

        守卫序（显式诊断不静默）：1) 注册表检查（未注册 →
        ``unknown_action:<id>``）；2) 执行器查找（缺 → ``no_executor:<id>``）；
        3) ``executor.execute(proposal, world, tick)``（异常 →
        ``executor_error`` 诊断）；4) ``ExecutorResult.failure`` 非 None →
        ``action_failed`` 诊断 + 零世界变更；5) committed effects →
        :meth:`_apply_effects`（空批次零提交）。
        """
        instance = self._instance
        current_revision = instance.world.world_revision
        diagnostics: list[str] = []
        if proposal.action_id not in instance.action_registry.specs:
            return StepResult(
                False,
                current_revision,
                (f"unknown_action:{proposal.action_id}",),
            )
        executor = instance.executors.get(str(proposal.action_id))
        if executor is None:
            return StepResult(
                False,
                current_revision,
                (f"no_executor:{proposal.action_id}",),
            )
        tick = at_tick if at_tick is not None else instance.runtime.logical_tick
        try:
            result = executor.execute(proposal, instance.world, tick)
        except Exception as exc:
            return StepResult(
                False,
                current_revision,
                (f"executor_error:{proposal.action_id}:{type(exc).__name__}: {exc}",),
            )
        if result.failure is not None:
            return StepResult(
                False,
                current_revision,
                (f"action_failed:{proposal.action_id}:{result.failure}",),
            )
        if result.committed:
            own_transactions: list[Transaction] = []
            diagnostics = self._apply_effects(
                list(result.committed),
                causal_root_id=str(proposal.proposal_id),
                transactions=own_transactions,
            )
            if transactions is not None:
                transactions.extend(own_transactions)
            return StepResult(
                not diagnostics,
                instance.world.world_revision,
                tuple(diagnostics),
                tuple(own_transactions),
            )
        return StepResult(
            not diagnostics,
            instance.world.world_revision,
            tuple(diagnostics),
            (),
        )

    def _apply_effects(
        self,
        effects: list[ProposedEffect],
        *,
        causal_root_id: str,
        transactions: list[Transaction] | None = None,
    ) -> list[str]:
        """提交管道唯一入口（K2）：CascadeExecutor.run → 世界替换 + 诊断。

        - 空批次：零提交（不消耗 revision；``commit_transaction`` 空批
          ValueError 由"不进入管道"前置规避）→ 零诊断、世界原样；
        - 管道产出承接：``final_state`` 字段级替换 ``instance.world``；
          transactions（含 ABORTED，commit 序）承接进调用方聚合列表；
        - 诊断投影（可检查不静默）：trace 决策记录中
          ``authority_decision decision=deny`` → ``authority_denied:<id>:
          <reason>``（closed-by-default 拒绝 = 世界不变，预期语义）；
          ``validation_decision decision=fail`` → ``validation_failed``；
          ABORTED 事务 → ``transaction_aborted``；级联诊断 →
          ``cascade_<kind>``。
        """
        if not effects:
            return []
        result = self._cascade.run(
            effects,
            self._instance.world,
            causal_root_id=causal_root_id,
            origin=_ENGINE_PROVENANCE,
        )
        diagnostics: list[str] = []
        for record in result.trace_records:
            payload = record.payload
            if record.kind is TraceKind.AUTHORITY_DECISION and (
                payload.get("decision") == "deny"
            ):
                diagnostics.append(
                    f"authority_denied:{payload.get('effect_id')}:{payload.get('reason')}"
                )
            elif record.kind is TraceKind.VALIDATION_DECISION and (
                payload.get("decision") == "fail"
            ):
                diagnostics.append(
                    f"validation_failed:{payload.get('effect_id')}:{payload.get('reason')}"
                )
        for txn in result.transactions:
            if txn.status is TransactionStatus.ABORTED:
                diagnostics.append(
                    f"transaction_aborted:{txn.transaction_id}:{txn.abort_reason}"
                )
        for cascade_diagnostic in result.diagnostics:
            diagnostics.append(
                f"cascade_{cascade_diagnostic.kind}:{cascade_diagnostic.detail}"
            )
        if transactions is not None:
            transactions.extend(result.transactions)
        self._instance.world = result.final_state
        return diagnostics
