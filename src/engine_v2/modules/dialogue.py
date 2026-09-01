"""P9 W6 官方模块：dialogue（T11；SOT §3.10 L746–765；导出 3 名）。

来源 = v1 对话 = 推理直出（``_decide_one_char`` 族）→ v2 = 结构化对话
回合（Policy 提案 → 执行器 → 关系回写），43.1-7 思想保留。

冻结消费（SOT §2.1/§2.4/§2.5）：core ``state``（``WorldState``:246）；
core ``revision``（``Revision``:43）；推理适配面（``InferenceBackend``:150
/ ``InferenceRequest``:98 / ``InferenceResponse``:132）；模块公共面
``modules.base``；``modules.character``（``NpcBehaviorPolicy``，W1
交付物）。SOT §3.1.2 requires 表 L488：dialogue = (character,
relationships)——对话方 = 角色；结果回写关系。

必备解释 (a)（DEV-W6-1，预裁决——闭集词表与数值）：SOT 未钉
``dialogue_relationship_delta`` 词表与数值。本模块钉定（测试同源钉 +
盲评独立复核）：

- 正增量标记（感谢/致歉类，casefold 后子串计次）：``感谢`` / ``谢谢``
  / ``对不起`` / ``抱歉`` / ``sorry`` / ``thanks`` / ``thank you``；
- 负增量标记（威胁类）：``威胁`` / ``警告`` / ``小心`` / ``杀了你`` /
  ``threat`` / ``kill``；
- 数值 = ``round(0.05 × 正命中数 - 0.10 × 负命中数, 6)``（命中数 =
  casefold 文本子串出现次数；确定性：同输入恒同输出）；
- 扫描面 = utterance 与 response 以换行拼接（SOT 表行 2 钉 response
  面；utterance 面 = 对称扩展——发言中的威胁同样产生负增量；属本预
  裁决词表面）。
- 备选（否）：无可枚举备选（SOT 未钉具体词表 / 数值；实现设计面，
  A1 同源断言 + 三分支钉值 + 盲评独立复核约束）。

纪律（K2/K5/D6/K8）：``run_dialogue`` 对 world 零写（只读消费；关系
落位由宿主经 ``modules.relationships.adjust_relationship`` 完成，
K2）；零随机 / wall-clock；零第三方编排/推理 SDK 导入（12 名闭集零
命中，SOT §0.5 D7）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from src.engine_v2.core.state import WorldState
from src.engine_v2.llm.adapter import InferenceBackend, InferenceRequest
from src.engine_v2.modules.base import OFFICIAL_MODULE_VERSION, ModuleIdentity
from src.engine_v2.modules.character import NpcBehaviorPolicy

__all__ = [
    "DialogueResult",
    "dialogue_relationship_delta",
    "run_dialogue",
]

#: 模块身份（SOT §3.1.2 requires 表 L488：dialogue = (character,
#: relationships)）。
IDENTITY: Final[ModuleIdentity] = ModuleIdentity(
    "llmsim-standard-dialogue",
    OFFICIAL_MODULE_VERSION,
    ("llmsim-standard-character", "llmsim-standard-relationships"),
)

#: 对话回合推理调用面 logical_role / profile（adapter #19 约定：
#: 请求三值同串；常量名本模块自定，此处钉死）。
_DIALOGUE_ROLE: Final[str] = "npc_dialogue"

#: 正增量标记（感谢/致歉类；DEV-W6-1 钉定闭集）。
_POSITIVE_MARKERS: Final[tuple[str, ...]] = (
    "感谢", "谢谢", "对不起", "抱歉", "sorry", "thanks", "thank you",
)

#: 负增量标记（威胁类；DEV-W6-1 钉定闭集）。
_NEGATIVE_MARKERS: Final[tuple[str, ...]] = (
    "威胁", "警告", "小心", "杀了你", "threat", "kill",
)

#: 数值面（DEV-W6-1 钉定）：每正命中 +0.05 / 每负命中 -0.10，
#: round 6 位。
_POSITIVE_STEP: Final[float] = 0.05
_NEGATIVE_STEP: Final[float] = 0.10
_ROUND_DIGITS: Final[int] = 6


@dataclass(frozen=True)
class DialogueResult:
    """一次对话回合的冻结结果（SOT §3.10 表行 1；字段逐字钉定）。"""

    speaker_id: str
    respondent_id: str
    utterance: str
    response: str
    relationship_delta: float
    tick: int


def dialogue_relationship_delta(utterance: str, response: str) -> float:
    """确定性规则式增量（SOT §3.10 表行 2；A3 主面）。

    词表 / 数值 / 扫描面 = 模块 docstring 必备解释 (a)（DEV-W6-1）钉定：
    闭集标记 casefold 子串计次 → ``round(0.05×正 - 0.10×负, 6)``；
    零推理消费 / 零随机（同输入恒同输出）。
    """
    text = (utterance + "\n" + response).casefold()
    positive = sum(text.count(marker) for marker in _POSITIVE_MARKERS)
    negative = sum(text.count(marker) for marker in _NEGATIVE_MARKERS)
    return round(_POSITIVE_STEP * positive - _NEGATIVE_STEP * negative,
                 _ROUND_DIGITS)


def run_dialogue(
    world: WorldState,
    speaker_id: str,
    respondent_id: str,
    utterance: str,
    backend: InferenceBackend,
    policy: NpcBehaviorPolicy,
    tick: int,
) -> DialogueResult:
    """对话回合（SOT §3.10 表行 3；A1 主面）。

    流程（确定性）：

    1. 一致性面：``policy.record.character_id == respondent_id``
       （B-CON-5 同族一致性，违规 → ``ValueError``）；speaker /
       respondent 均须为 world 实体（宿主构建面；缺席 →
       ``ValueError``）；
    2. 经注入 backend 取回应（脚本化；K5 零推理 SDK——backend =
       Protocol 调用面）：``InferenceRequest``:98 构造（三值同串
       ``npc_dialogue``；messages = 单条 user 消息，内容 = 发言方 /
       应答方 / 发言文本确定性拼接；base_revision =
       ``world.world_revision``；零 uuid——id 确定性拼装）；
    3. ``relationship_delta = dialogue_relationship_delta(utterance,
       response)``（同源自函数）；
    4. 返回 ``DialogueResult``。

    K2 零写：本函数只读 world——关系落位由宿主经
    ``modules.relationships.adjust_relationship``（W2 交付物）+ kernel
    事务面完成（SOT §3.10 表行 3 括注）。
    """
    if policy.record.character_id != respondent_id:
        raise ValueError(
            "run_dialogue respondent 与 policy 角色不一致："
            f"{policy.record.character_id!r} != {respondent_id!r}"
        )
    for entity_id in (speaker_id, respondent_id):
        if entity_id not in world.entities:
            raise ValueError(
                f"run_dialogue 实体不在世界：{entity_id!r}"
            )
    request = InferenceRequest(
        messages=[
            {
                "role": "user",
                "content": (
                    f"speaker={speaker_id}; respondent={respondent_id}; "
                    f"utterance={utterance}"
                ),
            }
        ],
        model=_DIALOGUE_ROLE,
        base_url="",
        api_key_env=None,
        temperature=0.0,
        max_tokens=None,
        timeout_seconds=0.0,
        logical_role=_DIALOGUE_ROLE,
        profile=_DIALOGUE_ROLE,
        base_revision=world.world_revision,
        prompt_metadata_ref=(
            f"prompt://{respondent_id}:{tick}:{world.world_revision}"
        ),
    )
    response = backend.generate(request)
    delta = dialogue_relationship_delta(utterance, response.text)
    return DialogueResult(
        speaker_id=speaker_id,
        respondent_id=respondent_id,
        utterance=utterance,
        response=response.text,
        relationship_delta=delta,
        tick=tick,
    )
