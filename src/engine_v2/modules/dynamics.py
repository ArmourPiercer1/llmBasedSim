"""P9 W7 官方模块：dynamics（T12；SOT §3.13；导出 2 名）。

来源 = P7 冻结 dynamics kernel（``engine_v2.dynamics`` 8 模块；SOT §2.2
冻结消费表）+ P9 桥接装配（本模块零新增 dynamics 逻辑，D-P9-12）：

- ``DynamicsBinding`` = backend + 驱动闭包（宿主协议：``turn(world,
  tick) -> Sequence[ProposedEffect]``，W6 ``p9_host.set_dynamics``
  接缝面，DEV-W6-3 项 3）；
- ``build_standard_dynamics`` = P7 ``CompositeDynamics`` 标准装配
  （composite.py:66 冻结面）：规则子在前（优先）、推理子在后（补位）；
  ``weight`` = 声明仲裁参数（SOT §3.13 签名槽位），P7 composite 冻结
  面 = 子序 fan-out，不消费该参数（零新 dynamics 逻辑）。

冻结消费（SOT §2.2）：``engine_v2.dynamics.{backend, composite,
llm_world, rule}`` + 模块公共面 ``modules.base``。

纪律（K7/D6）：零墙钟 / 零 uuid / 零随机源 / 零 time-datetime 导入；
零模块级可变对象；``turn`` 闭包 = 纯委托 backend（不修改入参、无中间
状态，K2）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from src.engine_v2.core.effects import ProposedEffect
from src.engine_v2.core.state import WorldState
from src.engine_v2.dynamics.backend import (
    DynamicsContext,
    WorldDynamicsBackend,
    WorldSnapshot,
)
from src.engine_v2.dynamics.composite import CompositeDynamics
from src.engine_v2.dynamics.llm_world import LLMWorldDynamics
from src.engine_v2.dynamics.rule import RuleDynamics
from src.engine_v2.modules.base import OFFICIAL_MODULE_VERSION, ModuleIdentity

__all__ = ["DynamicsBinding", "build_standard_dynamics"]

#: 模块身份（SOT §3.1.2 MODULE_REQUIRES 表：dynamics = 冻结 kernel 根，
#: requires = ()，不计入模块图边）。
IDENTITY: Final[ModuleIdentity] = ModuleIdentity(
    "llmsim-standard-dynamics", OFFICIAL_MODULE_VERSION, (),
)

#: 驱动闭包快照信封身份（D-9：instance 身份在信封层；确定性常量，K7）。
_WORLD_INSTANCE_ID: Final[str] = "p9.standard_dynamics"


@dataclass(frozen=True)
class DynamicsBinding:
    """dynamics 驱动绑定（SOT §3.13 表行 1）。

    - ``backend``：任意 ``WorldDynamicsBackend`` Protocol 实现（结构性
      满足，零类型分派，P7-INV-2 同纪律）；
    - ``turn``：宿主驱动协议闭包——``turn(world, tick) ->
      Sequence[ProposedEffect]``（W6 ``p9_host.set_dynamics`` 接缝面）；
      闭包 = 纯委托 ``backend.simulate``（快照 / 上下文自当前 world +
      逻辑刻现构，零中间状态，K2）。
    """

    backend: WorldDynamicsBackend
    turn: Callable[[WorldState, int], Sequence[ProposedEffect]]


def _make_turn(
    backend: WorldDynamicsBackend,
) -> Callable[[WorldState, int], Sequence[ProposedEffect]]:
    """驱动闭包构造（私有面）：``(world, tick) -> backend.simulate``
    纯委托（K2：闭包不修改 world 入参；零中间状态，双刻同 world →
    输出仅由 backend 语义决定，K7）。"""

    def turn(world: WorldState, tick: int) -> Sequence[ProposedEffect]:
        snapshot = WorldSnapshot(
            world_state=world,
            world_revision=world.world_revision,
            logical_tick=tick,
            world_instance_id=_WORLD_INSTANCE_ID,
        )
        context = DynamicsContext(base_revision=int(world.world_revision))
        return backend.simulate(snapshot, (), context)

    return turn


def build_standard_dynamics(
    rule_backend: RuleDynamics,
    llm_backend: LLMWorldDynamics,
    weight: float = 0.5,
) -> DynamicsBinding:
    """P9 标准装配（SOT §3.13 表行 2；P7 composite.py:66 冻结面装配，
    零新增 dynamics 逻辑，D-P9-12）。

    - 装配 = ``CompositeDynamics(children=(rule_backend, llm_backend))``
      ：规则子在前（优先）、推理子在后（补位）——子序 fan-out 拼接（P7
      冻结语义，test_composite t1 面）；
    - ``weight`` = 声明仲裁参数（SOT §3.13 签名槽位）：P7 composite
      冻结面不消费该参数（无仲裁逻辑）——仅机械类型检查（bool / 非
      float 拒绝），语义以 P7 composite 冻结面为准；
    - 返回 = ``DynamicsBinding(backend=composite, turn=composite 驱动
      闭包)``；闭包对 composite 纯委托（simulate 逐子求值序 = 子序）。
    """
    if isinstance(weight, bool) or not isinstance(weight, float):
        raise ValueError(
            f"weight 必须为 float（声明仲裁参数；bool / 非 float 拒绝）："
            f"{weight!r}"
        )
    composite = CompositeDynamics(children=(rule_backend, llm_backend))
    return DynamicsBinding(backend=composite, turn=_make_turn(composite))
