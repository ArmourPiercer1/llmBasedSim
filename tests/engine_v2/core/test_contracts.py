"""P1-T04 单元测试：行动 / 效果 / 事件 / 事务契约（设计文档 §7.4 C1–C7 口径）。

覆盖（对齐 ``docs/v2/contracts/P1-core-data-contracts.md`` §7.4 与任务包要求）：

- **C1 ActionProposal 必填**：缺 ``base_world_revision`` / ``provenance`` → 校验
  失败；``confidence`` 越界（<0 或 >1）→ 失败（边界 0/1 通过）；
- **C2 §9 字段在场**：``base_world_revision`` / ``observation_id`` /
  ``actor_state_revision`` / ``valid_until`` 均可序列化承载（Spec §9 示例
  ``base_world_revision=812, observation_id="obs_991"`` 可直接构造）；
- **C3 EffectTarget 判别**：entity / state_domain 两分支 round-trip；未知
  ``kind`` / 缺 ``kind`` → 失败；
- **C4 事务原子不变量**：COMMITTED ⇒ ``commit_revision == base_revision+1``、
  ``effects`` 非空、``sequence`` 唯一连续自 0；ABORTED ⇒ ``commit_revision is
  None`` 且 ``effects == []``；部分提交 schema 层不可表达；
- **C5 CommittedEffect 一致性**：事务内全部 effects 共享同一 ``transaction_id``
  / ``commit_revision``（不一致即被拒绝）；事务内 ``effect_id`` 唯一（KBC-2
  防线）；
- **C6 DomainEvent provenance**：``provenance`` / ``source_system`` /
  ``world_revision`` 必填；``cause_ids`` 的 CauseRef 种类校验；cascade 上下文
  depth/root 可承载；``wall_time`` ISO-8601 诊断侧 round-trip；
- **C7 数据级部分**（事务内可判定项）：重复 ``effect_id`` 进同一事务被拒绝。
  注：``check_transaction_references(state, txn)`` 依赖 T02 ``WorldState``
  （设计文档 §1.2 T02 在 T04 之后），其 missing entity / stale revision 判定
  不在本任务落位——见 deviations；
- **§5.0 provenance 小件**：OriginKind/CauseKind 词表、Provenance 完整性、
  CascadeContext 字段；
- **名字型类型标识符**（EffectTypeId/StateDomainId/ActionTypeId/EventTypeId）：
  §2.2 统一词法 + pydantic 类型保持（与 T01/T03 同模式）；
- **各 schema 字段契约**：全部模型字段集合与设计文档逐项一致（程序化守卫）；
- **extra=forbid / frozen**（J2/S5 口径）：全部 T04 模型；
- **JSON round-trip**（§0.2 铁律 / §6.1）：值相等 + 类型保持 + JSON 纯净 +
  Unicode 无损 + 边界值；
- **import 边界**（§0.3 / B1/B2）：五个新模块 AST 静态扫描 + fresh import
  sys.modules 增量。

全部用例无网络、无 LLM、无 API key（Spec §47 Phase 1 验收）。
"""

from __future__ import annotations

import ast
import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

import src.engine_v2.core.actions as actions_module
import src.engine_v2.core.effects as effects_module
import src.engine_v2.core.events as events_module
import src.engine_v2.core.provenance as provenance_module
import src.engine_v2.core.transaction as transaction_module
from src.engine_v2.core.actions import (
    ACTION_TYPE_ID_PATTERN,
    ActionLifecycleStatus,
    ActionProposal,
    ActionTiming,
    ActionTypeId,
    ActiveAction,
    FallbackSpec,
    parse_action_type_id,
)
from src.engine_v2.core.components import ComponentSchema, ComponentTypeId
from src.engine_v2.core.effects import (
    EFFECT_TYPE_ID_PATTERN,
    STATE_DOMAIN_ID_PATTERN,
    CommittedEffect,
    EffectTypeId,
    EntityTarget,
    ProposedEffect,
    StateDomainId,
    StateDomainTarget,
    parse_effect_type_id,
    parse_state_domain_id,
)
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.events import (
    EVENT_TYPE_ID_PATTERN,
    DomainEvent,
    EventTypeId,
    parse_event_type_id,
)
from src.engine_v2.core.ids import (
    ActionInstanceId,
    CascadeId,
    EffectId,
    EntityId,
    EventId,
    ObservationId,
    ProducerId,
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
from src.engine_v2.core.revision import Revision, next_revision
from src.engine_v2.core.transaction import Transaction, TransactionStatus

# —— 统一词法（设计文档 §2.2 类型标识符族）——

_NAME_TYPE_PATTERN = r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*"


def _assert_json_clean(value: Any) -> None:
    """递归断言仅含 JSON 原生类型（§0.2 铁律 1；T05 提供正式工具，此处自测口径）。"""
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


# —— 样本构造助手（确定性 ID，便于断言逐字相等）——

_HEX32 = {c: c * 32 for c in "abcdef0123456789"}


def _sample_provenance_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"producer_id": "policy.alice", "origin": "behavior_policy"}
    data.update(overrides)
    return data


def _sample_proposal_data(**overrides: Any) -> dict[str, Any]:
    """完整 ActionProposal 样本（含 §9 四字段、中文 intent、嵌套 timing/fallback）。"""
    data: dict[str, Any] = {
        "proposal_id": "act_" + _HEX32["a"],
        "actor_id": "ent_alice",
        "action_id": "interaction.knock",
        "arguments": {"target": "ent_door", "force": 3},
        "intent": "敲开村口的木门",
        "timing": {"earliest_start_tick": 5, "deadline_tick": 9, "duration_hint_ticks": 2},
        "confidence": 0.75,
        "fallback_action": {"action_id": "wait", "arguments": {"ticks": 1}},
        # Spec §9 示例口径：base_world_revision=812、observation_id="obs_991"
        "base_world_revision": 812,
        "observation_id": "obs_991",
        "actor_state_revision": 811,
        "valid_until": 820,
        "provenance": _sample_provenance_data(
            source_record_id="trc_" + _HEX32["d"], notes="异步决策"
        ),
    }
    data.update(overrides)
    return data


def _sample_proposal(**overrides: Any) -> ActionProposal:
    return ActionProposal.model_validate(_sample_proposal_data(**overrides))


def _sample_active_action_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "instance_id": "act_" + _HEX32["a"],
        "action_id": "interaction.knock",
        "actor_id": "ent_alice",
        "status": "active",
        "start_tick": 5,
        "expected_end_tick": 7,
        "progress": 0.5,
        "interruptible": True,
        "completion_condition": {"op": "eq", "field": "lock.state.open", "value": True},
        "next_checkpoint_tick": 6,
        "base_world_revision": 812,
        "provenance": _sample_provenance_data(),
        "last_transition_tick": 5,
        "result_summary": None,
    }
    data.update(overrides)
    return data


def _sample_active_action(**overrides: Any) -> ActiveAction:
    return ActiveAction.model_validate(_sample_active_action_data(**overrides))


def _sample_proposed_effect_data(index: int = 1, **overrides: Any) -> dict[str, Any]:
    """完整 ProposedEffect 样本；index 决定互不相同的 effect_id。"""
    data: dict[str, Any] = {
        "effect_id": f"eff_{index:032x}",
        "effect_type": "unlock",
        "source": "rule.lock_system",
        "target": {
            "kind": "entity",
            "entity_id": "ent_door",
            "component_type": "lock.state",
            "field_path": "open",
        },
        "payload": {"open": True, "原因": "钥匙开门"},
        "base_revision": 812,
        "cause_ids": [{"kind": "action", "ref_id": "act_" + _HEX32["a"]}],
        "authority_scope": "interaction.lock_system",
        "priority_hint": 3,
        "metadata": {"note": "中文备注"},
    }
    data.update(overrides)
    return data


def _sample_proposed_effect(index: int = 1, **overrides: Any) -> ProposedEffect:
    return ProposedEffect.model_validate(_sample_proposed_effect_data(index, **overrides))


def _sample_committed_effect(
    index: int, transaction_id: str, commit_revision: int
) -> CommittedEffect:
    return CommittedEffect(
        effect=_sample_proposed_effect(index=index),
        transaction_id=TransactionId(transaction_id),
        commit_revision=Revision(commit_revision),
        sequence=index - 1,
    )


def _sample_committed_txn_data(n_effects: int = 2, **overrides: Any) -> dict[str, Any]:
    txn_id = "txn_" + _HEX32["b"]
    base = 812
    data: dict[str, Any] = {
        "transaction_id": txn_id,
        "status": "committed",
        "base_revision": base,
        "commit_revision": base + 1,
        "logical_tick": 42,
        "effects": [
            _sample_committed_effect(i, txn_id, base + 1) for i in range(1, n_effects + 1)
        ],
        "event_ids": ["evt_" + _HEX32["e"]],
        "cascade": {
            "cascade_id": "csc_" + _HEX32["f"],
            "causal_root_id": "act_" + _HEX32["a"],
            "depth": 0,
        },
        "provenance": _sample_provenance_data(producer_id="rule.lock_system", origin="rule"),
        "abort_reason": None,
    }
    data.update(overrides)
    return data


def _sample_committed_txn(n_effects: int = 2, **overrides: Any) -> Transaction:
    return Transaction.model_validate(_sample_committed_txn_data(n_effects, **overrides))


def _sample_aborted_txn(**overrides: Any) -> Transaction:
    data: dict[str, Any] = {
        "transaction_id": "txn_" + _HEX32["c"],
        "status": "aborted",
        "base_revision": 812,
        "abort_reason": "conflict: 同一 field_path 并发写入",
    }
    data.update(overrides)
    return Transaction.model_validate(data)


def _sample_domain_event_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "event_id": "evt_" + _HEX32["e"],
        "event_type": "lock.opened",
        "world_revision": 813,
        "logical_tick": 42,
        "transaction_id": "txn_" + _HEX32["b"],
        "payload": {"door": "ent_door", "开启者": "alice"},
        "cause_ids": [
            {"kind": "effect", "ref_id": "eff_" + f"{1:032x}"},
            {"kind": "proposal", "ref_id": "act_" + _HEX32["a"]},
        ],
        "source_system": "rule.lock_system",
        "provenance": _sample_provenance_data(producer_id="rule.lock_system", origin="rule"),
        "cascade": {
            "cascade_id": "csc_" + _HEX32["f"],
            "causal_root_id": "act_" + _HEX32["a"],
            "depth": 1,
        },
        "wall_time": "2026-05-04T12:30:00+00:00",
    }
    data.update(overrides)
    return data


def _sample_domain_event(**overrides: Any) -> DomainEvent:
    return DomainEvent.model_validate(_sample_domain_event_data(**overrides))


# —— §5.0 provenance 共享小件 ——


class TestProvenanceSharedParts:
    """§5.0：OriginKind/CauseKind 词表、Provenance 完整性、CascadeContext 字段。"""

    def test_origin_kind_vocabulary(self) -> None:
        assert {member.value for member in OriginKind} == {
            "behavior_policy",
            "dynamics_backend",
            "rule",
            "script",
            "scenario",
            "developer",
            "system",
        }
        assert isinstance(OriginKind.DEVELOPER, str)
        assert OriginKind.DEVELOPER == "developer"  # Spec §22 origin=developer

    def test_cause_kind_vocabulary(self) -> None:
        assert {member.value for member in CauseKind} == {
            "event",
            "action",
            "effect",
            "proposal",
            "intervention",
        }

    def test_provenance_required_fields(self) -> None:
        """K6 完整性：producer_id / origin 必填。"""
        with pytest.raises(ValidationError):
            Provenance.model_validate({"origin": "rule"})
        with pytest.raises(ValidationError):
            Provenance.model_validate({"producer_id": "rule.lock_system"})

    def test_provenance_defaults_and_optional_semantics(self) -> None:
        prov = Provenance(producer_id=ProducerId("dev.console"), origin=OriginKind.DEVELOPER)
        assert prov.source_record_id is None
        assert prov.notes is None
        dumped = prov.model_dump(mode="json")
        assert dumped["source_record_id"] is None  # KBC-7：None 不改写
        assert dumped["notes"] is None

    def test_provenance_roundtrip_type_preserved(self) -> None:
        prov = Provenance.model_validate(
            _sample_provenance_data(source_record_id="trc_" + _HEX32["d"], notes="备注")
        )
        dumped = prov.model_dump(mode="json")
        _assert_json_clean(dumped)
        assert type(dumped["producer_id"]) is str
        assert dumped["origin"] == "behavior_policy"
        reloaded = Provenance.model_validate(dumped)
        assert reloaded == prov
        assert type(reloaded.producer_id) is ProducerId
        assert type(reloaded.source_record_id) is TraceRecordId
        assert type(reloaded.origin) is OriginKind

    def test_cause_ref_roundtrip(self) -> None:
        ref = CauseRef(kind=CauseKind.EFFECT, ref_id="eff_" + _HEX32["0"])
        dumped = ref.model_dump(mode="json")
        _assert_json_clean(dumped)
        reloaded = CauseRef.model_validate(dumped)
        assert reloaded == ref
        assert type(reloaded.kind) is CauseKind

    def test_cause_ref_invalid_kind_fails(self) -> None:
        with pytest.raises(ValidationError):
            CauseRef.model_validate({"kind": "bogus", "ref_id": "x"})

    def test_cascade_context_fields_and_defaults(self) -> None:
        ctx = CascadeContext(
            cascade_id=CascadeId("csc_" + _HEX32["f"]),
            causal_root_id="act_" + _HEX32["a"],
        )
        assert ctx.depth == 0  # 根为 0
        dumped = ctx.model_dump(mode="json")
        _assert_json_clean(dumped)
        reloaded = CascadeContext.model_validate(dumped)
        assert reloaded == ctx
        assert type(reloaded.cascade_id) is CascadeId

    def test_all_models_are_contract_models(self) -> None:
        """全部 T04 契约模型共享同一 frozen/extra=forbid 基类（§0.1）。"""
        for cls in (
            Provenance,
            CauseRef,
            CascadeContext,
            ActionTiming,
            FallbackSpec,
            ActionProposal,
            ActiveAction,
            EntityTarget,
            StateDomainTarget,
            ProposedEffect,
            CommittedEffect,
            DomainEvent,
            Transaction,
        ):
            assert issubclass(cls, ContractModel), cls.__name__
            assert cls.model_config["frozen"] is True
            assert cls.model_config["extra"] == "forbid"


# —— 名字型类型标识符（§2.2 统一词法 + 类型保持）——


class TestNameTypeIdsLexicon:
    """EffectTypeId/StateDomainId/ActionTypeId/EventTypeId 词法（§2.2 统一规定）。"""

    _PARSE_FUNCS = (
        parse_effect_type_id,
        parse_state_domain_id,
        parse_action_type_id,
        parse_event_type_id,
    )
    _CLASSES = (EffectTypeId, StateDomainId, ActionTypeId, EventTypeId)

    @pytest.mark.parametrize(
        "text",
        [
            "unlock",  # 设计文档 §0.4 示例（单段）
            "space.position",  # 多段
            "world_variables",  # 下划线
            "a",
            "a1_b2.c9",
            "interaction.knock",
        ],
    )
    def test_valid_lexicon(self, text: str) -> None:
        for parse, cls in zip(self._PARSE_FUNCS, self._CLASSES, strict=True):
            result = parse(text)
            assert type(result) is cls
            assert str(result) == text, "词法校验不得改写值（G1 稳定性）"

    @pytest.mark.parametrize(
        "text",
        [
            "",  # 空串
            "Unlock",  # 大写
            "1abc",  # 段以数字开头
            "a..b",  # 连续点
            ".space",  # 前导点
            "space.",  # 尾随点
            "space-position",  # 非法字符 '-'
            "space position",  # 空格
            "空间.position",  # 非 ASCII 段首
        ],
    )
    def test_invalid_lexicon(self, text: str) -> None:
        for parse in self._PARSE_FUNCS:
            with pytest.raises(ValueError):
                parse(text)

    def test_non_string_input_raises(self) -> None:
        for parse in self._PARSE_FUNCS:
            with pytest.raises(ValueError):
                parse(123)  # type: ignore[arg-type]

    def test_patterns_match_design_doc_unified_lexicon(self) -> None:
        """§2.2：类型标识符族词法统一——四个模式与 ComponentTypeId 同款正则。"""
        for pattern in (
            EFFECT_TYPE_ID_PATTERN,
            STATE_DOMAIN_ID_PATTERN,
            ACTION_TYPE_ID_PATTERN,
            EVENT_TYPE_ID_PATTERN,
        ):
            assert pattern.pattern == _NAME_TYPE_PATTERN

    def test_typed_str_subclass_semantics(self) -> None:
        """决策 D-1 模式推广：typed str 子类——isinstance str、可哈希、str 语义保持。"""
        for cls in self._CLASSES:
            assert issubclass(cls, str)
            instance = cls("space.position")
            assert isinstance(instance, str)
            assert instance == "space.position"
            assert {instance: 1}  # dict 可用


class TestNameTypeIdsPydantic:
    """名字型 ID 的 pydantic 类型保持（设计文档 §2.1，与 T01/T03 同模式）。"""

    class _NameIdEnvelope(BaseModel):
        effect_type: EffectTypeId
        state_domain: StateDomainId
        action_id: ActionTypeId
        event_type: EventTypeId

    def test_accepts_plain_str_rebuilds_subclass_and_roundtrips(self) -> None:
        model = self._NameIdEnvelope.model_validate(
            {
                "effect_type": "unlock",
                "state_domain": "world_variables",
                "action_id": "interaction.knock",
                "event_type": "lock.opened",
            }
        )
        assert type(model.effect_type) is EffectTypeId
        assert type(model.state_domain) is StateDomainId
        assert type(model.action_id) is ActionTypeId
        assert type(model.event_type) is EventTypeId
        dumped = model.model_dump(mode="json")
        for field_name in ("effect_type", "state_domain", "action_id", "event_type"):
            assert type(dumped[field_name]) is str  # §0.2 铁律 2：纯字符串
        reloaded = self._NameIdEnvelope.model_validate(dumped)
        assert reloaded == model
        assert type(reloaded.effect_type) is EffectTypeId
        assert type(reloaded.state_domain) is StateDomainId

    def test_state_domain_id_satisfies_components_forward_reference(self) -> None:
        """components.py（T03）以 TYPE_CHECKING 前向引用本任务的 StateDomainId。

        ``ComponentSchema.authority_domain`` 可承载真实 ``StateDomainId`` 实例
        （Spec §17.2 domain tag 维度预留，设计文档 §3.3/§5.3）。
        """
        schema = ComponentSchema(
            component_type=ComponentTypeId("space.position"),
            authority_domain=StateDomainId("world_variables"),
        )
        assert type(schema.authority_domain) is StateDomainId
        assert isinstance(schema.authority_domain, str)


# —— C1/C2：ActionProposal ——


class TestActionProposal:
    """C1 必填/越界校验 + C2 §9 字段在场 + 字段契约 + round-trip。"""

    def test_field_set_matches_design_doc(self) -> None:
        """§5.1 字段逐项：程序化守卫字段集合（public contract 冻结）。"""
        assert set(ActionProposal.model_fields) == {
            "proposal_id",
            "actor_id",
            "action_id",
            "arguments",
            "intent",
            "timing",
            "confidence",
            "fallback_action",
            "base_world_revision",
            "observation_id",
            "actor_state_revision",
            "valid_until",
            "provenance",
        }
        assert set(ActionTiming.model_fields) == {
            "earliest_start_tick",
            "deadline_tick",
            "duration_hint_ticks",
        }
        assert set(FallbackSpec.model_fields) == {"action_id", "arguments"}

    def test_missing_base_world_revision_fails(self) -> None:
        """C1：缺 base_world_revision（决策 D-13 必填）→ 校验失败。"""
        data = _sample_proposal_data()
        del data["base_world_revision"]
        with pytest.raises(ValidationError):
            ActionProposal.model_validate(data)

    def test_missing_provenance_fails(self) -> None:
        """C1：缺 provenance（K6）→ 校验失败。"""
        data = _sample_proposal_data()
        del data["provenance"]
        with pytest.raises(ValidationError):
            ActionProposal.model_validate(data)

    @pytest.mark.parametrize("bad", [-0.1, 1.5, 2.0, -3.0])
    def test_confidence_out_of_range_fails(self, bad: float) -> None:
        """C1：confidence 越界（<0 或 >1）→ 失败。"""
        with pytest.raises(ValidationError):
            ActionProposal.model_validate(_sample_proposal_data(confidence=bad))

    @pytest.mark.parametrize("ok", [0.0, 1.0, 0.5, None])
    def test_confidence_boundaries_ok(self, ok: float | None) -> None:
        proposal = ActionProposal.model_validate(_sample_proposal_data(confidence=ok))
        assert proposal.confidence == ok

    def test_spec9_example_constructible(self) -> None:
        """C2：Spec §9 示例 base_world_revision=812、observation_id='obs_991' 可直接构造。"""
        proposal = ActionProposal.model_validate(
            {
                "proposal_id": "act_" + _HEX32["a"],
                "actor_id": "ent_alice",
                "action_id": "rest",
                "base_world_revision": 812,
                "observation_id": "obs_991",
                "provenance": _sample_provenance_data(),
            }
        )
        assert proposal.base_world_revision == Revision(812)
        assert proposal.observation_id == ObservationId("obs_991")

    def test_section9_fields_serializable(self) -> None:
        """C2：§9 四字段均可序列化承载，round-trip 后类型保持。"""
        proposal = _sample_proposal()
        dumped = proposal.model_dump(mode="json")
        assert dumped["base_world_revision"] == 812
        assert type(dumped["base_world_revision"]) is int
        assert dumped["observation_id"] == "obs_991"
        assert type(dumped["observation_id"]) is str
        assert dumped["actor_state_revision"] == 811
        assert dumped["valid_until"] == 820
        reloaded = ActionProposal.model_validate(dumped)
        assert type(reloaded.base_world_revision) is Revision
        assert type(reloaded.observation_id) is ObservationId
        assert type(reloaded.actor_state_revision) is Revision
        assert type(reloaded.valid_until) is Revision

    def test_defaults(self) -> None:
        minimal = ActionProposal.model_validate(
            {
                "proposal_id": "act_" + _HEX32["a"],
                "actor_id": "ent_alice",
                "action_id": "rest",
                "base_world_revision": 0,
                "provenance": _sample_provenance_data(),
            }
        )
        assert minimal.arguments == {}
        assert minimal.intent is None
        assert minimal.timing == ActionTiming()
        assert minimal.confidence is None
        assert minimal.fallback_action is None
        assert minimal.observation_id is None
        assert minimal.actor_state_revision is None
        assert minimal.valid_until is None

    def test_roundtrip_full_type_preserved(self) -> None:
        proposal = _sample_proposal()
        dumped = proposal.model_dump(mode="json")
        _assert_json_clean(dumped)
        assert type(dumped["proposal_id"]) is str
        assert type(dumped["actor_id"]) is str
        assert dumped["intent"] == "敲开村口的木门"
        reloaded = ActionProposal.model_validate(dumped)
        assert reloaded == proposal
        assert type(reloaded.proposal_id) is ActionInstanceId
        assert type(reloaded.actor_id) is EntityId
        assert type(reloaded.action_id) is ActionTypeId
        assert type(reloaded.base_world_revision) is Revision
        assert type(reloaded.observation_id) is ObservationId
        assert type(reloaded.provenance.producer_id) is ProducerId
        assert type(reloaded.provenance.origin) is OriginKind

    def test_json_text_roundtrip_unicode(self) -> None:
        proposal = _sample_proposal()
        text = proposal.model_dump_json(ensure_ascii=False)
        assert "敲开村口的木门" in text, "ensure_ascii=False：中文不得被转义"
        reloaded = ActionProposal.model_validate_json(text)
        assert reloaded == proposal


class TestActiveAction:
    """§5.2 ActiveAction：§23.4 字段逐项、生命周期词表、D-3 实例 ID 贯穿。"""

    def test_lifecycle_status_vocabulary(self) -> None:
        """Spec §11.4：六态；IDLE 是 actor 层状态，不作为 action 记录状态。"""
        assert {member.value for member in ActionLifecycleStatus} == {
            "proposed",
            "validating",
            "active",
            "interrupted",
            "completed",
            "failed",
        }
        assert not hasattr(ActionLifecycleStatus, "IDLE")

    def test_field_set_matches_design_doc(self) -> None:
        """§23.4 字段逐项：程序化守卫字段集合。"""
        assert set(ActiveAction.model_fields) == {
            "instance_id",
            "action_id",
            "actor_id",
            "status",
            "start_tick",
            "expected_end_tick",
            "progress",
            "interruptible",
            "completion_condition",
            "next_checkpoint_tick",
            "base_world_revision",
            "provenance",
            "last_transition_tick",
            "result_summary",
        }

    def test_required_fields(self) -> None:
        data = _sample_active_action_data()
        for required in ("instance_id", "action_id", "actor_id", "status", "start_tick",
                         "base_world_revision", "provenance"):
            missing = dict(data)
            del missing[required]
            with pytest.raises(ValidationError):
                ActiveAction.model_validate(missing)

    def test_defaults(self) -> None:
        action = ActiveAction.model_validate(
            {
                "instance_id": "act_" + _HEX32["a"],
                "action_id": "rest",
                "actor_id": "ent_alice",
                "status": "proposed",
                "start_tick": 0,
                "base_world_revision": 0,
                "provenance": _sample_provenance_data(),
            }
        )
        assert action.expected_end_tick is None
        assert action.progress is None
        assert action.interruptible is True
        assert action.completion_condition is None
        assert action.next_checkpoint_tick is None
        assert action.last_transition_tick == 0
        assert action.result_summary is None

    @pytest.mark.parametrize("bad", [-0.1, 1.5])
    def test_progress_out_of_range_fails(self, bad: float) -> None:
        """§23.4 progress 取值 [0,1]（设计文档 §5.2 注释口径）。"""
        with pytest.raises(ValidationError):
            ActiveAction.model_validate(_sample_active_action_data(progress=bad))

    def test_d3_instance_id_flows_from_proposal(self) -> None:
        """决策 D-3：同一 ActionInstanceId 贯穿 ActionProposal → ActiveAction。"""
        proposal = _sample_proposal()
        active = ActiveAction(
            instance_id=proposal.proposal_id,
            action_id=proposal.action_id,
            actor_id=proposal.actor_id,
            status=ActionLifecycleStatus.ACTIVE,
            start_tick=5,
            base_world_revision=proposal.base_world_revision,
            provenance=proposal.provenance,
        )
        assert active.instance_id == proposal.proposal_id
        assert type(active.instance_id) is ActionInstanceId
        # round-trip 后仍保持同一实例 ID（K6/K7 全链路可追踪）
        reloaded = ActiveAction.model_validate(active.model_dump(mode="json"))
        assert reloaded.instance_id == proposal.proposal_id
        assert type(reloaded.instance_id) is ActionInstanceId

    def test_completion_condition_opaque_json(self) -> None:
        """K7：completion_condition 保持不透明 JSON（P1 不锁定条件 DSL）。"""
        action = _sample_active_action()
        dumped = action.model_dump(mode="json")
        assert dumped["completion_condition"] == {
            "op": "eq",
            "field": "lock.state.open",
            "value": True,
        }
        reloaded = ActiveAction.model_validate(dumped)
        assert reloaded == action

    def test_roundtrip_full_type_preserved(self) -> None:
        action = _sample_active_action()
        dumped = action.model_dump(mode="json")
        _assert_json_clean(dumped)
        assert dumped["status"] == "active"
        reloaded = ActiveAction.model_validate(dumped)
        assert reloaded == action
        assert type(reloaded.instance_id) is ActionInstanceId
        assert type(reloaded.action_id) is ActionTypeId
        assert type(reloaded.actor_id) is EntityId
        assert type(reloaded.status) is ActionLifecycleStatus
        assert type(reloaded.base_world_revision) is Revision


# —— C3：EffectTarget 判别 ——


class TestEffectTarget:
    """C3：entity / state_domain 两分支 round-trip；未知 kind → 失败。"""

    def test_field_sets_match_design_doc(self) -> None:
        assert set(EntityTarget.model_fields) == {
            "kind",
            "entity_id",
            "component_type",
            "field_path",
        }
        assert set(StateDomainTarget.model_fields) == {"kind", "domain"}

    def test_entity_branch_roundtrip(self) -> None:
        effect = _sample_proposed_effect()
        assert type(effect.target) is EntityTarget
        dumped = effect.model_dump(mode="json")
        assert dumped["target"]["kind"] == "entity"  # tagged union 判别字面量进 JSON
        reloaded = ProposedEffect.model_validate(dumped)
        assert reloaded == effect
        assert type(reloaded.target) is EntityTarget
        assert type(reloaded.target.entity_id) is EntityId
        assert type(reloaded.target.component_type) is ComponentTypeId

    def test_state_domain_branch_roundtrip(self) -> None:
        effect = _sample_proposed_effect(
            index=2,
            target={"kind": "state_domain", "domain": "world_variables"},
        )
        assert type(effect.target) is StateDomainTarget
        dumped = effect.model_dump(mode="json")
        assert dumped["target"] == {"kind": "state_domain", "domain": "world_variables"}
        reloaded = ProposedEffect.model_validate(dumped)
        assert reloaded == effect
        assert type(reloaded.target) is StateDomainTarget
        assert type(reloaded.target.domain) is StateDomainId

    def test_unknown_kind_fails(self) -> None:
        with pytest.raises(ValidationError):
            ProposedEffect.model_validate(
                _sample_proposed_effect_data(target={"kind": "bogus", "entity_id": "ent_x"})
            )

    def test_missing_kind_fails(self) -> None:
        with pytest.raises(ValidationError):
            ProposedEffect.model_validate(
                _sample_proposed_effect_data(target={"entity_id": "ent_x"})
            )


# —— ProposedEffect / CommittedEffect ——


class TestProposedEffect:
    """§5.3 ProposedEffect 字段契约（与 Spec §16.1 逐字段一致）。"""

    def test_field_set_matches_design_doc(self) -> None:
        assert set(ProposedEffect.model_fields) == {
            "effect_id",
            "effect_type",
            "source",
            "target",
            "payload",
            "base_revision",
            "cause_ids",
            "authority_scope",
            "priority_hint",
            "metadata",
        }

    def test_payload_required(self) -> None:
        """§16.1 payload 必填无缺省——变化只能经完整 payload 完成（KBC-4 防线）。"""
        data = _sample_proposed_effect_data()
        del data["payload"]
        with pytest.raises(ValidationError):
            ProposedEffect.model_validate(data)

    def test_defaults(self) -> None:
        data = _sample_proposed_effect_data()
        for optional in ("cause_ids", "authority_scope", "priority_hint", "metadata"):
            del data[optional]
        effect = ProposedEffect.model_validate(data)
        assert effect.cause_ids == []
        assert effect.authority_scope is None
        assert effect.priority_hint is None
        assert effect.metadata == {}

    def test_cause_ids_typed(self) -> None:
        effect = _sample_proposed_effect()
        assert all(type(cause) is CauseRef for cause in effect.cause_ids)
        assert effect.cause_ids[0].kind is CauseKind.ACTION

    def test_roundtrip_full_type_preserved(self) -> None:
        effect = _sample_proposed_effect()
        dumped = effect.model_dump(mode="json")
        _assert_json_clean(dumped)
        assert type(dumped["effect_id"]) is str
        assert type(dumped["base_revision"]) is int
        assert dumped["payload"]["原因"] == "钥匙开门"
        reloaded = ProposedEffect.model_validate(dumped)
        assert reloaded == effect
        assert type(reloaded.effect_id) is EffectId
        assert type(reloaded.effect_type) is EffectTypeId
        assert type(reloaded.source) is ProducerId
        assert type(reloaded.base_revision) is Revision


class TestCommittedEffect:
    """§5.4 CommittedEffect：内嵌提案自包含 + 字段契约。"""

    def test_field_set_matches_design_doc(self) -> None:
        assert set(CommittedEffect.model_fields) == {
            "effect",
            "transaction_id",
            "commit_revision",
            "sequence",
        }

    def test_self_contained_embedding(self) -> None:
        """§5.4 设计取舍：内嵌完整 ProposedEffect（provenance 不丢失，replay 自包含）。"""
        committed = _sample_committed_effect(1, "txn_" + _HEX32["b"], 813)
        assert type(committed.effect) is ProposedEffect
        assert committed.effect.source == ProducerId("rule.lock_system")
        assert committed.effect.metadata == {"note": "中文备注"}
        assert committed.sequence == 0

    def test_roundtrip_full_type_preserved(self) -> None:
        committed = _sample_committed_effect(1, "txn_" + _HEX32["b"], 813)
        dumped = committed.model_dump(mode="json")
        _assert_json_clean(dumped)
        reloaded = CommittedEffect.model_validate(dumped)
        assert reloaded == committed
        assert type(reloaded.transaction_id) is TransactionId
        assert type(reloaded.commit_revision) is Revision
        assert type(reloaded.effect.effect_id) is EffectId


# —— C6：DomainEvent ——


class TestDomainEvent:
    """C6：provenance/source_system/world_revision 必填、cause 种类、cascade 承载。"""

    def test_field_set_matches_design_doc(self) -> None:
        assert set(DomainEvent.model_fields) == {
            "event_id",
            "event_type",
            "world_revision",
            "logical_tick",
            "transaction_id",
            "payload",
            "cause_ids",
            "source_system",
            "provenance",
            "cascade",
            "wall_time",
        }

    @pytest.mark.parametrize("required", ["provenance", "source_system", "world_revision",
                                          "event_id", "event_type"])
    def test_required_fields(self, required: str) -> None:
        """C6：provenance / source_system / world_revision 必填（含身份字段）。"""
        data = _sample_domain_event_data()
        del data[required]
        with pytest.raises(ValidationError):
            DomainEvent.model_validate(data)

    def test_defaults(self) -> None:
        event = DomainEvent.model_validate(
            {
                "event_id": "evt_" + _HEX32["e"],
                "event_type": "tick",
                "world_revision": 1,
                "source_system": "system.kernel",
                "provenance": _sample_provenance_data(producer_id="system.kernel",
                                                      origin="system"),
            }
        )
        assert event.logical_tick is None
        assert event.transaction_id is None  # 无事务的 runtime 事实可为 None
        assert event.payload == {}
        assert event.cause_ids == []
        assert event.cascade is None
        assert event.wall_time is None

    def test_cause_ids_all_kinds_accepted(self) -> None:
        """C6：CauseRef 五种 kind 均可承载。"""
        causes = [
            {"kind": kind.value, "ref_id": "ref_" + kind.value} for kind in CauseKind
        ]
        event = _sample_domain_event(cause_ids=causes)
        assert [cause.kind for cause in event.cause_ids] == list(CauseKind)
        with pytest.raises(ValidationError):
            _sample_domain_event(cause_ids=[{"kind": "bogus", "ref_id": "x"}])

    def test_cascade_fields_carried(self) -> None:
        """C6：cascade 上下文 depth/root 可承载（§21.3 数据承载，§5.7）。"""
        event = _sample_domain_event()
        assert event.cascade is not None
        assert type(event.cascade.cascade_id) is CascadeId
        assert event.cascade.causal_root_id == "act_" + _HEX32["a"]
        assert event.cascade.depth == 1

    def test_wall_time_iso_roundtrip(self) -> None:
        """决策 D-14：wall_time 为诊断侧 ISO-8601；权威序用 logical_tick/world_revision。"""
        event = _sample_domain_event()
        dumped = event.model_dump(mode="json")
        assert type(dumped["wall_time"]) is str
        assert dumped["wall_time"].startswith("2026-05-04T12:30:00")
        reloaded = DomainEvent.model_validate(dumped)
        assert reloaded.wall_time == datetime(2026, 5, 4, 12, 30, tzinfo=timezone.utc)

    def test_roundtrip_full_type_preserved(self) -> None:
        event = _sample_domain_event()
        dumped = event.model_dump(mode="json")
        _assert_json_clean(dumped)
        assert dumped["payload"]["开启者"] == "alice"
        reloaded = DomainEvent.model_validate(dumped)
        assert reloaded == event
        assert type(reloaded.event_id) is EventId
        assert type(reloaded.event_type) is EventTypeId
        assert type(reloaded.world_revision) is Revision
        assert type(reloaded.transaction_id) is TransactionId
        assert type(reloaded.source_system) is ProducerId
        assert type(reloaded.provenance.producer_id) is ProducerId


# —— C4/C5：Transaction 四条不变量 ——


class TestTransactionInvariants:
    """C4 事务原子不变量 + C5 一致性 + 部分提交不可表达（§5.6）。"""

    def test_status_vocabulary(self) -> None:
        assert {member.value for member in TransactionStatus} == {"committed", "aborted"}

    def test_field_set_matches_design_doc(self) -> None:
        assert set(Transaction.model_fields) == {
            "transaction_id",
            "status",
            "base_revision",
            "commit_revision",
            "logical_tick",
            "effects",
            "event_ids",
            "cascade",
            "provenance",
            "abort_reason",
        }

    def test_committed_valid(self) -> None:
        txn = _sample_committed_txn()
        assert txn.commit_revision == Revision(813)
        assert len(txn.effects) == 2
        assert type(txn.status) is TransactionStatus

    @pytest.mark.parametrize("commit", [812, 814, 811, 900])
    def test_committed_commit_revision_must_equal_base_plus_1(self, commit: int) -> None:
        """不变量 1/4：commit_revision == base_revision + 1 是唯一可表达形态。"""
        with pytest.raises(ValidationError):
            Transaction.model_validate(_sample_committed_txn_data(commit_revision=commit))

    def test_committed_requires_commit_revision(self) -> None:
        data = _sample_committed_txn_data()
        del data["commit_revision"]
        with pytest.raises(ValidationError):
            Transaction.model_validate(data)

    def test_committed_requires_nonempty_effects(self) -> None:
        """不变量 1：空事务不产生状态变化，不应消耗 revision。"""
        with pytest.raises(ValidationError):
            Transaction.model_validate(_sample_committed_txn_data(effects=[]))

    def test_aborted_requires_no_revision(self) -> None:
        """不变量 2：ABORTED ⇒ commit_revision is None。"""
        with pytest.raises(ValidationError):
            _sample_aborted_txn(commit_revision=813)

    def test_aborted_requires_empty_effects(self) -> None:
        """不变量 2：ABORTED ⇒ effects == []。"""
        ce = _sample_committed_effect(1, "txn_" + _HEX32["c"], 813)
        with pytest.raises(ValidationError):
            _sample_aborted_txn(effects=[ce])

    def test_partial_commit_not_expressible(self) -> None:
        """不变量 2 数据形态：任何 effect 要么全体落盘，要么全体不落盘（§20.1）。"""
        ce = _sample_committed_effect(1, "txn_" + _HEX32["c"], 813)
        # ABORTED + 部分 effects → 拒绝
        with pytest.raises(ValidationError):
            _sample_aborted_txn(effects=[ce])
        # ABORTED + revision → 拒绝
        with pytest.raises(ValidationError):
            _sample_aborted_txn(commit_revision=813)
        # COMMITTED + 缺 revision → 拒绝（effects 在场也不允许悬空）
        data = _sample_committed_txn_data()
        del data["commit_revision"]
        with pytest.raises(ValidationError):
            Transaction.model_validate(data)
        # ABORTED 最小形态合法：无 revision 无 effects
        aborted = _sample_aborted_txn()
        assert aborted.commit_revision is None
        assert aborted.effects == []
        assert aborted.abort_reason is not None

    @pytest.mark.parametrize(
        "sequences",
        [[1], [0, 2], [0, 0], [0, 1, 3], [2, 1, 3]],
        ids=["not_from_zero", "gap", "duplicate", "gap_tail", "dup_and_gap"],
    )
    def test_sequence_must_be_unique_and_contiguous_from_zero(self, sequences: list[int]) -> None:
        """不变量 3：sequence 唯一且自 0 连续（reducer 确定性，§20.2）。"""
        txn_id = "txn_" + _HEX32["b"]
        effects = [
            CommittedEffect(
                effect=_sample_proposed_effect(index=i + 1),
                transaction_id=TransactionId(txn_id),
                commit_revision=Revision(813),
                sequence=seq,
            )
            for i, seq in enumerate(sequences)
        ]
        with pytest.raises(ValidationError):
            Transaction(
                transaction_id=TransactionId(txn_id),
                status=TransactionStatus.COMMITTED,
                base_revision=Revision(812),
                commit_revision=Revision(813),
                effects=effects,
            )

    @pytest.mark.parametrize("sequences", [[0], [0, 1, 2], [2, 1, 0]],
                             ids=["single", "ordered", "unordered_set_complete"])
    def test_sequence_valid_sets_accepted(self, sequences: list[int]) -> None:
        """sequence 集合恰为 {0..n-1} 即合法（列表顺序不是不变量的一部分）。"""
        txn_id = "txn_" + _HEX32["b"]
        effects = [
            CommittedEffect(
                effect=_sample_proposed_effect(index=i + 1),
                transaction_id=TransactionId(txn_id),
                commit_revision=Revision(813),
                sequence=seq,
            )
            for i, seq in enumerate(sequences)
        ]
        txn = Transaction(
            transaction_id=TransactionId(txn_id),
            status=TransactionStatus.COMMITTED,
            base_revision=Revision(812),
            commit_revision=Revision(813),
            effects=effects,
        )
        assert [effect.sequence for effect in txn.effects] == sequences

    def test_duplicate_effect_id_within_transaction_rejected(self) -> None:
        """C7 数据级 / KBC-2 防线：同一 effect_id 重复进同一事务 → 拒绝。"""
        txn_id = "txn_" + _HEX32["b"]
        same_effect = _sample_proposed_effect(index=1)
        effects = [
            CommittedEffect(
                effect=same_effect,
                transaction_id=TransactionId(txn_id),
                commit_revision=Revision(813),
                sequence=seq,
            )
            for seq in (0, 1)
        ]
        with pytest.raises(ValidationError, match="effect_id 重复"):
            Transaction(
                transaction_id=TransactionId(txn_id),
                status=TransactionStatus.COMMITTED,
                base_revision=Revision(812),
                commit_revision=Revision(813),
                effects=effects,
            )

    def test_c5_effects_share_transaction_id_and_commit_revision(self) -> None:
        """C5：事务内全部 effects 共享同一 transaction_id/commit_revision。"""
        txn_id = "txn_" + _HEX32["b"]
        # transaction_id 不一致 → 拒绝
        foreign = CommittedEffect(
            effect=_sample_proposed_effect(index=2),
            transaction_id=TransactionId("txn_" + _HEX32["c"]),
            commit_revision=Revision(813),
            sequence=1,
        )
        good = _sample_committed_effect(1, txn_id, 813)
        with pytest.raises(ValidationError, match="transaction_id"):
            Transaction(
                transaction_id=TransactionId(txn_id),
                status=TransactionStatus.COMMITTED,
                base_revision=Revision(812),
                commit_revision=Revision(813),
                effects=[good, foreign],
            )
        # commit_revision 不一致 → 拒绝
        foreign_rev = CommittedEffect(
            effect=_sample_proposed_effect(index=3),
            transaction_id=TransactionId(txn_id),
            commit_revision=Revision(999),
            sequence=1,
        )
        with pytest.raises(ValidationError, match="commit_revision"):
            Transaction(
                transaction_id=TransactionId(txn_id),
                status=TransactionStatus.COMMITTED,
                base_revision=Revision(812),
                commit_revision=Revision(813),
                effects=[good, foreign_rev],
            )
        # 一致 → 通过：全部 effects 与事务共享同一 transaction_id/commit_revision
        txn = _sample_committed_txn()
        assert all(effect.transaction_id == txn.transaction_id for effect in txn.effects)
        assert all(effect.commit_revision == txn.commit_revision for effect in txn.effects)

    def test_invariant4_commit_advances_revision_exactly_one(self) -> None:
        """不变量 4：一次 COMMITTED 使 world_revision 恰 +1（测试桩表达 P2 reducer 语义）。"""
        txn = _sample_committed_txn()
        world_revision = txn.base_revision
        # 测试桩：唯一合法的应用结果（P2 reducer 的语义预览）
        new_revision = (
            next_revision(world_revision) if txn.status is TransactionStatus.COMMITTED
            else world_revision
        )
        assert new_revision == txn.commit_revision
        assert int(txn.commit_revision) - int(txn.base_revision) == 1
        # 且仅可如此表达：+2 被 schema 拒绝
        with pytest.raises(ValidationError):
            Transaction.model_validate(_sample_committed_txn_data(commit_revision=814))

    def test_roundtrip_committed_type_preserved(self) -> None:
        txn = _sample_committed_txn()
        dumped = txn.model_dump(mode="json")
        _assert_json_clean(dumped)
        assert dumped["status"] == "committed"
        assert type(dumped["base_revision"]) is int
        assert type(dumped["effects"][0]["effect"]["effect_id"]) is str
        assert dumped["effects"][0]["effect"]["target"]["kind"] == "entity"
        reloaded = Transaction.model_validate(dumped)
        assert reloaded == txn
        assert type(reloaded.transaction_id) is TransactionId
        assert type(reloaded.status) is TransactionStatus
        assert type(reloaded.base_revision) is Revision
        assert type(reloaded.commit_revision) is Revision
        assert all(type(event_id) is EventId for event_id in reloaded.event_ids)
        assert type(reloaded.cascade) is CascadeContext
        assert type(reloaded.effects[0].effect.effect_id) is EffectId

    def test_roundtrip_aborted(self) -> None:
        txn = _sample_aborted_txn()
        dumped = txn.model_dump(mode="json")
        _assert_json_clean(dumped)
        assert dumped["status"] == "aborted"
        assert dumped["commit_revision"] is None
        assert dumped["effects"] == []
        reloaded = Transaction.model_validate(dumped)
        assert reloaded == txn
        assert reloaded.commit_revision is None
        assert reloaded.effects == []

    def test_provenance_optional_on_transaction(self) -> None:
        """§5.6：provenance 可空（如 developer 注入事务则携带 origin=developer）。"""
        txn = _sample_committed_txn()
        assert txn.provenance is not None
        dev_txn = Transaction.model_validate(
            _sample_committed_txn_data(
                provenance={"producer_id": "dev.console", "origin": "developer"}
            )
        )
        assert dev_txn.provenance is not None
        assert dev_txn.provenance.origin is OriginKind.DEVELOPER  # Spec §22


# —— extra=forbid / frozen / Unicode / 边界值 ——


_MINIMAL_VALID_DATA: list[tuple[type, dict[str, Any]]] = [
    (Provenance, {"producer_id": "policy.alice", "origin": "behavior_policy"}),
    (CauseRef, {"kind": "event", "ref_id": "evt_" + _HEX32["e"]}),
    (CascadeContext, {"cascade_id": "csc_" + _HEX32["f"],
                      "causal_root_id": "evt_" + _HEX32["e"]}),
    (ActionTiming, {}),
    (FallbackSpec, {"action_id": "wait"}),
    (ActionProposal, {
        "proposal_id": "act_" + _HEX32["a"],
        "actor_id": "ent_alice",
        "action_id": "rest",
        "base_world_revision": 0,
        "provenance": {"producer_id": "policy.alice", "origin": "behavior_policy"},
    }),
    (ActiveAction, {
        "instance_id": "act_" + _HEX32["a"],
        "action_id": "rest",
        "actor_id": "ent_alice",
        "status": "proposed",
        "start_tick": 0,
        "base_world_revision": 0,
        "provenance": {"producer_id": "policy.alice", "origin": "behavior_policy"},
    }),
    (EntityTarget, {"entity_id": "ent_x"}),
    (StateDomainTarget, {"domain": "world_variables"}),
    (ProposedEffect, {
        "effect_id": "eff_" + _HEX32["0"],
        "effect_type": "unlock",
        "source": "rule.lock_system",
        "target": {"kind": "state_domain", "domain": "world_variables"},
        "payload": {},
        "base_revision": 0,
    }),
    (CommittedEffect, {
        "effect": {
            "effect_id": "eff_" + _HEX32["0"],
            "effect_type": "unlock",
            "source": "rule.lock_system",
            "target": {"kind": "state_domain", "domain": "world_variables"},
            "payload": {},
            "base_revision": 0,
        },
        "transaction_id": "txn_" + _HEX32["b"],
        "commit_revision": 1,
        "sequence": 0,
    }),
    (DomainEvent, {
        "event_id": "evt_" + _HEX32["e"],
        "event_type": "tick",
        "world_revision": 1,
        "source_system": "system.kernel",
        "provenance": {"producer_id": "system.kernel", "origin": "system"},
    }),
    (Transaction, {
        "transaction_id": "txn_" + _HEX32["c"],
        "status": "aborted",
        "base_revision": 0,
    }),
]


class TestExtraForbidAndFrozen:
    """J2/S5 口径：全部 T04 模型 extra=forbid + frozen 阻断字段再赋值。"""

    @pytest.mark.parametrize(
        ("cls", "data"),
        _MINIMAL_VALID_DATA,
        ids=[cls.__name__ for cls, _ in _MINIMAL_VALID_DATA],
    )
    def test_extra_forbid(self, cls: type, data: dict[str, Any]) -> None:
        """注入未知字段 → 校验失败（契约冻结的程序化守卫）。"""
        with pytest.raises(ValidationError):
            cls.model_validate({**data, "__bogus__": 1})

    @pytest.mark.parametrize(
        ("cls", "data", "field_name", "value"),
        [
            (Provenance, _MINIMAL_VALID_DATA[0][1], "notes", "x"),
            (CascadeContext, _MINIMAL_VALID_DATA[2][1], "depth", 1),
            (ActionProposal, _MINIMAL_VALID_DATA[5][1], "intent", "x"),
            (ActiveAction, _MINIMAL_VALID_DATA[6][1], "progress", 0.5),
            (ProposedEffect, _MINIMAL_VALID_DATA[9][1], "authority_scope", "x"),
            (CommittedEffect, _MINIMAL_VALID_DATA[10][1], "sequence", 1),
            (DomainEvent, _MINIMAL_VALID_DATA[11][1], "logical_tick", 1),
            (Transaction, _MINIMAL_VALID_DATA[12][1], "abort_reason", "x"),
        ],
        ids=["Provenance", "CascadeContext", "ActionProposal", "ActiveAction",
             "ProposedEffect", "CommittedEffect", "DomainEvent", "Transaction"],
    )
    def test_frozen_blocks_assignment(
        self, cls: type, data: dict[str, Any], field_name: str, value: Any
    ) -> None:
        model = cls.model_validate(data)
        with pytest.raises((ValidationError, TypeError)):
            setattr(model, field_name, value)


class TestUnicodeAndBoundaryValues:
    """J7 口径：中文内容、空 dict、大整数 round-trip 无损。"""

    def test_chinese_content_roundtrip(self) -> None:
        proposal = _sample_proposal(intent="前往集市", provenance=_sample_provenance_data(
            notes="中文来源备注"))
        reloaded = ActionProposal.model_validate(proposal.model_dump(mode="json"))
        assert reloaded.intent == "前往集市"
        assert reloaded.provenance.notes == "中文来源备注"

    def test_boundary_values_roundtrip(self) -> None:
        effect = _sample_proposed_effect(
            base_revision=10**15,
            payload={"大整数": 10**18, "浮点": 1e308, "空": {}, "列表": []},
            metadata={},
        )
        dumped = effect.model_dump(mode="json")
        _assert_json_clean(dumped)
        reloaded = ProposedEffect.model_validate(dumped)
        assert reloaded == effect
        assert reloaded.payload["大整数"] == 10**18
        assert reloaded.payload["空"] == {}


# —— import 边界（§0.3 / B1/B2）——


class TestImportBoundary:
    """五个新模块只 import 标准库、pydantic 与同包 src.engine_v2。"""

    _STDLIB = {
        "__future__",
        "re",
        "enum",
        "datetime",
        "typing",
        "ast",
        "importlib",
        "sys",
        "pathlib",
    }

    @pytest.mark.parametrize(
        "module",
        [provenance_module, effects_module, actions_module, events_module,
         transaction_module],
        ids=["provenance", "effects", "actions", "events", "transaction"],
    )
    def test_only_whitelisted_imports(self, module: Any) -> None:
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        violations: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._check(alias.name, violations)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                self._check(node.module, violations)
        assert not violations, f"白名单外 import：{violations}"

    def _check(self, dotted: str, violations: set[str]) -> None:
        root = dotted.split(".")[0]
        if root == "src":
            assert dotted.startswith("src.engine_v2"), (
                f"同包 import 必须指向 src.engine_v2，得到 {dotted}"
            )
        elif root not in self._STDLIB | {"pydantic"}:
            violations.add(dotted)

    def test_fresh_import_pulls_no_forbidden_modules(self) -> None:
        """B2 口径：fresh import 五个新模块不新载入黑名单依赖。"""
        names = [
            "src.engine_v2.core.provenance",
            "src.engine_v2.core.effects",
            "src.engine_v2.core.actions",
            "src.engine_v2.core.events",
            "src.engine_v2.core.transaction",
        ]
        for name in names:
            sys.modules.pop(name, None)
        before = set(sys.modules)
        for name in names:
            importlib.import_module(name)
        pulled = set(sys.modules) - before
        forbidden_prefixes = ("langgraph", "langchain", "openai", "rich", "yaml")
        bad = sorted(
            name
            for name in pulled
            if any(name == p or name.startswith(p + ".") for p in forbidden_prefixes)
        )
        assert not bad, f"import T04 模块过程中新载入了禁止依赖：{bad}"
