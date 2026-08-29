"""engine_v2 core 层行为策略协议与策略执行门面（P4-T01，§3.9）。

依据 ``docs/v2/contracts/P4-actor-context-space-mode-design.md``（下称"设计文档"）：

- **§3.9（全量，权威）**：本模块 4 个导出符号，逐字——:class:`BehaviorPolicy`
  （Protocol；B-CON-1~5 逐条落位）/ :class:`PlayerPolicy`（纯标记协议 +
  ``bound_input_source`` 不透明标签）/ :func:`run_policy_decide`（策略执行门面，
  唯一执行点）/ :class:`PolicyActorMismatchError`（B-CON-5，ValueError 族）；
- **§3.9 末尾单测口径（L583）**：B-CON-1~5 机械断言（合规类通过 + 异步 decide
  拒绝 + 双参数签名拒绝 + actor 错配拒绝 + None 合法）；``run_policy_decide``
  异常传播（policy 抛 ValueError → 门面不包装、原样上抛）；base 漂移不拦
  （构造 stale base 提案 → 门面放行——REJECT 归 revalidation，与 A7b 呼应）；
- **§3.3 依赖图（L177）+ L183 零边条款**：behavior_policy → actions
  （ActionProposal，**运行期**）/ context_provider（ActorDecisionContext，
  **仅 TYPE_CHECKING**——house 模式，运行时零 import，见下 import 块）；
  behavior_policy **不** import reducer / scheduler（context 已物化，D-P4-05；
  K5：policy 无调度权），亦不 import state / capability / knowledge / space /
  provenance / components / effects（§3.4 黑名单，全部 ✗）；
- **D-P4-01**：``decide`` 同步化（偏离 D1）——返回 ``ActionProposal | None``，
  None = 合法 no-op（不产提案、不进流水线、不产 trace 失败记录）；云模型异步性
  属 P5 实现细节，经同步门面收敛（§3.4 确定性纪律）；
- **D-P4-02**：:class:`PlayerPolicy` = 纯标记（不新增必选方法）；
  ``bound_input_source: str | None`` 不透明标签（JSON-clean；P4 不解释其内容；
  K4：输入策略归属呈现层配置，策略不自我声明）；
- **D-P4-03**：策略缝只强制 ``actor_id``——``base_world_revision`` 漂移
  **不预检**：stale 判定唯一属 revalidation 门（scheduler.py:1661-1663），门面
  预检 = 双份事实源（KBC-3 反模式）；
- **D-P4-08**：capability ⊥ authority（双门正交）——缝不门控写授权：capability
  只门控策略在 context 构建时**能看见**什么，写授权唯一归 P2 authority；
- **D-P4-17**：错误分类两族——:class:`PolicyActorMismatchError` 属
  **ValueError 族**（输入/不变式违反），沿用 P1/P2/P3 既有二族风格。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from src.engine_v2.core.actions import ActionProposal

if TYPE_CHECKING:  # 仅注解用（house 模式，scheduler.py 同款；运行时零 import）
    from src.engine_v2.core.context_provider import ActorDecisionContext

__all__ = [
    "BehaviorPolicy",
    "PlayerPolicy",
    "run_policy_decide",
    "PolicyActorMismatchError",
]


# —— BehaviorPolicy / PlayerPolicy 协议（设计文档 §3.9 L544-564 逐字）——


class BehaviorPolicy(Protocol):
    """行为策略协议（Spec:818-825 的同步落地，D-P4-01 / 偏离 D1）。

    **B-CON 逐条**（单测机械断言面）：
    - B-CON-1：``decide`` 为同步方法（非协程函数——``inspect.iscoroutinefunction``
      为 False；云模型异步性属 P5 实现细节，经同步门面收敛，§3.4 确定性纪律）；
    - B-CON-2：签名 = 单参数 ``context``（ActorDecisionContext）；
    - B-CON-3：返回 ``ActionProposal | None``（None = 本 tick 不提案，合法）；
    - B-CON-4：policy 实例不持有 random/时钟/网络面（单测静态扫描类体 import 面）；
    - B-CON-5：返回提案的 ``actor_id`` 必须 == ``context.actor_id``
      （门面执行，D-P4-03；capability ⊥ authority，D-P4-08——缝不门控写授权；违规 = 越权代言，K5 数据面防线）。
    """

    def decide(self, context: "ActorDecisionContext") -> "ActionProposal | None": ...


class PlayerPolicy(BehaviorPolicy):
    """玩家策略标记协议（Spec:833 PlayerPolicy 变体；D-P4-02）。

    结构面 = BehaviorPolicy + ``bound_input_source: str | None``（不透明标签
    （JSON-clean）；P5 接线真实输入设备/网络输入，P4 只定契约不定实现）。
    """

    bound_input_source: str | None


# —— 策略执行门面（唯一执行点）+ 缝错误（设计文档 §3.9 L566-581 逐字）——


def run_policy_decide(
    policy: BehaviorPolicy, context: ActorDecisionContext
) -> ActionProposal | None:
    """策略执行门面（唯一执行点；P4 集成路径全部经此）。

    次序钉死：1. ``proposal = policy.decide(context)``——policy 抛出的任何
    异常**原样传播**（不包装——wakeup 侧由 P3 既有 ``SchedulerWakeupError``
    机制捕获，scheduler.py:1174-1177；非 wakeup 调用方自行负责）；
    2. None → 返回 None；3. ``proposal.actor_id != context.actor_id`` →
    :class:`PolicyActorMismatchError`（B-CON-5 / D-P4-03）；4. 返回 proposal。
    **不检查** ``base_world_revision`` 漂移——stale 判定唯一属 revalidation
    （scheduler.py:1661-1663），门面预检 = 双份事实源（KBC-3 反模式）。
    """
    proposal = policy.decide(context)
    if proposal is None:
        return None
    if proposal.actor_id != context.actor_id:
        raise PolicyActorMismatchError(
            f"策略代言了非上下文的 actor（B-CON-5 / D-P4-03）： "
            f"proposal.actor_id={proposal.actor_id!r} != context.actor_id={context.actor_id!r}"
        )
    return proposal


class PolicyActorMismatchError(ValueError):
    """B-CON-5：策略代言了非上下文的 actor。"""
