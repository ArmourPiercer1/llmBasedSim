# G2 Gate Report — Phase 2 Effect / Authority / Transaction Kernel（终版）

按 `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` §11、§21、§25 编制。
本报告取代初版 Integration Agent 报告（HEAD `6b0a33d`，1441 测试，已被后续修复与审查历史超越）。

---

## 0. 基础信息

- **Gate**: G2（Phase 2 — Effect / Authority / Transaction Kernel 门禁）
- **Commit SHA**: `a7485c4`（HEAD，Phase 2 最终交付点）
- **分支**: `architecture-v2`
- **审查基准**: `d6251a0`（P2-DESIGN）.. `a7485c4`；P1 冻结基线 `603535e` / M1 冻结提交 `c62faa5`
- **测试基线**: 全量 **1491 passed**（`tests/engine_v2` 子集 1040 passed）；`ruff check src/engine_v2 tests/engine_v2` → `All checks passed!`
- **审查执行**: 全部 `qiyuan-self / qwen3.8-27b`（2026-08-20 人工路由覆盖，见 `docs/plans/model-routing-providers.md`）；门禁审查 = 原计划 2 名 × 2 = **4 名独立盲审**，四裁决协议（通过/投机通过/补充内容/阻塞）

---

## 1. §21 字段

```text
Gate: G2
Commit SHA: a7485c4
Tasks completed: P2-DESIGN, P2-T01 ~ P2-T09（全部），+ Remediation（B1/B2/B3），
                 + 补充轮1（guard 槽泄漏），补充轮2（注册表快照化 + commit 路径 6b），
                 + 补充轮3（apply_committed_effects 复检 + 双前缀清理，人工批准例外轮）
Tasks waived: 无
Tests: 1491 passed（真实输出，.venv python，-p no:cacheprovider）；tests/engine_v2 1040 passed
Known failures: 0（v1 基线的 30 项 ruff 已知失败属 v1 冻结代码，不在 engine_v2 门禁范围）
Architecture deviations: 见 §5 偏差登记（全部已披露/已登记，无未声明偏差）
Open risks: 见 §6 风险登记册（全部为已声明级别残留，加固项排期 P3/P8）
Human review required: 否（M1 自动化授权范围内；补充轮3 已获人工事前批准）
Decision: PASS
```

**通过口径**（2026-08-20 人工指令协议）：4/4 盲审给出 通过/投机通过，无补充内容、无阻塞、无执行失败。

---

## 2. 门禁判据验证（计划 §11 G2 + 扩展判据）

### A. "必须测试" 7 条（全部真实通过，test_adversarial.py TestScenario1~7 + 各模块测试）

| # | 判据 | 证据 |
|---|---|---|
| 1 | 无权限 producer 写 state → reject | 越权探针（含伪造 authority_scope 变体）→ DENY；`check_authority` closed-by-default |
| 2 | 两个合法 writer 冲突 → resolver 可解释 | 四策仲裁链（authority→timestamp→producer→FIFO），WINNER/REJECT 可解释 |
| 3 | transaction 一项 invalid → 原子失败 | 3 条 atomic-failure 路径 → ABORTED，`new_state is base_state` 恒等、零事件 |
| 4 | commit 只增加一次 revision | 5-effect 事务 → revision 恰 +1 |
| 5 | event 保存 transaction/source/cause | K6 六元 provenance（txn_id、source/origin、CauseRef、world_revision、authority trace、cascade ctx）逐字段验证 |
| 6 | HP changed → set HP → HP changed 循环可检测 | 同位置重访 1 轮 cycle_detected；异位置链恰 max+1 轮 cascade_depth_exceeded；strict 模式抛 CascadeDepthExceededError |
| 7 | 任何 Public API 无法绕过 reducer 写权威状态 | guard 门面全内省/反射/序列化向量探针（含 name-mangled 名、token 槽、注册表解析链、pickle/copy/deepcopy）全部洁净；模块级注册表仅存深冻结快照，篡改副本不波及权威状态 |

### B. G2 静态三项（独立 AST/导入扫描 + 代码阅读）

- Runtime Producer 路径中不存在直接 authoritative state mutation —— 成立（零违规）；
- Reducer 不调用 LLM —— 成立（生产代码零 LLM/网络/v1 导入）；
- Reducer 不做语义推断 —— 成立（未注册 effect_type 即 ReducerError，D-P2-05）。

### C~F. 其余判据

- **C. K1~K8 不变量**：K1/K2/K3/K6 经对抗探针攻击成立（K7 归 P3）；
- **D. P1 冻结契约**：13 个契约模块与 `603535e` 逐字节一致（`git diff --quiet` 逐一验证）；`__init__.py` 纯增量（导出 93→196，零删）；§10.1 三项 P2 义务闭合（C2 晋升 core 无双源、C3 四条 pydantic 逃逸路径全拦截、ID-kind 跨族/错前缀全拒）；
- **E. P2 设计文档 D-P2-01~20 与 §11 对抗测试规格**：实现且真实运行；文末勘误 E1–E6、R1–R5 逐条独立核实与代码事实一致（R3 曾失准，已在补充轮 2 修订并复核）；
- **F. 双事务入口 revision 一致性**：`commit_transaction`（步骤 6b）与 `apply_committed_effects`（步骤 2 复检）两条路径上 future/stale/任意不一致的 effect 批均被拒绝且无任何部分应用（补充轮 3 闭合直调/P8 回放路径）。

---

## 3. 任务完成情况（Tasks completed）

| 任务 | 提交 | 交付 |
|---|---|---|
| P2-DESIGN | `d6251a0` | `docs/v2/contracts/P2-kernel-pipeline-design.md`（Spec B 落地，20 项决策 D-P2-01~20 + §11 对抗测试规格 + §7.3 级联伪代码；文末勘误 E1–E6/R1–R5 为后续审查产物） |
| P2-T01 | `fe8f32e` | `reducer.py`：Reducer-only 写屏障、`core.*` 结构效果词表、`EffectHandlerRegistry`、`guard()` 门面 |
| P2-T02 | `fe8f32e` | `authority.py`：`AuthoritySelector`/`AuthorityRule`/`AuthorityPolicy`/`ProducerRegistry` 数据契约 |
| P2-T03 | `b2c5864` | `authority.py`：求值管道（closed-by-default、首匹配、五维选择）与 Trace 协同 |
| P2-T04 | `b2c5864` | `validation.py`：L1/L2 校验管道、ID 种类词法复检、`check_transaction_references` 晋升入 core（C2 闭合） |
| P2-T05 | `77f016d` | `conflicts.py`：锁提取、连通分量、四策仲裁链、staged create→set_component 依赖豁免 |
| P2-T06 | `77f016d` | `transaction_executor.py`：`commit_transaction`/`abort_transaction` 原子提交 + L2 终检 |
| P2-T07 | `1e195ee` | `cascade.py`：`CascadeExecutor` 级联管线（深度 8/环路熔断/事件 1:1 发射/溯源保持）、写屏障全局武装点 |
| P2-T08 | `1e195ee` | 环路/深度诊断（CycleDetector + CascadeDepthExceededError + 诊断输出） |
| P2-T09 | `6b0a33d` | `test_adversarial.py`：7 类对抗场景 + G2 静态审计（后经三轮补充扩充至 1491 全量） |
| Remediation | `7bdad23` | B1 create_entity 管道（created_in_batch 批级暂存 + 冲突依赖豁免）、B2 GuardedWorldState 容器泄漏（`_FrozenMapping` 深冻结视图）、B3 对抗测试补强 32 例 |
| 补充轮 1 | `c714b17` | GuardedWorldState mangled-slot 活状态泄漏：token 注册表机制（实例不承载状态引用）、实体/场景视图值化、`__reduce__` 拦截、4 回归测试、勘误 E1–E5 |
| 补充轮 2 | `991ec62` | `_GuardEntry` 纯快照化（JSON roundtrip 深冻结副本，注册表任何时刻解析不到活权威状态）、commit 路径步骤 6b base/commit revision 一致性检查（第三类原子失败源）、8 回归测试、静态审计扩展注册表-状态访问模式、勘误 R4/修订 E1、R3 |
| 补充轮 3（人工批准例外轮） | `a7485c4` | `apply_committed_effects` 逐 effect base_revision 一致性复检（直调/P8 回放路径闭合，应用前原子 ReducerError）、步骤 6b abort_reason 去重前缀、6 回归测试、3 处 fixture 数据修正（断言零改动）、勘误追加 |

**Tasks waived: 无。**

---

## 4. 审查历史（对抗式独立盲审，全部 qwen3.8-27b）

| 轮次 | 裁决 | 关键发现 | 处置 |
|---|---|---|---|
| 原双审（GLM+QMax，API 故障前） | 2× REJECT | B1 create_entity 恒 ABORT（missing_entity 误报）、B2 GuardedWorldState 返回活可变容器（K2 违背）、B3 静态扫描过弱 | Remediation `7bdad23` |
| R1（4×盲审） | 1×补充 + 3×投机通过 | `_GuardedWorldState__wrapped` 经 name-mangling 取回活权威状态，原地突变静默成功（无 revision/事件/trace）；reducer 文档声称被证伪 | 补充轮 1 `c714b17` |
| R2（4×盲审，全新盲） | 2×补充 + 2×投机通过 | `_GUARD_REGISTRY[token].state` 持活引用（token 可读→注册表解析→突变，级联下随合法事务提交无效果声明）；勘误 R3 失准；commit 直调路径接受 future base_revision | 补充轮 2 `991ec62` |
| R3（4×盲审，全新盲） | 3×投机通过 + 1×补充 | `apply_committed_effects`（reducer 公共入口）缺逐 effect base_revision 复检（commit 路径 6b 有、直调入口无）→ P8 回放暴露；abort_reason 双前缀（外观） | 按协议两轮补充上限转 BLOCK → **人工批准例外第三轮** → 补充轮 3 `a7485c4` |
| **R4（4×盲审，全新盲，最终）** | **4× 通过/投机通过**（0×补充、0×阻塞、0×失败） | 残留风险均经独立探针确认"与登记严重度一致"；勘误 E1–E6/R1–R5 逐条核实为真；13 个 P1 模块逐字节一致；双入口 revision 一致性双路径实测 | **G2 关闭** |

> 备注：R4 的 4 名审查者中，2 名的完整裁决文本在本会话工具传输中被截断，但其裁决归属（通过/投机通过）由工作流聚合结果 `all_pass=true, has_supplement=false, has_block=false, failed_slots=[]` 权威确认；§6 风险登记册为 R1–R4 各轮已核实风险项的并集。

---

## 5. 偏差登记（Architecture deviations，全部已披露）

| # | 偏差 | 状态 |
|---|---|---|
| D-1 | C2"逐字迁移"字面未满足：`check_transaction_references` 实现中新增 create_entity/created_in_batch 语义（管线正确性所必需） | 已披露（代码 docstring + 提交 `7bdad23`），15 验收测试绿 |
| D-2 | `AuthorityDecision` 取值 "allow"/"deny"（沿用 P1 trace 词表） | 已披露 |
| D-3 | `CORE_SUBMODULES`=19、closeout 锚点 196（随导出面机械同步） | 已披露 |
| D-4 | 测试布局 `tests/engine_v2/core/`（设计文档 §2.6.1/§11 写 `kernel/`） | 勘误 E4 已记录 |
| D-5 | `CascadeConfig.strict` 为设计文档配置面之外的扩展（代码注释标明，缺省保持设计语义） | 已披露 |
| D-6 | 打包陷阱（P1 冻结，非 P2 缺陷）：规范导入路径 `src.engine_v2.core`；`engine_v2.core` 路径加载第二套不兼容类身份 | 已披露（P8 处理） |
| D-7 | 补充轮 3 修正 test_reducer.py 3 处 fixture 数据（`base_revision=` 实参），断言零改动——原 fixture 恰好编码了被修复的 bug 行为 | 已披露（工单外最小变更，人工批准轮内执行） |
| D-8 | 勘误 E3：设计文档 §3.1 正文 entity_class/entity_tags 维度与实现（5 单值维）不一致 | 以勘误为准（实现=计划 §11 口径），正文待后续文档修订同步 |

---

## 6. 风险登记册（Open risks — 投机通过审查者风险点并集，供后续 bug 排查参考）

按 2026-08-20 人工指令协议：SPECULATIVE_PASS 的门禁与风险点记录在案，供后续排查参考。

| # | 风险 | 严重度 | 可控性论证 | 后续排查/加固（责任阶段） |
|---|---|---|---|---|
| R1 | 写屏障唯一武装点为 `CascadeExecutor.__init__`（cascade.py:810）；绕过 cascade 直调 `commit_transaction`/`apply_committed_effects` 时 4 条 pydantic 逃逸路径敞开 | 低（已登记） | 逃逸产物为独立副本、与权威状态零别名，不构成权威状态损坏面；级联读侧全部经 guard() 快照；管线层 base_revision 双入口复检 + L2 引用检查拦截结构化绕过 | P3：内核运行时入口统一武装（或装配期恒武装断言 + 回归测试）；P8：确认无生产路径裸用未武装入口 |
| R2 | `write_barrier_exempt` 位于 core 公开导出面（`__init__.py`），显式绕过开关 | 低（已登记） | 上下文管理器语义明确、使用点可静态 grep 收敛，当前仅 reducer 内部工作副本与测试夹具使用；滥用可审计 | P3+：lint/审查规则禁止生产代码调用；P8：评估收窄为 devtools-only 导入面 + 审计计数 |
| R3/E2 | pickle 为第 5 条构造逃逸：armed 态 `pickle.loads(pickle.dumps(state))` 成功，产物为脱钩深拷贝（与权威状态零别名，篡改载入副本不波及权威）；unpickle 出的对象不自动 re-arm | 低（已登记） | 风险面是"影子世界副本"（离线分析/误用）而非权威状态损坏；管线 state 输入不受 producer 控制 | P8：屏障加固拦截 pickle `__reduce__`/`__reduce_ex__` 或反序列化后强制 `model_validate` 重校验 + 断言测试 |
| R4/D-15 | 原始 WorldState 嵌套容器（world_variables/组件 dict/scenario data）原地可变且 revision 不推进（P1 冻结 advisory，D-15） | 中（P1 已接受） | 影响仅限持有裸句柄的进程内代码；管道读侧（guard 快照）与提交侧（reducer 纯函数 + 双入口 base_revision 复检）不受污染；威胁模型为防御纵深而非进程内硬沙箱 | P8：对裸状态深冻结（MappingProxyType/copy-on-write）或 reducer 输入不对外暴露 |
| R5 | guard 注册表条目快照的嵌套 dict 进程内可变：篡改 `_GUARD_REGISTRY[tok].state.world_variables[...]` 反映到该条目自身 guard 的 `model_dump()`/`model_dump_json()` 读路径（仅副本，权威状态不可达、不受影响） | 低（已登记） | 模块私有白盒路径、非 Public API；E1"只污染该条目自己的副本"措辞经实测准确 | P8：评估注册表条目哈希校验 |
| R6 | 级联保守域锁可先于深度上限触发 cycle_detected（同位置每轮重提案场景；文档化行为） | 低（已文档化） | 影响面为必须测试 6 的场景构造方式（需每轮异位置），非正确性缺陷 | P3 测试构造时知悉；必要时 P8 调整锁粒度 |
| R7 | 打包陷阱：`engine_v2.core`（非 `src.` 前缀）导入加载第二套不兼容类身份（pydantic model_type 跨路径拒绝） | 低（P1 冻结） | 规范导入路径唯一且测试固定 `src.` 前缀 | P8：统一包导入方案 |
| R8 | 设计文档 §3.1 正文与实现维度不一致（勘误 E3 已裁定口径） | 极低（文档卫生） | 代码与勘误一致，实现=计划 §11 口径 | 后续文档修订时同步正文 |

---

## 7. 移交 P3 的接口与约束（Handoff Notes）

1. **武装入口**：P3 调度器统一经 `CascadeExecutor`（写屏障武装点）；R1 加固项（恒武装断言）建议随 P3 调度器装配落地。
2. **guard 语义**：producer/trigger 只应获得 `guard(state)` 视图（guard() 时刻深冻结快照，注册表 token 解析）；跨 commit 持 guard 不反映新状态——P3 每轮重新 guard。
3. **提交协议**：所有状态变更经 `ProposedEffect → Authority → Validation → Conflict → Transaction → Reducer → WorldState`；双入口（`commit_transaction` / `apply_committed_effects`）均有 base_revision 一致性复检；P3 stale proposal revalidation（P3-T07）应复用 `check_transaction_references` 与 L1/L2 管道，不另起校验源。
4. **P1 冻结**：13 模块字节级冻结（基线 `603535e`），P3 不得触碰；`__all__` 196 成员可纯增量。
5. **测试基线**：1491 passed / ruff clean；P3 新增测试为纯增量，既有断言零修改。
6. **G0 遗留（非阻塞）**：T04 真实 LLM 转录 + v1 boot proof 待 API key（G0 CONDITIONAL PASS 的遗留项，与 P2/P3 开发无依赖）。

---

## 8. 决策

**Decision: PASS**（4/4 独立盲审 通过/投机通过；两轮补充 + 一人工批准例外轮全部闭合；风险登记册见 §6；偏差全部披露见 §5）。

按 M1 自动化授权与 2026-08-20 人工指令协议，G2 关闭，**进入 Phase 3 — Scheduler / Time / Action**（计划 §12）。
