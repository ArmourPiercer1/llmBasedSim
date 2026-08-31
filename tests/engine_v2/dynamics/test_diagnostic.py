"""P7-W1 test_diagnostic.py（SOT §6.1 t1–t8（逐文件编号），8 平铺函数，零 test class）。

契约面：诊断载体 ``DynamicsDiagnostic``（镜像 P6 ``RuntimeDiagnostic`` 形状，
ERR-P6-10(a) 先例）与 P7 8 码闭集 ``P7_DYNAMICS_DIAGNOSTIC_CODES``——
码集精确面、与 P5/P6 码集机械不相交（A20）、extra=forbid + frozen、
dump 面 JSON-clean（P7-INV-4 铁律）。
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.engine_v2.content.schemas import DIAGNOSTIC_CODES, DiagnosticSeverity
from src.engine_v2.core.serialization import assert_json_clean
from src.engine_v2.dynamics.diagnostic import DynamicsDiagnostic, P7_DYNAMICS_DIAGNOSTIC_CODES
from src.engine_v2.prompts.diagnostic import P6_RUNTIME_DIAGNOSTIC_CODES


def test_diagnostic_valid_construction() -> None:
    """t26：合法构造（ERROR 带 refs / WARNING 缺省 refs 空元组）。"""
    d = DynamicsDiagnostic(
        code="p7.budget_exhausted",
        severity=DiagnosticSeverity.ERROR,
        path="inference.calls",
        message="budget exhausted",
    )
    assert d.refs == ()
    d2 = DynamicsDiagnostic(
        code="p7.wire_parse_failed",
        severity=DiagnosticSeverity.WARNING,
        path="wire",
        message="wire parse failed",
        refs=("eff_ab",),
    )
    assert d2.refs == ("eff_ab",)


def test_diagnostic_rejects_foreign_code() -> None:
    """t27：闭集外 code（P8 面 / P5 面 / 拼错 / 空串）→ ValidationError。"""
    for bad in ("p8.stimulus_rejected", "LLMSIM_INFERENCE_HTTP", "p7.not_a_code", ""):
        with pytest.raises(ValidationError):
            DynamicsDiagnostic(
                code=bad,
                severity=DiagnosticSeverity.ERROR,
                path="x",
                message="m",
            )


def test_codes_set_exact_eight() -> None:
    """t28：P7 码集 = 8 码精确面（SOT 表序成员，无多无缺）。"""
    assert len(P7_DYNAMICS_DIAGNOSTIC_CODES) == 8
    assert set(P7_DYNAMICS_DIAGNOSTIC_CODES) == frozenset(
        {
            "p7.budget_exhausted",
            "p7.wire_parse_failed",
            "p7.wire_schema_invalid",
            "p7.stimulus_rejected",
            "p7.checkpoint_restore_failed",
            "p7.composite_child_failed",
            "p7.metadata_vocabulary_violation",
            "p7.unknown_backend_id",
        }
    )


def test_codes_disjoint_from_p5() -> None:
    """t29：P7 码集与 P5 18 码（``DIAGNOSTIC_CODES``）机械不相交。"""
    assert P7_DYNAMICS_DIAGNOSTIC_CODES & DIAGNOSTIC_CODES == frozenset()


def test_codes_disjoint_from_p5_and_p6() -> None:
    """t30（A20）：P7 码集与 P5 18 码 + P6 21 码双不相交（机械面）。"""
    assert P7_DYNAMICS_DIAGNOSTIC_CODES & P6_RUNTIME_DIAGNOSTIC_CODES == frozenset()
    assert P7_DYNAMICS_DIAGNOSTIC_CODES & DIAGNOSTIC_CODES == frozenset()


def test_diagnostic_extra_forbid() -> None:
    """t31：extra="forbid" + frozen（未知字段 / 赋值均拒绝）。"""
    with pytest.raises(ValidationError):
        DynamicsDiagnostic(
            code="p7.budget_exhausted",
            severity=DiagnosticSeverity.ERROR,
            path="x",
            message="m",
            extra_field=1,
        )
    d = DynamicsDiagnostic(
        code="p7.budget_exhausted",
        severity=DiagnosticSeverity.ERROR,
        path="x",
        message="m",
    )
    with pytest.raises(ValidationError):
        d.code = "p7.wire_parse_failed"


def test_diagnostic_dump_json_clean() -> None:
    """t32：``model_dump(mode="json")`` 面过 JSON-clean 铁律 + 可序列化。"""
    d = DynamicsDiagnostic(
        code="p7.checkpoint_restore_failed",
        severity=DiagnosticSeverity.ERROR,
        path="checkpoint",
        message="bad version",
        refs=("cp1",),
    )
    dumped = d.model_dump(mode="json")
    assert_json_clean(dumped)
    assert dumped["severity"] in ("error", "warning")
    assert isinstance(json.dumps(dumped, sort_keys=True, ensure_ascii=False), str)


def test_diagnostic_severity_vocab() -> None:
    """t33：severity 词表 = {error, warning}；闭集外值拒绝。"""
    assert {s.value for s in DiagnosticSeverity} == {"error", "warning"}
    with pytest.raises(ValidationError):
        DynamicsDiagnostic(
            code="p7.budget_exhausted",
            severity="critical",
            path="x",
            message="m",
        )
