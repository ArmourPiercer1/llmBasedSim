"""P6-W1 ``profiles.py`` 单测（SOT §3.1 + §6.1 L808，恰 10 个平铺函数）。

覆盖项（逐项对应 §6.1 L808 行）：

1. ``test_tier_scale_monotonic``：TIER_SCALE 单调性——context_length_min 与
   max_output_min 严格递增 + reasoning_class_min 按 REASONING_ORDER 单调不减
   （两断言合 1 函数，A-W1-7）；
2. ``test_reasoning_vocabulary_closed_and_ordered``：REASONING_CLASSES 封闭
   4 值 + 与 REASONING_ORDER 序一致；
3. ``test_tier_level_all_five``：tier_level 正例（5 档全取）；
4. ``test_tier_level_out_of_range``：tier_level 反例（-1 / 5 越界 ValueError）；
5. ``test_profile_unknown_key_forbidden``：extra=forbid 拒绝未知键；
6. ``test_profile_tier_out_of_range``：tier 越界（5）拒绝；
7. ``test_profile_context_below_tier_floor``：context_length 低于档下限拒绝
   （tier=2 而 context_length=1000）；
8. ``test_profile_structured_output_required_by_tier``：tier 要求
   structured_output 而 False 拒绝（tier=2）；
9. ``test_profile_reasoning_class_below_tier_floor``：reasoning_class 低于档
   下限拒绝（tier=4 而 "standard"）；
10. ``test_capability_re_positive_negative``：CAPABILITY_RE 正/反（合法
    ``major_character`` 命中；大写开头 / 数字开头 / 65 字符拒绝）。

本文件自包含（零跨测试文件 import、不建 conftest，A-W1-1）；hermetic、无
网络、无 subprocess。
"""

from __future__ import annotations

import pytest

from pydantic import ValidationError

from src.engine_v2.llm.profiles import (
    CAPABILITY_RE,
    REASONING_CLASSES,
    REASONING_ORDER,
    TIER_SCALE,
    ModelCapabilityProfile,
    tier_level,
)


def _valid_kwargs(**overrides: object) -> dict[str, object]:
    """tier=2 合法基线（档下限恰值），按参覆盖。"""
    kwargs: dict[str, object] = {
        "model_id": "sim_model_a",
        "tier": 2,
        "context_length": 64000,
        "max_output": 8192,
        "structured_output": True,
        "reasoning_class": "standard",
    }
    kwargs.update(overrides)
    return kwargs


def test_tier_scale_monotonic() -> None:
    assert len(TIER_SCALE) == 5
    assert [level.tier for level in TIER_SCALE] == [0, 1, 2, 3, 4]
    for prev, cur in zip(TIER_SCALE, TIER_SCALE[1:]):
        assert cur.context_length_min > prev.context_length_min
        assert cur.max_output_min > prev.max_output_min
        assert (
            REASONING_ORDER.index(cur.reasoning_class_min)
            >= REASONING_ORDER.index(prev.reasoning_class_min)
        )


def test_reasoning_vocabulary_closed_and_ordered() -> None:
    assert REASONING_CLASSES == frozenset({"none", "standard", "advanced", "deep"})
    assert REASONING_ORDER == ("none", "standard", "advanced", "deep")
    assert len(REASONING_ORDER) == 4
    assert set(REASONING_ORDER) == REASONING_CLASSES


def test_tier_level_all_five() -> None:
    for index in range(5):
        assert tier_level(index) is TIER_SCALE[index]
    assert tier_level(0).label == "baseline"
    assert tier_level(1).label == "dialogue"
    assert tier_level(2).label == "standard"
    assert tier_level(3).label == "advanced"
    assert tier_level(4).label == "expert"


def test_tier_level_out_of_range() -> None:
    for bad_tier in (-1, 5):
        with pytest.raises(ValueError):
            tier_level(bad_tier)


def test_profile_unknown_key_forbidden() -> None:
    with pytest.raises(ValidationError):
        ModelCapabilityProfile(**_valid_kwargs(bogus_extra=True))


def test_profile_tier_out_of_range() -> None:
    with pytest.raises(ValidationError):
        ModelCapabilityProfile(**_valid_kwargs(tier=5))


def test_profile_context_below_tier_floor() -> None:
    with pytest.raises(ValidationError):
        ModelCapabilityProfile(**_valid_kwargs(context_length=1000))


def test_profile_structured_output_required_by_tier() -> None:
    with pytest.raises(ValidationError):
        ModelCapabilityProfile(**_valid_kwargs(structured_output=False))


def test_profile_reasoning_class_below_tier_floor() -> None:
    with pytest.raises(ValidationError):
        ModelCapabilityProfile(
            **_valid_kwargs(
                tier=4,
                context_length=262000,
                max_output=32768,
                structured_output=True,
                reasoning_class="standard",
            )
        )


def test_capability_re_positive_negative() -> None:
    assert CAPABILITY_RE.fullmatch("major_character") is not None
    assert CAPABILITY_RE.fullmatch("world_dynamics") is not None
    assert CAPABILITY_RE.fullmatch("Major_character") is None
    assert CAPABILITY_RE.fullmatch("1world") is None
    assert CAPABILITY_RE.fullmatch("a" * 65) is None
