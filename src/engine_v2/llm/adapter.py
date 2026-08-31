"""P6-W3 T04 传输面（SOT §3.4）：wire 协议接口（供应商无关）+ httpx 同步客户端
+ Fake 推理后端 + 注入单调时钟 seam（K7，D-P6-19）。

本模块是 P6 唯一触碰网络库与 ``time`` 标准库的模块（两处文档化例外，§3
导入纪律 D-P6-13；TestP6Boundary 方法 5 机械锁）：``httpx``（同步客户端，
Leader-A4）与 ``time``（仅 ``SystemMonotonicClock`` 实现体消费）。

纪律：同步面（Spec §31.1 async 签名偏差 DEV-2）；零内置重试（重试语义归
structured/policy 层，D-P6-09）；零日志输出（structlog 不 import——日志面归
宿主，Leader-A5「密钥值永不入日志」机械面之一）；凭据值只存在于 header
构造局部变量，永不进入任何异常 message / 诊断 / 记录（#12 探针断言）。
"""

from __future__ import annotations

import os
import time
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field

from src.engine_v2.core.revision import Revision

__all__ = [
    "MonotonicClock",
    "SystemMonotonicClock",
    "FixedMonotonicClock",
    "WireMessage",
    "InferenceRequest",
    "InferenceResponse",
    "InferenceBackend",
    "HttpxInferenceBackend",
    "FakeInferenceBackend",
    "InferenceConfigError",
    "InferenceTransportError",
]

#: 本模块消费的 INFERENCE 族诊断码（§8.1 共 7 码，W3 相关 5 码；21 码闭集见 §8.1）。
_ENDPOINT_MISSING = "LLMSIM_INFERENCE_ENDPOINT_MISSING"
_CREDENTIAL_MISSING = "LLMSIM_INFERENCE_CREDENTIAL_MISSING"
_TRANSPORT = "LLMSIM_INFERENCE_TRANSPORT"
_HTTP = "LLMSIM_INFERENCE_HTTP"
_MALFORMED_RESPONSE = "LLMSIM_INFERENCE_MALFORMED_RESPONSE"


class MonotonicClock(Protocol):
    """单调时钟注入 seam（K7，D-P6-19；模式 = P5 DslRng 注入先例 D-P5-15）。

    ``now_ms`` 返回单调非减的毫秒值；生产面 = ``SystemMonotonicClock``，
    测试面 = ``FixedMonotonicClock``（确定性双跑的延迟来源，#17）。
    结构化使用（无 runtime_checkable，SOT §3.4 L254 Protocol 面）。
    """

    def now_ms(self) -> int:
        """返回当前单调时刻（毫秒，单调非减）。"""
        ...


class SystemMonotonicClock:
    """生产面单调时钟（本模块唯一 ``time`` 消费点）。

    ``now_ms`` = ``time.monotonic_ns() // 1_000_000``（SOT §3.4 逐字）。
    """

    def now_ms(self) -> int:
        """返回当前单调时刻（毫秒，单调非减）。"""
        return time.monotonic_ns() // 1_000_000


class FixedMonotonicClock:
    """测试面确定性单调时钟（后置自增：首次 ``now_ms()`` = ``start_ms``）。

    每次调用返回当前值后自增 ``step_ms``（SOT §3.4 L256）；确定性双跑的延迟
    来源（#17）：同脚本同序列同输出。
    """

    def __init__(self, *, start_ms: int = 0, step_ms: int = 1) -> None:
        self._next_ms = start_ms
        self._step_ms = step_ms

    def now_ms(self) -> int:
        """返回当前值，然后自增 ``step_ms``（后置自增）。"""
        value = self._next_ms
        self._next_ms += self._step_ms
        return value


class WireMessage(BaseModel):
    """供应商无关最小消息面（Leader-A4）：role 三值闭集 + content 原文。"""

    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str


class InferenceRequest(BaseModel):
    """一次推理调用请求（frozen pydantic，``extra="forbid"``；11 字段，
    序 = SOT §3.4 L258-270 表序）。

    - ``messages`` min_length=1（供应商无关最小消息面）；
    - ``model`` / 端点 / ``temperature`` / ``timeout_seconds`` 取自
      ``ResolvedModel``（§3.3 router 产物；端点可为空串——调用期拦截，
      非 resolve 期）；
    - ``api_key_env`` 只名（Leader-A5）：值在 ``generate`` 内从
      ``os.environ`` 解析，解析后立即进入 header，不落任何记录；
    - ``logical_role`` / ``profile`` = trace 键同名，两值 = capability
      同串（#19）；
    - ``base_revision`` = 调用刻 context 基线（trace ``base_revision``
      键源；core ``Revision``：接受原生 int，构造后 ``type is Revision``）；
    - ``prompt_metadata_ref`` = 确定性句柄
      ``prompt://{actor_id}:{tick}:{base_revision}``（§3.6 格式，本波只
      存不校验）。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    messages: tuple[WireMessage, ...] = Field(min_length=1)
    model: str
    base_url: str
    api_key_env: str | None
    temperature: float
    max_tokens: int | None = None
    timeout_seconds: float
    logical_role: str
    profile: str
    base_revision: Revision
    prompt_metadata_ref: str


class InferenceResponse(BaseModel):
    """一次推理调用响应（frozen pydantic）。

    ``text`` = 原始输出文本；``model`` = 调用回报模型名（缺省 =
    request.model）；``latency_ms`` ≥ 0 = 注入时钟差（调用前/后）；
    ``input_tokens`` / ``output_tokens`` = usage 字段（缺失 / 非 int →
    None → trace 用估计值）。
    """

    model_config = ConfigDict(frozen=True)

    text: str
    model: str
    latency_ms: float = Field(ge=0)
    input_tokens: int | None
    output_tokens: int | None


class InferenceBackend(Protocol):
    """wire 可替换接口本体（同步——Spec §31.1 async 签名偏差 DEV-2）。

    非 core contract 一部分（Leader-A4）；生产面 = ``HttpxInferenceBackend``，
    测试 / 进程内面 = ``FakeInferenceBackend`` 或注入 ``transport`` 的
    ``HttpxInferenceBackend``。
    """

    def generate(self, request: InferenceRequest) -> InferenceResponse:
        """执行一次同步推理调用，返回原始输出响应。"""
        ...


def _extract_content(payload: dict[str, object]) -> str | None:
    """读 ``choices[0].message.content``；任一层缺失 / 非 str → None。"""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    return content if isinstance(content, str) else None


def _usage_int(usage: object, key: str) -> int | None:
    """读 usage 整数字段；缺失 / 非 int（含 bool）→ None。"""
    if not isinstance(usage, dict):
        return None
    value = usage.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


class HttpxInferenceBackend:
    """同步 httpx 推理后端（本模块唯一 ``httpx`` 使用面）。

    ``__init__``：``clock=None`` → ``SystemMonotonicClock``（生产面）；
    ``transport`` 注入 seam：None = 真实网络栈（生产面），非 None（如
    ``httpx.MockTransport``）= 进程内注入面（S0：零真实网络）。

    ``generate`` 次序钉死（1→9 严格次序，SOT §3.4 L274-283）：端点空 →
    ENDPOINT_MISSING；凭据 env 变量名非 None 但 ``os.environ`` 缺该变量 →
    CREDENTIAL_MISSING（message 只含变量名）；端点 = 端点
    ``rstrip("/")`` + ``/chat/completions``（默认 wire 约定 = 供应商侧通用
    ``/chat/completions`` wire 形状，Leader-A4；可替换性 = 换 Backend 实现
    或换端点，非改本模块）；body = model / messages / temperature
    （+ ``max_tokens`` 仅非 None 时）；header = Authorization Bearer
    （仅凭据 env 变量名非 None 时）+ ``Content-Type: application/json``
    （恒在）；同步 POST（凭据值只存在于 header 构造局部变量）；网络异常 /
    超时 → TRANSPORT（refs=[异常类名]）；非 2xx → HTTP（refs=[str(status)]，
    status = 状态码）；响应无 ``choices[0].message.content`` →
    MALFORMED_RESPONSE；成功 → ``InferenceResponse``（latency = 调用前/后
    时钟差；``model`` = 响应 JSON "model" 键非空时取之、否则
    request.model；usage 映射 "prompt_tokens" / "completion_tokens"，
    缺失 / 非 int → None）。

    零内置重试（D-P6-09）；零日志。
    """

    def __init__(
        self,
        *,
        clock: MonotonicClock | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._clock: MonotonicClock = SystemMonotonicClock() if clock is None else clock
        self._transport = transport

    def generate(self, request: InferenceRequest) -> InferenceResponse:
        """执行一次同步推理调用（1→9 次序钉死；失败抛对应 Inference*Error）。"""
        if not request.base_url:
            raise InferenceConfigError("inference endpoint is empty", code=_ENDPOINT_MISSING)
        api_key: str | None = None
        if request.api_key_env is not None:
            api_key = os.environ.get(request.api_key_env)
            if api_key is None:
                raise InferenceConfigError(
                    f"credential env variable not set: {request.api_key_env}",
                    code=_CREDENTIAL_MISSING,
                )
        endpoint = request.base_url.rstrip("/") + "/chat/completions"
        body: dict[str, object] = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key is not None:
            headers["Authorization"] = f"Bearer {api_key}"
        started_ms = self._clock.now_ms()
        try:
            with httpx.Client(
                timeout=request.timeout_seconds, transport=self._transport
            ) as client:
                response = client.post(endpoint, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise InferenceTransportError(
                f"transport failure: {exc.__class__.__name__}",
                code=_TRANSPORT,
                status=None,
                refs=(exc.__class__.__name__,),
            ) from exc
        finished_ms = self._clock.now_ms()
        latency_ms = float(finished_ms - started_ms)
        if not 200 <= response.status_code < 300:
            raise InferenceTransportError(
                f"non-2xx response status: {response.status_code}",
                code=_HTTP,
                status=response.status_code,
                refs=(str(response.status_code),),
            )
        raw: object
        try:
            raw = response.json()
        except ValueError:
            raw = None
        payload: dict[str, object] = raw if isinstance(raw, dict) else {}
        content = _extract_content(payload)
        if content is None:
            raise InferenceTransportError(
                "response missing choices[0].message.content",
                code=_MALFORMED_RESPONSE,
                status=None,
                refs=(),
            )
        model = request.model
        reported = payload.get("model")
        if isinstance(reported, str) and reported:
            model = reported
        usage = payload.get("usage")
        return InferenceResponse(
            text=content,
            model=model,
            latency_ms=latency_ms,
            input_tokens=_usage_int(usage, "prompt_tokens"),
            output_tokens=_usage_int(usage, "completion_tokens"),
        )


class FakeInferenceBackend:
    """脚本化确定性推理后端（T09 核心；测试面 / 进程内面）。

    ``generate``：调用序号 ``seq`` = 本实例 generate 计数 +1（1-based）；
    查找键 (``logical_role``, ``base_revision``, ``seq``) ∈ script → 命中
    值，否则 ``default_text``（``{"action_id": null}`` = 合法 no-op，
    B-CON-3 None 路径）；返回 ``InferenceResponse(text=命中值,
    model=request.model, latency_ms=base_latency_ms, input_tokens=None,
    output_tokens=None)``。

    ``calls`` = 只读调用史（每次 generate 追加后重建 tuple；测试断言调用
    次数 / 请求面，#15 / Leader-A6 消费）。确定性条款：脚本化 + 序号寻址
    → 同脚本同序列同输出（#17 双跑字节相等的 fake 面）；支持预制坏 JSON
    文本（"sorry, I cannot answer" 形态）与一次坏 JSON 情形（Leader-A7）。
    """

    def __init__(
        self,
        *,
        # §3.4 L285 签名逐字保留（只读不修改，无共享突变风险）：
        script: dict[tuple[str, Revision, int], str] = {},
        default_text: str = '{"action_id": null}',
        base_latency_ms: float = 5.0,
    ) -> None:
        self._script = script
        self._default_text = default_text
        self._base_latency_ms = base_latency_ms
        self._calls: tuple[InferenceRequest, ...] = ()

    @property
    def calls(self) -> tuple[InferenceRequest, ...]:
        """只读调用史（按调用序追加）。"""
        return self._calls

    def generate(self, request: InferenceRequest) -> InferenceResponse:
        """按 (logical_role, base_revision, 调用序号) 查脚本；未命中落 default_text。"""
        seq = len(self._calls) + 1
        text = self._script.get(
            (request.logical_role, request.base_revision, seq),
            self._default_text,
        )
        self._calls = self._calls + (request,)
        return InferenceResponse(
            text=text,
            model=request.model,
            latency_ms=self._base_latency_ms,
            input_tokens=None,
            output_tokens=None,
        )


class InferenceConfigError(ValueError):
    """配置错误（ValueError 族，D-P4-17 两族风格延续）：端点缺失 / 凭据 env 变量缺失。

    ``code`` ∈ INFERENCE 族诊断码（§8.1）；message 零凭据值（Leader-A5
    机械面；#12 探针断言）。
    """

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class InferenceTransportError(Exception):
    """传输错误（Exception 族）：网络异常 / 超时、非 2xx、malformed 响应。

    属性：``code`` ∈ INFERENCE 族诊断码（§8.1）；``status``（TRANSPORT =
    None；HTTP = 状态码；MALFORMED_RESPONSE = None）；``refs`` 默认空元组
    （步骤面 = 更细规格面，A-W3-1：步骤 6 refs=[异常类名]，步骤 7
    refs=[str(status)]）。message 零凭据值。
    """

    def __init__(
        self,
        message: str,
        *,
        code: str,
        status: int | None = None,
        refs: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.refs = refs
