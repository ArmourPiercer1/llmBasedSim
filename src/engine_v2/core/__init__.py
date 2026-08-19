"""v2 Kernel 核心契约（Phase 1 填充完成，P1-T06 re-export 收尾）。

职责：单一 authoritative state 的数据语言——Entity / typed Component、
WorldState / RuntimeState 分离、Revision、Action（Registry / Proposal /
Lifecycle）、ProposedEffect、Authority、Validation、Conflict Resolution、
Transaction / Reducer、DomainEvent（含 provenance）。

对应 Spec 章节：§4 Kernel 强制不变量（K1–K8）、§8 State Model、
§9 Revision Model、§10 Entity / Component Contract、§11 Action Contract、
§16 Effect Contract、§17 Authority Contract、§18 Effect Validation、
§19 Conflict Resolution、§20 Transaction / Reducer、§21 Event Contract。

此包禁止 import LangGraph / OpenAI（G1 门禁），且完全不接 LLM（Spec §47
Phase 1 验收：core tests 无网络、无 LLM 可完整运行）。

re-export 收尾（设计文档 §0.4）：P1 全部契约模块的公共导出集中于此——
从各模块 import 再导出并定义 ``__all__``（骨架期"__init__.py 仅 docstring"
纪律的预告解除，``tests/test_engine_v2_skeleton.py`` 已同步最小修订为仅
允许本文件的 re-export 语句与 ``__all__`` 清单）。契约类型一律以
``from src.engine_v2.core import <类型>`` 直接可用；各名称的**定义来源
保持单一**（``CONTRACT_SCHEMA_VERSION`` 只从 ``state.py`` 导入——T02
已确立其为唯一定义源，``snapshot.py`` 亦从 ``state.py`` 复用，严禁双源
复写）。

**同名遮蔽豁免（机械规则，非裁剪）**：与**子模块同名**的模块导出不在
包级 re-export——本包中即 ``snapshot.py`` 的 ``snapshot()`` 纯函数与
``snapshot`` 子模块同名：若把函数绑到包属性 ``core.snapshot``，会覆盖
import 系统在该子模块加载时设置的同名模块属性，使
``import src.engine_v2.core.snapshot as m``（bpo-30024：属性链成功时
不回退 sys.modules）拿到函数而非模块，破坏既有测试对子模块的访问。
故 ``snapshot()`` 仅经子模块路径导出（``from src.engine_v2.core.snapshot
import snapshot``）；包属性 ``core.snapshot`` 保持为子模块。该规则由
``tests/engine_v2/core/test_closeout.py`` 机械化断言（与子模块名撞名的
导出集合必须恰为豁免集合）。
"""

from src.engine_v2.core.actions import (
    ACTION_TYPE_ID_PATTERN,
    ActionLifecycleStatus,
    ActionProposal,
    ActionTiming,
    ActionTypeId,
    ActiveAction,
    FallbackSpec,
    parse_action_type_id,
)
from src.engine_v2.core.components import (
    COMPONENT_TYPE_ID_PATTERN,
    ComponentConflictError,
    ComponentData,
    ComponentRegistry,
    ComponentSchema,
    ComponentTypeId,
    parse_component_type_id,
)
from src.engine_v2.core.effects import (
    EFFECT_TYPE_ID_PATTERN,
    STATE_DOMAIN_ID_PATTERN,
    CommittedEffect,
    EffectTarget,
    EffectTypeId,
    EntityTarget,
    ProposedEffect,
    StateDomainId,
    StateDomainTarget,
    parse_effect_type_id,
    parse_state_domain_id,
)
from src.engine_v2.core.entity import ContractModel, EntityRecord, EntityRef, EntityView
from src.engine_v2.core.events import (
    EVENT_TYPE_ID_PATTERN,
    DomainEvent,
    EventTypeId,
    parse_event_type_id,
)
from src.engine_v2.core.ids import (
    FACTORY_BODY_PATTERN,
    PREFIX_BODY_PATTERN,
    PREFIX_TO_KIND,
    PRODUCER_ID_PATTERN,
    ActionInstanceId,
    CascadeId,
    EffectId,
    EntityId,
    EventId,
    ObservationId,
    ProducerId,
    ScheduledEntryId,
    TraceRecordId,
    TransactionId,
    new_action_instance_id,
    new_cascade_id,
    new_effect_id,
    new_entity_id,
    new_event_id,
    new_observation_id,
    new_scheduled_entry_id,
    new_trace_record_id,
    new_transaction_id,
    parse_id,
)
from src.engine_v2.core.provenance import (
    CascadeContext,
    CauseKind,
    CauseRef,
    OriginKind,
    Provenance,
)
from src.engine_v2.core.revision import (
    INITIAL_WORLD_REVISION,
    RevalidationOutcome,
    Revision,
    is_stale,
    next_revision,
)
from src.engine_v2.core.serialization import (
    assert_json_clean,
    deep_copy_via_roundtrip,
    dump_json,
    load_json,
)
# 注意：snapshot.py 的 ``snapshot()`` 纯函数**不**在包级 re-export——与
# ``snapshot`` 子模块同名，函数绑到包属性会遮蔽子模块属性（模块 docstring
# "同名遮蔽豁免"）；经 ``src.engine_v2.core.snapshot.snapshot`` 可达。
from src.engine_v2.core.snapshot import (
    SNAPSHOT_FORMAT_VERSION,
    Snapshot,
    check_snapshot_versions,
    freeze_view,
    restore_snapshot,
)
from src.engine_v2.core.state import (
    CONTRACT_SCHEMA_VERSION,
    ActorWakeup,
    BackendStateRef,
    RngState,
    RuntimeLifecycle,
    RuntimeState,
    ScenarioState,
    ScheduledEvent,
    WorldState,
)
from src.engine_v2.core.trace import (
    DECISION_PAYLOAD_KEYS,
    LLM_CALL_PAYLOAD_KEYS,
    PAYLOAD_RECORD_KEY,
    TraceKind,
    TraceRecord,
)
from src.engine_v2.core.transaction import Transaction, TransactionStatus

__all__ = [
    'ACTION_TYPE_ID_PATTERN',
    'ActionInstanceId',
    'ActionLifecycleStatus',
    'ActionProposal',
    'ActionTiming',
    'ActionTypeId',
    'ActiveAction',
    'ActorWakeup',
    'BackendStateRef',
    'COMPONENT_TYPE_ID_PATTERN',
    'CONTRACT_SCHEMA_VERSION',
    'CascadeContext',
    'CascadeId',
    'CauseKind',
    'CauseRef',
    'CommittedEffect',
    'ComponentConflictError',
    'ComponentData',
    'ComponentRegistry',
    'ComponentSchema',
    'ComponentTypeId',
    'ContractModel',
    'DECISION_PAYLOAD_KEYS',
    'DomainEvent',
    'EFFECT_TYPE_ID_PATTERN',
    'EVENT_TYPE_ID_PATTERN',
    'EffectId',
    'EffectTarget',
    'EffectTypeId',
    'EntityId',
    'EntityRecord',
    'EntityRef',
    'EntityTarget',
    'EntityView',
    'EventId',
    'EventTypeId',
    'FACTORY_BODY_PATTERN',
    'FallbackSpec',
    'INITIAL_WORLD_REVISION',
    'LLM_CALL_PAYLOAD_KEYS',
    'ObservationId',
    'OriginKind',
    'PAYLOAD_RECORD_KEY',
    'PREFIX_BODY_PATTERN',
    'PREFIX_TO_KIND',
    'PRODUCER_ID_PATTERN',
    'ProducerId',
    'ProposedEffect',
    'Provenance',
    'RevalidationOutcome',
    'Revision',
    'RngState',
    'RuntimeLifecycle',
    'RuntimeState',
    'SNAPSHOT_FORMAT_VERSION',
    'STATE_DOMAIN_ID_PATTERN',
    'ScenarioState',
    'ScheduledEntryId',
    'ScheduledEvent',
    'Snapshot',
    'StateDomainId',
    'StateDomainTarget',
    'TraceKind',
    'TraceRecord',
    'TraceRecordId',
    'Transaction',
    'TransactionId',
    'TransactionStatus',
    'WorldState',
    'assert_json_clean',
    'check_snapshot_versions',
    'deep_copy_via_roundtrip',
    'dump_json',
    'freeze_view',
    'is_stale',
    'load_json',
    'new_action_instance_id',
    'new_cascade_id',
    'new_effect_id',
    'new_entity_id',
    'new_event_id',
    'new_observation_id',
    'new_scheduled_entry_id',
    'new_trace_record_id',
    'new_transaction_id',
    'next_revision',
    'parse_action_type_id',
    'parse_component_type_id',
    'parse_effect_type_id',
    'parse_event_type_id',
    'parse_id',
    'parse_state_domain_id',
    'restore_snapshot',
]

