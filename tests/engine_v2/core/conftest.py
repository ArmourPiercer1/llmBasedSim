"""P3-T08 共享 fixture（设计文档 §5.1 前置设定工厂；Gate/对抗两文件共用）。

依据 ``docs/v2/contracts/P3-scheduler-time-action-design.md``：

- §5.1 前置设定（fixture，全场景共用）：``ent_player``（movement.position
  {x:0,y:0}）/ ``ent_dest``（{x:30,y:0}）/ 世界 R0；travel 注册表（hint×1.0，
  completion_trigger="movement.arrival"）；两个点名触发器 stub——
  ``scenario.encounter_12`` → create_entity(ent_bandit)、``movement.arrival`` →
  set_component(ent_player, movement, position=dest)——**幂等状态守卫**
  （R4/E-P3-24：重求值时查 guard 视图，目标已生效 → 返回空 effect 列表）；
  condition 型 B1 边界（C1: event_type=core.create_entity，blocking，
  interrupt，§5.1 逐字口径——任务简报"scheduled due_tick=12"与 §5.2 S7
  "C1 命中"表述冲突，以文档为准）；closed-by-default 授权策略（D-P3-23）；
  空 ``CascadeTriggerRegistry``（Gate 单路化，D-P3-27/E-P3-30）；run()-级
  origin = Provenance(producer_id=origin_scenario, origin=SCENARIO)
  （E-P3-34/E-P3-40）；初始队列 [ev_enc@12]；P1 提案工厂。
- "注册时声明"的 producer 载体 = stub ``evaluate`` 产出 effect 时写入
  ``ProposedEffect.source``（effects.py:219 必填 ProducerId；P2 注册表 API
  无 producer 存储位，L3-01）。
- 授权规则 2 以 ``component_type=ComponentTypeId("movement")`` 落位：
  文档 §5.1 "movement.position" 为速记——set_component 载荷是 movement
  组件整体替换（reducer.py 语义），authority 匹配维 ``component_type`` 与
  ``target.component_type`` 全等（authority.py 匹配逻辑），``field`` 维未
  指定即不辖制 field_path。

写屏障纪律（§2.6.2）：本 conftest 为 core/ 目录首个 conftest；autouse 夹具
每用例前后把全局屏障复原为**未武装**态（与 test_scheduler._barrier_isolation
同款口径，不跨文件受染）——需要武装态的用例经本文件的工厂/夹具自行武装
（与 test_scheduler._scheduler builder 先 ``install_write_barrier()`` 再构造
的同款口径）。无全局 monkeypatch。

import 纪律（任务硬规则 4）：本文件不 import datetime/time/random/asyncio/
provider/LLM/网络库；仅直接子模块导入（无星号导入）。
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from src.engine_v2.core.action_registry import (
    ActionRegistry,
    ActionSpec,
    ActionTypeId,
    DurationPolicy,
    ParameterSpec,
)
from src.engine_v2.core.actions import ActionProposal, ActionTiming
from src.engine_v2.core.authority import (
    AuthorityPolicy,
    AuthorityRule,
    AuthoritySelector,
)
from src.engine_v2.core.cascade import CascadeTriggerRegistry, SyncTrigger
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.effects import EntityTarget, ProposedEffect
from src.engine_v2.core.event_queue import (
    enqueue_scheduled_event,
    make_scheduled_event,
)
from src.engine_v2.core.events import DomainEvent
from src.engine_v2.core.ids import (
    ActionInstanceId,
    EffectId,
    EntityId,
    ProducerId,
)
from src.engine_v2.core.interrupt import DecisionBoundary, InterruptCondition
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.reducer import (
    EFFECT_CREATE_ENTITY,
    EFFECT_SET_COMPONENT,
    GuardedWorldState,
    install_write_barrier,
    uninstall_write_barrier,
)
from src.engine_v2.core.revision import INITIAL_WORLD_REVISION
from src.engine_v2.core.scheduler import Scheduler, SchedulerOutcome, TimePolicy
from src.engine_v2.core.state import RuntimeState, WorldState

# —— §5.1 固定常量（Gate fixture 口径）——

#: §5.1 实体（确定性命名 ID；构造点无词法校验，前缀约定 ent_）
ENT_PLAYER = EntityId("ent_player")
ENT_DEST = EntityId("ent_dest")
ENT_BANDIT = EntityId("ent_bandit")
ENT_NPC = EntityId("ent_npc")
#: movement 组件类型（set_component 整体替换该组件数据；position 为组件内字段）
COMP_MOVEMENT = ComponentTypeId("movement")
START_POSITION = {"x": 0, "y": 0}
DEST_POSITION = {"x": 30, "y": 0}
#: run()-级 origin producer（E-P3-34/E-P40 Leader 裁定 (A)；D-P3-11 统一口径）
ORIGIN_SCENARIO = ProducerId("origin_scenario")
ORIGIN_PROVENANCE = Provenance(
    producer_id=ORIGIN_SCENARIO, origin=OriginKind.SCENARIO
)
#: travel 行动类型（§5.1 注册表）
TRAVEL = ActionTypeId("travel")
TRIGGER_ENCOUNTER = "scenario.encounter_12"
TRIGGER_ARRIVAL = "movement.arrival"
#: R0 = INITIAL_WORLD_REVISION（revision.py:70）
R0 = INITIAL_WORLD_REVISION
#: P1 提案 ID = 行动实例 ID（D-3：同一实例 ID 贯穿 ActionProposal → ActiveAction）
P1_INSTANCE_ID = ActionInstanceId("act_p1")


# —— §5.1 工厂（纯函数；无 fixture 依赖，供夹具与对抗变体复用）——


def travel_spec() -> ActionSpec:
    """§5.1 travel 注册表条目（hint 型时长，hint_scale=1.0，duration_hint=30
    → 30 tick；completion_trigger="movement.arrival" 点名）。"""
    return ActionSpec(
        action_id=TRAVEL,
        executor="movement.travel_system",
        parameters={"destination": ParameterSpec(type="entity", required=True)},
        duration_policy=DurationPolicy(kind="hint", hint_scale=1.0),
        interruptible=True,
        completion_trigger=TRIGGER_ARRIVAL,
    )


def make_gate_world() -> WorldState:
    """§5.1 实体/组件：ent_player（movement.position 起点）、ent_dest（坐标
    {x:30,y:0}）；世界 revision R0（INITIAL_WORLD_REVISION）。"""
    return WorldState(
        entities={
            ENT_PLAYER: EntityRecord(
                entity_id=ENT_PLAYER,
                components={COMP_MOVEMENT: {"position": dict(START_POSITION)}},
            ),
            ENT_DEST: EntityRecord(
                entity_id=ENT_DEST,
                components={COMP_MOVEMENT: {"position": dict(DEST_POSITION)}},
            ),
        }
    )


def make_gate_registry() -> ActionRegistry:
    """§5.1 注册表（P5 在此生产，测试直接构造）。"""
    return ActionRegistry(specs={TRAVEL: travel_spec()})


def make_gate_time_policy() -> TimePolicy:
    """§5.1 TimePolicy：checkpoint_interval_ticks=10（cp@10/20/30 口径）。"""
    return TimePolicy(checkpoint_interval_ticks=10)


def make_encounter_stub() -> SyncTrigger:
    """``scenario.encounter_12`` → create_entity(ent_bandit)（§5.1）。

    幂等状态守卫（R4/E-P3-24）：ent_bandit 已在世界 → 返回空 effect 列表、
    不重发；producer = origin_scenario（注册时声明，写入 ProposedEffect.source）。
    ``cause_ids`` 空列表（Gate 单路点名求值无本回合事件可回指；D-P3-27 下
    级联再求值面为空，两种写法均确定，§5.1 通用契约段）。
    """

    def evaluate(
        events: Sequence[DomainEvent], state: GuardedWorldState, depth: int
    ) -> Sequence[ProposedEffect]:
        if state.has_entity(ENT_BANDIT):
            return []
        return [
            ProposedEffect(
                effect_id=EffectId("eff_encounter_001"),
                effect_type=EFFECT_CREATE_ENTITY,
                source=ORIGIN_SCENARIO,
                target=EntityTarget(entity_id=ENT_BANDIT),
                payload={
                    "entity_class": "bandit",
                    "tags": ["enemy"],
                    "components": {},
                },
                base_revision=state.world_revision,
                cause_ids=[],
            )
        ]

    return SyncTrigger(TRIGGER_ENCOUNTER, evaluate)


def make_arrival_stub() -> SyncTrigger:
    """``movement.arrival`` → set_component(ent_player, movement, position=dest)
    （§5.1）。

    幂等状态守卫（R4/E-P3-24）：movement.position 已达 dest → 返回空 effect
    列表、不重发；载荷 = movement 组件**整体数据**（reducer set_component
    语义：wholesale replace）；producer = origin_scenario。
    """

    def evaluate(
        events: Sequence[DomainEvent], state: GuardedWorldState, depth: int
    ) -> Sequence[ProposedEffect]:
        current = state.component_view(ENT_PLAYER, COMP_MOVEMENT)
        if current is not None and current.get("position") == DEST_POSITION:
            return []
        return [
            ProposedEffect(
                effect_id=EffectId("eff_arrival_001"),
                effect_type=EFFECT_SET_COMPONENT,
                source=ORIGIN_SCENARIO,
                target=EntityTarget(
                    entity_id=ENT_PLAYER, component_type=COMP_MOVEMENT
                ),
                payload={"position": dict(DEST_POSITION)},
                base_revision=state.world_revision,
                cause_ids=[],
            )
        ]

    return SyncTrigger(TRIGGER_ARRIVAL, evaluate)


def make_gate_boundary() -> DecisionBoundary:
    """§5.1 B1（逐字口径）：condition 型——C1 命中本刻事件流含
    event_type=core.create_entity 的事件（D-P3-17）→ fired；blocking ∧
    ent_player ∈ player_actor_ids → PAUSE（D-P3-10）；interrupt=True →
    命中行动 ACTIVE→INTERRUPTED（§5.2 S7）。"""
    return DecisionBoundary(
        boundary_id="B1",
        actor_id=ENT_PLAYER,
        kind="condition",
        condition=InterruptCondition(
            condition_id="C1",
            kind="event_type",
            parameters={"event_type": "core.create_entity"},
        ),
        blocking=True,
        interrupt=True,
        reason="encounter",
    )


def make_gate_authority_policy() -> AuthorityPolicy:
    """§5.1 授权策略（closed-by-default，D-P3-23）：仅 origin_scenario 可写
    create_entity 与 movement 组件 set_component 两个 effect 面。

    规则 2 落位说明：文档速记 "movement.position" → 匹配维
    ``component_type=ComponentTypeId("movement")``（set_component 整体替换
    movement 组件；target.component_type 全等匹配，field 维未指定不辖制）。
    """
    return AuthorityPolicy(
        rules=[
            AuthorityRule(
                rule_id="ap_create_entity",
                selector=AuthoritySelector(effect_type=EFFECT_CREATE_ENTITY),
                allowed_writers=[ORIGIN_SCENARIO],
            ),
            AuthorityRule(
                rule_id="ap_set_movement",
                selector=AuthoritySelector(
                    effect_type=EFFECT_SET_COMPONENT,
                    component_type=COMP_MOVEMENT,
                ),
                allowed_writers=[ORIGIN_SCENARIO],
            ),
        ]
    )


def make_gate_scheduler() -> Scheduler:
    """§5.1 Scheduler 装配（Gate 单路化，D-P3-27/E-P3-30）：

    - ``trigger_registry`` = 显式空注册表（级联回合再求值面为空，零重发、
      无 ``trigger_output_dropped``）；
    - ``named_triggers`` = 两 stub（点名求值唯一数据来源，D-P3-26 必填）；
    - run()-级 origin = ORIGIN_PROVENANCE（E-P3-34/E-P3-40）；
    - 写屏障须已武装（F2-06 第一步检查）——本工厂先行武装（test_scheduler
      _scheduler builder 同款口径）。
    """
    install_write_barrier()
    return Scheduler(
        make_gate_registry(),
        authority_policy=make_gate_authority_policy(),
        origin=ORIGIN_PROVENANCE,
        time_policy=make_gate_time_policy(),
        boundaries=[make_gate_boundary()],
        trigger_registry=CascadeTriggerRegistry(),
        named_triggers=frozenset(
            {
                (TRIGGER_ENCOUNTER, make_encounter_stub()),
                (TRIGGER_ARRIVAL, make_arrival_stub()),
            }
        ),
        player_actor_ids=frozenset({ENT_PLAYER}),
        assert_barrier_armed=True,
    )


def make_gate_proposal() -> ActionProposal:
    """§5.2 S1 P1：travel 提案（base_world_revision=R0、
    duration_hint_ticks=30 → resolve_duration = 30、无 valid_until）。"""
    return ActionProposal(
        proposal_id=P1_INSTANCE_ID,
        actor_id=ENT_PLAYER,
        action_id=TRAVEL,
        arguments={"destination": ENT_DEST},
        timing=ActionTiming(duration_hint_ticks=30),
        base_world_revision=R0,
        provenance=ORIGIN_PROVENANCE,
    )


def make_initial_runtime() -> RuntimeState:
    """§5.1 S0 初始队列：[ev_enc@12]（kind="event"，trigger_id 点名形态）。"""
    runtime = RuntimeState()
    runtime = enqueue_scheduled_event(
        runtime,
        make_scheduled_event(
            "event", 12, payload={"trigger_id": TRIGGER_ENCOUNTER}
        ),
    )
    return runtime


def make_gate_state() -> tuple[WorldState, RuntimeState, Scheduler, ActionProposal]:
    """§5.1 S0 完整初始态四元组 ``(world, runtime, scheduler, proposal)``：
    R0 世界 + 初始队列 [ev_enc@12] + Gate 装配调度器 + 未提交的 P1。"""
    return (
        make_gate_world(),
        make_initial_runtime(),
        make_gate_scheduler(),
        make_gate_proposal(),
    )


# —— pytest 夹具（供 test_p3_gate_scenario / test_p3_adversarial 按名请求）——


@pytest.fixture(autouse=True)
def p3_barrier_isolation() -> None:
    """写屏障全局复原（§2.6.2；test_scheduler._barrier_isolation 同款口径）：
    每用例前后复原为未武装态，不跨文件受染。"""
    uninstall_write_barrier()
    yield
    uninstall_write_barrier()


@pytest.fixture
def gate_world() -> WorldState:
    """§5.1 S0 世界（R0）。"""
    return make_gate_world()


@pytest.fixture
def gate_registry() -> ActionRegistry:
    """§5.1 travel 注册表（对抗变体可经 ``specs`` 扩展后重建）。"""
    return make_gate_registry()


@pytest.fixture
def gate_time_policy() -> TimePolicy:
    """§5.1 TimePolicy（checkpoint_interval_ticks=10）。"""
    return make_gate_time_policy()


@pytest.fixture
def gate_boundary() -> DecisionBoundary:
    """§5.1 B1（condition 型，blocking，interrupt）。"""
    return make_gate_boundary()


@pytest.fixture
def gate_authority_policy() -> AuthorityPolicy:
    """§5.1 closed-by-default 显式授予面（origin_scenario × 2 effect 面）。"""
    return make_gate_authority_policy()


@pytest.fixture
def gate_scheduler() -> Scheduler:
    """§5.1 Gate 装配调度器（空注册表 + 两命名 stub + B1 + player={ent_player}）。"""
    return make_gate_scheduler()


@pytest.fixture
def gate_proposal() -> ActionProposal:
    """§5.2 S1 P1 提案（base R0、hint 30、无 valid_until）。"""
    return make_gate_proposal()


@pytest.fixture
def gate_state(
    gate_world: WorldState,
    gate_scheduler: Scheduler,
    gate_proposal: ActionProposal,
) -> tuple[WorldState, RuntimeState, Scheduler, ActionProposal]:
    """§5.1 S0 初始态四元组 ``(world, runtime, scheduler, proposal)``。"""
    return (gate_world, make_initial_runtime(), gate_scheduler, gate_proposal)


def gate_run_to_pause(
    scheduler: Scheduler,
    world: WorldState,
    runtime: RuntimeState,
    proposal: ActionProposal,
) -> tuple[WorldState, RuntimeState, SchedulerOutcome]:
    """§5.2 S1-S8 公共推进：submit_proposal(P1)（ACCEPT，t=0 立即开跑）→
    fast_forward → B1 暂停点。返回 ``(world, runtime, outcome)``。

    供 G3-1 主时序 / G3-2 / G3-3 / G3-4 / A7 等从同一暂停点分叉的用例复用，
    保证各用例起步状态逐字一致（确定性）。
    """
    world, runtime, _decision = scheduler.submit_proposal(world, runtime, proposal)
    world, runtime, outcome = scheduler.fast_forward(world, runtime)
    return world, runtime, outcome


def gate_position(world: WorldState) -> dict[str, object]:
    """M2 观察口：ent_player 的 movement.position 组件数据（world 读，非
    trace 猜测，§5.5 M2 口径）。"""
    component = world.entities[ENT_PLAYER].components[COMP_MOVEMENT]
    return dict(component["position"])  # type: ignore[no-any-return]

# ─────────────────────────── P4 gate 节 ───────────────────────────
# D-P4-16：Gate 只证明 re-propose 流水线机制；BobPolicy 为最小确定性 stub，
# P5 整体替换策略内容。

from src.engine_v2.core.action_lifecycle import progress_of  # noqa: E402, F401
from src.engine_v2.core.behavior_policy import run_policy_decide  # noqa: E402
from src.engine_v2.core.capability import (  # noqa: E402
    DEFAULT_NPC_CAPABILITIES,
    CapabilityGrant,
    CapabilityTable,
)
from src.engine_v2.core.context_provider import (  # noqa: E402
    ActorDecisionContext,
    ContextBuildInput,
    DefaultContextProvider,  # noqa: F401
)
from src.engine_v2.core.gameplay_mode import (  # noqa: E402
    ModeChangeRequest,  # noqa: F401
    ModeChangeResolution,  # noqa: F401
    ModeOperation,  # noqa: F401
    ModeOperationKind,  # noqa: F401
    ModeOverlay,
    ModeOverlayRegistry,
    apply_mode_change,  # noqa: F401
)
from src.engine_v2.core.ids import new_action_instance_id  # noqa: E402
from src.engine_v2.core.knowledge import (  # noqa: E402
    KNOWLEDGE_COMPONENT,  # noqa: F401
    MEMORY_COMPONENT,  # noqa: F401
    OBSERVATIONS_COMPONENT,  # noqa: F401
)
from src.engine_v2.core.scheduler import WakeupHookRegistry  # noqa: E402
from src.engine_v2.core.space import (  # noqa: E402
    GraphSpace,
    GridSpace,
    SpaceMapping,
    SpaceRegistry,
    SpatialDomain,
    decode_spaces,  # noqa: F401
    encode_spaces,
    entity_domain_positions,  # noqa: F401
)

ENT_ALICE = EntityId("ent_alice")
ENT_BOB = EntityId("ent_bob")
ENT_VAULT = EntityId("ent_vault")
COMP_SPACES = ComponentTypeId("spaces")
COMP_LOOT = ComponentTypeId("loot")
COMP_INVENTORY = ComponentTypeId("inventory")
BOB_START_POSITION = {"x": 5, "y": 0}
ORIGIN_SCRIPT_PROVENANCE = Provenance(
    producer_id=ProducerId("origin_script"), origin=OriginKind.SCENARIO
)


def make_p4_world() -> WorldState:
    """S0 世界（R0，构造形态同 conftest.py:125-139）。

    alice/bob 双域映射（overworld + tactical）；alice 无任何认识论组件
    （obs/knowledge/memory 缺席——G4-1 的空上下文即由此而来）；
    dest/vault 无 spaces 映射（A3d unmapped-domain 口径天然覆盖）。
    """
    alice_spaces = encode_spaces((
        SpaceMapping(domain_id="overworld", position=dict(START_POSITION)),
        SpaceMapping(domain_id="tactical", position="t0"),
    ))
    bob_spaces = encode_spaces((
        SpaceMapping(domain_id="overworld", position=dict(BOB_START_POSITION)),
        SpaceMapping(domain_id="tactical", position="t1"),
    ))
    return WorldState(entities={
        ENT_ALICE: EntityRecord(
            entity_id=ENT_ALICE,
            components={
                COMP_MOVEMENT: {"position": dict(START_POSITION)},
                COMP_SPACES: alice_spaces,
            },
        ),
        ENT_BOB: EntityRecord(
            entity_id=ENT_BOB,
            components={
                COMP_MOVEMENT: {"position": dict(BOB_START_POSITION)},
                COMP_SPACES: bob_spaces,
                COMP_INVENTORY: {"items": []},
            },
        ),
        ENT_DEST: EntityRecord(
            entity_id=ENT_DEST,
            components={COMP_MOVEMENT: {"position": dict(DEST_POSITION)}},
        ),
        ENT_VAULT: EntityRecord(
            entity_id=ENT_VAULT,
            components={COMP_LOOT: {"loot": ["gold_cup"]}},
        ),
    })


def make_p4_runtime() -> RuntimeState:
    """P4 S0 运行时：全新 ``RuntimeState``（logical_tick=0），调度队列
    （``scheduler_queue``）、``active_actions``、``actor_wakeups`` 全空
    （state.py:217-222 缺省构造，本工厂零预置条目）。

    与 P3 节 ``make_initial_runtime``（conftest.py:307-316）的差异：后者为
    P3 Gate 专用、预置 ev_enc@12（kind="event"，trigger_id=
    scenario.encounter_12）；P4 Gate 的事件条目（scenario.theft_12@12）
    在 S0 装配处逐字入队（Gate 测试体，形态同 conftest.py:310-315），
    故 P4 工厂只产空队列，两 Gate 的预置面互不混用。
    """
    return RuntimeState()


def make_p4_space_registry() -> SpaceRegistry:
    """双域注册表：overworld = Grid(10×10)；tactical = Graph(t0-t1-t2 链)。"""
    return SpaceRegistry({
        "overworld": (
            SpatialDomain(domain_id="overworld", backend_kind="grid"),
            GridSpace(width=10, height=10),
        ),
        "tactical": (
            SpatialDomain(domain_id="tactical", backend_kind="graph"),
            GraphSpace(nodes=("t0", "t1", "t2"),
                       edges=(("t0", "t1"), ("t1", "t2"))),
        ),
    })


def make_p4_capability_table() -> CapabilityTable:
    """alice/bob 各持 NPC 默认 3 权（Spec:895-899）；action_requirements 空。"""
    grants = tuple(
        CapabilityGrant(actor_id=actor, capability=cap)
        for actor in (ENT_ALICE, ENT_BOB)
        for cap in sorted(DEFAULT_NPC_CAPABILITIES, key=lambda c: c.value)
    )
    return CapabilityTable(grants=grants, action_requirements={})


def p4_theft_stub() -> SyncTrigger:
    """``scenario.theft_12`` → 双 set_component（vault.loot=[] /
    bob.inventory←gold_cup）；签名形态同 conftest.py:161-163。

    幂等状态守卫（E-P3-24 纪律继承，形态同 conftest.py:164-165）：
    bob.inventory 已含 gold_cup → 返回空 effect 列表。
    producer = origin_scenario（注册时声明，写入 ProposedEffect.source，
    conftest.py:156 口径）。
    """

    def evaluate(
        events: Sequence[DomainEvent], state: GuardedWorldState, depth: int
    ) -> Sequence[ProposedEffect]:
        inv = state.component_view(ENT_BOB, COMP_INVENTORY)
        if inv is not None and "gold_cup" in tuple(inv.get("items", ())):
            return []
        return [
            ProposedEffect(
                effect_id=EffectId("eff_theft_vault_001"),
                effect_type=EFFECT_SET_COMPONENT,
                source=ORIGIN_SCENARIO,
                target=EntityTarget(
                    entity_id=ENT_VAULT, component_type=COMP_LOOT
                ),
                payload={"loot": []},
                base_revision=state.world_revision,
                cause_ids=[],
            ),
            ProposedEffect(
                effect_id=EffectId("eff_theft_inv_002"),
                effect_type=EFFECT_SET_COMPONENT,
                source=ORIGIN_SCENARIO,
                target=EntityTarget(
                    entity_id=ENT_BOB, component_type=COMP_INVENTORY
                ),
                payload={"items": ["gold_cup"]},
                base_revision=state.world_revision,
                cause_ids=[],
            ),
        ]

    return SyncTrigger("scenario.theft_12", evaluate)


def p4_arrival_stub() -> SyncTrigger:
    """``movement.arrival`` → set_component(ENT_BOB, movement,
    position=DEST_POSITION)；幂等守卫：bob 已在 DEST_POSITION → 返回 []。

    与 P3 节 make_arrival_stub（conftest.py:185-214，面向 ENT_PLAYER）区分：
    本 stub 面向 ENT_BOB，注册在 P4 独立 Scheduler 实例的 named_triggers 上，
    两节互不干扰。
    """

    def evaluate(
        events: Sequence[DomainEvent], state: GuardedWorldState, depth: int
    ) -> Sequence[ProposedEffect]:
        current = state.component_view(ENT_BOB, COMP_MOVEMENT)
        if current is not None and current.get("position") == DEST_POSITION:
            return []
        return [
            ProposedEffect(
                effect_id=EffectId("eff_arrival_bob_001"),
                effect_type=EFFECT_SET_COMPONENT,
                source=ORIGIN_SCENARIO,
                target=EntityTarget(
                    entity_id=ENT_BOB, component_type=COMP_MOVEMENT
                ),
                payload={"position": dict(DEST_POSITION)},
                base_revision=state.world_revision,
                cause_ids=[],
            )
        ]

    return SyncTrigger(TRIGGER_ARRIVAL, evaluate)


def make_p4_boundary() -> DecisionBoundary:
    """B1（P4 口径）：bob 的**非阻塞** interrupt 边界——本刻事件流含
    event_type=core.set_component 的事件（命中口径 conftest.py:218-221 同款）
    → fired；blocking=False ∧ interrupt=True → 命中行动 ACTIVE→INTERRUPTED
    （scheduler.py:783-790）+ enqueue_actor_wakeup(due_tick=本刻,
    reason="B1")（scheduler.py:791-794）。

    与 P3 节 make_gate_boundary（conftest.py:217-234，blocking=True → PAUSE）
    的差异正是本 Gate 的断言面：P4 走"不暂停"的中断+wakeup 路径。
    """
    return DecisionBoundary(
        boundary_id="B1",
        actor_id=ENT_BOB,
        kind="condition",
        condition=InterruptCondition(
            condition_id="b1_theft",
            kind="event_type",
            parameters={"event_type": "core.set_component"},
        ),
        blocking=False,
        interrupt=True,
        reason="theft",
    )


def make_p4_authority_policy() -> AuthorityPolicy:
    """P4 §5.1 授权策略（closed-by-default，D-P3-23 继承；构造形态
    conftest.py:237-261）：仅 origin_scenario 可 set_component 写
    loot / inventory / movement 三个组件面。"""
    return AuthorityPolicy(rules=[
        AuthorityRule(
            rule_id="ap_set_loot",
            selector=AuthoritySelector(
                effect_type=EFFECT_SET_COMPONENT, component_type=COMP_LOOT
            ),
            allowed_writers=[ORIGIN_SCENARIO],
        ),
        AuthorityRule(
            rule_id="ap_set_inventory",
            selector=AuthoritySelector(
                effect_type=EFFECT_SET_COMPONENT, component_type=COMP_INVENTORY
            ),
            allowed_writers=[ORIGIN_SCENARIO],
        ),
        AuthorityRule(
            rule_id="ap_set_movement",
            selector=AuthoritySelector(
                effect_type=EFFECT_SET_COMPONENT, component_type=COMP_MOVEMENT
            ),
            allowed_writers=[ORIGIN_SCENARIO],
        ),
    ])


class BobPolicy:
    """re-propose 策略 stub（D-P4-16：P4 供缝，内容是最小确定性口径）。

    规则：``wake_reason == "B1"`` ∧ bob 的 movement.position ≠ DEST_POSITION
    → re-propose travel（新提案 ID 走工厂、base = context.base_world_revision）；
    否则 → None（no-op，D-P4-01）。P5 整体替换本类。
    """

    def decide(self, context: ActorDecisionContext):
        if context.wake_reason != "B1":
            return None
        mv = context.self_view.get_component(COMP_MOVEMENT)
        if mv is not None and mv.get("position") == DEST_POSITION:
            return None
        return ActionProposal(
            proposal_id=new_action_instance_id(),
            actor_id=context.actor_id,
            action_id=TRAVEL,
            arguments={"destination": ENT_DEST},
            timing=ActionTiming(duration_hint_ticks=30),
            base_world_revision=context.base_world_revision,
            provenance=Provenance(
                producer_id=ProducerId("bob_policy"),
                origin=OriginKind.BEHAVIOR_POLICY,
            ),
        )


class PassPolicy:
    """分支 B：no-op 策略（D-P4-01 None 口径）——证明"wakeup 但无 re-propose"
    路径：不产新实例、旧实例保持 INTERRUPTED、RESUMED 边仍可复用旧实例。"""

    def decide(self, context: ActorDecisionContext):
        return None


class PolicyWakeupHook:
    """P4 具体 WakeupHook（实现 scheduler.py:316-336 协议）。

    流程：guard 视图 → DefaultContextProvider.build（一次性 context，
    D-P4-04/05）→ run_policy_decide（actor_id 唯一强制，D-P4-03）→
    提案序列（None → 空序列）。实例属性 ``actor_id`` 供
    WakeupHookRegistry.register 读取（scheduler.py:355-367）。
    """

    def __init__(self, actor_id, policy, provider, table, action_registry,
                 space_registry=None):
        self.actor_id = actor_id
        self._policy = policy
        self._provider = provider
        self._table = table
        self._registry = action_registry
        self._space_registry = space_registry

    def on_wakeup(self, actor_id, view, clock, reason):
        ctx = self._provider.build(ContextBuildInput(
            actor_id=actor_id,
            state=view,
            registry=self._registry,
            capability_table=self._table,
            space_registry=self._space_registry,
            tick=clock.tick,
            wake_reason=reason,
        ))
        proposal = run_policy_decide(self._policy, ctx)
        return (proposal,) if proposal is not None else ()


def make_p4_scheduler(wakeup_hooks: WakeupHookRegistry) -> Scheduler:
    """P4 Scheduler 装配（参数名/顺序以 scheduler.py:606-622 为准；
    装配形态同 conftest.py:264-290）：travel 注册表（P3 节复用）+
    双 named stub + B1 边界 + bob wakeup hook + 空 player 集
    （B1 blocking=False，无需 player 集）。"""
    install_write_barrier()
    return Scheduler(
        make_gate_registry(),
        authority_policy=make_p4_authority_policy(),
        origin=ORIGIN_PROVENANCE,
        time_policy=make_gate_time_policy(),
        boundaries=[make_p4_boundary()],
        trigger_registry=CascadeTriggerRegistry(),
        named_triggers=frozenset({
            ("scenario.theft_12", p4_theft_stub()),
            (TRIGGER_ARRIVAL, p4_arrival_stub()),
        }),
        wakeup_hooks=wakeup_hooks,
        player_actor_ids=frozenset(),
        assert_barrier_armed=True,
    )


def make_p4_mode_overlays() -> ModeOverlayRegistry:
    """两个模式 overlay（S12/S13 依次激活；字段口径见 §3.10）。

    dialogue：priority 10、checkpoint_interval 5、systems=("dialogue_system",)、
    context={"active": True}。
    tactical：priority 20、action_filter_kind="allow"、action_ids=("travel",)、
    checkpoint_interval 20、systems=("combat_system",)、
    time_policy=TimePolicy(checkpoint_interval_ticks=20)、
    input_policy={"capture_mode": "tactical"}、context={"active": True}。
    """
    return ModeOverlayRegistry({
        "dialogue": ModeOverlay(
            mode_id="dialogue", priority=10, checkpoint_interval=5,
            systems=("dialogue_system",), context={"active": True},
        ),
        "tactical": ModeOverlay(
            mode_id="tactical", priority=20,
            action_filter_kind="allow", action_ids=("travel",),
            checkpoint_interval=20, systems=("combat_system",),
            time_policy=TimePolicy(checkpoint_interval_ticks=20),
            input_policy={"capture_mode": "tactical"},
            context={"active": True},
        ),
    })
