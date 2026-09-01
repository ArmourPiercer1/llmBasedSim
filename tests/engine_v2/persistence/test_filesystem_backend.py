"""P8 T02 契约测试：``persistence/filesystem.py``（filesystem 后端；SOT §6.1 t1–t14）。

全部用例 = 模块级扁平函数（零 class / 零 subprocess / 零跨函数状态，P7
§6.1 同族纪律）；save 构建经 conftest 冻结缝（SC-1 脚本 run / 信封），
字节级破坏经 ``corrupt_save``（SC-4 6 kind 闭集，W5 AD 族同源）；
id / wall time / 版本串全部 host 侧字面量（§6.4：零随机、零时钟，D5/D6）。
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from src.engine_v2.core import (
    Snapshot,
    TraceKind,
    TraceRecord,
    TraceRecordId,
)
from src.engine_v2.persistence.base import (
    PERSISTENCE_SAVE_FILES,
    PersistenceBackend,
    PersistenceError,
)
from src.engine_v2.persistence.filesystem import FilesystemPersistenceBackend
from src.engine_v2.persistence.snapshot import to_persistence_snapshot
from tests.engine_v2.persistence.conftest import (
    build_p8_envelope,
    build_p8_save,
    corrupt_save,
    make_p8_backend,
    make_p8_runtime,
    make_p8_world,
    run_p8_script,
)

_SAVE_ROOT = Path("saves_root") / "saves"
_WALL_T1 = "1970-01-01T00:00:00+00:00"
_WALL_T2 = "1970-01-01T00:00:01+00:00"


def _make_min_snapshot(wsi: str) -> Snapshot:
    """host 字面量 core ``Snapshot``（最小面；版本默认当前世代）。"""
    return Snapshot(
        world_state=make_p8_world(),
        runtime_state=make_p8_runtime(),
        world_instance_id=wsi,
        created_logical_tick=0,
    )


def _second_envelope(run_final_state: "object") -> "object":
    """同 save_id 二次 save 的可区分信封（wall time T2 + 独立 WSI）。"""
    return to_persistence_snapshot(
        Snapshot(
            world_state=run_final_state,
            runtime_state=make_p8_runtime(),
            world_instance_id="wsi_p8_fs_overwrite",
            created_logical_tick=3,
            project_version="1.0.0",
            module_versions={"core": "84a5d4f"},
        ),
        trace_ref="trace.jsonl",
        created_wall_time=_WALL_T2,
    )


def test_save_creates_closed_layout(tmp_path: Path) -> None:
    """t1：目录闭集（save 目录 == ``PERSISTENCE_SAVE_FILES``；index 在 base 层）。"""
    save_dir = build_p8_save(tmp_path, run_p8_script())
    assert {p.name for p in save_dir.iterdir()} == set(PERSISTENCE_SAVE_FILES)
    ckpt_dir = save_dir / "checkpoints"
    assert ckpt_dir.is_dir()
    assert list(ckpt_dir.iterdir()) == []
    # index 面：base 层 index.json 含 save 条目
    index_path = tmp_path / "saves_root" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["saves"]["save_p8_base"] == {"created_wall_time": _WALL_T1}


def test_save_load_roundtrip_bundle_equal(tmp_path: Path) -> None:
    """t2：``SaveBundle`` envelope / trace / checkpoint 面 roundtrip 相等。"""
    run = run_p8_script()
    build_p8_save(tmp_path, run)
    bundle = make_p8_backend(tmp_path).load(save_id="save_p8_base")
    assert bundle.save_id == "save_p8_base"
    assert bundle.envelope == build_p8_envelope(run)
    assert bundle.trace_records == run.trace_records
    assert dict(bundle.checkpoint_payloads) == {}


def test_save_id_lexical_validation(tmp_path: Path) -> None:
    """t3：非法 id 3 例 → ``schema_invalid``（词法门先于一切 IO）。"""
    backend = make_p8_backend(tmp_path)
    env = to_persistence_snapshot(_make_min_snapshot("wsi_p8_fs_t3"))
    for bad_id in ("Save_1", "-leading", "a" * 129):
        with pytest.raises(PersistenceError) as exc_info:
            backend.save(
                save_id=bad_id, envelope=env, checkpoint_payloads={}, trace_records=()
            )
        assert exc_info.value.code == "schema_invalid"
    # 词法失败不产生任何落盘痕迹
    assert not (tmp_path / "saves_root").exists()


def test_atomic_write_replace_on_success(tmp_path: Path) -> None:
    """t4：同 id 二次 save = 整体覆盖（旧内容原子替换，load 取新面）。"""
    run = run_p8_script()
    build_p8_save(tmp_path, run)
    backend = make_p8_backend(tmp_path)
    env2 = _second_envelope(run.final_state)
    backend.save(
        save_id="save_p8_base",
        envelope=env2,
        checkpoint_payloads={},
        trace_records=run.trace_records,
    )
    bundle = backend.load(save_id="save_p8_base")
    assert bundle.envelope == env2
    assert bundle.envelope.created_wall_time == _WALL_T2


def test_atomic_write_corrupt_tmp_keeps_existing(tmp_path: Path) -> None:
    """t5（A14）：预置 ``snapshot.json.tmp`` 垃圾 → save 成功 → load 正常。

    垃圾 tmp 不泄漏进最终文件；save 后无 ``*.tmp`` 残留。
    """
    run = run_p8_script()
    save_dir = build_p8_save(tmp_path, run)
    (save_dir / "snapshot.json.tmp").write_text("not json at all", encoding="utf-8")
    backend = make_p8_backend(tmp_path)
    env2 = _second_envelope(run.final_state)
    backend.save(
        save_id="save_p8_base",
        envelope=env2,
        checkpoint_payloads={},
        trace_records=run.trace_records,
    )
    assert not any(p.name.endswith(".tmp") for p in save_dir.iterdir())
    bundle = backend.load(save_id="save_p8_base")
    assert bundle.envelope == env2
    assert bundle.envelope.created_wall_time == _WALL_T2


def test_list_saves_sorted_deterministic(tmp_path: Path) -> None:
    """t6：b/a/c 乱序 save → ``("a","b","c")``（index 读取 + 排序，零目录枚举）。"""
    backend = make_p8_backend(tmp_path)
    for sid in ("b", "a", "c"):
        backend.save(
            save_id=sid,
            envelope=to_persistence_snapshot(_make_min_snapshot(f"wsi_p8_fs_{sid}")),
            checkpoint_payloads={},
            trace_records=(),
        )
    assert backend.list_saves() == ("a", "b", "c")


def test_load_missing_save_explicit(tmp_path: Path) -> None:
    """t7：未知 id → ``save_not_found``（无 index / index 无条目 两面）。"""
    backend = make_p8_backend(tmp_path)
    with pytest.raises(PersistenceError) as exc_no_index:
        backend.load(save_id="nope")
    assert exc_no_index.value.code == "save_not_found"
    build_p8_save(tmp_path, run_p8_script())
    with pytest.raises(PersistenceError) as exc_no_entry:
        backend.load(save_id="never_saved")
    assert exc_no_entry.value.code == "save_not_found"


def test_corrupt_snapshot_file_explicit(tmp_path: Path) -> None:
    """t8：手写垃圾 snapshot.json → ``corrupt_file``（JSON 词法门）。"""
    save_dir = build_p8_save(tmp_path, run_p8_script())
    (save_dir / "snapshot.json").write_text("{{{ not json", encoding="utf-8")
    with pytest.raises(PersistenceError) as exc_info:
        make_p8_backend(tmp_path).load(save_id="save_p8_base")
    assert exc_info.value.code == "corrupt_file"


def test_trace_jsonl_order_preserved(tmp_path: Path) -> None:
    """t9：5 记录保序（文件行序 == load 序）。"""
    backend = make_p8_backend(tmp_path)
    records = tuple(
        TraceRecord(
            record_id=TraceRecordId(f"trc_{n:032d}"), kind=TraceKind.DOMAIN_EVENT
        )
        for n in range(1, 6)
    )
    backend.save(
        save_id="order_save",
        envelope=to_persistence_snapshot(_make_min_snapshot("wsi_p8_fs_t9")),
        checkpoint_payloads={},
        trace_records=records,
    )
    bundle = backend.load(save_id="order_save")
    assert [r.record_id for r in bundle.trace_records] == [
        r.record_id for r in records
    ]


def test_trace_jsonl_bad_line_explicit(tmp_path: Path) -> None:
    """t10：第 2 行垃圾 → ``corrupt_file`` + message 含行号。"""
    save_dir = build_p8_save(tmp_path, run_p8_script())
    corrupt_save(save_dir, "bad_trace_line")
    with pytest.raises(PersistenceError) as exc_info:
        make_p8_backend(tmp_path).load(save_id="save_p8_base")
    assert exc_info.value.code == "corrupt_file"
    assert "line 2" in str(exc_info.value)


def test_checkpoint_files_roundtrip(tmp_path: Path) -> None:
    """t11：2 backend 体 roundtrip 相等（文件面 + ``checkpoint_payloads`` 面）。"""
    backend = make_p8_backend(tmp_path)
    refs = {"alpha": "checkpoints/alpha.json", "beta": "checkpoints/beta.json"}
    payloads = {"alpha": {"version": 1, "seed": 7}, "beta": {"version": 2, "seed": 11}}
    backend.save(
        save_id="ckpt_save",
        envelope=to_persistence_snapshot(
            _make_min_snapshot("wsi_p8_fs_t11"), backend_checkpoints=refs
        ),
        checkpoint_payloads=payloads,
        trace_records=(),
    )
    save_dir = tmp_path / _SAVE_ROOT / "ckpt_save"
    assert (save_dir / "checkpoints" / "alpha.json").is_file()
    assert (save_dir / "checkpoints" / "beta.json").is_file()
    bundle = backend.load(save_id="ckpt_save")
    assert dict(bundle.checkpoint_payloads) == payloads
    assert bundle.envelope.backend_checkpoints == refs


def test_save_dirty_dir_layout_violation(tmp_path: Path) -> None:
    """t12：闭集外文件 → ``layout_violation``。"""
    save_dir = build_p8_save(tmp_path, run_p8_script())
    (save_dir / "rogue.txt").write_text("extra file", encoding="utf-8")
    with pytest.raises(PersistenceError) as exc_info:
        make_p8_backend(tmp_path).load(save_id="save_p8_base")
    assert exc_info.value.code == "layout_violation"


def test_save_directory_byte_deterministic(tmp_path: Path) -> None:
    """t13：固定 wall time 双 save（独立 root）→ 三文件字节一致。"""
    run = run_p8_script()
    root_a, root_b = tmp_path / "root_a", tmp_path / "root_b"
    env = to_persistence_snapshot(
        Snapshot(
            world_state=run.final_state,
            runtime_state=run.runtime_state,
            world_instance_id="wsi_p8_fs_t13",
            created_logical_tick=3,
            project_version="1.0.0",
            module_versions={"core": "84a5d4f"},
        ),
        trace_ref="trace.jsonl",
        created_wall_time=_WALL_T1,
    )
    for backend in (
        FilesystemPersistenceBackend(root_a),
        FilesystemPersistenceBackend(root_b),
    ):
        backend.save(
            save_id="det_save",
            envelope=env,
            checkpoint_payloads={},
            trace_records=run.trace_records,
        )
    dir_a = root_a / "saves" / "det_save"
    dir_b = root_b / "saves" / "det_save"
    assert (dir_a / "snapshot.json").read_bytes() == (dir_b / "snapshot.json").read_bytes()
    assert (dir_a / "trace.jsonl").read_bytes() == (dir_b / "trace.jsonl").read_bytes()
    idx_a = json.loads((root_a / "index.json").read_text(encoding="utf-8"))
    idx_b = json.loads((root_b / "index.json").read_text(encoding="utf-8"))
    assert idx_a["saves"]["det_save"] == idx_b["saves"]["det_save"]


def test_backend_protocol_method_surface(tmp_path: Path) -> None:
    """t14：3 方法签名面（Protocol 结构校验：keyword-only 闭集）。"""
    backend = make_p8_backend(tmp_path)
    assert isinstance(backend, PersistenceBackend)
    save_params = inspect.signature(backend.save).parameters
    assert list(save_params) == [
        "save_id",
        "envelope",
        "checkpoint_payloads",
        "trace_records",
    ]
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in save_params.values())
    load_params = inspect.signature(backend.load).parameters
    assert list(load_params) == ["save_id"]
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in load_params.values())
    assert list(inspect.signature(backend.list_saves).parameters) == []
