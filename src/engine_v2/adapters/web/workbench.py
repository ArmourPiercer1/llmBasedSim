"""P10 Web workbench prompt/trace 数据面（T07；SOT §3.11；导出 3 名）。

来源 = Spec §38（prompt/trace 最小视图）+ §45 主流程（宿主面）+
Plan §19 T07；K8（部署与项目分离）最小面：模型名 = 调用方面（测试
面值 fake-model-1，零供应商词）；零部署解析（P6 deployment 不消
费）。**ERR-P10-15 重钉签名 = calls pairs 面**（非 session）：
workbench 数据面 = 推理调用对流的纯投影（零会话状态、零回查、
确定性重跑字节相等，D6）。数据面经模块函数直调消费（W4 api
``/api/workbench/{id}`` = 404 信封保留行；W5 零路由改，SOT §3.11 /
Leader 裁决面）。

冻结消费面（只读）：P4 推理后端适配模块（``InferenceRequest`` /
``InferenceResponse`` frozen 模型 + ``WireMessage`` 词表面；import
闭集面 SOT §3.0 钉）。

纪律（P10-INV-1/4/10，D6，K8）：全输出面 JSON-clean（P10-INV-10，
t4 json.dumps 钉）；零 wall-clock / 零随机（D6）；零模块级实例
（P10-INV-4，A3 AST）；**零 core.entity / core.components 直读
import**（P10-INV-5 特例钉，face t4 / 边界 m4 AST 核）；12 名闭集
零命中（face t3 / 边界 m3 钉）。

8 节语义钉（SOT §3.11；「最近」= ``calls[-1]``）：

- ``assembled_prompt`` = 最近 request.messages 投影（逐消息
  ``{"role", "content"}``，消息序保留）；
- ``prompt_layers`` = messages 层序摘要（逐层 ``{"seq", "role",
  "content_chars"}``；seq = 1-based）；
- ``context_provenance`` = ``{"base_revision", "prompt_metadata_ref"}``
  （最近 request 面；base_revision 整型投影）；
- ``token_usage`` = ``{"input_tokens", "output_tokens"}``（最近
  response 面；None 显式保留 = 未测量 ≠ 0，KBC-7 严格 Optional）；
- ``logical_profile`` = 最近 request.logical_role；
- ``resolved_model`` = 最近 request.model（K8：模型名 = 调用方面，
  零推断）；
- ``structured_output`` = 最近 response.text（**原样保留**——解析
  失败原样保留，零重序列化）；
- ``critic_repair`` = ``{"supported": False}``（P10 零 critic
  实现——非范围标记面）。

空 calls → 确定性空面（8 键全在位：list = [] / 标量 = None /
critic_repair = ``{"supported": False}``）。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from src.engine_v2.llm.adapter import InferenceRequest, InferenceResponse

__all__ = [
    "WORKBENCH_SECTIONS",
    "build_workbench_view",
    "prompt_history",
]

#: workbench 8 节名（SOT §3.11 逐字序，序钉）。
WORKBENCH_SECTIONS: Final[tuple[str, ...]] = (
    "assembled_prompt",
    "prompt_layers",
    "context_provenance",
    "token_usage",
    "logical_profile",
    "resolved_model",
    "structured_output",
    "critic_repair",
)

#: critic_repair 节值（P10 零 critic 实现——非范围标记面，钉死）。
_CRITIC_REPAIR: Final[dict[str, bool]] = {"supported": False}


def _empty_view() -> dict[str, object]:
    """空 calls 确定性空面（8 键全在位，钉死）。"""
    return {
        "assembled_prompt": [],
        "prompt_layers": [],
        "context_provenance": {
            "base_revision": None,
            "prompt_metadata_ref": None,
        },
        "token_usage": {
            "input_tokens": None,
            "output_tokens": None,
        },
        "logical_profile": None,
        "resolved_model": None,
        "structured_output": None,
        "critic_repair": dict(_CRITIC_REPAIR),
    }


def build_workbench_view(
    calls: Sequence[tuple[InferenceRequest, InferenceResponse]],
) -> dict[str, object]:
    """8 节纯投影（SOT §3.11；ERR-P10-15 calls pairs 面；零反作用）。

    「最近」= ``calls[-1]``；空 calls → 确定性空面（8 键全在位）。
    键序 = :data:`WORKBENCH_SECTIONS` 逐字序；JSON-clean
    （P10-INV-10）。
    """
    if len(calls) == 0:
        return _empty_view()
    request, response = calls[-1]
    return {
        "assembled_prompt": [
            {"role": message.role, "content": message.content}
            for message in request.messages
        ],
        "prompt_layers": [
            {
                "seq": index + 1,
                "role": message.role,
                "content_chars": len(message.content),
            }
            for index, message in enumerate(request.messages)
        ],
        "context_provenance": {
            "base_revision": int(request.base_revision),
            "prompt_metadata_ref": request.prompt_metadata_ref,
        },
        "token_usage": {
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
        },
        "logical_profile": request.logical_role,
        "resolved_model": request.model,
        "structured_output": response.text,
        "critic_repair": dict(_CRITIC_REPAIR),
    }


def prompt_history(
    calls: Sequence[tuple[InferenceRequest, InferenceResponse]],
) -> tuple[dict, ...]:
    """prompt 史行元组（Spec §38 6 列；seq = 1-based；调用序保留）。

    行键闭集：seq / logical_role / base_revision / model /
    prompt_metadata_ref / response_text（W4 views.py 冻结表头
    ``_WORKBENCH_COLUMNS`` 同序，双常量零环——不 import views）。
    """
    return tuple(
        {
            "seq": index + 1,
            "logical_role": request.logical_role,
            "base_revision": int(request.base_revision),
            "model": request.model,
            "prompt_metadata_ref": request.prompt_metadata_ref,
            "response_text": response.text,
        }
        for index, (request, response) in enumerate(calls)
    )
