# Game Flow Interfaces

本文档记录游戏主流程的接口契约，供后续重构、Prompt 修改、配置扩展和协作开发时对齐使用。实现代码可以演进，但涉及本文件中的状态字段、节点输入输出、结构化模型或存档格式时，应同步更新本文档。

## 1. Design Principles

1. **图内状态使用 JSON-friendly dict**
   - LangGraph 内部 state 不保存 Pydantic 对象。
   - State 中不保存 `Path`、`datetime`、`Enum`、复杂 class 实例或不可 JSON 序列化对象。
   - 节点返回 partial update dict，由 LangGraph 合并到全局 state。

2. **Pydantic 只用于边界**
   - LLM 结构化输出使用 Pydantic 校验。
   - YAML 配置读取使用 Pydantic 校验。
   - 初始化 Agent 输出使用 Pydantic 校验。
   - 存档读取、导入或迁移时可使用 Pydantic 或专门函数做边界校验。

3. **节点之间只通过 `GameState` 交互**
   - 节点不直接调用 UI。
   - 节点不读写磁盘。
   - 节点不依赖全局可变状态。
   - 节点可以调用 LLM、PromptLoader 和纯函数 helper，但输出必须是 state partial update。

4. **下游节点不消费原始玩家输入**
   - `player_input` 只供 `player_intent_process` 使用。
   - NPC、物理和感官节点读取 `player_action`，不直接解释 `player_input`。

5. **Prompt 输出必须有 Pydantic schema 对应**
   - 每个结构化输出 prompt 都必须对应 `src/models/events.py` 或相关模型中的 schema。
   - Prompt 不应要求模型输出 schema 中不存在的字段。
   - 修改 Prompt 输出结构时必须同步修改模型和本文档。

## 2. State Contract

`GameState` 是 LangGraph tick 的唯一共享状态。图内状态应为普通 dict，字段值应保持 JSON-friendly。

### 2.1 Persistent State

这些字段长期存在，并应进入存档：

| 字段 | 类型 | 说明 |
|---|---|---|
| `tick` | `int` | 当前回合数。 |
| `max_ticks` | `int` | 最大回合数。 |
| `game_phase` | `str` | 游戏阶段，例如 `init`、`running`、`ended`。 |
| `world_name` | `str` | 世界名称。 |
| `world_description` | `str` | 世界描述。 |
| `locations` | `dict[str, dict]` | 地点数据，key 为 location id。 |
| `objects` | `dict[str, dict]` | 物体数据，key 为 object id。 |
| `character_positions` | `dict[str, dict[str, float]]` | NPC 位置，key 为 character id。 |
| `environment` | `dict` | 时间、天气、温度等环境信息。 |
| `characters` | `dict[str, dict]` | NPC 状态，key 为 character id；每个角色可包含 `attributes` 数值属性表。 |
| `player` | `dict` | 玩家状态，可包含 `attributes` 数值属性表。 |
| `world_rules` | `dict` | 从 init YAML 注入的规则配置。`physics`/`attribute` 子字段用于 LLM prompt 规则注入；`deterministic` 子字段用于 Python 侧系统规则预判，可声明 `disable`（禁用内置规则索引）和 `append`（追加正则/数值条件规则）。 |
| `narrative_style` | `dict[str, str]` | 从 init YAML 注入的叙事风格配置，含 `style_description`（文风描述）和 `style_example`（参考文段示例）。默认为空 dict，使用内置默认文风。 |
| `event_log` | `list[str]` | 全局事件日志，只追加。 |

### 2.2 Tick Transient State

这些字段描述当前 tick 的中间结果，可以在每轮开始或结束时清空或重建：

| 字段 | 类型 | 说明 |
|---|---|---|
| `player_input` | `str | None` | 玩家原始输入，只供 `player_intent_process` 使用。 |
| `player_action` | `dict | None` | 结构化玩家行动，是下游节点读取玩家行动的唯一正式入口。 |
| `action_intents` | `list[dict]` | NPC 行动意图。 |
| `physics_outcomes` | `list[dict]` | 物理节点输出的物理后果。 |
| `player_percept` | `dict | None` | 玩家最近一次可感知信息；进入存档以便 `--load` 后直接渲染上一轮结果。 |

### 2.3 Reducer Fields

这些字段可能被多个节点追加更新，需要 reducer：

```python
event_log: Annotated[list[str], operator.add]
action_intents: Annotated[list[dict], operator.add]
```

如果后续新增并发节点追加字段，也必须显式定义 reducer。

## 3. Tick Pipeline

目标 tick 流程：

```text
START
  ↓
player_intent_process
  ↓
player_action_resolve
  ↓
characters_all_decide
  ↓
physics_resolve
  ↓
state_apply
  ├─ attribute_update ──→ END
  └─ sensory_filter → narrative_stylize → END
```

每个节点只读取所需字段，并返回 partial update。节点不应直接修改传入 state 对象。

## 4. Node Contracts

### 4.1 `player_intent_process`

职责：将玩家原始自然语言输入转成结构化 `PlayerAction`。潜意识规则是可选输入；即使没有潜意识设定，也必须完成结构化和必要细化。

输入字段：

- `player_input`
- `player`
- `characters`
- `objects`
- `locations`
- `environment`
- `event_log[-10:]`

输出字段：

- `player_action`
- `event_log`

规则：

- 无 `player_input` 时输出 `player_action=None`。
- 无潜意识设定时，不强行改变玩家意图，但要补全模糊表达。
- 有潜意识设定时，可以修正表达方式或行动倾向。
- 不直接判断物理可行性，只解释“玩家想要/实际表达为”。

示例：玩家输入“向他解释我的意图”时，应根据上下文解析“他”是谁，并生成具体 `speech_content`。

### 4.2 `player_action_resolve`

职责：判断结构化玩家行动在当前世界和能力约束下是否可行。

输入字段：

- `player_action`
- `player.capabilities`
- `player.physical_profile`
- `objects`
- `locations`
- `environment`
- `world_rules`

输出字段：

- `player_action`
- `event_log`

规则：

- 填充或更新 `feasibility`、`feasibility_reason`、`success_probability`、`requires_roll`。
- 会先调用 `src/game/rules.py::check_action_feasibility()` 生成系统规则预判。
- `world_rules.deterministic` 可在系统规则预判阶段追加自定义规则：`match_action` 使用正则匹配行动文本，`condition` 使用安全的 `if(cond, out; ...; else_out)` 数值条件表达式。
- `world_rules.deterministic.disable` 可禁用内置预判规则：1=`blocked_common`，2=`extraordinary`，3=`strength_vs_weight`，4=`skill_vs_lock`，5=`body_width_vs_passage`。
- 自定义规则按 YAML 顺序检查，第一条命中即作为系统预判；解析或求值失败的自定义规则只记录 warning 并跳过，不中断游戏。
- 系统规则预判必须传入 LLM；LLM 不应被跳过。
- 除非当前场景存在明确、具体、且优先级更高的反例，LLM 应遵循系统规则预判；若反驳预判，必须在 `feasibility_reason` 中说明原因。
- `blocked` 行动不应直接修改世界。
- `uncertain` 行动的真实 roll 由 `state_apply` 的 Python 逻辑执行。

### 4.3 `characters_all_decide`

职责：让所有 NPC 根据当前世界、玩家结构化行动和自身状态生成行动意图。

输入字段：

- `characters`
- `character_positions`
- `objects`
- `locations`
- `environment`
- `player_action`
- `event_log[-10:]`

输出字段：

- `action_intents`
- `event_log`

规则：

- NPC 不直接读取 `player_input`。
- 第一版并发优化可在节点内部使用 `asyncio.gather()`。
- 返回顺序不作为游戏逻辑依据。

### 4.4 `physics_resolve`

职责：根据玩家行动和 NPC 行动推演物理后果。

输入字段：

- `player_action`
- `action_intents`
- `objects`
- `character_positions`
- `player.position`
- `environment`

输出字段：

- `physics_outcomes`
- `event_log`

规则：

- 同时处理玩家和 NPC 行动。
- 不直接修改 state，只输出 outcomes。
- 不处理秘密信息展示；玩家能看到什么由 `sensory_filter` 决定。

### 4.5 `state_apply`

职责：使用确定性 Python 逻辑应用物理后果和行动结果。

输入字段：

- `player_action`
- `action_intents`
- `physics_outcomes`
- 当前世界状态

输出字段：

- `player`
- `characters`
- `character_positions`
- `objects`
- `tick`
- `action_intents`
- `physics_outcomes`
- `player_input`

规则：

- 只做确定性状态应用。
- 不调用 LLM。
- 不生成玩家感官叙述。
- 通过 `src/game/state_apply.py::apply_player_action()` 应用玩家行动结果。
- `allowed` 的移动行动可更新 `player.position`；可携带物体交互可更新 `player.inventory` 和物体 `state`。
- `blocked` 行动可以记录事件，但不应改变对应世界状态。
- `uncertain` 且 `requires_roll=true` 的行动由 Python 侧 roll 决定成功/失败。

### 4.6 `attribute_update`

职责：根据本 tick 的行动、物理后果、近期事件和自然变化规则更新玩家与 NPC 的任意数值属性。

输入字段：

- `player.attributes`
- `characters[*].attributes`
- `player_action`
- `action_intents`
- `physics_outcomes`
- `event_log[-10:]`
- `environment`
- `game_time`

输出字段：

- `player`
- `characters`
- `event_log`

规则：

- 属性存放在角色自身 dict 的 `attributes` 字段下，不新增顶层属性状态。
- 每个属性由 init/config 自由定义 key，通用字段包括 `name`、`value`、`min`、`max`、`natural_delta_per_tick`、`description`、`hidden`、`unit`、`tags`、`locked`。
- Python 先应用 `natural_delta_per_tick` 并执行 min/max 裁剪。
- LLM 只输出 `AttributeUpdateResolution` 补丁；不存在的属性 key 应被忽略，不自动创建。
- 与 `sensory_filter` 并行运行；第一版不保证同一 tick 的属性变化会立即出现在玩家感官文本中。

### 4.7 `sensory_filter`

职责：把世界真实状态过滤成玩家可感知信息。

输入字段：

- 更新后的世界状态
- `player`
- `event_log[-10:]`

输出字段：

- `player_percept`

规则：

- 只输出玩家可感知内容。
- 不泄漏 hidden、internal、debug 字段。

### 4.8 `narrative_stylize`

职责：将 `sensory_filter` 输出的结构化感知数据改写为小说化的沉浸式叙事文本。

输入字段：

- `player_percept`（来自 `sensory_filter`）
- `player.name` / `player.persona`
- `environment`
- `game_time`
- `narrative_style`

输出字段：

- `player_percept`（新增 `narrative` 字段，保留所有原始字段）

规则：

- 在 `sensory_filter` 完成后串行执行，不改变管道并行结构（`sensory_filter → narrative_stylize → END`）。
- 读取 `narrative_style.style_description` 和 `narrative_style.style_example` 作为风格控制；两者均可为空，此时使用内置默认文风。
- 输出写入 `player_percept.narrative` 字段；原始 `senses`、`summary`、`self_action_summary` 等字段保持不变，供 `/see`、`/hear`、`/feel` 命令使用。
- 小说化叙事不应编造原始感知数据中不存在的事件、角色或对话。
- 失败时回退：将 `summary` 作为 `narrative` 字段内容。

## 5. Data Model Contracts

### 5.1 `PlayerAction`

`PlayerAction` 是玩家行动的唯一正式结构化入口。目标字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `raw_input` | `str` | 玩家原始输入。 |
| `interpreted_intent` | `str` | 对玩家真实意图的解释。 |
| `subconscious_adjustment` | `str | None` | 潜意识或人设造成的修正；无修正时为空。 |
| `action_type` | literal | 行动类型：`move`、`interact`、`speak`、`use_item`、`wait`、`observe`。 |
| `action_description` | `str` | 玩家实际尝试做出的行动。 |
| `speech_content` | `str | None` | 玩家实际说出口的话。 |
| `target_object_id` | `str | None` | 目标物体。 |
| `target_character_id` | `str | None` | 目标角色。 |
| `target_position` | `dict | None` | 目标位置。 |
| `emotion` | `str` | 玩家行动时的情绪。 |
| `feasibility` | `str | None` | `allowed`、`blocked`、`uncertain` 或空。 |
| `feasibility_reason` | `str | None` | 可行性原因。 |
| `success_probability` | `float | None` | 成功概率。 |
| `requires_roll` | `bool` | 是否需要随机检定。 |
| `confidence` | `float` | 解析置信度。 |
| `notes` | `str` | 调试说明，不直接展示给玩家。 |

规则：

- `subconscious_adjustment` 可为空。
- `speech_content` 在说话、解释、交涉类动作中应尽量具体。
- `feasibility` 初始可为空，由 `player_action_resolve` 填充。
- 下游节点不得重新解释 `raw_input`。

### 5.2 `ActionIntent`

NPC 行动意图，由角色 prompt 输出。它不表示玩家行动。

### 5.3 `PhysicsResolution`

物理节点输出的物理后果集合。它描述发生了什么，不直接负责写入世界状态。

### 5.4 `AttributeUpdateResolution`

属性更新节点输出的属性变化补丁集合。它只能描述已有属性的 delta，不直接返回完整角色状态。

### 5.5 `PlayerPercept`

玩家感官输出。它是 UI 面向玩家展示的主要结构，不应包含 debug reasoning。

### 5.6 `NarrativeOutput`

叙事改写节点的输出模型，仅含一个字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `narrative` | `str` | 小说化叙事文本。 |

## 6. Prompt Contracts

| Prompt | 输出模型 | 说明 |
|---|---|---|
| `player_intent_system.j2` / `player_intent_user.j2` | `PlayerAction` | 结构化和细化玩家输入，可选应用潜意识规则。 |
| `player_action_resolve_system.j2` / `player_action_resolve_user.j2` | `PlayerAction` | 判断玩家行动可行性。 |
| `character_system.j2` / `character_user.j2` | `ActionIntent` | 生成 NPC 行动。 |
| `physics_system.j2` / `physics_user.j2` | `PhysicsResolution` | 生成物理后果。物理规则由 `build_rules_context(PHYSICS_DEFAULT_RULES, world_rules.physics)` 动态生成后注入 `{{ rules }}` 上下文。 |
| `attribute_update_system.j2` / `attribute_update_user.j2` | `AttributeUpdateResolution` | 生成角色属性变化补丁。属性规则由 `build_rules_context(ATTRIBUTE_DEFAULT_RULES, world_rules.attribute, extra_sections=[...])` 动态生成后注入 `{{ rules }}` 上下文。 |
| `sensory_system.j2` / `sensory_user.j2` | `PlayerPercept` | 生成玩家可感知内容。 |
| `narrative_system.j2` / `narrative_user.j2` | `NarrativeOutput` | 将结构化感官数据改写为小说化叙事。由 `narrative_style.style_description` 和 `narrative_style.style_example` 控制文风。 |

Prompt 规则：

- 输出保持中文。
- 结构化输出必须严格遵守对应 Pydantic schema。
- 不引入 schema 外字段。
- 内部推理、debug 说明不得进入玩家感官输出。

## 7. Config Contracts

YAML 配置由 `src/config/loader.py` 读取，并由 `src/models/config.py` 校验。

### 7.1 Player Config

玩家配置应逐步支持：

- `name`
- `starting_position`
- `capabilities`
- `starting_inventory`
- `persona`
- `subconscious_rules`
- `subconscious_memory`
- `speech_examples`
- `physical_profile`
- `attributes`
- `allowed_extraordinary_actions`
- `blocked_common_actions`
- `skill_levels`

### 7.2 Character Config

角色配置应逐步支持：

- `id`
- `name`
- `personality`
- `starting_position`
- `starting_inventory`
- `relationships`
- `attributes`
- `speech_examples`
- `physical_profile`

### 7.3 World Config

世界配置继续支持：

- world metadata
- locations
- objects
- environment

物理尺寸等字段第一阶段可以放入 object `properties`，规则稳定后再收敛为强 schema。

## 8. Save/Load Contract

存档目标格式为 JSON-friendly `GameState`。

规则：

- 默认保存到 `saves/`。
- 存档应包含 persistent state 和最近一次 `player_percept`，以便 `--load` 后先渲染上一轮结果再等待新输入。
- `player_input`、`player_action`、`action_intents`、`physics_outcomes` 等 tick 中间状态不写入存档。
- 存档可能包含玩家设定和对话内容，应视为用户数据。
- 后续应确保 `saves/` 不被提交。

## 9. Compatibility Rules

1. 修改 `GameState` 字段时，同步更新：
   - 本文档；
   - `src/graph/game_state.py`；
   - 相关节点；
   - 存档加载逻辑。

2. 修改 Prompt 输出结构时，同步更新：
   - 对应 Pydantic 模型；
   - prompt 模板；
   - 本文档；
   - 相关测试或手动验证用例。

3. 修改 YAML schema 时，同步更新：
   - `src/models/config.py`；
   - 示例 YAML；
   - 本文档。

4. 下游节点不得绕过 `player_action` 直接解析 `player_input`。

5. 图内状态不得重新引入 Pydantic 对象，除非重新评估 LangGraph checkpoint、并发合并和存档兼容性。