# P9 Official Modules / v1 Migration — W0 设计 SOT

| 项 | 值 |
|---|---|
| 阶段 | Phase 9（Plan §18 L769–784） |
| 基线 commit | `aab029c`（G8 收口；P8 代码最终 `9eb3e27`） |
| 分支 | `architecture-v2` |
| 本文件角色 | P9 唯一设计 SOT（Single Source of Truth）；实现波次（W1–W7）以其为唯一依据 |
| 结构口径 | 逐节镜像 `docs/v2/contracts/P8-persistence-replay-devcontrol-design.md`（1782 行 @ 904c997） |
| 允许写盘 | 仅 §3.19 闭集白名单（47 行：46 新建 + 1 纯追加）+ 本文件 + `.review-drafts/p9-w0-dev-report.json`；W0 阶段零代码/测试/git 写操作 |
| 任务书 | `.p9/w0-brief.md`（191 行；与本文件冲突处以本文件为准并登记 §8.4 / §9） |

> **字节真值优先**：本文件所有 `file:line` 锚点均在 `aab029c` 工作树逐字节核验
> （`sed -n` / `awk 'NR>=X&&NR<=Y'` / AST 解析 / `wc -l`）。任务书与本文件的出入
> （v1 行总数口径、G9 条款计数、占位文件 docstring 完整性）以本文件为准，
> 登记于 §9 勘误预备区（ERR-P9-NN）。

---

## §0 定位与基线

### 0.1 范围（Plan §18 任务表 L769–784 逐项对齐 + P9 落位映射（能力列省略））

| ID | 任务 | 属性 | 难度 | 上下文 | 默认模型 | P9 落位（本 SOT §3） |
|---|---|---|---|---|---|---|
| P9-T01 | v1 reusable vs obsolete code mapping | 探索代码区 | 较高难度 | 1M | GFlash | 设计期交付 = §2.3 三态映射表；机械面 = W7 `test_module_face.py` + TestP9Boundary 方法 4 |
| P9-T02 | Attributes module migration | 开发 | 少量思考 | 256K | Q27 | `modules/attributes.py`（§3.2）；`modules/base.py` 公共面（§3.1）同波 W1 落盘 |
| P9-T03 | Inventory / object-state module | 开发 | 少量思考 | 256K | Q27 | `modules/inventory.py`（§3.3） |
| P9-T04 | Relationships module | 开发 | 少量思考 | 256K | Q27 | `modules/relationships.py`（§3.4） |
| P9-T05 | StandardCharacter module | 开发 | 少量思考 | 256K | Q27 | `modules/character.py`（§3.5） |
| P9-T06 | Perception / Knowledge module migration | 开发 | 较高难度 | 1M | QMax | `modules/perception.py`（§3.6）+ `modules/knowledge.py`（§3.7） |
| P9-T07 | Scenario / Trigger module | 开发 | 较高难度 | 1M | QMax | `modules/scenario.py`（§3.8） |
| P9-T08 | standard movement / interaction action executors | 开发 | 少量思考 | 256K | Q27 | `modules/actions.py`（§3.9） |
| P9-T09 | v1 init-file → Project Format v2 migration / compatibility | 开发 | 较高难度 | 1M | GFlash | `modules/v1_migration.py`（§3.15）+ `scripts/v2_migrate_v1.py`（§3.15.4） |
| P9-T10 | 删除 NPC global-event omniscience 行为并补回归测试 | 开发 | 少量思考 | 256K | Q27 | `test_perception_knowledge.py::t6`（§6.1；v1 锚 `src/graph/game_graph.py:553–561`） |
| P9-T11 | Galgame vertical slice sample | 测试 | 少量思考 | 256K | Q27 | `modules/dialogue.py`（§3.10）+ `modules/narration.py`（§3.14）+ 样例 §3.16.1 |
| P9-T12 | Sandbox vertical slice sample | 测试 | 较高难度 | 1M | GFlash | `modules/dynamics.py`（§3.13）+ 样例 §3.16.2 |
| P9-T13 | Tactical vertical slice sample | 测试 | 较高难度 | 1M | GFlash | `modules/space.py`（§3.11）+ `modules/tactical.py`（§3.12）+ 样例 §3.16.3 |
| P9-T14 | v1/v2 differential behavior review | 测试 | 较高难度 | 1M | GLM | §3.17 差分方法学 + `test_p9_differential.py`（§6.1） |

**G9 条款计数口径（勘误预备 ERR-P9-02）**：任务书「五+五+四」= 14 个命名面；
Plan G9 段（L786–815）「并且」2 条款（L810–813：旧 init file migration / 明确
incompatible diagnostics；旧 LangGraph 不再是 v2 Engine Runtime 必要依赖）。
本 SOT 口径：**16 个门面条**（14 命名面 + 迁移条款 A16 + LangGraph 条款归
TestP9Boundary 方法 4 的 import 闭包检查），A 判据共 24（§5.2）。

### 0.2 Gate G9 逐字回应（Plan L788–813 原文 + 逐条回应）

Plan 原文（L788–813 逐字；L786–787 = `## G9` 标题/空行、L814–815 = 尾随空行/节界，不入围栏）：

```text
三套 sample 必须分别证明：

### Galgame
- dialogue；
- character policy；
- relationship；
- observation；
- narrative-ready ViewState。

### Sandbox
- long action；
- world time；
- NPC wakeup；
- knowledge boundary；
- LLM / rules dynamics。

### Tactical
- Grid/Hex-like Space；
- tactical GameplayMode；
- deterministic actions；
- mode transition。

并且：

- 旧 init file 可以 migration 或给出明确 incompatible diagnostics；
- 旧 LangGraph 不再是 v2 Engine Runtime 的必要依赖。
```

逐条回应（每条 = 机制 + A 判据 + 1:1 平铺测试函数）：

| # | 条款 | 机制（本 SOT 章节） | A 判据 | 平铺函数（§6.1） |
|---|---|---|---|---|
| G9-1 | Galgame：dialogue | `modules/dialogue.py::run_dialogue`（§3.10）经 P6 `FakeInferenceBackend`（冻结缝 §2.5）产出回应 | A1 | `test_g9_galgame.py::t1_dialogue` |
| G9-2 | Galgame：character policy | `modules/character.py::NpcBehaviorPolicy`（§3.5）实现 core `BehaviorPolicy`（behavior_policy.py:54），由 `run_policy_decide`（behavior_policy.py:83）驱动 | A2 | `test_g9_galgame.py::t2_character_policy` |
| G9-3 | Galgame：relationship | `modules/relationships.py::adjust_relationship`（§3.4）经对话事件产出 `RelationshipEvent`，kernel 组件面落位 | A3 | `test_g9_galgame.py::t3_relationship_update` |
| G9-4 | Galgame：observation | `modules/perception.py::build_observations`（§3.6）产出 core `ObservationRecord`（knowledge.py:109），仅空间邻域 | A4 | `test_g9_galgame.py::t4_observation` |
| G9-5 | Galgame：narrative-ready ViewState | `modules/narration.py::render_narrative_view`（§3.14）= 派生数据、JSON-clean、非权威（Spec §8.5 L626–638） | A5 | `test_g9_galgame.py::t5_narrative_view` |
| G9-6 | Sandbox：long action | core `start_action`（scheduler.py:468）+ `DurationPolicy`（action_registry.py:102）+ `modules/actions.py` 执行器（§3.9） | A6 | `test_g9_sandbox.py::t1_long_action` |
| G9-7 | Sandbox：world time | core `LogicalClock`（clock.py:77）+ `ScenarioSpec.ticks_per_game_minute`（schemas.py:448 起）；世界时间 = 逻辑 tick 的确定性投影 | A7 | `test_g9_sandbox.py::t2_world_time` |
| G9-8 | Sandbox：NPC wakeup | core `enqueue_actor_wakeup`（scheduler.py:374）事件驱动；NPC 仅在 wakeup 时决策（43.2-2「all NPC decide every turn」移除） | A8 | `test_g9_sandbox.py::t3_npc_wakeup` |
| G9-9 | Sandbox：knowledge boundary | §3.6/§3.7 感知-知识分离；界外 NPC 的 KNOWLEDGE/MEMORY 组件零变更 | A9 | `test_g9_sandbox.py::t4_knowledge_boundary` |
| G9-10 | Sandbox：LLM / rules dynamics（Plan 单条 bullet = 2 判据，D-P9-11） | P7 冻结 `LLMWorldDynamics`（dynamics/llm_world.py:180）经脚本化 backend + P7 `RuleDynamics`（dynamics/rule.py:273），host = `run_dynamics_turn`（dynamics/host.py:86） | A10 / A11 | `test_g9_sandbox.py::t5_llm_dynamics` / `t6_rules_dynamics` |
| G9-11 | Tactical：Grid/Hex-like Space | `modules/space.py::HexGrid`（§3.11）hex 邻接 → 纯函数映射到冻结 `GraphSpace`（space.py:256）；kernel `GridSpace`（space.py:350）= 方格对照面 | A12 | `test_g9_tactical.py::t1_hex_space` |
| G9-12 | Tactical：tactical GameplayMode | `modules/tactical.py::build_tactical_overlay`（§3.12）产出冻结 `ModeOverlay`（gameplay_mode.py:150），`merge_modes`（gameplay_mode.py:266）合入 | A13 | `test_g9_tactical.py::t2_tactical_mode` |
| G9-13 | Tactical：deterministic actions | `modules/actions.py` 执行器 = 纯函数（零 backend 调用、注入时钟/RNG）；同输入 → 同效果流（P9-INV-6） | A14 | `test_g9_tactical.py::t3_deterministic_action` |
| G9-14 | Tactical：mode transition | 冻结 `apply_mode_change`（gameplay_mode.py:475）+ `modules/tactical.py::TacticalModePolicy`；探索→战术→探索，单一 WorldState 全程 | A15 | `test_g9_tactical.py::t4_mode_transition` |
| G9-15 | 并且①：旧 init file 可 migration 或明确 incompatible diagnostics | `modules/v1_migration.py`（§3.15）闭集映射规则；4 输入（public_start 3 项目 + config/simulation.yaml）逐一产出（可加载 v2 项目）或（闭集诊断码的 incompatible 报告） | A16 | `test_v1_migration.py::t1_gate_migration_clause` |
| G9-16 | 并且②：旧 LangGraph 不再是 v2 Engine Runtime 必要依赖 | engine_v2 全树 import 闭包零 `langgraph`/`langchain`（TestP9Boundary 方法 4，AST 级）；P9 模块零 LangGraph 消费；v1 冻结树自含（其测试在 3054 基线内独立运行） | —（边界方法） | `test_import_boundary.py::TestP9Boundary::test_p9_import_closure` |

### 0.3 基线表（W0 实测 @ aab029c，全部 `sed`/`wc`/`git`/pytest 复测）

| 项 | 实测值 | 核验命令 |
|---|---|---|
| 基线 commit | `aab029c`（`architecture-v2` 分支 HEAD） | `git rev-parse HEAD` |
| 门③ diff 面 | `git diff --name-only aab029c..HEAD -- src tests scripts` = ∅（W0 时点 HEAD == 基线，平凡成立；实现波次后以门③复测为准） | `git diff --name-only` |
| v1 冻结锚 | `f0a1052` = v1 树最后变更点；`git diff --name-status f0a1052..HEAD` 于 v1 路径集 = **25** 条既成条目（1 M `pyproject.toml` + 24 A = 4 个 v1 测试侧 `.py`（`char_helpers.py`/`test_char_graph.py`/`test_char_nodes.py`/`test_engine_v2_skeleton.py`）+ 20 个 `v2_*` fixture 文件，均 P1–P8 既成产物；ERR-P9-05(1) 撤回 ERR-P9-04(21) 之 24 计数）；`src/**`（除 `src/engine_v2/`）+ `public_start/**` + `config/**` 子集实测为空；P9-INV-1 冻结范围 = 自基线 `aab029c` 起不变 | `git diff --name-status f0a1052..HEAD -- src public_start config tests pyproject.toml`（仅排除 `src/engine_v2/` + `tests/engine_v2/` 两子树；子串过滤 `grep -v 'engine_v2'` 会误排 `tests/test_engine_v2_skeleton.py`，禁用） |
| v1 路径集定义 | `src/**`（除 `src/engine_v2/**`）+ `public_start/**` + `config/**` + `tests/**`（除 `tests/engine_v2/**`）+ `pyproject.toml` | — |
| 套件基线 | **3054 passed in 15.66s** | `PYTHONPATH=. .venv/bin/python -m pytest -q`（背景任务 bash-178 实测） |
| v1 源码 | 34 个 `.py`（含 10 个 `__init__.py`，其中 `src/__init__.py` 0 行），合计 **6146 行**（与任务书 ≈6146 一致；W0 初探 5710 系漏列文件，已按 §9 ERR-P9-01 更正） | `find src -name '*.py' -not -path '*/engine_v2/*' -exec wc -l {} +` |
| v1 测试 | `tests/` 顶层 20 个 `test_*.py` + `char_helpers.py` + `fixtures/`（v1 测试计入 3054 基线，冻结不改） | `ls tests/test_*.py` |
| v1 init 文件 | `public_start/test_empty.yaml` 154 行 / `whisperheads.yaml` 897 行 / `murder.yaml` 802 行（合计 1853）+ `config/simulation.yaml` 23 行 | `wc -l` |
| 边界锚文件 | `tests/engine_v2/core/test_import_boundary.py` **2071 行 @ HEAD**；P9 块 = L2071 后 EOF 纯追加（P8 R8 先例：1629→2071 实测 +442 行） | `wc -l` |
| core 冻结面 | 32 子模块、308 导出（`core/__init__.py:416` `__all__`，文件 727 行） | `wc -l` + `grep -c "^    '"`（单引号条目，实测 308） |
| P5 content 冻结面 | loader 6 / module_graph 11 / project_ir 6 / rule_module 43 / schemas 25 / validator 8 / cli 4 导出；`LAYOUT_REQUIRED`（loader.py:46）= `("game.yaml",)`；`LAYOUT_OPTIONAL`（loader.py:50–60）= 9 glob（world/characters/items/rules/actions/prompts/scenarios/modules 之 `*.yaml` + `plugins/*/plugin.yaml`），零 `.py`；`detect_v1_shape`（loader.py:242） | `awk '/^__all__ = \[/,/\]/'` |
| P6 llm/prompts 冻结面 | `llm/__init__.py` 9 行占位；adapter.py：InferenceRequest:98 / InferenceResponse:132 / InferenceBackend:150 / FakeInferenceBackend:296 / calls:326 / generate:330 / MonotonicClock:47 / FixedMonotonicClock:71；deployment.py：DeploymentProfile:74 / load_deployment:122；prompts/registry.py：render_template:116 | `grep -n` |
| P7 dynamics 冻结面 | 8 模块 35 导出；backend.py WorldDynamicsBackend:302 / BackendMetadata:232；host.py DynamicsTurn:40 / run_dynamics_turn:86；llm_world.py LLMWorldDynamics:180；rule.py WorldRule:82 / RuleDynamics:273；composite.py CompositeDynamics:66 | `grep -n` |
| P8 persistence/devtools 冻结面 | persistence 6 模块 25 导出（snapshot.py：PersistenceSnapshot:52 / to_persistence_snapshot:104 / dump_persistence_snapshot:133 / load_persistence_snapshot:143 / check_persistence_versions:176）+ devtools 3 模块 19 导出 = 44 | `grep -n` |
| 占位包 | `modules/__init__.py` 9 行 / `presentation/__init__.py` 8 行 / `context/__init__.py` 8 行 / `adapters/__init__.py` 8 行 / `runtime/__init__.py` 9 行（全部含「占位，Phase N 填充」docstring；P5/P7/P8 填充包后占位 docstring 均不更新的既有惯例，§2.9） | `wc -l` + `sed` |
| 行宽纪律 | `pyproject.toml:31` line-length = 100 | `sed -n '31p'` |
| scripts 现状 | `scripts/llm_smoke.py`、`scripts/v2_devcontrol.py`（2 文件；P9 新增 `v2_migrate_v1.py`） | `ls scripts` |
| P5 参考镜像 | `tests/fixtures/v2_project_zero_python/`（5 文件：game.yaml + world/main_world.yaml + characters/npc01.yaml + rules/basics.yaml + actions/move.yaml）= test_empty.yaml 的 P5 手工镜像（偏差台账 D-01：objects 未镜像） | `find` |
| Python 环境 | `.venv/bin/python` + `PYTHONPATH=.`；P9 代码 import 闭集 = stdlib + pydantic + `engine_v2` 冻结根（§3.0 闭集表；uv.lock 既有；冻结 pyproject 声明的 v1 树 10 依赖 P9 零消费） | — |

### 0.4 非范围（P9 明确不做，归后续阶段 / 门）

| 非范围项 | 归属 | 依据 |
|---|---|---|
| presentation/（CLI/Web adapter 实现） | P10/P11 | Spec §44（L2198–2201）；43.2-8 Web singleton session 移除 |
| 真机 runtime host（进程入口 / REPL / 循环宿主） | P1（Plan §10；冻结 `engine_v2/runtime/` 包 + Scheduler 宿主循环，见 §2.3 `src/main.py` 行与 `game_graph` 行） | P9 样例宿主 = 测试 conftest（§6.2）；Plan 全文无进程入口/REPL 条目（Plan §15 = Phase 6 LLM Runtime，非宿主面） |
| 图像侧叙述渲染（text/image 并行之 image） | P10 | Spec §32（L1678–1732）；P9 narration 仅 text 侧（D-P9-13） |
| OI-P7-1 项目侧 `.py` backend 发现 | 不移交、不实装 | G8 报告 R4（L195）+ D-P8-15 评估结论（loader 9-glob 冻结） |
| D-P7-13 测试侧 handler 注册 | 维持现状 | G8 报告 L203（core 冻结约束持续适用；条款跨 L202–203） |
| G8 三条 s2 评估面（branch-audit payload schema / replay ABORTED 保留 / snapshot-derived inspect 覆盖） | P9 仅登记、不评估 | G8 报告 L201–202；本 SOT §0.6 R5 占位 |
| SQLite / 并发持久化 | P8+ | G8 报告 R7（单进程原型 §0.4.7） |
| 新第三方依赖 / License 变更 | S4 HARD STOP | Plan §24 S4（L1259–1271）；P9-INV-10 |
| v1 行为回放（经 v1 LangGraph 运行时重放旧局） | 非本阶段 | D-P9-14：差分 = 纯函数直引 + 镜像同构，非运行时回放 |

### 0.5 纪律（D1–D8）

- **D1 字节真值优先**：一切 `file:line` 锚点 `aab029c` 工作树 `sed -n`/`awk`/AST
  逐字节核验后方可写入本文件与实现 docstring；引用 P7/P8 SOT 的行号以本 SOT
  §2 复核值为准。
- **D2 行宽**：P9 全部产物（落盘 src/tests/scripts）≤ 100 字符/行
  （`pyproject.toml:31`；`LC_ALL=C.UTF-8 awk 'length($0)>100'` 零命中，
  门③ ⑤ 步）；本 SOT = 非表格行零命中（markdown 表格行豁免，P8 SOT
  先例：max 760/表格行）。
- **D3 控制字节纪律**：P9 全部文本/docstring 参数零裸 `\b`（反斜杠+b 连续字节
  序列 0x5C 0x62）；正则以字符类/锚定替代（ERR-P7-14 先例）。
- **D4 依赖闭集**：P9 代码仅 stdlib + pydantic（uv.lock 既有）；`pyproject.toml`
  字节冻结；零新增依赖（S4）。
- **D5 冻结面零修改**：core/content/llm/prompts/dynamics/persistence/plugins +
  其测试目录 + v1 路径集 + 占位 `__init__` 五件套字节不变；唯一修改模式 =
  `tests/engine_v2/core/test_import_boundary.py` EOF 纯追加（P8 R8 先例）。
- **D6 确定性**：P9 全部公开函数纯函数或显式注入状态；时钟 = 注入（core
  `LogicalClock` / P6 `FixedMonotonicClock`）；RNG = 注入（P5 `DslRng` 或
  测试侧 `random.Random(seed)`）；零 wall-clock、零模块级全局 RNG 调用。
- **D7 K8 词表闭集**：P9 src 字符串字面量 12 名零命中（openai / anthropic /
  langchain / litellm / ollama / gemini / gpt / claude / llm / provider /
  api_key / base_url；P4 黑名单 L225–240）+ engine_v2 全树 import 零
  langgraph/langchain（G9 条款②）。
- **D8 勘误链纪律**：§9 唯一规范记录；历史条目不追改；实现波次勘误按
  ERR-P9-NN 续编（ERR-P8-01..07 先例，G8 报告 L203–204）。

### 0.6 风险登记册

| # | 风险 | 等级 | 缓解（SOT 面） |
|---|---|---|---|
| R1 | T09 自由文本规则（world_rules.append）折叠为 v2 规则条目产生语义漂移（v1 = LLM prompt 上下文 vs v2 = 可行性规则） | 中 | D-P9-08：passthrough 条件 `if(1 >= 0, allowed)` 永不改变可行性 + 逐条 INFO 诊断（MIGRATION_FREEFORM_RULE_FOLDED）+ §3.17 差分面复核 |
| R2 | whisperheads（897 行）/ murder（802 行）大文件迁移覆盖不全 | 中 | 三项目全文件迁移（非节选）+ A17 同构面（与 P5 zero_python 镜像对照）+ A22 诊断闭集 |
| R3 | hex 邻接与 kernel 方格 GridSpace 语义边界混淆 | 低 | `modules/space.py` hex → GraphSpace 纯函数映射（A12）；GridSpace 仅作对照面；两空间域以 `SpatialDomain` 分离 |
| R4 | 边界锚文件纯追加后体积增长 | 低 | 唯一修改模式 = EOF 纯追加；TestP9Boundary 6 方法估算 +350–450 行（P8 R8 实测 +442 行同量级） |
| R5 | v1 纯函数直引（T14 差分）的 import 风险（v1 树含 LangGraph 依赖文件） | 低 | W0 预验：`src/game/{attributes,condition_eval,deterministic_rules,tick_eval,state_apply}.py` 零第三方 import（实测头部 import 仅 re/random/copy/dataclass/typing）；`src/models/*.py` 仅 pydantic。若 import 失败 → S1 触发人工介入 |
| R6 | G8 三条 s2 评估面（branch-audit payload / replay ABORTED / snapshot-derived inspect）滞留 | 低 | §0.4 登记非范围；P9 零消费、零评估（G8 报告 L201–202 移交面原样保留） |
| R7 | 样例 fixture 项目膨胀（yaml 体量大 → 白名单管理面大） | 低 | 3 项目 ≤ 15 文件、单文件 ≤ 150 行；白名单逐行编号（§3.19） |

### 0.7 S1–S5 预检（Plan §24 L1212–1288 逐条）

- **S1（改变 Kernel invariant）— 未触发**：P9 零 kernel 修改；producer 不直写
  WorldState（P9-INV-3/K2）；Reducer 不调 LLM（narration/dialogue 的 LLM 面 =
  显式注入 backend 的模块函数，非 kernel reducer）；Session/World 零合并；
  Prompt override 零 global read；Project 零模型 pin（K8，D-P9-08 迁移面
  显式拒绝 llm 节）。
- **S2（Public Contract 两种合理不兼容设计）— 未触发**：P9 零新 public
  contract——ProposedEffect（effects.py:197）、Authority、Scheduler（scheduler.py:550）、
  ProjectIR（schemas.py:496）、Space domain identity（space.py:112）全部复用
  冻结面；P9 新面（模块 dataclass / 迁移诊断）= 模块内部，非跨阶段 contract。
- **S3（destructive migration）— 预检通过**：T09 迁移非破坏性——v1 输入只读；
  一切丢弃 = 显式诊断（WARNING/ERROR 闭集码，零静默 drop）；自由文本规则全文
  保留于 v2 `description`（可逆：源文本零损）；object state dict 折叠保留全键
  （`k=v` 串，键序排序）。
- **S4（新重大依赖 / License）— 未触发**：零新依赖（D4/P9-INV-10）。
- **S5（Backend 无法满足 replay/checkpoint）— 未触发**：P9 零新数值 backend；
  dynamics 复用 P7 后端（经 P8 持久化面已证明 snapshot/restore/branch 能力）。

---

## §1 不变量（P9-INV-1..10）

| ID | 不变量 | 机械验证面 |
|---|---|---|
| P9-INV-1 | v1 冻结面字节不变（v1 路径集；§0.3 定义；自基线 `aab029c` 起冻结——f0a1052 与 aab029c 之间的 25 条 P1–P8 既成条目不属本不变量冻结对象） | TestP9Boundary 方法 5（sha256 清单嵌入，W7 自 aab029c 基线工作树计算）+ 门③ `git diff` |
| P9-INV-2 | Kernel 冻结面零修改；边界锚文件唯一修改模式 = EOF 纯追加 | TestP9Boundary 方法 6（子树哈希清单）+ 门③ diff |
| P9-INV-3 | K2 零直写：P9 模块全纯函数/无状态 reducer；状态变更仅经 kernel 应用面（ProposedEffect / 组件 encode-decode / lifecycle 转移） | TestP9Boundary 方法 4（AST import 闭包 + 无 `WorldState` 可变方法调用模式检查）+ A 判据行为面 |
| P9-INV-4 | K8 零推词：P9 src 字符串字面量 12 名零命中；部署字段（llm/provider/model/api_key_env/base_url）零泄漏入项目 yaml | TestP9Boundary 方法 3 + A19 |
| P9-INV-5 | 模块边界闭集：13 模块 id = Spec §40 逐字；跨模块 import ⊆ 声明 requires；`modules/` 文件闭集 = 白名单 15 文件 | A18 / A20 + TestP9Boundary 方法 1/4 |
| P9-INV-6 | 确定性：同 WorldState + 同注入（时钟/RNG/backend 脚本）→ 同效果流；零 wall-clock / 零全局 RNG | A14 / A23 + D6 |
| P9-INV-7 | 感知局部性：观察生成仅依赖观察者空间邻域（空间域内距离 + 感知半径）；零全局事件注入 | A9 / T10（`test_perception_knowledge.py::t6`） |
| P9-INV-8 | ViewState 非权威：narration 输出 = 派生数据（Spec §8.5 L626–638 MUST NOT authoritative）；修改 view 零反作用于 WorldState | A5 行为面（view 突变后世界哈希不变） |
| P9-INV-9 | LangGraph 非依赖：engine_v2 全树 import 零 langgraph/langchain（G9 条款②） | TestP9Boundary 方法 4 |
| P9-INV-10 | 零新第三方依赖：`pyproject.toml` 字节冻结、uv.lock 零变更（S4） | TestP9Boundary 方法 6 + 门③ diff |

---

## §2 冻结缝表

> 本节为 P9 消费的**全部**冻结面清单；实现波次只允许引用本节列名（+ 其
> submodule 内 `__all__` 既有成员）。锚点行号均 `aab029c` 复测。

### 2.1 core 消费子集（`src/engine_v2/core/`，32 子模块 308 导出的 P9 面）

| 文件 | 消费名（file:line） | P9 用途 |
|---|---|---|
| action_registry.py | PARAMETER_TYPES:67 / ParameterSpec:73 / DurationPolicy:102 / ActionSpec:145 / ActionRegistry:203 / validate_timing:350 / UnknownActionError:377 | §3.9 标准动作规格注册；样例项目 actions yaml 校验 |
| actions.py | ActionTypeId:71 / parse_action_type_id:98 / ActionTiming:122 / FallbackSpec:134 / ActionProposal:145 / ActionLifecycleStatus:191 / ActiveAction:207 | §3.5/§3.9 策略提案 + 执行器面 |
| action_lifecycle.py | LIFECYCLE_TRANSITIONS:119 / transition_action:257 / progress_of:367 / resume_action:383 / abort_action:449 / complete_action:491 / fail_action:526 / apply_checkpoint:580 | §3.16.2 长动作推进；A6 |
| behavior_policy.py | BehaviorPolicy:54 / PlayerPolicy:70 / run_policy_decide:83 / PolicyActorMismatchError:107 | §3.5 NpcBehaviorPolicy；G9-2 |
| knowledge.py | BeliefKind:70 / Belief:75 / KnowledgeState:94 / ObservationRecord:109 / OBSERVATIONS_COMPONENT:139 / KNOWLEDGE_COMPONENT:140 / MEMORY_COMPONENT:141 / encode_observations:155 / decode_observations:160 / encode_knowledge:165 / decode_knowledge:170 | §3.6/§3.7 感知-知识分离载体；A4/A9 |
| space.py | SPATIAL_BACKEND_KINDS:96 / SpatialDomain:112 / SpaceBackend:150 / INF_DISTANCE:170 / SpaceRegistry:175 / make_backend:229 / GraphSpace:256 / GridSpace:350 / SpaceMapping:431 / SPACES_COMPONENT:447 / encode_spaces:450 / decode_spaces:492 / entity_domain_positions:505 | §3.9 移动执行器；§3.11 HexGrid→GraphSpace；A12 |
| gameplay_mode.py | ModeOperationKind:102 / ModeOperation:109 / ModeOverlay:150 / ModeOverlayRegistry:203 / ModeInvariantError:232 / MergedModeConfiguration:241 / merge_modes:266 / is_action_available:340 / ModeChangeRequest:396 / ModeChangeResolution:439 / ModePolicy:456 / DefaultModePolicy:465 / apply_mode_change:475 / UnknownModeError:553 | §3.12 tactical overlay；A13/A15 |
| scheduler.py | TimePolicy:251 / PauseReason:274 / SchedulerOutcome:288 / WakeupHook:316 / WakeupHookRegistry:339 / enqueue_actor_wakeup:374 / scheduler_fingerprint:429 / start_action:468 / Scheduler:550 | §3.16.2 样例宿主循环；A6/A8 |
| capability.py | Capability:55 / CapabilityGrant:68 / CapabilityTable:106 / check_capability:170 / DEFAULT_NPC_CAPABILITIES:187 / CapabilityScopeError:192 | §3.5 NPC 能力面（v1 capabilities 镜像，zero_python 先例） |
| context_provider.py | ActorUnknownError:253 / ContextInvariantError:257 / ContextBuildInput:265 / ActorDecisionContext:286 / ContextProvider:319 / DefaultContextProvider:326 | §3.5 策略上下文构建 |
| components.py | ComponentTypeId:61 / parse_component_type_id:88 / ComponentConflictError:118 / ComponentSchema:127 / ComponentRegistry:144 | §3.1.3 模块组件注册面 |
| state.py | ScenarioState:102 / RuntimeState:192 / ActorWakeup:158 / WorldState:246 | 样例宿主世界构建（§6.2 conftest） |
| clock.py | LogicalClock:77 / set_logical_tick:117 / next_due_tick:137 / rebuild_runtime:151 | A7 世界时间；D6 注入时钟 |
| effects.py | EffectTypeId:98 / StateDomainId:106 / EntityTarget:163 / StateDomainTarget:178 / ProposedEffect:197 / CommittedEffect:229 | K2 效果流载体（P9 模块只产 ProposedEffect，不写状态） |
| entity.py / ids.py / revision.py / trace.py | Entity/EntityId 族（entity.py 内既有 `__all__`）、Revision 族 | 世界构建 + 事件溯源消费 |

> core 其余导出（authority/cascade/conflicts/interrupt/provenance/
> revalidation/serialization/snapshot/transaction 等）P9 **不消费**——
> 边界方法 4 的 import 闭包检查以本表 + 各文件 `__all__` 为闭集。

### 2.2 P7 dynamics 消费（`src/engine_v2/dynamics/`，8 模块 35 导出）

| 文件 | 消费名（file:line） | P9 用途 |
|---|---|---|
| backend.py | BackendMetadata:232 / WorldDynamicsBackend:302 | §3.13 `build_standard_dynamics` 返回类型 |
| host.py | DynamicsTurn:40 / run_dynamics_turn:86 | §3.16.2 sandbox 样例动力学轮 |
| llm_world.py | LLMWorldDynamics:180（+ 其 `__all__` 4 名） | A10 脚本化 LLM 动力学 |
| rule.py | WorldRule:82 / RuleDynamics:273（+ 其 `__all__` 3 名） | A11 规则动力学 |
| composite.py | CompositeDynamics:66（+ 其 `__all__` 2 名） | §3.13 复合组装（P9 零新动力学逻辑，D-P9-12） |
| toy_rigid.py / diagnostic.py | 既有 `__all__`（3 / 2 名） | A10 样例可选 toy backend；诊断码消费 |

### 2.3 v1 冻结缝三态映射表（**P9-T01 交付物**；§43.1 保留思想 / §43.2 移除假设 / §43.3 必须重写 逐项落位）

三态定义：**保留思想**（43.1，v2 重写实现）/ **移除**（43.2，v2 无对应物，
不重写）/ **重写**（43.3，v2 新实现承接）。v1 锚点行号 @ f0a1052（== HEAD
工作树，P9-INV-1）。

**文件级总表**（v1 34 `.py` + init/config 4 文件 + v1 测试）：

| v1 文件（行数） | 三态 | v2 落位 |
|---|---|---|
| `src/graph/game_graph.py`（952） | 重写（§43.3 第 1 项）+ 内含 3 项 §43.3 函数 | 函数级拆散映射，见下表 |
| `src/graph/game_state.py`（136；GameState:9 / world_rules 字段:23） | 重写（§43.3 第 2 项） | core `WorldState`（state.py:246）+ 组件化（P1 已交付）；P9 零承接文件 |
| `src/game/attributes.py`（1100） | 保留思想（43.1-4 locked/derived attribute） | `modules/attributes.py`（§3.2），函数级见 §3.2 函数级锚表 |
| `src/game/condition_eval.py`（450） | 移除（思想已由 P5 承接） | P5 `content/rule_module.py`（冻结；parse_dsl:812 / evaluate_condition:903）——43.1-3 DSL 的 v2 归宿，P9 零重写 |
| `src/game/deterministic_rules.py`（163） | 移除（思想已由 P5 承接） | P5 `BUILTIN_RULE_IDS`（rule_module.py:515，5 名 tuple，保 v1 disable 1..5 位序）+ v2 rules yaml；P9 迁移器折叠面（§3.15.2） |
| `src/game/rules.py`（225；check_action_feasibility:122 / _custom_rule_result:94） | 移除（思想已由 P5 承接） | P5 `check_action_feasibility`（rule_module.py:1169）+ v2 rules yaml 自定义条目 |
| `src/game/state_apply.py`（253） | 重写（§43.3 第 3 项） | 拆散至 `modules/{attributes,inventory,relationships,character}.py` reducer（§3.2–3.5） |
| `src/game/tick_eval.py`（512；evaluate_tick_expression:59） | 移除（思想已由 P5 承接） | tick 表达式 = v2 DSL 文法（P5 冻结） |
| `src/agents/init.py`（378；world_rules 透传:261） | 重写（项目初始化） | P5 loader（冻结）+ `modules/v1_migration.py`（T09，§3.15） |
| `src/config/loader.py`（46）+ `config/simulation.yaml`（23；llm 节:7–13 / agents 节:15–） | 移除（43.2-9 one model config；K8） | P6 deployment（冻结；deployment.py:74）；迁移器对 llm/agents 节 = incompatible 诊断（D-P9-08） |
| `src/models/*.py`（common 22 / character 26 / config 138 / events 105 / player 46 / world 43 / __init__ 38） | 重写（43.1-1 Pydantic boundary validation 思想保留） | P5 `schemas.py`（冻结）+ P9 模块 dataclass（§3.2–3.14） |
| `src/llm/parser.py`（104） | 移除（43.1-6 structured LLM parsing 思想已由 P6 承接） | P6 `llm/structured.py`（冻结） |
| `src/prompts/loader.py`（105；PHYSICS_DEFAULT_RULES:6 / ATTRIBUTE_DEFAULT_RULES:19 / ATTRIBUTE_DEFAULT_REFERENCES:29） | 移除（43.2-5 LLM physics 移除 → 编号规则无 v2 对应物；43.1-5 Jinja2 思想已由 P6 承接） | P6 `prompts/`（冻结）；disable:[N] 引用 → WARNING 诊断丢弃（§3.15.2） |
| `src/ui/{cli,renderer,status}.py`（54/237/32） | 移除（43.1-11 CLI/Web adapter separation 思想保留，实现归后） | P10/P11（§0.4 非范围） |
| `src/web/{app,main}.py`（596/124） | 移除（43.2-8 Web singleton session）+ 重写（§43.3 第 9 项 web session lifecycle） | P10/P11（§0.4 非范围） |
| `src/main.py`（240） | 移除（LangGraph runner，43.2-1） | P1 runtime（§0.4 非范围） |
| `src/__init__.py`（0）+ `src/{game,graph,llm,ui,web,models,agents,config,prompts}/__init__.py`（10 个 `__init__.py` 全列；models/__init__.py 38 行已列上行） | 冻结 | P9-INV-1 |
| v1 测试（`tests/test_*.py` 20 文件 + `char_helpers.py` + `tests/fixtures/`） | 冻结（计入 3054 基线） | T14 差分直引 v1 纯函数（§3.17） |
| `public_start/*.yaml`（1853）+ `config/simulation.yaml`（23） | 冻结（T09 只读输入） | §3.15 迁移器输入面 |

**`src/graph/game_graph.py` 函数级映射**（§43.3 第 1/5/6/7 项落位）：

| v1 函数（file:line） | 三态 | v2 承接 |
|---|---|---|
| `build_game_graph`（:115；LangGraph wiring :922–948，11 add_node + 边表） | 移除（43.2-1 固定全局 tick pipeline） | v2 宿主循环 = Scheduler（scheduler.py:550）+ 相位序（P9 样例宿主 §6.2；runtime = P1） |
| `player_intent_process`（:125） | 保留思想（43.1-7 player subconscious policy） | `modules/character.py` PlayerPolicy 面（core PlayerPolicy:70 + run_policy_decide:83） |
| `_decide_one_char`（:302） | 保留思想（单角色 LLM 决策） | `modules/character.py::NpcBehaviorPolicy`（§3.5；事件驱动 wakeup，非每 tick） |
| `characters_all_decide`（:350） | 移除（43.2-2 all NPC decide every turn） | `enqueue_actor_wakeup`（scheduler.py:374）选择性唤醒；A8 钉「非 wakeup tick 零决策调用」 |
| `tick_speed_resolve`（:375；world_rules.tick_speed 读取:389–390） | 移除（43.2-3 universal tick） | `ScenarioSpec.ticks_per_game_minute`（schemas.py:448 起）静态声明；A7 |
| `physics_resolve`（:459；PHYSICS_DEFAULT_RULES 消费:465–466） | 移除（43.2-5 LLM physics directly owns physics） | §3.13 dynamics 模块（P7 RuleDynamics/LLMWorldDynamics 复用；D-P9-12） |
| `state_apply`（:496；**omniscience 行为 :553–561**：`event_log[-10:]` 注入全体 character memory，cap 50） | 重写（§43.3 第 3 项）；omniscience 子行为 = 移除（43.2-6 global event text copied to NPC memory） | 模块 reducer（§3.2–3.5）；omniscience 零重写；T10 回归钉 `test_perception_knowledge.py::t6`（界外 NPC knowledge/memory 零变更） |
| `sensory_filter`（:591） | 移除（§43.3 第 7 项 perception pipeline 重写；43.1-9 perception/knowledge separation 思想保留） | `modules/perception.py::build_observations`（§3.6，局部空间感知） |
| `natural_attribute_delta`（:665） | 保留思想（43.1-4） | `modules/attributes.py::compute_natural_deltas`（§3.2） |
| `attribute_update`（:715；ATTRIBUTE_DEFAULT_RULES 消费:733–734） | 重写 | `modules/attributes.py` reducer 族（§3.2）；编号规则引用 → 迁移器 WARNING（§3.15.2） |
| `narrative_stylize`（:769） | 保留思想（43.1-10 narrative renderer） | `modules/narration.py::render_narrative_view`（§3.14，text 侧；非权威 P9-INV-8） |
| `post_narrative_update`（:842） | 移除（v2 后处理 = kernel lifecycle + 场景触发器） | `modules/scenario.py::check_triggers`（§3.8） |

**§43.3 九项 → v2 落位闭包核对**：game_graph.py（上表）/ GameState
（core WorldState）/ state_apply.py（模块 reducer）/ physics_resolve
（§3.13）/ characters_all_decide（wakeup 选择）/ tick_speed_resolve
（ScenarioSpec 静态）/ perception pipeline（§3.6）/ model config（P6
deployment 冻结面 + 迁移器 incompatible 诊断）/ web session lifecycle
（P10/P11 非范围，§0.4）——九项全落位，零遗漏。

**§43.1 十一条 / §43.2 九条 逐条挂接核对**（ERR-P9-04 补；Spec §43.1
L2058–2070 / §43.2 L2072–2082；「挂接」= 该条目在本 SOT 明确落位的
节/行）：

| 条目 | 文本 | 挂接 |
|---|---|---|
| 43.1-1 | Pydantic boundary validation | §2.3 总表 `src/models` 行 |
| 43.1-2 | YAML/project-file authoring | §2.4 P5 loader/content（冻结；v2 内容 YAML 唯一创作入口）+ §3.15 迁移目标 = v2 YAML |
| 43.1-3 | condition/rule DSL | §2.3 总表 `condition_eval` 行 |
| 43.1-4 | locked/derived attribute | §2.3 总表 `attributes` 行 + §3.2 |
| 43.1-5 | Jinja2 template layer | §2.3 总表 `prompts/loader` 行（P6 冻结） |
| 43.1-6 | structured LLM parsing | §2.3 总表 `llm/parser` 行（P6 冻结） |
| 43.1-7 | player subconscious policy | §3.5 player 侧（core `PlayerPolicy` behavior_policy.py:70 冻结）+ D-P9-05 |
| 43.1-8 | NPC personality/motivation/relationship data | §3.5 `CharacterRecord.personality` + §3.4 RelationshipState + §3.15.2 M-3（CharacterSpec personality:258 / relationships:261） |
| 43.1-9 | perception/knowledge separation | D-P9-06 + §3.6/§3.7 |
| 43.1-10 | narrative renderer | §3.14 narration 模块（text 侧；image 侧 P10） |
| 43.1-11 | CLI/Web adapter separation | §2.3 总表 `src/ui` 行（实现归 P10/P11，§0.4） |
| 43.2-1 | LangGraph 固定全局 tick pipeline | §2.3 总表 `src/main.py` 行 + 函数表 `build_game_graph` 行 + G9-16 |
| 43.2-2 | all NPC decide every turn | 函数表 `characters_all_decide` 行 + D-P9-05 + G9-8 |
| 43.2-3 | universal tick | 函数表 `tick_speed_resolve` 行 |
| 43.2-4 | fixed six action types | §3.9 标准动作集说明 + §7.3 §11 行 |
| 43.2-5 | LLM physics | §2.3 总表 `prompts/loader` 行 + D-P9-12 |
| 43.2-6 | global event text copied to NPC memory | D-P9-06 + T10（v1 锚 game_graph.py:553–561） |
| 43.2-7 | global GameState 包含全部 runtime/transient/presentation | §2.3 总表 `game_state` 行——P1 WorldState 组件化（state.py:246）已使假设失效，P9 零承接文件 |
| 43.2-8 | Web singleton session | §2.3 总表 `src/web` 行 + §0.4 |
| 43.2-9 | one model config for all roles | §2.3 总表 `src/config` 行 + D-P9-08/09 |

20 条全挂接（43.1 = 11/11、43.2 = 9/9）。

### 2.4 P5 content 消费（`src/engine_v2/content/`，冻结）

| 文件 | 消费名（file:line） | P9 用途 |
|---|---|---|
| loader.py | LAYOUT_REQUIRED:46 / LAYOUT_OPTIONAL:50–60 / read_yaml_file / ProjectLoadResult / load_project / detect_v1_shape:242（`__all__` 6 名） | §3.15 迁移输出经 `load_project` 验证；`detect_v1_shape` = 迁移器入口判别（v1 形状输入确认） |
| module_graph.py | Requirement / RequirementKind / ModuleEdge / ModuleGraph / parse_requirement / build_module_graph / topological_order / find_cycles / check_unsatisfied_requires / check_module_versions / detect_conflicts（`__all__` 11 名） | Spec §41 显式 requires + 依赖图检查（A18 t4 requires 无环；项目侧 modules 声明面） |
| rule_module.py | parse_dsl:812 / evaluate_condition:903 / check_action_feasibility:1169 / BUILTIN_RULE_IDS:515 / DslContext / ActionInput / FeasibilityResult / DslRng（`__all__` 43 名之 P9 面） | §3.2 锁条件求值；§3.8 触发器条件；§3.9 动作可行性；A17 差分面 |
| schemas.py | DIAGNOSTIC_CODES:112–133（18 码，含 LLMSIM_PROJECT_FORMAT_V1:116 / LLMSIM_MODULE_*:121–124 / LLMSIM_DSL_PARSE:127）/ ENGINE_VERSION:68 / WorldSpec:169 / ObjectSpec:187（state: str\|None :199 / properties 开放 dict）/ AttributeSpec:203 / PlayerSpec:227 / CharacterSpec:250（personality:258 / relationships:261 / speech_examples:262 / attributes:263）/ ModuleGraphNode:365 / GameplayModeSpec:386 / ScenarioSpec:448（id/max_ticks:453 起）/ RawProject:461 / ProjectManifest:481（schema_version:489 = Literal["2"]）/ ProjectIR:496（16 字段 :505–520）/ Diagnostic:523 | 迁移目标形状；A17 IR 同构面；G9 样例项目加载 |
| project_ir.py / validator.py / cli.py | `__all__` 6 / 8 / 4 名（validator：ValidationResult / validate_project / check_duplicate_ids / check_references / check_authority_conflicts / check_deployment_leakage / check_dsl_parses / sort_diagnostics） | `validate_project` 零 ERROR = 迁移成功判据（A16）；`check_deployment_leakage` 与 D-P9-08 协同（K8 双保险） |

### 2.5 P6 llm / prompts 消费（冻结）

| 文件 | 消费名（file:line） | P9 用途 |
|---|---|---|
| llm/adapter.py | MonotonicClock:47 / FixedMonotonicClock:71 / InferenceRequest:98 / InferenceResponse:132 / InferenceBackend:150 / FakeInferenceBackend:296 / calls:326 / generate:330 | §3.5/§3.10 策略与对话的脚本化 backend（A2/A1/G9-10）；D6 注入时钟 |
| llm/deployment.py | DeploymentProfile:74 / load_deployment:122 / resolve_deployment_path:115 | §3.13 动力学 backend 组装的部署输入面（P9 模块自身零部署解析） |
| prompts/registry.py | TemplateDocument / TemplateStore / RenderResult / render_template:116 / validate_template_ref（`__all__` 5 名） | §3.5 策略 prompt 模板面（character_scene scope） |

### 2.6 P8 persistence 消费（冻结；P9 面 = 1 处）

| 文件 | 消费名（file:line） | P9 用途 |
|---|---|---|
| persistence/snapshot.py | PersistenceSnapshot:52 / to_persistence_snapshot:104 / dump_persistence_snapshot:133 / load_persistence_snapshot:143 / check_persistence_versions:176 | A24：P9 样例世界经 P8 冻结快照面 round-trip（证明 P9 组件数据 JSON-clean + 版本兼容） |

> P8 devtools（cli/intervention/trace_query 19 导出）P9 **不消费**——
> 边界方法 4 闭集不含 devtools（P9 模块零 devtools import）。

### 2.7 边界锚文件（唯一可修改的既有测试文件）

- 文件：`tests/engine_v2/core/test_import_boundary.py`，**2071 行 @ HEAD**。
- 既有块：P4_LLM_PROVIDER_BLACKLIST :225–240（12 名）；TestP6Boundary :959；
  P7_SRC_SUBMODULES :1240 / P7_TEST_FILES :1253 / TestP7Boundary 6 方法
  :1388/:1469/:1478/:1527/:1585/:1617；P8_SRC_SUBMODULES :1638 /
  TestP8Boundary :1777。
- P9 块：**L2071 后 EOF 纯追加**（D5/P9-INV-2）；`TestP9Boundary` 6 方法
  表见 §3.20；估算 +350–450 行（R4）。
- 追加块自含（不引用文件内 P4–P8 私有名的新语义扩展——黑名单 12 名常量
  复用既有 P4_LLM_PROVIDER_BLACKLIST，零重复定义）。

### 2.8 P5 参考镜像（T09 同构基线）

- `tests/fixtures/v2_project_zero_python/`（5 文件，§0.3）= test_empty.yaml
  的 P5 手工镜像；game.yaml 逐节结构（manifest/scenario/player/…）= 迁移器
  输出形状规范（§3.15.2 映射表以之为形状基线）。
- P5 偏差台账 D-01（objects 未镜像）→ P9 迁移器必须正确承接
  objects→items（§3.15.2 规则 M-4；A17 同构面覆盖 objects 差异披露）。

### 2.9 占位文件（字节冻结五件套）

| 文件 | 行数 | docstring | P9 处置 |
|---|---|---|---|
| `src/engine_v2/modules/__init__.py` | 9 | 「占位，Phase 9 填充」（docstring 列 9 模块名，**缺 actions/dialogue/dynamics/narration 4 名**——ERR-P9-03） | 字节冻结（P8 D8 先例：填充包后占位 docstring 不更新——persistence/__init__.py 8 行「占位，Phase 8 填充」、dynamics/__init__.py 9 行「占位，Phase 7 填充」为活证）；P9 一律经 submodule 路径 import（`engine_v2.modules.<name>`） |
| `src/engine_v2/presentation/__init__.py` | 8 | 「占位，Phase 10 填充」 | 字节冻结（P10 面） |
| `src/engine_v2/context/__init__.py` | 8 | 「占位，Phase 4 填充」 | 字节冻结（P4 遗留文案；P9 不消费） |
| `src/engine_v2/adapters/__init__.py` | 8 | 「占位，Phase 8/10/11 填充」 | 字节冻结（P10/P11 面） |
| `src/engine_v2/runtime/__init__.py` | 9 | 「占位，Phase 1/2 填充」 | 字节冻结（P1 面） |

### 2.10 冻结测试侧缝

- `tests/engine_v2/{core,content,llm,prompts,dynamics,persistence,plugins}/`
  全部文件字节不变（P9-INV-2）；唯一例外 = §2.7 锚文件 EOF 纯追加。
- v1 测试目录（`tests/test_*.py` 等）字节不变（P9-INV-1）；T14 差分测试
  **import** v1 纯函数（只读消费，非修改）。
- `tests/fixtures/` 既有 7 项目目录（v2_deployment / v2_deployment_p7 /
  v2_plugin_local / v2_project_broken / v2_project_llm / v2_project_p7 /
  v2_project_zero_python）字节不变；P9 新增 3 项目目录（§3.19 行 31–45）。

---

## §3 模块设计

### 3.0 包树与导入闭集

```text
src/engine_v2/modules/
├── __init__.py         # 既有 9 行占位，字节冻结（§2.9）；不 re-export
├── base.py             # 模块公共面（§3.1）
├── attributes.py       # T02（§3.2）
├── inventory.py        # T03（§3.3）
├── relationships.py    # T04（§3.4）
├── character.py        # T05（§3.5）
├── perception.py       # T06（§3.6）
├── knowledge.py        # T06/T10（§3.7）
├── scenario.py         # T07（§3.8）
├── actions.py          # T08（§3.9）
├── dialogue.py         # T11 面（§3.10）
├── space.py            # T13 面（§3.11）
├── tactical.py         # T13 面（§3.12）
├── dynamics.py         # T12 面（§3.13，P7 复用桥）
├── narration.py        # T11 面（§3.14）
└── v1_migration.py     # T09（§3.15；13 模块之外的包基础设施）
```

**导入闭集**（边界方法 4 AST 检查基准；每模块 `MODULE_REQUIRES` 见 §3.1.2）：

```text
允许 import 根 = stdlib + pydantic
               + engine_v2.core.*      （§2.1 消费子集）
               + engine_v2.content.*   （§2.4）
               + engine_v2.llm.*       （§2.5）
               + engine_v2.prompts.*   （§2.5）
               + engine_v2.dynamics.*  （§2.2）
               + engine_v2.persistence.snapshot（§2.6，仅测试侧 A24 经 conftest）
               + engine_v2.modules.<name>（仅 <name> ∈ 本模块 MODULE_REQUIRES）
禁止 = engine_v2.{presentation,context,adapters,runtime,plugins,devtools}
       + langgraph + langchain + 12 名推词（D7）+ 任何其它路径
```

### 3.1 模块公共面（`modules/base.py`；导出 5 名）

#### 3.1.1 `__all__`（逐字按序）

```python
__all__ = [
    "ModuleIdentity",
    "OFFICIAL_MODULE_IDS",
    "OFFICIAL_MODULE_VERSION",
    "parse_module_id",
    "UnknownModuleIdError",
]
```

#### 3.1.2 名/形/语义表

| 名 | 形 | 语义 |
|---|---|---|
| `ModuleIdentity` | frozen dataclass：`module_id: str`、`version: str`、`requires: tuple[str, ...]` | 官方模块身份三元组；每模块模块级常量 `IDENTITY: Final[ModuleIdentity]` 持有 |
| `OFFICIAL_MODULE_IDS` | `Final[tuple[str, ...]]`，13 名按 Spec §40（L1951–1963）逐字序：`llmsim-standard-attributes` / `-inventory` / `-character` / `-knowledge` / `-perception` / `-relationships` / `-space` / `-actions` / `-scenario` / `-dialogue` / `-tactical` / `-dynamics` / `-narration` | 官方模块 id 闭集（P9-INV-5）；id 语法 = Spec §40 原文（`llmsim-standard-<name>`） |
| `OFFICIAL_MODULE_VERSION` | `Final[str] = "1"` | 统一初始版本；满足 P5 版本文法 `^\d+(\.\d+)*$`（P5 D-P5-06） |
| `parse_module_id` | `(text: str) -> str`（校验后原样返回；失败抛 `UnknownModuleIdError`） | 文法 `llmsim-standard-` 前缀 + 小写蛇形尾段（字符类 `[a-z][a-z0-9_]*`）；零裸 `\b`（D3） |
| `UnknownModuleIdError` | `ValueError` 子类 | 非官方 id / 文法违例 |

各模块 `MODULE_REQUIRES`（声明式 requires，Spec §41 模块侧；kernel 包
core/content/llm/prompts/dynamics 为「冻结 kernel 根」，不计入 requires）：

| 模块 | MODULE_REQUIRES | 理由 |
|---|---|---|
| attributes | `()` | 自足 |
| inventory | `("llmsim-standard-attributes",)` | 负重上限读 strength 属性（v1 STRENGTH_TO_KG_FACTOR:50.0，rules.py:9） |
| character | `("llmsim-standard-attributes",)` | 角色记录含属性表 |
| knowledge | `("llmsim-standard-perception",)` | 消费 ObservationRecord 类型 |
| perception | `("llmsim-standard-space",)` | 距离查询经空间域 |
| relationships | `()` | 自足 |
| scenario | `("llmsim-standard-actions",)` | 触发器 firing 产动作提案/效果 |
| actions | `("llmsim-standard-space", "llmsim-standard-inventory")` | 移动经空间域；拾取/放下经物品 |
| dialogue | `("llmsim-standard-character", "llmsim-standard-relationships")` | 对话方 = 角色；结果回写关系 |
| space | `()` | 自足（kernel SpaceRegistry 为 kernel 根） |
| tactical | `("llmsim-standard-actions", "llmsim-standard-space")` | 战术模式限动作集 + 战术移动 |
| dynamics | `()` | P7 复用（dynamics 包 = 冻结 kernel 根） |
| narration | `()` | 自足（纯派生） |

#### 3.1.3 注册协议（无状态纪律）

P9 模块 = **纯函数 + Protocol + dataclass 库**（P7/P8 同风格）：零全局状态、
零模块级可变对象。注册 = 显式函数，把模块行为接入 kernel 注册表（调用方 =
测试 conftest 宿主或 P1 runtime；P9 无宿主实现）：

- 动作：`modules/actions.py::register_standard_actions(registry, space)`（§3.9）
- 空间：`modules/space.py::register_standard_space(registry, spec)`（§3.11）
- 模式：`modules/tactical.py::build_tactical_overlay(...)` 返回值交
  `ModeOverlayRegistry`（§3.12）
- 策略：`modules/character.py::build_npc_policy(record, backend, ...)`
  返回值挂接 `run_policy_decide`（§3.5）
- 组件：P9 模块**不注册新组件 schema**——全部落位既有冻结组件面
  （knowledge 三组件 / spaces 组件 / 属性与关系 = 实体 data 面经
  components.py 既有注册路径由宿主声明；P9 只产数据值）

### 3.2 attributes 模块（`modules/attributes.py`；T02；导出 11 名）

**来源**：v1 `src/game/attributes.py`（1100 行；本表即 §2.3 所指函数级锚）。保留
43.1-4（locked/derived attribute 思想）；`_LCParser`/`_ComputeParser`
（v1 :200/:446）私有解析器**不移植**——锁条件/派生计算改经 P5 冻结
DSL（`parse_dsl` :812 / `evaluate_condition` :903；43.1-3 思想的 v2 归宿）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "AttributeField",
    "AttributeEvent",
    "LockedAttributeError",
    "clamp_value",
    "apply_delta",
    "apply_new_value",
    "compute_natural_deltas",
    "evaluate_lock_condition",
    "take_attribute_snapshot",
    "summarize_attributes_for_prompt",
    "derive_attributes",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `AttributeField` | frozen dataclass：`name: str`、`value: float`、`min: float`、`max: float`、`locked: bool = False`、`hidden: bool = False`、`natural_delta_per_tick: float = 0.0` | v1 attr dict（min/max/locked/hidden/natural_delta_per_minute/value/name 键）的冻结 dataclass 化（零可变） |
| `AttributeEvent` | frozen dataclass：`actor_id: str`、`name: str`、`old: float`、`new: float`、`reason: str`、`tick: int` | 属性变更事件（kernel 事件流载荷；provenance 由 kernel 补） |
| `LockedAttributeError` | `ValueError` 子类（message 含属性名 + 「locked」） | v1 `_LockedConditionError`（:170）对应物 |
| `clamp_value` | `(value: float, field: AttributeField) -> float` | min/max 钳制（v1 `_clamp`:10 对齐） |
| `apply_delta` | `(fields: Mapping[str, AttributeField], actor_id: str, name: str, delta: float, tick: int) -> tuple[dict[str, AttributeField], tuple[AttributeEvent, ...]]` | 纯 reducer：locked 检查（v1 `_apply_delta`:24–25 对齐）→ 钳制 → 新 Mapping；不修改入参 |
| `apply_new_value` | 同形（`delta` 换 `value: float`） | v1 `_apply_new_value`:36–37 对齐 |
| `compute_natural_deltas` | `(fields: Mapping[str, AttributeField], ticks_elapsed: int) -> Mapping[str, float]` | v1 `apply_natural_attribute_deltas`:113 + `natural_attribute_delta`（game_graph.py:665）思想；`natural_delta_per_tick * ticks_elapsed`，零 LLM |
| `evaluate_lock_condition` | `(fields, actor_id: str, name: str, condition_dsl: str, tick: int) -> bool` | 锁条件经 P5 `parse_dsl` + `evaluate_condition`（注入 `DslRng`）；结构/语义错误 = 诊断路径（不吞：`DslEvalError` 透传） |
| `take_attribute_snapshot` | `(fields, actor_id: str, name: str, value: float) -> tuple[dict[str, AttributeField], tuple[AttributeEvent, ...]]` | v1 `_exec_snapshot`:851 对应：快照属性创建 = `hidden=True, locked=True`（v1 :866 对齐） |
| `summarize_attributes_for_prompt` | `(fields: Mapping[str, AttributeField], actor_id: str) -> str` | v1 `summarize_attributes_for_prompt`:1058 对应；hidden 属性零文本泄漏；确定性键序（sorted） |
| `derive_attributes` | `(fields: Mapping[str, AttributeField], actor_id: str, spec: Mapping[str, str]) -> Mapping[str, AttributeField]` | 派生属性：`spec = {派生名: DSL 表达式}`，经 P5 `evaluate_condition` 对 TruthyNode 化表达式求值（v1 `_ComputeParser`:446 思想的 DSL 化）；派生结果不反向写源字段 |

**docstring 纪律**：每函数 docstring 首行 = v1 锚（`对齐 v1
src/game/attributes.py:NN`）+ v2 差异（若有）；零裸 `\b`（D3）。

### 3.3 inventory 模块（`modules/inventory.py`；T03；导出 7 名）

**来源**：v1 objects（`src/models/world.py` ObjectSpec 族）+ v1 规则
`rules.py` 编号 1–5（负重 :169 / 门锁 :190 等）；43.2-4「fixed six action
types」移除 → 物品操作 = 项目声明动作（P9 标准集 §3.9）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "ItemState",
    "CarryLimit",
    "CarryCheck",
    "can_carry",
    "apply_pickup",
    "apply_drop",
    "item_summary",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `ItemState` | frozen dataclass：`id: str`、`name: str`、`description: str = ""`、`object_type: str = ""`、`position: Mapping[str, int] \| None`、`state: str \| None = None`、`properties: Mapping[str, object]` | v1 object dict → v2 `ObjectSpec`（schemas.py:187）形状对齐；`state` = 扁平 str（§3.15.2 M-4 折叠规范）；`properties` 开放（D-P5-05 豁免） |
| `CarryLimit` | frozen dataclass：`max_kg: float` | 负重上限 = `strength * 50.0`（v1 `STRENGTH_TO_KG_FACTOR`，rules.py:9；经 requires 读 attributes 模块 `AttributeField`） |
| `CarryCheck` | frozen dataclass：`allowed: bool`、`reason: str`、`used_kg: float`、`limit_kg: float` | v1 规则 3（strength_vs_weight）判定结果 |
| `can_carry` | `(items: Mapping[str, ItemState], actor_id: str, target: str, limit: CarryLimit) -> CarryCheck` | 纯判定（v1 rules.py:169 对齐口径） |
| `apply_pickup` | `(items, positions: Mapping[str, Mapping[str, int]], actor_id: str, item_id: str, tick: int) -> tuple[dict[str, ItemState], dict[str, Mapping[str, int]], tuple[...]]` | 物品位置 → 角色携带（零直写：返回新 Mapping + 事件） |
| `apply_drop` | 同形镜像 | 携带 → 地面位置 |
| `item_summary` | `(items: Mapping[str, ItemState], scope_id: str) -> str` | prompt 文本（确定性键序；state 扁平串原样呈现） |

### 3.4 relationships 模块（`modules/relationships.py`；T04；导出 5 名）

**来源**：v1 角色 yaml `relationships`（dict id→float，如
whisperheads.yaml:373）+ 43.1-8（NPC personality/motivation/relationship
data 保留）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "RelationshipState",
    "RelationshipEvent",
    "init_relationships",
    "adjust_relationship",
    "relationship_summary",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `RelationshipState` | frozen dataclass：`holder_id: str`、`target_id: str`、`affinity: float`（闭区间 [-1.0, 1.0]） | v1 float 直存 → v2 显式夹取（v1 无夹取 = 偏差披露，§8.4 DEV-P9-05） |
| `RelationshipEvent` | frozen dataclass：`holder_id`、`target_id`、`old`、`new`、`reason`、`tick` | 关系变更事件 |
| `init_relationships` | `(entries: Mapping[str, float], holder_id: str) -> tuple[RelationshipState, ...]` | v1 dict → 有序元组（sorted by target_id，确定性） |
| `adjust_relationship` | `(states: Sequence[RelationshipState], holder_id: str, target_id: str, delta: float, reason: str, tick: int) -> tuple[tuple[RelationshipState, ...], RelationshipEvent]` | 纯调整 + 夹取；目标缺席 = 新建（affinity 初值 0.0） |
| `relationship_summary` | `(states: Sequence[RelationshipState], holder_id: str) -> str` | prompt 文本（sorted；零隐藏面） |

### 3.5 character 模块（`modules/character.py`；T05；导出 5 名）

**来源**：v1 `_decide_one_char`（game_graph.py:302，保留思想）+ v1
`player_intent_process`（:125，43.1-7 player subconscious policy）+ v1
character yaml 形状（CharacterSpec:250 冻结面已承接）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "CharacterRecord",
    "PolicyPromptContext",
    "NpcBehaviorPolicy",
    "build_character_record",
    "build_npc_policy",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `CharacterRecord` | frozen dataclass：`character_id: str`、`name: str`、`personality: Mapping[str, str]`（traits/motivations/speech_style/background）、`attributes: Mapping[str, AttributeField]`、`position: Mapping[str, int] \| None` | v1 character 条目 → 冻结记录（经 `CharacterSpec` 校验后构建） |
| `PolicyPromptContext` | frozen dataclass：`actor_id: str`、`scene_text: str`、`persona_text: str`、`constraints: tuple[str, ...]` | 策略 prompt 上下文（渲染经 P6 `render_template` 冻结面） |
| `NpcBehaviorPolicy` | 实现 core `BehaviorPolicy`（behavior_policy.py:54）：`decide(ctx) -> ActionProposal` | 角色策略 = **纯函数对象**：内部经注入的 `InferenceBackend`（Protocol，adapter.py:150）取回应 → 解析为 `ActionProposal`（actions.py:145）；零直写、零全局 RNG；**仅在 wakeup 时被调用**（43.2-2 移除面的实现保证，A8） |
| `build_character_record` | `(spec: CharacterSpec) -> CharacterRecord` | 校验后构建（重复 id / 文法错误 → P5 诊断路径） |
| `build_npc_policy` | `(record: CharacterRecord, backend: InferenceBackend, prompt_store: TemplateStore, clock: MonotonicClock) -> NpcBehaviorPolicy` | 工厂；backend 为 Protocol 注入（测试 = `FakeInferenceBackend`，adapter.py:296；真机 = P6 后端，非 P9 面） |

**player 侧**：core `PlayerPolicy`（behavior_policy.py:70）为冻结面，P9
不新建 player 策略类——player subconscious（43.1-7）= 宿主以
`PlayerPolicy` 挂接（样例宿主 §6.2 演示）。

### 3.6 perception 模块（`modules/perception.py`；T06；导出 4 名）

**来源**：v1 `sensory_filter`（game_graph.py:591，§43.3 第 7 项重写）；
43.1-9（perception/knowledge separation 思想）；**43.2-6（global event
text copied to NPC memory）移除——本模块零全局事件消费**（P9-INV-7）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "PerceptionRange",
    "ObservationSource",
    "PerceptionResult",
    "build_observations",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `PerceptionRange` | frozen dataclass：`sight_m: float`、`hearing_m: float` | 观察者感知半径（来源 = 宿主从 `PlayerSpec.capabilities`（schemas.py:227）/ NPC 能力表（capability.py:106）投影） |
| `ObservationSource` | frozen dataclass：`observer_id: str`、`domain: str`（空间域 id）、`tick: int` | 一次感知批次的来源标记 |
| `PerceptionResult` | frozen dataclass：`source: ObservationSource`、`records: tuple[ObservationRecord, ...]`（core knowledge.py:109） | 感知输出 = 仅 `ObservationRecord` 元组（零 knowledge 直写） |
| `build_observations` | `(world_positions: Mapping[str, Mapping[str, int]], observers: Mapping[str, PerceptionRange], entities: Mapping[str, Mapping[str, object]], source: ObservationSource) -> PerceptionResult` | 纯函数：每观察者 × 每可感知实体，经空间域 `distance`（SpaceBackend:150）判定 ≤ 半径 → `ObservationRecord`（sight/hearing 分类）；**输入不含 event_log / 全局状态**（签名级保证 P9-INV-7） |

### 3.7 knowledge 模块（`modules/knowledge.py`；T06/T10；导出 4 名）

**来源**：v1 memory 注入行为（game_graph.py:553–561，cap 50）→ v2 =
**仅经 ObservationRecord 的 belief 更新**；载体 = core 冻结知识三组件
（OBSERVATIONS_COMPONENT:139 / KNOWLEDGE_COMPONENT:140 /
MEMORY_COMPONENT:141）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "BeliefEvent",
    "apply_observations",
    "memory_append",
    "knowledge_summary",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `BeliefEvent` | frozen dataclass：`actor_id: str`、`kind: BeliefKind`（core:70）、`subject: str`、`text: str`、`tick: int` | belief 更新事件 |
| `apply_observations` | `(knowledge: KnowledgeState, result: PerceptionResult) -> tuple[KnowledgeState, tuple[BeliefEvent, ...]]` | 纯 reducer：ObservationRecord → Belief 集（新增/强化，不衰减）；返回新 `KnowledgeState`（core:94）；**无 observations 输入 = 零变更**（T10 回归的模块侧保证） |
| `memory_append` | `(memory: tuple[str, ...], entry: str, cap: int = 50) -> tuple[str, ...]` | memory 追加 + cap（v1 :559 cap 50 对齐；sorted 无——保时序，tuple 追加） |
| `knowledge_summary` | `(knowledge: KnowledgeState, actor_id: str) -> str` | prompt 文本（确定性序） |

**T10 回归面**：`test_perception_knowledge.py::t6` 断言——世界事件发生
（宿主注入事件流）后，界外 NPC 的 KNOWLEDGE/MEMORY 组件**逐字节不变**
（v1 对照行为 = 全员 memory 注入 `event_log[-10:]`，game_graph.py:553–561；
v2 期望差 = 本条钉死）。

### 3.8 scenario 模块（`modules/scenario.py`；T07；导出 3 名）

**来源**：v1 无对应物（v2 新模块，Spec §40）；触发器条件 = P5 冻结 DSL
（43.1-3 思想的 v2 归宿）；v1 `post_narrative_update`（:842）的后处理
职责由本模块 + kernel lifecycle 承接。

#### `__all__`（逐字按序）

```python
__all__ = [
    "ScenarioTrigger",
    "TriggerFiring",
    "check_triggers",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `ScenarioTrigger` | frozen dataclass：`id: str`、`condition_dsl: str`、`action_type: ActionTypeId \| None`、`effect_description: str`、`once: bool = True`、`priority: int = 0` | 场景触发器声明（宿主从 ScenarioSpec 扩展区/项目 modules 声明构建） |
| `TriggerFiring` | frozen dataclass：`trigger_id: str`、`tick: int`、`proposed: ProposedEffect \| None`（core effects.py:197）、`action_proposal: ActionProposal \| None` | 一次 firing = 至多一效果或一提案（K2：均待 kernel 裁决） |
| `check_triggers` | `(triggers: Sequence[ScenarioTrigger], fired_once: frozenset[str], world_facts: Mapping[str, object], tick: int, rng: DslRng) -> tuple[TriggerFiring, ...]` | 纯函数：逐触发器 `parse_dsl`（:812）+ `evaluate_condition`（:903，注入 rng）；`once=True` 且已触发 = 跳过；firing 序 = (priority 降, id 升) 确定性 |

### 3.9 actions 模块（`modules/actions.py`；T08；导出 5 名）

**来源**：v1 固定六动作类型（43.2-4 移除）→ v2 = **项目声明动作 + P9
标准执行器库**；执行器 = 纯函数对象（K2：产 ProposedEffect/状态变更
提案，kernel 应用）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "STANDARD_ACTION_IDS",
    "ActionExecutor",
    "ExecutorResult",
    "MoveExecutor",
    "register_standard_actions",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `STANDARD_ACTION_IDS` | `Final[tuple[str, ...]] = ("move", "talk", "inspect", "pickup", "drop", "wait")` | 标准动作 id 参考集（≠ v1 固定六类型：此处为**执行器库**覆盖集，项目可用 actions yaml 增删/覆盖；43.2-4 移除的是「固定」，不是「存在」） |
| `ActionExecutor` | Protocol：`execute(proposal: ActionProposal, world: WorldState, tick: int) -> ExecutorResult` | 执行器协议（纯函数对象；`world` 只读） |
| `ExecutorResult` | frozen dataclass：`committed: tuple[ProposedEffect, ...]`、`failure: str \| None`、`duration_ticks: int = 0` | 执行结果（`duration_ticks > 0` = 长动作，宿主经 `start_action`（scheduler.py:468）+ DurationPolicy 推进） |
| `MoveExecutor` | 实现 `ActionExecutor`：目标位置经 `SpaceRegistry`（space.py:175）距离/邻接校验；越界/不可达 → `failure`（对齐 v1 移动语义，零 LLM） | A14 确定性动作主面 |
| `register_standard_actions` | `(registry: ActionRegistry, space: SpaceRegistry, executors: Mapping[str, ActionExecutor]) -> None` | 把标准动作 `ActionSpec`（action_registry.py:145）+ 执行器挂入注册表（幂等：重复注册同 id 覆盖并记诊断） |

> 样例项目 `actions/*.yaml`（§3.16）经 P5 冻结 `check_dsl_parses` 校验；
> 执行器与 yaml 的绑定 = 宿主按 action id 查 `executors`（缺失 → 诊断，
> 不静默）。

### 3.10 dialogue 模块（`modules/dialogue.py`；T11 面；导出 3 名）

**来源**：v1 对话 = LLM 直出（`_decide_one_char` 族）→ v2 = 结构化对话
回合（Policy 提案 → 执行器 → 关系回写），43.1-7 思想保留。

#### `__all__`（逐字按序）

```python
__all__ = [
    "DialogueResult",
    "dialogue_relationship_delta",
    "run_dialogue",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `DialogueResult` | frozen dataclass：`speaker_id: str`、`respondent_id: str`、`utterance: str`、`response: str`、`relationship_delta: float`、`tick: int` | 一次对话回合的冻结结果 |
| `dialogue_relationship_delta` | `(utterance: str, response: str) -> float` | 确定性规则式增量（回应含感谢/致歉类标记词 → 正增量；威胁类 → 负增量；闭集词表模块常量，零 LLM）；供 A3 |
| `run_dialogue` | `(world: WorldState, speaker_id: str, respondent_id: str, utterance: str, backend: InferenceBackend, policy: NpcBehaviorPolicy, tick: int) -> DialogueResult` | 对话回合：经注入 backend 取回应（脚本化；A1 主面）→ `dialogue_relationship_delta` → 返回结果（关系**落位**由宿主经 `adjust_relationship` 完成，K2） |

### 3.11 space 模块（`modules/space.py`；T13 面；导出 4 名）

**来源**：Spec §40 space 模块；kernel `GridSpace`（space.py:350，方格
4 邻 + 曼哈顿，冻结）不含 hex → G9「Grid/**Hex-like** Space」的 hex 面
= 本模块纯函数生成 hex 邻接，映射入冻结 `GraphSpace`（space.py:256）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "HexGrid",
    "hex_adjacency",
    "distance_between",
    "register_standard_space",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `HexGrid` | frozen dataclass：`cols: int`、`rows: int`、`offset: str = "odd-r"`（闭集 `odd-r`/`even-r`） | hex 网格参数（轴向 = offset 行坐标惯例；文法违例 → `ValueError`） |
| `hex_adjacency` | `(grid: HexGrid) -> tuple[tuple[str, str], ...]` | 纯函数：节点 id = `hex_<c>_<r>`；6 邻（offset 修正；出界裁剪）→ 对称边表（sorted 去重，确定性）；供 `GraphSpace(nodes, edges)` 构造（A12 主面） |
| `distance_between` | `(grid: HexGrid, a: str, b: str) -> int` | hex 立方坐标步数（纯函数；非网格节点 → `KeyError`） |
| `register_standard_space` | `(registry: SpaceRegistry, domain: str, backend: SpaceBackend) -> None` | 宿主把 `GraphSpace`（hex 邻接构造）或 `GridSpace`（方格对照）注册入域（幂等） |

### 3.12 tactical 模块（`modules/tactical.py`；T13 面；导出 4 名）

**来源**：Spec §40 tactical 模块 + Spec §25 GameplayMode/GameplayContext
（L1396–1452）冻结面
（gameplay_mode.py）；v1 无对应物（v2 新模块）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "TACTICAL_ACTION_IDS",
    "TacticalOverlaySpec",
    "build_tactical_overlay",
    "TacticalModePolicy",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `TACTICAL_ACTION_IDS` | `Final[tuple[str, ...]] = ("move", "attack", "reload", "take_cover", "wait")` | 战术模式动作集（参考集；项目可经 `GameplayModeSpec`（schemas.py:386）覆盖） |
| `TacticalOverlaySpec` | frozen dataclass：`mode_id: str`、`available_actions: tuple[str, ...]`、`description: str = ""` | overlay 声明 |
| `build_tactical_overlay` | `(spec: TacticalOverlaySpec) -> ModeOverlay`（core:150） | 纯构建：`available_actions` 经 `parse_action_type_id`（actions.py:98）校验 |
| `TacticalModePolicy` | 实现 core `ModePolicy`（gameplay_mode.py:456）：战术→探索转移允许；探索→战术允许（宿主 `ModeChangeRequest`）；战术内子模式转移拒绝 | 供 `apply_mode_change`（:475）；A15 主面 |

### 3.13 dynamics 模块（`modules/dynamics.py`；T12 面；导出 2 名）

**来源**：Spec §40 dynamics 模块 = **P7 复用桥**（D-P9-12：零新动力学
逻辑；P7 8 模块 35 导出冻结面见 §2.2）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "DynamicsBinding",
    "build_standard_dynamics",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `DynamicsBinding` | frozen dataclass：`backend: WorldDynamicsBackend`（backend.py:302）、`turn: Callable[[DynamicsTurn], ...]`（host.py:40/86 宿主签名） | 绑定 = backend + 轮驱动闭包（宿主注入 authority 裁决面） |
| `build_standard_dynamics` | `(rule_backend: RuleDynamics, llm_backend: LLMWorldDynamics, weight: float = 0.5) -> DynamicsBinding` | 组装 P7 `CompositeDynamics`（composite.py:66）：rule 优先、llm 补位（权重 = 复合仲裁参数）；**P9 不实现任何 dynamics 子类** |

### 3.14 narration 模块（`modules/narration.py`；T11 面；导出 4 名）

**来源**：v1 `narrative_stylize`（game_graph.py:769，43.1-10 narrative
renderer 思想保留）；Spec §8.5（L626–638）ViewState MUST NOT
authoritative；Spec §32 text/image 并行——**P9 仅 text 侧**（D-P9-13，
image = P10）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "NarrativeFrame",
    "NarrativeStyle",
    "NarrativeView",
    "render_narrative_view",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `NarrativeFrame` | frozen dataclass：`tick: int`、`speaker_id: str`、`text: str`、`mood: str = ""` | 单帧叙述（宿主从事件流/对话结果投影） |
| `NarrativeStyle` | frozen dataclass：`style_description: str`、`style_example: str = ""` | v1 `narrative_style` 节（test_empty.yaml:152 起）形状对齐；`ScenarioSpec.narrative_style`（schemas.py:448 起）承接 |
| `NarrativeView` | TypedDict（total=False）：`tick: int`、`scene_text: str`、`frames: list[dict]`、`actors_visible: list[str]`、`clock: dict` | **narrative-ready ViewState** = 纯 dict（JSON-clean；`json.dumps` 零失败，A5 断言） |
| `render_narrative_view` | `(world: WorldState, frames: Sequence[NarrativeFrame], style: NarrativeStyle, tick: int) -> NarrativeView` | 纯派生：WorldState 只读 → view；**零反作用**（P9-INV-8：A5 断言修改 view 后 WorldState 哈希不变）；LLM 润色为可选注入 backend 面（样例 = 零 backend，确定性文本模板） |

### 3.15 v1 迁移器（`modules/v1_migration.py` + `scripts/v2_migrate_v1.py`；T09；模块导出 5 名）

```python
__all__ = [
    "MIGRATION_DIAGNOSTIC_CODES",
    "MigrationDiagnostic",
    "MigrationReport",
    "migrate_project",
    "migrate_simulation",
]
```

#### 3.15.1 定位与放置（D-P9-07）

迁移器 = **包内可测逻辑**（`src/engine_v2/modules/v1_migration.py`）+
**薄 shell**（`scripts/v2_migrate_v1.py`，仅 argparse + 调用 + exit code：
0 = 全部成功 / 2 = 存在 incompatible / 1 = 用法错误）。备选（scripts 独占
/ `content/migrations_v1.py`）否决理由：content/ = P5 冻结面（新增文件
破坏 P5 边界测试闭集）；scripts 独占则测试需 `importlib` 绕路（D4 风格
违规）。`v1_migration.py` 为 13 官方模块之外的**包基础设施**（无
`ModuleIdentity`，边界方法 1 白名单含之，A18 闭集不含之）。

#### 3.15.2 闭集映射规则（M-1..M-9；零静默丢弃，S3 预检面）

**M-id 命名空间**：M-1..M-9 = 映射规则 id（下表第一列）；M-10..M-17 =
规则附着诊断事件 id（逐条对应 §3.15.3 绑定表的诊断码）。

输入 = v1 单文件项目（`public_start/*.yaml` 形状：world/player/
characters/objects/world_rules/starting_scene_description/max_ticks/
game_time/ticks_per_game_minute/narrative_style 顶层键）。

| 规则 | v1 源（锚） | v2 目标 | 诊断 |
|---|---|---|---|
| M-1 | 顶层 `world:`（test_empty.yaml:1 / whisperheads.yaml:1 / murder.yaml:1） | `world/<project>_world.yaml`（顶层键 `world`，P5 LAYOUT_OPTIONAL glob）；locations/objects 分拆（objects → M-4） | 缺 `world` 或 locations 零条 → ERROR（`MIGRATION_EMPTY_WORLD`，唯一无 M-id 码，§3.15.3 绑定表） |
| M-2 | 顶层 `player:`（test_empty.yaml:89 / whisperheads.yaml:223 / murder.yaml:312） | `game.yaml` 的 `player:` 节（`PlayerSpec`，schemas.py:227；zero_python 先例逐键对齐） | 缺 `player` → M-11 ERROR |
| M-3 | 顶层 `characters:`（test_empty.yaml:135 空表 / whisperheads.yaml:346 / murder.yaml:432） | `characters/<id>.yaml`（每角色一文件，顶层键 `characters` 列表）；`character_id` 冗余键（== `id`）→ 丢弃 + WARNING（M-16）；`personality`/`relationships`/`speech_examples`/`attributes` 逐键 → `CharacterSpec`（schemas.py:250–263） | 缺 id / 重复 id → ERROR（M-14） |
| M-4 | `world.objects`（test_empty.yaml:31–88；**v1 `state` 为 dict**，如 :40–42 `{closed: true}`） | `items/<id>.yaml`（顶层键 `items`，`ObjectSpec`，schemas.py:187）；**state dict 折叠 = 规范扁平串**：`state = ",".join(f"{k}={v}" for k, v in sorted(d.items()))`（bool → `true`/`false`；如 `{closed: true, unlocked: false}` → `"closed=true,unlocked=false"`）；空 dict → `state: null` | 每条折叠 → INFO（M-10）；`state` 非 dict（list/str）→ ERROR（M-10 shape 守卫分支，AD-P9-2） |
| M-5 | 顶层标量 `max_ticks`（:147）/ `game_time`（:148）/ `ticks_per_game_minute`（:151）/ `starting_scene_description`（:136）/ `narrative_style`（:152） | `game.yaml` 的 `scenario:` 节（`ScenarioSpec`，schemas.py:448：id = `scenario_<project>`，其余逐键；docstring 明示 v1 顶层标量归属此节） | 缺 `max_ticks` → ERROR（M-12） |
| M-6 | `world_rules.<kind>.append`（whisperheads.yaml:880–894：physics.append 5 条 / attribute.append 3 条；murder.yaml:783–799 同形） | `rules/<project>_v1_rules.yaml`（`rules` 列表，`RuleSpec` 形状）：每条 = `{id: rule_v1_<kind>_<NN>, description: <原文逐字>, condition: 'if(1 >= 0, allowed)', priority: <100 - NN>}`（**passthrough 条件**：永不改变可行性；NN = append 序号 01 起） | 每条 → INFO（M-13） |
| M-7 | `world_rules.<kind>.disable: [N]`（whisperheads.yaml:882 `[8]`；murder.yaml:785 `[]`） | **无 v2 对应物**（43.2-5：LLM physics 移除 → v1 编号内置规则表 `PHYSICS_DEFAULT_RULES`（prompts/loader.py:6）/ `ATTRIBUTE_DEFAULT_RULES`（:19）不存在于 v2） | 每个 N → WARNING（M-15），message 点名 N 与所属 kind |
| M-8 | 项目文件名（`test_empty` / `whisperheads` / `murder`） | `game.yaml` 的 `manifest:`（`ProjectManifest`，schemas.py:481：`schema_version: "2"`、`project_id: <文件名>`、`name`/`description` 模板化、`engine_version: ">=0.5.0"`（P5 ENGINE_VERSION:68）） | — |
| M-9 | 未知顶层键（白名单 9 键之外） | 拒绝（不迁移） | ERROR（M-11），message 点名键名 |

**规则表本身 = 模块常量** `MAPPING_RULES: Final[tuple[str, ...]]`
（9 规则 id `M-1`..`M-9` = 上表第一列，模块自检常量；规则 ↔ 码 ↔ severity 绑定以 §3.15.3 绑定表为准，A22 闭集交叉验证引用该表）。

#### 3.15.3 诊断闭集（D-P9-09；9 码，独立于 P5 18 码冻结面）

```python
MIGRATION_DIAGNOSTIC_CODES: Final[frozenset[str]] = frozenset({
    "MIGRATION_UNKNOWN_TOP_KEY",        # ERROR   M-9/M-11 族
    "MIGRATION_PLAYER_MISSING",         # ERROR   M-11
    "MIGRATION_MAX_TICKS_MISSING",      # ERROR   M-12
    "MIGRATION_DUPLICATE_ID",           # ERROR   M-14
    "MIGRATION_EMPTY_WORLD",            # ERROR   M-1 前置（无 world 或无 locations）
    "MIGRATION_DEPLOYMENT_FIELD",       # ERROR   M-17（simulation.yaml 面）
    "MIGRATION_OBJECT_STATE_FOLDED",    # INFO/ERROR M-10（折叠 / shape 守卫）
    "MIGRATION_FREEFORM_RULE_FOLDED",   # INFO    M-13
    "MIGRATION_RULE_REF_OBSOLETE",      # WARNING M-15/M-16
})
```

**M-id 绑定表**（9 码全绑定；M-11 双绑定 / M-15/M-16 同码双 id /
`MIGRATION_EMPTY_WORLD` 无 M-id 均显式钉死；与 §3.15.2 诊断列一致）：

| M-id | 诊断码 | severity | 触发（映射规则） |
|---|---|---|---|
| M-10 | `MIGRATION_OBJECT_STATE_FOLDED` | INFO / ERROR | M-4：对象 `state` dict 折叠 = INFO；`state` 非 dict（list/str）shape 守卫 = ERROR |
| M-11 | `MIGRATION_PLAYER_MISSING` | ERROR | M-2：顶层 `player` 缺失 |
| M-11 | `MIGRATION_UNKNOWN_TOP_KEY` | ERROR | M-9：未知顶层键——M-11 双绑定（码注释「M-9/M-11 族」= 此：缺 player 与未知顶层键同属顶层键缺失族两分支） |
| M-12 | `MIGRATION_MAX_TICKS_MISSING` | ERROR | M-5：顶层 `max_ticks` 缺失 |
| M-13 | `MIGRATION_FREEFORM_RULE_FOLDED` | INFO | M-6：每条 `world_rules.<kind>.append` 折叠 |
| M-14 | `MIGRATION_DUPLICATE_ID` | ERROR | M-3：角色 `id` 缺失 / 重复 |
| M-15 | `MIGRATION_RULE_REF_OBSOLETE` | WARNING | M-7：每个 `world_rules.<kind>.disable` 编号规则 |
| M-16 | `MIGRATION_RULE_REF_OBSOLETE` | WARNING | M-3：`character_id` 冗余键（== `id`）丢弃 |
| M-17 | `MIGRATION_DEPLOYMENT_FIELD` | ERROR | `migrate_simulation`：`simulation.yaml` llm/agents 节部署字段 |
| （无 M-id） | `MIGRATION_EMPTY_WORLD` | ERROR | M-1 前置：`world` 缺失或 locations 零条（唯一无 M-id 码） |

- `MigrationDiagnostic` frozen dataclass：`code: str`、`severity: str`
  （`ERROR`/`WARNING`/`INFO` 闭集）、`path: str`（yaml 相对路径 + 键链）、
  `message: str`。
- `MigrationReport` frozen dataclass：`input_path: str`、`status: str`
  （`migrated`/`incompatible` 闭集）、`diagnostics: tuple[MigrationDiagnostic, ...]`
  （sorted by (severity 降, code, path)）、`output_files: tuple[str, ...]`
  （migrated 时 = 写出文件相对路径，sorted）。
- **不变式**：报告内一切 code ∈ `MIGRATION_DIAGNOSTIC_CODES`（A22）；
  `status=migrated` ⇔ 零 ERROR 诊断 ⇔ 输出可经 P5 冻结
  `load_project` + `build_ir` + `validate_project` 零 ERROR（A16）。

#### 3.15.4 入口函数与 shell

| 名 | 形 | 语义 |
|---|---|---|
| `migrate_project` | `(input_path: str, out_dir: str) -> MigrationReport` | v1 单文件项目 → v2 分节项目（M-1..M-9）；**只读输入、只写 out_dir**（P9-INV-1）；yaml 输出 = `sort_keys=True` + 2 空格缩进 + UTF-8（字节稳定，A23 差分面） |
| `migrate_simulation` | `(input_path: str) -> MigrationReport` | `config/simulation.yaml` 面：`simulation` 节（max_ticks/tick_delay_ms/log_level/debug）与 `llm`/`agents` 节（:7–13/:15–）= **部署字段**（K8：P6 deployment 面，非项目内容）→ `status=incompatible` + `MIGRATION_DEPLOYMENT_FIELD` ERROR（点名 llm/agents 键）；不写出任何文件 |
| shell | `scripts/v2_migrate_v1.py`：`python scripts/v2_migrate_v1.py <v1.yaml> <out_dir>`（或 `--simulation <yaml>`） | 薄壳；stdout = JSON report（`json.dumps`，ensure_ascii=False） |

**四输入预期**（A16 钉死；W0 已按 §0.3 锚点核验源形状）：

| 输入 | 预期 status | 预期诊断 | 后续 |
|---|---|---|---|
| `public_start/test_empty.yaml`（154） | migrated | INFO ×N（M-10：objects 折叠；characters 空表零 M-14） | 输出可加载（A16）+ 与 P5 zero_python 镜像 IR 同构（A17，objects 差异披露） |
| `public_start/whisperheads.yaml`（897） | migrated | WARNING ×1（M-15：physics.disable [8]）+ INFO（M-13 ×8 条 append / M-10 objects 折叠） | 输出可加载（A16） |
| `public_start/murder.yaml`（802） | migrated | INFO（M-13 append / M-10 折叠）；disable 空表零 M-15 | 输出可加载（A16） |
| `config/simulation.yaml`（23） | incompatible | ERROR ×≥1（M-17：llm 节 + agents 节点名） | 零输出（A16） |

### 3.16 三样例垂直切片（T11/T12/T13；§3.19 行 31–45 fixture 项目）

**通用宿主协议**（§6.2 conftest `p9_host` fixture）：P5 `load_project` +
`build_ir` + `validate_project`（零 ERROR）→ 依 IR 构建 WorldState
（entities + 组件 + 空间域）→ 注册模块面（actions/space/mode/policy/
dynamics/narration）→ 确定性 tick 循环（注入 `LogicalClock` /
`FixedMonotonicClock` / `FakeInferenceBackend` 脚本 / `DslRng(seed)`）→
逐 tick 收集效果流。**宿主 = 测试代码，零 src 落位**（runtime = P1）。

#### 3.16.1 Galgame 样例（`tests/fixtures/v2_project_galgame/`，5 文件）

世界：1 地点（教室）+ 2 角色（yuki/lena，含 personality/relationships
初始值）+ 1 物品（letter）。切片序列（A1–A5 钉此序列）：

1. 加载项目（零 ERROR）→ 世界构建（A 前件）。
2. **A4 observation**：player 于教室 → `build_observations` 产出
   yuki/lena 的 `ObservationRecord`（sight）。
3. **A2 character policy**：`enqueue_actor_wakeup(yuki)` → 宿主驱动
   `run_policy_decide`（脚本 backend）→ yuki 提案 `talk` 动作
   （`ActionProposal`）。
4. **A1 dialogue**：player `talk` → `run_dialogue`（脚本 backend 回应）
   → `DialogueResult` 含回应文本。
5. **A3 relationship**：对话结果 → `adjust_relationship` 落位 →
   yuki 对 player affinity 变化事件在组件面可见。
6. **A5 narrative-ready ViewState**：`render_narrative_view` →
   `NarrativeView`（JSON-clean；含 tick/frames/actors_visible）；修改
   view dict 后 WorldState 哈希不变（P9-INV-8）。

#### 3.16.2 Sandbox 样例（`tests/fixtures/v2_project_sandbox/`，5 文件）

世界：2 地点 + 2 角色（wanderer/merchant）+ `rules/sandbox_rules.yaml`
（1 条世界规则 DSL）。切片序列（A6–A11 + A23 钉此序列）：

1. 加载 + 构建（A 前件）。
2. **A6 long action**：player 提案长动作（duration 3 tick）→
   `start_action`（scheduler.py:468）→ ActiveAction（actions.py:207）
   RUNNING；tick 3 后 COMPLETED（lifecycle 转移经
   `transition_action`（action_lifecycle.py:257））。
3. **A7 world time**：逻辑 tick 0→N（`set_logical_tick` :117）→ 游戏
   分钟 = tick × `ticks_per_game_minute`（scenario 声明 0.5）确定值
   （无 wall-clock）。
4. **A8 NPC wakeup**：仅对 merchant `enqueue_actor_wakeup`（:374）→
   该 tick 仅 merchant 一次 backend 调用（`FakeInferenceBackend.calls`
   计数 = 1）；未 wakeup 的 wanderer 零调用（43.2-2 移除面行为钉）。
5. **A9 knowledge boundary**：merchant 与 player 同地点（sight 内）→
   有观察；wanderer 异地点 → 零观察、KNOWLEDGE/MEMORY 组件哈希不变。
6. **A10 LLM dynamics**：`run_dynamics_turn`（host.py:86）+
   `LLMWorldDynamics`（脚本 backend）→ 产出 ProposedEffect（经宿主
   authority 面应用）→ 世界变更可见。
7. **A11 rules dynamics**：同 host + `RuleDynamics`（rule.py:273）+
   sandbox_rules.yaml 规则 → 条件命中 tick 产效果（确定性序）。
8. **A23 determinism**：同一脚本 + 同 seed 完整重跑序列 1–7 → 效果流
   逐条相等（P9-INV-6）。

#### 3.16.3 Tactical 样例（`tests/fixtures/v2_project_tactical/`，5 文件）

世界：hex 网格（3×3，`HexGrid(offset="odd-r")` → `hex_adjacency` →
`GraphSpace` 注册入 `tactical` 空间域）+ 2 角色（soldier_a/soldier_b）
+ `actions/tactical_actions.yaml`（attack/take_cover/move 声明）。
切片序列（A12–A15 钉此序列）：

1. **A12 hex space**：`hex_adjacency` 边表 = 期望对称边集（3×3 = 22 边，
   常量钉）；`distance_between` 对角 hex 步数 = 2（立方坐标公式钉）；
   方格对照：同域集注册 `GridSpace(3,3)`（space.py:350）曼哈顿距离钉。
2. **A13 tactical mode**：`build_tactical_overlay`（TACTICAL_ACTION_IDS）
   → `merge_modes`（gameplay_mode.py:266）→ 战术模式下
   `is_action_available`（:340）：`attack` 允许、样例中非战术动作
   （如 `talk`）拒绝。
3. **A14 deterministic actions**：soldier_a `attack` 提案 →
   `MoveExecutor`/攻击执行器（纯函数）→ **零 backend 调用**
   （`FakeInferenceBackend.calls` 全程为空）+ 同输入二次执行 = 同效果流。
4. **A15 mode transition**：`ModeChangeRequest`（:396）探索→战术→探索
   （`TacticalModePolicy` + `apply_mode_change` :475）→ 两次转移后
   `MergedModeConfiguration` 回到探索集；**单一 WorldState 全程**
   （无重建，tick 连续）。

### 3.17 T14 差分行为评审（方法学；`test_p9_differential.py` 6 函数）

**方法学（D-P9-14）**：v1 纯函数直引（**非**运行时回放）+ 镜像同构。
W0 预验（R5）：`src/game/{attributes,condition_eval,deterministic_rules,
tick_eval,state_apply}.py` 头部 import 仅 re/random/copy/dataclass/typing
（零 LangGraph/第三方）；`src/models/*.py` 仅 pydantic → `.venv` 内
可直引（`PYTHONPATH=.`）。

| 差分面 | v1 侧（冻结直引） | v2 侧 | 判据 |
|---|---|---|---|
| D-α 属性 parity | `src/game/attributes.py`：`_clamp`:10 / `apply_attribute_changes`:999 / `apply_natural_attribute_deltas`:113 | `modules/attributes.py` 同输入（钉死夹具：10 属性 × 3 变更 × 2 tick，零随机路径） | 终值逐属性相等（±0 精确浮点，输入取整点值）；locked 拒绝行为同序 |
| D-β DSL parity | `src/game/condition_eval.py::evaluate_condition`（def :35）对 v1 钉死条件集（8 条，取自 v1 测试夹具，确定性子集——零 rand 族） | P5 冻结 `evaluate_condition`（rule_module.py:903）同条件（文法逐字，P5 已声明 v1 对齐） | 判定结果（allowed/uncertain/blocked + 概率）逐条相等 |
| D-γ 自然差 parity | v1 `compute_attribute_deltas_diff`（attributes.py:59）同输入 | v2 `compute_natural_deltas` | 逐属性相等 |
| D-δ 迁移字节稳定 | —（自参照） | `migrate_project` 双跑（test_empty/whisperheads/murder） | 输出目录逐文件 sha256 相等（确定性写出） |
| D-ε 镜像同构（A17） | `tests/fixtures/v2_project_zero_python/`（P5 手工镜像，冻结） | `migrate_project(test_empty.yaml, tmp)` 输出 | 两项目 `load_project`+`build_ir` 后：manifest/scenario/player/world/characters/rules/actions 节 IR 字段**逐一相等**；**唯一允许差异 = items 节**（P5 D-01 未镜像 objects；P9 输出含 items 4 条，state 折叠串钉）——差异本身被断言钉死（非静默） |
| D-ζ 持久化 round-trip（A24） | —（P8 冻结面） | sandbox 样例终局 WorldState 经 `to_persistence_snapshot`（snapshot.py:104）→ `dump_persistence_snapshot`（:133）→ `load_persistence_snapshot`（:143）→ `check_persistence_versions`（:176） | 零版本冲突；JSON-clean（`json.dumps` 零失败） |

**差分结论登记**：实现波次将 D-α..D-ζ 实测差（预期 = 零差，D-ε 例外
= items 节披露）记入 §9 勘误链（若有非零差 → DEV-P9-NN 登记 + 归因：
v1 自身 bug 保留 / v2 有意的 43.2 移除差 / 移植错误——移植错误 = 修复，
不得以「对齐 v1」为由保留）。

### 3.18 波次表（W1–W7；每波结束套件全绿 + 白名单增量 = 该波列明文件）

| 波 | 任务 | src 新增 | test 新增 | fixture/scripts 新增 | 新增平铺函数 | 波后累计 |
|---|---|---|---|---|---|---|
| W1 | T02 + T05 | base.py / attributes.py / character.py | test_attributes.py / test_character.py | — | 12 + 4 = 16 | 3054+16 = 3070 |
| W2 | T03 + T04 | inventory.py / relationships.py | test_inventory.py / test_relationships.py | — | 6 + 4 = 10 | 3080 |
| W3 | T06 + T10 | perception.py / knowledge.py | test_perception_knowledge.py（含 T10 回归 t6） | — | 7 | 3087 |
| W4 | T07 + T08 | scenario.py / actions.py | test_scenario_trigger.py / test_action_executors.py | — | 4 + 6 = 10 | 3097 |
| W5 | T09 | v1_migration.py | test_v1_migration.py | scripts/v2_migrate_v1.py | 7 | 3104 |
| W6 | T11 + T13 | dialogue.py / narration.py / space.py / tactical.py | test_g9_galgame.py / test_g9_tactical.py | v2_project_galgame（5 文件）/ v2_project_tactical（5 文件） | 6 + 5 = 11 | 3115 |
| W7 | T12 + T14（+ T01 机械面） | dynamics.py | test_g9_sandbox.py / test_p9_differential.py / test_module_face.py + **TestP9Boundary 6 方法**（§3.20，锚文件 EOF 纯追加） | v2_project_sandbox（5 文件） | 8 + 6 + 7 = 21（+ 边界方法 6） | **3142 = 门③期望**（3054+82+6） |

波间纪律：每波结束 `pytest -q` 全绿；白名单外零写盘；fixture 一经落盘
跨波不改（§6.4）；W7 波内序 = dynamics.py → sandbox 样例 → 差分 →
module_face → 边界块（module_face 依赖 13 模块齐备）。

### 3.19 编号闭集白名单（47 行；门③ diff 判定基准）

> 判定规则：门③ `git diff --name-status aab029c..HEAD -- src tests scripts`
> 的非空行 **必须** 与下表逐行相等（A 新增 / M 修改）；表外任何路径
> （含 docs/ 以外文件、`.git*`）出现 = FAIL。

**src（行 1–15，全部 A）**

| # | 路径 | 章节 |
|---|---|---|
| 1 | `src/engine_v2/modules/base.py` | §3.1 |
| 2 | `src/engine_v2/modules/attributes.py` | §3.2 |
| 3 | `src/engine_v2/modules/inventory.py` | §3.3 |
| 4 | `src/engine_v2/modules/relationships.py` | §3.4 |
| 5 | `src/engine_v2/modules/character.py` | §3.5 |
| 6 | `src/engine_v2/modules/perception.py` | §3.6 |
| 7 | `src/engine_v2/modules/knowledge.py` | §3.7 |
| 8 | `src/engine_v2/modules/scenario.py` | §3.8 |
| 9 | `src/engine_v2/modules/actions.py` | §3.9 |
| 10 | `src/engine_v2/modules/dialogue.py` | §3.10 |
| 11 | `src/engine_v2/modules/space.py` | §3.11 |
| 12 | `src/engine_v2/modules/tactical.py` | §3.12 |
| 13 | `src/engine_v2/modules/dynamics.py` | §3.13 |
| 14 | `src/engine_v2/modules/narration.py` | §3.14 |
| 15 | `src/engine_v2/modules/v1_migration.py` | §3.15 |

**tests（行 16–30，全部 A）**

| # | 路径 | 章节 |
|---|---|---|
| 16 | `tests/engine_v2/modules/__init__.py` | §6.1（0 函数） |
| 17 | `tests/engine_v2/modules/conftest.py` | §6.2 |
| 18 | `tests/engine_v2/modules/test_attributes.py` | §6.1（12） |
| 19 | `tests/engine_v2/modules/test_inventory.py` | §6.1（6） |
| 20 | `tests/engine_v2/modules/test_relationships.py` | §6.1（4） |
| 21 | `tests/engine_v2/modules/test_character.py` | §6.1（4） |
| 22 | `tests/engine_v2/modules/test_perception_knowledge.py` | §6.1（7） |
| 23 | `tests/engine_v2/modules/test_scenario_trigger.py` | §6.1（4） |
| 24 | `tests/engine_v2/modules/test_action_executors.py` | §6.1（6） |
| 25 | `tests/engine_v2/modules/test_v1_migration.py` | §6.1（7） |
| 26 | `tests/engine_v2/modules/test_g9_galgame.py` | §6.1（6） |
| 27 | `tests/engine_v2/modules/test_g9_sandbox.py` | §6.1（8） |
| 28 | `tests/engine_v2/modules/test_g9_tactical.py` | §6.1（5） |
| 29 | `tests/engine_v2/modules/test_p9_differential.py` | §6.1（6） |
| 30 | `tests/engine_v2/modules/test_module_face.py` | §6.1（7） |

**fixtures（行 31–45，全部 A）**

| # | 路径 | 章节 |
|---|---|---|
| 31 | `tests/fixtures/v2_project_galgame/game.yaml` | §3.16.1 |
| 32 | `tests/fixtures/v2_project_galgame/world/galgame_world.yaml` | §3.16.1 |
| 33 | `tests/fixtures/v2_project_galgame/characters/yuki.yaml` | §3.16.1 |
| 34 | `tests/fixtures/v2_project_galgame/characters/lena.yaml` | §3.16.1 |
| 35 | `tests/fixtures/v2_project_galgame/items/letter.yaml` | §3.16.1 |
| 36 | `tests/fixtures/v2_project_sandbox/game.yaml` | §3.16.2 |
| 37 | `tests/fixtures/v2_project_sandbox/world/sandbox_world.yaml` | §3.16.2 |
| 38 | `tests/fixtures/v2_project_sandbox/characters/wanderer.yaml` | §3.16.2 |
| 39 | `tests/fixtures/v2_project_sandbox/characters/merchant.yaml` | §3.16.2 |
| 40 | `tests/fixtures/v2_project_sandbox/rules/sandbox_rules.yaml` | §3.16.2 |
| 41 | `tests/fixtures/v2_project_tactical/game.yaml` | §3.16.3 |
| 42 | `tests/fixtures/v2_project_tactical/world/arena.yaml` | §3.16.3 |
| 43 | `tests/fixtures/v2_project_tactical/characters/soldier_a.yaml` | §3.16.3 |
| 44 | `tests/fixtures/v2_project_tactical/characters/soldier_b.yaml` | §3.16.3 |
| 45 | `tests/fixtures/v2_project_tactical/actions/tactical_actions.yaml` | §3.16.3 |

**scripts（行 46，A）+ 既有文件修改（行 47，M = EOF 纯追加）**

| # | 路径 | 模式 | 章节 |
|---|---|---|---|
| 46 | `scripts/v2_migrate_v1.py` | A | §3.15.4 |
| 47 | `tests/engine_v2/core/test_import_boundary.py` | **M（L2071 后 EOF 纯追加；L1–L2071 逐字节不变，边界方法 6 自证）** | §3.20 |

**fixture 项目与 §6.1 测试文件 1:1 对应**（自检项）：白名单行 16–30 的
15 文件 = 13 个测试文件 + 2 个非测试文件（`__init__.py`/`conftest.py`）= §6.1 分表
13 个平铺函数表 + 2 个零函数文件；行 31–45 的 15 个 fixture 文件 =
§3.16 三样例各 5 文件。

### 3.20 TestP9Boundary 6 方法表（§2.7 锚文件 EOF 纯追加块）

| # | 方法名 | 检查内容 | 失败语义 |
|---|---|---|---|
| 1 | `test_p9_src_tree_closed` | `src/engine_v2/modules/` 文件集 == 白名单行 1–15 + 占位 `__init__.py`（16 项）；`scripts/v2_migrate_v1.py` 存在 | 白名单外新文件 / 缺失文件 |
| 2 | `test_p9_test_tree_closed` | `tests/engine_v2/modules/` 文件集 == 白名单行 16–30（15 项）；`tests/fixtures/v2_project_{galgame,sandbox,tactical}/` 文件集 == 行 31–45（15 项） | 同上 |
| 3 | `test_p9_string_literal_k8` | AST 遍历 P9 src 15 文件全部字符串字面量（含 docstring）× 12 名黑名单（复用既有 `P4_LLM_PROVIDER_BLACKLIST`，:225–240）零命中；大小写不敏感子串面 | K8 词泄漏（P9-INV-4） |
| 4 | `test_p9_import_closure` | AST 遍历 P9 src 15 文件全部 import：根闭集 ⊆ {stdlib, pydantic, engine_v2.core, engine_v2.content, engine_v2.llm, engine_v2.prompts, engine_v2.dynamics, engine_v2.modules.<requires 声明面>}（§3.0）；**engine_v2 全树**（含 P1–P8 冻结面 + P9 面）import 零 `langgraph` / `langchain` | 边界越权 / LangGraph 依赖回归（G9 条款②，P9-INV-5/9） |
| 5 | `test_v1_frozen_hashes` | v1 路径集（§0.3 定义）sha256 == 嵌入清单（W7 落盘时自基线工作树计算；34 src `.py` + public_start 3 + config 1 + v1 测试集） | v1 冻结面被修改（P9-INV-1） |
| 6 | `test_p9_frozen_surfaces_untouched` | (a) `pyproject.toml` sha256 不变（P9-INV-10）；(b) 占位五件套（§2.9）sha256 不变；(c) `src/engine_v2/{core,content,llm,prompts,dynamics,persistence,plugins}` + `tests/engine_v2/{core,content,llm,prompts,dynamics,persistence,plugins}` 子树哈希不变（**锚文件自身**以「前 2071 行 sha256 == 基线值」特判，排除纯追加段）；(d) `tests/fixtures/` 既有 7 项目目录哈希不变 | kernel / 冻结测试面被修改（P9-INV-2/10） |

实现注记：方法 5/6 的嵌入清单 = W7 实现者**自 `aab029c` 工作树**一次性
计算的 sha256 字面量（非运行时 `git` 调用——测试环境无 git 依赖假设）；
清单生成脚本 = W7 一次性 shell（不落盘，仅产出字面量粘贴入测试）。

### 3.21 门③ 六步文本块（实现波次 W7 收口逐字执行）

```text
① cd /home/armourpiercer/projects/llmBasedSim && git rev-parse HEAD
   → 记录门③ HEAD；确认 == 或晚于 aab029c（architecture-v2 分支）。
② git diff --name-status aab029c..HEAD -- src tests scripts
   → 非空行集与 §3.19 白名单 47 行逐行相等（A/M 模式匹配；表外路径 = FAIL）。
③ PYTHONPATH=. .venv/bin/python -m pytest -q
   → passed 计数 == 3142（§8.3 恒等式：3054 基线 + 82 P9 平铺 + 6 边界方法）；
     failed/error/skipped == 0。
④ TestP9Boundary 6 方法全绿（③ 之内含）+ TestP8Boundary/TestP7Boundary/
   TestP6Boundary 既有块全绿（冻结面自证）。
⑤ LC_ALL=C.UTF-8 awk 'length($0)>100' <P9 全部落盘文件> | wc -l == 0
   （行宽 D2）；grep -rn 裸反斜杠-b 序列（0x5C 0x62）于 P9 src = 0 命中
   （D3，ERR-P7-14 面）。
⑥ 本 SOT §8.2 台账逐模块 `__all__` 实数核对（python -c import 面）+
   §8.4 偏差登记闭合（全部 DEV-P9-NN 有处置）+ §9 勘误链更新。
```

---

## §4 决策登记（D-P9-01..16；五段：问题/备选/选择/理由/机械验证面；标「（自裁）」者备选段豁免）

### D-P9-01 官方模块包落位（Spec §40「一个 distribution」落地）

- **问题**：13 官方模块的物理落位——独立包 / 单包多子包 / 单包平铺模块？
- **备选**：独立包（13 个独立 distribution——否决：Spec §40 明确允许单
  distribution，W0 时点过度结构）/ 单包多子包（每模块一目录——否决：零
  多文件需求，过度结构，见理由）/ 单包平铺模块（采纳）。
- **选择**：单包平铺：`src/engine_v2/modules/<name>.py`（13 模块 + base +
  v1_migration = 15 文件）；Spec §40「可以实际打包在一个 distribution 中，
  但逻辑上要保持模块边界」→ 逻辑边界 = 导入闭集 + `MODULE_REQUIRES` 声明
  （§3.0/§3.1.2）+ 边界方法 4 机械检查。
- **理由**：P5/P7/P8 均「单包 + 子模块 + 冻结 `__init__` 占位」既有风格；
  子包化（每模块一目录）在无多文件需求的 W0 时点 = 过度结构；模块边界
  已由 AST 检查机械化，不依赖目录结构。
- **机械验证面**：边界方法 1（文件闭集）+ 方法 4（import 闭包）+ A18/A20。

### D-P9-02 模块发现机制 = 显式导入注册（非 .py 发现）

- **问题**（自裁）：官方模块如何被引擎发现？项目侧声明驱动？文件系统
  扫描？
- **选择**：kernel 侧 = 显式 `import engine_v2.modules.<name>` + 注册函数
  （§3.1.3）；项目侧 = `game.yaml` modules 声明（P5 `ModuleGraphNode`，
  schemas.py:365）+ P5 冻结 `module_graph` 依赖检查（Spec §41：`requires`
  显式声明 + 依赖图检查——**已由 P5 冻结面完整实现**，P9 零新增检查逻辑）。
- **理由**：P5 9-glob 零 `.py`（LAYOUT_OPTIONAL，loader.py:50–60）= 项目
  侧零 Python 的冻结契约；OI-P7-1（项目侧 `.py` backend 发现）G8 R4 已
  评估不移交（D-P8-15）。显式注册 = 确定性 + 可审计。
- **机械验证面**：A18 t4（requires 无环，经 P5 `find_cycles`）+ 样例项目
  加载（§3.16）+ 边界方法 4。

### D-P9-03 模块 id 语法与版本

- **问题**（自裁）：`MODULE_ID` 语法取何值？
- **选择**：`llmsim-standard-<name>` = Spec §40（L1951–1963）代码块逐字
  （13 名）；版本统一 `"1"`（P5 版本文法 `^\d+(\.\d+)*$`，D-P5-06）。
- **理由**：Spec 原文即规范；自造语法（如 `standard.<name>`）= 无依据偏离。
- **机械验证面**：A18（t1/t2/t3：13 模块身份面 + id 闭集 + 文法）。

### D-P9-04 T01 三态判据与锚定粒度

- **问题**：v1 代码 reusable/obsolete 映射的判据粒度？
- **备选**：全函数级锚（game_graph 11 函数 + attributes 17 函数族全钉——
  否决：多数 v1 函数 P9 零消费，锚成本与收益失衡）/ 纯文件级（否决：
  两高密度文件误读风险不可界，违 D1）/ 三态判据 + 文件级总表 + 两高密度
  文件函数级锚表（采纳）。
- **选择**：三态 = {保留思想（Spec §43.1 的 11 条逐一挂接）、移除（§43.2
  的 9 条逐一挂接）、重写（§43.3 的 9 项逐一挂接）}；粒度 = 文件级总表 +
  `game_graph.py`/`attributes.py` 两文件函数级锚表（game_graph 见 §2.3，attributes 见 §3.2）；其余 v1 文件
  到文件级即可（行数/职责单一）。
- **理由**：43.1/43.2/43.3 三节即判据本体（Spec 已裁决）；SOT 的职责 =
  逐条落位 + 行锚钉死（防止实现波次误读）；`game_graph.py`（952 行，11
  函数）与 `attributes.py`（1100 行，17 函数族）为两高密度文件，必到函数级。
- **机械验证面**：W7 `test_module_face.py`（模块面齐备）+ 边界方法 4
  （P9 树零 v1 import——v1 消费仅测试侧差分直引，AST 面：src 闭集不含
  `src.game`/`src.graph` 等 v1 根）。

### D-P9-05 NPC 决策面 = BehaviorPolicy + 事件驱动 wakeup（43.2-2 移除面）

- **问题**：v1 `characters_all_decide`（每 tick 全员决策）的 v2 承接？
- **备选**：保留全员决策循环（v1 同构——否决：43.2-2 明列移除 + K5）/
  纯 LLM Agent 统一 loop（所有 NPC 皆 LLM Agent——否决：K5「Agent 是
  Policy，不是 Engine」MUST NOT）/ BehaviorPolicy + 事件驱动选择性唤醒
  （采纳）。
- **选择**：NPC 决策 = `NpcBehaviorPolicy`（core `BehaviorPolicy` Protocol
  实现）+ 宿主经 `enqueue_actor_wakeup`（scheduler.py:374）选择性唤醒；
  **零「全员每 tick」实现**；player 侧 = core 冻结 `PlayerPolicy`（:70）。
- **理由**：K5（kernel 不假设全员决策）+ 43.2-2 明列移除；P3 Scheduler
  冻结面已提供事件驱动唤醒能力（WakeupHook/WakeupHookRegistry，
  scheduler.py:316/:339）。
- **机械验证面**：A8（非 wakeup tick 零决策 backend 调用——
  `FakeInferenceBackend.calls` 计数钉）+ A2（policy 提案面）。

### D-P9-06 感知-知识分离的模块切分（43.1-9 / 43.2-6 双面）

- **问题**：perception 与 knowledge 两模块的职责切面？
- **备选**：单模块合并（perception+knowledge 合一——否决：Spec §40 两模块
  分立，两段管线无法机械分界）/ knowledge 直读事件流（event_log 入签名
  ——否决：43.2-6 全知通道回潮，t6 回归无法钉）/ perception = 空间邻域 →
  ObservationRecord + knowledge = ObservationRecord 纯 reducer（采纳）。
- **选择**：`perception` = 纯空间邻域 → `ObservationRecord`（输入签名
  不含 event_log/全局状态）；`knowledge` = `ObservationRecord` →
  belief/memory 纯 reducer（载体 = core 冻结知识三组件）；**全局事件 →
  NPC memory 的通道不存在**（43.2-6 移除，v1 锚 game_graph.py:553–561）。
- **理由**：Spec §40 两模块分立 + 43.1-9 分离思想 + 43.2-6 移除假设；
  签名级局部性（而非注释约定）= 可机械化（A9 行为面 + t6 回归面）。
- **机械验证面**：A4/A9 + `test_perception_knowledge.py::t6`（T10）。

### D-P9-07 迁移器放置（`modules/v1_migration.py` + 薄 shell）

- **问题**（自裁）：T09 迁移器代码落位？
- **备选**：(a) `scripts/v2_migrate_v1.py` 独占；(b)
  `src/engine_v2/content/migrations_v1.py`；(c) `src/engine_v2/modules/v1_migration.py` + 薄 shell。
- **选择**：(c)。
- **理由**：(a) 测试需 `importlib` 绕路引 scripts（风格违规 + 闭集检查
  困难）；(b) content/ = P5 冻结面（新增文件破坏 P5 边界测试闭集，
  P9-INV-2）；(c) 迁移器 = 官方模块分布的「入口工具」，与 13 模块同包
  边界自然（无 ModuleIdentity = 包基础设施，§3.15.1），测试直接
  `from engine_v2.modules.v1_migration import ...`。
- **机械验证面**：白名单行 15/46 + A16/A17/A22 + shell exit code 面
  （t1 同函数断言三种 exit 语义）。

### D-P9-08 T09 闭集映射规则（零静默丢弃；S3 预检落位）

- **问题**（自裁，S3 相关）：v1 单文件项目 → v2 分节项目的字段映射规则？
  无 v2 对应物的字段如何处置？
- **选择**：M-1..M-9 闭集（§3.15.2）：逐节机械映射（world/player/
  characters/objects/scalar 标量五主面）；object state dict → 规范扁平串
  （`k=v` sorted 逗号连接，§3.15.2 M-4）；world_rules.append 自由文本 →
  rules yaml **passthrough 条目**（`condition: 'if(1 >= 0, allowed)'` 永不
  改可行性，原文入 `description` 零损，M-6）；world_rules.disable [N] →
  WARNING 丢弃（M-7，43.2-5 使 v1 编号内置规则表无 v2 对应物）；
  simulation.yaml 的 llm/agents 节 → **incompatible**（`MIGRATION_DEPLOYMENT_FIELD`
  ERROR，K8：部署字段禁入项目，M-17）；未知顶层键 → ERROR 拒绝（M-9）。
- **理由**：S3 预检 = 零 destructive——一切丢弃显式诊断（9 码闭集），
  一切文本零损保留；passthrough 折叠的语义漂移风险（R1）由「永不改可行性
  + INFO 逐条披露 + D-ε 差分面」三重缓解；P5 zero_python 镜像（§2.8）=
  形状基线（A17 同构）。
- **机械验证面**：A16（四输入预期表）/ A17（IR 同构 + items 差异披露）/
  A22（9 码闭集）/ D-δ（字节稳定）+ §3.15.2 规则表逐条测试（t2–t7）。

### D-P9-09 迁移诊断 = 独立 9 码闭集（不复用 P5 18 码）

- **问题**（自裁）：迁移器诊断码复用 P5 `DIAGNOSTIC_CODES`（18 码，
  schemas.py:112–133，冻结）还是新闭集？
- **选择**：新闭集 `MIGRATION_DIAGNOSTIC_CODES`（9 码，§3.15.3，
  `MIGRATION_*` 前缀）。
- **理由**：P5 18 码 = Project Format v2 加载/校验面的冻结契约（零变更，
  P9-INV-2）；迁移器输入 = v1 形状（`detect_v1_shape`，loader.py:242），
  不在 P5 码语义域内；独立闭集 = 语义清晰 + 可独立演进 + A22 可机械闭集
  检查（两闭集互斥：`MIGRATION_*` ∩ `LLMSIM_*` = ∅）。
- **机械验证面**：A22 + t7（报告全码 ∈ 闭集）+ 边界方法 3（码字面量不
  含 12 名推词——`MIGRATION_DEPLOYMENT_FIELD` 码名本身零推词，message
  文本点名 llm/agents 键时以「deployment 节」措辞规避，D7 检查面含
  message 字面量）。

### D-P9-10 三样例 = 新 fixture 项目 + 平铺测试（垂直切片宿主 = conftest）

- **问题**（自裁）：G9 三样例的载体——扩展现有 fixture 还是新建项目？
- **选择**：新建 3 个最小 v2 项目（各 5 文件，§3.16）+ 3 个平铺测试文件；
  样例宿主 = `tests/engine_v2/modules/conftest.py` 的 `p9_host` fixture
  （§6.2）；零 src 侧样例代码。
- **理由**：现有 fixture 项目各有冻结职责（zero_python = P5 镜像基线；
  v2_project_llm/p7 = P6/P7 面）——扩建破坏其冻结语义；G9 要求「三套
  sample 分别证明」= 三套独立垂直切片，项目级隔离最干净；fixture 项目
  经 P5 冻结 loader 加载 = 同时证明 Project Format v2 兼容性。
- **机械验证面**：A1–A15 各 1:1 平铺函数 + 白名单行 26–28/31–45。

### D-P9-11 G9「LLM / rules dynamics」= 2 判据（A10/A11 分立）

- **问题**（自裁）：Plan G9 Sandbox 第 5 条 bullet「LLM / rules
  dynamics」（Plan L802 单条）= 1 判据还是 2 判据？
- **选择**：2 判据（A10 LLM 动力学 + A11 规则动力学）；任务书「五+五+四」
  之 Sandbox 五 = 5 bullet，但 bullet 内「LLM / rules」= 两后端各证一次
  （§0.1 计数口径登记）。
- **理由**：两后端 = P7 两个独立冻结实现（llm_world.py:180 / rule.py:273）
  + 两条独立脚本化路径（backend 脚本 vs 规则 DSL 命中）；合并为 1 判据
  则其中一后端可被另一后端掩盖（失败面不互检）。
- **机械验证面**：t5/t6 分立函数 + §3.16.2 步骤 6/7 分立。

### D-P9-12 dynamics 模块 = P7 复用桥（零新动力学逻辑）

- **问题**（自裁）：官方 dynamics 模块（Spec §40 第 12 名）实装内容？
- **选择**：`modules/dynamics.py` = 2 导出（`DynamicsBinding` +
  `build_standard_dynamics`，组装 P7 `CompositeDynamics`）；零新
  backend/规则/效果逻辑。
- **理由**：P7 已冻结交付完整动力学面（8 模块 35 导出）；Spec §40 要求
  模块**存在**（官方分布完整性，A18 闭集）而非重复实现；桥面使「官方
  dynamics 模块」在注册/文档/样例面上真实可用（§3.16.2 经此组装）。
- **机械验证面**：A10/A11（经 `build_standard_dynamics` 组装面运行）+
  A18（模块身份面）+ 边界方法 4（仅 import P7 冻结根）。

### D-P9-13 narration 模块 = text 侧派生 ViewState（非权威；image 归 P10）

- **问题**（自裁）：官方 narration 模块的实装边界？
- **选择**：`modules/narration.py` = 纯派生 text 侧（`NarrativeView`
  TypedDict + `render_narrative_view` 纯函数；可选注入 backend 润色面，
  样例 = 零 backend 确定性模板）；**image 侧零实现**（Spec §32 text/image
  并行的 image = P10 presentation 面）。
- **理由**：Spec §8.5（L626–638）ViewState MUST NOT authoritative →
  narration 输出 = 派生数据（P9-INV-8，A5 行为钉）；P9 无 presentation
  宿主（P10），text 侧纯函数即可完整证明「narrative-ready」；LLM 润色
  面保留为注入点（G9 不要求 LLM 叙述，仅 narrative-ready）。
- **机械验证面**：A5（JSON-clean + 非权威双面）+ §3.16.1 步骤 6。

### D-P9-14 T14 差分方法学 = v1 纯函数直引 + 镜像同构（非运行时回放）

- **问题**（自裁）：v1/v2 差分行为评审如何执行？
- **选择**：六面 D-α..D-ζ（§3.17）：属性/DSL/自然差三面 = **v1 纯函数
  直引**（`.venv` 内 `import src.game.attributes` 等——W0 预验零 LangGraph
  import，R5）+ 钉死输入夹具逐值比对；迁移两面 = 字节稳定 + IR 同构
  （对 P5 zero_python 镜像）；持久化一面 = P8 冻结快照 round-trip。
  **不**经 v1 LangGraph 运行时回放旧局。
- **理由**：运行时回放需要 v1 全栈（LangGraph + 模型配置 + 随机 LLM 输出）
  = 非确定性 + S4 边缘（依赖面）+ 与 G9 条款②（LangGraph 非依赖）的精神
  冲突；纯函数直引 = 确定性逐值 parity，且 v1 冻结面保证输入侧可信
  （f0a1052 锚，P9-INV-1）。
- **机械验证面**：`test_p9_differential.py` 6 函数（D-α..D-ζ）+ R5 预验
  失败 → S1 触发（人工介入，不自行降级）。

### D-P9-15 波次划分 W1–W7（§3.18 表为准）

- **问题**（自裁）：14 任务 → 波次切分？
- **选择**：W1–W7 七波（§3.18 表）：T02+T05 / T03+T04 / T06+T10 /
  T07+T08 / T09 / T11+T13 / T12+T14（+T01 机械面）；T01 = 设计期交付
  （本 SOT §2.3）+ W7 机械验证面。
- **理由**：依赖序（attributes 先行——inventory/character requires 之；
  perception/knowledge 先行——sandbox 样例 A9 依赖之）+ 每波独立全绿
  （增量 ≤ 16 函数，故障定位面小）+ 样例波各自成块（W6 galgame/tactical、
  W7 sandbox——sandbox 依赖 W4 长动作执行器 + W3 知识面，置 W7 保序）；
  任务书「建议 ≤7 波」= 7 波顶格合规。
- **机械验证面**：§3.18 表逐波累计数 + 门③ 六步（§3.21）③ 步恒等式。

### D-P9-16 计数恒等式（门③期望 3142）

- **问题**（自裁）：门③ passed 计数期望如何钉？
- **选择**：**3142 = 3054（基线，§0.3 实测）+ 82（P9 平铺函数，§6.1 逐表
  合计）+ 6（TestP9Boundary 方法，§3.20）**；导出台账 = 71 名 / 15 文件
  （§8.2）；A 判据 = 24（16 门面 + 8 辅助，§5.2）。
- **理由**：P8 先例恒等式形（2925+123+6=3054）同构——基线 + 本阶段平铺
  + 边界方法 = 门期望；三项各自可机械复数（pytest / §6.1 表 / §3.20 表）。
- **机械验证面**：门③ ③ 步 + ⑥ 步（台账实数核对）+ §8.3 恒等式推导。

---

## §5 验收面

### 5.1 SC 场景（失败想象 → 机械面）

- **SC-P9-1 感知变全局**：若实现把 `build_observations` 输入扩为含
  event_log（「顺手」注入），T10 回归 t6 红（界外 NPC memory 变更）→
  签名级局部性（§3.6）+ A9 双面钉死。
- **SC-P9-2 迁移静默丢弃**：若 M-6 折叠丢失 append 文本或 M-7 静默吞
  disable 引用，A16（四输入预期诊断面）/ A22（码闭集）/ D-ε（IR 同构）
  必红；S3 预检（§0.7）= 流程面双保险。
- **SC-P9-3 模块越界 import**：若 attributes「顺手」import
  engine_v2.modules.scenario（requires 未声明），边界方法 4 红（AST
  闭集）+ A20（白名单树面）——双机械面。
- **SC-P9-4 词表泄漏**：若 narration docstring 写入真实供应商名，边界
  方法 3 / A19 红（12 名扫描含 docstring）。

### 5.2 A 判据表（24 条：A1–A16 门面条 + A17–A24 辅助面）

> **命名口径**：机械验证面列用短名形 `module.py::tN_<语义>`；规范
> pytest 收集名以 §5.3 1:1 清单为准（24 行一一对应；函数
> 命名规则见 §6.1 引言——`test_<短名>_tN_<语义>`，三个公共面文件
> 裸 `test_tN_<语义>` 形）。

| ID | 可验证陈述 | 机械验证面 |
|---|---|---|
| A1 | galgame 样例：player 对 yuki 发起 talk，脚本 backend 回应文本出现在 `DialogueResult.response` 且经事件流可达叙事帧 | `test_g9_galgame.py::t1_dialogue` |
| A2 | galgame 样例：wakeup 后的 yuki 经 `NpcBehaviorPolicy.decide` 产出 `ActionProposal`（type = talk，参数含 player 引用） | `test_g9_galgame.py::t2_character_policy` |
| A3 | galgame 样例：对话回合后 yuki→player `RelationshipState.affinity` 变化值 = `dialogue_relationship_delta` 钉值，事件在组件面可见 | `test_g9_galgame.py::t3_relationship_update` |
| A4 | galgame 样例：player 观察产出 ≥2 条 `ObservationRecord`（yuki/lena，kind=sight），且 records 不含任何事件文本字段 | `test_g9_galgame.py::t4_observation` |
| A5 | galgame 样例：`render_narrative_view` 输出 `json.dumps` 零失败（JSON-clean）+ 含 tick/frames/actors_visible 键 + 修改 view 后 WorldState 哈希不变（非权威） | `test_g9_galgame.py::t5_narrative_view` |
| A6 | sandbox 样例：duration=3 的动作 tick0 start → tick0–2 RUNNING → tick3 COMPLETED（lifecycle 状态序列钉） | `test_g9_sandbox.py::t1_long_action` |
| A7 | sandbox 样例：N 个逻辑 tick 后游戏分钟 = N × 0.5（scenario 声明 ticks_per_game_minute），逐 tick 值钉（零 wall-clock） | `test_g9_sandbox.py::t2_world_time` |
| A8 | sandbox 样例：仅 wakeup merchant 的 tick 上 backend 调用计数 = 1（merchant）；同 tick wanderer 零调用；未 wakeup 的 tick 零调用 | `test_g9_sandbox.py::t3_npc_wakeup` |
| A9 | sandbox 样例：同地点 merchant 有观察记录；异地点 wanderer 的 KNOWLEDGE/MEMORY 组件哈希在该 tick 前后逐字节不变 | `test_g9_sandbox.py::t4_knowledge_boundary` |
| A10 | sandbox 样例：`run_dynamics_turn` + `LLMWorldDynamics`（脚本 backend）产出 ≥1 ProposedEffect 且效果经宿主应用后世界可见变更 | `test_g9_sandbox.py::t5_llm_dynamics` |
| A11 | sandbox 样例：`RuleDynamics` 在规则条件命中 tick 产出效果（命中 tick 序号钉），非命中 tick 零效果 | `test_g9_sandbox.py::t6_rules_dynamics` |
| A12 | tactical 样例：3×3 hex 邻接边表 = 22 边（对称去重）+ 对角 hex `distance_between` = 2；`GridSpace(3,3)` 曼哈顿对照值钉 | `test_g9_tactical.py::t1_hex_space` |
| A13 | tactical 样例：战术模式下 `is_action_available`：attack 允许 / talk 拒绝（overlay 合并面） | `test_g9_tactical.py::t2_tactical_mode` |
| A14 | tactical 样例：attack 执行全程 `FakeInferenceBackend.calls` 为空（零推理调用）+ 同输入二次执行效果流逐条相等 | `test_g9_tactical.py::t3_deterministic_action` |
| A15 | tactical 样例：探索→战术→探索两次 `apply_mode_change` 成功，终态动作集 = 探索集；全程单一 WorldState（tick 连续无重建） | `test_g9_tactical.py::t4_mode_transition` |
| A16 | G9 并且①：test_empty/whisperheads/murder 迁移 status=migrated 且输出经 `load_project`+`validate_project` 零 ERROR；simulation.yaml status=incompatible 且含 `MIGRATION_DEPLOYMENT_FIELD`；一切诊断 ∈ 9 码闭集 | `test_v1_migration.py::t1_gate_migration_clause` |
| A17 | 迁移 test_empty 输出与 P5 zero_python 镜像的 IR 逐节相等；唯一差异 = items 节（P5 D-01 披露：4 条 items，state 折叠串逐值钉） | `test_p9_differential.py::t5_zero_python_isomorphism` |
| A18 | 13 模块各暴露 `IDENTITY: ModuleIdentity`；`OFFICIAL_MODULE_IDS` = 13 名闭集（Spec §40 逐字序）；版本全 = "1"（P5 文法）；requires 图无环（P5 `find_cycles` 零环） | `test_module_face.py::t2_ids_closed`（t1/t3/t4 同族辅助断言） |
| A19 | P9 src 15 文件全部字符串字面量（含 docstring）× 12 名黑名单零命中（大小写不敏感） | `test_module_face.py::t7_no_inference_names`（+ 边界方法 3 同源检查） |
| A20 | `src/engine_v2/modules/` 文件树 == 白名单 15 文件（+ 占位 `__init__.py`）；`tests/engine_v2/modules/` == 15 文件；3 样例 fixture 项目 == 15 文件 | `test_module_face.py::t6_src_tree_whitelist` |
| A21 | 15 文件 `__all__` 逐文件导出名/计数 == §8.2 台账（71 名）；`MIGRATION_DIAGNOSTIC_CODES` 9 名 | `test_module_face.py::t5_export_ledger` |
| A22 | 四输入迁移报告的全部诊断 code ∈ `MIGRATION_DIAGNOSTIC_CODES`（且 severity ∈ {ERROR,WARNING,INFO} 闭集） | `test_v1_migration.py::t7_codes_closed` |
| A23 | sandbox 样例完整切片（步骤 1–7）同 seed 同脚本双跑：效果流逐条相等 + 迁移三项目输出目录 sha256 双跑相等 | `test_g9_sandbox.py::t8_determinism_rerun`（+ 差分 D-δ 同面） |
| A24 | sandbox 终局 WorldState 经 P8 冻结快照面 round-trip：零版本冲突 + JSON-clean | `test_p9_differential.py::t6_persistence_roundtrip` |

### 5.3 A ↔ 平铺函数 1:1 映射（24 行；每 A 恰 1 函数，每门面条函数恰 1 A）

| A | 测试文件::函数 |
|---|---|
| A1 | `test_g9_galgame.py::test_g9_galgame_t1_dialogue` |
| A2 | `test_g9_galgame.py::test_g9_galgame_t2_character_policy` |
| A3 | `test_g9_galgame.py::test_g9_galgame_t3_relationship_update` |
| A4 | `test_g9_galgame.py::test_g9_galgame_t4_observation` |
| A5 | `test_g9_galgame.py::test_g9_galgame_t5_narrative_view` |
| A6 | `test_g9_sandbox.py::test_g9_sandbox_t1_long_action` |
| A7 | `test_g9_sandbox.py::test_g9_sandbox_t2_world_time` |
| A8 | `test_g9_sandbox.py::test_g9_sandbox_t3_npc_wakeup` |
| A9 | `test_g9_sandbox.py::test_g9_sandbox_t4_knowledge_boundary` |
| A10 | `test_g9_sandbox.py::test_g9_sandbox_t5_llm_dynamics` |
| A11 | `test_g9_sandbox.py::test_g9_sandbox_t6_rules_dynamics` |
| A12 | `test_g9_tactical.py::test_g9_tactical_t1_hex_space` |
| A13 | `test_g9_tactical.py::test_g9_tactical_t2_tactical_mode` |
| A14 | `test_g9_tactical.py::test_g9_tactical_t3_deterministic_action` |
| A15 | `test_g9_tactical.py::test_g9_tactical_t4_mode_transition` |
| A16 | `test_v1_migration.py::test_t1_gate_migration_clause` |
| A17 | `test_p9_differential.py::test_t5_zero_python_isomorphism` |
| A18 | `test_module_face.py::test_t2_ids_closed` |
| A19 | `test_module_face.py::test_t7_no_inference_names` |
| A20 | `test_module_face.py::test_t6_src_tree_whitelist` |
| A21 | `test_module_face.py::test_t5_export_ledger` |
| A22 | `test_v1_migration.py::test_t7_codes_closed` |
| A23 | `test_g9_sandbox.py::test_g9_sandbox_t8_determinism_rerun` |
| A24 | `test_p9_differential.py::test_t6_persistence_roundtrip` |

> 非 A 平铺函数（82 − 24 = 58）= 模块单元面 + 样例前件（项目加载 t6/t7
> 类）+ 差分辅助面（§6.1 逐表列明，不挂 A 但计入 82）。

---

## §6 测试设计

### 6.1 平铺函数清单（13 文件 × t# 表；合计 **82**）

> 函数名 = `test_<短名>_tN_<语义>`；三个公共面文件 `test_v1_migration`/
> `test_p9_differential`/`test_module_face` 用裸 `test_tN_<语义>` 形；
> A 面函数名与 §5.3 逐字一致。

**`test_attributes.py`（12）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_attributes_t1_clamp_within` | `clamp_value` 区间内原值 |
| 2 | `test_attributes_t2_clamp_bounds` | 越界 → min/max 钉值 |
| 3 | `test_attributes_t3_apply_delta_unlocked` | `apply_delta` 未锁 + 事件面（old/new/reason） |
| 4 | `test_attributes_t4_apply_delta_locked` | locked → `LockedAttributeError`（消息含属性名，v1 :25 对齐） |
| 5 | `test_attributes_t5_apply_new_value_locked` | `apply_new_value` locked 拒绝（v1 :37 对齐） |
| 6 | `test_attributes_t6_apply_new_value_clamped` | 未锁新值钳制 |
| 7 | `test_attributes_t7_natural_deltas` | `compute_natural_deltas` 3 tick × 2 属性钉值 |
| 8 | `test_attributes_t8_lock_condition_dsl` | `evaluate_lock_condition` 条件真/假双面（P5 DSL） |
| 9 | `test_attributes_t9_derive_attributes` | 派生属性 DSL 求值 + 零反写源字段 |
| 10 | `test_attributes_t10_snapshot` | `take_attribute_snapshot`（hidden+locked 创建面，v1 :866 对齐） |
| 11 | `test_attributes_t11_summarize_hidden` | `summarize_attributes_for_prompt` 隐藏属性零泄漏 + 键序钉 |
| 12 | `test_attributes_t12_v1_parity_case` | 钉死夹具（10 属性 × 3 变更）与 v1 `apply_attribute_changes` 同序同值（D-α 单元面） |

**`test_inventory.py`（6）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_inventory_t1_item_state_roundtrip` | `ItemState` 冻结面 + state 扁平串 |
| 2 | `test_inventory_t2_can_carry_under` | `can_carry` 限内 allowed（strength×50 面） |
| 3 | `test_inventory_t3_can_carry_over` | 超限 → allowed=False + reason 钉 |
| 4 | `test_inventory_t4_apply_pickup` | `apply_pickup` 位置转移 + 事件 |
| 5 | `test_inventory_t5_apply_drop` | `apply_drop` 镜像 |
| 6 | `test_inventory_t6_item_summary` | prompt 文本确定性 |

**`test_relationships.py`（4）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_relationships_t1_init_from_v1_dict` | v1 dict（含 whisperheads 形状样例）→ 有序元组 |
| 2 | `test_relationships_t2_adjust_clamped` | 越界夹取 [-1,1]（DEV-P9-05 面） |
| 3 | `test_relationships_t3_adjust_new_target` | 缺席目标新建（初值 0.0） |
| 4 | `test_relationships_t4_summary` | prompt 文本确定性 |

**`test_character.py`（4）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_character_t1_build_record` | `build_character_record`（CharacterSpec → 冻结记录） |
| 2 | `test_character_t2_policy_proposes` | `NpcBehaviorPolicy.decide`（脚本 backend）→ `ActionProposal` 面 |
| 3 | `test_character_t3_actor_mismatch` | `PolicyActorMismatchError`（core :107 透传面） |
| 4 | `test_character_t4_context_persona` | `PolicyPromptContext` 含 personality 文本（模板渲染面） |

**`test_perception_knowledge.py`（7）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_perception_knowledge_t1_sight_in_radius` | 半径内实体 → ObservationRecord（sight） |
| 2 | `test_perception_knowledge_t2_sight_out_of_radius` | 界外零记录 |
| 3 | `test_perception_knowledge_t3_hearing_only` | 听觉半径单独命中（kind 分类面） |
| 4 | `test_perception_knowledge_t4_belief_update` | `apply_observations` → Belief 集新增 |
| 5 | `test_perception_knowledge_t5_memory_cap` | `memory_append` cap=50 丢弃最旧（v1 :559 对齐） |
| 6 | `test_perception_knowledge_t6_no_global_event_leak` | **T10 回归**：事件发生后界外 NPC KNOWLEDGE/MEMORY 哈希不变（v1 对照 = game_graph.py:553–561 行为，v2 期望差钉死） |
| 7 | `test_perception_knowledge_t7_knowledge_summary` | prompt 文本确定性 |

**`test_scenario_trigger.py`（4）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_scenario_trigger_t1_fires` | 条件真 → firing（+ 效果/提案面） |
| 2 | `test_scenario_trigger_t2_not_fires` | 条件假 → 零 firing |
| 3 | `test_scenario_trigger_t3_once_semantics` | `once=True` 二次 tick 零 firing |
| 4 | `test_scenario_trigger_t4_priority_order` | 多触发器 (priority 降, id 升) 确定性序 |

**`test_action_executors.py`（6）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_action_executors_t1_move_graphspace` | `MoveExecutor` 经 `GraphSpace` 邻接移动成功 |
| 2 | `test_action_executors_t2_move_grid` | `GridSpace` 曼哈顿邻移 |
| 3 | `test_action_executors_t3_move_invalid` | 不可达 → `failure` 面（零状态变更） |
| 4 | `test_action_executors_t4_long_action_duration` | `duration_ticks` 面 + `start_action` 生命周期（与 A6 同机制，单元级） |
| 5 | `test_action_executors_t5_feasibility_dsl` | 动作条件经 P5 `check_action_feasibility`（:1169）判定面 |
| 6 | `test_action_executors_t6_register_idempotent` | `register_standard_actions` 幂等（重复注册覆盖 + 诊断） |

**`test_v1_migration.py`（7）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_t1_gate_migration_clause` | **A16**：四输入预期（§3.15.4 表）逐输入断言 |
| 2 | `test_t2_object_state_folded` | M-4 折叠规范串逐值钉（`closed=true,unlocked=false` 形态） |
| 3 | `test_t3_whisperheads_rule_ref_warning` | whisperheads：WARNING ×1（physics.disable [8]，M-15 点名 8）+ 输出可加载 |
| 4 | `test_t4_murder_append_folded` | murder：append 10 条 → rules yaml 10 条 passthrough（id/description/priority 钉） |
| 5 | `test_t5_simulation_incompatible` | simulation.yaml：incompatible + `MIGRATION_DEPLOYMENT_FIELD` 点名 llm/agents |
| 6 | `test_t6_adversarial_injection_rejected` | 4 项敌对注入（tmp 夹具，AD-P9-2）：未知顶层键 → ERROR `MIGRATION_UNKNOWN_TOP_KEY`；角色 `id` 重复 → ERROR `MIGRATION_DUPLICATE_ID`；`world` 缺失或 locations 零条 → ERROR `MIGRATION_EMPTY_WORLD`；对象 `state` 非 dict（list/str）→ ERROR `MIGRATION_OBJECT_STATE_FOLDED`（M-10 shape 守卫分支） |
| 7 | `test_t7_codes_closed` | **A22**：四输入全诊断 ∈ 9 码闭集 + severity 闭集 |

**`test_g9_galgame.py`（6）**：`test_g9_galgame_t1_dialogue`（A1）/
`test_g9_galgame_t2_character_policy`（A2）/ `test_g9_galgame_t3_relationship_update`
（A3）/ `test_g9_galgame_t4_observation`（A4）/ `test_g9_galgame_t5_narrative_view`
（A5）/ `test_g9_galgame_t6_project_loads`（样例项目 `load_project`+
`validate_project` 零 ERROR 前件）。

**`test_g9_sandbox.py`（8）**：`test_g9_sandbox_t1_long_action`（A6）/
`test_g9_sandbox_t2_world_time`（A7）/ `test_g9_sandbox_t3_npc_wakeup`（A8）/
`test_g9_sandbox_t4_knowledge_boundary`（A9）/ `test_g9_sandbox_t5_llm_dynamics`
（A10）/ `test_g9_sandbox_t6_rules_dynamics`（A11）/
`test_g9_sandbox_t7_project_loads`（前件）/ `test_g9_sandbox_t8_determinism_rerun`
（A23）。

**`test_g9_tactical.py`（5）**：`test_g9_tactical_t1_hex_space`（A12）/
`test_g9_tactical_t2_tactical_mode`（A13）/ `test_g9_tactical_t3_deterministic_action`
（A14）/ `test_g9_tactical_t4_mode_transition`（A15）/
`test_g9_tactical_t5_project_loads`（前件）。

**`test_p9_differential.py`（6）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_t1_attribute_parity` | D-α：v1 `apply_attribute_changes`（attributes.py:999）vs v2 钉夹具逐值 |
| 2 | `test_t2_dsl_parity` | D-β：v1 `evaluate_condition`（condition_eval.py）vs P5 `evaluate_condition`（:903）8 条件逐条 |
| 3 | `test_t3_natural_delta_parity` | D-γ：v1 `compute_attribute_deltas_diff`（:59）vs v2 逐属性 |
| 4 | `test_t4_migration_byte_stable` | D-δ：三项目迁移双跑 sha256 相等 |
| 5 | `test_t5_zero_python_isomorphism` | **A17**：D-ε IR 同构 + items 差异披露钉 |
| 6 | `test_t6_persistence_roundtrip` | **A24**：D-ζ P8 快照 round-trip |

**`test_module_face.py`（7）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_t1_identities_present` | 13 模块 `IDENTITY` 面存在且字段类型正确 |
| 2 | `test_t2_ids_closed` | **A18**：id 闭集 + Spec §40 逐字序 |
| 3 | `test_t3_version_grammar` | 版本 "1" × 13 + P5 文法匹配 |
| 4 | `test_t4_requires_acyclic` | requires 图经 P5 `find_cycles` 零环 + 边 ⊆ 闭集 |
| 5 | `test_t5_export_ledger` | **A21**：15 文件 `__all__` == §8.2 台账 |
| 6 | `test_t6_src_tree_whitelist` | **A20**：src/tests/fixture 三树 == 白名单 |
| 7 | `test_t7_no_inference_names` | **A19**：12 名扫描零命中 |

**合计**：12+6+4+4+7+4+6+7+6+8+5+6+7 = **82**（与 §3.18 波表、§8.3
恒等式一致）。

### 6.2 conftest（`tests/engine_v2/modules/conftest.py`；零测试函数）

| fixture | 形 | 职责 |
|---|---|---|
| `p9_host` | factory fixture：`(project_dir, *, seed=20240501, backend_script: Mapping) -> P9Host` | 通用宿主（§3.16 协议）：`load_project`→`build_ir`→`validate_project`（断言零 ERROR）→ WorldState 构建 → 模块面注册 → 返回 host 对象（`.tick(n)` / `.world` / `.effects` / `.backend`） |
| `fixed_clock` | `FixedMonotonicClock`（adapter.py:71）实例 | D6 注入时钟 |
| `scripted_backend` | `FakeInferenceBackend`（adapter.py:296）+ 钉死脚本映射 | 全样例 LLM 面脚本化（脚本 = 测试侧常量，键含 scope+revision 形状对齐 P7 先例） |
| `dsl_rng` | `DslRng`（P5）包装（固定 seed） | DSL rand 族确定性（样例零 rand 路径，仅保证注入存在） |
| `p9_world_builder` | helper fixture：IR → WorldState + 组件 + 空间域 | 样例世界构建（三样例共用，参数 = 空间域构造器） |

> host 对象 = conftest 内私有类（零 src 落位）；其 tick 循环相位序 =
> scheduler 到期事件 → dynamics 轮 → 触发器 → 属性自然差 → 生命周期
> 推进（相位序常量钉于 conftest docstring，与 P7 host 相位同风格）。

### 6.3 AD 对抗族（AD-P9-1..4；并入 §6.1 相应 t#，不单列函数）

| AD | 对抗面 | 并入 |
|---|---|---|
| AD-P9-1 | 锁条件 DSL 注入：条件串含未知变量/除零 → `DslEvalError` 透传（不吞、不误锁） | t8（`test_attributes`） |
| AD-P9-2 | 迁移宿主敌对 yaml：v1 夹具注入未知顶层键 / 重复 id / 空 world / 对象 state 非 dict（list/str）→ 4 个 ERROR 面按 §3.15.3 绑定表钉死（`MIGRATION_UNKNOWN_TOP_KEY` / `MIGRATION_DUPLICATE_ID` / `MIGRATION_EMPTY_WORLD` / `MIGRATION_OBJECT_STATE_FOLDED` ERROR——M-10 shape 守卫分支，即 M-4 规则 shape 守卫） | t6（`test_v1_migration`） |
| AD-P9-3 | 模块 id 文法边缘：`parse_module_id` 对 `LLMSIM-STANDARD-X`（大写）/ `llmsim-standard-`（空尾）/ `standard-x`（前缀缺）全拒 | t2/t3（`test_module_face`）辅助断言 |
| AD-P9-4 | hex 越界/畸形：`HexGrid(cols=0)` 拒绝；`hex_adjacency` 单行网格（1×N）边表钉（无 6 邻退化） | t1（`test_g9_tactical`）辅助断言 |

### 6.4 fixture 钉（fixture pin）

- 白名单行 31–45 的 15 个 fixture yaml：一经所属波落盘（W6/W7），**跨波
  字节冻结**（后波只增新文件，不改既有 fixture）；W7 门③ diff 面复证。
- fixture 形状纪律：单文件 ≤ 150 行（R7）；yaml `sort_keys=True` 写出
  （与迁移器输出同纪律）；角色/物品 id 全小写蛇形（P5 `_ID_PATTERN` 面）。
- v1 输入夹具（public_start/ + config/）= 冻结只读（P9-INV-1）；测试侧
  敌对夹具（AD-P9-2）= `tmp_path` 生成，零仓内落盘。

---

## §7 映射表

### 7.1 任务 → SOT 章节（14 任务全落位）

| 任务 | SOT 章节 | 交付物 |
|---|---|---|
| P9-T01 | §2.3 + §3.1 + §3.20(方法 4) | 三态映射表（设计期）+ 机械面（W7） |
| P9-T02 | §3.2 | `modules/attributes.py` |
| P9-T03 | §3.3 | `modules/inventory.py` |
| P9-T04 | §3.4 | `modules/relationships.py` |
| P9-T05 | §3.5 | `modules/character.py` |
| P9-T06 | §3.6 + §3.7 | `modules/perception.py` + `modules/knowledge.py` |
| P9-T07 | §3.8 | `modules/scenario.py` |
| P9-T08 | §3.9 | `modules/actions.py` |
| P9-T09 | §3.15 | `modules/v1_migration.py` + `scripts/v2_migrate_v1.py` |
| P9-T10 | §3.7 + §6.1(t6) | T10 回归函数（`test_perception_knowledge.py::t6`） |
| P9-T11 | §3.10 + §3.14 + §3.16.1 | dialogue/narration 模块 + galgame 样例 |
| P9-T12 | §3.13 + §3.16.2 | dynamics 桥 + sandbox 样例 |
| P9-T13 | §3.11 + §3.12 + §3.16.3 | space/tactical 模块 + tactical 样例 |
| P9-T14 | §3.17 + §6.1 | 差分 6 函数 |

### 7.2 任务 → 波次 → 文件（§3.18 波表的转置视图）

| 波 | 任务 | src 文件 | test 文件 | 其它 |
|---|---|---|---|---|
| W1 | T02, T05 | base / attributes / character | test_attributes / test_character | — |
| W2 | T03, T04 | inventory / relationships | test_inventory / test_relationships | — |
| W3 | T06, T10 | perception / knowledge | test_perception_knowledge | — |
| W4 | T07, T08 | scenario / actions | test_scenario_trigger / test_action_executors | — |
| W5 | T09 | v1_migration | test_v1_migration | scripts/v2_migrate_v1.py |
| W6 | T11, T13 | dialogue / narration / space / tactical | test_g9_galgame / test_g9_tactical | fixture galgame(5) + tactical(5) |
| W7 | T12, T14, T01 机械面 | dynamics | test_g9_sandbox / test_p9_differential / test_module_face + TestP9Boundary(6 方法) | fixture sandbox(5) |

### 7.3 Spec 章节 → SOT 章节

| Spec 章节（行锚） | SOT 章节 |
|---|---|
| K1–K8 Kernel invariants（L242–339） | §8.1 矩阵 |
| §5 Project / Deployment Contract（L343–450） | §3.15（M-2/M-8 形状面；K8 部署分离） |
| §6 ProjectIR（L454–482） | §2.4（ProjectIR:496 16 字段消费面） |
| §8.5 ViewState（L626–638） | §3.14 + P9-INV-8 + A5 |
| §11 Action（L736–802；六固定动作 L743–748 / Registry yaml L757–768 / ActionProposal L774–785 / 生命周期 L791–802） | §3.9（43.2-4「fixed six」移除面：标准集 = 执行器库覆盖集，非固定类型） |
| §12.2 BehaviorPolicy（L814–838） | §3.5（NpcBehaviorPolicy 实现面） |
| §12.3 CharacterDefinition/State（L840–868） | §3.5（CharacterRecord 形状面） |
| §32 叙述渲染 text/image（L1678–1732） | §3.14（text 侧）+ §0.4（image = P10） |
| §40 Standard Modules（L1944–1966，13 模块名逐字） | §0.1 / §3.0 / §3.1.2（OFFICIAL_MODULE_IDS） |
| §41 requires 声明 + 依赖图检查（L1970–1985） | §3.1.2（MODULE_REQUIRES）+ §2.4（module_graph 11 名消费） |
| §25 GameplayMode/GameplayContext（L1396–1452） | §3.12（tactical overlay 消费面） |
| §43 v1→v2 迁移（L2056–2096；43.1 十一条 / 43.2 九条 / 43.3 九项） | §2.3 三态映射表（逐条挂接） |
| §44 源码树 modules/ + presentation/（L2100–2202；modules/ 树 L2145–2154 / presentation/ L2198–2201） | §3.0 包树（单包落位）+ §0.4（presentation = P10/P11） |
| §46 MVP 第 21 条族（L2273–2311） | §0.4 / §3.17（D-ζ 持久化面消费 P8 交付） |

### 7.4 G9 面 → A 判据 → 测试函数（16 门面条 1:1）

| G9 面（§0.2 表编号） | A | 函数（§5.3 逐字名） |
|---|---|---|
| G9-1 Galgame dialogue | A1 | `test_g9_galgame_t1_dialogue` |
| G9-2 Galgame character policy | A2 | `test_g9_galgame_t2_character_policy` |
| G9-3 Galgame relationship | A3 | `test_g9_galgame_t3_relationship_update` |
| G9-4 Galgame observation | A4 | `test_g9_galgame_t4_observation` |
| G9-5 Galgame narrative-ready ViewState | A5 | `test_g9_galgame_t5_narrative_view` |
| G9-6 Sandbox long action | A6 | `test_g9_sandbox_t1_long_action` |
| G9-7 Sandbox world time | A7 | `test_g9_sandbox_t2_world_time` |
| G9-8 Sandbox NPC wakeup | A8 | `test_g9_sandbox_t3_npc_wakeup` |
| G9-9 Sandbox knowledge boundary | A9 | `test_g9_sandbox_t4_knowledge_boundary` |
| G9-10 Sandbox LLM / rules dynamics（2 判据，D-P9-11） | A10 / A11 | `test_g9_sandbox_t5_llm_dynamics` / `test_g9_sandbox_t6_rules_dynamics` |
| G9-11 Tactical Grid/Hex-like Space | A12 | `test_g9_tactical_t1_hex_space` |
| G9-12 Tactical tactical GameplayMode | A13 | `test_g9_tactical_t2_tactical_mode` |
| G9-13 Tactical deterministic actions | A14 | `test_g9_tactical_t3_deterministic_action` |
| G9-14 Tactical mode transition | A15 | `test_g9_tactical_t4_mode_transition` |
| G9-15 并且① init file migration | A16 | `test_t1_gate_migration_clause` |
| G9-16 并且② LangGraph 非依赖 | （边界方法 4） | `TestP9Boundary::test_p9_import_closure` |

---

## §8 台账与计数

### 8.1 K1–K8 × P9 面矩阵

| Kernel 不变量 | P9 消费/接触面 | P9 机械验证面 |
|---|---|---|
| K1 WorldState 唯一状态权威 | 样例宿主经 WorldState（state.py:246）构建世界；narration 输出零反作用 | P9-INV-8 + A5（view 突变后世界哈希不变） |
| K2 producer 不直写 WorldState | 全部 15 模块文件 = 纯函数/reducer；状态变更仅产 ProposedEffect（effects.py:197）/新 dataclass 值，由宿主经 kernel 应用面落位 | P9-INV-3 + 边界方法 4（AST 零可变写模式）+ 各 A 行为面（组件哈希前后钉） |
| K3 Authority 裁决效果 | P9 模块不实现 authority；样例宿主经冻结 authority 面应用 ProposedEffect（conftest §6.2） | A10/A11（效果经裁决后可见）+ 边界方法 4（P9 零 authority import 新语义） |
| K4 Prompt 不能定义世界权限（Spec L295–303） | P9 prompt 上下文面（`summarize_attributes_for_prompt`/`PolicyPromptContext`/叙事帧）零权限/authority 声明；模块面不产任何 authority policy | P9-INV-8 + A5（view 突变零反作用于世界）+ 边界方法 4（AST 零 authority 面 import） |
| K5 kernel 不假设全员 NPC 决策 | `NpcBehaviorPolicy` 仅经 `enqueue_actor_wakeup`（scheduler.py:374）唤醒驱动；零「全员每 tick」循环 | D-P9-05 + A8（非 wakeup tick 零 backend 调用）+ A2（policy 提案面） |
| K6 Event 必须可追踪来源（Spec L315–324） | P9 事件（AttributeEvent/RelationshipEvent/BeliefEvent/TriggerFiring）= kernel 事件流载荷，provenance（transaction id/source producer/cause id/world revision/authority decision）由 kernel 补 | A3/A4 事件面（事件含 tick/actor 字段，宿主断言 provenance 非空） |
| K7 Runtime 关键调度状态必须可检查（Spec L326–328） | P9 模块无状态（零模块级可变对象）+ 组件数据 JSON-clean 序列化后可检查；零隐藏 continuation 状态 | A24（P8 快照 round-trip）+ 边界方法 6（import 后 `__dict__` 审计） |
| K8 部署与项目分离 | 迁移器拒 llm/agents 节入项目（M-17，`MIGRATION_DEPLOYMENT_FIELD`）；P9 src 12 名推词零命中 | P9-INV-4/10 + A16（simulation 面）+ A19 + 边界方法 3 |
| D6 确定性双跑（P9-INV-6；P9 纪律，非 Spec K 项） | 注入纪律：`LogicalClock`/`FixedMonotonicClock`/`DslRng`/脚本 backend 全注入；模块零 wall-clock/零全局 RNG | A14/A23（双跑效果流相等 + 迁移字节稳定） |

### 8.2 P9 导出台账（P9_EXPORT_LEDGER；15 文件 71 名；`__all__` 逐字按序 = §3 各节代码块）

| # | 文件 | 导出数 | 导出名（`__all__` 序） |
|---|---|---|---|
| 1 | `modules/base.py` | 5 | ModuleIdentity / OFFICIAL_MODULE_IDS / OFFICIAL_MODULE_VERSION / parse_module_id / UnknownModuleIdError |
| 2 | `modules/attributes.py` | 11 | AttributeField / AttributeEvent / LockedAttributeError / clamp_value / apply_delta / apply_new_value / compute_natural_deltas / evaluate_lock_condition / take_attribute_snapshot / summarize_attributes_for_prompt / derive_attributes |
| 3 | `modules/inventory.py` | 7 | ItemState / CarryLimit / CarryCheck / can_carry / apply_pickup / apply_drop / item_summary |
| 4 | `modules/relationships.py` | 5 | RelationshipState / RelationshipEvent / init_relationships / adjust_relationship / relationship_summary |
| 5 | `modules/character.py` | 5 | CharacterRecord / PolicyPromptContext / NpcBehaviorPolicy / build_character_record / build_npc_policy |
| 6 | `modules/perception.py` | 4 | PerceptionRange / ObservationSource / PerceptionResult / build_observations |
| 7 | `modules/knowledge.py` | 4 | BeliefEvent / apply_observations / memory_append / knowledge_summary |
| 8 | `modules/scenario.py` | 3 | ScenarioTrigger / TriggerFiring / check_triggers |
| 9 | `modules/actions.py` | 5 | STANDARD_ACTION_IDS / ActionExecutor / ExecutorResult / MoveExecutor / register_standard_actions |
| 10 | `modules/dialogue.py` | 3 | DialogueResult / dialogue_relationship_delta / run_dialogue |
| 11 | `modules/space.py` | 4 | HexGrid / hex_adjacency / distance_between / register_standard_space |
| 12 | `modules/tactical.py` | 4 | TACTICAL_ACTION_IDS / TacticalOverlaySpec / build_tactical_overlay / TacticalModePolicy |
| 13 | `modules/dynamics.py` | 2 | DynamicsBinding / build_standard_dynamics |
| 14 | `modules/narration.py` | 4 | NarrativeFrame / NarrativeStyle / NarrativeView / render_narrative_view |
| 15 | `modules/v1_migration.py` | 5 | MIGRATION_DIAGNOSTIC_CODES / MigrationDiagnostic / MigrationReport / migrate_project / migrate_simulation |
| — | **合计** | **71** | （5+11+7+5+5+4+4+3+5+3+4+4+2+4+5 = 71） |

> 占位 `modules/__init__.py`（9 行，§2.9）零导出（字节冻结，不 re-export——
> P5/P7/P8 占位先例同口径）；`MAPPING_RULES` 常量（§3.15.2）为模块私有
> 面，不入 `__all__`。

### 8.3 计数恒等式（门③期望 passed = **3142**；三项各自机械可复数）

```text
基线（§0.3 实测 @ aab029c）          3054
+ P9 平铺函数（§6.1 逐表）            82
    test_attributes 12 + test_inventory 6 + test_relationships 4
    + test_character 4 + test_perception_knowledge 7
    + test_scenario_trigger 4 + test_action_executors 6
    + test_v1_migration 7 + test_g9_galgame 6
    + test_g9_sandbox 8 + test_g9_tactical 5
    + test_p9_differential 6 + test_module_face 7 = 82
+ TestP9Boundary 方法（§3.20，锚文件 EOF 纯追加） 6
──────────────────────────────────────────
= 门③ 期望 passed                          3142
```

交叉恒等式（自检项，实现波次 W7 逐条复算）：

- 波表累计：16+10+7+10+7+11+21 = 82（§3.18）== §6.1 合计 82；
- 白名单 47 行 = 15 src + 15 tests + 15 fixtures + 1 script + 1 boundary-M（§3.19）；
- 导出 71（§8.2）= A21 台账核对基准；
- A 判据 24 = 16 门面条（§5.2 A1–A16，G9-10 双判据计入）+ 8 辅助（A17–A24）；
  24 函数 ⊆ 82 平铺函数（§5.3 1:1）；
- 诊断码 9（§3.15.3）∩ P5 18 码（schemas.py:112–133）= ∅（前缀 MIGRATION_* vs LLMSIM_*）。

### 8.4 偏差登记（DEV-P9-01..05；W0 时点全部已有处置）

| ID | 问题 | 处置 |
|---|---|---|
| DEV-P9-01 | 任务书「五+五+四」= 14 命名面；Plan G9「并且」段另有 2 条款（migration / LangGraph）——计数口径歧义 | 采纳 16 门面条口径（§0.1 登记；G9-15/A16 + G9-16/边界方法 4 分立承接）；任务书不改（SOT 为准，D8） |
| DEV-P9-02 | W0 初探 v1 src 行总数 = 5710（文件清单漏列 4 文件）vs 任务书 ≈6146 | 复测全量 34 文件 = 6146（与任务书一致）；初探作废，登记 §9 ERR-P9-01 |
| DEV-P9-03 | `modules/__init__.py` 占位 docstring 列 13 模块中 9 名（缺 actions/dialogue/dynamics/narration） | 字节冻结不改（§2.9 既有先例：填充包后占位 docstring 不更新）；13 名闭集以 `OFFICIAL_MODULE_IDS` 为唯一权威（A18 钉）；登记 §9 ERR-P9-03 |
| DEV-P9-04 | P5 zero_python 镜像偏差 D-01（test_empty 的 4 个 objects 未镜像） | P9 迁移器 M-4 规则正确承接 objects→items；A17 同构面把该差异钉为**唯一允许差异**（非静默）；P5 fixture 本身冻结不改 |
| DEV-P9-05 | v1 `relationships` float 无值域约束；v2 `RelationshipState.affinity` 夹取 [-1,1] | 有意偏差（v2 契约面收紧）；`adjust_relationship` 夹取行为由 t2 钉；差分面 D-α..D-ζ 不覆盖 relationships（v1 无 parity 函数可引——记录为差分覆盖边界） |

---

## §9 勘误（errata）

> 纪律（D8）：本节为 P9 行锚/口径勘误**唯一规范记录**；历史条目不追改；
> 实现波次勘误按 ERR-P9-NN 续编（ERR-P8-01..07 先例，G8 报告 L203–204）。
> W0 种子条目（格式先例 = P8 SOT §9 表形）：

| ID | 类型 | 勘误 | 更正 | 状态 |
|---|---|---|---|---|
| ERR-P9-01 | 口径 | W0 初探「v1 src 合计 5710 行」及初版口径「30 `.py`（含 11 个 `__init__.py`）」 | 全量 34 `.py`（含 10 个 `__init__.py`）合计 **6146 行**（`find src -name '*.py' -not -path '*/engine_v2/*' -exec wc -l {} +` @ aab029c 实测）；任务书 ≈6146 正确，初探漏列 `src/agents/init.py`/`src/config/loader.py`/`src/models/__init__.py`/`src/ui/cli.py` 等文件，文件计数亦同批更正（§0.3/§2.3 已按实测落表） | W0 定案（§0.3 已按更正值落表） |
| ERR-P9-02 | 口径 | 任务书「五+五+四」G9 面计数 | Plan G9（L786–814）「并且」段 2 条款独立于 14 命名面 → SOT 口径 = **16 门面条**（§0.1/§5.2；A16 + 边界方法 4 分立承接） | W0 定案（§0.1 已落口径） |
| ERR-P9-03 | 披露 | `modules/__init__.py` 占位 docstring 仅列 9 模块名（缺 actions/dialogue/dynamics/narration） | 占位字节冻结（§2.9 先例）；官方 13 名闭集以 `modules/base.py::OFFICIAL_MODULE_IDS` 为唯一权威（Spec §40 逐字，A18 机械钉）；占位文案不更新（与 persistence/dynamics 占位同惯例） | W0 定案（§2.9 已落披露） |
| ERR-P9-04 | 口径/锚 | W0 设计盲评 R1（4 人全 SUPPLEMENT；findings 合计 45 = 19 SUPPLEMENT 级 + 21 DOC 级 + 5 INFO 级；跨评审人去重后裁决修正 18 项 + 合法面/他层 3 项）修正明细：(1) §0.3 v1 冻结锚行「diff = ∅（实测空）」为假——实测 24 条既成条目（1 M pyproject.toml + 23 A = 3 v1 测试 + 20 v2_* fixture，均 P1–P8 产物；src/public_start/config 子集确为空；评审 3 人计「25」系误计，byte-truth = 24），已改写为如实陈述 + P9-INV-1 冻结范围收窄至「自 aab029c 起不变」+ 方法 5 清单时点注明 W7；(2) rules.py 锚 8→9（2 处，`STRENGTH_TO_KG_FACTOR` def 实测 :9）；(3) condition_eval.py 锚 :113→def :35（D-β 行）；(4) game_state.py `GameState` 锚 23→9（world_rules 字段 :23 不变）；(5) Spec §40 列表行范围 L1948–1962→L1951–1963（2 处）；(6) 「Spec §42 GameplayMode（L1989–2052）」→「Spec §25 GameplayMode/GameplayContext（L1396–1452）」（2 处，Spec #42 实为测试层级）；(7) §2.3 补「§43.1 十一条/§43.2 九条逐条挂接核对」表（原缺 43.1-2 YAML authoring、43.2-7 global GameState 两条挂接；现 20/20 全挂接）；(8) §0.3 core 行核验命令 `grep -c '"'`（对单引号条目返回 0）→ `grep -c "^    '"`（实测 308）；(9) D2 行宽自指断言「本文件…零命中」为假（SOT 实测 273 表格行 >100）→ D2 作用域收窄为 P9 产物（src/tests/scripts），SOT 自限「非表格行零命中（表格行豁免，P8 先例）」；(10) §8.1 K 矩阵三行错标 Spec 不变量（K4 行实为 Spec K6 内容/K6 行「确定性」非 Spec K 项/K7 行非 Spec K7）→ 按 Spec L295–303（K4）/L315–324（K6）/L326–328（K7）重标，「确定性双跑」降为标注行「D6（P9 纪律，非 Spec K 项）」；(11) §8.1 K5 行机械验证面「P9-INV（D-P9-05）」悬空引用 → 「D-P9-05 + A8 + A2」；(12) §2.7 「表见 §3.18.3」→「§3.20」（§3.18 无子节）；(13) §2.10「既有 6 项目目录」→「7」（与磁盘 ls 及方法 6(d) 对齐）；(14) 方法 5 清单「30 src .py」→「34」（ERR-P9-01 已更正口径的残留）；(15) §6.1 头命名约定补三公共面文件裸 `test_tN_` 形说明（原声明与 3 文件实际命名不符）；(16) D-P9-01/04/05/06 四个非自裁决策补「备选」段（§4 五段式契约）；(17) §0.1 T02 行补 base.py 同波 W1 落盘注；(18) §0.3 Python 环境行补「冻结 pyproject 声明的 v1 树 10 依赖 P9 零消费」注；(19) 评审报告自述 3 处裸 0x5C 0x62 序列（L146/L436/L514）经裁决为 D3 自命名合法面，不修改；(20) R4-F14 任务书（`.p9/w0-brief.md`）层「v1 路径集 diff 为空」同口径错误 = brief 层，不追改任务书，以本 SOT 为准；(21) R1 评审「25 条」误计 1 处 = 评审层，以 byte-truth 24 为准 | W0 定案（正文已按更正值落表；实现波次复测以 `git diff aab029c..HEAD` + `sed -n` 为准） |
| ERR-P9-05 | 口径/锚 | W0 设计盲评 R2（4 人全 SUPPLEMENT；findings 合计 24 = 6 SUPPLEMENT + 7 DOC + 11 INFO；跨评审人去重后：13 项裁决修正〔SOT 层 18 处 findings 归并〕+ 合法面/他层 6 项〔brief 层 4 + 文档化变体 1 + 备查 1〕）修正明细：(1) **撤回 ERR-P9-04(1)(21) 之误计裁决**——v1 路径集 diff 实测 = **25** 条既成条目（1 M `pyproject.toml` + 24 A = 4 个 v1 测试侧 `.py`（`char_helpers.py`/`test_char_graph.py`/`test_char_nodes.py`/`test_engine_v2_skeleton.py`）+ 20 个 `v2_*` fixture，均 P1–P8 产物）；ERR-P9-04 之 24 计数系子串过滤 `grep -v 'engine_v2'` 误排 `tests/test_engine_v2_skeleton.py`（`tests/` 顶层文件，属 v1 路径集成员），R1/R3/R4 评审 25 计数 = byte-truth，§0.3/P9-INV-1 按 25 更正，核验命令排除口径改「仅排除 `src/engine_v2/` + `tests/engine_v2/` 两子树，子串过滤禁用」；(2) murder.yaml `world_rules` append 实测 = 10 条（physics 5 + attribute 5，:783–799），§6.1 T09 t4 行 8→10（whisperheads 8 条实测正确，不变）；(3) §3.15.2 补 M-id 命名空间声明（M-1..M-9 = 映射规则 id；M-10..M-17 = 规则附着诊断事件 id）+ §3.15.3 补 M-id 绑定表（9 码全绑定；M-11 双绑定 = 顶层键缺失族两分支显式化；`MIGRATION_EMPTY_WORLD` = 唯一无 M-id 码，触发 = M-1 前置），MAPPING_RULES 段、M-1/M-4 诊断列、frozenset 两条注释同步；(4) AD-P9-2 非 dict state shape 违规钉 `MIGRATION_OBJECT_STATE_FOLDED` ERROR（M-10 shape 守卫分支）；t6 钉面扩至 4 项敌对注入并更名 `test_t6_adversarial_injection_rejected`（82 平铺函数总数不变）；(5) §5.2 补命名口径注（机械验证面短名形 ↔ §5.3 规范收集名 1:1）；(6) §0.3 Python 环境行 import 闭集改「stdlib + pydantic + `engine_v2` 冻结根（§3.0 闭集表）」（原「仅 stdlib + pydantic」与 §3.0 矛盾）；(7) Spec §25 上界「L1396–1455」→「L1396–1452」×2（§3.12 来源行/§7.3 行；内容末 = L1452「由 ModePolicy 解析。」）；(8) Plan G9 围栏题注与 §0.1 口径行「L786–814」→ 围栏 = 正文 L788–813（L786–787 = `## G9` 标题/空行、L814–815 = 尾随空行/节界；「并且」2 条款 = L810–813）；(9) §3.16.2 A6 `transition_action` :257 补模块归属（action_lifecycle.py:257）；(10) §2.3 attributes 行「函数级见下表」→「函数级见 §3.2 函数级锚表」（§2.3 内唯一函数表 = game_graph 的；§3.2 来源行、D-P9-04 行同步）；(11) §3.19 自检注「13 个测试文件（含 2 非测试文件）」→「15 文件 = 13 个测试文件 + 2 个非测试文件」；(12) G8 报告行锚 3 处：§0.4 D-P7-13 行 → L203（短语实位，条款跨 L202–203）、D8 纪律行与 §9 续编注 → L203–204（勘误链纪律句跨）；(13) §0.4 真机 runtime host 行「P1（Plan §15 之前）」→「P1（Plan §10；冻结 `engine_v2/runtime/` 面）」（Plan §15 = Phase 6 LLM Runtime，Plan 全文无进程入口/REPL 条目；SOT 内依据 = §2.3 `src/main.py` 行/`game_graph` 行）。合法面/他层（不修改）：R1-F03/R2-F04/R3-F06/R4-F07 = brief 层（任务书与旧 brief 不追改，ERR-P9-04(20) 先例；R3 任务书派工前更正 C3 前提与 K 范围）；R4-F04 = G9-16 无 A id 文档化变体（§0.2/§7.4/§8.3/ERR-P9-02 四方一致，登记备查）；R4-F06 = Plan §24 范围声明精确（S1–S5 = L1212–1288 子区间，备查） | W0 定案（正文已按 (1)–(13) 更正值落表；本条为 ERR-P9-04(21) 之唯一规范撤回记录，历史条目不追改；实现波次复测以 `git diff aab029c..HEAD` + `sed -n` 为准） |

（后续实现波次勘误按 ERR-P9-NN 续编；行锚漂移以 `git diff aab029c..HEAD`
+ `sed -n` 复测为准，登记时附复测命令与输出摘要。）

---

*—— P9 W0 设计 SOT 终；实现波次（W1–W7）以本文件为唯一依据，门③
六步（§3.21）收口。 ——*

