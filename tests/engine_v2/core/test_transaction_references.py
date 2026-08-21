"""C7 数据级检查器 ``check_transaction_references`` 的回归验收（P1-T06 口径）。

**落位沿革（C2 义务闭环）**：P1-T06 时期本纯函数按任务包写入白名单
最小机械落位于**测试侧**（当时 core 契约模块冻结、不得新增）；本文件
模块 docstring 原"落位决定"段已随 **P2-T04 按 P1 设计 §10.1 义务 C2
晋升**而失效——实现体已**逐字移入** ``src/engine_v2/core/validation.py``
（签名 ``(state, txn) -> tuple[str, ...]`` 与全部语义零变化），测试侧
副本删除，本文件改为从 ``src.engine_v2.core.validation`` 导入
``check_transaction_references`` 与 ``TRANSACTION_REFERENCE_ISSUE_KINDS``
（原 ``ISSUE_KINDS`` 升格）。15 例测试断言**逐条保留**（验收口径不
变，只换被测对象来源）；``model_construct`` 用例按 P2 设计规范 §2.6.4
包入 ``write_barrier_exempt()``——无论写屏障是否武装、无论测试执行
顺序，全仓保持绿。

检查项（设计文档 §7.4 C7 三项，P1 只做数据级检查）：

1. ``missing_entity``——effect 的 target 为 entity 分支且指向
   ``state`` 中不存在的 entity（E5 口径：组件缺失**不是**错误——
   未挂载组件时门面查询返回 None，P1 不报；P2 validation 才判定）；
2. ``stale_revision``——``is_stale(effect.base_revision,
   state.world_revision)`` 成立（设计文档 §2.3 / §7.4 C7 口径：
   ``base_revision < current`` 可被 ``is_stale`` 判定；单向语义——
   ``base > current`` 不报）；
3. ``duplicated_effect_id``——同一事务内同一 ``effect_id`` 多次出现
   （KBC-2 重复累加防线；``Transaction`` 构造期不变量已拒绝此类数据
   （T04 C5 固化），本项为构造期之外拼装数据的数据级复检，纵深防御）。

不检查（明确边界）：state_domain 分支的 domain 词表（P2 authority
配置声明）；``event_ids`` / ``cascade`` 引用（P1 无状态级被引用方）。

全部用例无网络、无 LLM、无 API key（Spec §47 Phase 1 验收）。
"""

from __future__ import annotations

from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.effects import (
    CommittedEffect,
    EffectTypeId,
    EntityTarget,
    ProposedEffect,
    StateDomainId,
    StateDomainTarget,
)
from src.engine_v2.core.entity import EntityRecord
from src.engine_v2.core.ids import (
    EffectId,
    EntityId,
    ProducerId,
    TransactionId,
    new_transaction_id,
)
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.reducer import write_barrier_exempt
from src.engine_v2.core.revision import Revision, is_stale
from src.engine_v2.core.state import WorldState
from src.engine_v2.core.transaction import Transaction, TransactionStatus
from src.engine_v2.core.validation import (
    TRANSACTION_REFERENCE_ISSUE_KINDS,
    check_transaction_references,
)


# —— 测试样本工厂（自包含；值确定性构造，不依赖工厂随机性）——


def _make_provenance() -> Provenance:
    return Provenance(producer_id=ProducerId("rule.lock_system"), origin=OriginKind.RULE)


def _make_entity_target(entity_id: EntityId, component_type: str | None = None) -> EntityTarget:
    if component_type is None:
        return EntityTarget(entity_id=entity_id)
    return EntityTarget(entity_id=entity_id, component_type=ComponentTypeId(component_type))


def _make_state_domain_target() -> StateDomainTarget:
    return StateDomainTarget(domain=StateDomainId("world_variables"))


def _make_effect(
    effect_id: EffectId,
    base_revision: int,
    target: EntityTarget | StateDomainTarget,
) -> ProposedEffect:
    return ProposedEffect(
        effect_id=effect_id,
        effect_type=EffectTypeId("space.move"),
        source=ProducerId("dynamics.rigid_body"),
        target=target,
        payload={"dx": 1},
        base_revision=Revision(base_revision),
    )


def _make_committed(
    txn_id: TransactionId,
    base_revision: int,
    effects: list[ProposedEffect],
) -> list[CommittedEffect]:
    commit_revision = Revision(base_revision + 1)
    return [
        CommittedEffect(
            effect=effect,
            transaction_id=txn_id,
            commit_revision=commit_revision,
            sequence=sequence,
        )
        for sequence, effect in enumerate(effects)
    ]


def _make_transaction(base_revision: int, effects: list[ProposedEffect]) -> Transaction:
    txn_id = new_transaction_id()
    return Transaction(
        transaction_id=txn_id,
        status=TransactionStatus.COMMITTED,
        base_revision=Revision(base_revision),
        commit_revision=Revision(base_revision + 1),
        effects=_make_committed(txn_id, base_revision, effects),
    )


def _make_aborted_transaction(base_revision: int) -> Transaction:
    return Transaction(
        transaction_id=new_transaction_id(),
        status=TransactionStatus.ABORTED,
        base_revision=Revision(base_revision),
        abort_reason="validation failed",
    )


def _make_state(world_revision: int, entity_ids: list[EntityId]) -> WorldState:
    return WorldState(
        world_revision=Revision(world_revision),
        entities={
            eid: EntityRecord(entity_id=eid) for eid in entity_ids
        },
    )


_ENT_A = EntityId("ent_ref_a")
_ENT_B = EntityId("ent_ref_b")
_ENT_MISSING = EntityId("ent_ref_missing")


class TestCleanCases:
    """无问题场景：干净事务返回空元组。"""

    def test_fresh_transaction_no_issues(self) -> None:
        """base == current、目标 entity 全部在场 → 空报告（设计文档 §7.4 C7 反例口径）。"""
        state = _make_state(world_revision=5, entity_ids=[_ENT_A, _ENT_B])
        txn = _make_transaction(
            base_revision=5,
            effects=[
                _make_effect(EffectId("eff_ref_1"), 5, _make_entity_target(_ENT_A)),
                _make_effect(EffectId("eff_ref_2"), 5, _make_state_domain_target()),
                _make_effect(EffectId("eff_ref_3"), 5, _make_entity_target(_ENT_B, "space.position")),
            ],
        )
        assert check_transaction_references(state, txn) == ()

    def test_aborted_transaction_no_issues(self) -> None:
        """ABORTED 事务无 effects（C4 不变量）→ 空报告。"""
        state = _make_state(world_revision=5, entity_ids=[_ENT_A])
        assert check_transaction_references(state, _make_aborted_transaction(5)) == ()

    def test_future_base_revision_not_stale(self) -> None:
        """is_stale 单向语义：base > current 不陈旧，不误报（R6 口径交叉验证）。"""
        state = _make_state(world_revision=5, entity_ids=[_ENT_A])
        txn = _make_transaction(
            base_revision=7,
            effects=[_make_effect(EffectId("eff_ref_future"), 7, _make_entity_target(_ENT_A))],
        )
        assert is_stale(Revision(7), Revision(5)) is False
        assert check_transaction_references(state, txn) == ()


class TestMissingEntity:
    """C7 场景 1：effect 指向 missing entity。"""

    def test_missing_entity_reported_with_effect_and_entity(self) -> None:
        state = _make_state(world_revision=5, entity_ids=[_ENT_A])
        txn = _make_transaction(
            base_revision=5,
            effects=[_make_effect(EffectId("eff_ref_m1"), 5, _make_entity_target(_ENT_MISSING))],
        )
        issues = check_transaction_references(state, txn)
        assert issues == (f"missing_entity:eff_ref_m1:target={str(_ENT_MISSING)}",)

    def test_missing_component_is_not_missing_entity(self) -> None:
        """E5 口径：entity 在场但组件未挂载 ≠ 非法引用错误（P1 不报，P2 判定）。"""
        state = _make_state(world_revision=5, entity_ids=[_ENT_A])  # _ENT_A 无任何组件
        txn = _make_transaction(
            base_revision=5,
            effects=[
                _make_effect(
                    EffectId("eff_ref_m2"), 5, _make_entity_target(_ENT_A, "knowledge.belief")
                )
            ],
        )
        assert check_transaction_references(state, txn) == ()

    def test_state_domain_target_never_entity_checked(self) -> None:
        """state_domain 分支不参与 missing entity 检查（domain 词表属 P2 authority 配置）。"""
        state = _make_state(world_revision=5, entity_ids=[])
        txn = _make_transaction(
            base_revision=5,
            effects=[_make_effect(EffectId("eff_ref_m3"), 5, _make_state_domain_target())],
        )
        assert check_transaction_references(state, txn) == ()


class TestStaleRevision:
    """C7 场景 2：stale revision（``base_revision < current`` 可被 is_stale 判定）。"""

    def test_stale_revision_reported_with_base_and_current(self) -> None:
        state = _make_state(world_revision=813, entity_ids=[_ENT_A])
        txn = _make_transaction(
            base_revision=812,
            effects=[_make_effect(EffectId("eff_ref_s1"), 812, _make_entity_target(_ENT_A))],
        )
        issues = check_transaction_references(state, txn)
        assert issues == ("stale_revision:eff_ref_s1:base=812 current=813",)

    def test_fresh_base_not_reported(self) -> None:
        state = _make_state(world_revision=813, entity_ids=[_ENT_A])
        txn = _make_transaction(
            base_revision=813,
            effects=[_make_effect(EffectId("eff_ref_s2"), 813, _make_entity_target(_ENT_A))],
        )
        assert check_transaction_references(state, txn) == ()

    def test_each_effect_checked_independently(self) -> None:
        """事务内逐 effect 检查：一条陈旧一条新鲜 → 恰好一条 stale 报告。"""
        state = _make_state(world_revision=813, entity_ids=[_ENT_A, _ENT_B])
        txn = _make_transaction(
            base_revision=813,
            effects=[
                _make_effect(EffectId("eff_ref_s3"), 812, _make_entity_target(_ENT_A)),
                _make_effect(EffectId("eff_ref_s4"), 813, _make_entity_target(_ENT_B)),
            ],
        )
        issues = check_transaction_references(state, txn)
        assert issues == ("stale_revision:eff_ref_s3:base=812 current=813",)

    def test_spec9_example_values(self) -> None:
        """Spec §9 示例口径（base_world_revision=812 对照 current=813，设计文档 §7.1 R6 同源值）。"""
        state = _make_state(world_revision=813, entity_ids=[_ENT_A])
        assert is_stale(Revision(812), Revision(813)) is True
        txn = _make_transaction(
            base_revision=812,
            effects=[_make_effect(EffectId("eff_ref_s5"), 812, _make_entity_target(_ENT_A))],
        )
        assert len(check_transaction_references(state, txn)) == 1


class TestDuplicatedEffectId:
    """C7 场景 3：duplicated effect_id 进同一事务（KBC-2 重复累加防线）。

    ``Transaction`` 构造期不变量已拒绝重复 effect_id（T04 C5 固化）；
    本组用 ``model_construct`` 绕过构造期校验器，验证检查器对构造期之外
    拼装数据的数据级复检（纵深防御——未来 P2 管道若以非构造路径组装
    数据，本检查仍可捕获）。
    """

    def test_duplicated_effect_id_reported(self) -> None:
        state = _make_state(world_revision=5, entity_ids=[_ENT_A])
        effect = _make_effect(EffectId("eff_ref_dup"), 5, _make_entity_target(_ENT_A))
        txn_id = new_transaction_id()
        effects = _make_committed(txn_id, 5, [effect, effect])
        # 绕过 Transaction 构造期校验器（该不变量本身已由 T04 固化）；
        # 按 P2 设计规范 §2.6.4 包入 write_barrier_exempt()——无论写屏障
        # 是否武装、无论测试执行顺序，本用例恒绿。
        with write_barrier_exempt():
            txn = Transaction.model_construct(
                transaction_id=txn_id,
                status=TransactionStatus.COMMITTED,
                base_revision=Revision(5),
                commit_revision=Revision(6),
                effects=effects,
                event_ids=[],
                cascade=None,
                provenance=None,
                abort_reason=None,
                logical_tick=None,
            )
        issues = check_transaction_references(state, txn)
        assert issues == ("duplicated_effect_id:eff_ref_dup:count=2",)

    def test_unique_effect_ids_not_reported(self) -> None:
        state = _make_state(world_revision=5, entity_ids=[_ENT_A, _ENT_B])
        txn = _make_transaction(
            base_revision=5,
            effects=[
                _make_effect(EffectId("eff_ref_u1"), 5, _make_entity_target(_ENT_A)),
                _make_effect(EffectId("eff_ref_u2"), 5, _make_entity_target(_ENT_B)),
            ],
        )
        assert all(not i.startswith("duplicated_effect_id:") for i in check_transaction_references(state, txn))


class TestCheckerDiscipline:
    """检查器自身纪律：纯函数、结构化输出、只报告不处置。"""

    def test_pure_function_no_mutation(self) -> None:
        state = _make_state(world_revision=813, entity_ids=[_ENT_A])
        txn = _make_transaction(
            base_revision=812,
            effects=[_make_effect(EffectId("eff_ref_p1"), 812, _make_entity_target(_ENT_MISSING))],
        )
        state_before = state.model_dump(mode="json")
        txn_before = txn.model_dump(mode="json")
        issues = check_transaction_references(state, txn)
        assert issues  # 脏场景确实有报告
        assert state.model_dump(mode="json") == state_before, "检查器不得修改 state"
        assert txn.model_dump(mode="json") == txn_before, "检查器不得修改 txn"

    def test_returns_tuple_of_structured_strings(self) -> None:
        state = _make_state(world_revision=813, entity_ids=[])
        txn = _make_transaction(
            base_revision=812,
            effects=[_make_effect(EffectId("eff_ref_p2"), 812, _make_entity_target(_ENT_MISSING))],
        )
        issues = check_transaction_references(state, txn)
        assert isinstance(issues, tuple)
        assert len(issues) == 2  # 一条 missing_entity + 一条 stale_revision
        for issue in issues:
            assert isinstance(issue, str)
            kind = issue.split(":", 1)[0]
            assert kind in TRANSACTION_REFERENCE_ISSUE_KINDS, f"未知错误类别：{kind}"

    def test_new_entities_do_not_couple_checker_to_state_identity(self) -> None:
        """同一 txn 对"目标在场"与"目标缺失"两个 state 给出不同报告——
        检查确实读取了 state（而非仅依赖 txn 内部数据）。"""
        txn = _make_transaction(
            base_revision=5,
            effects=[_make_effect(EffectId("eff_ref_p3"), 5, _make_entity_target(_ENT_A))],
        )
        assert check_transaction_references(_make_state(5, [_ENT_A]), txn) == ()
        assert len(check_transaction_references(_make_state(5, []), txn)) == 1
