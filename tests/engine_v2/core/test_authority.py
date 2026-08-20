"""P2-T02 验收：authority.py 选择器层与模型结构（P2 设计规范 §3）。

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
   ``default_decision`` 缺省 DENY——closed-by-default）。
3. **AuthorityDecision 序列化与判断**——str-Enum 词表（``"permit"`` /
   ``"deny"``）、值重建、JSON 序列化落字符串、比较判断。

另覆盖 ``KERNEL_STATE_DOMAINS`` 常量、selector ``specificity()`` 计数，以及
**预留求值接口** ``check_authority`` 的首段实现基础口径（首条命中拍板 /
不 fall-through / default 回落 / priority → specificity → 注册序 /
``authority_scope`` 声明不提升权限 / 输入契约守卫）——求值器的完整口径
（reason code、trace 协同）属 P2-T03。

全部用例无网络、无 LLM、无 API key（Spec §47 Phase 1 验收）。
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.engine_v2.core.authority import (
    KERNEL_STATE_DOMAINS,
    AuthorityDecision,
    AuthorityError,
    AuthorityPolicy,
    AuthorityRule,
    AuthoritySelector,
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
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.serialization import assert_json_clean
from src.engine_v2.core.state import WorldState


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


# —— 2. AuthorityDecision：序列化与判断 ——


class TestAuthorityDecision:
    def test_values_are_string_literals(self):
        assert AuthorityDecision.PERMIT.value == "permit"
        assert AuthorityDecision.DENY.value == "deny"
        assert set(AuthorityDecision) == {AuthorityDecision.PERMIT, AuthorityDecision.DENY}

    def test_is_str_enum(self):
        assert isinstance(AuthorityDecision.PERMIT, str)
        assert isinstance(AuthorityDecision.DENY, str)

    def test_value_reconstruction(self):
        assert AuthorityDecision("permit") is AuthorityDecision.PERMIT
        assert AuthorityDecision("deny") is AuthorityDecision.DENY
        with pytest.raises(ValueError):
            AuthorityDecision("allow")

    def test_serialization_as_json_string(self):
        # 作为契约字段序列化：mode="json" 落字符串字面量，JSON 可编码
        policy = AuthorityPolicy(default_decision=AuthorityDecision.PERMIT)
        dump = policy.model_dump(mode="json")
        assert dump["default_decision"] == "permit"
        assert json.loads(json.dumps(dump))["default_decision"] == "permit"

    def test_judgment_comparisons(self):
        decision = check_authority(_entity_effect(), AuthorityPolicy())
        assert decision is AuthorityDecision.DENY
        assert decision == "deny"  # str-Enum 与裸字符串值比较相等
        assert decision in (AuthorityDecision.PERMIT, AuthorityDecision.DENY)


# —— 3. AuthorityRule / AuthorityPolicy：模型校验与 default DENY ——


class TestAuthorityRuleModel:
    def test_defaults(self):
        rule = AuthorityRule(
            selector=AuthoritySelector(), allowed_writers=[ProducerId("rule.lock_system")]
        )
        assert rule.priority == 0
        assert rule.description == ""

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
                "default_decision": "permit",
            }
        )
        clone = AuthorityPolicy.model_validate(policy.model_dump(mode="json"))
        assert clone == policy
        assert clone.default_decision is AuthorityDecision.PERMIT
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

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            AuthorityPolicy.model_validate({"rules": [], "unknown": 1})

    def test_invalid_default_decision_rejected(self):
        with pytest.raises(ValidationError):
            AuthorityPolicy.model_validate({"default_decision": "maybe"})


# —— 4. check_authority 预留求值接口：首段实现基础口径（T03 完善）——


class TestCheckAuthorityFirstStage:
    def test_no_matching_rule_falls_back_to_default_deny(self):
        assert check_authority(_entity_effect(), AuthorityPolicy()) is AuthorityDecision.DENY

    def test_no_matching_rule_uses_configured_default(self):
        policy = AuthorityPolicy(default_decision=AuthorityDecision.PERMIT)
        assert check_authority(_domain_effect(), policy) is AuthorityDecision.PERMIT

    def test_matched_rule_grants_to_allowed_writer(self):
        policy = AuthorityPolicy(
            rules=[
                AuthorityRule(
                    selector=AuthoritySelector(effect_type=EffectTypeId("core.set_component")),
                    allowed_writers=[ProducerId("rule.lock_system")],
                )
            ]
        )
        assert check_authority(_entity_effect(), policy) is AuthorityDecision.PERMIT

    def test_matched_rule_denies_unlisted_writer_no_fallthrough(self):
        # 首条命中规则拍板 deny → 后续更宽泛的允许规则不被参考（不 fall-through）
        policy = AuthorityPolicy(
            rules=[
                AuthorityRule(
                    selector=AuthoritySelector(effect_type=EffectTypeId("core.set_component")),
                    allowed_writers=[ProducerId("rule.lock_system")],
                ),
                AuthorityRule(
                    selector=AuthoritySelector(),
                    allowed_writers=[ProducerId("policy.alice")],
                ),
            ]
        )
        assert check_authority(_entity_effect(source="policy.alice"), policy) is (
            AuthorityDecision.DENY
        )

    def test_higher_priority_rule_evaluated_first(self):
        policy = AuthorityPolicy(
            rules=[
                AuthorityRule(
                    selector=AuthoritySelector(),
                    allowed_writers=[ProducerId("policy.alice")],
                ),
                AuthorityRule(
                    selector=AuthoritySelector(),
                    allowed_writers=[ProducerId("rule.lock_system")],
                    priority=10,
                ),
            ]
        )
        # 高 priority 规则先求值：producer 在其 writers 内 → PERMIT
        assert check_authority(_entity_effect(source="rule.lock_system"), policy) is (
            AuthorityDecision.PERMIT
        )

    def test_specificity_breaks_priority_tie(self):
        policy = AuthorityPolicy(
            rules=[
                AuthorityRule(
                    selector=AuthoritySelector(),
                    allowed_writers=[ProducerId("policy.alice")],
                ),
                AuthorityRule(
                    selector=AuthoritySelector(effect_type=EffectTypeId("core.set_component")),
                    allowed_writers=[ProducerId("rule.lock_system")],
                ),
            ]
        )
        # priority 同分：更具体的规则先求值 → alice 不在其 writers → DENY（不回落）
        assert check_authority(_entity_effect(source="policy.alice"), policy) is (
            AuthorityDecision.DENY
        )

    def test_registration_order_breaks_full_tie(self):
        policy = AuthorityPolicy(
            rules=[
                AuthorityRule(
                    selector=AuthoritySelector(effect_type=EffectTypeId("core.set_component")),
                    allowed_writers=[ProducerId("policy.alice")],
                ),
                AuthorityRule(
                    selector=AuthoritySelector(effect_type=EffectTypeId("core.set_component")),
                    allowed_writers=[ProducerId("rule.lock_system")],
                ),
            ]
        )
        # priority 与 specificity 全同 → 注册序在先者拍板
        assert check_authority(_entity_effect(source="rule.lock_system"), policy) is (
            AuthorityDecision.DENY
        )

    def test_state_and_registry_flow_into_matching(self):
        policy = AuthorityPolicy(
            rules=[
                AuthorityRule(
                    selector=AuthoritySelector(entity_tag="merchant"),
                    allowed_writers=[ProducerId("policy.alice")],
                )
            ]
        )
        state = _state_with(["ent_auth_a"], tags_by_id={"ent_auth_a": ["merchant"]})
        effect = _entity_effect(source="policy.alice")
        assert check_authority(effect, policy, state=state) is AuthorityDecision.PERMIT
        # 无 state → entity_tag 维不可判定 → 无匹配 → default DENY
        assert check_authority(effect, policy, state=None) is AuthorityDecision.DENY

    def test_authority_scope_declaration_does_not_grant(self):
        # D-P2-17：authority_scope 声明不提升权限
        policy = AuthorityPolicy(
            rules=[
                AuthorityRule(
                    selector=AuthoritySelector(effect_type=EffectTypeId("core.set_component")),
                    allowed_writers=[ProducerId("rule.lock_system")],
                )
            ]
        )
        effect = _entity_effect(source="llm.narrator", authority_scope="space.position")
        assert check_authority(effect, policy) is AuthorityDecision.DENY

    def test_non_policy_input_raises_authority_error(self):
        with pytest.raises(AuthorityError):
            check_authority(_entity_effect(), "not-a-policy")  # type: ignore[arg-type]

    def test_non_effect_input_raises_authority_error(self):
        with pytest.raises(AuthorityError):
            check_authority("not-an-effect", AuthorityPolicy())  # type: ignore[arg-type]

    def test_authority_error_is_value_error(self):
        assert issubclass(AuthorityError, ValueError)
