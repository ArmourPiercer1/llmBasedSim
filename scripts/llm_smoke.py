"""P6-W6 推理侧冒烟脚本（SOT §3.13 交付面；纯函数 main，零 subprocess）。

用途：以显式部署配置路径做一次真实推理侧调用（单一同步后端，无重试、
无修复轮次），打印 9 键形状的结果摘要（键集 = core trace 封闭集）后退出。

退出码（钉死）：

- 0 = 调用成功（已打印结果摘要 JSON）；
- 3 = 引导性失败（缺部署路径 / 部署加载失败 / 能力位未解析 / 凭据 env
  变量缺失）——打印引导文案；
- 4 = 运行期异常——只打印异常类名（不打印异常详情，防凭据值/端点泄漏）。

纪律面：

- ``main(argv=None, *, env=None) -> int`` 纯函数：``env`` = 环境视图
  （缺省 = ``os.environ``），主流程自身的存在性检查只读该视图；凭据值永不
  打印（只引用变量名）；零 subprocess、零真实网络替身（真实后端调用即
  本脚本唯一的外部面，调用由部署配置驱动）。
- 导入纪律 = P6 口径（SOT L123 D-P6-13）：stdlib + 冻结 core/content +
  P6 冻结模块；httpx 不直接 import（经冻结后端模块消费）。
- 12 名扫描口径：本文件全部字符串字面量（含 docstring）0 命中
  （K8 27 文件域成员，SOT §3.12）。
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from typing import Final

from src.engine_v2.content.schemas import InferenceCapabilityProfile
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.trace import LLM_CALL_PAYLOAD_KEYS
from src.engine_v2.llm.adapter import (
    HttpxInferenceBackend,
    InferenceRequest,
    WireMessage,
)
from src.engine_v2.llm.deployment import (
    DEPLOYMENT_ENV_POINTER,
    load_deployment,
)
from src.engine_v2.llm.router import resolve_capability
from src.engine_v2.prompts.assembler import CharDivisorTokenEstimator

EXIT_OK: Final[int] = 0
EXIT_NO_DEPLOYMENT: Final[int] = 3
EXIT_ERROR: Final[int] = 4

#: 冒烟能力位（与部署夹具/门禁场景同名的主能力位）。
_SMOKE_CAPABILITY: Final[str] = "major_character"
_SMOKE_ROLE: Final[str] = "smoke"
_SMOKE_SYSTEM_TEXT: Final[str] = (
    "这是一次冒烟调用。请只输出一个合法 JSON 对象，"
    "键 action_id 取 null，不要输出任何其他文本。"
)


def _guidance(message: str) -> str:
    return f"smoke: {message}"


def _resolve_deployment_path(
    argv: Sequence[str] | None, env: Mapping[str, str]
) -> str | None:
    """部署路径解析（优先级钉死）：显式参数 > env 指针 > None。"""
    if argv and len(argv) > 1 and str(argv[1]).strip():
        return str(argv[1])
    pointer = env.get(DEPLOYMENT_ENV_POINTER)
    if pointer is not None and pointer.strip():
        return pointer
    return None


def _requirement() -> InferenceCapabilityProfile:
    return InferenceCapabilityProfile(
        id="smoke",
        capability=_SMOKE_CAPABILITY,
        min_tier=0,
        ideal_tier=0,
    )


def main(argv: Sequence[str] | None = None, *, env: Mapping[str, str] | None = None) -> int:
    """冒烟主流程（纯函数；env = 环境视图，缺省 os.environ）。

    返回退出码（0/3/4，见模块 docstring）；所有引导/结果面向 stdout。
    """
    view: Mapping[str, str] = os.environ if env is None else env

    def _fail(code: int, message: str) -> int:
        print(_guidance(message))
        return code

    try:
        path = _resolve_deployment_path(argv, view)
        if path is None:
            return _fail(
                EXIT_NO_DEPLOYMENT,
                f"未找到部署配置。用法: llm_smoke.py <deployment.yaml>"
                f"（或设置 env 指针 {DEPLOYMENT_ENV_POINTER}）。",
            )

        loaded = load_deployment(path)
        if loaded.profile is None or loaded.diagnostics:
            codes = ",".join(d.code for d in loaded.diagnostics) or "unknown"
            return _fail(EXIT_NO_DEPLOYMENT, f"部署配置加载失败（{codes}）。")

        router = resolve_capability(loaded.profile, _requirement())
        if router.resolved is None:
            codes = ",".join(d.code for d in router.diagnostics) or "unknown"
            return _fail(EXIT_NO_DEPLOYMENT, f"能力位未解析（{codes}）。")
        resolved = router.resolved

        if resolved.api_key_env is not None:
            name = resolved.api_key_env
            if view.get(name) is None:
                return _fail(
                    EXIT_NO_DEPLOYMENT,
                    f"缺少凭据 env 变量 {name}（请设置后重试；值不会被打印）。",
                )

        estimator = CharDivisorTokenEstimator()
        system_text = _SMOKE_SYSTEM_TEXT
        request = InferenceRequest(
            messages=(WireMessage(role="system", content=system_text),),
            model=resolved.model_id,
            base_url=resolved.base_url,
            api_key_env=resolved.api_key_env,
            temperature=resolved.temperature,
            max_tokens=None,
            timeout_seconds=resolved.timeout_seconds,
            logical_role=_SMOKE_ROLE,
            profile=_SMOKE_ROLE,
            base_revision=Revision(0),
            prompt_metadata_ref="prompt://smoke:0:0",
        )
        response = HttpxInferenceBackend().generate(request)

        payload: dict[str, object] = {
            "logical_role": _SMOKE_ROLE,
            "profile": _SMOKE_ROLE,
            "resolved_model": resolved.model_id,
            "input_token_estimate": estimator.estimate(system_text),
            "prompt_metadata_ref": "prompt://smoke:0:0",
            "output_ref": "output://smoke:0:0",
            "latency_ms": response.latency_ms,
            "parse_retry": 0,
            "base_revision": 0,
        }
        # 机械自检：键集 == core trace 封闭 9 键（#19 口径）。
        assert set(payload) == LLM_CALL_PAYLOAD_KEYS, "冒烟 payload 键集必须封闭"
        print(json.dumps(payload, sort_keys=True, ensure_ascii=False))
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001 - 冒烟出口面：只报类名，防泄漏
        print(_guidance(f"运行期异常 {type(exc).__name__}"))
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
