"""P10 presentation 层 image 侧契约：RenderIntent / 图像过期策略（T03；
SOT §3.3；导出 6 名）。

来源 = Spec §32.2（L1698–1713，RenderIntent 8 字段建议面——本 SOT 逐字
采纳为规范）+ §32.3（L1715–1732，图片结果必带 scene_id +
view_revision；过期三策略 display/discard/archive 由 presentation
policy 决定）；G10-1 核心面。

纪律（P10-INV-2/10，D6，K8）：apply_image_result = 纯函数（零
wall-clock / 零随机；同输入恒同输出）；槽恒随当前 view（槽
view_revision 绝不等于过期 artifact 的旧值——G10-1「不错误覆盖」的槽
面表达）；bytes 不入槽（JSON-clean，P10-INV-10；字节存会话层
current_image，W4 面）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, TypedDict

from src.engine_v2.presentation.view import SceneView

__all__ = [
    "RENDER_INTENT_SCHEMA_VERSION",
    "ImageStalePolicy",
    "RenderIntent",
    "ImageArtifact",
    "ImageSlot",
    "apply_image_result",
]

#: RenderIntent schema 面值（SOT §3.3）。
RENDER_INTENT_SCHEMA_VERSION: Final[int] = 1

#: media_type 闭集 = 单值（SOT §3.3 ImageArtifact 行；Leader 终审 Q8
#: 裁定：x- 前缀 = RFC 6838 实验类型惯例，与伪图像参考面语义一致，
#: 零新依赖）。
IMAGE_MEDIA_TYPES: Final[frozenset[str]] = frozenset({"image/x-ppm"})


class ImageStalePolicy(str, Enum):
    """图像过期三策略（Spec §32.3 L1722–1726 逐字；P1 先例
    ``class Xxx(str, Enum)``）。

    默认策略 = DISCARD（D-P10-11 安全默认：过期 artifact 零覆盖、零
    槽面推进）。
    """

    DISPLAY = "display"
    DISCARD = "discard"
    ARCHIVE = "archive"


@dataclass(frozen=True)
class RenderIntent:
    """渲染意图（SOT §3.3；8 字段 = Spec §32.2 L1698–1713 逐字序；
    JSON-clean）。

    - subjects = view.actors 投影（Narrator 与 VisualDirector 的
      subjects 共同源，SOT §3.1 actors 键）；
    - camera = 确定性缺省面（模板路径 ``{"type": "fixed",
      "framing": "medium"}``；推理路径可覆盖——脚本化，SOT §3.4）；
    - continuity_refs = 历史意图尾 ≤3 条的 scene_id 序（T08 连续性面，
      SOT §3.4）。
    """

    scene_id: str
    view_revision: int
    subjects: tuple[dict, ...]
    environment: dict
    camera: dict
    mood: str
    continuity_refs: tuple[str, ...]
    style_refs: tuple[str, ...]

    def to_dict(self) -> dict:
        """JSON-clean dict 投影（P10-INV-10；新建容器，零别名；
        A9/t5 钉）。"""
        return {
            "scene_id": self.scene_id,
            "view_revision": self.view_revision,
            "subjects": [dict(subject) for subject in self.subjects],
            "environment": dict(self.environment),
            "camera": dict(self.camera),
            "mood": self.mood,
            "continuity_refs": list(self.continuity_refs),
            "style_refs": list(self.style_refs),
        }


@dataclass(frozen=True)
class ImageArtifact:
    """图像 artifact（SOT §3.3；Spec §32.3 必带标签面）。

    ``scene_id`` + ``view_revision`` = 请求刻 intent 面值（P10-INV-2
    载体：到达刻由 :func:`apply_image_result` 新鲜判定）；``payload``
    = 图像字节（不入槽，P10-INV-10）。
    """

    artifact_id: str
    scene_id: str
    view_revision: int
    media_type: str
    payload: bytes
    continuity_refs: tuple[str, ...]
    style_refs: tuple[str, ...]


class ImageSlot(TypedDict):
    """SceneView.image_slot 形状（SOT §3.3；7 键，JSON-clean）。

    ``view_revision`` = 显示时当前 view 面值（槽恒随当前 view，**绝不
    等于过期 artifact 的旧值**——G10-1「不错误覆盖」的槽面表达）；
    bytes 不入槽（P10-INV-10；字节存会话层 current_image，W4 面）。
    回投 = 会话层 apply_image_result 后单点（W4 实现时 docstring 钉
    「回投 = 槽唯一写入点」，Leader 终审 Q3 裁定）。
    """

    artifact_id: str
    scene_id: str
    view_revision: int
    stale: bool
    archived: bool
    media_type: str
    byte_length: int


def apply_image_result(
    current_slot: ImageSlot | None,
    artifact: ImageArtifact,
    current_view: SceneView,
    *,
    policy: ImageStalePolicy = ImageStalePolicy.DISCARD,
) -> ImageSlot | None:
    """纯函数：图像 artifact 到达 → 槽更新（SOT §3.3；G10-1 核心面；
    P10-INV-2）。

    新鲜判定（逐字）= ``artifact.view_revision ==
    current_view["view_revision"] and artifact.scene_id ==
    current_view["scene_id"]``。

    - 新鲜 → 新槽（stale=False, archived=False, view_revision=当前）；
    - 过期（core ``is_stale``（core/revision.py:78，base < current）
      或 scene 不符）→ 按 policy 三面：
      DISCARD（默认，D-P10-11）= 返回 current_slot 原样（无槽则
      None，零覆盖）；
      DISPLAY = 新槽（stale=True, archived=False, view_revision=
      当前）；
      ARCHIVE = 新槽（stale=True, archived=True, view_revision=
      当前）。
    - W4 预告面（本波 docstring 钉）：``artifact.view_revision >
      current`` = 会话流单调性下不可达分支（P10-INV-2：view_revision
      单调非减投影；artifact 请求刻 ≤ 到达刻）；机械落点按过期通面
      处置（槽 view_revision 恒随当前 view，零以未来刻覆盖）。
    """
    current_revision = int(current_view["view_revision"])
    current_scene_id = current_view["scene_id"]
    stale = not (
        artifact.view_revision == current_revision
        and artifact.scene_id == current_scene_id
    )
    if stale and policy is ImageStalePolicy.DISCARD:
        return current_slot
    archived = stale and policy is ImageStalePolicy.ARCHIVE
    return ImageSlot(
        artifact_id=artifact.artifact_id,
        scene_id=artifact.scene_id,
        view_revision=current_revision,
        stale=stale,
        archived=archived,
        media_type=artifact.media_type,
        byte_length=len(artifact.payload),
    )
