# ADR-002: Kernel 解耦 LangGraph、Agent 是 Policy 而非 Engine

- **状态**: accepted
- **出处**: `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md` §4 (K5), §12, §43.2; `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` §0 (原则 1, 9)

---

## 1. Context（背景与问题）

v1 原型依托 LangGraph 的 `game_graph.py` 构建主循环，存在核心结构性缺陷：
1. **执行流绑定框架**：图驱动框架硬编码了单 Turn “所有 NPC 齐步走决策”（`characters_all_decide`）、同步物理结算与全局 Tick 循环，无法支持连续时间跨度（如 30 分钟移动被 12 分钟事件打断）。
2. **Actor 与 Agent 概念混淆**：游戏实体（Actor）与决策算法（Agent）强绑定，导致无法灵活切换行为策略（如玩家接管、脚本 NPC、简易规则 NPC、大模型决策 NPC）。
3. **框架黑盒与测试困难**：LangGraph 内部状态与图调度对调试、确定性单步测试和快照回放造成额外阻碍。

---

## 2. Decision（决策内容）

1. **Kernel 核心脱离 LangGraph（Spec §43.2, Plan §0 原则 1）**：
   - 移除 `game_graph.py` 与 LangGraph 全局 Tick pipeline；
   - 引擎内核采用自主可控、显式可序列化的 Event-driven Scheduler 与 Action Lifecycle（Spec §23）。
2. **Agent 是 Policy，不是 Engine（Spec §4 K5, §12）**：
   - **Actor（行动实体）**：拥有世界状态、空间位置与属性的实体（Entity）；
   - **BehaviorPolicy（行为策略）**：计算 ActionProposal 的决策算法。Policy 可以是：
     - `LLMPolicy`（基于大模型推理）；
     - `ScriptPolicy` / `RulePolicy`（确定性规则或状态机）；
     - `PlayerInputPolicy`（人类交互输入）；
     - `HybridPolicy`（规则过滤 + LLM 意图生成）。
3. **Coding Agent 不是运行期依赖（Plan §0 原则 9-10）**：
   - 编码助手（如 DSH、Cursor 等）是开发期客户端，负责代码生成与编排；游戏引擎本身（llmBasedSim）运行不依赖宿主环境的私有通信通道。

---

## 3. Consequences（影响与后果）

### 正向收益
- **高度解耦与可插拔**：实体可以在运行期自由切换决策 Policy（例如战斗切规则 AI、叙事切 LLM、玩家随时接管）。
- **支持非齐步调度**：调度器支持基于时间推进与事件触发的动态调度（ActiveAction），不再强制全员逐轮决策。
- **轻量与高内聚**：内核纯粹基于 Python 核心对象与 Pydantic 契约，极低框架依赖。

### 代价与权衡
- 需要完全重新实现时间调度器与 Policy 运行时驱动（Phase 3 与 Phase 4）。
- v1 中的基于图编排的节点逻辑需重构为标准 ActionProposal 产生器。
