"""P8 持久化基面：错误族 / 布局闭集 / 抽象后端面 / save 载体。

本模块是 ``src.engine_v2.persistence`` 包基面（P8 T01a，SOT §3.1）：

- :data:`PERSISTENCE_FORMAT_VERSION` —— P8 持久化信封格式世代（P8-INV-10
  三层版本之 P8 层；core 层 ``SNAPSHOT_FORMAT_VERSION`` 与契约层
  ``CONTRACT_SCHEMA_VERSION`` 各层自治，load 时经冻结
  ``check_snapshot_versions`` 交叉校验）；
- :data:`PERSISTENCE_SAVE_FILES` —— 单 save 目录闭集布局（P8-INV-5），
  load 侧布局校验依据（额外文件 → ``layout_violation``）；
- :data:`SAVE_ID_PATTERN` —— ``save_id`` 词法面（host 给出，K7 零生成，D5）；
- :data:`P8_ERROR_CODES` —— P8 错误码 11 码闭集（D7 fail-loud；单异常面）；
- :class:`PersistenceError` —— P8 两包唯一异常基类（S2 单面）；ctor 校验
  ``code`` ∈ 闭集（闭集外 → ``ValueError``，编程错误面）；
- :class:`PersistenceBackend` —— 3 方法抽象面（Spec §30.3 MAY 的 P8
  单一定义，D-P8-03）；
- :class:`SaveBundle` —— save 载体（frozen dataclass；``to_dict`` JSON-clean，
  D3）。

纪律：本模块零 IO（全部文件 IO 收拢于 ``filesystem.py``，D4）；零时钟 /
零随机（D5/D6）；文档面不出现推理侧 12 名独立词（D2）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol, runtime_checkable

from src.engine_v2.core import assert_json_clean

if TYPE_CHECKING:
    from src.engine_v2.core import TraceRecord
    from src.engine_v2.persistence.snapshot import PersistenceSnapshot

__all__ = (
    "PERSISTENCE_FORMAT_VERSION",
    "PERSISTENCE_SAVE_FILES",
    "SAVE_ID_PATTERN",
    "P8_ERROR_CODES",
    "PersistenceError",
    "PersistenceBackend",
    "SaveBundle",
)

#: P8 持久化信封格式世代（P8-INV-10 三层版本之 P8 层）。
PERSISTENCE_FORMAT_VERSION: Final[int] = 1

#: 单 save 目录闭集布局（P8-INV-5）：快照信封 / checkpoint 体目录 /
#: trace JSONL。load 侧布局校验依据（闭集外任何文件 → ``layout_violation``）。
PERSISTENCE_SAVE_FILES: Final[tuple[str, ...]] = (
    "snapshot.json",
    "checkpoints",
    "trace.jsonl",
)

#: ``save_id`` 词法（host 给出，D5）：小写字母数字开头，下划线/字母数字延续，
#: 总长 1..128。
SAVE_ID_PATTERN: Final[str] = r"[a-z0-9][a-z0-9_]{0,127}"

#: P8 错误码 11 码闭集（D7 fail-loud；单异常面 code 维度）。
P8_ERROR_CODES: Final[tuple[str, ...]] = (
    "save_not_found",
    "corrupt_file",
    "schema_invalid",
    "version_mismatch",
    "layout_violation",
    "checkpoint_unavailable",
    "replay_mismatch",
    "branch_rejected",
    "intervention_rejected",
    "usage_error",
    "internal_error",
)


class PersistenceError(Exception):
    """P8 两包唯一异常基类（S2 单面；D7 fail-loud）。

    - ``code`` ∈ :data:`P8_ERROR_CODES`（ctor 闭集校验；闭集外 →
      ``ValueError`` —— 编程错误，不属 P8 错误面）；
    - ``message``：人读细节（确定性字符串，D6）；
    - ``str(exc) = "[code] message"``（稳定面；CLI / trace_query 面可依赖）。
    """

    def __init__(self, code: str, message: str) -> None:
        if code not in P8_ERROR_CODES:
            raise ValueError(
                f"PersistenceError.code {code!r} 不在 P8_ERROR_CODES 闭集："
                f"{P8_ERROR_CODES}"
            )
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


@runtime_checkable
class PersistenceBackend(Protocol):
    """持久化后端抽象面（Spec §30.3 MAY 的 P8 单一定义；D-P8-03）。

    3 方法面（全 keyword-only；D6 确定性）：

    - ``save(*, save_id, envelope, checkpoint_payloads, trace_records) ->
      None`` —— 全量写入（同 id 再存 = 整体覆盖，确定性 winner）；
    - ``load(*, save_id) -> SaveBundle`` —— 全量读出（布局闭集校验 +
      版本交叉校验；D7 fail-loud）；
    - ``list_saves() -> tuple[str, ...]`` —— index 键排序（确定性）。
    """

    def save(
        self,
        *,
        save_id: str,
        envelope: PersistenceSnapshot,
        checkpoint_payloads: Mapping[str, Mapping[str, object]],
        trace_records: Sequence[TraceRecord],
    ) -> None:
        ...

    def load(self, *, save_id: str) -> SaveBundle:
        ...

    def list_saves(self) -> tuple[str, ...]:
        ...


@dataclass(frozen=True)
class SaveBundle:
    """save 载体（frozen dataclass；D3 JSON-clean 面）。

    - ``save_id``：host 给出的词法 id（:data:`SAVE_ID_PATTERN`）；
    - ``envelope``：``PersistenceSnapshot`` 信封（嵌套 core ``Snapshot``）；
    - ``checkpoint_payloads``：backend_id → checkpoint 体（JSON-clean dict，
      体面；信封 ``backend_checkpoints`` 只存 ref 面）；
    - ``trace_records``：``TraceRecord`` 全量序列（文件序保序）。
    """

    save_id: str
    envelope: PersistenceSnapshot
    checkpoint_payloads: Mapping[str, Mapping[str, object]]
    trace_records: tuple[TraceRecord, ...]

    def to_dict(self) -> dict[str, object]:
        """JSON-clean 全量面（D3）：各成员经冻结序列化面展开后断言 clean。"""
        result: dict[str, object] = {
            "save_id": self.save_id,
            "envelope": self.envelope.to_dict(),
            "checkpoint_payloads": {
                str(backend_id): dict(payload)
                for backend_id, payload in self.checkpoint_payloads.items()
            },
            "trace_records": [record.model_dump(mode="json") for record in self.trace_records],
        }
        assert_json_clean(result)
        return result
