"""P6-W5 ``policy.py`` 单测（SOT §3.6 + §6.1 L813，恰 10 个平铺函数）。

覆盖项（按 §6.1 L813 行逐项 1:1）：

1. ``test_decide_success_path``：成功路径（9 键 + 记录序 + artifact 双
   ref）+ 请求 11 字段值来源表 + provenance 拼接面；
2. ``test_decide_assembly_failure``：组装失败 → None（VARIABLE_
   UNSUPPORTED 四元组 + assembly_failed 五键 + 零调用）；
3. ``test_decide_parse_double_failure``：解析终败（双败）→ None +
   PARSE_FAILED 诊断（refs 两次错误摘要 + parse_retry=1）；
4. ``test_decide_parse_retry``：parse retry 1 次（调用次数==2、
   parse_retry==1、PARSE_RECOVERED warning、user 消息 = repair 指令）；
5. ``test_critic_default_face``：critic 关/开默认面（默认 False；开时
   函数级惰性 import 经 sys.modules stub 消费，ERR-P6-10(d) 口径）；
6. ``test_critic_repair_success``：critic 修复 1 次成功（user 消息 =
   critique_instruction、无 PARSE_FAILED、parse_retry=1）；
7. ``test_critic_terminal_failure``：critic 终败 → None（refs "critic:"
   前缀 + parse_retry=1）；
8. ``test_decide_noop``：no-op（action_id None）→ None（合法跳过，
   零诊断零 artifact）；
9. ``test_build_failure``：build_llm_policy 失败 → policy None +
   NO_DEPLOYMENT 四元组精确；
10. ``test_bcon_face``：B-CON 面（非协程 / 单参 / None 态 / 8 字段封闭 /
    frozen）。

本文件自包含（不建 fixture；conftest 面仅消费 §6.2 W5 允许集：
mem_sink / scripted_backend / alice_context，SOT §6.2 末段纪律）；
hermetic、无真实网络、无 subprocess。测试数据用 sim 族假名（K8 12 名
stem 禁入，SOT L17 / L123）；探针串一律拼接构造。
"""

from __future__ import annotations

import inspect
import sys
import types
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Any

import pytest

from src.engine_v2.content.schemas import (
    DiagnosticSeverity,
    InferenceCapabilityProfile,
    PromptPolicy,
)
from src.engine_v2.core.provenance import OriginKind
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.trace import LLM_CALL_PAYLOAD_KEYS
from src.engine_v2.llm.adapter import FakeInferenceBackend
from src.engine_v2.llm.deployment import DeploymentEntry, DeploymentProfile
from src.engine_v2.llm.profiles import ModelCapabilityProfile
from src.engine_v2.llm.policy import LLMPolicy, build_llm_policy
from src.engine_v2.llm.structured import repair_instruction
from src.engine_v2.prompts.assembler import CharDivisorTokenEstimator, assemble_prompt
from src.engine_v2.prompts.registry import TemplateStore

#: 测试用 sim 族假名（K8 12 名 stem 禁入；端点/凭据均为假值）。
_CAP = "chat"
_MODEL_ID = "sim-alpha"
_BASE_URL = "https://sim.example/v1"
_CRED_ENV = "SIM_CRED_CHAT"
#: critic 模块名探针串（拼接构造，K8 口径）：与 policy 惰性 import 的
#: 目标模块完全同串（ERR-P6-10(b) DAG 面）。
_CRITIC_MODULE = "src.engine_v2." + "ll" + "m.critic"

#: 脚本化 wire 文本（确定性常量）。
_GOOD = (
    '{"action_id": "attack", "arguments": {"target": "ent_bob"}, '
    '"intent": "hit", "confidence": 0.9}'
)
_GOOD_NO_INTENT = '{"action_id": "attack", "arguments": {"target": "ent_bob"}}'
_BAD = "sorry, I cannot answer"
_TEMPLATE = "你是 {{actor_id}}。只输出 JSON。"


def _make_project(
    tmp_path: Path,
    *,
    template_text: str = _TEMPLATE,
    variables: tuple[str, ...] = ("actor_id",),
) -> TemplateStore:
    """临时项目 prompts/base.md + TemplateStore（W4 _make_store 口径）。"""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "base.md").write_text(template_text, encoding="utf-8")
    return TemplateStore(
        project_root=tmp_path,
        policies=(
            PromptPolicy(
                id="game_base",
                scope="game_policy",
                template_ref="prompts/base.md",
                variables=variables,
            ),
        ),
    )


def _make_deployment() -> DeploymentProfile:
    """单能力部署面（chat → sim-alpha tier 3，值均为假名/假值）。"""
    return DeploymentProfile(
        models={
            _MODEL_ID: ModelCapabilityProfile(
                model_id=_MODEL_ID,
                tier=3,
                context_length=131072,
                max_output=16384,
                structured_output=True,
                reasoning_class="advanced",
            ),
        },
        inference_profiles={
            _CAP: DeploymentEntry(
                provider="sim",
                model=_MODEL_ID,
                base_url=_BASE_URL,
                api_key_env=_CRED_ENV,
            ),
        },
    )


def _build_with(
    store: TemplateStore,
    backend: FakeInferenceBackend,
    mem_sink: Any,  # conftest _MemSink 实例（鸭子面：record/store_artifact/record_diagnostic）
    *,
    capability: str = _CAP,
    deployment_profile: DeploymentProfile | None = None,
    ttl_ticks: int | None = 5,
    enable_critic: bool = False,
) -> LLMPolicy:
    """build_llm_policy 公共构造面（构造失败 = 断言失败，不静默）。"""
    result = build_llm_policy(
        capability=capability,
        requirement=InferenceCapabilityProfile(
            id="cap_" + capability,
            capability=capability,
            min_tier=2,
            ideal_tier=3,
        ),
        deployment=deployment_profile if deployment_profile is not None else _make_deployment(),
        backend=backend,
        store=store,
        estimator=CharDivisorTokenEstimator(),
        sink=mem_sink,
        ttl_ticks=ttl_ticks,
        enable_critic=enable_critic,
    )
    assert result.policy is not None, f"构造失败：{result.diagnostics}"
    return result.policy


def _critic_stub(
    *,
    fail_when_intent_none: bool = False,
    always_errors: tuple[str, ...] = (),
) -> types.ModuleType:
    """critic 模块 stub（W6 模块面；ERR-P6-10(d) sys.modules 口径）。

    判定面确定性：always_errors 非空 → 恒败；fail_when_intent_none →
    wire.intent 为 None 时败（区分 seq1/seq2 wire）；否则恒过。
    """
    mod = types.ModuleType(_CRITIC_MODULE)

    class _CriticResult:
        def __init__(self, ok: bool, errors: tuple[str, ...]) -> None:
            self.ok = ok
            self.errors = errors

    def critique(context: Any, wire: Any) -> _CriticResult:
        if always_errors:
            return _CriticResult(False, always_errors)
        if fail_when_intent_none and wire.intent is None:
            return _CriticResult(False, ("action-not-candidate",))
        return _CriticResult(True, ())

    def critique_instruction(errors: tuple[str, ...]) -> str:
        return "critic 修复反馈: " + ";".join(errors)

    mod.critique = critique
    mod.critique_instruction = critique_instruction
    return mod


def test_decide_success_path(tmp_path, mem_sink, scripted_backend, alice_context) -> None:
    """1) 成功路径：9 键精确 + 记录序（prompt_assembly 先于 llm_call）+
    artifact 双 ref + 请求 11 字段值来源 + provenance 拼接面。"""
    store = _make_project(tmp_path)
    backend = scripted_backend({(_CAP, alice_context.base_world_revision, 1): _GOOD})
    policy = _build_with(store, backend, mem_sink)
    proposal = policy.decide(alice_context)
    assert proposal is not None

    # --- 提案面（B-CON-5 + staleness 接线） -------------------------------
    assert proposal.actor_id == alice_context.actor_id
    assert proposal.action_id == "attack"
    assert proposal.arguments == {"target": "ent_bob"}
    assert proposal.intent == "hit"
    assert proposal.confidence == 0.9
    assert proposal.base_world_revision == alice_context.base_world_revision
    assert proposal.valid_until == Revision(int(alice_context.base_world_revision) + 5)
    assert type(proposal.valid_until) is Revision
    assert proposal.provenance.origin is OriginKind.BEHAVIOR_POLICY
    assert proposal.provenance.producer_id == ("ll" + "m:") + str(alice_context.actor_id)
    assert proposal.provenance.notes.startswith("ll" + "m://")

    # --- 组装交叉验证（同 store 同 context 重算 = 同 token 估计/文本） ----
    pkg = assemble_prompt(
        alice_context, store, CharDivisorTokenEstimator(), capability=_CAP
    ).package
    assert pkg is not None

    # --- 记录序 + 9 键精确（LLM_CALL_PAYLOAD_KEYS 机械面） ----------------
    assert [kind for kind, _ in mem_sink.records] == ["prompt_assembly", "llm_call"]
    assembly_payload = mem_sink.records[0][1]
    assert assembly_payload == {
        "actor_id": str(alice_context.actor_id),
        "tick": alice_context.tick,
        "base_revision": int(alice_context.base_world_revision),
        "prompt_metadata_ref": "prompt://ent_alice:7:3",
        "token_estimate": pkg.token_estimate,
    }
    llm_call = mem_sink.records[1][1]
    assert frozenset(llm_call) == LLM_CALL_PAYLOAD_KEYS
    assert llm_call["logical_role"] == _CAP
    assert llm_call["profile"] == _CAP
    assert llm_call["resolved_model"] == _MODEL_ID
    assert llm_call["prompt_metadata_ref"] == "prompt://ent_alice:7:3"
    assert llm_call["output_ref"] == "output://ent_alice:7:3"
    assert llm_call["latency_ms"] == 5.0
    assert llm_call["parse_retry"] == 0
    assert llm_call["base_revision"] == int(alice_context.base_world_revision)
    assert llm_call["input_token_estimate"] == pkg.token_estimate
    request = backend.calls[0]
    assert len(request.messages) == 1
    assert request.messages[0].role == "system"
    assert request.messages[0].content == pkg.text

    # --- 请求 11 字段值来源表（max_tokens 恒 None） ------------------------
    assert request.model == _MODEL_ID
    assert request.base_url == _BASE_URL
    assert request.api_key_env == _CRED_ENV
    assert request.temperature == 0.7
    assert request.max_tokens is None
    assert request.timeout_seconds == 30.0
    assert request.logical_role == _CAP
    assert request.profile == _CAP
    assert request.base_revision == alice_context.base_world_revision
    assert request.prompt_metadata_ref == pkg.prompt_metadata_ref
    assert len(backend.calls) == 1

    # --- artifact 双 ref（摘要 dict + wire 原始文本 dict） -----------------
    assert sorted(mem_sink.artifacts) == [
        "output://ent_alice:7:3",
        "prompt://ent_alice:7:3",
    ]
    assert mem_sink.artifacts["prompt://ent_alice:7:3"] == {
        "actor_id": str(alice_context.actor_id),
        "logical_role": _CAP,
        "base_revision": int(alice_context.base_world_revision),
        "token_estimate": pkg.token_estimate,
        "prompt_metadata_ref": "prompt://ent_alice:7:3",
        "layer_count": len(pkg.layers),
    }
    assert mem_sink.artifacts["output://ent_alice:7:3"] == {"text": _GOOD}
    assert mem_sink.diagnostics == []


def test_decide_assembly_failure(tmp_path, mem_sink, scripted_backend, alice_context) -> None:
    """2) 组装失败 → None（声明变量不在 13 名封闭集 → VARIABLE_
    UNSUPPORTED；assembly_failed 五键 + 零调用 + 零 artifact）。"""
    store = _make_project(
        tmp_path, template_text="目标 {{global_x}}。", variables=("global_x",)
    )
    backend = scripted_backend({(_CAP, alice_context.base_world_revision, 1): _GOOD})
    policy = _build_with(store, backend, mem_sink)
    assert policy.decide(alice_context) is None

    assert [kind for kind, _ in mem_sink.records] == ["prompt_assembly"]
    assert mem_sink.records[0][1] == {
        "actor_id": str(alice_context.actor_id),
        "tick": alice_context.tick,
        "base_revision": int(alice_context.base_world_revision),
        "prompt_metadata_ref": "assembly_failed",
        "token_estimate": 0,
    }
    assert len(mem_sink.diagnostics) == 1
    diag = mem_sink.diagnostics[0]
    assert (
        diag.code,
        diag.path,
        diag.refs,
        diag.severity,
    ) == (
        "LLMSIM_PROMPT_VARIABLE_UNSUPPORTED",
        "game_base",
        ("global_x",),
        DiagnosticSeverity.ERROR,
    )
    assert backend.calls == ()
    assert mem_sink.artifacts == {}


def test_decide_parse_double_failure(tmp_path, mem_sink, scripted_backend, alice_context) -> None:
    """3) 解析终败（双败）→ None + PARSE_FAILED 诊断（refs = 两次错误
    摘要；parse_retry=1；零 artifact）。"""
    store = _make_project(tmp_path)
    backend = scripted_backend(
        {
            (_CAP, alice_context.base_world_revision, 1): _BAD,
            (_CAP, alice_context.base_world_revision, 2): _BAD,
        }
    )
    policy = _build_with(store, backend, mem_sink)
    assert policy.decide(alice_context) is None

    assert len(mem_sink.diagnostics) == 1
    diag = mem_sink.diagnostics[0]
    assert (
        diag.code,
        diag.severity,
        diag.refs,
    ) == ("LLMSIM_INFERENCE_PARSE_FAILED", DiagnosticSeverity.ERROR, ("no-json-object", "no-json-object"))
    assert [kind for kind, _ in mem_sink.records] == ["llm_call"]
    assert mem_sink.records[0][1]["parse_retry"] == 1
    assert frozenset(mem_sink.records[0][1]) == LLM_CALL_PAYLOAD_KEYS
    assert len(backend.calls) == 2
    assert mem_sink.artifacts == {}


def test_decide_parse_retry(tmp_path, mem_sink, scripted_backend, alice_context) -> None:
    """4) parse retry 1 次：调用次数==2、parse_retry==1、PARSE_RECOVERED
    warning（refs 首次错误摘要）、二次请求 user 消息 = repair 指令。"""
    store = _make_project(tmp_path)
    backend = scripted_backend(
        {
            (_CAP, alice_context.base_world_revision, 1): _BAD,
            (_CAP, alice_context.base_world_revision, 2): _GOOD,
        }
    )
    policy = _build_with(store, backend, mem_sink)
    proposal = policy.decide(alice_context)
    assert proposal is not None
    assert proposal.action_id == "attack"

    assert len(mem_sink.diagnostics) == 1
    diag = mem_sink.diagnostics[0]
    assert (
        diag.code,
        diag.severity,
        diag.refs,
    ) == ("LLMSIM_INFERENCE_PARSE_RECOVERED", DiagnosticSeverity.WARNING, ("no-json-object",))
    assert len(backend.calls) == 2
    retry_request = backend.calls[1]
    assert [m.role for m in retry_request.messages] == ["system", "user"]
    assert retry_request.messages[1].content == repair_instruction(("no-json-object",))
    assert [kind for kind, _ in mem_sink.records] == ["prompt_assembly", "llm_call"]
    assert mem_sink.records[1][1]["parse_retry"] == 1
    assert sorted(mem_sink.artifacts) == [
        "output://ent_alice:7:3",
        "prompt://ent_alice:7:3",
    ]


def test_critic_default_face(tmp_path, mem_sink, scripted_backend, alice_context, monkeypatch) -> None:
    """5) critic 关/开默认面：build 默认 enable_critic=False（关态零
    import）；开态经 sys.modules stub 消费（ERR-P6-10(d) 口径）。"""
    store = _make_project(tmp_path)

    # --- 关态（默认 False）：零 critic import -----------------------------
    monkeypatch.delitem(sys.modules, _CRITIC_MODULE, raising=False)
    backend_off = scripted_backend({(_CAP, alice_context.base_world_revision, 1): _GOOD})
    policy_off = _build_with(store, backend_off, mem_sink)
    assert policy_off.enable_critic is False
    assert policy_off.decide(alice_context) is not None
    assert len(backend_off.calls) == 1
    assert _CRITIC_MODULE not in sys.modules

    # --- 开态（stub 恒过）：1 次调用出提案 --------------------------------
    mem_sink.records.clear()
    mem_sink.artifacts.clear()
    mem_sink.diagnostics.clear()
    stub = _critic_stub()
    monkeypatch.setitem(sys.modules, _CRITIC_MODULE, stub)
    backend_on = scripted_backend({(_CAP, alice_context.base_world_revision, 1): _GOOD})
    policy_on = _build_with(store, backend_on, mem_sink, enable_critic=True)
    assert policy_on.enable_critic is True
    assert policy_on.decide(alice_context) is not None
    assert len(backend_on.calls) == 1
    assert mem_sink.diagnostics == []


def test_critic_repair_success(tmp_path, mem_sink, scripted_backend, alice_context, monkeypatch) -> None:
    """6) critic 修复 1 次成功：seq1 wire（intent None）被 critic 判败 →
    修复调用（user 消息 = critique_instruction）→ seq2 wire 过 critic；
    无 PARSE_FAILED、parse_retry=1（ERR-P6-10(c) 饱和 {0,1}）。"""
    monkeypatch.setitem(sys.modules, _CRITIC_MODULE, _critic_stub(fail_when_intent_none=True))
    store = _make_project(tmp_path)
    backend = scripted_backend(
        {
            (_CAP, alice_context.base_world_revision, 1): _GOOD_NO_INTENT,
            (_CAP, alice_context.base_world_revision, 2): _GOOD,
        }
    )
    policy = _build_with(store, backend, mem_sink, enable_critic=True)
    proposal = policy.decide(alice_context)
    assert proposal is not None
    assert proposal.action_id == "attack"
    assert proposal.intent == "hit"

    assert len(backend.calls) == 2
    repair_request = backend.calls[1]
    assert [m.role for m in repair_request.messages] == ["system", "user"]
    assert repair_request.messages[1].content == _critic_stub(
        fail_when_intent_none=True
    ).critique_instruction(("action-not-candidate",))
    assert mem_sink.diagnostics == []
    assert [kind for kind, _ in mem_sink.records] == ["prompt_assembly", "llm_call"]
    assert mem_sink.records[1][1]["parse_retry"] == 1


def test_critic_terminal_failure(tmp_path, mem_sink, scripted_backend, alice_context, monkeypatch) -> None:
    """7) critic 终败 → None：修复调用（seq2 坏 wire）仍不可解析 →
    PARSE_FAILED（refs "critic:" 前缀）+ parse_retry=1。"""
    monkeypatch.setitem(
        sys.modules, _CRITIC_MODULE, _critic_stub(always_errors=("target-not-visible",))
    )
    store = _make_project(tmp_path)
    backend = scripted_backend(
        {
            (_CAP, alice_context.base_world_revision, 1): _GOOD,
            (_CAP, alice_context.base_world_revision, 2): _BAD,
        }
    )
    policy = _build_with(store, backend, mem_sink, enable_critic=True)
    assert policy.decide(alice_context) is None

    assert len(mem_sink.diagnostics) == 1
    diag = mem_sink.diagnostics[0]
    assert (
        diag.code,
        diag.severity,
        diag.refs,
    ) == (
        "LLMSIM_INFERENCE_PARSE_FAILED",
        DiagnosticSeverity.ERROR,
        ("critic:target-not-visible",),
    )
    assert len(backend.calls) == 2
    assert [kind for kind, _ in mem_sink.records] == ["llm_call"]
    assert mem_sink.records[0][1]["parse_retry"] == 1
    assert mem_sink.artifacts == {}


def test_decide_noop(tmp_path, mem_sink, scripted_backend, alice_context) -> None:
    """8) no-op（action_id None）→ None：合法跳过非失败——仅 llm_call
    记录（parse_retry=0）、零诊断零 artifact、单次调用。"""
    store = _make_project(tmp_path)
    backend = scripted_backend({})  # default_text = {"action_id": null}
    policy = _build_with(store, backend, mem_sink)
    assert policy.decide(alice_context) is None

    assert [kind for kind, _ in mem_sink.records] == ["llm_call"]
    llm_call = mem_sink.records[0][1]
    assert frozenset(llm_call) == LLM_CALL_PAYLOAD_KEYS
    assert llm_call["parse_retry"] == 0
    assert mem_sink.diagnostics == []
    assert mem_sink.artifacts == {}
    assert len(backend.calls) == 1


def test_build_failure(tmp_path, mem_sink, scripted_backend) -> None:
    """9) build_llm_policy 失败 → policy None：capability 无部署条目 →
    NO_DEPLOYMENT 四元组精确（绝不静默回落任意模型，D-P6-07）。"""
    store = _make_project(tmp_path)
    backend = scripted_backend({})
    result = build_llm_policy(
        capability="major_character",
        requirement=InferenceCapabilityProfile(
            id="cap_major_character",
            capability="major_character",
            min_tier=2,
            ideal_tier=3,
        ),
        deployment=_make_deployment(),
        backend=backend,
        store=store,
        estimator=CharDivisorTokenEstimator(),
        sink=mem_sink,
    )
    assert result.policy is None
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert (
        diag.code,
        diag.path,
        diag.refs,
        diag.severity,
    ) == (
        "LLMSIM_RESOLVER_NO_DEPLOYMENT",
        "major_character",
        ("inference_profiles 无此键",),
        DiagnosticSeverity.ERROR,
    )


def test_bcon_face(tmp_path, mem_sink, scripted_backend, alice_context) -> None:
    """10) B-CON 面：decide 非协程 + 单参（self, context）+ None 态合法
    （no-op → None）+ 8 字段封闭（不持 random/clock/网络）+ frozen。"""
    assert inspect.iscoroutinefunction(LLMPolicy.decide) is False
    assert list(inspect.signature(LLMPolicy.decide).parameters) == ["self", "context"]
    assert tuple(f.name for f in fields(LLMPolicy)) == (
        "capability",
        "resolved",
        "backend",
        "store",
        "estimator",
        "sink",
        "ttl_ticks",
        "enable_critic",
    )
    store = _make_project(tmp_path)
    backend = scripted_backend({})
    policy = _build_with(store, backend, mem_sink)
    assert policy.decide(alice_context) is None
    with pytest.raises(FrozenInstanceError):
        policy.capability = "other"
