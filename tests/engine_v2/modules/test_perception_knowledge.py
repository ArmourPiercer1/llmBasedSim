"""P9 W3 perception / knowledge 模块单测（SOT §6.1：t1–t7 共 7 函数；
T06 + T10 回归）。

设计依据 = ``docs/v2/contracts/P9-official-modules-migration-design.md``
§3.6 / §3.7（函数级锚表）+ §6.1（测试表 L1556–1566）+ §1（P9-INV-7
感知局部性）+ §3.7（T10 回归面）。

T10 回归面（t6）：世界事件发生（宿主注入事件流）后，界外 NPC 的
KNOWLEDGE / MEMORY 组件逐字节不变——v1 对照行为 = 全员 memory 注入
``event_log[-10:]``（src/graph/game_graph.py:553–561，cap 50，:559），
v2 期望差 = 本条钉死（43.2-6 移除；P9-INV-7：``build_observations``
签名零事件输入 + ``apply_observations`` 空记录零变更）。

零 fixture 引用（纯 stdlib 数据面，W3 派工决定）；全部入参 = 本地
字面量构造，不引用 conftest fixture。

覆盖项（每项独立 test 函数）：

1. t1_sight_in_radius：半径内实体 → ObservationRecord（sight 分类；
   双半径同中 2 记录面 + 自排除 + 无位置不可感知（实体/观察者侧）
   + payload/observation_id/排序逐字钉）；
2. t2_sight_out_of_radius：界外零记录（hearing 同界外时 records = ()
   钉）；
3. t3_hearing_only：听觉半径单独命中（sight 界外 + hearing 界内 →
   恰 1 条 hearing 记录钉）；
4. t4_belief_update：``apply_observations`` → Belief 集新增（字段钉 +
   强化面 + last_updated_tick 面 + 事件钉 + 入参零修改 K2 + 强化
   value 更新 + 空 observed_entity_ids 跳过 + predicate 回退面）；
5. t5_memory_cap：``memory_append`` cap=50 丢弃最旧（v1 :559 对齐；
   默认 cap 面 + 显式 cap 面 + 保时序面）；
6. t6_no_global_event_leak：T10 回归（encode_knowledge JSON 序列化
   哈希前后不变 + memory tuple 不变；v1 对照锚注释注明）；
7. t7_knowledge_summary：prompt 文本确定性（同输入两次同串 + 空集面
   + 排序钉 + 格式逐字钉）。
"""

from __future__ import annotations

import hashlib
import inspect
import json

from src.engine_v2.core.ids import ObservationId
from src.engine_v2.core.knowledge import (
    Belief,
    BeliefKind,
    KnowledgeState,
    ObservationRecord,
    encode_knowledge,
)
from src.engine_v2.modules.knowledge import (
    BeliefEvent,
    apply_observations,
    knowledge_summary,
    memory_append,
)
from src.engine_v2.modules.perception import (
    ObservationSource,
    PerceptionRange,
    PerceptionResult,
    build_observations,
)


def _sha256(payload: dict[str, object]) -> str:
    """encode_knowledge 载荷 → 规范 JSON sha256（逐字节不变判定面）。"""
    blob = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def test_perception_knowledge_t1_sight_in_radius() -> None:
    """1) 半径内实体 → ObservationRecord（sight 分类；payload /
    observation_id / 排序逐字钉）。"""
    world_positions = {
        "npc_1": {"x": 0, "y": 0},
        "npc_2": {"x": 3, "y": 4},
        "npc_3": {"x": 0, "y": 2},
    }
    observers = {
        "npc_1": PerceptionRange(sight_m=10.0, hearing_m=5.0),
        "npc_3": PerceptionRange(sight_m=10.0, hearing_m=5.0),
        # 在 observers 而 world_positions 无位置 → 该观察者零记录
        # （v1 ref_pos 守卫面，game_graph.py:72–73）。
        "npc_5": PerceptionRange(sight_m=10.0, hearing_m=5.0),
    }
    entities = {
        "npc_1": {"name": "npc_1"},
        "npc_2": {"name": "npc_2"},
        "npc_3": {"name": "npc_3"},
        # 在 entities 而 world_positions 无位置 → 不可感知（零记录）。
        "npc_4": {"name": "npc_4"},
    }
    source = ObservationSource(
        observer_id="npc_1", domain="main_room", tick=3,
    )
    result = build_observations(
        world_positions, observers, entities, source,
    )
    assert result.source == source
    # 全序 (observer_id, entity_id, kind) 升序，7 条 observation_id
    # 逐字钉（双半径同中 = 每感官各 1 条；hearing < sight 字母序）。
    assert [r.observation_id for r in result.records] == [
        "obs_npc_1_npc_2_sight_3",
        "obs_npc_1_npc_3_hearing_3",
        "obs_npc_1_npc_3_sight_3",
        "obs_npc_3_npc_1_hearing_3",
        "obs_npc_3_npc_1_sight_3",
        "obs_npc_3_npc_2_hearing_3",
        "obs_npc_3_npc_2_sight_3",
    ]
    rec_1, rec_2, rec_3, rec_4, rec_5, rec_6, rec_7 = result.records
    # 记录字段逐字钉（JSON-native 最小 payload 面）。
    assert rec_1.actor_id == "npc_1"
    assert rec_1.tick == 3
    assert rec_1.payload == {
        "kind": "sight", "entity_id": "npc_2", "distance_m": 7,
    }
    assert rec_1.observed_entity_ids == ("npc_2",)
    assert rec_1.cause_event_id is None
    # 距离值钉（曼哈顿 L1：3+4=7 / 0+2=2 / 3+2=5）。
    assert rec_2.payload["distance_m"] == 2
    assert rec_3.payload["distance_m"] == 2
    assert rec_4.payload["distance_m"] == 2
    assert rec_5.payload["distance_m"] == 2
    assert rec_6.payload["distance_m"] == 5
    assert rec_7.payload["distance_m"] == 5
    # kind 分类钉：同 (观察者, 实体) 双中 = 2 条记录（每感官各 1）。
    assert rec_2.payload["kind"] == "hearing"
    assert rec_3.payload["kind"] == "sight"
    assert rec_6.payload["kind"] == "hearing"
    assert rec_7.payload["kind"] == "sight"
    # 自排除 + 无位置不可感知：零自我记录、零 npc_4 记录。
    assert all(
        r.observed_entity_ids != (r.actor_id,) for r in result.records
    )
    assert all(
        "npc_4" not in r.observed_entity_ids for r in result.records
    )
    # 观察者无位置面：npc_5 在 observers 而 world_positions 无位置 →
    # 该观察者零记录（v1 ref_pos 守卫 game_graph.py:72–73）。
    assert all(r.actor_id != "npc_5" for r in result.records)


def test_perception_knowledge_t2_sight_out_of_radius() -> None:
    """2) 界外零记录（hearing 同界外时 records = () 钉）。"""
    world_positions = {
        "npc_far": {"x": 40, "y": 0},
        "player_1": {"x": 0, "y": 0},
    }
    observers = {
        "npc_far": PerceptionRange(sight_m=10.0, hearing_m=5.0),
    }
    entities = {
        "npc_far": {"name": "npc_far"},
        "player_1": {"name": "player_1"},
    }
    source = ObservationSource(
        observer_id="npc_far", domain="main_room", tick=9,
    )
    result = build_observations(
        world_positions, observers, entities, source,
    )
    # 曼哈顿距离 40 > 10（sight 界外）且 > 5（hearing 界外）→ 零记录。
    assert result.records == ()
    assert result.source == source


def test_perception_knowledge_t3_hearing_only() -> None:
    """3) 听觉半径单独命中（kind 分类面：sight 界外 + hearing 界内
    → 恰 1 条 hearing 记录钉）。"""
    world_positions = {
        "npc_1": {"x": 0, "y": 0},
        "npc_2": {"x": 0, "y": 8},
    }
    observers = {
        "npc_1": PerceptionRange(sight_m=5.0, hearing_m=10.0),
    }
    entities = {
        "npc_1": {"name": "npc_1"},
        "npc_2": {"name": "npc_2"},
    }
    source = ObservationSource(
        observer_id="npc_1", domain="main_room", tick=5,
    )
    result = build_observations(
        world_positions, observers, entities, source,
    )
    # 距离 8：> 5（sight 界外）且 <= 10（hearing 界内）→ 恰 1 条。
    assert len(result.records) == 1
    (rec,) = result.records
    assert rec.observation_id == "obs_npc_1_npc_2_hearing_5"
    assert rec.actor_id == "npc_1"
    assert rec.tick == 5
    assert rec.payload == {
        "kind": "hearing", "entity_id": "npc_2", "distance_m": 8,
    }
    assert rec.observed_entity_ids == ("npc_2",)
    assert rec.cause_event_id is None


def test_perception_knowledge_t4_belief_update() -> None:
    """4) apply_observations → Belief 集新增（字段钉 + 强化面 +
    last_updated_tick 面 + 事件钉 + 入参零修改 K2）。"""
    rec_b = ObservationRecord(
        observation_id=ObservationId("obs_t4_b"),
        actor_id="npc_1",
        tick=5,
        payload={"kind": "hearing", "entity_id": "npc_3", "distance_m": 2},
        observed_entity_ids=("npc_3",),
        cause_event_id=None,
    )
    rec_a = ObservationRecord(
        observation_id=ObservationId("obs_t4_a"),
        actor_id="npc_1",
        tick=3,
        payload={"kind": "sight", "entity_id": "npc_2", "distance_m": 7},
        observed_entity_ids=("npc_2",),
        cause_event_id=None,
    )
    # 记录序刻意 (rec_b, rec_a)：belief 插入位 = (subject, predicate)
    # 全序（与到达序无关）；事件序 = record 处理序。
    result1 = PerceptionResult(
        source=ObservationSource(
            observer_id="npc_1", domain="main_room", tick=5,
        ),
        records=(rec_b, rec_a),
    )
    k0 = KnowledgeState(beliefs=(), last_updated_tick=0)
    k0_before = encode_knowledge(k0)
    k1, ev1 = apply_observations(k0, result1)
    # 新增字段钉（2 belief，(subject, predicate) 升序全序）。
    assert k1 is not k0
    assert k1.beliefs == (
        Belief(
            kind=BeliefKind.FACT,
            subject="npc_2",
            predicate="sight",
            value={"kind": "sight", "entity_id": "npc_2", "distance_m": 7},
            confidence=0.5,
            formed_tick=3,
            origin_event_id=None,
        ),
        Belief(
            kind=BeliefKind.FACT,
            subject="npc_3",
            predicate="hearing",
            value={"kind": "hearing", "entity_id": "npc_3", "distance_m": 2},
            confidence=0.5,
            formed_tick=5,
            origin_event_id=None,
        ),
    )
    # last_updated_tick = 变更 record 的 tick 最大值（3 / 5 → 5）。
    assert k1.last_updated_tick == 5
    # 事件钉（序 = record 处理序：rec_b 先，rec_a 后）。
    assert ev1 == (
        BeliefEvent(
            actor_id="npc_1",
            kind=BeliefKind.FACT,
            subject="npc_3",
            text="npc_1 观察到 npc_3 (hearing)",
            tick=5,
        ),
        BeliefEvent(
            actor_id="npc_1",
            kind=BeliefKind.FACT,
            subject="npc_2",
            text="npc_1 观察到 npc_2 (sight)",
            tick=3,
        ),
    )
    # 强化面：同 (subject, predicate) 再观察 → min(1.0, 0.5+0.1)，
    # formed_tick 不改；last_updated_tick = 变更 tick 最大值（4）。
    k1_before = encode_knowledge(k1)
    rec_a2 = ObservationRecord(
        observation_id=ObservationId("obs_t4_a2"),
        actor_id="npc_1",
        tick=4,
        # distance_m 刻意 ≠ 首记录（7 → 9）：value 更新断言可区分。
        payload={"kind": "sight", "entity_id": "npc_2", "distance_m": 9},
        observed_entity_ids=("npc_2",),
        cause_event_id=None,
    )
    result2 = PerceptionResult(
        source=ObservationSource(
            observer_id="npc_1", domain="main_room", tick=4,
        ),
        records=(rec_a2,),
    )
    k2, ev2 = apply_observations(k1, result2)
    assert k2 is not k1
    assert k2.beliefs[0].confidence == 0.6
    assert k2.beliefs[0].formed_tick == 3
    assert k2.beliefs[1] == k1.beliefs[1]
    assert k2.last_updated_tick == 4
    assert ev2 == (
        BeliefEvent(
            actor_id="npc_1",
            kind=BeliefKind.FACT,
            subject="npc_2",
            text="npc_1 观察到 npc_2 (sight)",
            tick=4,
        ),
    )
    # K2：入参零修改（encode_knowledge 字节等同复查）。
    assert encode_knowledge(k0) == k0_before
    assert encode_knowledge(k1) == k1_before
    # 强化时 value 更新为最新 record payload（delegated 面；rec_a2
    # distance_m=9 ≠ 首记录 7，断言可区分）。
    assert k2.beliefs[0].value == {
        "kind": "sight", "entity_id": "npc_2", "distance_m": 9,
    }
    # observed_entity_ids 空 → 确定性跳过（零 belief 零事件；delegated
    # 面）。
    rec_empty = ObservationRecord(
        observation_id=ObservationId("obs_t4_empty"),
        actor_id="npc_1",
        tick=7,
        payload={"distance_m": 1},
        observed_entity_ids=(),
        cause_event_id=None,
    )
    result3 = PerceptionResult(
        source=ObservationSource(
            observer_id="npc_1", domain="main_room", tick=7,
        ),
        records=(rec_empty,),
    )
    k3, ev3 = apply_observations(k2, result3)
    assert k3.beliefs == k2.beliefs
    assert k3.last_updated_tick == k2.last_updated_tick
    assert ev3 == ()
    # predicate 回退面：payload 缺 "kind" 键 → predicate = "observation"
    # （delegated 面）。
    rec_fk = ObservationRecord(
        observation_id=ObservationId("obs_t4_fk"),
        actor_id="npc_1",
        tick=8,
        payload={"distance_m": 3},
        observed_entity_ids=("npc_9",),
        cause_event_id=None,
    )
    result4 = PerceptionResult(
        source=ObservationSource(
            observer_id="npc_1", domain="main_room", tick=8,
        ),
        records=(rec_fk,),
    )
    k4, ev4 = apply_observations(k3, result4)
    assert len(k4.beliefs) == 3
    assert k4.beliefs[2] == Belief(
        kind=BeliefKind.FACT,
        subject="npc_9",
        predicate="observation",
        value={"distance_m": 3},
        confidence=0.5,
        formed_tick=8,
        origin_event_id=None,
    )
    assert k4.last_updated_tick == 8
    assert ev4 == (
        BeliefEvent(
            actor_id="npc_1",
            kind=BeliefKind.FACT,
            subject="npc_9",
            text="npc_1 观察到 npc_9 (observation)",
            tick=8,
        ),
    )


def test_perception_knowledge_t5_memory_cap() -> None:
    """5) memory_append cap=50 丢弃最旧（v1 :559 对齐；默认 cap 面 +
    显式 cap 面 + 保时序面）。"""
    # v1 :559–560 语义对齐：满 50 追加 → 保留最新 50（丢最旧 e0）。
    full = tuple(f"e{i}" for i in range(50))
    assert memory_append(full, "e50") == tuple(f"e{i}" for i in range(1, 51))
    # 默认 cap 面：49 + 1 = 50，零丢弃。
    almost = tuple(f"e{i}" for i in range(49))
    assert memory_append(almost, "e49") == tuple(f"e{i}" for i in range(50))
    # 显式 cap 面。
    short = memory_append(("a", "b"), "c", cap=3)
    assert short == ("a", "b", "c")
    assert memory_append(short, "d", cap=3) == ("b", "c", "d")
    # 保时序面（tuple 追加，不 sorted）。
    assert memory_append(("z", "a"), "m", cap=3) == ("z", "a", "m")
    # cap <= 0 退化面 → 零元组。
    assert memory_append(("a",), "b", cap=0) == ()


def test_perception_knowledge_t6_no_global_event_leak() -> None:
    """6) T10 回归：事件发生后界外 NPC KNOWLEDGE / MEMORY 逐字节不变。

    v1 对照行为 = ``event_log[-10:]`` 注入全员 character memory
    （src/graph/game_graph.py:553–561，cap 50，:559）；v2 期望差 =
    本条钉死（43.2-6 移除；P9-INV-7 模块侧保证：
    ``build_observations`` 签名零事件输入 + ``apply_observations``
    空记录零变更）。
    """
    # P9-INV-7 签名级面：零 event_log / 全局状态入参。
    params = inspect.signature(build_observations).parameters
    assert "event_log" not in params
    assert "state" not in params
    world_positions = {
        "player_1": {"x": 0, "y": 0},
        "npc_far": {"x": 100, "y": 100},
    }
    entities = {
        "player_1": {"name": "player_1"},
        "npc_far": {"name": "npc_far"},
    }
    observers = {
        "npc_far": PerceptionRange(sight_m=10.0, hearing_m=5.0),
    }
    source = ObservationSource(
        observer_id="npc_far", domain="main_room", tick=11,
    )
    # 界外 NPC 既有 KNOWLEDGE 组件物化（非空面；距离 200 远超半径）。
    state_before = KnowledgeState(
        beliefs=(
            Belief(
                kind=BeliefKind.FACT,
                subject="npc_near",
                predicate="sight",
                value={
                    "kind": "sight", "entity_id": "npc_near", "distance_m": 2,
                },
                confidence=0.6,
                formed_tick=4,
                origin_event_id=None,
            ),
        ),
        last_updated_tick=4,
    )
    # MEMORY 组件物化（v1 cap 50 保时序 tuple，满额面）。
    memory_before = tuple(f"mem_{i}" for i in range(50))
    # 宿主侧世界事件流：v1 此刻会 event_log[-10:] 注入全员 memory
    # （game_graph.py:553 / :558）；v2 签名零事件输入，此流不可达。
    event_log = [f"event_{i}" for i in range(10)]
    before_hash = _sha256(encode_knowledge(state_before))
    # v2 感知路径：界外 → 零记录。
    result = build_observations(
        world_positions, observers, entities, source,
    )
    assert result.records == ()
    # v2 知识路径：空记录 → 零变更 + 零事件。
    state_after, events = apply_observations(state_before, result)
    assert events == ()
    # KNOWLEDGE：encode_knowledge（core:165）JSON 序列化哈希前后不变。
    assert _sha256(encode_knowledge(state_after)) == before_hash
    assert encode_knowledge(state_after) == encode_knowledge(state_before)
    # MEMORY：零观察 → 零条目 → memory tuple 不变（v1 此刻会
    # mem.extend(event_log[-10:])，:558）+ 事件文本零泄漏。
    memory_after = memory_before
    for record in result.records:
        memory_after = memory_append(memory_after, str(record.observation_id))
    assert memory_after == memory_before
    assert not any(entry in memory_after for entry in event_log)


def test_perception_knowledge_t7_knowledge_summary() -> None:
    """7) prompt 文本确定性（同输入两次同串 + 空集面 + 排序钉 +
    格式逐字钉）。"""
    b_sight = Belief(
        kind=BeliefKind.FACT,
        subject="npc_2",
        predicate="sight",
        value={"kind": "sight", "entity_id": "npc_2", "distance_m": 7},
        confidence=0.5,
        formed_tick=3,
        origin_event_id=None,
    )
    b_hearing = Belief(
        kind=BeliefKind.FACT,
        subject="npc_3",
        predicate="hearing",
        value={"distance_m": 2, "kind": "hearing", "entity_id": "npc_3"},
        confidence=0.6,
        formed_tick=5,
        origin_event_id=None,
    )
    # 载荷序刻意倒置：摘要 = (subject, predicate) 规范序（与载荷序
    # 无关，排序钉）。
    state = KnowledgeState(
        beliefs=(b_hearing, b_sight), last_updated_tick=5,
    )
    text = knowledge_summary(state, "npc_1")
    # 格式逐字钉（value = 规范 JSON；confidence :g 格式；"; " 连接）。
    assert text == (
        "knowledge[npc_1]: "
        'npc_2=sight={"distance_m":7,"entity_id":"npc_2","kind":"sight"}:0.5; '
        'npc_3=hearing={"distance_m":2,"entity_id":"npc_3","kind":"hearing"}:0.6'
    )
    # 同输入两次同串（确定性）。
    assert knowledge_summary(state, "npc_1") == text
    # 标签槽面：actor_id 只改标签段，条目段不变。
    assert knowledge_summary(state, "other_label") == text.replace(
        "knowledge[npc_1]:", "knowledge[other_label]:", 1,
    )
    # 空集面。
    empty = KnowledgeState(beliefs=(), last_updated_tick=0)
    assert knowledge_summary(empty, "ghost") == "knowledge[ghost]: (空)"
