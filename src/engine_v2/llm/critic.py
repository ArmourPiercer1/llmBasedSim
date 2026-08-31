"""P6-W6 推理侧 critic（SOT §3.8；确定性纯函数，零 I/O）。

契约面（SOT §3.8 L402-419 钉死）：

- ``__all__`` 四元封闭且顺序钉死：``CriticResult`` / ``CRITIC_DEFAULT_ENABLED`` /
  ``critique`` / ``critique_instruction``；
- ``CRITIC_DEFAULT_ENABLED = False``（flag 默认关，Leader-A6）；
- ``critique(context, wire) -> CriticResult``：按钉死顺序执行两项检查，
  均不短路（两项都执行，errors 按钉死顺序聚合）；
- ``CriticResult`` 冻结：``ok: bool`` + ``errors: tuple[str, ...]``
  （错误串 = 稳定机器可读码，非展示文案）；
- ``critique_instruction(errors) -> str``：一行一错 + 重申只输出 JSON
  （repair 轮次的用户消息文本）。

检查顺序（钉死）：

1. ``wire.action_id is None`` → 合法 no-op，直接 ok（不查任何字段）；
2. ``wire.action_id not in set(context.candidate_actions)`` →
   ``action-not-in-candidates``；
3. ``wire.arguments`` 中键 ∈ 封闭集 ``{entity_id, target_id, target, actor_id}``
   且值为 str 的标量目标字段：值 ∉ 可见实体并集（``visible_entities`` ∪
   ``local_entity_views`` 键 ∪ ``global_entity_views`` 键）→ 每个违规值一条
   ``target-not-visible``（按 arguments 键序，一个键至多一条）；
4. 全部通过 → ok=True。

可见性域只消费 JSON-clean 面（context 为 P4 冻结数据类，本模块以
``typing.TYPE_CHECKING`` 引用类型，运行时零依赖 P4 类型导入图）。

K8 纪律：本文件全部字符串字面量（含 docstring）对 12 名封闭集
casefold 词边界扫描 0 命中（方法 = 冻结 test_import_boundary 口径）。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Final

from pydantic import BaseModel, ConfigDict

from src.engine_v2.prompts.assembler import LLMActionProposal

if TYPE_CHECKING:  # D2：类型引用不进运行时导入图（ERR-P6-10(b) DAG）
    from src.engine_v2.core.context_provider import ActorDecisionContext

__all__ = ["CriticResult", "CRITIC_DEFAULT_ENABLED", "critique", "critique_instruction"]

#: critic flag 默认值（默认关；policy 仅在 enable_critic=True 时惰性调用）。
CRITIC_DEFAULT_ENABLED: Final[bool] = False

#: 检查 2 的机器码（稳定值，测试与诊断 refs 消费）。
_ACTION_NOT_IN_CANDIDATES: Final[str] = "action-not-in-candidates"
#: 检查 3 的机器码。
_TARGET_NOT_VISIBLE: Final[str] = "target-not-visible"
#: 检查 3 的目标键封闭集（未知键不查，SOT §3.8）。
_TARGET_KEY_CLOSED_SET: Final[frozenset[str]] = frozenset(
    {"entity_id", "target_id", "target", "actor_id"}
)


class CriticResult(BaseModel):
    """critique 结果（冻结；``errors`` 顺序 = 钉死检查顺序）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool
    errors: tuple[str, ...] = ()


def _visible_entity_ids(context: ActorDecisionContext) -> frozenset[str]:
    """可见实体并集：visible_entities ∪ local_entity_views 键 ∪ global_entity_views 键。"""
    visible = frozenset(context.visible_entities)
    local = frozenset(context.local_entity_views.keys())
    global_views = context.global_entity_views
    if global_views is None:
        return visible | local
    return visible | local | frozenset(global_views.keys())


def critique(context: ActorDecisionContext, wire: LLMActionProposal) -> CriticResult:
    """对一次推理侧提案（wire）做确定性审查（纯函数，零 I/O）。

    两项检查均执行、不短路；errors 按检查顺序聚合（检查 2 先于检查 3；
    检查 3 内部按 arguments 键序）。合法 no-op（``action_id is None``）
    直接 ok。
    """
    if wire.action_id is None:
        return CriticResult(ok=True, errors=())

    errors: list[str] = []

    # 检查 2：候选动作域（不短路，继续检查 3）。
    if wire.action_id not in set(context.candidate_actions):
        errors.append(_ACTION_NOT_IN_CANDIDATES)

    # 检查 3：标量目标字段可见性域（一个违规值一条，按键序）。
    visible = _visible_entity_ids(context)
    for key, value in wire.arguments.items():
        if key in _TARGET_KEY_CLOSED_SET and isinstance(value, str) and value not in visible:
            errors.append(_TARGET_NOT_VISIBLE)

    return CriticResult(ok=not errors, errors=tuple(errors))


def critique_instruction(errors: Sequence[str]) -> str:
    """生成 repair 轮次的用户消息文本：一行一错 + 重申只输出 JSON。

    确定性：同输入同输出（无时钟、无随机、无环境读取）。
    """
    lines = ["提案未通过推理侧审查："]
    lines.extend(f"- {error}" for error in errors)
    lines.append("请修正后重新作答，只输出系统契约要求的 JSON 结构，不要输出解释。")
    return "\n".join(lines)
