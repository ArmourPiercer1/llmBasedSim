"""engine_v2 core 层 ID 原语：类型、前缀、生成、解析校验（P1-T01）。

依据 ``docs/v2/contracts/P1-core-data-contracts.md`` §2（下称"设计文档"）：

- 决策 D-1：ID 族采用 **typed ``str`` 子类**——运行时可 ``isinstance`` 区分
  ID 种类（P2 写屏障/校验需要，如拒绝把 ``EffectId`` 当 ``EntityId`` 传入
  target），序列化后在 JSON 中保持纯字符串（§0.2 JSON-friendly 铁律 2）；
- 决策 D-4：``ProducerId`` 为**名字型** ID（无随机段）——Spec §17.1
  authority 配置以名字引用 writer（``interaction.lock_system`` 等），故
  ``ProducerId`` 必须是确定性可读名字而非随机 ID；
- 稳定性（G1 "public IDs stable"）：(a) ID 值一经签发不得变更/重新生成
  （round-trip 不得改写）；(b) ID 类型名与前缀属 public contract，
  冻结后变更须走 Gate review。

说明：

- 类型标识符族（``ComponentTypeId`` / ``ActionTypeId`` / ``EffectTypeId`` /
  ``EventTypeId`` / ``StateDomainId``）按设计文档 §2.2 末尾注记属 T03/T04，
  本模块不实现；其词法（小写点分字符串）由 §2.2 统一规定。
- Pydantic 兼容性（设计文档 §2.1 风险项）：本仓 pydantic 2.13 对裸 str 子类
  注解不再生成 core schema（落入 unknown type）。因此每个 ID 类提供
  ``__get_pydantic_core_schema__`` 兜底：接受原生 ``str`` 值，校验链末端
  重建为子类实例——``model_validate`` 后 ``type(x) is <IdClass>`` 保持，
  ``model_dump(mode="json")`` 输出纯字符串，契约语义与设计文档 §2.1 一致。
  设计文档字面形态 ``Annotated[EntityId, BeforeValidator(...)]`` 在该兜底
  之上同样可用（tests/engine_v2/core/test_ids.py 有验证用例）。
- 本模块只 import 标准库与 pydantic（§0.3 import 边界白名单），不触碰 v1。
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated, Any, Final

from pydantic import AfterValidator

__all__ = [
    "PREFIX_BODY_PATTERN",
    "FACTORY_BODY_PATTERN",
    "PRODUCER_ID_PATTERN",
    "PREFIX_TO_KIND",
    "EntityId",
    "EffectId",
    "EventId",
    "TransactionId",
    "CascadeId",
    "ObservationId",
    "ActionInstanceId",
    "ScheduledEntryId",
    "TraceRecordId",
    "ProducerId",
    "new_entity_id",
    "new_effect_id",
    "new_event_id",
    "new_transaction_id",
    "new_cascade_id",
    "new_observation_id",
    "new_action_instance_id",
    "new_scheduled_entry_id",
    "new_trace_record_id",
    "parse_id",
]

# —— 词法规则（设计文档 §2.2）——

#: 前缀型 ID 的正文词法：小写字母/数字/下划线，非空。
#: 除工厂生成的 32 位小写 hex 外，还容纳确定性命名 ID（``ent_authoring_<slug>``，
#: 由 project loader（P5）保证不冲突）与 Spec 示例中的短 ID（``obs_991``）。
PREFIX_BODY_PATTERN: Final = re.compile(r"[a-z0-9_]+")

#: 工厂生成的前缀型 ID 正文：uuid4 hex，32 位小写。
FACTORY_BODY_PATTERN: Final = re.compile(r"[0-9a-f]{32}")

#: ``ProducerId`` 词法（决策 D-4，§2.2）：名字型，如 ``policy.alice``、
#: ``dynamics.rigid_body``、``rule.lock_system``、``dev.console``。
PRODUCER_ID_PATTERN: Final = re.compile(r"[a-z0-9_]+(\.[a-z0-9_]+)*")


class _TypedId(str):
    """ID 族公共基类：typed ``str`` 子类的统一基类形态（决策 D-1）。

    - 构造函数不做词法校验：确定性构造合法（设计文档 §2.2 通用规则"测试
      可用确定性构造（直接 ``EntityId("ent_test_1")``）"）；词法校验的公共
      入口是 :func:`parse_id`；
    - ``__get_pydantic_core_schema__`` 是设计文档 §2.1 的 pydantic 类型保持
      兜底（详见模块 docstring）。
    """

    __slots__ = ()

    #: ID 前缀（public contract；``ProducerId`` 无随机前缀，为名字型）
    PREFIX: str = ""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        """Pydantic v2 集成：接受原生 str 值，校验链末端重建为子类实例。

        内层 ``str`` schema 完成字符串校验，``AfterValidator(cls)`` 在校验
        完成后重建为 ``cls`` 实例——``model_validate`` 后（含 dict 键、list
        元素）保持 ``type(x) is cls``，JSON 序列化为纯字符串（设计文档
        §0.2 / §2.1 / §6.1 规则 3，测试口径 R2）。仅依赖 pydantic 公共 API
        （``Annotated`` / ``AfterValidator``），不 import pydantic 内部模块。
        """
        return handler(Annotated[str, AfterValidator(cls)])


class EntityId(_TypedId):
    """WorldInstance 内唯一的实体标识（Spec §10.1）。

    值一旦签发即稳定（G1: public IDs stable）。内容侧也可使用确定性命名
    ID（如 ``ent_authoring_<slug>``，由 project loader（P5）保证不冲突）；
    Kernel 只要求值稳定、可序列化。
    """

    PREFIX = "ent_"


class EffectId(_TypedId):
    """Effect 标识（每个 ProposedEffect 一个，Spec §16.1）。

    WorldInstance 内唯一；去重依据（规避 v1 KBC-2 重复累加，设计文档 §9）。
    """

    PREFIX = "eff_"


class EventId(_TypedId):
    """DomainEvent 标识（Spec §21.1）。

    WorldInstance 内唯一。Branch（Spec §30.5）后各世界线共享祖先事件 ID
    空间，uuid4 生成天然避免跨分支碰撞。
    """

    PREFIX = "evt_"


class TransactionId(_TypedId):
    """Transaction 标识（Spec §20.1 原子提交单元）。WorldInstance 内唯一。"""

    PREFIX = "txn_"


class CascadeId(_TypedId):
    """Cascade 标识（Spec §21.3 级联）。WorldInstance 内唯一，级联根创建时签发。"""

    PREFIX = "csc_"


class ObservationId(_TypedId):
    """观察（Observation）标识（Spec §9）。

    由 ContextProvider（Plan P4）签发；P1 只定义类型与格式（``obs_`` + 正文，
    Spec §9 示例 ``obs_991``）。异步结果回引其决策所基于的观察。
    """

    PREFIX = "obs_"


class ActionInstanceId(_TypedId):
    """Action 实例 ID（Spec §11.3 / §23.4）。WorldInstance 内唯一。

    决策 D-3：proposal 创建时签发，同一实例 ID 贯穿
    ``ActionProposal → ActiveAction``（调度、中断、trace 全链路可追踪，
    Spec K6/K7）；同一 actor 重复发起同 action 产生不同实例。
    """

    PREFIX = "act_"


class ScheduledEntryId(_TypedId):
    """调度队列条目 ID（Spec §8.2 scheduler queue）。WorldInstance 内唯一。

    K7 要求调度状态可检查，队列条目必须有身份（P3 语义，P1 只落数据契约）。
    """

    PREFIX = "sch_"


class TraceRecordId(_TypedId):
    """Trace 记录 ID（设计文档 §4.4 / §5.4）。trace 流内唯一。

    uuid4 hex（或单调计数器+随机段）；trace 只追加不修改，record_id 流内唯一。
    """

    PREFIX = "trc_"


class ProducerId(_TypedId):
    """名字型 producer 标识（无随机段，决策 D-4）。

    Spec §17.1 authority 配置以名字引用 writer（如 ``interaction.lock_system``、
    ``llm_world_dynamics``），故 ``ProducerId`` 必须是确定性可读名字而非随机
    ID。词法为 ``[a-z0-9_]+(\\.[a-z0-9_]+)*``；唯一性范围为 WorldInstance
    运行时（producer 注册表落位属 Plan P2）。
    """

    PREFIX = ""


# —— 前缀 → kind 表（§2.2；前缀互斥，匹配无歧义）——

_PREFIXED_KINDS: Final = (
    (EntityId, "EntityId"),
    (EffectId, "EffectId"),
    (EventId, "EventId"),
    (TransactionId, "TransactionId"),
    (CascadeId, "CascadeId"),
    (ObservationId, "ObservationId"),
    (ActionInstanceId, "ActionInstanceId"),
    (ScheduledEntryId, "ScheduledEntryId"),
    (TraceRecordId, "TraceRecordId"),
)

#: 前缀 → ID 种类（类名），供 :func:`parse_id` 与测试守卫使用。
PREFIX_TO_KIND: Final[dict[str, str]] = {cls.PREFIX: kind for cls, kind in _PREFIXED_KINDS}


# —— 工厂函数（§2.2 通用规则：内部 uuid.uuid4()）——


def new_entity_id() -> EntityId:
    """生成新的 ``EntityId``：``ent_`` + uuid4 hex（32 位小写）。"""
    return EntityId(EntityId.PREFIX + uuid.uuid4().hex)


def new_effect_id() -> EffectId:
    """生成新的 ``EffectId``：``eff_`` + uuid4 hex（32 位小写）。"""
    return EffectId(EffectId.PREFIX + uuid.uuid4().hex)


def new_event_id() -> EventId:
    """生成新的 ``EventId``：``evt_`` + uuid4 hex（32 位小写）。"""
    return EventId(EventId.PREFIX + uuid.uuid4().hex)


def new_transaction_id() -> TransactionId:
    """生成新的 ``TransactionId``：``txn_`` + uuid4 hex（32 位小写）。"""
    return TransactionId(TransactionId.PREFIX + uuid.uuid4().hex)


def new_cascade_id() -> CascadeId:
    """生成新的 ``CascadeId``：``csc_`` + uuid4 hex（32 位小写）。"""
    return CascadeId(CascadeId.PREFIX + uuid.uuid4().hex)


def new_observation_id() -> ObservationId:
    """生成符合格式的 ``ObservationId``：``obs_`` + uuid4 hex（32 位小写）。

    运行时签发方为 ContextProvider（Plan P4，Spec §9）；本工厂只保证格式。
    """
    return ObservationId(ObservationId.PREFIX + uuid.uuid4().hex)


def new_action_instance_id() -> ActionInstanceId:
    """生成新的 ``ActionInstanceId``：``act_`` + uuid4 hex（32 位小写）。

    决策 D-3：proposal 创建时签发，贯穿 ``ActionProposal → ActiveAction``。
    """
    return ActionInstanceId(ActionInstanceId.PREFIX + uuid.uuid4().hex)


def new_scheduled_entry_id() -> ScheduledEntryId:
    """生成新的 ``ScheduledEntryId``：``sch_`` + uuid4 hex（32 位小写）。"""
    return ScheduledEntryId(ScheduledEntryId.PREFIX + uuid.uuid4().hex)


def new_trace_record_id() -> TraceRecordId:
    """生成新的 ``TraceRecordId``：``trc_`` + uuid4 hex（32 位小写）。"""
    return TraceRecordId(TraceRecordId.PREFIX + uuid.uuid4().hex)


# —— 解析与校验（§2.2 通用规则：parse_id）——


def parse_id(text: str) -> tuple[str, str]:
    """解析并校验 ID 字符串，返回 ``(kind, value)``（设计文档 §2.2 通用规则）。

    Args:
        text: 待解析的 ID 字符串。

    Returns:
        ``(kind, value)``：``kind`` 为 ID 类型的类名（``"EntityId"`` 等或
        ``"ProducerId"``）；``value`` 为校验通过的完整 ID 字符串（含前缀，
        与输入逐字相同）。

    Raises:
        ValueError: 非法输入——非字符串、空串、未知前缀、前缀后空正文、
            大写、非法字符等。

    匹配规则：

    1. 先按前缀表匹配前缀型 ID（正文须匹配 :data:`PREFIX_BODY_PATTERN`）；
       前缀互斥，匹配无歧义；
    2. 仅当无前缀匹配时，才按名字型 :data:`PRODUCER_ID_PATTERN` 匹配
       ``ProducerId``（如裸字符串 ``policy.alice``）；
    3. :func:`parse_id` 只做词法校验，不做唯一性/存在性判定（后者属
       WorldInstance 运行时与 P2 validation）。
    """
    if not isinstance(text, str):
        raise ValueError(f"ID 必须是字符串，得到 {type(text).__name__}")
    for prefix, kind in PREFIX_TO_KIND.items():
        if text.startswith(prefix):
            body = text[len(prefix):]
            if PREFIX_BODY_PATTERN.fullmatch(body):
                return kind, text
            raise ValueError(
                f"非法 {kind}：前缀 {prefix!r} 后正文 {body!r} 不匹配 {PREFIX_BODY_PATTERN.pattern!r}"
            )
    if PRODUCER_ID_PATTERN.fullmatch(text):
        return "ProducerId", text
    raise ValueError(f"非法 ID {text!r}：无已知前缀，且不是合法的 ProducerId 名字")
