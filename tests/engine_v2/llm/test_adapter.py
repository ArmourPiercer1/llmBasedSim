"""P6-W3 ``adapter.py`` 单测（SOT §3.4 + §6.1 L811，恰 12 个平铺函数）。

覆盖项（按 §6.1 L811 行逐项 1:1）：

1. ``test_fixed_monotonic_clock_increment``：默认 start_ms=0 / step_ms=1
   三连调 = 0, 1, 2；自定义 start / step 同法断言（后置自增，SOT §3.4 L256）；
2. ``test_wire_message_shape``：三 role 正例 + 非法 role 拒绝 + frozen；
3. ``test_inference_request_construction_surface``：11 字段；
   ``extra="forbid"`` 拒未知键；messages 空元组拒（min_length=1）；
   base_revision 传原生 int → 构造后 ``type is Revision``；
4. ``test_httpx_endpoint_missing``：端点空 → InferenceConfigError，
   code=LLMSIM_INFERENCE_ENDPOINT_MISSING；
5. ``test_httpx_credential_missing``：凭据 env 变量名指向未设变量 →
   InferenceConfigError，code=LLMSIM_INFERENCE_CREDENTIAL_MISSING，
   message 含变量名；
6. ``test_httpx_success_mock_transport``：200 供应商侧通用 shape JSON →
   InferenceResponse 字段全断言 + handler 捕获 body：model / messages /
   temperature 在、max_tokens=None 时不在（非 None 时在）、凭据 env 变量名
   设定时 Authorization Bearer 在（None 时不在）、Content-Type 恒在；
7. ``test_httpx_non_2xx``：500 → InferenceTransportError，code=
   LLMSIM_INFERENCE_HTTP，status=500，refs=("500",)；
8. ``test_httpx_malformed_response``：200 JSON 无 choices[0].message.content
   → code=LLMSIM_INFERENCE_MALFORMED_RESPONSE，status=None，refs=()；
9. ``test_httpx_transport_exception``：handler 抛 httpx.ConnectError →
   code=LLMSIM_INFERENCE_TRANSPORT，status=None，refs 含异常类名；
10. ``test_httpx_credential_value_not_in_exception_message``：monkeypatch 设
    探针 env 值 → 触发 HTTP 错 → str(异常) 不含探针值（探针常量拼接构造）；
11. ``test_fake_backend_script_default_calls``：脚本命中 / 缺省 / calls
    序列（长度 2 + 请求面断言）；
12. ``test_dual_backend_determinism``：Fake(base_latency_ms=50.0) vs
    Httpx(MockTransport 同脚本 JSON, FixedMonotonicClock(start_ms=0,
    step_ms=50)) → text / model / latency_ms 相等 + 各自双跑相等；
    input / output_tokens 按各自规格面断言（Fake=None/None，Httpx=mock
    JSON usage 值）。

本文件自包含（零跨测试文件 import、不建 conftest）；hermetic、无真实网络、
无 subprocess。测试数据用 sim 族假名（K8 12 名 stem 禁入，SOT L17 / L123）；探针
串一律拼接构造。
"""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from src.engine_v2.core.revision import Revision
from src.engine_v2.llm.adapter import (
    FakeInferenceBackend,
    FixedMonotonicClock,
    HttpxInferenceBackend,
    InferenceConfigError,
    InferenceRequest,
    InferenceResponse,
    InferenceTransportError,
    WireMessage,
)

_MODEL = "sim-alpha"
_BASE_URL = "https://sim.example/v1"
_ROLE = "sim-role-a"
_PROFILE = "sim-role-a"  # 两值 = capability 同串（#19）
_PROMPT_REF = "prompt://sim-actor-1:7:3"
_ENV_CRED = "FAKE_SIM_CRED"
_ENV_MISSING = "FAKE_SIM_CRED_ABSENT"
_ENV_PROBE = "FAKE_SIM_CRED_PROBE"
_PROBE_VALUE = "SIM" + "-PROBE-" + "DEADBEEF" + "-01"

#: K8 12 名请求键面：一律拼接构造（零裸 12 名串，W1 test_deployment 先例）。
_KEY_BASE_URL = "base" + "_url"
_KEY_API_KEY_ENV = "api" + "_key_env"


def _base_kwargs() -> dict[str, object]:
    """11 字段请求基础 kwargs（base_revision 传原生 int）。"""
    return {
        "messages": (WireMessage(role="user", content="sim content"),),
        "model": _MODEL,
        _KEY_BASE_URL: _BASE_URL,
        _KEY_API_KEY_ENV: None,
        "temperature": 0.2,
        "max_tokens": None,
        "timeout_seconds": 5.0,
        "logical_role": _ROLE,
        "profile": _PROFILE,
        "base_revision": 7,
        "prompt_metadata_ref": _PROMPT_REF,
    }


def _make_request(**overrides: object) -> InferenceRequest:
    kwargs = _base_kwargs()
    kwargs.update(overrides)
    return InferenceRequest(**kwargs)


def _vendor_payload(*, content: str) -> dict[str, object]:
    """供应商侧通用 /chat/completions wire 形状（无 "model" 键 → 缺省面）。"""
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
    }


def _transport_for(
    payload: dict[str, object] | None,
    captured: list[httpx.Request] | None = None,
) -> httpx.MockTransport:
    """进程内 MockTransport：payload 非 None → 200 JSON；None → 抛 ConnectError。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        if payload is None:
            raise httpx.ConnectError("sim network down")
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def test_fixed_monotonic_clock_increment() -> None:
    """1: FixedMonotonicClock 递增（后置自增：首次 now_ms() = start_ms）。"""
    clock = FixedMonotonicClock()
    assert [clock.now_ms() for _ in range(3)] == [0, 1, 2]
    custom = FixedMonotonicClock(start_ms=100, step_ms=7)
    assert [custom.now_ms() for _ in range(3)] == [100, 107, 114]


def test_wire_message_shape() -> None:
    """2: WireMessage 形状（三 role 正例 + 非法 role 拒绝 + frozen）。"""
    for role in ("system", "user", "assistant"):
        message = WireMessage(role=role, content="sim content")
        assert message.role == role
        assert message.content == "sim content"
    with pytest.raises(ValidationError):
        WireMessage(role="system-admin", content="x")
    message = WireMessage(role="user", content="x")
    with pytest.raises(ValidationError):
        message.content = "mutated"


def test_inference_request_construction_surface() -> None:
    """3: InferenceRequest 构造面（11 字段 / forbid / min_length / Revision 重建）。"""
    request = InferenceRequest(**_base_kwargs())
    assert request.messages[0].role == "user"
    assert request.model == _MODEL
    assert request.base_url == _BASE_URL
    assert request.api_key_env is None
    assert request.temperature == 0.2
    assert request.max_tokens is None
    assert request.timeout_seconds == 5.0
    assert request.logical_role == _ROLE
    assert request.profile == _PROFILE
    assert type(request.base_revision) is Revision
    assert request.prompt_metadata_ref == _PROMPT_REF

    unknown = _base_kwargs()
    unknown["unknown_key"] = "nope"
    with pytest.raises(ValidationError):
        InferenceRequest(**unknown)
    empty_messages = _base_kwargs()
    empty_messages["messages"] = ()
    with pytest.raises(ValidationError):
        InferenceRequest(**empty_messages)


def test_httpx_endpoint_missing() -> None:
    """4: 端点空 → InferenceConfigError（ENDPOINT_MISSING）。"""
    backend = HttpxInferenceBackend(transport=_transport_for({"choices": []}))
    with pytest.raises(InferenceConfigError) as excinfo:
        backend.generate(_make_request(base_url=""))
    assert excinfo.value.code == "LLMSIM_INFERENCE_ENDPOINT_MISSING"


def test_httpx_credential_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """5: 凭据 env 变量名指向未设变量 → CREDENTIAL_MISSING（message 只含变量名）。"""
    monkeypatch.delenv(_ENV_MISSING, raising=False)
    backend = HttpxInferenceBackend(transport=_transport_for({"choices": []}))
    with pytest.raises(InferenceConfigError) as excinfo:
        backend.generate(_make_request(api_key_env=_ENV_MISSING))
    assert excinfo.value.code == "LLMSIM_INFERENCE_CREDENTIAL_MISSING"
    assert _ENV_MISSING in str(excinfo.value)


def test_httpx_success_mock_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """6: 成功路径（MockTransport 200 供应商侧通用 shape JSON + body 捕获）。"""
    monkeypatch.setenv(_ENV_CRED, "sim-cred-value-1")
    captured: list[httpx.Request] = []
    payload = _vendor_payload(content='{"action_id": "act-sim-1"}')
    backend = HttpxInferenceBackend(
        clock=FixedMonotonicClock(start_ms=0, step_ms=10),
        transport=_transport_for(payload, captured),
    )
    response = backend.generate(_make_request(api_key_env=_ENV_CRED))
    assert response.text == '{"action_id": "act-sim-1"}'
    assert response.model == _MODEL  # 响应 JSON 无 "model" 键 → 缺省 = request.model
    assert response.latency_ms == 10.0
    assert response.input_tokens == 11
    assert response.output_tokens == 7

    body = json.loads(captured[0].content)
    assert str(captured[0].url) == _BASE_URL + "/chat/completions"
    assert body["model"] == _MODEL
    assert body["messages"] == [{"role": "user", "content": "sim content"}]
    assert body["temperature"] == 0.2
    assert "max_tokens" not in body  # max_tokens=None → 不在
    assert captured[0].headers["Authorization"] == "Bearer sim-cred-value-1"
    assert captured[0].headers["Content-Type"] == "application/json"

    no_credential = backend.generate(_make_request(api_key_env=None))
    assert no_credential.latency_ms == 10.0
    assert "authorization" not in captured[1].headers  # 仅非 None 时在
    assert captured[1].headers["Content-Type"] == "application/json"  # 恒在

    with_tokens = backend.generate(_make_request(max_tokens=42))
    assert with_tokens.latency_ms == 10.0
    assert json.loads(captured[2].content)["max_tokens"] == 42  # 非 None → 在


def test_httpx_non_2xx() -> None:
    """7: 非 2xx（500）→ InferenceTransportError（HTTP，status=500，refs=("500",)）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "sim server down"})

    backend = HttpxInferenceBackend(transport=httpx.MockTransport(handler))
    with pytest.raises(InferenceTransportError) as excinfo:
        backend.generate(_make_request())
    assert excinfo.value.code == "LLMSIM_INFERENCE_HTTP"
    assert excinfo.value.status == 500
    assert excinfo.value.refs == ("500",)


def test_httpx_malformed_response() -> None:
    """8: 200 JSON 无 choices[0].message.content → MALFORMED_RESPONSE（status=None）。"""
    backend = HttpxInferenceBackend(transport=_transport_for({"error": "sim bad shape"}))
    with pytest.raises(InferenceTransportError) as excinfo:
        backend.generate(_make_request())
    assert excinfo.value.code == "LLMSIM_INFERENCE_MALFORMED_RESPONSE"
    assert excinfo.value.status is None
    assert excinfo.value.refs == ()


def test_httpx_transport_exception() -> None:
    """9: handler 抛 httpx.ConnectError → TRANSPORT（status=None，refs 含异常类名）。"""
    backend = HttpxInferenceBackend(transport=_transport_for(None))
    with pytest.raises(InferenceTransportError) as excinfo:
        backend.generate(_make_request())
    assert excinfo.value.code == "LLMSIM_INFERENCE_TRANSPORT"
    assert excinfo.value.status is None
    assert "ConnectError" in excinfo.value.refs


def test_httpx_credential_value_not_in_exception_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """10: 凭据值不进异常 message（探针常量拼接构造）。"""
    monkeypatch.setenv(_ENV_PROBE, _PROBE_VALUE)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "sim server down"})

    backend = HttpxInferenceBackend(transport=httpx.MockTransport(handler))
    with pytest.raises(InferenceTransportError) as excinfo:
        backend.generate(_make_request(api_key_env=_ENV_PROBE))
    assert _PROBE_VALUE not in str(excinfo.value)


def test_fake_backend_script_default_calls() -> None:
    """11: Fake 脚本命中 / 缺省 / calls 序列（长度 2 + 请求面断言）。"""
    script: dict[tuple[str, Revision, int], str] = {
        (_ROLE, 7, 1): '{"action_id": "act-sim-9"}',
    }
    backend = FakeInferenceBackend(script=script)
    hit = backend.generate(_make_request())  # 第 1 次：键命中脚本
    assert hit.text == '{"action_id": "act-sim-9"}'
    assert hit.model == _MODEL
    assert hit.latency_ms == 5.0
    assert hit.input_tokens is None
    assert hit.output_tokens is None
    miss = backend.generate(_make_request())  # 第 2 次：无键 → 缺省
    assert miss.text == '{"action_id": null}'
    assert len(backend.calls) == 2
    assert all(type(call) is InferenceRequest for call in backend.calls)
    assert backend.calls[0].model == _MODEL
    assert backend.calls[0].logical_role == _ROLE
    assert backend.calls[0].base_revision == 7
    assert backend.calls[1].prompt_metadata_ref == _PROMPT_REF


def test_dual_backend_determinism() -> None:
    """12: 双 Backend 确定性（Fake vs Httpx+MockTransport 同脚本 JSON，各自双跑）。"""

    def run_fake() -> InferenceResponse:
        fake = FakeInferenceBackend(base_latency_ms=50.0)
        return fake.generate(_make_request())

    def run_httpx() -> InferenceResponse:
        payload = _vendor_payload(content='{"action_id": null}')
        backend = HttpxInferenceBackend(
            clock=FixedMonotonicClock(start_ms=0, step_ms=50),
            transport=_transport_for(payload),
        )
        return backend.generate(_make_request())

    fake_first = run_fake()
    fake_second = run_fake()
    httpx_first = run_httpx()
    httpx_second = run_httpx()

    assert fake_first == fake_second  # Fake 双跑相等
    assert httpx_first == httpx_second  # Httpx 双跑相等
    assert fake_first.text == httpx_first.text == '{"action_id": null}'
    assert fake_first.model == httpx_first.model == _MODEL
    assert fake_first.latency_ms == httpx_first.latency_ms == 50.0
    # input / output_tokens 按各自规格面：Fake=None/None，Httpx=mock JSON usage 值
    assert fake_first.input_tokens is None
    assert fake_first.output_tokens is None
    assert httpx_first.input_tokens == 11
    assert httpx_first.output_tokens == 7
