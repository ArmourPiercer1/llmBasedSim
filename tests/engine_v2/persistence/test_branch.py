"""P8 T05 branch_world 测试（SOT §6.1 t1–t13）。

钉死面（§6.1 表逐项对应）：

- t1 A5 深化：world_variable/组件 4 象限交叉修改；
- t2 **A22**：双向零别名（branch→source / source→branch）；
- t3 **A18**：project version 失配 → message 含 ``"project_compatibility"``；
- t4 module versions 共有键值冲突 → ``BranchError``；
- t5 坏 ``WorldState.schema_version`` → ``BranchError(version_mismatch)``；
- t6 A7 深化：默认拒绝 message 点名 backend_id + code 断言；
- t7 ``allow_degraded=True`` → ``degraded_backends`` 点名 + 无异常；
- t8 checkpointable ref 缺 payload → ``BranchError``；
- t9 checkpoint payload 非 dict → ``schema_invalid``；
- t10 ``BRANCH_CHECKS ==`` Spec §30.5 三元组（snake_case 归一）；
- t11 handle frozen + ``to_dict`` clean；
- t12 无 backend_refs → 成功、degraded 空；
- t13 ``new_world_instance_id`` 空/纯空白 → ``schema_invalid``。

纪律：扁平函数（零 class / 零 subprocess / 零跨函数状态）；确定性（D6：
全部字面量 id）；state 修改全部经正常提交管道 ``CascadeExecutor.run``
（K2 零状态直写，测试侧 policy 显式放行 ``devtools.developer``）。
"""

from __future__ import annotations

import dataclasses

import pytest

from src.engine_v2.core import (
    EFFECT_SET_COMPONENT,
    EFFECT_SET_WORLD_VARIABLE,
    BackendStateRef,
    ComponentTypeId,
    EntityId,
    EntityTarget,
    EffectId,
    OriginKind,
    ProducerId,
    ProposedEffect,
    Provenance,
    StateDomainId,
    StateDomainTarget,
    WorldState,
    assert_json_clean,
)
from src.engine_v2.persistence.branch import (
    BRANCH_CHECKS,
    BranchError,
    BranchResult,
    WorldInstanceHandle,
    branch_world,
)
from src.engine_v2.persistence.checkpoint import BackendCheckpointRegistry
from tests.engine_v2.persistence.conftest import (
    make_p8_executor,
    make_p8_runtime,
    make_p8_world,
)

_WSI_SOURCE = "wsi_p8_sc1"


def _sc1_handle() -> WorldInstanceHandle:
    """SC-1 源 handle（无 backend_refs——检查 1 空面）。"""
    return WorldInstanceHandle(_WSI_SOURCE, make_p8_world(), make_p8_runtime())


def _empty_registry() -> BackendCheckpointRegistry:
    """空注册表（零 IO；``validate_refs`` 报告面）。"""
    return BackendCheckpointRegistry()


def _sc3_handle() -> WorldInstanceHandle:
    """SC-3 源 handle（G8-4 负样本：一条 non-checkpointable ref）。"""
    ref = BackendStateRef(
        backend_id="rigid_body",
        backend_kind="dynamics",
        checkpointable=False,
    )
    return WorldInstanceHandle(
        _WSI_SOURCE, make_p8_world(), make_p8_runtime(backend_refs=(ref,))
    )


def _sc_checkpointable_handle() -> WorldInstanceHandle:
    """checkpointable=True ref 源 handle（检查 1 payload 面）。"""
    ref = BackendStateRef(
        backend_id="rigid_body",
        backend_kind="dynamics",
        checkpointable=True,
    )
    return WorldInstanceHandle(
        _WSI_SOURCE, make_p8_world(), make_p8_runtime(backend_refs=(ref,))
    )


def _mutate_world_variable(
    state: WorldState,
    executor,
    value: int,
) -> WorldState:
    """world_variable 象限修改（正常提交管道，K2 零直写）。"""
    effect = ProposedEffect(
        effect_id=EffectId("eff_p8_branch_wv"),
        effect_type=EFFECT_SET_WORLD_VARIABLE,
        source=ProducerId("devtools.developer"),
        target=StateDomainTarget(domain=StateDomainId("world_variables")),
        payload={"key": "score", "value": value},
        base_revision=state.world_revision,
    )
    result = executor.run(
        (effect,),
        state,
        causal_root_id="p8-branch-wv",
        origin=Provenance(
            producer_id=ProducerId("devtools.developer"), origin=OriginKind.DEVELOPER
        ),
    )
    return result.final_state


def _mutate_component(
    state: WorldState,
    executor,
    entity_id: str,
) -> WorldState:
    """组件象限修改（正常提交管道，K2 零直写；``marker`` 描述型 schema）。"""
    effect = ProposedEffect(
        effect_id=EffectId("eff_p8_branch_comp"),
        effect_type=EFFECT_SET_COMPONENT,
        source=ProducerId("devtools.developer"),
        target=EntityTarget(
            entity_id=EntityId(entity_id),
            component_type=ComponentTypeId("marker"),
        ),
        payload={"tag": "p8_branch"},
        base_revision=state.world_revision,
    )
    result = executor.run(
        (effect,),
        state,
        causal_root_id="p8-branch-comp",
        origin=Provenance(
            producer_id=ProducerId("devtools.developer"), origin=OriginKind.DEVELOPER
        ),
    )
    return result.final_state


def test_branch_independence_matrix() -> None:
    """t1（A5 深化）：world_variable/组件 4 象限交叉修改。

    SC-1 源 branch A/B → 4 象限（A.world_variable / A.component /
    B.world_variable / B.component）各经正常提交管道修改——每象限修改后
    对方与源的 state dump 不变。
    """
    source = _sc1_handle()
    registry = _empty_registry()
    branch_a = branch_world(
        source, new_world_instance_id="wsi_p8_branch_a", registry=registry
    )
    branch_b = branch_world(
        source, new_world_instance_id="wsi_p8_branch_b", registry=registry
    )
    executor = make_p8_executor()
    source_dump = source.world_state.model_dump(mode="json")
    a_dump = branch_a.handle.world_state.model_dump(mode="json")
    b_dump = branch_b.handle.world_state.model_dump(mode="json")

    # —— Q1：A 的 world_variable ——
    a1 = _mutate_world_variable(branch_a.handle.world_state, executor, 7)
    assert a1.world_variables["score"] == 7
    assert a1.model_dump(mode="json") != a_dump
    assert branch_b.handle.world_state.model_dump(mode="json") == b_dump
    assert source.world_state.model_dump(mode="json") == source_dump

    # —— Q2：A 的组件（ent_a）——
    a2 = _mutate_component(a1, executor, "ent_a")
    assert a2.entities[EntityId("ent_a")].components["marker"] == {"tag": "p8_branch"}
    a2_dump = a2.model_dump(mode="json")
    assert branch_b.handle.world_state.model_dump(mode="json") == b_dump
    assert source.world_state.model_dump(mode="json") == source_dump

    # —— Q3：B 的 world_variable ——
    b1 = _mutate_world_variable(branch_b.handle.world_state, executor, 9)
    assert b1.world_variables["score"] == 9
    assert a2.model_dump(mode="json") == a2_dump
    assert source.world_state.model_dump(mode="json") == source_dump

    # —— Q4：B 的组件（ent_b）——
    b2 = _mutate_component(b1, executor, "ent_b")
    assert b2.entities[EntityId("ent_b")].components["marker"] == {"tag": "p8_branch"}
    assert a2.model_dump(mode="json") == a2_dump
    assert source.world_state.model_dump(mode="json") == source_dump


def test_branch_zero_alias_bidirectional() -> None:
    """t2（**A22**）：双向零别名（branch→source / source→branch）。

    branch 产物与源零别名（对象身份断言）；改 branch 侧 → 源 dump 不变；
    改源侧 → branch dump 不变。
    """
    source = _sc1_handle()
    branch_b = branch_world(
        source, new_world_instance_id="wsi_p8_branch_b", registry=_empty_registry()
    )
    assert branch_b.handle.world_instance_id == "wsi_p8_branch_b"
    # 零别名：容器身份不共享
    assert branch_b.handle.world_state is not source.world_state
    assert branch_b.handle.runtime_state is not source.runtime_state
    assert branch_b.handle.world_state.entities is not source.world_state.entities
    assert (
        branch_b.handle.world_state.world_variables
        is not source.world_state.world_variables
    )
    executor = make_p8_executor()
    source_dump = source.world_state.model_dump(mode="json")
    b_dump = branch_b.handle.world_state.model_dump(mode="json")

    # branch→source 方向（A22）：改 branch 侧，源不变
    b1 = _mutate_world_variable(branch_b.handle.world_state, executor, 5)
    assert b1.world_variables["score"] == 5
    assert source.world_state.model_dump(mode="json") == source_dump

    # source→branch 方向：改源侧，branch 不变
    s1 = _mutate_world_variable(source.world_state, executor, 6)
    assert s1.world_variables["score"] == 6
    assert branch_b.handle.world_state.model_dump(mode="json") == b_dump


def test_branch_project_compat_mismatch() -> None:
    """t3（**A18**）：project version 双方均给且不等 → ``BranchError``，
    message 含 ``"project_compatibility"``。"""
    with pytest.raises(BranchError) as excinfo:
        branch_world(
            _sc1_handle(),
            new_world_instance_id="wsi_p8_branch_c",
            registry=_empty_registry(),
            source_project_version="1.0",
            target_project_version="2.0",
        )
    assert excinfo.value.code == "branch_rejected"
    assert "project_compatibility" in str(excinfo.value)


def test_branch_module_version_conflict() -> None:
    """t4：module versions 共有键值冲突 → ``BranchError``；同值不拒。"""
    with pytest.raises(BranchError) as excinfo:
        branch_world(
            _sc1_handle(),
            new_world_instance_id="wsi_p8_branch_d",
            registry=_empty_registry(),
            source_module_versions={"core": "84a5d4f"},
            target_module_versions={"core": "999"},
        )
    assert excinfo.value.code == "branch_rejected"
    assert "project_compatibility" in str(excinfo.value)
    # 共有键同值 → 通过
    result = branch_world(
        _sc1_handle(),
        new_world_instance_id="wsi_p8_branch_d",
        registry=_empty_registry(),
        source_module_versions={"core": "84a5d4f"},
        target_module_versions={"core": "84a5d4f"},
    )
    assert result.handle.world_instance_id == "wsi_p8_branch_d"


def test_branch_version_check_failure() -> None:
    """t5：构造坏 ``WorldState.schema_version`` → ``version_mismatch``。"""
    bad_world = _tampered_schema_world()
    source = WorldInstanceHandle(_WSI_SOURCE, bad_world, make_p8_runtime())
    with pytest.raises(BranchError) as excinfo:
        branch_world(
            source, new_world_instance_id="wsi_p8_branch_v", registry=_empty_registry()
        )
    assert excinfo.value.code == "version_mismatch"


def _tampered_schema_world() -> WorldState:
    """坏 ``schema_version`` 世界（999 ≠ 当前契约代；检查 2 门禁消费）。"""
    world = make_p8_world()
    return world.model_copy(update={"schema_version": 999})


def test_branch_default_reject_message_naming_backend() -> None:
    """t6（A7 深化）：SC-3 默认拒绝——message 点名 backend_id + code 断言。"""
    with pytest.raises(BranchError) as excinfo:
        branch_world(
            _sc3_handle(),
            new_world_instance_id="wsi_p8_branch_e",
            registry=_empty_registry(),
        )
    assert excinfo.value.code == "branch_rejected"
    assert "rigid_body" in str(excinfo.value)


def test_branch_degraded_opt_in_records() -> None:
    """t7：``allow_degraded=True`` → ``degraded_backends`` 点名 + 无异常。"""
    result = branch_world(
        _sc3_handle(),
        new_world_instance_id="wsi_p8_branch_f",
        registry=_empty_registry(),
        allow_degraded=True,
    )
    assert result.degraded_backends == ("rigid_body",)
    assert result.handle.world_instance_id == "wsi_p8_branch_f"
    assert all(row["ok"] is True for row in result.checks)


def test_branch_checkpoint_payload_required() -> None:
    """t8：checkpointable ref 缺 checkpoint payload → ``BranchError``。"""
    with pytest.raises(BranchError) as excinfo:
        branch_world(
            _sc_checkpointable_handle(),
            new_world_instance_id="wsi_p8_branch_g",
            registry=_empty_registry(),
        )
    assert excinfo.value.code == "branch_rejected"
    assert "rigid_body" in str(excinfo.value)


def test_branch_checkpoint_payload_non_dict_rejected() -> None:
    """t9：checkpoint payload 非 dict → ``schema_invalid``。"""
    with pytest.raises(BranchError) as excinfo:
        branch_world(
            _sc_checkpointable_handle(),
            new_world_instance_id="wsi_p8_branch_h",
            registry=_empty_registry(),
            checkpoints={"rigid_body": "not-a-dict"},
        )
    assert excinfo.value.code == "schema_invalid"
    assert "rigid_body" in str(excinfo.value)


def test_branch_checks_closed_set() -> None:
    """t10：``BRANCH_CHECKS ==`` Spec §30.5 三元组（snake_case 归一）+
    结果行名机械链接。"""
    assert BRANCH_CHECKS == (
        "backend_checkpoint_support",
        "runtime_snapshot_availability",
        "project_compatibility",
    )
    result = branch_world(
        _sc1_handle(),
        new_world_instance_id="wsi_p8_branch_i",
        registry=_empty_registry(),
    )
    assert tuple(row["check"] for row in result.checks) == BRANCH_CHECKS
    assert all(row["ok"] is True for row in result.checks)
    assert all(set(row) == {"check", "ok", "detail"} for row in result.checks)


def test_handle_frozen_and_json_clean() -> None:
    """t11：handle frozen + ``to_dict`` clean（含 ``BranchResult.to_dict``）。"""
    handle = _sc1_handle()
    with pytest.raises(dataclasses.FrozenInstanceError):
        handle.world_instance_id = "wsi_other"  # type: ignore[misc]
    dumped = handle.to_dict()
    assert_json_clean(dumped)
    assert set(dumped) == {"world_instance_id", "world_state", "runtime_state"}
    assert dumped["world_instance_id"] == _WSI_SOURCE

    result = branch_world(
        handle, new_world_instance_id="wsi_p8_branch_j", registry=_empty_registry()
    )
    assert isinstance(result, BranchResult)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.degraded_backends = ("x",)  # type: ignore[misc]
    result_dump = result.to_dict()
    assert_json_clean(result_dump)
    assert set(result_dump) == {"handle", "degraded_backends", "checks"}
    assert result_dump["degraded_backends"] == []


def test_branch_empty_backend_refs_ok() -> None:
    """t12：无 backend_refs → 成功、degraded 空、revision 不 bump。"""
    result = branch_world(
        _sc1_handle(),
        new_world_instance_id="wsi_p8_branch_k",
        registry=_empty_registry(),
    )
    assert result.degraded_backends == ()
    assert result.handle.world_instance_id == "wsi_p8_branch_k"
    assert result.handle.world_state.world_revision == 0
    assert all(row["ok"] is True for row in result.checks)


def test_branch_new_id_validation() -> None:
    """t13：``new_world_instance_id`` 空/纯空白 → ``schema_invalid``。"""
    for bad_id in ("", "   "):
        with pytest.raises(BranchError) as excinfo:
            branch_world(
                _sc1_handle(),
                new_world_instance_id=bad_id,
                registry=_empty_registry(),
            )
        assert excinfo.value.code == "schema_invalid"
