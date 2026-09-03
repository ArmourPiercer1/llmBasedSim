# v2 项目格式（编写你的第一个 v2 游戏）

> v2 的开局载体是**项目目录**（GameProject），取代 v1 的单文件 /
> 文件组 init YAML。一个目录 = 一个完整游戏：世界、玩家、角色、
> 物品、动作、规则、玩法模式、推理能力声明，全部结构化 YAML，
> 可版本控制、可机器校验（`llmsim validate`）、可确定性装配进
> 引擎。
>
> 设计权威：Spec §5（GameProject / Source of Truth / Deployment
> 分离）、`docs/v2/contracts/P5-project-format-module-plugin-dsl-design.md`
> （P5 SOT，字段级冻结态）。本文是字段级使用参考。

## 1. 目录布局（闭集，零其他文件）

```text
my_game/
├── game.yaml                 # 必需。manifest / scenario / player + 5 个可选节
├── world/
│   └── <name>.yaml           # 可选，0 或 1 个文件。顶层键必为 world
├── characters/
│   └── <name>.yaml           # 可选，N 个。顶层键必为 characters
├── items/
│   └── <name>.yaml           # 可选，N 个。顶层键必为 items
├── rules/
│   └── <name>.yaml           # 可选，N 个。顶层键必为 rules
├── actions/
│   └── <name>.yaml           # 可选，N 个。顶层键必为 actions
├── prompts/
│   └── <name>.yaml           # 可选，N 个。顶层键必为 prompts
├── scenarios/
│   └── <name>.yaml           # 可选，N 个（追加场景；缺省场景在 game.yaml）
├── modules/
│   └── <name>.yaml           # 可选，N 个。顶层键必为 modules
└── plugins/
    └── <plugin>/plugin.yaml  # 可选，恰好两层。插件描述符
```

闭集纪律：

- loader 只识别上述模板（深度封闭）；**全树零 `.py` 扫描**
  （项目 = 纯数据，Python 化升级走 modules 声明面）；
- 每个节文件顶层键必须恰为节名（如 `characters/*.yaml` 顶层键
  必为 `characters`）；多余顶层键 → `LLMSIM_UNKNOWN_KEY`；
- 所有节字段 `extra="forbid"`：出现未声明字段 = 诊断（error）；
- id 一律小写蛇形（`_ID_PATTERN`）；`world/` 至多 1 个文件
  （≥2 → 取排序首文件 + 每余文件一条 error 诊断）；
- 项目**不得**包含部署信息（K8）：LLM provider / model /
  base_url 等只出现在项目外的 `deployment.yaml`（§7）。

## 2. game.yaml（8 键封闭集）

顶层 8 键：`manifest` / `scenario` / `player`（**必需**）+
`component_schemas` / `authority` / `gameplay_modes` /
`capabilities` / `plugin_descriptors`（可选）。

### 2.1 manifest（必需）

```yaml
manifest:
  schema_version: "2"          # 必为 "2"（v1 文件拒绝的机械判据之一）
  project_id: galgame          # 小写蛇形 id
  name: 教室的午后
  description: 教室小切片样例（可选）。
  engine_version: ">=0.5.0"    # ""（任意）| "1.2" | ">=1.2"
```

### 2.2 scenario（必需）

```yaml
scenario:
  id: scenario_galgame         # 场景 id（小写蛇形）
  max_ticks: 16                # 最大回合数（>= 1）
  ticks_per_game_minute: 0.5   # 每 tick 推进的游戏分钟数（> 0）
  game_time:                   # 起始时刻
    hour: 14                   # 0–23
    minute: 30                 # 0–59
  starting_scene_description: 午后铃声后的教室。阳光从窗斜进……
  narrative_style: 温暖克制的轻叙事，短句，少形容词。
```

追加场景 = `scenarios/*.yaml`（同形状，顶层键 `scenarios` 单值）。

### 2.3 player（必需）

```yaml
player:
  player_id: player_1
  name: 转学生
  persona: 转学第一天的学生，谨慎而善意。
  position: {x: 1.0, y: 1.0}            # 可选（空间域内坐标）
  capabilities:                          # 开放 dict（JSON-clean）
    sight_range_m: 8.0                   #   规范键：sight_range_m /
    hearing_range_m: 12.0                #   hearing_range_m / skill_levels /
  physical_profile:                      #   allowed_extraordinary_actions /
    height_cm: 165.0                     #   blocked_common_actions
    weight_kg: 55.0                      #   （height_cm / weight_kg /
                                         #    body_width_cm / strength /
                                         #    movement_mode）
  attributes:                            # 数值属性（封闭字段）
    spirit:
      name: spirit
      value: 6.0                         # 构造期校验 min <= value <= max
      min: 0.0
      max: 10.0
      natural_delta_per_minute: 0.0      # 自然漂移速率（可选，默认 0）
      description: 玩家精神值。
  inventory: []                          # 初始物品 id 列表
  subconscious_rules: []                 # 潜意识规则（字符串列表）
  subconscious_memory: []                # 潜意识记忆（字符串列表）
  speech_examples:                       # 语言风格范例（注入角色 prompt）
    - 谢谢你昨天帮我找资料。
```

### 2.4 可选节（game.yaml 顶层）

```yaml
gameplay_modes:                    # 玩法模式（P4；mode 切换约束动作集）
  - id: exploration
    mode_type: exploration         # 基线层（无约束）
    params: {}
    description: 自由探索阶段。
  - id: tactical
    mode_type: tactical            # allow 层（动作集限定）
    params: {}
    description: 战术阶段。

capabilities:                      # 推理能力需求画像（Spec §5.5；字段封闭，
  - id: major_characters           #   不得含任何部署 pinning——K8）
    capability: roleplay_major    #   理想模型画像，deployment 侧按 tier 匹配
    min_tier: 2
    ideal_tier: 3
    notes: 主要角色需要高一致性人设。

authority:                         # 权威声明（K3；P5 = 结构 + 域重叠静态检查）
  - id: authority_tactical
    domain: tactical
    owner: module.tactical
    exclusive: true

component_schemas:                 # 自定义组件 schema（点分 id，如 world.location）
  - id: custom.mood
    description: 心情组件。
    fields:
      - {name: mood, type: string, required: true}

plugin_descriptors:                # 插件描述符（source: local | entrypoint）
  - id: my_plugin
    source: entrypoint
    entrypoint: my_pkg.my_plugin:make_plugin   # module:Attribute 形式
```

## 3. 节文件格式（每节一个样例）

### 3.1 world/<name>.yaml（顶层键 `world`）

```yaml
world:
  name: 教室
  description: 午后铃声后的教室，阳光从窗斜进。
  environment:
    time_of_day: afternoon
    weather: clear
    temperature_c: 24.0
  locations:
    - id: classroom                # 小写蛇形
      name: 教室
      description: 长条教室，窗斜进午后阳光。
      connections: {east: corridor}   # 邻接关系（或空 {}）
      ambient_light: warm
      ambient_sound: quiet
      properties: {}                 # 开放 dict（JSON-clean）
```

### 3.2 characters/<name>.yaml（顶层键 `characters`，单元素列表）

```yaml
characters:
  - id: lena
    name: 莉娜·索蕾尔
    personality:                     # 开放 dict（规范键：traits / motivations /
      traits: [lively, sociable]     #   speech_style / background）
      motivations: 不想让新同学感到孤单，总想找话题。
      speech_style: 活泼，爱用反问句。
      background: 活泼的班长，爱聊天，自来熟。
    position: {x: 0.0, y: 2.0}
    relationships:                   # key = 其他 character id 或 player_id
      player_1: 0.3                  # 好感度 -1.0 ~ 1.0
    starting_inventory: []
    speech_examples:
      - 上个月的祭典你喜欢吗？
    attributes: {}                   # 同 player.attributes 形状
```

### 3.3 items/<name>.yaml（顶层键 `items`，单元素列表）

```yaml
items:
  - id: letter
    name: 手写信
    object_type: letter              # 自由字符串（furniture / container /
    description: 一封手写信，收件人姓名尚未落款。
    position: {x: 3.0, y: 2.0}
    state: sealed                    # v2 扁平化 str（v1 state dict 的形状简化）
    properties:                      # 开放 dict
      weight_kg: 0.01
```

### 3.4 rules/<name>.yaml（顶层键 `rules`，列表）

规则 = 确定性可行性判定（Python 侧，v1 `world_rules.deterministic`
的 v2 形态）。按 `priority` 降序、同 priority 按 id.casefold 序执行。

```yaml
rules:
  - id: rule_carry_weight
    description: 力量相对目标物重的搬运判定。
    condition: 'if(player.strength > target.weight * 1.5, allowed; player.strength > min(target.weight, 25.0), uncertain : 0.4; blocked)'
    priority: 100
  - id: rule_move_uncertain
    description: 移动动作匹配规则（match + 简式）。
    match: move                      # 动作 verb 匹配（正则/字面）
    feasibility: uncertain           # allowed | blocked | uncertain
    probability: 0.6                 # feasibility=uncertain 时必需（0 < p < 1）
    priority: 90
  # 另支持 disabled: true 停用某条规则
```

**condition DSL**（validate 期 `parse_dsl` 校验，零 Python 执行）：

- 文法：`if(cond, output; cond, output; …; else_output)`；
- 比较：`<` `>` `=` `<=` `>=` `!=`；算术：`+` `-` `*` `/`；
  函数：`min()` `max()`；
- 可引用：`player.<属性>` / `player.<技能>` / `target.<属性>`
  / 字面量数字；
- output ∈ `allowed` / `blocked` / `uncertain : <0<p<1>`。

### 3.5 actions/<name>.yaml（顶层键 `actions`，列表）

动作注册表（Spec §11.2：v2 废弃固定 action literal，动作 = 项目
声明的注册表条目 + 执行器）。

```yaml
actions:
  - id: move
    name: 移动
    verb: move                       # 缺省 interact
    description: 向相邻六角移动（邻接校验在执行器面）。
    condition: 'if(min(player.strength, 1.0) >= 0.0, allowed; blocked)'
    # 另支持 requires_components: [组件 id] / success_probability (0<p<1)
```

### 3.6 prompts / scenarios / modules / plugins（简述）

- `prompts/*.yaml`（顶层键 `prompts`）：`PromptPolicy` 列表——
  `{id, scope, template_ref, variables[]}`（字段封闭；无 authority /
  permission 类字段，K4）；
- `scenarios/*.yaml`（顶层键 `scenarios`）：追加 `ScenarioSpec`
  （§2.2 同形状）；
- `modules/*.yaml`（顶层键 `modules`）：`ModuleGraphNode` 列表——
  `{id（点分：族.模块）, version, entrypoint?, requires[], optional[],
  conflicts[], engine_version, description}`；官方 9 模块
  （attributes / inventory / character / knowledge / perception /
  relationships / space / tactical / scenario）已内置，项目按
  需声明启用；
- `plugins/<p>/plugin.yaml`：插件描述符（§2.4 同形状）。

## 4. deployment.yaml（项目外，用户侧）

K8 不变量：部署与项目分离。**项目声明「需要什么」（capabilities
画像）；deployment 声明「用什么」（模型 + provider）**。deployment
文件不属于项目（项目 12 名扫描面之外），放项目旁即可：

```yaml
models:                            # 模型画像（tier 0–3 分级）
  model_high:
    model_id: model_high
    tier: 3
    context_length: 131072
    max_output: 16384
    structured_output: true
    reasoning_class: advanced

inference_profiles:                # 推理 profile（项目 capability 按 tier 匹配）
  major_character:
    provider: openai               # provider-neutral 抽象下的标识
    model: model_high
    base_url: https://sim.example/v1
    api_key_env: FAKE_PROBE_KEY    # 密钥只引用环境变量名（K4/K8）
    temperature: 0.7
    timeout_seconds: 30.0
```

样例：`tests/fixtures/v2_deployment/deployment.yaml`。真实
provider 接线 = P11+ 承接面（quickstart §6）。

## 5. 校验

```bash
# 装过 console script（pip install -e .）：
.venv/bin/llmsim validate my_game/
# 未装（等价）：
PYTHONPATH=. .venv/bin/python -m src.engine_v2.content.cli validate my_game/
# 机器可读：
PYTHONPATH=. .venv/bin/python -m src.engine_v2.content.cli validate my_game/ --json
```

全链 = loader（布局/YAML 解析）→ build_ir（逐节 pydantic
校验 + 引用检查）→ validate_project（语义检查：重复 id / 引用
悬空 / 域重叠 / DSL 解析 / 版本文法）。诊断 = 18 码闭集
（`DIAGNOSTIC_CODES`）+ severity（error/warning）+ path + 确定性
message。退出码：0 = 无 error；1 = 有 error；2 = 用法错。

可直接运行的样例项目（全部 0 error）：

| 项目 | 位置 | 特点 |
|---|---|---|
| 教室（galgame） | `tests/fixtures/v2_project_galgame/` | 单地点 + 2 角色 + 1 物品；Web 演示世界源 |
| 六角演武场（tactical） | `tests/fixtures/v2_project_tactical/` | 3 动作 + gameplay_modes（exploration/tactical） |
| Zero Python 镜像 | `tests/fixtures/v2_project_zero_python/` | v1 test_empty 的 v2 镜像（§8 映射对照源） |
| sandbox / p7 / broken | `tests/fixtures/v2_project_*/` | 规则 / 能力画像 / 故意损坏（诊断样例） |

## 6. 用 Web 演示跑你自己的项目

当前装配路径（宿主侧；P11+ 将由官方装配 API 取代）= 验收驱动
同款 10 行链：

```python
from pathlib import Path
from src.engine_v2.adapters.web.server import run_web_server
from src.engine_v2.adapters.web.session import SessionManager
from src.engine_v2.content.loader import load_project
from src.engine_v2.content.project_ir import build_ir
from src.engine_v2.core.space import GridSpace
from src.engine_v2.presentation.image.backend import DeterministicImageBackend
from tests.engine_v2.adapters.web.conftest import HostTickDriver
from tests.engine_v2.modules.conftest import _build_world

load = load_project(Path("my_game"))          # .raw / .diagnostics
ir = build_ir(load.raw).ir                    # ProjectIR（16 字段）
world, *_ = _build_world(ir, "world", GridSpace(width=10, height=10))
manager = SessionManager(
    driver_factory=lambda: HostTickDriver(world),
    image_backend_factory=DeterministicImageBackend,
)
session_id = manager.create_session(world)
print(f"SESSION_ID={session_id}")
run_web_server(manager, host="127.0.0.1", port=8000)
```

完整可运行版 = `scripts/v2_g10_acceptance.py`（galgame 世界源；
它多做一步宿主侧 P10 表现面增强：actor 标签 + display 展示组件
+ location 实体 + game_time/weather 缺省——你的项目若要让 WebUI
投影出玩家/角色名，需要同款增强，参考该脚本
`_augment_p10_surface`）。

## 7. v1 init 文件 ↔ v2 项目映射

| v1 init 文件（public_start YAML） | v2 位置 | 备注 |
|---|---|---|
| 顶层 `world`（name/description/environment/locations） | `world/<name>.yaml` 顶层 `world` | 形状几乎一致 |
| v1 `world.objects` | `items/<name>.yaml` 顶层 `items` | 升为顶层分节；`state` dict → 扁平 str |
| 顶层 `player` | `game.yaml` 顶层 `player` | 字段几乎一致（capabilities/physical_profile 开放 dict 保留） |
| 顶层 `characters` | `characters/<name>.yaml`（每个角色一文件） | 分节化 |
| 顶层 `starting_scene_description` / `max_ticks` / `game_time` / `ticks_per_game_minute` / `narrative_style` | `game.yaml` 顶层 `scenario`（ScenarioSpec） | 归入场景节 |
| 顶层 `world_rules.physics/attribute`（LLM 规则注入） | **无 v2 对应**（P7 dynamics 域：规则引擎/LLM backend 分层，prompt 注入方式重构） | v2 中 LLM 只能提议（K4） |
| 顶层 `world_rules.deterministic`（Python 预判规则） | `rules/<name>.yaml`（RuleSpec + DSL） | 结构化 + validate 期解析 |
| 固定 action 字面量（v1 隐含） | `actions/<name>.yaml`（ActionSpec 注册表） | Spec §11.1 废弃固定 literal |
| （无） | `game.yaml`：manifest / gameplay_modes / capabilities / authority / component_schemas / plugin_descriptors | v2 新增面 |
| （无，LLM 配置在 config/simulation.yaml） | `deployment.yaml`（项目外） | K8 分离 |
| （无） | `llmsim validate` 机器校验 | v1 靠运行时报错 |

迁移工具参考：`scripts/v2_migrate_v1.py`（v1 形状 → v2 分节
镜像实验）+ `tests/fixtures/v2_project_zero_python/`（test_empty
完整镜像实例，头部注释含逐项映射与偏差台账）。

## 8. 常见诊断（排错）

| 症状 | 原因 |
|---|---|
| `LLMSIM_FILE_MISSING` | 缺 `game.yaml` |
| `LLMSIM_YAML_PARSE` | YAML 语法错（看 path 指到的文件） |
| `LLMSIM_UNKNOWN_KEY` | 出现 8 键封闭集 / 节字段之外的键（拼写？多打了缩进？） |
| `LLMSIM_SCHEMA` | 字段形状/范围错（value 越界、id 非蛇形、schema_version ≠ "2"、world 双文件…） |
| v1 文件直接 validate | 顶层 world/player 被判 v1 形状 → 拒绝（D-P5-04 零 v1 兼容），按 §7 映射改写 |
| `uncertain` 规则报概率错 | `feasibility: uncertain` 必须给 `probability`（0 < p < 1） |
