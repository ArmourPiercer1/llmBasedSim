"""P1-T05 单元测试：序列化与快照基础设施（设计文档 §6 / §7.5 口径）。

覆盖（对齐 ``docs/v2/contracts/P1-core-data-contracts.md`` §7.5 J1–J7 与
任务包要求）：

- **全部契约模型 JSON round-trip**（25 个样本模型参数化）：
  ``dump_json`` → ``assert_json_clean``（J1 JSON 纯净）→ ``load_json``
  值相等（§0.2 判据 5）+ **逐字段类型保持**（基于注解的通用递归检查器：
  typed ID 子类、Revision、枚举成员、嵌套模型、dict 键、datetime、
  Literal、JsonValue 严格 JSON 原生）+ ID/revision/枚举字面量稳定
  （§6.1 规则 4 / R2）；
- **§6.1 序列化 API 机械规则**：dump = ``model_dump(mode="json")`` +
  ``json.dumps(ensure_ascii=False)``；load 兼容 str/UTF-8 bytes；
  ``extra=forbid`` 拒绝未知字段（J2）；类型不符拒绝；
- **assert_json_clean 工具**：干净值通过（含嵌套/空容器）；脏值拒绝
  （bytes/set/NaN/±inf/datetime/对象/非 str 键/tuple/嵌套脏值）；错误
  信息携带 JSONPath 定位；
- **deep_copy_via_roundtrip**：值相等、类型重建、双向零别名；
- **J3 边界深拷贝隔离**：load 之后修改原始数据不影响模型；模型构造
  之后修改调用方传入的可变 dict 不影响模型；
- **快照信封结构与版本标记**（§6.3）：字段集合与顺序逐字等于文档；
  三层版本标记在场且默认正确（J6 前段）；``CONTRACT_SCHEMA_VERSION``
  单一来源（与 state.py 同一对象，无复写）；D-9 instance id 在信封层；
  Snapshot 自身 JSON round-trip（含 wall_time ISO-8601）；
- **§4.3 归属守卫**：Snapshot 收 WorldState/RuntimeState 全字段（含
  ``backend_refs``）、不收 trace；WorldState 无 trace/view 字段；
  TraceRecord 无状态本体字段；D-9 交叉断言；
- **snapshot()/restore_snapshot() 纯函数语义**：created_logical_tick
  缺省取 runtime tick；显式信封参数；快照与活状态零别名（D-15 第 4
  条）；J4 快照隔离（两个不同 revision 的快照互不影响 + restore 产物
  与快照零别名 + 恢复产物类型保持）；
- **J6 版本校验**：check_snapshot_versions 干净快照空报告；篡改
  contract_schema_version / world_state.schema_version /
  runtime_state.schema_version / snapshot_format_version 分别报告；
  P1 不做版本门禁（restore 对篡改快照仍纯函数还原，迁移属 P8）；
- **J5 深冻结视图**：freeze_view 结构（MappingProxyType/tuple 递归）、
  标量直通、逐层赋值抛 TypeError、源数据不受影响、对模型 dump 产物
  深冻结、与 EntityView 组件视图同一冻结语义（D-15 单一实现）;
- **J7 Unicode/边界值**：中文 round-trip 无 ASCII 转义；空容器；
  大整数精确；浮点极值（5e-324 / sys.float_info.max）精确；datetime
  ISO round-trip；
- **模块导出与 import 边界**：__all__ 与 §1.1 归属表一致；AST 白名单
  扫描（B1）；fresh import 无禁止依赖（B2）。

全部用例无网络、无 LLM、无 API key（Spec §47 Phase 1 验收）。
"""

from __future__ import annotations

import ast
import importlib
import json
import sys
import types as pytypes
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, Literal, Union, get_args, get_origin

import pytest
from pydantic import BaseModel, JsonValue, ValidationError

import src.engine_v2.core.serialization as serialization_module
import src.engine_v2.core.snapshot as snapshot_module
import src.engine_v2.core.state as state_module
from src.engine_v2.core.actions import (
    ActionLifecycleStatus,
    ActionProposal,
    ActionTiming,
    ActionTypeId,
    ActiveAction,
    FallbackSpec,
)
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.effects import (
    CommittedEffect,
    EffectTypeId,
    EntityTarget,
    ProposedEffect,
    StateDomainId,
    StateDomainTarget,
)
from src.engine_v2.core.entity import EntityRecord, EntityRef
from src.engine_v2.core.events import DomainEvent, EventTypeId
from src.engine_v2.core.ids import (
    ActionInstanceId,
    CascadeId,
    EffectId,
    EntityId,
    EventId,
    ObservationId,
    ProducerId,
    ScheduledEntryId,
    TraceRecordId,
    TransactionId,
)
from src.engine_v2.core.provenance import (
    CascadeContext,
    CauseKind,
    CauseRef,
    OriginKind,
    Provenance,
)
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.serialization import (
    assert_json_clean,
    deep_copy_via_roundtrip,
    dump_json,
    load_json,
)
from src.engine_v2.core.snapshot import (
    SNAPSHOT_FORMAT_VERSION,
    Snapshot,
    check_snapshot_versions,
    freeze_view,
    restore_snapshot,
    snapshot,
)
from src.engine_v2.core.state import (
    CONTRACT_SCHEMA_VERSION,
    ActorWakeup,
    BackendStateRef,
    RngState,
    RuntimeLifecycle,
    RuntimeState,
    ScenarioState,
    ScheduledEvent,
    WorldState,
)
from src.engine_v2.core.trace import PAYLOAD_RECORD_KEY, TraceKind, TraceRecord
from src.engine_v2.core.transaction import Transaction, TransactionStatus


# —— 样本工厂（全部契约模型；值全部严格 JSON 原生，含中文/边界值）——


def _make_provenance() -> Provenance:
    return Provenance(
        producer_id=ProducerId("policy.alice"),
        origin=OriginKind.BEHAVIOR_POLICY,
        source_record_id=TraceRecordId("trc_test_900"),
        notes="来源：客栈老板（中文注释）",
    )


def _make_entity_record() -> EntityRecord:
    return EntityRecord(
        entity_id=EntityId("ent_test_alice"),
        entity_class="npc",
        tags=["shopkeeper", "friendly"],
        created_revision=Revision(3),
        components={
            ComponentTypeId("space.position"): {
                "x": 1,
                "y": 2,
                "z": [0, 0],
                "label": "客栈门口",
            },
            ComponentTypeId("knowledge.belief"): {
                "facts": [
                    {"id": "f1", "text": "钥匙在柜台下"},
                    {"id": "f2", "text": "老板会修锁"},
                ]
            },
        },
    )


def _make_entity_ref() -> EntityRef:
    return EntityRef(
        entity_id=EntityId("ent_test_alice"),
        component_type=ComponentTypeId("space.position"),
        field_path="pos",
    )


def _make_scenario_state() -> ScenarioState:
    return ScenarioState(
        scenario_id="scn_test_1",
        stage="first_encounter",
        data={"goal": "找到钥匙", "depth": 2, "visited": ["a", "b"]},
    )


def _make_rng_state() -> RngState:
    return RngState(algorithm="pcg32", state={"seed": 42, "counter": 7})


def _make_scheduled_event() -> ScheduledEvent:
    return ScheduledEvent(
        entry_id=ScheduledEntryId("sch_0001"),
        due_tick=43,
        kind="wakeup",
        payload={"instance_id": "act_test_2"},
    )


def _make_actor_wakeup() -> ActorWakeup:
    return ActorWakeup(
        actor_id=EntityId("ent_test_bob"),
        due_tick=44,
        reason="被事件唤醒",
    )


def _make_backend_state_ref() -> BackendStateRef:
    return BackendStateRef(
        backend_id="dynamics_01",
        backend_kind="dynamics",
        checkpointable=True,
        restorable=True,
        replayable=False,
        checkpoint_ref="ckpt://dynamics/01",
        metadata={"gpu": 0, "note": "外置 checkpoint"},
    )


def _make_proposal() -> ActionProposal:
    """Spec §9 示例口径（base_world_revision=812、observation_id=obs_991）。"""
    return ActionProposal(
        proposal_id=ActionInstanceId("act_test_2"),
        actor_id=EntityId("ent_test_bob"),
        action_id=ActionTypeId("move"),
        arguments={"to": {"x": 1, "y": 2}},
        intent="移动到客栈门口",
        timing=ActionTiming(earliest_start_tick=1, deadline_tick=10, duration_hint_ticks=3),
        confidence=0.75,
        fallback_action=FallbackSpec(action_id=ActionTypeId("rest"), arguments={"minutes": 10}),
        base_world_revision=Revision(812),
        observation_id=ObservationId("obs_991"),
        actor_state_revision=Revision(810),
        valid_until=Revision(820),
        provenance=_make_provenance(),
    )


def _make_active_action() -> ActiveAction:
    return ActiveAction(
        instance_id=ActionInstanceId("act_test_1"),
        action_id=ActionTypeId("rest"),
        actor_id=EntityId("ent_test_alice"),
        status=ActionLifecycleStatus.ACTIVE,
        start_tick=40,
        expected_end_tick=50,
        progress=0.4,
        interruptible=True,
        completion_condition={"type": "duration", "ticks": 10},
        next_checkpoint_tick=45,
        base_world_revision=Revision(812),
        provenance=_make_provenance(),
        last_transition_tick=40,
        result_summary=None,
    )


def _make_runtime_state(logical_tick: int = 42) -> RuntimeState:
    return RuntimeState(
        schema_version=CONTRACT_SCHEMA_VERSION,
        logical_tick=logical_tick,
        lifecycle=RuntimeLifecycle.RUNNING,
        scheduler_queue=[_make_scheduled_event()],
        active_actions={ActionInstanceId("act_test_1"): _make_active_action()},
        actor_wakeups=[_make_actor_wakeup()],
        active_modes=["exploration"],
        mode_context={"overlay": "night", "intensity": 0.8},
        rng_state=_make_rng_state(),
        pending_proposals=[_make_proposal()],
        backend_refs={"dynamics_01": _make_backend_state_ref()},
    )


def _make_world_state(world_revision: int = 5) -> WorldState:
    return WorldState(
        schema_version=CONTRACT_SCHEMA_VERSION,
        world_revision=Revision(world_revision),
        entities={
            EntityId("ent_test_alice"): _make_entity_record(),
            EntityId("ent_test_bob"): EntityRecord(
                entity_id=EntityId("ent_test_bob"),
                entity_class="player",
                tags=["hero"],
                created_revision=Revision(1),
                components={ComponentTypeId("space.position"): {"x": 10, "y": 20}},
            ),
        },
        world_variables={
            "calendar": {"day": 3, "hour": 12, "minute": 0},
            "big_int": 10**30,
            "tiny_float": 5e-324,
            "max_float": sys.float_info.max,
            "note": "中文世界变量",
        },
        scenario_state=_make_scenario_state(),
    )


def _make_entity_target() -> EntityTarget:
    return EntityTarget(
        entity_id=EntityId("ent_test_alice"),
        component_type=ComponentTypeId("space.position"),
        field_path="pos",
    )


def _make_state_domain_target() -> StateDomainTarget:
    return StateDomainTarget(domain=StateDomainId("world_variables"))


def _make_proposed_effect() -> ProposedEffect:
    return ProposedEffect(
        effect_id=EffectId("eff_test_1"),
        effect_type=EffectTypeId("space.move"),
        source=ProducerId("dynamics.rigid_body"),
        target=_make_entity_target(),
        payload={"dx": 1.5, "dy": -2, "force": [0.1, 0.2], "note": "碰撞响应"},
        base_revision=Revision(812),
        cause_ids=[CauseRef(kind=CauseKind.ACTION, ref_id="act_test_1")],
        authority_scope="space",
        priority_hint=10,
        metadata={"origin": "碰撞响应"},
    )


def _make_proposed_effect_state_domain() -> ProposedEffect:
    return ProposedEffect(
        effect_id=EffectId("eff_test_2"),
        effect_type=EffectTypeId("world.increment"),
        source=ProducerId("rule.counter"),
        target=_make_state_domain_target(),
        payload={"key": "score", "delta": 1},
        base_revision=Revision(812),
        cause_ids=[],
        authority_scope=None,
        priority_hint=None,
        metadata={},
    )


def _make_committed_effect() -> CommittedEffect:
    return CommittedEffect(
        effect=_make_proposed_effect(),
        transaction_id=TransactionId("txn_test_1"),
        commit_revision=Revision(813),
        sequence=0,
    )


def _make_transaction() -> Transaction:
    return Transaction(
        transaction_id=TransactionId("txn_test_1"),
        status=TransactionStatus.COMMITTED,
        base_revision=Revision(812),
        commit_revision=Revision(813),
        logical_tick=42,
        effects=[_make_committed_effect()],
        event_ids=[EventId("evt_test_1")],
        cascade=CascadeContext(
            cascade_id=CascadeId("csc_test_1"),
            causal_root_id="act_test_1",
            depth=1,
        ),
        provenance=_make_provenance(),
        abort_reason=None,
    )


def _make_domain_event() -> DomainEvent:
    return DomainEvent(
        event_id=EventId("evt_test_1"),
        event_type=EventTypeId("space.moved"),
        world_revision=Revision(813),
        logical_tick=42,
        transaction_id=TransactionId("txn_test_1"),
        payload={"entity_id": "ent_test_alice", "to": [1, 2]},
        cause_ids=[CauseRef(kind=CauseKind.EFFECT, ref_id="eff_test_1")],
        source_system=ProducerId("dynamics.rigid_body"),
        provenance=_make_provenance(),
        cascade=CascadeContext(
            cascade_id=CascadeId("csc_test_1"),
            causal_root_id="act_test_1",
            depth=1,
        ),
        wall_time=datetime(2025, 6, 1, 12, 30, 45, 123456, tzinfo=timezone.utc),
    )


def _make_trace_record() -> TraceRecord:
    return TraceRecord(
        record_id=TraceRecordId("trc_test_1"),
        kind=TraceKind.DOMAIN_EVENT,
        world_revision=Revision(813),
        logical_tick=42,
        wall_time=datetime(2025, 6, 1, 12, 30, 45, 123456, tzinfo=timezone.utc),
        producer_id=ProducerId("dynamics.rigid_body"),
        transaction_id=TransactionId("txn_test_1"),
        cascade_id=CascadeId("csc_test_1"),
        payload={PAYLOAD_RECORD_KEY: _make_domain_event().model_dump(mode="json")},
    )


def _make_action_timing() -> ActionTiming:
    return ActionTiming(earliest_start_tick=1, deadline_tick=10, duration_hint_ticks=3)


def _make_fallback_spec() -> FallbackSpec:
    return FallbackSpec(action_id=ActionTypeId("rest"), arguments={"minutes": 10})


def _make_cause_ref() -> CauseRef:
    return CauseRef(kind=CauseKind.EFFECT, ref_id="eff_test_1")


def _make_cascade_context() -> CascadeContext:
    return CascadeContext(
        cascade_id=CascadeId("csc_test_1"),
        causal_root_id="act_test_1",
        depth=1,
    )


def _make_snapshot() -> Snapshot:
    return snapshot(
        _make_world_state(5),
        _make_runtime_state(42),
        "inst_test_a",
        created_wall_time=datetime(2025, 6, 1, 12, 30, 45, 123456, tzinfo=timezone.utc),
        project_version="0.1.0",
        module_versions={"engine_v2.core": "1.0"},
    )


#: 全部契约模型样本（设计文档 §1.1 文件清单的 ContractModel 子类全集 +
#: Snapshot 本身）：参数化 round-trip 测试的覆盖面。
ROUNDTRIP_SAMPLES: tuple[tuple[str, Callable[[], BaseModel]], ...] = (
    ("EntityRecord", _make_entity_record),
    ("EntityRef", _make_entity_ref),
    ("ScenarioState", _make_scenario_state),
    ("RngState", _make_rng_state),
    ("ScheduledEvent", _make_scheduled_event),
    ("ActorWakeup", _make_actor_wakeup),
    ("BackendStateRef", _make_backend_state_ref),
    ("RuntimeState", _make_runtime_state),
    ("WorldState", _make_world_state),
    ("Provenance", _make_provenance),
    ("CauseRef", _make_cause_ref),
    ("CascadeContext", _make_cascade_context),
    ("EntityTarget", _make_entity_target),
    ("StateDomainTarget", _make_state_domain_target),
    ("ProposedEffect.entity_target", _make_proposed_effect),
    ("ProposedEffect.state_domain_target", _make_proposed_effect_state_domain),
    ("CommittedEffect", _make_committed_effect),
    ("ActionTiming", _make_action_timing),
    ("FallbackSpec", _make_fallback_spec),
    ("ActionProposal", _make_proposal),
    ("ActiveAction", _make_active_action),
    ("DomainEvent", _make_domain_event),
    ("Transaction", _make_transaction),
    ("TraceRecord", _make_trace_record),
    ("Snapshot", _make_snapshot),
)


# —— 通用逐字段类型保持检查器（§2.1 / §6.1 规则 3 的程序化断言）——
#
# 基于 Pydantic ``model_fields`` 注解递归校验 round-trip 产物：typed ID /
# Revision 重建为**精确子类**（``type(x) is cls``，str/int 子类不混同）、
# 枚举为精确成员类、嵌套模型逐字段递归、dict 键逐键校验、JsonValue 字段
# 为严格 JSON 原生（精确标量类型，拒绝 str/int 子类渗入）。


def _strip_annotated(ann: Any) -> Any:
    if get_origin(ann) is Annotated:
        return get_args(ann)[0]
    return ann


def _is_json_value_ann(ann: Any) -> bool:
    """判断注解（或其成员）是否为 JsonValue 族（pydantic.JsonValue 递归别名）。"""
    ann = _strip_annotated(ann)
    if ann is JsonValue:
        return True
    origin = get_origin(ann)
    if origin is Union or origin is pytypes.UnionType:
        return any(_is_json_value_ann(m) for m in get_args(ann) if m is not type(None))
    if origin is list:
        return _is_json_value_ann(get_args(ann)[0])
    if origin is dict:
        key_ann, val_ann = get_args(ann)
        return _is_json_value_ann(key_ann) and _is_json_value_ann(val_ann)
    return False


def _check_json_native_strict(where: str, value: Any) -> None:
    """JsonValue 族值必须为**精确** JSON 原生类型（拒绝 str/int 子类渗入）。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        assert type(value) in (str, int, float, bool, type(None)), (
            f"{where}：期望精确 JSON 标量类型，得到 {type(value).__name__}"
        )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _check_json_native_strict(f"{where}[{index}]", item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str), f"{where}：dict 键必须为 str，得到 {type(key).__name__}"
            _check_json_native_strict(f"{where}.{key}", item)
        return
    raise AssertionError(f"{where}：非 JSON 原生类型 {type(value).__name__}")


def _check_model_fields(model: Any, where: str) -> None:
    for name, field_info in type(model).model_fields.items():
        _check_type(f"{where}.{name}", field_info.annotation, getattr(model, name))


def _check_union(where: str, members: tuple[Any, ...], value: Any) -> None:
    if value is None:
        return
    for member in members:
        member = _strip_annotated(member)
        # 容器型成员（如 dict[str, JsonValue] | None 中的 dict 分支）：
        # 命中容器类型则按该成员注解递归
        member_origin = get_origin(member)
        if member_origin is dict:
            if isinstance(value, dict):
                _check_type(where, member, value)
                return
            continue
        if member_origin is list:
            if isinstance(value, list):
                _check_type(where, member, value)
                return
            continue
        if isinstance(member, type) and type(value) is member:
            if issubclass(member, BaseModel):
                _check_model_fields(value, where)
            return
    raise AssertionError(
        f"{where}：{type(value).__name__} 不匹配任一 union 成员 "
        f"{[getattr(m, '__name__', repr(m)) for m in members]}"
    )


def _check_type(where: str, ann: Any, value: Any) -> None:
    """断言 value 的类型精确符合契约注解 ann（round-trip 类型保持）。"""
    ann = _strip_annotated(ann)
    if _is_json_value_ann(ann):
        _check_json_native_strict(where, value)
        return
    origin = get_origin(ann)
    if origin is Union or origin is pytypes.UnionType:
        _check_union(where, tuple(m for m in get_args(ann) if m is not type(None)), value)
        return
    if origin is list:
        assert isinstance(value, list), f"{where}：期望 list，得到 {type(value).__name__}"
        item_ann = get_args(ann)[0]
        for index, item in enumerate(value):
            _check_type(f"{where}[{index}]", item_ann, item)
        return
    if origin is dict:
        assert isinstance(value, dict), f"{where}：期望 dict，得到 {type(value).__name__}"
        key_ann, val_ann = get_args(ann)
        for key, item in value.items():
            _check_type(f"{where}.<key {key!r}>", key_ann, key)
            _check_type(f"{where}.{key}", val_ann, item)
        return
    if origin is Literal:
        assert value in get_args(ann), f"{where}：{value!r} 不在 {get_args(ann)}"
        return
    if isinstance(ann, type):
        assert isinstance(value, ann) and type(value) is ann, (
            f"{where}：期望精确类型 {ann.__name__}，得到 {type(value).__name__}"
        )
        if issubclass(ann, BaseModel):
            _check_model_fields(value, where)
        return
    raise AssertionError(f"{where}：未处理的注解 {ann!r}（检查器覆盖缺口）")


def _assert_types_preserved(model: Any, where: str) -> None:
    _check_model_fields(model, where)


# —— §6.1 序列化 API 机械规则 ——


class TestSerializationApi:
    """设计文档 §6.1 规则 1/2：唯一合法出入口 + ensure_ascii=False。"""

    def test_dump_json_is_mechanical_model_dump_json_plus_dumps(self) -> None:
        """dump_json ≡ model_dump(mode="json") + json.dumps(ensure_ascii=False)。"""
        model = _make_world_state()
        assert dump_json(model) == json.dumps(model.model_dump(mode="json"), ensure_ascii=False)

    def test_dump_json_ensure_ascii_false_chinese_literal(self) -> None:
        text = dump_json(_make_proposal())
        assert "移动到客栈门口" in text
        assert "\\u" not in text

    def test_load_json_accepts_str(self) -> None:
        model = _make_entity_record()
        assert load_json(EntityRecord, dump_json(model)) == model

    def test_load_json_accepts_utf8_bytes(self) -> None:
        model = _make_entity_record()
        rebuilt = load_json(EntityRecord, dump_json(model).encode("utf-8"))
        assert rebuilt == model

    def test_load_json_rejects_unknown_field(self) -> None:
        """J2：extra=forbid 生效——注入未知字段 → ValidationError。"""
        data = json.loads(dump_json(_make_entity_record()))
        data["unknown_field"] = 1
        with pytest.raises(ValidationError):
            load_json(EntityRecord, json.dumps(data))

    def test_load_json_rejects_wrong_type(self) -> None:
        data = json.loads(dump_json(_make_entity_record()))
        data["entity_id"] = 12345  # typed ID 必须是字符串
        with pytest.raises(ValidationError):
            load_json(EntityRecord, json.dumps(data))

    def test_load_json_rejects_non_object_json(self) -> None:
        with pytest.raises(ValidationError):
            load_json(EntityRecord, "42")

    def test_doc_0_2_roundtrip_criterion_verbatim(self) -> None:
        """§0.2 判据 5 原文形态：Cls.model_validate(obj.model_dump(mode="json")) == obj。"""
        model = _make_world_state()
        assert WorldState.model_validate(model.model_dump(mode="json")) == model
        model_rt = _make_runtime_state()
        assert RuntimeState.model_validate(model_rt.model_dump(mode="json")) == model_rt


# —— 全部契约模型 JSON round-trip（J1 + 类型保持 + 规则 4）——


class TestContractModelJsonRoundtrip:
    """任务包核心验收：全部已落盘契约模型 + Snapshot 的 JSON round-trip。"""

    @pytest.mark.parametrize(
        ("name", "factory"),
        ROUNDTRIP_SAMPLES,
        ids=[name for name, _ in ROUNDTRIP_SAMPLES],
    )
    def test_roundtrip_value_equality_types_and_json_purity(self, name: str, factory: Any) -> None:
        model: BaseModel = factory()
        text = dump_json(model)
        assert isinstance(text, str) and text
        # J1：dump 结果 JSON 纯净（§0.2 铁律 1）
        data = json.loads(text)
        assert_json_clean(data)
        # §6.1 出入口 + §0.2 判据 5：值相等
        rebuilt = load_json(type(model), text)
        assert rebuilt == model
        # §2.1 / §6.1 规则 3：逐字段类型保持（含 dict 键与嵌套模型）
        _assert_types_preserved(rebuilt, name)

    def test_rule4_id_revision_enum_literals_stable(self) -> None:
        """§6.1 规则 4：round-trip 不得改变任何 ID 值、revision 值、枚举字面量。"""
        ws = _make_world_state(5)
        rt = _make_runtime_state(42)
        ws2 = load_json(WorldState, dump_json(ws))
        rt2 = load_json(RuntimeState, dump_json(rt))
        # ID 值逐字相等 + 类型保持
        assert list(ws2.entities) == list(ws.entities)
        assert all(type(k) is EntityId for k in ws2.entities)
        for original_key, record in ws2.entities.items():
            assert record.entity_id == original_key
            assert type(record.entity_id) is EntityId
        # revision 值与类型
        assert ws2.world_revision == 5
        assert type(ws2.world_revision) is Revision
        # 枚举字面量
        assert rt2.lifecycle is RuntimeLifecycle.RUNNING
        for action in rt2.active_actions.values():
            assert action.status is ActionLifecycleStatus.ACTIVE
        # JSON 侧为纯整数（R5 口径）
        raw = json.loads(dump_json(ws))
        assert raw["world_revision"] == 5
        assert type(raw["world_revision"]) is int
        assert raw["entities"]["ent_test_alice"]["created_revision"] == 3

    def test_discriminated_union_branches_preserved(self) -> None:
        """C3 口径：EffectTarget 两分支 round-trip 后判别类型保持。"""
        entity_effect = _make_proposed_effect()
        rebuilt = load_json(ProposedEffect, dump_json(entity_effect))
        assert type(rebuilt.target) is EntityTarget
        domain_effect = _make_proposed_effect_state_domain()
        rebuilt2 = load_json(ProposedEffect, dump_json(domain_effect))
        assert type(rebuilt2.target) is StateDomainTarget
        assert type(rebuilt2.target.domain) is StateDomainId


# —— assert_json_clean 工具 ——


class TestAssertJsonClean:
    """J1 工具本体：递归 JSON 纯净断言。"""

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "中文与 ASCII 混合",
            0,
            -1,
            10**30,
            1.5,
            -0.25,
            5e-324,
            sys.float_info.max,
            True,
            False,
            [],
            {},
            [1, "a", None, True, [2, [3]]],
            {"a": 1, "b": [2, 3], "c": {"d": None}, "中文键": "中文值"},
        ],
        ids=[
            "none",
            "str",
            "int_zero",
            "int_neg",
            "int_big",
            "float",
            "float_neg",
            "float_subnormal",
            "float_max",
            "true",
            "false",
            "empty_list",
            "empty_dict",
            "nested_list",
            "nested_dict",
        ],
    )
    def test_clean_values_pass(self, value: Any) -> None:
        assert_json_clean(value)  # 不抛即通过

    @pytest.mark.parametrize(
        ("label", "value"),
        [
            ("bytes", b"x"),
            ("set", {1, 2}),
            ("frozenset", frozenset({1})),
            ("nan", float("nan")),
            ("inf", float("inf")),
            ("-inf", float("-inf")),
            ("datetime", datetime(2025, 1, 1)),
            ("object", object()),
            ("int_dict_key", {1: "a"}),
            ("tuple", (1, 2)),
            ("nested_dirty", {"a": [1, {"b": b"x"}]}),
        ],
    )
    def test_dirty_values_rejected(self, label: str, value: Any) -> None:
        with pytest.raises(AssertionError):
            assert_json_clean(value)

    def test_error_message_carries_jsonpath(self) -> None:
        with pytest.raises(AssertionError, match=r"\$\.a\[0\]"):
            assert_json_clean({"a": [b"x"]})
        with pytest.raises(AssertionError, match="dict 键必须为 str"):
            assert_json_clean({1: "a"})

    def test_contract_model_dumps_all_clean(self) -> None:
        """J1 全量：全部契约模型样本的 dump 结果经 assert_json_clean 通过。"""
        for name, factory in ROUNDTRIP_SAMPLES:
            data = json.loads(dump_json(factory()))
            # 参数化 round-trip 已断言；此处显式固定 J1 口径（不抛即通过）
            assert_json_clean(data)


# —— deep_copy_via_roundtrip（§6.1 / §6.2 D-15 第 4 条）——


class TestDeepCopyViaRoundtrip:
    def test_value_equality_type_rebuild(self) -> None:
        model = _make_world_state(7)
        copy = deep_copy_via_roundtrip(model)
        assert copy == model
        assert copy is not model
        assert type(copy) is WorldState
        # 类型重建
        assert all(type(k) is EntityId for k in copy.entities)
        assert type(copy.world_revision) is Revision
        assert all(
            type(ct) is ComponentTypeId
            for ct in copy.entities[EntityId("ent_test_alice")].components
        )

    def test_zero_aliasing_both_directions(self) -> None:
        model = _make_world_state()
        copy = deep_copy_via_roundtrip(model)
        baseline = model.model_dump(mode="json")
        # 改原模型嵌套容器 → copy 不受影响
        model.world_variables["injected_into_original"] = 1
        assert "injected_into_original" not in copy.world_variables
        # 改 copy 嵌套容器 → 原模型不受影响
        copy.world_variables["injected_into_copy"] = 2
        assert "injected_into_copy" not in model.world_variables
        # 剔除两侧已知的就地注入后，值仍与基线一致（零别名）
        m_dump = model.model_dump(mode="json")
        c_dump = copy.model_dump(mode="json")
        m_dump["world_variables"].pop("injected_into_original")
        c_dump["world_variables"].pop("injected_into_copy")
        assert m_dump == c_dump == baseline

    def test_copy_of_snapshot_envelope(self) -> None:
        snap = _make_snapshot()
        copy = deep_copy_via_roundtrip(snap)
        assert copy == snap and type(copy) is Snapshot
        copy.runtime_state.mode_context["injected"] = 1
        assert "injected" not in snap.runtime_state.mode_context


# —— J3 边界深拷贝隔离 ——


class TestBoundaryDeepCopyIsolation:
    def test_load_json_boundary_deep_copy(self) -> None:
        """J3：load 之后修改传入的原始数据 → 模型不受影响。"""
        raw = json.loads(dump_json(_make_world_state()))
        ws = load_json(WorldState, json.dumps(raw, ensure_ascii=False))
        raw["world_variables"]["calendar"]["day"] = 999
        raw["world_variables"]["injected"] = 1
        assert ws.world_variables["calendar"]["day"] == 3
        assert "injected" not in ws.world_variables

    def test_model_validate_does_not_alias_input_dict(self) -> None:
        """§3.5 纪律 2（入口深拷贝）：构造后修改调用方传入的可变 dict → 模型不变。"""
        raw: dict[str, Any] = {
            "entities": {},
            "world_variables": {"v": {"n": 1}},
            "scenario_state": {},
        }
        ws = WorldState.model_validate(raw)
        raw["world_variables"]["v"]["n"] = 999
        raw["world_variables"]["injected"] = 1
        assert ws.world_variables["v"]["n"] == 1
        assert "injected" not in ws.world_variables


# —— 快照信封结构与版本标记（§6.3 / J6）——


class TestSnapshotEnvelope:
    def test_field_set_and_order_exact(self) -> None:
        """§6.3 字段逐项：集合与声明顺序逐字等于设计文档。"""
        assert list(Snapshot.model_fields) == [
            "snapshot_format_version",
            "contract_schema_version",
            "world_instance_id",
            "world_state",
            "runtime_state",
            "created_logical_tick",
            "created_wall_time",
            "project_version",
            "module_versions",
        ]
        # 两个状态字段的注解精确为 WorldState / RuntimeState（不收 trace）
        assert Snapshot.model_fields["world_state"].annotation is WorldState
        assert Snapshot.model_fields["runtime_state"].annotation is RuntimeState

    def test_version_marks_present_and_defaults(self) -> None:
        """J6 前段：三层版本标记在场且默认值正确。"""
        assert SNAPSHOT_FORMAT_VERSION == 1
        assert CONTRACT_SCHEMA_VERSION == 1
        snap = _make_snapshot()
        assert snap.snapshot_format_version == SNAPSHOT_FORMAT_VERSION
        assert snap.contract_schema_version == CONTRACT_SCHEMA_VERSION
        assert snap.world_state.schema_version == CONTRACT_SCHEMA_VERSION
        assert snap.runtime_state.schema_version == CONTRACT_SCHEMA_VERSION
        # JSON 侧三层标记在场
        raw = json.loads(dump_json(snap))
        assert raw["snapshot_format_version"] == 1
        assert raw["contract_schema_version"] == 1
        assert raw["world_state"]["schema_version"] == 1
        assert raw["runtime_state"]["schema_version"] == 1

    def test_contract_schema_version_single_source(self) -> None:
        """T02 已确立的事实：snapshot.py 从 state.py import 复用，严禁双源复写。"""
        assert snapshot_module.CONTRACT_SCHEMA_VERSION is state_module.CONTRACT_SCHEMA_VERSION
        # Snapshot 字段缺省值引用的也是同一常量
        default = Snapshot.model_fields["contract_schema_version"].default
        assert default == state_module.CONTRACT_SCHEMA_VERSION

    def test_d9_instance_id_at_envelope_layer(self) -> None:
        """D-9：instance 身份在信封层，不在 WorldState 内。"""
        assert "world_instance_id" in Snapshot.model_fields
        assert "world_instance_id" not in WorldState.model_fields
        assert _make_snapshot().world_instance_id == "inst_test_a"

    def test_snapshot_extra_forbid(self) -> None:
        data = json.loads(dump_json(_make_snapshot()))
        data["trace_records"] = []  # 未知字段（且是"想塞 trace"的形态）
        with pytest.raises(ValidationError):
            Snapshot.model_validate(data)

    def test_snapshot_json_roundtrip_with_wall_time(self) -> None:
        snap = _make_snapshot()
        text = dump_json(snap)
        raw = json.loads(text)
        # wall_time 为 ISO-8601 字符串（§0.2 铁律 3：诊断侧墙钟）
        assert isinstance(raw["created_wall_time"], str)
        assert "T" in raw["created_wall_time"]
        rebuilt = load_json(Snapshot, text)
        assert rebuilt == snap
        _assert_types_preserved(rebuilt, "Snapshot")
        assert rebuilt.created_wall_time == snap.created_wall_time
        assert type(rebuilt.created_wall_time) is datetime


# —— §4.3 snapshot/trace 归属守卫 ——


class TestSnapshotOwnershipGuard:
    def test_snapshot_collects_full_state_no_trace(self) -> None:
        """§4.3 归属总表：Snapshot 收 WorldState/RuntimeState 全字段，不收 trace。"""
        field_names = set(Snapshot.model_fields)
        assert not any("trace" in name for name in field_names)
        assert "world_state" in field_names and "runtime_state" in field_names
        # 无任何字段以 TraceRecord 为（直接）承载类型
        for name, field_info in Snapshot.model_fields.items():
            assert field_info.annotation is not TraceRecord, f"Snapshot.{name} 不得承载 TraceRecord"

    def test_world_state_has_no_trace_or_view_fields(self) -> None:
        names = set(WorldState.model_fields)
        assert names == {
            "schema_version",
            "world_revision",
            "entities",
            "world_variables",
            "scenario_state",
        }
        assert not any("trace" in name or "view" in name for name in names)

    def test_runtime_state_fields_include_backend_refs(self) -> None:
        """§4.3：BackendState 仅 backend_refs（引用+能力声明）进快照（D-10）。"""
        names = set(RuntimeState.model_fields)
        assert names == {
            "schema_version",
            "logical_tick",
            "lifecycle",
            "scheduler_queue",
            "active_actions",
            "actor_wakeups",
            "active_modes",
            "mode_context",
            "rng_state",
            "pending_proposals",
            "backend_refs",
        }

    def test_trace_record_has_no_state_body(self) -> None:
        """§4.3：TraceRecord 不含状态本体（trace 记录"变化"，不复制状态）。"""
        names = set(TraceRecord.model_fields)
        state_body = {
            "entities",
            "world_variables",
            "scenario_state",
            "scheduler_queue",
            "active_actions",
            "actor_wakeups",
            "active_modes",
            "rng_state",
            "backend_refs",
        }
        assert not names & state_body


# —— snapshot()/restore_snapshot() 纯函数语义与 J4 隔离 ——


class TestSnapshotFunctions:
    def test_snapshot_default_created_tick_from_runtime(self) -> None:
        snap = snapshot(_make_world_state(5), _make_runtime_state(42), "inst_x")
        assert snap.created_logical_tick == 42
        assert snap.created_wall_time is None
        assert snap.project_version is None
        assert snap.module_versions == {}

    def test_snapshot_explicit_envelope_params(self) -> None:
        wall = datetime(2025, 6, 1, tzinfo=timezone.utc)
        snap = snapshot(
            _make_world_state(5),
            _make_runtime_state(42),
            "inst_x",
            created_logical_tick=99,
            created_wall_time=wall,
            project_version="9.9.9",
            module_versions={"a": "1"},
        )
        assert snap.created_logical_tick == 99
        assert snap.created_wall_time == wall
        assert snap.project_version == "9.9.9"
        assert snap.module_versions == {"a": "1"}

    def test_snapshot_zero_aliasing_with_live_state(self) -> None:
        """D-15 第 4 条：Snapshot 内数据与运行时活数据零别名。"""
        ws = _make_world_state(5)
        rt = _make_runtime_state(42)
        snap = snapshot(ws, rt, "inst_x")
        # 改活状态嵌套容器 → 快照不受影响
        ws.world_variables["live_change"] = 1
        rt.mode_context["live_change"] = 1
        assert "live_change" not in snap.world_state.world_variables
        assert "live_change" not in snap.runtime_state.mode_context
        # 改快照嵌套容器 → 活状态不受影响
        snap.world_state.world_variables["snap_change"] = 2
        snap.runtime_state.mode_context["snap_change"] = 2
        assert "snap_change" not in ws.world_variables
        assert "snap_change" not in rt.mode_context
        # 剔除两侧已知的就地注入后，值仍与全新构造一致（零别名）
        m_dump = ws.model_dump(mode="json")
        r_dump = rt.model_dump(mode="json")
        s_dump = snap.model_dump(mode="json")
        m_dump["world_variables"].pop("live_change")
        r_dump["mode_context"].pop("live_change")
        s_dump["world_state"]["world_variables"].pop("snap_change")
        s_dump["runtime_state"]["mode_context"].pop("snap_change")
        assert m_dump == _make_world_state(5).model_dump(mode="json")
        assert r_dump == _make_runtime_state(42).model_dump(mode="json")
        assert s_dump == snapshot(
            _make_world_state(5), _make_runtime_state(42), "inst_x"
        ).model_dump(mode="json")

    def test_snapshot_isolation_two_revisions(self) -> None:
        """J4 前段：两个不同 revision 的 Snapshot 互不影响。"""
        snap_a = snapshot(_make_world_state(5), _make_runtime_state(42), "inst_a")
        snap_b = snapshot(_make_world_state(6), _make_runtime_state(43), "inst_b")
        assert snap_a != snap_b
        assert snap_a.world_state.world_revision == 5
        assert snap_b.world_state.world_revision == 6
        # 改 snap_a 内部 → snap_b 不受影响
        snap_a.world_state.world_variables["only_a"] = 1
        snap_a.runtime_state.active_modes.append("only_a")
        assert "only_a" not in snap_b.world_state.world_variables
        assert "only_a" not in snap_b.runtime_state.active_modes
        # 各自值完整性
        assert snap_b == snapshot(_make_world_state(6), _make_runtime_state(43), "inst_b")

    def test_restore_snapshot_zero_aliasing(self) -> None:
        """J4 后段：restore 产物与快照零别名，改恢复产物不影响活快照。"""
        snap = _make_snapshot()
        restored_ws, restored_rt = restore_snapshot(snap)
        assert type(restored_ws) is WorldState
        assert type(restored_rt) is RuntimeState
        assert restored_ws == snap.world_state
        assert restored_rt == snap.runtime_state
        assert restored_ws is not snap.world_state
        assert restored_rt is not snap.runtime_state
        # 改恢复产物 → 快照不受影响
        restored_ws.world_variables["from_restore"] = 1
        restored_rt.mode_context["from_restore"] = 1
        assert "from_restore" not in snap.world_state.world_variables
        assert "from_restore" not in snap.runtime_state.mode_context
        # 改快照 → 恢复产物不受影响
        snap.world_state.world_variables["from_snap"] = 2
        assert "from_snap" not in restored_ws.world_variables

    def test_restore_snapshot_preserves_types(self) -> None:
        snap = _make_snapshot()
        restored_ws, restored_rt = restore_snapshot(snap)
        _assert_types_preserved(restored_ws, "restored.WorldState")
        _assert_types_preserved(restored_rt, "restored.RuntimeState")


# —— J6 版本校验（check_snapshot_versions）——


def _snapshot_tampered(mutate: Callable[[dict[str, Any]], None]) -> Snapshot:
    data = json.loads(dump_json(_make_snapshot()))
    mutate(data)
    return Snapshot.model_validate(data)


class TestVersionCheck:
    def test_clean_snapshot_no_issues(self) -> None:
        assert check_snapshot_versions(_make_snapshot()) == ()

    def test_tampered_contract_schema_version_reported(self) -> None:
        snap = _snapshot_tampered(lambda d: d.update({"contract_schema_version": 99}))
        issues = check_snapshot_versions(snap)
        assert len(issues) == 1
        assert "contract_schema_version" in issues[0]
        assert "99" in issues[0]

    @pytest.mark.parametrize(
        ("label", "mutate"),
        [
            ("world_state", lambda d: d["world_state"].update({"schema_version": 0})),
            ("runtime_state", lambda d: d["runtime_state"].update({"schema_version": 2})),
        ],
        ids=["world_state", "runtime_state"],
    )
    def test_tampered_state_model_version_reported(self, label: str, mutate: Any) -> None:
        snap = _snapshot_tampered(mutate)
        issues = check_snapshot_versions(snap)
        assert len(issues) == 1
        assert f"snapshot.{label}.schema_version" in issues[0]

    def test_tampered_envelope_format_version_reported(self) -> None:
        snap = _snapshot_tampered(lambda d: d.update({"snapshot_format_version": 2}))
        issues = check_snapshot_versions(snap)
        assert len(issues) == 1
        assert "snapshot_format_version" in issues[0]

    def test_tampered_multiple_reported_together(self) -> None:
        def mutate(data: dict[str, Any]) -> None:
            data["contract_schema_version"] = 3
            data["world_state"]["schema_version"] = 0

        issues = check_snapshot_versions(_snapshot_tampered(mutate))
        assert len(issues) == 2

    def test_restore_snapshot_pure_without_version_gate(self) -> None:
        """J6 后段 + §6.3：P1 只报告不处置——restore 对篡改快照仍纯函数还原，
        迁移/回退行为属 P8（Spec §44 content/migrations.py）。"""
        tampered = _snapshot_tampered(lambda d: d.update({"contract_schema_version": 99}))
        assert check_snapshot_versions(tampered) != ()
        restored_ws, restored_rt = restore_snapshot(tampered)
        assert restored_ws == tampered.world_state
        assert restored_rt == tampered.runtime_state


# —— J5 深冻结视图（freeze_view，决策 D-15）——


class TestFreezeView:
    def test_freeze_view_structure(self) -> None:
        value = {
            "a": 1,
            "b": {"c": [1, 2, {"d": "x"}]},
            "e": None,
            "f": "s",
            "g": 1.5,
            "h": True,
        }
        view = freeze_view(value)
        assert isinstance(view, MappingProxyType)
        assert isinstance(view["b"], MappingProxyType)
        assert isinstance(view["b"]["c"], tuple)
        assert isinstance(view["b"]["c"][2], MappingProxyType)
        assert view["a"] == 1
        assert view["e"] is None
        assert view["g"] == 1.5
        assert view["h"] is True

    def test_freeze_view_top_level_list_and_scalar(self) -> None:
        view = freeze_view([1, [2, {"k": 3}]])
        assert isinstance(view, tuple)
        assert isinstance(view[1], tuple)
        assert isinstance(view[1][1], MappingProxyType)
        # 标量直通
        assert freeze_view("x") == "x"
        assert freeze_view(None) is None
        assert freeze_view(3) == 3
        assert freeze_view(1.5) == 1.5
        assert freeze_view(True) is True

    def test_freeze_view_assignment_raises_all_levels(self) -> None:
        """J5：赋值抛错，嵌套层同样抛错。"""
        value = {"a": {"b": [1, 2]}, "top": [3]}
        view = freeze_view(value)
        with pytest.raises(TypeError):
            view["a"] = 1
        with pytest.raises(TypeError):
            view["a"]["b"] = [3]
        with pytest.raises(TypeError):
            view["a"]["b"][0] = 9
        with pytest.raises(TypeError):
            view["top"][0] = 4
        # 源数据未被冻结/未受影响
        assert value == {"a": {"b": [1, 2]}, "top": [3]}
        value["a"]["b"][0] = 99  # 源仍是普通可变结构
        assert value["a"]["b"][0] == 99

    def test_freeze_view_model_dump_deep_frozen(self) -> None:
        dump = _make_world_state().model_dump(mode="json")
        view = freeze_view(dump)
        with pytest.raises(TypeError):
            view["world_variables"]["k"] = 1
        with pytest.raises(TypeError):
            view["entities"]["ent_test_alice"]["components"]["space.position"]["x"] = 9

    def test_entity_view_uses_same_freeze_semantics(self) -> None:
        """D-15 单一实现：EntityView 组件视图与 freeze_view 同一冻结语义。"""
        ws = _make_world_state()
        view = ws.entity_view(EntityId("ent_test_alice"))
        assert view is not None
        comp = view.get_component(ComponentTypeId("space.position"))
        assert isinstance(comp, MappingProxyType)
        assert isinstance(comp["z"], tuple)
        with pytest.raises(TypeError):
            comp["x"] = 9
        with pytest.raises(TypeError):
            comp["z"][0] = 1


# —— J7 Unicode / 边界值 ——


class TestUnicodeAndBoundaryValues:
    def test_chinese_roundtrip_no_ascii_escape(self) -> None:
        proposal = _make_proposal()
        text = dump_json(proposal)
        assert proposal.intent in text
        assert "\\u" not in text
        rebuilt = load_json(ActionProposal, text)
        assert rebuilt.intent == proposal.intent
        assert rebuilt.provenance.notes == proposal.provenance.notes

    def test_empty_containers_roundtrip(self) -> None:
        empty_ws = WorldState()
        assert empty_ws.entities == {}
        assert empty_ws.world_variables == {}
        rebuilt = load_json(WorldState, dump_json(empty_ws))
        assert rebuilt == empty_ws
        empty_rt = RuntimeState()
        rebuilt_rt = load_json(RuntimeState, dump_json(empty_rt))
        assert rebuilt_rt == empty_rt

    def test_big_int_exact(self) -> None:
        big = 10**30 + 123456789
        ws = _make_world_state()
        data = json.loads(dump_json(ws))
        data["world_variables"]["big"] = big
        rebuilt = load_json(WorldState, json.dumps(data))
        assert rebuilt.world_variables["big"] == big
        assert type(rebuilt.world_variables["big"]) is int

    def test_float_extremes_exact(self) -> None:
        ws = _make_world_state()  # 样本已含 5e-324 与 sys.float_info.max
        rebuilt = load_json(WorldState, dump_json(ws))
        assert rebuilt.world_variables["tiny_float"] == 5e-324
        assert rebuilt.world_variables["max_float"] == sys.float_info.max
        assert rebuilt.world_variables["max_float"] == -(-sys.float_info.max)

    def test_datetime_iso_roundtrip(self) -> None:
        wall = datetime(2025, 6, 1, 12, 30, 45, 123456, tzinfo=timezone.utc)
        event = _make_domain_event()
        rebuilt = load_json(DomainEvent, dump_json(event))
        assert rebuilt.wall_time == wall
        assert type(rebuilt.wall_time) is datetime
        raw = json.loads(dump_json(event))
        # UTC 墙钟以 ISO-8601 落盘（pydantic 对 tz-aware UTC 输出 "Z" 后缀）
        assert raw["wall_time"] in (
            "2025-06-01T12:30:45.123456Z",
            "2025-06-01T12:30:45.123456+00:00",
        )


# —— 模块导出与 import 边界（§0.3 / §1.1 / B1 / B2）——


class TestModuleExportsAndImportBoundary:
    def test_serialization_module_exports_exact(self) -> None:
        assert set(serialization_module.__all__) == {
            "dump_json",
            "load_json",
            "assert_json_clean",
            "deep_copy_via_roundtrip",
        }

    def test_snapshot_module_exports_exact(self) -> None:
        assert set(snapshot_module.__all__) == {
            "CONTRACT_SCHEMA_VERSION",
            "SNAPSHOT_FORMAT_VERSION",
            "Snapshot",
            "snapshot",
            "restore_snapshot",
            "check_snapshot_versions",
            "freeze_view",
        }

    _STDLIB = {
        "__future__",
        "collections",  # collections.abc
        "datetime",
        "enum",
        "json",
        "math",
        "typing",
    }

    @pytest.mark.parametrize(
        "module",
        [serialization_module, snapshot_module],
        ids=["serialization", "snapshot"],
    )
    def test_only_whitelisted_imports(self, module: Any) -> None:
        """B1：AST 白名单扫描——只允许标准库 + pydantic + 同包 src.engine_v2。"""
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        violations: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root == "src":
                        assert alias.name.startswith("src.engine_v2"), (
                            f"同包 import 必须指向 src.engine_v2，得到 {alias.name}"
                        )
                    elif root not in self._STDLIB | {"pydantic"}:
                        violations.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                root = node.module.split(".")[0]
                if root == "src":
                    assert node.module.startswith("src.engine_v2"), (
                        f"同包 import 必须指向 src.engine_v2，得到 {node.module}"
                    )
                elif root not in self._STDLIB | {"pydantic"}:
                    violations.add(node.module)
        assert not violations, f"白名单外 import：{violations}"

    def test_fresh_import_pulls_no_forbidden_modules(self) -> None:
        """B2：fresh import 的 sys.modules 增量不含任何禁止依赖。"""
        forbidden = (
            "langgraph",
            "langchain",
            "openai",
            "rich",
            "yaml",
            "requests",
            "httpx",
            "socket",
            "subprocess",
        )
        module_names = ("src.engine_v2.core.serialization", "src.engine_v2.core.snapshot")
        for name in module_names:
            sys.modules.pop(name, None)
        before = set(sys.modules)
        for name in module_names:
            importlib.import_module(name)
        pulled = set(sys.modules) - before
        bad = sorted(
            name
            for name in pulled
            if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden)
        )
        assert not bad, f"import serialization/snapshot 过程中新载入了禁止依赖：{bad}"
