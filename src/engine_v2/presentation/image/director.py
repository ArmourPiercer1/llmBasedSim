"""P10 presentation 层 image 侧导演：VisualDirector（T03；SOT §3.4；
导出 3 名）。

来源 = Spec §32.1（L1680–1696，VisualDirector 支）+ §32.2（L1698–
1713，意图契约消费）+ §45 主流程（L2257–2268，VisualDirector →
Image）；输入 = SceneView 唯一（P10-INV-3，G10-2）；推理面 = 注入
脚本（K5 / P10-INV-6）。

纪律（P10-INV-3/6/10，D6，K8）：签名输入 = SceneView 唯一（零
RenderIntent 之外的契约输入 / 零 prose 参数——SC-P10-2 机械面）；
image/ 文件 import 零 ``presentation.text.*``（A2 AST，SOT §3.0 特例
钉）；零 wall-clock / 零随机（D6）；RenderIntent JSON-clean
（P10-INV-10）；推理路径脚本命中 JSON → 8 字段校验（违例 →
PresentationError（code="intent_schema_invalid"），SOT §3.4）。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Final

from src.engine_v2.core.revision import Revision
from src.engine_v2.llm.adapter import (
    InferenceBackend,
    InferenceRequest,
    WireMessage,
)
from src.engine_v2.presentation.image.contract import RenderIntent
from src.engine_v2.presentation.view import PresentationError, SceneView

__all__ = [
    "VISUAL_DIRECTOR_LOGICAL_ROLE",
    "VisualDirector",
    "derive_render_intent",
]

#: 脚本键 logical_role 面值（K8-safe 名；SOT §3.4）。
VISUAL_DIRECTOR_LOGICAL_ROLE: Final[str] = "visual_director"

#: RenderIntent 8 字段闭集（Spec §32.2 逐字；推理路径 JSON 校验面——
#: 键面闭集校验，缺键 / 多键即违例）。
_INTENT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "scene_id",
        "view_revision",
        "subjects",
        "environment",
        "camera",
        "mood",
        "continuity_refs",
        "style_refs",
    }
)

#: 确定性缺省 camera 面（SOT §3.3 RenderIntent 行：模板路径钉值）。
_DEFAULT_CAMERA: Final[dict[str, str]] = {"type": "fixed", "framing": "medium"}

#: 确定性缺省 mood（末帧 frame.mood 缺失 / 空串；SOT §3.4 模板路径）。
_DEFAULT_MOOD: Final[str] = "calm"

#: continuity_refs 窗口 = 尾 ≤3 条（T08 连续性面；SOT §3.4）。
_CONTINUITY_WINDOW: Final[int] = 3

#: system 消息基础面（确定性）。
_SYSTEM_PROMPT: Final[str] = (
    "基于 SceneView 结构化投影输出本场景 RenderIntent 8 字段 JSON；"
    "只输出单个 JSON 对象，零额外说明。"
)


def _intent_error(message: str) -> PresentationError:
    """PresentationError（code="intent_schema_invalid"）构造（SOT
    §3.4 推理路径违例错误族）。"""
    return PresentationError(message, code="intent_schema_invalid")


def _continuity_refs(continuity: Sequence[RenderIntent]) -> tuple[str, ...]:
    """continuity 尾 ≤3 条的 scene_id 序（T08 连续性面；SOT §3.4）。"""
    window = tuple(continuity)[-_CONTINUITY_WINDOW :]
    return tuple(intent.scene_id for intent in window)


def _template_mood(view: SceneView) -> str:
    """mood = 末帧 frame.mood 非空取之，否则 :data:`_DEFAULT_MOOD`
    （SOT §3.4 模板路径；帧面 = view.narrative.frames）。"""
    frames = view["narrative"]["frames"]
    if frames:
        last = frames[-1]
        if isinstance(last, dict):
            frame_mood = last.get("mood")
            if isinstance(frame_mood, str) and frame_mood:
                return frame_mood
    return _DEFAULT_MOOD


def _build_request(view: SceneView) -> InferenceRequest:
    """推理请求面（确定性；字段序 = P6 冻结面 InferenceRequest:98
    11 字段逐字；SOT §2.3 模型中性面注记）。"""
    view_revision = int(view["view_revision"])
    user_content = json.dumps(dict(view), ensure_ascii=False, sort_keys=True)
    return InferenceRequest(
        messages=(
            WireMessage(role="system", content=_SYSTEM_PROMPT),
            WireMessage(role="user", content=user_content),
        ),
        model="",
        base_url="",
        api_key_env=None,
        temperature=0.0,
        max_tokens=None,
        timeout_seconds=0.0,
        logical_role=VISUAL_DIRECTOR_LOGICAL_ROLE,
        profile=VISUAL_DIRECTOR_LOGICAL_ROLE,
        base_revision=Revision(view_revision),
        prompt_metadata_ref=(
            f"prompt://visual_director:{view['tick']}:{view_revision}"
        ),
    )


class VisualDirector:
    """VisualDirector（SOT §3.4；显式注入，零模块级实例）。

    - 模板路径（``backend=None``）：纯投影——subjects / environment
      自 view；mood = 末帧 frame.mood 非空取之，否则 "calm"；camera =
      :data:`_DEFAULT_CAMERA`；continuity_refs = ``continuity`` 尾 ≤3
      条的 scene_id 序（T08 连续性面）；style_refs = constructor 注入
      面；
    - 推理路径（``backend`` 非 None）：脚本命中 JSON → 8 字段校验
      （顶层非对象 / 键面 ≠ 8 字段闭集 / 字段类型违例 →
      PresentationError（code="intent_schema_invalid"）；8 字段全部
      取脚本 JSON 值——SOT §3.4「8 字段落位」）；
    - 推理请求面（确定性）：logical_role / profile =
      :data:`VISUAL_DIRECTOR_LOGICAL_ROLE` 同串；base_revision =
      ``Revision(view["view_revision"])``；prompt_metadata_ref =
      ``prompt://visual_director:{tick}:{base_revision}``（P6 §3.6
      确定性句柄格式）；model / 端点 / 凭据环境名 = 中性面（零部署
      解析，SOT §2.3 注记）。
    """

    def __init__(
        self,
        *,
        backend: InferenceBackend | None = None,
        style_refs: tuple[str, ...] = (),
    ) -> None:
        self._backend = backend
        self._style_refs = tuple(style_refs)

    def plan(
        self,
        view: SceneView,
        *,
        continuity: Sequence[RenderIntent] = (),
    ) -> RenderIntent:
        """SceneView → RenderIntent（纯函数；同输入恒同输出，D6 双跑）。"""
        if self._backend is None:
            return _template_intent(view, self._style_refs, continuity)
        return _scripted_intent(view, self._backend)


def _template_intent(
    view: SceneView,
    style_refs: tuple[str, ...],
    continuity: Sequence[RenderIntent],
) -> RenderIntent:
    """模板路径 = 纯投影（SOT §3.4；零推理调用，K5）。"""
    return RenderIntent(
        scene_id=view["scene_id"],
        view_revision=int(view["view_revision"]),
        subjects=tuple(dict(actor) for actor in view["actors"]),
        environment=dict(view["environment"]),
        camera=dict(_DEFAULT_CAMERA),
        mood=_template_mood(view),
        continuity_refs=_continuity_refs(continuity),
        style_refs=tuple(style_refs),
    )


def _validate_intent_fields(raw: dict) -> RenderIntent:
    """8 字段逐字段类型校验 + RenderIntent 构造（SOT §3.4；违例 →
    PresentationError（code="intent_schema_invalid"）；json.loads 产物
    结构性 JSON-clean，P10-INV-10）。"""
    scene_id = raw["scene_id"]
    view_revision = raw["view_revision"]
    subjects = raw["subjects"]
    environment = raw["environment"]
    camera = raw["camera"]
    mood = raw["mood"]
    continuity_refs = raw["continuity_refs"]
    style_refs = raw["style_refs"]
    if not isinstance(scene_id, str):
        raise _intent_error("scene_id 必须为 str")
    if isinstance(view_revision, bool) or not isinstance(view_revision, int):
        raise _intent_error("view_revision 必须为 int（排除 bool）")
    if not isinstance(subjects, list) or not all(
        isinstance(item, dict) for item in subjects
    ):
        raise _intent_error("subjects 必须为对象列表")
    if not isinstance(environment, dict):
        raise _intent_error("environment 必须为对象")
    if not isinstance(camera, dict):
        raise _intent_error("camera 必须为对象")
    if not isinstance(mood, str):
        raise _intent_error("mood 必须为 str")
    if not isinstance(continuity_refs, list) or not all(
        isinstance(item, str) for item in continuity_refs
    ):
        raise _intent_error("continuity_refs 必须为 str 列表")
    if not isinstance(style_refs, list) or not all(
        isinstance(item, str) for item in style_refs
    ):
        raise _intent_error("style_refs 必须为 str 列表")
    return RenderIntent(
        scene_id=scene_id,
        view_revision=view_revision,
        subjects=tuple(dict(item) for item in subjects),
        environment=dict(environment),
        camera=dict(camera),
        mood=mood,
        continuity_refs=tuple(continuity_refs),
        style_refs=tuple(style_refs),
    )


def _scripted_intent(view: SceneView, backend: InferenceBackend) -> RenderIntent:
    """推理路径：脚本命中 JSON → 8 字段校验 → RenderIntent（SOT §3.4；
    坏 JSON / 键面违例 / 类型违例 → PresentationError
    （code="intent_schema_invalid"））。"""
    response = backend.generate(_build_request(view))
    try:
        raw: object = json.loads(response.text)
    except ValueError as exc:
        raise _intent_error(f"RenderIntent 脚本 JSON 解析失败：{exc}") from exc
    if not isinstance(raw, dict):
        raise _intent_error("RenderIntent 脚本 JSON 顶层必须为对象")
    if set(raw) != _INTENT_FIELDS:
        raise _intent_error(
            "RenderIntent 脚本 JSON 键面必须等于 8 字段闭集（缺键/多键）"
        )
    return _validate_intent_fields(raw)


def derive_render_intent(
    view: SceneView,
    *,
    backend: InferenceBackend | None = None,
    style_refs: tuple[str, ...] = (),
    continuity: Sequence[RenderIntent] = (),
) -> RenderIntent:
    """模块函数入口（P9 平铺先例）：构造 VisualDirector 委托（SOT
    §3.4）。"""
    return VisualDirector(backend=backend, style_refs=style_refs).plan(
        view, continuity=continuity
    )
