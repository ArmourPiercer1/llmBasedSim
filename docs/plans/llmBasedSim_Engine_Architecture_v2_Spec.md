# llmBasedSim Engine Architecture v2 设计规范

> 文档状态：Draft v0.1  
> 目标版本：Engine Architecture v2  
> 适用对象：Engine Core 开发者、Official Module 开发者、第三方插件开发者、Coding Agent、GUI/CLI 开发者  
> 设计目标：为 LLM-native 角色扮演游戏建立一个可扩展、可调试、可回放、Agent-native 的运行时与开发框架

---

# 0. 文档定位

本文档定义 `llmBasedSim Engine Architecture v2` 的**规范性架构**。

它的目标不是描述“当前代码是如何工作的”，而是规定下一代引擎：

- 哪些概念必须稳定存在；
- 哪些状态属于 Engine Kernel；
- 哪些能力必须通过接口暴露；
- 哪些行为可以由游戏开发者替换；
- LLM、规则、Python 系统、数值后端如何共同修改世界；
- 时间、事件、空间、角色、Prompt、模型能力、存档与调试如何统一；
- Coding Agent、GUI、CLI 如何成为引擎开发客户端；
- 当前 v1 原型应当保留、替换或废弃哪些部分。

本文档中的关键字使用以下约定：

- **MUST**：实现必须满足；
- **MUST NOT**：实现禁止违反；
- **SHOULD**：强烈建议，除非有明确理由；
- **MAY**：可选；
- **DEFAULT**：官方默认实现，不属于强制内核语义。

---

# 1. 产品定义

## 1.1 核心定位

`llmBasedSim` 定义为：

> **一个面向 LLM-native 角色扮演游戏的 authority-mediated simulation engine。**

其核心思想不是“LLM 主导世界”，也不是“确定性规则永远优先于 LLM”，而是：

```text
Game Developer defines authority
        ↓
Rules / Python / Numerical Models / LLM
can all propose world consequences
        ↓
Kernel mediates:
permission
validation
conflict
causality
commit
replay
```

因此：

> **LLM、确定性规则、脚本、数值物理后端、AI Policy 都是世界变化的合法来源，但没有任何来源可以绕过 Kernel 的提交机制直接修改 authoritative state。**

## 1.2 第一阶段核心游戏类型

Engine v2 第一阶段优先服务：

1. Galgame / Visual Novel；
2. 沙盒角色扮演；
3. 战术 / 战棋 RPG。

这三类游戏不是三个独立 runtime，而是同一个持续世界在不同：

- GameplayMode；
- SpaceBackend；
- TimePolicy；
- PresentationBackend；
- Action Registry；
- DynamicsBackend；

组合下运行。

## 1.3 第一目标开发者

第一目标用户：

> **会少量 Python 的独立游戏开发者。**

后续扩展顺序：

1. B：少量 Python 开发者；
2. A：不懂编程的内容作者；
3. C：熟练 Python 的高级开发者；
4. D：重度技术型/科研型开发者。

因此 v2 的首要 DX 目标不是“完全无代码”，而是：

- 项目结构清晰；
- YAML/配置简单；
- Python extension 边界稳定；
- Coding Agent 易于理解；
- 错误机器可解析；
- Runtime 可追踪、可重放、可分支。

---

# 2. 总体架构

```text
┌──────────────────────────────────────────────────────┐
│                    Game Project                      │
│                                                      │
│ Content / Rules / Actions / Characters / Policies   │
│ Prompts / Modules / Python Extensions                │
└───────────────────────┬──────────────────────────────┘
                        │ load / compile
                        ▼
┌──────────────────────────────────────────────────────┐
│                     ProjectIR                        │
│ Canonical in-memory project representation           │
└───────────────────────┬──────────────────────────────┘
                        │ instantiate
                        ▼
┌──────────────────────────────────────────────────────┐
│                   Engine Kernel                      │
│                                                      │
│ World / Session                                      │
│ State / Revision                                     │
│ Scheduler / Clock                                    │
│ Action Lifecycle                                     │
│ Effect / Authority / Validation / Conflict           │
│ Reducer / Transaction                                │
│ Event / Provenance                                   │
│ Plugin Registry                                      │
│ Save / Replay / Checkpoint                           │
│ Capability / Context                                 │
└──────────────┬───────────────────────┬───────────────┘
               │                       │
               ▼                       ▼
┌──────────────────────────┐   ┌────────────────────────┐
│     Official Modules     │   │   Game / Third-party   │
│                          │   │       Extensions        │
│ Attributes               │   │                        │
│ Inventory                │   │ Custom Systems         │
│ Perception               │   │ Dynamics              │
│ Knowledge                │   │ Space                  │
│ Relationships            │   │ Policies               │
│ Standard Character       │   │ Renderers              │
│ Graph/Grid/Continuous    │   │ Persistence            │
│ Tactical                 │   │ ...                    │
└──────────────┬───────────┘   └─────────────┬──────────┘
               │                             │
               └─────────────┬───────────────┘
                             ▼
┌──────────────────────────────────────────────────────┐
│                  Runtime / Agents                    │
│ Actor Policies / LLM Runtime / Dynamics / Scripts    │
└───────────────────────┬──────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────┐
│                  Presentation Plane                  │
│ Text / Generated Image / Tactical View / Web / GUI   │
└──────────────────────────────────────────────────────┘
```

---

# 3. 三个平面

Engine v2 MUST 明确区分三个平面。

## 3.1 Authoring Plane

负责：

- YAML；
- Python；
- Prompt；
- Content；
- Tests；
- Game Project Source Files。

客户端包括：

- VS Code；
- Coding Agent；
- GUI；
- CLI。

## 3.2 Development Control Plane

负责：

- validate；
- inspect；
- trace；
- test；
- run；
- pause；
- step；
- replay；
- branch；
- prompt inspect；
- scenario testing；
- runtime introspection。

它 MUST 提供机器可读接口。

第一阶段：

```text
CLI --json
```

后续 MAY 增加：

- Python API；
- Local Dev Service；
- MCP-like protocol；
- GUI connection；
- DSH plugin adapter。

## 3.3 Runtime Plane

负责：

- authoritative world；
- logical time；
- scheduler；
- active actions；
- effects；
- transactions；
- events；
- dynamics；
- actors；
- gameplay modes；
- persistence；
- inference runtime。

---

# 4. Kernel 强制不变量

以下原则属于 Engine Kernel 的强制不变量。

## K1. 单一 authoritative state

任何时刻，一个 `WorldInstance` MUST 存在唯一 authoritative world representation。

GUI、Narrator、LLM prompt、render cache、debugger view MUST NOT 成为第二套 authoritative world。

## K2. 禁止直接状态写入

任何：

- LLM；
- GameSystem；
- Script；
- DynamicsBackend；
- BehaviorPolicy；
- Plugin；

MUST NOT 绕过 Effect/Transaction 路径直接修改 authoritative WorldState。

所有状态变化 MUST 经过：

```text
Producer
  ↓
ProposedEffect
  ↓
Authority Check
  ↓
Validation
  ↓
Conflict Resolution
  ↓
Transaction
  ↓
Reducer
  ↓
WorldState
```

## K3. Authority 与 Commit 分离

“某系统拥有写权限”仅意味着：

> 它有权决定某个 state domain 的候选新状态。

这不意味着：

> 它可以直接写内存对象。

## K4. Prompt 不能定义世界权限

Prompt 可以被高级开发者替换，但：

- Knowledge Boundary；
- World Read Capability；
- State Write Authority；

MUST 由 Engine capability/authority system 控制。

## K5. Agent 是 Policy，不是 Engine

Engine MUST NOT 假设：

- 所有 NPC 都是 LLM Agent；
- 所有 NPC 使用统一 agent loop；
- LangGraph 是 runtime 基础设施。

Actor 的 `BehaviorPolicy` 只需满足输入/输出 contract。

## K6. Event 必须可追踪来源

所有 committed state change SHOULD 具有：

- transaction id；
- source producer；
- cause id；
- world revision；
- authority decision；
- resulting domain events。

## K7. Runtime 内部关键调度状态必须可检查

Scheduler、ActiveAction、GameplayMode、Actor wakeup 等关键 runtime 状态 MUST NOT 完全隐藏在不可序列化 coroutine/generator continuation 中。

## K8. Deployment 与 Game Project 分离

Game Developer MUST NOT 固定：

- provider；
- model name；
- endpoint；
- credential。

Game Project 只能声明**能力需求**与建议。

---

# 5. Project / Deployment Contract

## 5.1 GameProject

`GameProject` 是游戏作者发布和维护的项目。

它包含：

```text
project/
├─ game.yaml
├─ world/
├─ characters/
├─ items/
├─ rules/
├─ actions/
├─ prompts/
├─ scenarios/
├─ modules/
├─ tests/
├─ plugins/            # optional
├─ .llmsim/            # engine metadata / generated guidance
└─ pyproject.toml      # optional
```

## 5.2 Game Project Source of Truth

磁盘源码文件 MUST 是 Authoring Plane 的 source of truth。

Engine MAY 加载为：

```text
Source Files
    ↓
Loader
    ↓
ProjectIR
```

`ProjectIR` 是 runtime/validation 使用的 canonical in-memory representation，但不是另一个作者数据库。

## 5.3 Python 化升级

简单项目 MAY 不包含 Python package。

当项目需要高级扩展时，可以升级为：

```text
my_game/
├─ pyproject.toml
├─ game.yaml
├─ my_game/
│  ├─ __init__.py
│  ├─ systems/
│  ├─ dynamics/
│  ├─ policies/
│  └─ plugins/
└─ ...
```

## 5.4 DeploymentProfile

部署配置属于用户，而不是游戏作者。

示例：

```yaml
inference_profiles:
  major_character:
    provider: user_selected_provider
    model: user_selected_model

  world_dynamics:
    provider: local
    model: local_reasoning_model
```

该文件 MUST NOT 被游戏项目要求固定。

## 5.5 游戏可声明的 Inference Capability

开发者 MAY 声明：

```yaml
inference_requirements:
  major_character:
    context_length_min: 64000
    input_modalities:
      - text
      - image
    structured_output: required
    reasoning_class: advanced
    tool_use: optional

  narrator:
    context_length_min: 32000
    reasoning_class: standard
    style_control: preferred
```

Game Project MAY 提供：

```yaml
recommendations:
  - "major_character 建议使用高推理能力模型"
```

但 MUST NOT 出现强制 model/provider pin。

---

# 6. ProjectIR

所有声明式内容在 runtime 前 SHOULD 编译为 `ProjectIR`。

`ProjectIR` SHOULD 包含：

```text
ProjectIR
├─ manifest
├─ entity definitions
├─ component schemas
├─ action registry
├─ rule registry
├─ authority policies
├─ module graph
├─ gameplay mode definitions
├─ inference capability profiles
├─ prompt policies
├─ plugin descriptors
└─ scenario definitions
```

ProjectIR MUST 支持：

- schema validation；
- dependency validation；
- unresolved reference detection；
- authority conflict static analysis；
- machine-readable inspection。

---

# 7. World / Session Contract

## 7.1 GameProject / WorldInstance / Session 分离

```text
GameProject
    ↓ instantiate
WorldInstance
    ↓ connect
Session
```

MUST 是三个独立概念。

## 7.2 WorldInstance

`WorldInstance` 表示一个独立游戏世界运行实例。

多个存档：

```text
GameProject
├─ WorldInstance A
├─ WorldInstance B
└─ WorldInstance C
```

## 7.3 Session

`Session` 表示一个控制/观察连接。

Session MAY：

- 控制一个 actor；
- 控制 party；
- 作为 GM；
- 作为 spectator；
- 作为 debugger；
- 作为 automated test client。

## 7.4 v2 MVP 多人范围

v2 MVP 默认：

- single-process；
- one active player session；
- single authoritative runtime。

接口 MUST NOT 假设 `Session == WorldInstance`，以避免未来多人架构被锁死。

---

# 8. State Model

Engine v2 MUST 废弃当前“一个巨大的 GameState 包含一切”的模型。

## 8.1 WorldState

`WorldState` 保存游戏世界事实。

包括：

```text
WorldState
├─ entities
├─ components
├─ world variables
├─ scenario state
├─ knowledge / belief components
└─ persistent gameplay state
```

特点：

- authoritative；
- serializable；
- revisioned；
- reducer-only mutation。

## 8.2 RuntimeState

保存 runtime control state：

```text
RuntimeState
├─ logical clock
├─ scheduler queue
├─ active actions
├─ actor wakeups
├─ gameplay contexts/modes
├─ RNG state
├─ pending proposals
└─ runtime lifecycle state
```

## 8.3 BackendState

用于保存插件/数值后端私有状态。

例如：

- integrator history；
- rigid-body solver contact cache；
- GPU buffers reference；
- custom simulation state；
- external solver checkpoint。

Backend MUST 声明：

```text
checkpointable
restorable
replayable
```

如果某 backend 不支持 checkpoint，则：

- runtime MAY 正常工作；
- arbitrary branch/replay capability MAY 降级。

## 8.4 TraceState

记录：

```text
commands
action proposals
proposed effects
authority decisions
validation decisions
conflict resolution
transactions
events
LLM calls
prompt assembly metadata
development interventions
```

Trace SHOULD 可以流式持久化。

## 8.5 ViewState

`ViewState` 是 derived data。

例如：

- player observation；
- narrative input；
- image render scene description；
- tactical UI projection；
- inspector projection。

ViewState MUST NOT 成为 authoritative world。

---

# 9. Revision Model

每次成功 transaction commit 后：

```text
world_revision += 1
```

所有异步结果 SHOULD 携带：

```text
base_world_revision
observation_id
actor_state_revision
optional valid_until
```

例如：

```python
ActionProposal(
    base_world_revision=812,
    observation_id="obs_991",
    ...
)
```

提交前 MUST 执行 revalidation。

可能结果：

```text
ACCEPT
REBASE
REPAIR
REJECT
```

---

# 10. Entity / Component Contract

## 10.1 Entity

Entity 是稳定 identity。

```text
EntityId
```

MUST：

- 在 WorldInstance 内唯一；
- 可序列化；
- 可追踪；
- 不依赖 Python object memory address。

## 10.2 Component

游戏状态 SHOULD 通过 typed components 表达。

例如：

```text
Transform
Inventory
Health
Relationship
Knowledge
ActorRuntime
VisualIdentity
```

但 Kernel MUST NOT 强制固定 RPG component 列表。

## 10.3 不强制真实 ECS

公共 API 只承诺：

> Entity + typed components。

内部实现 MAY 是：

- dict；
- Pydantic；
- dataclass；
- component tables；
- ECS；
- database-backed storage。

v2 MUST NOT 提前承诺 archetype ECS。

---

# 11. Action Contract

## 11.1 固定 action literal 废弃

v1 中：

```text
move
interact
speak
use_item
wait
observe
```

不能再成为扩展边界。

## 11.2 Action Registry

Game Project / Module 可以注册：

```yaml
actions:
  unlock:
    executor: interaction.unlock
    parameters:
      target:
        type: entity
    duration_policy: lockpicking
    tags:
      - interaction
      - physical
```

## 11.3 ActionProposal

Policy 输出：

```python
ActionProposal(
    actor_id=...,
    action_id=...,
    arguments=...,
    intent=...,
    timing=...,
    confidence=...,
    fallback_action=...,
    provenance=...
)
```

## 11.4 Action Lifecycle

建议标准状态机：

```text
IDLE
  ↓
PROPOSED
  ↓
VALIDATING
  ↓
ACTIVE
  ├─ INTERRUPTED
  ├─ COMPLETED
  └─ FAILED
```

---

# 12. Actor / Policy Contract

## 12.1 Actor != Agent

Actor 是世界实体。

Agent 是某种 Policy 实现。

## 12.2 BehaviorPolicy

公共接口概念：

```python
class BehaviorPolicy(Protocol):
    async def decide(
        self,
        context: ActorDecisionContext,
    ) -> ActionProposal:
        ...
```

内部可以是：

- RulePolicy；
- ScriptedPolicy；
- LLMPolicy；
- HybridPolicy；
- PlayerPolicy；
- RemotePolicy；
- LangGraph；
- multi-agent workflow。

Kernel 不关心内部 loop。

## 12.3 Standard Character Model

官方 SHOULD 提供预设：

```text
CharacterDefinition
├─ identity
├─ baseline traits
├─ background
├─ core values
└─ long-term tendencies

CharacterState
├─ emotion
├─ goals
├─ relationships
└─ mutable psychological state

KnowledgeState
├─ beliefs
├─ known facts
├─ rumors
└─ uncertainty

Memory
└─ episodic / semantic / retrieved memory
```

但游戏作者 MAY 自定义人格结构。

---

# 13. Context / Capability Contract

## 13.1 ContextProvider

Policy 不应默认读取 entire WorldState。

它通过 ContextProvider 获得能力限定的数据。

## 13.2 Capability

例如：

```text
observation.read
knowledge.read
memory.read
world.read.local
world.read.global
physics.summary
physics.raw
trace.read
```

普通 NPC 默认：

```text
Observation + Knowledge + Memory
```

World Director MAY 获得：

```text
world.read.global
```

## 13.3 Prompt override 不提升权限

自定义 PromptAssembler MUST NOT 自动获得未授权数据。

---

# 14. Prompt Architecture

Prompt SHOULD 由可组合层构成：

```text
L0 Engine Contract
L1 Game Policy
L2 Character / Scene Policy
L3 Runtime Context
L4 Untrusted Content
```

其中 L4 包括：

- player input；
- NPC dialogue；
- item text；
- books；
- user-generated content。

这些内容 MUST 作为数据处理。

高级开发者 MAY 替换 PromptAssembler，但 capability boundary 不变。

---

# 15. Dynamics Contract

## 15.1 WorldDynamicsBackend

v2 SHOULD 使用泛化概念：

```text
WorldDynamicsBackend
```

而不是强制狭义 `PhysicsBackend`。

统一表示：

> 根据当前世界和输入刺激，生成世界后果。

## 15.2 合法实现

```text
RuleDynamics
LLMWorldDynamics
RigidBodyDynamics
TacticalDynamics
ODEDynamics
HybridDynamics
CompositeDynamics
```

## 15.3 统一接口

概念：

```python
class WorldDynamicsBackend(Protocol):
    async def simulate(
        self,
        snapshot: WorldSnapshot,
        stimuli: list[Stimulus],
        context: DynamicsContext,
    ) -> list[ProposedEffect]:
        ...
```

## 15.4 Backend metadata

SHOULD 声明：

```text
domains
determinism
implementation_type
fidelity
checkpointable
restorable
replayable
```

例如：

```yaml
implementation_type: numerical
fidelity: rigid_body_2d
determinism: seeded
```

或：

```yaml
implementation_type: llm
fidelity: semantic
determinism: nondeterministic
```

## 15.5 Composite Dynamics

Kernel 不需要区分：

- numerical physics；
- semantic inference。

Hybrid backend MAY 内部组合：

```text
Rigid Solver
+
LLM Inference
```

并统一输出 ProposedEffect。

---

# 16. Effect Contract

## 16.1 ProposedEffect

所有状态写入先成为 ProposedEffect。

建议字段：

```python
ProposedEffect(
    effect_id: EffectId,
    effect_type: str,
    source: ProducerId,
    target: EntityRef | StateDomain,
    payload: dict,
    base_revision: int,
    cause_ids: list[str],
    authority_scope: str | None,
    priority_hint: int | None,
    metadata: dict,
)
```

## 16.2 Effect Producer

可能包括：

```text
RuleEngine
ScriptSystem
BehaviorPolicy
DynamicsBackend
QuestSystem
LLM
DeveloperCommand
```

---

# 17. Authority Contract

## 17.1 AuthorityPolicy

Authority 决定：

> 某 producer 是否有权对某 domain 提出 authoritative change。

例如：

```yaml
authority:
  door.lock_state:
    allowed_writers:
      - interaction.lock_system

  minor_environmental_state:
    allowed_writers:
      - llm_world_dynamics
      - rigid_body
```

## 17.2 Authority selector

SHOULD 优先使用：

- component type；
- field；
- domain tag；
- effect type；
- entity class/tag；

而不是依赖脆弱的裸字符串路径。

---

# 18. Effect Validation

通过 authority 的 effect 仍需验证。

Validation 可以检查：

- schema；
- preconditions；
- entity existence；
- type；
- invariants；
- stale proposal；
- domain constraints。

---

# 19. Conflict Resolution

若多个合法 ProposedEffect 冲突：

```text
Move(gem, floor)
Move(gem, alice_inventory)
```

ConflictResolver 决定：

```text
winner
merge
defer
reject
repair
```

Resolver MAY 使用：

- authority priority；
- timestamp；
- producer priority；
- causality；
- gameplay mode；
- domain-specific resolver。

---

# 20. Transaction / Reducer

## 20.1 Transaction

一组最终 accepted effects 组成 transaction。

Transaction SHOULD：

- atomic commit；
- produce one world revision；
- emit domain events；
- retain provenance。

## 20.2 Reducer

Reducer 是 authoritative state 的唯一 mutation mechanism。

Reducer MUST：

- deterministic with respect to accepted effect set；
- reject invalid state；
- not call LLM；
- not silently infer new semantics。

---

# 21. Event Contract

## 21.1 DomainEvent

Event 记录：

> 已经发生的世界事实或 runtime 事实。

建议字段：

```python
DomainEvent(
    event_id,
    event_type,
    world_revision,
    transaction_id,
    payload,
    cause_ids,
    source_system,
    timestamp,
    provenance,
)
```

## 21.2 Cause + Result

Event SHOULD 记录基本 provenance：

- cause ids；
- source；
- transaction；
- revision。

不要求每个微观物理过程都事件化。

## 21.3 Event Cascade

规范 transaction cascade：

```text
collect proposals
→ resolve
→ commit
→ emit events
→ evaluate synchronous triggers
→ produce new proposals
→ repeat
```

必须有：

```text
cascade_id
causal_root_id
depth
cycle diagnostics
max cascade depth
```

防止无限循环。

---

# 22. Development Intervention

开发者调试操作 MUST 与正常游戏事件分离。

定义：

```text
DevelopmentCommand
```

例如：

```text
pause
step
force_wake
inject_event
patch_state
branch
```

如果开发命令改变世界：

```text
DevelopmentCommand
→ ExternalInterventionEffect
→ normal commit pipeline
```

Trace 中必须明确标记：

```text
origin = developer
```

---

# 23. Scheduler / Time Contract

## 23.1 时间分层

Engine MUST 区分：

1. Action duration；
2. Actor decision horizon；
3. World logical time；
4. Physics integration timestep；
5. Player-facing turn；
6. Narrative time compression。

## 23.2 Event-driven scheduler

长行动不是重复“tick”。

例如：

```text
player starts travel
expected duration = 30 min

at t+12 min:
encounter occurs

→ interrupt
→ player decision boundary
```

## 23.3 Scheduler state 必须显式

Scheduler SHOULD 存储：

```text
ScheduledEvent
ActiveAction
ActorWakeup
Deadline
InterruptCondition
```

而不是仅靠 opaque coroutine。

## 23.4 ActiveAction

示例：

```python
ActiveAction(
    action_id,
    actor_id,
    start_time,
    expected_end,
    progress,
    interruptible,
    completion_condition,
    next_checkpoint,
)
```

---

# 24. Space Contract

## 24.1 SpaceBackend

空间 MUST 可替换。

```python
class SpaceBackend(Protocol):
    ...
```

支持：

```text
GraphSpace
GridSpace
HexSpace
Continuous2D
Continuous3D
CustomSpace
```

## 24.2 多 Spatial Domain

一个 WorldInstance MAY 同时具有多个 named spatial domains：

```text
overworld
city
tavern
combat_instance_17
```

例如：

```text
overworld = GraphSpace
tavern = Continuous2D
combat_17 = HexGrid
```

## 24.3 Entity 多空间映射

Entity MAY 同时存在于多个空间抽象中：

```text
world_location
local_position
tactical_position
```

但每个 mapping 必须明确所属 spatial domain。

---

# 25. GameplayMode / GameplayContext

## 25.1 Mode 是 overlay，不是另一个 world

例如：

```text
exploration
dialogue
tactical
cutscene
```

切换 mode 不创建第二份 WorldState。

## 25.2 可组合 Mode

多个 mode MAY 同时激活：

```text
exploration + dialogue
tactical + dialogue
```

## 25.3 Merge semantics

Mode 对不同 property 使用不同合并语义：

```text
available_actions → union/intersection
system_activation → union
renderer → composition
time_policy → priority winner
input_policy → priority winner
UI layers → composition
```

所有冲突策略 MUST 可检查。

## 25.4 ModeChangeRequest

以下都可以提出：

```text
Script
RuleEngine
LLM Director
Plugin
```

统一输出：

```text
ModeChangeRequest
```

由 ModePolicy 解析。

---

# 26. Rule / DSL

## 26.1 DSL 定位

YAML/DSL 用于：

> 简单、局部、短小、无副作用的 gameplay mechanics。

不应继续演化为完整编程语言。

## 26.2 推荐边界

适合 DSL：

```text
comparison
arithmetic
boolean
simple random
set membership
short conditions
simple derived value
simple trigger
```

应该转 Python：

```text
cross-entity
stateful
algorithmic
complex history
numerical solver
complex asynchronous process
```

## 26.3 非强制规则

复杂度边界是 style guidance，不是 hard lint。

Coding Agent SHOULD 读取对应开发指南，但 Engine 不强制拒绝复杂 YAML。

---

# 27. GameSystem / Python Extension

高级机制通过显式 System/Plugin 注册。

例如：

```python
class InfectionSystem(GameSystem):
    async def evaluate(self, context) -> list[ProposedEffect]:
        ...
```

System MUST NOT 直接写 WorldState。

---

# 28. Plugin System

## 28.1 本地项目插件

必须显式 manifest：

```yaml
plugins:
  - id: infection
    entrypoint: my_game.systems.infection:InfectionSystem
```

禁止隐式扫描加载。

## 28.2 第三方包

第三方 Python plugin SHOULD 使用 Python package entry points。

## 28.3 依赖

Module/plugin MUST 显式声明：

```text
requires
optional
conflicts
engine_version
```

---

# 29. `llmsim add`

`llmsim add` 不是另一个 package manager。

其职责：

- 解析模块 manifest；
- 调用底层 package manager；
- 更新依赖；
- 安装配置；
- 兼容性检查；
- lock；
- 注册模块。

底层 MAY 是：

- pip/uv；
- npm；
- asset package；
- future package systems。

---

# 30. Persistence / Save / Replay

## 30.1 默认模型

```text
Runtime State in memory
+
PersistenceBackend
```

## 30.2 默认持久化内容

SHOULD 支持：

```text
WorldState snapshot
RuntimeState snapshot
Backend checkpoints
Event/Trace log
Project version
Module versions
```

## 30.3 PersistenceBackend

MAY 实现：

```text
filesystem
SQLite
PostgreSQL
remote store
custom backend
```

## 30.4 Event-level replay

最低保证：

> 记录过的 commands/effects/events 可以重构 committed WorldState 历史。

不要求所有 numerical backend bit-identical rerun。

## 30.5 Branch

Branch 必须检查：

```text
backend checkpoint support
runtime snapshot availability
project compatibility
```

若 backend 不可 checkpoint：

```text
branch capability = degraded / unavailable
```

---

# 31. LLM Runtime

## 31.1 Structured Inference Adapter

统一接口：

```python
async def generate_structured(
    profile: InferenceProfile,
    messages: ...,
    schema: type[BaseModel],
) -> ...
```

不绑定某 provider。

## 31.2 Model Router

Game Project 只声明能力 profile。

Deployment Resolver 映射：

```text
capability profile
→ actual model/provider
```

## 31.3 记录

每次 LLM 调用 SHOULD 记录：

```text
logical role
profile
resolved model
input token estimate
assembled prompt metadata
output
latency
parse/retry
base revision
```

Credential MUST NOT 进入 trace。

---

# 32. Presentation Contract

## 32.1 Text 与 Image 平行

不采用：

```text
World → prose → image
```

作为唯一结构。

采用：

```text
View / Scene Context
      ├─ Narrator
      └─ VisualDirector
```

## 32.2 Visual Render Intent

建议：

```python
RenderIntent(
    scene_id,
    view_revision,
    subjects,
    environment,
    camera,
    mood,
    continuity_refs,
    style_refs,
)
```

## 32.3 异步图片过期

图片结果必须携带：

```text
scene_id
view_revision
```

如果生成结束时 view 已变化：

```text
display
discard
archive
```

由 presentation policy 决定。

---

# 33. Agent-native Development

## 33.1 Coding Agent 地位

Coding Agent 是正式一等开发客户端，但不是使用 Engine 的必要条件。

## 33.2 Agent 不负责的 Engine 能力

Engine MUST NOT 重写成熟 Coding Agent 平台已有能力：

- source patch；
- Git workflow；
- subagent orchestration；
- approval UI；
- planning；
- diff editor。

## 33.3 Engine 应提供的 game-semantic primitives

早期 CLI：

```bash
llmsim validate --json
llmsim inspect ...
llmsim trace ...
llmsim test ...
llmsim run ...
llmsim replay ...
llmsim branch ...
```

## 33.4 Structured Diagnostics

错误 SHOULD 使用机器可读结构。

示例：

```json
{
  "error_code": "AUTHORITY_CONFLICT",
  "path": "Transform.position",
  "writers": [
    "rigid_body",
    "llm_world_dynamics"
  ],
  "suggested_fixes": [
    "define resolver priority",
    "split ownership domains"
  ]
}
```

---

# 34. Agent Guidance Files

项目初始化 SHOULD 创建：

```text
.llmsim/
└─ agent/
   ├─ architecture.md
   ├─ project-layout.md
   ├─ authoring-guide.md
   ├─ extension-guide.md
   ├─ testing-guide.md
   ├─ debugging-guide.md
   └─ conventions.md
```

这些是 engine-owned canonical guidance。

不同 Agent host MAY 再增加 adapter：

```text
AGENTS.md
.dsh/
...
```

---

# 35. DSH Integration

DSH SHOULD 作为 thin adapter：

```text
DSH
├─ planning
├─ source editing
├─ subagents
├─ review
├─ git
└─ llmBasedSim adapter
   ├─ validate
   ├─ test
   ├─ inspect
   ├─ run
   ├─ trace
   ├─ replay
   └─ branch
```

Engine Runtime MUST NOT 依赖 DSH。

---

# 36. GUI 优先级

当前优先级：

```text
1. Runtime Inspector / Replay Debugger
2. LLM Workbench
3. Spatial Authoring
4. Logic Graph
5. Content Authoring
```

条件：

若 Coding Agent 实践证明无法可靠维护 Content Authoring 数据，则：

```text
1. Runtime Inspector
2. LLM Workbench
3. Content Authoring
4. Spatial Authoring
5. Logic Graph
```

---

# 37. Runtime Inspector

SHOULD 支持：

- WorldState inspection；
- RuntimeState；
- Scheduler；
- ActiveAction；
- Effect chain；
- Event chain；
- authority decision；
- producer；
- causal root；
- revision timeline；
- branch/replay；
- development intervention history。

---

# 38. LLM Workbench

SHOULD 支持：

- assembled prompt；
- prompt layers；
- context provenance；
- token usage；
- logical profile；
- resolved model；
- structured output；
- critic/repair flow；
- replay with different model；
- A/B comparison。

---

# 39. Security / Trust Model

## 39.1 Safe Project

只包含：

```text
YAML
DSL
assets
prompt/data
```

可被视为低权限内容。

## 39.2 Trusted Project

包含 Python plugin。

Python plugin 本质上是 trusted code，拥有宿主进程权限。

Engine MUST 清楚提示。

## 39.3 未来 Sandbox

未来 MAY 支持：

```text
subprocess
RPC
WASM
sandbox
permissioned plugin
```

v2 MVP 不要求实现。

---

# 40. Standard Modules

官方模块 SHOULD 与 Kernel 分离。

建议第一批：

```text
llmsim-standard-attributes
llmsim-standard-inventory
llmsim-standard-character
llmsim-standard-knowledge
llmsim-standard-perception
llmsim-standard-relationships
llmsim-standard-space
llmsim-standard-actions
llmsim-standard-scenario
llmsim-standard-dialogue
llmsim-standard-tactical
llmsim-standard-dynamics
llmsim-standard-narration
```

可以实际打包在一个 distribution 中，但逻辑上要保持模块边界。

---

# 41. Module Dependency

模块显式声明依赖。

例如：

```yaml
module:
  id: tactical
  requires:
    - standard.attributes >= 2
    - standard.space >= 2
    - standard.actions >= 2
```

Engine SHOULD 提供依赖图检查。

---

# 42. 测试层级

## 42.1 Kernel Unit Tests

必须能在：

```text
NO LLM
NO NETWORK
NO GUI
```

环境下运行。

## 42.2 Module Tests

测试：

- rules；
- actions；
- effects；
- authority；
- reducers；
- event cascade；
- scheduler；
- space；
- replay。

## 42.3 Scenario Tests

游戏项目可定义：

```yaml
scenario_test:
  initial_state: ...
  actions:
    - ...
  assertions:
    - ...
```

## 42.4 Agent Development Loop

推荐：

```text
Edit
↓
Static Validation
↓
Unit Tests
↓
Scenario Tests
↓
Headless Runtime
↓
Interaction / Simulation
↓
Assertions
↓
Trace Review
```

Engine 提供 primitive，Agent host 负责 orchestration。

---

# 43. v1 → v2 迁移

## 43.1 强烈保留的思想

- Pydantic boundary validation；
- YAML/project-file authoring；
- condition/rule DSL；
- locked/derived attribute 思想；
- Jinja2 template layer；
- structured LLM parsing；
- player subconscious policy；
- NPC personality/motivation/relationship data；
- perception / knowledge separation思想；
- narrative renderer；
- CLI/Web adapter separation。

## 43.2 应移除的核心假设

- LangGraph 固定全局 tick pipeline；
- all NPC decide every turn；
- universal tick；
- fixed six action types；
- LLM physics directly owns physics；
- global event text copied to NPC memory；
- global GameState 包含全部 runtime/transient/presentation；
- Web singleton session；
- one model config for all roles。

## 43.3 必须重写

```text
game_graph.py
GameState
state_apply.py
physics_resolve
characters_all_decide
tick_speed_resolve
perception pipeline
model config
web session lifecycle
```

---

# 44. 推荐源码目录

```text
src/
  engine/
    core/
      entity.py
      components.py
      state.py
      revision.py
      commands.py
      actions.py
      effects.py
      authority.py
      validation.py
      conflicts.py
      transaction.py
      reducer.py
      events.py

    runtime/
      engine.py
      world.py
      session.py
      clock.py
      scheduler.py
      active_action.py
      modes.py
      rng.py

    persistence/
      base.py
      snapshot.py
      replay.py
      checkpoint.py

    plugins/
      api.py
      registry.py
      manifest.py

    context/
      capability.py
      provider.py

  modules/
    attributes/
    inventory/
    character/
    knowledge/
    perception/
    relationships/
    space/
    tactical/
    scenario/

  agents/
    policies/
    critic/
    repair/
    narrator/

  dynamics/
    base.py
    rule.py
    llm.py
    composite.py

  llm/
    structured.py
    profiles.py
    router.py
    providers/

  prompts/
    assembler.py
    policies.py
    registry.py

  content/
    loader.py
    project_ir.py
    schemas.py
    migrations.py

  devtools/
    validate.py
    inspect.py
    trace.py
    replay.py
    branch.py
    scenario_test.py

  adapters/
    cli/
    web/
    dsh/

  presentation/
    text/
    image/
    tactical/
```

---

# 45. Engine Runtime 主流程

```text
External Command / Player Input
            │
            ▼
       Player Policy
            │
            ▼
      ActionProposal
            │
            ▼
    Action Validation
            │
            ▼
       ActiveAction
            │
            ▼
┌──────────────────────────────┐
│        Engine Runtime        │
│                              │
│ Scheduler                    │
│ Actor Wakeups                │
│ Rules                        │
│ WorldDynamics                │
│ Scenario                     │
│ GameplayModes                │
└──────────────┬───────────────┘
               │
               ▼
       ProposedEffects
               │
               ▼
         Authority
               │
               ▼
         Validation
               │
               ▼
      Conflict Resolution
               │
               ▼
          Transaction
               │
               ▼
            Reducer
               │
               ▼
          WorldState
               │
               ▼
         DomainEvents
               │
               ├─────────→ triggers / wakeups
               │
               └─────────→ View derivation
                                │
                     ┌──────────┴──────────┐
                     ▼                     ▼
                 Narrator            VisualDirector
                     │                     │
                     ▼                     ▼
                    Text                 Image
```

---

# 46. 第一阶段 v2 MVP 范围

## 必须实现

1. WorldInstance / Session 分离；
2. WorldState / RuntimeState 分离；
3. Entity / Component；
4. Revision；
5. Action Registry；
6. ProposedEffect；
7. Authority；
8. Validation；
9. Conflict Resolver；
10. Transaction / Reducer；
11. DomainEvent + provenance；
12. serializable scheduler；
13. ActiveAction；
14. single spatial domain API + multi-domain-ready representation；
15. BehaviorPolicy；
16. Context capability；
17. WorldDynamicsBackend；
18. ProjectIR；
19. module/plugin registry；
20. CLI validate/inspect/run/test；
21. snapshot + event-level replay；
22. provider-neutral inference profile。

## 可以推迟

1. Multiplayer authoritative server；
2. distributed simulation；
3. full GUI；
4. plugin sandbox；
5. remote package registry；
6. visual Logic Graph；
7. automatic semantic mutation API；
8. full local dev service；
9. complete branch debugger UI；
10. generalized multi-process runtime。

---

# 47. 第一期开发顺序

## Phase 0 — Freeze v1

目标：

- 停止向 `game_graph.py` 增加核心机制；
- 保留 v1 作为行为参考和兼容样例；
- 建立 Architecture v2 branch。

## Phase 1 — Core State / Effect Kernel

实现：

```text
Entity
Component
WorldState
RuntimeState
Revision
ProposedEffect
Authority
Validation
ConflictResolver
Transaction
Reducer
DomainEvent
Trace
```

此阶段完全不接 LLM。

验收：

> Engine core tests 可在无网络、无 LLM 情况下完整运行。

## Phase 2 — Scheduler / Action

实现：

```text
LogicalClock
ScheduledEvent
ActiveAction
ActionRegistry
ActionLifecycle
Interrupt
DecisionBoundary
```

验收：

- 30 min travel；
- t+12 encounter；
- travel interrupt；
- resume/abort；
- replay。

## Phase 3 — Actor / Context

实现：

```text
Actor
BehaviorPolicy
ContextProvider
Capability
Observation
Knowledge
```

先使用 RulePolicy。

## Phase 4 — LLM Runtime

实现：

```text
InferenceProfile
DeploymentResolver
StructuredInference
LLMPolicy
PromptAssembler
Revision-aware async result
```

## Phase 5 — Dynamics

实现：

```text
RuleDynamics
LLMWorldDynamics
CompositeDynamics
```

然后再接：

```text
optional physical backend
```

## Phase 6 — Persistence / Replay / DevTools

实现：

```text
snapshot
event replay
trace
inspect
scenario tests
branch prototype
```

## Phase 7 — Official Modules

迁移：

```text
attributes
inventory
relationships
perception
standard character
space
scenario
dialogue
tactical
```

## Phase 8 — Presentation

实现：

```text
Narrator
ViewState
VisualDirector
image generation adapter
revision-aware render result
```

## Phase 9 — Agent Integration

实现：

```text
CLI --json
.llmsim/agent docs
DSH thin adapter
```

---

# 48. 关键验收场景

Architecture v2 在进入稳定版前 SHOULD 至少通过以下端到端场景。

## Scenario A — 确定性开门

```text
Player requests open door
Door locked
No key
```

必须：

- LLM 不能绕过 lock system；
- action rejected/translated；
- trace 能解释原因。

## Scenario B — LLM 模糊环境后果

```text
Player hammers anvil
Gem sits near edge of nearby table
No detailed rigid-body model
```

允许：

```text
LLMWorldDynamics
→ gem falls
```

但必须：

- 产生 ProposedEffect；
- 通过 authority；
- commit；
- event 有 provenance；
- replay 可重构。

## Scenario C — Physics 与 LLM 冲突

```text
RigidBody says gem stays
LLM says gem falls
```

必须：

- 两个 effect 可见；
- conflict resolver 明确给出决策；
- debugger 能解释。

## Scenario D — 长时间旅行被打断

```text
Travel duration 30 min
Encounter at 12 min
```

必须：

- world time 到 12 min；
- travel action interrupted；
- player regain control；
- progress 保留。

## Scenario E — NPC epistemic boundary

Bob 偷东西。

Alice 看不到也不知道。

必须：

- Alice policy context 不包含该事实；
- prompt override 也无法自动获取；
- 除非显式授予 global read。

## Scenario F — Dialogue → Tactical

```text
exploration + dialogue
↓ hostile action
tactical + dialogue
```

必须：

- WorldState 不复制；
- GameplayMode overlay；
- TimePolicy resolver 正确；
- Spatial domain 可切换/增加。

## Scenario G — Async stale proposal

Alice 在 revision 812 开始决策。

返回时：

```text
revision = 829
Alice unconscious
```

必须：

- proposal 不直接 commit；
- revalidation reject/repair。

## Scenario H — Replay + Branch

从 revision N：

```text
branch A
branch B
```

如果 backend checkpointable：

- 两条分支独立继续。

如果不可 checkpoint：

- Engine 明确报告 branch 不可用原因。

---

# 49. 设计原则汇总

1. **Authority defines who may decide; Kernel defines how state commits.**
2. **No raw mutation of authoritative state.**
3. **Agent is policy, not engine.**
4. **LLM, rules, scripts and numerical models are all effect producers.**
5. **Prompt cannot enforce world invariants.**
6. **Context capability defines knowledge access.**
7. **Event separates systems and preserves causality.**
8. **Scheduler state must be inspectable and serializable.**
9. **World continuity is preserved across gameplay modes.**
10. **Space is backend-defined and may contain multiple domains.**
11. **Game declares model capability; user chooses actual model.**
12. **Source files are authoring truth; ProjectIR is runtime truth.**
13. **Coding Agent is a first-class client, not an Engine dependency.**
14. **GUI should expose runtime causality rather than merely replace text editors.**
15. **Complexity belongs in Python extensions, not an ever-growing YAML DSL.**
16. **Replay and provenance are architecture features, not afterthoughts.**
17. **Official gameplay systems are modules, not Kernel invariants.**
18. **Presentation never owns world truth.**

---

# 50. 推荐下一步

本规范通过后，下一步不应立即进行全量代码重构，而应先产出三份更低层的实现规范：

## Spec A — Core Data Contracts

具体定义：

```text
EntityId
WorldState
RuntimeState
Revision
ActionProposal
ActiveAction
ProposedEffect
CommittedEffect
Transaction
DomainEvent
TraceRecord
```

包括 Pydantic/dataclass schema。

## Spec B — Runtime Protocols

具体定义：

```text
BehaviorPolicy
WorldDynamicsBackend
SpaceBackend
ContextProvider
PersistenceBackend
ConflictResolver
AuthorityPolicy
TimePolicy
```

包括 Python Protocol / ABC 签名。

## Spec C — Project Format v2

具体定义：

```text
game.yaml
module manifest
action registry
authority config
gameplay modes
inference profiles
plugin entrypoints
```

并配套 JSON Schema / examples。

---

# 51. Architecture v2 的最终目标

当 v2 成熟时，理想开发路径应为：

```text
Developer:
“制作一个有动态社会关系、
真实战斗物理、
实时角色图像生成的沙盒 RPG”

        ↓

Coding Agent / VS Code / GUI

        ↓

Game Project
YAML + Python + Assets

        ↓

llmBasedSim validate/test/run

        ↓

Authority-mediated Engine Runtime

        ↓

Rules + Numerical Simulation + LLM Policies

        ↓

Persistent World + Replayable Causality

        ↓

Text / Tactical UI / Generated Visuals
```

最终目标不是让 LLM 取代游戏引擎，而是：

> **让确定性系统、数值模拟、程序化逻辑和 LLM 语义推理在一个可控制、可解释、可扩展的世界状态架构中共存。**

这应当成为 `llmBasedSim Engine Architecture v2` 的核心设计基线。
