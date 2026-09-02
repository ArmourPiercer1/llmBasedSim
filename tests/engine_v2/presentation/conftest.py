"""P10 presentation 层测试 fixture（SOT §6.2；4 fixture；零测试函数）。

世界 / 事件 / 脚本本波一次落盘，**跨波不改**（§6.4 fixture 钉；修改 =
勘误登记 + 白名单复核）。

fixture 清单（SOT §6.2 逐项对应）：

- ``fixture_world``：core 面构建 ``WorldState``——2 actor（player/npc
  实体 + 组件）+ 1 location（场景世界标识投影面）+ hex 域 3×3
  （GraphSpace 注册：节点 ``hex_<c>_<r>`` + 16 无向边，参照 P9 A12
  钉值）+ 方格域（GridSpace(3,3) 对照）+ LogicalClock 注入
  （``world_variables.logical_tick`` 世界侧投影；权威时钟 =
  ``RuntimeState.logical_tick``，见 ``make_fixture_runtime``——P1 D-6：
  tick 推进不推进 world_revision，世界侧逻辑刻为已提交世界事实）；
- ``known_event_sequence``：3 次 commit 经 K2 管道驱动（talk 提案 →
  效果 → 事件；move → 事件；属性变更 → 事件）→ world（revision 0→3）
  + 逐 commit 世界元组（revision 2 = 会话 step 后 world_revision，
  §6.4 脚本 base）+ runtime（logical_tick = 3）+ 宿主直构
  trace_records（kind = ACTION_PROPOSAL / PROPOSED_EFFECT /
  AUTHORITY_DECISION / TRANSACTION / DOMAIN_EVENT 五面 × 3，字面量
  record_id 零 uuid4；producer / transaction_id / world_revision 对齐；
  payload 内嵌管道真实 ``model_dump(mode="json")`` 记录）；
- ``script_backend``：``FakeInferenceBackend``（narrator /
  visual_director 脚本键预置；§6.4 钉值：base_revision = Revision(2)
  本文件常量锚定；seq 1-based）；
- ``scene_view``：``derive_scene_view(fixture_world)`` 投影。

纪律（D5/D6/K8）：全部 id / 面值 = 字面量（零随机、零 wall-clock）；
12 名闭集零命中；测试侧模型名 = ``fake-model-1`` 类（A 判据 t2 钉）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

import pytest

from src.engine_v2.core import (
    ActionInstanceId,
    ActionProposal,
    ActionTypeId,
    AuthorityPolicy,
    AuthorityRule,
    AuthoritySelector,
    CauseKind,
    CauseRef,
    CascadeExecutor,
    ComponentRegistry,
    ComponentSchema,
    ComponentTypeId,
    EFFECT_SET_COMPONENT,
    EFFECT_SET_WORLD_VARIABLE,
    EffectId,
    EntityId,
    EntityRecord,
    EntityTarget,
    GraphSpace,
    GridSpace,
    OriginKind,
    ProducerId,
    ProducerInfo,
    ProducerRegistry,
    ProposedEffect,
    Provenance,
    Revision,
    RuntimeState,
    SPACES_COMPONENT,
    SpaceBackend,
    SpaceMapping,
    SpaceRegistry,
    SpatialDomain,
    StateDomainId,
    StateDomainTarget,
    TraceKind,
    TraceRecord,
    TraceRecordId,
    TransactionStatus,
    WorldState,
    ScenarioState,
    default_handler_registry,
    encode_spaces,
    set_logical_tick,
    uninstall_write_barrier,
)
from src.engine_v2.core.snapshot import snapshot
from src.engine_v2.llm.adapter import FakeInferenceBackend
from src.engine_v2.modules.space import HexGrid, hex_adjacency, register_standard_space
from src.engine_v2.persistence.snapshot import (
    dump_persistence_snapshot,
    to_persistence_snapshot,
)
from src.engine_v2.presentation.view import SceneView, derive_scene_view, scene_id_of

__all__ = [
    "P10KnownSequence",
    "make_p10_world",
    "make_fixture_runtime",
    "make_space_registry",
    "world_hash",
    "fixture_world",
    "known_event_sequence",
    "script_backend",
    "scene_view",
]

# —— §6.4 钉死字面量（零随机、零时钟）——

_WSI = "wsi_p10_w1"
_PROJECT_VERSION = "1.0.0"
_HOST_PRODUCER = "p10.host"
_PLAYER_ID = "ent_authoring_player"
_NPC_ID = "ent_authoring_npc"
_LOCATION_ID = "ent_authoring_room"
_HEX_DOMAIN = "hex"
_GRID_DOMAIN = "grid"
_DISPLAY = ComponentTypeId("display")
_ATTRIBUTES = ComponentTypeId("attributes")
_TALK_TEXT = "那座摆锤钟，你还能修好吗？"

#: §6.4 脚本 base_revision = 会话 step 后 world_revision（本文件常量锚定）。
_SCRIPT_BASE_REVISION: Final = Revision(2)

_NARRATOR_SCRIPT_TEXT: Final[str] = (
    "旧钟表铺的灰尘在光柱里缓缓浮动，秒针早已停在十点。"
)

#: visual_director 脚本钉 = rev 2 视图的确定性意图投影（8 字段，
#: SOT §3.3 规范面；subjects/environment 与 ``derive_scene_view`` 对
#: ``known_event_sequence.worlds[1]`` 的投影逐值一致）。
_DIRECTOR_SCRIPT_INTENT: Final[dict[str, object]] = {
    "scene_id": scene_id_of((_LOCATION_ID, _NPC_ID, _PLAYER_ID)),
    "view_revision": 2,
    "subjects": [
        {
            "id": _NPC_ID,
            "name": "小满",
            "position": {"hex": "hex_0_1", "grid": {"x": 0, "y": 1}},
            "mood": "curious",
            "tags": ["actor"],
        },
        {
            "id": _PLAYER_ID,
            "name": "依依",
            "position": {"hex": "hex_2_1", "grid": {"x": 1, "y": 1}},
            "mood": "calm",
            "tags": ["actor"],
        },
    ],
    "environment": {
        "location": "旧钟表铺",
        "description": "柜台上的摆锤钟停在十点。",
        "time_of_day": "上午",
        "weather": "晴朗",
    },
    "camera": {"type": "fixed", "framing": "medium"},
    "mood": "calm",
    "continuity_refs": [],
    "style_refs": [],
}

_DIRECTOR_SCRIPT_TEXT: Final[str] = json.dumps(
    _DIRECTOR_SCRIPT_INTENT, ensure_ascii=False, sort_keys=True
)

#: fixture 世界 actor 规格（字面量；``make_p10_world`` 消费）。
_ACTOR_SPECS: Final[dict[str, dict[str, object]]] = {
    _PLAYER_ID: {
        "class": "player",
        "display": {"name": "依依", "mood": "calm"},
        "hex": "hex_1_1",
        "grid": {"x": 1, "y": 1},
    },
    _NPC_ID: {
        "class": "npc",
        "display": {"name": "小满", "mood": "curious"},
        "hex": "hex_0_1",
        "grid": {"x": 0, "y": 1},
    },
}


def _fail(reason: str) -> None:
    """宿主侧不变量违例（fail-loud；不静默）。"""
    raise RuntimeError(f"p10 conftest 不变量违例：{reason}")


# —— 空间域注册（hex 3×3 + 方格 3×3 对照；P9 A12 16 无向边参照）——


def _hex_nodes() -> list[str]:
    """节点表（col-major；``hex_<c>_<r>``，与 P9 世界构建面同序）。"""
    return [f"hex_{c}_{r}" for c in range(3) for r in range(3)]


def make_space_registry() -> SpaceRegistry:
    """宿主空间注册表（hex = GraphSpace 3×3 odd-r，16 无向边；
    grid = GridSpace(3,3) 对照域；P9 ``register_standard_space`` 冻结
    消费面，测试侧限定）。"""
    entries: dict[str, tuple[SpatialDomain, SpaceBackend]] = {}
    directed = hex_adjacency(HexGrid(cols=3, rows=3))
    edges = sorted({(min(a, b), max(a, b)) for a, b in directed})
    if len(edges) != 16:
        _fail(f"hex 3×3 无向边数 != 16：{len(edges)}")
    register_standard_space(entries, _HEX_DOMAIN, GraphSpace(_hex_nodes(), edges))
    register_standard_space(entries, _GRID_DOMAIN, GridSpace(3, 3))
    return SpaceRegistry(entries)


# —— fixture 世界 / 运行时 / 世界哈希（宿主侧合法构造面）——


def _spaces_payload(hex_position: str, grid_position: dict[str, int]) -> dict:
    """spaces 组件载荷（hex + grid 双域映射；载荷序 = (hex, grid)）。"""
    return encode_spaces(
        (
            SpaceMapping(domain_id=_HEX_DOMAIN, position=hex_position, entered_tick=0),
            SpaceMapping(domain_id=_GRID_DOMAIN, position=grid_position, entered_tick=0),
        )
    )


def make_p10_world(
    *,
    actor_ids: tuple[str, ...] = (_PLAYER_ID, _NPC_ID),
    location_id: str = _LOCATION_ID,
    logical_tick: int = 0,
) -> WorldState:
    """fixture_world 构造器（字面量 id；零随机、零时钟）。

    - 2 actor：``ent_authoring_player``（class player）/
      ``ent_authoring_npc``（class npc），tags = ``["actor"]``，组件 =
      ``display``（name/mood）+ ``attributes``（数值表）+ ``spaces``
      （hex + grid 双域映射）；
    - 1 location：class location，tags = ``["location"]``，display
      （name/description）= 场景世界标识投影面（D-P10-12）；
    - ``world_variables`` = logical_tick（世界侧逻辑刻投影，D-6）/
      game_time（结构化日历时间）/ weather；
    - ``scenario_state`` = scenario_p10_w1 / opening（信封）。
    """
    entities: dict[EntityId, EntityRecord] = {}
    for actor_id in actor_ids:
        spec = _ACTOR_SPECS[actor_id]
        entities[EntityId(actor_id)] = EntityRecord(
            entity_id=EntityId(actor_id),
            entity_class=str(spec["class"]),
            tags=["actor"],
            components={
                _DISPLAY: dict(spec["display"]),
                _ATTRIBUTES: {"attributes": {"energy": 7, "curiosity": 3}},
                SPACES_COMPONENT: _spaces_payload(
                    str(spec["hex"]), dict(spec["grid"])
                ),
            },
        )
    entities[EntityId(location_id)] = EntityRecord(
        entity_id=EntityId(location_id),
        entity_class="location",
        tags=["location"],
        components={
            _DISPLAY: {
                "name": "旧钟表铺",
                "description": "柜台上的摆锤钟停在十点。",
            }
        },
    )
    return WorldState(
        entities=entities,
        world_variables={
            "logical_tick": logical_tick,
            "game_time": {"day": 1, "hour": 10, "minute": 0},
            "weather": "晴朗",
        },
        scenario_state=ScenarioState(scenario_id="scenario_p10_w1", stage="opening"),
    )


def make_fixture_runtime(logical_tick: int = 0) -> RuntimeState:
    """LogicalClock 注入（权威时钟 = ``RuntimeState.logical_tick``，
    P1 D-6 单一单调计数；世界侧投影 = ``world_variables.logical_tick``，
    宿主构造期同刻镜像；tick 推进不推进 world_revision）。"""
    return RuntimeState(logical_tick=logical_tick)


def world_hash(world: WorldState, runtime: RuntimeState) -> str:
    """世界哈希（参照 P9 测试既有 WorldState 哈希 / dump 面：P8 冻结
    快照链 core snapshot → persistence envelope → dump → sha256；
    零臆造）。"""
    core_snapshot = snapshot(
        world, runtime, _WSI, project_version=_PROJECT_VERSION, module_versions={}
    )
    envelope = to_persistence_snapshot(core_snapshot)
    return hashlib.sha256(
        dump_persistence_snapshot(envelope).encode("utf-8")
    ).hexdigest()


# —— K2 管道接线（P8 conftest 同族：通配单规则放行宿主 producer）——


def _component_registry() -> ComponentRegistry:
    """测试侧组件注册表（描述型 schema，不透明 payload；D-8 校验点 (b)）。"""
    registry = ComponentRegistry()
    for component_type, description in (
        (SPACES_COMPONENT, "P10 fixture 世界空间映射组件（不透明 payload）"),
        (_DISPLAY, "P10 fixture 世界展示组件（name/mood/description）"),
        (_ATTRIBUTES, "P10 fixture 世界属性组件（数值表）"),
    ):
        registry.register(
            ComponentSchema(component_type=component_type, description=description)
        )
    return registry


def _producer_registry() -> ProducerRegistry:
    """测试侧 producer 注册表（宿主 producer，origin = scenario 脚本）。"""
    registry = ProducerRegistry()
    registry.register(
        ProducerInfo(
            producer_id=ProducerId(_HOST_PRODUCER),
            origin=OriginKind.SCENARIO,
            priority=100,
            description="P10 已知事件序列宿主 producer",
        )
    )
    return registry


def _policy() -> AuthorityPolicy:
    """测试侧 authority（closed-by-default；通配单规则放行宿主
    producer，P7 gate / P8 conftest 同族，K3）。"""
    return AuthorityPolicy(
        rules=[
            AuthorityRule(
                selector=AuthoritySelector(),
                allowed_writers=[ProducerId(_HOST_PRODUCER)],
                priority=100,
            )
        ]
    )


def _executor() -> CascadeExecutor:
    """K2 管道执行器（SOT 消费面：policy 注入 + 冻结
    ``default_handler_registry()`` + 测试侧组件 / producer 注册表）。"""
    return CascadeExecutor(
        policy=_policy(),
        handlers=default_handler_registry(),
        component_registry=_component_registry(),
        producer_registry=_producer_registry(),
    )


def _host_provenance() -> Provenance:
    """事务 / 提案级 provenance（宿主装配者，origin = scenario）。"""
    return Provenance(producer_id=ProducerId(_HOST_PRODUCER), origin=OriginKind.SCENARIO)


# —— 已知事件序列：3 次 commit 驱动（§6.2）——


@dataclass(frozen=True)
class P10KnownSequence:
    """known_event_sequence 载体（SOT §6.2）。

    - ``world``：3 笔 committed 事务后 ``WorldState``（revision 3）；
    - ``worlds``：逐 commit 后世界元组（revision 1 / 2 / 3；revision 2
      = 会话 step 后 world_revision，§6.4 脚本 base）；
    - ``runtime``：``RuntimeState``（logical_tick = 3，宿主相位每 commit
      推 1 刻；P1 D-6：不推进 world_revision）；
    - ``trace_records``：宿主直构五面记录流（每 commit 5 条，commit 序；
      字面量 record_id；producer / transaction_id / world_revision 对齐）。
    """

    world: WorldState
    worlds: tuple[WorldState, ...]
    runtime: RuntimeState
    trace_records: tuple[TraceRecord, ...]


def _commit_one(
    *,
    executor: CascadeExecutor,
    state: WorldState,
    runtime: RuntimeState,
    record_prefix: str,
    proposal: ActionProposal,
    effect: ProposedEffect,
) -> tuple[WorldState, RuntimeState, list[TraceRecord]]:
    """单 commit 驱动（宿主相位序）：时钟推进（``set_logical_tick``，每
    commit 1 刻）→ K2 管道提交（``CascadeExecutor.run``）→ 宿主直构
    五面 trace 记录（ACTION_PROPOSAL / PROPOSED_EFFECT /
    AUTHORITY_DECISION / TRANSACTION / DOMAIN_EVENT；字面量 record_id，
    零 uuid4；TRANSACTION / DOMAIN_EVENT 内嵌管道真实记录
    ``model_dump(mode="json")``）。"""
    runtime = set_logical_tick(runtime, runtime.logical_tick + 1)
    pre_revision = state.world_revision
    result = executor.run(
        [effect],
        state,
        causal_root_id=str(proposal.proposal_id),
        origin=_host_provenance(),
    )
    committed = [
        txn for txn in result.transactions if txn.status is TransactionStatus.COMMITTED
    ]
    if len(committed) != 1 or len(result.events) != 1:
        _fail(
            f"commit {record_prefix}：期望恰 1 COMMITTED 事务 + 1 事件，"
            f"实际 committed={len(committed)} events={len(result.events)}"
        )
    txn = committed[0]
    event = result.events[0]
    if txn.commit_revision != pre_revision.next():
        _fail(f"commit {record_prefix}：commit_revision 不连续（Spec §9）")
    state = result.final_state
    records = [
        TraceRecord(
            record_id=TraceRecordId(f"{record_prefix}_proposal"),
            kind=TraceKind.ACTION_PROPOSAL,
            world_revision=pre_revision,
            producer_id=ProducerId(_HOST_PRODUCER),
            payload={"record": proposal.model_dump(mode="json")},
        ),
        TraceRecord(
            record_id=TraceRecordId(f"{record_prefix}_effect"),
            kind=TraceKind.PROPOSED_EFFECT,
            world_revision=pre_revision,
            producer_id=ProducerId(_HOST_PRODUCER),
            payload={"record": effect.model_dump(mode="json")},
        ),
        TraceRecord(
            record_id=TraceRecordId(f"{record_prefix}_authority"),
            kind=TraceKind.AUTHORITY_DECISION,
            world_revision=pre_revision,
            producer_id=ProducerId(_HOST_PRODUCER),
            payload={
                "effect_id": str(effect.effect_id),
                "decision": "allow",
                "reason": "host 规则：p10.host 闭集放行",
            },
        ),
        TraceRecord(
            record_id=TraceRecordId(f"{record_prefix}_txn"),
            kind=TraceKind.TRANSACTION,
            world_revision=txn.commit_revision,
            producer_id=ProducerId(_HOST_PRODUCER),
            transaction_id=txn.transaction_id,
            payload={"record": txn.model_dump(mode="json")},
        ),
        TraceRecord(
            record_id=TraceRecordId(f"{record_prefix}_event"),
            kind=TraceKind.DOMAIN_EVENT,
            world_revision=event.world_revision,
            producer_id=event.source_system,
            transaction_id=txn.transaction_id,
            payload={"record": event.model_dump(mode="json")},
        ),
    ]
    return state, runtime, records


def _run_known_sequence(world: WorldState) -> P10KnownSequence:
    """3 次 commit 驱动（SOT §6.2 逐字）：talk 提案 → 效果 → 事件；
    move → 事件；属性变更 → 事件。world_revision 0→3，逐 commit 世界
    元组（revision 2 = 会话 step 后 world_revision，§6.4 脚本 base）。"""
    executor = _executor()
    state = world
    runtime = make_fixture_runtime(0)
    records: list[TraceRecord] = []
    worlds: list[WorldState] = []

    # —— commit 1：talk 提案 → 效果 → 事件（revision 0 → 1）——
    state, runtime, commit_records = _commit_one(
        executor=executor,
        state=state,
        runtime=runtime,
        record_prefix="trc_p10_c1",
        proposal=ActionProposal(
            proposal_id=ActionInstanceId("act_p10_talk"),
            actor_id=EntityId(_PLAYER_ID),
            action_id=ActionTypeId("talk"),
            arguments={"target": _NPC_ID, "text": _TALK_TEXT},
            intent="问候并询问摆锤钟",
            base_world_revision=Revision(0),
            provenance=_host_provenance(),
        ),
        effect=ProposedEffect(
            effect_id=EffectId("eff_p10_talk_1"),
            effect_type=EFFECT_SET_WORLD_VARIABLE,
            source=ProducerId(_HOST_PRODUCER),
            target=StateDomainTarget(domain=StateDomainId("world_variables")),
            payload={
                "key": "last_dialogue",
                "value": {"speaker": _PLAYER_ID, "text": _TALK_TEXT},
            },
            base_revision=Revision(0),
            cause_ids=[CauseRef(kind=CauseKind.PROPOSAL, ref_id="act_p10_talk")],
        ),
    )
    worlds.append(state)
    records.extend(commit_records)

    # —— commit 2：move → 事件（revision 1 → 2；hex 域 hex_1_1 → hex_2_1）——
    state, runtime, commit_records = _commit_one(
        executor=executor,
        state=state,
        runtime=runtime,
        record_prefix="trc_p10_c2",
        proposal=ActionProposal(
            proposal_id=ActionInstanceId("act_p10_move"),
            actor_id=EntityId(_PLAYER_ID),
            action_id=ActionTypeId("move"),
            arguments={"from": "hex_1_1", "to": "hex_2_1"},
            intent="走向里间",
            base_world_revision=Revision(1),
            provenance=_host_provenance(),
        ),
        effect=ProposedEffect(
            effect_id=EffectId("eff_p10_move_1"),
            effect_type=EFFECT_SET_COMPONENT,
            source=ProducerId(_HOST_PRODUCER),
            target=EntityTarget(
                entity_id=EntityId(_PLAYER_ID), component_type=SPACES_COMPONENT
            ),
            payload=_spaces_payload("hex_2_1", {"x": 1, "y": 1}),
            base_revision=Revision(1),
            cause_ids=[CauseRef(kind=CauseKind.PROPOSAL, ref_id="act_p10_move")],
        ),
    )
    worlds.append(state)
    records.extend(commit_records)

    # —— commit 3：属性变更 → 事件（revision 2 → 3；npc 属性表变更）——
    state, runtime, commit_records = _commit_one(
        executor=executor,
        state=state,
        runtime=runtime,
        record_prefix="trc_p10_c3",
        proposal=ActionProposal(
            proposal_id=ActionInstanceId("act_p10_attribute"),
            actor_id=EntityId(_NPC_ID),
            action_id=ActionTypeId("attribute_update"),
            arguments={"target": _NPC_ID, "changes": {"energy": 6, "curiosity": 5}},
            intent="交谈后状态微调",
            base_world_revision=Revision(2),
            provenance=_host_provenance(),
        ),
        effect=ProposedEffect(
            effect_id=EffectId("eff_p10_attribute_1"),
            effect_type=EFFECT_SET_COMPONENT,
            source=ProducerId(_HOST_PRODUCER),
            target=EntityTarget(entity_id=EntityId(_NPC_ID), component_type=_ATTRIBUTES),
            payload={"attributes": {"energy": 6, "curiosity": 5}},
            base_revision=Revision(2),
            cause_ids=[CauseRef(kind=CauseKind.PROPOSAL, ref_id="act_p10_attribute")],
        ),
    )
    worlds.append(state)
    records.extend(commit_records)

    if state.world_revision != Revision(3):
        _fail(f"known_event_sequence 终态 revision != 3：{state.world_revision}")
    return P10KnownSequence(
        world=state,
        worlds=tuple(worlds),
        runtime=runtime,
        trace_records=tuple(records),
    )


# —— 4 fixture（SOT §6.2；一经落盘跨波不改，§6.4）——


@pytest.fixture(autouse=True)
def _barrier_isolation() -> Iterator[None]:
    """写屏障 opt-in 纪律（P7 gate L113–118 / P8 conftest 同形）：
    CascadeExecutor 构造即武装屏障，测试前后各还原一次全局未武装态。"""
    uninstall_write_barrier()
    yield
    uninstall_write_barrier()


@pytest.fixture
def fixture_world() -> WorldState:
    """core 面构建 WorldState（SOT §6.2）：2 actor（player/npc 实体 +
    组件）+ 1 location（场景世界标识投影面）+ hex 域 3×3（16 无向边，
    P9 A12 钉值参照）+ 方格域 GridSpace(3,3)（对照）+ LogicalClock 注入
    （``world_variables.logical_tick`` 世界侧投影；权威时钟 =
    ``make_fixture_runtime`` 的 ``RuntimeState.logical_tick``）。"""
    return make_p10_world()


@pytest.fixture
def known_event_sequence(fixture_world: WorldState) -> P10KnownSequence:
    """3 次 commit 经 K2 管道驱动（talk 提案 → 效果 → 事件；move →
    事件；属性变更 → 事件）→ world（revision 3）+ 逐 commit 世界元组 +
    runtime（logical_tick 3）+ 宿主直构 trace_records（五面 × 3，
    producer / transaction_id / world_revision 对齐，§6.2）。"""
    return _run_known_sequence(fixture_world)


@pytest.fixture
def script_backend(fixture_world: WorldState) -> FakeInferenceBackend:
    """FakeInferenceBackend（narrator / visual_director 脚本键预置；
    §6.4 脚本钉：base_revision = 会话 step 后 world_revision =
    Revision(2)，本文件常量锚定；seq 1-based；测试侧模型名 =
    ``fake-model-1`` 类，K5 零真实推理）。"""
    intent = json.loads(_DIRECTOR_SCRIPT_TEXT)
    if intent["scene_id"] != derive_scene_view(fixture_world)["scene_id"]:
        _fail("script 钉 scene_id 与 fixture 世界派生 scene_id 不一致")
    if intent["view_revision"] != int(_SCRIPT_BASE_REVISION):
        _fail("script 钉 view_revision 与 _SCRIPT_BASE_REVISION 不一致")
    return FakeInferenceBackend(
        script={
            ("narrator", _SCRIPT_BASE_REVISION, 1): _NARRATOR_SCRIPT_TEXT,
            ("visual_director", _SCRIPT_BASE_REVISION, 1): _DIRECTOR_SCRIPT_TEXT,
        }
    )


@pytest.fixture
def scene_view(fixture_world: WorldState) -> SceneView:
    """``derive_scene_view(fixture_world)`` 投影（SOT §6.2）。"""
    return derive_scene_view(fixture_world)
