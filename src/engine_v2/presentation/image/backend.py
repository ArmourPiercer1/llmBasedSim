"""P10 presentation 层 image 侧 backend：参考 / 伪实现（T04；SOT
§3.5；导出 5 名）。

来源 = Spec §32.2–32.3（backend 消费 RenderIntent、产出携标签
artifact）；零真实图像依赖（S4 预裁决，D-P10-02）——参考 backend =
stdlib 确定性伪图像（PPM P3 纯文本面）+ 测试 fake；真实生成 = P11+。

纪律（P10-INV-6/10，D4/D6，K8）：``render_intent_to_ppm`` = f(intent)
纯函数（同 intent 同字节，A10/t2 双跑；scene_id 参与全部颜色派生
——t3 错场敏感面）；PPM P3 头部钉 ``"P3\\n{w} {h}\\n255\\n"`` + w×h×3
十进制分量（A10/t1）；artifact 标签 = intent 面值（Spec §32.3 必带
scene_id + view_revision）；media_type 闭集单值（contract
``IMAGE_MEDIA_TYPES`` 消费面，W2 落码零修改）；零第三方 import（face
t4 钉，零图像库）；零 wall-clock / 零随机 / 零 uuid4（artifact_id =
载荷哈希派生）；width / height ≤ 0 → ValueError（SOT §3.5 钉；bool
拒绝 = core GridSpace 同形）；12 名闭集零命中。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Protocol

from src.engine_v2.presentation.image.contract import (
    IMAGE_MEDIA_TYPES,
    ImageArtifact,
    RenderIntent,
)
from src.engine_v2.presentation.view import PresentationError

__all__ = [
    "IMAGE_BACKEND_KINDS",
    "ImageBackend",
    "DeterministicImageBackend",
    "FakeImageBackend",
    "render_intent_to_ppm",
]

IMAGE_BACKEND_KINDS: Final[tuple[str, ...]] = ("deterministic", "fake")

_DEFAULT_WIDTH: Final[int] = 64
_DEFAULT_HEIGHT: Final[int] = 32

_PPM_MAGIC: Final[str] = "P3"
_PPM_MAXVAL: Final[int] = 255
_ARTIFACT_ID_PREFIX: Final[str] = "art:"
_ARTIFACT_ID_DIGEST_LEN: Final[int] = 16


class ImageBackend(Protocol):
    """backend 契约（SOT §3.5；注入面；零全局实例）。

    同步面；「异步过期」= 会话层在 artifact 到达刻对当前 view 调
    ``apply_image_result``（§3.3）——backend 自身无时钟状态。
    """

    def render(self, intent: RenderIntent) -> ImageArtifact: ...


def _media_type() -> str:
    """media_type 单值面（SOT §3.3 ``IMAGE_MEDIA_TYPES`` 闭集消费；
    sorted 首值 = 确定性取单值，零面值重复落码）。"""
    return sorted(IMAGE_MEDIA_TYPES)[0]


def _backend_error(message: str) -> PresentationError:
    """PresentationError（code="image_backend_error"）构造（SOT §3.1
    code 闭集成员；intent 载荷面违例错误族）。"""
    return PresentationError(message, code="image_backend_error")


def _seed_color(seed: str) -> tuple[int, int, int]:
    """确定性哈希投影 → 24-bit 颜色（D6：同 seed 同颜色；零随机）。"""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return digest[0], digest[1], digest[2]


def _environment_seed(intent: RenderIntent) -> str:
    """environment → 确定性序列化 seed（JSON sort_keys）；非
    JSON-clean → 零异常逃逸，:func:`_backend_error`（AD-P10-2 面）。
    """
    try:
        return json.dumps(intent.environment, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise _backend_error(f"environment 必须 JSON-clean：{exc}") from exc


def _subject_seed(intent: RenderIntent, index: int, subject: Any) -> str:
    """subject → seed（SOT §3.5「每 subject 一矩形 = subject id 哈希
    映射」）；id 缺失 / 非 str / 空 → :func:`_backend_error`（fail-
    loud，零静默回落）。"""
    subject_id = subject.get("id") if isinstance(subject, dict) else None
    if not isinstance(subject_id, str) or not subject_id:
        raise _backend_error(f"subjects[{index}] 必须为携非空 str id 的对象")
    return f"{intent.scene_id}|subject|{subject_id}"


def _ppm_bytes(intent: RenderIntent, width: int, height: int) -> bytes:
    """PPM P3 字节构造（纯函数体；头部 + w×h×3 十进制分量）。

    背景色 = scene_id + environment 哈希映射；每 subject 一矩形 =
    scene_id + subject id 哈希映射（subjects 均分宽度竖带，纵向 1/4
    起 3/4 止）；mood = 边框色（外圈 1 像素）——scene_id 参与全部
    颜色派生（t2 双跑 / t3 错场敏感面）。
    """
    background = _seed_color(
        f"{intent.scene_id}|background|{_environment_seed(intent)}"
    )
    pixels: list[tuple[int, int, int]] = [background] * (width * height)
    count = len(intent.subjects)
    if count:
        top = height // 4
        bottom = height - height // 4
        for index, subject in enumerate(intent.subjects):
            color = _seed_color(_subject_seed(intent, index, subject))
            left = index * width // count
            right = (index + 1) * width // count
            for y in range(top, bottom):
                for x in range(left, right):
                    pixels[y * width + x] = color
    border = _seed_color(f"{intent.scene_id}|border|{intent.mood}")
    for x in range(width):
        pixels[x] = border
        pixels[(height - 1) * width + x] = border
    for y in range(height):
        pixels[y * width] = border
        pixels[y * width + width - 1] = border
    header = f"{_PPM_MAGIC}\n{width} {height}\n{_PPM_MAXVAL}\n"
    rows = [
        " ".join(
            str(channel)
            for pixel in pixels[y * width : (y + 1) * width]
            for channel in pixel
        )
        for y in range(height)
    ]
    return (header + "\n".join(rows)).encode("ascii")


def render_intent_to_ppm(
    intent: RenderIntent, *, width: int = 64, height: int = 32
) -> bytes:
    """纯函数：RenderIntent → PPM P3 字节（SOT §3.5；D-P10-02；
    DeterministicImageBackend 核心投影，独立导出供 face / AD 对抗面
    直接钉）。

    - 头部钉 = ``"P3\\n{w} {h}\\n255\\n"``（缺省 64×32；A10/t1）；体 =
      w×h×3 十进制分量（逐像素 r g b 空格分隔，行换行连接）；
    - 背景 / subject 矩形 / mood 边框 = 确定性哈希投影（docstring 详
      面）；
    - width / height ≤ 0 → ``ValueError``（SOT §3.5 钉；bool / 非
      int 拒绝 = core GridSpace 同形）；
    - bytes = f(intent)（同 intent 同字节，D6）。
    """
    for name, value in (("width", width), ("height", height)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} 必须为 int（bool 拒绝）：{value!r}")
        if value <= 0:
            raise ValueError(f"{name} 必须 > 0：{value!r}")
    return _ppm_bytes(intent, width, height)


def _build_artifact(intent: RenderIntent, payload: bytes) -> ImageArtifact:
    """携标签 artifact（SOT §3.3 必带标签面）：artifact_id = 载荷哈希
    确定性派生（零 uuid4）；标签 = intent 面值回显（scene_id /
    view_revision / continuity_refs / style_refs）。"""
    digest = hashlib.sha256(payload).hexdigest()[:_ARTIFACT_ID_DIGEST_LEN]
    return ImageArtifact(
        artifact_id=_ARTIFACT_ID_PREFIX + digest,
        scene_id=intent.scene_id,
        view_revision=intent.view_revision,
        media_type=_media_type(),
        payload=payload,
        continuity_refs=tuple(intent.continuity_refs),
        style_refs=tuple(intent.style_refs),
    )


class DeterministicImageBackend:
    """stdlib 伪图像参考面（SOT §3.5；D-P10-02；A10）。

    PPM P3（头部钉 + 十进制分量）；背景色 = environment 哈希映射、
    每 subject 一矩形 = subject id 哈希映射、mood = 边框色——全部
    确定性哈希投影（D6：同 intent 同字节，A10/t2）；artifact 标签 =
    intent 面值（Spec §32.3）；零第三方 import（face t4 钉，零图像
    库）。构造守卫：width / height ≤ 0 → ``ValueError``（SOT 钉；
    bool 拒绝 = core GridSpace 同形）。
    """

    def __init__(self, *, width: int = 64, height: int = 32) -> None:
        for name, value in (("width", width), ("height", height)):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} 必须为 int（bool 拒绝）：{value!r}")
            if value <= 0:
                raise ValueError(f"{name} 必须 > 0：{value!r}")
        self._width = width
        self._height = height

    def render(self, intent: RenderIntent) -> ImageArtifact:
        """RenderIntent → 携标签 artifact（纯函数；同 intent 同字节）。"""
        payload = render_intent_to_ppm(
            intent, width=self._width, height=self._height
        )
        return _build_artifact(intent, payload)


class FakeImageBackend:
    """测试面（P6 ``FakeInferenceBackend`` 先例对称，SOT §3.5；
    A10/t4）：payload = ``scene_id.encode() + b"\\x00" + str(
    view_revision).encode()``（回显钉）；``intents`` = 只读调用史
    （零像素逻辑）。
    """

    def __init__(self) -> None:
        self._intents: list[RenderIntent] = []

    def render(self, intent: RenderIntent) -> ImageArtifact:
        """回显 artifact（纯函数；同 intent 同 payload；调用史追加）。"""
        self._intents.append(intent)
        payload = (
            intent.scene_id.encode("utf-8")
            + b"\x00"
            + str(intent.view_revision).encode("ascii")
        )
        return _build_artifact(intent, payload)

    @property
    def intents(self) -> tuple[RenderIntent, ...]:
        """只读调用史（提交序；t4 钉面）。"""
        return tuple(self._intents)
