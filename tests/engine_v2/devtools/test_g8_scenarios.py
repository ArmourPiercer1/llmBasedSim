"""P8 W5 G8 场景族测试（SOT §6.1 G8 表 L1409–1424 + §5.2 A1–A12）。

交付 2（brief L107–120）：12 个扁平函数，覆盖 A1–A12（A2/A4/A6/A8/A9/
A11 各拆 2 函数）：

- A1/A2：save→load round-trip world_state 逐键相等 / contract 代篡改 →
  ``version_mismatch`` 显式；
- A3/A4：replay 终态 == 活管道终态 / replay 双跑全量文本字节一致（A4 已
  裁定 D-W5-1：本文件承担 SC-1 结构双跑；SC-2 语义 flavor 面 = 冻结 W2
  ``test_replay.py`` t2）；
- A5/A6：branch A/B 互不影响 / branch 信封身份（新 id / 版本检查空 /
  revision 不 bump）；
- A7：SC-3 non-checkpointable ref 默认 branch 显式拒绝（点名 backend）；
- A8/A9：dev 干预 trace 可辨识（DEV_INTERVENTION 恰 1 + DEVELOPER
  provenance）/ patch_state 正常提交管道（revision+1 / source /
  INTERVENTION cause 回指 record_id）；
- A10/A11：CLI 5 子命令 envelope 顶层键集 / tool / 版本稳定 / CLI 错误
  面 11 码闭集 + rc ∈ {1,2}；
- A12：SC-1 回 2 事件因果链 → producer（消费 W4 冻结 ``trace_query.py``
  面）。

纪律：零测试类、零 subprocess（扁平模块级函数；CLI 面走 conftest
``cli_runner`` 缝 = 进程内 ``run_devcontrol_cli`` + stdout 重定向）；
全用 devtools conftest 夹具（结构 SC-1；SC-3 经 ``make_sc3_runtime()``）；
零随机 / 零时钟（D5/D6：全部 id / wall time 为字面量）；断言消息中文 +
位置信息；测试侧 raw-dict ``json.dumps`` 一律 ``sort_keys=True,
ensure_ascii=False``。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.engine_v2.core import (
    CauseKind,
    CauseRef,
    EFFECT_SET_COMPONENT,
    EFFECT_SET_WORLD_VARIABLE,
    ComponentTypeId,
    EntityId,
    EntityTarget,
    EffectId,
    OriginKind,
    ProducerId,
    ProposedEffect,
    Provenance,
    Snapshot,
    StateDomainId,
    StateDomainTarget,
    TraceKind,
    TransactionStatus,
    WorldState,
    check_snapshot_versions,
)
from src.engine_v2.core.snapshot import snapshot as build_snapshot
from src.engine_v2.devtools.intervention import (
    DEVTOOLS_DEVELOPER_PRODUCER,
    DevelopmentCommand,
    apply_development_command,
)
from src.engine_v2.devtools.trace_query import TraceQuery
from src.engine_v2.persistence.base import P8_ERROR_CODES, PersistenceError
from src.engine_v2.persistence.branch import (
    BranchError,
    WorldInstanceHandle,
    branch_world,
)
from src.engine_v2.persistence.checkpoint import BackendCheckpointRegistry
from src.engine_v2.persistence.filesystem import FilesystemPersistenceBackend
from src.engine_v2.persistence.replay import replay_committed
from src.engine_v2.persistence.snapshot import to_persistence_snapshot
from tests.engine_v2.devtools.conftest import (
    build_p8_save,
    cli_runner,
    make_p8_backend,
    make_p8_executor,
    make_p8_runtime,
    make_p8_world,
    make_sc3_runtime,
    run_p8_script,
)

# —— §6.4 同族钉死字面量（零随机、零时钟）——

_WSI_SOURCE = "wsi_p8_sc1"
_WSI_BRANCH_A = "wsi_p8_g8a"
_WSI_BRANCH_B = "wsi_p8_g8b"
_SAVE_ID_SC1 = "save_p8_base"
_SAVE_ID_SC3 = "save_p8_sc3"
_WALL_TIME = "1970-01-01T00:00:00+00:00"
_RECORD_PATCH_ID = "trc_00000000000000000000000000000042"
_RULE_PRODUCER = "p8.rule"
_TOOL_NAME = "llmsim-devcontrol"
_ENVELOPE_KEYS = {"tool", "schema_version", "command", "ok", "data", "error"}


def _sc1_handle() -> WorldInstanceHandle:
    """SC-1 源 handle（零 backend_refs；W3 test_branch 同形）。"""
    return WorldInstanceHandle(_WSI_SOURCE, make_p8_world(), make_p8_runtime())


def _sc3_handle() -> WorldInstanceHandle:
    """SC-3 源 handle（A7 负样本：一条 non-checkpointable ref）。"""
    return WorldInstanceHandle(_WSI_SOURCE, make_p8_world(), make_sc3_runtime())


def _build_sc3_save(tmp_path: Path) -> None:
    """SC-3 save（A11 错误面；W4 ``test_cli.py::_build_sc3_save`` 同形）。

    SC-1 run 终态 + ``checkpointable=False`` runtime → ``save_p8_sc3``
    （与 SC-1 save 同 save 根）。
    """
    run = run_p8_script()
    snap = Snapshot(
        world_state=run.final_state,
        runtime_state=make_sc3_runtime(),
        world_instance_id=_WSI_SOURCE,
        created_logical_tick=3,
        project_version="1.0.0",
        module_versions={"core": "84a5d4f"},
    )
    envelope = to_persistence_snapshot(
        snap, trace_ref="trace.jsonl", created_wall_time=_WALL_TIME
    )
    backend = FilesystemPersistenceBackend(tmp_path / "saves_root")
    backend.save(
        save_id=_SAVE_ID_SC3,
        envelope=envelope,
        checkpoint_payloads={},
        trace_records=run.trace_records,
    )


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
        source=ProducerId(DEVTOOLS_DEVELOPER_PRODUCER),
        target=StateDomainTarget(domain=StateDomainId("world_variables")),
        payload={"key": "score", "value": value},
        base_revision=state.world_revision,
    )
    result = executor.run(
        (effect,),
        state,
        causal_root_id=causal_root,
        origin=Provenance(
            producer_id=ProducerId(DEVTOOLS_DEVELOPER_PRODUCER),
            origin=OriginKind.DEVELOPER,
        ),
    )
    return result.final_state


def _mutate_component(
    state: WorldState,
    executor,
    *,
    entity_id: str,
    effect_id: str,
    causal_root: str,
) -> WorldState:
    """组件象限修改（正常提交管道，K2 零直写；``marker`` 描述型 schema）。"""
    effect = ProposedEffect(
        effect_id=EffectId(effect_id),
        effect_type=EFFECT_SET_COMPONENT,
        source=ProducerId(DEVTOOLS_DEVELOPER_PRODUCER),
        target=EntityTarget(
            entity_id=EntityId(entity_id),
            component_type=ComponentTypeId("marker"),
        ),
        payload={"tag": "p8_g8b"},
        base_revision=state.world_revision,
    )
    result = executor.run(
        (effect,),
        state,
        causal_root_id=causal_root,
        origin=Provenance(
            producer_id=ProducerId(DEVTOOLS_DEVELOPER_PRODUCER),
            origin=OriginKind.DEVELOPER,
        ),
    )
    return result.final_state


def test_g8_1_save_load_same_world_state(tmp_path: Path) -> None:
    """G8-1（A1）：save→load round-trip，world_state 逐键相等（含 revision）。

    SOT §5.2 A1：SC-1 ``build_p8_save`` → ``backend.load`` →
    ``bundle.envelope.snapshot.world_state`` 与 save 前 ``WorldState``
    （= ``run.final_state``）的 ``model_dump(mode="json")`` 逐键相等（含
    ``world_revision``）。
    """
    run = run_p8_script()
    pre_dump = run.final_state.model_dump(mode="json")
    build_p8_save(tmp_path, run)
    bundle = make_p8_backend(tmp_path).load(save_id=_SAVE_ID_SC1)
    post_dump = bundle.envelope.snapshot.world_state.model_dump(mode="json")
    assert post_dump == pre_dump, (
        f"G8-1 save→load world_state 漂移（{_SAVE_ID_SC1}）："
        f"revision {post_dump.get('world_revision')!r} != {pre_dump.get('world_revision')!r}"
    )
    assert post_dump["world_revision"] == 3, (
        f"G8-1 world_revision 应为 3（SC-1 3 回合后），实际 {post_dump['world_revision']!r}"
    )


def test_g8_1_version_mismatch_explicit(tmp_path: Path) -> None:
    """G8-1b（A2）：contract 代篡改 → 999 → ``load`` 显式 ``version_mismatch``。

    SOT §5.2 A2：篡改 save 文本 ``contract_schema_version``（唯一出现 =
    嵌套 core ``Snapshot`` 字段；顶层镜像仅 project/module_versions）→
    嵌套 ``check_snapshot_versions`` 非空 → ``version_mismatch``；
    message 非空。
    """
    run = run_p8_script()
    save_dir = build_p8_save(tmp_path, run)
    snapshot_path = save_dir / "snapshot.json"
    text = snapshot_path.read_text(encoding="utf-8")
    new_text, count = re.subn(
        r'"contract_schema_version":\s*\d+',
        '"contract_schema_version": 999',
        text,
        count=1,
    )
    assert count == 1, (
        f"G8-1b contract_schema_version 应唯一出现于 {snapshot_path}，实际 {count} 处"
    )
    snapshot_path.write_text(new_text, encoding="utf-8")
    with pytest.raises(PersistenceError) as excinfo:
        make_p8_backend(tmp_path).load(save_id=_SAVE_ID_SC1)
    assert excinfo.value.code == "version_mismatch", (
        f"G8-1b（{snapshot_path} contract 代 999）期望 version_mismatch，"
        f"实际 {excinfo.value.code!r}"
    )
    assert excinfo.value.message, "G8-1b 错误 message 应非空"


def test_g8_2_replay_same_committed_state() -> None:
    """G8-2（A3）：replay 终态 == 活管道终态（base 0 → final 3）。

    SOT §5.2 A3：``replay_committed(make_p8_world(), run.trace_records)``
    终态 ``model_dump(mode="json")`` == 活管道终态（``run.final_state``）
    同面。
    """
    run = run_p8_script()
    result = replay_committed(make_p8_world(), run.trace_records)
    assert result.final_state.model_dump(mode="json") == run.final_state.model_dump(
        mode="json"
    ), "G8-2 replay 终态与活管道终态不一致（SC-1 3 回合 trace）"
    assert result.base_revision == 0, (
        f"G8-2 base_revision 应为 0，实际 {result.base_revision!r}"
    )
    assert result.final_revision == 3, (
        f"G8-2 final_revision 应为 3，实际 {result.final_revision!r}"
    )


def test_g8_2_replay_double_run_byte_identical() -> None:
    """G8-2b（A4；D-W5-1 已裁定）：replay 双跑全量文本字节一致。

    SOT §5.2 A4：SC-1 trace ``replay_committed`` 双跑，两次
    ``ReplayResult.final_state.model_dump(mode="json")`` 经
    ``json.dumps(…, sort_keys=True, ensure_ascii=False)`` 全量文本相等。
    范围裁定 D-W5-1：本文件承担 SC-1 结构双跑；SC-2 语义 flavor 面由
    冻结 W2 ``test_replay.py::test_replay_dynamics_flavor_semantic_handler``
    承担（SC-2 夹具仅 persistence 侧存在）。
    """
    run = run_p8_script()
    first = replay_committed(make_p8_world(), run.trace_records)
    second = replay_committed(make_p8_world(), run.trace_records)
    first_text = json.dumps(
        first.final_state.model_dump(mode="json"), sort_keys=True, ensure_ascii=False
    )
    second_text = json.dumps(
        second.final_state.model_dump(mode="json"), sort_keys=True, ensure_ascii=False
    )
    assert first_text == second_text, (
        "G8-2b replay 双跑终态全量文本不一致（A4 确定性；SC-1 结构面）"
    )


def test_g8_3_branch_ab_independent() -> None:
    """G8-3（A5）：branch A/B——改 A 的 world_variable + B 的组件，互不影响。

    SOT §5.2 A5：branch A/B 后：改 A 的 world_variable + B 的 entity 组件
    → 双方互不影响（dump 对比 source 与对方）。
    """
    source = _sc1_handle()
    registry = BackendCheckpointRegistry()
    branch_a = branch_world(
        source, new_world_instance_id=_WSI_BRANCH_A, registry=registry
    )
    branch_b = branch_world(
        source, new_world_instance_id=_WSI_BRANCH_B, registry=registry
    )
    executor = make_p8_executor()
    source_dump = source.world_state.model_dump(mode="json")
    b_dump = branch_b.handle.world_state.model_dump(mode="json")

    # —— 改 A（world_variable → 7）：B / source 不变 ——
    a1 = _mutate_world_variable(
        branch_a.handle.world_state,
        executor,
        value=7,
        effect_id="eff_p8_g8a_wv",
        causal_root="p8.g8.a",
    )
    a1_dump = a1.model_dump(mode="json")
    assert a1.world_variables["score"] == 7, (
        f"G8-3 A 侧修改未生效（{_WSI_BRANCH_A} score 应 7），"
        f"实际 {a1.world_variables.get('score')!r}"
    )
    assert branch_b.handle.world_state.model_dump(mode="json") == b_dump, (
        f"G8-3 改 A 后 B（{_WSI_BRANCH_B}）dump 变更——branch 别名泄漏"
    )
    assert source.world_state.model_dump(mode="json") == source_dump, (
        f"G8-3 改 A 后 source（{_WSI_SOURCE}）dump 变更——branch 别名泄漏"
    )

    # —— 改 B（ent_a 组件）：A / source 不变 ——
    b1 = _mutate_component(
        branch_b.handle.world_state,
        executor,
        entity_id="ent_a",
        effect_id="eff_p8_g8b_comp",
        causal_root="p8.g8.b",
    )
    assert b1.entities[EntityId("ent_a")].components["marker"] == {"tag": "p8_g8b"}, (
        f"G8-3 B 侧修改未生效（{_WSI_BRANCH_B} ent_a.marker 应 {{'tag': 'p8_g8b'}}），"
        f"实际 {b1.entities[EntityId('ent_a')].components.get('marker')!r}"
    )
    assert a1.model_dump(mode="json") == a1_dump, (
        f"G8-3 改 B 后 A 修改后对象（{_WSI_BRANCH_A}）变更——branch 别名泄漏"
    )
    assert source.world_state.model_dump(mode="json") == source_dump, (
        f"G8-3 改 B 后 source（{_WSI_SOURCE}）dump 变更——branch 别名泄漏"
    )


def test_g8_3_branch_envelope_identity() -> None:
    """G8-3b（A6）：branch 信封身份——新 id / 版本检查空 / revision 不 bump。

    SOT §5.2 A6：``handle.world_instance_id == 新 id``；
    ``check_snapshot_versions``（branch 产物经纯函数 ``snapshot`` 构造的
    信封）空；``handle.world_state.world_revision == source.world_revision``
    （branch 不 bump revision）。
    """
    source = _sc1_handle()
    branch_a = branch_world(
        source, new_world_instance_id=_WSI_BRANCH_A, registry=BackendCheckpointRegistry()
    )
    handle = branch_a.handle
    assert handle.world_instance_id == _WSI_BRANCH_A, (
        f"G8-3b 实例身份应为新 id，实际 {handle.world_instance_id!r}"
    )
    envelope = build_snapshot(
        handle.world_state, handle.runtime_state, handle.world_instance_id
    )
    issues = check_snapshot_versions(envelope)
    assert issues == (), (
        f"G8-3b branch 信封版本检查应空（{_WSI_BRANCH_A}），实际 {issues!r}"
    )
    assert handle.world_state.world_revision == source.world_state.world_revision, (
        f"G8-3b branch 不应 bump revision（source="
        f"{source.world_state.world_revision}），实际 {handle.world_state.world_revision}"
    )


def test_g8_4_noncheckpointable_explicit_reject() -> None:
    """G8-4（A7）：SC-3 non-checkpointable ref → 默认 branch 显式拒绝。

    SOT §5.2 A7：SC-3（``make_sc3_runtime()``）：默认 ``branch_world``
    （``allow_degraded=False``）→ ``BranchError``，``code ==
    "branch_rejected"``，``str(exc)`` 含该 backend_id（显式，非静默）。
    """
    source = _sc3_handle()
    with pytest.raises(BranchError) as excinfo:
        branch_world(
            source,
            new_world_instance_id="wsi_p8_g8c",
            registry=BackendCheckpointRegistry(),
        )
    assert excinfo.value.code == "branch_rejected", (
        f"G8-4 期望 branch_rejected，实际 {excinfo.value.code!r}"
    )
    assert "rigid_body" in str(excinfo.value), (
        f"G8-4 消息应点名 backend_id（rigid_body），实际 {str(excinfo.value)!r}"
    )


def test_g8_5_dev_intervention_trace_distinguishable() -> None:
    """G8-5（A8）：SC-1 回 1 后——DEV_INTERVENTION 恰 1 + DEVELOPER provenance。

    SOT §5.2 A8：回 1 ``patch_state`` 后：trace 中
    ``kind == TraceKind.DEV_INTERVENTION`` 恰 1 条（producer =
    ``devtools.developer``）；对应 committed 事务
    ``provenance.origin is OriginKind.DEVELOPER``。
    """
    world = make_p8_world()
    executor = make_p8_executor()
    command = DevelopmentCommand(
        command_id="dev-patch-1",
        kind="patch_state",
        payload={"target": "world_variable", "key": "score", "value": 1},
    )
    result = apply_development_command(
        command,
        world_state=world,
        executor=executor,
        logical_tick=1,
        intervention_record_id=_RECORD_PATCH_ID,
    )
    dev_records = [
        record for record in result.trace_records if record.kind is TraceKind.DEV_INTERVENTION
    ]
    assert len(dev_records) == 1, (
        f"G8-5（回 1 patch_state）DEV_INTERVENTION 应恰 1 条，实际 {len(dev_records)}"
    )
    (dev_record,) = dev_records
    assert str(dev_record.producer_id) == DEVTOOLS_DEVELOPER_PRODUCER, (
        f"G8-5 dev 记录 producer 应为 devtools.developer，"
        f"实际 {str(dev_record.producer_id)!r}"
    )
    committed = [
        txn
        for txn in result.cascade_result.transactions
        if txn.status is TransactionStatus.COMMITTED
    ]
    assert len(committed) == 1, (
        f"G8-5 committed 事务应恰 1 条，实际 {len(committed)}"
    )
    (txn,) = committed
    assert txn.provenance is not None, "G8-5 committed 事务缺 provenance"
    assert txn.provenance.origin is OriginKind.DEVELOPER, (
        f"G8-5 provenance.origin 应为 DEVELOPER，实际 {txn.provenance.origin!r}"
    )


def test_g8_5_patch_state_normal_commit_pipeline() -> None:
    """G8-5b（A9）：patch_state 正常提交管道（revision+1 / source / cause）。

    SOT §5.2 A9：revision +1；DEV 记录 payload ``command_id`` 与命令一致
    （D-P8-17 host 给出）；``CommittedEffect.source`` =
    ``devtools.developer``；cause 恰 1 INTERVENTION（ref_id 回指 dev 记录
    record_id）。
    """
    world = make_p8_world()
    executor = make_p8_executor()
    command = DevelopmentCommand(
        command_id="dev-patch-1",
        kind="patch_state",
        payload={"target": "world_variable", "key": "score", "value": 1},
    )
    result = apply_development_command(
        command,
        world_state=world,
        executor=executor,
        logical_tick=1,
        intervention_record_id=_RECORD_PATCH_ID,
    )
    assert result.changed is True, "G8-5b patch_state 应 changed=True"
    assert result.world_state.world_revision == world.world_revision + 1, (
        f"G8-5b revision 应 +1（{world.world_revision} → "
        f"{world.world_revision + 1}），实际 {result.world_state.world_revision}"
    )
    (dev_record,) = [
        record for record in result.trace_records if record.kind is TraceKind.DEV_INTERVENTION
    ]
    assert dev_record.payload["command"]["command_id"] == "dev-patch-1", (
        f"G8-5b dev 记录 payload command_id 失配（D-P8-17），实际 {dev_record.payload!r}"
    )
    (txn,) = [
        txn
        for txn in result.cascade_result.transactions
        if txn.status is TransactionStatus.COMMITTED
    ]
    (committed_effect,) = txn.effects
    assert str(committed_effect.effect.source) == DEVTOOLS_DEVELOPER_PRODUCER, (
        f"G8-5b CommittedEffect.source 应为 devtools.developer，"
        f"实际 {str(committed_effect.effect.source)!r}"
    )
    assert committed_effect.effect.cause_ids == [
        CauseRef(kind=CauseKind.INTERVENTION, ref_id=_RECORD_PATCH_ID)
    ], (
        f"G8-5b cause 应恰 1 INTERVENTION 回指 dev 记录"
        f"（{str(dev_record.record_id)}），实际 {committed_effect.effect.cause_ids!r}"
    )
    assert str(dev_record.record_id) == _RECORD_PATCH_ID, (
        f"G8-5b dev 记录 record_id 失配，实际 {str(dev_record.record_id)!r}"
    )


def test_g8_6_cli_envelope_schema_stable(tmp_path: Path) -> None:
    """G8-6（A10）：5 子命令 envelope 顶层键集 / tool / 版本稳定。

    SOT §5.2 A10：5 子命令（inspect / trace / replay / branch / test）
    stdout → JSON envelope 顶层键集 == 6 键字面量闭集；``tool ==
    "llmsim-devcontrol"``；``schema_version == 1``；ok 路径 ``ok == true``
    / ``error is None`` / rc 0。
    """
    build_p8_save(tmp_path, run_p8_script())
    cli = cli_runner(tmp_path)
    invocations = (
        ("inspect", _SAVE_ID_SC1),
        ("trace", _SAVE_ID_SC1),
        ("replay", _SAVE_ID_SC1),
        ("branch", _SAVE_ID_SC1, "--new-id", _WSI_BRANCH_A),
        ("test", _SAVE_ID_SC1),
    )
    for argv in invocations:
        stdout, code = cli(list(argv))
        envelope = json.loads(stdout)
        assert code == 0, f"G8-6 {argv!r} 应退出 0，实际 {code}"
        assert set(envelope) == _ENVELOPE_KEYS, (
            f"G8-6 {argv!r} envelope 顶层键集漂移，实际 {sorted(envelope)}"
        )
        assert envelope["tool"] == _TOOL_NAME, (
            f"G8-6 {argv!r} tool 漂移：{envelope['tool']!r}"
        )
        assert envelope["schema_version"] == 1, (
            f"G8-6 {argv!r} schema_version 漂移：{envelope['schema_version']!r}"
        )
        assert envelope["command"] == argv[0], (
            f"G8-6 {argv!r} command 字段漂移：{envelope['command']!r}"
        )
        assert envelope["ok"] is True, f"G8-6 {argv!r} ok 应为 true"
        assert envelope["error"] is None, f"G8-6 {argv!r} error 应为 None"


def test_g8_6_cli_error_closed_set(tmp_path: Path) -> None:
    """G8-6b（A11）：CLI 错误面闭集（11 码闭集 + rc ∈ {1,2} + 无未捕获异常）。

    SOT §5.2 A11：3 错误面（未知 save / 未知子命令 / SC-3 branch 拒绝）：
    每条 ``ok == false``；``error.code`` ∈ ``P8_ERROR_CODES``（base.py
    导出 11 码闭集）；rc ∈ {1,2}；stdout 始终可 JSON 解析（无未捕获
    异常）。
    """
    build_p8_save(tmp_path, run_p8_script())
    _build_sc3_save(tmp_path)
    cli = cli_runner(tmp_path)
    cases = (
        ("未知 save", ("inspect", "save_missing"), "save_not_found"),
        ("未知子命令", ("frobnicate", _SAVE_ID_SC1), "usage_error"),
        (
            "SC-3 branch 拒绝",
            ("branch", _SAVE_ID_SC3, "--new-id", "wsi_p8_g8c"),
            "branch_rejected",
        ),
    )
    for label, argv, expected_code in cases:
        stdout, code = cli(list(argv))
        envelope = json.loads(stdout)
        assert envelope["ok"] is False, f"G8-6b（{label}）ok 应为 false"
        assert code in (1, 2), (
            f"G8-6b（{label}）rc 应 ∈ {{1,2}}，实际 {code}"
        )
        assert envelope["error"]["code"] in P8_ERROR_CODES, (
            f"G8-6b（{label}）error.code 应 ∈ 11 码闭集，"
            f"实际 {envelope['error']['code']!r}"
        )
        assert envelope["error"]["code"] == expected_code, (
            f"G8-6b（{label}）期望 {expected_code}，实际 {envelope['error']['code']!r}"
        )


def test_g8_7_causal_chain_event_to_producer() -> None:
    """G8-7（A12）：SC-1 回 2 事件因果链 → producer（W4 trace_query 面）。

    SOT §5.2 A12：SC-1 回 2 event（``p8.rule`` 回合的 DOMAIN_EVENT 记录，
    唯一 ``world_revision == 2`` 事件记录）→ ``TraceQuery.causal_chain``：
    ``transaction`` 非 None；``effects`` 非空且每个
    ``effect.effect.source`` ∈ ``producers``；``producers`` 含
    ``p8.rule``（消费 W4 冻结 ``trace_query.py`` 面：10 方法 /
    ``CausalChain`` 6 字段）。
    """
    run = run_p8_script()
    event_records = [
        record
        for record in run.trace_records
        if record.kind is TraceKind.DOMAIN_EVENT and record.world_revision == 2
    ]
    assert len(event_records) == 1, (
        f"G8-7 回 2 DOMAIN_EVENT 应唯一，实际 {len(event_records)} 条"
    )
    (event_record,) = event_records
    event_id = str(event_record.payload["record"]["event_id"])
    chain = TraceQuery(run.trace_records).causal_chain(event_id)
    assert chain.transaction is not None, (
        f"G8-7 因果链缺 transaction（event_id={event_id}）"
    )
    assert len(chain.effects) > 0, (
        f"G8-7 因果链 effects 应非空（event_id={event_id}）"
    )
    for effect in chain.effects:
        assert str(effect.effect.source) in chain.producers, (
            f"G8-7 effect source {str(effect.effect.source)!r} 缺席 producers "
            f"{chain.producers!r}（event_id={event_id}）"
        )
    assert _RULE_PRODUCER in chain.producers, (
        f"G8-7 producers 应含 p8.rule（回 2 规则回合），实际 {chain.producers!r}"
    )
