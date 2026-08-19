"""engine_v2 core 层 Transaction 原子提交的数据表达（P1-T04）。

依据 ``docs/v2/contracts/P1-core-data-contracts.md``（下称"设计文档"）：

- §1.1 本文件职责：``TransactionStatus`` / ``Transaction``；
- §5.6 原子提交语义（Spec §20.1）的**数据层表达**——四条不变量由
  :class:`Transaction` 的 ``model_validator`` 在构造/``model_validate`` 时强制，
  任何违反立即抛 pydantic ``ValidationError``（T06 以不变量用例固化）：

  1. ``status == COMMITTED`` ⇒ ``commit_revision == base_revision.next()``
     （唯一新版本，§20.1 "produce one world revision"），且 ``effects`` 必须
     非空（``len(effects) >= 1``）——空事务不产生状态变化，不应消耗 revision；
  2. ``status == ABORTED`` ⇒ ``commit_revision is None`` 且 ``effects == []``
     （**部分提交不可表达**——任何 effect 要么全体共享同一 ``commit_revision``，
     要么全体不落盘；这正是 §20.1 atomic commit 的数据形态，也是 Plan P2 必须
     测试的"transaction 中一项 invalid → atomic failure"的契约基础）；
  3. ``effects[*].sequence`` 在事务内唯一且自 0 连续（reducer 确定性，§20.2）；
  4. 一次 COMMITTED transaction 使 ``world_revision`` 恰 +1（Spec §9）——
     reducer 行为在 P2，P1 以字段契约与测试桩保证该语义**可表达且仅可如此
     表达**（不变量 1 的 ``commit_revision == base_revision + 1`` 即其唯一
     数据形态）。

  另按 §7.4 C5（CommittedEffect 一致性）强制：事务内全部 effects 共享同一
  ``transaction_id`` / ``commit_revision``（与 :class:`Transaction` 自身字段
  一致）；按 §9 v1 陷阱规避表（KBC-2 重复累加）强制：事务内 ``effect_id``
  唯一（重复 ID 在数据层即被拒绝，而非仅"可检测"）。

reducer 行为（``apply_transaction(state, txn) -> WorldState``）属 Plan P2-T06；
P1 只落数据契约（设计文档 §8 非目标 5）。本模块只 import pydantic 与同包
``src.engine_v2``（§0.3 import 边界白名单），不触碰 v1。
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from src.engine_v2.core.effects import CommittedEffect
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.ids import EventId, TransactionId
from src.engine_v2.core.provenance import CascadeContext, Provenance
from src.engine_v2.core.revision import Revision

__all__ = [
    "TransactionStatus",
    "Transaction",
]


class TransactionStatus(str, Enum):
    """事务状态（设计文档 §5.6；Spec §20.1）。

    仅两态：提交成功（COMMITTED）或原子失败（ABORTED）。枚举一律
    ``class Xxx(str, Enum)``，JSON 值为字符串字面量（设计文档 §0.1）。
    """

    COMMITTED = "committed"
    ABORTED = "aborted"


class Transaction(ContractModel):
    """原子提交单元的数据表达（设计文档 §5.6；Spec §20.1）。

    字段逐项：

    - ``transaction_id``：WorldInstance 内唯一；
    - ``status``：COMMITTED / ABORTED；
    - ``base_revision``：**必填**——构建时对照的 world_revision；
    - ``commit_revision``：COMMITTED 时 ``== base_revision + 1``（唯一新版本）；
      ABORTED 时 None；
    - ``logical_tick``：提交时的逻辑刻，可空（权威序用整型，§0.2 铁律 3）；
    - ``effects``：仅 COMMITTED 携带（非空）；ABORTED 必为空——部分提交
      schema 层不可表达；
    - ``event_ids``：提交时派发的事件（§20.1 emit domain events）；
    - ``cascade``：级联上下文（Spec §21.3 数据承载，设计文档 §5.7），可空；
    - ``provenance``：可空——如 developer 注入的事务（Spec §22）；
    - ``abort_reason``：ABORTED 的原因（validation/conflict/atomic failure）。

    四条原子不变量在 ``_check_atomic_invariants`` 中强制（模块 docstring）。
    """

    transaction_id: TransactionId
    status: TransactionStatus
    base_revision: Revision
    commit_revision: Revision | None = None
    logical_tick: int | None = None
    effects: list[CommittedEffect] = Field(default_factory=list)
    event_ids: list[EventId] = Field(default_factory=list)
    cascade: CascadeContext | None = None
    provenance: Provenance | None = None
    abort_reason: str | None = None

    @model_validator(mode="after")
    def _check_atomic_invariants(self) -> "Transaction":
        """原子提交语义的数据层强制（设计文档 §5.6 四条不变量 + §7.4 C5）。

        构造与 ``model_validate``（含 JSON round-trip）时执行；违反任一条抛
        ``ValueError``（pydantic 包装为 ``ValidationError``）。frozen 模型上
        本校验器只读不写。
        """
        if self.status is TransactionStatus.COMMITTED:
            # 不变量 1：COMMITTED ⇒ commit_revision == base_revision + 1 且 effects 非空
            if self.commit_revision is None:
                raise ValueError(
                    "COMMITTED 事务必须携带 commit_revision"
                    "（== base_revision + 1，§20.1 唯一新版本）"
                )
            expected = self.base_revision.next()
            if self.commit_revision != expected:
                raise ValueError(
                    f"COMMITTED 事务 commit_revision 必须等于 base_revision + 1："
                    f"base={int(self.base_revision)}，"
                    f"期望 commit={int(expected)}，实际 commit={int(self.commit_revision)}"
                )
            if not self.effects:
                raise ValueError(
                    "COMMITTED 事务 effects 必须非空——空事务不产生状态变化，"
                    "不应消耗 revision（设计文档 §5.6 不变量 1）"
                )
            # 不变量 3：sequence 在事务内唯一且自 0 连续（reducer 确定性，§20.2）
            sequences = [effect.sequence for effect in self.effects]
            if sorted(sequences) != list(range(len(sequences))):
                raise ValueError(
                    f"effects[*].sequence 必须唯一且自 0 连续：得到 {sequences}"
                )
            # KBC-2 防线（设计文档 §9）：事务内 effect_id 唯一
            effect_ids = [effect.effect.effect_id for effect in self.effects]
            if len(set(effect_ids)) != len(effect_ids):
                raise ValueError("事务内 effect_id 重复（KBC-2 重复累加防线）")
            # §7.4 C5：事务内全部 effects 共享同一 transaction_id / commit_revision
            for effect in self.effects:
                if effect.transaction_id != self.transaction_id:
                    raise ValueError(
                        f"CommittedEffect.transaction_id 必须与事务一致："
                        f"{str(effect.transaction_id)!r} != {str(self.transaction_id)!r}"
                    )
                if effect.commit_revision != self.commit_revision:
                    raise ValueError(
                        f"CommittedEffect.commit_revision 必须与事务一致："
                        f"{int(effect.commit_revision)} != {int(self.commit_revision)}"
                    )
        else:  # ABORTED
            # 不变量 2：ABORTED ⇒ 无 revision 无 effects（部分提交不可表达）
            if self.commit_revision is not None:
                raise ValueError(
                    "ABORTED 事务不得携带 commit_revision（部分提交不可表达，§20.1）"
                )
            if self.effects:
                raise ValueError(
                    "ABORTED 事务 effects 必须为空——任何 effect 要么全体落盘"
                    "要么全体不落盘（§20.1 atomic commit）"
                )
        return self
