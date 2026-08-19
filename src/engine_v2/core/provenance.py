"""engine_v2 core 层跨契约共享的因果/来源小件（P1-T04 先行件）。

依据 ``docs/v2/contracts/P1-core-data-contracts.md``（下称"设计文档"）§5.0：

- :class:`OriginKind` / :class:`Provenance` —— K6：任何 committed 变化可回答
  "谁提出"。``ActionProposal`` / ``ActiveAction`` / ``DomainEvent`` /
  ``Transaction`` 共用本模块的 provenance 小件；
- :class:`CauseKind` / :class:`CauseRef` —— Spec §21.2 cause ids 的类型化表达：
  ``(kind, id)`` 对，避免裸字符串歧义（K6 的类型可追踪性）；
- :class:`CascadeContext` —— Spec §21.3：``cascade_id`` / ``causal_root_id`` /
  ``depth`` 随事件传播。max cascade depth 与 cycle diagnostics 是执行器运行时
  配置与诊断输出（Plan P2-T07/T08），**不是**数据字段（设计文档 §5.7）。

本模块是 T04 的先行件，供 ``effects.py`` / ``actions.py`` / ``events.py`` /
``transaction.py`` 引用（设计文档 §1.1 / §1.2 执行次序第 3 步）。
:class:`ContractModel` 基类复用 T03 ``entity.py`` 的内联定义（其 docstring 明确
"后续 T02/T04 模块可复用或内联"）——复用保证全部契约模型共享同一
frozen/extra=forbid 基类（设计文档 §0.1 统一模型基类约定）。

枚举一律 ``class Xxx(str, Enum)``，JSON 值为字符串字面量（设计文档 §0.1）。
本模块只 import 标准库与同包 ``src.engine_v2``（§0.3 import 边界白名单），
不触碰 v1。
"""

from __future__ import annotations

from enum import Enum

from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.ids import CascadeId, ProducerId, TraceRecordId

__all__ = [
    "OriginKind",
    "Provenance",
    "CauseKind",
    "CauseRef",
    "CascadeContext",
]


class OriginKind(str, Enum):
    """变化来源种类（设计文档 §5.0；K6"谁提出"的 origin 维度）。

    与 Spec §16.2 的 writer 家族对应：BehaviorPolicy / DynamicsBackend /
    RuleEngine / ScriptSystem / QuestSystem(scenario) / DeveloperCommand /
    Kernel 自身（结构性事件）。JSON 中为字符串字面量。
    """

    BEHAVIOR_POLICY = "behavior_policy"
    DYNAMICS_BACKEND = "dynamics_backend"
    RULE = "rule"
    SCRIPT = "script"
    SCENARIO = "scenario"
    DEVELOPER = "developer"  # Spec §22：origin=developer 显式标记
    SYSTEM = "system"  # Kernel 自身（如结构性事件）


class Provenance(ContractModel):
    """来源记录（设计文档 §5.0；K6：任何 committed 变化可回答"谁提出"）。

    ``ActionProposal`` / ``ActiveAction`` / ``DomainEvent`` / ``Transaction``
    共用。字段逐项：

    - ``producer_id``：产生者名字（决策 D-4，``ids.py``）；
    - ``origin``：来源种类（:class:`OriginKind`）；
    - ``source_record_id``：指向 trace 中的原始记录（如 ``llm_call``），可空；
    - ``notes``：自由文本补充，可空（严格 Optional 语义，KBC-7：None 与
      空串不可互换）。
    """

    producer_id: ProducerId
    origin: OriginKind
    source_record_id: TraceRecordId | None = None
    notes: str | None = None


class CauseKind(str, Enum):
    """因果引用种类（设计文档 §5.0；Spec §21.2 cause ids）。

    ``ref_id`` 的解释按 kind 区分（设计文档 §5.0 注释）：

    - ``EVENT`` → EventId；
    - ``ACTION`` → ActionInstanceId；
    - ``EFFECT`` → EffectId；
    - ``PROPOSAL`` → ActionInstanceId（proposal 与 active action 同实例 ID，
      决策 D-3）；
    - ``INTERVENTION`` → 开发干预记录（Spec §22）。
    """

    EVENT = "event"
    ACTION = "action"
    EFFECT = "effect"
    PROPOSAL = "proposal"
    INTERVENTION = "intervention"


class CauseRef(ContractModel):
    """类型化因果引用（设计文档 §5.0；Spec §21.2）。

    ``(kind, ref_id)`` 对，避免裸字符串歧义。``ref_id`` 保持 ``str``：其具体
    ID 族由 :class:`CauseKind` 语义决定，跨族统一承载用字符串（JSON 纯字符串，
    §0.2 铁律 2）；引用合法性判定属 P2 validation（P1 只落数据）。
    """

    kind: CauseKind
    ref_id: str


class CascadeContext(ContractModel):
    """级联上下文（设计文档 §5.0；Spec §21.3）。

    ``cascade_id`` / ``causal_root_id`` / ``depth`` 随事件传播：

    - ``cascade_id``：级联标识（级联根创建时签发，``ids.py``）；
    - ``causal_root_id``：级联根（EventId 或 ActionInstanceId），保持 ``str``
      统一承载（与 :class:`CauseRef.ref_id` 同理）；
    - ``depth``：根为 0。**max cascade depth 为运行时配置（P2 executor），
      不是数据字段**（设计文档 §5.0 / §5.7）。
    """

    cascade_id: CascadeId
    causal_root_id: str
    depth: int = 0
