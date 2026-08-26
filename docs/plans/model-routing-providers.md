# Architecture v2 — 模型路由 Provider 备忘

> 文档状态：Effective v2.0（2026-08-20 人工指令：路由覆盖生效中）
> 关联文档：[`llmBasedSim_Architecture_v2_Refactor_Development_Plan.md`](llmBasedSim_Architecture_v2_Refactor_Development_Plan.md) §3 模型池与职责
> 数据来源：DSH 运行时配置 `~/.dsh/settings.yaml` 的 `llm-pi-ai.providers` 注册表（2026-08-20 核对）

执行计划 §3 中的模型别名必须在 workflow `agent()` 调用中**同时指定 `provider` 和 `model`**，
否则模型会落到默认 provider（`qiyuan-inter`）上并可能因该 provider 不提供该模型而失败。

## 路由覆盖（2026-08-20 人工指令，当前生效）

因 API 问题，原 §3 模型池路由整体覆盖为以下规则（优先级高于本文件其余部分与执行计划 §3/§4/§5）：

1. **统一执行路由**：所有任务（开发、测试、集成、审查、验收）**一律使用 `qiyuan-self` / `qwen3.8-27b`**。
2. **开发任务重试上限**：允许重试两次，即同一任务包最多执行三次；三次均失败则按阻塞上报人工。
3. **审查与验收协议（对抗式独立审查）**：
   - 拉起**原计划数量两倍**的审查子代理（如原计划 2 名 → 实际 4 名），各自独立执行审查；
   - 每个审查者只能给出四选一裁决：
     - **通过 (PASS)**：有充分证据支持当前开发已实现门禁要求，且构成后续开发的可靠基础；
     - **投机通过 (SPECULATIVE_PASS)**：实际内容可通过门禁，但无法充分排除后续风险；现有证据支持风险可控。**该门禁及其风险点必须记录在案**（写入 Gate Report 的风险登记节），供后续 bug 排查参考；
     - **补充内容 (SUPPLEMENT)**：内容不足以通过门禁或后续有较明显风险，但可通过简单补充改善到投机通过/通过。审查者须给出**具体补充要求**，并说明其与既有计划的兼容性；
     - **阻塞 (BLOCK)**：前面开发有明显问题或重大风险项，应停止继续开发。
   - **通过标准**：所有审查者均给出 通过/投机通过 → 进入下一阶段；
     若出现任一 补充内容 → 执行补充后**重新拉起完整审查**，且新一轮审查**不得获知上一轮审查内容**（保持独立性）；
     若经两轮补充后仍无法全部 通过/投机通过 → 状态转为**阻塞**，等待人工介入。

## 已确认的路由映射

| 别名 | 计划中名称 | provider | 实际 model ID | 上下文窗口 | 备注 |
|---|---|---|---|---|---|
| `Q27` | qwen3.8-27b | **qiyuan-self** | `qwen3.8-27b` | 262K | 与计划"256K"档位吻合；**不在 qiyuan-inter 上** |
| `GFlash` | gemini-3.7-flash | **qiyuan-inter** | `gemini-3.7-flash` | 1M | 另有 `-nothinking` / `-thinking` 变体可选，默认用基础版 |
| `QMax` | qwen3.8-max | **qiyuan-inter** | `qwen3.8-max` | 1M | 与 DSH agent-default-model 相同 |
| `GLM` | glm-5.3 | **qiyuan-inter** | `glm-5.3` | 1M | aidns 上的 `glm-5.2` 是不同模型，不可替代 |
| `Opus` | opus-4.6 | **qiyuan-inter** | `claude-opus-4-6` | 1M | 实际 ID 与计划写法不同，注意拼写 |
| `Mimo` | mimo-v2.5 | **opencode-go** | `mimo-v2.5` | 1M | 唯一多模态路由 |
| `DSV4` | deepseek-v4-flash | **qiyuan-inter** | `deepseek-v4-flash-0731` | 1M | 人工选定（2026-08-20）；注意实际 ID 带 `-0731` 后缀 |

## DSV4 候选 provider（已于 2026-08-20 人工选定：选项 A）

| 选项 | provider | model ID | 上下文 | 最大输出 |
|---|---|---|---|---|
| **A（选定）** | qiyuan-inter | `deepseek-v4-flash-0731` | 1M | 128K |
| B | aidns | `deepseek-v4-flash` | 1M | 384K |
| C | opencode-go | `deepseek-v4-flash` | 1M | 384K |

## 事故记录

- **P0-T02 首次执行失败（2026-08-20）**：workflow 仅传 `model: "qwen3.8-27b"` 未传 provider，
  落到默认 provider `qiyuan-inter` 上，而该模型实际由 `qiyuan-self` 提供，子代理启动失败返回 null。
  经人工裁定：**该次失败属于路由配置错误，不计入计划 §5 的失败重试次数（R0）**。
  纠正措施：所有 `agent()` 调用必须显式携带 provider；本文件作为路由权威备忘。

## 注册表快照（核对时点全部 provider）

- **qiyuan-inter**（`https://svip.xty.app/v1`）：deepseek-v4-flash-0731、gemini-3.7-flash(-nothinking/-thinking)、glm-5.3、qwen3.8-max、claude-opus-4-6、hy3-preview、kimi-k2.7-code、minimax-m3、qwen3.6-plus、qwen3.7-max、qwen3.7-plus
- **aidns**（`https://ctmoai.com/v1`）：deepseek-v4-flash、deepseek-v4-pro、glm-5.2、kimi-k3
- **qiyuan-self**（`http://58.57.119.30:52010/v1`）：qwen3.8-27b、qwen3.6-27b、qwen3.6-35b-a3b、qwen3-embedding-0.6b
- **opencode-go**：deepseek-v4-flash、hy3、kimi-k3、mimo-v2.5、grok-4.5

> 若 `~/.dsh/settings.yaml` 注册表变更，本文件需重新核对。
