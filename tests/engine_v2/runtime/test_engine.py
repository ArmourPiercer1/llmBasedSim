"""engine_v2 runtime T2 engine 测试（contract §2 Gate 1–4 + 观察面）。

纪律（runtime_closure_contract §0）：只测 ``runtime/engine.py``；测试内
直构最小 WorldInstance（13 字段全必填；engine 不消费的字段取最小面——
``ir=None`` / ``spaces=SpaceRegistry({})`` / ``dynamics=()``，
component_registry / producer_registry / authority_policy 用最小真实
对象）；**注入自建 context_builder**（测试内直接构造 core
``ActorDecisionContext``，13 字段——T4 并行开发中，缺省 lazy import
路径不在此测）；stub executor / policy / dynamics backend = 测试内对象
（不构造 ProjectIR）。

Gate 覆盖：

1. ``submit_action`` 未注册 action → ok=False + diagnostics 非空
   （无异常、无静默）；
2. 注册 action + 自定义 executor 产 ``core.set_component`` effect
   （authority 显式 ALLOW）→ 组件改变 + world_revision+1 +
   StepResult 可查 Transaction COMMITTED；
3. ``advance(1)``：wake → stub policy 提案 → executor → commit
   （状态改变可观察）+ logical_tick+1 + actor_wakeups 清空；
4. 无 grant producer 的 effect 被 authority 拒绝（closed-by-default）
   → 世界不变 + 诊断可观察。
"""

from __future__ import annotations

from collections.abc import Mapping

from src.engine_v2.core.action_registry import ActionRegistry, ActionSpec
from src.engine_v2.core.actions import ActionProposal, ActionTypeId
from src.engine_v2.core.authority import (
    AuthorityPolicy,
    AuthorityRule,
    AuthoritySelector,
    ProducerInfo,
    ProducerRegistry,
)
from src.engine_v2.core.components import (
    ComponentRegistry,
    ComponentSchema,
    ComponentTypeId,
)
from src.engine_v2.core.context_provider import ActorDecisionContext
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.effects import EffectTypeId, EntityTarget, ProposedEffect
from src.engine_v2.core.ids import (
    EffectId,
    EntityId,
    ProducerId,
    new_action_instance_id,
)
from src.engine_v2.core.provenance import CauseKind, CauseRef, OriginKind, Provenance
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.space import SpaceRegistry
from src.engine_v2.core.state import RuntimeState, WorldState
from src.engine_v2.core.transaction import TransactionStatus
from src.engine_v2.dynamics.backend import (
    BackendMetadata,
    new_deterministic_effect_id,
)
from src.engine_v2.modules.actions import ExecutorResult
from src.engine_v2.runtime.engine import EngineInstance, StepResult
from src.engine_v2.runtime.world_instance import WorldInstance

# ── 测试侧常量（确定性）──

_ACTOR = EntityId("ent_authoring_alice")
_COMPONENT = ComponentTypeId("test.status")
_PRODUCER = ProducerId("test.giver")
_ROGUE_PRODUCER = ProducerId("test.rogue")
_ACTION = "test.give"
_SET_COMPONENT = EffectTypeId("core.set_component")


# ── 最小真实对象（core 构造面）──


def _make_world() -> WorldState:
    return WorldState(
        entities={
            _ACTOR: EntityRecord(
                entity_id=_ACTOR, entity_class="npc", tags=["actor"],
            ),
        },
    )


def _make_component_registry() -> ComponentRegistry:
    registry = ComponentRegistry()
    registry.register(ComponentSchema(component_type=_COMPONENT))
    return registry


def _make_producer_registry() -> ProducerRegistry:
    registry = ProducerRegistry()
    registry.register(
        ProducerInfo(producer_id=_PRODUCER, origin=OriginKind.SYSTEM, priority=100)
    )
    registry.register(
        ProducerInfo(
            producer_id=_ROGUE_PRODUCER, origin=OriginKind.SYSTEM, priority=100
        )
    )
    return registry


def _make_authority_policy() -> AuthorityPolicy:
    """closed-by-default + 单规则显式 ALLOW（Gate 2/4 授权面）。"""
    return AuthorityPolicy(
        rules=[
            AuthorityRule(
                selector=AuthoritySelector(component_type=_COMPONENT),
                allowed_writers=[_PRODUCER],
                priority=100,
                rule_id="test.allow_status",
            ),
        ],
    )


def _make_action_registry() -> ActionRegistry:
    typed = ActionTypeId(_ACTION)
    return ActionRegistry(specs={typed: ActionSpec(action_id=typed, executor="test.giver")})


# ── 测试内 stub（executor / policy / context_builder / dynamics）──


class GiveExecutor:
    """测试侧 stub 执行器（K2 纯函数：产 core.set_component，零直写）。"""

    def __init__(self, producer: ProducerId = _PRODUCER) -> None:
        self._producer = producer
        self.calls: list[tuple[ActionProposal, int]] = []

    def execute(
        self, proposal: ActionProposal, world: WorldState, tick: int
    ) -> ExecutorResult:
        self.calls.append((proposal, tick))
        effect = ProposedEffect(
            effect_id=EffectId(f"eff_give_{proposal.proposal_id}"),
            effect_type=_SET_COMPONENT,
            source=self._producer,
            target=EntityTarget(
                entity_id=proposal.actor_id, component_type=_COMPONENT,
            ),
            payload={"value": proposal.arguments.get("value", 1)},
            base_revision=world.world_revision,
            cause_ids=[
                CauseRef(kind=CauseKind.PROPOSAL, ref_id=str(proposal.proposal_id)),
            ],
        )
        return ExecutorResult((effect,), None, 0)


class GivePolicy:
    """测试侧 stub BehaviorPolicy（decide 同步单参；提案 actor 恒 = context）。"""

    def __init__(self, action_id: str = _ACTION, value: object = 7) -> None:
        self._action_id = action_id
        self._value = value
        self.contexts: list[ActorDecisionContext] = []

    def decide(self, context: ActorDecisionContext) -> ActionProposal | None:
        self.contexts.append(context)
        return ActionProposal(
            proposal_id=new_action_instance_id(),
            actor_id=context.actor_id,
            action_id=ActionTypeId(self._action_id),
            arguments={"value": self._value},
            base_world_revision=context.base_world_revision,
            provenance=Provenance(
                producer_id=ProducerId("policy.stub"), origin=OriginKind.BEHAVIOR_POLICY
            ),
        )


def _build_context(
    instance: WorldInstance, actor_id: EntityId
) -> ActorDecisionContext:
    """注入式 context_builder（测试内直构 13 字段 frozen dataclass）。"""
    view = instance.world.entity_view(actor_id)
    assert view is not None, "测试 actor 必须存在于世界"
    return ActorDecisionContext(
        actor_id=actor_id,
        tick=instance.runtime.logical_tick,
        base_world_revision=instance.world.world_revision,
        wake_reason="test_wake",
        self_view=view,
        visible_entities=frozenset({actor_id}),
        local_entity_views={},
        global_entity_views=None,
        observations=(),
        knowledge=None,
        memory=(),
        candidate_actions=(),
        granted_capabilities=frozenset(),
    )


class StubDynamics:
    """测试侧 stub WorldDynamicsBackend（协议鸭子；产单条 core.set_component）。"""

    def __init__(self, producer: ProducerId = _PRODUCER, value: object = 3) -> None:
        self._producer = producer
        self._value = value
        self.base_revisions: list[int] = []

    def metadata(self) -> BackendMetadata:
        return BackendMetadata(
            backend_id="stub.dynamics",
            producer_id=str(self._producer),
            domains=(str(_COMPONENT),),
            determinism="deterministic",
            implementation_type="rule",
            fidelity="abstract",
            checkpointable=False,
            restorable=False,
            replayable=False,
        )

    def simulate(self, snap, stimuli: Mapping, context) -> tuple[ProposedEffect, ...]:
        self.base_revisions.append(int(context.base_revision))
        effect = ProposedEffect(
            effect_id=new_deterministic_effect_id(
                "stub", str(snap.world_instance_id),
                str(snap.world_revision), str(snap.logical_tick),
            ),
            effect_type=_SET_COMPONENT,
            source=self._producer,
            target=EntityTarget(entity_id=_ACTOR, component_type=_COMPONENT),
            payload={"value": self._value},
            base_revision=Revision(int(context.base_revision)),
        )
        return (effect,)

    @property
    def diagnostics(self) -> tuple:
        return ()


class _NullTraceSink:
    """最小 trace sink 占位（T8 并行开发；engine 本波零 trace 调用）。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def record(self, *args: object, **kwargs: object) -> None:
        self.calls.append("record")

    def store_artifact(self, *args: object, **kwargs: object) -> None:
        self.calls.append("store_artifact")

    def record_diagnostic(self, *args: object, **kwargs: object) -> None:
        self.calls.append("record_diagnostic")


def _make_instance(
    *,
    world: WorldState | None = None,
    runtime: RuntimeState | None = None,
    spaces=None,
    action_registry: ActionRegistry | None = None,
    executors: dict | None = None,
    policies: dict | None = None,
    dynamics: tuple = (),
    component_registry: ComponentRegistry | None = None,
    producer_registry: ProducerRegistry | None = None,
    authority_policy: AuthorityPolicy | None = None,
) -> WorldInstance:
    """最小 WorldInstance 直构（engine 不消费 ir → None；其余最小面）。"""
    return WorldInstance(
        world_instance_id="t2_test_instance",
        ir=None,  # engine 零消费（contract §2：只消费 world/runtime/依赖闭包）
        world=world if world is not None else _make_world(),
        runtime=runtime if runtime is not None else RuntimeState(),
        spaces=spaces if spaces is not None else SpaceRegistry({}),
        action_registry=(
            action_registry if action_registry is not None else _make_action_registry()
        ),
        executors=executors if executors is not None else {_ACTION: GiveExecutor()},
        policies=policies if policies is not None else {},
        dynamics=tuple(dynamics),
        component_registry=(
            component_registry
            if component_registry is not None
            else _make_component_registry()
        ),
        producer_registry=(
            producer_registry
            if producer_registry is not None
            else _make_producer_registry()
        ),
        authority_policy=(
            authority_policy if authority_policy is not None else _make_authority_policy()
        ),
        trace_sink=_NullTraceSink(),
    )


# ═══════════════════════════ Gate 1 ═══════════════════════════


def test_gate1_submit_action_unregistered_explicit_diagnostic() -> None:
    engine = EngineInstance(_make_instance(), context_builder=_build_context)
    result = engine.submit_action(str(_ACTOR), "nope.missing", {})
    assert isinstance(result, StepResult)
    assert result.ok is False
    assert result.diagnostics == ("unknown_action:nope.missing",)
    assert result.transactions == ()
    assert engine.instance.world.world_revision == Revision(0)
    assert engine.instance.world.component_view(_ACTOR, _COMPONENT) is None


# ═══════════════════════════ Gate 2 ═══════════════════════════


def test_gate2_submit_action_committed_component_change_and_transaction() -> None:
    engine = EngineInstance(_make_instance(), context_builder=_build_context)
    before = engine.instance.world.world_revision
    result = engine.submit_action(str(_ACTOR), _ACTION, {"value": 42})
    # ok + 无诊断 + world_revision 恰 +1
    assert result.ok is True
    assert result.diagnostics == ()
    assert result.world_revision == before.next()
    assert engine.instance.world.world_revision == before.next()
    # 世界组件改变可观察
    view = engine.instance.world.component_view(_ACTOR, _COMPONENT)
    assert view is not None
    assert dict(view) == {"value": 42}
    # StepResult 可查 Transaction COMMITTED
    committed = [t for t in result.transactions if t.status is TransactionStatus.COMMITTED]
    assert len(committed) == 1
    assert committed[0].base_revision == before
    assert committed[0].commit_revision == before.next()
    assert len(committed[0].effects) == 1


# ═══════════════════════════ Gate 3 ═══════════════════════════


def test_gate3_advance_wakeup_policy_executor_commit_tick_and_cleared() -> None:
    policy = GivePolicy()
    executor = GiveExecutor()
    engine = EngineInstance(
        _make_instance(policies={str(_ACTOR): policy}, executors={_ACTION: executor}),
        context_builder=_build_context,
    )
    engine.wake(str(_ACTOR), reason="test")
    result = engine.advance(1)
    # 干净操作 + 状态改变可观察
    assert result.ok is True
    assert result.diagnostics == ()
    assert engine.instance.world.world_revision == Revision(1)
    view = engine.instance.world.component_view(_ACTOR, _COMPONENT)
    assert view is not None
    assert dict(view) == {"value": 7}
    # logical_tick+1 + actor_wakeups 清空
    assert engine.instance.runtime.logical_tick == 1
    assert engine.instance.runtime.actor_wakeups == []
    # 相位锚：context / executor 均取本刻（0）——相位 5 时钟推进在体后
    assert len(policy.contexts) == 1
    assert policy.contexts[0].tick == 0
    assert policy.contexts[0].base_world_revision == Revision(0)
    assert len(executor.calls) == 1
    assert executor.calls[0][1] == 0
    # advance 聚合面：COMMITTED 事务承接
    committed = [t for t in result.transactions if t.status is TransactionStatus.COMMITTED]
    assert len(committed) == 1


# ═══════════════════════════ Gate 4 ═══════════════════════════


def test_gate4_ungranted_producer_authority_denied_world_unchanged() -> None:
    engine = EngineInstance(
        _make_instance(executors={_ACTION: GiveExecutor(producer=_ROGUE_PRODUCER)}),
        context_builder=_build_context,
    )
    result = engine.submit_action(str(_ACTOR), _ACTION, {"value": 1})
    # 世界不变 + revision 不消耗 + 诊断可观察（不静默）
    assert result.ok is False
    assert any(d.startswith("authority_denied:") for d in result.diagnostics)
    assert engine.instance.world.world_revision == Revision(0)
    assert engine.instance.world.component_view(_ACTOR, _COMPONENT) is None
    # authority deny = 效果被过滤 → 空回合零事务（不消耗 revision）
    assert result.transactions == ()


# ═══════════════════════════ 相位与观察面补充 ═══════════════════════════


def test_advance_no_work_only_tick_advances() -> None:
    engine = EngineInstance(_make_instance(), context_builder=_build_context)
    result = engine.advance(1)
    assert result.ok is True
    assert result.diagnostics == ()
    assert result.transactions == ()
    assert engine.instance.runtime.logical_tick == 1
    assert engine.instance.world.world_revision == Revision(0)


def test_wake_future_due_tick_processed_at_due_tick() -> None:
    engine = EngineInstance(
        _make_instance(
            policies={str(_ACTOR): GivePolicy()}, executors={_ACTION: GiveExecutor()}
        ),
        context_builder=_build_context,
    )
    engine.wake(str(_ACTOR), due_tick=1)
    # 第 1 刻（体在 tick 0）：due_tick=1 未到期 → 仅时钟推进
    r1 = engine.advance(1)
    assert r1.ok is True
    assert engine.instance.runtime.logical_tick == 1
    assert engine.instance.world.world_revision == Revision(0)
    assert len(engine.instance.runtime.actor_wakeups) == 1
    # 第 2 刻（体在 tick 1）：到期 → 决策 + 提交
    r2 = engine.advance(1)
    assert r2.ok is True
    assert engine.instance.world.world_revision == Revision(1)
    assert engine.instance.runtime.logical_tick == 2
    assert engine.instance.runtime.actor_wakeups == []


def test_wake_without_policy_diagnostic_and_consumed() -> None:
    engine = EngineInstance(_make_instance(), context_builder=_build_context)
    engine.wake(str(_ACTOR))
    result = engine.advance(1)
    assert result.ok is False
    assert result.diagnostics == (f"no_policy:{_ACTOR}",)
    assert engine.instance.runtime.actor_wakeups == []
    assert engine.instance.world.world_revision == Revision(0)


def test_wake_policy_returns_none_is_legal_noop() -> None:
    class QuietPolicy:
        def decide(self, context):
            return None

    engine = EngineInstance(
        _make_instance(policies={str(_ACTOR): QuietPolicy()}),
        context_builder=_build_context,
    )
    engine.wake(str(_ACTOR))
    result = engine.advance(1)
    assert result.ok is True
    assert engine.instance.world.world_revision == Revision(0)
    assert engine.instance.runtime.logical_tick == 1


def test_dynamics_phase_commit_via_same_pipeline() -> None:
    backend = StubDynamics()
    engine = EngineInstance(
        _make_instance(dynamics=(backend,)), context_builder=_build_context
    )
    result = engine.advance(1)
    assert result.ok is True
    assert engine.instance.world.world_revision == Revision(1)
    view = engine.instance.world.component_view(_ACTOR, _COMPONENT)
    assert view is not None
    assert dict(view) == {"value": 3}
    # backend 消费面：base_revision = simulate 时刻世界 revision
    assert backend.base_revisions == [0]


def test_dynamics_failure_diagnostic_not_silent() -> None:
    class ExplodingDynamics:
        def metadata(self) -> BackendMetadata:
            return StubDynamics().metadata()

        def simulate(self, snap, stimuli, context):
            raise RuntimeError("boom")

        @property
        def diagnostics(self) -> tuple:
            return ()

    engine = EngineInstance(
        _make_instance(dynamics=(ExplodingDynamics(),)),
        context_builder=_build_context,
    )
    result = engine.advance(1)
    assert result.ok is False
    assert result.diagnostics[0].startswith("dynamics_failed:stub.dynamics:RuntimeError")
    assert engine.instance.world.world_revision == Revision(0)
    assert engine.instance.runtime.logical_tick == 1


def test_submit_proposal_pipeline() -> None:
    proposal = ActionProposal(
        proposal_id=new_action_instance_id(),
        actor_id=_ACTOR,
        action_id=ActionTypeId(_ACTION),
        arguments={"value": 9},
        base_world_revision=Revision(0),
        provenance=Provenance(
            producer_id=ProducerId("player"), origin=OriginKind.DEVELOPER
        ),
    )
    engine = EngineInstance(_make_instance(), context_builder=_build_context)
    result = engine.submit_proposal(proposal)
    assert result.ok is True
    assert result.world_revision == Revision(1)
    view = engine.instance.world.component_view(_ACTOR, _COMPONENT)
    assert view is not None
    assert dict(view) == {"value": 9}


def test_submit_proposal_unknown_action_diagnostic() -> None:
    proposal = ActionProposal(
        proposal_id=new_action_instance_id(),
        actor_id=_ACTOR,
        action_id=ActionTypeId("nope.missing"),
        arguments={},
        base_world_revision=Revision(0),
        provenance=Provenance(
            producer_id=ProducerId("player"), origin=OriginKind.DEVELOPER
        ),
    )
    engine = EngineInstance(_make_instance(), context_builder=_build_context)
    result = engine.submit_proposal(proposal)
    assert result.ok is False
    assert result.diagnostics == ("unknown_action:nope.missing",)


def test_view_reflects_revision_and_actors() -> None:
    engine = EngineInstance(_make_instance(), context_builder=_build_context)
    scene = engine.view()
    assert scene["view_revision"] == 0
    assert scene["tick"] == 0
    engine.submit_action(str(_ACTOR), _ACTION, {"value": 1})
    scene2 = engine.view()
    assert scene2["view_revision"] == 1
    assert [a["id"] for a in scene2["actors"]] == [str(_ACTOR)]
