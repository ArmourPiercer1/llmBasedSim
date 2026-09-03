"""T5（runtime closure）：P6 LLMPolicy 绑定面（WorldInstance.policies 的
LLM 供给者，合同 = docs/plans/runtime_closure_contract.md §4 T5 卡）。

职责：把 Game Project 的 ``ProjectIR`` 中每个 NPC（``CharacterSpec``）绑定
为一个 P6 :class:`~src.engine_v2.llm.policy.LLMPolicy`（BehaviorPolicy 实例），
供 T9 assembly 注入 ``WorldInstance.policies``。**player 不绑**（玩家 =
人类输入面，Spec:833 PlayerPolicy 属呈现层，不经 LLM 绑定）。

强制复用 P6 工厂（本模块零自写 router / 零自写组装）：

- :func:`~src.engine_v2.llm.policy.build_llm_policy`（llm/policy.py L383，
  构造工厂唯一入口——router 失败 = 显式 ``BuildResult(policy=None,
  diagnostics)``，绝不静默回落任意模型，D-P6-07）；
- :class:`~src.engine_v2.prompts.registry.TemplateStore`（``project_root`` +
  ``ir.prompts``，加载即校验）；
- :class:`~src.engine_v2.prompts.assembler.CharDivisorTokenEstimator`
  （``divisor=4.0``，§3.10 缺省面）。

语义（T5 卡冻结）：

1. requirement = ``ir.capabilities`` 中 ``capability == <capability>``（默认
   ``npc_policy``，计划 §2.4 默认约定）的 :class:`InferenceCapabilityProfile`；
   零条 → 单条 error 诊断（"no <capability> capability profile"）+ policies 空；
   多条 → 取 id casefold 排序首条 + warning 诊断（确定性，不静默）；
2. 每个 ``ir.characters`` 绑一个 policy（key = ``character.id``）；
3. ``deployment`` 或 ``backend`` 为 None → 单条 warning 诊断
   （"llm binding disabled: no deployment/backend"）+ policies 空 +
   **不抛异常**（headless assembly 合法路径；短路于 store 构造之前，
   零文件 I/O）；
4. ``BuildResult.policy is None``（router 失败）→ 该 character 一条 error
   诊断（归因 path = character.id，refs/message 携带 BuildResult.diagnostics
   信息）+ 不放入 policies；``resolved_models`` 仅收录成功者（审计面）。

诊断面：``LLMBindingResult.diagnostics`` 为 P5 :class:`Diagnostic`（18 码
闭集，content/schemas.py）——P6 运行时码（21 闭集）不可直接混入（构造期
闭集校验拒绝），故本模块把 P6 失败信息**转写**进 P5 码
（``LLMSIM_UNRESOLVED_REF`` / ``LLMSIM_DUPLICATE_ID``，refs 携带原 P6
code 作证据引用）。排序 = 按 (code, path, refs)（P5 D-P5-12 口径）。
``TemplateStore.diagnostics`` 不经本结果面转写——模板层诊断在 decide 期
经 ``sink.record_diagnostic`` 通道独立浮现（P6 §3.10 组装期透传，本模块
不重复记账）。

模块纪律：同步面；零网络；零非确定根源（确定性 = 同输入同诊断序）；
import 边界 = content/core/llm/prompts 冻结面（DAG 向下，llm 包不 import
runtime，无环）；src 零 ``import tests``。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from src.engine_v2.content.schemas import (
    Diagnostic,
    DiagnosticSeverity,
    InferenceCapabilityProfile,
    ProjectIR,
)
from src.engine_v2.core.behavior_policy import BehaviorPolicy
from src.engine_v2.llm.adapter import InferenceBackend
from src.engine_v2.llm.deployment import DeploymentProfile
from src.engine_v2.llm.policy import TraceSink, build_llm_policy
from src.engine_v2.prompts.assembler import CharDivisorTokenEstimator
from src.engine_v2.prompts.registry import TemplateStore

__all__ = ["LLMBindingResult", "bind_llm_policies"]

#: P5 18 码闭集内本模块消费的诊断码（content/schemas.py DIAGNOSTIC_CODES）。
_DIAG_UNRESOLVED_REF: Final[str] = "LLMSIM_UNRESOLVED_REF"
_DIAG_DUPLICATE_ID: Final[str] = "LLMSIM_DUPLICATE_ID"

#: token 估计除数（§3.10 缺省面 = CharDivisorTokenEstimator 默认值）。
_TOKEN_DIVISOR: Final[float] = 4.0


@dataclass(frozen=True)
class LLMBindingResult:
    """LLM 绑定结果（frozen；T5 卡冻结 API）。

    - ``policies``：actor_id（= character id）→ :class:`LLMPolicy`
      （BehaviorPolicy 实例）；player 不入；router 失败者不入；
    - ``diagnostics``：P5 :class:`Diagnostic` 元组，按 (code, path, refs)
      排序（确定性）；
    - ``resolved_models``：actor_id → resolved model_id（审计面；仅成功者）。
    """

    policies: dict[str, BehaviorPolicy]
    diagnostics: tuple[Diagnostic, ...]
    resolved_models: dict[str, str]


def _disabled_diagnostic(
    deployment: DeploymentProfile | None, backend: InferenceBackend | None
) -> Diagnostic:
    """disabled 短路诊断（单条 warning；refs = 缺失参数名，参数序）。"""
    missing = tuple(
        name
        for name, value in (("deployment", deployment), ("backend", backend))
        if value is None
    )
    return Diagnostic(
        code=_DIAG_UNRESOLVED_REF,
        severity=DiagnosticSeverity.WARNING,
        path="deployment",
        message="llm binding disabled: no deployment/backend",
        refs=missing,
    )


def _no_requirement_diagnostic(capability: str) -> Diagnostic:
    """零 capability profile 诊断（单条 error）。"""
    return Diagnostic(
        code=_DIAG_UNRESOLVED_REF,
        severity=DiagnosticSeverity.ERROR,
        path="capabilities",
        message=f"no {capability} capability profile",
        refs=("capability_profile", capability),
    )


def _multiple_requirement_diagnostic(
    capability: str, matches: tuple[InferenceCapabilityProfile, ...]
) -> Diagnostic:
    """多条 capability profile 诊断（warning；refs = 入选序全部 id）。"""
    return Diagnostic(
        code=_DIAG_DUPLICATE_ID,
        severity=DiagnosticSeverity.WARNING,
        path="capabilities",
        message=(
            f"multiple {capability} capability profiles; "
            "binding uses first by id casefold order"
        ),
        refs=tuple(profile.id for profile in matches),
    )


def _build_failed_diagnostic(
    character_id: str, capability: str, build_diagnostics: tuple
) -> Diagnostic:
    """单 character 绑定失败诊断（error；携带 BuildResult.diagnostics 信息）。

    path = character.id（逐 character 归因，同因失败亦不重码）；message =
    逐条 P6 code + message 拼接；refs = capability + 逐条 P6 code（证据引用，
    原 P6 21 码闭集字符串原样携带，机器可溯源）。
    """
    return Diagnostic(
        code=_DIAG_UNRESOLVED_REF,
        severity=DiagnosticSeverity.ERROR,
        path=character_id,
        message=(
            f"llm binding failed for character {character_id!r} "
            f"(capability {capability!r}): "
            + "; ".join(f"{d.code}: {d.message}" for d in build_diagnostics)
        ),
        refs=(capability, *(d.code for d in build_diagnostics)),
    )


def bind_llm_policies(
    project_root: Path,
    ir: ProjectIR,
    *,
    deployment: DeploymentProfile | None = None,
    backend: InferenceBackend | None = None,
    sink: "TraceSink",
    capability: str = "npc_policy",
    ttl_ticks: int | None = None,
) -> LLMBindingResult:
    """LLM 策略绑定（T5 卡冻结 API；纯组装，decide 期才触 backend/sink）。

    次序钉死：

    1. ``deployment is None or backend is None`` → 单条 warning + 空 policies
       + 空 resolved_models（headless assembly 合法路径，不抛异常；短路于
       TemplateStore 构造之前——disabled 态零文件 I/O）；
    2. requirement 选取：零条 → 单条 error + 空结果；多条 → id casefold
       排序首条 + warning（确定性兜底）；
    3. 强制复用面构造：``TemplateStore(project_root=..., policies=
       ir.prompts)`` + ``CharDivisorTokenEstimator(divisor=4.0)``；
    4. 逐 ``ir.characters``（IR 序）经 ``build_llm_policy`` 绑定
       （``enable_critic=False``，critic flag 属 decide 期宿主面，绑定面
       不开放）：``BuildResult.policy is None`` → 该 character 一条 error
       诊断 + 跳过；成功 → policies / resolved_models 收录。

    返回 :class:`LLMBindingResult`（诊断按 (code, path, refs) 排序）。
    """
    # ---- 1. disabled 短路（headless assembly 合法路径，不抛异常） ----------
    if deployment is None or backend is None:
        return LLMBindingResult(
            policies={},
            diagnostics=(_disabled_diagnostic(deployment, backend),),
            resolved_models={},
        )

    # ---- 2. requirement 选取（计划 §2.4 默认约定：capability 串匹配） ------
    matches = tuple(p for p in ir.capabilities if p.capability == capability)
    if not matches:
        return LLMBindingResult(
            policies={},
            diagnostics=(_no_requirement_diagnostic(capability),),
            resolved_models={},
        )
    matches = tuple(sorted(matches, key=lambda p: p.id.casefold()))
    diagnostics: list[Diagnostic] = []
    if len(matches) > 1:
        diagnostics.append(_multiple_requirement_diagnostic(capability, matches))
    requirement = matches[0]

    # ---- 3. 强制复用面（P6 工厂输入构造） ----------------------------------
    store = TemplateStore(project_root=project_root, policies=ir.prompts)
    estimator = CharDivisorTokenEstimator(divisor=_TOKEN_DIVISOR)

    # ---- 4. 逐 character 绑定（player 不绑 = 人类输入面） ------------------
    policies: dict[str, BehaviorPolicy] = {}
    resolved_models: dict[str, str] = {}
    for character in ir.characters:
        build = build_llm_policy(
            capability=capability,
            requirement=requirement,
            deployment=deployment,
            backend=backend,
            store=store,
            estimator=estimator,
            sink=sink,
            ttl_ticks=ttl_ticks,
            enable_critic=False,
        )
        if build.policy is None:
            # router 显式失败（D-P6-07）：逐 character 一条 error，不静默。
            diagnostics.append(
                _build_failed_diagnostic(character.id, capability, build.diagnostics)
            )
            continue
        policies[character.id] = build.policy
        resolved_models[character.id] = build.policy.resolved.model_id

    return LLMBindingResult(
        policies=policies,
        diagnostics=tuple(sorted(diagnostics, key=lambda d: (d.code, d.path, d.refs))),
        resolved_models=resolved_models,
    )
