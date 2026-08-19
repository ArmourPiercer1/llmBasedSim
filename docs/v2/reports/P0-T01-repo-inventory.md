# Task Package P0-T01: Repo-wide Inventory 权威盘点报告

- **任务 ID**: P0-T01
- **Phase**: Phase 0（冻结 v1 & 基线）
- **分支**: `architecture-v2`
- **生成日期**: 2026-08-20（Leader 更正：原稿误写为 2025-05-18）
- **环境**: Python 3.12.14 (`.venv/bin/python`)

---

## 1. 模块地图 (Module Map)

本项目 v1 采用 LangGraph 驱动的多 Agent 交互仿真架构。代码主要分布在 `src/`、`web/`、`prompts/`、`config/`、`public_start/` 及 `tests/` 目录。

### 1.1 `src/` 源码文件清单与职责

| 路径 | 行数 | 职责说明 |
|---|---|---|
| `src/__init__.py` | 0 | 顶层包标记文件 |
| `src/main.py` | 240 | CLI 命令行入口。负责加载配置、检查环境变量、初始化状态、构建 StateGraph、运行多轮异步主循环与 CLI 命令解析（如 `/save`, `/status`, `/see`, `/hear`, `/feel`） |
| `src/agents/__init__.py` | 3 | agents 模块导出 |
| `src/agents/init.py` | 378 | 游戏初始化逻辑。负责单文件 YAML (`whisperheads.yaml` 等) 与文件组（目录）YAML 的解析、补全坐标、构建初始 GameState，并包含可选的 LLM 初始场景生成 (`init_game`) |
| `src/config/__init__.py` | 3 | config 模块导出 |
| `src/config/loader.py` | 46 | 配置加载器 `ConfigLoader`，从 YAML 文件加载仿真运行配置 `SimulationConfig`、世界配置等 |
| `src/game/__init__.py` | 1 | game 模块导出 |
| `src/game/attributes.py` | 1100 | 属性引擎核心。包含属性标准化、自然分钟衰减/增长计算、确定性属性规则系统（timer 计时器、stage 阶段推进、compute 动态表达式求值、snapshot 快照、list_constraint 列表约束）、以及提示词属性摘要格式化与属性可见性过滤 |
| `src/game/condition_eval.py` | 450 | 规则条件表达式解析器。支持算术运算、比较运算、布尔逻辑 (`and`, `or`, `not`)、集合运算 (`in`, `subset`, `intersects`, `disjoint`)、随机函数 (`rand()`, `randint()`, `rand_range()`) 及嵌套 `if...else` 求值 |
| `src/game/deterministic_rules.py` | 163 | 确定性行动可行性规则。预置力量对比、体型狭窄通道、超常行动过滤、以及自定义正则/条件可行性规则匹配 |
| `src/game/rules.py` | 225 | 行动可行性判定核心适配层 `check_action_feasibility`。结合确定性规则与属性系统，评估玩家行动是 `allowed`、`blocked` 还是 `uncertain`（含成功率与掷骰判定） |
| `src/game/state_apply.py` | 253 | 确定性状态应用器。将物理结算和玩家/NPC 行动结果应用到角色位置、背包、物体状态，并处理好感度变更与事件日志压缩 (`compact_event_log`) |
| `src/game/tick_eval.py` | 512 | Tick 动态时间步长表达式求值器。支持根据玩家行动类型、NPC 耗时聚合函数（`min(npc_durations)` 等）和世界规则计算当前 Tick 耗时 |
| `src/graph/__init__.py` | 4 | graph 模块导出 |
| `src/graph/game_graph.py` | 952 | LangGraph `StateGraph` 定义与 11 个图节点实现（涵盖玩家意图、可行性、NPC 决策、Tick 计算、物理结算、状态更新、属性更新、感官过滤、叙事渲染及叙事后更新） |
| `src/graph/game_state.py` | 136 | `GameState` TypedDict 定义、时间推进工具函数 `advance_game_time`、瞬态字段清理 `strip_transient_state` 与每回合状态重置 `reset_tick_transients` |
| `src/llm/__init__.py` | 3 | llm 模块导出 |
| `src/llm/parser.py` | 104 | 结构化 LLM 输出生成器 `generate_structured`。基于 Pydantic 模型解析 LLM 返回的 JSON，包含 UTF-8 代理对清洗与容错修复提取 |
| `src/models/__init__.py` | 38 | 数据模型聚合导出 |
| `src/models/character.py` | 26 | NPC 状态模型 `CharacterState` 与性格特征模型 `CharacterPersonality` |
| `src/models/common.py` | 22 | 通用 3D 坐标模型 `Position` |
| `src/models/config.py` | 138 | 系统运行配置模型：`SimulationConfig`、`LLMConfig`、`AgentsConfig` 等 |
| `src/models/events.py` | 105 | 事件与动作核心模型：`ActionIntent`、`PlayerAction`、`PhysicsOutcome`、`PhysicsResolution`、`PlayerPercept`、`AttributeChange`、`AttributeUpdateResolution`、`NarrativeOutput`、`InitialGameConfig` |
| `src/models/player.py` | 46 | 玩家状态模型 `PlayerState`、感官与物理属性配置 `PlayerCapabilities`、`PlayerPhysicalProfile` |
| `src/models/world.py` | 43 | 世界实体模型：`Location`、`WorldObject`、`Environment`、`WorldState` |
| `src/prompts/__init__.py` | 3 | prompts 模块导出 |
| `src/prompts/loader.py` | 105 | Jinja2 模板加载器 `PromptLoader` 与规则提示词拼接工具 `build_rules_context`，内置物理与属性默认规则参考 |
| `src/ui/__init__.py` | 3 | ui 模块导出 |
| `src/ui/cli.py` | 54 | 终端交互与 Rich 文本渲染外壳 `GameUI` |
| `src/ui/renderer.py` | 237 | 终端感知与状态面板渲染（包含感官分类、玩家属性、调试事件展示） |
| `src/ui/status.py` | 32 | 终端每回合运行状态提示器 `TurnStatus` |
| `src/web/__init__.py` | 1 | web 模块导出 |
| `src/web/app.py` | 596 | WebUI 后端服务（基于 Python 标准库 `ThreadingHTTPServer`），提供 REST API（`/api/init-files`, `/api/game/start`, `/api/game/action`, `/api/game/status`, `/api/game/save`）与静态文件托管 |
| `src/web/main.py` | 124 | Web 服务启动脚本 CLI，处理参数解析与端口绑定 |

### 1.2 `web/` 前端文件清单与职责

| 路径 | 行数 | 职责说明 |
|---|---|---|
| `web/index.html` | 155 | WebUI 页面骨架，包含剧本选择、开场剧情展示、状态面板、感官视图、叙事流与输入框 |
| `web/static/app.js` | 770 | 前端单页应用逻辑，管理状态机、轮询 Turn 进度、渲染 Markdown 叙事、处理长任务中断与存档 |
| `web/static/styles.css` | 923 | WebUI 样式表（深色主题、响应式布局、状态徽章与动画） |

### 1.3 `prompts/` 模板清单与职责

| 路径 | 行数 | 职责说明 |
|---|---|---|
| `prompts/init_system.j2` | 27 | 初始场景生成的 System Prompt（用于从零生成世界和角色） |
| `prompts/player_intent_system.j2` | 24 | 玩家意图解析 System Prompt（引导模型理解模糊输入与潜意识） |
| `prompts/player_intent_user.j2` | 65 | 玩家意图解析 User Prompt（传入玩家输入、周围角色、物体、环境与最近事件） |
| `prompts/player_action_resolve_system.j2` | 10 | 玩家行动可行性判断 System Prompt |
| `prompts/player_action_resolve_user.j2` | 46 | 玩家行动可行性判断 User Prompt（注入确定性规则判定结果与角色属性） |
| `prompts/character_system.j2` | 76 | NPC 行动决策 System Prompt（注入性格、关系、动机与历史记忆） |
| `prompts/character_user.j2` | 60 | NPC 行动决策 User Prompt（传入位置、视线内物体/NPC、玩家行动） |
| `prompts/physics_system.j2` | 16 | 物理模拟 System Prompt（注入世界物理定律） |
| `prompts/physics_user.j2` | 59 | 物理模拟 User Prompt（传入各方行动意图、坐标与环境，计算物理反馈与碰撞） |
| `prompts/attribute_update_system.j2` | 32 | 属性语义变更 System Prompt（根据事件推断属性增减） |
| `prompts/attribute_update_user.j2` | 43 | 属性语义变更 User Prompt（传入当前所有实体属性与本轮事件） |
| `prompts/sensory_system.j2` | 55 | 玩家感官过滤 System Prompt（基于视听嗅触范围限制生成主观感官） |
| `prompts/sensory_user.j2` | 69 | 玩家感官过滤 User Prompt（结合自身行动、环境、属性变化生成感知流） |
| `prompts/narrative_system.j2` | 34 | 叙事文学润色 System Prompt（注入剧本风格要求） |
| `prompts/narrative_user.j2` | 45 | 叙事文学润色 User Prompt（输入感官结构化信息与上下文，产出最终小说级描述） |

### 1.4 `config/` 与 `public_start/` 清单

| 路径 | 行数 | 职责说明 |
|---|---|---|
| `config/simulation.yaml` | 23 | 默认仿真引擎配置（LLM 参数、并发配置、默认视听范围等） |
| `public_start/whisperheads.yaml` | 897 | 示例剧本《耳语岬》（克苏鲁/悬疑风，包含完整规则、NPC、复杂属性约束） |
| `public_start/murder.yaml` | 802 | 示例剧本《暴风雪山庄谋杀案》（侦探推理风） |
| `public_start/test_empty.yaml` | 154 | 最小测试空场景剧本 |

---

## 2. 调用链地图 (Call Graph & Execution Flow)

### 2.1 两个主入口

1. **CLI 入口 (`src/main.py`)**：
   - 加载 `config/simulation.yaml` 并初始化 `ChatOpenAI` 与 `PromptLoader`。
   - 通过 `load_init_file` / `init_file_to_game_state` 建立初始 `GameState`。
   - 调用 `build_game_graph` 编译 LangGraph 工作流。
   - 循环调用 `graph.ainvoke(state, config={"configurable": {"thread_id": ...}})`。
   - 渲染 `player_percept` 和 `narrative`，收集下一轮控制台输入。
2. **WebUI 入口 (`src/web/main.py` + `src/web/app.py`)**：
   - 启动 HTTP 线程服务器，单例维护当前 `GameSession`。
   - 前端发起 `/api/game/start` 触发剧本加载；发起 `/api/game/action` 提交玩家输入并触发一次异步 `graph.ainvoke`。
   - 通过 `WebTurnStatus` 提供执行阶段轮询。

### 2.2 端到端数据流与调用链

```text
[用户输入 / Web Action]
        │
        ▼
[main.py / app.py] ──> 设置 state["player_input"]，调用 ainvoke
        │
        ▼
[LangGraph: build_game_graph]
        │
        ├─ 1. player_intent_process (LLM)
        │      └─ prompts/player_intent_*.j2 ──> generate_structured(PlayerAction)
        │
        ├─ 2. player_action_resolve (混合: 规则 + LLM)
        │      ├─ src/game/rules.py::check_action_feasibility
        │      │    └─ src/game/deterministic_rules.py (力量/体型/自定义正则与条件)
        │      └─ prompts/player_action_resolve_*.j2 ──> generate_structured(PlayerAction)
        │
        ├─ 3. characters_all_decide (LLM 并发)
        │      └─ prompts/character_*.j2 ──> generate_structured(ActionIntent) × N
        │
        ├─ 4. tick_speed_resolve (确定性逻辑, 无 LLM)
        │      ├─ src/game/tick_eval.py::evaluate_tick_expression (解析 world_rules.tick_speed)
        │      └─ 动作耗时截断与 continuation 标记
        │
        ├─ 5. physics_resolve (LLM)
        │      └─ prompts/physics_*.j2 ──> generate_structured(PhysicsResolution)
        │
        ├─ 6. state_apply (确定性逻辑, 无 LLM)
        │      ├─ src/game/state_apply.py (apply_player_action, apply_npc_actions)
        │      ├─ 物体状态修改、位移变更、好感度更新、NPC 记忆追加
        │      └─ src/graph/game_state.py::advance_game_time (推进游戏内时间)
        │
        ├─ 7. natural_attribute_delta (确定性逻辑, 无 LLM)
        │      ├─ src/game/attributes.py::apply_natural_attribute_deltas (每分钟属性自增减)
        │      ├─ src/game/attributes.py::apply_deterministic_attributes (timer/stage/compute/snapshot/list_constraint)
        │      └─ 拆分 pre_narrative 与 deferred (post_narrative) 规则
        │
        ├──┬── 8. attribute_update (LLM 语义属性更新) ──> [END]
        │  │     └─ prompts/attribute_update_*.j2 ──> generate_structured(AttributeUpdateResolution)
        │  │
        │  └── 9. sensory_filter (LLM 感官过滤)
        │        └─ prompts/sensory_*.j2 ──> generate_structured(PlayerPercept)
        │               │
        │               ▼
        │        10. narrative_stylize (LLM 文学叙事润色)
        │               └─ prompts/narrative_*.j2 ──> generate_structured(NarrativeOutput)
        │                      │
        │                      ▼
        │        11. post_narrative_update (确定性逻辑, 无 LLM)
        │               ├─ 应用 deferred_natural_deltas 与 deferred_locked_rules
        │               └─ 写入下一轮生效的状态 ──> [END]
```

---

## 3. game_graph.py 11 个节点逐一拆解

图的整体拓扑结构：
- **线性主干**：`START` → `player_intent_process` → `player_action_resolve` → `characters_all_decide` → `tick_speed_resolve` → `physics_resolve` → `state_apply` → `natural_attribute_delta`
- **Fan-Out（分流）**：`natural_attribute_delta` 分发到两个分支：
  1. 分支 A: → `attribute_update` → `END`
  2. 分支 B: → `sensory_filter` → `narrative_stylize` → `post_narrative_update` → `END`
- **说明**：分支 A 与 分支 B 在 LangGraph 中并发执行，分别在节点末端汇入 `END`。

### 节点详细规范表

| 节点名称 | 读取 State 字段 | 产出 State 字段 | 是否调用 LLM | 使用 Prompt 模板 | 输出 Pydantic 模型 | 失败降级策略 | 节点性质 |
|---|---|---|---|---|---|---|---|
| **1. player_intent_process** | `player_input`, `action_continuation`, `player`, `characters`, `objects`, `locations`, `environment`, `event_log` | `player_action`, `action_continuation`, `event_log` | **是** (若无输入或仅命令则跳过) | `player_intent_system.j2`, `player_intent_user.j2` | `PlayerAction` | 返回 `player_action=None`，记录错误事件日志，忽略本轮输入 | LLM 语义推断 |
| **2. player_action_resolve** | `player_action`, `player`, `objects`, `locations`, `world_rules`, `environment` | `player_action`, `action_continuation`, `event_log` | **是** (前置规则判定) | `player_action_resolve_system.j2`, `player_action_resolve_user.j2` | `PlayerAction` | 保留原始 `player_action`，跳过 LLM 综合判断 | 混合 (规则 + LLM) |
| **3. characters_all_decide** | `characters`, `character_positions`, `locations`, `objects`, `environment`, `player_action` | `action_intents`, `event_log` | **是** (对每个 NPC `asyncio.gather` 并发) | `character_system.j2`, `character_user.j2` | `ActionIntent` | 单个 NPC 失败则返回 `None` 并记录错误，不影响其他 NPC | LLM 决策 |
| **4. tick_speed_resolve** | `player_action`, `action_intents`, `ticks_per_game_minute`, `world_rules`, `player` | `tick_duration_minutes`, `player_action`, `action_intents`, `action_continuation`, `event_log` | **否** | 无 | 无 (内部 dict 处理) | 表达式求值失败降级为 default 分钟数 | **确定性逻辑** |
| **5. physics_resolve** | `world_rules`, `objects`, `character_positions`, `action_intents`, `player_action`, `environment`, `tick_duration_minutes` | `physics_outcomes`, `event_log` | **是** | `physics_system.j2`, `physics_user.j2` | `PhysicsResolution` | 产出空的 `physics_outcomes=[]`，记录物理失败日志 | LLM 物理仿真 |
| **6. state_apply** | `character_positions`, `objects`, `characters`, `physics_outcomes`, `player`, `player_action`, `action_intents`, `event_log`, `tick_duration_minutes`, `ticks_per_game_minute`, `game_time`, `environment`, `tick` | `character_positions`, `objects`, `characters`, `player`, `tick`, `player_input`, `game_time`, `environment`, `event_log` | **否** | 无 | 无 (内部状态更新) | 纯 Python 计算，无降级 | **确定性逻辑** |
| **7. natural_attribute_delta** | `player`, `characters`, `tick_duration_minutes`, `world_rules` | `player`, `characters`, `event_log`, `attribute_deltas`, `deferred_natural_deltas`, `deferred_locked_rules` | **否** | 无 | 无 (计算前后 diff) | 纯 Python 计算，无降级 | **确定性逻辑** |
| **8. attribute_update** | `player`, `characters`, `world_rules`, `player_action`, `action_intents`, `physics_outcomes`, `event_log`, `environment`, `game_time` | `player`, `characters`, `event_log` | **是** (若无属性定义则直接跳过) | `attribute_update_system.j2`, `attribute_update_user.j2` | `AttributeUpdateResolution` | 忽略本轮 LLM 属性更新，仅保留错误日志 | LLM 语义属性 |
| **9. sensory_filter** | `player`, `objects`, `character_positions`, `characters`, `player_action`, `event_log`, `environment`, `game_time`, `attribute_deltas` | `player_percept`, `event_log` | **是** | `sensory_system.j2`, `sensory_user.j2` | `PlayerPercept` | 降级为默认感知结构（"你暂时无法感知周围环境"） | LLM 感知过滤 |
| **10. narrative_stylize** | `player_percept`, `narrative_style`, `player`, `environment`, `narrative_history`, `game_time`, `tick` | `player_percept`, `narrative_history`, `event_log` | **是** | `narrative_system.j2`, `narrative_user.j2` | `NarrativeOutput` | 将 `player_percept["summary"]` 作为叙事回填，记入历史 | LLM 叙事风格化 |
| **11. post_narrative_update** | `deferred_natural_deltas`, `deferred_locked_rules`, `player`, `characters`, `tick_duration_minutes` | `player`, `characters`, `deferred_natural_deltas`, `deferred_locked_rules`, `event_log` | **否** | 无 | 无 (重置 deferred 列表) | 纯 Python 计算，无降级 | **确定性逻辑** |

---

## 4. GameState 字段盘点 (`src/graph/game_state.py`)

`GameState` 是整个仿真流水线的单一体状态树（TypedDict）。按生命周期与更新语义分类如下：

### 4.1 持久化字段 (Persistent State)
游戏存盘（`/save`）和跨 Tick 演化所需的核心世界数据：
- `tick`: 当前回合数（`int`）
- `max_ticks`: 最大回合上限（`int`）
- `game_phase`: 当前游戏阶段（`str`，如 `"exploring"`, `"ended"`）
- `world_name`: 世界名称（`str`）
- `world_description`: 世界全局背景设定（`str`）
- `locations`: 地点字典集合（`dict[str, Location]`）
- `objects`: 场景内可交互物体集合（`dict[str, WorldObject]`）
- `character_positions`: 角色坐标索引（`dict[str, Position]`）
- `environment`: 环境变量（时间、天气、光照、温度等 `dict[str, Any]`）
- `characters`: 所有 NPC 状态字典（`dict[str, CharacterState]`，包含属性、记忆、背包、好感度）
- `player`: 玩家自身状态（`dict[str, Any]`，包含属性、能力、外貌、背包）
- `world_rules`: 世界物理/属性/确定性规则集（`dict[str, Any]`）
- `narrative_style`: 叙事风格配置（`dict[str, str]`）
- `game_time`: 游戏内世界时间（`dict[str, int]`，含 `day`, `hour`, `minute`）
- `ticks_per_game_minute`: 时间缩放率（`float`）

### 4.2 瞬态字段 (Transient State)
每轮 Tick 结束后通过 `strip_transient_state` 清除，或在回合启动时通过 `reset_tick_transients` 重置：
- `player_input`: 玩家本轮原始输入文本（`str | None`）
- `player_action`: 意图/可行性解析后的动作对象（`dict | None`）
- `physics_outcomes`: 本轮物理模拟结算产生的事件列表（`list[dict]`）
- `player_percept`: 本轮感官过滤生成的玩家主观感官与渲染文本（`dict | None`）
- `attribute_deltas`: 本轮自然变化的属性差异快照（`list[dict]`）
- `deferred_natural_deltas`: 延迟到叙事渲染后生效的自然属性变化（`list[dict]`）
- `deferred_locked_rules`: 延迟到叙事渲染后生效的锁定属性规则（`list[dict]`）
- `tick_duration_minutes`: 本轮实际推进的世界分钟数（`float`）
- `action_continuation`: 长任务（如多回合移动、持续搜查）的剩余状态快照（`dict | None`）

### 4.3 Reducer 累加字段 (Annotated[list, operator.add])
在 LangGraph 图执行期间，多个节点写入时自动执行列表追加合并：
- `action_intents`: `Annotated[list[dict], operator.add]`，所有 NPC 的意图动作列表（由 `characters_all_decide` 写入）
- `narrative_history`: `Annotated[list[dict], operator.add]`，全剧历史叙事文本快照流（由 `narrative_stylize` 追加）
- `event_log`: `Annotated[list[str], operator.add]`，全局调试与因果事件日志（各节点均向其追加形如 `[玩家意图]...`、`[物理]...`、`[属性]...` 的日志行，并在 `state_apply` 中按需执行滑动窗口压缩）

---

## 5. 测试套件盘点 (Test Suite Inventory)

仓库现有 17 个测试文件，共计 **368 个测试用例**（全部通过，运行耗时约 0.6s）。

| 测试文件 | 用例数 | 覆盖的主要模块 | 核心覆盖内容 |
|---|---|---|---|
| `tests/test_attributes.py` | 84 | `src/game/attributes.py` | 属性自然衰减、clamp 极值限制、锁定属性跳过、条件求值（集合/逻辑/算术/随机数）、timer/stage/compute/snapshot/list_constraint 规则、pre/post 延迟机制 |
| `tests/test_complications.py` | 15 | `src/game/attributes.py` | 复杂多规则级联情景（如产科复杂并发症状态推导、宫缩、指征列表约束） |
| `tests/test_condition_eval.py` | 42 | `src/game/condition_eval.py` | 规则 DSL 语法解析、比较、逻辑与或非、集合包含/子集/相交、随机函数、异常语法处理 |
| `tests/test_config_loader.py` | 4 | `src/config/loader.py` | 仿真配置、世界配置、玩家与 NPC 数据 YAML 加载 |
| `tests/test_init_and_state.py` | 8 | `src/agents/init.py`, `src/graph/game_state.py` | 单文件 YAML 解析、多文件目录解析、瞬态状态清除 round-trip、世界规则与叙事风格跨保存持久化 |
| `tests/test_init_extra.py` | 8 | `src/agents/init.py` | 玩家出生点推断逻辑、连接关系格式标准化、时间解析容错 |
| `tests/test_long_task.py` | 2 | `src/graph/game_graph.py` (部分) | 长任务 `/c` 延续与非 `/c` 输入打断逻辑 |
| `tests/test_models.py` | 20 | `src/models/*` | 所有 Pydantic 数据模型的默认值与序列化校验 |
| `tests/test_parser.py` | 13 | `src/llm/parser.py` | Markdown 代码块提取 JSON、Unicode 代理对清洗、容错回退 |
| `tests/test_phase4.py` | 7 | `src/game/state_apply.py`, `src/graph/game_state.py` | NPC 移动位移、对话目标跟踪、好感度增减、世界时间推进、日志压缩 |
| `tests/test_prompts.py` | 25 | `src/prompts/loader.py` | 全部 15 个 Jinja2 模板渲染测试与规则注入辅助函数 `build_rules_context` 校验 |
| `tests/test_renderer.py` | 10 | `src/ui/renderer.py` | 终端 UI 渲染函数、属性展示、感官分类显示 |
| `tests/test_rules.py` | 26 | `src/game/rules.py`, `src/game/deterministic_rules.py` | 力量对比规则、通道体型规则、超常动作过滤、自定义正则/条件可行性匹配优先级 |
| `tests/test_state_apply.py` | 17 | `src/game/state_apply.py` | 玩家与 NPC 行动的状态变更、掷骰成功与失败分支、背包拾取与消耗 |
| `tests/test_tick_eval.py` | 51 | `src/game/tick_eval.py` | Tick 表达式算术/比较/聚合函数（`min`, `max`, `avg`）、多分支 `if/else` 求值 |
| `tests/test_tick_speed.py` | 23 | `src/game/tick_speed.py` (集成) | 默认 NPC 时间聚合策略、Tick 表达式结合、动作耗时截断与 continuation 拆分 |
| `tests/test_webui.py` | 13 | `src/web/app.py` | WebUI 快照数据字段、剧本列表发现、绝对路径安全校验、`WebTurnStatus` 状态快照 |
| **总计** | **368** | - | - |

### 5.1 明显测试缺口 (Identified Gaps)
1. **`game_graph.py` 完整 11-Node 端到端 Characterization 缺口**：
   - 现有测试多为底层确定性单元测试，缺乏对 `game_graph.py` 中 11 个节点的隔离 characterization 测试（特别是节点输入/输出 schema 契约、mock LLM 下的图执行分支、Fan-out 并发与异常降级行为）。
2. **`main.py` CLI 主循环缺少集成覆盖**：
   - CLI 交互命令（如 `/save`, `/status`, `/see`, `/feel`, `/stop`）缺乏完整的自动化测试覆盖。
3. **`web/app.py` 缺乏 HTTP 端到端真实请求测试**：
   - 现有的 `test_webui.py` 主要测试工具函数与辅助类，缺少多回合并发 `/api/game/action` 的端到端 HTTP 集成测试。

---

## 6. 配置与内容格式规范 (Configs & Content Schemas)

### 6.1 `config/simulation.yaml`
```yaml
simulation:
  max_ticks: 100            # 最大回合上限
  tick_delay_ms: 100        # 回合间隔延迟
  log_level: "INFO"         # 日志级别
  debug: false              # 调试模式开关

llm:
  provider: "deepseek"      # LLM 供应商
  model: "deepseek-chat"    # 模型名称
  api_key_env: "DEEPSEEK_API_KEY" # 环境变量名称
  base_url: "https://api.deepseek.com" # API base URL
  temperature: 0.7          # 采样温度
  max_tokens: 16384         # 最大输出 Token

agents:
  character:
    memory_size: 50         # NPC 记忆窗口大小
    concurrent: true        # NPC 决策是否并发
  physics:
    chain_reaction_depth: 3 # 物理连锁反应深度
  sensory:
    default_sight_range_m: 50.0   # 默认视距 (米)
    default_hearing_range_m: 100.0 # 默认听距 (米)
```

### 6.2 剧本 Init YAML Schema
支持两种组织格式：
1. **单文件格式 (`public_start/*.yaml`)**：所有字段集中在一个 YAML 文件。
2. **文件组（目录）格式**：一个目录下包含 `world.yaml`（必需），以及可选的 `player.yaml`、`characters/*.yaml`、`rules.yaml` 等。

#### 核心 Top-Level 键结构
- `world`:
  - `name`: 世界名称（`str`）
  - `description`: 描述（`str`）
  - `locations`: 地点映射字典（包含 `name`, `description`, `objects`, `connections`, `coordinates`）
  - `objects`: 场景物体映射（包含 `name`, `description`, `position`, `portable`, `state`, `weight_kg`, `size_cm`）
  - `environment`: 环境状态（`time_of_day`, `weather`, `temperature_c`, `visibility`, `indoor`）
- `player`:
  - `name`, `persona`, `position`, `inventory`
  - `capabilities`: `sight_range_m`, `hearing_range_m`, `dark_vision`, `skills`
  - `physical_profile`: `body_width_cm`, `body_height_cm`, `strength_kg`, `max_carry_kg`
  - `attributes`: 属性字典（支持数值与枚举）
- `characters`: 列表形式，每个 NPC 包含 `id`, `name`, `persona`, `position`, `personality`, `speech_examples`, `relationships`, `attributes`, `memory`, `inventory`。
- `starting_scene_description`: 开场剧本背景文本。
- `game_time`: `{day: 1, hour: 8, minute: 0}`
- `ticks_per_game_minute`: 时间缩放因子。
- `world_rules`:
  - `physics`: 物理提示词定制（`disable_rules`, `custom_rules`）
  - `attribute`: 属性推断提示词定制
  - `deterministic`: 确定性可行性规则列表（包含 `id`, `match_action`, `match_condition`, `outcome`, `probability`, `reason`）
  - `locked_attributes`: 确定性属性求值规则列表（包含 `rule_type: timer|stage|compute|snapshot|list_constraint`, `update_position: pre_narrative|post_narrative` 等）
  - `tick_speed`: Tick 耗时计算规则（`default`, `min_minutes`, `max_minutes`, `rule` 表达式）
- `narrative_style`:
  - `style_description`: 文学风格指引（如克苏鲁、侦探、高魔奇幻）
  - `style_example`: 叙事范例文本

### 6.3 存档 JSON 格式 (`saves/<name>.json`)
通过 `strip_transient_state` 过滤后导出的纯净 `GameState` JSON 文件，包含除 `player_input`, `player_action`, `physics_outcomes`, `player_percept`, `attribute_deltas`, `deferred_*` 之外的全部字段，可被 CLI 或 WebUI 原样反序列化恢复游戏。

---

## 7. 外部依赖用途分析 (External Dependencies)

| 依赖包 | 声明版本 | 代码中实际使用位置 | 核心用途 |
|---|---|---|---|
| `langchain` / `langchain-core` | `>=0.3.0` | `src/graph/game_graph.py`, `src/agents/init.py`, `src/llm/parser.py` | 使用 `HumanMessage`, `SystemMessage`, `BaseMessage` 构造 LLM 消息序列 |
| `langgraph` | `>=0.4.0` | `src/graph/game_graph.py` | 驱动核心游戏循环：`StateGraph`, `START`, `END`, `InMemorySaver` |
| `langchain-openai` | `>=0.3.0` | `src/main.py`, `src/web/app.py`, `src/graph/game_graph.py`, `src/agents/init.py`, `src/llm/parser.py` | 实例化 `ChatOpenAI` 客户端，对接兼容 OpenAI 接口的 LLM 提供商（如 DeepSeek） |
| `pydantic` | `>=2.0` | `src/models/*.py`, `src/llm/parser.py`, `src/graph/game_state.py` | 全局数据建模、契约校验、JSON Schema 导出与 `generate_structured` 结构化解析 |
| `pyyaml` | `>=6.0` | `src/config/loader.py`, `src/agents/init.py` | 解析 `simulation.yaml` 配置文件与剧本 Init YAML 文件 |
| `jinja2` | `>=3.1` | `src/prompts/loader.py` | 编译与动态渲染 `prompts/*.j2` 模板 |
| `structlog` | `>=24.0` | `src/main.py`, `src/llm/parser.py` | 结构化系统日志记录 |
| `rich` | `>=13.0` | `src/main.py`, `src/ui/cli.py`, `src/ui/renderer.py` | 命令行终端彩色输出、格式化 Panel、Table 渲染 |
| `python-dotenv` | `>=1.0` | `src/main.py`, `src/web/app.py` | 从根目录 `.env` 加载环境变量（如 API Key） |

---

## 8. v2 迁移分类 (v1 → v2 Migration Categorization)

对照 `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md` §43 规范，将 v1 现有主要模块分类如下：

| 文件 / 模块 | 迁移分类 | 判定理由与 v2 目标 |
|---|---|---|
| `src/game/condition_eval.py` | **reusable** | 规则 DSL 解析引擎设计完善、无外部 LLM 依赖、测试充分，可直接作为 v2 规则求值器或迁移至 `src/engine/modules/rules/` |
| `src/game/tick_eval.py` | **reusable** | 纯确定性时间表达式解析器，可直接复用到 v2 的 `Scheduler` / `TimePolicy` 模块 |
| `src/prompts/loader.py` & `prompts/*.j2` | **migrate-with-changes** | Jinja2 模板分层思想保留，但提示词内容需适配 v2 的 Epistemic boundary（认知边界隔离）与 Effect Proposal 格式，迁移至 `src/prompts/assembler.py` |
| `src/game/attributes.py` | **migrate-with-changes** | 属性自然衰减与 timer/stage/compute 等规则算法成熟，但需要从直接修改 dict 改写为产生 `ProposedEffect`，进入 Transaction Reducer |
| `src/game/deterministic_rules.py` & `rules.py` | **migrate-with-changes** | 规则检查思想保留，但需重构成 v2 的 `ActionValidation` / `ConflictResolver` 管道 |
| `src/models/*.py` | **migrate-with-changes** | 数据契约思想保留，但 v1 混合了 RPG 专属字段与引擎状态；v2 需拆解为 Core Primitives (`EntityId`, `ProposedEffect`, `DomainEvent`) 与 RPG 官方模块 |
| `src/llm/parser.py` | **migrate-with-changes** | 容错提取与结构化解析需扩展为 provider-neutral 的 `StructuredInference`，支持模型路由与异步失效保护 |
| `src/ui/renderer.py` & `cli.py` | **migrate-with-changes** | Presentation 分离思想保留，迁移至 `src/adapters/cli/`，作为纯只读观察者 |
| `src/config/loader.py` & `agents/init.py` | **migrate-with-changes** | YAML 加载思想保留，需重构为 `ProjectIR` 加载与 Schema 验证器 |
| `src/graph/game_graph.py` | **obsolete-rewrite** | **必须废弃重写**。全局固定 11 节点流水线无法支持动态 Scheduler、多时间尺度、非全局 NPC 轮询及实时中断 |
| `src/graph/game_state.py` | **obsolete-rewrite** | **必须废弃重写**。大杂烩 TypedDict 违背状态隔离原则，v2 需彻底解耦为 `WorldState`（实体/组件/权威数据）与 `RuntimeState`（调度队列/会话数据） |
| `src/game/state_apply.py` | **obsolete-rewrite** | **必须废弃重写**。直接就地对 dict 执行状态修改违反 Kernel Invariant（无 raw mutation），必须由原子 Transaction + Reducer 接管 |
| `src/web/app.py` & `web/static/app.js` | **obsolete-rewrite** | **必须重写**。全局单例 Session 无法支持多会话与分支调试，v2 需在 `src/adapters/web/` 下建立标准 `SessionManager` |

---

## 9. 风险与不确定性清单 (Risks & Uncertainties)

1. **状态修改无写屏障（Raw Mutation 惯性）**：
   - v1 中多处节点和辅助函数直接深度复制并修改 dict。v2 引入 `ProposedEffect` → `Authority` → `Validation` → `Reducer` 链条后，需要彻底杜绝任何绕过 Reducer 的就地修改。
2. **LangGraph 隐式上下文依赖与异步调度风险**：
   - v1 的 NPC 决策是在同一个 Tick 内基于静态快照全部并发触发；v2 转为事件驱动/时间步长驱动后，需要严格处理 **Stale Proposal**（当 NPC 耗时决策返回时，世界状态已被玩家动作改变）。
3. **属性系统 DSL 的兼容性与边界情况**：
   - `attributes.py` 和 `condition_eval.py` 中有大量针对特定剧本（如《耳语岬》复杂医学/神智状态）定制的语法规则，重构到 Module 体系时需确保 84+ 个属性测试 100% 行为等价。
4. **认知边界 (Epistemic Boundary) 提示词重构挑战**：
   - v1 的 NPC prompt (`character_user.j2`) 直接传入了完整的 `player_action` 和全局场景对象；v2 必须严格依据 NPC 的感知能力和位置过滤 Context，防止 NPC "全知全能"。
5. **Web 会话单例状态迁移**：
   - v1 `web/app.py` 为全局单一游戏实例，无法支持多标签页或并行仿真，重构成 SessionManager 时需保证向下兼容现有简单 WebUI 接口。

---

*报告编制完成，供下游任务包 P0-T03（Characterization Tests）、P0-T04（Reference Transcripts）和 P0-T06（文档整理）参考使用。*

---

## Leader 核对附注（2026-08-20）

Leader 对报告关键事实做了源码交叉核对，下游任务包以本附注为准：

1. **world_rules 键名更正**：§6.2 中 `world_rules.physics` 写的 `disable_rules` / `custom_rules` 有误。
   源码实际键名为 `disable`（int 列表）与 `append`（str 列表），见 `src/prompts/loader.py:53-54`
   （`build_rules_context` 只识别这两个键）。`deterministic` 子字段同样是 `disable` / `append`。
2. **locked_attributes 规则类型确认**：`src/game/attributes.py:928-932` 的分发表共 **5 种**
   规则类型：`timer`、`stage`、`snapshot`、`list_constraint`、`compute`（README 中"四种"的说法已过时，
   `compute` 为最近提交 f0a1052 新增）。
3. **已知 v1 缺陷（来自 P0-T02）**：`src/graph/game_graph.py:475` 存在 F821 未定义名称
   `fallback`（physics_resolve 节点在 state 缺 `tick_duration_minutes` 时触发，被 try/except 掩盖）。
   P0-T03 characterization 应覆盖该路径的当前行为（记录现状，不修复）。
4. 报告其余节点拆解、状态分类与迁移分类经抽查与源码一致；下游使用时若发现与源码冲突，以源码为准。
