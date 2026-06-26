# 基于 LLM Agent 的互动模拟游戏

本工作区实现了一个由多个 LLM Agent 协同驱动的互动模拟游戏框架。游戏世界由结构化状态维护，NPC 会根据自身设定和世界状态自主做出行为，物理 Agent 推演环境变化，玩家感官 Agent 再将世界真实状态过滤为玩家可感知的信息。

项目当前处于**可运行原型阶段**。

## 主要特色

**多 Agent 协同推演。** 7 个 LangGraph 节点构成完整 tick 管道：玩家意图处理 → 行动可行性判断 → NPC 并发生成行动 → 物理推演 → 确定性状态应用 → 属性更新 / 玩家感官过滤。每轮输入驱动一轮完整的模拟推演，不再是固定剧本的"选择分支"。

**玩家潜意识系统。** 玩家输入的不仅是"想做什么"，还会被人设潜意识修正。一个傲娇大小姐即使心里想说"我爱你"，说出口的也可能是"哼，才没有喜欢你呢"。潜意识规则和记忆可以被游戏中的经历逐步更新。

**行动可行性判断（双轨制）。** 玩家行动同时经过 Python 确定性规则预判（能力约束、物理约束、技能检定）和 LLM 综合判断，产生 `allowed`/`blocked`/`uncertain` 三个结果。`uncertain` 的行动由随机检定决定成败。

**NPC 自主行为与关系演化。** NPC 根据性格、记忆、当前世界状态和玩家行动并发决策。好感度随行动情感波动，关系中积累的 ±0.05 最终会反映在 NPC 对玩家的行为上。

**开放式世界设计。** 通过单个 YAML 文件定义完整的世界（地点、物体、角色、环境），零编码即可创建全新的剧情场景。支持文件开局、对话开局和分散配置文件开局三种模式。

**存档/读档。** 游戏状态可随时保存为 JSON，支持 `/save <name>` 和 `--load <path>`。

**玩家感知过滤。** 世界真实状态和玩家能感知到的是两回事。感官 Agent 根据视野、听力、光线、遮挡等条件过滤信息——你不知道角落里那个 NPC 在想什么，除非他开口说。

## 快速开始

### 环境要求

- Python >= 3.12
- DeepSeek API Key

### 安装依赖

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 配置环境变量

复制 `.env.example` 为 `.env`，并填入真实 API Key：

```bash
cp .env.example .env
```

`.env` 内容示例：

```env
DEEPSEEK_API_KEY=sk-your-key-here
```

### 切换 API 后端

本项目使用 OpenAI 兼容客户端（`langchain_openai.ChatOpenAI`），任何兼容 OpenAI API 格式的服务都可以直接使用。切换只需修改两个文件：

**[`config/simulation.yaml`](config/simulation.yaml) — LLM 配置：**

```yaml
llm:
  provider: "deepseek"              # 任意标识，仅用于日志
  model: "deepseek-chat"            # 目标 API 的模型名
  api_key_env: "DEEPSEEK_API_KEY"   # .env 中对应的环境变量名
  base_url: "https://api.deepseek.com"  # API 端点 URL
  temperature: 0.7
  max_tokens: 16384
```

**[`.env`](.env) — API 密钥：**

确保 `api_key_env` 对应的环境变量已设置。

**常见后端示例：**

| 后端 | model | base_url | api_key_env |
|---|---|---|---|
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` |
| OpenAI | `gpt-4o` | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| 本地 Ollama | `llama3` | `http://localhost:11434/v1` | `OLLAMA_API_KEY` (任意值) |
| 其他兼容服务 | 按服务文档 | 按服务文档 | 按服务文档 |

核心逻辑在 [`src/main.py:46-52`](src/main.py#L46-L52) —— 所有 LLM 参数都从配置读取，没有硬编码。

### 启动游戏

```bash
python -m src.main
```

可用命令：

- `/quit` 或 `/exit`：退出游戏；
- `/help`：显示帮助；
- `/status`：显示玩家当前数值状态；
- `/save <name>`：保存当前进度；
- `/stop`：终止当前长行动。

### 从初始化文件直接开局

跳过对话初始化，使用预编写的 YAML 文件直接启动：

```bash
python -m src.main --init-file config/init_test.yaml
```

初始化文件格式参见 [`config/init_test.yaml`](config/init_test.yaml)（蔷薇庄园场景，含完整注释）。

更多场景文件见 [`private_start/files/`](private_start/files/) 目录。

## 项目定位

本项目不是固定剧本的文字冒险游戏，而是一个面向实验和扩展的 LLM 模拟游戏框架。核心目标是验证以下工作流：

```text
初始化 Agent
  ↓
玩家意图处理
  ↓
玩家行动可行性判断
  ↓
角色变化 Agent（并发）
  ↓
物理变化 Agent
  ↓
状态应用
  ↓
玩家感官 Agent
  ↓
玩家输入
  ↓
下一回合
```

长期目标是让角色、物理世界、玩家感知和世界状态形成一个可持续演化的模拟系统。

## 已有架构

### 入口层

- `src/main.py`

负责加载配置、加载 `.env`、初始化 LLM、运行初始化阶段、构建游戏图，并执行主游戏循环。

### 数据模型层

- `src/models/common.py`
- `src/models/world.py`
- `src/models/character.py`
- `src/models/player.py`
- `src/models/events.py`
- `src/models/config.py`

这些文件定义 Pydantic 数据模型，包括位置、世界、角色、玩家、事件和配置结构。

### 图与状态层

- `src/graph/game_state.py`
- `src/graph/game_graph.py`

`GameState` 是模拟世界的核心状态，使用 LangGraph `TypedDict` 定义。遵循"图内跑 dict，边界用 Pydantic"原则：状态在节点间以普通 dict 流转，Pydantic 只用于 LLM 输出解析、配置校验和存档边界。`game_graph.py` 构建 LangGraph tick 管道：

```text
START
  ↓
player_intent_process    ← 玩家输入 → 结构化 PlayerAction
  ↓
player_action_resolve   ← 判断可行性（能力/物理/技能）
  ↓
characters_all_decide   ← 所有 NPC 并发生成行动意图
  ↓
physics_resolve         ← 推演物理后果
  ↓
state_apply             ← 确定性状态应用
  ├─ attribute_update   ← 所有角色任意数值属性的自动更新
  └─ sensory_filter     ← 生成玩家感知 + 自行动反馈
      ↓
END
```

节点说明：

- `player_intent_process`：将玩家自然语言输入转成结构化 `PlayerAction`，补全模糊表达，可选应用潜意识规则；
- `player_action_resolve`：判断行动在当前世界中的可行性（`allowed`/`blocked`/`uncertain`），考虑玩家能力、物理约束和技能水平；
- `characters_all_decide`：使用 `asyncio.gather()` 并发生成所有 NPC 的行动意图；
- `physics_resolve`：根据玩家和 NPC 行动推演物理结果；
- `state_apply`：用确定性 Python 逻辑应用状态变化；
- `attribute_update`：根据本 tick 的行动、物理后果和事件更新玩家/NPC 的任意数值属性；
- `sensory_filter`：生成玩家可感知信息，同时反馈玩家角色本回合实际做了什么/说了什么。

### Agent 初始化层

- `src/agents/init.py`

通过四轮对话收集世界、玩家、NPC 和开场设定，然后调用 LLM 生成 `InitialGameConfig`，再转换为 `GameState`。同时提供 `load_init_file()` + `init_file_to_game_state()` 支持从单文件 YAML 直接开局。

### LLM 结构化输出层

- `src/llm/parser.py`

DeepSeek 当前不依赖原生 `response_format`。代码通过向 prompt 注入 JSON Schema，要求模型输出 JSON，再用 Pydantic 解析。如果解析失败，会带错误信息重试。

### Prompt 模板层

- `prompts/init_system.j2`
- `prompts/player_intent_system.j2`
- `prompts/player_intent_user.j2`
- `prompts/player_action_resolve_system.j2`
- `prompts/player_action_resolve_user.j2`
- `prompts/character_system.j2`
- `prompts/character_user.j2`
- `prompts/physics_system.j2`
- `prompts/physics_user.j2`
- `prompts/sensory_system.j2`
- `prompts/sensory_user.j2`

Prompt 使用中文 Jinja2 模板，由 `src/prompts/loader.py` 加载。

### 配置层

- `config/simulation.yaml`
- `config/world.yaml`
- `config/player.yaml`
- `config/characters/*.yaml`
- `config/init_test.yaml`

配置由 `src/config/loader.py` 加载并通过 Pydantic 校验。`init_test.yaml` 是包含完整世界、玩家和 NPC 设定的单文件测试场景。

#### 世界规则注入（`world_rules`）

Init YAML 可通过 `world_rules` 字段向物理引擎和属性更新系统注入场景特定规则，或禁用不适用的默认规则。格式如下：

```yaml
world_rules:
  physics:
    disable: [8]                # 禁用默认物理规则（1-based 索引）
    append:                     # 追加场景特定规则
      - "11. **亚空间低语**：Vox通讯中的Samus低语会导致附近电子设备间歇性失灵。"
      - "12. **低温环境**：气温-15°C下，裸露金属表面会结冰，需做防滑/解冻判定。"
  attribute:
    disable: []                 # 不禁用默认属性规则
    append:
      - "接触远古石碑时：sanity下降2-8点，corruption_resistance下降1-3点。"
```

- **`disable`**：要禁用的默认规则编号列表（1-based）。被禁用的规则不会出现在 LLM prompt 中。
- **`append`**：追加的自定义规则列表。规则自动编号（接续默认规则末尾），以"自定义规则"节出现在 prompt 中。
- 所有字段可选；未声明 `world_rules` 时行为与默认完全一致。
- 默认物理规则共 10 条（重力、碰撞检测、连锁反应、声音传播等），默认属性规则共 7 条。
- 完整示例参见 [`public_start/whisperheads.yaml`](public_start/whisperheads.yaml)（耳语山场景：禁用"物理一致性"规则以体现 Warp 影响区域的物理异常，追加 5 条物理规则和 3 条属性规则）。

### 接口文档

- `docs/game-flow-interfaces.md`

记录状态契约、节点输入输出、数据模型、Prompt 和存档格式的接口规范。修改相关代码时应同步更新该文档。

### UI 层

- `src/ui/cli.py`
- `src/ui/renderer.py`
- `src/ui/status.py`

使用 Rich 实现终端交互、双面板玩家感官输出和 tick 处理进度展示。

## 代码主要任务

1. 通过初始化 Agent 创建初始世界，或从 YAML 文件直接加载；
2. 将玩家自然语言输入结构化为 `PlayerAction`，支持模糊表达细化和可选的潜意识/人设修正；
3. 判断结构化玩家行动在当前世界中的可行性（能力约束、物理约束、技能检定）；
4. 维护玩家、NPC、物体、地点、环境等状态；
5. 驱动 NPC 根据性格、记忆、环境和结构化玩家行动做出行动；
6. 使用物理 Agent 推演玩家和角色行动造成的物理变化；
7. 将世界真实状态过滤成玩家可感知的信息，并反馈"玩家角色实际做了什么"；
8. 通过 CLI 与玩家交互。

## 已完成开发工作

当前已经完成：

- 项目依赖配置；
- Pydantic 数据模型（含玩家潜意识、能力约束、物理数据、语言范例）；
- YAML 配置加载与 Pydantic 校验；
- Jinja2 Prompt 模板（13 个模板，覆盖初始化、玩家意图、可行性、角色、物理、属性更新、感官全链路）；
- DeepSeek 接入；
- Prompt-based JSON 结构化解析；
- 初始化 Agent（对话式 + 文件式）；
- LangGraph tick 管道（7 节点，含玩家输入处理、行动可行性判断和属性更新）；
- 玩家输入结构化（`player_intent_process`）——模糊表达细化、可选潜意识修正；
- 玩家行动可行性判断（`player_action_resolve`）——LLM 综合判断 + Python 系统规则预判；
- Python 侧确定性规则预判（`src/game/rules.py`）——能力约束、物理约束、锁难度与技能概率；
- 玩家行动状态应用（`src/game/state_apply.py`）——玩家移动、物体交互、使用物品、blocked/uncertain/roll 事件；
- 概率检定（`requires_roll` + `success_probability`，由 Python 侧执行随机检定）；
- NPC 行为并发生成（`asyncio.gather()`）；
- NPC 行动状态应用（`apply_npc_actions`）——NPC 移动、交互、对话、使用物品结果写入状态；
- 对话状态追踪（`conversation_target` / `last_spoken_to`）——NPC 对话有连续性；
- 关系数值变化（`emotion` 驱动 `relationships`，好感度反映在行为中）；
- 通用角色属性系统（`attributes` + `attribute_update`）——init 文件可为玩家/NPC 定义任意数值属性，节点按行动、事件和自然变化更新；
- 世界规则注入（`world_rules`）——init YAML 可声明 `physics`/`attribute` 的 `disable` 和 `append`，向物理引擎和属性系统注入场景特定规则或屏蔽默认规则；
- 游戏时间追踪（`game_time` + `ticks_per_game_minute`，每 tick 推进，`time_of_day` 自动切换）；
- 行动时长与截断系统——长行动自动跨 tick 延续，`/stop` 终止；
- 物理结果生成（同时处理玩家与 NPC 行动）；
- 基础状态应用（物体移动、破坏、状态变化、玩家行动结果应用）；
- 玩家感官过滤 + 自行动反馈（"你做了什么"面板）；
- CLI 处理进度展示（`TurnStatus` Live 面板，实时显示管道步骤）；
- 命令内层循环（`/help` `/status` `/save` `/stop` 后即时响应，不触发 NPC 决策）；
- PlayerAction 字段强制填写 + Schema 嵌入约束；
- 玩家意图处理增强（目标三级匹配：精确→模糊→性格兜底）；
- 单文件 YAML 直接开局（`--init-file`）；
- 分散配置 YAML 直接开局（`--from-config`）；
- 存档/读档（`/save <name>` 与 `--load <path>`）；
- 调试输出开关（`simulation.debug`）；
- 事件日志压缩（超 100 条自动统计摘要）；
- 节点级容错（全部 6 个 LLM 节点含 try/except 降级）；
- NPC 语言范例注入（`speech_examples` → `character_system.j2`）；
- Rich CLI（双面板渲染）；
- 接口规范文档（`docs/game-flow-interfaces.md`）；
- `CONTRIBUTING.md` 接口维护约定。

## 当前限制

1. **长行动截断依赖 LLM 设置结构化字段**
   - 已有 Python 距离兜底和关键词兜底；
   - 但"无已知坐标的搜索类行动"（如"一直走直到找到出口"）仍可能在 LLM 不设 `target_position` 时失效。

2. **确定性规则覆盖有限**
   - 当前已有超凡行动、禁止行动、力量 vs 重量、身体宽度 vs 通道宽度、开锁技能 vs 锁难度等系统规则预判；
   - 但规则匹配仍偏启发式，复杂语义约束仍依赖 LLM 判断；
   - 规则预判只作为 LLM 输入，不是最终裁决。

3. **概率检定仍较基础**
   - `uncertain` + `requires_roll` 已由 Python 侧执行随机检定；
   - 但还没有角色属性、难度等级、优势/劣势、重试惩罚等完整检定系统。

4. **自动化测试覆盖已大幅提升，但集成测试仍缺失**
   - 纯函数测试已覆盖 118 个用例：JSON 解析、Prompt 模板加载与渲染、配置校验、数据模型默认值、规则预判（能力/物理/技能）、状态应用（玩家/NPC/物品/对话/情绪/检定）、属性更新、世界规则注入、UI 渲染、初始化文件、游戏时间和事件压缩；
   - 但还没有 mock LLM 的完整 tick 集成测试和 Prompt 输出样例测试。

5. **Prompt 和 schema 仍需收敛**
   - LLM 输出可能出现字段格式波动；
   - 当前靠兼容逻辑兜底，后续需要更严格的输出约束和测试样例。

## 近期待开发工作

1. **扩展确定性规则系统** — 将启发式文本匹配逐步替换为更明确的 action/object/location schema；增加门、容器、隐藏物体、视线遮挡等规则；增加规则测试样例库。

2. **完善检定系统** — 引入难度等级、角色属性、优势/劣势、重试惩罚等完整检定机制；将检定结果写入事件日志和角色记忆。

3. **补齐集成测试** — 在现有 118 个纯函数测试基础上，增加 mock LLM 完整 tick 集成测试、Prompt 输出样例测试、save/load CLI 行为测试。

4. **Prompt 与 schema 收敛** — 为常见行动建立固定示例库；减少 LLM 输出字段格式波动；明确 `PlayerAction`、`PhysicsOutcome` 与 `AttributeUpdateResolution` 的职责边界。

5. **支持更多 LLM 后端的针对性适配** — 当前依赖 OpenAI 兼容协议；对非 OpenAI 兼容的本地模型（如直接调用 transformers）需要增加适配层。

## 远期目标

- 更完整的多 Agent 系统（Agent 间协商、冲突消解、层级决策）；
- 长期角色记忆与知识图谱（跨会话持久化、记忆衰减、错误记忆）；
- 角色关系网络与目标冲突（三角关系、联盟、背叛、秘密）；
- 更严格的世界状态 schema（物理尺寸、材质属性、视线遮挡等系统化）；
- 事件溯源和 replay（从初始状态完整回放任意时间线）；
- Web UI（地图渲染、角色面板、物品栏、事件时间线、关系图）；
- Prompt 评估用例与回归测试框架；
- CI 与自动化测试流水线。

## 协作者快速索引

| 目标 | 入口文件 |
|---|---|
| 启动游戏 | `src/main.py` |
| 修改主循环 | `src/main.py` |
| 修改 tick 管道 | `src/graph/game_graph.py` |
| 修改全局状态结构 | `src/graph/game_state.py` |
| 修改初始化流程 | `src/agents/init.py` |
| 修改结构化输出解析 | `src/llm/parser.py` |
| 修改数据模型 | `src/models/` |
| 修改 LLM 配置 | `config/simulation.yaml` |
| 修改 Prompt | `prompts/*.j2` |
| 修改终端 UI | `src/ui/` |
| 修改确定性规则 | `src/game/rules.py`, `src/game/state_apply.py` |
| 修改 CLI 状态显示 | `src/ui/status.py` |
| 编写/使用初始化文件 | `config/init_test.yaml` |
| 查看接口规范 | `docs/game-flow-interfaces.md` |
| 查看协作约定 | `CONTRIBUTING.md` |
