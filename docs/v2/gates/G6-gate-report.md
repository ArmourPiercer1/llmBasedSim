# G6 Gate Report — Phase 6 LLM Runtime / Prompt / Capability Routing（终版）

按 `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` §15、§21、§24 编制。
G6-R1 盲审 4/4 通过、0 补充、0 阻塞、0 执行失败（六条准则 4 名 reviewer 独立复跑全部 met），
本报告为 G6 最终交付点记录。

---

## 0. 基础信息

- **Gate**: G6（Phase 6 — LLM Runtime / Prompt / Capability Routing 门禁）
- **Commit SHA**: `28a91bb`（HEAD，Phase 6 最终交付点；纯文档闭合）；审查点 = `00b0e4b`（W6 R1 闭合，
  代码与 `23d40fe` 完全一致）；G6-R1 文档闭合 `28a91bb`（ERR-P6-14，零代码 diff）
- **分支**: `architecture-v2`
- **审查基准**: `f4fc42a`（P6 设计冻结基线，套件 2669）.. `28a91bb`；
  P6 设计文档（SOT）= W0 交付物 + 勘误链 ERR-P6-1..14（§9，文档 1056 行）
- **测试基线**: 全量 **2813 passed / 0 failed**（gate ① 真实输出，`.venv/bin/python -m pytest tests/ -x -q`；
  P6 全程 +144 = 2813 − 2669：W1 +22（profiles 10 + deployment 12）/ W2 +12（router 12）/
  W3 +12（adapter 12）/ W4 +37（structured 12 + registry 12 + assembler 13）/ W5 +18（policy 10 +
  staleness 8）/ W6 +43（critic 8 + gate 20 + adversarial 9 + Leader TestP6Boundary 6）；
  SOT §8.3 eq.4 = 138 平铺 + 6 边界 = 144 对账一致）；
  gate ② `ruff check src/engine_v2/llm src/engine_v2/prompts tests/engine_v2 scripts` → `All checks passed!`
- **审查执行**: 全部 `qiyuan-self / qwen3.8-27b`（2026-08-20 人工路由覆盖）；设计阶段 4 轮盲审
  （R1 2 BLOCK+8 补充 F-01..F-08 → R2 3 补充+42 文档/信息 F-09..F-16 → R3 2 补充+11 文档/信息
  F-17/F-18 → R4 4/4 通过 + 8 处免费文档修正 F-19..F-25；设计冻结 `f4fc42a`）+ 波次审查
  （W1-R1..R3（R3 终验 4/4）/ W2-R1 / W3-R1 / W4-R1 / W5-R1 / W6-R1，全部 4/4 通过闭合，
  勘误链 ERR-P6-1..13）+ 门禁阶段 **1 轮 × 4 名独立盲审（G6-R1，全新一轮全新盲）**，
  四裁决协议（通过/投机通过/补充内容/阻塞）

---

## 1. §21 字段

```text
Gate: G6
Commit SHA: 28a91bb
Tasks completed: P6-T01 ~ P6-T10（全部）：
                  T01 = W0 设计期 v1 LLM/parser/prompt 调用链 survey + K8 12 名探针面 + 冻结缝清单（设计冻结）；
                  T02 = W1 profiles.py InferenceCapabilityProfile（8 导出）+ diagnostic 载体（21 码闭集）；
                  T03 = W1 deployment.py DeploymentProfile（8 导出）+ W2 router.py resolve_capability（4 导出）；
                  T04 = W3 adapter.py provider-neutral structured inference adapter（11 导出，
                         HttpxInferenceBackend/FakeInferenceBackend/固定时钟双缝）；
                  T05 = W4 assembler.py PromptAssembler L0-L4 + provenance（12 导出）+ registry.py（5 导出）
                         + structured.py（wire 模型 LLMActionProposal + extract_json_robust 三族 parser）；
                  T06 = W5 policy.py LLMPolicy decide 9 步参考实现（414 行，零 asyncio，D-P6-13 导入纪律）；
                  T07 = W5 staleness.py revision-aware 结果处理（84 行，委托冻结 core 再验证管线，零重复实现）；
                  T08 = W6 critic.py 可选 behavior critic + one-shot repair（112 行 4 导出，decide 步骤 7 懒 import）；
                  T09 = W6 fake-model 确定性测试（gate 20 = SOT §5.2 1:1 + adversarial 9 + conftest 11 fixture
                         + 8 fixture 文件，S3 脚本化 JSON 攻击面）；
                  T10 = W6 scripts/llm_smoke.py（162 行，exit 3/0/4 钉死，真实凭据不进 CI secrets，D-P6-17）；
                  + 锚点同步（test_import_boundary.py TestP6Boundary 6 方法纯追加块 + pyproject +httpx，
                    Leader 执行，白名单 #24/#37）
                  + G6 文档级闭合（ERR-P6-1..14：6 处开发前原位修正 + 8 处 R1 轮后 DOC 修正，全部登记）
Tasks waived: 无
Tests: 2813 passed / 0 failed（真实输出，.venv python，-x -q）
Known failures: 0
Architecture deviations: 见 §6 偏差登记（B3 受控偏离 ERR-P6-6 + 自裁登记面，全部已披露/已登记）
Open risks: 见 §7 风险登记册（uv.lock 漂移等，均低）
Human review required: 否（HARD STOP S1-S5 未触发，逐条核验见 §8；门禁实质轮 0/3 在预算内，
                       按 2026-08-20 协议无需人工批准）
Decision: PASS
```

---

## 2. 门禁判据验证（Plan §15「G6」L661-666 六条，逐字 + 双重证据）

| # | 准则（Plan L661-666 逐字） | 实现面 | 测试面 | 实测证据（G6-R1 四 reviewer 独立复跑确认 met） |
|---|---|---|---|---|
| 1 | 假模型可完整跑 | `adapter.py` FakeInferenceBackend（(logical_role, base_revision, seq) 脚本化）+ `policy.py` decide 9 步 + PolicyWakeupHook 管线 + S3 脚本化 JSON 攻击（bob/hit/0.9） | g6_01..g6_04（#1-4） | gate ⑥ 隔离复跑 20/20；假模型 e2e 全链零诊断、9 键 trace 封闭、K7 双跑字节相等 |
| 2 | user DeploymentProfile 可以改变实际模型而不修改游戏项目 | `deployment.py` load_deployment（两节形状）+ `router.py` resolve_capability；双部署 fixture（model_high tier 3 / model_alt tier 2）零游戏项目改动 | g6_05..g6_06（#5-6） | 同一游戏项目 fixture 分别指向两部署文件 → resolved_model 不同（model id/tier 断言），游戏项目字节零改 |
| 3 | Prompt override 不提升 context capability | `assembler.py` CONTEXT_VARIABLES = 13 名封闭集（== ActorDecisionContext 13 字段，集合等值）；未授权变量 = "null" 字符串化 | g6_07..g6_09（#7-9） | 13==13 集合等值（reviewer 独立复核）；override 注入未授权变量 → 渲染面 "null"，capability 位不升级 |
| 4 | stale ActionProposal 不会直接 commit | `staleness.py` valid_until/effective_valid_until + 委托冻结 core 再验证管线（revalidation.rebased_proposal，零重复实现） | g6_10..g6_11（#10-11） | base<current → stale → 再验证面；g6_11 REJECT 面无世界副作用（scheduler REJECT face 消费） |
| 5 | trace 不记录 credential | api_key_env 名字化（只引用变量名）+ `LLM_CALL_PAYLOAD_KEYS` 9 键封闭集 + FAKE_PROBE_KEY 探针 | g6_12..g6_13（#12-13） | 探针值 PROBE-VALUE-DEADBEEF01 在 trace payload 零出现；payload 键集 == 9 键封闭集（== core 冻结集） |
| 6 | LLM parser 不依赖 DeepSeek/OpenAI 特定语义作为 Core Contract | `structured.py` extract_json_robust 三族（合法 JSON / 嵌入 JSON / 修复轮）+ InferenceBackend Protocol + K8 12 名扫描 | g6_14..g6_16（#14-16）+ test_structured 12 | K8 27 文件域 0 命中（R2 独立复扫 27/0；正式口径 0，过度严格纯子串变体 41 子串误报/0 正式命中）；三族 parser 行为断言全绿 |

---

## 3. gate 运行序 ①-⑥（真实输出）

1. `.venv/bin/python -m pytest tests/ -x -q` → **2813 passed in 16.14s**（0 failed）；
2. `.venv/bin/python -m ruff check src/engine_v2/llm src/engine_v2/prompts tests/engine_v2 scripts` → **All checks passed!**
   （L582 字面命令 G6-R1 后已补 scripts 路径，F-G6-02）；
3. `git diff --name-only f4fc42a..HEAD -- src tests pyproject.toml scripts` → **恰 37 行**
   （pyproject 1 / scripts 1 / src 11 = llm 8 + prompts 3 / tests 24 = core 1 + llm 12 + prompts 3 + fixtures 8）；
4. `TestP6Boundary` → **6 passed, 14 deselected**（边界文件总 20/20 含冻结 B1/B2/B3 + P3/P4/P5）；
5. 回归 = `tests/engine_v2/core/` **1959 passed** + `test_p5_gate_scenario.py` **20 passed**（零回退）；
6. fake e2e（`test_p6_gate_scenario.py` 隔离 **20 passed**）+ `scripts/llm_smoke.py` 无凭据进程内 dry-run
   → **exit 3**（引导文案只打印 env 变量名 FAKE_PROBE_KEY，永不打印值；有凭据路径 = 手动专用真调，D-P6-17）。

---

## 4. 白名单 diff（K8 封闭集 37）

= SOT §3.13 #1-37 **集合 + 计数等值**（R1 双向独立对账 + 与边界文件内 `_P6_WHITELIST_37` 元组三向一致；
R2/R3/R4 各自独立复算）。顺序语义 = 集合 + 计数等值（`git diff --name-only` 恒按路径字母序输出、
§3.13 表 = 波次序；字面顺序敏感读法结构不可行——ERR-P6-14 F1-R1-INFO-1 登记，封闭集语义不变）。
多一少一 = 门禁失败：实测恰好 37。

---

## 5. 审查记录（盲审轮次）

- **设计阶段 R1-R4**（4/4 通过冻结）：R1 2 BLOCK+8 补充 → R2 3 补充+42 文档/信息 → R3 2 补充+11 文档/信息
  → R4 4/4 通过（8 处免费文档修正 F-19..F-25）；设计冻结 `f4fc42a`。
- **波次审查**：W1-R1..R3（R2 含 L519 K8 口径关键更正 F-31；R3 终验 4/4）/ W2-R1 / W3-R1 / W4-R1 /
  W5-R1 / W6-R1——全部 4/4 通过、0 补充、0 阻塞、0 执行失败闭合；实质轮全部 0/3（文档面修正不占补充预算，
  2026-08-20 gate 政策）。
- **G6-R1（本轮）**：4/4 通过、7 findings（3 DOC + 4 INFO）、0 BLOCK/SUPPLEMENT、0 执行失败；
  引文核验 85/104/42/68 全部落盘复核；gate ①-⑥ 四 reviewer 独立复跑全绿且互相对账一致；
  唯一授权 git 命令各执行恰好一次。处置：
  - **F-G6-01**（R1，DOC，已采纳）：SOT L125 模块依赖 DAG 句漂移——4 子项全部 Leader 字节实证
    （11 模块 AST import map + RuntimeDiagnostic 构造点计数）+ Leader 独立另发现 5 处 per-module 缺边，
    同 hunk 七子编辑原位修正（5 per-module 边补全 + 汇总句 +critic（wire 模型）/ policy 括注
    +RuntimeDiagnostic + 诊断句重写含 6/3/5/7/1 构造点计数与封闭集零外部 import 陈述）。
  - **F-G6-02**（R2，DOC，已采纳）：§3.13 gate 步骤 2（L582）ruff 命令补 ` scripts`（smoke = #36）。
  - **F-G6-03**（R2，DOC，已采纳）：L17 环境行 httpx「传递依赖」→「直接依赖 ≥0.28，W6 白名单 #24」。
  - **4 INFO**（零行动登记）：gate ③ 顺序语义（F1-R1-INFO-1）；S4 措辞精度（R2-I1：python-dotenv =
    v1 时代既有依赖，P6 依赖 delta = 恰 +httpx>=0.28）；uv.lock 未重同步（R3-I1 / R4 两名独立盲审同靶命中，
    见 §7）。
- 全部修正为纯文档面（零代码 diff，不占补充预算）；闭合状态：套件 2813/0（复验）、ruff 净、
  gate ①-⑥ 全绿、TestP6Boundary 6/6、K8 27 文件域 0/0。

---

## 6. 偏差登记

| # | 偏差 | 裁定 / 登记 |
|---|---|---|
| D-P6-1 | W3 `test_adapter.py` 直接 import httpx vs B3「网络/进程 IO」黑名单 | **受控偏离**（ERR-P6-6）：Leader W3 提前落地 B3 P6 例外（P5 先例 ERR-P5-16 体例；仅豁免该文件 httpx 类命中，provider/v1 零容忍保持；方法体注释明注「第二处受控偏离」）；dev 零 import 改写绕行 |
| D-P6-2 | InferenceTransportError 三属性 code/status/refs vs SOT 异常规格行仅列 code/status | 实现面登记（非偏离）：generate 步骤 6/7 显式引用 refs → refs 补默认空元组（A-W3-1，唯一 A-W 残留） |
| D-P6-3 | 真实 P4 上下文（frozen dataclass/frozenset）crash assembler L3 JSON 清洗 | JSON-clean twin 裁定（ERR-P6-10(a)）：ALL decide/assemble 测试路径 = conftest JSON-clean twin（alice/unauthorized_context）；world/scheduler 侧可用真实 P4 harness（make_p4_world 先例） |
| D-P6-4 | `critique_instruction` 签名 `Sequence[str]` vs SOT §3.8 tuple 钉面 | 自裁登记（F-R1-01，ERR-P6-13）：全部钉死调用点传 tuple，行为等价 |
| D-P6-5 | gate 主链直接调 `policy.decide()` 而非 `run_policy_decide` facade | 自裁登记（F-R1-02，ERR-P6-13）：facade 唯一增量 = B-CON-5 actor 匹配守卫，g6_20 机械验证反例（PolicyActorMismatchError） |
| D-P6-6 | AD-8 双跑范围 = decide/assemble 全链（含坏 JSON）而非 e2e 世界链 | 自裁登记（R3-2，ERR-P6-13）：e2e 世界双跑归 g6_17（SOT D-P6-19 + §5.2 #17 交叉支持） |
| D-P6-7 | uv.lock 未随 pyproject httpx 增加重同步 | G6-R1 登记（R3-I1/R4 独立同靶）：uv.lock 按设计在 37 白名单与 gate ③ 路径域之外；后续维护波次 `uv lock` 重同步（非闭合前置） |

---

## 7. 风险登记册

| 风险 | 等级 | 处置 |
|---|---|---|
| uv.lock 与 pyproject httpx 漂移（clean env `uv sync` 不会装上 httpx） | 低 | 维护波次 `uv lock` 重同步（D-P6-7；venv 实装 httpx 0.28.1，门禁机械面不受影响） |
| smoke 有凭据路径 = 手动专用真调（真实网络） | 低（设计面） | gate ⑥ 机械面 = 无凭据 dry-run exit 3 确定性（D-P6-17）；凭据值永不打印 |
| `proposal_id` 无 nonce → 同 (actor,tick,base) 重提交覆盖 lifecycle 记录 | 低（冻结 W4 规格固有） | g6_11 已钉语义（FAILED 同键覆盖）；P8 评估面（ERR-P6-13 R4-F5） |
| AD-4 钉面硬断言耦合冻结 `DeploymentEntry` 字段名 + 夹具字节 | 低 | 未来 schema 改名/夹具编辑会断钉（登记面，非 W6 缺陷；R4-F4） |
| TestP6Boundary 块 fail-loud：未来波次 P6 族新文件不扩块即红 | 低（期望属性） | 方法 1/2 封闭集断言（ERR-P6-13 (3)） |
| 边界文件 12 名 AST 负载随后续 Leader hunk 增长 | 预期 | 排除机制不变；84/82/2 口径持续以独立复扫为准（ERR-P6-13 (4)） |
| t06 单文件 httpx 例外模式（冻结 `test_adapter.py:45`） | 登记 | ERR-P6-6 口径 govern 未来测试侧 transport 替身 |

---

## 8. HARD STOP 逐条核验（Plan §24，L1214-1290）

- **S1（需要改变 Architecture Kernel invariant）— 未触发**。P6 纯消费冻结缝（core 32 子模块 / 308 导出
  冻结不变量 K1-K8 零改动）：gate ③ 白名单 37 行**零** `src/engine_v2/core` 路径（由 G6-3 输出推导，
  四名 reviewer 独立一致）；冻结缝字节面抽查（core/trace.py 9 键封闭集、core/revision.py is_stale 语义、
  behavior_policy B-CON 面）与 SOT §2 缝清单一致。
- **S2（Public Contract 两种同样合理但不兼容设计，Agent 自行选一并扩散）— 未触发**。交付公共面单设计：
  恰 1 个 wire 模型（`prompts/assembler.py` LLMActionProposal，L0 层所有）、1 个 decide 入口
  （`policy.py` LLMPolicy.decide）、1 个 parser（`structured.py` extract_json_robust）、1 个 router
  （`router.py` resolve_capability）、1 个 staleness 面（`staleness.py`）；11 模块导出账本 70 与
  SOT §8.2 逐项对账一致；交付文件中无竞争第二设计。
- **S3（为通过测试需要 destructive migration）— 未触发**。37 行白名单纯追加：两个既有触及文件均验证为
  追加面（`pyproject.toml` 仅 +依赖行；`test_import_boundary.py` 纯追加块 L818-1231 位于 marker 之后、
  零新增顶层 import、块内全部 helper/常量解析至冻结定义、白名单元组序与 SOT 表 #1-37 一致）；
  37 行不含 `src/engine_v2/core`、`src/engine_v2/content`、`src/game` 任何路径（P1-P5 交付 .py 零改写）。
- **S4（引入新的重大依赖 / License 风险）— 未触发（披露）**。P6 依赖 delta = **恰 +httpx>=0.28**
  （BSD-3-Clause，小型纯 Python HTTP 客户端；不在 S4 风险类：GPL/AGPL/LGPL/MPL 复用、游戏引擎、数据库、
  物理 runtime、JS/Node、本地服务框架）。python-dotenv>=1.0 = v1 时代既有依赖（P5 基线在位，
  src/main.py:11 / src/web/app.py:17 消费），非 P6 新增（R2-I1 精度登记）。37 行内无新 requirements 文件、
  无 vendored 代码。
- **S5（Backend 无法满足 replay/checkpoint Contract）— 未触发（N/A）**。P6 无数值 backend；
  确定性双跑契约（K7）由 g6_17 + AD-8 承载（规范化 JSON 字节相等，2 独立实例，全绿）。

---

## 9. 结论

- G6-R1：**4/4 通过、0 补充、0 阻塞、0 执行失败**（G6 实质轮 0/3，文档面修正不占补充预算）；
- 门禁判据 **6/6 met**（4 名独立盲审 reviewer 各自完整核验 + 独立复跑 ①-⑥ 全步对账一致）；
- gate 运行序 ①-⑥ 全绿；
- 白名单 diff = **37**（封闭集，多一少一 = 门禁失败，实测恰好 37，集合 + 计数等值）；
- HARD STOP S1-S5 未触发（§8 逐条核验）；
- 未使用 CONDITIONAL PASS（Plan §21 默认禁止）。

**下一阶段**：P7（WorldDynamics，Plan §16）；HARD STOP 清单（Plan §24 S1-S5）持续适用。
