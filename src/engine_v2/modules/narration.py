"""P9 W6 官方模块：narration（T11；SOT §3.14 L834–857；导出 4 名）。

来源 = v1 ``narrative_stylize``（src/graph/game_graph.py:769，43.1-10
narrative renderer 思想保留）；Spec §8.5（L626–638）ViewState MUST NOT
authoritative；Spec §32 text/image 并行——**P9 仅 text 侧**（D-P9-13，
image = P10）。

冻结消费（SOT §2.1/§2.4）：core ``state``（``WorldState``:246）；模块
公共面 ``modules.base``；content ``schemas``（``ScenarioSpec``:448——
``narrative_style`` 字段 v1 ``narrative_style`` 节
（test_empty.yaml:152 起）形状对齐承接）。自足模块（SOT §3.1.2 L492：
narration 自足（纯派生）→ requires = ()）。

模板文本规则（本波样例 = 零 backend，确定性文本模板，此处钉死）：

- ``scene_text`` = ``style.style_description``；``style_example`` 非空
  时追加 ``（例：<style_example>）``；再逐帧追加摘要行
  ``[tick=<frame.tick>] <speaker_id>：<text>``（帧序保持；零帧 →
  摘要行 = ``（无帧）``）；各行以换行连接；
- ``frames`` = 每帧 ``{"tick", "speaker_id", "text"}``，``mood`` 非空
  时追加 ``"mood"`` 键（JSON-clean）；
- ``actors_visible`` = 帧 ``speaker_id`` 去重（首现序，确定性）；
- ``clock`` = ``{"tick": tick}``（逻辑刻唯一时钟面；零 wall-clock）。

纪律（P9-INV-8/D6/K8）：纯派生零反作用（WorldState 只读；view 突变
后 WorldState 零反作用——A5 主面）；本模块零推理调用面导入（润色 =
可选注入 backend 面，本波不实现——SOT §3.14 表行 4 括注）；零
wall-clock / 零随机；12 名闭集零命中。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, TypedDict

from src.engine_v2.core.state import WorldState
from src.engine_v2.modules.base import OFFICIAL_MODULE_VERSION, ModuleIdentity

__all__ = [
    "NarrativeFrame",
    "NarrativeStyle",
    "NarrativeView",
    "render_narrative_view",
]

#: 模块身份（SOT §3.1.2 requires 表 L492：narration 自足（纯派生）→
#: requires = ()）。
IDENTITY: Final[ModuleIdentity] = ModuleIdentity(
    "llmsim-standard-narration", OFFICIAL_MODULE_VERSION, (),
)


@dataclass(frozen=True)
class NarrativeFrame:
    """单帧叙述（SOT §3.14 表行 1；宿主从事件流 / 对话结果投影）。"""

    tick: int
    speaker_id: str
    text: str
    mood: str = ""


@dataclass(frozen=True)
class NarrativeStyle:
    """叙述风格（SOT §3.14 表行 2；v1 ``narrative_style`` 节形状对齐——
    ``ScenarioSpec.narrative_style``（content/schemas.py:448 起）承接）。"""

    style_description: str
    style_example: str = ""


class NarrativeView(TypedDict, total=False):
    """narrative-ready ViewState（SOT §3.14 表行 3；A5 主面）。

    纯 dict（JSON-clean；``json.dumps`` 零失败）；非权威（P9-INV-8：
    修改 view 零反作用于 WorldState）。键集 = tick / scene_text /
    frames / actors_visible / clock（total=False）。
    """

    tick: int
    scene_text: str
    frames: list[dict]
    actors_visible: list[str]
    clock: dict


def render_narrative_view(
    world: WorldState,
    frames: Sequence[NarrativeFrame],
    style: NarrativeStyle,
    tick: int,
) -> NarrativeView:
    """纯派生：WorldState 只读 → view（SOT §3.14 表行 4；A5 主面）。

    模板规则 = 模块 docstring「模板文本规则」钉死。``world`` = 权威
    只读面（派生上下文预留消费面；本波模板仅消费 frames / style /
    tick——零 world 字段读取，非权威性构造性成立）；本函数零世界写、
    零推理调用、零随机（同输入恒同输出）；返回 dict 与 WorldState 零
    别名共享（P9-INV-8：A5 断言修改 view 后世界哈希不变）。
    """
    lines = [style.style_description]
    if style.style_example:
        lines.append(f"（例：{style.style_example}）")
    if frames:
        for frame in frames:
            lines.append(
                f"[tick={frame.tick}] {frame.speaker_id}：{frame.text}"
            )
    else:
        lines.append("（无帧）")

    frame_dicts: list[dict] = []
    visible: list[str] = []
    for frame in frames:
        entry: dict = {
            "tick": frame.tick,
            "speaker_id": frame.speaker_id,
            "text": frame.text,
        }
        if frame.mood:
            entry["mood"] = frame.mood
        frame_dicts.append(entry)
        if frame.speaker_id not in visible:
            visible.append(frame.speaker_id)

    return NarrativeView(
        tick=tick,
        scene_text="\n".join(lines),
        frames=frame_dicts,
        actors_visible=visible,
        clock={"tick": tick},
    )
