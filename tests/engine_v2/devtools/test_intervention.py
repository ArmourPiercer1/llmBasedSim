"""P8 T06 intervention 面测试（SOT §6.1 t1–t12）。

钉死面（§6.1 表逐项对应）：

- t1 6 种 kind == Spec §22 字面量 + 三子集 partition 断言（并集 == 全集、
  两两交集空）；
- t2 **A19**：未知 kind → ``usage_error``；
- t3 payload 含非 JSON 值 → ``schema_invalid``；
- t4 空/纯空白 command_id → ``schema_invalid``（id host 给出）；
- t5 组件 patch：revision +1、组件落位、结构 handler 路径（零测试侧语义
  handler 依赖）；
- t6 包裹面：source/cause_ids/base_revision 字段断言；
- t7 事务 ``provenance`` 字段级（A8 深化：DEVELOPER origin +
  CommittedEffect.source/cause_ids）；
- t8 2 指令面（pause/step）+ state dump 不变；
- t9 指令含 entity_id；缺 key → ``usage_error``；
- t10 ``branch`` kind：无世界变更 + ``("branch",)`` 指令（DEV-P8-3）；
- t11 4 族 ``InterventionResult.to_dict`` clean（runtime 控制 / 实例级 /
  patch / inject）；
- t12 ``DEVTOOLS_DEVELOPER_PRODUCER`` fullmatch 冻结 pattern。

纪律：扁平函数（零 class / 零 subprocess / 零跨函数状态）；确定性（D6：
record_id / command_id 全部 ``trc_`` / 字面量）；世界变更型经正常提交
管道 ``CascadeExecutor.run``（K2 零旁路；K3 测试侧 policy 显式放行）。
"""

from __future__ import annotations

import re

import pytest

from src.engine_v2.core import (
    CauseKind,
    CauseRef,
    EFFECT_SET_COMPONENT,
    EffectId,
    EntityId,
    OriginKind,
    PRODUCER_ID_PATTERN,
    TraceKind,
    TransactionStatus,
    assert_json_clean,
)
from src.engine_v2.devtools.intervention import (
    DEVTOOLS_DEVELOPER_PRODUCER,
    DEVELOPMENT_COMMAND_KINDS,
    INSTANCE_LEVEL_KINDS,
    RUNTIME_CONTROL_KINDS,
    WORLD_MUTATING_KINDS,
    DevelopmentCommand,
    InterventionError,
    apply_development_command,
    to_intervention_effects,
)
from tests.engine_v2.devtools.conftest import make_p8_executor, make_p8_world

# —— record_id 字面量（K7 零 uuid4；§6.4 同族：确定性 host 给出）——

_RECORD_PATCH_ID = "trc_00000000000000000000000000000042"
_RECORD_INJECT_ID = "trc_00000000000000000000000000000043"
_RECORD_PAUSE_ID = "trc_00000000000000000000000000000050"
_RECORD_STEP_ID = "trc_00000000000000000000000000000051"
_RECORD_FW_ID = "trc_00000000000000000000000000000052"
_RECORD_FW_BAD_ID = "trc_00000000000000000000000000000053"
_RECORD_BRANCH_ID = "trc_00000000000000000000000000000054"
_RECORD_T11_PAUSE_ID = "trc_00000000000000000000000000000055"
_RECORD_T11_BRANCH_ID = "trc_00000000000000000000000000000056"
_RECORD_T11_PATCH_ID = "trc_00000000000000000000000000000057"
_RECORD_T11_INJECT_ID = "trc_00000000000000000000000000000058"


def _patch_command(value: object = 1) -> DevelopmentCommand:
    """``patch_state`` world_variable 命令（§6.4 字面量 command_id）。"""
    return DevelopmentCommand(
        command_id="dev-patch-1",
        kind="patch_state",
        payload={"target": "world_variable", "key": "score", "value": value},
    )


def test_command_closed_set_matches_spec() -> None:
    """t1：6 种 == Spec §22 字面量 + 三子集 partition 断言。"""
    assert DEVELOPMENT_COMMAND_KINDS == (
        "pause",
        "step",
        "force_wake",
        "inject_event",
        "patch_state",
        "branch",
    )
    full = set(DEVELOPMENT_COMMAND_KINDS)
    subsets = (
        set(WORLD_MUTATING_KINDS),
        set(RUNTIME_CONTROL_KINDS),
        set(INSTANCE_LEVEL_KINDS),
    )
    # 并集 == 全集
    assert subsets[0] | subsets[1] | subsets[2] == full
    # 两两交集空
    assert subsets[0] & subsets[1] == set()
    assert subsets[0] & subsets[2] == set()
    assert subsets[1] & subsets[2] == set()
    # 各子集 ⊆ 全集
    for subset in subsets:
        assert subset <= full


def test_command_unknown_kind_rejected() -> None:
    """t2（**A19**）：``kind="teleport"`` → ``InterventionError(usage_error)``。"""
    with pytest.raises(InterventionError) as excinfo:
        DevelopmentCommand(command_id="dev-teleport-1", kind="teleport", payload={})
    assert excinfo.value.code == "usage_error"


def test_command_payload_must_be_json_clean() -> None:
    """t3：payload 含非 JSON 值（set）→ ``schema_invalid``。"""
    with pytest.raises(InterventionError) as excinfo:
        DevelopmentCommand(
            command_id="dev-dirty-1", kind="pause", payload={"v": {1, 2}}
        )
    assert excinfo.value.code == "schema_invalid"


def test_command_id_host_given() -> None:
    """t4：空/纯空白 command_id → ``schema_invalid``；host 给值逐字保留。"""
    for bad_id in ("", "   "):
        with pytest.raises(InterventionError) as excinfo:
            DevelopmentCommand(command_id=bad_id, kind="pause", payload={})
        assert excinfo.value.code == "schema_invalid"
    command = DevelopmentCommand(command_id="dev-host-1", kind="pause", payload={})
    assert command.command_id == "dev-host-1"


def test_patch_state_component_commit() -> None:
    """t5：组件 patch——revision +1、组件落位、结构 handler 路径。"""
    world = make_p8_world()
    executor = make_p8_executor()
    command = DevelopmentCommand(
        command_id="dev-patch-1",
        kind="patch_state",
        payload={
            "target": "component",
            "entity_id": "ent_a",
            "key": "marker",
            "data": {"tag": "p8_rule"},
        },
    )
    result = apply_development_command(
        command,
        world_state=world,
        executor=executor,
        logical_tick=1,
        intervention_record_id=_RECORD_PATCH_ID,
    )
    assert result.changed is True
    assert result.world_state.world_revision == world.world_revision + 1
    assert (
        result.world_state.entities[EntityId("ent_a")].components["marker"]
        == {"tag": "p8_rule"}
    )
    # 结构 handler 路径：冻结 default registry 的 core.set_component
    # （零测试侧语义 handler 依赖）
    committed = [
        txn
        for txn in result.cascade_result.transactions
        if txn.status is TransactionStatus.COMMITTED
    ]
    assert len(committed) == 1
    (committed_effect,) = committed[0].effects
    assert committed_effect.effect.effect_type == EFFECT_SET_COMPONENT
    # A9 面：CommittedEffect.source + cause_ids（INTERVENTION → record_id）
    assert committed_effect.effect.source == DEVTOOLS_DEVELOPER_PRODUCER
    assert committed_effect.effect.cause_ids == [
        CauseRef(kind=CauseKind.INTERVENTION, ref_id=_RECORD_PATCH_ID)
    ]


def test_inject_event_wraps_proposed_effect() -> None:
    """t6：包裹面——source/cause_ids/base_revision 字段断言。"""
    world = make_p8_world()
    command = DevelopmentCommand(
        command_id="dev-inject-1",
        kind="inject_event",
        payload={
            "effect_id": "eff_p8_dev_inject_1",
            "effect_type": "core.set_world_variable",
            "target_kind": "state_domain",
            "domain": "world_variables",
            "payload": {"key": "score", "value": 2},
        },
    )
    (wrapped,) = to_intervention_effects(
        command,
        base_revision=world.world_revision,
        intervention_record_id=_RECORD_INJECT_ID,
    )
    assert wrapped.command_id == "dev-inject-1"
    effect = wrapped.effect
    assert effect.effect_id == EffectId("eff_p8_dev_inject_1")
    assert effect.effect_type == "core.set_world_variable"
    assert effect.source == DEVTOOLS_DEVELOPER_PRODUCER
    assert effect.base_revision == world.world_revision
    assert effect.cause_ids == [
        CauseRef(kind=CauseKind.INTERVENTION, ref_id=_RECORD_INJECT_ID)
    ]
    # 非世界变更型 kind → 空元组（partition 语义面）
    pause_command = DevelopmentCommand(command_id="dev-pause-x", kind="pause", payload={})
    assert to_intervention_effects(
        pause_command,
        base_revision=world.world_revision,
        intervention_record_id=_RECORD_PAUSE_ID,
    ) == ()


def test_intervention_origin_developer_fields() -> None:
    """t7：事务 ``provenance`` 字段级（A8 深化）。"""
    world = make_p8_world()
    executor = make_p8_executor()
    command = _patch_command()
    result = apply_development_command(
        command,
        world_state=world,
        executor=executor,
        logical_tick=1,
        intervention_record_id=_RECORD_PATCH_ID,
    )
    # DEV_INTERVENTION 恰 1 条（producer = devtools.developer；干预时刻读数）
    dev_records = [
        record for record in result.trace_records if record.kind is TraceKind.DEV_INTERVENTION
    ]
    assert len(dev_records) == 1
    (dev_record,) = dev_records
    assert dev_record.producer_id == DEVTOOLS_DEVELOPER_PRODUCER
    assert dev_record.record_id == _RECORD_PATCH_ID
    assert dev_record.world_revision == 0
    assert dev_record.payload == {
        "command": {
            "command_id": "dev-patch-1",
            "kind": "patch_state",
            "payload": {"target": "world_variable", "key": "score", "value": 1},
        }
    }
    # committed 事务 provenance 字段级
    committed = [
        txn
        for txn in result.cascade_result.transactions
        if txn.status is TransactionStatus.COMMITTED
    ]
    assert len(committed) == 1
    (txn,) = committed
    assert txn.provenance is not None
    assert txn.provenance.origin is OriginKind.DEVELOPER
    assert txn.provenance.producer_id == DEVTOOLS_DEVELOPER_PRODUCER
    (committed_effect,) = txn.effects
    assert committed_effect.effect.source == DEVTOOLS_DEVELOPER_PRODUCER


def test_pause_step_runtime_directive_no_state_change() -> None:
    """t8：2 指令面（pause/step）+ state dump 不变（零级联）。"""
    world = make_p8_world()
    executor = make_p8_executor()
    world_dump = world.model_dump(mode="json")
    for tick, (kind, record_id) in enumerate(
        (("pause", _RECORD_PAUSE_ID), ("step", _RECORD_STEP_ID)), start=1
    ):
        command = DevelopmentCommand(
            command_id=f"dev-{kind}-1", kind=kind, payload={}
        )
        result = apply_development_command(
            command,
            world_state=world,
            executor=executor,
            logical_tick=tick,
            intervention_record_id=record_id,
        )
        assert result.changed is False
        assert result.runtime_directive == (kind,)
        assert result.cascade_result is None
        assert result.world_state is world
        assert result.world_state.model_dump(mode="json") == world_dump
        assert len(result.trace_records) == 1
        assert result.trace_records[0].kind is TraceKind.DEV_INTERVENTION


def test_force_wake_directive_surface() -> None:
    """t9：指令含 entity_id；缺 key → ``usage_error``。"""
    world = make_p8_world()
    executor = make_p8_executor()
    command = DevelopmentCommand(
        command_id="dev-fw-1", kind="force_wake", payload={"entity_id": "ent_a"}
    )
    result = apply_development_command(
        command,
        world_state=world,
        executor=executor,
        logical_tick=1,
        intervention_record_id=_RECORD_FW_ID,
    )
    assert result.changed is False
    assert result.runtime_directive == ("force_wake", "ent_a")
    assert result.cascade_result is None
    # 缺 key → usage_error
    command_bad = DevelopmentCommand(
        command_id="dev-fw-2", kind="force_wake", payload={}
    )
    with pytest.raises(InterventionError) as excinfo:
        apply_development_command(
            command_bad,
            world_state=world,
            executor=executor,
            logical_tick=1,
            intervention_record_id=_RECORD_FW_BAD_ID,
        )
    assert excinfo.value.code == "usage_error"


def test_branch_command_instance_level() -> None:
    """t10：``branch`` kind——无世界变更 + ``("branch",)`` 指令（DEV-P8-3）。"""
    world = make_p8_world()
    executor = make_p8_executor()
    command = DevelopmentCommand(
        command_id="dev-branch-1", kind="branch", payload={}
    )
    result = apply_development_command(
        command,
        world_state=world,
        executor=executor,
        logical_tick=1,
        intervention_record_id=_RECORD_BRANCH_ID,
    )
    assert result.changed is False
    assert result.runtime_directive == ("branch",)
    assert result.cascade_result is None
    assert result.world_state is world
    assert len(result.trace_records) == 1
    assert result.trace_records[0].kind is TraceKind.DEV_INTERVENTION


def test_result_to_dict_json_clean() -> None:
    """t11：4 族 ``InterventionResult.to_dict`` clean。"""
    world = make_p8_world()
    executor = make_p8_executor()
    results = {
        "pause": apply_development_command(
            DevelopmentCommand(command_id="dev-pause-1", kind="pause", payload={}),
            world_state=world,
            executor=executor,
            logical_tick=1,
            intervention_record_id=_RECORD_T11_PAUSE_ID,
        ),
        "branch": apply_development_command(
            DevelopmentCommand(command_id="dev-branch-1", kind="branch", payload={}),
            world_state=world,
            executor=executor,
            logical_tick=2,
            intervention_record_id=_RECORD_T11_BRANCH_ID,
        ),
        "patch": apply_development_command(
            _patch_command(),
            world_state=world,
            executor=executor,
            logical_tick=3,
            intervention_record_id=_RECORD_T11_PATCH_ID,
        ),
        "inject": apply_development_command(
            DevelopmentCommand(
                command_id="dev-inject-1",
                kind="inject_event",
                payload={
                    "effect_id": "eff_p8_dev_inject_1",
                    "effect_type": "core.set_world_variable",
                    "target_kind": "state_domain",
                    "domain": "world_variables",
                    "payload": {"key": "score", "value": 2},
                },
            ),
            world_state=world,
            executor=executor,
            logical_tick=4,
            intervention_record_id=_RECORD_T11_INJECT_ID,
        ),
    }
    for family, result in results.items():
        dumped = result.to_dict()
        assert_json_clean(dumped)
        assert set(dumped) == {
            "world_state",
            "changed",
            "runtime_directive",
            "cascade_result",
            "trace_records",
        }, family
    assert results["pause"].to_dict()["cascade_result"] is None
    assert results["branch"].to_dict()["cascade_result"] is None
    assert results["patch"].to_dict()["cascade_result"] is not None
    assert results["inject"].to_dict()["cascade_result"] is not None


def test_producer_id_fullmatch_pattern() -> None:
    """t12：``DEVTOOLS_DEVELOPER_PRODUCER`` fullmatch 冻结 pattern。"""
    assert re.fullmatch(PRODUCER_ID_PATTERN, DEVTOOLS_DEVELOPER_PRODUCER) is not None
