"""P3-T05 ``interrupt.py`` 决策边界与声明式条件求值单测（设计文档 §3.7 / §6.1）。

覆盖点（§6.1 L1124 + 简报第 5 步）：

- 契约模型：``InterruptCondition`` / ``DecisionBoundary`` / ``BoundaryReport``
  的 frozen / extra-forbid / kind 互斥校验矩阵；
- 四个内置条件 kind（``event_type`` / ``world_variable`` / ``entity_component`` /
  ``time``）各自命中 / 未命中 / 缺态 = miss（False，非错误）；
- 静态参数非法（缺参数 / 未知 op / time tick 非 int / 不可比类型）= 抛
  ``SchedulerError``（可检查而非静默，D-P3-16 纪律）；
- ``UnknownConditionError``：未知 kind 且无注册 resolver；
- ``ConditionResolverRegistry``：注册 / 解析 / miss / 重复注册 / 共享默认
  实例禁注册（E-P3-39④）；
- ``evaluate_boundaries``：blocking 规则（D-P3-10 双向）、interrupt=False
  空实例、scheduled 到期门槛、注册序稳定性、非 ACTIVE / 非 interruptible
  排除、纯函数（不突变 runtime）。

纪律：直连子模块导入（不经包 ``__init__``）；零 wall-clock / random /
asyncio；resolver 对动态状态缺失返回 False，对静态参数非法抛错。
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from src.engine_v2.core.actions import (
    ActionLifecycleStatus,
    ActionTypeId,
    ActiveAction,
)
from src.engine_v2.core.clock import SchedulerError
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.events import DomainEvent, EventTypeId
from src.engine_v2.core.ids import (
    ActionInstanceId,
    EntityId,
    EventId,
    ProducerId,
)
from src.engine_v2.core.interrupt import (
    BUILTIN_CONDITION_RESOLVERS,
    CONDITION_KINDS,
    BoundaryReport,
    ConditionResolver,
    ConditionResolverRegistry,
    DecisionBoundary,
    InterruptCondition,
    UnknownConditionError,
    evaluate_boundaries,
    evaluate_condition,
)
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.reducer import guard
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.state import RuntimeState, WorldState

# --------------------------------------------------------------------------- #
# 常量 / 小夹具
# --------------------------------------------------------------------------- #

_PLAYER = EntityId("player_1")
_NPC = EntityId("npc_1")
_ORIG = ProducerId("origin_scenario")
_PROV = Provenance(producer_id=_ORIG, origin=OriginKind.SCENARIO)


def _event(event_type: str, *, revision: int = 1) -> DomainEvent:
    return DomainEvent(
        event_id=EventId("evt_001"),
        event_type=EventTypeId(event_type),
        world_revision=Revision(revision),
        source_system=_ORIG,
        provenance=_PROV,
    )


def _world(
    *,
    variables: dict[str, Any] | None = None,
    player_components: dict[ComponentTypeId, dict[str, Any]] | None = None,
) -> WorldState:
    return WorldState(
        entities={
            _PLAYER: EntityRecord(
                entity_id=_PLAYER,
                components=player_components or {},
            ),
            _NPC: EntityRecord(entity_id=_NPC),
        },
        world_variables=variables or {},
    )


def _view(
    *,
    variables: dict[str, Any] | None = None,
    player_components: dict[ComponentTypeId, dict[str, Any]] | None = None,
):
    return guard(_world(variables=variables, player_components=player_components))


def _condition(
    kind: str, parameters: dict[str, Any] | None = None, cid: str = "cond_1"
) -> InterruptCondition:
    return InterruptCondition(condition_id=cid, kind=kind, parameters=parameters or {})


def _boundary(
    kind: str,
    *,
    actor: EntityId = _PLAYER,
    due_tick: int | None = None,
    condition: InterruptCondition | None = None,
    blocking: bool = False,
    interrupt: bool = True,
    reason: str | None = None,
    bid: str = "bnd_1",
) -> DecisionBoundary:
    return DecisionBoundary(
        boundary_id=bid,
        actor_id=actor,
        kind=kind,
        due_tick=due_tick,
        condition=condition,
        blocking=blocking,
        interrupt=interrupt,
        reason=reason,
    )


def _active(
    instance_id: str,
    actor: EntityId,
    *,
    status: ActionLifecycleStatus = ActionLifecycleStatus.ACTIVE,
    interruptible: bool = True,
) -> ActiveAction:
    return ActiveAction(
        instance_id=ActionInstanceId(instance_id),
        action_id=ActionTypeId("walk"),
        actor_id=actor,
        status=status,
        start_tick=0,
        base_world_revision=Revision(0),
        provenance=_PROV,
        interruptible=interruptible,
    )


def _registry() -> ConditionResolverRegistry:
    return ConditionResolverRegistry()


class _SpyResolver:
    """记录入参并返回固定结果的自定义 resolver（Protocol 结构满足）。"""

    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def evaluate(self, condition, view, events, *, tick: int) -> bool:
        self.calls.append(
            {
                "condition_id": condition.condition_id,
                "tick": tick,
                "n_events": len(events),
                "world_revision": view.world_revision,
            }
        )
        return self.result


# --------------------------------------------------------------------------- #
# 契约模型
# --------------------------------------------------------------------------- #


class TestInterruptConditionModel:
    def test_defaults_empty_parameters(self) -> None:
        cond = InterruptCondition(condition_id="c1", kind="time")
        assert cond.parameters == {}

    def test_parameters_kept(self) -> None:
        cond = _condition("world_variable", {"key": "k", "op": "gt", "value": 1})
        assert cond.parameters["key"] == "k"
        assert cond.parameters["value"] == 1

    def test_frozen(self) -> None:
        cond = _condition("time")
        with pytest.raises(ValidationError):
            cond.kind = "scheduled"  # type: ignore[misc]

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            InterruptCondition(  # type: ignore[call-arg]
                condition_id="c1", kind="time", oops=1
            )


class TestDecisionBoundaryModel:
    def test_defaults(self) -> None:
        b = _boundary("scheduled", due_tick=5)
        assert b.blocking is False
        assert b.interrupt is True
        assert b.reason is None
        assert b.condition is None
        assert b.due_tick == 5

    def test_scheduled_requires_due_tick(self) -> None:
        with pytest.raises(ValidationError):
            _boundary("scheduled")

    def test_scheduled_mutually_excludes_condition(self) -> None:
        with pytest.raises(ValidationError):
            _boundary(
                "scheduled",
                due_tick=5,
                condition=_condition("time"),
            )

    def test_condition_requires_condition(self) -> None:
        with pytest.raises(ValidationError):
            _boundary("condition")

    def test_condition_mutually_excludes_due_tick(self) -> None:
        with pytest.raises(ValidationError):
            _boundary("condition", due_tick=5, condition=_condition("time"))

    def test_unknown_kind_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _boundary("whenever", due_tick=5)

    def test_frozen(self) -> None:
        b = _boundary("scheduled", due_tick=5)
        with pytest.raises(ValidationError):
            b.blocking = True  # type: ignore[misc]


class TestBoundaryReportModel:
    def test_defaults(self) -> None:
        report = BoundaryReport(tick=12, fired=[])
        assert report.fired == []
        assert report.player_blocking is False
        assert report.npc_notices == []

    def test_frozen(self) -> None:
        report = BoundaryReport(tick=0, fired=[], player_blocking=True)
        with pytest.raises(ValidationError):
            report.player_blocking = False  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# 内置条件 kind：命中 / 未命中 / 缺态 = miss
# --------------------------------------------------------------------------- #


class TestBuiltinEventTypeName:
    def test_hit(self) -> None:
        assert evaluate_condition(
            _condition("event_type", {"event_type": "core.set_world_variable"}),
            _view(),
            [_event("core.set_world_variable")],
            tick=7,
            registry=_registry(),
        ) is True

    def test_mismatch_miss(self) -> None:
        assert evaluate_condition(
            _condition("event_type", {"event_type": "other.type"}),
            _view(),
            [_event("core.set_world_variable")],
            tick=7,
            registry=_registry(),
        ) is False

    def test_any_event_match_among_many(self) -> None:
        assert evaluate_condition(
            _condition("event_type", {"event_type": "b"}),
            _view(),
            [_event("a"), _event("b"), _event("c")],
            tick=7,
            registry=_registry(),
        ) is True

    def test_empty_events_miss(self) -> None:
        assert evaluate_condition(
            _condition("event_type", {"event_type": "a"}),
            _view(),
            [],
            tick=7,
            registry=_registry(),
        ) is False


class TestBuiltinWorldVariable:
    @pytest.mark.parametrize(
        ("value", "op", "expected", "hit"),
        [
            (10, "gt", 5, True),
            (5, "gt", 5, False),
            (5, "gte", 5, True),
            (4, "gte", 5, False),
            (3, "lt", 5, True),
            (5, "lt", 5, False),
            (5, "eq", 5, True),
            (6, "eq", 5, False),
        ],
    )
    def test_comparisons(
        self, value: Any, op: str, expected: Any, hit: bool
    ) -> None:
        assert evaluate_condition(
            _condition(
                "world_variable",
                {"key": "flag", "op": op, "value": expected},
            ),
            _view(variables={"flag": value}),
            [],
            tick=7,
            registry=_registry(),
        ) is hit

    def test_missing_key_is_miss_not_error(self) -> None:
        assert evaluate_condition(
            _condition("world_variable", {"key": "absent", "op": "eq", "value": 1}),
            _view(variables={"flag": 1}),
            [],
            tick=7,
            registry=_registry(),
        ) is False

    def test_untyped_eq_hit(self) -> None:
        assert evaluate_condition(
            _condition("world_variable", {"key": "name", "op": "eq", "value": "x"}),
            _view(variables={"name": "x"}),
            [],
            tick=7,
            registry=_registry(),
        ) is True


class TestBuiltinEntityComponent:
    def _components(self) -> dict[ComponentTypeId, dict[str, Any]]:
        return {
            ComponentTypeId("movement"): {"position": {"x": 30, "y": 0}, "hp": 3}
        }

    def test_field_path_hit(self) -> None:
        assert evaluate_condition(
            _condition(
                "entity_component",
                {
                    "entity_id": "player_1",
                    "component_type": "movement",
                    "field_path": "position.x",
                    "op": "eq",
                    "value": 30,
                },
            ),
            _view(player_components=self._components()),
            [],
            tick=7,
            registry=_registry(),
        ) is True

    def test_scalar_field_hit(self) -> None:
        assert evaluate_condition(
            _condition(
                "entity_component",
                {
                    "entity_id": "player_1",
                    "component_type": "movement",
                    "field_path": "hp",
                    "op": "gte",
                    "value": 3,
                },
            ),
            _view(player_components=self._components()),
            [],
            tick=7,
            registry=_registry(),
        ) is True

    def test_value_mismatch_miss(self) -> None:
        assert evaluate_condition(
            _condition(
                "entity_component",
                {
                    "entity_id": "player_1",
                    "component_type": "movement",
                    "field_path": "position.x",
                    "op": "eq",
                    "value": 99,
                },
            ),
            _view(player_components=self._components()),
            [],
            tick=7,
            registry=_registry(),
        ) is False

    def test_missing_entity_miss(self) -> None:
        assert evaluate_condition(
            _condition(
                "entity_component",
                {
                    "entity_id": "ghost",
                    "component_type": "movement",
                    "field_path": "hp",
                    "op": "eq",
                    "value": 1,
                },
            ),
            _view(player_components=self._components()),
            [],
            tick=7,
            registry=_registry(),
        ) is False

    def test_missing_component_miss(self) -> None:
        assert evaluate_condition(
            _condition(
                "entity_component",
                {
                    "entity_id": "player_1",
                    "component_type": "inventory",
                    "field_path": "hp",
                    "op": "eq",
                    "value": 1,
                },
            ),
            _view(player_components=self._components()),
            [],
            tick=7,
            registry=_registry(),
        ) is False

    def test_missing_path_part_miss(self) -> None:
        assert evaluate_condition(
            _condition(
                "entity_component",
                {
                    "entity_id": "player_1",
                    "component_type": "movement",
                    "field_path": "position.z",
                    "op": "eq",
                    "value": 1,
                },
            ),
            _view(player_components=self._components()),
            [],
            tick=7,
            registry=_registry(),
        ) is False


class TestBuiltinTime:
    def test_gte_hit_at_boundary_tick(self) -> None:
        assert evaluate_condition(
            _condition("time", {"tick": 12, "op": "gte"}),
            _view(),
            [],
            tick=12,
            registry=_registry(),
        ) is True

    def test_lt_miss_at_boundary_tick(self) -> None:
        assert evaluate_condition(
            _condition("time", {"tick": 12, "op": "lt"}),
            _view(),
            [],
            tick=12,
            registry=_registry(),
        ) is False

    def test_explicit_eq(self) -> None:
        assert evaluate_condition(
            _condition("time", {"tick": 12, "op": "eq"}),
            _view(),
            [],
            tick=13,
            registry=_registry(),
        ) is False
        assert evaluate_condition(
            _condition("time", {"tick": 12, "op": "eq"}),
            _view(),
            [],
            tick=12,
            registry=_registry(),
        ) is True

    def test_default_op_is_gte(self) -> None:
        assert evaluate_condition(
            _condition("time", {"tick": 12}),
            _view(),
            [],
            tick=11,
            registry=_registry(),
        ) is False
        assert evaluate_condition(
            _condition("time", {"tick": 12}),
            _view(),
            [],
            tick=12,
            registry=_registry(),
        ) is True


# --------------------------------------------------------------------------- #
# 错误语义：静态参数非法 = SchedulerError；动态缺失 = miss
# --------------------------------------------------------------------------- #


class TestStaticParameterErrors:
    def test_missing_event_type_param(self) -> None:
        with pytest.raises(SchedulerError):
            evaluate_condition(
                _condition("event_type"), _view(), [], tick=7, registry=_registry()
            )

    def test_missing_world_variable_key(self) -> None:
        with pytest.raises(SchedulerError):
            evaluate_condition(
                _condition(
                    "world_variable", {"op": "gt", "value": 1}
                ),
                _view(variables={"flag": 2}),
                [],
                tick=7,
                registry=_registry(),
            )

    def test_missing_entity_id_param(self) -> None:
        with pytest.raises(SchedulerError):
            evaluate_condition(
                _condition(
                    "entity_component",
                    {
                        "component_type": "movement",
                        "field_path": "hp",
                        "op": "eq",
                        "value": 1,
                    },
                ),
                _view(),
                [],
                tick=7,
                registry=_registry(),
            )

    def test_missing_time_tick_param(self) -> None:
        with pytest.raises(SchedulerError):
            evaluate_condition(
                _condition("time"), _view(), [], tick=7, registry=_registry()
            )

    def test_time_tick_bool_rejected(self) -> None:
        with pytest.raises(SchedulerError):
            evaluate_condition(
                _condition("time", {"tick": True}),  # type: ignore[dict-item]
                _view(),
                [],
                tick=7,
                registry=_registry(),
            )

    @pytest.mark.parametrize("kind", ["world_variable", "entity_component", "time"])
    def test_unknown_op_rejected(self, kind: str) -> None:
        params: dict[str, Any] = {"op": "foobar"}
        if kind == "world_variable":
            params.update({"key": "flag", "value": 1})
            view = _view(variables={"flag": 1})
        elif kind == "entity_component":
            # 视图须含 movement 组件使路径走通、抵达 op 校验
            params.update(
                {
                    "entity_id": "player_1",
                    "component_type": "movement",
                    "field_path": "hp",
                    "value": 1,
                }
            )
            view = _view(player_components={ComponentTypeId("movement"): {"hp": 3}})
        else:
            params["tick"] = 5
            view = _view()
        with pytest.raises(SchedulerError):
            evaluate_condition(
                _condition(kind, params), view, [], tick=7, registry=_registry()
            )

    def test_event_type_param_must_be_str(self) -> None:
        with pytest.raises(SchedulerError):
            evaluate_condition(
                _condition("event_type", {"event_type": 42}),  # type: ignore[dict-item]
                _view(),
                [_event("a")],
                tick=7,
                registry=_registry(),
            )

    def test_ordering_op_on_uncomparable_raises(self) -> None:
        with pytest.raises(SchedulerError):
            evaluate_condition(
                _condition(
                    "world_variable",
                    {"key": "name", "op": "gt", "value": 1},
                ),
                _view(variables={"name": "x"}),
                [],
                tick=7,
                registry=_registry(),
            )

    def test_missing_value_for_ordering_op(self) -> None:
        with pytest.raises(SchedulerError):
            evaluate_condition(
                _condition("world_variable", {"key": "flag", "op": "gt"}),
                _view(variables={"flag": 1}),
                [],
                tick=7,
                registry=_registry(),
            )


# --------------------------------------------------------------------------- #
# UnknownConditionError / 自定义 resolver / 内置优先级
# --------------------------------------------------------------------------- #


class TestUnknownCondition:
    def test_unknown_kind_unregistered_raises(self) -> None:
        with pytest.raises(UnknownConditionError):
            evaluate_condition(
                _condition("moon_phase", {"phase": "full"}),
                _view(),
                [],
                tick=7,
                registry=_registry(),
            )

    def test_error_is_scheduler_error_subclass(self) -> None:
        assert issubclass(UnknownConditionError, SchedulerError)

    def test_error_message_names_kind_and_condition(self) -> None:
        with pytest.raises(UnknownConditionError, match="moon_phase"):
            evaluate_condition(
                _condition("moon_phase", cid="cond_42"),
                _view(),
                [],
                tick=7,
                registry=_registry(),
            )

    def test_registered_custom_resolver_used(self) -> None:
        reg = _registry()
        spy = _SpyResolver(result=True)
        reg.register("moon_phase", spy)
        events = [_event("a"), _event("b")]
        assert (
            evaluate_condition(
                _condition("moon_phase", {"phase": "full"}),
                _view(),
                events,
                tick=9,
                registry=reg,
            )
            is True
        )
        assert spy.calls == [
            {
                "condition_id": "cond_1",
                "tick": 9,
                "n_events": 2,
                "world_revision": 0,
            }
        ]

    def test_builtin_kind_precedes_caller_registry_override(self) -> None:
        reg = _registry()
        reg.register("time", _SpyResolver(result=True))
        # 内置 time 优先：tick=5 < 12 应 miss，而非 spy 的 True
        assert (
            evaluate_condition(
                _condition("time", {"tick": 12}),
                _view(),
                [],
                tick=5,
                registry=reg,
            )
            is False
        )


# --------------------------------------------------------------------------- #
# ConditionResolverRegistry
# --------------------------------------------------------------------------- #


class TestRegistry:
    def test_register_and_resolve_roundtrip(self) -> None:
        reg = _registry()
        spy: ConditionResolver = _SpyResolver()
        reg.register("custom", spy)
        assert reg.resolve("custom") is spy

    def test_resolve_miss_returns_none(self) -> None:
        assert _registry().resolve("custom") is None

    def test_duplicate_register_raises(self) -> None:
        reg = _registry()
        reg.register("custom", _SpyResolver())
        with pytest.raises(SchedulerError):
            reg.register("custom", _SpyResolver())

    def test_builtin_shared_default_register_raises(self) -> None:
        with pytest.raises(SchedulerError):
            BUILTIN_CONDITION_RESOLVERS.register("custom", _SpyResolver())

    def test_builtin_kinds_resolvable_on_shared_instance(self) -> None:
        assert BUILTIN_CONDITION_RESOLVERS.resolve("time") is not None
        assert BUILTIN_CONDITION_RESOLVERS.resolve("event_type") is not None

    def test_condition_kinds_frozenset_content(self) -> None:
        assert CONDITION_KINDS == frozenset(
            {"event_type", "world_variable", "entity_component", "time"}
        )

    def test_custom_resolver_satisfies_protocol_structurally(self) -> None:
        reg = _registry()
        reg.register("x", _SpyResolver())  # 结构满足 ConditionResolver 即合法
        assert reg.resolve("x") is not None


# --------------------------------------------------------------------------- #
# evaluate_boundaries：blocking 规则 / interrupt=False / 注册序 / 排除
# --------------------------------------------------------------------------- #


class TestEvaluateBoundaries:
    def test_no_boundaries_empty_report(self) -> None:
        runtime = RuntimeState(logical_tick=12)
        report = evaluate_boundaries(
            _view(),
            runtime,
            tick=12,
            events=[],
            boundaries=[],
            registry=_registry(),
            player_actor_ids=frozenset({_PLAYER}),
        )
        assert report.fired == []
        assert report.player_blocking is False
        assert report.npc_notices == []

    def test_player_blocking_hit_sets_flag(self) -> None:
        runtime = RuntimeState(
            logical_tick=12,
            active_actions={
                ActionInstanceId("a1"): _active("a1", _PLAYER),
            },
        )
        report = evaluate_boundaries(
            _view(),
            runtime,
            tick=12,
            events=[_event("hit")],
            boundaries=[
                _boundary(
                    "condition",
                    blocking=True,
                    condition=_condition("event_type", {"event_type": "hit"}),
                )
            ],
            registry=_registry(),
            player_actor_ids=frozenset({_PLAYER}),
        )
        assert report.player_blocking is True
        assert report.npc_notices == []
        assert report.fired == [("bnd_1", [ActionInstanceId("a1")])]

    def test_npc_blocking_hit_is_notice_not_pause(self) -> None:
        runtime = RuntimeState(
            logical_tick=12,
            active_actions={
                ActionInstanceId("a1"): _active("a1", _NPC),
            },
        )
        report = evaluate_boundaries(
            _view(),
            runtime,
            tick=12,
            events=[_event("hit")],
            boundaries=[
                _boundary(
                    "condition",
                    actor=_NPC,
                    blocking=True,
                    condition=_condition("event_type", {"event_type": "hit"}),
                )
            ],
            registry=_registry(),
            player_actor_ids=frozenset({_PLAYER}),
        )
        assert report.player_blocking is False
        assert report.npc_notices == [("bnd_1", _NPC)]
        assert report.fired == [("bnd_1", [ActionInstanceId("a1")])]

    def test_nonblocking_player_hit_is_notice(self) -> None:
        runtime = RuntimeState(
            logical_tick=12,
            active_actions={
                ActionInstanceId("a1"): _active("a1", _PLAYER),
            },
        )
        report = evaluate_boundaries(
            _view(),
            runtime,
            tick=12,
            events=[_event("hit")],
            boundaries=[
                _boundary(
                    "condition",
                    blocking=False,
                    condition=_condition("event_type", {"event_type": "hit"}),
                )
            ],
            registry=_registry(),
            player_actor_ids=frozenset({_PLAYER}),
        )
        assert report.player_blocking is False
        assert report.npc_notices == [("bnd_1", _PLAYER)]
        assert report.fired == [("bnd_1", [ActionInstanceId("a1")])]

    def test_interrupt_false_fires_with_empty_instances(self) -> None:
        runtime = RuntimeState(
            logical_tick=12,
            active_actions={
                ActionInstanceId("a1"): _active("a1", _NPC),
            },
        )
        report = evaluate_boundaries(
            _view(),
            runtime,
            tick=12,
            events=[_event("hit")],
            boundaries=[
                _boundary(
                    "condition",
                    actor=_NPC,
                    blocking=True,
                    interrupt=False,
                    condition=_condition("event_type", {"event_type": "hit"}),
                )
            ],
            registry=_registry(),
            player_actor_ids=frozenset({_PLAYER}),
        )
        assert report.npc_notices == [("bnd_1", _NPC)]
        assert report.fired == [("bnd_1", [])]

    def test_scheduled_due_tick_not_reached_not_fired(self) -> None:
        report = evaluate_boundaries(
            _view(),
            RuntimeState(logical_tick=10),
            tick=10,
            events=[],
            boundaries=[_boundary("scheduled", actor=_NPC, due_tick=12)],
            registry=_registry(),
            player_actor_ids=frozenset({_PLAYER}),
        )
        assert report.fired == []

    def test_scheduled_due_tick_reached_fired(self) -> None:
        runtime = RuntimeState(
            logical_tick=12,
            active_actions={
                ActionInstanceId("a1"): _active("a1", _NPC),
            },
        )
        report = evaluate_boundaries(
            _view(),
            runtime,
            tick=12,
            events=[],
            boundaries=[_boundary("scheduled", actor=_NPC, due_tick=12)],
            registry=_registry(),
            player_actor_ids=frozenset({_PLAYER}),
        )
        assert report.fired == [("bnd_1", [ActionInstanceId("a1")])]
        assert report.npc_notices == [("bnd_1", _NPC)]

    def test_registration_order_stability(self) -> None:
        runtime = RuntimeState(
            logical_tick=12,
            active_actions={
                ActionInstanceId("a1"): _active("a1", _NPC),
            },
        )
        boundaries = [
            _boundary(
                "condition",
                actor=_NPC,
                blocking=True,
                condition=_condition("event_type", {"event_type": "hit"}, cid="c1"),
                bid="b2",
            ),
            _boundary(
                "condition",
                actor=_NPC,
                blocking=True,
                condition=_condition("event_type", {"event_type": "hit"}, cid="c2"),
                bid="b1",
            ),
        ]
        report = evaluate_boundaries(
            _view(),
            runtime,
            tick=12,
            events=[_event("hit")],
            boundaries=boundaries,
            registry=_registry(),
            player_actor_ids=frozenset({_PLAYER}),
        )
        assert [bid for bid, _ in report.fired] == ["b2", "b1"]
        assert [bid for bid, _ in report.npc_notices] == ["b2", "b1"]

    def test_non_active_instance_excluded(self) -> None:
        runtime = RuntimeState(
            logical_tick=12,
            active_actions={
                ActionInstanceId("a1"): _active(
                    "a1", _NPC, status=ActionLifecycleStatus.INTERRUPTED
                ),
            },
        )
        report = evaluate_boundaries(
            _view(),
            runtime,
            tick=12,
            events=[_event("hit")],
            boundaries=[
                _boundary(
                    "condition",
                    actor=_NPC,
                    blocking=True,
                    condition=_condition("event_type", {"event_type": "hit"}),
                )
            ],
            registry=_registry(),
            player_actor_ids=frozenset({_PLAYER}),
        )
        assert report.fired == [("bnd_1", [])]

    def test_non_interruptible_instance_excluded(self) -> None:
        runtime = RuntimeState(
            logical_tick=12,
            active_actions={
                ActionInstanceId("a1"): _active("a1", _NPC, interruptible=False),
            },
        )
        report = evaluate_boundaries(
            _view(),
            runtime,
            tick=12,
            events=[_event("hit")],
            boundaries=[
                _boundary(
                    "condition",
                    actor=_NPC,
                    blocking=True,
                    condition=_condition("event_type", {"event_type": "hit"}),
                )
            ],
            registry=_registry(),
            player_actor_ids=frozenset({_PLAYER}),
        )
        assert report.fired == [("bnd_1", [])]

    def test_pure_does_not_mutate_runtime(self) -> None:
        action = _active("a1", _NPC)
        runtime = RuntimeState(
            logical_tick=12,
            active_actions={ActionInstanceId("a1"): action},
        )
        before = {
            "tick": runtime.logical_tick,
            "status": action.status,
            "actions": runtime.active_actions,
        }
        evaluate_boundaries(
            _view(),
            runtime,
            tick=12,
            events=[_event("hit")],
            boundaries=[
                _boundary(
                    "condition",
                    actor=_NPC,
                    blocking=True,
                    condition=_condition("event_type", {"event_type": "hit"}),
                )
            ],
            registry=_registry(),
            player_actor_ids=frozenset({_PLAYER}),
        )
        assert runtime.logical_tick == before["tick"]
        assert runtime.active_actions is before["actions"]
        assert runtime.active_actions[ActionInstanceId("a1")].status is before[
            "status"
        ]

    def test_report_tick_is_input_tick(self) -> None:
        report = evaluate_boundaries(
            _view(),
            RuntimeState(logical_tick=12),
            tick=37,
            events=[],
            boundaries=[_boundary("scheduled", actor=_NPC, due_tick=37)],
            registry=_registry(),
            player_actor_ids=frozenset({_PLAYER}),
        )
        assert report.tick == 37
