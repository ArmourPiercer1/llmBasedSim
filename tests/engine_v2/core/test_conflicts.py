"""P2-T05 验收：conflicts.py 冲突定义与锁提取、连通分量分组、策略链与批级报告（P2 设计规范 §5）。

覆盖（任务包 P2-T05 目标 1–3 口径）：

1. **冲突定义与锁提取**（目标 1a；§5.1 / D-P2-11 前段）——
   :class:`ConflictKey` 与 :func:`extract_effect_locks` /
   :func:`conflict_key` / :func:`conflicts_with`：
   - 五行锁规则表：整实体锁 / 整组件锁 / 字段锁 / 域锁 / 结构动词
     （``core.create_entity`` / ``core.remove_entity``）升级锁级别；
   - ConflictKey 不变量（kind 词表 / entity 定位键齐备 / 字段锁不悬空 /
     domain 键纯净 → :class:`ConflictError`）、frozen / 可哈希 / 全等 /
     ``render`` 规范化串；
   - 相交判定全矩阵（同 entity + None 通配层级 / 同组件不同字段不相交 /
     域锁全等 / 异 kind 永不相交）；
   - ``effect_locks`` 设计文档 §5.1 命名与任务包命名同一函数对象；
   - 输入契约守卫（非 ``ProposedEffect`` → ConflictError）。
2. **detect_conflicts 连通分量分组**（目标 1b；§5.2）——
   - 无冲突 / 空批 / 单元素 → ``[]``；
   - 双元素组（组内到达序）；传递链 A–B–C 同组（A∩C 为空仍同组——连通
     分量口径）；星形拓扑；
   - 多不相交组按组内最小到达序升序；交错到达同序断言；
   - 同组件不同 field_path **不成组**（P2 设计规范 §11 类别 2b）；整组件
     vs 字段成组（2c）；结构动词升级锁级别（create/remove_entity 恒整
     实体锁）；**批内暂存依赖豁免**（P2-REMEDIATION B1）：先到达的
     ``core.create_entity`` 与后到达的同实体 ``core.set_component``（初
     始化挂载）不成组（双创建 / 倒序到达 / remove_entity 组合仍成组）；
   - ``ConflictGroup.keys`` = 成员锁去重并（成员到达序 + 成员内 render
     序）；确定性（同输入同输出）。
3. **默认四策**（目标 2a；§5.4 固定顺序）——逐策略判定与弃权条件：
   - ``AuthorityPriorityStrategy``：rule_priority 最大且唯一胜 / 并列弃权 /
     无 decisions 弃权 / 全 rule_priority=None 弃权 / 部分无排序优先级时
     唯一可排序者胜；
   - ``TimestampStrategy``（D-P2-16）：全员携带 int → 最大胜（LWW）/ 任一
     缺失弃权 / 非 int（str/float/bool）弃权 / 并列弃权；
   - ``ProducerPriorityStrategy``：registry 优先级 / 并列比 hint（None 视
     0）/ 含 hint 仍并列弃权 / 无 registry 弃权 / 未注册 producer 归 0；
   - ``EntityFifoStrategy``：到达序最小胜 / 永不弃权 / arrival 缺失防御性
     永不胜出。
4. **DefaultConflictResolver 策略链**（目标 2b；§5.3/§5.5）——
   - 链序四策接力（每策构造"会选不同赢家"的输入，证明弃权链与求值序）；
   - 全策略弃权 → 保守 REJECT 全组（``strategy="fallback"``，
     ``accepted=()``，``dropped`` = 全组）；
   - 扩展位透传（桩策略 MERGE / DEFER 原样返回——§5.5 机制正确性，不引入
     真实域语义）；
   - 自定义 strategies 元组（子集 / 换序）；
   - 输入守卫（组 <2 / 非 ConflictGroup → ConflictError）。
5. **ConflictResolutionReport 与批级入口**（目标 3；任务包目标 3）——
   - ``resolve_all`` 混合批（冲突对 + 直通）→ resolutions 逐组 / accepted /
     dropped 均到达序；无冲突批 → resolutions 空、全直通；
   - 输入守卫：批内重复 effect_id → ConflictError；ctx.arrival 未全覆盖 →
     ConflictError；
   - ``resolution_for``（胜者/败者 → 所属组；直通 → None）；
   - ``resolve_conflicts`` 模块级门面与解析器方法等价。
6. **Trace 协同**（§9）——``ConflictResolution.to_trace_payload`` 恰为 P1
   冻结约定键 ``DECISION_PAYLOAD_KEYS`` 三键；WINNER → effect_id = 唯一
   胜者、decision = "winner"；REJECT → effect_id = 组成员串、decision =
   "reject"；reason = 策略名 + detail；确定性（同结果同 payload，不生成
   ID）。
7. **导出集成**——包级 re-export 与模块定义同一对象（closeout 机械化口径的
   本模块侧印证）。

全部用例无网络、无 LLM、无 API key（Spec §47 Phase 1 验收）。
"""

from __future__ import annotations

import dataclasses
from dataclasses import FrozenInstanceError, is_dataclass
from typing import Any

import pytest

import src.engine_v2.core as core_pkg
import src.engine_v2.core.conflicts as conflicts_mod
from src.engine_v2.core.authority import (
    AuthorityDecision,
    AuthorityEvaluationResult,
    ProducerInfo,
    ProducerRegistry,
)
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.conflicts import (
    AuthorityPriorityStrategy,
    ConflictAction,
    ConflictError,
    ConflictGroup,
    ConflictKey,
    ConflictResolution,
    ConflictResolutionReport,
    ConflictStrategy,
    DEFAULT_STRATEGIES,
    DefaultConflictResolver,
    DomainResolverFactory,
    EntityFifoStrategy,
    ProducerPriorityStrategy,
    ResolutionContext,
    TIMESTAMP_METADATA_KEY,
    TimestampStrategy,
    conflict_key,
    conflicts_with,
    detect_conflicts,
    effect_locks,
    extract_effect_locks,
    resolve_conflicts,
)
from src.engine_v2.core.effects import (
    EffectTypeId,
    EntityTarget,
    ProposedEffect,
    StateDomainId,
    StateDomainTarget,
)
from src.engine_v2.core.ids import EffectId, EntityId, ProducerId
from src.engine_v2.core.provenance import OriginKind
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.trace import DECISION_PAYLOAD_KEYS


# —— 样本工厂（自包含、确定性构造）——


def _entity_effect(
    effect_id: str = "eff_conf_a",
    *,
    source: str = "rule.p_a",
    effect_type: str = "core.set_component",
    entity_id: str = "ent_conf_x",
    component_type: str | None = "space.position",
    field_path: str | None = None,
    priority_hint: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> ProposedEffect:
    """确定性构造 entity 分支拟议效果（``core.set_component`` 形态）。"""
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
        priority_hint=priority_hint,
        metadata=dict(metadata or {}),
    )


def _domain_effect(
    effect_id: str = "eff_conf_w",
    *,
    source: str = "rule.clock",
    effect_type: str = "core.set_world_variable",
    domain: str = "world_variables",
    priority_hint: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> ProposedEffect:
    """确定性构造 state domain 分支拟议效果（``core.set_world_variable`` 形态）。"""
    return ProposedEffect(
        effect_id=EffectId(effect_id),
        effect_type=EffectTypeId(effect_type),
        source=ProducerId(source),
        target=StateDomainTarget(domain=StateDomainId(domain)),
        payload={},
        base_revision=Revision(0),
        priority_hint=priority_hint,
        metadata=dict(metadata or {}),
    )


def _ctx(
    effects: list[ProposedEffect],
    authority_decisions: dict[EffectId, AuthorityEvaluationResult] | None = None,
    producer_registry: ProducerRegistry | None = None,
) -> ResolutionContext:
    """经 from_batch 构造解析上下文（arrival = 批内到达序）。"""
    return ResolutionContext.from_batch(
        effects,
        authority_decisions=authority_decisions,
        producer_registry=producer_registry,
    )


def _decision(
    effect_id: str,
    *,
    rule_priority: int | None,
    reason_code: str = "rule_allow",
    producer: str = "rule.p_a",
) -> AuthorityEvaluationResult:
    """确定性构造 authority 求值结果（策略 1 输入；rule_priority 为排序键）。"""
    return AuthorityEvaluationResult(
        effect_id=EffectId(effect_id),
        producer=ProducerId(producer),
        decision=AuthorityDecision.ALLOW,
        reason_code=reason_code,
        evaluated_rules_count=1 if rule_priority is not None else 0,
        rule_priority=rule_priority,
    )


def _registry(priorities: dict[str, int]) -> ProducerRegistry:
    """按 {producer 名: priority} 构造 producer 注册表（origin 统一 SYSTEM）。"""
    registry = ProducerRegistry()
    for name, priority in priorities.items():
        registry.register(
            ProducerInfo(producer_id=ProducerId(name), origin=OriginKind.SYSTEM, priority=priority)
        )
    return registry


def _pair_group(a: ProposedEffect, b: ProposedEffect) -> ConflictGroup:
    """两个同址冲突 effect → 唯一冲突组（确定性单组断言 + 取组）。"""
    groups = detect_conflicts([a, b])
    assert len(groups) == 1, f"期望恰好一个冲突组，得到 {len(groups)}"
    return groups[0]


# —— 1. 冲突键与锁推导（§5.1）——


class TestConflictKeyShape:
    """ConflictKey 数据形状：kind 不变量 / frozen / 哈希 / render。"""

    def test_entity_locks_shapes(self):
        key_entity = ConflictKey(kind="entity", entity_id=EntityId("ent_1"))
        key_component = ConflictKey(
            kind="entity",
            entity_id=EntityId("ent_1"),
            component_type=ComponentTypeId("health"),
        )
        key_field = ConflictKey(
            kind="entity",
            entity_id=EntityId("ent_1"),
            component_type=ComponentTypeId("health"),
            field_path="hp",
        )
        key_domain = ConflictKey(kind="domain", domain=StateDomainId("world_variables"))
        assert (key_entity, key_component, key_field, key_domain) is not None
        assert key_entity.render() == "entity:ent_1"
        assert key_component.render() == "entity:ent_1:comp:health"
        assert key_field.render() == "entity:ent_1:comp:health:field:hp"
        assert key_domain.render() == "domain:world_variables"

    def test_frozen_and_hashable_and_eq(self):
        key_a = ConflictKey(kind="entity", entity_id=EntityId("ent_1"))
        key_b = ConflictKey(kind="entity", entity_id=EntityId("ent_1"))
        assert key_a == key_b
        assert hash(key_a) == hash(key_b)
        assert {key_a, key_b} == {key_a}
        with pytest.raises(FrozenInstanceError):
            key_a.entity_id = EntityId("ent_2")  # type: ignore[misc]

    @pytest.mark.parametrize("kwargs", [
        {"kind": "component"},  # kind 词表之外
        {"kind": "entity"},  # entity 缺 entity_id
        {"kind": "domain"},  # domain 缺 domain
        {"kind": "entity", "entity_id": EntityId("ent_1"), "domain": StateDomainId("scenario")},
        {"kind": "entity", "field_path": "hp"},  # 字段锁悬空（无 component_type）
        {
            "kind": "domain",
            "domain": StateDomainId("scenario"),
            "entity_id": EntityId("ent_1"),
        },  # domain 键不纯净
    ])
    def test_invariants_raise_conflict_error(self, kwargs):
        with pytest.raises(ConflictError):
            ConflictKey(**kwargs)
        assert issubclass(ConflictError, ValueError)

    def test_field_lock_with_component_is_valid(self):
        key = ConflictKey(
            kind="entity",
            entity_id=EntityId("ent_1"),
            component_type=ComponentTypeId("health"),
            field_path="hp",
        )
        assert key.render() == "entity:ent_1:comp:health:field:hp"


class TestLockExtraction:
    """extract_effect_locks 五行锁规则表 + 结构动词升级 + 命名双轨。"""

    def test_entity_target_without_component_is_whole_entity_lock(self):
        effect = _entity_effect(component_type=None)
        assert extract_effect_locks(effect) == frozenset(
            {ConflictKey(kind="entity", entity_id=EntityId("ent_conf_x"))}
        )

    def test_entity_target_with_component_is_whole_component_lock(self):
        effect = _entity_effect()
        assert extract_effect_locks(effect) == frozenset(
            {
                ConflictKey(
                    kind="entity",
                    entity_id=EntityId("ent_conf_x"),
                    component_type=ComponentTypeId("space.position"),
                )
            }
        )

    def test_entity_target_with_field_is_field_lock(self):
        effect = _entity_effect(field_path="x")
        assert extract_effect_locks(effect) == frozenset(
            {
                ConflictKey(
                    kind="entity",
                    entity_id=EntityId("ent_conf_x"),
                    component_type=ComponentTypeId("space.position"),
                    field_path="x",
                )
            }
        )

    def test_state_domain_target_is_domain_lock(self):
        effect = _domain_effect(domain="scenario")
        assert extract_effect_locks(effect) == frozenset(
            {ConflictKey(kind="domain", domain=StateDomainId("scenario"))}
        )

    def test_create_entity_upgrades_to_whole_entity_lock(self):
        # target 上附带 component_type/field_path 也被结构动词升级抹平
        effect = _entity_effect(
            effect_id="eff_conf_create",
            effect_type="core.create_entity",
            entity_id="ent_conf_new",
            component_type="space.position",
            field_path="x",
        )
        assert extract_effect_locks(effect) == frozenset(
            {ConflictKey(kind="entity", entity_id=EntityId("ent_conf_new"))}
        )

    def test_remove_entity_upgrades_to_whole_entity_lock(self):
        effect = _entity_effect(
            effect_id="eff_conf_remove",
            effect_type="core.remove_entity",
            entity_id="ent_conf_new",
            component_type="space.position",
        )
        assert extract_effect_locks(effect) == frozenset(
            {ConflictKey(kind="entity", entity_id=EntityId("ent_conf_new"))}
        )

    def test_remove_component_does_not_upgrade(self):
        # 结构动词升级仅限 create/remove entity：remove_component 保持整组件锁
        effect = _entity_effect(effect_type="core.remove_component")
        assert extract_effect_locks(effect) == frozenset(
            {
                ConflictKey(
                    kind="entity",
                    entity_id=EntityId("ent_conf_x"),
                    component_type=ComponentTypeId("space.position"),
                )
            }
        )

    def test_returns_frozenset_and_single_key(self):
        locks = extract_effect_locks(_entity_effect())
        assert type(locks) is frozenset
        assert len(locks) == 1

    def test_conflict_key_is_single_lock_member(self):
        for effect in (
            _entity_effect(),
            _entity_effect(component_type=None),
            _entity_effect(field_path="x"),
            _domain_effect(),
            _entity_effect(effect_type="core.create_entity", entity_id="ent_conf_new"),
        ):
            locks = extract_effect_locks(effect)
            assert conflict_key(effect) in locks
            assert len(locks) == 1

    def test_effect_locks_alias_is_same_function(self):
        # 设计文档 §5.1 命名（effect_locks）与任务包命名（extract_effect_locks）
        # 同一函数对象
        assert effect_locks is extract_effect_locks

    def test_non_proposed_effect_raises_conflict_error(self):
        with pytest.raises(ConflictError):
            conflict_key(object())  # type: ignore[arg-type]
        with pytest.raises(ConflictError):
            extract_effect_locks("not an effect")  # type: ignore[arg-type]


class TestConflictsWith:
    """conflicts_with 相交判定全矩阵（§5.1 相交判定）。"""

    def test_same_entity_both_whole(self):
        k1 = ConflictKey(kind="entity", entity_id=EntityId("ent_1"))
        k2 = ConflictKey(kind="entity", entity_id=EntityId("ent_1"))
        assert conflicts_with(k1, k2) and conflicts_with(k2, k1)

    def test_whole_entity_vs_component_same_entity(self):
        whole = ConflictKey(kind="entity", entity_id=EntityId("ent_1"))
        comp = ConflictKey(
            kind="entity", entity_id=EntityId("ent_1"), component_type=ComponentTypeId("health")
        )
        assert conflicts_with(whole, comp) and conflicts_with(comp, whole)

    def test_component_vs_field_same_component(self):
        comp = ConflictKey(
            kind="entity", entity_id=EntityId("ent_1"), component_type=ComponentTypeId("health")
        )
        field = ConflictKey(
            kind="entity",
            entity_id=EntityId("ent_1"),
            component_type=ComponentTypeId("health"),
            field_path="hp",
        )
        assert conflicts_with(comp, field) and conflicts_with(field, comp)

    def test_same_entity_different_components_do_not_conflict(self):
        k1 = ConflictKey(
            kind="entity", entity_id=EntityId("ent_1"), component_type=ComponentTypeId("health")
        )
        k2 = ConflictKey(
            kind="entity", entity_id=EntityId("ent_1"), component_type=ComponentTypeId("inventory")
        )
        assert not conflicts_with(k1, k2)

    def test_same_component_different_fields_do_not_conflict(self):
        k1 = ConflictKey(
            kind="entity",
            entity_id=EntityId("ent_1"),
            component_type=ComponentTypeId("health"),
            field_path="hp",
        )
        k2 = ConflictKey(
            kind="entity",
            entity_id=EntityId("ent_1"),
            component_type=ComponentTypeId("health"),
            field_path="max_hp",
        )
        assert not conflicts_with(k1, k2)

    def test_field_vs_whole_entity_conflicts(self):
        whole = ConflictKey(kind="entity", entity_id=EntityId("ent_1"))
        field = ConflictKey(
            kind="entity",
            entity_id=EntityId("ent_1"),
            component_type=ComponentTypeId("health"),
            field_path="hp",
        )
        assert conflicts_with(field, whole)

    def test_different_entities_do_not_conflict(self):
        k1 = ConflictKey(kind="entity", entity_id=EntityId("ent_1"))
        k2 = ConflictKey(kind="entity", entity_id=EntityId("ent_2"))
        assert not conflicts_with(k1, k2)

    def test_same_domain_conflicts(self):
        k1 = ConflictKey(kind="domain", domain=StateDomainId("world_variables"))
        k2 = ConflictKey(kind="domain", domain=StateDomainId("world_variables"))
        assert conflicts_with(k1, k2)

    def test_different_domains_do_not_conflict(self):
        k1 = ConflictKey(kind="domain", domain=StateDomainId("world_variables"))
        k2 = ConflictKey(kind="domain", domain=StateDomainId("scenario"))
        assert not conflicts_with(k1, k2)

    def test_entity_kind_vs_domain_kind_never_conflicts(self):
        k1 = ConflictKey(kind="entity", entity_id=EntityId("ent_1"))
        k2 = ConflictKey(kind="domain", domain=StateDomainId("scenario"))
        assert not conflicts_with(k1, k2)
        assert not conflicts_with(k2, k1)


# —— 2. detect_conflicts 连通分量分组（§5.2）——


class TestDetectConflicts:
    """连通分量分组：确定性 / 传递闭包 / 多组排序 / keys 并集。"""

    def test_no_conflict_returns_empty(self):
        effects = [
            _entity_effect(effect_id="eff_c1", entity_id="ent_a", component_type="comp.x"),
            _entity_effect(effect_id="eff_c2", entity_id="ent_b", component_type="comp.x"),
            _domain_effect(effect_id="eff_c3", domain="scenario"),
        ]
        assert detect_conflicts(effects) == []

    def test_empty_batch_returns_empty(self):
        assert detect_conflicts([]) == []

    def test_single_effect_returns_empty(self):
        assert detect_conflicts([_entity_effect()]) == []

    def test_pair_forms_single_group_in_arrival_order(self):
        e0 = _entity_effect(effect_id="eff_c4")
        e1 = _entity_effect(effect_id="eff_c5", component_type="space.position")
        groups = detect_conflicts([e0, e1])
        assert len(groups) == 1
        assert groups[0].effects == (e0, e1)  # 组内到达序

    def test_transitive_chain_groups_together(self):
        # A(f1) ∩ B(整组件) 、B ∩ C(f2) ，A ∩ C = ∅ → 仍同组（连通分量口径）
        a = _entity_effect(effect_id="eff_c6", field_path="hp")
        b = _entity_effect(effect_id="eff_c7")
        c = _entity_effect(effect_id="eff_c8", field_path="max_hp")
        assert not conflicts_with(
            conflict_key(a), conflict_key(c)
        ), "前置自检：A 与 C 不应直接相交"
        groups = detect_conflicts([a, b, c])
        assert len(groups) == 1
        assert groups[0].effects == (a, b, c)

    def test_star_topology_groups_together(self):
        center = _entity_effect(effect_id="eff_c9", component_type=None)
        leaves = [
            _entity_effect(effect_id=f"eff_c1{i}", component_type=f"comp.l{i}") for i in range(3)
        ]
        groups = detect_conflicts([center, *leaves])
        assert len(groups) == 1
        assert groups[0].effects == (center, *leaves)

    def test_disjoint_groups_sorted_by_min_arrival(self):
        g1a = _entity_effect(effect_id="eff_c11", entity_id="ent_g1", component_type="comp.a")
        g1b = _entity_effect(
            effect_id="eff_c12", entity_id="ent_g1", component_type="comp.a", field_path="f1"
        )
        lone = _entity_effect(effect_id="eff_c13", entity_id="ent_lone")
        g2a = _entity_effect(
            effect_id="eff_c14", entity_id="ent_g2", component_type="comp.b", field_path="f9"
        )
        g2b = _entity_effect(effect_id="eff_c15", entity_id="ent_g2", component_type="comp.b")
        groups = detect_conflicts([g1a, g1b, lone, g2a, g2b])
        assert len(groups) == 2
        assert groups[0].effects == (g1a, g1b)  # 最小到达序 0
        assert groups[1].effects == (g2a, g2b)  # 最小到达序 3
        assert all(lone is not e for g in groups for e in g.effects), "直通 effect 不进任何组"

    def test_interleaved_arrival_order_preserved(self):
        e0 = _entity_effect(effect_id="eff_c16", entity_id="ent_i1", field_path="f1")
        e1 = _entity_effect(effect_id="eff_c17", entity_id="ent_i2", field_path="f9")
        e2 = _entity_effect(effect_id="eff_c18", entity_id="ent_i1")
        e3 = _entity_effect(effect_id="eff_c19", entity_id="ent_i2")
        groups = detect_conflicts([e0, e1, e2, e3])
        assert [g.effects for g in groups] == [(e0, e2), (e1, e3)]

    def test_same_component_different_fields_do_not_group(self):
        # P2 设计规范 §11 类别 2b：同组件不同 field_path 的两个字段级效果不成组
        e0 = _entity_effect(effect_id="eff_c20", field_path="hp")
        e1 = _entity_effect(effect_id="eff_c21", field_path="max_hp")
        assert detect_conflicts([e0, e1]) == []

    def test_whole_component_vs_field_groups(self):
        # §11 类别 2c：整组件效果 vs 字段效果应成组
        e0 = _entity_effect(effect_id="eff_c22")
        e1 = _entity_effect(effect_id="eff_c23", field_path="hp")
        assert len(detect_conflicts([e0, e1])) == 1

    def test_create_then_set_component_is_staged_dependency_not_conflict(self):
        # P2-REMEDIATION B1：同批次先 create 后对同一实体 set_component
        #（初始化挂载）是合法暂存依赖，不建冲突边——锁相交成立（整实体锁
        # × 组件锁）但语义为顺序依赖而非互斥竞争
        e0 = _entity_effect(
            effect_id="eff_c24", effect_type="core.create_entity", entity_id="ent_c24"
        )
        e1 = _entity_effect(
            effect_id="eff_c25", entity_id="ent_c24", component_type="space.position"
        )
        assert detect_conflicts([e0, e1]) == []

    def test_staged_dependency_multiple_init_components(self):
        # 创建 + 多组件初始化挂载（不同组件互不相交，且均与 create 豁免）
        e0 = _entity_effect(
            effect_id="eff_c24a", effect_type="core.create_entity", entity_id="ent_c24a"
        )
        e1 = _entity_effect(
            effect_id="eff_c24b", entity_id="ent_c24a", component_type="space.position"
        )
        e2 = _entity_effect(
            effect_id="eff_c24c", entity_id="ent_c24a", component_type="attrs.hp"
        )
        assert detect_conflicts([e0, e1, e2]) == []

    def test_staged_dependency_with_field_level_init(self):
        # 字段级初始化挂载同样豁免（create 整实体锁 × 字段锁相交但为暂存依赖）
        e0 = _entity_effect(
            effect_id="eff_c24d", effect_type="core.create_entity", entity_id="ent_c24d"
        )
        e1 = _entity_effect(
            effect_id="eff_c24e",
            entity_id="ent_c24d",
            component_type="attrs.hp",
            field_path="current",
        )
        assert detect_conflicts([e0, e1]) == []

    def test_double_create_same_entity_still_conflicts(self):
        # 双创建同一实体：结构动词 × 结构动词，不在豁免组合内 → 成组
        e0 = _entity_effect(
            effect_id="eff_c24f", effect_type="core.create_entity", entity_id="ent_c24f"
        )
        e1 = _entity_effect(
            effect_id="eff_c24g", effect_type="core.create_entity", entity_id="ent_c24f"
        )
        groups = detect_conflicts([e0, e1])
        assert len(groups) == 1
        assert groups[0].effects == (e0, e1)

    def test_reversed_set_before_create_still_conflicts(self):
        # 倒序到达（set_component 先、create 后）不构成暂存依赖 → 保守成组
        e0 = _entity_effect(
            effect_id="eff_c24h", entity_id="ent_c24h", component_type="space.position"
        )
        e1 = _entity_effect(
            effect_id="eff_c24i", effect_type="core.create_entity", entity_id="ent_c24h"
        )
        groups = detect_conflicts([e0, e1])
        assert len(groups) == 1
        assert groups[0].effects == (e0, e1)

    def test_remove_entity_vs_set_component_still_conflicts(self):
        # 豁免仅限 create → set_component；remove_entity 与同实体变更仍成组
        e0 = _entity_effect(
            effect_id="eff_c24j", effect_type="core.remove_entity", entity_id="ent_c24j"
        )
        e1 = _entity_effect(
            effect_id="eff_c24k", entity_id="ent_c24j", component_type="space.position"
        )
        groups = detect_conflicts([e0, e1])
        assert len(groups) == 1
        assert groups[0].effects == (e0, e1)

    def test_staged_dependency_does_not_shield_competing_sets(self):
        # create 豁免不遮蔽同组件竞争写：两个 set_component 仍互相成组，
        # create 直通（豁免只去边，不改变连通分量的其余结构）
        e0 = _entity_effect(
            effect_id="eff_c24l", effect_type="core.create_entity", entity_id="ent_c24l"
        )
        e1 = _entity_effect(
            effect_id="eff_c24m", entity_id="ent_c24l", component_type="space.position"
        )
        e2 = _entity_effect(
            effect_id="eff_c24n", entity_id="ent_c24l", component_type="space.position"
        )
        groups = detect_conflicts([e0, e1, e2])
        assert len(groups) == 1
        assert groups[0].effects == (e1, e2), "create 不进组；竞争写照常仲裁"

    def test_entity_vs_domain_never_group(self):
        e0 = _entity_effect(effect_id="eff_c26")
        e1 = _domain_effect(effect_id="eff_c27")
        assert detect_conflicts([e0, e1]) == []

    def test_group_keys_is_deduped_union_in_deterministic_order(self):
        e0 = _entity_effect(effect_id="eff_c28", field_path="hp")
        e1 = _entity_effect(effect_id="eff_c29")
        e2 = _entity_effect(effect_id="eff_c30", field_path="hp")  # 与 e0 同锁（去重验证）
        groups = detect_conflicts([e0, e1, e2])
        assert len(groups) == 1
        assert groups[0].keys == (
            ConflictKey(
                kind="entity",
                entity_id=EntityId("ent_conf_x"),
                component_type=ComponentTypeId("space.position"),
                field_path="hp",
            ),
            ConflictKey(
                kind="entity",
                entity_id=EntityId("ent_conf_x"),
                component_type=ComponentTypeId("space.position"),
            ),
        )

    def test_determinism_same_input_same_output(self):
        effects = [
            _entity_effect(effect_id="eff_c31", entity_id="ent_d1", field_path="f1"),
            _entity_effect(effect_id="eff_c32", entity_id="ent_d1"),
            _entity_effect(effect_id="eff_c33", entity_id="ent_d2", field_path="f2"),
            _entity_effect(effect_id="eff_c34", entity_id="ent_d2"),
            _domain_effect(effect_id="eff_c35"),
        ]
        first = detect_conflicts(effects)
        second = detect_conflicts(effects)
        assert first == second
        assert [g.effects for g in first] == [
            (effects[0], effects[1]),
            (effects[2], effects[3]),
        ]

    def test_non_proposed_effect_element_raises_conflict_error(self):
        with pytest.raises(ConflictError):
            detect_conflicts([object()])  # type: ignore[list-item]


# —— 3. 默认四策（§5.4）——


class TestAuthorityPriorityStrategy:
    """策略 1：authority 规则优先级（rule_priority 最大且唯一胜）。"""

    def test_highest_unique_rule_priority_wins(self):
        e0 = _entity_effect(effect_id="eff_a0", source="rule.p_a")
        e1 = _entity_effect(effect_id="eff_a1", source="rule.p_b")
        ctx = _ctx(
            [e0, e1],
            authority_decisions={
                EffectId("eff_a0"): _decision("eff_a0", rule_priority=5),
                EffectId("eff_a1"): _decision("eff_a1", rule_priority=3),
            },
        )
        resolution = AuthorityPriorityStrategy().resolve(_pair_group(e0, e1), ctx)
        assert resolution is not None
        assert resolution.action is ConflictAction.WINNER
        assert resolution.strategy == "authority_priority"
        assert resolution.accepted == (EffectId("eff_a0"),)
        assert resolution.dropped == (EffectId("eff_a1"),)
        assert "rule_priority=5" in resolution.reason
        assert "eff_a0" in resolution.reason

    def test_tie_abstains(self):
        e0 = _entity_effect(effect_id="eff_a2", source="rule.p_a")
        e1 = _entity_effect(effect_id="eff_a3", source="rule.p_b")
        ctx = _ctx(
            [e0, e1],
            authority_decisions={
                EffectId("eff_a2"): _decision("eff_a2", rule_priority=4),
                EffectId("eff_a3"): _decision("eff_a3", rule_priority=4),
            },
        )
        assert AuthorityPriorityStrategy().resolve(_pair_group(e0, e1), ctx) is None

    def test_no_decisions_abstains(self):
        e0 = _entity_effect(effect_id="eff_a4")
        e1 = _entity_effect(effect_id="eff_a5")
        ctx = _ctx([e0, e1])
        assert AuthorityPriorityStrategy().resolve(_pair_group(e0, e1), ctx) is None

    def test_all_rule_priority_none_abstains(self):
        # closed-by-default 回落 ALLOW（无拍板规则）→ 无可排序优先级 → 弃权
        e0 = _entity_effect(effect_id="eff_a6")
        e1 = _entity_effect(effect_id="eff_a7")
        ctx = _ctx(
            [e0, e1],
            authority_decisions={
                EffectId("eff_a6"): _decision(
                    "eff_a6", rule_priority=None, reason_code="no_matching_rule"
                ),
                EffectId("eff_a7"): _decision(
                    "eff_a7", rule_priority=None, reason_code="no_matching_rule"
                ),
            },
        )
        assert AuthorityPriorityStrategy().resolve(_pair_group(e0, e1), ctx) is None

    def test_unique_rankable_beats_unrankable(self):
        # 唯一可排序者胜；无排序优先级者落选进 dropped
        e0 = _entity_effect(effect_id="eff_a8")
        e1 = _entity_effect(effect_id="eff_a9")
        ctx = _ctx(
            [e0, e1],
            authority_decisions={
                EffectId("eff_a8"): _decision("eff_a8", rule_priority=0),
                EffectId("eff_a9"): _decision(
                    "eff_a9", rule_priority=None, reason_code="no_matching_rule"
                ),
            },
        )
        resolution = AuthorityPriorityStrategy().resolve(_pair_group(e0, e1), ctx)
        assert resolution is not None
        assert resolution.accepted == (EffectId("eff_a8"),)
        assert resolution.dropped == (EffectId("eff_a9"),)

    def test_three_way_unique_max_wins(self):
        a = _entity_effect(effect_id="eff_b0", field_path="hp")
        b = _entity_effect(effect_id="eff_b1")
        c = _entity_effect(effect_id="eff_b2", field_path="max_hp")
        ctx = _ctx(
            [a, b, c],
            authority_decisions={
                EffectId("eff_b0"): _decision("eff_b0", rule_priority=1),
                EffectId("eff_b1"): _decision("eff_b1", rule_priority=7),
                EffectId("eff_b2"): _decision("eff_b2", rule_priority=2),
            },
        )
        groups = detect_conflicts([a, b, c])
        resolution = AuthorityPriorityStrategy().resolve(groups[0], ctx)
        assert resolution is not None
        assert resolution.accepted == (EffectId("eff_b1"),)
        assert resolution.dropped == (EffectId("eff_b0"), EffectId("eff_b2"))

    def test_pure_function_repeated_calls_identical(self):
        e0 = _entity_effect(effect_id="eff_b3")
        e1 = _entity_effect(effect_id="eff_b4")
        ctx = _ctx(
            [e0, e1],
            authority_decisions={EffectId("eff_b3"): _decision("eff_b3", rule_priority=9)},
        )
        group = _pair_group(e0, e1)
        first = AuthorityPriorityStrategy().resolve(group, ctx)
        second = AuthorityPriorityStrategy().resolve(group, ctx)
        assert first == second  # 纯函数：同输入同结果（frozen dataclass 语义相等）


class TestTimestampStrategy:
    """策略 2：producer 时间戳（D-P2-16；全员携带 int 时最大者胜）。"""

    def test_all_carry_int_max_wins_last_writer_wins(self):
        e0 = _entity_effect(
            effect_id="eff_t0", metadata={TIMESTAMP_METADATA_KEY: 1000}
        )
        e1 = _entity_effect(effect_id="eff_t1", metadata={TIMESTAMP_METADATA_KEY: 2000})
        ctx = _ctx([e0, e1])
        resolution = TimestampStrategy().resolve(_pair_group(e0, e1), ctx)
        assert resolution is not None
        assert resolution.strategy == "timestamp"
        assert resolution.accepted == (EffectId("eff_t1"),)
        assert resolution.dropped == (EffectId("eff_t0"),)
        assert "producer_timestamp_ms=2000" in resolution.reason

    def test_any_member_missing_key_abstains(self):
        e0 = _entity_effect(effect_id="eff_t2", metadata={TIMESTAMP_METADATA_KEY: 1000})
        e1 = _entity_effect(effect_id="eff_t3")
        ctx = _ctx([e0, e1])
        assert TimestampStrategy().resolve(_pair_group(e0, e1), ctx) is None

    @pytest.mark.parametrize("bad_value", ["1000", 1000.5, True, None, [1000]])
    def test_non_int_value_abstains(self, bad_value):
        e0 = _entity_effect(effect_id="eff_t4", metadata={TIMESTAMP_METADATA_KEY: bad_value})
        e1 = _entity_effect(effect_id="eff_t5", metadata={TIMESTAMP_METADATA_KEY: 2000})
        ctx = _ctx([e0, e1])
        assert TimestampStrategy().resolve(_pair_group(e0, e1), ctx) is None

    def test_tie_abstains(self):
        e0 = _entity_effect(effect_id="eff_t6", metadata={TIMESTAMP_METADATA_KEY: 500})
        e1 = _entity_effect(effect_id="eff_t7", metadata={TIMESTAMP_METADATA_KEY: 500})
        ctx = _ctx([e0, e1])
        assert TimestampStrategy().resolve(_pair_group(e0, e1), ctx) is None

    def test_three_way_unique_max_wins(self):
        a = _entity_effect(effect_id="eff_t8", field_path="hp", metadata={TIMESTAMP_METADATA_KEY: 10})
        b = _entity_effect(effect_id="eff_t9", metadata={TIMESTAMP_METADATA_KEY: 30})
        c = _entity_effect(
            effect_id="eff_t10", field_path="max_hp", metadata={TIMESTAMP_METADATA_KEY: 20}
        )
        ctx = _ctx([a, b, c])
        groups = detect_conflicts([a, b, c])
        resolution = TimestampStrategy().resolve(groups[0], ctx)
        assert resolution is not None
        assert resolution.accepted == (EffectId("eff_t9"),)
        assert resolution.dropped == (EffectId("eff_t8"), EffectId("eff_t10"))


class TestProducerPriorityStrategy:
    """策略 3：producer 优先级（并列比 hint，None 视 0）。"""

    def test_highest_producer_priority_wins(self):
        e0 = _entity_effect(effect_id="eff_p0", source="rule.p_a")
        e1 = _entity_effect(effect_id="eff_p1", source="rule.p_b")
        ctx = _ctx(
            [e0, e1], producer_registry=_registry({"rule.p_a": 10, "rule.p_b": 20})
        )
        resolution = ProducerPriorityStrategy().resolve(_pair_group(e0, e1), ctx)
        assert resolution is not None
        assert resolution.strategy == "producer_priority"
        assert resolution.accepted == (EffectId("eff_p1"),)
        assert resolution.dropped == (EffectId("eff_p0"),)
        assert "producer_priority=20" in resolution.reason

    def test_tie_broken_by_priority_hint(self):
        e0 = _entity_effect(effect_id="eff_p2", source="rule.p_a", priority_hint=2)
        e1 = _entity_effect(effect_id="eff_p3", source="rule.p_b", priority_hint=None)
        ctx = _ctx([e0, e1], producer_registry=_registry({"rule.p_a": 5, "rule.p_b": 5}))
        resolution = ProducerPriorityStrategy().resolve(_pair_group(e0, e1), ctx)
        assert resolution is not None
        assert resolution.accepted == (EffectId("eff_p2"),)
        assert "hint=2" in resolution.reason

    def test_tie_including_hint_abstains(self):
        e0 = _entity_effect(effect_id="eff_p4", source="rule.p_a", priority_hint=3)
        e1 = _entity_effect(effect_id="eff_p5", source="rule.p_b", priority_hint=3)
        ctx = _ctx([e0, e1], producer_registry=_registry({"rule.p_a": 5, "rule.p_b": 5}))
        assert ProducerPriorityStrategy().resolve(_pair_group(e0, e1), ctx) is None

    def test_no_registry_abstains(self):
        e0 = _entity_effect(effect_id="eff_p6")
        e1 = _entity_effect(effect_id="eff_p7")
        ctx = _ctx([e0, e1])
        assert ProducerPriorityStrategy().resolve(_pair_group(e0, e1), ctx) is None

    def test_unregistered_producer_scores_zero(self):
        # 未注册 producer 经 priority_of 缺省纪律归 0：注册者（5）胜
        e0 = _entity_effect(effect_id="eff_p8", source="rule.p_a")
        e1 = _entity_effect(effect_id="eff_p9", source="policy.stranger")
        ctx = _ctx([e0, e1], producer_registry=_registry({"rule.p_a": 5}))
        resolution = ProducerPriorityStrategy().resolve(_pair_group(e0, e1), ctx)
        assert resolution is not None
        assert resolution.accepted == (EffectId("eff_p8"),)

    def test_both_unregistered_tie_abstains(self):
        e0 = _entity_effect(effect_id="eff_p10", source="policy.s_a")
        e1 = _entity_effect(effect_id="eff_p11", source="policy.s_b")
        ctx = _ctx([e0, e1], producer_registry=_registry({"rule.p_a": 9}))
        assert ProducerPriorityStrategy().resolve(_pair_group(e0, e1), ctx) is None


class TestEntityFifoStrategy:
    """策略 4：到达序 FIFO（先至先赢；永不弃权）。"""

    def test_earliest_arrival_wins(self):
        e0 = _entity_effect(effect_id="eff_f0")
        e1 = _entity_effect(effect_id="eff_f1")
        ctx = _ctx([e0, e1])
        resolution = EntityFifoStrategy().resolve(_pair_group(e0, e1), ctx)
        assert resolution is not None
        assert resolution.strategy == "entity_fifo"
        assert resolution.accepted == (EffectId("eff_f0"),)
        assert resolution.dropped == (EffectId("eff_f1"),)
        assert "arrival=0" in resolution.reason

    def test_never_abstains_even_without_any_other_input(self):
        e0 = _entity_effect(effect_id="eff_f2")
        e1 = _entity_effect(effect_id="eff_f3")
        ctx = _ctx([e0, e1])
        for _ in range(3):
            assert EntityFifoStrategy().resolve(_pair_group(e0, e1), ctx) is not None

    def test_missing_arrival_never_wins_defensive(self):
        # 防御路径：arrival 缺失 → +inf 永不胜出（resolve_all 入口强制全覆盖，
        # 直接构造部分 arrival 的 ctx 验证策略层行为）
        e0 = _entity_effect(effect_id="eff_f4")
        e1 = _entity_effect(effect_id="eff_f5")
        ctx = ResolutionContext(arrival={EffectId("eff_f5"): 0})
        resolution = EntityFifoStrategy().resolve(_pair_group(e0, e1), ctx)
        assert resolution is not None
        assert resolution.accepted == (EffectId("eff_f5"),)
        assert resolution.dropped == (EffectId("eff_f4"),)

    def test_three_way_earliest_wins(self):
        a = _entity_effect(effect_id="eff_f6", field_path="hp")
        b = _entity_effect(effect_id="eff_f7")
        c = _entity_effect(effect_id="eff_f8", field_path="max_hp")
        ctx = _ctx([a, b, c])
        groups = detect_conflicts([a, b, c])
        resolution = EntityFifoStrategy().resolve(groups[0], ctx)
        assert resolution is not None
        assert resolution.accepted == (EffectId("eff_f6"),)
        assert resolution.dropped == (EffectId("eff_f7"), EffectId("eff_f8"))


# —— 4. DefaultConflictResolver 策略链（§5.3/§5.4/§5.5）——


class _StubMergeStrategy:
    """§5.5 扩展位桩策略：恒产 MERGE（不引入真实域语义，仅机制正确性）。"""

    name = "stub_merge"

    def resolve(self, group: ConflictGroup, ctx: ResolutionContext) -> ConflictResolution | None:
        return ConflictResolution(
            action=ConflictAction.MERGE,
            strategy=self.name,
            accepted=tuple(effect.effect_id for effect in group.effects),
            dropped=(),
            reason="桩策略：合并（机制正确性覆盖）",
        )


class _StubDeferStrategy:
    """§5.5 扩展位桩策略：恒产 DEFER（管道语义：被 defer 者作下一回合提案）。"""

    name = "stub_defer"

    def resolve(self, group: ConflictGroup, ctx: ResolutionContext) -> ConflictResolution | None:
        return ConflictResolution(
            action=ConflictAction.DEFER,
            strategy=self.name,
            accepted=tuple(effect.effect_id for effect in group.effects),
            dropped=(),
            reason="桩策略：顺延至下一回合（机制正确性覆盖）",
        )


class _AlwaysAbstainStrategy:
    """恒弃权桩策略（触发解析器保守 REJECT 兜底路径）。"""

    name = "stub_abstain"

    def resolve(self, group: ConflictGroup, ctx: ResolutionContext) -> ConflictResolution | None:
        return None


class TestDefaultConflictResolverChain:
    """策略链：四策顺序接力 + 保守 REJECT 兜底 + 扩展位透传。"""

    def test_default_strategies_tuple_order(self):
        assert [s.name for s in DEFAULT_STRATEGIES] == [
            "authority_priority",
            "timestamp",
            "producer_priority",
            "entity_fifo",
        ]
        resolver = DefaultConflictResolver()
        assert resolver.strategies == DEFAULT_STRATEGIES

    def test_authority_decides_first_chain(self):
        # authority（5>3）拍板 e0——尽管 timestamp/producer 都会选 e1、
        # fifo 也选 e0：拍板者只能是 authority（证明求值序第一策）
        e0 = _entity_effect(effect_id="eff_ch0", source="rule.p_a", priority_hint=1)
        e1 = _entity_effect(effect_id="eff_ch1", source="rule.p_b")
        ctx = _ctx(
            [e0, e1],
            authority_decisions={
                EffectId("eff_ch0"): _decision("eff_ch0", rule_priority=5),
                EffectId("eff_ch1"): _decision("eff_ch1", rule_priority=3),
            },
            producer_registry=_registry({"rule.p_a": 10, "rule.p_b": 20}),
        )
        e0.metadata[TIMESTAMP_METADATA_KEY] = 1000
        e1.metadata[TIMESTAMP_METADATA_KEY] = 2000
        resolution = DefaultConflictResolver().resolve_group(_pair_group(e0, e1), ctx)
        assert resolution.strategy == "authority_priority"
        assert resolution.accepted == (EffectId("eff_ch0"),)

    def test_chain_falls_through_to_timestamp(self):
        # 无 authority decisions → timestamp 拍板 e1（2000>1000）——尽管
        # producer（20>10）与 fifo 都会选 e0：拍板者只能是 timestamp
        e0 = _entity_effect(
            effect_id="eff_ch2", source="rule.p_a", metadata={TIMESTAMP_METADATA_KEY: 1000}
        )
        e1 = _entity_effect(
            effect_id="eff_ch3", source="rule.p_b", metadata={TIMESTAMP_METADATA_KEY: 2000}
        )
        ctx = _ctx([e0, e1], producer_registry=_registry({"rule.p_a": 10, "rule.p_b": 20}))
        resolution = DefaultConflictResolver().resolve_group(_pair_group(e0, e1), ctx)
        assert resolution.strategy == "timestamp"
        assert resolution.accepted == (EffectId("eff_ch3"),)

    def test_chain_falls_through_to_producer(self):
        # authority 弃权（无 decisions）+ timestamp 弃权（e1 缺键）→
        # producer 拍板 e0（10>20 的反例：设 p_a=20 > p_b=10）
        e0 = _entity_effect(
            effect_id="eff_ch4", source="rule.p_a", metadata={TIMESTAMP_METADATA_KEY: 1000}
        )
        e1 = _entity_effect(effect_id="eff_ch5", source="rule.p_b")
        ctx = _ctx([e0, e1], producer_registry=_registry({"rule.p_a": 20, "rule.p_b": 10}))
        resolution = DefaultConflictResolver().resolve_group(_pair_group(e0, e1), ctx)
        assert resolution.strategy == "producer_priority"
        assert resolution.accepted == (EffectId("eff_ch4"),)

    def test_chain_falls_through_to_fifo(self):
        # authority/timestamp/producer 全弃权（ts 并列 + registry 并列 +
        # hint 并列）→ fifo 兜底：到达序最早者胜
        e0 = _entity_effect(
            effect_id="eff_ch6",
            source="rule.p_a",
            priority_hint=1,
            metadata={TIMESTAMP_METADATA_KEY: 700},
        )
        e1 = _entity_effect(
            effect_id="eff_ch7",
            source="rule.p_b",
            priority_hint=1,
            metadata={TIMESTAMP_METADATA_KEY: 700},
        )
        ctx = _ctx([e0, e1], producer_registry=_registry({"rule.p_a": 4, "rule.p_b": 4}))
        resolution = DefaultConflictResolver().resolve_group(_pair_group(e0, e1), ctx)
        assert resolution.strategy == "entity_fifo"
        assert resolution.accepted == (EffectId("eff_ch6"),)
        assert resolution.dropped == (EffectId("eff_ch7"),)

    def test_fifo_respects_reversed_arrival(self):
        # 到达序反转（e1 先到）→ fifo 改判 e1（权威序 = 到达序，非 ID 序）
        e1 = _entity_effect(effect_id="eff_ch8")
        e0 = _entity_effect(effect_id="eff_ch9")
        ctx = _ctx([e1, e0])
        resolution = DefaultConflictResolver().resolve_group(_pair_group(e1, e0), ctx)
        assert resolution.strategy == "entity_fifo"
        assert resolution.accepted == (EffectId("eff_ch8"),)

    def test_all_abstain_conservative_reject(self):
        # 空策略链 → 全策略弃权（理论不可达路径）→ 保守 REJECT 全组
        e0 = _entity_effect(effect_id="eff_r0")
        e1 = _entity_effect(effect_id="eff_r1")
        ctx = _ctx([e0, e1])
        resolution = DefaultConflictResolver(strategies=()).resolve_group(
            _pair_group(e0, e1), ctx
        )
        assert resolution.action is ConflictAction.REJECT
        assert resolution.strategy == "fallback"
        assert resolution.accepted == ()
        assert resolution.dropped == (EffectId("eff_r0"), EffectId("eff_r1"))
        assert "全部策略弃权" in resolution.reason

    def test_all_abstain_conservative_reject_with_abstaining_strategy(self):
        e0 = _entity_effect(effect_id="eff_r2")
        e1 = _entity_effect(effect_id="eff_r3")
        ctx = _ctx([e0, e1])
        resolution = DefaultConflictResolver(
            strategies=(_AlwaysAbstainStrategy(),)
        ).resolve_group(_pair_group(e0, e1), ctx)
        assert resolution.action is ConflictAction.REJECT
        assert resolution.accepted == ()
        assert resolution.dropped == (EffectId("eff_r2"), EffectId("eff_r3"))

    def test_stub_merge_strategy_passthrough(self):
        # §5.5 扩展位：域解析器产 MERGE → 解析器透传不裁剪
        e0 = _entity_effect(effect_id="eff_m0")
        e1 = _entity_effect(effect_id="eff_m1")
        ctx = _ctx([e0, e1])
        resolution = DefaultConflictResolver(
            strategies=(_StubMergeStrategy(),)
        ).resolve_group(_pair_group(e0, e1), ctx)
        assert resolution.action is ConflictAction.MERGE
        assert resolution.strategy == "stub_merge"
        assert resolution.accepted == (EffectId("eff_m0"), EffectId("eff_m1"))
        assert resolution.dropped == ()

    def test_stub_defer_strategy_passthrough(self):
        # §5.5：DEFER 管道语义的机制正确性（被 defer 者作下一回合提案归
        # cascade 层；本层只验证解析器对域解析器产物的透传）
        e0 = _entity_effect(effect_id="eff_d0")
        e1 = _entity_effect(effect_id="eff_d1")
        ctx = _ctx([e0, e1])
        resolution = DefaultConflictResolver(
            strategies=(_StubDeferStrategy(),)
        ).resolve_group(_pair_group(e0, e1), ctx)
        assert resolution.action is ConflictAction.DEFER
        assert resolution.strategy == "stub_defer"
        assert resolution.accepted == (EffectId("eff_d0"), EffectId("eff_d1"))

    def test_custom_strategy_order_precedes_defaults(self):
        # 自定义链：fifo 放第一 → 即便 authority 可拍板也用 fifo（链序即
        # 求值序，strategies 参数完全定制）
        e0 = _entity_effect(effect_id="eff_o0", source="rule.p_a")
        e1 = _entity_effect(effect_id="eff_o1", source="rule.p_b")
        ctx = _ctx(
            [e0, e1],
            authority_decisions={
                EffectId("eff_o0"): _decision("eff_o0", rule_priority=5),
                EffectId("eff_o1"): _decision("eff_o1", rule_priority=3),
            },
        )
        resolution = DefaultConflictResolver(
            strategies=(EntityFifoStrategy(), AuthorityPriorityStrategy())
        ).resolve_group(_pair_group(e0, e1), ctx)
        assert resolution.strategy == "entity_fifo"

    def test_domain_resolver_factory_alias_shape(self):
        # §5.5 注入点类型：Callable[[ConflictGroup, ResolutionContext],
        # ConflictStrategy | None]（P2 不内置任何域解析器，仅类型在位）。
        # 按结构断言（origin/args），不依赖 typing 对象身份。
        import collections.abc
        import typing

        origin = typing.get_origin(DomainResolverFactory)
        args = typing.get_args(DomainResolverFactory)
        assert origin is collections.abc.Callable
        assert list(args[0]) == [ConflictGroup, ResolutionContext]
        assert args[1] == (ConflictStrategy | None)

    def test_single_element_group_raises_conflict_error(self):
        e0 = _entity_effect(effect_id="eff_g0")
        group = ConflictGroup(effects=(e0,), keys=())
        with pytest.raises(ConflictError):
            DefaultConflictResolver().resolve_group(group, _ctx([e0]))

    def test_non_conflict_group_raises_conflict_error(self):
        with pytest.raises(ConflictError):
            DefaultConflictResolver().resolve_group(
                "not a group",  # type: ignore[arg-type]
                ResolutionContext(arrival={}),
            )


# —— 5. ConflictResolutionReport 与批级入口（任务包目标 3）——


class TestConflictResolutionReport:
    """resolve_all 批级装配：直通 / accepted / dropped / 输入守卫。"""

    def test_mixed_batch_report_in_arrival_order(self):
        # 批：[冲突对(e0 胜 e1) + 直通 e2 + 冲突对(e3 胜 e4)]
        # authority 拍板：e0/e3 的 rule_priority 更高
        e0 = _entity_effect(effect_id="eff_rp0", source="rule.p_a")
        e1 = _entity_effect(effect_id="eff_rp1", source="rule.p_b")
        e2 = _entity_effect(effect_id="eff_rp2", entity_id="ent_rp_lone")
        e3 = _entity_effect(effect_id="eff_rp3", entity_id="ent_rp_y", source="rule.p_a")
        e4 = _entity_effect(effect_id="eff_rp4", entity_id="ent_rp_y", source="rule.p_b")
        effects = [e0, e1, e2, e3, e4]
        ctx = _ctx(
            effects,
            authority_decisions={
                EffectId("eff_rp0"): _decision("eff_rp0", rule_priority=9),
                EffectId("eff_rp1"): _decision("eff_rp1", rule_priority=1),
                EffectId("eff_rp3"): _decision("eff_rp3", rule_priority=9),
                EffectId("eff_rp4"): _decision("eff_rp4", rule_priority=1),
            },
        )
        report = DefaultConflictResolver().resolve_all(effects, ctx)
        assert type(report) is ConflictResolutionReport
        assert report.has_conflicts
        assert len(report.resolutions) == 2
        assert all(r.strategy == "authority_priority" for r in report.resolutions)
        assert report.accepted == (
            EffectId("eff_rp0"),
            EffectId("eff_rp2"),  # 直通夹在两组之间
            EffectId("eff_rp3"),
        )
        assert report.dropped == (EffectId("eff_rp1"), EffectId("eff_rp4"))

    def test_no_conflict_batch_all_passthrough(self):
        e0 = _entity_effect(effect_id="eff_n0", entity_id="ent_n0")
        e1 = _domain_effect(effect_id="eff_n1", domain="scenario")
        ctx = _ctx([e0, e1])
        report = DefaultConflictResolver().resolve_all([e0, e1], ctx)
        assert report.resolutions == ()
        assert not report.has_conflicts
        assert report.accepted == (EffectId("eff_n0"), EffectId("eff_n1"))
        assert report.dropped == ()

    def test_staged_create_plus_init_component_both_accepted(self):
        # P2-REMEDIATION B1 批级口径：create + 初始化 set_component 全部
        # 直通（无 resolution、零 dropped），交由 reducer 暂存顺序应用
        e0 = _entity_effect(
            effect_id="eff_sd0", effect_type="core.create_entity", entity_id="ent_sd"
        )
        e1 = _entity_effect(
            effect_id="eff_sd1", entity_id="ent_sd", component_type="space.position"
        )
        e2 = _entity_effect(
            effect_id="eff_sd2", entity_id="ent_sd", component_type="attrs.hp"
        )
        ctx = _ctx([e0, e1, e2])
        report = DefaultConflictResolver().resolve_all([e0, e1, e2], ctx)
        assert report.resolutions == ()
        assert not report.has_conflicts
        assert report.accepted == (
            EffectId("eff_sd0"),
            EffectId("eff_sd1"),
            EffectId("eff_sd2"),
        )
        assert report.dropped == ()

    def test_resolution_for_membership(self):
        e0 = _entity_effect(effect_id="eff_rf0", source="rule.p_a")
        e1 = _entity_effect(effect_id="eff_rf1", source="rule.p_b")
        e2 = _entity_effect(effect_id="eff_rf2", entity_id="ent_rf_lone")
        ctx = _ctx(
            [e0, e1, e2],
            authority_decisions={
                EffectId("eff_rf0"): _decision("eff_rf0", rule_priority=5),
                EffectId("eff_rf1"): _decision("eff_rf1", rule_priority=2),
            },
        )
        report = DefaultConflictResolver().resolve_all([e0, e1, e2], ctx)
        assert report.resolution_for(EffectId("eff_rf0")) is report.resolutions[0]
        assert report.resolution_for(EffectId("eff_rf1")) is report.resolutions[0]
        assert report.resolution_for(EffectId("eff_rf2")) is None

    def test_duplicate_effect_id_raises_conflict_error(self):
        e0 = _entity_effect(effect_id="eff_dup0")
        e1 = _entity_effect(effect_id="eff_dup0", field_path="hp")
        ctx = _ctx([e0, e1])
        with pytest.raises(ConflictError, match="重复 effect_id"):
            DefaultConflictResolver().resolve_all([e0, e1], ctx)

    def test_arrival_coverage_guard_raises_conflict_error(self):
        e0 = _entity_effect(effect_id="eff_cov0")
        e1 = _entity_effect(effect_id="eff_cov1")
        ctx = ResolutionContext(arrival={EffectId("eff_cov0"): 0})  # 未覆盖 e1
        with pytest.raises(ConflictError, match="未覆盖"):
            DefaultConflictResolver().resolve_all([e0, e1], ctx)

    def test_conservative_reject_flows_into_report(self):
        e0 = _entity_effect(effect_id="eff_cr0")
        e1 = _entity_effect(effect_id="eff_cr1")
        e2 = _entity_effect(effect_id="eff_cr2", entity_id="ent_cr_lone")
        ctx = _ctx([e0, e1, e2])
        report = DefaultConflictResolver(strategies=()).resolve_all([e0, e1, e2], ctx)
        assert len(report.resolutions) == 1
        assert report.resolutions[0].action is ConflictAction.REJECT
        assert report.accepted == (EffectId("eff_cr2"),)
        assert report.dropped == (EffectId("eff_cr0"), EffectId("eff_cr1"))

    def test_resolve_conflicts_facade_matches_resolver(self):
        e0 = _entity_effect(effect_id="eff_fc0", source="rule.p_a")
        e1 = _entity_effect(effect_id="eff_fc1", source="rule.p_b")
        ctx = _ctx(
            [e0, e1],
            authority_decisions={
                EffectId("eff_fc0"): _decision("eff_fc0", rule_priority=6),
                EffectId("eff_fc1"): _decision("eff_fc1", rule_priority=4),
            },
        )
        via_facade = resolve_conflicts([e0, e1], ctx)
        via_resolver = DefaultConflictResolver().resolve_all([e0, e1], ctx)
        assert via_facade == via_resolver
        # 自定义解析器经门面透传
        via_custom = resolve_conflicts(
            [e0, e1], ctx, resolver=DefaultConflictResolver(strategies=(EntityFifoStrategy(),))
        )
        assert via_custom.resolutions[0].strategy == "entity_fifo"

    def test_determinism_repeated_resolve_all(self):
        e0 = _entity_effect(effect_id="eff_det0", metadata={TIMESTAMP_METADATA_KEY: 111})
        e1 = _entity_effect(effect_id="eff_det1", metadata={TIMESTAMP_METADATA_KEY: 222})
        e2 = _entity_effect(effect_id="eff_det2", entity_id="ent_det_lone")
        ctx = _ctx([e0, e1, e2])
        first = DefaultConflictResolver().resolve_all([e0, e1, e2], ctx)
        second = DefaultConflictResolver().resolve_all([e0, e1, e2], ctx)
        assert first == second

    def test_report_is_frozen_dataclass(self):
        assert is_dataclass(ConflictResolutionReport)
        assert dataclasses.is_dataclass(ConflictResolutionReport)
        e0 = _entity_effect(effect_id="eff_fr0")
        e1 = _entity_effect(effect_id="eff_fr1")
        ctx = _ctx([e0, e1])
        report = DefaultConflictResolver().resolve_all([e0, e1], ctx)
        with pytest.raises(FrozenInstanceError):
            report.accepted = ()  # type: ignore[misc]


# —— 6. Trace 协同（§9）——


class TestTracePayload:
    """to_trace_payload：P1 冻结三键 + decision 词表 + 策略名 detail。"""

    def test_payload_keys_exactly_decision_payload_keys(self):
        e0 = _entity_effect(effect_id="eff_tr0", source="rule.p_a")
        e1 = _entity_effect(effect_id="eff_tr1", source="rule.p_b")
        ctx = _ctx(
            [e0, e1],
            authority_decisions={EffectId("eff_tr0"): _decision("eff_tr0", rule_priority=5)},
        )
        resolution = DefaultConflictResolver().resolve_group(_pair_group(e0, e1), ctx)
        payload = resolution.to_trace_payload()
        assert set(payload) == set(DECISION_PAYLOAD_KEYS)
        assert set(payload) == {"effect_id", "decision", "reason"}

    def test_winner_payload_shape(self):
        e0 = _entity_effect(effect_id="eff_tr2", source="rule.p_a")
        e1 = _entity_effect(effect_id="eff_tr3", source="rule.p_b")
        ctx = _ctx(
            [e0, e1],
            authority_decisions={EffectId("eff_tr2"): _decision("eff_tr2", rule_priority=5)},
        )
        resolution = DefaultConflictResolver().resolve_group(_pair_group(e0, e1), ctx)
        payload = resolution.to_trace_payload()
        assert payload["effect_id"] == "eff_tr2"  # 唯一胜者
        assert payload["decision"] == "winner"
        assert payload["reason"].startswith("authority_priority:")
        assert "rule_priority=5" in payload["reason"]
        assert all(isinstance(value, str) for value in payload.values())

    def test_reject_payload_group_member_string(self):
        e0 = _entity_effect(effect_id="eff_tr4")
        e1 = _entity_effect(effect_id="eff_tr5")
        ctx = _ctx([e0, e1])
        resolution = DefaultConflictResolver(strategies=()).resolve_group(
            _pair_group(e0, e1), ctx
        )
        payload = resolution.to_trace_payload()
        assert payload["effect_id"] == "eff_tr4;eff_tr5"  # 组成员串（到达序）
        assert payload["decision"] == "reject"
        assert payload["reason"].startswith("fallback:")

    def test_payload_deterministic_no_id_generation(self):
        e0 = _entity_effect(effect_id="eff_tr6")
        e1 = _entity_effect(effect_id="eff_tr7")
        ctx = _ctx([e0, e1])
        first = DefaultConflictResolver().resolve_group(_pair_group(e0, e1), ctx)
        second = DefaultConflictResolver().resolve_group(_pair_group(e0, e1), ctx)
        assert first.to_trace_payload() == second.to_trace_payload()

    def test_str_enum_values_match_spec19_vocabulary(self):
        assert ConflictAction.WINNER.value == "winner"
        assert ConflictAction.MERGE.value == "merge"
        assert ConflictAction.DEFER.value == "defer"
        assert ConflictAction.REJECT.value == "reject"
        assert ConflictAction.REPAIR.value == "repair"
        assert isinstance(ConflictAction.WINNER, str)


# —— 7. 导出集成（D-P2-19 / §10.3）——


class TestPackageReexportIntegration:
    """包级 re-export 与模块定义同一对象（closeout 机械化口径的模块侧印证）。"""

    def test_all_module_exports_reexported_from_package(self):
        for name in conflicts_mod.__all__:
            assert name in core_pkg.__all__, f"{name} 未进入包 __all__"
            assert getattr(core_pkg, name) is getattr(conflicts_mod, name), (
                f"{name}：包级 re-export 与 conflicts 模块定义不是同一对象"
            )

    def test_no_submodule_name_collision(self):
        # closeout 同名遮蔽豁免集必须恒为 {'snapshot'}（本模块导出不得撞
        # 子模块名）
        assert not (set(conflicts_mod.__all__) & {"conflicts"})

    def test_public_surface_covers_task_package_targets(self):
        # 任务包 P2-T05 目标 1–3 的表面齐备性
        expected = {
            "extract_effect_locks",  # 目标 1：锁提取
            "detect_conflicts",  # 目标 1：连通分量分组
            "ConflictKey",
            "ConflictGroup",
            "conflict_key",
            "conflicts_with",
            "DefaultConflictResolver",  # 目标 2：策略链
            "ConflictStrategy",
            "ConflictAction",
            "ConflictResolution",
            "ResolutionContext",
            "AuthorityPriorityStrategy",  # 目标 2：四策
            "TimestampStrategy",
            "ProducerPriorityStrategy",
            "EntityFifoStrategy",
            "DEFAULT_STRATEGIES",
            "TIMESTAMP_METADATA_KEY",
            "ConflictResolutionReport",  # 目标 3
            "resolve_conflicts",
            "DomainResolverFactory",
        }
        assert expected <= set(conflicts_mod.__all__)

    def test_context_and_resolution_are_frozen_dataclasses(self):
        for cls in (ConflictGroup, ConflictResolution, ResolutionContext):
            assert is_dataclass(cls)
        ctx = ResolutionContext(arrival={})
        with pytest.raises(FrozenInstanceError):
            ctx.arrival = {EffectId("eff_x"): 0}  # type: ignore[misc]
        resolution = ConflictResolution(
            action=ConflictAction.WINNER,
            strategy="entity_fifo",
            accepted=(EffectId("eff_x"),),
            dropped=(),
            reason="测试",
        )
        with pytest.raises(FrozenInstanceError):
            resolution.reason = "篡改"  # type: ignore[misc]
