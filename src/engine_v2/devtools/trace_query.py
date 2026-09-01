"""P8 T07 trace 查询面（SOT §3.8 / §8.2 导出表）。

内存 trace 记录流的只读查询视图：

- D4 零 IO：构造即索引、全内存（模块面零 ``open`` / ``os`` / ``pathlib``）；
- D6 确定性：投影保持输入序，零时钟 / 零随机数；
- D7 单一错误族：错误统一为 ``TraceQueryError``（``PersistenceError`` 子类，
  默认码 ``schema_invalid``）；
- D3 JSON-clean：``CausalChain.to_dict`` 过 ``assert_json_clean``。

Spec §37 的 trace 派生 8 项中，7 项为具体方法（Effect 链→``transactions`` /
Event 链→``domain_events`` / authority 决策→``authority_decisions`` /
producer 活动→``by_producer`` / causal root→``causal_chain`` / revision
时间线→``revision_timeline`` / 开发干预历史→``intervention_history``）；
branch/replay 审计为派生查询面（D-P8-08 S2 单选：不加专用方法）。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from src.engine_v2.core import (
    CauseKind,
    CommittedEffect,
    DomainEvent,
    PAYLOAD_RECORD_KEY,
    TraceKind,
    TraceRecord,
    Transaction,
    assert_json_clean,
)
from src.engine_v2.persistence.base import PersistenceError

__all__ = ("TraceQuery", "CausalChain", "TraceQueryError")


class TraceQueryError(PersistenceError):
    """trace 查询面错误（D7：``PersistenceError`` 单一族）。

    默认码 ``schema_invalid``（查询面只接受内存记录，不涉文件侧错误码）；
    构造形如 ``TraceQueryError(message, *, code=...)``，与 W2/W3 子类同形。
    """

    def __init__(self, message: str, *, code: str = "schema_invalid") -> None:
        super().__init__(code, message)


@dataclass(frozen=True)
class CausalChain:
    """单域事件因果链面（SOT §3.8；D3 JSON-clean）。

    六字段载体：

    - ``event``：链起点；
    - ``transaction``：经 ``event.transaction_id`` 定位（无则 None）；
    - ``effects``：``transaction.effects``（含完整内嵌 ``ProposedEffect``，
      无事务时空元组）；
    - ``producers``：唯一化 + 排序（``event.source_system`` + 各
      ``effect.effect.source``）；
    - ``action_refs``：``event.cause_ids`` + 各 effect ``cause_ids`` 中
      ``CauseKind.ACTION/PROPOSAL`` 的 ``ref_id``（保序去重）；
    - ``intervention_refs``：同上但 ``CauseKind.INTERVENTION``（回指
      ``DEV_INTERVENTION`` 记录 record_id——G8-5/G8-7 闭环）。
    """

    event: DomainEvent
    transaction: Transaction | None
    effects: tuple[CommittedEffect, ...]
    producers: tuple[str, ...]
    action_refs: tuple[str, ...]
    intervention_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """全量面投影（模型 ``model_dump(mode="json")``；D3 JSON-clean）。"""
        result: dict[str, object] = {
            "event": self.event.model_dump(mode="json"),
            "transaction": (
                self.transaction.model_dump(mode="json") if self.transaction is not None else None
            ),
            "effects": [effect.model_dump(mode="json") for effect in self.effects],
            "producers": list(self.producers),
            "action_refs": list(self.action_refs),
            "intervention_refs": list(self.intervention_refs),
        }
        assert_json_clean(result)
        return result


class TraceQuery:
    """内存 trace 记录流的只读查询视图（零 IO；构造即索引，D6 输入序）。

    输入为内存 ``Sequence[TraceRecord]``（序 = ``trace.jsonl`` 落盘序）；
    payload 解析惰性——解析失败在查询时以
    ``TraceQueryError(code="schema_invalid")`` 暴露。
    """

    def __init__(self, records: Sequence[TraceRecord]) -> None:
        self._records: tuple[TraceRecord, ...] = tuple(records)
        self._by_kind: dict[TraceKind, list[TraceRecord]] = {}
        self._by_txn: dict[str, list[TraceRecord]] = {}
        for record in self._records:
            self._by_kind.setdefault(record.kind, []).append(record)
            # 仅索引 TRANSACTION 记录本身（DOMAIN_EVENT 等也携 transaction_id
            # ——若一并索引，因果链取 ``[-1]`` 会取到事件记录而非事务记录）。
            if record.kind is TraceKind.TRANSACTION:
                self._by_txn.setdefault(record.transaction_id, []).append(record)

    # —— 原始流投影（输入序）——

    def records(self) -> tuple[TraceRecord, ...]:
        """全记录流（输入序原样）。"""
        return self._records

    def by_kind(self, kind: TraceKind) -> tuple[TraceRecord, ...]:
        """按 kind 投影（输入序）。"""
        return tuple(self._by_kind.get(kind, ()))

    def by_producer(self, producer_id: str) -> tuple[TraceRecord, ...]:
        """按 producer 投影（输入序）。"""
        return tuple(r for r in self._records if r.producer_id == producer_id)

    # —— 解析投影（惰性解析）——

    def domain_events(self) -> tuple[DomainEvent, ...]:
        """``DOMAIN_EVENT`` 记录流解析（``payload["record"]``）。"""
        return tuple(
            self._parse(record, DomainEvent) for record in self.by_kind(TraceKind.DOMAIN_EVENT)
        )

    def transactions(self) -> tuple[Transaction, ...]:
        """``TRANSACTION`` 记录流解析（全量，含 ABORTED）。"""
        return tuple(
            self._parse(record, Transaction) for record in self.by_kind(TraceKind.TRANSACTION)
        )

    def committed_transactions(self) -> tuple[Transaction, ...]:
        """COMMITTED 事务子集（输入序）。

        ``COMMITTED ⟺ commit_revision`` 非空（Transaction 原子不变量；
        ``status`` 枚举不在 P8 §2.1 消费面——经不变量等价判定，W2 冻结
        先例 ``persistence/replay.py`` 同款）。
        """
        return tuple(t for t in self.transactions() if t.commit_revision is not None)

    def authority_decisions(self) -> tuple[dict[str, object], ...]:
        """authority 决策投影（输入序）。

        行 = ``{"record_id", "world_revision", "producer_id", "payload"}``；
        payload = 冻结 ``decision.to_trace_payload()`` 原样透传（JSON-clean 由
        产生侧保证，P8 零重定义）。
        """
        return tuple(
            {
                "record_id": record.record_id,
                "world_revision": record.world_revision,
                "producer_id": record.producer_id,
                "payload": record.payload,
            }
            for record in self.by_kind(TraceKind.AUTHORITY_DECISION)
        )

    def revision_timeline(self) -> tuple[dict[str, object], ...]:
        """按 revision 聚合时间线（升序，每 revision 一行）。

        行 = ``{"world_revision", "logical_tick", "wall_time", "kinds",
        "transaction_count", "event_count"}``；``logical_tick`` = 组内非 None
        最大值（否则 None）；``wall_time`` = 组内非 None 最大 datetime 的
        ISO-8601（否则 None）；``kinds`` = 组内 kind 值排序元组。
        """
        groups: dict[int, list[TraceRecord]] = {}
        for record in self._records:
            if record.world_revision is not None:
                groups.setdefault(record.world_revision, []).append(record)
        rows: list[dict[str, object]] = []
        for revision in sorted(groups):
            group = groups[revision]
            ticks = [r.logical_tick for r in group if r.logical_tick is not None]
            walls = [r.wall_time for r in group if r.wall_time is not None]
            rows.append(
                {
                    "world_revision": revision,
                    "logical_tick": max(ticks) if ticks else None,
                    "wall_time": max(walls).isoformat() if walls else None,
                    "kinds": tuple(sorted({r.kind.value for r in group})),
                    "transaction_count": sum(1 for r in group if r.kind is TraceKind.TRANSACTION),
                    "event_count": sum(1 for r in group if r.kind is TraceKind.DOMAIN_EVENT),
                }
            )
        return tuple(rows)

    def intervention_history(self) -> tuple[TraceRecord, ...]:
        """开发干预历史（``kind=DEV_INTERVENTION``，输入序）。"""
        return self.by_kind(TraceKind.DEV_INTERVENTION)

    # —— 因果链（G8-7）——

    def causal_chain(self, event_id: str) -> CausalChain:
        """单域事件因果链重建。

        定位 ``event_id`` 对应的 ``DOMAIN_EVENT`` 记录（未知 →
        ``TraceQueryError``），再沿 ``event.transaction_id`` → 事务 → 已提交
        效果 → 因果引用组装 :class:`CausalChain`。
        """
        for record in self.by_kind(TraceKind.DOMAIN_EVENT):
            payload = record.payload
            if not isinstance(payload, dict):
                continue
            raw = payload.get(PAYLOAD_RECORD_KEY)
            if not isinstance(raw, dict) or raw.get("event_id") != event_id:
                continue
            return self._build_chain(self._parse(record, DomainEvent))
        raise TraceQueryError(
            f"causal_chain: 未找到 event_id={event_id!r} 的 DOMAIN_EVENT 记录",
            code="schema_invalid",
        )

    def _build_chain(self, event: DomainEvent) -> CausalChain:
        transaction: Transaction | None = None
        if event.transaction_id is not None:
            txn_records = self._by_txn.get(event.transaction_id)
            if txn_records:
                transaction = self._parse(txn_records[-1], Transaction)
        effects: tuple[CommittedEffect, ...] = tuple(transaction.effects) if transaction else ()

        producers = {event.source_system}
        causes: list[Any] = list(event.cause_ids)
        for effect in effects:
            producers.add(effect.effect.source)
            causes.extend(effect.effect.cause_ids)

        return CausalChain(
            event=event,
            transaction=transaction,
            effects=effects,
            producers=tuple(sorted(producers)),
            action_refs=self._deduped_refs(
                causes, (CauseKind.ACTION, CauseKind.PROPOSAL)
            ),
            intervention_refs=self._deduped_refs(causes, (CauseKind.INTERVENTION,)),
        )

    @staticmethod
    def _deduped_refs(causes: Sequence[Any], kinds: tuple[CauseKind, ...]) -> tuple[str, ...]:
        """按 ``cause_ids`` 序提取指定 kind 的 ``ref_id``（保序去重）。"""
        seen: set[str] = set()
        refs: list[str] = []
        for cause in causes:
            if cause.kind in kinds and cause.ref_id not in seen:
                seen.add(cause.ref_id)
                refs.append(cause.ref_id)
        return tuple(refs)

    # —— payload 解析（惰性；失败 → schema_invalid）——

    @staticmethod
    def _parse(record: TraceRecord, model: type[Any]) -> Any:
        """解析 ``payload["record"]`` 为 core 模型（D7：失败抛 ``TraceQueryError``）。"""
        payload = record.payload
        raw = payload.get(PAYLOAD_RECORD_KEY) if isinstance(payload, dict) else None
        if not isinstance(raw, dict):
            raise TraceQueryError(
                f"trace 记录 payload 缺 {PAYLOAD_RECORD_KEY!r}（record_id={record.record_id!r}）",
                code="schema_invalid",
            )
        try:
            return model.model_validate(raw)
        except (KeyError, ValueError) as exc:
            raise TraceQueryError(
                f"trace 记录 payload schema 非法（record_id={record.record_id!r}）",
                code="schema_invalid",
            ) from exc
