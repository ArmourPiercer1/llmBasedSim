"""T8 测试面：RuntimeTraceSink 协议 + InMemoryTraceSink（production 内存 trace）。

覆盖 = 任务卡 Gate 1-4 + 确定性 / 读面孔纪律补充：

1. ``record`` 两条（llm_call / prompt_assembly）→ records 按序可读 +
   序号递增；
2. ``store_artifact`` 同 ref 两次 → 后者覆盖 + artifacts 恰 1 项；
3. ``record_diagnostic`` 一条 RuntimeDiagnostic → diagnostics 可读；
4. 结构断言：三方法 hasattr + 签名参数名与 ``llm.policy.TraceSink``
   一致（inspect 机械面；两协议均非 runtime_checkable，不做
   isinstance）。

纪律：断言零时间戳 / 零 uuid / 零文件 IO；import 风格统一
``from src.engine_v2...``。
"""

from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError

import pytest

from src.engine_v2.content.schemas import DiagnosticSeverity
from src.engine_v2.llm.policy import TraceSink as LLMPolicyTraceSink
from src.engine_v2.prompts.diagnostic import RuntimeDiagnostic
from src.engine_v2.runtime.observability import (
    InMemoryTraceSink,
    RuntimeTraceSink,
    TraceEvent,
)


def _make_diag() -> RuntimeDiagnostic:
    """最小 RuntimeDiagnostic（21 码闭集 PROMPT 族 1 码，确定性文本）。"""
    return RuntimeDiagnostic(
        code="LLMSIM_PROMPT_TEMPLATE_MISSING",
        severity=DiagnosticSeverity.ERROR,
        path="policies/npc_policy",
        message="template missing: tpl/attack",
    )


# —— Gate 1：record 按序 + seq 递增 ——


def test_record_appends_in_order_with_increasing_seq() -> None:
    sink = InMemoryTraceSink()
    sink.record("llm_call", {"profile": "npc_policy", "latency_ms": 12})
    sink.record("prompt_assembly", {"actor_id": "ent_alice", "tick": 7})

    events = sink.records
    assert isinstance(events, tuple)
    assert len(events) == 2
    assert [event.kind for event in events] == ["llm_call", "prompt_assembly"]
    assert events[0].payload == {"profile": "npc_policy", "latency_ms": 12}
    assert events[1].payload == {"actor_id": "ent_alice", "tick": 7}
    # seq 0-based 自增 + 严格递增（K7：不掺时间戳 / uuid）
    assert [event.seq for event in events] == [0, 1]
    assert all(b.seq > a.seq for a, b in zip(events, events[1:]))
    # 读面孔元素不可变（append-only 在读面孔层面成立）
    with pytest.raises(FrozenInstanceError):
        events[0].kind = "tampered"


def test_record_to_dict_is_json_clean_projection() -> None:
    sink = InMemoryTraceSink()
    sink.record("llm_call", {"profile": "npc_policy"})

    (event,) = sink.records
    assert isinstance(event, TraceEvent)
    # kind/seq/payload 直出（T9/E2E 断言面）
    assert event.to_dict() == {
        "seq": 0,
        "kind": "llm_call",
        "payload": {"profile": "npc_policy"},
    }


# —— Gate 2：store_artifact 同 ref 幂等覆盖 ——


def test_store_artifact_same_ref_overwrites_idempotently() -> None:
    sink = InMemoryTraceSink()
    sink.store_artifact("prompt://ent_alice:7:3", {"summary": "v1"})
    sink.store_artifact("prompt://ent_alice:7:3", {"summary": "v2"})

    artifacts = sink.artifacts
    # 同 ref 覆盖：artifacts 恰 1 项，值 = 后写
    assert len(artifacts) == 1
    assert artifacts == {"prompt://ent_alice:7:3": {"summary": "v2"}}


def test_store_artifact_distinct_refs_coexist() -> None:
    sink = InMemoryTraceSink()
    sink.store_artifact("prompt://ent_alice:7:3", {"summary": "p"})
    sink.store_artifact("output://ent_alice:7:3", {"text": "wire"})

    assert set(sink.artifacts) == {"prompt://ent_alice:7:3", "output://ent_alice:7:3"}


# —— Gate 3：record_diagnostic 可读 ——


def test_record_diagnostic_appends_readable() -> None:
    sink = InMemoryTraceSink()
    sink.record_diagnostic(_make_diag())
    sink.record_diagnostic(_make_diag())

    diags = sink.diagnostics
    assert isinstance(diags, tuple)
    assert len(diags) == 2
    assert all(isinstance(d, RuntimeDiagnostic) for d in diags)
    assert diags[0].code == "LLMSIM_PROMPT_TEMPLATE_MISSING"
    assert diags[0].severity is DiagnosticSeverity.ERROR


# —— Gate 4：结构面（llm.policy.TraceSink 同名同签名，机械断言）——


def test_structurally_satisfies_llm_policy_trace_sink() -> None:
    """三方法 hasattr + 签名参数名与 llm.policy.TraceSink 一致（非 isinstance）。"""
    sink = InMemoryTraceSink()
    for method_name in ("record", "store_artifact", "record_diagnostic"):
        assert hasattr(sink, method_name)
        proto_sig = inspect.signature(getattr(LLMPolicyTraceSink, method_name))
        impl_sig = inspect.signature(getattr(InMemoryTraceSink, method_name))
        # 参数名逐位一致（self + 冻结参数名）
        assert list(impl_sig.parameters) == list(proto_sig.parameters)
        # 返回注解一致（两模块均 PEP 563："None"）
        assert impl_sig.return_annotation == proto_sig.return_annotation


def test_world_instance_trace_sink_annotation_binds_this_protocol() -> None:
    """contract §1：WorldInstance.trace_sink 注解名 = 本模块 Protocol 名。"""
    from src.engine_v2.runtime.world_instance import WorldInstance

    field_type = WorldInstance.__dataclass_fields__["trace_sink"].type
    assert field_type == RuntimeTraceSink.__name__


# —— 补充：K7 确定性 + 读面孔投影语义 ——


def test_same_call_sequence_yields_identical_streams() -> None:
    def drive(target: InMemoryTraceSink) -> None:
        target.record("llm_call", {"profile": "npc_policy"})
        target.store_artifact("prompt://ent_alice:7:3", {"summary": "p"})
        target.record_diagnostic(_make_diag())
        target.record("prompt_assembly", {"actor_id": "ent_alice", "tick": 7})

    first, second = InMemoryTraceSink(), InMemoryTraceSink()
    drive(first)
    drive(second)

    # K7 确定性：无隐藏时间 / 随机源，同输入序列 ⇒ 同流
    assert first.records == second.records
    assert first.artifacts == second.artifacts
    assert first.diagnostics == second.diagnostics


def test_read_faces_are_defensive_projections() -> None:
    sink = InMemoryTraceSink()
    sink.record("llm_call", {"profile": "npc_policy"})
    sink.store_artifact("prompt://ent_alice:7:3", {"summary": "p"})

    records_view = sink.records
    artifacts_view = sink.artifacts
    diagnostics_view = sink.diagnostics
    artifacts_view["rogue_ref"] = object()

    # 外部对返回容器的变异不污染 sink 状态（property 投影语义）
    assert "rogue_ref" not in sink.artifacts
    assert len(sink.records) == 1
    assert records_view[0].kind == "llm_call"
    assert diagnostics_view == ()
