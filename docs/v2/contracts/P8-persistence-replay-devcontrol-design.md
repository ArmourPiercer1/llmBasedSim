# P8 Persistence / Replay / Development Control Plane — W0 设计 SOT

| 项 | 值 |
|---|---|
| 阶段 | Phase 8（Plan §17 L727–757） |
| 基线 commit | `84a5d4f`（G7 收口；P7 最终交付 `ea84d00`） |
| 分支 | `architecture-v2` |
| 本文件角色 | P8 唯一设计 SOT（Single Source of Truth）；实现波次（W1–W5）以其为唯一依据 |
| 结构口径 | 逐节镜像 `docs/v2/contracts/P7-world-dynamics-design.md`（HEAD 1696 行） |
| 允许写盘 | 仅 §3.10 闭集白名单（25 文件）+ 本文件 + `.review-drafts/` 报告；W0 阶段零代码/测试/ git 写操作 |
| 任务书 | `.p8/w0-brief.md`（200 行；与本文件冲突处以本文件为准并登记 §8.4 / §9） |

> **字节真值优先**：本文件所有 `file:line` 锚点均在 `84a5d4f` 工作树逐字节核验
> （`sed -n` / `awk 'NR>=X&&NR<=Y'` / AST 解析）。任务书与本文件的出入（OriginKind
> 值数、§37 归属、monotonic clock 归属）以本文件为准，登记于 §9 勘误预备区。

---

## §0 定位与基线

### 0.1 范围（Plan §17 任务表 L735–745 逐项对齐 + P8 落位映射（能力列省略））

| ID | 任务 | 属性 | 难度 | 上下文 | 默认模型 | P8 落位（本 SOT §3） |
|---|---|---|---|---|---|---|
| P8-T01 | snapshot format / version metadata | 开发 | 较高难度 | 1M | QMax | `persistence/base.py`（部分）+ `persistence/snapshot.py` |
| P8-T02 | filesystem PersistenceBackend reference | 开发 | 少量思考 | 256K | Q27 | `persistence/filesystem.py` |
| P8-T03 | event-level replay engine | 开发 | 较高难度 | 1M | QMax | `persistence/replay.py` |
| P8-T04 | BackendCheckpoint registry / restore | 开发 | 较高难度 | 1M | QMax | `persistence/checkpoint.py` |
| P8-T05 | branch / fork WorldInstance prototype | 开发 | 较高难度 | 1M | QMax | `persistence/branch.py` |
| P8-T06 | DevelopmentCommand / ExternalInterventionEffect | 开发 | 较高难度 | 1M | QMax | `devtools/intervention.py` |
| P8-T07 | trace query / causal chain API | 开发 | 较高难度 | 1M | QMax | `devtools/trace_query.py` |
| P8-T08 | CLI `inspect/trace/replay/branch/test --json` | 开发 | 少量思考 | 256K | Q27 | `devtools/cli.py` + `scripts/v2_devcontrol.py` |
| P8-T09 | corruption/replay/branch adversarial tests | 测试 | 较高难度 | 1M | GFlash | `tests/engine_v2/persistence/test_p8_adversarial.py` + `tests/engine_v2/devtools/test_g8_scenarios.py` |

计划目标（Plan L731 逐字）：

> 把 replay/debug 能力作为架构能力，而不是后补日志。

P8 = **`core/` 之外的纯消费方包**（S1 零核心变更）：两个已存在的占位包
（`src/engine_v2/persistence/__init__.py` 8 行、`src/engine_v2/devtools/__init__.py` 8 行，
均标注"占位，Phase 8 填充"）填充为：

- `persistence/`（T01–T05）：持久化信封格式、filesystem 参考后端、event-level replay、
  BackendCheckpoint 注册/恢复、branch/fork 原型；
- `devtools/`（T06–T08）：DevelopmentCommand/ExternalInterventionEffect、
  trace 查询/因果链 API、CLI（Spec §3.2 Development Control Plane 12 职责 L194–205
  中 W0 可机械验证的子集）。

Spec 依据：§3.2（L190–212，CLI `--json` MUST L212）、§7.2（WorldInstance L500–510）、
§8.1–8.5（WorldState/RuntimeState/BackendState 三声明/TraceState 11 记录 L611–621/
ViewState MUST NOT authoritative）、§22（DevelopmentCommand 6 例 L1254–1259 +
ExternalInterventionEffect→正常提交管道 L1265–1267 + origin=developer L1273）、
§30.1–30.5（默认模型 L1572 / 6 SHOULD 持久化内容 L1584–1590 / 5 MAY 后端 L1597–1602 /
event-level replay 最低保证 L1607–1611 / branch 3 检查 L1617–1620）、
§37（Runtime Inspector 12 项 SHOULD L1873–1884）、§44（推荐布局 L2100–2202）。

### 0.2 G8 门禁逐字回应（Plan §17 L747–757）

Plan 原文（`docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` L747–757）：

```text
## G8

必须完成：

- snapshot → load → same WorldState；
- event replay → same committed state；
- branch A/B 独立；
- non-checkpointable backend 明确拒绝 branch，而不是静默错误；
- Development intervention 可在 trace 中区分；
- CLI JSON schema 稳定；
- causal chain 可从 event 回溯至 action / effect / producer。
```

逐项回应（实现策略 / A 判据 / 承载测试函数；A 全量定义见 §5.2，1:1 映射见 §5.3）：

1. **snapshot → load → same WorldState**
   - 实现策略：T01 持久化信封（`PersistenceSnapshot`，§3.2）嵌套冻结 core
     `Snapshot` 信封（`core/snapshot.py:73`，`SNAPSHOT_FORMAT_VERSION` L70 = 1）零重定义
     （D-P8-02）；T02 `FilesystemPersistenceBackend.save/load` 经冻结
     `dump_json`/`load_json`（`core/serialization.py:54/67`）落盘/读盘；load 侧经
     冻结 `check_snapshot_versions`（`core/snapshot.py:171`）+ P8 信封层版本门双重校验。
   - A 判据：**A1**（save→load 后 `WorldState` 字段级相等，含 `world_revision`）、
     **A2**（任一层版本失配 → 显式 `PersistenceError`，码 ∈ `P8_ERROR_CODES`）。
   - 测试函数：`test_g8_scenarios.py::test_g8_1_save_load_same_world_state`（A1）、
     `::test_g8_1_version_mismatch_explicit`（A2）。
2. **event replay → same committed state**
   - 实现策略：T03 `replay_committed`（§3.4）**不重跑后端**——按 `commit_revision`
     序把 trace 中 COMMITTED 事务逐笔经冻结 `apply_transaction`
     （`core/reducer.py:974`，唯一状态变更路径）重放；`CommittedEffect` 内嵌完整
     `ProposedEffect`（`core/effects.py:245`，设计注记 L241–242"事务/快照记录自包含，
     event-level replay 无需回查 trace 索引"）保证自足；逐笔校验
     `base_revision == 当前 world_revision` 连续性。Spec §30.4 最低保证
     （L1607–1611：记录过的 commands/effects/events 可重构 committed WorldState 历史，
     不要求 numerical backend bit-identical rerun）⇒ replay 路径天然双跑字节一致（K7）。
   - A 判据：**A3**（replay 终态 == 活管道终态，`model_dump(mode="json")` 相等）、
     **A4**（replay 双跑字节一致 + 连续性校验生效）。
   - 测试函数：`test_g8_scenarios.py::test_g8_2_replay_same_committed_state`（A3）、
     `::test_g8_2_replay_double_run_byte_identical`（A4）。
3. **branch A/B 独立**
   - 实现策略：T05 `branch_world`（§3.6）= 新 WorldInstance 原型
     （`WorldInstanceHandle`，Spec §7.2 L500–510 的信封层身份三元组）；重建经冻结
     `restore_snapshot`（`core/snapshot.py:150`，D-15 第 4 条零别名）⇒ A/B 不共享
     任何可变容器；branch 不 bump revision（分支非提交）。
   - A 判据：**A5**（改 A 的 world variable/组件，B 不变；反之亦然）、
     **A6**（branch 信封 `world_instance_id` = 新 id + `check_snapshot_versions` 通过）。
   - 测试函数：`test_g8_scenarios.py::test_g8_3_branch_ab_independent`（A5）、
     `::test_g8_3_branch_envelope_identity`（A6）。
4. **non-checkpointable backend 明确拒绝 branch，而不是静默错误**
   - 实现策略：T05 三检查闭集 `BRANCH_CHECKS`（= Spec §30.5 L1617–1620 三项）；
     检查 1（backend checkpoint support）：凡 `BackendStateRef.checkpointable == False`
     （`core/state.py:185`）的 backend_ref，默认 `allow_degraded=False` →
     `BranchError`（码 `branch_rejected`，message 必含 backend_id）；
     `allow_degraded=True` = Spec §30.5 L1623–1626"degraded"面的**显式开关**
     （结果面 `degraded_backends` 记录，零静默）。
   - A 判据：**A7**（含 non-checkpointable ref 的 world 默认 branch → `BranchError`
     且 message 点名该 backend_id；degraded 开关下结果面可见）。
   - 测试函数：`test_g8_scenarios.py::test_g8_4_noncheckpointable_explicit_reject`（A7）。
5. **Development intervention 可在 trace 中区分**
   - 实现策略：T06（§3.7）：`DevelopmentCommand` 闭集 6 种（Spec §22 L1254–1259 逐字）；
     世界变更型命令（`inject_event`/`patch_state`）经 `to_intervention_effects` 包裹成
     冻结 `ProposedEffect`（source = `devtools.developer`，`cause_ids =
     [CauseRef(kind=INTERVENTION, ref_id=intervention_record_id)]`——冻结 `CauseKind.INTERVENTION`
     `core/provenance.py:94` 为此预留），经冻结 `CascadeExecutor.run`
     （`core/cascade.py:867`，`origin = Provenance(producer_id="devtools.developer",
     origin=OriginKind.DEVELOPER)`——冻结 `OriginKind.DEVELOPER`
     `core/provenance.py:54` 注释即"Spec §22：origin=developer 显式标记"）进入正常
     提交管道（K2 零旁路，D-P8-07）；trace 面 = 冻结 `TraceKind.DEV_INTERVENTION`
     （`core/trace.py:109`）记录 + 事务 provenance origin=developer 三重可辨。
   - A 判据：**A8**（intervention 后 trace 恰含 1 条 `dev_intervention` 记录且
     producer = `devtools.developer`；对应事务 `provenance.origin == DEVELOPER`）、
     **A9**（`patch_state` → 正常提交管道：revision +1、`CommittedEffect.source`
     = `devtools.developer`、cause 链含 INTERVENTION→该命令 DEV_INTERVENTION 记录 record_id）。
   - 测试函数：`test_g8_scenarios.py::test_g8_5_dev_intervention_trace_distinguishable`（A8）、
     `::test_g8_5_patch_state_normal_commit_pipeline`（A9）。
6. **CLI JSON schema 稳定**
   - 实现策略：T08（§3.9）：逻辑面 = `devtools/cli.py`（argparse，可测），入口 =
     `scripts/v2_devcontrol.py`（薄壳，`scripts/llm_smoke.py` 先例）；**单一** JSON
     信封：顶层恰 6 键 `{tool, schema_version, command, ok, data, error}`，
     `tool = "llmsim-devcontrol"`、`schema_version = DEVCONTROL_CLI_SCHEMA_VERSION = 1`；
     `error = null | {"code": <∈ P8_ERROR_CODES 闭集>, "message": str}`；
     `data` 逐命令 JSON-clean（冻结 `assert_json_clean`，`core/serialization.py:82`）。
   - A 判据：**A10**（5 子命令全跑 → 顶层键集恒为 6 键 + `schema_version == 1`）、
     **A11**（错误路径 `ok=false` + code ∈ 闭集 + 进程不崩溃（无裸 traceback））。
   - 测试函数：`test_g8_scenarios.py::test_g8_6_cli_envelope_schema_stable`（A10）、
     `::test_g8_6_cli_error_closed_set`（A11）。
7. **causal chain 可从 event 回溯至 action / effect / producer**
   - 实现策略：T07 `TraceQuery.causal_chain(event_id)`（§3.8）：
     `DOMAIN_EVENT` 记录 → `DomainEvent`（`core/events.py:111`，`transaction_id` L135、
     `cause_ids` L137、`source_system` L138）→ 事务记录 → `Transaction.effects[]`
     （`CommittedEffect.effect.source` = ProducerId，`core/effects.py:219/245`）→
     producer 集合；`cause_ids` 中 `CauseKind.ACTION/PROPOSAL` → action/proposal 记录
     回指、`CauseKind.INTERVENTION` → dev_intervention 记录回指（G8-5 因果闭环）。
   - A 判据：**A12**（对 scripted world 的 event：链含其事务、全部 committed effects
     及每个 effect 的 source producer；chain 含 intervention ref 指向 DEV_INTERVENTION 记录 record_id）。
   - 测试函数：`test_g8_scenarios.py::test_g8_7_causal_chain_event_to_producer`（A12）。

### 0.3 基线表

| 项 | 值 | 验证方式 |
|---|---|---|
| 基线 commit | `84a5d4f` | `git rev-parse HEAD` |
| 基线套件 | **2925 passed / 0 failed**（17.32s） | `.venv/bin/python -m pytest -q --tb=no` @ `84a5d4f` 工作树（W0 实测） |
| 门③基线 diff | `git diff --name-only 84a5d4f..HEAD -- src tests scripts` = **∅** | W0 实测（gate-③ 基线干净） |
| core 面 | 32 子模块 / `__all__` 308 导出（`core/__init__.py:416`） | AST 解析 `__all__` 计数 |
| P7 冻结面 | `dynamics/` 8 模块 35 导出（backend 12 / toy_rigid 3 / authority 7 / host 2 / composite 2 / rule 3 / llm_world 4 / diagnostic 2） | P7 SOT §8.2 @ `84a5d4f` |
| 占位字节 | `persistence/__init__.py` 8 行、`devtools/__init__.py` 8 行，**字节冻结**（门③ diff 不得包含） | `wc -l` + `cat` 实测 |
| 边界锚文件 | `tests/engine_v2/core/test_import_boundary.py` 1629 行；P4 黑名单 L225–240、P6 块 L821–1231、P7 块 L1233–1629 | `wc -l` + `grep -n` 实测 |
| 行宽 | `pyproject.toml:31` `line-length = 100`（ruff）；`pyproject.toml` 不在白名单 | 实测 |
| 测试运行器 | `.venv/bin/python -m pytest`（系统 `python3` 无 pytest——W0 实测确认） | 实测 |

### 0.4 非范围（明确不做）

1. **core/ 零变更**（S1）：不修改 `src/engine_v2/core/` 任何文件；不新增 core 导出。
2. **SQLite / PostgreSQL / remote store 后端**：Spec §30.3 MAY 项（L1597–1602），P8 只定
   `PersistenceBackend` 三方法抽象面 + filesystem 参考实现；其余后端 = P8+。
3. **scenario test 引擎**（Spec §3.2 职责之一）：CLI `test` 子命令 = save 完整性 +
   replay 一致性**校验报告**（D-P8-14，DEV-P8-5）；完整 scenario 测试编排 = P8+ host 面。
4. **项目侧 `.py` backend 发现**（OI-P7-1 移交）：**本波不实装**（D-P8-15）；
   P8 checkpoint 注册面 = host 注入（registry 由调用方构造并传入），不消费项目 `.py`；
   涉 ProjectIR 扩展则届时按 S2 走人工。
5. **测试侧 handler 提升 src**（D-P7-13 移交评估）：**维持现状**（D-P8-15）——
   P8 replay 的 handler 注册表 = host 注入参数；测试侧注册（P7 `gem_effect_handlers`
   模式）足以承载 replay，src 面零变更。
6. **RuntimeState 直接改写**：devtools 对 runtime 只出**指令**（directive），
   不直接改 `RuntimeState`（K2 一致性；runtime 台账变更 = host 职责）。
7. **并发/分布式保存**：单进程原型；`index.json` 单文件写 = 单进程语义（R7）。
8. **ViewState / 呈现层**：Spec §8.5 ViewState MUST NOT authoritative；P8 不产出 ViewState。
9. **bit-identical 数值重跑**：Spec §30.4 L1611 明确不要求；P8 replay 不消费数值后端
   （R3）。
10. **`uv.lock` 变更**：零新第三方依赖（S4）；pyproject/lock 均不在白名单。

### 0.5 纪律（W0 定调，机械验证面见 §8.1/§8.2/§3.10）

- **D1 依赖闭集**：P8 src 仅允许 stdlib（`json`/`os`/`pathlib`/`dataclasses`/
  `typing`/`collections.abc`/`argparse`/`re`/`functools`）+ 冻结 core 公开面 +
  冻结 P7 `dynamics.backend`（T04 消费 `BackendMetadata`）+ P8 包内互引。
  **零新第三方依赖**（S4）；禁 `asyncio`/`httpx`/`requests`/`socket`/`urllib`/
  `random`/`datetime`/`time`/`uuid`/`subprocess`/`threading`。
- **D2 K8 十二名扫描口径**（P8 边界方法 3 同形 P6 块 L1050–1093 实现（def L1050、体 L1061–1093）；P7 块 L1478 同构）：
  - 扫描面 = P8 全部 src 文件（9 模块 + 脚本）的 **AST Constant str 面**
    （所有字符串字面量含模块/函数 docstring、f-string 的 Constant 部件）；
  - 匹配 = **casefold** 后对 12 名逐一施加**双词边界** `\b{name}\b`
    （12 名 = P4 边界黑名单 `tests/engine_v2/core/test_import_boundary.py` L225–240
    闭集；本 SOT 正文称"推理侧 12 名"）；
  - **标识符豁免**：仅代码标识符/属性名不扫描（扫描限字符串字面量面）；
    字符串内容含该名（含路径片段如 `xx/llm/yy` 中的独立段）即命中；
  - **无拼接豁免**：字符串拼接/格式化拆分不构成豁免；
  - 负探针：`"llmsim"`、`"api_key_env"` 必须**不**命中（`\b` 边界天然免疫，
    边界测试内置探针断言）；
  - 推论：P8 src 字符串字面量中不得出现独立成词的推理侧词汇；P8 模块 docstring
    一律用"推理侧"表述；`CLI_TOOL_NAME = "llmsim-devcontrol"` 安全（`llm` 后接 `s`
    无词边界）。
- **D3 JSON-clean 铁律**：P8 全部公共数据面（`PersistenceSnapshot`/`SaveBundle`/
  `CheckpointSnapshot`/`ReplayResult`/`BranchResult`/`WorldInstanceHandle`/
  `InterventionResult`/`CausalChain`/CLI 信封）的 `to_dict()` 与落盘文本必须通过
  冻结 `assert_json_clean`（`core/serialization.py:82`）；datetime 不落 P8 数据面
  （嵌套 core `Snapshot.created_wall_time` 经 `dump_json(mode="json")` 落 ISO 串）。
- **D4 零 async / 零 IO 分层**：`persistence/replay.py`、`devtools/trace_query.py`、
  `devtools/intervention.py` 的查询/组装面**零文件 IO**（AST 机械断言：无
  `open`/`os`/`pathlib` 引用）；IO 唯一合法面 = `persistence/filesystem.py`。
- **D5 身份纪律**：P8 不发明身份——`save_id`/`command_id`/`world_instance_id`
  全部 **host 给出**（词法校验：`SAVE_ID_PATTERN` 等）；P8 内**零 `uuid4`**；
  P8 自产 trace 记录仅 1 族（DEV_INTERVENTION）= record_id host 给出确定性 `trc_` 字面量（K7 零 uuid4；冻结 `new_trace_record_id` = uuid4 工厂，P8 不消费，D-P8-17）。
- **D6 确定性双跑**（K7）：replay / 信封序列化 / CLI 三面对同一输入双跑
  **字节一致**；P8 模块**零模块级可变状态**；wall-clock 一律 host 给出
  （`created_wall_time` 参数），P8 不读时钟。
- **D7 显式失败面**（fail-loud，G8-4/5）：corruption / 版本失配 / 连续性断裂 /
  non-checkpointable branch / 未注册 effect / 未知命令 kind → P8 异常族
  （`PersistenceError` 单基类，`code` ∈ `P8_ERROR_CODES` 闭集 11 码）；
  **零静默跳过、零静默降级**（degraded 仅显式开关下且结果面记录）。
- **D8 占位字节不变**：两个占位 `__init__.py`（各 8 行）本波**零改动**（P7 先例：
  `dynamics/__init__.py` 9 行占位未动）；P8 导入一律走子模块路径
  （`from src.engine_v2.persistence.snapshot import ...`），不走包级 `__init__` 再导出。

### 0.6 风险登记册

| # | 风险 | 等级 | 缓解/处置 |
|---|---|---|---|
| R1 | 语义 effect replay 需 handler 注册表注入；CLI 独立运行时只有冻结默认结构 handler（`default_handler_registry`，`core/reducer.py:743`），含语义 effect 的 save 在 CLI replay 会失败 | 中 | CLI `replay`/`test` 对未注册语义型 → 显式 `replay_mismatch`（不静默跳过）；语义型 replay 走 host 注入注册表（T03 签名已含 `handlers` 参数）；W0 测试双覆盖（test_replay.py t2 用 P7 测试侧注册面） |
| R2 | 未来真实数值后端 non-checkpointable 时 branch 能力 | 低（本波） | 本波 G8-4 已 fail-loud（默认拒绝 + degraded 显式开关）；届时若"重要数值后端只可跑不可分支"触发 Plan §24 S5（L1274）→ 人工闸门 |
| R3 | 推理侧动力学（P7 `LLMWorldDynamics`，`replayable=False` 声明）与 replay 的关系 | 低 | Spec §30.4 最低保证不要求数值重跑；P8 replay 路径**不消费** `replayable` 声明（不重跑后端）；若未来需要"数值重跑"= P8+ 新面（需重新走 S2 评估） |
| R4 | OI-P7-1（项目侧 backend 发现）不移交风险 | 低 | D-P8-15 评估结论登记于 §4；P8 注册面 = host 注入，零项目 `.py` 消费；loader 9-glob（`content/loader.py:46/50–60`，零 `.py`）冻结不动 |
| R5 | G6 carryover：`proposal_id` 无 nonce / `uv lock` 漂移（G7 报告 L206） | 低 | P8 不引入 proposal id 新概念（复用冻结 `EffectId`/`TransactionId` 面）；零新依赖 ⇒ lock 不动 |
| R6 | 嵌套 `Snapshot` 的 pydantic 校验深度与 JSON-clean 成本 | 低 | 信封 `snapshot` 字段 = 嵌套冻结模型（非裸 dict）；`dump_json(mode="json")` 确定性（`created_wall_time` datetime → ISO）；W1 测试钉死 roundtrip |
| R7 | `index.json` 单文件写并发 | 低 | 单进程原型（§0.4.7）；并发面 = P8+（届时 SQLite 后端，S2 评估） |
| R8 | 边界锚文件纯追加后体积增长（P7 块后 1629 行 + P8 块 ≈ +380 行） | 低 | 锚文件唯一修改模式 = EOF 纯追加（P7 先例）；AST 负载增长 = 已知成本（G7 报告 L206 同项） |

### 0.7 S1–S5 预检（Plan §24 L1212–1288）

| HARD STOP | 条款（Plan 锚点） | 本波判定 | 依据 |
|---|---|---|---|
| S1 需要改变 Architecture Kernel invariant | L1216 | **未触发** | P8 = `core/` 外消费方包；§2 全部消费冻结面；`core/` 零文件变更（门③ diff 机械验证） |
| S2 Public Contract 存在两种同样合理但不兼容的设计 | L1230 | **未触发** | 二选一面均已显式单选并登记 §4：信封层（D-P8-02：嵌套复用而非新信封）/ intervention 落位（D-P8-07：P8 本地包裹而非 core 扩展）/ CLI 落位（D-P8-09：`devtools/` + `scripts/` 薄壳）/ degraded 开关（D-P8-10：显式参数而非双 API）；OI-P7-1 二选一 = 本波不实装（D-P8-15），无扩散 |
| S3 为通过测试需要 destructive migration | L1246 | **未触发** | v1 根目录零触碰；P8 save 格式 = 新格式（`PERSISTENCE_FORMAT_VERSION=1` 世代），零向后兼容义务、零迁移；`pyproject` 不动 |
| S4 引入新的重大依赖 / License 风险 | L1259 | **未触发** | stdlib only（D1 闭集）；`pyproject.toml` 不在白名单；零 lock 变更 |
| S5 Backend 无法满足 replay/checkpoint Contract | L1274 | **本波未触发**（面已备） | 本波唯一数值后端 = P7 toy（`checkpointable=True`，`dynamics/toy_rigid.py:46` 起）；non-checkpointable 面 = G8-4 fail-loud（默认拒绝）+ degraded 显式开关，非"只可跑但分支会坏"的静默态；未来真实数值后端若触发 → 人工闸门（R2） |

---

## §1 不变量

| # | 不变量 | K 锚点 / 先例 | 机械验证面 |
|---|---|---|---|
| P8-INV-1 | **core 零变更**：`persistence/`+`devtools/` 为 `core/` 外消费方包；core 32 子模块零文件引用 `engine_v2.persistence`/`engine_v2.devtools`/任何 P8 类型名 | S1（Plan L1216）；P7-INV-2 同形 | 门③ diff（§3.10 步骤 6）+ 边界方法 4（kernel-agnostic 扫描） |
| P8-INV-2 | **零 async / 零网络 / 零新依赖**：P8 src 导入面 ∈ D1 闭集；无 `asyncio`/`socket`/`urllib`/`random`/`datetime`/`time`/`uuid` 使用 | S4（Plan L1259）；core scheduler 纪律块 `core/scheduler.py:105–111` 同族 | 边界方法 4（导入面 AST）+ ruff |
| P8-INV-3 | **JSON-clean 铁律**：P8 全部公共数据面 `to_dict()`/落盘文本过 `assert_json_clean`（`core/serialization.py:82`） | Spec §0.2 JSON-friendly 铁律；P6/P7 同族 | 各模块 t 测试 + A20 + AD 族 |
| P8-INV-4 | **持久化/devtools 零状态直写**：世界写只经 `ProposedEffect → CascadeExecutor.run`（intervention，K2）与 `apply_transaction`（replay，K1/K2 复用）；devtools 对 RuntimeState 仅出 directive | K2；Spec §22 L1265–1267（正常提交管道）；`core/reducer.py:974` 唯一路径 | §5.2 A9 + test_intervention 面 + 边界方法 4 |
| P8-INV-5 | **闭集**：`P8_ERROR_CODES` 11 码 / `DEVELOPMENT_COMMAND_KINDS` 6 种 / `BRANCH_CHECKS` 3 项 / CLI 顶层 6 键 / `CLI_COMMANDS` 5 命令 / save 布局 3 件 + index / `PERSISTENCE_SAVE_FILES` 常量化 | S2（单一面显式）；P7 闭集先例（`STIMULUS_KINDS` 等） | 各模块"闭集 == 字面量"测试 + 边界方法 6（ledger） |
| P8-INV-6 | **显式失败面**：corruption/版本失配/连续性断裂/non-checkpointable/未注册 effect/未知 kind → P8 异常族（`code` ∈ 闭集）；零静默跳过/静默降级 | G8-4/5；Spec §30.5 L1623–1626（degraded 显式） | A7/A15–A19 + AD-1..AD-10 |
| P8-INV-7 | **确定性双跑**：replay/信封/CLI 三面对同一输入双跑字节一致；零模块级可变状态；零 `uuid4`；wall-clock host 给出 | K7；P7 K7 同族 | A4 + A14 + 各模块确定性 t 测试 |
| P8-INV-8 | **占位字节不变**：`persistence/__init__.py`（8 行）与 `devtools/__init__.py`（8 行）本波零改动 | D8；P7 先例（`dynamics/__init__.py` 9 行未动） | 门③ diff 子断言（白名单含 25 文件，不含两占位） |
| P8-INV-9 | **推理侧 12 名零入面**：P8 src 字符串字面量面（D2 口径）对 12 名双 `\b` casefold 扫描零命中；持久化声明载体 = P8 模块导出 + host 注入，项目不进入持久化声明 | K8；P4 黑名单 L225–240 | 边界方法 3（含负探针 `"llmsim"`/`"api_key_env"`） |
| P8-INV-10 | **版本元数据三层各自独立迁移维度**：`PERSISTENCE_FORMAT_VERSION`（P8 信封层）/ `SNAPSHOT_FORMAT_VERSION`（core 信封层，`core/snapshot.py:70`）/ `CONTRACT_SCHEMA_VERSION`（契约世代，`core/state.py:99`）；load = P8 信封层门 + 冻结 `check_snapshot_versions`（`core/snapshot.py:171`）交叉校验 | Spec §30.2 L1589–1590（Project/Module versions）；core 三层版本自相似模式 | A2 + test_snapshot_format t3/t7/t8 |

---

## §2 冻结缝表（全部 @ `84a5d4f` 字节核验）

> 路径口径：`core/…` = `src/engine_v2/core/…`；`dynamics/…` = `src/engine_v2/dynamics/…`；
> `llm/…` = `src/engine_v2/llm/…`。所有锚点 = 定义行或签名起始行。
> `content/…` = `src/engine_v2/content/…`；裸 `tests/…` = 仓库根相对路径。

### 2.1 core（32 子模块 / 308 导出，`core/__init__.py:416`）——P8 消费子集

| 模块 | 符号（行） | P8 用法 |
|---|---|---|
| `core/snapshot.py`（231 行） | `__all__` L57–65（7 导出）；`SNAPSHOT_FORMAT_VERSION` L70（=1）；`Snapshot` L73（字段 L98–107：`snapshot_format_version`/`contract_schema_version`/`world_instance_id`/`world_state`/`runtime_state`/`created_logical_tick`/`created_wall_time`/`project_version`/`module_versions`）；`snapshot()` L110–119；`restore_snapshot()` L150（→ `tuple[WorldState, RuntimeState]`）；`check_snapshot_versions()` L171（→ `tuple[str, ...]`）；`freeze_view()` L214 | T01 信封嵌套（零重定义，D-P8-02）；T02 save/load 校验；T05 branch 重建（D-15 第 4 条零别名） |
| `core/serialization.py` | `__all__` L41–46（4 导出）；`dump_json` L54；`load_json` L67；`assert_json_clean` L82；`deep_copy_via_roundtrip` L135 | P8 全部 JSON 出入口唯一合法面（D3） |
| `core/provenance.py` | `__all__` L32–38（5 导出）；`OriginKind` L41（**7 值** L49–55：`DEVELOPER` L54 注释"Spec §22：origin=developer 显式标记"，`SYSTEM` L55）；`Provenance` L58（`producer_id` L71 / `origin` L72 / `source_record_id` L73 / `notes` L74）；`CauseKind` L77（5 值 L90–94：`EVENT`/`ACTION`/`EFFECT`/`PROPOSAL`/`INTERVENTION`，INTERVENTION = L94）；`CauseRef` L97（`kind` L105 / `ref_id` L106）；`CascadeContext` L109（`cascade_id` L121 / `causal_root_id` L122 / `depth` L123） | T06 intervention 三重标记（origin/cause/kind）；T07 因果链回溯 |
| `core/trace.py`（139 行） | `__all__` L56–62（5 导出）；`PAYLOAD_RECORD_KEY` L67（`"record"`）；`DECISION_PAYLOAD_KEYS` L71；`LLM_CALL_PAYLOAD_KEYS` L76–88（9 键 frozenset）；`TraceKind` L91（12 值 L99–110：`COMMAND` L99 … `TRANSACTION` L105 / `DOMAIN_EVENT` L106 / `LLM_CALL` L107 / … / `DEV_INTERVENTION` L109 / `SYSTEM` L110）；`TraceRecord` L113（字段 L131–139：`record_id`/`kind`/`world_revision`/`logical_tick`/`wall_time`/`producer_id`/`transaction_id`/`cascade_id`/`payload`） | T03 replay 驱动记录族；T07 查询面；T08 CLI trace 命令 |
| `core/state.py` | `__all__` L85–95（9 导出）；`CONTRACT_SCHEMA_VERSION` L99（=1）；`RuntimeLifecycle` L115（5 值 L123–127，`STEPPING` L126 = pause/step 语义载体）；`BackendStateRef` L169（`backend_id` L183 / `backend_kind` L184 / `checkpointable` L185 / `restorable` L186 / `replayable` L187，三者默认 False / `checkpoint_ref` L188 / `metadata` L189）；`RuntimeState` L192（字段 L217–227：`schema_version`/`logical_tick`/`lifecycle`/`scheduler_queue`/`active_actions`/`actor_wakeups`/`active_modes`/`mode_context`/`rng_state`/`pending_proposals`/`backend_refs`）；`WorldState` L246（字段 L274–280：`schema_version`/`world_revision`/`entities`/`world_variables`/`scenario_state`） | T01 信封内容；T04 三声明消费；T05 branch 三检查；T08 inspect 面（Spec §37 1–4 项） |
| `core/revision.py` | `Revision` L43（int 子类）；`INITIAL_WORLD_REVISION` L70（`Revision(0)`）；`next_revision` L73；`is_stale` L78 | T03 连续性校验；T05 branch 不 bump 语义 |
| `core/effects.py` | `__all__` L50；`EffectTarget` L191（tagged union，判别 `"kind"` L193）；`EntityTarget` L163（`kind` L172 / `entity_id` L173 / `component_type` L174 / `field_path` L175）；`StateDomainTarget` L178（`kind` L185 / `domain` L186）；`ProposedEffect` L197（字段 L217–226：`effect_id`/`effect_type`/`source` L219（ProducerId）/`target`/`payload`/`base_revision`/`cause_ids` L223（默认空 list）/`authority_scope`/`priority_hint`/`metadata`）；`CommittedEffect` L229（`effect` L245 内嵌完整 `ProposedEffect` / `transaction_id` L246 / `commit_revision` L247 / `sequence` L248；自包含设计注记 L241–242） | T03 replay 自足性根据；T06 intervention 包裹面 |
| `core/transaction.py` | `Transaction` L62（字段 L83–92：`transaction_id`/`status`/`base_revision`/`commit_revision` L86（可空）/`logical_tick`/`effects` L88/`event_ids` L89/`cascade`/`provenance`/`abort_reason` L92；原子不变量校验 L94 起） | T03 replay 驱动单元；T07 因果链中间层 |
| `core/reducer.py` | `__all__` 37 导出；结构效果型常量 L216–222（`core.create_entity`/`core.remove_entity`/`core.set_component`/`core.remove_component`/`core.set_world_variable`/`core.remove_world_variable`/`core.set_scenario_data`）；`STRUCTURAL_EFFECT_TYPES` L226；`ReducerError` L159；`EffectHandlerRegistry` L695（ctor L711 预注册全部结构效果；`register` L717；`resolve` L730；`has` L734）；`default_handler_registry()` L743；`apply_committed_effects` L843；`apply_transaction(state, txn, *, component_registry=None, handlers=None)` L974–980（COMMITTED-only，L988–992） | T03 replay 唯一应用路径（K2 复用）；T06 patch_state 映射到结构效果；R1 CLI 默认 registry |
| `core/cascade.py` | `CascadeResult` L678（字段 L697–702：`final_state`/`transactions`/`events`/`trace_records`/`deferred`/`diagnostics`）；`CascadeExecutor` L767（ctor 必填 `policy`）；`run(initial_proposals: Sequence[ProposedEffect], state: WorldState, *, causal_root_id: str, origin: Provenance) -> CascadeResult` L867–874；authority trace 构造 L1069–1078（`payload = decision.to_trace_payload()`） | T06 提交驱动（P7 host 模式同形）；T07 authority 行面 |
| `core/transaction_executor.py` | `commit_transaction` L162；`abort_transaction` L337 | 冻结面（P8 不直接调用——replay 经 reducer 面；列此备查） |
| `core/scheduler.py` | `Scheduler` L550（ctor 必填 `origin: Provenance` L576–578）；`step` L1507；`submit_proposal` L1520（docstring：外部提案入口 player/devtools）；纪律块 L105–111 | P8 测试 conftest 驱动 scripted world（同 P7 gate 模式） |
| `core/ids.py` | `PRODUCER_ID_PATTERN` L77；`ProducerId` L189；`new_trace_record_id` L268（uuid4 工厂，P8 不消费——D-P8-17） | T06 producer id 词法校验（`PRODUCER_ID_PATTERN`） |
| `core/events.py` | `DomainEvent` L111（字段 L131–141：`event_id`/`event_type`/`world_revision`/`logical_tick`/`transaction_id` L135/`payload`/`cause_ids` L137/`source_system` L138/`provenance`/`cascade`/`wall_time`） | T03 event 重建；T07 因果链起点 |
| `core/authority.py` | `AuthorityPolicy`/`AuthorityRule`/`AuthoritySelector`（core 根导出）；`check_authority` L550 | 测试侧 policy（devtools.developer 放行规则） |
| `core/components.py` | `ComponentRegistry` L144 | conftest 注册表注入 |
| `core/entity.py` | `ContractModel` L51（frozen + extra="forbid" 基类） | T01 `PersistenceSnapshot` 基类 |
| `core/clock.py` | `LogicalClock` L77（世界逻辑时钟） | 备查（P8 不消费——逻辑 tick = host 传入；**注意**：`core/clock.py` = 逻辑时钟，monotonic clock Protocol 在 P6 `llm/adapter.py:47`——任务书此处归属有误，§9 勘误） |

> 导入面注意（DEV-P8-6）：`snapshot()` 函数**不在** core `__all__`（308 中无此项，
> AST 实测）⇒ P8 从子模块 `src.engine_v2.core.snapshot` 导入（非 core 变更，纯导入路径）。
> 其余 P8 消费名均在 core 根 `__all__`（AST 逐一核验通过：`ReducerError`/
> `AuthorityPolicy`/`AuthorityRule`/`AuthoritySelector`/`AuthorityEvaluationResult`/
> `ComponentRegistry`/`default_handler_registry` 等）。

### 2.2 P7 `dynamics/`（8 模块 35 导出，冻结交付 @ `ea84d00`/`84a5d4f`）

| 模块 | 符号（行） | P8 用法 |
|---|---|---|
| `dynamics/backend.py` | 12 导出（`WorldSnapshot`/`Stimulus`/`STIMULUS_KINDS`/`DynamicsContext`/`InferenceBudget`/`BackendMetadata`/`DETERMINISM_CLASSES`/`IMPLEMENTATION_TYPES`/`FIDELITY_PATTERN`/`WorldDynamicsBackend`/`new_deterministic_effect_id`/`DynamicsError`） | T04 消费 `BackendMetadata`（三声明声明载体） |
| `dynamics/toy_rigid.py` | 3 导出；`RIGID_COMPONENT` L40；`TOY_CHECKPOINT_VERSION` L43（=1）；`ToyRigidDynamics` L46（`metadata` L62（checkpointable=True）；`simulate` L76；`checkpoint()` L127 → `{"version": 1, "seed": N}` L132；`restore()` L134（版本门 L150）） | T04 注册/恢复的参考实现；T05 branch 检查 1 的正样本；conftest 语义 save |
| `dynamics/authority.py` | 7 导出；producer ids L51–54（`rule_dynamics`/`llm_world_dynamics`/`rigid_body`/`composite_dynamics`）；`P7_PRODUCER_IDS` L55；`build_dynamics_producers` L80；`default_dynamics_policy` L100；优先级 100/100/80/50 L62–65 | conftest 动力学 save 的 policy/producer 接线（P7 gate 同形） |
| `dynamics/host.py` | 2 导出（`run_dynamics_turn` L86；`DynamicsTurn` L40）；驱动模式 = simulate → `executor.run(effects, state, causal_root_id=…, origin=…)` | T06 驱动同形先例（devtools driver = 自包含组装点，D-P8-07） |
| `dynamics/composite.py` / `rule.py` / `llm_world.py` / `diagnostic.py` | 2/3/4/2 导出 | 备查（P8 W0 测试不直接消费） |

### 2.3 P6 冻结面（conftest 消费，P8 src 零消费）

| 符号（行） | 用法 |
|---|---|
| `llm/adapter.py`：`MonotonicClock` L47（Protocol）；`FixedMonotonicClock` L71；`FakeInferenceBackend` L296（`script: dict[tuple[str, Revision, int], str]` L316；lookup `(logical_role, base_revision, seq)` L300/L333；`calls` L326；`generate` L330） | persistence conftest 动力学 flavor save 的脚本化推理面 |
| `llm/deployment.py`：8 导出；`load_deployment` L122 | conftest 装载 `tests/fixtures/v2_deployment_p7/deployment.yaml` |
| `prompts/diagnostic.py`：`RuntimeDiagnostic` L21；`P6_RUNTIME_DIAGNOSTIC_CODES` L57（21 码） | 备查（P8 W0 不消费） |

### 2.4 P5 冻结面（评估消费，零变更）

| 符号（行） | 用法 |
|---|---|
| `content/loader.py`（`src/engine_v2/content/loader.py`）：`LAYOUT_REQUIRED` L46；`LAYOUT_OPTIONAL` L50–60（**9-glob 闭集，零 `.py`**） | OI-P7-1 评估面（D-P8-15）：P8 不扩展 9-glob、不读项目 `.py`；注册面 = host 注入 |

### 2.5 边界锚文件（`tests/engine_v2/core/test_import_boundary.py`，1629 行 @ `84a5d4f`）

| 块 | 行 | P8 关系 |
|---|---|---|
| `P4_LLM_PROVIDER_BLACKLIST`（推理侧 12 名闭集） | L225–240 | 边界方法 3 直接复用（import 自既有块） |
| P6 块（`TestP6Boundary` L959；12 名扫描方法 def L1050、体 L1061–1093） | L821–1231 | 方法 3 实现同形模板 |
| P7 块：`P7_SRC_SUBMODULES` L1240 / `P7_TEST_FILES` L1253（12 文件）/ `_P7_WHITELIST_23` L1270 / `P7_EXPORT_LEDGER` L1297 / `_p7_ast_face` L1335 / `_p7_string_literal_face` L1347 / `TestP7Boundary` L1355（6 方法 L1388/L1469/L1478/L1527/L1585/L1617） | L1233–1629 | P8 块 = **EOF 纯追加**（L1629 之后），6 方法同构（§3.10.3）；P7 块零改动 |

### 2.6 占位文件（字节冻结，门③ diff 不得包含）

| 文件 | 行数 | 内容 |
|---|---|---|
| `src/engine_v2/persistence/__init__.py` | 8 | "占位，Phase 8 填充"（本波保持原样——D8：导入走子模块路径） |
| `src/engine_v2/devtools/__init__.py` | 8 | "v2 开发控制平面 devtools（占位，Phase 8 填充）"（引用 Spec §22/§33/§37/§44；本波保持原样） |

### 2.7 冻结测试侧缝（conftest 消费，零改动）

| 缝（行） | 用法 |
|---|---|
| `tests/engine_v2/dynamics/conftest.py`：`_det_entity_id` L49；`make_p7_world` L54；`make_p7_component_registry` L77；`gem_effect_handlers` L125（注册 `gem.moved`/`gem.fell` 语义 handler，L134–135）；`make_p7_producer_registry` L139；`make_p7_policy` L149；`make_p7_executor` L159；fixtures `stim_support_removed` L176（session）/ `p7_deployment` L188 / `p7_game` L200 / `scripted_wire_response` L208；fixture 根 L46（`tests/fixtures/`） | persistence conftest 动力学 flavor save 复用（`from tests.engine_v2.dynamics.conftest import …`；测试树含 `__init__.py`，包路径可导入） |
| `tests/fixtures/v2_deployment_p7/`、`tests/fixtures/v2_project_p7/` | conftest fixture 路径（P7 §6.4 已钉死，P8 零新增 fixture 文件） |

---

## §3 模块设计

### 3.0 包树与导入纪律闭集

```text
src/engine_v2/
  persistence/                    # P8-T01..T05（占位 __init__ 字节冻结）
    __init__.py                   #   8 行占位，零改动（D8）
    base.py                       #   T01a：错误族 / 布局常量 / 抽象面 / SaveBundle
    snapshot.py                   #   T01：持久化信封（格式 + 版本元数据）
    filesystem.py                 #   T02：filesystem PersistenceBackend 参考实现
    replay.py                     #   T03：event-level replay 引擎（零 IO）
    checkpoint.py                 #   T04：BackendCheckpoint 注册 / 恢复（零 IO）
    branch.py                     #   T05：branch / fork WorldInstance 原型（零 IO）
  devtools/                       # P8-T06..T08（占位 __init__ 字节冻结）
    __init__.py                   #   8 行占位，零改动（D8）
    intervention.py               #   T06：DevelopmentCommand / ExternalInterventionEffect
    trace_query.py                #   T07：trace 查询 / 因果链 API（零 IO）
    cli.py                        #   T08：CLI 逻辑面（argparse；JSON 信封）
  core/                           # 冻结（32 子模块 / 308 导出）
  dynamics/                       # 冻结（8 模块 35 导出）
scripts/
  v2_devcontrol.py                # T08：薄入口（sys.exit(run_devcontrol_cli(sys.argv[1:]))）
tests/engine_v2/
  persistence/                    # 8 文件：__init__/conftest/test_snapshot_format/
                                  #   test_filesystem_backend/test_replay/
                                  #   test_checkpoint_registry/test_branch/test_p8_adversarial
  devtools/                       # 6 文件：__init__/conftest/test_intervention/
                                  #   test_trace_query/test_cli/test_g8_scenarios
  core/test_import_boundary.py    # 纯追加 P8 块（唯一锚文件）
```

**导入纪律闭集**（P8 src 全部模块 + 脚本；ruff + 边界方法 1 双验证）：

| 允许 | 禁止 |
|---|---|
| stdlib：`json` `os` `pathlib` `dataclasses` `typing` `collections.abc` `argparse`（仅 cli.py）`re` `functools`（仅脚本）`sys`（仅脚本） | `asyncio` `httpx` `requests` `socket` `urllib` `random` `datetime` `time` `uuid` `subprocess` `threading` 及其余全部 stdlib/三方（`pydantic` = 独立允许行 3 名窄例外，D-P8-18；零新依赖——`pydantic` ∈ uv.lock 既有） |
| `src.engine_v2.core`（根，仅 §2.1 已列消费名）；`src.engine_v2.core.snapshot`（子模块，仅 `snapshot` 函数——DEV-P6 导入路径） | core 其余子模块直引（未列即禁） |
| `pydantic`（仅 3 名：`Field` / `model_validator` / `ValidationError`——ContractModel 基础设施面，与冻结 core 27 模块同款；D-P8-18） | pydantic 其余名（未列即禁） |
| `src.engine_v2.dynamics.backend`（仅 `BackendMetadata`，T04） | dynamics 其余子模块直引 |
| P8 包内：`persistence.base` → 被全部 P8 模块消费；`persistence.snapshot` → filesystem/branch/cli；`persistence.filesystem` → cli；`persistence.replay` → cli；`persistence.checkpoint` → branch/cli；`persistence.branch` → cli；`devtools.trace_query` → cli；`devtools.intervention` → cli | devtools → persistence 之外的跨包引用（`devtools → persistence.base` 单向允许：错误族单基类，D-P8-11） |

循环规避：`base.py` 对 `snapshot.py` 仅 `TYPE_CHECKING` 引用（`SaveBundle` 字段注解）；
运行时导入方向单向：`base ← snapshot ← filesystem/branch ← cli`，`base ← replay/checkpoint ← cli`，
`base ← intervention/trace_query ← cli`。

### 3.1 `persistence/base.py`（T01a；7 导出）

```python
__all__ = (
    "PERSISTENCE_FORMAT_VERSION",
    "PERSISTENCE_SAVE_FILES",
    "SAVE_ID_PATTERN",
    "P8_ERROR_CODES",
    "PersistenceError",
    "PersistenceBackend",
    "SaveBundle",
)
```

| 名 | 形 | 语义 |
|---|---|---|
| `PERSISTENCE_FORMAT_VERSION` | `Final[int] = 1` | P8 持久化信封格式世代（P8-INV-10 三层版本之 P8 层） |
| `PERSISTENCE_SAVE_FILES` | `Final[tuple[str, ...]] = ("snapshot.json", "checkpoints", "trace.jsonl")` | 单个 save 目录的**闭集**布局（P8-INV-5）；load 侧布局校验依据（额外文件 → `layout_violation`） |
| `SAVE_ID_PATTERN` | `Final[str] = r"[a-z0-9][a-z0-9_]{0,127}"` | `save_id` 词法（host 给出；D5） |
| `P8_ERROR_CODES` | `Final[tuple[str, ...]]` | **11 码闭集**：`save_not_found` / `corrupt_file` / `schema_invalid` / `version_mismatch` / `layout_violation` / `checkpoint_unavailable` / `replay_mismatch` / `branch_rejected` / `intervention_rejected` / `usage_error` / `internal_error` |
| `PersistenceError` | `class (Exception)` | 字段 `code: str`（ctor 校验 ∈ `P8_ERROR_CODES`，否则 `ValueError`）、`message: str`；`__str__` = "[code] message"；P8 两包**唯一**异常基类（S2 单面） |
| `PersistenceBackend` | `@runtime_checkable Protocol`（isinstance 探针面，t14 锚定） | 3 方法抽象面（Spec §30.3 MAY 的 P8 单一定义；D-P8-03）：`save(*, save_id, envelope, checkpoint_payloads, trace_records) -> None`；`load(*, save_id) -> SaveBundle`；`list_saves() -> tuple[str, ...]` |
| `SaveBundle` | `@dataclass(frozen=True)` | 字段：`save_id: str`；`envelope: PersistenceSnapshot`；`checkpoint_payloads: Mapping[str, Mapping[str, object]]`；`trace_records: tuple[TraceRecord, ...]`；`to_dict() -> dict[str, object]`（JSON-clean，D3） |

docstring 纪律：模块 docstring 说明"持久化基面：错误族 / 布局闭集 / 抽象后端面 /
save 载体"；**不得**出现推理侧 12 名独立词（D2）。

### 3.2 `persistence/snapshot.py`（T01；5 导出）

```python
__all__ = (
    "PersistenceSnapshot",
    "to_persistence_snapshot",
    "dump_persistence_snapshot",
    "load_persistence_snapshot",
    "check_persistence_versions",
)
```

**`PersistenceSnapshot`**（`ContractModel` 继承——frozen + extra="forbid"，
`core/entity.py:51`；D-P8-02：嵌套复用冻结 core 信封，零字段重定义）：

| 字段 | 类型 | 语义 / 校验 |
|---|---|---|
| `persistence_format_version` | `int`（默认 `PERSISTENCE_FORMAT_VERSION`） | P8 层版本；load 门要求 `== 1`（否则 `version_mismatch`） |
| `snapshot` | `Snapshot`（core 嵌套模型，**非裸 dict**） | 状态层信封（R6：嵌套模型保校验深度） |
| `project_version` | `str \| None` | Spec §30.2 L1589；顶层冗余镜像；`model_validator`：必须 `== snapshot.project_version`（失配 → `schema_invalid`） |
| `module_versions` | `dict[str, str]`（默认 `{}`） | Spec §30.2 L1590；顶层冗余镜像；同上交叉校验 |
| `backend_checkpoints` | `dict[str, str]`（默认 `{}`） | Spec §30.2 L1587（Backend checkpoints）：backend_id → checkpoint_ref（相对路径，如 `"checkpoints/toy_rigid.json"`）；**只存 ref，不存体**（体在 `checkpoints/` 目录，T04） |
| `trace_ref` | `str \| None`（默认 `None`） | Spec §30.2 L1588（Event/Trace log）：如 `"trace.jsonl"` |
| `created_wall_time` | `str \| None`（默认 `None`） | ISO-8601 串（**非 datetime**——P8 数据面零 datetime，D3/D6）；诊断面，host 给出；不参与状态身份 |

`to_dict() -> dict[str, object]`：`model_dump(mode="json")` + `assert_json_clean`。

**签名**：

```python
def to_persistence_snapshot(
    snapshot: Snapshot,
    *,
    backend_checkpoints: Mapping[str, str] | None = None,
    trace_ref: str | None = None,
    created_wall_time: str | None = None,
) -> PersistenceSnapshot: ...   # 纯函数；project/module_versions 自 snapshot 镜像

def dump_persistence_snapshot(envelope: PersistenceSnapshot) -> str: ...
    # assert_json_clean(envelope.to_dict()) + dump_json(envelope)（冻结
    # dump_json 仅收 BaseModel，core/serialization.py:54）；确定性（D6）

def load_persistence_snapshot(payload: str | bytes) -> PersistenceSnapshot: ...
    # 唯一合法入口 = load_json（serialization.py:67）；
    # pydantic ValidationError → PersistenceError(code="schema_invalid")；
    # persistence_format_version != 1 → PersistenceError(code="version_mismatch")

def check_persistence_versions(envelope: PersistenceSnapshot) -> tuple[str, ...]: ...
    # 空 = 一致；非空 = 问题串元组；含冻结 check_snapshot_versions（snapshot.py:171）
    # 的完整输出 + P8 层检查（persistence_format_version / 冗余镜像一致性）
```

Spec §30.2 六项覆盖核对：WorldState snapshot / RuntimeState snapshot（嵌套
`Snapshot.world_state/runtime_state`）✓；Backend checkpoints（`backend_checkpoints`
ref 面 + filesystem 体面）✓；Event/Trace log（`trace_ref` + `trace.jsonl`，全
`TraceRecord` JSONL——**超集**覆盖，DEV-P8-4）✓；Project version（顶层 + 嵌套双
镜像）✓；Module versions（顶层 + 嵌套双镜像）✓。

### 3.3 `persistence/filesystem.py`（T02；2 导出）

```python
__all__ = ("FilesystemPersistenceBackend", "read_trace_records")
```

**目录布局**（`<base>` = 构造参数；单 save 目录闭集 = `PERSISTENCE_SAVE_FILES`）：

```text
<base>/
  index.json                    # {"persistence_format_version": 1,
  saves/<save_id>/              #   "saves": {"<id>": {"created_wall_time": str | null}}}
    snapshot.json               # PersistenceSnapshot 全文（dump_persistence_snapshot）
    checkpoints/                # 每 backend 一个 <backend_id>.json（checkpoint 体，JSON-clean）
    trace.jsonl                 # 每行一条 TraceRecord JSON（保序）
```

**`FilesystemPersistenceBackend`**：

| 方法 | 语义 | 失败面（code） |
|---|---|---|
| `__init__(base_dir: str \| Path)` | 记录根目录；不预创建（惰性） | — |
| `save(*, save_id, envelope, checkpoint_payloads, trace_records) -> None` | `save_id` 词法（`SAVE_ID_PATTERN.fullmatch`，否则 `schema_invalid`）；`os.makedirs(exist_ok=True)`；**原子写** = 同目录临时文件（`<name>.tmp`）+ `os.replace`（D6 双跑确定性；A14 依据）；写序：`snapshot.json` → 各 `checkpoints/<id>.json` → `trace.jsonl` → `index.json`（upsert 条目）；同 `save_id` 二次 save = **整体覆盖**（旧文件被替换，确定性 winner） | 词法 → `schema_invalid`；OS 错误 → `internal_error`（wrap，保留原因） |
| `load(*, save_id) -> SaveBundle` | 读 `index.json`（缺 save 条目 → `save_not_found`）；`snapshot.json` → `load_persistence_snapshot`；`checkpoints/` 逐个 `load_json`（JSON-clean 校验）；`trace.jsonl` → `read_trace_records`；save 目录含**闭集外文件** → `layout_violation`（显式，不忽略） | `save_not_found` / `corrupt_file` / `schema_invalid` / `version_mismatch` / `layout_violation`（§3.1 闭集） |
| `list_saves() -> tuple[str, ...]` | index 键**排序**（确定性，D6）；无 index → 空元组 | — |

**`read_trace_records(path: str \| Path) -> tuple[TraceRecord, ...]`**：
逐行 `load_json` → `TraceRecord`（唯一合法入口）；保文件序；空行跳过；坏行 →
`PersistenceError(corrupt_file)`（message 含**行号**）；`record_id` 重复 →
`corrupt_file`。

IO 面纪律（D4）：本模块 = P8 **唯一**文件 IO 面；`os` 仅用 `makedirs`/`replace`/
`listdir`，禁 `remove` 以外的破坏性调用（临时文件失败清理亦经 `os.replace` 语义族）。

### 3.4 `persistence/replay.py`（T03；3 导出）

```python
__all__ = ("ReplayResult", "ReplayError", "replay_committed")
```

**`ReplayResult`**（`@dataclass(frozen=True)`）：

| 字段 | 类型 | 语义 |
|---|---|---|
| `final_state` | `WorldState` | 重放终态（与输入零别名——K7/零别名族） |
| `base_revision` / `final_revision` | `int` | 起止 revision（`final == base + transactions_applied` 恒等） |
| `transactions_applied` | `int` | 应用的 COMMITTED 事务数 |
| `applied_transaction_ids` | `tuple[str, ...]` | 应用序 transaction_id 闭集 |
| `events` | `tuple[DomainEvent, ...]` | 由 `DOMAIN_EVENT` 记录重建（其 `transaction_id` ∈ 应用集），序 = `(commit_revision, 事务内 event_ids 序)` |
| `to_dict()` | `dict[str, object]` | JSON-clean（`final_state.model_dump(mode="json")` + 计数 + event ids） |

**`ReplayError`**（`PersistenceError` 子类；默认码 `replay_mismatch`）。

**`replay_committed`**（零 IO、零模块状态——D4/D6）：

```python
def replay_committed(
    world_state: WorldState,
    trace_records: Sequence[TraceRecord],
    *,
    handlers: EffectHandlerRegistry | None = None,
    component_registry: ComponentRegistry | None = None,
) -> ReplayResult: ...
```

算法（确定性；同一 `(world_state, trace_records, handlers)` 双跑字节一致——A4）：

1. **抽取**：`kind == TraceKind.TRANSACTION` 记录 → `payload["record"]`
   （`PAYLOAD_RECORD_KEY`，`core/trace.py:67`）→ `Transaction`（pydantic 校验，
   失败 → `ReplayError(schema_invalid)`）；`(record_id, transaction_id)` 去重校验
   （重复 → `ReplayError`）。
2. **排序**：`status is COMMITTED` 子集按 `commit_revision` 稳定排序；同一
   `commit_revision` 出现两笔 COMMITTED → `ReplayError`（revision 唯一性，
   Spec §20.1 同族）。
3. **逐笔应用**（K2 唯一路径复用）：每笔校验 `txn.base_revision ==
   world_state.world_revision`（断裂 → `ReplayError`，message 含两侧 revision——
   A16/AD-4 面）；`state = apply_transaction(state, txn, component_registry=…,
   handlers=…)`（冻结 `core/reducer.py:974`）；`ReducerError`（如未注册语义型
   effect，R1）→ wrap `ReplayError`（**不静默跳过**——AD-5 面）。
4. **ABORTED 跳过**：非 COMMITTED 事务不驱动状态（A21）；其审计存在性由 trace 面
   保留（冻结 `core/trace.py:105` 注释"含 ABORTED，审计原子失败"）。
5. **event 重建**：`DOMAIN_EVENT` 记录（`transaction_id` ∈ `applied_transaction_ids`）
   → `DomainEvent`，按序组装（Spec §30.4"commands/effects/events 可重构"面）。

不重跑后端（D-P8-05）：replay 不消费任何 `WorldDynamicsBackend` ⇒ Spec §30.4
L1611"不要求 bit-identical rerun"自然满足；`replayable` 声明（`core/state.py:187`）
在 replay 路径**不被消费**（R3）。

### 3.5 `persistence/checkpoint.py`（T04；3 导出）

```python
__all__ = ("CheckpointError", "CheckpointSnapshot", "BackendCheckpointRegistry")
```

**`CheckpointError`**（`PersistenceError` 子类；默认码 `checkpoint_unavailable`）。

**`CheckpointSnapshot`**（`@dataclass(frozen=True)`）：字段 `backend_id: str` /
`checkpointable: bool` / `restorable: bool` / `replayable: bool`（镜像注册 metadata
三声明，`dynamics/backend.py` `BackendMetadata`）/ `checkpoint: Mapping[str, object] |
None`（non-checkpointable → `None`，**降级可见**——非静默丢弃）；`to_dict()` JSON-clean。

**`BackendCheckpointRegistry`**（零 IO——checkpoint 体进出 = 调用方/filesystem 面）：

| 方法 | 语义 | 失败面 |
|---|---|---|
| `register(*, backend_id: str, metadata: BackendMetadata, instance: object) -> None` | 绑定 `backend_id → (metadata, instance)`；重复 id → `CheckpointError`；**一致性门**：`metadata.checkpointable == True` 而 instance 无 `checkpoint` 可调用 → `CheckpointError(schema_invalid)`（声明/能力不符，显式）；`restorable == True` 而 instance 无 `restore` → 同 | `checkpoint_unavailable` / `schema_invalid` |
| `checkpoint_all() -> tuple[CheckpointSnapshot, ...]` | 按注册序（确定性）：checkpointable → `instance.checkpoint()`（返回值必须 dict，`assert_json_clean`；非 dict → `CheckpointError(schema_invalid)`）；non-checkpointable → `checkpoint=None`（降级可见，`to_dict` 面可辨） | `schema_invalid` |
| `restore(*, backend_id: str, checkpoint: Mapping[str, object]) -> object` | 委派 `instance.restore(checkpoint)`（toy 模式：返回**新实例**，`dynamics/toy_rigid.py:134`；版本门在实例侧，`L150`）；未知 id → `CheckpointError`；实例侧异常（版本失配/类型坏）→ wrap `CheckpointError`（版本类 → `version_mismatch`，形态类 → `schema_invalid`——判别最窄实现：实例侧异常 `str` casefold 含 `version` → 版本类，余 → 形态类；锚冻结 `dynamics/toy_rigid.py:150` 版本门消息面；ERR-P8-03 补注） | `checkpoint_unavailable` / `version_mismatch` / `schema_invalid` |
| `validate_refs(backend_refs: Sequence[BackendStateRef]) -> tuple[str, ...]` | 空 = 一致；ref 的 backend_id 未注册 → issue 串；ref `checkpointable=True` 而注册项 non-checkpointable → issue 串（声明漂移显式） | —（报告面，不抛） |

### 3.6 `persistence/branch.py`（T05；5 导出）

```python
__all__ = (
    "BRANCH_CHECKS",
    "BranchError",
    "WorldInstanceHandle",
    "BranchResult",
    "branch_world",
)
```

| 名 | 形 | 语义 |
|---|---|---|
| `BRANCH_CHECKS` | `Final[tuple[str, ...]] = ("backend_checkpoint_support", "runtime_snapshot_availability", "project_compatibility")` | Spec §30.5 L1617–1620 三项**闭集**（P8-INV-5）；`BranchResult.checks` 行名锚 |
| `BranchError` | `PersistenceError` 子类 | 默认码 `branch_rejected` |
| `WorldInstanceHandle` | `@dataclass(frozen=True)` | 字段 `world_instance_id: str`（host 给出；D-9 信封层身份，`core/snapshot.py:130` 注释同族）/ `world_state: WorldState` / `runtime_state: RuntimeState`；`to_dict()` JSON-clean |
| `BranchResult` | `@dataclass(frozen=True)` | 字段 `handle: WorldInstanceHandle` / `degraded_backends: tuple[str, ...]`（degraded 开关下的点名面——G8-4 非静默）/ `checks: tuple[dict[str, object], ...]`（3 行，行名 = `BRANCH_CHECKS`，每行 `{"check", "ok", "detail"}`）；`to_dict()` JSON-clean |
| `branch_world(...)` | 见下签名 | 见下语义 |

**签名**：

```python
def branch_world(
    source: WorldInstanceHandle,
    *,
    new_world_instance_id: str,
    registry: BackendCheckpointRegistry,
    checkpoints: Mapping[str, Mapping[str, object]] | None = None,
    allow_degraded: bool = False,
    source_project_version: str | None = None,
    target_project_version: str | None = None,
    source_module_versions: Mapping[str, str] | None = None,
    target_module_versions: Mapping[str, str] | None = None,
) -> BranchResult: ...
```

**三检查语义**（顺序执行；任一失败 → `BranchError`，message 含检查名 + 涉事对象）：

1. **backend_checkpoint_support**：对 `source.runtime_state.backend_refs`
   （`core/state.py:227`）逐条：
   - `checkpointable == False` → 默认（`allow_degraded=False`）→ `BranchError`
     （**明确拒绝**，G8-4；message 含该 backend_id）；`allow_degraded=True` →
     记入 `degraded_backends`（Spec §30.5 L1623–1626"degraded"显式面）；
   - `checkpointable == True` → `checkpoints` 必含该 backend_id 的 payload
     （缺 → `BranchError`；payload 非 dict → `BranchError(schema_invalid)`）；
     `registry.validate_refs` 的 issue 面并入 `checks` 行 detail。
2. **runtime_snapshot_availability**：以 `new_world_instance_id` 构造冻结
   `snapshot(world_state, runtime_state, world_instance_id, ...)`
   （`core/snapshot.py:110`；零别名固化内建——D-15 第 4 条）→
   `check_snapshot_versions`（`core/snapshot.py:171`）非空 → `BranchError
   (version_mismatch)`（issues 并入 detail）。
3. **project_compatibility**：`source_project_version` 与 `target_project_version`
   均非 None 且不等 → `BranchError`；`module_versions` 双方共有键值不同 →
   `BranchError`；任一侧未给（None）→ 该项通过（原型口径：兼容面锚定 host 给值，
   不猜）。

**重建**：`restore_snapshot(检查 2 的 Snapshot)`（`core/snapshot.py:150`）→
`(world_state, runtime_state)` 零别名新对象 → `WorldInstanceHandle(new_id, …)`
（G8-3 独立性的机械根据——A5/A22）。branch **不 bump** `world_revision`
（分支非提交；新分支首笔提交由 host 经正常管道完成）。

### 3.7 `devtools/intervention.py`（T06；11 导出）

```python
__all__ = (
    "DEVTOOLS_DEVELOPER_PRODUCER",
    "DEVELOPMENT_COMMAND_KINDS",
    "WORLD_MUTATING_KINDS",
    "RUNTIME_CONTROL_KINDS",
    "INSTANCE_LEVEL_KINDS",
    "DevelopmentCommand",
    "ExternalInterventionEffect",
    "InterventionResult",
    "InterventionError",
    "to_intervention_effects",
    "apply_development_command",
)
```

**闭集常量**（P8-INV-5）：

| 名 | 值 | 依据 |
|---|---|---|
| `DEVTOOLS_DEVELOPER_PRODUCER` | `"devtools.developer"`（`Final[str]`） | fullmatch 冻结 `PRODUCER_ID_PATTERN`（`core/ids.py:77`）；producer 注册 = host policy 面（测试侧放行） |
| `DEVELOPMENT_COMMAND_KINDS` | `("pause", "step", "force_wake", "inject_event", "patch_state", "branch")` | Spec §22 L1254–1259 六例**逐字闭集**（"例如"非穷举 → 闭集 = P8 本地契约，D-P8-13；新增 kind = 波次决策，非开放枚举） |
| `WORLD_MUTATING_KINDS` | `("inject_event", "patch_state")` | 子集闭集：走正常提交管道（Spec §22 L1265–1267） |
| `RUNTIME_CONTROL_KINDS` | `("pause", "step", "force_wake")` | 子集闭集：只出 runtime directive（§0.4.6：devtools 不直写 RuntimeState） |
| `INSTANCE_LEVEL_KINDS` | `("branch",)` | 子集闭集：实例级操作（= T05 `branch_world` 的控制面标记，DEV-P8-3） |

（三子集闭集 **partition** 全集——机械断言：并集 == 全集、两两交集空。）

**`DevelopmentCommand`**（`@dataclass(frozen=True)`）：字段 `command_id: str`
（host 给出；空串/纯空白 → `InterventionError(schema_invalid)`）/ `kind: str`
（ctor 校验 ∈ `DEVELOPMENT_COMMAND_KINDS`，否则 `InterventionError(usage_error)`
——A19 面）/ `payload: Mapping[str, object]`（ctor 时 `assert_json_clean`）。

**`ExternalInterventionEffect`**（`@dataclass(frozen=True)`）：字段
`command_id: str` / `effect: ProposedEffect`（冻结模型包裹——D-P8-07）；
`to_dict()` JSON-clean。

**`InterventionResult`**（`@dataclass(frozen=True)`）：字段 `world_state: WorldState`
（可能已变更）/ `changed: bool` / `runtime_directive: tuple[str, ...] | None`
（如 `("pause",)` / `("force_wake", "<entity_id>")`；世界变更型 = `None`）/
`cascade_result: CascadeResult | None`（非世界变更型 = `None`）/
`trace_records: tuple[TraceRecord, ...]`（含 1 条 `DEV_INTERVENTION` 记录 +
级联 trace）；`to_dict()` JSON-clean。

**`InterventionError`**（`PersistenceError` 子类；默认码 `intervention_rejected`）。

**`to_intervention_effects(command, *, base_revision: Revision, intervention_record_id: str) ->
tuple[ExternalInterventionEffect, ...]`**（纯函数；`intervention_record_id` = 该命令 DEV_INTERVENTION 记录 record_id（D-P8-17））：

| kind | payload 闭集形态 | 映射（结构效果常量，`core/reducer.py:216–222`） |
|---|---|---|
| `patch_state` | `{"target": "world_variable", "key": <str>, "value": <JsonValue>}` | `core.set_world_variable`；target = `StateDomainTarget(domain="world_variables")`（tagged union 判别 `"kind"`，`core/effects.py:191`）；payload = `{"key": …, "value": …}` |
| `patch_state` | `{"target": "component", "entity_id": <str>, "key": <component_type str>, "data": <Mapping>}` | `core.set_component`；target = `EntityTarget(entity_id=…, component_type=…)`；payload = `{"data": …}` 展开为组件数据（冻结 handler 契约：`core/reducer.py:415` 起 `state_set_component` 读 `effect.payload` 为组件数据） |
| `inject_event` | `{"effect_id": <host 给出>, "effect_type": <str>, "target_kind": "entity"\|"state_domain", "entity_id": <str, entity 分支>, "domain": <str, state_domain 分支>, "payload": <Mapping>}` | 通用 `ProposedEffect` 包裹（effect_type 原样——未注册语义型在正常管道 L1 即显式拒绝，D-P2-05 同族；P8 不特判） |
| 其他 3 kind | — | 返回空元组（非世界变更型，`to_intervention_effects` 仅对 `WORLD_MUTATING_KINDS` 有产出） |

所有产出的 `ProposedEffect` 统一：`source = DEVTOOLS_DEVELOPER_PRODUCER`；
`base_revision` = 参数；`cause_ids = [CauseRef(kind=CauseKind.INTERVENTION,
ref_id=intervention_record_id)]`（冻结 `CauseKind.INTERVENTION`，`core/provenance.py:94`；D-P2-20：ref_id = 该命令 DEV_INTERVENTION 记录 record_id，D-P8-17）。

**`apply_development_command(command, *, world_state: WorldState,
executor: CascadeExecutor, logical_tick: int = 0, intervention_record_id: str) ->
InterventionResult`**（`intervention_record_id` host 给出；空/非 `trc_` 词法 →
`InterventionError(schema_invalid)`，`core/ids.py:180–186`；devtools driver = 自包含组装点，
P7 `dynamics/host.py:86` 模式同形——D-P8-07）：

1. 命令校验（闭集 / JSON-clean / command_id 词法）。
2. `DEV_INTERVENTION` 记录：`TraceRecord(record_id=intervention_record_id
   （host 给出，K7 零 uuid4——D-P8-17）, kind=TraceKind.DEV_INTERVENTION（core/trace.py:109）,
   world_revision=world_state.world_revision（干预时刻读数）, logical_tick=参数,
   producer_id=DEVTOOLS_DEVELOPER_PRODUCER, payload={"command":
   command 的 JSON-clean dict})`。
3. 分派：
   - `RUNTIME_CONTROL_KINDS`：`changed=False`；`runtime_directive = (kind,)`
     （`force_wake` 附 entity_id：`("force_wake", payload["entity_id"])`，缺 key →
     `InterventionError(usage_error)`）；`cascade_result=None`；trace 仅 dev 记录。
   - `INSTANCE_LEVEL_KINDS`（`branch`）：`changed=False`；
     `runtime_directive=("branch",)`；实例级动作 = host 调 `branch_world`
     （command_id 作为 causal 锚点，DEV-P8-3）。
   - `WORLD_MUTATING_KINDS`：`effects = to_intervention_effects(...)` →
     `result = executor.run(tuple(e.effect for e in effects), world_state,
     causal_root_id=command.command_id,
     origin=Provenance(producer_id=DEVTOOLS_DEVELOPER_PRODUCER,
     origin=OriginKind.DEVELOPER))`（冻结 `core/cascade.py:867–874`）；
     `InterventionResult(world_state=result.final_state, changed=True,
     cascade_result=result, trace_records=(dev_record, *result.trace_records))`。

**K2/K3 面**：干预效果与任何 producer 提案走**同一条** authority/validation/reducer
管道（`check_authority` L550 → L1 → commit）；`devtools.developer` 未获 policy
放行 → 正常 deny（closed-by-default，K3）——测试侧 policy 显式放行（conftest）。

### 3.8 `devtools/trace_query.py`（T07；3 导出）

```python
__all__ = ("TraceQuery", "CausalChain", "TraceQueryError")
```

**`TraceQuery`**（同步、零 IO——D4：构造即索引，全内存）：

```python
def __init__(self, records: Sequence[TraceRecord]) -> None: ...
    # 索引：kind → list；transaction_id → list（2 项；无 record_id
    # 直查——causal_chain 经 by_kind(DOMAIN_EVENT) 扫描）；
    # 顺序 = 输入序（确定性，D6）

def records(self) -> tuple[TraceRecord, ...]: ...          # 输入序原样
def by_kind(self, kind: TraceKind) -> tuple[TraceRecord, ...]: ...
def by_producer(self, producer_id: str) -> tuple[TraceRecord, ...]: ...
def domain_events(self) -> tuple[DomainEvent, ...]: ...    # payload["record"] 解析
def transactions(self) -> tuple[Transaction, ...]: ...     # 全量（含 ABORTED）
def committed_transactions(self) -> tuple[Transaction, ...]: ...
def authority_decisions(self) -> tuple[dict[str, object], ...]: ...
    # 行 = {"record_id", "world_revision", "producer_id", "payload"}；
    # payload = 冻结 decision.to_trace_payload()（core/cascade.py:1076）原样透传
    # （JSON-clean 由产生侧保证；P8 零重定义）
def revision_timeline(self) -> tuple[dict[str, object], ...]: ...
    # 每 revision 一行（升序）：{"world_revision", "logical_tick", "wall_time",
    # "kinds": <sorted kind 值元组>, "transaction_count", "event_count"}
def intervention_history(self) -> tuple[TraceRecord, ...]: ...   # kind=DEV_INTERVENTION
def causal_chain(self, event_id: str) -> CausalChain: ...        # G8-7
    # 同一 transaction_id 多记录时取输入序末条（trace 文件序）
```

Spec §37 12 项（L1873–1884）分配（D-P8-08）：WorldState 检视 / RuntimeState /
Scheduler 队列 / ActiveAction 台账 = **快照派生 4 项 → T08 `inspect` 面**（数据源 =
`SaveBundle.envelope.snapshot` 的 `WorldState`/`RuntimeState`，含
`scheduler_queue`/`active_actions` 字段，`core/state.py:220–221`）；Effect 链 /
Event 链 / authority 决策 / producer 活动 / causal root / revision 时间线 /
branch/replay 审计 / 开发干预历史 = **trace 派生 8 项 → T07 面**。ViewState
（Spec §8.5）MUST NOT authoritative——P8 不产出（§0.4.8）。

逐项映射（R1 设计分叉裁定，S2 单选 = 派生面，不加专用方法）：8 项 = 7 具体方法
（Effect 链→`transactions()` / Event 链→`domain_events()` / authority 决策→
`authority_decisions()` / producer→`by_producer()` / causal root→`causal_chain()` /
revision 时间线→`revision_timeline()` / 开发干预历史→`intervention_history()`）
+ 1 派生面：**branch/replay 审计 = 派生查询，不新增 `replay_audit()`/`branch_markers()`
专用方法**——branch 半 = `intervention_history()` + `payload["command"]["kind"] ==
"branch"` 过滤（每 branch 命令产 1 条 DEV_INTERVENTION 记录，§3.7 步 2）；replay 半
= `replay_committed` 纯重构、不产 trace 记录（§3.4），其审计面 = `transactions()`
（含 ABORTED——冻结 `core/trace.py:105` 注释）+ `domain_events()`。

**`CausalChain`**（`@dataclass(frozen=True)`）：

| 字段 | 类型 | 语义 |
|---|---|---|
| `event` | `DomainEvent` | 链起点（`core/events.py:111`） |
| `transaction` | `Transaction \| None` | 经 `event.transaction_id`（L135）定位 |
| `effects` | `tuple[CommittedEffect, ...]` | `transaction.effects`（含完整内嵌 `ProposedEffect`） |
| `producers` | `tuple[str, ...]` | 唯一化 + 排序：`event.source_system`（L138）+ 各 `effect.effect.source`（`core/effects.py:219`） |
| `action_refs` | `tuple[str, ...]` | `event.cause_ids` + 各 effect `cause_ids` 中 `CauseKind.ACTION/PROPOSAL` 的 `ref_id`（回指 action/proposal 记录） |
| `intervention_refs` | `tuple[str, ...]` | 同上但 `CauseKind.INTERVENTION`（回指 `DEV_INTERVENTION` 记录的 record_id——G8-5/G8-7 闭环） |
| `to_dict()` | `dict[str, object]` | JSON-clean（模型 `model_dump(mode="json")` + id 元组） |

未知 `event_id` / payload 解析失败 → `TraceQueryError`（`PersistenceError` 子类，
码 `schema_invalid`）。

### 3.9 `devtools/cli.py`（T08；5 导出）+ `scripts/v2_devcontrol.py`

```python
__all__ = (
    "CLI_TOOL_NAME",
    "DEVCONTROL_CLI_SCHEMA_VERSION",
    "CLI_COMMANDS",
    "build_cli_envelope",
    "run_devcontrol_cli",
)
```

| 名 | 值 / 形 | 语义 |
|---|---|---|
| `CLI_TOOL_NAME` | `Final[str] = "llmsim-devcontrol"` | 信封 `tool` 字段；D2 安全（`llm` 后接 `s` 无词边界） |
| `DEVCONTROL_CLI_SCHEMA_VERSION` | `Final[int] = 1` | 信封 `schema_version`（G8-6 稳定锚；升版 = 波次决策） |
| `CLI_COMMANDS` | `Final[tuple[str, ...]] = ("inspect", "trace", "replay", "branch", "test")` | 子命令**闭集**（Plan §17 T08 逐字 + `test`） |
| `build_cli_envelope(command, *, ok, data=None, error_code=None, error_message=None) -> dict[str, Any]` | 纯函数 | **顶层恰 6 键**：`{"tool", "schema_version", "command", "ok", "data", "error"}`；`error = None | {"code": <∈ P8_ERROR_CODES>, "message": str}`；`ok=false` 时 `data=None`；构造即 `assert_json_clean`（S2 单面——全部子命令共用） |
| `run_devcontrol_cli(argv: Sequence[str], *, base_dir: str \| Path \| None = None, backend: PersistenceBackend \| None = None) -> int` | argparse（stdlib） | 解析 → 执行 → **stdout 单行 JSON**（`json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":"))`）→ 返回码 |

**返回码闭集**：`0` = `ok=true`；`1` = `ok=false` 且 code ≠ `usage_error`
（含 `branch_rejected` 显式拒绝——G8-4 在 CLI 面同样 fail-loud，**不**返回 0）；
`2` = `usage_error`（无子命令 / 未知子命令 / 缺参）。

**子命令语义**（数据面全部 JSON-clean；`backend` 参数缺省 =
`FilesystemPersistenceBackend(base_dir)`）：

| 子命令 | 参数 | `data` 面（闭集键） | Spec 锚点 |
|---|---|---|---|
| `inspect` | `<save_id>` | `{"save_id", "world_state", "runtime_state", "backend_refs", "persistence_versions"}`（`runtime_state` 含 `scheduler_queue`/`active_actions`——§37 1–4 项快照派生面；`persistence_versions` = 三层版本读数） | §37 L1873–1876 |
| `trace` | `<save_id> [--kind <kind>]` | `{"save_id", "records", "count"}`（`records` = `TraceRecord` JSON 数组，保序；`--kind` ∈ 冻结 `TraceKind` 12 值，非法 → `usage_error`） | §37 L1877–1882 |
| `replay` | `<save_id>` | `{"save_id", "final_world_state", "base_revision", "final_revision", "transactions_applied", "events"}`；registry = 冻结 `default_handler_registry()`（R1：语义型 → 显式 `replay_mismatch`，不静默）；walk 最窄实现注（DEV-W4-2 更新）：自快照 revision 起取最长连续已提交前缀——`base_revision` 低于快照 revision 的事务视为已反映于快照态（跳过不重放）；运行结束存档 = 空前缀（applied=0），基线态存档（快照 revision == trace 起点）= 全量重放 | §30.4；G8-2 |
| `branch` | `<save_id> --new-id <id>` | 成功 = `BranchResult.to_dict()`；拒绝 = `ok=false` + `error.code="branch_rejected"`（非 checkpointable 默认拒绝——G8-4） | §30.5；G8-3/4 |
| `test` | `<save_id>` | `{"save_id", "ok", "checks"}`；`checks` 行名**闭集 5**：`layout`（闭集布局）/ `envelope_versions`（三层一致）/ `trace_parse`（JSONL 可解析）/ `replay_consistency`（replay 终 revision == 快照 `world_revision`——G8-2 的 save 级最强代理）/ `json_clean`（全体落盘文本过 `assert_json_clean`）；报告面生成 ⇒ 信封恒 ok=true（检查行失败不翻信封/rc；`data["ok"] = all(checks)` 为总体裁决载体——SOT 沉默面，W4-R1 裁定 DEV-W4-4） | §3.2 validate+test（D-P8-14，DEV-P8-5） |

**`--json` 旗标**（Spec §3.2 L212 MUST）：解析器**接受**该旗标；W0 原型输出恒为
JSON 信封（无人读模式——单面，D-P8-09）；测试断言：有无 `--json` 信封逐字节一致。
最窄实现注：`--json` 定义于主解析器（全局位置，子命令之前；t13 钉此位置）；
子命令后位置不接受 → `usage_error`（rc 2）；旗标为 no-op（`json_output`
dest 从不读取）——SOT 沉默面，W4-R1 裁定 DEV-W4-3。

**`scripts/v2_devcontrol.py`**（薄壳；`scripts/llm_smoke.py` 先例同形）：

```python
#!/usr/bin/env python3
"""v2 dev control plane CLI 入口（薄壳；逻辑面 = src/engine_v2/devtools/cli.py）。"""
import sys
from src.engine_v2.devtools.cli import run_devcontrol_cli

if __name__ == "__main__":
    sys.exit(run_devcontrol_cli(sys.argv[1:]))
```

### 3.10 波次、闭集白名单与门禁 6 步

#### 3.10.1 波次表（依赖序；每波独立可门禁）

| 波 | 任务 | 新增文件（白名单内） | 新增测试 |
|---|---|---|---|
| W1 | T01+T02 | `persistence/base.py`、`persistence/snapshot.py`、`persistence/filesystem.py`、`tests/engine_v2/persistence/__init__.py`、`tests/engine_v2/persistence/conftest.py`、`test_snapshot_format.py`、`test_filesystem_backend.py` | 12+14 = **26** |
| W2 | T03+T04 | `persistence/replay.py`、`persistence/checkpoint.py`、`test_replay.py`、`test_checkpoint_registry.py` | 13+11 = **24** |
| W3 | T05+T06 | `persistence/branch.py`、`devtools/intervention.py`、`test_branch.py`、`test_intervention.py` | 13+12 = **25** |
| W4 | T07+T08 | `devtools/trace_query.py`、`devtools/cli.py`、`scripts/v2_devcontrol.py`、`tests/engine_v2/devtools/__init__.py`、`tests/engine_v2/devtools/conftest.py`、`test_trace_query.py`、`test_cli.py` | 12+14 = **26** |
| W5 | T09 | `test_p8_adversarial.py`、`test_g8_scenarios.py`、`tests/engine_v2/core/test_import_boundary.py`（**纯追加** P8 块） | 10+12 = **22** |
| 合计 | T01–T09 | **25 文件** | **123** |

#### 3.10.2 闭集白名单（门③ diff 的**精确**右值；25 文件，编号引用）

| # | 路径 | 波 |
|---|---|---|
| 1 | `src/engine_v2/persistence/base.py` | W1 |
| 2 | `src/engine_v2/persistence/snapshot.py` | W1 |
| 3 | `src/engine_v2/persistence/filesystem.py` | W1 |
| 4 | `src/engine_v2/persistence/replay.py` | W2 |
| 5 | `src/engine_v2/persistence/checkpoint.py` | W2 |
| 6 | `src/engine_v2/persistence/branch.py` | W3 |
| 7 | `src/engine_v2/devtools/intervention.py` | W3 |
| 8 | `src/engine_v2/devtools/trace_query.py` | W4 |
| 9 | `src/engine_v2/devtools/cli.py` | W4 |
| 10 | `scripts/v2_devcontrol.py` | W4 |
| 11 | `tests/engine_v2/persistence/__init__.py` | W1 |
| 12 | `tests/engine_v2/persistence/conftest.py` | W1 |
| 13 | `tests/engine_v2/persistence/test_snapshot_format.py` | W1 |
| 14 | `tests/engine_v2/persistence/test_filesystem_backend.py` | W1 |
| 15 | `tests/engine_v2/persistence/test_replay.py` | W2 |
| 16 | `tests/engine_v2/persistence/test_checkpoint_registry.py` | W2 |
| 17 | `tests/engine_v2/persistence/test_branch.py` | W3 |
| 18 | `tests/engine_v2/persistence/test_p8_adversarial.py` | W5 |
| 19 | `tests/engine_v2/devtools/__init__.py` | W4 |
| 20 | `tests/engine_v2/devtools/conftest.py` | W4 |
| 21 | `tests/engine_v2/devtools/test_intervention.py` | W3 |
| 22 | `tests/engine_v2/devtools/test_trace_query.py` | W4 |
| 23 | `tests/engine_v2/devtools/test_cli.py` | W4 |
| 24 | `tests/engine_v2/devtools/test_g8_scenarios.py` | W5 |
| 25 | `tests/engine_v2/core/test_import_boundary.py`（纯追加） | W5 |

> 占位 `persistence/__init__.py` 与 `devtools/__init__.py` **不在**白名单
> （P8-INV-8：字节不变）；`pyproject.toml` / `uv.lock` / docs 均不在白名单。

#### 3.10.3 TestP8Boundary（6 方法，同构 P7 块 L1355；纯追加于锚文件 EOF）

| 方法 | 语义（同构 P7 对应） |
|---|---|
| `test_p8_src_import_whitelist` | 9 src 模块 + 脚本的 import 面 ∈ §3.0 闭集（同构 P7 L1388） |
| `test_p8_test_files_closed` | `tests/engine_v2/persistence/`（8 文件）+ `tests/engine_v2/devtools/`（6 文件）目录枚举 == 闭集（同构 P7 L1469；`P7_TEST_FILES` L1253 模式） |
| `test_p8_k8_string_scan` | P8 src + 脚本字符串字面量面对推理侧 12 名 casefold 双 `\b` 扫描零命中 + 负探针 `"llmsim"`/`"api_key_env"` 不命中（同构 P7 L1478；实现模板 P6 块 def L1050 / 体 L1061–1093） |
| `test_p8_kernel_agnostic_zero_async` | core 32 子模块 + `core/__init__.py` 零引用 `engine_v2.persistence`/`engine_v2.devtools`/P8 类型名（AST 名 + 字符串面）；P8 src 导入面零 `asyncio`/`socket`/`random`/`datetime`/`time`/`uuid`（同构 P7 L1527） |
| `test_p8_whitelist_diff_mirror` | `git diff --name-only 84a5d4f..HEAD -- src tests scripts` == `P8_WHITELIST`（25 文件）；子断言：两占位 `__init__.py` 不在 diff（同构 P7 L1585） |
| `test_p8_export_ledger_dual_equality` | 9 模块：AST `__all__` == `P8_EXPORT_LEDGER[module]` 且每个名 = 模块级定义（双相等，同构 P7 L1617） |

#### 3.10.4 门禁 6 步运行序（每波收口 + 最终门）

```text
1. .venv/bin/python -m pytest tests/engine_v2/persistence tests/engine_v2/devtools -q
   # P8 新面（红→绿；每波追加后重跑）
2. .venv/bin/python -m pytest tests/engine_v2/core/test_import_boundary.py -q
   # 边界锚（含 TestP8Boundary 6 方法）
3. .venv/bin/python -m pytest -q --tb=no
   # 全量：期望 3048（§8.3 恒等式）
4. .venv/bin/python -m ruff check src/engine_v2/persistence src/engine_v2/devtools \
      tests/engine_v2/persistence tests/engine_v2/devtools scripts/v2_devcontrol.py
   # 新面范围（line-length = 100，pyproject.toml:31）
5. .venv/bin/python -m ruff check
   # 全量回归
6. git diff --name-only 84a5d4f..HEAD -- src tests scripts   # == 白名单 25 文件
   git diff --stat 84a5d4f..HEAD -- src/engine_v2/persistence/__init__.py \
       src/engine_v2/devtools/__init__.py                     # 两占位 = 零改动
   grep -rPl '[\x00-\x08\x0B\x0C\x0E-\x1F]' <白名单 25 文件>   # 控制字节预扫（ERR-P7-14 项 3 同形）= 空
```

---

## §4 决策登记（D-P8-01..18；五段式：问题 / 备选 / 选择 / 理由 / 机械验证面；（自裁）标记者备选段豁免 = P7 D-P7-13/14/15 先例）

**D-P8-01 包落位与模块粒度**
- 问题：T01–T08 代码落哪两个既有占位包？模块名是否逐字对齐 Spec §44（L2100–2202）？
- 备选：(a) 单包 `persistence/` 全量 + devtools 仅 CLI；(b) `persistence/`（T01–T05）+
  `devtools/`（T06–T08），模块名任务粒度。
- 选择：(b)。`base.py`（错误族/抽象面）为 P8 新增文件（DEV-P8-1）；replay/branch
  逻辑面在 `persistence/`，CLI 复用（DEV-P8-2）。
- 理由：两占位包已按此分工标注"Phase 8 填充"；Spec §44 为**推荐**布局（P7 先例
  DEV-P7-2：模块粒度偏离登记为非偏离）；replay/branch 是持久化语义（零 IO 面），
  与 T02 的 IO 面同包便于 D4 分层。
- 机械验证面：§3.10.2 白名单 25 文件；边界方法 2（测试文件闭集）。

**D-P8-02 T01 信封：嵌套复用 vs 新信封**
- 问题：持久化格式 = 复用冻结 core `Snapshot` 信封，还是 P8 另定义新信封？
- 备选：(a) P8 重定义一份持久化专用状态信封（双信封）；(b) P8 信封 = 存储格式层，
  **嵌套**冻结 `Snapshot` 模型（零字段重定义），自持 `persistence_format_version` +
  checkpoint ref + trace ref + 冗余版本镜像。
- 选择：(b)。
- 理由：S2 单面（双信封 = 两种同样合理但不兼容的设计，触发 S2）；core 信封已含
  Spec §30.2 的 WorldState/RuntimeState/Project/Module versions 四项；P8 层只补
  存储语义（checkpoint ref 面 + trace ref 面 + 格式世代）；三层版本各自独立迁移
  （P8-INV-10）。
- 机械验证面：A1/A2；test_snapshot_format t3（冗余镜像失配显式）；§8.4 DEV-P8-6
  （`snapshot()` 子模块导入路径登记）。

**D-P8-03 T02 抽象面：是否定义 PersistenceBackend Protocol**
- 问题：T02 = "filesystem PersistenceBackend reference"——参考实现是否需要抽象面？
- 备选：(a) 只写 `FilesystemPersistenceBackend` 具体类（无抽象）；(b) `base.py` 定义
  3 方法 Protocol（save/load/list_saves）+ filesystem 参考实现；SQLite/PostgreSQL/
  remote store（Spec §30.3 MAY L1597–1602）= P8+。
- 选择：(b)，抽象面 = 3 方法最小面。
- 理由：Spec §30.3 列举 5 类后端 ⇒ 抽象面是 spec 预期；3 方法面不预设任何具体
  后端语义（单面，S2）；`branch`/`replay` CLI 的 `backend` 参数类型化（§3.9）。
- 机械验证面：边界方法 1（base.py 仅 TYPE_CHECKING 引用 snapshot）；t14（协议方法面）。

**D-P8-04 T02 布局与原子写**
- 问题：save 目录布局？写原子性？
- 备选：(a) 单文件（snapshot + checkpoints + trace 合一 JSON）；(b) 3 文件闭集
  （`snapshot.json` / `checkpoints/<id>.json` / `trace.jsonl`）+ `index.json`；
  原子写 = 同目录临时文件 + `os.replace`。
- 选择：(b)。
- 理由：trace 追加语义与 JSONL 天然对齐（Spec §8.4 记录流）；checkpoint 体与
  envelope ref 分离 = T04 的体/ref 分层；`os.replace` = stdlib 原子语义（D1）；
  闭集布局 = load 侧 `layout_violation` 显式校验面（P8-INV-5）。
- 机械验证面：t1（闭集布局）、t12（脏目录显式）、A14（原子写）、AD-1/AD-8/AD-9。

**D-P8-05 T03 replay 语义：重跑后端 vs 应用已提交事务**
- 问题：event-level replay 如何重构 committed WorldState 历史？
- 备选：(a) 重跑数值后端（bit-identical 要求）；(b) 按 `commit_revision` 序应用
  trace 中 COMMITTED 事务（经冻结 `apply_transaction`），不重跑后端。
- 选择：(b)。
- 理由：Spec §30.4 L1607–1611 最低保证 = "记录过的 commands/effects/events 可以
  重构 committed WorldState 历史"，且**明确**"不要求所有 numerical backend
  bit-identical rerun"；`CommittedEffect` 内嵌完整 `ProposedEffect`
  （`core/effects.py:241–242` 设计注记自包含）⇒ (b) 完全满足 spec 且 K7 双跑
  字节一致；(a) 将把 `replayable=False` 的推理侧后端拖入重跑（R3 触发 S2 风险）。
- 机械验证面：A3/A4；test_replay t2（P7 语义 handler 测试侧注入——D-P7-13 评估锚）；
  AD-4/AD-5（连续性/未注册显式）。

**D-P8-06 T04 注册表绑定与 checkpoint 体位**
- 问题：checkpoint 注册表绑定什么？checkpoint 体存哪？
- 备选：(a) 注册表只存 `BackendStateRef`（无活实例）；(b) 注册表绑定
  `backend_id → (BackendMetadata, 活实例)`；envelope `backend_checkpoints` 只存
  **ref**，体在 filesystem `checkpoints/` 目录。
- 选择：(b)。
- 理由：restore 需要活实例委派（toy 模式：`restore` 返回新实例，
  `dynamics/toy_rigid.py:134`）；体/ref 分离 = Spec §30.2 "Backend checkpoints"
  与 §8.3 三声明的自然分层；注册表零 IO（D4）——体进出 = filesystem 面。
- 机械验证面：test_checkpoint_registry 全 11 函数；A17/AD-2（恢复失败显式）。

**D-P8-07 T06 intervention 落位与提交路径**
- 问题：`ExternalInterventionEffect` 放 core 还是 P8？世界变更如何提交？
- 备选：(a) core 新增 intervention 类型（**触发 S1**——core 零变更被破）；(b) P8 本地
  包裹：`ExternalInterventionEffect` = 冻结 `ProposedEffect` 的 typed wrapper
  （source=`devtools.developer` + `CauseRef(INTERVENTION)`），提交 = 冻结
  `CascadeExecutor.run(origin=Provenance(origin=OriginKind.DEVELOPER))`（P7 host
  驱动同形）。
- 选择：(b)。
- 理由：S1 不可破；core 冻结面已备齐三重标记（`OriginKind.DEVELOPER` L54 +
  `CauseKind.INTERVENTION` L94 + `TraceKind.DEV_INTERVENTION` L109）——P8 只做
  **组装**，零重定义；K2/K3：干预与正常提案同管道（authority closed-by-default 天然
  适用）。`patch_state` 映射到**冻结结构效果**（`core.set_world_variable`/
  `core.set_component`，默认 registry 内置 handler）⇒ 不依赖测试侧语义 handler
  （D-P7-13 维持的机械根据之一）。
- 机械验证面：A8/A9；test_intervention t5–t7；G8-5 双函数。

**D-P8-08 T07 查询 API 形态与 §37 12 项分配**
- 问题：trace 查询 = 同步零 IO 还是 IO 内聚？Spec §37 12 项（L1873–1884）归谁？
- 备选：(a) TraceQuery 内聚 IO（自读 save 目录）；(b) TraceQuery = 纯内存
  （消费 `tuple[TraceRecord, ...]`），IO = T02 面；§37 12 项 = trace 派生 8 项
  （T07）+ 快照派生 4 项（T08 `inspect`）。
- 选择：(b)。
- 理由：D4 零 IO 分层（查询面对内存 trace 可测/可嵌 host）；§37 前 4 项数据源 =
  `WorldState`/`RuntimeState`（快照），非 trace——按数据源分配零双实现；
  因果链（G8-7）纯 trace 派生。
- 机械验证面：t12（零 IO AST）；A12/A13；test_cli t3（inspect 快照派生面）。

**D-P8-09 T08 CLI 落位与 JSON 信封**
- 问题：CLI 代码放 `scripts/` 还是 `src/`？JSON schema 如何定稳？
- 备选：(a) 全部逻辑在 `scripts/v2_devcontrol.py`（不可测）；(b) 逻辑 =
  `devtools/cli.py`（可测）+ `scripts/` 薄壳（`scripts/llm_smoke.py` 先例）；
  信封 = 顶层恰 6 键 + `schema_version=1` + 错误码闭集。
- 选择：(b)。
- 理由：`scripts/` 先例 = 薄入口（`llm_smoke.py`）；G8-6"schema 稳定"需要可测的
  单一信封构造面（`build_cli_envelope` 纯函数）；6 键闭集 + 11 错误码闭集 =
  机械稳定面；`--json` 旗标接受但输出恒 JSON（W0 单面，D-P8-13 同族口径）。
- 机械验证面：A10/A11；test_cli 全 14 函数；A20（JSON-clean）。

**D-P8-10 T05 branch 语义与 degraded 开关**
- 问题：branch = 完整会话系统还是原型？non-checkpointable 后端 = 静默降级还是拒绝？
- 备选：(a) WorldInstanceHandle 原型 + 默认拒绝 + `allow_degraded` 显式开关；
  (b) 默认静默降级（结果不含该 backend）；(c) 完整 session/branch 树系统。
- 选择：(a)。
- 理由：G8-4 逐字要求"明确拒绝 branch，而不是静默错误"⇒ 默认拒绝；Spec §30.5
  L1623–1626"degraded / unavailable"⇒ degraded 是 spec 允许的**显式**能力降级面，
  单参数开关（S2 单面：一个 API，显式布尔）；(c) 超 W0 范围（Spec §7.2 原型足够）。
  branch 经 `restore_snapshot` 零别名重建 ⇒ G8-3 机械成立。
- 机械验证面：A5–A7；A22；test_branch 全 13 函数；AD-6/AD-7/AD-10。

**D-P8-11 错误族单基类**
- 问题：P8 两包异常 = 各自基类还是单基类？
- 备选：(a) persistence/devtools 各定义异常族；(b) `PersistenceError` 单基类
  （`persistence/base.py`）+ 11 码闭集，devtools 继承复用。
- 选择：(b)。
- 理由：S2 单面（错误码是公共契约——CLI 信封 `error.code` 与库异常同一闭集）；
  devtools → persistence.base 单向导入（§3.0 允许项）。
- 机械验证面：t12（P8_ERROR_CODES 闭集断言）；A11；边界方法 6（ledger）。

**D-P8-12 K7 确定性线**
- 问题：P8 确定性面如何钉死？
- 备选：(a) 全链世界双跑字节相等（含 LLM 面）；(b) 四面对（replay/信封/filesystem/CLI）
  + 零模块级可变状态 + id 全 host 给出 + 零 uuid4 + 零 wall-clock。
- 选择：replay（A4）/ 信封序列化（dump 确定性，t4）/ filesystem 双 save（t13，
  固定 wall time）/ CLI（t13 同族）四面对同一输入双跑字节一致；零模块级可变
  状态；id 全 host 给出（D5）+ 零 `uuid4`；wall-clock 零读取。
- 理由：K7 不变量（P7 同族）；`created_wall_time` = 参数（ISO 串）⇒ P8 src 零
  `datetime` 导入（D1 闭集的自然推论）。
- 机械验证面：A4/A14/t13；边界方法 4（datetime 禁面）。

**D-P8-13（自裁）DevelopmentCommand 闭集 = Spec §22 六例逐字**
- 问题：§22 L1254–1259 是"例如"（非穷举）——P8 命令集 = 开放还是闭集？
- 选择：闭集 = 六例逐字 `("pause","step","force_wake","inject_event","patch_state",
  "branch")`；新增 kind = 波次决策（需同步 authority policy 面 + 测试）。
- 理由：S2 纪律 = 二选一面必须显式单选；开放枚举无法机械验证（P8-INV-5 需要
  字面量锚）；三子集 partition 闭集使分派面可穷举测试。
- 机械验证面：test_intervention t1（闭集 == 字面量）；t2（未知 kind 显式）。

**D-P8-14（自裁）CLI `test` 子命令语义**
- 问题：Plan T08 列 `test --json`——= 什么？
- 选择：`test` = save 完整性 + replay 一致性**校验报告**（5 检查行闭集，§3.9）；
  完整 scenario 测试编排 = P8+（§0.4.3）。
- 理由：Spec §3.2 职责含 validate + scenario test 两义；W0 单面 = 校验报告
  （可机械、零 scenario 引擎）；`replay_consistency` 行 = G8-2 的 save 级最强代理。
- 机械验证面：test_cli t7（checks 行名闭集）；DEV-P8-5。

**D-P8-15（自裁）P7 移交评估：OI-P7-1 与 D-P7-13**
- 问题：G7 报告 §7（L195/L197）移交 P8 的两项如何处置？
- 选择：**OI-P7-1**（项目侧 `.py` backend 发现）= **本波不实装**——P8 checkpoint
  注册面 = host 注入（`BackendCheckpointRegistry` 由调用方构造传入），零项目 `.py`
  消费；loader 9-glob（`content/loader.py:46/50–60`，零 `.py`）冻结；若届时
  实装涉 ProjectIR 扩展 = S2 邻域，走人工（G7 报告 L195 同口径）。**D-P7-13**
  （测试侧-only handler 注册）= **维持现状**——P8 replay 的 `handlers` 参数 = host
  注入（test_replay t2 用 P7 `gem_effect_handlers` 测试侧注册面完整跑通语义 replay），
  且 T06 `patch_state` 映射到冻结结构 handler（零测试侧依赖）⇒ src 面零变更需求。
- 理由：S1（core/loader 冻结）+ 最小面原则；两项评估结论均有机械锚（t2 / §0.4.4）。
- 机械验证面：test_replay t2；R4/R5 登记；§0.4.4/5。

**D-P8-16（自裁）G6 carryover 处置**
- 问题：G7 报告 L206 移交的 P8 评估面 = `proposal_id` nonce + `uv lock`。
- 选择：`proposal_id` nonce = **不适用**——P8 不引入 proposal id 新概念（复用冻结
  `EffectId`/`TransactionId`/`command_id`（host 给出）面）；`uv lock` = **零变更**
  （S4：stdlib only，lock 不在白名单）。
- 理由：R5 登记；评估 = "无需处置"结论本身即移交面闭合。
- 机械验证面：门③ diff（lock 不在 25 文件）；§8.3 恒等式（零依赖影响）。

**D-P8-17（自裁）干预 cause ref 指向 DEV_INTERVENTION 记录 record_id**
- 问题：`CauseRef(INTERVENTION, ref_id)` 的 ref_id 指向什么？冻结
  `core/validation.py:148–157`（D-P2-20 注释 L148–150；`_CAUSE_REF_EXPECTED_KIND`
  dict L151–157，INTERVENTION 条目 L156）将 INTERVENTION 映射至
  TraceRecordId 词法，注释明言「开发干预在 trace 中以 dev_intervention 记录承载，
  无独立 ID 族」（D-P2-20）。
- 备选：(a) ref_id = command_id（command_id 被迫取 trc_ 词法——语义是命令标识、
  词法冒充记录 ID，指向不存在的记录）；(b) ref_id = 该命令 DEV_INTERVENTION 记录
  record_id（host 给出确定性 trc_ 字面量）。
- 选择：**(b)**。`to_intervention_effects(command, *, base_revision,
  intervention_record_id)`；`apply_development_command` 增 host 参数
  `intervention_record_id`（空/非 trc_ 词法 → schema_invalid）；record_id 不消费
  冻结 `new_trace_record_id()`（uuid4 工厂，K7 冲突）；command_id 保持不透明
  host 标识（仍作 `causal_root_id` 与 branch causal 锚点，DEV-P8-3 不动）。
- 理由：对齐冻结 D-P2-20 语义（cause ref 指向真实审计载体）；因果链（G8-7）
  effect → cause ref → dev_intervention 记录 → payload.command 完整闭环；R1 probe
  实证 (a) 旧面（ref_id="dev-patch-1"）VALIDATION bad_id_kind → committed=0，
  (b) 面 commit 绿。
- 机械验证面：A9/A13 + §6.4 字面量钉死（command_id "dev-patch-1" / record_id
  "trc_00000000000000000000000000000042"）+ test_intervention cause_ids 断言。

**D-P8-18（自裁）pydantic 导入面 = 3 名窄例外（ContractModel 基础设施）**
- 问题：§3.0 导入闭集禁止列 catch-all「其余全部 stdlib/三方」与 §3.2 的
  `model_validator`（L453）/ `ValidationError → schema_invalid`（L477）机制处方
  互斥；且 45 个冻结 P1–P7 src 模块全部直接 import pydantic（core 27 / content 3 /
  dynamics 2 / llm 7 / plugins 3 / prompts 3，grep 实证）——S2 双口径。
- 备选：(a) 严守 catch-all（P8 src 零 pydantic 导入；镜像校验 = 工厂级检查 +
  裸 `ValueError` 捕获——损失错误保真且异于全代码库模式）；(b) pydantic 窄例外
  （仅 `Field` / `model_validator` / `ValidationError` 3 名，与冻结 core 同款）。
- 选择：**(b)**。§3.0 允许列增独立行 + 禁止列 catch-all 括注例外。
- 理由：§3.2 机制处方 = W0 三轮 12 评审已过的字节在位文本；P8 信封 =
  `ContractModel` 子类，pydantic = 项目唯一建模基础设施（零新依赖，uv.lock 不动）；
  机械可验证面保持闭集（边界方法 1 允许面 = §3.0 允许列，现含 3 名例外）。
- 机械验证面：W1 实现在位（snapshot.py / filesystem.py 导入面 == 3 名）；边界
  方法 1（W5，允许面含 pydantic 3 名）；ruff。

---

## §5 场景与 A 判据

### 5.1 基础场景（conftest 钉死，§6.2/6.4）

- **SC-1 结构 scripted world**（持久化 + devtools 两侧 conftest 各构一份，
  §6.2 重复口径）：初始 `WorldState` = 2 entity（`ent_a`/`ent_b`，确定性 id）+
  world variable `{"score": 0}`；scripted 3 回合（全结构效果，零推理侧消费）：
  回 1 `patch_state` world_variable `score→1`（devtools.developer，INTERVENTION
  cause）；回 2 测试侧 rule producer `p8.rule` 对 `ent_a` `core.set_component`；
  回 3 `inject_event`（通用包裹：`core.set_world_variable` `score→2`）。
  ⇒ committed 事务 3 笔、`world_revision` 0→3、events 3 条、trace 含
  command/authority/validation/transaction/domain_event/dev_intervention 族。
- **SC-2 P7 动力学 flavor save**（persistence conftest；复用 §2.7 冻结测试侧缝）：
  P7 gate 同形接线（`make_p7_world`/`make_p7_executor`/`gem_effect_handlers`/
  `FakeInferenceBackend(script={("world_dynamics", Revision(0), 1): …})` +
  `run_dynamics_turn`）⇒ trace 含 `gem.moved` 语义 effect + llm_call 记录；
  registry 绑 `ToyRigidDynamics`（checkpointable=True）。
- **SC-3 non-checkpointable world**：SC-1 的 world + `runtime_state.backend_refs`
  含一条 `checkpointable=False` 的 `BackendStateRef`（G8-4 负样本）。
- **SC-4 corruption 变体**（AD 族，§6.3）：对已存 save 做字节级破坏
  （截断 / 类型篡改 / 版本降级 / 中间行垃圾 / 索引悬空 / 目录缺失）。

### 5.2 A 判据（A1–A22；每条 ↔ 恰好 1 个扁平测试函数，§5.3）

| A | 门禁 | 判据（可执行语义） |
|---|---|---|
| A1 | G8-1 | SC-1 save → `FilesystemPersistenceBackend.load` → `SaveBundle.envelope.snapshot.world_state` 与 save 前 `WorldState` 的 `model_dump(mode="json")` **逐键相等**（含 `world_revision`） |
| A2 | G8-1 | 篡改 save 文本（`contract_schema_version` → 999）→ `load` 抛 `PersistenceError`，`code == "version_mismatch"`；message 非空 |
| A3 | G8-2 | SC-1：`replay_committed(初始 state, trace)` 终态 `model_dump(mode="json")` == 活管道终态同面相等 |
| A4 | G8-2 | SC-2（语义 flavor）：replay 双跑，两次 `ReplayResult.final_state.model_dump(mode="json")` **字节一致**（`json.dumps` 全量文本相等） |
| A5 | G8-3 | SC-1：branch A/B 后——改 A 的 world_variable + B 的 entity 组件 → 双方互不影响（dump 对比 source 与对方） |
| A6 | G8-3 | branch 结果：`handle.world_instance_id == 新 id`；`check_snapshot_versions`（branch 内部构造的信封）空；`handle.world_state.world_revision == source.world_revision`（不 bump） |
| A7 | G8-4 | SC-3：默认 `branch_world` → `BranchError`，`code == "branch_rejected"`，`str(exc)` 含该 backend_id |
| A8 | G8-5 | SC-1 回 1 后：trace 中 `kind == DEV_INTERVENTION` 恰 1 条（producer = `devtools.developer`）；对应 committed 事务 `provenance.origin is OriginKind.DEVELOPER` |
| A9 | G8-5 | `patch_state` 后：`world_revision` +1；`CommittedEffect.source == "devtools.developer"`；`cause_ids` 含 `CauseRef(INTERVENTION, intervention_record_id)`（该命令 DEV_INTERVENTION 记录 record_id；冻结 `_CAUSE_REF_EXPECTED_KIND` INTERVENTION → TraceRecordId 词法，D-P8-17） |
| A10 | G8-6 | 5 子命令对有效 save 全跑：输出可 `json.loads`；顶层键集恒 `{"tool","schema_version","command","ok","data","error"}`；`tool == "llmsim-devcontrol"`；`schema_version == 1` |
| A11 | G8-6 | 错误路径（未知 save / 未知子命令 / non-checkpointable branch）：`ok == false`；`error.code` ∈ `P8_ERROR_CODES`；进程正常返回（返回码 ∈ {1,2}，无未捕获异常） |
| A12 | G8-7 | SC-1 回 2 的 event：`causal_chain` → `transaction` 非 None；`effects` 非空且每个 `effect.effect.source` ∈ `producers`；`producers` 含 `p8.rule` |
| A13 | G8-7 | SC-1 回 1 的 event：chain `intervention_refs == (intervention_record_id,)`；含 PROPOSAL/ACTION cause 的 event → `action_refs` 含对应 ref_id |
| A14 | 补充 | 预置 `<snapshot.json>.tmp` 垃圾文件 → `save` 成功 → `load` 正常（旧文件完好，tmp 不残留） |
| A15 | 补充（AD） | `snapshot.json` 截断 40% → `load` 抛 `PersistenceError`，`code == "corrupt_file"` |
| A16 | 补充（AD） | 删除 trace 中间一笔事务记录 → replay 抛 `ReplayError`，message 含两侧 revision |
| A17 | 补充（AD） | toy checkpoint 体 `{"version":1,"seed":"not_int"}` → `registry.restore` 抛 `CheckpointError` |
| A18 | 补充 | `source_project_version="1.0"` / `target_project_version="2.0"` → `BranchError`；message 含 `"project_compatibility"` |
| A19 | 补充 | `DevelopmentCommand(kind="teleport", …)` → `InterventionError`，`code == "usage_error"` |
| A20 | 补充 | 5 子命令全部 stdout 过 `assert_json_clean`（解析后） |
| A21 | 补充 | 注入 ABORTED 事务记录（合法构造）→ replay 不应用、revision 不跳、`transactions_applied` 不含之 |
| A22 | 补充 | branch 后改 **branch 侧** state → source handle 的 state dump 不变（双向零别名的 branch→source 方向） |

### 5.3 A ↔ 测试函数 1:1 映射（22 ↔ 22）

| A | 测试函数（文件::函数） |
|---|---|
| A1 | `test_g8_scenarios.py::test_g8_1_save_load_same_world_state` |
| A2 | `test_g8_scenarios.py::test_g8_1_version_mismatch_explicit` |
| A3 | `test_g8_scenarios.py::test_g8_2_replay_same_committed_state` |
| A4 | `test_g8_scenarios.py::test_g8_2_replay_double_run_byte_identical` |
| A5 | `test_g8_scenarios.py::test_g8_3_branch_ab_independent` |
| A6 | `test_g8_scenarios.py::test_g8_3_branch_envelope_identity` |
| A7 | `test_g8_scenarios.py::test_g8_4_noncheckpointable_explicit_reject` |
| A8 | `test_g8_scenarios.py::test_g8_5_dev_intervention_trace_distinguishable` |
| A9 | `test_g8_scenarios.py::test_g8_5_patch_state_normal_commit_pipeline` |
| A10 | `test_g8_scenarios.py::test_g8_6_cli_envelope_schema_stable` |
| A11 | `test_g8_scenarios.py::test_g8_6_cli_error_closed_set` |
| A12 | `test_g8_scenarios.py::test_g8_7_causal_chain_event_to_producer` |
| A13 | `test_trace_query.py::test_causal_chain_includes_action_intervention_refs` |
| A14 | `test_filesystem_backend.py::test_atomic_write_corrupt_tmp_keeps_existing` |
| A15 | `test_p8_adversarial.py::test_ad1_truncated_snapshot_json` |
| A16 | `test_p8_adversarial.py::test_ad4_replay_middle_transaction_missing` |
| A17 | `test_p8_adversarial.py::test_ad2_checkpoint_seed_type_corrupt` |
| A18 | `test_branch.py::test_branch_project_compat_mismatch` |
| A19 | `test_intervention.py::test_command_unknown_kind_rejected` |
| A20 | `test_cli.py::test_cli_output_json_clean` |
| A21 | `test_replay.py::test_replay_skips_aborted_transactions` |
| A22 | `test_branch.py::test_branch_zero_alias_bidirectional` |

> 非 A 承载的扁平函数（123 − 22 = 101）= 模块面/构造/校验/闭集/AST 纪律测试，
> 逐函数列表见 §6.1；无测试类、无 subprocess、无跨函数状态（P7 §6.1 同族纪律）。

---

## §6 测试计划

### 6.1 扁平函数清单（123；每文件 = 模块级 `def test_*`，零 class / 零 subprocess）

**`tests/engine_v2/persistence/test_snapshot_format.py`（12）**

| # | 函数 | 面 |
|---|---|---|
| t1 | `test_envelope_defaults_version_surface` | 默认值面（`persistence_format_version==1`、`backend_checkpoints=={}`、`trace_ref is None`） |
| t2 | `test_envelope_redundant_versions_match_nested` | 冗余镜像一致性（正样本构造） |
| t3 | `test_envelope_redundant_versions_mismatch_raises` | 镜像失配 → `schema_invalid`（P8-INV-10） |
| t4 | `test_dump_load_roundtrip_json_clean` | dump/load roundtrip 相等 + JSON-clean |
| t5 | `test_load_unknown_field_rejected` | extra 字段 → `schema_invalid`（extra="forbid"） |
| t6 | `test_load_version_zero_rejected` | `persistence_format_version=0` → `version_mismatch` |
| t7 | `test_check_persistence_versions_consistent` | 好信封 → 空元组 |
| t8 | `test_check_persistence_versions_reports_nested_mismatch` | 嵌套版本篡改 → 非空 issues |
| t9 | `test_to_persistence_snapshot_zero_alias` | 输入 `Snapshot` 后置修改不影响信封（零别名） |
| t10 | `test_envelope_frozen` | 改字段 → 异常（frozen） |
| t11 | `test_backend_checkpoints_map_surface` | 非空 map：JSON-clean + ref 相对路径面 |
| t12 | `test_persistence_format_version_closed` | `PERSISTENCE_FORMAT_VERSION == 1` + `P8_ERROR_CODES` 11 码闭集 == 字面量（§3.1） |

**`tests/engine_v2/persistence/test_filesystem_backend.py`（14）**

| # | 函数 | 面 |
|---|---|---|
| t1 | `test_save_creates_closed_layout` | 目录闭集（`PERSISTENCE_SAVE_FILES` + index） |
| t2 | `test_save_load_roundtrip_bundle_equal` | `SaveBundle` envelope 相等 |
| t3 | `test_save_id_lexical_validation` | 非法 id 3 例 → `schema_invalid` |
| t4 | `test_atomic_write_replace_on_success` | 同 id 二次 save = 整体覆盖，load 有效 |
| t5 | `test_atomic_write_corrupt_tmp_keeps_existing` | **A14** |
| t6 | `test_list_saves_sorted_deterministic` | b/a/c save → `("a","b","c")` |
| t7 | `test_load_missing_save_explicit` | 未知 id → `save_not_found` |
| t8 | `test_corrupt_snapshot_file_explicit` | 手写垃圾 snapshot.json → `corrupt_file` |
| t9 | `test_trace_jsonl_order_preserved` | 5 记录保序 |
| t10 | `test_trace_jsonl_bad_line_explicit` | 第 2 行垃圾 → `corrupt_file` + message 含行号 |
| t11 | `test_checkpoint_files_roundtrip` | 2 backend 体 roundtrip 相等 |
| t12 | `test_save_dirty_dir_layout_violation` | 闭集外文件 → `layout_violation` |
| t13 | `test_save_directory_byte_deterministic` | 固定 wall time 双 save → snapshot.json/trace.jsonl/index 条目字节一致 |
| t14 | `test_backend_protocol_method_surface` | 3 方法签名面（Protocol 结构校验） |

**`tests/engine_v2/persistence/test_replay.py`（13）**

| # | 函数 | 面 |
|---|---|---|
| t1 | `test_replay_reconstructs_committed_state` | SC-1 结构 replay 终态相等 |
| t2 | `test_replay_dynamics_flavor_semantic_handler` | SC-2：注入 P7 `gem_effect_handlers()`（测试侧）→ 语义 replay 终态相等（**D-P7-13 评估锚**） |
| t3 | `test_replay_skips_aborted_transactions` | **A21** |
| t4 | `test_replay_empty_trace_noop` | 空 trace → 原样、计数 0 |
| t5 | `test_replay_base_revision_mismatch_raises` | 首笔 base ≠ 当前 → `ReplayError` |
| t6 | `test_replay_duplicate_revision_raises` | 同 commit_revision 两笔 → `ReplayError` |
| t7 | `test_replay_unknown_effect_type_raises` | 未注册语义型（registry 未注册）→ `ReplayError`（wrap `ReducerError`） |
| t8 | `test_replay_events_reconstructed_ordered` | `result.events` ids/序 == 管道 events |
| t9 | `test_replay_ignores_non_transaction_kinds` | 非 TRANSACTION 记录不驱动状态 |
| t10 | `test_replay_result_to_dict_json_clean` | `to_dict` JSON-clean |
| t11 | `test_replay_result_fields_exact` | 字段名闭集（6 字段 + `to_dict`） |
| t12 | `test_replay_zero_io_ast` | `replay.py` AST：无 `open`/`os`/`pathlib`（D4） |
| t13 | `test_replay_base_state_untouched` | 输入 state replay 后 dump 不变（零别名） |

**`tests/engine_v2/persistence/test_checkpoint_registry.py`（11）**

| # | 函数 | 面 |
|---|---|---|
| t1 | `test_register_and_metadata_binding` | 绑定面 + 重复拒绝前置 |
| t2 | `test_checkpoint_all_returns_snapshots` | 2 backend（toy + stub non-checkpointable）→ 2 快照；后者 `checkpoint is None`（降级可见） |
| t3 | `test_checkpoint_all_payload_json_clean` | toy 体 `{"version":1,"seed":N}` JSON-clean |
| t4 | `test_restore_delegates_and_returns_new_instance` | restore → 新实例（`is not` 原实例） |
| t5 | `test_restore_unknown_backend_raises` | 未知 id → `checkpoint_unavailable` |
| t6 | `test_restore_corrupt_payload_raises` | 坏类型体 → `CheckpointError` |
| t7 | `test_validate_refs_consistent` | 一致 → 空 issues |
| t8 | `test_validate_refs_unknown_ref_reported` | 未知 ref → 非空 |
| t9 | `test_validate_refs_capability_mismatch_reported` | 声明漂移 → 非空 |
| t10 | `test_register_duplicate_rejected` | 重复 id → `CheckpointError` |
| t11 | `test_register_capability_inconsistency_rejected` | 声明/能力不符 → `schema_invalid` |

**`tests/engine_v2/persistence/test_branch.py`（13）**

| # | 函数 | 面 |
|---|---|---|
| t1 | `test_branch_independence_matrix` | A5 深化：world_variable/组件 4 象限交叉修改 |
| t2 | `test_branch_zero_alias_bidirectional` | **A22** |
| t3 | `test_branch_project_compat_mismatch` | **A18** |
| t4 | `test_branch_module_version_conflict` | 共有键值冲突 → `BranchError` |
| t5 | `test_branch_version_check_failure` | 构造坏 `WorldState.schema_version` → `BranchError(version_mismatch)` |
| t6 | `test_branch_default_reject_message_naming_backend` | A7 深化：message 点名 + code 断言 |
| t7 | `test_branch_degraded_opt_in_records` | `allow_degraded=True` → `degraded_backends` 点名 + 无异常 |
| t8 | `test_branch_checkpoint_payload_required` | 缺 payload → `BranchError` |
| t9 | `test_branch_checkpoint_payload_non_dict_rejected` | payload 非 dict → `schema_invalid` |
| t10 | `test_branch_checks_closed_set` | `BRANCH_CHECKS ==` Spec §30.5 三元组（snake_case 归一） |
| t11 | `test_handle_frozen_and_json_clean` | frozen + `to_dict` clean |
| t12 | `test_branch_empty_backend_refs_ok` | 无 backend_refs → 成功、degraded 空 |
| t13 | `test_branch_new_id_validation` | `""`/`" "` → `schema_invalid` |

**`tests/engine_v2/persistence/test_p8_adversarial.py`（10；T09 三族）**

| # | 函数 | 族 |
|---|---|---|
| t1 | `test_ad1_truncated_snapshot_json` | **A15**；corruption |
| t2 | `test_ad2_checkpoint_seed_type_corrupt` | **A17**；corruption |
| t3 | `test_ad3_version_downgrade_envelope` | corruption：`persistence_format_version` 0/999 → `version_mismatch` |
| t4 | `test_ad4_replay_middle_transaction_missing` | **A16**；replay：中间事务缺失 → 连续性断裂 |
| t5 | `test_ad5_replay_unregistered_semantic_effect` | replay：SC-2 trace + 纯结构 registry → `ReplayError`（不静默） |
| t6 | `test_ad6_branch_degraded_not_silent` | branch：degraded 开关 → 结果面点名（非静默） |
| t7 | `test_ad7_branch_checkpoint_payload_non_mapping` | branch：标量 payload → `schema_invalid` |
| t8 | `test_ad8_trace_jsonl_mid_corrupt` | corruption：第 3 行垃圾 → `read_trace_records` 显式（行号） |
| t9 | `test_ad9_index_points_missing_dir` | corruption：索引悬空（目录删）→ `save_not_found` |
| t10 | `test_ad10_branch_of_branch_independent` | branch：branch-of-branch 三方独立（base/A/B） |

**`tests/engine_v2/devtools/test_intervention.py`（12）**

| # | 函数 | 面 |
|---|---|---|
| t1 | `test_command_closed_set_matches_spec` | 6 种 == Spec §22 字面量 + 三子集 partition 断言 |
| t2 | `test_command_unknown_kind_rejected` | **A19** |
| t3 | `test_command_payload_must_be_json_clean` | payload 含非 JSON 值 → `schema_invalid` |
| t4 | `test_command_id_host_given` | 空/纯空白 id → `schema_invalid` |
| t5 | `test_patch_state_component_commit` | 组件 patch：revision +1、组件落位、结构 handler 路径（零测试侧语义 handler 依赖） |
| t6 | `test_inject_event_wraps_proposed_effect` | 包裹面：source/cause_ids/base_revision 字段断言 |
| t7 | `test_intervention_origin_developer_fields` | 事务 `provenance` 字段级（A8 深化） |
| t8 | `test_pause_step_runtime_directive_no_state_change` | 2 指令面 + state dump 不变 |
| t9 | `test_force_wake_directive_surface` | 指令含 entity_id；缺 key → `usage_error` |
| t10 | `test_branch_command_instance_level` | `branch` kind：无世界变更 + `("branch",)` 指令（DEV-P8-3） |
| t11 | `test_result_to_dict_json_clean` | 4 族 `InterventionResult.to_dict` clean |
| t12 | `test_producer_id_fullmatch_pattern` | `DEVTOOLS_DEVELOPER_PRODUCER` fullmatch 冻结 pattern |

**`tests/engine_v2/devtools/test_trace_query.py`（12）**

| # | 函数 | 面 |
|---|---|---|
| t1 | `test_query_records_preserve_input_order` | 输入序保持 |
| t2 | `test_by_kind_projection` | kind 投影计数 |
| t3 | `test_domain_events_parsed` | 解析字段与源一致 |
| t4 | `test_transactions_and_committed_projection` | 全量/COMMITTED 子集 |
| t5 | `test_authority_decisions_rows` | 行面 4 键 + payload dict |
| t6 | `test_producer_activity` | `by_producer("p8.rule")` |
| t7 | `test_revision_timeline_rows` | 行/升序/计数面 |
| t8 | `test_intervention_history_surface` | 仅 `DEV_INTERVENTION` |
| t9 | `test_causal_chain_with_proposal_cause` | PROPOSAL cause → `action_refs` |
| t10 | `test_causal_chain_includes_action_intervention_refs` | **A13** |
| t11 | `test_causal_chain_unknown_event_raises` | 未知 id → `TraceQueryError` |
| t12 | `test_chain_surface_clean_and_zero_io` | `CausalChain.to_dict` clean + `trace_query.py` 零 IO AST（D4） |

**`tests/engine_v2/devtools/test_cli.py`（14）**

| # | 函数 | 面 |
|---|---|---|
| t1 | `test_cli_five_commands_run_ok` | 5 命令全跑 `ok=true`（A10 深化） |
| t2 | `test_envelope_keys_exact_set` | 顶层键集 == 6 键字面量（闭集） |
| t3 | `test_inspect_data_surface` | §37 快照派生 4 项面（world/runtime/scheduler_queue/active_actions） |
| t4 | `test_trace_filter_by_kind` | `--kind` 过滤 + 非法 kind → `usage_error` |
| t5 | `test_replay_final_state_matches` | CLI replay 终态 == inspect 快照态（SC-1） |
| t6 | `test_branch_reject_error_envelope` | SC-3 → `ok=false` + `branch_rejected` + 返回码 1 |
| t7 | `test_test_command_report` | `test` 命令：checks 行名闭集 5 + `replay_consistency` 行 `ok=true` |
| t8 | `test_cli_output_json_clean` | **A20** |
| t9 | `test_schema_version_constant` | 常量 == 1 + `CLI_COMMANDS` 5 元组字面量 |
| t10 | `test_usage_error_code` | 无/未知子命令 → `usage_error` + 返回码 2 |
| t11 | `test_save_not_found_code` | 未知 save → `save_not_found` + 返回码 1 |
| t12 | `test_exit_codes_ok_zero` | 成功路径返回码 0 |
| t13 | `test_json_flag_accepted_noop` | 有无 `--json` 信封逐字节一致 |
| t14 | `test_cli_zero_asyncio_ast` | `cli.py` + 脚本 AST：零 `asyncio`/`socket`/`subprocess`（D4/D1） |

**`tests/engine_v2/devtools/test_g8_scenarios.py`（12）**

| # | 函数 | A |
|---|---|---|
| t1 | `test_g8_1_save_load_same_world_state` | A1 |
| t2 | `test_g8_1_version_mismatch_explicit` | A2 |
| t3 | `test_g8_2_replay_same_committed_state` | A3 |
| t4 | `test_g8_2_replay_double_run_byte_identical` | A4 |
| t5 | `test_g8_3_branch_ab_independent` | A5 |
| t6 | `test_g8_3_branch_envelope_identity` | A6 |
| t7 | `test_g8_4_noncheckpointable_explicit_reject` | A7 |
| t8 | `test_g8_5_dev_intervention_trace_distinguishable` | A8 |
| t9 | `test_g8_5_patch_state_normal_commit_pipeline` | A9 |
| t10 | `test_g8_6_cli_envelope_schema_stable` | A10 |
| t11 | `test_g8_6_cli_error_closed_set` | A11 |
| t12 | `test_g8_7_causal_chain_event_to_producer` | A12 |

**合计**：12+14+13+11+13+10 + 12+12+14+12 = **123**（零测试类、零 subprocess）。

### 6.2 conftest 设计（2 个 conftest；零新增 fixture 文件）

**`tests/engine_v2/persistence/conftest.py`**：

| 构件 | 契约 |
|---|---|
| `@pytest.fixture(autouse=True) _barrier_isolation` | 写屏障 opt-in 纪律（P7 gate L113–118 同形）：前后各 `uninstall_write_barrier()` |
| `make_p8_world()` | SC-1 初始 `WorldState`（2 entity + `score` 变量；确定性 id，`_det_entity_id` 同族自构） |
| `make_p8_runtime(backend_refs=())` | `RuntimeState`（`lifecycle=STEPPING` 语义不强制；`backend_refs` 参数化——SC-3 注入 non-checkpointable ref） |
| `make_p8_policy()` / `make_p8_executor()` | 测试侧 authority policy：放行 `devtools.developer` + `p8.rule`（`AuthorityPolicy`/`AuthorityRule`/`AuthoritySelector`，同 P7 gate L131–146 模式）；`CascadeExecutor(policy=…, handlers=default_handler_registry(), component_registry=…)` |
| `run_p8_script()` | SC-1 3 回合脚本（§5.1）→ `P8RunBundle(final_state, runtime_state, trace_records, dev_command_ids, rule_producer_id)`（模块级 dataclass，conftest 私有） |
| `make_p8_backend(tmp_path)` | `FilesystemPersistenceBackend(tmp_path / "saves_root")` |
| `build_p8_save(tmp_path, run)` | SC-1 → 完整 save（`save_id="save_p8_base"`；wall time 固定串 `"1970-01-01T00:00:00+00:00"`——D6） |
| `build_p8_dynamics_save(tmp_path)` | **SC-2**：函数内 lazy import `from tests.engine_v2.dynamics.conftest import _det_entity_id, make_p7_executor, make_p7_world`（§2.7 冻结缝；`gem_effect_handlers` 在冻结 `make_p7_executor` 体内注册，dynamics/conftest.py:159）+ `FakeInferenceBackend(script=…)` + `run_dynamics_turn(executor=make_p7_executor(), …)` → save（`save_id="save_p8_dyn"`）+ registry（toy 绑定） |
| `corrupt_save(save_dir, kind)` | SC-4 破坏函数（`"truncate_snapshot"` / `"bad_checkpoint_seed"` / `"version_zero"` / `"drop_middle_txn"` / `"bad_trace_line"` / `"dangling_index"`）——AD 族共用 |

**`tests/engine_v2/devtools/conftest.py`**：自包含**紧凑版** SC-1 构件
（`make_p8_world`/`make_p8_executor`/`run_p8_script`/`build_p8_save` 同契约，
零 P7 依赖——devtools CLI 面只需结构 save）+ `SC-3` 变体 + `cli_runner(tmp_path)`
（返回 `argv → (stdout, exit_code)` 助手：`run_devcontrol_cli(argv, base_dir=…)`
捕获 stdout）。

> **重复口径**（§6.2 明示）：结构 save 紧凑 builder 在两侧 conftest 各一份
> （约 40 行测试侧重复）；P7 动力学 flavor 构件**只**在 persistence 侧
> （经冻结测试侧缝复用，零复制）。重复 = 测试局部决策，src 面零影响；
> 保持测试包间零导入图（P6 llm/prompts 双 conftest 先例）。

### 6.3 AD 对抗族（T09；一函数一破坏，10 个）

AD-1..AD-10 = `test_p8_adversarial.py` t1–t10（§6.1 表；族 = corruption 5
[AD-1/2/3/8/9] + replay 2 [AD-4/5] + branch 3 [AD-6/7/10]）。纪律（P7 AD 同族）：
每函数**独立 save 生命周期**（tmp_path 隔离）、破坏后**只断言异常面**
（类型 + code + message 关键词，不吞 traceback）、零静默路径断言
（"未抛异常" = 测试失败）。G8-4 在 CLI 面的 fail-loud 由 `test_cli.py::
test_branch_reject_error_envelope` 独立承载（非 AD 编号，避免 1:1 歧义）。

### 6.4 fixture 钉死面（零新增 fixture 文件）

| 项 | 钉死 |
|---|---|
| 新增 fixture 文件 | **零**（白名单 25 文件不含 `tests/fixtures/` 任何路径） |
| 复用既有 | `tests/fixtures/v2_deployment_p7/deployment.yaml`、`tests/fixtures/v2_project_p7/game.yaml`（路径 = P7 SOT §6.4 已钉；SC-2 消费） |
| SC-1 世界 | 由 conftest 确定性构造（§5.1）；entity id / producer id / command_id / save_id / wall time 全部**字面量**（`"ent_a"`/`"ent_b"`/`"p8.rule"`/`"dev-patch-1"`/`"trc_00000000000000000000000000000042"`（record_id 字面量；与 command_id 并存——command_id 不透明标识、record_id = cause ref 目标）…/`"save_p8_base"`/`"1970-01-01T00:00:00+00:00"`）——无随机、无时钟 |
| SC-2 脚本 | `FakeInferenceBackend` script 键 = `("world_dynamics", Revision(0), 1)`（lookup 面，`llm/adapter.py:300/333` 冻结）；响应串 = 字面量（P7 gate `scripted_wire_response` 同族） |
| 推理侧词汇 | fixture/deployment yaml 内的推理侧配置字段 = P7 既有 fixture 内容（零改动）；P8 测试**代码**字符串面受 D2 扫描（yaml 文件不在扫描面——与 P7 同口径：扫描限 src 模块 + 脚本） |

---

## §7 映射表

### 7.1 任务 → 模块 → 测试 → A

| 任务 | 模块（白名单 #） | 测试文件（函数数） | 承载 A |
|---|---|---|---|
| T01 | `base.py`（#1）+ `snapshot.py`（#2） | `test_snapshot_format.py`（12） | A2（经 g8） |
| T02 | `filesystem.py`（#3） | `test_filesystem_backend.py`（14） | A1/A14/A15（经 g8/AD） |
| T03 | `replay.py`（#4） | `test_replay.py`（13） | A3/A4/A16/A21（经 g8/AD） |
| T04 | `checkpoint.py`（#5） | `test_checkpoint_registry.py`（11） | A17（经 AD） |
| T05 | `branch.py`（#6） | `test_branch.py`（13） | A5–A7/A18/A22（经 g8） |
| T06 | `intervention.py`（#7） | `test_intervention.py`（12） | A8/A9/A19（经 g8） |
| T07 | `trace_query.py`（#8） | `test_trace_query.py`（12） | A12/A13（经 g8） |
| T08 | `cli.py`（#9）+ `scripts/v2_devcontrol.py`（#10） | `test_cli.py`（14） | A10/A11/A20（经 g8） |
| T09 | —（测试波） | `test_p8_adversarial.py`（10）+ `test_g8_scenarios.py`（12）+ 边界块（#25） | 全 22 A 的门禁承载在 g8 12 函数 |

### 7.2 G8 七项 → A → 函数 → 模块（§0.2 的回查表）

| G8 项 | A | 测试函数 | 主要模块 |
|---|---|---|---|
| 1 snapshot→load→same WorldState | A1, A2 | g8 t1, t2 | `snapshot.py` + `filesystem.py` |
| 2 event replay→same committed state | A3, A4 | g8 t3, t4 | `replay.py` |
| 3 branch A/B 独立 | A5, A6 | g8 t5, t6 | `branch.py` |
| 4 non-checkpointable 明确拒绝 | A7 | g8 t7 | `branch.py` |
| 5 intervention trace 可区分 | A8, A9 | g8 t8, t9 | `intervention.py` |
| 6 CLI JSON schema 稳定 | A10, A11 | g8 t10, t11 | `cli.py` |
| 7 causal chain 回溯 | A12（+A13） | g8 t12（+ trace_query t10） | `trace_query.py` |

---

## §8 机械检查面

### 8.1 K1–K8 矩阵（P8 触点）

> 标签 = Spec 逐字（P7 §8.1 先例）：K1「单一 authoritative state」L246 / K2「禁止直接状态写入」L252 /
> K3「Authority 与 Commit 分离」L285 / K4「Prompt 不能定义世界权限」L295 /
> K5「Agent 是 Policy，不是 Engine」L305 / K6「Event 必须可追踪来源」L315 /
> K7「Runtime 内部关键调度状态必须可检查」L326 / K8「Deployment 与 Game Project 分离」L330。

| K | P8 触点 | 验证面 |
|---|---|---|
| K1 WorldState 唯一权威 | 信封 = 冻结 `Snapshot`（状态唯一容器）；replay 重构**同一**状态面，零第二状态源；branch = 新实例同面 | A1/A3/A5；§3.2/§3.4 |
| K2 零状态直写 | intervention → `ProposedEffect → CascadeExecutor.run`；replay → `apply_transaction`（唯一变更路径 `core/reducer.py:974`）；devtools 对 RuntimeState 仅 directive | A9；P8-INV-4；t13（replay 零别名） |
| K3 authority/commit 分离 | `devtools.developer` 经正常 authority（closed-by-default；测试侧 policy 显式放行）；干预无特权通道 | t7（origin 字段）；§3.7 K2/K3 面 |
| K4 提示词面 | 无触点（P8 不产出提示词；CLI 输出非提示词） | — |
| K5 agent 面 | 无触点（devtools = 开发者工具，非 agent 决策者） | — |
| K6 provenance | intervention 三重标记 = 冻结面（`OriginKind.DEVELOPER` L54 / `CauseKind.INTERVENTION` L94 / `TraceKind.DEV_INTERVENTION` L109）；因果链回溯全链路 | A8/A12/A13 |
| K7 可检查性 | T08 `inspect` 暴露 RuntimeState 调度面 = `scheduler_queue`/`active_actions`（分配面 L785–787；冻结 `core/state.py:220–221` 字段） | A2/inspect 场景；扩展面（确定性）= D-P8-12（四面对双跑字节一致） |
| K8 推理侧 12 名 | P8 src 字符串字面量面零命中（D2 口径）；持久化声明 = 模块导出 + host 注入，项目零 `.py` 消费 | 边界方法 3（负探针内置）；D-P8-15 |

### 8.2 导出台账（`P8_EXPORT_LEDGER`；边界方法 6 双相等锚）

| 模块 | `__all__`（封闭） | 计数 |
|---|---|---|
| `persistence/base.py` | `PERSISTENCE_FORMAT_VERSION`, `PERSISTENCE_SAVE_FILES`, `SAVE_ID_PATTERN`, `P8_ERROR_CODES`, `PersistenceError`, `PersistenceBackend`, `SaveBundle` | 7 |
| `persistence/snapshot.py` | `PersistenceSnapshot`, `to_persistence_snapshot`, `dump_persistence_snapshot`, `load_persistence_snapshot`, `check_persistence_versions` | 5 |
| `persistence/filesystem.py` | `FilesystemPersistenceBackend`, `read_trace_records` | 2 |
| `persistence/replay.py` | `ReplayResult`, `ReplayError`, `replay_committed` | 3 |
| `persistence/checkpoint.py` | `CheckpointError`, `CheckpointSnapshot`, `BackendCheckpointRegistry` | 3 |
| `persistence/branch.py` | `BRANCH_CHECKS`, `BranchError`, `WorldInstanceHandle`, `BranchResult`, `branch_world` | 5 |
| `devtools/intervention.py` | `DEVTOOLS_DEVELOPER_PRODUCER`, `DEVELOPMENT_COMMAND_KINDS`, `WORLD_MUTATING_KINDS`, `RUNTIME_CONTROL_KINDS`, `INSTANCE_LEVEL_KINDS`, `DevelopmentCommand`, `ExternalInterventionEffect`, `InterventionResult`, `InterventionError`, `to_intervention_effects`, `apply_development_command` | 11 |
| `devtools/trace_query.py` | `TraceQuery`, `CausalChain`, `TraceQueryError` | 3 |
| `devtools/cli.py` | `CLI_TOOL_NAME`, `DEVCONTROL_CLI_SCHEMA_VERSION`, `CLI_COMMANDS`, `build_cli_envelope`, `run_devcontrol_cli` | 5 |
| **合计** | | **44** |

`scripts/v2_devcontrol.py` 无 `__all__`（脚本非模块面；白名单内，台账外——
边界方法 6 只锚 9 模块）。

### 8.3 计数恒等式（门禁 ① 期望值）

```text
基线套件（84a5d4f 实测）            = 2925
P8 新增（§6.1 逐函数计数）           = 123
  persistence: 12+14+13+11+13+10     =  73
  devtools:    12+12+14+12           =  50
─────────────────────────────────────────────
gate1_expected                        = 3048
```

恒等式约束：`§6.1 函数总数 == 123 == W 波次表 Σ（26+24+25+26+22）==
A↔函数映射非 A 部分（101）+ A（22）`。实现波次若新增/删减测试函数，
**必须**同步更新本恒等式与报告 `counts`（W0 纪律，P7 §8.3 同族）。

### 8.4 偏离登记（DEV-P8-*）

| # | 偏离 | 性质 | 依据 |
|---|---|---|---|
| DEV-P8-1 | `persistence/base.py` 为 Spec §44 推荐文件（P8 用作错误族/Protocol/布局常量载体），非任务表显式文件 | 模块粒度决策（非偏离） | P7 先例 DEV-P7-2 同族 |
| DEV-P8-2 | Spec §44 推荐 `devtools/replay.py` + `devtools/branch.py`；P8 将 replay/branch 逻辑面置于 `persistence/`（零模块重复，CLI 复用） | 落位决策（非偏离） | §44 = 推荐；S2 单面 |
| DEV-P8-3 | Spec §22 六例之 `branch` 在命令闭集内，但其动作为实例级（= `branch_world` 控制面标记），无世界效果 | 语义澄清（非偏离） | Spec §22 L1262"如果开发命令改变世界："的条件句式 |
| DEV-P8-4 | Spec §30.2 第 4 项 "Event/Trace log"：P8 存**全** `TraceRecord` JSONL（超集覆盖 events） | 超集覆盖（非偏离） | 最低保证面（§30.4） |
| DEV-P8-5 | CLI `test` 子命令 = save 校验报告（validate+test 两义原型合一）；scenario test 引擎 = P8+ | 范围决策（非偏离） | D-P8-14；§0.4.3 |
| DEV-P8-6 | `snapshot()` 不在 core `__all__`（AST 实测 308 无此名）⇒ P8 经子模块 `src.engine_v2.core.snapshot` 导入 | 导入路径事实登记（非偏离；core 零变更） | §2.1 导入面注意 |

---

## §9 勘误（errata）

> 格式先例：ERR-P7-01..17 链。W0 阶段无实现勘误；以下为 **W0 设计勘误预备区**
> （任务书与本 SOT 的出入，实现波次引用时以本 SOT 为准）：

| # | 项 | 任务书口径 | 字节真值（@ `84a5d4f`） | 处置 |
|---|---|---|---|---|
| E-P8-01 | `OriginKind` 值数 | "8 值" | **7 值**（`core/provenance.py:41`，L49–55：BEHAVIOR_POLICY…DEVELOPER L54、SYSTEM L55） | 本 SOT 按 7 值；引用时点名 `OriginKind.DEVELOPER`（L54） |
| E-P8-02 | trace 查询 10 项清单归属 | "§38 区段 L1875–1886" | 实际 = **Spec §37 Runtime Inspector**（标题 L1869；12 项 SHOULD L1873–1884；10 项子清单 L1875–1884；§38 标题在 L1888） | 本 SOT §0.1/§3.8 按 §37 归属 |
| E-P8-03 | monotonic clock 归属 | 归 `core/clock.py` | `core/clock.py` = **逻辑时钟**（`LogicalClock` L77，世界逻辑时间）；monotonic clock Protocol 在 P6 `llm/adapter.py:47` | 本 SOT §2.1 双注；P8 两 clock 面均不消费（逻辑 tick = host 传入；monotonic = 推理侧面，P8 零触点） |

- **E-P8-04**（W0-R1 修订；4/4 评审 = 4 SUPPLEMENT、0 BLOCK，全 docs 面）：
  (1) Spec §22 行锚 ×9 重钉（L1254–1259/L1265–1267/L1273/L1262）；
  (2) loader 路径 3 处 core/→content/ + 路径口径补 content/ 行；
  (3) serialization 导出 5→4（L41–46）；(4) D-P8-08 补 branch/replay 逐项派生映射
  （S2 单选）；(5) Spec §44 区间 2 处 → L2100–2202（brief 称 3 处，磁盘实测 2 处，
  改后全文 0 命中）；(6) conftest pin ×2（def 行口径 L188/L200）；(7) P6 块区间
  3 处 def L1050/体 L1061–1093 + D2 标签归属；(8) ABORTED 注释归属 Spec §8.4 →
  core/trace.py:105；(9) 五段式补全（§4 头注记 + D-P8-12 备选行）；(10) §8.1 K 矩阵
  Spec 逐字标签 + K7 行改可检查性触点（确定性降扩展面；K7 行分配面自锚按插入后
  行号 L785–787 钉）；(11) **D-P8-17**（自裁）干预 cause ref = DEV_INTERVENTION
  记录 record_id（host 确定性 trc_ 字面量；冻结 new_trace_record_id uuid4 工厂不
  消费）——R1 probe 实证 + 冻结 D-P2-20 语义裁定；(12) D-P8-13..17 自裁标记备选豁免
  注记（13–16 备选段豁免；17 = 五段全在位；D-P8-12 未标记、五段全在位）。计数/白
  名单/账本零变化（gate1 期望仍 3048）。本条目按 §9 续编取 E-P8-04
  （brief 原文 E-P8-03 与既有条目 monotonic clock 行重号，P7 先例 = 严格递增）。

- **E-P8-05**（W0-R2 修订；R2 4/4 评审 = 3 PASS + 1 SUPPLEMENT，全 docs 面）：
  (1) D-P8-17 问题段 pin `core/validation.py:149–155` → `148–157`（D-P2-20 注释
  L148–150；dict L151–157，INTERVENTION 条目 L156——字节实证；4/4 评审同靶）；
  (2) E-P8-04(12) 自述修正 D-P8-12..16 → D-P8-13..17（V12 §9 自洽；13–16 备选段
  豁免、17 五段全在位、D-P8-12 未标记五段全在位）；
  (3) §0.1 标题「逐字对齐」→「逐项对齐 + P8 落位映射（能力列省略）」（9 行 ×
  ID/任务/属性/难度/上下文/默认模型 6 列逐项逐字，R2 逐行字节比对；能力列全行 =
  纯coding）；
  (4) Plan 目标锚 L729–731 → L731（目标句单行 L731）；
  (5) §6.1 t10「三元组字面量」→「三元组（snake_case 归一）」（Spec §30.5 = 自然
  语言三项）。计数/白名单/账本零变化（gate1 期望仍 3048）；本条目按 §9 续编取
  E-P8-05（严格递增）。

- **E-P8-06**（W0-R3 修订；R3 4/4 评审 = 4 PASS、0 SUPPLEMENT、0 BLOCK——设计
  收口轮；3 DOC 修正 + 2 INFO 不处置）：
  (1) E-P8-05(5) 自引 §6.4 → §6.1（t10 行物理位于 §6.1 扁平清单 L1314；3/4 评审
  同靶）；
  (2) `core/provenance.py:54` 注释引文 ×2（L127/L290）：ASCII 冒号 + 空格 → 全角
  冒号（byte 保真 1 字节修正，od 实证）；
  (3) DEV-P8-3 依据列（L1543）引文「若…改变世界」→「如果开发命令改变世界：」
  （Spec L1262 逐字；引号内改写瑕疵）。
  2 INFO 不处置：D-P8-17 问题段引文反引号面省略（V13 窗口正确）；§30.x 区间
  开-fence 口径（内部一致、覆盖全条目）。计数/白名单/账本零变化（gate1 期望仍
  3048）；本条目按 §9 续编取 E-P8-06（严格递增）。

- **ERR-P8-01**（W1 触发；D-P8-18 联动；W1 实现零改动）：
  触发文件:行：`src/engine_v2/persistence/snapshot.py:27`（W1 dev 偏差 #1 登记；
  `filesystem.py` 同款）；
  原口径：§3.0 导入闭集禁止列 catch-all「其余全部 stdlib/三方」与 §3.2 L453
  `model_validator` / L477 `ValidationError → schema_invalid` 机制处方互斥，且与
  45 个冻结 P1–P7 src 模块 pydantic 直接导入模式（core 27 / content 3 / dynamics 2 /
  llm 7 / plugins 3 / prompts 3，grep 实证）冲突——SOT 自洽缺陷（W0 三轮 12 评审
  未捕获：§3.0 表与 §3.2 处方分属不同审查面）；
  修正口径：§3.0 允许列增 `pydantic` 独立行（仅 3 名：`Field` / `model_validator` /
  `ValidationError`；ContractModel 基础设施面）+ 禁止列 catch-all 括注例外 +
  D-P8-18（自裁）登记（§4 头 D-P8-01..18）；
  影响面：边界方法 1 允许面口径（W5 实现 = §3.0 允许列，含 pydantic 3 名）；
  计数/白名单/账本零变化（26 / 2951 / 3048 不变）；W1 实现按修正口径已在位
  （dev 偏差 #1 溯及合法化，G8 报告 §6 登记）。

- **ERR-P8-02**（W1-R1 评审触发；SOT 3 处校准；实现零改动）：
  (1) §6.2 `build_p8_dynamics_save` 行 stale 注记：import 列 `gem_effect_handlers, …`
  + `load_deployment(v2_deployment_p7)` 子句 → 函数内 lazy import（`_det_entity_id` /
  `make_p7_executor` / `make_p7_world`，sed 实证 conftest L475–479）+
  `gem_effect_handlers` 在冻结 `make_p7_executor` 体内注册（dynamics/conftest.py:159）
  + 无 load_deployment 子句（W1-R1 r4-F1 DOC；行为面已实证达标：gem.moved
  committed + 9 键 LLM payload）；
  (2) §3.2 `dump_persistence_snapshot` 伪码 `dump_json(envelope.to_dict())` 不可实现
  （冻结 `dump_json` 仅收 BaseModel，core/serialization.py:54）→
  `assert_json_clean(envelope.to_dict()) + dump_json(envelope)`（与 W1 实现
  snapshot.py L139–140 字节一致；r4-F3 DOC）；
  (3) §3.1 追认事实契约面：`PersistenceError.__str__` = "[code] message" +
  `PersistenceBackend` = `@runtime_checkable Protocol`（isinstance 探针面，t14
  锚定；r3-F1 DOC）。计数/白名单/账本零变化（26 / 2951 / 3048 不变）。

- **ERR-P8-03**（W2-R1 评审触发；SOT 1 处补注；实现零改动）：
  触发文件:行：`src/engine_v2/persistence/checkpoint.py:191`（W2 dev 偏差 #4
  登记；W2-R1 4/4 评审独立同靶收敛——r1–r4 各 3 条 checkpoint.py L180/L186/
  L191 偏差条目（同靶 SOT L599 restore 行）+ r4 erratum 候选，均判 SOT
  沉默面而非交付违规，0 finding）；
  原口径：§3.5 L599 restore 行「版本类 → `version_mismatch`，形态类 →
  `schema_invalid`」未定判别机制（沉默面；4 评审偏差同靶 = 重复面，W5
  对抗族 AD-2 将触及）；
  修正口径：L599 补注判别最窄实现 = 实例侧异常 `str` casefold 含 `version`
  → 版本类，余 → 形态类（锚冻结 `dynamics/toy_rigid.py:150` 版本门消息面；
  W2 实现 checkpoint.py L191 已在位，零改动）；
  影响面：W5 AD-2（恢复失败显式）与 G8 场景判别面口径锚定；测试面 F01
  处置 = `test_replay.py` 4 处（7 调用点）`json.dumps` 补 `ensure_ascii=False`
  与仓库确定性序列化惯用法对齐（r4-F01 DOC；纯形式零行为变化，W2 波提交前
  修正，不计实质修复预算——ERR-P8-02 同族口径）；
  计数/白名单/账本零变化（24 / 2975 / 3048 不变）。

- **ERR-P8-04**（W4-R1 评审触发；SOT 6 处标注校准 + W4 预提交修正 2；W4-R1 两条
  SUPPLEMENT 发现处置）：
  触发 1 文件:行：`src/engine_v2/devtools/trace_query.py:32`（W4-R1 r2-F01
  SUPPLEMENT、C5 FAIL：`TransactionStatus` 导入非 §2.1 已列消费名——SOT 全文
  0 命中；§2.1 L295 core/transaction.py 行仅列 `Transaction`；§3.0 L398 明文
  「仅 §2.1 已列消费名」；W2 冻结先例 `persistence/replay.py` L171–172 刻意
  规避枚举并留显式注释）；
  修正 1（预提交，W2-F01 同族口径：SOT 明文对齐、零行为变化）：删导入 +
  `committed_transactions` = `commit_revision is not None` 不变量等价判定
  （Transaction 原子不变量：COMMITTED ⟺ commit_revision 非空，冻结
  `core/transaction.py` model_validator 双向强制）+ W2 先例同款注释；
  触发 2 文件:行：`src/engine_v2/devtools/cli.py:236`（W4-R1 r4-F01
  SUPPLEMENT：`_replay_from_snapshot` walk 自最早 committed 事务起、首个
  base≠revision 即 break ⇒ mid-history save（快照 revision 居 trace 中段）
  applied=0，证伪 DEV-W4-2 文档「自快照 revision 起取最长连续已提交前缀」
  一般陈述；探针 save_p8_mid 实证）；
  修正 2（预提交，实质修复 1/3：SOT 沉默面行为修正）：walk 增 skip 条款
  （base 低于快照 revision 视为已反映于快照态、不重放）——mid-history save =
  前向连续前缀（探针：base=1/final=3/applied=2）；运行结束存档不变
  （base=final=3/applied=0，t5 重钉）；基线态存档不变（全量重放）；`test`
  命令 `replay_consistency` 行（L853 口径）对 mid-history save 显式报
  ok=false（fail-loud，消除空洞假绿）；
  SOT 6 处标注校准（W4-R1 4 评审独立收敛；全 DOC 面、零行为变化）：
  (1) §3.0 L401 包内允许边表补 `persistence.filesystem → cli` 边（§3.9 L845
  缺省 backend 类要求强制；原表遗漏 = SOT 内部不一致）；
  (2) §3.8 L767 伪码索引 3 项 → 2 项（`kind`/`transaction_id`；无 record_id
  直查）+ L784 `causal_chain` 补注「同一 transaction_id 多记录取输入序末条」；
  (3) §3.9 L837 `build_cli_envelope` 返回标注 `dict[str, object]` →
  `dict[str, Any]`（与实现字节一致；运行时同解，零行为影响）；
  (4) §3.9 `replay` 行补 walk 最窄实现注（DEV-W4-2 更新：skip 条款 +
  mid-history save 前向前缀）；
  (5) §3.9 `test` 行补报告面注（报告面生成 ⇒ 信封恒 ok=true，`data["ok"]`
  总体裁决载体，检查行失败不翻信封——DEV-W4-4）；
  (6) §3.9 `--json` 条补最窄实现注（主解析器全局位置；子命令后 →
  `usage_error` rc 2；no-op——DEV-W4-3，SOT 沉默面）；
  影响面：W4 5 文件行数 1301→1308（trace_query 269→273，cli 392→395）；
  W4 偏差登记更新（DEV-W4-1/2 保留 + DEV-W4-2 语义更新 + DEV-W4-3/4 新增）；
  计数/白名单/账本零变化（26 / 3026 / 3048 不变）。

（后续实现波次勘误按 `ERR-P8-NN` 续编；每条必含：触发文件:行 / 原口径 / 修正口径 /
影响面。本区之外零自由文本。）

---

*（本 SOT 完；结构镜像 P7 SOT §0–§9；全部 file:line 锚点 @ `84a5d4f` 字节核验；
实现波次唯一依据 = 本文件 + §3.10.2 闭集白名单。）*
