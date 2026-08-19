# ADR-001: Authority-mediated Commit 管道机制

- **状态**: accepted
- **出处**: `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md` §1.1, §4 (K2/K3), §16–§20; `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` §0 (原则 5)

---

## 1. Context（背景与问题）

在 v1 原型中，状态变更由 LLM 解析后直接应用或通过分散的逻辑写入（如 `state_apply.py` 直接修改全局状态字典），导致以下问题：
1. **幻觉与越权写入**：LLM 自由生成的状态字段可能破坏游戏核心规则（例如直接瞬移或修改只读属性）。
2. **多 Agent 竞态与冲突**：多个 NPC 或规则同时发起状态修改时缺乏统一裁决、原子事务与回滚机制。
3. **不可追溯**：无法精确区分状态变更来自于哪个 Agent 提议、哪条权威规则裁决、哪个事务提交。

---

## 2. Decision（决策内容）

Architecture v2 确立 **Kernel 强制不变量 K2 与 K3**：严禁对 Authoritative State 进行直接状态写入（No Raw Mutation）。
所有状态变更必须严格流经标准管道：

```text
ProposedEffect → Authority → Validation → Conflict Resolution → Transaction → Reducer
```

1. **ProposedEffect（提议效果，Spec §16）**：
   - 包含 LLM、规则脚本、数值动力学系统在内的一切组件均只是“Effect Producer”，只能生成 ProposedEffect（意图/提议），无权直接修改世界。
2. **Authority（权威策略，Spec §17）**：
   - 每类 Effect 必须路由至明确声明的 AuthorityPolicy（如 World/Physics/Inventory/Combat/Narrative Authority）进行管辖权认定。
3. **Validation（合法性校验，Spec §18）**：
   - 校验前置条件、实体存在性、版本一致性、资源余量等，非法提议被显式拒绝并记录原因。
4. **Conflict Resolution（冲突解决，Spec §19）**：
   - 当多个 Producer 产生互斥或竞争的 Effect 时，按明确策略（优先级/抢占/合并/时间序）统一裁决。
5. **Transaction & Reducer（事务与归约，Spec §20）**：
   - 通过校验与仲裁的 Effect 打包为原子 Transaction；
   - 纯函数 Reducer 计算产生新的不可变 WorldState，并派发 DomainEvent。

---

## 3. Consequences（影响与后果）

### 正向收益
- **世界规则确定性保障**：LLM 即使产生幻觉也无法绕过 Authority 破坏核心状态。
- **并发与时间可中断性**：状态变更具备原子性与因果一致性，支持时间片中断与回退。
- **高可测试性**：Kernel 核心可以在无 LLM、无网络、无外部环境的单测中完全验证裁决与归约。

### 代价与权衡
- 开发各类 Gameplay 机制时必须严格定义 ActionProposal、ProposedEffect 与 Authority 逻辑，增加了初始契约代码编写量。
- 状态应用不再是单行 `state.xxx = yyy`，而是需要通过 Effect 提交。
