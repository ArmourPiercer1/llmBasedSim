# ADR-004: 游戏声明能力、用户选择模型，禁止 Provider/Model Pin

- **状态**: accepted
- **出处**: `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md` §4 (K8), §5.4–§5.5, §49 (原则 11); `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` §3–§4, §15 (Phase 6)

---

## 1. Context（背景与问题）

在 v1 原型与常见 LLM 应用中，往往存在硬编码模型提供商（如在代码中直接锁定 `gpt-4o` 或 `claude-3-5-sonnet`）的问题：
1. **环境不可移植**：当用户本地部署（如 Ollama / vLLM）、使用特定企业网关或处于离线单机环境时，硬编码直接导致工程崩溃。
2. **职责倒置**：游戏作者应该关注“此 NPC 需要复杂的心理反思能力还是仅需简短对话”，而非决定终端玩家必须调用哪家 API。
3. **模型演进脆弱**：外部大模型频繁换代，硬编码 Model ID 会迅速沦为遗留技术债。

---

## 2. Decision（决策内容）

Architecture v2 确立 **Kernel 强制不变量 K8**（Deployment 与 Game Project 分离）与原则 11（Game declares capability; user chooses model）：

1. **游戏项目（GameProject）仅声明 Capability（Spec §5.5）**：
   - 游戏只在配置或代码中声明所需的抽象推理能力标签，例如：
     - `narrative_creative`（叙事创造力）；
     - `logic_planner`（复杂逻辑规划/反思）；
     - `fast_dialogue`（快速低延迟对话）；
     - `vision_understanding`（图像感知）；
     - `structured_parser`（严格 JSON/DSL 提取）。
2. **用户/运行环境提供 DeploymentProfile（Spec §5.4）**：
   - 由部署环境（`deployment.yaml` 或环境变量）将抽象 Capability 映射到具体的 Provider（如 DeepSeek, OpenAI, Anthropic, Qwen, Ollama）及具体 Model ID。
3. **禁止代码与游戏工程内 Model Pinning（Plan §15 Phase 6 强制约束）**：
   - 核心代码和发布的游戏剧本中严禁硬编码 Provider 名称与 Model 字符串；
   - 缺省情况下提供基于 Fallback 梯度的默认 Capability 映射表（`model-routing-providers.md`）。

---

## 3. Consequences（影响与后果）

### 正向收益
- **完全解耦与可移植**：同一款游戏剧本可以在全本地纯离线小模型（如 Qwen-2.5-7B/14B）或顶配云端 API（如 Claude-3.7/DeepSeek-V4）下无缝切换运行。
- **成本与性能自适应优化**：高频低智商 NPC 自动路由至极低成本快速模型，关键剧情转折路由至高智商模型。
- **优雅降级**：API 额度耗尽或超时错误时，Capability Router 可在同能力池内自动执行 Fallback 重试。

### 代价与权衡
- 需要实现基于 Capability Registry 与 DeploymentProfile 的解析与路由分发层（Phase 6）。
- 测试用例中必须使用 Mock / Fake LLM Provider，不可依赖外部真实 API 的私有返回值格式。
