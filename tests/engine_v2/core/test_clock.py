"""P3-T01 clock.py 单元测试（设计文档 §3.3 全量 + §2.2/§2.3 时钟语义）。

依据 ``docs/v2/contracts/P3-scheduler-time-action-design.md``：

- **LogicalClock 值类型**（§2.3 / D-P3-02，Revision 模式）：``of`` 投影恒等
  （``LogicalClock.of(runtime).tick == runtime.logical_tick``）；``elapsed``
  下界 0；``advanced(delta >= 0)`` 前移（负 delta → :class:`ClockRollbackError`）；
  ``tick`` 字段 ``ge=0``；ContractModel（frozen / extra=forbid，round-trip 可测）；
- **唯一时钟写点** :func:`set_logical_tick`（§3.3 / D-P3-02）：
  ``tick < 当前`` → :class:`ClockRollbackError`（信息含 from/to）；
  单调推进（``tick == 当前`` 幂等 no-op、``tick > 当前`` 一步跳变，
  fast-forward 核心原语，§2.4 / D-P3-03）；重建模式返回新实例、self 不变；
  只写 ``logical_tick``，不触碰世界状态（与 revision 解耦，P2 D-P2-18 原文）；
- **fast-forward 终点判据** :func:`next_due_tick`（§3.3 / §2.4）：
  队列空 → ``None``；否则 ``scheduler_queue[*].due_tick`` 最小值；
  时钟跳变后与队列最小值恒等（D-P3-05 写时稳定排序的可断言口径）；
- **重建公共缝隙** :func:`rebuild_runtime`（§3.3，P1 state.py:213-214 授权）：
  ``model_dump()`` → dict 更新 → ``model_validate()``（P1 唯一合法序列化
  路径，serialization.py 规则 1）；重跑 ``active_actions`` 键一致性
  ``model_validator``（键不符 → ``ValidationError``）；
- **刻语义**（§2.2 / D-P3-01）：core 单位无关、只计数 tick——1 tick ≙ 1 世界
  分钟是内容层映射，本模块不出现单位换算（测试口径：tick 值逐字保持，
  不乘除任何常数）；
- **错误基类族**（D-P3-16，宿主置 clock.py 依赖叶）：
  ``ClockRollbackError ⊂ SchedulerError ⊂ ValueError``。

全部用例无网络、无 LLM、无 API key、无墙钟（§8.3 P3 专项 import 边界：
禁 ``datetime``/``time``/``random``/``asyncio``）。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from src.engine_v2.core.actions import (
    ActionLifecycleStatus,
    ActionTypeId,
    ActiveAction,
)
from src.engine_v2.core.clock import (
    ClockRollbackError,
    LogicalClock,
    SchedulerError,
    next_due_tick,
    rebuild_runtime,
    set_logical_tick,
)
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.event_queue import enqueue_scheduled_event, make_scheduled_event
from src.engine_v2.core.ids import new_action_instance_id, new_entity_id
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.serialization import assert_json_clean, dump_json, load_json
from src.engine_v2.core.state import RuntimeState, RuntimeLifecycle, ScheduledEvent

# —— 测试专用构造助手（确定性 ID，非工厂随机段）——


def _runtime(tick: int = 0, **kwargs: Any) -> RuntimeState:
    """构造 ``logical_tick=tick`` 的测试 RuntimeState。"""
    return RuntimeState(logical_tick=tick, **kwargs)


def _action() -> ActiveAction:
    """构造最小合法 ActiveAction（键一致性 validator 测试用；工厂签发 ID）。"""
    return ActiveAction(
        instance_id=new_action_instance_id(),
        action_id=ActionTypeId("travel"),
        actor_id=new_entity_id(),
        status=ActionLifecycleStatus.ACTIVE,
        start_tick=0,
        base_world_revision=Revision(0),
        provenance=Provenance(producer_id="test.producer", origin=OriginKind.SYSTEM),
    )


def _runtime_with_action() -> tuple[RuntimeState, ActiveAction]:
    """携带一条 active_actions 记录的 RuntimeState（键 = instance_id，合法）。"""
    action = _action()
    runtime = _runtime(active_actions={action.instance_id: action})
    return runtime, action


class TestLogicalClockValueType:
    """§2.3 / D-P3-02：LogicalClock 值类型（Revision 模式，非第二权威）。"""

    def test_is_contract_model(self) -> None:
        assert issubclass(LogicalClock, ContractModel)

    @pytest.mark.parametrize("tick", (0, 1, 12, 30, 10**18))
    def test_of_projection_identity(self, tick: int) -> None:
        """of 投影恒等：任何时刻权威值 = runtime.logical_tick（K1 同源纪律）。"""
        runtime = _runtime(tick=tick)
        assert LogicalClock.of(runtime).tick == tick
        assert type(LogicalClock.of(runtime).tick) is int

    def test_of_reprojects_after_write(self) -> None:
        """投影随权威值更新——非第二权威：写回后重新投影得新值。"""
        runtime = _runtime(tick=0)
        assert LogicalClock.of(runtime).tick == 0
        advanced = set_logical_tick(runtime, 30)
        assert LogicalClock.of(advanced).tick == 30
        # 原 runtime 未被"第二时钟"影响（值类型生命周期不超出一次纯函数求值）
        assert LogicalClock.of(runtime).tick == 0

    @pytest.mark.parametrize(
        "tick,since,expected",
        (
            (0, 0, 0),
            (12, 0, 12),
            (12, 12, 0),
            (12, 20, 0),
            (30, 12, 18),
            (30, 29, 1),
            (0, 5, 0),
        ),
    )
    def test_elapsed_lower_bound_zero(self, tick: int, since: int, expected: int) -> None:
        """elapsed = max(0, tick - since_tick)：since_tick 晚于/等于当前刻不产生负值。"""
        assert LogicalClock(tick=tick).elapsed(since) == expected

    def test_advanced_zero_is_noop_value(self) -> None:
        """advanced(0) 返回同值新对象（值类型，self 不变）。"""
        clock = LogicalClock(tick=12)
        result = clock.advanced(0)
        assert result.tick == 12
        assert result is not clock
        assert clock.tick == 12

    def test_advanced_positive_returns_new_clock(self) -> None:
        result = LogicalClock(tick=12).advanced(18)
        assert result.tick == 30
        assert LogicalClock(tick=12).tick == 12

    def test_advanced_negative_raises_clock_rollback_error(self) -> None:
        """advanced(delta < 0) → ClockRollbackError（单调性，D-P3-02）。"""
        with pytest.raises(ClockRollbackError):
            LogicalClock(tick=12).advanced(-1)
        with pytest.raises(ClockRollbackError):
            LogicalClock(tick=0).advanced(-1)

    def test_tick_field_ge_zero(self) -> None:
        """tick: int = Field(ge=0)：负值构造失败（P1 契约模型约束）。"""
        with pytest.raises(ValidationError):
            LogicalClock(tick=-1)

    def test_frozen_no_field_reassignment(self) -> None:
        clock = LogicalClock(tick=12)
        with pytest.raises(ValidationError):
            clock.tick = 13  # type: ignore[misc]

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            LogicalClock(tick=12, epoch="game_minute")  # type: ignore[call-arg]

    def test_serialization_roundtrip(self) -> None:
        """LogicalClock 自身是 ContractModel：dump_json/load_json round-trip 恒等。"""
        clock = LogicalClock(tick=12)
        text = dump_json(clock)
        assert_json_clean(json.loads(text))
        restored = load_json(LogicalClock, text)
        assert restored == clock
        assert restored.tick == 12
        assert type(restored.tick) is int


class TestSetLogicalTick:
    """§3.3 / D-P3-02：set_logical_tick 唯一时钟写点（回退 / 单调推进 / 刻语义）。"""

    def test_rollback_raises_clock_rollback_error(self) -> None:
        """回退 ClockRollbackError：tick < 当前 → 抛（信息含 from/to）。"""
        runtime = _runtime(tick=12)
        with pytest.raises(ClockRollbackError) as excinfo:
            set_logical_tick(runtime, 11)
        message = str(excinfo.value)
        assert "from=12" in message
        assert "to=11" in message

    def test_rollback_to_zero_from_positive(self) -> None:
        with pytest.raises(ClockRollbackError):
            set_logical_tick(_runtime(tick=30), 0)

    def test_rollback_negative_target(self) -> None:
        """tick 负值亦属回退（当前恒 >= 0，负目标必 < 当前）。"""
        with pytest.raises(ClockRollbackError):
            set_logical_tick(_runtime(tick=0), -1)

    def test_equal_tick_is_idempotent_noop(self) -> None:
        """tick == 当前 合法：幂等 no-op，仍返回新实例（重建模式）。"""
        runtime = _runtime(tick=12)
        result = set_logical_tick(runtime, 12)
        assert result.logical_tick == 12
        assert result is not runtime
        assert result == runtime  # 值相等（重建产物与原状态语义一致）

    def test_forward_jump_single_step(self) -> None:
        """单调推进：0 → 30 一步跳变（fast-forward 核心，§2.4 / D-P3-03 不逐 tick 迭代）。"""
        result = set_logical_tick(_runtime(tick=0), 30)
        assert result.logical_tick == 30
        assert LogicalClock.of(result).tick == 30

    @pytest.mark.parametrize("from_tick,to_tick", ((0, 1), (11, 12), (29, 30), (30, 31)))
    def test_monotonic_forward_progression(self, from_tick: int, to_tick: int) -> None:
        assert set_logical_tick(_runtime(tick=from_tick), to_tick).logical_tick == to_tick

    def test_self_not_mutated(self) -> None:
        """重建模式：原 RuntimeState 不变（frozen 契约 + 新实例返回）。"""
        runtime = _runtime(tick=0, lifecycle=RuntimeLifecycle.RUNNING)
        result = set_logical_tick(runtime, 30)
        assert runtime.logical_tick == 0
        assert result.logical_tick == 30
        assert runtime is not result

    def test_only_logical_tick_changes(self) -> None:
        """只写 logical_tick：其余簿记字段逐一保持（与 revision 解耦，D-P2-18 原文）。"""
        action = _action()
        runtime = _runtime(
            tick=5,
            lifecycle=RuntimeLifecycle.RUNNING,
            active_actions={action.instance_id: action},
        )
        result = set_logical_tick(runtime, 35)
        assert result.logical_tick == 35
        assert result.lifecycle is RuntimeLifecycle.RUNNING
        assert result.active_actions == runtime.active_actions
        assert result.scheduler_queue == runtime.scheduler_queue
        assert result.actor_wakeups == runtime.actor_wakeups
        assert result.schema_version == runtime.schema_version

    def test_tick_is_pure_count_no_unit_conversion(self) -> None:
        """刻语义（§2.2 / D-P3-01）：core 单位无关、只计数 tick。

        1 tick ≙ 1 世界分钟是 P5 内容层默认映射——本模块不做任何换算：
        写入 30 即读回 30（逐字保持，Gate 数字 30/12 字面对齐的基础）。
        """
        result = set_logical_tick(_runtime(tick=0), 30)
        assert result.logical_tick == 30
        assert set_logical_tick(_runtime(tick=0), 12).logical_tick == 12


class TestNextDueTick:
    """§3.3 / §2.4：fast-forward 终点判据（min(queue.due_tick)；队列空 → None）。"""

    def test_empty_queue_returns_none(self) -> None:
        """队列空 → None（无更多调度工作，确定性终点）。"""
        assert next_due_tick(_runtime()) is None

    def test_min_due_tick(self) -> None:
        runtime = _runtime()
        for due in (5, 1, 5, 9, 1):
            runtime = enqueue_scheduled_event(
                runtime, make_scheduled_event("wakeup", due, payload={"actor_id": "ent_a"})
            )
        assert next_due_tick(runtime) == 1

    def test_single_entry(self) -> None:
        runtime = enqueue_scheduled_event(
            _runtime(), make_scheduled_event("wakeup", 7, payload={"actor_id": "ent_a"})
        )
        assert next_due_tick(runtime) == 7

    def test_identity_with_queue_min_after_clock_jump(self) -> None:
        """时钟跳变后 next_due_tick 与队列最小值恒等（D-P3-05 可断言口径）。

        时钟跳变不消费队列（消费是 take_due 的职责）——故恒等口径是
        ``next_due_tick(runtime) == min(队列 due_tick)``，与当前刻无关；
        跳变前后逐一断言。完整的"取批 → 跳变"主循环口径见
        test_event_queue.py::TestTakeDue::test_clock_jump_then_next_due_tick_identity。
        """
        runtime = _runtime()
        # 交错入队（t=5, t=1, t=5）：写时稳定排序后 [t1, t5(A), t5(B)]
        a = make_scheduled_event("action_end", 5, payload={"instance_id": "act_a"})
        b = make_scheduled_event("wakeup", 1, payload={"actor_id": "ent_a"})
        c = make_scheduled_event("action_end", 5, payload={"instance_id": "act_b"})
        runtime = enqueue_scheduled_event(runtime, a)
        runtime = enqueue_scheduled_event(runtime, b)
        runtime = enqueue_scheduled_event(runtime, c)

        def _identity(state: RuntimeState) -> None:
            queue = state.scheduler_queue
            assert next_due_tick(state) == (min(e.due_tick for e in queue) if queue else None)

        _identity(runtime)
        # 时钟跳变（D-P3-03 核心）：队列不变 → 最小值不变 → 恒等仍成立
        jumped = set_logical_tick(runtime, 1)
        _identity(jumped)
        assert next_due_tick(jumped) == 1
        jumped = set_logical_tick(jumped, 5)
        _identity(jumped)
        assert next_due_tick(jumped) == 1  # t=1 条目仍在队列中（未被时钟跳变消费）
        # 队列耗尽 → None
        assert next_due_tick(set_logical_tick(_runtime(), 99)) is None


class TestRebuildRuntime:
    """§3.3：RuntimeState 重建公共缝隙（model_dump → 更新 → model_validate）。"""

    def test_no_updates_is_value_identity(self) -> None:
        """零更新重建：值相等（P1 唯一合法序列化路径的 round-trip 恒等）。"""
        runtime, action = _runtime_with_action()
        rebuilt = rebuild_runtime(runtime)
        assert rebuilt == runtime
        assert rebuilt is not runtime

    def test_updates_applied(self) -> None:
        runtime = _runtime(tick=0)
        rebuilt = rebuild_runtime(runtime, logical_tick=30, lifecycle=RuntimeLifecycle.RUNNING)
        assert rebuilt.logical_tick == 30
        assert rebuilt.lifecycle is RuntimeLifecycle.RUNNING
        assert runtime.logical_tick == 0  # self 不变

    def test_unmentioned_fields_preserved(self) -> None:
        action = _action()
        runtime = _runtime(
            tick=5,
            lifecycle=RuntimeLifecycle.STEPPING,
            active_actions={action.instance_id: action},
        )
        rebuilt = rebuild_runtime(runtime, logical_tick=6)
        assert rebuilt.lifecycle is RuntimeLifecycle.STEPPING
        assert rebuilt.active_actions == runtime.active_actions
        assert rebuilt.schema_version == runtime.schema_version

    def test_active_actions_key_consistency_validator_rerun(self) -> None:
        """重跑 active_actions 键一致性 model_validator：键不符 → ValidationError。"""
        runtime, action = _runtime_with_action()
        bad_key = new_action_instance_id()
        assert bad_key != action.instance_id
        with pytest.raises(ValidationError):
            rebuild_runtime(runtime, active_actions={bad_key: action})

    def test_active_actions_valid_key_passes(self) -> None:
        """键一致（== instance_id）的重建通过 validator（正例对照）。"""
        _, action = _runtime_with_action()
        runtime = _runtime()
        rebuilt = rebuild_runtime(runtime, active_actions={action.instance_id: action})
        assert rebuilt.active_actions == {action.instance_id: action}
        assert next(iter(rebuilt.active_actions)) == action.instance_id

    def test_scheduler_queue_update_roundtrip(self) -> None:
        """队列字段更新经重建保持类型（ScheduledEvent 列表重建，typed ID 保持）。"""
        runtime = _runtime()
        event = make_scheduled_event("wakeup", 3, payload={"actor_id": "ent_a"})
        rebuilt = rebuild_runtime(runtime, scheduler_queue=[event])
        assert rebuilt.scheduler_queue == [event]
        assert type(rebuilt.scheduler_queue[0]) is ScheduledEvent
        assert str(rebuilt.scheduler_queue[0].entry_id).startswith("sch_")


class TestErrorFamily:
    """D-P3-16：P3 错误基类族（宿主置 clock.py 依赖叶，无环）。"""

    def test_scheduler_error_derives_value_error(self) -> None:
        assert issubclass(SchedulerError, ValueError)

    def test_clock_rollback_error_derives_scheduler_error(self) -> None:
        assert issubclass(ClockRollbackError, SchedulerError)

    def test_clock_rollback_error_catchable_as_value_error(self) -> None:
        """异常族统一可捕获：ValueError 级捕获可接住时钟回退（P1/P2 同族）。"""
        with pytest.raises(ValueError):
            set_logical_tick(_runtime(tick=12), 11)


class TestModuleSurface:
    """设计文档 §3.3 代码块导出面：模块 __all__ 恰 6 符号。"""

    def test_all_exports_exactly_six_symbols(self) -> None:
        import src.engine_v2.core.clock as clock_module

        assert clock_module.__all__ == [
            "LogicalClock",
            "set_logical_tick",
            "next_due_tick",
            "rebuild_runtime",
            "SchedulerError",
            "ClockRollbackError",
        ]

    def test_all_names_resolvable_in_module(self) -> None:
        import src.engine_v2.core.clock as clock_module

        for name in clock_module.__all__:
            assert hasattr(clock_module, name), f"{name} 未绑定到模块属性"
