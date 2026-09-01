"""P9 W1 tests/engine_v2/modules fixtures（SOT §6.2 的 W1 子集；零测试函数）。

W1 交付 = ``fixed_clock`` / ``scripted_backend`` / ``dsl_rng``。

波次拆分注（派工决定，SOT §6.2 = 最终形态）：``p9_host`` /
``p9_world_builder`` 两 fixture 待 W6（首个 g9 样例测试波）随宿主协议
（SOT §3.16）落盘；W1–W5 单测波不引用。

``SeededRng`` = 本包自含一份（口径对齐
``tests/engine_v2/content/conftest.py::SeededRng`` 先例；**不 import**
P5 测试侧 conftest）：实现 P5 ``DslRng`` Protocol 三方法
rand/uniform/randint，固定 seed（W1 默认 20240501）。
"""

from __future__ import annotations

import random

import pytest

from src.engine_v2.core.revision import Revision
from src.engine_v2.llm.adapter import FakeInferenceBackend, FixedMonotonicClock

#: 脚本钉面（测试侧常量）：键 = (logical_role, base_revision, 调用序号)；
#: 值 = 脚本回应 JSON（character 策略 capability 同串约定
#: ``npc_policy``；W1 t2/t3 消费）。
_SCRIPT_KEY = ("npc_policy", Revision(3), 1)
_SCRIPT_TEXT = (
    '{"action_id": "talk", "arguments": {"target": "player"},'
    ' "intent": "greet", "confidence": 0.9}'
)


class SeededRng:
    """确定性随机源（仅测试侧；实现 P5 ``DslRng`` Protocol 三方法口径）。

    - ``rand()`` → [0, 1) float；
    - ``uniform(lo, hi)`` → float；
    - ``randint(lo, hi)`` → 闭区间 int。

    底层 = stdlib ``random.Random``（固定 seed；测试代码允许 import
    random——src 不允许，确定性纪律的测试侧注脚）。
    """

    def __init__(self, seed: int = 20240501) -> None:
        self._random = random.Random(seed)

    def rand(self) -> float:
        return self._random.random()

    def uniform(self, lo: float, hi: float) -> float:
        return self._random.uniform(lo, hi)

    def randint(self, lo: int, hi: int) -> int:
        return self._random.randint(lo, hi)


@pytest.fixture
def fixed_clock() -> FixedMonotonicClock:
    """D6 注入时钟（后置自增：首次 ``now_ms()`` = 0）。"""
    return FixedMonotonicClock(start_ms=0, step_ms=1)


@pytest.fixture
def scripted_backend() -> FakeInferenceBackend:
    """脚本化 backend（钉死脚本映射；``calls`` 可供断言；未命中落
    default no-op 文本 ``{"action_id": null}``）。"""
    return FakeInferenceBackend(script={_SCRIPT_KEY: _SCRIPT_TEXT})


@pytest.fixture
def dsl_rng() -> SeededRng:
    """固定 seed ``DslRng``（t8/t9 确定性面；t12 = 零随机直引面，§3.17 D-α）。"""
    return SeededRng()
