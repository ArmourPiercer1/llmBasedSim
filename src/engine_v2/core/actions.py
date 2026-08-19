"""engine_v2 core 层 Action 契约（P1-T04）。

依据 ``docs/v2/contracts/P1-core-data-contracts.md``（下称"设计文档"）：

- §1.1 本文件职责：``ActionTypeId`` / ``ActionLifecycleStatus``（Spec §11.4）/
  ``ActionTiming`` / ``FallbackSpec`` / ``ActionProposal``（Spec §11.3 + §9
  字段）/ ``ActiveAction``（Spec §23.4 字段）；
- §5.1 :class:`ActionProposal`：身份与主体 + Spec §9 异步结果修订字段
  （``base_world_revision`` 必填，决策 D-13）+ 来源（provenance）；
- §5.2 :class:`ActiveAction`：Spec §23.4 字段逐项。K7 落位——全部字段可序列化、
  可检查，不存在隐藏于 coroutine 的调度事实（Spec §23.3 "Scheduler state 必须
  显式"）；``completion_condition`` 刻意保持不透明 JSON：P1 不锁定条件 DSL
  （Plan P3 决定），避免把 P3 决策提前扩散；
- **决策 D-3**（``ids.py``）：``ActionInstanceId`` 在 proposal 创建时签发，
  同一实例 ID 贯穿 ``ActionProposal.proposal_id → ActiveAction.instance_id``
  （调度、中断、trace 全链路可追踪，Spec K6/K7）；同一 actor 重复发起同
  ``action_id`` 产生不同实例；
- **决策 D-12**（``actor_state_revision`` 的口径）：v2 只有单一 world_revision
  （K1 单一权威状态），不建立独立 actor 修订序列；``actor_state_revision``
  记录**读取 actor 决策相关状态时的 world_revision**；
- **决策 D-13**（必填性）：``base_world_revision`` 必填（Spec §9 对异步结果的
  要求 + 强制设计约束"异步结果携带 base_world_revision"）；``observation_id`` /
  ``actor_state_revision`` 可选——同步玩家提案在 P1 阶段可能尚无观察管线
  （P4 才有 ContextProvider）。revalidation 的判定行为属 P2（Plan P2-T04）。

:class:`ActionTypeId` 为**名字型** typed ``str`` 子类：小写点分字符串（正则
``[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*``，设计文档 §2.2 类型标识符族统一词法）；
注册词表归 Action Registry（设计文档 §11.2，Plan P3/P5），Kernel 无内置取值
（§8 非目标 1）。

Pydantic 兼容性（设计文档 §2.1 风险项，与 T01/T03 同根因）：``ActionTypeId``
提供与 ID 族同构的 ``__get_pydantic_core_schema__`` 兜底（接受原生 ``str``，
校验链末端重建为子类实例，JSON 序列化为纯字符串）。

调度语义（排序/触发/中断执行/生命周期迁移行为）属 Plan P3；P1 只落数据契约
（设计文档 §8 非目标 6）。本模块只 import 标准库、pydantic 与同包
``src.engine_v2``（§0.3 import 边界白名单），不触碰 v1。
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Any, Final

from pydantic import AfterValidator, Field, JsonValue

from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.ids import ActionInstanceId, EntityId, ObservationId
from src.engine_v2.core.provenance import Provenance
from src.engine_v2.core.revision import Revision

__all__ = [
    "ACTION_TYPE_ID_PATTERN",
    "ActionTypeId",
    "parse_action_type_id",
    "ActionTiming",
    "FallbackSpec",
    "ActionProposal",
    "ActionLifecycleStatus",
    "ActiveAction",
]

# —— 词法规则（设计文档 §2.2：类型标识符族统一词法，与 ComponentTypeId 同）——

#: ActionTypeId 词法：名字型小写点分字符串（如 ``rest``、``interaction.knock``，
#: 与 Spec §11.2 action registry 示例一致）。
ACTION_TYPE_ID_PATTERN: Final = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*")


class ActionTypeId(str):
    """Action 类型标识（设计文档 §2.2 类型标识符族 / §5.1）。

    - 名字型 typed ``str`` 子类（与 ID 族同构，决策 D-1 的模式推广）：运行时
      ``isinstance`` 可区分，JSON 中为纯字符串；
    - 构造函数不做词法校验（确定性构造合法，与 ID 族/ComponentTypeId 一致）；
      词法校验的公共入口是 :func:`parse_action_type_id`；
    - 注册词表归 Action Registry（设计文档 §11.2，Plan P3/P5），Kernel 无内置
      取值（§8 非目标 1）；值一经使用即稳定（G1）；
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


def parse_action_type_id(text: str) -> ActionTypeId:
    """校验 action 类型标识词法（设计文档 §2.2 类型标识符族统一词法）。

    Args:
        text: 待校验的 action 类型标识字符串。

    Returns:
        对应的 ``ActionTypeId``（值与输入逐字相同）。

    Raises:
        ValueError: 非法输入——非字符串、空串、大写、段以数字开头、连续点、
            前导/尾随点、非法字符。

    只做词法校验，不做注册存在性判定（注册词表归 Action Registry，Plan P3/P5）。
    """
    if not isinstance(text, str):
        raise ValueError(f"action 类型标识必须是字符串，得到 {type(text).__name__}")
    if not ACTION_TYPE_ID_PATTERN.fullmatch(text):
        raise ValueError(
            f"非法 ActionTypeId {text!r}：不匹配 {ACTION_TYPE_ID_PATTERN.pattern!r}"
        )
    return ActionTypeId(text)


class ActionTiming(ContractModel):
    """行动时序的最小数据表达（设计文档 §5.1；Spec §11.3 timing）。

    调度语义（排序/触发/同刻规则）属 Plan P3；P1 只落数据（占位字段纪律，
    设计文档 §4.2）。全部字段可空，严格 Optional 语义（KBC-7）。
    """

    earliest_start_tick: int | None = None
    deadline_tick: int | None = None
    duration_hint_ticks: int | None = None


class FallbackSpec(ContractModel):
    """回退行动（设计文档 §5.1；Spec §11.3 fallback_action）。

    主行动不可执行/失败时的替代 ``action_id`` 与参数。语义判定属 P3；P1 只落
    数据。
    """

    action_id: ActionTypeId
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class ActionProposal(ContractModel):
    """行动提案（设计文档 §5.1；Spec §11.3 字段 + §9 revision 字段）。

    身份与主体：

    - ``proposal_id``：``ActionInstanceId``——决策 D-3：贯穿
      ``proposal → ActiveAction`` 的实例 ID；
    - ``actor_id``：Actor 是世界实体（Spec §12.1），故为 ``EntityId``；
    - ``action_id``：注册词表归 Action Registry（§11.2，P3/P5）；
    - ``arguments``：开放参数（``dict[str, JsonValue]``）；
    - ``intent``：自由文本意图，可空；
    - ``timing``：时序最小数据表达（调度语义属 P3）；
    - ``confidence``：取值 ``[0, 1]``，越界校验失败（设计文档 §5.1）；
    - ``fallback_action``：可空。

    Spec §9 异步结果修订字段（stale proposal 防线，设计文档 §9）：

    - ``base_world_revision``：**必填**（决策 D-13）——提案所基于的世界版本；
    - ``observation_id``：决策所基于的观察（P4 签发；Spec §9 示例
      ``obs_991``），可空；
    - ``actor_state_revision``：读取 actor 决策相关状态时的 world_revision
      （决策 D-12），可空；
    - ``valid_until``：可选有效期（``is_stale`` 的 valid_until 参数口径，
      ``revision.py``）。

    来源：``provenance`` 必填（K6）。
    """

    # —— 身份与主体 ——
    proposal_id: ActionInstanceId
    actor_id: EntityId
    action_id: ActionTypeId
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    intent: str | None = None
    timing: ActionTiming = Field(default_factory=ActionTiming)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    fallback_action: FallbackSpec | None = None
    # —— Spec §9 异步结果修订字段 ——
    base_world_revision: Revision
    observation_id: ObservationId | None = None
    actor_state_revision: Revision | None = None
    valid_until: Revision | None = None
    # —— 来源 ——
    provenance: Provenance


class ActionLifecycleStatus(str, Enum):
    """Action 生命周期状态机（设计文档 §5.2；Spec §11.4）。

    **IDLE 是 actor 层状态（未持有任何 action），不作为 action 记录状态**
    （设计文档 §5.2 注记）——故本枚举不含 IDLE。状态迁移行为属 Plan P3
    （P1 只落数据词表，设计文档 §8 非目标 6）。
    """

    PROPOSED = "proposed"
    VALIDATING = "validating"
    ACTIVE = "active"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"


class ActiveAction(ContractModel):
    """进行中的行动记录（设计文档 §5.2；Spec §23.4 字段逐项）。

    - ``instance_id``：= 对应 ``ActionProposal.proposal_id``（决策 D-3）；
    - ``action_id`` / ``actor_id``：§23.4 action_id / actor_id；
    - ``status``：生命周期状态（Spec §11.4）；
    - ``start_tick``：§23.4 start_time → logical_tick 口径（权威序用整型，
      §0.2 铁律 3）；
    - ``expected_end_tick``：§23.4 expected_end，可空；
    - ``progress``：§23.4 progress，取值 ``[0, 1]``（设计文档 §5.2 注释口径，
      与 ``confidence`` 同款区间约束）；
    - ``interruptible``：§23.4 interruptible，缺省 True；
    - ``completion_condition``：声明式条件数据，求值器属 P3（格式契约由 P3 定，
      P1 保持不透明 JSON，设计文档 §5.2 K7 落位注记）；
    - ``next_checkpoint_tick``：§23.4 next_checkpoint，可空；
    - ``base_world_revision``：继承自 proposal（§9 revalidation 依据），必填；
    - ``provenance``：K6，必填；
    - ``last_transition_tick``：最近一次状态迁移的 tick（审计用），缺省 0；
    - ``result_summary``：COMPLETED/FAILED 时的结果摘要，可空。

    K7 落位：全部字段可序列化、可检查，不存在隐藏于 coroutine 的调度事实
    （Spec §23.3）。
    """

    instance_id: ActionInstanceId
    action_id: ActionTypeId
    actor_id: EntityId
    status: ActionLifecycleStatus
    start_tick: int
    expected_end_tick: int | None = None
    progress: float | None = Field(default=None, ge=0.0, le=1.0)
    interruptible: bool = True
    completion_condition: dict[str, JsonValue] | None = None
    next_checkpoint_tick: int | None = None
    base_world_revision: Revision
    provenance: Provenance
    last_transition_tick: int = 0
    result_summary: dict[str, JsonValue] | None = None
