"""T5（runtime closure）test_llm_binding.py：P6 LLMPolicy 绑定面 Gate 覆盖。

覆盖对象 = ``src/engine_v2/runtime/llm_binding.py``（owned surface）。
T5 卡 Gate 逐条：

1. 同 ProjectIR，Deployment A（npc_policy → model X）vs Deployment B（→
   model Y，model 声明在 models 且 tier 满足）→ resolved_models 不同
   （两 actor 分别 = X / Y）；
2. FakeInferenceBackend 脚本（键 = (logical_role="npc_policy", base_revision,
   seq=1)）→ ``policies[npc_id].decide(最小 ActorDecisionContext)`` 产
   ActionProposal 且 ``action_id == "talk"``；
3. deployment 缺 "npc_policy" 条目 → 诊断非空 + 该 actor 无 policy +
   不抛异常；
4. deployment=None → warning 诊断 + policies 空。

纪律：只 import src 冻结面 + 本模块；零真实网络（FakeInferenceBackend）；
最小 context 按 tests/engine_v2/llm/conftest.py ``_make_context`` 先例
（ActorDecisionContext = plain frozen dataclass 无运行时校验，JSON 原生
替代值合法消费）。
"""

from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from src.engine_v2.content.schemas import (
    CharacterSpec,
    Diagnostic,
    DiagnosticSeverity,
    InferenceCapabilityProfile,
    PlayerSpec,
    ProjectIR,
    ProjectManifest,
    ScenarioSpec,
    ScenarioTime,
)
from src.engine_v2.core.actions import ActionProposal, ActionTypeId
from src.engine_v2.core.context_provider import ActorDecisionContext
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.revision import Revision
from src.engine_v2.llm.adapter import FakeInferenceBackend
from src.engine_v2.llm.deployment import DeploymentEntry, DeploymentProfile
from src.engine_v2.llm.policy import LLMPolicy
from src.engine_v2.llm.profiles import ModelCapabilityProfile
from src.engine_v2.runtime.llm_binding import LLMBindingResult, bind_llm_policies

# —— 构造助手（最小 IR / deployment / context）——


def _model(model_id: str, *, tier: int) -> ModelCapabilityProfile:
    """tier 档下限满足的 model 声明（tier 2 / 3 两档形状）。"""
    if tier == 2:
        return ModelCapabilityProfile(
            model_id=model_id,
            tier=2,
            context_length=65536,
            max_output=8192,
            structured_output=True,
            reasoning_class="standard",
        )
    if tier == 3:
        return ModelCapabilityProfile(
            model_id=model_id,
            tier=3,
            context_length=131072,
            max_output=16384,
            structured_output=True,
            reasoning_class="advanced",
        )
    raise AssertionError(f"test 只覆盖 tier 2/3：{tier}")


def _entry(model: str) -> DeploymentEntry:
    """最小部署条目（端点空串合法——调用期拦截面，非 resolve 期）。"""
    return DeploymentEntry(provider="test-provider", model=model)


def _deployment(
    models: dict[str, ModelCapabilityProfile],
    profiles: dict[str, DeploymentEntry],
) -> DeploymentProfile:
    return DeploymentProfile(models=models, inference_profiles=profiles)


def _npc_policy_profile(
    *, profile_id: str = "cap_npc_policy", min_tier: int = 2, ideal_tier: int = 2
) -> InferenceCapabilityProfile:
    return InferenceCapabilityProfile(
        id=profile_id,
        capability="npc_policy",
        min_tier=min_tier,
        ideal_tier=ideal_tier,
    )


def _ir(
    *,
    characters: tuple[CharacterSpec, ...],
    capabilities: tuple[InferenceCapabilityProfile, ...] = (
        _npc_policy_profile(),
    ),
) -> ProjectIR:
    """最小 ProjectIR（必填节 manifest/scenario/player 直构，build_ir 绕行）。"""
    return ProjectIR(
        manifest=ProjectManifest(
            schema_version="2", project_id="t5_binding", name="T5 Binding Project"
        ),
        scenario=ScenarioSpec(
            id="scenario_main",
            max_ticks=10,
            ticks_per_game_minute=1.0,
            game_time=ScenarioTime(hour=12, minute=0),
        ),
        player=PlayerSpec(player_id="player_1", name="Player"),
        characters=characters,
        capabilities=capabilities,
    )


class _MemSink:
    """内存 TraceSink（三方法封闭；conftest _MemSink 同构先例）。"""

    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []
        self.artifacts: dict[str, Any] = {}
        self.diagnostics: list[Any] = []

    def record(self, kind: str, payload: dict[str, object]) -> None:
        self.records.append((kind, payload))

    def store_artifact(self, ref: str, artifact: object) -> None:
        self.artifacts[ref] = artifact

    def record_diagnostic(self, diag: Any) -> None:
        self.diagnostics.append(diag)


def _context(
    *, actor_id: str, base: Revision, candidate_actions: tuple[str, ...]
) -> ActorDecisionContext:
    """最小 ActorDecisionContext（13 字段直构，JSON 原生替代值，conftest
    ``_make_context`` 先例移植；candidate_actions 由测试面按 Gate 注入）。"""
    return ActorDecisionContext(
        actor_id=EntityId(actor_id),
        tick=7,
        base_world_revision=base,
        wake_reason="t5_bind",
        self_view={
            "entity_id": actor_id,
            "entity_class": "character",
            "tags": (),
            "revision": int(base),
            "components": {},
        },
        visible_entities=(actor_id,),
        local_entity_views={},
        global_entity_views=None,
        observations=(),
        knowledge=None,
        memory=(),
        candidate_actions=tuple(ActionTypeId(a) for a in candidate_actions),
        granted_capabilities=("knowledge.read",),
    )


_BASE = Revision(3)
_TALK_SCRIPT = (
    '{"action_id": "talk", "arguments": {"target": "player"}, '
    '"intent": "greet", "confidence": 0.9}'
)


# —— Gate 1：Deployment A vs B → resolved_models 不同（X / Y）——


def test_gate1_deployment_switch_resolves_different_models() -> None:
    characters = (
        CharacterSpec(id="npc_a", name="NPC A"),
        CharacterSpec(id="npc_b", name="NPC B"),
    )
    ir = _ir(characters=characters)
    deployment_a = _deployment({"model_x": _model("model_x", tier=2)}, {"npc_policy": _entry("model_x")})
    deployment_b = _deployment({"model_y": _model("model_y", tier=2)}, {"npc_policy": _entry("model_y")})
    backend = FakeInferenceBackend()
    sink = _MemSink()

    result_a = bind_llm_policies(
        Path("/nonexistent-root"), ir, deployment=deployment_a, backend=backend, sink=sink
    )
    result_b = bind_llm_policies(
        Path("/nonexistent-root"), ir, deployment=deployment_b, backend=backend, sink=sink
    )

    # 两 actor 分别 = X / Y（同 IR 两 deployment 面）
    assert result_a.resolved_models == {"npc_a": "model_x", "npc_b": "model_x"}
    assert result_b.resolved_models == {"npc_a": "model_y", "npc_b": "model_y"}
    assert result_a.resolved_models != result_b.resolved_models
    # policies 键 = 全部 character id（player 不绑）；构造成功零诊断
    for result in (result_a, result_b):
        assert tuple(result.policies) == ("npc_a", "npc_b")
        assert "player_1" not in result.policies
        assert all(isinstance(p, LLMPolicy) for p in result.policies.values())
        assert result.diagnostics == ()
    # 透传面：capability / ttl / critic flag 冻结口径
    for result in (result_a, result_b):
        for policy in result.policies.values():
            assert policy.capability == "npc_policy"
            assert policy.ttl_ticks is None
            assert policy.enable_critic is False


def test_gate1_ttl_ticks_passthrough() -> None:
    ir = _ir(characters=(CharacterSpec(id="npc_a", name="NPC A"),))
    deployment = _deployment(
        {"model_x": _model("model_x", tier=2)}, {"npc_policy": _entry("model_x")}
    )
    result = bind_llm_policies(
        Path("/nonexistent-root"),
        ir,
        deployment=deployment,
        backend=FakeInferenceBackend(),
        sink=_MemSink(),
        ttl_ticks=5,
    )
    assert result.policies["npc_a"].ttl_ticks == 5


# —— Gate 2：FakeInferenceBackend 脚本 → decide 产 talk 提案 ——


def test_gate2_scripted_backend_decide_produces_talk_proposal() -> None:
    ir = _ir(characters=(CharacterSpec(id="npc_1", name="NPC 1"),))
    deployment = _deployment(
        {"model_x": _model("model_x", tier=2)}, {"npc_policy": _entry("model_x")}
    )
    backend = FakeInferenceBackend(
        script={("npc_policy", _BASE, 1): _TALK_SCRIPT},
    )
    sink = _MemSink()
    result = bind_llm_policies(
        Path("/nonexistent-root"), ir, deployment=deployment, backend=backend, sink=sink
    )
    assert result.diagnostics == ()
    assert result.resolved_models == {"npc_1": "model_x"}
    policy = result.policies["npc_1"]
    assert isinstance(policy, LLMPolicy)
    # BehaviorPolicy 非 runtime_checkable（设计口径）：结构面 = 同步单参 decide
    assert not inspect.iscoroutinefunction(policy.decide)
    assert len(inspect.signature(policy.decide).parameters) == 1

    context = _context(actor_id="npc_1", base=_BASE, candidate_actions=("talk",))
    proposal = policy.decide(context)

    assert isinstance(proposal, ActionProposal)
    assert proposal is not None
    assert proposal.action_id == "talk"
    assert proposal.actor_id == EntityId("npc_1")
    assert proposal.arguments == {"target": "player"}
    assert proposal.intent == "greet"
    assert proposal.confidence == 0.9
    # 脚本寻址面：logical_role = capability 串 "npc_policy"，一次调用命中
    assert len(backend.calls) == 1
    call = backend.calls[0]
    assert call.logical_role == "npc_policy"
    assert call.profile == "npc_policy"
    assert call.model == "model_x"
    # trace 面：llm_call 9 键 payload + prompt artifact 落句柄
    llm_calls = [payload for kind, payload in sink.records if kind == "llm_call"]
    assert len(llm_calls) == 1
    assert llm_calls[0]["logical_role"] == "npc_policy"
    assert llm_calls[0]["resolved_model"] == "model_x"
    assert "prompt://npc_1:7:3" in sink.artifacts


# —— Gate 3：deployment 缺 npc_policy 条目 → 诊断非空 + 无 policy + 不抛 ——


def test_gate3_deployment_missing_npc_policy_entry_no_policy_no_raise() -> None:
    characters = (
        CharacterSpec(id="npc_a", name="NPC A"),
        CharacterSpec(id="npc_b", name="NPC B"),
    )
    ir = _ir(characters=characters)
    # models 有声明但 inference_profiles 无 "npc_policy" 键（router 步骤 2 面）
    deployment = _deployment({"model_x": _model("model_x", tier=2)}, {})
    result = bind_llm_policies(
        Path("/nonexistent-root"),
        ir,
        deployment=deployment,
        backend=FakeInferenceBackend(),
        sink=_MemSink(),
    )

    assert result.policies == {}
    assert result.resolved_models == {}
    assert len(result.diagnostics) == len(characters)  # 逐 character 一条
    assert [d.path for d in result.diagnostics] == ["npc_a", "npc_b"]
    for diag in result.diagnostics:
        assert diag.severity is DiagnosticSeverity.ERROR
        assert "LLMSIM_RESOLVER_NO_DEPLOYMENT" in diag.message  # P6 信息转写携带
        assert "npc_policy" in diag.refs


def test_gate3_tier_mismatch_also_no_policy_no_raise() -> None:
    """router 步骤 4 面（tier 不满足）= 同为 BuildResult.policy None 路径。"""
    ir = _ir(
        characters=(CharacterSpec(id="npc_a", name="NPC A"),),
        capabilities=(
            InferenceCapabilityProfile(
                id="cap_high", capability="npc_policy", min_tier=3, ideal_tier=3
            ),
        ),
    )
    deployment = _deployment(
        {"model_low": _model("model_low", tier=2)}, {"npc_policy": _entry("model_low")}
    )
    result = bind_llm_policies(
        Path("/nonexistent-root"),
        ir,
        deployment=deployment,
        backend=FakeInferenceBackend(),
        sink=_MemSink(),
    )
    assert result.policies == {}
    assert result.resolved_models == {}
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].severity is DiagnosticSeverity.ERROR
    assert result.diagnostics[0].path == "npc_a"
    assert "LLMSIM_RESOLVER_TIER_MISMATCH" in result.diagnostics[0].message


# —— Gate 4：deployment=None → warning + policies 空（不抛）——


def test_gate4_deployment_none_disabled_warning_empty() -> None:
    ir = _ir(characters=(CharacterSpec(id="npc_a", name="NPC A"),))
    result = bind_llm_policies(
        Path("/nonexistent-root"),
        ir,
        deployment=None,
        backend=FakeInferenceBackend(),
        sink=_MemSink(),
    )
    assert result.policies == {}
    assert result.resolved_models == {}
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.severity is DiagnosticSeverity.WARNING
    assert diag.message == "llm binding disabled: no deployment/backend"
    assert diag.refs == ("deployment",)


def test_gate4_backend_none_disabled_warning_empty() -> None:
    ir = _ir(characters=(CharacterSpec(id="npc_a", name="NPC A"),))
    deployment = _deployment(
        {"model_x": _model("model_x", tier=2)}, {"npc_policy": _entry("model_x")}
    )
    result = bind_llm_policies(
        Path("/nonexistent-root"),
        ir,
        deployment=deployment,
        backend=None,
        sink=_MemSink(),
    )
    assert result.policies == {}
    assert result.resolved_models == {}
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].severity is DiagnosticSeverity.WARNING
    assert result.diagnostics[0].message == "llm binding disabled: no deployment/backend"
    assert result.diagnostics[0].refs == ("backend",)


# —— requirement 选取面（T5 卡语义 1）——


def test_no_capability_profile_single_error_empty() -> None:
    ir = _ir(characters=(CharacterSpec(id="npc_a", name="NPC A"),), capabilities=())
    deployment = _deployment(
        {"model_x": _model("model_x", tier=2)}, {"npc_policy": _entry("model_x")}
    )
    result = bind_llm_policies(
        Path("/nonexistent-root"),
        ir,
        deployment=deployment,
        backend=FakeInferenceBackend(),
        sink=_MemSink(),
    )
    assert result.policies == {}
    assert result.resolved_models == {}
    assert len(result.diagnostics) == 1
    diag = result.diagnostics[0]
    assert diag.severity is DiagnosticSeverity.ERROR
    assert diag.message == "no npc_policy capability profile"


def test_multiple_capability_profiles_first_by_id_casefold_plus_warning() -> None:
    # casefold 序首 = "alpha_cap"（min_tier=2 可胜出）；若误选 "zeta_cap"
    # （min_tier=3）→ tier 2 model 触发 TIER_MISMATCH → policies 空。
    ir = _ir(
        characters=(CharacterSpec(id="npc_a", name="NPC A"),),
        capabilities=(
            InferenceCapabilityProfile(
                id="zeta_cap", capability="npc_policy", min_tier=3, ideal_tier=3
            ),
            InferenceCapabilityProfile(
                id="alpha_cap", capability="npc_policy", min_tier=2, ideal_tier=2
            ),
        ),
    )
    deployment = _deployment(
        {"model_x": _model("model_x", tier=2)}, {"npc_policy": _entry("model_x")}
    )
    result = bind_llm_policies(
        Path("/nonexistent-root"),
        ir,
        deployment=deployment,
        backend=FakeInferenceBackend(),
        sink=_MemSink(),
    )
    # 恰好一条 warning（多条 profile）；alpha_cap 胜出 → 绑定成功
    warnings = [d for d in result.diagnostics if d.severity is DiagnosticSeverity.WARNING]
    errors = [d for d in result.diagnostics if d.severity is DiagnosticSeverity.ERROR]
    assert len(warnings) == 1
    assert warnings[0].refs == ("alpha_cap", "zeta_cap")
    assert errors == []
    assert result.resolved_models == {"npc_a": "model_x"}


# —— 结果形状面（T5 卡冻结 API）——


def test_result_shape_frozen_and_typed() -> None:
    ir = _ir(characters=(CharacterSpec(id="npc_a", name="NPC A"),))
    deployment = _deployment(
        {"model_x": _model("model_x", tier=2)}, {"npc_policy": _entry("model_x")}
    )
    result = bind_llm_policies(
        Path("/nonexistent-root"),
        ir,
        deployment=deployment,
        backend=FakeInferenceBackend(),
        sink=_MemSink(),
    )
    assert isinstance(result, LLMBindingResult)
    assert isinstance(result.policies, dict)
    assert isinstance(result.diagnostics, tuple)
    assert all(isinstance(d, Diagnostic) for d in result.diagnostics)
    assert isinstance(result.resolved_models, dict)
    # frozen dataclass：字段赋值拒绝
    with pytest.raises(FrozenInstanceError):
        result.diagnostics = ()  # type: ignore[misc]
