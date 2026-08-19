# ADR-006: Replay 与 Provenance 是核心架构能力而非事后日志

- **状态**: accepted
- **出处**: `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md` §4 (K6), §30, §49 (原则 16); `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` §0 (原则 10), §35

---

## 1. Context（背景与问题）

在传统 LLM 模拟中，调试与记录往往依赖非结构化日志（如标准输出 print 或普通的日志文件 dump）：
1. **事后日志不可执行**：日志只能给人看，无法让系统回到发生异常的前一个状态精确重放。
2. **缺乏因果出处（Provenance 缺失）**：当某个 NPC 做出反常决定或某一属性异常变动时，无法反查是哪个 Prompt 输入触发、哪个 LLM Response 建议、经过了哪个 Authority 批准、由哪条规则或级联事件派生。
3. **分支与时间旅行困难**：游戏开发中的 SL（Save/Load）大法、剧情多结局分支试错、AI 对抗策略沙盒演练都需要对运行历史进行分支与复现。

---

## 2. Decision（决策内容）

确立 **Replay 与 Provenance 为 Engine Kernel 的一等公民能力**（First-class Architectural Feature，Spec §30, §49 原则 16）：

1. **确定性 Event-level Replay（Spec §30.4）**：
   - 只要输入初始种子快照（Snapshot）和有序的已裁决 DomainEvent 序列，纯函数 Reducer 能够 100% 确定性地重建任意时刻的 `WorldState`。
2. **全链路因果追溯（Trace & Provenance，Spec §4 K6, §8.4）**：
   - 每个 DomainEvent 均携带 `cause_id`、`effect_ref`、`trigger_actor_id`；
   - 记录产生 Effect 的 Policy 决策上下文（包括 Prompt 模板指纹、LLM Token 消耗、生成时间与种子）。
3. **无缝分支能力（Branching，Spec §30.5）**：
   - 支持从历史任意 Revision 点创建分支会话（Fork Session），在不影响主时间线的前提下探索不同选择的发展。
4. **架构前置要求（Plan §35）**：
   - Replay / Trace 不作为最后完善体验的“附件”，而是在 Phase 8（紧随核心内核）即完成集成与持久化验证，成为后续所有 Gameplay 开发的调试基石。

---

## 3. Consequences（影响与后果）

### 正向收益
- **极度强大的调试能力**：遇到偶发 bug 或 NPC 决策崩坏，可直接导出一份轻量级的 Event Log 在本地无网络、无 LLM 环境下 100% 确定性复现并打断点排查。
- **天然支持撤销与多结局玩法**：为 Time-travel 机制、剧情回溯、Undo 功能提供了原生的底层支持。

### 代价与权衡
- 所有 DomainEvent 与 Reducer 必须保持严格的纯函数与确定性，严禁在 Reducer 内部引入随机数、外部时钟或外部 IO。
