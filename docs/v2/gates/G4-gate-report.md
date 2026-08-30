# G4 Gate Report — Phase 4 Actor / Context / Space / GameplayMode（终版）

按 `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` §13、§21、§25 编制。
G4-R1 盲审（`42a38ee` 审查点）4/4 通过/投机通过、0 补充、0 阻塞、0 执行失败后，
Leader 另执行一个文档级留痕清零提交（`9baa5b7`，ERR-P4-3 纯追加勘误，零断言零行为
变更，按 2026-08-20 协议文档级修复不消耗补充预算、不触发复审）；本报告为 G4 最终
交付点记录。

---

## 0. 基础信息

- **Gate**: G4（Phase 4 — Actor / Context / Space / GameplayMode 门禁）
- **Commit SHA**: `9baa5b7`（HEAD，Phase 4 最终交付点）
- **分支**: `architecture-v2`
- **审查基准**: `ab0c7d2`（G3 门禁报告，pre-P4 冻结基线）.. `42a38ee`（Wave F，G4-R1 审查点）；
  P4 设计 `c162d19`（frozen）+ 勘误 `6a6f19e`（ERR-P4-1）/ `76c82d0`（ERR-P4-2）；
  P1 冻结基线 `603535e`，P2 冻结点 `f49ecd5`（G2 PASS），P3 冻结点 `8814225`（G3 PASS）
- **测试基线**: 全量 **2399 passed**（ERR-P4-3 后复验，12.26s；新增 171 测试 =
  2399 − 2228 G3 基线 = 9 个 P4 测试文件 169 + `test_import_boundary.py`
  `TestP4Boundary` 2 函数）；`ruff check src/engine_v2 tests/engine_v2` →
  `All checks passed!`
- **审查执行**: 全部 `qiyuan-self / qwen3.8-27b`（2026-08-20 人工路由覆盖，见
  `docs/plans/model-routing-providers.md`）；设计阶段 5 轮盲审（R1–R5，全闭合，
  0 阻塞/0 补充残留）+ 门禁阶段 **1 轮 × 4 名独立盲审（G4-R1，全新一轮全新盲）**，
  四裁决协议（通过/投机通过/补充内容/阻塞）

---

## 1. §21 字段

```text
Gate: G4
Commit SHA: 9baa5b7
Tasks completed: P4-DESIGN（R5 收尾轮关闭，ERR-P4-1/2 勘误），
                 P4-T01 ~ P4-T10（全部；T05/T06/T07 = space.py 上/下半同文件串行，
                 T08/T09 = gameplay_mode.py 上/下半同文件串行，T10 = D/E/F 三波测试），
                 + G4 文档级闭合（ERR-P4-3：D7/D8/D9 偏离登记 + 错误族族分类解读
                 + M-INV-6 编号 + make_backend 参数缺失错误面 + conftest 逐字口径）
Tasks waived: 无
Tests: 2399 passed（真实输出，.venv python，-p no:cacheprovider）
Known failures: 0
Architecture deviations: 见 §5 偏差登记（全部已披露/已登记，无未声明偏差）
Open risks: 见 §6 风险登记册（全部为已声明级别残留/移交，低）
Human review required: 否（M1 自动化授权范围内；G4 实质补充轮 0/3 在预算内，
                       按 2026-08-20 协议无需人工批准）
Decision: PASS
```

---

## 2. 门禁判据验证

### A. 设计 §1.2 G4 六条（与 Plan §13 G4 六条一一对应，映射明细见设计 §7）

| # | 判据（Plan:577-582 逐字） | 证据 |
|---|---|---|
| G4-1 | Alice 不知道她没有 Observation/Knowledge 的 Bob 偷窃事件 | `test_g4_1_epistemic_boundary`：**#1–#3**（S11 后 alice context 构建 + 世界侧对照——`observations == ()`、`knowledge is None`、可见集 = {self}∪观察∪知识引用∪local 邻域；theft 已于 R1 提交入世界，与 alice 上下文完全隔离）+ **A1 强化**（`test_a1_epistemic_attack` 独立探针）；认识论边界 = 构建期物化（CX-INV-4/D-P4-05，context 不持 `GuardedWorldState` 引用）；G4-R1 R4 独立探针（不复用测试模块，S0 世界 gold_cup 变体）复现成立 |
| G4-2 | 自定义 Policy 不能因为更换 Prompt 而获得 global read | `test_g4_2_prompt_cannot_grant`：**#4–#6**（双 provider baseline/override prompt → 上下文全等；阳性对照：显式 global 授权 → `global_entity_views` 非 None 恰 4 实体）+ **A2 强化**（`test_a2_prompt_privilege_escalation` 含静态签名扫描）；唯一授权面 = `CapabilityTable`（K4；prompt 不透明、构建期从不查询，CX-INV-5）；G4-R1 R4 独立探针复现 ①②③④ 成立 |
| G4-3 | 一个 Entity 可拥有 overworld + tactical 映射 | `test_g4_3_multi_space`：**#7–#9**（`spaces` 组件解码保序；`entity_domain_positions` 双域 {overworld: grid 坐标, tactical: 图节点}；tactical 跨节点 BFS 距离精确）+ **A3 强化**；S-INV-1~5 构造/查找/编解码全拒绝面 + codec roundtrip（A6 JSON-clean） |
| G4-4 | Dialogue + Tactical 可同时 active | `test_g4_4_mode_bookkeeping`：**#10–#12**（S12/S13 逐字请求（`ORIGIN_SCRIPT_PROVENANCE`，origin=SCENARIO）；`active_modes` 双元素排序 list + `mode_context` per-mode 上下文；applied/ignored 精确；重复 activate noop（C3）；未知 mode 原子拒绝（C1，runtime 全字段不变））+ **A5 强化** + **C1–C3** |
| G4-5 | TimePolicy 冲突有明确 winner | `test_g4_5_merge_deterministic`：**#13–#16**（per-property 单胜者 = argmax priority，平手 casefold 较小 id（D-P4-14）；`time_policy` 整对象替换；`activated_systems` 并集；`winner_by_field` 键集与值——多过滤集单胜者记录 = D9 裁定面）+ **A4 强化**（排列不变性对抗） |
| G4-6 | mode change 不复制 WorldState | `test_g4_6_no_world_copy`：**#17–#19**（`inspect.signature(apply_mode_change).parameters` 键集 == {"request","runtime","registry"}（M-INV-3/D-P4-15）；world 对象同一性 + revision 不变；monkeypatch 复制点全 raise 仍通过）+ **A5 强化**（簿记面封闭，M-INV-5）+ **A6 强化**（JSON-clean）；内部唯一重建路径 = `rebuild_runtime`（clock.py:151，RuntimeState-only） |

19 条编号断言（3+3+3+3+4+3）全部落位于 `test_p4_gate_scenario.py`（7 测试函数，
896 行），S0 装配逐字（§5.1），S12/S13 逐字（§5.2 L1477）；G4-R1 R2 盲审 34+ 条
行级设计锚点比对全部命中（要求 ≥10）。

### B. 扩展门禁判据（M1–M3 机械面 + 对抗 + 集成 + P3 移交）

- **M1（无世界写/无 LLM 面）**：①②③ 落 `test_p4_adversarial.py::test_m1_no_world_write_no_llm_surface`
  （6 模块 AST 扫描：零 `providers.*`/`asyncio`/`random`/`datetime`/`json` 导入、
  零 `transaction`/`transaction_executor` 导入与 `apply_transaction`/
  `apply_committed_effects` 调用、`gameplay_mode` scheduler 导入 ⊆ {TimePolicy}）；
  ④ 落 `test_import_boundary.py::TestP4Boundary::test_p4_core_modules_no_nondeterminism_imports`
  （12 名封闭集 openai/anthropic/langchain/litellm/ollama/gemini/gpt/claude/llm/
  provider/api_key/base_url，casefold + `\b` 词边界全源扫描 0 命中，§6.4 钉死位置）。
- **M2（context 不持久化）**：`test_m2_context_not_persisted`——WorldState/
  RuntimeState `model_fields` 无 `ActorDecisionContext` 类型字段；text 仅出现于
  context_provider.py / behavior_policy.py。
- **M3（revalidation 域封闭）**：全部 `RevalidationDecision` 结果断言 ∈
  {ACCEPT, REJECT}（gate + integration 逐处）。
- **A1–A8 对抗 8 行**（§6.3）→ `test_p4_adversarial.py` 10 函数（A1–A8 + M1①②③/M2）：
  A7① 重提案全管道 ACCEPT + `checkpoint_skipped_interrupted` 诊断；A7② stale base
  REJECT；A7③ hook 异常整批原子（errors[0] 前缀 `SchedulerWakeupError` ∧ 世界/队列
  零 delta，失败 wakeup 记录保留）；A8 capability ⊥ authority（capability 拒绝不改
  authority 判定）。
- **R1–R8 + C1–C3 集成**（§5.4）→ `test_p4_integration.py` 11 函数：分支 A
  S0→S1→bounded ff(max_tick=12)→t42 终态（R1 中断重锚 / R4 观察面 / R7 progress）；
  分支 B PassPolicy→bounded→`resume_action` 三元素（INTERRUPTED→ACTIVE，RESUMED
  at_tick 12）→progress 0.4 精确→t30 COMPLETED 单实例（R8）；C1 未知 mode 原子 /
  C2 空 operations 构造拒绝 / C3 重复 activate noop。
- **G3 移交 2（fingerprint 披露，D5）**：`test_g3_handoff2_fingerprint_disclosure`——
  `wakeup_hooks` 已接线装配（`make_p4_scheduler` per-actor `PolicyWakeupHook`，
  scheduler.py:615）与 P3 基线装配指纹相等（`scheduler_fingerprint` 输入面 =
  registry + time_policy + boundaries，scheduler.py:429-452，结构排除）；输入面
  扩展本身 = P5 义务（G3:163）。

### C. P1/P2/P3 冻结与导出台账（机械核验）

- **白名单**：`git diff --name-status ab0c7d2..42a38ee` = **恰 20 文件**：
  设计文档 1 + 新模块 6（capability/knowledge/space/context_provider/
  behavior_policy/gameplay_mode）+ 测试文件 10（conftest + test_capability/
  knowledge/space/context_provider/behavior_policy/gameplay_mode/
  p4_gate_scenario/p4_adversarial/p4_integration）+ 锚点文件 3（`core/__init__.py`、
  `test_closeout.py`、`test_import_boundary.py`）。G4-R1 四名盲审各自独立执行 V3
  核验，文件集一致（`whitelist_ok=true`）。
- **冻结零变更**：P1/P2/P3 既有模块 diff 为空（G4-R1 R3 抽验 `transaction.py` /
  `reducer.py` 等空 diff；conftest 自 Wave E `fc27517` 后零变更，R4 `git log` 核验）。
- **导出台账**：`core/__init__.py` `__all__` 249 → **308**（+59 = capability 6 +
  knowledge 11 + space 18 + context_provider 6 + behavior_policy 4 +
  gameplay_mode 14）；59 新名 17 个间隙邻接对与设计 §3.11 表（L753-771）逐行一致，
  间隙内顺序按 L773 D-I1 注（表行序，不 casefold 重排）；原 249 名相对序零变化；
  全部 308 名包导入可解析。`test_closeout.py` 32 模块元组 + `len(__all__) == 308` +
  算术块（249 + 6 模块 59 = 308）+ shadowed == {snapshot}；`test_import_boundary.py`
  `CORE_SUBMODULES` 32 元组 + P4 常量块 4 项（`P4_SUBMODULES`/`P4_NONDETERMINISM_ROOTS`/
  `P4_TEST_FILES`/`P4_LLM_PROVIDER_BLACKLIST`）+ `TestP4Boundary` 2 函数。已知红
  （Wave A/B 预披露的 import_boundary stems 锚点）于 Wave F 锚点同步后闭合。

---

## 3. 任务完成情况（Tasks completed）

| 任务 | 提交 | 交付 |
|---|---|---|
| P4-DESIGN | `c162d19` | `docs/v2/contracts/P4-actor-context-space-mode-design.md`（1897 行：6 模块 59 导出、D-P4-01~17、§3.11 锚点账本、§5 gate 场景 S0–S13 + 19 编号断言、§6 测试规格（M1–M3/A1–A8/import 边界）、§7 映射表、§8 自检 + 偏离 D1–D6）；设计盲审 R1–R5 五轮（R1–R4 findings：A 0 / B 2 DOC+1 INFO / C 1 DOC+437 引用 W=0 / D 1 INFO；R5 残留 3 DOC 免费补丁闭合——A5b 标签→M1③、A7 ①=A7a/②=A7b 声明、5 处章节区间端点收紧）；已知红预披露（§3.11/§8.5-D4：Wave F 锚点文件集，升 26→32 后闭合） |
| P4-T03+T04+T05（Wave A） | `6fa185c` | `capability.py`（§3.5 全量 6 导出：grant 表/check/scope/`DEFAULT_NPC_CAPABILITIES`/`CapabilityScopeError`）+ `knowledge.py`（§3.6 全量 11 导出：Belief/KnowledgeState/ObservationRecord/4 组件常量/编解码 JSON-clean）+ `space.py` 上半（§3.7 10 导出：SpatialDomain/SpaceRegistry/`SPATIAL_BACKEND_KINDS`/`make_backend` 6 kind 分派）；已知红 = 预披露锚点（`test_import_boundary` stems） |
| P4-T02+T06+T07+T08（Wave B） | `a969096` | `context_provider.py`（§3.8 全量 6 导出：`ContextBuildInput` 7 字段/`ActorDecisionContext` 13 字段/`DefaultContextProvider`/观察面 grant 门控/K4–K7）+ `space.py` 下半（§3.7 追加 8 导出 → 18：GraphSpace/GridSpace/`SpaceMapping`/spaces codec/`entity_domain_positions`，S-INV-1~5）+ `gameplay_mode.py` 上半（§3.10 7 导出 + `ModeInvariantError`，D-P4-14 合并语义）；前置勘误 **ERR-P4-1**（`6a6f19e`：`ContextBuildInput` 增 `actor_id` 字段，首位）；B1（space 下半）→ B2（T02 ∥ T08）串行/并行 = T02 依赖 `entity_domain_positions` |
| P4-T01+T09（Wave C） | `f3b92f4` | `behavior_policy.py`（§3.9 4 导出：`BehaviorPolicy` 协议/`run_policy_decide` 同步纯函数（D-P4-01）/`PolicyActorMismatchError`）+ `gameplay_mode.py` 下半（§3.10 追加 8 导出 → 14：`merge_modes`/`apply_mode_change`（M-INV-2/3/5）/`is_action_available`/`ModePolicy`/`ModeOverlayRegistry`）；前置勘误 **ERR-P4-2**（`76c82d0`：§3.8 单测口径 TypeError → `FrozenInstanceError`，代码库基线 `pytest.raises(FrozenInstanceError)`） |
| P4-T10a（Wave D） | `ac9cbe1` | `conftest.py` P4 节（§5.1 逐字 + 20 条机械 `# noqa: E402/F401`，commit 自述「20 noqa 机械偏离」）+ 6 模块单测 **141 用例**（test_capability 6 / test_knowledge 29 / test_space 21 / test_context_provider 31（5 类）/ test_behavior_policy 14 / test_gameplay_mode 32） |
| P4-T10b（Wave E） | `fc27517` | `test_p4_gate_scenario.py`（896 行，7 函数：`test_g4_1~6` → #1–#19 + A1–A6 行强化 + `test_g3_handoff2_fingerprint_disclosure`）；S0 装配逐字（§5.1 L1427-1456）；S12/S13 逐字（§5.2 L1477）；S11 终态 9 事实 = 共享场景前提（模块 helper `_run_branch_a`）；披露：thaw 缝面比对（值逐字）/ A6① roundtrip 参照 = 纯 JSON 镜像 / A6③ 双跑延至 Wave F（Leader 裁定）；全量 2375 passed + 1 已知红（预披露 stems 锚点） |
| P4-T10c（Wave F） | `42a38ee` | `test_p4_adversarial.py`（1036 行，10 函数：A1–A8 + M1①②③/M2）+ `test_p4_integration.py`（497 行，11 函数：R1–R8 分支 A/B + C1–C3）+ **Leader 锚点同步**（`core/__init__.py` 249→308 纯增量 / `test_closeout.py` 32/308 / `test_import_boundary.py` 32 + P4 常量块 + `TestP4Boundary`）；已知红闭合；全量 **2399 passed / 0 failed** |
| G4 文档级闭合 | `9baa5b7` | **ERR-P4-3**（设计 §9 纯追加）：G4-R1 盲审 DOC findings 闭合——D7/D8/D9 偏离登记（GraphSpace 重复节点 id / GridSpace bool-非int w/h / `merge_modes` action_filter 单胜者记录）+ 错误族总表族分类解读（L441/L728 vs L351/L611）+ M-INV-6 编号定义 + `make_backend` 参数缺失 KeyError 错误面注明 + conftest「逐字 + 20 机械 noqa」口径；代码行为零变化 |

---

## 4. 审查历史（对抗式独立盲审，全部 qiyuan-self / qwen3.8-27b）

### A. 设计阶段（P4-DESIGN，裁决链记录于 `c162d19` 提交正文与设计 §9 勘误留痕）

| 轮 | 结果 |
|---|---|
| R1–R4 | 全闭合；findings：A 0 / B 2 DOC + 1 INFO / C 1 DOC + 437 引用核验 W=0 / D 1 INFO；0 阻塞、0 补充 |
| R5 | 收尾轮关闭；残留 3 DOC 按 G3 DOC-1 先例免费文档级补丁闭合（不复审、不占预算）：A5b 标签 → M1③、A7 ①=A7a/②=A7b 声明、5 处章节区间端点收紧（552-582 / 1044-1111 / 1341-1392 / 1396-1452 / 818-838） |

设计阶段实质补充轮：**0/3**。

### B. 实现门禁 G4（本 Gate）

| 轮 | 审查点 | 结果 |
|---|---|---|
| G4-R1 | `42a38ee`（Wave F，4 名独立盲审，全新一轮全新盲，盲审纪律：禁读 `.review-drafts/` 既有报告 / 只读仓库 / 只 `.venv/bin/python`） | **4/4 通过/投机通过，0 SUPPLEMENT、0 BLOCK、0 执行失败**：R1 模块契约面 = 通过（5 DOC + 4 INFO；每模块 ≥3 不变量独立探针核验，56 项探针）；R2 测试规格面 = 投机通过（1 DOC + 7 INFO；34+ 条行级设计锚比对全命中，19 编号断言/R1–R8/C1–C3/A1–A8/M1–M3/S0/S12-S13 逐一核验）；R3 不变量与冻结面 = 通过（2 DOC + 1 INFO；K1–K8/M-INV/S-INV/D-P4 ≥8 条独立核验 + 冻结空 diff 抽验 + 锚点账本机械重算）；R4 执行与确定性面 = 通过（3 INFO；全 suite 2399/0 + ruff clean + 白名单 20 文件 + 双跑逐字一致 + 跨测试 import 0 命中 + conftest 最新变更 = fc27517 + A1/A2 独立探针复现）。四名各自 V1/V2/V3 执行验证数字一致（2399/0、ruff clean、whitelist 20 文件） |

G4-R1 DOC findings（5 类，均文档级）按 2026-08-20 协议以 **ERR-P4-3**（`9baa5b7`）
文档级闭合，不消耗补充预算、不触发复审：① 三处「列入 deviations」登记缺口 →
D7/D8/D9 登记；② 错误族总表 vs 字段级 pattern 规格内部矛盾 → 族（ValueError 族）
分类解读裁定；③ M-INV-6 编号缺失 → 编号定义；④ `make_backend` 参数缺失错误面
沉默 → KeyError 注明；⑤ conftest「逐字」标签 vs ruff 纪律 → 「逐字 + 20 机械
noqa」口径。G4 实质补充轮：**0/3**。

---

## 5. 偏差登记（Architecture deviations，全部已披露）

**设计预披露（设计 §8.5，D1–D6；实现零偏离）**：D1 同步 decide（Spec async →
同步纯函数，D-P4-01）；D2 无通用 registry 模块（三注册表归属各自领域模块）；
D3 模式簿记走 `rebuild_runtime` 而非世界流水线（非世界 effect，K2）；D4
closeout/import_boundary 多行结构性编辑（§6.4/§3.11 预披露精确口径）；D5
`scheduler_fingerprint` 零变化（`wakeup_hooks` 指纹中性，测试层披露）；D6 P4 承接
组件类型注册（P9 必须复用，4 组件常量 + 编解码）。

**ERR-P4-3 新登记（设计 §9，G4-R1 盲审闭合）**：D7 `GraphSpace` 重复节点 id 拒绝
（G-INV 清单外的确定性扩展）；D8 `GridSpace` bool/非 int w/h 拒绝（「w/h ≤ 0」
钉死面外的 fail-fast 扩展）；D9 `merge_modes` action_filter 单胜者记录 = 排序首现
kind 等于最终 kind 的 overlay（确定性 + 排列不变，`test_gameplay_mode.py:503-519`
钉住）。

**实现/门禁侧（本登记，D10–D22；全部 commit 自述或 Leader 裁定留痕）**：

| # | 偏差 | 披露状态 |
|---|---|---|
| D10 | conftest P4 段 = §5.1 逐字 + 20 条机械 `# noqa: E402/F401`（剥离后 ruff 失败；「逐字」读作机械 lint 注释归一后字节一致，ERR-P4-3⑤） | 已披露（`ac9cbe1` commit 自述 + ERR-P4-3） |
| D11 | M1①②③/M2 落 `test_p4_adversarial.py`（设计 §5.5 未钉宿主文件；M1④ 按 §6.4 钉死 `TestP4Boundary`，精确命中） | 已披露（文件 docstring Leader 裁定 + G4-R1 R2 INFO 核验合理） |
| D12 | A6③ 独立双跑（事件键同构 + `logical_tick` 全 None）落 adversarial 文件（gate 文件实现 A6 ①②④） | 已披露（`fc27517` commit + Leader 裁定） |
| D13 | A5 全行同时断言于 `test_g4_4` 与 `test_g4_6`（§6.2 两行均声明 A5 强化）+ `test_a5`（adversarial） | 已披露（G4-R1 R2 INFO 核验） |
| D14 | gate 场景 `component_view`/`entity_domain_positions` 深冻结面以引擎自有 thaw 缝归一为 JSON-native 面比对（值逐字，无近似容差） | 已披露（`fc27517` commit） |
| D15 | A6① JSON roundtrip 参照 = 纯 JSON 镜像（非世界对象同一性） | 已披露（`fc27517` commit） |
| D16 | gate 上下文构建取 `tick=42`/`wake_reason=None`（设计仅对 S 表场景构建钉死取值；G4-1..G4-3 构建面） | 已披露（Leader 裁定 + G4-R1 R2 INFO 核验合理） |
| D17 | S13 逐字请求 `request_id` 命名 = `req_tac`（§5.2 逐字块未钉该字段命名，零语义差异） | 已披露（Leader 裁定） |
| D18 | S0–S13 以模块级 helper `_run_branch_a` 装配（S11 终态 9 事实 = 9 条共享场景前提断言，`_run_branch_a_terminal` 复用） | 已披露（`fc27517` commit + G4-R1 R2 INFO） |
| D19 | A7③ 按调度器实际错误结果语义实现（hook 异常不穿透 `fast_forward`；per-tick-batch 前置状态对捕获 scheduler.py:1328-1329，错误路径 :1436-1450 返回空 tx/evt/trace/transitions + errors；设计 L1684「恢复 tick 前状态」在批粒度提交点下唯一自洽解释 = 已提交 theft 不回滚、失败 wakeup 批恢复 post-theft 状态） | 已披露（F1 源码行引文自述 + Leader 独立源码核验） |
| D20 | `core/__init__.py` 间隙内多新名按设计 L773 表行序落位（D-I1 注，不 casefold 重排）；`__all__` 单引号风格保持 | 已披露（Leader 锚点同步，设计 L773 预披露） |
| D21 | Leader 锚点同步注释修正（`test_closeout.py` L89 26→32 注释、`test_import_boundary.py` L50 19→32 注释）零断言零行为；`core/__init__.py` 模块 docstring 未动（设计沉默，不越权改写 P3 历史行） | 已披露（`42a38ee` commit 正文） |
| D22 | adversarial `_assemble(max_tick=None, policy=BobPolicy, capability_table=gate_table)` 2 个参数化点（默认值 = gate 场景值，docstring 逐点披露） | 已披露（F1 自述） |

---

## 6. 风险登记册（Open risks — G4-R1 已核实残留 + 设计移交，供后续 bug 排查参考）

1. **D7 补覆盖（非阻塞）**：`GraphSpace` 重复节点 id 拒绝（D7）无专项测试断言
   （超出设计 G-INV 清单面的扩展行为，G4-R1 R1 探针已独立验证精确抛
   `SpaceInvariantError`）；后续 P4 触及 space 测试时补一条断言即可，不阻塞门禁。
2. **P5 义务：`scheduler_fingerprint` 输入面扩展**（G3 移交 2，G3:163）：P4 真实
   接线改动一个构造输入 `wakeup_hooks`（指纹中性，D5，测试层披露）；把
   named_triggers/trigger_registry/wakeup_hooks/condition_resolvers 四 callable
   配置面纳入指纹（或维持披露分支）= P5 义务。
3. **P5 义务：重提案策略内容**（G3 移交 3，D-P4-16）：P4 提供缝/契约/集成证明
   （A7① 全管道 ACCEPT + 诊断 + 收敛路径）；中断后「决定做什么」的行为策略内容
   = P5。P4 永不产出 REPAIR（scheduler 路径 `allow_rebase=False`）。
4. **P5：LLM 策略内容**：`BehaviorPolicy`/`ModePolicy` 两协议 = LLM Director 接入
   点（D-P4-16 机械层→P4、内容层→P5）；P4 六模块零 provider/LLM 面（M1 机械
   核验，12 名封闭集 0 命中）。
5. **P9 义务：knowledge 组件类型复用**（D6）：P9 knowledge 模块必须复用 P4 已注册
   的 4 个 `ComponentTypeId` 常量（OBSERVATIONS/KNOWLEDGE/MEMORY/SPACES_COMPONENT）
   及编解码，不得重复注册或新增 Kernel 字段。
6. **P8 消费面：`input_policy` 不透明直通**（M-INV-6，ERR-P4-3③ 编号定义）：
   内容语义归 P8 表现层，P4 不解释（§10 裁定说明 3，renderer/UI 合并未落地 = P8）。
7. **口径备注**：`make_backend` graph/grid 参数缺失 = 裸 `KeyError`（ERR-P4-3④ 注明，
   设计沉默点）；具名错误构造双轨（直接构造路径具名 ValueError 族 / `model_validate`
   路径 pydantic ValidationError，同 ValueError 族，D-P4-17 族分类不受影响，
   各模块 docstring 披露）。

---

## 7. 移交 P5 的接口与约束（Handoff Notes）

1. **策略协议入口（D-P4-16）**：P5 实现 LLM 策略时经 `BehaviorPolicy.decide`
   （同步纯函数，`run_policy_decide` 门面）与 `ModePolicy.resolve` 两协议接入；
   `ActorDecisionContext` 13 字段（构建期物化，只持值不持世界引用）+ `wake_reason`
   字段 + `PolicyWakeupHook`（§5.1 conftest 逐字模型）= 既有缝，P5 不改缝。
2. **确定性纪律延续**：P5 策略内容若引入非确定性，必须收敛在协议实现内部（门面
   内等待/超时 → None，D1 口径）；P4 六模块 AST 黑名单面（M1）对 P5 新模块同样
   适用（import 边界常量块模式：`P5_SUBMODULES` 等，§6.4 先例）。
3. **fingerprint 义务**（G3 移交 2）：见 §6-2。
4. **认识论边界不变量**：P5 的任何「prompt 换权限」式实现 = K4 违背（G4-2/A2 断言
   面为回归防线）；可见集四源（self/观察/知识引用/local 邻域，CX-INV-2/3）为
   context 构建唯一授权输入。
5. **P9/P8 义务**：见 §6-5/§6-6。
6. **G5 门禁参照（Plan §14）**：零 Python 项目可以 load + validate / Python plugin
   必须显式注册 / 不允许目录自动扫描执行任意 Python / module dependency cycle 可
   诊断 / DSL 不重新发明 Python（无 loop/function-definition）/ validator 返回
   machine-readable diagnostics——P5 设计应逐条回应（先例：P4 设计 §1.2 对 Plan
   §13 G4 六条的逐条回应体例）。

---

## 8. 决策

**Decision: PASS**（G4-R1 最终轮 4/4 独立盲审 通过/投机通过，0 补充、0 阻塞、0 执行
失败；ERR-P4-3 文档级闭合；风险登记册见 §6；偏差全部披露见 §5）。

按 M1 自动化授权与 2026-08-20 人工指令协议，G4 关闭，**进入 Phase 5 — Project
Format / Module / Plugin / DSL**（计划 §14）。
