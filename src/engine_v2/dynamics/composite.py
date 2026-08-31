"""P7-W4 fan-out 组合 dynamics backend（SOT §3.6，T04；2 exports，账本序 §8.2 钉死）。

``CompositeDynamics`` 是 **fan-out** 组合 backend：全部子 backend 以**同一输入**
（同 snapshot / stimuli / context）参与，输出按**子序拼接**；路由式 routing 留
P8+ 扩展位（MAY，本波不做）。零本地状态（除 last-run 诊断视图，D-P7-15）。

纪律（SOT §0.5/§3.0）：

- P7-INV-2：对 ``WorldDynamicsBackend`` Protocol 面**泛化调用**（零 backend
  类型 if/elif 分派）；
- K7：零墙钟 / 零随机 / 零模块级可变状态；子失败诊断 ``message`` 为**确定性
  文本**（含子 backend_id、触发诊断数、异常类型名——无时间戳 / 无指针 /
  无随机）；
- A7 弃权序前提：组合体**不改动**任何子 effect 字段（effect ``metadata``
  恒为 backend 产出的缺省 ``{}``）；
- D-P7-15：``diagnostics`` property = last-run 视图（simulate 入口重置）。
"""

from __future__ import annotations

from typing import Final

from src.engine_v2.core.effects import ProposedEffect
from src.engine_v2.dynamics.backend import (
    BackendMetadata,
    DynamicsContext,
    Stimulus,
    WorldDynamicsBackend,
    WorldSnapshot,
)
from src.engine_v2.dynamics.diagnostic import DynamicsDiagnostic

__all__ = ["CompositeDynamics", "determinism_join"]

#: 确定性格全序（SOT §3.1 ``DETERMINISM_CLASSES`` 逐字镜像；本模块闭集 import
#: 面不含该常量，P3 校验与 metadata 折叠共用此本地逐字元组——词法一致性由
#: 构造期 backend 校验 + 本模块 ValueError 纵深双重把守）。
_DETERMINISM_LATTICE: Final[tuple[str, ...]] = (
    "deterministic",
    "seeded",
    "nondeterministic",
)


def determinism_join(a: str, b: str) -> str:
    """确定性格 join（取最差；全序 deterministic < seeded < nondeterministic）。

    | a \\ b | deterministic | seeded | nondeterministic |
    |---|---|---|---|
    | deterministic | deterministic | seeded | nondeterministic |
    | seeded | seeded | seeded | nondeterministic |
    | nondeterministic | nondeterministic | nondeterministic | nondeterministic |

    任一输入 ∉ 闭集 → ``ValueError``（§2.8 P3：构造面纵深防御；组合 metadata
    折叠路径不触达——子 metadata 构造期已词表校验）。
    """
    for value in (a, b):
        if value not in _DETERMINISM_LATTICE:
            raise ValueError(
                f"determinism_join 输入必须 ∈ {_DETERMINISM_LATTICE}，"
                f"得到 {value!r}"
            )
    return _DETERMINISM_LATTICE[max(_DETERMINISM_LATTICE.index(a), _DETERMINISM_LATTICE.index(b))]


class CompositeDynamics:
    """fan-out 组合 dynamics backend（SOT §3.6 逐字）。

    - ``children``：子 backend 元组（``children=()`` 合法——§2.8 P1 空面）；
    - ``simulate``：逐子 ``simulate(snapshot, stimuli, context)``（同输入）→
      按子序拼接；子异常 或 子 last-run 诊断非空 → 每问题子**恰 1 条**
      ``p7.composite_child_failed``（severity=error、path=``composite_dynamics``、
      refs=子 backend_id、message 含子 backend_id + 触发诊断数——§2.8 P2）；
    - ``metadata()``：domains 排序去重并集 / determinism 折叠 join / fidelity
      ``"composite." + ".".join(子 fidelity)`` / 三布尔 and 折叠（空 children
      面 = P1：domains=()、determinism=格单位元、fidelity="composite"、
      三布尔 True）；
    - ``diagnostics``：last-run 视图（D-P7-15；simulate 入口重置）。
    """

    __slots__ = ("_children", "_diagnostics")

    def __init__(self, *, children: tuple[WorldDynamicsBackend, ...]) -> None:
        self._children = children
        self._diagnostics: tuple[DynamicsDiagnostic, ...] = ()

    def metadata(self) -> BackendMetadata:
        """组合 metadata（子 metadata 的格/并/and 聚合；SOT §3.6 公式）。"""
        child_metadata = tuple(child.metadata() for child in self._children)
        if not child_metadata:
            # P1 空 children 面：SOT 公式 ``"composite." + ".".join(...)`` 空时
            # 产生尾点，口径钉死为 "composite"（无尾点）。
            return BackendMetadata(
                backend_id="composite_dynamics",
                producer_id="composite_dynamics",
                domains=(),
                determinism="deterministic",
                implementation_type="composite",
                fidelity="composite",
                checkpointable=True,
                restorable=True,
                replayable=True,
            )
        domains: set[str] = set()
        for meta in child_metadata:
            domains.update(meta.domains)
        determinism = "deterministic"
        for meta in child_metadata:
            determinism = determinism_join(determinism, meta.determinism)
        return BackendMetadata(
            backend_id="composite_dynamics",
            producer_id="composite_dynamics",
            domains=tuple(sorted(domains)),
            determinism=determinism,
            implementation_type="composite",
            fidelity="composite." + ".".join(meta.fidelity for meta in child_metadata),
            checkpointable=all(meta.checkpointable for meta in child_metadata),
            restorable=all(meta.restorable for meta in child_metadata),
            replayable=all(meta.replayable for meta in child_metadata),
        )

    def simulate(
        self,
        snapshot: WorldSnapshot,
        stimuli: tuple[Stimulus, ...],
        context: DynamicsContext,
    ) -> tuple[ProposedEffect, ...]:
        """fan-out 求值：全部子同输入，输出按子序拼接（SOT §3.6）。"""
        self._diagnostics = ()
        collected: list[ProposedEffect] = []
        for child in self._children:
            child_id = child.metadata().backend_id
            try:
                collected.extend(child.simulate(snapshot, stimuli, context))
            except Exception as exc:  # 子失败隔离：诊断上浮，组合体不炸
                self._diagnostics = self._diagnostics + (
                    self._child_failed_diagnostic(
                        child_id,
                        len(child.diagnostics),
                        f"simulate raised {type(exc).__name__}",
                    ),
                )
                continue
            child_diagnostics = child.diagnostics
            if child_diagnostics:
                self._diagnostics = self._diagnostics + (
                    self._child_failed_diagnostic(
                        child_id,
                        len(child_diagnostics),
                        "last run reported diagnostics",
                    ),
                )
        return tuple(collected)

    @property
    def diagnostics(self) -> tuple[DynamicsDiagnostic, ...]:
        """last-run 诊断视图（D-P7-15）；首次 simulate 前 = 空。"""
        return self._diagnostics

    @staticmethod
    def _child_failed_diagnostic(
        child_id: str, triggered_count: int, trigger: str
    ) -> DynamicsDiagnostic:
        """``p7.composite_child_failed`` 单条装配（§2.8 P2 字段面钉死）。

        ``message`` 确定性文本：含子 backend_id + 触发诊断数 + 触发描述
        （异常类型名 / last-run 诊断上浮标记）——零时间戳 / 零指针 / 零随机。
        """
        return DynamicsDiagnostic(
            code="p7.composite_child_failed",
            severity="error",
            path="composite_dynamics",
            message=(
                f"composite child '{child_id}' {trigger} "
                f"(triggered diagnostics: {triggered_count})"
            ),
            refs=(child_id,),
        )
