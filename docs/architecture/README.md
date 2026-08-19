# llmBasedSim Architecture v2 文档总览与导航

## 1. 权威规范说明（Source of Truth）

本目录（`docs/architecture/`）是 **llmBasedSim Architecture v2** 的架构导航、架构决策记录（ADR）与迁移约束派生视图。

本项目的权威设计与计划规范（Source of Truth）位于：
1. **[llmBasedSim Engine Architecture v2 设计规范](../plans/llmBasedSim_Engine_Architecture_v2_Spec.md)**：架构完整设计、核心不变量、数据契约、状态模型、调度与动力学模型（共 50 个章节）。
2. **[llmBasedSim Architecture v2 完整代码开发 / 重构计划](../plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md)**：分阶段工程路线图、任务包标准、门禁准则、测试验收与中断规则（共 37 个章节）。
3. **[模型路由 Provider 备忘](../plans/model-routing-providers.md)**：开发期与运行期各能力梯度的模型候选与 Provider 路由记录。

任何架构实现与开发任务必须以 `docs/plans/` 中的源文档为最终裁决依据。

---

## 2. 目录结构

```text
docs/architecture/
├── README.md                  # 本文件：v2 架构文档导航与阅读路径
├── migration-constraints.md   # 迁移硬约束（执行原则、单 Owner 清单、HARD STOP、重写清单等）
└── adr/                       # 架构决策记录（Architecture Decision Records）
    ├── ADR-000-index.md       # ADR 汇总索引表
    ├── ADR-001-authority-mediated-commit-pipeline.md
    ├── ADR-002-kernel-uncoupled-from-langgraph-agent-as-policy.md
    ├── ADR-003-separate-state-models-deprecate-monolithic-gamestate.md
    ├── ADR-004-capability-declaration-and-user-selected-models.md
    ├── ADR-005-side-by-side-migration-strategy.md
    └── ADR-006-replay-and-provenance-as-architectural-capabilities.md
```

---

## 3. 建议阅读路径

根据不同的角色与工作场景，推荐以下阅读顺序：

### 路径 A：新协作者 / 人工开发者路径（全局认知与领域理解）
1. **[README.md](./README.md)**（本文）：建立全局导航与 Source of Truth 认知。
2. **[ADR 索引与决策记录](./adr/ADR-000-index.md)**：快速了解 v2 相较于 v1 的 6 项核心架构代际决策与取舍。
3. **[迁移硬约束汇总](./migration-constraints.md)**：明确开发红线、不可并发的单 Owner 模块与必须人工介入的 HARD STOP 场景。
4. **[Engine Architecture v2 设计规范](../plans/llmBasedSim_Engine_Architecture_v2_Spec.md)**：
   - §0–§4：产品定位、总体架构、三个平面与 8 大 Kernel 强制不变量（K1–K8）；
   - §8–§21：状态模型、Action/Actor、动力学、Effect/Authority/Transaction 管道与事件级联；
   - §23–§30：调度时间模型、空间后端、持久化与回放；
   - §49：18 条核心设计原则汇总。
5. **[开发与重构计划](../plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md)**：了解 Phase 0 至 Phase 11 的路线图与交付标准。

### 路径 B：Coding Agent / Subagent 执行路径（任务上下文与契约约束）
1. **[迁移硬约束汇总](./migration-constraints.md)**：必须首先加载并遵守 Plan §0 十大执行原则、§7 单 Owner Contract、§24 S1–S12 HARD STOP 触发条件。
2. **[ADR 决策集合](./adr/ADR-000-index.md)**：对齐目标子系统对应的 ADR（如修改状态流转必须遵守 ADR-001/003，涉及模型调用必须遵守 ADR-004）。
3. **任务包（Task Package）指定的 Spec / Plan 章节**：
   - 严格阅读任务包中关联的权威章节；
   - 禁止凭空发明规范外的架构决策；
   - 严格按照 Phase Gate（§9–§21）与验收标准（§22）执行无 LLM 独立单元测试。
