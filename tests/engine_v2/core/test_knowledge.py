"""P4-T04 单元测试：knowledge 模块（设计文档 §3.6 全量 + §6.1 L1653 + 口径行 L331）。

依据 ``docs/v2/contracts/P4-actor-context-space-mode-design.md``（下称"设计文档"）：

- §3.6（L263-332，含代码块与不变量，字段级权威）：11 导出——
  ``BeliefKind`` / ``Belief``（七字段，含 ``formed_tick``）/ ``KnowledgeState``（临时
  物化视图，D-P4-04 不持久化自身）/ ``ObservationRecord``（OBS-INV-1）/ 三组件槽位
  常量 / 两对编解码纯函数（载荷 raw，不持久化）；
- 单测口径行 L331：Belief confidence 越界拒绝（含 0/1 边界）；OBS-INV-1 重复 id
  拒绝；四个编解码 roundtrip 全等（encode→decode→encode 字节级）；畸形载荷 →
  ``ValidationError``（不静默、不降级）；``reference_entity_ids`` 去重与
  ``beliefs_about`` 序；
- §6.1 表格 L1653：OBS-INV-1（observation_id 唯一）；两对编解码往返（含 confidence
  边界 0/1）；Belief kind ∈ {FACT, RUMOR}（D-P4-09）；reference_entity_ids /
  beliefs_about 一致性；Memory 原始 JsonValue 列表（无 codec，D-P4-09）；三组件
  常量（OBSERVATIONS/KNOWLEDGE/MEMORY_COMPONENT）；
- D-P4-09（L912-923）：Belief kind×confidence 承载 uncertainty（不设第三种
  kind）；Memory = ``list[JsonValue]`` 原始列表，无编解码器，P4 只透传；
- D-P4-17（错误分类法）：本模块不定义新错误类型——一切构造期拒绝统一走 pydantic
  ``ValidationError``（ValueError 族）。

覆盖项（G1，逐项落位）：

1. Belief confidence 越界拒绝：``<0`` 与 ``>1`` 拒绝；``0``/``1`` 边界接受
   （``test_belief_confidence_below_zero_rejected`` /
   ``test_belief_confidence_above_one_rejected`` /
   ``test_belief_confidence_boundaries_zero_and_one_accepted``）；
2. OBS-INV-1：``observed_entity_ids`` 重复 → 拒绝（构造期与 model_validate/decode
   两路径，``test_observation_record_duplicate_observed_entity_ids_rejected`` /
   ``test_decode_observations_duplicate_observed_entity_ids_rejected``）；
3. 四个编解码 roundtrip 全等（"四个" = 两对 × encode/decode 方向全覆盖）：
   ``encode_observations→decode_observations`` 与 ``encode_knowledge→
   decode_knowledge``，encode→decode→encode 字节级（``test_observations_codec_*``
   / ``test_knowledge_codec_*``）；
4. 畸形载荷 → ``ValidationError``（不静默、不降级：缺字段 / 错类型 / 多余字段，
   ``test_decode_observations_*_rejected`` / ``test_decode_knowledge_*_rejected``）；
5. ``reference_entity_ids`` 去重 + ``beliefs_about`` 序（§3.6 代码块语义：载荷序，
   非排序——``test_reference_entity_ids_*`` / ``test_beliefs_about_*``）；
6. §6.1：Belief kind ∈ {FACT, RUMOR}（D-P4-09，其他 kind 拒绝）；Memory 原始
   JsonValue 列表（无 codec，按 §3.6 实际面断言）；三组件常量值（
   ``test_belief_seven_field_contract`` / ``test_belief_kind_vocab_fact_rumor_only`` /
   ``test_memory_payload_raw_json_values_no_codec`` /
   ``test_component_constant_values`` / ``test_module_exports_exactly_eleven_symbols``）。

错误类型口径（pytest.raises 断言的实际类型，以源码为准）：源码四个编解码函数与
``ObservationRecord`` 的 ``_check_observed_entity_ids_unique``（model_validator
mode="after"，内部抛裸 ``ValueError``，被 pydantic v2 统一包装为
``ValidationError``）+ ``Belief`` 的 ``Field(ge=0.0, le=1.0)`` / ``Field(ge=0)``
约束——对外可见类型一律是 pydantic ``ValidationError``（模块 docstring D-P4-17：
不吞、不降级、无模块自定错误类型）。

全部用例无网络、无 LLM、无 API key。
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

import src.engine_v2.core.knowledge as knowledge_mod
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.events import EventTypeId
from src.engine_v2.core.ids import EntityId, ObservationId
from src.engine_v2.core.knowledge import (
    KNOWLEDGE_COMPONENT,
    MEMORY_COMPONENT,
    OBSERVATIONS_COMPONENT,
    Belief,
    BeliefKind,
    KnowledgeState,
    ObservationRecord,
    decode_knowledge,
    decode_observations,
    encode_knowledge,
    encode_observations,
)


# —— 构造助手（确定性 ID 构造，ids.py 设计文档 §2.2 测试口径同款）——


def _belief(
    subject: str = "ent_s",
    predicate: str = "knows",
    value: object = "v",
    kind: BeliefKind = BeliefKind.FACT,
    confidence: float = 0.5,
    formed_tick: int = 0,
    origin_event_id: EventTypeId | None = None,
) -> Belief:
    """一条合法 Belief（七字段全给，越界/词表测试只改单维）。"""
    return Belief(
        kind=kind,
        subject=subject,
        predicate=predicate,
        value=value,  # type: ignore[arg-type]
        confidence=confidence,
        formed_tick=formed_tick,
        origin_event_id=origin_event_id,
    )


def _record(
    observation_id: str = "obs_991",
    actor_id: str = "ent_actor",
    tick: int = 0,
    payload: dict[str, object] | None = None,
    observed_entity_ids: tuple[EntityId, ...] = (),
    cause_event_id: EventTypeId | None = None,
) -> ObservationRecord:
    """一条合法 ObservationRecord（OBS-INV-1 默认满足）。"""
    return ObservationRecord(
        observation_id=ObservationId(observation_id),
        actor_id=EntityId(actor_id),
        tick=tick,
        payload=dict(payload) if payload is not None else {},
        observed_entity_ids=observed_entity_ids,
        cause_event_id=cause_event_id,
    )


def _canonical(obj: object) -> str:
    """字节级比较口径：json.dumps sort_keys（口径行 L331：json 允许）。"""
    return json.dumps(obj, sort_keys=True)


def _ordered_state() -> KnowledgeState:
    """载荷序刻意非字母序的三 belief 状态（zeta 先于 alpha；zeta 重复）。"""
    return KnowledgeState(
        beliefs=(
            _belief(subject="zeta", predicate="p_first", value=1, formed_tick=1),
            _belief(kind=BeliefKind.RUMOR, subject="alpha", predicate="p_two", value=2, formed_tick=2),
            _belief(kind=BeliefKind.RUMOR, subject="zeta", predicate="p_third", value=3, formed_tick=3),
        ),
        last_updated_tick=7,
    )


# —— 覆盖项 1：Belief confidence 越界拒绝（口径行 L331，含 0/1 边界）——


@pytest.mark.parametrize("confidence", [-0.1, -1.0, -1e-9])
def test_belief_confidence_below_zero_rejected(confidence: float) -> None:
    """confidence < 0 → pydantic ValidationError（源码 Field(ge=0.0) 约束）。"""
    with pytest.raises(ValidationError):
        _belief(confidence=confidence)


@pytest.mark.parametrize("confidence", [1.000000000000001, 1.000001, 1.5, 2.0])
def test_belief_confidence_above_one_rejected(confidence: float) -> None:
    """confidence > 1 → pydantic ValidationError（源码 Field(le=1.0) 约束）。"""
    with pytest.raises(ValidationError):
        _belief(confidence=confidence)


def test_belief_confidence_boundaries_zero_and_one_accepted() -> None:
    """0 与 1 边界接受（ge/le 闭区间；D-P4-09 kind×confidence 两端都合法）。"""
    lo = _belief(confidence=0.0)
    hi = _belief(confidence=1.0)
    assert lo.confidence == 0.0
    assert hi.confidence == 1.0
    assert isinstance(lo.confidence, float)
    assert isinstance(hi.confidence, float)


# —— 覆盖项 2：OBS-INV-1 重复 observed_entity_ids 拒绝（§3.6 不变量）——


def test_observation_record_duplicate_observed_entity_ids_rejected() -> None:
    """构造期：observed_entity_ids 重复 → ValidationError（OBS-INV-1）。

    源码 ``_check_observed_entity_ids_unique``（model_validator mode="after"）
    内部抛裸 ValueError，pydantic v2 统一包装为 ValidationError（模块 docstring
    D-P4-17 分类）；对外可见类型 = ValidationError，无模块自定错误类型。
    """
    assert set(ObservationRecord.model_fields) == {
        "observation_id",
        "actor_id",
        "tick",
        "payload",
        "observed_entity_ids",
        "cause_event_id",
    }
    with pytest.raises(ValidationError):
        _record(observed_entity_ids=(EntityId("ent_a"), EntityId("ent_b"), EntityId("ent_a")))


def test_decode_observations_duplicate_observed_entity_ids_rejected() -> None:
    """model_validate 路径（decode 即 model_validate）：同 OBS-INV-1 显式拒绝。"""
    rec = _record().model_dump(mode="json")
    rec["observed_entity_ids"] = ["ent_a", "ent_a"]
    with pytest.raises(ValidationError):
        decode_observations({"items": [rec]})


# —— 覆盖项 3：四个编解码 roundtrip 全等（口径行 L331 字节级；§6.1 含 0/1 边界）——


def test_observations_codec_roundtrip_byte_equal() -> None:
    """encode_observations→decode_observations：对象全等 + encode 字节级全等。"""
    records = (
        _record(
            observation_id="obs_991",
            actor_id="ent_1",
            tick=3,
            payload={"x": 1, "n": None},
            observed_entity_ids=(EntityId("ent_2"),),
            cause_event_id=EventTypeId("core.observe"),
        ),
        _record(observation_id="obs_992", actor_id="ent_1", tick=4),
    )
    payload = encode_observations(records)
    assert isinstance(payload, dict)
    assert set(payload) == {"items"}
    # §3.6 encode docstring：items 按载荷序（输入 tuple 序原样）
    assert [item["observation_id"] for item in payload["items"]] == ["obs_991", "obs_992"]
    decoded = decode_observations(payload)
    assert decoded == records
    assert isinstance(decoded, tuple)
    # P1 §2.1 类型保持：decode 后 typed str 子类重建（JSON 中为纯字符串）
    assert type(decoded[0].observation_id) is ObservationId
    assert type(decoded[0].actor_id) is EntityId
    assert type(decoded[0].observed_entity_ids[0]) is EntityId
    assert type(decoded[0].cause_event_id) is EventTypeId
    assert decoded[1].cause_event_id is None
    # 字节级全等：encode→decode→encode（json.dumps sort_keys 比较，json 允许）
    assert _canonical(encode_observations(decoded)) == _canonical(payload)


def test_observations_codec_roundtrip_empty_tuple() -> None:
    """空记录序列：{"items": []} 往返 + 字节级全等。"""
    payload = encode_observations(())
    assert payload == {"items": []}
    assert decode_observations(payload) == ()
    assert _canonical(encode_observations(decode_observations(payload))) == _canonical(payload)


def test_knowledge_codec_roundtrip_byte_equal() -> None:
    """encode_knowledge→decode_knowledge：对象全等 + encode 字节级全等。

    §6.1 L1653 口径：往返含 confidence 边界 0/1（beliefs 首尾两端分别取 1.0 /
    0.0）；JsonValue 全形态（嵌套 dict / str / None）与 origin_event_id 可空两端。
    """
    state = KnowledgeState(
        beliefs=(
            _belief(
                subject="zeta",
                predicate="p1",
                value={"a": [1, 2]},
                confidence=1.0,
                formed_tick=2,
                origin_event_id=EventTypeId("ev.x"),
            ),
            _belief(kind=BeliefKind.RUMOR, subject="alpha", predicate="p2", value="txt", confidence=0.0, formed_tick=5),
            _belief(kind=BeliefKind.RUMOR, subject="zeta", predicate="p3", value=None, confidence=0.5, formed_tick=9),
        ),
        last_updated_tick=12,
    )
    payload = encode_knowledge(state)
    assert isinstance(payload, dict)
    assert set(payload) == {"beliefs", "last_updated_tick"}
    decoded = decode_knowledge(payload)
    assert decoded == state
    assert isinstance(decoded.beliefs, tuple)
    assert type(decoded.beliefs[0].kind) is BeliefKind
    assert decoded.last_updated_tick == 12
    assert _canonical(encode_knowledge(decoded)) == _canonical(payload)


def test_knowledge_codec_roundtrip_default_state() -> None:
    """缺省 KnowledgeState：{"beliefs": [], "last_updated_tick": 0} 往返 + 字节级。"""
    assert set(KnowledgeState.model_fields) == {"beliefs", "last_updated_tick"}
    payload = encode_knowledge(KnowledgeState())
    assert payload == {"beliefs": [], "last_updated_tick": 0}
    assert decode_knowledge(payload) == KnowledgeState()
    assert _canonical(encode_knowledge(decode_knowledge(payload))) == _canonical(payload)


# —— 覆盖项 4：畸形载荷 → ValidationError（不静默、不降级；D-P4-17）——


def test_decode_observations_missing_items_key_rejected() -> None:
    """envelope 缺 items 键 → ValidationError（_ObservationsPayload 包络校验）。"""
    with pytest.raises(ValidationError):
        decode_observations({})


def test_decode_observations_extra_envelope_field_rejected() -> None:
    """envelope 多余键 → ValidationError（ContractModel extra="forbid"，不吞）。"""
    with pytest.raises(ValidationError):
        decode_observations({"items": [], "junk": 1})


def test_decode_observations_items_wrong_type_rejected() -> None:
    """items 非序列（str）→ ValidationError。"""
    with pytest.raises(ValidationError):
        decode_observations({"items": "nope"})


def test_decode_observations_record_missing_field_rejected() -> None:
    """记录缺必填字段（observation_id）→ ValidationError。"""
    with pytest.raises(ValidationError):
        decode_observations({"items": [{"actor_id": "ent_1", "tick": 0}]})


def test_decode_observations_record_wrong_type_rejected() -> None:
    """记录字段错类型（tick=str / payload=list）→ ValidationError。"""
    rec = _record().model_dump(mode="json")
    with pytest.raises(ValidationError):
        decode_observations({"items": [{**rec, "tick": "abc"}]})
    rec = _record().model_dump(mode="json")
    with pytest.raises(ValidationError):
        decode_observations({"items": [{**rec, "payload": [1, 2]}]})


def test_decode_observations_record_extra_field_rejected() -> None:
    """记录多余字段 → ValidationError（extra="forbid"，不降级吞字段）。"""
    rec = _record().model_dump(mode="json")
    with pytest.raises(ValidationError):
        decode_observations({"items": [{**rec, "surprise": True}]})


def test_decode_knowledge_belief_missing_field_rejected() -> None:
    """belief 缺字段（formed_tick）→ ValidationError。

    注：KnowledgeState 自身两字段均有缺省（空载荷 → 缺省状态，见
    ``test_decode_knowledge_empty_payload_defaults``），真正的"缺字段"畸形在
    belief 层。
    """
    belief = _belief().model_dump(mode="json")
    del belief["formed_tick"]
    with pytest.raises(ValidationError):
        decode_knowledge({"beliefs": [belief]})


def test_decode_knowledge_wrong_type_rejected() -> None:
    """last_updated_tick=str / beliefs=dict / belief.confidence=str → ValidationError。"""
    with pytest.raises(ValidationError):
        decode_knowledge({"beliefs": [], "last_updated_tick": "x"})
    with pytest.raises(ValidationError):
        decode_knowledge({"beliefs": {"a": 1}})
    belief = _belief().model_dump(mode="json")
    with pytest.raises(ValidationError):
        decode_knowledge({"beliefs": [{**belief, "confidence": "high"}]})


def test_decode_knowledge_extra_field_rejected() -> None:
    """state 层 / belief 层多余键 → ValidationError（extra="forbid"）。"""
    with pytest.raises(ValidationError):
        decode_knowledge({"beliefs": [], "last_updated_tick": 1, "surprise": 1})
    belief = _belief().model_dump(mode="json")
    with pytest.raises(ValidationError):
        decode_knowledge({"beliefs": [{**belief, "mood": "x"}]})


def test_decode_knowledge_empty_payload_defaults() -> None:
    """钉死源码实际行为：KnowledgeState 两字段有缺省，空载荷非畸形。"""
    assert decode_knowledge({}) == KnowledgeState()
    assert decode_knowledge({"beliefs": []}).last_updated_tick == 0


# —— 覆盖项 5：reference_entity_ids 去重 + beliefs_about 序（§3.6 代码块语义）——


def test_reference_entity_ids_deduplicates_subjects() -> None:
    """全部 belief 的 subject 去重集合（frozenset[str]；zeta 重复只计一次）。"""
    refs = _ordered_state().reference_entity_ids()
    assert refs == frozenset({"zeta", "alpha"})
    assert isinstance(refs, frozenset)
    assert all(isinstance(x, str) for x in refs)


def test_beliefs_about_returns_payload_order_not_sorted() -> None:
    """subject 全等的 belief 序列 = 载荷序（确定性），非排序。

    排序口径钉死（§3.6 代码块 docstring 逐字："subject 全等的 belief 序列
    （载荷序，确定性）"）：返回 beliefs tuple 中按出现顺序过滤，**不做字母
    排序**——zeta 的两条保持 p_first 先于 p_third（载荷序），与 subject
    值的大小无关。
    """
    state = _ordered_state()
    zetas = state.beliefs_about("zeta")
    assert [b.predicate for b in zetas] == ["p_first", "p_third"]
    assert isinstance(zetas, tuple)
    assert [b.predicate for b in state.beliefs_about("alpha")] == ["p_two"]


def test_beliefs_about_unknown_subject_returns_empty() -> None:
    """无命中 subject → 空 tuple（不抛错）。"""
    assert _ordered_state().beliefs_about("nope") == ()


def test_reference_entity_ids_beliefs_about_consistency() -> None:
    """§6.1 L1653 口径：reference_entity_ids / beliefs_about 一致性。"""
    state = _ordered_state()
    refs = state.reference_entity_ids()
    assert all(len(state.beliefs_about(s)) >= 1 for s in refs)
    assert sum(len(state.beliefs_about(s)) for s in refs) == len(state.beliefs)
    assert all(belief.subject in refs for belief in state.beliefs)


def test_reference_entity_ids_empty_state() -> None:
    """缺省状态：空 frozenset + 任意 subject 空序列。"""
    empty = KnowledgeState()
    assert empty.reference_entity_ids() == frozenset()
    assert empty.beliefs_about("x") == ()


# —— 覆盖项 6：§6.1（kind 词表 / Memory 无 codec / 三组件常量 / 11 导出）——


def test_belief_seven_field_contract() -> None:
    """§3.6 代码块：Belief 七字段契约（含 formed_tick），D-P4-09 字段级权威。"""
    assert set(Belief.model_fields) == {
        "kind",
        "subject",
        "predicate",
        "value",
        "confidence",
        "formed_tick",
        "origin_event_id",
    }


def test_belief_kind_vocab_fact_rumor_only() -> None:
    """D-P4-09：kind ∈ {FACT, RUMOR}，不设第三种 kind（其他 kind 拒绝）。"""
    assert BeliefKind.FACT.value == "fact"
    assert BeliefKind.RUMOR.value == "rumor"
    assert {member.value for member in BeliefKind} == {"fact", "rumor"}
    assert len(list(BeliefKind)) == 2
    _belief(kind=BeliefKind.FACT)
    _belief(kind=BeliefKind.RUMOR)
    # 词表外拒绝（含大小写不符）：无第三种 kind，uncertainty 由 kind×confidence 承载
    for bad_kind in ("guess", "uncertain", "UNSURE"):
        with pytest.raises(ValidationError):
            _belief(kind=bad_kind)


def test_memory_payload_raw_json_values_no_codec() -> None:
    """D-P4-09：Memory = 原始 JsonValue 列表，无 codec（§3.6 实际面断言）。

    源码 §3.6 实际面：模块导出 11 名中 memory 相关仅 ``MEMORY_COMPONENT`` 常量，
    无 encode_memory/decode_memory——memory 组件载荷 = ``{"items":
    list[JsonValue]}`` 原始列表不经任何编解码函数（episodic/semantic/retrieved
    结构属 Spec:864-865 MAY 自定义域，P4 只透传）。
    """
    public_names = set(knowledge_mod.__all__)
    memory_names = {name for name in public_names if "memory" in name.lower()}
    assert memory_names == {"MEMORY_COMPONENT"}
    assert not hasattr(knowledge_mod, "encode_memory")
    assert not hasattr(knowledge_mod, "decode_memory")
    # 原始载荷形态：任意 JsonValue 列表皆合法（模块不解释、不校验其内部结构）
    payload: dict[str, object] = {"items": [1, "x", {"k": "v"}, None, [1, 2]]}
    assert isinstance(payload, dict)
    assert isinstance(payload["items"], list)
    assert payload["items"][2] == {"k": "v"}
    assert payload["items"][3] is None


def test_component_constant_values() -> None:
    """§3.6 代码块：三组件槽位常量值（P9 必须复用、不得重复注册）。"""
    assert str(OBSERVATIONS_COMPONENT) == "observations"
    assert str(KNOWLEDGE_COMPONENT) == "knowledge"
    assert str(MEMORY_COMPONENT) == "memory"
    assert type(OBSERVATIONS_COMPONENT) is ComponentTypeId
    assert type(KNOWLEDGE_COMPONENT) is ComponentTypeId
    assert type(MEMORY_COMPONENT) is ComponentTypeId
    assert len({OBSERVATIONS_COMPONENT, KNOWLEDGE_COMPONENT, MEMORY_COMPONENT}) == 3


def test_module_exports_exactly_eleven_symbols() -> None:
    """§3.6 头（P4-T04；11 导出）：__all__ 恰 11 名且全部可访问。"""
    assert set(knowledge_mod.__all__) == {
        "BeliefKind",
        "Belief",
        "KnowledgeState",
        "ObservationRecord",
        "OBSERVATIONS_COMPONENT",
        "KNOWLEDGE_COMPONENT",
        "MEMORY_COMPONENT",
        "encode_observations",
        "decode_observations",
        "encode_knowledge",
        "decode_knowledge",
    }
    for name in knowledge_mod.__all__:
        assert hasattr(knowledge_mod, name)

