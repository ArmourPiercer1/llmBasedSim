"""P6-W5 conftest（SOT §6.2 平铺 fixture 面；W5-W6 消费面）。

纪律（SOT §6.2 末段）：W1-W4 测试文件（test_profiles/test_deployment/
test_router/test_adapter/test_structured）自足，**不得依赖**本节 fixture；
上述 fixture 仅 W5-W6 测试文件消费。

fixture 面（§6.2 逐项）：``fake_clock`` / ``mem_sink`` / ``alice_context``
/ ``unauthorized_context`` / ``template_store`` / ``deployment`` /
``deployment_alt`` / ``high_policy`` / ``alt_policy`` / ``scripted_backend``
+ session 级机械审计 ``p6_diagnostic_code_audit``（D-P6-21，惰性执行，
不占 §6.1 平铺计数）。

fixture 文件根 = ``tests/fixtures/``（W6 交付面 #28-35）：
``template_store`` / ``deployment`` / ``deployment_alt`` / ``high_policy`` /
``alt_policy`` 仅在被请求时执行（惰性 = 绿），W5 测试不请求。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
import yaml
from pydantic import ValidationError

from src.engine_v2.content.schemas import (
    DIAGNOSTIC_CODES,
    DiagnosticSeverity,
    InferenceCapabilityProfile,
    PromptPolicy,
)
from src.engine_v2.core.actions import ActionTypeId
from src.engine_v2.core.context_provider import ActorDecisionContext
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.revision import Revision
from src.engine_v2.llm.adapter import FakeInferenceBackend, FixedMonotonicClock
from src.engine_v2.llm.deployment import DeploymentProfile, load_deployment
from src.engine_v2.llm.policy import LLMPolicy, build_llm_policy
from src.engine_v2.prompts.assembler import CharDivisorTokenEstimator
from src.engine_v2.prompts.diagnostic import P6_RUNTIME_DIAGNOSTIC_CODES, RuntimeDiagnostic
from src.engine_v2.prompts.registry import TemplateStore

#: fixture 文件根（W6 交付目录 #28-35；本 conftest 只引用路径不创建）。
_FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures"

#: e2e 脚本覆盖的 base_revision 范围（scenario max_ticks=20，§6.4）。
_E2E_REVISION_RANGE = range(20)


class _MemSink:
    """内存 TraceSink（闭包类内联实现，零 import 面，SOT §6.2）。

    三通道收集：``records`` = (kind, payload) 按记录序；``artifacts`` =
    ref → artifact 本体；``diagnostics`` = RuntimeDiagnostic 按记录序。
    """

    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, object]]] = []
        self.artifacts: dict[str, object] = {}
        self.diagnostics: list[Any] = []

    def record(self, kind: str, payload: dict[str, object]) -> None:
        self.records.append((kind, payload))

    def store_artifact(self, ref: str, artifact: object) -> None:
        self.artifacts[ref] = artifact

    def record_diagnostic(self, diag: Any) -> None:
        self.diagnostics.append(diag)


def _entity_view_mirror(entity_id: str, components: dict[str, Any]) -> dict[str, Any]:
    """EntityView 形状 dict 镜像（JSON 原生字段值，ERR-P6-10(a) 口径）。"""
    return {
        "entity_id": entity_id,
        "entity_class": "character",
        "tags": (),
        "revision": 3,
        "components": components,
    }


def _make_context(*, global_views: dict[str, Any] | None) -> ActorDecisionContext:
    """P4 口径 context（make_p4_world 先例移植，ERR-P6-10；字段值 JSON 原生）。

    alice actor + bob 实体 + candidate_actions 含 "attack" + granted_
    capabilities 面（DEFAULT_NPC_CAPABILITIES 按 value 排序口径）；
    ActorDecisionContext = plain frozen dataclass 无运行时校验，
    substitute 类型（tuple/dict）合法消费（context_provider.py:285-286）。
    """
    return ActorDecisionContext(
        actor_id=EntityId("ent_alice"),
        tick=7,
        base_world_revision=Revision(3),
        wake_reason="wake_test",
        self_view=_entity_view_mirror(
            "ent_alice", {"movement": {"position": {"x": 0, "y": 0}}}
        ),
        visible_entities=("ent_bob",),
        local_entity_views={},
        global_entity_views=global_views,  # type: ignore[arg-type]
        observations=(),
        knowledge=None,
        memory=(),
        candidate_actions=(ActionTypeId("attack"),),
        granted_capabilities=("knowledge.read", "memory.read", "observation.read"),
    )


def _e2e_script() -> dict[tuple[str, Revision, int], str]:
    """S3 e2e 脚本化面（§5）：(major_character, base_revision, 1) →
    attack 提案 fenced JSON（全 20 个 base_revision 预置）。"""
    text = (
        "```json\n"
        '{"action_id":"attack","arguments":{"target_id":"bob"},'
        '"intent":"hit","confidence":0.9}\n'
        "```"
    )
    return {("major_character", Revision(r), 1): text for r in _E2E_REVISION_RANGE}


@pytest.fixture
def fake_clock() -> FixedMonotonicClock:
    """FixedMonotonicClock(start_ms=0, step_ms=1)，每用例新实例（SOT §6.2）。"""
    return FixedMonotonicClock(start_ms=0, step_ms=1)


@pytest.fixture
def mem_sink() -> _MemSink:
    """内存 trace 收集面（record/artifact/diagnostic 三通道，SOT §6.2）。"""
    return _MemSink()


@pytest.fixture
def scripted_backend() -> (
    Callable[[dict[tuple[str, Revision, int], str]], FakeInferenceBackend]
):
    """(logical_role, base_revision, seq) 脚本工厂（平铺函数 make_script，
    SOT §6.2）。"""

    def make_script(script: dict[tuple[str, Revision, int], str]) -> FakeInferenceBackend:
        return FakeInferenceBackend(script=script)

    return make_script


@pytest.fixture
def alice_context() -> ActorDecisionContext:
    """P4 口径 alice 决策上下文（global_entity_views 授权态，ERR-P6-10）。"""
    return _make_context(
        global_views={
            "ent_bob": _entity_view_mirror(
                "ent_bob", {"movement": {"position": {"x": 5, "y": 0}}}
            ),
        }
    )


@pytest.fixture
def unauthorized_context() -> ActorDecisionContext:
    """同 alice_context 但 global_entity_views=None（未授权态，SOT §6.2）。"""
    return _make_context(global_views=None)


@pytest.fixture
def template_store() -> TemplateStore:
    """v2_project_llm 装载（TemplateStore 正常态，SOT §6.2/§6.4）。

    通用装载：读 ``tests/fixtures/v2_project_llm/prompts/*.yaml``，逐文件
    顶层 ``prompts`` 列表解析为 PromptPolicy（字段 id/scope/template_ref/
    variables）；template_ref 与 validate_template_ref 路径纪律（§3.9，
    要求 ref 解析落于 project_root/prompts/ 之下）的前缀对齐 = W6 消费
    面裁定事项（§6.4 表 face 记录在案）。
    """
    root = _FIXTURE_ROOT / "v2_project_llm"
    policies: list[PromptPolicy] = []
    for path in sorted((root / "prompts").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for entry in data["prompts"]:
            policies.append(PromptPolicy(**entry))
    policies.sort(key=lambda p: p.id)
    return TemplateStore(project_root=root, policies=tuple(policies))


@pytest.fixture
def deployment() -> DeploymentProfile:
    """tests/fixtures/v2_deployment/deployment.yaml 装载结果（SOT §6.2）。

    钉死形状（§6.4）：models model_high(tier 3)/model_alt(tier 2)；
    inference_profiles.major_character → model_high（resolved_via=primary）。
    """
    result = load_deployment(_FIXTURE_ROOT / "v2_deployment" / "deployment.yaml")
    assert result.profile is not None, f"deployment 装载失败：{result.diagnostics}"
    return result.profile


@pytest.fixture
def deployment_alt() -> DeploymentProfile:
    """tests/fixtures/v2_deployment/deployment_alt.yaml 装载结果（SOT §6.2）。

    钉死形状（§6.4）：models model_alt(tier 2)；
    inference_profiles.major_character → model_alt（alt tier 2 ≥ min 2，
    S5 换模型 e2e 仍可跑）。
    """
    result = load_deployment(_FIXTURE_ROOT / "v2_deployment" / "deployment_alt.yaml")
    assert result.profile is not None, (
        f"deployment_alt 装载失败：{result.diagnostics}"
    )
    return result.profile


def _build_policy(deployment_profile: DeploymentProfile, store: TemplateStore) -> LLMPolicy:
    """high/alt policy 公共构造面（build_llm_policy 产物，§6.2）。"""
    requirement = InferenceCapabilityProfile(
        id="cap_major_character",
        capability="major_character",
        min_tier=2,
        ideal_tier=3,
    )
    result = build_llm_policy(
        capability="major_character",
        requirement=requirement,
        deployment=deployment_profile,
        backend=FakeInferenceBackend(script=_e2e_script()),
        store=store,
        estimator=CharDivisorTokenEstimator(),
        sink=_MemSink(),
    )
    assert result.policy is not None, (
        f"policy 构造失败（router 显式失败面）：{result.diagnostics}"
    )
    return result.policy


@pytest.fixture
def high_policy(deployment: DeploymentProfile, template_store: TemplateStore) -> LLMPolicy:
    """高档位 policy：major_character → model_high（SOT §6.2/§6.4）。"""
    return _build_policy(deployment, template_store)


@pytest.fixture
def alt_policy(
    deployment_alt: DeploymentProfile, template_store: TemplateStore
) -> LLMPolicy:
    """换模型 policy：major_character → model_alt（S5 e2e 面，SOT §6.2/§6.4）。"""
    return _build_policy(deployment_alt, template_store)


@pytest.fixture(scope="session")
def p6_diagnostic_code_audit() -> None:
    """session 级机械审计（D-P6-21；惰性 = 仅被请求时执行，SOT §6.2）。

    ① 构造期拒绝：code ∉ P6 21 码闭集 → pydantic ValidationError（闭集
    面构造期强制，不静默）；
    ② P6 21 码 ∩ P5 18 码（content.schemas DIAGNOSTIC_CODES）= ∅
    （两闭集零交集，P5 冻结面不混入 P6 运行时码）。
    """
    with pytest.raises(ValidationError):
        RuntimeDiagnostic(
            code="LLMSIM_UNKNOWN_CODE",
            severity=DiagnosticSeverity.ERROR,
            path="p6",
            message="audit",
        )
    assert P6_RUNTIME_DIAGNOSTIC_CODES & DIAGNOSTIC_CODES == frozenset()
