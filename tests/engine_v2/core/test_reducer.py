"""P2-T01 Reducer-only 纯状态突变引擎与写屏障验收（P2 设计规范 §2 全量）。

覆盖（任务包 P2-T01 测试要求逐项落位）：

- **7 种 core 结构效果的正确突变**（§2.1 词表 / D-P2-04）：
  create/remove entity、set/remove component（整体替换）、
  set/remove world variable（整值替换）、set scenario data（整体替换）；
- **异常回退**：无效 payload（extra 键 / 缺键 / 组件类型词法 / schema 不符）、
  实体不存在、组件未挂载（显式拒绝空操作）、重复创建、domain 不匹配、
  目标种类错误、防御性复检（transaction_id / commit_revision / sequence /
  base+1）失败、未注册 effect_type（不推断，D-P2-05）、ABORTED 事务、
  handler 返回非 WorldState——**任何异常下输入 WorldState 原样不变**（原子性）；
- **apply_committed_effects 纯函数与零别名**：空列表原样返回（同一对象）、
  输入/输出零别名（容器与嵌套 dict 双层）、确定性、revision 恰 +1（D-P2-06）、
  事务内顺序依赖合法（暂存可见性，§2.4 步骤 3）、语义 handler 见到暂存物化；
- **state_* 纯函数族**（§2.2）：七函数各自 purity + 零别名 + 前置条件抛错；
- **EffectHandlerRegistry**（§2.3）：7 个结构 handler 预注册（注册序确定性）、
  同一 handler 幂等、不同 handler 冲突（结构 handler 不可覆盖）、
  未注册 resolve=None、default_handler_registry 每次新建；
- **写屏障 C3 正/反例**（§2.6，P1 §10.1 条件 C3 闭合）：
  武装态四条逃逸路径（model_copy / model_construct / copy.copy /
  copy.deepcopy）全部拦截；``write_barrier_exempt()`` 窗口内四者放行且窗口
  最小；``WriteBarrier`` 上下文与嵌套深度；reducer 自身（含语义 handler）在
  武装态不受阻；``uninstall_write_barrier()`` 后 P1 语义复原；install 幂等；
  P1-T07 原始逃逸场景（ABORTED 事务 copy-update 出 commit_revision）被拦截；
- **guard() 只读门面**（§2.6.3）：4 个只读门面 + model_dump 出口可用、
  公共字段只读；model_copy / model_construct / copy / deepcopy / 属性赋值 /
  属性删除 / 私有缝隙访问一律 WriteBarrierError（无条件，与令牌无关）；
  门面非契约模型、不参与 round-trip。

全部用例无网络、无 LLM、无 API key。写屏障为 **opt-in**：本文件 autouse
夹具保证每用例前后全局状态复原，不跨文件受染（§2.6.2 纪律）。
"""

from __future__ import annotations

import copy
import json
from collections.abc import Sequence

import pytest
from pydantic import BaseModel, ValidationError

from src.engine_v2.core.components import (
    ComponentRegistry,
    ComponentSchema,
    ComponentTypeId,
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
from src.engine_v2.core.ids import EffectId, EntityId, ProducerId, TransactionId
from src.engine_v2.core.reducer import (
    EFFECT_CREATE_ENTITY,
    EFFECT_REMOVE_COMPONENT,
    EFFECT_REMOVE_ENTITY,
    EFFECT_REMOVE_WORLD_VARIABLE,
    EFFECT_SET_COMPONENT,
    EFFECT_SET_SCENARIO_DATA,
    EFFECT_SET_WORLD_VARIABLE,
    STRUCTURAL_EFFECT_TYPES,
    CreateEntityPayload,
    EmptyPayload,
    EffectApplicationError,
    EffectHandler,
    EffectHandlerRegistry,
    GuardedWorldState,
    HandlerConflictError,
    ReducerError,
    RemoveWorldVariablePayload,
    SetScenarioDataPayload,
    SetWorldVariablePayload,
    WriteBarrier,
    WriteBarrierError,
    apply_committed_effects,
    apply_transaction,
    default_handler_registry,
    guard,
    install_write_barrier,
    is_guarded,
    state_create_entity,
    state_remove_component,
    state_remove_entity,
    state_remove_world_variable,
    state_set_component,
    state_set_scenario_state,
    state_set_world_variable,
    uninstall_write_barrier,
    write_barrier_exempt,
    write_barrier_installed,
)
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.state import ScenarioState, WorldState
from src.engine_v2.core.transaction import Transaction, TransactionStatus


# —— 确定性构造助手 ——


def _base_state(world_revision: int = 0) -> WorldState:
    """确定性基线世界：1 实体（含 1 组件）+ 嵌套世界变量 + scenario 信封。"""
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
        },
        world_variables={
            "calendar": {"day": 3, "hour": 12},
            "deep": {"l1": {"l2": 1}},
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


class _EffectFactory:
    """确定性效果构造：eff_ id 按工厂序号唯一；固定 producer / txn。"""

    def __init__(self) -> None:
        self._n = 0

    def proposed(
        self,
        effect_type: str,
        target: EntityTarget | StateDomainTarget,
        payload: dict,
        *,
        base_revision: int = 0,
        source: str = "rule.test",
    ) -> ProposedEffect:
        self._n += 1
        return ProposedEffect(
            effect_id=EffectId(f"eff_test_{self._n:03d}"),
            effect_type=EffectTypeId(effect_type),
            source=ProducerId(source),
            target=target,
            payload=payload,
            base_revision=Revision(base_revision),
        )

    def committed(
        self,
        effect: ProposedEffect,
        *,
        txn_id: str = "txn_test_0001",
        commit_revision: int = 1,
        sequence: int = 0,
    ) -> CommittedEffect:
        return CommittedEffect(
            effect=effect,
            transaction_id=TransactionId(txn_id),
            commit_revision=Revision(commit_revision),
            sequence=sequence,
        )


def _committed_transaction(
    state: WorldState, effects: Sequence[ProposedEffect], *, txn_id: str = "txn_test_0001"
) -> Transaction:
    """按 P1 §5.6 不变量装配合法 COMMITTED 事务（commit = base + 1，seq 0..n-1）。"""
    base = state.world_revision
    commit = base.next()
    committed = [
        CommittedEffect(
            effect=effect,
            transaction_id=TransactionId(txn_id),
            commit_revision=commit,
            sequence=i,
        )
        for i, effect in enumerate(effects)
    ]
    return Transaction(
        transaction_id=TransactionId(txn_id),
        status=TransactionStatus.COMMITTED,
        base_revision=base,
        commit_revision=commit,
        effects=committed,
    )


@pytest.fixture()
def f() -> _EffectFactory:
    return _EffectFactory()


@pytest.fixture(autouse=True)
def _ensure_barrier_unarmed() -> None:
    """写屏障 opt-in 纪律（§2.6.2）：每用例前后全局复原，不跨文件受染。

    前置 uninstall 是防御性兜底：前序用例若在 install 后异常退出，残留武装
    不得污染后续用例（包括本文件之外的 P1 既有测试）。
    """
    uninstall_write_barrier()
    yield
    uninstall_write_barrier()


class _AtomicFailure:
    """异常回退断言复用：EffectApplicationError 定位属性 + 输入状态原样。"""

    @staticmethod
    def assert_raises(
        state: WorldState,
        committed: Sequence[CommittedEffect],
        *,
        seq: int,
        effect_id: str,
        match: str = "",
        **apply_kwargs: object,
    ) -> EffectApplicationError:
        snapshot = state.model_dump(mode="json")
        with pytest.raises(EffectApplicationError) as exc_info:
            apply_committed_effects(state, committed, **apply_kwargs)  # type: ignore[arg-type]
        err = exc_info.value
        assert err.sequence == seq, f"sequence 应为 {seq}，实际 {err.sequence}"
        assert err.effect_id == effect_id, (
            f"effect_id 应为 {effect_id!r}，实际 {err.effect_id!r}"
        )
        if match:
            assert match in str(err), f"异常信息应含 {match!r}：{err}"
        assert state.model_dump(mode="json") == snapshot, "异常后输入状态被污染（原子性破坏）"
        return err


class TestStructuralVocabulary:
    """7 种 core 结构效果的正确突变（§2.1 / D-P2-04）。"""

    def test_structural_effect_types_vocabulary(self) -> None:
        assert STRUCTURAL_EFFECT_TYPES == frozenset(
            {
                "core.create_entity",
                "core.remove_entity",
                "core.set_component",
                "core.remove_component",
                "core.set_world_variable",
                "core.remove_world_variable",
                "core.set_scenario_data",
            }
        )
        assert len(STRUCTURAL_EFFECT_TYPES) == 7
        assert all(isinstance(t, EffectTypeId) for t in STRUCTURAL_EFFECT_TYPES)

    def test_structural_set_matches_builtin_handlers(self) -> None:
        reg = EffectHandlerRegistry()
        assert set(STRUCTURAL_EFFECT_TYPES) == set(reg.effect_types())

    def test_create_entity_applies(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        eff = f.proposed(
            "core.create_entity",
            _entity_target("ent_new"),
            {
                "entity_class": "npc",
                "tags": ["shopkeeper"],
                "components": {"space.position": {"x": 7, "y": 8}},
            },
        )
        result = apply_committed_effects(state, [f.committed(eff)])
        rec = result.entities[EntityId("ent_new")]
        assert rec.entity_class == "npc"
        assert rec.tags == ["shopkeeper"]
        assert rec.components == {ComponentTypeId("space.position"): {"x": 7, "y": 8}}
        # created_revision 由 reducer 强制置为 commit_revision（payload 不得携带）
        assert rec.created_revision == Revision(1)
        assert result.world_revision == Revision(1)
        # 输入状态原样
        assert set(state.entities) == {EntityId("ent_alice")}
        assert state.world_revision == Revision(0)

    def test_create_entity_minimal_payload(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        eff = f.proposed("core.create_entity", _entity_target("ent_min"), {})
        result = apply_committed_effects(state, [f.committed(eff)])
        rec = result.entities[EntityId("ent_min")]
        assert rec.entity_class is None
        assert rec.tags == []
        assert rec.components == {}
        assert rec.created_revision == Revision(1)

    def test_remove_entity_applies(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        eff = f.proposed("core.remove_entity", _entity_target("ent_alice"), {})
        result = apply_committed_effects(state, [f.committed(eff)])
        assert not result.has_entity(EntityId("ent_alice"))
        assert result.entities == {}
        assert state.has_entity(EntityId("ent_alice"))

    def test_set_component_replaces_whole(self, f: _EffectFactory) -> None:
        """整体替换，无部分合并（KBC-4 防线，§2.1）。"""
        state = _base_state(0)
        eff = f.proposed(
            "core.set_component",
            _entity_target("ent_alice", "space.position"),
            {"z": 3},
        )
        result = apply_committed_effects(state, [f.committed(eff)])
        # 旧键 x/y 不残留——不是合并
        assert result.entities[EntityId("ent_alice")].components == {
            ComponentTypeId("space.position"): {"z": 3}
        }
        assert state.entities[EntityId("ent_alice")].components == {
            ComponentTypeId("space.position"): {"x": 1, "y": 2}
        }

    def test_remove_component_applies(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        eff = f.proposed(
            "core.remove_component", _entity_target("ent_alice", "space.position"), {}
        )
        result = apply_committed_effects(state, [f.committed(eff)])
        assert result.entities[EntityId("ent_alice")].components == {}
        # entity 本体保留（只摘组件）
        assert result.has_entity(EntityId("ent_alice"))

    def test_set_world_variable_adds_and_replaces(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        add = f.proposed(
            "core.set_world_variable", _domain_target("world_variables"),
            {"key": "note", "value": "中文世界变量"},
        )
        replace = f.proposed(
            "core.set_world_variable", _domain_target("world_variables"),
            {"key": "calendar", "value": {"day": 4, "hour": 13}},
        )
        result = apply_committed_effects(
            state, [f.committed(add, sequence=0), f.committed(replace, sequence=1)]
        )
        assert result.world_variables["note"] == "中文世界变量"
        # 整值替换：旧结构（hour 键等）被完整新值取代
        assert result.world_variables["calendar"] == {"day": 4, "hour": 13}
        assert state.world_variables == {"calendar": {"day": 3, "hour": 12}, "deep": {"l1": {"l2": 1}}}

    def test_remove_world_variable_applies(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        eff = f.proposed(
            "core.remove_world_variable", _domain_target("world_variables"), {"key": "deep"}
        )
        result = apply_committed_effects(state, [f.committed(eff)])
        assert "deep" not in result.world_variables
        assert "calendar" in result.world_variables

    def test_set_scenario_data_replaces_whole(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        eff = f.proposed(
            "core.set_scenario_data",
            _domain_target("scenario"),
            {"scenario_id": "scn_new", "stage": "act2", "data": {"flag": True}},
        )
        result = apply_committed_effects(state, [f.committed(eff)])
        assert result.scenario_state == ScenarioState(
            scenario_id="scn_new", stage="act2", data={"flag": True}
        )
        # 整体替换：旧 data 键（goal）不残留
        assert "goal" not in result.scenario_state.data
        assert state.scenario_state.scenario_id == "scn_main"

    def test_set_scenario_data_minimal_payload(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        eff = f.proposed("core.set_scenario_data", _domain_target("scenario"), {"data": {}})
        result = apply_committed_effects(state, [f.committed(eff)])
        assert result.scenario_state == ScenarioState()


# —— 异常回退（无效 payload / 实体不存在 / 组件冲突等；原子性）——


class TestExceptionRollback:
    """前置条件/无效 payload 违反 → 异常回退，输入状态原样（§2.4 步骤 5）。"""

    def test_duplicate_create_raises(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        eff = f.proposed("core.create_entity", _entity_target("ent_alice"), {})
        _AtomicFailure.assert_raises(
            state, [f.committed(eff)], seq=0, effect_id=str(eff.effect_id), match="已存在"
        )

    def test_remove_missing_entity_raises(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        eff = f.proposed("core.remove_entity", _entity_target("ent_ghost"), {})
        _AtomicFailure.assert_raises(
            state, [f.committed(eff)], seq=0, effect_id=str(eff.effect_id), match="不存在"
        )

    def test_set_component_missing_entity_raises(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        eff = f.proposed(
            "core.set_component", _entity_target("ent_ghost", "space.position"), {"x": 1}
        )
        _AtomicFailure.assert_raises(
            state, [f.committed(eff)], seq=0, effect_id=str(eff.effect_id), match="不存在"
        )

    def test_remove_component_not_mounted_raises(self, f: _EffectFactory) -> None:
        """实体存在但组件未挂载 → 显式拒绝空操作歧义（§2.1）。"""
        state = _base_state(0)
        eff = f.proposed(
            "core.remove_component", _entity_target("ent_alice", "attrs.hp"), {}
        )
        _AtomicFailure.assert_raises(
            state, [f.committed(eff)], seq=0, effect_id=str(eff.effect_id), match="未挂载"
        )

    def test_remove_world_variable_missing_key_raises(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        eff = f.proposed(
            "core.remove_world_variable", _domain_target("world_variables"), {"key": "nope"}
        )
        _AtomicFailure.assert_raises(
            state, [f.committed(eff)], seq=0, effect_id=str(eff.effect_id), match="键不存在"
        )

    def test_invalid_payload_extra_key_raises(self, f: _EffectFactory) -> None:
        """payload 携带 created_revision（extra="forbid" 拒绝，§2.1）。"""
        state = _base_state(0)
        eff = f.proposed(
            "core.create_entity", _entity_target("ent_new"), {"created_revision": 5}
        )
        _AtomicFailure.assert_raises(
            state, [f.committed(eff)], seq=0, effect_id=str(eff.effect_id), match="无效 payload"
        )

    def test_invalid_payload_missing_required_key_raises(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        eff = f.proposed(
            "core.remove_world_variable", _domain_target("world_variables"), {"value": 1}
        )
        _AtomicFailure.assert_raises(
            state, [f.committed(eff)], seq=0, effect_id=str(eff.effect_id), match="无效 payload"
        )

    def test_invalid_payload_wrong_key_type_raises(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        eff = f.proposed(
            "core.set_world_variable", _domain_target("world_variables"), {"key": 123, "value": 1}
        )
        _AtomicFailure.assert_raises(
            state, [f.committed(eff)], seq=0, effect_id=str(eff.effect_id), match="无效 payload"
        )

    def test_invalid_payload_component_not_dict_raises(self, f: _EffectFactory) -> None:
        """create 的 components 值必须是组件数据对象（dict）。"""
        state = _base_state(0)
        eff = f.proposed(
            "core.create_entity", _entity_target("ent_new"), {"components": {"bad": 5}}
        )
        _AtomicFailure.assert_raises(
            state, [f.committed(eff)], seq=0, effect_id=str(eff.effect_id), match="无效 payload"
        )

    def test_create_component_type_bad_lexicon_raises(self, f: _EffectFactory) -> None:
        """payload 组件类型标识词法非法（parse_component_type_id 拒绝）。"""
        state = _base_state(0)
        eff = f.proposed(
            "core.create_entity",
            _entity_target("ent_new"),
            {"components": {"Space.Position": {"x": 1}}},
        )
        _AtomicFailure.assert_raises(
            state, [f.committed(eff)], seq=0, effect_id=str(eff.effect_id),
            match="词法非法",
        )

    def test_wrong_target_kind_raises(self, f: _EffectFactory) -> None:
        """结构动词要求的目标种类不符（create 要求 EntityTarget）。"""
        state = _base_state(0)
        eff = f.proposed(
            "core.create_entity", _domain_target("world_variables"), {}
        )
        _AtomicFailure.assert_raises(
            state, [f.committed(eff)], seq=0, effect_id=str(eff.effect_id),
            match="EntityTarget",
        )

    def test_set_component_without_component_type_raises(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        eff = f.proposed("core.set_component", _entity_target("ent_alice"), {"x": 1})
        _AtomicFailure.assert_raises(
            state, [f.committed(eff)], seq=0, effect_id=str(eff.effect_id),
            match="component_type",
        )

    def test_domain_mismatch_raises(self, f: _EffectFactory) -> None:
        """core.set_world_variable 要求 domain == world_variables。"""
        state = _base_state(0)
        eff = f.proposed(
            "core.set_world_variable", _domain_target("scenario"), {"key": "k", "value": 1}
        )
        _AtomicFailure.assert_raises(
            state, [f.committed(eff)], seq=0, effect_id=str(eff.effect_id),
            match="world_variables",
        )

    def test_partial_failure_input_state_untouched(self, f: _EffectFactory) -> None:
        """事务内第二条失败 → 整批不落盘：第一条的变更在输入状态不可观测。"""
        state = _base_state(0)
        ok = f.proposed(
            "core.set_world_variable", _domain_target("world_variables"),
            {"key": "landing_key", "value": 1},
        )
        bad = f.proposed(
            "core.remove_world_variable", _domain_target("world_variables"), {"key": "nope"}
        )
        err = _AtomicFailure.assert_raises(
            state,
            [f.committed(ok, sequence=0), f.committed(bad, sequence=1)],
            seq=1,
            effect_id=str(bad.effect_id),
        )
        assert "landing_key" not in state.world_variables, "部分提交可观测（原子性破坏）"
        assert isinstance(err, ReducerError)

    def test_unregistered_semantic_type_raises_plain_reducer_error(
        self, f: _EffectFactory
    ) -> None:
        """未注册 effect_type → ReducerError 本体（不推断，D-P2-05）；
        批级 fatal，**不是** EffectApplicationError 包装（§2.4 步骤 3 口径）。"""
        state = _base_state(0)
        eff = f.proposed(
            "game.hp_change", _entity_target("ent_alice", "attrs.hp"), {"value": 3}
        )
        with pytest.raises(ReducerError) as exc_info:
            apply_committed_effects(state, [f.committed(eff)])
        assert "未注册 effect_type" in str(exc_info.value)
        assert "game.hp_change" in str(exc_info.value)
        assert not isinstance(exc_info.value, EffectApplicationError)
        assert state.world_revision == Revision(0)

    def test_commit_revision_mismatch_raises_reducer_error(self, f: _EffectFactory) -> None:
        """防御性复检：commit_revision 必须 == base + 1（§2.4 步骤 2）。"""
        state = _base_state(0)
        eff = f.proposed(
            "core.set_world_variable", _domain_target("world_variables"),
            {"key": "k", "value": 1},
        )
        with pytest.raises(ReducerError, match="commit_revision 必须等于"):
            apply_committed_effects(state, [f.committed(eff, commit_revision=2)])

    def test_mixed_transaction_ids_raise_reducer_error(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        e1 = f.proposed(
            "core.set_world_variable", _domain_target("world_variables"),
            {"key": "a", "value": 1},
        )
        e2 = f.proposed(
            "core.set_world_variable", _domain_target("world_variables"),
            {"key": "b", "value": 2},
        )
        with pytest.raises(ReducerError, match="transaction_id"):
            apply_committed_effects(
                state,
                [
                    f.committed(e1, txn_id="txn_aaa_0000", sequence=0),
                    f.committed(e2, txn_id="txn_bbb_0000", sequence=1),
                ],
            )

    def test_mixed_commit_revisions_raise_reducer_error(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        e1 = f.proposed(
            "core.set_world_variable", _domain_target("world_variables"),
            {"key": "a", "value": 1},
        )
        e2 = f.proposed(
            "core.set_world_variable", _domain_target("world_variables"),
            {"key": "b", "value": 2},
        )
        with pytest.raises(ReducerError, match="commit_revision"):
            apply_committed_effects(
                state,
                [
                    f.committed(e1, commit_revision=1, sequence=0),
                    f.committed(e2, commit_revision=2, sequence=1),
                ],
            )

    def test_sequence_gap_raises_reducer_error(self, f: _EffectFactory) -> None:
        """sequence 必须恰为 0..n-1（§2.4 步骤 2 复检）。"""
        state = _base_state(0)
        e1 = f.proposed(
            "core.set_world_variable", _domain_target("world_variables"),
            {"key": "a", "value": 1},
        )
        e2 = f.proposed(
            "core.set_world_variable", _domain_target("world_variables"),
            {"key": "b", "value": 2},
        )
        with pytest.raises(ReducerError, match="sequence"):
            apply_committed_effects(
                state,
                [
                    f.committed(e1, commit_revision=1, sequence=0),
                    f.committed(e2, commit_revision=1, sequence=2),
                ],
            )

    def test_apply_transaction_aborted_raises(self) -> None:
        txn = Transaction(
            transaction_id=TransactionId("txn_ab1"),
            status=TransactionStatus.ABORTED,
            base_revision=Revision(0),
            abort_reason="reducer 测试用 ABORTED 事务",
        )
        state = _base_state(0)
        with pytest.raises(ReducerError, match="COMMITTED"):
            apply_transaction(state, txn)
        assert state.world_revision == Revision(0)

    def test_handler_returning_non_worldstate_raises(self, f: _EffectFactory) -> None:
        handlers = default_handler_registry()
        handlers.register(EffectTypeId("test.bad_return"), lambda state, effect: 42)
        eff = f.proposed("test.bad_return", _domain_target("world_variables"), {})
        state = _base_state(0)
        _AtomicFailure.assert_raises(
            state,
            [f.committed(eff)],
            seq=0,
            effect_id=str(eff.effect_id),
            match="WorldState",
            handlers=handlers,
        )

    def test_handler_returning_non_worldstate_via_apply(
        self, f: _EffectFactory
    ) -> None:
        """同上，但显式经 apply_committed_effects 的 handlers 参数传入（定位属性复检）。"""
        handlers = default_handler_registry()
        handlers.register(EffectTypeId("test.bad_return2"), lambda state, effect: "nope")
        eff = f.proposed("test.bad_return2", _domain_target("world_variables"), {})
        state = _base_state(0)
        with pytest.raises(EffectApplicationError) as exc_info:
            apply_committed_effects(state, [f.committed(eff)], handlers=handlers)
        assert exc_info.value.sequence == 0
        assert exc_info.value.effect_id == str(eff.effect_id)
        assert state.model_dump(mode="json") == _base_state(0).model_dump(mode="json")

    def test_component_registry_schema_mismatch_raises(self, f: _EffectFactory) -> None:
        """组件冲突（语义层）：已注册 schema 与 payload 不符 → 回退（D-8 校验点 b）。"""

        class _HpPayload(BaseModel):
            value: int

        registry = ComponentRegistry()
        registry.register(
            ComponentSchema(component_type=ComponentTypeId("attrs.hp"), payload_model=_HpPayload)
        )
        state = _base_state(0)
        eff = f.proposed(
            "core.set_component", _entity_target("ent_alice", "attrs.hp"),
            {"value": "not-an-int"},
        )
        _AtomicFailure.assert_raises(
            state,
            [f.committed(eff)],
            seq=0,
            effect_id=str(eff.effect_id),
            match="schema",
            component_registry=registry,
        )

    def test_component_registry_valid_payload_applies(self, f: _EffectFactory) -> None:
        class _HpPayload(BaseModel):
            value: int

        registry = ComponentRegistry()
        registry.register(
            ComponentSchema(component_type=ComponentTypeId("attrs.hp"), payload_model=_HpPayload)
        )
        state = _base_state(0)
        eff = f.proposed(
            "core.set_component", _entity_target("ent_alice", "attrs.hp"), {"value": 3}
        )
        result = apply_committed_effects(state, [f.committed(eff)], component_registry=registry)
        assert result.entities[EntityId("ent_alice")].components[
            ComponentTypeId("attrs.hp")
        ] == {"value": 3}

    def test_component_registry_validates_create_components(
        self, f: _EffectFactory
    ) -> None:
        """core.create_entity 的 components 逐项经 registry 校验（§2.4）。"""

        class _HpPayload(BaseModel):
            value: int

        registry = ComponentRegistry()
        registry.register(
            ComponentSchema(component_type=ComponentTypeId("attrs.hp"), payload_model=_HpPayload)
        )
        state = _base_state(0)
        eff = f.proposed(
            "core.create_entity", _entity_target("ent_new"),
            {"components": {"attrs.hp": {"value": 9}}},
        )
        result = apply_committed_effects(state, [f.committed(eff)], component_registry=registry)
        assert result.entities[EntityId("ent_new")].components[
            ComponentTypeId("attrs.hp")
        ] == {"value": 9}
        bad = f.proposed(
            "core.create_entity", _entity_target("ent_new2"),
            {"components": {"attrs.hp": {"value": "bad"}}},
        )
        _AtomicFailure.assert_raises(
            state,
            [f.committed(bad)],
            seq=0,
            effect_id=str(bad.effect_id),
            match="schema",
            component_registry=registry,
        )


# —— 事务内顺序依赖与暂存可见性（§2.4 步骤 3）——


class TestOrderingAndStaging:
    """_WorkingWorld 暂存：同事务内顺序依赖合法；语义 handler 见到暂存物化。"""

    def test_in_transaction_create_then_set_component(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        create = f.proposed(
            "core.create_entity", _entity_target("ent_seq"),
            {"entity_class": "item", "components": {}},
        )
        set_comp = f.proposed(
            "core.set_component", _entity_target("ent_seq", "attrs.rarity"), {"tier": 2}
        )
        result = apply_committed_effects(
            state,
            [f.committed(create, sequence=0), f.committed(set_comp, sequence=1)],
        )
        rec = result.entities[EntityId("ent_seq")]
        assert rec.components == {ComponentTypeId("attrs.rarity"): {"tier": 2}}
        assert rec.created_revision == Revision(1)

    def test_in_transaction_remove_then_set_component_fails(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        remove = f.proposed("core.remove_entity", _entity_target("ent_alice"), {})
        set_comp = f.proposed(
            "core.set_component", _entity_target("ent_alice", "space.position"), {"x": 9}
        )
        _AtomicFailure.assert_raises(
            state,
            [f.committed(remove, sequence=0), f.committed(set_comp, sequence=1)],
            seq=1,
            effect_id=str(set_comp.effect_id),
            match="不存在",
        )

    def test_semantic_handler_sees_staged_state(self, f: _EffectFactory) -> None:
        """语义 handler 收到暂存物化的 WorldState（含前序结构效果）+ base revision。"""
        seen: list[WorldState] = []

        def observe(state: WorldState, effect: ProposedEffect) -> WorldState:
            seen.append(state)
            return state

        handlers = default_handler_registry()
        handlers.register(EffectTypeId("test.observe"), observe)
        state = _base_state(0)
        create = f.proposed("core.create_entity", _entity_target("ent_staged"), {})
        observe_eff = f.proposed("test.observe", _domain_target("world_variables"), {})
        result = apply_committed_effects(
            state,
            [f.committed(create, sequence=0), f.committed(observe_eff, sequence=1)],
            handlers=handlers,
        )
        assert len(seen) == 1
        assert seen[0].has_entity(EntityId("ent_staged")), "handler 未见到暂存中的新实体"
        assert seen[0].world_revision == Revision(0), "物化应保持 base revision"
        assert result.has_entity(EntityId("ent_staged"))


# —— 纯函数与零别名（§2.4 步骤 1/4/5）——


class TestPureFunctionAndZeroAliasing:
    """apply_committed_effects / apply_transaction 纯函数特性。"""

    def test_empty_list_returns_input_identity(self) -> None:
        state = _base_state(0)
        assert apply_committed_effects(state, []) is state

    def test_input_state_unchanged_after_success(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        snapshot = state.model_dump(mode="json")
        eff = f.proposed("core.create_entity", _entity_target("ent_new"), {})
        apply_committed_effects(state, [f.committed(eff)])
        assert state.model_dump(mode="json") == snapshot

    def test_output_zero_aliasing_with_input(self, f: _EffectFactory) -> None:
        state = _base_state(0)
        eff = f.proposed(
            "core.set_world_variable", _domain_target("world_variables"),
            {"key": "note", "value": {"a": {"b": 1}}},
        )
        result = apply_committed_effects(state, [f.committed(eff)])
        assert result is not state
        # 容器层零别名
        assert result.world_variables is not state.world_variables
        assert result.entities is not state.entities
        assert result.scenario_state is not state.scenario_state
        # 嵌套 dict 层零别名（重建切断共享）
        assert result.world_variables["deep"] is not state.world_variables["deep"]
        assert result.world_variables["deep"]["l1"] is not state.world_variables["deep"]["l1"]
        # entity 记录层零别名
        alice_in = state.entities[EntityId("ent_alice")]
        alice_out = result.entities[EntityId("ent_alice")]
        assert alice_out is not alice_in
        assert alice_out.components is not alice_in.components
        assert alice_out.components[ComponentTypeId("space.position")] is not alice_in.components[
            ComponentTypeId("space.position")
        ]
        # 修改输出不波及输入（三层嵌套逐一）
        result.world_variables["deep"]["l1"]["l2"] = 999
        assert state.world_variables["deep"]["l1"]["l2"] == 1
        result.world_variables["note"]["a"]["b"] = 77
        result.entities[EntityId("ent_alice")].components[ComponentTypeId("space.position")]["x"] = 55
        assert state.entities[EntityId("ent_alice")].components[ComponentTypeId("space.position")]["x"] == 1
        assert result.scenario_state.data is not state.scenario_state.data
        result.scenario_state.data["goal"] = "篡改"
        assert state.scenario_state.data["goal"] == "find the key"

    def test_deterministic_same_input_same_output(self, f: _EffectFactory) -> None:
        state_a = _base_state(3)
        state_b = _base_state(3)
        eff = f.proposed(
            "core.set_world_variable", _domain_target("world_variables"),
            {"key": "k", "value": 1},
            base_revision=3,  # G2 补充轮 3：必须匹配状态 revision（reducer 逐 effect 复检）
        )
        ce = f.committed(eff, commit_revision=4)
        assert apply_committed_effects(state_a, [ce]) == apply_committed_effects(state_b, [ce])

    def test_revision_bumped_by_exactly_one(self, f: _EffectFactory) -> None:
        state = _base_state(7)
        eff = f.proposed(
            "core.remove_world_variable", _domain_target("world_variables"), {"key": "deep"},
            base_revision=7,  # G2 补充轮 3：必须匹配状态 revision（reducer 逐 effect 复检）
        )
        result = apply_committed_effects(state, [f.committed(eff, commit_revision=8)])
        assert result.world_revision == Revision(8)
        assert state.world_revision == Revision(7)

    def test_apply_transaction_happy_path(self, f: _EffectFactory) -> None:
        state = _base_state(2)
        eff = f.proposed(
            "core.remove_world_variable", _domain_target("world_variables"), {"key": "deep"},
            base_revision=2,  # G2 补充轮 3：必须匹配状态 revision（reducer 逐 effect 复检）
        )
        txn = _committed_transaction(state, [eff])
        result = apply_transaction(state, txn)
        assert "deep" not in result.world_variables
        assert result.world_revision == Revision(3)
        assert state.world_variables["deep"] == {"l1": {"l2": 1}}


# —— state_* 纯函数族（§2.2）——


class TestStateFunctions:
    """七纯函数：purity + 零别名 + 结构前置条件抛 ReducerError。"""

    def test_state_create_entity_pure_and_zero_aliasing(self) -> None:
        state = _base_state(0)
        snapshot = state.model_dump(mode="json")
        comp_data = {"a": 1}
        tags = ["t1"]
        result = state_create_entity(
            state,
            EntityId("ent_x"),
            entity_class="npc",
            tags=tags,
            components={ComponentTypeId("c.d"): comp_data},
            created_revision=Revision(1),
        )
        # self 不变（值 + 内部容器）
        assert state.model_dump(mode="json") == snapshot
        assert not state.has_entity(EntityId("ent_x"))
        # 结果正确
        assert result.has_entity(EntityId("ent_x"))
        rec = result.entities[EntityId("ent_x")]
        assert rec.created_revision == Revision(1)
        # 零别名：修改传入的可变容器不波及结果
        comp_data["a"] = 999
        tags.append("t2")
        assert rec.components[ComponentTypeId("c.d")] == {"a": 1}
        assert rec.tags == ["t1"]
        # state_* 不推进 revision
        assert result.world_revision == Revision(0)

    def test_state_create_entity_duplicate_raises(self) -> None:
        state = _base_state(0)
        with pytest.raises(ReducerError, match="已存在"):
            state_create_entity(state, EntityId("ent_alice"), created_revision=Revision(1))

    def test_state_remove_entity_pure(self) -> None:
        state = _base_state(0)
        snapshot = state.model_dump(mode="json")
        result = state_remove_entity(state, EntityId("ent_alice"))
        assert state.model_dump(mode="json") == snapshot
        assert state.has_entity(EntityId("ent_alice"))
        assert not result.has_entity(EntityId("ent_alice"))

    def test_state_remove_entity_missing_raises(self) -> None:
        state = _base_state(0)
        with pytest.raises(ReducerError, match="不存在"):
            state_remove_entity(state, EntityId("ent_ghost"))

    def test_state_set_component_pure_and_zero_aliasing(self) -> None:
        state = _base_state(0)
        snapshot = state.model_dump(mode="json")
        data = {"x": 10}
        result = state_set_component(
            state, EntityId("ent_alice"), ComponentTypeId("space.position"), data
        )
        assert state.model_dump(mode="json") == snapshot
        assert result.entities[EntityId("ent_alice")].components[
            ComponentTypeId("space.position")
        ] == {"x": 10}
        data["x"] = 777
        assert result.entities[EntityId("ent_alice")].components[
            ComponentTypeId("space.position")
        ] == {"x": 10}

    def test_state_set_component_missing_entity_raises(self) -> None:
        state = _base_state(0)
        with pytest.raises(ReducerError, match="不存在"):
            state_set_component(state, EntityId("ent_ghost"), ComponentTypeId("c.d"), {})

    def test_state_remove_component_pure(self) -> None:
        state = _base_state(0)
        snapshot = state.model_dump(mode="json")
        result = state_remove_component(state, EntityId("ent_alice"), ComponentTypeId("space.position"))
        assert state.model_dump(mode="json") == snapshot
        assert result.entities[EntityId("ent_alice")].components == {}

    def test_state_remove_component_not_mounted_raises(self) -> None:
        state = _base_state(0)
        with pytest.raises(ReducerError, match="未挂载"):
            state_remove_component(state, EntityId("ent_alice"), ComponentTypeId("attrs.hp"))

    def test_state_remove_component_missing_entity_raises(self) -> None:
        state = _base_state(0)
        with pytest.raises(ReducerError, match="不存在"):
            state_remove_component(state, EntityId("ent_ghost"), ComponentTypeId("c.d"))

    def test_state_set_world_variable_pure_and_zero_aliasing(self) -> None:
        state = _base_state(0)
        snapshot = state.model_dump(mode="json")
        value = {"day": 9}
        result = state_set_world_variable(state, "calendar", value)
        assert state.model_dump(mode="json") == snapshot
        assert result.world_variables["calendar"] == {"day": 9}
        value["day"] = 99
        assert result.world_variables["calendar"] == {"day": 9}

    def test_state_remove_world_variable_pure(self) -> None:
        state = _base_state(0)
        snapshot = state.model_dump(mode="json")
        result = state_remove_world_variable(state, "deep")
        assert state.model_dump(mode="json") == snapshot
        assert "deep" not in result.world_variables

    def test_state_remove_world_variable_missing_key_raises(self) -> None:
        state = _base_state(0)
        with pytest.raises(ReducerError, match="键不存在"):
            state_remove_world_variable(state, "nope")

    def test_state_set_scenario_state_pure_and_zero_aliasing(self) -> None:
        state = _base_state(0)
        snapshot = state.model_dump(mode="json")
        data = {"goal": "new goal"}
        scenario = ScenarioState(scenario_id="scn_new", stage="s", data=data)
        result = state_set_scenario_state(state, scenario)
        assert state.model_dump(mode="json") == snapshot
        assert result.scenario_state == scenario
        data["goal"] = "篡改"
        assert result.scenario_state.data == {"goal": "new goal"}


# —— payload 模型（§2.1：extra="forbid" 继承 ContractModel）——


class TestPayloadModels:
    def test_empty_payload_forbids_any_key(self) -> None:
        assert EmptyPayload.model_validate({}) == EmptyPayload()
        with pytest.raises(ValidationError):
            EmptyPayload.model_validate({"x": 1})

    def test_create_entity_payload_forbids_created_revision(self) -> None:
        with pytest.raises(ValidationError):
            CreateEntityPayload.model_validate({"created_revision": 5})
        p = CreateEntityPayload.model_validate({"entity_class": "npc", "tags": ["a"]})
        assert p.components == {}

    def test_set_world_variable_payload_requires_key(self) -> None:
        with pytest.raises(ValidationError):
            SetWorldVariablePayload.model_validate({"value": 1})
        assert SetWorldVariablePayload.model_validate({"key": "k", "value": 1}).key == "k"

    def test_remove_world_variable_payload_requires_key(self) -> None:
        with pytest.raises(ValidationError):
            RemoveWorldVariablePayload.model_validate({})
        assert RemoveWorldVariablePayload.model_validate({"key": "k"}).key == "k"

    def test_set_scenario_data_payload_defaults(self) -> None:
        p = SetScenarioDataPayload.model_validate({"data": {"a": 1}})
        assert p.scenario_id is None and p.stage is None and p.data == {"a": 1}


# —— EffectHandlerRegistry（§2.3 / D-P2-05）——


class TestHandlerRegistry:
    def test_default_registry_pre_registers_seven_in_order(self) -> None:
        reg = EffectHandlerRegistry()
        assert reg.effect_types() == (
            EFFECT_CREATE_ENTITY,
            EFFECT_REMOVE_ENTITY,
            EFFECT_SET_COMPONENT,
            EFFECT_REMOVE_COMPONENT,
            EFFECT_SET_WORLD_VARIABLE,
            EFFECT_REMOVE_WORLD_VARIABLE,
            EFFECT_SET_SCENARIO_DATA,
        )
        for et in reg.effect_types():
            assert reg.has(et)
            assert callable(reg.resolve(et))

    def test_default_handler_registry_is_fresh_instance(self) -> None:
        a = default_handler_registry()
        b = default_handler_registry()
        assert a is not b
        a.register(EffectTypeId("test.only_a"), lambda state, effect: state)
        assert not b.has(EffectTypeId("test.only_a"))

    def test_register_semantic_and_resolve(self) -> None:
        reg = EffectHandlerRegistry()

        def handler(state: WorldState, effect: ProposedEffect) -> WorldState:
            return state

        reg.register(EffectTypeId("test.foo"), handler)
        assert reg.has(EffectTypeId("test.foo"))
        assert reg.resolve(EffectTypeId("test.foo")) is handler

    def test_register_same_handler_idempotent(self) -> None:
        reg = EffectHandlerRegistry()

        def handler(state: WorldState, effect: ProposedEffect) -> WorldState:
            return state

        reg.register(EffectTypeId("test.dup"), handler)
        reg.register(EffectTypeId("test.dup"), handler)  # 幂等，不抛
        assert reg.resolve(EffectTypeId("test.dup")) is handler

    def test_register_different_handler_conflict(self) -> None:
        reg = EffectHandlerRegistry()

        def h1(state: WorldState, effect: ProposedEffect) -> WorldState:
            return state

        def h2(state: WorldState, effect: ProposedEffect) -> WorldState:
            return state

        reg.register(EffectTypeId("test.dup"), h1)
        with pytest.raises(HandlerConflictError):
            reg.register(EffectTypeId("test.dup"), h2)

    def test_effect_handler_alias_is_resolvable(self) -> None:
        """EffectHandler 类型别名即 resolve 的返回形态（§2.3 纯函数协议）。"""
        handler: EffectHandler | None = default_handler_registry().resolve(EFFECT_CREATE_ENTITY)
        assert handler is not None and callable(handler)

    def test_structural_handler_cannot_be_overridden(self) -> None:
        reg = EffectHandlerRegistry()
        with pytest.raises(HandlerConflictError):
            reg.register(EFFECT_SET_COMPONENT, lambda state, effect: state)

    def test_resolve_unregistered_returns_none(self) -> None:
        assert EffectHandlerRegistry().resolve(EffectTypeId("test.nope")) is None


# —— 写屏障：层二 运行时逃逸拦截（§2.6.2 / P1 §10.1 条件 C3）——


class TestWriteBarrier:
    """C3 正/反例：四条逃逸路径拦截 + 豁免窗口 + reducer 不受阻 + 复原。"""

    def test_armed_barrier_blocks_all_four_escape_paths(self) -> None:
        install_write_barrier()
        assert write_barrier_installed()
        state = _base_state(0)
        with pytest.raises(WriteBarrierError):
            state.model_copy(update={"world_revision": 99})
        with pytest.raises(WriteBarrierError):
            WorldState.model_construct(world_revision=Revision(1))
        with pytest.raises(WriteBarrierError):
            copy.copy(state)
        with pytest.raises(WriteBarrierError):
            copy.deepcopy(state)

    def test_armed_barrier_blocks_non_worldstate_contract_models(self) -> None:
        """类级包裹覆盖全部 ContractModel 子类（非仅 WorldState）。"""
        install_write_barrier()
        with pytest.raises(WriteBarrierError):
            Transaction.model_construct(
                transaction_id=TransactionId("txn_x"),
                status=TransactionStatus.ABORTED,
                base_revision=Revision(0),
            )
        with pytest.raises(WriteBarrierError):
            ScenarioState().model_copy(update={"scenario_id": "scn_hack"})
        with pytest.raises(WriteBarrierError):
            copy.deepcopy(EntityRecord(entity_id=EntityId("ent_x")))

    def test_p1_t07_escape_scenario_blocked(self) -> None:
        """P1-T07 原始逃逸场景：ABORTED 事务被 copy-update 出 commit_revision。"""
        install_write_barrier()
        txn = Transaction(
            transaction_id=TransactionId("txn_ab"),
            status=TransactionStatus.ABORTED,
            base_revision=Revision(5),
            abort_reason="x",
        )
        with pytest.raises(WriteBarrierError):
            txn.model_copy(update={"commit_revision": Revision(6)})
        with write_barrier_exempt():
            # 豁免窗口内该"病态构造"可行（仅供测试/诊断）
            hacked = txn.model_copy(update={"commit_revision": Revision(6)})
            assert int(hacked.commit_revision) == 6

    def test_exempt_window_allows_four_paths_and_is_minimal(self) -> None:
        install_write_barrier()
        state = _base_state(0)
        with write_barrier_exempt():
            copied = state.model_copy(update={"world_revision": Revision(99)})
            assert copied.world_revision == Revision(99)
            constructed = WorldState.model_construct(world_revision=Revision(1))
            assert constructed.world_revision == Revision(1)
            shallow = copy.copy(state)
            deep = copy.deepcopy(state)
            assert shallow == state and deep == state
        # 窗口最小：退出后立即恢复拦截
        with pytest.raises(WriteBarrierError):
            state.model_copy(update={"world_revision": 99})

    def test_write_barrier_context_allows(self) -> None:
        install_write_barrier()
        state = _base_state(0)
        with WriteBarrier():
            copied = state.model_copy(update={"world_revision": Revision(5)})
            assert copied.world_revision == Revision(5)
        with pytest.raises(WriteBarrierError):
            copy.deepcopy(state)

    def test_scopes_nest_by_depth(self) -> None:
        install_write_barrier()
        state = _base_state(0)
        with write_barrier_exempt():
            with WriteBarrier():
                state.model_copy()
            # 内层退出，外层豁免仍活动（深度计数）
            state.model_copy()
        with pytest.raises(WriteBarrierError):
            state.model_copy()

    def test_token_is_thread_local(self) -> None:
        """令牌为 threading.local（§2.6.2）：其他线程无令牌，仍被拦截。"""
        import threading

        install_write_barrier()
        state = _base_state(0)
        outcome: dict[str, str] = {}

        def worker() -> None:
            try:
                state.model_copy()
                outcome["other_thread"] = "allowed"
            except WriteBarrierError:
                outcome["other_thread"] = "blocked"

        with write_barrier_exempt():
            # 主线程令牌活动（对照）
            state.model_copy()
            t = threading.Thread(target=worker)
            t.start()
            t.join()
        assert outcome == {"other_thread": "blocked"}

    def test_reducer_runs_unimpeded_when_armed(self, f: _EffectFactory) -> None:
        """C3 正例：reducer 自身在武装态不受阻（§2.6.2）。"""
        install_write_barrier()
        state = _base_state(0)
        eff = f.proposed(
            "core.set_world_variable", _domain_target("world_variables"),
            {"key": "k", "value": 1},
        )
        txn = _committed_transaction(state, [eff])
        result = apply_transaction(state, txn)
        assert result.world_variables["k"] == 1
        assert result.world_revision == Revision(1)

    def test_semantic_handler_escape_paths_allowed_inside_apply(
        self, f: _EffectFactory
    ) -> None:
        """reducer 令牌覆盖其 handler：语义 handler 内的 model_copy 不被拦截。"""
        install_write_barrier()

        def sneaky(state: WorldState, effect: ProposedEffect) -> WorldState:
            return state.model_copy()

        handlers = default_handler_registry()
        handlers.register(EffectTypeId("test.sneaky"), sneaky)
        state = _base_state(0)
        eff = f.proposed("test.sneaky", _domain_target("world_variables"), {})
        result = apply_committed_effects(state, [f.committed(eff)], handlers=handlers)
        # 除 revision 推进（base+1，D-P2-06）外，内容与输入语义一致
        assert result.world_revision == Revision(1)
        expected = state.model_dump(mode="json")
        expected["world_revision"] = 1
        assert result.model_dump(mode="json") == expected

    def test_uninstall_restores_p1_semantics(self) -> None:
        install_write_barrier()
        state = _base_state(0)
        uninstall_write_barrier()
        assert not write_barrier_installed()
        copied = state.model_copy(update={"world_revision": Revision(7)})
        assert copied.world_revision == Revision(7)
        constructed = WorldState.model_construct(world_revision=Revision(2))
        assert constructed.world_revision == Revision(2)
        assert copy.copy(state) == state
        assert copy.deepcopy(state) == state

    def test_uninstall_when_not_installed_is_noop(self) -> None:
        uninstall_write_barrier()  # 未武装时无操作，不抛
        assert not write_barrier_installed()

    def test_install_is_idempotent_and_uninstall_once_restores(self) -> None:
        install_write_barrier()
        install_write_barrier()  # 幂等
        assert write_barrier_installed()
        uninstall_write_barrier()
        assert not write_barrier_installed()
        _base_state(0).model_copy()  # P1 语义复原


# —— 写屏障：层三 guard() 只读门面（§2.6.3）——


class TestGuardFacade:
    """guard() 只读门面：读路径可用，写路径一律拦截（与令牌无关）。"""

    def test_guard_delegates_readonly_facades(self) -> None:
        state = _base_state(0)
        g = guard(state)
        assert is_guarded(g)
        assert not is_guarded(state)
        # 4 个只读门面
        assert g.has_entity(EntityId("ent_alice")) is True
        assert g.has_entity(EntityId("ent_none")) is False
        assert g.entity_view(EntityId("ent_alice")) == state.entity_view(EntityId("ent_alice"))
        assert g.entity_view(EntityId("ent_none")) is None
        assert g.component_view(EntityId("ent_alice"), ComponentTypeId("space.position")) == {
            "x": 1,
            "y": 2,
        }
        assert g.entities_with_component(ComponentTypeId("space.position")) == (
            EntityId("ent_alice"),
        )
        # 公共字段只读
        assert g.world_revision == state.world_revision
        assert g.schema_version == state.schema_version
        assert g.entities == state.entities
        assert g.world_variables == state.world_variables
        assert g.scenario_state == state.scenario_state

    def test_guard_model_dump_exits(self) -> None:
        state = _base_state(0)
        g = guard(state)
        assert g.model_dump(mode="json") == state.model_dump(mode="json")
        assert g.model_dump_json() == state.model_dump_json()
        # 序列化出口 JSON 干净
        json.loads(g.model_dump_json())

    def test_guard_blocks_all_write_paths(self) -> None:
        state = _base_state(0)
        g = guard(state)
        with pytest.raises(WriteBarrierError):
            g.model_copy(update={"world_revision": 99})
        with pytest.raises(WriteBarrierError):
            g.model_construct()
        with pytest.raises(WriteBarrierError):
            copy.copy(g)
        with pytest.raises(WriteBarrierError):
            copy.deepcopy(g)
        with pytest.raises(WriteBarrierError):
            g.world_revision = Revision(99)  # 属性赋值
        with pytest.raises(WriteBarrierError):
            del g.entities  # 属性删除
        with pytest.raises(WriteBarrierError):
            g._with_world_revision(Revision(99))  # 私有缝隙访问
        with pytest.raises(WriteBarrierError):
            g.__wrapped  # 名称改写私有槽亦落入缝隙拦截
        with pytest.raises(AttributeError):
            g.no_such_public_attribute

    def test_guard_write_paths_blocked_even_when_armed(self) -> None:
        """层三与层二令牌无关：武装态下门面读路径可用、写路径仍拦截。"""
        install_write_barrier()
        state = _base_state(0)
        g = guard(state)
        assert g.has_entity(EntityId("ent_alice"))
        assert g.world_revision == Revision(0)
        with pytest.raises(WriteBarrierError):
            g.model_copy()

    def test_guard_is_not_a_contract_model(self) -> None:
        g = guard(_base_state(0))
        assert isinstance(g, GuardedWorldState)
        # 不继承 pydantic 模型：不是契约模型，不参与 round-trip
        from pydantic import BaseModel

        assert not isinstance(g, BaseModel)

    def test_guard_rejects_non_world_state(self) -> None:
        with pytest.raises(TypeError):
            guard(ScenarioState())

    def test_guard_entity_view_deep_frozen(self) -> None:
        """门面返回的视图深冻结（D-15 咨询性不变量的门面侧兑现）。"""
        g = guard(_base_state(0))
        view = g.entity_view(EntityId("ent_alice"))
        data = view.get_component(ComponentTypeId("space.position"))
        assert data is not None
        with pytest.raises(TypeError):
            data["x"] = 99  # MappingProxyType 只读

    def test_guard_container_views_deep_frozen(self) -> None:
        """B2 修复：entities / world_variables / scenario_state 容器级深冻结。

        顶层与嵌套的 ``__setitem__`` / ``__delitem__`` / ``clear`` / ``pop``
        等原地修改一律 TypeError；tags 转 tuple；权威状态零变化。
        """
        state = _base_state(0)
        snapshot = state.model_dump(mode="json")
        g = guard(state)

        with pytest.raises(TypeError):
            g.world_variables["calendar"] = {"day": 99}
        with pytest.raises(TypeError):
            del g.world_variables["calendar"]
        with pytest.raises(TypeError):
            g.world_variables.pop("calendar")
        with pytest.raises(TypeError):
            g.world_variables.clear()
        with pytest.raises(TypeError):
            g.world_variables.setdefault("injected", 1)
        with pytest.raises(TypeError):
            g.world_variables.update({"injected": 1})
        with pytest.raises(TypeError):
            g.world_variables["calendar"]["day"] = 99
        with pytest.raises(TypeError):
            g.world_variables["deep"]["l1"]["l2"] = 999

        with pytest.raises(TypeError):
            g.entities[EntityId("ent_intruder")] = g.entities[EntityId("ent_alice")]
        with pytest.raises(TypeError):
            del g.entities[EntityId("ent_alice")]
        with pytest.raises(TypeError):
            g.entities.clear()
        with pytest.raises(TypeError):
            g.entities.pop(EntityId("ent_alice"))

        alice = g.entities[EntityId("ent_alice")]
        with pytest.raises(TypeError):
            alice.components[ComponentTypeId("space.position")]["x"] = 55
        with pytest.raises(TypeError):
            alice.components[ComponentTypeId("intruder")] = {"x": 0}
        with pytest.raises(TypeError):
            del alice.components[ComponentTypeId("space.position")]
        with pytest.raises(TypeError):
            alice.components.clear()
        with pytest.raises(TypeError):
            alice.components.pop(ComponentTypeId("space.position"))
        with pytest.raises(TypeError):
            alice.tags[0] = "hacked"

        with pytest.raises(TypeError):
            g.scenario_state.data["goal"] = "篡改"
        with pytest.raises(TypeError):
            g.scenario_state.data.pop("goal")
        with pytest.raises(TypeError):
            g.scenario_state.data.clear()

        # 门面属性赋值 / 私有缝隙 / 复制逃逸 → WriteBarrierError（层三语义）
        with pytest.raises(WriteBarrierError):
            alice.entity_id = EntityId("ent_intruder")
        with pytest.raises(WriteBarrierError):
            alice._with_components({})
        with pytest.raises(WriteBarrierError):
            g.scenario_state.scenario_id = "scn_hijack"
        with pytest.raises(WriteBarrierError):
            copy.copy(alice)
        with pytest.raises(WriteBarrierError):
            copy.deepcopy(g.scenario_state)

        # 读路径与判等口径不变
        assert g.entities == state.entities
        assert g.world_variables == state.world_variables
        assert g.scenario_state == state.scenario_state
        assert alice.tags == ("shopkeeper",)
        assert alice.created_revision == Revision(0)
        # 复制出口：deepcopy 产出独立可变快照（合法工作副本模式，零别名）
        wv_copy = copy.deepcopy(g.world_variables)
        assert wv_copy == state.world_variables
        wv_copy["calendar"]["day"] = 99
        assert state.world_variables["calendar"]["day"] == 3, "快照突变不波及权威状态"
        # 全部攻击后权威状态零变化
        assert state.model_dump(mode="json") == snapshot

    def test_guard_repr_does_not_leak(self) -> None:
        g = guard(_base_state(3))
        text = repr(g)
        assert "GuardedWorldState" in text
        assert "world_revision=3" in text
