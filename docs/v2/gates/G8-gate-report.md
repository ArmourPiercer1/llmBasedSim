# G8 Gate Report — Phase 8 Persistence / Replay / Dev Control Plane（终版）

按 `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` §17、§21、§24 编制。
G8-R1 盲审 4/4 通过、0 补充、0 阻塞、0 执行失败（判据 7 条 + gate 六步由 4 名 reviewer
独立复跑全部 met 且对账一致），本报告为 G8 最终交付点记录。

---

## 0. 基础信息

- **Gate**: G8（Phase 8 — Persistence / Replay / Dev Control Plane 门禁）
- **Commit SHA**: `9eb3e27`（P8 代码最终交付点 = W5 波；其后 docs 闭合链 `161b582`
  ERR-P8-06 → `904c997` ERR-P8-07 → 本报告提交〔docs-only，不改代码面〕）
- **分支**: `architecture-v2`
- **审查基准**: `84a5d4f`（G7 闭合基线，套件 2925）.. `9eb3e27`（代码面）/ SOT 至 `904c997`；
  P8 设计文档（SOT）= `docs/v2/contracts/P8-persistence-replay-devcontrol-design.md`
  （1782 行 @ `904c997` = W0 1608 行 + 勘误链 ERR-P8-01..07，§9）
- **测试基线**: 全量 **3054 passed / 0 failed**（gate ③ 真实输出）；
  P8 全程 +129 = 3054 − 2925：W1 +26（12+14）/ W2 +24（13+11）/ W3 +25（13+12）/
  W4 +26（12+14）/ W5 +28（10+12+6 边界）；SOT §8.3 恒等 gate1_p8_face 3048 = 2925+123 /
  gate1_expected 3054 = 3048+6（边界纯追加，ERR-P8-05）对账一致
- **审查执行**: 全部 `qiyuan-self / qwen3.8-27b`（人工路由覆盖）；设计阶段
  R1 4/4 补充 → R2 3 通过 + 1 补充 → R3 4/4 通过（docs-only 闭合，ERR-P8-01/02，
  设计冻结）+ 波次审查（W1 R1 4/4 通过，3 DOC 预提交修，ERR-P8-03 /
  W2 R1 4/4 通过，1 DOC 预提交修，ERR-P8-04 / W3 R1 4/4 通过，1 DOC + 3 INFO /
  W4 R1 2 通过 + 2 补充 → 3 预提交修（1 实质 1/3：walk skip）→ R2 4/4 通过 /
  W5 R1 4/4 通过全 DOC → ERR-P8-06 预提交修，无 R2）+ 门禁阶段
  **1 轮 × 4 名独立盲审（G8-R1，全新一轮全新盲）**，四裁决协议
  （通过/投机通过/补充内容/阻塞）

---

## 1. §21 字段

```text
Gate: G8
Commit SHA: 9eb3e27（代码面；docs 闭合链至本报告提交，见 §0/§5）
Tasks completed: P8-T01 ~ P8-T09（全部）：
                  T01 = W0 设计期 SOT（1608 行：P8-INV-1..10 + D-P8-01..18 决策登记 +
                         A1–A22 判据 + 边界 6 法 + gate 运行序六步）+ persistence 信封
                         snapshot 格式（persistence/snapshot.py，5 导出，嵌套复用冻结
                         core Snapshot，零重定义，D-P8-02）+ base.py 错误族单基类
                         （7 导出，D-P8-11）；
                  T02 = filesystem PersistenceBackend 参考后端（persistence/filesystem.py，
                         2 导出；3 方法抽象面 D-P8-03 + os.replace 原子写 D-P8-04）；
                  T03 = event-level replay（persistence/replay.py，3 导出；不重跑后端，
                         按 commit_revision 应用已提交事务，D-P8-05；walk skip 条款
                         DEV-W4-2）；
                  T04 = BackendCheckpoint registry / restore（persistence/checkpoint.py，
                         3 导出；注册表 host 注入，D-P8-15 评估面）；
                  T05 = branch / fork WorldInstance 原型（persistence/branch.py，5 导出；
                         BRANCH_CHECKS 3 闭集；默认拒绝 + degraded 显式开关，D-P8-10）；
                  T06 = DevelopmentCommand / ExternalInterventionEffect
                         （devtools/intervention.py，11 导出；命令闭集 6 种 = Spec §22
                         逐字，D-P8-13；三重标记 + trc_ 确定性 record_id，D-P8-17）；
                  T07 = trace query / causal chain API（devtools/trace_query.py，3 导出；
                         同步零 IO 10 方法；CausalChain 冻结 6 字段；D-P8-08 §37 12 项分配）；
                  T08 = CLI inspect/trace/replay/branch/test --json
                         （devtools/cli.py 5 导出 + scripts/v2_devcontrol.py 薄壳；
                         6 键信封闭集 + 11 错误码闭集 + exit 0/1/2，D-P8-09）；
                  T09 = corruption/replay/branch adversarial tests
                         （test_p8_adversarial.py 10 平铺 AD-1..10 +
                          test_g8_scenarios.py 12 平铺 A1–A12 逐行）
                         + TestP8Boundary 6 法纯追加（Leader 锚点，白名单 #25，+442/−0）；
                  + 2 conftest（persistence 17 fixture / devtools 8 fixture，零新增
                    fixture 文件）+ 2 占位 __init__.py（字节冻结，不在白名单）。
```

---

## 2. 门禁判据验证（Plan §17「G8」L747–759 七条逐字 + 双重证据）

| # | 准则（Plan L747–759 逐字） | 实现面（SOT） | 测试面 | 实测证据（G8-R1 四 reviewer 独立复跑确认 met） |
|---|---|---|---|---|
| C1 | snapshot → load → same WorldState | §3.2 信封嵌套复用（D-P8-02）+ §3.3 save/load（load 恰 5 门禁码；OSError→internal_error wrap 仅 save 行，DEV-W5-2 评估未实装） | `test_g8_scenarios.py::test_g8_1*`（per-key 相等 + `world_revision==3`；篡改 `contract_schema_version`→999 ⇒ `version_mismatch`）+ W1 `test_snapshot_format.py`（12） | 4/4 MET |
| C2 | event replay → same committed state | §3.4 `replay_committed`（不重跑后端，K2 复用；walk skip 条款 + 首个 base≠revision break，DEV-W4-2） | `test_g8_scenarios.py::test_g8_2*`（dump 相等 base 0 / final 3；SC-1 结构双跑 `json.dumps` 全量文本字节一致）+ W2 `test_replay.py`（13；SC-2 语义双跑 t2） | 4/4 MET |
| C3 | branch A/B 独立 | §3.6 `branch_world`（新 WorldInstance 原型；`BRANCH_CHECKS` 3 闭集；revision 不 bump） | `test_g8_scenarios.py::test_g8_3*`（双向别名隔离；新 id + `check_snapshot_versions` 空 + revision 不 bump）+ W3 `test_branch.py`（13） | 4/4 MET |
| C4 | non-checkpointable backend 明确拒绝 branch，而不是静默错误 | §3.6 默认拒绝（`BranchError` `branch_rejected`）+ `allow_degraded` 显式开关（degraded 结果面点名，非静默，D-P8-10） | `test_g8_scenarios.py::test_g8_4*`（SC-3 运行时 ⇒ `BranchError`，message 点名 `rigid_body`）+ AD-6（degraded 开关结果面点名） | 4/4 MET |
| C5 | Development intervention 可在 trace 中区分 | §3.7 三重标记（`OriginKind.DEVELOPER` + `CauseKind.INTERVENTION` + `TraceKind.DEV_INTERVENTION`；record_id host 给出确定性 `trc_`，K7 零 uuid4，D-P8-17） | `test_g8_scenarios.py::test_g8_5*`（DEV_INTERVENTION 恰 1 条 + `OriginKind.DEVELOPER`；`command_id=="dev-patch-1"`；cause_ids 精确链） | 4/4 MET |
| C6 | CLI JSON schema 稳定 | §3.9 6 键信封闭集 + `P8_ERROR_CODES` 11 码闭集 + exit 0/1/2 + `CLI_TOOL_NAME`/`DEVCONTROL_CLI_SCHEMA_VERSION` 常量（`--json` 主解析器全局位置 DEV-W4-3；`test` 报告面 ⇒ 信封恒 ok=true，DEV-W4-4） | `test_g8_scenarios.py::test_g8_6*`（5 子命令 + 6 键信封 + tool/schema_version；3 错误路径 code ∈ 闭集 + rc∈{1,2}）+ W4 `test_cli.py`（14） | 4/4 MET |
| C7 | causal chain 可从 event 回溯至 action / effect / producer | §3.8 `TraceQuery.causal_chain`（同步零 IO；冻结 6 字段；`committed_transactions` = `t.commit_revision is not None`） | `test_g8_scenarios.py::test_g8_7*`（transaction 非 None；effects source ∈ producers；`p8.rule` ∈ producers）+ W4 `test_trace_query.py`（12） | 4/4 MET |

---

## 3. gate 运行序 ①–⑥ 结果（SOT §3.10.4；G8-R1 四 reviewer 各自独立复跑且对账一致）

| 步 | 面 | 实测 |
|---|---|---|
| ① P8 新面 pytest | `.venv/bin/python -m pytest tests/engine_v2/persistence tests/engine_v2/devtools -q -p no:cacheprovider` | **123 passed / 0**（= persistence 73〔snapshot 12 + filesystem 14 + replay 13 + checkpoint 11 + branch 13 + adversarial 10〕+ devtools 50〔intervention 12 + trace_query 12 + cli 14 + g8 12〕，SOT §6.1） |
| ② 边界锚 pytest | `.venv/bin/python -m pytest tests/engine_v2/core/test_import_boundary.py -q -p no:cacheprovider` | **32 passed / 0** = 既有 26 + `TestP8Boundary` 6（m1 import 白名单 / m2 测试文件闭集 / m3 K8 12 名扫描 / m4 内核无关零 async / m5 白名单 diff 镜像 / m6 导出账本双相等）；锚文件 +442/−0 纯追加（1629→2071 行） |
| ③ 全量 pytest | `.venv/bin/python -m pytest tests/ -q -p no:cacheprovider` | **3054 passed / 0**（期望 = 2925 + 123 + 6，SOT §8.3 ERR-P8-05 口径） |
| ④ ruff 新面 | `ruff check src/engine_v2/persistence src/engine_v2/devtools tests/engine_v2/persistence tests/engine_v2/devtools scripts/v2_devcontrol.py` | **All checks passed**（line-length 100，pyproject.toml:31） |
| ⑤ ruff 全量 | `ruff check` | **30 findings，全部位于 12 个冻结 v1 既有文件**（`src/main.py` 8 / `src/game/*` 13 / `src/graph/game_graph.py` 2 / `src/ui/*` 2 / `src/prompts/loader.py` 1 / `src/models/events.py` 1 / `tests/test_models.py` 2 / `tests/test_init_extra.py` 1）；`src/engine_v2` / `tests/engine_v2` / `scripts` **零命中**——G7 基线面原样未变（v1 @ f0a1052 冻结，不在白名单，零动作） |
| ⑥ 白名单 diff + 占位 + 控制字节 | `git diff --name-only 84a5d4f..HEAD -- src tests scripts`；两占位 `git diff --stat`；`grep -rPl '[\x00-\x08\x0B\x0C\x0E-\x1F]' <25 文件>` | **25 文件** == SOT §3.10.2 闭集（集合 + 计数等值，G6 ERR-P6-14 口径）；两占位 `__init__.py` **零 diff**（创建于基线前，字节冻结 P8-INV-8）；控制字节预扫 **0 命中**（ERR-P7-14 项 3 同形） |

---

## 4. 白名单 diff（gate ⑥，封闭集 25 文件）

`git diff --name-only 84a5d4f..HEAD -- src tests scripts` = **25 文件**（与 SOT §3.10.2 表
集合 + 计数等值；顺序语义 = 集合 + 计数）：

| # | 文件 | 波 | | # | 文件 | 波 |
|---|---|---|---|---|---|---|
| 1 | `src/engine_v2/persistence/base.py` | W1 | | 14 | `tests/engine_v2/persistence/test_filesystem_backend.py` | W1 |
| 2 | `src/engine_v2/persistence/snapshot.py` | W1 | | 15 | `tests/engine_v2/persistence/test_replay.py` | W2 |
| 3 | `src/engine_v2/persistence/filesystem.py` | W1 | | 16 | `tests/engine_v2/persistence/test_checkpoint_registry.py` | W2 |
| 4 | `src/engine_v2/persistence/replay.py` | W2 | | 17 | `tests/engine_v2/persistence/test_branch.py` | W3 |
| 5 | `src/engine_v2/persistence/checkpoint.py` | W2 | | 18 | `tests/engine_v2/persistence/test_p8_adversarial.py` | W5 |
| 6 | `src/engine_v2/persistence/branch.py` | W3 | | 19 | `tests/engine_v2/devtools/__init__.py` | W3 |
| 7 | `src/engine_v2/devtools/intervention.py` | W3 | | 20 | `tests/engine_v2/devtools/conftest.py` | W3 |
| 8 | `src/engine_v2/devtools/trace_query.py` | W4 | | 21 | `tests/engine_v2/devtools/test_intervention.py` | W3 |
| 9 | `src/engine_v2/devtools/cli.py` | W4 | | 22 | `tests/engine_v2/devtools/test_trace_query.py` | W4 |
| 10 | `scripts/v2_devcontrol.py` | W4 | | 23 | `tests/engine_v2/devtools/test_cli.py` | W4 |
| 11 | `tests/engine_v2/persistence/__init__.py` | W1 | | 24 | `tests/engine_v2/devtools/test_g8_scenarios.py` | W5 |
| 12 | `tests/engine_v2/persistence/conftest.py` | W1 | | 25 | `tests/engine_v2/core/test_import_boundary.py`（**纯追加**，唯一锚点文件） | W5 |
| 13 | `tests/engine_v2/persistence/test_snapshot_format.py` | W1 | | | | |

25 = src 9 + scripts 1 + tests 15；**零 `src/engine_v2/core` 实质变更**（唯一 core 路径 =
锚文件纯追加 +442/−0）；**零 `docs/` 路径**（docs 依设计不入白名单）；两占位
`persistence/__init__.py` / `devtools/__init__.py` 不在白名单且字节冻结。

---

## 5. 审查记录（逐轮；verdict/findings 全文在 `.review-drafts/`，gate 闭合后删除，
SOT §9 勘误链为唯一规范记录）

| 轮 | 结果 | 处置 | 勘误 |
|---|---|---|---|
| 设计 R1 → R3 | R1 4/4 补充 → R2 3 通过 + 1 补充 → R3 4/4 通过（docs-only） | 补充闭合 ×2 提交，设计冻结 | ERR-P8-01/02 |
| W1 R1 | 4/4 通过（3 DOC，0 补充/0 阻塞） | 预提交修（无复审）；实质 0/3 | ERR-P8-03 |
| W2 R1 | 4/4 通过（1 DOC） | 预提交修（无复审）；实质 0/3 | ERR-P8-04 |
| W3 R1 | 4/4 通过（1 DOC，3 INFO） | 预提交修；INFO 登记；实质 0/3 | 并入 W3 波 |
| W4 R1 → R2 | R1 2 通过 + 2 补充 → 3 预提交修（闭集合规零行为 + walk skip **实质 1/3** + 行宽 DOC）→ R2 4/4 通过 | 波次内闭合 | 并入 W4 波 |
| W5 R1 | 4/4 通过（9/9 准则；全 DOC 级：t8 行号 4/4、§2.1 8 名 4/4、A4 口径 2/4、#19/#20 标签 2/4、A15 截断 1/4 + DEV-W5-7） | 预提交修 6 项（无 R2）；实质 0/3 | ERR-P8-06 |
| G8-R1（门禁） | **4/4 通过**（9/9 准则 MET；门禁 6 步独立复跑全绿；7 findings = 3 DOC + 4 INFO 全部 ≤ DOC/INFO：SOT 层 2〔§3.10.1 波次表残留 + R8 体积估计〕+ brief 层 5〔1 DOC 陈旧行锚 + 4 INFO〕） | 预提交修 SOT 层 2 项（无 R2）；门禁实质 0/3 | ERR-P8-07 |

提交链（G7 闭合后）：`6b815cf`（W0 SOT）→ `d0369af`（ERR-P8-01）→ `8504a25`
（ERR-P8-02）→ `bbf21f3`（W1 波）→ `d2cae8b`（ERR-P8-03）→ `067de80`（W2 波）
→ `e48112d`（ERR-P8-04）→ `a7834c6`（W3 波）→ `f790486`（W4 波）
→ `23b614c`（ERR-P8-05，W5 派发前 SOT 自洽审查）→ `161b582`（ERR-P8-06，W5-R1 DOC
闭合）→ `9eb3e27`（W5 波）→ `904c997`（ERR-P8-07，G8-R1 DOC 闭合）→ 本报告提交
（docs-only；SHA 不锚定，取 `git log` 链末位）。

---

## 6. 偏差登记

### 6.1 决策登记（D-P8-01..18，SOT §4 五段式；（自裁）标记者备选段豁免 = P7 先例）

| # | 项 | 选择（一行） |
|---|---|---|
| D-P8-01 | 包落位与模块粒度 | (b)。9 模块落 `src/engine_v2/persistence/`（6）+ `devtools/`（3）；`base.py` 错误族/抽象面为 P8 新增文件（DEV-P8-1）；replay/branch 逻辑面在 `persistence/`，CLI 复用（DEV-P8-2） |
| D-P8-02 | T01 信封：嵌套复用 vs 新信封 | (b)。嵌套复用冻结 core `Snapshot`（零重定义）；P8 层只补 Spec §30.2 的 WorldState/RuntimeState/Project/Module versions 四项；单面（S2） |
| D-P8-03 | T02 抽象面：PersistenceBackend Protocol | (b)。3 方法最小面（save/load/list_saves 族）；Spec §30.3 五类后端 ⇒ 抽象面是 spec 预期 |
| D-P8-04 | T02 布局与原子写 | (b)。trace JSONL 追加语义 + checkpoint 体位分离（envelope ref = T04 体/ref 分层）；`os.replace` = stdlib 原子语义（D1） |
| D-P8-05 | T03 replay 语义：重跑后端 vs 应用已提交事务 | (b)。不重跑后端——按 `commit_revision` 应用已提交事务（Spec §30.4 最低保证）；明确「不要求所有 numerical backend 可重放」 |
| D-P8-06 | T04 注册表绑定与 checkpoint 体位 | (b)。restore 活实例委派（toy 模式：`restore` 返回新实例，`dynamics/toy_rigid.py:134`）；体/ref 分离 = Spec §30.2 |
| D-P8-07 | T06 intervention 落位与提交路径 | (b)。P8 本地包裹而非 core 扩展（S1 不可破）；core 冻结面已备齐三重标记（`OriginKind.DEVELOPER` L54 + `CauseKind.INTERVENTION` L94 + `TraceKind.DEV_INTERVENTION` L109） |
| D-P8-08 | T07 查询 API 形态与 §37 12 项分配 | (b)。同步零 IO 10 方法（D4 零 IO 分层）；§37 前 4 项数据源 = `WorldState`/`RuntimeState` 快照，非 trace——零双实现 |
| D-P8-09 | T08 CLI 落位与 JSON 信封 | (b)。`devtools/cli.py`（argparse 可测）+ `scripts/` 薄壳（`llm_smoke.py` 先例）；单一信封构造面（`build_cli_envelope` 纯函数）；6 键闭集 + 11 错误码闭集 |
| D-P8-10 | T05 branch 语义与 degraded 开关 | (a)。默认拒绝（G8-4 逐字「明确拒绝 branch，而不是静默错误」）；Spec §30.5 L1623–1626「degraded / unavailable」⇒ degraded = 显式能力降级面（`allow_degraded` 参数，非双 API） |
| D-P8-11 | 错误族单基类 | (b)。`PersistenceError` 单基类（码闭集 = CLI 信封 `error.code` 同一闭集，S2 单面）；devtools → persistence.base 单向导入 |
| D-P8-12 | K7 确定性线 | (b)。replay（A4）/ 信封序列化（dump 确定性 t4）/ filesystem 双 save（t13）/ CLI（t13 同族）四面对同一输入双跑字节一致；零模块级可变状态；id 全 host 给出（D5）+ 零 `uuid4`；wall-clock 零读取 |
| D-P8-13（自裁） | DevelopmentCommand 闭集 | Spec §22 六例逐字 `("pause","step","force_wake","inject_event","patch_state","branch")`；新增 kind = 波次决策（需同步 authority policy 面 + 测试） |
| D-P8-14（自裁） | CLI `test` 子命令语义 | save 完整性 + replay 一致性**校验报告**（5 检查行闭集）；完整 scenario 测试编排 = P8+（§0.4.3） |
| D-P8-15（自裁） | P7 移交评估：OI-P7-1 与 D-P7-13 | **OI-P7-1**（项目侧 `.py` backend 发现）= **本波不实装**——注册面 = host 注入（`BackendCheckpointRegistry` 调用方构造传入），零项目 `.py` 消费；loader 9-glob 冻结；**D-P7-13**（测试侧 handler 提升 src）= 维持现状（core 冻结） |
| D-P8-16（自裁） | G6 carryover 处置 | `proposal_id` nonce = 不适用——P8 不引入 proposal id 新概念（复用冻结 `EffectId`/`TransactionId`/`command_id`（host 给出）面）；`uv lock` = **零变更**（S4：stdlib only，lock 不在白名单） |
| D-P8-17（自裁） | 干预 cause ref 指向 DEV_INTERVENTION 记录 record_id | (b)。`to_intervention_effects(command, *, base_revision, intervention_record_id)`；`apply_development_command` 增 host 参数 `intervention_record_id`（空/非 `trc_` 词法 → schema_invalid）；record_id 不消费 uuid4 工厂 |
| D-P8-18（自裁） | pydantic 导入面 = 3 名窄例外 | (b)。`Field`/`model_validator`/`ValidationError`（ContractModel 基础设施面，与冻结 core 27 模块同款；§3.0 允许列独立行 + 禁止列 catch-all 括注例外）；零新依赖，uv.lock 不动 |

### 6.2 W1–W5 自裁偏差面（盲审裁定合规、维持现状、全部已登记；14+7+7+4+7 = 39 项）

| 面（代表项） | 波 | 处置 |
|---|---|---|
| `base.py` = P8 新增文件（DEV-P8-1）；CLI 逻辑面 persistence 复用（DEV-P8-2）；`test` 子命令报告面语义（DEV-P8-5）；`snapshot()` 经子模块 `core.snapshot` 导入（DEV-P8-6，不在 core 根 `__all__`）等 14 项 | W1 | legit-narrow，登记 |
| 7 项（含 checkpoint 判别面、degraded 点名面细节） | W2 | legit-narrow，登记 |
| 7 项（含 registry 注入面、branch 审计 payload 面——s2 风险面移交 P9 评估） | W3 | legit-narrow，登记（1 DOC + 3 INFO） |
| store-root `saves_root` 约定（DEV-W4-1）；walk skip 条款（DEV-W4-2，**实质 1/3**）；`--json` 主解析器全局位置（DEV-W4-3）；test 报告面信封恒 ok=true（DEV-W4-4） | W4 | legit-narrow，登记 |
| A4 = SC-1 结构双跑（SC-2 语义双跑由冻结 W2 `test_replay.py` t2 承载，§6.2 包内闭集）（DEV-W5-1）；load 侧 raw-OSError 逃逸 = SOT 照写（评估未实装，DEV-W5-2）；W4 语义合规（DEV-W5-3）；K8 正则盘上字节 0x5C 0x62（DEV-W5-4）；边界方法 1 = 模块级闭集 + 3 名级窄例外，union 40 名全 §2.1（DEV-W5-5）；AD-4 记录级输入面（DEV-W5-6）；method 4 `PersistenceBackend` 裸词排除（DEV-W5-7，冻结 core 裸词 5 处 + P7 先例） | W5 | legit-narrow，登记（全 DOC 级） |

全文载体：各波提交 message + SOT §4/§9 + `.review-drafts/`（gate 闭合后删除）。

---

## 7. 风险登记册

SOT §0.6（R1–R8）逐条承继：

| # | 风险 | 等级 | 处置 |
|---|---|---|---|
| R1 | 语义 effect replay 需 handler 注册表注入；CLI 独立运行时仅冻结默认结构 handler | 低 | `default_handler_registry`（`core/reducer.py:743`）；语义面经测试侧注入（D-P7-13/D-P8-15 维持现状） |
| R2 | 未来真实数值后端 non-checkpointable 时 branch 能力 | 低（本波） | G8-4 fail-loud（默认拒绝 + degraded 显式开关）已备 |
| R3 | 推理侧动力学（P7 `LLMWorldDynamics`，`replayable=False`）与 replay 的关系 | 低 | Spec §30.4 最低保证不要求数值重跑；P8 replay 路径不消费 `replayable` 声明 |
| R4 | OI-P7-1（项目侧 backend 发现）不移交风险 | 低 | D-P8-15 评估结论登记 §4；loader 9-glob 冻结 |
| R5 | G6 carryover：`proposal_id` 无 nonce / `uv lock` 漂移 | 低 | D-P8-16：P8 零新 id 概念 + lock 零变更 |
| R6 | 嵌套 `Snapshot` 的 pydantic 校验深度与 JSON-clean 成本 | 低 | 信封 `snapshot` 字段 = 嵌套冻结模型；`dump_json(mode="json")` 确定性 |
| R7 | `index.json` 单文件写并发 | 低 | 单进程原型（§0.4.7）；并发面 = P8+（届时 SQLite 后端，S2 评估） |
| R8 | 边界锚文件纯追加后体积增长 | 低 | 锚文件唯一修改模式 = EOF 纯追加；**实测 +442 行**（1629→2071，ERR-P8-07 已校准估计面） |

**P9 移交/承继面**：branch-audit payload schema / replay ABORTED 保留面 /
snapshot-derived inspect 覆盖（W3-R2 F02–F04 INFO，P9 评估面）；D-P7-13 测试侧 handler
注册维持现状（core 冻结约束持续适用）；SOT 行锚勘误链纪律（ERR-P8-01..07 先例：
§9 唯一规范记录，历史条目不追改）。

---

## 8. HARD STOP 逐条核验（Plan §24，L1212–1288）

- **S1（需要改变 Architecture Kernel invariant）— 未触发**。`git diff 84a5d4f..9eb3e27
  -- src/engine_v2/core` 中唯一 core 路径 = 锚文件 `test_import_boundary.py` **纯追加**
  +442/−0（Leader-owned，P7 先例）；25 白名单文件全部为 `src/engine_v2/persistence` +
  `src/engine_v2/devtools` 新增 + tests 新增/纯追加 + scripts 新增；core 32 子模块 /
  308 导出冻结不变量零改动；K1–K8 语义面实证（K4 authority closed-by-default 零旁路 /
  K5 intervention = policy 只产 ProposedEffect 零直写 / K6 DEV_INTERVENTION 三重标记
  可追踪 / K7 g8_2b 双跑字节一致 + AD 族 / K8 推理侧 12 名零命中 + Deployment/Game
  Project separation）4/4 reviewer 独立一致。
- **S2（Public Contract 两种同样合理但不兼容设计，Agent 自行选一并扩散）— 未触发**。
  交付公共面单设计：9 模块 44 导出名单一账本（§8.2 序双等，边界方法 6）；二选一面均已
  显式单选并登记 §4：信封层（D-P8-02 嵌套复用）/ intervention 落位（D-P8-07 P8 本地
  包裹）/ CLI 落位（D-P8-09 devtools + scripts 薄壳）/ degraded 开关（D-P8-10 显式参数
  非双 API）/ 错误族（D-P8-11 单基类）；OI-P7-1 二选一 = 本波不实装（D-P8-15），无扩散。
- **S3（为通过测试需要 destructive migration）— 未触发**。25/25 文件纯新增 / 纯追加、
  0 删除行；v1 根目录零触碰；P8 save 格式 = 新格式（`PERSISTENCE_FORMAT_VERSION=1`
  世代），零向后兼容义务、零既有数据迁移。
- **S4（引入新的重大依赖 / License 风险）— 未触发**。`pyproject.toml` / `uv.lock` 不在
  diff 内；零新增第三方依赖（`pydantic` = uv.lock 既有，3 名窄例外 D-P8-18）；
  stdlib only（D1 闭集）；无 vendored 代码、无本地服务、无数据库。
- **S5（Backend 无法满足 replay/checkpoint Contract）— 本波未触发（面已备）**。
  本波唯一数值后端 = P7 toy（`checkpointable=True`，`dynamics/toy_rigid.py:46` 起；
  checkpoint JSON-clean / restore 确定性续延 / G8-3 分支等价）；non-checkpointable
  拒绝面 fail-loud（G8-4 默认拒绝 + degraded 显式点名，C4 4/4 MET）；
  LLMWorldDynamics `replayable=False` 诚实自报且不在 P8 replay 路径（R3）。

---

## 9. 结论

- G8-R1：**4/4 通过、0 补充、0 阻塞、0 执行失败**（G8 实质轮 0/3；7 findings = 3 DOC +
  4 INFO：SOT 层 2 DOC → ERR-P8-07 预提交修；其余 1 DOC + 4 INFO 全部 brief 层——
  速查表占位行 / ruff 全量文件数标签 / P8-INV 范围 / g8 表陈旧行锚——零 SOT 动作）；
- 门禁判据 **7/7 met**（Plan §17 G8 逐字：snapshot→load / event replay / branch A/B
  独立 / non-checkpointable 明确拒绝 / intervention trace 可区分 / CLI JSON schema 稳定 /
  causal chain 回溯；4 名独立盲审 reviewer 各自完整核验 + 独立复跑 ①–⑥ 全步对账一致）；
- gate 运行序 ①–⑥ 全绿（**123 / 32 / 3054 / ruff 新面 0 / ruff 全量 30 = v1 冻结既有面
  / diff 25 + 占位 0 diff + 控制字节 0**）；
- 白名单 diff = **25**（封闭集，集合 + 计数等值，多一少一 = 门禁失败，实测恰好 25）；
- 计数恒等：2925 + 123（P8 新面 = 73+50）+ 6（TestP8Boundary 纯追加）= **3054**
  （SOT §8.3，ERR-P8-05 口径；§6.1 123 恒等式 26+24+25+26+22 不变）；
- HARD STOP S1–S5 未触发（§8 逐条核验）；
- 各波实质修复轮：W1 0/3、W2 0/3、W3 0/3、W4 **1/3**（walk skip）、W5 0/3、
  G8 0/3——全部在预算内；docs 闭合 ×7（ERR-P8-01..07）不消耗补充预算；
- 未使用 CONDITIONAL PASS（Plan §21 默认禁止）。

**下一阶段**：P9（Official Modules / v1 Migration，Plan §18）；
HARD STOP 清单（Plan §24 S1–S5）持续适用；P9 移交面 = OI-P7-1（项目侧 `.py` backend
发现，D-P8-15 评估未实装）+ D-P7-13 测试侧 handler 注册维持现状 + §7 三条 s2 评估面。
