"""P3-T04b scheduler.py 门面单元测试（设计文档 §3.8 / §2.4 / §3.9 / §6.1 口径）。

依据 ``docs/v2/contracts/P3-scheduler-time-action-design.md``：

- **契约模型**（§3.8）：``TimePolicy`` / ``PauseReason`` / ``SchedulerOutcome``
  必填字段、缺省面与 frozen / extra="forbid" 契约校验（ContractModel 纪律）；
- **确定性指纹**（§3.8 / D-P3-15 / E-P3-39③）：同输入恒等 / 三项各篡改一
  字段变指纹（三条探针，与 G3-4(d) 同口径）/ 键序与字段声明序无关
  （canonical JSON sort_keys）/ 鸭子对象经 ``vars()`` 投影路径；
- **WakeupHookRegistry / enqueue_actor_wakeup**（§3.8 / D-P3-14 / §2.5 尾注）：
  注册校验（actor_id 字符串属性、同 actor 唯一）/ 双记录 (actor_id, due_tick)
  一致 / payload 仅 actor_id（reason 不入 payload）/ 稳定序 / 过去刻拒绝；
- **装配**（F2-06 / D-P3-23 / D-P3-26 / R4）：R1 写屏障负例（未武装环境 →
  ``SchedulerConfigurationError`` 且不构造执行器）/ 正例（武装态构造成功）/
  ``authority_policy`` / ``origin`` / ``named_triggers`` 缺参 → ``TypeError``
  （必填构造参数）/ 重复 trigger_id → 配置错误 / ``trigger_registry=None``
  缺省 = 空注册表；
- **权威接线**（D-P3-23 / §5.1）：closed-by-default 空 rules 下世界写入 →
  authority DENY（无 COMMITTED 事务、世界零变更、AUTHORITY_DECISION 诊断）/
  显式授予面 → ``set_world_variable`` 可提交；
- **run() 五 kind 分支**（§2.5 词表；本任务实现面）：``action_start``
  （预约开跑两跳复合 + pending 移除）/ ``action_checkpoint``（E-P3-40
  ``checkpoint_interval`` 透传 → 双刻推演 t=10 → cp@20 → t=20 → cp@30，
  §5.2 S4 / §5.3 A2；间隔 None → 不入队且 ``next_checkpoint_tick`` 置 None）/
  ``action_end``（到点且 ACTIVE → complete，completion_trigger 点名求值 →
  完成 effect 经 P2 管道提交，producer = 触发器声明 producer，D-P3-11）/
  ``deadline``（到点且 ACTIVE → fail_action("deadline_missed")）/
  ``event``（trigger_id 点名求值形态 + effects 显式形态；不可解析
  trigger_id → ``QueueInvariantError`` → 原子刻错误路径）；
- **D-P3-24 入口首检（未响应暂停幂等重报）**：∃ 玩家 INTERRUPTED 行动 +
  blocking 边界 → 返回同暂停（重入零副作用、时钟/队列不变、四空元组）；
  abort 后规则自动失效；非玩家 / 非 blocking / ``pause_on_player_boundary=
  False`` 三探针不重报；
- **D-P3-22 循环前播种**：scheduled 边界幂等补入 decision_boundary 停靠
  条目（boundary_id 去重；时钟推进过其刻后不重播）；
- **因果根（Leader 裁定 (C)）**：同刻批提交事务 ``cascade.causal_root_id``
  = 批首条 entry_id 字符串；
- **revalidation**（§3.9 / Leader 裁定 (F)，``_revalidate`` 委托
  ``revalidation.revalidate_proposal``）：is_stale → REJECT
  （F2-05 过期优先：valid_until_expired > stale_revision）/ actor_missing /
  actor_state_revision 仅诊断 / ACCEPT；submit_proposal REJECT 路径（FAILED
  终态记录 + 提案留 pending_proposals + 世界/队列零变更，A5 口径）；
- **接线点**（Leader 裁定 (B)/(C)）：decision_boundary 条目 = 时钟停靠点
  no-op（D-P3-22 播种，裁定 (C) 不动）；wakeup 条目经 ``_drain_wakeup``
  消费（T06 已接线，D-P3-14：无 hook → SYSTEM 诊断；hook → ``on_wakeup``
  求值 + 提案经 ``submit_proposal`` 全管道；hook 异常 →
  ``SchedulerWakeupError`` → 原子刻错误路径；actor_wakeups 记录随条目
  消费同步移除，F5-02）；
- **边界与聚合**：max_tick 批还队 + bounded 暂停 / step 单批强制暂停 /
  空队列 terminal / outcome 按调用聚合（D-P3-18）/ 原子刻错误路径
  （F2-03/D-P3-24④：刻前状态对 + 四空元组 + 非空 errors）。

披露（T04b 实现边界，Leader 裁定 (B)）：§6.1 中依赖**刻后边界求值**的探针
（边界 fired 记录 / trace 留痕 / 玩家边界中断行为 / ``pause_on_player_boundary=
False`` 的 fired 留痕面）属 T05 接线，本文件只覆盖 T04b 落地的机制面
（入口首检、播种、五 kind 分支、原子刻、聚合、装配、契约、指纹）；wakeup
hook 执行已由 T06 接线（D-P3-14），本文件 ``TestWakeupWiring`` /
``TestWakeupDrain`` 断言接线后行为（无 hook 诊断、全管道、错误路径、
reason 实参、记录移除、同刻序）。
§6.1 R1 负例的"新进程未武装环境"以 ``uninstall_write_barrier()`` 前置复原
达成（写屏障为进程全局态，P2 套件同款 autouse 隔离纪律，test_cascade.py
口径），断言时刻 ``write_barrier_installed() is False`` 与"未武装环境"等价。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.engine_v2.core.action_lifecycle import (
    IllegalTransitionError,
    LifecycleEvent,
)
from src.engine_v2.core.action_registry import (
    ActionRegistry,
    ActionSpec,
    DurationPolicy,
)
from src.engine_v2.core.actions import (
    ActionLifecycleStatus,
    ActionProposal,
    ActionTiming,
    ActionTypeId,
    ActiveAction,
)
from src.engine_v2.core.authority import (
    AuthorityPolicy,
    AuthorityRule,
    AuthoritySelector,
)
from src.engine_v2.core.cascade import CascadeTriggerRegistry, SyncTrigger
from src.engine_v2.core.clock import SchedulerError
from src.engine_v2.core.entity import ContractModel, EntityRecord
from src.engine_v2.core.effects import (
    ProposedEffect,
    StateDomainId,
    StateDomainTarget,
)
from src.engine_v2.core.event_queue import (
    QueueInvariantError,
    enqueue_scheduled_event,
    make_scheduled_event,
)
from src.engine_v2.core.ids import (
    ActionInstanceId,
    EntityId,
    EffectId,
    ProducerId,
)
from src.engine_v2.core.interrupt import (
    DecisionBoundary,
    InterruptCondition,
)
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.reducer import (
    EFFECT_SET_WORLD_VARIABLE,
    install_write_barrier,
    uninstall_write_barrier,
    write_barrier_installed,
)
from src.engine_v2.core.revision import RevalidationOutcome, Revision
from src.engine_v2.core.scheduler import (
    PauseReason,
    Scheduler,
    SchedulerConfigurationError,
    SchedulerOutcome,
    SchedulerWakeupError,
    TimePolicy,
    WakeupHook,
    WakeupHookRegistry,
    enqueue_actor_wakeup,
    scheduler_fingerprint,
)
from src.engine_v2.core.state import ActorWakeup, RuntimeState, WorldState
from src.engine_v2.core.trace import TraceKind
from src.engine_v2.core.transaction import TransactionStatus

# —— 共享常量（§5.1 Gate fixture 口径）——

_PLAYER = EntityId("player_1")
_NPC = EntityId("npc_1")
_ORIGIN_SCENARIO = ProducerId("origin_scenario")
#: Gate fixture origin（E-P3-34 / E-P3-40，Leader 裁定 (A)）
_ORIGIN_PROVENANCE = Provenance(
    producer_id=_ORIGIN_SCENARIO, origin=OriginKind.SCENARIO
)
_WALK = ActionTypeId("walk")
_WAIT = ActionTypeId("wait")
_WALK_EFFECT = ActionTypeId("walk_effect")


# —— 鸭子对象：DecisionBoundary（T05 交付，Leader 裁定 (B) 鸭子式属性读）——


class _Boundary:
    """DecisionBoundary 鸭子替身：T04b 机制面（_unanswered_pause /
    _seed_boundary_entries）只读 blocking/actor_id/boundary_id/kind/due_tick
    五属性；T05 刻后求值（interrupt.evaluate_boundaries）读全属性面
    （+condition/interrupt/reason）——替身按全表面给出，语义与真型一致。"""

    def __init__(
        self,
        boundary_id: str,
        actor_id: EntityId,
        *,
        kind: str = "scheduled",
        due_tick: int | None = None,
        condition: InterruptCondition | None = None,
        blocking: bool = False,
        interrupt: bool = True,
        reason: str | None = None,
    ) -> None:
        self.boundary_id = boundary_id
        self.actor_id = actor_id
        self.kind = kind
        self.due_tick = due_tick
        self.condition = condition
        self.blocking = blocking
        self.interrupt = interrupt
        self.reason = reason


# —— 构造辅助 ——


def _registry(*, with_effect_trigger: bool = False) -> ActionRegistry:
    """行动注册表：walk（固定 30 tick）/ wait（事件驱动无时长）；可选
    walk_effect（completion_trigger 点名 "t_complete"）。"""
    specs: dict[ActionTypeId, ActionSpec] = {
        _WALK: ActionSpec(
            action_id=_WALK,
            executor="sim.walk",
            duration_policy=DurationPolicy(kind="fixed", duration_ticks=30),
        ),
        _WAIT: ActionSpec(
            action_id=_WAIT,
            executor="sim.wait",
            duration_policy=DurationPolicy(kind="none"),
        ),
    }
    if with_effect_trigger:
        specs[_WALK_EFFECT] = ActionSpec(
            action_id=_WALK_EFFECT,
            executor="sim.walk",
            duration_policy=DurationPolicy(kind="fixed", duration_ticks=30),
            completion_trigger="t_complete",
        )
    return ActionRegistry(specs=specs)


def _allow_policy(writers: tuple[str, ...] = ("origin_scenario",)) -> AuthorityPolicy:
    """§5.1 型显式授予面（closed-by-default 下唯一放行路径）。"""
    return AuthorityPolicy(
        rules=[
            AuthorityRule(
                selector=AuthoritySelector(),
                allowed_writers=[ProducerId(w) for w in writers],
                priority=1,
                rule_id="allow_writers",
            )
        ]
    )


def _closed_policy() -> AuthorityPolicy:
    """空 rules（D-P2-09 closed-by-default：无匹配规则 → default DENY）。"""
    return AuthorityPolicy()


def _set_var_effect(
    key: str,
    value: object,
    *,
    source: str = "origin_scenario",
    base_revision: int = 0,
    effect_id: str = "eff_probe_001",
) -> ProposedEffect:
    """确定性世界变量 effect（core.set_world_variable，无组件依赖）。"""
    return ProposedEffect(
        effect_id=EffectId(effect_id),
        effect_type=EFFECT_SET_WORLD_VARIABLE,
        source=ProducerId(source),
        target=StateDomainTarget(domain=StateDomainId("world_variables")),
        payload={"key": key, "value": value},
        base_revision=Revision(base_revision),
        cause_ids=[],
    )


def _flag_trigger(trigger_id: str = "t_evt") -> SyncTrigger:
    """点名触发器 stub：产出单一世界变量 effect（producer = origin_scenario，
    D-P3-11：完成/事件 effect 的 producer = 触发器注册时声明的 producer）。"""
    return SyncTrigger(
        trigger_id,
        lambda events, state, depth: [
            _set_var_effect("flag", True, effect_id=f"eff_{trigger_id}_001")
        ],
    )


def _world() -> WorldState:
    return WorldState(
        entities={
            _PLAYER: EntityRecord(entity_id=_PLAYER),
            _NPC: EntityRecord(entity_id=_NPC),
        }
    )


def _proposal(
    action_id: ActionTypeId = _WALK,
    *,
    actor: EntityId = _PLAYER,
    base: int = 0,
    valid_until: int | None = None,
    timing: ActionTiming | None = None,
    state_rev: int | None = None,
    pid: str = "act_p1",
) -> ActionProposal:
    return ActionProposal(
        proposal_id=ActionInstanceId(pid),
        actor_id=actor,
        action_id=action_id,
        base_world_revision=Revision(base),
        timing=timing if timing is not None else ActionTiming(),
        valid_until=Revision(valid_until) if valid_until is not None else None,
        actor_state_revision=(
            Revision(state_rev) if state_rev is not None else None
        ),
        provenance=_ORIGIN_PROVENANCE,
    )


def _active(
    instance_id: str,
    actor_id: EntityId,
    status: ActionLifecycleStatus,
    *,
    start: int = 0,
    end: int | None = 30,
    action_id: ActionTypeId = _WALK,
) -> ActiveAction:
    return ActiveAction(
        instance_id=ActionInstanceId(instance_id),
        action_id=action_id,
        actor_id=actor_id,
        status=status,
        start_tick=start,
        expected_end_tick=end,
        interruptible=True,
        base_world_revision=Revision(0),
        provenance=_ORIGIN_PROVENANCE,
    )


def _scheduler(
    *,
    time_policy: TimePolicy | None = None,
    boundaries: tuple[_Boundary, ...] = (),
    named: tuple[tuple[str, SyncTrigger], ...] = (),
    policy: AuthorityPolicy | None = None,
    player_ids: tuple[EntityId, ...] = (),
    registry: ActionRegistry | None = None,
    trigger_registry: CascadeTriggerRegistry | None = None,
    assert_armed: bool = True,
    origin: Provenance | None = None,
) -> Scheduler:
    """正例装配：先武装写屏障（R1 正例路径），再构造。"""
    install_write_barrier()
    return Scheduler(
        registry if registry is not None else _registry(),
        authority_policy=policy if policy is not None else _allow_policy(),
        origin=origin if origin is not None else _ORIGIN_PROVENANCE,
        time_policy=time_policy if time_policy is not None else TimePolicy(),
        boundaries=boundaries,
        named_triggers=frozenset(named),
        player_actor_ids=frozenset(player_ids),
        trigger_registry=trigger_registry,
        assert_barrier_armed=assert_armed,
    )


@pytest.fixture(autouse=True)
def _barrier_isolation() -> None:
    """写屏障 opt-in 纪律（§2.6.2）：每用例前后全局复原，不跨文件受染
    （test_cascade.py 同款 autouse 口径）。"""
    uninstall_write_barrier()
    yield
    uninstall_write_barrier()


# —— 1. 契约模型（§3.8）——


class TestTimePolicyContract:
    def test_defaults(self) -> None:
        tp = TimePolicy()
        assert tp.fast_forward_enabled is True
        assert tp.checkpoint_interval_ticks is None
        assert tp.max_ticks_per_step is None
        assert tp.pause_on_player_boundary is True

    def test_checkpoint_interval_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TimePolicy(checkpoint_interval_ticks=0)

    def test_checkpoint_interval_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TimePolicy(checkpoint_interval_ticks=-1)

    def test_frozen(self) -> None:
        tp = TimePolicy()
        with pytest.raises(ValidationError):
            tp.checkpoint_interval_ticks = 5  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            TimePolicy(bogus_field=1)  # type: ignore[call-arg]


class TestPauseReasonContract:
    def test_minimal_fields(self) -> None:
        pr = PauseReason(kind="terminal", tick=12)
        assert pr.kind == "terminal"
        assert pr.boundary_id is None
        assert pr.tick == 12

    def test_missing_kind_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PauseReason(tick=12)  # type: ignore[call-arg]

    def test_missing_tick_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PauseReason(kind="terminal")  # type: ignore[call-arg]


class TestSchedulerOutcomeContract:
    def test_minimal_defaults(self) -> None:
        oc = SchedulerOutcome(paused=False, ticks_processed=0)
        assert oc.pause_reason is None
        assert oc.transactions == ()
        assert oc.events == ()
        assert oc.trace_records == ()
        assert oc.transitions == ()
        assert oc.errors == ()

    def test_missing_paused_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SchedulerOutcome(ticks_processed=0)  # type: ignore[call-arg]

    def test_missing_ticks_processed_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SchedulerOutcome(paused=True)  # type: ignore[call-arg]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            SchedulerOutcome(paused=True, ticks_processed=0, bogus=1)  # type: ignore[call-arg]


# —— 2. 确定性指纹（§3.8 / D-P3-15 / E-P3-39③）——


class TestSchedulerFingerprint:
    def test_deterministic(self) -> None:
        reg, tp = _registry(), TimePolicy(checkpoint_interval_ticks=10)
        bounds = (_Boundary("B1", _PLAYER, due_tick=12),)
        assert scheduler_fingerprint(reg, tp, bounds) == scheduler_fingerprint(
            reg, tp, bounds
        )

    def test_sha256_hex_digest(self) -> None:
        fp = scheduler_fingerprint(_registry(), TimePolicy(), ())
        assert len(fp) == 64
        int(fp, 16)  # 纯 hex

    def test_registry_tamper_changes_fingerprint(self) -> None:
        """三项各篡改一字段变指纹——探针 1：registry（walk 时长 30→31）。"""
        tp, bounds = TimePolicy(), ()
        reg_a = _registry()
        reg_b = ActionRegistry(
            specs={
                _WALK: ActionSpec(
                    action_id=_WALK,
                    executor="sim.walk",
                    duration_policy=DurationPolicy(kind="fixed", duration_ticks=31),
                )
            }
        )
        assert scheduler_fingerprint(reg_a, tp, bounds) != scheduler_fingerprint(
            reg_b, tp, bounds
        )

    def test_time_policy_tamper_changes_fingerprint(self) -> None:
        """探针 2：time_policy（间隔 10→20）。"""
        reg, bounds = _registry(), ()
        assert (
            scheduler_fingerprint(reg, TimePolicy(checkpoint_interval_ticks=10), bounds)
            != scheduler_fingerprint(reg, TimePolicy(checkpoint_interval_ticks=20), bounds)
        )

    def test_boundary_tamper_changes_fingerprint(self) -> None:
        """探针 3：boundaries（B1 刻 12→13）。"""
        reg, tp = _registry(), TimePolicy()
        bounds_a = (_Boundary("B1", _PLAYER, due_tick=12),)
        bounds_b = (_Boundary("B1", _PLAYER, due_tick=13),)
        assert scheduler_fingerprint(reg, tp, bounds_a) != scheduler_fingerprint(
            reg, tp, bounds_b
        )

    def test_duck_key_order_independence(self) -> None:
        """鸭子对象 vars() 插入序不同 → 同指纹（canonical JSON 键排序，
        sort_keys=True 的键序稳定性）。"""

        class _DuckA:
            def __init__(self) -> None:
                self.boundary_id = "B1"
                self.actor_id = "player_1"

        class _DuckB:
            def __init__(self) -> None:
                self.actor_id = "player_1"
                self.boundary_id = "B1"

        reg, tp = _registry(), TimePolicy()
        assert (
            scheduler_fingerprint(reg, tp, (_DuckA(),))
            == scheduler_fingerprint(reg, tp, (_DuckB(),))
        )

    def test_model_field_order_independence(self) -> None:
        """Pydantic 模型字段声明序不同、同值 → 同指纹（model_fields 序投影
        后由 sort_keys 归一）。"""

        class _ModelA(ContractModel):
            b: int = 1
            a: str = "x"

        class _ModelB(ContractModel):
            a: str = "x"
            b: int = 1

        reg, tp = _registry(), TimePolicy()
        assert (
            scheduler_fingerprint(reg, tp, (_ModelA(),))
            == scheduler_fingerprint(reg, tp, (_ModelB(),))
        )

    def test_mapping_boundary_supported(self) -> None:
        """Mapping 分支：dict 边界经按键投影（值递归）后入指纹。"""
        reg, tp = _registry(), TimePolicy()
        fp = scheduler_fingerprint(
            reg, tp, ({"boundary_id": "B1", "actor_id": "player_1"},)
        )
        assert len(fp) == 64


# —— 3. WakeupHookRegistry / enqueue_actor_wakeup（§3.8 / D-P3-14）——


class _Hook:
    """WakeupHook 鸭子替身（注册键 = actor_id 字符串属性）。"""

    def __init__(self, actor_id: str | None) -> None:
        self.actor_id = actor_id
        self.calls: list[tuple[object, ...]] = []

    def on_wakeup(self, actor_id: EntityId, view: object, clock: object, reason: str | None) -> list:
        self.calls.append((actor_id, view, clock, reason))
        return []


class TestWakeupHookRegistry:
    def test_register_and_lookup(self) -> None:
        reg = WakeupHookRegistry()
        hook = _Hook("player_1")
        reg.register(hook)
        assert reg.hook_for(_PLAYER) is hook
        assert reg.hook_for(_NPC) is None

    def test_missing_actor_id_rejected(self) -> None:
        reg = WakeupHookRegistry()
        with pytest.raises(SchedulerConfigurationError):
            reg.register(_Hook(None))

    def test_empty_actor_id_rejected(self) -> None:
        reg = WakeupHookRegistry()
        with pytest.raises(SchedulerConfigurationError):
            reg.register(_Hook(""))

    def test_missing_actor_attr_rejected(self) -> None:
        reg = WakeupHookRegistry()
        with pytest.raises(SchedulerConfigurationError):
            reg.register(object())  # type: ignore[arg-type]

    def test_duplicate_actor_rejected(self) -> None:
        reg = WakeupHookRegistry()
        reg.register(_Hook("player_1"))
        with pytest.raises(SchedulerConfigurationError):
            reg.register(_Hook("player_1"))


class TestEnqueueActorWakeup:
    def test_dual_records_consistent(self) -> None:
        """双记录 (actor_id, due_tick) 一致；payload 仅 actor_id（reason 不入
        payload，§2.5 尾注口径）。"""
        rt = RuntimeState(logical_tick=0)
        new_rt = enqueue_actor_wakeup(rt, _PLAYER, 12, reason="woken")
        assert new_rt.actor_wakeups == [
            ActorWakeup(actor_id=_PLAYER, due_tick=12, reason="woken")
        ]
        entry = new_rt.scheduler_queue[0]
        assert entry.kind == "wakeup"
        assert entry.due_tick == 12
        assert entry.payload == {"actor_id": "player_1"}
        assert "reason" not in entry.payload

    def test_stable_sort_by_due_tick(self) -> None:
        rt = RuntimeState(logical_tick=0)
        rt = enqueue_actor_wakeup(rt, _PLAYER, 30)
        rt = enqueue_actor_wakeup(rt, _NPC, 5)
        assert [w.due_tick for w in rt.actor_wakeups] == [5, 30]
        assert [e.due_tick for e in rt.scheduler_queue] == [5, 30]

    def test_past_due_rejected(self) -> None:
        rt = RuntimeState(logical_tick=10)
        with pytest.raises(QueueInvariantError):
            enqueue_actor_wakeup(rt, _PLAYER, 5)

    def test_pure_function(self) -> None:
        rt = RuntimeState(logical_tick=0)
        before = (rt.actor_wakeups, rt.scheduler_queue)
        enqueue_actor_wakeup(rt, _PLAYER, 12)
        assert (rt.actor_wakeups, rt.scheduler_queue) == before


# —— 4. 装配（F2-06 / D-P3-23 / D-P3-26 / R4）——


class TestSchedulerAssembly:
    def test_r1_negative_unarmed_no_executor(self) -> None:
        """R1 负例（§6.1）：未武装环境（断言时刻前置条件成立）→
        SchedulerConfigurationError，且 __init__ 第一步检查先于执行器构造
        ——未武装不构造执行器（屏障保持未武装 = 构造未发生的可观察证据）。"""
        assert write_barrier_installed() is False  # autouse 复原保证
        with pytest.raises(SchedulerConfigurationError):
            Scheduler(
                _registry(),
                authority_policy=_allow_policy(),
                origin=_ORIGIN_PROVENANCE,
                named_triggers=frozenset(),
            )
        # CascadeExecutor.__init__ 会幂等武装屏障——若执行器被构造，此处必 True
        assert write_barrier_installed() is False

    def test_r1_positive_armed(self) -> None:
        """R1 正例：预武装后构造成功，武装态保持。"""
        install_write_barrier()
        assert write_barrier_installed() is True
        scheduler = Scheduler(
            _registry(),
            authority_policy=_allow_policy(),
            origin=_ORIGIN_PROVENANCE,
            named_triggers=frozenset(),
        )
        assert write_barrier_installed() is True
        assert scheduler is not None

    def test_assert_barrier_armed_false_skips_check(self) -> None:
        """显式放弃 R1 断言：未武装环境构造成功（执行器构造副作用武装屏障）。"""
        assert write_barrier_installed() is False
        Scheduler(
            _registry(),
            authority_policy=_allow_policy(),
            origin=_ORIGIN_PROVENANCE,
            named_triggers=frozenset(),
            assert_barrier_armed=False,
        )
        assert write_barrier_installed() is True

    def test_missing_authority_policy_typeerror(self) -> None:
        install_write_barrier()
        with pytest.raises(TypeError):
            Scheduler(  # type: ignore[call-arg]
                _registry(),
                origin=_ORIGIN_PROVENANCE,
                named_triggers=frozenset(),
            )

    def test_missing_origin_typeerror(self) -> None:
        install_write_barrier()
        with pytest.raises(TypeError):
            Scheduler(  # type: ignore[call-arg]
                _registry(),
                authority_policy=_allow_policy(),
                named_triggers=frozenset(),
            )

    def test_missing_named_triggers_typeerror(self) -> None:
        install_write_barrier()
        with pytest.raises(TypeError):
            Scheduler(  # type: ignore[call-arg]
                _registry(),
                authority_policy=_allow_policy(),
                origin=_ORIGIN_PROVENANCE,
            )

    def test_duplicate_trigger_id_rejected(self) -> None:
        """D-P3-26 / K7：同键异触发器 → 构造点拒绝（不静默覆盖）。"""
        install_write_barrier()
        with pytest.raises(SchedulerConfigurationError):
            Scheduler(
                _registry(),
                authority_policy=_allow_policy(),
                origin=_ORIGIN_PROVENANCE,
                named_triggers=frozenset(
                    {("t_x", _flag_trigger("t_x")), ("t_x", _flag_trigger("t_x"))}
                ),
            )

    def test_trigger_registry_none_default(self) -> None:
        """D-P3-27 / R5：trigger_registry=None 缺省 = 空注册表——构造成功、
        点名求值正常（named_triggers 为唯一数据来源）。"""
        s = _scheduler(named=(("t_evt", _flag_trigger()),))
        world, rt = _world(), RuntimeState(logical_tick=0)
        entry = make_scheduled_event("event", 5, payload={"trigger_id": "t_evt"})
        rt = enqueue_scheduled_event(rt, entry)
        world2, rt2, oc = s.fast_forward(world, rt)
        assert world2.world_variables == {"flag": True}
        assert len(oc.transactions) == 1


# —— 5. 权威接线（D-P3-23 / §5.1）——


class TestAuthorityWiring:
    def test_closed_by_default_denies_world_write(self) -> None:
        """空 rules（closed-by-default）：事件 effect 在 authority 阶段 DENY
        ——无 COMMITTED 事务、世界零变更、诊断可查（AUTHORITY_DECISION）。"""
        s = _scheduler(policy=_closed_policy(), named=(("t_evt", _flag_trigger()),))
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_scheduled_event(
            rt, make_scheduled_event("event", 5, payload={"trigger_id": "t_evt"})
        )
        world2, rt2, oc = s.fast_forward(world, rt)
        assert world2 == world  # 世界零变更
        assert world2.world_variables == {}
        committed = [tx for tx in oc.transactions if tx.status is TransactionStatus.COMMITTED]
        assert committed == []
        deny_traces = [
            r
            for r in oc.trace_records
            if r.kind is TraceKind.AUTHORITY_DECISION
            and r.payload.get("decision") == "deny"
        ]
        assert deny_traces, "authority DENY 诊断须可查（AUTHORITY_DECISION trace）"

    def test_explicit_grant_allows_commit(self) -> None:
        """§5.1 型显式授予面：set_world_variable 可提交（txn + event + 世界变更）。"""
        s = _scheduler(named=(("t_evt", _flag_trigger()),))
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_scheduled_event(
            rt, make_scheduled_event("event", 5, payload={"trigger_id": "t_evt"})
        )
        world2, rt2, oc = s.fast_forward(world, rt)
        assert world2.world_variables == {"flag": True}
        assert world2.world_revision == 1
        assert len(oc.transactions) == 1
        assert oc.transactions[0].status is TransactionStatus.COMMITTED
        assert len(oc.events) == 1


# —— 6. run() 五 kind 分支 ——


class TestActionStartBranch:
    def test_immediate_start_on_submit(self) -> None:
        """timing 无 earliest（已到当刻）→ submit 侧立即 start_action 两跳复合
        （PROPOSED→VALIDATING→ACTIVE），成功移出 pending_proposals（F2-12）。"""
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        world2, rt2, decision = s.submit_proposal(world, rt, _proposal())
        assert decision.outcome is RevalidationOutcome.ACCEPT
        action = rt2.active_actions["act_p1"]
        assert action.status is ActionLifecycleStatus.ACTIVE
        assert action.start_tick == 0
        assert action.expected_end_tick == 30
        assert rt2.pending_proposals == []  # F2-12：成功移出
        kinds = [e.kind for e in rt2.scheduler_queue]
        assert kinds == ["action_end"]
        assert rt2.scheduler_queue[0].due_tick == 30

    def test_reserved_start_then_fast_forward(self) -> None:
        """earliest_start_tick 未到 → PROPOSED 记录 + pending + 预约
        action_start 条目；ff 到点 → 两跳复合 start（2 条复合记录**不入**
        ff outcome，D-P3-18/19——观察出口仅模块级 start_action 直调，F2-16），
        pending 移除，start_tick = 开跑刻。"""
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        world2, rt2, _decision = s.submit_proposal(
            world, rt, _proposal(timing=ActionTiming(earliest_start_tick=15))
        )
        assert rt2.active_actions["act_p1"].status is ActionLifecycleStatus.PROPOSED
        assert rt2.pending_proposals == [_proposal(timing=ActionTiming(earliest_start_tick=15))]
        assert [e.kind for e in rt2.scheduler_queue] == ["action_start"]
        assert rt2.scheduler_queue[0].due_tick == 15

        world3, rt3, oc = s.fast_forward(world2, rt2)
        action = rt3.active_actions["act_p1"]
        assert action.status is ActionLifecycleStatus.COMPLETED
        assert action.start_tick == 15
        assert action.expected_end_tick == 45
        assert rt3.pending_proposals == []
        # D-P3-18/19：start 的两跳复合记录不属于本调用作用域 outcome；
        # 批内可见迁移仅 end@45 的 COMPLETED（complete_action 返回记录）
        assert [t.event for t in oc.transitions] == [LifecycleEvent.COMPLETED]
        assert oc.transitions[0].at_tick == 45
        # end@45 后队列耗尽 → terminal
        assert rt3.scheduler_queue == []
        assert oc.pause_reason == PauseReason(kind="terminal", tick=45)

    def test_reserved_start_terminal_after_end(self) -> None:
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        _, rt, _ = s.submit_proposal(
            world, rt, _proposal(timing=ActionTiming(earliest_start_tick=5))
        )
        world2, rt2, oc = s.fast_forward(world, rt)
        assert rt2.active_actions["act_p1"].status is ActionLifecycleStatus.COMPLETED
        assert rt2.scheduler_queue == []
        assert oc.pause_reason == PauseReason(kind="terminal", tick=35)


class TestActionCheckpointBranch:
    def test_dual_tick_derivation_interval_passthrough(self) -> None:
        """E-P3-40 间隔透传 + §5.2 S4 / §5.3 A2 双刻推演：start@0、间隔 10 →
        cp@10 处理 → 下一 cp 入队 @20（next_checkpoint_tick 镜像）→ cp@20
        处理 → 下一 cp @30。逐刻断言（max_tick 边界停靠）。"""
        s = _scheduler(time_policy=TimePolicy(checkpoint_interval_ticks=10))
        world, rt = _world(), RuntimeState(logical_tick=0)
        _, rt, _ = s.submit_proposal(world, rt, _proposal())
        action = rt.active_actions["act_p1"]
        assert action.next_checkpoint_tick == 10
        assert [e.kind for e in rt.scheduler_queue] == ["action_checkpoint", "action_end"]

        # 第一刻：t=10 checkpoint → 下一 cp 入队 t=20
        _, rt1, oc1 = s.fast_forward(world, rt, max_tick=10)
        assert oc1.pause_reason == PauseReason(kind="bounded", tick=10)
        assert rt1.active_actions["act_p1"].next_checkpoint_tick == 20
        cp_entries = [
            (e.kind, e.due_tick) for e in rt1.scheduler_queue
            if e.kind == "action_checkpoint"
        ]
        assert cp_entries == [("action_checkpoint", 20)]
        # progress 镜像（D-P3-08）：(10-0)/(30-0)
        assert rt1.active_actions["act_p1"].progress == pytest.approx(10 / 30)

        # 第二刻：t=20 checkpoint → 下一 cp 入队 t=30
        _, rt2, oc2 = s.fast_forward(world, rt1, max_tick=20)
        assert oc2.pause_reason == PauseReason(kind="bounded", tick=20)
        assert rt2.active_actions["act_p1"].next_checkpoint_tick == 30
        assert rt2.active_actions["act_p1"].progress == pytest.approx(20 / 30)
        assert [
            (e.kind, e.due_tick) for e in rt2.scheduler_queue
            if e.kind == "action_checkpoint"
        ] == [("action_checkpoint", 30)]

        # 收尾：t=30 同刻批 [cp@30, end@30]（稳定 FIFO）→ cp 入队 cp@40 →
        # end COMPLETED 剪除 cp@40（D-P3-25①）→ terminal
        _, rt3, oc3 = s.fast_forward(world, rt2)
        assert rt3.active_actions["act_p1"].status is ActionLifecycleStatus.COMPLETED
        assert rt3.scheduler_queue == []
        assert oc3.pause_reason == PauseReason(kind="terminal", tick=30)
        assert [t.event for t in oc3.transitions] == [LifecycleEvent.COMPLETED]

    def test_interval_none_no_checkpoint_entry(self) -> None:
        """间隔 None（缺省 TimePolicy）：不入队 checkpoint 条目且
        next_checkpoint_tick 为 None。"""
        s = _scheduler()  # TimePolicy() 缺省 checkpoint_interval_ticks=None
        world, rt = _world(), RuntimeState(logical_tick=0)
        _, rt, _ = s.submit_proposal(world, rt, _proposal())
        assert rt.active_actions["act_p1"].next_checkpoint_tick is None
        assert [e.kind for e in rt.scheduler_queue] == ["action_end"]
        _, rt2, oc = s.fast_forward(world, rt)
        assert rt2.active_actions["act_p1"].status is ActionLifecycleStatus.COMPLETED
        assert oc.transitions and oc.transitions[0].event is LifecycleEvent.COMPLETED

    def test_checkpoint_on_interrupted_is_noop_with_diagnostic(self) -> None:
        """非 ACTIVE 守卫（F2-02 第二道防线）：INTERRUPTED 实例的 checkpoint
        条目 → 不查迁移表、不入队下一 cp、返回诊断 TraceRecord（SYSTEM，
        checkpoint_skipped_interrupted）。"""
        s = _scheduler(time_policy=TimePolicy(checkpoint_interval_ticks=10))
        world = _world()
        rt = RuntimeState(
            logical_tick=0,
            active_actions={"act_x": _active("act_x", _PLAYER, ActionLifecycleStatus.INTERRUPTED)},
        )
        rt = enqueue_scheduled_event(
            rt, make_scheduled_event("action_checkpoint", 10, payload={"instance_id": "act_x"})
        )
        _, rt2, oc = s.fast_forward(world, rt)
        assert rt2.active_actions["act_x"].status is ActionLifecycleStatus.INTERRUPTED
        assert rt2.scheduler_queue == []  # 条目消费，未补入下一 cp
        assert rt2.active_actions["act_x"].next_checkpoint_tick is None
        assert len(oc.trace_records) == 1
        record = oc.trace_records[0]
        assert record.kind is TraceKind.SYSTEM
        assert "checkpoint_skipped_interrupted" in str(record.payload)


class TestActionEndBranch:
    def test_end_completes_without_trigger(self) -> None:
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        _, rt, _ = s.submit_proposal(world, rt, _proposal())
        world2, rt2, oc = s.fast_forward(world, rt)
        assert rt2.active_actions["act_p1"].status is ActionLifecycleStatus.COMPLETED
        assert rt2.scheduler_queue == []
        assert world2 == world  # 无完成 effect → 世界零变更
        assert oc.transactions == ()
        assert [t.event for t in oc.transitions] == [LifecycleEvent.COMPLETED]
        assert oc.transitions[0].at_tick == 30

    def test_end_completion_trigger_commits_effect(self) -> None:
        """completion_trigger 点名求值（D-P3-26）→ 完成 effect 经 P2 管道提交；
        producer = 触发器声明 producer（D-P3-11：不引用 spec.executor）。"""
        complete = SyncTrigger(
            "t_complete",
            lambda events, state, depth: [
                _set_var_effect("arrived", True, effect_id="eff_complete_001")
            ],
        )
        s = _scheduler(
            registry=_registry(with_effect_trigger=True),
            named=(("t_complete", complete),),
        )
        world, rt = _world(), RuntimeState(logical_tick=0)
        _, rt, _ = s.submit_proposal(world, rt, _proposal(action_id=_WALK_EFFECT))
        world2, rt2, oc = s.fast_forward(world, rt)
        assert rt2.active_actions["act_p1"].status is ActionLifecycleStatus.COMPLETED
        assert world2.world_variables == {"arrived": True}
        assert world2.world_revision == 1
        assert len(oc.transactions) == 1
        txn = oc.transactions[0]
        assert txn.status is TransactionStatus.COMMITTED
        # producer 口径：effect source = origin_scenario（触发器声明，非 executor）
        assert txn.effects[0].effect.source == _ORIGIN_SCENARIO
        # 剪除（D-P3-25①）：终态迁移剪掉该实例剩余条目
        assert rt2.scheduler_queue == []


class TestDeadlineBranch:
    def test_deadline_fails_active_action(self) -> None:
        """kind="deadline"（§2.5 词表）：到点且 ACTIVE → fail_action
        ("deadline_missed") → FAILED 终态。fail_action 签名仅返回 RuntimeState
        （不产出 LifecycleTransition 记录）→ outcome.transitions 恒空，FAILED
        终态经 ActiveAction 记录观察（簿记型，同 checkpoint 分支口径）。"""
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        _, rt, _ = s.submit_proposal(
            world, rt, _proposal(action_id=_WAIT, timing=ActionTiming(deadline_tick=25))
        )
        # wait 无时长 → 队列仅 deadline@25
        assert [e.kind for e in rt.scheduler_queue] == ["deadline"]
        assert rt.scheduler_queue[0].due_tick == 25
        assert rt.active_actions["act_p1"].expected_end_tick is None

        world2, rt2, oc = s.fast_forward(world, rt)
        action = rt2.active_actions["act_p1"]
        assert action.status is ActionLifecycleStatus.FAILED
        assert action.result_summary == {"reason": "deadline_missed", "tick": 25}
        assert rt2.scheduler_queue == []
        assert oc.transitions == ()
        assert oc.pause_reason == PauseReason(kind="terminal", tick=25)


class TestEventBranch:
    def test_trigger_id_form_commits(self) -> None:
        """trigger_id 形态：named_triggers 点名求值 → effect 经管道提交。"""
        s = _scheduler(named=(("t_evt", _flag_trigger()),))
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_scheduled_event(
            rt, make_scheduled_event("event", 5, payload={"trigger_id": "t_evt"})
        )
        world2, rt2, oc = s.fast_forward(world, rt)
        assert world2.world_variables == {"flag": True}
        assert world2.world_revision == 1
        assert len(oc.transactions) == 1
        assert oc.transactions[0].status is TransactionStatus.COMMITTED
        assert len(oc.events) == 1
        assert rt2.scheduler_queue == []

    def test_effects_form_commits(self) -> None:
        """effects 形态：payload 显式 ProposedEffect JSON 批 → 提交。"""
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_scheduled_event(
            rt,
            make_scheduled_event(
                "event",
                5,
                payload={
                    "effects": [_set_var_effect("x", 1, effect_id="eff_fx_001").model_dump(mode="json")],
                    "producer": "origin_scenario",
                },
            ),
        )
        world2, rt2, oc = s.fast_forward(world, rt)
        assert world2.world_variables == {"x": 1}
        assert len(oc.transactions) == 1

    def test_trigger_id_unresolvable_raises_queue_invariant(self) -> None:
        """空命名映射 + trigger_id 形态 → QueueInvariantError（构造点外，
        分支内检查）。"""
        s = _scheduler(named=())
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_scheduled_event(
            rt, make_scheduled_event("event", 5, payload={"trigger_id": "t_missing"})
        )
        world2, rt2, oc = s.fast_forward(world, rt)
        # 原子刻错误路径（F2-03）：刻前状态对 + 非空 errors
        assert world2 is world
        assert oc.paused is False
        assert oc.pause_reason is None
        assert oc.ticks_processed == 0
        assert oc.transactions == () and oc.events == ()
        assert oc.transitions == () and oc.trace_records == ()
        assert len(oc.errors) == 1
        assert "trigger_id 不可解析" in oc.errors[0]

    def test_same_tick_trigger_sees_prior_events(self) -> None:
        """同刻批事件流（批内 FIFO）：后到的 trigger_id 条目求值时可见先
        提交条目本刻产生的事件（tick_events 统一维护）。"""
        s = _scheduler(
            named=(
                (
                    "t_cond",
                    SyncTrigger(
                        "t_cond",
                        lambda events, state, depth: (
                            [
                                _set_var_effect(
                                    "chain",
                                    len(events),
                                    effect_id="eff_chain_001",
                                    base_revision=1,
                                )
                            ]
                            if events
                            else []
                        ),
                    ),
                ),
            )
        )
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_scheduled_event(
            rt,
            make_scheduled_event(
                "event",
                5,
                payload={
                    "effects": [_set_var_effect("first", 1, effect_id="eff_first_001").model_dump(mode="json")]
                },
            ),
        )
        rt = enqueue_scheduled_event(
            rt, make_scheduled_event("event", 5, payload={"trigger_id": "t_cond"})
        )
        world2, rt2, oc = s.fast_forward(world, rt)
        # 触发器看到 1 个本刻事件 → chain=1 提交成功（若事件流断裂 → 无提交）
        assert world2.world_variables == {"first": 1, "chain": 1}
        assert len(oc.transactions) == 2


# —— 7. 因果根（Leader 裁定 (C)）——


class TestCausalRoot:
    def test_causal_root_is_first_batch_entry(self) -> None:
        """同刻批两条 event 条目（显式 entry_id sch_a 先于 sch_b）：两条
        提交事务的 cascade.causal_root_id 均为批首条 entry_id 字符串 "sch_a"。"""
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_scheduled_event(
            rt,
            make_scheduled_event(
                "event",
                5,
                payload={
                    "effects": [_set_var_effect("a", 1, effect_id="eff_root_001").model_dump(mode="json")]
                },
                entry_id="sch_a",
            ),
        )
        rt = enqueue_scheduled_event(
            rt,
            make_scheduled_event(
                "event",
                5,
                payload={
                    "effects": [
                        _set_var_effect(
                            "b", 2, effect_id="eff_root_002", base_revision=1
                        ).model_dump(mode="json")
                    ],
                },
                entry_id="sch_b",
            ),
        )
        world2, rt2, oc = s.fast_forward(world, rt)
        assert len(oc.transactions) == 2
        for txn in oc.transactions:
            assert txn.cascade is not None
            assert txn.cascade.causal_root_id == "sch_a"
        # origin 口径（Leader 裁定 (A)）：全部提交统一 origin_scenario
        assert all(txn.provenance == _ORIGIN_PROVENANCE for txn in oc.transactions)


# —— 8. D-P3-24 入口首检（未响应暂停幂等重报）——


class TestUnansweredPause:
    def _interrupted_runtime(self) -> RuntimeState:
        return RuntimeState(
            logical_tick=12,
            active_actions={
                "act_1": _active("act_1", _PLAYER, ActionLifecycleStatus.INTERRUPTED, start=0)
            },
        )

    def test_idempotent_re_report_zero_side_effects(self) -> None:
        """首次 ff 与重入 ff 返回同一暂停（同 boundary_id / tick）；入口首检
        纯派生、重入零副作用（世界/运行时同一对象、四空元组）。"""
        s = _scheduler(
            boundaries=(_Boundary("B1", _PLAYER, blocking=True),),
            player_ids=(_PLAYER,),
        )
        world, rt = _world(), self._interrupted_runtime()
        world1, rt1, oc1 = s.fast_forward(world, rt)
        assert world1 is world
        assert rt1 is rt
        assert oc1.paused is True
        assert oc1.pause_reason == PauseReason(
            kind="decision_boundary", boundary_id="B1", tick=12
        )
        assert oc1.ticks_processed == 12
        assert oc1.transactions == () and oc1.events == ()
        assert oc1.transitions == () and oc1.errors == ()

        # 重入：同一暂停
        world2, rt2, oc2 = s.fast_forward(world1, rt1)
        assert world2 is world
        assert rt2 is rt
        assert oc2 == oc1

    def test_abort_invalidates_rule(self) -> None:
        """显式 abort（status 离开 INTERRUPTED）→ 规则自动失效，后续 ff
        正常推进（空队列 → terminal）。"""
        s = _scheduler(
            boundaries=(_Boundary("B1", _PLAYER, blocking=True),),
            player_ids=(_PLAYER,),
        )
        world, rt = _world(), self._interrupted_runtime()
        _, _, oc1 = s.fast_forward(world, rt)
        assert oc1.paused is True
        runtime2 = s.abort_action(world, rt, ActionInstanceId("act_1"))
        # ABORTED 是 LifecycleEvent 而非状态：INTERRUPTED --ABORTED--> FAILED
        assert runtime2.active_actions["act_1"].status is ActionLifecycleStatus.FAILED
        _, _, oc2 = s.fast_forward(world, runtime2)
        assert oc2.paused is False
        assert oc2.pause_reason == PauseReason(kind="terminal", tick=12)

    def test_resume_invalidates_rule(self) -> None:
        s = _scheduler(
            boundaries=(_Boundary("B1", _PLAYER, blocking=True),),
            player_ids=(_PLAYER,),
        )
        world, rt = _world(), self._interrupted_runtime()
        _, _, oc1 = s.fast_forward(world, rt)
        assert oc1.paused is True
        world2, rt2, _transition = s.resume_action(world, rt, ActionInstanceId("act_1"))
        assert rt2.active_actions["act_1"].status is ActionLifecycleStatus.ACTIVE
        _, _, oc2 = s.fast_forward(world2, rt2)
        assert oc2.paused is False

    def test_first_hit_in_registration_order(self) -> None:
        """多边界命中 → 按注册序首个命中边界（boundary_id 重新推导）。"""
        s = _scheduler(
            boundaries=(
                _Boundary("B2", _NPC, blocking=True),
                _Boundary("B1", _PLAYER, blocking=True),
                _Boundary("B3", _PLAYER, blocking=True),
            ),
            player_ids=(_PLAYER,),
        )
        world, rt = _world(), self._interrupted_runtime()
        _, _, oc = s.fast_forward(world, rt)
        assert oc.pause_reason == PauseReason(
            kind="decision_boundary", boundary_id="B1", tick=12
        )

    def test_non_player_actor_not_re_reported(self) -> None:
        """玩家集合外 actor 的 INTERRUPTED 行动 → 不重报（NPC 边界中断语义
        属 T05 刻后求值；入口首检只辖玩家）。"""
        s = _scheduler(
            boundaries=(_Boundary("B1", _NPC, blocking=True),),
            player_ids=(_PLAYER,),
        )
        world, rt = _world(), RuntimeState(
            logical_tick=12,
            active_actions={
                "act_1": _active("act_1", _NPC, ActionLifecycleStatus.INTERRUPTED, start=0)
            },
        )
        _, _, oc = s.fast_forward(world, rt)
        assert oc.paused is False
        assert oc.pause_reason == PauseReason(kind="terminal", tick=12)

    def test_non_blocking_boundary_not_re_reported(self) -> None:
        s = _scheduler(
            boundaries=(_Boundary("B1", _PLAYER, blocking=False),),
            player_ids=(_PLAYER,),
        )
        world, rt = _world(), self._interrupted_runtime()
        _, _, oc = s.fast_forward(world, rt)
        assert oc.paused is False

    def test_pause_on_player_boundary_false_disables_rule(self) -> None:
        """R5/F4-03 前置：pause_on_player_boundary=False → 重报规则不生效。"""
        s = _scheduler(
            time_policy=TimePolicy(pause_on_player_boundary=False),
            boundaries=(_Boundary("B1", _PLAYER, blocking=True),),
            player_ids=(_PLAYER,),
        )
        world, rt = _world(), self._interrupted_runtime()
        _, _, oc = s.fast_forward(world, rt)
        assert oc.paused is False

    def test_precheck_takes_precedence_over_terminal(self) -> None:
        """空队列 + 未响应暂停 → 返回暂停而非 terminal（入口首检先于取批）。"""
        s = _scheduler(
            boundaries=(_Boundary("B1", _PLAYER, blocking=True),),
            player_ids=(_PLAYER,),
        )
        world, rt = _world(), self._interrupted_runtime()
        assert rt.scheduler_queue == []
        _, _, oc = s.fast_forward(world, rt)
        assert oc.paused is True
        assert oc.pause_reason is not None
        assert oc.pause_reason.kind == "decision_boundary"


# —— 9. D-P3-22 循环前播种 + T05 接线点现状 ——


class TestSeedBoundaryEntries:
    def test_scheduled_boundary_seeded_and_clock_stops(self) -> None:
        """scheduled 边界（due_tick > 当前刻）→ 循环前补入 decision_boundary
        停靠条目（payload {boundary_id, actor_id}）；时钟停在其刻（条目本身
        no-op——fired 判定属 T05 刻后求值）。"""
        s = _scheduler(
            boundaries=(_Boundary("B1", _PLAYER, kind="scheduled", due_tick=12),)
        )
        world, rt = _world(), RuntimeState(logical_tick=0)
        world2, rt2, oc = s.fast_forward(world, rt)
        assert rt2.logical_tick == 12
        assert rt2.scheduler_queue == []  # 停靠条目已消费
        assert world2 == world
        assert oc.ticks_processed == 12
        assert oc.pause_reason == PauseReason(kind="terminal", tick=12)

    def test_seed_payload_contract(self) -> None:
        """停靠条目 payload = {boundary_id, actor_id}（§2.5 表）。"""
        s = _scheduler(
            boundaries=(_Boundary("B7", _NPC, kind="scheduled", due_tick=5),)
        )
        world, rt = _world(), RuntimeState(logical_tick=0)
        # max_tick=4：播种后批 due 5 > 4 → 批还队、bounded 暂停——队列保留，
        # 可观察播种产物
        _, rt1, oc = s.fast_forward(world, rt, max_tick=4)
        assert oc.pause_reason == PauseReason(kind="bounded", tick=0)
        entry = rt1.scheduler_queue[0]
        assert entry.kind == "decision_boundary"
        assert entry.due_tick == 5
        assert entry.payload == {"boundary_id": "B7", "actor_id": "npc_1"}

    def test_seed_idempotent_while_queued(self) -> None:
        """边界去重：条目仍在队列（max_tick 还队）时重复 ff 不重复补入。"""
        s = _scheduler(
            boundaries=(_Boundary("B7", _NPC, kind="scheduled", due_tick=5),)
        )
        world, rt = _world(), RuntimeState(logical_tick=0)
        _, rt1, _ = s.fast_forward(world, rt, max_tick=4)
        _, rt2, _ = s.fast_forward(world, rt1, max_tick=4)
        boundary_entries = [
            e for e in rt2.scheduler_queue if e.kind == "decision_boundary"
        ]
        assert len(boundary_entries) == 1

    def test_no_reseed_after_clock_passes(self) -> None:
        """时钟推进过边界刻后（due_tick <= logical_tick）→ 不重播（幂等终点
        语义：重复 ff 不再产生停靠条目）。"""
        s = _scheduler(
            boundaries=(_Boundary("B7", _NPC, kind="scheduled", due_tick=5),)
        )
        world, rt = _world(), RuntimeState(logical_tick=0)
        _, rt1, _ = s.fast_forward(world, rt)  # 停 @5 消费，terminal@5
        assert rt1.logical_tick == 5
        _, rt2, oc2 = s.fast_forward(world, rt1)
        assert rt2.scheduler_queue == []
        assert oc2.pause_reason == PauseReason(kind="terminal", tick=5)

    def test_past_due_boundary_not_seeded(self) -> None:
        s = _scheduler(
            boundaries=(_Boundary("B1", _PLAYER, kind="scheduled", due_tick=3),)
        )
        world, rt = _world(), RuntimeState(logical_tick=10)
        _, rt2, oc = s.fast_forward(world, rt)
        assert rt2.scheduler_queue == []
        assert oc.pause_reason == PauseReason(kind="terminal", tick=10)


class TestDecisionBoundaryStub:
    def test_decision_boundary_entry_is_clock_stop_noop(self) -> None:
        """T05 接线点现状（Leader 裁定 (B)）：decision_boundary 条目 = 时钟
        停靠点 no-op——条目消费、零 effect、零诊断、不暂停。"""
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_scheduled_event(
            rt,
            make_scheduled_event(
                "decision_boundary",
                8,
                payload={"boundary_id": "B1", "actor_id": "player_1"},
            ),
        )
        world2, rt2, oc = s.fast_forward(world, rt)
        assert world2 == world
        assert rt2.logical_tick == 8
        assert rt2.scheduler_queue == []
        assert oc.transactions == () and oc.events == ()
        assert oc.trace_records == () and oc.transitions == ()
        assert oc.errors == ()
        assert oc.pause_reason == PauseReason(kind="terminal", tick=8)


class TestWakeupWiring:
    def test_wakeup_entry_consumed_hook_invoked(self) -> None:
        """T06 已接线（D-P3-14）：wakeup 条目被 take_due 消费 →
        ``_drain_wakeup`` 求值注册的 hook——调用实参 (actor_id, view, clock,
        reason)，reason 经 (actor_id, due_tick) 记录查得（payload 不含
        reason，F5-02）；hook 返回空列表 → 零提案；actor_wakeups 记录随
        条目消费同步移除（F5-02）；世界零变更、terminal 停靠。"""
        hook = _Hook("player_1")
        s = _scheduler()
        registry = WakeupHookRegistry()
        registry.register(hook)
        s._wakeup_hooks = registry  # T06 已接线：hook 被求值
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_actor_wakeup(rt, _PLAYER, 7, reason="r")
        world2, rt2, oc = s.fast_forward(world, rt)
        assert len(hook.calls) == 1  # T06 已接线：hook 被调用恰好一次
        call = hook.calls[0]
        assert call[0] == _PLAYER
        assert call[3] == "r"  # reason = actor_wakeups 记录实参
        assert call[2].tick == 7  # clock = LogicalClock 当前刻
        assert rt2.logical_tick == 7
        assert rt2.actor_wakeups == []  # 记录随消费移除（F5-02）
        assert rt2.scheduler_queue == []
        assert rt2.pending_proposals == []
        assert oc.transactions == () and oc.events == ()
        assert oc.trace_records == () and oc.transitions == ()
        assert oc.errors == ()
        assert oc.pause_reason == PauseReason(kind="terminal", tick=7)
        assert world2 is world  # 零提交 → 同一对象


# —— 10. max_tick / step / terminal / 聚合 / 原子刻 ——


class TestMaxTickAndStep:
    def test_max_tick_requeues_batch_and_pauses_bounded(self) -> None:
        """批 due > max_tick → 批整体还队（队列保留）、bounded 暂停（tick =
        当前 logical_tick，时钟不动）。"""
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        entry = make_scheduled_event(
            "event",
            20,
            payload={
                "effects": [_set_var_effect("x", 1, effect_id="eff_mt_001").model_dump(mode="json")]
            },
            entry_id="sch_mt",
        )
        rt = enqueue_scheduled_event(rt, entry)
        world2, rt2, oc = s.fast_forward(world, rt, max_tick=10)
        assert world2 == world  # 批未处理 → 世界零变更
        assert rt2.scheduler_queue == [entry]  # 队列保留
        assert rt2.logical_tick == 0
        assert oc.paused is True
        assert oc.pause_reason == PauseReason(kind="bounded", tick=0)
        assert oc.ticks_processed == 0
        # 边界相等：due == max_tick 不触发还队
        world3, rt3, oc3 = s.fast_forward(world2, rt2, max_tick=20)
        assert world3.world_variables == {"x": 1}
        assert oc3.paused is False

    def test_step_single_batch_forced_pause(self) -> None:
        """step()：推进至下一边界（单批）后强制暂停——paused=True、
        PauseReason(kind="bounded", tick=本步到达刻)、ticks_processed=到达刻。"""
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_scheduled_event(
            rt,
            make_scheduled_event(
                "event",
                5,
                payload={
                    "effects": [_set_var_effect("a", 1, effect_id="eff_st_001").model_dump(mode="json")]
                },
            ),
        )
        rt = enqueue_scheduled_event(
            rt,
            make_scheduled_event(
                "event",
                10,
                payload={
                    "effects": [
                        _set_var_effect(
                            "b", 2, effect_id="eff_st_002", base_revision=1
                        ).model_dump(mode="json")
                    ],
                },
            ),
        )
        world1, rt1, oc1 = s.step(world, rt)
        assert world1.world_variables == {"a": 1}  # 只处理第一批
        assert rt1.logical_tick == 5
        assert oc1.paused is True
        assert oc1.pause_reason == PauseReason(kind="bounded", tick=5)
        assert oc1.ticks_processed == 5
        assert len(rt1.scheduler_queue) == 1  # 第二批保留
        # 第二步：处理第二批
        world2, rt2, oc2 = s.step(world1, rt1)
        assert world2.world_variables == {"a": 1, "b": 2}
        assert oc2.pause_reason == PauseReason(kind="bounded", tick=10)

    def test_step_empty_queue_terminal(self) -> None:
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=3)
        _, _, oc = s.step(world, rt)
        assert oc.paused is False
        assert oc.pause_reason == PauseReason(kind="terminal", tick=3)

    def test_fast_forward_empty_queue_terminal(self) -> None:
        """空队列 → terminal（时钟不动）。"""
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=3)
        world2, rt2, oc = s.fast_forward(world, rt)
        assert world2 is world
        assert rt2 is rt
        assert oc.paused is False
        assert oc.pause_reason == PauseReason(kind="terminal", tick=3)
        assert oc.ticks_processed == 3


class TestOutcomeAggregation:
    def test_outcome_scoped_per_call(self) -> None:
        """D-P3-18：两次连续 ff 的 outcome 各自只含本调用提交（不累计）。"""
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_scheduled_event(
            rt,
            make_scheduled_event(
                "event",
                5,
                payload={
                    "effects": [_set_var_effect("a", 1, effect_id="eff_ag_001").model_dump(mode="json")]
                },
            ),
        )
        rt = enqueue_scheduled_event(
            rt,
            make_scheduled_event(
                "event",
                10,
                payload={
                    "effects": [
                        _set_var_effect(
                            "b", 2, effect_id="eff_ag_002", base_revision=1
                        ).model_dump(mode="json")
                    ],
                },
            ),
        )
        world1, rt1, oc1 = s.fast_forward(world, rt, max_tick=5)
        assert len(oc1.transactions) == 1
        world2, rt2, oc2 = s.fast_forward(world1, rt1)
        assert len(oc2.transactions) == 1  # 仅本调用（不累计第一次的 1 条）
        assert oc2.events and len(oc2.events) == 1
        assert world2.world_variables == {"a": 1, "b": 2}


# —— 11. submit_proposal revalidation（§3.9 / Leader 裁定 (F)，委托
#    revalidation.revalidate_proposal）——


class TestSubmitProposalRevalidation:
    def test_accept_immediate_start(self) -> None:
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        _, rt2, decision = s.submit_proposal(world, rt, _proposal())
        assert decision.outcome is RevalidationOutcome.ACCEPT
        assert decision.reason == "accept"
        assert rt2.active_actions["act_p1"].status is ActionLifecycleStatus.ACTIVE

    def test_stale_revision_rejected(self) -> None:
        """is_stale（base < current）→ REJECT stale_revision；FAILED 终态记录
        + 提案留 pending + 世界/队列零变更（A5 口径）。"""
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        # 世界先推进（提交一个 event effect → world_revision 1）
        rt = enqueue_scheduled_event(
            rt,
            make_scheduled_event(
                "event",
                1,
                payload={
                    "effects": [_set_var_effect("v", 0, effect_id="eff_rv_001").model_dump(mode="json")]
                },
            ),
        )
        world2, rt2, _ = s.fast_forward(world, rt)
        assert world2.world_revision == 1
        # 以 base=0 提交（当前 1）→ stale
        world3, rt3, decision = s.submit_proposal(
            world2, rt2, _proposal(base=0, pid="act_stale")
        )
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "stale_revision"
        record = rt3.active_actions["act_stale"]
        assert record.status is ActionLifecycleStatus.FAILED
        assert record.result_summary["reason"] == "stale_revision"
        # F2-12：提案留在 pending_proposals（移除仅发生于 start_action 成功时）
        assert [p.proposal_id for p in rt3.pending_proposals] == ["act_stale"]
        # A5：世界/队列零变更
        assert world3 == world2
        assert rt3.scheduler_queue == rt2.scheduler_queue

    def test_valid_until_expired_priority(self) -> None:
        """F2-05 过期优先：base<current 且 current>valid_until 同时成立 →
        reason = valid_until_expired（不随实现顺序漂移）。"""
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_scheduled_event(
            rt,
            make_scheduled_event(
                "event",
                1,
                payload={
                    "effects": [_set_var_effect("v", 0, effect_id="eff_vu_001").model_dump(mode="json")]
                },
            ),
        )
        world2, rt2, _ = s.fast_forward(world, rt)
        # 世界 revision 已至 1；后续逐刻提交需 base 跟随（L2 一致性）
        rt3 = rt2
        world3 = world2
        for i in (2, 3):
            rt3 = enqueue_scheduled_event(
                rt3,
                make_scheduled_event(
                    "event",
                    i,
                    payload={
                        "effects": [
                            _set_var_effect(
                                f"k{i}",
                                0,
                                effect_id=f"eff_vu_00{i}",
                                base_revision=i - 1,
                            ).model_dump(mode="json")
                        ]
                    },
                ),
            )
            world3, rt3, _ = s.fast_forward(world3, rt3, max_tick=i)
        assert world3.world_revision == 3
        world4, rt4, decision = s.submit_proposal(
            world3, rt3, _proposal(base=0, valid_until=2, pid="act_vu")
        )
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "valid_until_expired"

    def test_expired_but_not_stale_rejected(self) -> None:
        """current == valid_until 不陈旧（边界刻有效）；current > valid_until
        且 base == current → 仍 REJECT valid_until_expired（is_stale 第二肢）。"""
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_scheduled_event(
            rt,
            make_scheduled_event(
                "event",
                1,
                payload={
                    "effects": [_set_var_effect("v", 0, effect_id="eff_vu2_001").model_dump(mode="json")]
                },
            ),
        )
        world2, rt2, _ = s.fast_forward(world, rt)
        # base == current == 1，valid_until = 0（< current）→ 仅第二肢触发
        _, _, decision = s.submit_proposal(
            world2, rt2, _proposal(base=1, valid_until=0, pid="act_vu2")
        )
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "valid_until_expired"
        # 边界刻有效：valid_until == current → 不陈旧 → ACCEPT
        _, _, decision2 = s.submit_proposal(
            world2, rt2, _proposal(base=1, valid_until=1, pid="act_vu3")
        )
        assert decision2.outcome is RevalidationOutcome.ACCEPT

    def test_actor_missing_rejected(self) -> None:
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        _, rt2, decision = s.submit_proposal(
            world, rt, _proposal(actor=EntityId("ghost_1"), pid="act_ghost")
        )
        assert decision.outcome is RevalidationOutcome.REJECT
        assert decision.reason == "actor_missing"
        assert rt2.active_actions["act_ghost"].status is ActionLifecycleStatus.FAILED

    def test_actor_state_revision_stale_is_diagnostic_only(self) -> None:
        """D-12：actor_state_revision 陈旧仅 details 诊断，不作 REJECT 依据。"""
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        _, rt2, decision = s.submit_proposal(
            world, rt, _proposal(base=0, state_rev=0, pid="act_asr")
        )
        # base == current == 0 不陈旧；state_rev 陈旧（0 < 0 不成立 → 需推进）
        assert decision.outcome is RevalidationOutcome.ACCEPT
        # 世界推进后再提交：base 跟新、state_rev 留旧 → 仍 ACCEPT + 诊断
        rt2 = enqueue_scheduled_event(
            rt2,
            make_scheduled_event(
                "event",
                1,
                payload={
                    "effects": [_set_var_effect("v", 0, effect_id="eff_asr_001").model_dump(mode="json")]
                },
            ),
        )
        world2, rt3, _ = s.fast_forward(world, rt2)
        _, _, decision2 = s.submit_proposal(
            world2, rt3, _proposal(base=1, state_rev=0, pid="act_asr2")
        )
        assert decision2.outcome is RevalidationOutcome.ACCEPT
        assert any("actor_state_revision_stale" in d for d in decision2.details)

    def test_unknown_action_no_proposed_record(self) -> None:
        """次序第 1 步（registry 查找）失败 → REJECT + FAILED 轨迹
        （reason="unknown_action"、诊断含 action_id）；不创建 PROPOSED 记录
        （无悬空 PROPOSED，F2-12）。"""
        s = _scheduler()
        world, rt = _world(), RuntimeState(logical_tick=0)
        world2, rt2, decision = s.submit_proposal(
            world, rt, _proposal(action_id=ActionTypeId("unknown_action_x"), pid="act_unk")
        )
        assert decision.outcome is RevalidationOutcome.REJECT
        record = rt2.active_actions["act_unk"]
        assert record.status is ActionLifecycleStatus.FAILED
        assert record.result_summary["reason"] == "unknown_action"
        assert "unknown_action_x" in str(record.result_summary)
        assert world2 == world
        assert rt2.scheduler_queue == []


# —— 12. resume / abort（§3.6 委托口径）——


class TestResumeAbort:
    def test_resume_from_interrupted_reanchors(self) -> None:
        s = _scheduler()
        world = _world()
        # 先推进世界 revision 至 1（re-anchor 目标可区分）
        rt0 = enqueue_scheduled_event(
            RuntimeState(logical_tick=0),
            make_scheduled_event(
                "event",
                1,
                payload={
                    "effects": [_set_var_effect("v", 0, effect_id="eff_ra_001").model_dump(mode="json")]
                },
            ),
        )
        world2, rt1, _ = s.fast_forward(world, rt0)
        assert world2.world_revision == 1
        # 叠加一个 INTERRUPTED 行动实例（中断本体属 T05；此处直造状态对）
        rt2 = RuntimeState(
            logical_tick=rt1.logical_tick,
            active_actions={
                "act_1": _active("act_1", _PLAYER, ActionLifecycleStatus.INTERRUPTED, start=0)
            },
        )
        world3, rt3, transition = s.resume_action(world2, rt2, ActionInstanceId("act_1"))
        assert transition.event is LifecycleEvent.RESUMED
        assert transition.from_status is ActionLifecycleStatus.INTERRUPTED
        assert transition.to_status is ActionLifecycleStatus.ACTIVE
        # re-anchor：base_world_revision = 当前世界 revision
        assert rt3.active_actions["act_1"].base_world_revision == world3.world_revision

    def test_resume_from_active_illegal(self) -> None:
        s = _scheduler()
        world, rt = _world(), RuntimeState(
            logical_tick=0,
            active_actions={
                "act_1": _active("act_1", _PLAYER, ActionLifecycleStatus.ACTIVE, start=0)
            },
        )
        with pytest.raises(IllegalTransitionError):
            s.resume_action(world, rt, ActionInstanceId("act_1"))

    def test_abort_from_active_illegal(self) -> None:
        """ACTIVE 无直接 ABORTED 边（E-P3-29②）：abort 须先经 INTERRUPTED。"""
        s = _scheduler()
        world, rt = _world(), RuntimeState(
            logical_tick=0,
            active_actions={
                "act_1": _active("act_1", _PLAYER, ActionLifecycleStatus.ACTIVE, start=0)
            },
        )
        with pytest.raises(IllegalTransitionError):
            s.abort_action(world, rt, ActionInstanceId("act_1"))

    def test_abort_from_interrupted(self) -> None:
        s = _scheduler()
        world, rt = _world(), RuntimeState(
            logical_tick=0,
            active_actions={
                "act_1": _active("act_1", _PLAYER, ActionLifecycleStatus.INTERRUPTED, start=0)
            },
        )
        rt2 = s.abort_action(world, rt, ActionInstanceId("act_1"))
        # ABORTED 是 LifecycleEvent 而非状态：INTERRUPTED --ABORTED--> FAILED
        assert rt2.active_actions["act_1"].status is ActionLifecycleStatus.FAILED


# —— 13. 原子刻错误路径（F2-03 / D-P3-24④）——


class TestAtomicTick:
    def test_error_mid_tick_returns_pre_tick_state(self) -> None:
        """批处理中 P3 错误（trigger_id 不可解析）→ 返回刻前状态对 +
        SchedulerOutcome(paused=False, pause_reason=None, ticks_processed=
        刻前 logical_tick, 四空元组, 非空 errors)。"""
        s = _scheduler(named=())
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_scheduled_event(
            rt, make_scheduled_event("event", 5, payload={"trigger_id": "t_missing"})
        )
        world2, rt2, oc = s.fast_forward(world, rt)
        # 刻前状态对：世界零变更（同一对象——无提交发生）
        assert world2 is world
        assert rt2.logical_tick == 0  # 时钟未跳变（跳变前出错）
        assert oc.paused is False
        assert oc.pause_reason is None
        assert oc.ticks_processed == 0
        assert oc.transactions == ()
        assert oc.events == ()
        assert oc.trace_records == ()
        assert oc.transitions == ()
        assert len(oc.errors) == 1

    def test_error_after_partial_tick_does_not_leak_world(self) -> None:
        """同刻批前半提交、后半出错 → 世界零可见变更（不可变值 = 天然回滚）：
        前半提交的 world 对象虽已产生，但 outcome 返回刻前 world。"""
        s = _scheduler(
            named=(
                (
                    "t_bad",
                    SyncTrigger(
                        "t_bad",
                        lambda events, state, depth: [_set_var_effect("leak", 1, effect_id="eff_leak_001")],
                    ),
                ),
            )
        )
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_scheduled_event(
            rt,
            make_scheduled_event(
                "event",
                5,
                payload={
                    "effects": [_set_var_effect("ok", 1, effect_id="eff_ok_001").model_dump(mode="json")]
                },
            ),
        )
        # 第二条同刻：未注册 trigger_id → 分支内 QueueInvariantError
        rt = enqueue_scheduled_event(
            rt, make_scheduled_event("event", 5, payload={"trigger_id": "t_missing"})
        )
        world2, rt2, oc = s.fast_forward(world, rt)
        assert world2 is world  # 刻前 world——前半提交对外不可见
        assert oc.errors and len(oc.errors) == 1
        assert oc.transactions == ()  # 部分提交不可见


# —— 11. 刻后边界求值接线（T05，§2.4 刻后块 / §3.7；真实 DecisionBoundary 对象）——


def _hit_condition(cid: str = "C1") -> InterruptCondition:
    """玩家/NPC 共用的命中条件：本刻提交事件流出现 core.set_world_variable
    （D-P3-17：event_type 恒等于 effect type）。"""
    return InterruptCondition(
        condition_id=cid,
        kind="event_type",
        parameters={"event_type": EFFECT_SET_WORLD_VARIABLE},
    )


def _event_entry(
    due_tick: int,
    *,
    key: str = "flag",
    value: object = True,
    effect_id: str = "eff_bnd_001",
    base_revision: int = 0,
):
    """确定性 event 条目：commit core.set_world_variable（无 trigger 路径）。"""
    return make_scheduled_event(
        "event",
        due_tick,
        payload={
            "effects": [
                _set_var_effect(
                    key,
                    value,
                    effect_id=effect_id,
                    base_revision=base_revision,
                ).model_dump(mode="json")
            ]
        },
    )


def _fired_traces(oc: SchedulerOutcome) -> list:
    """outcome 中 decision_boundary_fired 系统事件记录（F2-12 留痕面）。"""
    return [
        r
        for r in oc.trace_records
        if r.kind is TraceKind.SYSTEM
        and r.payload.get("diagnostic") == "decision_boundary_fired"
    ]


class TestPostTickBoundaryWiring:
    """真实 DecisionBoundary 对象的刻后求值 e2e（§5.2 S7/S8 口径）。"""

    def test_player_condition_boundary_interrupts_and_pauses(self) -> None:
        """Gate 式玩家条件边界：fired → INTERRUPTED（re-anchor rev 1、progress
        镜像 0.4、reason 透传）+ paused（decision_boundary/B1/12）+ fired 系统
        事件 trace（§5.2 S7/S8：transitions 恰 1 条）。"""
        b = DecisionBoundary(
            boundary_id="B1",
            actor_id=_PLAYER,
            kind="condition",
            condition=_hit_condition(),
            blocking=True,
            interrupt=True,
            reason="encounter",
        )
        s = _scheduler(boundaries=(b,), player_ids=(_PLAYER,))
        world = _world()
        rt = RuntimeState(
            logical_tick=0,
            active_actions={"act_b1": _active("act_b1", _PLAYER, ActionLifecycleStatus.ACTIVE)},
        )
        rt = enqueue_scheduled_event(rt, _event_entry(12))
        world2, rt2, oc = s.fast_forward(world, rt)
        assert oc.paused is True
        assert oc.pause_reason == PauseReason(
            kind="decision_boundary", boundary_id="B1", tick=12
        )
        assert oc.ticks_processed == 12
        act = rt2.active_actions["act_b1"]
        assert act.status is ActionLifecycleStatus.INTERRUPTED
        assert act.progress == pytest.approx(0.4)
        assert act.base_world_revision == Revision(1)
        assert act.last_transition_tick == 12
        assert len(oc.transitions) == 1
        t0 = oc.transitions[0]
        assert t0.event is LifecycleEvent.INTERRUPTED
        assert t0.instance_id == "act_b1"
        assert t0.at_tick == 12
        assert t0.reason == "encounter"
        assert world2.world_revision == Revision(1)
        traces = _fired_traces(oc)
        assert len(traces) == 1
        assert traces[0].logical_tick == 12
        assert traces[0].payload["fired"] == [["B1", ["act_b1"]]]
        assert traces[0].payload["player_blocking"] is True
        assert traces[0].payload["npc_notices"] == []

    def test_record_only_keeps_active_and_continues(self) -> None:
        """E-P3-36 record-only（pause_on_player_boundary=False）：玩家 blocking
        命中仍 fired + trace，但**不中断、不暂停**——行动保持 ACTIVE、后续刻
        照常推进至 terminal。"""
        b = DecisionBoundary(
            boundary_id="B1",
            actor_id=_PLAYER,
            kind="condition",
            condition=_hit_condition(),
            blocking=True,
            interrupt=True,
            reason="encounter",
        )
        s = _scheduler(
            boundaries=(b,),
            time_policy=TimePolicy(pause_on_player_boundary=False),
            player_ids=(_PLAYER,),
        )
        world = _world()
        rt = RuntimeState(
            logical_tick=0,
            active_actions={"act_b1": _active("act_b1", _PLAYER, ActionLifecycleStatus.ACTIVE)},
        )
        rt = enqueue_scheduled_event(rt, _event_entry(12))
        # 第二停靠点：wakeup 条目（无 effect、无事件 → 条件不再命中）
        rt = enqueue_actor_wakeup(rt, _NPC, 15, reason="probe")
        world2, rt2, oc = s.fast_forward(world, rt)
        assert oc.paused is False
        assert oc.pause_reason == PauseReason(kind="terminal", tick=15)
        assert oc.transitions == ()
        assert rt2.active_actions["act_b1"].status is ActionLifecycleStatus.ACTIVE
        assert world2.world_revision == Revision(1)
        traces = _fired_traces(oc)
        assert [t.logical_tick for t in traces] == [12]
        assert traces[0].payload["fired"] == [["B1", ["act_b1"]]]
        assert traces[0].payload["player_blocking"] is True

    def test_npc_blocking_boundary_interrupts_without_pause_wakes(self) -> None:
        """NPC blocking 命中（D-P3-10 选 B）：中断 NPC 行动但**不暂停**；
        npc_notices → wakeup 双记录（ActorWakeup 记录 reason=boundary_id、
        队列 payload 仅 actor_id）；同刻 wakeup 重入不重报（活络守卫）；
        后续 checkpoint 条目 → checkpoint_skipped_interrupted 诊断 no-op
        （D-P3-25）。"""
        b = DecisionBoundary(
            boundary_id="B1",
            actor_id=_NPC,
            kind="condition",
            condition=_hit_condition(),
            blocking=True,
            interrupt=True,
            reason="ambush",
        )
        s = _scheduler(boundaries=(b,), player_ids=(_PLAYER,))
        world = _world()
        rt = RuntimeState(
            logical_tick=0,
            active_actions={"act_n1": _active("act_n1", _NPC, ActionLifecycleStatus.ACTIVE)},
        )
        rt = enqueue_scheduled_event(rt, _event_entry(12))
        rt = enqueue_scheduled_event(
            rt, make_scheduled_event("action_checkpoint", 20, payload={"instance_id": "act_n1"})
        )
        # 段 1：step() 单批——同刻 wakeup 重入前观察双记录
        world2, rt2, oc = s.step(world, rt)
        assert oc.paused is True
        # step 强制暂停口径（NPC 命中不产生边界暂停，bounded 而非
        # decision_boundary——与玩家边界路径对照见 test_step_…）
        assert oc.pause_reason == PauseReason(kind="bounded", tick=12)
        act = rt2.active_actions["act_n1"]
        assert act.status is ActionLifecycleStatus.INTERRUPTED
        assert len(oc.transitions) == 1
        assert oc.transitions[0].event is LifecycleEvent.INTERRUPTED
        assert oc.transitions[0].at_tick == 12
        assert oc.transitions[0].reason == "ambush"
        # wakeup 双记录：ActorWakeup 记录（reason=boundary_id）+ 队列条目
        # （payload 仅 actor_id、reason 不入 payload，§2.5 尾注）
        assert ActorWakeup(actor_id=_NPC, due_tick=12, reason="B1") in rt2.actor_wakeups
        wq = [e for e in rt2.scheduler_queue if e.kind == "wakeup"]
        assert len(wq) == 1
        assert wq[0].due_tick == 12
        assert wq[0].payload == {"actor_id": "npc_1"}
        assert "reason" not in wq[0].payload
        assert len(_fired_traces(oc)) == 1
        # 段 2：续推——同刻 wakeup 消费（不重报：活络守卫）、checkpoint @20
        # 诊断 no-op、terminal @20
        world3, rt3, oc2 = s.fast_forward(world2, rt2)
        assert oc2.paused is False
        assert oc2.pause_reason == PauseReason(kind="terminal", tick=20)
        assert rt3.scheduler_queue == []
        # 记录随条目消费同步移除（F5-02，T06 接线）：wakeup@12 记录随条目
        # 消费移除；未再 fired → 无新记录（重入求值被守卫跳过、无二次迁移）
        assert rt3.actor_wakeups == []
        assert oc2.transitions == ()
        assert rt3.active_actions["act_n1"].status is ActionLifecycleStatus.INTERRUPTED
        diags = [
            r.payload.get("diagnostic")
            for r in oc2.trace_records
            if r.kind is TraceKind.SYSTEM
        ]
        assert "checkpoint_skipped_interrupted" in diags
        assert "decision_boundary_fired" not in diags  # 同刻重入不二次 fired 留痕
        assert "wakeup_no_hook" in diags  # T06 接线：无 hook 命中 → 仅诊断
        assert oc2.errors == ()

    def test_player_blocking_interrupt_false_fires_and_pauses_only(self) -> None:
        """D-P3-24⑥ 边角：玩家 blocking 命中但 interrupt=False → fired（空
        实例）+ 暂停，行动保持 ACTIVE、零迁移。"""
        b = DecisionBoundary(
            boundary_id="B1",
            actor_id=_PLAYER,
            kind="condition",
            condition=_hit_condition(),
            blocking=True,
            interrupt=False,
            reason="gate",
        )
        s = _scheduler(boundaries=(b,), player_ids=(_PLAYER,))
        world = _world()
        rt = RuntimeState(
            logical_tick=0,
            active_actions={"act_b1": _active("act_b1", _PLAYER, ActionLifecycleStatus.ACTIVE)},
        )
        rt = enqueue_scheduled_event(rt, _event_entry(12))
        world2, rt2, oc = s.fast_forward(world, rt)
        assert oc.paused is True
        assert oc.pause_reason == PauseReason(
            kind="decision_boundary", boundary_id="B1", tick=12
        )
        assert oc.transitions == ()
        assert rt2.active_actions["act_b1"].status is ActionLifecycleStatus.ACTIVE
        traces = _fired_traces(oc)
        assert len(traces) == 1
        assert traces[0].payload["fired"] == [["B1", []]]

    def test_step_reports_decision_boundary_not_bounded(self) -> None:
        """step() 单批 + 刻后求值：边界命中 → pause_reason =
        decision_boundary（优先于 single_batch 的 bounded 口径）。"""
        b = DecisionBoundary(
            boundary_id="B1",
            actor_id=_PLAYER,
            kind="condition",
            condition=_hit_condition(),
            blocking=True,
            interrupt=True,
            reason="encounter",
        )
        s = _scheduler(boundaries=(b,), player_ids=(_PLAYER,))
        world = _world()
        rt = RuntimeState(
            logical_tick=0,
            active_actions={"act_b1": _active("act_b1", _PLAYER, ActionLifecycleStatus.ACTIVE)},
        )
        rt = enqueue_scheduled_event(rt, _event_entry(12))
        world2, rt2, oc = s.step(world, rt)
        assert oc.paused is True
        assert oc.pause_reason == PauseReason(
            kind="decision_boundary", boundary_id="B1", tick=12
        )
        assert oc.ticks_processed == 12
        assert rt2.active_actions["act_b1"].status is ActionLifecycleStatus.INTERRUPTED

    def test_unknown_condition_kind_atomic_error(self) -> None:
        """未知条件 kind（未注册 resolver）→ UnknownConditionError（
        D-P3-16 可检查不静默）→ 原子刻错误路径：刻前状态对 + 单条 errors、
        零提交不可见。"""
        b = DecisionBoundary(
            boundary_id="B1",
            actor_id=_PLAYER,
            kind="condition",
            condition=InterruptCondition(
                condition_id="C1", kind="moon_phase", parameters={}
            ),
            blocking=True,
        )
        s = _scheduler(boundaries=(b,), player_ids=(_PLAYER,))
        world = _world()
        rt = RuntimeState(
            logical_tick=0,
            active_actions={"act_b1": _active("act_b1", _PLAYER, ActionLifecycleStatus.ACTIVE)},
        )
        rt = enqueue_scheduled_event(rt, _event_entry(12))
        world2, rt2, oc = s.fast_forward(world, rt)
        assert world2 is world  # 刻前 world——提交对外不可见
        assert rt2.logical_tick == 0
        assert rt.active_actions["act_b1"].status is ActionLifecycleStatus.ACTIVE
        assert oc.paused is False
        assert oc.pause_reason is None
        assert oc.ticks_processed == 0
        assert oc.transactions == ()
        assert oc.events == ()
        assert oc.transitions == ()
        assert len(oc.errors) == 1
        assert "moon_phase" in str(oc.errors[0])


# —— 14. _drain_wakeup 接线（T06，D-P3-14 / E-P3-35 / F5-02 / E-P3-39⑤）——


class _WakeupHookDuck:
    """WakeupHook 鸭子替身（注册键 = actor_id 字符串属性；T06 接线断言
    口径）：命中返回预置提案列表（可空）、记录调用实参（actor_id / view /
    clock / reason）、向共享序日志追加 actor_id（同刻序钉死）。"""

    def __init__(self, actor_id: str, *, order_log: list[str] | None = None) -> None:
        self.actor_id = actor_id
        self._order_log = order_log
        self.proposals: list = []
        self.calls: list[dict[str, object]] = []

    def on_wakeup(
        self,
        actor_id: EntityId,
        view: object,
        clock: object,
        reason: str | None,
    ) -> list:
        self.calls.append(
            {"actor_id": actor_id, "view": view, "clock": clock, "reason": reason}
        )
        if self._order_log is not None:
            self._order_log.append(str(actor_id))
        return list(self.proposals)


class _RaisingHook:
    """WakeupHook 鸭子替身：命中即抛异常（D-P3-14 失败处置 → 包装
    SchedulerWakeupError → 原子刻错误路径）。"""

    def __init__(self, actor_id: str) -> None:
        self.actor_id = actor_id
        self.calls = 0

    def on_wakeup(
        self,
        actor_id: EntityId,
        view: object,
        clock: object,
        reason: str | None,
    ) -> list:
        self.calls += 1
        raise ValueError("boom")


def _scheduler_with_hooks(*hooks: WakeupHook) -> Scheduler:
    """T06 接线测试装配：先武装写屏障（R1 正例路径），再构造携带
    wakeup_hooks 注册表的 Scheduler（无 hook → 空注册表；E-P3-39⑤ 缺省
    None → 空注册表由 test_no_hook_… 直构覆盖）。"""
    install_write_barrier()
    registry = WakeupHookRegistry()
    for hook in hooks:
        registry.register(hook)
    return Scheduler(
        _registry(),
        authority_policy=_allow_policy(),
        origin=_ORIGIN_PROVENANCE,
        time_policy=TimePolicy(),
        boundaries=(),
        named_triggers=frozenset(),
        player_actor_ids=frozenset(),
        trigger_registry=None,
        assert_barrier_armed=True,
        wakeup_hooks=registry,
    )


class TestWakeupDrain:
    """``_drain_wakeup`` 接线（T06，D-P3-14）：§6.1 六口径 + REJECT 穿透
    口径（提案经既有 submit_proposal 全管道，不绕过、不内联重实现，
    Leader 裁定 (B)）。"""

    def test_no_hook_diagnostic_zero_bookkeeping(self) -> None:
        """无 hook 命中（E-P3-39⑤，wakeup_hooks=None 缺省）→ 仅 SYSTEM
        诊断 trace、不崩溃、簿记零影响：条目消费 + (actor_id, due_tick)
        记录移除（F5-02）；世界零变更、terminal 停靠。"""
        install_write_barrier()
        s = Scheduler(
            _registry(),
            authority_policy=_allow_policy(),
            origin=_ORIGIN_PROVENANCE,
            time_policy=TimePolicy(),
            boundaries=(),
            named_triggers=frozenset(),
            player_actor_ids=frozenset(),
            trigger_registry=None,
            assert_barrier_armed=True,
            wakeup_hooks=None,  # E-P3-39⑤：None 缺省 → 空注册表
        )
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_actor_wakeup(rt, _NPC, 10, reason="B1")
        world2, rt2, oc = s.fast_forward(world, rt)
        assert oc.errors == ()
        assert rt2.logical_tick == 10
        assert rt2.actor_wakeups == []  # 记录随消费移除（F5-02）
        assert rt2.scheduler_queue == []  # 条目消费
        assert rt2.active_actions == {} and rt2.pending_proposals == []
        assert oc.transactions == () and oc.events == () and oc.transitions == ()
        assert oc.ticks_processed == 10
        assert oc.pause_reason == PauseReason(kind="terminal", tick=10)
        assert world2 is world  # 零提交 → 同一对象
        diags = [r for r in oc.trace_records if r.kind is TraceKind.SYSTEM]
        assert len(diags) == 1
        assert diags[0].payload == {
            "diagnostic": "wakeup_no_hook",
            "actor_id": "npc_1",
        }
        assert diags[0].logical_tick == 10

    def test_hook_hit_full_submit_pipeline(self) -> None:
        """hook 命中 → 提案经 ``submit_proposal`` 全管道（D-P3-14 /
        Leader 裁定 (B)）：ACCEPT → 立即 start_action 两跳复合（D-P3-19）
        → ACTIVE（start_tick = 消费刻）+ pending 移除（F2-12）+ action_end
        @40 入队（walk 固定 30 tick）；hook 恰调一次、实参正确（view =
        当刻 guard 视图、clock = 当刻 LogicalClock、reason = 记录 reason）；
        start 复合迁移不入 ff outcome（F2-16）；续推 → 到点 complete。"""
        hook = _WakeupHookDuck("npc_1")
        hook.proposals = [_proposal(actor=_NPC, pid="act_h1")]
        s = _scheduler_with_hooks(hook)
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_actor_wakeup(rt, _NPC, 10, reason="B1")
        # 段 1：停到消费刻（max_tick=10）——观察 start 后的当刻簿记
        world2, rt2, oc = s.fast_forward(world, rt, max_tick=10)
        assert oc.errors == ()
        assert oc.paused is True
        assert oc.pause_reason == PauseReason(kind="bounded", tick=10)
        assert len(hook.calls) == 1
        call = hook.calls[0]
        assert call["actor_id"] == _NPC
        assert call["reason"] == "B1"
        assert call["clock"].tick == 10  # LogicalClock 当前刻（D-P3-02）
        assert call["view"].world_revision == world.world_revision  # 当刻 guard 视图
        act = rt2.active_actions.get("act_h1")
        assert act is not None
        assert act.status is ActionLifecycleStatus.ACTIVE
        assert act.start_tick == 10  # 立即开跑（timing 无 earliest）
        assert act.expected_end_tick == 40  # walk 固定 30 tick
        assert rt2.pending_proposals == []  # F2-12：start 成功移除
        end_entries = [e for e in rt2.scheduler_queue if e.kind == "action_end"]
        assert len(end_entries) == 1
        assert end_entries[0].due_tick == 40
        assert end_entries[0].payload == {"instance_id": "act_h1"}
        assert oc.transitions == ()  # 复合迁移仅 start_action 直调可见（F2-16）
        assert rt2.actor_wakeups == []  # 记录随消费移除（F5-02）
        # 段 2：续推 → action_end @40 到点 complete、terminal
        world3, rt3, oc2 = s.fast_forward(world2, rt2)
        assert oc2.errors == ()
        assert oc2.pause_reason == PauseReason(kind="terminal", tick=40)
        assert rt3.active_actions["act_h1"].status is ActionLifecycleStatus.COMPLETED
        assert rt3.scheduler_queue == []

    def test_hook_raises_atomic_error_path(self) -> None:
        """hook 抛异常（D-P3-14 失败处置）→ 包装 SchedulerWakeupError
        （携带 actor_id + cause）→ 单刻原子错误路径（D-P3-24④）：刻前
        状态对 + 错误 outcome、不崩溃、部分提交不可见。"""
        hook = _RaisingHook("npc_1")
        s = _scheduler_with_hooks(hook)
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_actor_wakeup(rt, _NPC, 10, reason="B1")
        world2, rt2, oc = s.fast_forward(world, rt)
        assert hook.calls == 1
        # 刻前状态对（take_due 已把 due 批移出队列、时钟未跳变、记录未移除
        # ——移除发生于 _drain_wakeup 内、错误之后不可达）
        assert world2 is world
        assert rt2.logical_tick == 0
        assert rt2.scheduler_queue == []
        assert rt2.actor_wakeups == [
            ActorWakeup(actor_id=_NPC, due_tick=10, reason="B1")
        ]
        assert oc.paused is False
        assert oc.pause_reason is None
        assert oc.ticks_processed == 0
        assert oc.transactions == () and oc.events == ()
        assert oc.trace_records == () and oc.transitions == ()
        assert len(oc.errors) == 1
        assert oc.errors[0].startswith("SchedulerWakeupError:")
        assert "npc_1" in oc.errors[0]
        assert "ValueError: boom" in oc.errors[0]

    def test_scheduler_wakeup_error_carries_actor_and_cause(self) -> None:
        """D-P3-16 错误族：SchedulerWakeupError 继承 SchedulerError、携带
        actor_id + cause，消息可检查不静默。"""
        cause = ValueError("boom")
        err = SchedulerWakeupError(_NPC, cause=cause)
        assert isinstance(err, SchedulerError)
        assert err.actor_id == _NPC
        assert err.cause is cause
        assert "npc_1" in str(err)
        assert "ValueError: boom" in str(err)

    def test_reason_arg_from_record_not_payload(self) -> None:
        """reason 实参 = (actor_id, due_tick) 记录的 reason（F5-02：payload
        仅 actor_id、不含 reason）：带 reason 入队 → hook 收到该 reason；
        无 reason 入队 → hook 收到 None；payload 键集机械口径。"""
        player_hook = _WakeupHookDuck("player_1")
        npc_hook = _WakeupHookDuck("npc_1")
        s = _scheduler_with_hooks(player_hook, npc_hook)
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_actor_wakeup(rt, _NPC, 10, reason="B1")
        rt = enqueue_actor_wakeup(rt, _PLAYER, 10)  # 无 reason → None
        # 机械口径（F5-02 / §2.5 尾注）：payload 键集恰为 {"actor_id"}
        entries = [e for e in rt.scheduler_queue if e.kind == "wakeup"]
        assert len(entries) == 2
        for e in entries:
            assert set(e.payload) == {"actor_id"}
            assert "reason" not in e.payload
        assert [e.payload["actor_id"] for e in entries] == ["npc_1", "player_1"]
        world2, rt2, oc = s.fast_forward(world, rt)
        assert oc.errors == ()
        assert npc_hook.calls[0]["reason"] == "B1"
        assert player_hook.calls[0]["reason"] is None

    def test_consumption_removes_only_consumed_record(self) -> None:
        """记录消费即移除（F5-02）：同 actor 多刻 wakeup（@10 / @20）→
        仅被消费条目的 (actor_id, due_tick) 记录移除；未消费记录（@20）
        原样保留（条目经批还队保留、记录不动）。"""
        s = _scheduler_with_hooks()  # 无 hook → 诊断路径
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_actor_wakeup(rt, _NPC, 10, reason="r1")
        rt = enqueue_actor_wakeup(rt, _NPC, 20, reason="r2")
        world2, rt2, oc = s.fast_forward(world, rt, max_tick=10)
        assert oc.errors == ()
        assert oc.paused is True
        assert oc.pause_reason == PauseReason(kind="bounded", tick=10)
        assert rt2.logical_tick == 10
        # @10 记录随条目消费移除；@20 记录未消费 → 保留
        assert rt2.actor_wakeups == [
            ActorWakeup(actor_id=_NPC, due_tick=20, reason="r2")
        ]
        # @10 条目已消费；@20 条目经批还队保留（§6.1"队列保留"）
        wakeups = [e for e in rt2.scheduler_queue if e.kind == "wakeup"]
        assert len(wakeups) == 1
        assert wakeups[0].due_tick == 20

    def test_same_tick_wakeups_follow_queue_order(self) -> None:
        """同刻多条 wakeup：确定序 = 队列序（take_due 同刻批序 = 插入序
        FIFO，D-P3-05 / D-P3-14），不按 actor_id 排序、不重排。"""
        order_log: list[str] = []
        player_hook = _WakeupHookDuck("player_1", order_log=order_log)
        npc_hook = _WakeupHookDuck("npc_1", order_log=order_log)
        s = _scheduler_with_hooks(player_hook, npc_hook)
        world, rt = _world(), RuntimeState(logical_tick=0)
        # 插入序：player 先、npc 后（字母序 npc < player——若按 actor_id
        # 排序将得到相反序，故该断言区分队列序与排序序）
        rt = enqueue_actor_wakeup(rt, _PLAYER, 10, reason="B1")
        rt = enqueue_actor_wakeup(rt, _NPC, 10, reason="B2")
        world2, rt2, oc = s.fast_forward(world, rt)
        assert oc.errors == ()
        assert order_log == ["player_1", "npc_1"]  # 队列序、非 actor_id 序
        assert rt2.actor_wakeups == []  # 两条记录均随消费移除
        assert rt2.scheduler_queue == []

    def test_hook_proposal_reject_stays_in_pipeline(self) -> None:
        """REJECT 穿透口径（Leader 裁定 (B)：不绕过、不内联重实现）：hook
        提案经既有 submit_proposal → _revalidate（委托
        revalidation.revalidate_proposal）——同刻 event 先提交
        （world_revision 1）→ base=0 提案 stale → REJECT stale_revision：
        FAILED 终态记录 + 提案留 pending_proposals（A5 口径）+ 无 error
        （REJECT 为正常裁决、非刻错误）+ 运行继续至 terminal。"""
        hook = _WakeupHookDuck("npc_1")
        hook.proposals = [_proposal(actor=_NPC, base=0, pid="act_r1")]
        s = _scheduler_with_hooks(hook)
        world, rt = _world(), RuntimeState(logical_tick=0)
        rt = enqueue_scheduled_event(rt, _event_entry(10))  # 同刻先入队 → 先提交
        rt = enqueue_actor_wakeup(rt, _NPC, 10, reason="B1")
        world2, rt2, oc = s.fast_forward(world, rt)
        assert oc.errors == ()  # REJECT 非原子刻错误
        assert world2.world_revision == 1  # event 提交发生
        assert len(hook.calls) == 1
        assert hook.calls[0]["reason"] == "B1"
        # REJECT：FAILED 终态记录 + 提案留 pending（A5 口径）
        assert rt2.active_actions["act_r1"].status is ActionLifecycleStatus.FAILED
        assert rt2.active_actions["act_r1"].result_summary["reason"] == "stale_revision"
        assert [p.proposal_id for p in rt2.pending_proposals] == ["act_r1"]
        # 无开跑：无 action_end 条目
        assert not [e for e in rt2.scheduler_queue if e.kind == "action_end"]
        assert rt2.actor_wakeups == []  # 记录随消费移除（REJECT 不改变口径）
        assert oc.pause_reason == PauseReason(kind="terminal", tick=10)
