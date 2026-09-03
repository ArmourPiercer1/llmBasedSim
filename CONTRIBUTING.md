# Contributing

本文档面向参与本项目开发的协作者（含 LLM 协作代理），说明环境、
运行、模块边界、**v2 门禁纪律**与提交前检查。协作规则以本文档
为准；接口/设计细节以 `docs/v2/contracts/`（冻结 SOT）与
`docs/plans/`（Spec）为准；使用面以 `docs/v2/usage/` 为准。

## 1. 项目协作目标

本仓库是双引擎仓库：

- **v2（`src/engine_v2/`）= 主开发线**：把 LLM 互动模拟游戏推进
  为稳定、可测试、可回放、可扩展的确定性内核 + Policy 架构；
- **v1（`src/main.py` / `src/web/` / `web/`）= 冻结原型**：G0
  基线，可运行、可作迁移对照，**不再演进**。

协作时优先关注：

1. 保持模块边界清晰（v2 子包边界 + v1/v2 零互 import）；
2. 优先修复影响内核稳定性的 bug；
3. 对 SOT 钉面、状态结构、Prompt/推理面的修改小步提交；
4. **不把真实 API Key 提交到仓库**（`.env` 保持占位符
   `sk-your-...` 形态；部署配置只引用环境变量名）；
5. 测试里**零真实 LLM 调用**（K5 纪律：确定性 fake/backend；
   真实 provider 接线是独立任务面）。

## 2. 本地开发环境

```bash
cd /home/armourpiercer/projects/llmBasedSim
# 要求 Python >= 3.12（.venv = 3.12.14）
python -m venv .venv
.venv/bin/pip install -r requirements.txt
# 可选（获得 llmsim console script）：
.venv/bin/pip install -e .

cp .env.example .env          # 仅 v1 运行需要真实 key；v2 开发不需要
```

## 3. 运行与验证

```bash
# v2 全量测试（当前基线 = G10 收口 3205 passed / 0 failed，~17s）
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q -p no:cacheprovider

# v2 单面
PYTHONPATH=. .venv/bin/python -m pytest tests/engine_v2/<子包> -q -p no:cacheprovider

# v2 项目校验
PYTHONPATH=. .venv/bin/python -m src.engine_v2.content.cli validate <project>/

# v2 Web 演示（零 API Key）
PYTHONPATH=. .venv/bin/python scripts/v2_g10_acceptance.py --port 8000

# v2 一键验收（preflight + HTTP + Playwright UI；见 G10 验收方案）
bash acceptance/run.sh && bash acceptance/stop.sh

# v1（冻结，仅回归用途）
python -m src.main / python -m src.web.main
```

**测试恒等式纪律**：每个 Phase 收口时门禁报告钉一个
「基线 + 本 Phase 增量 = 总数」的恒等式（G10 = 3142 + 63 =
3205）。改测试前先查当前 Phase 的门禁报告恒等式；新增测试要在
收口时更新恒等式。

## 4. v2 门禁与 SOT 纪律（核心）

v2 按 `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md`
的 Phase → 任务包 → 波次（W）→ 门禁（G）推进。每个 Phase：

1. **W0 设计**：产出/冻结该 Phase 的设计 SOT
   （`docs/v2/contracts/P<n>-*.md`），盲评评审收敛（通过/投机
   通过/补充/阻塞 四裁决）；
2. **W1..Wn 实现波次**：从 SOT 落码；每波独立盲审；
3. **门禁 G<n>**：全量测试 + 门①–⑥ 步骤 + 门禁报告
   （`docs/v2/gates/G<n>-gate-report.md`）；
4. **勘误链**：SOT §9 的 `ERR-P<n>-NN` 行 = 实现期全部裁决
   记录（发现面/原钉面/更正面/裁定依据 四栏）。**SOT 冻结后
   不改原文，只追加 §9 勘误行**；钉面更新与勘误行同提交。

波次纪律要点（P10 实例，通用同构）：

- 白名单路径集：每个 Phase 的 SOT 钉该 Phase 可触碰的文件集
  （如 P10 = 37 unique paths）；**白名单外的文件改动 = 门禁
  违规**（确需改动先裁决、登记、更新白名单）；
- 双 sha 钉：关键冻结文件（锚文件等）以 sha256 钉死，改动即红；
- 纪律机械面：行宽 ≤100（ruff）、特定域零控制字节（D3）、
  K8 扫描域零 provider 名（除钉住的合法命中）、骨架期零提前
  实现（`tests/test_engine_v2_skeleton.py` 静态扫描）；
- **过程目录永不提交**：`.p8/` `.p9/` `.p10/` `.review-drafts/`
  （评审工作区）、`.venv*/`、运行时产物（`acceptance/*-report.json`
  / `*.log` / `*.pid`、`docs/v2/gates/evidence-*/`）；
- 人工面挂起规则：含人工判定的门禁（如 G10 S11 三面）在用户
  按 SOT 记录格式判定前，门禁决策保持「PASS（机械面；人工
  挂起）」，**Leader/协作者不自裁人工面**。

## 5. 代码结构约定

**v2（`src/engine_v2/`，13 子包）**——职责与 Spec 章节对照见
`src/engine_v2/README.md`；冻结规则（v2 骨架期起即生效）：

1. `engine_v2` 内任何文件**不得 import v1 模块**（`src.graph` /
   `src.game` / `src.agents` / `src.web` / `src.llm` /
   `src.prompts` / `src.config` / `src.models` / `src.ui`）；
2. v1 入口不得 import / 引用 `engine_v2`（G0 互锁门禁）；
3. LangGraph / OpenAI 依赖不得进入 `engine_v2.core`；provider
   SDK 只允许出现在 `engine_v2/llm/` 且保持 provider-neutral；
4. 核心面不 import 表现层；状态面（core）不 import 调度面
   （runtime）——按各 Phase SOT 的导入闭集执行。

**v1**（冻结）：`src/main.py` 只入口与主循环；`src/graph/`
管道与状态 schema；`src/models/` 只数据模型；`prompts/` 只模板；
`config/` 只配置。v1 改动仅限：门禁要求的回归维护，或用户明示。

**通用**：

- 新增功能先找对应 Phase SOT 的扩展点（模块 / 插件 / backend
  协议），不新造平行机制（`docs/v2/usage/devtools-and-extensions.md`
  §3）；
- 数据面与路由面分离（P10 先例：inspector/workbench 数据面先建、
  路由后落——保留面用 404 信封显式披露，不静默）；
- 错误面 = 封闭码 + 确定性 message（零时间戳/零随机/零指针）。

## 6. Prompt / 推理面修改约定（v2）

1. LLM 输出 = 提议（K4/K5）：改推理面时确认 authority/commit
   链未被绕过；
2. 项目只声明 capability 画像（字段封闭，K8）；provider/model
   pinning 一律进 deployment 面，不进项目文件（K8 扫描会抓）；
3. 改 InferenceProfile / prompt policy 后跑对应 Phase 测试面 +
   全量；`llm_call` / `prompt_assembly` trace 钉值要同步；
4. 测试零真实 LLM：用 FakeInferenceBackend（确定性脚本响应）。

v1 prompt 约定（冻结参考）：中文输出、JSON 要求明确、与
Pydantic schema 一致、改后手动跑一轮。

## 7. 文档维护约定

| 改动面 | 同步文档 |
|---|---|
| v2 引擎行为/契约 | 对应 `docs/v2/contracts/P<n>` SOT（§9 勘误行）+ 门禁报告；使用面变化 → `docs/v2/usage/` |
| v2 架构级决策 | Spec 修订记录（`docs/plans/`） |
| v2 项目格式 | `docs/v2/usage/project-authoring.md` + P5 SOT |
| v1 接口 | `docs/game-flow-interfaces.md`（仅 v1 回归维护时） |
| 顶层使用/协作 | `README.md` / `CONTRIBUTING.md` / `llm_readme.md` |

文档语言 = 中文（代码标识符/路径保持原文）。引用设计时引
SOT 章节号 + 文件名，不引行号（行锚会漂移；勘误链惯例 =
「行锚漂移以复测为准」）。

## 8. 提交前检查清单

- [ ] v2 全量测试绿（`PYTHONPATH=. .venv/bin/python -m pytest tests/ -q -p no:cacheprovider`）；
- [ ] 测试恒等式未破坏（或已按收口惯例更新）；
- [ ] 改动在白名单/授权范围内（越界 = 先裁决）；
- [ ] 未提交 `.env` 真实 key / `.p*/` / `.review-drafts/` / `.venv*/` / 运行时产物；
- [ ] SOT 钉面改动与 §9 勘误行同提交；
- [ ] 使用面变化已同步 `docs/v2/usage/`；
- [ ] 人工面未自裁（挂起态保持「机械 PASS + 人工挂起」）；
- [ ] v1 未被 v2 改动波及（互锁测试绿：`tests/test_engine_v2_skeleton.py`）。
