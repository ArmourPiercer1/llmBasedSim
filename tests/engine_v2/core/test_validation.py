"""P2-T04 Effect Validation 管道与 C2 晋升验收（P2 设计规范 §4 全量）。

覆盖（P2 设计规范 §4 / 任务包 P2-T04 逐项落位）：

- **阶段 1 ID 种类与前缀严格校验**（§4.4 / D-P2-15 / D-P2-20，
  ``check_effect_id_kinds``）：跨种类 typed ID 实例的静默重建攻击
  （P1-T07 §D.2 口径：``EffectId`` 值落入 ``target.entity_id``）、
  错误前缀串、名字型 source 被前缀串冒充、cause_ids 按 CauseKind 的
  期望种类（INTERVENTION → ``trc_``，D-P2-20）、component_type /
  domain / effect_type 词法；问题串格式
  ``bad_id_kind:<field>:expected=<kind> got=<kind|lexErr>:value=<v>``；
- **L1 单效果基础校验器**（任务包口径 ``validate_proposed_effect`` →
  ``(bool, str | None)``）：实体存在性（``core.create_entity`` 豁免）、
  组件 Schema/Registry 校验（D-8 边界：未注册放行 / 有 schema 拒绝
  非法 payload）、base_revision stale 判定（``is_stale`` 单向语义）+
  未来版本拒绝（``future_base_revision``）、domain 词表
  （``unknown_domain``）、field_path 四规则（§4.6）、结构前置条件
  （与 reducer 同规则）、no_handler（D-P2-05）；**多问题一次性收齐**
  （阶段不短路）；
- **L1 批级过滤语义**（D-P2-10 第一层，``EffectValidator.validate_batch``）：
  失败 effect 被过滤、其余继续；批级 ``duplicated_effect_id``（同批同
  ID 全部副本被拒，KBC-2 防线，问题串与 C7 同构）；``ValidationReport``
  形态（``accepted`` / ``issues`` / ``issues_for`` / ``ok``）；
- **L2 事务终检 C2 晋升接线**（§4.5）：``check_transaction_references``
  / ``TRANSACTION_REFERENCE_ISSUE_KINDS`` 自 core 可达且与包级
  re-export 同一对象；问题串格式与单向 stale 语义（与
  ``test_transaction_references.py`` 15 例共同固化）；
- **任务包组合面**：``ValidationPipeline.run`` 严格模式（任何问题 →
  ``ValidationError``，携带全量 issue；零问题 → accepted）与
  ``ValidationError`` 形态（``ValueError`` 派生、``issues`` 属性、
  分号串接消息）；
- **包级 re-export**：validation 11 个公开名自 ``src.engine_v2.core``
  可达且与模块属性同一对象（D-P2-19）。

全部用例无网络、无 LLM、无 API key。
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

import src.engine_v2.core as core_pkg
# 模块级 import（收集期绑定，与 core_pkg 同一模块代次）：``test_import_boundary``
# 的 B2 fresh-import 用例会在执行期 pop/重 import/恢复 sys.modules，其 finally
# 恢复 sys.modules 但**不恢复**父包 ``src.engine_v2.core`` 属性链（bpo-30024：
# 子模块 import 会在父包对象上绑定同名属性）——执行期内 ``import ... as``
# 属性链可能拿到恢复后的"另一代"模块对象（P1 设计"同名遮蔽豁免"注记同款
# 陷阱）。收集期绑定保证本文件全部断言在同一自洽模块图上进行（与
# ``test_closeout.py`` 收集期捕获同款纪律）。
import src.engine_v2.core.validation as validation_mod
from src.engine_v2.core import (
    check_effect_id_kinds,
    check_transaction_references,
)
from src.engine_v2.core.components import ComponentRegistry, ComponentSchema, ComponentTypeId
from src.engine_v2.core.effects import (
    CommittedEffect,
    EffectTypeId,
    EntityTarget,
    ProposedEffect,
    StateDomainId,
    StateDomainTarget,
)
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.ids import EffectId, EntityId, ProducerId, new_transaction_id
from src.engine_v2.core.provenance import CauseKind, CauseRef
from src.engine_v2.core.reducer import default_handler_registry
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.state import WorldState
from src.engine_v2.core.transaction import Transaction, TransactionStatus
from src.engine_v2.core.validation import (
    TRANSACTION_REFERENCE_ISSUE_KINDS,
    VALIDATION_ISSUE_KINDS,
    EffectValidator,
    ValidationError,
    ValidationContext,
    ValidationPipeline,
    validate_proposed_effect,
)


# —— 测试样本工厂（自包含、确定性构造）——


class _PositionModel(BaseModel):
    """测试用组件 payload schema（字段 x / y 均为 int）。"""

    x: int
    y: int


def _make_state(
    world_revision: int = 0,
    entity_ids: tuple[str, ...] = (),
    components: dict[str, dict[ComponentTypeId, dict[str, Any]]] | None = None,
    world_variables: dict[str, Any] | None = None,
) -> WorldState:
    return WorldState(
        world_revision=Revision(world_revision),
        entities={
            EntityId(eid): EntityRecord(
                entity_id=EntityId(eid),
                components=dict((components or {}).get(eid, {})),
            )
            for eid in entity_ids
        },
        world_variables=dict(world_variables or {}),
    )


def _position_registry() -> ComponentRegistry:
    registry = ComponentRegistry()
    registry.register(
        ComponentSchema(
            component_type=ComponentTypeId("space.position"),
            payload_model=_PositionModel,
        )
    )
    return registry


def _make_effect(
    effect_id: str,
    effect_type: str,
    target: EntityTarget | StateDomainTarget,
    payload: dict[str, Any],
    *,
    base_revision: int = 0,
    source: str = "rule.lock_system",
    cause_ids: list[CauseRef] | None = None,
) -> ProposedEffect:
    return ProposedEffect(
        effect_id=EffectId(effect_id),
        effect_type=EffectTypeId(effect_type),
        source=ProducerId(source),
        target=target,
        payload=payload,
        base_revision=Revision(base_revision),
        cause_ids=list(cause_ids or []),
    )


def _make_effect_via_roundtrip(**overrides: Any) -> ProposedEffect:
    """经 ``model_validate`` 构造——typed ID 的 pydantic 路径不校验前缀
    词法（P1-T07 §D.2：跨种类静默重建攻击面），ID 攻击用例必经此路径。"""
    data: dict[str, Any] = {
        "effect_id": "eff_vt_1",
        "effect_type": "core.set_world_variable",
        "source": "rule.lock_system",
        "target": {"kind": "state_domain", "domain": "world_variables"},
        "payload": {"key": "k", "value": 1},
        "base_revision": 0,
    }
    data.update(overrides)
    return ProposedEffect.model_validate(data)


def _entity_target(
    entity_id: str, component_type: str | None = None, field_path: str | None = None
) -> EntityTarget:
    return EntityTarget(
        entity_id=EntityId(entity_id),
        component_type=ComponentTypeId(component_type) if component_type else None,
        field_path=field_path,
    )


def _domain_target(domain: str) -> StateDomainTarget:
    return StateDomainTarget(domain=StateDomainId(domain))


def _set_world_variable(effect_id: str, key: str = "k", base_revision: int = 0) -> ProposedEffect:
    return _make_effect(
        effect_id,
        "core.set_world_variable",
        _domain_target("world_variables"),
        {"key": key, "value": 1},
        base_revision=base_revision,
    )


def _make_committed_txn(base_revision: int, effects: list[ProposedEffect]) -> Transaction:
    txn_id = new_transaction_id()
    commit_revision = Revision(base_revision + 1)
    return Transaction(
        transaction_id=txn_id,
        status=TransactionStatus.COMMITTED,
        base_revision=Revision(base_revision),
        commit_revision=commit_revision,
        effects=[
            CommittedEffect(
                effect=effect,
                transaction_id=txn_id,
                commit_revision=commit_revision,
                sequence=sequence,
            )
            for sequence, effect in enumerate(effects)
        ],
    )


# —— 阶段 1：check_effect_id_kinds（§4.4 / D-P2-15 / D-P2-20）——


class TestCheckEffectIdKinds:
    """跨种类 ID 词法与前缀严格校验（P1 §10.1 义务 3）。"""

    def test_clean_effect_no_issues(self) -> None:
        effect = _make_effect(
            "eff_clean",
            "core.set_world_variable",
            _entity_target("ent_a"),
            {},
        )
        assert check_effect_id_kinds(effect) == ()

    def test_cross_kind_typed_id_in_entity_id_rejected(self) -> None:
        """P1-T07 §D.2 攻击面：``eff_`` 前缀值静默重建进 EntityId 字段。"""
        effect = _make_effect_via_roundtrip(
            target={"kind": "entity", "entity_id": "eff_cross_kind"}
        )
        assert type(effect.target) is EntityTarget
        assert check_effect_id_kinds(effect) == (
            "bad_id_kind:target.entity_id:expected=EntityId got=EffectId:"
            "value=eff_cross_kind",
        )

    def test_wrong_prefix_string_in_effect_id_rejected(self) -> None:
        effect = _make_effect_via_roundtrip(effect_id="evt_wrong_family")
        assert check_effect_id_kinds(effect) == (
            "bad_id_kind:effect_id:expected=EffectId got=EventId:value=evt_wrong_family",
        )

    def test_source_with_prefixed_value_rejected(self) -> None:
        """名字型 source 被前缀型 ID 值冒充（parse_id 判为 EntityId）。"""
        effect = _make_effect_via_roundtrip(source="ent_alice")
        assert check_effect_id_kinds(effect) == (
            "bad_id_kind:source:expected=ProducerId got=EntityId:value=ent_alice",
        )

    def test_source_invalid_lexicon_reported_as_lexerr(self) -> None:
        effect = _make_effect_via_roundtrip(source="Bad-Name")
        assert check_effect_id_kinds(effect) == (
            "bad_id_kind:source:expected=ProducerId got=lexErr:value=Bad-Name",
        )

    def test_cause_ref_expected_kinds_all_valid(self) -> None:
        """五种 CauseKind 的 ref_id 按期望种类全合法 → 无问题（D-P2-20）。"""
        effect = _make_effect(
            "eff_cause",
            "core.set_world_variable",
            _domain_target("world_variables"),
            {"key": "k", "value": 1},
            cause_ids=[
                CauseRef(kind=CauseKind.EVENT, ref_id="evt_abc"),
                CauseRef(kind=CauseKind.ACTION, ref_id="act_abc"),
                CauseRef(kind=CauseKind.EFFECT, ref_id="eff_abc"),
                CauseRef(kind=CauseKind.PROPOSAL, ref_id="act_xyz"),
                CauseRef(kind=CauseKind.INTERVENTION, ref_id="trc_abc"),
            ],
        )
        assert check_effect_id_kinds(effect) == ()

    def test_cause_ref_intervention_non_trace_rejected(self) -> None:
        """INTERVENTION 必须为 ``trc_`` 词法（D-P2-20：trace 记录承载）。

        ``dev_intervention_x`` 无前缀但匹配 ProducerId 名字词法 → 以 parse
        结果报告 got=ProducerId（种类不符）；带连字符值则 got=lexErr。
        """
        effect = _make_effect_via_roundtrip(
            cause_ids=[{"kind": "intervention", "ref_id": "dev_intervention_x"}]
        )
        assert check_effect_id_kinds(effect) == (
            "bad_id_kind:cause_ids[0].ref_id:expected=TraceRecordId got=ProducerId:"
            "value=dev_intervention_x",
        )
        effect_lexerr = _make_effect_via_roundtrip(
            cause_ids=[{"kind": "intervention", "ref_id": "dev-x"}]
        )
        assert check_effect_id_kinds(effect_lexerr) == (
            "bad_id_kind:cause_ids[0].ref_id:expected=TraceRecordId got=lexErr:"
            "value=dev-x",
        )

    def test_cause_ref_cross_family_rejected(self) -> None:
        effect = _make_effect_via_roundtrip(
            cause_ids=[{"kind": "event", "ref_id": "eff_wrong_family"}]
        )
        assert check_effect_id_kinds(effect) == (
            "bad_id_kind:cause_ids[0].ref_id:expected=EventId got=EffectId:"
            "value=eff_wrong_family",
        )

    def test_bad_component_type_lexicon(self) -> None:
        effect = _make_effect_via_roundtrip(
            target={"kind": "entity", "entity_id": "ent_a", "component_type": "Bad_Type"}
        )
        assert check_effect_id_kinds(effect) == (
            "bad_id_kind:target.component_type:expected=ComponentTypeId got=lexErr:"
            "value=Bad_Type",
        )

    def test_bad_domain_lexicon(self) -> None:
        effect = _make_effect_via_roundtrip(
            target={"kind": "state_domain", "domain": "World-Variables"}
        )
        assert check_effect_id_kinds(effect) == (
            "bad_id_kind:target.domain:expected=StateDomainId got=lexErr:"
            "value=World-Variables",
        )

    def test_bad_effect_type_lexicon(self) -> None:
        effect = _make_effect_via_roundtrip(effect_type="Bad.Type")
        assert check_effect_id_kinds(effect) == (
            "bad_id_kind:effect_type:expected=EffectTypeId got=lexErr:value=Bad.Type",
        )

    def test_pure_function_deterministic(self) -> None:
        effect = _make_effect_via_roundtrip(target={"kind": "entity", "entity_id": "eff_x"})
        assert isinstance(check_effect_id_kinds(effect), tuple)
        assert check_effect_id_kinds(effect) == check_effect_id_kinds(effect)


# —— L1 单效果基础校验器（任务包口径 validate_proposed_effect）——


class TestValidateProposedEffect:
    """L1 单效果七阶段管道（阶段 2–7 + 任务包 (bool, str | None) 表面）。"""

    def test_clean_structural_effect_passes(self) -> None:
        state = _make_state(world_revision=3, entity_ids=("ent_a",))
        effect = _make_effect(
            "eff_ok", "core.set_component", _entity_target("ent_a", "space.position"),
            {"x": 1, "y": 2}, base_revision=3,
        )
        assert validate_proposed_effect(effect, state) == (True, None)

    def test_missing_entity_rejected(self) -> None:
        state = _make_state(world_revision=0, entity_ids=("ent_a",))
        effect = _make_effect(
            "eff_m", "core.set_component", _entity_target("ent_missing", "space.position"), {"x": 1}
        )
        ok, reason = validate_proposed_effect(effect, state)
        assert ok is False
        assert reason == "missing_entity:eff_m:target=ent_missing 不存在于 WorldState"

    def test_create_entity_exempt_from_missing_entity(self) -> None:
        """core.create_entity 豁免实体存在性（其 target 是新 ID）。"""
        state = _make_state(world_revision=0)
        effect = _make_effect(
            "eff_create", "core.create_entity", _entity_target("ent_new"), {}
        )
        assert validate_proposed_effect(effect, state) == (True, None)

    def test_create_entity_existing_rejected_as_precondition(self) -> None:
        state = _make_state(world_revision=0, entity_ids=("ent_a",))
        effect = _make_effect("eff_dup_create", "core.create_entity", _entity_target("ent_a"), {})
        ok, reason = validate_proposed_effect(effect, state)
        assert ok is False
        assert "precondition_failed:eff_dup_create:core.create_entity 前置条件不满足：" in reason
        assert "entity 已存在：ent_a" in reason

    def test_remove_entity_missing_rejected(self) -> None:
        state = _make_state(world_revision=0)
        effect = _make_effect(
            "eff_rm", "core.remove_entity", _entity_target("ent_missing"), {}
        )
        ok, reason = validate_proposed_effect(effect, state)
        assert ok is False
        assert "missing_entity:eff_rm:target=ent_missing" in reason

    def test_remove_component_not_attached_rejected(self) -> None:
        state = _make_state(world_revision=0, entity_ids=("ent_a",))  # ent_a 无组件
        effect = _make_effect(
            "eff_rc", "core.remove_component", _entity_target("ent_a", "space.position"), {}
        )
        ok, reason = validate_proposed_effect(effect, state)
        assert ok is False
        assert reason == (
            "missing_component:eff_rc:entity=ent_a 未挂载组件 space.position"
        )

    def test_remove_component_entity_missing_reports_only_missing_entity(self) -> None:
        """阶段间分工：entity 不存在由阶段 4 专属 kind 报告一次，
        阶段 7 不重复报同事实（模块 docstring"阶段间分工"）。"""
        state = _make_state(world_revision=0)
        effect = _make_effect(
            "eff_rc2", "core.remove_component", _entity_target("ent_missing", "space.position"), {}
        )
        ok, reason = validate_proposed_effect(effect, state)
        assert ok is False
        assert reason is not None
        assert reason.count("; ") == 0, f"同事实被双报告：{reason}"
        assert reason.startswith("missing_entity:")

    def test_stale_revision_rejected(self) -> None:
        state = _make_state(world_revision=813, entity_ids=("ent_a",))
        effect = _set_world_variable("eff_stale", base_revision=812)
        ok, reason = validate_proposed_effect(effect, state)
        assert ok is False
        assert reason == "stale_revision:eff_stale:base=812 current=813"

    def test_future_base_revision_rejected(self) -> None:
        """base > current → 未来版本不存在，确定性管道拒绝（必须测试 7.5）。"""
        state = _make_state(world_revision=8)
        effect = _set_world_variable("eff_future", base_revision=9)
        ok, reason = validate_proposed_effect(effect, state)
        assert ok is False
        assert reason == "future_base_revision:eff_future:base=9 current=8"

    def test_fresh_base_passes(self) -> None:
        state = _make_state(world_revision=813)
        fresh = _set_world_variable("eff_fresh", base_revision=813)
        assert validate_proposed_effect(fresh, state) == (True, None)

    def test_bad_payload_extra_key_rejected(self) -> None:
        """EmptyPayload（extra=forbid）拒绝多余键。"""
        state = _make_state(world_revision=0, entity_ids=("ent_a",))
        effect = _make_effect(
            "eff_extra", "core.remove_entity", _entity_target("ent_a"), {"foo": 1}
        )
        ok, reason = validate_proposed_effect(effect, state)
        assert ok is False
        assert "bad_payload:eff_extra:payload 不符合 EmptyPayload" in reason

    def test_bad_payload_missing_key_rejected(self) -> None:
        state = _make_state(world_revision=0)
        effect = _make_effect(
            "eff_nokey", "core.set_world_variable", _domain_target("world_variables"), {}
        )
        ok, reason = validate_proposed_effect(effect, state)
        assert ok is False
        assert "bad_payload:eff_nokey:payload 不符合 SetWorldVariablePayload" in reason

    def test_set_component_registry_schema_violation(self) -> None:
        state = _make_state(world_revision=0, entity_ids=("ent_a",))
        effect = _make_effect(
            "eff_bad_data",
            "core.set_component",
            _entity_target("ent_a", "space.position"),
            {"x": "不是整数", "y": 2},
        )
        ok, reason = validate_proposed_effect(effect, state, _position_registry())
        assert ok is False
        assert "bad_payload:eff_bad_data:组件 space.position 数据不符合已注册 schema" in reason

    def test_set_component_unregistered_component_passes(self) -> None:
        """D-8 边界策略：未注册组件类型放行（不透明 JSON dict）。"""
        state = _make_state(world_revision=0, entity_ids=("ent_a",))
        effect = _make_effect(
            "eff_unreg", "core.set_component", _entity_target("ent_a", "mystery.component"),
            {"anything": [1, 2, 3]},
        )
        assert validate_proposed_effect(effect, state, _position_registry()) == (True, None)

    def test_create_entity_component_schema_violation(self) -> None:
        """core.create_entity 的 components 逐项经 registry 校验（与 reducer 同规则）。"""
        state = _make_state(world_revision=0)
        effect = _make_effect(
            "eff_create_bad",
            "core.create_entity",
            _entity_target("ent_new"),
            {"entity_class": None, "tags": [], "components": {"space.position": {"x": "bad"}}},
        )
        ok, reason = validate_proposed_effect(effect, state, _position_registry())
        assert ok is False
        assert "组件 space.position 数据不符合已注册 schema" in reason

    def test_create_entity_bad_component_key_lexicon(self) -> None:
        state = _make_state(world_revision=0)
        effect = _make_effect(
            "eff_create_badkey",
            "core.create_entity",
            _entity_target("ent_new"),
            {"components": {"Bad_Type": {}}},
        )
        ok, reason = validate_proposed_effect(effect, state)
        assert ok is False
        assert "payload.components 键 'Bad_Type' 不是合法 ComponentTypeId" in reason

    def test_unknown_domain_rejected(self) -> None:
        state = _make_state(world_revision=0)
        effect = _make_effect(
            "eff_inv", "core.set_world_variable", _domain_target("inventory"),
            {"key": "k", "value": 1},
        )
        ok, reason = validate_proposed_effect(effect, state)
        assert ok is False
        assert "unknown_domain:eff_inv:domain='inventory'" in reason

    def test_no_handler_for_semantic_type(self) -> None:
        """handlers 在场且语义型未注册 → no_handler（D-P2-05 不推断）。"""
        state = _make_state(world_revision=0, entity_ids=("ent_a",))
        effect = _make_effect(
            "eff_sem", "space.move", _entity_target("ent_a"), {"dx": 1}
        )
        ok, reason = validate_proposed_effect(
            effect, state, handlers=default_handler_registry()
        )
        assert ok is False
        assert "no_handler:eff_sem:effect_type='space.move' 未注册 handler" in reason

    def test_no_handler_skipped_without_handlers(self) -> None:
        """handlers=None → 跳过 no_handler 阶段（纯数据校验场景）。"""
        state = _make_state(world_revision=0, entity_ids=("ent_a",))
        effect = _make_effect("eff_sem2", "space.move", _entity_target("ent_a"), {"dx": 1})
        assert validate_proposed_effect(effect, state) == (True, None)

    def test_structural_effect_type_passes_handler_stage(self) -> None:
        """结构效果恒预注册：handlers 在场时不误报 no_handler。"""
        state = _make_state(world_revision=0)
        effect = _set_world_variable("eff_struct")
        assert validate_proposed_effect(
            effect, state, handlers=default_handler_registry()
        ) == (True, None)

    def test_field_path_lexical_invalid(self) -> None:
        state = _make_state(world_revision=0, entity_ids=("ent_a",))
        effect = _make_effect(
            "eff_fp1", "space.move",
            _entity_target("ent_a", "space.position", field_path="Bad_Path"),
            {},
        )
        ok, reason = validate_proposed_effect(effect, state, _position_registry())
        assert ok is False
        assert "bad_field_path:eff_fp1:field_path='Bad_Path' 词法非法" in reason

    def test_field_path_requires_component_type(self) -> None:
        state = _make_state(world_revision=0, entity_ids=("ent_a",))
        effect = _make_effect(
            "eff_fp2", "space.move", _entity_target("ent_a", field_path="x"), {}
        )
        ok, reason = validate_proposed_effect(effect, state, _position_registry())
        assert ok is False
        assert "field_path 要求 target.component_type 非 None" in reason

    def test_field_path_component_not_registered(self) -> None:
        state = _make_state(world_revision=0, entity_ids=("ent_a",))
        effect = _make_effect(
            "eff_fp3", "space.move",
            _entity_target("ent_a", "mystery.component", field_path="x"),
            {},
        )
        ok, reason = validate_proposed_effect(effect, state, _position_registry())
        assert ok is False
        assert "mystery.component 未注册 schema 或 payload_model 为空" in reason

    def test_field_path_not_in_payload_model(self) -> None:
        state = _make_state(world_revision=0, entity_ids=("ent_a",))
        effect = _make_effect(
            "eff_fp4", "space.move",
            _entity_target("ent_a", "space.position", field_path="z"),
            {},
        )
        ok, reason = validate_proposed_effect(effect, state, _position_registry())
        assert ok is False
        assert "字段 'z' 不在组件 space.position 的 payload_model.model_fields 中" in reason

    def test_field_path_ok(self) -> None:
        state = _make_state(world_revision=0, entity_ids=("ent_a",))
        effect = _make_effect(
            "eff_fp5", "space.move",
            _entity_target("ent_a", "space.position", field_path="x"),
            {},
        )
        assert validate_proposed_effect(effect, state, _position_registry()) == (True, None)

    def test_field_path_without_registry_conservatively_rejected(self) -> None:
        """registry 缺席 → field_path 合法性不可判定 → 保守拒绝。"""
        state = _make_state(world_revision=0, entity_ids=("ent_a",))
        effect = _make_effect(
            "eff_fp6", "space.move",
            _entity_target("ent_a", "space.position", field_path="x"),
            {},
        )
        ok, reason = validate_proposed_effect(effect, state)
        assert ok is False
        expected = "bad_field_path:eff_fp6:组件 space.position 未注册 schema 或 payload_model 为空，field_path 不可用"
        assert reason == expected

    def test_world_variable_verb_domain_mismatch(self) -> None:
        """core.set_world_variable 要求 domain==world_variables（scenario 属词表但动词不匹配）。"""
        state = _make_state(world_revision=0)
        effect = _make_effect(
            "eff_dom", "core.set_world_variable", _domain_target("scenario"),
            {"key": "k", "value": 1},
        )
        ok, reason = validate_proposed_effect(effect, state)
        assert ok is False
        expected = (
            "precondition_failed:eff_dom:"
            "core.set_world_variable 要求 target.domain == 'world_variables'"
        )
        assert expected in reason

    def test_remove_world_variable_key_missing(self) -> None:
        state = _make_state(world_revision=0, world_variables={"a": 1})
        effect = _make_effect(
            "eff_rmkey", "core.remove_world_variable", _domain_target("world_variables"),
            {"key": "b"},
        )
        ok, reason = validate_proposed_effect(effect, state)
        assert ok is False
        assert "core.remove_world_variable 前置条件不满足：键 'b' 不存在于 world_variables" in reason

    def test_multiple_issues_accumulated_no_shortcircuit(self) -> None:
        """阶段不短路：词法非法 effect_type（阶段 1+2 双报）+ missing entity
        （阶段 4）+ stale（阶段 6）一次性收齐。"""
        state = _make_state(world_revision=8, entity_ids=("ent_a",))
        effect = _make_effect(
            "eff_multi", "Bad.Type", _entity_target("ent_missing"), {}, base_revision=5
        )
        ok, reason = validate_proposed_effect(effect, state)
        assert ok is False
        assert reason is not None
        parts = reason.split("; ")
        assert len(parts) == 4
        expected_bad_id = (
            "bad_id_kind:eff_multi:effect_type:expected=EffectTypeId got=lexErr:value=Bad.Type"
        )
        assert expected_bad_id in parts
        assert "bad_type_id:eff_multi:effect_type='Bad.Type' 不匹配 EffectTypeId 词法" in parts
        assert "missing_entity:eff_multi:target=ent_missing 不存在于 WorldState" in parts
        assert "stale_revision:eff_multi:base=5 current=8" in parts


# —— L1 批级过滤语义（D-P2-10 第一层）——


class TestEffectValidatorBatch:
    """validate_batch：过滤语义 + 批级 duplicated_effect_id（KBC-2 防线）。"""

    def test_filter_semantics_bad_filtered_good_accepted(self) -> None:
        state = _make_state(world_revision=0, entity_ids=("ent_a",))
        good = _set_world_variable("eff_good")
        bad = _make_effect(
            "eff_bad", "core.set_component",
            _entity_target("ent_missing", "space.position"), {"x": 1},
        )
        report = EffectValidator().validate_batch([good, bad], ValidationContext(state=state))
        assert report.accepted == (good,)
        assert [issue.effect_id for issue in report.issues] == ["eff_bad"]
        assert report.ok is False
        assert report.issues_for("eff_bad")
        assert report.issues_for("eff_good") == ()

    def test_all_clean_ok(self) -> None:
        state = _make_state(world_revision=2)
        good1 = _set_world_variable("eff_g1", base_revision=2)
        good2 = _set_world_variable("eff_g2", base_revision=2)
        report = EffectValidator().validate_batch([good1, good2], ValidationContext(state=state))
        assert report.ok is True
        assert report.accepted == (good1, good2)
        assert report.issues == ()

    def test_duplicated_effect_id_all_copies_rejected(self) -> None:
        state = _make_state(world_revision=0)
        effect = _set_world_variable("eff_dup")
        report = EffectValidator().validate_batch([effect, effect], ValidationContext(state=state))
        assert report.accepted == ()
        assert report.ok is False
        assert [issue.to_trace_str() for issue in report.issues] == [
            "duplicated_effect_id:eff_dup:count=2"
        ]

    def test_duplicated_effect_id_count_three(self) -> None:
        state = _make_state(world_revision=0)
        effects = [
            _set_world_variable("eff_t1"),
            _set_world_variable("eff_t1"),
            _set_world_variable("eff_t1"),
        ]
        report = EffectValidator().validate_batch(effects, ValidationContext(state=state))
        assert report.accepted == ()
        assert report.issues[0].detail == "count=3"

    def test_duplicated_issues_in_first_arrival_order(self) -> None:
        """批级问题按 ID 首现（到达）序输出（确定性）。"""
        state = _make_state(world_revision=0)
        effects = [
            _set_world_variable("eff_b"),
            _set_world_variable("eff_a"),
            _set_world_variable("eff_a"),
            _set_world_variable("eff_b"),
        ]
        report = EffectValidator().validate_batch(effects, ValidationContext(state=state))
        assert report.accepted == ()
        assert [issue.effect_id for issue in report.issues] == ["eff_b", "eff_a"]

    def test_duplicated_id_with_stage_issues(self) -> None:
        """重复 ID 与阶段问题并存：两份副本各自 stale + 一条批级重复报告。"""
        state = _make_state(world_revision=8)
        stale1 = _set_world_variable("eff_sd", base_revision=5)
        stale2 = _set_world_variable("eff_sd", base_revision=5)
        report = EffectValidator().validate_batch([stale1, stale2], ValidationContext(state=state))
        assert report.accepted == ()
        kinds = [issue.kind for issue in report.issues]
        assert kinds == ["stale_revision", "stale_revision", "duplicated_effect_id"]

    def test_empty_batch_ok(self) -> None:
        state = _make_state()
        report = EffectValidator().validate_batch([], ValidationContext(state=state))
        assert report.ok is True
        assert report.accepted == ()
        assert report.issues == ()


# —— L2 事务终检 C2 晋升接线（§4.5）——


class TestCheckTransactionReferencesPromoted:
    """C2 义务闭环：core 实现 + 包级 re-export 同一对象 + 形态复检。"""

    def test_reexport_same_object_as_module(self) -> None:
        assert core_pkg.check_transaction_references is check_transaction_references
        assert core_pkg.TRANSACTION_REFERENCE_ISSUE_KINDS is TRANSACTION_REFERENCE_ISSUE_KINDS

    def test_issue_kinds_constant_matches_c7(self) -> None:
        assert TRANSACTION_REFERENCE_ISSUE_KINDS == (
            "missing_entity",
            "stale_revision",
            "duplicated_effect_id",
        )
        assert set(TRANSACTION_REFERENCE_ISSUE_KINDS) <= VALIDATION_ISSUE_KINDS

    def test_l2_missing_entity_string_format(self) -> None:
        state = _make_state(world_revision=5, entity_ids=("ent_a",))
        effect = _make_effect(
            "eff_l2_m", "core.set_component", _entity_target("ent_missing"), {"x": 1},
            base_revision=5,
        )
        issues = check_transaction_references(state, _make_committed_txn(5, [effect]))
        assert issues == ("missing_entity:eff_l2_m:target=ent_missing",)

    def test_l2_aborted_noop(self) -> None:
        state = _make_state(world_revision=5)
        aborted = Transaction(
            transaction_id=new_transaction_id(),
            status=TransactionStatus.ABORTED,
            base_revision=Revision(5),
            abort_reason="validation failed",
        )
        assert check_transaction_references(state, aborted) == ()

    def test_l2_pure_no_mutation(self) -> None:
        state = _make_state(world_revision=813, entity_ids=())
        effect = _make_effect(
            "eff_l2_p", "core.set_component", _entity_target("ent_missing"), {"x": 1},
            base_revision=812,
        )
        txn = _make_committed_txn(812, [effect])
        state_before = state.model_dump(mode="json")
        txn_before = txn.model_dump(mode="json")
        issues = check_transaction_references(state, txn)
        assert issues  # 脏场景确有报告
        assert state.model_dump(mode="json") == state_before
        assert txn.model_dump(mode="json") == txn_before


# —— 任务包组合面：ValidationPipeline / ValidationError ——


class TestValidationPipelineStrict:
    """严格模式：任何问题 → ValidationError（all-or-nothing），零问题 → accepted。"""

    def test_run_returns_accepted_when_clean(self) -> None:
        state = _make_state(world_revision=0)
        good = _set_world_variable("eff_ok")
        pipeline = ValidationPipeline()
        assert pipeline.run([good], ValidationContext(state=state)) == (good,)

    def test_run_raises_on_issues(self) -> None:
        state = _make_state(world_revision=8)
        stale = _set_world_variable("eff_stale", base_revision=5)
        pipeline = ValidationPipeline()
        with pytest.raises(ValidationError) as excinfo:
            pipeline.run([stale], ValidationContext(state=state))
        error = excinfo.value
        assert isinstance(error, ValueError)
        assert [issue.kind for issue in error.issues] == ["stale_revision"]
        assert error.issues[0].effect_id == "eff_stale"

    def test_error_message_contains_trace_strings(self) -> None:
        state = _make_state(world_revision=0)
        bad = _make_effect(
            "eff_msg", "core.set_component", _entity_target("ent_missing"), {"x": 1}
        )
        with pytest.raises(ValidationError) as excinfo:
            ValidationPipeline().run([bad], ValidationContext(state=state))
        message = str(excinfo.value)
        assert message.startswith("validation failed: ")
        assert "missing_entity:eff_msg:target=ent_missing 不存在于 WorldState" in message

    def test_pipeline_is_effect_validator(self) -> None:
        assert isinstance(ValidationPipeline(), EffectValidator)


# —— 词表与包级 re-export（D-P2-19）——


class TestVocabularyAndReexports:
    def test_validation_issue_kinds_exact_vocabulary(self) -> None:
        assert VALIDATION_ISSUE_KINDS == frozenset(
            {
                "bad_id_kind",
                "bad_type_id",
                "bad_payload",
                "bad_field_path",
                "missing_entity",
                "missing_component",
                "stale_revision",
                "future_base_revision",
                "unknown_domain",
                "no_handler",
                "precondition_failed",
                "duplicated_effect_id",
            }
        )

    def test_all_eleven_public_names_reexported_same_object(self) -> None:
        for name in validation_mod.__all__:
            assert getattr(core_pkg, name) is getattr(validation_mod, name), name
        assert set(validation_mod.__all__) == {
            "EffectValidator",
            "TRANSACTION_REFERENCE_ISSUE_KINDS",
            "VALIDATION_ISSUE_KINDS",
            "ValidationError",
            "ValidationContext",
            "ValidationIssue",
            "ValidationPipeline",
            "ValidationReport",
            "check_effect_id_kinds",
            "check_transaction_references",
            "validate_proposed_effect",
        }
