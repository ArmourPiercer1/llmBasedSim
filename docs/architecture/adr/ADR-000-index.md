# 架构决策记录索引（ADR Index）

本文档汇总 llmBasedSim Architecture v2 的核心架构决策记录（Architecture Decision Records）。
所有 ADR 均为规范（Spec）与重构开发计划（Plan）中已定稿并接受的决策（Status: **accepted**）。

| ADR 编号 | 标题 | 状态 | 规范出处章节 |
|---|---|---|---|
| [ADR-001](./ADR-001-authority-mediated-commit-pipeline.md) | Authority-mediated Commit 管道机制 | accepted | Spec §1.1, Spec §4 (K2), Spec §16–§20, Plan §0 (原则 5) |
| [ADR-002](./ADR-002-kernel-uncoupled-from-langgraph-agent-as-policy.md) | Kernel 解耦 LangGraph、Agent 是 Policy 而非 Engine | accepted | Spec §4 (K5), Spec §12, Spec §43.2, Plan §0 (原则 1, 9) |
| [ADR-003](./ADR-003-separate-state-models-deprecate-monolithic-gamestate.md) | 废弃大一统 GameState，分离五大多层状态模型 | accepted | Spec §4 (K1, K7), Spec §8, Spec §43.2, Spec §43.3 |
| [ADR-004](./ADR-004-capability-declaration-and-user-selected-models.md) | 游戏声明能力、用户选择模型，禁止 Provider/Model Pin | accepted | Spec §4 (K8), Spec §5.4–§5.5, Spec §49 (原则 11), Plan §3–§4 |
| [ADR-005](./ADR-005-side-by-side-migration-strategy.md) | 旁路迁移策略（冻结 v1 → 并行 Kernel → Vertical Slice → 替换） | accepted | Plan §1, Plan §35, Spec §43 |
| [ADR-006](./ADR-006-replay-and-provenance-as-architectural-capabilities.md) | Replay 与 Provenance 是核心架构能力而非事后日志 | accepted | Spec §4 (K6), Spec §30, Spec §49 (原则 16), Plan §0 (原则 10), Plan §35 |
