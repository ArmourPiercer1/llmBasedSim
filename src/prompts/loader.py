from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

PHYSICS_DEFAULT_RULES: list[str] = [
    "1. **重力**：没有支撑的物体会向下方（y轴负方向）掉落。",
    "2. **碰撞检测**：如果角色的动作使其身体延伸到某个物体所在的空间，则发生碰撞。碰撞的严重程度取决于动作的 intensity 参数。",
    "3. **连锁反应**：一个物体的移动可能导致其他物体受到影响。连锁反应深度通常不超过3级。",
    "4. **脆弱物品**：标记为 fragile=true 的物体在受到足够冲击时会碎裂或损坏。",
    "5. **声音传播**：响亮的声音（玻璃碎裂、大声喊叫、重物掉落）会传播到整个当前地点，影响所有在场角色；轻微的声音（脚步声、低声细语）只在5米范围内可察觉。",
    "6. **不可移动物体**：标记为 immovable=true 的物体不会被移动，但可能被碰撞影响。",
    "7. **角色互动**：角色之间的直接互动（speak类型动作）不产生物理结果——除非动作描述中明确包含物理接触。但如果一个角色的动作影响了环境，这个环境变化可能影响其他角色。",
    "8. **物理一致性**：不要编造与场景设定矛盾的物理结果。如果你不确定某个结果是否合理，选择更保守的预判。",
    "9. **动作类型一致性**：优先依据 action_type 判断物理行为；如果 action_type 与描述不一致（例如 speak 中夹带走动），只能在 reasoning 中简要说明，不要强行制造物理后果。",
    "10. **JSON安全**：所有字符串字段必须是合法JSON字符串。reasoning和description中不要使用英文双引号引用短语；如需引用，请使用中文书名号《》或单引号。",
]

ATTRIBUTE_DEFAULT_RULES: list[str] = [
    "1. 只允许更新用户消息中列出的已有属性 key；不要创造新属性。",
    "2. 只输出属性数值变化，不要修改位置、物品、关系、世界物体状态或角色记忆。",
    "3. `delta` 是相对于当前值的变化量，可以为正、负或 0。",
    "4. 如果某个属性没有理由变化，就不要输出 change。",
    "5. 变化幅度应保守：普通行动通常为 1-5，强烈事件才使用更大变化。",
    "6. 已有自然恢复/消耗已由系统处理；你只处理行动和事件造成的额外变化。",
    "7. 对 `hidden=true` 的属性仍可更新，但 reason 不要泄漏玩家不应知道的秘密，只写内部原因。",
]

ATTRIBUTE_DEFAULT_REFERENCES: list[str] = [
    "- 奔跑、战斗、搬重物、受伤：体力/耐力下降。",
    "- 休息、进食、喝水、治疗：相关属性恢复。",
    "- 侮辱、失败、恐惧、危险：心情/压力/理智等下降。",
    "- 鼓励、成功、被帮助：心情/士气等上升。",
    "- 使用魔法或特殊能力：魔法值/能量等下降。",
]


def build_rules_context(
    default_rules: list[str],
    custom_rules_config: dict[str, Any] | None,
    *,
    extra_sections: list[tuple[str, list[str]]] | None = None,
) -> str:
    """Build a rule text block from default rules and optional custom configuration.

    `default_rules` are the 1-indexed built-in rules.
    `custom_rules_config` may contain `disable` (list of int rule indices) and `append` (list of str).
    `extra_sections` is an optional list of (heading, lines) to insert before rule items, such as
    references / common knowledge.
    Returns a Jinja2-safe string ready for template interpolation.
    """
    config = custom_rules_config or {}
    disabled: set[int] = {int(i) for i in (config.get("disable") or []) if isinstance(i, (int, float))}
    append_rules: list[str] = [str(r) for r in (config.get("append") or []) if isinstance(r, str)]

    sections: list[str] = []

    # ── Extra sections (references etc.) ──
    if extra_sections:
        for heading, lines in extra_sections:
            if not lines:
                continue
            sections.append(f"## {heading}")
            sections.extend(lines)
            sections.append("")

    # ── Default rules ──
    if default_rules:
        sections.append("## 默认规则")
        for i, rule in enumerate(default_rules, 1):
            if i in disabled:
                continue
            sections.append(rule)
        sections.append("")

    # ── Custom appended rules ──
    if append_rules:
        sections.append("## 自定义规则")
        next_index = len(default_rules) + 1
        for rule in append_rules:
            # If the rule already starts with a number prefix like "11. ", keep it;
            # otherwise auto-number it.
            stripped = rule.strip()
            if stripped and (stripped[0].isdigit() or (len(stripped) > 1 and stripped[1].isdigit())):
                sections.append(stripped)
            else:
                sections.append(f"{next_index}. {stripped}")
            next_index += 1
        sections.append("")

    sections.append("")
    return "\n".join(sections)


class PromptLoader:
    def __init__(self, prompts_dir: str = "prompts"):
        self._env = Environment(
            loader=FileSystemLoader(prompts_dir),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template_name: str, context: dict) -> str:
        template = self._env.get_template(template_name)
        return template.render(**context)
