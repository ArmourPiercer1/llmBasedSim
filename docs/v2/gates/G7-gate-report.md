# G7 Gate Report — Phase 7 WorldDynamics（终版）

按 `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` §16、§21、§24 编制。
G7-R1 盲审 4/4 通过、0 补充、0 阻塞、0 执行失败（四条判据 + gate 六步由 4 名 reviewer
独立复跑全部 met 且对账一致），本报告为 G7 最终交付点记录。

---

## 0. 基础信息

- **Gate**: G7（Phase 7 — WorldDynamics 门禁）
- **Commit SHA**: `ea84d00`（HEAD，P7 最终交付点；W5 R3 post-closure docs 校准）
- **分支**: `architecture-v2`
- **审查基准**: `e816a64`（G6 闭合基线，套件 2813）.. `ea84d00`；
  P7 设计文档（SOT）= `docs/v2/contracts/P7-world-dynamics-design.md`（1696 行 = W0 1321 行 +
  勘误链 ERR-P7-01..17，§9）
- **测试基线**: 全量 **2925 passed / 0 failed**（gate ① 真实输出）；
  P7 全程 +112 = 2925 − 2813：W1 +33（12+13+8）/ W2 +10 / W3 +14 /
  W4 +26（8+8+10）/ W5 +29（14+9+6）；SOT §8.3 方程对账一致
- **审查执行**: 全部 `qiyuan-self / qwen3.8-27b`（2026-08-20 人工路由覆盖）；设计阶段
  **1 轮 × 4 盲审（R1 4/4 通过 + 28 findings 全部 ≤ DOC/INFO，ERR-P7-01，设计冻结）**
  + 波次审查（W1 R1 4/4 补充 → R2 4/4 通过，实质 1/3，ERR-P7-02..04 /
  W2 R1 3/4 阻塞 → R2 4/4 通过，实质 1/3，ERR-P7-05..06 /
  W3 R1 4/4 通过 R1 闭合，0/3，ERR-P7-07..08 /
  W4 R1 3 通过+1 补充 → R2 4/4 通过，0/3，ERR-P7-09..12 /
  W5 R1 4/4 阻塞（0x08 词边界腐蚀同根因）→ R2 3 通过+1 补充（docs 闭合）→ R3 4/4 通过，
  实质 1/3，ERR-P7-13..17）+ 门禁阶段 **1 轮 × 4 名独立盲审（G7-R1，全新一轮全新盲）**，
  四裁决协议（通过/投机通过/补充内容/阻塞）

---

## 1. §21 字段

```text
Gate: G7
Commit SHA: ea84d00
Tasks completed: P7-T01 ~ P7-T08（全部）：
                  T01 = W0 设计期 SOT（1696 行：P7-INV-1..10 + D-P7-01..15 决策登记 +
                         A1–A20 判据 + 边界 6 法 + gate 运行序六步；设计 R1 4/4 通过，
                         ERR-P7-01）+ W1 backend.py WorldDynamicsBackend Protocol +
                         BackendMetadata（2 exports，D-P7-01 同步面）；
                  T02 = W1 diagnostic.py DynamicsDiagnostic（3 exports，D-P7-10 诊断码）
                         + W2 rule.py RuleDynamics reference backend（规则声明序 = 求值序）；
                  T03 = W3 llm_world.py LLMWorldDynamics（复用 P6 冻结运行时缝
                         InferenceBackend Protocol，scripted fake，零网络，D-P7-05）；
                  T04 = W4 composite.py CompositeDynamics 双 backend 编排（缺省四策链）；
                  T05 = W4 authority.py dynamics domain ownership / authority integration
                         （build_dynamics_producers 4 id + default_dynamics_policy，
                         closed-by-default，D-P7-08）；
                  T06 = W1 toy_rigid.py reference checkpointable toy 数值 backend
                         （1D 刚体 Euler 积分，Case C 契约面，D-P7-04）；
                  T07 = W5 外部 physics 库 PoC / dependency evaluation 记录
                         （EVALUATION ONLY，零新增依赖，S4 评估面，D-P7-06）；
                  T08 = W5 test_g7_scenarios.py 14 平铺（A1–A14 逐行）
                         + test_p7_adversarial.py 9 平铺（AD-1..AD-9 一 AD 一函数）
                         + TestP7Boundary 6 法纯追加（Leader 锚点，白名单 #23）；
                  + W4 host.py run_dynamics_turn / DynamicsTurn（2 exports，
                    P7 自持组装点，§3.8，D-P7-09）；
                  + 锚点同步（test_import_boundary.py P7 块纯追加 L1232–1629 / 398 行，
                    Leader 执行，白名单 #23）；
                  + G7 文档级闭合（ERR-P7-01..17：开发前 + 各轮后勘误全部登记，SOT §9）
Tasks waived: 无
Tests: 2925 passed / 0 failed（真实输出，.venv python）
Known failures: 0
Architecture deviations: 见 §6 偏差登记（D-P7-01..15 全部已登记 + W1–W5 自裁 INFO 面，
                        全部已披露/已登记）
Open risks: 见 §7 风险登记册（OI-P7-1 项目侧 backend 发现移交 P8+ 等，均低）
Human review required: 否（HARD STOP S1-S5 未触发，逐条核验见 §8；各波实质轮
                        W1 1/3、W2 1/3、W3 0/3、W4 0/3、W5 1/3、G7 0/3，均在预算内，
                        按 2026-08-20 协议无需人工批准）
Decision: PASS
```

---

## 2. 门禁判据验证（Plan §16「G7」L689–723 四条逐字 + 双重证据）

| # | 准则（Plan L689–723 逐字） | 实现面 | 测试面 | 实测证据（G7-R1 四 reviewer 独立复跑确认 met） |
|---|---|---|---|---|
| G1 | Case A 无详细物理：`LLMWorldDynamics → GemMoved` | `llm_world.py` scripted fake 产 `gem.moved` ProposedEffect，经冻结 `CascadeExecutor` 完整 K2 管道，场景零 physics backend 在场 | test_g7_scenarios t1–t4（A1–A4） | 4/4 独立 probe：终态 gem 已移动、单 effect trace、诊断零异常 |
| G2 | Case B「Rigid/Rule backend 与 LLM 同时 propose：`physics → stay` / `LLM → fall`；必须可见两个 ProposedEffect，并由 resolver 决定」 | `composite.py` 双 backend 同批（`CompositeDynamics(children=(toy, llm))` 声明序）→ 2 ProposedEffect 可见；冻结 `conflicts.detect_conflicts` 恰 1 组；缺省四策链 producer_priority 100>50 拍板 → WINNER = 物理 stay / REJECT = llm fall | test_g7_scenarios t5–t9（A5–A9） | 4/4 独立 probe：2 effects 可见 / 恰 1 冲突组 / 恰 1 WINNER / WINNER = 物理 / 终态 stay |
| G3 | Case C toy numerical backend：「checkpoint；restore；branch 后继续；metadata 正确」 | `toy_rigid.py` checkpoint = JSON-clean dict（`{"version": 1, "seed": 0}`）；restore 纯函数于输入；同一 cp 两次独立 restore = 两条独立 continuation | test_g7_scenarios t11–t14（A11–A14） | 4/4 独立 probe：JSON-clean 断言 / 确定性续延 / 双 continuation byte-identical / metadata 三布尔全真（K7 双跑字节相等） |
| G4 | 「不得在 Kernel 中写：`if backend is LLM ...` / `elif backend is physics ...`」 | `host.py` 对 `WorldDynamicsBackend` Protocol 面泛化调用（零 backend 类型 if/elif，P7-INV-2 机械口）；边界第 4 法双向机械断言：core/** 零命中 `engine_v2.dynamics` 包路径 / `if backend is` / `elif backend is` / 35 P7 export 名 | t10（A10）+ TestP7Boundary 第 4 法 | 4/4 独立 grep（core 33 个 .py 全扫）零命中；35 名运行时自 `__all__` 派生（§8.2 序双等） |

---

## 3. gate 运行序 ①–⑥ 结果（SOT §3.10；G7-R1 四 reviewer 各自独立复跑且对账一致）

| 步 | 面 | 实测 |
|---|---|---|
| ① full pytest | `.venv/bin/python -m pytest tests/ -q -p no:cacheprovider` | **2925 passed / 0 failed**（期望 2813 + 112 = 2925，SOT §3.10 步 1 逐字） |
| ② ruff | scope = `src/engine_v2/dynamics tests/engine_v2/dynamics` + 既有 P6 scope（`src/engine_v2/llm src/engine_v2/prompts tests/engine_v2 scripts`），line-length 100 | `All checks passed!`（0 findings） |
| ③ 白名单 diff | `git diff --name-only e816a64..HEAD -- src tests scripts` | **23 文件**，与 SOT §3.10 表集合 + 计数等值（G6 ERR-P6-14 口径）；`dynamics/__init__.py` 占位字节不变（433 B / 9 行，diff stat 零）；**控制字节预扫（ERR-P7-14 item 3）：23 文件 C0 控制字节（除 \t\n\r）= 0**（0x08 计数 = 0） |
| ④ 边界 | `-k "TestP7Boundary or TestP6Boundary or TestP5Boundary"` | **17 passed** = TestP7Boundary 6 + TestP6Boundary 6 + TestP5Boundary **5**（P5 边界 = 5 法，--collect-only 自核验，非 6）全绿 |
| ⑤ gate 回归 | core/test_p3_gate_scenario + core/test_p4_gate_scenario + content/test_p5_gate_scenario + llm/test_p6_gate_scenario | **57 passed**（10 + 7 + 20 + 20，逐文件 --collect-only 自算） |
| ⑥ fake e2e + P7 smoke | P6 fake e2e 面复跑 + P7 smoke 面 | **34 passed**（P6 e2e 20 + g7 14；本波零脚本新增——SOT §3.10 步 6 明注：P7 smoke 面 = 本报告附录 G7 三 case 摘要，不预加独立脚本） |

**附录：G7 三 case 摘要**（P7 smoke 面，SOT §3.10 步 6 指定载体）：

- **Case A**（t1–t4）：scripted fake LLMWorldDynamics → `gem.moved` ProposedEffect
  → 冻结 K2 管道（Validation → Transaction → Reducer）→ 终态 gem 已移动；场景零物理 backend。
- **Case B**（t5–t9）：CompositeDynamics(toy, llm) 同批 propose → 2 个 ProposedEffect 可见
  （`physics → stay` / `LLM → fall`）→ detect_conflicts 恰 1 组 → 缺省四策链
  producer_priority 100>50 拍板 → WINNER = 物理 stay、REJECT = llm fall → 终态 stay。
- **Case C**（t11–t14）：toy checkpoint `{"version": 1, "seed": 0}`（JSON-clean）→
  restore 确定性续延 → 同一 cp 两次独立 restore = 两条独立 continuation，
  byte-identical（K7）→ metadata 三项布尔全真。

---

## 4. 白名单 diff（gate ③，封闭集 23 文件）

`git diff --name-only e816a64..HEAD -- src tests scripts` = **23 文件**（与 SOT §3.10 表
集合 + 计数等值；顺序语义 = 集合 + 计数，G6 ERR-P6-14 口径）：

| # | 文件 | 波 | | # | 文件 | 波 |
|---|---|---|---|---|---|---|
| 1 | `src/engine_v2/dynamics/backend.py` | W1 | | 13 | `src/engine_v2/dynamics/llm_world.py` | W3 |
| 2 | `src/engine_v2/dynamics/diagnostic.py` | W1 | | 14 | `tests/engine_v2/dynamics/test_llm_world.py` | W3 |
| 3 | `src/engine_v2/dynamics/toy_rigid.py` | W1 | | 15 | `src/engine_v2/dynamics/composite.py` | W4 |
| 4 | `tests/engine_v2/dynamics/__init__.py` | W1 | | 16 | `src/engine_v2/dynamics/authority.py` | W4 |
| 5 | `tests/engine_v2/dynamics/conftest.py` | W1 | | 17 | `src/engine_v2/dynamics/host.py` | W4 |
| 6 | `tests/engine_v2/dynamics/test_backend_metadata.py` | W1 | | 18 | `tests/engine_v2/dynamics/test_composite.py` | W4 |
| 7 | `tests/engine_v2/dynamics/test_toy_rigid.py` | W1 | | 19 | `tests/engine_v2/dynamics/test_authority_host.py` | W4 |
| 8 | `tests/engine_v2/dynamics/test_diagnostic.py` | W1 | | 20 | `tests/engine_v2/dynamics/test_host_driver.py` | W4 |
| 9 | `tests/fixtures/v2_deployment_p7/deployment.yaml` | W1 | | 21 | `tests/engine_v2/dynamics/test_g7_scenarios.py` | W5 |
| 10 | `tests/fixtures/v2_project_p7/game.yaml` | W1 | | 22 | `tests/engine_v2/dynamics/test_p7_adversarial.py` | W5 |
| 11 | `src/engine_v2/dynamics/rule.py` | W2 | | 23 | `tests/engine_v2/core/test_import_boundary.py`（**纯追加**，唯一锚点文件） | W5 |
| 12 | `tests/engine_v2/dynamics/test_rule_dynamics.py` | W2 | | | | |

23 = src 8 + tests 13 + fixtures 2；**零 `src/engine_v2/core` 路径**（kernel 零改动）；
**零 `docs/` 路径**（docs 依设计不入白名单）；**零 `scripts/` 路径**（本波零脚本新增）。

---

## 5. 审查记录（逐轮；verdict/findings 全文在 `.review-drafts/`，gate 闭合后删除，
SOT §9 勘误链为唯一规范记录）

| 轮 | 结果 | 处置 | 勘误 |
|---|---|---|---|
| 设计 R1 | 4/4 通过（28 findings 全部 ≤ DOC/INFO，0 阻塞/0 补充） | 12 DOC 项开发前闭合 | ERR-P7-01 |
| W1 R1 → R2 | R1 4/4 补充 → R2 4/4 通过 | 实质 1/3（ERR-P7-02 SOT 闭集词表 llm→inference，W1 交付面内闭合） | ERR-P7-02..04 |
| W2 R1 → R2 | R1 3/4 阻塞 → R2 4/4 通过 | 实质 1/3（契约错误 = SOT §2.1 符号表缺口，W2 交付面内闭合） | ERR-P7-05..06 |
| W3 R1 | 4/4 通过（R1 闭合） | 0/3 实质；开发前 Leader 预检 + R1 docs 精度修 | ERR-P7-07..08 |
| W4 R1 → R2 | R1 3 通过 + 1 补充 → R2 4/4 通过 | 0/3 实质；SOT §3.6/§3.7/§5.1 口径补注（policy 匹配 (b) / host 规则目标 (c) / composite fidelity (e) 三裁定） | ERR-P7-09..12 |
| W5 R1 → R2 → R3 | R1 4/4 阻塞（同根因：锚点方法 3 词边界 `\b` 两字符转义腐蚀为 0x08 字节 ×4，K8 扫描 + 负向锚点 probe 结构性空洞）→ R2 3 通过 + 1 补充（行号 stale + A10 bullet 缺口）→ R3 4/4 通过 | 实质 1/3（Leader 锚点修复：0x08 ×4 → 两字符转义 + ERR-P7-14 自检块，转义再腐蚀响亮失败）+ docs ×4（ERR-P7-13 预对齐 / ERR-P7-15 口径 ×5 / ERR-P7-16 行号 + A10 / ERR-P7-17 post-closure §6.2 handlers 口径） | ERR-P7-13..17 |
| **G7-R1** | **4/4 通过、0 补充、0 阻塞、0 执行失败** | 2 INFO findings 同靶（ERR-P7-14 第 2 条行号引用锚定 d598cfb blob 几何；两 reviewer 独立字节实证自洽——d598cfb blob L1510/L1517 确为 0x08 ×4，HEAD 同逻辑行已移 L1516/L1523；裁定无动作，见 §7） | — |

提交链（G6 闭合后）：`24084ea`（W0 SOT）→ `a8d11e2`（W1 波）→ `e2bdd`（ERR-P7-02）
→ … → `69930f7`（W4 R2 DOC）→ `d598cfb`（W5 波）→ `0e4b6c9`（ERR-P7-13）
→ `1d4790f`（ERR-P7-14/15，R1 代码修复）→ `3282794`（ERR-P7-16，R2 docs 闭合）
→ `ea84d00`（ERR-P7-17，R3 post-closure）。

---

## 6. 偏差登记

### 6.1 决策登记（D-P7-01..15，SOT §4；D-P7-01..12 = 任务书 D1–D12，D-P7-13..15 = 自裁）

| # | 项 | 选择（一行） |
|---|---|---|
| D-P7-01 | simulate 同步 vs 异步 | (b) 同步 `simulate(...) -> tuple[ProposedEffect, ...]`（DEV-P7-1 登记；边界第 4 法 (b) 零 async 机械面） |
| D-P7-02 | 代码落位与项目 backend 发现 | (b) 8 模块落 `src/engine_v2/dynamics/`，loader 9-glob 闭集零改动；项目 `.py` backend 发现 = OI-P7-1 移交 P8+ |
| D-P7-03 | metadata 形态与闭集词表 | frozen `BackendMetadata`；determinism/implementation_type 闭集 + fidelity 名字型描述串；载体 = 模块导出 + host 注册（永不出现在游戏项目文件） |
| D-P7-04 | toy 数值 backend 形态 + Case C 读法 | toy = 1D 刚体（pos/vel/acc，Euler dt）；Case C = 契约面非物理（checkpoint/restore/branch 契约） |
| D-P7-05 | LLMWorldDynamics 形态 | 复用 P6 冻结运行时缝（InferenceBackend Protocol），scripted fake，零网络 |
| D-P7-06 | T07 外部 physics 库 | EVALUATION ONLY：只产依赖评估记录（license 类别等），零新增依赖、零运行时开关 |
| D-P7-07 | kernel 无感 | P7 = core/ 之外消费者包；backend 一律经 Protocol 泛化调用（G4 机械口） |
| D-P7-08 | producer id 词表与权限配置权 | 4 id 定案 = `rule_dynamics` / `llm_world_dynamics` / `rigid_body` / `composite_dynamics`（全 fullmatch PRODUCER_ID_PATTERN）；权限配置权 = host（build_dynamics_producers priority 100/100/80/50 + default_dynamics_policy closed-by-default） |
| D-P7-09 | 输入数据类与调用点 | 三数据类全 frozen；WorldSnapshot = core Snapshot 薄投影；host 自持组装点 |
| D-P7-10 | 诊断码 | `DynamicsDiagnostic`（frozen pydantic extra="forbid"，码闭集） |
| D-P7-11 | 波次 + 白名单 + gate 运行序 | 5 波 + 23 封闭集 + gate 六步（SOT §3.10） |
| D-P7-12 | K7 行 | RuleDynamics / toy 双跑 byte-identical（canonical JSON） |
| D-P7-13 | G7 场景 effect 类型 | 自裁：语义型（`EffectTypeId` 小写点分名，测试侧经公开注册面） |
| D-P7-14 | WorldSnapshot | 自裁：P7 薄投影（world_state/world_revision/logical_tick 等），非别名（零状态污染） |
| D-P7-15 | 诊断通道 | 自裁：每实例 `diagnostics` 属性（last-run 视图；`simulate` 入口清空） |

### 6.2 W1–W5 自裁 INFO 面（盲审裁定合规、维持现状、全部已登记）

| 面 | 波 | 处置 |
|---|---|---|
| 私有 _MonotonicClock/_FixedMonotonicClock 镜像（边界白名单覆盖）；conftest p7_game 返回 object；toy severity 字符串 "error"（pydantic 强制）；AD-4 豁免 `__all__`/`Final`；EFFECT_TYPE_ID_PATTERN 直接 import | W1 | INFO 合规 |
| @field 仅解顶层模板标量；rule.py 未测附加面 | W2 | INFO 合规 |
| llm_world L2 `str(None)`→"None"；`payload=dict()` 防御性拷贝；`Field(default_factory=dict)` ≡ `{}`；repair_instruction P6 schema 文本失配 | W3 | INFO 合规 |
| t8 单条通配 policy（ERR-P7-09(b)）；host S1 规则目标钉 `gem_state`（ERR-P7-09(c)）；composite 空 children fidelity="composite" 无尾点（ERR-P7-09(e)）；_DETERMINISM_LATTICE 本地镜像；host `run_dynamics_turn` 未标注（Protocol 面）；t10 uuid4 跨 run 投影（D-P3-15①②） | W4 | INFO 合规（SOT §3.6/§3.7/§5.1 口径补注） |
| g7 host turn 通配 policy（遵循 ERR-P7-09(b)）；Case B composite (toy, llm) 声明序 + origin `composite_dynamics`；t9 acc `.get` byte-truth；A10 35 名 `__all__` 派生；AD-3 12 名闭集复用锚点 import；AD-7 本地 "note" 组件世界；_S5_WIRE 本地常量；方法 5 目录封闭镜像（ERR-P7-13）；_p7_module_paths 2 条结构性断言 | W5 | INFO 合规（维持现状） |
| conftest.py L164 docstring handlers 口径 stale | W1 冻结面 | ERR-P7-17 登记 carryover：不改冻结文件，SOT §6.2 行已校准；未来重构波次随锚点 hunk 收敛 |

---

## 7. 风险登记册

| 风险 | 等级 | 处置 |
|---|---|---|
| OI-P7-1：项目侧 `.py` backend 发现（D-P7-02）本波未实装 | 低（设计面） | 移交 P8+ 评估面（D-P7-02 选择明注；涉 ProjectIR 扩展则届时按 S2 走人工） |
| T07 = S4 评估记录面（零新增依赖、无运行时行为开关） | 低 | 人工批准门禁面已预置（D-P7-06）；真实 runtime 引入 = S4 触发，须人工 |
| 测试侧-only handler 注册（D-P7-13） | 低 | src 侧 handler 表 = 冻结 core 面；P8 persistence/replay 波评估是否提升 src |
| toy fidelity 抽象（Case C = 契约非物理） | 低（设计面） | D-P7-04 明注；真实数值 backend 引入 = S5 评估面 |
| LLM 验证 = scripted fakes only（P7-INV-3 零网络） | 低（设计面） | 真实 provider 集成属 P6 llm runtime 面（冻结）；P7 不拥有网络缝 |
| last-run 诊断视图（D-P7-15，单线程假设） | 低 | 并发 backend 非 P7 范围（D-P7-01 同步纪律） |
| conftest.py L164 docstring handlers 口径 stale（W1 冻结面） | 低（登记面） | ERR-P7-17 carryover：冻结文件不动，SOT §6.2 已校准（G7-R1 复核确认） |
| ERR-P7-14 第 2 条行号引用 L1510/L1517 锚定 d598cfb blob 几何 | 低（历史勘误） | G7-R1 两 reviewer 独立字节实证自洽（d598cfb blob 该两处确 0x08 ×4；HEAD 同逻辑行 L1516/L1523）；无动作 |
| gate ③ 控制字节预扫（ERR-P7-14 item 3） | 期望属性 | 本 gate 已执行 = 0；后续各 gate ③ 同款重扫 |
| 边界方法 1 白名单闭集全枚举（24 允许根 + 13 禁止） | 期望属性 | 未来波次（P8+）须在其内，否则需锚点扩块（Leader-owned） |
| ERR-P7-09 policy 匹配裁定 SOT-canonical | 登记面 | (b)/(c)/(e) 三裁定已 §3.6/§3.7/§5.1 补注，g7/host 同构 |
| G6 carryover：uv.lock 漂移 / smoke 凭据路径手动专用 / proposal_id 无 nonce / AD-4 字段名耦合 / TestP6Boundary fail-loud / 边界文件 AST 负载增长 | 低（P6 报告 §7） | 按 P6 口径处置；P8 评估面 = proposal_id nonce + `uv lock` |

---

## 8. HARD STOP 逐条核验（Plan §24，L1214–1290）

- **S1（需要改变 Architecture Kernel invariant）— 未触发**。`git diff e816a64..HEAD -- src/engine_v2/core`
  = 空（23 白名单文件全部为 `src/engine_v2/dynamics` 新增 + tests 新增/纯追加 + fixtures；
  SOT §0.4 第 1 条「不改 core/ 任何文件」成立）；core 32 子模块 / 308 导出冻结不变量零改动；
  K1–K8 语义面实证（K4 Prompt 不定义世界权限 / K5 backend=policy 只产 ProposedEffect 零直写 /
  K6 origin = DYNAMICS_BACKEND 可追踪 / K7 Case C 双跑 byte-identical / K8 Deployment 与
  Game Project separation = fixtures 两文件分离）4/4 reviewer 独立一致。
- **S2（Public Contract 两种同样合理但不兼容设计，Agent 自行选一并扩散）— 未触发**。
  交付公共面单设计：恰 1 个 Protocol（`WorldDynamicsBackend`）、1 个组装点
  （`host.run_dynamics_turn`）、1 个诊断载体（`DynamicsDiagnostic`）、35 导出名单一账本
  （§8.2 序双等）；ERR-P7-09 三裁定（policy 匹配 / host 规则目标 / composite fidelity）
  全部 W4 交付前 SOT §3.6/§3.7/§5.1 显式补注，裁定面单一，无并行不兼容设计。
- **S3（为通过测试需要 destructive migration）— 未触发**。23/23 文件纯新增、0 删除行；
  v1 根（`src/engine`、`tests/engine` 旧树）未触碰；无任何持久化 save 格式变更。
- **S4（引入新的重大依赖 / License 风险）— 未触发**。纯 additive：`pyproject.toml` 不在
  diff 内；零新增第三方依赖（T07 = 评估记录 only，零运行时行为开关，D-P7-06）；
  无 GPL/AGPL/LGPL/MPL 复用、无游戏引擎、无数据库、无外部 physics runtime、
  无 JS/Node、无本地服务框架；23 行内无新 requirements 文件、无 vendored 代码。
- **S5（Backend 无法满足 replay/checkpoint Contract）— 未触发**。toy 数值 backend 满足
  checkpoint/restore/branch 契约（G3 证据：checkpoint JSON-clean / restore 确定性续延 /
  同一 cp 两次独立 restore 双 continuation byte-identical / metadata 三布尔全真）；
  LLMWorldDynamics `replayable=False` 为诚实自报且非核心数值 backend（数值确定性由 toy
  承载），branch 等价性测试不依赖 LLM 重放。

---

## 9. 结论

- G7-R1：**4/4 通过、0 补充、0 阻塞、0 执行失败**（G7 实质轮 0/3；2 INFO findings 同靶 =
  历史勘误几何自洽，字节实证，无动作）；
- 门禁判据 **4/4 met**（Plan §16 G7 逐字：Case A / Case B / Case C / kernel if-elif 禁令；
  4 名独立盲审 reviewer 各自完整核验 + 独立复跑 ①–⑥ 全步对账一致）；
- gate 运行序 ①–⑥ 全绿（2925 / ruff 0 / diff 23 / 边界 17 / 回归 57 / e2e + smoke 34）；
- 白名单 diff = **23**（封闭集，集合 + 计数等值，多一少一 = 门禁失败，实测恰好 23）；
- HARD STOP S1-S5 未触发（§8 逐条核验）；
- 各波实质修复轮：W1 1/3、W2 1/3、W3 0/3、W4 0/3、W5 1/3（ERR-P7-14，0x08 词边界腐蚀）、
  G7 0/3——全部在预算内；W5 docs 闭合 ×4（ERR-P7-13..17）不消耗补充预算；
- 未使用 CONDITIONAL PASS（Plan §21 默认禁止）。

**下一阶段**：P8（Persistence / Replay / Dev Control Plane，Plan §17）；
HARD STOP 清单（Plan §24 S1-S5）持续适用；OI-P7-1（项目侧 `.py` backend 发现）进入 P8 评估面。
