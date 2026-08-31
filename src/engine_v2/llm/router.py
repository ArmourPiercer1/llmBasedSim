"""P6-W2 T03 后半（SOT §3.3）：capability → deployment 匹配 + fallback 梯度 + 诊断。

G6-2 实现面：改实际模型 = 改用户部署文件（Spec §31.2「Deployment Resolver
映射 capability profile → actual model」，Spec:1647-1656）。纯函数，零 I/O、
零非确定根源、同步面。五步次序钉死（步骤间严格次序，全步不抛异常，
SOT §3.3 L237-242）；语义钉死（D-P6-07）：fallback = 同 capability 池内按
声明序降级（primary → fallbacks）；候选间无跨档偏好（首个满足 min_tier 者
胜，不择优、不跳档）；min_tier 是唯一硬门槛。诊断序 = 按 (code, path, refs)
排序（P5 D-P5-12 口径移植，同 W1 deployment.py）。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.engine_v2.content.schemas import DiagnosticSeverity, InferenceCapabilityProfile
from src.engine_v2.llm.deployment import DeploymentEntry, DeploymentProfile
from src.engine_v2.llm.profiles import CAPABILITY_RE, ModelCapabilityProfile
from src.engine_v2.prompts.diagnostic import RuntimeDiagnostic

__all__ = [
    "ResolvedModel",
    "RouterResult",
    "resolve_capability",
    "candidates_for",
    "meets_tier",
    "resolved_via",
]

_NO_DEPLOYMENT = "LLMSIM_RESOLVER_NO_DEPLOYMENT"
_MODEL_UNDECLARED = "LLMSIM_RESOLVER_MODEL_UNDECLARED"
_TIER_MISMATCH = "LLMSIM_RESOLVER_TIER_MISMATCH"
_BELOW_IDEAL = "LLMSIM_RESOLVER_BELOW_IDEAL"


class ResolvedModel(BaseModel):
    """router 产物（adapter 消费，13 字段，SOT §3.3 L219-229）。

    - capability = requirement.capability（logical role id，同一字符串域）；
    - model_id / tier / context_length / max_output / structured_output /
      reasoning_class 取自 models 目录胜出项（回显，trace/审计面）；
    - entry 侧字段（供应商侧 / 端点 / temperature / timeout_seconds）
      取自 entry（端点可为 ``""``——调用期拦截，非 resolve 期）；
    - api_key_env 只名不值（Leader-A5，内省断言无值字段）；
    - resolved_via = ``"primary"`` 或 ``"fallback:<n>"``（n ≥ 1 = fallbacks
      第 n 项，1-based；provenance 面）。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    capability: str
    model_id: str
    provider: str
    base_url: str
    api_key_env: str | None
    tier: int
    context_length: int
    max_output: int
    structured_output: bool
    reasoning_class: str
    temperature: float
    timeout_seconds: float
    resolved_via: str


class RouterResult(BaseModel):
    """路由结果：判定 = 数据，失败不抛（P5/P3 先例；载体 §3.11）。

    SOT L231 逐字：frozen pydantic（不加 ``extra="forbid"``）。
    """

    model_config = ConfigDict(frozen=True)

    resolved: ResolvedModel | None
    diagnostics: tuple[RuntimeDiagnostic, ...]


def _sorted_diagnostics(diagnostics: list[RuntimeDiagnostic]) -> tuple[RuntimeDiagnostic, ...]:
    """诊断集按 (code, path, refs) 排序（P5 D-P5-12 口径移植，SOT §3.3 L246）。"""
    return tuple(sorted(diagnostics, key=lambda d: (d.code, d.path, d.refs)))


def candidates_for(deployment: DeploymentProfile, capability: str) -> tuple[DeploymentEntry, ...]:
    """候选梯度：capability ∉ inference_profiles → ``()``；否则 = ``(entry,)``
    + fallbacks 各项展开为同 entry 的 model 替换视图（序 = primary 先、
    fallbacks 声明序；确定性，无排序无随机）。"""
    entry = deployment.inference_profiles.get(capability)
    if entry is None:
        return ()
    views = tuple(entry.model_copy(update={"model": name}) for name in entry.fallbacks)
    return (entry,) + views


def meets_tier(model: ModelCapabilityProfile, min_tier: int) -> bool:
    """tier 门槛：``model.tier >= min_tier``（纯比较；tier 档下限校验已在
    构造期完成，此处只比档位）。"""
    return model.tier >= min_tier


def resolved_via(index: int) -> str:
    """0-based candidate 索引 → provenance 编码：0 → ``"primary"``；
    n > 0 → ``"fallback:<n>"``（n = fallbacks 第 n 项，1-based）。"""
    if index == 0:
        return "primary"
    return f"fallback:{index}"


def resolve_capability(
    deployment: DeploymentProfile,
    requirement: InferenceCapabilityProfile,
) -> RouterResult:
    """capability 需求 → 实际模型（五步次序钉死，全步不抛异常，SOT §3.3）。

    1. capability pattern 违例 → NO_DEPLOYMENT（refs=["capability-malformed"]，
       防御性；P5 侧已保证）；
    2. capability ∉ inference_profiles → NO_DEPLOYMENT（绝不跨 capability
       借用，静默换模型禁令，G6-2 机械面）；
    3. 逐 candidate 求 models[candidate.model]（缺失 → MODEL_UNDECLARED，
       跳过该 candidate）；首个 meets_tier 者胜（不择优、不跳档）；
    4. 无胜出 → TIER_MISMATCH（refs = tried model_id 列表按尝试序——显式
       失败，绝不静默换模型，D-P6-07）；
    5. 胜出但 tier < ideal_tier → 附加 BELOW_IDEAL warning（建议级，
       不阻断）。
    """
    capability = requirement.capability

    # 步骤 1：capability pattern 违例（防御性）。
    if CAPABILITY_RE.fullmatch(capability) is None:
        return RouterResult(
            resolved=None,
            diagnostics=_sorted_diagnostics(
                [
                    RuntimeDiagnostic(
                        code=_NO_DEPLOYMENT,
                        severity=DiagnosticSeverity.ERROR,
                        path=capability,
                        message=f"capability {capability!r} 违例 capability 字符串约定",
                        refs=("capability-malformed",),
                    ),
                ]
            ),
        )

    # 步骤 2：capability 无部署条目（绝不跨 capability 借用）。
    entry = deployment.inference_profiles.get(capability)
    if entry is None:
        return RouterResult(
            resolved=None,
            diagnostics=_sorted_diagnostics(
                [
                    RuntimeDiagnostic(
                        code=_NO_DEPLOYMENT,
                        severity=DiagnosticSeverity.ERROR,
                        path=capability,
                        message=f"capability {capability!r} 无部署条目",
                        refs=("inference_profiles 无此键",),
                    ),
                ]
            ),
        )

    # 步骤 3：逐 candidate 查 models 目录，首个 meets_tier 者胜。
    diagnostics: list[RuntimeDiagnostic] = []
    tried: list[str] = []
    winner_index: int | None = None
    winner_model: ModelCapabilityProfile | None = None
    for index, candidate in enumerate(candidates_for(deployment, capability)):
        name = candidate.model
        model = deployment.models.get(name)
        if model is None:
            diagnostics.append(
                RuntimeDiagnostic(
                    code=_MODEL_UNDECLARED,
                    severity=DiagnosticSeverity.ERROR,
                    path=capability,
                    message=f"capability {capability!r} 引用未声明 model {name!r}",
                    refs=(name,),
                )
            )
            continue
        tried.append(name)
        if meets_tier(model, requirement.min_tier):
            winner_index = index
            winner_model = model
            break

    # 步骤 4：无胜出 → TIER_MISMATCH（显式失败，绝不静默换模型）。
    if winner_index is None or winner_model is None:
        diagnostics.append(
            RuntimeDiagnostic(
                code=_TIER_MISMATCH,
                severity=DiagnosticSeverity.ERROR,
                path=capability,
                message=f"capability {capability!r} 无 candidate 满足 min_tier",
                refs=tuple(tried),
            )
        )
        return RouterResult(resolved=None, diagnostics=_sorted_diagnostics(diagnostics))

    # 步骤 5：胜出 tier < ideal_tier → BELOW_IDEAL warning（不阻断）。
    if winner_model.tier < requirement.ideal_tier:
        diagnostics.append(
            RuntimeDiagnostic(
                code=_BELOW_IDEAL,
                severity=DiagnosticSeverity.WARNING,
                path=capability,
                message=(
                    f"capability {capability!r} 胜出 tier {winner_model.tier} 低于 "
                    f"ideal_tier {requirement.ideal_tier}（建议级，不阻断）"
                ),
                refs=(winner_model.model_id, str(requirement.ideal_tier)),
            )
        )

    return RouterResult(
        resolved=ResolvedModel(
            capability=capability,
            model_id=winner_model.model_id,
            provider=entry.provider,
            base_url=entry.base_url,
            api_key_env=entry.api_key_env,
            tier=winner_model.tier,
            context_length=winner_model.context_length,
            max_output=winner_model.max_output,
            structured_output=winner_model.structured_output,
            reasoning_class=winner_model.reasoning_class,
            temperature=entry.temperature,
            timeout_seconds=entry.timeout_seconds,
            resolved_via=resolved_via(winner_index),
        ),
        diagnostics=_sorted_diagnostics(diagnostics),
    )
