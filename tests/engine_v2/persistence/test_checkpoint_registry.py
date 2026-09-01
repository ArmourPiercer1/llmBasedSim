"""P8 T04 BackendCheckpointRegistry 测试（SOT §6.1 t1–t11）。

钉死面（§6.1 表逐项对应）：

- t1 绑定面 + 重复拒绝前置；
- t2 2 backend（toy + stub non-checkpointable）→ 2 快照；后者
  ``checkpoint is None``（降级可见）；
- t3 toy 体 ``{"version": 1, "seed": N}`` JSON-clean；
- t4 restore → 新实例（``is not`` 原实例）；
- t5 未知 id → ``checkpoint_unavailable``；
- t6 坏类型体 → ``CheckpointError``（形态 → ``schema_invalid``；版本失配 →
  ``version_mismatch``）；
- t7 一致 → 空 issues；
- t8 未知 ref → 非空；
- t9 声明漂移 → 非空；
- t10 重复 id → ``CheckpointError``；
- t11 声明/能力不符 → ``schema_invalid``。

纪律：扁平函数（零 class / 零 subprocess / 零跨函数状态，P7 §6.1 同族）；
确定性（D6：注册序 = 快照序）。
"""

from __future__ import annotations

import pytest

from src.engine_v2.core import BackendStateRef, assert_json_clean
from src.engine_v2.dynamics.backend import BackendMetadata
from src.engine_v2.dynamics.toy_rigid import ToyRigidDynamics
from src.engine_v2.persistence.checkpoint import (
    BackendCheckpointRegistry,
    CheckpointError,
    CheckpointSnapshot,
)

_TOY_SEED = 7


def _stub_metadata(
    *,
    backend_id: str,
    checkpointable: bool = False,
    restorable: bool = False,
    replayable: bool = False,
) -> BackendMetadata:
    """测试侧 ``BackendMetadata`` 字面量（全闭集词法面合法）。"""
    return BackendMetadata(
        backend_id=backend_id,
        producer_id=f"{backend_id}.producer",
        domains=(),
        determinism="deterministic",
        implementation_type="rule",
        fidelity="abstract",
        checkpointable=checkpointable,
        restorable=restorable,
        replayable=replayable,
    )


class _PlainBackend:
    """stub backend：无 ``checkpoint`` / ``restore`` 能力（non-checkpointable
    注册面；降级可见的钉死对象）。"""


class _CheckpointOnlyBackend:
    """stub backend：仅 ``checkpoint``（``restorable=False`` 注册面）。"""

    def checkpoint(self) -> dict[str, object]:
        return {"version": 1, "stub": "ok"}


def test_register_and_metadata_binding() -> None:
    """t1：绑定面（``backend_id → (metadata, instance)``）+ 快照镜像声明。"""
    registry = BackendCheckpointRegistry()
    metadata = _stub_metadata(backend_id="stub_one", checkpointable=True)
    registry.register(
        backend_id="stub_one",
        metadata=metadata,
        instance=_CheckpointOnlyBackend(),
    )
    (snapshot,) = registry.checkpoint_all()
    assert snapshot.backend_id == "stub_one"
    assert snapshot.checkpointable is True
    assert snapshot.restorable is False
    assert snapshot.replayable is False
    assert snapshot.checkpoint == {"version": 1, "stub": "ok"}


def test_checkpoint_all_returns_snapshots() -> None:
    """t2：2 backend（toy + stub non-checkpointable）→ 2 快照（注册序）。

    后者 ``checkpoint is None``（降级可见——非静默丢弃）；``to_dict`` 面可辨。
    """
    registry = BackendCheckpointRegistry()
    registry.register(
        backend_id="rigid_body",
        metadata=_stub_metadata(
            backend_id="rigid_body",
            checkpointable=True,
            restorable=True,
            replayable=True,
        ),
        instance=ToyRigidDynamics(seed=_TOY_SEED),
    )
    registry.register(
        backend_id="plain",
        metadata=_stub_metadata(backend_id="plain"),
        instance=_PlainBackend(),
    )
    snapshots = registry.checkpoint_all()
    assert [s.backend_id for s in snapshots] == ["rigid_body", "plain"]
    assert all(isinstance(s, CheckpointSnapshot) for s in snapshots)
    assert snapshots[0].checkpoint is not None
    assert snapshots[1].checkpoint is None
    assert snapshots[1].checkpointable is False
    # 降级面 to_dict 可辨（None 显式存在，非键缺失）
    assert snapshots[1].to_dict()["checkpoint"] is None
    assert_json_clean(snapshots[1].to_dict())


def test_checkpoint_all_payload_json_clean() -> None:
    """t3：toy 体 ``{"version": 1, "seed": N}`` JSON-clean（D3 断言面）。"""
    registry = BackendCheckpointRegistry()
    registry.register(
        backend_id="rigid_body",
        metadata=_stub_metadata(
            backend_id="rigid_body", checkpointable=True, restorable=True
        ),
        instance=ToyRigidDynamics(seed=_TOY_SEED),
    )
    (snapshot,) = registry.checkpoint_all()
    assert snapshot.checkpoint == {"version": 1, "seed": _TOY_SEED}
    payload = snapshot.to_dict()
    assert payload["checkpoint"] == {"version": 1, "seed": _TOY_SEED}
    assert_json_clean(payload)


def test_restore_delegates_and_returns_new_instance() -> None:
    """t4：restore 委派实例侧，返回**新实例**（toy 模式，零就地变更）。"""
    registry = BackendCheckpointRegistry()
    original = ToyRigidDynamics(seed=_TOY_SEED)
    registry.register(
        backend_id="rigid_body",
        metadata=_stub_metadata(
            backend_id="rigid_body", checkpointable=True, restorable=True
        ),
        instance=original,
    )
    restored = registry.restore(
        backend_id="rigid_body", checkpoint={"version": 1, "seed": _TOY_SEED}
    )
    assert restored is not original
    assert restored.checkpoint() == {"version": 1, "seed": _TOY_SEED}


def test_restore_unknown_backend_raises() -> None:
    """t5：未知 id → ``CheckpointError``（默认码 ``checkpoint_unavailable``）。"""
    registry = BackendCheckpointRegistry()
    with pytest.raises(CheckpointError) as excinfo:
        registry.restore(backend_id="ghost", checkpoint={"version": 1, "seed": 7})
    assert excinfo.value.code == "checkpoint_unavailable"
    assert "ghost" in str(excinfo.value)


def test_restore_corrupt_payload_raises() -> None:
    """t6：坏体 → ``CheckpointError``（形态类 → ``schema_invalid``；版本
    失配 → ``version_mismatch``）。"""
    registry = BackendCheckpointRegistry()
    registry.register(
        backend_id="rigid_body",
        metadata=_stub_metadata(
            backend_id="rigid_body", checkpointable=True, restorable=True
        ),
        instance=ToyRigidDynamics(seed=_TOY_SEED),
    )
    # 形态坏：seed 非 int（实例侧"必须为 int"门）
    with pytest.raises(CheckpointError) as excinfo:
        registry.restore(
            backend_id="rigid_body", checkpoint={"version": 1, "seed": "corrupt"}
        )
    assert excinfo.value.code == "schema_invalid"
    # 版本失配：version != 1（实例侧版本门）
    with pytest.raises(CheckpointError) as excinfo:
        registry.restore(
            backend_id="rigid_body", checkpoint={"version": 99, "seed": 7}
        )
    assert excinfo.value.code == "version_mismatch"


def test_validate_refs_consistent() -> None:
    """t7：ref 面与注册面一致 → 空 issues（报告面）。"""
    registry = BackendCheckpointRegistry()
    registry.register(
        backend_id="rigid_body",
        metadata=_stub_metadata(
            backend_id="rigid_body",
            checkpointable=True,
            restorable=True,
            replayable=True,
        ),
        instance=ToyRigidDynamics(seed=_TOY_SEED),
    )
    refs = (
        BackendStateRef(
            backend_id="rigid_body",
            backend_kind="toy",
            checkpointable=True,
            restorable=True,
            replayable=True,
        ),
    )
    assert registry.validate_refs(refs) == ()


def test_validate_refs_unknown_ref_reported() -> None:
    """t8：ref 的 backend_id 未注册 → 非空 issues（ref 悬空显式）。"""
    registry = BackendCheckpointRegistry()
    refs = (BackendStateRef(backend_id="ghost", backend_kind="toy"),)
    issues = registry.validate_refs(refs)
    assert len(issues) == 1
    assert "ghost" in issues[0]


def test_validate_refs_capability_mismatch_reported() -> None:
    """t9：ref ``checkpointable=True`` 而注册项 non-checkpointable → 非空
    issues（声明漂移显式）。"""
    registry = BackendCheckpointRegistry()
    registry.register(
        backend_id="plain",
        metadata=_stub_metadata(backend_id="plain"),
        instance=_PlainBackend(),
    )
    refs = (
        BackendStateRef(
            backend_id="plain", backend_kind="stub", checkpointable=True
        ),
    )
    issues = registry.validate_refs(refs)
    assert len(issues) == 1
    assert "plain" in issues[0]
    assert "checkpointable" in issues[0]


def test_register_duplicate_rejected() -> None:
    """t10：重复 id → ``CheckpointError``（默认码 ``checkpoint_unavailable``）。"""
    registry = BackendCheckpointRegistry()
    metadata = _stub_metadata(backend_id="dup_one")
    registry.register(
        backend_id="dup_one", metadata=metadata, instance=_PlainBackend()
    )
    with pytest.raises(CheckpointError) as excinfo:
        registry.register(
            backend_id="dup_one", metadata=metadata, instance=_PlainBackend()
        )
    assert excinfo.value.code == "checkpoint_unavailable"
    assert "dup_one" in str(excinfo.value)


def test_register_capability_inconsistency_rejected() -> None:
    """t11：声明/能力不符 → ``CheckpointError(schema_invalid)``（一致性门）。"""
    registry = BackendCheckpointRegistry()
    # checkpointable=True 而 instance 无 checkpoint 可调用
    with pytest.raises(CheckpointError) as excinfo:
        registry.register(
            backend_id="broken_cp",
            metadata=_stub_metadata(backend_id="broken_cp", checkpointable=True),
            instance=_PlainBackend(),
        )
    assert excinfo.value.code == "schema_invalid"
    # restorable=True 而 instance 无 restore 可调用
    with pytest.raises(CheckpointError) as excinfo:
        registry.register(
            backend_id="broken_rs",
            metadata=_stub_metadata(backend_id="broken_rs", restorable=True),
            instance=_PlainBackend(),
        )
    assert excinfo.value.code == "schema_invalid"
