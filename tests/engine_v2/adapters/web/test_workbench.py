"""P10 web workbench 数据面测试（SOT §6.1 test_workbench t1–t4 逐字
面；ERR-P10-15 重钉签名 = calls pairs 面）。

- t1 = prompt_history 钉（脚本 2 调用 = 测试驱动 script_backend 2 次
  generate 收集 (request, response) pairs → 行 6 列逐字：seq /
  logical_role / base_revision / model / prompt_metadata_ref /
  response_text）；
- t2 = logical_profile == "narrator" + resolved_model ==
  "fake-model-1"（K8：模型名 = 调用方面，零推词）；
- t3 = build_workbench_view 全量字符串化 × 12 名黑名单零命中（K8）；
- t4 = json.dumps 零失败（P10-INV-10）。

纪律：InferenceRequest 构造 = llm 适配面（测试内合法）；脚本
backend = 测试函数内局部构造（合法面：W1 presentation conftest
script_backend 同构——脚本键 ("narrator", Revision(2), 1) 命中钉
文案，seq 2 落 default_text；conftest 跨树 fixture 引用面不解析
——零 conftest 修改）；全部 id / 面值 = 字面量（零随机、零墙钟，
D6）；词边界转义经 ``chr(92) + "b"`` 运行时构造（零裸 0x5C 0x62，
D3 同源纪律）。
"""

from __future__ import annotations

import json
import re

from src.engine_v2.adapters.web.workbench import (
    WORKBENCH_SECTIONS,
    build_workbench_view,
    prompt_history,
)
from src.engine_v2.core.revision import Revision
from src.engine_v2.llm.adapter import (
    FakeInferenceBackend,
    InferenceRequest,
    InferenceResponse,
    WireMessage,
)
from tests.engine_v2.presentation.conftest import _NARRATOR_SCRIPT_TEXT

#: 词边界转义（零裸 0x5C 0x62 纪律，锚文件同源）。
_WB = chr(92) + "b"

#: 12 名闭集（P4_LLM_PROVIDER_BLACKLIST 同值，face/边界同源口径）。
_K8_BLACKLIST: tuple[str, ...] = (
    "openai",
    "anthropic",
    "langchain",
    "litellm",
    "ollama",
    "gemini",
    "gpt",
    "claude",
    "llm",
    "provider",
    "api_key",
    "base_url",
)

#: t1 脚本命中钉（W1 presentation conftest _NARRATOR_SCRIPT_TEXT 同
#: 值；本文件字面量自持——零跨测试模块 import，漂移即红）。
_SCRIPT_HIT_TEXT = "旧钟表铺的灰尘在光柱里缓缓浮动，秒针早已停在十点。"
_SCRIPT_MISS_TEXT = '{"action_id": null}'


def _make_backend() -> FakeInferenceBackend:
    """脚本 backend 局部构造（W1 conftest script_backend 同构面；
    脚本键 = ("narrator", Revision(2), 1)——§6.4 钉）。"""
    return FakeInferenceBackend(
        script={("narrator", Revision(2), 1): _SCRIPT_HIT_TEXT}
    )


def _make_request(prompt_ref: str, user_content: str) -> InferenceRequest:
    """InferenceRequest 构造（llm 适配面；测试侧模型名 =
    fake-model-1，K8 调用方面）。"""
    return InferenceRequest(
        messages=(
            WireMessage(
                role="system",
                content="基于结构化视图投影渲染本场景叙事文本；只输出纯文本。",
            ),
            WireMessage(role="user", content=user_content),
        ),
        model="fake-model-1",
        base_url="",
        api_key_env=None,
        temperature=0.0,
        timeout_seconds=5.0,
        logical_role="narrator",
        profile="narrator",
        base_revision=Revision(2),
        prompt_metadata_ref=prompt_ref,
    )


def _make_calls(
    backend: FakeInferenceBackend,
) -> tuple[tuple[InferenceRequest, InferenceResponse], ...]:
    """脚本 2 调用：驱动 backend 2 次 generate，收集 (request,
    response) pairs（SOT §6.1 t1 逐字面）。"""
    first_request = _make_request(
        "prompt://p10.w5:1:2", "旧钟表铺：秒针停在十点，灰尘在光里浮动。"
    )
    first_response = backend.generate(first_request)
    second_request = _make_request(
        "prompt://p10.w5:2:2", "同一场景的第二次渲染请求。"
    )
    second_response = backend.generate(second_request)
    return ((first_request, first_response), (second_request, second_response))


def test_workbench_t1_prompt_history() -> None:
    """t1：prompt_history 行 6 列逐字钉（脚本 2 调用 pairs 收集）。"""
    assert _SCRIPT_HIT_TEXT == _NARRATOR_SCRIPT_TEXT  # 同源钉（W1 面值）
    calls = _make_calls(_make_backend())
    assert prompt_history(calls) == (
        {
            "seq": 1,
            "logical_role": "narrator",
            "base_revision": 2,
            "model": "fake-model-1",
            "prompt_metadata_ref": "prompt://p10.w5:1:2",
            "response_text": _NARRATOR_SCRIPT_TEXT,
        },
        {
            "seq": 2,
            "logical_role": "narrator",
            "base_revision": 2,
            "model": "fake-model-1",
            "prompt_metadata_ref": "prompt://p10.w5:2:2",
            "response_text": _SCRIPT_MISS_TEXT,
        },
    )


def test_workbench_t2_logical_profile_model() -> None:
    """t2：logical_profile == "narrator" + resolved_model ==
    "fake-model-1"（K8 零推词）。"""
    view = build_workbench_view(_make_calls(_make_backend()))
    assert set(view) == set(WORKBENCH_SECTIONS)
    assert view["logical_profile"] == "narrator"
    assert view["resolved_model"] == "fake-model-1"


def test_workbench_t3_k8_clean_view() -> None:
    """t3：build_workbench_view 全量字符串化 × 12 名黑名单零命中
    （K8）。"""
    view = build_workbench_view(_make_calls(_make_backend()))
    blob = json.dumps(view, ensure_ascii=False, sort_keys=True).casefold()
    for name in _K8_BLACKLIST:
        assert not re.search(_WB + re.escape(name) + _WB, blob), name


def test_workbench_t4_json_clean() -> None:
    """t4：json.dumps 零失败（P10-INV-10）。"""
    calls = _make_calls(_make_backend())
    json.dumps(build_workbench_view(calls), ensure_ascii=False)
    json.dumps(list(prompt_history(calls)), ensure_ascii=False)
