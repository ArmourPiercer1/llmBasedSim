"""engine_v2 core 层知识侧契约：Belief / KnowledgeState / 观察记录 / 组件槽位与载荷编解码（P4-T04）。

依据 ``docs/v2/contracts/P4-actor-context-space-mode-design.md``（下称"设计文档"）：

- **§3.6（全量，权威）**：本模块 11 个导出符号，逐字——:class:`BeliefKind` /
  :class:`Belief`（七字段契约）/ :class:`KnowledgeState`（临时物化视图）/
  :class:`ObservationRecord`（OBS-INV-1）/ 组件槽位常量
  ``OBSERVATIONS_COMPONENT`` / ``KNOWLEDGE_COMPONENT`` / ``MEMORY_COMPONENT`` /
  :func:`encode_observations` / :func:`decode_observations` /
  :func:`encode_knowledge` / :func:`decode_knowledge`（纯函数，载荷 raw）；
- **D-P4-04**（context 一次性，ephemeral，永不持久化）：knowledge 是世界侧组件
  载荷——其单一合法位置是 ``WorldState.entities[*].components``（K2 单一合法
  写路径，reducer-only 写面）；:class:`KnowledgeState` 是从组件载荷解析的临时
  物化，**不持久化自身**，也不进入任何 RuntimeState 字段/快照；
- **D-P4-05**（认识论边界 = 构建期固化）：context 构建侧只取本模块 decode
  结果的物化值（复制进冻结结构），不持有组件载荷/视图引用——本模块不承载
  context 侧物化，只提供世界侧数据契约与编解码；
- **D-P4-09**（不确定性建模）：``Belief`` kind×confidence 承载 uncertainty
  （不设第三种 kind）；**Memory 无编解码器**——``memory`` 组件载荷 =
  ``{"items": list[JsonValue]}`` 原始列表，episodic/semantic/retrieved 结构属
  Spec:864-865 MAY 自定义域，P4 只透传（context 侧 ``memory`` 字段 = 原始
  tuple，不解释）；
- **D-P4-17**（错误分类法）：本模块不定义新错误类型（10 型两族表无 knowledge
  模块条目）；一切构造期拒绝统一走 pydantic ``ValidationError``
  （ValueError 族基类）——OBS-INV-1 重复 / 字段畸形 / 载荷畸形，不吞、不降级。

import 面（设计文档 §3.3 依赖图，全部指向 P1 冻结底座）：
``entity(ContractModel)`` / ``ids(ObservationId, EntityId)`` /
``components(ComponentTypeId)`` / ``events(EventTypeId)`` + pydantic；标准库
仅 ``enum`` / ``collections.abc``；§3.4 黑名单全部适用（无 asyncio / random /
datetime / time / uuid / json 直接 import / os / subprocess / 网络面）。

组件缺失语义（G4-1② 断言面）：``component_view(eid, KNOWLEDGE_COMPONENT)
is None`` → context 的 ``knowledge is None``（context 侧物化归 T02，本模块
不承载）。

单测口径（设计文档 §3.6 / §6.1 ``test_knowledge.py``）：Belief confidence
越界拒绝（含 0/1 边界）；OBS-INV-1 重复 id 拒绝；四个编解码 roundtrip 全等
（encode→decode→encode 字节级）；畸形载荷 → ``ValidationError``（不静默、
不降级）；``reference_entity_ids`` 去重与 ``beliefs_about`` 序。
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

from pydantic import Field, JsonValue, model_validator

from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.entity import ContractModel
from src.engine_v2.core.events import EventTypeId
from src.engine_v2.core.ids import EntityId, ObservationId

__all__ = [
    "BeliefKind",
    "Belief",
    "KnowledgeState",
    "ObservationRecord",
    "OBSERVATIONS_COMPONENT",
    "KNOWLEDGE_COMPONENT",
    "MEMORY_COMPONENT",
    "encode_observations",
    "decode_observations",
    "encode_knowledge",
    "decode_knowledge",
]


class BeliefKind(str, Enum):
    FACT = "fact"
    RUMOR = "rumor"


class Belief(ContractModel):
    """单条信念（Spec:858-862 KnowledgeState.beliefs 的标准骨架）。

    - ``subject`` / ``predicate``：自由串（entity_id 或概念词；P4 不建词表）；
    - ``value``：JSON 值（P1 §0.2 铁律 1：JSON-native 类型）；
    - ``confidence``：[0,1]——uncertainty 维度的编码（D-P4-09：Spec:862
      "uncertainty" 不另设 kind，由 kind × confidence 承载）；
    - ``origin_event_id``：可空因果回指（K6 数据面）。
    """

    kind: BeliefKind
    subject: str
    predicate: str
    value: JsonValue
    confidence: float = Field(ge=0.0, le=1.0)
    formed_tick: int = Field(ge=0)
    origin_event_id: EventTypeId | None = None


class KnowledgeState(ContractModel):
    """知识状态视图（从组件载荷解析的临时物化，D-P4-04 不持久化自身）。"""

    beliefs: tuple[Belief, ...] = ()
    last_updated_tick: int = 0

    def reference_entity_ids(self) -> frozenset[str]:
        """全部 belief 的 subject 去重集合（调用方 ∩ 世界实存，CX-INV-2）。"""
        return frozenset(belief.subject for belief in self.beliefs)

    def beliefs_about(self, subject: str) -> tuple[Belief, ...]:
        """subject 全等的 belief 序列（载荷序，确定性）。"""
        return tuple(belief for belief in self.beliefs if belief.subject == subject)


class ObservationRecord(ContractModel):
    """单条观察记录（P1 ``ObservationId`` ids.py:150 + 工厂 ids.py:247）。

    **OBS-INV-1**：``observed_entity_ids`` 重复 → 构造失败
    （K7 可检查不静默；与 P1 builder 助手拒绝重复同纪律，entity.py:86-97）。
    """

    observation_id: ObservationId
    actor_id: EntityId
    tick: int = Field(ge=0)
    payload: dict[str, JsonValue] = {}
    observed_entity_ids: tuple[EntityId, ...] = ()
    cause_event_id: EventTypeId | None = None

    @model_validator(mode="after")
    def _check_observed_entity_ids_unique(self) -> "ObservationRecord":
        """OBS-INV-1 数据层执行：重复 ``observed_entity_ids`` 显式拒绝（构造失败）。"""
        seen: set[EntityId] = set()
        for entity_id in self.observed_entity_ids:
            if entity_id in seen:
                raise ValueError(
                    f"重复 observed_entity_ids：{str(entity_id)!r}——"
                    "数据层必须显式拒绝（OBS-INV-1，entity.py:86-97 同纪律）"
                )
            seen.add(entity_id)
        return self


#: 组件类型 ID（P1 无内置 knowledge 类组件的槽位落位，state.py:255-257 逐字；
#  P4 注册归属裁定见 §8.5 偏离 D6，P9 必须复用、不得重复注册）
OBSERVATIONS_COMPONENT = ComponentTypeId("observations")
KNOWLEDGE_COMPONENT = ComponentTypeId("knowledge")
MEMORY_COMPONENT = ComponentTypeId("memory")


class _ObservationsPayload(ContractModel):
    """解码包络（私有，不导出）：``observations`` 组件载荷形状 ``{"items": [...]}``。

    包络级校验统一走 pydantic（缺 ``items`` 键 / 多余字段 / 记录字段畸形 →
    ``ValidationError``，不吞、不降级）——§3.6 decode 签名只钉外部形态与
    畸形 → ``ValidationError`` 的行为。
    """

    items: tuple[ObservationRecord, ...]


def encode_observations(records: tuple[ObservationRecord, ...]) -> dict[str, JsonValue]:
    """→ ``{"items": [record 全字段 JSON, ...]}``（载荷序）。"""
    return {"items": [record.model_dump(mode="json") for record in records]}


def decode_observations(payload: Mapping[str, JsonValue]) -> tuple[ObservationRecord, ...]:
    """载荷 → 记录序列；字段畸形 → pydantic ``ValidationError``（不吞）。"""
    return _ObservationsPayload.model_validate(payload).items


def encode_knowledge(state: KnowledgeState) -> dict[str, JsonValue]:
    """→ ``{"beliefs": [...], "last_updated_tick": int}``。"""
    return state.model_dump(mode="json")


def decode_knowledge(payload: Mapping[str, JsonValue]) -> KnowledgeState:
    """载荷 → KnowledgeState；字段畸形 → pydantic ``ValidationError``。"""
    return KnowledgeState.model_validate(payload)
