# llmBasedSim — 基于 LLM Agent 的互动模拟游戏（双引擎仓库）

本仓库包含**两个引擎**：

| | **v1（冻结原型）** | **v2（主开发线）** |
|---|---|---|
| 代码 | `src/main.py`、`src/graph/`、`src/agents/`、`src/web/`、`web/` | `src/engine_v2/`（13 子包） |
| 架构 | LangGraph 11 节点 tick 管道 | 三平面（Authoring / Dev Control / Runtime）+ K1–K8 不变量 + revision/commit 内核 |
| 开局载体 | init 文件（`public_start/*.yaml` 单文件/文件组） | **v2 项目目录**（`game.yaml` + world/ + characters/ + …，见 `docs/v2/usage/project-authoring.md`） |
| 状态 | **冻结**：G0 门禁基线，可继续运行，不再演进（v1↔v2 零 import 互锁） | **活跃**：Phase 1–10 已收口（G0–G10 机械面 PASS，全量 3205/0），P11+ 进行中 |
| LLM | 运行时多节点直接调用 LLM | K4/K5：LLM 只是 Policy（提议者），权限与提交全在确定性引擎 |
| 入口 | `python -m src.main`（CLI）/ `python -m src.web.main`（WebUI） | Web 演示驱动（`scripts/v2_g10_acceptance.py`）；CLI/DSH 适配器 = P11+ |

**读法**：想跑/写 v2 → 下面 §1；想跑 v1 老游戏 → §2；想改
v2 代码 → `CONTRIBUTING.md` + `docs/v2/usage/`；LLM 协作者
简报 → `llm_readme.md`。

---

## 1. v2 引擎（`src/engine_v2`）

### 1.1 当前状态

- 分支 `architecture-v2`；全量测试 **3348 passed / 0 failed**
  （恒等式 3205 closure 基线 + 143 closure 增量：T1–T8 +103 /
  T9 +23 / P5-06b +1 / T11 E2E +16；G10 基线 3205 = 3142 G9 + 63 P10）；
- Phase 1–10 全部过门禁（`docs/v2/gates/G0…G10-*.md`；G10 人工
  面 S11 待判定，见 `docs/v2/gates/G10-test-acceptance-plan.md`）；
- **runtime closure 完成**（production game path：YAML 项目 + 受信
  Python 扩展 → 权威世界 → 五相位 tick → 单一提交管道 → 场景视图；
  Gate C1–C9 9/9，见 `docs/v2/gates/runtime-closure-gate-report.md`）；
- 已建：Core Kernel、Scheduler/Action、Actor/Context/Space、
  LLM Runtime（provider-neutral 抽象）、Project Format / 9 官方
 模块 / 插件、WorldDynamics、Persistence/Replay/Devtools、
  Presentation/Web（会话 API + 确定性图像 backend）、
  Runtime 生产装配（`src.engine_v2.runtime.assemble_project` 单入口）；
- 未建（P11+ 承接）：CLI/DSH 适配器、零配置默认 LLM 部署、
  inspector/workbench 页面路由。

### 1.2 60 秒概念模型

```text
Authoring Plane        Development Control Plane      Runtime Plane
project/*.yaml ──load──▶ ProjectIR ──validate──▶ (llmsim validate)
       │                      │
       └── deployment.yaml（LLM 部署，K8 分离）
                             └──build_world──▶ WorldInstance ──▶ Session
                                                        tick → ActionProposal
                                                        → ProposedEffect
                                                        → Authority 裁决
                                                        → Commit（revision +1）
                                                        → ViewState 派生（叙事/图像/战术）
```

核心不变量（Spec 第 2 节，全部测试强制）：**K1** 单一权威状态 /
**K2** 禁止直接状态写入（只能 Action→Effect→Commit）/ **K3**
Authority 与 Commit 分离 / **K4** Prompt 不能定义世界权限 /
**K5** Agent 是 Policy 不是 Engine / **K6** Event 可追踪来源 /
**K7** 调度状态可检查 / **K8** Deployment 与 Game Project 分离。

状态五分离：WorldState / RuntimeState / BackendState /
TraceState / ViewState。没有 LLM 的世界照样 tick；有 LLM 的世界
里 LLM 也只能提议。

### 1.3 快速开始

```bash
cd /home/armourpiercer/projects/llmBasedSim

# ① 跑 v2 Web 演示（galgame 样例世界；确定性宿主，零 API Key）
PYTHONPATH=. .venv/bin/python scripts/v2_g10_acceptance.py --port 8000
#    → 打印 SESSION_ID=…；浏览器开 http://127.0.0.1:8000/ 填入会话 ID

# ② 一键验收（机械面 3205 + HTTP 18 项 + Playwright UI 6 项 + 截图存证）
bash acceptance/run.sh          # 收尾 bash acceptance/stop.sh

# ③ 测试套件（G10 基线 3205/0，~17s）
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q -p no:cacheprovider

# ④ 校验你的 v2 项目
PYTHONPATH=. .venv/bin/python -m src.engine_v2.content.cli validate path/to/project

# ⑤ 开发控制平面（存档检视/追踪/重放/分支）
PYTHONPATH=. .venv/bin/python scripts/v2_devcontrol.py inspect <save_id>

# ⑥ headless 装配并 tick 一个 v2 游戏（runtime closure 单入口；
#    reference game = examples/complex_minimal，trust_python=True 激活
#    Python 扩展；deployment 参数可开 LLM NPC，缺省 headless）
PYTHONPATH=. .venv/bin/python -c "
from src.engine_v2.runtime import assemble_project
result = assemble_project('examples/complex_minimal', trust_python=True)
engine = result.engine
for _ in range(3):
    engine.advance(1)
print('revision:', int(engine.instance.world.world_revision))
"
```

v2 不需要 API Key 即可运行全部机械面（K5：演示宿主 = 确定性
policy/backend）。「接真 LLM 玩一局」= P11+ 承接面。

### 1.4 文档索引

| 文档 | 内容 |
|---|---|
| `docs/v2/usage/README.md` | 使用文档组索引 + 引擎概览 |
| `docs/v2/usage/quickstart.md` | 环境 / 运行 / WebUI / 验收 / 测试 |
| `docs/v2/usage/project-authoring.md` | **v2 项目格式**（字段级参考 + v1 init 映射） |
| `docs/v2/usage/devtools-and-extensions.md` | devtools / 存档 / 回放 / 扩展点 |
| `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md` | 总 Spec（架构权威） |
| `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` | 执行计划（Phase/任务/门禁） |
| `docs/v2/contracts/P1…P10-*.md` | 各 Phase 冻结设计 SOT（含 §9 勘误链） |
| `docs/v2/gates/G0…G10-*.md` | 门禁报告（收口证据） |
| `docs/v2/gates/runtime-closure-gate-report.md` | runtime closure 门禁（Gate C1–C9 证据） |
| `docs/plans/llmBasedSim_12h_complex_game_runtime_closure_subagent_plan.md` | 12h closure 计划（T1–T11 波次 + Gate 定义） |
| `src/engine_v2/runtime/README.md` | runtime 层：装配入口 / tick 循环 / 授权面 / 观测 |
| `docs/v2/gates/G10-test-acceptance-plan.md` | G10 人工面验收方案（S11） |
| `src/engine_v2/README.md` | 引擎目录布局 + v2 冻结规则 |

---

## 2. v1 引擎（冻结原型，仍可运行）

由多个 LLM Agent 协同驱动的互动模拟游戏框架：11 个 LangGraph
节点构成完整 tick 管道（玩家意图 → 行动可行性 → NPC 并发决策 →
物理推演 → 状态应用 → 属性更新/感官过滤 → 叙事改写）。世界真实状态
与玩家感知分离（感官过滤），玩家潜意识系统修正表层输入，行动
双轨制（Python 确定性规则 + LLM 综合判断）。

### 2.1 快速开始

环境：Python >= 3.12 + DeepSeek API Key（任何 OpenAI 兼容后端，
见下）。

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate  /  macOS|Linux: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # 填入 DEEPSEEK_API_KEY
```

**切换 API 后端**（OpenAI 兼容客户端）：改
`config/simulation.yaml` 的 `llm:` 节（`model` / `base_url` /
`api_key_env`）+ `.env` 对应变量。

| 后端 | model | base_url | api_key_env |
|---|---|---|---|
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` |
| OpenAI | `gpt-4o` | `https://api.openai.com/v1` | `OPENAI_API_KEY` |
| 本地 Ollama | `llama3` | `http://localhost:11434/v1` | `OLLAMA_API_KEY`（任意值） |

**CLI：**

```bash
python -m src.main                                  # 对话式初始化开局
python -m src.main --init-file public_start/whisperheads.yaml   # init 文件直接开局
python -m src.main --init-file-set public_start/murder          # 文件组开局
python -m src.main --load saves/<name>.json                     # 读档
```

**WebUI：**

```bash
python -m src.web.main            # 打开 http://127.0.0.1:8000
python -m src.web.main --lan      # 局域网/手机访问（打印 LAN IP）
```

启动页自动发现 `public_start/` 与 `private_start/` 的 init 文件
（文件组标记 `[拆分配置]`），支持任意路径开局与 `saves/*.json`
读档。

**CLI/WebUI 命令**：`/help` `/idid`（本回合玩家实际做了什么）
`/status` `/see` `/hear` `/feel`（感官分类查询）`/save <name>`
`/stop`（终止长行动）`/quit`。命令不消耗 tick。

### 2.2 init 文件格式（v1 开局载体）

两种形式：**单文件 YAML**（推荐）与**启动文件组**（目录）。
权威示例 = `public_start/whisperheads.yaml`（完整注释）与
`public_start/murder/`（文件组）。

**单文件最简示例：**

```yaml
world:
  name: 测试场景
  description: 一个简单的测试房间
  locations:
    - id: room
      name: 房间
      description: 一间普通的石室
      connections: {north: corridor}
      ambient_light: 昏黄的烛光
      ambient_sound: 壁炉的噼啪声
  objects:
    - id: table
      name: 桌子
      object_type: furniture        # furniture/container/decoration/tool/food/
      description: 一张木桌          #   weapon/character_equipment/device/
      position: {x: 1, y: 0, z: 2}  #   document/clothing/misc
      state: {locked: false}
      properties: {weight_kg: 30, lock_difficulty: 0.6}
player:
  name: 冒险者
  persona: 一个普通的冒险者
  capabilities:
    sight_range_m: 50.0
    hearing_range_m: 100.0
    skill_levels: {sword: 0.8, lockpicking: 0.3}
    allowed_extraordinary_actions: [灵能感知]
    blocked_common_actions: [飞行]
  physical_profile: {strength: 0.8, body_width_cm: 60.0}
  attributes:
    stamina: {name: 体力, value: 100, max: 100}
    sanity: {name: 理智, value: 80, max: 100, hidden: true}
  subconscious_rules: [在公开场合不承认超自然现象的存在]
  speech_examples: [我不需要你的怜悯。]
characters:
  - id: guard
    name: 守卫
    personality:
      traits: [严肃, 尽责]
      motivations: [看守石门]
      speech_style: 寡言
      background: 驻守十年的老守卫
    position: {x: 2, y: 0, z: 0}
    relationships: {player: 0.3}     # -1.0 ~ 1.0
    attributes: {loyalty: {name: 忠诚度, value: 70, max: 100}}
    speech_examples: [我不建议走那条路。]
starting_scene_description: 你推开石门，走进一间昏暗的石室。
max_ticks: 100
game_time: {hour: 6, minute: 0}
ticks_per_game_minute: 0.2
```

**顶层字段**：`world` / `player` / `characters` /
`starting_scene_description`（必需）+ `max_ticks` / `game_time` /
`ticks_per_game_minute` / `world_rules` / `narrative_style`
（可选）。

**`world_rules`（世界规则注入）**：

```yaml
world_rules:
  physics:                        # 物理 prompt 规则
    disable: [8]                  #   禁用默认规则（1-based 索引；默认共 10 条）
    append:
      - "11. **亚空间低语**：Vox 通讯会导致附近电子设备间歇性失灵。"
  attribute:                      # 属性 prompt 规则（默认共 7 条）
    disable: []
    append:
      - "接触远古石碑时：sanity 下降 2-8 点。"
  deterministic:                  # Python 侧确定性预判规则
    disable: [3]                  #   跳过内置规则（1=人设 2=超凡 3=力量vs重量
                                  #    4=开锁技能 5=身体宽度vs通道）
    append:
      - id: sanity_gate
        description: 精神崩溃时多数行动受限
        condition: "if(player.sanity < 20, blocked; player.sanity < 40, uncertain:0.3; allowed)"
      - id: storm_heavy_lift
        description: 暴风中搬运重物
        match_action: "搬运|抬起|举起|推动|拖动"
        condition: "if(player.storm_tolerance < 30, blocked; allowed)"
  locked_attributes:              # locked 属性计算规则（LLM 不可改，引擎算）
    - type: timer                 #   timer / stage / snapshot / list_constraint
      timer_key: alert_timer
      condition: "danger > 0"
      thresholds: [10, 30]
      warning: "警报已持续{threshold}分钟。"
```

condition 语法：`if(cond, out; cond, out; else_out)`；比较/算术/
`min()` `max()` / `abs()` / `and` `or`；引用 `player.<属性>` /
`target.<属性>`。`uncertain:<p>` = 概率检定（0 < p < 1，Python
侧 roll）。

**`narrative_style`**：`{style_description, style_example}` 控制
叙事文风。

**启动文件组**（`public_start/<场景名>/`）：`world.yaml`（必需）
+ `player.yaml` + `characters/*.yaml` + `settings.yaml`（可选：
world_rules / narrative_style / max_ticks / game_time /
ticks_per_game_minute）。WebUI 自动发现含 `world.yaml` 的子目录。

**位置约定**：`public_start/` 纳入版本控制；`private_start/`
私人场景（`.gitignore` 排除）。CLI/WebUI 均可从任意路径加载。

> v1 init 文件与 v2 项目格式的逐字段映射见
> `docs/v2/usage/project-authoring.md` §7（v2 是 init 文件的
> 后继：分节化 + 机器校验 + 动作/规则注册表 + 部署分离）。

### 2.3 架构（v1）

| 层 | 位置 | 职责 |
|---|---|---|
| 入口 | `src/main.py` | 配置加载 / LLM 初始化 / 初始化阶段 / 主循环 |
| 图与状态 | `src/graph/game_graph.py`、`game_state.py` | LangGraph tick 管道（11 节点）+ `GameState`（dict 流转，边界 Pydantic） |
| 数据模型 | `src/models/` | 位置/世界/角色/玩家/事件/配置 |
| Agent 初始化 | `src/agents/init.py` | 四轮对话初始化 或 `load_init_file()` 文件开局 |
| 结构化输出 | `src/llm/parser.py` | prompt 注入 JSON Schema → Pydantic 解析 + 失败重试 |
| Prompt | `prompts/*.j2`（15 模板）+ `src/prompts/loader.py` | 中文 Jinja2 模板 |
| 配置 | `config/simulation.yaml` | LLM / 模拟 / Agent 全局配置（零硬编码） |
| 确定性规则 | `src/game/rules.py`、`state_apply.py` | 能力/物理/技能预判 + 状态应用 |
| UI | `src/ui/`（Rich CLI）、`src/web/` + `web/`（WebUI） | 双面板终端 / 暗色 HUD 三栏 Web |
| 接口规范 | `docs/game-flow-interfaces.md` | 状态契约 / 节点 IO / Prompt / 存档格式 |

**tick 管道**：

```text
player_intent_process → player_action_resolve → characters_all_decide
→ tick_speed_resolve → physics_resolve → state_apply
→ natural_attribute_delta（确定性：自然 delta + locked 属性 + diff）
  ├─ attribute_update（LLM 事件驱动属性变化）
  └─ sensory_filter → narrative_stylize → post_narrative_update（叙事后确定性更新）
```

### 2.4 v1 当前限制（冻结时点记录）

1. 长行动截断对「无坐标搜索类行动」依赖 LLM 设 `target_position`；
2. 确定性规则偏启发式（正则匹配），复杂语义仍靠 LLM；规则预判
   只是 LLM 输入，不是最终裁决；
3. 检定系统基础（uncertain + roll；无难度等级/优势劣势/重试惩罚）;
4. 测试 = 251 纯函数用例（无 mock-LLM 完整 tick 集成测试）；
5. LLM 输出字段格式偶有波动，靠兼容逻辑兜底。

v1 不再演进——新功能一律进 v2（迁移对照：`docs/v2/reference/` +
`docs/v2/usage/project-authoring.md` §7）。

---

## 3. 协作者快速索引

| 目标 | 入口 |
|---|---|
| 跑 v2 演示 / 验收 | `scripts/v2_g10_acceptance.py` / `bash acceptance/run.sh` |
| 写 v2 游戏项目 | `docs/v2/usage/project-authoring.md` + `tests/fixtures/v2_project_*` |
| v2 devtools / 回放 | `scripts/v2_devcontrol.py` + `docs/v2/usage/devtools-and-extensions.md` |
| 改 v2 引擎代码 | `CONTRIBUTING.md`（门禁纪律）+ `src/engine_v2/` + 对应 `docs/v2/contracts/P<n>` |
| 查 v2 架构权威 | `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md` |
| 查门禁/设计决策 | `docs/v2/gates/` / `docs/v2/contracts/` §9 勘误链 |
| 跑 v1 游戏 | `python -m src.main` / `python -m src.web.main` |
| v1 主循环 / 管道 | `src/main.py` / `src/graph/game_graph.py` |
| v1 模型 / 状态 | `src/models/` / `src/graph/game_state.py` |
| v1 初始化流程 | `src/agents/init.py` |
| v1 结构化解析 | `src/llm/parser.py` |
| v1 LLM 配置 | `config/simulation.yaml` |
| v1 Prompt | `prompts/*.j2` |
| v1 确定性规则 | `src/game/rules.py` / `src/game/state_apply.py` |
| v1 init 文件示例 | `public_start/whisperheads.yaml` / `public_start/murder/` |
| v1 接口规范 | `docs/game-flow-interfaces.md` |
| LLM 协作者简报 | `llm_readme.md` |
| 协作约定 | `CONTRIBUTING.md` |
