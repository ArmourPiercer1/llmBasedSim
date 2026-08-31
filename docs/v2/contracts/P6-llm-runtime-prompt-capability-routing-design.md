# P6 LLM Runtime / Prompt / Capability Routing 设计 — Phase 6 LLM 运行时 / 提示组装 / 能力路由 实现规范（Spec B）

- **任务**: P6-DESIGN（Phase 6 — LLM Runtime / Prompt / Capability Routing 架构设计，Plan §15；先例：P2-DESIGN / P3-DESIGN / P4-DESIGN / P5-DESIGN）
- **文档地位**: 等价于 Plan §15「Phase 6 — LLM Runtime / Prompt / Capability Routing」（Plan:618-669）的字段级 / 函数级实现规范：任务表 P6-T01~T10（Plan:626-637）+ 强制设计约束（Plan:639-657，允许 6 项 / 禁止 4 项逐字）+ G6 六条门禁（Plan:661-666）。Leader 预裁定 Leader-A1~Leader-A12 全部落为正式决策（§4，D-P6-01~D-P6-22 逐条引用裁定编号，零重新裁定）；开放设计项全部钉死为 D-P6-xx（含机械验证面）。Q27/GFlash 按本文档可"纯执行"实现 T01~T10 全部任务，无需再做架构判断。全部决策编号钉死为 **D-P6-01~D-P6-22**（§4）；全部行号引用已对冻结源逐行核验（SOT 文档 @ 本设计文档 commit 基线；v1 冻结文件锚定其预 P6 提交，§1.3），引用格式 `file:line`；Gate 断言共 **20 条**（§5.2，G6-1~G6-6 = 4+2+3+2+2+3 + 不变量 4 条 #17-20）；模块数 **11**、导出名总数 **70**（11 个模块 `__all__` 并集，§8.2 台账逐名核验）；P6 诊断码 **21** 枚（§8.1 闭集，三命名空间 LLMSIM_RESOLVER_* 6 / LLMSIM_INFERENCE_* 7 / LLMSIM_PROMPT_* 8）；文件白名单 **37**（§3.13 封闭集，含 scripts/ 域 1 文件）。
- **路由声明**: 2026-08-20 人工路由覆写（全任务 → qiyuan-self/qwen3.8-27b，P5 文档:5，ERR-P5-1 裁定 2 确认适用于全部 v2 任务与执行波次）**适用于 P6 全部任务与执行波次**。Plan §15 任务表默认模型列（Plan:628-637：T01 → GFlash、T02~T05/T07/T08 → QMax、T06/T09/T10 → Q27）为无人工覆写时的后备值，本期不执行。
- **分支与基线**: `architecture-v2`；**基线 SHA 占位 = `<P6-BASELINE-SHA>`**（= 本设计文档 commit，由 Leader 于 W1 开波时钉死，Leader-A9；gate 运行序 ③ 的 diff 左端以此为锚）。上游状态：G5 门禁闭合 PASS（P5 SOT §3.12 L569 gate 运行序全绿）；core 冻结基线 **32 模块 / 308 导出名**（`tests/engine_v2/core/test_closeout.py:96-129,226`，P6 零触碰，D-P6-01）；P5 冻结面 = `src/engine_v2/content/` 7 模块 + `src/engine_v2/plugins/` 3 模块（零修改，D-P6-01）；全套测试基线 **2669 passed / 0 failed**（Leader 维持，P6 只增不改）。
- **权威输入**:
  - `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md`（下称 **Spec**）§4 K1-K8（L242-339：K4 L295-303、K5 L305-313、K8 L330-339 逐字）、§5.4 DeploymentProfile（L403-420）、§5.5 游戏可声明的 Inference Capability（L422-450，yaml 形状 L426-441 逐字）、§6 ProjectIR（L454-457）、§9 Revision Model（L642-678：四修订字段 L650-657 + revalidation MUST L669 + ACCEPT/REBASE/REPAIR/REJECT L673-677）、§11.3 ActionProposal（L770-785）、§11.4 Action Lifecycle（L787-802）、§12.2 BehaviorPolicy（L814-838，`async def decide` L820）、§13 Context/Capability（L872-909：13.3 Prompt override 不提升权限 L907-909 逐字）、§14 Prompt Architecture（L913-935：L0-L4 层定义 L917-923 逐字 + L4 untrusted content 清单 L925-931 逐字 + MUST 作为数据处理 L933 + 高级开发者 MAY 替换 PromptAssembler L935）、§31 LLM Runtime（L1631-1674：31.1 adapter 签名 L1633-1645、31.2 Model Router L1647-1656、31.3 记录字段 L1658-1672 + Credential MUST NOT 进入 trace L1674 逐字）、§39 Security（L1905-1940）、§42 测试层级（L1989-2053：42.1 NO LLM / NO NETWORK / NO GUI L1995-1999 逐字）
  - `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md`（下称 **Plan**）§15（L618-669：任务表 L626-637、强制设计约束 L639-657、G6 L661-666 全部逐字）、§21 Gate 报告格式（L888-903，默认禁止 CONDITIONAL PASS L905）、§24 HARD STOP S1-S5（L1212-1288）
  - `docs/architecture/adr/ADR-004-capability-declaration-and-user-selected-models.md`（45 行全读：决策 1-3 L19-32、fallback 梯度 L41、Mock/Fake 纪律 L45）
  - `docs/architecture/adr/ADR-002-kernel-uncoupled-from-langgraph-agent-as-policy.md`（43 行全读：决策 1-3 L19-30、Policy 词表 L24-28）
  - `docs/v2/contracts/P5-project-format-module-plugin-dsl-design.md`（下称 **P5 SOT**，997 行；结构模板 + 冻结消费面：§3.1 InferenceCapabilityProfile L278 / PromptPolicy L279 字段封闭条款、§3.11 锚点同步 L510-528、§3.12 白名单与 gate 运行序 L529-570、§5.2 断言体例 L696-720、§6.4 TestP5Boundary 5 方法规格 L787-798、§8.3 计数等式体例 L905-921、§9 勘误格式 L939-941）
  - P5 冻结代码（只读消费面）：`src/engine_v2/content/schemas.py:395-426`（InferenceCapabilityProfile / PromptPolicy 字段封闭）、`src/engine_v2/content/project_ir.py:245,357-358`（build_ir 的 capabilities/prompts 填充）、`src/engine_v2/content/loader.py:46-60`（LAYOUT_REQUIRED / LAYOUT_OPTIONAL 9 模板）、`src/engine_v2/content/validator.py:88-103,316-347`（12 名禁名词 + check_deployment_leakage）
  - 冻结 core 契约（只读消费面；P6 零修改）：`core/behavior_policy.py:54-108`（BehaviorPolicy Protocol B-CON-1~5 + run_policy_decide 唯一执行门面）、`core/actions.py:122-188`（ActionTiming / FallbackSpec / ActionProposal base_world_revision 必填 L183）、`core/context_provider.py:286-323`（ActorDecisionContext 13 字段 + ContextProvider 协议，build 签名 L323）、`core/capability.py:55-190`（Capability / CapabilityTable / check_capability / DEFAULT_NPC_CAPABILITIES）、`core/revalidation.py:56-272`（RevalidationDecision / revalidate_proposal / rebase_proposal）、`core/revision.py:34-91`（Revision / INITIAL_WORLD_REVISION / next_revision / is_stale / RevalidationOutcome）、`core/trace.py:56-88,107-108`（LLM_CALL_PAYLOAD_KEYS 冻结 9 键 + TraceKind.LLM_CALL/PROMPT_ASSEMBLY）、`core/scheduler.py:316-337,339,1507-1530`（WakeupHook 协议 / WakeupHookRegistry / step / submit_proposal）、`core/ids.py:80-88,255-260`（_TypedId 直接构造口径 / new_action_instance_id）、`core/provenance.py:41-74`（OriginKind / Provenance）、`core/serialization.py:54,82`（dump_json / assert_json_clean）
  - P0 骨架预留槽（P6 唯一新代码落位）：`src/engine_v2/llm/__init__.py`（9 行占位 docstring）、`src/engine_v2/prompts/__init__.py`（7 行占位 docstring）；`src/engine_v2/README.md:21-22`（llm/ = Phase 6、prompts/ = Phase 6）
  - v1 LLM 调用链（T01 survey 对象，只读）：`src/llm/parser.py`（104 行）、`src/prompts/loader.py`（105 行）、`src/models/config.py:9-15`（LLMConfigModel）、`src/graph/game_graph.py`（952 行，LLM 调用点 7 处）、`src/agents/init.py`（378 行）、`src/config/loader.py:17-21` + `config/simulation.yaml:7-13`
- **环境事实**: python 3.12 venv（`.venv/`，无 pip，禁止安装任何包）；已装 = pydantic v2 / pyyaml / httpx（传递依赖，可用）/ structlog / rich；ruff line-length=100 target py312（`pyproject.toml`）；pytest `asyncio_mode=auto` 但 **P6 代码零 asyncio**（Leader-A3）；套件基线 2669/0；K8 12 名黑名单 = openai/anthropic/langchain/litellm/ollama/gemini/gpt/claude/llm/provider/api_key/base_url（`test_import_boundary.py:225-240` P4_LLM_PROVIDER_BLACKLIST 逐名；`content/validator.py:88-103` 拼接构造同一集合；casefold + 词边界，下划线 = 词字符）。
- **写面（W0，本设计任务仅两个文件可写）**: 本文档 + `.review-drafts/p6-w0-design-report.json`。实现波次写面 = §3.13 白名单 37 文件（封闭集）。

---

## §1 定位

### 1.1 十件 scope（T01-T10 逐任务一句落点）

P6 = 「LLM 运行时 / 提示组装 / 能力路由」十件，对应 Plan §15 任务表（Plan:626-637）：

| # | 任务（Plan 任务表逐字） | 落点（本文档锚点） |
|---|---|---|
| T01 | v1 LLM/parser/prompt 调用链 survey | §7.4 v1 语义 → v2 落点表（14 行逐环节；本设计 W0 完成，实现波次零 survey 工作） |
| T02 | InferenceCapabilityProfile schema | **消歧（Leader-A2）**：game 侧 = P5 已冻结 `content/schemas.py:395-416`（零修改）；P6 交付 = model 侧 `llm/profiles.py`（ModelCapabilityProfile + tier 尺度 0-4 + 匹配语义，§3.1） |
| T03 | DeploymentProfile + user-side model resolver | `llm/deployment.py`（§3.2，用户侧加载 + env 名化 credential）+ `llm/router.py`（§3.3，capability → deployment 匹配 + fallback 梯度 + 诊断） |
| T04 | provider-neutral structured inference adapter | `llm/adapter.py`（§3.4，wire 协议接口 + httpx 同步客户端 + FakeInferenceBackend + 注入时钟 seam）+ `llm/structured.py`（§3.5，JSON 提取 + wire 模型 + parse retry） |
| T05 | PromptAssembler L0-L4 + provenance | `prompts/registry.py`（§3.9，模板加载 + 路径纪律 + 变量解析）+ `prompts/assembler.py`（§3.10，L0-L4 组装 + 每层 provenance + token 估计 + override 不提升权限机械面） |
| T06 | LLMBehaviorPolicy reference implementation | `llm/policy.py`（§3.6，LLMPolicy 同步门面，B-CON-1~5 全合规，经 run_policy_decide 接入） |
| T07 | revision-aware async result handling | `llm/staleness.py`（§3.7，**时间语义非协程语义**，Leader-A3）：revision-aware 结果处理 + revalidate_proposal/rebase_proposal 集成 + valid_until 语义 |
| T08 | optional behavior critic / one-shot repair module | `llm/critic.py`（§3.8，feature flag 默认关，Leader-A6；one-shot repair = 带校验错误反馈的第二次调用） |
| T09 | fake-model deterministic tests | `llm/adapter.py` FakeInferenceBackend 核心 + `tests/engine_v2/llm/` 全组（§6；fake e2e + stale e2e + 双跑字节相等） |
| T10 | actual provider smoke-test script（不进 CI secrets） | `scripts/llm_smoke.py`（§3.13 波次表 W6 + §4 D-P6-17 + §6.2 预期面；无 credential 退出码 3 / 有 credential 单次真实调用 / 异常 4；不进 CI，Leader-A10） |

### 1.2 G6 六条逐字回应（Plan:661-666 逐字）

| # | G6 条款（逐字，Plan:661-666） | 实现手段（本文档锚点） | 决策 | 断言 |
|---|---|---|---|---|
| G6-1 | 假模型可完整跑； | 确定性 headless 场景（§5.1 S3/S4）：P6 fixture 项目（合法 P5 项目：P5 validator 零诊断 + capabilities 节 + prompts 节 + 模板文本文件）+ `FakeInferenceBackend`（脚本化、确定性：按 (logical_role, base_revision, 调用序号) 返回预制响应，含结构化输出与一次坏 JSON 情形）+ LLMPolicy 经 `run_policy_decide`（behavior_policy.py:83）接入 scheduler wakeup → N tick `step()`（scheduler.py:1507）→ 提案 → revalidation → commit；断言链 = trace 含 llm_call（9 键齐全）+ action_proposal + 提交提案可回溯 | D-P6-14 | #1-#4 |
| G6-2 | user DeploymentProfile 可以改变实际模型而不修改游戏项目； | 路由层只读用户侧 deployment 文件（§3.2/§3.3）：同一项目 fixture + 两份部署 fixture（deployment.yaml / deployment_alt.yaml）→ `resolve_capability` 产出不同 `ResolvedModel.model_id`；游戏项目字节零变更（sha256 断言） | D-P6-05/07 | #5-#6 |
| G6-3 | Prompt override 不提升 context capability； | assembler 输入只来自 `ActorDecisionContext`（context_provider.py:286-314）授予面：`CONTEXT_VARIABLES` 封闭供给集 = context 13 字段名（§3.10）；override 仅可替换 L1/L2 游戏文本（D-P6-12 自裁；Spec:935 = MAY 替换 + capability boundary 不变面；Spec:907-909「自定义 PromptAssembler MUST NOT 自动获得未授权数据」= 不提升面），L0/L3/L4 封装 = 引擎固定；未授权字段投影 = `"null"` 而非数据 | D-P6-12 | #7-#9 |
| G6-4 | stale ActionProposal 不会直接 commit； | P6 零直写（P6-INV-2）：提案唯一提交入口 = `scheduler.submit_proposal`（scheduler.py:1520）既有 revalidation 管线（core/revalidation.py:107 五步判定）；stale e2e = fake 调用期间世界 revision 推进 → REJECT 路径 + FAILED 生命周期 | D-P6-19 + §3.7 | #10-#11 |
| G6-5 | trace 不记录 credential； | credential 模型 = env 名化（§3.2：`api_key_env` 只持变量名，值经 os.environ 在调用点解析）；llm_call payload 键集 == `LLM_CALL_PAYLOAD_KEYS`（trace.py:76-88）冻结 9 键（无 credential 位）；机械测试 = 注入假 credential（拼接构造探针）到 env → 跑 e2e → 断言全 trace 序列化文本不含该值 | D-P6-04/20 | #12-#13 |
| G6-6 | LLM parser 不依赖 DeepSeek/OpenAI 特定语义作为 Core Contract。 | contract = 我方 Python 类型面（InferenceBackend Protocol + WireMessage/InferenceRequest/Response）+ 通用 JSON 提取（fenced / 裸 / 首尾杂文三族，`extract_json_robust`）；wire 协议 = 可替换接口（非 core contract 一部分，Leader-A4）；P6 src 12 名 casefold 词边界字符串字面量扫描 0 命中（标识符豁免，Leader-A5） | D-P6-08/09/13 | #14-#16 |

### 1.3 输入基线

**P5 冻结面（零修改，只读 import）**：

| 消费面 | 锚点 | P6 用途 |
|---|---|---|
| `InferenceCapabilityProfile`（id/capability/min_tier/ideal_tier/notes + ideal>=min 校验，字段封闭） | `content/schemas.py:395-416`；P5 SOT L278 | router 输入（§3.3）；P6 不扩展其字段（Leader-A2） |
| `PromptPolicy`（id/scope/template_ref/variables，字段封闭） | `content/schemas.py:418-426`；P5 SOT L279（template_ref = prompts/ 内相对路径） | registry 输入（§3.9） |
| `ProjectIR.capabilities / .prompts` 字段 | `content/schemas.py:517-518`（字段声明，ProjectIR 类 schemas.py:496 16 字段）；`project_ir.py:357-358`（build_ir 填充行） | fixture 项目经 build_ir 填充（§5.1 S1） |
| `LAYOUT_REQUIRED = ("game.yaml",)` + `LAYOUT_OPTIONAL` 9 模板（`prompts/*.yaml` → prompts 节；**模板 .md 文本文件不在闭集内 = P5 loader 不可见**） | `content/loader.py:46-60` | Leader-A12 模板文件读法的前提（§3.9） |
| 18 诊断码闭集（`DIAGNOSTIC_CODES`）+ `check_deployment_leakage`（12 名 casefold 词边界；`llmsim`/`api_key_env` 不命中口径） | `content/schemas.py:112-133`（18 码闭集）+ `content/validator.py:88-103,316-347`（12 名闭集 + leakage） | P6 不触碰 P5 validator（Leader-A11）；词边界口径移植到 TestP6Boundary |
| P5 `Diagnostic`（code/severity/path/message/refs，code 闭集校验构造期拒绝）+ `DiagnosticSeverity` | `content/schemas.py:523-548`（含构造期 validator L542-548） | P6 **不自造语义、但新立本地载体**：P6 诊断载体 = P6 自有 `RuntimeDiagnostic`（§3.11，字段与 P5 Diagnostic 同构；severity 复用 P5 `DiagnosticSeverity`，跨包只读 import，Leader-A11 先例；validator 镜像 P5 L542-548 口径改锚 P6 21 码闭集）；**P6 21 码入 P6 自有闭集常量 `P6_RUNTIME_DIAGNOSTIC_CODES`，不扩 P5 18 码**（P6 运行时诊断 code ∈ P6 21 码闭集；P5 18 码 = 项目文件 validate 期面，两闭集零交集，机械核验 = §6.2 集合不相交断言） |

**core 冻结面（零修改，只读 import）**：B-CON-1~5 协议与门面（`core/behavior_policy.py:54-108`：decide 同步单参、返回 `ActionProposal | None`、actor_id 一致、类体 import 面静态扫描、run_policy_decide 唯一执行点且不预检 base 漂移——stale 判定唯一属 revalidation）；`ActionProposal.base_world_revision` 必填（`core/actions.py:183`，D-13）；`ActorDecisionContext` 13 字段（`core/context_provider.py:286-314`）；revalidation 四结果（`core/revalidation.py:107-114,261-272` + `core/revision.py:91`）；`is_stale`（base < current 即陈旧；valid_until 非 None 时 current > valid_until 亦陈旧，current == valid_until 不陈旧，`core/revision.py:78-88`）；`LLM_CALL_PAYLOAD_KEYS` 冻结 9 键（`core/trace.py:76-88`：logical_role/profile/resolved_model/input_token_estimate/prompt_metadata_ref/output_ref/latency_ms/parse_retry/base_revision，credential 永不出现）+ `TraceKind.LLM_CALL` / `PROMPT_ASSEMBLY`（P6 起产生记录，trace.py 注释自述）；WakeupHook 协议（`core/scheduler.py:316-337`：on_wakeup(actor_id, view, clock, reason) → Sequence[ActionProposal]）+ `WakeupHookRegistry`（:339）+ `step`（:1507）+ `submit_proposal`（:1520：revalidation → ACCEPT 入队 / REJECT 记 FAILED）；同步 step 面、全 engine_v2 零 asyncio（scheduler.py:105-111 纪律段：datetime/time/random/asyncio 黑名单；P6 继承此纪律并扩展为 §3.12 双例外口径，D-P6-13）；`_TypedId` 构造不做词法校验（`core/ids.py:83-85` 确定性构造口径）；`dump_json` / `assert_json_clean`（`core/serialization.py:54,82`）；`OriginKind.BEHAVIOR_POLICY` + `Provenance`（`core/provenance.py:41-74`）。

**骨架槽（P0 预留，Leader-A1）**：`src/engine_v2/llm/__init__.py`（占位 docstring：「本包是唯一允许触达 OpenAI / provider SDK 的位置；engine_v2.core 仍禁止 import 它们」——**该句与 Leader-A4 零 provider SDK 裁定相抵触，占位保留零修改，抵触登记为 DEV-4，gate 报告披露**）；`src/engine_v2/prompts/__init__.py`（占位 docstring：PromptAssembler / Prompt Policies / Prompt Registry + K4 + §13.3）；`src/engine_v2/README.md:21-22`（llm/ = Phase 6、prompts/ = Phase 6）。骨架 `__init__.py` 零修改（docstring-only 纪律，`tests/test_engine_v2_skeleton.py:145` 逐节点断言，P5 D-P5-02 先例延续）。

**环境事实**：见头部「环境事实」行。httpx 已装（传递依赖）→ pyproject +httpx 行 = Leader hunk（Leader-A9；设计文档只引用不修改 pyproject）。

### 1.4 不做什么（out of scope）

1. **不改 core/**（32/308 零触碰，D-P6-01）、**不改 content/ 与 plugins/**（P5 冻结零修改）、**不改 v1**（`src/llm/`、`src/prompts/`、`src/graph/`、`src/agents/`、`src/config/`、`src/game/`、`config/` 全部只读）、**不改 pyproject.toml 与 test_import_boundary.py**（Leader hunk 单列，§3.12）。
2. **不做 async**：llm/ 与 prompts/ 公开面全部同步（httpx 同步客户端）；Spec §31.1 `async def generate_structured`（Spec:1638）= 登记偏差 DEV-2；T07 的 "async" = 时间语义（结果携带 base_world_revision + 提交前 revalidation），非协程语义（Leader-A3）。
3. **不做真实 provider CI**：全部测试 = fake/mock 面（§42.1 NO LLM / NO NETWORK / NO GUI，Spec:1995-1999；ADR-004 L45 逐字「测试用例中必须使用 Mock / Fake LLM Provider，不可依赖外部真实 API 的私有返回值格式」）；真实调用仅 T10 smoke 脚本人工触发且不进 CI（Leader-A10）。
4. **不做 web/presentation/adapters**（他阶段预留：presentation = Phase 10、adapters = Phase 8/10/11，README.md:25-26；P6 不碰）。
5. **多模态 = 声明面 only**：`ModelCapabilityProfile.multimodal` 是纯声明字段（tier 匹配维度之一），**不实现图像管线**（无图像解码/编码/传输面；Spec §5.5 `input_modalities` 细粒度声明经 tier 尺度抽象承载，Leader-A2）。
6. **不实现 LangGraph 假设（K5）**：engine 不假设所有 NPC 是 LLM（Spec:307-311）；LLMPolicy = BehaviorPolicy 一种可选实现，按 actor 挂载，e2e 中仅 1 个 actor 挂 LLM 策略，其余走规则/无策略（ADR-002 决策 2）。
7. **不做 P5 项目文件面**：P5 validator 不动（Leader-A11）；P6 诊断 = 运行时面（resolve/inference/assemble 阶段）；P6 不新增项目文件诊断码进 P5 18 码闭集。
8. **不做 persistence/replay 接线**（Phase 8）：P6 trace sink = 宿主注入的 Protocol（内存收集面），不触碰事件级回放契约。
9. **不做 dynamics 规则库迁移**：v1 `PHYSICS_DEFAULT_RULES` 等硬编码规则文本不迁移（§7.4 行 11，显式废弃）。
10. **不重裁定**：Leader-A1~Leader-A12 全部照做（§4 逐条引用裁定编号）；与 SOT 矛盾时 SOT 优先 + 登记 §8.4（S2 纪律）。开放问题（保守读法）= 3 项：OI-P6-1 / OI-P6-3 / OI-P6-6（本档 §4 定义，§7.5 第 1 项 P7 移交面含 OI-P6-3；原「报告 JSON open_questions（6 项）」引用悬空，本档更正，OI-P6-2/4/5 不存在）。

---

## §2 不变量映射（K1-K8 → P6 机械映像）

K1-K8 全文见 Spec:242-339。P6 是**读世界视图 → 产新值（提案/记录/包）**阶段：不持有 WorldInstance、无 mutation API、无第二套权威状态。K 不变量在 P6 的落点 = 结构面 + 机械可验映像。**口径注**：本表列 = 相关断言全集；主归因口径以 §8.1 矩阵为准：

| K | 不变量（Spec 行号） | P6 机械映像 | P6-INV | 机械核验手段 |
|---|---|---|---|---|
| K1 | 单一 authoritative state（Spec:246-250） | P6 不持 WorldInstance；世界引用只经 scheduler 传入的 guard 视图 / `ActorDecisionContext`；全部 P6 输出 = 新值（ResolvedModel / PromptPackage / ActionProposal / trace payload），不产生第二套真源 | P6-INV-1 | e2e 世界只经 core 公共 API 构建（conftest 先例 = P4 conftest.py:472 make_p4_world 同型）；P6 模块无 WorldState 写面 API（导出台账人工核验 + 双跑字节相等 #17 间接锁）；#5/#19（§8.1 主归因：S5 双部署对比 + 项目 fixture 树 sha256 未动；logical_role==profile==capability 三同域；content diff 空） |
| K2 | 禁止直接状态写入（Spec:252-283） | LLMPolicy 唯一产物 = ActionProposal；提交唯一入口 = `scheduler.submit_proposal`（scheduler.py:1520）既有 revalidation → Transaction → Reducer 管线（Spec:267-283 全链）；P6 无 effect/transaction/reducer 调用面 | P6-INV-2 | stale e2e（#11）：REJECT 后世界零变更；正常 e2e（#4）：世界 diff 全部来自 commit 事务（K6 溯源）；TestP6Boundary：P6 模块 import 面不含 `core.effects`/`core.reducers`/`core.transactions` 写面模块；#5/#12（§8.1 主归因：项目 fixture 树 sha256 未动；探针值缺席于全部 trace 序列化文本 + artifact 内容） |
| K3 | Authority 与 Commit 分离（Spec:285-293） | P6 产物 = 候选值（proposal 是"候选新状态"的提案载体）；P6 无任何 commit API；`handle_result` 只产 `RevalidationDecision`（判定 = 数据，revalidation.py:63-104） | P6-INV-3 | 导出台账无 `commit/apply/write` 公共 API（§8.2 逐名核验）；#10/#11 REJECT 路径零副作用断言；#3/#17（§8.1 主归因：世界 revision 经提交事务单调递增；双跑字节相等） |
| K4 | Prompt 不能定义世界权限（Spec:295-303：Knowledge Boundary / World Read Capability / State Write Authority 必须由 Engine capability/authority system 控制） | assembler 输入**只来自** `ActorDecisionContext` 授予面（ContextProvider 经 capability 限定构建，Spec:874-878）；`CONTEXT_VARIABLES` 封闭供给集 = context 13 字段名（§3.10）——override 模板能引用的变量**上限**被供给集钉死；`PromptPolicy` 无 authority 字段（P5 冻结，schemas.py:418-426）；override 仅替换 L1/L2（Spec:935 MAY 面），L0/L3/L4 引擎固定（§13.3 Spec:907-909 逐字：「自定义 PromptAssembler MUST NOT 自动获得未授权数据」） | P6-INV-4 | 断言 #7-#9：无 world.read.global 授权的 context → override 模板 `{{global_entity_views}}` 投影 = `"null"`（零数据泄漏）；同世界授权 context → 投影 == 授权数据 JSON 投影本身（不多不少）；供给集外变量 → `LLMSIM_PROMPT_VARIABLE_UNSUPPORTED` |
| K5 | Agent 是 Policy，不是 Engine（Spec:305-313） | LLMPolicy = BehaviorPolicy 一种实现（结构合规 B-CON-1~5）；`run_policy_decide`（behavior_policy.py:83）唯一执行入口；engine 不假设所有 NPC 是 LLM——e2e 仅 1 actor 挂 LLMPolicy（经 WakeupHook，scheduler.py:316-337），其余 actor 规则/无策略 | P6-INV-5 | 断言 #20（B-CON-1~5 机械五连）；#1（e2e 非 LLM actor 与 LLM actor 共存于同一 step 序列） |
| K6 | Event 必须可追踪来源（Spec:315-324） | P6 三族记录全溯源：llm_call payload 9 键（trace.py:76-88）含 base_revision + prompt/output ref；prompt_assembly 记录含每层 provenance（source 标签）；提案 `Provenance(producer_id=ProducerId(_LLM_PRODUCER_PREFIX + context.actor_id), origin=OriginKind.BEHAVIOR_POLICY, source_record_id=None, notes=_LLM_NOTES_PREFIX + actor_id + ":" + str(tick) + ":" + str(base_revision))`（示意以 §3.5 字段表为准；私有拼接常量 §3.5，provenance.py:41-74） | P6-INV-6 | 断言 #2/#3/#19：9 键精确集 + 提交提案 ↔ llm_call 记录可回溯（base_revision 相等 + provenance notes 格式）+ prompt_assembly 存在；#1/#12（§8.1 主归因：e2e llm_call payload 9 键精确集；探针值缺席于全部 trace 序列化文本 + artifact 内容） |
| K7 | 关键调度状态可检查（Spec:326-328） | 无隐藏状态：时钟 = 注入 seam（MonotonicClock Protocol，D-P6-19）；零模块级可变全局；全部数据结构 JSON-clean（`assert_json_clean`，serialization.py:82）；ref = 确定性句柄（无 uuid/日期） | P6-INV-7 | 断言 #17 双跑字节相等；TestP6Boundary（零 asyncio / 非确定根源扫描 + 时钟 seam 唯一例外 / JSON-clean 单测族） |
| K8 | Deployment 与 Game Project 分离（Spec:330-339：Game Developer MUST NOT 固定 provider/model name/endpoint/credential；只能声明能力需求与建议） | 项目侧 = P5 冻结 `InferenceCapabilityProfile`（字段封闭，无部署 pin 字段，schemas.py:395-416）+ P5 18 码 validate 面不动（fixture 项目 validate 零诊断含 K8 扫描）；引擎侧 = P6 src 12 名 casefold 词边界**字符串字面量域** 0 命中（标识符豁免，Leader-A5；docstring 文案纪律见 §3.12）；部署侧 = 用户文件（`api_key_env` 只持 env 变量名，值永不入 trace/payload，Spec:1674 逐字） | P6-INV-8 | 断言 #12/#13/#14/#16/#18；#18 = 字段集内省（DeploymentEntry/ResolvedModel 无 credential 值字段）+ TestP6Boundary 12 名扫描 |

**P6-INV 清单**：P6-INV-1 ~ P6-INV-8（上表右列）。全部在 §5.2 断言、§6 单测或 TestP6Boundary 中有机械落点；无"仅靠自觉"的不变量。

---

## §3 模块与字段级规格

总览（11 模块 / 70 导出）：

| 模块 | 文件 | 导出数 | 任务 | 波次 |
|---|---|---|---|---|
| 3.1 | `src/engine_v2/llm/profiles.py` | 8 | T02 | W1 |
| 3.2 | `src/engine_v2/llm/deployment.py` | 8 | T03 | W1 |
| 3.3 | `src/engine_v2/llm/router.py` | 6 | T03 | W2 |
| 3.4 | `src/engine_v2/llm/adapter.py` | 11 | T04 | W3 |
| 3.5 | `src/engine_v2/llm/structured.py` | 6 | T04 | W4 |
| 3.6 | `src/engine_v2/llm/policy.py` | 4 | T06 | W5 |
| 3.7 | `src/engine_v2/llm/staleness.py` | 4 | T07 | W5 |
| 3.8 | `src/engine_v2/llm/critic.py` | 4 | T08 | W6 |
| 3.9 | `src/engine_v2/prompts/registry.py` | 5 | T05 | W4 |
| 3.10 | `src/engine_v2/prompts/assembler.py` | 12 | T05 | W4 |
| 3.11 | `src/engine_v2/prompts/diagnostic.py` | 2 | T03 | W1 |

**导入纪律（全部 P6 模块，D-P6-13）**：允许 import = stdlib（`__future__` `typing` `re` `enum` `os` `json` `math` `pathlib` `dataclasses` `collections.abc` `hashlib`）+ `pydantic` + `yaml` + `src.engine_v2.core.*`（冻结只读：actions / behavior_policy / context_provider / capability / ids / provenance / revalidation / revision / serialization / trace）+ `src.engine_v2.content.schemas`（冻结只读：DiagnosticSeverity / InferenceCapabilityProfile / PromptPolicy；**不 import P5 `Diagnostic`**——P6 诊断载体 = P6 自有本地 `RuntimeDiagnostic`（§3.11，D-P6-21），跨包仅复用 `DiagnosticSeverity`）。**两处文档化例外**（机械核验 = TestP6Boundary 方法 5）：① `httpx` 仅 `llm/adapter.py` 可 import（同步客户端，Leader-A4）；② `time` 仅 `llm/adapter.py` 可 import 且仅限 `SystemMonotonicClock` 实现体（注入时钟 seam，D-P6-19）。禁止：`asyncio` / `datetime` / `random` / `socket` / `urllib` / `requests` / `http.client` / v1 根（`src.game.*` `src.config.*` `src.agents.*` `src.llm.*` `src.prompts.*`）/ provider SDK 根（12 名，标识符豁免口径见下）/ 动态加载面（`importlib.import_module` / `__import__` / `spec_from_file_location`）。**12 名扫描域 = 27 文件域 × AST 字符串字面量域**（文件域 = 27 个 .py 文件 = 白名单 28 个 .py 文件 − 边界文件自身（28 构成 = 11 个新建 src 模块 + P6_TEST_FILES 15 + 2 个新建测试侧 `__init__.py` #9/#15，其中 P6_TEST_FILES 所含边界文件自身 `tests/engine_v2/core/test_import_boundary.py` 在此扣减）——明确排除 2 个既有骨架 src `__init__.py`（P0 冻结、零修改、不在白名单）+ 边界文件自身（白名单 #37 纯追加；既有冻结内容含 12 名明文常量，方法 2 字符串字面量面排除，§3.12 方法 2），非 .py 文件不入域，域细则 = §3.12 方法 2；`ast.Constant` str 节点值，含 docstring；casefold + 词边界，`test_import_boundary.py:225-240` 口径 + P5 SOT §6.4 行 2（test_p5_12_name_blacklist）同型口径）——标识符（包名 `llm`、字段名 `provider`/`model` = Spec:410-417 结构性名称；`base_url` = P6 DeploymentEntry 字段名）豁免；**docstring/注释文案纪律**：P6 src 文案中凡提及本域一律用「推理」「推理后端」「部署方」，不得出现 12 名单词（否则自扫描命中）；测试探针串一律拼接构造（`"ll"+"m"` 式，P5 先例）。

**模块间依赖（DAG，零环；→ = import 方向）**：`deployment → {profiles, prompts/diagnostic（RuntimeDiagnostic 发射面，§3.2 L205）}`；`router → {profiles, deployment}`；`structured → prompts/assembler`（wire 模型，运行期 import）；`policy → {router, adapter（模块级：WireMessage/InferenceRequest 运行时构造面 + InferenceBackend Protocol 注解）, staleness（模块级，§3.6 步骤 9）, structured, deployment（模块级：build_llm_policy 参数注解面）, prompts/registry, prompts/assembler；critic = decide() 步骤 7 内函数级懒 import（enable_critic 面，critic 落 W6，DAG 原「TYPE_CHECKING 仅」与 staleness/critic/deployment 缺边 = 汇总面遗漏，ERR-P6-10）}`；`staleness → core 冻结面`；`critic → core 冻结面（context 经 TYPE_CHECKING）`；`prompts/assembler → {prompts/registry, core 冻结面, content.schemas}`；`prompts/registry → {core 冻结面, content.schemas}`；`prompts/diagnostic → {content.schemas (DiagnosticSeverity)}`（DAG 叶，仅 pydantic + 该跨包只读 import）。**prompts 包零 llm import（registry/assembler/diagnostic 仅依赖 core + content.schemas + 包内兄弟模块）；llm 包对 prompts 的 import 发生在 structured（wire 模型）、policy（TemplateStore + TokenEstimator）与 deployment（RuntimeDiagnostic 发射面，§3.2 L205）；诊断发射/消费模块（deployment〔发射面〕/ router / adapter / structured / critic / registry / assembler / policy）对 `prompts/diagnostic` 的 `RuntimeDiagnostic` 类型 + `P6_RUNTIME_DIAGNOSTIC_CODES` 封闭集为只读 import（deployment = 构造期发射面，policy = decide 运行时发射面（透传组装诊断 + 构造 PARSE_* 族，§3.6 步骤 1/5/6/7），其余仅类型级）——wire 模型归 L0 层所有（Leader-A6）；零环**。

### 3.1 `llm/profiles.py`（8 导出）

**定位**：T02 model 侧交付（Leader-A2 消歧）：tier 尺度 0-4 定义 + `ModelCapabilityProfile`（部署侧：模型提供什么）+ capability 字符串约定。game 侧 `InferenceCapabilityProfile` = P5 冻结消费面（schemas.py:395-416），本模块**只 import 不修改**（router 消费）。纯数据 + 纯函数，零 I/O，零 core 依赖（本模块是 llm 包中唯一不 import core/content 的模块）。

`__all__`（8，按本表序）：`REASONING_CLASSES`, `REASONING_ORDER`, `TierLevel`, `TIER_SCALE`, `tier_level`, `ModelCapabilityProfile`, `CAPABILITY_ID_PATTERN`, `CAPABILITY_RE`

**tier 尺度（D-P6-03，封闭 5 档）**：

- **REASONING_CLASSES**（`Final[frozenset[str]]`，封闭词表 4 值）：`{"none", "standard", "advanced", "deep"}`。
- **REASONING_ORDER**（`Final[tuple[str, ...]]`）：`("none", "standard", "advanced", "deep")`（序 = 强度递增，比较基准）。
- **TierLevel**（`@dataclass(frozen=True)`）：

| 字段 | 类型 | 说明 |
|---|---|---|
| tier | int | 0..4（封闭域） |
| label | str | 档名（`baseline`/`dialogue`/`standard`/`advanced`/`expert`） |
| context_length_min | int | 该档 context 长度下限（**含 context 长度维**，Leader-A2） |
| max_output_min | int | 该档输出长度下限 |
| structured_output_required | bool | 该档是否要求结构化输出能力 |
| reasoning_class_min | str | 该档推理等级下限（∈ REASONING_CLASSES，按 REASONING_ORDER 比较） |

- **TIER_SCALE**（`Final[tuple[TierLevel, ...]]`，5 档，机械性质 = context_length_min 与 max_output_min 严格单调递增 + reasoning_class_min 单调不减，单测断言）：

| tier | label | context_length_min | max_output_min | structured_output_required | reasoning_class_min |
|---|---|---|---|---|---|
| 0 | baseline | 8000 | 1024 | False | none |
| 1 | dialogue | 32000 | 4096 | False | none |
| 2 | standard | 64000 | 8192 | True | standard |
| 3 | advanced | 128000 | 16384 | True | advanced |
| 4 | expert | 262000 | 32768 | True | deep |

- **tier_level(tier: int) -> TierLevel**：索引助手；`tier ∉ 0..4` → `ValueError`（输入违例族）。
- **ModelCapabilityProfile**（frozen pydantic，`extra="forbid"`）：

| 字段 | 类型 | 约束/默认 | 引注 |
|---|---|---|---|
| model_id | str | min_length=1；= 部署文件 `models` 节键 | Spec §5.4 用户侧模型标识（Spec:410-417） |
| tier | int | 0..4（model_validator：∈ TIER_SCALE 域） | D-P6-03 |
| context_length | int | >0；model_validator：≥ TIER_SCALE[tier].context_length_min | tier 档下限机械锁 |
| max_output | int | >0；model_validator：≥ TIER_SCALE[tier].max_output_min | 同上 |
| multimodal | bool | 默认 False（**声明面 only**，§1.4-5） | Plan:646 multimodal requirement（MAY） |
| structured_output | bool | 默认 False；model_validator：tier 要求时为 True | Plan:648 structured-output requirement |
| tool_support | bool | 默认 False | Plan:649 tool requirement |
| reasoning_class | str | ∈ REASONING_CLASSES；model_validator：REASONING_ORDER 序 ≥ 档下限 | Plan:647 reasoning class |
| notes | str | 默认 `""` | — |

- **CAPABILITY_ID_PATTERN**（`Final[str]`）：`"^[a-z][a-z0-9_]{0,63}$"`；**CAPABILITY_RE**（`Final[re.Pattern[str]]`）：编译体。
- **capability 字符串约定（D-P6-03）**：`capability` = **logical role id**，与 Spec §5.4 `inference_profiles` 键（Spec:410-417，如 `major_character` / `world_dynamics`）同族、同 pattern；与 game 侧 `InferenceCapabilityProfile.capability`（schemas.py:395-414）及 trace 键 `logical_role`（trace.py:76-88）三者**同一字符串域**（机械核验 = #5/#19 断言链中三处取值相等）。

**模块纪律**：零 I/O、零非确定根源、同步面；frozen 数据面；构造期形状违例 = pydantic ValidationError（load 面捕获转诊断，D-P6-18）。

### 3.2 `llm/deployment.py`（8 导出）

**定位**：T03 前半：用户侧部署配置加载（DeploymentProfile schema + 指针解析）+ credential env 名化模型（Leader-A5）。部署文件 = 用户文件（不属于 Game Project，K8 项目扫描面之外，Spec:405「部署配置属于用户，而不是游戏作者」）；本模块是 P6 唯一读用户文件的位置。

`__all__`（8，按本表序）：`DeploymentEntry`, `DeploymentProfile`, `DeploymentLoadResult`, `DEPLOYMENT_ENV_POINTER`, `resolve_deployment_path`, `load_deployment`, `load_deployment_auto`, `resolve_api_key`

- **DEPLOYMENT_ENV_POINTER**（`Final[str]`）：`"LLMSIM_DEPLOYMENT"`（env 指针名；12 名扫描负例自检：casefold 后 `\bllm\b` 不命中 `llmsim_deployment`——下划线/后随词字符口径，validator.py:324-327 同构）。
- **DeploymentEntry**（frozen pydantic，`extra="forbid"`）——用户侧单能力位配置（Spec §5.4 形状 Spec:409-418 的扩展，DEV-5）：

| 字段 | 类型 | 约束/默认 | 引注 |
|---|---|---|---|
| provider | str | min_length=1（用户侧任意字符串；可含 12 名词——用户文件非扫描域） | Spec:412 `provider: user_selected_provider` |
| model | str | min_length=1；load 期 ∈ `DeploymentProfile.models` 键（→ `LLMSIM_RESOLVER_MODEL_UNDECLARED`） | Spec:413 |
| base_url | str | 默认 `""`；调用期空 = 显式失败（`LLMSIM_INFERENCE_ENDPOINT_MISSING`，§3.4），**无静默默认端点** | P6 自裁（DEV-5 延伸，端点 = 用户面） |
| api_key_env | str \| None | 默认 None；pattern `^[A-Z][A-Z0-9_]{0,127}$`（env 变量**名**，永不持值，Leader-A5）；None = 无需认证（如本地后端） | Leader-A5；Spec:414-417 无 credential 值位 |
| temperature | float | 默认 0.7；0..2 | v1 先例 config.py:14（temperature 0.7） |
| timeout_seconds | float | 默认 30.0；≥0.1 | httpx 超时面（§3.4） |
| fallbacks | tuple[str, ...] | 默认 `()`；每项非空且 load 期 ∈ models 键（同 `LLMSIM_RESOLVER_MODEL_UNDECLARED`）；序 = 降级序（§3.3） | ADR-004 L41 同能力池 fallback |

- **DeploymentProfile**（frozen pydantic，`extra="forbid"`）：

| 字段 | 类型 | 约束/默认 |
|---|---|---|
| models | dict[str, ModelCapabilityProfile] | 默认 `{}`；**model_validator**：键 == 内层 `model_id`（不一致 → ValidationError）；ModelCapabilityProfile 构造违例 → ValidationError（load 面转 `LLMSIM_RESOLVER_DEPLOYMENT_PARSE`） |
| inference_profiles | dict[str, DeploymentEntry] | 默认 `{}`；**model_validator**：键 ∈ CAPABILITY_RE（capability 字符串约定，§3.1） |

  形状 = 两节（`models` + `inference_profiles`），Spec §5.4 示例单节形状登记为 DEV-5（MAY 级示例，非冻结字段表）。
- **DeploymentLoadResult**（frozen pydantic）：`path: str`、`profile: DeploymentProfile | None`（文件缺失/解析失败 = None + 诊断）、`diagnostics: tuple[RuntimeDiagnostic, ...]`（§3.11 本地载体；severity 仅复用 P5 `DiagnosticSeverity`，Leader-A11）。
- **resolve_deployment_path(explicit: str | Path | None = None) -> str | None**：指针优先级钉死 = **显式参数 > `os.environ[DEPLOYMENT_ENV_POINTER]` > None**（Leader-A5「deployment.yaml 路径或 LLMSIM_DEPLOYMENT env 指针」）。纯读 env，零 I/O。
- **load_deployment(path: str | Path) -> DeploymentLoadResult**：读 `path` → 缺失 → `LLMSIM_RESOLVER_DEPLOYMENT_MISSING`（error，path=该路径）；YAML 解析失败 / 根非 dict → `LLMSIM_RESOLVER_DEPLOYMENT_PARSE`（error）；pydantic 构造违例 → `LLMSIM_RESOLVER_DEPLOYMENT_PARSE`（refs=[pydantic loc 点分串]）；语义引用检查：inference_profiles 各 entry 的 `model` 与 `fallbacks` 各项 ∈ models 键 → 违例每项一条 `LLMSIM_RESOLVER_MODEL_UNDECLARED`（error，path=capability 键，refs=[缺失 model 名]）。**诊断不中断**：语义错 → profile 仍非 None（形状合法），resolve 期二次拦截（§3.3 同码同 refs 口径）；形状错 → profile = None。
- **load_deployment_auto(explicit: str | Path | None = None) -> DeploymentLoadResult**：`resolve_deployment_path(explicit)` = None → `LLMSIM_RESOLVER_DEPLOYMENT_MISSING`（path=`"<none>"`，refs=[DEPLOYMENT_ENV_POINTER]）；否则委托 `load_deployment`。
- **resolve_api_key(api_key_env: str | None) -> str | None**：None → None；否则 `os.environ.get(api_key_env)`（缺失 → None，调用期转 `LLMSIM_INFERENCE_CREDENTIAL_MISSING`，§3.4）。**返回值 = 值本身，仅存于调用方内存**；本模块无任何把值写进数据结构/诊断/payload 的路径（Leader-A5 机械面 = #12）。

**模块纪律**：读面仅 `os`（env）+ `pathlib` + `yaml`；零网络；同步面；确定性（同输入同诊断集，诊断序 = (code, path, refs) 排序，P5 D-P5-12 口径移植）。

### 3.3 `llm/router.py`（6 导出）

**定位**：T03 后半：capability → deployment 匹配 + fallback 梯度 + 诊断（G6-2 实现面：改实际模型 = 改用户部署文件，Spec §31.2「Deployment Resolver 映射 capability profile → actual model/provider」，Spec:1647-1656）。纯函数，零 I/O。

`__all__`（6，按本表序）：`ResolvedModel`, `RouterResult`, `resolve_capability`, `candidates_for`, `meets_tier`, `resolved_via`

- **ResolvedModel**（frozen pydantic，`extra="forbid"`）——router 产物（adapter 消费；13 字段）：

| 字段 | 类型 | 说明 |
|---|---|---|
| capability | str | logical role id（= requirement.capability） |
| model_id / provider / base_url | str | 取自 entry（base_url 可能为 `""`——调用期拦截，非 resolve 期） |
| api_key_env | str \| None | **只名不值**（Leader-A5；#18 内省断言无值字段） |
| tier / context_length / max_output | int | 取自 models 目录项（回显，trace/审计面） |
| structured_output / reasoning_class | bool / str | 取自 models 目录项 |
| temperature / timeout_seconds | float | 取自 entry |
| resolved_via | str | `"primary"` 或 `"fallback:<n>"`（n ≥ 1 = fallbacks 第 n 项，1-based；provenance 面，#6 断言消费） |

- **RouterResult**（frozen pydantic）：`resolved: ResolvedModel | None`、`diagnostics: tuple[RuntimeDiagnostic, ...]`（判定 = 数据，失败不抛——P5/P3 先例；载体 §3.11）。
- **candidates_for(deployment: DeploymentProfile, capability: str) -> tuple[DeploymentEntry, ...]**：capability ∉ inference_profiles → `()`；否则 = `(entry,)` + entry.fallbacks 各项展开为**同 entry 的 model 替换视图**（顺序 = primary 先、fallbacks 声明序；确定性，无排序无随机）。
- **meets_tier(model: ModelCapabilityProfile, min_tier: int) -> bool**：`model.tier >= min_tier`（纯比较；tier 档下限校验已在构造期完成，此处只比档位）。
- **resolved_via(index: int) -> str**：0 → `"primary"`；n>0 → `f"fallback:{n}"`。
- **resolve_capability(deployment: DeploymentProfile, requirement: InferenceCapabilityProfile) -> RouterResult**：

  五步次序钉死（步骤间严格次序，全步不抛异常）：
  1. `capability = requirement.capability`（pattern 违例 → `LLMSIM_RESOLVER_NO_DEPLOYMENT`（refs=["capability-malformed"]）——防御性；P5 侧已保证）。
  2. capability ∉ `deployment.inference_profiles` → `LLMSIM_RESOLVER_NO_DEPLOYMENT`（error，path=capability，refs=["inference_profiles 无此键"]）+ resolved=None。**绝不跨 capability 借用**（静默换模型禁令，G6-2 机械面）。
  3. 逐 candidate 求 `models[entry.model]`（缺失 → `LLMSIM_RESOLVER_MODEL_UNDECLARED` 跳过该 candidate）；首个 `meets_tier(model, requirement.min_tier)` 的 candidate 胜出。
  4. 无胜出 → `LLMSIM_RESOLVER_TIER_MISMATCH`（error，path=capability，refs=tried model_id 列表按尝试序——显式失败，绝不静默换模型，D-P6-07）。
  5. 胜出但 `model.tier < requirement.ideal_tier` → 附加 `LLMSIM_RESOLVER_BELOW_IDEAL`（warning，path=capability，refs=[model_id, str(ideal_tier)]）——**不阻断**（ideal 是建议级，Plan:650 recommendation 语义）。

  语义钉死（D-P6-07）：fallback = **同 capability 池内**按声明序降级（primary → fallbacks）；候选间**无跨档偏好**（首个满足 min_tier 者胜，不择优、不跳档）；min_tier 是唯一硬门槛；game 侧细粒度需求（context length / multimodal / reasoning class / structured-output / tool，Plan:644-649 允许清单）**全部经 tier 尺度抽象承载**（Leader-A2：许可集 MAY 声明，P6 不新增 game 侧声明面——P5 严格度未知键 = error + 字段封闭裁决使其不可行）。

**模块纪律**：零 I/O、零非确定根源、同步面；诊断序 = (code, path, refs) 排序。

### 3.4 `llm/adapter.py`（11 导出）

**定位**：T04：wire 协议接口（provider-neutral，Leader-A4/G6-6）+ httpx **同步**客户端 + FakeInferenceBackend（T09 fake 核心）+ 注入单调时钟 seam（K7，D-P6-19）。本模块是 P6 唯一触碰网络库与 `time` 的模块（两处文档化例外，§3 导入纪律）。

`__all__`（11，按本表序）：`MonotonicClock`, `SystemMonotonicClock`, `FixedMonotonicClock`, `WireMessage`, `InferenceRequest`, `InferenceResponse`, `InferenceBackend`, `HttpxInferenceBackend`, `FakeInferenceBackend`, `InferenceConfigError`, `InferenceTransportError`

- **MonotonicClock**（Protocol）：`now_ms(self) -> int`（单调非减；注入 seam，模式 = P5 DslRng 注入先例 D-P5-15）。
- **SystemMonotonicClock**（class）：`now_ms()` = `time.monotonic_ns() // 1_000_000`（**唯一** time 消费点；生产面）。
- **FixedMonotonicClock**（class，测试面）：`__init__(self, *, start_ms: int = 0, step_ms: int = 1)`；每次 `now_ms()` 返回后自增 step_ms——**确定性双跑**的延迟来源（#17）。
- **WireMessage**（frozen pydantic）：`role: Literal["system", "user", "assistant"]`、`content: str`（provider-neutral 最小消息面，Leader-A4）。
- **InferenceRequest**（frozen pydantic，`extra="forbid"`；11 字段）：

| 字段 | 类型 | 说明 |
|---|---|---|
| messages | tuple[WireMessage, ...] | min_length=1 |
| model / base_url | str | 取自 ResolvedModel |
| api_key_env | str \| None | **只名**（值在 generate 内 os.environ 解析，解析后立即进入 header，不落任何记录） |
| temperature | float | 取自 entry |
| max_tokens | int \| None | 默认 None（provider 上限 = 模型 max_output，部署侧已声明） |
| timeout_seconds | float | 取自 entry |
| logical_role / profile | str | trace 键同名（trace.py:76-88）；两值 = capability 同串（#19） |
| base_revision | Revision | 调用刻 context 基线（trace `base_revision` 键源） |
| prompt_metadata_ref | str | 确定性句柄 `prompt://{actor_id}:{tick}:{base_revision}`（§3.6） |

- **InferenceResponse**（frozen pydantic）：`text: str`（原始输出文本）、`model: str`（provider 回报模型名；缺省 = request.model）、`latency_ms: float`（≥0；注入时钟差）、`input_tokens: int | None`（provider usage 字段；缺失 = None → trace 用估计值）、`output_tokens: int | None`（同）。
- **InferenceBackend**（Protocol）：`generate(self, request: InferenceRequest) -> InferenceResponse`（**同步**——Spec §31.1 async 签名偏差 DEV-2；Protocol = wire 可替换接口本体，非 core contract 一部分，Leader-A4）。
- **HttpxInferenceBackend**（class）：`__init__(self, *, clock: MonotonicClock | None = None, transport: httpx.BaseTransport | None = None)`（clock None → SystemMonotonicClock；**transport 注入 seam**：默认 None = 真实网络栈（生产面），非 None（如 `httpx.MockTransport`）= 进程内注入面（S0 L751 / 断言 #15 L789 / §6.1 test_adapter L811 / D-P6-09 机械面所依））。`generate(request)` 次序钉死：
  1. `base_url` 空 → `InferenceConfigError`（code=`LLMSIM_INFERENCE_ENDPOINT_MISSING`）；
  2. `api_key_env` 非 None 且 env 缺失 → `InferenceConfigError`（code=`LLMSIM_INFERENCE_CREDENTIAL_MISSING`，message 只含**变量名**）；
  3. 端点 = `base_url.rstrip("/") + "/chat/completions"`（**默认 wire 约定 = OpenAI 兼容形状**，Leader-A4；可替换性 = 换 Backend 实现或换 base_url，非改本模块）；
  4. body = `{"model", "messages": [{role, content}], "temperature"}`（+`max_tokens` 非 None 时）；header = `Authorization: Bearer <解析值>`（仅 api_key_env 非 None 时）+ `Content-Type: application/json`；
  5. `httpx.Client(timeout=timeout_seconds, transport=transport)` 同步 POST（**credential 值只存在于 header 构造局部变量，不写入任何异常 message / 诊断 / 记录**）；
  6. 网络异常 / 超时 → `InferenceTransportError`（code=`LLMSIM_INFERENCE_TRANSPORT`，refs=[异常类名]）；
  7. 非 2xx → `InferenceTransportError`（code=`LLMSIM_INFERENCE_HTTP`，refs=[str(status)]）；
  8. 响应 JSON 无 `choices[0].message.content` → `InferenceTransportError`（code=`LLMSIM_INFERENCE_MALFORMED_RESPONSE`）；
  9. 成功 → `InferenceResponse`（latency = clock.now_ms() 差；usage 字段可选读）。
  **确定性条款**：本类零内置重试（重试语义归 structured/policy 层，D-P6-09）；零日志输出（structlog 不 import——日志面归宿主，Leader-A5「密钥值永不入日志」机械面之一）。
- **FakeInferenceBackend**（class，T09 核心）：`__init__(self, *, script: dict[tuple[str, Revision, int], str] = {}, default_text: str = '{"action_id": null}', base_latency_ms: float = 5.0)`；`generate(request)`：
  - 调用序号 `seq` = 本实例 generate 计数 +1（**1-based**）；
  - 查找键 `(request.logical_role, request.base_revision, seq)` ∈ script → 命中值；否则 default_text（`{"action_id": null}` = 合法 no-op，B-CON-3 None 路径）；
  - 返回 `InferenceResponse(text=命中值, model=request.model, latency_ms=base_latency_ms, input_tokens=None, output_tokens=None)`；
  - **`calls: tuple[InferenceRequest, ...]`**（只读调用史——测试断言调用次数/请求面，如 #15 wire 可替换性、Leader-A6 retry 上限）；
  - **确定性条款**：脚本化 + 序号寻址 → 同脚本同序列同输出（#17 双跑字节相等的 fake 面）；支持预制坏 JSON 文本（`"sorry, I cannot answer"` 形态）与一次坏 JSON 情形（Leader-A7）。
- **InferenceConfigError**（`ValueError` 子类，D-P4-17 两族风格延续）：属性 `code: str`（∈ INFERENCE 族诊断码）。
- **InferenceTransportError**（`Exception` 子类）：属性 `code: str`、`status: int | None`（TRANSPORT = None；HTTP = 状态码；MALFORMED_RESPONSE = None）。

**模块纪律**：`httpx`/`time` 双例外唯一宿主（TestP6Boundary 方法 5 机械锁）；异常 message 零 credential 值（#12 探针断言）；同步面；零 asyncio。

### 3.5 `llm/structured.py`（6 导出）

**定位**：T04：健壮 JSON 提取（G6-6：provider-neutral 三族形状）+ parse retry（Leader-A6：上限 1）+ wire 模型 → core ActionProposal 映射。**wire 模型本体归 `prompts/assembler.py` 所有**（L0 层拥有输出 schema 定义，Leader-A6；本模块 import 之，llm → prompts 单向依赖，§3 依赖 DAG）。

`__all__`（6，按本表序）：`ParseResult`, `PARSE_RETRY_MAX`, `extract_json_robust`, `parse_llm_response`, `repair_instruction`, `make_action_proposal`

**私有拼接常量（不入 `__all__`，Leader 裁定 F-04）**：`_LLM_PRODUCER_PREFIX: Final[str] = "ll" + "m:"`、`_LLM_NOTES_PREFIX: Final[str] = "ll" + "m://"`——K6 provenance 命名空间前缀，源文本零 12 名 `llm` 字面量（K8 自扫描 0 命中口径，TestP6Boundary 方法 2）；本档全部 provenance 组装示例（§2 K6 行 / 本表 / §5.2 断言 #2 测试比较串 `"ll" + "m://"`）一律经此常量拼接构造，零裸前缀字面量。

- **PARSE_RETRY_MAX**（`Final[int]`）：`1`（Leader-A6 上限钉死；trace `parse_retry` 键值域 = {0, 1}）。
- **extract_json_robust(text: str) -> str | None**：三族提取次序钉死（移植 v1 parser.py:91-104 语义，provider 中立化）：
  1. markdown fence（```json 或 ``` 块，DOTALL）→ 块内 strip（v1 JSON_BLOCK_RE 等价面）；
  2. 裸 JSON：首个 `{` 到末个 `}`（end > start）；
  3. 首尾杂文：前 1-2 族均未命中 → 整体 strip 后返回（交给 json 解析报错）；
  4. 无 `{` 或全空 → None（= 提取失败，转 parse 失败路径）。
  **确定性**：纯字符串函数，无 provider 分支、无 12 名词（G6-6 机械面 = #14）。
- **ParseResult**（frozen pydantic）：`value: LLMActionProposal | None`、`raw_json: str | None`（提取到的候选串）、`error: str | None`（pydantic 错误确定性摘要 = 首个 loc 点分串 + type；无 provider 语义）。
- **parse_llm_response(text: str) -> ParseResult**：`extract_json_robust` → None → ParseResult(None, None, "no-json-object")；否则 `LLMActionProposal.model_validate_json`（pydantic v2）成功 → (value, raw, None)；失败 → (None, raw, 错误摘要)。不抛异常（判定 = 数据）。
- **repair_instruction(errors: tuple[str, ...]) -> str**：确定性修复反馈文本模板（错误清单逐行 + 输出契约重申；无 provider 语义、无 12 名；v1 parser.py:79-84 反馈语义的中立等价迁移，§7.4 行 6）。
- **make_action_proposal(context: ActorDecisionContext, wire: LLMActionProposal, *, valid_until: Revision | None = None) -> ActionProposal**（`context` 为 TYPE_CHECKING import）：映射面逐项钉死（wire → core，语义对齐 Spec §11.3 L774-784）：

| core 字段（actions.py:174-188） | 取值 | 条款 |
|---|---|---|
| proposal_id | `ActionInstanceId("act_" + sha256(f"{context.actor_id}:{context.tick}:{context.base_world_revision}".encode()).hexdigest()[:16])` | **确定性推导**（不用 uuid 工厂 ids.py:255——K7 双跑字节相等，D-P6-19）；直接构造口径 = ids.py:83-85 |
| actor_id | `context.actor_id` | B-CON-5（门面二次校验） |
| action_id | `ActionTypeId(wire.action_id)`（wire.action_id 非 None 时——None 路径 policy 层拦截，不进入本函数） | Spec §11.3 |
| arguments | `wire.arguments` | 开放参数（actions.py:177 字段声明；docstring 描述行 actions.py:154） |
| intent | `wire.intent` | 可空 |
| timing | `ActionTiming()`（默认空，actions.py:122-131 全可空） | 调度语义归 scheduler |
| confidence | `wire.confidence` | [0,1]（wire 模型已校验） |
| fallback_action | `FallbackSpec(action_id=ActionTypeId(wire.fallback_action), arguments={})`（wire.fallback_action 非 None 时；None → None） | actions.py:134-142 |
| base_world_revision | `context.base_world_revision` | **必填**（actions.py:183，D-13；Spec §9） |
| observation_id | None | context 无该字段（13 字段封闭，context_provider.py:299-314）；P4 管线签发面，P6 不造 |
| actor_state_revision | `context.base_world_revision` | D-12 口径：读取 actor 决策相关状态时的 world_revision = context 构建刻 revision |
| valid_until | 参数透传（§3.7 计算） | Spec §9 L656 optional valid_until |
| provenance | `Provenance(producer_id=ProducerId(_LLM_PRODUCER_PREFIX + context.actor_id), origin=OriginKind.BEHAVIOR_POLICY, source_record_id=None, notes=_LLM_NOTES_PREFIX + actor_id + ":" + str(tick) + ":" + str(base_revision))` | K6（provenance.py:41-74）；前缀 = 本模块私有拼接常量（Leader 裁定 F-04，零裸前缀字面量）；ProducerId 直接构造不做词法校验（ids.py:83-85）——`PRODUCER_ID_PATTERN`（ids.py:77）为点分名字型、不含冒号，冒号形态仅直接构造可达，P6 无 parse_id 读回面；source_record_id 由宿主 sink 接线回填（P8 面） |

  **确定性条款**：同 (context, wire, valid_until) → 逐字段相等的提案（#17 消费）；不抛异常（构造违例 = pydantic ValidationError 上抛，属输入不变式违反族）。

**模块纪律**：stdlib（hashlib + re，§3 导入纪律白名单内）+ pydantic + core 冻结面 + prompts.assembler（wire 模型）；零网络、零 I/O、零非确定根源、同步面。

### 3.6 `llm/policy.py`（4 导出）

**定位**：T06：`LLMPolicy` = P6 门面（BehaviorPolicy 实例），组装 + 调用 + 解析 + staleness 接线 + trace 记录全在此收口；`build_llm_policy` = 构造工厂（router 失败 = 显式失败，绝不静默）。B-CON-1..5 全量落地（#20 机械面）。

`__all__`（4，按本表序）：`LLMPolicy`, `BuildResult`, `build_llm_policy`, `TraceSink`

- **TraceSink**（Protocol，宿主注入，K6 接线面，三方法封闭）：
  - `record(self, kind: str, payload: dict[str, object]) -> None`（kind ∈ `{"llm_call", "prompt_assembly"}`；payload 键集合 = 对应 PAYLOAD 键常量精确等值——llm_call 9 键 = trace.py:76-88，prompt_assembly 键 = {actor_id, tick, base_revision, prompt_metadata_ref, token_estimate}；**键集与 kind 词表封闭，诊断不进入本方法**）；
  - `store_artifact(self, ref: str, artifact: object) -> None`（确定性句柄存 artifact 本体：ref = `prompt://{actor_id}:{tick}:{base_revision}` 存 PromptPackage 摘要 dict、`output://{actor_id}:{tick}:{base_revision}` 存 wire 原始文本 dict——**artifact 本体由宿主决定落盘**，P6 只给 ref+内容，不碰文件系统）；
  - `record_diagnostic(self, diag: RuntimeDiagnostic) -> None`（独立诊断通道，Leader 裁定 F-02 / D-P6-22：诊断与记录分离——`RuntimeDiagnostic`（§3.11）经此通道入宿主 sink，不进 `record` 的封闭键集；宿主侧如何落 trace/日志 = 宿主实现面，P6 只交付对象）。
- **BuildResult**（frozen pydantic）：`policy: LLMPolicy | None`、`diagnostics: tuple[RuntimeDiagnostic, ...]`（resolve 失败 = policy None + 诊断，显式失败面，D-P6-07）。
- **build_llm_policy(*, capability: str, requirement: InferenceCapabilityProfile, deployment: DeploymentProfile, backend: InferenceBackend, store: TemplateStore, estimator: TokenEstimator, sink: TraceSink, ttl_ticks: int | None = None, enable_critic: bool = False) -> BuildResult**：
  1. `resolve_capability(deployment, requirement)`（§3.3）；
  2. resolved=None → BuildResult(None, 原诊断)（**绝不回落任意模型**）；
  3. resolved → `LLMPolicy(capability=..., resolved=..., backend=..., store=..., estimator=..., sink=..., ttl_ticks=..., enable_critic=...)` + 原诊断（below_ideal 警告随结果传递）。
  `InferenceBackend` 经 TYPE_CHECKING import（Protocol 面，B-CON-4：policy.py 运行时不 import adapter 具体类）。
- **LLMPolicy**（class，frozen dataclass 语义——`__slots__` 只读属性，构造期赋值后不暴露写面）：

  属性（B-CON-4：类体仅 Protocol/契约类型 + 注入值，无任何 random/clock/网络面）：`capability: str`、`resolved: ResolvedModel`、`backend: InferenceBackend`、`store: TemplateStore`、`estimator: TokenEstimator`、`sink: TraceSink`、`ttl_ticks: int | None`、`enable_critic: bool`。

  **`decide(self, context: ActorDecisionContext) -> ActionProposal | None`**（同步、单参、B-CON-1/2；B-CON-3 None 合法）——流程九步钉死：
  1. **组装**：`result = assemble_prompt(context, self.store, self.estimator, capability=self.capability)`（§3.10）；`result.package is None` → 组装期诊断逐一 `self.sink.record_diagnostic(d)`（PROMPT_* 族，独立诊断通道，D-P6-22）+ `self.sink.record("prompt_assembly", {...})`（组装失败时 payload 五键 = `actor_id`/`tick`/`base_revision` 正常值 + `prompt_metadata_ref` 定值 `assembly_failed` + `token_estimate` = 0；五键封闭集不变，L343 口径一致）→ **返回 None**（组装失败 = no-op，显式失败，不猜）。（组装期诊断传递：assemble_prompt 返回值即含诊断本体，policy 经 record_diagnostic 通道透传宿主 sink 消费。现有 test_policy「组装失败 → None」用例只钉返回值、不钉 payload，无需改。）
  2. **请求构造**：`messages = (WireMessage(role="system", content=pkg.text),)`（单 system 消息承载全层——L0-L4 已压平为一段契约文本，Leader-A4 wire 最小面）；request 字段按 §3.4 表自 `pkg` + `self.resolved` 填充（base_revision = `context.base_world_revision`，prompt_metadata_ref = pkg 句柄）。
  3. **首次调用**：`response = self.backend.generate(request)`（传输异常**原样上抛**——house 语义：fake 永不抛，httpx 面异常属运行时环境失败族，不吞不转；P5/P3 先例「判定=数据」仅适用于判定函数，generate 是副作用调用面）。
  4. **解析**：`parse = parse_llm_response(response.text)`；成功 → wire = parse.value；失败 → 进入 5。
  5. **repair 重试**（仅当 attempt 0 失败且 retry 预算可用）：messages 追加 `WireMessage(role="user", content=repair_instruction((parse.error,)))` → 二次 `generate` → 再解析。成功 → wire = 再解析值，且 `sink.record_diagnostic(LLMSIM_INFERENCE_PARSE_RECOVERED warning，refs=[首次错误摘要])`（本调用 parse_retry=1，随第 9 步 llm_call payload 定格）；失败 → 进入 6。预算钉死：parse 阶段至多 1 次重试（PARSE_RETRY_MAX=1，Leader-A6）；critic 阶段另计 1 次（§3.8）；**单次 decide 总调用上限 = 3**（1 + parse-retry 1 + critic-repair 1），`self.calls_budget` 非持久（decide 内局部计数，跨 decide 无状态——K7 无可变全局）。
  6. **解析终败**：双次失败 → `sink.record_diagnostic(LLMSIM_INFERENCE_PARSE_FAILED error，refs=[两次错误摘要])` + `sink.record("llm_call", payload含 parse_retry=1)` → **返回 None**（不 crash、不抛，B-CON-3 语义）。
  7. **critic**（仅 `enable_critic`）：`crit = critique(context, wire)`（§3.8）；失败 → **一次**修复调用（`critique_instruction(crit.errors)` 追加为 user 消息 → generate → 解析，不再重试）→ 仍败 → `sink.record_diagnostic(LLMSIM_INFERENCE_PARSE_FAILED error，refs 前缀 "critic:")` + `sink.record("llm_call", payload含 parse_retry=1)` → 返回 None。
  8. **no-op 分支**：`wire.action_id is None` → `sink.record("llm_call", ...parse_retry=实际次数...)` → **返回 None**（合法跳过，非失败）。
  9. **提案分支**：`valid_until = effective_valid_until(context, self.ttl_ticks)`（§3.7）；`proposal = make_action_proposal(context, wire, valid_until=valid_until)`（§3.5）；`sink.record("prompt_assembly", {5 键})` + `sink.store_artifact(prompt_ref, 摘要)` + `sink.record("llm_call", {9 键})` + `sink.store_artifact(output_ref, {"text": wire 原始候选 json 串})` → **返回 proposal**。

  **llm_call payload 9 键精确表**（= LLM_CALL_PAYLOAD_KEYS，trace.py:76-88；#1/#19 机械断言）：

  | 键 | 值来源 |
  |---|---|
  | logical_role | `self.capability` |
  | profile | `self.capability`（同串，D-P6-03 三同域） |
  | resolved_model | `self.resolved.model_id` |
  | input_token_estimate | `pkg.token_estimate`（int，估计器面，非 provider usage） |
  | prompt_metadata_ref | `prompt://{actor_id}:{tick}:{base_revision}` |
  | output_ref | `output://{actor_id}:{tick}:{base_revision}` |
  | latency_ms | 首次调用 response.latency_ms（float ≥0） |
  | parse_retry | 实际重试次数 ∈ {0, 1} |
  | base_revision | `context.base_world_revision`（int） |

  **类体纪律（B-CON-4 机械面）**：类体（含类级注解）零具体后端类名、零 clock 实例、零 random、零网络对象（TestP6Boundary 方法 6 AST 扫描）；`asyncio` 零出现（#20 包）。

**模块纪律**：policy.py import ∩ {httpx, time, random, asyncio, datetime, socket, urllib, requests} = ∅（机械断言）；同步面；零非确定根源（注入 clock 经 backend，policy 自身不持 clock）；诊断面经 sink，不直接构造 RuntimeDiagnostic 落盘。

### 3.7 `llm/staleness.py`（4 导出）

**定位**：T07：stale 处理接线 = **委托既有 revalidation 管线**（Spec §9 L669 逐字「提交前 MUST 执行 revalidation。」——P6 不重复实现，只算 `valid_until` 并消费既有语义）。async 的 time 语义（Leader-A2 消歧后的 T07 真实落点）= valid_until TTL 推导，非异步。

`__all__（4，按本表序）`：`COMMITTABLE_OUTCOMES`, `effective_valid_until`, `handle_result`, `is_acceptable`

- **COMMITTABLE_OUTCOMES**（`Final[frozenset[str]]`）：`{"ACCEPT", "REBASE"}`（= RevalidationDecision 可提交结局，revalidation.py:63-104 + revision.py:91 RevalidationOutcome）。
- **effective_valid_until(context: ActorDecisionContext, ttl_ticks: int | None) -> Revision | None**（`context` TYPE_CHECKING）：
  - ttl_ticks is None → None（valid_until = None = 无显式上界，纯靠 base 对比 + 提交期 revalidation 拦截，Spec §9 L656 optional 语义）；
  - 否则 → `Revision(context.base_world_revision + ttl_ticks)`（TTL 从 context 基线起算；ttl_ticks ≥ 1 由调用方保证，0/负 = 输入违例 ValueError）。
  - **语义钉死**：`is_stale`（revision.py:78-88）既有口径——base_revision < current → stale；current > valid_until → stale；current == valid_until → **不 stale**（边界含等号，revision.py:88 口径原样消费，P6 不发明第二套）。
- **handle_result(decision: RevalidationDecision, proposal: ActionProposal) -> str**：`decision.outcome` → 规范化字符串（"ACCEPT"/"REBASE"/"REPAIR"/"REJECT"，Spec §9 L673-677）；**REBASE**：`decision.rebased_proposal`（revalidation.py:91）非 None → 返回 "REBASE"（rebased 提案由宿主提交——P6 不自动重提交，宿主决定，#10 面）。
- **is_acceptable(outcome: str) -> bool**：`outcome ∈ COMMITTABLE_OUTCOMES`。
- **消费链（#10 语义面）**：policy 产出提案 → 宿主（wake-up 钩子）`scheduler.submit_proposal`（scheduler.py:1520-1530：revalidation → ACCEPT 入队 / REJECT 置 FAILED）→ P6 侧对 decision 只做记录不做干预。**G6-4「stale 不直接 commit」= 该链的机械断言**（P6 零独立 stale 拦截器——设计立场：stale 判定权唯一归 revalidation，P6 越权拦截 = 重复状态面，禁止）。

**模块纪律**：零 I/O、纯函数、同步面；只 import core 冻结面（revision/revalidation 类型）。

### 3.8 `llm/critic.py`（4 导出）

**定位**：T08：可选规则 critic（flag 默认关，Leader-A6）。critic = 对 wire 结果的**确定性规则校验**（非 LLM critic——K7 零非确定、调用预算钉死）：action_id 合法性 + 目标实体可见性。

`__all__`（4，按本表序）：`CriticResult`, `CRITIC_DEFAULT_ENABLED`, `critique`, `critique_instruction`

- **CRITIC_DEFAULT_ENABLED**（`Final[bool]`）：`False`（Leader-A6 默认关）。
- **CriticResult**（frozen pydantic）：`ok: bool`、`errors: tuple[str, ...]`（确定性错误摘要串，序 = 检查序）。
- **critique(context: ActorDecisionContext, wire: LLMActionProposal) -> CriticResult**（`context` TYPE_CHECKING）——检查序钉死：
  1. `wire.action_id is None` → 跳过（no-op 无错）；
  2. `wire.action_id` ∉ {`a` for a in context.candidate_actions}（candidate_actions 元素本身即 ActionTypeId，13 字段之一，context_provider.py:312）→ error `"action-not-in-candidates"`；
  3. `wire.arguments` 的标量目标字段（键 ∈ 封闭目标键集合 `{"entity_id", "target_id", "target", "actor_id"}`——键名面，D-P6-10）的 str 值 ∉ {*context.visible_entities, *context.local_entity_views, *(context.global_entity_views or {})}（实体 id 并集：visible_entities 本身即 EntityId frozenset，两视图 dict 取键 = EntityId，global_entity_views 未授权时 = None，P4 冻结字段类型 context_provider.py:306-308）→ error `"target-not-visible"`（逐值一条，序 = arguments 键序）；
  4. 全过 → ok=True。
  **确定性**：纯比较，零 I/O；集合序 = context 字段序（P4 冻结序）。
- **critique_instruction(errors: tuple[str, ...]) -> str**：确定性修复反馈（错误逐行 + 「请只输出 JSON」重申；无 provider 语义、无 12 名）。

**模块纪律**：纯函数、同步面；目标键集合封闭（扩键 = 版本变更，D-P6-10 登记）。

### 3.9 `prompts/registry.py`（5 导出）

**定位**：T05 前半：game PromptPolicy（P5 冻结 schemas.py:418-426）→ 模板文档加载 + 路径纪律（Leader-A12）。模板 = `.md` 文本文件（非 .yaml——P5 loader glob 面外，§1.3（L61 LAYOUT_OPTIONAL 行注记）/D-P6-11）。

`__all__`（5，按本表序）：`TemplateDocument`, `TemplateStore`, `RenderResult`, `render_template`, `validate_template_ref`

- **TemplateDocument**（frozen pydantic）：`policy_id: str`、`scope: str`、`template_ref: str`（原样保存，相对路径）、`variables: tuple[str, ...]`（P5 声明序）、`text: str`（文件内容本体，可能为 `""`）、`path: str`（解析后绝对路径，诊断面）。
- **validate_template_ref(template_ref: str, project_root: Path) -> tuple[Path, str | None]**：
  1. 绝对路径 / `..` 逃逸 / 解析后 realpath 前缀 ∉ `project_root/prompts/` → (原 Path, `"path-escape"`）（→ `LLMSIM_PROMPT_PATH_ESCAPE`，error，Leader-A12 钉死：越界读 = 拒绝，不静默）；
  2. 合法 → (realpath, None)。
  **符号链接**：realpath 前缀检查天然拦截 symlink 逃逸（#16/AD-5 探针对）。
- **render_template(document: TemplateDocument, values: dict[str, str]) -> RenderResult**：`{{var}}` 双花括号替换（**无 jinja2**——venv 白外面，Leader-A12/D-P6-11）：
  - 扫描文中全部 `{{token}}`（token = 非空非空白串）：token ∉ document.variables → 诊断 `LLMSIM_PROMPT_UNDECLARED_VARIABLE`（error，refs=[token]，**替换为原文保留**——诊断不中断渲染）；
  - token ∈ variables 但 values 缺 → `LLMSIM_PROMPT_VARIABLE_MISSING`（error，refs=[token]，替换为 `""`）；
  - 全过 → 替换成功文本。
  替换为**单次线性扫描**（确定性，无嵌套求值）。
- **RenderResult**（frozen pydantic）：`text: str`、`diagnostics: tuple[RuntimeDiagnostic, ...]`。
- **TemplateStore**（class）：`__init__(self, *, project_root: Path, policies: tuple[PromptPolicy, ...])`（P5 PromptPolicy 序列，来自 IR）——加载即校验：
  1. 逐 policy：id 重复（casefold 比较）→ `LLMSIM_PROMPT_DUPLICATE_POLICY`（error，refs=[id]）；
  1.5（F-03 钉死，D-P6-18 触发面）：`policy.scope.casefold() ∉ {"game_policy", "character_scene"}` → `LLMSIM_PROMPT_SCOPE_UNKNOWN`（warning，refs=[scope]），且**该 policy 不进入 store 分层**（`by_id` 无此条目，后续步骤 2-5 对该 policy 跳过，assembler 侧自然不可见）——scope 词表闭集 = 2 值（P5 `PromptPolicy.scope` 为 str 无 enum，schemas.py:418-426 冻结面，闭集校验归 P6 运行时）；
  2. `validate_template_ref` → 逃逸 → `LLMSIM_PROMPT_PATH_ESCAPE`（error，path=template_ref）；
  3. 文件缺失 → `LLMSIM_PROMPT_TEMPLATE_MISSING`（error，path=template_ref）；
  4. 读取（`Path.read_text`，UTF-8）→ 空文件 → `LLMSIM_PROMPT_TEMPLATE_EMPTY`（warning）；
  5. 成功 → TemplateDocument 入 store（按 policy 序）。
  `store.by_id: dict[str, TemplateDocument]`、`store.diagnostics: tuple[RuntimeDiagnostic, ...]`（序 = (code, path, refs) 排序，确定性）。
  **scope 分派面**：`store.for_scope(scope: str) -> tuple[TemplateDocument, ...]` 不存在于本模块（scope 分派归 assembler §3.10——registry 只管加载与纪律，assembler 只管组装，单一职责）。

**模块纪律**：读面 = `pathlib` + `re` + pydantic + core/content 冻结类型 + `prompts/diagnostic`（W1）；零网络、零非确定根源、同步面；P5 PromptPolicy 只读消费（P5 冻结）。

### 3.10 `prompts/assembler.py`（12 导出）

**定位**：T05 后半：L0-L4 组装 + capability 限定变量供给（K4 天花板）+ wire 模型（L0 拥有输出 schema，Leader-A6）+ token 估计。assembler **零 llm import**（§3 依赖 DAG）。

`__all__`（12，按本表序）：`PromptLayer`, `LayerSegment`, `PromptAssembly`, `PromptPackage`, `UntrustedContent`, `TokenEstimator`, `CharDivisorTokenEstimator`, `CONTEXT_VARIABLES`, `L0_CONTRACT_TEMPLATE`, `LLMActionProposal`, `context_variable_value`, `assemble_prompt`

- **PromptLayer**（`enum.Enum`，封闭 5 值，Spec §14 L917-923）：`L0_ENGINE_CONTRACT` / `L1_GAME_POLICY` / `L2_CHARACTER_SCENE` / `L3_RUNTIME_CONTEXT` / `L4_UNTRUSTED`。
- **LayerSegment**（frozen pydantic）：`layer: PromptLayer`、`source: str`（来源标记：`"engine"` / policy_id / `"runtime"` / 来源标签）、`text: str`、`overridable: bool`（L1/L2=True，余 False——D-P6-12 自裁「override 只换 L1/L2」机械面；Spec:935 = MAY 替换 + capability boundary 不变依据；Spec:907-909「自定义 PromptAssembler MUST NOT 自动获得未授权数据」= 不提升逐字依据）。
- **CONTEXT_VARIABLES**（`Final[frozenset[str]]`，**封闭供给集 = ActorDecisionContext 13 字段名精确集**，context_provider.py:299-314）：`{"actor_id", "tick", "base_world_revision", "wake_reason", "self_view", "visible_entities", "local_entity_views", "global_entity_views", "observations", "knowledge", "memory", "candidate_actions", "granted_capabilities"}`。K4 天花板：**assembler 只认这 13 名，context 之外的任何数据无进入 prompt 的通道**（#7-9 机械面）。
- **context_variable_value(context: ActorDecisionContext, name: str) -> str | None**（`context` TYPE_CHECKING）：
  - name ∉ CONTEXT_VARIABLES → None（→ `LLMSIM_PROMPT_VARIABLE_UNSUPPORTED`，error——P5 声明了但运行时不供给的变量 = 显式拒绝，不猜）；
  - `global_entity_views` 且 context 该字段 = None（未授权）→ `"null"`（**不泄漏**，#7 机械面）；
  - 其余 → JSON 清洗确定性序列化（`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))`；不可序列化值 = 输入违例 ValueError 上抛，house 族）。
  序列化口径与 core serialization.py:82 assert_json_clean 同族（P5/P4 先例）。
- **UntrustedContent**（frozen pydantic）：`source_label: str`、`payload: str`（L4 数据包装，Spec §14 L933 MUST data 语义：非受信内容必须数据化、带标记包裹）。
- **L0_CONTRACT_TEMPLATE**（`Final[str]`）：引擎契约层模板（**中性措辞，零 12 名、零 provider 语义**，G6-6 面）：含输出 schema（LLMActionProposal JSON schema 内嵌）、JSON-only 指令、repair 约定、no-op 约定（`"action_id": null` = 本 tick 不行动）。v1 json_instruction（parser.py:44-52）的中立等价迁移（§7.4 行 5）。
- **LLMActionProposal**（frozen pydantic，**wire 模型**，`extra="ignore"`——provider 附加字段容忍，Leader-A4 中立面）：

  | 字段 | 类型 | 约束/默认 |
  |---|---|---|
  | action_id | str \| None | 默认 None = no-op |
  | arguments | dict[str, JsonValue] | 默认 `{}`（JsonValue = P5/core JSON 封闭类型族） |
  | intent | str \| None | 默认 None |
  | confidence | float \| None | 默认 None；0..1 |
  | fallback_action | str \| None | 默认 None |

- **TokenEstimator**（Protocol）：`estimate(self, text: str) -> int`（≥0；注入 seam，同 MonotonicClock 模式）。
- **CharDivisorTokenEstimator**（class）：`__init__(self, *, divisor: float = 4.0)`；`estimate` = `max(0, math.ceil(len(text) / divisor))`（确定性；divisor < 0.5 → ValueError）。
- **PromptAssembly**（frozen pydantic）：`package: PromptPackage | None`、`diagnostics: tuple[RuntimeDiagnostic, ...]`（组装失败 = package None + 诊断，显式失败，§3.6 步骤 1 消费）。
- **PromptPackage**（frozen pydantic）：`actor_id: str`、`logical_role: str`（= capability）、`base_revision: Revision`、`layers: tuple[LayerSegment, ...]`（序 = L0→L4 固定）、`text: str`（压平全文 = L0 + 各层以确定性分隔标记拼接）、`token_estimate: int`、`prompt_metadata_ref: str`（`prompt://{actor_id}:{tick}:{base_revision}`）。
- **assemble_prompt(context: ActorDecisionContext, store: TemplateStore, estimator: TokenEstimator, *, capability: str) -> PromptAssembly**（`context` TYPE_CHECKING）——层序与规则钉死：
  1. **L0**：L0_CONTRACT_TEMPLATE（引擎所有，overridable=False，source="engine"）。
  2. **L1**：store 中 scope=`"game_policy"` 的 policy 文档。**同 scope 多条 = casefold 字典序首 id 胜、无诊断**（确定性兜底钉死；P5 侧无同 scope 多条约束，P6 登记自裁，D-P6-12）。渲染 = `render_template(doc, values)`，values = 声明变量 ∩ CONTEXT_VARIABLES 逐个 `context_variable_value`（缺值/不支持 → 诊断透传）。
  3. **L2**：scope=`"character_scene"`，同规则；`{character_id}` 式场景变量**不引入**（L2 变量同样受 13 名供给约束——K4 天花板不分层）。
  4. **L3**：运行时上下文层 = 确定性模板（引擎所有）+ 全 13 变量 JSON 序列化块（**全量供给，无挑选**——变量供给由 K4 天花板封顶，由 L1/L2 的 `variables` 声明控制「哪些进游戏层」，L3 全量进运行时层）。`global_entity_views` 未授权 → `"null"`（#7）。
  5. **L4**：untrusted 包装层——当前 P6 组装器**零 L4 内容源**（P7 动态叙事面预留；层定义存在但本相空段 = 确定性空文本）。预留接口 `assemble_prompt` 无 L4 入参（扩展 = 版本变更）。
  6. 压平（显式逐层拼接，公式面钉死）：`text = L0.text + ''.join(层标记 + seg.text for seg in L1..L4 层段)`，其中每层标记 = `"\n\n<!-- LAYER:" + seg.layer.name + " -->\n"`（L0 居首；L1-L4 各前置本层标记，标记次数 = 层段数；原记法 `{name}` = `segment.layer.name`，如 `L1_GAME_POLICY`）；分隔标记确定性固定；`token_estimate = estimator.estimate(text)`；包构造（actor_id/logical_role/base_revision 取自 context）。
  7. 任一 error 级诊断 → package=None（显式失败）；仅 warning → package 正常。
  **override 语义**：宿主 override = **替换 L1/L2 的文档文本**（store 以 override 版 policy 加载即生效——override 不提升 context capability，G6-3：override 模板变量仍受 13 名供给约束，Spec:935 + Plan G6 第 3 条）。

**模块纪律**：零 llm import、零网络、零非确定根源、同步面；pydantic + core/content 冻结面 + stdlib（json/math/enum/re）。

### 3.11 `prompts/diagnostic.py`（2 导出）

**定位**：P6 运行时诊断载体（Leader-A11 诊断封闭集的类型载体，D-P6-21 新裁）：P6 **不 import P5 `Diagnostic`**（其 code 闭集 = P5 18 码项目文件诊断域，content/schemas.py:112-133），而是新立与其字段同构的本地载体——同字段集、同构造期校验语义、换码闭集（P6 21 码运行时域，§8.1）；severity 仅复用 P5 `DiagnosticSeverity`（跨包只读 import，schemas.py:102-107）。首个消费者 = deployment（T03 前，W1 构造期发射面：LLMSIM_RESOLVER_DEPLOYMENT_MISSING/DEPLOYMENT_PARSE/MODEL_UNDECLARED）；首个 resolver 消费者 = router（T03 后，其余 LLMSIM_RESOLVER_* 发射面）。纯数据 + 纯常量，零 I/O，零 core 依赖，DAG 叶（§3 头 DAG）。

`__all__`（2，按本表序）：`RuntimeDiagnostic`, `P6_RUNTIME_DIAGNOSTIC_CODES`

- **RuntimeDiagnostic**（frozen pydantic，`extra="forbid"`）——与 P5 `Diagnostic`（content/schemas.py:523-548）字段同构：

| 字段 | 类型 | 说明 |
|---|---|---|
| code | str | ∈ `P6_RUNTIME_DIAGNOSTIC_CODES`（21 码闭集，§8.1）；**闭集外 = 构造期拒绝**（镜像 P5 validator 口径，schemas.py:542-548，闭集换 P6 21 码）——构造期 `ValidationError` 是本载体唯一错误通道 |
| severity | DiagnosticSeverity | 复用 P5 str-Enum（schemas.py:102-107：`ERROR="error"` / `WARNING="warning"`） |
| path | str | `min_length=1`；诊断归因对象（capability id / 部署路径 / policy id / template ref 等，K6 可追踪面） |
| message | str | `min_length=1`，确定性文本（无时间戳 / 无指针 / 无随机，D-P5-15 纪律） |
| refs | tuple[str, ...] | 默认 `()`；结构化引用（机械断言面，构造时定序，如 `[capability, min_tier, candidate_tiers]`） |

- **P6_RUNTIME_DIAGNOSTIC_CODES**（`Final[frozenset[str]]`，21 码）：全表 = §8.1 诊断码表（RESOLVER 6 / INFERENCE 7 / PROMPT 8）；`RuntimeDiagnostic` 构造期 `model_validator(mode="after")` 拒绝 `code` ∉ 本集（镜像 P5 L542-548，闭集换为本常量）；与 P5 18 码零重叠 = 机械断言 `set-disjoint`（§6.2 conftest session fixture，D-P6-21 机械验证面）。

**模块纪律**：仅 stdlib（`__future__` / `typing`）+ `pydantic` + `content.schemas`（`DiagnosticSeverity` 单名）；零 core、零 I/O、零网络；诊断发射/消费模块（deployment / router / adapter / structured / critic / registry / assembler 发射，policy 经 sink 消费，TYPE_CHECKING）对本模块为类型级只读 import。

### 3.12 边界同步面（TestP6Boundary 规格，Leader-A8）

追加于 `tests/engine_v2/core/test_import_boundary.py`（**纯追加块，Leader hunk**，P5 先例：TestP5Boundary 5 方法规格 P5 SOT:787-798 同构）：

- 常量 **P6_SUBMODULES**（11 干名，封闭）：`("profiles", "deployment", "router", "adapter", "structured", "policy", "staleness", "critic", "registry", "assembler", "diagnostic")`（前 8 = llm/，后 3 = prompts/）。
- 常量 **P6_TEST_FILES**（15 个 .py 文件名，封闭，不含 `__init__.py`）：llm/ 10 测试文件（`test_profiles`…`test_p6_adversarial`）+ `tests/engine_v2/llm/conftest.py` + prompts/ 2 测试文件（`test_registry`, `test_assembler`）+ `tests/engine_v2/core/test_import_boundary.py`（边界文件自身）+ `scripts/llm_smoke.py`（smoke 脚本同入边界扫描域，Leader-A10）= 15。
- **6 方法**（全量 green = gate ④）：
  1. `test_p6_file_set_closed`：白名单 37 文件闭集断言（gate ③ 的 pytest 内镜像）；
  2. `test_p6_no_12_name_in_string_literals`：AST 字符串字面量域 12 名 casefold 词边界扫描 = 0 命中；**文件域 = 27 个 .py 文件**（白名单 28 个 .py 文件 − 边界文件自身：11 个新建 src 模块 + P6_TEST_FILES 15 + 2 个新建测试侧 `__init__.py`：#9 `tests/engine_v2/llm/__init__.py`、#15 `tests/engine_v2/prompts/__init__.py`——其中 P6_TEST_FILES 所含边界文件自身 `tests/engine_v2/core/test_import_boundary.py` 在此扣减）；**明确排除** = 2 个既有骨架 src `__init__.py`（`src/engine_v2/llm/__init__.py` 9 行、`src/engine_v2/prompts/__init__.py` 7 行——P0 冻结、零修改、不在白名单；DEV-4 已登记其 docstring 措辞冲突；实测 llm/ 骨架 docstring 命中 openai/llm/provider，prompts/ 骨架 clean）+ 边界文件自身 `tests/engine_v2/core/test_import_boundary.py`（白名单 #37 = 纯追加 TestP6Boundary 块、Leader hunk；其既有冻结内容含 12 名明文常量 `P4_LLM_PROVIDER_BLACKLIST` 等，实测 42 处命中（K8 12 名 casefold 词边界 token 累加计，langchain ∈ 12 名（SOT L17）；其中 langchain 2 处（`PROVIDER_ROOTS` 与 `P4_LLM_PROVIDER_BLACKLIST` 各 1）；剔 langchain 的 11 名辅助口径 = 40），不可移除——不入 12 名 AST 字符串字面量扫描域；镜像 P5 先例 `_p5_all_files()` / `_p5_ast_face()` 封闭集排除（P5_TEST_FILES 亦不含边界文件自身，P5 块以拼接构造自豁免）；边界文件仍保留在方法 1 文件集闭集域与方法 3/4/5/6 import 面域，仅方法 2 字符串字面量面排除；P6 追加块自身同样以拼接构造自豁免（方法 2 探针规则），不做单独块级扫描（与 P5 完全同构））；非 .py 文件不入域（项目侧 yaml fixture（v2_project_llm）归 P5 validator `check_deployment_leakage` 全文扫描面，用户域 `v2_deployment/*.yaml` 不入任何 12 名扫描面（与 L189/AD-4 一致）；pyproject.toml 不入域）；探针串拼接构造；拼接集 == P4_LLM_PROVIDER_BLACKLIST 断言；同构锚 = P5 SOT §6.4 行 2（test_p5_12_name_blacklist：_p5_all_files() 同型文件集封闭 + 拼接探针自豁免 + 负例锚；P5 扫描域为全文 casefold 口径，P6 收紧为 AST 字符串字面量口径；P6 域 = 上钉 27 文件域）；
  3. `test_p6_no_v1_absolute_imports`：`src.game.*` / `src.config.*` / `src.agents.*` / `src.llm.*` / `src.prompts.*` 绝对 import = 0；
  4. `test_p6_zero_asyncio`：import asyncio = 0 且 `ast.AsyncFunctionDef` = 0；
  5. `test_p6_nondeterminism_and_io_surface`：random/datetime = 0 命中；`time` 与 `httpx` import 仅 llm/adapter.py（+ `tests/engine_v2/llm/test_adapter.py` MockTransport 进程内面 = B3 受控偏离 ERR-P6-6，唯一文档化测试侧 httpx import；ERR-P6-12）；socket/urllib/requests/http.client = 0；动态加载面（importlib/__import__）= 0（边界文件自身 P4 冻结可导入性探针 harness 自豁免，同方法 2 排除同型；ERR-P6-12）；
  6. `test_p6_policy_strict_face`：policy.py 模块 import ∩ {httpx, time, random, asyncio, datetime, socket, urllib, requests} = ∅；LLMPolicy 类体注解面零具体后端类名（B-CON-4 AST 面）。

### 3.13 波次与文件白名单（封闭集，Leader-A9）

**波次**（D-P6-16 执行序；波内并行、波间依赖串行）：

| 波 | 文件 | 任务 | 依赖 |
|---|---|---|---|
| W1 | profiles.py, deployment.py, prompts/diagnostic.py | T02, T03 前（diagnostic 载体先行，首消费者 T03） | 无（pydantic + core/content 冻结面） |
| W2 | router.py | T03 后 | W1 |
| W3 | adapter.py | T04 传输面 | 无（core 冻结面） |
| W4 | registry.py, assembler.py, structured.py | T05, T04 解析面 | structured 运行期 import assembler 的 wire 模型 → 同波内 assembler 先落、structured 后落 |
| W5 | policy.py, staleness.py | T06, T07 | W1-W4 全 |
| W6 | critic.py + gate/adversarial 测试 + fixtures + smoke + Leader hunks | T08/T09/T10 | W5 全 |

**文件白名单（封闭集，37 文件；gate ③ 机械面 = `git diff --name-only <P6-BASELINE-SHA>..HEAD -- src tests pyproject.toml scripts` 恰 37 行，F-05）**：

| # | 文件 | 新建/修改 | 波次 |
|---|---|---|---|
| 1 | `src/engine_v2/llm/profiles.py` | 新建 | W1 |
| 2 | `src/engine_v2/llm/deployment.py` | 新建 | W1 |
| 3 | `src/engine_v2/prompts/diagnostic.py` | 新建 | W1 |
| 4 | `tests/engine_v2/llm/test_profiles.py` | 新建 | W1 |
| 5 | `tests/engine_v2/llm/test_deployment.py` | 新建 | W1 |
| 6 | `src/engine_v2/llm/router.py` | 新建 | W2 |
| 7 | `tests/engine_v2/llm/test_router.py` | 新建 | W2 |
| 8 | `src/engine_v2/llm/adapter.py` | 新建 | W3 |
| 9 | `tests/engine_v2/llm/__init__.py` | 新建 | W3 |
| 10 | `tests/engine_v2/llm/test_adapter.py` | 新建 | W3 |
| 11 | `src/engine_v2/llm/structured.py` | 新建 | W4 |
| 12 | `src/engine_v2/prompts/registry.py` | 新建 | W4 |
| 13 | `src/engine_v2/prompts/assembler.py` | 新建 | W4 |
| 14 | `tests/engine_v2/llm/test_structured.py` | 新建 | W4 |
| 15 | `tests/engine_v2/prompts/__init__.py` | 新建 | W4 |
| 16 | `tests/engine_v2/prompts/test_registry.py` | 新建 | W4 |
| 17 | `tests/engine_v2/prompts/test_assembler.py` | 新建 | W4 |
| 18 | `src/engine_v2/llm/policy.py` | 新建 | W5 |
| 19 | `src/engine_v2/llm/staleness.py` | 新建 | W5 |
| 20 | `tests/engine_v2/llm/conftest.py` | 新建 | W5 |
| 21 | `tests/engine_v2/llm/test_policy.py` | 新建 | W5 |
| 22 | `tests/engine_v2/llm/test_staleness.py` | 新建 | W5 |
| 23 | `src/engine_v2/llm/critic.py` | 新建 | W6 |
| 24 | `pyproject.toml` | 修改（+httpx 行，**Leader hunk**） | W6 |
| 25 | `tests/engine_v2/llm/test_critic.py` | 新建 | W6 |
| 26 | `tests/engine_v2/llm/test_p6_gate_scenario.py` | 新建 | W6 |
| 27 | `tests/engine_v2/llm/test_p6_adversarial.py` | 新建 | W6 |
| 28 | `tests/fixtures/v2_project_llm/game.yaml` | 新建 | W6 |
| 29 | `tests/fixtures/v2_project_llm/characters/alice.yaml` | 新建 | W6 |
| 30 | `tests/fixtures/v2_project_llm/prompts/game_policy.yaml` | 新建 | W6 |
| 31 | `tests/fixtures/v2_project_llm/prompts/character_alice.yaml` | 新建 | W6 |
| 32 | `tests/fixtures/v2_project_llm/prompts/game_policy.md` | 新建 | W6 |
| 33 | `tests/fixtures/v2_project_llm/prompts/character_alice.md` | 新建 | W6 |
| 34 | `tests/fixtures/v2_deployment/deployment.yaml` | 新建 | W6 |
| 35 | `tests/fixtures/v2_deployment/deployment_alt.yaml` | 新建 | W6 |
| 36 | `scripts/llm_smoke.py` | 新建 | W6 |
| 37 | `tests/engine_v2/core/test_import_boundary.py` | 修改（纯追加 TestP6Boundary 块，**Leader hunk**） | W6 |

**gate 运行序（六步，机械可复跑，P5 SOT:569 先例同构）**：
1. `.venv/bin/python -m pytest tests/ -x -q`（基线 2669 + P6 增量全绿）；
2. `.venv/bin/python -m ruff check src/engine_v2/llm src/engine_v2/prompts tests/engine_v2`（line-length 100，target py312）；
3. `git diff --name-only <P6-BASELINE-SHA>..HEAD -- src tests pyproject.toml scripts` == 白名单 37（#1-37 精确等值，波次排序，§3.13 表）；
4. `TestP6Boundary` 6 方法全绿（§3.12）；
5. 回归 = TestP5Boundary + TestP4Boundary + TestB1StaticScan/TestB3OfflineRunnable + skeleton + P5 gate scenario 20 断言（零回退）；
6. fake e2e（G6-1 面，test_p6_gate_scenario 包内）+ `scripts/llm_smoke.py` 无凭据进程内 dry-run（exit 3 确定，CI 安全）。

**fixture 面**（W6，Leader-A7 fake e2e）：`v2_project_llm/` = 最小 P5 合规游戏项目（1 character alice + capabilities 声明 `major_character`（min_tier=2, ideal_tier=3）+ prompts 两条 policy 指 .md 模板）；`v2_deployment/` 两文件 = 同 capability 两档模型（deployment.yaml 高模型 / deployment_alt.yaml 低模型——G6-2 换模型面；**alt 模型 tier ≥ min 以保 e2e 可跑，#5-6 断言 resolved_model 差异**）。

---

## §4 决策登记表（D-P6-01 … D-P6-22）

格式：问题 / 备选 / 选择 / 理由（引 Leader 预判编号 Leader-A1~Leader-A12 或 SOT）/ 机械验证面。Leader-A1~Leader-A12 全部原样执行，不复议；AD-1~AD-9 = 对抗探针编号（§6.3），与 Leader 裁定编号区分。

### D-P6-01 模块落位（= Leader-A1 执行）
- **问题**：P6 代码放哪？
- **备选**：① skeleton 预留槽位 `src/engine_v2/llm/` + `src/engine_v2/prompts/`；② 新顶层包；③ 并入 core。
- **选择**：①。`llm/` 8 模块 + `prompts/` 3 模块（§3 总览）。core 冻结 32 子模块（含 __init__.py 物理 33 个 .py 文件）308 导出零触碰；content/plugins 冻结；skeleton `llm/__init__.py`（9L）与 `prompts/__init__.py`（7L）**零修改**（占位 docstring 与 Leader-A4 的措辞冲突 = DEV-4 登记披露，改期归 Leader）。
- **理由**：Leader-A1 预判 + README.md:21-22（llm/=Phase 6, prompts/=Phase 6 槽位声明）。ADR-004 Decision 3 默认 Capability→provider 映射表（宿主文件 model-routing-providers.md）：P6 不承载该表——部署缺失走显式失败诊断（`LLMSIM_RESOLVER_*`，D-P6-07），不回落默认表，即不触及其适用面（P6R1-2-06 兼容注记）。
- **机械验证面**：白名单 37 文件闭集（§3.13）；core 目录 diff = 空（gate ③ 的 name-only 集合不含 core/）。

### D-P6-02 T02 消歧（= Leader-A2 执行）
- **问题**：Plan T02「能力档案定义（context length / multimodal / reasoning class / structured-output / tool）」与 P5 已冻结的 game 侧 `InferenceCapabilityProfile` 字段封闭裁决冲突（P5 严格度未知键 = error，字段不可扩）。
- **备选**：① P6 扩 game 侧 schema（破 P5 冻结）；② P6 只交付 model 侧（profile + tier + 匹配），game 侧零新面；③ 建平行第二套 game 侧档案。
- **选择**：②。P6 交付 = `ModelCapabilityProfile`（部署侧，§3.1）+ tier 尺度 0-4（§3.1）+ router 匹配（§3.3）；game 侧 `InferenceCapabilityProfile` = P5 冻结消费面只读（schemas.py:395-416）。Plan:644-650 允许清单（context length requirement / multimodal requirement / reasoning class / structured-output requirement / tool requirement / recommendation）的**细粒度项目全部经 tier 尺度抽象承载**（tier 档内含 context_length_min/max_output_min/structured_output_required/reasoning_class_min 四维，§3.1 表）；推荐 = ideal_tier warning 语义（§3.3 步骤 5）。
- **理由**：Leader-A2 预判（P5 冻结 + 字段封闭 + G5 已裁决，不可逆）；Spec §5.4/§5.5 字段表（Spec:409-418/426-441）为 MAY 级示例非冻结字段表（Spec 原文示例值非字段封闭清单）。
- **机械验证面**：content/ 目录 diff = 空（gate ③）；P6 src 对 InferenceCapabilityProfile 零 import 写面（只读类型引用经 router 参数签名）；DEV-1 登记（§8.4）。

### D-P6-03 tier 尺度 + REASONING_CLASSES + capability 字符串约定（开放项裁决）
- **问题**：tier 数值尺度、推理等级词表、capability 标识符域均无 SOT 冻结值，P6 须钉死。
- **备选**：① tier 0-4 五档（本文）；② 三档（低/中/高）；③ 无档，纯数值门槛。
- **选择**：①。tier 0-4 封闭 5 档（§3.1 表，context_length_min/max_output_min 严格单调递增）；REASONING_CLASSES 封闭 4 值 {none, standard, advanced, deep} + REASONING_ORDER 递增序；capability = logical role id，pattern `^[a-z][a-z0-9_]{0,63}$`，与 Spec §5.4 inference_profiles 键 / game 侧 capability / trace logical_role 三处同域。
- **理由**：开放项自裁（无 Leader-A 号覆盖）；五档 = 区分度与可枚举性平衡；单调性 = tier 比较的机械可验证性；三同域 = G6-2「改部署不改游戏」的引用链闭合（#5/#19 断言）。
- **机械验证面**：TIER_SCALE 单调性断言（test_profiles）；REASONING_CLASSES/ORDER 封闭集断言；CAPABILITY_RE 正反例矩阵；#5（resolved_model 两部署差异）/#19（9 键中 logical_role==profile==capability）断言链。

### D-P6-04 credential 模型（= Leader-A5 执行）
- **问题**：API 凭据如何表示、解析、禁止入 trace？
- **备选**：① env 名化（entry 存变量名，调用点 os.environ 取值）；② entry 存值；③ 宿主 secret 注入函数。
- **选择**：①。`api_key_env: str | None`（pattern `^[A-Z][A-Z0-9_]{0,127}$`，None = 无需认证）；`resolve_api_key` 唯一取值点，返回值仅存调用方内存；HttpxInferenceBackend 内值只入 header 局部变量；ResolvedModel/InferenceRequest 全链只名。
- **理由**：Leader-A5 预判（G6-5「trace 不记录 credential」+ 部署文件可入库面）；Spec:1674「Credential MUST NOT 进入 trace。」（逐字）。
- **机械验证面**：#12（AD-1 探针：注入假凭据 env → e2e → 全 trace 序列化文本缺值，payload 恰 9 键）；#18（字段内省：ResolvedModel/DeploymentEntry/InferenceRequest 无值型 credential 字段）；test_deployment resolve_api_key 缺失/命中两用例。

### D-P6-05 deployment 文件形状 + 指针优先级（开放项裁决）
- **问题**：用户侧部署文件的形状、路径解析、错误面。
- **备选**：① 两节 models + inference_profiles（本文）；② Spec §5.4 单节平铺；③ 每 capability 独立文件。
- **选择**：①。`models: dict[model_id, ModelCapabilityProfile]` + `inference_profiles: dict[capability, DeploymentEntry]`（§3.2 字段表）；指针优先级 = 显式参数 > `LLMSIM_DEPLOYMENT` env > None（DEPLOYMENT_ENV_POINTER 常量）；形状错 = ValidationError → 诊断 `LLMSIM_RESOLVER_DEPLOYMENT_PARSE`（profile=None）；引用错 = 诊断 + profile 保留（resolve 期二次拦截）。
- **理由**：开放项自裁；两节 = model 目录与 capability 绑定分离（一模型多能力复用 = 用户自由度，G6-2 换模型面只需改 entry 指向）；Spec:405「部署配置属于用户」；单节示例 = MAY 级（DEV-5 登记）。
- **机械验证面**：test_deployment 12 用例（缺失/解析错/键==model_id/pattern 违规/引用缺失/指针优先级三态/resolve_api_key）；gate ①。

### D-P6-06 同步面（= Leader-A3 执行）
- **问题**：Spec §31.1 给 `async def generate` 签名（Spec:1638），引擎全树零 asyncio（§42.1 NO NETWORK 纪律 + scheduler 纪律段 L105-111）。
- **备选**：① P6 同步面（本文）；② P6 局部 asyncio 事件循环；③ 维持 async 签名 + 宿主 loop。
- **选择**：①。`InferenceBackend.generate` 同步 Protocol（§3.4）；LLMPolicy.decide 同步（B-CON-1）；T07 的 async 语义重读 = time 语义（staleness TTL 推导，§3.7）。asyncio 全树零容忍（TestP6Boundary 方法 4）。
- **理由**：Leader-A3 预判；B-CON-1（behavior_policy.py:54-67）+ §42.1（Spec:1995-1999）+ scheduler 纪律段（scheduler.py:105-111 datetime/time/random/asyncio 黑名单先例）。
- **机械验证面**：#20（B-CON 五件套）；TestP6Boundary 方法 4（asyncio import + AsyncFunctionDef 双零）；DEV-2/DEV-3 登记。

### D-P6-07 fallback 梯度（开放项裁决）
- **问题**：capability 解析失败/降级时的行为面。
- **备选**：① 同 capability 池内 primary+fallbacks 声明序 + min_tier 硬门槛 + 显式失败（本文）；② 跨 capability 借用；③ 任意最低可用模型静默兜底；④ 调用期跨模型热切换。
- **选择**：①。resolve 五步钉死（§3.3）：无 entry → `LLMSIM_RESOLVER_NO_DEPLOYMENT`；候选无满足 min_tier → `LLMSIM_RESOLVER_TIER_MISMATCH`（**绝不静默换模型**）；tier < ideal_tier → warning `LLMSIM_RESOLVER_BELOW_IDEAL`（不阻断）。**P6 不实现调用期跨模型 fallback**（ADR-004 L41 graceful degradation 的调用期面 = OI-P6-3，显式错误面先行，降级留给后续相）。
- **理由**：开放项自裁；G6-2「user DeploymentProfile 可以改变实际模型」= resolve 期面（部署文件即唯一模型变更入口）；ADR-004 L41 允许 fallback 语义但调用期热切换破坏 K7 双跑确定性（重试语义归 parse 层，D-P6-09）。
- **机械验证面**：test_router 12 用例（五步各分支 + 诊断序）；#5-6（两部署两模型）；AD-9（tier mismatch 显式失败探针）；AD-7（NO_DEPLOYMENT 显式失败探针）。

### D-P6-08 传输面（= Leader-A4 执行）
- **问题**：用什么库、什么 wire 约定、可替换性口径。
- **备选**：① httpx 同步 + provider-neutral JSON + OpenAI 兼容默认端点（本文）；② provider SDK；③ 手写 urllib；④ 全 fake 无真客户端。
- **选择**：①。`HttpxInferenceBackend`（§3.4）= 唯一真实传输；端点约定 = `base_url + "/chat/completions"`（默认 OpenAI 兼容形状 = **可替换接口约定，非 core contract**）；零 provider SDK（12 名扫描域含标识符豁免口径——包名 `llm`/字段名 `provider`/`model`/`base_url` 豁免，字符串字面量域零命中）；`InferenceBackend` Protocol = 可替换性本体（G6-6「LLM parser 不依赖特定 provider 语义作为 Core Contract」）。
- **理由**：Leader-A4 预判（httpx 在 venv 白面 + 同步面 + 零 SDK）；G6-6 逐字（Plan:661-666）；v1 langchain ChatOpenAI 依赖 = 拆除对象（ADR-002 L24-28 policy 替换清单 + §7.4 行 8/9）。
- **机械验证面**：#14（三族提取 provider-neutral）；#15（wire 可替换性：Fake vs httpx.MockTransport 同提案）；#16（12 名 AST 扫描 0 命中）；TestP6Boundary 方法 5（httpx 仅 adapter.py）。

### D-P6-09 结构化输出（= Leader-A6 执行）
- **问题**：如何从 provider 自由文本得到 typed 结果，失败面如何。
- **备选**：① L0 prompt 层 JSON 契约（引擎所有）+ 健壮提取 + pydantic wire 模型 + parse retry 上限 1 + 终败 = 诊断 + None（本文）；② provider structured-output API 面；③ retry 上限 2（v1 先例）。
- **选择**：①。`extract_json_robust` 三族（fence/裸/整体，§3.5）+ `LLMActionProposal`（extra="ignore"，§3.10）+ PARSE_RETRY_MAX=1 + repair_instruction 确定性反馈；终败 → `LLMSIM_INFERENCE_PARSE_FAILED` + None（B-CON-3 no-op 语义，不 crash）。
- **理由**：Leader-A6 预判；G6-6（parser 不依赖 provider 语义）；v1 max_retries=2（parser.py:35）在 K7 下预算翻倍无收益——上限 1 钉死（#15 调用次数断言）。
- **机械验证面**：test_structured 12 用例（三族正反例 + pydantic 违例面 + 确定性）；AD-6（全坏 JSON 探针：调用次数==2、parse_retry==1、PARSE_FAILED、None）/ AD-7（NO_DEPLOYMENT 探针：policy None）；#19（parse_retry ∈ {0,1}）。

### D-P6-10 critic（= Leader-A6 执行，含目标键封闭面自裁）
- **问题**：critic 的形状、默认态、修复预算。
- **备选**：① 确定性规则 critic + flag 默认关 + 一次性修复（本文）；② LLM critic；③ 默认开。
- **选择**：①。`critique`（§3.8）= action_id ∈ candidate_actions + 目标可见性（目标键封闭集 {entity_id, target_id, target, actor_id}）；CRITIC_DEFAULT_ENABLED=False；修复 = 一次 critique_instruction 调用，无再重试；decide 总调用预算 = 3（1+parse 1+critic 1）。
- **理由**：Leader-A6 预判（可选、默认关、一次性修复）；LLM critic 破 K7 + 预算不定。
- **机械验证面**：test_critic 8 用例；#15（critic 关/开双态下提案相等——默认关面）；AD 系调用计数断言（AD-6/AD-7/AD-8）。

### D-P6-11 模板文件读取（= Leader-A12 执行）
- **问题**：PromptPolicy.template_ref 指向什么文件、如何读、如何防越界。
- **备选**：① .md 文本 + {{var}} 替换 + 路径纪律（本文）；② .yaml 结构化模板（并入 P5 loader glob 面）；③ jinja2。
- **选择**：①。模板 = `prompts/*.md` 纯文本（**P5 loader glob 面外**——loader.py:50-60 的 9 类模板不含 .md，P5 不可见 = 披露项 OI-P6-1）；`{{var}}` 单次线性替换（无 jinja2，venv 白外面）；`validate_template_ref` realpath 前缀检查（绝对/`..`/symlink 逃逸 → `LLMSIM_PROMPT_PATH_ESCAPE`）；变量纪律三码（UNDECLARED/MISSING/UNSUPPORTED，§3.9）。
- **理由**：Leader-A12 预判；P5 PromptPolicy 字段封闭（schemas.py:418-426，template_ref = prompts/-relative-path 口径）；jinja2 不在 venv 白面（环境事实）。
- **机械验证面**：test_registry 13 用例（逃逸含 symlink 探针对、重复 id、空文件、缺失、SCOPE_UNKNOWN 步 1.5（F-03））；AD-5 探针（§6）；gate ④ 方法 2（模板文本 12 名扫描）。

### D-P6-12 组装器 L0-L4 + 供给天花板（开放项裁决，含同 scope 冲突规则）
- **问题**：层结构、变量供给面、override 语义、同 scope 多 policy 行为。
- **备选**：① 本文 §3.10 全量规则；② 每层独立文件；③ 变量白名单由游戏声明。
- **选择**：①。L0-L4 封闭 5 层（PromptLayer 枚举）；**CONTEXT_VARIABLES = ActorDecisionContext 13 字段名精确集**（K4 天花板，context_provider.py:299-314）——供给面封闭 = assembler 代码即白名单，游戏声明 variables 只能从 13 名中选；override 只换 L1/L2（D-P6-12 自裁；Spec:935 = MAY 替换 + capability boundary 不变依据；Spec:907-909「自定义 PromptAssembler MUST NOT 自动获得未授权数据」= 不提升逐字依据）；L4 本相空段预留；**同 scope 多 policy = casefold 字典序首 id 胜、无诊断**（确定性兜底，P5 无此约束，P6 登记自裁）。
- **理由**：开放项自裁；K4（Spec:295-303 能力限定变量供给）+ Spec §14（层表 L917-931 + MUST data L933 + MAY replace assembler L935）；G6-3（override 不提升 context capability）。
- **机械验证面**：test_assembler 12 用例；#7-9（未授权 → "null"、授权投影精确、unsupported 诊断）；#19（prompt_assembly 记录存在 + 5 键）。

### D-P6-13 import 边界纪律（开放项裁决，含 docstring 文案规则）
- **问题**：P6 的 import 白面与例外。
- **备选**：① §3 导入纪律全量（本文）；② 全树 httpx 允许；③ v1 依赖兼容层。
- **选择**：①。白名单 = stdlib 子集（`__future__ typing re enum os json math pathlib dataclasses collections.abc hashlib`）+ pydantic + yaml + core 冻结面 + content.schemas 冻结面；**两处文档化例外**：httpx 仅 llm/adapter.py、time 仅 llm/adapter.py（SystemMonotonicClock 实现体）；asyncio/datetime/random/socket/urllib/requests/http.client/v1 根/provider SDK 根/动态加载面全禁；**docstring 文案规则**：P6 src 字符串字面量（含 docstring）零 12 名单词（用「推理」「部署方」措辞），测试探针串拼接构造。
- **理由**：开放项自裁，Leader-A5（credential 不入域）/Leader-A4（httpx 限定）/Leader-A8（边界测试规格）综合口径；P5 SOT §6.4 行 2（test_p5_12_name_blacklist）12 名扫描先例（test_import_boundary.py:225-240 常量 + P5 SOT:635）。
- **机械验证面**：TestP6Boundary 方法 2/3/4/5/6 全量（§3.12）；gate ④。

### D-P6-14 fake 模型 e2e fixture（= Leader-A7 执行）
- **问题**：G6-1「假模型可完整跑」的 fixture 形状。
- **备选**：① 最小 P5 合规项目 + 两部署文件 + FakeInferenceBackend（本文）；② 全量 fixture 复用；③ 无 fixture 纯单测。
- **选择**：①。`tests/fixtures/v2_project_llm/`（alice 单角色 + major_character capability 声明 min=2 ideal=3 + 2 条 prompt policy 指 .md 模板）+ `tests/fixtures/v2_deployment/{deployment,deployment_alt}.yaml`（同 capability 两模型，alt 亦满足 min_tier 保 e2e 可跑）；FakeInferenceBackend 脚本化（(logical_role, base_revision, seq) 寻址，§3.4）；e2e 走 P4 冻结管线面（PolicyWakeupHook 先例 conftest.py:719-748：view → DefaultContextProvider.build → run_policy_decide → submit_proposal）。
- **理由**：Leader-A7 预判；G6-1 逐字（Plan:661-666）；PolicyWakeupHook 是既有冻结测试面（零新管线发明）。
- **机械验证面**：#1-4（e2e N tick 完成 + 9 键 + 溯源链 + revision 递增）；gate ⑥。

### D-P6-15 TestP6Boundary 规格（= Leader-A8 执行）
- **问题**：边界测试常量与方法集。
- **备选**：本文 §3.12 全量。
- **选择**：P6_SUBMODULES 11 干名 + P6_TEST_FILES 15 文件名 + 6 方法（§3.12 逐条）。追加于 test_import_boundary.py 纯块（Leader hunk，白名单 #37）。
- **理由**：Leader-A8 预判；P5 TestP5Boundary 5 方法先例（P5 SOT:787-798）扩展 6 方法（+1 = policy 严格面 AST 扫描，B-CON-4 机械面新增）。
- **机械验证面**：gate ④ 自身；常量封闭性 = 方法 1 白名单镜像断言。

### D-P6-16 白名单 + gate 运行序 + baseline（= Leader-A9 执行）
- **问题**：写面闭集与验证序。
- **选择**：37 文件白名单（§3.13 表，含 2 处 Leader hunk：pyproject.toml httpx 行 + test_import_boundary.py 追加块）；gate 六步（§3.13，P5 SOT:569 先例同构）；baseline SHA 占位符 `<P6-BASELINE-SHA>`（Leader 填实后 gate ③ 可复跑）。
- **理由**：Leader-A9 预判；P5 先例（39 文件白名单 + 六步序，P5 SOT:542-569）。
- **机械验证面**：gate ①-⑥ 全序本身。

### D-P6-17 smoke 脚本（= Leader-A10 执行）
- **问题**：T10 smoke 的形状与 CI 行为。
- **选择**：`scripts/llm_smoke.py`，`main(argv=None, *, env=None) -> int` 纯函数（进程内可测，零 subprocess 依赖）；无 deployment/凭据 → stdout 引导 + **exit 3**（确定性，CI 安全——Plan T10 字面「（不进 CI secrets）」）；有凭据 → 单次真调用 + 打印 9 键形状 JSON + exit 0；异常 → 异常类名 + exit 4；**密钥值永不打印/入日志**（只印变量名）。
- **理由**：Leader-A10 预判；Plan T10（Q27 档，Plan:628-637 任务表，T10 = Plan:637）。
- **机械验证面**：gate ⑥（进程内 dry-run exit 3 断言）；smoke 入 P6_TEST_FILES 边界扫描域（§3.12）。

### D-P6-18 诊断封闭集（= Leader-A11 执行，21 码）
- **问题**：P6 诊断码集、与 P5 关系、触发面。
- **选择**：21 码封闭集（§8.1 表：RESOLVER 6 + INFERENCE 7 + PROMPT 8），**与 P5 18 码零重叠**（机械断言 = 集合不相交）；诊断载体 = P6 本地 `RuntimeDiagnostic` + `P6_RUNTIME_DIAGNOSTIC_CODES`（§3.11，D-P6-21：字段同构 P5 `Diagnostic`（content/schemas.py:523-548），构造期 validator 镜像 P5 L542-548，severity 仅复用 P5 `DiagnosticSeverity`（schemas.py:102-107）跨包只读；P5 `DIAGNOSTIC_CODES` 18 码闭集（schemas.py:112-133）与 P5 validator 零触碰）；每码触发 + 不触发各 ≥1 用例（§6 矩阵）；诊断不中断原则（语义错 → 诊断 + 继续；形状错 → None + 诊断）。
- **理由**：Leader-A11 预判；P5 DIAGNOSTIC_CODES 封闭先例（schemas.py:112-133，18 码）+ P5 诊断族 style（path/refs 面，schemas.py:523-548）。
- **机械验证面**：test_deployment/test_adapter/test_registry 等内嵌触发矩阵；§8.1 计数方程；gate ①。

### D-P6-19 确定性（= K7 落地裁决）
- **问题**：双跑字节相等的实现面。
- **选择**：① 时钟 seam：MonotonicClock Protocol + SystemMonotonicClock（生产）+ FixedMonotonicClock（测试，start_ms=0 step_ms=1）注入 backend，policy 自身零 clock；② proposal_id 确定性推导（sha256 actor:tick:base_revision[:16]，§3.5——不用 uuid4 工厂 ids.py:255-260）；③ 零可变全局（LLMPolicy 无可变状态，decide 内局部计数）；④ JSON 清洗确定性序列化（sort_keys/ensure_ascii=False/separators）；⑤ 诊断序 = (code, path, refs) 排序。
- **理由**：K7（Spec:326-328 调度状态可检查；确定性双跑 = P6 扩展面，D-P6-19 新裁）；P5 D-P5-15 注入先例（DslRng seam 模式同构）。
- **机械验证面**：#17（双跑全 trace 字节相等，AD-8 含坏 JSON 运行 AD-6）；test_adapter FixedMonotonicClock 递增断言；OI-P6-6（proposal_id 规则是否升 core 约定，留 Leader）。

### D-P6-20 trace 集成（= K6 落地裁决）
- **问题**：trace 记录面、sink 注入、artifact 句柄。
- **选择**：TraceSink Protocol 宿主注入（record + record_diagnostic + store_artifact 三方法，§3.6，F-02）；llm_call payload = 9 键精确（= LLM_CALL_PAYLOAD_KEYS，trace.py:76-88，#1/#19 机械断言）；prompt_assembly payload = 5 键（{actor_id, tick, base_revision, prompt_metadata_ref, token_estimate}，TraceKind.PROMPT_ASSEMBLY 既有面 trace.py）；确定性句柄 `prompt://…` / `output://…`；artifact 本体落盘归宿主（P8 面），P6 只给 ref+内容。
- **理由**：K6（Spec:315-324：Event 必须可追踪来源）+ trace.py 冻结面（9 键封闭常量，trace.py:76-88）+ Leader-A5（credential 不入 payload——9 键中无 credential 键，机械面 #18）。
- **机械验证面**：#1（9 键精确集）；#19（prompt_assembly 存在 + 键面）；#12（探针值缺席）；test_policy sink 记录序列断言。

### D-P6-21 P6 诊断载体（R1 新裁，F-01）
- **问题**：P6 诊断的载体类型与封闭集常量落位（R1 审查发现：跨包直用 P5 `Diagnostic` 使 P6 的 21 码无声明落点，且构造期校验无 P6 侧接线面）。
- **备选**：① 跨包直用 P5 `Diagnostic` + 无本地封闭集（原文面）；② P6 本地冻结 pydantic `RuntimeDiagnostic` + `P6_RUNTIME_DIAGNOSTIC_CODES`；③ 扩 P5 侧诊断面（破 P5 冻结，排除）。
- **选择**：②。§3.11：`RuntimeDiagnostic(code: str, severity: DiagnosticSeverity, path: str(min 1), message: str(min 1), refs: tuple[str, ...] = ())`——字段同构 P5 `Diagnostic`（content/schemas.py:523-548）；`P6_RUNTIME_DIAGNOSTIC_CODES: Final[frozenset[str]]`（21 码 = §8.1 表）；构造期 `model_validator(mode="after")` 拒绝 code ∉ 21 码（镜像 P5 validator，schemas.py:542-548）；severity 仅复用 P5 `DiagnosticSeverity`（schemas.py:102-107，跨包只读 import）。模块 import = stdlib + pydantic + content.schemas（DiagnosticSeverity）only，零 core、零 I/O。全 P6 诊断 tuple 类型 = `tuple[RuntimeDiagnostic, ...]`。
- **理由**：P5 冻结面（`DIAGNOSTIC_CODES` 18 码，schemas.py:112-133）与 P5 validator 零触碰；P6 21 码自有声明落点且与 18 码机械断言不相交；同构五字段形状保宿主跨相消费一致；F-01 裁定面。
- **机械验证面**：§3.11 `__all__` 2 导出（`RuntimeDiagnostic`/`P6_RUNTIME_DIAGNOSTIC_CODES`）；conftest session 级 `p6_diagnostic_code_audit`（构造期拒绝 + 21 ∩ 18 = ∅，§6.2，不占 §6.1 平铺计数）；gate ③ 白名单 #3（`prompts/diagnostic.py`）。

### D-P6-22 TraceSink 诊断通道（R1 新裁，F-02）
- **问题**：P6 诊断的入 sink 通道（R1 审查发现：`TraceSink` 原双方法 `record`/`store_artifact` 键集与 kind 词表均封闭，诊断载体无记录通道）。
- **备选**：① 借用 `record(kind, payload)` 携带诊断（破 kind 词表 {llm_call, prompt_assembly} + 封闭键集）；② 第三方法 `record_diagnostic(diag: RuntimeDiagnostic) -> None` 独立通道；③ 诊断上浮宿主自行记录（P6 失去诊断传递纪律）。
- **选择**：②。`TraceSink` Protocol 第三方法 `record_diagnostic(self, diag: RuntimeDiagnostic) -> None`（§3.6，三方法封闭）；`record(kind, payload)` 封闭键集（9 键/5 键）与 kind 词表零变化；诊断 = 独立通道（宿主侧如何落 trace/日志 = 宿主实现面，P6 只交付对象）。
- **理由**：F-02 裁定面；record 键封闭（#1/#19 机械断言）与 kind 词表零改动；载体同构 P5 `Diagnostic` 五字段，宿主一次实现两相消费。
- **机械验证面**：§3.6 Protocol 三方法（L342-345）；TestP6Boundary 方法 6（policy 严格面 AST 扫描含 `record_diagnostic` 签名面）；test_policy sink 记录序列断言含 `record_diagnostic` 调用序。

---

## §5 G6 门禁场景（S0-S9 + 编号断言 #1-#20）

### 5.1 场景脚本（S0-S9）

**S0 环境钉死**：`.venv/bin/python`（3.12）；零真实网络（全部 InferenceBackend = FakeInferenceBackend 或 httpx.MockTransport 进程内面）；FixedMonotonicClock(start_ms=0, step_ms=1)；`LLMSIM_DEPLOYMENT` env 未设（显式路径传参）；临时凭据 env `FAKE_PROBE_KEY` = 探针值 **`PROBE-VALUE-DEADBEEF01`**（AD-1 用，gate 结束 unset）。

**S1 fixture 装载**：`v2_project_llm/` → `load_project`（P5 loader，冻结面）→ IR；capabilities 面取 `major_character`（min_tier=2, ideal_tier=3）；`TemplateStore(project_root, IR.prompts)`（2 文档加载零诊断）；`load_deployment("tests/fixtures/v2_deployment/deployment.yaml")` → profile（0 诊断）；`resolve_capability` → resolved（model=高模型，resolved_via="primary"，0 诊断）。

**S2 组装**：alice actor 的 context（P4 冻结面构造：make_p4_world + PolicyWakeupHook 先例 conftest.py:719-748 的 view → DefaultContextProvider.build 链）→ `assemble_prompt` → package（5 层段，L0 非空，L1/L2 文本 = 模板替换产物，L3 含 13 变量块，L4 空段，0 诊断，token_estimate > 0）。

**S3 首次 tick（e2e 面）**：FakeInferenceBackend 脚本 `{"major_character": (base_rev, 1) → '```json\n{"action_id":"attack","arguments":{"target_id":"bob"},"intent":"hit","confidence":0.9}\n```'}` → `build_llm_policy` → `run_policy_decide(policy, context)`（B-CON 门面）→ proposal（非 None）→ `scheduler.submit_proposal` → revalidation ACCEPT → ActiveAction 入队；sink 记录序列 = [prompt_assembly, llm_call]（2 条）。

**S4 世界推进**：scheduler.step N 次（N ≥ 3，tick 递增）；每 tick 一个 decide 调用（脚本键 (logical_role, base_revision, seq) 逐 tick 递进）；世界 revision 单调递增（next_revision 链，revision.py:73）。

**S5 换模型（G6-2 面）**：同 S1-S4 全链重跑，仅 `load_deployment(deployment_alt.yaml)` 变（alt 模型 tier=2 ≥ min）→ 全部其余字节（项目 fixture sha256）不变。

**S6 越权供给（G6-3 面）**：构造 unauthorized context（global_entity_views=None）+ override 模板文本含 `{{global_entity_views}}` 声明 → 组装 → 该变量渲染 = `"null"`；对照 authorized context（global_entity_views=具体 dict）→ 渲染 == `json.dumps(该值, sort_keys=True, ensure_ascii=False, separators=(",",":"))` 精确相等；unsupported 变量（模板声明 `{{not_a_context_field}}`）→ `LLMSIM_PROMPT_VARIABLE_UNSUPPORTED` 诊断。

**S7 stale 提交（G6-4 面）**：S3 之后，Fake 脚本在**调用期**推进世界（fixture 侧先 submit 一个外部提案使 current revision 前进，再跑 decide 产出 base=旧 revision 的提案）→ `submit_proposal` → revalidation REJECT（base < current，revision.py:78-88）→ 提案不 commit、世界不变、无 ActiveAction、生命周期 FAILED（scheduler.py:1520-1530 REJECT 面）。

**S8 凭据探针（G6-5 面）**：`os.environ["FAKE_PROBE_KEY"] = "PROBE-VALUE-DEADBEEF01"`（gate 内单值，与 S0 同值）→ entry.api_key_env="FAKE_PROBE_KEY" → 全 e2e（S3-S4）→ 收集 sink 全部 record payload + 全部 artifact 内容 → 序列化全文（assert_json_clean 口径）不含探针值；entry/resolved/request 各字段内省无值。

**S9 双跑（K7 面）**：S1-S8 同脚本全链跑两遍（每遍独立实例，FixedMonotonicClock 同参）→ 全部 trace 记录（kind + payload 序列化）+ 全部提案字段逐字节相等。

### 5.2 编号断言（#1-#20，G6 六条逐字映射）

| # | 断言 | G6 条款（Plan:661-666 逐字面） | 场景 | 测试文件 |
|---|---|---|---|---|
| 1 | e2e 跑完 N≥3 tick 零异常；sink 存在 llm_call 记录且 payload 键集合 == LLM_CALL_PAYLOAD_KEYS 精确等值（9 键） | G6-1 假模型可完整跑 | S3/S4 | test_p6_gate_scenario |
| 2 | 每个提交的 ActionProposal 可溯源：provenance.origin == BEHAVIOR_POLICY 且 notes 以 `_LLM_NOTES_PREFIX` 运行时值开头（拼接构造，§3.5） 且 base_world_revision == 对应 llm_call payload 的 base_revision | G6-1（trace 可追溯面） | S3 | test_p6_gate_scenario |
| 3 | 世界 revision 经提交事务单调递增（每 ACCEPT 后 current == next_revision(prev)） | G6-1（世界一致性） | S4 | test_p6_gate_scenario |
| 4 | prompt_assembly 记录存在，payload == {actor_id, tick, base_revision, prompt_metadata_ref, token_estimate} 5 键；prompt_metadata_ref == llm_call 的 prompt_metadata_ref（同 tick 同句柄） | G6-1（组装可审计面） | S3 | test_p6_gate_scenario |
| 5 | S5 对比：两部署文件 → 两 e2e 的 llm_call resolved_model 不同（高模型 ≠ 低模型）；项目 fixture 树 sha256 逐文件相等（未动） | G6-2 user DeploymentProfile 可以改变实际模型而不修改游戏项目 | S5 | test_p6_gate_scenario |
| 6 | alt e2e 的 resolved_via == "primary"（alt 亦主位命中）且 resolved 的 tier ≥ min_tier；两 e2e 提案结构面（action_id/arguments）逐字段相等（同脚本） | G6-2（行为不变面） | S5 | test_p6_gate_scenario |
| 7 | S6 unauthorized：override 模板 `{{global_entity_views}}` 渲染 == `"null"`；prompt 全文不含未授权数据任何片段（探针实体 id 缺席） | G6-3 Prompt override 不提升 context capability | S6 | test_p6_gate_scenario |
| 8 | S6 authorized：渲染 == 授权数据精确 JSON（sort_keys/ensure_ascii=False/紧凑分隔） | G6-3（供给正确性面） | S6 | test_p6_gate_scenario |
| 9 | S6 unsupported：`{{not_a_context_field}}` → LLMSIM_PROMPT_VARIABLE_UNSUPPORTED（error）且 package=None（显式失败） | G6-3（天花板面） | S6 | test_p6_gate_scenario |
| 10 | S7：调用期世界已前进 → submit 后 decision.outcome == REJECT（is_stale base<current） | G6-4 stale ActionProposal 不会直接 commit | S7 | test_p6_gate_scenario |
| 11 | S7 后：世界状态逐字段 == 提交前快照（无变更）；无新 ActiveAction；该提案生命周期 == FAILED | G6-4（无副作用面） | S7 | test_p6_gate_scenario |
| 12 | S8：探针值缺席于全部 trace 序列化文本 + 全部 artifact 内容；llm_call payload 恰 9 键（无 credential 键） | G6-5 trace 不记录 credential | S8 | test_p6_gate_scenario |
| 13 | S8：DeploymentEntry.api_key_env == 变量名（pattern 过）；resolve_api_key 返回值 == 探针值（内存面）；ResolvedModel 无值字段（字段内省） | G6-5（名字化模型面） | S8 | test_p6_gate_scenario |
| 14 | extract_json_robust 三族（fence 包裹 / 裸 JSON / 前置杂文+裸 JSON）各命中正确对象；provider 中立 = 函数体零 12 名（AST 扫描） | G6-6 LLM parser 不依赖 DeepSeek/OpenAI 特定语义作为 Core Contract | 单元面 | test_p6_gate_scenario（委托 test_structured 语义，gate 文件内复跑断言） |
| 15 | wire 可替换性：同脚本下 FakeInferenceBackend 与 HttpxInferenceBackend(httpx.MockTransport 同脚本 JSON) → make_action_proposal 产物逐字段相等 | G6-6（可替换面） | S3 对照 | test_p6_gate_scenario |
| 16 | P6 全部 src+test .py 文件（27 文件域，边界文件自身除外，§3.12 方法 2）AST 字符串字面量域 12 名扫描 == 0 命中（fixture .md/.yaml 文本面经 P5 validator check_deployment_leakage 覆盖（S1 fixture validate 零诊断）） | G6-6（12 名封闭面，K8） | 静态面 | test_p6_gate_scenario（= TestP6Boundary 方法 2 的 gate 内镜像） |
| 17 | S9 双跑：全部 trace 记录 + 提案字段逐字节相等（含 S7 REJECT 路径与坏 JSON 运行） | 不变式 K7 | S9 | test_p6_gate_scenario |
| 18 | 字段内省：ResolvedModel/DeploymentEntry/InferenceRequest/InferenceResponse 全部字段类型面零 credential 值位；12 名标识符豁免口径 = 扫描域排除标识符（探针：`api_key_env` 字段名本身不命中扫描） | 不变式 K8 | 静态面 | test_p6_gate_scenario |
| 19 | 9 键值域面：logical_role == profile == capability 三同域；parse_retry ∈ {0,1}；base_revision == int；input_token_estimate == int == estimator.estimate(pkg.text) | 不变式 K6 | S3 | test_p6_gate_scenario |
| 20 | B-CON 五件套机械面：decide 同步非协程（inspect.iscoroutinefunction == False）；单参（签名面）；返回 ActionProposal | None（双态用例）；LLMPolicy 类体 AST 零 random/clock/网络面（方法 6 镜像）；actor_id 一致（构造注入 capability 与 context.actor_id 面，经 run_policy_decide 触发 PolicyActorMismatchError 反例断言） | 不变式 K5（B-CON-1..5） | S3 面 | test_p6_gate_scenario |

**G6 六条 → 断言覆盖核对**：G6-1 = #1-4；G6-2 = #5-6；G6-3 = #7-9；G6-4 = #10-11；G6-5 = #12-13；G6-6 = #14-16；不变式 K5/K6/K7/K8 = #17-20。**6/6 全覆盖，20/20 编号闭合。**

---

## §6 测试计划（138 平铺函数）

**纪律**：全部测试 = 平铺函数（无 class、无 fixture 类继承、无 subprocess——AD-8/P5 先例）；fixture 数据经 conftest 平铺 fixture（pytest 原生）装载；确定性 = 双跑字节相等（#17/AD-8）；零真实网络（httpx.MockTransport = 进程内假传输，披露项）；gate scenario 文件与 §5.2 编号 1:1（20 函数 `test_g6_01` … `test_g6_20`）。

### 6.1 逐文件函数计数（合计 138）

| 文件 | 函数数 | 覆盖要点 |
|---|---|---|
| tests/engine_v2/llm/test_profiles.py | 10 | TIER_SCALE 单调性 2 断言合并 1 函数；REASONING_CLASSES/ORDER 封闭 1；tier_level 正反 2；ModelCapabilityProfile 形状违例（forbid 未知键 / tier 越界 / ctx 低于档下限 / structured_output 档要求缺失 / reasoning_class 低于档下限）5；CAPABILITY_RE 正反 1 → 共 10 |
| tests/engine_v2/llm/test_deployment.py | 12 | DEPLOYMENT_ENV_POINTER 负例自检 1；resolve_deployment_path 三态 3（显式/env/None）；load_deployment 缺失 1；解析错 1；键≠model_id 1；pattern 违规（api_key_env 小写 / 超长）1；model 未声明 1；fallbacks 未声明 1；load_deployment_auto 三态 1（resolve_api_key 命中/缺失断言并入，W1 实现面，ERR-P6-1）；诊断确定性序 1 → 12 |
| tests/engine_v2/llm/test_router.py | 12 | 无 capability 1；MODEL_UNDECLARED 跳过 1；TIER_MISMATCH 显式失败 1；BELOW_IDEAL warning 不阻断 1；primary 胜出 1；fallback 序（primary 不达标 → fallback 1 达标，resolved_via="fallback:1"）1；多 fallback 首个满足者胜 1；candidates_for 空/序 1；meets_tier 边界 1；resolved_via 编码 1；诊断序 (code,path,refs) 1；不跨 capability 借用 1 → 12 |
| tests/engine_v2/llm/test_adapter.py | 12 | FixedMonotonicClock 递增 1；WireMessage 形状 1；InferenceRequest 构造面 1；Httpx：endpoint 缺失 1；credential 缺失 1；成功（MockTransport）1；非 2xx 1；malformed 1；transport 异常 1；credential 值不进异常 message 1；Fake：脚本命中/缺省/calls 序列 1；双 Backend 确定性 1 → 12 |
| tests/engine_v2/llm/test_structured.py | 12 | extract 三族正例 3；extract 无 JSON 1；extract fence 内非 JSON 1；parse 成功/失败 2；extra="ignore" 容忍 1；confidence 越界 1；repair_instruction 确定性 1；make_action_proposal 全字段映射（valid_until 透传断言并入，W4 实现面，ERR-P6-8）1；proposal_id 确定性（同入同出 + 异 tick 异出）1 → 12 |
| tests/engine_v2/llm/test_policy.py | 10 | 成功路径（9 键 + 记录序 + artifact 双 ref）1；组装失败 → None 1；解析终败（双败）→ None + PARSE_FAILED 诊断 1；parse retry 1 次（调用次数==2、parse_retry==1）1；critic 关/开默认面 1；critic 修复 1 次成功 1；critic 终败 → None 1；no-op（action_id None）→ None 1；build_llm_policy 失败 → policy None 1；B-CON 面（非协程/单参/None 态）1 → 10 |
| tests/engine_v2/llm/test_staleness.py | 8 | COMMITTABLE_OUTCOMES 封闭 1；effective_valid_until None 透传 1；TTL 计算（base+ttl）1；ttl 非法（0/负）1；is_stale 边界（== valid_until 不 stale）1；handle_result 四态 1；REBASE rebased_proposal 非空面 1；is_acceptable 四值 1 → 8 |
| tests/engine_v2/llm/test_critic.py | 8 | no-op 跳过 1；action 不在候选 1；目标不可见 1；目标键封闭集（未知键不查）1；全过 1；critique_instruction 确定性 1；多错排序 1；CRITIC_DEFAULT_ENABLED 值 1 → 8 |
| tests/engine_v2/prompts/test_registry.py | 13 | 正常加载 1；重复 policy id 1；路径逃逸（`..`）1；绝对路径 1；symlink 逃逸 1；文件缺失 1；空文件 warning 1；未声明变量 1；缺值变量 1；render 单次线性（重复 token 全替换）1；诊断确定性序 1；UTF-8 读取 1；SCOPE_UNKNOWN（步 1.5，F-03）1 → 13 |
| tests/engine_v2/prompts/test_assembler.py | 12 | CONTEXT_VARIABLES == 13 字段名精确集 1；context_variable_value 未授权 null 1；context_variable_value 序列化口径 1；unsupported None 1；L0 非空 + 零 12 名 1；L1 渲染面 1；L2 渲染面 + 同 scope 首 id 1；L3 全量 13 块 1；L4 空段 1；压平序 + 分隔标记（期望串 = §3.10 步 6 显式逐层拼接口径：L0 居首、L1-L4 各前置本层标记，标记 = `"\n\n<!-- LAYER:" + seg.layer.name + " -->\n"`）1；error 级诊断 → package None 1；token_estimate 口径 1 → 12 |
| tests/engine_v2/llm/test_p6_gate_scenario.py | 20 | test_g6_01 … test_g6_20（= §5.2 行 1:1，平铺函数） |
| tests/engine_v2/llm/test_p6_adversarial.py | 9 | AD-1 凭据泄漏探针 1；AD-2 stale/valid_until 边界探针 1；AD-3 override 提权探针 1；AD-4 12 名泄漏探针 + 部署文件负例（部署文件可含 12 名词——用户文件域，src 扫描零命中）1；AD-5 模板路径遍历（含 symlink 创建）1；AD-6 坏 JSON retry 上限（调用次数==2、parse_retry==1、None）1；AD-7 无部署显式失败（NO_DEPLOYMENT + policy None）1；AD-8 双跑字节相等（含坏 JSON 运行）1；AD-9 tier mismatch 显式失败 1 → 9 |
| **合计** | **138** | 10+12+12+12+12+10+8+8+13+12+20+9 = 138 |

### 6.2 conftest.py（tests/engine_v2/llm/）平铺 fixture 面

- `fake_clock`：FixedMonotonicClock(start_ms=0, step_ms=1) 每用例新实例；
- `mem_sink`：平铺 list 收集 record/artifact（闭包类内联实现，零 import 面）；
- `alice_context`：P4 口径构造（make_p4_world 先例 conftest.py:472 口径移植）——alice actor + bob 实体 + candidate_actions 含 "attack" + granted_capabilities 面；**字段值 JSON 原生**（self_view = EntityView 形状 dict 镜像 / visible_entities、granted_capabilities = tuple / local_entity_views = dict / observations = tuple / knowledge = None——ActorDecisionContext = plain frozen dataclass 无运行时校验，context_provider.py:285-286；口径依据 = §3.10 L461 ValueError 钉死 + W4 闭合实现 + G6-1 e2e 须可跑，ERR-P6-10）；
- `unauthorized_context`：同 alice_context 但 global_entity_views=None；
- `template_store`：v2_project_llm 装载（TemplateStore 正常态）；
- `deployment` / `deployment_alt`：两 fixture 文件 load 结果；
- `high_policy` / `alt_policy`：build_llm_policy 产物（FakeInferenceBackend 注入）；
- `scripted_backend`：(logical_role, base_revision, seq) 脚本工厂（平铺函数 `make_script(script)`）。
- Session 级机械验证面（D-P6-21，**不占 §6.1 平铺计数**）：`p6_diagnostic_code_audit`（session scope fixture，惰性执行）= ① 构造期拒绝：`RuntimeDiagnostic(code="LLMSIM_UNKNOWN_CODE", severity=..., path="p6", message="audit")` 抛错（code ∉ 21 码闭集）；② `P6_RUNTIME_DIAGNOSTIC_CODES` ∩ P5 `DIAGNOSTIC_CODES`（schemas.py:112-133，18 码）= ∅。W1-W4 测试文件（test_profiles/test_deployment/test_router/test_adapter/test_structured）自足，**不得依赖**本节 conftest fixture（上述 fixture 仅 W5-W6 测试文件消费）。

**预期诊断/exit 码面**：诊断断言 = (code, path, refs, severity) 四元组精确断言（P5 先例口径）；smoke exit 3/0/4 三态 = gate ⑥ 进程内断言（非 subprocess）。

### 6.3 对抗清单（AD-1~AD-9，= §6.1 末行 1:1）

| AD# | 探针 | 预期 |
|---|---|---|
| AD-1 | 假凭据值注入 env → 全 e2e → 序列化扫描 | 值缺席；9 键精确 |
| AD-2 | 构造 valid_until == current 边界 + base 落后 1 | 前者不 stale（commit），后者 REJECT |
| AD-3 | override 模板声明 global_entity_views（未授权 context） | 渲染 "null"；越权数据缺席 |
| AD-4 | src+test 27 文件域 12 名 AST 扫描（边界文件自身除外）+ fixture 面；部署文件故意含 12 名词 | src/test/fixture 0 命中；部署文件（用户域）不入扫描域（断言扫描器不碰该路径） |
| AD-5 | 模板 ref = `../../etc/passwd` 形态 + 真 symlink 指向项目外 | PATH_ESCAPE；零越界读 |
| AD-6 | 脚本全坏 JSON | 调用次数==2；parse_retry==1；decide → None；PARSE_FAILED 诊断 |
| AD-7 | deployment 无该 capability | NO_DEPLOYMENT；build → policy None；零静默模型 |
| AD-8 | 全链（含 AD-6 坏 JSON 运行）双跑 | 逐字节相等 |
| AD-9 | min_tier=3，部署全 tier=2 | TIER_MISMATCH；policy None；显式失败文本可断言 |

### 6.4 fixture 规格（逐文件钉死形状，D-P6-14 执行面）

| 文件 | 钉死形状 |
|---|---|
| `tests/fixtures/v2_project_llm/game.yaml` | 顶层键 = `manifest` + `scenario` + `player` + `capabilities`（game.yaml 8 键封闭集之 4 键，project_ir.py L74-83 `_GAME_SECTIONS`；必选 3 节 = manifest/scenario/player，project_ir.py L89 `_REQUIRED_GAME_SECTIONS`）：manifest: {schema_version: `'2'`, project_id: `p6_llm_e2e`, name: `P6 E2E Fixture`}；scenario: {id: `scenario_main`, max_ticks: 20, ticks_per_game_minute: 1, game_time: {hour: 12, minute: 0}}；player: {player_id: `player_1`, name: `Tester`}（player **不声明** sensor capabilities）；capabilities: [{id: `cap_major_character`, capability: `major_character`, min_tier: 2, ideal_tier: 3}]（顶层键恰为 capabilities）。**name 值须避开 12 名裸 token**：P5 validator `check_deployment_leakage` 对项目文件全文做 casefold 词边界扫描，如 name 写成 'P6 LLM E2E' 会命中 `llm` 词边界触发 LLMSIM_DEPLOYMENT_FIELD；钉死值 `P6 E2E Fixture` 已核 clean；`project_id p6_llm_e2e` 安全（下划线 = 词字符，llm 两侧为词字符不成词边界） |
| `tests/fixtures/v2_project_llm/characters/alice.yaml` | characters: [{id: `alice`, name: `Alice`}]（顶层键恰为 `characters`，project_ir.py L95-104 `_SECTION_FILES`）单角色（无其他实体/角色） |
| `tests/fixtures/v2_project_llm/prompts/game_policy.yaml` | prompts: [{id: `gp_main`, scope: `game_policy`, template_ref: `prompts/game_policy.md`, variables: []}]（顶层键恰为 `prompts`，LAYOUT_OPTIONAL） |
| `tests/fixtures/v2_project_llm/prompts/character_alice.yaml` | prompts: [{id: `cs_alice`, scope: `character_scene`, template_ref: `prompts/character_alice.md`, variables: []}]（顶层键恰为 `prompts`，LAYOUT_OPTIONAL） |
| `prompts/game_policy.md` / `prompts/character_alice.md` | 非空纯文本；**零 `{{` token**（variables=[] ⇒ 无替换点，render 零诊断） |
| `tests/fixtures/v2_deployment/deployment.yaml` | models: `model_high`（tier 3）/ `model_alt`（tier 2）；inference_profiles.major_character → `model_high`（resolved_via=`primary`） |
| `tests/fixtures/v2_deployment/deployment_alt.yaml` | models: `model_alt`（tier 2）；inference_profiles.major_character → `model_alt`（alt tier 2 ≥ min 2，S5 换模型 e2e 仍可跑） |

钉死 = 机械面：S1 装载后 IR 字段与上表逐一相等（test_profiles/test_deployment + e2e 首段断言）；两部署文件 = 唯一模型面差异（G6-2）；项目侧 fixture sha256 在 S5 前后不变（#5 断言）。顶层键遵循 P5 冻结 loader（project_ir.py L89 `_REQUIRED_GAME_SECTIONS` + L95-104 `_SECTION_FILES` + L74-83 game.yaml 8 键封闭集）；R2-3 实测修正后形状 → P5 validator 零诊断、IR.capabilities/IR.prompts 与表逐一相等。

---

## §7 映射表

### 7.1 G6 → 实现 → 决策 → 断言 → 测试

| G6 条款（Plan:661-666 逐字缩写） | 实现落点 | 决策 | 断言 | 测试 |
|---|---|---|---|---|
| 假模型可完整跑 | FakeInferenceBackend + PolicyWakeupHook 管线 + fixture | D-P6-14 | #1-4 | test_p6_gate_scenario S3/S4 |
| DeploymentProfile 改实际模型不改游戏 | DeploymentProfile 双文件 + resolve_capability | D-P6-05/07 | #5-6 | test_p6_gate_scenario S5 |
| Prompt override 不提升 context capability | CONTEXT_VARIABLES 13 名封闭 + 未授权 "null" | D-P6-12 | #7-9 | test_p6_gate_scenario S6 |
| stale ActionProposal 不直接 commit | valid_until + 委托 revalidation 管线 | D-P6-19 + §3.7 | #10-11 | test_p6_gate_scenario S7 |
| trace 不记录 credential | api_key_env 名字化 + 9 键封闭 + 探针 | D-P6-04/20 | #12-13 | test_p6_gate_scenario S8 |
| LLM parser 不依赖特定 provider 语义 | extract_json_robust 三族 + InferenceBackend Protocol + 12 名扫描 | D-P6-08/09/13 | #14-16 | test_p6_gate_scenario + test_structured |

### 7.2 Spec 章节 → P6 落点

| Spec 章节 | 引注 | P6 落点 | 状态 |
|---|---|---|---|
| §4 Kernel 强制不变量 | Spec:242-339 | §2 P6-INV-1..8 机械映像 + §8.1 K1-K8 落地矩阵（K5→#20、K6→#1/#12/#19、K7→#17、K8→#16/#18） | 实现（机械映像） |
| §5.4 DeploymentProfile | Spec:403-420 | deployment.py 两节形状 + capability 约定 | 形状扩展（DEV-5），语义承载 |
| §5.5 游戏可声明的 Inference Capability | Spec:422-450 | router BELOW_IDEAL warning 语义 | MAY 级承载（细粒度项 → tier 抽象，D-P6-02） |
| §6 ProjectIR | Spec:454-457 | ProjectIR.capabilities/.prompts 只读消费（router/registry 输入，§1.3/S1） | 实现 |
| §9 提案再验证（释义；Spec 原标题「Revision Model」） | Spec:642-678 | staleness.py 委托面 + make_action_proposal base/valid_until 字段 | 消费既有管线（零重复实现） |
| §11.3 提案语义 | Spec:770-785 | make_action_proposal 字段映射表（§3.5） | 实现 |
| §11.4 唤醒面 | Spec:787-802 | PolicyWakeupHook 先例消费（conftest.py:719-748） | 消费 |
| §12.2 BehaviorPolicy | Spec:814-838 | LLMPolicy.decide 同步面（`async def decide` L820 = DEV-3，继承 P4 裁决） | 同步（DEV-3） |
| §13 Context/Capability | Spec:872-909 | §3.10 CONTEXT_VARIABLES 13 名授权供给面 + 13.3 override 不提升权限（Spec:907-909 逐字，D-P6-12） | 实现 |
| §14 提示词层 | Spec:913-935 | L0-L4 组装 + override L1/L2 + L4 data 语义 | 实现（MAY replace assembler 面保留） |
| §31 LLM 运行时 | Spec:1631-1674 | adapter/policy/trace 全量（async 签名 L1638 = DEV-2；router 面 L1647-1656 = §3.3；record 字段 L1658-1672 = 9 键；Credential MUST NOT L1674 = D-P6-04；诊断码 21 封闭集 = 记录/trace 纪律延伸面（D-P6-18/21，Spec 侧依据 = §31.1 record 封闭面）） | 实现（DEV-2） |
| §39 Security/Trust Model | Spec:1905-1940 | 12 名扫描 + 白名单 37 + 用户部署域隔离（K8 安全面，D-P6-13/18/21） | 实现 |
| §42 零网络纪律（释义；Spec 原标题「测试层级」） | Spec:1989-2053 | 双例外纪律（httpx/time 仅 adapter.py）+ NO LLM/NO GUI 面 | 文档化例外（§3 导入纪律） |

### 7.3 Plan 任务 → 文件 → 波次

| 任务（Plan:626-637） | 文件 | 波次 |
|---|---|---|
| T01 现状调查（GFlash） | 本档 §7.4（调查面 = 设计文档，零代码） | W0 |
| T02 能力档案（QMax） | llm/profiles.py | W1 |
| T03 部署匹配（QMax） | llm/deployment.py + llm/router.py | W1/W2 |
| T04 推理适配（QMax） | llm/adapter.py + llm/structured.py | W3/W4 |
| T05 提示词组装（QMax） | prompts/registry.py + prompts/assembler.py | W4 |
| T06 策略门面（Q27） | llm/policy.py | W5 |
| T07 stale/time 语义（QMax） | llm/staleness.py | W5 |
| T08 critic（QMax） | llm/critic.py | W6 |
| T09 fake e2e（Q27） | fixtures 8 文件 + FakeInferenceBackend + gate 测试 | W6 |
| T10 smoke（Q27） | scripts/llm_smoke.py | W6 |

### 7.4 v1 语义 → v2 落点（调查 14 行）

| # | v1 源（file:line） | v1 语义 | v2 落点 | 处置 |
|---|---|---|---|---|
| 1 | src/models/config.py:9-15 | LLMConfigModel：provider="deepseek" / model="deepseek-chat" / api_key_env / base_url / temperature 0.7 | DeploymentEntry（api_key_env 名字化、零默认 pin） | 替换（v1 provider/model 默认值 = pin 反模式，G6-2 违例面，禁用） |
| 2 | config/simulation.yaml:7-13 | llm 段随游戏配置 | tests/fixtures/v2_deployment/*.yaml（用户侧） | 替换（部署 = 用户面，K8 项目面隔离） |
| 3 | src/llm/parser.py:19 | JSON_BLOCK_RE fence 提取 | extract_json_robust 族 1 | 等价迁移（中立化） |
| 4 | src/llm/parser.py:91-104 | _extract_json fence/首{末} 回退 | extract_json_robust 族 1-3 | 等价迁移 |
| 5 | src/llm/parser.py:44-52 | json_instruction（DeepSeek 特定注记 :3-6） | L0_CONTRACT_TEMPLATE 中性契约 | 替换（G6-6） |
| 6 | src/llm/parser.py:31-88 | async generate_structured + ChatOpenAI + max_retries=2 + 反馈重试 | InferenceBackend.generate 同步 + PARSE_RETRY_MAX=1 + repair_instruction | 替换（D-P6-06/09；retry 2→1 预算钉死） |
| 7 | src/llm/parser.py:79-84 | 重试反馈文本 | repair_instruction 确定性模板 | 等价迁移（中立化） |
| 8 | src/llm/parser.py:12-13 | langchain ChatOpenAI import | 拆除（零 provider SDK，Leader-A4） | 丢弃（ADR-002 L24-28） |
| 9 | src/agents/init.py:61-62 | langchain message 构造（ChatOpenAI import 面 :7-8） | assembler L0-L4 + WireMessage | 替换 |
| 10 | src/prompts/loader.py:4 | jinja2 渲染 | render_template {{var}} 封闭变量（无 jinja2） | 替换（D-P6-11；venv 白外面） |
| 11 | src/prompts/loader.py:6-35 | PHYSICS/ATTRIBUTE 默认规则常量 | 明确丢弃（P7 动态叙事面，非 P6 范围） | 丢弃（§1.4 范围外 10 项） |
| 12 | src/prompts/loader.py:95-105 | PromptLoader 无纪律读取 | TemplateStore + 路径纪律三码 | 替换（D-P6-11） |
| 13 | src/graph/game_graph.py:9,28 + 调用点 :158/214/337/478/642/747/810 | LangGraph 节点直接调 LLM（7 点） | 拆除；语义经 wakeup → run_policy_decide → submit_proposal → revalidation 管线承载 | 丢弃（ADR-002；无 revision 面 = v1 缺陷，v2 = Spec §9 面） |
| 14 | src/graph/game_graph.py:123-371 输出消费 + src/models/config.py:19-20 memory_size/concurrent（AgentCharacterConfig 冻结面） | 节点内 LLM 输出消费 / 角色记忆并发配置 | PolicyWakeupHook 面（conftest.py:719 先例）+ P4 context/memory + P7 移交 | 拆分（P6 承载门面，余归 P7） |

**移交注记**：v1 condition_eval/tick_eval DSL 面 = P5 已交付（66 用例 parity），P6 零触碰；v1 世界状态直改（无 revision）= v2 全树 revision 链取代（revision.py 冻结面）。

### 7.5 移交与分歧注记

1. **P7 移交**：L4 untrusted 内容源（本相空段预留）、调用期跨模型 fallback（OI-P6-3）、多角色并发 LLM 预算（v1 concurrent 面）、动态叙事层内容（v1 PHYSICS/ATTRIBUTE 规则丢弃面的承接者）。
2. **P8 移交**：trace artifact 落盘（sink.store_artifact 的宿主实现）、source_record_id 回填（provenance 链闭合）。
3. **分歧登记**：DEV-1..7 全量见 §8.4（Spec §5.5/§31.1/§12.2 双面对/§5.4 示例面 vs P6 冻结裁决 + 占位 docstring 措辞冲突 + R1 诊断载体裁定 DEV-7）。
4. **baseline 注记**：`<P6-BASELINE-SHA>` 由 Leader 在 gate ③ 前填实；填实前 gate ③ 不可复跑（占位符状态 = 本档交付态）。
5. **plugins 移交澄清**：plugins.api EntryPointSpec 执行 = P5 SOT L483「P6+」口径；P6 任务表（Plan:626-637）不含该项，执行归后续相（P9 modules 面），P6 零触碰 plugins/。G5 门禁报告 §9 L192 移交注记「（执行归 P6）」为短写：本档从 P5 SOT L483「P6+」口径并经 Plan:626-637 任务表裁定为 P9 面，G5 短写与本档裁定的差异由此闭合。

---

## §8 自检

### 8.1 K1-K8 不变式 → P6 落地矩阵 + 诊断码全表

| 不变式（Spec:242-339） | P6 落地 | 机械面 |
|---|---|---|
| K1（单一 authoritative state） | game 侧 P5 冻结 / model 侧 profiles.py 分离；router 单向消费 | #5/#19 三同域；content diff 空 |
| K2（禁止直接状态写入） | deployment.py 双文件 + 指针优先级；项目零 credential | #5（项目 sha256 不变）；#12 |
| K3（Authority 与 Commit 分离） | proposal_id sha256 推导 + base_world_revision 必填 + revision 链消费 | #3/#17；§3.5 表 |
| K4（Prompt 不能定义世界权限） | CONTEXT_VARIABLES 13 名封闭 + 未授权 "null" | #7-9；test_assembler 用例 1 |
| K5（Agent 是 Policy 不是 Engine） | LLMPolicy 严格面 + run_policy_decide 门面 | #20 五件套；TestP6Boundary 方法 6 |
| K6（Event 必须可追踪来源） | 9 键 llm_call + 5 键 prompt_assembly + 确定性句柄 | #1/#19/#12；test_policy 记录序 |
| K7（关键调度状态可检查） | clock seam + 零可变全局 + JSON 清洗 + 诊断排序 | #17/AD-8；FixedMonotonicClock |
| K8（Deployment 与 Game Project 分离） | 12 名扫描 + 白名单 37 + 部署用户域隔离 | #16/#18；TestP6Boundary 方法 2/5 |

**诊断码封闭集（21 码，D-P6-18；与 P5 18 码零重叠 = 机械断言 set-disjoint；载体 = P6 本地 `RuntimeDiagnostic` + `P6_RUNTIME_DIAGNOSTIC_CODES`（§3.11，D-P6-21））**：

| 族 | 码 | severity | 触发 |
|---|---|---|---|
| RESOLVER | LLMSIM_RESOLVER_DEPLOYMENT_MISSING | error | 文件缺失 / 指针 None |
| RESOLVER | LLMSIM_RESOLVER_DEPLOYMENT_PARSE | error | YAML 错 / 根非 dict / pydantic 违例 |
| RESOLVER | LLMSIM_RESOLVER_NO_DEPLOYMENT | error | capability ∉ inference_profiles |
| RESOLVER | LLMSIM_RESOLVER_MODEL_UNDECLARED | error | entry.model/fallbacks ∉ models 键 |
| RESOLVER | LLMSIM_RESOLVER_TIER_MISMATCH | error | 无 candidate 满足 min_tier |
| RESOLVER | LLMSIM_RESOLVER_BELOW_IDEAL | warning | 胜出 tier < ideal_tier |
| INFERENCE | LLMSIM_INFERENCE_ENDPOINT_MISSING | error | 调用期 base_url 空 |
| INFERENCE | LLMSIM_INFERENCE_CREDENTIAL_MISSING | error | api_key_env 非 None 且 env 缺失 |
| INFERENCE | LLMSIM_INFERENCE_TRANSPORT | error | 网络异常/超时 |
| INFERENCE | LLMSIM_INFERENCE_HTTP | error | 非 2xx |
| INFERENCE | LLMSIM_INFERENCE_MALFORMED_RESPONSE | error | 响应无 choices[0].message.content |
| INFERENCE | LLMSIM_INFERENCE_PARSE_FAILED | error | parse（含 critic）终败 |
| INFERENCE | LLMSIM_INFERENCE_PARSE_RECOVERED | warning | 首次失败、重试成功 |
| PROMPT | LLMSIM_PROMPT_TEMPLATE_MISSING | error | 模板文件缺失 |
| PROMPT | LLMSIM_PROMPT_PATH_ESCAPE | error | 绝对/`..`/symlink 逃逸 |
| PROMPT | LLMSIM_PROMPT_DUPLICATE_POLICY | error | policy id 重复（casefold） |
| PROMPT | LLMSIM_PROMPT_SCOPE_UNKNOWN | warning | scope ∉ {game_policy, character_scene} |
| PROMPT | LLMSIM_PROMPT_TEMPLATE_EMPTY | warning | 模板空文件 |
| PROMPT | LLMSIM_PROMPT_UNDECLARED_VARIABLE | error | 模板 token ∉ policy.variables |
| PROMPT | LLMSIM_PROMPT_VARIABLE_MISSING | error | 声明变量无值 |
| PROMPT | LLMSIM_PROMPT_VARIABLE_UNSUPPORTED | error | 声明变量 ∉ CONTEXT_VARIABLES |

计数：6 + 7 + 8 = **21** ✓（每码触发 + 不触发用例 = §6.1 矩阵）

### 8.2 导出账本（11 模块 70 名，与 §3 逐模块表精确一致）

| 模块 | 导出（按 __all__ 序） | 计数 |
|---|---|---|
| llm/profiles.py | REASONING_CLASSES, REASONING_ORDER, TierLevel, TIER_SCALE, tier_level, ModelCapabilityProfile, CAPABILITY_ID_PATTERN, CAPABILITY_RE | 8 |
| llm/deployment.py | DeploymentEntry, DeploymentProfile, DeploymentLoadResult, DEPLOYMENT_ENV_POINTER, resolve_deployment_path, load_deployment, load_deployment_auto, resolve_api_key | 8 |
| llm/router.py | ResolvedModel, RouterResult, resolve_capability, candidates_for, meets_tier, resolved_via | 6 |
| llm/adapter.py | MonotonicClock, SystemMonotonicClock, FixedMonotonicClock, WireMessage, InferenceRequest, InferenceResponse, InferenceBackend, HttpxInferenceBackend, FakeInferenceBackend, InferenceConfigError, InferenceTransportError | 11 |
| llm/structured.py | ParseResult, PARSE_RETRY_MAX, extract_json_robust, parse_llm_response, repair_instruction, make_action_proposal | 6 |
| llm/policy.py | LLMPolicy, BuildResult, build_llm_policy, TraceSink | 4 |
| llm/staleness.py | COMMITTABLE_OUTCOMES, effective_valid_until, handle_result, is_acceptable | 4 |
| llm/critic.py | CriticResult, CRITIC_DEFAULT_ENABLED, critique, critique_instruction | 4 |
| prompts/diagnostic.py | RuntimeDiagnostic, P6_RUNTIME_DIAGNOSTIC_CODES | 2 |
| prompts/registry.py | TemplateDocument, TemplateStore, RenderResult, render_template, validate_template_ref | 5 |
| prompts/assembler.py | PromptLayer, LayerSegment, PromptAssembly, PromptPackage, UntrustedContent, TokenEstimator, CharDivisorTokenEstimator, CONTEXT_VARIABLES, L0_CONTRACT_TEMPLATE, LLMActionProposal, context_variable_value, assemble_prompt | 12 |
| **合计** | | **70** |

### 8.3 计数交叉核对方程

1. **导出总数**：8 + 8 + 6 + 11 + 6 + 4 + 4 + 4 + 2 + 5 + 12 = **70** = §8.2 合计 = §3 总览表逐行求和 ✓
2. **白名单文件**：src 新建 11（llm 8 + prompts 3，含 `prompts/diagnostic.py` #3）+ pyproject 修改 1（#24）+ 测试新建 15（含 2 个测试侧 `__init__.py` + conftest）+ fixture 新建 8（#28-35）+ smoke 1（#36）+ 边界测试修改 1（#37）= **37** = §3.13 表行数（波次排序 #1-37，F-05 gate ③ 恰 37 行）✓
   （测试 15 分解：llm/ 12 项（#4/5/7/9/10/14/20/21/22/25/26/27：`__init__` + conftest + 10 测试文件）+ prompts/ 3 项（#15-17：`__init__` + test_registry + test_assembler）= 15 ✓）
3. **gate 断言**：G6-1(4) + G6-2(2) + G6-3(3) + G6-4(2) + G6-5(2) + G6-6(3) + 不变式(4) = **20** = §5.2 行数 = test_p6_gate_scenario 函数数 ✓
4. **测试函数**：10+12+12+12+12+10+8+8+13+12+20+9 = **138** = §6.1 合计 ✓（测试文件核算：llm/ 10 个测试文件（8 单元 + gate + adversarial）+ prompts/ 2 个 = 12 个平铺测试文件；12 + conftest 1 + `__init__.py` 2 = 15 = 方程 2 的测试段 ✓；D-P6-21 conftest session 级 `p6_diagnostic_code_audit` 不占平铺计数，§6.2）
5. **诊断码**：6 + 7 + 8 = **21** = §8.1 表行数；21 ∩ 18(P5) = ∅（待 gate 断言）✓
6. **决策**：Leader-A 号 12 个（Leader-A1~Leader-A12）映射决策 13 项（A1→01, A2→02, A3→06, A4→08, A5→04, A6→09+10, A7→14, A8→15, A9→16, A10→17, A11→18, A12→11——A6 拆 09/10 两项）+ 开放项自裁 7 项（03/05/07/12/13/19/20）+ R1 新裁 2 项（D-P6-21/22 = F-01/F-02）= 13 + 7 + 2 = **22** ✓
7. **波次覆盖**：W1(5) + W2(2) + W3(3) + W4(7) + W5(5) + W6(15：critic 1 + pyproject 1 + 测试 3 + fixture 8 + smoke 1 + 边界 1) = src 11 + pyproject 1 + 测试新建 15 + 边界修改 1 + fixture 8 + smoke 1 = 37 ✓（eq.7）

### 8.4 偏差登记（DEV-1 … DEV-7）

| # | 偏差 | SOT 面 | P6 裁决 | 理由/影响 |
|---|---|---|---|---|
| DEV-1 | Spec §5.5 细粒度能力 yaml（context length/multimodal 等显式字段）vs P5 冻结 game 侧字段封闭 | Spec:426-448 | tier 尺度抽象承载；game 侧零新面（D-P6-02） | P5 冻结 + G5 已裁决不可逆；MAY 级语义保全（ideal warning） |
| DEV-2 | Spec §31.1 `async def generate_structured`（L1638）vs 全树零 asyncio | Spec:1638 | 同步 Protocol（D-P6-06） | B-CON-1 + §42.1 + scheduler 纪律段；async 语义重读 = TTL（D-P6-06） |
| DEV-3 | Spec §12.2 双面对 P4/P6 同步面 | 面 1：Spec:820 `async def decide` vs B-CON-1 冻结同步门面（P4 已裁，behavior_policy.py:54-67）；面 2：Spec §12.2 协议返回非可选 `ActionProposal` vs 冻结 `ActionProposal | None`（B-CON-3「无决策」语义，behavior_policy.py:54-67） | 面 1：继承 P4 裁决，同步 decide（零复议）；面 2：继承冻结 core 语义（`None` = 无决策），P6 零改动 | P4 SOT 已裁决（B-CON-1/B-CON-3）；面 2 实质被冻结 core 语义覆盖，不影响实现（R1 补登完整度，P6R1-2-05） |
| DEV-4 | skeleton `llm/__init__.py:4-5` 占位「本包是唯一允许触达 OpenAI / provider SDK 的位置」vs Leader-A4 零 SDK | 占位 docstring（非 SOT 裁决件） | 占位文件零修改，披露于 gate 报告；措辞更新归 Leader | A1 零修改 + A4 零 SDK 的措辞冲突；代码面零影响（__init__ 无 import 面） |
| DEV-5 | Spec §5.4 单节示例 vs P6 两节部署形状 | Spec:409-418 | 两节（D-P6-05） | Spec 示例 = MAY 级非冻结字段表；两节 = 模型目录复用自由度 |
| DEV-6 | Spec §5.5 示例值 vs P6 tier 数值 | Spec:426-448 | tier 0-4 数值 = P6 新裁（D-P6-03）；multimodal 声明面 only | 无 SOT 冻结数值；单调性机械可验 |
| DEV-7 | 原档「跨包只读复用 P5 `Diagnostic`/`DiagnosticSeverity`」措辞 vs 21 码无声明落点 | 原档 D-P6-18 选择段（R1 前） | P6 本地 `RuntimeDiagnostic` + `P6_RUNTIME_DIAGNOSTIC_CODES`（§3.11，D-P6-21，F-01 裁定）；severity 仍跨包只读复用 P5 `DiagnosticSeverity`（schemas.py:102-107），P5 18 码闭集与 P5 validator 零触碰 | 两条实现路径分别与已钉要求互斥（扩 P5 18 码集破 P5 冻结/G5 闭包；无本地封闭集则 21 码无落点、构造期校验无 P6 侧接线面）；本地同构载体为唯一兼容解（R1 新裁，非复议） |

---

## §9 勘误

ERR-P6-1（W1 开发前文档面修正 + 实现边界注）：(a) §6.1 `test_deployment` 行原面列 11 项合计 13 函数却标「→ 12」（行内自相矛盾，§8.3 方程 4 钉死 12）；W1 实现裁定：`resolve_api_key` 命中/缺失断言并入 `test_load_deployment_auto_three_states`（env 语境最近），诊断确定性序保持独立函数 → 函数数恰 12，与表头/方程 4 一致；该行原位修正（原「resolve_api_key 命中/缺失 1」独立项删除）。(b) pydantic 2.13.4 实测：模型级 `model_validator(mode="after")` 违例的 error `loc` = 空元组；`load_deployment` 的 `LLMSIM_RESOLVER_DEPLOYMENT_PARSE` refs 点分串对空 loc 记哨兵 `<root>`（本档未规定该边界，字段级违例 loc 正常点分不受影响）；接受，不复议。

ERR-P6-2（W1 R1 盲审轮处置）：R1 轮 4 审查员 = SUPPLEMENT / PASS / SUPPLEMENT / PASS，findings 13（2 SUPPLEMENT 同根 + 3 DOC + 8 INFO）。处置：F-26 采纳（L125 DAG 枚举补 `deployment → prompts/diagnostic`（RuntimeDiagnostic 发射面，§3.2 L205）；「llm 包对 prompts 的 import 只发生在 structured 与 policy」句改「发生在 structured、policy 与 deployment」；诊断模块枚举补 deployment〔发射面〕并注明「deployment = 构造期发射面，其余仅类型级」——裁定：审查员原评 SUPPLEMENT 实为纯文档枚举遗漏（代码面与 §3.2 L205 规范行一致、零代码 diff），按 DOC 面处置）；F-27 驳回（审查员称 P5 18 码闭集引用「content/schemas.py:112-133」偏移 1 行，字节实证：赋值 L112、码串 L114-131、右括号 L133，本档引用「112-133」精确，审查员误计 L110-111 注释行——字节真 > 审查员，不改）；F-28/F-29 采纳（两测试文件 7 处注释/docstring 将「brief 注」与开发侧内部审计编号 A-W1-x/R3 改引 SOT 登记面 §9 ERR-P6-1(a)/§6.1 L808/L809 或去除，零行为 diff）。INFO 8 项记录不处置（frozenset 行序非钉死面 / TIER_SCALE 单调断言 = SOT L148 自身钉死 / 双 validator 合并行为同构 / fallbacks 元素约束注解显式化 / DeploymentLoadResult 刻意无 forbid = SOT L205 逐字 / `<root>` 哨兵测试断言 = 覆盖建议非必备 / tier_level bool 入参边界 SOT 未钉 / 内部审计编号：两测试文件 7 处已随 F-29 清除，src deployment.py docstring 残留 5 处经 R2 轮 F-34 清除（见 ERR-P6-3））。套件 2691 绿、ruff 净、K8 串面 0 命中复验通过。

ERR-P6-3（W1 R2 盲审轮处置）：R2 轮 4 审查员 = PASS / PASS / PASS / SUPPLEMENT，findings 13（去重后 6 个独立文档面 + 重复引用 + 1 INFO 披露；SUPPLEMENT 原评经字节实证裁定为纯 SOT 自面口径矛盾、零代码 diff，按 DOC 面处置）。处置：F-30 采纳（L125 DAG 行两处「§3.2 L204」→「§3.2 L205」：RuntimeDiagnostic 规范行 = L205（DeploymentLoadResult.diagnostics 行），L204 = DEV-5 形状注；ERR-P6-2 内同面两处同步修正）；F-31 采纳（关键口径更正，§3.12 方法 2 注 L519：按 SOT L17 钉死与 `test_import_boundary.py:225-240` / `content/validator.py:88-103` 两处冻结常量，langchain ∈ K8 12 名（12 名 = openai/anthropic/langchain/litellm/ollama/gemini/gpt/claude/llm/provider/api_key/base_url）；原文「实测 40 处命中（K8 12 名口径；langchain 等非 12 名名单词未计入，若计入则 42）」系 Leader 设计期 F-21 误将 11 名累加（40）标为 12 名口径——原始数字 40/2/42 曾实测在案但标签钉错集合；更正为「实测 42 处命中（K8 12 名口径，langchain ∈ 12 名（SOT L17）；langchain 2 处 = `PROVIDER_ROOTS` 与 `P4_LLM_PROVIDER_BLACKLIST` 各 1；剔 langchain 的 11 名辅助口径 = 40）」；W1 五文件两口径均 0 命中、结果不受影响；W6 方法 2 机械面按 L17 12 名集合执行（「拼接集 == P4_LLM_PROVIDER_BLACKLIST 断言」验证的正是该集合）；**后续全部 brief 的 12 名枚举一律含 langchain**）；F-32 采纳（§3.11 L493「首个消费者 = router（T03，LLMSIM_RESOLVER_* 发射面）」与 W1 字节真矛盾：deployment（W1，T03 前）为构造期首个消费者/发射者，改「首个消费者 = deployment（T03 前，W1 构造期发射面）；首个 resolver 消费者 = router（T03 后）」）；F-33 采纳（ERR-P6-2 自引修正：「§6.1 L808」→「L808/L809」两行、「SOT L147」→「SOT L148」空行订正）；F-34 采纳（deployment.py docstring 5 处 A-W1-x 审计号改引 SOT §3.2 L207（语义错不中断规范行）/L211（诊断序行），零行为 diff）；W1-R2-4-4 不处置（deployment.py L195 = 110 字符超 ruff line-length=100 设定，ruff 默认规则集不含 E501 → gate ② 判 clean；house 容差先例 = 冻结面 core/scheduler.py 自身 2 行 >100；披露项）。套件 2691 绿、ruff 净、K8 串面（12 名含 langchain 口径）0 命中复验通过。

ERR-P6-4（W1 R3 终验轮处置 + 波次闭合）：R3 轮 4 审查员 = PASS / PASS / PASS / PASS（4/4 通过、0 SUPPLEMENT、0 BLOCK、0 执行失败）→ **W1（白名单 #1-5）满足闭合条件**（代码面 + SOT 自面 + 冻结面三域全符合，R4 独立结论「可闭合」）。findings 6（2 DOC 微修 + 4 INFO 披露）。处置：F-35 采纳（§3.11 L509 模块纪律行诊断发射/消费模块枚举缺 deployment，与 F-26 修正后 L125 DAG 行不一致——发射名单头部补 `deployment`，零代码 diff）；F-36 采纳（§9 ERR-P6-2 自交叉引用「F-35」笔误 →「F-34」，与 ERR-P6-3 编号对齐）。INFO 4 项记录不处置：W1-R3-1-1（L125 DAG 未枚举 deployment → content.schemas（DiagnosticSeverity）边——L123 导入纪律允许、枚举粒度不对称提示项，可归后续波次文档面）；W1-R3-1-2 + W1-R3-4 隔离跑披露（tests/engine_v2/llm/ 无 __init__.py（白名单 #9 归 W3）→ 裸 pytest 控制台脚本单跑 collection 失败，全树与 `python -m pytest` 双模式均绿；gate ①-④ 运行命令 S0 已钉 `python -m pytest`，W3 #9 落地后单跑面自动消除）；W1-R3-4 勘误引文面披露（ERR-P6-3 勘误体例引 F-21 原文致 literal-grep 40/42 差值 = 引文面非规范面残留）。独立重算坐实面：边界文件 12 名口径 = 42 / 11 名辅助 = 40 / langchain = 2（L101 PROVIDER_ROOTS + L229 P4_LLM_PROVIDER_BLACKLIST 各 1）；W1 五文件 0 命中（两口径）；套件 2691/0、ruff 三路径净、__all__ 8/8/2 逐序、21 码 ∩ 18 码 = ∅。W1 三波次记录：R1（2 SUPPLEMENT 同根 + 3 DOC + 8 INFO → F-26..F-29，F-27 字节驳回）→ R2（13 findings = 1 SUPPLEMENT + 8 DOC + 4 INFO → F-30..F-34，含 F-31 关键口径更正）→ R3（4/4 PASS 闭合）。

ERR-P6-5（W2 R1 盲审轮处置 + 闭合）：W2（`router.py` 233 行〔F-41 后终态〕+ `test_router.py` 323 行，白名单 #6-7）R1 轮 4 审查员 = 4/4 PASS，findings 11（去重后 7 个独立主题 + 4 重复引用；5 DOC + 6 INFO，无 BLOCK/SUPPLEMENT）。处置：F-37 采纳（ResolvedModel docstring 取值分组把 model_id 归 models 目录侧，SOT §3.3 L224 字段源表归 entry 侧；两侧值恒等——deployment.py 构造期不变量强制 models 键 == 内层 model_id——docstring 对齐 SOT 表，零行为 diff）；F-38 采纳（模块 docstring 引 Spec §31.2 漏原文「/provider」非逐字；按 K8 docstring 零 12 名规则改旁转措辞「与供应商侧」；SOT L215 同引文面属文档层、不属扫描域）；F-39 采纳（测试文件 3 处开发侧内部审计编号「A-W2-6」非 SOT 登记面〔SOT 全文 grep 0 命中〕；W1 闭合先例 ERR-P6-2 F-29 / ERR-P6-3 F-34 已清同型 A-W1-x，W2 复发——改引 SOT #18 登记锚点 §3.3 L225，零行为 diff）；F-40 采纳（模块 docstring 覆盖项 12「profiles」可误读为 models 节，改 SOT §3.2 定名 inference_profiles，零行为 diff）。F-41（Leader 闭合自纠，F-37 引入的回归）：F-37 替换文案漏列 entry 侧 temperature/timeout_seconds（SOT L228 行钉死面），恢复 13 字段枚举，零行为 diff。INFO 6 项记录不处置：(a) test 5 诊断探针在 primary 干净胜出路径遍历空诊断集（无值字段半侧仍有效）；(b) test 12 末行断言结构冗余（步骤 2 早退已保证恰 1 条 NO_DEPLOYMENT）；(c) TIER_MISMATCH refs 的 tried 列表不含未声明 model 名（SOT L241 未钉死该边界，实现与 L240 skip 语义一致，test L296-301 已断言钉口径；W6 AD-9 探针构造时对齐口径参照）；(d) model_id 双源取值恒等（随 F-37 吸收）。dev 报告唯一偏离（content.schemas import 面含 DiagnosticSeverity 单名）经 Leader 按 SOT L123（D-P6-13 导入纪律）复核裁定合规：允许名明列 DiagnosticSeverity / InferenceCapabilityProfile / PromptPolicy，W1 冻结先例 deployment.py L28 同法，brief 表述欠钉、SOT 胜 brief。闭合状态：套件 2703/0（基线 2691 + 12）；隔离 llm 34；ruff 三路径净；`__all__` 6 名钉死序；12 平铺测试 1:1 §6.1 L810；K8 12 名（含 langchain）AST 串面 0 命中（Leader 独立复扫双口径 12/11 = 0/0）；W1 五文件零 diff。

ERR-P6-6（W3 B3 边界冲突处置 + 闭合）：W3（`adapter.py` 379 行 + `tests/engine_v2/llm/__init__.py` + `test_adapter.py` 320 行，白名单 #8-10）首跑全套件 2714/1：唯一失败 = `TestB3OfflineRunnable::test_t06`（P0/P3 边界方法，扫 tests/engine_v2/ 树 §0.3 黑名单 import），违规面 = `test_adapter.py` 的 `httpx` import（「网络/进程 IO」类）。成因：SOT §5.1 S0 L751（零真实网络，全部 InferenceBackend = FakeInferenceBackend 或 httpx.MockTransport 进程内面）+ §6.1 L811（「成功（MockTransport）1」/「transport 异常 1」）钉死 W3 测试 httpx 进程内面；`test_import_boundary.py` 为 Leader 所有跨相位演进集成文件，本档 §3.12 将其 P6 hunk 排程 W6「TestP6Boundary 6 方法纯追加块」——不含 B3 方法（§3.12 未明列 B3 例外项，dev 报告指出）。处置：Leader 于 W3 提前落地 B3 P6 例外（同方法 P5 例外先例 ERR-P5-16 体例的受控偏离：仅豁免该文件「网络/进程 IO」类命中（httpx），provider / v1 类对该文件仍零容忍；方法体注释明注「第二处受控偏离」）；本档 §3.12 W6 hunk 规格不变（保持纯追加块；B3 例外已于 W3 落地、以本勘误为登记面）。W3 dev 零 import 改写绕行（改写 = 重新设计，铁律禁止）。实现面登记（非偏离）：InferenceTransportError 三属性 code/status/refs——SOT 异常规格行只列 code/status，generate 步骤 6/7 显式引用 refs（步骤面 = 更细规格面 → refs 补默认空元组，Leader 预判 A-W3-1）；不可解析 JSON / 非 dict 响应落步骤 8 MALFORMED_RESPONSE 面（SOT 未钉该分支）。闭合状态：套件 2715/0（基线 2703 + 12）；隔离 llm 46；bare pytest 单跑 46（白名单 #9 `__init__.py` 效果 = 单跑收集修复实证）；ruff 三路径净；`__all__` 11 名钉死序；12 平铺测试 1:1 §6.1 L811；K8 12 名（含 langchain）AST 串面 0 命中（Leader 独立复扫 3 文件）；time 消费点唯一 = SystemMonotonicClock.now_ms（L68）；W1/W2 七文件零 diff。

ERR-P6-7（W3 R1 盲审轮处置 + 闭合）：W3 R1 轮 4 审查员 = 4/4 PASS（工作流传输面 R1 返回值丢失，盘上报告完整在位——Leader 按盘上 JSON 验收，传输失败不重发），findings 15（4 DOC + 11 INFO，无 BLOCK/SUPPLEMENT）。处置：F-42a..f 采纳（adapter.py 4 处 + test_adapter.py 2 处开发侧内部审计编号 A-W3-3/4/8/11/12 引用非 SOT 登记面——W1 F-29（ERR-P6-2）/ W2 F-39（ERR-P6-5）同型第三次复发，改引 SOT 锚点：A-W3-3 → §3.4 L256；A-W3-4 → §3.4 L258-270；A-W3-8 → §3.4 L285；A-W3-11 → L17/L123 K8 口径；A-W3-12 → §3.4 L254 Protocol 面；adapter.py L364 的 A-W3-1 已登记（ERR-P6-6）保留——零行为 diff；src 侧 A-W3-x 残留三次复发根因 = 各波 dev brief 的 Leader 预判编号被 dev 直引，后续波次 brief 明令「预判编号不入交付文案，一律引 SOT 锚点」）；F-43 采纳（Leader 自面：ERR-P6-5 头行『router.py 232 行』= F-41 前计数，字节实测终态 233 行，改 233 行〔F-41 后终态〕）。INFO 11 项（去重 7 主题）记录不处置：(a) 端点 rstrip('/') 尾斜杠分支无用例（§6.1 L811 未钉，R1 F-2 ≡ R2 F1b）；(b) 成功路径响应 JSON 非空 'model' 回报分支无用例（mock payload 刻意缺省，R1 F-3 ≡ R2 F1a ≡ R4 F-W3-4-2）；(c) usage wire 键名 prompt_tokens/completion_tokens = 实现约定（SOT 全文 0 命中该两键，与 L277 默认 wire 约定自洽；W4/W6 消费面需知悉此映射，R1 F-4 ≡ R2 F4 ≡ R3 F-3）；(d) test 9 refs 成员断言与 test 7/8 精确元组断言严格度不对称（R2 F2）；(e) test 5 credential 缺失只断言正面（变量名 in message），负面探针在 test 10（R2 F3）；(f) latency_ms = 注入时钟两次调用差（Fixed 面 = 恰 step_ms，SOT L272「注入时钟差」语义内，R3 F-4）；(g) _usage_int 排除 bool（int 子类，SOT 未钉，docstring 自披露，R4 F-W3-4-3）。闭合状态：套件 2715/0；隔离 llm 46；bare pytest 单跑 46；ruff 三路径净；`__all__` 11 名钉死序；12 平铺测试 1:1 §6.1 L811；K8 12 名（含 langchain）AST 串面 0 命中（Leader 独立复扫 3 文件双口径）；A-W3 残留 = 恰 1（A-W3-1 已登记面）。

ERR-P6-8（W4 开发前文档面修正）：§6.1 `test_structured` 行原面列 10 项合计 13 函数却标「→ 12」（行内自相矛盾，与 ERR-P6-1(a) 同型；§8.3 计数方程钉死该文件 = 12，138 总方程依赖之）。W4 实现裁定：「valid_until 透传 1」独立项并入「make_action_proposal 全字段映射」（valid_until 即映射字段之一，全字段映射测试自然携带其透传断言，语境最近）→ 函数数恰 12，与表头/§8.3 方程一致；该行原位修正（ERR-P6-1(a) 先例同款处置）。纯文档面，零代码 diff，不占补充预算。

ERR-P6-9（W4 R1 盲审轮处置）：R1 轮 4 审查员 = 4 × PASS，findings 17（8 DOC + 9 INFO，0 BLOCK / 0 SUPPLEMENT；R1 63 / R2 90 / R3 83 / R4 83 实核样本，计数全自算自洽：导出 6/5/12、测试 12/13/12、套件 2752、K8 双口径 0）。去重后独立根 4，全部纯文档面（零代码 diff），Leader 直接修正（F-44..F-47）：F-44 = test_structured.py docstring「SOT §3.11」→「SOT §3.5」误引（L1；R1-2/R3-2/R4-1 三审查员同根）+ 同文件「family 1」→「族 3」误标（L7 覆盖列表 + L101 函数 docstring，族 3 = 首尾杂文，R1-3）；F-45 = test_registry.py docstring「§6.1 L815」→「L816」行号偏移 1（L1/L3 两处；L815 = test_critic 行，R3-1/R4-2）；F-46 = 本档 L334 §3.5 模块纪律行 stdlib 枚举「json + hashlib」vs 实现实际「hashlib + re」（json 未用——JSON 解析由 pydantic model_validate_json 承接，re 承担 fence 提取；re/json 均在 D-P6-13 白名单 L123 内，代码合规，修 SOT 文本，R1-1/R3-3/R4-3）；F-47 = 本档 L447 §3.9 读面枚举窄于实际 import 面（补 `re` + pydantic + `prompts/diagnostic`（W1），R2-4）。INFO 9 项记录不处置：R2-1 TEMPLATE_EMPTY「空」= strip 后空（dev 登记自裁，SOT 未钉）；R2-2 目录 → TEMPLATE_MISSING（行为超集，防 IsADirectoryError）；R2-3 诊断 path 自裁 ×3（DUPLICATE_POLICY = 首占位 id / SCOPE_UNKNOWN = policy.id / TEMPLATE_EMPTY = template_ref）；R3-4 assemble_prompt L3 全供给对真实 ActorDecisionContext 非 JSON 原生字段（self_view EntityView / visible_entities frozenset / local_entity_views / observations / knowledge）抛 ValueError = SOT L461 钉死语义（house 族），W4 测试刻意 JSON-clean context——**s2 风险**：W5 policy 接线 / W6 gate 场景 fixture 必须维持 JSON-clean（make_p4_world 先例 §6.2 L826）或 SOT 增设序列化适配面；R3-5 UNSUPPORTED 变量 → 该层停渲染空段（SOT 未钉渲染面，两可：error → package None）；R3-6 DUPLICATE_POLICY path 自裁（模块 docstring 已明示）；R4-3 = F-46 根；R1-4 探针发现冻结 ids 直接构造下 ActionTypeId(None) 静默 coerce 为字面串 'None'（非 loud failure）——**s2 风险**：no-op wire 的 None 拦截唯一防线 = W5 policy 层（structured 无 guard 为 SOT L320 钉死设计）。另 R3 登记：assembler 同 scope casefold 并列分支（min by casefold）当前为死代码（registry 先以 DUPLICATE_POLICY 拒绝 casefold 重复 id）。闭合状态：套件 2752/0；隔离 llm 58；隔离 prompts 25；bare pytest llm 58 / prompts 25；ruff 三路径净；`__all__` 6/5/12 钉死序；测试计数 12/13/12 = §6.1 行面 1:1；K8 12 名（含 langchain）AST 串面 0 命中（Leader 独立复扫 7 文件双口径，修正后复扫仍 0）。

ERR-P6-10（W5 开发前文档面修正 + 实现边界裁定）：(a) §6.2 `alice_context` 行原面「P4 冻结面构造（make_p4_world 先例 conftest.py:472 口径移植）」——实证（W4 闭合实现 + 真实 EntityView dataclass context 探针）：self_view（frozen dataclass）/ visible_entities（frozenset）/ granted_capabilities（frozenset）经 §3.10 L461 `context_variable_value` → ValueError（JSON 原生封闭集），真实 context 无法进入 assemble/decide 的 L3 全供给路径（G6-1 假模型 e2e 必须可完整跑）。裁定：`alice_context` / `unauthorized_context` fixture = P4 口径的 **JSON-clean twin**（同 actor/capability 面：ent_alice + ent_bob + candidate_actions 含 "attack" + granted_capabilities 面；字段值 = JSON 原生代用类型：self_view = EntityView 形状 dict 镜像、visible_entities / granted_capabilities = tuple、local_entity_views = dict、observations = tuple、knowledge = None；`ActorDecisionContext` = plain @dataclass(frozen=True)（context_provider.py:285-286）无运行时校验，代用类型运行时可达）——行面原位澄清（ERR-P6-8 先例同款），零代码 diff。(b) §3 DAG 行（L125）policy 依赖枚举缺边 + 措辞遗漏（汇总面，ERR-P6-2 F-26 同类）：`policy → staleness`（模块级 import，§3.6 步骤 9 `effective_valid_until`）与 `policy → critic`（`decide()` 步骤 7 函数级懒 import——critic.py 落 W6，模块级 import 将破坏 W5 可导入性；懒 import 仅 `enable_critic=True` 时执行）与 `policy → deployment`（模块级，`build_llm_policy` 参数注解面）；另 DAG 原「adapter（TYPE_CHECKING 仅 Protocol 面）」与 §3.6 步骤 2 字节矛盾（`decide()` 运行时构造 `WireMessage` / `InferenceRequest` 具体类——adapter 实为模块级 import）——DAG 行原位补正。(c) `parse_retry` 键口径裁定：= 本次 decide 发生过修复重试（parse-retry 或 critic-repair）则为 1、否则 0（`{0,1}` 饱和域 = 表面钉死；SOT 全部字面字节——步骤 6「parse_retry=1」、步骤 7「parse_retry=1」、AD-6「parse_retry==1」、no-op「实际次数」——在该口径下自洽；3 调用最坏路径（parse-retry + critic-repair 均发生）饱和为 1，域不破）。(d) W5 实现边界：test_policy critic 行（§6.1 行 5-7）经 `monkeypatch.setitem(sys.modules, "src.engine_v2.llm.critic", stub)` 打桩（stub = 确定性 `critique` / `critique_instruction`，W5 覆盖面 = policy 接线，真 critic 归 W6 test_critic）；conftest 全量落 §6.2 fixture 面，其中 `template_store` / `deployment` / `deployment_alt` / `high_policy` / `alt_policy` 依赖 W6 fixture 目录（#28-35），仅 W6 测试消费（pytest fixture 惰性解析，W5 不消费 = W5 绿）。(a)(b) 纯文档面；(c)(d) 实现边界裁定。均不占补充预算。

ERR-P6-11（W5 R1 盲审轮处置 + 闭合）：W5（policy.py 414 行 + staleness.py 84 行 + conftest.py 266 行 + test_policy.py 530 行 + test_staleness.py 148 行，白名单 #18-22）R1 轮 4 审查员 = 4/4 PASS（工作流传输面 R2/R3/R4 裁决截断、盘上报告完整在位——Leader 按盘上 JSON 验收，传输失败不重发，ERR-P6-6 先例同型），findings 17（1 DOC + 16 INFO，BLOCK/SUPPLEMENT 0，执行失败 0）。处置：F-48 采纳（R1-1 DOC：L125 DAG 汇总行诊断子句括号注「（deployment = 构造期发射面，其余仅类型级）」与 §3.6 步骤 1/5/6/7 字节冲突——§3.6 钉死 policy 运行时 record_diagnostic（步骤 1 透传组装期 PROMPT_* 诊断、步骤 5 构造 PARSE_RECOVERED、步骤 6/7 构造 PARSE_FAILED），policy.py L166/L214-215/L228-229/L254-255 实测 3 处运行时 RuntimeDiagnostic 构造 = decide 运行时发射面，非仅类型级；实现按 §3.6 落位合规（详细规格 > 汇总行措辞），本条为汇总面措辞残留，同族 = ERR-P6-2 F-26 / ERR-P6-10(b)（补正 DAG 缺边时未及此括号注）→ L125 原位修正为「（deployment = 构造期发射面，policy = decide 运行时发射面（透传组装诊断 + 构造 PARSE_* 族，§3.6 步骤 1/5/6/7），其余仅类型级）」）。F-49 采纳（R3-3 + R4-3 INFO 升格 W6 消费面裁定：§6.4 L856-857 表钉 template_ref 裸名 `game_policy.md`/`character_alice.md` 与 .md 落 `v2_project_llm/prompts/` 之下不可同时满足冻结 registry `validate_template_ref`（registry.py L94-112：绝对/`..` → path-escape；`(project_root/template_ref).resolve()` ∉ `project_root/prompts/` → path-escape）——裸 ref 解析落 project_root 根层 = LLMSIM_PROMPT_PATH_ESCAPE（error，记诊断并跳过该文档）⇒ W6 S1「2 文档加载零诊断」+ G6-1 e2e 组装链不可达，W6 硬阻塞 → L856-857 原位修正为 `prompts/game_policy.md`/`prompts/character_alice.md`；W6 fixture #29-31 yaml 内 template_ref 值须按本修正口径，白名单 #32/#33 .md 文件路径不变（本已在 prompts/ 下））。余 15 INFO 全自披露/自裁登记面（policy.py：_PROMPT_ASSEMBLY_KEYS 本地常量、first_error 防御式默认、prompt 摘要 layer_count 键、两处键集 assert 守卫（-O 可剥离，test_policy + W6 TestP6Boundary 独立强制）、__get_pydantic_core_schema__ 房规模式（先例 core/ids.py L96、core/revision.py L58）、docstring「httpx 面异常」= §3.6 L359 逐字转述；staleness.py handle_result proposal 参数 = §3.7 L396 钉死签名宿主对称日志透传面（只读 decision）；conftest：_MemSink 模块级内联类 vs「闭包类」措辞粒度、_entity_view_mirror 硬编码值、global_entity_views type: ignore、template_store docstring 前缀对齐自披露、_build_policy 独立 _MemSink、_e2e_script 全 20 键预置、template_store id 定序装载自裁）——无 SOT 字节冲突、无动作，记录在案。全部修正纯文档面（零代码 diff，不占补充预算）。闭合状态：套件 2770/0（基线 2752 + 18）；隔离 llm 76 / prompts 25；bare pytest 76/25；ruff 净；policy/staleness __all__ 4/4 钉死序；test_policy 10 / test_staleness 8；K8 12 名（含 langchain）双口径 0/0（Leader 独立复扫）；critic 函数级懒 import（AST 链 Module > ClassDef > FunctionDef > If > ImportFrom @ policy.py L241）；W5 测试零消费 W6 目录 fixture（AST 参数面核验 + 目录缺席实测）。s2 风险传递 W6：(1) W6 fixture 目录内容须匹配 W5 conftest fixture 体期望（template_store 装载 v2_project_llm/prompts/*.yaml 经 yaml.safe_load 顶层 prompts 键构造 PromptPolicy；deployment/alt 装载 v2_deployment yaml；high_policy 脚本键 ("major_character", Revision(r), 1) r∈[0,20)——"major_character" = §6.4 game.yaml capability 名，部署 fixture 须声明同 capability）；(2) template_ref 前缀对齐裁定 = 本勘误 F-49 修正口径（prompts/ 前缀必须，validate_template_ref realpath 前缀纪律）；(3) 真 critic.py 落 W6（W5 sys.modules-stub 测试保持有效接线覆盖，真逻辑 test_critic）；(4) 全部 decide/assemble 路径（含 G6-1 e2e、AD-6/AD-8）必须 JSON-clean twin context（ERR-P6-10(a)）；(5) W6 TestP6Boundary 方法 2 扫 27 .py（含 W5 五文件，实测 0/0），风险仅在 W6 新文件引入 12 名字符串字面量。

ERR-P6-12（W6 Leader hunk 实现面文档面修正）：W6 Leader hunk #37（TestP6Boundary 6 方法纯追加块）实现时，方法 5 按 §3.12 L522 字面（「`time` 与 `httpx` import 仅 llm/adapter.py；动态加载面（importlib/__import__）= 0」+ L519「边界文件仍保留在方法 3/4/5/6 import 面域」）首跑 2 处命中冻结面，均 = 汇总行措辞 vs 详细规格/冻结字节冲突（F-48/ERR-P6-11 同型：详细规格 > 汇总行、冻结 > 文档）：(a) `tests/engine_v2/llm/test_adapter.py`（W3 冻结，白名单 #10）直接 import httpx = §6 L802「httpx.MockTransport = 进程内假传输，披露项」+ §6.1 L811「成功（MockTransport）1」+ B3 受控偏离（test_import_boundary.py B3 方法 P6 例外块，ERR-P6-6 已登记）钉死的唯一文档化测试侧 httpx import 面——方法 5 字面「仅 llm/adapter.py」与冻结字节不可同真；(b) 边界文件自身 P4 冻结骨架（L41 import importlib、L403/405 importlib.import_module 可导入性探针 harness）按 L519 在方法 5 import 面域内，与「importlib = 0」字面自相矛盾（P4 内容不可修改——Leader hunk 纯追加铁律）。处置：§3.12 L522 原位修正（httpx 例外 = adapter + test_adapter.py MockTransport 面，标注 B3 受控偏离 ERR-P6-6；importlib/__import__ 检查边界文件 harness 自豁免，同方法 2 排除同型）；Leader hunk 方法 5 实现按修正口径落地（httpx 允许集 = {llm/adapter.py, tests/engine_v2/llm/test_adapter.py}；importlib/__import__ 扫描域 = 28 文件面 − 边界文件自身；random/datetime、socket/urllib/requests/http.client 检查口径不变且边界文件自身仍受扫）。纯文档面（零代码 diff，不占补充预算）。
