"""P6-W5 T07（SOT §3.7）：stale 处理接线 = 委托既有 revalidation 管线。

定位（Leader-A2 消歧后的 T07 真实落点）：P6 不重复实现 stale 判定——只
① 计算 ``valid_until`` 上界（TTL 从 context 基线推导，非异步 time 语义）
与 ② 消费既有 revalidation 语义（``core.revision.RevalidationOutcome``
四值冻结词表 + ``core.revalidation.RevalidationDecision``）；stale 判定
权唯一归 revalidation（Spec §9 L669「提交前 MUST 执行 revalidation」），
P6 越权拦截 = 重复状态面，禁止（G6-4 机械断言的消费前提）。

消费链（#10 语义面）：policy 产出提案 → 宿主（wake-up 钩子）
``scheduler.submit_proposal``（revalidation → ACCEPT 入队 / REJECT 置
FAILED）→ P6 侧 ``handle_result`` 只把 decision 结局规范化为大写规范串、
``is_acceptable`` 只判可提交性——只做记录不干预、绝不自动重提交（REBASE
的 rebased 提案由宿主提交，#10 面）。

模块纪律（SOT §3.7）：零 I/O、纯函数、同步面；只 import core 冻结面
（revision/revalidation 类型）；零非确定根源。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from src.engine_v2.core.revision import Revision

if TYPE_CHECKING:
    from src.engine_v2.core.actions import ActionProposal
    from src.engine_v2.core.context_provider import ActorDecisionContext
    from src.engine_v2.core.revalidation import RevalidationDecision

__all__ = [
    "COMMITTABLE_OUTCOMES",
    "effective_valid_until",
    "handle_result",
    "is_acceptable",
]

#: 可提交的 revalidation 结局（SOT §3.7；revalidation.py:63-104 +
#: revision.py:91 词表）：ACCEPT（原提案照提交）/ REBASE（以 rebased
#: 提案提交）。REPAIR / REJECT = 不可提交。
COMMITTABLE_OUTCOMES: Final[frozenset[str]] = frozenset({"ACCEPT", "REBASE"})


def effective_valid_until(
    context: ActorDecisionContext, ttl_ticks: int | None
) -> Revision | None:
    """从 context 基线推导 ``valid_until`` 上界（SOT §3.7）。

    - ``ttl_ticks is None`` → ``None``（无显式上界，纯靠 base 对比 + 提交
      期 revalidation 拦截，Spec §9 L656 optional 语义）；
    - 否则 → ``Revision(context.base_world_revision + ttl_ticks)``（TTL 从
      context 基线起算）；
    - ``ttl_ticks`` 0 / 负 = 输入违例 → ``ValueError``（``≥1`` 由调用方
      保证，本函数不静默接纳）。

    语义钉死：``is_stale``（revision.py:78-88）既有口径——base < current
    → stale；current > valid_until → stale；current == valid_until → 不
    stale（边界含等号，revision.py:88 口径原样消费，P6 不发明第二套）。
    """
    if ttl_ticks is None:
        return None
    if ttl_ticks < 1:
        raise ValueError(f"ttl_ticks 必须 ≥1（got {ttl_ticks}）")
    return Revision(context.base_world_revision + ttl_ticks)


def handle_result(decision: RevalidationDecision, proposal: ActionProposal) -> str:
    """revalidation decision 结局 → 大写规范串（SOT §3.7）。

    映射面 = Spec §9 L673-677 规范四值："ACCEPT" / "REBASE" / "REPAIR" /
    "REJECT"（``RevalidationOutcome.name``——词表 ``.value`` 为小写，本
    函数只做 case 面规范化，不重发明映射）。

    ``proposal`` 为被判定提案（#10 消费链面，宿主对称日志透传）；本函数
    只读 ``decision`` 不做干预：REBASE 时 ``decision.rebased_proposal``
    非 None（构造期不变量，revalidation.py:91），rebased 提案由宿主提交
    ——P6 不自动重提交（#10 面）。
    """
    return decision.outcome.name


def is_acceptable(outcome: str) -> bool:
    """可提交判定：``outcome ∈ COMMITTABLE_OUTCOMES``（SOT §3.7）。"""
    return outcome in COMMITTABLE_OUTCOMES
