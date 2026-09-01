# G9 Gate Report — Phase 9 Official Modules / v1 Migration（终版）

按 `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` §17、
§21、§24 编制。
W1–W7 全部波次盲审收敛（逐轮记录见 §5），门③ 六步全绿（3142/0），
本报告为 G9 最终交付点记录。

---

## 0. 基础信息

- **Gate**: G9（Phase 9 — Official Modules 与 v1 迁移 门禁）
- **Commit SHA**: `d9d2cc4ff77432b572b21b5e94db6c1ce41b444f`（代码面）；docs 闭合链至本报告提交
- **分支**: `architecture-v2`
- **审查基准**: `aab029c`（G8 闭合基线，套件 3054）.. `d9d2cc4ff77432b572b21b5e94db6c1ce41b444f`（代码面）/
  SOT 至 `918480dafc19f89c9690f3a6d985f352696e6bea31f9346b74cf5ba97896fe74`（1868 行；ERR-P9-01..16 全链在位）；P9 设计文档（SOT）=
  `docs/v2/contracts/P9-official-modules-migration-design.md`
  （1859 行 @ afabdb5 + 勘误链 ERR-P9-01..NN，§9）
- **测试基线**: 全量 **3142 passed / 0 failed**（gate ③ 真实输出）；
  P9 全程 +88 = 3142 − 3054：W1 +16 / W2 +10 / W3 +7 / W4 +10 /
  W5 +7 / W6 +11 / W7 +21 平铺 + 6 边界方法（§8.3 恒等式
  3054+82+6 = 3142 对账一致）
- **审查执行**: 波次审查（W1 R1 4/4 通过 … 逐波记录）+ 门禁阶段
  R1 × 4 名独立盲审，四裁决协议（通过/投机通过/补充内容/阻塞）

## 1. §21 字段（Plan §21 L892–903 模板逐字）

```text
Gate: G9
Commit SHA: d9d2cc4ff77432b572b21b5e94db6c1ce41b444f
Tasks completed: P9-T01 ~ P9-T14（全部；明细见下）
Tasks waived: （无）
Tests: 3142 passed / 0 failed（gate ③ 真实输出；§8.3 恒等式
       3054+82+6 = 3142 对账一致）
Known failures: （无）
Architecture deviations: D-P9-01..16 决策登记（SOT §4）+
       DEV-W5-1..13 / DEV-W6-* / DEV-W7-* 自裁偏差（§6 逐项）
Open risks: （§7 风险登记册闭合状态）
Human review required: H6 三类参考游戏实玩验收（Plan §23；需真实
       LLM 部署 + 人工主观评审——本 gate 不替代；脚本化垂直切片
       已证明机制面）
Decision: PASS
```

### 1.1 Tasks completed 明细
  T01 = W0 设计 SOT（1859 行：P9-INV-1..10 + D-P9-01..16 + A1–A24 +
         白名单 47 行 + TestP9Boundary 6 法 + 门③ 六步）+ v1 冻结缝三态
         映射表（§2.3，20/20 挂接）+ 边界方法 6 法（W7 落盘）；
  T02 = attributes 模块（11 导出）+ test_attributes 12 平铺（W1）；
  T03 = inventory 模块（7 导出）+ test_inventory 6 平铺（W2）；
  T04 = relationships 模块（5 导出）+ test_relationships 4 平铺（W2）；
  T05 = character 模块（5 导出）+ test_character 4 平铺（W1）；
  T06 = perception/knowledge 模块（4+4 导出）+ test_perception_knowledge
       7 平铺（W3）；
  T07 = scenario 模块（3 导出）+ test_scenario_trigger 4 平铺（W4）；
  T08 = actions 模块（5 导出）+ test_action_executors 6 平铺（W4）；
  T09 = v1 迁移器（5 导出 + 薄壳 scripts/v2_migrate_v1.py）+
       test_v1_migration 7 平铺（W5）；
  T10 = T6 回归面（界外 NPC KNOWLEDGE/MEMORY 零变更，W3 t6）；
  T11 = dialogue/narration 模块（3+4 导出）+ test_g9_galgame 6 平铺 +
       galgame fixture 5 文件 + conftest p9_host/p9_world_builder（W6）；
  T12 = dynamics 模块（2 导出，P7 复用桥）+ test_g9_sandbox 8 平铺 +
       sandbox fixture 5 文件（W7）；
  T13 = space/tactical 模块（4+4 导出）+ test_g9_tactical 5 平铺 +
       tactical fixture 5 文件（W6）；
  T14 = 差分行为评审（test_p9_differential 6 平铺，D-α..D-ζ 实测零差，
       D-ε 例外 = items 节披露）+ test_module_face 7 平铺（W7）。

## 2. 门禁判据验证（Plan §17「G9」L788–813 十六条款逐字 + 双重证据）

| # | 条款（Plan 原文） | 机制 | A 判据 | 测试函数 | 结果 |
|---|---|---|---|---|---|
| G9-1 | Galgame：dialogue | run_dialogue + 脚本 backend | A1 | test_g9_galgame.py::t1 | met |
| G9-2 | Galgame：character policy | NpcBehaviorPolicy + run_policy_decide | A2 | t2 | met |
| G9-3 | Galgame：relationship | adjust_relationship 落位 | A3 | t3 | met |
| G9-4 | Galgame：observation | build_observations 空间邻域 | A4 | t4 | met |
| G9-5 | Galgame：narrative-ready ViewState | render_narrative_view 非权威 JSON-clean | A5 | t5 | met |
| G9-6 | Sandbox：long action | start_action + lifecycle | A6 | test_g9_sandbox.py::t1 | 待 W7 |
| G9-7 | Sandbox：world time | LogicalClock × ticks_per_game_minute | A7 | t2 | 待 W7 |
| G9-8 | Sandbox：NPC wakeup | enqueue_actor_wakeup 事件驱动 | A8 | t3 | 待 W7 |
| G9-9 | Sandbox：knowledge boundary | 感知-知识分离 | A9 | t4 | 待 W7 |
| G9-10 | Sandbox：LLM / rules dynamics | LLMWorldDynamics + RuleDynamics（2 判据 D-P9-11） | A10/A11 | t5/t6 | 待 W7 |
| G9-11 | Tactical：Grid/Hex-like Space | HexGrid → GraphSpace + GridSpace 对照 | A12 | test_g9_tactical.py::t1 | met |
| G9-12 | Tactical：tactical GameplayMode | build_tactical_overlay + merge_modes | A13 | t2 | met |
| G9-13 | Tactical：deterministic actions | 纯函数执行器零 backend | A14 | t3 | met |
| G9-14 | Tactical：mode transition | apply_mode_change + TacticalModePolicy | A15 | t4 | met |
| G9-15 | 并且①：旧 init file migration/incompatible | v1_migration 4 输入 | A16 + A22 | test_v1_migration.py::t1/t7 | met |
| G9-16 | 并且②：LangGraph 非必要依赖 | engine_v2 全树 import 闭包零 langgraph/langchain | — | TestP9Boundary::test_p9_import_closure | 待 W7 |

## 3. 门③ 六步执行（SOT §3.21）

| 步 | 内容 | 结果 |
|---|---|---|
| ① | HEAD = d9d2cc4ff77432b572b21b5e94db6c1ce41b444f ≥ aab029c | 通过（`git merge-base --is-ancestor` = true；W1–W7 共 14 提交） |
| ② | git diff --name-status aab029c..HEAD -- src tests scripts == 白名单 47 行 | 通过（Leader 提交后实测：47 行集合 + 计数双等；M 行纯追加 0 删除；§4 逐行对账） |
| ③ | pytest -q → 3142 passed / 0 failed/error/skipped | 通过（门级 R1 ×4 独立复跑 3142/0；恒等式 3054+82+6 四方自核一致） |
| ④ | TestP9Boundary 6 法 + P8/P7/P6 既有块全绿 | 通过（门级 R1 ×4：Boundary 38/38；方法 5/6 嵌入清单独立复算 9–11 值全等） |
| ⑤ | 行宽 ≤100 零命中 + 0x5C0x62 零命中 | 通过（47 文件行宽 0 命中；P9 产物面 0x5C0x62 零；锚冻结前段 12 处 = 基线同值非 P9 面） |
| ⑥ | §8.2 台账 71 名核对 + §8.4 偏差闭合 + §9 勘误链 | 通过（15 文件 71 名 AST 逐字全等；28 个 DEV-Wn-* 披露块全在位；ERR-P9-01..16 全链字面在位） |

## 4. 白名单 diff（gate ②，封闭集 47 行）

命令：`git diff --name-status aab029c..HEAD -- src tests scripts`
（HEAD = d9d2cc4ff77432b572b21b5e94db6c1ce41b444f）。期望行集（= SOT §3.19 L1080–1151 逐行（勘误后行号；勘误前行号 L1079–1150）；
**预核对**：W1–W6 面 37 行已在树、白名单外路径零、W7 恰补 10 行）：

| # | 模式 | 路径 |
|---|---|---|
| 1 | A | src/engine_v2/modules/base.py |
| 2 | A | src/engine_v2/modules/attributes.py |
| 3 | A | src/engine_v2/modules/inventory.py |
| 4 | A | src/engine_v2/modules/relationships.py |
| 5 | A | src/engine_v2/modules/character.py |
| 6 | A | src/engine_v2/modules/perception.py |
| 7 | A | src/engine_v2/modules/knowledge.py |
| 8 | A | src/engine_v2/modules/scenario.py |
| 9 | A | src/engine_v2/modules/actions.py |
| 10 | A | src/engine_v2/modules/dialogue.py |
| 11 | A | src/engine_v2/modules/space.py |
| 12 | A | src/engine_v2/modules/tactical.py |
| 13 | A | src/engine_v2/modules/dynamics.py |
| 14 | A | src/engine_v2/modules/narration.py |
| 15 | A | src/engine_v2/modules/v1_migration.py |
| 16 | A | tests/engine_v2/modules/__init__.py |
| 17 | A | tests/engine_v2/modules/conftest.py |
| 18 | A | tests/engine_v2/modules/test_attributes.py |
| 19 | A | tests/engine_v2/modules/test_inventory.py |
| 20 | A | tests/engine_v2/modules/test_relationships.py |
| 21 | A | tests/engine_v2/modules/test_character.py |
| 22 | A | tests/engine_v2/modules/test_perception_knowledge.py |
| 23 | A | tests/engine_v2/modules/test_scenario_trigger.py |
| 24 | A | tests/engine_v2/modules/test_action_executors.py |
| 25 | A | tests/engine_v2/modules/test_v1_migration.py |
| 26 | A | tests/engine_v2/modules/test_g9_galgame.py |
| 27 | A | tests/engine_v2/modules/test_g9_sandbox.py |
| 28 | A | tests/engine_v2/modules/test_g9_tactical.py |
| 29 | A | tests/engine_v2/modules/test_p9_differential.py |
| 30 | A | tests/engine_v2/modules/test_module_face.py |
| 31 | A | tests/fixtures/v2_project_galgame/game.yaml |
| 32 | A | tests/fixtures/v2_project_galgame/world/galgame_world.yaml |
| 33 | A | tests/fixtures/v2_project_galgame/characters/yuki.yaml |
| 34 | A | tests/fixtures/v2_project_galgame/characters/lena.yaml |
| 35 | A | tests/fixtures/v2_project_galgame/items/letter.yaml |
| 36 | A | tests/fixtures/v2_project_sandbox/game.yaml |
| 37 | A | tests/fixtures/v2_project_sandbox/world/sandbox_world.yaml |
| 38 | A | tests/fixtures/v2_project_sandbox/characters/wanderer.yaml |
| 39 | A | tests/fixtures/v2_project_sandbox/characters/merchant.yaml |
| 40 | A | tests/fixtures/v2_project_sandbox/rules/sandbox_rules.yaml |
| 41 | A | tests/fixtures/v2_project_tactical/game.yaml |
| 42 | A | tests/fixtures/v2_project_tactical/world/arena.yaml |
| 43 | A | tests/fixtures/v2_project_tactical/characters/soldier_a.yaml |
| 44 | A | tests/fixtures/v2_project_tactical/characters/soldier_b.yaml |
| 45 | A | tests/fixtures/v2_project_tactical/actions/tactical_actions.yaml |
| 46 | A | scripts/v2_migrate_v1.py |
| 47 | M | tests/engine_v2/core/test_import_boundary.py（EOF 纯追加） |

实际 diff 输出（`git diff --name-status aab029c..d9d2cc4ff77432b572b21b5e94db6c1ce41b444f -- src tests scripts | sort`）：

```text
A   scripts/v2_migrate_v1.py
A   src/engine_v2/modules/actions.py
A   src/engine_v2/modules/attributes.py
A   src/engine_v2/modules/base.py
A   src/engine_v2/modules/character.py
A   src/engine_v2/modules/dialogue.py
A   src/engine_v2/modules/dynamics.py
A   src/engine_v2/modules/inventory.py
A   src/engine_v2/modules/knowledge.py
A   src/engine_v2/modules/narration.py
A   src/engine_v2/modules/perception.py
A   src/engine_v2/modules/relationships.py
A   src/engine_v2/modules/scenario.py
A   src/engine_v2/modules/space.py
A   src/engine_v2/modules/tactical.py
A   src/engine_v2/modules/v1_migration.py
A   tests/engine_v2/modules/__init__.py
A   tests/engine_v2/modules/conftest.py
A   tests/engine_v2/modules/test_action_executors.py
A   tests/engine_v2/modules/test_attributes.py
A   tests/engine_v2/modules/test_character.py
A   tests/engine_v2/modules/test_g9_galgame.py
A   tests/engine_v2/modules/test_g9_sandbox.py
A   tests/engine_v2/modules/test_g9_tactical.py
A   tests/engine_v2/modules/test_inventory.py
A   tests/engine_v2/modules/test_module_face.py
A   tests/engine_v2/modules/test_p9_differential.py
A   tests/engine_v2/modules/test_perception_knowledge.py
A   tests/engine_v2/modules/test_relationships.py
A   tests/engine_v2/modules/test_scenario_trigger.py
A   tests/engine_v2/modules/test_v1_migration.py
A   tests/fixtures/v2_project_galgame/characters/lena.yaml
A   tests/fixtures/v2_project_galgame/characters/yuki.yaml
A   tests/fixtures/v2_project_galgame/game.yaml
A   tests/fixtures/v2_project_galgame/items/letter.yaml
A   tests/fixtures/v2_project_galgame/world/galgame_world.yaml
A   tests/fixtures/v2_project_sandbox/characters/merchant.yaml
A   tests/fixtures/v2_project_sandbox/characters/wanderer.yaml
A   tests/fixtures/v2_project_sandbox/game.yaml
A   tests/fixtures/v2_project_sandbox/rules/sandbox_rules.yaml
A   tests/fixtures/v2_project_sandbox/world/sandbox_world.yaml
A   tests/fixtures/v2_project_tactical/actions/tactical_actions.yaml
A   tests/fixtures/v2_project_tactical/characters/soldier_a.yaml
A   tests/fixtures/v2_project_tactical/characters/soldier_b.yaml
A   tests/fixtures/v2_project_tactical/game.yaml
A   tests/fixtures/v2_project_tactical/world/arena.yaml
M   tests/engine_v2/core/test_import_boundary.py
```

对账结论：行集 + 计数（47）双等 + M 行纯追加（`<` 行 0）= **通过**（集合 + 计数双等实测；M 行 = 锚文件，纯追加 0 删除行；47 行 = SOT §3.19 白名单逐行一致）

## 5. 审查记录（逐轮；JSON 全文在 .review-drafts/，gate 闭合后按 P8
先例处置）

- **W0 设计 SOT（4 盲设计评审 × 4 轮收敛）**：R1 4/4 SUPPLEMENT
  （45 findings = 19S + 21D + 5I）→ 18 项裁决修正（ERR-P9-04，
  `759edc5`）；R2 裁决修正 13 项（含 1 项误计裁决撤回 + M-id 绑定
  表 + AD-P9-2 钉码，ERR-P9-05，`5cf3acd`）；R3 裁决（ERR-P9-06，
  `e884ee7`）；R4 收敛 4/4 = 3 PASS + 1 SPECULATIVE_PASS、0
  SUPPLEMENT / 0 BLOCK → 设计冻结（`e2dd4b1`）。派发前实现性勘误
  ERR-P9-07（`3217485`）/ ERR-P9-08（`afabdb5`）= docs 闭合，不消耗
  波次补充预算（D8）。SOT 终态 = 1859 行 @ `afabdb5`（+ 本 gate
  收口勘误链续编，§9）。
- **W1（T02+T05，`8a98bd9`，3070/0）**：R1 4/4 PASS（11 findings =
  7 DOC 预提交修正 + 4 INFO 简报层不处置；2 项无效裁定驳回）。
  实质修复轮 0/3。
- **W2（T03+T04，`11ff7c9`，3080/0）**：R1 4/4 PASS（12 findings =
  1 DOC + 11 INFO；3 项 DOC 级预提交修正）。0/3。
- **W3（T06+T10，`9bc3415`，3087/0）**：R1 4×SUPPLEMENT（R8 钉面
  缺口 2 类 + 1 DOC）→ 6 项内容补充 / DOC 预提交修正 → R2 4/4 PASS
  （3 INFO 不占预算）。1/3。
- **W4（T07+T08，`6fdfdcf`，3097/0）**：R1 4/4 PASS（3 DOC + 5 INFO
  → 7 项 DOC/内容补充预提交修正，零预算）。0/3。
- **W5（T09，`c4a8a07`，3104/0）**：R1 4×SUPPLEMENT（10 补充 + 2 FIX
  偏差登记）→ R2 1 BLOCK + 2 SUPPLEMENT + 1 PASS（全文档级：D1 锚
  字节 ×2 处 + 披露块冲突面 ×1 + 交叉引用 ×1）→ Leader 预提交补充
  M1–M5（字节真值复验）。1/3（R2 = 第 2 轮）。
- **W6（T11+T13）**：R1 4 盲 = 2 补充内容 + 2 投机通过（R8 分歧
  2:2 → Leader 字节裁定：S-1 波内身份点钉 + S-2 register 幂等/核验
  序钉成立；4 DOC + 7 INFO 备案；DEV-W6-8 Leader 追认）；Leader
  预提交补充 16 处（点钉 2 组 + 幂等钉 + 行号 ×7 + 注释 ×1 +
  备选（否）×5）+ 全量复验 3115/0 + 扫描零 + head-74 sha 一致 →
  R2 4×通过（1 DOC + 2 INFO → 预提交补充 4 处：L810 行锚 /
  相位序注释 / DEV-W6-4/5/6 披露文本；复验 3115/0）→ 提交
  `2a417d0`。2/3 预算（R2 = 第 2 轮，零 R3）。
- **W7（T12+T14）**：R1 4×补充内容（S-1 A6 逐 tick 绝对刻直钉〔宿主
  tick(n) = 绝对刻语义实测发现〕+ S-2 parse 负例 4 例 + S-3 per-module
  requires (a2) 级 + 6 注释锚修正）→ Leader 预提交补充 + 全量复验
  3142/0 → R2 3×通过 + 1×补充内容（t2 IDENTITY 序钉）→ Leader
  序钉补充（红探针验证 RED）→ R3 3×通过 + 1×补充内容（frozen 面钉
  + 2 DOC）→ Leader 补充（FrozenInstanceError 行为钉 + t7 docstring
  A16 归因 + _VERSION_RE 注释语义等价修正；复验 3142/0）→
  R4 **4×通过**（0 SUPPLEMENT / 0 BLOCK；1 交付面 DOC = game.yaml
  注释 SOT L1005 钉值更正（勘误后行号；勘误前 L1004）+ manifest sha 同步，Leader 预提交修正；
  复验 3142/0 + head-2071 sha 26fc0528 不变）→ 提交
  `d9d2cc4ff77432b572b21b5e94db6c1ce41b444f`（10 文件 +2380）。
- **门③ 门级 R1（4 盲）**：4 名独立盲审各自完整核验 16 条款
  + 独立复跑 ①–⑥ 全步对账（G8 先例同构）→ **4×通过**
  （0 SUPPLEMENT / 0 BLOCK；findings 全 = 任务书层 DOC/INFO
  〔Plan 节号 §17→§18 转述 / 「10 平铺」误计 13 / G9-15 第 4 输入
  括注 / 0x5C0x62 范围措辞 / core 32 子模块口径〕+ 已入勘误链面
  〔ERR-P9-12/16〕，零交付物/SOT 实质缺陷）。门 = **PASS**。

## 6. 偏差登记

### 6.1 决策登记（D-P9-01..16，SOT §4 五段全文；本表 = 选择摘要）

| ID | 决策面 | 选择（摘要） |
|---|---|---|
| D-P9-01 | 官方模块包落位 | 单包平铺 `src/engine_v2/modules/<name>.py`（13 + base） |
| D-P9-02 | 模块发现机制 | 显式导入注册（非 .py 发现）；kernel 侧 import + 注册函数 |
| D-P9-03 | 模块 id 语法与版本 | `llmsim-standard-<name>` = Spec §40 代码块逐字；version "1" |
| D-P9-04 | T01 三态判据 | 三态 = 保留思想 / 移除 / 挂接（Spec §43.1/§43.2 逐条 20/20） |
| D-P9-05 | NPC 决策面 | NpcBehaviorPolicy + 事件驱动 wakeup（43.2-2 移除面承接） |
| D-P9-06 | 感知-知识切分 | perception = 空间邻域 → ObservationRecord；knowledge = 边界面 |
| D-P9-07 | 迁移器放置 | modules/v1_migration.py + scripts 薄壳（选 c） |
| D-P9-08 | T09 闭集映射 | M-1..M-9 闭集 + 诊断面（零静默丢弃；S3 预检落位） |
| D-P9-09 | 迁移诊断码 | 独立 9 码闭集 `MIGRATION_DIAGNOSTIC_CODES`（不复用 P5 18 码） |
| D-P9-10 | 三样例落位 | 3 新 fixture 项目（各 5 文件）+ 3 平铺测试；宿主 = conftest |
| D-P9-11 | G9-10 判据拆法 | 2 判据 A10（LLM dynamics）/ A11（rules dynamics）分立 |
| D-P9-12 | dynamics 模块 | P7 复用桥（2 导出；零新动力学逻辑） |
| D-P9-13 | narration 模块 | text 侧纯派生非权威 ViewState（image 归 P10） |
| D-P9-14 | T14 差分方法学 | v1 纯函数直引 + 镜像同构（非运行时回放）；六面 D-α..D-ζ |
| D-P9-15 | 波次划分 | W1–W7 七波（§3.18 表为准） |
| D-P9-16 | 计数恒等式 | 3142 = 3054 基线 + 82 平铺 + 6 边界（§8.3） |

### 6.2 各波自裁偏差面（W5 14 项 + W6 8 项 + W7 6 项；
四要素全文 = 交付物内披露块 + .p9 工作文档；本表 = 冲突面/选择摘要）

**W5（T09 v1 迁移）**：

| ID | 冲突面（摘要） | 选择（单选摘要） |
|---|---|---|
| DEV-W5-1 | SOT 字面 passthrough 条件经 P5 parse_dsl 失败（缺 else 分支 → validate 必 ERROR，破坏 A16） | 最小修正 `if(1 >= 0, allowed; blocked)`（恒真 → 恒 ALLOWED，语义保持；probe 双形态留证） |
| DEV-W5-2 | v1 自由形态引用面含不解析引用（实测三项目命中） | 引用池「保留」分支 = v1 源 ∩ (角色 id ∪ {player_id})（t3 逐角色钉） |
| DEV-W5-3 | M-3 字面「(== id) → 丢弃 + WARNING」与四输入表/t3 钉冲突（字面读 = whisperheads M-16 ×7） | 独立重算 12/12 零触发口径（character_id==id 三项目全等 → 零 WARNING 实证） |
| DEV-W5-4 | v1 narrative_style = dict vs v2 ScenarioSpec = str | dict → 模板化 str 折叠（style_description 主面 + example 并入） |
| DEV-W5-5 | SOT 未钉模板文本（name/description） | 模板化实现面 + docstring 逐字钉（A16/A22 不钉模板内容） |
| DEV-W5-6 | SOT 对 game_time / ticks_per_game_minute / starting_scene_description / narrative_style 缺省沉默 | 显式缺省值钉（docstring）；缺失 → INFO 诊断 |
| DEV-W5-7 | SOT 未定义纯 simulation 面（零部署节）status/诊断/输出 | status = 完整输出 + 零部署节诊断 INFO（t 钉） |
| DEV-W5-8 | argparse 默认 usage 错退出码 = 2 vs SOT「1 = 用法错误」 | 薄壳捕获 → 退出码 1（t7 钉） |
| DEV-W5-9 | t2 行钉值 = 首键摘要 vs 完整折叠串（各对象 state dict 均 2 键实测） | 钉值 = 完整折叠串（公式逐键拼接，M-4 L895） |
| DEV-W5-10 | v1 逐属性条目含 P5 AttributeSpec 无承载键 hidden（whisperheads 6 / murder 3） | 忠实逐键 → description 并入 + WARNING 诊断 |
| DEV-W5-11 | 属性数值字段「数字+描述」合并单标量（YAML 整体解析为字符串） | float 提取 + 残余文本并入 description 逐字（t1 钉） |
| DEV-W5-12 | 任务书 items 元组序 vs Python sorted 序（oak_door 先） | sorted 实现面序（任务书层错误，DOC 级登记） |
| DEV-W5-13 | M-4 字面「空 dict → state: null」未豁免诊断 vs 实现无条件 INFO | S7 裁决：空 dict → `state: null` + 零诊断豁免（Leader 裁决面） |
| FIX-W5-S5 | 任务书 S5 要求 subprocess 消费薄壳 vs 边界测试 B3 禁测试树 subprocess | 薄壳直 import 消费（任务书层修正；披露块） |
| FIX-W5-S6 | 任务书 S6 钉形 `__all__` == 元组 vs SOT 字面块 = 列表字面量 | 列表字面量（SOT 字面优先；t 断言 `tuple(__all__)` 双兼容） |

**W6（T11+T13 dialogue/narration + space/tactical）**：

| ID | 冲突面（摘要） | 选择（单选摘要） |
|---|---|---|
| DEV-W6-1 | dialogue 增量词表/数值 SOT 未钉 | 闭集标记（正 7 / 负 5 词）+ `round(0.05×正 − 0.10×负, 6)`；docstring 逐字钉；A3 同源断言 |
| DEV-W6-2 | odd-r 邻表/立方公式 SOT 未钉 | 标准 odd-r 惯例（邻居表 + x = c−(r∓(r&1))//2 + cube max）；self-proof 16/32 + 距离 2 + BFS==cube |
| DEV-W6-3 | 宿主相位序/绑定面/可重跑面 SOT 未钉 | P9Host 相位 1–5 常量钉；K2 = CascadeExecutor（DENY + 2 规则）；双样例可重跑 hash 复验 |
| DEV-W6-4 | scenario id SOT 未钉 | `scenario_galgame` / `scenario_tactical`（M-5 `scenario_<project>` 先例） |
| DEV-W6-5 | player_id SOT 未钉 | `player_1`（两样例同值；zero_python 先例） |
| DEV-W6-6 | gameplay_modes 承载键未钉（game.yaml 8 键闭集） | game.yaml 顶层 `gameplay_modes`（P5 既有承载面 project_ir.py:356；零 ERROR 实证） |
| DEV-W6-7 | 世界哈希定义 SOT 未钉（A5/A15） | P8 冻结快照面 to_persistence_snapshot:104 → dump:133 → sha256（docstring 钉） |
| DEV-W6-8 | SOT §3.11 L789 签名 `register_standard_space(registry: SpaceRegistry,…)` 不可实现（SpaceRegistry 不可变，core/space.py:185 构造器唯一、零公共 mutator） | entries 宿主映射参数 + 校验 + 幂等覆盖，宿主写毕再构造 SpaceRegistry（S-INV-4/5 核验）；字面签名/私有突变均否。**Leader R1 裁决追认**（byte-truth 强制；3 评审独立复验）→ SOT 勘误 **ERR-P9-10**（G9 收口 docs 提交；预备文本 `.p9/sot-errata-g9-pending.md`） |

**W7（T12+T14 dynamics 桥 + sandbox + 差分 + 边界）**：

| 偏差 | 冲突面 | 裁决/落位 |
|---|---|---|
| DEV-W7-1 | scenario id SOT 未钉（§3.16.2 仅钉 tpgm 0.5） | `scenario_sandbox`（M-5 `scenario_<project>` 先例；预裁决） |
| DEV-W7-2 | 长动作 ActionSpec 承载面（sandbox fixture 白名单行 36–40 无 actions 目录） | 测试侧注册（DurationPolicy kind="fixed" duration_ticks=3，action_registry.py:102 冻结面；预裁决） |
| DEV-W7-3 | t5/t6 dynamics 绑定形态 | t5 = LLMWorldDynamics 直绑 + build_standard_dynamics 装配单元同函数；t6 = RuleDynamics 单绑（保非命中 tick 零效果钉；预裁决） |
| DEV-W7-4 | **headline**：SOT §3.17 D-ε 行「唯一允许差异 = items 节」被实测证伪——完整差异集 = manifest 三模板字段 + scenario.id + characters（0/1）+ rules（0/2）+ actions（0/1）+ items（4/0）；player/world IR 相等 | Leader 独立探针复现逐值一致；归因 = W5 迁移器模板面（合法）+ P5 镜像手工附加（非移植错误）；t5 钉死完整集（更严非放宽）；**SOT 勘误 ERR-P9-11**（G9 收口 docs 提交） |
| DEV-W7-5 | SOT §3.0 导入闭集块遗漏既有依赖 PyYAML（v1_migration.py:160 必需 import yaml） | pyproject.toml:11 预声明 + 冻结 v1/P1–P8 面已 import（零新依赖）；方法 4 将 yaml 列既有第三方根；**SOT 勘误 ERR-P9-12** |
| DEV-W7-6 | §2.10「T14 import v1 纯函数」与冻结 P1 边界 test_t06（锚 L432–466，静态禁 tests/engine_v2/ v1 import）字面冲突 | importlib.import_module 动态直引（保留直引非回放语义；SOT L877/L1288 绕路先例同风格〔L1288 = 勘误后行号，勘误前 L1287〕；零断言放宽）；**SOT 勘误 ERR-P9-13** |

## 7. 风险登记册（SOT §0.6 R1–R7 闭合状态）

| # | 风险（SOT 原文缩写） | 闭合状态 | 证据 |
|---|---|---|---|
| R1 | T09 自由文本规则折叠语义漂移 | 闭合 | D-P9-08 passthrough 条件 `if(1 >= 0, allowed)` 永不改可行性（whisperheads physics 5 / attribute 3 + murder 同形）；逐条 INFO 诊断（MIGRATION_FREEFORM_RULE_FOLDED）；T14 差分面 D-α..D-ζ 实测零差（D-ε = 完整差异集披露，ERR-P9-11） |
| R2 | 大文件迁移覆盖不全 | 闭合 | 三项目全文件迁移非节选（897/802/154 行）；A17 同构面（P5 zero_python 镜像对照）；A22 诊断闭集断言（test_v1_migration t7） |
| R3 | hex 邻接与 GridSpace 边界混淆 | 闭合 | `modules/space.py` hex → GraphSpace 纯函数映射（A12：16/32 逐边常量 + 距离 2 双钉 + GridSpace 曼哈顿对照 + AD-P9-4）；两空间域 SpatialDomain 分离（conftest 参数化构造）；W6 R1 几何独立复核（§5 记录） |
| R4 | 边界锚文件纯追加体积增长 | 闭合 | TestP9Boundary 6 方法 W7 EOF 纯追加（实测 +521 行，2071→2592；P8 R8 先例 +442 同量级）；L1–L2071 逐字节不变（head-2071 sha256 前后恒等 26fc0528… 自证）；唯一修改模式纪律门③ ⑤ 核 |
| R5 | v1 纯函数直引 import 风险 | 闭合 | W0 预验实测：`src/game/{attributes,condition_eval,deterministic_rules,tick_eval,state_apply}.py` 零第三方 import（re/random/copy/dataclass/typing）；`src/models/*.py` 仅 pydantic；T14 差分 6 平铺零 import 失败（W7 绿） |
| R6 | G8 三条 s2 评估面滞留 | 闭合（移交保留） | §0.4 登记非范围；P9 零消费零评估；G8 报告 L201–202 移交面（branch-audit payload / replay ABORTED / snapshot-derived inspect + D-P7-13）原样承继至本报告 §9 移交面 |
| R7 | 样例 fixture 膨胀 | 闭合 | 3 样例项目 × 5 文件、单文件 ≤150 行、id 小写蛇形、yaml 顶层键字母序（§6.4 落盘后字节冻结，跨波 sha 复测）；白名单逐行编号门② 对账 |

## 8. HARD STOP 逐条核验（Plan §24，L1212–1366）

- **S1（需要改变 Architecture Kernel invariant）— 未触发**。`git diff
  aab029c..HEAD -- src/engine_v2/core` 零 diff 行（core 冻结面零改动；
  P9 15 模块全落 modules/ 冻结缝上）；K2 管道实证：全部模块零直接
  状态写入（policy 只产 ProposedEffect，经 core 冻结 authority/
  transaction 面落位）；K5：样例零 LLM（FakeInferenceBackend 脚本
  化，键 (logical_role, base_revision, seq)）；K8：零 provider 字面
  + 零 langgraph/langchain import（G9-16）。
- **S2（Public Contract 两种同样合理但不兼容设计）— 未触发**。P9
  零新 public contract 设计：15 模块复用面 = P1–P8 冻结契约
  （ProposedEffect / Authority / Transaction / Event provenance /
  Scheduler / ProjectIR / Space domain identity 皆冻结面）；
  D-P9-01..16 全部单选设计并登记（SOT §4 五段 + 备选否决）；全程
  无 contract 级分歧需人工裁决（各波 4 盲审收敛，§5）。
- **S3（为通过测试需要 destructive migration）— 未触发**。v1 三项目
  （whisperheads 897 行 / murder 802 行 / test_empty 154 行）字节
  冻结零触碰；迁移输出 = 全新 v2 树（纯新增）；M-1..M-16 映射全
  诊断面（WARNING/INFO），零静默 drop 字段、零 v1 语义改变；门②
  diff 零删除行（纯新增 + 锚文件 EOF 纯追加）。
- **S4（引入新的重大依赖 / License 风险）— 未触发**。`pyproject.toml`
  / `uv.lock` 零 diff；P9 = stdlib + pydantic（uv.lock 既有）；
  G9-16 边界方法：engine_v2 全树 import 零 langgraph/langchain。
- **S5（Backend 无法满足 replay/checkpoint Contract）— 不适用
  （N/A）**。P9 零新数值 backend；样例推理 = FakeInferenceBackend
  （P6 冻结面，脚本化）；dynamics = P7 复用桥（D-P9-12 零新动力学
  逻辑；P7 8 模块 35 导出冻结面）。
- **S6（同一任务连续失败）— 未触发**。W1–W7 全部波次于 R1/R2
  预算内收敛（§5 逐轮记录）；无波次达 R0/R1/R2 穷尽 + 无稳定
  root cause 态；每波 4 名独立盲审诊断收敛一致。
- **S7（测试通过但语义明显违背设计）— 未触发（门③ 终核记录）**。
  五反例面核验：mode change = `apply_mode_change`（:475）非
  WorldState 复制（W6 t4 断言）；LLM 写入不藏 reducer（K2 管道 +
  边界方法）；authority = core 冻结真面（零 diff）；multi-space =
  SpaceRegistry 域映射（非单 active space）；replay = 真事件流
  （P7/P8 冻结面，非最终 snapshot 重读）。
- **S8（baseline 与架构目标冲突、兼容意图不清）— 未触发（v1 已知
  偏差 = 诊断化，非自动兼容）**。v1 偏差面（character_id==id 冗余 /
  world_rules.disable 等）按 SOT M 表逐条诊断（M-16 丢弃 + WARNING /
  M-15 逐条 WARNING / M-13 逐条 INFO），零静默自动兼容；独立重算
  12/12 零 M-16 触发（W5 R2 复核）。
- **S9（并发 / 异步 state corruption）— 未触发**。P9 测试面全同步
  tick（零线程 / 零 async / 零并发原语）；零 revision 倒退 /
  duplicate commit / lost event / stale effect 观察（P8 revision
  冻结面 + A15 单一 WorldState tick 连续断言）。
- **S10（性能目标需要架构级 tradeoff）— 不适用（N/A）**。G9 十六
  条款零性能判据；样例小规模（≤5 角色 / ≤9 hex 单元 / 百 tick 级），
  零 scheduler 瓶颈 / trace 体积 / checkpoint 成本证据；P1 runtime
  如现再评估（移交面登记，§9）。
- **S11（多模态主观验收无法确定）— 人工延期（预登记面，不自裁）**。
  G9 十六条款全机械判据，本 gate 无多模态面；H6 = Plan §23 三类
  参考游戏实玩验收（需真实 LLM 部署 + 人工主观评审）延期人工面
  （§1 字段登记；本 gate 不替代）；图像/视觉连续面 = P10（S11
  于 G10-5/6/7 点触发，预登记延期）。
- **S12（Agent 重构超出工作包边界）— 未触发**。逐波白名单封闭集
  （W1–W7 各波 diff == 该波白名单；门② 合计 47 行对账，§4）；
  dev 报告零越包声称；Leader 直接补充仅文档级且披露 + 复验
  （W3 / W5 M1–M5 先例，D8 纪律）。

## 9. 结论

- 未使用 CONDITIONAL PASS（Plan §21 默认禁止）。
- **Decision: PASS**（16 条款全 met；S1–S12 未触发；3142/0）
- 移交面：<如有滞留评估面，逐项登记（P8 s2 先例）>
- 勘误链（D8）：ERR-P9-01..08（SOT 种子 + W0 R1–R3 裁决 + 派发前
  实现性勘误 ×2，`afabdb5` 闭合）+ **ERR-P9-09**（W5 R2：M-3/M-16
  行 vs A16 四输入表 character_id 冲突——== id 静默丢弃）+
  **ERR-P9-10**（W6 DEV-W6-8：§3.11 表行 4 签名 → entries 宿主映射
  形，D5 冻结面强制；W6 提交信息「候选 ERR-P9-09」= 早期候选号，
  最终号按队列序重编号）= G9 收口 docs 提交（与代码提交分离）
- 人工验收面（Plan §23）：H6 三类参考游戏实玩 = 需真实 LLM 部署 +
  人工主观评审（本 gate 不替代；脚本化切片已证明机制面）
