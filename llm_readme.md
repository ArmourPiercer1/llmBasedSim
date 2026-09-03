# llm_readme — LLM 协作者简报

> 本文档面向**在本工作区干活的 LLM 协作代理**：你是谁、现在
> 处在什么阶段、必须遵守什么纪律、文档在哪。历史开发计划
> 存档在 §5。

## 1. 你是谁

你是本仓库（llmBasedSim，LLM 互动模拟游戏）的协作开发代理。
仓库 = **双引擎**：

- **v2（`src/engine_v2/`）= 主开发线**：确定性内核 + Policy
  架构（K1–K8 不变量，Spec 第 2 节）。当前进度 = Phase 1–10
  收口（G0–G10 机械面 PASS，全量 3205/0），P11+ 进行中；
- **v1（`src/main.py` / `src/web/`）= 冻结原型**：LangGraph
  实现，可运行、可作迁移对照，不再演进。

## 2. 你的工作纪律（硬性）

1. **门禁纪律**（详见 `CONTRIBUTING.md` §4）：按 Phase → 任务包
   → 波次（W）→ 门禁（G）推进；SOT（`docs/v2/contracts/P<n>`）
   冻结后**只追加 §9 勘误行**，不改原文；白名单外文件改动先裁决；
   过程目录（`.p8/` `.p9/` `.p10/` `.review-drafts/`）**永不提交**；
2. **测试纪律**：全量命令
   `PYTHONPATH=. .venv/bin/python -m pytest tests/ -q -p no:cacheprovider`
   （当前基线 3205/0；恒等式 = 门禁报告钉值）；**零真实 LLM
   调用**（确定性 fake）；**零真实 API Key**（`.env` 保持占位符）；
3. **人工面不自裁**：含人工判定的门禁（如 G10 S11：GUI 信息
   层次 / 实时图像不错场 / Galgame 视觉连续性），判定人 = 用户；
   你的职责 = 备好自动化前置（`acceptance/run.sh`）+ 按 SOT
   记录格式收记录，**不代替用户下结论**；
4. **冻结面不静默改**：v2 白名单文件、锚文件 sha256 钉、行宽
   ≤100、控制字节 / K8 扫描域纪律——机械测试会抓，先裁决再动；
5. **披露优先**：发现交付缺陷（钉面矛盾、不可达路径等）→
   机械修复 + SOT 勘误行 + 向用户披露（先例：ERR-P10-16，
   P10 index 页静态引用 404，由 Playwright 端到端自动化发现）；
6. **文档同步**：使用面变化 → `docs/v2/usage/`；契约变化 →
   SOT §9；顶层 → `README.md` / `CONTRIBUTING.md` / 本文件。

## 3. 快速定向

| 我要… | 去哪 |
|---|---|
| 理解架构权威 | `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md`（§1–§47） |
| 看当前 Phase 设计 | `docs/v2/contracts/P<n>-*.md`（§9 = 全部裁决记录） |
| 看收口证据 | `docs/v2/gates/G<n>-gate-report.md` |
| 写/跑 v2 游戏 | `docs/v2/usage/`（quickstart / project-authoring / devtools-and-extensions） |
| 跑演示 / 验收 | `PYTHONPATH=. .venv/bin/python scripts/v2_g10_acceptance.py --port 8000` / `bash acceptance/run.sh` |
| 看代码结构 | `src/engine_v2/README.md`（13 子包 + 冻结规则） |
| v1 行为对照 | `docs/game-flow-interfaces.md` + `docs/v2/reference/` |

**环境**：Python 3.12（`.venv`）；v2 开发**不需要 API Key**
（K5：演示宿主 = 确定性 policy/backend）；`.venv-acceptance`
= Playwright 专用 venv（UI 面自动化），勿混入主 venv。

**常用命令**：

```bash
# 全量测试（~17s）
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q -p no:cacheprovider
# 项目校验
PYTHONPATH=. .venv/bin/python -m src.engine_v2.content.cli validate <project>/
# Web 演示（galgame 样例；零 key）
PYTHONPATH=. .venv/bin/python scripts/v2_g10_acceptance.py --port 8000
# devtools（存档检视/追踪/重放/分支/一致性）
PYTHONPATH=. .venv/bin/python scripts/v2_devcontrol.py <cmd> <save_id>
# 一键验收（机械面 + HTTP + UI + 截图存证）
bash acceptance/run.sh && bash acceptance/stop.sh
```

## 4. 当前待办面（P11+ 承接，供排期参考）

- `adapters/cli/` + `adapters/dsh/`（P11，Spec §35/§44）；
- 真实 LLM provider 接线 + 开箱即玩装配（P6 抽象已备）；
- 真实图像生成 backend（P10 抽象 + 确定性参考面已备；S4 人工面）;
- inspector / workbench HTTP 页面路由（数据面已备；P10 404 保留）；
- 官方装配 API（项目 → 可玩会话；当前装配 = 验收驱动宿主侧链）；
- G10 人工面 S11 三判据（判定人 = 用户；前置自动化已就绪）。

## 5. 历史开发计划（存档）

以下两节是项目最初的需求简报（v1 时代），v1 已按此实现并冻结；
保留原文以追溯功能设计动机（潜意识系统 / 行动可行性双轨 /
物理数据维护 / 语言范例注入）。

### 5.1 Development Plan Initial

#### （一）多 agent 系统

1. **物理变化 agent**：决定**非角色**的所有物理过程，并给出物理
   变化及它与人物交互的快过程结果。
2. **角色变化 agent**：根据设定，决定角色的行为。
3. **玩家感官 agent**：决定玩家能接收到什么信息。
4. **初始化 agent**：通过与玩家对话，初始化工作流、角色设定、
   玩家设定等信息。

例如：

```text
角色变化agent A -> 角色A挥手 -> 物理变化agent -> 角色A站在桌子
旁边，所以他会碰到桌子；桌子上有个花瓶，花瓶掉落 -> 玩家感官
agent -> 玩家看到花瓶掉落
```

#### （二）数值维护系统

存储玩家、各角色、物理世界的各种信息，以供 agent 作出决策。

### 5.2 Development Plan 20260623 — Idea

#### （一）玩家意识-潜意识转换（精神层）

玩家的操作决策实际上是玩家的表层意识，但玩家的潜意识也会对
行动造成影响。“玩家输入的”和“世界中的玩家想要做的”会有区别，
需要潜意识节点处理玩家输入。例如：

```text
玩家人设 = 傲娇大小姐。虽然喜欢一个 npc，但做不到直接说。
输入“我对{喜欢的对象}说‘我爱你。’”
→ 潜意识节点处理为“哼，才没有喜欢你呢！”
```

潜意识层也需要更新（经历改变人设后，她能正常说“我爱你”了）。
需维护玩家角色的潜意识记录 + 负责潜意识处理的节点；玩家输入
在这一层被处理为结构化输出。

#### （二）玩家想法-行动转换（物理层）

从“玩家想做的”到“玩家实际做的”之间有巨大鸿沟（“我飞起来击杀
大 boss”在多数场景不可行）。需节点 + 「玩家能做什么」数据库
（User Capability List），维护：

1. 符合普通人认知但玩家不能做的（无腿者不能走路）；
2. 不符合普通人认知但玩家能做的（高修仙者可飞）；
3. 玩家能概率成功的（不熟练盗贼开锁需 roll 点）。

需维护玩家角色能力数据，并提示物理引擎节点处理。

#### （三）游戏工作流优化

1. 从结构化文件直接输入玩家/NPC/环境设定，跳过对话初始化；
2. 存档及恢复功能；
3. 维护玩家/NPC/环境的物理数据（身高三围 ↔ 门尺寸等推理）；
4. 语言表达范例：注入设定与示例语段到对应节点提示词，维护
   人设与文风一致。

> 上述全部在 v1 落地（`src/agents/init.py` 文件开局、
> `src/graph/game_graph.py` 潜意识/可行性节点、`src/game/`
> 能力规则、`saves/` 存档、`speech_examples` 注入）；v2 中的
> 对应承接面见 `docs/v2/usage/project-authoring.md`（项目格式
> 字段：`subconscious_rules` / `capabilities` / `speech_examples`
> / `physical_profile` / `attributes`）。
