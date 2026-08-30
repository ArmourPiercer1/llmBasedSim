"""P4 Wave F 集成测试（设计 §5.3/§5.4：R1–R8 + 分支 B 序列 + 分支 C C1–C3）。

权威契约：``docs/v2/contracts/P4-actor-context-space-mode-design.md``（frozen + 2 errata）：

- §5.1（L1427–1456）S0 装配块——模块级 helper ``_assemble`` 函数体内逐字复现
  （唯一形态差：hook 策略参数化——分支 A = BobPolicy、分支 B = PassPolicy，
  §5.3 分支表「fixture 差异」列逐字口径）；
- §5.2（L1458–1482）S0–S13 步表——分支 A 驱动方式：S1 submit_proposal →
  S2–S5 有界 ``fast_forward(max_tick=12)``（t10 检查点 + t12 偷窃事务 +
  t12 B1 中断 + t12 wakeup drain 重提案 ACCEPT，t12 刻完整处理后暂停；
  精确语义核对 scheduler.py:1471-1505 / _advance max_tick 分支）→
  S6–S11 无界 ``fast_forward`` 至 t42 终态；有界调用段另断言
  ``out12.ticks_processed == 12`` 且世界 R0+1；
- §5.4（L1567–1618）R1–R8——R 行基于分支 A 的 S0–S11 状态快照
  （rt12 = 有界调用后；out_final/rt_final = 续跑终态）；
- §5.3 分支 B（PassPolicy）：S0–S4 同 A、S5′ 排水无提案 → 有界停 t12 →
  ``resume_action``（RESUMED 边）→ 再快进至 t30 终态（无第二实例）；
- §5.4 C1–C3（分支 C 口径）：纯簿记面，独立小装配（S0+S1 非平凡 runtime）；
- §5.5 M3：本文件所有 RevalidationDecision outcome 断言取值域断言
  {ACCEPT, REJECT}（值域，非基数）。

import 纪律（任务硬规则）：不 import 兄弟测试文件（test_p3/test_p4 任何
文件，含 test_p4_gate_scenario.py——只读对齐、不得 import）；小 helper
各自本地定义；conftest 裸名直引（只导入实际用到的名字）。
"""

from __future__ import annotations

from collections.abc import Mapping
from types import SimpleNamespace

import pytest

from src.engine_v2.core.action_lifecycle import LifecycleEvent, progress_of
from src.engine_v2.core.actions import ActionLifecycleStatus, ActionProposal, ActionTiming
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.context_provider import DefaultContextProvider
from src.engine_v2.core.event_queue import enqueue_scheduled_event, make_scheduled_event
from src.engine_v2.core.gameplay_mode import (
    ModeChangeRequest,
    ModeChangeResolution,
    ModeInvariantError,
    ModeOperation,
    ModeOperationKind,
    UnknownModeError,
    apply_mode_change,
)
from src.engine_v2.core.ids import ActionInstanceId, EntityId
from src.engine_v2.core.revalidation import RevalidationDecision
from src.engine_v2.core.revision import RevalidationOutcome
from src.engine_v2.core.scheduler import PauseReason, WakeupHookRegistry
from src.engine_v2.core.state import RuntimeState, WorldState
from src.engine_v2.core.trace import TraceKind

from tests.engine_v2.core.conftest import (
    BobPolicy,
    COMP_INVENTORY,
    COMP_LOOT,
    COMP_MOVEMENT,
    DEST_POSITION,
    ENT_BOB,
    ENT_DEST,
    ENT_VAULT,
    ORIGIN_PROVENANCE,
    ORIGIN_SCRIPT_PROVENANCE,
    PassPolicy,
    PolicyWakeupHook,
    R0,
    TRAVEL,
    make_gate_registry,
    make_p4_capability_table,
    make_p4_mode_overlays,
    make_p4_runtime,
    make_p4_scheduler,
    make_p4_space_registry,
    make_p4_world,
)

#: 固定实例 ID（分支 A/B 提交提案，P_BOB 逐字形态）
ACT_BOB = ActionInstanceId("act_bob")
#: rev 记法（§5.2：R1/R2 = R0+1 / R0+2）
R1 = R0 + 1
R2 = R0 + 2
#: t12：偷窃 event / B1 中断 / wakeup drain 重提案（分支 A/B 同刻）
B1_TICK = 12
#: 分支 A 终态 tick（ACT_BOB2 12→42 完成，§5.2 S10/S11）
FINAL_TICK = 42
#: 分支 B 终态 tick（act_bob 0→30 完成，RESUMED 复用旧实例）
FINAL_TICK_B = 30
#: M3（§5.5）：P4 全部 RevalidationDecision outcome 取值域（值域断言，非基数）
_P4_OUTCOME_DOMAIN = frozenset({RevalidationOutcome.ACCEPT, RevalidationOutcome.REJECT})


def _assert_m3_domain(decision: RevalidationDecision) -> None:
    """M3 值域纪律：P4 不产出 REPAIR/REBASE——outcome ∈ {ACCEPT, REJECT}。"""
    assert decision.outcome in _P4_OUTCOME_DOMAIN


def _component_surface(world: WorldState, eid: EntityId, ct: ComponentTypeId) -> object:
    """component_view 读取面 → JSON 原生面（同值归一，断言语义不变）。

    ``component_view`` 返回深冻结视图（state.py:312-317；list → tuple），设计
    契约字面量（``{"loot": []}`` / ``{"items": ["gold_cup"]}`` /
    ``{"position": DEST_POSITION}``）按同值 JSON 原生面比较（先例：Wave E
    test_p4_gate_scenario ``_component_surface``/``_jsonable``；R6 小 helper
    本地定义）。
    """
    value = world.component_view(eid, ct)
    return _json_native(value)


def _json_native(value: object) -> object:
    """递归归一：Mapping/tuple/list 逐层降级为 JSON 原生结构，其余原样。"""
    if isinstance(value, Mapping):
        return {str(key): _json_native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_native(item) for item in value]
    return value


def _assemble(policy: type) -> SimpleNamespace:
    """S0 装配（设计 §5.1 L1427–1456 逐字形态；hook 策略参数化——
    分支 A = BobPolicy / 分支 B = PassPolicy，§5.3 分支表 fixture 差异列）。

    返回 S0 全量快照（世界 R0、runtime t0 + 预置 event@12、scheduler、
    mode_registry、P_BOB 提案）。
    """
    w0 = make_p4_world()                      # R0
    rt0 = make_p4_runtime()                   # P4 节新工厂（§5.1；t0，空队列）
    rt0 = enqueue_scheduled_event(
        rt0,
        make_scheduled_event(
            "event", 12, payload={"trigger_id": "scenario.theft_12"}),
    )                                         # 纯函数语义：返回值必须 rebind
    provider = DefaultContextProvider()       # prompt 缺省（opaque，D-P4-05）
    hook = PolicyWakeupHook(
        ENT_BOB, policy(), provider,
        make_p4_capability_table(), make_gate_registry(),
        make_p4_space_registry())
    hook_registry = WakeupHookRegistry()
    hook_registry.register(hook)              # 读 hook.actor_id（scheduler.py:355-367）
    scheduler = make_p4_scheduler(hook_registry)
    mode_registry = make_p4_mode_overlays()

    p_bob = ActionProposal(
        proposal_id=ACT_BOB,
        actor_id=ENT_BOB,
        action_id=TRAVEL,
        arguments={"destination": ENT_DEST},
        timing=ActionTiming(duration_hint_ticks=30),
        base_world_revision=R0,
        provenance=ORIGIN_PROVENANCE,
    )
    return SimpleNamespace(
        w0=w0,
        rt0=rt0,
        scheduler=scheduler,
        mode_registry=mode_registry,
        p_bob=p_bob,
    )


def _run_branch_a() -> SimpleNamespace:
    """分支 A：S0→S1→有界 ff(max_tick=12)→无界 ff 至 t42 终态。

    有界段断言（场景前提）：out12.paused is True（PauseReason kind=bounded
    结构核对）∧ ticks_processed == 12 ∧ 世界 R1。S11 终态事实同 COMMON 节
    （tick 42 / 世界 R2 / act_bob INTERRUPTED / ACT_BOB2 COMPLETED 12→42 /
    bob 到位 / loot 空 / inventory gold_cup）写为 helper 内前提断言
    （所有 R 行共享的前提，非跨行断言）。
    """
    base = _assemble(BobPolicy)

    # ── S1：提交（t0；revalidation ACCEPT，0 tx / 0 evt）─────────────────
    world1: WorldState
    rt1: RuntimeState
    world1, rt1, s1_decision = base.scheduler.submit_proposal(
        base.w0, base.rt0, base.p_bob)
    _assert_m3_domain(s1_decision)
    assert s1_decision.outcome is RevalidationOutcome.ACCEPT

    # ── S2–S5：有界快进（t10 检查点 + t12 偷窃/B1 中断/wakeup 重提案）────
    # t12 刻完整处理（含 drain）后暂停于 t12（scheduler.py _advance max_tick
    # 分支：下一批 due > max_tick → 批整体还队 + bounded 暂停）
    w12, rt12, out12 = base.scheduler.fast_forward(world1, rt1, max_tick=B1_TICK)
    # 有界调用段场景前提
    assert out12.paused is True
    assert out12.pause_reason == PauseReason(kind="bounded", tick=B1_TICK)
    assert out12.ticks_processed == B1_TICK
    assert out12.errors == ()
    assert w12.world_revision == R1

    # ── S6–S11：无界快进至终态（确定性终点，时钟空队列返回）──────────────
    world_final, rt_final, out_final = base.scheduler.fast_forward(w12, rt12)
    # S11 终态事实（9 条，所有 R 行共享）
    assert out_final.ticks_processed == FINAL_TICK
    assert out_final.paused is False
    assert out_final.errors == ()
    assert world_final.world_revision == R2
    act_bob = rt_final.active_actions[ACT_BOB]
    assert act_bob.status is ActionLifecycleStatus.INTERRUPTED
    new_ids = set(rt_final.active_actions) - {ACT_BOB}
    assert len(new_ids) == 1  # 工厂值（D-P4-07），集合差捕获
    act_bob2_id = next(iter(new_ids))
    act_bob2 = rt_final.active_actions[act_bob2_id]
    assert act_bob2.status is ActionLifecycleStatus.COMPLETED
    assert act_bob2.start_tick == B1_TICK
    assert act_bob2.expected_end_tick == FINAL_TICK
    assert act_bob2.base_world_revision == R1
    assert _component_surface(world_final, ENT_BOB, COMP_MOVEMENT) == {
        "position": DEST_POSITION
    }
    assert _component_surface(world_final, ENT_VAULT, COMP_LOOT) == {"loot": []}
    assert _component_surface(world_final, ENT_BOB, COMP_INVENTORY) == {"items": ["gold_cup"]}

    return SimpleNamespace(
        scheduler=base.scheduler,
        mode_registry=base.mode_registry,
        world1=world1,
        rt1=rt1,
        s1_decision=s1_decision,
        w12=w12,
        rt12=rt12,
        out12=out12,
        world_final=world_final,
        rt_final=rt_final,
        out_final=out_final,
        act_bob2_id=act_bob2_id,
    )


# ══════════════════════════════════════════════════════════════════
# R1–R7（分支 A 集成断言，§5.4）
# ══════════════════════════════════════════════════════════════════


def test_r1_interrupt_reanchor() -> None:
    """R1（S4 后，断言于 rt12）：B1 非阻塞中断——act_bob INTERRUPTED @12
    ∧ last_transition_tick == 12（actions.py:234/243）∧ base_world_revision
    重锚 R0+1（actions.py:241；S4 迁移 updates 携带，scheduler.py:783-790）。"""
    snap = _run_branch_a()
    act = snap.rt12.active_actions[ACT_BOB]
    assert act.status is ActionLifecycleStatus.INTERRUPTED
    assert act.last_transition_tick == B1_TICK
    assert act.base_world_revision == R1


def test_r2_repropose_accept_active() -> None:
    """R2（S5 后，断言于 rt12）：wakeup drain 重提案全流水线 ACCEPT 的逻辑像——
    集合差恰含 1 个新键（工厂值，D-P4-07）∧ 新实例直接落 ACTIVE（ACCEPT 当刻
    start_action 两跳复合，scheduler.py:1577-1586）∧ trace 中无新实例的
    FAILED 生命周期记录（REJECT 路径会留 FAILED 留痕，scheduler.py:1570-1572——
    缺席 + 实例存在 = ACCEPT；直接流水线 REJECT 证明见 A7b 对抗文件）。"""
    snap = _run_branch_a()
    rt12 = snap.rt12
    new_ids = set(rt12.active_actions) - {ACT_BOB}
    assert len(new_ids) == 1
    act_bob2 = next(iter(new_ids))
    assert rt12.active_actions[act_bob2].status is ActionLifecycleStatus.ACTIVE
    # REJECT 留痕缺席（FAILED 终态记录 / FAILED 迁移边均不存在）
    assert not any(
        rec.instance_id == act_bob2 and rec.status is ActionLifecycleStatus.FAILED
        for rec in rt12.active_actions.values()
    )
    assert not any(
        tr.instance_id == act_bob2 and tr.to_status is ActionLifecycleStatus.FAILED
        for tr in snap.out12.transitions
    )
    _assert_m3_domain(snap.s1_decision)


def test_r3_repropose_window_base() -> None:
    """R3（S5 后，断言于 rt12）：新实例时间窗与基线——start_tick == 12 ∧
    expected_end_tick == 42（actions.py:235/236；hint 30、start 12）∧
    base_world_revision == R0+1（actions.py:241，context 固化口径 D-P4-05）。"""
    snap = _run_branch_a()
    act = snap.rt12.active_actions[snap.act_bob2_id]
    assert act.start_tick == B1_TICK
    assert act.expected_end_tick == FINAL_TICK
    assert act.base_world_revision == R1


def test_r4_checkpoint_skipped_trace() -> None:
    """R4（S6 后，断言于 out_final.trace_records）：旧 act_bob cp@20 条目
    命中非 ACTIVE 守卫 → no-op + SYSTEM 诊断 ``checkpoint_skipped_interrupted``
    （D-P3-25 trace 口径；payload 键名核对源码 + P3 Gate 先例）。"""
    snap = _run_branch_a()
    hits = [
        rec
        for rec in snap.out_final.trace_records
        if rec.kind is TraceKind.SYSTEM
        and rec.payload.get("diagnostic") == "checkpoint_skipped_interrupted"
        and rec.payload.get("instance_id") == "act_bob"
    ]
    assert len(hits) == 1  # 旧实例仅一条 cp@20 跳过（§5.2 S6「+1 trace」）
    assert hits[0].logical_tick == 20


def test_r5_terminal_completed() -> None:
    """R5（S10/S11 终态）：新实例 COMPLETED ∧ 世界 R0+2 ∧ bob 到位
    （component_view == DEST_POSITION，conftest.py:93 口径）。"""
    snap = _run_branch_a()
    act = snap.rt_final.active_actions[snap.act_bob2_id]
    assert act.status is ActionLifecycleStatus.COMPLETED
    assert snap.world_final.world_revision == R2
    assert _component_surface(snap.world_final, ENT_BOB, COMP_MOVEMENT) == {
        "position": DEST_POSITION
    }


def test_r6_interrupted_lingering() -> None:
    """R6（S11 终态）：旧实例不自动收敛——act_bob 终态仍 INTERRUPTED
    （G3:165 移交 4；收敛只能由显式操作触发）。"""
    snap = _run_branch_a()
    assert snap.rt_final.active_actions[ACT_BOB].status is ActionLifecycleStatus.INTERRUPTED


def test_r7_explicit_abort_failed() -> None:
    """R7（R6 之后，显式 abort）：``abort_action``（仅返回 RuntimeState，
    scheduler.py:1615-1624）→ act_bob FAILED（ABORTED 边：INTERRUPTED→FAILED；
    无 ABORTED 状态值，actions.py:191-205）∧ world 引用/内容不变（abort
    不接世界：同一对象引用且 dump 不变）。"""
    snap = _run_branch_a()
    world_final = snap.world_final
    rt_final = snap.rt_final
    world_ref = world_final
    dump_before = world_final.model_dump()
    rt7 = snap.scheduler.abort_action(world_final, rt_final, ACT_BOB)
    assert rt7.active_actions[ACT_BOB].status is ActionLifecycleStatus.FAILED
    assert world_final is world_ref
    assert world_final.model_dump() == dump_before
    # abort 仅触及被中止实例（其余簿记不动）
    assert rt7.active_actions[snap.act_bob2_id].status is ActionLifecycleStatus.COMPLETED
    assert set(rt7.active_actions) == set(rt_final.active_actions)


# ══════════════════════════════════════════════════════════════════
# R8（分支 B：PassPolicy → 无重提案 → RESUMED 边复用旧实例，§5.4）
# ══════════════════════════════════════════════════════════════════


def test_r8_branch_b_resume_single_instance() -> None:
    """R8（分支 B，独立装配：S0 同 A 但 hook 策略 = PassPolicy——decide 恒
    None，D-P4-01）：有界 ff(max_tick=12)（S0–S4 同 A：中断 + wakeup 照常；
    S5′ 排水无提案 → 队列仅剩旧 act_bob 的 cp@20/end@30）→ out_bounded.paused
    is True → ``resume_action``（RESUMED 边）→ act_bob ACTIVE ∧
    last_transition_tick == 12 → progress_of(act_bob, 12) == 0.4 精确
    （action_lifecycle.py:367-380，同式 (12-0)/(30-0)）→ 再 ff 至终态 →
    logical_tick == 30 ∧ act_bob COMPLETED ∧ 世界 R0+2 ∧ 无第二实例
    （RESUMED 边复用旧实例，与分支 A 的新实例路径对照）。"""
    base = _assemble(PassPolicy)

    # ── S1：提交（同 A）───────────────────────────────────────────────
    world1: WorldState
    rt1: RuntimeState
    world1, rt1, s1_decision = base.scheduler.submit_proposal(
        base.w0, base.rt0, base.p_bob)
    _assert_m3_domain(s1_decision)
    assert s1_decision.outcome is RevalidationOutcome.ACCEPT

    # ── 有界快进：t10 检查点 + t12 偷窃/B1 中断/wakeup 排水（无提案）──
    w12, rt12, out12 = base.scheduler.fast_forward(world1, rt1, max_tick=B1_TICK)
    assert out12.paused is True
    assert out12.pause_reason == PauseReason(kind="bounded", tick=B1_TICK)
    assert out12.ticks_processed == B1_TICK
    assert out12.errors == ()
    assert w12.world_revision == R1
    # S5′ 无重提案：无第二实例、旧实例滞留 INTERRUPTED（@12、base 重锚 R1）
    assert set(rt12.active_actions) == {ACT_BOB}
    act_bob12 = rt12.active_actions[ACT_BOB]
    assert act_bob12.status is ActionLifecycleStatus.INTERRUPTED
    assert act_bob12.last_transition_tick == B1_TICK
    assert act_bob12.base_world_revision == R1

    # ── RESUMED 边（scheduler.py:1595-1613；at_tick = 当刻 12）────────
    world_r, rt_r, transition = base.scheduler.resume_action(w12, rt12, ACT_BOB)
    assert transition.instance_id == ACT_BOB
    assert transition.from_status is ActionLifecycleStatus.INTERRUPTED
    assert transition.to_status is ActionLifecycleStatus.ACTIVE
    assert transition.event is LifecycleEvent.RESUMED
    assert transition.at_tick == B1_TICK
    act = rt_r.active_actions[ACT_BOB]
    assert act.status is ActionLifecycleStatus.ACTIVE
    assert act.last_transition_tick == B1_TICK
    # resume re-anchor 至当前世界版本（D-P3-08 口径；§5.3 A1）
    assert act.base_world_revision == R1
    # 时间预算不变：0→30，progress 纯派生 (12-0)/(30-0)
    assert act.start_tick == 0
    assert act.expected_end_tick == FINAL_TICK_B
    assert progress_of(act, B1_TICK) == 0.4

    # ── 无界快进至终态（t30 完成提交 → 世界 R2）────────────────────────
    w30, rt30, out30 = base.scheduler.fast_forward(world_r, rt_r)
    assert rt30.logical_tick == FINAL_TICK_B
    assert out30.ticks_processed == FINAL_TICK_B
    assert out30.paused is False
    assert out30.errors == ()
    assert rt30.active_actions[ACT_BOB].status is ActionLifecycleStatus.COMPLETED
    assert w30.world_revision == R2
    # 无第二实例——RESUMED 复用旧实例（分支 A 新实例路径的对照面）
    assert set(rt30.active_actions) == {ACT_BOB}


# ══════════════════════════════════════════════════════════════════
# C1–C3（分支 C：模式错误路径 / 幂等 no-op，§5.4；纯簿记面）
# ══════════════════════════════════════════════════════════════════


def _assemble_c() -> SimpleNamespace:
    """分支 C 独立小装配（与时间流无关，可在任意分支后执行——§5.3）：
    S0（BobPolicy）+ S1 提交受理 → 非平凡 runtime（act_bob ACTIVE、队列
    非空），供 C1 原子性 dump 对比与 C3 S12 应用。"""
    base = _assemble(BobPolicy)
    world1, rt1, s1_decision = base.scheduler.submit_proposal(
        base.w0, base.rt0, base.p_bob)
    _assert_m3_domain(s1_decision)
    assert s1_decision.outcome is RevalidationOutcome.ACCEPT
    return SimpleNamespace(
        scheduler=base.scheduler,
        mode_registry=base.mode_registry,
        world1=world1,
        rt1=rt1,
    )


def test_c1_unknown_mode_atomic() -> None:
    """C1（M-INV-3 原子性）：operations 含未知 mode_id → ``apply_mode_change``
    抛 UnknownModeError（查找点先于任何簿记变更）；异常后原 runtime 逐字段
    不变（同一对象引用 + model_dump 逐字段相等）。"""
    snap = _assemble_c()
    rt: RuntimeState = snap.rt1
    rt_before = rt
    dump_before = rt.model_dump()
    request_bad = ModeChangeRequest(
        request_id="req_bad",
        source=ORIGIN_SCRIPT_PROVENANCE,
        operations=(ModeOperation(
            operation_kind=ModeOperationKind.ACTIVATE, mode_id="nope"),),
    )
    with pytest.raises(UnknownModeError):
        apply_mode_change(
            request=request_bad, runtime=rt, registry=snap.mode_registry)
    assert rt is rt_before
    assert rt.model_dump() == dump_before


def test_c2_empty_operations_construction() -> None:
    """C2（M-INV-2 非空操作）：``ModeChangeRequest(operations=())`` 构造时即
    抛 ModeInvariantError（具名类型，不静默、不包裹）。"""
    with pytest.raises(ModeInvariantError):
        ModeChangeRequest(
            request_id="req_empty",
            source=ORIGIN_SCRIPT_PROVENANCE,
            operations=(),
        )


def test_c3_repeat_activate_noop() -> None:
    """C3（幂等 no-op）：S12 之后（S12 请求逐字 = 设计 §5.2 L1477：
    req_dlg / ORIGIN_SCRIPT_PROVENANCE / ACTIVATE dialogue）再次 ACTIVATE
    dialogue → res3.applied == () ∧ res3.ignored == ("activate:dialogue",)
    ∧ runtime 的 active_modes / mode_context 逐字段不变。"""
    snap = _assemble_c()
    # ── S12 逐字请求（设计 §5.2 L1477）────────────────────────────────
    req_dlg = ModeChangeRequest(
        request_id="req_dlg",
        source=ORIGIN_SCRIPT_PROVENANCE,
        operations=(ModeOperation(
            operation_kind=ModeOperationKind.ACTIVATE, mode_id="dialogue"),),
    )
    rt_mode1: RuntimeState
    res1: ModeChangeResolution
    rt_mode1, res1 = apply_mode_change(
        request=req_dlg, runtime=snap.rt1, registry=snap.mode_registry)
    # S12 前提（§5.2 S12 行：active_modes == ["dialogue"] 等）
    assert res1.applied == ("activate:dialogue",)
    assert res1.ignored == ()
    assert rt_mode1.active_modes == ["dialogue"]
    assert rt_mode1.mode_context == {"dialogue": {"active": True}}
    # ── C3：再次 ACTIVATE dialogue（新请求，同操作）────────────────────
    req_repeat = ModeChangeRequest(
        request_id="req_dlg_repeat",
        source=ORIGIN_SCRIPT_PROVENANCE,
        operations=(ModeOperation(
            operation_kind=ModeOperationKind.ACTIVATE, mode_id="dialogue"),),
    )
    rt_mode3, res3 = apply_mode_change(
        request=req_repeat, runtime=rt_mode1, registry=snap.mode_registry)
    assert res3.applied == ()
    assert res3.ignored == ("activate:dialogue",)
    # 幂等 no-op：active_modes / mode_context 逐字段不变（M-INV-5 其余字段位级不变）
    assert rt_mode3.active_modes == rt_mode1.active_modes
    assert rt_mode3.mode_context == rt_mode1.mode_context
    assert rt_mode3.model_dump() == rt_mode1.model_dump()
    # resolution 新态面与簿记面一致
    assert res3.new_active_modes == ("dialogue",)
    assert res3.new_mode_context == {"dialogue": {"active": True}}
