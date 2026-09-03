# llmBasedSim：12h Complex-Game Runtime Closure Subagent Task Plan

> **目标分支**：`architecture-v2`  
> **审查基线**：`8585d7f7090d79ea7d53302633552b3acb3cdc5c`  
> **计划性质**：subagent execution plan，不是 Phase / 软件开发阶段计划书  
> **墙钟预算**：12h 上限；按 **4 个并行 coding slot + 1 个 leader/integrator** 编排  
> **核心目标**：在不扩张产品面的前提下，尽快达到“可以使用 LLM + Python complex systems 构建开放式 simulation game”的最低可用状态。

---

## 0. 一句话结论

当前最缺的不是更多 subsystem，而是把已经存在的 subsystem 接成一条 **production-only game path**。

本轮只完成：

```text
GameProject
  → load / validate / ProjectIR
  → explicit trusted Python extensions
  → WorldInstance materialization
  → official actions + custom ActionExecutor
  → P6 LLMPolicy binding
  → Python WorldDynamicsBackend
  → EngineInstance tick / wakeup / proposal execution
  → Authority / Transaction / Reducer commit
  → Perception / SceneView
```

并用一个 **不 import `tests.*`** 的复杂 reference game 证明整条链路。

本轮不追求：

- WebSession 重构；
- 图像生成；
- Inspector / Workbench Web 页面；
- DSH adapter；
- 通用异步 runtime；
- generic GameSystem 大抽象；
- multiplayer；
- production-grade packaging / release；
- 完整历史 replay；
- UI 美化。

---

# 1. 12h 结束时的 Definition of Done

必须存在一个独立项目，例如：

```text
examples/complex_minimal/
├── game.yaml
├── world/
├── characters/
├── actions/
├── prompts/
├── plugins/
│   └── simulation/plugin.yaml
├── pyproject.toml
└── complex_minimal/
    ├── __init__.py
    └── extension.py
```

并且只通过 `src/engine_v2` 的 production API，可以完成：

```text
load_project
→ build_ir
→ validate_project
→ explicit Python entrypoint load
→ materialize WorldInstance
→ assemble EngineInstance
→ player/custom action
→ ActionExecutor
→ ProposedEffect
→ Authority
→ Transaction
→ Reducer
→ committed WorldState
→ Python dynamics tick
→ committed WorldState
→ NPC wakeup
→ P6 LLMPolicy
→ ActionProposal
→ ActionExecutor
→ committed WorldState
→ SceneView
```

### 必须通过的最终 E2E

1. **零 `tests.*` import**；
2. 未声明的 `.py` 文件不会被扫描或 import；
3. Python extension 只有在 `trust_python=True` / 明确 trusted 模式下才加载；
4. Python extension 至少提供一个 custom `ActionExecutor` 和一个 custom `WorldDynamicsBackend`；
5. custom action 确实改变 authoritative WorldState，且只能经 `ProposedEffect → Authority → Transaction → Reducer`；
6. Python dynamics 在 tick 中运行并提交 effect；
7. 一个 NPC 经 **P6 `LLMPolicy`**（Fake backend in CI）产生 `ActionProposal`；
8. NPC proposal 确实进入同一 action/effect/commit pipeline，而不是只记录后丢弃；
9. ActorDecisionContext 只包含可见实体，`global_entity_views=None`；
10. `derive_scene_view()` 能从提交后的 world 产生新的 SceneView；
11. fake-model + deterministic Python backend 双跑结果一致；
12. 全仓原有测试不出现新的失败。

### 真实模型要求

本轮 CI **不依赖真实网络和密钥**。但 production assembly 必须允许注入 `HttpxInferenceBackend()`，并使用已有 `DeploymentProfile → resolve_capability → build_llm_policy`。因此已有 `scripts/llm_smoke.py` 成功的环境中，不需要再修改 runtime 才能切换真模型。

---

# 2. 本轮最重要的范围裁决

## 2.1 不修 Web，先做 headless production runtime

当前 WebSession 有两个独立问题：Session 自己持 WorldState，且 player `ActionProposal` 生成后被丢弃。

**本轮不在 `adapters/web/` 中修。**

原因：

1. Web 不是“能否开始造复杂游戏”的必要条件；
2. 一旦 production EngineInstance 建好，Web 后续只需要变成 adapter；
3. 现在修 Web 会把 Runtime Closure 和旧 P10 临时语义重新耦合。

本轮完成后关系应是：

```text
WebSession
    ↓ adapter
EngineInstance
    ↓
WorldInstance
```

---

## 2.2 不新造通用 GameSystem framework

12h 内不增加新的通用生命周期抽象。Python 扩展仅允许返回三类现有协议对象：

```text
ActionExecutor
WorldDynamicsBackend
BehaviorPolicy
```

它们覆盖：

| 复杂机制 | 本轮表达方式 |
|---|---|
| 玩家/NPC 主动触发的复杂算法 | `ActionExecutor` |
| 连续物理、生态、经济、环境演化 | `WorldDynamicsBackend` |
| 自定义非 LLM / 特殊 agent | `BehaviorPolicy` |
| 自定义状态 | `component_schemas` + `ProposedEffect` |
| LLM NPC | P6 `LLMPolicy` |

以后如有必要，再把这些包装成 `GameSystem` sugar layer。

---

## 2.3 不修改 P5 ProjectIR schema，除非发现硬阻塞

当前 schema 已经有 `component_schemas / authority / actions / modules / capabilities / plugin_descriptors / prompts`。

本轮默认 **零 schema 扩展**，特别禁止为了“更漂亮”新增：

```text
character.policy
character.model
plugin.priority
runtime.*
```

---

## 2.4 NPC LLM binding 采用一个最小约定

由于当前 `CharacterSpec` 没有 policy/capability binding 字段，本轮不扩 schema。

默认：

```text
InferenceCapabilityProfile.capability == "npc_policy"
```

作为所有普通 NPC 的默认 P6 policy requirement。

特殊 NPC 由 Python extension 提供 `BehaviorPolicy` override。

---

# 3. Leader 在开工前必须冻结的最小接口

这一步 **不交给 subagent 做设计**。Leader 最多写一个 `<100 行` 临时 contract note。

## 3.1 `WorldInstance`

```python
@dataclass
class WorldInstance:
    world_instance_id: str
    ir: ProjectIR
    world: WorldState
    runtime: RuntimeState
    spaces: SpaceRegistry
    action_registry: ActionRegistry
    executors: dict[str, ActionExecutor]
    policies: dict[str, BehaviorPolicy]
    dynamics: tuple[WorldDynamicsBackend, ...]
    component_registry: ComponentRegistry
    producer_registry: ProducerRegistry
    authority_policy: AuthorityPolicy
    trace_sink: RuntimeTraceSink
```

职责固定：**authoritative runtime state + 已装配 runtime dependencies**。

## 3.2 `EngineInstance`

```python
class EngineInstance:
    @property
    def instance(self) -> WorldInstance: ...

    def submit_proposal(self, proposal: ActionProposal) -> StepResult: ...

    def submit_action(
        self,
        actor_id: str,
        action_id: str,
        arguments: Mapping[str, object],
        *,
        intent: str | None = None,
    ) -> StepResult: ...

    def wake(
        self,
        actor_id: str,
        *,
        reason: str | None = None,
        due_tick: int | None = None,
    ) -> None: ...

    def advance(self, ticks: int = 1) -> StepResult: ...

    def view(self) -> SceneView: ...
```

明确不做：session management / network server / image / async task manager / multiplayer。

## 3.3 Python extension contract

```python
@dataclass(frozen=True)
class ProducerGrant:
    producer_id: str
    component_types: tuple[str, ...]
    priority: int = 50

@dataclass(frozen=True)
class ExtensionBundle:
    action_executors: Mapping[str, ActionExecutor] = ...
    dynamics_backends: tuple[WorldDynamicsBackend, ...] = ()
    policies: Mapping[str, BehaviorPolicy] = ...
    producer_grants: tuple[ProducerGrant, ...] = ()
```

entrypoint 只允许：

```python
def build_extension(context: ExtensionContext) -> ExtensionBundle:
    ...
```

`WorldDynamicsBackend.metadata()` 已包含 `producer_id / domains / implementation_type`，因此 dynamics grant SHOULD 自动从 metadata 派生。ActionExecutor 的自定义 producer 则必须显式给 `ProducerGrant`。

## 3.4 trusted Python 规则

唯一允许动态 import 的路径：

```text
explicit declared entrypoint
→ EntryPointSpec
→ importlib.import_module(spec.module)
→ getattr(spec.attribute)
```

禁止：

```text
rglob("*.py")
walk project tree
exec arbitrary file
猜测 module
自动 import 目录中所有 Python
```

---

# 4. Subagent 执行纪律

## 4.1 “一根线”原则

任何 coding subagent 都不得同时拥有两项：

```text
project loading
world materialization
runtime loop
Python loading
LLM binding
context/perception
action binding
dynamics binding
composition
E2E acceptance
```

如果发现必须修改另一个 task 的 owned file：**停止，不顺手修；写 <=5 行 blocker note 给 Leader。**

## 4.2 每个 subagent 的读取上限

- 先读 task card 指定 2–5 个文件；
- 可额外搜索最多 3 个 symbol；
- **禁止全仓 documentation survey**；
- 禁止重读 P1–P10 长 SOT；
- 如果读到第 8 个源码文件仍不能开始编码，返回 Leader。

## 4.3 每个 subagent 的 handoff

只交：

```text
1. changed files
2. tests run + result
3. public symbols added/changed
4. assumptions used
5. blockers / follow-up (<=5)
```

**handoff <= 50 行。**

## 4.4 测试纪律

每个 task 只跑自己的 targeted tests + 1 个直接依赖 regression。不要让每个 subagent 都跑 3205 全套。

全套测试只在：

1. Runtime Assembly 首次合并后；
2. 最终 Gate；

各跑一次。

## 4.5 Review 纪律

不再采用“每 task 四盲审”。

- Local owner check：subagent targeted tests；
- Seam review：每个并行 wave 后 1 reviewer，只看新增 public contracts / cross-file interface / diff；
- Final adversarial review：2 reviewer 并行：
  - R-runtime：K2 / proposal / scheduler / authority / state correctness；
  - R-authoring：从新 GameProject 出发验证 Python + LLM。

---

# 5. 串并行总图

```text
                         ┌─ T1 World materialization ───────┐
                         │                                  │
Leader contract freeze ─┼─ T2 Engine runtime loop ─────────┼────┐
                         │                                  │    │
                         ├─ T3 Python extension activation ─┤    │
                         │                                  │    │
                         └─ T4 Context / perception ────────┘    │
                                                               │
                  ┌──────── T5 LLM policy binding ◀─ T4 ───────┤
                  ├──────── T6 Action binding / grants ◀ T1 ───┤
                  ├──────── T7 Dynamics binding ◀ T3 ──────────┤
                  └──────── T8 Runtime trace sink ──────────────┘
                                                               │
                                                               ▼
                                                       T9 Assembly glue
                                                               │
                                      ┌────────────────────────┴───────────────┐
                                      │                                        │
                             T10 reference game                        T11 E2E acceptance
                                      │                                        │
                                      └────────────────────────┬───────────────┘
                                                               ▼
                                                    Final dual review + fixes
                                                               │
                                                               ▼
                                                         Full regression
```

T10 reference game 可在 Leader freeze extension contract 后立即开始写，只在最后等待 T9 assembly。

---

# 6. Task cards

## T1 — `ProjectIR → World materialization`

**只接：**

```text
ProjectIR
→ WorldState + RuntimeState + Space/Mode/component runtime surfaces
```

- **负责人**：Subagent A
- **预计**：1.5h
- **依赖**：Leader frozen contract
- **首读**：
  - `tests/engine_v2/modules/conftest.py::_build_world`
  - `tests/engine_v2/modules/conftest.py::_build_mode_surfaces`
  - `src/engine_v2/content/schemas.py`
  - `src/engine_v2/modules/space.py`
  - `src/engine_v2/modules/character.py`
- **写入**：
  - `src/engine_v2/runtime/materialize.py`
  - `tests/engine_v2/runtime/test_materialize.py`

建议入口：

```python
materialize_world(
    ir: ProjectIR,
    *,
    world_instance_id: str,
    domain_id: str = "world",
    space_backend: SpaceBackend | None = None,
) -> WorldMaterialization
```

必须从 test-side `_build_world` 搬**语义**，不能 import helper。

额外最小要求：将 NPC 的 `name / personality / speech_examples` 投影进一个 read-only authoring/profile component，使 P6 `self_view` 能看到角色信息；不为它增加 mutation flow。

**禁止**：LLM / plugin import / tick / CascadeExecutor / persistence / Web。

**Gate**：
- 至少两个既有 P9 fixture 可 materialize；
- 无 `tests.*` import；
- 同 IR 双构造 world serialization 一致。

---

## T2 — production Engine runtime loop

**只接：**

```text
WorldInstance
→ tick / wakeup / proposal execution / dynamics phase
```

- **负责人**：Subagent B
- **预计**：2.0h
- **首读**：
  - `tests/engine_v2/modules/conftest.py::P9Host.tick`
  - `_phase_1_due_events`
  - `_execute_proposal`
  - `_phase_2_dynamics`
  - `apply_effects`
  - `_phase_5_lifecycle`
  - `core/scheduler.py`
  - `core/cascade.py`
  - `core/action_lifecycle.py`
- **写入**：
  - `src/engine_v2/runtime/engine.py`
  - `tests/engine_v2/runtime/test_engine.py`

T2 不构造 ProjectIR / policies / executors / dynamics，只消费已装配 `WorldInstance`。

只保留必要相位：

```text
1 due actor wakeups
2 policy → ActionProposal → executor → effects
3 dynamics backends
4 action lifecycle completion
5 logical tick update
```

必须提供 `submit_proposal / submit_action / wake / advance / view`。

未注册 action 必须显式失败/诊断，不静默。

---

## T3 — explicit trusted Python activation

**只接：**

```text
declared entrypoint
→ import
→ ExtensionBundle
```

- **负责人**：Subagent C
- **预计**：1.5h
- **首读**：
  - `plugins/api.py`
  - `plugins/manifest.py`
  - `plugins/registry.py`
  - `dynamics/backend.py`
  - `modules/actions.py`
- **写入**：
  - `runtime/extensions.py`
  - `tests/engine_v2/runtime/test_extensions.py`

新增：`ExtensionContext / ProducerGrant / ExtensionBundle / ExtensionLoadResult / load_extensions()`。

只支持 executable entrypoint：

```python
def build_extension(context) -> ExtensionBundle
```

优先支持 `plugins/*/plugin.yaml`；若 `ProjectIR.plugin_descriptors` 已明确给 entrypoint，也可消费。不要另造第三种 source。

安全 Gate：

```text
rogue.py 未声明 → 不 import
trust_python=False → 不 import + 明确诊断
明确 entrypoint + trust_python=True → import
entrypoint 错型 → 明确诊断
```

禁止 scan `.py` / pip install / sandbox / hot reload / 修改 P5 PluginAPI。

---

## T4 — ActorDecisionContext + perception wire

**只接：**

```text
WorldInstance + actor_id
→ ActorDecisionContext
```

- **负责人**：Subagent D
- **预计**：1.5h
- **首读**：
  - `core/context_provider.py`
  - `modules/perception.py`
  - `modules/knowledge.py`
  - `core/space.py`
- **写入**：
  - `runtime/context.py`
  - `tests/engine_v2/runtime/test_context.py`

必须：

```text
self_view = actor entity view
visible_entities = perception result
local_entity_views = only visible
global_entity_views = None
observations = build_observations(...)
candidate_actions = runtime ActionRegistry
```

感知范围不加 schema：player 可消费已有 capability 数值；普通 NPC 用固定 runtime default；高级覆盖后续走 custom context provider。

Gate：near NPC 可见，far NPC 不可见，`global_entity_views is None`。

---

## T5 — P6 LLMPolicy binding

**只接：**

```text
IR capability + DeploymentProfile + InferenceBackend
→ actor_id → P6 LLMPolicy
```

- **负责人**：Subagent E
- **预计**：1.5h
- **依赖**：接口依赖 T4，可并行开发
- **首读**：
  - `llm/policy.py`
  - `llm/deployment.py`
  - `llm/router.py`
  - `prompts/registry.py`
  - `content/schemas.py`
- **写入**：
  - `runtime/llm_binding.py`
  - `tests/engine_v2/runtime/test_llm_binding.py`

强制复用：

```text
build_llm_policy()
DeploymentProfile
InferenceBackend
TemplateStore
CharDivisorTokenEstimator
```

**不要修改 P9 `NpcBehaviorPolicy` 去硬接真实网络。**

默认 `capability == "npc_policy"` → 所有普通 CharacterSpec。Python extension policy 后续覆盖默认。

Gate：同 GameProject，Deployment A/B 得到不同 resolved model；Fake backend 的 NPC decision 产生 P6 ActionProposal。

---

## T6 — action/executor binding + action-side grants

**只接：**

```text
IR actions + SpaceRegistry + ExtensionBundle.action_executors
→ ActionRegistry + executors + grants
```

- **负责人**：Subagent F
- **预计**：1.25h
- **首读**：
  - `modules/actions.py`
  - `core/action_registry.py`
  - `core/authority.py`
- **写入**：
  - `runtime/action_binding.py`
  - `tests/engine_v2/runtime/test_action_binding.py`

本轮支持：
- project-declared action specs；
- standard move executor；
- extension-provided action executors。

其他标准 action 如果没有 production executor：保留声明，执行时明确 `executor_not_bound`，不要临时实现五个动作。

T6 不构造最终 AuthorityPolicy，只返回：

```text
action_registry
executors
producer_grants
```

---

## T7 — dynamics binding + dynamics-side grants

**只接：**

```text
IR rules + ExtensionBundle.dynamics_backends
→ runtime dynamics list + producer grants
```

- **负责人**：Subagent G
- **预计**：1.0h
- **首读**：
  - `dynamics/backend.py`
  - `dynamics/rule.py`
  - `dynamics/host.py`
  - `dynamics/authority.py`
- **写入**：
  - `runtime/dynamics_binding.py`
  - `tests/engine_v2/runtime/test_dynamics_binding.py`

支持：
- project rules → `RuleDynamics`（如果现有 constructor 可直接投影）；
- Python extension → arbitrary `WorldDynamicsBackend`；
- backend `metadata().producer_id/domains` 自动生成 grants。

不做：新 physics library / async dynamics / LLMWorldDynamics 自动装配。

Gate：Python numerical backend `simulate() → ProposedEffect`，metadata 可生成 grant。

---

## T8 — RuntimeTraceSink

**只接：**

```text
P6 TraceSink + runtime events
→ inspectable in-memory trace
```

- **负责人**：Subagent H
- **预计**：0.75h
- **首读**：
  - `llm/policy.py::TraceSink`
  - `core/trace.py`
  - `devtools/trace_query.py`
- **写入**：
  - `runtime/observability.py`
  - `tests/engine_v2/runtime/test_observability.py`

提供 production in-memory sink：`record / store_artifact / record_diagnostic`，Engine 暴露 `trace_records / artifacts / diagnostics`。

不做 Web Inspector / trace persistence redesign / full replay。


## T9 — assembly glue

**只做 glue，不新增 subsystem logic**

```text
project root
→ assembled EngineInstance
```

- **负责人**：Subagent I（建议高智力、上下文较长，但严格只读新接口）
- **预计**：1.5h
- **依赖**：T1–T8
- **优先只读**：
  - `runtime/materialize.py`
  - `runtime/engine.py`
  - `runtime/extensions.py`
  - `runtime/context.py`
  - `runtime/llm_binding.py`
  - `runtime/action_binding.py`
  - `runtime/dynamics_binding.py`
  - `runtime/observability.py`
- 然后只读：
  - `content.loader`
  - `content.project_ir`
  - `content.validator`
- **写入**：
  - `runtime/assembly.py`
  - `tests/engine_v2/runtime/test_assembly.py`

公开入口：

```python
assemble_project(
    project_root,
    *,
    deployment: DeploymentProfile | None = None,
    inference_backend: InferenceBackend | None = None,
    trust_python: bool = False,
) -> AssemblyResult
```

固定顺序：

```text
1 load
2 build_ir
3 validate
4 materialize
5 load_extensions
6 action binding
7 dynamics binding
8 build producer registry + authority policy
9 trace sink
10 LLM policy binding
11 extension policy override
12 construct WorldInstance
13 construct EngineInstance
```

Authority merge 只允许 T6/T7/T3 明确产出的 `ProducerGrant`。禁止：

```text
allow every producer
allow every component
first seen producer auto-authorize
```

### “glue purity”规则

如果 T9 需要写：

- 新 executor；
- 新 backend；
- 新 parser；
- 新 perception；
- 新 plugin loader；

说明上游 task 缺口，退回 owner，不允许 Assembly agent 顺手实现。

---

## T10 — complex reference game

**只写游戏，不写引擎**

- **负责人**：Subagent J
- **预计**：1.25h
- **开始时间**：Leader freeze extension contract 后立即并行
- **唯一写入**：`examples/complex_minimal/**`

建议最小场景：

```text
state:
  environment.temperature
  machine.power
  NPC state

custom action:
  inject_heat / cool / toggle_machine

Python dynamics:
  温度按简单 ODE/离散积分演化
  machine power 影响热源
  可加入阈值事件

NPC LLM:
  看见局部状态
  根据温度/机器状态选择 action
```

不要做宏大剧情。

Python extension：

```python
build_extension(context) -> ExtensionBundle
```

返回：
- 1 个 custom ActionExecutor；
- 1 个 numerical WorldDynamicsBackend；
- 对应 ProducerGrant。

GameProject 必须同时演示：

```text
YAML authoring
component_schemas
actions
capabilities
prompts
explicit plugin manifest
Python package
```

禁止：
- 直接 import runtime 私有对象绕过 assembly；
- 直接修改 WorldState；
- test fixture helper；
- image；
- Web。

---

## T11 — Complex Game E2E acceptance

**只证明“真的能造复杂游戏”**

- **负责人**：Subagent K（独立于 T1–T10 authors）
- **预计**：1.5h
- **唯一主要写入**：`tests/engine_v2/runtime/test_complex_game_e2e.py`

### Case 1：Trusted Python

```text
trust_python=False
→ project load/IR 可完成
→ extension activation 被明确拒绝
```

### Case 2：Custom Action

```text
assemble trusted project
→ player submit custom action
→ Python ActionExecutor
→ ProposedEffect
→ Authority
→ Transaction COMMITTED
→ target component changed
```

### Case 3：Python Dynamics

```text
advance 1+
→ numerical backend simulate
→ effect committed
→ physical/system state evolves
```

### Case 4：LLM NPC

Fake backend 脚本：

```json
{
  "action_id": "cool",
  "arguments": {},
  "intent": "temperature is too high",
  "confidence": 0.9,
  "fallback_action": null
}
```

流程：

```text
engine.wake(npc)
→ ActorDecisionContext
→ P6 LLMPolicy
→ ActionProposal
→ custom ActionExecutor
→ effect
→ commit
```

### Case 5：Epistemic boundary

远距离实体：

```text
not in local_entity_views
global_entity_views is None
```

### Case 6：Determinism

```text
same project
same fake model script
same Python deterministic backend
same actions
→ same final serialized WorldState
```

### Case 7：No test dependency

AST/static check：

```text
src/engine_v2/runtime/**
```

零：

```text
import tests
from tests
```

---

# 7. Leader-only hot files

为了避免并行任务在高冲突文件互相踩踏，下列文件只允许 Leader 最后改：

```text
src/engine_v2/runtime/__init__.py
pyproject.toml
README.md
docs/v2/usage/project-authoring.md
docs/v2/usage/devtools-and-extensions.md
```

coding subagent **不得自行修改这些文件**。

如果需要 export，在 handoff 中列出 export 名，由 Leader 一次汇总。

---

# 8. 12h 墙钟编排

以下按 4 coding slots。

## 0:00–0:30 — Leader freeze

Leader：

- 创建工作分支；
- 固定 §3 interfaces；
- 给 T1–T4 发 brief；
- 给 T10 提前发 authoring brief；
- 禁止各 agent 自行重做 architecture design。

---

## 0:30–2:30 — Wave A：四根基础线完全并行

| Slot | Task | 预算 |
|---|---|---:|
| A | T1 materialization | 1.5h |
| B | T2 engine loop | 2.0h |
| C | T3 Python activation | 1.5h |
| D | T4 context/perception | 1.5h |

同时：
- T10 reference game 可由额外 slot 开始；
- 如果只有 4 slot，T10 推迟到下一波。

### 2:00 左右 Seam Review A

一个 reviewer，只看：

```text
T1–T4 public symbols
类型/职责是否越界
是否出现 shared write
```

目标 20–30 min。

---

## 2:30–4:00 — Wave B：四根 binding 线并行

| Slot | Task | 预算 |
|---|---|---:|
| A | T5 LLM binding | 1.5h |
| B | T6 action binding | 1.25h |
| C | T7 dynamics binding | 1.0h |
| D | T8 trace sink | 0.75h |

T10 同时继续。

任何 agent 都只能返回“binding object / mapping / grants”。

**禁止在这里创建 EngineInstance。**

---

## 4:00–5:30 — T9 Composition

T9 独占 integration context。

其他 slot：

- T10 完成 reference project；
- 1 reviewer 预读 T9 interface；
- 1 slot 处理 Wave A/B targeted test 小失败。

---

## 5:30–7:00 — T11 E2E

T11 独立 agent 从“游戏作者”视角测试。

Leader 不提前替它补 path。

真实性标准：

> 如果 T11 需要 import tests helper，本轮即判失败。

---

## 7:00–8:00 — First full regression

Leader/integration runner：

```text
runtime targeted tests
P5/P6/P7/P9 critical regression
full pytest
ruff changed runtime paths
```

不要先写文档。

---

## 8:00–9:00 — Final dual review（并行）

### R-runtime

只检查：

```text
K2
Authority
proposal 是否真的消费
scheduler/wakeup
WorldState mutation path
producer grants
```

### R-authoring

完全从 `examples/complex_minimal` 开始，不看内部历史。

回答：

```text
我是否能理解怎么添加：
1 Python action
1 Python dynamics
1 LLM NPC
1 custom component
```

---

## 9:00–10:30 — Fix window

只修 final review 中：

```text
BLOCKER
能力链断裂
接口明显错误
```

不处理：

```text
命名美化
抽象重构
文档风格
future extensibility
```

同一个根因最多 1 轮 fixer。第二次仍不闭合：

> Leader 直接裁决 fallback / cut，不允许继续 agent loop。

---

## 10:30–11:15 — Docs / exports

Leader 一次性：

- 更新 `runtime/__init__.py`；
- 修正 `project-authoring.md`：
  - declarative discovery surface closed；
  - project tree NOT closed；
  - Trusted Python explicit entrypoint；
- `devtools-and-extensions.md` 改掉“registry 做装载”的不准确说法；
- 增加 `examples/complex_minimal` 最短运行说明。

不写新的大 SOT。

---

## 11:15–12:00 — Final Gate

最后一次：

```text
full pytest
ruff
complex E2E
AST no-tests-import
rogue-python no-import
```

生成一页以内 Gate note。

---

# 9. Agent-hour / wall-clock 预算

## Coding

| Task | Agent-hour |
|---|---:|
| T1 | 1.5 |
| T2 | 2.0 |
| T3 | 1.5 |
| T4 | 1.5 |
| T5 | 1.5 |
| T6 | 1.25 |
| T7 | 1.0 |
| T8 | 0.75 |
| T9 | 1.5 |
| T10 | 1.25 |
| T11 | 1.5 |
| **合计 coding** | **15.25 agent-h** |

## Review / integration

约：

```text
Leader freeze        0.5h
Seam review          0.5h
full regression      1.0h
dual final review    2 × 1.0h
fix window           1.5–3 agent-h
docs/gate            1.0h
```

总 agent-hour 约 **21–23 agent-h**。

4 slot 并行时关键路径：

```text
0.5 freeze
+ 2.0 Wave A
+ 1.5 Wave B
+ 1.5 assembly
+ 1.5 E2E
+ 1.0 regression
+ 1.0 review
+ 1.5 fix
+ 0.75 docs/gate
≈ 10.75h
```

保留约 **1.25h** 风险缓冲。

### 并行度要求

- 4 coding slots：12h 可行；
- 3 slots：有希望，但 buffer 很小；
- 2 slots：不建议承诺 12h。

---

# 10. 严格的切面优先级

如果进度落后，不得平均缩水。

## Cut 1：先删 convenience

可直接延后：

```text
通用 run CLI
Web adapter
save command convenience
extra docs
```

## Cut 2：再删非核心 standard automation

可延后：

```text
LLMWorldDynamics auto assembly
所有 standard actions executor
natural attribute delta 自动 host phase
高级 GameplayMode 自动激活
```

只要 custom Python action + Python dynamics + LLM NPC 核心链仍成立。

## 不可 Cut

以下任一未完成，则不能宣称进入 complex-game authoring：

```text
ProjectIR → production WorldInstance
explicit Python activation
Python ActionExecutor → commit
Python WorldDynamicsBackend → commit
P6 LLMPolicy → proposal → executor → commit
ActorDecisionContext epistemic boundary
zero tests.* production dependency
```

---

# 11. 关键风险与预案

## Risk 1 — Cascade authority 接线比预期复杂

### 症状

action/dynamics 的 ProposedEffect 被默认 DENY。

### 预案

不要改 Cascade。

只统一：

```text
T6 grants
+
T7 metadata-derived grants
+
T3 explicit grants
→ T9 build AuthorityPolicy / ProducerRegistry
```

如果 effect 仍被拒绝：

> 查 producer/component grant，不放宽 default DENY。

---

## Risk 2 — `space.move` 等 standard effect 缺 handler

### 症状

MoveExecutor 可产生 ProposedEffect，但 Cascade 不认识 effect type。

### 预案

本轮 E2E 主 custom action 使用已经被 core 支持的结构 effect：

```text
core.set_component
```

`move` 作为额外 regression。

不要为了 move 在本轮扩张完整 effect-handler framework。

---

## Risk 3 — P6 prompt 看不到 personality

### 症状

LLMPolicy 能调用，但 ActorDecisionContext 的 self_view 不包含角色 persona。

### 预案

T1 将 CharacterSpec authoring profile 投影为 read-only component。

不修改 P6 PromptAssembler，不扩 CONTEXT_VARIABLES。

---

## Risk 4 — local project Python package import 不可见

### 症状

`import_module("complex_minimal.extension")` 找不到 project package。

### 预案

T3 只在：

```text
trust_python=True
+
explicit activation scope
```

内临时 prepend project root 到 `sys.path`，`finally` 恢复。

禁止 `spec_from_file_location` 扫文件方案。

---

## Risk 5 — T9 变成“大总管 agent”

### 症状

Assembly agent 开始修 parser、world builder、plugin loader。

### 处置

强制：

> T9 新增“非 glue 逻辑”超过约 30 行，即返回 owner task。

T9 的成功标准不是代码量，而是“调用 T1–T8”。

---

# 12. Merge 规则

建议每个 task 单独 commit：

```text
runtime: materialize project world
runtime: add engine loop
runtime: activate trusted extensions
runtime: build actor context
runtime: bind p6 llm policy
runtime: bind actions
runtime: bind dynamics
runtime: add trace sink
runtime: assemble project engine
example: add complex minimal game
test: add complex-game e2e
```

Leader 按 dependency graph cherry-pick / merge。

不要让 subagent 各自 merge 主工作分支。

### Shared hotspot

任何 task 都不改：

```text
runtime/__init__.py
pyproject.toml
README/docs index
```

最后 Leader 一次合并。

---

# 13. 最终 Gate

Gate 只回答：

> **现在能否停止继续造 subsystem，开始用这个引擎造复杂游戏？**

## Gate C1 — Authoring

新 GameProject `YAML + explicit Python package` 可 load / validate / assemble。

## Gate C2 — Trusted Python

只有声明 entrypoint 被 import；rogue `.py` 不 import。

## Gate C3 — Python Action

```text
ActionExecutor
→ ProposedEffect
→ Authority
→ Transaction
→ Reducer
→ state change
```

## Gate C4 — Python Dynamics

```text
WorldDynamicsBackend
→ ProposedEffect
→ same commit pipeline
```

## Gate C5 — LLM Actor

```text
P6 LLMPolicy
→ ActionProposal
→ same action pipeline
→ state change
```

## Gate C6 — Knowledge boundary

NPC prompt/context 不含不可见实体的完整 view。

## Gate C7 — No test runtime

`src/engine_v2/runtime/**` 零 `tests.*` import。

## Gate C8 — Repeatability

Fake LLM + deterministic Python backend 双跑一致。

## Gate C9 — Regression

原有 test suite 无新增失败。

---

# 14. 本轮结束后仍然明确欠缺的东西

若 Gate C1–C9 全通过，我认为已经可以进入：

> **“用引擎造复杂游戏，同时边用边补 engine”**

而不是继续等待 P11。

后续可做：

```text
WebSession → EngineInstance adapter
real image backend
true async inference/tasks
generic GameSystem sugar API
full persistence/replay closure
Inspector/Workbench Web route
DSH adapter
llmsim run UX
release packaging
```

这些不再阻止 game authoring。

---

# 15. 给主 Agent 的执行摘要

主 Agent 不应把本计划重新解释成 Phase。

只需要：

1. 冻结 §3；
2. 同时派 T1/T2/T3/T4；
3. 同时派 T5/T6/T7/T8；
4. T9 只做 composition；
5. T10 是“真正游戏作者”，不能碰 engine；
6. T11 是独立验收，不允许引用 tests helpers；
7. Final review 只收 blocker；
8. 12h 到点以 Gate C1–C9 判断，不追求代码“漂亮”。

最需要防止的旧失败模式：

```text
一个大 agent
→ 读整个 P1–P10
→ 压缩
→ 重建 architecture
→ 再读
→ 顺手修 docs
→ 顺手抽象
→ 任务无限膨胀
```

本轮正确模式：

```text
T1 接 world
T2 接 loop
T3 接 Python
T4 接 context
T5 接 LLM
T6 接 action
T7 接 dynamics
T8 接 trace
        ↓
T9 只插插头
        ↓
T11 用一个真实复杂游戏把所有插头拉一遍
```

这就是 12h Runtime Closure 的全部目标。
