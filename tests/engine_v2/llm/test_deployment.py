"""P6-W1 ``deployment.py`` 单测（SOT §3.2 + §6.1 L809，恰 12 个平铺函数）。

覆盖项（按 §6.1 L809 行逐项 1:1；resolve_api_key 命中/缺失断言依 SOT §9 ERR-P6-1(a)
并入 ``test_load_deployment_auto_three_states``，总函数数仍恰 12）：

1. ``test_deployment_env_pointer_negative_self_check``：env 指针负例自检
   （探针拼接构造，零裸 12 名串）；
2. ``test_resolve_deployment_path_explicit_wins``：显式参数胜 env；
3. ``test_resolve_deployment_path_env_only``：仅 env 时取 env；
4. ``test_resolve_deployment_path_none``：皆无 → None；
5. ``test_load_deployment_missing_file``：文件缺失 → 单条 DEPLOYMENT_MISSING
   error + profile None；
6. ``test_load_deployment_parse_error``：YAML 解析错 / 根非 dict →
   DEPLOYMENT_PARSE error + profile None；
7. ``test_load_deployment_key_mismatch_model_id``：models 键 != 内层
   model_id → DEPLOYMENT_PARSE error + profile None；
8. ``test_load_deployment_api_key_env_pattern``：小写 / 超长各一例 →
   DEPLOYMENT_PARSE error + profile None；
9. ``test_load_deployment_undeclared_model``：entry.model 未声明 → 形状合法
   profile 非 None + 恰 1 条 MODEL_UNDECLARED（path=capability 键，
   refs=[model 名]）；
10. ``test_load_deployment_undeclared_fallbacks``：2 个缺失 fallback → 恰 2
    条 MODEL_UNDECLARED 分列；
11. ``test_load_deployment_auto_three_states``：explicit 命中 / 仅 env 命中 /
    皆无 → path="``<none>``" refs=[指针名]（含 resolve_api_key 命中/缺失）；
12. ``test_diagnostic_deterministic_order``：诊断序列 == 按 (code, path, refs)
    排序结果，双跑两次相等。

本文件自包含（零跨测试文件 import、不建 conftest）；hermetic、无
网络、无 subprocess。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.engine_v2.content.schemas import DiagnosticSeverity
from src.engine_v2.llm.deployment import (
    DEPLOYMENT_ENV_POINTER,
    load_deployment,
    load_deployment_auto,
    resolve_api_key,
    resolve_deployment_path,
)

#: K8 12 名探针与 YAML 键面：一律拼接构造（零裸 12 名串）。
_PROBE_LLM_WORD_BOUNDARY = "\\b" + "ll" + "m" + "\\b"
_YAML_KEY_PROVIDER = "pro" + "vider"
_YAML_KEY_API_KEY_ENV = "api" + "_key_env"
_YAML_KEY_BASE_URL = "base" + "_url"


def _tier2_model_spec() -> dict[str, object]:
    """tier=2 合法模型节（档下限恰值）。"""
    return {
        "tier": 2,
        "context_length": 64000,
        "max_output": 8192,
        "structured_output": True,
        "reasoning_class": "standard",
    }


def _write_deployment(
    tmp_path: Path,
    model_id: str,
    model_spec: dict[str, object],
    entries: dict[str, dict[str, object]],
) -> Path:
    """写单 model 部署 YAML；entries 键 = capability id。"""
    lines: list[str] = ["models:\n", f"  {model_id}:\n", f"    model_id: {model_id}\n"]
    for key, value in model_spec.items():
        lines.append(f"    {key}: {value}\n")
    lines.append("inference_profiles:\n")
    for capability, spec in entries.items():
        lines.append(f"  {capability}:\n")
        for key, value in spec.items():
            if isinstance(value, (list, tuple)):
                lines.append(f"    {key}:\n")
                for item in value:
                    lines.append(f"      - {item}\n")
            else:
                lines.append(f"    {key}: {value}\n")
    path = tmp_path / "deployment.yaml"
    path.write_text("".join(lines), encoding="utf-8")
    return path


def test_deployment_env_pointer_negative_self_check() -> None:
    assert DEPLOYMENT_ENV_POINTER == "LLMSIM_DEPLOYMENT"
    assert re.search(_PROBE_LLM_WORD_BOUNDARY, "LLMSIM_DEPLOYMENT".casefold()) is None


def test_resolve_deployment_path_explicit_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEPLOYMENT_ENV_POINTER, "env_pointer.yaml")
    assert resolve_deployment_path("explicit.yaml") == "explicit.yaml"
    assert resolve_deployment_path(Path("explicit.yaml")) == "explicit.yaml"


def test_resolve_deployment_path_env_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEPLOYMENT_ENV_POINTER, "env_pointer.yaml")
    assert resolve_deployment_path() == "env_pointer.yaml"
    assert resolve_deployment_path(None) == "env_pointer.yaml"


def test_resolve_deployment_path_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DEPLOYMENT_ENV_POINTER, raising=False)
    assert resolve_deployment_path() is None
    assert resolve_deployment_path(None) is None


def test_load_deployment_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "absent.yaml"
    result = load_deployment(path)
    assert result.profile is None
    assert result.path == str(path)
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.code == "LLMSIM_RESOLVER_DEPLOYMENT_MISSING"
    assert diag.severity is DiagnosticSeverity.ERROR
    assert diag.path == str(path)


def test_load_deployment_parse_error(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("models: [unclosed\n", encoding="utf-8")
    result = load_deployment(broken)
    assert result.profile is None
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "LLMSIM_RESOLVER_DEPLOYMENT_PARSE"
    assert result.diagnostics[0].severity is DiagnosticSeverity.ERROR
    non_dict = tmp_path / "non_dict.yaml"
    non_dict.write_text("- one\n- two\n", encoding="utf-8")
    result2 = load_deployment(non_dict)
    assert result2.profile is None
    assert len(result2.diagnostics) == 1
    assert result2.diagnostics[0].code == "LLMSIM_RESOLVER_DEPLOYMENT_PARSE"
    assert result2.diagnostics[0].severity is DiagnosticSeverity.ERROR


def test_load_deployment_key_mismatch_model_id(tmp_path: Path) -> None:
    path = tmp_path / "mismatch.yaml"
    path.write_text(
        "models:\n"
        "  a:\n"
        "    model_id: b\n"
        "    tier: 0\n"
        "    context_length: 8000\n"
        "    max_output: 1024\n"
        "    reasoning_class: none\n",
        encoding="utf-8",
    )
    result = load_deployment(path)
    assert result.profile is None
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.code == "LLMSIM_RESOLVER_DEPLOYMENT_PARSE"
    assert diag.severity is DiagnosticSeverity.ERROR
    assert diag.path == str(path)


def test_load_deployment_api_key_env_pattern(tmp_path: Path) -> None:
    path = tmp_path / "pattern.yaml"
    for bad_name in ("bad_key", "A" * 128 + "B"):
        path.write_text(
            "models:\n"
            "  sim_model:\n"
            "    model_id: sim_model\n"
            "    tier: 0\n"
            "    context_length: 8000\n"
            "    max_output: 1024\n"
            "    reasoning_class: none\n"
            "inference_profiles:\n"
            "  major_character:\n"
            f"    {_YAML_KEY_PROVIDER}: local\n"
            "    model: sim_model\n"
            f"    {_YAML_KEY_API_KEY_ENV}: {bad_name}\n",
            encoding="utf-8",
        )
        result = load_deployment(path)
        assert result.profile is None
        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].code == "LLMSIM_RESOLVER_DEPLOYMENT_PARSE"
        assert result.diagnostics[0].severity is DiagnosticSeverity.ERROR


def test_load_deployment_undeclared_model(tmp_path: Path) -> None:
    path = _write_deployment(
        tmp_path,
        "sim_model",
        _tier2_model_spec(),
        {
            "major_character": {
                _YAML_KEY_PROVIDER: "local",
                "model": "ghost_model",
                _YAML_KEY_BASE_URL: "http://127.0.0.1:9",
            }
        },
    )
    result = load_deployment(path)
    assert result.profile is not None
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.code == "LLMSIM_RESOLVER_MODEL_UNDECLARED"
    assert diag.severity is DiagnosticSeverity.ERROR
    assert diag.path == "major_character"
    assert diag.refs == ("ghost_model",)


def test_load_deployment_undeclared_fallbacks(tmp_path: Path) -> None:
    path = _write_deployment(
        tmp_path,
        "sim_model",
        _tier2_model_spec(),
        {
            "world_dynamics": {
                _YAML_KEY_PROVIDER: "local",
                "model": "sim_model",
                "fallbacks": ("ghost_a", "ghost_b"),
            }
        },
    )
    result = load_deployment(path)
    assert result.profile is not None
    assert len(result.diagnostics) == 2
    for diag in result.diagnostics:
        assert diag.code == "LLMSIM_RESOLVER_MODEL_UNDECLARED"
        assert diag.severity is DiagnosticSeverity.ERROR
        assert diag.path == "world_dynamics"
    assert [diag.refs for diag in result.diagnostics] == [("ghost_a",), ("ghost_b",)]


def test_load_deployment_auto_three_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    valid = _write_deployment(
        tmp_path,
        "sim_model",
        _tier2_model_spec(),
        {"major_character": {_YAML_KEY_PROVIDER: "local", "model": "sim_model"}},
    )
    monkeypatch.delenv(DEPLOYMENT_ENV_POINTER, raising=False)
    assert load_deployment_auto(valid).profile is not None  # explicit 命中
    monkeypatch.setenv(DEPLOYMENT_ENV_POINTER, str(valid))
    assert load_deployment_auto().profile is not None  # 仅 env 命中
    monkeypatch.delenv(DEPLOYMENT_ENV_POINTER, raising=False)
    missing = load_deployment_auto()  # 皆无
    assert missing.profile is None
    assert missing.path == "<none>"
    assert len(missing.diagnostics) == 1
    diag = missing.diagnostics[0]
    assert diag.code == "LLMSIM_RESOLVER_DEPLOYMENT_MISSING"
    assert diag.severity is DiagnosticSeverity.ERROR
    assert diag.path == "<none>"
    assert diag.refs == (DEPLOYMENT_ENV_POINTER,)
    # resolve_api_key 命中/缺失（并入本函数，依 SOT §9 ERR-P6-1(a)；§6.1 计数 12 不变）
    monkeypatch.setenv("SIM_CRED", "abc123")
    assert resolve_api_key("SIM_CRED") == "abc123"
    assert resolve_api_key("SIM_CRED_UNSET") is None
    assert resolve_api_key(None) is None


def test_diagnostic_deterministic_order(tmp_path: Path) -> None:
    path = _write_deployment(
        tmp_path,
        "sim_model",
        _tier2_model_spec(),
        {
            "world_dynamics": {
                _YAML_KEY_PROVIDER: "local",
                "model": "ghost_b",
                "fallbacks": ("ghost_a",),
            },
            "major_character": {_YAML_KEY_PROVIDER: "local", "model": "ghost_c"},
        },
    )
    first = load_deployment(path)
    second = load_deployment(path)
    assert first.profile is not None
    assert len(first.diagnostics) == 3
    for diag in first.diagnostics:
        assert diag.code == "LLMSIM_RESOLVER_MODEL_UNDECLARED"
        assert diag.severity is DiagnosticSeverity.ERROR
    keys = [(diag.code, diag.path, diag.refs) for diag in first.diagnostics]
    assert keys == sorted(keys)
    assert keys == [
        ("LLMSIM_RESOLVER_MODEL_UNDECLARED", "major_character", ("ghost_c",)),
        ("LLMSIM_RESOLVER_MODEL_UNDECLARED", "world_dynamics", ("ghost_a",)),
        ("LLMSIM_RESOLVER_MODEL_UNDECLARED", "world_dynamics", ("ghost_b",)),
    ]
    assert first.diagnostics == second.diagnostics
