# Architecture v2 迁移硬约束（Migration Constraints）

本文档汇总 llmBasedSim Architecture v2 重构与迁移过程中的所有硬性约束、执行纪律、单 Owner 契约边界及必须人工介入的 HARD STOP 场景。
所有参与开发的 Subagent 与人工开发者必须严格遵守。

---

## 1. Plan §0 十大执行原则

1. **禁止在旧架构上打补丁**：不在旧 `game_graph.py` 上继续叠加核心架构。
2. **保留 v1 为参考基准**：保留当前 v1 作为行为参考与迁移源（Golden Master）。
3. **数据契约先行**：先稳定数据 Contract（Core Data Contracts），再并行开发 Runtime。
4. **内核独立纯粹性**：Kernel 必须在无 LLM、无网络、无 GUI 环境下独立单测验证。
5. **严禁直接状态写入**：所有 authoritative state 变化必须严格流经管道：
   `ProposedEffect → Authority → Validation → Conflict Resolution → Transaction → Reducer`。
6. **任务包高内聚与可验收**：所有 Agent 工作包必须具有明确输入、输出、禁止改动范围和自动验收测试。
7. **门禁依赖阻断**：Phase Gate（G0–G11）未通过时不得继续进入后续依赖 Phase。
8. **严禁自行决议架构**：架构歧义不得由 Subagent 自行“顺手决定”。
9. **开发与运行解耦**：Coding Agent 是开发客户端，不是 Runtime 依赖。
10. **平台职责清晰**：DSH / 其他 Agent Host 负责代码写入、任务编排、Git、人工审批；llmBasedSim 负责游戏语义、验证、测试、运行、trace、replay。

---

## 2. Plan §7 单 Owner Contract 清单（不得无协调并行）

为防止并发开发引发语义撕裂与契约不兼容，以下核心概念与公共契约在同一 Phase 内**必须由单 Owner 串行修改与维护**，禁止未经协调的多 Agent 同时并行编辑：

1. **Core ID / Revision**（核心标识符与版本推进模型）
2. **WorldState / RuntimeState**（核心世界状态与运行态定义）
3. **ProposedEffect**（效应提议标准契约）
4. **AuthorityPolicy**（权威管辖与仲裁策略）
5. **Transaction / Reducer**（事务提交与不可变状态归约器）
6. **DomainEvent**（领域事件与因果元数据契约）
7. **Scheduler**（事件驱动与动态时间调度器）
8. **ProjectIR schema**（项目中间表示标准规范）

---

## 3. Plan §24 HARD STOP（S1–S12）必须人工介入场景摘要表

当遇到以下 12 类场景时，Subagent / Leader Agent 必须**立即中断开发并请求人工介入**，严禁擅自绕过：

| 编号 | 场景名称 | 触发条件 / 典型表现 | 强制动作 |
|---|---|---|---|
| **S1** | 变更 Kernel 不变量 | 提出直接写状态、Reducer 调 LLM、合并 Session/World、Prompt 提升权限、强制 Pin 模型等 | 停机，请求人工确认架构原则 |
| **S2** | Public Contract 存在分歧 | 核心 Contract（Effect/Authority/Transaction/Event/Scheduler/ProjectIR/Space 等）出现两种合理但不兼容设计 | 停机，请求人工裁决标准契约 |
| **S3** | 破坏性迁移（Destructive Migration） | 为通过测试而删除旧存档字段、静默丢弃数据、擅自变更 v1 语义或无法向下兼容 | 停机，请求人工决定兼容策略 |
| **S4** | 引入重大依赖或 License 风险 | 引入 GPL/AGPL/MPL 等风险代码，或试图引入大型重型外部引擎/数据库/Node栈 | 停机，仅可提建议，不得合入 Core |
| **S5** | Backend 无法满足持久化/回放契约 | 某数值动力学/空间 Backend 无法 snapshot/restore 或导致分支探索失真 | 停机，人工决定降级、更换或调整契约 |
| **S6** | 经能力升级仍连续失败 | 经过 R0（局部修复）、R1/R2（升级模型/上下文）、R3（独立诊断）后仍无稳定 root cause | 停机，防止无限消耗 Token |
| **S7** | 虚假通过测试（语义违背） | 用 Mock 绕过真正 Authority、Replay 仅重新加载快照、Multi-space 伪实现、Reducer 藏 LLM 等 | 停机，严惩并纠正作弊实现 |
| **S8** | 基线与架构目标冲突 | 发现 v1 baseline 本身存在与 Architecture 冲突的 bug，但不确定兼容意图 | 停机，请示是否继承或修正 bug |
| **S9** | 异步并发状态损坏 | 出现 Revision 倒退、重复提交、事件丢失、Stale effect 偶发写入、分支污染等 | 停机，停止新特性开发，转专项排查 |
| **S10** | 性能瓶颈需要架构级 Tradeoff | 序列化调度器、Trace 体积、事件溯源等对性能产生不可接受的负担，需牺牲语义 | 停机，由人工权衡架构取舍 |
| **S11** | 多模态主观验收无法判定 | 无法可靠判定画面连贯性、UI 可读性或图像与状态冲突 | 停机，转人工主观评审 |
| **S12** | 试图超出工作包边界重构 | Subagent 声称“为了完成本任务需要顺便重写另外三个核心模块” | 停机，退回 Leader 重新拆解工作包 |

---

## 4. Spec §43 v1 → v2 保留 / 移除 / 重写清单

### 4.1 强烈保留的思想（Spec §43.1）
- Pydantic boundary validation
- YAML/project-file authoring
- condition/rule DSL
- locked/derived attribute 思想
- Jinja2 template layer
- structured LLM parsing
- player subconscious policy
- NPC personality/motivation/relationship data
- perception / knowledge separation 思想
- narrative renderer
- CLI/Web adapter separation

### 4.2 应移除的核心假设（Spec §43.2）
- ❌ LangGraph 固定全局 tick pipeline
- ❌ all NPC decide every turn（所有 NPC 逐轮强行决策）
- ❌ universal tick（全局齐步走时间）
- ❌ fixed six action types（固定 6 种动作字面量）
- ❌ LLM physics directly owns physics（LLM 物理裁决直接写状态）
- ❌ global event text copied to NPC memory（全局事件文本粗暴复制至记忆）
- ❌ global GameState 包含全部 runtime/transient/presentation
- ❌ Web singleton session（单例 Web 会话）
- ❌ one model config for all roles（全角色单一模型配置）

### 4.3 必须重写（Spec §43.3）
- `game_graph.py` → 替换为 Event-driven Scheduler 与 Action Lifecycle
- `GameState` → 替换为 WorldState/RuntimeState/BackendState/TraceState/ViewState
- `state_apply.py` → 替换为 ProposedEffect + Authority + Transaction + Reducer
- `physics_resolve` → 替换为 WorldDynamicsBackend 与 AuthorityPolicy
- `characters_all_decide` → 替换为基于时间到期与事件触发的 BehaviorPolicy
- `tick_speed_resolve` → 替换为 Dynamic Time Slicing & ActiveAction
- `perception pipeline` → 替换为 ContextProvider 与 Epistemic Boundary
- `model config` → 替换为 Inference Capability + DeploymentProfile
- `web session lifecycle` → 替换为 SessionManager + 多 Instance 会话隔离

---

## 5. Plan §35 执行优先级结论

在资源与开发力量分配上，严禁平均用力，必须严格遵循以下阶段演进序列：

```text
【最高优先级（必须先于任何外围功能完成）】
P0 (冻结基线) → P1 (Core Contracts) → P2 (Kernel 管道) → P3 (Scheduler/Time) → P4 (Actor/Space) → P8 (Persistence/Replay)

【关键聚焦】：
1. Effect / Authority / Transaction
2. Scheduler
3. Replay / Trace
（以上三组为最不可“后补”的架构支柱）

【第二优先级（格式与推理基础设施）】
P5 (Project Format) → P6 (LLM Runtime / Capability Routing) → P7 (WorldDynamics)

【第三优先级（业务与呈现扩展）】
P9 (Standard Modules / v1 Migration) → P10 (Presentation / Web) → P11 (Hardening / Release)
```

**核心铁律**：
> **先做一个无 LLM 但状态、时间、因果、权限、回放都正确的游戏内核，再把 LLM 挂上去。**
