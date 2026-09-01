"""P9 W6 官方模块：tactical（T13；SOT §3.12 L791–813；导出 4 名）。

来源 = Spec §40 tactical 模块 + Spec §25 GameplayMode/GameplayContext
（L1396–1452）冻结面（core ``gameplay_mode``）；v1 无对应物（v2 新
模块）。

冻结消费（SOT §2.1/§2.4）：core ``gameplay_mode``（``ModeOperation``:109
/ ``ModeOperationKind``:102 / ``ModeOverlay``:150 /
``ModeOverlayRegistry``:203 / ``MergedModeConfiguration``:241 /
``merge_modes``:266 / ``is_action_available``:340 /
``ModeChangeRequest``:396 / ``ModeChangeResolution``:439 /
``ModePolicy``:456 / ``apply_mode_change``:475）；core ``actions``
（``parse_action_type_id``:98）；core ``state``（``RuntimeState``:192）；
模块公共面 ``modules.base``。

``TacticalModePolicy`` 拒绝语义（core 对齐面，此处钉死）：core 既有
异常族 = ``ModeInvariantError``（构造期不变量）/ ``UnknownModeError``
（查找点）——均不表达「转移被策略拒绝」。拒绝面钉定 core 既有
``ModeChangeResolution`` 判定面（:439）：请求含任一被拒操作 → 整请求
原子拒绝——全部操作进 ``ignored``（请求序）、``applied = ()``、
``new_active_modes`` / ``new_mode_context`` = 当前 runtime 值（零
变更），直接返回 resolution，不调用 ``apply_mode_change``；全部操作
允许 → 委托 ``apply_mode_change``（:475）解析。

纪律（K2/D6/K8）：全纯函数 / 零直写（模式变更 = core 冻结执行器单写
面）；零 wall-clock / 全局 RNG；零推理消费；12 名闭集零命中。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from src.engine_v2.core.actions import parse_action_type_id
from src.engine_v2.core.gameplay_mode import (
    ModeChangeRequest,
    ModeChangeResolution,
    ModeOperation,
    ModeOperationKind,
    ModeOverlay,
    ModeOverlayRegistry,
    apply_mode_change,
)
from src.engine_v2.core.state import RuntimeState
from src.engine_v2.modules.base import OFFICIAL_MODULE_VERSION, ModuleIdentity

__all__ = [
    "TACTICAL_ACTION_IDS",
    "TacticalOverlaySpec",
    "build_tactical_overlay",
    "TacticalModePolicy",
]

#: 模块身份（SOT §3.1.2 requires 表 L490：tactical = (actions,
#: space)——战术模式限动作集 + 战术移动）。
IDENTITY: Final[ModuleIdentity] = ModuleIdentity(
    "llmsim-standard-tactical",
    OFFICIAL_MODULE_VERSION,
    ("llmsim-standard-actions", "llmsim-standard-space"),
)

#: 战术模式动作集（SOT §3.12 表行 1，逐字 5 名；参考集——项目可经
#: ``GameplayModeSpec``（content/schemas.py:386）覆盖）。
TACTICAL_ACTION_IDS: Final[tuple[str, ...]] = (
    "move", "attack", "reload", "take_cover", "wait",
)

#: overlay 缺省 priority（战术约束层 > 基线层；winner 语义 = core
#: D-P4-14，gameplay_mode.py:241–266）。
_DEFAULT_OVERLAY_PRIORITY: Final[int] = 10


@dataclass(frozen=True)
class TacticalOverlaySpec:
    """overlay 声明（SOT §3.12 表行 2；字段逐字钉定）。

    ``mode_id`` 文法 = core ``ModeOverlay``:150 构造期 pattern
    （``^[a-z][a-z0-9_]*$``；违例经 :func:`build_tactical_overlay`
    构造期拒绝透传）。
    """

    mode_id: str
    available_actions: tuple[str, ...]
    description: str = ""


def build_tactical_overlay(spec: TacticalOverlaySpec) -> ModeOverlay:
    """纯构建（SOT §3.12 表行 3；core ``ModeOverlay``:150 冻结面）。

    - ``available_actions`` 逐个经 ``parse_action_type_id``（core
      actions.py:98）校验，文法违例 → 其异常透传（ValueError 族，
      不包裹、不吞）；
    - ``action_filter_kind = "allow"``（动作集限定语义；M-INV-1：
      allow ⇒ ``action_ids`` 非空——``available_actions`` 空元组 →
      core 构造期 ``ModeInvariantError`` 透传）；
    - ``priority = 10``（缺省，本模块钉定）；``context`` =
      ``{"description": spec.description}``（不透明载荷，P8 表现层
      消费）；其余字段缺省。
    """
    for action_id in spec.available_actions:
        parse_action_type_id(action_id)
    return ModeOverlay(
        mode_id=spec.mode_id,
        priority=_DEFAULT_OVERLAY_PRIORITY,
        action_filter_kind="allow",
        action_ids=spec.available_actions,
        context={"description": spec.description},
    )


def _op_label(op: ModeOperation) -> str:
    """操作字符串标签（core 钉定形态，gameplay_mode.py:444：
    ``"activate:<mode_id>"`` 形态，请求序）。"""
    return f"{op.operation_kind.value}:{op.mode_id}"


class TacticalModePolicy:
    """战术模式转移策略（SOT §3.12 表行 4；A15 主面）：实现 core
    ``ModePolicy``（gameplay_mode.py:456 Protocol——``resolve(request,
    registry, runtime) -> ModeChangeResolution``）。

    转移语义（本模块钉定）：

    - 战术 → 探索（deactivate 一个已激活战术模式）：允许；
    - 探索 → 战术（activate 战术模式，且当前无**其他**战术模式
      激活）：允许（宿主经 ``ModeChangeRequest``:396 驱动）；
    - 战术内子模式转移（已有某战术模式激活时 activate **另一**战术
      模式）：拒绝；
    - 非战术模式操作：不属本策略域 → 透传 core
      ``apply_mode_change``（:475）。

    拒绝语义 = core 既有 resolution 面（模块 docstring 钉死）：任一
    操作被拒 → 整请求原子拒绝（全部操作 → ``ignored``、``applied =
    ()``、runtime 零变更，不调用 ``apply_mode_change``）。

    构造：``TacticalModePolicy(tactical_mode_ids=("tactical",))``——
    战术模式 id 闭集（fixture 面 = 单 id；多 id = 战术子模式面，
    两两互斥）。
    """

    def __init__(
        self,
        tactical_mode_ids: tuple[str, ...] = ("tactical",),
    ) -> None:
        if not tactical_mode_ids:
            raise ValueError("tactical_mode_ids 必须非空")
        self.tactical_mode_ids: Final[tuple[str, ...]] = tuple(
            tactical_mode_ids
        )

    def resolve(
        self,
        request: ModeChangeRequest,
        registry: ModeOverlayRegistry,
        runtime: RuntimeState,
    ) -> ModeChangeResolution:
        """解析模式变更请求（core ``ModePolicy``:456 方法面）。"""
        active_tactical = {
            mode_id
            for mode_id in runtime.active_modes
            if mode_id in self.tactical_mode_ids
        }
        rejected = False
        for op in request.operations:
            if op.mode_id not in self.tactical_mode_ids:
                continue
            if (
                op.operation_kind == ModeOperationKind.ACTIVATE
                and active_tactical
                and op.mode_id not in active_tactical
            ):
                rejected = True
                break
        if rejected:
            return ModeChangeResolution(
                effects=(),
                new_active_modes=runtime.active_modes,
                new_mode_context=dict(runtime.mode_context),
                applied=(),
                ignored=tuple(_op_label(op) for op in request.operations),
            )
        return apply_mode_change(
            request=request, runtime=runtime, registry=registry
        )[1]
