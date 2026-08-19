"""P1-T02 单元测试：状态容器与 Trace 记录契约（设计文档 §7.3 S1–S5 口径）。

覆盖（对齐 ``docs/v2/contracts/P1-core-data-contracts.md`` §7.3 与任务包要求）：

- **S1 round-trip**：WorldState / RuntimeState / BackendStateRef /
  TraceRecord（各 kind 代表样本，12 种全参数化）
  ``model_validate(model_dump(mode="json"))`` 值相等 + 类型保持
  （EntityId/ActionInstanceId dict 键、Revision、枚举、各 ID 族）+ JSON 纯净；
- **S2 snapshot/trace 归属**（§4.3 归属总表的程序化断言）：WorldState /
  RuntimeState 字段集合与设计文档一致且不含 trace/view/瞬态数据；
  TraceRecord 不含状态本体；BackendState 只以 ref + 能力声明进快照（D-10）；
  WorldState/RuntimeState 均不内嵌 world_instance_id（D-9）；
- **S3 占位字段纪律**：RuntimeState 占位字段默认空且 round-trip 保持；
  state.py 不导出任何调度语义函数（模块级零公共函数）；
- **S4 BackendStateRef**：三项能力声明默认 False；checkpoint_ref 可空；
- **S5 frozen**：WorldState/RuntimeState 等全部 T02 模型字段赋值抛错；
- **零公共 mutator 静态断言**：全部 T02 模型 ``vars(cls)`` 扫描无 mutator
  前缀方法名；WorldState 公共面 = 四个只读门面方法；
- **§3.5 reducer-only 纪律**：``_with_*`` 私有构造缝隙（新实例、self 不变、
  零别名、整体替换、不导出）；入口深拷贝隔离（J3 口径）；
- **决策 D-6 / KBC-4 日历时间完整性**：日历时间结构化承载于
  ``world_variables``，round-trip 后 day 不丢失；RuntimeState 只有单一
  ``logical_tick``，无任何日历字段（不存在可部分覆写的复合时钟）；
  world_variables 缝隙为整体替换（无部分覆写形态）；
- **RNG state 可序列化**：RngState 单独与内嵌 RuntimeState 的 round-trip；
- **TraceKind 判别**：12 成员词表与 §4.4 逐项一致；非法 kind 拒绝；
  payload 键名约定常量（record / decision 三键 / llm_call 九键，credential
  永不入内）；内嵌完整契约模型（transaction/domain_event/proposal/effect）
  可离线还原；
- **extra=forbid / 严格 Optional**（J2/KBC-7 口径）：未知字段拒绝；None 与
  0/空 dict 不可互换；
- **import 边界**（§0.3 / B1/B2）：state.py / trace.py AST 白名单扫描 +
  fresh import sys.modules 增量无禁止依赖。

全部用例无网络、无 LLM、无 API key（Spec §47 Phase 1 验收）。
"""

from __future__ import annotations

import ast
import importlib
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import src.engine_v2.core.state as state_module
import src.engine_v2.core.trace as trace_module
from src.engine_v2.core.actions import (
    ActionLifecycleStatus,
    ActionProposal,
    ActionTypeId,
    ActiveAction,
)
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.effects import (
    CommittedEffect,
    EffectId,
    EffectTypeId,
    EntityTarget,
    ProposedEffect,
)
from src.engine_v2.core.entity import ContractModel, EntityRecord
from src.engine_v2.core.events import DomainEvent, EventTypeId
from src.engine_v2.core.ids import (
    ActionInstanceId,
    CascadeId,
    EntityId,
    EventId,
    ObservationId,
    ProducerId,
    ScheduledEntryId,
    TraceRecordId,
    TransactionId,
)
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.revision import INITIAL_WORLD_REVISION, Revision
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
from src.engine_v2.core.trace import (
    DECISION_PAYLOAD_KEYS,
    LLM_CALL_PAYLOAD_KEYS,
    PAYLOAD_RECORD_KEY,
    TraceKind,
    TraceRecord,
)
from src.engine_v2.core.transaction import Transaction, TransactionStatus


# —— 测试助手 ——


def _assert_json_clean(value: Any) -> None:
    """递归断言仅含 JSON 原生类型（§0.2 铁律 1；T05 提供正式工具，此处为 T02 自测口径）。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for item in value:
            _assert_json_clean(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str), f"dict 键必须为 str，得到 {type(key).__name__}"
            _assert_json_clean(item)
        return
    raise AssertionError(f"非 JSON 原生类型：{type(value).__name__}")


def _provenance() -> Provenance:
    return Provenance(producer_id=ProducerId("policy.alice"), origin=OriginKind.BEHAVIOR_POLICY)


def _sample_proposal() -> ActionProposal:
    """Spec §9 示例口径（base_world_revision=812、observation_id=obs_991）。"""
    return ActionProposal(
        proposal_id=ActionInstanceId("act_test_1"),
        actor_id=EntityId("ent_test_alice"),
        action_id=ActionTypeId("rest"),
        arguments={"地点": "客栈"},
        intent="休息恢复体力",
        confidence=0.75,
        base_world_revision=Revision(812),
        observation_id=ObservationId("obs_991"),
        provenance=_provenance(),
    )


def _sample_active_action() -> ActiveAction:
    return ActiveAction(
        instance_id=ActionInstanceId("act_test_1"),
        action_id=ActionTypeId("rest"),
        actor_id=EntityId("ent_test_alice"),
        status=ActionLifecycleStatus.ACTIVE,
        start_tick=10,
        expected_end_tick=15,
        progress=0.5,
        base_world_revision=Revision(812),
        provenance=_provenance(),
    )


def _sample_proposed_effect() -> ProposedEffect:
    return ProposedEffect(
        effect_id=EffectId("eff_test_1"),
        effect_type=EffectTypeId("unlock"),
        source=ProducerId("rule.lock_system"),
        target=EntityTarget(entity_id=EntityId("ent_test_alice")),
        payload={"locked": False},
        base_revision=Revision(812),
    )


def _sample_transaction() -> Transaction:
    txn_id = TransactionId("txn_test_1")
    commit = Revision(813)
    return Transaction(
        transaction_id=txn_id,
        status=TransactionStatus.COMMITTED,
        base_revision=Revision(812),
        commit_revision=commit,
        logical_tick=42,
        effects=[
            CommittedEffect(
                effect=_sample_proposed_effect(),
                transaction_id=txn_id,
                commit_revision=commit,
                sequence=0,
            )
        ],
    )


def _sample_domain_event() -> DomainEvent:
    return DomainEvent(
        event_id=EventId("evt_test_1"),
        event_type=EventTypeId("door.unlocked"),
        world_revision=Revision(813),
        logical_tick=42,
        transaction_id=TransactionId("txn_test_1"),
        payload={"door": "城门"},
        source_system=ProducerId("rule.lock_system"),
        provenance=Provenance(producer_id=ProducerId("rule.lock_system"), origin=OriginKind.RULE),
    )


def _sample_world_state() -> WorldState:
    """完整样本：entities/components/world variables/scenario state + 日历时间。"""
    return WorldState.model_validate(
        {
            "world_revision": 812,
            "entities": {
                "ent_test_alice": {
                    "entity_id": "ent_test_alice",
                    "entity_class": "npc.villager",
                    "tags": ["ally", "村庄守卫"],
                    "created_revision": 3,
                    "components": {
                        "space.position": {"x": 1.5, "y": -2, "grid": [0, 1]},
                        "knowledge.memory": {"events": [{"what": "见到 bob", "day": 2}]},
                    },
                },
                "ent_test_bob": {"entity_id": "ent_test_bob", "tags": ["merchant"]},
            },
            "world_variables": {
                # 日历时间：结构化完整承载（决策 D-6；KBC-4 防线样本）
                "calendar_time": {"day": 3, "hour": 7, "minute": 15},
                "weather": "晴",
            },
            "scenario_state": {
                "scenario_id": "scn_demo",
                "stage": "act_1",
                "data": {"flags": ["gate_open"], "count": 2},
            },
        }
    )


def _sample_runtime_state() -> RuntimeState:
    """完整样本：Spec §8.2 全部字段在场（占位字段以真实结构承载）。"""
    return RuntimeState(
        logical_tick=42,
        lifecycle=RuntimeLifecycle.RUNNING,
        scheduler_queue=[
            ScheduledEvent(
                entry_id=ScheduledEntryId("sch_test_1"),
                due_tick=44,
                kind="action_checkpoint",
                payload={"instance_id": "act_test_1"},
            )
        ],
        active_actions={ActionInstanceId("act_test_1"): _sample_active_action()},
        actor_wakeups=[
            ActorWakeup(actor_id=EntityId("ent_test_alice"), due_tick=50, reason="日常作息")
        ],
        active_modes=["exploration"],
        mode_context={"exploration": {"pace": "free"}},
        rng_state=RngState(algorithm="pcg32", state={"seed": 12345, "counter": 7}),
        pending_proposals=[_sample_proposal()],
        backend_refs={
            "backend_dynamics_1": BackendStateRef(
                backend_id="backend_dynamics_1",
                backend_kind="dynamics",
                checkpointable=True,
                restorable=True,
                replayable=False,
                checkpoint_ref="ckpt://dynamics/42",
                metadata={"version": "1.0"},
            )
        },
    )


def _payload_for_kind(kind: TraceKind) -> dict[str, Any]:
    """按 §4.4 payload 子约定为每种 kind 构造代表样本。"""
    if kind is TraceKind.ACTION_PROPOSAL:
        return {PAYLOAD_RECORD_KEY: _sample_proposal().model_dump(mode="json")}
    if kind is TraceKind.PROPOSED_EFFECT:
        return {PAYLOAD_RECORD_KEY: _sample_proposed_effect().model_dump(mode="json")}
    if kind is TraceKind.TRANSACTION:
        return {PAYLOAD_RECORD_KEY: _sample_transaction().model_dump(mode="json")}
    if kind is TraceKind.DOMAIN_EVENT:
        return {PAYLOAD_RECORD_KEY: _sample_domain_event().model_dump(mode="json")}
    if kind in (
        TraceKind.AUTHORITY_DECISION,
        TraceKind.VALIDATION_DECISION,
        TraceKind.CONFLICT_RESOLUTION,
    ):
        return {"effect_id": "eff_test_1", "decision": "allow", "reason": "authority 域匹配"}
    if kind is TraceKind.LLM_CALL:
        return {
            "logical_role": "npc_decision",
            "profile": "profile_a",
            "resolved_model": "model_a",
            "input_token_estimate": 512,
            "prompt_metadata_ref": "trc_prompt_1",
            "output_ref": "trc_output_1",
            "latency_ms": 1234,
            "parse_retry": 0,
            "base_revision": 812,
        }
    if kind is TraceKind.DEV_INTERVENTION:
        return {"origin": OriginKind.DEVELOPER.value, "command": "将 lifecycle 置为 paused"}
    # command / prompt_assembly / system：开放 payload
    return {"note": "示例记录"}


# —— S1 / WorldState 字段契约与 round-trip ——


class TestWorldStateFieldContract:
    """WorldState 字段契约（设计文档 §4.1）与数据完整性。"""

    def test_field_set_matches_design(self) -> None:
        assert set(WorldState.model_fields) == {
            "schema_version",
            "world_revision",
            "entities",
            "world_variables",
            "scenario_state",
        }

    def test_world_instance_id_not_embedded_d9(self) -> None:
        """D-9：WorldState/RuntimeState 本体不内嵌 world_instance_id（信封层职责）。"""
        assert "world_instance_id" not in WorldState.model_fields
        assert "world_instance_id" not in RuntimeState.model_fields

    def test_defaults(self) -> None:
        ws = WorldState()
        assert ws.schema_version == CONTRACT_SCHEMA_VERSION == 1
        assert ws.world_revision == INITIAL_WORLD_REVISION
        assert type(ws.world_revision) is Revision
        assert ws.entities == {}
        assert ws.world_variables == {}
        assert ws.scenario_state == ScenarioState()

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            WorldState(bogus_field=1)  # type: ignore[call-overload]

    def test_entity_key_mismatch_rejected(self) -> None:
        """entities 键与 EntityRecord.entity_id 不一致 → 数据层拒绝（防 KBC-3 同型分裂）。"""
        rec = EntityRecord(entity_id=EntityId("ent_a"))
        with pytest.raises(ValidationError, match="不一致"):
            WorldState(entities={EntityId("ent_b"): rec})


class TestWorldStateRoundtrip:
    """S1：WorldState JSON round-trip（值相等 + 类型保持 + JSON 纯净 + Unicode）。"""

    def test_roundtrip_full(self) -> None:
        ws = _sample_world_state()
        dumped = ws.model_dump(mode="json")
        _assert_json_clean(dumped)
        # §0.2 铁律 2：Revision 纯整数、typed ID 纯字符串（含 dict 键）
        assert type(dumped["world_revision"]) is int
        assert dumped["world_revision"] == 812
        assert all(type(k) is str for k in dumped["entities"])
        reloaded = WorldState.model_validate(dumped)
        assert reloaded == ws
        assert type(reloaded.world_revision) is Revision
        for key, record in reloaded.entities.items():
            assert type(key) is EntityId
            assert type(record.entity_id) is EntityId
            assert key == record.entity_id
            assert all(type(ct) is ComponentTypeId for ct in record.components)
        assert reloaded.scenario_state == ws.scenario_state
        assert reloaded.world_variables == ws.world_variables

    def test_json_text_roundtrip_unicode(self) -> None:
        ws = _sample_world_state()
        text = ws.model_dump_json(ensure_ascii=False)
        assert "村庄守卫" in text, "ensure_ascii=False：中文不得被转义"
        assert WorldState.model_validate_json(text) == ws

    def test_entry_deep_copy_isolation(self) -> None:
        """J3 口径：构造后修改传入的原始 dict → WorldState 不受影响（§3.5 纪律 2）。"""
        source: dict[str, Any] = {"x": 1, "nested": {"z": 3}}
        ws = WorldState.model_validate(
            {
                "entities": {
                    "ent_iso": {"entity_id": "ent_iso", "components": {"space.position": source}}
                },
                "world_variables": {"calendar_time": {"day": 1, "hour": 0, "minute": 0}},
            }
        )
        source["x"] = 999
        source["nested"]["z"] = 42
        comp = ws.entities[EntityId("ent_iso")].components[ComponentTypeId("space.position")]
        assert comp["x"] == 1
        assert comp["nested"]["z"] == 3
        assert comp is not source


class TestWorldStateFacade:
    """§4.1 只读门面：entity_view / component_view / entities_with_component / has_entity。"""

    def test_entity_view_carries_world_revision_and_deep_freeze(self) -> None:
        ws = _sample_world_state()
        view = ws.entity_view(EntityId("ent_test_alice"))
        assert view is not None
        assert view.revision == Revision(812)
        assert type(view.revision) is Revision
        assert view.entity_class == "npc.villager"
        comp = view.get_component(ComponentTypeId("space.position"))
        assert comp is not None
        with pytest.raises(TypeError):
            comp["x"] = 0  # type: ignore[index]

    def test_entity_view_missing_returns_none(self) -> None:
        ws = _sample_world_state()
        assert ws.entity_view(EntityId("ent_missing")) is None

    def test_component_view_hit_and_miss(self) -> None:
        ws = _sample_world_state()
        assert ws.component_view(EntityId("ent_test_alice"), ComponentTypeId("knowledge.memory")) is not None
        assert ws.component_view(EntityId("ent_missing"), ComponentTypeId("space.position")) is None
        assert ws.component_view(EntityId("ent_test_alice"), ComponentTypeId("no.such")) is None

    def test_entities_with_component_result_and_order(self) -> None:
        ws = _sample_world_state()
        assert ws.entities_with_component(ComponentTypeId("space.position")) == (
            EntityId("ent_test_alice"),
        )
        assert ws.entities_with_component(ComponentTypeId("no.such")) == ()
        # bob 无组件
        assert ws.entities_with_component(ComponentTypeId("knowledge.memory")) == (
            EntityId("ent_test_alice"),
        )

    def test_has_entity(self) -> None:
        ws = _sample_world_state()
        assert ws.has_entity(EntityId("ent_test_bob")) is True
        assert ws.has_entity(EntityId("ent_missing")) is False

    def test_public_surface_is_four_readonly_facade(self) -> None:
        """WorldState 公共面 = §4.1 四个只读门面方法（无任何写方法）。"""
        public_methods = {
            name for name, value in vars(WorldState).items()
            if not name.startswith("_") and callable(value)
        }
        assert public_methods == {
            "entity_view",
            "component_view",
            "entities_with_component",
            "has_entity",
        }


class TestWorldStateReducerOnlySeams:
    """§3.5 reducer-only 纪律：零公共 mutator + _with_* 私有构造缝隙。"""

    def test_with_world_revision_new_instance_self_unchanged(self) -> None:
        ws = _sample_world_state()
        ws2 = ws._with_world_revision(Revision(813))
        assert ws2 is not ws
        assert ws2.world_revision == Revision(813)
        assert type(ws2.world_revision) is Revision
        assert ws.world_revision == Revision(812), "self 不变（frozen）"
        assert ws2.entities == ws.entities
        assert WorldState.model_validate(ws2.model_dump(mode="json")) == ws2

    def test_with_entities_whole_replacement_zero_alias(self) -> None:
        ws = _sample_world_state()
        fresh = EntityRecord(
            entity_id=EntityId("ent_new"),
            components={ComponentTypeId("space.position"): {"x": 1}},
        )
        ws2 = ws._with_entities({fresh.entity_id: fresh})
        # 整体替换：旧 entities 不残留
        assert set(ws2.entities) == {EntityId("ent_new")}
        assert set(ws.entities) == {EntityId("ent_test_alice"), EntityId("ent_test_bob")}
        # 零别名：构造后改动调用方记录 → 新状态不受影响
        fresh.components[ComponentTypeId("space.position")]["x"] = 999
        view = ws2.component_view(EntityId("ent_new"), ComponentTypeId("space.position"))
        assert view is not None and view["x"] == 1

    def test_with_entities_key_mismatch_rejected(self) -> None:
        ws = _sample_world_state()
        mismatched = EntityRecord(entity_id=EntityId("ent_other"))
        with pytest.raises(ValidationError, match="不一致"):
            ws._with_entities({EntityId("ent_key"): mismatched})

    def test_with_world_variables_whole_replacement(self) -> None:
        """KBC-4 防线的数据形态：整体替换，无部分覆写/合并语义。"""
        ws = _sample_world_state()
        new_calendar = {"day": 4, "hour": 0, "minute": 0}
        ws2 = ws._with_world_variables({"calendar_time": new_calendar})
        assert ws2.world_variables == {"calendar_time": new_calendar}
        assert "weather" not in ws2.world_variables, "整体替换：旧键不残留"
        assert ws.world_variables["calendar_time"]["day"] == 3, "self 不变"

    def test_with_world_variables_entry_deep_copy(self) -> None:
        ws = _sample_world_state()
        incoming: dict[str, Any] = {"calendar_time": {"day": 5, "hour": 1, "minute": 2}}
        ws2 = ws._with_world_variables(incoming)
        incoming["calendar_time"]["day"] = 999
        assert ws2.world_variables["calendar_time"]["day"] == 5

    def test_with_scenario_state_replacement_zero_alias(self) -> None:
        ws = _sample_world_state()
        fresh = ScenarioState(scenario_id="scn_next", stage="act_2", data={"flag": True})
        ws2 = ws._with_scenario_state(fresh)
        assert ws2.scenario_state == fresh
        assert ws.scenario_state.scenario_id == "scn_demo", "self 不变"
        assert WorldState.model_validate(ws2.model_dump(mode="json")) == ws2

    def test_seams_are_private_not_exported(self) -> None:
        seams = (
            "_with_world_revision",
            "_with_entities",
            "_with_world_variables",
            "_with_scenario_state",
        )
        for name in seams:
            assert hasattr(WorldState, name), f"缺少私有构造缝隙 {name}"
            assert name not in state_module.__all__, "缝隙不得导出为公共 API"


class TestScenarioState:
    """ScenarioState（§4.1）：Kernel 只给信封，语义归 P9。"""

    def test_defaults_and_roundtrip(self) -> None:
        sc = ScenarioState()
        assert sc.scenario_id is None
        assert sc.stage is None
        assert sc.data == {}
        reloaded = ScenarioState.model_validate(sc.model_dump(mode="json"))
        assert reloaded == sc
        assert reloaded.scenario_id is None  # KBC-7：None 保持

    def test_full_roundtrip(self) -> None:
        sc = ScenarioState(scenario_id="scn_demo", stage="act_1", data={"flags": ["a"]})
        dumped = sc.model_dump(mode="json")
        _assert_json_clean(dumped)
        assert ScenarioState.model_validate(dumped) == sc

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            ScenarioState(bogus=1)  # type: ignore[call-overload]


# —— 决策 D-6 / KBC-4：日历时间完整性 ——


class TestCalendarTimeKbc4:
    """D-6 时间语义 + KBC-4 防线：日历时间结构化完整，day 不丢失。"""

    _CALENDAR_FIELD_NAMES = {
        "day",
        "hour",
        "minute",
        "calendar",
        "calendar_time",
        "game_time",
        "date",
        "time_of_day",
    }

    def test_calendar_in_world_variables_roundtrip_keeps_day(self) -> None:
        ws = _sample_world_state()
        dumped = ws.model_dump(mode="json")
        assert dumped["world_variables"]["calendar_time"] == {"day": 3, "hour": 7, "minute": 15}
        reloaded = WorldState.model_validate(dumped)
        calendar = reloaded.world_variables["calendar_time"]
        assert calendar == {"day": 3, "hour": 7, "minute": 15}
        assert calendar["day"] == 3, "KBC-4：day 键不得在 round-trip 中丢失"

    def test_runtime_state_has_no_calendar_fields(self) -> None:
        """D-6：日历时间不是 RuntimeState 字段（它是世界事实，归 WorldState）。"""
        assert not (set(RuntimeState.model_fields) & self._CALENDAR_FIELD_NAMES)

    def test_runtime_state_single_logical_clock(self) -> None:
        """D-6：RuntimeState 只有单一 logical_tick——无可被部分覆写的复合时钟。"""
        tick_fields = [name for name in RuntimeState.model_fields if "tick" in name]
        assert tick_fields == ["logical_tick"]

    def test_no_partial_override_seam_for_world_variables(self) -> None:
        """v1 KBC-4 的直接成因是部分 dict 覆写；WorldState 不提供任何部分更新 API。"""
        partial_update_names = {
            name
            for name in vars(WorldState)
            if not name.startswith("__")
            and name.startswith(("update_", "set_", "patch_", "merge_", "apply_partial_"))
        }
        assert partial_update_names == set()


# —— S3 / S5 / RuntimeState 字段契约与 round-trip ——


class TestRuntimeStateFieldContract:
    """RuntimeState 字段契约（设计文档 §4.2，与 Spec §8.2 清单一一对应）。"""

    def test_field_set_matches_design(self) -> None:
        assert set(RuntimeState.model_fields) == {
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

    def test_placeholder_fields_default_empty(self) -> None:
        """S3：占位字段默认空；schema_version 与 CONTRACT_SCHEMA_VERSION 一致。"""
        rt = RuntimeState()
        assert rt.schema_version == CONTRACT_SCHEMA_VERSION == 1
        assert rt.logical_tick == 0
        assert rt.lifecycle is RuntimeLifecycle.CREATED
        assert rt.scheduler_queue == []
        assert rt.active_actions == {}
        assert rt.actor_wakeups == []
        assert rt.active_modes == []
        assert rt.mode_context == {}
        assert rt.rng_state is None
        assert rt.pending_proposals == []
        assert rt.backend_refs == {}

    def test_placeholder_empties_survive_roundtrip(self) -> None:
        rt = RuntimeState()
        reloaded = RuntimeState.model_validate(rt.model_dump(mode="json"))
        assert reloaded == rt
        assert reloaded.scheduler_queue == []
        assert reloaded.pending_proposals == []
        assert reloaded.backend_refs == {}
        assert reloaded.rng_state is None

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            RuntimeState(bogus_field=1)  # type: ignore[call-overload]

    def test_invalid_lifecycle_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RuntimeState.model_validate({"lifecycle": "bogus"})

    def test_active_action_key_mismatch_rejected(self) -> None:
        action = _sample_active_action()
        with pytest.raises(ValidationError, match="不一致"):
            RuntimeState(active_actions={ActionInstanceId("act_other"): action})

    def test_no_seams_or_scheduler_methods_in_p1(self) -> None:
        """占位纪律：P1 不为 RuntimeState 提供构造缝隙/调度方法（语义属 P3）。"""
        offending = [
            name
            for name in vars(RuntimeState)
            if name.startswith("_with")
            or name.startswith(("schedule", "trigger", "merge", "advance", "dispatch"))
        ]
        assert offending == []


class TestRuntimeStateRoundtrip:
    """S1：RuntimeState JSON round-trip（全字段样本 + 类型保持）。"""

    def test_roundtrip_full(self) -> None:
        rt = _sample_runtime_state()
        dumped = rt.model_dump(mode="json")
        _assert_json_clean(dumped)
        assert dumped["lifecycle"] == "running"
        assert type(dumped["logical_tick"]) is int
        assert all(type(k) is str for k in dumped["active_actions"])
        reloaded = RuntimeState.model_validate(dumped)
        assert reloaded == rt
        assert type(reloaded.lifecycle) is RuntimeLifecycle
        key = next(iter(reloaded.active_actions))
        assert type(key) is ActionInstanceId
        assert reloaded.active_actions[key].status is ActionLifecycleStatus.ACTIVE
        assert type(reloaded.scheduler_queue[0].entry_id) is ScheduledEntryId
        assert type(reloaded.actor_wakeups[0].actor_id) is EntityId
        assert type(reloaded.pending_proposals[0].proposal_id) is ActionInstanceId
        assert type(reloaded.pending_proposals[0].base_world_revision) is Revision
        assert reloaded.rng_state is not None
        assert reloaded.rng_state.algorithm == "pcg32"
        ref = reloaded.backend_refs["backend_dynamics_1"]
        assert type(ref) is BackendStateRef
        assert ref.checkpointable is True
        assert ref.replayable is False
        assert ref.checkpoint_ref == "ckpt://dynamics/42"

    def test_json_text_roundtrip_unicode(self) -> None:
        rt = _sample_runtime_state()
        text = rt.model_dump_json(ensure_ascii=False)
        assert "日常作息" in text
        assert RuntimeState.model_validate_json(text) == rt


class TestRuntimeLifecycle:
    """生命周期词表（§4.2；Spec §8.2）。"""

    def test_vocabulary_matches_design(self) -> None:
        assert {member.value for member in RuntimeLifecycle} == {
            "created",
            "running",
            "paused",
            "stepping",
            "stopped",
        }
        assert len(RuntimeLifecycle) == 5

    def test_default_is_created(self) -> None:
        assert RuntimeState().lifecycle is RuntimeLifecycle.CREATED


class TestRngState:
    """RNG state（§4.2）：可序列化，算法不固定。"""

    def test_algorithm_required(self) -> None:
        with pytest.raises(ValidationError):
            RngState.model_validate({"state": {"seed": 1}})

    def test_roundtrip_and_json_clean(self) -> None:
        rng = RngState(algorithm="mt19937", state={"seed": 42, "mt": list(range(8)), "index": 3})
        dumped = rng.model_dump(mode="json")
        _assert_json_clean(dumped)
        reloaded = RngState.model_validate(dumped)
        assert reloaded == rng
        assert reloaded.state["mt"] == list(range(8))

    def test_state_default_empty(self) -> None:
        assert RngState(algorithm="pcg32").state == {}

    def test_within_runtime_state_serializable(self) -> None:
        rt = RuntimeState(rng_state=RngState(algorithm="pcg32", state={"seed": 7}))
        text = rt.model_dump_json(ensure_ascii=False)
        assert RuntimeState.model_validate_json(text) == rt


class TestScheduledEventAndActorWakeup:
    """调度队列条目与 actor wakeups 占位（§4.2；语义属 P3/P4）。"""

    def test_scheduled_event_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            ScheduledEvent.model_validate({"due_tick": 1, "kind": "wakeup"})

    def test_scheduled_event_roundtrip_and_defaults(self) -> None:
        ev = ScheduledEvent(entry_id=ScheduledEntryId("sch_test_9"), due_tick=9, kind="wakeup")
        assert ev.payload == {}
        dumped = ev.model_dump(mode="json")
        _assert_json_clean(dumped)
        reloaded = ScheduledEvent.model_validate(dumped)
        assert reloaded == ev
        assert type(reloaded.entry_id) is ScheduledEntryId

    def test_actor_wakeup_roundtrip_and_none_reason_preserved(self) -> None:
        wakeup = ActorWakeup(actor_id=EntityId("ent_test_alice"), due_tick=9)
        assert wakeup.reason is None
        reloaded = ActorWakeup.model_validate(wakeup.model_dump(mode="json"))
        assert reloaded == wakeup
        assert reloaded.reason is None  # KBC-7：None 不被改写
        assert type(reloaded.actor_id) is EntityId


class TestBackendStateRef:
    """S4：BackendStateRef（决策 D-10 / ADR-003）——仅 ref + 三项能力声明。"""

    def test_defaults_capabilities_false(self) -> None:
        ref = BackendStateRef(backend_id="backend_1", backend_kind="dynamics")
        assert ref.checkpointable is False
        assert ref.restorable is False
        assert ref.replayable is False
        assert ref.checkpoint_ref is None
        assert ref.metadata == {}

    def test_roundtrip_with_capabilities(self) -> None:
        ref = BackendStateRef(
            backend_id="backend_2",
            backend_kind="inference_host",
            checkpointable=True,
            restorable=True,
            replayable=True,
            checkpoint_ref="ckpt://infer/9",
            metadata={"index": 0},
        )
        dumped = ref.model_dump(mode="json")
        _assert_json_clean(dumped)
        reloaded = BackendStateRef.model_validate(dumped)
        assert reloaded == ref
        assert reloaded.checkpointable is True

    def test_required_backend_id_and_kind(self) -> None:
        with pytest.raises(ValidationError):
            BackendStateRef(backend_id="only_id")  # type: ignore[call-overload]

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            BackendStateRef(backend_id="b", backend_kind="space", gpu_buffer="<opaque>")  # type: ignore[call-overload]

    def test_frozen_blocks_assignment(self) -> None:
        ref = BackendStateRef(backend_id="b", backend_kind="space")
        with pytest.raises((ValidationError, TypeError)):
            ref.checkpointable = True  # type: ignore[misc]


# —— S2：snapshot/trace 归属总表（§4.3）程序化断言 ——


class TestSnapshotTraceAttribution:
    """§4.3 归属总表：哪些字段进 snapshot、哪些进 trace。"""

    #: v1 瞬态/呈现结构（设计文档 §8 非目标 4）不得进入状态容器
    _TRANSIENT_PRESENTATION_NAMES = {
        "event_log",
        "narrative_history",
        "player_percept",
        "attribute_deltas",
        "trace",
        "trace_records",
        "view",
        "view_state",
        "commands",
    }

    def test_world_state_carries_no_trace_or_view_data(self) -> None:
        assert not (set(WorldState.model_fields) & self._TRANSIENT_PRESENTATION_NAMES)

    def test_runtime_state_carries_no_trace_or_view_data(self) -> None:
        assert not (set(RuntimeState.model_fields) & self._TRANSIENT_PRESENTATION_NAMES)

    def test_trace_record_field_set_and_no_state_body(self) -> None:
        assert set(TraceRecord.model_fields) == {
            "record_id",
            "kind",
            "world_revision",
            "logical_tick",
            "wall_time",
            "producer_id",
            "transaction_id",
            "cascade_id",
            "payload",
        }
        state_body = {
            "entities",
            "world_variables",
            "scenario_state",
            "scheduler_queue",
            "active_actions",
            "actor_wakeups",
            "rng_state",
            "backend_refs",
        }
        assert not (set(TraceRecord.model_fields) & state_body), "trace 记录变化，不复制状态本体"

    def test_backend_state_enters_snapshot_only_as_ref(self) -> None:
        """D-10：进快照的 BackendState 只有引用 + 能力声明，无不可 JSON 化的本体。"""
        assert set(BackendStateRef.model_fields) == {
            "backend_id",
            "backend_kind",
            "checkpointable",
            "restorable",
            "replayable",
            "checkpoint_ref",
            "metadata",
        }
        assert RuntimeState.model_fields["backend_refs"].annotation is not None


# —— TraceKind / TraceRecord（§4.4，决策 D-11）——


class TestTraceKind:
    """kind 判别词表（与 §4.4 / Spec §8.4 逐项一致）。"""

    def test_vocabulary_matches_design(self) -> None:
        expected = {
            "command",
            "action_proposal",
            "proposed_effect",
            "authority_decision",
            "validation_decision",
            "conflict_resolution",
            "transaction",
            "domain_event",
            "llm_call",
            "prompt_assembly",
            "dev_intervention",
            "system",
        }
        assert {member.value for member in TraceKind} == expected
        assert len(TraceKind) == 12
        assert all(isinstance(member.value, str) for member in TraceKind)

    def test_kind_constructible_from_literal(self) -> None:
        assert TraceKind("llm_call") is TraceKind.LLM_CALL
        assert TraceKind("dev_intervention") is TraceKind.DEV_INTERVENTION


class TestTraceRecordContract:
    """TraceRecord 字段契约（§4.4）：单一信封 + kind 判别。"""

    def test_required_record_id_and_kind(self) -> None:
        with pytest.raises(ValidationError):
            TraceRecord.model_validate({"kind": "system"})
        with pytest.raises(ValidationError):
            TraceRecord.model_validate({"record_id": "trc_x"})

    def test_defaults_optional_none_empty_payload(self) -> None:
        rec = TraceRecord(record_id=TraceRecordId("trc_min"), kind=TraceKind.SYSTEM)
        assert rec.world_revision is None
        assert rec.logical_tick is None
        assert rec.wall_time is None
        assert rec.producer_id is None
        assert rec.transaction_id is None
        assert rec.cascade_id is None
        assert rec.payload == {}

    def test_strict_optional_none_preserved(self) -> None:
        """KBC-7：None 不得被改写为 0/空 dict。"""
        rec = TraceRecord(record_id=TraceRecordId("trc_min"), kind=TraceKind.SYSTEM)
        reloaded = TraceRecord.model_validate(rec.model_dump(mode="json"))
        assert reloaded.world_revision is None
        assert reloaded.logical_tick is None
        assert reloaded.wall_time is None

    def test_invalid_kind_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TraceRecord(record_id=TraceRecordId("trc_x"), kind="bogus_kind")  # type: ignore[arg-type]

    def test_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            TraceRecord(record_id=TraceRecordId("trc_x"), kind=TraceKind.SYSTEM, bogus=1)  # type: ignore[call-overload]

    def test_wall_time_iso_diagnostic_roundtrip(self) -> None:
        ts = datetime(2024, 5, 1, 12, 30, 45, tzinfo=timezone.utc)
        rec = TraceRecord(record_id=TraceRecordId("trc_t"), kind=TraceKind.SYSTEM, wall_time=ts)
        dumped = rec.model_dump(mode="json")
        assert isinstance(dumped["wall_time"], str), "墙钟在 JSON 中为 ISO-8601 字符串"
        assert TraceRecord.model_validate(dumped) == rec


class TestTraceRecordRoundtripAllKinds:
    """S1：各 kind 代表样本 round-trip（kind 判别 + 类型保持 + JSON 纯净）。"""

    @pytest.mark.parametrize("kind", list(TraceKind), ids=[member.value for member in TraceKind])
    def test_roundtrip_per_kind(self, kind: TraceKind) -> None:
        rec = TraceRecord(
            record_id=TraceRecordId("trc_test_1"),
            kind=kind,
            world_revision=Revision(813),
            logical_tick=42,
            wall_time=datetime(2024, 5, 1, 12, 30, tzinfo=timezone.utc),
            producer_id=ProducerId("rule.lock_system"),
            transaction_id=TransactionId("txn_test_1"),
            cascade_id=CascadeId("csc_test_1"),
            payload=_payload_for_kind(kind),
        )
        dumped = rec.model_dump(mode="json")
        _assert_json_clean(dumped)
        assert dumped["kind"] == kind.value, "kind 在 JSON 中为字符串字面量"
        assert type(dumped["world_revision"]) is int
        assert type(dumped["record_id"]) is str
        reloaded = TraceRecord.model_validate(dumped)
        assert reloaded == rec
        assert type(reloaded.record_id) is TraceRecordId
        assert type(reloaded.kind) is TraceKind
        assert reloaded.kind is kind
        assert type(reloaded.world_revision) is Revision
        assert type(reloaded.producer_id) is ProducerId
        assert type(reloaded.transaction_id) is TransactionId
        assert type(reloaded.cascade_id) is CascadeId


class TestTracePayloadConventions:
    """§4.4 payload 子约定：键名冻结 + 内嵌完整契约模型支持离线审计。"""

    def test_payload_key_conventions_frozen(self) -> None:
        assert PAYLOAD_RECORD_KEY == "record"
        assert DECISION_PAYLOAD_KEYS == frozenset({"effect_id", "decision", "reason"})
        assert LLM_CALL_PAYLOAD_KEYS == frozenset(
            {
                "logical_role",
                "profile",
                "resolved_model",
                "input_token_estimate",
                "prompt_metadata_ref",
                "output_ref",
                "latency_ms",
                "parse_retry",
                "base_revision",
            }
        )
        # Spec §31.3 / K8：credential/api_key 永不入 llm_call 键名约定
        assert not any("credential" in key or "api_key" in key for key in LLM_CALL_PAYLOAD_KEYS)

    def test_record_payload_embeds_full_models_offline_auditable(self) -> None:
        """trace 内嵌完整记录：无 runtime 即可还原契约模型（离线审计）。"""
        samples = {
            TraceKind.TRANSACTION: _sample_transaction(),
            TraceKind.DOMAIN_EVENT: _sample_domain_event(),
            TraceKind.ACTION_PROPOSAL: _sample_proposal(),
            TraceKind.PROPOSED_EFFECT: _sample_proposed_effect(),
        }
        for kind, model in samples.items():
            rec = TraceRecord(
                record_id=TraceRecordId("trc_emb"),
                kind=kind,
                payload={PAYLOAD_RECORD_KEY: model.model_dump(mode="json")},
            )
            reloaded = TraceRecord.model_validate(rec.model_dump(mode="json"))
            embedded = reloaded.payload[PAYLOAD_RECORD_KEY]
            assert type(model).model_validate(embedded) == model

    def test_dev_intervention_origin_developer(self) -> None:
        """Spec §22：dev_intervention 强制 origin=developer（词表即 OriginKind）。"""
        rec = TraceRecord(
            record_id=TraceRecordId("trc_dev"),
            kind=TraceKind.DEV_INTERVENTION,
            payload=_payload_for_kind(TraceKind.DEV_INTERVENTION),
        )
        assert rec.payload["origin"] == OriginKind.DEVELOPER.value == "developer"


# —— S5 / 零公共 mutator：全部 T02 模型 ——


class TestFrozenAndZeroPublicMutators:
    """S5 frozen + §3.5 纪律 1：全部 T02 模型零公共写 API。"""

    _MUTATOR_PREFIXES = (
        "set_",
        "add_",
        "append_",
        "insert_",
        "remove_",
        "update_",
        "replace_",
        "mutate_",
        "clear_",
        "del_",
    )

    _MODEL_CLASSES = (
        WorldState,
        RuntimeState,
        ScenarioState,
        RngState,
        ScheduledEvent,
        ActorWakeup,
        BackendStateRef,
        TraceRecord,
    )

    @pytest.mark.parametrize(
        "model_cls", _MODEL_CLASSES, ids=[cls.__name__ for cls in _MODEL_CLASSES]
    )
    def test_no_public_mutator_api(self, model_cls: type) -> None:
        """静态断言：类自身声明的公共属性中无 mutator 前缀方法名（T06 E3 同款口径）。"""
        mutators = [
            name
            for name in vars(model_cls)
            if not name.startswith("_") and name.startswith(self._MUTATOR_PREFIXES)
        ]
        assert mutators == []
        assert issubclass(model_cls, ContractModel)
        assert model_cls.model_config["frozen"] is True
        assert model_cls.model_config["extra"] == "forbid"

    @pytest.mark.parametrize(
        ("make_instance", "field", "value"),
        [
            (lambda: WorldState(), "world_revision", 999),
            (lambda: RuntimeState(), "logical_tick", 7),
            (lambda: ScenarioState(), "stage", "act_9"),
            (lambda: RngState(algorithm="pcg32"), "algorithm", "mt19937"),
            (
                lambda: ScheduledEvent(
                    entry_id=ScheduledEntryId("sch_f"), due_tick=1, kind="wakeup"
                ),
                "due_tick",
                2,
            ),
            (lambda: ActorWakeup(actor_id=EntityId("ent_f"), due_tick=1), "due_tick", 2),
            (
                lambda: BackendStateRef(backend_id="b_f", backend_kind="dynamics"),
                "checkpointable",
                True,
            ),
            (
                lambda: TraceRecord(record_id=TraceRecordId("trc_f"), kind=TraceKind.SYSTEM),
                "kind",
                TraceKind.COMMAND,
            ),
        ],
        ids=[cls.__name__ for cls in _MODEL_CLASSES],
    )
    def test_frozen_blocks_assignment(self, make_instance: Any, field: str, value: Any) -> None:
        instance = make_instance()
        with pytest.raises((ValidationError, TypeError)):
            setattr(instance, field, value)


# —— 模块级契约：导出面 / import 边界 ——


class TestModuleExports:
    """S3：state.py 不导出任何调度语义函数；导出面与设计文档一致。"""

    def test_state_module_exports_exact(self) -> None:
        assert set(state_module.__all__) == {
            "CONTRACT_SCHEMA_VERSION",
            "ScenarioState",
            "RuntimeLifecycle",
            "RngState",
            "ScheduledEvent",
            "ActorWakeup",
            "BackendStateRef",
            "RuntimeState",
            "WorldState",
        }

    def test_state_module_exports_no_behavioral_functions(self) -> None:
        """占位纪律（S3）：P1 state.py 导出纯数据契约，无模块级公共行为函数。"""
        functions = [
            name
            for name in state_module.__all__
            if isinstance(getattr(state_module, name), types.FunctionType)
        ]
        assert functions == [], "无任何调度/变更语义函数被导出（语义属 P2/P3）"

    def test_trace_module_exports_exact(self) -> None:
        assert set(trace_module.__all__) == {
            "PAYLOAD_RECORD_KEY",
            "DECISION_PAYLOAD_KEYS",
            "LLM_CALL_PAYLOAD_KEYS",
            "TraceKind",
            "TraceRecord",
        }

    def test_contract_schema_version_value(self) -> None:
        assert state_module.CONTRACT_SCHEMA_VERSION == 1


class TestImportBoundary:
    """§0.3 import 边界：state.py / trace.py 只 import 标准库、pydantic 与同包 src.engine_v2。"""

    _STDLIB = {
        "__future__",
        "collections",  # collections.abc
        "enum",
        "typing",
        "datetime",
    }

    @pytest.mark.parametrize("module", [state_module, trace_module], ids=["state", "trace"])
    def test_only_whitelisted_imports(self, module: Any) -> None:
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
        """B2 口径：fresh import 的 sys.modules 增量不含任何禁止依赖。"""
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
        module_names = ("src.engine_v2.core.state", "src.engine_v2.core.trace")
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
        assert not bad, f"import state/trace 过程中新载入了禁止依赖：{bad}"
