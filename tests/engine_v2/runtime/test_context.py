"""Runtime Closure T4 gate 测试：runtime/context.py（ActorDecisionContext
构建 + 感知物化）。

契约依据 = ``docs/plans/runtime_closure_contract.md`` §4 T4 行（owned file
``src/engine_v2/runtime/context.py``；主路径复用 P4 冻结
``DefaultContextProvider``，感知物化 = P9 冻结 ``build_observations``）。

Gate（任务钉死；测试内直接构造最小 ``WorldInstance``——13 字段全必填，
world = 最小真实 WorldState（player actor + 三 NPC entity + spaces 组件），
spaces = GridSpace 最小实例 10×10 单域 ``world``，actor 位于 (0,0)）：

1. 同 domain 近距离 NPC（曼哈顿距离 1 ≤ 半径 5）→ 进 ``local_entity_views``
   + ``visible_entities``：
   ``TestGates::test_gate1_near_npc_in_local_and_visible``；
2. 远距离 NPC（曼哈顿距离 18 > 半径 5）→ 不在 ``local_entity_views``：
   ``TestGates::test_gate2_far_npc_not_in_local``；
3. ``global_entity_views is None``（无 world.read.global 授权）：
   ``TestGates::test_gate3_global_entity_views_none``；
4. ``self_view`` = actor 自己的 entity_view（entity_id 一致）+
   ``candidate_actions`` 为 registry 注册项的有序子集（casefold 排序、
   无重复、⊆ 注册键）：
   ``TestGates::test_gate4_self_view_and_candidate_actions``。

扩展钉面（结果钉 + 错误面 + 下层函数）：

- 感知记录 = build_observations 产物（sight/hearing 双感官分类 + 距离面 +
  自排除 + actor/tick 因子）：``TestObservations::test_observations_shape``；
- visible 并集口径 = self ∪ 感知 ∪ local（knowledge 缺席 → 无贡献）：
  ``TestObservations::test_visible_union_semantics``；
- ``local_entity_views`` 只含 visible：
  ``TestObservations::test_local_subset_visible``；
- 默认 grant 集 = 最小集（无 world.read.global）：
  ``TestObservations::test_granted_capabilities_minimum_set``；
- actor 不存在 → ``ActorUnknownError``（LookupError 族，显式错误）：
  ``TestErrors::test_unknown_actor_raises``；
- 主入口 = 下层函数缺省口径（wake_reason None + logical_tick）：
  ``TestWakeup::test_main_entry_defaults``；
- 下层函数 wake_reason / tick 透传（含感知记录 tick 因子）：
  ``TestWakeup::test_wakeup_passthrough``；
- player IR 数值声明消费（sight_m/hearing_m 覆盖 runtime 常量；local 半径
  同参联动）：``TestPlayerNumeric::test_player_numeric_capabilities``；
- bool 型"数值"拒绝（回落 runtime 常量）：
  ``TestPlayerNumeric::test_player_bool_declaration_rejected``；
- NPC 作决策主体 = 固定 runtime 默认路径（player id 推导零泄漏；global
  None / 最小 grant 集对 NPC 同样成立，Leader 勘误 2 口径）：
  ``TestNpcActor::test_npc_actor_fixed_defaults``。

自包含纪律：零 conftest 依赖（tests/engine_v2/runtime 无 conftest）；
``trace_sink`` = T8 同名 no-op 替身（T8 模块未就位；WorldInstance 为无
类型校验 dataclass，字段值任意对象可承载）；零网络 / 零 LLM / 零 API key。
"""

from __future__ import annotations

from src.engine_v2.content.schemas import (
    PlayerSpec,
    ProjectIR,
    ProjectManifest,
    ScenarioSpec,
    ScenarioTime,
)
from src.engine_v2.core.action_registry import ActionRegistry, ActionSpec
from src.engine_v2.core.actions import ActionTypeId
from src.engine_v2.core.authority import AuthorityPolicy, ProducerRegistry
from src.engine_v2.core.capability import Capability
from src.engine_v2.core.components import ComponentRegistry
from src.engine_v2.core.context_provider import ActorUnknownError
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.space import (
    SPACES_COMPONENT,
    GridSpace,
    SpaceMapping,
    SpaceRegistry,
    SpatialDomain,
    encode_spaces,
)
from src.engine_v2.core.state import RuntimeState, WorldState
from src.engine_v2.runtime.context import (
    build_actor_context,
    build_actor_context_for_wakeup,
)
from src.engine_v2.runtime.world_instance import WorldInstance

import pytest

# —— 确定性常量（内容侧命名约定 ids.py:68：ent_authoring_<slug>）——

PLAYER = EntityId("ent_authoring_player_one")
NPC_NEAR = EntityId("ent_authoring_npc_near")   # world (1,0)：距 actor 曼哈顿 1（≤ 半径 5）
NPC_MID = EntityId("ent_authoring_npc_mid")     # world (4,0)：距 actor 曼哈顿 4（≤ 5；> 听觉 3）
NPC_FAR = EntityId("ent_authoring_npc_far")     # world (9,9)：距 actor 曼哈顿 18（> 半径 5）

DOMAIN = "world"
TICK = 7

#: runtime 默认 grant 集（最小集；与 context.py 常量同值断言面）
MINIMUM_GRANTS = frozenset(
    {
        Capability.OBSERVATION_READ,
        Capability.KNOWLEDGE_READ,
        Capability.MEMORY_READ,
        Capability.WORLD_READ_LOCAL,
    }
)


class _StubTraceSink:
    """T8 RuntimeTraceSink 同名 no-op 替身（T8 模块未就位；WorldInstance
    dataclass 零类型校验，协议名面 = record / store_artifact /
    record_diagnostic，contract §1）。"""

    def record(self, *args: object, **kwargs: object) -> None:
        return None

    def store_artifact(self, *args: object, **kwargs: object) -> None:
        return None

    def record_diagnostic(self, *args: object, **kwargs: object) -> None:
        return None


# —— 最小构造工厂（自包含；每测试本地组装）——


def _entity(eid: EntityId, pos: tuple[int, int] | None = None) -> EntityRecord:
    """EntityRecord；pos 非 None → spaces 组件（单域 SpaceMapping）。"""
    components: dict = {}
    if pos is not None:
        components[SPACES_COMPONENT] = encode_spaces(
            (SpaceMapping(domain_id=DOMAIN, position={"x": pos[0], "y": pos[1]}),)
        )
    return EntityRecord(entity_id=eid, components=components)


def _ir(player_capabilities: dict | None = None) -> ProjectIR:
    return ProjectIR(
        manifest=ProjectManifest(
            schema_version="2", project_id="proj_ctx", name="ctx"
        ),
        scenario=ScenarioSpec(
            id="scene_ctx",
            max_ticks=10,
            ticks_per_game_minute=1.0,
            game_time=ScenarioTime(hour=8, minute=0),
        ),
        player=PlayerSpec(
            player_id="player_one",
            name="Player",
            capabilities=dict(player_capabilities or {}),
        ),
    )


def _spaces() -> SpaceRegistry:
    """GridSpace 最小实例：10×10 单域 ``world``（坐标越界拒绝面不触发）。"""
    return SpaceRegistry(
        {
            DOMAIN: (
                SpatialDomain(domain_id=DOMAIN, backend_kind="grid"),
                GridSpace(10, 10),
            )
        }
    )


def _registry() -> ActionRegistry:
    """三 action 规格；**插入序刻意非排序序**（验证 casefold 排序输出，
    而非透传插入序，CX-INV-7 口径）。"""
    return ActionRegistry(
        specs={
            ActionTypeId("travel"): ActionSpec(action_id="travel", executor="npc.brain"),
            ActionTypeId("ping"): ActionSpec(action_id="ping", executor="npc.brain"),
            ActionTypeId("interact"): ActionSpec(action_id="interact", executor="npc.brain"),
        }
    )


def _instance(player_capabilities: dict | None = None) -> WorldInstance:
    """最小真实 WorldInstance（13 字段全必填；world = player(0,0) + 三 NPC；
    runtime.logical_tick = 7；executors/policies 空、dynamics 空、authority
    closed-by-default 缺省）。"""
    world = WorldState(
        entities={
            PLAYER: _entity(PLAYER, (0, 0)),
            NPC_NEAR: _entity(NPC_NEAR, (1, 0)),
            NPC_MID: _entity(NPC_MID, (4, 0)),
            NPC_FAR: _entity(NPC_FAR, (9, 9)),
        }
    )
    return WorldInstance(
        world_instance_id="wi_ctx_1",
        ir=_ir(player_capabilities),
        world=world,
        runtime=RuntimeState(logical_tick=TICK),
        spaces=_spaces(),
        action_registry=_registry(),
        executors={},
        policies={},
        dynamics=(),
        component_registry=ComponentRegistry(),
        producer_registry=ProducerRegistry(),
        authority_policy=AuthorityPolicy(),
        trace_sink=_StubTraceSink(),
    )


def _kinds(ctx) -> set:
    """感知记录 → {(entity_id, kind, distance)} 断言面。"""
    return {
        (str(record.observed_entity_ids[0]), record.payload["kind"], record.payload["distance_m"])
        for record in ctx.observations
    }


# —— Gate 1–4（任务钉死）——


class TestGates:
    def test_gate1_near_npc_in_local_and_visible(self) -> None:
        """Gate 1：同 domain 近距离 NPC（曼哈顿 1 ≤ 半径 5）→ 进
        local_entity_views + visible_entities。"""
        ctx = build_actor_context(_instance(), str(PLAYER))
        assert NPC_NEAR in ctx.local_entity_views
        assert ctx.local_entity_views[NPC_NEAR].entity_id == NPC_NEAR
        assert NPC_NEAR in ctx.visible_entities

    def test_gate2_far_npc_not_in_local(self) -> None:
        """Gate 2：远距离 NPC（曼哈顿 18 > 半径 5）→ 不在
        local_entity_views（亦不在 visible——感知半径同参 5）。"""
        ctx = build_actor_context(_instance(), str(PLAYER))
        assert NPC_FAR not in ctx.local_entity_views
        assert NPC_FAR not in ctx.visible_entities

    def test_gate3_global_entity_views_none(self) -> None:
        """Gate 3：global_entity_views is None（无 world.read.global 授权；
        未授权 → None 非 {}，P4 第 4 步口径）。"""
        ctx = build_actor_context(_instance(), str(PLAYER))
        assert ctx.global_entity_views is None

    def test_gate4_self_view_and_candidate_actions(self) -> None:
        """Gate 4：self_view = actor 自己的 entity_view（entity_id 一致）；
        candidate_actions 为 registry 注册项的有序子集。"""
        instance = _instance()
        ctx = build_actor_context(instance, str(PLAYER))
        # self_view 身份 = actor 自身（值相等；entity_id 一致）
        assert ctx.self_view.entity_id == PLAYER
        assert ctx.self_view == instance.world.entity_view(PLAYER)
        assert ctx.actor_id == PLAYER
        # candidate_actions = registry 注册项的有序子集（⊆ 注册键、无重复、
        # casefold 排序；action_requirements 空 → 全满足 = 全项排序）
        registered = tuple(instance.action_registry.specs)
        assert set(ctx.candidate_actions) <= set(registered)
        assert len(set(ctx.candidate_actions)) == len(ctx.candidate_actions)
        assert list(ctx.candidate_actions) == sorted(
            ctx.candidate_actions, key=lambda aid: str(aid).casefold()
        )
        assert ctx.candidate_actions == ("interact", "ping", "travel")


# —— 结果钉：感知物化 / 并集口径 / grant 回显——


class TestObservations:
    def test_observations_shape(self) -> None:
        """observations = build_observations 产物：双感官分类 + 曼哈顿距离
        + actor/tick 因子 + 自排除（P9 冻结语义承继）。"""
        ctx = build_actor_context(_instance(), str(PLAYER))
        kinds = _kinds(ctx)
        # NEAR 距 1：sight(1) + hearing(1) 各一条
        assert (str(NPC_NEAR), "sight", 1) in kinds
        assert (str(NPC_NEAR), "hearing", 1) in kinds
        # MID 距 4：sight(4) 中、hearing 不中（4 > 3）
        assert (str(NPC_MID), "sight", 4) in kinds
        assert (str(NPC_MID), "hearing", 4) not in kinds
        # FAR 距 18：零记录
        assert not any(eid == str(NPC_FAR) for eid, _kind, _dist in kinds)
        # 记录全序 / actor / tick / 域 / 自排除
        assert all(record.actor_id == PLAYER for record in ctx.observations)
        assert all(record.tick == TICK for record in ctx.observations)
        assert all(PLAYER not in record.observed_entity_ids for record in ctx.observations)
        order = [
            (str(record.actor_id), str(record.observed_entity_ids[0]), str(record.payload["kind"]))
            for record in ctx.observations
        ]
        assert order == sorted(order)

    def test_visible_union_semantics(self) -> None:
        """visible_entities = 感知结果并集口径（self ∪ 感知 ∪ local；
        knowledge 组件缺席 → 零贡献）。"""
        ctx = build_actor_context(_instance(), str(PLAYER))
        assert ctx.visible_entities == frozenset({PLAYER, NPC_NEAR, NPC_MID})

    def test_local_subset_visible(self) -> None:
        """local_entity_views 只含 visible（键集 ⊆ visible_entities；local
        物化含 actor 自身，距离 0 ≤ 半径）。"""
        ctx = build_actor_context(_instance(), str(PLAYER))
        assert set(ctx.local_entity_views) <= set(ctx.visible_entities)
        assert PLAYER in ctx.local_entity_views  # 自身距离 0 ≤ 半径（P4 口径）
        assert NPC_MID in ctx.local_entity_views  # 距 4 ≤ local 半径 5

    def test_granted_capabilities_minimum_set(self) -> None:
        """grant 回显 = 最小集（无 world.read.global；含 world.read.local）。"""
        ctx = build_actor_context(_instance(), str(PLAYER))
        assert ctx.granted_capabilities == MINIMUM_GRANTS
        assert Capability.WORLD_READ_GLOBAL not in ctx.granted_capabilities
        assert Capability.WORLD_READ_LOCAL in ctx.granted_capabilities


# —— 错误面——


class TestErrors:
    def test_unknown_actor_raises(self) -> None:
        """actor 不存在 → ActorUnknownError（LookupError 族，显式错误，
        不产半截 context，CX-INV-1）。"""
        with pytest.raises(ActorUnknownError):
            build_actor_context(_instance(), "ent_nobody")


# —— 主入口 / 下层函数口径——


class TestWakeup:
    def test_main_entry_defaults(self) -> None:
        """主入口 = 下层函数缺省口径（wake_reason None + logical_tick）。"""
        instance = _instance()
        direct = build_actor_context(instance, str(PLAYER))
        via_wakeup = build_actor_context_for_wakeup(instance, str(PLAYER))
        assert direct == via_wakeup
        assert direct.wake_reason is None
        assert direct.tick == TICK
        assert direct.base_world_revision == instance.world.world_revision

    def test_wakeup_passthrough(self) -> None:
        """下层函数 wake_reason / tick 透传（含感知记录 tick 因子）。"""
        instance = _instance()
        ctx = build_actor_context_for_wakeup(
            instance, str(PLAYER), wake_reason="boundary_b1", tick=9
        )
        assert ctx.wake_reason == "boundary_b1"
        assert ctx.tick == 9
        assert all(record.tick == 9 for record in ctx.observations)


# —— 兜底语义（降级不崩溃，P4 D-P4-06 同款纪律）——


class TestDegraded:
    def test_empty_space_registry_zero_contribution(self) -> None:
        """空 SpaceRegistry（零注册域）→ 感知/local 零贡献不崩溃：
        visible = {actor}、local = {}、observations = ()、global 仍 None。"""
        instance = _instance()
        instance.spaces = SpaceRegistry({})
        ctx = build_actor_context(instance, str(PLAYER))
        assert ctx.visible_entities == frozenset({PLAYER})
        assert ctx.local_entity_views == {}
        assert ctx.observations == ()
        assert ctx.global_entity_views is None

    def test_actor_without_spaces_component_no_crash(self) -> None:
        """actor 无 spaces 组件（该域无 mapping）→ 感知/local 零贡献不崩溃
        （P4 兜底 1：无 mapping 域零贡献；感知缺席面同口径）。"""
        instance = _instance()
        instance.world = WorldState(
            entities={
                PLAYER: _entity(PLAYER, None),
                NPC_NEAR: _entity(NPC_NEAR, (1, 0)),
            }
        )
        ctx = build_actor_context(instance, str(PLAYER))
        assert ctx.visible_entities == frozenset({PLAYER})
        assert ctx.local_entity_views == {}
        assert ctx.observations == ()


# —— 普通 NPC 固定默认路径（decision subject = NPC，player id 推导零泄漏）——


class TestNpcActor:
    def test_npc_actor_fixed_defaults(self) -> None:
        """NPC 作决策主体：固定 runtime 默认集（与 player 同款最小集，无
        world.read.global → global=None 对 NPC 同样成立）；感知视角 = NPC
        自身（player 距 1 进 local + visible；self 自排除；grant 回显 =
        最小集）。"""
        ctx = build_actor_context(_instance(), str(NPC_NEAR))
        assert ctx.actor_id == NPC_NEAR
        assert ctx.self_view.entity_id == NPC_NEAR
        assert ctx.global_entity_views is None
        assert ctx.granted_capabilities == MINIMUM_GRANTS
        # local：NPC_NEAR(1,0) 视角——PLAYER(0,0) 距 1、MID(4,0) 距 3（≤ 5）
        assert PLAYER in ctx.local_entity_views
        assert NPC_MID in ctx.local_entity_views
        assert NPC_FAR not in ctx.local_entity_views
        assert set(ctx.local_entity_views) <= set(ctx.visible_entities)
        # 感知：sight 5 / hearing 3——PLAYER 距 1 双中；MID 距 3 双中（3 ≤ 3）
        kinds = _kinds(ctx)
        assert (str(PLAYER), "sight", 1) in kinds
        assert (str(PLAYER), "hearing", 1) in kinds
        assert (str(NPC_MID), "sight", 3) in kinds
        assert (str(NPC_MID), "hearing", 3) in kinds
        assert not any(eid == str(NPC_FAR) for eid, _kind, _dist in kinds)
        assert all(record.actor_id == NPC_NEAR for record in ctx.observations)
        assert ctx.visible_entities == frozenset({NPC_NEAR, PLAYER, NPC_MID})


# —— player IR 数值声明消费——


class TestPlayerNumeric:
    def test_player_numeric_capabilities(self) -> None:
        """player.capabilities 数值声明（sight_m=8 / hearing_m=2）消费：
        感知半径覆盖 runtime 常量；local 半径同参联动（ceil(8)=8）——
        MID 距 4 仍 local 内且仅 sight（4 > hearing 2）；FAR 距 18 出局。"""
        instance = _instance(player_capabilities={"sight_m": 8, "hearing_m": 2})
        ctx = build_actor_context(instance, str(PLAYER))
        kinds = _kinds(ctx)
        assert (str(NPC_MID), "sight", 4) in kinds
        assert (str(NPC_MID), "hearing", 4) not in kinds  # 4 > hearing 2
        assert (str(NPC_NEAR), "hearing", 1) in kinds  # 1 ≤ hearing 2
        assert NPC_MID in ctx.local_entity_views  # 4 ≤ local 半径 8
        assert NPC_FAR not in ctx.local_entity_views  # 18 > 8
        assert NPC_FAR not in ctx.visible_entities  # 18 > sight 8

    def test_player_bool_declaration_rejected(self) -> None:
        """bool 型"数值"声明拒绝（house 纪律：bool 是 int 子类，显式排除）
        → 回落 runtime 常量（与缺省 world 同口径）。"""
        declared = _instance(player_capabilities={"sight_m": True, "hearing_m": False})
        plain = _instance()
        ctx_declared = build_actor_context(declared, str(PLAYER))
        ctx_plain = build_actor_context(plain, str(PLAYER))
        assert _kinds(ctx_declared) == _kinds(ctx_plain)
        assert set(ctx_declared.local_entity_views) == set(ctx_plain.local_entity_views)
