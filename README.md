# 基于 LLM Agent 的互动模拟游戏

本工作区旨在实现一个由多个 LLM Agent 协同驱动的互动模拟游戏。游戏世界由结构化状态维护，非玩家角色会根据自身设定和当前世界状态做出行为，物理 Agent 会推演行为造成的环境变化，玩家感官 Agent 再把世界真实状态过滤为玩家可感知的信息。

项目当前处于**可运行原型阶段**：已经具备命令行交互、初始化对话或文件开局、玩家输入结构化与潜意识处理、行动可行性判断、多角色并发行为决策、物理变化推演、玩家感官输出和基础状态维护能力。

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

## 当前状态

当前代码已经可以运行一个 CLI 原型：

- 通过初始化对话或 `--init-file` 参数从 YAML 文件直接开局；
- 玩家自然语言输入被结构化为 `PlayerAction`，支持模糊表达细化和可选潜意识修正；
- 行动可行性节点判断玩家行动在当前世界和能力约束下是否可行；
- NPC 根据性格、记忆、上下文和结构化玩家行动并发产生行动；
- 物理 Agent 根据玩家和 NPC 行动推演环境变化；
- 感官 Agent 输出玩家可感知信息，并反馈"玩家角色实际做了什么"；
- 玩家可以输入自然语言动作推动下一回合。

当前仍不是完整游戏产品，很多系统还处于原型阶段，详见“当前限制”。

## 快速开始

### 环境要求

- Python >= 3.12
- uv 管理的虚拟环境
- DeepSeek API Key

### 安装依赖

```bash
uv pip install -e .
```

### 配置环境变量

复制 `.env.example` 为 `.env`，并填入真实 API Key：

```bash
copy .env.example .env
```

`.env` 内容示例：

```env
DEEPSEEK_API_KEY=sk-your-key-here
```

### 启动游戏

```bash
python -m src.main
```

可用命令：

- `/quit` 或 `/exit`：退出游戏；
- `/help`：显示帮助。

### 从初始化文件直接开局

跳过对话初始化，使用预编写的 YAML 文件直接启动：

```bash
python -m src.main --init-file config/init_test.yaml
```

初始化文件格式参见 [`config/init_test.yaml`](config/init_test.yaml)（蔷薇庄园场景，含完整注释）。

## 代码主要任务

本项目代码主要负责：

1. 通过初始化 Agent 创建初始世界，或从 YAML 文件直接加载；
2. 将玩家自然语言输入结构化为 `PlayerAction`，支持模糊表达细化和可选的潜意识/人设修正；
3. 判断结构化玩家行动在当前世界中的可行性（能力约束、物理约束、技能检定）；
4. 维护玩家、NPC、物体、地点、环境等状态；
5. 驱动 NPC 根据性格、记忆、环境和结构化玩家行动做出行动；
6. 使用物理 Agent 推演玩家和角色行动造成的物理变化；
7. 将世界真实状态过滤成玩家可感知的信息，并反馈"玩家角色实际做了什么"；
8. 通过 CLI 与玩家交互。

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
  ↓
sensory_filter          ← 生成玩家感知 + 自行动反馈
  ↓
END
```

节点说明：

- `player_intent_process`：将玩家自然语言输入转成结构化 `PlayerAction`，补全模糊表达，可选应用潜意识规则；
- `player_action_resolve`：判断行动在当前世界中的可行性（`allowed`/`blocked`/`uncertain`），考虑玩家能力、物理约束和技能水平；
- `characters_all_decide`：使用 `asyncio.gather()` 并发生成所有 NPC 的行动意图；
- `physics_resolve`：根据玩家和 NPC 行动推演物理结果；
- `state_apply`：用确定性 Python 逻辑应用状态变化；
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

### 接口文档

- `docs/game-flow-interfaces.md`

记录状态契约、节点输入输出、数据模型、Prompt 和存档格式的接口规范。修改相关代码时应同步更新该文档。

### UI 层

- `src/ui/cli.py`
- `src/ui/renderer.py`

使用 Rich 实现终端交互和玩家感官输出。

## 已完成开发工作

当前已经完成：

- 项目依赖配置；
- Pydantic 数据模型（含玩家潜意识、能力约束、物理数据、语言范例）；
- YAML 配置加载与 Pydantic 校验；
- Jinja2 Prompt 模板（11 个模板，覆盖初始化、玩家意图、可行性、角色、物理、感官全链路）；
- DeepSeek 接入；
- Prompt-based JSON 结构化解析；
- 初始化 Agent（对话式 + 文件式）；
- LangGraph tick 管道（6 节点，含玩家输入处理与行动可行性判断）；
- 玩家输入结构化（`player_intent_process`）——模糊表达细化、可选潜意识修正；
- 玩家行动可行性判断（`player_action_resolve`）——能力约束、物理约束、技能检定预留；
- NPC 行为并发生成（`asyncio.gather()`）；
- 物理结果生成（同时处理玩家与 NPC 行动）；
- 基础状态应用（物体移动、破坏、状态变化）；
- 玩家感官过滤 + 自行动反馈（"你做了什么"黄色面板）；
- LangGraph 内部状态 TypedDict 重构（图内 dict，边界 Pydantic）；
- 单文件 YAML 直接开局（`--init-file`）；
- Rich CLI（含"你做了什么"和"你感知到的"双面板渲染）；
- 接口规范文档（`docs/game-flow-interfaces.md`）；
- `CONTRIBUTING.md` 接口维护约定；
- 多轮运行中发现的问题修复，包括：
  - LLM 输出 dict/list 格式波动；
  - object type 扩展；
  - `GameState` 导入缺失；
  - 角色节点未执行导致感知输出重复；
  - 物体 `state` 为字符串导致状态更新失败。

## 当前限制

当前实现仍有以下限制：

1. **状态应用仍较基础**
   - 已支持物体移动、破坏、状态变化；
   - 角色位置更新、库存变化、关系数值变化、对话后果等还未完整落地；
   - 玩家行动结果的状态应用（如移动、拾取）尚未完全接入 `state_apply`。

2. **玩家行动可行性完全依赖 LLM 判断**
   - `player_action_resolve` 目前由 LLM 判断 `allowed`/`blocked`/`uncertain`；
   - 尚无 Python 侧的确定性规则校验（如 `body_width > door_width → blocked`）；
   - LLM 可能对同一约束在不同回合给出不一致判断。

3. **概率检定（roll）尚未实现**
   - `uncertain` 行动已记录 `success_probability` 和 `requires_roll`；
   - 但实际随机检定逻辑未实现，当前即使 `requires_roll=true` 也不会执行 roll。

4. **调试信息仍直接显示在 UI 中**
   - 最近事件日志目前用于开发调试；
   - 后续应增加 debug 开关。

5. **缺少自动化测试套件**
   - `pyproject.toml` 已配置 pytest；
   - 但测试文件尚未补齐。

6. **存档/读档未实现**
   - `/save` 目前只是帮助中提到，尚无实际功能。

7. **Prompt 和 schema 仍需收敛**
   - LLM 输出可能出现字段格式波动；
   - 当前靠兼容逻辑兜底，后续需要更严格的输出约束和测试样例。

8. **NPC Prompt 尚未消费语言表达范例**
   - `CharacterState.speech_examples` 字段已定义，YAML 可配置；
   - 但 `character_system.j2` 尚未注入此字段，NPC 语言风格仍仅依赖 personality 描述。

## 近期待开发工作

建议优先完成：

1. **增强状态应用系统**
   - 支持玩家和 NPC 位置移动；
   - 支持物品拾取、放下、使用；
   - 支持角色 `current_action` 更新；
   - 支持角色关系和记忆变化。

2. **Python 侧行动可行性确定性校验**
   - 为物理尺寸约束（如身体宽度 vs 门宽）增加确定性规则；
   - 为技能检定增加真实的 `random < skill_level` 判断；
   - 保留 LLM 判断作为复杂语义约束的兜底。

3. **NPC Prompt 消费语言表达范例**
   - 将 `CharacterState.speech_examples` 注入 `character_system.j2`；
   - 使 NPC 语言风格更一致、更可配置。

4. **调试输出开关**
   - 在配置中增加 debug 选项；
   - 普通玩家模式隐藏内部事件日志。

5. **补齐测试**
   - 测试 `generate_structured()`；
   - 测试 `init_file_to_game_state()`；
   - 测试 `state_apply()`；
   - 测试自行动摘要构建逻辑；
   - 增加 mock LLM 的完整 tick 集成测试。

6. **完善文件开局模式**
   - 支持从分散的 `config/world.yaml`、`config/player.yaml`、`config/characters/*.yaml` 直接开局（`--from-config`）；
   - 与当前单文件 `--init-file` 模式并存。

7. **存档与恢复**
   - 实现 `/save <name>` 和 `--load <path>`；
   - 图内状态已是 JSON-friendly dict，存档序列化成本低。

## 远期目标

远期目标是把当前 CLI 原型发展为一个稳定、可扩展、可协作开发的 LLM 模拟游戏框架。

包括：

- 更完整的多 Agent 系统；
- 长期角色记忆；
- 角色关系与目标冲突；
- 更严格的世界状态 schema；
- 事件溯源和 replay；
- 存档/读档；
- 确定性规则系统与 LLM 推演结合；
- Web UI；
- 地图、角色面板、物品栏、事件时间线；
- Prompt 评估用例；
- CI 与自动化测试。

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
| 修改示例世界/角色 | `config/world.yaml`, `config/characters/*.yaml` |
| 编写/使用初始化文件 | `config/init_test.yaml` |
| 查看接口规范 | `docs/game-flow-interfaces.md` |
| 查看协作约定 | `CONTRIBUTING.md` |
