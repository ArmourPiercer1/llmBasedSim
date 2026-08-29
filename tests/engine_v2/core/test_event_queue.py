"""P3-T01 event_queue.py 单元测试（设计文档 §3.4 全量 + §2.5 队列语义/不变量）。

依据 ``docs/v2/contracts/P3-scheduler-time-action-design.md``：

- **kind 封闭词表**（§2.5 表唯一定义处，D-P3-04）：7 kind；词表外 →
  :class:`QueueInvariantError`（``make_scheduled_event`` 构造点拒绝，
  可检查不静默）；
- **逐 kind 必填 payload 键**（§2.5 表）：7 kind × 缺键矩阵 → 抛；
  完整 payload 正例逐 kind 通过；``payload=None`` 视同空 dict（必缺键）；
  多余键不违例（"必填"语义——``kind="event"`` effects 形态本就携带
  额外 ``producer`` 键，§2.5 注）；
- **``kind="event"`` 互斥**（唯一口径，R7-S4 风险 3）：``trigger_id`` 与
  ``effects`` 恰居其一——双缺报错、双在报错（互斥），单居其一通过
  （两种声明式形态均合法，payload 内禁止可执行物）；
- **due_tick 校验**：负刻（``due_tick < 0``）构造点抛；
- **禁止过去调度**（D-P3-05 不变量 3，与 D-P3-02 单调性同源）：
  ``enqueue_scheduled_event`` 传 ``due_tick < runtime.logical_tick`` →
  :class:`QueueInvariantError`；``due_tick == logical_tick`` 合法（§2.4
  边界情形：同刻新入队追加同刻批尾部）；
- **身份唯一**（D-P3-05 不变量 4，KBC-2 同款去重纪律）：重复 ``entry_id``
  入队 → 抛（构造点拒绝）；缺省 ``entry_id`` 经 ``new_scheduled_entry_id()``
  （``sch_`` 前缀，ids.py 冻结工厂）签发，两次调用不同；
- **写时稳定排序**（D-P3-05 不变量 1，单键 ``due_tick``）：交错入队
  （t=5, t=1, t=5）→ 队列 ``[t1, t5(A), t5(B)]``——任意时刻可检（K7），
  调度器永不重排；
- **同刻批 FIFO 稳定序**（D-P3-05 不变量 2）：同 due_tick 依序入队
  A, B, C → ``take_due`` 批序 A, B, C（先入队先处理，对抗 A3）；
- **take_due 抽取语义**（§3.4 / §2.4）：抽走最小 due_tick 的**整批**
  （批后队列前移）；批序 = 队列序 = 插入序；队列空 → ``None``
  （fast-forward 终点判据）；返回新 RuntimeState、self 不变；
- **due_tick 跳变恒等**：时钟跳变（``set_logical_tick``）后
  ``next_due_tick`` 与队列最小值恒等（复现 §2.4 主循环路径）；
- **序列化零新增**（§2.5 / G3-2 单元层）：队列经 P1 ``dump_json`` /
  ``load_json`` round-trip——``sch_`` 前缀重建（typed ID 类型保持）、
  ``assert_json_clean`` 通过、``==`` 恒等。

全部用例无网络、无 LLM、无 API key、无墙钟（§8.3 P3 专项 import 边界：
禁 ``datetime``/``time``/``random``/``asyncio``）。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import JsonValue

from src.engine_v2.core.clock import (
    LogicalClock,
    SchedulerError,
    next_due_tick,
    set_logical_tick,
)
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.event_queue import (
    SCHEDULED_EVENT_KINDS,
    QueueInvariantError,
    enqueue_scheduled_event,
    make_scheduled_event,
    take_due,
)
from src.engine_v2.core.ids import ScheduledEntryId, new_scheduled_entry_id
from src.engine_v2.core.serialization import assert_json_clean, dump_json, load_json
from src.engine_v2.core.state import RuntimeState, ScheduledEvent

# —— 测试专用构造助手 ——


def _runtime(tick: int = 0, **kwargs: Any) -> RuntimeState:
    """构造 ``logical_tick=tick`` 的测试 RuntimeState。"""
    return RuntimeState(logical_tick=tick, **kwargs)


def _event(kind: str, due_tick: int, **payload: JsonValue) -> ScheduledEvent:
    """经 ``make_scheduled_event`` 构造条目（P3 构造点，词表/payload 校验生效）。"""
    return make_scheduled_event(kind, due_tick, payload=payload)


#: §2.5 表逐 kind 完整 payload 正例（"必填 payload 键"列的字面构造）。
_FULL_PAYLOADS: dict[str, dict[str, JsonValue]] = {
    "action_start": {"instance_id": "act_a"},
    "action_checkpoint": {"instance_id": "act_a"},
    "action_end": {"instance_id": "act_a"},
    "deadline": {"instance_id": "act_a"},
    "wakeup": {"actor_id": "ent_a"},
    "decision_boundary": {"boundary_id": "boundary_1", "actor_id": "ent_a"},
    "event": {"trigger_id": "scenario.encounter_12"},
}


class TestKindVocabulary:
    """§2.5 / D-P3-04：kind 封闭词表（§2.5 表为唯一定义处，7 kind）。"""

    def test_kinds_exactly_the_seven(self) -> None:
        assert SCHEDULED_EVENT_KINDS == frozenset(
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

    @pytest.mark.parametrize("kind", SCHEDULED_EVENT_KINDS)
    def test_each_vocabulary_kind_constructs(self, kind: str) -> None:
        """词表内 7 kind × 完整 payload：构造通过（正例矩阵）。"""
        event = make_scheduled_event(kind, 5, payload=dict(_FULL_PAYLOADS[kind]))
        assert event.kind == kind
        assert event.due_tick == 5

    @pytest.mark.parametrize(
        "kind",
        ("action_resume", "Action_Start", "TICK", "tick", "checkpoint", "", "act_start"),
    )
    def test_out_of_vocabulary_kind_raises(self, kind: str) -> None:
        """词表外 kind → QueueInvariantError（构造点拒绝，可检查不静默）。"""
        with pytest.raises(QueueInvariantError):
            make_scheduled_event(kind, 5, payload={"instance_id": "act_a"})


class TestRequiredPayloadKeys:
    """§2.5 表：逐 kind 必填 payload 键（7 kind × 缺键矩阵 → 抛）。"""

    @pytest.mark.parametrize(
        "kind", ("action_start", "action_checkpoint", "action_end", "deadline")
    )
    def test_action_kinds_missing_instance_id_raises(self, kind: str) -> None:
        """action_start/checkpoint/end/deadline 必填 instance_id（缺键矩阵 4/7 kind）。"""
        payload = {k: v for k, v in _FULL_PAYLOADS[kind].items() if k != "instance_id"}
        with pytest.raises(QueueInvariantError):
            make_scheduled_event(kind, 5, payload=payload)

    def test_wakeup_missing_actor_id_raises(self) -> None:
        """wakeup 必填 actor_id（payload 仅携带 actor_id，reason 不入 payload，§2.5 尾注）。"""
        with pytest.raises(QueueInvariantError):
            make_scheduled_event("wakeup", 5, payload={})
        with pytest.raises(QueueInvariantError):
            make_scheduled_event("wakeup", 5, payload={"reason": "boundary_1"})

    @pytest.mark.parametrize("missing", ("boundary_id", "actor_id"))
    def test_decision_boundary_missing_either_key_raises(self, missing: str) -> None:
        """decision_boundary 必填 boundary_id 与 actor_id（缺一即抛）。"""
        payload = {k: v for k, v in _FULL_PAYLOADS["decision_boundary"].items() if k != missing}
        with pytest.raises(QueueInvariantError):
            make_scheduled_event("decision_boundary", 5, payload=payload)

    @pytest.mark.parametrize("kind", ("action_start", "wakeup", "decision_boundary", "deadline"))
    def test_payload_none_equivalent_to_empty_dict(self, kind: str) -> None:
        """payload=None 视同空 dict：必填键必缺 → 抛。"""
        with pytest.raises(QueueInvariantError):
            make_scheduled_event(kind, 5)

    def test_extra_payload_keys_allowed(self) -> None:
        """必填语义（非"恰为"）：多余键不违例。"""
        event = _event(
            "action_start", 5, instance_id="act_a", note="scheduled by submit_proposal"
        )
        assert event.payload["instance_id"] == "act_a"
        assert event.payload["note"] == "scheduled by submit_proposal"

    def test_full_payloads_pass_all_kinds(self) -> None:
        """§2.5 表完整 payload 正例矩阵：7 kind 全部通过。"""
        for kind, payload in _FULL_PAYLOADS.items():
            event = make_scheduled_event(kind, 5, payload=dict(payload))
            assert set(event.payload.keys()) == set(payload.keys())


class TestEventKindExclusive:
    """§2.5 注（R7-S4 风险 3）：kind="event" 的 trigger_id/effects 恰居其一（互斥，唯一口径）。"""

    def test_both_missing_raises(self) -> None:
        """双缺报错：缺 trigger_id 且无 effects → QueueInvariantError。"""
        with pytest.raises(QueueInvariantError):
            make_scheduled_event("event", 5, payload={})
        with pytest.raises(QueueInvariantError):
            make_scheduled_event("event", 5, payload={"producer": "test.producer"})

    def test_both_present_raises(self) -> None:
        """双在报错（互斥）：trigger_id 与 effects 同时存在 → QueueInvariantError。"""
        with pytest.raises(QueueInvariantError):
            make_scheduled_event(
                "event",
                5,
                payload={"trigger_id": "scenario.encounter_12", "effects": []},
            )

    def test_trigger_id_only_passes(self) -> None:
        """声明式形态 1：引用命名的 P2 CascadeTrigger（注册表持有）。"""
        event = make_scheduled_event("event", 12, payload={"trigger_id": "scenario.encounter_12"})
        assert event.due_tick == 12
        assert event.payload == {"trigger_id": "scenario.encounter_12"}

    def test_effects_only_passes_with_producer(self) -> None:
        """声明式形态 2：显式预声明效果批（携带 producer，payload 内禁止可执行物）。"""
        effects: list[JsonValue] = [{"effect_type": "core.set_world_variable"}]
        event = make_scheduled_event(
            "event", 12, payload={"effects": effects, "producer": "test.producer"}
        )
        assert event.payload["effects"] == effects
        assert event.payload["producer"] == "test.producer"


class TestDueTickValidation:
    """due_tick 校验：负刻（构造点）/ 过去调度（入队点，D-P3-05 不变量 3）。"""

    def test_negative_due_tick_raises_at_construction(self) -> None:
        """due_tick < 0 → QueueInvariantError（tick 非负，与 D-P3-02 单调性同源）。"""
        with pytest.raises(QueueInvariantError):
            make_scheduled_event("wakeup", -1, payload={"actor_id": "ent_a"})
        with pytest.raises(QueueInvariantError):
            make_scheduled_event("wakeup", -30, payload={"actor_id": "ent_a"})

    def test_zero_due_tick_legal(self) -> None:
        """due_tick = 0 合法（刻 0 是有效逻辑刻）。"""
        event = make_scheduled_event("wakeup", 0, payload={"actor_id": "ent_a"})
        assert event.due_tick == 0

    def test_past_scheduling_rejected_at_enqueue(self) -> None:
        """过去调度：due_tick < logical_tick → QueueInvariantError（时间只能向前）。"""
        runtime = _runtime(tick=10)
        event = make_scheduled_event("wakeup", 9, payload={"actor_id": "ent_a"})
        with pytest.raises(QueueInvariantError):
            enqueue_scheduled_event(runtime, event)

    def test_due_tick_equal_to_clock_allowed(self) -> None:
        """due_tick == logical_tick 合法（§2.4 边界情形：同刻批尾部，稳定 FIFO 覆盖）。"""
        runtime = _runtime(tick=10)
        event = make_scheduled_event("wakeup", 10, payload={"actor_id": "ent_a"})
        result = enqueue_scheduled_event(runtime, event)
        assert result.scheduler_queue == [event]


class TestEntryIdUniqueness:
    """D-P3-05 不变量 4：身份唯一（重复 entry_id → 抛；sch_ 工厂签发）。"""

    def test_duplicate_entry_id_rejected(self) -> None:
        """同一 entry_id 二次入队（仍在队列中）→ QueueInvariantError（构造点拒绝）。"""
        runtime = _runtime()
        event = make_scheduled_event("wakeup", 5, payload={"actor_id": "ent_a"})
        runtime = enqueue_scheduled_event(runtime, event)
        with pytest.raises(QueueInvariantError):
            enqueue_scheduled_event(runtime, event)
        # 队列未被部分修改（拒绝即整体不变）
        assert len(runtime.scheduler_queue) == 1

    def test_reenqueue_after_take_allowed(self) -> None:
        """重复判定针对当前队列：take_due 抽走后同一 entry_id 可再次入队。

        RuntimeState 即调度全部真相（K7 状态显式）——队列外无历史记忆，
        生命周期唯一性不可表达，故语义 = 当前队列内唯一。
        """
        runtime = _runtime()
        event = make_scheduled_event("wakeup", 5, payload={"actor_id": "ent_a"})
        runtime = enqueue_scheduled_event(runtime, event)
        out = take_due(runtime)
        assert out is not None
        runtime, _batch = out
        result = enqueue_scheduled_event(runtime, event)
        assert result.scheduler_queue == [event]

    def test_default_entry_id_sch_prefix_and_fresh(self) -> None:
        """entry_id 缺省 new_scheduled_entry_id()（sch_ 前缀，ids.py 冻结工厂）。"""
        a = make_scheduled_event("wakeup", 5, payload={"actor_id": "ent_a"})
        b = make_scheduled_event("wakeup", 5, payload={"actor_id": "ent_a"})
        assert type(a.entry_id) is ScheduledEntryId
        assert str(a.entry_id).startswith("sch_")
        assert a.entry_id != b.entry_id  # 每次构造新签发

    def test_explicit_entry_id_respected(self) -> None:
        explicit = new_scheduled_entry_id()
        event = make_scheduled_event(
            "wakeup", 5, payload={"actor_id": "ent_a"}, entry_id=explicit
        )
        assert event.entry_id == explicit
        assert str(event.entry_id).startswith("sch_")


class TestStableFifoOrdering:
    """D-P3-05 不变量 1/2：写时稳定排序（due_tick 单键）+ 同刻批 FIFO 稳定序。"""

    def test_same_tick_fifo_order(self) -> None:
        """同刻稳定 FIFO：同 due_tick 依序入队 A, B, C → 队列序与 take_due 批序均 A, B, C。"""
        runtime = _runtime()
        a = _event("action_end", 30, instance_id="act_a")
        b = _event("action_checkpoint", 30, instance_id="act_b")
        c = _event("wakeup", 30, actor_id="ent_c")
        runtime = enqueue_scheduled_event(runtime, a)
        runtime = enqueue_scheduled_event(runtime, b)
        runtime = enqueue_scheduled_event(runtime, c)
        assert [e.entry_id for e in runtime.scheduler_queue] == [a.entry_id, b.entry_id, c.entry_id]
        out = take_due(runtime)
        assert out is not None
        _runtime_after, batch = out
        assert [e.entry_id for e in batch] == [a.entry_id, b.entry_id, c.entry_id]

    def test_interleaved_enqueue_single_key_stable_sort(self) -> None:
        """交错入队（t=5, t=1, t=5）→ 队列 [t1, t5(A), t5(B)]（单键稳定排序）。"""
        runtime = _runtime()
        a = _event("action_end", 5, instance_id="act_a")
        b = _event("wakeup", 1, actor_id="ent_b")
        c = _event("action_end", 5, instance_id="act_c")
        runtime = enqueue_scheduled_event(runtime, a)
        runtime = enqueue_scheduled_event(runtime, b)
        runtime = enqueue_scheduled_event(runtime, c)
        assert [e.entry_id for e in runtime.scheduler_queue] == [
            b.entry_id,
            a.entry_id,
            c.entry_id,
        ]
        # 同 tick 的相对序 = 插入序（A 先于 C），未被重排
        t5 = [e.entry_id for e in runtime.scheduler_queue if e.due_tick == 5]
        assert t5 == [a.entry_id, c.entry_id]

    def test_queue_sorted_at_all_times(self) -> None:
        """K7 可检查性：任意时刻（多次交错入队后）队列按 due_tick 非降。"""
        runtime = _runtime()
        for due in (9, 3, 7, 3, 1, 7, 5):
            runtime = enqueue_scheduled_event(
                runtime, make_scheduled_event("wakeup", due, payload={"actor_id": "ent_a"})
            )
        dues = [e.due_tick for e in runtime.scheduler_queue]
        assert dues == sorted(dues)
        assert dues == [1, 3, 3, 5, 7, 7, 9]

    def test_enqueue_does_not_mutate_original(self) -> None:
        """纯函数：原 RuntimeState 队列不变（frozen 契约 + 新实例返回）。"""
        runtime = _runtime()
        a = _event("wakeup", 5, actor_id="ent_a")
        result = enqueue_scheduled_event(runtime, a)
        assert runtime.scheduler_queue == []
        assert result.scheduler_queue == [a]
        assert runtime is not result

    def test_enqueue_preserves_other_fields(self) -> None:
        runtime = _runtime(tick=2)
        a = _event("wakeup", 5, actor_id="ent_a")
        result = enqueue_scheduled_event(runtime, a)
        assert result.logical_tick == 2
        assert result.active_actions == runtime.active_actions
        assert result.actor_wakeups == runtime.actor_wakeups
        assert result.lifecycle is runtime.lifecycle
        assert result.schema_version == runtime.schema_version


class TestTakeDue:
    """§3.4 / §2.4：take_due 抽取语义（最小 due_tick 整批；批后队列前移；空 → None）。"""

    def test_empty_queue_returns_none(self) -> None:
        """队列空 → None（fast-forward 终点判据，§2.4）。"""
        assert take_due(_runtime()) is None

    def test_extract_whole_batch_and_queue_advances(self) -> None:
        """抽走整批（同刻批），批后队列前移：逐批抽至耗尽 → None。"""
        runtime = _runtime()
        a = _event("action_end", 5, instance_id="act_a")
        b = _event("wakeup", 1, actor_id="ent_b")
        c = _event("action_end", 5, instance_id="act_c")
        runtime = enqueue_scheduled_event(runtime, a)
        runtime = enqueue_scheduled_event(runtime, b)
        runtime = enqueue_scheduled_event(runtime, c)

        out = take_due(runtime)
        assert out is not None
        runtime, batch1 = out
        assert [e.entry_id for e in batch1] == [b.entry_id]  # 最小刻 t=1 整批
        assert [e.entry_id for e in runtime.scheduler_queue] == [a.entry_id, c.entry_id]

        out = take_due(runtime)
        assert out is not None
        runtime, batch2 = out
        assert [e.entry_id for e in batch2] == [a.entry_id, c.entry_id]  # t=5 同刻批 FIFO
        assert runtime.scheduler_queue == []
        assert take_due(runtime) is None

    def test_batch_first_entry_due_tick_is_current_tick(self) -> None:
        """§2.4 主循环口径：t = batch[0].due_tick（批内 due_tick 恒等）。"""
        runtime = _runtime()
        for due in (8, 2, 2, 2):
            runtime = enqueue_scheduled_event(
                runtime, make_scheduled_event("wakeup", due, payload={"actor_id": "ent_a"})
            )
        out = take_due(runtime)
        assert out is not None
        _runtime_after, batch = out
        t = batch[0].due_tick
        assert t == 2
        assert all(e.due_tick == t for e in batch)
        assert len(batch) == 3

    def test_clock_jump_then_next_due_tick_identity(self) -> None:
        """due_tick 跳变后 next_due_tick 与队列最小值恒等（复现 §2.4 主循环）。

        取批 → 时钟跳变至批首刻（D-P3-03 核心：不逐 tick 迭代）→ 恒等再断言，
        直至队列耗尽 → None（确定性终点）。
        """
        runtime = _runtime()
        for due in (5, 1, 5, 9, 5):
            runtime = enqueue_scheduled_event(
                runtime, make_scheduled_event("wakeup", due, payload={"actor_id": "ent_a"})
            )

        extracted: list[tuple[int, int]] = []  # (t, 批大小)
        while True:
            out = take_due(runtime)
            if out is None:
                break
            runtime, batch = out
            t = batch[0].due_tick
            if t > LogicalClock.of(runtime).tick:
                runtime = set_logical_tick(runtime, t)
            # 恒等断言：next_due_tick == 队列最小值（含跳变前后）
            queue = runtime.scheduler_queue
            assert next_due_tick(runtime) == (min(e.due_tick for e in queue) if queue else None)
            extracted.append((t, len(batch)))
        assert extracted == [(1, 1), (5, 3), (9, 1)]
        assert runtime.logical_tick == 9
        assert next_due_tick(runtime) is None

    def test_take_due_returns_new_runtime(self) -> None:
        """纯函数：原 RuntimeState 队列不变（self 不修改）。"""
        runtime = _runtime()
        a = _event("wakeup", 3, actor_id="ent_a")
        runtime = enqueue_scheduled_event(runtime, a)
        out = take_due(runtime)
        assert out is not None
        runtime_after, _batch = out
        assert runtime.scheduler_queue == [a]  # 原实例队列保持
        assert runtime_after.scheduler_queue == []
        assert runtime_after is not runtime


class TestSerializationRoundtrip:
    """§2.5 / G3-2 单元层：序列化零新增——P1 dump_json/load_json round-trip。"""

    def test_queue_roundtrip_identity(self) -> None:
        """队列 round-trip：== 恒等、sch_ 前缀重建（typed ID 类型保持）。"""
        runtime = _runtime(tick=12)
        events = [
            _event("action_end", 30, instance_id="act_a"),
            _event("wakeup", 12, actor_id="ent_a"),
            _event("event", 20, trigger_id="scenario.encounter_12"),
        ]
        for event in events:
            runtime = enqueue_scheduled_event(runtime, event)

        text = dump_json(runtime)
        assert_json_clean(json.loads(text))  # JSON 原生类型守卫（铁律 1）

        restored = load_json(RuntimeState, text)
        assert restored == runtime
        assert restored.scheduler_queue == runtime.scheduler_queue
        for original, entry in zip(runtime.scheduler_queue, restored.scheduler_queue):
            assert type(entry.entry_id) is ScheduledEntryId  # sch_ 前缀重建
            assert str(entry.entry_id).startswith("sch_")
            assert entry.entry_id == original.entry_id
            assert type(entry.due_tick) is int

    def test_scheduled_event_standalone_roundtrip(self) -> None:
        """单条目 round-trip（条目即 P1 冻结类型，序列化零新增）。"""
        event = make_scheduled_event(
            "event", 12, payload={"effects": [{"effect_type": "core.set_world_variable"}]}
        )
        text = dump_json(event)
        assert_json_clean(json.loads(text))
        restored = load_json(ScheduledEvent, text)
        assert restored == event
        assert type(restored.entry_id) is ScheduledEntryId

    def test_contract_model_base(self) -> None:
        """ScheduledEvent 复用确认（D-P3-04：不新建条目类型，P1 冻结 ContractModel）。"""
        assert issubclass(ScheduledEvent, ContractModel)


class TestModuleSurface:
    """设计文档 §3.4 代码块导出面：模块 __all__ 恰 5 符号 + 错误族继承。"""

    def test_all_exports_exactly_five_symbols(self) -> None:
        import src.engine_v2.core.event_queue as event_queue_module

        assert event_queue_module.__all__ == [
            "SCHEDULED_EVENT_KINDS",
            "make_scheduled_event",
            "enqueue_scheduled_event",
            "take_due",
            "QueueInvariantError",
        ]

    def test_all_names_resolvable_in_module(self) -> None:
        import src.engine_v2.core.event_queue as event_queue_module

        for name in event_queue_module.__all__:
            assert hasattr(event_queue_module, name), f"{name} 未绑定到模块属性"

    def test_queue_invariant_error_hierarchy(self) -> None:
        """D-P3-16：QueueInvariantError ⊂ SchedulerError ⊂ ValueError（宿主 clock.py）。"""
        assert issubclass(QueueInvariantError, SchedulerError)
        assert issubclass(SchedulerError, ValueError)

    def test_queue_invariant_error_catchable_as_value_error(self) -> None:
        with pytest.raises(ValueError):
            make_scheduled_event("bogus_kind", 5, payload={})
