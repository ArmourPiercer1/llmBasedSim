"""P3-T08 Gate 场景端到端 + G3 可执行清单（设计文档 §5.2–§5.5 / §6.2）。

依据 ``docs/v2/contracts/P3-scheduler-time-action-design.md``：

- **G3-1**（§5.2 S0–S8 / §5.3 分支 A / §5.4 分支 B）：
  ``test_gate_scenario_travel_interrupt`` —— S0→S8 单跑（暂停点 9 断言）+
  分支 A resume（4 断言）+ 分支 B abort（4 断言），共 **17 条**，逐条标注
  S 编号 / 裁定号；分支自同一暂停点经 ``deep_copy_via_roundtrip`` 分叉
  （E-P3-07/D-P3-11②：唯一合法深拷贝）；
- **G3-2**（§6.2）：``test_queue_serialization`` —— RuntimeState JSON
  往返（``dump_json`` → ``assert_json_clean`` → ``load_json``）后
  队列/active_actions/actor_wakeups/logical_tick 逐项恒等（entry_id 保 ``sch_``
  前缀）、往返后 resume+ff 续跑事件键序列与独立深拷贝路径恒同；
- **G3-3**（§6.2，文档口径 = 中断跨度的 progress 语义）：
  ``test_progress_across_interrupt`` —— 暂停点 progress == 12/30 精确、resume
  checkpoint 序列 0.4 → 0.6667 → 1.0 单调、abort 分支
  ``result_summary["progress"] == 0.4`` + 终态记录保留、snapshot 往返后
  progress 重算恒等（与存储值无关）；
- **G3-4**（§6.2）：``test_replay_determinism`` —— (a) 同一 snapshot 两次
  restore 续跑事件键序列 + tick 水位恒等；(b) snapshot 路径 vs 无 snapshot
  深拷贝路径事件键恒等；(c) ``apply_committed_effects`` 重放
  （reducer.py:843）== 实际世界；(d) 指纹三探针（registry / time_policy /
  boundaries 各篡改一字段）+ 同输入恒等——回放拒绝 = 测试层指纹失配检查
  （引擎不静默回放，D-P3-15①/D-P3-20）；
- **§5.5 M1/M2/M3 可测试化表达式**：``test_m1_background_blinks_no_pause``
  （200 背景 blink 不干扰 Gate 暂停）/ ``test_m2_position_commit_isolation``
  （position 仅在 txn_2 提交点变 dest + 授权/校验/提交 trace 三口 + 伪造
  progress 探针）/ ``test_m3_purity_and_serialization``（双拷贝 outcome 逐项
  恒等 + snapshot/restore 续跑恒等 + RuntimeState 全字段 JSON-clean）；
- **错误路径**（G3-3 三条错误路径，§6.2 G3-3"在 Gate 场景内复现"口径；
  §6.3 A5/A2 探针）：分三处覆盖：

  - invalid spec → ``test_invalid_spec_gate_context`` —— **fixture 无关的
    校验层探针**：非法 spec 属参数 schema 校验（``model_validate`` 构造期
    拒绝：extra=forbid / 缺必填 / 注册表键一致性），与 Gate 场景状态无关
    （不涉世界/队列/时钟）；单元级全矩阵见
    ``tests/engine_v2/core/test_action_registry.py::TestContractModelInvariants::test_extra_forbid``
    （参数面含 ActionSpec）+ ``TestActionSpecContract``；
  - unknown action → ``test_unknown_action_gate_context`` —— **Gate 语境**
    （conftest §5.1 共享 fixture：travel 世界 + 双幂等 named trigger stub +
    空 trigger registry + B1 边界）：先提交未注册 ``flying``（A5 探针）→
    ``UnknownActionError`` 于 registry 查找点抛出、被 ``submit_proposal``
    捕获转 FAILED 轨迹（reason="unknown_action"；E-P3-39⑧ 次序第 1 步：
    registry 查找先于 revalidate，错误路径不创建 PROPOSED 记录、不查迁移
    表）；A5 口径逐条：不崩溃、队列零残留、世界零变更、诊断串含
    action_id + F2-12 pending_proposals 簿记；随后同场景内继续 Gate 主
    时序 → t=12 照常暂停（B1）、暂停点 progress == 12/30（与主场景同
    值）——错误路径发生在场景内且场景语义完整；
  - IllegalTransition → ``test_illegal_transition_gate_context`` —— **Gate
    语境、复用 S8 暂停点**（``gate_run_to_pause`` 达成，与主场景同写
    法）：表外探针 INTERRUPTED→INTERRUPTED 双中断（对照
    LIFECYCLE_TRANSITIONS 唯一权威，INTERRUPTED 行仅 RESUMED/ABORTED
    出边；A2 探针集）→ ``IllegalTransitionError``（消息含 from/to/
    event）；错误后 ``fast_forward`` = D-P3-24 入口首检幂等重报
    （paused=True、tick 水位不前进、transactions/events/transitions/
    errors 全空、队列不变 [cp@20, end@30]、世界零副作用）；终态侧
    （abort 后 resume）亦 IllegalTransitionError——与 test_scheduler.py
    的 ACTIVE 探针互补的 Gate 全装配角度。
  (a)(b) 不触碰既有 17 条 G3-1 断言（E-P3-04 计数口径不变：9+4+4=17）。

裁定 / 差异注记（与报告 one_line 同步）：

- 文档 §6.2 G3-3 = ``test_progress_across_interrupt``（progress 跨中断语义）；
  G3-3 三条错误路径分三处落实（见"错误路径"节：invalid spec 为 fixture
  无关探针 + unknown action / IllegalTransition 于 Gate 语境复现），与
  G3-3 progress 测试并存；
- COMPLETED 存储 progress = 最后 checkpoint 镜像（0.6667，``complete_action``
  不镜像 progress——§3.6 进度镜像仅 INTERRUPTED/RESUMED 两事件，E-P3-28）；
  §5.3 A4 表"COMPLETED / 1.0" = ``progress_of(action, 30)`` 派生权威值
  （D-P3-08：运行时权威值恒为派生），断言 10 的 1.0 点用派生口径；
- ``Scheduler.abort_action`` 门面仅返回新 RuntimeState（E-P3-39⑥ 与模块级
  签名对齐，world 不变——P1 D-5 纯簿记）；
- import 纪律（任务硬规则 4）：本文件直接子模块导入、无星号导入，不 import
  datetime/time/random/asyncio/provider/LLM/网络库。
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.engine_v2.core.action_lifecycle import (
    ActiveAction,
    IllegalTransitionError,
    LifecycleEvent,
    progress_of,
    transition_action,
)
from src.engine_v2.core.action_registry import (
    ActionRegistry,
    ActionSpec,
    ActionTypeId,
    DurationPolicy,
)
from src.engine_v2.core.actions import (
    ActionLifecycleStatus,
    ActionProposal,
    ActionTiming,
)
from src.engine_v2.core.cascade import CascadeTriggerRegistry
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.events import DomainEvent
from src.engine_v2.core.ids import ActionInstanceId
from src.engine_v2.core.interrupt import DecisionBoundary
from src.engine_v2.core.reducer import apply_committed_effects
from src.engine_v2.core.revalidation import RevalidationOutcome
from src.engine_v2.core.revision import INITIAL_WORLD_REVISION
from src.engine_v2.core.scheduler import (
    Scheduler,
    SchedulerOutcome,
    TimePolicy,
    scheduler_fingerprint,
)
from src.engine_v2.core.serialization import (
    assert_json_clean,
    deep_copy_via_roundtrip,
    dump_json,
    load_json,
)
from src.engine_v2.core.snapshot import restore_snapshot, snapshot
from src.engine_v2.core.state import RuntimeState, WorldState
from src.engine_v2.core.trace import TraceKind
from tests.engine_v2.core import conftest as p3
from src.engine_v2.core.reducer import install_write_barrier

#: M1 背景 blink 行动类型（NPC，fixed 1 tick，事件驱动完成——completion_trigger=None）
BLINK = ActionTypeId("npc.blink")


# —— 观察口辅助（replay 比较键口径：D-P3-15①/D-P3-20）——


def _event_key(event: DomainEvent, outcome: SchedulerOutcome) -> tuple[str, int, int]:
    """逐事件键 ``(event_type, world_revision, 事件发生刻)``。

    发生刻 = 本次调用的 ``ticks_processed`` 水位：调度器不打逻辑戳于事务/事件
    （D-P2-18/D-P3-20：``event.logical_tick`` 恒 None），发生刻由事件在
    ``outcome.events`` 中的位置 + 调用 tick 水位承载（一次 ff 调用的事件全部
    发生于该调用到达的水位刻）。uuid4 标识不入键（D-P3-15①/D-P3-20：数量/运行内唯一性/
    前缀/位置同构比较，不跨运行比原始值）。
    """
    return (event.event_type, int(event.world_revision), outcome.ticks_processed)


def _event_keys(outcome: SchedulerOutcome) -> list[tuple[str, int, int]]:
    return [_event_key(e, outcome) for e in outcome.events]


def _canonical_payload(payload: dict) -> str:
    """effect payload 的确定性投影（typed ID → str；键排序）。"""
    return json.dumps(payload, sort_keys=True, default=str)


def _outcome_signature(outcome: SchedulerOutcome) -> tuple:
    """M3(a) 双运行 outcome 逐项比较键（D-P3-15①/②：排除 uuid4 原始值）。

    - events：逐事件键（发生刻 = 调用水位）；
    - transactions：(status, base, commit, 逐 effect (类型, 目标实体, sequence,
      规范化 payload))；
    - transitions：(from, event, to, at_tick)；
    - traces：(kind, world_revision, logical_tick, producer_id)。
    """
    events = [_event_key(e, outcome) for e in outcome.events]
    transactions = [
        (
            t.status.value,
            int(t.base_revision),
            None if t.commit_revision is None else int(t.commit_revision),
            tuple(
                (
                    ce.effect.effect_type,
                    str(ce.effect.target.entity_id),
                    ce.sequence,
                    _canonical_payload(ce.effect.payload),
                )
                for ce in sorted(t.effects, key=lambda c: c.sequence)
            ),
        )
        for t in outcome.transactions
    ]
    transitions = [
        (tr.from_status.value, tr.event.value, tr.to_status.value, tr.at_tick)
        for tr in outcome.transitions
    ]
    traces = [
        (
            r.kind.value,
            None if r.world_revision is None else int(r.world_revision),
            r.logical_tick,
            None if r.producer_id is None else str(r.producer_id),
        )
        for r in outcome.trace_records
    ]
    return (events, transactions, transitions, traces)


# ══════════════════════════════════════════════════════════════════════
# G3-1（§5.2/§5.3/§5.4）：Gate 场景 17 断言
# ══════════════════════════════════════════════════════════════════════


def test_gate_scenario_travel_interrupt(
    gate_state: tuple[WorldState, RuntimeState, Scheduler, ActionProposal],
) -> None:
    """G3-1：travel 中断 Gate 场景（S0→S8 暂停点 9 断言 + 分支 A 4 + 分支 B 4）。"""
    world, runtime, scheduler, proposal = gate_state

    # —— S1：提交（t=0）→ ACCEPT、当刻立即开跑（D-P3-19 两跳复合）——
    world, runtime, decision = scheduler.submit_proposal(world, runtime, proposal)
    assert decision.outcome is RevalidationOutcome.ACCEPT
    act_s2 = runtime.active_actions[p3.P1_INSTANCE_ID]

    # —— S2–S8：单次 fast_forward 至 B1 暂停点（事件驱动快进，D-P3-03）——
    world8, runtime8, outcome8 = scheduler.fast_forward(world, runtime)
    act8 = runtime8.active_actions[p3.P1_INSTANCE_ID]

    # G3-1#1（S7，D-P3-10/E-P3-13）：暂停 = B1 玩家 blocking 命中
    assert outcome8.paused is True
    assert outcome8.pause_reason is not None
    assert outcome8.pause_reason.kind == "decision_boundary"
    assert outcome8.pause_reason.boundary_id == "B1"

    # G3-1#2（S7）：暂停点恰为 tick 12（ev_enc@12 驱动，无逐 tick 迭代）
    assert runtime8.logical_tick == 12
    assert outcome8.ticks_processed == 12

    # G3-1#3（S6，D-P2-06）：txn_1（create ent_bandit）恰一次提交 → R1
    assert world8.world_revision == INITIAL_WORLD_REVISION.next()

    # G3-1#4（S7，D-P3-25）：act_1 迁 INTERRUPTED（B1.interrupt=True）
    assert act8.status is ActionLifecycleStatus.INTERRUPTED

    # G3-1#5（S7，E-P3-28 / G3-1 断言 4）：INTERRUPTED 迁移后存储 progress
    # 镜像恰为 12/30（纯派生值，非累加）
    assert act8.progress == 12 / 30

    # G3-1#6（S2/S3，D-P3-08）：预算不变——暂停不消耗逻辑时间
    assert act_s2.start_tick == 0
    assert act8.start_tick == 0
    assert act8.expected_end_tick == 30

    # G3-1#7（S7）：base_world_revision re-anchor 至 R1 + 末次迁移审计刻 12
    assert act8.base_world_revision == INITIAL_WORLD_REVISION.next()
    assert act8.last_transition_tick == 12

    # G3-1#8（S8，D-P3-25/D-P3-22）：队列恰为 [cp@20, end@30]——cp@10 已消费、
    # ev@12 已消费且**不重复入队**（条目消费唯一）；entry_id 保 sch_ 前缀、kind 保形
    assert [(e.kind, e.due_tick) for e in runtime8.scheduler_queue] == [
        ("action_checkpoint", 20),
        ("action_end", 30),
    ]
    assert all(str(e.entry_id).startswith("sch_") for e in runtime8.scheduler_queue)

    # G3-1#9（S7，D-P2-18）：边界命中本身不产生世界写入（position 恒起点）
    assert p3.gate_position(world8) == p3.START_POSITION

    # ══ 分支 A（§5.3）：自同一暂停点 resume（独立深拷贝，E-P3-07/D-P3-11②）══
    worldA, runtimeA = deep_copy_via_roundtrip(world8), deep_copy_via_roundtrip(runtime8)
    worldA, runtimeA, _trA = scheduler.resume_action(worldA, runtimeA, p3.P1_INSTANCE_ID)
    worldF, runtimeF, outcomeA = scheduler.fast_forward(worldA, runtimeA)
    actF = runtimeF.active_actions[p3.P1_INSTANCE_ID]

    # G3-1#10（§5.3 A5，D-P3-08/E-P3-28）：progress 沿时间线单调
    # 0.0 → 10/30 → 12/30 → 20/30 → 1.0。末点为派生值：complete_action 不镜像
    # progress（§3.6 镜像仅 INTERRUPTED/RESUMED 两事件），COMPLETED 存储镜像停
    # 于最后 checkpoint 值 0.6667，§5.3 A4 表"COMPLETED / 1.0" =
    # progress_of(action, 30) 派生权威值（D-P3-08）。
    seq = [
        progress_of(act_s2, 0),  # S2：t=0（开跑）
        progress_of(act8, 10),  # S4：t=10（checkpoint 派生）
        progress_of(act8, 12),  # S7：t=12（暂停；存储镜像 == 派生）
        progress_of(act8, 20),  # A2：t=20（checkpoint 派生）
        progress_of(actF, 30),  # A5：t=30（终点派生 = 1.0）
    ]
    assert seq == [0.0, 10 / 30, 12 / 30, 20 / 30, 1.0]
    assert all(b > a for a, b in zip(seq, seq[1:]))

    # G3-1#11（§5.3 A4）：position 首次且仅在 txn_2 提交处变 dest（世界读为
    # 唯一观察口；暂停点 position 已由 #9 断言为起点）
    set_effects_A = [
        ce
        for t in outcomeA.transactions
        for ce in t.effects
        if ce.effect.effect_type == "core.set_component"
    ]
    assert len(set_effects_A) == 1
    assert set_effects_A[0].effect.target.entity_id == p3.ENT_PLAYER
    assert p3.gate_position(worldF) == p3.DEST_POSITION

    # G3-1#12（§5.3 A4）：全场景事务总数 = 2——txn_1（R0→R1，首次 ff）+
    # txn_2（R1→R2，续跑 ff）；无其他提交
    all_txns = list(outcome8.transactions) + list(outcomeA.transactions)
    assert len(all_txns) == 2
    assert [
        (int(t.base_revision), int(t.commit_revision)) for t in all_txns
    ] == [(0, 1), (1, 2)]

    # G3-1#13（§5.3 A4）：COMPLETED + result_summary = {"completed_at": 30}
    assert actF.status is ActionLifecycleStatus.COMPLETED
    assert actF.result_summary == {"completed_at": 30}

    # ══ 分支 B（§5.4）：自同一暂停点 abort（第二个独立深拷贝）══
    worldB, runtimeB = deep_copy_via_roundtrip(world8), deep_copy_via_roundtrip(runtime8)
    # 门面返回仅新 RuntimeState（E-P3-39⑥，与模块级签名对齐；world 不变，P1 D-5）
    runtimeB = scheduler.abort_action(worldB, runtimeB, p3.P1_INSTANCE_ID)
    actB = runtimeB.active_actions[p3.P1_INSTANCE_ID]
    worldB2, runtimeB2, outcomeB = scheduler.fast_forward(worldB, runtimeB)

    # G3-1#14（§5.4 B1，D-P3-25）：abort = FAILED + result_summary 三元 +
    # 终态剪除队列条目（cp@20/end@30 → 空）
    assert actB.status is ActionLifecycleStatus.FAILED
    assert actB.result_summary == {"reason": "aborted", "tick": 12, "progress": 0.4}
    assert runtimeB.scheduler_queue == []

    # G3-1#15（§5.4 B2）：abort 后续 ff = 确定性终点（队列耗尽），时钟停在 12
    assert outcomeB.paused is False
    assert outcomeB.pause_reason is not None
    assert outcomeB.pause_reason.kind == "terminal"
    assert runtimeB2.logical_tick == 12
    assert outcomeB.ticks_processed == 12

    # G3-1#16（§5.4）：世界不被 abort 改动（纯 RuntimeState 簿记，P1 D-5）：
    # revision 停 R1、position 全程起点
    assert worldB2.world_revision == INITIAL_WORLD_REVISION.next()
    assert p3.gate_position(worldB2) == p3.START_POSITION

    # G3-1#17（D-P3-25）：终态记录保留于 active_actions（剪除仅队列条目，
    # 不剪记录；终端可检查）
    assert p3.P1_INSTANCE_ID in runtimeB2.active_actions


# ══════════════════════════════════════════════════════════════════════
# G3-2（§6.2）：队列/运行时序列化往返
# ══════════════════════════════════════════════════════════════════════


def test_queue_serialization(
    gate_state: tuple[WorldState, RuntimeState, Scheduler, ActionProposal],
) -> None:
    """G3-2：RuntimeState JSON 往返恒等 + 往返后续跑等价。

    ``dump_json → assert_json_clean → load_json`` 后：队列逐条恒等（entry_id
    保 ``sch_`` 前缀与类型）、active_actions/actor_wakeups/logical_tick/
    pending_proposals 恒等；往返运行时上 resume+ff 续跑的事件键序列与
    独立深拷贝路径恒同（D-P3-15①）。
    """
    world, runtime, scheduler, proposal = gate_state
    world8, runtime8, _outcome8 = p3.gate_run_to_pause(
        scheduler, world, runtime, proposal
    )

    text = dump_json(runtime8)
    assert_json_clean(json.loads(text))  # 全 RuntimeState JSON-clean（无二进制/函数）
    roundtripped = load_json(RuntimeState, text)

    # 队列逐条恒等（kind / due_tick / payload / entry_id，sch_ 前缀保形）
    assert [(e.kind, e.due_tick, e.payload) for e in roundtripped.scheduler_queue] == [
        (e.kind, e.due_tick, e.payload) for e in runtime8.scheduler_queue
    ]
    assert [str(e.entry_id) for e in roundtripped.scheduler_queue] == [
        str(e.entry_id) for e in runtime8.scheduler_queue
    ]
    assert all(
        str(e.entry_id).startswith("sch_") for e in roundtripped.scheduler_queue
    )
    # 其余调度簿记恒等
    assert roundtripped.active_actions == runtime8.active_actions
    assert roundtripped.actor_wakeups == runtime8.actor_wakeups
    assert roundtripped.pending_proposals == runtime8.pending_proposals
    assert roundtripped.logical_tick == runtime8.logical_tick == 12

    # 往返后续跑 vs 独立深拷贝续跑：事件键序列 + 水位恒等
    world1, runtime1 = deep_copy_via_roundtrip(world8), roundtripped
    world1, runtime1, _t1 = scheduler.resume_action(world1, runtime1, p3.P1_INSTANCE_ID)
    world1, runtime1, o1 = scheduler.fast_forward(world1, runtime1)
    world2, runtime2 = deep_copy_via_roundtrip(world8), deep_copy_via_roundtrip(runtime8)
    world2, runtime2, _t2 = scheduler.resume_action(world2, runtime2, p3.P1_INSTANCE_ID)
    world2, runtime2, o2 = scheduler.fast_forward(world2, runtime2)
    assert _event_keys(o1) == _event_keys(o2)
    assert o1.ticks_processed == o2.ticks_processed == 30
    assert _outcome_signature(o1) == _outcome_signature(o2)


# ══════════════════════════════════════════════════════════════════════
# G3-3（§6.2）：progress 跨中断语义
# ══════════════════════════════════════════════════════════════════════


def test_progress_across_interrupt(
    gate_state: tuple[WorldState, RuntimeState, Scheduler, ActionProposal],
) -> None:
    """G3-3（文档口径，§6.2）：progress 在中断/恢复/中止/快照各路径的语义。"""
    world, runtime, scheduler, proposal = gate_state
    world8, runtime8, _o8 = p3.gate_run_to_pause(scheduler, world, runtime, proposal)
    act8 = runtime8.active_actions[p3.P1_INSTANCE_ID]

    # (1) 暂停点 progress == 12/30 精确（存储镜像 == 派生值，E-P3-28/D-P3-08）
    assert act8.progress == 12 / 30
    assert progress_of(act8, 12) == 12 / 30

    # (2) resume → checkpoint 序列 0.4 → 0.6667 → 1.0 单调（真实切片推进：
    # t=20 由 checkpoint 写入镜像，t=30 终点取派生值——complete_action 不镜像）
    worldA, runtimeA, _t = scheduler.resume_action(world8, runtime8, p3.P1_INSTANCE_ID)
    worldA, runtimeA, o20 = scheduler.fast_forward(worldA, runtimeA, max_tick=20)
    act20 = runtimeA.active_actions[p3.P1_INSTANCE_ID]
    assert o20.paused is True
    assert o20.pause_reason is not None
    assert o20.pause_reason.kind == "bounded"  # max_tick 边界（非 B1 重暂停）
    assert act20.progress == 20 / 30  # t=20 checkpoint 镜像（re-anchor 后写入）
    worldF, runtimeF, oF = scheduler.fast_forward(worldA, runtimeA)
    actF = runtimeF.active_actions[p3.P1_INSTANCE_ID]
    assert [act8.progress, act20.progress, progress_of(actF, 30)] == [
        12 / 30,
        20 / 30,
        1.0,
    ]
    assert progress_of(actF, 30) > act20.progress > act8.progress  # 严格单调

    # (3) abort 分支：result_summary["progress"] == 0.4（abort 时刻的派生值
    # 入摘要）+ 终态记录保留（D-P3-25）
    worldB, runtimeB = deep_copy_via_roundtrip(world8), deep_copy_via_roundtrip(runtime8)
    runtimeB = scheduler.abort_action(worldB, runtimeB, p3.P1_INSTANCE_ID)
    actB = runtimeB.active_actions[p3.P1_INSTANCE_ID]
    assert actB.result_summary is not None
    assert actB.result_summary["progress"] == 0.4
    assert p3.P1_INSTANCE_ID in runtimeB.active_actions

    # (4) snapshot 往返后 progress 重算恒等（派生与存储值无关：restore 出的
    # 记录经同一 progress_of 重算，值恒同）
    snap = snapshot(world8, runtime8, "p3-g3-3")
    worldR, runtimeR = restore_snapshot(snap)
    actR = runtimeR.active_actions[p3.P1_INSTANCE_ID]
    assert actR.progress == act8.progress  # 存储镜像往返恒等
    assert progress_of(actR, 12) == 12 / 30
    assert progress_of(actR, 20) == 20 / 30
    assert progress_of(actR, 30) == 1.0


# ══════════════════════════════════════════════════════════════════════
# G3-4（§6.2）：回放确定性
# ══════════════════════════════════════════════════════════════════════


def test_replay_determinism(
    gate_state: tuple[WorldState, RuntimeState, Scheduler, ActionProposal],
    gate_registry: ActionRegistry,
    gate_time_policy: TimePolicy,
    gate_boundary: DecisionBoundary,
) -> None:
    """G3-4：(a) 双 restore 确定性 / (b) snapshot vs 深拷贝路径 / (c) effects
    重放 / (d) 指纹探针。

    回放拒绝 = 测试层指纹失配检查（``scheduler_fingerprint`` 三输入面；引擎
    本体不静默回放——失配时由编排层以配置错误拒绝，E-P3-39③）。
    """
    world, runtime, scheduler, proposal = gate_state
    world8, runtime8, _o8 = p3.gate_run_to_pause(scheduler, world, runtime, proposal)
    snap = snapshot(world8, runtime8, "p3-g3-4")

    def branch_a(
        ws: WorldState, rs: RuntimeState
    ) -> tuple[WorldState, RuntimeState, SchedulerOutcome]:
        """分支 A 续跑：resume（t=12）→ 单次 ff 至终点（t=30）。"""
        ws, rs, _t = scheduler.resume_action(ws, rs, p3.P1_INSTANCE_ID)
        return scheduler.fast_forward(ws, rs)

    # (a) 同一 snapshot 两次 restore（每次 restore 独立深拷贝）→ 续跑事件键
    # 序列 + tick 水位恒等（D-P3-15①）
    world1, runtime1 = restore_snapshot(snap)
    world2, runtime2 = restore_snapshot(snap)
    _wf1, _rf1, o1 = branch_a(world1, runtime1)
    _wf2, _rf2, o2 = branch_a(world2, runtime2)
    assert _event_keys(o1) == _event_keys(o2)
    assert o1.ticks_processed == o2.ticks_processed == 30

    # (b) snapshot 路径 vs 无 snapshot 深拷贝路径（S8 直接分叉）→ 事件键恒同
    world3, runtime3 = deep_copy_via_roundtrip(world8), deep_copy_via_roundtrip(runtime8)
    _wf3, _rf3, o3 = branch_a(world3, runtime3)
    assert _event_keys(o1) == _event_keys(o3)
    assert _outcome_signature(o1) == _outcome_signature(o3)

    # (c) apply_committed_effects 重放（reducer.py:843 纯函数；输入世界须处于
    # base_revision，输出 revision = base+1）== 实际世界
    world8c, runtime8c, o8c = p3.gate_run_to_pause(
        scheduler, p3.make_gate_world(), p3.make_initial_runtime(), p3.make_gate_proposal()
    )
    replay1 = apply_committed_effects(
        p3.make_gate_world(), list(o8c.transactions[0].effects)
    )
    assert replay1 == world8c
    assert int(replay1.world_revision) == 1
    world9, runtime9 = deep_copy_via_roundtrip(world8c), deep_copy_via_roundtrip(runtime8c)
    worldA9, runtimeA9, oA9 = branch_a(world9, runtime9)
    replay2 = apply_committed_effects(
        deep_copy_via_roundtrip(world8c), list(oA9.transactions[0].effects)
    )
    assert replay2 == worldA9
    assert int(replay2.world_revision) == 2

    # (d) 指纹（E-P3-39③：三输入面 canonical JSON sha256）——同输入恒等 +
    # 三探针各篡改一字段必变指纹（含 boundaries 面：reason 属边界面）
    fp_base = scheduler_fingerprint(gate_registry, gate_time_policy, (gate_boundary,))
    assert scheduler_fingerprint(gate_registry, gate_time_policy, (gate_boundary,)) == fp_base
    spec15 = ActionSpec(
        **{
            **p3.travel_spec().model_dump(),
            "duration_policy": {"kind": "hint", "hint_scale": 1.5},
        }
    )
    reg15 = ActionRegistry(specs={**gate_registry.specs, p3.TRAVEL: spec15})
    assert (
        scheduler_fingerprint(reg15, gate_time_policy, (gate_boundary,)) != fp_base
    )
    tp20 = TimePolicy(checkpoint_interval_ticks=20)
    assert scheduler_fingerprint(gate_registry, tp20, (gate_boundary,)) != fp_base
    b_ambush = DecisionBoundary(**{**gate_boundary.model_dump(), "reason": "ambush"})
    assert scheduler_fingerprint(gate_registry, gate_time_policy, (b_ambush,)) != fp_base


# ══════════════════════════════════════════════════════════════════════
# §5.5 M1：背景 blink 不干扰 Gate 暂停
# ══════════════════════════════════════════════════════════════════════


def _blink_spec() -> ActionSpec:
    """M1 NPC blink：fixed 1 tick、interruptible、事件驱动完成（无
    completion_trigger → 到点 complete、零 effect、零提交）。"""
    return ActionSpec(
        action_id=BLINK,
        executor="npc.blink_system",
        duration_policy=DurationPolicy(kind="fixed", duration_ticks=1),
        interruptible=True,
    )


def _m1_world() -> WorldState:
    """Gate 世界 + 裸 NPC 实体（无组件；blink 不需要组件面）。"""
    base = p3.make_gate_world()
    return WorldState(
        entities={**base.entities, p3.ENT_NPC: EntityRecord(entity_id=p3.ENT_NPC)}
    )


def _m1_scheduler() -> Scheduler:
    """M1 装配：Gate 口径 + blink 注册表变体（conftest 工厂的同款参数面）。"""
    install_write_barrier()
    return Scheduler(
        ActionRegistry(specs={**p3.make_gate_registry().specs, BLINK: _blink_spec()}),
        authority_policy=p3.make_gate_authority_policy(),
        origin=p3.ORIGIN_PROVENANCE,
        time_policy=p3.make_gate_time_policy(),
        boundaries=[p3.make_gate_boundary()],
        trigger_registry=CascadeTriggerRegistry(),
        named_triggers=frozenset(
            {
                (p3.TRIGGER_ENCOUNTER, p3.make_encounter_stub()),
                (p3.TRIGGER_ARRIVAL, p3.make_arrival_stub()),
            }
        ),
        player_actor_ids=frozenset({p3.ENT_PLAYER}),
        assert_barrier_armed=True,
    )


def test_m1_background_blinks_no_pause() -> None:
    """§5.5 M1（200 背景 blink，t=0..199，fixed 1 tick）：

    (a) 无 t<12 暂停——单次 ff 直达 B1（ticks_processed == 12）；
    (b) 玩家 wakeup 零条目（actor_wakeups 空、队列无 kind="wakeup"）；
    (c) 暂停前 blink COMPLETED 迁移恰 12 条（k=0..11，t=1..12 完成）；
    (d) resume 续跑全程玩家暂停恰 1 次（B1 一次性命中）。
    """
    scheduler = _m1_scheduler()
    world = _m1_world()
    runtime = p3.make_initial_runtime()

    # 200 个 blink 提案 t=0 全部提交（k=0 当刻开跑；k≥1 预约 action_start@k）
    for k in range(200):
        proposal = ActionProposal(
            proposal_id=ActionInstanceId(f"act_blink_{k:03d}"),
            actor_id=p3.ENT_NPC,
            action_id=BLINK,
            arguments={},
            timing=ActionTiming(earliest_start_tick=k),
            base_world_revision=INITIAL_WORLD_REVISION,
            provenance=p3.ORIGIN_PROVENANCE,
        )
        world, runtime, decision = scheduler.submit_proposal(world, runtime, proposal)
        assert decision.outcome is RevalidationOutcome.ACCEPT

    # travel 提案（P1，base R0——提交序在 blink 后，世界仍 R0，无 stale）
    travel = p3.make_gate_proposal()
    world, runtime, decision = scheduler.submit_proposal(world, runtime, travel)
    assert decision.outcome is RevalidationOutcome.ACCEPT

    pre_active = dict(runtime.active_actions)  # 实例 → action_id 映射（ff 前快照）

    # (a) 单次 ff 直达 B1 暂停点
    world8, runtime8, o1 = scheduler.fast_forward(world, runtime)
    assert o1.paused is True
    assert o1.pause_reason is not None
    assert o1.pause_reason.kind == "decision_boundary"
    assert o1.pause_reason.boundary_id == "B1"
    assert o1.pause_reason.tick == 12
    assert o1.ticks_processed == 12  # t<12 无任何暂停

    # (b) 玩家 wakeup 零条目（B1 的 actor 是玩家：走中断/暂停路，非 NPC
    # notices 路——无 wakeup 双记录）
    assert runtime8.actor_wakeups == []
    assert not any(e.kind == "wakeup" for e in runtime8.scheduler_queue)

    # (c) 暂停前 blink COMPLETED 迁移恰 12 条（k=0..11：t=1..12 完成；
    # k=12 的 start 与 ev_enc 同刻批内，完成于 t=13——暂停点之后）
    blink_completed = [
        tr
        for tr in o1.transitions
        if tr.instance_id in pre_active
        and pre_active[tr.instance_id].action_id == BLINK
        and tr.to_status is ActionLifecycleStatus.COMPLETED
    ]
    assert len(blink_completed) == 12

    # (d) resume 续跑至终点：玩家暂停全程恰 1 次（B1 一次性；B1 条件依赖
    # create_entity 事件流，续跑期无新 create_entity → 不重命中）
    worldR, runtimeR, _t = scheduler.resume_action(world8, runtime8, p3.P1_INSTANCE_ID)
    worldT, runtimeT, o2 = scheduler.fast_forward(worldR, runtimeR)
    assert o2.paused is False
    assert o2.pause_reason is not None
    assert o2.pause_reason.kind == "terminal"
    total_player_pauses = sum(
        1
        for o in (o1, o2)
        if o.paused
        and o.pause_reason is not None
        and o.pause_reason.kind == "decision_boundary"
    )
    assert total_player_pauses == 1


# ══════════════════════════════════════════════════════════════════════
# §5.5 M2：position 提交隔离 + trace 三口 + 伪造 progress 探针
# ══════════════════════════════════════════════════════════════════════


def test_m2_position_commit_isolation(
    gate_state: tuple[WorldState, RuntimeState, Scheduler, ActionProposal],
) -> None:
    """§5.5 M2（切片 ff：max_tick=10/12/20/∞）：

    (a) 各切片边界 position 恒起点、唯 t=30 提交后为 dest；
    (b) 唯一 position 变更事务 = txn_2（commit R1→R2），其 outcome 含
        AUTHORITY_DECISION / VALIDATION_DECISION / TRANSACTION(COMMITTED) 三口；
    (c) 暂停点存储 progress == 0.4 ≠ 1.0；
    (d) 伪造存储 progress（1.0）不影响派生（progress_of 纯时钟推导，D-P3-08）。
    """
    world, runtime, scheduler, proposal = gate_state
    world, runtime, _d = scheduler.submit_proposal(world, runtime, proposal)

    # 切片 1：t=0→10（bounded）
    w10, r10, o10 = scheduler.fast_forward(world, runtime, max_tick=10)
    assert o10.paused is True
    assert o10.pause_reason is not None and o10.pause_reason.kind == "bounded"
    assert p3.gate_position(w10) == p3.START_POSITION  # (a) S4 观察点

    # 切片 2：t=10→12（B1 暂停）
    w12, r12, o12 = scheduler.fast_forward(w10, r10, max_tick=12)
    assert o12.paused is True
    assert o12.pause_reason is not None and o12.pause_reason.kind == "decision_boundary"
    assert p3.gate_position(w12) == p3.START_POSITION  # (a) S7 观察点
    act12 = r12.active_actions[p3.P1_INSTANCE_ID]
    assert act12.progress == 0.4  # (c) 暂停 progress 0.4 ≠ 1.0
    assert progress_of(act12, 12) != 1.0

    # 切片 3：resume → t=12→20（bounded；cp@20 checkpoint）
    w20a, r20a, _t = scheduler.resume_action(w12, r12, p3.P1_INSTANCE_ID)
    w20, r20, o20 = scheduler.fast_forward(w20a, r20a, max_tick=20)
    assert o20.paused is True
    assert o20.pause_reason is not None and o20.pause_reason.kind == "bounded"
    assert p3.gate_position(w20) == p3.START_POSITION  # (a) A2 观察点（dest 未提交）

    # 切片 4：t=20→30（终点；arrival 触发器提交 set_component）
    w30, r30, o30 = scheduler.fast_forward(w20, r20)
    assert o30.paused is False
    assert o30.pause_reason is not None and o30.pause_reason.kind == "terminal"
    assert p3.gate_position(w30) == p3.DEST_POSITION  # (a) 唯终点变 dest

    # (b) 唯一 position 变更事务 = 切片 4 的 txn_2（commit R1→R2）
    pos_effects = [
        (o, ce)
        for o in (o10, o12, o20, o30)
        for t in o.transactions
        for ce in t.effects
        if ce.effect.effect_type == "core.set_component"
        and ce.effect.target.entity_id == p3.ENT_PLAYER
        and ce.effect.target.component_type == p3.COMP_MOVEMENT
    ]
    assert len(pos_effects) == 1
    owning_outcome, ce = pos_effects[0]
    assert owning_outcome is o30
    owning_txn = o30.transactions[0]
    assert int(owning_txn.base_revision) == 1
    assert int(owning_txn.commit_revision) == 2
    assert ce.effect is not None  # CommittedEffect 内嵌 ProposedEffect（自包含）
    kinds30 = {tr.kind for tr in o30.trace_records}
    assert TraceKind.AUTHORITY_DECISION in kinds30  # 授权口：ap_set_movement 命中
    assert TraceKind.VALIDATION_DECISION in kinds30  # 校验口
    txn_records = [tr for tr in o30.trace_records if tr.kind is TraceKind.TRANSACTION]
    assert any(
        tr.payload.get("record", {}).get("status") == "committed" for tr in txn_records
    )  # COMMITTED 事务记录

    # (d) 伪造存储 progress 探针：直构 ActiveAction 副本（屏障不辖制新构造），
    # 存储镜像被篡为 1.0 也不影响纯派生（D-P3-08：运行时权威值恒为派生）
    forged = ActiveAction(**{**act12.model_dump(), "progress": 1.0})
    assert progress_of(forged, 12) == 0.4
    assert progress_of(forged, 30) == 1.0


# ══════════════════════════════════════════════════════════════════════
# §5.5 M3：纯度 / 序列化
# ══════════════════════════════════════════════════════════════════════


def test_m3_purity_and_serialization(
    gate_state: tuple[WorldState, RuntimeState, Scheduler, ActionProposal],
) -> None:
    """§5.5 M3：

    (a) 纯度：同一 S0 提交态两份深拷贝、各单次 ff → outcome 逐项恒等
        （D-P3-15①/② 键投影；uuid4 原始值不跨运行比较）；
    (b) S8 snapshot/restore 续跑 vs 无 snapshot 深拷贝续跑 → 事件键序列恒同；
    (c) 静态 import 边界（asyncio/datetime/time/random 零 import）由
        ``test_import_boundary.py`` 的 P3 专项谓词机械强制（P3_SUBMODULES 7
        文件 + P3_TEST_FILES 10 文件——G3-5 口径），本行仅为口径锚点；
    (d) RuntimeState 全字段 JSON-clean（``assert_json_clean`` 逐字段）。
    """
    world, runtime, scheduler, proposal = gate_state
    world, runtime, _d = scheduler.submit_proposal(world, runtime, proposal)

    # (a) 双深拷贝、双 ff、逐项恒等
    world1, runtime1 = deep_copy_via_roundtrip(world), deep_copy_via_roundtrip(runtime)
    world2, runtime2 = deep_copy_via_roundtrip(world), deep_copy_via_roundtrip(runtime)
    world1, runtime1, o1 = scheduler.fast_forward(world1, runtime1)
    world2, runtime2, o2 = scheduler.fast_forward(world2, runtime2)
    assert _outcome_signature(o1) == _outcome_signature(o2)
    assert world1 == world2  # 世界逐字段恒等（同 R1、同实体集、同组件）

    # (b) snapshot/restore 续跑 vs 无 snapshot 深拷贝续跑
    snap = snapshot(world1, runtime1, "p3-m3")
    worldS, runtimeS = restore_snapshot(snap)
    worldS, runtimeS, _tS = scheduler.resume_action(worldS, runtimeS, p3.P1_INSTANCE_ID)
    worldS, runtimeS, o_snap = scheduler.fast_forward(worldS, runtimeS)
    worldD, runtimeD = deep_copy_via_roundtrip(world1), deep_copy_via_roundtrip(runtime1)
    worldD, runtimeD, _tD = scheduler.resume_action(worldD, runtimeD, p3.P1_INSTANCE_ID)
    worldD, runtimeD, o_direct = scheduler.fast_forward(worldD, runtimeD)
    assert _event_keys(o_snap) == _event_keys(o_direct)
    assert o_snap.ticks_processed == o_direct.ticks_processed == 30

    # (c) 静态 import 边界：见模块 docstring 口径锚点（机械检查在
    # test_import_boundary.py，P3 专项谓词 + P3_TEST_FILES 逐文件 provider/LLM 检查）。

    # (d) RuntimeState 全字段 JSON-clean（逐字段取 model_dump 纯数据投影）
    dumped = runtimeD.model_dump()
    assert_json_clean(dumped)
    for field_name in RuntimeState.model_fields:
        assert_json_clean(dumped[field_name])


# ══════════════════════════════════════════════════════════════════════
# 错误路径（G3-3）：invalid spec（fixture 无关探针）+ unknown action（Gate
# 语境）+ IllegalTransition（Gate 语境复用 S8 暂停点）
# ══════════════════════════════════════════════════════════════════════


def test_invalid_spec_gate_context() -> None:
    """G3-3 错误路径① invalid spec：fixture 无关的校验层探针。

    非法 spec 属**参数 schema 校验**（``model_validate`` 构造期拒绝，K7
    可检查不静默），与 Gate 场景状态无关（不涉世界/队列/时钟）——故此探针
    不装配 Gate 场景、不依赖 §5.1 fixture 状态，仅以 conftest §5.1 travel
    spec 常量为有效基线构造非法变体；其余两条错误路径（unknown action /
    IllegalTransition）由 ``test_unknown_action_gate_context`` /
    ``test_illegal_transition_gate_context`` 在 Gate 语境复现（满足 §6.2
    G3-3"在 Gate 场景内复现"口径）。单元级全矩阵另见
    test_action_registry.py（extra_forbid / TestActionSpecContract）。
    """
    # ① ActionSpec extra 字段 → extra=forbid（ContractModel，entity.py:51）
    with pytest.raises(ValidationError):
        ActionSpec.model_validate({**p3.travel_spec().model_dump(), "__bogus__": 1})
    # ② ActionSpec 缺必填字段（action_id 必填）→ ValidationError
    data = p3.travel_spec().model_dump()
    del data["action_id"]
    with pytest.raises(ValidationError):
        ActionSpec.model_validate(data)
    # ③ 注册表键一致性：键 != spec.action_id → 构造期拒绝（P1
    # active_actions 键一致性同款纪律，D-P3-06 数据层）
    with pytest.raises(ValidationError):
        ActionRegistry(specs={ActionTypeId("travel2"): p3.travel_spec()})


def test_unknown_action_gate_context(
    gate_state: tuple[WorldState, RuntimeState, Scheduler, ActionProposal],
) -> None:
    """G3-3 错误路径② unknown action：Gate 场景内复现（§6.3 A5 口径逐条）。

    (1) 场景内发生错误：先 ``submit_proposal`` 未注册 ``flying``（A5 探针）
        → ``UnknownActionError`` 于 registry 查找点抛出、被 ``submit_proposal``
        捕获转 FAILED 轨迹（E-P3-39⑧ 次序第 1 步：registry 查找先于
        revalidate，错误路径不创建 PROPOSED ActiveAction 记录、不查迁移表）；
        A5 口径逐条：不崩溃、队列零残留、世界零变更、诊断串含 action_id，
        另 F2-12 pending_proposals 簿记（REJECT 留痕 = 提案仍在列表 +
        RevalidationDecision REJECT 记录；全量残留断言另见
        test_p3_adversarial.py TestA5）；
    (2) 时间线不受污染：错误发生后同场景内继续 Gate 主时序（提交 P1 →
        fast_forward）→ t=12 照常暂停（B1 decision boundary）、暂停点
        progress == 12/30 == 0.4（与主场景 G3-1#5 同值）、队列/位置/
        revision/事务口径与主时序逐字一致——证明错误路径发生在场景内
        且场景语义完整。
    """
    world, runtime, scheduler, proposal = gate_state

    # —— (1) A5：未注册 action_id（registry 查找点抛，编排层捕获转 FAILED）——
    flying_id = ActionInstanceId("act_flying")
    flying = ActionProposal(
        proposal_id=flying_id,
        actor_id=p3.ENT_PLAYER,
        action_id=ActionTypeId("flying"),
        arguments={},
        timing=ActionTiming(duration_hint_ticks=10),
        base_world_revision=INITIAL_WORLD_REVISION,
        provenance=p3.ORIGIN_PROVENANCE,
    )
    worldX, runtimeX, decision = scheduler.submit_proposal(world, runtime, flying)
    # REJECT + reason + 诊断串含 action_id（A5 口径逐条）
    assert decision.outcome is RevalidationOutcome.REJECT
    assert decision.reason == "unknown_action"
    assert any("flying" in d for d in decision.details)
    # FAILED 终态记录（无 PROPOSED 中间态，E-P3-39⑧/F2-12 纪律）
    flying_rec = runtimeX.active_actions[flying_id]
    assert flying_rec.status is ActionLifecycleStatus.FAILED
    assert flying_rec.result_summary == {
        "reason": "unknown_action",
        "action_id": "flying",
    }
    assert all(
        r.status is not ActionLifecycleStatus.PROPOSED
        for r in runtimeX.active_actions.values()
    )
    # F2-12 簿记：REJECT 提案留在 pending_proposals（移除仅发生于
    # start_action 成功时）
    assert [p.proposal_id for p in runtimeX.pending_proposals] == [flying_id]
    # 队列零残留（初始 ev_enc@12 原样）+ 世界零变更（R0）
    assert [(e.kind, e.due_tick) for e in runtimeX.scheduler_queue] == [("event", 12)]
    assert worldX == world
    assert worldX.world_revision == INITIAL_WORLD_REVISION

    # —— (2) 继续 Gate 主时序：错误路径不污染场景语义 ——
    worldA, runtimeA, dA = scheduler.submit_proposal(worldX, runtimeX, proposal)
    assert dA.outcome is RevalidationOutcome.ACCEPT
    worldF, runtimeF, outcomeF = scheduler.fast_forward(worldA, runtimeA)
    actF = runtimeF.active_actions[p3.P1_INSTANCE_ID]
    # t=12 照常暂停（B1，主场景 G3-1#1/#2 同值）
    assert outcomeF.paused is True
    assert outcomeF.pause_reason is not None
    assert outcomeF.pause_reason.kind == "decision_boundary"
    assert outcomeF.pause_reason.boundary_id == "B1"
    assert outcomeF.pause_reason.tick == 12
    assert runtimeF.logical_tick == 12
    assert outcomeF.ticks_processed == 12
    # 暂停点 progress == 12/30（与主场景同值，G3-1#5 口径）
    assert actF.status is ActionLifecycleStatus.INTERRUPTED
    assert actF.progress == 12 / 30
    # 时间线与主场景一致：txn_1 恰一次提交 → R1、队列 [cp@20, end@30]、
    # position 恒起点、transitions 恰 S7 一条（INTERRUPTED@12）
    assert worldF.world_revision == INITIAL_WORLD_REVISION.next()
    assert [(int(t.base_revision), int(t.commit_revision)) for t in outcomeF.transactions] == [
        (0, 1)
    ]
    assert [(e.kind, e.due_tick) for e in runtimeF.scheduler_queue] == [
        ("action_checkpoint", 20),
        ("action_end", 30),
    ]
    assert p3.gate_position(worldF) == p3.START_POSITION
    assert [
        (t.from_status.value, t.event.value, t.to_status.value, t.at_tick)
        for t in outcomeF.transitions
    ] == [("active", "interrupted", "interrupted", 12)]


def test_illegal_transition_gate_context(
    gate_state: tuple[WorldState, RuntimeState, Scheduler, ActionProposal],
) -> None:
    """G3-3 错误路径③ IllegalTransition：Gate 场景内复现（§6.3 A2 探针口径）。

    (1) 先把合法 travel 行动推进到 S8 INTERRUPTED 暂停点（与主场景同款
        写法，经 ``gate_run_to_pause``：B1 命中、progress 12/30、队列
        [cp@20, end@30]）；
    (2) 触发一条表外迁移：INTERRUPTED→INTERRUPTED 双中断（对照
        LIFECYCLE_TRANSITIONS 唯一权威选探针——INTERRUPTED 行仅
        RESUMED/ABORTED 出边，A2 探针集）→ ``IllegalTransitionError``
        （消息含 from/to/event，D-P3-16 可检查不静默）；
    (3) 错误后暂停点幂等重报（D-P3-24 入口首检）：直接对暂停态再
        ``fast_forward`` → 返回同一暂停（paused=True、B1、tick=12、
        tick 水位不前进、transactions/events/transitions/errors 全空）、
        队列零残留（队列不变 [cp@20, end@30]）、世界零副作用（revision
        R1、position 恒起点）；
    (4) 终态侧对照：abort（合法 INTERRUPTED→FAILED）后 resume →
        ``IllegalTransitionError``（终态无出边，D-P3-07）——与
        test_scheduler.py 的 ACTIVE 探针互补（终态侧经完整 Gate 场景
        装配达到）。
    """
    world, runtime, scheduler, proposal = gate_state

    # —— (1) 推进至 S8 INTERRUPTED 暂停点（与主场景同款达成写法）——
    world8, runtime8, o8 = p3.gate_run_to_pause(scheduler, world, runtime, proposal)
    assert o8.paused is True
    act8 = runtime8.active_actions[p3.P1_INSTANCE_ID]
    assert act8.status is ActionLifecycleStatus.INTERRUPTED
    assert act8.progress == 12 / 30
    assert runtime8.logical_tick == 12
    queue8 = runtime8.scheduler_queue
    assert [(e.kind, e.due_tick) for e in queue8] == [
        ("action_checkpoint", 20),
        ("action_end", 30),
    ]

    # —— (2) 表外探针：INTERRUPTED→INTERRUPTED 双中断（A2 探针集）——
    with pytest.raises(IllegalTransitionError) as excinfo:
        transition_action(
            runtime8, p3.P1_INSTANCE_ID, LifecycleEvent.INTERRUPTED, at_tick=12
        )
    msg = str(excinfo.value)
    # 消息含 from/to/event 三要素（D-P3-16 ①）
    assert "from=interrupted" in msg
    assert "to=<illegal>" in msg
    assert "event=interrupted" in msg

    # —— (3) D-P3-24 入口首检幂等重报：表外迁移不消耗队列、不推进时钟、
    # 不静默跳过边界、不崩溃 ——
    worldR, runtimeR, oR = scheduler.fast_forward(world8, runtime8)
    assert oR.paused is True
    assert oR.pause_reason is not None
    assert oR.pause_reason.kind == "decision_boundary"
    assert oR.pause_reason.boundary_id == "B1"
    assert oR.pause_reason.tick == 12
    assert oR.ticks_processed == 12
    # 零副作用：四清单全空（SchedulerOutcome 字段为 tuple 型）
    assert oR.transactions == ()
    assert oR.events == ()
    assert oR.transitions == ()
    assert oR.errors == ()
    # tick 水位不前进 + 队列零残留（队列不变）+ 世界零副作用
    assert runtimeR.logical_tick == 12
    assert runtimeR.scheduler_queue == queue8
    assert worldR == world8
    assert worldR.world_revision == INITIAL_WORLD_REVISION.next()
    assert p3.gate_position(worldR) == p3.START_POSITION

    # —— (4) 终态侧对照：abort 后 resume → IllegalTransitionError（FAILED
    # 终态无出边；消息含 from/to/event）——
    wB8, rB8, _oB8 = p3.gate_run_to_pause(
        scheduler,
        p3.make_gate_world(),
        p3.make_initial_runtime(),
        p3.make_gate_proposal(),
    )
    rB8 = scheduler.abort_action(wB8, rB8, p3.P1_INSTANCE_ID)
    assert rB8.active_actions[p3.P1_INSTANCE_ID].status is ActionLifecycleStatus.FAILED
    with pytest.raises(IllegalTransitionError) as excinfo2:
        scheduler.resume_action(wB8, rB8, p3.P1_INSTANCE_ID)
    msg2 = str(excinfo2.value)
    assert "from=failed" in msg2
    assert "event=resumed" in msg2
