"""engine_v2 core 层 Event 契约（P1-T04）。

依据 ``docs/v2/contracts/P1-core-data-contracts.md``（下称"设计文档"）：

- §1.1 本文件职责：``EventTypeId`` / ``DomainEvent``（Spec §21.1 字段 +
  cause/provenance + cascade context）；
- §5.5 :class:`DomainEvent`：Spec §21.1 字段逐项 + ``provenance``（K6/§21.2
  source 全量表达）+ ``cascade``（§21.3 级联数据承载）；
- **决策 D-14（timestamp 口径）**：Spec §23.1 时间分层下，"timestamp"一词有
  墙钟/逻辑刻/日历三种合理读法。本契约**同时**提供权威序（``logical_tick`` +
  ``world_revision``，整型、可比较、replay 友好）与诊断墙钟（``wall_time``，
  ISO-8601，可空）；日历时间不进事件（它是世界状态事实，可经 payload 引用）。
  该设计为三者并存而非择一，无需裁决；
- 事件粒度（Spec §21.2）：只要求基本 provenance，不要求微观物理过程事件化——
  ``payload`` 开放，粒度由 producer/P2 策略决定；
- §5.7 级联数据承载：每个 ``DomainEvent`` 可携带 ``CascadeContext``
  （``provenance.py``），``cause_ids`` 串联因果链；max cascade depth 与 cycle
  diagnostics 是执行器运行时配置与诊断输出（Plan P2-T07/T08），不是数据字段。

:class:`EventTypeId` 为**名字型** typed ``str`` 子类：小写点分字符串（正则
``[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*``，设计文档 §2.2 类型标识符族统一词法）；
词表由模块定义，**Kernel 不预置 RPG 事件**（§8 非目标 1）。

Pydantic 兼容性（设计文档 §2.1 风险项，与 T01/T03 同根因）：``EventTypeId``
提供与 ID 族同构的 ``__get_pydantic_core_schema__`` 兜底（接受原生 ``str``，
校验链末端重建为子类实例，JSON 序列化为纯字符串）。``wall_time`` 的
``datetime`` 字段 ``mode="json"`` 自动转 ISO 字符串（§0.2 铁律 3）。

本模块只 import 标准库、pydantic 与同包 ``src.engine_v2``（§0.3 import 边界
白名单），不触碰 v1。
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Final

from pydantic import AfterValidator, Field, JsonValue

from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.ids import EventId, ProducerId, TransactionId
from src.engine_v2.core.provenance import CascadeContext, CauseRef, Provenance
from src.engine_v2.core.revision import Revision

__all__ = [
    "EVENT_TYPE_ID_PATTERN",
    "EventTypeId",
    "parse_event_type_id",
    "DomainEvent",
]

# —— 词法规则（设计文档 §2.2：类型标识符族统一词法，与 ComponentTypeId 同）——

#: EventTypeId 词法：名字型小写点分字符串；词表由模块定义，Kernel 不预置
#: RPG 事件（设计文档 §8 非目标 1）。
EVENT_TYPE_ID_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*")


class EventTypeId(str):
    """事件类型标识（设计文档 §2.2 类型标识符族 / §5.5）。

    - 名字型 typed ``str`` 子类（与 ID 族同构，决策 D-1 的模式推广）：运行时
      ``isinstance`` 可区分，JSON 中为纯字符串；
    - 构造函数不做词法校验（确定性构造合法，与 ID 族/ComponentTypeId 一致）；
      词法校验的公共入口是 :func:`parse_event_type_id`；
    - 词表由模块定义，Kernel 不预置 RPG 事件（§8 非目标 1）；值一经使用即
      稳定（G1）；
    - ``__get_pydantic_core_schema__``：pydantic 2.13 类型保持兜底（设计文档
      §2.1 风险项，与 T01 同根因）。
    """

    __slots__ = ()

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        """Pydantic v2 集成：接受原生 str 值，校验链末端重建为子类实例。

        内层 ``str`` schema 完成字符串校验，``AfterValidator(cls)`` 在校验完成
        后重建为 ``cls`` 实例——``model_validate`` 后保持 ``type(x) is cls``，
        JSON 序列化为纯字符串（设计文档 §0.2 / §2.1 / §6.1 规则 3）。仅依赖
        pydantic 公共 API。
        """
        return handler(Annotated[str, AfterValidator(cls)])


def parse_event_type_id(text: str) -> EventTypeId:
    """校验事件类型标识词法（设计文档 §2.2 类型标识符族统一词法）。

    Args:
        text: 待校验的事件类型标识字符串。

    Returns:
        对应的 ``EventTypeId``（值与输入逐字相同）。

    Raises:
        ValueError: 非法输入——非字符串、空串、大写、段以数字开头、连续点、
            前导/尾随点、非法字符。

    只做词法校验，不做词表存在性判定（词表由模块定义，设计文档 §5.5）。
    """
    if not isinstance(text, str):
        raise ValueError(f"事件类型标识必须是字符串，得到 {type(text).__name__}")
    if not EVENT_TYPE_ID_PATTERN.fullmatch(text):
        raise ValueError(
            f"非法 EventTypeId {text!r}：不匹配 {EVENT_TYPE_ID_PATTERN.pattern!r}"
        )
    return EventTypeId(text)


class DomainEvent(ContractModel):
    """领域事件（设计文档 §5.5；Spec §21.1 字段 + cause/provenance + cascade）。

    字段逐项：

    - ``event_id``：WorldInstance 内唯一（branch 后各世界线共享祖先事件 ID
      空间，uuid4 生成天然避免跨分支碰撞，``ids.py``）；
    - ``event_type``：名字型；词表由模块定义，Kernel 不预置 RPG 事件；
    - ``world_revision``：**必填**——= 产生该事件的事务 commit_revision；
    - ``logical_tick``：§21.1 timestamp 的**权威序**落位（决策 D-14），可空；
    - ``transaction_id``：可空——无事务的 runtime 事实可为 None；
    - ``payload``：开放 payload（粒度由 producer/P2 策略决定，Spec §21.2）；
    - ``cause_ids``：类型化因果引用（``CauseRef``，Spec §21.2）；
    - ``source_system``：**必填**——产生事件的系统名字（ProducerId）；
    - ``provenance``：**必填**——K6/§21.2 source 全量表达；
    - ``cascade``：级联上下文（Spec §21.3），可空；
    - ``wall_time``：§21.1 timestamp 的**诊断侧**——ISO-8601 墙钟，仅诊断，
      权威排序一律用 ``world_revision + logical_tick``（§0.2 铁律 3）。
    """

    event_id: EventId
    event_type: EventTypeId
    world_revision: Revision
    logical_tick: int | None = None
    transaction_id: TransactionId | None = None
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    cause_ids: list[CauseRef] = Field(default_factory=list)
    source_system: ProducerId
    provenance: Provenance
    cascade: CascadeContext | None = None
    wall_time: datetime | None = None
