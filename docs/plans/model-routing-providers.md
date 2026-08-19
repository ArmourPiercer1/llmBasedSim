# Architecture v2 — 模型路由 Provider 备忘

> 文档状态：Effective v1.0
> 关联文档：[`llmBasedSim_Architecture_v2_Refactor_Development_Plan.md`](llmBasedSim_Architecture_v2_Refactor_Development_Plan.md) §3 模型池与职责
> 数据来源：DSH 运行时配置 `~/.dsh/settings.yaml` 的 `llm-pi-ai.providers` 注册表（2026-08-20 核对）

执行计划 §3 中的模型别名必须在 workflow `agent()` 调用中**同时指定 `provider` 和 `model`**，
否则模型会落到默认 provider（`qiyuan-inter`）上并可能因该 provider 不提供该模型而失败。

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
