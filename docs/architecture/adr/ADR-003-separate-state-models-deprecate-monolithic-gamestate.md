# ADR-003: 废弃大一统 GameState，分离五大多层状态模型

- **状态**: accepted
- **出处**: `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md` §4 (K1, K7), §8, §43.2, §43.3; `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` §10 (Phase 1)

---

## 1. Context（背景与问题）

在 v1 原型中，`src/graph/game_state.py` 维护了一个大一统的 `GameState` 结构，将以下内容全部混杂在一起：
1. 世界实体与客观事实（Entity、属性、地点）；
2. 调度执行状态（当前 Tick、进行中的协程与中间变量）；
3. 后端资源句柄（LLM 客户端配置、Provider 缓存）；
4. 追溯与调用日志（中间 Token 消耗、Trace 链路）；
5. 呈现与前端视图（UI 格式化文本、当前渲染中的临时图像提示词）。

这导致：
- **存盘与快照极重**：序列化包含大量瞬态（Transient）与外部后端对象，难以稳定持久化；
- **回放污染**：无法区分“世界历史”与“UI展示过程”；
- **并发与版本混淆**：无法针对客观事实进行精确的 Revision 版本管理。

---

## 2. Decision（决策内容）

彻底废弃大一统 `GameState`，在 Architecture v2 中建立**清晰分层的五大状态模型**（Spec §8）：

```text
┌─────────────────────────────────────────────────────────────┐
│ 1. WorldState (客观世界状态: Entity, Component, Space, Clock)  │
├─────────────────────────────────────────────────────────────┤
│ 2. RuntimeState (引擎运行时: Scheduler, ActiveActions, Queue) │
├─────────────────────────────────────────────────────────────┤
│ 3. BackendState (后端基础设施: LLM Pools, Spatial Index, DB) │
├─────────────────────────────────────────────────────────────┤
│ 4. TraceState (全链路追踪: Events, Causality, Telemetry)     │
├─────────────────────────────────────────────────────────────┤
│ 5. ViewState (表现与呈现: Client Views, Narrative, UI Cache) │
└─────────────────────────────────────────────────────────────┘
```

1. **WorldState（权威世界状态，Spec §8.1）**：
   - 唯一的 Authoritative Truth（K1）。纯数据、不可变、严格可序列化、具备单调递增的 Revision ID（Spec §9）。
2. **RuntimeState（引擎运行态，Spec §8.2）**：
   - 管理 EventQueue、ActiveAction 列表、待处理 Proposal。可检查、可持久化并支持从中断点恢复。
3. **BackendState（基础设施状态，Spec §8.3）**：
   - 包含 LLM API 连接、向量库缓存、外部图片生成队列等，不进入 WorldState 快照。
4. **TraceState（审计与因果追踪，Spec §8.4）**：
   - 记录 DomainEvent 历史树、Effect 提议与仲裁原因、LLM 输入输出元数据（Provenance）。
5. **ViewState（表现与视图状态，Spec §8.5）**：
   - 纯只读投影，服务于 Web/CLI 前端，包含感知过滤后的局部视角（Fog of War / Epistemic Boundary）。

---

## 3. Consequences（影响与后果）

### 正向收益
- **快照与回放极轻极快**：存盘仅需固化 `WorldState` 与关键 `RuntimeState`。
- **职责清晰**：表现层渲染延迟或大模型 API 故障绝不导致世界状态数据损坏。
- **支持版本分支**：基于轻量不可变的 `WorldState` + Revision 树，天然支持 Branch、Time-travel 与分支探索。

### 代价与权衡
- 跨层访问必须通过明确契约（如 ViewState 必须从 WorldState 经过 Context Provider 投影派生），严禁模块跨层直接读取底层私有字段。
