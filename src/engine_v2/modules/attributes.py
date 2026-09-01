"""P9 W1 官方模块：attributes（T02；SOT §3.2；导出 11 名）。

来源 = v1 ``src/game/attributes.py``（1100 行；43.1-4 locked/derived
attribute 思想保留）。v1 私有解析器（``_LCParser`` :200 /
``_ComputeParser`` :446）**不移植**——锁条件 / 派生计算改经 P5 冻结 DSL
（``parse_dsl`` :812 / ``evaluate_condition`` :903；43.1-3 思想的 v2
归宿）。

冻结消费（SOT §2.4/§2.5）：``engine_v2.content.rule_module``
（``parse_dsl`` / ``evaluate_condition`` / ``DslRng`` / ``DslEvalError`` /
``DslContext`` / ``Feasibility``）+ 模块公共面 ``modules.base``。

纪律（K2/D6）：全部函数为纯函数——返回新 Mapping，不修改入参；零模块级
可变对象；随机源 = 注入（``DslRng`` 型参）；零推理消费。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Final

from src.engine_v2.content.rule_module import (
    DslContext,
    DslEvalError,
    DslRng,
    Feasibility,
    evaluate_condition,
    parse_dsl,
)
from src.engine_v2.modules.base import OFFICIAL_MODULE_VERSION, ModuleIdentity

__all__ = [
    "AttributeField",
    "AttributeEvent",
    "LockedAttributeError",
    "clamp_value",
    "apply_delta",
    "apply_new_value",
    "compute_natural_deltas",
    "evaluate_lock_condition",
    "take_attribute_snapshot",
    "summarize_attributes_for_prompt",
    "derive_attributes",
]

#: 模块身份（SOT §3.1 MODULE_REQUIRES 表：attributes 自足 → requires = ()）。
IDENTITY: Final[ModuleIdentity] = ModuleIdentity(
    "llmsim-standard-attributes", OFFICIAL_MODULE_VERSION, (),
)


@dataclass(frozen=True)
class AttributeField:
    """v1 attr dict 的冻结 dataclass 化（零可变；SOT §3.2 表行 1）。"""

    name: str
    value: float
    min: float
    max: float
    locked: bool = False
    hidden: bool = False
    natural_delta_per_tick: float = 0.0


@dataclass(frozen=True)
class AttributeEvent:
    """属性变更事件（kernel 事件流载荷；provenance 由 kernel 补）。"""

    actor_id: str
    name: str
    old: float
    new: float
    reason: str
    tick: int


class LockedAttributeError(ValueError):
    """对齐 v1 src/game/attributes.py:170（``_LockedConditionError``）。

    locked 属性变更被拒；message 含属性名 + ``locked``。v2 差异：v1 锁
    条件求值失败抛此错；v2 锁条件求值走 P5 DSL（``DslEvalError`` 族），
    本错专用于 locked 字段拒绝变更（``apply_delta`` /
    ``apply_new_value`` 面）。
    """


def clamp_value(value: float, field: AttributeField) -> float:
    """对齐 v1 src/game/attributes.py:10（``_clamp``）。

    min/max 钳制；界内原样返回。
    """
    return max(field.min, min(field.max, value))


def apply_delta(
    fields: Mapping[str, AttributeField],
    actor_id: str,
    name: str,
    delta: float,
    tick: int,
) -> tuple[dict[str, AttributeField], tuple[AttributeEvent, ...]]:
    """对齐 v1 src/game/attributes.py:24–25（``_apply_delta``）。

    纯 reducer：locked 检查（**先于钳制**）→ 钳制 → 新 Mapping；不修改
    入参。
    v2 差异：

    - v1 返回 ``(attr, old, new) | None``（locked → None 静默跳过）；v2
      返回 ``(新 Mapping, 事件元组)``, locked → 抛
      ``LockedAttributeError``（显式拒绝面，宿主 try/except 钉序）；
    - 属性名缺失 → ``KeyError``（v1 宿主侧「不存在属性」警告面不迁移）；
    - 事件 = 仅 ``old != new`` 时产出；``reason`` 钉 ``"delta"``（v1
      reason = 宿主传入自由文本，v2 模块面零宿主文本依赖）。
    """
    attr = fields[name]
    if attr.locked:
        raise LockedAttributeError(f"属性 {name} 已锁定（locked），拒绝变更")
    new_value = clamp_value(attr.value + delta, attr)
    if new_value == attr.value:
        return dict(fields), ()
    updated = dict(fields)
    updated[name] = replace(attr, value=new_value)
    event = AttributeEvent(
        actor_id=actor_id,
        name=name,
        old=attr.value,
        new=new_value,
        reason="delta",
        tick=tick,
    )
    return updated, (event,)


def apply_new_value(
    fields: Mapping[str, AttributeField],
    actor_id: str,
    name: str,
    value: float,
    tick: int,
) -> tuple[dict[str, AttributeField], tuple[AttributeEvent, ...]]:
    """对齐 v1 src/game/attributes.py:36–37（``_apply_new_value``）。

    纯 reducer：locked 检查（**先于钳制**）→ 置新值 → 新 Mapping；不修改
    入参。
    v2 差异：

    - v1 置值不钳制；v2 一律钳制至 ``[min, max]``（t6 钉面）；
    - 异常 / 事件语义同 ``apply_delta``；``reason`` 钉 ``"new_value"``。
    """
    attr = fields[name]
    if attr.locked:
        raise LockedAttributeError(f"属性 {name} 已锁定（locked），拒绝变更")
    new_value = clamp_value(value, attr)
    if new_value == attr.value:
        return dict(fields), ()
    updated = dict(fields)
    updated[name] = replace(attr, value=new_value)
    event = AttributeEvent(
        actor_id=actor_id,
        name=name,
        old=attr.value,
        new=new_value,
        reason="new_value",
        tick=tick,
    )
    return updated, (event,)


def compute_natural_deltas(
    fields: Mapping[str, AttributeField],
    ticks_elapsed: int,
) -> Mapping[str, float]:
    """对齐 v1 src/game/attributes.py:113（``apply_natural_attribute_
    deltas``）+ src/graph/game_graph.py:665（``natural_attribute_delta``）
    思想。

    每 tick 自然增量 × ticks（零推理消费）。
    v2 差异：

    - 返回 = 仅非零增量项（v1 delta==0.0 跳过语义对齐，含
      ``ticks_elapsed == 0`` 全零面）；键 = Mapping dict 键（v1 同面，
      v1 属性名仅用于事件文本）；
    - 确定性 sorted 迭代；locked 属性**不预滤**——拒绝面 =
      ``apply_delta`` 显式异常（v1 ``_apply_delta`` locked 跳过对齐，
      同序可比，t12 钉面）。
    """
    result: dict[str, float] = {}
    for key in sorted(fields):
        delta = fields[key].natural_delta_per_tick * ticks_elapsed
        if delta == 0.0:
            continue
        result[key] = delta
    return result


def evaluate_lock_condition(
    fields: Mapping[str, AttributeField],
    actor_id: str,
    name: str,
    condition_dsl: str,
    rng: DslRng,
    tick: int,
) -> bool:
    """对齐 v1 src/game/attributes.py:170（``_LockedConditionError``）
    锁条件思想；v1 ``_LCParser``（:200）私有解析器不移植 → P5 冻结
    DSL（43.1-3 思想 v2 归宿）。

    评估锁条件 DSL（P5 完整 if-chain），仅 ALLOWED 返回 True。
    ERR-P9-07 钉面（SOT §9）：

    - ``condition_dsl`` = 完整 ``if(...)`` if-chain 串（P5
      ``parse_dsl`` :812 根产生式；裸表达式 = 结构错误）；
    - 上下文 = ``DslContext(variables={attr.name: attr.value for attr
      in fields.values()})``（变量面 = 属性名空间；player/target 槽
      不用）；
    - 结构错误（ast=None）→ 抛 ``DslEvalError``（诊断消息外化；不吞、
      不误锁）；语义错误（未知变量 / 除零等）= ``DslEvalError`` 自然
      透传（AD-P9-1）；
    - 返回 = ``evaluate_condition`` :903
      ``feasibility is Feasibility.ALLOWED``（UNCERTAIN/BLOCKED →
      False）。

    ``actor_id``/``name``/``tick`` = 接口统一性槽位（求值内零消费，
    供宿主事件回填）。
    """
    parsed = parse_dsl(condition_dsl, path_label="evaluate_lock_condition")
    if parsed.ast is None:
        raise DslEvalError(parsed.diagnostics[0].message)
    context = DslContext(
        variables={attr.name: attr.value for attr in fields.values()},
    )
    outcome = evaluate_condition(parsed.ast, context, rng)
    return outcome.feasibility is Feasibility.ALLOWED


def take_attribute_snapshot(
    fields: Mapping[str, AttributeField],
    actor_id: str,
    name: str,
    value: float,
) -> tuple[dict[str, AttributeField], tuple[AttributeEvent, ...]]:
    """对齐 v1 src/game/attributes.py:851（``_exec_snapshot``）。

    创建 / 覆写快照属性（hidden + locked）；两路径均零事件（v1 返回
    ``[]`` 事件对齐）。
    v2 差异：

    - 创建面 ``hidden=True, locked=True``（v1 :866 对齐）且
      ``min=max=value``（v1 创建 dict 无 min/max 键，v2 冻结字段须值；
      锁定面使界无变更意义）；
    - 既有键路径仅覆写 ``value``（v1 :851–861 对齐，**无 locked
      检查**）；
    - 不修改入参；``actor_id`` = 接口统一性槽位（零消费）。
    """
    updated = dict(fields)
    if name in updated:
        updated[name] = replace(updated[name], value=value)
    else:
        updated[name] = AttributeField(
            name=name,
            value=value,
            min=value,
            max=value,
            locked=True,
            hidden=True,
        )
    return updated, ()


def summarize_attributes_for_prompt(
    fields: Mapping[str, AttributeField],
    actor_id: str,
) -> str:
    """对齐 v1 src/game/attributes.py:1058（``summarize_attributes_
    for_prompt``）。

    确定性文本摘要（hidden 属性零文本泄漏；键序 sorted）。
    v2 差异：v1 返回 dict（hidden 属性带 ``hidden`` 标记、不过滤）；
    v2 返回文本串，hidden 属性名与值均不出现在文本中。
    格式钉（W1）：``attributes[{actor_id}]: name=value (min=..., max=
    ...)`` 条目以 ``"; "`` 连接，数值 ``:g`` 格式；可见集为空 →
    ``attributes[{actor_id}]: (空)``。
    """
    entries = [
        f"{attr.name}={attr.value:g} (min={attr.min:g}, max={attr.max:g})"
        for key in sorted(fields)
        for attr in (fields[key],)
        if not attr.hidden
    ]
    if not entries:
        return f"attributes[{actor_id}]: (空)"
    return f"attributes[{actor_id}]: " + "; ".join(entries)


def derive_attributes(
    fields: Mapping[str, AttributeField],
    actor_id: str,
    spec: Mapping[str, str],
    rng: DslRng,
) -> Mapping[str, AttributeField]:
    """对齐 v1 src/game/attributes.py:446（``_ComputeParser``）思想 =
    DSL 化注记；v1 数值算术派生不迁移（DEV-P9-06 披露面）。

    派生属性：``spec = {派生名: 裸 DSL 表达式}`` → 0/1 派生字段。
    ERR-P9-07 钉面（SOT §9）：

    - **唯一包裹点** = 模块内部合成 ``if(<expr>, allowed; blocked)``
      （spec 对外保持裸表达式形），再经 P5 ``parse_dsl`` :812 +
      ``evaluate_condition`` :903（``DslRng`` 注入）；
    - 派生 ``AttributeField.value`` = 1.0（ALLOWED）/ 0.0（非
      ALLOWED）；``min=0.0``、``max=1.0``、``locked=False``、
      ``hidden=False``、``natural_delta_per_tick=0.0``；
    - 派生结果**不反写源字段**（源 Mapping 原样）；返回值 = 仅派生
      条目（sorted spec 键序）；
    - 结构错误 → 抛 ``DslEvalError``（诊断消息外化）；语义错误
      （未知变量 / 除零等）= 自然透传。

    ``actor_id`` = 接口统一性槽位（零消费）。
    """
    context = DslContext(
        variables={attr.name: attr.value for attr in fields.values()},
    )
    derived: dict[str, AttributeField] = {}
    for derived_name in sorted(spec):
        chain = f"if({spec[derived_name]}, allowed; blocked)"
        parsed = parse_dsl(chain, path_label=f"derive_attributes:{derived_name}")
        if parsed.ast is None:
            raise DslEvalError(parsed.diagnostics[0].message)
        outcome = evaluate_condition(parsed.ast, context, rng)
        value = 1.0 if outcome.feasibility is Feasibility.ALLOWED else 0.0
        derived[derived_name] = AttributeField(
            name=derived_name,
            value=value,
            min=0.0,
            max=1.0,
        )
    return derived
