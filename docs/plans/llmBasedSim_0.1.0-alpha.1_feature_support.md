# llmBasedSim 0.1.0-alpha.1 功能支持清单

> 本文定义 `0.1.0-alpha.1` 对游戏开发者承诺的功能边界。
>
> 它描述“这个版本能够支持怎样的游戏系统”，而不是某一个具体 reference game 的设计。
>
> Alpha 含义：这些能力已经可以用于实际项目验证，但 API、authoring format 与 ergonomics 在后续 alpha 中仍可能调整。

---

# 1. 核心支持模型

`0.1.0-alpha.1` 的核心定位是：

> **一个 authority-mediated、component-based、Python-extensible 的 headless simulation/game runtime。**

游戏内容可以提供：

```text
GameProject
+ authoring data
+ custom actions
+ custom numerical / simulation logic
```

引擎负责：

```text
load
→ materialize
→ action execution
→ dynamics
→ authority
→ transaction
→ reducer
→ authoritative WorldState
```

---

# 2. World / Entity / Component

## 支持

### Entity

支持以 entity 表示：

- 玩家；
- NPC / actor；
- item / object；
- location；
- 项目自定义实体类别。

### Component

支持 entity 携带 JSON-native component data。

Kernel 对自定义 component 保持语义无关。

游戏可以用 component 表示例如：

```text
stats
inventory state
item metadata
equipment state
durability
resource state
physical parameters
AI state
environment values
custom state machines
```

以上仅为数据形状示例，不代表 engine 内置这些玩法语义。

### Initial authoritative state

alpha.1 支持 GameProject 中已有的核心作者数据在 tick 0 直接进入 authoritative WorldState，包括：

- Player / Character attributes；
- Player / Character initial inventory；
- Item/Object state；
- Item/Object properties；
- object identity / description / type 等运行时需要的数据。

---

# 3. 自定义数值系统

## 支持

游戏可定义任意 JSON-compatible 数值字段，例如：

```text
int
float
bool
string enum-like value
list
nested object
```

项目可以拥有任意数量的业务数值。

Engine 不要求固定的：

```text
HP
MP
STR
DEX
armor
damage
```

字段。

这些完全由游戏定义。

## 支持的操作

Custom ActionExecutor / DynamicsBackend 可以：

- 读取数值；
- 对数值执行自定义计算；
- 根据当前状态决定 outcome；
- 通过 ProposedEffect 替换 component；
- 一次修改多个 entity / component。

## 暂不承诺

alpha.1 不提供完整通用的：

- derived stat graph；
- buff/debuff framework；
- modifier stacking；
- attribute locking；
- stat dependency resolver；
- formula DSL。

这些可由游戏 extension 自行实现。

---

# 4. Item / Object

## 支持

每个 item/object 可以拥有：

- authoritative identity；
- name / description；
- object type；
- arbitrary state；
- arbitrary properties。

因此不同 item 可以有完全不同的数据结构和业务参数。

## 支持自定义 interaction metadata

游戏可以把 interaction mode / interaction profile 存在 item properties 或相关 component 中。

Custom executor 可以读取这些信息并选择对应行为。

因此 engine 支持：

```text
同一通用 action
→ 根据 target item 数据
→ 分派到不同业务逻辑
```

也支持：

```text
不同 action id
→ 绑定不同 custom executor
```

## 不限制 interaction 类型

engine 不限定 item interaction 必须属于预设词表。

游戏可以定义自己的 interaction 语义。

## 暂不承诺

alpha.1 不内置完整：

- equipment slot system；
- stackable item framework；
- container-in-container；
- crafting framework；
- trade/economy framework；
- ownership law；
- encumbrance rules。

---

# 5. Inventory

## 支持

Player / Character 可以拥有 authoritative initial inventory。

inventory 中的 item reference 使用 authoritative entity ID。

游戏可通过 custom actions 修改 inventory component。

## 支持游戏侧自定义规则

项目可以自行实现：

- capacity；
- pickup restrictions；
- drop restrictions；
- weight limit；
- category limit；
- ownership；
- item availability；
- item state-dependent access。

## 暂不承诺

alpha.1 不把上述规则实现成 engine-level inventory framework。

---

# 6. Custom Actions

## 支持

GameProject 可以声明自定义 action。

Python extension 可以为 action 绑定自定义 `ActionExecutor`。

基础运行模型：

```text
ActionProposal
+ WorldState
→ ActionExecutor
→ ExecutorResult
```

## ActionExecutor 可支持

- 任意参数解析；
- actor / target lookup；
- arbitrary component reads；
- item/object property reads；
- custom validation；
- custom numerical calculation；
- external pure-Python solver 调用；
- 0..N ProposedEffect 输出；
- deterministic failure。

## Multi-effect action

一个 action 可以同时提议多个 world changes，例如：

```text
entity A component X
entity A component Y
entity B component Z
world variable W
```

是否合法提交由 authority / validation / conflict resolution / transaction 决定。

## 暂不承诺

- long-running action；
- action progress；
- interrupt/resume lifecycle；
- timed action completion；
- scheduler-backed duration semantics。

---

# 7. 自定义物理 / 数值仿真

## 支持

项目可以实现任意 Python numerical / physics solver。

solver 可以被：

```text
ActionExecutor
```

调用，也可以作为：

```text
DynamicsBackend
```

的一部分运行。

## 支持的 solver 类型

从 engine contract 角度，不限制为某一具体方法，可包括：

- analytical rules；
- finite-state model；
- ODE step；
- algebraic solver；
- deterministic numerical integration；
- geometry calculation；
- collision-like calculation；
- probability-free deterministic model；
- domain-specific scientific model。

如果需要随机模型，alpha.1 应由项目自行保证 seed 与 deterministic replay policy；不将随机运行时作为首版核心承诺。

## Authority requirement

solver 不能直接改变 authoritative WorldState。

正式链路必须是：

```text
solver
→ structured outcome
→ ProposedEffect
→ Authority
→ Validation
→ Conflict Resolution
→ Transaction
→ Reducer
```

---

# 8. Dynamics / Continuous World Evolution

## 支持

Project extension 可以注册 custom `DynamicsBackend`。

基础接口：

```text
WorldSnapshot
+ DynamicsContext
→ ProposedEffect(s)
```

DynamicsBackend 可以用于：

- environment evolution；
- resource regeneration/decay；
- autonomous state-machine evolution；
- numerical integration；
- global simulation state；
- time-dependent system evolution。

## 支持读取

- current WorldState；
- arbitrary components；
- world variables；
- current logical tick；
- dynamics context。

## 支持写入

经 authority grant：

- entity components；
- Kernel state domains，例如 world variables。

---

# 9. 时间系统

## 支持双层时间概念

alpha.1 明确支持：

```text
logical_tick
```

与：

```text
game/world time
```

分离。

### logical_tick

含义：

> Kernel 的确定性因果推进步。

保持单位无关。

### world time

含义：

> 游戏定义的模拟时间状态。

可以存储在 authoritative WorldState 中。

## 支持动态 world-time rate

每个 logical tick 对应的 world-time increment 可以由当前 WorldState 动态决定。

抽象表达：

```text
Δworld_time = f(WorldState)
```

因此游戏能够实现：

- 不同 state machine 状态对应不同时间倍率；
- 不同 gameplay mode 对应不同 world-time 推进；
- 环境状态改变时间步；
- activity state 改变时间步；
- project-specific fast/slow time。

Engine 不内置上述业务规则。

## 暂不支持

alpha.1 不承诺：

```text
logical_tick duration = f(WorldState)
```

也就是说，不动态改变 Kernel logical tick 本身的语义。

---

# 10. Authority-Mediated State Mutation

这是 alpha.1 的核心承诺。

## 支持

Authoritative state mutation 必须走：

```text
Producer
→ ProposedEffect
→ Authority Check
→ Validation
→ Conflict Resolution
→ Transaction
→ Reducer
→ WorldState
```

## Component authority

支持按 component type 对 producer 授权。

## Kernel state-domain authority

支持对 Kernel state domain 进行正式授权，包括 alpha.1 所需的：

```text
world_variables
scenario_state
```

## Closed-by-default

没有获得授权的 producer 不应自动获得写权限。

## 不允许

Project extension / numerical solver / NPC policy 不应拥有直接 authoritative write path。

---

# 11. Failure / Rejection Semantics

## 支持

ActionExecutor 可以返回 deterministic failure。

failure 时：

- 不产生 authoritative mutation；
- world revision 不应被伪造推进；
- failure 可以被 runner / diagnostics 观察。

Authority deny 时：

- denied effect 不应进入 committed authoritative mutation。

无效 effect：

- 应由 validation / transaction pipeline 显式处理；
- 不应静默写入 WorldState。

---

# 12. Determinism

## 核心承诺

对于不使用外部非确定源的项目：

```text
same initial project
+ same inputs
+ same action order
+ same advance sequence
→ same resulting authoritative state
```

这是 alpha.1 E2E 的必测能力。

## 不承诺

alpha.1 不提供完整 replay debugger 或 timeline browser。

---

# 13. Project Python Extensions

## 支持

项目可通过受信任 Python extension 注册：

- ActionExecutor；
- DynamicsBackend；
- producer grants；
- extension-side policies（若使用）。

## Trust boundary

Python extension 必须显式启用 trust。

默认不应无条件加载任意项目 Python 代码。

## Extension autonomy

项目 extension 可以自行组织：

```text
rules
solvers
interaction dispatch
state machines
numerical models
domain-specific logic
```

Engine 不要求这些内容全部转写为 DSL。

---

# 14. Headless Runtime

## 支持

alpha.1 可以在没有：

- LLM；
- WebUI；
- graphical frontend；

的情况下运行完整核心 simulation loop。

项目可以：

```text
assemble
submit action
advance
inspect state
inspect trace/result
```

作为最基本运行方式。

---

# 15. Validation / Diagnostics

## 支持

现有：

```text
llmsim validate <project>
```

继续作为项目静态 validation 入口。

alpha.1 应能够诊断至少：

- project format error；
- unresolved authoring reference；
- extension loading error；
- duplicate/conflicting binding；
- invalid authority path；
- runtime failure 中已有诊断类型。

## 不承诺

完整 developer control plane 不属于 alpha.1。

---

# 16. LLM 支持状态

## 可存在，但不是 alpha.1 核心能力承诺

当前 runtime 已有 LLM policy 相关实现，但 `0.1.0-alpha.1` 的发布验收不依赖真实 LLM。

这意味着：

- headless / deterministic game 是一级支持场景；
- LLM NPC 可继续实验使用；
- LLM integration failure 不应阻断非 LLM project。

## 本版本不承诺

- production-grade NPC orchestration；
- multi-agent scheduling；
- prompt IDE；
- memory system completeness；
- critic loop completeness；
- LLM-based physics authority。

---

# 17. 当前明确不支持或不保证的游戏能力

以下均不属于 `0.1.0-alpha.1` support contract：

- long action lifecycle；
- action interruption；
- scheduler-backed travel/sleep/work duration；
- event/stimulus → dynamics routing；
- continuous sub-tick simulation；
- dynamic Kernel logical-tick size；
- full declarative Authority authoring；
- P5 DSL rule execution completeness；
- arbitrary component YAML authoring；
- complete equipment system；
- complete inventory framework；
- crafting；
- economy；
- quest system；
- dialogue system；
- combat framework；
- relationship framework；
- persistence UX；
- save slots；
- replay debugger；
- timeline branching UX；
- multiplayer；
- networking；
- Web game client；
- graphical rendering；
- DSH / Agent-Team integration；
- hot reload；
- plugin sandbox/security isolation beyond current trust gate；
- backward compatibility guarantee across future alpha versions。

这些并非都“不可能实现”，而是 **alpha.1 不提供 engine-level guarantee**。

---

# 18. 对游戏类型的实际表达能力

`0.1.0-alpha.1` 不针对某一个具体 genre。

只要游戏核心状态能够表达为：

```text
entities
+ JSON-native components
+ world variables
```

核心操作能够表达为：

```text
ActionProposal
→ custom deterministic logic
→ ProposedEffect(s)
```

连续/周期演化能够表达为：

```text
WorldSnapshot
→ custom DynamicsBackend
→ ProposedEffect(s)
```

那么它就在 alpha.1 的目标支持范围内。

因此本版本验证的是一种 **simulation substrate**，而不是预设的 RPG、Galgame、战棋或其他固定玩法框架。

---

# 19. alpha.1 功能支持总表

| 能力 | 状态 |
|---|---|
| GameProject load / validate | **支持** |
| GameProject → authoritative initial WorldState | **支持** |
| Player / Character attributes materialization | **支持** |
| Initial inventory materialization | **支持** |
| Item state / properties materialization | **支持** |
| Arbitrary JSON component runtime storage | **支持** |
| Custom ActionExecutor | **支持** |
| Custom item interactions | **支持，项目侧实现** |
| Multi-effect action | **支持** |
| Independent pure-Python numerical solver | **支持** |
| Custom DynamicsBackend | **支持** |
| Component authority | **支持** |
| Kernel state-domain authority | **支持** |
| World-variable mutation through Kernel | **支持** |
| Dynamic world-time rate | **支持** |
| Dynamic logical-tick duration | **不支持** |
| Deterministic headless runtime | **支持** |
| Action failure without mutation | **支持** |
| Authority deny without mutation | **支持** |
| Long action lifecycle | **不支持** |
| Scheduler-backed game duration | **不支持** |
| Action → Stimulus → Dynamics routing | **不支持** |
| Generic arbitrary component YAML DSL | **不支持** |
| Full inventory framework | **不支持** |
| Full attribute framework | **不支持** |
| Full combat framework | **不支持** |
| Full equipment framework | **不支持** |
| LLM NPC | **实验性存在，但非 alpha.1 发布承诺** |
| Web UI | **非 alpha.1 支持范围** |
| Persistence / save UX | **非 alpha.1 支持范围** |
| Replay debugger | **非 alpha.1 支持范围** |
| DSH / agent-native control plane | **非 alpha.1 支持范围** |

---

# 20. Version Contract

只有当以下四条同时成立时，才可以对外称为 `0.1.0-alpha.1`：

1. **Authoring data really becomes authoritative state.**
2. **Project-defined logic can really produce authoritative state changes through Kernel mediation.**
3. **Component and state-domain authority both work in production assembly.**
4. **A headless project can run deterministically from clean install without test-only assembly.**

这四条是本版本真正的功能边界。
