# llmBasedSim Architecture v2 — 完整代码开发 / 重构计划

> 文档状态：Execution Plan v0.1  
> 目标架构：`llmBasedSim Engine Architecture v2`  
> 仓库基线：`ArmourPiercer1/llmBasedSim` `main@f0a1052b6c7584ab6a64614aa9bbfcd35f4254fc`  
> 适用对象：Leader Agent、Router、Subagent、人工 Reviewer  
> 核心策略：**冻结 v1 行为基线 → 旁路建立 v2 Kernel → 分层迁移 → 端到端验证 → 再替换旧 Runtime**

---

# 0. 计划目标与执行原则

本计划将 Architecture v2 转换为可以由多 Subagent 并行执行的工程任务。

计划必须同时满足：

1. 不在旧 `game_graph.py` 上继续叠加核心架构；
2. 保留当前 v1 作为行为参考与迁移源；
3. 先稳定数据 Contract，再并行开发 Runtime；
4. Kernel 必须在无 LLM、无网络、无 GUI 环境下独立测试；
5. 所有 authoritative state 变化必须走：
   `ProposedEffect → Authority → Validation → Conflict Resolution → Transaction → Reducer`；
6. 所有 Agent 工作包必须具有明确输入、输出、禁止改动范围和自动验收；
7. Phase Gate 未通过时不得继续进入后续依赖 Phase；
8. 架构歧义不得由 Subagent 自行“顺手决定”；
9. Coding Agent 是开发客户端，不是 Runtime 依赖；
10. DSH / 其他 Agent Host 负责代码写入、任务编排、Git、人工审批；llmBasedSim 负责游戏语义、验证、测试、运行、trace、replay。

---

# 1. 当前代码基线与重构策略

当前仓库已经存在较完整的 v1 原型，包括：

- `src/graph/game_graph.py`：当前主流程；
- `src/graph/game_state.py`：大一统 GameState；
- `src/game/state_apply.py`：直接状态应用；
- `src/game/attributes.py`：属性演化；
- `src/game/rules.py`、`condition_eval.py`：确定性规则 / DSL；
- `src/llm/parser.py`：结构化 LLM 输出；
- `src/prompts/loader.py` 与 `prompts/`：Prompt 层；
- `src/web/app.py`：当前 Web Session；
- `public_start/`、`private_start/`、YAML 初始化文件；
- 已有 pytest 测试覆盖 attributes、condition evaluator、初始化、long task、models、parser 等。

**重构策略不是“大爆炸式替换”。**

采用：

```text
v1 frozen runtime
      │
      │ characterization tests
      ▼
Architecture v2 side-by-side kernel
      │
      ├── migrate reusable rules / attributes / loaders
      ├── migrate LLM adapter / prompts
      ├── migrate content
      └── build compatibility layer
      ▼
v2 vertical slice
      │
      ▼
v2 becomes default runtime
      │
      ▼
remove / archive v1 orchestration
```

在 Phase 9 之前，旧 Runtime SHOULD 继续可运行。

---

# 2. 任务标签规范

每个 Task Package 均使用以下字段。

## 2.1 属性

| 标签 | 含义 |
|---|---|
| `探索代码区` | 阅读、映射、依赖分析、接口勘察、风险分析；原则上不进行大规模代码修改 |
| `开发` | 新增、重构、迁移、删除正式代码 |
| `测试` | 单元 / 集成 / characterization / scenario / 回归测试及测试工具开发 |

一个任务可有一个主属性；必要时在说明中注明辅属性。

---

## 2.2 难度

| 标签 | 含义 |
|---|---|
| `纯执行` | Contract 已明确，主要是机械实现、迁移、补测试 |
| `少量思考` | 需要局部设计判断，但不得改变 Architecture Contract |
| `较高难度` | 涉及跨模块架构、并发 / replay / authority / 状态一致性等，需要高级模型或独立 review |

---

## 2.3 能力需求

| 标签 | 含义 |
|---|---|
| `纯coding` | 文本代码、测试、文档即可完成 |
| `多模态` | 必须读取 / 判断 GUI、生成图片、渲染结果、截图等视觉内容 |

---

## 2.4 上下文档位

| 档位 | 使用条件 |
|---|---|
| `256K` | 任务可以严格限制在一个局部模块、若干接口和测试文件 |
| `1M` | 需要 repo-wide 搜索、迁移分析、大量跨文件上下文、复杂集成 / review |

**原则：尽量通过缩小任务边界让实现任务进入 256K，而不是机械使用 1M。**

---

# 3. 模型池与职责

## 3.1 模型别名

| 别名 | 模型 | 定位 |
|---|---|---|
| `Q27` | qwen3.8-27b | 免费；默认执行器；256K；纯 coding |
| `GFlash` | gemini-3.7-flash | 廉价；1M；代码区探索、repo-wide 分析、集成检查 |
| `DSV4` | deepseek-v4-flash | 1M；较贵且缓存命中不佳；用于一次性独立诊断，不作为高频迭代执行器 |
| `QMax` | qwen3.8-max | 1M；较贵、慢；用于 Contract-sensitive / 高难度设计与实现 |
| `GLM` | glm-5.3 | 1M；贵、慢、有 5h 限制；作为高级独立 reviewer / blocker solver |
| `Opus` | opus-4.6 | 很贵；仅最终升级 |
| `Mimo` | mimo-v2.5 | 廉价、1M、多模态；UI / image / visual regression 主模型 |

---

# 4. 默认路由策略

## 4.1 正常路由

| 任务条件 | 首选 |
|---|---|
| 纯执行 + 256K + coding | `Q27` |
| 少量思考 + 256K + coding | `Q27` |
| repo-wide 探索 / 1M 代码阅读 | `GFlash` |
| 1M 低中难度开发 | `GFlash`，或先 GFlash 分析后拆给 Q27 |
| Contract-sensitive / 较高难度实现 | `QMax` |
| 多模态 | `Mimo` |
| 高难度独立 review | `GLM` 或 `DSV4` |
| 多轮失败后的最终架构判断 | `Opus` |

---

## 4.2 成本优先原则

1. `Q27` 能完成的任务不升级；
2. 仅因为“文件很多”而不是“逻辑困难”时，优先 `GFlash`；
3. `QMax` 用于**架构敏感**而非“大文件”；
4. `DSV4` 避免反复 retry；适合作为一次性的独立 root-cause analysis；
5. `GLM` 不用于并行大规模 fan-out；其 5h 限制使其更适合关键 gate / blocker；
6. `Opus` 只能由 Leader 在明确满足升级条件时调用；
7. `Mimo` 不因为有 1M 就自动接纯 coding；其主要职责是视觉任务。

---

# 5. 通用失败重试 / 升级策略

## R0 — 本模型局部修复

适用：

- 单一测试失败；
- syntax/type/import；
- 少量文件内逻辑缺陷；
- Contract 未改变。

允许原模型 **最多一次** repair。

必须提供：

- 失败测试；
- traceback；
- 当前 diff；
- 预期 Contract。

---

## R1 — 上下文升级

若失败原因是：

- 未找到真正调用链；
- 修改导致远处回归；
- 256K 无法覆盖依赖；
- 不理解 v1 / v2 迁移关系；

则：

```text
Q27 → GFlash
```

GFlash 先进行 repo-wide diagnosis，再：

- 自己修复；或
- 重新切小任务给 Q27。

---

## R2 — 能力升级

若失败原因是：

- reducer / transaction / replay 不一致；
- scheduler 时序错误；
- authority/conflict 语义错误；
- 跨模块 Contract 设计；
- 异步 stale proposal；
- checkpoint / branch；
- mode merge / multi-space；

则：

```text
Q27 / GFlash → QMax
```

QMax 必须先给出：

```text
root cause
contract interpretation
minimal fix scope
required tests
```

再修改代码。

---

## R3 — 独立高级诊断

若 QMax 修复后仍失败，或两个 Agent 对 Contract 理解相反：

任选一个**独立 reviewer**：

```text
DSV4  — 适合一次性大上下文 root-cause
GLM   — 适合高级架构 review
```

Reviewer SHOULD NOT 直接大改代码，先输出 diagnosis。

---

## R4 — 最终升级

仅在：

- 已完成 R0-R3；
- blocker 会阻塞关键 Phase Gate；
- Architecture 文档仍不足以决定；
- 人工尚不能从 diagnosis 直接决定；

时使用：

```text
Opus 4.6
```

Opus 输出应作为**建议**，若建议改变 Architecture Contract，仍必须请求人工批准。

---

## R5 — 多模态失败

```text
Mimo
  ↓ one retry with explicit visual criteria
```

若仍无法判断：

> **不得使用纯文本模型假装完成视觉验收；转人工。**

---

# 6. Subagent Task Package 标准 Contract

每个工作包必须包含：

```text
Task ID:
Phase:
Goal:

Authoritative inputs:
- Architecture v2 spec section
- exact source files / directories
- upstream contracts
- accepted ADRs

Allowed files:
- ...

Forbidden changes:
- public contracts outside scope
- architecture invariants
- unrelated formatting
- dependency changes unless explicitly allowed

Deliverables:
- code
- tests
- docs / migration note if needed

Required tests:
- exact commands

Exit report:
- files changed
- tests run + results
- contract assumptions
- unresolved risks
- whether any architecture deviation was needed
```

Subagent **MUST NOT** 在 exit report 中隐藏：

- skipped tests；
- flaky behavior；
- architecture ambiguity；
- unreviewed dependency；
- temporary compatibility hack。

---

# 7. Git / 并行执行策略

推荐：

```text
main                     # v1 stable
architecture-v2          # v2 integration branch
v2/pX-task-id-*          # task branches / worktrees
```

## 7.1 可并行

可以并行：

- 探索任务；
- 不同 module 的单元测试；
- 不修改同一 Contract 的独立 implementation；
- 文档与测试基建；
- standard module 迁移（在 Kernel Contract 冻结后）。

## 7.2 不得无协调并行

以下文件 / 概念必须单 owner：

- Core ID / Revision；
- WorldState / RuntimeState；
- ProposedEffect；
- AuthorityPolicy；
- Transaction / Reducer；
- DomainEvent；
- Scheduler；
- ProjectIR schema。

同一 Phase 内对以上核心 contract 的修改需要 Leader 串行合并。

---

# 8. 总体 Phase 路线图

| Phase | 目标 | 关键门禁 |
|---|---|---|
| P0 | 冻结 v1、建立基线、创建 v2 工作区 | G0：v1 baseline 可重复、characterization tests 完成 |
| P1 | Core Data Contracts | G1：无 LLM Core model 可序列化、Contract 冻结 |
| P2 | Effect / Authority / Transaction Kernel | G2：无 raw mutation；authority/conflict/cascade 全通过 |
| P3 | Scheduler / Time / Action | G3：30 min travel 在 12 min 中断并可 replay |
| P4 | Actor / Context / Space / GameplayMode | G4：epistemic boundary + multi-space + mode overlay |
| P5 | Project Format / Module / Plugin / DSL | G5：YAML 项目可加载验证，Python plugin 显式注册 |
| P6 | LLM Runtime / Prompt / Capability Routing | G6：provider-neutral；stale result 安全；无 model pin |
| P7 | WorldDynamics | G7：Rule/LLM/Composite Dynamics 共享统一 effect pipeline |
| P8 | Persistence / Replay / Dev Control Plane | G8：snapshot/replay/branch/trace/CLI JSON |
| P9 | Standard Modules 与 v1 迁移 | G9：三类 reference game vertical slice |
| P10 | Presentation / Web / Realtime Image | G10：text/image 平行；stale render 安全；SessionManager |
| P11 | Agent-native / DSH / Hardening / Release | G11：Agent 开发闭环 + clean install + RC 人工验收 |

---

# 9. Phase 0 — Freeze v1 & Baseline

## 目标

在任何架构修改前建立可比较基线，避免后续 Agent 把“旧 bug、预期行为、架构改变”混为一谈。

## 任务包

| ID | 任务 | 属性 | 难度 | 能力 | 上下文 | 默认模型 | 依赖 |
|---|---|---|---|---|---|---|---|
| P0-T01 | Repo-wide 模块、调用链、测试、配置 inventory | 探索代码区 | 少量思考 | 纯coding | 1M | GFlash | 无 |
| P0-T02 | 跑现有 pytest/ruff，建立 baseline report | 测试 | 纯执行 | 纯coding | 256K | Q27 | 无 |
| P0-T03 | 为 `game_graph.py` 关键 11-node 流程补 characterization tests | 测试 | 较高难度 | 纯coding | 1M | QMax | T01 |
| P0-T04 | 保存 3–5 个 v1 reference init/save/input transcript | 测试 | 少量思考 | 纯coding | 256K | Q27 | T01 |
| P0-T05 | 建立 `src/engine_v2` 或目标新目录 skeleton，禁止接入旧 Runtime | 开发 | 纯执行 | 纯coding | 256K | Q27 | T02 |
| P0-T06 | 将 Architecture v2 规范、ADR index、迁移约束放入 repo docs | 开发 | 少量思考 | 纯coding | 1M | GFlash | T01 |

## G0 门禁

必须：

- 当前已有测试全部运行并记录；
- 若 baseline 自身有失败，明确分类为：
  `known-v1-failure` / `environment failure` / `real regression`；
- 旧 v1 能用至少 2 个 reference project 启动；
- `game_graph.py` 的主要输入输出行为有 characterization coverage；
- 新 v2 目录可以 import，但没有替换 v1；
- Architecture 文档进入 repo。

**若当前 baseline 存在无法解释的失败，停止后续 Phase。**

---

# 10. Phase 1 — Core Data Contracts

## 目标

把 Architecture v2 中最核心的数据语言固定下来。

## 任务包

| ID | 任务 | 属性 | 难度 | 能力 | 上下文 | 默认模型 |
|---|---|---|---|---|---|---|
| P1-T01 | `EntityId / EffectId / EventId / TransactionId / Revision` primitives | 开发 | 纯执行 | 纯coding | 256K | Q27 |
| P1-T02 | `WorldState / RuntimeState / BackendStateRef / TraceRecord` contract | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P1-T03 | Entity + typed component logical facade；不绑定 ECS | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P1-T04 | `ActionProposal / ActiveAction / ProposedEffect / CommittedEffect / DomainEvent / Transaction` schemas | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P1-T05 | Snapshot / serialization / immutable read view 基础设施 | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P1-T06 | Core schema round-trip、ID uniqueness、revision contract tests | 测试 | 少量思考 | 纯coding | 256K | Q27 |
| P1-T07 | Core Contract independent review | 探索代码区 | 较高难度 | 纯coding | 1M | GLM |

## 强制约束

- 不允许把标准 RPG 字段写进 Kernel；
- 不允许加入 provider/model；
- 不允许让 Entity ID 依赖 Python object；
- 不允许从 v1 GameState 直接复制 transient/presentation 混合结构；
- public contract 修改必须经 Gate review。

## G1

- Core import 不需要 LangGraph / OpenAI；
- 所有 schema 可 round-trip；
- World revision 明确；
- public IDs stable；
- Core unit tests 无网络通过；
- 高级 reviewer 没有发现“后续必须 breaking change”的明显问题。

---

# 11. Phase 2 — Effect / Authority / Transaction Kernel

## 目标

建立 v2 最重要的 Kernel invariant：

> producer 可以决定候选状态，但没有 producer 可以直接写 WorldState。

## 任务包

| ID | 任务 | 属性 | 难度 | 能力 | 上下文 | 默认模型 |
|---|---|---|---|---|---|---|
| P2-T01 | Reducer-only write barrier / mutation API | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P2-T02 | Authority selector：component/field/domain/effect/entity tag | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P2-T03 | AuthorityPolicy evaluation | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P2-T04 | Effect schema/invariant/stale validation pipeline | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P2-T05 | ConflictResolver framework + default strategies | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P2-T06 | Transaction atomic commit + revision increment | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P2-T07 | DomainEvent + provenance + causal root + cascade executor | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P2-T08 | Cycle/depth diagnostics | 测试 | 少量思考 | 纯coding | 256K | Q27 |
| P2-T09 | Authority / conflict / transaction adversarial tests | 测试 | 较高难度 | 纯coding | 1M | GFlash |

## 必须测试

1. 无权限 producer 写 state → reject；
2. 两个合法 writer 冲突 → resolver 可解释；
3. transaction 中一项 invalid → atomic failure；
4. commit 只增加一次 revision；
5. event 保存 transaction/source/cause；
6. `HP changed → set HP → HP changed` cycle 可检测；
7. 任何 Public API 无法从 producer 绕过 reducer。

## G2

所有上述测试通过，并通过静态代码搜索确认：

- Runtime Producer 中不存在直接 authoritative state mutation；
- Reducer 不调用 LLM；
- Reducer 不做语义推断。

---

# 12. Phase 3 — Scheduler / Time / Action

## 目标

替代 `tick_speed_resolve` 和 LangGraph 每回合固定流水线。

## 任务包

| ID | 任务 | 属性 | 难度 | 能力 | 上下文 | 默认模型 |
|---|---|---|---|---|---|---|
| P3-T01 | LogicalClock + serializable ScheduledEvent queue | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P3-T02 | ActionRegistry + parameter schema | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P3-T03 | Action lifecycle state machine | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P3-T04 | ActiveAction progress / checkpoint / completion | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P3-T05 | InterruptCondition + DecisionBoundary | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P3-T06 | Actor wakeup hook / scheduler callback contract | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P3-T07 | Generic stale proposal revalidation | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P3-T08 | Travel/interruption/replay timing tests | 测试 | 较高难度 | 纯coding | 1M | GFlash |

## 核心 Gate 场景

```text
Player starts 30 min travel
t = 12 min encounter event
→ scheduler stops fast-forward
→ ActiveAction progress == 12/30
→ player decision boundary
→ action may resume / abort
```

不得：

- 因 NPC 1 秒动作强迫玩家每秒操作；
- 通过“把 position 直接设置到终点”伪装长动作；
- 使用不可检查 coroutine 作为唯一 scheduler truth。

## G3

- 场景精确通过；
- scheduler queue 可 serialize；
- interruption 后 progress 正确；
- replay event order 一致；
- no LLM required。

---

# 13. Phase 4 — Actor / Context / Space / GameplayMode

## 目标

形成 Runtime 世界语义层，但仍不接实际云模型。

## 任务包

| ID | 任务 | 属性 | 难度 | 能力 | 上下文 | 默认模型 |
|---|---|---|---|---|---|---|
| P4-T01 | BehaviorPolicy / PlayerPolicy Protocol | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P4-T02 | ActorDecisionContext + ContextProvider | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P4-T03 | Capability grant/check system | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P4-T04 | Standard Observation / Knowledge skeleton | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P4-T05 | SpaceBackend Protocol + named SpatialDomain | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P4-T06 | GraphSpace + GridSpace reference implementations | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P4-T07 | Entity multi-space mapping | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P4-T08 | GameplayMode overlay + per-property merge strategies | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P4-T09 | ModeChangeRequest resolver | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P4-T10 | epistemic boundary / multi-space / mode integration tests | 测试 | 较高难度 | 纯coding | 1M | GFlash |

## G4

必须证明：

- Alice 不知道她没有 Observation/Knowledge 的 Bob 偷窃事件；
- 自定义 Policy 不能因为更换 Prompt 而获得 global read；
- 一个 Entity 可拥有 overworld + tactical 映射；
- Dialogue + Tactical 可同时 active；
- TimePolicy 冲突有明确 winner；
- mode change 不复制 WorldState。

---

# 14. Phase 5 — Project Format / Module / Plugin / DSL

## 目标

让 Game Project 成为可由人类、Coding Agent、未来 GUI 同时维护的 source of truth。

## 任务包

| ID | 任务 | 属性 | 难度 | 能力 | 上下文 | 默认模型 |
|---|---|---|---|---|---|---|
| P5-T01 | Project Format v2 repo-wide schema survey | 探索代码区 | 少量思考 | 纯coding | 1M | GFlash |
| P5-T02 | ProjectIR schema + compiler | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P5-T03 | YAML/file-group v2 loader | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P5-T04 | Module manifest + dependency graph | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P5-T05 | local explicit plugin manifest loader | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P5-T06 | Python package entry-point plugin loader | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P5-T07 | 现有 condition/rule DSL 封装为标准 Rule module | 开发 | 较高难度 | 纯coding | 1M | GFlash |
| P5-T08 | YAML round-trip-safe 策略 / loader tests | 测试 | 少量思考 | 纯coding | 256K | Q27 |
| P5-T09 | `llmsim validate --json` 初版 | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P5-T10 | simple zero-Python reference project | 测试 | 纯执行 | 纯coding | 256K | Q27 |

## G5

- 零 Python 项目可以 load + validate；
- Python plugin 必须显式注册；
- 不允许目录自动扫描执行任意 Python；
- module dependency cycle 可诊断；
- DSL 继续支持已有简单规则，但没有引入 loop/function-definition 等“重新发明 Python”的能力；
- validator 返回 machine-readable diagnostics。

---

# 15. Phase 6 — LLM Runtime / Prompt / Capability Routing

## 目标

在 Kernel 稳定以后接入 LLM，但 LLM 不改变 Kernel authority 规则。

## 任务包

| ID | 任务 | 属性 | 难度 | 能力 | 上下文 | 默认模型 |
|---|---|---|---|---|---|---|
| P6-T01 | v1 LLM/parser/prompt 调用链 survey | 探索代码区 | 少量思考 | 纯coding | 1M | GFlash |
| P6-T02 | InferenceCapabilityProfile schema | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P6-T03 | DeploymentProfile + user-side model resolver | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P6-T04 | provider-neutral structured inference adapter | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P6-T05 | PromptAssembler L0-L4 + provenance | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P6-T06 | LLMBehaviorPolicy reference implementation | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P6-T07 | revision-aware async result handling | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P6-T08 | optional behavior critic / one-shot repair module | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P6-T09 | fake-model deterministic tests | 测试 | 少量思考 | 纯coding | 256K | Q27 |
| P6-T10 | actual provider smoke-test script（不进 CI secrets） | 测试 | 少量思考 | 纯coding | 256K | Q27 |

## 强制设计约束

Game Project：

```text
允许：
context length requirement
multimodal requirement
reasoning class
structured-output requirement
tool requirement
recommendation

禁止：
provider pin
model name pin
API key
endpoint credential
```

## G6

- 假模型可完整跑；
- user DeploymentProfile 可以改变实际模型而不修改游戏项目；
- Prompt override 不提升 context capability；
- stale ActionProposal 不会直接 commit；
- trace 不记录 credential；
- LLM parser 不依赖 DeepSeek/OpenAI 特定语义作为 Core Contract。

---

# 16. Phase 7 — WorldDynamics

## 目标

统一 deterministic rules、LLM inference、数值物理和 Hybrid backend。

## 任务包

| ID | 任务 | 属性 | 难度 | 能力 | 上下文 | 默认模型 |
|---|---|---|---|---|---|---|
| P7-T01 | WorldDynamicsBackend Protocol + metadata | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P7-T02 | RuleDynamics reference backend | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P7-T03 | LLMWorldDynamics backend | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P7-T04 | CompositeDynamics orchestration | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P7-T05 | dynamics domain ownership / authority integration | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P7-T06 | reference checkpointable toy numerical backend | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P7-T07 | 外部 physics library PoC / dependency evaluation | 探索代码区 | 较高难度 | 纯coding | 1M | GFlash |
| P7-T08 | anvil/gem deterministic + LLM + conflict scenarios | 测试 | 较高难度 | 纯coding | 1M | GFlash |

## G7

至少通过：

### Case A
无详细物理：

```text
LLMWorldDynamics → GemMoved
```

### Case B
Rigid/Rule backend 与 LLM 同时 propose：

```text
physics → stay
LLM → fall
```

必须可见两个 ProposedEffect，并由 resolver 决定。

### Case C
toy numerical backend：

- checkpoint；
- restore；
- branch 后继续；
- metadata 正确。

不得在 Kernel 中写：

```text
if backend is LLM ...
elif backend is physics ...
```

---

# 17. Phase 8 — Persistence / Replay / Dev Control Plane

## 目标

把 replay/debug 能力作为架构能力，而不是后补日志。

## 任务包

| ID | 任务 | 属性 | 难度 | 能力 | 上下文 | 默认模型 |
|---|---|---|---|---|---|---|
| P8-T01 | snapshot format / version metadata | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P8-T02 | filesystem PersistenceBackend reference | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P8-T03 | event-level replay engine | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P8-T04 | BackendCheckpoint registry / restore | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P8-T05 | branch / fork WorldInstance prototype | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P8-T06 | DevelopmentCommand / ExternalInterventionEffect | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P8-T07 | trace query / causal chain API | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P8-T08 | CLI `inspect/trace/replay/branch/test --json` | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P8-T09 | corruption/replay/branch adversarial tests | 测试 | 较高难度 | 纯coding | 1M | GFlash |

## G8

必须完成：

- snapshot → load → same WorldState；
- event replay → same committed state；
- branch A/B 独立；
- non-checkpointable backend 明确拒绝 branch，而不是静默错误；
- Development intervention 可在 trace 中区分；
- CLI JSON schema 稳定；
- causal chain 可从 event 回溯至 action / effect / producer。

---

# 18. Phase 9 — Official Modules / v1 Migration

## 目标

迁移 v1 中真正有价值的 gameplay systems，而不是迁移旧 orchestration。

## 任务包

| ID | 任务 | 属性 | 难度 | 能力 | 上下文 | 默认模型 |
|---|---|---|---|---|---|---|
| P9-T01 | v1 reusable vs obsolete code mapping | 探索代码区 | 较高难度 | 纯coding | 1M | GFlash |
| P9-T02 | Attributes module migration | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P9-T03 | Inventory / object-state module | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P9-T04 | Relationships module | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P9-T05 | StandardCharacter module | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P9-T06 | Perception / Knowledge module migration | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P9-T07 | Scenario / Trigger module | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P9-T08 | standard movement / interaction action executors | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P9-T09 | v1 init-file → Project Format v2 migration / compatibility | 开发 | 较高难度 | 纯coding | 1M | GFlash |
| P9-T10 | 删除 NPC global-event omniscience 行为并补回归测试 | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P9-T11 | Galgame vertical slice sample | 测试 | 少量思考 | 纯coding | 256K | Q27 |
| P9-T12 | Sandbox vertical slice sample | 测试 | 较高难度 | 纯coding | 1M | GFlash |
| P9-T13 | Tactical vertical slice sample | 测试 | 较高难度 | 纯coding | 1M | GFlash |
| P9-T14 | v1/v2 differential behavior review | 测试 | 较高难度 | 纯coding | 1M | GLM |

## G9

三套 sample 必须分别证明：

### Galgame
- dialogue；
- character policy；
- relationship；
- observation；
- narrative-ready ViewState。

### Sandbox
- long action；
- world time；
- NPC wakeup；
- knowledge boundary；
- LLM / rules dynamics。

### Tactical
- Grid/Hex-like Space；
- tactical GameplayMode；
- deterministic actions；
- mode transition。

并且：

- 旧 init file 可以 migration 或给出明确 incompatible diagnostics；
- 旧 LangGraph 不再是 v2 Engine Runtime 的必要依赖。

---

# 19. Phase 10 — Presentation / Web / Realtime Image

## 目标

建立 Text / Image / Tactical presentation 平行结构。

## 任务包

| ID | 任务 | 属性 | 难度 | 能力 | 上下文 | 默认模型 |
|---|---|---|---|---|---|---|
| P10-T01 | ViewState / SceneView derivation | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P10-T02 | Narrator presentation backend | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P10-T03 | VisualDirector + RenderIntent contract | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P10-T04 | image backend adapter + revision/scene stale handling | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P10-T05 | Web singleton → EngineInstance / SessionManager | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P10-T06 | Runtime Inspector minimal web view | 开发 | 较高难度 | 多模态 | 1M | Mimo |
| P10-T07 | LLM Workbench minimal prompt/trace view | 开发 | 较高难度 | 多模态 | 1M | Mimo |
| P10-T08 | stale-image / scene-continuity visual test | 测试 | 少量思考 | 多模态 | 1M | Mimo |

## G10

自动：

- Image A 属于 `view_revision=83`，当前已到 87 → 不错误覆盖当前 view；
- Narrator 与 VisualDirector 均读取结构化 View，而非 image 强制依赖 prose；
- Web 不存在 module-level singleton World；
- inspector 能定位 event → transaction → effect → producer。

人工：

- GUI 信息层次可读；
- 实时图像不会明显错场；
- Galgame 场景视觉连续性达到可接受水平。

---

# 20. Phase 11 — Agent-native / DSH / Hardening / Release

## 目标

形成可实际交给 Coding Agent 使用的开发闭环，并完成 RC。

## 任务包

| ID | 任务 | 属性 | 难度 | 能力 | 上下文 | 默认模型 |
|---|---|---|---|---|---|---|
| P11-T01 | structured diagnostic schema 统一 | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P11-T02 | `.llmsim/agent` guidance generator | 开发 | 少量思考 | 纯coding | 256K | Q27 |
| P11-T03 | CLI agent workflow examples / JSON contracts | 开发 | 纯执行 | 纯coding | 256K | Q27 |
| P11-T04 | DSH integration surface survey | 探索代码区 | 少量思考 | 纯coding | 1M | GFlash |
| P11-T05 | DSH thin adapter prototype | 开发 | 较高难度 | 纯coding | 1M | QMax |
| P11-T06 | CI / lint / test matrix / clean install | 测试 | 少量思考 | 纯coding | 256K | Q27 |
| P11-T07 | performance / memory / long-run soak tests | 测试 | 较高难度 | 纯coding | 1M | GFlash |
| P11-T08 | dependency/license inventory | 探索代码区 | 少量思考 | 纯coding | 1M | GFlash |
| P11-T09 | release docs / migration guide / architecture docs sync | 开发 | 少量思考 | 纯coding | 1M | GFlash |
| P11-T10 | RC adversarial integration review | 测试 | 较高难度 | 纯coding | 1M | GLM |
| P11-T11 | final visual / human workflow package | 测试 | 少量思考 | 多模态 | 1M | Mimo |

## G11

- clean environment 安装成功；
- no-secret CI 全绿；
- DSH 能：
  `read guidance → modify sample → validate → test → run → inspect trace`；
- Engine 不依赖 DSH 才能运行；
- architecture spec 与代码一致；
- dependency/license 清单完成；
- 人工最终验收通过。

---

# 21. Phase Gate 统一规则

进入下一 Phase 前，Leader 必须生成 Gate Report：

```text
Gate:
Commit SHA:
Tasks completed:
Tasks waived:
Tests:
Known failures:
Architecture deviations:
Open risks:
Human review required:
Decision: PASS / FAIL / CONDITIONAL
```

**默认禁止 CONDITIONAL PASS。**

只有不影响下游 Contract 的非核心缺陷才可 conditional，并必须建立显式 issue。

---

# 22. Agent 自动测试与验收标准

## 22.1 所有代码包的通用要求

Subagent 必须：

```bash
pytest <relevant tests>
ruff check <changed paths>
```

若 Phase 已有完整测试可运行：

```bash
pytest
```

必须提供真实命令输出摘要，不得仅声称“tests should pass”。

---

## 22.2 Core Kernel 测试

必须无：

- API key；
- network；
- provider；
- LangGraph server；
- Web。

测试类别：

### State
- serialization；
- ID stability；
- revision；
- invalid reference；
- snapshot isolation。

### Effects
- permission denied；
- validator fail；
- conflict；
- merge；
- transaction atomicity。

### Events
- provenance；
- causal root；
- cascade；
- cycle；
- max depth。

### Scheduler
- ordering；
- same-time events；
- cancellation；
- interruption；
- resume；
- serialization。

---

## 22.3 Property / adversarial 风格

关键模块不应只测试 happy path。

Agent 必须主动构造：

- duplicated ID；
- missing entity；
- stale revision；
- conflicting effects；
- circular module dependency；
- event loop；
- invalid mode merge；
- non-checkpointable backend branch；
- out-of-order async result；
- unauthorized context access。

---

## 22.4 LLM 测试

CI 默认使用 FakeInferenceBackend。

必须测试：

- valid structured output；
- malformed output；
- retry；
- timeout；
- stale response；
- capability mismatch；
- deployment resolver failure；
- prompt provenance；
- no model pin in GameProject。

真实 provider smoke test：

- 手动或安全环境触发；
- 不作为普通 PR Gate；
- 不提交 secret。

---

## 22.5 Replay 验收

Agent 必须证明：

```text
Snapshot N
+ committed event/effect sequence
→ State M
```

与原 State M 语义一致。

至少对：

- deterministic action；
- interrupted long action；
- mode transition；
- dynamics effect；

各测试一次。

---

## 22.6 Migration 验收

对 reference v1 content：

```text
v1 input
→ migration
→ v2 project
→ validate
→ run
```

若不兼容：

- error 必须明确指出；
- 不允许 silent drop；
- 不允许 silently reinterpret 高风险字段。

---

# 23. 人工执行的测试与验收

自动测试不能替代以下判断。

## H1 — Phase 0 行为基线确认

人工确认：

- 当前 v1 reference game 的行为确实是“可作为迁移参考”的行为；
- characterization test 没有把明显 bug 锁成永恒 contract。

若发现 v1 是 bug：

```text
mark as known bug
do not require v2 compatibility
```

---

## H2 — Core Contract Review（P1/P2）

人工查看：

- WorldState / RuntimeState 边界；
- ProposedEffect；
- Authority；
- Transaction；
- Event；
- public naming。

重点不是代码 style，而是：

> 是否愿意长期承担这个 public API。

---

## H3 — Dynamic Time Game Feel

自动测试只能证明：

```text
30 min / 12 min
```

计算正确。

人工必须判断：

- travel fast-forward 是否自然；
- 对话是否过快/过慢；
- tactical 时序是否符合游戏体验；
- interrupt 是否造成频繁打断。

---

## H4 — NPC 行为合理性

人工使用实际用户选择模型测试：

- NPC 是否有明显 omniscience；
- personality 是否过度僵化；
- critic 是否造成所有角色“保守化”；
- repair 是否保持原目标；
- LLMWorldDynamics 是否产生过多无关世界变化。

---

## H5 — Model Capability / Deployment UX

人工确认：

- 游戏作者不需要知道具体 provider；
- 用户可以清楚地将 capability profile 映射到自己的模型；
- capability mismatch 报错能看懂；
- model 建议不会演化成 hidden hard pin。

---

## H6 — 三类 reference game

人工至少完整体验短流程：

### Galgame
- 10–20 分钟；
- 多轮对话；
- relationship/knowledge；
- narrative。

### Sandbox
- 长距离动作；
- NPC off-screen；
- world dynamics；
- interruption。

### Tactical
- exploration → tactical → exploration；
- space mapping；
- deterministic action；
- UI / time transition。

---

## H7 — 实时图片

必须人工检查：

- 角色身份连续；
- 场景位置没有明显错位；
- stale image 不覆盖新场景；
- 视觉信息与 authoritative state 不冲突；
- 图像失败不会阻塞游戏 Runtime。

Mimo 可以预筛，但不能代替最终人工视觉验收。

---

## H8 — Agent-native DX

由人工真实使用 DSH 或另一个 Coding Agent：

1. 初始化项目；
2. 读取 `.llmsim/agent`；
3. 要求 Agent 增加一个简单玩法；
4. Agent 修改源码；
5. `llmsim validate`；
6. scenario test；
7. runtime trace；
8. 修复一个故意注入的 bug。

观察：

- Agent 是否能找到正确 source of truth；
- 是否经常误改生成文件；
- diagnostics 是否足够；
- 是否需要大量人工提示。

---

## H9 — Release Candidate

最终人工决定：

- 是否切换默认 Runtime；
- v1 是否进入 legacy；
- migration 文档是否足够；
- 许可证 / 第三方 notices 是否可发布；
- 哪些 experimental API 不应承诺稳定。

---

# 24. 必须中断开发并请求人工介入的场景

以下为 **HARD STOP**。Subagent / Leader Agent 不得自行继续。

## S1 — 需要改变 Architecture Kernel invariant

例如提出：

- producer 必须直接写 WorldState；
- Reducer 需要调用 LLM；
- Session 和 World 必须重新合并；
- Prompt override 自动获得 global read；
- Game Project 必须 pin 某模型。

必须人工确认。

---

## S2 — Public Contract 存在两种同样合理但不兼容的设计

尤其：

- ProposedEffect；
- Authority selector；
- Transaction；
- Event provenance；
- Scheduler；
- ProjectIR；
- Space domain identity。

Agent 不得自行选一个并大规模扩散。

---

## S3 — 为通过测试需要 destructive migration

例如：

- 删除旧 save 数据；
- silently drop 字段；
- 改变 v1 内容语义；
- 无法 backward convert。

必须人工决定兼容策略。

---

## S4 — 引入新的重大依赖 / License 风险

尤其：

- GPL / AGPL / LGPL / MPL 等需要重新评估的代码复用；
- 大型游戏引擎；
- 数据库；
- 外部 physics runtime；
- JS/Node stack；
- 本地服务框架。

Subagent 可以提出建议，不得自行永久纳入 Core。

---

## S5 — Backend 无法满足 replay/checkpoint Contract

若某重要数值 backend 只能运行但：

- 无法 snapshot；
- 无法 restore；
- branch 会失真；

且它又是核心目标 backend，必须人工决定：

- 接受能力降级；
- 改 backend；
- 改 checkpoint contract。

---

## S6 — 同一任务经过能力升级仍连续失败

触发条件：

- R0 已执行；
- R1/R2 已执行；
- 已有至少一个独立高级 diagnosis；
- 仍无稳定 root cause。

不得无限烧模型。

---

## S7 — 测试通过但语义明显违背设计

例如：

- 用 mock 绕过真正 authority；
- replay 只是重新加载最终 snapshot；
- “multi-space” 实际只保存一个 active space；
- LLM 写入直接藏在 reducer；
- mode change 通过复制 WorldState 实现。

必须停。

---

## S8 — 发现 baseline 本身与 Architecture 目标冲突，但兼容意图不清楚

不要自动兼容 v1 bug。

---

## S9 — 并发 / 异步导致无法解释的 state corruption

出现：

- revision 倒退；
- duplicate commit；
- lost event；
- stale effect 偶发写入；
- branch 互相污染；

立即停止新 feature，转 root-cause。

---

## S10 — 性能目标需要架构级 tradeoff

若发现：

- serializable scheduler 明显成为瓶颈；
- trace 体积不可接受；
- event sourcing 对长时间沙盒成本过高；
- checkpoint 极大；

而修复需要改变 public semantics，必须人工选择。

---

## S11 — 多模态主观验收无法确定

Mimo 不能可靠判断：

- visual continuity；
- UI 可读性；
- image/state 是否冲突；

转人工，不得让纯 coding model 替代。

---

## S12 — Agent 想重构超出工作包边界

若 Subagent 声称：

> “为了完成本任务，需要顺便重写另外三个核心模块。”

必须返回 Leader 重新切包。

---

# 25. Integration Agent 职责

每个 Phase 结束应分配一个 Integration Agent。

推荐：

- 普通 Phase：`GFlash`
- Contract-sensitive Gate：`QMax`
- RC：`GLM`

Integration Agent 不负责大量新 feature，而负责：

1. 读取本 Phase 所有 diff；
2. 检查 Contract 是否漂移；
3. 跑 full tests；
4. 搜索 duplicate implementation；
5. 检查临时 adapter/hack；
6. 检查不同 Subagent 对同一概念命名是否分叉；
7. 生成 Gate Report。

---

# 26. Code Review 分层

## Level 0 — Executor self-check

每个 task 必须做。

## Level 1 — Peer Agent review

适用于：

- 256K 普通实现；
- standard modules；
- tests。

默认 reviewer 可用 `Q27` 或 `GFlash`。

## Level 2 — Architecture review

适用于：

- State；
- Effect；
- Authority；
- Transaction；
- Scheduler；
- ProjectIR；
- Context Capability；
- Dynamics；
- Replay。

默认 `QMax`；Gate 可用 `GLM` 独立 review。

## Level 3 — Human review

适用于：

- public Contract freeze；
- architecture change；
- license；
- destructive migration；
- RC。

---

# 27. 推荐的 Router 规则伪代码

```text
if task.multimodal:
    route = Mimo
else if task.context == 256K and task.difficulty in [pure_execution, some_thinking]:
    route = Q27
else if task.attribute == exploration and task.context == 1M:
    route = GFlash
else if task.difficulty == high:
    route = QMax
else:
    route = GFlash
```

失败：

```text
if local_test_failure and retry_count == 0:
    retry_same_model()

elif context_miss:
    escalate_to(GFlash)

elif architecture_sensitive_failure:
    escalate_to(QMax)

elif repeated_failure:
    independent_diagnosis(DSV4 or GLM)

elif still_blocked:
    if architecture_decision_needed:
        HUMAN_STOP
    else:
        last_resort(Opus)
```

---

# 28. 模型使用建议摘要

## qwen3.8-27b

大量使用：

- schema 实现；
- standard module；
- CLI；
- tests；
- migration mechanics；
- simple adapters。

**它应该承担最多 task count。**

---

## Gemini 3.7 Flash

大量使用：

- repo-wide exploration；
- v1/v2 mapping；
- integration review；
- large-context test analysis；
- dependency graph；
- migration diagnosis。

最推荐的模式：

```text
GFlash explores / scopes
→ Q27 executes local packages
```

---

## Qwen3.8 Max

集中用于：

- Core Contract；
- Transaction；
- Scheduler；
- Context security；
- Dynamics composition；
- Replay / branch；
- ProjectIR。

不要拿来批量写简单 tests。

---

## DeepSeek V4 Flash

由于成本 / cache 问题：

- 不做默认 executor；
- 不做循环 repair；
- 适合“把完整 repo + failure trace 一次给进去，要求独立诊断”。

---

## GLM-5.3

利用其高能力但考虑 5h 限制：

- Gate reviewer；
- architecture blocker；
- RC adversarial review。

不要一次拉十个 GLM Subagent。

---

## Opus-4.6

仅：

- R0–R3 已失败；
- blocker 很关键；
- architecture / concurrency / replay 问题仍无法解释。

不得作为“保险起见”的默认 reviewer。

---

## Mimo-v2.5

主要：

- Runtime Inspector；
- LLM Workbench；
- Web UI；
- image pipeline；
- visual regression。

文本 coding 任务若无视觉输入，一般不优先。

---

# 29. CI 建议

最低 CI：

```text
Python 3.12
pytest
ruff
```

v2 后期增加：

```text
core no-network test
reference-project scenario test
snapshot/replay test
clean-install test
migration test
```

Kernel test job MUST 显式禁止网络，以确保没有偷偷依赖模型。

建议添加：

- `pytest-cov`：用于监控 core 关键路径；
- 关键 Kernel 模块目标 statement coverage ≥ 90%；
- 比 coverage 更重要的是 critical branch scenario 列表全部存在。

Coverage 未达标不是唯一 gate；核心语义缺失测试即使 100% coverage 也不得通过。

---

# 30. 性能与长期测试

Phase 8 后建立基准：

```text
100 entities
1000 entities
10k scheduled events
1h logical simulation
1000 revisions replay
50 branches (toy backend)
```

记录：

- commit throughput；
- scheduler pop/push；
- snapshot size；
- trace growth；
- replay time；
- branch memory；
- Context assembly size。

暂不设强硬性能数字。

若后续优化需要改变 Architecture Contract，触发人工 stop。

---

# 31. 推荐的 Reference Scenarios

这些场景同时作为测试、demo 和 regression corpus。

## RS-01 Locked Door

确定性 authority。

## RS-02 Anvil Gem

LLM Dynamics authority。

## RS-03 Conflicting Gem Dynamics

Physics / LLM conflict。

## RS-04 Interrupted Travel

Dynamic time。

## RS-05 Hidden Theft

Epistemic boundary。

## RS-06 Tavern Assassin

Exploration + Dialogue → Tactical + Dialogue。

## RS-07 Stale Alice Proposal

revision-aware async。

## RS-08 Replay Branch

checkpoint / branch。

## RS-09 Stale Generated Image

Presentation revision。

## RS-10 Agent Adds Infection System

Agent-native developer workflow。

---

# 32. Milestone 级人工决策点

建议只在以下节点强制人工 Gate，避免每个小任务都阻塞：

```text
M0 = G0 baseline
M1 = G2 Kernel write semantics
M2 = G4 runtime semantic primitives
M3 = G6 LLM integration
M4 = G8 replay/devtools
M5 = G9 three-game vertical slice
M6 = G10 presentation
M7 = G11 RC
```

其中：

- M1/M4 最重要；
- 若 M1 错误，所有 gameplay module 都要返工；
- 若 M4 错误，Debugger/Agent-native 方向会失去基础。

---

# 33. “完成”的定义

一个 Phase 不以“代码已经写完”为完成。

必须同时满足：

```text
Implementation complete
AND local tests pass
AND full phase tests pass
AND documentation updated
AND trace/diagnostics available where required
AND no unresolved architecture deviation
AND Gate Report PASS
```

一个 Subagent 工作包也不以“创建了文件”为完成。

如果没有真实测试结果，则状态只能是：

```text
IMPLEMENTED_UNVERIFIED
```

不得标记 DONE。

---

# 34. 最终交付形态

Architecture v2 完成后，仓库应达到：

```text
llmBasedSim/
├─ src/
│  ├─ engine/
│  │  ├─ core/
│  │  ├─ runtime/
│  │  ├─ persistence/
│  │  ├─ context/
│  │  └─ plugins/
│  ├─ modules/
│  ├─ agents/
│  ├─ dynamics/
│  ├─ llm/
│  ├─ prompts/
│  ├─ content/
│  ├─ devtools/
│  ├─ presentation/
│  └─ adapters/
├─ tests/
│  ├─ core/
│  ├─ runtime/
│  ├─ modules/
│  ├─ replay/
│  ├─ migration/
│  └─ scenarios/
├─ examples/
│  ├─ galgame/
│  ├─ sandbox/
│  └─ tactical/
├─ docs/
│  ├─ architecture/
│  ├─ project-format/
│  ├─ plugin-api/
│  └─ migration/
└─ ...
```

并能够：

```text
llmsim validate
llmsim test
llmsim run
llmsim inspect
llmsim trace
llmsim replay
llmsim branch
```

---

# 35. 执行优先级结论

如果资源有限，绝不能平均分配开发力量。

最高优先级：

```text
P0 → P1 → P2 → P3 → P4 → P8
```

特别是：

```text
Effect / Authority / Transaction
Scheduler
Replay / Trace
```

是整个项目最不应该“后补”的三组能力。

其次：

```text
P5 Project Format
P6 LLM Runtime
P7 Dynamics
```

最后再扩展：

```text
P9 Standard Modules
P10 Presentation
P11 GUI / DSH polish
```

换言之：

> **先做一个无 LLM 但状态、时间、因果、权限、回放都正确的游戏内核，再把 LLM 挂上去。**

这是降低本次架构代际重构风险的核心原则。

---

# 36. Leader Agent 开工指令建议

正式开始时，Leader 首先只下发：

```text
P0-T01
P0-T02
```

两者完成后再建立：

```text
P0-T03/T04/T05/T06
```

**不要一开始并行启动 P1/P2。**

在 G0 通过以后：

1. 由 `QMax` 负责 P1 Contract owner；
2. Q27 执行其明确切分的 primitives/tests；
3. P1-T07 独立 reviewer；
4. 人工冻结 M1 前的 public Contract；
5. 再进入 Effect Kernel。

这比一次拉起十几个 Subagent 全仓库重构可靠得多。

---

# 37. 最终原则

这次重构最重要的成功标准不是：

> “把旧代码重写成了更多文件。”

而是：

1. **任何世界变化都能回答谁提出、谁允许、为什么接受、最终修改了什么；**
2. **任何 NPC 决策都能回答它当时看到了什么、知道什么、依据哪个 revision；**
3. **任何长时间动作都能被中断、恢复、追踪；**
4. **任何重要运行结果都能 replay / inspect；**
5. **复杂数值后端与 LLM 推断能共享同一世界提交协议；**
6. **游戏作者声明能力，用户决定模型；**
7. **Coding Agent 可以高效开发，但 Engine 不依赖任何单一 Agent Host；**
8. **当自动 Agent 不应继续做决定时，系统有明确 HARD STOP。**

达到这些目标以后，再增加更多 RPG mechanics、图片生成、GUI 或插件生态，才不会重新把项目推回一个不可控的 monolithic agent graph。
