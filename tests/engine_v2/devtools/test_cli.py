"""P8 T08 devcontrol CLI 面测试（SOT §6.1 t1–t14）。

钉死面（§6.1 表逐项对应）：

- t1 5 命令全跑 ``ok=true``（A10 深化）；
- t2 顶层键集 == 6 键字面量（闭集）+ tool/schema_version/command 值面；
- t3 ``inspect`` 数据面（score / revision / logical_tick / scheduler_queue /
  active_actions / backend_refs / 三版本）；
- t4 ``--kind`` 过滤 + 非法 kind → ``usage_error``（退出码 2）；
- t5 CLI replay 终态 == inspect 快照态（SC-1；DEV-W4-2 存档无基线态 ⇒
  运行结束存档重放 = 自快照 revision 的空连续前缀：base=final=3、
  applied=0、events 空）；
- t6 SC-3（``checkpointable=False`` backend ref）→ ``branch_rejected``
  + message 含 backend_id + 退出码 1（G8-4 CLI 面）；
- t7 ``test`` 命令 checks 行名闭集 5 + ``replay_consistency`` 行 ok=true；
- t8 **A20**：5 命令 stdout 全部 JSON-clean；
- t9 ``DEVCONTROL_CLI_SCHEMA_VERSION == 1`` + ``CLI_COMMANDS`` 5 元组
  字面量；
- t10 无 / 未知子命令 → ``usage_error`` + 退出码 2；
- t11 未知 save → ``save_not_found`` + 退出码 1；
- t12 成功路径退出码 0；
- t13 有无 ``--json`` 信封逐字节一致（D-P8-09 单面）；
- t14 ``cli.py`` + 脚本 AST：零 ``asyncio``/``socket``/``subprocess``
  （D4/D1）。

纪律：扁平函数（零 class / 零 subprocess / 零跨函数状态）；CLI 经冻结
conftest ``cli_runner`` 缝（惰性导入 + stdout 重定向，跨波次）；确定性
（D6：不钉 uuid 派生 id，save 由 ``build_p8_save`` 确定性构造）。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from src.engine_v2.core import Snapshot, assert_json_clean
from src.engine_v2.devtools.cli import (
    CLI_COMMANDS,
    CLI_TOOL_NAME,
    DEVCONTROL_CLI_SCHEMA_VERSION,
)
from src.engine_v2.persistence.filesystem import FilesystemPersistenceBackend
from src.engine_v2.persistence.snapshot import to_persistence_snapshot
from tests.engine_v2.devtools.conftest import (
    build_p8_save,
    cli_runner,
    make_sc3_runtime,
    run_p8_script,
)

# —— 字面量面（§6.4 同族：host 给出，D6）——

_SAVE_ID_SC1 = "save_p8_base"
_SAVE_ID_SC3 = "save_p8_sc3"
_FIVE_INVOCATIONS: tuple[tuple[str, ...], ...] = (
    ("inspect", _SAVE_ID_SC1),
    ("trace", _SAVE_ID_SC1),
    ("replay", _SAVE_ID_SC1),
    ("branch", _SAVE_ID_SC1, "--new-id", "wsi_p8_branch_a"),
    ("test", _SAVE_ID_SC1),
)
_ENVELOPE_KEYS = {"tool", "schema_version", "command", "ok", "data", "error"}
_FORBIDDEN_MODULES = {"asyncio", "socket", "subprocess"}


def _build_sc3_save(tmp_path: Path) -> None:
    """SC-3 save（G8-4 负样本）：SC-1 run + ``checkpointable=False`` runtime。"""
    run = run_p8_script()
    snapshot = Snapshot(
        world_state=run.final_state,
        runtime_state=make_sc3_runtime(),
        world_instance_id="wsi_p8_sc1",
        created_logical_tick=3,
        project_version="1.0.0",
        module_versions={"core": "84a5d4f"},
    )
    envelope = to_persistence_snapshot(
        snapshot,
        trace_ref="trace.jsonl",
        created_wall_time="1970-01-01T00:00:00+00:00",
    )
    backend = FilesystemPersistenceBackend(tmp_path / "saves_root")
    backend.save(
        save_id=_SAVE_ID_SC3,
        envelope=envelope,
        checkpoint_payloads={},
        trace_records=run.trace_records,
    )


def _sc1_cli(tmp_path: Path):
    """SC-1 save + 冻结 CLI 缝（每测试独立 tmp_path，零跨函数状态）。"""
    build_p8_save(tmp_path, run_p8_script())
    return cli_runner(tmp_path)


def test_cli_five_commands_run_ok(tmp_path: Path) -> None:
    """t1：5 命令全跑 ``ok=true``（A10 深化）。"""
    cli = _sc1_cli(tmp_path)
    for argv in _FIVE_INVOCATIONS:
        stdout, code = cli(list(argv))
        envelope = json.loads(stdout)
        assert code == 0
        assert envelope["ok"] is True
        assert envelope["error"] is None
        assert envelope["data"] is not None


def test_envelope_keys_exact_set(tmp_path: Path) -> None:
    """t2：顶层键集 == 6 键字面量（闭集）+ tool / 版本 / command 值面。"""
    cli = _sc1_cli(tmp_path)
    stdout, code = cli(["inspect", _SAVE_ID_SC1])
    envelope = json.loads(stdout)
    assert code == 0
    assert set(envelope) == _ENVELOPE_KEYS
    assert envelope["tool"] == "llmsim-devcontrol"
    assert envelope["schema_version"] == 1
    assert envelope["command"] == "inspect"


def test_inspect_data_surface(tmp_path: Path) -> None:
    """t3：Spec §37 快照派生面（score / revision / tick / 队列 / 版本）。"""
    cli = _sc1_cli(tmp_path)
    stdout, code = cli(["inspect", _SAVE_ID_SC1])
    envelope = json.loads(stdout)
    assert code == 0
    data = envelope["data"]
    assert set(data) == {
        "save_id",
        "world_state",
        "runtime_state",
        "backend_refs",
        "persistence_versions",
    }
    assert data["save_id"] == _SAVE_ID_SC1
    assert data["world_state"]["world_variables"]["score"] == 2
    assert data["world_state"]["world_revision"] == 3
    assert data["runtime_state"]["logical_tick"] == 3
    assert "scheduler_queue" in data["runtime_state"]
    assert "active_actions" in data["runtime_state"]
    assert data["backend_refs"] == {}
    assert data["persistence_versions"] == {
        "persistence_format_version": 1,
        "snapshot_format_version": 1,
        "contract_schema_version": 1,
    }


def test_trace_filter_by_kind(tmp_path: Path) -> None:
    """t4：``--kind`` 过滤计数 + 非法 kind → ``usage_error``（退出码 2）。"""
    cli = _sc1_cli(tmp_path)
    stdout, code = cli(["trace", _SAVE_ID_SC1, "--kind", "transaction"])
    envelope = json.loads(stdout)
    assert code == 0
    assert envelope["ok"] is True
    data = envelope["data"]
    assert data["count"] == 3
    assert len(data["records"]) == 3
    assert all(record["kind"] == "transaction" for record in data["records"])
    stdout, code = cli(["trace", _SAVE_ID_SC1, "--kind", "bogus_kind"])
    envelope = json.loads(stdout)
    assert code == 2
    assert envelope["ok"] is False
    assert envelope["data"] is None
    assert envelope["error"]["code"] == "usage_error"


def test_replay_final_state_matches(tmp_path: Path) -> None:
    """t5：CLI replay 终态 == inspect 快照态（SC-1；DEV-W4-2 空前缀面）。"""
    cli = _sc1_cli(tmp_path)
    inspect_data = json.loads(cli(["inspect", _SAVE_ID_SC1])[0])["data"]
    stdout, code = cli(["replay", _SAVE_ID_SC1])
    envelope = json.loads(stdout)
    assert code == 0
    assert envelope["ok"] is True
    data = envelope["data"]
    assert data["final_world_state"] == inspect_data["world_state"]
    # DEV-W4-2：存档格式无 trace 基线态 ⇒ 运行结束存档（SC-1，快照 rev 3）
    # 取自快照 revision 的最长连续已提交前缀 = 空前缀 ⇒ 恒等重放面。
    assert data["base_revision"] == 3
    assert data["final_revision"] == 3
    assert data["transactions_applied"] == 0
    assert data["events"] == []


def test_branch_reject_error_envelope(tmp_path: Path) -> None:
    """t6：SC-3 → ``branch_rejected`` + message 含 backend_id + 退出码 1。"""
    _build_sc3_save(tmp_path)
    cli = cli_runner(tmp_path)
    stdout, code = cli(["branch", _SAVE_ID_SC3, "--new-id", "wsi_p8_sc3_b"])
    envelope = json.loads(stdout)
    assert code == 1
    assert envelope["ok"] is False
    assert envelope["data"] is None
    assert envelope["error"]["code"] == "branch_rejected"
    assert "rigid_body" in envelope["error"]["message"]


def test_test_command_report(tmp_path: Path) -> None:
    """t7：``test`` 命令 checks 行名闭集 5 + ``replay_consistency`` ok=true。"""
    cli = _sc1_cli(tmp_path)
    stdout, code = cli(["test", _SAVE_ID_SC1])
    envelope = json.loads(stdout)
    assert code == 0
    assert envelope["ok"] is True
    data = envelope["data"]
    assert data["save_id"] == _SAVE_ID_SC1
    assert data["ok"] is True
    checks = data["checks"]
    assert [row["check"] for row in checks] == [
        "layout",
        "envelope_versions",
        "trace_parse",
        "replay_consistency",
        "json_clean",
    ]
    assert all(set(row) == {"check", "ok"} for row in checks)
    assert all(row["ok"] is True for row in checks)
    replay_row = next(row for row in checks if row["check"] == "replay_consistency")
    assert replay_row["ok"] is True


def test_cli_output_json_clean(tmp_path: Path) -> None:
    """t8（**A20**）：5 命令 stdout 全部 JSON-clean。"""
    cli = _sc1_cli(tmp_path)
    for argv in _FIVE_INVOCATIONS:
        stdout, _code = cli(list(argv))
        assert_json_clean(json.loads(stdout))


def test_schema_version_constant() -> None:
    """t9：schema 版本常量 == 1 + ``CLI_COMMANDS`` 5 元组字面量。"""
    assert DEVCONTROL_CLI_SCHEMA_VERSION == 1
    assert CLI_COMMANDS == ("inspect", "trace", "replay", "branch", "test")
    assert CLI_TOOL_NAME == "llmsim-devcontrol"


def test_usage_error_code(tmp_path: Path) -> None:
    """t10：无 / 未知子命令 → ``usage_error`` + 退出码 2。"""
    cli = cli_runner(tmp_path)
    stdout, code = cli([])
    envelope = json.loads(stdout)
    assert code == 2
    assert envelope["ok"] is False
    assert envelope["data"] is None
    assert envelope["command"] is None
    assert envelope["error"]["code"] == "usage_error"
    stdout, code = cli(["frobnicate", _SAVE_ID_SC1])
    envelope = json.loads(stdout)
    assert code == 2
    assert envelope["ok"] is False
    assert envelope["command"] is None
    assert envelope["error"]["code"] == "usage_error"


def test_save_not_found_code(tmp_path: Path) -> None:
    """t11：未知 save → ``save_not_found`` + 退出码 1（先建合法 save 根）。"""
    cli = _sc1_cli(tmp_path)
    stdout, code = cli(["inspect", "save_missing"])
    envelope = json.loads(stdout)
    assert code == 1
    assert envelope["ok"] is False
    assert envelope["data"] is None
    assert envelope["error"]["code"] == "save_not_found"


def test_exit_codes_ok_zero(tmp_path: Path) -> None:
    """t12：成功路径（5 命令）退出码恒 0。"""
    cli = _sc1_cli(tmp_path)
    for argv in _FIVE_INVOCATIONS:
        _stdout, code = cli(list(argv))
        assert code == 0


def test_json_flag_accepted_noop(tmp_path: Path) -> None:
    """t13：有无 ``--json`` 信封逐字节一致（D-P8-09 单面）。"""
    cli = _sc1_cli(tmp_path)
    plain = cli(["inspect", _SAVE_ID_SC1])
    flagged = cli(["--json", "inspect", _SAVE_ID_SC1])
    assert flagged == plain


def test_cli_zero_asyncio_ast() -> None:
    """t14：``cli.py`` + 脚本 AST 零 ``asyncio``/``socket``/``subprocess``。"""
    root = Path(__file__).resolve().parents[3]
    for relative in (
        ("src", "engine_v2", "devtools", "cli.py"),
        ("scripts", "v2_devcontrol.py"),
    ):
        tree = ast.parse((root / Path(*relative)).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in _FORBIDDEN_MODULES
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in _FORBIDDEN_MODULES
            elif isinstance(node, ast.Name):
                assert node.id not in _FORBIDDEN_MODULES
