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
    transition_action,
)
from src.engine_v2.core.actions import ActionLifecycleStatus, ActionTypeId, ActiveAction
from src.engine_v2.core.clock import SchedulerError
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.event_queue import make_scheduled_event
from src.engine_v2.core.ids import ActionInstanceId, new_action_instance_id, new_entity_id
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.revision import INITIAL_WORLD_REVISION, Revision
from src.engine_v2.core.serialization import dump_json, load_json
from src.engine_v2.core.state import ActorWakeup, RuntimeState, ScheduledEvent

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
