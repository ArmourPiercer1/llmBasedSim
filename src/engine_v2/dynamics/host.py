"""P7-W4 host driver（SOT §3.8，D-P7-09；2 exports，账本序 §8.2 钉死）。

``run_dynamics_turn`` 是 **P7 自持组装点**（SOT §2.4 调度器扩展点核验结论：
scheduler 无 dynamics 入口 → host driver 方案）：

1. ``effects = backend.simulate(snapshot, stimuli, context)``；
2. ``result = executor.run(effects, state, causal_root_id=..., origin=...)``
   （state 纯函数不被触碰——cascade 纯函数纪律）；
3. 聚合 ``backend.diagnostics``（last-run 视图，D-P7-15）→ ``DynamicsTurn``。

纪律（SOT §0.5/§3.0）：零 asyncio；零 backend 类型 if/elif 分派（对
``WorldDynamicsBackend`` Protocol 面泛化调用——P7-INV-2 机械口）；K6 事务级
溯源 = host 构造的 ``origin``（``OriginKind.DYNAMICS_BACKEND``）贯穿本 turn
全部事务与事件。

``DynamicsTurn.summary_dict()`` = JSON-clean 汇总面（ERR-P6-10(a) 机械断言
内嵌）：顶层恰 3 键 ``effects`` / ``result`` / ``diagnostics``；``CascadeResult``
为 plain dataclass（无 ``model_dump``）→ 成员手工装配，各成员
``model_dump(mode="json")``（唯一例外 ``CascadeDiagnostic`` 亦为 plain
frozen dataclass → 手工 dict 装配）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.engine_v2.core.cascade import CascadeExecutor, CascadeResult
from src.engine_v2.core.effects import ProposedEffect
from src.engine_v2.core.provenance import Provenance
from src.engine_v2.core.serialization import assert_json_clean
from src.engine_v2.core.state import WorldState
from src.engine_v2.dynamics.backend import WorldSnapshot
from src.engine_v2.dynamics.diagnostic import DynamicsDiagnostic

__all__ = ["run_dynamics_turn", "DynamicsTurn"]


@dataclass(frozen=True)
class DynamicsTurn:
    """一个完整 dynamics turn（simulate 产物 + cascade 结果 + backend 诊断）。

    - ``effects``：``backend.simulate`` 产物（本 turn 全部 ProposedEffect——
      含后续被 cascade 拒绝者，审计全量面）；
    - ``result``：``CascadeExecutor.run`` 结果（纯函数产物：final_state /
      transactions / events / trace_records / deferred / diagnostics）；
    - ``diagnostics``：backend last-run 诊断视图聚合（D-P7-15）。

    frozen：任何字段赋值 → ``dataclasses.FrozenInstanceError``（§2.6 P5）。
    """

    effects: tuple[ProposedEffect, ...]
    result: CascadeResult
    diagnostics: tuple[DynamicsDiagnostic, ...]

    def summary_dict(self) -> dict[str, Any]:
        """JSON-clean 汇总（§2.6 P5 形状钉死；``assert_json_clean`` 内嵌机械断言）。

        顶层 3 键：``effects`` / ``result`` / ``diagnostics``；``result`` 成员
        = ``final_state`` / ``transactions`` / ``events`` / ``trace_records`` /
        ``deferred`` / ``diagnostics``（逐项 ``model_dump(mode="json")``；
        ``CascadeDiagnostic`` 手工 dict：kind / depth / detail）。
        """
        result = self.result
        summary: dict[str, Any] = {
            "effects": [effect.model_dump(mode="json") for effect in self.effects],
            "result": {
                "final_state": result.final_state.model_dump(mode="json"),
                "transactions": [txn.model_dump(mode="json") for txn in result.transactions],
                "events": [event.model_dump(mode="json") for event in result.events],
                "trace_records": [
                    record.model_dump(mode="json") for record in result.trace_records
                ],
                "deferred": [effect.model_dump(mode="json") for effect in result.deferred],
                "diagnostics": [
                    {"kind": diag.kind, "depth": diag.depth, "detail": diag.detail}
                    for diag in result.diagnostics
                ],
            },
            "diagnostics": [diag.model_dump(mode="json") for diag in self.diagnostics],
        }
        assert_json_clean(summary)
        return summary


def run_dynamics_turn(
    *,
    backend,
    snapshot: WorldSnapshot,
    stimuli,
    context,
    state: WorldState,
    executor: CascadeExecutor,
    causal_root_id: str,
    origin: Provenance,
) -> DynamicsTurn:
    """host driver：一个 dynamics turn（SOT §3.8 三步钉死）。

    纯函数于输入（``state`` 不被触碰）；零 asyncio；零 backend 类型
    if/elif（Protocol 面泛化调用）。``origin`` 由 host 构造（
    ``origin.origin_kind`` = ``OriginKind.DYNAMICS_BACKEND``，K6 事务级
    溯源）；``causal_root_id`` 贯穿本 turn 全部事务/事件的因果树根。

    参数（全 keyword，SOT §3.8 签名逐字）：

    - ``backend``：任意 ``WorldDynamicsBackend`` Protocol 实现（无类型
      注解——P7-INV-2 泛化面）；
    - ``snapshot`` / ``stimuli`` / ``context``：simulate 三入参（同形透传）；
    - ``state``：cascade 初始世界状态（纯函数输入，不被触碰）；
    - ``executor``：host 装配的 ``CascadeExecutor``（policy / registry /
      handlers 均属 host——D-P7-08）；
    - ``causal_root_id`` / ``origin``：因果树根 + K6 溯源（host 钉死）。
    """
    effects = backend.simulate(snapshot, stimuli, context)
    result = executor.run(
        effects,
        state,
        causal_root_id=causal_root_id,
        origin=origin,
    )
    return DynamicsTurn(
        effects=effects,
        result=result,
        diagnostics=backend.diagnostics,
    )
