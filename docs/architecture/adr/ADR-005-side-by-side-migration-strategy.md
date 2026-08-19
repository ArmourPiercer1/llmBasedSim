# ADR-005: 旁路迁移策略（冻结 v1 → 并行 Kernel → Vertical Slice → 替换）

- **状态**: accepted
- **出处**: `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` §1, §35; `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md` §43

---

## 1. Context（背景与问题）

从 v1 原型重构至 v2 是一次代际演进，涉及内核状态模型、调度器、效应管道和决策策略的全面升级。
如果采取“大爆炸式就地修改”（Big-bang in-place refactor）：
1. 现有 v1 的端到端可运行功能会迅速被破坏，导致中途失去参照物与验收基准；
2. 长开发周期内无法验证新内核是否能完整支撑复杂业务流程；
3. 多 Subagent 并行开发时极易造成代码库剧烈冲突。

---

## 2. Decision（决策内容）

实施 **Side-by-side（旁路并行）演化迁移策略**（Plan §1 与 §35）：

```text
v1 frozen runtime (基准冻结，作为 behavior golden master 与 characterization 参照)
      │
      │ 提取可复用属性公式、规则条件 DSL、提示词模板
      ▼
Architecture v2 side-by-side kernel (独立无依赖开发：P0 → P1 → P2 → P3 → P4 → P8)
      │
      ├── migrate reusable rules / attributes / loaders
      ├── migrate LLM adapter / prompts
      ├── migrate content
      └── build compatibility layer
      ▼
v2 vertical slice (Galgame / Sandbox / Tactical 三类参考场景切片验证)
      │
      ▼
v2 becomes default runtime (通过 Phase Gate 验收后切换为主运行环境)
      │
      ▼
remove / archive v1 orchestration (清理 / 归档旧 game_graph.py 及历史无用代码)
```

1. **Phase 0 冻结 v1**：固化现有测试集与运行特征，建立 Characterization Baseline。
2. **核心构建次序（Plan §35 优先级）**：
   - **最高优先级**：`P0 → P1 (Contracts) → P2 (Effect/Authority/Transaction) → P3 (Scheduler/Time) → P4 (Actor/Space) → P8 (Replay/Trace)`。
   - **内核独立验证原则**：先做一个无 LLM 但状态、时间、因果、权限、回放都正确的游戏内核，再把 LLM 与外部系统挂载上去。
3. **分阶段 Vertical Slice 验收（Phase 9）**：
   - 分别针对 Galgame（叙事/好感）、Sandbox（多地点/物品流动/偷窃）、Tactical（战斗/空间移动）进行垂直切片回归，满足标准后再废弃 v1。

---

## 3. Consequences（影响与后果）

### 正向收益
- **低风险、高确定性**：随时拥有可运行的对照基准，保证重构过程中行为不失真。
- **高并发安全性**：新旧代码物理隔离，Subagent 可以在全新的 `src/engine/` 命名空间内快速搭建新模块而不会污染现有代码。

### 代价与权衡
- 短期内代码库中会并存 v1 与 v2 两个体系的代码，增加了暂时的代码体积。
- 最终切换时需要执行一次显式的 v1 废弃清理（Phase 11）。
