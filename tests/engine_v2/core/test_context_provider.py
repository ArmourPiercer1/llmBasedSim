"""P4-T02 收尾验收：context_provider（设计文档 §3.8 全量行为，单测口径 L539）。

依据 ``docs/v2/contracts/P4-actor-context-space-mode-design.md``（下称"设计
文档"）§3.8（L445-540，含代码块与 CX-INV-1~7）+ 单测口径行 L539 + §6.1 表格
行 L1655 + D-P4-04/05/06 + ERR-P4-1/ERR-P4-2（Errata 修正口径）。

覆盖项 → 测试函数对照（G1；被测 6 导出 = ContextBuildInput / ActorDecisionContext /
ContextProvider / DefaultContextProvider / ActorUnknownError /
ContextInvariantError）：

1. **13 字段构造与冻结**（口径 L539 第 1 子项；ERR-P4-2 口径 =
   ``FrozenInstanceError``，代码库基线 test_entity_components.py:336 同款）：
   - ``TestFieldContract::test_context_build_input_7_fields_actor_id_first``
     （ContextBuildInput 7 字段序核验，actor_id 首位 = ERR-P4-1；
     实测序 actor_id/state/registry/capability_table/space_registry/tick/wake_reason）
   - ``TestFieldContract::test_actor_decision_context_13_field_order``
     （13 字段名与序，§3.8 代码块 L482-494 逐字）
   - ``TestFieldContract::test_actor_decision_context_full_construction``
     （13 字段全量构造成功 + 逐字段值断言）
   - ``TestFieldContract::test_actor_decision_context_reassignment_raises_frozen``
     （**任一**字段再赋值 → ``pytest.raises(FrozenInstanceError)``，13 字段逐一）
2. **无 actor → ActorUnknownError**（CX-INV-1；LookupError 族）：
   - ``TestActorUnknown::test_build_unknown_actor_raises``
3. **能力矩阵六行**（CX-INV-6，§3.8 L504 实际能力面；逐 capability 授予/撤回
   两态 × 对应字段填充/缺省）：
   - 行 1 observation.read ⇔ ``observations``：
     ``TestCapabilityMatrix::test_matrix_row_observation_read``
   - 行 2 knowledge.read ⇔ ``knowledge``：
     ``TestCapabilityMatrix::test_matrix_row_knowledge_read``
   - 行 3 memory.read ⇔ ``memory``（D-P4-09 原始透传）：
     ``TestCapabilityMatrix::test_matrix_row_memory_read``
   - 行 4 world.read.local ⇔ ``local_entity_views``：
     ``TestCapabilityMatrix::test_matrix_row_world_read_local``
   - 行 5 world.read.global ⇔ ``global_entity_views``（未授权 → **None**，非 {}）：
     ``TestCapabilityMatrix::test_matrix_row_world_read_global``
   - 行 6 candidate_actions ⇔ 逐 action ``table.satisfied``（空要求 = 恒满足；
     CX-INV-7 casefold 排序元组）：
     ``TestCapabilityMatrix::test_matrix_row_candidate_actions``
4. **可见集并集四来源各一**（CX-INV-2；self/observations/knowledge/local 各贡献
   恰一互异 id → 恰 4 id）+ 负例：
   - ``TestVisibleUnion::test_visible_entities_four_sources_each_one``
   - 超集负例（第五实体世界实存但四来源不可达 → 并集无额外 id）：
     ``TestVisibleUnion::test_visible_superset_negative_unreachable_fifth``
   - 缺项负例（移除 obs 组件 → 该 id 缺席）：
     ``TestVisibleUnion::test_visible_missing_negative_obs_removed``
5. **local 五态 + 两兜底**（D-P4-06 L507-514；六形态矩阵 §6.1 L1655）：
   - 态 1 None scope（默认半径 1）：
     ``TestLocalScope::test_local_scope_none_default_radius_one``
   - 态 2 ``{"radius": r}``（int r ≥ 1）：
     ``TestLocalScope::test_local_scope_radius_int``
   - 态 3 ``{"domain": d}``（域限定）：
     ``TestLocalScope::test_local_scope_domain_restriction``
   - 态 4 双键 ``{"domain": d, "radius": r}``：
     ``TestLocalScope::test_local_scope_domain_and_radius_both``
   - 态 5 未知键（含非 dict 形态）→ ContextInvariantError：
     ``TestLocalScope::test_local_scope_unknown_key_rejected``
   - radius=0 负例 → ContextInvariantError（r ≥ 1 边界，D-P4-06 权威；含
     bool/float 类型拒绝）：``TestLocalScope::test_local_scope_radius_zero_or_non_int_rejected``
   - 兜底 1 无 mapping 域不崩（域已注册、actor 无该域映射 → 零贡献不抛）：
     ``TestLocalScope::test_local_no_mapping_domain_zero_contribution``
   - 兜底 2 ``space_registry=None`` → ``{}`` 降级（不报错）：
     ``TestLocalScope::test_local_space_registry_none_downgrades``
6. **prompt 不透明**（CX-INV-5 的 A2 运行期面：不同 prompt 同输入 → 逐字段
   相等的 context）：
   - ``TestPromptOpacity::test_prompt_opaque_build_independent``
7. **granted_capabilities 回显 == 表内该 actor 授权集**（G4-2 断言面）：
   - ``TestGrantedEcho::test_granted_capabilities_echo``

fixture 基线（任务钉死）：每个测试构造自己的最小 WorldState（``guard()`` 得
GuardedWorldState）+ ActionRegistry + CapabilityTable + SpaceRegistry（或 None）
+ ContextBuildInput 7 字段——全部本地构造，自包含，不依赖 conftest 工厂。

布局（P2 勘误 E4 沿袭）：位于 ``tests/engine_v2/core/``；直接从子模块 import，
不经包级导出；全部用例无网络、无 LLM、无 API key。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields
from typing import Any

import pytest
from pydantic import JsonValue

from src.engine_v2.core.action_registry import ActionRegistry, ActionSpec
from src.engine_v2.core.actions import ActionTypeId
from src.engine_v2.core.capability import Capability, CapabilityGrant, CapabilityTable
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.context_provider import (
    ActorDecisionContext,
    ActorUnknownError,
    ContextBuildInput,
    ContextInvariantError,
    DefaultContextProvider,
)
from src.engine_v2.core.entity import EntityRecord, EntityView
from src.engine_v2.core.ids import EntityId, ObservationId
from src.engine_v2.core.knowledge import (
    KNOWLEDGE_COMPONENT,
    MEMORY_COMPONENT,
    OBSERVATIONS_COMPONENT,
    Belief,
    BeliefKind,
    KnowledgeState,
    ObservationRecord,
    encode_knowledge,
    encode_observations,
)
from src.engine_v2.core.reducer import guard
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.space import (
    SPACES_COMPONENT,
    GridSpace,
    SpaceMapping,
    SpaceRegistry,
    SpatialDomain,
    encode_spaces,
)
from src.engine_v2.core.state import WorldState

# —— 确定性常量（自包含；前缀词法 ids.py 口径）——

ACTOR = EntityId("ent_actor")
OTHER = EntityId("ent_other")
ENT_OBS = EntityId("ent_obs")
ENT_KNOW = EntityId("ent_know")
ENT_LOCAL = EntityId("ent_local")
ENT_FIFTH = EntityId("ent_fifth")
ENT_NEAR = EntityId("ent_near")  # overworld (0,1)，距 actor 曼哈顿 1
ENT_MID = EntityId("ent_mid")  # overworld (0,2)，距 actor 曼哈顿 2
ENT_FAR = EntityId("ent_far")  # overworld (0,4)，距 actor 曼哈顿 4
ENT_OWN = EntityId("ent_own")  # overworld (1,0)，距 actor 曼哈顿 1
ENT_CITY = EntityId("ent_city")  # city (3,2)，距 actor city 位 (2,2) 曼哈顿 1
ENT_CITY_MID = EntityId("ent_city_mid")  # city (4,2)，距 actor city 位曼哈顿 2
ENT_CITY_FAR = EntityId("ent_city_far")  # city (5,2)，距 actor city 位曼哈顿 3

OVERWORLD = "overworld"
CITY = "city"


# —— 最小构造工厂（自包含；每测试本地组装 fixture 基线）——


def _entity(eid: EntityId, components: Mapping[ComponentTypeId, Any] | None = None) -> EntityRecord:
    return EntityRecord(entity_id=eid, components=dict(components or {}))


def _obs_component() -> dict[str, Any]:
    """observations 组件载荷（D-P4-09 编解码面；观察对象 = ENT_OBS）。"""
    return encode_observations(
        (
            ObservationRecord(
                observation_id=ObservationId("obs_001"),
                actor_id=ACTOR,
                tick=1,
                observed_entity_ids=(ENT_OBS,),
            ),
        )
    )


def _knowledge_component() -> dict[str, Any]:
    """knowledge 组件载荷（belief subject = "ent_know"，世界实存 → ∩ 后入并集）。"""
    return encode_knowledge(
        KnowledgeState(
            beliefs=(
                Belief(
                    kind=BeliefKind.FACT,
                    subject="ent_know",
                    predicate="adjacent_to",
                    value=1,
                    confidence=0.9,
                    formed_tick=1,
                ),
            ),
            last_updated_tick=1,
        )
    )


def _spaces_component(*pairs: tuple[str, int, int]) -> dict[str, Any]:
    """spaces 组件载荷：(domain_id, x, y) 逐条 SpaceMapping。"""
    return encode_spaces(
        tuple(SpaceMapping(domain_id=d, position={"x": x, "y": y}) for d, x, y in pairs)
    )


def _registry() -> ActionRegistry:
    return ActionRegistry(
        specs={
            ActionTypeId("travel"): ActionSpec(action_id="travel", executor="npc.brain"),
        }
    )


def _three_action_registry() -> ActionRegistry:
    """三 action 规格；**插入序刻意非排序序**（验证 CX-INV-7 排序输出，
    而非透传插入序）。"""
    return ActionRegistry(
        specs={
            ActionTypeId("travel"): ActionSpec(action_id="travel", executor="npc.brain"),
            ActionTypeId("ping"): ActionSpec(action_id="ping", executor="npc.brain"),
            ActionTypeId("interact"): ActionSpec(action_id="interact", executor="npc.brain"),
        }
    )


def _grant(
    capability: Capability, scope: Mapping[str, Any] | list[Any] | None = None
) -> CapabilityGrant:
    """单条授权工厂；scope 非 Mapping 形态（list 等，合法 JsonValue）原样透传
    （供"scope 非 None 且非 dict → ContextInvariantError"用例）。"""
    if scope is None:
        scope_value: JsonValue | None = None
    elif isinstance(scope, Mapping):
        scope_value = dict(scope)
    else:
        scope_value = list(scope)
    return CapabilityGrant(actor_id=ACTOR, capability=capability, scope=scope_value)


def _table(*grants: CapabilityGrant) -> CapabilityTable:
    return CapabilityTable(grants=grants)


def _all_grants_table() -> CapabilityTable:
    return _table(
        _grant(Capability.OBSERVATION_READ),
        _grant(Capability.KNOWLEDGE_READ),
        _grant(Capability.MEMORY_READ),
        _grant(Capability.WORLD_READ_LOCAL),
        _grant(Capability.WORLD_READ_GLOBAL),
    )


def _grid_registry(*domains: str) -> SpaceRegistry:
    """8×8 GridSpace 域注册表（域 id 小写，S-INV-1 合规）。"""
    return SpaceRegistry(
        {d: (SpatialDomain(domain_id=d, backend_kind="grid"), GridSpace(8, 8)) for d in domains}
    )


def _input(
    state: WorldState,
    table: CapabilityTable,
    registry: ActionRegistry,
    space_registry: SpaceRegistry | None,
    actor: EntityId = ACTOR,
    tick: int = 7,
    wake_reason: str | None = "boundary_b1",
) -> ContextBuildInput:
    """ContextBuildInput 7 字段当刻组装（state 经 guard() 得 GuardedWorldState）。"""
    return ContextBuildInput(
        actor_id=actor,
        state=guard(state),
        registry=registry,
        capability_table=table,
        space_registry=space_registry,
        tick=tick,
        wake_reason=wake_reason,
    )


def _full_world() -> WorldState:
    """四来源各一的最小世界（CX-INV-2 union 口径）：

    - ACTOR：obs 组件（观察 ENT_OBS）+ knowledge 组件（subject "ent_know"）
      + memory 组件 + overworld (0,0) 空间映射；
    - ENT_OBS：无空间映射（仅 obs 源可达）；
    - ENT_KNOW：无空间映射（仅 knowledge 源可达）；
    - ENT_LOCAL：overworld (1,0)（距 actor 1 → local 源可达，半径 1 内）。
    """
    return WorldState(
        world_revision=Revision(3),
        entities={
            ACTOR: _entity(
                ACTOR,
                {
                    OBSERVATIONS_COMPONENT: _obs_component(),
                    KNOWLEDGE_COMPONENT: _knowledge_component(),
                    MEMORY_COMPONENT: {"items": [1, "a"]},
                    SPACES_COMPONENT: _spaces_component((OVERWORLD, 0, 0)),
                },
            ),
            ENT_OBS: _entity(ENT_OBS),
            ENT_KNOW: _entity(ENT_KNOW),
            ENT_LOCAL: _entity(
                ENT_LOCAL, {SPACES_COMPONENT: _spaces_component((OVERWORLD, 1, 0))}
            ),
        },
    )


def _local_world(extra: Mapping[EntityId, tuple[str, int, int]]) -> WorldState:
    """local 物化最小世界：ACTOR overworld (0,0) + 指定实体的域位置映射。"""
    entities: dict[EntityId, EntityRecord] = {
        ACTOR: _entity(ACTOR, {SPACES_COMPONENT: _spaces_component((OVERWORLD, 0, 0))})
    }
    for eid, (domain, x, y) in extra.items():
        entities[eid] = _entity(eid, {SPACES_COMPONENT: _spaces_component((domain, x, y))})
    return WorldState(world_revision=Revision(3), entities=entities)


def _build_full() -> ActorDecisionContext:
    """全授权 + 四来源世界的 provider 产物（冻结/逐字段断言的公共基线）。"""
    return DefaultContextProvider().build(
        _input(_full_world(), _all_grants_table(), _registry(), _grid_registry(OVERWORLD))
    )


# —— 覆盖项 1：13 字段构造与冻结（口径 L539；ERR-P4-1/ERR-P4-2）——


class TestFieldContract:
    """覆盖项 1：ContextBuildInput 7 字段（actor_id 首位，ERR-P4-1）+
    ActorDecisionContext 13 字段全量构造与冻结（ERR-P4-2 口径 =
    ``FrozenInstanceError``，test_entity_components.py:336 同款基线）。"""

    def test_context_build_input_7_fields_actor_id_first(self) -> None:
        names = [f.name for f in fields(ContextBuildInput)]
        assert len(names) == 7
        assert names[0] == "actor_id"  # ERR-P4-1：actor_id 首位（唤醒侧值传递）
        assert names == [
            "actor_id",
            "state",
            "registry",
            "capability_table",
            "space_registry",
            "tick",
            "wake_reason",
        ]

    def test_actor_decision_context_13_field_order(self) -> None:
        names = [f.name for f in fields(ActorDecisionContext)]
        assert len(names) == 13  # K7 全可检查：13 字段契约
        assert names == [
            "actor_id",
            "tick",
            "base_world_revision",
            "wake_reason",
            "self_view",
            "visible_entities",
            "local_entity_views",
            "global_entity_views",
            "observations",
            "knowledge",
            "memory",
            "candidate_actions",
            "granted_capabilities",
        ]

    def test_actor_decision_context_full_construction(self) -> None:
        state = _full_world()
        view = state.entity_view(ACTOR)
        assert view is not None
        ctx = ActorDecisionContext(
            actor_id=ACTOR,
            tick=7,
            base_world_revision=Revision(3),
            wake_reason="boundary_b1",
            self_view=view,
            visible_entities=frozenset({ACTOR, ENT_OBS, ENT_KNOW, ENT_LOCAL}),
            local_entity_views={},
            global_entity_views=None,
            observations=(),
            knowledge=None,
            memory=(),
            candidate_actions=(),
            granted_capabilities=frozenset(),
        )
        assert ctx.actor_id == ACTOR
        assert ctx.tick == 7
        assert ctx.base_world_revision == Revision(3)
        assert ctx.wake_reason == "boundary_b1"
        assert ctx.self_view.entity_id == ACTOR
        assert ctx.visible_entities == frozenset({ACTOR, ENT_OBS, ENT_KNOW, ENT_LOCAL})
        assert ctx.local_entity_views == {}
        assert ctx.global_entity_views is None
        assert ctx.observations == ()
        assert ctx.knowledge is None
        assert ctx.memory == ()
        assert ctx.candidate_actions == ()
        assert ctx.granted_capabilities == frozenset()

    def test_actor_decision_context_reassignment_raises_frozen(self) -> None:
        ctx = _build_full()
        for f in fields(ActorDecisionContext):  # 13 字段逐一（任一字段即拒）
            with pytest.raises(FrozenInstanceError):
                setattr(ctx, f.name, None)  # type: ignore[misc]


# —— 覆盖项 2：无 actor → ActorUnknownError（CX-INV-1）——


class TestActorUnknown:
    """覆盖项 2：CX-INV-1——``ContextBuildInput.actor_id`` 不在世界实体集
    → build 抛 :class:`ActorUnknownError`（LookupError 族，§3.8 L532-533；
    不产半截 context）。"""

    def test_build_unknown_actor_raises(self) -> None:
        state = WorldState(world_revision=Revision(3), entities={OTHER: _entity(OTHER)})
        table = _table(_grant(Capability.OBSERVATION_READ))
        inp = _input(
            state, table, _registry(), _grid_registry(OVERWORLD), actor=EntityId("ent_ghost")
        )
        with pytest.raises(ActorUnknownError) as excinfo:
            DefaultContextProvider().build(inp)
        assert isinstance(excinfo.value, LookupError)


# —— 覆盖项 3：能力矩阵六行（CX-INV-6，§3.8 L504 实际能力面）——


class TestCapabilityMatrix:
    """覆盖项 3：CX-INV-6 能力门控填充矩阵——六行以 §3.8 L504 实际能力面为准，
    每行授予/撤回两态 × 对应字段填充/缺省（详见模块 docstring 行 1-6 对照）。"""

    def test_matrix_row_observation_read(self) -> None:
        """行 1：observation.read ⇔ ``observations``（经本域 decode_observations）。"""
        state = WorldState(
            world_revision=Revision(3),
            entities={
                ACTOR: _entity(ACTOR, {OBSERVATIONS_COMPONENT: _obs_component()}),
                ENT_OBS: _entity(ENT_OBS),
            },
        )
        # 授予态：observations 填充
        ctx = DefaultContextProvider().build(
            _input(state, _table(_grant(Capability.OBSERVATION_READ)), _registry(), None)
        )
        assert len(ctx.observations) == 1
        assert ctx.observations[0].observation_id == ObservationId("obs_001")
        assert ctx.observations[0].observed_entity_ids == (ENT_OBS,)
        # 撤回态：组件在位但无授权 → 缺省 ()（组件存在不泄漏）
        ctx_revoked = DefaultContextProvider().build(_input(state, _table(), _registry(), None))
        assert ctx_revoked.observations == ()

    def test_matrix_row_knowledge_read(self) -> None:
        """行 2：knowledge.read ⇔ ``knowledge``（经本域 decode_knowledge）。"""
        state = WorldState(
            world_revision=Revision(3),
            entities={
                ACTOR: _entity(ACTOR, {KNOWLEDGE_COMPONENT: _knowledge_component()}),
                ENT_KNOW: _entity(ENT_KNOW),
            },
        )
        ctx = DefaultContextProvider().build(
            _input(state, _table(_grant(Capability.KNOWLEDGE_READ)), _registry(), None)
        )
        assert isinstance(ctx.knowledge, KnowledgeState)
        assert ctx.knowledge is not None
        assert ctx.knowledge.reference_entity_ids() == frozenset({"ent_know"})
        assert ctx.knowledge.beliefs[0].confidence == 0.9
        # 撤回态：组件在位但无授权 → 缺省 None
        ctx_revoked = DefaultContextProvider().build(_input(state, _table(), _registry(), None))
        assert ctx_revoked.knowledge is None

    def test_matrix_row_memory_read(self) -> None:
        """行 3：memory.read ⇔ ``memory``（D-P4-09 无编解码器，原始 tuple 透传）。"""
        state = WorldState(
            world_revision=Revision(3),
            entities={
                ACTOR: _entity(ACTOR, {MEMORY_COMPONENT: {"items": [1, "a"]}}),
            },
        )
        ctx = DefaultContextProvider().build(
            _input(state, _table(_grant(Capability.MEMORY_READ)), _registry(), None)
        )
        assert ctx.memory == (1, "a")  # {"items": [...]} 原始列表 → tuple 不解释
        # 撤回态：组件在位但无授权 → 缺省 ()
        ctx_revoked = DefaultContextProvider().build(_input(state, _table(), _registry(), None))
        assert ctx_revoked.memory == ()

    def test_matrix_row_world_read_local(self) -> None:
        """行 4：world.read.local ⇔ ``local_entity_views``（授权且空间可达才填充）。"""
        state = _local_world({ENT_NEAR: (OVERWORLD, 0, 1)})
        # 授予态（scope None = 全注册域半径 1）：邻域填充（含 actor 自身，距离 0）
        ctx = DefaultContextProvider().build(
            _input(
                state,
                _table(_grant(Capability.WORLD_READ_LOCAL)),
                _registry(),
                _grid_registry(OVERWORLD),
            )
        )
        assert set(ctx.local_entity_views) == {ACTOR, ENT_NEAR}
        # 撤回态：无授权 → 缺省 {}（空间可达也不填充）
        ctx_revoked = DefaultContextProvider().build(
            _input(state, _table(), _registry(), _grid_registry(OVERWORLD))
        )
        assert ctx_revoked.local_entity_views == {}

    def test_matrix_row_world_read_global(self) -> None:
        """行 5：world.read.global ⇔ ``global_entity_views``（未授权 → **None**，非 {}）。"""
        state = WorldState(
            world_revision=Revision(3),
            entities={
                ACTOR: _entity(ACTOR),
                ENT_OBS: _entity(ENT_OBS),
                ENT_KNOW: _entity(ENT_KNOW),
            },
        )
        # 授予态：全实体视图（键 = 世界全部实体）
        ctx = DefaultContextProvider().build(
            _input(
                state,
                _table(_grant(Capability.WORLD_READ_GLOBAL)),
                _registry(),
                _grid_registry(OVERWORLD),
            )
        )
        assert ctx.global_entity_views is not None
        assert set(ctx.global_entity_views) == {ACTOR, ENT_OBS, ENT_KNOW}
        for eid, view in ctx.global_entity_views.items():
            assert isinstance(view, EntityView)
            assert view.entity_id == eid
        # 撤回态：未授权 → None（§3.8 L494 逐字，非 {}）
        ctx_revoked = DefaultContextProvider().build(_input(state, _table(), _registry(), None))
        assert ctx_revoked.global_entity_views is None

    def test_matrix_row_candidate_actions(self) -> None:
        """行 6：candidate_actions ⇔ 逐 action ``table.satisfied``
        （空要求 = 恒满足；CX-INV-7 casefold 排序元组，确定性不依赖插入序）。"""
        table = CapabilityTable(
            grants=(_grant(Capability.WORLD_READ_LOCAL),),
            action_requirements={
                ActionTypeId("travel"): (Capability.WORLD_READ_LOCAL,),
                ActionTypeId("interact"): (Capability.OBSERVATION_READ,),
            },
        )
        ctx = DefaultContextProvider().build(
            _input(_local_world({}), table, _three_action_registry(), None)
        )
        # 满足者入（travel：要求已授权；ping：无要求 = 恒满足）；interact 要求
        # observation.read 未授权 → 排除。插入序 travel/ping/interact → 排序输出
        # ping/travel（casefold 序）。
        assert ctx.candidate_actions == (ActionTypeId("ping"), ActionTypeId("travel"))
        assert type(ctx.candidate_actions) is tuple
        assert type(ctx.candidate_actions[0]) is ActionTypeId


# —— 覆盖项 4：可见集并集四来源各一（CX-INV-2）——


class TestVisibleUnion:
    """覆盖项 4：CX-INV-2——visible_entities = {actor} ∪ observations ∪
    (knowledge.reference_entity_ids() ∩ 世界实存) ∪ local 键集；超集禁止、
    缺项禁止（两侧断言）。"""

    def test_visible_entities_four_sources_each_one(self) -> None:
        ctx = _build_full()
        # 恰 4 个互异 id：self / observations / knowledge / local 各贡献恰一
        assert ctx.visible_entities == frozenset({ACTOR, ENT_OBS, ENT_KNOW, ENT_LOCAL})
        assert len(ctx.visible_entities) == 4
        # 来源互异性断言（缺项禁止的正面形态）
        observed_ids = frozenset(
            eid for record in ctx.observations for eid in record.observed_entity_ids
        )
        assert observed_ids == frozenset({ENT_OBS})
        assert ctx.knowledge is not None
        assert ctx.knowledge.reference_entity_ids() == frozenset({"ent_know"})
        assert set(ctx.local_entity_views) == {ACTOR, ENT_LOCAL}  # local 源 = 邻域（含自身）
        assert ENT_OBS not in ctx.local_entity_views  # ENT_OBS 仅 obs 源（无空间映射）
        assert ENT_KNOW not in ctx.local_entity_views  # ENT_KNOW 仅 knowledge 源

    def test_visible_superset_negative_unreachable_fifth(self) -> None:
        """超集负例：第五实体世界实存但四来源均不可达 → 并集无额外 id。"""
        state = WorldState(
            world_revision=Revision(3),
            entities={
                **_full_world().entities,
                # ENT_FIFTH：overworld (3,3)（距 actor 曼哈顿 6 > 半径 1），
                # 无 obs / knowledge 引用 → 四来源均不可达
                ENT_FIFTH: _entity(
                    ENT_FIFTH, {SPACES_COMPONENT: _spaces_component((OVERWORLD, 3, 3))}
                ),
            },
        )
        ctx = DefaultContextProvider().build(
            _input(state, _all_grants_table(), _registry(), _grid_registry(OVERWORLD))
        )
        assert ENT_FIFTH in state.entities  # 世界实存（对照：不是"不在世界"）
        assert ENT_FIFTH not in ctx.visible_entities  # 超集禁止
        assert ctx.visible_entities == frozenset({ACTOR, ENT_OBS, ENT_KNOW, ENT_LOCAL})
        assert len(ctx.visible_entities) == 4

    def test_visible_missing_negative_obs_removed(self) -> None:
        """缺项负例：移除 obs 组件 → 观察源贡献消失，该 id 缺席。"""
        state = WorldState(
            world_revision=Revision(3),
            entities={
                ACTOR: _entity(
                    ACTOR,
                    {
                        # 无 OBSERVATIONS_COMPONENT（移除 obs 组件；授权仍在）
                        KNOWLEDGE_COMPONENT: _knowledge_component(),
                        SPACES_COMPONENT: _spaces_component((OVERWORLD, 0, 0)),
                    },
                ),
                ENT_OBS: _entity(ENT_OBS),
                ENT_KNOW: _entity(ENT_KNOW),
                ENT_LOCAL: _entity(
                    ENT_LOCAL, {SPACES_COMPONENT: _spaces_component((OVERWORLD, 1, 0))}
                ),
            },
        )
        table = _table(
            _grant(Capability.OBSERVATION_READ),
            _grant(Capability.KNOWLEDGE_READ),
            _grant(Capability.WORLD_READ_LOCAL),
        )
        ctx = DefaultContextProvider().build(
            _input(state, table, _registry(), _grid_registry(OVERWORLD))
        )
        assert ctx.observations == ()
        assert ENT_OBS not in ctx.visible_entities  # 缺项
        assert ctx.visible_entities == frozenset({ACTOR, ENT_KNOW, ENT_LOCAL})


# —— 覆盖项 5：local 五态 + 两兜底（D-P4-06；§6.1 L1655 六形态矩阵）——


class TestLocalScope:
    """覆盖项 5：D-P4-06 local 范围语义——scope 四形态 + 未知键拒绝
    （五态）+ radius=0 负例（r ≥ 1 边界，D-P4-06 权威）+ 无 mapping 域零贡献
    / ``space_registry=None`` 恒空（两兜底）。全部用例 actor overworld (0,0)、
    8×8 GridSpace（曼哈顿距离）。"""

    def test_local_scope_none_default_radius_one(self) -> None:
        """态 1：scope None → 全部注册域、半径 1（保守缺省：仅邻接）。"""
        state = _local_world({ENT_NEAR: (OVERWORLD, 0, 1), ENT_MID: (OVERWORLD, 0, 2)})
        ctx = DefaultContextProvider().build(
            _input(
                state,
                _table(_grant(Capability.WORLD_READ_LOCAL)),
                _registry(),
                _grid_registry(OVERWORLD),
            )
        )
        assert set(ctx.local_entity_views) == {ACTOR, ENT_NEAR}  # 距离 1 入、距离 2 出

    def test_local_scope_radius_int(self) -> None:
        """态 2：``{"radius": r}``（int r ≥ 1）→ 全部注册域、半径 r。"""
        state = _local_world(
            {
                ENT_NEAR: (OVERWORLD, 0, 1),
                ENT_MID: (OVERWORLD, 0, 2),
                ENT_FAR: (OVERWORLD, 0, 4),
            }
        )
        ctx = DefaultContextProvider().build(
            _input(
                state,
                _table(_grant(Capability.WORLD_READ_LOCAL, {"radius": 3})),
                _registry(),
                _grid_registry(OVERWORLD),
            )
        )
        assert set(ctx.local_entity_views) == {ACTOR, ENT_NEAR, ENT_MID}  # 距离 2 入、4 出

    def test_local_scope_domain_restriction(self) -> None:
        """态 3：``{"domain": d}`` → 仅域 d、半径 1（跨域邻接不纳入）。"""
        state = WorldState(
            world_revision=Revision(3),
            entities={
                ACTOR: _entity(
                    ACTOR,
                    {SPACES_COMPONENT: _spaces_component((OVERWORLD, 0, 0), (CITY, 2, 2))},
                ),
                ENT_OWN: _entity(ENT_OWN, {SPACES_COMPONENT: _spaces_component((OVERWORLD, 1, 0))}),
                ENT_CITY: _entity(
                    ENT_CITY, {SPACES_COMPONENT: _spaces_component((CITY, 3, 2))}
                ),
            },
        )
        ctx = DefaultContextProvider().build(
            _input(
                state,
                _table(_grant(Capability.WORLD_READ_LOCAL, {"domain": CITY})),
                _registry(),
                _grid_registry(OVERWORLD, CITY),
            )
        )
        assert set(ctx.local_entity_views) == {ACTOR, ENT_CITY}  # 仅 city 域扫描
        assert ENT_OWN not in ctx.local_entity_views  # overworld 邻接被域限定排除

    def test_local_scope_domain_and_radius_both(self) -> None:
        """态 4：``{"domain": d, "radius": r}`` → 仅域 d、半径 r。"""
        state = WorldState(
            world_revision=Revision(3),
            entities={
                ACTOR: _entity(
                    ACTOR,
                    {SPACES_COMPONENT: _spaces_component((OVERWORLD, 0, 0), (CITY, 2, 2))},
                ),
                ENT_OWN: _entity(ENT_OWN, {SPACES_COMPONENT: _spaces_component((OVERWORLD, 1, 0))}),
                ENT_CITY: _entity(
                    ENT_CITY, {SPACES_COMPONENT: _spaces_component((CITY, 3, 2))}
                ),
                ENT_CITY_MID: _entity(
                    ENT_CITY_MID, {SPACES_COMPONENT: _spaces_component((CITY, 4, 2))}
                ),
                ENT_CITY_FAR: _entity(
                    ENT_CITY_FAR, {SPACES_COMPONENT: _spaces_component((CITY, 5, 2))}
                ),
            },
        )
        ctx = DefaultContextProvider().build(
            _input(
                state,
                _table(_grant(Capability.WORLD_READ_LOCAL, {"domain": CITY, "radius": 2})),
                _registry(),
                _grid_registry(OVERWORLD, CITY),
            )
        )
        # city 域内：距离 1（ENT_CITY）/2（ENT_CITY_MID）入、距离 3（ENT_CITY_FAR）出
        assert set(ctx.local_entity_views) == {ACTOR, ENT_CITY, ENT_CITY_MID}
        assert ENT_OWN not in ctx.local_entity_views  # 域限定仍生效

    def test_local_scope_unknown_key_rejected(self) -> None:
        """态 5：未知 scope 键（及非 dict 形态）→ ContextInvariantError
        （可检查不静默，fail-fast；ValueError 族，§3.8 L535-536）。"""
        state = _local_world({})
        registry = _registry()
        space_registry = _grid_registry(OVERWORLD)
        for scope in ({"radius": 1, "zoom": 2}, ["radius", 1]):
            table = _table(_grant(Capability.WORLD_READ_LOCAL, scope))
            with pytest.raises(ContextInvariantError):
                DefaultContextProvider().build(_input(state, table, registry, space_registry))
        with pytest.raises(ContextInvariantError) as excinfo:
            table = _table(_grant(Capability.WORLD_READ_LOCAL, {"radius": 1, "zoom": 2}))
            DefaultContextProvider().build(_input(state, table, registry, space_registry))
        assert isinstance(excinfo.value, ValueError)

    def test_local_scope_radius_zero_or_non_int_rejected(self) -> None:
        """radius=0 负例 → ContextInvariantError（r ≥ 1 边界，D-P4-06 权威）；
        同边界类型面：bool / float radius 拒绝（isinstance 陷阱显式堵死）。"""
        state = _local_world({})
        registry = _registry()
        space_registry = _grid_registry(OVERWORLD)
        for scope in ({"radius": 0}, {"radius": True}, {"radius": 2.0}):
            table = _table(_grant(Capability.WORLD_READ_LOCAL, scope))
            with pytest.raises(ContextInvariantError):
                DefaultContextProvider().build(_input(state, table, registry, space_registry))

    def test_local_no_mapping_domain_zero_contribution(self) -> None:
        """兜底 1：域已注册、actor 无该域映射 → 该域零贡献（不崩溃、不抛）。"""
        state = WorldState(
            world_revision=Revision(3),
            entities={
                # actor 仅 overworld 映射（city 域无 mapping）
                ACTOR: _entity(ACTOR, {SPACES_COMPONENT: _spaces_component((OVERWORLD, 0, 0))}),
                ENT_CITY: _entity(
                    ENT_CITY, {SPACES_COMPONENT: _spaces_component((CITY, 0, 0))}
                ),
            },
        )
        registry = _registry()
        space_registry = _grid_registry(OVERWORLD, CITY)
        # 全注册域读法（scope None）：city 域零贡献，overworld 邻域仍填充
        ctx_all = DefaultContextProvider().build(
            _input(
                state,
                _table(_grant(Capability.WORLD_READ_LOCAL)),
                registry,
                space_registry,
            )
        )
        assert set(ctx_all.local_entity_views) == {ACTOR}
        assert ENT_CITY not in ctx_all.local_entity_views
        # 显式域限定读法：actor 无 city mapping → 零贡献不抛（与全注册域等价回退）
        ctx_city = DefaultContextProvider().build(
            _input(
                state,
                _table(_grant(Capability.WORLD_READ_LOCAL, {"domain": CITY})),
                registry,
                space_registry,
            )
        )
        assert ctx_city.local_entity_views == {}

    def test_local_space_registry_none_downgrades(self) -> None:
        """兜底 2：``space_registry is None`` → local 恒空（无空间面 = 无 local
        数据，降级不报错；授权与 actor 空间映射均在位也不改变）。"""
        state = _local_world({ENT_NEAR: (OVERWORLD, 0, 1)})
        ctx = DefaultContextProvider().build(
            _input(
                state,
                _table(_grant(Capability.WORLD_READ_LOCAL)),
                _registry(),
                None,
            )
        )
        assert ctx.local_entity_views == {}


# —— 覆盖项 6：prompt 不透明（CX-INV-5 的 A2 运行期面）——


class TestPromptOpacity:
    """覆盖项 6：prompt 仅 ``__init__`` 存储点（CX-INV-5）——两个
    DefaultContextProvider（不同 prompt）同输入 → 逐字段相等的 context
    （A2 的运行期面：build 路径零引用 prompt，K4：Prompt 不定义权限）。"""

    def test_prompt_opaque_build_independent(self) -> None:
        inp = _input(_full_world(), _all_grants_table(), _registry(), _grid_registry(OVERWORLD))
        provider_a = DefaultContextProvider(prompt="prompt-alpha")
        provider_b = DefaultContextProvider(prompt="prompt-beta")
        assert provider_a.prompt == "prompt-alpha"  # 存储点（CX-INV-5）
        assert provider_b.prompt == "prompt-beta"
        ctx_a = provider_a.build(inp)
        ctx_b = provider_b.build(inp)
        for f in fields(ActorDecisionContext):  # 逐字段相等（13 字段全量）
            assert getattr(ctx_a, f.name) == getattr(ctx_b, f.name), f.name
        # 缺省 prompt（None 存储缺省位）同输入同 context
        ctx_default = DefaultContextProvider().build(inp)
        assert DefaultContextProvider().prompt is None
        for f in fields(ActorDecisionContext):
            assert getattr(ctx_default, f.name) == getattr(ctx_a, f.name), f.name


# —— 覆盖项 7：granted_capabilities 回显（G4-2 断言面）——


class TestGrantedEcho:
    """覆盖项 7：``granted_capabilities`` = 表内该 actor 授权集的回显
    （frozenset；他 actor 授权不混入）。"""

    def test_granted_capabilities_echo(self) -> None:
        state = WorldState(
            world_revision=Revision(3),
            entities={
                **_full_world().entities,
                OTHER: _entity(OTHER),
            },
        )
        table = CapabilityTable(
            grants=(
                _grant(Capability.OBSERVATION_READ),
                _grant(Capability.WORLD_READ_GLOBAL),
                # 他 actor（OTHER）授权：MEMORY_READ / PHYSICS_RAW——不得混入
                # ACTOR 的回显集
                CapabilityGrant(actor_id=OTHER, capability=Capability.MEMORY_READ),
                CapabilityGrant(actor_id=OTHER, capability=Capability.PHYSICS_RAW),
            )
        )
        ctx = DefaultContextProvider().build(
            _input(state, table, _registry(), _grid_registry(OVERWORLD))
        )
        assert type(ctx.granted_capabilities) is frozenset
        assert ctx.granted_capabilities == frozenset(
            {Capability.OBSERVATION_READ, Capability.WORLD_READ_GLOBAL}
        )
        # == 表内该 actor 授权集（grants_for 口径）
        assert ctx.granted_capabilities == frozenset(
            grant.capability for grant in table.grants_for(ACTOR)
        )
        assert Capability.MEMORY_READ not in ctx.granted_capabilities
        assert Capability.PHYSICS_RAW not in ctx.granted_capabilities
