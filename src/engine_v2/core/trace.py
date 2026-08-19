"""engine_v2 core 层 Trace 记录契约（P1-T02）。

依据 ``docs/v2/contracts/P1-core-data-contracts.md``（下称"设计文档"）§4.4：

- **决策 D-11**：TraceState 采用**单一信封 + kind 判别 + 开放 payload** 的
  append-only 记录流，而非每类记录一个顶层模型。理由：(a) Spec §8.4 要求
  trace 可流式持久化——同质信封对 append-only 文件/表最友好；(b) P2/P6
  新增记录种类（conflict 决定、LLM 调用）不需要改 core 顶层类型集合，只需
  注册新 ``TraceKind`` 与 payload 子约定；(c) 前向兼容：旧工具遇未知 kind
  可按 payload 原样透传；
- §4.3 归属总表：commands / action proposals / proposed effects / authority /
  validation / conflict 决定 / transactions / domain events / LLM calls /
  prompt assembly metadata / development interventions 全部**进 Trace 不进
  Snapshot**；trace 记录"变化"，不复制状态本体——:class:`TraceRecord` 不含
  任何状态字段（测试口径 S2 的程序化断言对象）；
- 时间语义（决策 D-6/D-14 同源）：权威序用 ``world_revision + logical_tick``
  （整型，§0.2 铁律 3）；``wall_time`` 墙钟仅诊断（ISO-8601）。日历时间
  不进 trace（它是世界状态事实，归 WorldState）；
- **流不变量**：trace 只追加不修改；``record_id`` 流内唯一；同一
  WorldInstance 的 trace 与 snapshot 通过 ``world_revision + logical_tick``
  对齐。存储介质（文件/SQLite/…）属 PersistenceBackend（Spec §30.3，Plan
  P8），P1 不定。

payload 子约定（按 kind，§4.4 表）由本模块常量冻结键名：

- ``action_proposal`` / ``proposed_effect`` / ``transaction`` /
  ``domain_event``：``{"record": <对应契约模型的 model_dump(mode="json")>}``
  （:data:`PAYLOAD_RECORD_KEY`）——trace 内嵌完整记录，支持无 runtime 离线
  审计；
- ``authority_decision`` / ``validation_decision`` / ``conflict_resolution``：
  ``effect_id`` / ``decision`` / ``reason``（:data:`DECISION_PAYLOAD_KEYS`；
  decision 词表 P2 定义：allow/deny/…）；
- ``llm_call``：Spec §31.3 字段键名（:data:`LLM_CALL_PAYLOAD_KEYS`）。
  **不得**出现 credential/api_key（Spec §31.3、K8）；P1 只冻结键名约定，
  不产生记录（P6 起产生）；
- ``dev_intervention``：``origin: "developer"`` 强制（Spec §22；词表即
  ``provenance.py`` :class:`OriginKind.DEVELOPER`）+ 命令描述。

本模块仅依赖 ``ids`` / ``revision`` 与本包已落盘类型（``ContractModel``，
T03）；只 import 标准库、pydantic 与同包 ``src.engine_v2``（§0.3 import
边界白名单），不触碰 v1。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Final

from pydantic import Field, JsonValue

from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.ids import CascadeId, ProducerId, TraceRecordId, TransactionId
from src.engine_v2.core.revision import Revision

__all__ = [
    "PAYLOAD_RECORD_KEY",
    "DECISION_PAYLOAD_KEYS",
    "LLM_CALL_PAYLOAD_KEYS",
    "TraceKind",
    "TraceRecord",
]

#: payload 子约定（§4.4 表）：``action_proposal`` / ``proposed_effect`` /
#: ``transaction`` / ``domain_event`` 四种 kind 以本键内嵌对应契约模型的
#: ``model_dump(mode="json")`` 完整记录——无 runtime 离线审计的数据基础。
PAYLOAD_RECORD_KEY: Final[str] = "record"

#: payload 子约定（§4.4 表）：``authority_decision`` / ``validation_decision``
#: ``conflict_resolution`` 三种 kind 的约定键（``decision`` 词表 P2 定义）。
DECISION_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset({"effect_id", "decision", "reason"})

#: payload 子约定（§4.4 表）：``llm_call`` kind 的 Spec §31.3 预留键名。
#: P1 只冻结键名约定，不产生记录（P6 起产生）；credential/api_key **永不**
#: 出现在此集合或任何 payload（Spec §31.3、K8）。
LLM_CALL_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "logical_role",
        "profile",
        "resolved_model",
        "input_token_estimate",
        "prompt_metadata_ref",
        "output_ref",
        "latency_ms",
        "parse_retry",
        "base_revision",
    }
)


class TraceKind(str, Enum):
    """Trace 记录种类（设计文档 §4.4；Spec §8.4 内容逐项落位，决策 D-11）。

    与 Spec §8.4 清单一一对应；``SYSTEM`` 收纳 lifecycle/错误等杂项
    （含 §5.7 为 cascade 诊断预留的通道）。枚举一律 ``class Xxx(str, Enum)``，
    JSON 值为字符串字面量（设计文档 §0.1）。
    """

    COMMAND = "command"  # Spec §8.4 commands
    ACTION_PROPOSAL = "action_proposal"  # action proposals
    PROPOSED_EFFECT = "proposed_effect"  # proposed effects
    AUTHORITY_DECISION = "authority_decision"  # authority decisions（P2 产生）
    VALIDATION_DECISION = "validation_decision"
    CONFLICT_RESOLUTION = "conflict_resolution"
    TRANSACTION = "transaction"  # transactions（含 ABORTED，审计原子失败）
    DOMAIN_EVENT = "domain_event"  # events
    LLM_CALL = "llm_call"  # LLM calls（P6 起；payload 键名见 LLM_CALL_PAYLOAD_KEYS）
    PROMPT_ASSEMBLY = "prompt_assembly"  # prompt assembly metadata
    DEV_INTERVENTION = "dev_intervention"  # development interventions（Spec §22）
    SYSTEM = "system"  # lifecycle/错误等杂项


class TraceRecord(ContractModel):
    """TraceState 的记录单元（设计文档 §4.4；Spec §8.4，决策 D-11）。

    单一信封 + ``kind`` 判别 + 开放 ``payload``：

    - ``record_id``：trace 流内唯一（流不变量；流级唯一性检查属 P8 存储层）；
    - ``kind``：记录种类判别（:class:`TraceKind`）；
    - ``world_revision`` / ``logical_tick``：记录产生时的权威序坐标，可空；
      trace 与 snapshot 通过二者对齐（流不变量）；
    - ``wall_time``：仅诊断；权威排序一律用 ``revision + tick``（§0.2 铁律 3）；
    - ``producer_id`` / ``transaction_id`` / ``cascade_id``：因果关联键，可空；
    - ``payload``：开放 JSON dict，子约定按 kind（模块常量）。

    trace 记录"变化"，不复制状态本体（§4.3 归属总表）：本模型无任何状态
    字段（无 entities/world_variables/scheduler_queue 等）。严格 Optional
    语义（KBC-7）：缺省一律 None，None 与 0/空 dict 不可互换。
    """

    record_id: TraceRecordId
    kind: TraceKind
    world_revision: Revision | None = None
    logical_tick: int | None = None
    wall_time: datetime | None = None
    producer_id: ProducerId | None = None
    transaction_id: TransactionId | None = None
    cascade_id: CascadeId | None = None
    payload: dict[str, JsonValue] = Field(default_factory=dict)
