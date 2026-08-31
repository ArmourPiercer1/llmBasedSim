"""P6-W5 T06（SOT §3.6）：LLMPolicy = P6 门面（BehaviorPolicy 实例）。

定位：组装 + 调用 + 解析 + staleness 接线 + trace 记录全在本门面收口——
`build_llm_policy` = 构造工厂（router 失败 = 显式失败，绝不静默回落任意
模型，D-P6-07）；`decide` 九步流程钉死（组装 → 请求构造 → 首次调用 →
解析 → repair 重试 → 解析终败 → critic（可选）→ no-op → 提案）。
B-CON-1..5 全量落地（#20 机械面）：decide 同步、单参、返回
ActionProposal | None（None 合法）、实例不持 random/clock/网络。

trace 面（K6 接线，宿主注入 `TraceSink`，三方法封闭）：`record` 承载
`llm_call`（9 键 = core.trace.LLM_CALL_PAYLOAD_KEYS）与
`prompt_assembly`（5 键封闭集）两类结构化事件；`store_artifact` 以
确定性句柄（prompt:// / output://）存 artifact 本体；`record_diagnostic`
= 独立诊断通道（Leader 裁定 F-02 / D-P6-22：诊断与记录分离）。

staleness 接线（§3.7 委托面）：提案分支经 `effective_valid_until` 计算
valid_until 上界后交 `make_action_proposal`；stale 判定权唯一归
revalidation 管线，本门面零独立拦截器（G6-4 前提）。

critic 接线（§3.8，flag 默认关）：`enable_critic=True` 时才函数级惰性
import critic 模块（W6 交付面，本模块模块级零引用；ERR-P6-10(b) DAG）；
one-shot repair，单次 decide 总调用上限 = 3（1 + parse-retry 1 +
critic-repair 1，PARSE_RETRY_MAX=1，Leader-A6）。

模块纪律（SOT §3.6）：import 边界 = §3 白名单（stdlib typing/dataclasses +
pydantic + core/content/prompts 冻结面 + 本包冻结面），零网络、零时钟、
零随机源、零协程（机械断言）；同步面；零非确定根源（clock 经 backend
注入，本模块不持 clock）；诊断经 sink 通道，不落盘。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, Final, Protocol

from pydantic import AfterValidator, BaseModel, ConfigDict

from src.engine_v2.content.schemas import DiagnosticSeverity, InferenceCapabilityProfile
from src.engine_v2.core.trace import LLM_CALL_PAYLOAD_KEYS
from src.engine_v2.llm.adapter import InferenceBackend, InferenceRequest, WireMessage
from src.engine_v2.llm.deployment import DeploymentProfile
from src.engine_v2.llm.router import ResolvedModel, resolve_capability
from src.engine_v2.llm.staleness import effective_valid_until
from src.engine_v2.llm.structured import (
    make_action_proposal,
    parse_llm_response,
    repair_instruction,
)
from src.engine_v2.prompts.assembler import (
    PromptPackage,
    TokenEstimator,
    assemble_prompt,
)
from src.engine_v2.prompts.diagnostic import RuntimeDiagnostic
from src.engine_v2.prompts.registry import TemplateStore

if TYPE_CHECKING:
    from src.engine_v2.core.actions import ActionProposal
    from src.engine_v2.core.context_provider import ActorDecisionContext

__all__ = ["LLMPolicy", "BuildResult", "build_llm_policy", "TraceSink"]

#: 本模块消费的 INFERENCE 族诊断码（P6 21 码闭集，§8.1；W5 消费 2 码）。
_PARSE_FAILED = "LLMSIM_INFERENCE_PARSE_FAILED"
_PARSE_RECOVERED = "LLMSIM_INFERENCE_PARSE_RECOVERED"

#: prompt_assembly payload 5 键封闭集（SOT §3.6：组装成功/失败两态键集
#: 不变，仅值面变化——失败态 prompt_metadata_ref 定值 + token_estimate 0）。
_PROMPT_ASSEMBLY_KEYS: Final[frozenset[str]] = frozenset(
    {"actor_id", "tick", "base_revision", "prompt_metadata_ref", "token_estimate"}
)


class TraceSink(Protocol):
    """宿主注入 trace 接收面（K6 接线面，三方法封闭，SOT §3.6）。

    结构化使用（无 runtime_checkable，W3 adapter.py InferenceBackend 先例）。
    """

    def record(self, kind: str, payload: dict[str, object]) -> None:
        """记录一条结构化事件。

        kind ∈ {"llm_call", "prompt_assembly"}；payload 键集合 = 对应
        PAYLOAD 键常量精确等值（llm_call 9 键 = core.trace
        LLM_CALL_PAYLOAD_KEYS；prompt_assembly 5 键 = 本模块封闭集）；
        键集与 kind 词表封闭，诊断不进入本方法（D-P6-22）。
        """
        ...

    def store_artifact(self, ref: str, artifact: object) -> None:
        """确定性句柄存 artifact 本体（P6 只给 ref + 内容，不碰文件系统）。

        ref = ``prompt://{actor_id}:{tick}:{base_revision}`` 存 PromptPackage
        摘要 dict；``output://{actor_id}:{tick}:{base_revision}`` 存 wire
        原始文本 dict；artifact 本体落盘方式由宿主决定。
        """
        ...

    def record_diagnostic(self, diag: RuntimeDiagnostic) -> None:
        """独立诊断通道（Leader 裁定 F-02 / D-P6-22：诊断与记录分离）。

        RuntimeDiagnostic（§3.11）经此通道入宿主 sink，不进 `record` 的
        封闭键集；宿主侧如何落 trace/日志 = 宿主实现面。
        """
        ...


@dataclass(frozen=True, slots=True)
class LLMPolicy:
    """P6 门面（BehaviorPolicy 实例；B-CON-1..5 落地面，SOT §3.6）。

    8 字段全注入（构造期钉死，frozen + slots，零可变状态）：

    - ``capability``：能力名（D-P6-03 三同域：logical_role = profile =
      capability 同串）；
    - ``resolved``：router 解析结果（§3.3，构造工厂唯一来源）；
    - ``backend``：wire 可替换接口（生产面 / 测试面注入）；
    - ``store`` / ``estimator``：组装期输入（§3.9 / §3.10）；
    - ``sink``：宿主 trace 接收面；
    - ``ttl_ticks``：valid_until TTL（None = 无显式上界，§3.7）；
    - ``enable_critic``：critic flag（默认关，Leader-A6）。
    """

    capability: str
    resolved: ResolvedModel
    backend: InferenceBackend
    store: TemplateStore
    estimator: TokenEstimator
    sink: TraceSink
    ttl_ticks: int | None
    enable_critic: bool

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        """Pydantic v2 集成（core ids.py / revision.py 同构兜底模式）。

        本仓 pydantic 2.13 对 dataclass 成员标注非 runtime_checkable
        Protocol（InferenceBackend / TokenEstimator / TraceSink，W3/W4
        冻结定义零修改）不再生成 core schema；兜底 = 任意对象 + 校验链
        末端 ``AfterValidator`` isinstance 检查——``BuildResult(policy=...)``
        保持类型，错型 = ValidationError（K7 可检查不静默）。
        """

        def _check(value: object) -> object:
            if value is not None and not isinstance(value, cls):
                raise ValueError(
                    f"policy 字段必须是 {cls.__name__}（got {type(value).__name__}）"
                )
            return value

        return handler(Annotated[object, AfterValidator(_check)])

    def decide(self, context: ActorDecisionContext) -> ActionProposal | None:
        """P6 决策主流程（SOT §3.6 九步钉死；同步、单参，B-CON-1/2）。

        步骤 1-9 与 SOT §3.6 L356-365 逐条对应；传输异常原样上抛（house
        语义：fake 永不抛，httpx 面异常属运行时环境失败族，不吞不转）；
        组装/解析/critic 失败 = 显式 None（B-CON-3），不猜不 crash。
        """
        # ---- 1. 组装 -----------------------------------------------------
        result = assemble_prompt(
            context, self.store, self.estimator, capability=self.capability
        )
        if result.package is None:
            for diag in result.diagnostics:
                self.sink.record_diagnostic(diag)
            self.sink.record(
                "prompt_assembly",
                self._prompt_assembly_payload(
                    context, prompt_metadata_ref="assembly_failed", token_estimate=0
                ),
            )
            return None
        pkg = result.package

        # ---- 2. 请求构造（单 system 消息承载全层，Leader-A4 wire 最小面） --
        messages: tuple[WireMessage, ...] = (
            WireMessage(role="system", content=pkg.text),
        )
        request = InferenceRequest(
            messages=messages,
            model=self.resolved.model_id,
            base_url=self.resolved.base_url,
            api_key_env=self.resolved.api_key_env,
            temperature=self.resolved.temperature,
            max_tokens=None,
            timeout_seconds=self.resolved.timeout_seconds,
            logical_role=self.capability,
            profile=self.capability,
            base_revision=context.base_world_revision,
            prompt_metadata_ref=pkg.prompt_metadata_ref,
        )

        # ---- 3. 首次调用（latency 记录首次响应面） ------------------------
        response = self.backend.generate(request)
        first_latency_ms = response.latency_ms

        # ---- 4. 解析 ------------------------------------------------------
        parse = parse_llm_response(response.text)
        parse_retry = 0

        # ---- 5. repair 重试（parse 阶段至多 1 次，PARSE_RETRY_MAX=1） -----
        if parse.value is None:
            first_error = parse.error or "no-json-object"
            messages = messages + (
                WireMessage(role="user", content=repair_instruction((first_error,))),
            )
            request = request.model_copy(update={"messages": messages})
            response = self.backend.generate(request)
            parse_retry = 1
            parse = parse_llm_response(response.text)
            if parse.value is None:
                # ---- 6. 解析终败（双次失败 → 显式 no-op，B-CON-3 语义） ----
                self.sink.record_diagnostic(
                    RuntimeDiagnostic(
                        code=_PARSE_FAILED,
                        severity=DiagnosticSeverity.ERROR,
                        path=self.capability,
                        message="parse 双次失败，本 tick 决策 no-op",
                        refs=(first_error, parse.error or "no-json-object"),
                    )
                )
                self.sink.record(
                    "llm_call",
                    self._llm_call_payload(context, pkg, first_latency_ms, parse_retry),
                )
                return None
            self.sink.record_diagnostic(
                RuntimeDiagnostic(
                    code=_PARSE_RECOVERED,
                    severity=DiagnosticSeverity.WARNING,
                    path=self.capability,
                    message=f"parse 重试后恢复（首次错误：{first_error}）",
                    refs=(first_error,),
                )
            )
        wire = parse.value

        # ---- 7. critic（仅 enable_critic；one-shot repair） --------------
        if self.enable_critic:
            from src.engine_v2.llm.critic import critique, critique_instruction

            crit = critique(context, wire)
            if not crit.ok:
                messages = messages + (
                    WireMessage(role="user", content=critique_instruction(crit.errors)),
                )
                request = request.model_copy(update={"messages": messages})
                response = self.backend.generate(request)
                parse_retry = 1
                parse = parse_llm_response(response.text)
                if parse.value is None:
                    # critic 修复仍败 → 显式 no-op（不再重试，预算钉死）
                    self.sink.record_diagnostic(
                        RuntimeDiagnostic(
                            code=_PARSE_FAILED,
                            severity=DiagnosticSeverity.ERROR,
                            path=self.capability,
                            message="critic 修复失败，本 tick 决策 no-op",
                            refs=tuple(f"critic:{e}" for e in crit.errors),
                        )
                    )
                    self.sink.record(
                        "llm_call",
                        self._llm_call_payload(
                            context, pkg, first_latency_ms, parse_retry
                        ),
                    )
                    return None
                wire = parse.value

        # ---- 8. no-op 分支（合法跳过，非失败） ----------------------------
        if wire.action_id is None:
            self.sink.record(
                "llm_call",
                self._llm_call_payload(context, pkg, first_latency_ms, parse_retry),
            )
            return None

        # ---- 9. 提案分支（staleness 接线 + trace 记录 + artifact 落句柄） --
        valid_until = effective_valid_until(context, self.ttl_ticks)
        proposal = make_action_proposal(context, wire, valid_until=valid_until)
        prompt_ref = pkg.prompt_metadata_ref
        output_ref = (
            "output://"
            + str(context.actor_id)
            + ":"
            + str(context.tick)
            + ":"
            + str(int(context.base_world_revision))
        )
        self.sink.record(
            "prompt_assembly",
            self._prompt_assembly_payload(
                context,
                prompt_metadata_ref=prompt_ref,
                token_estimate=pkg.token_estimate,
            ),
        )
        self.sink.store_artifact(
            prompt_ref,
            {
                "actor_id": str(context.actor_id),
                "logical_role": self.capability,
                "base_revision": int(context.base_world_revision),
                "token_estimate": pkg.token_estimate,
                "prompt_metadata_ref": prompt_ref,
                "layer_count": len(pkg.layers),
            },
        )
        self.sink.record(
            "llm_call",
            self._llm_call_payload(context, pkg, first_latency_ms, parse_retry),
        )
        self.sink.store_artifact(output_ref, {"text": parse.raw_json})
        return proposal

    def _prompt_assembly_payload(
        self,
        context: ActorDecisionContext,
        *,
        prompt_metadata_ref: str,
        token_estimate: int,
    ) -> dict[str, object]:
        """prompt_assembly 事件 5 键 payload（键集封闭，机械断言）。"""
        payload: dict[str, object] = {
            "actor_id": str(context.actor_id),
            "tick": context.tick,
            "base_revision": int(context.base_world_revision),
            "prompt_metadata_ref": prompt_metadata_ref,
            "token_estimate": token_estimate,
        }
        assert frozenset(payload) == _PROMPT_ASSEMBLY_KEYS, (
            "prompt_assembly payload 键集必须与 5 键封闭集精确等值"
        )
        return payload

    def _llm_call_payload(
        self,
        context: ActorDecisionContext,
        pkg: PromptPackage,
        latency_ms: float,
        parse_retry: int,
    ) -> dict[str, object]:
        """llm_call 事件 9 键 payload（= LLM_CALL_PAYLOAD_KEYS，机械断言）。"""
        payload: dict[str, object] = {
            "logical_role": self.capability,
            "profile": self.capability,
            "resolved_model": self.resolved.model_id,
            "input_token_estimate": pkg.token_estimate,
            "prompt_metadata_ref": pkg.prompt_metadata_ref,
            "output_ref": (
                "output://"
                + str(context.actor_id)
                + ":"
                + str(context.tick)
                + ":"
                + str(int(context.base_world_revision))
            ),
            "latency_ms": latency_ms,
            "parse_retry": parse_retry,
            "base_revision": int(context.base_world_revision),
        }
        assert frozenset(payload) == LLM_CALL_PAYLOAD_KEYS, (
            "llm_call payload 键集必须与 LLM_CALL_PAYLOAD_KEYS 精确等值"
        )
        return payload


class BuildResult(BaseModel):
    """构造工厂结果（frozen pydantic，SOT §3.6）。

    resolve 失败 = ``policy None + 诊断``（显式失败面，D-P6-07，绝不回落
    任意模型）；resolved = ``policy + 原诊断``（below_ideal 警告随结果）。
    """

    model_config = ConfigDict(frozen=True)

    policy: LLMPolicy | None
    diagnostics: tuple[RuntimeDiagnostic, ...]


def build_llm_policy(
    *,
    capability: str,
    requirement: InferenceCapabilityProfile,
    deployment: DeploymentProfile,
    backend: InferenceBackend,
    store: TemplateStore,
    estimator: TokenEstimator,
    sink: TraceSink,
    ttl_ticks: int | None = None,
    enable_critic: bool = False,
) -> BuildResult:
    """构造工厂（SOT §3.6 步骤 1-3；router 失败 = 显式失败，绝不静默）。

    1. ``resolve_capability(deployment, requirement)``（§3.3）；
    2. resolved=None → ``BuildResult(None, 原诊断)``（绝不回落任意模型）；
    3. resolved → ``LLMPolicy(...)`` + 原诊断（below_ideal 警告随结果）。
    """
    result = resolve_capability(deployment, requirement)
    if result.resolved is None:
        return BuildResult(policy=None, diagnostics=result.diagnostics)
    policy = LLMPolicy(
        capability=capability,
        resolved=result.resolved,
        backend=backend,
        store=store,
        estimator=estimator,
        sink=sink,
        ttl_ticks=ttl_ticks,
        enable_critic=enable_critic,
    )
    return BuildResult(policy=policy, diagnostics=result.diagnostics)
