"""P2-T09 Adversarial Test Suite 对抗性测试套件。

严格覆盖 P2 设计规范 §11、Plan §11 必须测试 7 条与 G2 静态确认要求：

1. **场景 1（越权写入被拒 / 必须测试 1）**：
   policy 仅授权 rule.lock_system 写 door.lock_state 组件域；
   攻击提案分别来自：
   (a) 未授权 producer policy.alice；
   (b) 完全未注册 producer llm.narrator；
   (c) 携带 authority_scope="door.lock_state" 伪造声明的未授权 producer（D-P2-17）；
   (d) 无匹配规则（空白 policy）。
   断言：check_authority 全部 deny（rule_deny / no_matching_rule）；
   CascadeExecutor.run 后 final_state == 初始 state、revision 不变、零 COMMITTED 事务；
   trace 含 AUTHORITY_DECISION(deny) 逐条记录。

2. **场景 2（双写冲突仲裁 / 必须测试 2）**：
   Spec §19 原型 Move(gem, floor) vs Move(gem, alice_inventory) 结构化等价物；
   两个均被授权的 producer 对同一 (ent_gem, space.position) 提 core.set_component；
   (a) 三写同址成组；
   (b) 同组件不同 field_path 的两个字段级效果不成组；
   (c) 整组件效果 vs 字段效果成组。
   断言：detect_conflicts 分组正确；DefaultConflictResolver 给出唯一 WINNER 可解释
   （strategy 名 + reason 入 trace CONFLICT_RESOLUTION）；
   固定输入下 winner 确定（逐策略构造：authority rule_priority 差、
   metadata 时间戳全带/部分带、producer priority、到达序兜底各一例）；败者不落状态。

3. **场景 3（无效效果原子失败 / 必须测试 3）**：
   (a) L2 终检路径——批次内一条 effect 指向 missing entity（以 commit_transaction 直接装配）；
   (b) reducer 应用路径——同事务 seq0 core.remove_entity(X) + seq1 对 X core.set_component；
   (c) stale 批次（base_revision 落后于 state）。
   断言：返回 (base_state 原样, ABORTED 事务, [])；commit_revision is None、effects == []；
   revision 不变；trace 含 ABORTED 事务记录；部分提交在任何断言面不可观测。

4. **场景 4（原子提交与 Revision 单调递增 / 必须测试 4）**：
   (a) N=5 效果单事务；
   (b) 三级级联（触发器链产生 3 个回合）；
   (c) 一次 ABORTED；
   (d) 空 accepted 回合（authority 全拒后管道空转）。
   断言：(a) revision 恰 +1；(b) revision 恰 +3 且各事务 commit_revision 连续递增；
   (c)(d) revision +0；任何路径不出现 +2/跳号（对全部 transactions 程序化断言
   commit_revision == base_revision + 1）。

5. **场景 5（循环事件级联熔断 / 必须测试 6）**：
   构造 A -> B -> A 循环触发器与位置重访，HP changed -> set HP -> HP changed；
   CycleDetector 在 depth 1 即丢弃回环提案，诊断 cycle_detected 含祖先深度与位置链；
   级联正常收敛（无死循环、无异常）；深度上限触发（depth > 8 -> 在 depth 9 启动前停，
   诊断 cascade_depth_exceeded，至多 9 个 COMMITTED）；全部事件 cascade_id/root 一致、depth 单调。

6. **场景 6（写屏障拦截与零公共写入绕过 / 必须测试 7）**：
   (1) 屏障武装态下 state.model_copy(update={"world_revision": 99}) -> WriteBarrierError；
       Transaction.model_construct(...) -> WriteBarrierError；
       copy.copy(state) / copy.deepcopy(state) -> WriteBarrierError；
       write_barrier_exempt() 内四者放行；
   (2) guard(state) 包装器：4 个只读门面 + model_dump 可用；
       model_copy / model_construct / 属性赋值 / _with_* 访问全部 WriteBarrierError；
       **容器级原地修改攻击**（P2-REMEDIATION B2）：guard(state).world_variables /
       entities / scenario_state.data / 嵌套组件 dict 的 __setitem__ / __delitem__ /
       clear / pop / popitem / setdefault / update 全部 TypeError，权威状态零变化；
       **私有槽 / mangled 名向量**（P2-REMEDIATION G2 补充轮 1）：
       getattr(g, "_GuardedWorldState__wrapped") 与实体 / scenario 门面同类槽
       确定性 WriteBarrierError、不返回活权威状态；object.__getattribute__ /
       vars() / type.__dict__ 内省 / __slots__ 扫描均无活 WorldState 引用
       （含闭包单元深度）；实例只持 int token（模块私有注册表承载状态）；
       经任何可达路径对权威状态的原地容器写入全部拦截且 revision/内容不变；
       视图 copy / deepcopy 仍返回独立可变快照（回归）；
   (3) 静态审计自测：合成违规源码字符串全部被捕获；reducer.py 自身白名单放行；
   (4) 管道面：触发器收到的是 GuardedWorldState（isinstance 断言 + 写路径抛错）；
   (5) uninstall_write_barrier() 后 P1 语义复原。

7. **场景 7（事件来源与因果溯源 K6 + ID 义务 / 必须测试 5）**：
   (1) 提交后每个事件携带 transaction_id、source_system == effect.source、
       cause_ids 含 CauseRef(EFFECT, effect_id)、world_revision == commit_revision（K6 六要素）；
   (2) 跨种类 ID 攻击：EffectId 值写入 target.entity_id、"evt_x" 串写入 effect_id、
       INTERVENTION cause 携带非 trc_ ref_id -> validation bad_id_kind 拒绝；
   (3) 未注册 effect_type（语义型且无 handler）-> no_handler 拒绝；直接喂 reducer -> ReducerError；
   (4) 同批重复 effect_id -> duplicated_effect_id 全副本拒绝；
   (5) future_base_revision (base > current) -> 拒绝；
   (6) 开发干预通道：origin=DEVELOPER 经 policy 显式授权后可提交，trace provenance 完整。

8. **场景 8（core.create_entity 提交路径 / P2-REMEDIATION B1）**：
   (1) 单独 create_entity 提交成功（revision 恰 +1、实体落地、事件 1:1）；
   (2) 同事务先 create_entity 后 set_component 的暂存依赖：L2 终检零
       missing_entity、conflicts 不判冲突、reducer 顺序应用落地；
   (3) create 已存在实体 -> reducer 前置条件报错（非 missing_entity）；
   (4) CascadeExecutor 级联端到端：create + component.set 同回合完整通过
       且成功落地；create 事件触发后续回合对新实体的效果落地。

9. **G2 静态代码扫描确认**：
   - 静态扫描整个 src/engine_v2/，断言没有任何直接修改状态的 public API
     （全类口径，reducer.py 白名单——唯一授权变更机制）；
   - **直接下标写入扫描**（P2-REMEDIATION B3）：src/engine_v2/（白名单外）
     不得出现对状态容器属性（entities / world_variables / scenario_state /
     components / data / tags）的任何下标写入/删除；
   - 静态断言 Reducer 纯函数绝不调用 LLM（无 provider/llm import）、不做语义推断。
"""

from __future__ import annotations

import ast
import copy
import pickle
from pathlib import Path
from typing import Any

import pytest

from src.engine_v2.core.authority import (
    AuthorityDecision,
    AuthorityPolicy,
    AuthorityRule,
    AuthoritySelector,
    ProducerInfo,
    ProducerRegistry,
    check_authority,
)
from src.engine_v2.core.cascade import (
    CascadeConfig,
    CascadeExecutor,
    CascadeResult,
    CascadeTriggerRegistry,
    SyncTrigger,
)
from src.engine_v2.core.components import (
    ComponentTypeId,
)
from src.engine_v2.core.conflicts import (
    DefaultConflictResolver,
    ResolutionContext,
    detect_conflicts,
)
from src.engine_v2.core.effects import (
    CommittedEffect,
    EffectTypeId,
    EntityTarget,
    ProposedEffect,
    StateDomainId,
    StateDomainTarget,
)
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.events import DomainEvent
from src.engine_v2.core.ids import (
    CascadeId,
    EffectId,
    EntityId,
    EventId,
    ProducerId,
    TransactionId,
    new_transaction_id,
)
from src.engine_v2.core.provenance import (
    CascadeContext,
    CauseKind,
    CauseRef,
    OriginKind,
    Provenance,
)
import src.engine_v2.core.reducer as reducer
from src.engine_v2.core.reducer import (
    EFFECT_CREATE_ENTITY,
    EFFECT_REMOVE_ENTITY,
    EFFECT_SET_COMPONENT,
    EFFECT_SET_WORLD_VARIABLE,
    GuardedWorldState,
    ReducerError,
    WriteBarrierError,
    apply_transaction,
    default_handler_registry,
    guard,
    install_write_barrier,
    is_guarded,
    uninstall_write_barrier,
    write_barrier_exempt,
    write_barrier_installed,
)
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.state import ScenarioState, WorldState
from src.engine_v2.core.trace import TraceKind
from src.engine_v2.core.transaction import Transaction, TransactionStatus
from src.engine_v2.core.transaction_executor import (
    commit_transaction,
)
from src.engine_v2.core.validation import (
    EffectValidator,
    ValidationContext,
    check_effect_id_kinds,
    check_transaction_references,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
ENGINE_V2_DIR = REPO_ROOT / "src" / "engine_v2"


@pytest.fixture(autouse=True)
def _reset_write_barrier_per_test() -> Any:
    """保证每用例前后全局写屏障复原，测试间互不污染。"""
    uninstall_write_barrier()
    try:
        yield
    finally:
        uninstall_write_barrier()


def _make_base_state(
    rev: int = 0,
    *,
    entities: dict[EntityId, EntityRecord] | None = None,
    world_variables: dict[str, Any] | None = None,
) -> WorldState:
    """辅助创建测试初始状态。"""
    ents = entities if entities is not None else {
        EntityId("ent_alice"): EntityRecord(
            entity_id=EntityId("ent_alice"),
            components={
                ComponentTypeId("space.position"): {"x": 0, "y": 0},
                ComponentTypeId("door.lock_state"): {"locked": True},
                ComponentTypeId("attrs.hp"): {"current": 100, "max": 100},
            },
            entity_class="character",
            tags=["hero"],
        ),
        EntityId("ent_door"): EntityRecord(
            entity_id=EntityId("ent_door"),
            components={
                ComponentTypeId("door.lock_state"): {"locked": True},
            },
            entity_class="prop",
            tags=["interactive"],
        ),
        EntityId("ent_gem"): EntityRecord(
            entity_id=EntityId("ent_gem"),
            components={
                ComponentTypeId("space.position"): {"x": 10, "y": 20},
            },
            entity_class="item",
            tags=["treasure"],
        ),
    }
    wvars = world_variables if world_variables is not None else {}
    return WorldState(
        world_revision=Revision(rev),
        entities=ents,
        world_variables=wvars,
        scenario_state=ScenarioState(),
    )


def _make_proposed_effect(
    effect_id: str,
    effect_type: str,
    target: EntityTarget | StateDomainTarget,
    payload: dict[str, Any],
    *,
    source: str = "rule.system",
    base_revision: int = 0,
    authority_scope: str | None = None,
    cause_ids: list[CauseRef] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ProposedEffect:
    return ProposedEffect(
        effect_id=EffectId(effect_id),
        effect_type=EffectTypeId(effect_type),
        target=target,
        payload=payload,
        source=ProducerId(source),
        base_revision=Revision(base_revision),
        authority_scope=authority_scope,
        cause_ids=cause_ids or [],
        metadata=metadata or {},
    )


# ==============================================================================
# 场景 1: 越权写入被拒 (Plan §11.1 / P2 §11.1)
# ==============================================================================


class TestScenario1AuthorityAdversarial:
    """场景 1（越权写入被拒）：未授权 producer 对 locked/restricted 状态域发起变更，
    经 Authority 严格拦截，产生 DENY trace，世界状态 100% 未突变。
    """

    def test_unauthorized_producers_strict_denial_and_state_immutability(self) -> None:
        state = _make_base_state(0)

        # Policy 仅授权 rule.lock_system 写 door.lock_state 组件域
        policy = AuthorityPolicy(
            rules=[
                AuthorityRule(
                    selector=AuthoritySelector(
                        component_type=ComponentTypeId("door.lock_state"),
                    ),
                    allowed_writers=[ProducerId("rule.lock_system")],
                    priority=10,
                )
            ]
        )

        producers = ProducerRegistry()
        producers.register(ProducerInfo(producer_id=ProducerId("rule.lock_system"), origin=OriginKind.RULE))
        producers.register(ProducerInfo(producer_id=ProducerId("policy.alice"), origin=OriginKind.BEHAVIOR_POLICY))
        # llm.narrator 未注册

        target = EntityTarget(
            entity_id=EntityId("ent_door"),
            component_type=ComponentTypeId("door.lock_state"),
        )

        # (a) 未授权 producer policy.alice
        eff_a = _make_proposed_effect(
            "eff_a",
            EFFECT_SET_COMPONENT,
            target,
            {"component_type": "door.lock_state", "data": {"locked": False}},
            source="policy.alice",
        )
        res_a = check_authority(eff_a, policy, state)
        assert res_a.decision == AuthorityDecision.DENY
        assert res_a.reason_code == "rule_deny"

        # (b) 完全未注册 producer llm.narrator
        eff_b = _make_proposed_effect(
            "eff_b",
            EFFECT_SET_COMPONENT,
            target,
            {"component_type": "door.lock_state", "data": {"locked": False}},
            source="llm.narrator",
        )
        res_b = check_authority(eff_b, policy, state)
        assert res_b.decision == AuthorityDecision.DENY
        assert res_b.reason_code == "rule_deny"

        # (c) 携带 authority_scope="door.lock_state" 伪造声明的未授权 producer (D-P2-17)
        eff_c = _make_proposed_effect(
            "eff_c",
            EFFECT_SET_COMPONENT,
            target,
            {"component_type": "door.lock_state", "data": {"locked": False}},
            source="policy.alice",
            authority_scope="door.lock_state",
        )
        res_c = check_authority(eff_c, policy, state)
        assert res_c.decision == AuthorityDecision.DENY
        assert res_c.reason_code == "rule_deny"

        # (d) 无匹配规则（空白 policy）
        blank_policy = AuthorityPolicy(rules=[])
        res_d = check_authority(eff_a, blank_policy, state)
        assert res_d.decision == AuthorityDecision.DENY
        assert res_d.reason_code == "no_matching_rule"

        # 端到端：经 CascadeExecutor 运行攻击批次
        executor = CascadeExecutor(
            policy=policy,
            producer_registry=producers,
        )
        origin_tx = Provenance(producer_id=ProducerId("policy.alice"), origin=OriginKind.BEHAVIOR_POLICY)
        result: CascadeResult = executor.run(
            [eff_a, eff_b, eff_c],
            state,
            causal_root_id="act_attack_1",
            origin=origin_tx,
        )

        # 断言：final_state 100% 未突变、revision 不变、零 COMMITTED 事务
        assert result.final_state == state
        assert result.final_state.world_revision == Revision(0)
        assert len(result.transactions) == 0
        assert len(result.events) == 0

        # trace 含 AUTHORITY_DECISION(deny) 逐条记录
        auth_traces = [
            t for t in result.trace_records if t.kind == TraceKind.AUTHORITY_DECISION
        ]
        assert len(auth_traces) == 3
        for t in auth_traces:
            assert t.payload["decision"] == "deny"


# ==============================================================================
# 场景 2: 双写冲突仲裁 (Plan §11.2 / P2 §11.2)
# ==============================================================================


class TestScenario2ConflictResolutionAdversarial:
    """场景 2（双写冲突仲裁）：多个 producer 对同一资源发起互斥变更，
    ConflictResolver 给出唯一 WINNER，败者被标记 REJECT 并记录仲裁因果。
    """

    def test_conflict_grouping_rules(self) -> None:
        """验证锁分组：(a) 三写同址成组；(b) 同组件不同 field_path 不成组；(c) 整组件 vs 字段成组。"""
        # (a) 三写同址
        target_gem = EntityTarget(
            entity_id=EntityId("ent_gem"),
            component_type=ComponentTypeId("space.position"),
        )
        e1 = _make_proposed_effect("e1", EFFECT_SET_COMPONENT, target_gem, {"component_type": "space.position", "data": {"x": 1, "y": 1}}, source="p1")
        e2 = _make_proposed_effect("e2", EFFECT_SET_COMPONENT, target_gem, {"component_type": "space.position", "data": {"x": 2, "y": 2}}, source="p2")
        e3 = _make_proposed_effect("e3", EFFECT_SET_COMPONENT, target_gem, {"component_type": "space.position", "data": {"x": 3, "y": 3}}, source="p3")

        groups_a = detect_conflicts([e1, e2, e3])
        assert len(groups_a) == 1
        assert len(groups_a[0].effects) == 3

        # (b) 同组件不同 field_path 不应成组
        target_f1 = EntityTarget(
            entity_id=EntityId("ent_alice"),
            component_type=ComponentTypeId("attrs.hp"),
            field_path="current",
        )
        target_f2 = EntityTarget(
            entity_id=EntityId("ent_alice"),
            component_type=ComponentTypeId("attrs.hp"),
            field_path="max",
        )
        ef1 = _make_proposed_effect("ef1", EFFECT_SET_COMPONENT, target_f1, {"value": 90}, source="p1")
        ef2 = _make_proposed_effect("ef2", EFFECT_SET_COMPONENT, target_f2, {"value": 120}, source="p2")
        groups_b = detect_conflicts([ef1, ef2])
        assert len(groups_b) == 0

        # (c) 整组件 vs 字段效果应成组
        target_whole = EntityTarget(
            entity_id=EntityId("ent_alice"),
            component_type=ComponentTypeId("attrs.hp"),
        )
        ew = _make_proposed_effect("ew", EFFECT_SET_COMPONENT, target_whole, {"component_type": "attrs.hp", "data": {"current": 80, "max": 100}}, source="p1")
        groups_c = detect_conflicts([ew, ef1])
        assert len(groups_c) == 1
        assert len(groups_c[0].effects) == 2

    def test_deterministic_conflict_resolution_strategies(self) -> None:
        """逐策略测试仲裁可解释性与确定性，验证 trace 与败者丢弃。"""
        # Spec §19 原型 Move(gem, floor) vs Move(gem, alice_inventory)
        target = EntityTarget(entity_id=EntityId("ent_gem"), component_type=ComponentTypeId("space.position"))

        # 1. Authority Rule Priority 差决胜
        p_alice = ProducerId("actor.alice")
        p_bob = ProducerId("actor.bob")
        eff_alice = _make_proposed_effect("eff_alice", EFFECT_SET_COMPONENT, target, {"component_type": "space.position", "data": {"x": 1, "y": 1}}, source=str(p_alice))
        eff_bob = _make_proposed_effect("eff_bob", EFFECT_SET_COMPONENT, target, {"component_type": "space.position", "data": {"x": 2, "y": 2}}, source=str(p_bob))

        res_alice = check_authority(
            eff_alice,
            AuthorityPolicy(rules=[AuthorityRule(selector=AuthoritySelector(component_type=ComponentTypeId("space.position")), allowed_writers=[p_alice], priority=20)]),
        )
        res_bob = check_authority(
            eff_bob,
            AuthorityPolicy(rules=[AuthorityRule(selector=AuthoritySelector(component_type=ComponentTypeId("space.position")), allowed_writers=[p_bob], priority=10)]),
        )

        ctx_auth = ResolutionContext(
            arrival={EffectId("eff_alice"): 0, EffectId("eff_bob"): 1},
            authority_decisions={EffectId("eff_alice"): res_alice, EffectId("eff_bob"): res_bob},
        )
        resolver = DefaultConflictResolver()
        report_auth = resolver.resolve_all([eff_alice, eff_bob], ctx_auth)
        assert report_auth.accepted == (EffectId("eff_alice"),)
        assert report_auth.dropped == (EffectId("eff_bob"),)
        assert report_auth.resolutions[0].strategy == "authority_priority"
        assert report_auth.resolutions[0].accepted == (EffectId("eff_alice"),)
        payload_auth = report_auth.resolutions[0].to_trace_payload()
        assert payload_auth["decision"] == "winner"
        assert payload_auth["effect_id"] == "eff_alice"

        # 2. Timestamp 策略 (LWW)
        eff_t1 = _make_proposed_effect("eff_t1", EFFECT_SET_COMPONENT, target, {"component_type": "space.position", "data": {"x": 1, "y": 1}}, source="p1", metadata={"producer_timestamp_ms": 1000})
        eff_t2 = _make_proposed_effect("eff_t2", EFFECT_SET_COMPONENT, target, {"component_type": "space.position", "data": {"x": 2, "y": 2}}, source="p2", metadata={"producer_timestamp_ms": 2000})
        ctx_ts = ResolutionContext(arrival={EffectId("eff_t1"): 0, EffectId("eff_t2"): 1})
        report_ts = resolver.resolve_all([eff_t1, eff_t2], ctx_ts)
        assert report_ts.accepted == (EffectId("eff_t2"),)
        assert report_ts.resolutions[0].strategy == "timestamp"

        # 3. Producer Priority 策略
        reg = ProducerRegistry()
        reg.register(ProducerInfo(producer_id=ProducerId("p_high"), origin=OriginKind.RULE, priority=100))
        reg.register(ProducerInfo(producer_id=ProducerId("p_low"), origin=OriginKind.BEHAVIOR_POLICY, priority=10))
        eff_p1 = _make_proposed_effect("eff_p1", EFFECT_SET_COMPONENT, target, {"component_type": "space.position", "data": {"x": 1, "y": 1}}, source="p_high")
        eff_p2 = _make_proposed_effect("eff_p2", EFFECT_SET_COMPONENT, target, {"component_type": "space.position", "data": {"x": 2, "y": 2}}, source="p_low")
        ctx_prod = ResolutionContext(arrival={EffectId("eff_p1"): 0, EffectId("eff_p2"): 1}, producer_registry=reg)
        report_prod = resolver.resolve_all([eff_p1, eff_p2], ctx_prod)
        assert report_prod.accepted == (EffectId("eff_p1"),)
        assert report_prod.resolutions[0].strategy == "producer_priority"

        # 4. FIFO 到达序兜底
        eff_f1 = _make_proposed_effect("eff_f1", EFFECT_SET_COMPONENT, target, {"component_type": "space.position", "data": {"x": 1, "y": 1}}, source="p_same")
        eff_f2 = _make_proposed_effect("eff_f2", EFFECT_SET_COMPONENT, target, {"component_type": "space.position", "data": {"x": 2, "y": 2}}, source="p_same")
        ctx_fifo = ResolutionContext(arrival={EffectId("eff_f1"): 0, EffectId("eff_f2"): 1})
        report_fifo = resolver.resolve_all([eff_f1, eff_f2], ctx_fifo)
        assert report_fifo.accepted == (EffectId("eff_f1"),)
        assert report_fifo.resolutions[0].strategy == "entity_fifo"


# ==============================================================================
# 场景 3: 无效效果原子失败 (Plan §11.3 / P2 §11.3)
# ==============================================================================


class TestScenario3AtomicFailureAdversarial:
    """场景 3（无效效果原子失败）：一个事务批次中混入 1 个无效效果，
    触发 L2 终检失败或 Reducer 失败，整批全部 ABORT，已有的有效效果也不得应用，
    世界状态与 revision 零变化。
    """

    def test_missing_entity_l2_check_aborts_entire_transaction(self) -> None:
        """(a) L2 终检路径——批次内一条指向 missing entity，整批 ABORT，有效效果不被应用。"""
        state = _make_base_state(0)
        eff_valid = _make_proposed_effect(
            "eff_valid",
            EFFECT_SET_WORLD_VARIABLE,
            StateDomainTarget(domain=StateDomainId("world_variables")),
            {"key": "test_var", "value": 42},
        )
        eff_missing = _make_proposed_effect(
            "eff_missing",
            EFFECT_SET_COMPONENT,
            EntityTarget(entity_id=EntityId("ent_nonexistent"), component_type=ComponentTypeId("space.position")),
            {"component_type": "space.position", "data": {"x": 9, "y": 9}},
        )

        txn_id = new_transaction_id()
        producer = Provenance(producer_id=ProducerId("rule.system"), origin=OriginKind.RULE)
        new_state, txn, events = commit_transaction(
            state,
            [eff_valid, eff_missing],
            txn_id,
            producer,
        )

        assert txn.status == TransactionStatus.ABORTED
        assert txn.commit_revision is None
        assert txn.effects == []
        assert txn.event_ids == []
        assert "missing_entity" in txn.abort_reason
        assert len(events) == 0
        assert new_state == state
        assert new_state.world_revision == Revision(0)
        assert "test_var" not in new_state.world_variables

    def test_reducer_step_failure_aborts_entire_transaction(self) -> None:
        """(b) reducer 应用路径——同事务 seq0 remove_entity(X) + seq1 对 X set_component。"""
        state = _make_base_state(0)
        target = EntityTarget(entity_id=EntityId("ent_alice"), component_type=ComponentTypeId("space.position"))
        eff_rm = _make_proposed_effect(
            "eff_rm",
            EFFECT_REMOVE_ENTITY,
            EntityTarget(entity_id=EntityId("ent_alice")),
            {},
        )
        eff_set = _make_proposed_effect(
            "eff_set",
            EFFECT_SET_COMPONENT,
            target,
            {"component_type": "space.position", "data": {"x": 5, "y": 5}},
        )

        txn_id = new_transaction_id()
        producer = Provenance(producer_id=ProducerId("rule.system"), origin=OriginKind.RULE)
        new_state, txn, events = commit_transaction(
            state,
            [eff_rm, eff_set],
            txn_id,
            producer,
        )

        assert txn.status == TransactionStatus.ABORTED
        assert txn.commit_revision is None
        assert "reducer_failed" in txn.abort_reason
        assert len(events) == 0
        assert new_state == state
        assert new_state.world_revision == Revision(0)
        # 实体 Alice 依然完好存在
        assert EntityId("ent_alice") in new_state.entities

    def test_stale_batch_aborts_entire_transaction(self) -> None:
        """(c) stale 批次（base_revision 落后于 state）。"""
        state = _make_base_state(5)
        eff_stale = _make_proposed_effect(
            "eff_stale",
            EFFECT_SET_WORLD_VARIABLE,
            StateDomainTarget(domain=StateDomainId("world_variables")),
            {"key": "stale_k", "value": 100},
            base_revision=3,  # 落后于 5
        )

        producer = Provenance(producer_id=ProducerId("rule.system"), origin=OriginKind.RULE)
        new_state, txn, events = commit_transaction(
            state,
            [eff_stale],
            new_transaction_id(),
            producer,
        )

        assert txn.status == TransactionStatus.ABORTED
        assert txn.commit_revision is None
        assert "stale_revision" in txn.abort_reason
        assert len(events) == 0
        assert new_state == state
        assert new_state.world_revision == Revision(5)


# ==============================================================================
# 场景 4: 原子提交与 Revision 单调递增 (Plan §11.4 / P2 §11.4)
# ==============================================================================


class TestScenario4RevisionMonotonicityAdversarial:
    """场景 4（原子提交与 Revision 单调递增）：事务成功提交时，world_revision 恰好严格 +1；
    失败提交时 revision 保持不变。
    """

    def test_revision_increments_exactly_plus_one_per_committed_transaction(self) -> None:
        # (a) N=5 效果单事务 -> revision 恰 +1
        state0 = _make_base_state(0)
        effects = [
            _make_proposed_effect(
                f"eff_{i}",
                EFFECT_SET_WORLD_VARIABLE,
                StateDomainTarget(domain=StateDomainId("world_variables")),
                {"key": f"var_{i}", "value": i},
                base_revision=0,
            )
            for i in range(5)
        ]
        producer = Provenance(producer_id=ProducerId("rule.system"), origin=OriginKind.RULE)
        state1, txn1, events1 = commit_transaction(state0, effects, new_transaction_id(), producer)
        assert txn1.status == TransactionStatus.COMMITTED
        assert txn1.commit_revision == Revision(1)
        assert txn1.base_revision == Revision(0)
        assert state1.world_revision == Revision(1)
        assert len(events1) == 5

        # (b) 三级级联 -> revision 恰 +3 且各事务 commit_revision 连续递增
        def trigger_level1(events: list[DomainEvent], s: GuardedWorldState, depth: int) -> list[ProposedEffect]:
            if not events or depth != 0:
                return []
            res: list[ProposedEffect] = []
            for event in events:
                target = event.payload.get("target", {})
                if target.get("kind") == "state_domain" and target.get("domain") == "world_variables":
                    res.append(
                        _make_proposed_effect(
                            "eff_cascade_1",
                            EFFECT_SET_COMPONENT,
                            EntityTarget(entity_id=EntityId("ent_alice"), component_type=ComponentTypeId("layer.d1")),
                            {"component_type": "layer.d1", "data": {"v": 1}},
                            source="rule.t1",
                            base_revision=int(s.world_revision),
                            cause_ids=[CauseRef(kind=CauseKind.EVENT, ref_id=str(event.event_id))],
                        )
                    )
            return res

        def trigger_level2(events: list[DomainEvent], s: GuardedWorldState, depth: int) -> list[ProposedEffect]:
            if not events or depth != 1:
                return []
            res: list[ProposedEffect] = []
            for event in events:
                target = event.payload.get("target", {})
                if target.get("entity_id") == "ent_alice" and target.get("component_type") == "layer.d1":
                    res.append(
                        _make_proposed_effect(
                            "eff_cascade_2",
                            EFFECT_SET_COMPONENT,
                            EntityTarget(entity_id=EntityId("ent_alice"), component_type=ComponentTypeId("layer.d2")),
                            {"component_type": "layer.d2", "data": {"v": 2}},
                            source="rule.t2",
                            base_revision=int(s.world_revision),
                            cause_ids=[CauseRef(kind=CauseKind.EVENT, ref_id=str(event.event_id))],
                        )
                    )
            return res

        policy = AuthorityPolicy(
            rules=[
                AuthorityRule(selector=AuthoritySelector(), allowed_writers=[ProducerId("rule.system"), ProducerId("rule.t1"), ProducerId("rule.t2")]),
            ]
        )
        trig_reg = CascadeTriggerRegistry()
        trig_reg.register(SyncTrigger("t1", trigger_level1))
        trig_reg.register(SyncTrigger("t2", trigger_level2))

        executor = CascadeExecutor(
            policy=policy,
            triggers=trig_reg,
        )

        init_eff = _make_proposed_effect(
            "eff_init",
            EFFECT_SET_WORLD_VARIABLE,
            StateDomainTarget(domain=StateDomainId("world_variables")),
            {"key": "var_0", "value": 0},
            source="rule.system",
            base_revision=1,
        )
        res_cascade = executor.run([init_eff], state1, causal_root_id="act_init", origin=producer)
        assert len(res_cascade.transactions) == 3
        # 初始 rev=1 -> rev=4
        assert res_cascade.final_state.world_revision == Revision(4)
        for i, txn in enumerate(res_cascade.transactions):
            assert txn.base_revision == Revision(1 + i)
            assert txn.commit_revision == Revision(2 + i)
            assert txn.commit_revision == txn.base_revision + 1

        # (c) 一次 ABORTED -> revision +0
        state_before = res_cascade.final_state
        state_after, txn_abort, _ = commit_transaction(
            state_before,
            [_make_proposed_effect("eff_bad", EFFECT_SET_WORLD_VARIABLE, StateDomainTarget(domain=StateDomainId("world_variables")), {"key": "bad", "value": 1}, base_revision=0)],
            new_transaction_id(),
            producer,
        )
        assert txn_abort.status == TransactionStatus.ABORTED
        assert state_after.world_revision == state_before.world_revision == Revision(4)

        # (d) 空 accepted 回合（authority 全拒后管道空转） -> revision +0
        strict_policy = AuthorityPolicy(rules=[])
        exec_strict = CascadeExecutor(policy=strict_policy)
        res_empty = exec_strict.run([init_eff], state_after, causal_root_id="act_strict", origin=producer)
        assert len(res_empty.transactions) == 0
        assert res_empty.final_state.world_revision == Revision(4)


# ==============================================================================
# 场景 5: 循环事件级联熔断 (Plan §11.6 / P2 §11.6)
# ==============================================================================


class TestScenario5CycleDetectorAdversarial:
    """场景 5（循环事件级联熔断）：构造 A -> B -> A 循环触发器，
    验证 CycleDetector 在达到深度上限或检测到重访时自动熔断，不发生死循环，
    记录 cascade_cycle / cascade_depth_exceeded 诊断。
    """

    def test_hp_revisit_cycle_fuse(self) -> None:
        """HP changed -> set HP -> HP changed 原型环路熔断。"""
        state = _make_base_state(0)

        # 触发器：每次收到 attrs.hp 变更事件，又提议修改 attrs.hp
        def on_hp_changed(events: list[DomainEvent], s: GuardedWorldState, depth: int) -> list[ProposedEffect]:
            res: list[ProposedEffect] = []
            for event in events:
                if event.event_type == EFFECT_SET_COMPONENT:
                    target = event.payload.get("target", {})
                    if target.get("component_type") == "attrs.hp":
                        res.append(
                            _make_proposed_effect(
                                f"eff_cycle_{event.event_id}",
                                EFFECT_SET_COMPONENT,
                                EntityTarget(entity_id=EntityId("ent_alice"), component_type=ComponentTypeId("attrs.hp")),
                                {"component_type": "attrs.hp", "data": {"current": 90, "max": 100}},
                                source="rule.hp_responder",
                                base_revision=int(s.world_revision),
                                cause_ids=[CauseRef(kind=CauseKind.EVENT, ref_id=str(event.event_id))],
                            )
                        )
            return res

        policy = AuthorityPolicy(
            rules=[
                AuthorityRule(selector=AuthoritySelector(), allowed_writers=[ProducerId("rule.system"), ProducerId("rule.hp_responder")]),
            ]
        )

        trig_reg = CascadeTriggerRegistry()
        trig_reg.register(SyncTrigger("hp_responder", on_hp_changed))

        executor = CascadeExecutor(
            policy=policy,
            triggers=trig_reg,
        )

        root_eff = _make_proposed_effect(
            "eff_root_hp",
            EFFECT_SET_COMPONENT,
            EntityTarget(entity_id=EntityId("ent_alice"), component_type=ComponentTypeId("attrs.hp")),
            {"component_type": "attrs.hp", "data": {"current": 95, "max": 100}},
            source="rule.system",
            base_revision=0,
        )

        producer = Provenance(producer_id=ProducerId("rule.system"), origin=OriginKind.RULE)
        result = executor.run([root_eff], state, causal_root_id="act_hp", origin=producer)

        # 断言：在 depth 1 即丢弃回环提案，记录 cycle_detected 诊断，级联收敛
        assert len(result.transactions) == 1
        assert len(result.diagnostics) >= 1
        cycle_diag = next(d for d in result.diagnostics if d.kind == "cycle_detected")
        assert "attrs.hp" in cycle_diag.detail
        assert cycle_diag.depth == 1

    def test_max_depth_exceeded_fuse(self) -> None:
        """无环但触发器链深度 > 8 -> 在 depth 9 启动前熔断，至多 9 个 COMMITTED。"""
        state = _make_base_state(0)

        # 构造无环自持长链：修改 (ent_alice, depth.d{depth})
        def self_sustaining_chain(events: list[DomainEvent], s: GuardedWorldState, depth: int) -> list[ProposedEffect]:
            if not events:
                return []
            return [
                _make_proposed_effect(
                    f"eff_sustain_{depth}",
                    EFFECT_SET_COMPONENT,
                    EntityTarget(
                        entity_id=EntityId("ent_alice"),
                        component_type=ComponentTypeId(f"depth.d{depth}"),
                    ),
                    {"v": depth},
                    source="rule.chain",
                    base_revision=int(s.world_revision),
                    cause_ids=[
                        CauseRef(kind=CauseKind.EVENT, ref_id=str(events[0].event_id))
                    ],
                )
            ]

        policy = AuthorityPolicy(
            rules=[
                AuthorityRule(selector=AuthoritySelector(), allowed_writers=[ProducerId("rule.system"), ProducerId("rule.chain")]),
            ]
        )

        trig_reg = CascadeTriggerRegistry()
        trig_reg.register(SyncTrigger("chain_trigger", self_sustaining_chain))

        executor = CascadeExecutor(
            policy=policy,
            config=CascadeConfig(max_cascade_depth=8, location_revisit="allow"),
            triggers=trig_reg,
        )

        root_eff = _make_proposed_effect(
            "eff_step_0",
            EFFECT_SET_WORLD_VARIABLE,
            StateDomainTarget(domain=StateDomainId("world_variables")),
            {"key": "step_0", "value": 0},
            source="rule.system",
            base_revision=0,
        )

        producer = Provenance(producer_id=ProducerId("rule.system"), origin=OriginKind.RULE)
        result = executor.run([root_eff], state, causal_root_id="act_chain", origin=producer)
        # 0..8 一共 9 个 depth，COMMITTED <= 9
        assert len(result.transactions) == 9
        assert len(result.diagnostics) >= 1
        depth_diag = next(d for d in result.diagnostics if d.kind == "cascade_depth_exceeded")
        assert depth_diag.depth == 9

        # 断言全部事件 cascade_id/root 一致，depth 连续
        root_cascade_id = result.transactions[0].cascade.cascade_id
        for i, txn in enumerate(result.transactions):
            assert txn.cascade.cascade_id == root_cascade_id
            assert txn.cascade.depth == i


# ==============================================================================
# 场景 6: 写屏障拦截与零公共写入绕过 (Plan §11.7 / P2 §11.7)
# ==============================================================================


class TestScenario6WriteBarrierAdversarial:
    """场景 6（写屏障拦截与零公共写入绕过）：验证试图通过 model_copy、
    model_construct、copy/deepcopy、反射赋值或直接修改绕过 Reducer 的行为被全部拦截。

    G2 补充轮 1（必须测试 7 检查单补充——私有槽 / mangled 名向量）：旧
    ``_GuardedWorldState__wrapped`` 名称改写槽（及 ``_GuardedEntityRecord__wrapped`` /
    ``_GuardedScenarioState__wrapped`` 同类槽）在属性存在时经描述符常规
    查找命中（``__getattr__`` 永不触发），返回活权威状态、其嵌套容器可被
    原地突变（revision 不变、无事件/trace）——G2 门禁盲审发现的缝隙，
    已由 token 注册表机制闭合。本组测试显式列入该向量：

    (a) mangled 槽访问确定性抛 WriteBarrierError（私有缝隙错误种类契约），
        任何变体不返回活 WorldState；
    (b) ``object.__getattribute__`` / ``vars()`` / ``type(g).__dict__``
        内省 / ``__slots__`` 扫描均无活 WorldState 引用（含闭包单元深度）；
    (c) 经任何可达路径对权威状态的原地容器写入全部被拦截
        （TypeError / WriteBarrierError）且 revision / 内容不变；
    (d) 视图 copy / deepcopy 仍返回独立可变快照（改副本不波及权威，回归）。
    """

    def test_four_escape_paths_blocked_when_armed(self) -> None:
        """屏障武装态下四条逃逸路径逐一拦截，豁免窗口放行。"""
        install_write_barrier()
        assert write_barrier_installed()
        state = _make_base_state(0)

        # 1. model_copy
        with pytest.raises(WriteBarrierError):
            state.model_copy(update={"world_revision": Revision(99)})

        # 2. model_construct
        with pytest.raises(WriteBarrierError):
            Transaction.model_construct(
                transaction_id=new_transaction_id(),
                base_revision=Revision(0),
                commit_revision=Revision(1),
                status=TransactionStatus.COMMITTED,
                effects=[],
                event_ids=[],
            )

        # 3. copy.copy
        with pytest.raises(WriteBarrierError):
            copy.copy(state)

        # 4. copy.deepcopy
        with pytest.raises(WriteBarrierError):
            copy.deepcopy(state)

        # write_barrier_exempt 豁免窗口内放行
        with write_barrier_exempt():
            c1 = state.model_copy(update={"world_revision": Revision(99)})
            assert c1.world_revision == Revision(99)
            c2 = Transaction.model_construct(
                transaction_id=TransactionId("txn_test"),
                base_revision=Revision(0),
                commit_revision=Revision(1),
                status=TransactionStatus.COMMITTED,
                effects=[],
                event_ids=[],
            )
            assert c2.transaction_id == "txn_test"
            c3 = copy.copy(state)
            c4 = copy.deepcopy(state)
            assert c3 == state
            assert c4 == state

    def test_guard_facade_blocks_mutations(self) -> None:
        """guard(state) 只读包装器：只读门面与序列化可用，写路径全部拦截。"""
        state = _make_base_state(0)
        g = guard(state)
        assert is_guarded(g)

        # 只读门面可用
        assert g.has_entity(EntityId("ent_alice")) is True
        assert g.entity_view(EntityId("ent_alice")) is not None
        assert g.component_view(EntityId("ent_alice"), ComponentTypeId("space.position")) == {"x": 0, "y": 0}
        assert g.model_dump(mode="json") == state.model_dump(mode="json")

        # 写路径全部拦截
        with pytest.raises(WriteBarrierError):
            g.model_copy(update={"world_revision": Revision(99)})
        with pytest.raises(WriteBarrierError):
            g.model_construct()
        with pytest.raises(WriteBarrierError):
            copy.copy(g)
        with pytest.raises(WriteBarrierError):
            copy.deepcopy(g)
        with pytest.raises(WriteBarrierError):
            g.world_revision = Revision(99)
        with pytest.raises(WriteBarrierError):
            g._with_world_revision(Revision(99))

    def test_guard_container_level_mutation_attacks_blocked(self) -> None:
        """B2 修复验证：guard 门面的容器级原地修改攻击全部拦截（TypeError），
        权威状态零变化。

        覆盖攻击面：guard(state).world_variables（顶层 + 嵌套 dict）、
        guard(state).entities（容器 + 实体门面 + 组件容器 + 嵌套组件数据 +
        tags）、guard(state).scenario_state.data——``__setitem__`` /
        ``__delitem__`` / ``clear`` / ``pop`` / ``popitem`` / ``setdefault`` /
        ``update`` 等一切原地修改形态。
        """
        base_entities = _make_base_state(0).entities
        state = WorldState(
            world_revision=Revision(0),
            entities=base_entities,
            world_variables={"calendar": {"day": 3}, "gold": 10},
            scenario_state=ScenarioState(
                scenario_id="scn_main", stage="opening", data={"goal": "find key"}
            ),
        )
        snapshot = state.model_dump(mode="json")
        g = guard(state)

        def _expect_type_error(attack: Any) -> None:
            """每个原地修改攻击形态都必须抛 TypeError（只读容器契约）。"""
            with pytest.raises(TypeError):
                attack()

        # —— world_variables：顶层与嵌套 ——
        _expect_type_error(lambda: exec('g.world_variables["gold"] = 999', {"g": g}))
        _expect_type_error(lambda: exec('del g.world_variables["gold"]', {"g": g}))
        _expect_type_error(lambda: g.world_variables.clear())
        _expect_type_error(lambda: g.world_variables.pop("gold"))
        _expect_type_error(lambda: g.world_variables.popitem())
        _expect_type_error(lambda: g.world_variables.setdefault("injected", 1))
        _expect_type_error(lambda: g.world_variables.update({"injected": 1}))
        _expect_type_error(lambda: exec('g.world_variables["calendar"]["day"] = 99', {"g": g}))
        _expect_type_error(lambda: g.world_variables["calendar"].clear())

        # —— entities：容器级 ——
        _expect_type_error(
            lambda: exec(
                'g.entities[EntityId("ent_intruder")] = g.entities[EntityId("ent_alice")]',
                {"g": g, "EntityId": EntityId},
            )
        )
        _expect_type_error(
            lambda: exec('del g.entities[EntityId("ent_alice")]', {"g": g, "EntityId": EntityId})
        )
        _expect_type_error(lambda: g.entities.clear())
        _expect_type_error(lambda: g.entities.pop(EntityId("ent_alice")))
        _expect_type_error(lambda: g.entities.popitem())
        _expect_type_error(lambda: g.entities.update({}))

        # —— entities：实体门面内的组件容器与嵌套组件数据 ——
        alice = g.entities[EntityId("ent_alice")]
        _expect_type_error(
            lambda: exec(
                'alice.components[ComponentTypeId("attrs.hp")] = {"current": 0}',
                {"alice": alice, "ComponentTypeId": ComponentTypeId},
            )
        )
        _expect_type_error(
            lambda: exec(
                'del alice.components[ComponentTypeId("attrs.hp")]',
                {"alice": alice, "ComponentTypeId": ComponentTypeId},
            )
        )
        _expect_type_error(lambda: alice.components.clear())
        _expect_type_error(lambda: alice.components.pop(ComponentTypeId("attrs.hp")))
        _expect_type_error(
            lambda: exec(
                'alice.components[ComponentTypeId("attrs.hp")]["current"] = 0',
                {"alice": alice, "ComponentTypeId": ComponentTypeId},
            )
        )
        _expect_type_error(lambda: exec("alice.tags[0] = 'possessed'", {"alice": alice}))

        # —— scenario_state.data ——
        _expect_type_error(lambda: exec('g.scenario_state.data["goal"] = "hijacked"', {"g": g}))
        _expect_type_error(lambda: g.scenario_state.data.clear())
        _expect_type_error(lambda: g.scenario_state.data.pop("goal"))

        # —— 门面属性赋值 / 删除 / 私有缝隙 / 复制逃逸 → WriteBarrierError ——
        with pytest.raises(WriteBarrierError):
            alice.entity_id = EntityId("ent_intruder")
        with pytest.raises(WriteBarrierError):
            del alice.entity_class
        with pytest.raises(WriteBarrierError):
            alice._with_components({})
        with pytest.raises(WriteBarrierError):
            g.scenario_state.scenario_id = "scn_hijack"
        with pytest.raises(WriteBarrierError):
            copy.copy(alice)
        with pytest.raises(WriteBarrierError):
            copy.deepcopy(g.scenario_state)

        # —— 读路径仍可用：视图判等口径不变 ——
        assert g.entities == state.entities
        assert g.world_variables == state.world_variables
        assert g.scenario_state == state.scenario_state
        assert alice.components[ComponentTypeId("attrs.hp")]["current"] == 100
        assert alice.tags == ("hero",)

        # —— 全部攻击后权威状态零变化 ——
        assert state.model_dump(mode="json") == snapshot
        assert state.world_variables["gold"] == 10
        assert state.entities[EntityId("ent_alice")].components[
            ComponentTypeId("attrs.hp")
        ] == {"current": 100, "max": 100}
        assert state.scenario_state.data == {"goal": "find key"}

    def test_guard_private_slot_vectors_expose_no_live_state(self) -> None:
        """G2 补充轮 1（必须测试 7 检查单补充）：私有槽 / mangled 名向量
        不得解析出活权威状态。

        向量清单（机制：GuardedWorldState 实例只持 int token，权威状态与
        深冻结视图快照存于模块私有注册表 ``_GUARD_REGISTRY``）：

        1. ``getattr(g, "_GuardedWorldState__wrapped")`` → 确定性
           :class:`WriteBarrierError`（私有缝隙错误种类契约；旧机制下该
           向量返回活 WorldState——G2 门禁盲审发现）；
        2. mangled 名变体扫描（规范改名名 / 未改名私有形态 / 其他名称）：
           一律不返回活 WorldState；
        3. ``object.__getattribute__(g, <旧槽名>)`` →
           ``AttributeError``（显式 ``object.__getattribute__`` 不经过
           ``__getattr__`` 缝隙拦截器；槽不存在 → 确定性 AttributeError，
           同样不返回活状态）；
        4. ``vars(g)`` / ``__dict__`` 扫描：要么抛错，要么结果无状态引用；
        5. ``type(g).__dict__`` 内省（含方法闭包单元）与 ``__slots__``
           扫描：无活 WorldState 引用，槽名不含 ``wrapped``；
        6. 唯一槽 ``_GuardedWorldState__token`` 仅为 int 令牌。
        """
        state = _make_base_state(0)
        g = guard(state)

        # (1) 规范 mangled 槽名：确定性 WriteBarrierError（不返回活状态）
        with pytest.raises(WriteBarrierError):
            getattr(g, "_GuardedWorldState__wrapped")

        # (2) mangled 名变体扫描：任何变体不返回活 WorldState
        for name in (
            "_GuardedWorldState__wrapped",
            "__wrapped",
            "_wrapped",
            "_state",
            "wrapped",
            "state",
        ):
            try:
                value = getattr(g, name)
            except (AttributeError, WriteBarrierError):
                continue
            assert not isinstance(value, WorldState), f"{name} 泄漏活权威状态"

        # (3) object.__getattribute__ 旧槽名 → AttributeError（槽不存在；
        # 显式 object.__getattribute__ 不经 __getattr__ 兜底，不返回活状态）
        with pytest.raises(AttributeError):
            object.__getattribute__(g, "_GuardedWorldState__wrapped")

        # (4) vars(g) / __dict__ 扫描：无状态引用
        for accessor in (lambda: vars(g), lambda: g.__dict__):
            try:
                inst_dict = accessor()
            except (TypeError, WriteBarrierError):
                continue
            assert all(not isinstance(v, WorldState) for v in inst_dict.values())

        # (5) 类内省：方法闭包单元无活状态；__slots__ 扫描无活状态引用
        for value in vars(type(g)).values():
            for candidate in (getattr(value, "__func__", value),):
                for cell in getattr(candidate, "__closure__", None) or ():
                    assert not isinstance(cell.cell_contents, WorldState)
        for slot in getattr(type(g), "__slots__", ()):
            assert "wrapped" not in slot.lower()
            try:
                value = object.__getattribute__(g, slot)
            except (AttributeError, WriteBarrierError):
                continue
            assert not isinstance(value, WorldState)

        # (6) 唯一槽为 int token（机制性断言，防回归回槽承载状态）
        token = object.__getattribute__(g, "_GuardedWorldState__token")
        assert isinstance(token, int) and not isinstance(token, bool)

    def test_guard_entity_scenario_facade_slot_vectors_blocked(self) -> None:
        """G2 补充轮 1：实体 / scenario 门面的 mangled 槽同类缝隙已闭合。

        - ``getattr(facade, "_GuardedEntityRecord__wrapped")`` →
          WriteBarrierError（旧机制该向量返回活 EntityRecord，其
          components dict 可被原地突变——与 GuardedWorldState 同型缝隙）；
        - ``getattr(facade, "_GuardedScenarioState__wrapped")`` →
          WriteBarrierError；
        - 门面只持标量拷贝 + 深冻结视图：槽扫描无活记录 / 活模型引用，
          槽名不含 ``wrapped``；components / data 视图为快照容器而非
          权威容器别名（``is not``）。
        """
        state = _make_base_state(0)
        g = guard(state)
        alice = g.entities[EntityId("ent_alice")]

        with pytest.raises(WriteBarrierError):
            getattr(alice, "_GuardedEntityRecord__wrapped")
        with pytest.raises(WriteBarrierError):
            getattr(g.scenario_state, "_GuardedScenarioState__wrapped")

        for facade, live_type in ((alice, EntityRecord), (g.scenario_state, ScenarioState)):
            for slot in getattr(type(facade), "__slots__", ()):
                assert "wrapped" not in slot.lower()
                try:
                    value = object.__getattribute__(facade, slot)
                except (AttributeError, WriteBarrierError):
                    continue
                assert not isinstance(value, live_type)

        # 视图为快照容器，非权威容器别名
        pos = alice.components[ComponentTypeId("space.position")]
        assert pos is not state.entities[EntityId("ent_alice")].components[
            ComponentTypeId("space.position")
        ]
        assert g.scenario_state.data is not state.scenario_state.data

    def test_guard_all_reachable_paths_write_blocked_state_unchanged(self) -> None:
        """G2 补充轮 1（必须测试 7 检查单补充）：经任何可达路径对权威状态
        的原地容器写入均被拦截，且 s 的 revision / 内容不变。

        攻击面（自 guard 门面出发全枚举）：

        1. ``world_variables`` 顶层 / 嵌套 dict 原地写（TypeError）；
        2. ``entities`` 容器 / 实体门面 components / 嵌套组件数据原地写
           （TypeError）；
        3. ``scenario_state.data`` 原地写（TypeError）；
        4. 私有缝隙路径：mangled 槽访问（WriteBarrierError，取不到活状态）；
        5. 门面属性赋值 / model_copy / model_construct / copy / deepcopy /
           pickle（WriteBarrierError）。
        """
        state = WorldState(
            world_revision=Revision(0),
            entities=_make_base_state(0).entities,
            world_variables={"calendar": {"day": 3}, "gold": 10},
            scenario_state=ScenarioState(
                scenario_id="scn_main", stage="opening", data={"goal": "find key"}
            ),
        )
        snapshot = state.model_dump(mode="json")
        revision_before = state.world_revision
        g = guard(state)
        alice = g.entities[EntityId("ent_alice")]
        pos_ct = ComponentTypeId("space.position")

        # (1) world_variables
        with pytest.raises(TypeError):
            g.world_variables["injected"] = 1
        with pytest.raises(TypeError):
            g.world_variables["calendar"]["day"] = 99
        with pytest.raises(TypeError):
            g.world_variables.pop("gold")

        # (2) entities
        with pytest.raises(TypeError):
            g.entities[EntityId("ent_intruder")] = alice
        with pytest.raises(TypeError):
            alice.components[pos_ct]["x"] = 55
        with pytest.raises(TypeError):
            alice.components[ComponentTypeId("intruder")] = {"x": 0}

        # (3) scenario
        with pytest.raises(TypeError):
            g.scenario_state.data["goal"] = "篡改"

        # (4) 私有缝隙路径
        for mangled, target in (
            ("_GuardedWorldState__wrapped", g),
            ("_GuardedEntityRecord__wrapped", alice),
            ("_GuardedScenarioState__wrapped", g.scenario_state),
        ):
            with pytest.raises(WriteBarrierError):
                getattr(target, mangled)

        # (5) 门面写路径 / 复制路径
        with pytest.raises(WriteBarrierError):
            g.world_revision = Revision(99)
        with pytest.raises(WriteBarrierError):
            g.model_copy(update={"world_revision": Revision(99)})
        with pytest.raises(WriteBarrierError):
            g.model_construct()
        with pytest.raises(WriteBarrierError):
            copy.copy(g)
        with pytest.raises(WriteBarrierError):
            copy.deepcopy(g)
        with pytest.raises(WriteBarrierError):
            pickle.dumps(g)

        # 权威状态：revision 与内容均不变
        assert state.world_revision == revision_before
        assert state.model_dump(mode="json") == snapshot

    def test_guard_view_copy_deepcopy_still_independent_snapshots(self) -> None:
        """G2 补充轮 1 回归：视图 copy / deepcopy 仍返回独立可变快照。

        producer 侧合法工作副本模式不受机制变更影响：对读出的视图做
        ``copy.copy`` / ``copy.deepcopy`` 返回独立 dict（顶层可变、嵌套深
        拷贝），改副本不波及权威状态；视图判等口径不变；门面本体仍不可
        copy / deepcopy（写屏障契约不变）。
        """
        state = WorldState(
            world_revision=Revision(0),
            entities=_make_base_state(0).entities,
            world_variables={"calendar": {"day": 3}, "gold": 10},
            scenario_state=ScenarioState(
                scenario_id="scn_main", stage="opening", data={"goal": "find key"}
            ),
        )
        snapshot = state.model_dump(mode="json")
        g = guard(state)

        # world_variables 视图：copy / deepcopy 独立快照
        shallow = copy.copy(g.world_variables)
        assert isinstance(shallow, dict)
        shallow["injected"] = 1
        assert "injected" not in state.world_variables
        deep = copy.deepcopy(g.world_variables)
        assert isinstance(deep, dict)
        deep["calendar"]["day"] = 99
        assert state.world_variables["calendar"]["day"] == 3, "副本突变不波及权威状态"

        # 实体组件数据视图：deepcopy 独立快照
        alice = g.entities[EntityId("ent_alice")]
        comp = copy.deepcopy(alice.components[ComponentTypeId("attrs.hp")])
        assert isinstance(comp, dict)
        comp["current"] = 1
        assert state.entities[EntityId("ent_alice")].components[
            ComponentTypeId("attrs.hp")
        ]["current"] == 100

        # scenario data 视图：deepcopy 独立快照
        sdata = copy.deepcopy(g.scenario_state.data)
        sdata["goal"] = "篡改"
        assert state.scenario_state.data == {"goal": "find key"}

        # 门面本体仍不可复制（写屏障契约不变）
        with pytest.raises(WriteBarrierError):
            copy.copy(g)
        with pytest.raises(WriteBarrierError):
            copy.deepcopy(g)

        # 视图判等口径不变
        assert g.entities == state.entities
        assert g.world_variables == state.world_variables
        assert g.scenario_state == state.scenario_state
        assert state.model_dump(mode="json") == snapshot

    def test_static_audit_scanner_self_test(self) -> None:
        """向扫描器喂入合成违规源码字符串全部被捕获；reducer.py 自身白名单放行。"""
        def scan_code_string(source: str) -> list[str]:
            tree = ast.parse(source)
            violations: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # 检测 model_copy(update=...)
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "model_copy":
                        if any(k.arg == "update" for k in node.keywords):
                            violations.append(f"line {node.lineno}: model_copy(update=...)")
                    # 检测 .model_construct(
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "model_construct":
                        violations.append(f"line {node.lineno}: model_construct(...)")
                    # 检测 _with_* 调用
                    if isinstance(node.func, ast.Attribute) and node.func.attr.startswith("_with_"):
                        violations.append(f"line {node.lineno}: {node.func.attr}(...)")
            return violations

        bad_source = """
def malicious_mutate(state):
    s1 = state.model_copy(update={"world_revision": 99})
    s2 = Transaction.model_construct(base_revision=0)
    s3 = state._with_entities({})
    return s1, s2, s3
"""
        violations = scan_code_string(bad_source)
        assert len(violations) == 3
        assert any("model_copy(update=...)" in v for v in violations)
        assert any("model_construct(...)" in v for v in violations)
        assert any("_with_entities(...)" in v for v in violations)

    def test_pipeline_trigger_receives_guarded_state(self) -> None:
        """管道面：触发器接收到的是 GuardedWorldState，写路径抛错。"""
        captured: list[Any] = []

        def spy_trigger(events: list[DomainEvent], s: GuardedWorldState, depth: int) -> list[ProposedEffect]:
            captured.append(s)
            with pytest.raises(WriteBarrierError):
                s.model_copy(update={"world_revision": Revision(999)})
            return []

        policy = AuthorityPolicy(
            rules=[AuthorityRule(selector=AuthoritySelector(), allowed_writers=[ProducerId("rule.system")])]
        )
        trig_reg = CascadeTriggerRegistry()
        trig_reg.register(SyncTrigger("spy", spy_trigger))

        executor = CascadeExecutor(
            policy=policy,
            triggers=trig_reg,
        )

        eff = _make_proposed_effect(
            "eff_spy",
            EFFECT_SET_WORLD_VARIABLE,
            StateDomainTarget(domain=StateDomainId("world_variables")),
            {"key": "k", "value": 1},
        )
        producer = Provenance(producer_id=ProducerId("rule.system"), origin=OriginKind.RULE)
        executor.run([eff], _make_base_state(0), causal_root_id="act_spy", origin=producer)

        assert len(captured) == 1
        assert isinstance(captured[0], GuardedWorldState)
        assert is_guarded(captured[0])

    def test_uninstall_restores_p1_semantics(self) -> None:
        """卸载写屏障后，P1 原生语义（如用于构造测试对象的 model_construct）完全复原。"""
        install_write_barrier()
        assert write_barrier_installed()
        uninstall_write_barrier()
        assert not write_barrier_installed()

        state = _make_base_state(0)
        c = state.model_copy(update={"world_revision": Revision(42)})
        assert c.world_revision == Revision(42)


# ==============================================================================
# 场景 7: 事件来源与因果溯源 K6 + ID 义务 (Plan §11.5 / P2 §11.5)
# ==============================================================================


class TestScenario7ProvenanceAndK6Adversarial:
    """场景 7（事件来源与因果溯源 K6 + ID 义务）：验证所有提交生成的 DomainEvent
    均可溯源至根提议，且严格遵循 ID 种类义务与前置条件校验。
    """

    def test_domain_event_k6_provenance_elements(self) -> None:
        """提交后每个事件携带 transaction_id、source_system、cause_ids、world_revision 等 K6 要素。"""
        state = _make_base_state(0)
        cause_root = CauseRef(kind=CauseKind.EFFECT, ref_id="eff_root_parent")
        eff = _make_proposed_effect(
            "eff_prov",
            EFFECT_SET_WORLD_VARIABLE,
            StateDomainTarget(domain=StateDomainId("world_variables")),
            {"key": "k", "value": 1},
            source="rule.system",
            cause_ids=[cause_root],
            base_revision=0,
        )

        txn_id = new_transaction_id()
        cascade_ctx = CascadeContext(cascade_id=CascadeId("cas_123"), causal_root_id=EffectId("eff_root_parent"), depth=0)
        producer = Provenance(producer_id=ProducerId("rule.system"), origin=OriginKind.RULE)
        new_state, txn, events = commit_transaction(
            state,
            [eff],
            txn_id,
            producer,
            cascade=cascade_ctx,
        )

        assert txn.status == TransactionStatus.COMMITTED
        assert len(events) == 1
        evt = events[0]

        # K6 要素逐一断言
        assert evt.transaction_id == txn_id
        assert evt.source_system == ProducerId("rule.system")
        assert evt.world_revision == txn.commit_revision == Revision(1)
        assert evt.cascade == cascade_ctx
        assert CauseRef(kind=CauseKind.EFFECT, ref_id="eff_prov") in evt.cause_ids
        assert cause_root in evt.cause_ids

    def test_cross_kind_id_attack_rejected(self) -> None:
        """跨种类 ID 攻击被 check_effect_id_kinds 拦截。"""
        # (a) EffectId 值写入 target.entity_id
        eff_bad_ent = ProposedEffect.model_construct(
            effect_id=EffectId("eff_1"),
            effect_type=EffectTypeId(EFFECT_REMOVE_ENTITY),
            target=EntityTarget(entity_id=EntityId("eff_bad_entity_id")),
            payload={},
            source=ProducerId("rule.system"),
            base_revision=Revision(0),
            cause_ids=[],
            metadata={},
        )
        issues_a = check_effect_id_kinds(eff_bad_ent)
        assert any("bad_id_kind:target.entity_id" in iss for iss in issues_a)

        # (b) "evt_x" 串写入 effect_id
        eff_bad_eff_id = ProposedEffect.model_construct(
            effect_id=EffectId("evt_wrong_prefix"),
            effect_type=EffectTypeId(EFFECT_REMOVE_ENTITY),
            target=EntityTarget(entity_id=EntityId("ent_alice")),
            payload={},
            source=ProducerId("rule.system"),
            base_revision=Revision(0),
            cause_ids=[],
            metadata={},
        )
        issues_b = check_effect_id_kinds(eff_bad_eff_id)
        assert any("bad_id_kind:effect_id" in iss for iss in issues_b)

        # (c) INTERVENTION cause 携带非 trc_ ref_id
        eff_bad_cause = ProposedEffect.model_construct(
            effect_id=EffectId("eff_2"),
            effect_type=EffectTypeId(EFFECT_REMOVE_ENTITY),
            target=EntityTarget(entity_id=EntityId("ent_alice")),
            payload={},
            source=ProducerId("rule.system"),
            base_revision=Revision(0),
            cause_ids=[CauseRef(kind=CauseKind.INTERVENTION, ref_id="bad_prefix")],
            metadata={},
        )
        issues_c = check_effect_id_kinds(eff_bad_cause)
        assert any("bad_id_kind:cause_ids[0]" in iss for iss in issues_c)

    def test_unregistered_semantic_effect_type_rejected(self) -> None:
        """未注册 effect_type -> L1 no_handler 拒绝；直接喂 reducer -> ReducerError。"""
        eff_unreg = _make_proposed_effect(
            "eff_unreg",
            "semantic.unknown_magic",
            StateDomainTarget(domain=StateDomainId("world_variables")),
            {"foo": "bar"},
        )
        state = _make_base_state(0)

        validator = EffectValidator()
        report = validator.validate_batch([eff_unreg], ValidationContext(state=state, handlers=default_handler_registry()))
        assert eff_unreg.effect_id not in report.accepted
        assert any("no_handler" in iss.to_trace_str() for iss in report.issues_for(eff_unreg.effect_id))

        # 纵深：直接通过 apply_transaction 喂入未注册 effect
        committed = CommittedEffect(
            effect=eff_unreg,
            transaction_id=new_transaction_id(),
            commit_revision=Revision(1),
            sequence=0,
        )
        txn = Transaction(
            transaction_id=committed.transaction_id,
            base_revision=Revision(0),
            commit_revision=Revision(1),
            status=TransactionStatus.COMMITTED,
            effects=[committed],
            event_ids=[EventId("evt_dummy")],
        )
        with pytest.raises(ReducerError):
            apply_transaction(state, txn)

    def test_duplicated_effect_ids_in_batch_rejected(self) -> None:
        """同批重复 effect_id -> duplicated_effect_id 全副本拒绝。"""
        eff1 = _make_proposed_effect("eff_dup", EFFECT_SET_WORLD_VARIABLE, StateDomainTarget(domain=StateDomainId("world_variables")), {"key": "k1", "value": 1})
        eff2 = _make_proposed_effect("eff_dup", EFFECT_SET_WORLD_VARIABLE, StateDomainTarget(domain=StateDomainId("world_variables")), {"key": "k2", "value": 2})

        validator = EffectValidator()
        report = validator.validate_batch([eff1, eff2], ValidationContext(state=_make_base_state(0)))
        assert len(report.accepted) == 0
        assert any("duplicated_effect_id" in iss.to_trace_str() for iss in report.issues_for(EffectId("eff_dup")))

    def test_future_base_revision_rejected(self) -> None:
        """future_base_revision (base > current) -> 拒绝。"""
        eff_future = _make_proposed_effect(
            "eff_future",
            EFFECT_SET_WORLD_VARIABLE,
            StateDomainTarget(domain=StateDomainId("world_variables")),
            {"key": "k", "value": 1},
            base_revision=10,  # 当前是 0
        )
        validator = EffectValidator()
        report = validator.validate_batch([eff_future], ValidationContext(state=_make_base_state(0)))
        assert eff_future.effect_id not in report.accepted
        assert any("future_base_revision" in iss.to_trace_str() for iss in report.issues_for(eff_future.effect_id))

    def test_developer_intervention_provenance_pipeline(self) -> None:
        """origin=DEVELOPER 的 producer 经 policy 显式授权后可提交，trace provenance 完整。"""
        state = _make_base_state(0)
        p_dev = ProducerId("dev.admin")
        reg = ProducerRegistry()
        reg.register(ProducerInfo(producer_id=p_dev, origin=OriginKind.DEVELOPER))

        policy = AuthorityPolicy(
            rules=[AuthorityRule(selector=AuthoritySelector(), allowed_writers=[p_dev])]
        )
        executor = CascadeExecutor(policy=policy, producer_registry=reg)

        cause_int = CauseRef(kind=CauseKind.INTERVENTION, ref_id="trc_admin_command_1")
        eff = _make_proposed_effect(
            "eff_dev",
            EFFECT_SET_WORLD_VARIABLE,
            StateDomainTarget(domain=StateDomainId("world_variables")),
            {"key": "debug_flag", "value": True},
            source=str(p_dev),
            cause_ids=[cause_int],
            base_revision=0,
        )

        origin_dev = Provenance(producer_id=p_dev, origin=OriginKind.DEVELOPER)
        res = executor.run([eff], state, causal_root_id="act_dev", origin=origin_dev)
        assert len(res.transactions) == 1
        txn = res.transactions[0]
        assert txn.provenance.origin == OriginKind.DEVELOPER
        assert txn.provenance.producer_id == p_dev
        assert eff.cause_ids == [cause_int]


# ==============================================================================
# 场景 8: core.create_entity 提交路径 (P2-REMEDIATION B1)
# ==============================================================================


class TestScenario8CreateEntityEndToEnd:
    """场景 8（core.create_entity 提交路径；P2-REMEDIATION B1 修复验证）：

    - 单独 ``core.create_entity`` 提交成功（revision 恰 +1、实体落地、事件 1:1）；
    - 同事务先 ``create_entity`` 后 ``set_component`` 的**暂存依赖**：
      L2 终检零 ``missing_entity``、conflicts 不判冲突、reducer 按 sequence
      顺序应用落地；
    - create 已存在实体 → reducer 前置条件报错（非 missing_entity 语义）；
    - CascadeExecutor 级联端到端：create + component.set 同回合完整通过；
      create 事件触发后续回合对新实体的效果落地。
    """

    def test_create_entity_standalone_commit(self) -> None:
        """单独 create_entity：L2 不再误报 missing_entity，COMMITTED 且实体落地。"""
        state = _make_base_state(0)
        eff = _make_proposed_effect(
            "eff_create_solo",
            EFFECT_CREATE_ENTITY,
            EntityTarget(entity_id=EntityId("ent_summoned")),
            {"entity_class": "item", "tags": ["treasure"], "components": {}},
        )
        producer = Provenance(producer_id=ProducerId("rule.system"), origin=OriginKind.RULE)
        new_state, txn, events = commit_transaction(
            state, [eff], new_transaction_id(), producer
        )

        assert txn.status == TransactionStatus.COMMITTED
        assert txn.abort_reason is None
        assert txn.commit_revision == Revision(1)
        assert new_state.world_revision == Revision(1)
        rec = new_state.entities[EntityId("ent_summoned")]
        assert rec.entity_class == "item"
        assert rec.tags == ["treasure"]
        assert rec.created_revision == Revision(1), "created_revision 恒为 commit_revision"
        assert len(events) == 1, "事件 1:1 发射（D-P2-12）"
        assert state.has_entity(EntityId("ent_summoned")) is False, "输入状态零触碰"

    def test_create_existing_target_reports_precondition_not_missing_entity(self) -> None:
        """create 已存在实体：由 reducer 前置条件报错，不报 missing_entity。"""
        state = _make_base_state(0)
        eff = _make_proposed_effect(
            "eff_create_dup",
            EFFECT_CREATE_ENTITY,
            EntityTarget(entity_id=EntityId("ent_alice")),
            {},
        )
        producer = Provenance(producer_id=ProducerId("rule.system"), origin=OriginKind.RULE)
        new_state, txn, events = commit_transaction(
            state, [eff], new_transaction_id(), producer
        )

        assert txn.status == TransactionStatus.ABORTED
        assert txn.commit_revision is None
        assert "missing_entity" not in (txn.abort_reason or ""), (
            "已存在目标不是 missing_entity 语义"
        )
        assert "reducer_failed" in txn.abort_reason
        assert "已存在" in txn.abort_reason
        assert len(events) == 0
        assert new_state == state
        assert new_state.world_revision == Revision(0)

    def test_create_then_set_component_same_transaction(self) -> None:
        """同事务先 create 后 set_component：暂存依赖全链路放行。"""
        state = _make_base_state(0)
        eff_create = _make_proposed_effect(
            "eff_create_combo",
            EFFECT_CREATE_ENTITY,
            EntityTarget(entity_id=EntityId("ent_summoned")),
            {},
        )
        eff_set = _make_proposed_effect(
            "eff_init_component",
            EFFECT_SET_COMPONENT,
            EntityTarget(
                entity_id=EntityId("ent_summoned"),
                component_type=ComponentTypeId("space.position"),
            ),
            {"x": 5, "y": 7},
        )

        # L2 终检数据级口径：零问题（created_in_batch 语义）
        txn_id = new_transaction_id()
        producer = Provenance(producer_id=ProducerId("rule.system"), origin=OriginKind.RULE)
        new_state, txn, events = commit_transaction(
            state, [eff_create, eff_set], txn_id, producer
        )

        assert txn.status == TransactionStatus.COMMITTED
        assert txn.abort_reason is None
        assert txn.commit_revision == Revision(1)
        rec = new_state.entities[EntityId("ent_summoned")]
        assert rec.components == {ComponentTypeId("space.position"): {"x": 5, "y": 7}}
        assert len(events) == 2
        assert state.has_entity(EntityId("ent_summoned")) is False

    def test_create_then_set_component_l2_reference_check_clean(self) -> None:
        """check_transaction_references 直检：create + 同批引用 → 空报告。"""
        state = _make_base_state(0)
        eff_create = _make_proposed_effect(
            "eff_l2_create",
            EFFECT_CREATE_ENTITY,
            EntityTarget(entity_id=EntityId("ent_l2_new")),
            {},
        )
        eff_set = _make_proposed_effect(
            "eff_l2_set",
            EFFECT_SET_COMPONENT,
            EntityTarget(
                entity_id=EntityId("ent_l2_new"),
                component_type=ComponentTypeId("space.position"),
            ),
            {"x": 1, "y": 1},
        )
        txn_id = new_transaction_id()
        commit_revision = Revision(1)
        committed = [
            CommittedEffect(
                effect=effect,
                transaction_id=txn_id,
                commit_revision=commit_revision,
                sequence=sequence,
            )
            for sequence, effect in enumerate([eff_create, eff_set])
        ]
        txn = Transaction(
            transaction_id=txn_id,
            base_revision=Revision(0),
            commit_revision=commit_revision,
            status=TransactionStatus.COMMITTED,
            effects=committed,
            event_ids=[EventId("evt_l2_1"), EventId("evt_l2_2")],
        )
        assert check_transaction_references(state, txn) == ()

        # 对照：无 create 前导的悬空引用仍报 missing_entity（语义未放宽过度）
        dangling_txn_id = new_transaction_id()
        txn_dangling = Transaction(
            transaction_id=dangling_txn_id,
            base_revision=Revision(0),
            commit_revision=commit_revision,
            status=TransactionStatus.COMMITTED,
            effects=[
                CommittedEffect(
                    effect=eff_set,
                    transaction_id=dangling_txn_id,
                    commit_revision=commit_revision,
                    sequence=0,
                )
            ],
            event_ids=[EventId("evt_l2_3")],
        )
        issues = check_transaction_references(state, txn_dangling)
        assert issues == ("missing_entity:eff_l2_set:target=ent_l2_new",)

    def test_create_then_set_component_via_cascade_executor(self) -> None:
        """CascadeExecutor 端到端：create + component.set 同回合不被 conflicts
        判冲突、通过 L1/L2 与 reducer，成功落地且 revision 恰 +1。"""
        state = _make_base_state(0)
        eff_create = _make_proposed_effect(
            "eff_cas_create",
            EFFECT_CREATE_ENTITY,
            EntityTarget(entity_id=EntityId("ent_summoned")),
            {"entity_class": "item"},
            source="rule.system",
        )
        eff_set = _make_proposed_effect(
            "eff_cas_set",
            EFFECT_SET_COMPONENT,
            EntityTarget(
                entity_id=EntityId("ent_summoned"),
                component_type=ComponentTypeId("space.position"),
            ),
            {"x": 1, "y": 2},
            source="rule.system",
        )
        policy = AuthorityPolicy(
            rules=[
                AuthorityRule(
                    selector=AuthoritySelector(),
                    allowed_writers=[ProducerId("rule.system")],
                )
            ]
        )
        executor = CascadeExecutor(policy=policy)
        producer = Provenance(producer_id=ProducerId("rule.system"), origin=OriginKind.RULE)

        result = executor.run(
            [eff_create, eff_set], state, causal_root_id="act_summon", origin=producer
        )

        assert len(result.transactions) == 1
        txn = result.transactions[0]
        assert txn.status == TransactionStatus.COMMITTED
        assert txn.commit_revision == Revision(1)
        assert result.final_state.world_revision == Revision(1)
        rec = result.final_state.entities[EntityId("ent_summoned")]
        assert rec.entity_class == "item"
        assert rec.components == {ComponentTypeId("space.position"): {"x": 1, "y": 2}}
        assert len(result.events) == 2
        # 暂存依赖不判冲突：无 CONFLICT_RESOLUTION trace
        assert all(
            t.kind != TraceKind.CONFLICT_RESOLUTION for t in result.trace_records
        ), "create + 初始化 component.set 不应触发冲突仲裁"
        # L1 未过滤暂存依赖的 set_component
        validation_traces = [
            t for t in result.trace_records if t.kind == TraceKind.VALIDATION_DECISION
        ]
        assert all(t.payload["decision"] == "pass" for t in validation_traces)

    def test_cascade_trigger_followup_on_created_entity(self) -> None:
        """级联链：create_entity 事件触发第二回合对新实体的效果，完整落地。"""
        state = _make_base_state(0)

        def on_create(
            events: list[DomainEvent], s: GuardedWorldState, depth: int
        ) -> list[ProposedEffect]:
            res: list[ProposedEffect] = []
            if depth != 0:
                return []
            for event in events:
                if event.event_type != EFFECT_CREATE_ENTITY:
                    continue
                target = event.payload.get("target", {})
                entity_id = target.get("entity_id")
                if entity_id is None:
                    continue
                res.append(
                    _make_proposed_effect(
                        "eff_followup_init",
                        EFFECT_SET_COMPONENT,
                        EntityTarget(
                            entity_id=EntityId(entity_id),
                            component_type=ComponentTypeId("attrs.hp"),
                        ),
                        {"current": 10, "max": 10},
                        source="rule.responder",
                        base_revision=int(s.world_revision),
                        cause_ids=[
                            CauseRef(kind=CauseKind.EVENT, ref_id=str(event.event_id))
                        ],
                    )
                )
            return res

        policy = AuthorityPolicy(
            rules=[
                AuthorityRule(
                    selector=AuthoritySelector(),
                    allowed_writers=[ProducerId("rule.system"), ProducerId("rule.responder")],
                )
            ]
        )
        trig_reg = CascadeTriggerRegistry()
        trig_reg.register(SyncTrigger("on_create", on_create))
        executor = CascadeExecutor(policy=policy, triggers=trig_reg)

        eff_create = _make_proposed_effect(
            "eff_root_create",
            EFFECT_CREATE_ENTITY,
            EntityTarget(entity_id=EntityId("ent_summoned")),
            {},
            source="rule.system",
            base_revision=0,
        )
        producer = Provenance(producer_id=ProducerId("rule.system"), origin=OriginKind.RULE)
        result = executor.run(
            [eff_create], state, causal_root_id="act_summon_chain", origin=producer
        )

        # 两回合两事务：depth0 create，depth1 对新实体的组件初始化
        assert len(result.transactions) == 2
        assert all(
            txn.status == TransactionStatus.COMMITTED for txn in result.transactions
        )
        assert result.final_state.world_revision == Revision(2)
        rec = result.final_state.entities[EntityId("ent_summoned")]
        assert rec.components == {ComponentTypeId("attrs.hp"): {"current": 10, "max": 10}}
        for i, txn in enumerate(result.transactions):
            assert txn.base_revision == Revision(i)
            assert txn.commit_revision == Revision(i + 1)
            assert txn.cascade is not None
            assert txn.cascade.depth == i


# ==============================================================================
# G2 补充轮 2: 注册表纯快照化 + commit 路径一致性 (注册表条目不得解析活权威状态)
# ==============================================================================


class TestG2SupplementRound2RegistrySnapshot:
    """G2 补充轮 2 对抗回归：注册表条目纯快照化 + commit 路径一致性检查。

    上轮 G2 盲审一致发现：``guard()`` 实例唯一槽持 int token，token 可经
    ``object.__getattribute__`` 读出，模块级 ``_GUARD_REGISTRY[token].state``
    解析出**活**权威 WorldState（嵌套容器别名同源），原地突变静默成功——
    revision 不变、无事件/trace，级联下注入突变可随合法事务提交且无效果
    声明。本轮修复：注册表条目仅存 ``guard()`` 时刻经 JSON roundtrip 构造
    的深冻结快照（独立副本、零别名）——对条目快照的任何原地写只污染该条
    目自己的副本，权威状态不受影响。本类全部为**纯新增**断言，不改任何
    既有测试。
    """

    def _make_state(self, rev: int = 0) -> WorldState:
        """含实体（组件 dict）+ world_variables + scenario data 的测试状态。"""
        return WorldState(
            world_revision=Revision(rev),
            entities={
                EntityId("ent_alice"): EntityRecord(
                    entity_id=EntityId("ent_alice"),
                    components={
                        ComponentTypeId("attrs.hp"): {"current": 100, "max": 100},
                    },
                    entity_class="character",
                    tags=["hero"],
                )
            },
            world_variables={"gold": 10, "calendar": {"day": 1}},
            scenario_state=ScenarioState(scenario_id="s1", stage="night", data={"goal": "x"}),
        )

    def test_registry_entry_state_is_not_live_authority(self) -> None:
        """(1) 恒等性：取 token 后 ``reducer._GUARD_REGISTRY[tok].state is s``
        为 False——注册表条目持深冻结快照（独立副本），不再存活权威引用；
        全部嵌套容器零别名，但 guard() 时刻值相等（门面读值口径不变）。"""
        s = self._make_state(0)
        g = guard(s)
        tok = object.__getattribute__(g, "_GuardedWorldState__token")
        entry = reducer._GUARD_REGISTRY[tok]

        # 恒等性断言（任务 2.1：修复后恒成立）
        assert reducer._GUARD_REGISTRY[tok].state is not s
        # 嵌套容器零别名（快照为独立对象）
        assert entry.state.world_variables is not s.world_variables
        assert entry.state.world_variables["calendar"] is not s.world_variables["calendar"]
        assert (
            entry.state.entities[EntityId("ent_alice")].components[ComponentTypeId("attrs.hp")]
            is not s.entities[EntityId("ent_alice")].components[ComponentTypeId("attrs.hp")]
        )
        assert entry.state.scenario_state is not s.scenario_state
        assert entry.state.scenario_state.data is not s.scenario_state.data
        # guard() 时刻值相等（委托读取口径不变）
        assert entry.state == s

    def test_registry_entry_inplace_mutation_leaves_authority_untouched(self) -> None:
        """(2) 注册表条目原地突变（world_variables + 组件 dict）后，权威状态
        s 的内容 / revision / 事件 / trace 全部不变；注入突变不得随合法
        事务提交（提交产物只含已声明效果）。"""
        s = self._make_state(0)
        base_dump = s.model_dump(mode="json")
        g = guard(s)
        tok = object.__getattribute__(g, "_GuardedWorldState__token")
        entry = reducer._GUARD_REGISTRY[tok]

        # 经注册表条目原地突变（轮 1 机制下此处直接污染权威状态；
        # 快照化后只污染条目自己的副本）
        entry.state.world_variables["injected"] = 1
        entry.state.world_variables["calendar"]["day"] = 99
        entry.state.entities[EntityId("ent_alice")].components[ComponentTypeId("attrs.hp")][
            "current"
        ] = 1

        # 权威状态：内容 / revision 全不变
        assert s.model_dump(mode="json") == base_dump
        assert s.world_revision == Revision(0)
        # 注入突变只落在条目自己的快照副本上
        assert entry.state.world_variables["injected"] == 1
        assert entry.state.world_variables["calendar"]["day"] == 99

        # 合法事务提交：注入突变不得随提交落盘（无效果声明的变更不可达）
        new_state, txn, events = commit_transaction(
            s,
            [
                _make_proposed_effect(
                    "eff_legit",
                    EFFECT_SET_WORLD_VARIABLE,
                    StateDomainTarget(domain=StateDomainId("world_variables")),
                    {"key": "gold", "value": 5},
                    base_revision=0,
                )
            ],
            new_transaction_id(),
            Provenance(producer_id=ProducerId("rule.system"), origin=OriginKind.RULE),
        )
        assert txn.status == TransactionStatus.COMMITTED
        assert new_state.world_revision == Revision(1)
        # 提交产物只含已声明效果（gold=5）；注入键与组件突变零残留
        assert new_state.world_variables == {"gold": 5, "calendar": {"day": 1}}
        assert (
            new_state.entities[EntityId("ent_alice")].components[ComponentTypeId("attrs.hp")]
            == {"current": 100, "max": 100}
        )
        # 事件 1:1 对应已声明效果（无未声明变更产生的事件）
        assert len(events) == 1
        assert events[0].event_type == EFFECT_SET_WORLD_VARIABLE

    def test_producer_guard_only_token_registry_path_cannot_reach_live_state(self) -> None:
        """(3) producer 仅持 guard（不持任何原始引用）时，显式覆盖
        "token 读取 + 模块级 _GUARD_REGISTRY 解析"路径：解析出的条目上
        不存在活权威状态；条目全槽扫描无活状态引用/别名容器；对解析结果
        的原地写（快照可变性）只作用于副本。"""
        s = self._make_state(0)
        g = guard(s)
        base_dump = s.model_dump(mode="json")

        # producer 视角：只持有 guard 对象
        tok = object.__getattribute__(g, "_GuardedWorldState__token")
        assert isinstance(tok, int)
        entry = reducer._GUARD_REGISTRY[tok]

        # 条目任一槽都解析不出活权威状态 s（本体或别名容器）
        live_containers = (
            s,
            s.world_variables,
            s.world_variables["calendar"],
            s.entities,
            s.entities[EntityId("ent_alice")],
            s.entities[EntityId("ent_alice")].components[ComponentTypeId("attrs.hp")],
            s.scenario_state,
            s.scenario_state.data,
        )
        for slot in type(entry).__slots__:
            value = object.__getattribute__(entry, slot)
            assert not any(value is c for c in live_containers), f"槽 {slot} 解析出活权威容器"

        # 对解析结果的原地写（快照副本可变性）只作用于副本
        entry.state.world_variables["prod_injected"] = 42
        entry.state.entities[EntityId("ent_alice")].components[ComponentTypeId("attrs.hp")][
            "current"
        ] = 0
        assert s.model_dump(mode="json") == base_dump
        assert s.world_revision == Revision(0)
        assert entry.state.world_variables["prod_injected"] == 42

    def test_cascade_trigger_guard_only_no_undeclared_committed_change(self) -> None:
        """(4) 端到端：级联 trigger 仅持 guard 视图，经 "token → 注册表 →
        条目快照" 路径原地注入突变并正常提案已声明效果（与根提案不同
        location，避免 §7.5 环路熔断）——提交后权威状态无任何未声明字段
        变化（注入突变零落盘，声明效果正常落地）。"""
        s = self._make_state(0)
        base_dump = s.model_dump(mode="json")

        def inject_and_propose(
            events: list[DomainEvent], guarded: GuardedWorldState, depth: int
        ) -> list[ProposedEffect]:
            if depth != 0 or not events:
                return []
            # 注入者只有 guard 视图：经 token + 模块级注册表解析条目，
            # 对解析结果原地突变（轮 1 机制下污染权威状态并随提交落盘）
            tok = object.__getattribute__(guarded, "_GuardedWorldState__token")
            entry = reducer._GUARD_REGISTRY[tok]
            entry.state.world_variables["injected"] = "ghost"
            entry.state.world_variables["calendar"]["day"] = 999
            entry.state.entities[EntityId("ent_alice")].components[ComponentTypeId("attrs.hp")][
                "current"
            ] = 666
            return [
                _make_proposed_effect(
                    "eff_declared",
                    EFFECT_SET_COMPONENT,
                    EntityTarget(
                        entity_id=EntityId("ent_alice"),
                        component_type=ComponentTypeId("attrs.hp"),
                    ),
                    {"current": 10, "max": 10},
                    source="rule.responder",
                    base_revision=int(guarded.world_revision),
                    cause_ids=[CauseRef(kind=CauseKind.EVENT, ref_id=str(events[0].event_id))],
                )
            ]

        policy = AuthorityPolicy(
            rules=[
                AuthorityRule(
                    selector=AuthoritySelector(),
                    allowed_writers=[ProducerId("rule.system"), ProducerId("rule.responder")],
                )
            ]
        )
        trig_reg = CascadeTriggerRegistry()
        trig_reg.register(SyncTrigger("inject_and_propose", inject_and_propose))
        executor = CascadeExecutor(policy=policy, triggers=trig_reg)

        root = _make_proposed_effect(
            "eff_root",
            EFFECT_SET_WORLD_VARIABLE,
            StateDomainTarget(domain=StateDomainId("world_variables")),
            {"key": "seed", "value": 1},
            base_revision=0,
        )
        result = executor.run(
            [root],
            s,
            causal_root_id="act_ghost_inject",
            origin=Provenance(producer_id=ProducerId("rule.system"), origin=OriginKind.RULE),
        )

        # 两回合两事务（根提案 + 触发器声明效果），全部 COMMITTED
        assert len(result.transactions) == 2
        assert all(txn.status == TransactionStatus.COMMITTED for txn in result.transactions)
        assert result.final_state.world_revision == Revision(2)
        # 声明效果落地（hp 为声明值 {10,10}，非注入值 666）
        assert (
            result.final_state.entities[EntityId("ent_alice")].components[ComponentTypeId("attrs.hp")]
            == {"current": 10, "max": 10}
        )
        # 注入突变零落盘：最终状态 == 仅应用声明效果的期望形态
        expected = dict(base_dump)
        expected["world_revision"] = 2
        expected["world_variables"] = {"gold": 10, "calendar": {"day": 1}, "seed": 1}
        expected["entities"]["ent_alice"]["components"]["attrs.hp"] = {"current": 10, "max": 10}
        assert result.final_state.model_dump(mode="json") == expected
        # 逐事务核对：已提交效果集合 == 声明集合（无未声明变更进入事务）
        committed_ids = sorted(
            str(committed.effect.effect_id)
            for txn in result.transactions
            for committed in txn.effects
        )
        assert committed_ids == ["eff_declared", "eff_root"]

    def test_pickle_roundtrip_loaded_object_distinct_from_authority(self) -> None:
        """(5) E2 pickle 回归补强：载入对象与权威状态不同恒等（副本非
        权威实例本身），值相等、零别名——篡改载入副本不波及权威状态
        （与勘误 E2 实测口径一致）；guard 门面的 pickle 拦截由既有测试
        ``test_guard_all_reachable_paths_write_blocked_state_unchanged``
        覆盖（本类不重复、不改既有断言）。"""
        s = self._make_state(0)
        base_dump = s.model_dump(mode="json")

        loaded = pickle.loads(pickle.dumps(s))
        # 不同恒等 + 值相等
        assert loaded is not s
        assert loaded == s
        # 零别名：嵌套容器为独立对象
        assert loaded.world_variables is not s.world_variables
        assert (
            loaded.entities[EntityId("ent_alice")].components[ComponentTypeId("attrs.hp")]
            is not s.entities[EntityId("ent_alice")].components[ComponentTypeId("attrs.hp")]
        )
        # 篡改载入副本 → 权威状态零变化
        loaded.world_variables["gold"] = 999999
        loaded.entities[EntityId("ent_alice")].components[ComponentTypeId("attrs.hp")][
            "current"
        ] = -1
        assert s.model_dump(mode="json") == base_dump
        assert s.world_revision == Revision(0)

    def test_future_base_revision_direct_commit_rejected(self) -> None:
        """(6) 任务 4 回归：公开 commit_transaction 直接调用 + future
        base_revision（effect.base_revision > base 状态 world_revision）→
        原子拒绝（ABORTED，base_revision_mismatch 语义），不得静默提交出
        "已提交效果记录的 base_revision 与事务 base_revision 自相矛盾"
        的事务；状态 / revision 原样。"""
        s = self._make_state(0)
        base_dump = s.model_dump(mode="json")
        new_state, txn, events = commit_transaction(
            s,
            [
                _make_proposed_effect(
                    "eff_future",
                    EFFECT_SET_WORLD_VARIABLE,
                    StateDomainTarget(domain=StateDomainId("world_variables")),
                    {"key": "k", "value": 1},
                    base_revision=10,  # future：base 状态是 0
                )
            ],
            new_transaction_id(),
            Provenance(producer_id=ProducerId("rule.system"), origin=OriginKind.RULE),
        )
        assert txn.status == TransactionStatus.ABORTED
        assert "base_revision_mismatch" in txn.abort_reason
        assert txn.commit_revision is None and txn.effects == []
        assert events == []
        # 原子性：状态对象原样、内容不变
        assert new_state is s
        assert s.model_dump(mode="json") == base_dump
        assert s.world_revision == Revision(0)


# ==============================================================================
# G2 门禁静态代码扫描确认 (Plan §11 G2 / P2 §12)
# ==============================================================================


class TestG2StaticScanConfirmation:
    """G2 门禁静态扫描确认：
    1. 静态扫描整个 src/engine_v2/，断言没有任何直接修改状态的 public API
       （契约状态类口径 + P2-REMEDIATION B3 补强的全类口径）；
    2. 静态扫描整个 src/engine_v2/，断言没有任何对状态容器属性的直接
       下标写入（``__setitem__`` / ``__delitem__`` / 增量赋值形态，
       P2-REMEDIATION B3）；
    3. 静态断言 Reducer 纯函数绝不调用 LLM、不做语义推断。

    白名单纪律（P2 设计规范 §2.6.1 静态审计口径）：``reducer.py`` 是唯一
    授权的 authoritative state 变更机制（其 ``_WorkingWorld`` 私有暂存的
    就地应用与 ``state_*`` 纯函数为合法变更面），全类口径扫描中豁免。
    """

    #: 静态扫描白名单：reducer.py 为唯一授权变更机制（§2.6.1 口径）。
    _SCAN_WHITELIST: frozenset[str] = frozenset({"reducer.py"})

    #: 状态容器属性名词表：对这些属性的下标写入即"直接修改权威状态"。
    _STATE_CONTAINER_ATTRS: frozenset[str] = frozenset(
        {"entities", "world_variables", "scenario_state", "components", "data", "tags"}
    )

    #: 直接状态修改类 public 方法禁用词表。
    _FORBIDDEN_PUBLIC_METHODS: frozenset[str] = frozenset(
        {
            "set_entity",
            "remove_entity",
            "set_component",
            "remove_component",
            "set_world_variable",
            "remove_world_variable",
            "mutate",
            "update_state",
        }
    )

    #: 注册表条目权威数据属性词表（G2 补充轮 2）：``_GUARD_REGISTRY[...]``
    #: 索引后接以下任一属性访问即"直接注册表-状态访问"（绕过 guard 门面
    #: 的唯一授权读面）——含条目槽（``state`` / ``*_view``）与 WorldState
    #: 权威数据字段（``entities`` / ``world_variables`` / ``scenario_state``
    #: / ``world_revision`` / ``schema_version``）。
    _GUARD_REGISTRY_STATE_ATTRS: frozenset[str] = frozenset(
        {
            "state",
            "entities",
            "world_variables",
            "scenario_state",
            "entities_view",
            "world_variables_view",
            "scenario_view",
            "world_revision",
            "schema_version",
        }
    )

    def test_no_direct_authoritative_state_mutation_public_api(self) -> None:
        """扫描 src/engine_v2/ 内部所有 Python 文件，确认不存在直接修改 WorldState 实例属性的 Public 方法。"""
        forbidden_public_methods = set(self._FORBIDDEN_PUBLIC_METHODS)

        violations: list[str] = []
        for py_file in ENGINE_V2_DIR.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # 检查是否有类暴露了上述直接修改方法且不是纯函数/reducer
                    if node.name in ("WorldState", "EntityRecord", "RuntimeState"):
                        for item in node.body:
                            if isinstance(item, ast.FunctionDef):
                                if item.name in forbidden_public_methods and not item.name.startswith("_"):
                                    violations.append(f"{py_file.name}:{node.name}.{item.name}")

        assert not violations, f"发现违反 K2 的直接状态修改 Public API: {violations}"

    def test_no_public_mutator_api_on_any_class(self) -> None:
        """补强（P2-REMEDIATION B3）：禁用词表扩展到 src/engine_v2/ 的
        **全部类**（不限契约状态类），白名单外不得出现任何直接修改状态的
        public 方法名。"""
        violations: list[str] = []
        for py_file in ENGINE_V2_DIR.rglob("*.py"):
            if py_file.name in self._SCAN_WHITELIST:
                continue
            violations.extend(
                self._scan_public_mutator_api(
                    py_file.read_text(encoding="utf-8"), py_file.name
                )
            )

        assert not violations, (
            f"发现违反 K2 的直接状态修改 Public API（全类口径）: {violations}"
        )

    def test_no_direct_subscript_writes_to_state_containers(self) -> None:
        """补强（P2-REMEDIATION B3）：真实扫描 src/engine_v2/，断言白名单外
        无任何对状态容器属性的直接下标写入/删除/增量赋值。

        检测形态（ast.Subscript 作为赋值/删除目标，且被下标对象为状态容器
        属性访问）：``x.entities[k] = v`` / ``del x.world_variables[k]`` /
        ``record.components[ct] = d`` / ``scenario.data[k] += 1`` 等。局部
        变量名字下标（如 ``payload["entities"] = ...`` 的重建装配）不被误报
        ——只针对"属性访问 + 下标"的权威状态就地修改形态。
        """
        violations: list[str] = []
        for py_file in ENGINE_V2_DIR.rglob("*.py"):
            if py_file.name in self._SCAN_WHITELIST:
                continue
            violations.extend(
                self._scan_state_container_subscript_writes(
                    py_file.read_text(encoding="utf-8"), py_file.name
                )
            )

        assert not violations, (
            f"发现违反 K2 的状态容器直接下标写入: {violations}"
        )

    def test_strengthened_scanners_self_test_on_synthetic_source(self) -> None:
        """自测（与场景 6 静态审计同款纪律）：合成违规源码必须被两个补强
        扫描器捕获——证明扫描逻辑非空转；合法形态不误报。"""
        bad_source = (
            "class Evil:\n"
            "    def mutate_state(self, state, rec, ct):\n"
            '        state.entities["ent_x"] = None\n'
            '        del state.world_variables["gold"]\n'
            '        state.scenario_state.data["k"] = 1\n'
            "        rec.components[ct] += 1\n"
            "    def set_component(self, x):\n"
            "        pass\n"
        )
        sub_violations = self._scan_state_container_subscript_writes(bad_source)
        assert len(sub_violations) == 4
        assert any(".entities[...]" in v for v in sub_violations)
        assert any(".world_variables[...]" in v for v in sub_violations)
        assert any(".data[...]" in v for v in sub_violations)
        assert any(".components[...]" in v for v in sub_violations)

        api_violations = self._scan_public_mutator_api(bad_source)
        assert api_violations == ["<synthetic>:Evil.set_component"]

        # 合法形态不误报：局部名字下标的重建装配 / 私有方法 / 只读访问
        good_source = (
            "def rebuild(state):\n"
            '    payload = {"entities": {}}\n'
            '    payload["entities"] = {k: v for k, v in state.entities.items()}\n'
            "    return payload\n"
            "class Ok:\n"
            "    def _private_set_component(self):\n"
            "        pass\n"
        )
        assert self._scan_state_container_subscript_writes(good_source) == []
        assert self._scan_public_mutator_api(good_source) == []

    def test_no_direct_guard_registry_state_access(self) -> None:
        """新增（G2 补充轮 2）：静态扫描 src/engine_v2/，断言白名单外无任何
        "模块级 ``_GUARD_REGISTRY[...]`` 索引后接权威数据属性访问"——直接
        注册表-状态访问绕过 guard 门面的唯一授权读面（条目仅存 guard() 时刻
        深冻结快照；读快照亦属越权面，写快照会污染副本，且该访问形态本身
        即轮 1 "注册表持活引用"缝隙的回潮信号）。含经别名变量中转形态
        （``entry = _GUARD_REGISTRY[tok]`` → ``entry.state``）。"""
        violations: list[str] = []
        for py_file in ENGINE_V2_DIR.rglob("*.py"):
            if py_file.name in self._SCAN_WHITELIST:
                continue
            violations.extend(
                self._scan_guard_registry_state_access(
                    py_file.read_text(encoding="utf-8"), py_file.name
                )
            )

        assert not violations, (
            f"发现直接注册表-状态访问（K2：guard 门面是唯一授权读面）: {violations}"
        )

    def test_guard_registry_scanner_self_test_on_synthetic_source(self) -> None:
        """自测（同款纪律）：合成违规源码必须被注册表-状态访问扫描器捕获
        ——直接形态（模块限定 / 模块级名）与别名变量中转形态均命中；合法
        形态（guard 门面读面 / 非注册表下标）不误报。"""
        bad_source = (
            "import src.engine_v2.core.reducer as reducer_mod\n"
            "def direct_via_module(g):\n"
            '    tok = object.__getattribute__(g, "_GuardedWorldState__token")\n'
            "    v = reducer_mod._GUARD_REGISTRY[tok].state\n"
            "    return v\n"
            "def direct_module_level(g):\n"
            "    tok = 1\n"
            "    w = _GUARD_REGISTRY[tok].world_variables\n"
            "    e = _GUARD_REGISTRY[tok].entities\n"
            "    return w, e\n"
            "def via_alias(g):\n"
            "    tok = 2\n"
            "    entry = _GUARD_REGISTRY[tok]\n"
            "    s = entry.state\n"
            "    r = entry.world_revision\n"
            "    return s, r\n"
        )
        violations = self._scan_guard_registry_state_access(bad_source)
        # 直接形态 ×3（.state / .world_variables / .entities）+ 别名形态 ×2
        # （entry.state / entry.world_revision）
        assert len(violations) == 5
        assert any("reducer_mod" not in v and ".state" in v for v in violations)
        assert any(".world_variables" in v for v in violations)
        assert any(".entities" in v for v in violations)
        assert any(".world_revision" in v for v in violations)

        # 合法形态不误报：guard 门面读面 / 非注册表下标 / 注册表方法调用
        good_source = (
            "def read_via_facade(g):\n"
            "    v = g.world_variables\n"
            "    r = g.world_revision\n"
            "    return v, r\n"
            "def other_subscript(g):\n"
            "    m = _SOME_OTHER_REGISTRY[tok]\n"
            "    return m.state\n"
            "def registry_method_call(g):\n"
            "    entry = _GUARD_REGISTRY.get(tok)\n"
            "    return entry\n"
        )
        assert self._scan_guard_registry_state_access(good_source) == []

    @classmethod
    def _scan_public_mutator_api(cls, source: str, filename: str = "<synthetic>") -> list[str]:
        """全类口径 public 状态修改方法扫描器（白名单由调用方应用）。"""
        violations: list[str] = []
        tree = ast.parse(source, filename=filename)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if (
                    isinstance(item, ast.FunctionDef)
                    and item.name in cls._FORBIDDEN_PUBLIC_METHODS
                ):
                    violations.append(f"{filename}:{node.name}.{item.name}")
        return violations

    @classmethod
    def _scan_state_container_subscript_writes(
        cls, source: str, filename: str = "<synthetic>"
    ) -> list[str]:
        """状态容器属性下标写入扫描器（Assign / AugAssign / Delete 三形态）。"""
        violations: list[str] = []
        tree = ast.parse(source, filename=filename)
        for node in ast.walk(tree):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AugAssign):
                targets = [node.target]
            elif isinstance(node, ast.Delete):
                targets = list(node.targets)
            else:
                continue
            for target in targets:
                for sub in ast.walk(target):
                    if (
                        isinstance(sub, ast.Subscript)
                        and isinstance(sub.value, ast.Attribute)
                        and sub.value.attr in cls._STATE_CONTAINER_ATTRS
                    ):
                        violations.append(
                            f"{filename}:{sub.lineno}: 直接下标写入 "
                            f".{sub.value.attr}[...]（K2：状态只能经 reducer 变更）"
                        )
        return violations

    @classmethod
    def _scan_guard_registry_state_access(cls, source: str, filename: str = "<synthetic>") -> list[str]:
        """注册表-状态直接访问扫描器（G2 补充轮 2；AST 静态口径）。

        检测形态（白名单由调用方应用）：

        1. **直接形态**：``_GUARD_REGISTRY[...]`` / ``mod._GUARD_REGISTRY[...]``
           索引后**立即**接权威数据属性访问——
           ``reducer._GUARD_REGISTRY[tok].state`` /
           ``_GUARD_REGISTRY[tok].world_variables`` 等（ast.Attribute 的
           value 为注册表名的 ast.Subscript）；
        2. **别名变量中转形态**：``entry = _GUARD_REGISTRY[tok]``（含模块
           限定）赋值后，对别名 Name 的权威数据属性访问——``entry.state`` /
           ``entry.entities`` / ``entry.world_revision`` 等。

        合法形态不误报：guard 门面读面（``g.world_variables``——value 为
        Name/Call 而非常规注册表下标）、非注册表名的下标、注册表方法
        调用（``_GUARD_REGISTRY.get(...)`` 为 Attribute 而非 Subscript 于
        注册表名，不产生别名）。
        """
        violations: list[str] = []
        tree = ast.parse(source, filename=filename)

        def _is_registry_base(node: ast.expr) -> bool:
            if isinstance(node, ast.Name):
                return node.id == "_GUARD_REGISTRY"
            if isinstance(node, ast.Attribute):
                return node.attr == "_GUARD_REGISTRY"
            return False

        alias_vars: set[str] = set()
        for node in ast.walk(tree):
            # 别名收集：entry = _GUARD_REGISTRY[tok]（含模块限定形态）
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Subscript)
                and _is_registry_base(node.value.value)
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        alias_vars.add(target.id)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr not in cls._GUARD_REGISTRY_STATE_ATTRS:
                continue
            base = node.value
            if isinstance(base, ast.Subscript) and _is_registry_base(base.value):
                violations.append(
                    f"{filename}:{node.lineno}: 直接注册表-状态访问 "
                    f"_GUARD_REGISTRY[...].{node.attr}（K2：guard 门面是唯一授权读面）"
                )
            elif isinstance(base, ast.Name) and base.id in alias_vars:
                violations.append(
                    f"{filename}:{node.lineno}: 经注册表别名变量中转的 "
                    f"权威数据属性访问 .{node.attr}（K2：guard 门面是唯一授权读面）"
                )
        return violations

    def test_reducer_pure_function_no_llm_imports_or_calls(self) -> None:
        """静态断言 reducer.py 纯函数绝不调用 LLM（无 provider/llm/network import），无语义推断。"""
        reducer_file = ENGINE_V2_DIR / "core" / "reducer.py"
        tree = ast.parse(reducer_file.read_text(encoding="utf-8"), filename=str(reducer_file))

        forbidden_import_prefixes = (
            "openai",
            "anthropic",
            "langchain",
            "langgraph",
            "src.engine_v2.llm",
            "src.engine_v2.prompts",
            "urllib",
            "requests",
            "httpx",
            "aiohttp",
        )

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(alias.name.startswith(p) for p in forbidden_import_prefixes), (
                        f"reducer.py 出现非法 LLM/网络 import: {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert not any(mod.startswith(p) for p in forbidden_import_prefixes), (
                    f"reducer.py 出现非法 LLM/网络 import: {mod}"
                )

    def test_reducer_rejects_unregistered_semantic_effects_deterministically(self) -> None:
        """行为验证：Reducer 不做语义推断，遇到未注册 effect_type 一律抛出 ReducerError，无静默回退或插值。"""
        handlers = default_handler_registry()
        unregistered_effect = ProposedEffect(
            effect_id=EffectId("eff_infer_test"),
            effect_type=EffectTypeId("semantic.magic_heal"),
            target=EntityTarget(entity_id=EntityId("ent_alice"), component_type=ComponentTypeId("attrs.hp")),
            payload={"heal_amount": 50},
            source=ProducerId("rule.system"),
            base_revision=Revision(0),
        )

        assert handlers.resolve(unregistered_effect.effect_type) is None
