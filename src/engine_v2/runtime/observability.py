"""T8 runtime 可观测面（contract §1 / runtime-closure 计划 T8 卡）：
RuntimeTraceSink 协议 + InMemoryTraceSink production 内存实现。

冻结 seam（docs/plans/runtime_closure_contract.md）：

- §1 ``WorldInstance.trace_sink: RuntimeTraceSink``——本模块是该类型的
  唯一来源：``from src.engine_v2.runtime.observability import
  RuntimeTraceSink``（runtime/world_instance.py 的 TYPE_CHECKING 引用
  解析到本文件）；
- Protocol 三方法同名同签名 = ``llm.policy.TraceSink``（P6 宿主注入面、
  K6 接线面、三方法封闭，llm/policy.py L74-105）——InMemoryTraceSink
  结构化满足该协议；两个协议均**非** runtime_checkable（"结构化使用"，
  宿主侧零 isinstance 断言）。

语义（K7 确定性 / 零 IO / 零 wall-clock）：

- ``record`` = append-only 结构化事件流：存 (kind, payload) + 自增序号
  （seq = 流内位置，0-based）——不掺时间戳 / uuid / 随机，同一调用
  序列 ⇒ 同一流；
- ``store_artifact`` = 同 ref 幂等覆盖（后写胜；P6 确定性句柄
  prompt:// / output://，artifact 本体不落盘，落盘方式归宿主）；
- ``record_diagnostic`` = 独立诊断通道（F-02 / D-P6-22：诊断与记录
  分离，append-only，不进 ``record`` 的封闭键集）。

实现选择（T8 记录）：InMemoryTraceSink 内部 list + dict 存储，读面孔
为 property 投影（records → 新 tuple / artifacts → 浅 dict 拷贝 /
diagnostics → 新 tuple，每次访问重建）——O(1) append；读方拿到不可变
快照，外部对返回容器的变异不污染 sink 状态（append-only 在读面孔
层面成立）。

记录面纪律：payload 的 JSON-clean 校验归调用方（P6 已保证 kind 词表 +
payload 键集封闭，D-P6-22）——sink 不重复校验；读面孔提供
``TraceEvent.to_dict()``（kind/seq/payload 直出）供 T9/E2E 断言。

不做：Web Inspector / trace 持久化 / replay / 文件 IO / 时间戳——存储
介质属 PersistenceBackend 面（Spec §30.3，Plan P8），不属本模块。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from src.engine_v2.prompts.diagnostic import RuntimeDiagnostic

__all__ = ["InMemoryTraceSink", "RuntimeTraceSink", "TraceEvent"]


class RuntimeTraceSink(Protocol):
    """P6 TraceSink 结构超集（record/store_artifact/record_diagnostic 三方法同名同签名）。"""

    def record(self, kind: str, payload: dict[str, object]) -> None:
        """记录一条结构化事件（kind 词表 / payload 键集封闭 = P6 面）。"""
        ...

    def store_artifact(self, ref: str, artifact: object) -> None:
        """确定性句柄存 artifact 本体（prompt:// / output://）。"""
        ...

    def record_diagnostic(self, diag: "RuntimeDiagnostic") -> None:
        """独立诊断通道（F-02：诊断与记录分离）。"""
        ...


@dataclass(frozen=True, slots=True)
class TraceEvent:
    """一条已记录事件（读面孔元素；最小面 = seq/kind/payload）。

    - ``seq``：流内位置（0-based 自增，K7 确定性——不掺时间戳 / uuid）；
    - ``kind`` / ``payload``：调用方提供原样（JSON-clean 归调用方保证，
      P6 键集封闭；sink 不重复校验）；
    - 元素 frozen + slots：记录流不可事后改写（append-only 在读面孔
      层面成立）。
    """

    seq: int
    kind: str
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        """JSON-clean 投影（kind/seq/payload 直出，供 T9/E2E 断言）。"""
        return {"seq": self.seq, "kind": self.kind, "payload": self.payload}


@dataclass(slots=True)
class InMemoryTraceSink:
    """production 内存实现（确定性、零 IO、零 wall-clock）。

    结构化满足 ``llm.policy.TraceSink``（三方法同名同签名，非
    runtime_checkable）；读面孔 = property 投影（不可变快照）：

    - ``records``：按记录序 tuple（元素 :class:`TraceEvent`，seq 自 0
      自增）；
    - ``artifacts``：dict[ref, artifact]（同 ref 幂等覆盖，后写胜）；
    - ``diagnostics``：按记录序 tuple（:class:`RuntimeDiagnostic`）。

    实现 assumption（T8 记录）：内部 list/dict + property 投影（每次
    访问重建 tuple / 浅 dict 拷贝），O(1) append；外部对返回容器的
    变异不污染 sink 状态。
    """

    _events: list[TraceEvent] = field(default_factory=list, repr=False)
    _artifacts: dict[str, object] = field(default_factory=dict, repr=False)
    _diagnostics: list[RuntimeDiagnostic] = field(default_factory=list, repr=False)

    # —— 读面孔（property 投影）——

    @property
    def records(self) -> tuple[TraceEvent, ...]:
        """记录流（按记录序；元素不可变）。"""
        return tuple(self._events)

    @property
    def artifacts(self) -> dict[str, object]:
        """artifact 库（ref → artifact 本体）。"""
        return dict(self._artifacts)

    @property
    def diagnostics(self) -> tuple[RuntimeDiagnostic, ...]:
        """诊断通道（按记录序）。"""
        return tuple(self._diagnostics)

    # —— 写面孔（Protocol 三方法；同名同签名 = llm.policy.TraceSink）——

    def record(self, kind: str, payload: dict[str, object]) -> None:
        """追加一条结构化事件：(kind, payload) + 自增 seq（0-based）。"""
        self._events.append(TraceEvent(seq=len(self._events), kind=kind, payload=payload))

    def store_artifact(self, ref: str, artifact: object) -> None:
        """同 ref 幂等覆盖（后写胜）。"""
        self._artifacts[ref] = artifact

    def record_diagnostic(self, diag: RuntimeDiagnostic) -> None:
        """追加一条运行时诊断（独立通道，不进 record 封闭键集）。"""
        self._diagnostics.append(diag)
