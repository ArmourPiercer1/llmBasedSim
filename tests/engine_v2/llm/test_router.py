"""P6-W2 ``router.py`` 单测（SOT §3.3 + §6.1 L810，恰 12 个平铺函数）。

覆盖项（按 §6.1 L810 行逐项 1:1）：

1. ``test_no_capability``：capability ∉ inference_profiles → resolved None
   + 恰 1 条 NO_DEPLOYMENT（path=capability）；
2. ``test_model_undeclared_skip``：entry.model ∉ models 键 → 该 candidate
   被跳过 + MODEL_UNDECLARED 诊断，后续 candidate 仍参与（fallback 1 胜出）；
3. ``test_tier_mismatch_explicit_failure``：全 candidate 不满足 min_tier →
   resolved None + 恰 1 条 TIER_MISMATCH（refs = tried model_id 按尝试序）；
4. ``test_below_ideal_warning_non_blocking``：胜者 tier < ideal_tier →
   resolved 非 None + 恰 1 条 BELOW_IDEAL warning（refs=[model_id,
   str(ideal_tier)]）不阻断；
5. ``test_primary_wins``：primary 满足 min_tier → resolved_via="primary"
   （含 credential 只名不值内省断言：无值字段 + 诊断 message/refs 无 env 值
   探针）；
6. ``test_fallback_order``：primary 不达标 → fallback 1 达标 →
   resolved_via="fallback:1"；
7. ``test_multi_fallback_first_qualifier``：fallback 1 不达标、fallback 2
   达标（fallback 3 存在更高档）→ resolved_via="fallback:2"（首个满足者
   胜，非跳档择优）；
8. ``test_candidates_for_empty_and_order``：∉ → ()；∈ 含 2 fallback →
   (entry, fb1 视图, fb2 视图) 序 + 各视图 .model 面正确、entry 其余字段
   不变；
9. ``test_meets_tier_boundary``：tier == min_tier → True；tier =
   min_tier - 1 → False；
10. ``test_resolved_via_encoding``：0 → "primary"；1 → "fallback:1"；
    3 → "fallback:3"；
11. ``test_diagnostic_deterministic_order``：多条 (code, path, refs) 不同
    诊断场景 → diagnostics 序列 == (code, path, refs) 排序 + 双跑相等；
12. ``test_no_cross_capability_borrow``：profiles 只有 capability A，
    requirement B → NO_DEPLOYMENT + resolved None（绝不解析到 A 的模型）。

本文件自包含（零跨测试文件 import、不建 conftest、不建 __init__.py）；测试
数据直接构造（W1/P5 导出，零 I/O、零 fixture 文件）；hermetic、无网络、无
subprocess。
"""

from __future__ import annotations

import pytest

from src.engine_v2.content.schemas import DiagnosticSeverity, InferenceCapabilityProfile
from src.engine_v2.llm.deployment import DeploymentEntry, DeploymentProfile
from src.engine_v2.llm.profiles import ModelCapabilityProfile
from src.engine_v2.llm.router import (
    ResolvedModel,
    RouterResult,
    candidates_for,
    meets_tier,
    resolve_capability,
    resolved_via,
)

#: 诊断码常量（P6 21 码闭集之 RESOLVER 族 W2 发射面，SOT §8.1）。
_NO_DEPLOYMENT = "LLMSIM_RESOLVER_NO_DEPLOYMENT"
_MODEL_UNDECLARED = "LLMSIM_RESOLVER_MODEL_UNDECLARED"
_TIER_MISMATCH = "LLMSIM_RESOLVER_TIER_MISMATCH"
_BELOW_IDEAL = "LLMSIM_RESOLVER_BELOW_IDEAL"

#: credential env 名/值：名合 W1 pattern，值仅供「值不出现在任何面」探针
#: （A-W2-6 内省断言消费）。
_CRED_ENV_NAME = "SIM_CRED_NAME"
_CRED_ENV_VALUE = "cred-value-0001"


def _model(model_id: str, tier: int) -> ModelCapabilityProfile:
    """按 tier 档下限恰值直接构造合法模型画像（零 I/O）。"""
    context_length, max_output, structured_output, reasoning_class = {
        1: (32000, 4096, False, "none"),
        2: (64000, 8192, True, "standard"),
        3: (128000, 16384, True, "advanced"),
        4: (262000, 32768, True, "deep"),
    }[tier]
    return ModelCapabilityProfile(
        model_id=model_id,
        tier=tier,
        context_length=context_length,
        max_output=max_output,
        structured_output=structured_output,
        reasoning_class=reasoning_class,
    )


def _requirement(capability: str, min_tier: int, ideal_tier: int) -> InferenceCapabilityProfile:
    """直接构造需求画像（P5 冻结面：构造期校验 ideal_tier >= min_tier）。"""
    return InferenceCapabilityProfile(
        id=f"req-{capability}",
        capability=capability,
        min_tier=min_tier,
        ideal_tier=ideal_tier,
    )


def _entry(model: str, fallbacks: tuple[str, ...] = ()) -> DeploymentEntry:
    """直接构造 capability 位 entry（供应商侧取中性占位值）。"""
    return DeploymentEntry(provider="prov-a", model=model, fallbacks=fallbacks)


def test_no_capability() -> None:
    """1) 无 capability：∉ inference_profiles → resolved None + 恰 1 条 NO_DEPLOYMENT。"""
    deployment = DeploymentProfile(
        models={"m_low": _model("m_low", 1)},
        inference_profiles={"cap_a": _entry("m_low")},
    )
    result = resolve_capability(deployment, _requirement("cap_b", 1, 1))
    assert result.resolved is None
    assert len(result.diagnostics) == 1
    (diag,) = result.diagnostics
    assert diag.code == _NO_DEPLOYMENT
    assert diag.severity is DiagnosticSeverity.ERROR
    assert diag.path == "cap_b"
    assert diag.refs == ("inference_profiles 无此键",)


def test_model_undeclared_skip() -> None:
    """2) MODEL_UNDECLARED 跳过：entry.model 缺失 → 跳过 + 诊断，后续 candidate 仍胜出。"""
    deployment = DeploymentProfile(
        models={"m_low": _model("m_low", 1)},
        inference_profiles={"cap_a": _entry("m_ghost", fallbacks=("m_low",))},
    )
    result = resolve_capability(deployment, _requirement("cap_a", 1, 1))
    assert result.resolved is not None
    assert result.resolved.model_id == "m_low"
    assert result.resolved.resolved_via == "fallback:1"
    assert len(result.diagnostics) == 1
    (diag,) = result.diagnostics
    assert diag.code == _MODEL_UNDECLARED
    assert diag.severity is DiagnosticSeverity.ERROR
    assert diag.path == "cap_a"
    assert diag.refs == ("m_ghost",)


def test_tier_mismatch_explicit_failure() -> None:
    """3) TIER_MISMATCH 显式失败：全 candidate 不达标 → resolved None + 恰 1 条（refs 按尝试序）。"""
    deployment = DeploymentProfile(
        models={"m_low": _model("m_low", 1), "m_mid": _model("m_mid", 2)},
        inference_profiles={"cap_a": _entry("m_low", fallbacks=("m_mid",))},
    )
    result = resolve_capability(deployment, _requirement("cap_a", 3, 3))
    assert result.resolved is None
    assert len(result.diagnostics) == 1
    (diag,) = result.diagnostics
    assert diag.code == _TIER_MISMATCH
    assert diag.severity is DiagnosticSeverity.ERROR
    assert diag.path == "cap_a"
    assert diag.refs == ("m_low", "m_mid")


def test_below_ideal_warning_non_blocking() -> None:
    """4) BELOW_IDEAL warning 不阻断：胜者 tier < ideal → resolved 非 None + 恰 1 条 warning。"""
    deployment = DeploymentProfile(
        models={"m_low": _model("m_low", 1)},
        inference_profiles={"cap_a": _entry("m_low")},
    )
    result = resolve_capability(deployment, _requirement("cap_a", 1, 2))
    assert isinstance(result, RouterResult)
    assert result.resolved is not None
    assert isinstance(result.resolved, ResolvedModel)
    assert result.resolved.model_id == "m_low"
    assert len(result.diagnostics) == 1
    (diag,) = result.diagnostics
    assert diag.code == _BELOW_IDEAL
    assert diag.severity is DiagnosticSeverity.WARNING
    assert diag.path == "cap_a"
    assert diag.refs == ("m_low", "2")


def test_primary_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """5) primary 胜出 + credential 只名不值内省（A-W2-6：无值字段 + 诊断无 env 值）。"""
    monkeypatch.setenv(_CRED_ENV_NAME, _CRED_ENV_VALUE)
    entry = DeploymentEntry(
        provider="prov-a",
        model="m_low",
        base_url="https://example.invalid/v1",
        api_key_env=_CRED_ENV_NAME,
        temperature=0.3,
        timeout_seconds=12.5,
    )
    deployment = DeploymentProfile(
        models={"m_low": _model("m_low", 2)},
        inference_profiles={"cap_a": entry},
    )
    result = resolve_capability(deployment, _requirement("cap_a", 2, 2))
    assert result.resolved is not None
    resolved = result.resolved
    assert resolved.resolved_via == "primary"
    assert resolved.capability == "cap_a"
    assert resolved.model_id == "m_low"
    assert resolved.tier == 2
    assert resolved.context_length == 64000
    assert resolved.max_output == 8192
    assert resolved.structured_output is True
    assert resolved.reasoning_class == "standard"
    assert resolved.provider == "prov-a"
    assert resolved.base_url == "https://example.invalid/v1"
    assert resolved.api_key_env == _CRED_ENV_NAME
    assert resolved.temperature == 0.3
    assert resolved.timeout_seconds == 12.5
    # A-W2-6：只名不值——ResolvedModel 无 credential 值字段，诊断 message/
    # refs 亦无 env 值探针。
    assert _CRED_ENV_VALUE not in str(resolved)
    for value in resolved.model_dump().values():
        assert _CRED_ENV_VALUE not in str(value)
    for diag in result.diagnostics:
        assert _CRED_ENV_VALUE not in diag.message
        assert _CRED_ENV_VALUE not in diag.refs
    assert result.diagnostics == ()


def test_fallback_order() -> None:
    """6) fallback 序：primary 不达标 → fallback 1 达标 → resolved_via="fallback:1"。"""
    deployment = DeploymentProfile(
        models={"m_low": _model("m_low", 1), "m_mid": _model("m_mid", 2)},
        inference_profiles={"cap_a": _entry("m_low", fallbacks=("m_mid",))},
    )
    result = resolve_capability(deployment, _requirement("cap_a", 2, 2))
    assert result.resolved is not None
    assert result.resolved.model_id == "m_mid"
    assert result.resolved.resolved_via == "fallback:1"
    assert result.diagnostics == ()


def test_multi_fallback_first_qualifier() -> None:
    """7) 多 fallback 首个满足者胜：fb1 不达标、fb2 达标（fb3 更高档存在）→ "fallback:2"。"""
    deployment = DeploymentProfile(
        models={
            "m_low": _model("m_low", 1),
            "m_mid": _model("m_mid", 2),
            "m_hi": _model("m_hi", 3),
            "m_top": _model("m_top", 4),
        },
        inference_profiles={"cap_a": _entry("m_low", fallbacks=("m_mid", "m_hi", "m_top"))},
    )
    result = resolve_capability(deployment, _requirement("cap_a", 3, 3))
    assert result.resolved is not None
    assert result.resolved.model_id == "m_hi"
    assert result.resolved.resolved_via == "fallback:2"
    assert result.diagnostics == ()


def test_candidates_for_empty_and_order() -> None:
    """8) candidates_for 空/序：∉ → ()；∈ 含 2 fallback → (entry, fb1 视图, fb2 视图) 序。"""
    entry = DeploymentEntry(
        provider="prov-a",
        model="m_a",
        base_url="https://example.invalid/v1",
        api_key_env=_CRED_ENV_NAME,
        temperature=0.9,
        timeout_seconds=5.5,
        fallbacks=("m_b", "m_c"),
    )
    deployment = DeploymentProfile(inference_profiles={"cap_a": entry})
    assert candidates_for(deployment, "cap_b") == ()
    views = candidates_for(deployment, "cap_a")
    assert len(views) == 3
    assert views[0] is entry
    assert views[0].model == "m_a"
    for view, expected_model in ((views[1], "m_b"), (views[2], "m_c")):
        assert view.model == expected_model
        # 同 entry 的 model 替换视图：其余字段不变。
        assert view.provider == entry.provider
        assert view.base_url == entry.base_url
        assert view.api_key_env == entry.api_key_env
        assert view.temperature == entry.temperature
        assert view.timeout_seconds == entry.timeout_seconds
        assert view.fallbacks == entry.fallbacks


def test_meets_tier_boundary() -> None:
    """9) meets_tier 边界：tier == min_tier → True；tier = min_tier - 1 → False。"""
    model = _model("m_mid", 2)
    assert meets_tier(model, 2) is True
    assert meets_tier(model, 3) is False


def test_resolved_via_encoding() -> None:
    """10) resolved_via 编码：0 → "primary"；1 → "fallback:1"；3 → "fallback:3"。"""
    assert resolved_via(0) == "primary"
    assert resolved_via(1) == "fallback:1"
    assert resolved_via(3) == "fallback:3"


def test_diagnostic_deterministic_order() -> None:
    """11) 诊断确定性序：发射序非排序序 → 结果 == (code, path, refs) 排序 + 双跑相等。"""
    deployment = DeploymentProfile(
        models={"m_low": _model("m_low", 1)},
        inference_profiles={"cap_a": _entry("m_low", fallbacks=("z_ghost", "a_ghost"))},
    )
    requirement = _requirement("cap_a", 2, 2)
    first = resolve_capability(deployment, requirement)
    assert first.resolved is None
    assert len(first.diagnostics) == 3
    # 发射序为 (z_ghost, a_ghost, m_low)；排序键下 a_ghost < z_ghost，
    # 排序序必须重排前两条 → 断言非 vacuous。
    assert [d.code for d in first.diagnostics] == [
        _MODEL_UNDECLARED,
        _MODEL_UNDECLARED,
        _TIER_MISMATCH,
    ]
    assert [d.refs for d in first.diagnostics] == [("a_ghost",), ("z_ghost",), ("m_low",)]
    expected = tuple(sorted(first.diagnostics, key=lambda d: (d.code, d.path, d.refs)))
    assert first.diagnostics == expected
    second = resolve_capability(deployment, requirement)
    assert second.diagnostics == first.diagnostics


def test_no_cross_capability_borrow() -> None:
    """12) 不跨 capability 借用：profiles 只有 cap_a，requirement cap_b → NO_DEPLOYMENT + None。"""
    deployment = DeploymentProfile(
        models={"m_low": _model("m_low", 1)},
        inference_profiles={"cap_a": _entry("m_low")},
    )
    result = resolve_capability(deployment, _requirement("cap_b", 1, 1))
    assert result.resolved is None
    assert len(result.diagnostics) == 1
    (diag,) = result.diagnostics
    assert diag.code == _NO_DEPLOYMENT
    assert diag.severity is DiagnosticSeverity.ERROR
    assert diag.path == "cap_b"
    assert diag.refs == ("inference_profiles 无此键",)
    # 绝不解析到 cap_a 的模型（静默换模型禁令，G6-2 机械面）。
    assert all(d.code != _TIER_MISMATCH for d in result.diagnostics)
