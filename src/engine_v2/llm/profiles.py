"""P6-W1 T02 model 侧（SOT §3.1，D-P6-03）：tier 尺度 0-4 + 模型能力画像 + capability 字符串约定。

纯数据 + 纯函数，零 I/O、零非确定根源、同步面；frozen 数据面。本模块是当前
包中唯一不 import core/content 的模块（game 侧 InferenceCapabilityProfile =
P5 冻结消费面，router 消费，本模块不触碰）。构造期形状违例 = pydantic
ValidationError（load 面捕获转诊断，D-P6-18）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "REASONING_CLASSES",
    "REASONING_ORDER",
    "TierLevel",
    "TIER_SCALE",
    "tier_level",
    "ModelCapabilityProfile",
    "CAPABILITY_ID_PATTERN",
    "CAPABILITY_RE",
]

#: 推理等级 4 值封闭词表（D-P6-03）。
REASONING_CLASSES: Final[frozenset[str]] = frozenset({"none", "standard", "advanced", "deep"})

#: 推理等级强度递增序（序 = 强度递增，比较基准）。
REASONING_ORDER: Final[tuple[str, ...]] = ("none", "standard", "advanced", "deep")


@dataclass(frozen=True)
class TierLevel:
    """tier 尺度单档（D-P6-03，封闭 5 档域 0..4）。"""

    tier: int
    label: str
    context_length_min: int
    max_output_min: int
    structured_output_required: bool
    reasoning_class_min: str


#: tier 尺度 5 档（机械性质：context_length_min 与 max_output_min 严格单调
#: 递增 + reasoning_class_min 单调不减，单测断言）。
TIER_SCALE: Final[tuple[TierLevel, ...]] = (
    TierLevel(0, "baseline", 8000, 1024, False, "none"),
    TierLevel(1, "dialogue", 32000, 4096, False, "none"),
    TierLevel(2, "standard", 64000, 8192, True, "standard"),
    TierLevel(3, "advanced", 128000, 16384, True, "advanced"),
    TierLevel(4, "expert", 262000, 32768, True, "deep"),
)


def tier_level(tier: int) -> TierLevel:
    """索引助手：tier 0..4 → 对应档；越界（输入违例族）→ ValueError。"""
    if not 0 <= tier <= 4:
        raise ValueError(f"tier_level: tier 必须 ∈ 0..4，收到 {tier!r}")
    return TIER_SCALE[tier]


class ModelCapabilityProfile(BaseModel):
    """模型能力画像（部署侧：模型提供什么；SOT §3.1）。

    tier 档下限机械锁：context_length / max_output ≥ 档下限；tier 要求时
    structured_output 必须 True；reasoning_class ∈ 封闭词表且按
    REASONING_ORDER 序 ≥ 档下限。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str = Field(min_length=1)
    tier: int
    context_length: int = Field(gt=0)
    max_output: int = Field(gt=0)
    multimodal: bool = False
    structured_output: bool = False
    tool_support: bool = False
    reasoning_class: str
    notes: str = ""

    @model_validator(mode="after")
    def _check_tier_floor(self) -> "ModelCapabilityProfile":
        if not 0 <= self.tier <= 4:
            raise ValueError(f"tier 必须 ∈ TIER_SCALE 域 0..4：{self.tier!r}")
        scale = TIER_SCALE[self.tier]
        if self.context_length < scale.context_length_min:
            raise ValueError(
                f"context_length {self.context_length} 低于 tier {self.tier} 档下限 "
                f"{scale.context_length_min}"
            )
        if self.max_output < scale.max_output_min:
            raise ValueError(
                f"max_output {self.max_output} 低于 tier {self.tier} 档下限 "
                f"{scale.max_output_min}"
            )
        if scale.structured_output_required and not self.structured_output:
            raise ValueError(f"tier {self.tier} 要求 structured_output=True")
        if self.reasoning_class not in REASONING_CLASSES:
            raise ValueError(f"reasoning_class 必须 ∈ REASONING_CLASSES：{self.reasoning_class!r}")
        if (
            REASONING_ORDER.index(self.reasoning_class)
            < REASONING_ORDER.index(scale.reasoning_class_min)
        ):
            raise ValueError(
                f"reasoning_class {self.reasoning_class!r} 低于 tier {self.tier} 档下限 "
                f"{scale.reasoning_class_min!r}"
            )
        return self


#: capability = logical role id 字符串域 pattern（D-P6-03）。
CAPABILITY_ID_PATTERN: Final[str] = "^[a-z][a-z0-9_]{0,63}$"

#: CAPABILITY_ID_PATTERN 编译体。
CAPABILITY_RE: Final[re.Pattern[str]] = re.compile(CAPABILITY_ID_PATTERN)
