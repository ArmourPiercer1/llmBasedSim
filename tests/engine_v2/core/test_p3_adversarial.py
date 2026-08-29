"""P3-T08 对抗套件（设计文档 §6.3 A1–A8 原始类条款逐类落地）。

依据 ``docs/v2/contracts/P3-scheduler-time-action-design.md`` §6.3（原始
八类条款清单；本文件按原文逐类实现——任务简报转述与原文有出入处，以
原文为准，裁定记入报告）：

- **A1**（stale 提案）：``TestA1`` —— 5 条 t=1 显式 effect 条目先把世界
  推到 R5（预声明升序 base R0..R4、FIFO 提交 R0→R5；管道同刻多提交要求
  base 预声明——处理时 base 须等于当前世界 revision，D-P2-10），再提交
  P1（base R0、无 valid_until）→ REJECT ``stale_revision``；act_1 不进
  ACTIVE、提案留 pending_proposals（F2-12：移除仅发生于 start_action
  成功）、世界/队列零变更、revision 停在 R5；变体 ``valid_until=R4``
  （stale ∧ expired 双真）→ REJECT ``valid_until_expired``（F2-05 过期
  优先）。
- **A2**（中断/恢复/中止矩阵）：``TestA2`` —— 4 个表外
  IllegalTransitionError 探针（COMPLETED→RESUMED / FAILED→RESUMED /
  ACTIVE→ABORTED / INTERRUPTED→INTERRUPTED，错误串均携带
  from/to/event）+ 合法对照序列（resume → 再中断@14 → abort，全部
  表内迁移）+ D-P3-25 非阻塞 NPC 方向（boundary interrupt=True ∧
  blocking=False → INTERRUPTED 不暂停、时钟继续到 30、cp@10 唯一
  ``checkpoint_skipped_interrupted`` 诊断、end@30 no-op 守卫）。
- **A3**（同刻事件顺序）：``TestA3`` —— 3 生产者（prod_a/prod_b/
  prod_c）t=5 三条显式 effect 条目（预声明升序 base R0/R1/R2）FIFO
  提交（revision 1/2/3）→ 刻后 B3（NPC 非阻塞）fired → INTERRUPTED +
  同刻尾部 wakeup（D 条目，§2.4 边界情形）→ 第二批 drain wakeup
  （``wakeup_no_hook`` 唯一诊断、trace 尾部）→ 处理顺序 ==
  trace_records 追加序（D-P3-05 稳定 FIFO）；双跑键序列恒等
  （D-P3-15①）。
- **A4**（回放确定性）：``TestA4`` —— E1（分支 A 全跑事件键序列）
  后缀 == E2（t=12 snapshot→restore 续跑）== E3（新 fixture 重跑续跑）；
  uuid4 标识按数量/运行内唯一性/前缀（evt_/txn_/sch_）/位置同构比较
  （D-P3-15②：从不跨运行比较原始值）。
- **A5**（未注册行动）：``TestA5`` —— action_id="flying" →
  UnknownActionError 被编排层捕获（D-P3-16 双轨 / E-P3-39⑧ 第 1 步）→
  REJECT ``unknown_action`` + FAILED 终态记录（result_summary reason +
  action_id）+ 无悬空 PROPOSED（F2-12）+ 不崩溃 + 队列零残留 + 世界
  零变更 + 诊断串含 action_id。
- **A6**（直接模块级 transition 误用）：``TestA6`` —— 延迟启动提案
  （earliest_start_tick=20 → PROPOSED 滞留 + action_start@20 预约）上
  直接 ``transition_action(runtime, iid, RESUMED)`` →
  IllegalTransitionError（PROPOSED 行无 RESUMED 边）；合法事件探针
  （INTERRUPTED→RESUMED）携带 ``updates`` 契约外字段 → ValidationError
  （``_rebuild_action`` 经 model_validate extra=forbid，第二道防线）。
- **A7**（边界无响应者）：``TestA7`` —— B1 暂停后不 resume/abort 再
  ff → entry-first-check 幂等重报（同暂停：B1/tick 12/ticks 12、四清单
  全空、时钟不前进、队列不变 [cp@20, end@30]，D-P3-24②）→ 显式 abort
  使规则自动失效（状态离开 INTERRUPTED，D-P3-24③）→ 续跑至终态
  （分支 B 形态）→ 再 ff 仍幂等终态。
- **A8**（时钟/队列不变量）：``TestA8`` —— ``set_logical_tick`` 回退 →
  ClockRollbackError（单调时钟；唯一合法回退是状态级 restore，D-P3-02）；
  5 个 QueueInvariantError 探针（past 入队 / 负 due / 重复 entry_id /
  表外 kind / 缺 payload 键）；时钟跳变后 ``next_due_tick == 队列
  最小 due_tick``；同刻入队（due == 当前刻）合法且追加同刻批尾部
  （D-P3-05 / §2.4 边界情形）。

import 纪律（任务硬规则 4）：本文件不 import datetime/time/random/
asyncio/provider/LLM/网络库；仅直接子模块导入（无星号导入）；机械
谓词锚点见 ``test_import_boundary.py`` P3 段。

纯测试任务（零 src/ 改动）：全部机制已对当前实现经验证（若发现实现
偏差 → 报告精确 delta，不修 src）。
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from src.engine_v2.core.action_lifecycle import (
    IllegalTransitionError,
    LifecycleEvent,
    transition_action,
)
from src.engine_v2.core.action_registry import ActionRegistry, ActionTypeId
from src.engine_v2.core.actions import (
    ActionLifecycleStatus,
    ActionProposal,
    ActionTiming,
)
from src.engine_v2.core.authority import (
    AuthorityPolicy,
    AuthorityRule,
    AuthoritySelector,
)
from src.engine_v2.core.cascade import CascadeTriggerRegistry, SyncTrigger
from src.engine_v2.core.clock import (
    ClockRollbackError,
    next_due_tick,
    set_logical_tick,
)
from src.engine_v2.core.effects import EntityTarget, ProposedEffect
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.events import DomainEvent
from src.engine_v2.core.event_queue import (
    QueueInvariantError,
    enqueue_scheduled_event,
    make_scheduled_event,
    take_due,
)
from src.engine_v2.core.ids import ActionInstanceId, EffectId, EntityId, ProducerId
from src.engine_v2.core.interrupt import DecisionBoundary, InterruptCondition
from src.engine_v2.core.reducer import (
    EFFECT_CREATE_ENTITY,
    GuardedWorldState,
    install_write_barrier,
)
from src.engine_v2.core.revalidation import RevalidationOutcome
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.scheduler import Scheduler, SchedulerOutcome, TimePolicy
from src.engine_v2.core.snapshot import restore_snapshot, snapshot
from src.engine_v2.core.state import RuntimeState, WorldState
from src.engine_v2.core.trace import TraceKind
from tests.engine_v2.core import conftest as p3

#: A2 第二遭遇实体（独立幂等守卫）
ENT_BANDIT_2 = EntityId("ent_bandit_2")
#: A3 三生产者（"注册时声明"的 producer 载体 = effect.source，L3-01）
PROD_A = ProducerId("prod_a")
PROD_B = ProducerId("prod_b")
PROD_C = ProducerId("prod_c")
#: A3/A2 非阻塞 NPC 方向实例
NPC_INSTANCE_ID = ActionInstanceId("act_npc_travel")
#: A5 未注册行动探针
FLYING_ID = ActionInstanceId("act_flying")
#: A6 延迟启动探针
DEFERRED_ID = ActionInstanceId("act_deferred")


# —— 本地观察口辅助（replay 比较键口径：D-P3-15①/D-P3-20，同 Gate 文件）——


def _event_key(event: DomainEvent, outcome: SchedulerOutcome) -> tuple[str, int, int]:
    """逐事件键 ``(event_type, world_revision, 事件发生刻)``。

    发生刻 = 本次调用 ``ticks_processed`` 水位（调度器不打逻辑戳于事件，
    D-P2-18/D-P3-20：``event.logical_tick`` 恒 None）。uuid4 标识不入键。
    """
    return (event.event_type, int(event.world_revision), outcome.ticks_processed)


def _event_keys(outcome: SchedulerOutcome) -> list[tuple[str, int, int]]:
    return [_event_key(e, outcome) for e in outcome.events]


def _transition_keys(
    outcome: SchedulerOutcome,
) -> list[tuple[str, str, str, int]]:
    """transitions 的 uuid4 无关投影（from, event, to, at_tick）。"""
    return [
        (tr.from_status.value, tr.event.value, tr.to_status.value, tr.at_tick)
        for tr in outcome.transitions
    ]


def _trace_keys(
    outcome: SchedulerOutcome,
) -> list[tuple[str, int | None, int | None, str | None]]:
    """trace_records 追加序投影（kind, world_revision, tick, producer）。"""
    return [
        (
            r.kind.value,
            None if r.world_revision is None else int(r.world_revision),
            r.logical_tick,
            None if r.producer_id is None else str(r.producer_id),
        )
        for r in outcome.trace_records
    ]


# —— 对抗变体工厂（纯函数；conftest 口径镜像，零 src/ 依赖新增）——


def _encounter_stub(
    trigger_id: str, entity_id: EntityId, effect_id: str
) -> SyncTrigger:
    """泛化遭遇 stub：幂等状态守卫（目标已在世界 → 空 effect 列表，
    R4/E-P3-24）+ create_entity；producer = origin_scenario（注册时声明，
    写入 ``ProposedEffect.source``；L3-01）。"""

    def evaluate(
        events: Sequence[DomainEvent], state: GuardedWorldState, depth: int
    ) -> Sequence[ProposedEffect]:
        if state.has_entity(entity_id):
            return []
        return [
            ProposedEffect(
                effect_id=EffectId(effect_id),
                effect_type=EFFECT_CREATE_ENTITY,
                source=p3.ORIGIN_SCENARIO,
                target=EntityTarget(entity_id=entity_id),
                payload={"entity_class": "bandit", "tags": ["enemy"], "components": {}},
                base_revision=state.world_revision,
                cause_ids=[],
            )
        ]

    return SyncTrigger(trigger_id, evaluate)


def _build_scheduler(
    *,
    named_triggers: frozenset[tuple[str, SyncTrigger]] | None = None,
    boundaries: list[DecisionBoundary] | None = None,
    authority_policy: AuthorityPolicy | None = None,
    player_ids: frozenset[EntityId] | None = None,
    registry: ActionRegistry | None = None,
    time_policy: TimePolicy | None = None,
) -> Scheduler:
    """对抗变体调度器装配（conftest ``make_gate_scheduler`` 同款口径）：
    空级联注册表（D-P3-27/E-P3-30 单路化）+ named_triggers 点名求值 +
    run()-级 origin + 写屏障先行武装（F2-06）。"""
    install_write_barrier()
    return Scheduler(
        registry or p3.make_gate_registry(),
        authority_policy=authority_policy or p3.make_gate_authority_policy(),
        origin=p3.ORIGIN_PROVENANCE,
        time_policy=time_policy or p3.make_gate_time_policy(),
        boundaries=boundaries if boundaries is not None else [p3.make_gate_boundary()],
        trigger_registry=CascadeTriggerRegistry(),
        named_triggers=(
            named_triggers
            if named_triggers is not None
            else frozenset(
                {
                    (p3.TRIGGER_ENCOUNTER, p3.make_encounter_stub()),
                    (p3.TRIGGER_ARRIVAL, p3.make_arrival_stub()),
                }
            )
        ),
        player_actor_ids=(
            player_ids if player_ids is not None else frozenset({p3.ENT_PLAYER})
        ),
        assert_barrier_armed=True,
    )


def _npc_world() -> WorldState:
    """A2/A3 变体世界：Gate 世界 + 裸 ENT_NPC（无组件；travel 参数面不
    要求 NPC 持 movement）。冻结模型经模块级构造重建（合法，非写路径）。"""
    base = p3.make_gate_world()
    return WorldState(
        entities={
            **base.entities,
            p3.ENT_NPC: EntityRecord(entity_id=p3.ENT_NPC, components={}),
        }
    )


def _npc_boundary() -> DecisionBoundary:
    """B_npc：condition 型（C1 同款 event_type=core.create_entity）、
    actor=ent_npc、**blocking=False ∧ interrupt=True**（D-P3-25 非阻塞
    方向：命中 → INTERRUPTED 不暂停 + npc_notices wakeup 建议）。"""
    return DecisionBoundary(
        boundary_id="B_npc",
        actor_id=p3.ENT_NPC,
        kind="condition",
        condition=InterruptCondition(
            condition_id="C_npc",
            kind="event_type",
            parameters={"event_type": "core.create_entity"},
        ),
        blocking=False,
        interrupt=True,
        reason="npc-encounter",
    )


def _npc_proposal() -> ActionProposal:
    """NPC travel 提案（base R0、hint 30 → 30 tick；t=0 立即开跑）。"""
    return ActionProposal(
        proposal_id=NPC_INSTANCE_ID,
        actor_id=p3.ENT_NPC,
        action_id=p3.TRAVEL,
        arguments={"destination": p3.ENT_DEST},
        timing=ActionTiming(duration_hint_ticks=30),
        base_world_revision=p3.R0,
        provenance=p3.ORIGIN_PROVENANCE,
    )


def _triple_producer_policy() -> AuthorityPolicy:
    """A3 授权变体：prod_a/prod_b/prod_c 三者均可写 create_entity（closed-
    by-default 下显式授予，D-P3-23）。"""
    return AuthorityPolicy(
        rules=[
            AuthorityRule(
                rule_id="ap_create_entity_triple",
                selector=AuthoritySelector(effect_type=EFFECT_CREATE_ENTITY),
                allowed_writers=[PROD_A, PROD_B, PROD_C],
            )
        ]
    )


def _explicit_create_entry(
    due_tick: int,
    base_revision: int,
    effect_id: str,
    producer: ProducerId,
    entity_id: str,
    entity_class: str = "npc",
) -> "object":
    """显式 effect 形态队列条目（kind="event"，``effects`` + ``producer``
    XOR ``trigger_id``）：target 必须携带 ``"kind": "entity"``
    （EntityTarget 判别联合）。"""
    return make_scheduled_event(
        "event",
        due_tick,
        payload={
            "effects": [
                {
                    "effect_id": effect_id,
                    "effect_type": EFFECT_CREATE_ENTITY,
                    "source": str(producer),
                    "target": {"kind": "entity", "entity_id": entity_id},
                    "payload": {"entity_class": entity_class, "tags": [], "components": {}},
                    "base_revision": base_revision,
                    "cause_ids": [],
                }
            ],
            "producer": str(producer),
        },
    )


# —— A1 前置：5 条 t=1 显式 effect 条目把世界推到 R5 ——


def _advance_world_to_r5(runtime: RuntimeState) -> RuntimeState:
    """A1 世界前置（原文逐字"先经其他事件把世界推进到 R5"）：5 条同刻
    条目**预声明升序 base R0..R4** → 处理时 base == 当前 revision 逐条
    通过（D-P2-10 校验时点）→ FIFO 提交 R0→R1→...→R5（F2-05 每 commit
    恰 +1）。"""
    for k in range(5):
        runtime = enqueue_scheduled_event(
            runtime,
            _explicit_create_entry(
                1, k, f"eff_adv_{k:03d}", p3.ORIGIN_SCENARIO, f"ent_b{k + 1}",
                entity_class="bandit",
            ),
        )
    return runtime


# —— A4 分支 A 全跑（E1 口径：S0→S8 + resume→终态，新鲜状态起步）——


def _branch_a_to_pause() -> tuple[WorldState, RuntimeState, Scheduler, SchedulerOutcome]:
    world, runtime, scheduler, proposal = p3.make_gate_state()
    world, runtime, outcome = p3.gate_run_to_pause(scheduler, world, runtime, proposal)
    return world, runtime, scheduler, outcome


def _resume_and_finish(
    scheduler: Scheduler, world: WorldState, runtime: RuntimeState
) -> SchedulerOutcome:
    """分支 A 续跑（resume 必须使用返回的新状态，F2-16 门面口径）。"""
    world, runtime, _transition = scheduler.resume_action(
        world, runtime, p3.P1_INSTANCE_ID
    )
    _world, _runtime, outcome = scheduler.fast_forward(world, runtime)
    return outcome


# —— A3 场景装配（三生产者同刻 + NPC 非阻塞边界）——


def _a3_setup() -> tuple[WorldState, RuntimeState, Scheduler, ActionProposal]:
    world = _npc_world()
    runtime = RuntimeState()
    for k, (producer, entity_id) in enumerate(
        [(PROD_A, "ent_x1"), (PROD_B, "ent_x2"), (PROD_C, "ent_x3")]
    ):
        runtime = enqueue_scheduled_event(
            runtime,
            _explicit_create_entry(5, k, f"eff_x{k + 1:03d}", producer, entity_id),
        )
    scheduler = _build_scheduler(
        authority_policy=_triple_producer_policy(),
        boundaries=[_npc_boundary()],
        player_ids=frozenset(),
    )
    return world, runtime, scheduler, _npc_proposal()


class TestA1:
    """A1（stale 提案）：世界先推进到 R5 后提交 base R0 的 P1 → REJECT
    stale_revision；变体 valid_until=R4 → REJECT valid_until_expired
    （F2-05 过期优先，D-P3-16 revalidation 双条件）。"""

    def test_stale_rejected_after_world_advances(
        self, gate_scheduler: Scheduler
    ) -> None:
        world, runtime = p3.make_gate_world(), p3.make_initial_runtime()
        runtime = _advance_world_to_r5(runtime)
        world, runtime, o1 = gate_scheduler.fast_forward(world, runtime)
        # t=1：5 条 FIFO 提交（revision 1..5）→ 刻后 B1（create_entity
        # 命中）→ blocking 玩家暂停 @1（D-P3-10）
        assert int(world.world_revision) == 5
        assert [int(txn.commit_revision) for txn in o1.transactions] == [1, 2, 3, 4, 5]
        assert o1.paused is True
        assert o1.pause_reason is not None
        assert o1.pause_reason.kind == "decision_boundary"
        assert o1.pause_reason.boundary_id == "B1"
        assert o1.pause_reason.tick == 1
        assert o1.ticks_processed == 1
        # A1：R5 之上提交 P1（base R0、无 valid_until）→ REJECT stale_revision
        world2, runtime2, decision = gate_scheduler.submit_proposal(
            world, runtime, p3.make_gate_proposal()
        )
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "stale_revision"
        record = runtime2.active_actions[p3.P1_INSTANCE_ID]
        assert record.status is ActionLifecycleStatus.FAILED  # A1：不进 ACTIVE
        assert record.result_summary["reason"] == "stale_revision"
        # F2-12：提案留在 pending_proposals（移除仅发生于 start_action 成功）
        assert [p.proposal_id for p in runtime2.pending_proposals] == [
            p3.P1_INSTANCE_ID
        ]
        # A1：世界零额外变更、队列零变更、revision 停在 R5
        assert world2 == world
        assert runtime2.scheduler_queue == runtime.scheduler_queue
        assert int(world2.world_revision) == 5

    def test_valid_until_expired_priority(self, gate_scheduler: Scheduler) -> None:
        """变体：base R0 ∧ valid_until=R4（当前 R5）——stale 与 expired
        双真 → REJECT 理由必须为 ``valid_until_expired``（F2-05 过期
        优先于 stale_revision）。"""
        world, runtime = p3.make_gate_world(), p3.make_initial_runtime()
        runtime = _advance_world_to_r5(runtime)
        world, runtime, _o1 = gate_scheduler.fast_forward(world, runtime)
        assert int(world.world_revision) == 5
        proposal = ActionProposal(
            proposal_id=p3.P1_INSTANCE_ID,
            actor_id=p3.ENT_PLAYER,
            action_id=p3.TRAVEL,
            arguments={"destination": p3.ENT_DEST},
            timing=ActionTiming(duration_hint_ticks=30),
            base_world_revision=p3.R0,
            valid_until=Revision(4),
            provenance=p3.ORIGIN_PROVENANCE,
        )
        world2, runtime2, decision = gate_scheduler.submit_proposal(
            world, runtime, proposal
        )
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "valid_until_expired"
        record = runtime2.active_actions[p3.P1_INSTANCE_ID]
        assert record.status is ActionLifecycleStatus.FAILED
        assert record.result_summary["reason"] == "valid_until_expired"
        assert [p.proposal_id for p in runtime2.pending_proposals] == [
            p3.P1_INSTANCE_ID
        ]
        assert world2 == world
        assert int(world2.world_revision) == 5


class TestA2:
    """A2（中断/恢复/中止矩阵）：表外探针 4 连击（错误串含 from/to/
    event）+ 合法对照序列（resume→再中断→abort 全表内）+ D-P3-25 非阻塞
    NPC 方向（INTERRUPTED 不暂停、时钟继续、cp 跳过诊断唯一）。"""

    def test_illegal_transition_probes(self) -> None:
        # 探针 1：COMPLETED→RESUMED（分支 A 终态后）
        world, runtime, scheduler, proposal = p3.make_gate_state()
        world, runtime, _o1 = p3.gate_run_to_pause(
            scheduler, world, runtime, proposal
        )
        world, runtime, _t = scheduler.resume_action(
            world, runtime, p3.P1_INSTANCE_ID
        )
        world, runtime, _o2 = scheduler.fast_forward(world, runtime)
        assert (
            runtime.active_actions[p3.P1_INSTANCE_ID].status
            is ActionLifecycleStatus.COMPLETED
        )
        with pytest.raises(IllegalTransitionError) as exc1:
            transition_action(
                runtime, p3.P1_INSTANCE_ID, LifecycleEvent.RESUMED, at_tick=30
            )
        msg1 = str(exc1.value)
        assert "from=completed" in msg1
        assert "to=<illegal>" in msg1
        assert "event=resumed" in msg1
        # 探针 2：FAILED→RESUMED（abort 终态后）
        worldB, runtimeB, schedB, propB = p3.make_gate_state()
        worldB, runtimeB, _ = p3.gate_run_to_pause(schedB, worldB, runtimeB, propB)
        runtimeB = schedB.abort_action(worldB, runtimeB, p3.P1_INSTANCE_ID)
        with pytest.raises(IllegalTransitionError) as exc2:
            transition_action(
                runtimeB, p3.P1_INSTANCE_ID, LifecycleEvent.RESUMED, at_tick=12
            )
        assert "from=failed" in str(exc2.value)
        assert "event=resumed" in str(exc2.value)
        # 探针 3：ACTIVE→ABORTED（表外：abort 仅自 INTERRUPTED，
        # E-P3-29② 直调门面同口径——迁移表 ACTIVE 行无 ABORTED 边）
        worldC, runtimeC, schedC, propC = p3.make_gate_state()
        worldC, runtimeC, _ = schedC.submit_proposal(worldC, runtimeC, propC)
        assert (
            runtimeC.active_actions[p3.P1_INSTANCE_ID].status
            is ActionLifecycleStatus.ACTIVE
        )
        with pytest.raises(IllegalTransitionError) as exc3:
            transition_action(
                runtimeC, p3.P1_INSTANCE_ID, LifecycleEvent.ABORTED, at_tick=0
            )
        msg3 = str(exc3.value)
        assert "from=active" in msg3
        assert "to=<illegal>" in msg3
        assert "event=aborted" in msg3
        # 探针 4：INTERRUPTED→INTERRUPTED（重复中断自环，表外）
        worldD, runtimeD, schedD, propD = p3.make_gate_state()
        worldD, runtimeD, _ = p3.gate_run_to_pause(schedD, worldD, runtimeD, propD)
        with pytest.raises(IllegalTransitionError) as exc4:
            transition_action(
                runtimeD, p3.P1_INSTANCE_ID, LifecycleEvent.INTERRUPTED, at_tick=12
            )
        msg4 = str(exc4.value)
        assert "from=interrupted" in msg4
        assert "event=interrupted" in msg4

    def test_legal_resume_reinterrupt_abort_sequence(self) -> None:
        """合法对照：两次遭遇（t=12/t=14 各自 create_entity）——
        pause@12 → resume → 再中断@14（pause 再发）→ abort，全部表内
        迁移、零异常；终态剪除 D-P3-25 清队列。"""
        world = p3.make_gate_world()
        runtime = p3.make_initial_runtime()  # [ev_enc@12]
        runtime = enqueue_scheduled_event(
            runtime,
            make_scheduled_event(
                "event", 14, payload={"trigger_id": "scenario.encounter_14"}
            ),
        )
        scheduler = _build_scheduler(
            named_triggers=frozenset(
                {
                    (p3.TRIGGER_ENCOUNTER, p3.make_encounter_stub()),
                    (
                        "scenario.encounter_14",
                        _encounter_stub(
                            "scenario.encounter_14", ENT_BANDIT_2, "eff_encounter_002"
                        ),
                    ),
                    (p3.TRIGGER_ARRIVAL, p3.make_arrival_stub()),
                }
            )
        )
        proposal = p3.make_gate_proposal()
        world, runtime, _decision = scheduler.submit_proposal(world, runtime, proposal)
        world, runtime, o1 = scheduler.fast_forward(world, runtime)
        # t=12：create ent_bandit（txn R0→R1）→ B1 → INTERRUPTED@12 + 暂停
        assert o1.paused is True
        assert o1.pause_reason is not None
        assert o1.pause_reason.boundary_id == "B1"
        assert o1.pause_reason.tick == 12
        assert [int(txn.commit_revision) for txn in o1.transactions] == [1]
        assert (
            _transition_keys(o1)
            == [("active", "interrupted", "interrupted", 12)]
        )
        # 合法：resume（INTERRUPTED→ACTIVE 表内；使用返回新状态）
        world, runtime, t1 = scheduler.resume_action(
            world, runtime, p3.P1_INSTANCE_ID
        )
        assert t1.event is LifecycleEvent.RESUMED
        assert t1.at_tick == 12
        assert t1.from_status is ActionLifecycleStatus.INTERRUPTED
        assert t1.to_status is ActionLifecycleStatus.ACTIVE
        # re-anchor 至当前世界 revision（D-P3-08）
        assert int(runtime.active_actions[p3.P1_INSTANCE_ID].base_world_revision) == 1
        # t=14：create ent_bandit_2（txn R1→R2）→ B1 再 fired（跨刻重评
        # 不受活络守卫辖制）→ 再中断@14 + 暂停再发
        world, runtime, o2 = scheduler.fast_forward(world, runtime, max_tick=14)
        assert o2.paused is True
        assert o2.pause_reason is not None
        assert o2.pause_reason.boundary_id == "B1"
        assert o2.pause_reason.tick == 14
        assert o2.ticks_processed == 14
        assert [int(txn.commit_revision) for txn in o2.transactions] == [2]
        assert (
            _transition_keys(o2)
            == [("active", "interrupted", "interrupted", 14)]
        )
        # 合法：abort（INTERRUPTED→FAILED 表内；门面仅返回 runtime，P1 D-5）
        runtime = scheduler.abort_action(world, runtime, p3.P1_INSTANCE_ID)
        record = runtime.active_actions[p3.P1_INSTANCE_ID]
        assert record.status is ActionLifecycleStatus.FAILED
        assert record.result_summary["reason"] == "aborted"
        assert record.result_summary["tick"] == 14
        # D-P3-25① 终态剪除：cp@20/end@30 残留条目清空
        assert len(runtime.scheduler_queue) == 0

    def test_nonblocking_npc_interrupt_continues(self) -> None:
        """D-P3-25 非阻塞方向：B_npc（blocking=False ∧ interrupt=True）
        命中 → NPC travel INTERRUPTED 但**不暂停**（玩家暂停仅 blocking
        命中，D-P3-10）；同刻尾部 wakeup 被 drain（``wakeup_no_hook``
        唯一诊断）；cp@10 唯一 ``checkpoint_skipped_interrupted``；
        end@30 no-op 守卫；时钟继续至终态 30，全程零异常。"""
        world = _npc_world()
        runtime = RuntimeState()
        runtime = enqueue_scheduled_event(
            runtime,
            make_scheduled_event(
                "event", 5, payload={"trigger_id": p3.TRIGGER_ENCOUNTER}
            ),
        )
        scheduler = _build_scheduler(
            boundaries=[_npc_boundary()], player_ids=frozenset()
        )
        proposal = _npc_proposal()
        world, runtime, _decision = scheduler.submit_proposal(
            world, runtime, proposal
        )
        world, runtime, outcome = scheduler.fast_forward(world, runtime)
        # 无暂停：终态收口 @30（非阻塞命中不产生 decision_boundary 暂停）
        assert outcome.paused is False
        assert outcome.pause_reason is not None
        assert outcome.pause_reason.kind == "terminal"
        assert outcome.pause_reason.tick == 30
        assert outcome.ticks_processed == 30
        # t=5 唯一提交：create ent_bandit（R0→R1）。键的第 3 位 = 本次
        # 调用 ticks_processed 水位（30；事件真实刻不打戳存储——
        # D-P2-18/D-P3-20——由下条 INTERRUPTED@5 迁移与单事件位序钉死）
        assert int(world.world_revision) == 1
        assert [int(txn.commit_revision) for txn in outcome.transactions] == [1]
        assert _event_keys(outcome) == [("core.create_entity", 1, 30)]
        # 唯一迁移：INTERRUPTED@5（ACTIVE→INTERRUPTED；re-anchor 至 R1）
        assert _transition_keys(outcome) == [
            ("active", "interrupted", "interrupted", 5)
        ]
        record = runtime.active_actions[NPC_INSTANCE_ID]
        assert record.status is ActionLifecycleStatus.INTERRUPTED
        assert record.base_world_revision == 1
        assert record.last_transition_tick == 5
        # D-P3-25：收敛路径 = P4/P5 重提案（本套件不触发）——INTERRUPTED
        # 记录保留、cp/end 残留条目由终态语义兜底（cp@10 跳过诊断、
        # end@30 no-op）
        system_traces = [
            r for r in outcome.trace_records if r.kind is TraceKind.SYSTEM
        ]
        assert sum(
            1 for r in system_traces if r.payload.get("diagnostic") == "wakeup_no_hook"
        ) == 1  # 同刻尾部 wakeup（D 条目）被 drain；无 hook → 唯一诊断
        assert sum(
            1
            for r in system_traces
            if r.payload.get("diagnostic") == "checkpoint_skipped_interrupted"
        ) == 1  # cp@10：INTERRUPTED 守卫跳过（action_lifecycle.py:652）
        wakeup_traces = [
            r for r in system_traces if r.payload.get("diagnostic") == "wakeup_no_hook"
        ]
        assert wakeup_traces[0].payload.get("actor_id") == "ent_npc"
        # npc_notices 留痕（F2-12）：fired 报告 trace 含 B_npc 建议对
        notice_traces = [
            r
            for r in system_traces
            if "B_npc" in str(r.payload.get("npc_notices", ""))
        ]
        assert len(notice_traces) == 1
        # 时钟越过中断刻继续推进（无暂停的权威证据）
        assert runtime.logical_tick == 30


class TestA3:
    """A3（同刻事件顺序）：三生产者 t=5 三条显式 effect 条目 FIFO 提交
    + 刻后非阻塞边界派生 wakeup（D）追加同刻批尾部 → 处理顺序 ==
    trace_records 追加序（D-P3-05）；双跑键序列恒等（D-P3-15①）。"""

    def test_same_tick_fifo_order_with_derived_wakeup(self) -> None:
        world, runtime, scheduler, proposal = _a3_setup()
        world, runtime, _decision = scheduler.submit_proposal(world, runtime, proposal)
        world, runtime, outcome = scheduler.fast_forward(world, runtime)
        # t=5 批 [A, B, C] FIFO（入队序）：3 提交（revision 1/2/3）
        commits = [
            (int(txn.base_revision), int(txn.commit_revision))
            for txn in outcome.transactions
        ]
        assert commits == [(0, 1), (1, 2), (2, 3)]
        # 事件序 A, B, C（event_type == effect_type 同词法空间，
        # transaction_executor 1:1 发射映射 D-P2-12）。键第 3 位 = 本次
        # 调用水位（30；真实刻不打戳——由 DOMAIN_EVENT trace 的 revision
        # 序 1/2/3 与同批位序承载，见下）
        assert _event_keys(outcome) == [
            ("core.create_entity", 1, 30),
            ("core.create_entity", 2, 30),
            ("core.create_entity", 3, 30),
        ]
        # 处理顺序 == trace_records 追加序：DOMAIN_EVENT trace 的
        # (revision, producer) 序逐字 A→B→C
        domain_traces = [
            r
            for r in outcome.trace_records
            if r.kind is TraceKind.DOMAIN_EVENT
        ]
        assert [(int(r.world_revision), str(r.producer_id)) for r in domain_traces] == [
            (1, "prod_a"),
            (2, "prod_b"),
            (3, "prod_c"),
        ]
        effect_ids = [
            r.payload["record"]["payload"]["effect_id"] for r in domain_traces
        ]
        assert effect_ids == ["eff_x001", "eff_x002", "eff_x003"]
        # D 条目（wakeup）追加同刻批尾部、第二批 drain → wakeup_no_hook
        # 唯一诊断且位于三条 DOMAIN_EVENT trace 之后（追加序尾部）
        system_traces = [
            r for r in outcome.trace_records if r.kind is TraceKind.SYSTEM
        ]
        wakeup_idx = [
            i
            for i, r in enumerate(outcome.trace_records)
            if r.kind is TraceKind.SYSTEM
            and r.payload.get("diagnostic") == "wakeup_no_hook"
        ]
        assert len(wakeup_idx) == 1
        last_domain_idx = max(
            i for i, r in enumerate(outcome.trace_records)
            if r.kind is TraceKind.DOMAIN_EVENT
        )
        assert wakeup_idx[0] > last_domain_idx
        assert wakeup_idx[0] < len(outcome.trace_records)
        # B3（B_npc）fired：INTERRUPTED@5 + npc_notices 留痕；无暂停
        assert _transition_keys(outcome) == [
            ("active", "interrupted", "interrupted", 5)
        ]
        assert outcome.paused is False
        assert outcome.pause_reason is not None
        assert outcome.pause_reason.kind == "terminal"
        assert outcome.ticks_processed == 30
        # cp@10 跳过诊断（INTERRUPTED 守卫）与终态
        assert sum(
            1
            for r in system_traces
            if r.payload.get("diagnostic") == "checkpoint_skipped_interrupted"
        ) == 1
        record = runtime.active_actions[NPC_INSTANCE_ID]
        assert record.status is ActionLifecycleStatus.INTERRUPTED
        assert int(record.base_world_revision) == 3  # re-anchor 至 R3
        assert int(world.world_revision) == 3

    def test_same_tick_order_deterministic_across_runs(self) -> None:
        """双跑（新装配）：逐事件键 / DOMAIN_EVENT (revision, producer) /
        transitions / 全 trace 投影 / 世界终态 逐项恒等（D-P3-15①：
        确定性 = 相同输入 → 相同可观察序）。"""
        world1, runtime1, scheduler1, proposal1 = _a3_setup()
        world1, runtime1, _d1 = scheduler1.submit_proposal(
            world1, runtime1, proposal1
        )
        world1, runtime1, o1 = scheduler1.fast_forward(world1, runtime1)
        world2, runtime2, scheduler2, proposal2 = _a3_setup()
        world2, runtime2, _d2 = scheduler2.submit_proposal(
            world2, runtime2, proposal2
        )
        world2, runtime2, o2 = scheduler2.fast_forward(world2, runtime2)
        assert _event_keys(o1) == _event_keys(o2)
        assert _transition_keys(o1) == _transition_keys(o2)
        assert _trace_keys(o1) == _trace_keys(o2)
        d1 = [
            (int(r.world_revision), str(r.producer_id))
            for r in o1.trace_records
            if r.kind is TraceKind.DOMAIN_EVENT
        ]
        d2 = [
            (int(r.world_revision), str(r.producer_id))
            for r in o2.trace_records
            if r.kind is TraceKind.DOMAIN_EVENT
        ]
        assert d1 == d2 == [(1, "prod_a"), (2, "prod_b"), (3, "prod_c")]
        assert world1 == world2


class TestA4:
    """A4（回放确定性）：E1 分支 A 全跑事件键序列后缀 == E2
    （t=12 snapshot→restore 续跑）== E3（新 fixture 重跑续跑）；uuid4
    标识按数量/运行内唯一性/前缀/位置同构比较（D-P3-15②，从不跨运行
    比原始值）。"""

    def test_branch_a_replay_event_keys(self) -> None:
        # E1：分支 A 全跑（暂停段 + 续跑段）
        world8, runtime8, scheduler, o1 = _branch_a_to_pause()
        o2 = _resume_and_finish(scheduler, world8, runtime8)
        e1 = _event_keys(o1) + _event_keys(o2)
        assert e1 == [
            ("core.create_entity", 1, 12),
            ("core.set_component", 2, 30),
        ]
        # E2：t=12 暂停点 snapshot → restore 续跑（E-P3-07/D-P3-11② 唯一
        # 合法深拷贝路径）
        snap = snapshot(world8, runtime8, "p3-a4-e2")
        worldR, runtimeR = restore_snapshot(snap)
        worldR, runtimeR, _t = scheduler.resume_action(
            worldR, runtimeR, p3.P1_INSTANCE_ID
        )
        _worldR, _runtimeR, oE2 = scheduler.fast_forward(worldR, runtimeR)
        e2 = _event_keys(oE2)
        # E3：新 fixture 重跑至暂停 → 续跑
        world3, runtime3, scheduler3, proposal3 = p3.make_gate_state()
        world3, runtime3, _o13 = p3.gate_run_to_pause(
            scheduler3, world3, runtime3, proposal3
        )
        oE3 = _resume_and_finish(scheduler3, world3, runtime3)
        e3 = _event_keys(oE3)
        # 原文口径：E1 后缀 == E2 == E3（t=12 之后的事件键序列）
        assert e1[1:] == e2 == e3
        assert e2 == [("core.set_component", 2, 30)]
        # 续跑段 transitions/trace 投影亦恒等（确定性全通道）
        assert _transition_keys(o2) == _transition_keys(oE2) == _transition_keys(oE3)
        assert _trace_keys(o2) == _trace_keys(oE2) == _trace_keys(oE3)

    def test_uuid4_id_invariants_across_runs(self) -> None:
        """D-P3-15②：uuid4 标识不跨运行比原始值——只比数量/运行内
        唯一性/前缀/位置同构。两次独立全跑（暂停 + 续跑）。"""
        def _run() -> tuple[list[str], list[str], list[str]]:
            world8, runtime8, scheduler, o1 = _branch_a_to_pause()
            # 暂停点队列条目 ID（ev_enc + cp@20 + end@30，sch_ 前缀）
            entry_ids = [e.entry_id for e in runtime8.scheduler_queue]
            o2 = _resume_and_finish(scheduler, world8, runtime8)
            event_ids = [e.event_id for e in o1.events] + [e.event_id for e in o2.events]
            txn_ids = [
                t.transaction_id for t in o1.transactions
            ] + [t.transaction_id for t in o2.transactions]
            return event_ids, txn_ids, entry_ids

        run1 = _run()
        run2 = _run()
        # (a) 数量相等
        for ids1, ids2 in zip(run1, run2, strict=True):
            assert len(ids1) == len(ids2)
        assert len(run1[0]) == 2  # 每段各 1 事件
        assert len(run1[1]) == 2  # 每段各 1 事务
        assert len(run1[2]) == 2  # 暂停点队列 2 条目（ev_enc 已于 t=12 消费）
        # (b) 运行内唯一性
        for ids in run1:
            assert len(set(ids)) == len(ids)
        for ids in run2:
            assert len(set(ids)) == len(ids)
        # (c) 前缀：evt_ / txn_ / sch_
        assert all(i.startswith("evt_") for i in run1[0])
        assert all(i.startswith("txn_") for i in run1[1])
        assert all(i.startswith("sch_") for i in run1[2])
        assert all(i.startswith("evt_") for i in run2[0])
        assert all(i.startswith("txn_") for i in run2[1])
        assert all(i.startswith("sch_") for i in run2[2])
        # (d) 位置同构（同位置同类前缀；原始值可不同）
        for ids1, ids2 in zip(run1, run2, strict=True):
            for a, b in zip(ids1, ids2, strict=True):
                assert a[:4] == b[:4]


class TestA5:
    """A5（未注册行动）：action_id="flying" → UnknownActionError 被编排
    层捕获转 FAILED 轨迹（D-P3-16 双轨 / E-P3-39⑧ 第 1 步）：不崩溃、
    无悬空 PROPOSED、队列零残留、世界零变更、诊断串含 action_id。"""

    def test_unknown_action_failed_trajectory(self) -> None:
        world, runtime, scheduler, _ = p3.make_gate_state()
        flying = ActionProposal(
            proposal_id=FLYING_ID,
            actor_id=p3.ENT_PLAYER,
            action_id=ActionTypeId("flying"),
            arguments={},
            timing=ActionTiming(duration_hint_ticks=10),
            base_world_revision=p3.R0,
            provenance=p3.ORIGIN_PROVENANCE,
        )
        world2, runtime2, decision = scheduler.submit_proposal(world, runtime, flying)
        # REJECT + 诊断串含 action_id（E-P3-39⑧ 第 1 步）
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "unknown_action"
        assert any("flying" in d for d in decision.details)
        # FAILED 终态记录（错误路径不创建 PROPOSED 记录，F2-12 纪律）
        record = runtime2.active_actions[FLYING_ID]
        assert record.status is ActionLifecycleStatus.FAILED
        assert record.result_summary == {
            "reason": "unknown_action",
            "action_id": "flying",
        }
        assert all(
            r.status is not ActionLifecycleStatus.PROPOSED
            for r in runtime2.active_actions.values()
        )
        # F2-12 留痕：提案留在 pending_proposals（_record_failed 口径）
        assert [p.proposal_id for p in runtime2.pending_proposals] == [FLYING_ID]
        # A5：队列零残留（初始 [ev_enc@12] 原样）、世界零变更
        assert runtime2.scheduler_queue == runtime.scheduler_queue
        assert world2 == world
        assert int(world2.world_revision) == int(p3.R0)

    def test_unknown_action_then_ff_unaffected(self) -> None:
        """REJECT 后世界/时钟未动 → ff 正常继续：t=12 遭遇提交（R0→R1）
        + B1 blocking 暂停（无 ACTIVE 玩家行动亦暂停，D-P3-10 口径）、
        transitions 空（无可中断对象）。"""
        world, runtime, scheduler, _ = p3.make_gate_state()
        flying = ActionProposal(
            proposal_id=FLYING_ID,
            actor_id=p3.ENT_PLAYER,
            action_id=ActionTypeId("flying"),
            arguments={},
            timing=ActionTiming(duration_hint_ticks=10),
            base_world_revision=p3.R0,
            provenance=p3.ORIGIN_PROVENANCE,
        )
        world, runtime, _decision = scheduler.submit_proposal(world, runtime, flying)
        world, runtime, outcome = scheduler.fast_forward(world, runtime)
        assert int(world.world_revision) == 1
        assert [int(txn.commit_revision) for txn in outcome.transactions] == [1]
        assert outcome.paused is True
        assert outcome.pause_reason is not None
        assert outcome.pause_reason.kind == "decision_boundary"
        assert outcome.pause_reason.boundary_id == "B1"
        assert outcome.pause_reason.tick == 12
        # 无 ACTIVE 玩家行动 → 中断步无对象 → transitions 空
        assert outcome.transitions == ()
        # t=12 后队列耗尽（ev_enc 已消费；无行动派生条目）
        assert len(runtime.scheduler_queue) == 0


class TestA6:
    """A6（直接模块级 transition 误用）：延迟启动 PROPOSED 状态上直接
    RESUMED → IllegalTransitionError（PROPOSED 行无 RESUMED 边）；合法
    事件 + ``updates`` 契约外字段 → ValidationError（``_rebuild_action``
    经 model_validate extra=forbid——第二道防线，第一道 = 迁移表）。"""

    def test_proposed_resume_illegal(self) -> None:
        world, runtime, scheduler, _ = p3.make_gate_state()
        deferred = ActionProposal(
            proposal_id=DEFERRED_ID,
            actor_id=p3.ENT_PLAYER,
            action_id=p3.TRAVEL,
            arguments={"destination": p3.ENT_DEST},
            timing=ActionTiming(earliest_start_tick=20, duration_hint_ticks=30),
            base_world_revision=p3.R0,
            provenance=p3.ORIGIN_PROVENANCE,
        )
        world, runtime, decision = scheduler.submit_proposal(world, runtime, deferred)
        # 延迟启动：ACCEPT → PROPOSED 滞留 + pending + action_start@20
        assert decision.outcome is RevalidationOutcome.ACCEPT
        record = runtime.active_actions[DEFERRED_ID]
        assert record.status is ActionLifecycleStatus.PROPOSED
        assert [p.proposal_id for p in runtime.pending_proposals] == [DEFERRED_ID]
        queue_kinds = [(e.kind, e.due_tick) for e in runtime.scheduler_queue]
        assert ("action_start", 20) in queue_kinds
        assert ("event", 12) in queue_kinds
        # A6：PROPOSED 上直接 RESUMED → 表外 → IllegalTransitionError
        with pytest.raises(IllegalTransitionError) as exc:
            transition_action(runtime, DEFERRED_ID, LifecycleEvent.RESUMED, at_tick=0)
        msg = str(exc.value)
        assert "from=proposed" in msg
        assert "to=<illegal>" in msg
        assert "event=resumed" in msg

    def test_updates_out_of_contract_field_rejected(self) -> None:
        """合法事件探针（INTERRUPTED→RESUMED 表内）但 ``updates`` 携带
        契约外字段 → ``_rebuild_action`` 的 model_validate（extra=forbid）
        抛 ValidationError——即使迁移表放行，重建期仍拦截。"""
        world, runtime, scheduler, proposal = p3.make_gate_state()
        world, runtime, _o1 = p3.gate_run_to_pause(scheduler, world, runtime, proposal)
        assert (
            runtime.active_actions[p3.P1_INSTANCE_ID].status
            is ActionLifecycleStatus.INTERRUPTED
        )
        with pytest.raises(ValidationError):
            transition_action(
                runtime,
                p3.P1_INSTANCE_ID,
                LifecycleEvent.RESUMED,
                at_tick=12,
                updates={"bogus_field": 1},
            )


class TestA7:
    """A7（边界无响应者）：B1 暂停后不 resume/abort 再 ff → 入口首检
    幂等重报同一暂停（D-P3-24②：四清单全空、时钟不前进、队列不变）；
    显式 abort 使规则自动失效（状态离开 INTERRUPTED，D-P3-24③）→ 续跑
    至终态（分支 B 形态）；终态后再次 ff 仍幂等。"""

    def test_unanswered_pause_idempotent_re_report(self) -> None:
        world, runtime, scheduler, proposal = p3.make_gate_state()
        world, runtime, o1 = p3.gate_run_to_pause(scheduler, world, runtime, proposal)
        assert o1.pause_reason is not None
        assert o1.pause_reason.boundary_id == "B1"
        queue_before = runtime.scheduler_queue
        assert [(e.kind, e.due_tick) for e in queue_before] == [
            ("action_checkpoint", 20),
            ("action_end", 30),
        ]
        # 无响应者（不 resume/abort）再 ff：entry-first-check → 幂等重报
        # 同一暂停（D-P3-24②：暂停报告是纯派生，不消耗队列、不推进时钟）
        world2, runtime2, o2 = scheduler.fast_forward(world, runtime)
        assert o2.paused is True
        assert o2.pause_reason is not None
        assert o2.pause_reason.kind == "decision_boundary"
        assert o2.pause_reason.boundary_id == "B1"
        assert o2.pause_reason.tick == 12
        assert o2.ticks_processed == 12
        # 零副作用：四清单全空（SchedulerOutcome 字段为 tuple 型）
        assert o2.transactions == ()
        assert o2.events == ()
        assert o2.transitions == ()
        assert o2.errors == ()
        # 时钟停在 12、队列不变、世界零变更
        assert runtime2.logical_tick == 12
        assert runtime2.scheduler_queue == queue_before
        assert world2 == world

    def test_abort_invalidates_rule_then_terminal(self) -> None:
        world, runtime, scheduler, proposal = p3.make_gate_state()
        world, runtime, _o1 = p3.gate_run_to_pause(scheduler, world, runtime, proposal)
        # 显式 abort → 状态离开 INTERRUPTED → 无响应者规则自动失效
        # （D-P3-24③：规则 = 派生条件，非持久挂起标志）
        runtime = scheduler.abort_action(world, runtime, p3.P1_INSTANCE_ID)
        assert (
            runtime.active_actions[p3.P1_INSTANCE_ID].status
            is ActionLifecycleStatus.FAILED
        )
        # 续跑至终态（分支 B 形态）：终态剪除清空队列（D-P3-25①）
        world, runtime, o2 = scheduler.fast_forward(world, runtime)
        assert o2.paused is False
        assert o2.pause_reason is not None
        assert o2.pause_reason.kind == "terminal"
        assert o2.pause_reason.tick == 12
        assert o2.ticks_processed == 12
        assert o2.transactions == ()
        assert o2.events == ()
        assert o2.transitions == ()
        assert o2.errors == ()
        assert len(runtime.scheduler_queue) == 0

    def test_terminal_re_report_idempotent(self) -> None:
        """终态收口后再次 ff：队列空 → 再报同一终态（纯派生、幂等；
        与 A7② 的暂停幂等同一机制面）。"""
        world, runtime, scheduler, proposal = p3.make_gate_state()
        world, runtime, _o1 = p3.gate_run_to_pause(scheduler, world, runtime, proposal)
        runtime = scheduler.abort_action(world, runtime, p3.P1_INSTANCE_ID)
        world, runtime, o2 = scheduler.fast_forward(world, runtime)
        world, runtime, o3 = scheduler.fast_forward(world, runtime)
        assert o3.paused is False
        assert o3.pause_reason is not None
        assert o3.pause_reason.kind == "terminal"
        assert o3.pause_reason.tick == o2.pause_reason.tick
        assert o3.ticks_processed == 12
        assert o3.transactions == ()
        assert o3.events == ()


class TestA8:
    """A8（时钟/队列不变量）：单调时钟回退 → ClockRollbackError；5 个
    QueueInvariantError 探针（past 入队 / 负 due / 重复 entry_id / 表外
    kind / 缺 payload 键）；时钟跳变后 next_due_tick == 队列最小
    due_tick；同刻入队（due == 当前刻）合法且追加同刻批尾部
    （D-P3-05 / §2.4 边界情形）。"""

    def test_clock_rollback_rejected(self) -> None:
        runtime = p3.make_initial_runtime()
        assert runtime.logical_tick == 0
        # 前跳合法（单调非降；调度器自身即前跳推进）
        runtime = set_logical_tick(runtime, 12)
        assert runtime.logical_tick == 12
        # 回退 → ClockRollbackError（唯一合法回退是状态级 restore，D-P3-02）
        with pytest.raises(ClockRollbackError) as exc:
            set_logical_tick(runtime, 5)
        msg = str(exc.value)
        assert "from=12" in msg
        assert "to=5" in msg
        # 异常路径零副作用（不可变运行时）
        assert runtime.logical_tick == 12

    def test_queue_invariant_probes(self) -> None:
        runtime12 = set_logical_tick(RuntimeState(), 12)
        # 探针 1：past 入队（due_tick < logical_tick）→ 入队点拒绝
        past = make_scheduled_event(
            "event", 10, payload={"trigger_id": p3.TRIGGER_ENCOUNTER}
        )
        with pytest.raises(QueueInvariantError):
            enqueue_scheduled_event(runtime12, past)
        # 探针 2：负 due_tick → make 点拒绝（词表 + 非负校验）
        with pytest.raises(QueueInvariantError):
            make_scheduled_event(
                "event", -1, payload={"trigger_id": p3.TRIGGER_ENCOUNTER}
            )
        # 探针 3：重复 entry_id → 第二次入队拒绝（运行内唯一）
        dup = "sch_dup_001"
        e1 = make_scheduled_event(
            "event", 20, payload={"trigger_id": p3.TRIGGER_ENCOUNTER}, entry_id=dup
        )
        runtime2 = enqueue_scheduled_event(runtime12, e1)
        e2 = make_scheduled_event(
            "event", 25, payload={"trigger_id": p3.TRIGGER_ENCOUNTER}, entry_id=dup
        )
        with pytest.raises(QueueInvariantError):
            enqueue_scheduled_event(runtime2, e2)
        # 探针 4：表外 kind → make 点拒绝（SCHEDULED_EVENT_KINDS 词表）
        with pytest.raises(QueueInvariantError):
            make_scheduled_event("teleport", 5, payload={})
        # 探针 5：缺必需 payload 键 → make 点拒绝
        # （event 形态 trigger_id XOR effects+producer；action_end 需
        # instance_id）
        with pytest.raises(QueueInvariantError):
            make_scheduled_event("event", 5, payload={})
        with pytest.raises(QueueInvariantError):
            make_scheduled_event("action_end", 5, payload={})
        # next_due_tick 恒等：时钟跳变后 == 队列最小 due_tick
        runtime3 = enqueue_scheduled_event(
            set_logical_tick(RuntimeState(), 12),
            make_scheduled_event(
                "event", 20, payload={"trigger_id": p3.TRIGGER_ENCOUNTER}
            ),
        )
        runtime3 = enqueue_scheduled_event(
            runtime3,
            make_scheduled_event(
                "event", 25, payload={"trigger_id": p3.TRIGGER_ARRIVAL}
            ),
        )
        assert next_due_tick(runtime3) == min(
            e.due_tick for e in runtime3.scheduler_queue
        ) == 20
        # 空队列 → None
        assert next_due_tick(RuntimeState()) is None

    def test_same_tick_enqueue_legal_and_fifo_tail(self) -> None:
        """§2.4 边界情形：``due_tick == 当前刻`` 的入队合法（追加同刻批
        尾部，仍在同一刻内处理完）；同刻多条按入队序稳定 FIFO
        （D-P3-05，调度器永不重排）。"""
        runtime12 = set_logical_tick(RuntimeState(), 12)
        entry = make_scheduled_event(
            "event", 12, payload={"trigger_id": p3.TRIGGER_ENCOUNTER}
        )
        runtime2 = enqueue_scheduled_event(runtime12, entry)  # 合法：无异常
        assert next_due_tick(runtime2) == 12
        runtime3, batch = take_due(runtime2)
        assert batch is not None
        assert [e.entry_id for e in batch] == [entry.entry_id]
        assert runtime3 is not None
        assert runtime3.logical_tick == 12
        # 同刻 FIFO：先入 a 后入 b → 批内序 [a, b]
        runtime5 = set_logical_tick(RuntimeState(), 5)
        a = make_scheduled_event(
            "event", 5, payload={"trigger_id": p3.TRIGGER_ENCOUNTER}
        )
        b = make_scheduled_event(
            "event", 5, payload={"trigger_id": p3.TRIGGER_ARRIVAL}
        )
        runtime5 = enqueue_scheduled_event(runtime5, a)
        runtime5 = enqueue_scheduled_event(runtime5, b)
        _runtime6, batch2 = take_due(runtime5)
        assert batch2 is not None
        assert [e.entry_id for e in batch2] == [a.entry_id, b.entry_id]
