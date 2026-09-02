"""P10 Web 运行时 inspector 数据面（T06；SOT §3.10；导出 3 名）。

来源 = Spec §37（inspector 12 项视图，SHOULD 最小化承接）+ §45 主流程
（宿主面）+ Plan §19 T06；G10-4「inspector 能定位 event → transaction
→ effect → producer」机械面（A4）；K6（Event 必须可追踪来源）+ K7
（Runtime 关键调度状态必须可检查）P10 消费面。数据面经模块函数直调
消费（W4 api ``/api/inspector/{id}`` = 404 信封保留行；W5 零路由改，
SOT §3.10 / Leader 裁决面）。

冻结消费面（只读）：W4 ``adapters/web.session``（``WebSession`` 公开面
= ``state_snapshot()`` / ``save_names``；同包私有面 = ``_world``
（WorldState 只读组件投影，§3.10 明许）+ ``_trace_query``（TraceQuery
实例——**链全经它**，P10-INV-5 合规）+ ``_paused`` / ``_closed``
（运行时生命周期面投影））/ P8 邻接 ``devtools.trace_query``
（TraceQuery 7 方法面：committed_transactions / domain_events /
authority_decisions / records / causal_chain / revision_timeline /
intervention_history）。

纪律（P10-INV-1/5/10，D6，K6/K7）：

- build_inspector_view = 纯投影：零会话/世界反作用（P10-INV-1）；
  12 节闭集（:data:`INSPECTOR_SECTIONS`，Spec §37 逐字序，t1 键集
  钉）；
- **零直读 WorldState 内部构链（P10-INV-5）**：全部因果链经
  ``session._trace_query.causal_chain``（trace_query.py:199）→
  ``CausalChain.to_dict()``（trace_query.py:75）；本模块**零
  core.entity / core.components 直读 import**（特例钉，face t4 /
  边界 m4 AST 核）；
- 事件缺席 → TraceQueryError 透传（P8 D7 单一错误族；映射 404 信封
  = api 层 AD-P10-1 面，本模块零捕获）；
- 全输出面 JSON-clean（P10-INV-10，t1 json.dumps 钉）；零 wall-clock
  / 零随机（D6）；零模块级实例（P10-INV-4，A3 AST）；
- INSPECTOR_SECTIONS 12 名值与 W4 views.py 冻结私有副本
  ``_INSPECTOR_SECTIONS`` 逐字一致（双常量零环：inspector 不 import
  views，各自持常量、值一致即可——W5 一致性自验落报告）。

12 节语义钉（SOT §3.10 逐节；最小面——Spec §37 SHOULD）：

- ``world_state`` = ``state_snapshot()`` 子面（12 展示键：
  world_name / world_description / tick / view_revision / scene_id /
  game_phase / game_time / time_of_day / weather / player /
  player_attributes / npc_dynamics；私有常量
  :data:`_WORLD_STATE_SNAPSHOT_KEYS` 钉，零硬编码清单）；
- ``runtime_state`` = 会话运行时生命周期面：``lifecycle`` ∈
  running / paused / stopped（``_closed`` / ``_paused`` 投影，词表
  对齐 core ``RuntimeLifecycle``）+ ``logical_tick``（快照 tick）+
  ``scenario``（世界 scenario 信封投影：scenario_id / stage）；
- ``scheduler`` = 确定性空面（``scheduler_queue = []``：P10 会话层
  无 Scheduler 实例——P1 runtime 面，SOT §0.4 非范围；键名对齐
  Spec §8.2 scheduler queue）；
- ``active_action`` = 确定性空面（``active_actions = []``：世界面
  无 ActiveAction 记录——P3 RuntimeState active_actions 键名对齐，
  Spec §23.4）；
- ``effect_chain`` = ``TraceQuery.committed_transactions()`` 投影
  （逐事务 5 键：transaction_id / base_revision / commit_revision /
  event_ids / effect_count）；
- ``event_chain`` = ``TraceQuery.domain_events()`` 投影（逐事件 5 键：
  event_id / event_type / world_revision / transaction_id /
  source_system）；
- ``authority_decision`` = ``TraceQuery.authority_decisions()`` 原样
  （4 键行：record_id / world_revision / producer_id / payload；K6
  producer 非空 t4 钉）；
- ``producer`` = TraceQuery 全记录 ``producer_id`` 唯一化排序键集
  （by_producer 活动聚合面）；
- ``causal_root`` = 最近 domain 事件 ``causal_chain`` 摘要（5 键：
  event_id / transaction_id / effect_count / producers / action_refs；
  无事件 → None）；
- ``revision_timeline`` = ``TraceQuery.revision_timeline()`` 投影
  （升序行；严格单调钉 t3）；
- ``branch_replay`` = ``save_names`` 名表 + replay 可用性标志
  （Spec §46-9 完整 UI = 非范围；P10 零 replay 实现 → 确定性
  False）；
- ``intervention_history`` = ``TraceQuery.intervention_history()``
  投影（4 键行：record_id / world_revision / producer_id / payload；
  无 DEV_INTERVENTION 记录 → []）。
"""

from __future__ import annotations

from typing import Final

from src.engine_v2.adapters.web.session import WebSession
from src.engine_v2.devtools.trace_query import TraceQuery

__all__ = [
    "INSPECTOR_SECTIONS",
    "build_inspector_view",
    "inspect_event",
]

#: inspector 12 节名（Spec §37 逐字序，序钉；W4 views.py 冻结私有副本
#: ``_INSPECTOR_SECTIONS`` 逐字值一致——双常量零环，不 import views）。
INSPECTOR_SECTIONS: Final[tuple[str, ...]] = (
    "world_state",
    "runtime_state",
    "scheduler",
    "active_action",
    "effect_chain",
    "event_chain",
    "authority_decision",
    "producer",
    "causal_root",
    "revision_timeline",
    "branch_replay",
    "intervention_history",
)

#: world_state 节子面键集（state_snapshot 24 键的展示投影子集；
#: 钉死，零硬编码清单）。
_WORLD_STATE_SNAPSHOT_KEYS: Final[tuple[str, ...]] = (
    "world_name",
    "world_description",
    "tick",
    "view_revision",
    "scene_id",
    "game_phase",
    "game_time",
    "time_of_day",
    "weather",
    "player",
    "player_attributes",
    "npc_dynamics",
)


def _world_state_section(snapshot: dict[str, object]) -> dict[str, object]:
    """world_state = state_snapshot 子面（12 展示键投影）。"""
    return {key: snapshot[key] for key in _WORLD_STATE_SNAPSHOT_KEYS}


def _runtime_state_section(
    session: WebSession, snapshot: dict[str, object]
) -> dict[str, object]:
    """runtime_state = 生命周期 + tick + scenario 信封（只读投影）。"""
    if session._closed:
        lifecycle = "stopped"
    elif session._paused:
        lifecycle = "paused"
    else:
        lifecycle = "running"
    scenario = session._world.scenario_state
    return {
        "lifecycle": lifecycle,
        "logical_tick": snapshot["tick"],
        "scenario": {
            "scenario_id": scenario.scenario_id,
            "stage": scenario.stage,
        },
    }


def _effect_chain_section(trace: TraceQuery) -> list[dict[str, object]]:
    """effect_chain = 已提交事务投影（5 键/行）。"""
    rows: list[dict[str, object]] = []
    for transaction in trace.committed_transactions():
        commit = transaction.commit_revision
        rows.append(
            {
                "transaction_id": str(transaction.transaction_id),
                "base_revision": int(transaction.base_revision),
                "commit_revision": None if commit is None else int(commit),
                "event_ids": [str(event_id) for event_id in transaction.event_ids],
                "effect_count": len(transaction.effects),
            }
        )
    return rows


def _event_chain_section(
    events: tuple[object, ...]
) -> list[dict[str, object]]:
    """event_chain = domain 事件投影（5 键/行）。"""
    rows: list[dict[str, object]] = []
    for event in events:
        transaction_id = event.transaction_id
        rows.append(
            {
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "world_revision": int(event.world_revision),
                "transaction_id": (
                    None if transaction_id is None else str(transaction_id)
                ),
                "source_system": event.source_system,
            }
        )
    return rows


def _producer_section(trace: TraceQuery) -> list[str]:
    """producer = 全记录 producer_id 唯一化排序键集。"""
    return sorted({record.producer_id for record in trace.records()})


def _causal_root_section(
    trace: TraceQuery, latest_event: object | None
) -> dict[str, object] | None:
    """causal_root = 最近事件因果链摘要（无事件 → None）。"""
    if latest_event is None:
        return None
    chain = trace.causal_chain(str(latest_event.event_id))
    transaction = chain.transaction
    return {
        "event_id": str(latest_event.event_id),
        "transaction_id": (
            None if transaction is None else str(transaction.transaction_id)
        ),
        "effect_count": len(chain.effects),
        "producers": list(chain.producers),
        "action_refs": list(chain.action_refs),
    }


def _intervention_section(trace: TraceQuery) -> list[dict[str, object]]:
    """intervention_history = DEV_INTERVENTION 记录投影（4 键/行）。"""
    return [
        {
            "record_id": record.record_id,
            "world_revision": record.world_revision,
            "producer_id": record.producer_id,
            "payload": record.payload,
        }
        for record in trace.intervention_history()
    ]


def build_inspector_view(session: WebSession) -> dict[str, object]:
    """12 节纯投影（SOT §3.10；零反作用，P10-INV-1）。

    数据源闭集：``session.state_snapshot()``（公开）+ ``session._world``
    （只读组件投影）+ ``session._trace_query``（TraceQuery——链全经它，
    INV-5）+ ``session.save_names``（公开）。键序 =
    :data:`INSPECTOR_SECTIONS` 逐字序（t1 钉）；JSON-clean
    （P10-INV-10）。
    """
    snapshot = session.state_snapshot()
    trace = session._trace_query
    events = trace.domain_events()
    latest_event = events[-1] if events else None
    return {
        "world_state": _world_state_section(snapshot),
        "runtime_state": _runtime_state_section(session, snapshot),
        "scheduler": {"scheduler_queue": []},
        "active_action": {"active_actions": []},
        "effect_chain": _effect_chain_section(trace),
        "event_chain": _event_chain_section(events),
        "authority_decision": list(trace.authority_decisions()),
        "producer": _producer_section(trace),
        "causal_root": _causal_root_section(trace, latest_event),
        "revision_timeline": list(trace.revision_timeline()),
        "branch_replay": {
            "saves": list(session.save_names),
            "replay_available": False,
        },
        "intervention_history": _intervention_section(trace),
    }


def inspect_event(session: WebSession, event_id: str) -> dict[str, object]:
    """单域事件因果链全量投影（SOT §3.10；G10-4 / A4）。

    = ``TraceQuery.causal_chain(event_id)``（trace_query.py:199）→
    ``CausalChain.to_dict()``（trace_query.py:75）六字段全量投影
    （event / transaction / effects / producers / action_refs /
    intervention_refs）。事件缺席 → TraceQueryError 透传（零捕获；
    映射 404 信封 = api 层 AD-P10-1 面）。
    """
    chain = session._trace_query.causal_chain(event_id)
    return chain.to_dict()
