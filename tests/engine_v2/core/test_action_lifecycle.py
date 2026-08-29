"""P3-T03 action_lifecycle.py 迁移表层单元测试（设计文档 §3.6 上半全量 + D-P3-07/08/25 口径）。

依据 ``docs/v2/contracts/P3-scheduler-time-action-design.md``：

- **迁移矩阵全表**（§6.1 action_lifecycle 用例口径）：6 状态 × 9 事件 = 54
  格，逐格断言"期望目标态"或 :class:`IllegalTransitionError`（信息含
  from/to/event）；不存在实例 → 抛（同型，信息含 instance/event）；
- **D-P3-07**（六态 + 9 事件 + RESUMED 边）：合法 10 边逐边（含 RESUMED
  返回边、CHECKPOINT 自迁移）；终态（COMPLETED/FAILED）无出边 → 任何事件
  表外抛（迁移不可逆、可断言）；ACTIVE 无直接 ABORTED 边（E-P3-29②）；
- **INTERRUPTED re-anchor**（§5.2 S7 / G3-1 断言 6 / §2.4 刻后求值伪代码）：
  当前世界 revision 由调用方经 ``updates`` 携带 → 新记录
  ``base_world_revision`` 逐字一致（Revision 类型保持）；RESUMED 同口径；
- **progress 镜像**（E-P3-28 / D-P3-08）：INTERRUPTED 与 RESUMED 迁移
  同步更新 ``progress`` 镜像（纯推导、clamp、事件驱动 → None、伪造存储值
  不影响推导、调用方同名值无效）；非镜像事件（如 CHECKPOINT）不强制镜像
  （调用方透传合并）；
- **剪除仅终态**（D-P3-25 ①，全文唯一剪除点）：COMPLETED/FAILED（含
  ABORTED 边与 VALIDATING→FAILED 边）剪除该实例 action_checkpoint /
  action_end / deadline 条目（action_start / wakeup / event 等其他 kind 与
  其他实例条目不动）；INTERRUPTED 为非终态、不剪除任何条目；
- **双中断探针**：INTERRUPTED 实例再 INTERRUPTED → 表外抛；合法序列
  resume → 再中断 → abort（E-P3-29② 对照组）通过；
- **受管/审计字段**：逐迁移自动置 ``last_transition_tick=at_tick``
  （updates 不可覆盖）；``status`` 以表边 to 态为唯一权威（updates 同名
  值无效）；updates 合法字段合并进 ActiveAction（rebuild 模式，与 P1 冻结
  字段逐字对齐）；未知键 / 越界 progress → pydantic ``ValidationError``
  （可检查不静默）；
- **纯函数纪律**：输入 RuntimeState / ActiveAction 不变（frozen 重建）、
  不推进逻辑时钟（D-P3-02 唯一写点 ``set_logical_tick``）、其余
  RuntimeState 字段不触碰；
- **迁移记录**（:class:`LifecycleTransition`）：字段逐字；ContractModel
  （frozen / extra="forbid"）；JSON round-trip 恒等（类型重建保持）；
- **错误族**（D-P3-16 ①）：``IllegalTransitionError ⊂ SchedulerError ⊂
  ValueError``。

本任务范围外（P3-T04 同文件串行，§3.10 单 Owner 纪律）：``progress_of`` /
``apply_checkpoint`` / ``start_action`` / ``resume_action`` / ``abort_action``
/ ``complete_action`` / ``fail_action`` 用例——本文件不含。

全部用例无网络、无 LLM、无 API key、无墙钟（§8.3 P3 专项 import 边界：
禁 ``datetime``/``time``/``random``/``asyncio``）。
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import JsonValue, ValidationError

from src.engine_v2.core.action_lifecycle import (
    LIFECYCLE_TRANSITIONS,
    IllegalTransitionError,
    LifecycleEvent,
    LifecycleTransition,
    abort_action,
    apply_checkpoint,
    complete_action,
    fail_action,
    progress_of,
    resume_action,
    transition_action,
)
from src.engine_v2.core.actions import ActionLifecycleStatus, ActionTypeId, ActiveAction
from src.engine_v2.core.clock import SchedulerError
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.effects import EffectTypeId, EntityTarget, ProposedEffect
from src.engine_v2.core.event_queue import make_scheduled_event
from src.engine_v2.core.ids import (
    ActionInstanceId,
    EffectId,
    ProducerId,
    new_action_instance_id,
    new_entity_id,
)
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.revision import INITIAL_WORLD_REVISION, Revision
from src.engine_v2.core.serialization import dump_json, load_json
from src.engine_v2.core.state import ActorWakeup, RuntimeState, ScheduledEvent, WorldState
from src.engine_v2.core.trace import TraceKind, TraceRecord

# —— 状态/事件短名（测试专用，避免 100 列上限下的冗长参数化行）——

PROPOSED = ActionLifecycleStatus.PROPOSED
VALIDATING = ActionLifecycleStatus.VALIDATING
ACTIVE = ActionLifecycleStatus.ACTIVE
INTERRUPTED = ActionLifecycleStatus.INTERRUPTED
COMPLETED = ActionLifecycleStatus.COMPLETED
FAILED = ActionLifecycleStatus.FAILED

E_ACCEPT = LifecycleEvent.VALIDATION_ACCEPTED
E_REJECT = LifecycleEvent.VALIDATION_REJECTED
E_SCHEDULED = LifecycleEvent.SCHEDULED
E_CHECKPOINT = LifecycleEvent.CHECKPOINT
E_INTERRUPT = LifecycleEvent.INTERRUPTED
E_COMPLETED = LifecycleEvent.COMPLETED
E_FAILED = LifecycleEvent.FAILED
E_RESUMED = LifecycleEvent.RESUMED
E_ABORTED = LifecycleEvent.ABORTED

#: 设计文档 §3.6 / D-P3-07 的合法 10 边（测试侧独立期望表——不镜像实现表，
#: 全矩阵与表结构断言均以此为准）。
_EXPECTED_EDGES: dict[
    tuple[ActionLifecycleStatus, LifecycleEvent], ActionLifecycleStatus
] = {
    (PROPOSED, E_ACCEPT): VALIDATING,
    (PROPOSED, E_REJECT): FAILED,
    (VALIDATING, E_SCHEDULED): ACTIVE,
    (VALIDATING, E_REJECT): FAILED,
    (ACTIVE, E_CHECKPOINT): ACTIVE,
    (ACTIVE, E_INTERRUPT): INTERRUPTED,
    (ACTIVE, E_COMPLETED): COMPLETED,
    (ACTIVE, E_FAILED): FAILED,
    (INTERRUPTED, E_RESUMED): ACTIVE,
    (INTERRUPTED, E_ABORTED): FAILED,
}

#: 全矩阵：6 状态 × 9 事件 = 54 格（§6.1 口径）。
_ALL_CELLS: list[tuple[ActionLifecycleStatus, LifecycleEvent]] = [
    (status, event) for status in ActionLifecycleStatus for event in LifecycleEvent
]

#: 合法 10 边的审计字段探针序列（(from, event, at_tick)，at_tick 逐边可区分）。
_EDGE_PROBES: list[tuple[ActionLifecycleStatus, LifecycleEvent, int]] = [
    (PROPOSED, E_ACCEPT, 0),
    (PROPOSED, E_REJECT, 1),
    (VALIDATING, E_SCHEDULED, 0),
    (VALIDATING, E_REJECT, 2),
    (ACTIVE, E_CHECKPOINT, 20),
    (ACTIVE, E_INTERRUPT, 12),
    (ACTIVE, E_COMPLETED, 30),
    (ACTIVE, E_FAILED, 31),
    (INTERRUPTED, E_RESUMED, 20),
    (INTERRUPTED, E_ABORTED, 30),
]


# —— 测试专用构造助手（确定性 ID，非工厂随机段）——


def _runtime(tick: int = 0, **kwargs: Any) -> RuntimeState:
    """构造 ``logical_tick=tick`` 的测试 RuntimeState。"""
    return RuntimeState(logical_tick=tick, **kwargs)


def _action(
    *,
    status: ActionLifecycleStatus = ACTIVE,
    start_tick: int = 0,
    expected_end_tick: int | None = 30,
    progress: float | None = None,
    base_world_revision: Revision = INITIAL_WORLD_REVISION,
) -> ActiveAction:
    """构造最小合法 ActiveAction（工厂签发 ID，键一致性天然成立）。"""
    return ActiveAction(
        instance_id=new_action_instance_id(),
        action_id=ActionTypeId("travel"),
        actor_id=new_entity_id(),
        status=status,
        start_tick=start_tick,
        expected_end_tick=expected_end_tick,
        progress=progress,
        interruptible=True,
        base_world_revision=base_world_revision,
        provenance=Provenance(producer_id="test.producer", origin=OriginKind.SYSTEM),
    )


def _runtime_with_action(action: ActiveAction, **kwargs: Any) -> RuntimeState:
    """携带一条 active_actions 记录的 RuntimeState（键 = instance_id，合法）。"""
    return _runtime(active_actions={action.instance_id: action}, **kwargs)


def _entry(kind: str, due_tick: int, **payload: JsonValue) -> ScheduledEvent:
    """经 ``make_scheduled_event`` 构造条目（P3 构造点，词表/payload 校验生效）。"""
    return make_scheduled_event(kind, due_tick, payload=payload)


def _gate_queue(instance_id: ActionInstanceId) -> list[ScheduledEvent]:
    """Gate §5.2 S7 点队列：``[cp@20, end@30]``（该实例，入队序即队列序）。"""
    return [
        _entry("action_checkpoint", 20, instance_id=str(instance_id)),
        _entry("action_end", 30, instance_id=str(instance_id)),
    ]


class TestLifecycleEventVocabulary:
    """§3.6：P3 语义层事件词表（9 事件，str-Enum 字面量逐字）。"""

    def test_nine_members_exactly(self) -> None:
        assert len(LifecycleEvent) == 9
        assert {m.name for m in LifecycleEvent} == {
            "VALIDATION_ACCEPTED",
            "VALIDATION_REJECTED",
            "SCHEDULED",
            "CHECKPOINT",
            "INTERRUPTED",
            "COMPLETED",
            "FAILED",
            "RESUMED",
            "ABORTED",
        }

    def test_str_enum_literal_values(self) -> None:
        assert {m.value for m in LifecycleEvent} == {
            "validation_accepted",
            "validation_rejected",
            "scheduled",
            "checkpoint",
            "interrupted",
            "completed",
            "failed",
            "resumed",
            "aborted",
        }
        assert all(isinstance(m.value, str) for m in LifecycleEvent)


class TestTransitionTableStructure:
    """§3.6 / D-P3-07：迁移表结构（六态全键、终态无出边、合法 10 边钉死）。"""

    def test_keys_are_all_six_states(self) -> None:
        assert set(LIFECYCLE_TRANSITIONS) == set(ActionLifecycleStatus)

    def test_terminal_states_have_no_out_edges(self) -> None:
        """终态（COMPLETED/FAILED）无出边——迁移不可逆、可断言（D-P3-07）。"""
        assert LIFECYCLE_TRANSITIONS[COMPLETED] == frozenset()
        assert LIFECYCLE_TRANSITIONS[FAILED] == frozenset()

    def test_edges_match_design_spec(self) -> None:
        """展开全部表边，与测试侧独立期望表（§3.6 / D-P3-07 十边）逐字相等。"""
        actual = {
            (from_status, event, to_status)
            for from_status, edges in LIFECYCLE_TRANSITIONS.items()
            for event, to_status in edges
        }
        expected = {
            (from_status, event, to_status)
            for (from_status, event), to_status in _EXPECTED_EDGES.items()
        }
        assert actual == expected

    def test_edge_shape(self) -> None:
        for edges in LIFECYCLE_TRANSITIONS.values():
            assert isinstance(edges, frozenset)
            for edge in edges:
                assert len(edge) == 2
                assert isinstance(edge[0], LifecycleEvent)
                assert isinstance(edge[1], ActionLifecycleStatus)


class TestMigrationMatrixFullTable:
    """§6.1 迁移矩阵全表：6 × 9 = 54 格，逐格"期望目标态"或 IllegalTransitionError。"""

    @pytest.mark.parametrize(
        "cell",
        _ALL_CELLS,
        ids=[f"{s.value}-{e.value}" for s, e in _ALL_CELLS],
    )
    def test_cell(self, cell: tuple[ActionLifecycleStatus, LifecycleEvent]) -> None:
        from_status, event = cell
        action = _action(status=from_status)
        runtime = _runtime_with_action(action)
        expected = _EXPECTED_EDGES.get(cell)
        if expected is None:
            # 表外（含终态任何事件）→ IllegalTransitionError（信息含 from/to/event）
            with pytest.raises(IllegalTransitionError) as excinfo:
                transition_action(runtime, action.instance_id, event, at_tick=7)
            msg = str(excinfo.value)
            assert f"from={from_status.value}" in msg
            assert f"event={event.value}" in msg
            assert "to=<illegal>" in msg
            assert str(action.instance_id) in msg
            # 错误路径零副作用：输入状态不变
            assert (
                runtime.active_actions[action.instance_id].status is from_status
            )
        else:
            # 合法边 → 期望目标态 + 迁移记录
            new_runtime, transition = transition_action(
                runtime, action.instance_id, event, at_tick=7
            )
            assert (
                new_runtime.active_actions[action.instance_id].status is expected
            )
            assert transition.instance_id == action.instance_id
            assert transition.from_status is from_status
            assert transition.to_status is expected
            assert transition.event is event
            assert transition.at_tick == 7


class TestMissingInstance:
    """§3.6 docstring：实例不存在 → IllegalTransitionError（可检查不静默）。"""

    def test_raises_with_instance_and_event(self) -> None:
        action = _action()
        runtime = _runtime_with_action(action)
        ghost = new_action_instance_id()
        with pytest.raises(IllegalTransitionError) as excinfo:
            transition_action(runtime, ghost, E_INTERRUPT, at_tick=5)
        msg = str(excinfo.value)
        assert "from=<missing>" in msg
        assert "event=interrupted" in msg
        assert str(ghost) in msg

    def test_no_side_effects(self) -> None:
        action = _action()
        runtime = _runtime_with_action(action)
        ghost = new_action_instance_id()
        with pytest.raises(IllegalTransitionError):
            transition_action(runtime, ghost, E_COMPLETED, at_tick=5)
        assert runtime.active_actions[action.instance_id].status is ACTIVE
        assert runtime.logical_tick == 0


class TestInterruptedReanchorGateS7:
    """INTERRUPTED re-anchor（§5.2 S7 / G3-1 断言 6 / §2.4 伪代码）：
    当前世界 revision 由调用方经 updates 携带，本函数合并。"""

    def test_gate_s7_full_state(self) -> None:
        """Gate §5.2 S7 点完整复刻（模块层对 G3-1 断言 3–7 的等价口径）：
        act_1 ACTIVE（start=0/end=30/base R0）、队列 [cp@20, end@30]、t=12、
        世界已经 txn_1 推进至 R1 → INTERRUPTED@12（updates 携带 R1）。"""
        action = _action(start_tick=0, expected_end_tick=30)
        runtime = _runtime(
            tick=12,
            active_actions={action.instance_id: action},
            scheduler_queue=_gate_queue(action.instance_id),
        )
        new_runtime, transition = transition_action(
            runtime,
            action.instance_id,
            E_INTERRUPT,
            at_tick=12,
            updates={"base_world_revision": Revision(1)},
            reason="decision_boundary:B1",
        )
        act = new_runtime.active_actions[action.instance_id]
        # G3-1 断言 3：INTERRUPTED
        assert act.status is INTERRUPTED
        # 断言 4：progress 镜像 == 12/30（精确相等，浮点同构 0.4）
        assert act.progress == 12 / 30
        assert act.progress == 0.4
        # 断言 5：暂停不改时间预算
        assert act.start_tick == 0
        assert act.expected_end_tick == 30
        # 断言 6：re-anchor 至 R1 + 审计字段
        assert act.base_world_revision == Revision(1)
        assert act.last_transition_tick == 12
        # 断言 7：INTERRUPTED 不剪除——队列恰为 [cp@20, end@30]（逐条恒等）
        queue = new_runtime.scheduler_queue
        assert [e.due_tick for e in queue] == [20, 30]
        assert [e.kind for e in queue] == ["action_checkpoint", "action_end"]
        assert [e.entry_id for e in queue] == [
            e.entry_id for e in runtime.scheduler_queue
        ]
        # 迁移记录
        assert transition.from_status is ACTIVE
        assert transition.to_status is INTERRUPTED
        assert transition.event is E_INTERRUPT
        assert transition.at_tick == 12
        assert transition.reason == "decision_boundary:B1"
        # 纯函数：时钟不推进（唯一写点 set_logical_tick，D-P3-02）
        assert new_runtime.logical_tick == 12

    def test_resumed_reanchor_carried_via_updates(self) -> None:
        """RESUMED 边同口径：调用方经 updates 携带当前 revision（D-P3-08 对齐）。"""
        action = _action(status=INTERRUPTED, start_tick=0, expected_end_tick=30)
        runtime = _runtime(
            tick=12,
            active_actions={action.instance_id: action},
            scheduler_queue=_gate_queue(action.instance_id),
        )
        new_runtime, _ = transition_action(
            runtime,
            action.instance_id,
            E_RESUMED,
            at_tick=12,
            updates={"base_world_revision": Revision(1)},
        )
        act = new_runtime.active_actions[action.instance_id]
        assert act.status is ACTIVE
        assert act.base_world_revision == Revision(1)
        # start_tick / expected_end_tick 不变（progress 连续，§2.3）
        assert act.start_tick == 0
        assert act.expected_end_tick == 30

    def test_reanchor_type_preserved(self) -> None:
        """updates 中 Revision 以 JSON 整数携带 → 重建后类型保持 Revision。"""
        action = _action()
        runtime = _runtime_with_action(action)
        new_runtime, _ = transition_action(
            runtime,
            action.instance_id,
            E_INTERRUPT,
            at_tick=12,
            updates={"base_world_revision": 1},
        )
        act = new_runtime.active_actions[action.instance_id]
        assert type(act.base_world_revision) is Revision
        assert act.base_world_revision == Revision(1)


class TestProgressMirror:
    """progress 镜像（E-P3-28 / D-P3-08）：INTERRUPTED 与 RESUMED 同步更新，
    纯派生、不累加、不可篡改；非镜像事件不强制。"""

    def test_interrupted_mirror_derived_at_mid(self) -> None:
        action = _action(start_tick=0, expected_end_tick=30)
        runtime = _runtime_with_action(action)
        new_runtime, _ = transition_action(runtime, action.instance_id, E_INTERRUPT, at_tick=12)
        assert new_runtime.active_actions[action.instance_id].progress == 0.4

    def test_interrupted_mirror_clamp_above_end(self) -> None:
        """clock > end → clamp 1.0（推导式钳制，D-P3-08 一致性）。"""
        action = _action(start_tick=0, expected_end_tick=30)
        runtime = _runtime_with_action(action)
        new_runtime, _ = transition_action(runtime, action.instance_id, E_INTERRUPT, at_tick=35)
        assert new_runtime.active_actions[action.instance_id].progress == 1.0

    def test_interrupted_mirror_clamp_below_start(self) -> None:
        """clock < start → clamp 0.0（公式探针，存储构造可越界而推导不越界）。"""
        action = _action(start_tick=10, expected_end_tick=40)
        runtime = _runtime_with_action(action)
        new_runtime, _ = transition_action(runtime, action.instance_id, E_INTERRUPT, at_tick=5)
        assert new_runtime.active_actions[action.instance_id].progress == 0.0

    def test_interrupted_mirror_event_driven_none(self) -> None:
        """expected_end_tick is None（事件驱动）→ 镜像 None。"""
        action = _action(start_tick=0, expected_end_tick=None)
        runtime = _runtime_with_action(action)
        new_runtime, _ = transition_action(runtime, action.instance_id, E_INTERRUPT, at_tick=12)
        assert new_runtime.active_actions[action.instance_id].progress is None

    def test_stored_progress_forged_does_not_affect_mirror(self) -> None:
        """伪造存储 progress 不影响推导（"不得 2"的镜像口径，E-P3-28）。"""
        action = _action(start_tick=0, expected_end_tick=30, progress=0.99)
        runtime = _runtime_with_action(action)
        new_runtime, _ = transition_action(runtime, action.instance_id, E_INTERRUPT, at_tick=12)
        assert new_runtime.active_actions[action.instance_id].progress == 0.4

    def test_caller_progress_override_inert_on_interrupted(self) -> None:
        """受管字段：INTERRUPTED 迁移中调用方 updates 的 progress 值无效
        （镜像恒为派生值，不可被 effect/调用方篡改）。"""
        action = _action(start_tick=0, expected_end_tick=30)
        runtime = _runtime_with_action(action)
        new_runtime, _ = transition_action(
            runtime,
            action.instance_id,
            E_INTERRUPT,
            at_tick=12,
            updates={"progress": 0.1},
        )
        assert new_runtime.active_actions[action.instance_id].progress == 0.4

    def test_resumed_mirror_derived(self) -> None:
        """RESUMED 迁移同步更新镜像（暂停期间逻辑时间冻结，§2.3）。"""
        action = _action(status=INTERRUPTED, start_tick=0, expected_end_tick=30)
        runtime = _runtime_with_action(action)
        new_runtime, _ = transition_action(runtime, action.instance_id, E_RESUMED, at_tick=12)
        assert new_runtime.active_actions[action.instance_id].progress == 0.4

    def test_checkpoint_self_transition_no_forced_mirror(self) -> None:
        """非镜像事件（CHECKPOINT）不强制镜像：调用方透传值原样合并
        （apply_checkpoint 的 progress 重算属 T04 口径，经 updates 携带）。"""
        action = _action(start_tick=0, expected_end_tick=30)
        runtime = _runtime_with_action(action)
        new_runtime, _ = transition_action(
            runtime,
            action.instance_id,
            E_CHECKPOINT,
            at_tick=20,
            updates={"progress": 0.5, "next_checkpoint_tick": 30},
        )
        act = new_runtime.active_actions[action.instance_id]
        assert act.status is ACTIVE
        assert act.progress == 0.5
        assert act.next_checkpoint_tick == 30


class TestTerminalPruning:
    """剪除仅终态（D-P3-25 ①，全文唯一剪除点）；INTERRUPTED 不剪除。"""

    def _mixed_queue(self, instance_id: ActionInstanceId) -> list[ScheduledEvent]:
        """该实例 3 类剪除 kind + 其他 kind + 其他实例条目（同 kind 对照）。"""
        other = new_action_instance_id()
        return [
            _entry("action_checkpoint", 20, instance_id=str(instance_id)),
            _entry("action_end", 30, instance_id=str(instance_id)),
            _entry("deadline", 40, instance_id=str(instance_id)),
            _entry("wakeup", 15, actor_id=new_entity_id()),
            _entry("action_checkpoint", 25, instance_id=str(other)),
            _entry("event", 12, trigger_id="scenario.encounter_12"),
        ]

    def test_completed_prunes_remaining_entries(self) -> None:
        """ACTIVE→COMPLETED：该实例 cp/end/deadline 剪除，其余条目逐一保留。"""
        action = _action()
        queue = self._mixed_queue(action.instance_id)
        runtime = _runtime_with_action(action, scheduler_queue=queue)
        new_runtime, _ = transition_action(runtime, action.instance_id, E_COMPLETED, at_tick=30)
        rest = new_runtime.scheduler_queue
        # 队列保持插入序（list 字段，非按 due_tick 排序）
        assert [e.due_tick for e in rest] == [15, 25, 12]
        assert [e.kind for e in rest] == ["wakeup", "action_checkpoint", "event"]
        # 其他实例条目（同 kind）保留
        assert rest[1].payload["instance_id"] != str(action.instance_id)
        # 原实例 3 类条目全部消失
        assert not any(
            e.payload.get("instance_id") == str(action.instance_id) for e in rest
        )

    def test_failed_from_active_prunes(self) -> None:
        action = _action()
        queue = self._mixed_queue(action.instance_id)
        runtime = _runtime_with_action(action, scheduler_queue=queue)
        new_runtime, _ = transition_action(runtime, action.instance_id, E_FAILED, at_tick=9)
        assert not any(
            e.payload.get("instance_id") == str(action.instance_id)
            for e in new_runtime.scheduler_queue
        )

    def test_aborted_from_interrupted_prunes(self) -> None:
        """INTERRUPTED→FAILED（ABORTED 边）同样进入终态 → 剪除（D-P3-25 ①）。"""
        action = _action(status=INTERRUPTED)
        queue = self._mixed_queue(action.instance_id)
        runtime = _runtime_with_action(action, scheduler_queue=queue)
        new_runtime, _ = transition_action(
            runtime, action.instance_id, E_ABORTED, at_tick=25
        )
        assert new_runtime.active_actions[action.instance_id].status is FAILED
        assert not any(
            e.payload.get("instance_id") == str(action.instance_id)
            for e in new_runtime.scheduler_queue
        )

    def test_validation_rejected_to_failed_prunes(self) -> None:
        """VALIDATING→FAILED（VALIDATION_REJECTED 边）亦为终态进入 → 剪除：
        剪除判定面是 to_status 终态，而非事件名。"""
        action = _action(status=VALIDATING)
        queue = self._mixed_queue(action.instance_id)
        runtime = _runtime_with_action(action, scheduler_queue=queue)
        new_runtime, _ = transition_action(runtime, action.instance_id, E_REJECT, at_tick=3)
        assert new_runtime.active_actions[action.instance_id].status is FAILED
        assert not any(
            e.payload.get("instance_id") == str(action.instance_id)
            for e in new_runtime.scheduler_queue
        )

    def test_action_start_kind_not_pruned(self) -> None:
        """D-P3-25 ① 明文列举三 kind（cp/end/deadline）——action_start 不在
        剪除面（正常流程该条目已被 start_action 消费，此处钉死口径边界）。"""
        action = _action()
        queue = [
            _entry("action_start", 0, instance_id=str(action.instance_id)),
            _entry("action_checkpoint", 20, instance_id=str(action.instance_id)),
        ]
        runtime = _runtime_with_action(action, scheduler_queue=queue)
        new_runtime, _ = transition_action(runtime, action.instance_id, E_COMPLETED, at_tick=30)
        assert [e.kind for e in new_runtime.scheduler_queue] == ["action_start"]

    def test_interrupted_does_not_prune(self) -> None:
        """INTERRUPTED 为非终态：全部条目保留（§5.2 S8 断言 7 / §6.3 A1 口径）。"""
        action = _action()
        queue = self._mixed_queue(action.instance_id)
        runtime = _runtime_with_action(action, scheduler_queue=queue)
        new_runtime, _ = transition_action(
            runtime, action.instance_id, E_INTERRUPT, at_tick=12
        )
        # 值相等且 entry_id 序列逐一相同（设计口径为内容不变；
        # rebuild 后条目为重建实例，不承诺对象同一性）
        assert new_runtime.scheduler_queue == queue
        assert [e.entry_id for e in new_runtime.scheduler_queue] == [
            e.entry_id for e in queue
        ]

    def test_terminal_with_no_entries_noop(self) -> None:
        """终态进入但无可剪条目 → 队列不变（确定性簿记，无副作用）。"""
        action = _action()
        runtime = _runtime_with_action(action)
        new_runtime, _ = transition_action(runtime, action.instance_id, E_COMPLETED, at_tick=30)
        assert new_runtime.scheduler_queue == []


class TestDoubleInterruptAndSequences:
    """双中断探针与合法序列（E-P3-29②：resume → 再中断 → abort 对照组）。"""

    def test_double_interrupt_raises(self) -> None:
        """双中断探针：INTERRUPTED 实例再 INTERRUPTED → 表外抛
        （INTERRUPTED 出边仅 RESUMED/ABORTED，D-P3-07）。"""
        action = _action()
        runtime = _runtime_with_action(action)
        runtime2, _ = transition_action(runtime, action.instance_id, E_INTERRUPT, at_tick=12)
        assert runtime2.active_actions[action.instance_id].status is INTERRUPTED
        with pytest.raises(IllegalTransitionError) as excinfo:
            transition_action(runtime2, action.instance_id, E_INTERRUPT, at_tick=15)
        msg = str(excinfo.value)
        assert "from=interrupted" in msg
        assert "event=interrupted" in msg
        # 探针零副作用
        assert runtime2.active_actions[action.instance_id].status is INTERRUPTED

    def test_active_has_no_direct_aborted(self) -> None:
        """ACTIVE 无直接 ABORTED 边（E-P3-29② 注：ABORTED 边仅出自 INTERRUPTED）。"""
        action = _action()
        runtime = _runtime_with_action(action)
        with pytest.raises(IllegalTransitionError):
            transition_action(runtime, action.instance_id, E_ABORTED, at_tick=5)

    def test_legal_sequence_resume_reinterrupt_abort(self) -> None:
        """合法序列（LIFECYCLE_TRANSITIONS 为唯一权威）：
        INTERRUPTED@12 → RESUMED@20 → INTERRUPTED@25 → ABORTED@30。"""
        action = _action(start_tick=0, expected_end_tick=30)
        runtime = _runtime(
            tick=12,
            active_actions={action.instance_id: action},
            scheduler_queue=_gate_queue(action.instance_id),
        )
        runtime2, tr2 = transition_action(
            runtime, action.instance_id, E_INTERRUPT, at_tick=12
        )
        assert runtime2.active_actions[action.instance_id].status is INTERRUPTED
        # 中断不剪除：cp@20/end@30 仍在队列（T04 resume 从原条目继续求值）
        assert [e.due_tick for e in runtime2.scheduler_queue] == [20, 30]
        runtime3, tr3 = transition_action(
            runtime2,
            action.instance_id,
            E_RESUMED,
            at_tick=20,
            updates={"base_world_revision": Revision(1)},
        )
        assert runtime3.active_actions[action.instance_id].status is ACTIVE
        assert tr3.from_status is INTERRUPTED
        runtime4, tr4 = transition_action(runtime3, action.instance_id, E_INTERRUPT, at_tick=25)
        assert runtime4.active_actions[action.instance_id].status is INTERRUPTED
        runtime5, tr5 = transition_action(
            runtime4, action.instance_id, E_ABORTED, at_tick=30
        )
        act = runtime5.active_actions[action.instance_id]
        assert act.status is FAILED
        assert act.last_transition_tick == 30
        assert tr5.to_status is FAILED
        # 终态进入 → 剪除剩余条目
        assert runtime5.scheduler_queue == []


class TestManagedAndAuditFields:
    """受管字段（status/last_transition_tick/镜像）与 updates 合并语义。"""

    @pytest.mark.parametrize(
        ("from_status", "event", "at_tick"),
        _EDGE_PROBES,
        ids=[f"{s.value}-{e.value}" for s, e, _ in _EDGE_PROBES],
    )
    def test_last_transition_tick_set_on_every_edge(
        self,
        from_status: ActionLifecycleStatus,
        event: LifecycleEvent,
        at_tick: int,
    ) -> None:
        """审计字段（actions.py:243）：逐迁移自动置 at_tick（D-P3-07 一致性）。"""
        action = _action(status=from_status)
        runtime = _runtime_with_action(action)
        new_runtime, _ = transition_action(
            runtime, action.instance_id, event, at_tick=at_tick
        )
        assert (
            new_runtime.active_actions[action.instance_id].last_transition_tick
            == at_tick
        )

    def test_last_transition_tick_not_overridable(self) -> None:
        """受管字段：updates 中同名 last_transition_tick 无效（自动置 at_tick）。"""
        action = _action()
        runtime = _runtime_with_action(action)
        new_runtime, _ = transition_action(
            runtime,
            action.instance_id,
            E_INTERRUPT,
            at_tick=12,
            updates={"last_transition_tick": 999},
        )
        assert (
            new_runtime.active_actions[action.instance_id].last_transition_tick == 12
        )

    def test_status_from_table_not_from_updates(self) -> None:
        """受管字段：目标态以表边为唯一权威（D-P3-07），updates 的 status 无效。"""
        action = _action()
        runtime = _runtime_with_action(action)
        new_runtime, _ = transition_action(
            runtime,
            action.instance_id,
            E_CHECKPOINT,
            at_tick=20,
            updates={"status": "completed"},
        )
        assert new_runtime.active_actions[action.instance_id].status is ACTIVE

    def test_updates_merge_custom_field(self) -> None:
        """合法字段合并（rebuild 模式，与 P1 冻结字段逐字对齐）。"""
        action = _action()
        runtime = _runtime_with_action(action)
        new_runtime, _ = transition_action(
            runtime,
            action.instance_id,
            E_CHECKPOINT,
            at_tick=20,
            updates={"result_summary": {"note": "probe"}, "next_checkpoint_tick": 30},
        )
        act = new_runtime.active_actions[action.instance_id]
        assert act.result_summary == {"note": "probe"}
        assert act.next_checkpoint_tick == 30
        # 未触碰字段保持原值
        assert act.interruptible is True
        assert act.base_world_revision == INITIAL_WORLD_REVISION

    def test_updates_unknown_key_raises_validation_error(self) -> None:
        """未知键 → pydantic ValidationError（ContractModel extra="forbid"，
        可检查不静默）。"""
        action = _action()
        runtime = _runtime_with_action(action)
        with pytest.raises(ValidationError):
            transition_action(
                runtime, action.instance_id, E_CHECKPOINT, at_tick=20,
                updates={"not_a_field": 1},
            )

    def test_updates_out_of_range_progress_raises(self) -> None:
        """progress 越界（P1 冻结约束 0..1）→ ValidationError（非镜像事件的
        透传值同样受字段约束）。"""
        action = _action()
        runtime = _runtime_with_action(action)
        with pytest.raises(ValidationError):
            transition_action(
                runtime, action.instance_id, E_CHECKPOINT, at_tick=20,
                updates={"progress": 1.5},
            )

    def test_reason_default_none_and_passthrough(self) -> None:
        action = _action()
        runtime = _runtime_with_action(action)
        _, tr_default = transition_action(runtime, action.instance_id, E_INTERRUPT, at_tick=12)
        assert tr_default.reason is None
        _, tr_custom = transition_action(
            runtime, action.instance_id, E_INTERRUPT, at_tick=12, reason="encounter"
        )
        assert tr_custom.reason == "encounter"


class TestPurity:
    """纯函数纪律：输入不可变、时钟不推进、其余 RuntimeState 字段不触碰。"""

    def test_input_runtime_and_action_unchanged(self) -> None:
        action = _action()
        runtime = _runtime(
            tick=12,
            active_actions={action.instance_id: action},
            scheduler_queue=_gate_queue(action.instance_id),
        )
        new_runtime, _ = transition_action(
            runtime, action.instance_id, E_INTERRUPT, at_tick=12
        )
        # 新实例 ≠ 旧实例
        assert new_runtime is not runtime
        assert (
            new_runtime.active_actions[action.instance_id] is not action
        )
        # 输入记录不变（frozen 重建，非原地修改）
        assert runtime.active_actions[action.instance_id].status is ACTIVE
        assert runtime.active_actions[action.instance_id].progress is None
        assert (
            runtime.active_actions[action.instance_id].last_transition_tick == 0
        )
        assert runtime.active_actions[action.instance_id] is action

    def test_clock_not_advanced(self) -> None:
        """transition_action 不是时钟写点（D-P3-02）：at_tick ≠ logical_tick
        时，时钟保持原值（推进由 set_logical_tick 负责）。"""
        action = _action()
        runtime = _runtime_with_action(action, tick=12)
        new_runtime, transition = transition_action(
            runtime, action.instance_id, E_COMPLETED, at_tick=30
        )
        assert new_runtime.logical_tick == 12
        assert transition.at_tick == 30

    def test_other_runtime_fields_untouched(self) -> None:
        action = _action()
        wakeup = ActorWakeup(actor_id=new_entity_id(), due_tick=5, reason="probe")
        runtime = _runtime(
            tick=12,
            active_actions={action.instance_id: action},
            actor_wakeups=[wakeup],
            mode_context={"active": True},
            active_modes=["exploration"],
        )
        new_runtime, _ = transition_action(
            runtime, action.instance_id, E_INTERRUPT, at_tick=12
        )
        assert new_runtime.actor_wakeups == [wakeup]
        assert new_runtime.mode_context == {"active": True}
        assert new_runtime.active_modes == ["exploration"]
        assert new_runtime.lifecycle == runtime.lifecycle


class TestTransitionRecord:
    """LifecycleTransition 记录（ContractModel：frozen / extra=forbid / round-trip）。"""

    def test_is_contract_model(self) -> None:
        assert issubclass(LifecycleTransition, ContractModel)

    def test_frozen_assignment_raises(self) -> None:
        action = _action()
        record = LifecycleTransition(
            instance_id=action.instance_id,
            from_status=ACTIVE,
            to_status=INTERRUPTED,
            event=E_INTERRUPT,
            at_tick=12,
        )
        with pytest.raises(ValueError):
            record.at_tick = 99  # type: ignore[misc]

    def test_extra_field_forbidden(self) -> None:
        action = _action()
        with pytest.raises(ValidationError):
            LifecycleTransition(
                instance_id=action.instance_id,
                from_status=ACTIVE,
                to_status=INTERRUPTED,
                event=E_INTERRUPT,
                at_tick=12,
                bogus=1,  # type: ignore[call-arg]
            )

    def test_json_round_trip_identity(self) -> None:
        """P1 serialization 基础设施：dump_json/load_json round-trip 恒等，
        类型重建保持（typed ID / str-Enum）。"""
        action = _action()
        record = LifecycleTransition(
            instance_id=action.instance_id,
            from_status=ACTIVE,
            to_status=INTERRUPTED,
            event=E_INTERRUPT,
            at_tick=12,
            reason="decision_boundary:B1",
        )
        text = dump_json(record)
        back = load_json(LifecycleTransition, text)
        assert back == record
        assert type(back.instance_id) is ActionInstanceId
        assert back.event is E_INTERRUPT
        assert back.from_status is ACTIVE
        assert back.to_status is INTERRUPTED


class TestErrorHierarchy:
    """错误族（D-P3-16 ①）：IllegalTransitionError ⊂ SchedulerError ⊂ ValueError。"""

    def test_inherits_scheduler_error_and_value_error(self) -> None:
        assert issubclass(IllegalTransitionError, SchedulerError)
        assert issubclass(IllegalTransitionError, ValueError)

    def test_catchable_as_value_error(self) -> None:
        """编排层可经基类统一捕获（可检查不静默，无第三条路）。"""
        action = _action()
        runtime = _runtime_with_action(action)
        with pytest.raises(ValueError):
            transition_action(runtime, action.instance_id, E_ABORTED, at_tick=5)


# ======================================================================
# §3.6 下半（P3-T04a：progress_of / resume_action / abort_action /
# complete_action / fail_action）——同文件串行追加（§3.10 单 Owner 纪律；
# 全部用例复用上方 T03 测试助手层 _action/_runtime/_entry/_gate_queue）。
#
# 本节不含 apply_checkpoint / start_action 用例（同属 §3.6 下半，范围
# 裁定见任务/报告）；表外迁移在迁移表层（TestTransitionAction 全矩阵）
# 已逐格覆盖，本节的表外用例仅钉住各公共入口的同一防线行为。
# ======================================================================


def _pos_effect() -> ProposedEffect:
    """一个确定性位置类 ProposedEffect（complete_action 输入——纯函数只
    原样传出给调用方（Scheduler）经 P2 管道提交，本函数不消费、不写世界）。"""
    return ProposedEffect(
        effect_id=EffectId("eff_" + "0" * 32),
        effect_type=EffectTypeId("set_position"),
        source=ProducerId("test.producer"),
        target=EntityTarget(entity_id=new_entity_id(), field_path="position"),
        payload={"x": 10.0, "y": 20.0},
        base_revision=INITIAL_WORLD_REVISION,
    )


def _gate_a1() -> tuple[ActionInstanceId, RuntimeState, ActiveAction]:
    """Gate §5.2 S7 / §5.3 A1 场景构造：travel 行动 start@0、end@30（周期
    checkpoint 间隔 10，cp@20 已入队），@12 被 Plan Gate 中断——世界
    revision 已推进至 1 并 re-anchor、progress 镜像 0.4、队列保留
    cp@20/end@30（中断不剪除，D-P3-25 ①）。

    返回 ``(instance_id, 中断后 runtime, 中断后 ActiveAction)``。
    """
    action = _action()
    runtime = _runtime_with_action(
        action, scheduler_queue=_gate_queue(action.instance_id)
    )
    runtime, _ = transition_action(
        runtime,
        action.instance_id,
        E_INTERRUPT,
        at_tick=12,
        updates={"base_world_revision": Revision(1)},
    )
    return action.instance_id, runtime, runtime.active_actions[action.instance_id]


def _interrupted_action(
    *,
    expected_end_tick: int | None,
    next_checkpoint_tick: int | None,
    progress: float | None,
) -> tuple[ActionInstanceId, ActiveAction]:
    """直接构造 INTERRUPTED 记录（跳过 start_action——T04b 范围），供
    防御分支 / 事件驱动 / 伪造镜像用例使用。"""
    action = ActiveAction(
        instance_id=new_action_instance_id(),
        action_id=ActionTypeId("travel"),
        actor_id=new_entity_id(),
        status=INTERRUPTED,
        start_tick=0,
        expected_end_tick=expected_end_tick,
        progress=progress,
        interruptible=True,
        next_checkpoint_tick=next_checkpoint_tick,
        base_world_revision=Revision(1),
        provenance=Provenance(producer_id="test.producer", origin=OriginKind.SYSTEM),
    )
    return action.instance_id, action


class TestProgressOf:
    """D-P3-08 progress 纯派生（§3.6 下半公共面；E-P3-28 镜像/防篡改口径）。"""

    def test_event_driven_returns_none(self) -> None:
        """事件驱动（expected_end_tick 为 None）→ None（无时长语义）。"""
        action = _action(expected_end_tick=None)
        assert progress_of(action, 99) is None

    def test_gate_a1_exact(self) -> None:
        """G3-1 断言 4 口径：start=0、end=30、t=12 → 0.4（逐字相等）。"""
        action = _action(start_tick=0, expected_end_tick=30)
        assert progress_of(action, 12) == 0.4

    def test_midpoint_half(self) -> None:
        action = _action(start_tick=0, expected_end_tick=30)
        assert progress_of(action, 15) == 0.5

    def test_offset_start_window(self) -> None:
        """start_tick 非 0：分母为 (end - start)，t=10 → (10-5)/(25-5)=0.25。"""
        action = _action(start_tick=5, expected_end_tick=25)
        assert progress_of(action, 10) == 0.25

    def test_clamped_zero_before_start(self) -> None:
        action = _action(start_tick=5, expected_end_tick=25)
        assert progress_of(action, 0) == 0.0
        assert progress_of(action, 4) == 0.0

    def test_clamped_one_after_end(self) -> None:
        action = _action(start_tick=0, expected_end_tick=30)
        assert progress_of(action, 31) == 1.0
        assert progress_of(action, 45) == 1.0

    def test_monotonic_non_decreasing(self) -> None:
        action = _action(start_tick=0, expected_end_tick=30)
        seen = [progress_of(action, tick) for tick in range(0, 36)]
        assert all(a is None or b is None or b >= a for a, b in zip(seen, seen[1:]))
        assert seen[0] == 0.0
        assert seen[30] == 1.0
        assert seen[35] == 1.0

    def test_stored_mirror_never_read(self) -> None:
        """E-P3-28：存储 progress 仅作快照镜像——伪造 0.99 不影响纯派生。"""
        action = _action(start_tick=0, expected_end_tick=30, progress=0.99)
        assert progress_of(action, 12) == 0.4

    def test_return_type_float(self) -> None:
        action = _action(start_tick=0, expected_end_tick=30)
        assert isinstance(progress_of(action, 12), float)


class TestResumeAction:
    """INTERRUPTED→ACTIVE（RESUMED，D-P3-07）：时间预算不变、re-anchor、
    镜像重推、不剪除、不重复入队、防御补入队（D-P3-25 ①）。"""

    def test_gate_a1_full(self) -> None:
        """§5.3 A1：@12 resume，cp@20 已在队列 → 不重复入队；全部字段逐字。"""
        world = WorldState()
        iid, runtime, interrupted = _gate_a1()
        assert interrupted.status is INTERRUPTED
        assert interrupted.base_world_revision == Revision(1)
        queue_before = [e.entry_id for e in runtime.scheduler_queue]
        world2, runtime2, trans = resume_action(
            world, runtime, iid, at_tick=12, current_revision=Revision(1)
        )
        assert world2 is world  # 纯函数不写世界
        act = runtime2.active_actions[iid]
        assert act.status is ACTIVE
        assert act.start_tick == 0  # 时间预算不变（§2.3 / D-P3-08）
        assert act.expected_end_tick == 30
        assert act.base_world_revision == Revision(1)  # re-anchor 至 current_revision
        assert act.progress == 0.4  # 镜像 = progress_of(action, 12) 纯重推
        assert act.last_transition_tick == 12
        # 不剪除、不重复入队：条目逐位不变（entry_id 序列逐字）
        assert [e.entry_id for e in runtime2.scheduler_queue] == queue_before
        assert runtime2.logical_tick == runtime.logical_tick  # 不推进逻辑时钟（D-P3-02）
        assert trans.instance_id == iid
        assert trans.from_status is INTERRUPTED
        assert trans.to_status is ACTIVE
        assert trans.event is E_RESUMED
        assert trans.at_tick == 12
        assert trans.reason is None  # 正常路径无诊断

    def test_reanchor_to_new_revision(self) -> None:
        """resume 刻世界 revision 已再推进（Plan Gate 期间他事提交）→
        re-anchor 至调用方携带的 current_revision。"""
        world = WorldState()
        iid, runtime, _ = _gate_a1()
        _, runtime2, _ = resume_action(
            world, runtime, iid, at_tick=12, current_revision=Revision(2)
        )
        assert runtime2.active_actions[iid].base_world_revision == Revision(2)

    def test_no_duplicate_enqueue_with_foreign_entries(self) -> None:
        """他实例 / 其他 kind 条目不干扰本实例存在性判定（payload 双条件）。"""
        world = WorldState()
        iid, runtime, _ = _gate_a1()
        other_iid, other = _interrupted_action(
            expected_end_tick=40, next_checkpoint_tick=25, progress=0.1
        )
        queue = list(runtime.scheduler_queue)
        queue.append(_entry("action_checkpoint", 25, instance_id=str(other_iid)))
        queue.append(_entry("deadline", 40, instance_id=str(other_iid)))
        runtime = _runtime(
            tick=12,
            active_actions={
                iid: runtime.active_actions[iid],
                other_iid: other,
            },
            scheduler_queue=queue,
        )
        _, runtime2, trans = resume_action(
            world, runtime, iid, at_tick=12, current_revision=Revision(1)
        )
        assert len(runtime2.scheduler_queue) == 4  # 本实例 2 + 他实例 2，无新增
        assert [e.entry_id for e in runtime2.scheduler_queue] == [
            e.entry_id for e in queue
        ]
        assert trans.reason is None

    def test_defect_requeue_diagnostic(self) -> None:
        """D-P3-25 ① 防御分支：cp 条目因缺陷缺失 + next_checkpoint_tick 非空
        → 按 next_checkpoint_tick 补入队 + 迁移记录承载诊断串。"""
        world = WorldState()
        iid, action = _interrupted_action(
            expected_end_tick=30, next_checkpoint_tick=20, progress=0.4
        )
        runtime = _runtime(
            tick=12,
            active_actions={iid: action},
            scheduler_queue=[_entry("action_end", 30, instance_id=str(iid))],
        )
        world2, runtime2, trans = resume_action(
            world, runtime, iid, at_tick=12, current_revision=Revision(1)
        )
        assert world2 is world
        cps = [e for e in runtime2.scheduler_queue if e.kind == "action_checkpoint"]
        assert len(cps) == 1
        assert cps[0].due_tick == 20  # 按 next_checkpoint_tick（无需间隔公式）
        assert cps[0].payload["instance_id"] == str(iid)
        assert cps[0].entry_id.startswith("sch_")  # ids.py 冻结工厂签发
        assert [e.due_tick for e in runtime2.scheduler_queue] == [20, 30]  # 稳定排序
        assert trans.reason == "checkpoint_requeued_after_defect"
        assert trans.to_status is ACTIVE

    def test_event_driven_absent_is_not_defect(self) -> None:
        """事件驱动行动（next_checkpoint_tick 为 None）本无周期 checkpoint——
        条目缺失不构成缺陷：不补入队、无诊断。"""
        world = WorldState()
        iid, action = _interrupted_action(
            expected_end_tick=None, next_checkpoint_tick=None, progress=None
        )
        runtime = _runtime(
            tick=12,
            active_actions={iid: action},
            scheduler_queue=[_entry("action_end", 30, instance_id=str(iid))],
        )
        _, runtime2, trans = resume_action(
            world, runtime, iid, at_tick=12, current_revision=Revision(1)
        )
        assert len(runtime2.scheduler_queue) == 1
        assert all(e.kind != "action_checkpoint" for e in runtime2.scheduler_queue)
        assert trans.reason is None

    def test_mirror_rederived_not_forged(self) -> None:
        """E-P3-28：中断刻镜像若为伪造值（簿记缺陷），RESUMED 迁移重推覆盖——
        存储值不进入推导。"""
        world = WorldState()
        iid, action = _interrupted_action(
            expected_end_tick=30, next_checkpoint_tick=20, progress=0.99
        )
        runtime = _runtime(
            tick=12,
            active_actions={iid: action},
            scheduler_queue=_gate_queue(iid),
        )
        _, runtime2, trans = resume_action(
            world, runtime, iid, at_tick=12, current_revision=Revision(1)
        )
        assert runtime2.active_actions[iid].progress == 0.4
        assert trans.reason is None  # cp@20 在队列 → 正常路径

    @pytest.mark.parametrize("status", [PROPOSED, VALIDATING, ACTIVE, COMPLETED, FAILED])
    def test_illegal_source_status(self, status: ActionLifecycleStatus) -> None:
        """RESUMED 边仅出自 INTERRUPTED（D-P3-07 表外 → IllegalTransitionError）。"""
        action = _action(status=status)
        runtime = _runtime_with_action(action)
        with pytest.raises(IllegalTransitionError):
            resume_action(
                WorldState(),
                runtime,
                action.instance_id,
                at_tick=12,
                current_revision=Revision(1),
            )

    def test_missing_instance(self) -> None:
        runtime = _runtime()
        with pytest.raises(IllegalTransitionError):
            resume_action(
                WorldState(),
                runtime,
                new_action_instance_id(),
                at_tick=12,
                current_revision=Revision(1),
            )


class TestAbortAction:
    """INTERRUPTED→FAILED（ABORTED；§5.4 B1 口径；E-P3-29 ② ACTIVE 无直边）。"""

    def test_gate_b1_full(self) -> None:
        """§5.4 B1：@12 abort（默认 reason），result_summary 逐字、剪除全部
        该实例条目、无完成 effect。"""
        iid, runtime, _ = _gate_a1()
        runtime2 = abort_action(runtime, iid, at_tick=12)
        act = runtime2.active_actions[iid]
        assert act.status is FAILED
        assert act.result_summary == {"reason": "aborted", "tick": 12, "progress": 0.4}
        assert act.last_transition_tick == 12
        assert runtime2.scheduler_queue == []  # cp@20/end@30 均剪除（终态）
        assert runtime2.logical_tick == runtime.logical_tick

    def test_custom_reason(self) -> None:
        iid, runtime, _ = _gate_a1()
        runtime2 = abort_action(runtime, iid, at_tick=12, reason="npc_intervened")
        assert runtime2.active_actions[iid].result_summary["reason"] == "npc_intervened"

    def test_event_driven_progress_none(self) -> None:
        action = _action(status=INTERRUPTED, expected_end_tick=None)
        runtime = _runtime_with_action(action)
        runtime2 = abort_action(runtime, action.instance_id, at_tick=7)
        assert runtime2.active_actions[action.instance_id].result_summary["progress"] is None

    def test_abort_after_clock_advance(self) -> None:
        """中断刻与中止刻之间时钟推进：progress 按**中止刻**纯派生（不依赖
        存储镜像）——@12 中断、@20 中止 → 20/30。"""
        iid, runtime, _ = _gate_a1()
        runtime2 = abort_action(runtime, iid, at_tick=20)
        summary = runtime2.active_actions[iid].result_summary
        assert summary["tick"] == 20
        assert summary["progress"] == pytest.approx(20 / 30)
        assert summary["reason"] == "aborted"

    def test_prunes_only_own_entries(self) -> None:
        """剪除仅命中本实例（payload instance_id 双条件）；他实例条目不动。"""
        iid, runtime, _ = _gate_a1()
        other_iid, other = _interrupted_action(
            expected_end_tick=40, next_checkpoint_tick=25, progress=0.1
        )
        queue = list(runtime.scheduler_queue)
        queue.append(_entry("action_checkpoint", 25, instance_id=str(other_iid)))
        queue.append(_entry("deadline", 40, instance_id=str(other_iid)))
        runtime = _runtime(
            tick=12,
            active_actions={
                iid: runtime.active_actions[iid],
                other_iid: other,
            },
            scheduler_queue=queue,
        )
        runtime2 = abort_action(runtime, iid, at_tick=12)
        remaining = runtime2.scheduler_queue
        assert len(remaining) == 2
        assert all(e.payload.get("instance_id") == str(other_iid) for e in remaining)
        assert runtime2.active_actions[iid].status is FAILED  # 状态记录保留
        assert runtime2.active_actions[other_iid].status is INTERRUPTED  # 他实例不受影响

    @pytest.mark.parametrize(
        "status", [PROPOSED, VALIDATING, ACTIVE, COMPLETED, FAILED]
    )
    def test_illegal_source_status(self, status: ActionLifecycleStatus) -> None:
        """ABORTED 边仅出自 INTERRUPTED——含 E-P3-29 ② 关键点：ACTIVE 无
        直接 ABORTED 边（须先中断再中止）。"""
        action = _action(status=status)
        runtime = _runtime_with_action(action)
        with pytest.raises(IllegalTransitionError):
            abort_action(runtime, action.instance_id, at_tick=12)

    def test_missing_instance(self) -> None:
        runtime = _runtime()
        with pytest.raises(IllegalTransitionError):
            abort_action(runtime, new_action_instance_id(), at_tick=12)


class TestCompleteAction:
    """ACTIVE→COMPLETED（D-P3-08 完成语义：位置/进度只在此刻经事务移动；
    纯函数只出 effect、不写世界、不推进 revision）。"""

    def test_gate_a4_full(self) -> None:
        """§5.2 S8：@30 完成，end@30/cp@30 同刻条目一并剪除；世界原样返回。"""
        world = WorldState()
        action = _action()
        iid = action.instance_id
        queue = [
            _entry("action_end", 30, instance_id=str(iid)),
            _entry("action_checkpoint", 30, instance_id=str(iid)),
        ]
        runtime = _runtime_with_action(action, scheduler_queue=queue)
        world2, runtime2, trans = complete_action(
            world, runtime, iid, at_tick=30, completion_effects=[]
        )
        assert world2 is world  # 同一对象：纯函数不写世界
        assert world2.world_revision == INITIAL_WORLD_REVISION  # 不推进 revision（P1 D-5）
        act = runtime2.active_actions[iid]
        assert act.status is COMPLETED
        assert act.result_summary == {"completed_at": 30}
        assert runtime2.scheduler_queue == []  # 终态剪除（D-P3-25 ①）
        assert runtime2.logical_tick == runtime.logical_tick
        assert act.progress is None  # COMPLETED 非镜像事件（E-P3-28）：不强推 1.0
        assert trans.instance_id == iid
        assert trans.from_status is ACTIVE
        assert trans.to_status is COMPLETED
        assert trans.event is E_COMPLETED
        assert trans.at_tick == 30
        assert trans.reason is None

    def test_completion_effects_do_not_touch_world(self) -> None:
        """带 completion_effects（位置 effect）：纯函数仍不提交——世界同一
        对象、revision 不变；effect 由调用方经 P2 管道提交（本函数只放行）。"""
        world = WorldState()
        action = _action()
        iid = action.instance_id
        runtime = _runtime_with_action(
            action, scheduler_queue=[_entry("action_end", 30, instance_id=str(iid))]
        )
        world2, runtime2, _ = complete_action(
            world, runtime, iid, at_tick=30, completion_effects=[_pos_effect()]
        )
        assert world2 is world
        assert world2.world_revision == INITIAL_WORLD_REVISION
        assert runtime2.active_actions[iid].status is COMPLETED
        assert runtime2.scheduler_queue == []

    @pytest.mark.parametrize(
        "status", [PROPOSED, VALIDATING, INTERRUPTED, COMPLETED, FAILED]
    )
    def test_illegal_source_status(self, status: ActionLifecycleStatus) -> None:
        """COMPLETED 边仅出自 ACTIVE（终态不可逆：COMPLETED 自身无出边）。"""
        action = _action(status=status)
        runtime = _runtime_with_action(action)
        with pytest.raises(IllegalTransitionError):
            complete_action(
                WorldState(), runtime, action.instance_id, at_tick=30, completion_effects=[]
            )

    def test_missing_instance(self) -> None:
        with pytest.raises(IllegalTransitionError):
            complete_action(
                WorldState(), _runtime(), new_action_instance_id(),
                at_tick=30, completion_effects=[],
            )


class TestFailAction:
    """ACTIVE→FAILED（FAILED 边仅出自 ACTIVE；VALIDATING 被拒经
    VALIDATION_REJECTED 属 submit_proposal REJECT 轨迹，不经本函数，
    E-P3-05 口径）。"""

    def test_deadline_missed_full(self) -> None:
        """§2.4 口径：deadline 条目命中仍 ACTIVE → reason="deadline_missed"；
        终态剪除该实例全部剩余条目。"""
        action = _action()
        iid = action.instance_id
        queue = [
            _entry("deadline", 30, instance_id=str(iid)),
            _entry("action_checkpoint", 20, instance_id=str(iid)),
        ]
        runtime = _runtime_with_action(action, scheduler_queue=queue)
        runtime2 = fail_action(runtime, iid, at_tick=30, reason="deadline_missed")
        act = runtime2.active_actions[iid]
        assert act.status is FAILED
        assert act.result_summary == {"reason": "deadline_missed", "tick": 30}
        assert runtime2.scheduler_queue == []
        assert runtime2.logical_tick == runtime.logical_tick

    def test_reason_is_required_keyword(self) -> None:
        """reason 为必填关键字（无缺省）——遗漏 → TypeError（签名级防线）。"""
        action = _action()
        runtime = _runtime_with_action(action)
        with pytest.raises(TypeError):
            fail_action(runtime, action.instance_id, at_tick=30)  # type: ignore[call-arg]

    def test_validating_not_reachable(self) -> None:
        """E-P3-05：对 VALIDATING 实例调用 fail_action → 表外抛（该边属
        VALIDATION_REJECTED 轨迹，不经本函数）；并结构钉住迁移表口径。"""
        action = _action(status=VALIDATING)
        runtime = _runtime_with_action(action)
        with pytest.raises(IllegalTransitionError):
            fail_action(runtime, action.instance_id, at_tick=5, reason="bad")
        # 结构断言（嵌套表：状态 → frozenset{(事件, 目标态)}）：ACTIVE 出发的
        # FAILED 目标边恰为 {E_FAILED}；VALIDATING 出边恰为 {E_SCHEDULED,
        # E_REJECT}（两者皆非 fail_action 的调用面入口）
        failed_from_active = {
            ev for ev, tgt in LIFECYCLE_TRANSITIONS[ACTIVE] if tgt is FAILED
        }
        assert failed_from_active == {E_FAILED}
        validating_events = {ev for ev, _tgt in LIFECYCLE_TRANSITIONS[VALIDATING]}
        assert validating_events == {E_SCHEDULED, E_REJECT}

    @pytest.mark.parametrize("status", [PROPOSED, INTERRUPTED, COMPLETED, FAILED])
    def test_illegal_source_status(self, status: ActionLifecycleStatus) -> None:
        action = _action(status=status)
        runtime = _runtime_with_action(action)
        with pytest.raises(IllegalTransitionError):
            fail_action(runtime, action.instance_id, at_tick=5, reason="x")

    def test_missing_instance(self) -> None:
        with pytest.raises(IllegalTransitionError):
            fail_action(_runtime(), new_action_instance_id(), at_tick=5, reason="x")

    def test_input_runtime_untouched(self) -> None:
        """纯函数纪律：原 RuntimeState / ActiveAction 不变（frozen 重建）。"""
        action = _action()
        runtime = _runtime_with_action(action)
        fail_action(runtime, action.instance_id, at_tick=30, reason="deadline_missed")
        assert runtime.active_actions[action.instance_id].status is ACTIVE
        assert runtime.active_actions[action.instance_id].result_summary is None
        assert runtime.scheduler_queue == []


# ======================================================================
# §3.6 下半（P3-T04a2：apply_checkpoint）——同文件串行追加（§3.10 单
# Owner 纪律；用例复用上方 T03 助手层 _runtime/_runtime_with_action/
# _entry/_gate_queue/_gate_a1，本节另落全字段构造助手 _full_action）。
#
# 口径依据（Leader 裁定 E-P3-40 修订后的现文）：
# - §3.6 ``apply_checkpoint`` 现文：签名含关键字
#   ``checkpoint_interval: int | None = None``（Scheduler 透传
#   ``time_policy.checkpoint_interval_ticks``，D-P3-13；None → 不入队
#   下一 checkpoint）；CHECKPOINT 自迁移 + progress 重算 + base
#   re-anchor + 入队下一 checkpoint；纯 RuntimeState 簿记（P1 D-5）；
#   正常路径 record=None；
# - §5.2 S4 / §5.3 A2 两刻推演：t=10 → progress 10/30、入队 cp@20、
#   队列 [ev@12, cp@20, end@30]；t=20（resume 后 R1）→ progress 20/30、
#   入队 cp@30、队列 [end@30, cp@30]（稳定 FIFO：end@30 先入队）——
#   同一函数/同一间隔公式两刻与 Gate 表逐字一致；
# - §6.1 用例口径："progress 重算 + next_checkpoint_tick 前进 + 下刻
#   入队 + base re-anchor + 无世界事务/revision 不变"；
# - E-P3-12 ② / D-P3-25 非 ACTIVE 双道守卫：终态 →
#   checkpoint_skipped_terminal、INTERRUPTED → checkpoint_skipped_interrupted
#   （TraceKind.SYSTEM 开放信封），不查表/不迁移/不入队，状态与队列
#   不变。
# ======================================================================


def _full_action(
    *,
    status: ActionLifecycleStatus = ACTIVE,
    start_tick: int = 0,
    expected_end_tick: int | None = 30,
    progress: float | None = None,
    next_checkpoint_tick: int | None = None,
    base_world_revision: Revision = INITIAL_WORLD_REVISION,
    last_transition_tick: int = 0,
    result_summary: dict[str, JsonValue] | None = None,
) -> ActiveAction:
    """全字段 ActiveAction 构造（T04a2 节局部助手——T03 助手 ``_action``
    不暴露 ``next_checkpoint_tick`` / ``last_transition_tick``，两刻推演
    前置态按 Gate 表逐字钉死需显式构造；ID 工厂签发，键一致性天然成立）。"""
    return ActiveAction(
        instance_id=new_action_instance_id(),
        action_id=ActionTypeId("travel"),
        actor_id=new_entity_id(),
        status=status,
        start_tick=start_tick,
        expected_end_tick=expected_end_tick,
        progress=progress,
        interruptible=True,
        next_checkpoint_tick=next_checkpoint_tick,
        base_world_revision=base_world_revision,
        provenance=Provenance(producer_id="test.producer", origin=OriginKind.SYSTEM),
        last_transition_tick=last_transition_tick,
        result_summary=result_summary,
    )


class TestApplyCheckpoint:
    """CHECKPOINT 自迁移（§3.6 下半；D-P3-07/08/13；E-P3-12 ② / E-P3-40）。"""

    def test_s4_normal_path(self) -> None:
        """§5.2 S4 两刻推演①：cp@10 处理 → CHECKPOINT 自迁移 + progress
        10/30 重算 + re-anchor（current_revision=R0）+ 入队 cp@20 +
        next_checkpoint_tick 10→20；队列 [ev@12, cp@20, end@30]（稳定
        序）；record=None；逻辑时钟不推进。"""
        action = _full_action(
            progress=0.0,
            next_checkpoint_tick=10,
            base_world_revision=Revision(0),
            last_transition_tick=0,
        )
        iid = action.instance_id
        ev = _entry("event", 12, trigger_id="scenario.encounter_12")
        end = _entry("action_end", 30, instance_id=str(iid))
        runtime = _runtime_with_action(action, tick=10, scheduler_queue=[ev, end])
        runtime2, record = apply_checkpoint(
            runtime, iid, at_tick=10, current_revision=Revision(0), checkpoint_interval=10
        )
        assert record is None  # 正常路径 record=None（§3.6 现文）
        act = runtime2.active_actions[iid]
        assert act is not action  # rebuild 新对象（输入不变）
        assert act.status is ACTIVE  # CHECKPOINT 自迁移：ACTIVE → ACTIVE
        assert act.progress == 10 / 30  # progress 重算 = progress_of(action, 10)
        assert act.next_checkpoint_tick == 20  # 前进至新入队刻（§6.1 口径）
        assert act.base_world_revision == Revision(0)  # re-anchor 至 current_revision
        assert act.last_transition_tick == 10  # 审计字段（actions.py:243）
        assert act.start_tick == 0  # 时间预算不变
        assert act.expected_end_tick == 30
        # 队列：新 cp@20 经稳定排序插入 12 < 20 < 30 位，旧条目 entry_id 保留
        assert [(e.kind, e.due_tick) for e in runtime2.scheduler_queue] == [
            ("event", 12),
            ("action_checkpoint", 20),
            ("action_end", 30),
        ]
        assert runtime2.scheduler_queue[0].entry_id == ev.entry_id
        assert runtime2.scheduler_queue[2].entry_id == end.entry_id
        new_cp = runtime2.scheduler_queue[1]
        assert new_cp.entry_id.startswith("sch_")  # new_scheduled_entry_id() 工厂
        assert new_cp.payload == {"instance_id": str(iid)}
        assert runtime2.logical_tick == 10  # 不推进逻辑时钟（D-P3-02）

    def test_a2_normal_path(self) -> None:
        """§5.3 A2 两刻推演②：cp@20 处理（resume 后，R1）→ progress 20/30
        重算 + re-anchor（R1）+ 入队 cp@30 + next_checkpoint_tick 20→30；
        队列 [end@30, cp@30]（稳定 FIFO：end@30 开始刻先入队）；
        record=None。与 S4 同一函数/同一间隔公式，两刻推演一致且 progress
        单调（Gate 分支 A 断言 0.0 → 0.3333 → 0.4 → 0.6667 → 1.0）。"""
        action = _full_action(
            progress=0.4,
            next_checkpoint_tick=20,
            base_world_revision=Revision(1),
            last_transition_tick=12,
        )
        iid = action.instance_id
        end = _entry("action_end", 30, instance_id=str(iid))
        runtime = _runtime_with_action(action, tick=20, scheduler_queue=[end])
        runtime2, record = apply_checkpoint(
            runtime, iid, at_tick=20, current_revision=Revision(1), checkpoint_interval=10
        )
        assert record is None
        act = runtime2.active_actions[iid]
        assert act.status is ACTIVE
        assert act.progress == 20 / 30  # > S4 的 10/30：两刻间单调
        assert act.next_checkpoint_tick == 30
        assert act.base_world_revision == Revision(1)
        assert act.last_transition_tick == 20
        # 稳定 FIFO：end@30（先入队）先于 cp@30（本刻派生，§2.5/D-P3-05）
        assert [(e.kind, e.due_tick) for e in runtime2.scheduler_queue] == [
            ("action_end", 30),
            ("action_checkpoint", 30),
        ]
        assert runtime2.scheduler_queue[0].entry_id == end.entry_id
        new_cp = runtime2.scheduler_queue[1]
        assert new_cp.entry_id.startswith("sch_")
        assert new_cp.entry_id != end.entry_id
        assert new_cp.payload == {"instance_id": str(iid)}
        assert runtime2.logical_tick == 20

    def test_interval_none_no_enqueue(self) -> None:
        """E-P3-40：checkpoint_interval=None → 不入队下一 checkpoint；
        next_checkpoint_tick 镜像置 None（下一 checkpoint 不存在——保留
        过去值会诱导 resume 防御补入队按过去刻入队 → QueueInvariantError）；
        自迁移 / progress 重算 / re-anchor 照常；record=None。"""
        action = _full_action(
            progress=0.2,
            next_checkpoint_tick=6,
            base_world_revision=Revision(0),
            last_transition_tick=6,
        )
        iid = action.instance_id
        end = _entry("action_end", 30, instance_id=str(iid))
        runtime = _runtime_with_action(action, tick=6, scheduler_queue=[end])
        runtime2, record = apply_checkpoint(
            runtime, iid, at_tick=6, current_revision=Revision(0), checkpoint_interval=None
        )
        assert record is None
        act = runtime2.active_actions[iid]
        assert act.status is ACTIVE
        assert act.progress == 6 / 30  # 重算照常
        assert act.base_world_revision == Revision(0)
        assert act.last_transition_tick == 6
        assert act.next_checkpoint_tick is None  # 无下一 checkpoint
        # 队列不变：无新增条目
        assert [(e.kind, e.due_tick) for e in runtime2.scheduler_queue] == [
            ("action_end", 30)
        ]
        assert runtime2.scheduler_queue[0].entry_id == end.entry_id

    def test_reanchor_to_new_revision(self) -> None:
        """base re-anchor 可观察口径：checkpoint 刻世界 revision 已推进
        （start 后他事提交）→ base_world_revision := current_revision
        （D-P3-08 口径，与 INTERRUPTED 边 / resume_action 对齐；§5.2 S7 /
        G3-1 断言 6）。"""
        action = _full_action(
            progress=0.0,
            next_checkpoint_tick=10,
            base_world_revision=Revision(0),
            last_transition_tick=0,
        )
        runtime = _runtime_with_action(action, tick=10)
        runtime2, _ = apply_checkpoint(
            runtime,
            action.instance_id,
            at_tick=10,
            current_revision=Revision(3),
            checkpoint_interval=10,
        )
        assert (
            runtime2.active_actions[action.instance_id].base_world_revision
            == Revision(3)
        )

    def test_guard_completed_terminal(self) -> None:
        """E-P3-12 ② 第二道防线：终态 COMPLETED → 不查迁移表 / 不调
        transition_action / 不入队下一 checkpoint；返回（未变更 runtime,
        诊断 TraceRecord：TraceKind.SYSTEM + checkpoint_skipped_terminal）；
        状态 / progress / base / 审计字段 / 队列全不变。"""
        action = _full_action(
            status=COMPLETED,
            progress=1.0,
            next_checkpoint_tick=40,
            base_world_revision=Revision(2),
            last_transition_tick=30,
            result_summary={"completed_at": 30},
        )
        iid = action.instance_id
        queue = [
            _entry("action_checkpoint", 30, instance_id=str(iid)),
            _entry("action_end", 30, instance_id=str(iid)),
        ]
        runtime = _runtime_with_action(action, tick=30, scheduler_queue=queue)
        queue_before = [e.entry_id for e in runtime.scheduler_queue]
        runtime2, record = apply_checkpoint(
            runtime, iid, at_tick=30, current_revision=Revision(2), checkpoint_interval=10
        )
        # 诊断 TraceRecord（§3.6 现文：开放信封 + SYSTEM + 诊断串）
        assert isinstance(record, TraceRecord)
        assert record.kind is TraceKind.SYSTEM
        assert record.payload["diagnostic"] == "checkpoint_skipped_terminal"
        assert record.payload["instance_id"] == str(iid)
        assert record.record_id.startswith("trc_")  # new_trace_record_id() 工厂
        assert record.logical_tick == 30
        assert record.world_revision == Revision(2)
        # 未变更：不查表 → 不迁移 / 不重算 / 不 re-anchor / 不推进审计字段
        act = runtime2.active_actions[iid]
        assert act.status is COMPLETED
        assert act.progress == 1.0
        assert act.base_world_revision == Revision(2)
        assert act.last_transition_tick == 30
        assert act.next_checkpoint_tick == 40  # 守卫不触碰（不置空、不清除）
        # 队列不变：不入队下一 checkpoint、不触碰既有条目
        assert [e.entry_id for e in runtime2.scheduler_queue] == queue_before
        assert [(e.kind, e.due_tick) for e in runtime2.scheduler_queue] == [
            ("action_checkpoint", 30),
            ("action_end", 30),
        ]

    def test_guard_interrupted(self) -> None:
        """E-P3-12 ② / D-P3-25：INTERRUPTED → 诊断
        checkpoint_skipped_interrupted（同信封）；Gate S8 暂停点场景
        （cp@20 命中未响应中断实例）——状态 / progress / base / 审计字段 /
        队列全不变。"""
        iid, runtime, _interrupted = _gate_a1()
        queue_before = [e.entry_id for e in runtime.scheduler_queue]
        runtime2, record = apply_checkpoint(
            runtime, iid, at_tick=20, current_revision=Revision(1), checkpoint_interval=10
        )
        assert isinstance(record, TraceRecord)
        assert record.kind is TraceKind.SYSTEM
        assert record.payload["diagnostic"] == "checkpoint_skipped_interrupted"
        assert record.payload["instance_id"] == str(iid)
        assert record.record_id.startswith("trc_")
        assert record.logical_tick == 20
        assert record.world_revision == Revision(1)
        # 未变更（Gate S7 点状态原样保留）
        act = runtime2.active_actions[iid]
        assert act.status is INTERRUPTED
        assert act.progress == 0.4  # 不重算（镜像保留中断刻值）
        assert act.base_world_revision == Revision(1)  # 不 re-anchor
        assert act.last_transition_tick == 12  # 审计字段不推进
        assert act.next_checkpoint_tick is None
        # 队列不变：不入队下一 checkpoint（中断不剪除、守卫不追加）
        assert [e.entry_id for e in runtime2.scheduler_queue] == queue_before
        assert [(e.kind, e.due_tick) for e in runtime2.scheduler_queue] == [
            ("action_checkpoint", 20),
            ("action_end", 30),
        ]

    def test_return_tuple_shape(self) -> None:
        """返回类型钉死（§3.6 现文签名 E-P3-12 ②）：正常路径
        (RuntimeState, None)；守卫路径 (RuntimeState, TraceRecord)。"""
        action = _full_action(progress=0.0, next_checkpoint_tick=10)
        runtime = _runtime_with_action(action, tick=10)
        runtime2, record = apply_checkpoint(
            runtime,
            action.instance_id,
            at_tick=10,
            current_revision=Revision(0),
            checkpoint_interval=10,
        )
        assert isinstance(runtime2, RuntimeState)
        assert record is None
        assert isinstance(runtime2.active_actions[action.instance_id], ActiveAction)
        # 守卫路径（checkpoint_interval 缺省 None——守卫路径不消费间隔）
        iid, runtime_int, _ = _gate_a1()
        runtime3, record3 = apply_checkpoint(
            runtime_int, iid, at_tick=20, current_revision=Revision(1)
        )
        assert isinstance(runtime3, RuntimeState)
        assert isinstance(record3, TraceRecord)
        assert record3.kind is TraceKind.SYSTEM

    def test_missing_instance_raises(self) -> None:
        """实例不存在于 active_actions → IllegalTransitionError（可检查
        不静默，D-P3-16 ① 同型；信息含 instance/event）。"""
        runtime = _runtime(tick=10)
        with pytest.raises(IllegalTransitionError, match="不存在于 active_actions"):
            apply_checkpoint(
                runtime,
                new_action_instance_id(),
                at_tick=10,
                current_revision=Revision(0),
                checkpoint_interval=10,
            )

    def test_unstarted_status_raises(self) -> None:
        """PROPOSED/VALIDATING + cp 条目 = 簿记不变量违例（cp 条目仅可能
        在 SCHEDULED 迁移后入队）→ 不属守卫 skip 口径（守卫仅覆盖
        INTERRUPTED / 终态）→ IllegalTransitionError（与 transition_action
        表外行为同型，不静默）。"""
        for status in (PROPOSED, VALIDATING):
            action = _full_action(status=status)
            runtime = _runtime_with_action(
                action,
                tick=10,
                scheduler_queue=[
                    _entry("action_checkpoint", 10, instance_id=str(action.instance_id))
                ],
            )
            with pytest.raises(IllegalTransitionError, match="簿记不变量违例"):
                apply_checkpoint(
                    runtime,
                    action.instance_id,
                    at_tick=10,
                    current_revision=Revision(0),
                    checkpoint_interval=10,
                )

    def test_purity_input_unchanged(self) -> None:
        """纯函数纪律：原 RuntimeState / ActiveAction / 队列不变（frozen
        重建）；逻辑时钟不推进（D-P3-02 唯一写点 set_logical_tick）；其余
        RuntimeState 字段不触碰。"""
        action = _full_action(progress=0.0, next_checkpoint_tick=10)
        iid = action.instance_id
        end = _entry("action_end", 30, instance_id=str(iid))
        runtime = _runtime_with_action(action, tick=10, scheduler_queue=[end])
        runtime2, _ = apply_checkpoint(
            runtime, iid, at_tick=10, current_revision=Revision(0), checkpoint_interval=10
        )
        assert runtime2 is not runtime
        assert runtime.active_actions[iid] is action  # 输入对象未被替换
        assert runtime.active_actions[iid].progress == 0.0  # 原值保留
        assert runtime.active_actions[iid].next_checkpoint_tick == 10
        assert runtime.scheduler_queue == [end]  # 原队列不变
        assert runtime.logical_tick == 10
        assert runtime2.logical_tick == 10
        # 其余 RuntimeState 字段不触碰
        assert runtime2.actor_wakeups == runtime.actor_wakeups
        assert runtime2.pending_proposals == runtime.pending_proposals
        assert runtime2.lifecycle == runtime.lifecycle
        assert runtime2.active_modes == runtime.active_modes
        assert runtime2.mode_context == runtime.mode_context
