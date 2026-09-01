"""P9 W2 官方模块：relationships（T04；SOT §3.4；导出 5 名）。

来源 = v1 角色 yaml ``relationships``（dict id→float，如
whisperheads.yaml:373–380）+ 43.1-8（NPC personality/motivation/
relationship data 保留）。

冻结消费（SOT §3.0 导入闭集）：stdlib + 模块公共面 ``modules.base``
（``ModuleIdentity`` / ``OFFICIAL_MODULE_VERSION``）；自足模块
（SOT §3.1.2 表：requires = ()）。

纪律（K2/D6）：全部函数为纯函数——返回新元组，不修改入参；零模块级可变
对象；零 wall-clock / 全局 RNG；零推理消费。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from src.engine_v2.modules.base import OFFICIAL_MODULE_VERSION, ModuleIdentity

__all__ = [
    "RelationshipState",
    "RelationshipEvent",
    "init_relationships",
    "adjust_relationship",
    "relationship_summary",
]

#: 模块身份（SOT §3.1.2 MODULE_REQUIRES 表：relationships 自足 →
#: requires = ()）。
IDENTITY: Final[ModuleIdentity] = ModuleIdentity(
    "llmsim-standard-relationships", OFFICIAL_MODULE_VERSION, (),
)


def _clamp_affinity(value: float) -> float:
    """affinity 夹取闭区间 [-1.0, 1.0]（DEV-P9-05 夹取面；v1 无夹取 =
    有意收紧，SOT §8.4）。"""
    return max(-1.0, min(1.0, value))


@dataclass(frozen=True)
class RelationshipState:
    """v1 角色 yaml relationships dict 条目的冻结 dataclass 化（零可变；
    SOT §3.4 表行 1）。

    来源段 = v1 角色 yaml relationships dict（id → float，
    whisperheads.yaml:373；43.1-8 保留）。夹取面（DEV-P9-05，SOT §8.4）：
    ``affinity`` 闭区间 [-1.0, 1.0]——v1 float 直存 → v2 显式夹取（v1 无
    夹取 = 有意收紧）。
    """

    holder_id: str
    target_id: str
    affinity: float


@dataclass(frozen=True)
class RelationshipEvent:
    """关系变更事件（SOT §3.4 表行 2；kernel 事件流载荷，provenance 由
    kernel 补，SOT §8.1 K6 行）。"""

    holder_id: str
    target_id: str
    old: float
    new: float
    reason: str
    tick: int


def init_relationships(
    entries: Mapping[str, float],
    holder_id: str,
) -> tuple[RelationshipState, ...]:
    """对齐 v1 public_start/whisperheads.yaml:373（角色 yaml relationships
    dict id→float；43.1-8 保留；7 条形状样例 :373–380）。

    v1 dict → 有序元组：按 ``target_id`` 升序（确定性）；``holder_id`` =
    本 dict 持有者（v1 = 所属角色 id 隐式，v2 显式槽位）。
    夹取面（DEV-P9-05，SOT §8.4）：init 面同样夹取 [-1.0, 1.0]（状态
    不变量保持；v1 无夹取 = 有意收紧）。
    """
    return tuple(
        RelationshipState(
            holder_id=holder_id,
            target_id=target_id,
            affinity=_clamp_affinity(float(entries[target_id])),
        )
        for target_id in sorted(entries)
    )


def adjust_relationship(
    states: Sequence[RelationshipState],
    holder_id: str,
    target_id: str,
    delta: float,
    reason: str,
    tick: int,
) -> tuple[tuple[RelationshipState, ...], RelationshipEvent]:
    """v2 新增 / 无 v1 对齐面（v1 关系变更 = 宿主侧自由写
    state_apply.py:187–191，无 parity 函数可引——SOT §8.4 DEV-P9-05 记录
    差分覆盖边界）。

    纯调整 + 夹取 [-1.0, 1.0]（DEV-P9-05，SOT §8.4：v1 无夹取 = 有意
    收紧）；目标缺席 = 新建（affinity 初值 0.0，old = 0.0）。仅改
    holder_id 匹配且 target_id 匹配条目，其余条目原样（值不变）；返回
    元组保持 target_id 升序（新建目标插入排序位）。
    事件 = RelationshipEvent（old = 调整前值，缺席时 0.0；new = 夹取后
    值；reason = 宿主传入自由文本）。
    """
    current: RelationshipState | None = None
    rest: list[RelationshipState] = []
    for state in states:
        if state.holder_id == holder_id and state.target_id == target_id:
            if current is None:
                current = state
            continue
        rest.append(state)
    old = current.affinity if current is not None else 0.0
    new = _clamp_affinity(old + delta)
    updated_state = RelationshipState(
        holder_id=holder_id,
        target_id=target_id,
        affinity=new,
    )
    ordered = sorted(rest + [updated_state], key=lambda s: s.target_id)
    event = RelationshipEvent(
        holder_id=holder_id,
        target_id=target_id,
        old=old,
        new=new,
        reason=reason,
        tick=tick,
    )
    return tuple(ordered), event


def relationship_summary(
    states: Sequence[RelationshipState],
    holder_id: str,
) -> str:
    """v2 新增 / 无 v1 对齐面（v1 无关系 prompt 摘要函数面）。

    确定性 prompt 文本（SOT §3.4 表行 5：sorted；零隐藏面——无字段被省略
    呈现）。先过滤 ``s.holder_id == holder_id``（holder 视角面；单 holder
    输入下幂等），再按 ``target_id`` 升序。
    格式钉（W2）：``relationships[{holder_id}]: target_id=affinity`` 条目
    以 ``"; "`` 连接；affinity 数值 ``:g`` 格式；空集 →
    ``relationships[{holder_id}]: (空)``。
    """
    mine = [s for s in states if s.holder_id == holder_id]
    entries = [
        f"{s.target_id}={s.affinity:g}"
        for s in sorted(mine, key=lambda s: s.target_id)
    ]
    if not entries:
        return f"relationships[{holder_id}]: (空)"
    return f"relationships[{holder_id}]: " + "; ".join(entries)
