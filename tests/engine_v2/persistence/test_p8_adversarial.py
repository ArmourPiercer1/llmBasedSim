"""P8 W5 AD 对抗族测试（SOT §6.1 AD 表 L1341–1354 + §6.3 纪律）。

交付 1（brief L89–98）：10 个扁平函数 ``test_ad1``..``test_ad10``，三族：

- corruption（AD-1/2/3/8/9）：save 面字节级破坏（conftest ``corrupt_save``
  6 kind 闭集，SOT §6.2）→ 闭集码显式错误（SOT §3.4 11 码闭集）；
- replay（AD-4/5）：中间事务缺失 → 连续性断裂 ``ReplayError``（message 含
  两侧 revision）；SC-2 语义 effect 未注册 → ``ReplayError``（显式，
  不静默）；
- branch（AD-6/7/10）：degraded 结果面非静默；标量 checkpoint payload →
  ``schema_invalid``；branch-of-branch 三方独立（base/A/B 双向零别名，
  A22 同族）。

AD-4 replay 输入面说明（DEV-W5-6）：冻结 conftest 的
``corrupt_save(kind="drop_middle_txn")`` 删除 SC-1 17 行 trace 流的中间
行（= 回 2 的 ``validation_decision``，非事务）；A16 "中间事务缺失" 面
由测试侧对损坏后加载 trace 排除中位事务记录实现（文件侧破坏仍走
闭集 kind，AD 纪律合规）。

纪律：零测试类、零 subprocess（扁平模块级函数）；零随机 / 零时钟
（D5/D6：全部 id / wall time 为字面量或 conftest 面）；断言消息中文 +
位置信息；测试侧 raw-dict ``json.dumps`` 一律 ``sort_keys=True,
ensure_ascii=False``。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.engine_v2.core import (
    EFFECT_SET_WORLD_VARIABLE,
    BackendStateRef,
    EffectId,
    OriginKind,
    ProducerId,
    ProposedEffect,
    Provenance,
    StateDomainId,
    StateDomainTarget,
    TraceKind,
    WorldState,
)
from src.engine_v2.dynamics.backend import BackendMetadata
from src.engine_v2.dynamics.toy_rigid import ToyRigidDynamics
from src.engine_v2.persistence.base import PersistenceError
from src.engine_v2.persistence.branch import (
    BranchError,
    WorldInstanceHandle,
    branch_world,
)
from src.engine_v2.persistence.checkpoint import (
    BackendCheckpointRegistry,
    CheckpointError,
)
from src.engine_v2.persistence.filesystem import read_trace_records
from src.engine_v2.persistence.replay import ReplayError, replay_committed
from tests.engine_v2.persistence.conftest import (
    build_p8_dynamics_save,
    build_p8_save,
    corrupt_save,
    make_p8_backend,
    make_p8_executor,
    make_p8_runtime,
    make_p8_world,
    run_p8_script,
)

# —— §6.4 同族钉死字面量（零随机、零时钟）——

_SAVE_ID_SC1 = "save_p8_base"
_SAVE_ID_SC2 = "save_p8_dyn"
_WSI_SOURCE = "wsi_p8_sc1"
_TOY_SEED = 7
_DEV_PRODUCER = "devtools.developer"


def _toy_registry() -> BackendCheckpointRegistry:
    """toy 注册表（AD-2 restore 面；W2 test_checkpoint_registry 同族字面量）。"""
    registry = BackendCheckpointRegistry()
    registry.register(
        backend_id="rigid_body",
        metadata=BackendMetadata(
            backend_id="rigid_body",
            producer_id="rigid_body.producer",
            domains=(),
            determinism="deterministic",
            implementation_type="rule",
            fidelity="abstract",
            checkpointable=True,
            restorable=True,
            replayable=True,
        ),
        instance=ToyRigidDynamics(seed=_TOY_SEED),
    )
    return registry


def _mutate_world_variable(
    state: WorldState,
    executor,
    *,
    value: int,
    effect_id: str,
    causal_root: str,
) -> WorldState:
    """world_variable 象限修改（正常提交管道，K2 零直写；W3 test_branch 同形）。"""
    effect = ProposedEffect(
        effect_id=EffectId(effect_id),
        effect_type=EFFECT_SET_WORLD_VARIABLE,
        source=ProducerId(_DEV_PRODUCER),
        target=StateDomainTarget(domain=StateDomainId("world_variables")),
        payload={"key": "score", "value": value},
        base_revision=state.world_revision,
    )
    result = executor.run(
        (effect,),
        state,
        causal_root_id=causal_root,
        origin=Provenance(producer_id=ProducerId(_DEV_PRODUCER), origin=OriginKind.DEVELOPER),
    )
    return result.final_state


def test_ad1_truncated_snapshot_json(tmp_path: Path) -> None:
    """AD-1（A15；corruption）：snapshot.json 半截断 → ``load`` 显式 ``corrupt_file``。

    SOT §6.1 AD 表 t1；§6.2 ``corrupt_save`` 闭集（truncate_snapshot：
    snapshot.json 截半，JSON 词法级损坏）；§3.3 load 门（JSON 词法损坏 →
    ``corrupt_file``）。
    """
    run = run_p8_script()
    save_dir = build_p8_save(tmp_path, run)
    corrupt_save(save_dir, kind="truncate_snapshot")
    with pytest.raises(PersistenceError) as excinfo:
        make_p8_backend(tmp_path).load(save_id=_SAVE_ID_SC1)
    assert excinfo.value.code == "corrupt_file", (
        f"AD-1（{save_dir / 'snapshot.json'} 截半）期望 corrupt_file，"
        f"实际 {excinfo.value.code!r}"
    )


def test_ad2_checkpoint_seed_type_corrupt(tmp_path: Path) -> None:
    """AD-2（A17；corruption）：checkpoint seed 类型损坏 → ``schema_invalid``。

    SOT §6.1 AD 表 t2；ERR-P8-03 判别最窄实现：实例侧异常 ``str`` casefold
    含 ``version`` → 版本类，余 → 形态类。冻结 ``dynamics/toy_rigid.py``
    restore 的 seed 失败消息 = ``checkpoint.seed 必须为 int（bool 拒绝）…``
    （不含 ``version`` → 形态类）。注释锚 ERR-P8-03。
    """
    save = build_p8_dynamics_save(tmp_path)
    corrupt_save(save.save_dir, kind="bad_checkpoint_seed")
    bundle = make_p8_backend(tmp_path).load(save_id=_SAVE_ID_SC2)
    registry = _toy_registry()
    with pytest.raises(CheckpointError) as excinfo:
        registry.restore(
            backend_id="rigid_body",
            checkpoint=bundle.checkpoint_payloads["rigid_body"],
        )
    # ERR-P8-03：seed 失败消息不含 version → 形态类码（非 version_mismatch）
    assert excinfo.value.code == "schema_invalid", (
        f"AD-2（{save.save_dir / 'checkpoints' / 'rigid_body.json'} seed 损坏）"
        f"期望 schema_invalid（ERR-P8-03 形态类），实际 {excinfo.value.code!r}"
    )
    assert "必须为 int" in str(excinfo.value), (
        f"AD-2 期望 toy restore seed 失败消息，实际 {str(excinfo.value)!r}"
    )


def test_ad3_version_downgrade_envelope(tmp_path: Path) -> None:
    """AD-3（corruption）：``persistence_format_version`` 降 0 → ``version_mismatch``。

    SOT §6.1 AD 表 t3（version 降级 0/999 → ``version_mismatch``）；§3.3
    snapshot 门（``persistence_format_version != 1`` → ``version_mismatch``）。
    """
    run = run_p8_script()
    save_dir = build_p8_save(tmp_path, run)
    corrupt_save(save_dir, kind="version_zero")
    with pytest.raises(PersistenceError) as excinfo:
        make_p8_backend(tmp_path).load(save_id=_SAVE_ID_SC1)
    assert excinfo.value.code == "version_mismatch", (
        f"AD-3（{save_dir / 'snapshot.json'} 版本降级）期望 version_mismatch，"
        f"实际 {excinfo.value.code!r}"
    )


def test_ad4_replay_middle_transaction_missing(tmp_path: Path) -> None:
    """AD-4（A16；replay）：中间事务缺失 → ``ReplayError`` 含两侧 revision。

    SOT §6.1 AD 表 t4；replay.py 连续性门（``base_revision 断裂：…
    base_revision=N != world_revision=M``）。DEV-W5-6：冻结 conftest 的
    ``drop_middle_txn`` 删流中间行（回 2 ``validation_decision``，非事务）；
    replay 输入面 = 对损坏后加载 trace 排除中位事务记录（文件破坏走闭集
    kind）。
    """
    run = run_p8_script()
    save_dir = build_p8_save(tmp_path, run)
    corrupt_save(save_dir, kind="drop_middle_txn")
    bundle = make_p8_backend(tmp_path).load(save_id=_SAVE_ID_SC1)
    txn_records = [r for r in bundle.trace_records if r.kind is TraceKind.TRANSACTION]
    assert len(txn_records) == 3, (
        f"AD-4 SC-1 事务数应为 3，实际 {len(txn_records)}（{save_dir / 'trace.jsonl'}）"
    )
    dropped = txn_records[len(txn_records) // 2]
    replay_input = tuple(r for r in bundle.trace_records if r is not dropped)
    with pytest.raises(ReplayError) as excinfo:
        replay_committed(make_p8_world(), replay_input)
    message = str(excinfo.value)
    assert "base_revision=2" in message, (
        f"AD-4 消息应含断裂侧 revision（dropped={dropped.transaction_id}），"
        f"实际 {message!r}"
    )
    assert "world_revision=1" in message, (
        f"AD-4 消息应含 world 侧 revision（dropped={dropped.transaction_id}），"
        f"实际 {message!r}"
    )


def test_ad5_replay_unregistered_semantic_effect(tmp_path: Path) -> None:
    """AD-5（replay）：SC-2 ``gem.moved`` 语义 effect 未注册 → 显式 ``ReplayError``。

    SOT §6.1 AD 表 t5：handlers 缺省（冻结 ``default_handler_registry``，
    无语义 handler 注入——同 test_replay t1 调用面）；初始态经冻结缝惰性
    导入 ``make_p7_world``（test_replay t2 L83–87 先例）。未注册 effect
    类型不静默放行——显式错误。
    """
    from tests.engine_v2.dynamics.conftest import make_p7_world

    build_p8_dynamics_save(tmp_path)
    bundle = make_p8_backend(tmp_path).load(save_id=_SAVE_ID_SC2)
    with pytest.raises(ReplayError) as excinfo:
        replay_committed(make_p7_world(), bundle.trace_records)
    message = str(excinfo.value)
    assert "gem.moved" in message, (
        f"AD-5 消息应点名未注册 effect_type（_SAVE_ID_SC2 trace），实际 {message!r}"
    )


def test_ad6_branch_degraded_not_silent() -> None:
    """AD-6（branch）：``allow_degraded=True`` → 无异常 + 结果面点名 backend。

    SOT §6.1 AD 表 t6（行为面 = W3 test_branch t7 同族；AD 纪律 = 独立
    生命周期 + 断言面）：non-checkpointable ref 降级为显式报告，非静默。
    """
    ref = BackendStateRef(
        backend_id="rigid_body",
        backend_kind="dynamics",
        checkpointable=False,
    )
    source = WorldInstanceHandle(
        "wsi_p8_ad6", make_p8_world(), make_p8_runtime(backend_refs=(ref,))
    )
    result = branch_world(
        source,
        new_world_instance_id="wsi_p8_ad6_a",
        registry=BackendCheckpointRegistry(),
        allow_degraded=True,
    )
    assert result.degraded_backends == ("rigid_body",), (
        f"AD-6 degraded 面应点名 rigid_body（wsi_p8_ad6 → wsi_p8_ad6_a），"
        f"实际 {result.degraded_backends!r}"
    )


def test_ad7_branch_checkpoint_payload_non_mapping() -> None:
    """AD-7（branch）：checkpoint payload 给标量（非 mapping）→ ``schema_invalid``。

    SOT §6.1 AD 表 t7；branch.py L179 面（缺失 → 拒绝；非 dict →
    ``schema_invalid``；message 点名 backend_id）。
    """
    ref = BackendStateRef(
        backend_id="rigid_body",
        backend_kind="dynamics",
        checkpointable=True,
    )
    source = WorldInstanceHandle(
        "wsi_p8_ad7", make_p8_world(), make_p8_runtime(backend_refs=(ref,))
    )
    with pytest.raises(BranchError) as excinfo:
        branch_world(
            source,
            new_world_instance_id="wsi_p8_ad7_a",
            registry=BackendCheckpointRegistry(),
            checkpoints={"rigid_body": "not-a-mapping"},
        )
    assert excinfo.value.code == "schema_invalid", (
        f"AD-7（rigid_body payload 标量）期望 schema_invalid，"
        f"实际 {excinfo.value.code!r}"
    )
    assert "rigid_body" in str(excinfo.value), (
        f"AD-7 消息应点名 backend_id，实际 {str(excinfo.value)!r}"
    )


def test_ad8_trace_jsonl_mid_corrupt(tmp_path: Path) -> None:
    """AD-8（corruption）：trace.jsonl 行级垃圾 → ``read_trace_records`` 显式（行号）。

    SOT §6.1 AD 表 t8；§6.2 ``corrupt_save`` 闭集（bad_trace_line：冻结
    conftest 损坏点 = 第 2 行 ``{not valid json``）；filesystem.py
    ``read_trace_records`` 门（``trace line {lineno} 非法 JSON：…`` →
    ``corrupt_file``）。
    """
    run = run_p8_script()
    save_dir = build_p8_save(tmp_path, run)
    corrupt_save(save_dir, kind="bad_trace_line")
    with pytest.raises(PersistenceError) as excinfo:
        read_trace_records(save_dir / "trace.jsonl")
    assert excinfo.value.code == "corrupt_file", (
        f"AD-8（{save_dir / 'trace.jsonl'} 行级损坏）期望 corrupt_file，"
        f"实际 {excinfo.value.code!r}"
    )
    assert "trace line 2" in str(excinfo.value), (
        f"AD-8 消息应含行号（损坏点 = 第 2 行），实际 {str(excinfo.value)!r}"
    )


def test_ad9_index_points_missing_dir(tmp_path: Path) -> None:
    """AD-9（corruption）：索引悬空（目录删）→ ``save_not_found``。

    SOT §6.1 AD 表 t9；§6.2 ``corrupt_save`` 闭集（dangling_index：
    ``shutil.rmtree`` save 目录、index.json 悬空）；filesystem.py ``load``
    门（index 条目目录缺失 → ``save_not_found``，message 点名"save 目录
    缺失"）。
    """
    run = run_p8_script()
    save_dir = build_p8_save(tmp_path, run)
    corrupt_save(save_dir, kind="dangling_index")
    with pytest.raises(PersistenceError) as excinfo:
        make_p8_backend(tmp_path).load(save_id=_SAVE_ID_SC1)
    assert excinfo.value.code == "save_not_found", (
        f"AD-9（index 悬空条目 {_SAVE_ID_SC1}）期望 save_not_found，"
        f"实际 {excinfo.value.code!r}"
    )
    assert "save 目录缺失" in str(excinfo.value), (
        f"AD-9 消息应点名 save 目录缺失，实际 {str(excinfo.value)!r}"
    )


def test_ad10_branch_of_branch_independent(tmp_path: Path) -> None:
    """AD-10（branch）：branch-of-branch 三方独立（base/A/B 双向零别名，A22 同族）。

    SOT §6.1 AD 表 t10：base → A → B（B 自 A 的 handle 分叉）；改 A 的
    state → base/B dump 不变；改 B → base/A 不变。每方修改均经正常提交
    管道（K2 零直写）。
    """
    run = run_p8_script()
    base = WorldInstanceHandle(_WSI_SOURCE, run.final_state, run.runtime_state)
    registry = BackendCheckpointRegistry()
    branch_a = branch_world(
        base, new_world_instance_id="wsi_p8_ad10a", registry=registry
    )
    branch_b = branch_world(
        branch_a.handle, new_world_instance_id="wsi_p8_ad10b", registry=registry
    )
    executor = make_p8_executor()
    base_dump = base.world_state.model_dump(mode="json")
    a_dump = branch_a.handle.world_state.model_dump(mode="json")
    b_dump = branch_b.handle.world_state.model_dump(mode="json")

    # —— 改 A（world_variable → 21）：base / B 不变 ——
    a1 = _mutate_world_variable(
        branch_a.handle.world_state,
        executor,
        value=21,
        effect_id="eff_p8_ad10_a",
        causal_root="p8.ad10.a",
    )
    a1_dump = a1.model_dump(mode="json")
    assert a1.world_variables["score"] == 21, (
        f"AD-10 A 侧修改未生效（wsi_p8_ad10a score 应 21），"
        f"实际 {a1.world_variables.get('score')!r}"
    )
    assert base.world_state.model_dump(mode="json") == base_dump, (
        "AD-10 改 A 后 base（wsi_p8_sc1）dump 变更——branch 别名泄漏"
    )
    assert branch_b.handle.world_state.model_dump(mode="json") == b_dump, (
        "AD-10 改 A 后 B（wsi_p8_ad10b）dump 变更——branch 别名泄漏"
    )

    # —— 改 B（world_variable → 31）：base / A 不变 ——
    b1 = _mutate_world_variable(
        branch_b.handle.world_state,
        executor,
        value=31,
        effect_id="eff_p8_ad10_b",
        causal_root="p8.ad10.b",
    )
    assert b1.world_variables["score"] == 31, (
        f"AD-10 B 侧修改未生效（wsi_p8_ad10b score 应 31），"
        f"实际 {b1.world_variables.get('score')!r}"
    )
    assert base.world_state.model_dump(mode="json") == base_dump, (
        "AD-10 改 B 后 base（wsi_p8_sc1）dump 变更——branch 别名泄漏"
    )
    assert branch_a.handle.world_state.model_dump(mode="json") == a_dump, (
        "AD-10 改 B 后 A（wsi_p8_ad10a）dump 变更——branch 别名泄漏"
    )
    assert a1.model_dump(mode="json") == a1_dump, (
        "AD-10 改 B 后 A 修改后对象（eff_p8_ad10_a 产物）变更——别名泄漏"
    )
