# 启动文件编写指南

本指南涵盖编写模拟游戏启动文件的全部内容，包括单文件 YAML 和启动文件组两种格式、世界规则注入、数值属性联动、叙事风格控制等高级功能。

## 目录

1. [快速开始](#快速开始)
2. [单文件 YAML 格式](#单文件-yaml-格式)
3. [启动文件组格式](#启动文件组格式)
4. [世界定义](#世界定义)
5. [玩家定义](#玩家定义)
6. [NPC 定义](#npc-定义)
7. [属性系统](#属性系统)
8. [世界规则注入](#世界规则注入)
9. [叙事风格控制](#叙事风格控制)
10. [游戏时间与 Tick 速度](#游戏时间与-tick-速度)
11. [存档兼容性](#存档兼容性)
12. [完整字段参考](#完整字段参考)
13. [示例文件](#示例文件)

---

## 快速开始

最简启动文件仅需定义世界、玩家和初始叙事：

```yaml
world:
  name: 测试场景
  description: 一个简单的测试房间
  locations:
    - id: room
      name: 房间
      description: 一间普通的石室
  objects:
    - id: table
      name: 桌子
      object_type: furniture
      description: 一张木桌
      properties:
        weight_kg: 30
player:
  name: 冒险者
  persona: 一个普通的冒险者
characters:
  - id: guard
    name: 守卫
    personality:
      traits: [严肃, 尽责]
    starting_position:
      x: 2
      y: 0
      z: 0
starting_scene_description: 你推开石门，走进一间昏暗的石室。角落里站着一个沉默的守卫。
```

用 `python -m src.main --init-file path/to/scene.yaml` 启动。

---

## 单文件 YAML 格式

一个 `.yaml` 文件包含完整场景。放在 `public_start/` 或 `private_start/` 目录下。

### 顶层字段

| 字段 | 必需 | 类型 | 默认值 | 说明 |
|---|---|---|---|---|
| `world` | 是 | dict | — | 世界定义，含 `name`、`description`、`locations`、`objects`、`environment` |
| `player` | 是 | dict | — | 玩家定义 |
| `characters` | 是 | list | — | NPC 列表 |
| `starting_scene_description` | 是 | str | `"游戏开始。"` | 开场叙事文本 |
| `starting_location_id` | 否 | str | — | 用于推断玩家初始位置的场所 ID |
| `max_ticks` | 否 | int | `100` | 最大回合数 |
| `game_time` | 否 | dict | `{hour: 18, minute: 0}` | 初始游戏时间 |
| `ticks_per_game_minute` | 否 | float | `0.2` | 每个 tick 推进的游戏分钟数（静态模式） |
| `world_rules` | 否 | dict | — | 世界规则注入，含 `physics`、`attribute`、`deterministic`、`locked_attributes` |
| `narrative_style` | 否 | dict | — | 叙事风格控制 |

---

## 启动文件组格式

将世界、玩家、NPC 分别放在不同文件中。放在 `public_start/<场景名>/` 或 `private_start/<场景名>/` 下。

### 目录结构

```
public_start/murder/
  world.yaml          ← 必需。世界定义
  player.yaml         ← 可选。玩家设定（缺失时使用默认值）
  characters/         ← 可选。NPC 目录
    lucius.yaml
    eidolon.yaml
  settings.yaml       ← 可选。world_rules、narrative_style、max_ticks 等
```

### `world.yaml`

仅含 `world:` 顶层键：

```yaml
world:
  name: 谋杀星
  description: 第六十三之十九号世界
  environment:
    time_of_day: 清晨
    weather: 离子风暴前夕
    temperature_c: 35.0
  locations:
    - id: landing_zone
      name: 登陆区
      description: 风暴鸟降落的金属平台
      connections: {north: forest_edge}
  objects:
    - id: stormbird
      name: 风暴鸟运输机
      object_type: device
      description: 第十连的专属运输机
      properties: {weight_kg: 8000}
```

### `player.yaml`

仅含 `player:` 顶层键：

```yaml
player:
  name: 萨乌尔·塔维茨
  persona: 帝皇之子第十连一线连长
  capabilities:
    allowed_extraordinary_actions:
      - 以帝皇之子完美战术指挥战斗
    skill_levels:
      swordsmanship: 0.95
  physical_profile:
    strength: 0.9
  attributes:
    stamina: {name: 体力, value: 95, max: 100}
```

### `characters/<name>.yaml`

每文件一个 NPC，仅含 `character:` 顶层键：

```yaml
character:
  id: lucius
  name: 卢修斯
  personality:
    traits: [傲慢, 天才, 残忍]
    motivations:
      - 证明自己是全军团最伟大的剑士
    speech_style: 华丽而自恋
    background: 帝皇之子第三连的剑术冠军
  position: {x: 5, y: 0, z: 3}
  attributes:
    pride: {name: 傲慢值, value: 90, max: 100}
```

### `settings.yaml`

可选的全局设置覆盖文件：

```yaml
world_rules:
  physics: ...
  attribute: ...
  deterministic: ...
narrative_style:
  style_description: 战锤40K哥特式军事科幻
  style_example: 离子风暴的紫光照亮了登陆平台……
max_ticks: 80
game_time: {hour: 5, minute: 30}
ticks_per_game_minute: 0.5
```

### 启动方式

```bash
# 单文件
python -m src.main --init-file public_start/whisperheads.yaml

# 文件组
python -m src.main --init-file-set public_start/murder
```

---

## 世界定义

### 环境（`world.environment`）

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `time_of_day` | str | `"morning"` | 时段描述（清晨/上午/中午/下午/傍晚/夜晚/深夜）。系统会根据 `game_time` 自动覆盖此值 |
| `weather` | str | `"clear"` | 天气描述 |
| `temperature_c` | float | `20.0` | 摄氏温度 |

### 场所（`world.locations`）

```yaml
locations:
  - id: hall              # 必需：唯一标识符
    name: 大厅            # 必需：显示名称
    description: 一座宏伟的大理石大厅  # 必需：环境描述
    connections:           # 可选：到其他场所的连接
      north: garden
      east: kitchen
    ambient_light: 昏黄的烛光    # 可选，默认 "bright"
    ambient_sound: 壁炉的噼啪声  # 可选，默认 "quiet"
    properties:            # 可选
      width_cm: 300        # 通道宽度，影响身体宽度判定
```

`connections` 支持两种格式：
- **字典**（推荐）：`{north: garden, east: kitchen}`
- **列表**：`[north, east]` → 自动展开为 `{north: north, east: east}`

### 物体（`world.objects`）

```yaml
objects:
  - id: ancient_desk       # 必需：唯一标识符
    object_type: furniture  # 必需：物体类型
    name: 古旧书桌         # 必需：显示名称
    description: 一张橡木书桌，抽屉半开着  # 必需
    position:               # 可选，默认 {x:0, y:0, z:0}
      x: 1
      y: 0
      z: 2
    state:                  # 可选，初始状态
      locked: false
    properties:             # 可选，影响物理和交互判定
      weight_kg: 80         # 重量（kg），影响力量判定
      lock_difficulty: 0.6  # 锁难度（0-1），触发开锁技能检定
      portable: true        # 是否可携带
      consumable: true      # 是否消耗品
      material: oak         # 材质
```

#### 物体类型（`object_type`）

| 类型 | 说明 |
|---|---|
| `furniture` | 家具（桌、椅、床） |
| `container` | 容器（箱子、柜子） |
| `decoration` | 装饰物 |
| `tool` | 工具 |
| `food` | 食物 |
| `weapon` | 武器 |
| `character_equipment` | 角色装备 |
| `device` | 设备/机械 |
| `document` | 文档/书籍 |
| `clothing` | 衣物 |
| `misc` | 其他 |

#### 影响判定的物体属性

| 属性 | 类型 | 影响的判定 |
|---|---|---|
| `weight_kg` | float | 力量 vs 重量判定（规则 3） |
| `lock_difficulty` | float (0-1) | 开锁技能 vs 锁难度判定（规则 4） |
| `width_cm` / `effective_width_cm` | float | 身体宽度 vs 通道判定（规则 5） |
| `portable` | bool | 是否可拾取到物品栏 |
| `consumable` | bool | 使用后是否消耗 |

---

## 玩家定义

```yaml
player:
  name: 角色名
  persona: 一段描述角色性格、背景和行为倾向的文字
  position: {x: 0, y: 0, z: 0}   # 可选，默认自动推断

  capabilities:                    # 感知与行动能力
    sight_range_m: 50.0            # 视野范围（米），默认 50
    hearing_range_m: 100.0         # 听力范围（米），默认 100
    field_of_view_degrees: 180.0   # 视野角度，默认 120
    special_senses:                # 特殊感官列表
      - 夜视
      - 热感应
    allowed_extraordinary_actions:  # 允许的超凡行动
      - 灵能感知
      - 指挥部队
    blocked_common_actions:        # 人设限制：禁止的普通行动
      - 飞行
      - 对盟友使用致命武力
    skill_levels:                  # 技能等级（0.0-1.0）
      sword: 0.8
      lockpicking: 0.3
      observation: 0.7

  physical_profile:                # 身体数据
    height_cm: 175.0
    weight_kg: 70.0
    body_width_cm: 50.0            # 影响通过窄通道的判定
    movement_mode: normal_walking  # 移动方式
    strength: 0.5                  # 力量系数，影响可搬运重量（力量×50=可搬运kg数）

  attributes:                      # 自定义数值属性（详见属性系统章节）
    stamina: {name: 体力, value: 100, max: 100}
    sanity: {name: 理智, value: 80, max: 100, hidden: true}

  inventory: []                    # 初始物品栏（物品 ID 列表）
  subconscious_rules:              # 潜意识修正规则
    - 在公开场合不承认超自然现象的存在
  subconscious_memory:             # 潜意识记忆（影响行为倾向）
    - 你曾在类似情况下被背叛过，所以你天生不信任何人
  speech_examples:                 # 语言风格示例
    - 我不需要你的怜悯。
    - 这件事不需要讨论。
```

### 玩家位置推断

如果未显式设置 `position`，系统按以下优先级自动推断：
1. 检查 `starting_location_id` 指向的场所中是否有物体，定位在物体附近
2. 扫描所有场所中是否包含有位置的物体
3. 定位在第一个 NPC 附近
4. 回退为 `{x: 0, y: 0, z: 0}`，同时记录警告事件

---

## NPC 定义

```yaml
characters:
  - id: knight_rain       # 必需：唯一标识符
    name: 雷恩            # 必需：显示名称
    personality:          # 可选，但有默认值
      traits:             # 性格特征（形容词列表）
        - 忠诚
        - 沉默
        - 敏锐
      motivations:        # 内在驱动力
        - 保护主角
        - 寻找失踪的妹妹
      speech_style: 寡言但精准，偶尔流露出深藏的温柔  # 说话风格描述
      background: 曾是王都骑士团的成员，在一次任务失败后自我放逐  # 背景故事
    position: {x: 3, y: 0, z: 1}   # 初始坐标
    inventory: []                  # 初始物品栏
    relationships:                 # 初始好感度（-1.0 ~ 1.0）
      player: 0.3
    attributes:                    # 数值属性
      loyalty: {name: 忠诚度, value: 70, max: 100}
    speech_examples:               # 语言风格示例
      - 我建议你不要走那条路。
      - 我曾经见过这样的东西……在很远的地方。
```

### 好感度系统

- 范围 `-1.0`（极端厌恶）到 `1.0`（极度喜爱）
- NPC 与玩家互动时，情绪倾向会影响关系数值：
  - 正面情绪（友好、开心、感激等）→ `+0.05`
  - 负面情绪（愤怒、敌意、厌恶等）→ `-0.05`
- 好感度变化后会被写入事件日志，并影响 NPC 后续行为倾向

### NPC 感知范围

NPC 的视野和交互范围硬编码为 **20 米**（与玩家的可配置不同）。

---

## 属性系统

属性是挂在玩家和 NPC 上的自定义数值（或非数值）状态。引擎通过三条路径自动更新属性：

```
natural_attribute_delta:
  ├─ apply_natural_attribute_deltas()     ← natural_delta_per_minute × tick_duration
  ├─ apply_deterministic_attributes()     ← 系统自动计算的 locked 属性
  └─ (diff → sensory_filter)

attribute_update (LLM, 并行):
  └─ apply_attribute_changes()            ← LLM 根据事件判断的属性变化
```

### 属性字段

```yaml
attributes:
  stamina:
    name: 体力                        # 显示名称
    value: 100                        # 当前值（可为 float/int/str/bool/list）
    min: 0                            # 最小值（可选）
    max: 100                          # 最大值（可选）
    natural_delta_per_minute: -0.1    # 每分钟自然变化量（默认 0）
    description: 身体和精神精力的储备   # 描述文本
    hidden: false                     # 是否隐藏（不在默认 UI 中展示）
    locked: false                     # LLM 是否不可修改（但引擎可计算）
    unit: ""                          # 单位（如 "cm", "bpm", "ml"）
    tags: []                          # 分类标签
```

### 属性值类型

| 类型 | 示例 | 说明 |
|---|---|---|
| `float` | `value: 100.0` | 数值型，支持 min/max 裁剪和 natural_delta_per_minute |
| `int` | `value: 5` | 同 float 处理 |
| `str` | `value: "latent"` | 字符串型（如阶段名、状态名） |
| `bool` | `value: false` | 布尔型（如标记位） |
| `list` | `value: []` | 列表型（如状态集合、标签集合） |

非数值属性更新时 LLM 必须用 `new_value` 而非 `delta`。

### `natural_delta_per_minute`

每游戏分钟的自然漂移速率。引擎在 `natural_attribute_delta` 节点中自动应用：

```
实际变化 = natural_delta_per_minute × tick_duration_minutes
```

- 正值：随时间增加
- 负值：随时间减少
- `0.0`：无自然变化

示例：
```yaml
fatigue:
  name: 疲劳
  value: 10
  min: 0
  max: 100
  natural_delta_per_minute: 0.1    # 每分钟增加 0.1 点疲劳
```

### `locked`（锁定属性）

`locked: true` 的属性 **LLM 无法修改**（`_apply_delta` / `_apply_new_value` 会拦截），但引擎的 `apply_deterministic_attributes()` 可以直接操作它们。

适用场景：需要系统根据多个属性的组合逻辑自动计算状态的属性。

### `hidden`（隐藏属性）

`hidden: true` 的属性不会在默认 UI 中展示给玩家，但仍参与检定和 NPC 行为判断。

---

## 世界规则注入

通过 `world_rules` 字段向引擎注入场景特定的规则，或禁用不适用的默认规则。

### 完整结构

```yaml
world_rules:
  physics:
    disable: [8]       # 禁用的默认物理规则编号（1-based）
    append:            # 追加的场景物理规则
      - "11. **异常重力区域**：废墟内部的重力方向不稳定，所有物体和角色的重量感知可能失准。"
      - "12. **低温环境**：气温-15°C下，裸露金属表面会结冰，需做防滑判定。"
  attribute:
    disable: []        # 禁用的默认属性规则编号
    append:            # 追加的属性变化规则
      - "接触远古石碑时：sanity下降2-8点，corruption_resistance下降1-3点。"
      - "在毒雾区域停留时：stamina每tick额外下降1-3点。"
  deterministic:
    disable: [3]       # 禁用的内置系统预判规则编号
    append:            # 追加的确定性规则
      - id: sanity_gate
        description: 精神崩溃时多数行动受限
        condition: "if(player.sanity < 20, blocked; player.sanity < 40, uncertain:0.3; allowed)"
      - id: heavy_lift
        description: 搬运重物时，力量不足会直接失败
        match_action: "搬运|抬起|举起|推动|拖动"
        condition: "if(player.strength * 50 < target.weight, uncertain:0.3; allowed)"
```

### Physics 规则（`world_rules.physics`）

注入到物理引擎 LLM 的 system prompt 中，增加或替换物理推演规则。

- **`disable`**：要移除的默认物理规则编号列表（1-based）
- **`append`**：追加的自由文本规则列表（从规则 11 开始编号，之后 12、13...）

默认物理规则共 10 条，涵盖重力、碰撞检测、连锁反应、声音传播等基础物理。

### Attribute 规则（`world_rules.attribute`）

注入到属性更新 LLM 的 system prompt 中，影响 LLM 如何判断属性变化。

- **`disable`**：要移除的默认属性规则编号列表（1-based）
- **`append`**：追加的自由文本规则列表

默认属性规则共 7 条。

### Deterministic 规则（`world_rules.deterministic`）

注入到 Python 侧的系统规则预判中。在 LLM 判断行动可行性之前，先用确定性 Python 逻辑做预判。

- **`disable`**：要禁用的内置规则编号列表：

| 编号 | 规则 | 说明 |
|---|---|---|
| `1` | `blocked_common_actions` | 人设限制：禁止的行动 |
| `2` | `allowed_extraordinary_actions` | 超凡能力：允许的超常规行动 |
| `3` | `strength_vs_weight` | 力量 vs 重量：`player.strength * 50` vs `target.weight_kg` |
| `4` | `skill_vs_lock` | 开锁技能 vs 锁难度 |
| `5` | `body_width_vs_passage` | 身体宽度 vs 通道宽度 |

- **`append`**：追加的自定义规则列表，每条规则包含：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | str | 唯一标识符 |
| `description` | str | 规则描述 |
| `match_action` | str（可选） | 正则表达式，匹配行动文本 |
| `condition` | str（可选） | `if(...)` 表达式语法，支持数值条件 |
| `feasibility` | str | 命中后的判定结果：`allowed` / `blocked` / `uncertain` |
| `probability` | float（可选） | 若 `feasibility` 为 `uncertain`，需指定成功概率（0 < p < 1） |

规则必须有 `match_action` 或 `condition`（至少一个）。自定义规则按 YAML 中的顺序检查，第一条命中即作为系统预判。解析或求值失败的自定义规则会记录 warning 并被跳过，不中断游戏。

#### Deterministic 条件表达式语法

使用 `if(condition1, result1; condition2, result2; else_result)` 格式：

```
if(player.sanity < 20, blocked; player.sanity < 40, uncertain:0.3; allowed)
```

支持的操作：
- **比较**：`<`、`>`、`=`、`<=`、`>=`、`!=`
- **算术**：`+`、`-`、`*`、`/`
- **聚合**：`min(a, b)`、`max(a, b)`
- **分组**：`(a + b) * c`
- **变量前缀**：
  - `player.` → 读取玩家属性、技能（`player.stamina`）、物理数据（`player.strength`）、能力限制等
  - `target.` → 读取目标物体属性，支持别名：`target.weight` → `weight_kg`、`target.width` → `effective_width_cm` / `width_cm`

### Locked 属性自动计算（`world_rules.locked_attributes`）

`locked: true` 属性的值由引擎自动计算，LLM 无法修改。通过 `locked_attributes` 列表声明计算规则，每条规则包含 `type` 字段和类型特定的参数。

#### 四种规则类型

**`timer`** — 当 condition 满足时累加 tick_duration_minutes，否则重置为 0。跨越阈值时写 warning 事件：

```yaml
- type: timer
  timer_key: alert_timer              # 被累加的属性 key
  condition: "danger > 0"             # 何时累加（纯布尔表达式）
  thresholds: [10, 30]                # 阈值列表（分钟），跨越时触发 warning
  warning: "警报已持续{threshold}分钟。"  # warning 模板，{threshold} 替换为实际值
```

**`stage`** — 按优先级条件链判定阶段，单向不可逆（阶段只进不退）：

```yaml
- type: stage
  stage_key: phase                    # 被设置的属性 key
  stages: [one, two, three]           # 有序的阶段名列表
  rules:                              # 优先级从高到低的条件链
    - condition: "progress >= 80"     # 条件满足 → 设置对应 stage
      stage: three
    - condition: "progress >= 50"
      stage: two
    - stage: one                      # 无 condition = fallback（默认）
```

**`snapshot`** — 将一个属性的当前值快照保存到另一属性，供后续 tick 比较：

```yaml
- type: snapshot
  source_key: position                # 源属性 key
  snapshot_key: _prev_position        # 快照目标 key（不存在则自动创建）
```

**`list_constraint`** — 当 condition 满足时向列表属性追加值（不重复追加）：

```yaml
- type: list_constraint
  list_key: flags                     # 列表属性 key
  condition: "threshold > 3"          # 触发条件
  value: alert                        # 要追加的值
```

#### Condition 表达式语法

与 deterministic 规则的 `if(...)` 不同，locked_attributes 的 condition 是**纯布尔表达式**：

| 能力 | 示例 |
|---|---|
| 数值比较 | `hp < 100` |
| 字符串比较 | `stage == "active"` |
| 布尔比较 | `flag == true` |
| 算术运算 | `max_value - current_value < 15` |
| 逻辑或/与 | `val < 100 or val > 180`、`x > 30 and x < 60` |
| abs 函数 | `abs(value - _prev_value) < 0.001` |
| 分组 | `(a + b) / 2 > c` |

所有标识符自动解析为当前实体的属性值。关键字：`true`→True、`false`→False、`null`→None。

#### 规则执行顺序

规则按 YAML 声明顺序执行。若 timer 的 condition 引用了 snapshot 属性，snapshot 规则必须声明在 timer 之前。

#### 向后兼容

`locked_attributes` 缺失或为空列表时，`apply_deterministic_attributes()` 直接返回（no-op）。所有不涉及 locked 属性的现有场景无需修改。

---

## 叙事风格控制

通过 `narrative_style` 字段控制 `narrative_stylize` 节点的输出文风：

```yaml
narrative_style:
  style_description: 战锤40K哥特式军事科幻风格。宏大、黑暗、悲壮，带有史诗感和沉重的宿命感。
  style_example: |
    离子风暴的紫光照亮了登陆平台。金属在风暴中震颤，仿佛是行星本身也在抗拒他们的到来。
    塔维茨按下了风暴鸟的舱门释放钮。液压系统嘶鸣着，像一头垂死的巨兽。
```

- `style_description`：对期望文风的口头描述（几句话即可）
- `style_example`：一段参考文段，展示目标文风的实际样貌
- 两者均可为空，此时使用引擎内置默认文风

---

## 游戏时间与 Tick 速度

### 静态模式（`ticks_per_game_minute`）

文件顶层的 `ticks_per_game_minute` 定义每个 tick 推进多少游戏分钟：

```yaml
ticks_per_game_minute: 0.5    # 每 tick = 2 游戏分钟
ticks_per_game_minute: 1.0    # 每 tick = 1 游戏分钟
ticks_per_game_minute: 0.2    # 每 tick = 5 游戏分钟（默认）
```

### 动态模式

当 `tick_speed_resolve` 节点启用后，引擎会根据当前游戏情境（战斗、旅行、对话等）自动调整 tick 代表的游戏时间长短（0.5-30 分钟）。此时 `ticks_per_game_minute` 作为初始参考值。

### 初始游戏时间

```yaml
game_time:
  hour: 5      # 0-23
  minute: 15   # 0-59
```

时段（`environment.time_of_day`）会根据 `game_time.hour` 自动推断：
- 5-7 → 清晨
- 8-11 → 上午
- 12-13 → 中午
- 14-17 → 下午
- 18-19 → 傍晚
- 20-23 → 夜晚
- 0-4 → 深夜

---

## 存档兼容性

存档保存 `GameState` 的持久字段（JSON 格式）。以下字段**不会**写入存档（它们是每 tick 重建的瞬态）：

- `player_input`、`player_action`
- `action_intents`、`physics_outcomes`
- `tick_duration_minutes`、`attribute_deltas`

修改 `GameState` 结构时需同步更新 `strip_transient_state()` 和 `normalize_state()`。

存档中会保留：
- 玩家和 NPC 的完整属性状态
- 世界状态（物体位置、状态等）
- `event_log`、`narrative_history`
- `world_rules`、`narrative_style`

因此，修改 init YAML 的结构后加载旧存档可能不兼容（旧存档缺少新增字段）。`normalize_state()` 中所有字段都有默认值以提供向后兼容。

---

## 完整字段参考

### `world.locations[]` 字段

| 字段 | 必需 | 类型 | 默认值 |
|---|---|---|---|
| `id` | 是 | str | — |
| `name` | 是 | str | — |
| `description` | 是 | str | — |
| `connections` | 否 | dict[str,str] 或 list[str] | `{}` |
| `ambient_light` | 否 | str | `"bright"` |
| `ambient_sound` | 否 | str | `"quiet"` |
| `properties` | 否 | dict | `{}` |

### `world.objects[]` 字段

| 字段 | 必需 | 类型 | 默认值 |
|---|---|---|---|
| `id` | 是 | str | — |
| `object_type` | 是 | 枚举（11种） | — |
| `name` | 是 | str | — |
| `description` | 是 | str | — |
| `position` | 否 | `{x, y, z}` | `{0,0,0}` |
| `state` | 否 | dict | `{}` |
| `properties` | 否 | dict | `{}` |

### `player` 字段

| 字段 | 必需 | 类型 | 默认值 |
|---|---|---|---|
| `name` | 否 | str | `"玩家"` |
| `persona` | 否 | str | `""` |
| `position` | 否 | `{x, y, z}` | 自动推断 |
| `capabilities` | 否 | dict | 见下文 |
| `physical_profile` | 否 | dict | 见下文 |
| `attributes` | 否 | dict[str,Attribute] | `{}` |
| `inventory` | 否 | list[str] | `[]` |
| `subconscious_rules` | 否 | list[str] | `[]` |
| `subconscious_memory` | 否 | list[str] | `[]` |
| `speech_examples` | 否 | list[str] | `[]` |

### `player.capabilities` 字段

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `sight_range_m` | float | `50.0` | 视野范围（米） |
| `hearing_range_m` | float | `100.0` | 听力范围（米） |
| `field_of_view_degrees` | float | `120.0` | 视野角度 |
| `special_senses` | list[str] | `[]` | 特殊感官 |
| `allowed_extraordinary_actions` | list[str] | `[]` | 允许的超凡行动 |
| `blocked_common_actions` | list[str] | `[]` | 禁止的普通行动 |
| `skill_levels` | dict[str,float] | `{}` | 技能等级（0.0-1.0） |

### `player.physical_profile` 字段

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `height_cm` | float | `None` | 身高（cm） |
| `weight_kg` | float | `None` | 体重（kg） |
| `body_width_cm` | float | `None` | 身体宽度（cm），影响通过窄通道判定 |
| `movement_mode` | str | `"walk"` | 移动方式 |
| `strength` | float | `None` | 力量系数，`strength * 50` = 最大搬运重量（kg） |

### `characters[]` 字段

| 字段 | 必需 | 类型 | 默认值 |
|---|---|---|---|
| `id` | 是 | str | — |
| `name` | 是 | str | — |
| `personality.traits` | 否 | list[str] | `[]` |
| `personality.motivations` | 否 | list[str] | `[]` |
| `personality.speech_style` | 否 | str | `"casual"` |
| `personality.background` | 否 | str | `""` |
| `position` | 否 | `{x, y, z}` | `{0,0,0}` |
| `inventory` | 否 | list[str] | `[]` |
| `relationships` | 否 | dict[str,float] | `{}` |
| `attributes` | 否 | dict[str,Attribute] | `{}` |
| `speech_examples` | 否 | list[str] | `[]` |

### Attribute 字段

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `name` | str | `""` | 显示名称 |
| `value` | Any | `0.0` | 当前值（float/int/str/bool/list） |
| `min` | float | `None` | 最小值 |
| `max` | float | `None` | 最大值 |
| `natural_delta_per_minute` | float | `0.0` | 每分钟自然变化量 |
| `description` | str | `""` | 描述文本 |
| `hidden` | bool | `false` | 是否在 UI 中隐藏 |
| `locked` | bool | `false` | LLM 是否不可修改 |
| `unit` | str | `""` | 单位 |
| `tags` | list[str] | `[]` | 分类标签 |

---

## 示例文件

以下文件可直接参考：

| 文件 | 说明 |
|---|---|
| `public_start/test_empty.yaml` | 最简测试场景：3 个场所、4 个物体、无 NPC、2 个属性 |
| `public_start/whisperheads.yaml` | 完整战锤40K场景：7 场所、8 物体、6 NPC、8 属性、潜意识规则、world_rules（禁用物理规则 8 + 追加 5 条物理 + 3 条属性）、narrative_style |
| `public_start/murder.yaml` | 完整战锤40K场景：8 场所、11 物体、5 NPC、7 属性、world_rules（追加 5 条物理 + 5 条属性）、narrative_style |


---

## 相关文件索引

| 关注点 | 入口文件 |
|---|---|
| Pydantic 校验模型 | `src/models/config.py` |
| 确定性规则解析 | `src/game/deterministic_rules.py` |
| 条件表达式求值 | `src/game/condition_eval.py` |
| 行动可行性判定 | `src/game/rules.py` |
| 状态应用 | `src/game/state_apply.py` |
| 属性引擎 | `src/game/attributes.py` |
| GameState 定义 | `src/graph/game_state.py` |
| 初始化转换 | `src/agents/init.py` |
| 拆分配置加载 | `src/config/loader.py` |
| 物理系统 Prompt | `prompts/physics_system.j2` |
| 属性更新 Prompt | `prompts/attribute_update_system.j2` |
| 接口规范 | `docs/game-flow-interfaces.md` |
