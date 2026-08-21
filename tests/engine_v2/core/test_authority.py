"""P2-T02/T03 验收：authority.py 选择器层、模型结构与求值层（P2 设计规范 §3）。

覆盖（任务包口径）：

1. **各维选择器（5 种目标类型）的匹配规则**——``match_selector``：
   - ``effect_type`` 维：全等 / 不匹配 / 通配；两种 target 种类通用；
   - ``component_type`` 维：全等 / 不匹配 / selector 指定而 effect 未指定 →
     不匹配 / 通配；
   - ``field`` 维：与 ``target.field_path`` 全等 / 不匹配 / selector 指定而
     effect 无字段 → 不匹配 / 通配；
   - ``domain_tag`` 维：EntityTarget 经 registry ``authority_domain`` 判定
     （相等 → 匹配；不等 / 组件未注册 / 无 authority_domain / 无 registry /
     目标无组件 → 不匹配——不可判定 ≠ 默认放行）；StateDomainTarget 与
     ``target.domain`` 直接全等；
   - ``entity_tag`` 维：state 中实体带 tag → 匹配；无 tag / 无 state / 实体
     不存在 → 不匹配；
   - 维度与目标种类不相容（StateDomainTarget + component_type/field/
     entity_tag）→ 不匹配；
   - 空 selector 匹配一切；多维 AND 语义。
2. **AuthorityPolicy 模型校验与 default DENY 特性**——pydantic 契约
   （frozen / extra=forbid / ``model_validate`` 配置入口 / typed ID 类型
   重建 / JSON round-trip / JSON 序列化干净；``allowed_writers`` ≥1 强制；
   ``rule_id`` 可选且非空；``default_decision`` 缺省 DENY——closed-by-default）。
3. **AuthorityDecision 序列化与判断**——str-Enum 词表（``"allow"`` /
   ``"deny"``，对齐 P1 trace decision 词表——T03 废止 T02 首段
   ``"permit"`` 字面量）、值重建、JSON 序列化落字符串、比较判断。
4. **check_authority 求值器（P2-T03）**——
   - 规则排序：priority 降序 → specificity 降序 → 规则声明序（稳定排序）；
   - 首条匹配规则拍板（First-match-wins），不 fall-through；
   - 无匹配 → 严格回落 ``policy.default_decision``（Closed-by-default，
     缺省 DENY）；
   - ``authority_scope`` 仅 advisory 咨询与日志标记，严禁经 prompt
     override 提权（K4 不变量，D-P2-17）；
   - 输入契约守卫（``AuthorityError``）。
5. **AuthorityEvaluationResult 输出结构（P2-T03）**——decision /
   matched_rule_id / matched_rule_description / reason_code /
   evaluated_rules_count + 拍板规则下标/priority/selector + advisory 字段；
   frozen dataclass 纪律；reason_code 冻结词表 ``AUTHORITY_REASON_CODES``。
6. **Trace 协同（P2-T03）**——``to_trace_payload`` 恰为 P1 冻结约定键
   ``DECISION_PAYLOAD_KEYS`` 三键（``effect_id`` / ``decision`` /
   ``reason``）；``decision`` ∈ {allow, deny} 直接落值无映射层；
   ``reason`` = reason_code（规则拍板时附拍板规则下标，P2 设计规范 §9）。
7. **ProducerRegistry（P2 设计规范 §3.4，T03 交付物）**——注册时词法校验
   （``PRODUCER_ID_PATTERN``）/ 同 info 幂等 / 冲突 → ``ProducerConflictError``
   （``ValueError`` 族）/ ``get`` 未注册 None / ``origin_of`` /
   ``priority_of`` 缺省纪律。

全部用例无网络、无 LLM、无 API key（Spec §47 Phase 1 验收）。
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, is_dataclass

import pytest
from pydantic import ValidationError

from src.engine_v2.core.authority import (
    AUTHORITY_REASON_CODES,
    KERNEL_STATE_DOMAINS,
    AuthorityDecision,
    AuthorityEvaluationResult,
    AuthorityError,
    AuthorityPolicy,
    AuthorityRule,
    AuthoritySelector,
    ProducerConflictError,
    ProducerInfo,
    ProducerRegistry,
    check_authority,
    match_selector,
)
from src.engine_v2.core.components import (
    ComponentRegistry,
    ComponentSchema,
    ComponentTypeId,
)
from src.engine_v2.core.effects import (
    EffectTypeId,
    EntityTarget,
    ProposedEffect,
    StateDomainId,
    StateDomainTarget,
)
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.ids import EffectId, EntityId, ProducerId
from src.engine_v2.core.provenance import OriginKind
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.serialization import assert_json_clean
from src.engine_v2.core.state import WorldState
from src.engine_v2.core.trace import DECISION_PAYLOAD_KEYS


# —— 样本工厂（自包含、确定性构造）——


def _entity_effect(
    *,
    effect_id: str = "eff_auth_1",
    effect_type: str = "core.set_component",
    source: str = "rule.lock_system",
    entity_id: str = "ent_auth_a",
    component_type: str | None = "space.position",
    field_path: str | None = None,
    authority_scope: str | None = None,
) -> ProposedEffect:
    """确定性构造 entity 分支的拟议效果（``core.set_component`` 形态）。"""
    return ProposedEffect(
        effect_id=EffectId(effect_id),
        effect_type=EffectTypeId(effect_type),
        source=ProducerId(source),
        target=EntityTarget(
            entity_id=EntityId(entity_id),
            component_type=ComponentTypeId(component_type)
            if component_type is not None
            else None,
            field_path=field_path,
        ),
        payload={},
        base_revision=Revision(0),
        authority_scope=authority_scope,
    )


def _domain_effect(
    *,
    effect_id: str = "eff_auth_2",
    effect_type: str = "core.set_world_variable",
    source: str = "rule.clock",
    domain: str = "world_variables",
) -> ProposedEffect:
    """确定性构造 state domain 分支的拟议效果（``core.set_world_variable`` 形态）。"""
    return ProposedEffect(
        effect_id=EffectId(effect_id),
        effect_type=EffectTypeId(effect_type),
        source=ProducerId(source),
        target=StateDomainTarget(domain=StateDomainId(domain)),
        payload={},
        base_revision=Revision(0),
    )


def _entity_record(entity_id: str, *, tags: list[str] | None = None) -> EntityRecord:
    return EntityRecord(entity_id=EntityId(entity_id), tags=list(tags or []))


def _state_with(
    entity_ids: list[str], tags_by_id: dict[str, list[str]] | None = None
) -> WorldState:
    """构造只含指定实体（及 tag）的最小 WorldState。"""
    tags_by_id = tags_by_id or {}
    return WorldState(
        world_revision=Revision(1),
        entities={
            EntityId(eid): _entity_record(eid, tags=tags_by_id.get(eid, []))
            for eid in entity_ids
        },
    )


def _registry_with_domain(component_type: str, domain: str | None) -> ComponentRegistry:
    """构造只注册一个组件 schema（带或不带 authority_domain）的 registry。"""
    registry = ComponentRegistry()
    registry.register(
        ComponentSchema(
            component_type=ComponentTypeId(component_type),
            authority_domain=StateDomainId(domain) if domain is not None else None,
        )
    )
    return registry


def _rule(
    selector: AuthoritySelector,
    writers: list[str],
    *,
    priority: int = 0,
    description: str = "",
    rule_id: str | None = None,
) -> AuthorityRule:
    """构造 authority 规则的确定性工厂（writers 取字符串名单）。"""
    return AuthorityRule(
        selector=selector,
        allowed_writers=[ProducerId(w) for w in writers],
        priority=priority,
        description=description,
        rule_id=rule_id,
    )


# —— 0. 内置状态域常量（P2 设计规范 §3.6）——


class TestKernelStateDomains:
    def test_builtin_domains_match_worldstate_fields(self):
        assert KERNEL_STATE_DOMAINS == frozenset({"world_variables", "scenario"})
        assert all(type(d) is StateDomainId for d in KERNEL_STATE_DOMAINS)


# —— 1. 各维选择器（5 种目标类型）的匹配规则 ——


class TestSelectorEffectTypeDimension:
    """effect_type 维：全等匹配（不做前缀/层级匹配），两种 target 通用。"""

    def test_exact_match(self):
        selector = AuthoritySelector(effect_type=EffectTypeId("core.set_component"))
        assert match_selector(selector, _entity_effect()) is True

    def test_mismatch_no_match(self):
        selector = AuthoritySelector(effect_type=EffectTypeId("core.remove_component"))
        assert match_selector(selector, _entity_effect()) is False

    def test_wildcard_when_unspecified(self):
        assert match_selector(AuthoritySelector(), _entity_effect()) is True

    def test_applies_to_state_domain_target_too(self):
        selector = AuthoritySelector(effect_type=EffectTypeId("core.set_world_variable"))
        assert match_selector(selector, _domain_effect()) is True
        selector = AuthoritySelector(effect_type=EffectTypeId("core.set_component"))
        assert match_selector(selector, _domain_effect()) is False


class TestSelectorComponentTypeDimension:
    """component_type 维：全等；selector 指定而 effect 未指定 → 不匹配。"""

    def test_exact_match(self):
        selector = AuthoritySelector(component_type=ComponentTypeId("space.position"))
        assert match_selector(selector, _entity_effect()) is True

    def test_mismatch_no_match(self):
        selector = AuthoritySelector(component_type=ComponentTypeId("knowledge.belief"))
        assert match_selector(selector, _entity_effect()) is False

    def test_selector_specified_effect_unspecified_no_match(self):
        selector = AuthoritySelector(component_type=ComponentTypeId("space.position"))
        effect = _entity_effect(component_type=None)
        assert match_selector(selector, effect) is False

    def test_wildcard_when_unspecified(self):
        assert match_selector(AuthoritySelector(), _entity_effect(component_type=None)) is True


class TestSelectorFieldDimension:
    """field 维：与 target.field_path 全等；selector 指定而 effect 无字段 → 不匹配。"""

    def test_exact_match_against_field_path(self):
        selector = AuthoritySelector(field="x")
        assert match_selector(selector, _entity_effect(field_path="x")) is True

    def test_mismatch_no_match(self):
        selector = AuthoritySelector(field="x")
        assert match_selector(selector, _entity_effect(field_path="y")) is False

    def test_selector_specified_effect_without_field_no_match(self):
        selector = AuthoritySelector(field="x")
        assert match_selector(selector, _entity_effect(field_path=None)) is False

    def test_wildcard_when_unspecified(self):
        assert match_selector(AuthoritySelector(), _entity_effect(field_path="x")) is True


class TestSelectorDomainTagDimension:
    """domain_tag 维：EntityTarget 经 registry authority_domain 判定；
    StateDomainTarget 与 target.domain 直接全等；不可判定 → 不匹配。"""

    def test_entity_target_registry_domain_match(self):
        selector = AuthoritySelector(domain_tag=StateDomainId("location"))
        registry = _registry_with_domain("space.position", "location")
        assert match_selector(selector, _entity_effect(), component_registry=registry) is True

    def test_entity_target_domain_mismatch(self):
        selector = AuthoritySelector(domain_tag=StateDomainId("location"))
        registry = _registry_with_domain("space.position", "inventory")
        assert match_selector(selector, _entity_effect(), component_registry=registry) is False

    def test_entity_target_component_unregistered_no_match(self):
        selector = AuthoritySelector(domain_tag=StateDomainId("location"))
        registry = ComponentRegistry()  # 未注册任何组件
        assert match_selector(selector, _entity_effect(), component_registry=registry) is False

    def test_entity_target_schema_without_domain_no_match(self):
        selector = AuthoritySelector(domain_tag=StateDomainId("location"))
        registry = _registry_with_domain("space.position", None)
        assert match_selector(selector, _entity_effect(), component_registry=registry) is False

    def test_entity_target_without_registry_no_match(self):
        selector = AuthoritySelector(domain_tag=StateDomainId("location"))
        assert match_selector(selector, _entity_effect(), component_registry=None) is False

    def test_entity_target_entity_level_effect_no_match(self):
        # 目标无 component_type（core.create_entity 等实体级效果）→ 域不可判定
        selector = AuthoritySelector(domain_tag=StateDomainId("location"))
        registry = _registry_with_domain("space.position", "location")
        effect = _entity_effect(component_type=None)
        assert match_selector(selector, effect, component_registry=registry) is False

    def test_state_domain_target_domain_match(self):
        selector = AuthoritySelector(domain_tag=StateDomainId("world_variables"))
        assert match_selector(selector, _domain_effect()) is True

    def test_state_domain_target_domain_mismatch(self):
        selector = AuthoritySelector(domain_tag=StateDomainId("scenario"))
        assert match_selector(selector, _domain_effect()) is False

    def test_state_domain_target_wildcard(self):
        assert match_selector(AuthoritySelector(), _domain_effect()) is True


class TestSelectorEntityTagDimension:
    """entity_tag 维：需要 state 的实体记录；实体维度不可判定即不放行。"""

    def test_tag_present_in_state(self):
        selector = AuthoritySelector(entity_tag="merchant")
        state = _state_with(["ent_auth_a"], tags_by_id={"ent_auth_a": ["merchant", "npc"]})
        assert match_selector(selector, _entity_effect(), state=state) is True

    def test_tag_absent(self):
        selector = AuthoritySelector(entity_tag="merchant")
        state = _state_with(["ent_auth_a"], tags_by_id={"ent_auth_a": ["npc"]})
        assert match_selector(selector, _entity_effect(), state=state) is False

    def test_state_missing_no_match(self):
        selector = AuthoritySelector(entity_tag="merchant")
        assert match_selector(selector, _entity_effect(), state=None) is False

    def test_entity_not_in_state_no_match(self):
        selector = AuthoritySelector(entity_tag="merchant")
        state = _state_with(["ent_other"])
        assert match_selector(selector, _entity_effect(), state=state) is False

    def test_wildcard_when_unspecified(self):
        assert match_selector(AuthoritySelector(), _entity_effect(), state=None) is True


class TestSelectorTargetKindCompatAndCombo:
    """维度/目标种类不相容、空 selector 全匹配、多维 AND 语义。"""

    def test_incompatible_dimensions_on_state_domain_target(self):
        effect = _domain_effect()
        for selector in (
            AuthoritySelector(component_type=ComponentTypeId("space.position")),
            AuthoritySelector(field="x"),
            AuthoritySelector(entity_tag="merchant"),
        ):
            assert match_selector(selector, effect) is False, (
                f"component_type/field/entity_tag 维与 StateDomainTarget 不相容：{selector}"
            )

    def test_incompatible_dimensions_rejected_even_when_domain_matches(self):
        selector = AuthoritySelector(
            domain_tag=StateDomainId("world_variables"),
            component_type=ComponentTypeId("space.position"),
        )
        assert match_selector(selector, _domain_effect()) is False

    def test_empty_selector_matches_everything(self):
        selector = AuthoritySelector()
        assert match_selector(selector, _entity_effect()) is True
        assert match_selector(selector, _domain_effect()) is True

    def test_multi_dimension_all_hit(self):
        selector = AuthoritySelector(
            component_type=ComponentTypeId("space.position"),
            field="x",
            effect_type=EffectTypeId("core.set_component"),
            entity_tag="merchant",
        )
        state = _state_with(["ent_auth_a"], tags_by_id={"ent_auth_a": ["merchant"]})
        registry = _registry_with_domain("space.position", "location")
        effect = _entity_effect(field_path="x")
        assert match_selector(selector, effect, state=state, component_registry=registry) is True

    def test_multi_dimension_one_miss(self):
        selector = AuthoritySelector(
            component_type=ComponentTypeId("space.position"),
            field="x",
            entity_tag="merchant",
        )
        state = _state_with(["ent_auth_a"], tags_by_id={"ent_auth_a": ["npc"]})  # entity_tag 漏
        effect = _entity_effect(field_path="x")
        assert match_selector(selector, effect, state=state) is False


class TestSelectorSpecificity:
    """specificity()：指定维度计数（求值序 tiebreak 输入）。"""

    def test_specificity_counts_specified_dimensions(self):
        assert AuthoritySelector().specificity() == 0
        assert (
            AuthoritySelector(effect_type=EffectTypeId("core.set_component")).specificity()
            == 1
        )
        full = AuthoritySelector(
            component_type=ComponentTypeId("space.position"),
            field="x",
            domain_tag=StateDomainId("location"),
            effect_type=EffectTypeId("core.set_component"),
            entity_tag="merchant",
        )
        assert full.specificity() == 5


# —— 2. AuthorityDecision：序列化与判断（allow/deny 词表，P1 trace 对齐）——


class TestAuthorityDecision:
    def test_values_are_string_literals(self):
        assert AuthorityDecision.ALLOW.value == "allow"
        assert AuthorityDecision.DENY.value == "deny"
        assert set(AuthorityDecision) == {AuthorityDecision.ALLOW, AuthorityDecision.DENY}

    def test_is_str_enum(self):
        assert isinstance(AuthorityDecision.ALLOW, str)
        assert isinstance(AuthorityDecision.DENY, str)

    def test_value_reconstruction(self):
        assert AuthorityDecision("allow") is AuthorityDecision.ALLOW
        assert AuthorityDecision("deny") is AuthorityDecision.DENY
        with pytest.raises(ValueError):
            AuthorityDecision("permit")  # T02 首段词表已废止（T03 对齐 P1 allow/deny）
        with pytest.raises(ValueError):
            AuthorityDecision("maybe")

    def test_serialization_as_json_string(self):
        # 作为契约字段序列化：mode="json" 落字符串字面量，JSON 可编码
        policy = AuthorityPolicy(default_decision=AuthorityDecision.ALLOW)
        dump = policy.model_dump(mode="json")
        assert dump["default_decision"] == "allow"
        assert json.loads(json.dumps(dump))["default_decision"] == "allow"

    def test_judgment_comparisons(self):
        result = check_authority(_entity_effect(), AuthorityPolicy())
        assert result.decision is AuthorityDecision.DENY
        assert result.decision == "deny"  # str-Enum 与裸字符串值比较相等
        assert result.decision in (AuthorityDecision.ALLOW, AuthorityDecision.DENY)


# —— 3. AuthorityRule / AuthorityPolicy：模型校验与 default DENY ——


class TestAuthorityRuleModel:
    def test_defaults(self):
        rule = AuthorityRule(
            selector=AuthoritySelector(), allowed_writers=[ProducerId("rule.lock_system")]
        )
        assert rule.priority == 0
        assert rule.description == ""
        assert rule.rule_id is None

    def test_empty_allowed_writers_rejected(self):
        # closed-by-default：无 writer 的规则无意义（model_validator 强制 ≥1）
        with pytest.raises(ValidationError):
            AuthorityRule(selector=AuthoritySelector(), allowed_writers=[])

    def test_writers_reconstructed_to_producer_id(self):
        rule = AuthorityRule.model_validate(
            {"selector": {}, "allowed_writers": ["policy.alice", "dev.console"]}
        )
        assert all(type(w) is ProducerId for w in rule.allowed_writers)

    def test_selector_reconstructed_from_nested_dict(self):
        rule = AuthorityRule.model_validate(
            {
                "selector": {
                    "component_type": "space.position",
                    "domain_tag": "location",
                    "effect_type": "core.set_component",
                },
                "allowed_writers": ["rule.lock_system"],
            }
        )
        assert type(rule.selector.component_type) is ComponentTypeId
        assert type(rule.selector.domain_tag) is StateDomainId
        assert type(rule.selector.effect_type) is EffectTypeId
        assert rule.selector.field is None
        assert rule.selector.entity_tag is None

    def test_rule_id_optional(self):
        rule = _rule(
            AuthoritySelector(), ["rule.lock_system"], rule_id="door.lock.write"
        )
        assert rule.rule_id == "door.lock.write"

    def test_rule_id_empty_string_rejected(self):
        with pytest.raises(ValidationError):
            _rule(AuthoritySelector(), ["rule.lock_system"], rule_id="")

    def test_rule_id_json_roundtrip(self):
        policy = AuthorityPolicy.model_validate(
            {
                "rules": [
                    {
                        "selector": {},
                        "allowed_writers": ["rule.lock_system"],
                        "rule_id": "r1",
                        "description": "门闩写入",
                    }
                ]
            }
        )
        clone = AuthorityPolicy.model_validate(policy.model_dump(mode="json"))
        assert clone == policy
        assert clone.rules[0].rule_id == "r1"

    def test_frozen(self):
        rule = AuthorityRule(
            selector=AuthoritySelector(), allowed_writers=[ProducerId("rule.lock_system")]
        )
        with pytest.raises(ValidationError):
            rule.priority = 99  # type: ignore[misc]

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            AuthorityRule.model_validate(
                {
                    "selector": {},
                    "allowed_writers": ["rule.lock_system"],
                    "unknown": 1,
                }
            )


class TestAuthorityPolicyModel:
    def test_defaults_closed_by_default(self):
        # default DENY 特性：缺省策略完全封闭（空规则 + default_decision=DENY）
        policy = AuthorityPolicy()
        assert policy.rules == []
        assert policy.default_decision is AuthorityDecision.DENY

    def test_model_validate_from_dict(self):
        policy = AuthorityPolicy.model_validate(
            {
                "rules": [
                    {
                        "selector": {"effect_type": "core.set_component"},
                        "allowed_writers": ["rule.lock_system"],
                        "priority": 5,
                        "description": "门闩状态写入",
                    }
                ],
                "default_decision": "deny",
            }
        )
        assert len(policy.rules) == 1
        rule = policy.rules[0]
        assert rule.priority == 5
        assert rule.description == "门闩状态写入"
        assert policy.default_decision is AuthorityDecision.DENY

    def test_roundtrip(self):
        policy = AuthorityPolicy.model_validate(
            {
                "rules": [
                    {
                        "selector": {
                            "component_type": "space.position",
                            "entity_tag": "merchant",
                        },
                        "allowed_writers": ["rule.lock_system"],
                    }
                ],
                "default_decision": "allow",
            }
        )
        clone = AuthorityPolicy.model_validate(policy.model_dump(mode="json"))
        assert clone == policy
        assert clone.default_decision is AuthorityDecision.ALLOW
        assert type(clone.rules[0].selector.component_type) is ComponentTypeId

    def test_json_dump_is_clean(self):
        policy = AuthorityPolicy.model_validate(
            {
                "rules": [
                    {
                        "selector": {"field": "x"},
                        "allowed_writers": ["dynamics.rigid_body"],
                    }
                ]
            }
        )
        dump = policy.model_dump(mode="json")
        assert_json_clean(dump)
        assert dump["default_decision"] == "deny"
        assert dump["rules"][0]["allowed_writers"] == ["dynamics.rigid_body"]
        assert dump["rules"][0]["rule_id"] is None

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            AuthorityPolicy.model_validate({"rules": [], "unknown": 1})

    def test_invalid_default_decision_rejected(self):
        with pytest.raises(ValidationError):
            AuthorityPolicy.model_validate({"default_decision": "maybe"})

    def test_legacy_permit_default_rejected(self):
        # T02 首段词表 "permit" 已废止：词表对齐 P1 trace 的 allow/deny（P2-T03）
        with pytest.raises(ValidationError):
            AuthorityPolicy.model_validate({"default_decision": "permit"})


# —— 4. reason_code 冻结词表（P2 设计规范 §3.5）——


class TestAuthorityReasonCodes:
    def test_frozen_vocabulary(self):
        assert AUTHORITY_REASON_CODES == ("rule_allow", "rule_deny", "no_matching_rule")
        assert len(AUTHORITY_REASON_CODES) == len(set(AUTHORITY_REASON_CODES))


# —— 5. check_authority 求值器（P2-T03：首条拍板 / 不 fall-through / 默认回落）——


class TestCheckAuthorityEvaluator:
    """求值层核心口径：确定性求值序 + First-match-wins + closed-by-default 回落。"""

    def test_no_matching_rule_falls_back_to_default_deny(self):
        result = check_authority(_entity_effect(), AuthorityPolicy())
        assert result.decision is AuthorityDecision.DENY
        assert result.reason_code == "no_matching_rule"
        # 无拍板规则：全部解释字段为 None
        assert result.matched_rule_id is None
        assert result.matched_rule_description is None
        assert result.matched_rule_index is None
        assert result.rule_priority is None
        assert result.selector is None
        # 空策略：遍历 0 条规则
        assert result.evaluated_rules_count == 0

    def test_no_matching_rule_uses_configured_default(self):
        # 显式配置的 default_decision=ALLOW 生效（policy 侧显式声明，非 K4 提权）
        policy = AuthorityPolicy(
            default_decision=AuthorityDecision.ALLOW,
            rules=[_rule(AuthoritySelector(effect_type=EffectTypeId("core.remove_component")), ["rule.x"])],
        )
        result = check_authority(_domain_effect(), policy)
        assert result.decision is AuthorityDecision.ALLOW
        assert result.reason_code == "no_matching_rule"
        # 无匹配：全部规则被遍历（1 条）
        assert result.evaluated_rules_count == 1
        assert result.matched_rule_index is None

    def test_matched_rule_grants_to_allowed_writer(self):
        policy = AuthorityPolicy(
            rules=[
                _rule(
                    AuthoritySelector(effect_type=EffectTypeId("core.set_component")),
                    ["rule.lock_system"],
                    priority=3,
                    description="门闩状态写入",
                    rule_id="door.lock.write",
                )
            ]
        )
        effect = _entity_effect()
        result = check_authority(effect, policy)
        assert result.decision is AuthorityDecision.ALLOW
        assert result.reason_code == "rule_allow"
        assert result.effect_id == effect.effect_id
        assert result.producer == effect.source
        assert result.matched_rule_id == "door.lock.write"
        assert result.matched_rule_description == "门闩状态写入"
        assert result.matched_rule_index == 0
        assert result.rule_priority == 3
        assert result.selector == AuthoritySelector(
            effect_type=EffectTypeId("core.set_component")
        )
        # 首条命中即拍板：只遍历了 1 条规则
        assert result.evaluated_rules_count == 1
        # effect 未携带 authority_scope → advisory 字段为 None
        assert result.authority_scope is None

    def test_matched_rule_denies_unlisted_writer_no_fallthrough(self):
        # 首条命中规则拍板 deny → 后续更宽泛的允许规则不被参考（不 fall-through）
        policy = AuthorityPolicy(
            rules=[
                _rule(
                    AuthoritySelector(effect_type=EffectTypeId("core.set_component")),
                    ["rule.lock_system"],
                    rule_id="r-specific",
                ),
                _rule(AuthoritySelector(), ["policy.alice"], rule_id="r-wildcard"),
            ]
        )
        result = check_authority(_entity_effect(source="policy.alice"), policy)
        assert result.decision is AuthorityDecision.DENY
        assert result.reason_code == "rule_deny"
        # 拍板者是第一条命中规则（具体规则），通配规则未被求值
        assert result.matched_rule_id == "r-specific"
        assert result.evaluated_rules_count == 1

    def test_higher_priority_rule_evaluated_first(self):
        policy = AuthorityPolicy(
            rules=[
                _rule(AuthoritySelector(), ["policy.alice"], rule_id="r-low"),
                _rule(AuthoritySelector(), ["rule.lock_system"], priority=10, rule_id="r-high"),
            ]
        )
        # 高 priority 规则先求值：producer 在其 writers 内 → ALLOW
        result = check_authority(_entity_effect(source="rule.lock_system"), policy)
        assert result.decision is AuthorityDecision.ALLOW
        assert result.reason_code == "rule_allow"
        # 排序后高 priority 规则占据求值序第 0 位
        assert result.matched_rule_id == "r-high"
        assert result.matched_rule_index == 0
        assert result.rule_priority == 10

    def test_specificity_breaks_priority_tie(self):
        policy = AuthorityPolicy(
            rules=[
                _rule(AuthoritySelector(), ["policy.alice"], rule_id="r-broad"),
                _rule(
                    AuthoritySelector(effect_type=EffectTypeId("core.set_component")),
                    ["rule.lock_system"],
                    rule_id="r-specific",
                ),
            ]
        )
        # priority 同分：更具体的规则先求值 → alice 不在其 writers → DENY（不回落）
        result = check_authority(_entity_effect(source="policy.alice"), policy)
        assert result.decision is AuthorityDecision.DENY
        assert result.reason_code == "rule_deny"
        assert result.matched_rule_id == "r-specific"

    def test_registration_order_breaks_full_tie(self):
        policy = AuthorityPolicy(
            rules=[
                _rule(
                    AuthoritySelector(effect_type=EffectTypeId("core.set_component")),
                    ["policy.alice"],
                    rule_id="r-first",
                ),
                _rule(
                    AuthoritySelector(effect_type=EffectTypeId("core.set_component")),
                    ["rule.lock_system"],
                    rule_id="r-second",
                ),
            ]
        )
        # priority 与 specificity 全同 → 注册序在先者拍板
        result = check_authority(_entity_effect(source="rule.lock_system"), policy)
        assert result.decision is AuthorityDecision.DENY
        assert result.reason_code == "rule_deny"
        assert result.matched_rule_id == "r-first"
        assert result.matched_rule_index == 0

    def test_evaluated_rules_count_counts_rules_before_decision(self):
        # 前三条规则均不命中，第四条拍板 → 实际遍历 4 条
        policy = AuthorityPolicy(
            rules=[
                _rule(AuthoritySelector(effect_type=EffectTypeId("core.remove_entity")), ["a.b"], rule_id="r1"),
                _rule(AuthoritySelector(component_type=ComponentTypeId("knowledge.belief")), ["c.d"], rule_id="r2"),
                _rule(AuthoritySelector(domain_tag=StateDomainId("location")), ["e.f"], rule_id="r3"),
                _rule(AuthoritySelector(effect_type=EffectTypeId("core.set_component")), ["rule.lock_system"], rule_id="r4"),
            ]
        )
        result = check_authority(_entity_effect(), policy)
        assert result.matched_rule_id == "r4"
        assert result.matched_rule_index == 3
        assert result.evaluated_rules_count == 4

    def test_state_and_registry_flow_into_matching(self):
        policy = AuthorityPolicy(
            rules=[_rule(AuthoritySelector(entity_tag="merchant"), ["policy.alice"])]
        )
        state = _state_with(["ent_auth_a"], tags_by_id={"ent_auth_a": ["merchant"]})
        effect = _entity_effect(source="policy.alice")
        assert check_authority(effect, policy, state=state).decision is AuthorityDecision.ALLOW
        # 无 state → entity_tag 维不可判定 → 无匹配 → default DENY
        result = check_authority(effect, policy, state=None)
        assert result.decision is AuthorityDecision.DENY
        assert result.reason_code == "no_matching_rule"
        assert result.evaluated_rules_count == 1

    def test_authority_scope_declaration_does_not_grant(self):
        # D-P2-17 / K4：authority_scope 声明不提升权限（prompt override 无效）
        policy = AuthorityPolicy(
            rules=[
                _rule(
                    AuthoritySelector(effect_type=EffectTypeId("core.set_component")),
                    ["rule.lock_system"],
                )
            ]
        )
        effect = _entity_effect(source="llm.narrator", authority_scope="space.position")
        result = check_authority(effect, policy)
        assert result.decision is AuthorityDecision.DENY
        assert result.reason_code == "rule_deny"
        # advisory 字段仅原样透传供审计/日志标记——不影响判定
        assert result.authority_scope == "space.position"
        # 无匹配规则路径同样不受伪造声明影响
        blank = check_authority(effect, AuthorityPolicy())
        assert blank.decision is AuthorityDecision.DENY
        assert blank.reason_code == "no_matching_rule"
        assert blank.authority_scope == "space.position"

    def test_result_is_deterministic(self):
        policy = AuthorityPolicy(
            rules=[
                _rule(AuthoritySelector(), ["policy.alice"], rule_id="r1"),
                _rule(
                    AuthoritySelector(effect_type=EffectTypeId("core.set_component")),
                    ["rule.lock_system"],
                    rule_id="r2",
                ),
            ]
        )
        assert check_authority(_entity_effect(), policy) == check_authority(
            _entity_effect(), policy
        )

    def test_non_policy_input_raises_authority_error(self):
        with pytest.raises(AuthorityError):
            check_authority(_entity_effect(), "not-a-policy")  # type: ignore[arg-type]

    def test_non_effect_input_raises_authority_error(self):
        with pytest.raises(AuthorityError):
            check_authority("not-an-effect", AuthorityPolicy())  # type: ignore[arg-type]

    def test_authority_error_is_value_error(self):
        assert issubclass(AuthorityError, ValueError)


# —— 6. AuthorityEvaluationResult：输出结构与 frozen 纪律 ——


class TestAuthorityEvaluationResult:
    def test_is_frozen_dataclass(self):
        result = check_authority(_entity_effect(), AuthorityPolicy())
        assert isinstance(result, AuthorityEvaluationResult)
        assert is_dataclass(result)
        with pytest.raises(FrozenInstanceError):
            result.decision = AuthorityDecision.ALLOW  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            result.evaluated_rules_count = 99  # type: ignore[misc]

    def test_unmatched_fields_default_to_none(self):
        result = check_authority(_entity_effect(), AuthorityPolicy())
        assert result.matched_rule_id is None
        assert result.matched_rule_description is None
        assert result.matched_rule_index is None
        assert result.rule_priority is None
        assert result.selector is None
        assert result.authority_scope is None

    def test_empty_description_normalized_to_none(self):
        policy = AuthorityPolicy(
            rules=[_rule(AuthoritySelector(), ["rule.lock_system"], description="")]
        )
        result = check_authority(_entity_effect(), policy)
        assert result.decision is AuthorityDecision.ALLOW
        assert result.matched_rule_description is None
        # rule_id 缺省 → None（以 matched_rule_index 定位拍板规则）
        assert result.matched_rule_id is None
        assert result.matched_rule_index == 0


# —— 7. Trace 协同：to_trace_payload（P2 设计规范 §9 / P1 DECISION_PAYLOAD_KEYS）——


class TestAuthorityTracePayload:
    """to_trace_payload 恰为 authority_decision 的 P1 冻结约定键形态。"""

    def test_payload_keys_exactly_decision_payload_keys(self):
        policy = AuthorityPolicy(rules=[_rule(AuthoritySelector(), ["rule.lock_system"])])
        result = check_authority(_entity_effect(), policy)
        payload = result.to_trace_payload()
        assert set(payload) == set(DECISION_PAYLOAD_KEYS)
        assert set(payload) == {"effect_id", "decision", "reason"}

    def test_allow_payload_values(self):
        policy = AuthorityPolicy(
            rules=[
                _rule(
                    AuthoritySelector(effect_type=EffectTypeId("core.set_component")),
                    ["rule.lock_system"],
                    rule_id="door.lock.write",
                )
            ]
        )
        payload = check_authority(_entity_effect(), policy).to_trace_payload()
        assert payload["effect_id"] == "eff_auth_1"
        assert payload["decision"] == "allow"
        # reason = reason_code[+rule index]（P2 设计规范 §9）
        assert payload["reason"] == "rule_allow[rule#0]"

    def test_deny_payload_reason_carries_rule_index(self):
        policy = AuthorityPolicy(
            rules=[
                _rule(
                    AuthoritySelector(effect_type=EffectTypeId("core.remove_component")),
                    ["rule.lock_system"],
                    rule_id="r0",
                ),
                _rule(
                    AuthoritySelector(effect_type=EffectTypeId("core.set_component")),
                    ["rule.lock_system"],
                    rule_id="r1",
                ),
            ]
        )
        # 同 priority/specificity → 注册序：r0 先求值（effect_type 不命中），
        # r1 在求值序下标 1 拍板 deny → reason 附 [rule#1]
        result = check_authority(_entity_effect(source="policy.alice"), policy)
        assert result.matched_rule_id == "r1"
        assert result.matched_rule_index == 1
        assert result.evaluated_rules_count == 2
        payload = result.to_trace_payload()
        assert payload["effect_id"] == "eff_auth_1"
        assert payload["decision"] == "deny"
        assert payload["reason"] == "rule_deny[rule#1]"

    def test_no_matching_rule_reason_bare(self):
        # 无规则拍板：reason 不带下标后缀
        result = check_authority(_entity_effect(), AuthorityPolicy())
        payload = result.to_trace_payload()
        assert payload["effect_id"] == "eff_auth_1"
        assert payload["decision"] == "deny"
        assert payload["reason"] == "no_matching_rule"
        assert "[rule#" not in payload["reason"]

    def test_payload_is_json_serializable_and_values_plain_strings(self):
        policy = AuthorityPolicy(
            rules=[_rule(AuthoritySelector(), ["rule.lock_system"]), _rule(
                AuthoritySelector(effect_type=EffectTypeId("core.set_world_variable")),
                ["rule.clock"],
            )]
        )
        for effect in (_entity_effect(), _domain_effect()):
            payload = check_authority(effect, policy).to_trace_payload()
            assert all(type(v) is str for v in payload.values())
            json.loads(json.dumps(payload))  # JSON 可编码（P1 §0.2 铁律 2 口径）

    def test_decision_vocabulary_matches_trace_decision_vocabulary(self):
        # decision 值 ∈ P1 trace 词表 {allow, deny}——直接落值、无映射层
        policy = AuthorityPolicy(
            rules=[_rule(AuthoritySelector(), ["rule.lock_system"]), _rule(
                AuthoritySelector(effect_type=EffectTypeId("core.remove_entity")),
                ["nobody.here"],
            )]
        )
        decisions = {
            check_authority(effect, policy).to_trace_payload()["decision"]
            for effect in (_entity_effect(), _domain_effect())
        }
        assert decisions == {"allow", "deny"}

    def test_authority_scope_not_in_trace_payload(self):
        # D-P2-17：advisory 字段仅随 proposed_effect 记录入档，不入 decision payload
        effect = _entity_effect(authority_scope="space.position")
        payload = check_authority(effect, AuthorityPolicy()).to_trace_payload()
        assert "authority_scope" not in payload
        assert set(payload) == set(DECISION_PAYLOAD_KEYS)


# —— 8. ProducerRegistry（P2 设计规范 §3.4；T03 交付物）——


class TestProducerInfo:
    def test_defaults(self):
        info = ProducerInfo(
            producer_id=ProducerId("policy.alice"), origin=OriginKind.BEHAVIOR_POLICY
        )
        assert info.priority == 0
        assert info.description == ""

    def test_is_frozen_dataclass(self):
        info = ProducerInfo(producer_id=ProducerId("policy.alice"), origin=OriginKind.RULE)
        assert is_dataclass(info)
        with pytest.raises(FrozenInstanceError):
            info.priority = 5  # type: ignore[misc]


class TestProducerRegistry:
    def test_register_and_get(self):
        registry = ProducerRegistry()
        info = ProducerInfo(
            producer_id=ProducerId("rule.lock_system"),
            origin=OriginKind.RULE,
            priority=3,
            description="门锁规则",
        )
        registry.register(info)
        assert registry.get(ProducerId("rule.lock_system")) is info
        # 未注册 ≠ 错误：返回 None
        assert registry.get(ProducerId("policy.alice")) is None

    def test_idempotent_duplicate_registration(self):
        registry = ProducerRegistry()
        info = ProducerInfo(producer_id=ProducerId("rule.lock_system"), origin=OriginKind.RULE)
        registry.register(info)
        registry.register(
            ProducerInfo(producer_id=ProducerId("rule.lock_system"), origin=OriginKind.RULE)
        )
        assert registry.get(ProducerId("rule.lock_system")) is info

    def test_conflicting_reregistration_raises(self):
        registry = ProducerRegistry()
        registry.register(
            ProducerInfo(producer_id=ProducerId("rule.lock_system"), origin=OriginKind.RULE)
        )
        with pytest.raises(ProducerConflictError):
            registry.register(
                ProducerInfo(
                    producer_id=ProducerId("rule.lock_system"),
                    origin=OriginKind.DEVELOPER,
                    priority=5,
                )
            )
        # 冲突不影响原注册
        assert registry.get(ProducerId("rule.lock_system")).origin is OriginKind.RULE

    def test_producer_conflict_error_hierarchy(self):
        assert issubclass(ProducerConflictError, AuthorityError)
        assert issubclass(ProducerConflictError, ValueError)

    def test_bad_producer_id_lexicon_rejected(self):
        # _TypedId 构造不校验词法 → 注册侧复检（P2 设计规范 §3.4 / 纵深防御）
        registry = ProducerRegistry()
        with pytest.raises(AuthorityError):
            registry.register(
                ProducerInfo(producer_id=ProducerId("BAD-UPPER"), origin=OriginKind.SYSTEM)
            )
        with pytest.raises(AuthorityError):
            registry.register(
                ProducerInfo(producer_id=ProducerId("a..b"), origin=OriginKind.SYSTEM)
            )
        # 词法非法的 producer 未进入注册表
        assert registry.get(ProducerId("BAD-UPPER")) is None

    def test_register_non_info_raises(self):
        registry = ProducerRegistry()
        with pytest.raises(AuthorityError):
            registry.register("not-a-producer-info")  # type: ignore[arg-type]

    def test_origin_of_registered_and_default(self):
        registry = ProducerRegistry()
        registry.register(
            ProducerInfo(producer_id=ProducerId("dev.console"), origin=OriginKind.DEVELOPER)
        )
        assert registry.origin_of(ProducerId("dev.console")) is OriginKind.DEVELOPER
        # 未注册 → 缺省 SYSTEM（设计文档 §3.4 签名口径）
        assert registry.origin_of(ProducerId("unknown.prod")) is OriginKind.SYSTEM
        assert registry.origin_of(ProducerId("unknown.prod"), default=OriginKind.RULE) is (
            OriginKind.RULE
        )

    def test_priority_of_registered_and_default(self):
        registry = ProducerRegistry()
        registry.register(
            ProducerInfo(
                producer_id=ProducerId("dynamics.rigid_body"),
                origin=OriginKind.DYNAMICS_BACKEND,
                priority=7,
            )
        )
        assert registry.priority_of(ProducerId("dynamics.rigid_body")) == 7
        assert registry.priority_of(ProducerId("unknown.prod")) == 0
        assert registry.priority_of(ProducerId("unknown.prod"), default=9) == 9
