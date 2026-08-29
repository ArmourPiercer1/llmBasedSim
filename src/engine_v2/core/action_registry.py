"""engine_v2 core 层 Action 注册表：行动规格契约、参数 schema 校验、时长解析（P3-T02）。

依据 ``docs/v2/contracts/P3-scheduler-time-action-design.md``（下称"P3 设计规范"）：

- §3.5 :data:`PARAMETER_TYPES` —— 参数类型词表（Spec §11.2 YAML 示例的 ``type``
  列：``entity`` / ``number`` / ``string`` / ``boolean``）；
- §3.5 :class:`ParameterSpec` —— 单参数声明（type 词表 + ``required`` +
  ``enum_values`` + ``min_value``/``max_value`` 数值界 + ``description``）；
- §3.5 :class:`DurationPolicy` —— 时长策略（``fixed`` / ``hint`` / ``none``
  词表；``fixed`` 必填且 ``duration_ticks >= 1``，``hint`` 持 ``hint_scale``
  ``gt=0.0``）；
- §3.5 :class:`ActionSpec` —— 单行动类型声明（Spec §11.2 字段 + 新增
  ``completion_trigger`` 命名 P2 CascadeTrigger，D-P3-08）；
- §3.5 :class:`ActionRegistry` —— 注册表（键 = ``ActionTypeId``；
  ``model_validator`` 强制键 == ``spec.action_id``，P1 RuntimeState 键一致性
  同款纪律，state.py:229-244）+ 纯函数 :meth:`~ActionRegistry.lookup` /
  :meth:`~ActionRegistry.validate_arguments` /
  :meth:`~ActionRegistry.resolve_duration`；
- §3.5 :func:`validate_timing` —— :class:`~src.engine_v2.core.actions.ActionTiming`
  结构自洽校验（issue 串）；
- §3.5 :class:`UnknownActionError` —— 未注册 action_id 异常（D-P3-16 ①；
  基类 :class:`~src.engine_v2.core.clock.SchedulerError` 宿主于依赖叶
  ``clock.py``，D-P3-12/D-P3-16）。

落实的设计决策：

- **D-P3-06**（core 只做结构 + 校验点）：YAML 注册表由 P5 加载后经
  ``model_validate`` 构造，core 不引 yaml 依赖（import 边界白名单
  stdlib + pydantic，§3.2）；
- **D-P3-01**（1 tick ≙ 1 世界分钟；子 tick 钳制规则）：
  :meth:`ActionRegistry.resolve_duration` 对 < 1 的结果钳制为 1 tick
  （显式量化规则而非精度损失，D3 披露，§8.5）；
- **D-P3-16**（可检查不静默）：未注册 action_id → 抛
  :class:`UnknownActionError`（调度侧配对生命周期 FAILED 记录
  ``reason="unknown_action"``，属编排层职责，§3.8）；参数问题返回 issue 串
  （缺必填 / 未知键 / 类型不符 / 越界 / enum 不在集合）；
- **K7**（可检查）：词表/必填不变量全部构造期拒绝（pydantic
  ``ValidationError``），运行期不出现未定义分支。

本模块只 import 标准库、pydantic 与同包 ``src.engine_v2``（§3.2 import 边界
白名单，继承 P1 设计 §0.3 / P2 §1.3）；无 LLM / 网络 / 墙钟 / 隐式随机
（P3 专项黑名单 ``datetime``/``time``/``random``/``asyncio``，§8.3）。
"""

from __future__ import annotations

from typing import Final

from pydantic import Field, JsonValue, field_validator, model_validator

from src.engine_v2.core.actions import ActionTiming, ActionTypeId
from src.engine_v2.core.clock import SchedulerError
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.ids import parse_id

__all__ = [
    "ActionRegistry",
    "ActionSpec",
    "DurationPolicy",
    "PARAMETER_TYPES",
    "ParameterSpec",
    "UnknownActionError",
    "validate_timing",
]

#: 参数类型词表（P3 设计规范 §3.5；Spec §11.2 YAML 示例的 ``type`` 列）。
PARAMETER_TYPES: Final[frozenset[str]] = frozenset({"entity", "number", "string", "boolean"})

#: DurationPolicy kind 词表（P3 设计规范 §3.5；私有，不入包导出）。
_DURATION_POLICY_KINDS: Final[frozenset[str]] = frozenset({"fixed", "hint", "none"})


class ParameterSpec(ContractModel):
    """单参数声明（P3 设计规范 §3.5；Spec §11.2 registry 参数项）。

    - ``type``：:data:`PARAMETER_TYPES` 词表（构造期校验，K7 可检查不静默）；
    - ``required``：缺省 ``True``；
    - ``enum_values``：允许值集合（可选；给出时参数值必须 ∈ 集合）；
    - ``min_value`` / ``max_value``：数值界（仅 ``type == "number"`` 生效，
      P3 设计规范 §3.5 字段注）；
    - ``description``：可选说明（P5 内容层用途）。
    """

    type: str
    required: bool = True
    enum_values: list[JsonValue] | None = None
    min_value: float | None = None
    max_value: float | None = None
    description: str | None = None

    @field_validator("type")
    @classmethod
    def _check_type_vocabulary(cls, value: str) -> str:
        """type 必须在 PARAMETER_TYPES 词表内（P3 设计规范 §3.5 字段注）。"""
        if value not in PARAMETER_TYPES:
            raise ValueError(
                f"ParameterSpec.type {value!r} 不在词表 {sorted(PARAMETER_TYPES)!r} 内"
            )
        return value


class DurationPolicy(ContractModel):
    """行动时长策略（P3 设计规范 §3.5）。

    ``kind`` 词表（构造期校验）：

    - ``"fixed"``：固定时长，``duration_ticks`` 必填且 ``>= 1``；
    - ``"hint"``：由 ``ActionTiming.duration_hint_ticks`` 经 ``hint_scale``
      推导，``hint_scale`` 必填（``gt=0.0``，字段自带约束）；
    - ``"none"``：事件驱动，无时长语义（``expected_end_tick`` = ``None``）。
    """

    kind: str
    duration_ticks: int | None = None
    hint_scale: float | None = Field(default=None, gt=0.0)
    description: str | None = None

    @field_validator("kind")
    @classmethod
    def _check_kind_vocabulary(cls, value: str) -> str:
        """kind 必须在 fixed/hint/none 词表内（P3 设计规范 §3.5）。"""
        if value not in _DURATION_POLICY_KINDS:
            raise ValueError(
                f"DurationPolicy.kind {value!r} 不在词表 {sorted(_DURATION_POLICY_KINDS)!r} 内"
            )
        return value

    @model_validator(mode="after")
    def _check_kind_requirements(self) -> "DurationPolicy":
        """kind 与承载字段的必填性绑定（P3 设计规范 §3.5 字段注；K7 可检查不静默）。

        - ``fixed`` ⇒ ``duration_ticks`` 必填且 ``>= 1``；
        - ``hint`` ⇒ ``hint_scale`` 必填（``gt=0.0`` 由字段约束承担）。
        """
        if self.kind == "fixed" and (self.duration_ticks is None or self.duration_ticks < 1):
            raise ValueError(
                "DurationPolicy.kind='fixed' 要求 duration_ticks 必填且 >= 1"
                f"（P3 设计规范 §3.5）：duration_ticks={self.duration_ticks!r}"
            )
        if self.kind == "hint" and self.hint_scale is None:
            raise ValueError("DurationPolicy.kind='hint' 要求 hint_scale 必填（gt=0.0）")
        return self


class ActionSpec(ContractModel):
    """单行动类型声明（P3 设计规范 §3.5；Spec §11.2 registry 条目）。

    - ``action_id``：行动类型标识（名字型 typed str，actions.py 词法纪律）；
    - ``executor``：P5 producer/trigger 名字（与 ProducerId 同词法，ids.py:189-198；
      不持随机段）——P4/P5 执行层归属用途；P3 effect 侧 producer 口径不引用
      本字段（D-P3-11/F2-01）；
    - ``parameters``：参数名 → :class:`ParameterSpec`；
    - ``duration_policy``：时长策略，缺省 ``DurationPolicy(kind="none")``
      （事件驱动）；
    - ``interruptible``：缺省 ``True``（与 ActiveAction.interruptible 一致，
      actions.py:238）；
    - ``completion_trigger``：命名 P2 CascadeTrigger（cascade.py:473）——
      complete 时刻求值出完成效果（如 arrival 位置 effect），经 P2 管道提交
      （D-P3-08："位置只在此刻经管道提交"）；
    - ``tags``：自由标签（P5 内容层用途）。
    """

    action_id: ActionTypeId
    executor: str
    parameters: dict[str, ParameterSpec] = Field(default_factory=dict)
    duration_policy: DurationPolicy = Field(default_factory=lambda: DurationPolicy(kind="none"))
    interruptible: bool = True
    completion_trigger: str | None = None
    tags: list[str] = Field(default_factory=list)


def _check_argument_type(expected_type: str, value: JsonValue) -> bool:
    """按 type 判定单个参数值是否类型相符（P3 设计规范 §3.5 / §6.1 校验矩阵）。

    - ``string``：``str``；
    - ``number``：``int`` 或 ``float``（排除 ``bool``——Python ``bool`` 是
      ``int`` 子类，必须显式排除）；
    - ``boolean``：``bool``；
    - ``entity``：``str`` 且符合 ``EntityId`` 词法（``ent_`` 前缀 + 正文
      词法，经 ids.py :func:`parse_id` 公共入口；kind 必须为 ``"EntityId"``，
      ProducerId 名字型字符串不算）。

    ``expected_type`` 已由 :class:`ParameterSpec` 构造期词表校验保证在
    :data:`PARAMETER_TYPES` 内，末行 ``False`` 仅为静态类型完备性兜底。
    """
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "entity":
        if not isinstance(value, str):
            return False
        try:
            kind, _ = parse_id(value)
        except ValueError:
            return False
        return kind == "EntityId"
    return False


class ActionRegistry(ContractModel):
    """行动注册表（P3 设计规范 §3.5；D-P3-06：core 只做结构 + 校验点）。

    YAML 注册表由 P5 加载后经 ``model_validate`` 构造本模型（core 不引
    yaml 依赖，D-P3-06；与 P2 ``AuthorityPolicy`` 同款：pydantic 入口）。

    - ``specs``：键 = ``ActionTypeId``；``model_validator`` 强制键 ==
      ``spec.action_id``（P1 RuntimeState 键一致性同款纪律，state.py:229-244）；
    - :meth:`lookup`：按键查找（未注册 → ``None``，不抛错）；
    - :meth:`validate_arguments`：参数 schema 校验（未注册 action_id → 抛
      :class:`UnknownActionError`，D-P3-16；参数问题返回 issue 串）；
    - :meth:`resolve_duration`：时长解析（fixed/hint/none → int | None；
      D-P3-01 子 tick 钳制规则；``None`` = 事件驱动完成，
      ``expected_end_tick`` 为空，§2.1 第 1 层 / D-P3-08）。
    """

    specs: dict[ActionTypeId, ActionSpec] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_spec_key_consistency(self) -> "ActionRegistry":
        """specs 键必须与 ActionSpec.action_id 逐字一致。

        dict 语义不阻止"键与记录身份不一致"的畸形数据；若放行，按键查询与
        规格自身身份将静默分裂——与 KBC-3（双份事实源）同型的陷阱，在数据层
        拒绝（P1 RuntimeState.active_actions 键一致性同款纪律，state.py:229-244）。
        """
        for key, spec in self.specs.items():
            if spec.action_id != key:
                raise ValueError(
                    "ActionRegistry.specs 键与 ActionSpec.action_id 不一致："
                    f"键 {str(key)!r} != 记录 {str(spec.action_id)!r}"
                )
        return self

    def lookup(self, action_id: ActionTypeId) -> ActionSpec | None:
        """按键查找行动规格。

        Args:
            action_id: 行动类型标识。

        Returns:
            对应 :class:`ActionSpec`；未注册 → ``None``（调用方自行决定抛错
            或回退；:meth:`validate_arguments` 的口径是抛
            :class:`UnknownActionError`）。
        """
        return self.specs.get(action_id)

    def validate_arguments(
        self,
        action_id: ActionTypeId,
        arguments: dict[str, JsonValue],
    ) -> tuple[str, ...]:
        """按行动的参数 schema 校验实参映射（纯函数，确定性顺序）。

        校验项（P3 设计规范 §3.5 / §6.1 矩阵）：

        1. 逐参数（``spec.parameters`` 插入序）：
           - 缺必填（``required=True`` 且 arguments 缺键）；
           - 类型不符（``string`` / ``number`` / ``boolean`` / ``entity``，
             :func:`_check_argument_type` 口径；类型不符时跳过该参数的后续
             界/枚举检查）；
           - 越界（``number``：低于 ``min_value`` 或高于 ``max_value``，
             单参数至多一条 issue）；
           - enum 不在集合（``enum_values`` 给出时值必须 ∈ 集合）。
        2. 未知键（arguments 插入序）：不在 ``spec.parameters`` 中的键。

        Args:
            action_id: 目标行动类型标识。
            arguments: 实参映射（JSON 值）。

        Returns:
            issue 串元组（空元组 = 通过）。issue 格式（确定性、可断言）：
            ``missing_required:<name>`` / ``unknown_argument:<key>`` /
            ``type_mismatch:<name>`` / ``out_of_range:<name>`` /
            ``enum_violation:<name>``。

        Raises:
            UnknownActionError: ``action_id`` 未注册（D-P3-16 ①；可检查不
                静默——调度侧配对生命周期 FAILED 记录
                ``reason="unknown_action"``，属编排层职责，§3.8）。
        """
        spec = self.specs.get(action_id)
        if spec is None:
            raise UnknownActionError(f"未注册行动类型：{str(action_id)!r}")
        issues: list[str] = []
        for name, param in spec.parameters.items():
            if name not in arguments:
                if param.required:
                    issues.append(f"missing_required:{name}")
                continue
            value = arguments[name]
            if not _check_argument_type(param.type, value):
                issues.append(f"type_mismatch:{name}")
                continue
            if param.type == "number":
                below_min = param.min_value is not None and value < param.min_value
                above_max = param.max_value is not None and value > param.max_value
                if below_min or above_max:
                    issues.append(f"out_of_range:{name}")
            if param.enum_values is not None and value not in param.enum_values:
                issues.append(f"enum_violation:{name}")
        for key in arguments:
            if key not in spec.parameters:
                issues.append(f"unknown_argument:{key}")
        return tuple(issues)

    def resolve_duration(self, spec: ActionSpec, timing: ActionTiming) -> int | None:
        """按 spec 的时长策略 + 提案时序提示解析预期时长（tick）。

        （P3 设计规范 §3.5；D-P3-01 子 tick 钳制规则；D-P3-08 产出即
        ``ActiveAction.expected_end_tick`` 的来源。）

        - ``fixed`` → ``duration_policy.duration_ticks``（构造期校验保证
          非空且 ``>= 1``）；
        - ``hint`` → ``round(hint_scale * timing.duration_hint_ticks)``；
          ``duration_hint_ticks`` 缺失（``None``）→ ``None`` = 事件驱动完成
          （``expected_end_tick`` 为空）；
        - ``none`` → ``None``（事件驱动）。

        结果 ``< 1`` 一律钳制为 1 tick（D-P3-01 子 tick 规则；D3 披露，
        §8.5——显式量化规则，确定性可断言，非精度损失）。

        Args:
            spec: 行动规格（提供 ``duration_policy``）。
            timing: 提案时序（提供 ``duration_hint_ticks`` 提示）。

        Returns:
            预期时长（tick，``>= 1``）；事件驱动 → ``None``。
        """
        policy = spec.duration_policy
        if policy.kind == "fixed":
            # 构造期校验（DurationPolicy._check_kind_requirements）保证非空且 >= 1；
            # None 分支为类型完备性兜底，语义上不可达。
            if policy.duration_ticks is None:
                return None
            result = policy.duration_ticks
        elif policy.kind == "hint":
            if timing.duration_hint_ticks is None:
                return None  # hint 缺失 = 事件驱动完成（P3 设计规范 §3.5）
            result = round(policy.hint_scale * timing.duration_hint_ticks)
        else:  # kind == "none"（构造期词表校验保证）
            return None
        if result < 1:
            return 1  # D-P3-01 子 tick 钳制规则（D3 披露，§8.5）
        return result


def validate_timing(timing: ActionTiming) -> tuple[str, ...]:
    """校验 :class:`ActionTiming` 结构自洽（P3 设计规范 §3.5；issue 串）。

    校验项（字段全可空，仅在场字段参与判定）：

    - ``deadline_tick`` >= ``earliest_start_tick``（两者均在场时）；
    - ``duration_hint_ticks`` >= 1（在场时）。

    Args:
        timing: 待校验的时序结构。

    Returns:
        issue 串元组（空元组 = 通过）。issue 格式（确定性、可断言）：
        ``deadline_before_earliest`` / ``duration_hint_below_one``。
    """
    issues: list[str] = []
    if (
        timing.deadline_tick is not None
        and timing.earliest_start_tick is not None
        and timing.deadline_tick < timing.earliest_start_tick
    ):
        issues.append("deadline_before_earliest")
    if timing.duration_hint_ticks is not None and timing.duration_hint_ticks < 1:
        issues.append("duration_hint_below_one")
    return tuple(issues)


class UnknownActionError(SchedulerError):
    """未注册 action_id 异常（P3 设计规范 §3.5；D-P3-16 ①）。

    由 :meth:`ActionRegistry.validate_arguments` 对未注册 ``action_id``
    抛出（注册表点，可检查不静默）。双轨配对（D-P3-16）：编排层（scheduler，
    §3.8）对本异常落生命周期 FAILED 记录
    （``result_summary.reason="unknown_action"``）——记录属生命周期/编排层
    职责，不在本模块。
    """
