"""engine_v2 core 层逻辑时钟值类型与唯一时钟写点（P3-T01）。

依据 ``docs/v2/contracts/P3-scheduler-time-action-design.md``（下称"设计文档"）：

- §2.2 / D-P3-01：1 tick ≙ 1 世界分钟（默认映射）；core 层**单位无关**，
  只计数 tick——换算常数归 P5 内容层，本模块不出现"分钟"字面量、不做任何
  单位换算；
- §2.3 / D-P3-02：:class:`LogicalClock` 是 **Revision 同款的值类型**
  （typed 值、无状态引用，``revision.py`` 先例）——权威时钟恒为冻结字段
  ``RuntimeState.logical_tick``（P1 D-6 单一单调计数，``state.py:218``）；
  本对象不是第二权威，仅作派生视图与纯计算，经 ``LogicalClock.of(runtime)``
  投影、经 :func:`set_logical_tick` 写回，生命周期不超出一次纯函数求值；
- §3.3（P3-T01 全量）：唯一时钟写点 :func:`set_logical_tick`（重建模式，
  ``tick < 当前`` → :class:`ClockRollbackError`）、fast-forward 终点判据
  :func:`next_due_tick`（最小 ``due_tick``；队列空 → ``None``，§2.4）、
  ``RuntimeState`` 重建公共缝隙 :func:`rebuild_runtime`，以及 **P3 错误基类
  族宿主**（D-P3-16：P3 全部 7 类异常型错误继承 :class:`SchedulerError`，
  基类置依赖叶模块 ``clock.py`` 避免跨模块环）。

纪律（设计文档 §0.3 继承 / §8.3 P3 专项）：

- **单调**（D-P3-02）：``set_logical_tick`` 是调度器**唯一**时钟写点；
  回退只允许发生在状态级 restore（整对 ``(world, runtime)`` 从快照还原，
  ``snapshot.py``，不经时钟函数）；
- **无墙钟**：只 import stdlib + pydantic + 同包 ``src.engine_v2`` core
  既有模块；P3 专项黑名单 ``datetime`` / ``time`` / ``random`` / ``asyncio``
  对本模块生效（§8.3；暂停期间逻辑时间冻结——墙钟不可复现）；
- **可序列化**：时钟是 ``RuntimeState`` 内的 int，``dump_json`` /
  ``load_json`` round-trip 恒等（P1 ``serialization.py`` 基础设施，零新增）；
  :class:`LogicalClock` 自身也是 ContractModel（round-trip 可测）；
- **与 revision 解耦**（P2 D-P2-18 原文）：tick 推进**不**推进
  ``world_revision``——本模块只写 ``logical_tick``，不触碰世界状态。
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.state import RuntimeState

__all__ = [
    "LogicalClock",
    "set_logical_tick",
    "next_due_tick",
    "rebuild_runtime",
    "SchedulerError",
    "ClockRollbackError",
]


class SchedulerError(ValueError):
    """P3 错误基类（设计文档 §3.3 / D-P3-16"可检查不静默"）。

    P3 全部异常型错误（``UnknownActionError`` / ``IllegalTransitionError`` /
    ``QueueInvariantError`` / ``ClockRollbackError`` / ``UnknownConditionError``
    / ``SchedulerConfigurationError`` / ``SchedulerWakeupError``）继承本类；
    继承 ``ValueError`` 与 P1/P2 词法/数据校验错误族统一（P2 异常族体例，
    ``reducer.py`` ReducerError 先例）。"可检查不静默"：每类失败要么抛可捕获
    异常、要么落在可序列化记录里，无第三条路——数据结果类失败（stale 提案 /
    边界命中）走 P1 词表，不新增异常类型。
    """


class ClockRollbackError(SchedulerError):
    """逻辑时钟回退尝试（设计文档 §2.3 / D-P3-02）。

    时钟单调非降：``set_logical_tick(runtime, tick)`` 传 ``tick <
    runtime.logical_tick``、或 :meth:`LogicalClock.advanced` 传负
    ``delta_ticks``，均抛本错误（信息含 from/to）。restore（整对
    ``(world, runtime)`` 从快照还原）是唯一合法回退通道，不经时钟函数。
    """


class LogicalClock(ContractModel):
    """逻辑时钟值类型（Revision 模式，D-P3-02）。

    不是第二权威：任何时刻权威值 = RuntimeState.logical_tick（K1 同源
    纪律）；本对象仅作派生视图与纯计算，经 LogicalClock.of(runtime) 投影、
    经 set_logical_tick 写回，生命周期不超出一次纯函数求值。
    """

    tick: int = Field(ge=0)

    @classmethod
    def of(cls, runtime: RuntimeState) -> "LogicalClock":
        """投影（新增，§2.3）：由权威值 ``runtime.logical_tick`` 构造派生视图。

        每次调用重新投影——``RuntimeState`` 不可变，投影即当前权威值本身
        （恒等口径：``LogicalClock.of(runtime).tick == runtime.logical_tick``）。
        """
        return cls(tick=runtime.logical_tick)

    def elapsed(self, since_tick: int) -> int:
        """自 ``since_tick`` 起的经过 tick 数：``max(0, tick - since_tick)``。

        下界钳 0（§2.3：``since_tick`` 晚于当前刻不产生负值）。
        """
        return max(0, self.tick - since_tick)

    def advanced(self, delta_ticks: int) -> "LogicalClock":
        """返回前移 ``delta_ticks`` tick 的**新**时钟（值类型，self 不变）。

        ``delta_ticks >= 0``，否则 :class:`ClockRollbackError`（单调性，
        D-P3-02；信息含 from/to）。
        """
        if delta_ticks < 0:
            raise ClockRollbackError(
                f"logical clock rollback: from={self.tick} "
                f"to={self.tick + delta_ticks} (delta={delta_ticks})"
            )
        return type(self)(tick=self.tick + delta_ticks)


def set_logical_tick(runtime: RuntimeState, tick: int) -> RuntimeState:
    """唯一时钟写点（§3.3 / D-P3-02）：返回 ``logical_tick`` 替换为 ``tick`` 的
    新 ``RuntimeState``（重建模式，self 不变）。

    - ``tick < runtime.logical_tick`` → :class:`ClockRollbackError`（信息含
      from/to）；回退只允许发生在状态级 restore（整对从快照还原），不经本函数；
    - ``tick == 当前`` 合法（幂等 no-op，仍返回新实例）；
    - fast-forward 的核心原语（§2.4 / D-P3-03）：``t > 当前`` 时一步跳变到
      ``t``，不逐 tick 迭代；
    - 内部经 :func:`rebuild_runtime`（P3 全部 RuntimeState 簿记变更统一经此）。
    """
    current = runtime.logical_tick
    if tick < current:
        raise ClockRollbackError(
            f"logical clock rollback: from={current} to={tick} "
            "（单调时钟；唯一合法回退是状态级 restore）"
        )
    return rebuild_runtime(runtime, logical_tick=tick)


def next_due_tick(runtime: RuntimeState) -> int | None:
    """调度队列最小 ``due_tick``（§3.3 / §2.4 fast-forward 终点判据）。

    队列空 → ``None``（无更多调度工作，确定性终点）；否则为
    ``scheduler_queue[*].due_tick`` 的最小值——队列经写时稳定排序（D-P3-05）
    任意时刻保持 ``(due_tick, 插入序)`` 全序，时钟跳变后本值与队列最小值
    恒等（对抗 A4 的可断言口径）。
    """
    queue = runtime.scheduler_queue
    if not queue:
        return None
    return min(entry.due_tick for entry in queue)


def rebuild_runtime(runtime: RuntimeState, **updates: Any) -> RuntimeState:
    """RuntimeState 重建公共缝隙（P1 state.py:213-214 授权的行为侧实现）：model_dump() →
    dict 更新 → model_validate()——走 P1 唯一合法序列化路径（serialization.py 规则 1），
    不触碰 P2 写屏障四逃逸路径；重跑 active_actions 键一致性 model_validator。
    P3 全部 RuntimeState 簿记变更统一经此函数。"""
    payload = runtime.model_dump()
    payload.update(updates)
    return RuntimeState.model_validate(payload)
