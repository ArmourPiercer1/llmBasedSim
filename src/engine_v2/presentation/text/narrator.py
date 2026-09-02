"""P10 presentation 层 text 侧 backend：Narrator（T02；SOT §3.2；导出 5 名）。

来源 = Spec §32.1（L1680–1696，View/Scene Context → Narrator +
VisualDirector 平行结构，Narrator 支）+ §45 主流程（L2257–2268，
Narrator → Text）；输入 = SceneView 唯一（P10-INV-3，G10-2）；润色
推理 = 可选注入面（K5 / P10-INV-6）；模板文风 = v1
``narrative_stylize`` 思想参照（src/graph/game_graph.py:769，43.1-10，
文本参照零 import）；P9 narration 已承接 text 侧派生——P10 为
presentation 层 backend，与 P9 模块零耦合（narrative 5 键 = P10 自
派生形状复用，零 ``engine_v2.modules`` import，D-P10-01，同
``presentation/view.py`` narrative 面纪律）。

纪律（P10-INV-1/3/6/10，D6，K8）：签名输入 = SceneView 唯一（零
RenderIntent / 零 prose 参数——SC-P10-2 机械面）；text/ 文件 import
零 ``presentation.image.*``（A2 AST，SOT §3.0 特例钉）；backend 注入
点唯一 = constructor（零模块级实例，P10-INV-4 同族）；template 路径
零推理调用（K5，A8/t1 钉）；纯函数或显式注入状态，零 wall-clock /
零随机（D6）；TextArtifact JSON-clean（P10-INV-10）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final

from src.engine_v2.core.revision import Revision
from src.engine_v2.llm.adapter import (
    InferenceBackend,
    InferenceRequest,
    WireMessage,
)
from src.engine_v2.presentation.view import SceneView

__all__ = [
    "NARRATOR_LOGICAL_ROLE",
    "TEXT_SOURCES",
    "TextArtifact",
    "NarratorPresentationBackend",
    "narrate_scene",
]

#: FakeInferenceBackend 脚本键 logical_role 面值（K8-safe 名；SOT §3.2）。
NARRATOR_LOGICAL_ROLE: Final[str] = "narrator"

#: artifact.source 闭集（SOT §3.2 逐字钉面值：template = 模板路径；
#: 第 2 名 = 脚本命中推理路径标签〔类别标签，非供应商名〕）。
TEXT_SOURCES: Final[tuple[str, ...]] = ("template", "llm")

#: 模板拼接分隔符（SOT §3.2「scene_text + frames 拼接」的确定性钉值；
#: 零帧 → 纯 scene_text，无尾随分隔符）。
_TEMPLATE_FRAME_SEPARATOR: Final[str] = "。"

#: system 消息基础面（确定性；style 两键追加其尾，见 _system_content）。
_SYSTEM_PROMPT: Final[str] = (
    "基于 SceneView 结构化投影渲染本场景叙事文本；只输出纯文本，零额外说明。"
)

#: style 消费键闭集（v1 narrative_style 语义参照，
#: src/graph/game_graph.py:774–776；仅 str 非空值消费）。
_STYLE_KEYS: Final[tuple[str, ...]] = ("style_description", "style_example")


@dataclass(frozen=True)
class TextArtifact:
    """文本产物（SOT §3.2；5 字段逐字序；JSON-clean）。

    - ``view_revision`` / ``scene_id`` = 派生时 view 面值（Spec §32.3
      必带标签纪律的 text 侧对应；P10-INV-2 载体）；
    - ``source`` ∈ :data:`TEXT_SOURCES`；
    - ``frames`` = view.narrative.frames 投影（复制容器，零别名）。
    """

    text: str
    frames: tuple[dict, ...]
    view_revision: int
    scene_id: str
    source: str

    def to_dict(self) -> dict:
        """JSON-clean dict 投影（P10-INV-10；新建容器，零别名）。"""
        return {
            "text": self.text,
            "frames": [dict(frame) for frame in self.frames],
            "view_revision": self.view_revision,
            "scene_id": self.scene_id,
            "source": self.source,
        }


class NarratorPresentationBackend:
    """Narrator presentation backend（SOT §3.2；显式注入，零模块级实例）。

    - template 路径（``backend=None``）：确定性模板 = scene_text +
      frames 文本拼接（分隔符 = :data:`_TEMPLATE_FRAME_SEPARATOR`），
      零推理调用（K5；A8/t1 钉）；
    - 推理路径（``backend`` 非 None）：脚本命中 → 润色文本
      （source = :data:`TEXT_SOURCES`[1]）；空响应文本 → template 面
      回落（零异常逃逸，SOT §3.2）。注：``FakeInferenceBackend`` 脚本
      未命中落 default_text（非空 → 按命中输出原样消费——fake 参考面
      语义；测试侧脚本钉保证命中面，SOT §6.4）；
    - ``style`` 消费 = ``style_description`` / ``style_example`` 两键
      可选 str 值（v1 narrative_style 语义参照，
      src/graph/game_graph.py:774–776），只影响推理路径 system 消息；
      template 路径零影响（D6 同输入恒同输出）；
    - 推理请求面（确定性）：logical_role / profile =
      :data:`NARRATOR_LOGICAL_ROLE` 同串；base_revision =
      ``Revision(view["view_revision"])``；prompt_metadata_ref =
      ``prompt://narrator:{tick}:{base_revision}``（P6 §3.6 确定性
      句柄格式）；model / 端点 / 凭据环境名 = 中性面（零部署解析，
      SOT §2.3 注记）。
    """

    def __init__(
        self,
        *,
        backend: InferenceBackend | None = None,
        style: dict | None = None,
    ) -> None:
        self._backend = backend
        self._style = dict(style) if style is not None else {}

    def render(self, view: SceneView) -> TextArtifact:
        """SceneView → TextArtifact（纯函数；同输入恒同输出，D6 双跑）。"""
        view_revision = int(view["view_revision"])
        frames = tuple(dict(frame) for frame in view["narrative"]["frames"])
        if self._backend is None:
            return TextArtifact(
                text=_template_text(view),
                frames=frames,
                view_revision=view_revision,
                scene_id=view["scene_id"],
                source=TEXT_SOURCES[0],
            )
        response = self._backend.generate(_build_request(view, self._style))
        polished = response.text.strip()
        if polished:
            text = polished
            source = TEXT_SOURCES[1]
        else:
            text = _template_text(view)
            source = TEXT_SOURCES[0]
        return TextArtifact(
            text=text,
            frames=frames,
            view_revision=view_revision,
            scene_id=view["scene_id"],
            source=source,
        )


def _template_text(view: SceneView) -> str:
    """确定性模板（SOT §3.2）：scene_text + frames 文本拼接（分隔符 =
    "。"；frame 非 dict / 无 text 键 / 空串帧跳过；零帧 → 纯
    scene_text）。"""
    parts: list[str] = [view["narrative"]["scene_text"]]
    for frame in view["narrative"]["frames"]:
        if isinstance(frame, dict):
            text = frame.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
    return _TEMPLATE_FRAME_SEPARATOR.join(parts)


def _system_content(style: dict) -> str:
    """system 消息内容（确定性拼接；style 两键面消费，SOT §3.2
    constructor style 语义钉）。"""
    parts: list[str] = [_SYSTEM_PROMPT]
    for key in _STYLE_KEYS:
        value = style.get(key)
        if isinstance(value, str) and value:
            parts.append(value)
    return " ".join(parts)


def _build_request(view: SceneView, style: dict) -> InferenceRequest:
    """推理请求面（确定性；字段序 = P6 冻结面 InferenceRequest:98
    11 字段逐字；SOT §2.3 模型中性面注记）。"""
    view_revision = int(view["view_revision"])
    user_content = json.dumps(dict(view), ensure_ascii=False, sort_keys=True)
    return InferenceRequest(
        messages=(
            WireMessage(role="system", content=_system_content(style)),
            WireMessage(role="user", content=user_content),
        ),
        model="",
        base_url="",
        api_key_env=None,
        temperature=0.0,
        max_tokens=None,
        timeout_seconds=0.0,
        logical_role=NARRATOR_LOGICAL_ROLE,
        profile=NARRATOR_LOGICAL_ROLE,
        base_revision=Revision(view_revision),
        prompt_metadata_ref=(
            f"prompt://narrator:{view['tick']}:{view_revision}"
        ),
    )


def narrate_scene(
    view: SceneView,
    *,
    backend: InferenceBackend | None = None,
    style: dict | None = None,
) -> TextArtifact:
    """模块函数入口（P9 平铺先例）：构造 NarratorPresentationBackend
    委托（SOT §3.2）。"""
    return NarratorPresentationBackend(backend=backend, style=style).render(
        view
    )
