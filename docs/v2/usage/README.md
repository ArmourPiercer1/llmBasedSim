# v2 引擎使用文档组

> 本目录是 **`src/engine_v2`（Architecture v2 引擎）** 的使用面文档：
> 引擎概念模型、如何运行、如何编写游戏项目（v2 项目格式，取代 v1 的
> init 文件）、开发控制平面（devtools）与扩展点。
>
> 设计权威不在本目录——本目录是**使用面导航**。设计与决策的权威源：
>
> | 层 | 位置 |
> |---|---|
> | 总 Spec（架构规范） | `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md` |
> | 执行计划（Phase / 任务包 / 门禁） | `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` |
> | 各 Phase 设计 SOT（冻结态） | `docs/v2/contracts/P1…P10-*.md`（每个含 §9 勘误链） |
> | 门禁报告（每 Phase 收口证据） | `docs/v2/gates/G0…G10-*.md` |
> | 任务交付报告 | `docs/v2/reports/` |
> | v1 参照语料（迁移对照） | `docs/v2/reference/` |

## 当前状态（截至 G10 收口）

- 分支 `architecture-v2`；全量测试 **3205 passed / 0 failed**
  （恒等式 3142 G9 基线 + 63 P10 增量）。
- Phase 1–10 全部实现并过门禁（G0–G10 机械面 PASS；G10 人工面
  S11 待用户判定，见 `docs/v2/gates/G10-test-acceptance-plan.md`）。
- **已实现且可运行**：Core State/Effect Kernel、Scheduler/Action、
  Actor/Context/Space、LLM Runtime（provider-neutral 抽象，零真实
  LLM 接入）、Project Format / Modules / Plugins、WorldDynamics、
  Persistence / Replay / Dev Control Plane、9 个官方游戏模块、
  Presentation / Web（静态页面 + 会话 API + 确定性图像 backend）。
- **未建（P11+ 承接面）**：CLI 适配器（`adapters/cli/`）、
  DSH 适配器（`adapters/dsh/`）、真实 LLM/图像 backend 的
  开箱即玩装配、inspector / workbench 页面路由（当前 404 保留面）。
- v1 引擎（`src/main.py` / `src/web/`，LangGraph 实现）**冻结保留**
  于本仓库，可继续运行；v2 不 import v1，v1 不 import v2。

## 文件索引

| 文档 | 内容 | 读者 |
|---|---|---|
| [quickstart.md](quickstart.md) | 环境准备、跑起来（Web 演示 + 验收流程 + 测试套件）、WebUI 操作 | 第一次接触 v2 的人 |
| [project-authoring.md](project-authoring.md) | **v2 项目格式**：game.yaml / world/ / characters/ / items/ / actions/ / rules / gameplay_modes / deployment；`llmsim validate`；v1 init 文件 ↔ v2 项目映射 | 要写一个 v2 游戏的人 |
| [devtools-and-extensions.md](devtools-and-extensions.md) | `llmsim-devcontrol`（inspect/trace/replay/branch/test）、存档布局、持久化/回放/分支、扩展点（模块 / 插件 / LLM / dynamics）、设计文档导航 | 要调试、回放、扩展 v2 的开发者 |

## 引擎 60 秒概念模型

v2 把「游戏」拆成**三个平面**（Spec §3）：

```text
Authoring Plane        Development Control Plane      Runtime Plane
（作者面：项目文件）     （开发面：校验/检视/回放）       （运行面：实例/会话）
project/*.yaml  ──load_project──▶  ProjectIR          ──build_world──▶  WorldInstance
       │                (校验 validate)                (装配 WorldState)      │
       └── deployment.yaml（LLM/部署，用户侧）                          Session（一次游玩）
                                                                      tick → Action →
                                                                      Effect → Commit → Revision+1
```

核心不变量（Spec 第 2 节 K1–K8，全部由测试强制）：

| 不变量 | 一句话 |
|---|---|
| **K1** 单一 authoritative state | 世界状态只有一份权威，任何视图（叙事/图像/UI）都是它的派生 |
| **K2** 禁止直接状态写入 | 状态只能经 Action → Effect → **Commit**（Transaction/Reducer）变更 |
| **K3** Authority 与 Commit 分离 | 谁有权提 Effect（authority policy）与谁来应用（reducer）是两层 |
| **K4** Prompt 不能定义世界权限 | LLM 是提议者，不是裁决者；权限来自项目声明与 authority policy |
| **K5** Agent 是 Policy，不是 Engine | 调度/时钟/提交全在确定性引擎里；LLM 以 BehaviorPolicy 身份被调用 |
| **K6** Event 必须可追踪来源 | 每个 DomainEvent 带 cause/result，trace 记录流完整（可回放） |
| **K7** 调度状态必须可检查 | scheduler / active_action / revision timeline 全部可 inspect |
| **K8** Deployment 与 Game Project 分离 | 游戏内容（项目）与 LLM 部署（deployment.yaml）不混放 |

状态五分离（Spec §8）：`WorldState`（世界本体，revision 单调）/
`RuntimeState`（会话调度）/ `BackendState`（后端引用）/ `TraceState`
（记录流）/ `ViewState`（表现层投影）——互相不越界。

一次 tick 的骨架：玩家/角色提出 **ActionProposal** → 各
**Effect Producer**（官方模块）产生 **ProposedEffect** →
**AuthorityPolicy** 裁决 → **Commit**（revision +1，DomainEvent
级联）→ 表现层（narrator / image / tactical view）从新 ViewState
派生输出。**没有 LLM 的世界照样 tick**（规则/确定性 policy）；
**有 LLM 的世界里 LLM 也只能提议**（K4/K5）。
