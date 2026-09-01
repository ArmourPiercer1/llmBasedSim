"""P8 T01 契约测试：``persistence/snapshot.py``（P8 信封格式面；SOT §6.1 t1–t12）。

全部用例 = 模块级扁平函数（零 class / 零 subprocess / 零跨函数状态，P7
§6.1 同族纪律）；世界 / 运行时 / 版本串 / wall time 全部 host 侧字面量
（§6.4：零随机、零时钟，D5/D6）。构件经 ``tests.engine_v2.persistence.conftest``
冻结缝导入（§2.7）。
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.engine_v2.core import Snapshot, assert_json_clean
from src.engine_v2.persistence.base import (
    P8_ERROR_CODES,
    PERSISTENCE_FORMAT_VERSION,
    PersistenceError,
)
from src.engine_v2.persistence.snapshot import (
    PersistenceSnapshot,
    check_persistence_versions,
    dump_persistence_snapshot,
    load_persistence_snapshot,
    to_persistence_snapshot,
)
from tests.engine_v2.persistence.conftest import make_p8_runtime, make_p8_world

_WS_T1 = "wsi_p8_snap_t1"
_WALL_T1 = "1970-01-01T00:00:00+00:00"
_PROJ_T1 = "1.0.0"
_MODS_T1 = {"core": "84a5d4f"}


def _make_core_snapshot(
    *,
    project_version: str | None = None,
    module_versions: dict[str, str] | None = None,
) -> Snapshot:
    """host 字面量 core ``Snapshot``（SC-1 同族世界 / 运行时）。"""
    return Snapshot(
        world_state=make_p8_world(),
        runtime_state=make_p8_runtime(),
        world_instance_id=_WS_T1,
        created_logical_tick=3,
        project_version=project_version,
        module_versions=dict(module_versions) if module_versions is not None else {},
    )


def _full_envelope() -> PersistenceSnapshot:
    """全量面信封（镜像 / ref / wall time 均给定；roundtrip 用例共享形状）。"""
    return to_persistence_snapshot(
        _make_core_snapshot(project_version=_PROJ_T1, module_versions=_MODS_T1),
        backend_checkpoints={"rigid_body": "checkpoints/rigid_body.json"},
        trace_ref="trace.jsonl",
        created_wall_time=_WALL_T1,
    )


def test_envelope_defaults_version_surface() -> None:
    """t1：默认值面（版本 == 1 / ``backend_checkpoints=={}`` / ``trace_ref is None``）。"""
    env = to_persistence_snapshot(_make_core_snapshot())
    assert env.persistence_format_version == PERSISTENCE_FORMAT_VERSION == 1
    assert env.backend_checkpoints == {}
    assert env.trace_ref is None
    assert env.created_wall_time is None
    # 冗余镜像默认 = 嵌套默认（None / {}）
    assert env.project_version is None
    assert env.module_versions == {}


def test_envelope_redundant_versions_match_nested() -> None:
    """t2：冗余镜像一致性正样本（镜像 == 嵌套 → 构造通过）。"""
    snap = _make_core_snapshot(project_version=_PROJ_T1, module_versions=_MODS_T1)
    env = to_persistence_snapshot(snap)
    assert env.project_version == snap.project_version == _PROJ_T1
    assert env.module_versions == snap.module_versions == _MODS_T1
    # 显式构造同形正样本：validator 通过且与纯函数产出相等
    explicit = PersistenceSnapshot(
        snapshot=snap, project_version=_PROJ_T1, module_versions=_MODS_T1
    )
    assert explicit == env


def test_envelope_redundant_versions_mismatch_raises() -> None:
    """t3：镜像失配 → ``schema_invalid``（P8-INV-10）。"""
    snap = _make_core_snapshot(project_version=_PROJ_T1, module_versions=_MODS_T1)
    with pytest.raises(PersistenceError) as exc_proj:
        PersistenceSnapshot(
            snapshot=snap, project_version="2.0.0", module_versions=_MODS_T1
        )
    assert exc_proj.value.code == "schema_invalid"
    with pytest.raises(PersistenceError) as exc_mods:
        PersistenceSnapshot(
            snapshot=snap, project_version=_PROJ_T1, module_versions={"core": "999"}
        )
    assert exc_mods.value.code == "schema_invalid"


def test_dump_load_roundtrip_json_clean() -> None:
    """t4：dump/load roundtrip 相等 + JSON-clean（D3）。"""
    env = _full_envelope()
    text = dump_persistence_snapshot(env)
    assert isinstance(text, str)
    assert_json_clean(json.loads(text))
    assert load_persistence_snapshot(text) == env
    # bytes 入参同面
    assert load_persistence_snapshot(text.encode("utf-8")) == env


def test_load_unknown_field_rejected() -> None:
    """t5：extra 字段 → ``schema_invalid``（``extra="forbid"``）。"""
    env = _full_envelope()
    d = json.loads(dump_persistence_snapshot(env))
    d["not_a_field"] = 1
    text = json.dumps(d, ensure_ascii=False, sort_keys=True)
    with pytest.raises(PersistenceError) as exc_info:
        load_persistence_snapshot(text)
    assert exc_info.value.code == "schema_invalid"


def test_load_version_zero_rejected() -> None:
    """t6：``persistence_format_version=0`` → ``version_mismatch``。"""
    env = _full_envelope()
    d = json.loads(dump_persistence_snapshot(env))
    d["persistence_format_version"] = 0
    text = json.dumps(d, ensure_ascii=False, sort_keys=True)
    with pytest.raises(PersistenceError) as exc_info:
        load_persistence_snapshot(text)
    assert exc_info.value.code == "version_mismatch"


def test_check_persistence_versions_consistent() -> None:
    """t7：好信封 → 空元组（报告面只报不处置）。"""
    assert check_persistence_versions(_full_envelope()) == ()


def test_check_persistence_versions_reports_nested_mismatch() -> None:
    """t8：嵌套版本篡改 → 非空 issues（经冻结 ``check_snapshot_versions``）。

    嵌套 ``contract_schema_version=999`` 而顶层镜像仍 == 嵌套（validator
    构造通过）——报告面必须捕获 core 层失配。
    """
    snap = _make_core_snapshot()
    tampered = snap.model_copy(update={"contract_schema_version": 999})
    env = to_persistence_snapshot(tampered)
    issues = check_persistence_versions(env)
    assert issues
    assert any("contract_schema_version" in issue for issue in issues)


def test_to_persistence_snapshot_zero_alias() -> None:
    """t9：输入 ``Snapshot`` 后置修改不影响信封（零别名，D15）。"""
    snap = _make_core_snapshot()
    env = to_persistence_snapshot(snap)
    # 后置修改：输入侧世界变量 dict 原地篡改（P8 缝：信封不得别名输入侧）
    snap.world_state.world_variables["score"] = 999
    assert env.snapshot.world_state.world_variables["score"] == 0
    assert env.snapshot.world_state.world_variables is not snap.world_state.world_variables
    # 嵌套 model 对象亦不共享（deep_copy_via_roundtrip 固化）
    assert env.snapshot.world_state is not snap.world_state
    assert env.snapshot is not snap


def test_envelope_frozen() -> None:
    """t10：改字段 → 异常（``ContractModel`` frozen）。"""
    env = _full_envelope()
    with pytest.raises(ValidationError):
        env.trace_ref = "rogue.jsonl"
    with pytest.raises(ValidationError):
        env.persistence_format_version = 2


def test_backend_checkpoints_map_surface() -> None:
    """t11：非空 map：JSON-clean + ref 相对路径面 + roundtrip 保面。"""
    env = _full_envelope()
    assert env.backend_checkpoints == {"rigid_body": "checkpoints/rigid_body.json"}
    for ref in env.backend_checkpoints.values():
        assert not ref.startswith("/")
        assert "\\" not in ref
    assert_json_clean(env.to_dict())
    loaded = load_persistence_snapshot(dump_persistence_snapshot(env))
    assert loaded.backend_checkpoints == env.backend_checkpoints


def test_persistence_format_version_closed() -> None:
    """t12：``PERSISTENCE_FORMAT_VERSION == 1`` + 11 码闭集 == 字面量（§3.1）。"""
    assert PERSISTENCE_FORMAT_VERSION == 1
    assert P8_ERROR_CODES == (
        "save_not_found",
        "corrupt_file",
        "schema_invalid",
        "version_mismatch",
        "layout_violation",
        "checkpoint_unavailable",
        "replay_mismatch",
        "branch_rejected",
        "intervention_rejected",
        "usage_error",
        "internal_error",
    )
