"""P9 W3 官方模块：knowledge（T06/T10；SOT §3.7；导出 4 名）。

来源 = v1 memory 注入行为（src/graph/game_graph.py:553–561，cap 50）
→ v2 = **仅经 ObservationRecord 的 belief 更新**（43.2-6 移除——v1
全局事件文本注入全员 memory = omniscience 子行为；43.1-9
perception/knowledge 分离思想）；载体 = core 冻结知识三组件
（OBSERVATIONS_COMPONENT:139 / KNOWLEDGE_COMPONENT:140 /
MEMORY_COMPONENT:141，core knowledge.py）——本模块只产数据值，组件
写路径经宿主 encode（K2 零直写）。

冻结消费（SOT §3.0 导入闭集）：stdlib + core ``knowledge``
（``BeliefKind``:70 / ``Belief``:75 / ``KnowledgeState``:94 /
``ObservationRecord``:109）+ 模块公共面 ``modules.base`` +
``modules.perception``（``PerceptionResult``；SOT §3.1.2 表 requires
= ("llmsim-standard-perception",)——消费 ObservationRecord 类型面）。

纪律（K2/D6）：全部函数 = 纯函数（返回新对象，零入参修改）；零模块级
可变对象；零 wall-clock / 全局 RNG / uuid / random。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final

from src.engine_v2.core.knowledge import (
    Belief,
    BeliefKind,
    KnowledgeState,
    ObservationRecord,
)
from src.engine_v2.modules.base import OFFICIAL_MODULE_VERSION, ModuleIdentity
from src.engine_v2.modules.perception import PerceptionResult

__all__ = [
    "BeliefEvent",
    "apply_observations",
    "memory_append",
    "knowledge_summary",
]

#: 模块身份（SOT §3.1.2 MODULE_REQUIRES 表：knowledge 声明
#: requires = ("llmsim-standard-perception",)——消费 ObservationRecord
#: 类型面）。
IDENTITY: Final[ModuleIdentity] = ModuleIdentity(
    "llmsim-standard-knowledge", OFFICIAL_MODULE_VERSION,
    ("llmsim-standard-perception",),
)

#: 新增 belief 初值置信度（delegated 面；W3 测试钉，见
#: ``apply_observations`` docstring）。
_INITIAL_CONFIDENCE = 0.5
#: 每次强化置信度增量（delegated 面；不衰减，上界 1.0；W3 测试钉）。
_REINFORCE_STEP = 0.1


@dataclass(frozen=True)
class BeliefEvent:
    """belief 更新事件（SOT §3.7 表行 1）。"""

    actor_id: str
    kind: BeliefKind
    subject: str
    text: str
    tick: int


def _belief_event(record: ObservationRecord, kind: BeliefKind, subject: str) -> BeliefEvent:
    """确定性事件措辞：``"<actor_id> 观察到 <subject> (<predicate>)"``。"""
    return BeliefEvent(
        actor_id=record.actor_id,
        kind=kind,
        subject=subject,
        text=f"{record.actor_id} 观察到 {subject} ({record.payload.get('kind', 'observation')})",
        tick=record.tick,
    )


def apply_observations(
    knowledge: KnowledgeState,
    result: PerceptionResult,
) -> tuple[KnowledgeState, tuple[BeliefEvent, ...]]:
    """v2 新增 / 无 v1 parity 函数可引（v1 memory 注入 = 全局状态直写，
    43.2-6 移除；v2 = 仅经 ObservationRecord 的纯 reducer，T10 回归
    的模块侧保证）。

    纯 reducer：ObservationRecord → Belief 集（新增/强化，不衰减）；
    返回新 ``KnowledgeState``（core:94，经构造器新建，零入参修改，K2）；
    **无 observations 输入 = 零变更**（返回 state 的 ``encode_knowledge``
    （core:165）逐字节等同入参 + 空事件元组）。

    映射（确定性；delegated 面；W3 测试钉）：

    - 每条 record → 候选 Belief：``kind`` = FACT；``subject`` =
      ``observed_entity_ids[0]``；``predicate`` = 感官分类
      （``payload["kind"]``，缺失 → ``"observation"``）；``value`` =
      ``payload`` 全 dict（JSON-native；防御性浅拷贝）；``confidence``
      初值 0.5；``formed_tick`` = record tick；``origin_event_id`` =
      ``record.cause_event_id``（本模块记录面 = None）；
    - ``observed_entity_ids`` 为空的 record → 零 belief 零事件（无
      subject，确定性跳过）；
    - 强化：同 ``(subject, predicate)`` 已存在 → ``confidence`` =
      min(1.0, old + 0.1)（不衰减）；``formed_tick`` / ``kind`` /
      ``origin_event_id`` 保持旧值（不改 formed_tick）；``value`` 更新
      为最新 record payload；
    - 新增 = 按 ``(subject, predicate)`` 升序全序插入位（beliefs 元组
      恒保持该全序，与 record 到达序无关）；
    - ``last_updated_tick`` = 实际变更（新增或强化）record 的 tick
      最大值；零变更 = 保持不变（逐字节等同）；
    - 事件：每个新增/强化的 Belief 产 1 条 ``BeliefEvent``（``text`` =
      确定性措辞，见 ``_belief_event``；``tick`` = record tick）；事件
      序 = record 处理序（result.records 序）；零 records = 零事件。
    """
    beliefs: list[Belief] = list(knowledge.beliefs)
    events: list[BeliefEvent] = []
    changed_ticks: list[int] = []
    index: dict[tuple[str, str], int] = {
        (belief.subject, belief.predicate): pos
        for pos, belief in enumerate(beliefs)
    }
    for record in result.records:
        if not record.observed_entity_ids:
            continue
        subject = record.observed_entity_ids[0]
        predicate = str(record.payload.get("kind", "observation"))
        value = dict(record.payload)
        key = (subject, predicate)
        if key in index:
            old = beliefs[index[key]]
            beliefs[index[key]] = Belief(
                kind=old.kind,
                subject=old.subject,
                predicate=old.predicate,
                value=value,
                confidence=min(1.0, old.confidence + _REINFORCE_STEP),
                formed_tick=old.formed_tick,
                origin_event_id=old.origin_event_id,
            )
            events.append(_belief_event(record, old.kind, subject))
            changed_ticks.append(record.tick)
            continue
        belief = Belief(
            kind=BeliefKind.FACT,
            subject=subject,
            predicate=predicate,
            value=value,
            confidence=_INITIAL_CONFIDENCE,
            formed_tick=record.tick,
            origin_event_id=record.cause_event_id,
        )
        pos = 0
        while (
            pos < len(beliefs)
            and (beliefs[pos].subject, beliefs[pos].predicate) < key
        ):
            pos += 1
        beliefs.insert(pos, belief)
        index = {
            (b.subject, b.predicate): i for i, b in enumerate(beliefs)
        }
        events.append(_belief_event(record, belief.kind, subject))
        changed_ticks.append(record.tick)
    last_updated = knowledge.last_updated_tick
    if changed_ticks:
        last_updated = max(changed_ticks)
    return (
        KnowledgeState(beliefs=tuple(beliefs), last_updated_tick=last_updated),
        tuple(events),
    )


def memory_append(
    memory: tuple[str, ...],
    entry: str,
    cap: int = 50,
) -> tuple[str, ...]:
    """对齐 v1 src/graph/game_graph.py:559（``if len(mem) > 50: mem =
    mem[-50:]``；memory 注入块 game_graph.py:553–561）。

    纯追加 + cap（保留最新 ``cap`` 条、丢弃最旧；``cap`` 默认 50 = v1
    面）；保时序 tuple 追加，不 sorted；``cap <= 0`` → 零元组（退化
    面，确定性）。
    """
    if cap <= 0:
        return ()
    extended = memory + (entry,)
    if len(extended) > cap:
        return extended[-cap:]
    return extended


def _format_value(value: object) -> str:
    """JSON-native 值 → 确定性 JSON 串（键全序 / 紧凑分隔符 / 零
    ASCII 转义）。"""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


def knowledge_summary(knowledge: KnowledgeState, actor_id: str) -> str:
    """v2 新增 / 无 v1 parity 函数可引（v1 无 knowledge prompt 摘要
    函数面）。

    确定性 prompt 文本（SOT §3.7 表行 4）：``actor_id`` = 标签槽面
    （knowledge 载体 = 实体组件，非按 actor 分区；本函数只产 prompt
    文本）。格式钉（W3，对齐 W1/W2 摘要形制）：
    ``knowledge[{actor_id}]: subject=predicate=value:confidence`` 条目
    以 ``"; "`` 连接；value = JSON 编码（``_format_value``）；
    confidence ``:g`` 格式；条目按 ``(subject, predicate)`` 升序（规范
    序，与载荷序无关）；空集 → ``knowledge[{actor_id}]: (空)``。
    """
    entries = [
        f"{belief.subject}={belief.predicate}="
        f"{_format_value(belief.value)}:{belief.confidence:g}"
        for belief in sorted(
            knowledge.beliefs,
            key=lambda b: (b.subject, b.predicate),
        )
    ]
    if not entries:
        return f"knowledge[{actor_id}]: (空)"
    return f"knowledge[{actor_id}]: " + "; ".join(entries)
