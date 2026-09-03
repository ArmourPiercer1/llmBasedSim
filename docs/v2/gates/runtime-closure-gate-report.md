# Runtime Closure Gate Report — production game path 闭环（终版）

按 `docs/plans/llmBasedSim_12h_complex_game_runtime_closure_subagent_plan.md`
§13（最终 Gate C1–C9）与 §12（Review/integration）编制。
T1–T11 全部波次完成，T11 E2E 独立验收发现 L1–L3 / F1–F3 问题，Leader
修复窗（ERR-C-01..05）收敛后双评审 blocker 全清，本报告为 closure 最终
交付点记录。

回答计划 §13 的头号问题：**现在能否停止继续造 subsystem，开始用这个引擎
造复杂游戏？** —— 是（C1–C9 全过；证据见 §3）。

---

## 0. 基础信息

- **Gate**: runtime closure（12h 复杂游戏 runtime 闭环，Plan §13 C1–C9）
- **分支**: `architecture-v2`
- **提交面**: `0b3eae4`（P5 gate ruling，closure 起点）.. 本报告提交
  （T1..T11 + 修复窗 + docs；逐提交见 `git log --oneline 0b3eae4..HEAD`）
- **审查基准**: 全仓基线 **3205 passed / 0 failed**（closure 起点真实输出）
- **测试基线**: 全量 **3348 passed / 0 failed**（最终回归真实输出，
  19.3s；增量 = T1–T8 +103 / T9 +23 / P5-06b +1 / T11 E2E +16 =
  3205+143 恒等式对账一致；零新增失败）
- **审查执行**: 逐波 Leader seam review + 收口波双盲评审
  （R-runtime：1 blocker B1；R-authoring：2 blockers）+ Leader 修复窗 +
  T11 E2E 复验（blockers-only 口径）
- **冻结面纪律**: P9/P10 锚定文件 append-only（L1–2625 零改），闭包刷新块
  EOF 纯追加（最后赋值生效，ERR-P10-09 同形）；生产 src 触碰面 =
  `src/engine_v2/runtime/**` 12 文件（R-runtime criterion 6 核验干净）

---

## 1. Plan §13 字段（最终 Gate 模板逐字回答）

```text
Gate: runtime closure（C1–C9）
Commit SHA: 215ba80（代码面：T11 E2E 重钉收口）；docs 闭合链至本报告提交
Tasks completed: T1 materialize / T2 engine / T3 extensions / T4 context /
       T5 llm_binding / T6 action_binding / T7 dynamics_binding /
       T8 observability / T9 assembly / T10 reference game /
       T11 E2E 独立验收（全部）
Tasks waived: （无）
Tests: 3348 passed / 0 failed（最终回归真实输出；恒等式
       3205+103+1+23+16 = 3348 对账一致）
Known failures: （无）
Architecture deviations: ERR-C-01..05 勘误登记（§5 逐项）+
       P4↔P5 跨面张力裁决（JSON-clean 适配器，ERR-C-03）+
       P9/P10 import 授权例外 4 处（§6）
Open risks: §7
Human review required: H-closure——examples/complex_minimal 真实 LLM
       部署实玩验收（Plan §14 语义；本 gate 脚本化验收不替代主观体验）
```

---

## 2. 闭环链路（production-only game path）

```text
GameProject (YAML + explicit Python package, examples/complex_minimal)
  → load_project / build_ir / validate            （P5 content，0 error）
  → materialize_world                             （T1：IR → WorldState 权威面）
  → load_extensions (trust_python=True)           （T3：仅声明 entrypoint 被 import）
  → bind_actions                                  （T6：标准面 + extension executors）
  → bind_dynamics                                 （T7：backend 透传 + metadata→grant 派生）
  → 授权面构建（closed-by-default DENY；单写权拆分，§5 ERR-C-05）
  → bind_llm_policies                             （T5：P6 build_llm_policy 复用）
  → WorldInstance（13 字段 seam）→ EngineInstance
      tick 五相位：due wakeups → policy/executor → dynamics
                   → action lifecycle → 时钟
      一切世界写 = ProposedEffect → Authority → Transaction → Reducer（K2）
  → view() = derive_scene_view(committed world)
```

零 `tests.*` import、零第三方新依赖、零 P5 schema 扩展、零新框架。

---

## 3. Gate C1–C9 证据（Plan §13 编号；测试面 = T11 E2E + 模块级双层覆盖）

| Gate | 判据 | 证据 | 结果 |
|---|---|---|---|
| **C1 Authoring** | 新 GameProject 可 load/validate/assemble | P5 链 0 error（R-authoring 实测）；`assemble_project('examples/complex_minimal', trust_python=True)` → engine 非 None + 0 error 级诊断；E2E `test_c3_*`/`test_c4_*`；T1/T9 模块级 | ✅ |
| **C2 Trusted Python** | 仅声明 entrypoint 被 import；rogue 不 import | E2E `test_c2_undeclared_module_never_imported`（tmp 副本 + rogue.py，trust=True 装配成功 + sys.modules 差集无 rogue）；T3 零扫描测试族 | ✅ |
| **C3 Python Action** | executor → ProposedEffect → Authority → Transaction → Reducer → state change | E2E `test_c5_inject_heat_*`：`submit_action(operator, inject_heat, {})` → ok、零诊断、machine.power 2→3 **COMMITTED**、revision 0→1、恰 1 txn（修复窗 F1 自举后实测）；cool 同管道 power 2→1 | ✅ |
| **C4 Python Dynamics** | backend → ProposedEffect → same commit pipeline | E2E `test_c6_dynamics_tick_commit`：fresh `advance(1)` → temperature 20.0→24.0（`20 + 0.2·(12+14·2−20)·1`，approx abs=1e-9）+ 恰 1 COMMITTED txn（base 0 → commit 1）+ 零诊断 | ✅ |
| **C5 LLM Actor** | P6 LLMPolicy → ActionProposal → same action pipeline → state change | E2E `test_c7_*` 全链（FakeInferenceBackend 脚本）：`wake(ent_authoring_watchman)` + `advance(1)` → backend.calls=1、提案 inject_heat → **同一管道** COMMITTED（machine 2→3）+ dynamics 同刻温度 20→26.8（power=3 精确积分）、恰 2 committed txn、sink 记录 prompt_assembly + llm_call 事件（修复窗 G1/G2/F3 后实测） | ✅ |
| **C6 Knowledge boundary** | NPC prompt/context 不含不可见实体完整 view | E2E `test_c9a_actor_context_visibility`：`global_entity_views is None`（未授权即不投影）、self_view 在场、visible_entities 精确集、候选动作仅声明面；L3 运行时块对不可序列化/未授权字段渲染字面 `"null"`（不泄漏） | ✅ |
| **C7 No test runtime** | `src/engine_v2/runtime/**` 零 `tests.*` import | E2E `test_c1_*` 三重：AST 全模块扫描 + 禁用字面串扫描 + 装配前后 sys.modules 差集（trust=True 全链后无 tests 前缀模块）；修复窗 L3 字面违例 3 处已清（xfail 摘除） | ✅ |
| **C8 Repeatability** | Fake LLM + deterministic backend 双跑一致 | E2E `test_c9c_double_run_byte_equal`：双独立装配 + 同输入序列 → `dump_json(world)` 字节相等 + sink 逐事件 `to_dict()` 全等；T9 `test_gate3_k7_*` 双装配字节相等 | ✅ |
| **C9 Regression** | 原有 suite 无新增失败 | 最终回归 **3348 passed / 0 failed**（基线 3205 + closure 净增 143，无删除、无既有失败） | ✅ |

**Gate 全过：C1–C9 = 9/9。**

---

## 4. T11 E2E 独立验收发现（blockers 全清）

T11（tests-only 独立验收，653 行 16 测试）钉出三类问题，Leader 修复窗
全部收敛（修复后 T11 复验重钉）：

| # | 发现 | 根因 | 修复（ERR） |
|---|---|---|---|
| L1 (G1) | NPC policy 不可达：binding 以 authoring slug 键、engine 以实体 id 查 → `no_policy` 恒真 | T5/T2 键空间错位，T9 装配未桥接 | ERR-C-02：assembly 步 12 重映射（slug → `ent_authoring_<slug>`，T2 实体 id 契约；T5 冻结面不改） |
| L2 (G2) | 真实 T4 context → assembler L3 块 json.dumps `granted_capabilities`（frozenset）抛 ValueError，P6 decide crash | P4 富类型 context 字段 × P5 json-clean 组装的跨面张力（各冻结面自洽，端到端首曝） | ERR-C-03：`JsonCleanContextPolicyAdapter`（runtime 装配层适配位；13 字段探测、不可序列化者影子置 None → "null" K4 不泄漏） |
| L3 | 3 个 runtime 模块 docstring 含禁用字面串 "import tests" | 字面纪律（机械双查口径） | ERR-C-04：docstring 措辞改写（零语义变更） |
| F1 | machine 组件永不物化 → inject_heat/toggle_machine 恒 action_failed | P5 作者面无物品组件挂载面 + materialize 不产 machine | ERR-C-05：executor 首动作以 schema 缺省自举落位（与 dynamics 温度自举同款） |
| F2 | 双 producer 同 claim machine+temperature → 首条匹配拍板下动作侧恒拒 | T10 样例 grant 设计（A8 文档面预警过） | ERR-C-05：单写权拆分（executor 独占 machine、dynamics 独占 temperature；cool 语义 = power−1；冗余显式 dynamics grant 删除） |
| F3 | 场景 prompt 声明 3 个变量 ∉ CONTEXT_VARIABLES 封闭 13 集 | T10 样例面（K4 天花板） | 模板变量改 [actor_id, tick, wake_reason, candidate_actions] + 功率语义文本 |

F4（SceneView 无组件载荷 = P10 设计面，组件在场于权威世界）与 F5
（trace 面 = 逐事件 `to_dict()` 冻结面）为口径记录，零代码变更。

---

## 5. 勘误/偏差登记（ERR-C-01..05）

- **ERR-C-01**（test 隔离）：`test_contracts.py` fresh-import 测试补 B2
  同款 save/restore（原先新模块对象泄漏进 sys.modules → 类身份分裂 →
  测试期首 import 的 Python 扩展 isinstance 断裂；P3 潜伏、closure 首曝）。
  同步 skeleton 测试 re-export 豁免参数化（runtime/__init__ 导出台账，
  同 core P1 收尾先例）+ P9/P10 锚定 EOF 刷新块（闭包两波，append-only）。
- **ERR-C-02**（键空间）：见 §4 L1。WorldInstance.policies 键 = 世界实体
  id（runtime 域契约）；binding 面 slug 键保留（authoring 域）。
- **ERR-C-03**（JSON-clean 边界）：见 §4 L2。适配位 = runtime 装配层
  （composition 面职责），P4/P5/P6 冻结面零改。
- **ERR-C-04**（字面纪律）：见 §4 L3。
- **ERR-C-05**（单写权）：见 §4 F1/F2。授权面语义登记：P2 首条匹配拍板 ⇒
  每 component_type 恰一有效 writer（runtime README 授权面节固化）。

---

## 6. 授权例外（Leader 裁决）

- runtime → P9/P10 面 4 个 import 为契约授权（非 criterion 3 违约）：
  `materialize→modules.space`、`context→modules.perception`（T4 卡面
  build_observations）、`action_binding→modules.actions`（T6 卡面
  MoveExecutor）、`engine→presentation.view`（contract §2
  `view()=derive_scene_view(world)`）。零环（P9/P10 面零 import runtime）。
  R-runtime criterion 3 疑问 → 本裁决闭合。

---

## 7. Open risks / follow-ups（非 blocker）

1. 长动作生命周期（start/complete 两跳）——engine 现面 = 短动作
   （duration 0/1 tick）；follow-up（T2 assumption 面）。
2. 引擎相位级 trace 接线（现 sink 记录 policy/dynamics/commit 事件族；
   相位边界事件留面）——follow-up（T8 面）。
3. P5 DSL 规则 → WorldRule 翻译器（dynamics_binding 现面对 DSL 规则逐条
   warning 不投影）——follow-up。
4. SceneView 组件载荷投影（P10 设计 = 视图不带组件数据；游戏 UI 若需
   投影需 P10 面决议）——F4 记录。
5. H-closure 人类实玩验收（真实 LLM 部署 + 主观体验）——本 gate 不替代。

---

## 8. 双评审与复验记录

- **R-runtime**（盲评审，11 文件 + README + 契约 + 提交面）：verdict FAIL ×
  1 blocker（B1 = ERR-C-02 键错位；criterion 7 逻辑缺陷口径）+ 5 非 blocker
  观察（§6 裁决 / C3 演示缺口 = ERR-C-05 / G2-G3 墙 = ERR-C-03+F3 /
  工作树 untracked 记录 / L3 字面）。
- **R-authoring**（盲评审，examples 全面 + P5 链实测）：verdict FAIL ×
  2 blockers（machine 死环 = ERR-C-05 F1 / 双写冲突 = ERR-C-05 F2）+
  4 非 blocker 观察（冗余 dynamics grant → 已删 / grid warning 可接受 /
  headless warning 预期 / character_profile 投影提示）。
- **修复后复验**：T11 E2E 复验重钉（16/16 全绿，单文件 0.32s，
  2026-09-04 01:45 CST）+ 最终回归 **3348 passed / 0 failed**。
