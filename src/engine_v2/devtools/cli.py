"""P8 T08 devcontrol CLI 逻辑面（SOT §3.9 / §8.2 导出表）。

单行 JSON 信封命令行界面：

- 信封顶层恰 6 键：``tool`` / ``schema_version`` / ``command`` / ``ok`` /
  ``data`` / ``error``；``ok=false`` ⇒ ``data=None`` 且
  ``error={"code", "message"}``（码 ∈ ``P8_ERROR_CODES`` 闭集）；
- 退出码：0 = ok=true；1 = ok=false 且码 ≠ ``usage_error``（含
  ``branch_rejected``）；2 = ``usage_error``；
- D4：逻辑面零直接 ``open`` / ``os`` —— 盘面状态只经注入的
  ``PersistenceBackend`` 接口读取（缺省 ``FilesystemPersistenceBackend``，
  store-root 约定 ``<root>/saves_root`` 见 DEV-W4-1）；
- D6 确定性：零时钟 / 零随机数；``--json`` 接受且无副作用（D-P8-09 单面）；
- ``replay`` / ``test`` 重放语义：存档只含存档时刻终态快照、无 trace 基线态
  （DEV-W4-2）⇒ 自快照态重放「最长连续已提交事务前缀」（运行结束存档 =
  空前缀，终态 == 快照态）。
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from src.engine_v2.core import (
    PAYLOAD_RECORD_KEY,
    TraceKind,
    Transaction,
    TraceRecord,
    assert_json_clean,
)
from src.engine_v2.persistence.base import (
    P8_ERROR_CODES,
    PersistenceBackend,
    PersistenceError,
    SaveBundle,
)
from src.engine_v2.persistence.branch import BranchError, WorldInstanceHandle, branch_world
from src.engine_v2.persistence.checkpoint import BackendCheckpointRegistry
from src.engine_v2.persistence.filesystem import FilesystemPersistenceBackend
from src.engine_v2.persistence.replay import ReplayError, ReplayResult, replay_committed
from src.engine_v2.persistence.snapshot import check_persistence_versions

__all__ = (
    "CLI_TOOL_NAME",
    "DEVCONTROL_CLI_SCHEMA_VERSION",
    "CLI_COMMANDS",
    "build_cli_envelope",
    "run_devcontrol_cli",
)

CLI_TOOL_NAME: Final[str] = "llmsim-devcontrol"
DEVCONTROL_CLI_SCHEMA_VERSION: Final[int] = 1
CLI_COMMANDS: Final[tuple[str, ...]] = ("inspect", "trace", "replay", "branch", "test")

_USAGE_ERROR_CODE = "usage_error"


class _UsageError(Exception):
    """argparse 用法错误（内部载体 → ``usage_error`` 信封，退出码 2）。"""


class _DevcontrolParser(argparse.ArgumentParser):
    """把 argparse 用法错误转为异常的解析器（不直接 sys.exit）。"""

    def error(self, message: str) -> None:
        raise _UsageError(message)


def _default_backend(base_dir: str | Path | None) -> PersistenceBackend:
    """缺省 backend：``FilesystemPersistenceBackend(<root>/saves_root)``。

    ``base_dir=None`` → 当前工作目录。store-root 后缀 ``/saves_root`` 为 W4
    约定（DEV-W4-1：SOT §3.9 仅定缺省 backend 类，未定 store-root 布局；
    冻结 conftest 缝以 ``<tmp>/saves_root`` 钉死可观测行为）。
    """
    root = Path(base_dir) if base_dir is not None else Path.cwd()
    return FilesystemPersistenceBackend(root / "saves_root")


def build_cli_envelope(
    command: str | None,
    *,
    ok: bool,
    data: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    """构造 6 键 JSON 信封（D3：构造时过 ``assert_json_clean``）。

    ``ok=true`` ⇒ ``error=None``（携 error_* 为编程错误 → ``ValueError``）；
    ``ok=false`` ⇒ ``data`` 强制 None、``error={"code","message"}``，且
    ``code`` ∈ :data:`P8_ERROR_CODES` 闭集（闭集外 → ``ValueError``）。
    """
    if ok:
        if error_code is not None or error_message is not None:
            raise ValueError("ok=true 信封不得携 error 字段")
        error: dict[str, str] | None = None
    else:
        if error_code is None or error_message is None:
            raise ValueError("ok=false 信封必须携 error_code 与 error_message")
        if error_code not in P8_ERROR_CODES:
            raise ValueError(f"error_code {error_code!r} 不在 P8_ERROR_CODES 闭集")
        data = None
        error = {"code": error_code, "message": error_message}
    envelope: dict[str, Any] = {
        "tool": CLI_TOOL_NAME,
        "schema_version": DEVCONTROL_CLI_SCHEMA_VERSION,
        "command": command,
        "ok": ok,
        "data": data,
        "error": error,
    }
    assert_json_clean(envelope)
    return envelope


def _emit(envelope: dict[str, Any]) -> int:
    """打印单行 JSON 信封并返回退出码（0/1/2）。"""
    print(
        json.dumps(
            envelope,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    if envelope["ok"]:
        return 0
    return 2 if envelope["error"]["code"] == _USAGE_ERROR_CODE else 1


def _build_parser() -> _DevcontrolParser:
    parser = _DevcontrolParser(prog=CLI_TOOL_NAME, add_help=False)
    parser.add_argument("--json", dest="json_output", action="store_true", default=False)
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_inspect = sub.add_parser("inspect", help="检视 save 盘面", add_help=False)
    p_inspect.add_argument("save_id")

    p_trace = sub.add_parser("trace", help="查询 trace 记录流", add_help=False)
    p_trace.add_argument("save_id")
    p_trace.add_argument("--kind", dest="kind", default=None, metavar="KIND")

    p_replay = sub.add_parser("replay", help="重放已提交事务", add_help=False)
    p_replay.add_argument("save_id")

    p_branch = sub.add_parser("branch", help="自 save 派生新实例", add_help=False)
    p_branch.add_argument("save_id")
    p_branch.add_argument("--new-id", dest="new_id", required=True, metavar="NEW_ID")

    p_test = sub.add_parser("test", help="跑一致性检查报告", add_help=False)
    p_test.add_argument("save_id")
    return parser


# —— 命令数据面（只读 SaveBundle）——


def _cmd_inspect(bundle: SaveBundle) -> dict[str, Any]:
    """Spec §37 快照派生 4 项面（world/runtime/scheduler_queue/active_actions）。"""
    snapshot = bundle.envelope.snapshot
    runtime = snapshot.runtime_state
    return {
        "save_id": bundle.save_id,
        "world_state": snapshot.world_state.model_dump(mode="json"),
        "runtime_state": runtime.model_dump(mode="json"),
        "backend_refs": {
            backend_id: ref.model_dump(mode="json")
            for backend_id, ref in runtime.backend_refs.items()
        },
        "persistence_versions": {
            "persistence_format_version": bundle.envelope.persistence_format_version,
            "snapshot_format_version": snapshot.snapshot_format_version,
            "contract_schema_version": snapshot.contract_schema_version,
        },
    }


def _cmd_trace(bundle: SaveBundle, kind_filter: TraceKind | None) -> dict[str, Any]:
    records = [r for r in bundle.trace_records if kind_filter is None or r.kind is kind_filter]
    return {
        "save_id": bundle.save_id,
        "records": [record.model_dump(mode="json") for record in records],
        "count": len(records),
    }


def _replay_from_snapshot(bundle: SaveBundle) -> ReplayResult:
    """自快照态重放 trace：重放自快照修订起的**最长连续已提交事务前缀**。

    存档格式（Spec §30.2 六 SHOULD 项）只持久化存档时刻的终态快照，不含
    trace 基线态（基线 revision 0 的世界态不在存档任何字段内）；而冻结
    ``replay_committed`` 的连续性语义（每笔 ``txn.base_revision == 当前状态
    revision``，W2 实现）⇒ 对「运行结束时刻存档」（快照 revision == 最后
    提交 revision）无法自存档单独做全史重放。

    W4 取 SOT 沉默面最窄通解（DEV-W4-2）：自快照 revision 起取连续已提交
    前缀重放——``base_revision`` 低于快照 revision 的事务视为已反映于快照
    态（跳过，不重放）；运行结束存档 = 空前缀（终态 == 快照态、applied=0、
    events=()）；基线态存档（快照 revision == trace 起点）= 全量重放。
    事务 schema 非法或 commit_revision 重复仍显式抛错（不静默跳过，D7）。
    """
    state = bundle.envelope.snapshot.world_state
    committed: list[tuple[int, Transaction, TraceRecord]] = []
    for record in bundle.trace_records:
        if record.kind is not TraceKind.TRANSACTION:
            continue
        payload = record.payload
        raw = payload.get(PAYLOAD_RECORD_KEY) if isinstance(payload, dict) else None
        if not isinstance(raw, dict):
            raise ReplayError(
                code="schema_invalid",
                message=f"TRANSACTION 记录 payload 缺失或非法（record_id={record.record_id}）",
            )
        try:
            transaction = Transaction.model_validate(raw)
        except (KeyError, ValueError) as exc:
            raise ReplayError(
                code="schema_invalid",
                message=f"TRANSACTION 记录 payload 缺失或非法（record_id={record.record_id}）",
            ) from exc
        if transaction.commit_revision is None:
            continue  # ABORTED 不变式：COMMITTED ⟺ commit_revision 非空
        committed.append((int(transaction.commit_revision), transaction, record))
    committed.sort(key=lambda item: item[0])  # 稳定排序，同序重放
    seen_revisions: set[int] = set()
    for commit_revision, _transaction, _record in committed:
        if commit_revision in seen_revisions:
            raise ReplayError(message=f"commit_revision 重复：{commit_revision}")
        seen_revisions.add(commit_revision)
    revision = int(state.world_revision)
    included_record_ids: set[str] = set()
    for _commit_revision, transaction, record in committed:
        if int(transaction.base_revision) < revision:
            continue  # base 低于快照 revision：已反映于快照态，不重放
        if int(transaction.base_revision) != revision:
            break  # 连续性断裂 ⇒ 前缀结束（commit 序下 base 严格递增）
        included_record_ids.add(record.record_id)
        revision = int(transaction.commit_revision)
    filtered = [
        record
        for record in bundle.trace_records
        if record.kind is not TraceKind.TRANSACTION or record.record_id in included_record_ids
    ]
    return replay_committed(state, filtered)


def _cmd_replay(bundle: SaveBundle) -> dict[str, Any]:
    result = _replay_from_snapshot(bundle)
    return {
        "save_id": bundle.save_id,
        "final_world_state": result.final_state.model_dump(mode="json"),
        "base_revision": result.base_revision,
        "final_revision": result.final_revision,
        "transactions_applied": result.transactions_applied,
        "events": [event.model_dump(mode="json") for event in result.events],
    }


def _cmd_branch(bundle: SaveBundle, new_world_instance_id: str) -> dict[str, Any]:
    snapshot = bundle.envelope.snapshot
    handle = WorldInstanceHandle(
        world_instance_id=snapshot.world_instance_id,
        world_state=snapshot.world_state,
        runtime_state=snapshot.runtime_state,
    )
    result = branch_world(
        handle,
        new_world_instance_id=new_world_instance_id,
        registry=BackendCheckpointRegistry(),
        checkpoints=bundle.checkpoint_payloads,
    )
    return result.to_dict()


def _cmd_test(bundle: SaveBundle) -> dict[str, Any]:
    """5 检查行报告（行名闭集；报告面生成 ⇒ 信封恒 ok=true）。"""
    checks: list[dict[str, Any]] = [
        {"check": "layout", "ok": True},
        {
            "check": "envelope_versions",
            "ok": check_persistence_versions(bundle.envelope) == (),
        },
        {"check": "trace_parse", "ok": True},
    ]
    result = _replay_from_snapshot(bundle)
    checks.append(
        {
            "check": "replay_consistency",
            "ok": result.final_revision == bundle.envelope.snapshot.world_state.world_revision,
        }
    )
    try:
        bundle.to_dict()
        json_clean = True
    except Exception:
        json_clean = False
    checks.append({"check": "json_clean", "ok": json_clean})
    return {
        "save_id": bundle.save_id,
        "ok": all(row["ok"] for row in checks),
        "checks": checks,
    }


def run_devcontrol_cli(
    argv: Sequence[str],
    *,
    base_dir: str | Path | None = None,
    backend: PersistenceBackend | None = None,
) -> int:
    """执行 devcontrol 命令：解析参数 → 读 save → 打单行信封。

    返回退出码：0 = ok=true；1 = ok=false 且码 ≠ ``usage_error``；
    2 = ``usage_error``。``backend`` 注入点供测试；未传时按 ``base_dir``
    构造缺省 backend。
    """
    parser = _build_parser()
    try:
        namespace = parser.parse_args(list(argv))
    except _UsageError as exc:
        return _emit(
            build_cli_envelope(
                None,
                ok=False,
                error_code=_USAGE_ERROR_CODE,
                error_message=f"usage: {exc}",
            )
        )

    command: str | None = namespace.command
    if command is None:
        return _emit(
            build_cli_envelope(
                None,
                ok=False,
                error_code=_USAGE_ERROR_CODE,
                error_message="missing subcommand: " + " | ".join(CLI_COMMANDS),
            )
        )

    kind_filter: TraceKind | None = None
    if command == "trace" and namespace.kind is not None:
        try:
            kind_filter = TraceKind(namespace.kind)
        except ValueError:
            allowed = ", ".join(kind.value for kind in TraceKind)
            return _emit(
                build_cli_envelope(
                    command,
                    ok=False,
                    error_code=_USAGE_ERROR_CODE,
                    error_message=f"--kind 须为以下之一: {allowed}",
                )
            )

    active_backend = backend if backend is not None else _default_backend(base_dir)
    try:
        bundle = active_backend.load(save_id=namespace.save_id)
    except PersistenceError as exc:
        return _emit(
            build_cli_envelope(command, ok=False, error_code=exc.code, error_message=exc.message)
        )

    if command == "inspect":
        return _emit(build_cli_envelope(command, ok=True, data=_cmd_inspect(bundle)))
    if command == "trace":
        return _emit(build_cli_envelope(command, ok=True, data=_cmd_trace(bundle, kind_filter)))
    if command == "replay":
        try:
            data = _cmd_replay(bundle)
        except ReplayError as exc:
            return _emit(
                build_cli_envelope(
                    command, ok=False, error_code=exc.code, error_message=exc.message
                )
            )
        return _emit(build_cli_envelope(command, ok=True, data=data))
    if command == "branch":
        try:
            data = _cmd_branch(bundle, namespace.new_id)
        except BranchError as exc:
            return _emit(
                build_cli_envelope(
                    command, ok=False, error_code=exc.code, error_message=exc.message
                )
            )
        return _emit(build_cli_envelope(command, ok=True, data=data))
    # command == "test"
    try:
        data = _cmd_test(bundle)
    except ReplayError as exc:
        return _emit(
            build_cli_envelope(command, ok=False, error_code=exc.code, error_message=exc.message)
        )
    return _emit(build_cli_envelope(command, ok=True, data=data))
