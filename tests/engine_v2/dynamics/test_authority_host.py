"""P7-W4 test_authority_host.py（SOT §6.1 t1–t8 逐文件编号，8 平铺函数，
零 test class）。

契约面：producer 注册器 + 缺省权限策略构建器（SOT §3.7，T05）——
``P7_PRODUCER_IDS`` fullmatch 词法（t1，**A19**）/ 集合 + 常量逐字（t2）/
``build_dynamics_producers`` 4 注册 + priority 100/100/80/50 + origin
DYNAMICS_BACKEND（t3）/ 声明组件 4 producer 逐一 ``rule_allow``（t4）/
未注册 rogue + 未声明组件 → DENY ``no_matching_rule``（t5，**A18** 纯
authority 面）/ priority 全序 + 未注册归 0（t6，P7 钉死最小面）/ 单规则
并集结构逐字段（t7）/ ``model_dump`` JSON-clean（t8）。

夹具：消费 W1 conftest ``_det_entity_id``（实体 ID 确定性夹具；SOT §6.2）。
"""

from __future__ import annotations

from src.engine_v2.core.authority import AuthorityDecision, check_authority
from src.engine_v2.core.effects import EntityTarget, ProposedEffect
from src.engine_v2.core.ids import PRODUCER_ID_PATTERN
from src.engine_v2.core.provenance import OriginKind
from src.engine_v2.core.serialization import assert_json_clean
from src.engine_v2.dynamics.authority import (
    COMPOSITE_DYNAMICS_PRODUCER,
    LLM_WORLD_DYNAMICS_PRODUCER,
    P7_PRODUCER_IDS,
    RIGID_BODY_PRODUCER,
    RULE_DYNAMICS_PRODUCER,
    build_dynamics_producers,
    default_dynamics_policy,
)
from src.engine_v2.dynamics.backend import new_deterministic_effect_id
from tests.engine_v2.dynamics.conftest import _det_entity_id


def _effect(source: str, component_type: str | None = "rigid") -> ProposedEffect:
    """测试用 ProposedEffect（确定性 effect_id；target 声明组件可配）。"""
    return ProposedEffect(
        effect_id=new_deterministic_effect_id("auth_test", source, 0, 0),
        effect_type="gem.fell",
        source=source,
        target=EntityTarget(
            entity_id=_det_entity_id("gem"),
            component_type=component_type,
        ),
        payload={"moved": True},
        base_revision=0,
    )


def test_producer_ids_pattern_fullmatch() -> None:
    """t1：A19——``P7_PRODUCER_IDS`` 每名 fullmatch ``PRODUCER_ID_PATTERN`` + 4 常量 ∈ 元组 + 长度 4。"""
    assert len(P7_PRODUCER_IDS) == 4
    for producer_id in P7_PRODUCER_IDS:
        assert PRODUCER_ID_PATTERN.fullmatch(producer_id) is not None
    assert RULE_DYNAMICS_PRODUCER in P7_PRODUCER_IDS
    assert LLM_WORLD_DYNAMICS_PRODUCER in P7_PRODUCER_IDS
    assert RIGID_BODY_PRODUCER in P7_PRODUCER_IDS
    assert COMPOSITE_DYNAMICS_PRODUCER in P7_PRODUCER_IDS


def test_producer_ids_set_exact() -> None:
    """t2：集合精确 + 4 常量值逐字 + 元组序逐字（SOT §3.7 代码块）。"""
    assert set(P7_PRODUCER_IDS) == {
        "rule_dynamics",
        "llm_world_dynamics",
        "rigid_body",
        "composite_dynamics",
    }
    assert RULE_DYNAMICS_PRODUCER == "rule_dynamics"
    assert LLM_WORLD_DYNAMICS_PRODUCER == "llm_world_dynamics"
    assert RIGID_BODY_PRODUCER == "rigid_body"
    assert COMPOSITE_DYNAMICS_PRODUCER == "composite_dynamics"
    assert P7_PRODUCER_IDS == (
        "rule_dynamics",
        "llm_world_dynamics",
        "rigid_body",
        "composite_dynamics",
    )
    assert len(P7_PRODUCER_IDS) == len(set(P7_PRODUCER_IDS))


def test_build_producers_priorities() -> None:
    """t3：``build_dynamics_producers``——4 注册（get 非 None）+ priority 100/100/80/50 + origin DYNAMICS_BACKEND 逐 producer。"""
    registry = build_dynamics_producers()
    for producer_id in P7_PRODUCER_IDS:
        info = registry.get(producer_id)
        assert info is not None
        assert info.origin == OriginKind.DYNAMICS_BACKEND
    assert registry.priority_of("rule_dynamics") == 100
    assert registry.priority_of("rigid_body") == 100
    assert registry.priority_of("composite_dynamics") == 80
    assert registry.priority_of("llm_world_dynamics") == 50
    assert registry.get("rogue") is None


def test_default_policy_allows_declared() -> None:
    """t4：声明 (rigid, gem_state)——4 producer 各构 1 effect（source 逐名、target 声明组件）→ ALLOW + rule_allow 逐 producer。"""
    policy = default_dynamics_policy(component_types=("rigid", "gem_state"))
    for producer_id in P7_PRODUCER_IDS:
        evaluation = check_authority(_effect(producer_id, "rigid"), policy)
        assert evaluation.decision == AuthorityDecision.ALLOW
        assert evaluation.reason_code == "rule_allow"
        assert evaluation.matched_rule_index is not None
        assert str(evaluation.producer) == producer_id


def test_closed_default_no_matching_rule_deny() -> None:
    """t5：A18——rogue（未注册）effect 于 gem_state + 仅声明 rigid 的 policy → DENY no_matching_rule；空声明 policy 同判。"""
    rogue_effect = _effect("rogue", "gem_state")
    policy_rigid_only = default_dynamics_policy(component_types=("rigid",))
    evaluation = check_authority(rogue_effect, policy_rigid_only)
    assert evaluation.decision == AuthorityDecision.DENY
    assert evaluation.reason_code == "no_matching_rule"
    assert evaluation.matched_rule_index is None
    policy_empty = default_dynamics_policy()
    evaluation_empty = check_authority(rogue_effect, policy_empty)
    assert evaluation_empty.decision == AuthorityDecision.DENY
    assert evaluation_empty.reason_code == "no_matching_rule"
    assert policy_empty.rules == []


def test_producer_priority_ordering_physics_over_llm() -> None:
    """t6：P7 钉死最小面——priority_of 全序 rule/rigid 100 > composite 80 > 推理 50 + 未注册 id 归 0。"""
    registry = build_dynamics_producers()
    priority_rule = registry.priority_of("rule_dynamics")
    priority_rigid = registry.priority_of("rigid_body")
    priority_composite = registry.priority_of("composite_dynamics")
    priority_inference = registry.priority_of("llm_world_dynamics")
    assert priority_rule == 100
    assert priority_rigid == 100
    assert priority_composite == 80
    assert priority_inference == 50
    assert priority_rule == priority_rigid > priority_composite > priority_inference
    assert registry.priority_of("rogue") == 0


def test_default_policy_component_dimension() -> None:
    """t7：2 组件声明 → 恰 2 规则；逐条 selector.component_type 逐字 + allowed_writers 4 名逐字 + priority 100；default_decision DENY。"""
    policy = default_dynamics_policy(component_types=("rigid", "gem_state"))
    assert len(policy.rules) == 2
    assert [str(rule.selector.component_type) for rule in policy.rules] == [
        "rigid",
        "gem_state",
    ]
    for rule in policy.rules:
        assert rule.selector.field is None
        assert rule.selector.domain_tag is None
        assert rule.selector.effect_type is None
        assert rule.selector.entity_tag is None
        assert [str(writer) for writer in rule.allowed_writers] == [
            "rule_dynamics",
            "rigid_body",
            "llm_world_dynamics",
            "composite_dynamics",
        ]
        assert rule.priority == 100
    assert policy.default_decision == AuthorityDecision.DENY


def test_default_policy_dump_json_clean() -> None:
    """t8：``policy.model_dump(mode="json")`` → ``assert_json_clean`` 过（ERR-P6-10(a) JSON-clean 机械面）。"""
    policy = default_dynamics_policy(component_types=("rigid", "gem_state"))
    dumped = policy.model_dump(mode="json")
    assert_json_clean(dumped)
    assert set(dumped.keys()) == {"rules", "default_decision"}
    assert dumped["default_decision"] == "deny"
    assert len(dumped["rules"]) == 2
    assert set(dumped["rules"][0].keys()) == {
        "selector",
        "allowed_writers",
        "priority",
        "description",
        "rule_id",
    }
