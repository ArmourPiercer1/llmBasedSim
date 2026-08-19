# `src/engine_v2` — Architecture v2 引擎（骨架阶段）

> **状态**：Phase 0 骨架（P0-T05）。本目录当前**只有占位结构**：每个子包的
> `__init__.py` 仅含模块 docstring，不 import 任何依赖，不实现任何功能，
> 不接入、不引用 v1 旧 Runtime。
>
> **依据**：Spec §44「推荐源码目录」、§46「第一阶段 v2 MVP 范围」、
> §47「第一期开发顺序」（Phase 0）；执行计划 §9 P0-T05。

## 1. 目录布局

| 子包 | 职责（占位 docstring 中有详述） | Spec 章节 | 填充 Phase |
|---|---|---|---|
| `core/` | Kernel 核心契约：Entity / Component、WorldState / RuntimeState、Revision、Action、Effect、Authority、Validation、Conflict、Transaction / Reducer、DomainEvent | §4、§8、§9、§10、§11、§16、§18、§19、§20、§21 | Phase 1 |
| `runtime/` | Engine 主循环宿主：WorldInstance / Session、Scheduler、LogicalClock、ActiveAction、GameplayMode、RNG | §7、§23、§25、§45 | Phase 1–2 |
| `persistence/` | Snapshot / Checkpoint / Replay（事件级回放） | §30、§9 | Phase 8 |
| `plugins/` | Plugin API / Registry / Manifest（module/plugin registry） | §28、§29 | Phase 5 |
| `context/` | ContextProvider / Capability | §13 | Phase 4 |
| `modules/` | 标准游戏模块（attributes / inventory / character / knowledge / perception / relationships / space / tactical / scenario） | §40、§41 | Phase 9 |
| `dynamics/` | WorldDynamicsBackend（rule / llm / composite） | §15 | Phase 7 |
| `llm/` | Provider-neutral LLM Runtime：structured inference、InferenceProfile、router、providers | §5.5、§31 | Phase 6 |
| `prompts/` | PromptAssembler / Prompt Policies / Prompt Registry | §14 | Phase 6 |
| `content/` | Content Loader / ProjectIR / schemas / migrations | §5、§6 | Phase 5 |
| `devtools/` | 开发控制平面：validate / inspect / trace / replay / branch / scenario_test | §22、§33、§37 | Phase 8 |
| `adapters/` | 外部入口适配：cli / web / dsh | §35、§44 | Phase 8 / 10 / 11 |
| `presentation/` | 表现层：text / image / tactical 视图派生 | §8.5、§32 | Phase 10 |

Spec §44 中的 `agents/`（policies / critic / repair / narrator）本期**未建**：
任务包 P0-T05 的最小化清单未包含它，且 v1 已有冻结的 `src/agents/`（LangGraph
实现）；v2 的 BehaviorPolicy 归属在 Phase 4 按 Spec §12 再定名落位。

## 2. v2 冻结规则（骨架期起即生效）

1. **不得 import v1 模块**：`engine_v2` 内任何文件不得 import `src.graph`、
   `src.game`、`src.agents`、`src.web`、`src.llm`、`src.prompts`、
   `src.config`、`src.models`、`src.ui`（v1 模块，注意与 `engine_v2` 自有
   的 `llm/`、`prompts/` 子包区分）。
2. **不得被 v1 入口引用**：`src/main.py`、`public_start/`、`web/` 等 v1
   入口不得 import / 引用 `engine_v2`（新目录可 import，但没有替换 v1——
   G0 门禁）。
3. **LangGraph / OpenAI 依赖不得进入 `engine_v2.core`**（G1 门禁：Core
   import 不需要 LangGraph / OpenAI；Phase 1 验收要求 core tests 无网络、
   无 LLM 可完整运行）。provider SDK 仅允许未来出现在 `engine_v2/llm/`
   （Phase 6），且必须保持 provider-neutral 抽象。
4. **骨架期禁止实现具体数据结构**：Spec 的 Entity / State / Effect 等
   数据结构属于 Phase 1 任务，本目录当前不得提前实现。
5. 以上规则由 `tests/test_engine_v2_skeleton.py` 静态扫描强制。

## 3. 后续 Phase 填充索引（Spec §47 第一期开发顺序）

- **Phase 1 — Core State / Effect Kernel** → `core/`（此阶段完全不接 LLM）；
- **Phase 2 — Scheduler / Action** → `runtime/`（LogicalClock、ScheduledEvent、
  ActiveAction、ActionRegistry、ActionLifecycle、Interrupt、DecisionBoundary）；
- **Phase 3 — Actor / Context** → `context/` + Actor / BehaviorPolicy（先 RulePolicy）；
- **Phase 4 — LLM Runtime** → `llm/`、`prompts/`（InferenceProfile、
  StructuredInference、PromptAssembler、revision-aware async result）；
- **Phase 5 — Project Format / Module / Plugin / DSL** → `content/`、`modules/`、`plugins/`；
- **Phase 7 — WorldDynamics** → `dynamics/`；
- **Phase 8 — Persistence / Replay / Dev Control Plane** → `persistence/`、`devtools/`；
- **Phase 9 — Official Modules / v1 Migration** → `modules/` 各官方模块；
- **Phase 10 — Presentation / Web** → `presentation/`、`adapters/`；
- **Phase 11 — Agent-native / DSH / Hardening / Release** → `adapters/dsh/` 等。
