"""P8 文件系统持久化后端面：P8 包唯一文件 IO 面（T02，SOT §3.3，D4）。

目录布局（``<base>`` = 构造参数；单 save 目录闭集 =
:data:`~src.engine_v2.persistence.base.PERSISTENCE_SAVE_FILES`）::

    <base>/
      index.json                    # {"persistence_format_version": 1,
      saves/<save_id>/              #   "saves": {"<id>": {"created_wall_time": str | null}}}
        snapshot.json               # PersistenceSnapshot 全文（dump_persistence_snapshot）
        checkpoints/                # 每 backend 一个 <backend_id>.json（checkpoint 体，JSON-clean）
        trace.jsonl                 # 每行一条 TraceRecord JSON（保序）

纪律（D4）：本模块 = P8 **唯一**文件 IO 面；``os`` 仅用
``makedirs`` / ``replace`` / ``listdir`` 三函族（零破坏性调用；临时文件
清理亦经 ``os.replace`` 语义族）；原子写 = 同目录临时文件 ``<name>.tmp`` +
``os.replace``（D6 双跑确定性；A14：既有损坏 tmp 被覆写、零残留）。
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import ValidationError

from src.engine_v2.core import (
    TraceRecord,
    assert_json_clean,
    dump_json,
    load_json,
)
from src.engine_v2.persistence.base import (
    PERSISTENCE_FORMAT_VERSION,
    PERSISTENCE_SAVE_FILES,
    SAVE_ID_PATTERN,
    PersistenceError,
    SaveBundle,
)
from src.engine_v2.persistence.snapshot import (
    PersistenceSnapshot,
    dump_persistence_snapshot,
    load_persistence_snapshot,
)

__all__ = ("FilesystemPersistenceBackend", "read_trace_records")

_INDEX_FILENAME = "index.json"
_SNAPSHOT_FILENAME = "snapshot.json"
_CHECKPOINTS_DIRNAME = "checkpoints"
_TRACE_FILENAME = "trace.jsonl"
_TMP_SUFFIX = ".tmp"


def _require_save_id(save_id: str) -> None:
    """save_id 词法门（SAVE_ID_PATTERN.fullmatch；闭集外 → schema_invalid）。"""
    if not isinstance(save_id, str) or re.fullmatch(SAVE_ID_PATTERN, save_id) is None:
        raise PersistenceError(
            "schema_invalid",
            f"save_id {save_id!r} 不匹配词法 {SAVE_ID_PATTERN!r}",
        )


def _require_backend_id(backend_id: str) -> None:
    """backend_id 词法门（单路径段：非空、非 . / ..、零分隔符；→ schema_invalid）。

    防御面：checkpoint 体文件名 = ``<backend_id>.json``，分隔符 / 空段可
    逃逸 ``checkpoints/`` 目录（路径穿越）——load 侧布局闭集之外的第二道门。
    """
    if (
        not isinstance(backend_id, str)
        or backend_id in ("", ".", "..")
        or "/" in backend_id
        or "\\" in backend_id
        or os.sep in backend_id
    ):
        raise PersistenceError(
            "schema_invalid",
            f"backend_id {backend_id!r} 非法（须为单路径段：非空、非 . / ..、零分隔符）",
        )


def _dump_json_clean(value: object) -> str:
    """裸 dict → 确定性 JSON 文本（JSON-clean 断言 + 排序键，D6）。"""
    assert_json_clean(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _parse_json_object(text: str, where: str) -> dict[str, object]:
    """JSON 文本 → 对象 dict（fail-loud：解析失败 / 非对象 / 非 clean → corrupt_file）。"""
    try:
        raw = json.loads(text)
        assert_json_clean(raw)
    except (ValueError, AssertionError) as exc:
        raise PersistenceError("corrupt_file", f"{where} 非法：{exc}") from exc
    if not isinstance(raw, dict):
        raise PersistenceError("corrupt_file", f"{where} 顶层必须为 JSON 对象")
    return raw


def _dump_trace_text(trace_records: Sequence[TraceRecord]) -> str:
    """trace 序列 → JSONL 文本（每行一条；空序列 = 空文件；D6 确定性）。"""
    lines = [dump_json(record) for record in trace_records]
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


class FilesystemPersistenceBackend:
    """文件系统持久化后端（``PersistenceBackend`` 面结构实现；D4 唯一 IO 面）。

    - **惰性**：``__init__`` 只记录根目录，不预创建（首次 save 时
      ``os.makedirs(exist_ok=True)``）；
    - **原子写**：同目录临时文件 ``<name>.tmp`` + ``os.replace``（D6；
      A14：同 id 再存时既有损坏 tmp 被覆写、替换后零残留）；
    - **写序**（save）：``snapshot.json`` → 各 ``checkpoints/<id>.json``
      （backend_id 字典序）→ ``trace.jsonl`` → ``index.json``（upsert 条目）；
    - **同 ``save_id`` 二次 save = 整体覆盖**（旧文件被替换，确定性 winner）。
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir)

    # —— 内部面 ——

    def _save_dir(self, save_id: str) -> Path:
        return self._base / "saves" / save_id

    def _atomic_write(self, path: Path, text: str) -> None:
        """同目录临时文件 + ``os.replace``（D6 原子写；零 ``os.remove``）。"""
        tmp_path = path.with_name(path.name + _TMP_SUFFIX)
        with open(tmp_path, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_path, path)

    def _read_index_raw(self) -> dict[str, object] | None:
        """index.json 读取：缺失 → None（惰性面）；在场 → 解析 + 形状校验。"""
        index_path = self._base / _INDEX_FILENAME
        if not index_path.exists():
            return None
        return self._parse_index(index_path.read_text(encoding="utf-8"))

    @staticmethod
    def _parse_index(text: str) -> dict[str, object]:
        """index.json 文本 → 校验后 dict（fail-loud：corrupt_file / version_mismatch）。"""
        index = _parse_json_object(text, "index.json")
        version = index.get("persistence_format_version")
        if version != PERSISTENCE_FORMAT_VERSION:
            raise PersistenceError(
                "version_mismatch",
                f"index.json persistence_format_version={version!r} "
                f"!= 当前 {PERSISTENCE_FORMAT_VERSION}",
            )
        saves = index.get("saves")
        if not isinstance(saves, dict):
            raise PersistenceError("corrupt_file", "index.json saves 字段必须为对象")
        for save_id, entry in saves.items():
            if not isinstance(entry, dict) or "created_wall_time" not in entry:
                raise PersistenceError(
                    "corrupt_file", f"index.json 条目形状非法：save_id={save_id!r}"
                )
            wall_time = entry["created_wall_time"]
            if wall_time is not None and not isinstance(wall_time, str):
                raise PersistenceError(
                    "corrupt_file",
                    f"index.json created_wall_time 必须为 ISO-8601 串或 null："
                    f"save_id={save_id!r}",
                )
        return index

    def _upsert_index(self, save_id: str, created_wall_time: str | None) -> None:
        """index upsert：读（缺 → 新）→ 条目覆写 → 原子写回（D6 确定性文本）。"""
        index = self._read_index_raw()
        if index is None:
            index = {
                "persistence_format_version": PERSISTENCE_FORMAT_VERSION,
                "saves": {},
            }
        saves = index["saves"]
        assert isinstance(saves, dict)
        saves[save_id] = {"created_wall_time": created_wall_time}
        self._atomic_write(self._base / _INDEX_FILENAME, _dump_json_clean(index))

    def _check_layout(self, save_dir: Path) -> list[str]:
        """save 目录布局闭集校验（P8-INV-5；闭集外 / 缺失 / 子形状 → layout_violation）。

        返回 ``checkpoints/`` 内文件名单（字典序；供 checkpoint 体读取）。
        """
        entries = sorted(os.listdir(save_dir))
        expected = set(PERSISTENCE_SAVE_FILES)
        actual = set(entries)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise PersistenceError(
                "layout_violation",
                f"save 目录布局违反闭集 {PERSISTENCE_SAVE_FILES}："
                f"缺失={missing} 额外={extra}",
            )
        checkpoints_dir = save_dir / _CHECKPOINTS_DIRNAME
        checkpoint_names = sorted(os.listdir(checkpoints_dir))
        for name in checkpoint_names:
            if not name.endswith(".json") or not (checkpoints_dir / name).is_file():
                raise PersistenceError(
                    "layout_violation",
                    f"checkpoints/ 含非 JSON 体文件：{name!r}",
                )
        return checkpoint_names

    # —— PersistenceBackend 面 ——

    def save(
        self,
        *,
        save_id: str,
        envelope: PersistenceSnapshot,
        checkpoint_payloads: Mapping[str, Mapping[str, object]],
        trace_records: Sequence[TraceRecord],
    ) -> None:
        """全量写入（写序：snapshot → checkpoints → trace → index upsert）。

        失败面：``save_id`` / ``backend_id`` 词法 → ``schema_invalid``；
        OS 错误 → ``internal_error``（wrap 保留原因）。同 ``save_id`` 二次
        save = 整体覆盖（确定性 winner）。
        """
        _require_save_id(save_id)
        save_dir = self._save_dir(save_id)
        try:
            os.makedirs(save_dir / _CHECKPOINTS_DIRNAME, exist_ok=True)
            self._atomic_write(
                save_dir / _SNAPSHOT_FILENAME, dump_persistence_snapshot(envelope)
            )
            for backend_id in sorted(checkpoint_payloads):
                _require_backend_id(backend_id)
                self._atomic_write(
                    save_dir / _CHECKPOINTS_DIRNAME / f"{backend_id}.json",
                    _dump_json_clean(dict(checkpoint_payloads[backend_id])),
                )
            self._atomic_write(
                save_dir / _TRACE_FILENAME, _dump_trace_text(trace_records)
            )
            self._upsert_index(save_id, envelope.created_wall_time)
        except PersistenceError:
            raise
        except OSError as exc:
            raise PersistenceError(
                "internal_error", f"save {save_id!r} 文件系统操作失败：{exc}"
            ) from exc

    def load(self, *, save_id: str) -> SaveBundle:
        """全量读出（index 门 → 布局闭集 → snapshot → checkpoints → trace）。

        失败面（§3.1 闭集）：index 缺失条目 / 目录缺失 → ``save_not_found``；
        文件损坏 → ``corrupt_file``；词法 / 结构违约 → ``schema_invalid``；
        版本门 → ``version_mismatch``；布局闭集外 → ``layout_violation``。
        """
        _require_save_id(save_id)
        index = self._read_index_raw()
        if index is None:
            raise PersistenceError(
                "save_not_found", f"index.json 缺失（无任何 save）：save_id={save_id!r}"
            )
        saves = index["saves"]
        assert isinstance(saves, dict)
        if save_id not in saves:
            raise PersistenceError(
                "save_not_found",
                f"index 无 save_id={save_id!r} 条目（已知 {sorted(saves)}）",
            )
        save_dir = self._save_dir(save_id)
        if not save_dir.is_dir():
            raise PersistenceError(
                "save_not_found",
                f"save 目录缺失（index 悬空条目）：{save_dir}",
            )
        checkpoint_names = self._check_layout(save_dir)
        envelope = load_persistence_snapshot(
            (save_dir / _SNAPSHOT_FILENAME).read_text(encoding="utf-8")
        )
        checkpoint_payloads: dict[str, dict[str, object]] = {}
        for name in checkpoint_names:
            backend_id = name[: -len(".json")]
            body_text = (save_dir / _CHECKPOINTS_DIRNAME / name).read_text(encoding="utf-8")
            checkpoint_payloads[backend_id] = _parse_json_object(body_text, f"checkpoints/{name}")
        trace_records = read_trace_records(save_dir / _TRACE_FILENAME)
        return SaveBundle(
            save_id=save_id,
            envelope=envelope,
            checkpoint_payloads=checkpoint_payloads,
            trace_records=trace_records,
        )

    def list_saves(self) -> tuple[str, ...]:
        """index 键排序（D6 确定性）；index 缺失 → 空元组（惰性面）。"""
        index = self._read_index_raw()
        if index is None:
            return ()
        saves = index["saves"]
        assert isinstance(saves, dict)
        return tuple(sorted(saves))


def read_trace_records(path: str | Path) -> tuple[TraceRecord, ...]:
    """trace JSONL → ``TraceRecord`` 序列（逐行 ``load_json`` 唯一合法入口）。

    - 保文件序；空行跳过；
    - 坏行（JSON 词法 / 结构校验失败）→ ``PersistenceError(corrupt_file)``
      （message 含**行号**）；
    - ``record_id`` 重复 → ``corrupt_file``（流不变量：流内唯一）；
    - 文件缺失 → ``usage_error``（调用方错误面）；其他 OS 错误 →
      ``internal_error``。
    """
    trace_path = Path(path)
    try:
        text = trace_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PersistenceError(
            "usage_error", f"trace 文件不存在：{trace_path}"
        ) from exc
    except OSError as exc:
        raise PersistenceError(
            "internal_error", f"trace 文件读取失败：{trace_path}: {exc}"
        ) from exc
    records: list[TraceRecord] = []
    seen_ids: set[str] = set()
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = load_json(TraceRecord, line)
        except ValidationError as exc:
            raise PersistenceError(
                "corrupt_file", f"trace line {lineno} 非法 TraceRecord：{exc}"
            ) from exc
        except ValueError as exc:
            # json.JSONDecodeError 为 ValueError 子类
            raise PersistenceError(
                "corrupt_file", f"trace line {lineno} 非法 JSON：{exc}"
            ) from exc
        record_id = str(record.record_id)
        if record_id in seen_ids:
            raise PersistenceError(
                "corrupt_file", f"trace line {lineno} record_id 重复：{record_id!r}"
            )
        seen_ids.add(record_id)
        records.append(record)
    return tuple(records)
