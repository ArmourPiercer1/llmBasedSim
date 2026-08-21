"""P2-T06 Transaction 装配与原子提交执行器验收（P2 设计规范 §6 全量）。

覆盖（任务包 P2-T06 测试要求逐项落位）：

- **事务装配与原子提交流程**（D-P2-02/D-P2-12，§6.2/§6.4）：
  非空守卫（空 accepted_effects → ValueError，不消耗 revision）；
  COMMITTED 事务数据形态（``commit_revision == base + 1``、sequence
  0..n-1、effects/event_ids 共享不变量、事务级 provenance / cascade /
  logical_tick 承载）；提交后世界 revision **恰 +1**（Spec §9，Plan 必须
  测试 4）；事务内顺序依赖合法（先 create 后 set_component，暂存可见性）；
  **事件发射 1:1 映射**（``event_type == effect_type`` 且类型重建为
  ``EventTypeId``、``world_revision == commit_revision``、``cause_ids`` =
  EFFECT 自引用前置 + 提案原 cause_ids 原样拼接、``source_system`` /
  事件级 provenance（registry origin 解析 / 缺省 SYSTEM）/ cascade /
  logical_tick 透传、payload 最小事实载荷）；
- **原子失败**（Plan 必须测试 3，D-P2-10，§6.3）：L2 终检
  ``missing_entity`` / ``stale_revision``（多问题 ``"; "`` 串接格式）→
  整事务 ABORTED；reducer 应用失败（``EffectApplicationError`` 携 seq →
  ``reducer_failed[seq=<i>]: <detail>``）/ 批级 ``ReducerError``（未注册
  effect_type → ``reducer_failed: <detail>``）→ 整事务 ABORTED；ABORTED
  数据形态（``commit_revision is None``、``effects == []``、
  ``event_ids == []``、``abort_reason`` 非空）；返回状态**原样**（同一
  对象 + revision 不动 + 部分提交在任何断言面不可观测）；同批重复
  effect_id → Transaction 构造期不变量 ValueError（KBC-2，构造期不变量
  自动生效，部分提交同样不可达）；
- **零别名与不可变保证**（任务包目标 2）：成功路径新状态与原状态双向
  零别名（容器 + 嵌套 dict 双层，修改任一侧不波及另一侧）；失败路径
  返回原状态对象；输入 ProposedEffect 批次不被污染；同一 base 两次
  提交产物独立（分支独立）；
- **导出面**（D-P2-19 / §10.3）：``from src.engine_v2.core import
  commit_transaction / abort_transaction`` 直接可用且与模块定义为同一
  对象；模块 ``__all__`` 恰为两个公开函数。
- **core.create_entity 提交路径**（P2-REMEDIATION B1）：单独 create 提交
  成功（L2 终检不再误报 missing_entity）；同事务先 create 后
  set_component 的暂存依赖全链路放行；create 已存在实体由 reducer 前置
  条件报错（非 missing_entity 语义）。

全部用例无网络、无 LLM、无 API key。
"""

from __future__ import annotations

from typing import Any

import pytest

from src.engine_v2.core import (
    abort_transaction as pkg_abort_transaction,
    commit_transaction as pkg_commit_transaction,
)
from src.engine_v2.core.authority import ProducerInfo, ProducerRegistry
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.effects import (
    EffectTypeId,
    EntityTarget,
    ProposedEffect,
    StateDomainId,
    StateDomainTarget,
)
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.events import DomainEvent, EventTypeId
from src.engine_v2.core.ids import (
    CascadeId,
    EffectId,
    EntityId,
    ProducerId,
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
from src.engine_v2.core.state import ScenarioState, WorldState
from src.engine_v2.core.transaction import TransactionStatus
from src.engine_v2.core.transaction_executor import (
    abort_transaction,
    commit_transaction,
)


# —— 确定性构造助手（与 test_reducer.py 同款纪律：固定 ID 词表、无墙钟）——


def _base_state(world_revision: int = 0) -> WorldState:
    """确定性基线世界：2 实体（各 1 组件）+ 嵌套世界变量 + scenario 信封。"""
    return WorldState(
        world_revision=Revision(world_revision),
        entities={
            EntityId("ent_alice"): EntityRecord(
                entity_id=EntityId("ent_alice"),
                entity_class="npc",
                tags=["shopkeeper"],
                created_revision=Revision(0),
                components={
                    ComponentTypeId("space.position"): {"x": 1, "y": 2},
                },
            ),
            EntityId("ent_bob"): EntityRecord(
                entity_id=EntityId("ent_bob"),
                entity_class="player",
                tags=[],
                created_revision=Revision(0),
                components={
                    ComponentTypeId("knowledge.belief"): {"facts": []},
                },
            ),
        },
        world_variables={
            "calendar": {"day": 3, "hour": 12},
            "gold": 0,
        },
        scenario_state=ScenarioState(
            scenario_id="scn_main", stage="act1", data={"goal": "find the key"}
        ),
    )


def _entity_target(eid: str, component_type: str | None = None) -> EntityTarget:
    return EntityTarget(
        entity_id=EntityId(eid),
        component_type=ComponentTypeId(component_type) if component_type else None,
    )


def _domain_target(domain: str) -> StateDomainTarget:
    return StateDomainTarget(domain=StateDomainId(domain))


def _producer() -> Provenance:
    """事务级 Provenance（装配者）。"""
    return Provenance(producer_id=ProducerId("dev.kernel"), origin=OriginKind.SYSTEM)


def _cascade_ctx() -> CascadeContext:
    return CascadeContext(
        cascade_id=CascadeId("csl_t06"), causal_root_id="act_t06_root", depth=1
    )


class _EffectFactory:
    """确定性效果构造：eff_t06 id 按工厂序号唯一；固定 producer。"""

    def __init__(self) -> None:
        self._n = 0

    def proposed(
        self,
        effect_type: str,
        target: EntityTarget | StateDomainTarget,
        payload: dict[str, Any],
        *,
        base_revision: int = 0,
        source: str = "rule.test",
        cause_ids: list[CauseRef] | None = None,
    ) -> ProposedEffect:
        self._n += 1
        return ProposedEffect(
            effect_id=EffectId(f"eff_t06_{self._n:03d}"),
            effect_type=EffectTypeId(effect_type),
            source=ProducerId(source),
            target=target,
            payload=payload,
            base_revision=Revision(base_revision),
            cause_ids=list(cause_ids or []),
        )


@pytest.fixture()
def f() -> _EffectFactory:
    return _EffectFactory()


def _happy_effects(f: _EffectFactory, *, base_revision: int = 0) -> list[ProposedEffect]:
    """三条合法结构效果（世界变量 / 组件 / scenario 整体替换），base 与状态
    一致，且全部 target 在基线状态中可判定（L2 终检通过，§6.2 步骤 6）。"""
    return [
        f.proposed(
            "core.set_world_variable",
            _domain_target("world_variables"),
            {"key": "gold", "value": 10},
            base_revision=base_revision,
        ),
        f.proposed(
            "core.set_component",
            _entity_target("ent_alice", "space.position"),
            {"x": 9, "y": 9},
            base_revision=base_revision,
        ),
        f.proposed(
            "core.set_scenario_data",
            _domain_target("scenario"),
            {
                "scenario_id": "scn_main",
                "stage": "act2",
                "data": {"goal": "found the key", "depth": 1},
            },
            base_revision=base_revision,
        ),
    ]


class TestCommitTransactionHappyPath:
    """成功路径：装配 + 终检通过 + reducer 应用 + 事件 1:1 发射（§6.2/§6.4）。"""

    def test_empty_accepted_effects_rejected(self) -> None:
        """步骤 1 非空守卫：空批次 ValueError，revision 不消耗（P1 §5.6 镜像）。"""
        state = _base_state(0)
        snapshot = state.model_dump(mode="json")
        with pytest.raises(ValueError, match="空 accepted_effects"):
            commit_transaction(state, [], TransactionId("txn_t06_empty"), _producer())
        assert state.model_dump(mode="json") == snapshot, "空批次守卫不得触碰状态"
        assert state.world_revision == Revision(0)

    def test_commit_txn_shape_and_revision_exactly_plus_one(self, f: _EffectFactory) -> None:
        """COMMITTED 事务数据形态 + revision 恰 +1（Spec §9；必须测试 4）。"""
        state = _base_state(0)
        effects = _happy_effects(f)
        tx_id = TransactionId("txn_t06_ok")
        producer = _producer()
        cascade = _cascade_ctx()
        new_state, txn, events = commit_transaction(
            state, effects, tx_id, producer, logical_tick=7, cascade=cascade
        )
        # 事务形态（P1 §5.6 不变量在返回对象上复检）
        assert txn.status is TransactionStatus.COMMITTED
        assert txn.transaction_id == tx_id
        assert txn.base_revision == Revision(0)
        assert txn.commit_revision == Revision(1), "commit_revision 必须恰为 base + 1"
        assert new_state.world_revision == Revision(1), "世界 revision 恰 +1"
        assert txn.abort_reason is None
        # effects：sequence 0..n-1、共享 transaction_id / commit_revision
        assert [e.sequence for e in txn.effects] == [0, 1, 2]
        assert all(e.transaction_id == tx_id for e in txn.effects)
        assert all(e.commit_revision == Revision(1) for e in txn.effects)
        assert [str(e.effect.effect_id) for e in txn.effects] == [
            str(e.effect_id) for e in effects
        ]
        # 事务级承载：provenance / logical_tick / cascade 原样
        assert txn.provenance is producer
        assert txn.logical_tick == 7
        assert txn.cascade == cascade
        # 事件 1:1（D-P2-12）：数量一致、ID 唯一、与 txn.event_ids 对齐
        assert len(events) == 3
        assert len(set(ev.event_id for ev in events)) == 3
        assert [ev.event_id for ev in events] == txn.event_ids
        assert txn.event_ids[0] == events[0].event_id

    def test_commit_state_content_applied(self, f: _EffectFactory) -> None:
        """状态内容：世界变量整值替换 / 组件整体替换 / scenario 整体替换。"""
        state = _base_state(0)
        effects = _happy_effects(f)
        new_state, txn, _ = commit_transaction(
            state, effects, TransactionId("txn_c1"), _producer()
        )
        assert new_state.world_variables["gold"] == 10
        assert new_state.component_view(
            EntityId("ent_alice"), ComponentTypeId("space.position")
        ) == {"x": 9, "y": 9}
        # scenario 整体替换（Kernel 只给信封，语义归 P9）
        assert new_state.scenario_state == ScenarioState(
            scenario_id="scn_main", stage="act2", data={"goal": "found the key", "depth": 1}
        )
        # 未触及的世界事实原样保留
        assert new_state.world_variables["calendar"] == {"day": 3, "hour": 12}

    def test_commit_defaults_none_tick_and_cascade(self, f: _EffectFactory) -> None:
        """logical_tick / cascade 缺省 None 透传（D-P2-18：P2 不拥有时钟）。"""
        state = _base_state(0)
        effects = _happy_effects(f)
        new_state, txn, events = commit_transaction(
            state, effects, TransactionId("txn_d1"), _producer()
        )
        assert new_state.world_revision == Revision(1)
        assert txn.logical_tick is None
        assert txn.cascade is None
        assert all(ev.logical_tick is None for ev in events)
        assert all(ev.cascade is None for ev in events)

    def test_sequential_dependency_in_transaction(self, f: _EffectFactory) -> None:
        """事务内顺序依赖合法：reducer 按 sequence 在暂存上应用，顺序敏感
        的批次成功提交（§2.4 步骤 3；L2 终检通过——两个 target 均在基线
        状态中，C2 逐字语义下合法）。

        批次：seq0 remove_component(ent_bob) → seq1 remove_entity(ent_bob)。
        若按 seq1→seq0 顺序应用则 seq0 必失败（实体已删）——本用例固化
        "顺序敏感批次经提交路径成功"的暂存可见性。
        """
        state = _base_state(0)
        effects = [
            f.proposed(
                "core.remove_component", _entity_target("ent_bob", "knowledge.belief"), {}
            ),
            f.proposed("core.remove_entity", _entity_target("ent_bob"), {}),
        ]
        new_state, txn, events = commit_transaction(
            state, effects, TransactionId("txn_seq"), _producer()
        )
        assert txn.status is TransactionStatus.COMMITTED
        assert not new_state.has_entity(EntityId("ent_bob")), "顺序应用后实体应已删除"
        assert new_state.has_entity(EntityId("ent_alice"))
        assert len(events) == 2

    def test_create_entity_standalone_commits(self, f: _EffectFactory) -> None:
        """P2-REMEDIATION B1：单独 core.create_entity 提交成功（L2 终检不再
        误报 missing_entity），revision 恰 +1、实体落地、事件 1:1。"""
        state = _base_state(0)
        effect = f.proposed(
            "core.create_entity",
            _entity_target("ent_summoned"),
            {"entity_class": "item", "tags": ["treasure"], "components": {}},
        )
        new_state, txn, events = commit_transaction(
            state, [effect], TransactionId("txn_cr1"), _producer()
        )
        assert txn.status is TransactionStatus.COMMITTED
        assert txn.abort_reason is None
        assert txn.commit_revision == Revision(1)
        assert new_state.world_revision == Revision(1)
        rec = new_state.entities[EntityId("ent_summoned")]
        assert rec.entity_class == "item"
        assert rec.tags == ["treasure"]
        assert rec.created_revision == Revision(1)
        assert len(events) == 1
        assert events[0].event_type == effect.effect_type
        assert state.has_entity(EntityId("ent_summoned")) is False, "输入状态零触碰"

    def test_create_then_set_component_staged_dependency_commits(
        self, f: _EffectFactory
    ) -> None:
        """P2-REMEDIATION B1：同事务先 create_entity 后 set_component 的暂存
        依赖——L2 终检通过（created_in_batch）、reducer 按 sequence 应用落地。"""
        state = _base_state(0)
        create = f.proposed(
            "core.create_entity", _entity_target("ent_summoned"), {"entity_class": "npc"}
        )
        init_component = f.proposed(
            "core.set_component",
            _entity_target("ent_summoned", "space.position"),
            {"x": 5, "y": 7},
        )
        new_state, txn, events = commit_transaction(
            state, [create, init_component], TransactionId("txn_cr2"), _producer()
        )
        assert txn.status is TransactionStatus.COMMITTED
        assert txn.abort_reason is None
        assert txn.commit_revision == Revision(1)
        rec = new_state.entities[EntityId("ent_summoned")]
        assert rec.components == {ComponentTypeId("space.position"): {"x": 5, "y": 7}}
        assert len(events) == 2
        assert state.has_entity(EntityId("ent_summoned")) is False

    def test_create_existing_entity_aborts_on_precondition_not_missing(
        self, f: _EffectFactory
    ) -> None:
        """create 已存在实体：reducer 前置条件报错（非 missing_entity 语义），
        整事务原子 ABORTED。"""
        state = _base_state(0)
        effect = f.proposed("core.create_entity", _entity_target("ent_alice"), {})
        new_state, txn, events = commit_transaction(
            state, [effect], TransactionId("txn_cr3"), _producer()
        )
        assert new_state is state
        assert txn.status is TransactionStatus.ABORTED
        assert txn.commit_revision is None and txn.effects == []
        assert events == []
        assert "missing_entity" not in (txn.abort_reason or "")
        assert txn.abort_reason.startswith("reducer_failed[seq=0]: ")
        assert "已存在" in txn.abort_reason

    def test_repeated_commits_deterministic_state(self, f: _EffectFactory) -> None:
        """同一输入两次提交 → 世界状态确定性一致（事件 ID 为身份不参与相等）。"""
        effects_a = _happy_effects(_EffectFactory())
        effects_b = _happy_effects(_EffectFactory())
        assert all(a == b for a, b in zip(effects_a, effects_b))
        state_a, txn_a, _ = commit_transaction(
            _base_state(0), effects_a, TransactionId("txn_det_a"), _producer()
        )
        state_b, txn_b, _ = commit_transaction(
            _base_state(0), effects_b, TransactionId("txn_det_a"), _producer()
        )
        assert state_a == state_b
        assert state_a.model_dump(mode="json") == state_b.model_dump(mode="json")
        assert txn_a.base_revision == txn_b.base_revision
        assert txn_a.commit_revision == txn_b.commit_revision


class TestEventEmissionMapping:
    """D-P2-12 事件发射 1:1 映射（§6.4）：逐字段程序化断言（必须测试 5 口径）。"""

    def test_event_type_one_to_one_with_effect_type(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        effects = _happy_effects(f)
        _, _, events = commit_transaction(state, effects, TransactionId("txn_ev1"), _producer())
        assert len(events) == len(effects)
        for event, effect in zip(events, effects):
            assert event.event_type == effect.effect_type, (
                "event_type 必须与 effect_type 1:1 对齐（D-P2-12）"
            )
            assert type(event.event_type) is EventTypeId, "类型必须重建为 EventTypeId"

    def test_event_k6_fields(self, f: _EffectFactory) -> None:
        """K6 六要素：transaction_id / world_revision / source_system / cause_ids 等。"""
        state = _base_state(0)
        original_causes = [
            CauseRef(kind=CauseKind.ACTION, ref_id="act_t06_root"),
            CauseRef(kind=CauseKind.PROPOSAL, ref_id="act_t06_root"),
        ]
        effect = f.proposed(
            "core.set_world_variable",
            _domain_target("world_variables"),
            {"key": "gold", "value": 1},
            cause_ids=original_causes,
        )
        cascade = _cascade_ctx()
        _, _, events = commit_transaction(
            state, [effect], TransactionId("txn_k6"), _producer(), logical_tick=11, cascade=cascade
        )
        event: DomainEvent = events[0]
        assert event.world_revision == Revision(1), "world_revision == 事务 commit_revision"
        assert event.transaction_id == TransactionId("txn_k6")
        assert event.source_system == effect.source, "source_system = 提案者（谁提出）"
        assert event.logical_tick == 11
        assert event.cascade == cascade
        # cause_ids：EFFECT 自引用前置 + 原 cause_ids 原样拼接
        assert event.cause_ids[0] == CauseRef(kind=CauseKind.EFFECT, ref_id=str(effect.effect_id))
        assert event.cause_ids[1:] == original_causes
        # payload：最小事实载荷（effect_id + target JSON 形态）
        assert event.payload == {
            "effect_id": str(effect.effect_id),
            "target": effect.target.model_dump(mode="json"),
        }

    def test_event_provenance_from_producer_registry(self, f: _EffectFactory) -> None:
        """事件级 provenance：origin 经 producer_registry.origin_of 解析。"""
        state = _base_state(0)
        registry = ProducerRegistry()
        registry.register(
            ProducerInfo(producer_id=ProducerId("rule.test"), origin=OriginKind.RULE)
        )
        registry.register(
            ProducerInfo(producer_id=ProducerId("scenario.quest"), origin=OriginKind.SCENARIO)
        )
        effects = [
            f.proposed(
                "core.set_world_variable",
                _domain_target("world_variables"),
                {"key": "gold", "value": 1},
                source="rule.test",
            ),
            f.proposed(
                "core.set_world_variable",
                _domain_target("world_variables"),
                {"key": "gold", "value": 2},
                source="scenario.quest",
            ),
        ]
        _, _, events = commit_transaction(
            state, effects, TransactionId("txn_prov"), _producer(), producer_registry=registry
        )
        assert events[0].provenance.producer_id == ProducerId("rule.test")
        assert events[0].provenance.origin is OriginKind.RULE
        assert events[1].provenance.producer_id == ProducerId("scenario.quest")
        assert events[1].provenance.origin is OriginKind.SCENARIO

    def test_event_provenance_default_origin_without_registry(self, f: _EffectFactory) -> None:
        """producer_registry 缺省 → 事件 origin 恒 SYSTEM（origin_of 缺省语义）。"""
        state = _base_state(0)
        effects = [
            f.proposed(
                "core.set_world_variable",
                _domain_target("world_variables"),
                {"key": "gold", "value": 1},
            )
        ]
        _, _, events = commit_transaction(state, effects, TransactionId("txn_prov2"), _producer())
        assert events[0].provenance.producer_id == ProducerId("rule.test")
        assert events[0].provenance.origin is OriginKind.SYSTEM


class TestAtomicFailure:
    """原子失败（必须测试 3；D-P2-10 L2 语义，§6.3）：ABORTED + 状态原样。"""

    def test_reference_check_missing_entity_aborts(self, f: _EffectFactory) -> None:
        """L2 终检：missing_entity → 整事务 ABORTED（绕过 L1 过滤模拟外部批次）。"""
        state = _base_state(0)
        effect = f.proposed("core.remove_entity", _entity_target("ent_ghost"), {})
        base_dump = state.model_dump(mode="json")
        new_state, txn, events = commit_transaction(
            state, [effect], TransactionId("txn_miss"), _producer()
        )
        assert new_state is state, "失败必须原样返回原状态对象"
        assert state.model_dump(mode="json") == base_dump
        assert state.world_revision == Revision(0), "ABORTED 不递增 revision"
        assert txn.status is TransactionStatus.ABORTED
        assert txn.transaction_id == TransactionId("txn_miss")
        assert txn.base_revision == Revision(0)
        assert txn.commit_revision is None
        assert txn.effects == []
        assert txn.event_ids == []
        assert events == []
        assert txn.abort_reason == (
            f"reference_check_failed: missing_entity:{effect.effect_id}:target=ent_ghost"
        )

    def test_reference_check_stale_revision_aborts(self, f: _EffectFactory) -> None:
        """L2 终检：stale 批次（base_revision 落后于 state）→ 整事务 ABORTED。"""
        state = _base_state(2)
        effect = f.proposed(
            "core.set_world_variable",
            _domain_target("world_variables"),
            {"key": "gold", "value": 7},
            base_revision=0,  # 提案时的版本，状态已前进到 2
        )
        new_state, txn, events = commit_transaction(
            state, [effect], TransactionId("txn_stale"), _producer()
        )
        assert new_state is state
        assert state.world_revision == Revision(2)
        assert txn.status is TransactionStatus.ABORTED
        assert txn.commit_revision is None and txn.effects == []
        assert events == []
        assert txn.abort_reason == (
            f"reference_check_failed: stale_revision:{effect.effect_id}:base=0 current=2"
        )

    def test_reference_check_multi_issues_semicolon_joined(self, f: _EffectFactory) -> None:
        """多问题串接格式："reference_check_failed: " + "; ".join(issues)。"""
        state = _base_state(2)
        e1 = f.proposed("core.remove_entity", _entity_target("ent_ghost"), {}, base_revision=2)
        e2 = f.proposed(
            "core.remove_entity", _entity_target("ent_alice"), {}, base_revision=1
        )
        _, txn, _ = commit_transaction(state, [e1, e2], TransactionId("txn_multi"), _producer())
        assert txn.status is TransactionStatus.ABORTED
        assert txn.abort_reason == (
            "reference_check_failed: "
            f"missing_entity:{e1.effect_id}:target=ent_ghost"
            f"; stale_revision:{e2.effect_id}:base=1 current=2"
        )

    def test_reducer_failure_aborts_with_seq(self, f: _EffectFactory) -> None:
        """reducer 失败源 2：seq0 remove 后 seq1 对同一实体 set_component → ABORTED。"""
        state = _base_state(0)
        e1 = f.proposed("core.remove_entity", _entity_target("ent_bob"), {})
        e2 = f.proposed(
            "core.set_component",
            _entity_target("ent_bob", "knowledge.belief"),
            {"facts": []},
        )
        base_dump = state.model_dump(mode="json")
        new_state, txn, events = commit_transaction(
            state, [e1, e2], TransactionId("txn_red"), _producer()
        )
        assert new_state is state
        assert state.model_dump(mode="json") == base_dump
        assert state.world_revision == Revision(0)
        assert txn.status is TransactionStatus.ABORTED
        assert txn.commit_revision is None and txn.effects == []
        assert events == []
        assert txn.abort_reason == (
            "reducer_failed[seq=1]: core.set_component 前置条件不满足：entity 不存在：ent_bob"
        )

    def test_unregistered_semantic_effect_type_aborts(self, f: _EffectFactory) -> None:
        """批级 ReducerError（未注册 effect_type，不推断）→ ABORTED 且格式无 seq。"""
        state = _base_state(0)
        effect = f.proposed(
            "combat.attack", _entity_target("ent_alice"), {"target": "ent_bob", "dmg": 5}
        )
        new_state, txn, events = commit_transaction(
            state, [effect], TransactionId("txn_nohandler"), _producer()
        )
        assert new_state is state
        assert txn.status is TransactionStatus.ABORTED
        assert txn.commit_revision is None and txn.effects == []
        assert events == []
        assert txn.abort_reason.startswith("reducer_failed: ")
        assert "未注册 effect_type: combat.attack" in txn.abort_reason

    def test_duplicate_effect_id_rejected_at_construction(self, f: _EffectFactory) -> None:
        """同批重复 effect_id：Transaction 构造期不变量 ValueError（KBC-2，§6.2 步骤 5）。"""
        state = _base_state(0)
        effect = f.proposed(
            "core.set_world_variable",
            _domain_target("world_variables"),
            {"key": "gold", "value": 5},
        )
        base_dump = state.model_dump(mode="json")
        with pytest.raises(ValueError, match="重复"):
            commit_transaction(state, [effect, effect], TransactionId("txn_dup"), _producer())
        assert state.model_dump(mode="json") == base_dump
        assert state.world_revision == Revision(0)

    def test_no_partial_commit_observable(self, f: _EffectFactory) -> None:
        """部分提交在任何断言面不可观测：seq0 有效 + seq1 缺失目标 → 全部不落盘。"""
        state = _base_state(0)
        e1 = f.proposed(
            "core.set_world_variable",
            _domain_target("world_variables"),
            {"key": "gold", "value": 99},
        )
        e2 = f.proposed(
            "core.remove_component", _entity_target("ent_ghost", "knowledge.belief"), {}
        )
        new_state, txn, events = commit_transaction(
            state, [e1, e2], TransactionId("txn_part"), _producer()
        )
        assert txn.status is TransactionStatus.ABORTED
        # seq0 的变更不得部分落盘
        assert new_state.world_variables["gold"] == 0, "seq0 有效效果不得部分提交"
        assert new_state.entities == state.entities
        assert new_state.world_revision == Revision(0)
        assert events == []

    def test_aborted_txn_carries_txn_level_fields(self, f: _EffectFactory) -> None:
        """ABORTED 事务仍承载事务级 provenance / logical_tick / cascade（可审计）。"""
        state = _base_state(0)
        producer = _producer()
        cascade = _cascade_ctx()
        effect = f.proposed("core.remove_entity", _entity_target("ent_ghost"), {})
        _, txn, _ = commit_transaction(
            state, [effect], TransactionId("txn_ab_fields"), producer,
            logical_tick=42, cascade=cascade,
        )
        assert txn.status is TransactionStatus.ABORTED
        assert txn.provenance is producer
        assert txn.logical_tick == 42
        assert txn.cascade == cascade
        assert txn.abort_reason is not None and txn.abort_reason


class TestAbortTransaction:
    """abort_transaction（§6.5）：ABORTED 数据形态构造器。"""

    def test_aborted_data_shape(self) -> None:
        state = _base_state(5)
        producer = _producer()
        aborted = abort_transaction(
            state, TransactionId("txn_ab1"), "conflict_dropped_by_test", producer
        )
        assert aborted.status is TransactionStatus.ABORTED
        assert aborted.transaction_id == TransactionId("txn_ab1")
        assert aborted.base_revision == Revision(5)
        assert aborted.commit_revision is None, "ABORTED 不得携带 commit_revision"
        assert aborted.effects == [], "ABORTED effects 必为空（部分提交不可表达）"
        assert aborted.event_ids == []
        assert aborted.abort_reason == "conflict_dropped_by_test"
        assert aborted.provenance is producer
        assert aborted.logical_tick is None
        assert aborted.cascade is None

    def test_rejected_effects_not_embedded(self, f: _EffectFactory) -> None:
        """rejected_effects 不进事务（数据层不可表达），由调用方写 trace（§6.5）。"""
        state = _base_state(0)
        rejected = [
            f.proposed(
                "core.set_world_variable",
                _domain_target("world_variables"),
                {"key": "gold", "value": 1},
            ),
            f.proposed(
                "core.set_world_variable",
                _domain_target("world_variables"),
                {"key": "gold", "value": 2},
            ),
        ]
        aborted = abort_transaction(
            state,
            TransactionId("txn_ab2"),
            "test_rejected",
            _producer(),
            rejected_effects=rejected,
            logical_tick=9,
            cascade=_cascade_ctx(),
        )
        assert aborted.effects == []
        assert aborted.event_ids == []
        assert aborted.logical_tick == 9
        assert aborted.cascade == _cascade_ctx()
        assert aborted.abort_reason == "test_rejected"

    def test_state_untouched(self) -> None:
        state = _base_state(3)
        base_dump = state.model_dump(mode="json")
        abort_transaction(state, TransactionId("txn_ab3"), "probe", _producer())
        assert state.model_dump(mode="json") == base_dump
        assert state.world_revision == Revision(3)


class TestZeroAliasing:
    """零别名与不可变保证（任务包目标 2）：三向零别名（P1 §3.5 三纪律）。"""

    def test_success_state_zero_alias_with_base(self, f: _EffectFactory) -> None:
        """成功路径：新状态 ↔ 原状态双向零别名（容器 + 嵌套 dict 双层）。"""
        state = _base_state(0)
        effects = _happy_effects(f)
        new_state, _, _ = commit_transaction(state, effects, TransactionId("txn_za1"), _producer())
        assert new_state is not state
        # world_variables：顶层与嵌套 dict 均非共享；修改新侧不波及原侧
        assert new_state.world_variables is not state.world_variables
        assert new_state.world_variables["calendar"] is not state.world_variables["calendar"]
        new_state.world_variables["calendar"]["day"] = 31
        assert state.world_variables["calendar"]["day"] == 3
        # 反向：修改原侧不波及新侧
        state.world_variables["gold"] = 12345
        assert new_state.world_variables["gold"] == 10
        # entities：记录与组件数据非共享
        alice_new = new_state.entities[EntityId("ent_alice")]
        alice_base = state.entities[EntityId("ent_alice")]
        assert alice_new is not alice_base
        pos_key = ComponentTypeId("space.position")
        assert alice_new.components[pos_key] is not alice_base.components[pos_key]
        alice_new.components[pos_key]["x"] = -1
        assert alice_base.components[pos_key]["x"] == 1, "修改新侧组件数据污染了原状态"
        # scenario_state：信封与 data 非共享
        assert new_state.scenario_state is not state.scenario_state
        assert new_state.scenario_state.data is not state.scenario_state.data
        new_state.scenario_state.data["goal"] = "篡改"
        assert state.scenario_state.data["goal"] == "find the key"

    def test_base_state_untouched_after_success(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        snapshot = state.model_dump(mode="json")
        commit_transaction(state, _happy_effects(f), TransactionId("txn_za2"), _producer())
        assert state.model_dump(mode="json") == snapshot, "提交后原状态不得被触碰"
        assert state.world_revision == Revision(0)

    def test_input_effects_untouched(self, f: _EffectFactory) -> None:
        """输入 ProposedEffect 批次不被装配过程污染（frozen 契约的输入侧）。"""
        state = _base_state(0)
        effects = _happy_effects(f)
        snapshots = [e.model_dump(mode="json") for e in effects]
        commit_transaction(state, effects, TransactionId("txn_za3"), _producer())
        assert [e.model_dump(mode="json") for e in effects] == snapshots

    def test_commits_from_same_base_independent(self, f: _EffectFactory) -> None:
        """同一 base 两次提交（等价基线）：产物语义一致且相互独立（分支独立）。"""
        effects_a = _happy_effects(_EffectFactory())
        effects_b = _happy_effects(_EffectFactory())
        state_a, _, _ = commit_transaction(
            _base_state(0), effects_a, TransactionId("txn_za4a"), _producer()
        )
        state_b, _, _ = commit_transaction(
            _base_state(0), effects_b, TransactionId("txn_za4b"), _producer()
        )
        assert state_a is not state_b
        assert state_a == state_b
        # 嵌套修改互不波及
        state_a.world_variables["calendar"]["hour"] = 23
        assert state_b.world_variables["calendar"]["hour"] == 12
        state_a.scenario_state.data["goal"] = "篡改"
        assert state_b.scenario_state.data["goal"] == "found the key"

    def test_failed_return_state_is_original_and_untouched(self, f: _EffectFactory) -> None:
        """失败路径：返回**原状态对象**（原样），且原状态未被触碰。"""
        state = _base_state(0)
        snapshot = state.model_dump(mode="json")
        effect = f.proposed("core.remove_entity", _entity_target("ent_ghost"), {})
        new_state, _, _ = commit_transaction(state, [effect], TransactionId("txn_za5"), _producer())
        assert new_state is state, "失败路径必须原样返回同一状态对象"
        assert state.model_dump(mode="json") == snapshot


class TestExportSurface:
    """D-P2-19 / §10.3：re-export 面（单一来源、同一对象）。"""

    def test_package_reexports_same_object_as_module(self) -> None:
        assert pkg_commit_transaction is commit_transaction
        assert pkg_abort_transaction is abort_transaction

    def test_module_all_is_two_public_functions(self) -> None:
        import src.engine_v2.core.transaction_executor as mod

        assert set(mod.__all__) == {"commit_transaction", "abort_transaction"}

    def test_package_all_contains_both(self) -> None:
        import src.engine_v2.core as core_pkg

        assert "commit_transaction" in core_pkg.__all__
        assert "abort_transaction" in core_pkg.__all__
