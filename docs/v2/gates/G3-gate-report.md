# G3 Gate Report — Phase 3 Scheduler / Time / Action（终版）

按 `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` §12、§21、§25 编制。
G3-R2 盲审（`1279e51` 审查点）4/4 通过/投机通过后，Leader 另执行两个文档级留痕清零提交（`b21f266`、`8814225`，零断言零行为变更，按 2026-08-20 协议文档级修复不消耗补充预算、不触发复审）；本报告为 G3 最终交付点记录。

---

## 0. 基础信息

- **Gate**: G3（Phase 3 — Scheduler / Time / Action 门禁）
- **Commit SHA**: `8814225`（HEAD，Phase 3 最终交付点）
- **分支**: `architecture-v2`
- **审查基准**: `4556c83`（P3-DESIGN）.. `1279e51`（G3 补充轮1，G3-R2 审查点）；G3-R1 审查点 `9b25359`（Wave F）；P1 冻结基线 `603535e`，P2 冻结点 `f49ecd5`（G2 PASS）
- **测试基线**: 全量 **2228 passed**（`tests/engine_v2` 子集 1777 passed；新增 737 测试 = 2228 − 1491 G2 基线）；`ruff check src/engine_v2 tests/engine_v2` → `All checks passed!`
- **审查执行**: 全部 `qiyuan-self / qwen3.8-27b`（2026-08-20 人工路由覆盖，见 `docs/plans/model-routing-providers.md`）；设计阶段 6 轮盲审（R2~R7，4 名/轮）+ 门禁阶段 **2 轮 × 4 名独立盲审（G3-R1 + G3-R2，全新一轮全新盲）**，四裁决协议（通过/投机通过/补充内容/阻塞）

---

## 1. §21 字段

```text
Gate: G3
Commit SHA: 8814225
Tasks completed: P3-DESIGN（R7 收尾轮关闭，E-P3-01~39 勘误链），
                 P3-T01 ~ P3-T08（全部；T04 = T04a+T04a2+T04b，T07 = T07+T07-wire），
                 + G3 补充轮1（G3 扩展判据三条错误路径 Gate 语境化 + 设计勘误 E-P3-41~43）
Tasks waived: 无
Tests: 2228 passed（真实输出，.venv python，-p no:cacheprovider）；tests/engine_v2 1777 passed
Known failures: 0（v1 基线的 30 项 ruff 已知失败属 v1 冻结代码，不在 engine_v2 门禁范围）
Architecture deviations: 见 §5 偏差登记（全部已披露/已登记，无未声明偏差）
Open risks: 见 §6 风险登记册（全部为已声明级别残留，低/极低）
Human review required: 否（M1 自动化授权范围内；G3 实质补充轮 1/3 在预算内，按 2026-08-20 协议无需人工批准）
Decision: PASS
```

**通过口径**（2026-08-20 人工指令协议，同 G2）：最终轮（G3-R2）4/4 盲审给出 通过/投机通过，无补充内容、无阻塞、无执行失败。

---

## 2. 门禁判据验证

### A. 设计 §6.2 G3 五条（与 Plan §12 G3 五条一一对应，映射明细见设计 §7）

| # | 判据（原文） | 证据 |
|---|---|---|
| G3-1 | 场景精确通过 | `test_gate_scenario_travel_interrupt`：30-min travel、t=12 encounter 暂停，**恰 17 条编号断言**（9 暂停点 S0-S8 + 分支 A resume 4 + 分支 B abort 4，E-P3-04/D-P3-19 计数口径 9+4+4=17）；全部精确值断言（`==`/`is`/列表恒等，全文件无近似容差）；G3-R2 盲审独立核验文档 17 条列举 ↔ 测试 17 条标记取值/对象全量双射（编号序差异为标注层面，逐条可回指） |
| G3-2 | scheduler queue 可 serialize | `test_queue_serialization`：RuntimeState JSON 往返（`dump_json` → `assert_json_clean` → `load_json`）后队列/active_actions/actor_wakeups/logical_tick 逐项恒等（entry_id 保 `sch_` 前缀）、往返后 resume+ff 续跑事件键序列与独立深拷贝路径恒同；单元层 = `test_event_queue.py` 逐 kind 缺必填键矩阵 + round-trip 恒等（G3-2 单元口径） |
| G3-3 | interruption 后 progress 正确 | `test_progress_across_interrupt`：暂停点 `progress == 12/30` 精确；resume checkpoint 序列 `0.4 → 0.6667 → 1.0` 单调；abort 分支 `result_summary["progress"] == 0.4` 且终态记录保留；snapshot round-trip 后 progress 重算恒等（不依赖存储值，E-P3-28 镜像口径：COMPLETED 存储镜像停于最后 checkpoint 值，运行时权威值恒为 `progress_of` 派生，D-P3-08） |
| G3-4 | replay event order 一致 | `test_replay_determinism`：(a) 同一 snapshot 两次 restore 续跑事件键序列 + tick 水位恒等（E1==E2==E3）；(b) snapshot 路径 vs 无 snapshot 深拷贝路径事件键恒同；(c) `apply_committed_effects`（reducer.py:843）事务回放 == 实际世界；(d) 指纹三探针（registry/time_policy/boundaries 各篡改一字段 → 失配）+ 同输入恒等——回放拒绝 = 测试层指纹失配检查（引擎不静默回放，D-P3-15①/D-P3-20） |
| G3-5 | no LLM required | `test_import_boundary.py` P3 段机械核验：B1 静态（`P3_SUBMODULES` 7 模块非确定性根谓词 `datetime`/`time`/`random`/`asyncio` + provider/llm 名称黑名单，按模块分流作用域——3 个 P1 冻结模块的诊断性 `datetime` 属预期带入不判违规，§6.4/D4 预披露）+ `P3_TEST_FILES` 10 个新增测试文件（9 个 `test_*.py` + `conftest.py`）逐文件全谓词核验；G3-R2 独立 grep 复验绝对 import 面（仅 stdlib/pydantic/pytest/core 既有模块，零 openai/anthropic/网络）；Gate 场景全程零网络、零 LLM、零 API key |

### B. 扩展门禁判据（G3 门禁简报，超出五条）

**三条错误路径 Gate 语境化**（单元级锚点 = 设计 §6.3 A2/A5 + §3.6 迁移矩阵；G3-R1 RB SUPPLEMENT-1 驱动补全）：

| 错误路径 | 测试 | 关键断言 |
|---|---|---|
| invalid spec | `test_invalid_spec_gate_context` | fixture 无关的校验层探针（extra=forbid / 缺必填 / 注册表键一致性，`model_validate` 构造期拒绝，K7 可检查不静默）——非法 spec 属参数 schema 校验，不涉世界/队列/时钟，故不装配 Gate 场景；单元级全矩阵另见 `test_action_registry.py` |
| unknown action | `test_unknown_action_gate_context` | `flying` 未注册 → `UnknownActionError` 于 registry 查找点抛出、被 `submit_proposal` 捕获转 FAILED 轨迹（reason=unknown_action、**无 PROPOSED 记录**、E-P3-39⑧ 次序：registry 查找先于 revalidate、REJECT 轨迹不查迁移表）+ F2-12 `pending_proposals` 簿记 + 诊断串含 action_id + 队列零残留 + 世界零副作用；错误后 Gate 时间线照常续跑（t12 暂停、progress==12/30，与主场景同值） |
| IllegalTransition | `test_illegal_transition_gate_context` | 复用 S8 暂停点：表外探针 INTERRUPTED→INTERRUPTED 双中断（对照 `LIFECYCLE_TRANSITIONS` 唯一权威：INTERRUPTED 行仅 RESUMED/ABORTED 出边）→ `IllegalTransitionError`（消息含 from/to/event）；错误后 `fast_forward` = D-P3-24 入口首检幂等重报（四清单全空 + tick 水位不前进 + 队列不变 `[cp@20, end@30]` + 世界零副作用）；终态侧（abort 后 resume）亦 IllegalTransitionError——与 `test_scheduler.py` ACTIVE 探针互补的 Gate 全装配角度 |

**§5.5 三条"不得"（M1-M3）**：`test_m1_background_blinks_no_pause`（200 背景 blink 不干扰 Gate 暂停；暂停前 NPC blink 恰 12 条 COMPLETED 迁移，设计口径 ≥12 的严格子集，推导留痕）/ `test_m2_position_commit_isolation`（position 仅在 txn_2 提交点变 dest + 授权/校验/提交 trace 三口 + 伪造 progress 探针）/ `test_m3_purity_and_serialization`（双拷贝 outcome 逐项恒等 + snapshot/restore 续跑恒等 + RuntimeState 全字段 JSON-clean）。

**§6.3 八类对抗 A1-A8（19 探针）**：`test_p3_adversarial.py` 逐字落地——A1 stale/过期优先（F2-05：valid_until_expired 先于 stale_revision）；A2 非法迁移矩阵（4 探针 + 合法再中断对照 + NPC 非阻塞中断收敛 D-P3-25）；A3 同刻 FIFO + 批内派生 D 尾部（D-P3-05）；A4 回放 E1 后缀==E2==E3 + uuid4 4 方同构（D-P3-15①/D-P3-20：数量/唯一性/前缀/位置，不跨运行比原值）；A5 unknown_action 轨迹；A6 PROPOSED 直调 + extra=forbid；A7 幂等重报 + abort 失效 + 终态幂等；A8 时钟回退 + 队列四不变量 5 探针 + 同刻入队。

### C. P1/P2 冻结与导出台账（机械核验）

- **P1 13 契约模块**与 `603535e` 逐字节一致（Leader `git diff` 逐一验证；E-P3-43 冻结核验口径：P3 跨度 19 个既有 core 文件 = 13 P1 契约 + 6 P2 行为模块，零差异）；
- **P2 6 行为模块**（authority/cascade/conflicts/reducer/transaction_executor/validation）与 `f49ecd5`（G2 点）逐字节一致；
- `core/__init__.py` **纯增量 +127 行、零删**：196 基线 → **249**（= 196 + 53），196 成员保序子序列（53 项按 casefold 插入位，零违例；保序事实依赖 Leader git-diff，见 §6 R7），53 项与 26 个子模块名零撞名；P3 每模块导出终态（D6 后）：clock 6 / event_queue 5 / action_registry 7 / action_lifecycle 11 / interrupt 10 / revalidation 3 / scheduler 11；
- `test_closeout.py` 249 规模锚 + 文件集锚点 26（`CORE_SUBMODULES` 19→22→23→24→25→26 逐波机械同步）在位并通过；G3-R2 RC 独立重验 249 = 196 + 53 台账与包级 `__all__` == 26 子模块 `__all__` 之并集减 `{snapshot}`。

---

## 3. 任务完成情况（Tasks completed）

| 任务 | 提交 | 交付 |
|---|---|---|
| P3-DESIGN | `4556c83` | `docs/v2/contracts/P3-scheduler-time-action-design.md`（7 新模块、27 决策 D-P3-01~27、§5 Gate 场景、§6 测试规格、§7 映射表、§8 自检；设计盲审 R2~R7 六轮修复 64 项 → 勘误 E-P3-01~39，R7 收尾轮关闭；全裁决链记录于该提交正文） |
| P3-T01+T02（Wave A） | `c4f7184` | `clock.py`（6 导出：LogicalClock 唯一时钟写点，1 tick ≙ 1 世界分钟）+ `event_queue.py`（5 导出：kind 词表 + payload 契约、写时稳定排序、同刻批抽取）+ `action_registry.py`（7 导出：ActionSpec/ParameterSpec/DurationPolicy/ActionRegistry、参数 schema 校验、duration 解析）；193 新测试，全量 1684 |
| P3-T03（Wave B） | `bf06366` | `action_lifecycle.py` 上半（状态机）：LifecycleEvent / LIFECYCLE_TRANSITIONS（九边，INTERRUPTED 仅 RESUMED/ABORTED 出边，终态无边）/ `transition_action` 表驱动 + IllegalTransitionError（from/to/event）+ INTERRUPTED/RESUMED re-anchor + progress 镜像更新 + 终态队列剪除（INTERRUPTED 永不剪）；108 新测试，全量 1792 |
| P3-T04（Wave C：T04a+T04a2+T04b） | `ddbce35` | `action_lifecycle.py` 下半（progress_of/resume/abort/complete/fail + apply_checkpoint，E-P3-40 间隔通道）+ `scheduler.py` 核心（§3.8 门面 / §2.4 主循环 / §3.9 revalidation 接线占位，10 导出）+ E-P3-40 勘误；全量 1937。（T04b 前 3 次执行失败经人工裁定不计失败次数——2 次上下文压缩故障 + 1 次人工停止——全新预算 1 次执行即成功） |
| P3-T05（Wave D） | `7a57094` | `interrupt.py` 全量（4 内置 kind 纯求值 / DecisionBoundary 互斥必填 / UnknownConditionError / BUILTIN 缺省实例）+ scheduler 刻后边界求值接线（pause_on_player_boundary 两路：暂停 / record-only，E-P3-36；D-P3-24 自洽）；全量 2015 |
| P3-T06+T07+T07-wire+集成（Wave E） | `7807896` | scheduler wakeup 排空接线（D-P3-14 同步纯钩子 / 无钩子 SYSTEM 诊断 / 钩子异常 → SchedulerWakeupError 整 tick 原子回滚 / E-P3-35 双记录：actor_wakeups + kind="wakeup" 队列条目，同刻序 = 队列序）+ `revalidation.py` 新模块（§3.9 五步序 / F2-05 REJECT 优先级 valid_until_expired 先于 stale_revision / E-P3-26 不产 REPAIR / D-12 revision 诊断 details-only / rebase_proposal 纯变换 / is_stale 单源复用 revision.py）+ T07-wire 占位替换（`revalidate_proposal` 真接线，零断言变更）+ `core/__init__` D-P3-12 集成（7 模块 53 导出、196 保序子序列、`__all__` 249、文件集锚点 25→26）+ start_action 台账校正（偏差 D6，E-P3-41）；全量 2197 |
| P3-T08（Wave F） | `9b25359` | `conftest.py`（`tests/engine_v2/core/` 首建，§5.1 fixture 工厂：R0 / travel spec / 双幂等 named trigger stub / 空 trigger_registry 单路化 D-P3-27 / origin=E-P3-34 / scheduled 边界 @12 玩家阻塞）+ `test_p3_gate_scenario.py`（8 测试：G3-1 恰 17 条编号断言 + M1-M3 + G3-4 回放 + 错误路径）+ `test_p3_adversarial.py`（19 测试 A1-A8）+ `test_import_boundary.py` P3 扩展（P3_SUBMODULES 7 + P3_TEST_FILES 10，§6.4/D4 预披露）；全量 2226，src/ 零改动 |
| G3 补充轮1 | `1279e51` | RB SUPPLEMENT-1：三条错误路径 Gate 语境化（新增 `test_unknown_action_gate_context` + `test_illegal_transition_gate_context`；`test_invalid_spec_gate_context` 保留为 fixture 无关探针）+ 既有 17 条 G3-1 / M1-M3 / 回放断言零改动 + `test_p3_adversarial` D-P3-15②→①/D-P3-20 引用更正 3 处（零断言）+ 设计勘误 E-P3-41（D6 留痕 + §3.2 依赖图边校正）/ E-P3-42（§3.6 fail_action REJECT 轨迹不查迁移表澄清，RA-D1）/ E-P3-43（冻结核验口径 13→19 文件澄清）；全量 2228 |
| G3 R2 文档级清零 | `b21f266` | 4 处文档级修订：event_queue 队列有序性"三"→"四"条不变量（标题与条目数对齐）+ test_p3_gate_scenario M2(b) 注释 D-P3-15②→①/D-P3-20（RD-DOC-1）+ scheduler 模块 docstring 导出计数 10→11 并补 start_action（D6/E-P3-41 后陈旧计数）+ scheduler TYPE_CHECKING 注释措辞精确化；零断言零行为变更，全量 2228 |
| G3 R2 残留 DOC-1 清零 | `8814225` | `test_p3_gate_scenario.py` 7 处幻影引用更正：『§6.2 G3-3 "在 Gate 场景内复现"口径』（该措辞在设计 §6.2 G3-3 行与 Plan §12 G3 五条中均不存在）→ 三条错误路径 = G3 门禁简报扩展核验项，单元级锚点 = 设计 §6.3 A2/A5 + §3.6 迁移矩阵（模块 docstring / 分节注释 / 3 个错误路径测试 docstring）；零断言零行为变更，全量 2228 |

**Tasks waived: 无。**

---

## 4. 审查历史（对抗式独立盲审，全部 qiyuan-self / qwen3.8-27b）

### A. 设计阶段（P3-DESIGN，裁决链记录于 `4556c83` 提交正文与设计 §9 勘误逐条留痕）

| 轮次 | 裁决（finding 级） | 关键发现 | 处置 |
|---|---|---|---|
| R1 | delivery-degraded（执行降级） | — | 重跑为 R2 |
| R2（4×盲审） | 2 BLOCK + 14 SUPP（`4556c83` 提交正文口径） | BLOCK-1：§5.1 fixture C1 中断条件 `kind="event_kind"`/encounter 触发器口径与 Plan §12 核心 Gate 场景 + Spec §48 Scenario D 冲突（F-01：`event_kind` 虚构字段，P1 冻结 `DomainEvent` 无此字段）；BLOCK-2：§3.8 `SchedulerOutcome` 草图缺事件列表/trace 承载面，无法支持 Plan §12 G3 "replay event order 一致"（G3-4 判据①逐事件键序列）；SUPP 要点：四处宣称 "logical_tick=t 透传打戳" 与 P2 D-P2-18 矛盾（P2 不拥有时钟）/ ActiveAction 字段数 16 vs 实读 14 / P3 专项黑名单作用域机制两处互斥描述 / S8 transitions 聚合口径 / G3-1 计数口径 | 人工裁定：BLOCK 按第一轮修复处理 → 合并清单 F-01~F-15 → **E-P3-01~10**（E-P3-01 = event_kind→event_type，D-P3-17；E-P3-10 = 事实性引用与措辞批量勘误） |
| R3（4×盲审，全新盲） | 4× SUPP | F2-01~F2-16：named_triggers 数据来源 / run guard 因果链 / outcome 按调用聚合口径 / start_action 两跳 2 记录断言面 / D-P3-11 打戳矛盾等 | **E-P3-11~23**（含 D-P3-17~25 规则层补全：F2-05 REJECT 优先级、F2-06 R1 回归断言时刻前置、D-P3-24 幂等重报、D-P3-25 NPC 非阻塞收敛） |
| R4（4×盲审，全新盲） | 1× 通过 + 3× SUPP | F3-01~F3-06 + L3-01~L3-07 | **E-P3-24~29**（**D-P3-26** `named_triggers` 必填构造参数 + §5.1 stub 幂等守卫机制） |
| R5（4×盲审，全新盲） | 2× SUPP + 2× 投机通过 | F4-01~F4-03 + L4-01 | **E-P3-30~32**（**D-P3-27** Gate fixture 单路化：trigger_registry 显式空注册表；F4-02 D-P3-24 重报保证限定 INTERRUPTED 期间；F4-03 `pause_on_player_boundary=False` = record-only） |
| R6（4×盲审，全新盲） | 2× 通过 + 1× 投机通过 + 1× SUPP | F5-01~F5-03 + L5-01 | **E-P3-33~36**（F5-01 run()-级 origin `OriginKind.SCENARIO`、E-P3-34；F5-02 wakeup 双记录口径、E-P3-35；F5-03 `pause_on_player_boundary=False` 重裁 record-only、E-P3-36（重裁 E-P3-32① 中断部分，留痕）；L5-01 引用区间就地更正、E-P3-33） |
| R7（4×盲审，收尾轮） | 1× 通过 + 3× SUPP（**全部文档级**） | F7-01~F7-06 + R7-01~R7-05 | **E-P3-37~39**（D-P3-20 工厂区间就地更正取代 E-P3-21/E-P3-33 该处裁定；F2-15 `causal_root_id` docstring 偏离披露；九项文档级口径——S8 transitions 承诺 / Spec §23.2 锚点 / `scheduler_fingerprint` 签名与输入面 / `BUILTIN_CONDITION_RESOLVERS` 缺省注记 / `wakeup_hooks` 缺省 / 门面返回类型 / `kind="event"` payload 互斥 / `submit_proposal` 次序 / `cause_ids` 引用区间）——**设计关闭** |

> 备注：① 六轮修复共 **64 项** finding 全部落入勘误链 E-P3-01~39（设计 §9 逐条留痕，每条含内容与原因 + 盲审出处槽位-项号）。② 按 2026-08-20 人工门禁策略：文档级修复不消耗实质补充预算——设计阶段**实质补充轮使用 0/3**（R2 的 BLOCK 经人工裁定按第一轮修复处理，其内容全部为文档勘误）。③ R7 收尾轮 3× SUPP 均为文档级口径澄清/就地更正，Leader 核验修复后关闭设计阶段。④ R2 起各轮完整裁决文本经 `.review-drafts/` 持久化（本 Gate 报告提交后随 P3 收尾删除）；R1 delivery-degraded 无裁决留痕。

### B. 实现门禁 G3（本 Gate）

| 轮次 | 审查点 | 裁决 | 关键发现 | 处置 |
|---|---|---|---|---|
| G3-R1（4×盲审，全新一轮） | `9b25359`（Wave F，2226） | 4× 通过（0× 阻塞） | **SUPPLEMENT-1（RB 维度，Gate 场景保真）**：三条错误路径 Gate 语境覆盖不足——当时仅 invalid spec 在 Gate 语境（含 flying 探针），unknown action / IllegalTransition 仅模块级覆盖、无 Gate 全装配语境；另 2× DOC 级（RA：设计 §3.6 fail_action 注记"经 VALIDATION_REJECTED 边"字面可误读为 REJECT 轨迹需遍历迁移表；RD：D-P3-15② 引文归属偏差 ×3 处，应为 D-P3-15①/D-P3-20） | **补充轮1** `1279e51`（**实质 1/3**）：G3-S1 新增 2 个 Gate 语境测试 + invalid-spec 探针定位留痕 + 3 处引用更正；RA-D1 由 Leader 同轮修复 → E-P3-42；E-P3-41（D6 留痕）/E-P3-43（冻结口径）同轮落定 |
| **G3-R2（4×盲审，全新一轮，最终）** | `1279e51`（2228） | **4/4 通过/投机通过**（RA 通过 / RB 投机通过 / RC 投机通过 / RD 通过；**0× 补充、0× 阻塞、0× 执行失败**） | 残留全为 INFO/DOC 级：1× DOC（测试 docstring 幻影引用『§6.2 G3-3 "在 Gate 场景内复现"口径』——该措辞在设计 §6.2 G3-3 行与 Plan §12 G3 五条中均不存在，全库 grep 仅测试文件自身命中；三条错误路径覆盖本身真实通过）+ INFO 系列（apply_checkpoint 防御分支、skip_boundary_ids 存活守卫、原子刻错误路径状态对构成、scheduler_fingerprint callable 面排除、K 编号引文错位、P2 既有 ValidationError 同名、__all__ 保序可复算性、A1/A3 测试构造变体——逐项见 §6 风险登记册） | DOC-1 由 Leader R2 后修复（`8814225`，7 处 docstring/注释更正，零行为，按协议文档级不触发复审）；INFO 系列 → §6 风险登记册 |

**G3 关闭**：最终轮 4/4 通过/投机通过、0 补充、0 阻塞、0 执行失败——2026-08-20 协议满足。实质补充轮使用 **1/3**（预算内，未触发人工批准）。

> 备注：两轮 8 份盲审完整裁决 JSON 持久化于 `.review-drafts/g3-blind-{RA,RC,RD}.json` / `g3r2-blind-{RA,RB,RC,RD}.json`（RB-R1 补充需求见该轮工作流聚合输出；本 Gate 报告提交后随 P3 收尾删除）。全量套件由 RD 两轮各复跑 2 次（2226×2 → 2228×2，RC=0），复现性独立确认。

---

## 5. 偏差登记（Architecture deviations，全部已披露）

| # | 偏差 | 状态 |
|---|---|---|
| D1 | 任务书预期"ScheduledEvent 新类型"；P1 已冻结 `ScheduledEvent`（state.py:143）→ 采用 D-P3-04 复用方案（澄清性偏差，P1 零改动为最高约束） | 已披露（设计 §8.5） |
| D2 | Spec §11.4"建议"状态机无 INTERRUPTED→ACTIVE 返回边，Plan §12 Gate 要求 resume → 新增 RESUMED 边（D-P3-07；Plan Gate 效力高于 Spec"建议"级） | 已披露（设计 §8.5 + D-P3-07 留痕） |
| D3 | 子 tick 动作钳制为 1 tick + 诊断（Spec 未规定亚 tick 处置；全冻结字段 int tick 无亚 tick 表达位） | 已披露（设计 §8.5，M1 fixture 恰用此规则） |
| D4 | `test_import_boundary.py` 结构性修订：P3 专项黑名单按模块分流作用域（`P3_SUBMODULES` 7 + 全谓词 `P3_TEST_FILES` 10），B1/B2 原三类全局谓词不变（多行、预披露，非一行级） | 已披露（设计 §8.5 + §6.4，P3-T08 白名单内执行） |
| D5 | `test_closeout.py` 196 规模锚点 → 249（一行级机械同步含注释块；R3 盲审补录 E-P3-17） | 已披露（设计 §8.5，T01 白名单内执行） |
| D6 | `start_action` 设计 §3.6 规定落于 `action_lifecycle.py`（该模块 12 导出 / scheduler 10），实现（依先前 Leader 裁定，scheduler.py:452 注释留痕）落位 `scheduler.py:465`；Wave E 集成暴露 T04a 遗留 `__all__` 幻影占位（`# noqa: F822`）→ 21 项收集错误；台账对齐（最小变更）：action_lifecycle 11 / scheduler 11，249 集合不变、零撞名、196 保序子序列不变 | 已披露（代码注释 + E-P3-41 + 本表）；G3-R1 RA 独立复验 API 面 6/5/7/11/10/3/11=53 |
| D7 | Wave E 三段拆分（T06/T07/T07-wire）：原任务包 T06（wakeup 排空）与 T07（revalidation 模块 + 接线）共享 scheduler.py 写面，按写入白名单串行纪律拆分；T07-wire 替换 T04b 的 revalidation 接线占位（零断言变更） | 已披露（`7807896` 提交正文；Leader 波次计划） |
| D8 | `core/__init__.py` 集成 Leader 化（D-P3-12 逐波机械同步：CORE_SUBMODULES 19→22→23→24→25→26、导出锚 196→249）；保序约定 = 196 基线序仅可经 git 历史复现（RA-R2 留痕），53 项按 casefold 插入位 | 已披露（各波次提交正文；§6 R7） |
| D9 | T04b 前 3 次执行失败（2 次上下文压缩故障 + 1 次人工停止）经人工裁定**不计入失败次数**；全新预算 1 次执行即成功（dev 任务 ≤3 次执行协议） | 人工裁定（2026-08-29）留痕 |
| D10 | E-P3-40（实现期 Leader 裁定两项）：`apply_checkpoint` 增关键字 `checkpoint_interval: int \| None = None`（间隔通道，None → 不入队下一 checkpoint）+ `Scheduler.__init__` 增必填 `origin: Provenance`（E-P3-34/F5-01 漏列参数补齐）——实现期暴露的契约缝隙，零源码语义改动、零断言改动 | 已披露（E-P3-40） |
| D11 | T06 2 处 stub-era 断言随真实接线同提交更新 + T07-wire 3 处注释同步（零行为变更） | 已披露（`7807896` 提交正文） |
| D12 | R2 后两个文档级提交（`b21f266` + `8814225`）：全 docstring/注释，零断言零行为，按 2026-08-20 协议文档级修复不消耗预算、不触发复审 | 已披露（§4-B G3-R2 行） |

---

## 6. 风险登记册（Open risks — G3-R1/R2 已核实风险项并集，供后续 bug 排查参考）

按 2026-08-20 人工指令协议：SPECULATIVE_PASS 的门禁与风险点记录在案，供后续排查参考。

| # | 风险 | 严重度 | 可控性论证 | 后续排查/加固（责任阶段） |
|---|---|---|---|---|
| R1 | `apply_checkpoint`（action_lifecycle.py:580）对 PROPOSED/VALIDATING + checkpoint 条目另抛 `IllegalTransitionError`，比文档字面（仅点名 INTERRUPTED/终态两跳过族 → SYSTEM 诊断）更严 | 极低（防御性分支） | RA-R2 逐行核对：scheduler 仅对 ACTIVE 实例入队 checkpoint（start_action），该分支正常流不可达 = 防御性不变量断言，符合 D-P3-16 可检查不静默；文档点名的两跳过族诊断均已实现 | P4：保留分支；若扩展 checkpoint 语义，同步文档措辞 |
| R2 | `_maybe_evaluate_boundaries` 的 `skip_boundary_ids` 存活守卫（同 tick 已触发边界去重，防重评估再触发）为超出 §2.4 伪代码字面的实现级补充 | 低（实现级补充，行为确定） | 依据 = §2.4 边界情形注记（L208：同 tick 新条目追加至批尾）；注册序求值 + player_blocking 判定 + E-P3-36 record-only 语义均逐行核对未变，守卫仅防同刻重复触发 | P4：新增多边界场景时知悉同刻去重语义 |
| R3 | 原子刻错误路径的"刻前状态对"捕获点在 `take_due` 已抽走 due 批之后（scheduler.py:1290→1327）：返回 runtime 队列不含失败批条目；wakeup hook 抛错时 `actor_wakeups` 记录未移除（移除代码在 hook 调用后不可达）→"记录在、条目失"惰性残留 | 低（已登记） | §2.4 论证 5 仅钉死"返回刻前状态对 + 部分提交不可见"，未钉死返回对的队列/actor_wakeups 构成；世界零副作用 + revision 不变 + 幂等重报（D-P3-24/A7）已实测钉死，残留为进程内簿记、不暴露于世界/trace | P4：若钉死错误路径返回值构成，增勘误并同步测试 |
| R4 | `scheduler_fingerprint` 排除 4 个 callable 配置面（named_triggers / trigger_registry / wakeup_hooks / condition_resolvers，E-P3-39③）：未来仅改这些面时指纹不变 | 低（已披露设计边界） | 设计 E-P3-39③ + 代码 docstring 双重留痕；指纹失配 = 测试层回放拒绝（引擎不静默回放），G3-4 回放判据按同装配口径构造，callable 面不入可序列化指纹为设计选择 | P4/P5：接入真实 trigger/hook 策略时扩展指纹输入面或在测试层显式披露 |
| R5 | 门禁简报 K 编号引文与 Spec §4 原文错位（简报"K5"=revision 单调 / "K8"=事件溯源，Spec 真正 K5=Agent-is-Policy-not-Engine / K8=部署/项目分离） | 极低（文档卫生） | RC-R2 按 Spec 原文逐一独立核验全部被引属性均成立（is_stale 唯一定义于 revision.py:78 且 revalidation.py:53 导入复用非重定义；溯源 origin 必填 + causal_root_id 接线 cascade.py:867-913 强制；K1 无事件存储字段于 WorldState/RuntimeState），无代码影响 | 后续门禁简报统一引用 Spec §4 原文编号 |
| R6 | 既有 P2 跨模块同名：validation.py:238 项目类 `ValidationError(ValueError)` 与 reducer.py:82 引入的 pydantic `ValidationError` 同名，包级 `core.ValidationError` 解析为前者 | 低（P2 既有，双文件字节冻结） | 非 P3 增量；P3 代码与测试均用具体模块引用；closeout 仅钉集合级相等，不影响 P3 判定 | P8：统一包导入方案时评估消歧（同 G2 风险 R7 打包陷阱族） |
| R7 | `__all__` "既有 196 条保序子序列"性质在无 git 历史时不可独立复算（审查协议禁 git）：集合级纯度已全验（249 = 196 + 53、逐模块 6/5/7/11/10/3/11 与 E-P3-41 吻合、零撞名、包级 `__all__` == 26 子模块并集减 {snapshot}），但基线排序无法以任何简单排序键复现 | 极低（可复算性边界） | 保序事实依赖 Leader git-diff 核验（196 零删零改）；closeout 249 锚点每轮机械复核；53 项插入位 casefold 规则已固化于 `__init__.py` 约定 | P8：考虑从 git 基线生成保序校验脚本 |
| R8 | P1 `events.py:141` 诊断性 `wall_time`（datetime，P1 设计决策 D-14）预期带入、不在 P3 专项边界内 | 极低（P1 已登记） | P1 字节冻结；7 个 P3 模块 + 10 个 P3 测试文件独立 AST 扫描零 datetime/time/random/asyncio/provider/网络导入（248 条绝对导入核验）；B1/B2 双扫描 + G3-5 机械口径在位 | 无需动作（P8 打包统一时评估） |
| R9 | A1/A3 测试构造变体（A1：5 条显式 `kind="event"` create_entity 条目 + t=1 B1 玩家 blocking 暂停副作用，动机 = D-P2-10 同刻多提交 base 预声明口径；A3：D 条目落为同刻尾部 wakeup 条目而非原文"新 due_tick=5 条目"，wakeup_no_hook 唯一诊断位于全部 DOMAIN_EVENT trace 之后） | 极低（测试构造，已披露） | RD-R2 逐字核对：与 §2.4 边界情形（L208）一致、D-P3-05 稳定 FIFO 断言保持；所有钉死断言保留，docstring L7-14 留痕 | 无需动作（保留 docstring 留痕） |

---

## 7. 移交 P4 的接口与约束（Handoff Notes）

1. **REPAIR 扩展（E-P3-26）**：P3 revalidation 结果域 = ACCEPT/REBASE/REJECT，**REPAIR 从不产生**（P3 测试不得把结果域钉死为三值集合当词表不变量）；REPAIR 分支的 actor 重提案策略是 P4 域。
2. **`scheduler_fingerprint` 输入面（E-P3-39③）**：4 个 callable 配置面被排除在指纹外；P4/P5 接入真实 trigger/hook 策略时必须扩展指纹输入面或在测试层显式披露（见 §6 R4）。
3. **WakeupHook Protocol 接缝（D-P3-14）**：P3 提供同步纯钩子协议 + 无钩子 SYSTEM 诊断 + 钩子异常 → `SchedulerWakeupError` 整 tick 原子回滚；真实 wakeup 重提案策略（含 NPC 非阻塞中断后的再提案）是 P4/P5 域。
4. **NPC 非阻塞中断收敛（D-P3-25）**：NPC 边界 `interrupt=True` 命中 → 行动迁 INTERRUPTED 不暂停，其后 checkpoint 刻跳过（`checkpoint_skipped_interrupted` 诊断）；P3 不提供自动收敛——收敛 = P4/P5 wakeup 重提案或外部 abort（设计使然，非缺陷）。
5. **named_triggers 生产注册表（D-P3-26/27）**：P3 Gate fixture = 幂等 stub + 显式空 `trigger_registry` 单路化；生产命名触发器装配（scenario 触发器接线）是 P5 域。
6. **RESUMED 边（D-P3-07）**：边已实现并测试（Gate 分支 A resume 路径、A2 合法再中断对照）；生产触发路径（中断后 actor 重提案）是 P4/P5 域。
7. **P1 字段未触碰面**：`RuntimeState` 的 `active_modes` / `mode_context` / `backend_refs` / `rng_state` 在 P3 保持未触碰 = P4/P5/P8 域。
8. **冻结与台账沿用**：19 个既有 core 文件（13 P1 契约 + 6 P2 行为模块）P3 点冻结（基线 `603535e` / `f49ecd5`），P4 不得触碰；`__all__` 249 纯增量扩展（P4 新模块按 D-P3-12 同模式机械同步：CORE_SUBMODULES 26→…、closeout 锚点 249→…）；G2 移交 2 的每轮重新 guard 语义（guard() 时刻深冻结快照、跨 commit 不反映新状态）对 P4 producer/trigger/actor 继续适用（见 §6 R1/R2 相关注记）。
9. **G0 遗留（非阻塞，沿用 G2 报告 §7-6）**：T04 真实 LLM 转录 + v1 boot proof 待 API key，与 P4 无依赖。
10. **G4 门禁参照（Plan §13）**：Alice 不知道她没有 Observation/Knowledge 的 Bob 偷窃事件 / 自定义 Policy 不能因更换 Prompt 获得 global read / 一个 Entity 可拥有 overworld + tactical 映射 / Dialogue + Tactical 可同时 active / TimePolicy 冲突有明确 winner / mode change 不复制 WorldState——P4 设计应逐条回应（先例：P3 设计 §1.2 对 Plan §12 三条"不得"的逐条回应体例）。

---

## 8. 决策

**Decision: PASS**（G3-R2 最终轮 4/4 独立盲审 通过/投机通过，0 补充、0 阻塞、0 执行失败；实质补充轮 1/3 预算内闭合；风险登记册见 §6；偏差全部披露见 §5）。

按 M1 自动化授权与 2026-08-20 人工指令协议，G3 关闭，**进入 Phase 4 — Actor / Context / Space / GameplayMode**（计划 §13）。
