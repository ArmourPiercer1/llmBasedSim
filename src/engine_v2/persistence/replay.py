"""P8 T03：event-level replay 引擎（零 IO）。

本模块是 ``src.engine_v2.persistence`` 包 replay 面（P8 T03，SOT §3.4）：
自 save 时点的 ``WorldState`` + 全量 ``TraceRecord`` 序列重建 COMMITTED
事务序终态（K2 唯一应用路径复用：冻结 ``core/reducer.py`` 的
``apply_transaction``）；不重跑推理侧（D-P8-05：不消费任何动力学
backend，R3"不要求 bit-identical rerun"自然满足）。

导出（§8.2 账目 3 名）：

- :class:`ReplayResult` —— 重放结果载体（frozen dataclass；``final_state``
  与输入零别名；``to_dict`` JSON-clean，D3）；
- :class:`ReplayError` —— T03 错误族（``PersistenceError`` 子类；默认码
  ``replay_mismatch``；D7 fail-loud 单错误族）；
- :func:`replay_committed` —— 重放入口（零 IO / 零模块状态，D4/D6；同一
  ``(world_state, trace_records, handlers)`` 双跑字节一致，A4）。

算法（SOT §3.4 五步；确定性）：

1. 抽取：``kind == TraceKind.TRANSACTION`` 记录 → ``payload["record"]``
   （``PAYLOAD_RECORD_KEY``）→ ``Transaction``（pydantic 校验，失败 →
   ``ReplayError(schema_invalid)``）；``(record_id, transaction_id)`` 对
   去重（重复 → ``ReplayError``）；
2. 排序：COMMITTED 子集按 ``commit_revision`` 稳定排序（同一 revision
   两笔 → ``ReplayError``，revision 唯一性，Spec §20.1 同族）；
3. 逐笔应用：每笔校验 ``txn.base_revision == world_state.world_revision``
   （断裂 → ``ReplayError``，message 含两侧 revision——A16/AD-4 面）；
   经冻结 ``apply_transaction`` 应用（K2）；``ReducerError`` → wrap
   ``ReplayError``（不静默跳过——AD-5 面）；
4. ABORTED 跳过：非 COMMITTED 事务不驱动状态（A21）；
5. event 重建：``DOMAIN_EVENT`` 记录（``transaction_id`` ∈ 应用集）→
   ``DomainEvent``，按序组装（序 = ``(commit_revision, 事务内 event_ids
   序)``；记录缺失 → ``ReplayError``，fail-loud 不静默丢弃）。

纪律：零 IO（D4——AST 机械可验：无 ``open`` / ``os`` / ``pathlib`` 引用
面）；零时钟 / 零随机（D5/D6）；文档面不出现推理侧 12 名独立词（D2）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import ValidationError

from src.engine_v2.core import (
    PAYLOAD_RECORD_KEY,
    ComponentRegistry,
    DomainEvent,
    EffectHandlerRegistry,
    ReducerError,
    TraceKind,
    TraceRecord,
    Transaction,
    WorldState,
    apply_transaction,
    assert_json_clean,
)
from src.engine_v2.persistence.base import PersistenceError

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ("ReplayResult", "ReplayError", "replay_committed")


@dataclass(frozen=True)
class ReplayResult:
    """重放结果载体（frozen dataclass；D3 JSON-clean 面）。

    - ``final_state``：重放终态（与输入状态零别名——应用路径每步返回新
      状态，输入逐字节不变）；
    - ``base_revision`` / ``final_revision``：起止 revision（恒等
      ``final == base + transactions_applied``）；
    - ``transactions_applied``：应用的 COMMITTED 事务数；
    - ``applied_transaction_ids``：应用序 transaction_id 闭集；
    - ``events``：由 ``DOMAIN_EVENT`` 记录重建的事件（其
      ``transaction_id`` ∈ 应用集），序 = ``(commit_revision, 事务内
      event_ids 序)``。
    """

    final_state: WorldState
    base_revision: int
    final_revision: int
    transactions_applied: int
    applied_transaction_ids: tuple[str, ...]
    events: tuple[DomainEvent, ...]

    def to_dict(self) -> dict[str, object]:
        """JSON-clean 全量面（D3）：终态经冻结序列化面展开 + 计数 +
        event ids。"""
        result: dict[str, object] = {
            "final_state": self.final_state.model_dump(mode="json"),
            "base_revision": self.base_revision,
            "final_revision": self.final_revision,
            "transactions_applied": self.transactions_applied,
            "applied_transaction_ids": list(self.applied_transaction_ids),
            "events": [str(event.event_id) for event in self.events],
        }
        assert_json_clean(result)
        return result


class ReplayError(PersistenceError):
    """T03 replay 错误族（``PersistenceError`` 子类；D7 fail-loud）。

    默认码 ``replay_mismatch``（SOT §3.4）；``code=`` 可显式指定 P8 错误
    码闭集另一成员（如 ``schema_invalid``——trace payload 不合 schema 面）。
    """

    def __init__(self, message: str, *, code: str = "replay_mismatch") -> None:
        super().__init__(code, message)


def replay_committed(
    world_state: WorldState,
    trace_records: Sequence[TraceRecord],
    *,
    handlers: EffectHandlerRegistry | None = None,
    component_registry: ComponentRegistry | None = None,
) -> ReplayResult:
    """重建 COMMITTED 事务序终态（SOT §3.4 算法；零 IO、零模块状态）。

    步骤逐面（module docstring 算法 1–5）：

    - 抽取/校验/去重：TRANSACTION 记录 payload 缺失或非法 →
      ``ReplayError(schema_invalid)``；``(record_id, transaction_id)`` 对
      重复 → ``ReplayError``；
    - 排序：COMMITTED 子集按 ``commit_revision`` 稳定排序；同一 revision
      两笔 → ``ReplayError``（revision 唯一性）；
    - 应用：每笔 ``base_revision`` 连续性校验（message 含两侧 revision，
      A16/AD-4 面）；``ReducerError`` → wrap ``ReplayError``（不静默跳过，
      AD-5 面）；ABORTED 不驱动状态（A21）；
    - event 重建：以应用事务 ``event_ids`` 为序源、``DOMAIN_EVENT`` 记录
      为体源；缺失 → ``ReplayError``；应用事务未声明的 event 记录 →
      ``ReplayError``（trace/txn 声明不一致，fail-loud）。

    语义型 effect 的 handler 经 ``handlers`` 注入（None = 冻结默认
    registry，R1 注入面）；``component_registry`` 非 None 时结构效果按
    注册 schema 校验（与正常管道同面，K2）。
    """
    # —— 步骤 1：抽取 / 校验 / 去重 ——
    transactions: list[Transaction] = []
    seen_pairs: set[tuple[str, str]] = set()
    for record in trace_records:
        if record.kind is not TraceKind.TRANSACTION:
            continue
        try:
            transaction = Transaction.model_validate(record.payload[PAYLOAD_RECORD_KEY])
        except (KeyError, ValidationError) as exc:
            raise ReplayError(
                code="schema_invalid",
                message=(
                    f"TRANSACTION 记录 payload 缺失或非法"
                    f"（record_id={record.record_id}）：{exc}"
                ),
            ) from exc
        pair = (str(record.record_id), str(transaction.transaction_id))
        if pair in seen_pairs:
            raise ReplayError(
                message=(
                    f"TRANSACTION 记录重复"
                    f"（record_id={record.record_id}，"
                    f"transaction_id={transaction.transaction_id}）"
                )
            )
        seen_pairs.add(pair)
        transactions.append(transaction)

    # —— 步骤 2：COMMITTED 稳定排序 + revision 唯一性 ——
    # COMMITTED ⟺ commit_revision 非空（Transaction 原子不变量；
    # status 枚举不在本模块消费面内，经不变量等价判定）。
    committed = [txn for txn in transactions if txn.commit_revision is not None]
    committed.sort(key=lambda txn: int(txn.commit_revision))
    seen_revisions: set[int] = set()
    for txn in committed:
        revision = int(txn.commit_revision)
        if revision in seen_revisions:
            raise ReplayError(message=f"commit_revision 重复：{revision}")
        seen_revisions.add(revision)

    # —— 步骤 3/4：逐笔连续性校验 + 应用（ABORTED 不在 committed，A21）——
    state = world_state
    base_revision = int(state.world_revision)
    applied_transaction_ids: list[str] = []
    for txn in committed:
        if int(txn.base_revision) != int(state.world_revision):
            raise ReplayError(
                message=(
                    f"base_revision 断裂：transaction {txn.transaction_id} "
                    f"base_revision={int(txn.base_revision)} != "
                    f"world_revision={int(state.world_revision)}"
                )
            )
        try:
            state = apply_transaction(
                state,
                txn,
                component_registry=component_registry,
                handlers=handlers,
            )
        except ReducerError as exc:
            raise ReplayError(
                message=f"apply_transaction 失败（transaction {txn.transaction_id}）：{exc}"
            ) from exc
        applied_transaction_ids.append(str(txn.transaction_id))

    # —— 步骤 5：event 重建（序 = (commit_revision, 事务内 event_ids 序)）——
    event_records: list[tuple[TraceRecord, DomainEvent]] = []
    for record in trace_records:
        if record.kind is not TraceKind.DOMAIN_EVENT:
            continue
        try:
            event = DomainEvent.model_validate(record.payload[PAYLOAD_RECORD_KEY])
        except (KeyError, ValidationError) as exc:
            raise ReplayError(
                code="schema_invalid",
                message=(
                    f"DOMAIN_EVENT 记录 payload 缺失或非法"
                    f"（record_id={record.record_id}）：{exc}"
                ),
            ) from exc
        event_records.append((record, event))

    events_index: dict[tuple[str, str], DomainEvent] = {}
    for record, event in event_records:
        key = (str(record.transaction_id), str(event.event_id))
        if key in events_index:
            raise ReplayError(
                message=(
                    f"DOMAIN_EVENT 记录重复：transaction {record.transaction_id} "
                    f"event_id={event.event_id}（record_id={record.record_id}）"
                )
            )
        events_index[key] = event

    committed_event_keys: set[tuple[str, str]] = set()
    ordered_events: list[DomainEvent] = []
    for txn in committed:
        for event_id in txn.event_ids:
            key = (str(txn.transaction_id), str(event_id))
            committed_event_keys.add(key)
            event = events_index.get(key)
            if event is None:
                raise ReplayError(
                    message=(
                        f"DOMAIN_EVENT 记录缺失：transaction {txn.transaction_id} "
                        f"event_id={event_id}"
                    )
                )
            ordered_events.append(event)

    applied_set = set(applied_transaction_ids)
    for record, event in event_records:
        if record.transaction_id is None:
            continue
        if str(record.transaction_id) not in applied_set:
            continue
        key = (str(record.transaction_id), str(event.event_id))
        if key not in committed_event_keys:
            raise ReplayError(
                message=(
                    f"DOMAIN_EVENT 记录未被应用事务声明：transaction "
                    f"{record.transaction_id} event_id={event.event_id}"
                    f"（record_id={record.record_id}）"
                )
            )

    return ReplayResult(
        final_state=state,
        base_revision=base_revision,
        final_revision=int(state.world_revision),
        transactions_applied=len(applied_transaction_ids),
        applied_transaction_ids=tuple(applied_transaction_ids),
        events=tuple(ordered_events),
    )
