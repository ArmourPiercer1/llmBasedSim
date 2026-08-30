# P5 Project Format / Module / Plugin / DSL 设计 — Phase 5 项目格式 / 模块清单 / 插件注册 / 规则 DSL 实现规范（Spec B）

- **任务**: P5-DESIGN（Phase 5 — Project Format / Module / Plugin / DSL 架构设计，Plan §14；先例：P2-DESIGN / P3-DESIGN / P4-DESIGN）
- **文档地位**: 等价于 Plan §14「Phase 5 — Project Format / Module / Plugin / DSL」（Plan:586-616）的字段级 / 函数级实现规范。任务归属 P5-T01~T10 按 Plan §14 任务表（Plan:594-605）：T01/T07 → GFlash、T02 → QMax、T03~T06/T08/T09/T10 → Q27（默认模型列在无人工路由覆写时生效，见路由声明）。Q27/GFlash 按本文档可"纯执行"实现 T01~T10 全部任务，无需再做架构判断。全部决策编号钉死为 **D-P5-01~D-P5-17**（§4）；全部行号引用已对冻结源逐行核验（全部 SOT 文档 @ HEAD `e5c4db4`；v1 冻结文件锚定其预 P5 提交，§1.3），引用格式 `file:line`；Gate 断言共 **20 条**（§5.2，G5-1~G5-6 = 4+3+2+3+2+4 + 不变量 2 条 #19/#20）；模块数 **10**、导出名总数 **116**（10 个模块 `__all__` 并集，§8.2 台账逐名核验）；诊断码 **18** 枚（§3.1 DIAGNOSTIC_CODES）；DSL 封闭节点种类 **23**（§3.5 DSL_NODE_KINDS）。
- **路由声明**: 2026-08-20 人工路由覆写（全任务 → qiyuan-self/qwen3.8-27b，P4 文档:3）为覆盖整个 v2 执行的常设指令，**适用于 P5 全部任务与执行波次**（ERR-P5-1 裁定 2，2026-08-30 确认）。Plan §14 默认模型列（Plan:594-605：T01/T07 → GFlash、T02 → QMax、T03-T06/T08-T10 → Q27）为无人工覆写时的后备值，本期不执行。
- **分支**: `architecture-v2`（HEAD `e5c4db4`，G4 门禁闭合 PASS，G4 报告:247-253；core 冻结基线 32 模块 / 308 导出名；全套 2399 passed、ruff clean）
- **权威输入**:
  - `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md`（下称 **Spec**）§3.1（L172-190）、§4 K1-K8（L242-339）、§5（L343-454，5.1 布局 L351-366）、§6（L454-486，12 类 L460-474 + 5 MUST L476-482）、§26（L1456-1496）、§28（L1516-1545）、§29（L1547-1568）、§40（L1944-1966）、§41（L1970-1987）、§44（L2100-2202，plugins/ L2136-2139、content/ L2179-2183）、§46（L2273-2314，MVP 18/19/20 L2294-2296、plugin sandbox 推迟 L2305）、§47（L2315-2469，Phase 5=Dynamics L2401-2415）
  - `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md`（下称 **Plan**）§14（L586-616，任务表 L594-605、G5 六条 L607-614）、§21（L888-909）、§22.3（L975-990）、§24（L1212-1371，S2 = L1230-1242）、§32（L1685-1707）
  - `docs/v2/contracts/P4-actor-context-space-mode-design.md`（下称 **P4**）— 体例先例（§3.11 锚点台账、§3.12 波次、§5.4 断言编号、§9 勘误格式、§10 未决问题）
  - `docs/v2/gates/G4-gate-report.md`（下称 **G4**）§5 偏差 D10-D22（L178-194）、§6 风险登记册（L198-214，P5 义务 = 第 2/3/4 条）、§7 移交 P5 的接口与约束（L239-243）、§8 PASS（L247-253）
  - `docs/v2/reports/P0-T03-characterization-report.md` — v1 行为基线（368 v1 用例 + 6 骨架 = 374；新增 77 characterization 用例；FakeLLM 设计；全离线）
- **冻结源（v1，只读，P5 零修改）**: `src/game/condition_eval.py` @ `f0a1052`（450 行）、`src/game/deterministic_rules.py` @ `f0a1052`（163 行）、`src/game/rules.py` @ `f0a1052`（225 行）、`src/game/state_apply.py` @ `f0a1052`（253 行）、`public_start/test_empty.yaml` @ `5b6837b`（154 行）、`public_start/whisperheads.yaml` / `public_start/murder.yaml` @ `5b6837b`、`config/simulation.yaml` @ `ac4b704`（23 行）、`src/config/loader.py`（46 行）、`src/agents/init.py`（378 行）、`tests/test_condition_eval.py`（367 行，41 用例）、`tests/test_rules.py`（408 行，25 用例）
- **写面（W1，本设计任务仅两个文件可写）**: 本文档 + `.review-drafts/p5-design-author.json`。实现波次写面 = §3.12 白名单 39 文件（封闭集）。

---

## §1 定位

### 1.1 五件 scope

P5 = 「项目格式 / 模块 / 插件 / DSL / 校验 CLI」五件，对应 Plan §14 任务表（Plan:594-605）T01~T10 与 Spec §46 MVP 18/19/20（Spec:2294-2296）：

| 件 | 内容 | 主要落点 | 任务 |
|---|---|---|---|
| 1. Project Format | v2 项目目录布局（Spec:351-366）+ 加载器 + ProjectIR（Spec:460-474 十二类全结构）+ round-trip | `content/{schemas,project_ir,loader}.py` | T02/T03/T08 |
| 2. Module | 模块清单（§28.3 requires/optional/conflicts/engine_version）+ 依赖图 + 拓扑/环/冲突/版本诊断 | `content/module_graph.py` | T04 |
| 3. Plugin | 本地显式 manifest（§28.1）+ entry-point 组（§28.2）+ 注册表 + 安全模型（G5-2/G5-3） | `plugins/{manifest,api,registry}.py` | T05/T06 |
| 4. DSL | v1 condition/rule DSL 语义等价封装为标准 Rule module（23 种封闭 AST + 内建规则库 + 注入式随机） | `content/rule_module.py` | T07 |
| 5. Validator CLI | `llmsim validate --json`，18 诊断码，确定性排序，退出码 0/1/2 | `content/{validator,cli}.py` + `pyproject.toml [project.scripts]` | T09/T10 |

### 1.2 G5 六条逐条回应（Plan:607-614 逐字）

| # | G5 条款（逐字） | 实现手段（本文档锚点） | 决策 | 断言 |
|---|---|---|---|---|
| G5-1 | 零 Python 项目可以 load + validate | `LAYOUT_OPTIONAL` 封闭路径模板（§3.3）：缺省可选目录/文件 = 合法空；无 `pyproject.toml` ∧ 无 `plugins/` = 合法完整项目；参照项目 fixture（§3.12 #30-34，内容镜像 `public_start/test_empty.yaml` 的 world/player/meta 结构）经 `load_project → build_ir → validate_project` 全链 0 error | D-P5-04/05/13 | #1-3、#16 |
| G5-2 | Python plugin 必须显式注册 | 恰好两条显式注册路径（§3.10 D-P5-07）：`plugins/<id>/plugin.yaml` 本地 manifest；`importlib.metadata` entry-point 组 `llmsim.plugins`。目录无 manifest = 不存在（静默忽略，不报错不加载）；`plugins/` 非空 ∧ 无 `pyproject.toml` → `LLMSIM_PLUGIN_NO_PYPROJECT` | D-P5-07/08 | #4-5、#8 |
| G5-3 | 不允许目录自动扫描执行任意 Python | 发现面 = 封闭路径模板（§3.3）+ 纯 metadata 读取（§3.10，validate 期零 import / 零执行）；**机械自证**：gate 测试对 `content/loader.py` + `plugins/registry.py` 源码做 AST 封闭模式扫描——禁止 `importlib.import_module` / `__import__` / `importlib.util.spec_from_file_location` / `importlib.util.module_from_spec` 调用模式（断言 #6）；rogue `.py` 探针（断言 #7） | D-P5-07/15 | #6-7 |
| G5-4 | module dependency cycle 可诊断 | Kahn 拓扑 + 环提取（§3.4 D-P5-06）：每 SCC 一条 `LLMSIM_MODULE_CYCLE`（refs = SCC 节点 casefold 排序列表）；环上零 exception（返回诊断，非异常）；`topological_order` 环图返回 `[]` | D-P5-06 | #9-10、#18 |
| G5-5 | DSL 继续支持已有简单规则，但没有引入 loop/function-definition 等"重新发明 Python"的能力 | v1 if-chain 语法原样（§3.5 D-P5-09，tokenizer 正则与条件/值/输出文法逐条对齐 `condition_eval.py`）；封闭 23 种 AST（`DSL_NODE_KINDS`）；函数白名单仅 `rand/randint/min/max/len`（`condition_eval.py:243-273`）；文法无 loop/def/赋值产生式（机械封闭）；66 例 characterization 等价集 1:1 转录（§6.2） | D-P5-09/10 | #11-12 |
| G5-6 | validator 返回 machine-readable diagnostics | `Diagnostic{code,severity,path,message,refs}`（§3.1）+ `--json` 纯 stdout JSON（§3.7 D-P5-12）+ 确定性排序 `(code,path,message)` + 退出码 0/1/2；18 诊断码封闭集 `DIAGNOSTIC_CODES` | D-P5-12 | #13-15、#17 |

### 1.3 输入基线

1. **G4 PASS**（G4:247-253）：G4-R1 最终轮 4/4 盲审通过；全套 **2399 passed / ruff clean** @ HEAD `e5c4db4`；core 冻结 32 模块 / `__all__` 308 名（`core/__init__.py:416-725`）。
2. **P4 移交（G4 §7，L239-243）四条，P5 逐条接受**：
   - §7-1 策略协议入口（D-P4-16）：`BehaviorPolicy.decide` / `ModePolicy.resolve` 两协议 + `ActorDecisionContext` 13 字段 = 既有缝，**P5 不改缝**（P5 白名单不触 core/P4 模块，机械满足）。
   - §7-2 确定性纪律延续：P4 六模块 AST 黑名单面（M1④ 12 名 casefold 词边界扫描，`test_import_boundary.py:474-478` 模式）对 P5 新模块同样适用，import 边界常量块模式 `P5_SUBMODULES`（§3.11）——**本文档已落实为 TestP5Boundary**。
   - §7-3 fingerprint 义务（G3 移交 2，G4:202-203）：`scheduler_fingerprint` 四 callable 配置面扩展**或维持披露分支**——P5 裁定 = 维持披露分支（core 冻结，D-P5-01），移交登记见 §8.4 D-P5-DEV-4。
   - §7-4 LLM 策略内容（G4:204-205）：`BehaviorPolicy`/`ModePolicy` 内容层 = P5 阶段义务；P5-T01~T10 模块面零 provider/LLM 面（K8 机械保证，§3.11）。内容层排期归属见 §10 OI-P5-3（§8.4 D-P5-DEV-5）。
   - §7-5 认识论边界：P5 任何「prompt 换权限」式实现 = K4 违背（`PromptPolicy` 无 authority 字段，§3.1；回归防线 = #19b）。
3. **v1 行为基线（P0-T03）**：368 v1 用例全通过 + 6 骨架用例；77 characterization 用例（`tests/test_char_nodes.py` 60 + `tests/test_char_graph.py` 17）；FakeLLM 全离线。P5 的 DSL 等价性基线另取 `tests/test_condition_eval.py`（41 用例）+ `tests/test_rules.py`（25 用例，其中 5 个为 `TestTextMatchesRule` 类方法）共 **66 例**（§6.2，pytest `--collect-only` 权威计数已核验）。
4. **v1 项目文件基线**（P5 loader 的对照物，P5 只读不改）：
   - `public_start/test_empty.yaml`（154 行）：`world{name,description,environment{time_of_day,weather,temperature_c},locations[{id,name,description,connections{east,hallway,…},ambient_light,ambient_sound}],objects[{id,object_type,name,description,position{x,y,z},state,properties}]}`、`player{player_id,name,persona,position,capabilities{…skill_levels},physical_profile{height_cm,weight_kg,body_width_cm,movement_mode,strength},attributes{key:{name,value,min,max,natural_delta_per_minute,description}},subconscious_rules,subconscious_memory,speech_examples,inventory}`、`characters: []`（L135）、`starting_scene_description`、`max_ticks: 20`（L147）、`game_time`（L148-150）、`ticks_per_game_minute: 1`（L151）、`narrative_style`（L152-154）。
   - `public_start/whisperheads.yaml` / `murder.yaml`：同构 + `world_rules{physics{disable:[8],append},attribute{disable,append}}`；characters 带 `personality{traits,motivations,speech_style,background}`、`relationships{char_id:float}`、`starting_inventory`、`attributes`；whisperheads `max_ticks=60`、`ticks_per_game_minute=0.5`、`game_time{5,15}`。
   - `config/simulation.yaml`（23 行）：`simulation/llm{provider,model,api_key_env,base_url,temperature,max_tokens}/agents` —— **DeploymentProfile 前驱，K8 的动机**（Spec:330-339）：v2 项目文件永不出现该形态（§3.6 check_deployment_leakage）。
   - v1 加载入口（P5 不 import，仅语义对照）：`src/config/loader.py:42-46`（`yaml.safe_load` @ :45 + `model_validate` @ :46）、`src/agents/init.py:125-128`（`load_init_file`）、`src/agents/init.py:355-365`（`load_init_file_set`）。
5. **锚点文件基线**（P5 前已冻结，行号均 @ `e5c4db4`）：
   - `tests/engine_v2/core/test_closeout.py`（517 行）：L96-129 32 模块 tuple；L169 `shadowed == {"snapshot"}`；L181-225 算术注释块（`# = 308` @ L225）；L226 `len(core_pkg.__all__) == 308`。
   - `tests/engine_v2/core/test_import_boundary.py`（505 行）：L58-91 `CORE_SUBMODULES`；L98-151 PROVIDER/V1/NETWORK 根集；L192-199 `P4_SUBMODULES`；L209-220 `P4_TEST_FILES`；L225-240 `P4_LLM_PROVIDER_BLACKLIST`（12 名）；L246 `_collect_absolute_imports`；L263 `_blacklist_category`；L292 `_p3_strict_violation`；L316 `TestB1StaticScan`（:318-322 文件集断言 = CORE_SUBMODULES ∪ {__init__}）；L316 后 `TestB3OfflineRunnable`（递归扫 `tests/engine_v2/**`，**自动覆盖 P5 新测试目录，零修改**）；L443 `TestP4Boundary`；L474-478 12 名 casefold 词边界文本扫描模式。
   - `tests/test_engine_v2_skeleton.py`（207 行）：L27-41 `SUBPACKAGES`（13 子包，含 `plugins` L30 / `content` L36）；L110-136 `_is_core_reexport_node`（**core 专属** re-export 豁免）；L144 `test_engine_v2_init_files_are_docstring_only`（断言 13 子包 + 根包 `__init__.py` docstring-only，仅 core 豁免）。
   - `src/engine_v2/core/__init__.py`（727 行）：import 块 L51-415；`__all__ = [` L416 … `]` L725（308 名）。
   - `src/engine_v2/core/serialization.py`：`dump_json` L54、`load_json` L67、`assert_json_clean` L82。
   - `src/engine_v2/content/__init__.py`（8 行，docstring-only）、`src/engine_v2/plugins/__init__.py`（7 行，docstring-only）——P5 填充标记。
   - `src/engine_v2/README.md`（62 行）：L17 `plugins/` 行（Phase 5）、L23 `content/` 行（Phase 5）、L57 Phase 5 描述行。
   - `pyproject.toml`（32 行）：L1 `[project]`、L2 name="llm-based-sim"、L3 version="0.1.0"、L5 requires-python、L6-16 dependencies、L18 optional-deps、L26-28 ruff（line-length 100）、L30-32 pytest（asyncio_mode auto）。**无 `[project.scripts]`**（P5 新增，§3.11）。

### 1.4 不做什么（out of scope）

| 项 | 理由 | 去向 |
|---|---|---|
| `llmsim add`（Spec §29, L1547-1568） | 包管理器集成非 P5 任务表项 | 后续 CLI 阶段（MVP 20 CLI validate/inspect/run/test 的扩展面，Spec:2296） |
| `llmsim inspect/run/test` 子命令 | 同上 | 同上 |
| LLM 策略内容（Director 决策层内容） | G4 §7-4 内容层义务，非 T01-T10 任务面 | OI-P5-3（§10）+ D-P5-DEV-5（§8.4） |
| v1 attributes 子 DSL（`_LCParser` / `_ComputeParser`，`src/game/attributes.py:200/446`） | P7/P9 范围，P5 仅引用不实现 | P7 Dynamics / P9 内容模块 |
| 插件运行时执行 / 沙箱 | Spec:2305 明示 plugin sandbox 推迟；执行 = runtime（P6+） | P6+（`plugins/api.py` Protocol = 预留缝） |
| authority/action/mode/capability/prompt 的运行时语义 | P5 = 结构定义 + 静态检查（D-P5-03） | P6（action/authority 接线）、P8（prompt/表现） |
| v1→v2 迁移工具 | D-P5-04 无 v1 兼容；Spec §44 `content/migrations.py` 推荐文件推迟 | D-P5-DEV-1（§8.4） |
| `scheduler_fingerprint` 输入面扩展 | core 冻结（D-P5-01）；G4 已授权"维持披露分支" | D-P5-DEV-4（§8.4），移交下阶段触 core 者 |
| `modules/`（P9）、`dynamics/`（P7）、`devtools/`（P8）、`adapters/`（P8/10/11）子包 | 骨架占位属对应阶段（README.md:15-23 各行） | 对应阶段 |

---

## §2 不变量映射（K1-K8 → P5 机械映像）

K1-K8 全文见 Spec:242-339。P5 是**纯读/纯产新值**阶段（不持有 WorldInstance、不提交事务），K 不变量在 P5 的落点是**结构面 + 机械可验映像**：

| K | 不变量（Spec 行号） | P5 机械映像 | P5-INV | 机械核验手段 |
|---|---|---|---|---|
| K1 | 单一 authoritative state（Spec:244-249） | ProjectIR = 项目源在 validate 期的**唯一**结构化投影；loader 不缓存/不改写源文件；`canonical_yaml` 是 IR 的纯函数，不产生第二套真源 | P5-INV-1 | 同一 `RawProject` 两次 `build_ir` 深比较相等（单测）；loader 零写操作（白名单无源文件修改） |
| K2 | 禁止直接状态写入（Spec:251-275） | P5 对世界**只读**：全部输出 = 新值（IR / 诊断 / 字符串）；输入对象零原地变更（frozen pydantic 模型 + `raw.files` 只读语义） | P5-INV-2 | `build_ir`/`validate_project` 前后输入 deepcopy 相等（单测）；全部 P5 数据模型 `frozen=True` |
| K3 | Authority 与 Commit 分离（Spec:277-287） | `AuthorityPolicy` 在 P5 = 声明数据（domain/owner/exclusive）；P5 无任何写权限授予面（无 mutation API）；冲突检查 = 纯诊断 | P5-INV-3 | `check_authority_conflicts` 只产诊断不变更（单测）；P5 模块无 `set/append/mutate` 公共 API（台账人工核验） |
| K4 | Prompt 不能定义世界权限（Spec:289-299） | `PromptPolicy` 字段封闭集 = {id, scope, template_ref, variables}，**无** authority/permission 字段；`InferenceCapabilityProfile` 无 provider/model/endpoint/credential 字段 | P5-INV-4 | `test_schemas.py` 字段集内省断言（#19b）+ 12 名扫描（#19a） |
| K5 | Agent 是 Policy，不是 Engine（Spec:301-311） | ProjectIR 16 字段封闭（§3.1），无 LLM-agent loop / LangGraph 假设字段；能力需求仅以 `InferenceCapabilityProfile` 声明 | P5-INV-5 | ProjectIR 字段集内省（test_schemas.py）；P5 源码零 provider 根 import（TestP5Boundary） |
| K6 | Event 必须可追踪来源（Spec:313-324） | 诊断 = P5 的"事件"：每条 `Diagnostic` 必带非空 `path`（源定位）+ `code`（类型）+ `refs`（证据引用） | P5-INV-6 | 断言 #17：对损坏项目 fixture 产出的**全部**诊断逐条 shape 校验（code∈DIAGNOSTIC_CODES、severity∈{error,warning}、path 非空、message 非空） |
| K7 | 关键调度状态可检查/可序列化（Spec:326-328） | ProjectIR / ModuleGraph / Diagnostic 全 JSON-clean（无 datetime / 无随机态 / 无引用环）；IR = 可序列化快照 | P5-INV-7 | `ir_to_data` 尾部 `assert_json_clean`（serialization.py:82）机械钩子；双 dump 字节稳定（#20） |
| K8 | Deployment 与 Game Project 分离（Spec:330-339） | 项目文件禁含 provider/model name/endpoint/credential（Spec:332-335 四项）：机械面 = 12 名 casefold 词边界扫描（D-P5-11）；schema 面 = 能力画像/提示策略字段封闭（P5-INV-4 共用） | P5-INV-8 | 断言 #19：`api_key` 探针 → `LLMSIM_DEPLOYMENT_FIELD`；`model: x` **不**命中（12 名集无 model，词边界口径）；引擎自身 `pyproject.toml` 不在扫描面（引擎 ≠ 项目） |

**P5-INV 清单**：P5-INV-1 ~ P5-INV-8（上表右列）。全部在 §5.2 断言或 §6 单测中有机械落点；无"仅靠自觉"的不变量。

---

## §3 模块与字段级规格

总览（10 模块 / 116 导出）：

| 模块 | 文件 | 导出数 | 任务 | 波次 |
|---|---|---|---|---|
| 3.1 | `src/engine_v2/content/schemas.py` | 25 | T02 | W1 |
| 3.2 | `src/engine_v2/content/project_ir.py` | 6 | T02 | W2 |
| 3.3 | `src/engine_v2/content/loader.py` | 6 | T03 | W2 |
| 3.4 | `src/engine_v2/content/module_graph.py` | 11 | T04 | W3 |
| 3.5 | `src/engine_v2/content/rule_module.py` | 43 | T07 | W4 |
| 3.6 | `src/engine_v2/content/validator.py` | 8 | T09 | W6 |
| 3.7 | `src/engine_v2/content/cli.py` | 4 | T09 | W6 |
| 3.8 | `src/engine_v2/plugins/manifest.py` | 3 | T05 | W5 |
| 3.9 | `src/engine_v2/plugins/api.py` | 3 | T05 | W5 |
| 3.10 | `src/engine_v2/plugins/registry.py` | 7 | T05/T06 | W5 |

**导入纪律（全部 P5 模块，D-P5-15）**：允许 import = stdlib 白名单（`typing` `re` `enum` `pathlib` `json` `argparse` `logging` `sys` `importlib.metadata` `collections.abc`）+ `pydantic` + `yaml` + `src.engine_v2.core.serialization`（仅 `dump_json`/`load_json`/`assert_json_clean`）。禁止：`asyncio` `datetime` `time` `random` 网络族（`socket`/`http`/`urllib`/`requests` 等）、`src.*`（v1，含 `src.game.*`/`src.config.*`/`src.agents.*`）、`langgraph`/`openai`/`langchain*` 族、`importlib.import_module`/`__import__`/`importlib.util.spec_from_file_location`（G5-3 机械面，仅 `importlib.metadata` 允许）。`importlib.metadata` 的使用面被限制在 `plugins/registry.py` 内且**只读 metadata，零 import**（D-P5-08）。机械核验 = TestP5Boundary（§3.11/§6.4）。

模块间依赖（DAG，零环）：`schemas ← {project_ir, module_graph, rule_module, plugins.manifest, plugins.api} ← loader / plugins.registry ← validator ← cli`。`content/*` 之间禁止互导（`project_ir` 可导 `schemas`；`loader` 可导 `schemas`+`project_ir`（RawProject）；`validator` 可导 `schemas`+`project_ir`+`module_graph`+`rule_module`+`plugins.registry`）。

### 3.1 `content/schemas.py`（25 导出）

**定位**：ProjectIR 十二类（Spec:460-474）+ 诊断 schema + RawProject 的**纯数据**定义。Pydantic v2，全部 `model_config = ConfigDict(frozen=True)`（K2/P5-INV-2）；全部模型 `extra="forbid"`（D-P5-05 严格模式）；零逻辑（除 model_validator 形状校验）、零 I/O、零 core import。

`__all__`（25，按本表序）：
`DIAGNOSTIC_CODES`, `RawProject`, `ProjectManifest`, `ProjectIR`, `WorldSpec`, `EnvironmentSpec`, `LocationSpec`, `ObjectSpec`, `PositionSpec`, `AttributeSpec`, `PlayerSpec`, `CharacterSpec`, `ComponentSchema`, `ComponentField`, `ActionSpec`, `RuleSpec`, `AuthorityPolicy`, `ModuleGraphNode`, `GameplayModeSpec`, `InferenceCapabilityProfile`, `PromptPolicy`, `PluginDescriptor`, `ScenarioSpec`, `Diagnostic`, `DiagnosticSeverity`

**错误族**：模型构造期形状违例 = pydantic `ValidationError`（由 `project_ir.build_ir` 捕获转 `LLMSIM_SCHEMA`；本模块不直接产诊断，除 `Diagnostic` 自身 code 校验）。

**字段表**：

- **DiagnosticSeverity**（enum, str）：`ERROR="error"`, `WARNING="warning"`。
- **DIAGNOSTIC_CODES**（`Final[frozenset[str]]`，18 枚）：

| code | severity | 语义 |
|---|---|---|
| `LLMSIM_FILE_MISSING` | error | 必需文件缺失（`game.yaml`）或项目根不存在 |
| `LLMSIM_YAML_PARSE` | error | YAML 解析失败 / 根非 dict |
| `LLMSIM_PROJECT_FORMAT_V1` | error | 检出 v1 项目形状（无 `manifest.schema_version="2"`，D-P5-04） |
| `LLMSIM_SCHEMA` | error | 字段类型/约束违例（pydantic 路径转写） |
| `LLMSIM_UNKNOWN_KEY` | error | 未知字段（`extra="forbid"` 命中，D-P5-05） |
| `LLMSIM_DUPLICATE_ID` | error | ID 重复（池内，§3.6 check_duplicate_ids） |
| `LLMSIM_UNRESOLVED_REF` | error | 引用指向不存在的实体 |
| `LLMSIM_MODULE_REQUIRES_MISSING` | error | 模块 requires 目标未声明 |
| `LLMSIM_MODULE_VERSION` | error | 版本约束不满足 / 版本语法非法 |
| `LLMSIM_MODULE_CYCLE` | error | 模块依赖环（每 SCC 一条，D-P5-06） |
| `LLMSIM_MODULE_CONFLICT` | error | 模块 conflicts 声明命中 |
| `LLMSIM_AUTHORITY_CONFLICT` | error | 同 domain 双 exclusive 策略（D-P5-03） |
| `LLMSIM_DEPLOYMENT_FIELD` | error | 项目内容含 Deployment 12 名词边界命中（K8，D-P5-11） |
| `LLMSIM_DSL_PARSE` | error | 规则 DSL 解析失败（D-P5-09） |
| `LLMSIM_PLUGIN_ENTRY_INVALID` | error | 插件 entrypoint 声明非法（`module:Attribute` 文法） |
| `LLMSIM_PLUGIN_NO_PYPROJECT` | error | `plugins/` 非空 ∧ 无 `pyproject.toml`（D-P5-07） |
| `LLMSIM_ENGINE_VERSION` | error | `engine_version` 约束不满足（D-P5-08） |
| `LLMSIM_PLUGIN_ENTRY_UNRESOLVED` | warning | 声明的插件未在注册表（运行时或可由其他分布提供，D-P5-08） |

- **Diagnostic**（frozen）：

| 字段 | 类型 | 约束 |
|---|---|---|
| code | str | ∈ DIAGNOSTIC_CODES（model_validator） |
| severity | DiagnosticSeverity | — |
| path | str | 非空；文件相对路径（posix）或实体/规则 ID |
| message | str | 非空；**确定性文本**（无时间戳/无指针/无随机） |
| refs | tuple[str, ...] | 默认 `()`；证据引用（环节点序、重复 ID 对等），构造时定序 |

- **RawProject**（frozen）：

| 字段 | 类型 | 说明 |
|---|---|---|
| root | str | 项目根绝对路径（posix） |
| files | dict[str, Any] | key = 相对 posix 路径（如 `game.yaml`、`world/main_world.yaml`），value = YAML 解析结果（JSON-clean 可断言） |
| texts | dict[str, str] | 同 key 集的**原始文本**（K8 扫描面，D-P5-11；loader 保留原文，不丢信息） |
| pyproject_present | bool | 根下 `pyproject.toml` 存在性 |
| plugins_dir_present | bool | 根下 `plugins/` 目录存在性 |

- **ProjectManifest**（frozen）：

| 字段 | 类型 | 约束/默认 |
|---|---|---|
| schema_version | Literal["2"] | 必为 "2"（v1 拒绝的机械判据之一，D-P5-04） |
| project_id | str | pattern `^[a-z][a-z0-9_]{0,63}$` |
| name | str | 1..200 字符 |
| description | str | 默认 `""` |
| engine_version | str | 默认 `""`（= 任意）；文法 `""` \| `X.Y.Z` \| `>=X.Y.Z`（D-P5-06 版本文法） |

- **ProjectIR**（frozen，根聚合，**16 字段** ↔ 十二类映射见 §7.2）：

| 字段 | 类型 | 默认 | Spec 十二类归属（Spec:460-474） |
|---|---|---|---|
| manifest | ProjectManifest | 必需 | ① manifest |
| scenario | ScenarioSpec | 必需 | ⑫ scenario definitions（默认场景，来自 game.yaml） |
| world | WorldSpec | 必需 | ② entity definitions |
| player | PlayerSpec | 必需 | ② entity definitions |
| items | tuple[ObjectSpec, ...] | () | ② entity definitions |
| characters | tuple[CharacterSpec, ...] | () | ② entity definitions |
| component_schemas | tuple[ComponentSchema, ...] | () | ③ component schemas |
| actions | tuple[ActionSpec, ...] | () | ④ action registry（P5 结构；运行时 P6） |
| rules | tuple[RuleSpec, ...] | () | ⑤ rule registry |
| authority | tuple[AuthorityPolicy, ...] | () | ⑥ authority policies（P5 静态面；接线 P6） |
| modules | tuple[ModuleGraphNode, ...] | () | ⑦ module graph |
| gameplay_modes | tuple[GameplayModeSpec, ...] | () | ⑧ gameplay mode definitions（P5 结构） |
| capabilities | tuple[InferenceCapabilityProfile, ...] | () | ⑨ inference capability profiles |
| prompts | tuple[PromptPolicy, ...] | () | ⑩ prompt policies |
| plugin_descriptors | tuple[PluginDescriptor, ...] | () | ⑪ plugin descriptors |
| scenarios | tuple[ScenarioSpec, ...] | () | ⑫ scenario definitions（追加场景，scenarios/*.yaml） |

- **PositionSpec**（frozen）：`x: float`, `y: float`, `z: float = 0.0`。
- **EnvironmentSpec**（frozen）：`time_of_day: str = ""`, `weather: str = ""`, `temperature_c: float | None = None`（v1 形状对照 test_empty.yaml L9-13）。
- **LocationSpec**（frozen）：

| 字段 | 类型 | 约束/默认 |
|---|---|---|
| id | str | pattern `^[a-z][a-z0-9_]{0,63}$` |
| name | str | 非空 |
| description | str | `""` |
| connections | dict[str, str] | `{}`；key = 方向名（`east` 等，v1 test_empty.yaml L27-35 形状），value = 目标 location id（check_references 面） |
| ambient_light | str \| None | None |
| ambient_sound | str \| None | None |
| properties | dict[str, Any] | `{}`（**开放 dict**，JSON-clean 即可，D-P5-05） |

- **ObjectSpec**（frozen）：`id`（同上 pattern）, `object_type: str = ""`, `name: str`, `description: str = ""`, `position: PositionSpec | None = None`, `state: str | None = None`, `properties: dict[str, Any] = {}`（**开放 dict**）。
- **AttributeSpec**（frozen）：`name: str`, `value: float`, `min: float`, `max: float`（model_validator `min <= value <= max`）, `natural_delta_per_minute: float = 0.0`, `description: str = ""`（v1 attributes 形状对照 test_empty.yaml player.attributes）。
- **PlayerSpec**（frozen）：

| 字段 | 类型 | 约束/默认 |
|---|---|---|
| player_id | str | pattern 同上 |
| name | str | 非空 |
| persona | str | `""` |
| position | PositionSpec \| None | None |
| capabilities | dict[str, Any] | `{}`（**开放 dict**；规范键：`skill_levels` / `blocked_common_actions` / `allowed_extraordinary_actions`——v1 test_rules.py:14-18 形状） |
| physical_profile | dict[str, Any] | `{}`（**开放 dict**；规范键：`height_cm` / `weight_kg` / `body_width_cm` / `movement_mode` / `strength`——v1 形状） |
| attributes | dict[str, AttributeSpec] | `{}`；key = 属性键 |
| inventory | list[str] | `[]`；object id（含 items） |
| subconscious_rules | list[str] | `[]` |
| subconscious_memory | list[str] | `[]` |
| speech_examples | list[str] | `[]` |

- **CharacterSpec**（frozen）：`id`（pattern 同上）, `name: str`, `personality: dict[str, Any] = {}`（**开放 dict**；规范键 `traits`/`motivations`/`speech_style`/`background`——v1 whisperheads.yaml 形状）, `position: PositionSpec | None = None`, `starting_inventory: list[str] = []`, `relationships: dict[str, float] = {}`（key = character id 或 player_id，check_references 面）, `speech_examples: list[str] = []`, `attributes: dict[str, AttributeSpec] = {}`。
- **ComponentField**（frozen）：`name: str`, `type: ComponentType`（enum: `string`/`number`/`boolean`/`list`/`map`/`object`；私有 enum，不进 `__all__`）, `required: bool = False`, `default: Any | None = None`, `description: str = ""`。
- **ComponentSchema**（frozen）：`id: str`（如 `world.location`；pattern `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$`）, `fields: tuple[ComponentField, ...]`（非空、name 唯一）, `description: str = ""`。
- **ActionSpec**（frozen）：`id: str`, `name: str`, `verb: str = "interact"`, `requires_components: tuple[str, ...] = ()`（ComponentSchema id）, `condition: str | None = None`（DSL 字符串，D-P5-09；validate 期 parse_dsl 校验）, `success_probability: float | None = None`（0<p<1）, `description: str = ""`。
- **RuleSpec**（frozen）：

| 字段 | 类型 | 约束/默认 | 依据 |
|---|---|---|---|
| id | str | pattern 同上，全局唯一 | v1 DeterministicRule.id（deterministic_rules.py:13） |
| description | str | `""`（可空；v1 要求非空 → v2 放宽，§8.4 D-P5-DEV-3 附注） | deterministic_rules.py:86-90 |
| match | str \| None | None；正则，`re.IGNORECASE`（v1 deterministic_rules.py:130 口径） | v1 `match_action` |
| condition | str \| None | None；if-chain DSL 字符串 | v1 `condition`（:103-106 形状校验） |
| feasibility | Literal["allowed","blocked","uncertain"] \| None | None（缺省 + 无 condition 时 = "allowed"，v1 rules.py:117 口径） | v1 feasibility（:113-118） |
| probability | float \| None | None；`feasibility="uncertain"` 时**必需**且 0<p<1 | v1 deterministic_rules.py:160-161 |
| priority | int | 100；越小越先（同 priority 按 id.casefold 序，D-P5-06） | v2 新增（v1 自定义规则按列表序） |
| disabled | bool | False（替代 v1 数字索引 disable 1-5 的 ID 化，D-P5-10） | v1 disable（rules.py:146 等） |

- **AuthorityPolicy**（frozen）：`id: str`, `domain: str`（非空；如 `attributes.sanity`）, `owner: str`（模块/系统 ID）, `exclusive: bool = True`, `description: str = ""`。P5 = 结构 + 重叠静态检查（D-P5-03；运行时语义 P6）。
- **ModuleGraphNode**（frozen）：`id: str`（pattern 同上）, `version: str`（`\d+(\.\d+)*`）, `entrypoint: str | None = None`, `requires: tuple[str, ...] = ()`（`"id"` 或 `"id >= X.Y"`，Spec §41:1974-1978 形状）, `optional: tuple[str, ...] = ()`, `conflicts: tuple[str, ...] = ()`, `engine_version: str = ""`, `description: str = ""`（§28.3:1538-1543 四字段齐）。
- **GameplayModeSpec**（frozen）：`id: str`, `mode_type: str`, `params: dict[str, Any] = {}`, `description: str = ""`。
- **InferenceCapabilityProfile**（frozen）：`id: str`, `capability: str`（非空；能力需求名，如 `structured_output`）, `min_tier: int = 0`（≥0）, `ideal_tier: int = 0`（≥0，model_validator `ideal_tier >= min_tier`）, `notes: str = ""`。**字段封闭**：不得出现 provider/model/endpoint/credential 字段（K8，#19b 内省断言）。
- **PromptPolicy**（frozen）：`id: str`, `scope: str`, `template_ref: str`（`prompts/` 内相对路径）, `variables: tuple[str, ...] = ()`。**字段封闭**：无 authority/permission 类字段（K4，#19b）。
- **PluginDescriptor**（frozen）：`id: str`, `source: Literal["local","entrypoint"] = "local"`, `entrypoint: str | None = None`（`module:Attribute` 形式，Spec §28.1:1526 形状）, `description: str = ""`。
- **ScenarioSpec**（frozen）：

| 字段 | 类型 | 约束/默认 | v1 对照 |
|---|---|---|---|
| id | str | pattern 同上 | — |
| max_ticks | int | ≥1 | test_empty.yaml:147 `max_ticks: 20` |
| ticks_per_game_minute | float | >0 | :151 |
| game_time | ScenarioTime | 见下 | :148-150 `{hour, minute}` |
| starting_scene_description | str | `""` | test_empty.yaml 顶层 |
| narrative_style | str | `""` | :152-154 |

  （`ScenarioTime`（frozen，**私有**模型，不进 `__all__`）：`hour: int`（0..23）, `minute: int`（0..59）。）

### 3.2 `content/project_ir.py`（6 导出）

**定位**：raw → IR 编译器 + IR → 数据/YAML 的 round-trip 面。导入：`schemas` + `pydantic` + `yaml` + `core.serialization`。

`__all__`（6）：`IRBuildResult`, `build_ir`, `flatten_entities`, `iter_entity_refs`, `ir_to_data`, `canonical_yaml`

- **IRBuildResult**（frozen）：`ir: ProjectIR | None`（编译失败 = None，诊断在 diagnostics）, `diagnostics: tuple[Diagnostic, ...]`。
- **build_ir(raw: RawProject) -> IRBuildResult**：
  1. `game.yaml` 缺失（loader 已报 FILE_MISSING，此处 raw.files 无该键）→ 直接返回 (None, [LLMSIM_FILE_MISSING path="game.yaml"])（双保险）。
  2. game.yaml 顶层键封闭集 = {`manifest`, `scenario`, `component_schemas`, `authority`, `gameplay_modes`, `capabilities`, `plugin_descriptors`}；逐节 `model_validate`（`extra="forbid"`）：pydantic `ValidationError` → `LLMSIM_SCHEMA`（path = 文件路径，refs = `[e['loc'] 点分串, e['type']]`，每条 error 一条诊断，按 loc 序）；`extra` 键 → `LLMSIM_UNKNOWN_KEY`（path = 文件路径，refs = `[键名]`）。
  3. 各节文件（world/*.yaml 顶层键必为 `world`；characters/items/rules/actions/prompts/scenarios/modules/*.yaml 顶层键必为同名复数键；plugins/*/plugin.yaml 由 plugins 面消费，build_ir 不解析）：同 2 的校验；节文件缺 = 合法空（D-P5-05）。
  4. 成功 → IR（各节文件按 sorted 路径序合并进对应 tuple）；失败 → (None, 诊断集)。**永不 raise** 内容级异常（K2/P5-INV-2 纯产新值）。
- **flatten_entities(ir: ProjectIR) -> dict[str, Any]**：ID → 实体 spec 映射（locations ∪ objects ∪ items ∪ characters ∪ player by player_id）；重复键后者覆盖（重复本身由 check_duplicate_ids 诊断，本函数不判重）。
- **iter_entity_refs(ir: ProjectIR) -> Iterator[tuple[str, str, str]]**：`(holder_id, ref_kind, ref_value)`；ref_kind ∈ {`connection`, `relationship`, `inventory`}（connections.values / relationships.keys / inventory+starting_inventory 元素）。
- **ir_to_data(ir: ProjectIR) -> dict[str, Any]**：`model_dump(mode="json")` 嵌套展开；**尾部 `assert_json_clean`（serialization.py:82）机械钩子**（K7/P5-INV-7）。
- **canonical_yaml(ir: ProjectIR) -> str**：`yaml.safe_dump(ir_to_data(ir), sort_keys=True, allow_unicode=True, default_flow_style=False, width=100)`（D-P5-14）。纯函数；双 dump 字节稳定（#20）。

### 3.3 `content/loader.py`（6 导出）

**定位**：文件系统 + YAML 解析的 IO 边界。**只读**（P5-INV-2）；封闭路径模板（D-P5-07：发现面 = 固定模板，非任意 walk）。

`__all__`（6）：`LAYOUT_REQUIRED`, `LAYOUT_OPTIONAL`, `ProjectLoadResult`, `load_project`, `read_yaml_file`, `detect_v1_shape`

- **LAYOUT_REQUIRED**（`Final[tuple[str, ...]]`）：`("game.yaml",)`。
- **LAYOUT_OPTIONAL**（`Final[tuple[tuple[str, str, str], ...]]`，(glob, 节名, 种类)）：
  `("world/*.yaml","world","world")`, `("characters/*.yaml","characters","characters")`, `("items/*.yaml","items","items")`, `("rules/*.yaml","rules","rules")`, `("actions/*.yaml","actions","actions")`, `("prompts/*.yaml","prompts","prompts")`, `("scenarios/*.yaml","scenarios","scenarios")`, `("modules/*.yaml","modules","modules")`, `("plugins/*/plugin.yaml","plugins","plugin_manifest")`。
  模板深度封闭（`plugins/*/plugin.yaml` 恰好两层）；**全树零 `.py` 扫描**；每模板命中集 `sorted()`（确定性，D-P5-06 同族口径）。
- **ProjectLoadResult**（frozen）：`root: str`, `raw: RawProject | None`（v1 形状拒绝时 = None，D-P5-04）, `diagnostics: tuple[Diagnostic, ...]`。
- **load_project(root: str | Path) -> ProjectLoadResult**（流程，步序即诊断追加序）：
  1. root 不存在 / 非目录 → (None, [LLMSIM_FILE_MISSING path=f"{root}/game.yaml"])。
  2. 读 `game.yaml`：缺 → LLMSIM_FILE_MISSING；`read_yaml_file` 失败 → LLMSIM_YAML_PARSE（path="game.yaml"）。
  3. `detect_v1_shape(game_raw)` → True → (None, [LLMSIM_PROJECT_FORMAT_V1 path="game.yaml", refs=["no manifest", "v1 top-level world/player"]])，**停止**（不编译余下文件，D-P5-04）。
  4. 遍历 LAYOUT_OPTIONAL（模板序）：glob 命中集 sorted；逐文件 `read_yaml_file`；解析失败 → LLMSIM_YAML_PARSE（path=相对路径，**继续**下一文件，不中止）；成功 → files[rel] = 值、texts[rel] = 原文。
  5. `pyproject_present` = 根下 `pyproject.toml` 存在；`plugins_dir_present` = 根下 `plugins/` 是目录。
  6. 返回 (RawProject, 诊断集)。
- **read_yaml_file(path: Path, label: str) -> tuple[Any | None, tuple[Diagnostic, ...]]**：`open(encoding="utf-8")` + `yaml.safe_load`；`YAMLError`/OSError → (None, [LLMSIM_YAML_PARSE path=label])；根非 dict → (None, [LLMSIM_YAML_PARSE path=label, refs=["root-not-dict"]])。纯 helper（测试直用）。
- **detect_v1_shape(raw_game_yaml: Any) -> bool**：`isinstance(dict) ∧ "manifest" not in raw ∧ ("world" in raw or "player" in raw)`（v1 判据：顶层 world/player 且无 manifest——test_empty.yaml:1-12/135/147-151 形状；D-P5-04）。

### 3.4 `content/module_graph.py`（11 导出）

**定位**：模块清单（Spec §28.3/§41）→ 有向图 + 确定性拓扑 + 环/冲突/版本/缺依赖诊断。导入：`schemas` + 仅 stdlib。

`__all__`（11）：`Requirement`, `RequirementKind`, `ModuleEdge`, `ModuleGraph`, `parse_requirement`, `build_module_graph`, `topological_order`, `find_cycles`, `check_unsatisfied_requires`, `check_module_versions`, `detect_conflicts`

- **RequirementKind**（enum, str）：`REQUIRED="required"`, `OPTIONAL="optional"`。
- **Requirement**（frozen）：`module_id: str`, `version_range: str = ""`（`""` 或 `>=X.Y[.Z]`；裸 `X.Y[.Z]` = 精确）。
- **ModuleEdge**（frozen）：`source: str`, `target: str`, `kind: RequirementKind`。
- **ModuleGraph**（frozen）：`nodes: dict[str, ModuleGraphNode]`, `edges: tuple[ModuleEdge, ...]`（构造序 = 节点 casefold 序 × 声明序，确定性）。
- **parse_requirement(entry: str, owner_id: str) -> tuple[Requirement, Diagnostic | None]**：文法 = 去空白后 `id` \| `id >= V`；`id` pattern `^[a-z][a-z0-9_]*$`、`V` = `\d+(\.\d+)*`（Spec §41:1975-1978 例子 `standard.attributes >= 2` 中版本 `2` 为合法 token）；非法 → (Requirement(entry 原样, ""), LLMSIM_MODULE_VERSION path=owner_id, refs=[entry])。
- **build_module_graph(ir: ProjectIR) -> ModuleGraph**：nodes = ir.modules；edges = 各节点 requires（REQUIRED）+ optional（OPTIONAL）经 parse_requirement（解析错误**不**在此报——validator.check_module_versions 复扫并报，build 保持纯转换，D-P5-06）。
- **topological_order(graph: ModuleGraph) -> list[str]**：Kahn 入度拓扑；**平局 = casefold 序**（取当前最小 casefold 节点出队，D-P5-06 钉死唯一确定序）；存在环 → 返回 `[]`（**不 raise**，G5-4 诊断面）。
- **find_cycles(graph: ModuleGraph) -> list[list[str]]**：Tarjan SCC；size>1 或自环的 SCC 各一；每个 SCC 输出 = 其节点 **casefold 排序列表**（旋转归一化的确定性形态，信息无损，D-P5-06）。
- **check_unsatisfied_requires(graph) -> list[Diagnostic]**：REQUIRED 边 target ∉ nodes → LLMSIM_MODULE_REQUIRES_MISSING（path=source，refs=[target]）；OPTIONAL 缺失 = 合法（无诊断）。
- **check_module_versions(graph) -> list[Diagnostic]**：对每条带 version_range 的边：target ∉ nodes → 跳过（归 check_unsatisfied_requires 报，防双报）；∈ nodes：版本比较 = 点分数字逐位（短者补 0）；`>=V` 不满足或精确不等 → LLMSIM_MODULE_VERSION（path=source，refs=[f"{target}:{requirement}", f"have {node.version}"]）。
- **detect_conflicts(graph) -> list[Diagnostic]**：节点 A 的 conflicts 含 c 且 c ∈ nodes → 无序对 {A,c} 一条 LLMSIM_MODULE_CONFLICT（path=min(casefold)，refs=[A.id, c] casefold 序；对称去重，每对一条）。

### 3.5 `content/rule_module.py`（43 导出）

**定位**：v1 condition/rule DSL 的**语义等价**标准 Rule module（G5-5）。两阶段：`parse_dsl`（纯结构，全分支，validate 期可无上下文跑）+ `evaluate_condition`（急进 first-match 遍历，运行时）。v1 语义逐条对齐 `src/game/condition_eval.py` @ `f0a1052`（行号均指该文件）与 `src/game/rules.py` / `src/game/deterministic_rules.py`（同提交）。

**导入纪律特记**：本模块**零 `random` import**（v1 condition_eval.py:3 `import random as _random` 是 v1 非确定性根；v2 随机面 = 注入 `DslRng`，D-P5-15/D-P5-09）。

`__all__`（43，按本表序）：
`DslRng`, `DslToken`, `tokenize_dsl`, `DslNode`, `DSL_NODE_KINDS`, `IfChainNode`, `ComparisonNode`, `InTestNode`, `NotInTestNode`, `ContainsNode`, `SubsetNode`, `SupersetNode`, `IntersectsNode`, `DisjointNode`, `TruthyNode`, `AddNode`, `SubNode`, `MulNode`, `DivNode`, `NegNode`, `NumberNode`, `StringNode`, `VariableNode`, `FunctionCallNode`, `FeasibilityNode`, `AndNode`, `OrNode`, `NotNode`, `DslParseResult`, `DslEvalError`, `Feasibility`, `ConditionOutcome`, `DslContext`, `resolve_variable`, `parse_dsl`, `evaluate_condition`, `ActionInput`, `action_text`, `resolve_target`, `TargetRef`, `FeasibilityResult`, `check_action_feasibility`, `BUILTIN_RULE_IDS`

**错误族**：`DslEvalError(ValueError)`（解析 + 求值语义错误统一族；v1 `ConditionEvalError(ValueError)` condition_eval.py:9 的等价物）——`evaluate_condition` 层**不吞**；`check_action_feasibility` 层按规则 warn+skip（v1 rules.py:102-104 口径，`logging` 模块 logger，默认无输出）。

- **DslRng**（Protocol，runtime_checkable）：`rand() -> float`（[0,1)）；`uniform(lo: float, hi: float) -> float`；`randint(lo: int, hi: int) -> int`（闭区间，对齐 v1 condition_eval.py:250-252 `_random.randint` 口径）。
- **DslToken**（frozen）：`kind: str`（`number`/`string`/`name`/`op`）, `value: str`。
- **tokenize_dsl(expression: str) -> list[DslToken]**：**正则逐字对齐 v1 `_TOKEN_RE`（condition_eval.py:25-30）**（number `\d+(?:\.\d+)?` / string `"…"` / name `[A-Za-z_][A-Za-z0-9_\.]*|[一-鿿][一-鿿A-Za-z0-9_\.]*` / op `<=|>=|!=|[+\-*/<>=(),;:]`）；不可解析片段 → `DslEvalError`（对齐 v1 :45-47 行为；错误消息含片段前 20 字符，对齐 v1 :46）。
- **DSL_NODE_KINDS**（`Final[frozenset[str]]`，23 枚）：`if_chain, comparison, in, not_in, contains, subset, superset, intersects, disjoint, truthy, add, sub, mul, div, neg, number, string, variable, function_call, feasibility, and, or, not`。
- **DslNode**（pydantic v2 判别联合，discriminator="kind"）：23 节点类之并。全部节点类 frozen BaseModel，`kind: Literal[...]` 首字段。节点表（字段均为必填除注明）：

| 类 | kind | 字段 | v1 依据 |
|---|---|---|---|
| IfChainNode | if_chain | branches: tuple[tuple[DslNode, FeasibilityNode], ...]；trailing: FeasibilityNode | parse_if :72-93（`;` 分隔分支 + 尾裸 outcome 必需） |
| ComparisonNode | comparison | op: Literal["<",">","=","<=",">=","!="]；left/right: DslNode | :119-143（任一侧 str → 仅 `=`/`!=`，否则 `ConditionEvalError("字符串不支持 …")`） |
| InTestNode / NotInTestNode | in / not_in | left/right: DslNode | :147-168（右需列表，`_to_set` :353-360） |
| ContainsNode | contains | left: DslNode（容器）, right: DslNode（元素） | :169-180 |
| SubsetNode / SupersetNode / IntersectsNode / DisjointNode | subset / superset / intersects / disjoint | left/right: DslNode | :181-193（`_SET_KEYWORDS` :66） |
| AndNode / OrNode | and / or | left/right: DslNode | :95-111（`_CONDITION_KEYWORDS` :66） |
| NotNode | not | operand: DslNode | :113-117 |
| TruthyNode | truthy | value: DslNode | :119-121（裸值条件） |
| AddNode / SubNode | add / sub | left/right: DslNode | parse_add_sub（:195-211 区间，含行内口径） |
| MulNode / DivNode | mul / div | left/right: DslNode | :212-218（**除零 → DslEvalError**，v1 :216-217 口径） |
| NegNode | neg | operand: DslNode | 一元 `-`（:219-224 区间） |
| NumberNode | number | value: float | tokenizer number 组 |
| StringNode | string | value: str | tokenizer string 组（去引号） |
| VariableNode | variable | name: str | :343-351 |
| FunctionCallNode | function_call | name: Literal["rand","randint","min","max","len"]；args: tuple[DslNode, ...]（rand 0 或 2 参；randint/min/max 2 参；len 1 参——parse 期 arity 校验，v1 :243-273 口径） | :243-273（rand→_random.random()/uniform；randint→_random.randint；len 需 list/str :253-258；min/max 双参 :259-265） |
| FeasibilityNode | feasibility | feasibility: Feasibility；probability: float \| None（仅 uncertain 可带；**parse 期**校验 0<p<1，v1 :296-299 口径；allowed/blocked 带 prob = parse 错误，对齐 v1 :293 前文分支） | _parse_outcome :275-299（嵌套 if 在 outcome 位 → IfChainNode 递归，:279-281） |

- **DslParseResult**（frozen）：`ast: DslNode | None`, `diagnostics: tuple[Diagnostic, ...]`（code=LLMSIM_DSL_PARSE, path=入参 path_label）。
- **parse_dsl(expression: str, path_label: str) -> DslParseResult**：结构解析（tokenize → 文法树；**全部 if 分支结构解析**——比 v1 急进跳过更严，§8.4 D-P5-DEV-3 披露）。结构检查面 = v1 parser 的 parse 时检查全集：if 形状（:72-93）、比较/集合 op 存在性（:104-143 的 token 判定）、函数名/arity（:243-273）、outcome 关键字 ∈ {allowed,blocked,uncertain}（:283-287，lowercase 化）+ uncertain prob 范围（:296-299）、末尾多余 token（expect_end :301-304）。**不做**变量解析/值求值（validate 期无上下文可跑 = G5-6 的机械前提）。
- **evaluate_condition(ast: DslNode, context: DslContext, rng: DslRng) -> ConditionOutcome**：急进遍历（与 v1 parse+eval 融合的行为等价）：if_chain 逐分支——求值条件；真 → 立即返回该分支 outcome（**后续分支不求值、不做语义检查**——v1 `_skip_until_if_end` :331-340 口径的等价物）；假 → 下一分支；尾 trailing 返回。比较/集合/算术/函数按 v1 语义（含 str 比较限制 :125-131、除零 :216-217、len 类型 :255-258、rand 族 → rng 注入）；语义错误 → **raise DslEvalError**（不吞）。
- **ConditionOutcome**（frozen）：`feasibility: Feasibility`, `probability: float | None = None`（v1 condition_eval.py:13-16 同形）。**uncertain 无 `:prob` 时 DSL 层缺省 0.5**（v1 condition_eval.py:294 `probability = 0.5`，`:prob` 覆盖后 `0<p<1` 检查 @ :297-299——v1 测试 `test_uncertain_without_probability_defaults_to_half` @ tests/test_condition_eval.py:91 钉死）；roll 消费面另有独立缺省 `or 0.5`（state_apply.py:97）——该处属 P6 runtime 接线面（§7.5），与 DSL 层缺省互不替代。
- **Feasibility**（enum, str）：`ALLOWED="allowed"`, `BLOCKED="blocked"`, `UNCERTAIN="uncertain"`（v1 `_VALID_OUTCOMES` :31 同集）。
- **DslContext**（frozen）：`player: dict[str, Any] = {}`（v1 player dict 原形）, `target: dict[str, Any] | None = None`（v1 target dict 原形，`{"properties": {...}}`）, `variables: dict[str, Any] = {}`（自由名；v1 自定义规则上下文 = {player, target, action}（rules.py:98-101）→ v2 `variables={"action": …}` 映射）。
- **resolve_variable(name: str, context: DslContext) -> Any**（**查找序逐字对齐 v1**）：
  - `player.X`（condition_eval.py:398-421）：`player.attributes[X].value`（attributes 为 dict 且含 X 且 item 为 dict 含 "value"）→ `player.physical_profile[X]` → `player.capabilities.skill_levels[X]` → `player[X]` → `DslEvalError(f"未知变量 player.{X}")`。
  - `target.X`（:424-441）：`target.properties` 内别名表 `{weight: (weight_kg, weight), width: (effective_width_cm, width_cm, width)}`（:430-433）逐键探测 → `target[X]` → `DslEvalError(f"未知变量 target.{X}")`。
  - 其他（:343-351）：`name not in context.variables or context.variables[name] is None` → `DslEvalError(f"未知变量 {name!r}")`（**v1 对显式 None 值按缺失处理**，:347-349 口径）→ 返回值。
- **ActionInput**（frozen）：`raw_input: str = ""`, `interpreted_intent: str = ""`, `action_description: str = ""`, `speech_content: str = ""`, `target_object_id: str | None = None`, `action_type: str | None = None`（v1 player_action dict 键封闭集，rules.py:31-38/41-53 用到之全集）。
- **action_text(action: ActionInput) -> str**：非空 (raw_input, interpreted_intent, action_description, speech_content) 以 `"\n"` 连接（v1 `_action_text` rules.py:31-38 逐字等价）。
- **TargetRef**（frozen）：`object: dict[str, Any] | None`, `width_cm: float | None`, `source: str | None`（`object:<id>` | `location:<id>` | None）。
- **resolve_target(action: ActionInput, objects: Mapping[str, Any], locations: Mapping[str, Any]) -> TargetRef**：v1 `_target_object`（rules.py:41-53：id 直查 → 文本含 name/object_id 首命中，遍历序 = objects dict 序）+ `_target_width`（:55-75：目标对象 properties `effective_width_cm` 优先 `width_cm`，:58 口径 → 回退文本命中的 location 同法取宽）的合并等价物。
- **FeasibilityResult**（frozen）：`feasibility: Feasibility`, `reason: str`, `matched_rule: str`, `success_probability: float | None = None`, `requires_roll: bool = False`（v1 结果 dict 五键全映射，rules.py:85-91）。
- **check_action_feasibility(rules: Sequence[RuleSpec], action: ActionInput, context: DslContext, objects: Mapping[str, Any], locations: Mapping[str, Any], disabled: frozenset[str] = frozenset(), rng: DslRng | None = None) -> FeasibilityResult | None**：
  1. `text = action_text(action)`；`target_ref = resolve_target(action, objects, locations)`。
  2. **项目规则**：`[r for r in rules if not r.disabled]` 按 `(priority, id.casefold())` 排序（D-P5-06）；逐条：`r.match` 非空且 `re.search(r.match, text, re.IGNORECASE)` 不中 → skip（v1 rules.py:137-138 口径）；`r.condition` 非空 → `parse_dsl`（结构错 = 配置级错误，validate 已拦；运行期若再遇 → 记 warn + skip 本条）→ `evaluate_condition(ast, context, rng)`；`DslEvalError` → **warn + skip 本条**（v1 rules.py:102-104 逐字口径）→ 命中返回 `FeasibilityResult(outcome.feasibility, f"系统规则预判（{r.id}）：{r.description}", f"custom:{r.id}", outcome.probability, outcome.feasibility is Feasibility.UNCERTAIN)`（v1 :106-114 五字段口径）。`r.condition` 空 → `FeasibilityResult(r.feasibility or ALLOWED, 同 reason, f"custom:{r.id}", r.probability, (r.feasibility or "allowed") == "uncertain")`（v1 :116-121 口径）。
  3. **内建规则 1..5**（`id not in disabled` 门控，固定序，阈值常量冻结于实现）：
     - 1 `blocked_common`（rules.py:146-153）：遍历 `context.player["capabilities"]["blocked_common_actions"]`，`_text_matches_rule` 等价（:13-30：全串子串 ∨ 逗号/、分段子串 ∨ **16 词表** {道歉,感谢,不会跳舞,秘密通道,暗门,命令,仆人,开锁,门锁,撬锁,推,搬,拿起,穿过,通过} 中 rule 串所含词命中 text）→ blocked，reason `系统规则预判：玩家人设限制不允许执行该行动（{rule}）。`。
     - 2 `extraordinary`（:155-162）：同法对 `allowed_extraordinary_actions` → allowed，reason `系统规则预判：玩家具备可执行该行动的特殊能力（{rule}）。`。
     - 3 `strength_vs_weight`（:164-187）：`action_type=="interact"` ∧ target ∧ `props["weight_kg"]` 非空 ∧ `physical_profile["strength"]` 非空：capacity = strength×**50.0**（:9 常量）；capacity < weight → blocked；capacity < weight×1.5 → uncertain，prob = `max(0.1, min(0.9, capacity/(weight*1.5)))`。
     - 4 `skill_vs_lock`（:188-206）：同作用域 `props["lock_difficulty"]` 非空：skill = `skill_levels["lockpicking"]`（缺省 0.0）；skill < difficulty → uncertain，prob = `max(0.05, min(0.95, skill/difficulty if difficulty else 0.05))`；否则 allowed。
     - 5 `body_width_vs_passage`（:208-223）：`action_type=="move"` ∧ width_cm 非空 ∧ `physical_profile["body_width_cm"]` 非空：body > width → blocked；否则 allowed。
     - matched_rule 名 = v1 原样五名（`blocked_common` 等）；reason 文本 = v1 f-string 原样（:150-151/:159-160/:174-175/:180-181/:194-195/:200-201/:214-215/:220-221）。
  4. 全不中 → `None`（v1 :225 口径）。
- **BUILTIN_RULE_IDS**（`Final[tuple[str, ...]]`）：`("blocked_common", "extraordinary", "strength_vs_weight", "skill_vs_lock", "body_width_vs_passage")`（= v1 matched_rule 名 = v2 disable 用 ID，D-P5-10 映射表：v1 disable 数字 1..5 ↔ 本 tuple 下标）。

**等价性契约（G5-5 机械面）**：对任意 (expression, context)：v1 `evaluate_condition`（condition_eval.py:35-39）成功且不含"未达分支含垃圾"形态（§8.4 D-P5-DEV-3）⟺ v2 `parse_dsl` + `evaluate_condition` 同值（feasibility + probability 逐位相等，float 按 `==`）；v1 raise `ConditionEvalError` ⟺ v2 在 parse_dsl（结构错）或 evaluate_condition（语义错）raise/产诊断。66 例 characterization 集验证（§6.2，断言 #11）。

### 3.6 `content/validator.py`（8 导出）

**定位**：IR 语义检查编排 + K8 文本扫描 + 插件检查。导入：`schemas` `project_ir`（RawProject）`module_graph` `rule_module`（parse_dsl）`plugins.registry` `re`。

`__all__`（8）：`ValidationResult`, `validate_project`, `check_duplicate_ids`, `check_references`, `check_authority_conflicts`, `check_deployment_leakage`, `check_dsl_parses`, `sort_diagnostics`

- **ValidationResult**（frozen）：`ok: bool`（无 error 级诊断）, `diagnostics: tuple[Diagnostic, ...]`（**已排序**）, `ir: ProjectIR | None`。
- **validate_project(ir: ProjectIR, raw: RawProject | None = None) -> ValidationResult**：诊断 = check_duplicate_ids ∪ check_references ∪ check_authority_conflicts ∪ check_dsl_parses ∪ module 面（build_module_graph + check_unsatisfied_requires + check_module_versions + detect_conflicts + 对 find_cycles 每环一条 LLMSIM_MODULE_CYCLE path=min(node) refs=节点序）∪（raw 非 None 时）check_deployment_leakage(raw) ∪ plugins.registry.validate_plugins(discover_local_plugins(raw).registry, ir, raw)；最后 `sort_diagnostics`。**永不 raise**（内容级）。raw=None → 仅 IR 面（K8 文本面与插件面跳过，文档披露）。
- **check_duplicate_ids(ir) -> list[Diagnostic]**：池内判重（LLMSIM_DUPLICATE_ID，path=池名，refs=[id, 首次出现文件, 重复出现文件]）：池 = locations / objects+items / characters / player 单值（对 location/object/character id 撞名 = 合法，v1 独立命名空间口径）；**全局唯一池** = rules / actions / modules / prompts / scenarios（含默认 scenario id）/ component_schemas / authority / gameplay_modes / capabilities / plugin_descriptors（path=池名）。
- **check_references(ir) -> list[Diagnostic]**（LLMSIM_UNRESOLVED_REF，path=holder id，refs=[ref_kind, ref_value]）：`connection` 值 → location id 池；`relationship` 键 → character 池 ∪ {player_id}；`inventory`/`starting_inventory` 元素 → object 池（含 items）。
- **check_authority_conflicts(ir) -> list[Diagnostic]**：两两同 domain ∧ 双 exclusive → LLMSIM_AUTHORITY_CONFLICT（path=domain，refs=[owner_a, owner_b] casefold 序，每对一条）（D-P5-03 声明域重叠级）。
- **check_deployment_leakage(raw) -> list[Diagnostic]**：**DEPLOYMENT_FORBIDDEN_KEYS = 12 名封闭集，构造 = 字符串拼接自证豁免**（`{"open"+"ai","anthro"+"pic","lang"+"chain","lite"+"llm","ol"+"lama","gem"+"ini","g"+"pt","cla"+"ude","ll"+"m","prov"+"ider","api_"+"key","base_"+"url"}`——与 test_import_boundary.py:225-240 集逐名相等，#19 附注核验）；扫描面 = raw.texts 全部 key（含 plugins/*/plugin.yaml 与 pyproject.toml 文本）；对每 (文件, 名)：`re.finditer(rf"\b{name}\b", text.casefold())` ≥1 命中 → 一条 LLMSIM_DEPLOYMENT_FIELD（path=文件，refs=[name]，每对去重）。**口径**：`\b` 词边界 → `llmsim` 不命中 `llm`、`api_key_env` 命中 `api_key`（`_` 非 \w 边界——`api_key_env` 中 `api_key` 后接 `_`：`_` 属 \w，故 **不**命中；核验：`\bapi_key\b` 对 "api_key_env" = 无边界（`y`→`_` 均 \w）= 不命中——正确，v1 simulation.yaml 的 `api_key_env` 键名本身是 Deployment 面而非项目面，项目里出现字面 `api_key` 完整词才命中，口径一致）（D-P5-11）。
- **check_dsl_parses(ir) -> list[Diagnostic]**：每条 RuleSpec.condition 与 ActionSpec.condition（非 None）→ `parse_dsl(expr, path_label=id)`，透传其诊断（path 重写为规则/动作 id，refs=[expr 前 40 字符]）。
- **sort_diagnostics(diagnostics: Sequence[Diagnostic]) -> list[Diagnostic]**：稳定排序 key = `(code, path, message)`（D-P5-12）。

### 3.7 `content/cli.py`（4 导出）

**定位**：`llmsim validate` 入口（T09）。导入：`argparse` `sys` `loader` `project_ir` `validator` + 渲染用 stdlib。**stdout 纪律（D-P5-12）**：`--json` 模式 stdout = 且仅 = `render_json` 输出；human 模式 = `render_human` 行 + 1 行汇总；任何模式下**零其他 stdout**（stderr 不限制，P5 实现零 stderr 输出）。

`__all__`（4）：`main`, `run_validate`, `render_human`, `render_json`

- **main(argv: Sequence[str] | None = None) -> int**：`argv=None` → `sys.argv[1:]`（console script 口径，pyproject `[project.scripts] llmsim = "src.engine_v2.content.cli:main"`）。argparse 子命令 `validate <project_root> [--json]`；**usage 错 = 返回 2**（自捕获：parser.error 覆写收集消息 → stderr 渲染 → return 2，不 raise SystemExit——console wrapper 以返回值退出）。无子命令/未知参数 = 2。
- **run_validate(project_root: str | Path, as_json: bool = False) -> int**：`load_project` → raw=None 时以 raw 级诊断成 ValidationResult(ir=None)；否则 `build_ir` → ir=None 时同上；否则 `validate_project(ir, raw)`；输出（--json → render_json 到 stdout；human → render_human 每诊断一行 + `llmsim validate: {e} error(s), {w} warning(s)` 末行）；退出 = 1 if 任一 error 级 else 0。
- **render_human(diagnostics: Sequence[Diagnostic]) -> str**：每诊断一行 `[ERROR|WARNING] {code} {path}: {message}`（排序后序）。
- **render_json(result: ValidationResult) -> str**：`json.dumps({"ok": …, "diagnostics": [{"code","severity","path","message","refs": [...]}…（已排序）], }, ensure_ascii=False, indent=2, sort_keys=True) + "\n"`（refs 数组）。纯 stdout 可 `json.loads`（断言 #13）。

### 3.8 `plugins/manifest.py`（3 导出）

**定位**：本地项目插件 manifest（Spec §28.1，"必须显式 manifest" L1520-1521；禁隐式扫描 L1530）的解析。导入：`schemas`（Diagnostic）+ 仅 stdlib。

`__all__`（3）：`PluginManifest`, `PluginManifestParseResult`, `parse_plugin_manifest`

- **PluginManifest**（frozen）：

| 字段 | 类型 | 约束/默认 | 依据 |
|---|---|---|---|
| id | str | pattern `^[a-z][a-z0-9_]{0,63}$` | §28.1 例 `infection`（:1525） |
| version | str | `\d+(\.\d+)*` | §28.3 |
| entrypoint | str | `module:Attribute`（恰一个 `:`；module = 点分标识符；attribute = 标识符） | §28.1 例 `my_game.systems.infection:InfectionSystem`（:1526） |
| requires | tuple[str, ...] | () | §28.3:1538 |
| optional | tuple[str, ...] | () | :1539 |
| conflicts | tuple[str, ...] | () | :1540 |
| engine_version | str | `""`（文法同 ProjectManifest） | :1541 |

- **PluginManifestParseResult**（frozen）：`manifest: PluginManifest | None`, `diagnostics: tuple[Diagnostic, ...]`。
- **parse_plugin_manifest(path_label: str, raw: Any) -> PluginManifestParseResult**：非 dict → (None, [LLMSIM_SCHEMA path=path_label])；字段违例 → LLMSIM_SCHEMA（refs=[loc, type]）；entrypoint 文法错 → LLMSIM_PLUGIN_ENTRY_INVALID（path=path_label，refs=[entrypoint 原值])。

### 3.9 `plugins/api.py`（3 导出）

**定位**：插件 API 契约面（Protocol 缝，执行归 P6+；P5 **永不 import 插件模块**——G5-3）。导入：仅 stdlib + pydantic。

`__all__`（3）：`PLUGIN_API_VERSION`, `EntryPointSpec`, `PluginAPI`

- **PLUGIN_API_VERSION**（`Final[str]`）：`"1"`（契约版本标记；未来不兼容演进递增）。
- **EntryPointSpec**（frozen）：`module: str`（点分标识符）, `attribute: str`（标识符）；classmethod `from_string(s: str) -> tuple[EntryPointSpec | None, Diagnostic | None]`（`module:Attribute` 文法；非法 → (None, LLMSIM_PLUGIN_ENTRY_INVALID path=s)。与 manifest.py 的文法实现共享口径（两个模块各自持有纯函数实现，禁止互导以维持 plugins 包内 DAG 简洁——文法正则常量在各自模块内同值定义，测试同值核验）。
- **PluginAPI**（Protocol）：`id: str`、`version: str`、`capabilities: tuple[str, ...]`。P5 = 形状声明（runtime_checkable）；任何对 PluginAPI 实例的方法调用 = P6+ runtime 行为（P5 测试仅做 isinstance 形状断言）。

### 3.10 `plugins/registry.py`（7 导出）

**定位**：双路发现（本地 manifest + entry-point）+ 注册校验（G5-2/G5-3）。导入：`schemas` `project_ir`（RawProject）`plugins.manifest` `plugins.api` `importlib.metadata`。**机械面**：本文件 + `content/loader.py` 是 AST 封闭模式扫描对象（断言 #6）：源码中不得出现 `import_module` / `__import__` / `spec_from_file_location` / `module_from_spec` 调用或 `entry.load()` 模式。

`__all__`（7）：`ENGINE_VERSION`, `PluginSourceKind`, `RegisteredPlugin`, `PluginRegistry`, `discover_local_plugins`, `discover_entry_point_plugins`, `validate_plugins`

- **ENGINE_VERSION**（`Final[str]`）：`"0.5.0"`（P5 钉死的引擎版本；manifest `engine_version` 对照此值；随 release 更新 = 单点常量，D-P5-08）。
- **PluginSourceKind**（enum, str）：`LOCAL_MANIFEST="local_manifest"`, `ENTRY_POINT="entry_point"`。
- **RegisteredPlugin**（frozen）：`manifest: PluginManifest`, `source: PluginSourceKind`, `origin: str`（本地 = 相对路径 `plugins/<id>/plugin.yaml`；entry-point = distribution 名或 EP 名）。
- **PluginRegistry**（frozen）：`plugins: dict[str, RegisteredPlugin]`（key = manifest.id；构造期 casefold 唯一性由发现函数保证）。
- **discover_local_plugins(raw: RawProject) -> tuple[PluginRegistry, tuple[Diagnostic, ...]]**：遍历 `raw.files` 中匹配 `plugins/*/plugin.yaml` 的键（sorted）→ `parse_plugin_manifest`；解析失败 → 跳过该 manifest + 诊断；**id 重复**（跨本地 manifest）→ LLMSIM_DUPLICATE_ID（path="plugins"，refs=[id, 首文件, 重文件]），后者胜出（确定性：sorted 序）。**无 manifest 的 `plugins/<id>/` 目录 = 不存在**（loader 模板 `plugins/*/plugin.yaml` 不命中 → 无键 → 零诊断零加载，D-P5-07）。
- **discover_entry_point_plugins(group: str = "llmsim.plugins") -> tuple[PluginRegistry, tuple[Diagnostic, ...]]**：`importlib.metadata.entry_points(group=group)`（**仅 metadata 枚举**——EP 对象只读 `.name`/`.value`/`.distribution`，**零 `.load()` 调用、零 import**，D-P5-08）；逐 EP：`EntryPointSpec.from_string(EP.value)`；非法 → LLMSIM_PLUGIN_ENTRY_INVALID（origin=distribution 名）；合法 → RegisteredPlugin(manifest=PluginManifest(id=EP.name, version=EP.distribution 版本或 "0.0.0", entrypoint=EP.value), source=ENTRY_POINT, origin=distribution 名)。
- **validate_plugins(registry: PluginRegistry, ir: ProjectIR, raw: RawProject | None = None, engine_version: str = ENGINE_VERSION) -> list[Diagnostic]**：
  1. `raw.plugins_dir_present ∧ ¬raw.pyproject_present` → LLMSIM_PLUGIN_NO_PYPROJECT（path="pyproject.toml"，refs=["plugins/ present but pyproject.toml missing"]）（D-P5-07）。
  2. 每个注册 manifest.engine_version 非空且对照 engine_version 不满足（D-P5-06 版本比较口径）→ LLMSIM_ENGINE_VERSION（path=manifest.id，refs=[constraint, engine_version]）。
  3. 每个 `ir.plugin_descriptors` 条目 id ∉ registry.plugins → LLMSIM_PLUGIN_ENTRY_UNRESOLVED（**warning**，path=descriptor.id，refs=[source 期望]）（D-P5-08：运行时或可由其他分布提供，不阻塞 validate）。

---

### 3.11 锚点台账与 import 边界同步机制

**原则（沿 P4 §3.11 体例）**：P5 **不新增 core 模块、不改 core `__all__`**（core 冻结 32/308，D-P5-01）；锚点面唯一变更文件 = `tests/engine_v2/core/test_import_boundary.py`（**纯追加**：既有行零改动）。全部锚点行号 @ 冻结 HEAD `e5c4db4` 已逐行核验。

**锚点同步表**：

| 文件 | 锚点（冻结行号，已核验） | P5 动作 |
|---|---|---|
| `src/engine_v2/core/__init__.py` | import 块 L51-415；`__all__ = [` L416 … `]` L725（308 名） | **零修改**（D-P5-01：P5 模块不入 core） |
| `tests/engine_v2/core/test_closeout.py` | L96-129 `_CORE_SUBMODULE_NAMES`（32）；L169 `shadowed == {"snapshot"}`；L181-225 算术注释块（`# = 308` @ L225）；L226 `len(core_pkg.__all__) == 308` | **零修改**（32/308 不变 → 全组断言自然通过） |
| `tests/engine_v2/core/test_import_boundary.py` | L58-91 `CORE_SUBMODULES`；L98-151 PROVIDER/V1/NETWORK 根集；L192-199 `P4_SUBMODULES`；L209-220 `P4_TEST_FILES`；L225-240 `P4_LLM_PROVIDER_BLACKLIST`（12 名）；L246 `_collect_absolute_imports`；L263 `_blacklist_category`；L292 `_p3_strict_violation`；L316 `TestB1StaticScan`（:318-322 文件集 = CORE_SUBMODULES∪{__init__}）；`TestB3OfflineRunnable`（递归 `tests/engine_v2/**`）；L443 `TestP4Boundary`；L474-478 12 名 casefold 词边界扫描模式 | **唯一锚点变更文件，纯追加**：① L240 后（P4_LLM_PROVIDER_BLACKLIST 块止）插入两个常量块 `P5_SUBMODULES: tuple[str, ...]`（10 茎：`schemas, project_ir, loader, module_graph, rule_module, validator, cli` + `manifest, api, registry`）与 `P5_TEST_FILES: tuple[str, ...]`（15 项，§3.12 测试文件清单，不含 `__init__.py`，P4_TEST_FILES 同款口径）；② 文件尾追加 `class TestP5Boundary`（5 方法，§6.4）。既有行零改动 |
| `tests/test_engine_v2_skeleton.py` | L27-41 `SUBPACKAGES`（13 子包：`plugins` @ L30、`content` @ L36）；L110-136 `_is_core_reexport_node`（**core 专属豁免**）；L144 `test_engine_v2_init_files_are_docstring_only`（L152 附近 `len(init_files) == len(SUBPACKAGES)+1`；逐文件 body 逐节点 docstring-only 断言，仅 core_init 豁免） | **零修改**（D-P5-02：`content/__init__.py`（8 行）与 `plugins/__init__.py`（7 行）保持 docstring-only → 断言面不变；P5 消费方走子模块路径 import，如 `from src.engine_v2.content.loader import load_project`） |
| `src/engine_v2/content/__init__.py` / `src/engine_v2/plugins/__init__.py` | 8 行 / 7 行，docstring-only（P5 填充标记） | **零修改**（同上） |
| `src/engine_v2/README.md` | L17 `plugins/` 行、L23 `content/` 行、L57 Phase 5 描述行（"→ `content/`、`modules/`、`plugins/`"） | **零修改**（P5 恰好填充 content/ 与 plugins/；README 表述保持准确；`modules/` 归 P9） |
| `pyproject.toml` | L1 `[project]`；L2 `name = "llm-based-sim"`；L3 `version = "0.1.0"`；L6-16 dependencies（L7 langchain、L8 langgraph、L9 langchain-openai、L10 pydantic、L11 pyyaml、L12-15 jinja2/structlog/rich/python-dotenv）；L18 `[project.optional-dependencies]`；L26-28 ruff；L30-32 pytest | **唯一 py 配置变更**：L16（dependencies `]`）与 L18 之间插入：空行 + `[project.scripts]` + `llmsim = "src.engine_v2.content.cli:main"` + 空行。**dependencies 零增删**（D-P5-15：无新依赖） |
| `tests/engine_v2/core/conftest.py`（797 行，P4 节自 L417 起） | — | **零修改**（P5 测试 fixture 自建于 `tests/engine_v2/content/conftest.py`） |

**TestB3OfflineRunnable 自动覆盖**（零修改面）：其扫描面 = `tests/engine_v2/**` 递归（P4 先例），P5 新测试目录 `tests/engine_v2/content/`、`tests/engine_v2/plugins/` 自动进入离线可运行断言面 → P5 测试文件**不得**在 import 期触网/触真实 LLM（P5-INV-15 的测试侧镜像）。

### 3.12 实现波次与文件白名单（封闭集）

**波次**（依赖序；W6 末段串行含锚点同步，P4 波次 F 先例）：

| 波次 | 内容 | 任务 | 串行约束 |
|---|---|---|---|
| W1 | `content/schemas.py` + `test_schemas.py` | T02a | — |
| W2 | `content/project_ir.py` + `content/loader.py` + `content/conftest.py` + `content/__init__.py` + `test_project_ir.py` + `test_loader.py` | T02b/T03 | W1 后 |
| W3 | `content/module_graph.py` + `test_module_graph.py` | T04 | W1 后（可与 W2 并行） |
| W4 | `content/rule_module.py` + `test_rule_dsl_parity.py` + `test_rule_module.py` | T07 | W1 后（**最重，单独串行**；66 例等价集） |
| W5 | `plugins/{manifest,api,registry}.py` + `plugins/{__init__,conftest,test_manifest,test_registry}.py` | T05/T06 | W1 后（可与 W2/W3/W4 并行） |
| W6（末，串行） | `content/validator.py` + `content/cli.py` + `pyproject.toml [project.scripts]` + 三组 fixture（#30-39）+ `test_validator.py` + `test_cli.py` + `test_p5_gate_scenario.py` + `test_p5_adversarial.py` + `test_p5_integration.py` + **`test_import_boundary.py` P5 块（锚点同步）** | T08/T09/T10 + 锚点 | W1-W5 全绿后 |

**白名单（39 文件，封闭集）**——G5 门禁运行 `git diff --name-only e5c4db4..HEAD -- src tests pyproject.toml`（**代码区域限定**，P4 §3.12 体例：白名单只覆盖代码区），文件集 **必须恰好等于**本表（多一少一 = 门禁失败）。W1 交付物（本文档 `docs/v2/contracts/P5-*.md` 与 `.review-drafts/p5-design-author.json`）不属代码白名单，单独追踪（`.review-drafts/` 目录未入 git，文档提交属 W1 面）。

| # | 文件 | 性质 |
|---|---|---|
| 1-7 | `src/engine_v2/content/{schemas,project_ir,loader,module_graph,rule_module,validator,cli}.py` | 新增 |
| 8-10 | `src/engine_v2/plugins/{manifest,api,registry}.py` | 新增 |
| 11 | `pyproject.toml` | 修改（仅 +`[project.scripts]` 3 行块） |
| 12 | `tests/engine_v2/content/__init__.py` | 新增（1 行 docstring，tests/engine_v2/core/__init__.py 同款） |
| 13 | `tests/engine_v2/content/conftest.py` | 新增（fixture：`seeded_rng`（可复现 DslRng 实现）、`zero_python_project`（fixture 路径常量）、`broken_project`、`plugin_project`、IR/RuleSpec 构造器） |
| 14-24 | `tests/engine_v2/content/{test_schemas,test_project_ir,test_loader,test_module_graph,test_rule_dsl_parity,test_rule_module,test_validator,test_cli,test_p5_gate_scenario,test_p5_adversarial,test_p5_integration}.py` | 新增（11 个） |
| 25 | `tests/engine_v2/plugins/__init__.py` | 新增（1 行 docstring） |
| 26 | `tests/engine_v2/plugins/conftest.py` | 新增（fixture：manifest 文本样例、entry-point monkeypatch 面） |
| 27-28 | `tests/engine_v2/plugins/{test_manifest,test_registry}.py` | 新增 |
| 29 | `tests/engine_v2/core/test_import_boundary.py` | 修改（纯追加 P5 块，§3.11） |
| 30 | `tests/fixtures/v2_project_zero_python/game.yaml` | 新增 fixture（manifest+scenario；镜像 test_empty.yaml 的 meta 值：max_ticks 20、ticks_per_game_minute 1、game_time、narrative_style） |
| 31 | `tests/fixtures/v2_project_zero_python/world/main_world.yaml` | 新增 fixture（world 节：environment + ≥2 locations 带 connections + ≥2 objects 带 properties{weight_kg, lock_difficulty, width_cm}） |
| 32 | `tests/fixtures/v2_project_zero_python/characters/npc01.yaml` | 新增 fixture（characters 节：1 名，personality/relationships/inventory 齐全） |
| 33 | `tests/fixtures/v2_project_zero_python/rules/basics.yaml` | 新增 fixture（rules 节：≥2 条 RuleSpec——1 条 `condition` if-chain（含 `player.X`/`target.X`/算术/函数各一）、1 条 `match`+`feasibility`+`probability` 形） |
| 34 | `tests/fixtures/v2_project_zero_python/actions/move.yaml` | 新增 fixture（actions 节：1 条 ActionSpec 带 DSL condition） |
| 35 | `tests/fixtures/v2_plugin_local/game.yaml` | 新增 fixture（plugin_descriptors 声明 infection） |
| 36 | `tests/fixtures/v2_plugin_local/pyproject.toml` | 新增 fixture（**内容零 12 名命中**：name="infection-plugin-project"、version、dependencies=[]——K8 扫描面自洽） |
| 37 | `tests/fixtures/v2_plugin_local/plugins/infection/plugin.yaml` | 新增 fixture（id/version/entrypoint `infection_plugin.system:InfectionSystem`/requires/engine_version ">=0.5.0"） |
| 38 | `tests/fixtures/v2_project_broken/game.yaml` | 新增 fixture（故意损坏：manifest 节 + 顶层 `api_key: "sk-test"` 字段 + plugin_descriptors 声明未注册插件——#17/#19 断言靶） |
| 39 | `tests/fixtures/v2_project_broken/world/dup_world.yaml` | 新增 fixture（两个同名 location id + 一条指向不存在 location 的 connection——#17 DUPLICATE_ID/UNRESOLVED_REF 靶） |

**白名单外 = 零修改**：core/、P4 六模块、v1 `src/`/`public_start/`/`config/`/`prompts/`、既有全部测试、`test_closeout.py`、`test_engine_v2_skeleton.py`、`content/__init__.py`、`plugins/__init__.py`、`README.md`、其余 `pyproject` 段。

**gate 运行序（W6 尾）**：① `.venv/bin/python -m pytest tests/ -x -q`（全绿）；② `.venv/bin/python -m ruff check src/engine_v2/content src/engine_v2/plugins tests/engine_v2`（clean，line-length 100 口径 pyproject:27）；③ `git diff --name-only e5c4db4..HEAD -- src tests pyproject.toml` == 白名单 39（§3.12 表）；④ TestP5Boundary 全组绿（含 12 名自扫描 0 命中——验证 split-string 豁免有效）；⑤ TestB1StaticScan/TestB3OfflineRunnable/TestP4Boundary/skeleton 全组绿（零修改锚点回归）；⑥ `llmsim validate` 三态冒烟（clean=0 / broken=1 / usage=2）。

## §4 决策登记（D-P5-01 ~ D-P5-17）

体例沿 P4 §4：每条 = 问题 / 备选 / 选择 / 理由与一致性。决策面 D-A~D-J 全部钉死（任务书要求），映射：D-A→D-P5-01/02、D-B→D-P5-03、D-C→D-P5-04、D-D→D-P5-06、D-E→D-P5-07/08、D-F→D-P5-09/10、D-G→D-P5-16、D-H→D-P5-13、D-I→D-P5-14、D-J→D-P5-15。

### D-P5-01 模块落位（content/ + plugins/ 预留子包，core 零触碰）
- **问题**：P5 十个模块放哪？
- **备选**：(a) 新增顶层子包；(b) 扩入 `core/`；(c) 填 `Spec §5.1` 布局中 `src/engine_v2/` 下已预留的 `content/` 与 `plugins/`（Spec §44:2136-2139/2179-2183；`src/engine_v2/README.md:17,23` 明示 Phase 5 填充）。
- **选择**：(c)。`content/` 7 模块 + `plugins/` 3 模块。
- **理由与一致性**：core 冻结 32 模块 / 308 `__all__`（`test_closeout.py:96-129,226`）——扩 core 须同步 4 个锚点面，违反"锚点零扰动最小化"；预留子包 = Spec 布局 + README 既定语义，G4 门禁 PASS 时该布局已冻结。`modules/` 子包留待 P9（Spec §5.1）。

### D-P5-02 `__init__.py` docstring-only 纪律（骨架测试零改动）
- **问题**：P5 子包 `__init__.py` 是否做 re-export 聚合面？
- **备选**：(a) `from .schemas import *` 聚合导出；(b) 保持 docstring-only（现状 8 行 / 7 行），消费方走子模块路径 import。
- **选择**：(b)。
- **理由与一致性**：`tests/test_engine_v2_skeleton.py:144 test_engine_v2_init_files_are_docstring_only` 逐节点断言 13 子包 + 根 `__init__` docstring-only，豁免集 `_is_core_reexport_node`（:110-136）**仅覆盖 core**——选 (a) 必改骨架测试（锚点外文件，白名单膨胀）。选 (b) = 骨架测试零改动、零新锚点；代价 = import 语句变长（可接受，P4 模块同纪律）。

### D-P5-03 ProjectIR 范围切分（结构全 12 类 + 静态冲突分析限声明域重叠）
- **问题**：Spec §6 要求"project 级 12 类制品 + MUST 含 authority 冲突静态分析"（Spec:460-482），P5 与后续阶段如何切分？
- **备选**：(a) P5 只留 manifest/scenario 薄 IR；(b) P5 结构化承载全部 12 类（typed schema），数据填充由项目方完成；authority 冲突分析限定"声明域重叠"（同一 domain 被 ≥2 条 AuthorityPolicy 声明）层级；(c) P5 连 Prompt 语义也做。
- **选择**：(b)。ProjectIR 16 字段 ↔ 12 类映射（§3.1）；`PromptPolicy` schema 无 authority 字段（K4：prompt 不能定义世界权威，Spec:289-299）。
- **理由与一致性**：(a) 使 P6+ 每阶段各造一套 IR 面，违背单一权威状态（K1）；(c) 超出 P5 任务表（Plan:594-605 无 LLM 内容项）且触碰 K4 边界（G4 §7 移交面 4）。**S2 标记**：Plan §24 S2（:1230-1242）点名 ProjectIR 为待人工裁决面——本决策 = (a) 类"扁平 typed IR"方案先行动工依据，终局裁决推迟至 M3（G6）首个人工门禁（Plan §32：G5 非强制人工门禁）。详见 §10 OI-P5-1。

### D-P5-04 零 v1 兼容（显式格式码，不做自动迁移）
- **问题**：v1 项目文件（`public_start/*.yaml` 等）是否可被 `load_project` 接受？
- **备选**：(a) 双格式自动嗅探；(b) 拒绝 v1 + 显式诊断码引导；(c) 完整 v1→v2 迁移器（Spec §44 `migrations.py`）。
- **选择**：(b)。`detect_v1_shape(raw) = isinstance(raw, dict) ∧ "manifest" not in raw ∧ ("world" in raw or "player" in raw)`（§3.3）→ 恰好 1 条 `LLMSIM_PROJECT_FORMAT_V1`（error），validate 退出码 1。`migrations.py` 推迟（D-P5-DEV-1）。
- **理由与一致性**：迁移器需 v1 全语义面（368 用例域），单列任务超 P5 任务表容量；显式码 = 零猜测、可审计（断言 #16 锁定"恰好 1 条"）。

### D-P5-05 严格度基线（未知键 = error；缺可选目录 = 合法空）
- **问题**：YAML 顶层/节级未知键与缺失目录的处置？
- **备选**：(a) pydantic `extra="allow"` 宽容；(b) 全部 `extra="forbid"`；(c) 顶层 `forbid` + 三个开放 dict 豁免。
- **选择**：(c)。全 schema `extra="forbid"`，豁免 3 处：`ObjectSpec.properties`、`PlayerSpec.capabilities`、`CharacterSpec.personality`（v1 自由 dict 语义面，`condition_eval.py:343-351` 变量解析依赖任意键）。
- **理由与一致性**：(a) 拼写错误静默吞没（Plan §22.3 "duplicated ID" 同族风险）；(b) 卡死 v1 兼容数据形状。缺失可选目录 = 合法空（Spec §5.1 `#optional` 语义；`game.yaml` 必需，Spec §5.1:351-366 首行）。

### D-P5-06 模块图确定性（Kahn + casefold 平手唯一序）
- **问题**：拓扑序在多入度 0 并存时如何选？
- **备选**：(a) 字典序（区分大小写）；(b) casefold 平手打破；(c) 不保证，文档化"任一合法序"。
- **选择**：(b)。Kahn 堆式实现，heap 键 = `id.casefold()`；输出唯一确定序。环 = 空列表 + 每个 SCC 恰好 1 条 `MODULE_CYCLE`（SCC 节点 casefold 排序入 refs）。版本文法 `\d+(\.\d+)*`，点数字串 padding 比较（`2 < 2.1 < 2.1.0` 对齐 v1 `standard.attributes >= 2` 习惯，Spec §41:1970-1987）。
- **理由与一致性**：K7（可调度/可序列化运行时状态，Spec:326-328）要求图计算面可复现；(c) 使断言 #9/#10 不可写。casefold 与 P4 `P4_LLM_PROVIDER_BLACKLIST` casefold 扫描口径同源。

### D-P5-07 插件安全模型（两条显式注册路径 + AST 封闭模式自检）
- **问题**：插件如何被发现？（G5-2/G5-3，Plan:607-614）
- **备选**：(a) `plugins/**/*.py` walk+import 隐式发现；(b) 双路显式：本地 `plugins/<id>/plugin.yaml` manifest（无 manifest = 目录不存在，静默忽略）+ 分发 entry-point 组 `llmsim.plugins`；(c) 仅本地。
- **选择**：(b)，并加机械守卫：`plugins/` 非空 ∧ `pyproject.toml` 缺失 → `LLMSIM_PLUGIN_NO_PYPROJECT`（error）；零 Python 项目（无 `pyproject.toml` ∧ 无 `plugins/`）= 合法完备（Spec §46 MVP 与 §5.1 `#optional` 面；断言 #1/#3）。loader.py + registry.py 源码受 AST 封闭模式扫描（禁 `import_module`/`__import__`/`spec_from_file_location`/`module_from_spec`/`entry.load()` 调用模式，断言 #6）。
- **理由与一致性**：(a) = 任意代码执行面，直接违背 G5-3"不得隐式加载 .py"；(c) 断绝第三方插件分发（Spec §28/§44 面）。

### D-P5-08 entry-point 发现 = metadata-only（零 import）
- **问题**：entry-point 发现时是否 `import` 插件模块？
- **备选**：(a) `entry.load()` 立即导入；(b) 仅读 metadata（`.name/.value/.distribution`），注册 `RegisteredPlugin` 记录，import 留 P6+ runtime；(c) 懒加载包装器。
- **选择**：(b)。`ENGINE_VERSION = "0.5.0"`（P5 钉死单点常量）；manifest `engine_version` 约束不满足 → `LLMSIM_ENGINE_VERSION`（error）；`plugin_descriptors` 声明的插件未注册 → `LLMSIM_PLUGIN_ENTRY_UNRESOLVED`（**warning**，不阻塞 validate）；entrypoint 值文法非法 → `LLMSIM_PLUGIN_ENTRY_INVALID`（error）。
- **理由与一致性**：(a) 在 validate 期执行任意插件代码 = G5-3 违例且 validate 失去纯性；warning 级别因 EP 可来自未安装分布（合法部署形态，断言 #5 用 monkeypatch metadata 证明零 import：`sys.modules` 无插件模块）。

### D-P5-09 DSL 等价（v1 文法原样 + 封闭 23 种 AST + 两阶段求值）
- **问题**：v2 DSL 相对 v1 的语法/求值面如何定？（G5-5）
- **备选**：(a) 自由 re-AST（Python 子集）；(b) v1 文法 1:1（tokenizer 正则逐字符对齐 `condition_eval.py:25-30`），封闭 23 种节点（`DSL_NODE_KINDS`），两阶段：`parse_dsl`（结构，全分支）→ `evaluate_condition`（语义，急停首匹配）；(c) 重写为更严文法。
- **选择**：(b)。函数白名单 `rand/randint/min/max/len`（v1 `condition_eval.py:243-273`）；**无** loop/def/赋值/lambda 产生式（文法层面不存在，机械封闭）；`rand` 族接受注入 `DslRng` Protocol 参数（`rand()/uniform(lo,hi)/randint(lo,hi)`，D-P5-15）。`DslEvalError` 在 evaluate 层抛出；`check_action_feasibility` 层按 v1 `rules.py:102-104` 语义 warn+skip（规则跳过不崩）。
- **理由与一致性**：(a) = G5-5 明禁"重新发明 Python"；(c) 破坏 66 例等价面。两阶段比 v1 eager-skip 更严的披露见 D-P5-DEV-3。

### D-P5-10 内建规则 = 引擎内 handler（非数据 DSL），阈值冻结
- **问题**：v1 `check_action_feasibility` 的 5 条内建规则（`rules.py:146-223`）用数据 DSL 表达还是引擎 handler？
- **备选**：(a) 翻译成 RuleSpec 数据；(b) 引擎内 5 个冻结 handler，ID = v1 `matched_rule` 名（`BUILTIN_RULE_IDS`），`disabled_rules` 按字符串 ID 禁用。
- **选择**：(b)。冻结阈值：strength × 50.0（`rules.py:9`）；`capacity < weight → blocked`、`capacity < weight×1.5 → uncertain prob = max(0.1, min(0.9, capacity/(weight×1.5)))`（:164-187）；lock：`skill < difficulty → uncertain prob = max(0.05, min(0.95, skill/difficulty if difficulty else 0.05))`（:188-206）；body_width：`body > width → blocked` else allowed（:208-223）；blocked_common/extraordinary 走 `_text_matches_rule` 16 键表（:13-30）。
- **理由与一致性**：(a) 不可行——16 关键词子串匹配 + 物理量级判断无法在封闭 23 种 AST 内表达（函数白名单无子串/正则原语）；(b) = v1 行为逐位等价（断言 #11 覆盖）。

### D-P5-11 K8 扫描机制（12 名 casefold 词边界 + split-string 常量 + 项目文件域）
- **问题**：K8（Spec:330-339：项目 MUST NOT pin provider/模型名/endpoint/credential）的机械实现？
- **备选**：(a) schema 层字段禁令 + 全文本扫描；(b) 仅 schema 层；(c) LLM 审查。
- **选择**：(a) 组合面：schema 层 `InferenceCapabilityProfile`/`PromptPolicy` 无 provider/model/endpoint 字段（字段集内省，断言 #19b）；文本层对 `raw.texts`（各 YAML 原文）跑 12 名 casefold `\b` 词边界扫描（与 `test_import_boundary.py:225-240` 黑名单同名单：openai/anthropic/langchain/litellm/ollama/gemini/gpt/claude/llm/provider/api_key/base_url），命中 → `LLMSIM_DEPLOYMENT_FIELD`（error，path=文件，refs=[命中名, 上下文片段]）。常量以串拼接构造（`"prov"+"ider"` 式）使 TestP5Boundary 自扫描 0 命中。扫描域 = **仅项目文件**（引擎自身 `pyproject.toml` 不在域内——引擎 ≠ 项目）。
- **理由与一致性**：(b) 漏 YAML 自由文本（`narrative_style: "ask gpt for help"` 形态）；(c) 不可机械验证。边界语义钉死：`llmsim` 不匹配 `\bllm\b`、`api_key_env` 不匹配 `\bapi_key\b`（`\w` 无边界，测试钉两个负例）。

### D-P5-12 诊断 schema + 排序 + 退出码
- **问题**：诊断输出形态与 CLI 退出语义？
- **备选**：(a) 自由 dict；(b) frozen `Diagnostic{code, severity, path, message, refs}`，`code ∈ DIAGNOSTIC_CODES`（18 枚，§3.1 闭集），确定性排序 `(code, path, message)`；退出码 0=无 error / 1=有 error / 2=用法错；`--json` 时 stdout 纯 JSON（人读输出走 stderr 或省略）。
- **选择**：(b)。
- **理由与一致性**：(a) 使断言 #14（双跑字节级一致）与 #17（形状校验）不可写；退出码三分与 `--json` 纯 stdout = 管道/CI 可消费（断言 #13/#15）。

### D-P5-13 零 Python 参考项目（fixture 即验收物）
- **问题**：G5-1"零插件、零 Python 依赖的项目必须可加载可校验"如何验收？
- **备选**：(a) 文档描述；(b) `tests/fixtures/v2_project_zero_python/` 5 文件 fixture（白名单 #30-34），结构镜像 `public_start/test_empty.yaml`（@5b6837b：world/player/characters/max_ticks 20/ticks_per_game_minute 1/game_time/narrative_style 同形面），`llmsim validate` 退出码 0。
- **选择**：(b)。
- **理由与一致性**：(a) 不可盲审；(b) 断言 #1-#3 直接消费该 fixture，P0-T03 的 v1 最小项目形态成为 v2 基线（格式换代、字段映射见 §7.4）。

### D-P5-14 round-trip 策略（数据级恒等 + 字节稳定双 dump）
- **问题**：IR → YAML → IR 的等价定义？
- **备选**：(a) 字节级恒等（dump 幂等）；(b) 数据级恒等 `load(dump(ir)) == ir` + 双 dump 字节稳定 `dump(dump(ir)) == dump(ir)`；(c) 只测数据级。
- **选择**：(b)。dump 器 = `yaml.safe_dump(sort_keys=True, allow_unicode=True, default_flow_style=False, width=100)`（`canonical_yaml`）。
- **理由与一致性**：(a) 对输入文件原文不成立（注释/序不可恢复）；(c) 漏"序列化面自漂移"风险。断言 #20 双条件。

### D-P5-15 确定性纪律（零非确定根源 + DslRng 注入 + JSON 洁净钩子）
- **问题**：P5 模块的非确定面如何清零？
- **备选**：(a) 文档约束；(b) 机械面：10 模块零 `asyncio/datetime/time/random/network/v1 import/provider 根`（TestP5Boundary AST 扫描，与 P4 M1④ 同机制）；`rand` 族仅经注入 `DslRng` Protocol；`ir_to_data` 出口过 `core.serialization.assert_json_clean`（serialization.py:82）。
- **选择**：(b)。
- **理由与一致性**：K7 可复现面；v1 双非确定根源（`condition_eval.py:3` `import random`、`state_apply.py:101` roll `random.random()`）在 v2 全部改为注入——roll 消费的 0.5 缺省留在 P6 runtime（§7.5 移交注），DSL 层只产概率不掷骰。`pyproject.toml` dependencies 零增删（D-P5-01 冻结面）。

### D-P5-16 CLI 面（console script + 纯函数 main）
- **问题**：`llmsim` 命令的形状？
- **备选**：(a) 多子命令框架（validate/run/migrate）；(b) 仅 `validate` 子命令 + `--json`，`main(argv: Sequence[str]) -> int` 纯函数面（无 `sys.exit` 内嵌，可单测）；console script `llmsim = "src.engine_v2.content.cli:main"`（pyproject `[project.scripts]`，白名单 #11）。
- **选择**：(b)。usage 错 → 2；validate 有 error → 1；clean → 0。
- **理由与一致性**：(a) run/migrate 属 P6+/D-P5-04 推迟面，空壳子命令 = 死代码面；(b) 断言 #13/#15 可单测无子进程依赖（console script 存在性由 W6 gate ⑥ 冒烟）。

### D-P5-17 锚点与白名单策略（唯一锚点变更文件 + 39 文件封闭集）
- **问题**：P5 对既有锚点文件动几处？门禁如何判"零越界"？
- **备选**：(a) 各锚点文件分别扩 P5 块；(b) 仅 `tests/engine_v2/core/test_import_boundary.py` 纯追加（L240 后插 `P5_SUBMODULES`/`P5_TEST_FILES` + 尾追 `TestP5Boundary`）；(c) 新文件承载 P5 边界测试。
- **选择**：(b) + 39 文件封闭白名单（§3.12，代码区域 `-- src tests pyproject.toml`）；门禁跑 `git diff --name-only e5c4db4..HEAD -- src tests pyproject.toml` == 白名单（多一少一皆失败）。
- **理由与一致性**：(a) 扰动 `test_closeout.py`/骨架测试 = 32/308 算术面与 docstring-only 断言面风险；(c) 与 P4 `TestP4Boundary` 体例断裂（同文件内 P4/P5 块并列 = 演进史可读）。12 名黑名单扫描对 P5 新文件自动生效（P5 模块零 provider 词面，D-P5-15 保证 0 命中）。

---

## §5 G5 门禁场景（S-steps + 编号断言）

### 5.1 场景步（S0~S9）

| 步 | 场景 | 输入 | 预期 |
|---|---|---|---|
| S0 | 工作区基线 | 冻结 HEAD `e5c4db4` 全绿（2399 passed / ruff clean） | 测试套件可重复跑 |
| S1 | 零 Python 项目加载 | fixture `v2_project_zero_python/`（5 文件，#30-34） | `load_project` 成功；`validate` 退出码 0 |
| S2 | 本地插件项目 | fixture `v2_plugin_local/`（#35-37） | 注册 `infection`（LOCAL_MANIFEST）；validate 0（entrypoint 未注册仅当声明了才 warning） |
| S3 | entry-point 发现 | monkeypatch `importlib.metadata.entry_points`（假 EP 组） | 注册 ENTRY_POINT 源；`sys.modules` 无插件模块 |
| S4 | 坏项目 | fixture `v2_project_broken/`（#38-39）+ K8 探针文本 | 全诊断集非空、形状合法、排序确定、退出码 1 |
| S5 | 模块图对抗 | 3 环 A→B→C→A、钻石图、缺 requires、版本不满足 | 断言 #9/#10/#18 |
| S6 | DSL 等价 | 66 例转录集（§6.2）+ AST 封闭对抗（#13 例 while/def/lambda） | 断言 #11/#12 |
| S7 | CLI 面 | `--json` 双跑（clean / broken / usage 错） | 断言 #13/#14/#15 |
| S8 | v1 文件拒收 | `public_start/test_empty.yaml`（只读） | 断言 #16 |
| S9 | 白名单与锚点回归 | `git diff --name-only e5c4db4..HEAD -- src tests pyproject.toml` + 全测试套件 | == 39 白名单（代码区）；TestB1/B3/P4/skeleton 全绿 |

### 5.2 编号断言（20 条；G5 条款映射：#1-3,16→G5-1；#4,5,8→G5-2；#6,7→G5-3；#9,10,18→G5-4；#11,12→G5-5；#13-15,17→G5-6；#19→K8/不变量；#20→K7/不变量）

| # | 断言 | G5 |
|---|---|---|
| 1 | `load_project(zero_python_fixture)` 成功且诊断集中 `LLMSIM_FILE_MISSING` 计数 = 0（5 文件全命中模板，可选目录缺席零诊断） | G5-1 |
| 2 | 同一 fixture 全链路 `validate_project` 返回诊断集 = ∅，`main(["validate", path]) == 0` | G5-1 |
| 3 | 零 Python 项目（无 `pyproject.toml` ∧ 无 `plugins/`）validate 中 plugin 族诊断（`LLMSIM_PLUGIN_*` 6 码）计数 = 0 | G5-1 |
| 4 | `discover_local_plugins`：合法 `plugins/<id>/plugin.yaml` → `RegisteredPlugin(source=LOCAL_MANIFEST, origin="plugins/<id>/plugin.yaml")`；无 manifest 的 `plugins/<x>/` 目录 → 零注册零诊断（静默忽略） | G5-2 |
| 5 | monkeypatch entry-point 后 `discover_entry_point_plugins` 产出 `RegisteredPlugin(source=ENTRY_POINT)`，且 `sys.modules` 中无该 EP 模块名（metadata-only 证明）；EP 值非法 → `LLMSIM_PLUGIN_ENTRY_INVALID` | G5-2 |
| 6 | AST 封闭模式扫描 `content/loader.py` + `plugins/registry.py` 源码 AST：无 `importlib.import_module`/`__import__`/`importlib.util.spec_from_file_location`/`importlib.util.module_from_spec` 调用节点、无 `entry.load()` 属性调用模式（白名单 #6/#7 族） | G5-3 |
| 7 | 对抗：`plugins/rogue/plugin_impl.py`（无 manifest）项目 → validate 零插件诊断 ∧ `sys.modules` 无 `rogue` 模块（walk+import 不存在于代码面，断言 #6 静态 + 本条动态双证） | G5-3 |
| 8 | `plugins/` 非空 ∧ `pyproject.toml` 缺失 → 恰好 1 条 `LLMSIM_PLUGIN_NO_PYPROJECT`（path="pyproject.toml"） | G5-2 |
| 9 | 模块图 A→B→C→A：`topological_order == []` ∧ 恰好 1 条 `MODULE_CYCLE`，其 refs = casefold 排序节点集（轮换归一：`[a,b,c]` 唯一形态，断言不依赖入边起点） | G5-4 |
| 10 | 钻石图（A→{B,C}→D，全 requires 声明）：`topological_order` 与冻结期望序列逐位相等（casefold 平手打破的确定性锁定） | G5-4 |
| 11 | 66 例 v1 等价集（§6.2）：对每例，v1 期望（feasibility, probability, 异常族, matched_rule 名）与 v2 `check_action_feasibility`/`evaluate_condition` 输出逐位一致（float `==`；v1 异常类型 → v2 `DslEvalError`/诊断码映射表内） | G5-5 |
| 12 | AST 封闭性：对合法 DSL 语料，所有节点 `kind ∈ DSL_NODE_KINDS`（23 枚闭集）；`while (x) {...}`、`def f(): ...`、`lambda x: x` 输入 → `parse_dsl` 产 `LLMSIM_DSL_PARSE`（`DSL_NODE_KINDS` 中不存在任何 loop/def/lambda 种类——文法封闭，非运行时拒绝） | G5-5 |
| 13 | `main(["validate", path, "--json"])`：stdout 可被 `json.loads` 且键集 = `{project, diagnostics, exit_code}`（封闭形状）；broken 项目 exit_code=1 且进程退出码=1 | G5-6 |
| 14 | 同一 broken 项目双跑 `--json`：两次 stdout 字节级相等 ∧ 诊断集按 `(code, path, message)` 字典序（排序器 = `sorted(key=lambda d: (d.code, d.path, d.message))`） | G5-6 |
| 15 | 退出码三态：clean fixture → 0；broken fixture → 1；`main([])` / `main(["frobnicate"])` → 2（usage） | G5-6 |
| 16 | v1 文件 `public_start/test_empty.yaml`（只读，零修改）→ validate 诊断集中 `LLMSIM_PROJECT_FORMAT_V1` 计数 = 1（恰好），其余码 0 | G5-1 |
| 17 | broken fixture 全诊断集逐条形状校验：`code ∈ DIAGNOSTIC_CODES`（18 枚闭集）∧ `severity ∈ {error, warning}` ∧ `path` 非空 ∧ `message` 非空（`Diagnostic` 构造期 invariant 的出口复证） | G5-6 |
| 18 | 模块 requires 缺失：B requires A 但 A 未声明 → 恰好 1 条 `LLMSIM_MODULE_REQUIRES_MISSING`，path = 需求方 B 的模块文件，refs 含缺失模块名 | G5-4 |
| 19 | K8 双证：(a) 项目 YAML 含 `api_key: "sk-test"` → `LLMSIM_DEPLOYMENT_FIELD`（refs 含 `api_key`）；`model: "x"` 字段 → 同码命中（`model` 属 12 名族经 `\b` 边界：`model` 单独不命中，命中来自字段名 `model_name`/值形态——断言以 §3.6 探针表为准，含 `llmsim`/`api_key_env` 两个必不命中负例）；(b) `InferenceCapabilityProfile`/`PromptPolicy` 字段集内省：无 `provider`/`model`/`base_url`/`api_key` 任何形态字段名 | K8 |
| 20 | round-trip：对 zero_python 与 plugin fixture 的 IR，`canonical_yaml(ir_to_data(ir2)) == canonical_yaml(ir_to_data(ir))` 且 `ir2 == ir`（`load_project(dump 后文件) == load_project(原文件)` 数据级恒等） | K7 |

### 5.3 不得（门禁期硬约束）

1. 不得 import 或修改 `src/engine_v2/core/` 任何文件（白名单外）。
2. 不得修改 `tests/test_engine_v2_skeleton.py`、`tests/engine_v2/core/test_closeout.py`、`src/engine_v2/{content,plugins}/__init__.py`、`src/engine_v2/README.md`。
3. 不得新增 `pyproject.toml` dependencies（D-P5-15 冻结面）。
4. 不得在 P5 任何模块出现 walk/glob-`.py`-then-import 模式（D-P5-07 机械面，断言 #6）。
5. 不得 import v1 `src/game/`/`src/config/`/`src/agents/` 任何模块（P5-INV-15）。
6. 不得使用 `asyncio`/`datetime`/`time`/`random` 模块（D-P5-15；`random` 语义一律经 `DslRng` 注入）。
7. 不得出现真实 LLM 客户端代码或网络调用（provider 根 12 名 + 网络库，TestP5Boundary 扫描）。
8. 不得在 `pyproject.toml` 插入 `[project.scripts]` 以外的任何段变更。
9. 不得修改 `tests/fixtures/` 以外已存在的任何 fixture/项目文件（`public_start/` 只读）。

## §6 测试规范

### 6.1 模块单测映射

| 测试文件 | 被测模块 | 用例族（最少覆盖） |
|---|---|---|
| `content/test_schemas.py` | §3.1 | 25 导出逐一构造；`DIAGNOSTIC_CODES` 18 枚闭集核验（集合相等）；`Diagnostic` 非法 code 构造期拒绝；每模型 `extra="forbid"` 未知键 → `ValidationError`（每模型 ≥1 例）；3 个开放 dict 豁免各 ≥1 例；`ProjectManifest` 字段闭集；`ProjectIR` 16 字段默认值面 |
| `content/test_project_ir.py` | §3.2 | `build_ir` 全 fixture raw → IR 16 字段填充断言；`flatten_entities` 序（casefold 稳定）；`iter_entity_refs` 全引用类；`ir_to_data` → `assert_json_clean` 通过；`canonical_yaml` 双 dump 字节稳定；`IRBuildResult` 诊断聚合 |
| `content/test_loader.py` | §3.3 | `LAYOUT_REQUIRED`/`LAYOUT_OPTIONAL` 模板闭集；`load_project` 6 步：缺 `game.yaml` → `LLMSIM_FILE_MISSING`；缺可选目录 → 零诊断；`RawProject.texts` 保留原文（K8 面）；`read_yaml_file` 非 dict 顶层 → `LLMSIM_SCHEMA`；`detect_v1_shape` 真值表（v1 文件真、v2 文件假、非 dict 假、空 dict 假） |
| `content/test_module_graph.py` | §3.4 | `parse_requirement` 文法全族（含非法）；钻石图拓扑精确序列（断言 #10 同源数据）；3 环 → `[]` + 恰好 1 条 `MODULE_CYCLE`（#9）；requires 缺失 → `LLMSIM_MODULE_REQUIRES_MISSING`（#18）；版本比较矩阵（`2`/`2.1`/`2.1.0`/`>=2`/`<3`）；`conflicts` 双向命中 1 条 |
| `content/test_rule_dsl_parity.py` | §3.5 | **66 例 1:1 转录**（§6.2），无新增无删减，函数名与 v1 同名 |
| `content/test_rule_module.py` | §3.5（v2 面） | AST 封闭：23 种类逐一可产出 + `while/def/lambda` → `LLMSIM_DSL_PARSE`（#12）；两阶段：未达分支含垃圾 → `parse_dsl` 结构错（DEV-3 披露点，每例 docstring 标注）；`DslRng` 注入：同种子同值 + 区间断言；`resolve_variable` 查找序负例（显式 `None` = 缺失 → `DslEvalError`）；`action_text` 四键 join；`resolve_target` 三序（id → name → object_id-in-text）；custom 规则流：regex+condition 双命中、优先级（custom > builtin）、`disabled_rules` 禁用、非法 condition warn+skip（`matched_rule=None` 不崩）；`BUILTIN_RULE_IDS` 与 v1 5 名逐字相等 |
| `content/test_validator.py` | §3.6 | 18 码路径覆盖矩阵（每码 ≥1 触发例 + 1 不触发例）；`sort_diagnostics` 排序器锁定；authority 声明域重叠 → `LLMSIM_AUTHORITY_CONFLICT`（重叠 1 条，非笛卡尔积）；K8 探针表（含 `llmsim`/`api_key_env` 负例，#19a）；`InferenceCapabilityProfile`/`PromptPolicy` 字段集内省（#19b） |
| `content/test_cli.py` | §3.7 | 退出码三态（#15）；`--json` stdout 纯 JSON + 键集封闭（#13）；双跑字节相等（#14）；usage=2；`run_validate` 无 `sys.exit` 面（返回 int 可单测） |
| `content/test_p5_gate_scenario.py` | §5 全 | `test_assert_01`…`test_assert_20` 与 §5.2 一一对应（S0-S9 步为 fixture/setup） |
| `content/test_p5_adversarial.py` | Plan §22.3 | A1-A13（§6.3） |
| `content/test_p5_integration.py` | 全链 | load→build_ir→validate→`main` 两 fixture 端到端；round-trip（#20）；gate 运行序 ⑥ 冒烟等价（子进程 `llmsim validate` 三态） |
| `plugins/test_manifest.py` | §3.8 | `parse_plugin_manifest` 全字段；id pattern 边界（64/65 字符）；entrypoint 文法（恰一个 `:`）；缺 id/version/entrypoint 各 1 例 |
| `plugins/test_registry.py` | §3.10 | `discover_local_plugins`：合法/无 manifest 目录静默/非法 manifest 跳过/重复 id 后者胜（#4）；`discover_entry_point_plugins` monkeypatch `importlib.metadata.entry_points`（#5 含 `sys.modules` 无插件模块证明）；`validate_plugins`：`LLMSIM_PLUGIN_NO_PYPROJECT`（#8）/`LLMSIM_ENGINE_VERSION`/`LLMSIM_PLUGIN_ENTRY_UNRESOLVED`（warning 级断言） |

### 6.2 等价转录方法（66 例，G5-5 机械面）

**方法**：`tests/test_condition_eval.py`（41 例）与 `tests/test_rules.py`（25 例，含 `TestTextMatchesRule` 类 5 方法）逐例 1:1 转录至 `tests/engine_v2/content/test_rule_dsl_parity.py`，**函数名不变**（v1 名 = v2 名），v1 import 换 v2（`evaluate_condition`/`check_action_feasibility` 同名面），context 构造从 v1 `_context()`/`_test_state()`（tests/test_condition_eval.py:6-29）映射为 `DslContext` + `ActionInput`。转录文件 docstring 内置 66 行映射表（v1 文件:行号 → v2 期望 → 转录备注），盲审逐行可核。

**v1 名单（转录源，@ 冻结 HEAD 核验）**：
- `test_condition_eval.py`（41）：`test_simple_comparison_returns_blocked`(L32)、`test_ifelse_chain_returns_uncertain_with_probability`(L39)、`test_arithmetic_and_target_weight_alias`(L46)、`test_parentheses_and_precedence`(L52)、`test_min_max_functions`(L58)、`test_skill_level_lookup`(L64)、`test_missing_variable_raises`(L71)、`test_division_by_zero_raises`(L76)、`test_invalid_syntax_raises`(L81)、`test_invalid_outcome_raises`(L86)、`test_uncertain_without_probability_defaults_to_half`(L91)、`test_and_operator`(L132)、`test_and_operator_false`(L139)、`test_or_operator`(L146)、`test_not_operator`(L153)、`test_compound_boolean`(L160)、`test_in_operator`(L170)、`test_in_operator_false`(L177)、`test_not_in_operator`(L184)、`test_subset_operator`(L191)、`test_subset_operator_true`(L199)、`test_intersects_operator`(L212)、`test_intersects_operator_true`(L220)、`test_disjoint_operator`(L227)、`test_contains_operator`(L235)、`test_len_function`(L245)、`test_string_comparison_equals`(L255)、`test_string_comparison_not_equals`(L262)、`test_nested_if_as_branch_value`(L272)、`test_nested_if_as_branch_value_matched`(L279)、`test_nested_if_as_default`(L286)、`test_nested_if_deep`(L293)、`test_set_and_bool_combined`(L305)、`test_boolean_with_set`(L313)、`test_in_with_nonlist_rhs_raises`(L324)、`test_subset_with_string_raises`(L329)、`test_len_on_number_raises`(L334)、`test_rand_comparison`(L342)、`test_rand_range_comparison`(L349)、`test_randint_comparison`(L356)、`test_rand_with_boolean_input`(L363)
- `test_rules.py`（25）：`test_strength_rule_blocks_heavy_table`(L44)、`test_lock_rule_returns_uncertain_probability`(L57)、`test_no_rule_returns_none`(L72)、`test_body_width_blocks_fat_player_thin_passage`(L84)、`test_body_width_allows_thin_player_slim_passage`(L99)、`test_extraordinary_action_allows_superhuman`(L113)、`test_blocked_common_action_blocks_player`(L128)、`test_skill_vs_lock_allows_high_skill`(L144)、`test_strength_rule_uncertain_when_close`(L158)、`test_world_rules_with_no_deterministic_key_are_noop`(L184)、`test_custom_regex_blocked_takes_priority_over_extraordinary`(L196)、`test_custom_regex_allowed_takes_priority_over_blocked_common`(L220)、`test_custom_condition_blocks_action`(L244)、`test_custom_condition_returns_uncertain_probability`(L267)、`test_custom_match_action_plus_condition_requires_both`(L290)、`test_disable_strength_rule`(L320)、`test_disable_body_width_rule`(L331)、`test_invalid_regex_is_skipped_and_builtin_rules_continue`(L343)、`test_invalid_condition_is_skipped_and_builtin_rules_continue`(L360)、`test_first_matching_custom_rule_wins`(L376)、`TestTextMatchesRule.test_exact_match`(L394)、`test_substring_match`(L397)、`test_comma_separated_keywords`(L400)、`test_no_match`(L403)、`test_empty_inputs`(L406)

**rand 族处置（4 例）**：v1 期望值由 `_random`（condition_eval.py:3）非确定产生，原断言为区间/形状。v2 转录时注入种子化 `DslRng`（conftest `seeded_rng`）：区间断言保留 + 同种子精确值断言新增（v2 确定性是 v1 的**严格增强**，不弱化原断言——等价方向单向：v1 通过 ⟹ v2 通过）。

**异常映射表**（docstring 内置）：v1 `ConditionEvalError`（解析类：语法/非法输出/未定义变量/除零/集合类型错）⟺ v2 `parse_dsl` 产 `LLMSIM_DSL_PARSE`（结构性）或 `evaluate_condition` 抛 `DslEvalError`（语义性：未定义变量、除零、`_to_set` 类型错）；`test_rules.py` 中 v1 `logger.warning`+skip 形态 ⟺ v2 同层 warn+skip（`caplog` 断言 + 规则跳过）。

**DEV-3 披露义务**：若任一例属"matched 分支后含垃圾"形态（v1 `_skip_until_if_end` condition_eval.py:331-340 容忍），v2 `parse_dsl` 将产 `LLMSIM_DSL_PARSE`——转录者**必须先运行 v1 用例**（P0-T03 基线 368 全绿可复现）确认行为再转录，并在映射表该例标注 `DEV-3` 及 v1 行为描述。执行前静态预判：66 例中 if-chain 用例（L39/L272-293 族）需逐一核对其 else 分支后是否有尾随内容。

**等价判定**：`(feasibility, probability)` 逐位相等（float `==`）；`check_action_feasibility` 结果五键（feasibility/feasibility_reason/success_probability/requires_roll/matched_rule，rules.py:78-91）逐字段相等；无匹配 → `None` 语义保持（v2 返回 `None`，v2 `FeasibilityResult` 不用于无匹配路径）。

### 6.3 对抗表（A1-A13，Plan §22.3 L975-990 逐项）

| # | Plan §22.3 项 | v2 落面 | 期望 | 测试 |
|---|---|---|---|---|
| A1 | duplicated ID | `check_duplicate_ids` | 每重复 id 恰好 1 条 `LLMSIM_DUPLICATE_ID`（path=文件，refs=[id, 首次位置, 重复位置]） | test_p5_adversarial + fixture #39 |
| A2 | missing entity | `check_references` | 悬空引用（connection→不存在 location；inventory→不存在 object）→ `LLMSIM_UNRESOLVED_REF` 每条 1 | 同 |
| A3 | stale revision | 模块 requires 版本 > 目标声明版本 | `LLMSIM_MODULE_VERSION`（需求方 path） | 同 |
| A4 | conflicting effects | 两条 `AuthorityPolicy` 声明域重叠；模块 `conflicts` 互指 | `LLMSIM_AUTHORITY_CONFLICT` 1 条（声明域重叠级，D-P5-03）+ `LLMSIM_MODULE_CONFLICT` 1 条 | 同 |
| A5 | circular module dependency | `find_cycles` | 断言 #9（恰好 1 条 `MODULE_CYCLE`） | 同 + #9 |
| A6 | event loop | — | **N/A（P5 无事件面；事件循环归 P6 runtime）**——P5 面零事件概念，无落点可对抗；记录于 §10 | 无 |
| A7 | invalid mode merge | `GameplayModeSpec` 封闭字段 + 合并语义面 | 非法 mode 合并字段 → `LLMSIM_SCHEMA`（pydantic 层） | test_rule_module 外置 → test_validator |
| A8 | non-checkpointable backend branch | — | **N/A（P8 状态快照面）**；P5 侧镜像保证：`ProjectIR` 全数据态、`assert_json_clean` 可序列化（构造上 checkpointable） | test_project_ir |
| A9 | out-of-order async result | — | **N/A（D-P5-15：P5 零 asyncio，无 async 结果可乱序）** | 无（TestP5Boundary 静态面覆盖） |
| A10 | unauthorized context access | DSL 未定义变量 | `evaluate_condition` 抛 `DslEvalError`（v1 condition_eval.py:247 等价）；`check_action_feasibility` 层 warn+skip 不崩（v1 rules.py:102-104） | test_p5_adversarial |
| A11 | rogue .py in plugins/（无 manifest） | loader 模板 + 发现函数 | 零诊断、零注册、`sys.modules` 无该模块 | 断言 #7 |
| A12 | api_key in project YAML | K8 扫描 | `LLMSIM_DEPLOYMENT_FIELD`（refs 含 `api_key`） | 断言 #19a + fixture #38 |
| A13 | DSL 含 def/while | `parse_dsl` | `LLMSIM_DSL_PARSE`（AST 无对应种类，#12 同源语料扩展） | test_p5_adversarial |

### 6.4 `TestP5Boundary` 规格（`test_import_boundary.py` 追加块，5 方法）

扫描面 = `P5_SUBMODULES`（10 茎 → `src/engine_v2/content/`+`src/engine_v2/plugins/` 实际 .py 文件集）∪ `P5_TEST_FILES`（15）；既有辅助（`_collect_absolute_imports` L246、`_blacklist_category` L263、12 名常量 L225-240）直接复用，P5 专属常量仅 2 个（§3.11）。

| 方法 | 断言 |
|---|---|
| `test_p5_file_set` | 实际文件集（路径扫描）== `P5_SUBMODULES`∪`{__init__.py}×2` 与 `P5_TEST_FILES` 闭包（TestB1 L318-322 同型）——白名单代码面的测试内镜像 |
| `test_p5_12_name_blacklist` | 12 名 casefold `\b` 词边界扫描全部 P5 src+test 文件 → 0 命中（常量以串拼接构造自豁免，P4 先例）；负例锚：`llmsim`/`api_key_env` 不命中（`\w` 边界语义钉死） |
| `test_p5_forbidden_roots` | 绝对 import 扫描：provider 根集（L98-151 同常量）∪ 网络库根（`httpx`/`requests`/`socket`/`urllib` 族）→ 0 命中 |
| `test_p5_ast_nondeterminism` | AST 扫描 10 个 src 模块：`time`/`random`/`datetime`/`asyncio` import 或属性调用 → 0 命中；`content/loader.py`+`plugins/registry.py` 封闭模式（`import_module`/`__import__`/`spec_from_file_location`/`module_from_spec`/`entry.load()`）→ 0 命中（断言 #6 的测试内实现） |
| `test_p5_no_v1_imports` | `src.game.*`/`src.config.*`/`src.agents.*` 绝对 import → 0 命中（P5-INV-15 机械面） |

### 6.5 CLI 测试

`test_cli.py`（单元，无子进程）+ `test_p5_integration.py`（子进程冒烟：`[sys.executable, "-m", "src.engine_v2.content.cli", ...]` 三态退出码——console script 装配等价面）+ W6 gate 运行序 ⑥（真实 `llmsim` 命令，依赖 `.venv` 已 pip install -e 或 PATH 注入；若环境未装 console script，冒烟降级为 `-m` 面并在 gate 报告披露）。

---

## §7 映射表

### 7.1 G5 条款 → 实现 → 决策 → 断言 → 测试

| G5（Plan:607-614 逐字） | 实现 | 决策 | 断言 | 测试文件 |
|---|---|---|---|---|
| 零 Python 项目可以 load + validate | `load_project`（§3.3）+ fixture #30-34 + `validate_project` | D-P5-13/04/05 | #1,#2,#3,#16 | test_loader, test_p5_gate_scenario |
| Python plugin 必须显式注册 | `discover_local_plugins`+`discover_entry_point_plugins`（§3.10）+ manifest 文法（§3.8） | D-P5-07/08 | #4,#5,#8 | test_manifest, test_registry, test_p5_gate_scenario |
| 不允许目录自动扫描执行任意 Python | AST 封闭模式（§3.10 机械面）+ 无 manifest 静默 | D-P5-07 | #6,#7 | test_p5_gate_scenario, TestP5Boundary |
| module dependency cycle 可诊断 | `find_cycles`（SCC 粒度 1 条）+ `topological_order`（§3.4） | D-P5-06 | #9,#10,#18 | test_module_graph, test_p5_gate_scenario |
| DSL 支持已有简单规则，不引入 loop/function-definition | 66 例等价集 + 封闭 23 种 AST + 两阶段（§3.5） | D-P5-09/10 | #11,#12 | test_rule_dsl_parity, test_rule_module |
| validator 返回 machine-readable diagnostics | `Diagnostic` 闭集 18 码 + 排序 + `--json` 纯 stdout + 退出码（§3.6/3.7） | D-P5-12/16 | #13,#14,#15,#17 | test_validator, test_cli, test_p5_gate_scenario |

### 7.2 Spec 章节 → P5 落点

| Spec 章节 | 落点 |
|---|---|
| §3.1 项目定义（L172-190） | `ProjectIR`/`ProjectManifest`（§3.1） |
| §4 K1-K8（L242-339） | §2 机械镜像表（P5-INV-1..8）；K8 → §3.6 双证（#19） |
| §5.1 项目布局（L351-366） | `LAYOUT_REQUIRED`/`LAYOUT_OPTIONAL` 闭模板（§3.3）+ fixture #30-34 |
| §6 项目制品 12 类 + MUST（L460-482） | `ProjectIR` 16 字段 ↔ 12 类（§3.1）；authority 冲突静态分析 = 声明域重叠级（D-P5-03） |
| §26 简单随机（L1470-1478） | `DslRng` Protocol 注入（§3.5，D-P5-15） |
| §28 插件 manifest（L1516-1545） | §3.8-§3.10 全节；entrypoint 例 `my_game.systems.infection:InfectionSystem`（L1526）文法源 |
| §29 `llmsim add`（L1547-1568） | **P5 不做**（D-P5-16：CLI 仅 `validate`）；add 归后续任务包 |
| §40 13 标准模块（L1944-1966） | `ModuleGraphNode` 数据面（§3.1/3.4）——标准模块**实现**归 P9 |
| §41 模块依赖例（L1970-1987） | 版本文法 + `standard.attributes >= 2` 解析例（test_module_graph） |
| §44 文件清单（L2136-2183） | D-P5-DEV-2（content/ 7 模块 vs 建议 4 文件）；`migrations.py` 推迟 D-P5-DEV-1 |
| §46 MVP（L2294-2296）+ 插件沙箱推迟（L2305） | 零 Python 参考（D-P5-13）；沙箱不在 P5（双路显式注册即当前安全面，D-P5-07） |
| §47 Phase 5 = Dynamics（L2401-2415） | OI-P5-2（编号分歧事实，Plan §14 为执行 SOT） |

### 7.3 Plan T01-T10 → 文件 → 波次（Plan:594-605 任务表逐行）

| 任务（Plan 原表） | 产出文件 | 波次 |
|---|---|---|
| P5-T01 Project Format v2 repo-wide schema survey（GFlash） | **本文档**（§1.3 基线 + §7.4 v1 语义映射 = survey 交付物；无代码文件，不占白名单） | W0（设计期完成） |
| P5-T02 ProjectIR schema + compiler（QMax） | `content/schemas.py`（W1）+ `content/project_ir.py`（W2）+ 对应 2 单测 | W1/W2 |
| P5-T03 YAML/file-group v2 loader（Q27） | `content/loader.py` + `content/conftest.py` + `test_loader.py` | W2 |
| P5-T04 Module manifest + dependency graph（Q27） | `content/module_graph.py` + `test_module_graph.py` | W3 |
| P5-T05 local explicit plugin manifest loader（Q27） | `plugins/manifest.py` + `plugins/test_manifest.py` | W5 |
| P5-T06 Python package entry-point plugin loader（Q27） | `plugins/registry.py`（EP 面）+ `plugins/api.py` + `plugins/test_registry.py` + `plugins/conftest.py` + `plugins/__init__.py` | W5 |
| P5-T07 现有 condition/rule DSL 封装为标准 Rule module（GFlash） | `content/rule_module.py` + `test_rule_dsl_parity.py` + `test_rule_module.py` | W4（单独串行） |
| P5-T08 YAML round-trip-safe 策略 / loader tests（Q27） | `canonical_yaml`（§3.2，实现随 W1/W2）+ `test_p5_integration.py`（round-trip #20） | W2 实现 / W6 测试 |
| P5-T09 `llmsim validate --json` 初版（Q27） | `content/validator.py` + `content/cli.py` + `pyproject.toml [project.scripts]` + `test_validator.py` + `test_cli.py` | W6 |
| P5-T10 simple zero-Python reference project（Q27） | fixture #30-34（`v2_project_zero_python/`）+ `test_p5_gate_scenario.py`（S1 步） | W6 |
| （P5 门禁面）gate/对抗/锚点同步 | `test_p5_gate_scenario.py` + `test_p5_adversarial.py` + fixture #35-39 + `test_import_boundary.py` P5 块 | W6（末段串行） |

### 7.4 v1 语义 → v2 落点（T01 survey 核心表）

| v1 面（文件 @ 提交） | v2 落点 |
|---|---|
| `public_start/test_empty.yaml`（@5b6837b）顶层 `world/player/characters/max_ticks/game_time/ticks_per_game_minute/narrative_style` | fixture #30-34 的 `game.yaml`+分节文件：`manifest`（id/version 新增）+ `scenario`（max_ticks/game_time/ticks_per_game_minute/narrative_style 入 `ScenarioSpec`）+ `world/characters/items` 分文件；`player` 入 `PlayerSpec`（§3.1） |
| `src/config/loader.py` `_load_yaml`/`model_validate`（:42-46） | `loader.read_yaml_file`（`yaml.safe_load` 同底层）+ pydantic `model_validate` 同模式 |
| `condition_eval.py` tokenizer 正则（:25-30）/ 文法产生式（:35-340） | `tokenize_dsl` 正则逐字符对齐 + 23 种 AST（§3.5）；`and/or/not` 在 v1 关键字表（:66）内 → v2 同 |
| `condition_eval.py` 函数族 `rand/randint/min/max/len`（:243-273） | 同白名单 + `DslRng` 注入（唯一语义差：确定性） |
| `deterministic_rules.py` `DeterministicRule`（:11-18）+ 解析（:71-119） | `RuleSpec`（§3.1）；warnings-not-exceptions 口径保留（非法规则 = warning 诊断 + 跳过） |
| `rules.py` 5 内建规则（:146-223）+ `_text_matches_rule` 16 键表（:13-30） | 引擎内 5 handler（D-P5-10）+ `BUILTIN_RULE_IDS` 逐字对齐 |
| `state_apply.py` roll `or 0.5`（:97）+ `random.random()`（:101） | **P6 移交**：DSL 层 `uncertain` 缺省 0.5 保留（condition_eval.py:294 等价）；roll 掷骰 + 缺省归 P6 runtime（§7.5） |
| v1 `world_rules` 自由键（whisperheads/murder 形态） | `rules/` 目录 `RuleSpec` 列表（D-P5-05 严格化：未知键 error） |
| `src/agents/init.py` `load_init_file(_set)`（:125-128/:355-365） | v2 项目 init 文件加载归 P6+（P5 仅 `LAYOUT_OPTIONAL` 预留位）——**不占白名单** |

### 7.5 移交与分歧注记

1. **阶段编号分歧**：Spec §47（L2401-2415）"Phase 5 = Dynamics" vs Plan §14（L586-616）"Phase 5 = Project Format"——以 Plan 为执行 SOT（G4 报告 §8 同口径），Spec §47 为设计文档内部编号。OI-P5-2。
2. **roll 消费面**：`success_probability` 缺省 0.5（state_apply.py:97）与 `random.random()`（:101）两处非确定/缺省行为归 P6 runtime 接线；P5 保证 DSL 层产出的 `FeasibilityResult.success_probability` 与 v1 `rule_result` 五键逐位一致，使 P6 消费面无语义差。
3. **G4 移交 4 项承接**：① 协议缝 P5 不触碰（§2 P5-INV-1）；② `scheduler_fingerprint` 输入面 = 维持披露分支（D-P5-DEV-4）；③ policy 内容重提案 + ④ LLM 策略内容层 = OI-P5-3 待 Leader 裁决（D-P5-DEV-5），P5 模块自身零 LLM 面（K8 机械保证）。
4. **`llmsim add`**（Spec §29）不在 P5 CLI（D-P5-16）；未来任务包承接时以本文档 `Diagnostic`/`ProjectIR` 面为输入。

---

## §8 自检与偏差登记

### 8.1 K1-K8 → P5 机械验证手段矩阵

| 不变量 | P5 机械面 | 验证 |
|---|---|---|
| K1 单一权威状态 | `ProjectIR` = 唯一 typed 项目态；`RawProject` 只读输入面 | test_project_ir（16 字段单一来源） |
| K2 无直接状态写 | P5 无状态写面（纯函数：load/parse/build/validate 全返回新值） | TestP5Boundary（零可变全局面） |
| K3 Authority-Commit 分离 | `AuthorityPolicy` 仅声明面，无执行字段 | test_schemas 字段集断言 |
| K4 Prompt 不定义权威 | `PromptPolicy` schema 无 authority 字段（#19b 内证） | 字段集内省 |
| K5 Agent = Policy | P5 无 Agent 面；`InferenceCapabilityProfile` 仅能力描述（无模型名字段，#19b） | 字段集内省 |
| K6 事件可追溯 | P5 无事件面（N/A，P6+） | — |
| K7 可调度/可序列化 | `assert_json_clean`（`ir_to_data` 出口）+ round-trip #20 + 拓扑确定性 #10 | test_project_ir, test_p5_integration |
| K8 项目不 pin 部署 | 12 名 `\b` 扫描 + schema 字段双证（#19） | test_validator, test_cli |

### 8.2 导出台账（10 模块 116 名，与 §3 逐模块 `__all__` 表逐名一致）

| 模块 | 导出数 | 名单 |
|---|---|---|
| content/schemas.py | 25 | DIAGNOSTIC_CODES, RawProject, ProjectManifest, ProjectIR, WorldSpec, EnvironmentSpec, LocationSpec, ObjectSpec, PositionSpec, AttributeSpec, PlayerSpec, CharacterSpec, ComponentSchema, ComponentField, ActionSpec, RuleSpec, AuthorityPolicy, ModuleGraphNode, GameplayModeSpec, InferenceCapabilityProfile, PromptPolicy, PluginDescriptor, ScenarioSpec, Diagnostic, DiagnosticSeverity |
| content/project_ir.py | 6 | IRBuildResult, build_ir, flatten_entities, iter_entity_refs, ir_to_data, canonical_yaml |
| content/loader.py | 6 | LAYOUT_REQUIRED, LAYOUT_OPTIONAL, ProjectLoadResult, load_project, read_yaml_file, detect_v1_shape |
| content/module_graph.py | 11 | Requirement, RequirementKind, ModuleEdge, ModuleGraph, parse_requirement, build_module_graph, topological_order, find_cycles, check_unsatisfied_requires, check_module_versions, detect_conflicts |
| content/rule_module.py | 43 | DslRng, DslToken, tokenize_dsl, DslNode, DSL_NODE_KINDS, IfChainNode, ComparisonNode, InTestNode, NotInTestNode, ContainsNode, SubsetNode, SupersetNode, IntersectsNode, DisjointNode, TruthyNode, AddNode, SubNode, MulNode, DivNode, NegNode, NumberNode, StringNode, VariableNode, FunctionCallNode, FeasibilityNode, AndNode, OrNode, NotNode, DslParseResult, DslEvalError, Feasibility, ConditionOutcome, DslContext, resolve_variable, parse_dsl, evaluate_condition, ActionInput, action_text, resolve_target, TargetRef, FeasibilityResult, check_action_feasibility, BUILTIN_RULE_IDS |
| content/validator.py | 8 | ValidationResult, validate_project, check_duplicate_ids, check_references, check_authority_conflicts, check_deployment_leakage, check_dsl_parses, sort_diagnostics |
| content/cli.py | 4 | main, run_validate, render_human, render_json |
| plugins/manifest.py | 3 | PluginManifest, PluginManifestParseResult, parse_plugin_manifest |
| plugins/api.py | 3 | PLUGIN_API_VERSION, EntryPointSpec, PluginAPI |
| plugins/registry.py | 7 | ENGINE_VERSION, PluginSourceKind, RegisteredPlugin, PluginRegistry, discover_local_plugins, discover_entry_point_plugins, validate_plugins |
| **合计** | **116** | 10 模块 `__all__` 并集，模块间零重名（pydantic 模型名全局唯一约束；执行期测试：`test_p5_gate_scenario` 内置 116 名唯一性断言） |

### 8.3 内部计数交叉核验

| 量 | 值 | 展开核验点 |
|---|---|---|
| 模块数 | 10 | §8.2 行数 = 10 |
| 导出名 | 116 | §8.2 逐行名计数 25+6+6+11+43+8+4+3+3+7 = 116 |
| 决策 | 17 | §4 标题计数 D-P5-01..17 |
| 断言 | 20 | §5.2 表行数；G5 分布 4+3+2+3+2+4=18 + 不变量 2（#19/#20） |
| 白名单文件 | 39 | §3.12 表行号 1-39 |
| 诊断码 | 18 | §3.1 DIAGNOSTIC_CODES 表行数 |
| DSL 节点种类 | 23 | §3.5 `DSL_NODE_KINDS` 表行数 |
| 等价集 | 66 | §6.2 两名单 41+25（pytest collect-only 权威计数核验） |
| 对抗项 | 13 | §6.3 表 A1-A13（3 项 N/A 带理由） |
| S-step | 10 | §5.1 S0-S9 |
| 偏差 | 5 | §8.4 D-P5-DEV-1..5 |
| 开放问题 | 3 | §10 OI-P5-1..3（1 项 S2 标记） |

### 8.4 偏差登记

| 编号 | 偏差 | 理由 | 影响面 |
|---|---|---|---|
| D-P5-DEV-1 | `migrations.py` 推迟（Spec §44:2183 列名） | 无 v1 自动兼容（D-P5-04）且无既有 v2 数据可迁移；迁移器需独立任务包 | Spec §44 文件清单面；未来 v1 用户走"手工重填 + validate"路径 |
| D-P5-DEV-2 | `content/` 7 模块 vs Spec §44 建议 4 文件（loader/project_ir/schemas/migrations） | 多出的 `module_graph/rule_module/validator/cli` = Spec §6 MUST 项（authority 冲突静态分析、模块图、machine-readable diagnostics）的载体；§44 清单为"建议"非封闭 | Spec §44 建议面；模块边界更细（单文件 <400 行纪律） |
| D-P5-DEV-3 | DSL 两阶段比 v1 更严：matched 分支后尾随垃圾 v1 容忍（`_skip_until_if_end` condition_eval.py:331-340）→ v2 `LLMSIM_DSL_PARSE` | 两阶段使 parse 可独立审计（G5-6 machine-readable 面）；未达分支垃圾是数据缺陷非语义 | 66 例等价集若含该形态用例，映射表逐例披露（§6.2 DEV-3 披露义务）；等价契约限定于"不含该形态"（§3.5） |
| D-P5-DEV-4 | G4 §6-2 `scheduler_fingerprint` 输入面扩展 = 维持披露分支（不扩展） | core 冻结（32/308）禁止 P5 触碰 scheduler 输入面；扩展需动 core | 下一触碰 core/scheduler 的阶段（P6+）承接扩展或正式关闭披露 |
| D-P5-DEV-5 | G4 §6-3/§6-4 LLM 策略内容层（BehaviorPolicy/ModePolicy 内容）调度未定 | 内容层属 LLM 面，P5 模块按 K8 机械零 LLM 面；调度需 Leader 裁决（与 OI-P5-3 同因） | OI-P5-3；P5 结构面（`InferenceCapabilityProfile`/`PromptPolicy` schema）已就位，内容填充归后续 |

---

## §9 勘误（append-only；初始无）

格式（沿 P4 §9）：`ERR-P5-n`（日期）：症状 → 裁定 → 影响面。后续勘误仅追加，不删除不重排。

**ERR-P5-1**（2026-08-30）：症状 → D-P5-03「S2 标记」与 OI-P5-1 将 ProjectIR 顶层契约（(a) 16 节扁平 typed IR vs (b) ECS 实体中心 IR）标记为 Plan §24 S2（:1230-1242）待人工裁决面，作者按 (a) 先行执行、终局裁决推迟至 M3（G6）；同文档路由声明（头部路由声明行、附录路由行）误读 2026-08-20 人工路由覆写，称其「不自动延申至 P5」。→ 裁定（2026-08-30，项目所有人，详细冲突简报后明确裁定）：
1. **ProjectIR 顶层契约 = (a) 16 节扁平 typed IR，终局**（OI-P5-1 关闭）。裁定理由（记录备查）：Spec §6（`docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md`:454-486）字面枚举即扁平 12 类树（entity definitions 与 component schemas 为兄弟节，非嵌套）；Spec §10.3（:717-735）「v2 MUST NOT 提前承诺 archetype ECS」——ProjectIR 正是承诺形状的位置，实体中心 IR 构成该条款警告的形状承诺；Spec §8.1（:542-563）扁平节列表为 Spec 自身风格先例；P1 D-7 entity-centric（P1-core-data-contracts.md:277-281）属 §10.3 MAY 条款下内部实现，不要求 authoring-time IR 同形。
2. **2026-08-20 人工路由覆写（全任务 → qiyuan-self/qwen3.8-27b，P4 文档:3）为覆盖整个 v2 执行的常设指令，适用于 P5 全部任务与执行波次**；Plan §14 默认模型列（Plan:594-605）为无人工覆写时的后备值，本期不执行。
3. **OI-P5-3 Leader 裁定**：LLM 策略内容层（BehaviorPolicy/ModePolicy 内容、policy 内容重提案）归 P6（Plan §15:618 — Phase 6 LLM Runtime / Prompt / Capability Routing）；P5 零内容层工作，仅保结构面（`InferenceCapabilityProfile`/`PromptPolicy` schema）。
→ 影响面：
- D-P5-03 中「终局裁决推迟至 M3（G6）首个人工门禁」一句作废，其余（16 字段 ↔ 12 类映射、authority 冲突静态分析限声明域重叠）确认为终局，不再是「推迟前先行」；
- §10 OI-P5-1 裁定状态更新为已裁定/已关闭（本勘误），§10 OI-P5-3 更新为已裁定（Leader 2026-08-30），§10 其余文本保留（append-only 纪律）；
- §8.3「开放问题 3（1 项 S2 标记）」行被本勘误取代：OI-P5-1 关闭、OI-P5-3 已裁定、OI-P5-2 保留为事实记录（无行动）；
- §3.1 / §7.2 的 16 字段映射、20 条编号断言、116 导出台账、39 文件白名单**均不受影响**（本就按 (a) 依据构建）；
- 头部路由声明行与附录路由行按裁定 2 修正（见下文）。

---

## §10 开放问题

### OI-P5-1（**S2 标记**，Plan §24 S2 L1230-1242 点名 ProjectIR）
- **问题**：ProjectIR 顶层契约 = (a) 16 节扁平 typed IR（本文档 D-P5-03 选择，执行依据）vs (b) ECS 实体中心 IR（更贴 Spec §7 内核）。两者均可辩护且不可兼容（schema 层形状根本不同）。
- **裁定状态**：**已裁定（ERR-P5-1，2026-08-30，项目所有人）：(a) 16 节扁平 typed IR 终局，本项关闭。** 原状态（已被勘误取代，保留备查）：P5 按 (a) 纯执行；终局裁决推迟至 M3（G6）——G5 之后首个人工门禁（Plan §32：G5 非强制人工门禁）。
- **影响评估（若 (b) 胜）**：`schemas/project_ir/loader/validator` 4 模块可重建（数据映射层）；`rule_module/module_graph/plugins/cli` 6 模块**不受影响**（接口隔离为设计目标——rule_module 消费 `DslContext` 不消费 IR 顶层形状，module_graph 消费 `ModuleGraphNode` 列表，plugins 消费 `RawProject`/`PluginManifest` 独立面）。白名单 39 文件中 fixture #30-34 的 YAML 数据形态两方案通用。

### OI-P5-2（事实记录，无行动）
- Spec §47 与 Plan §14 阶段编号分歧（Spec Phase 5 = Dynamics L2401-2415；Plan Phase 5 = Project Format L586-616）。执行 SOT = Plan §14（G4 §8 同口径）。Spec 修订归 Leader/文档 owner。

### OI-P5-3（**已裁定**，ERR-P5-1 裁定 3，Leader 2026-08-30）
- **裁定**：LLM 策略内容层（BehaviorPolicy/ModePolicy 内容、policy 内容重提案）归 **P6**（Plan §15:618 — Phase 6 LLM Runtime / Prompt / Capability Routing）；P5 零内容层工作，仅保结构面（§3.1 `InferenceCapabilityProfile`/`PromptPolicy` schema 已就位）。内容层任务包随 P6 kickoff 立项。
- 原状态（保留备查）：G4 §6-3/§6-4 移交面：policy 内容重提案 + LLM 策略内容层（BehaviorPolicy/ModePolicy 内容）的调度归属与时间窗。P5 侧已就位结构面（§3.1 `InferenceCapabilityProfile`/`PromptPolicy`），内容层填充任务包待立。

---

## 附：路由声明与作者

- **路由**：2026-08-20 人工路由覆写（全任务 → qiyuan-self/qwen3.8-27b，P4 文档:3）为覆盖整个 v2 执行的常设指令，**适用于 P5 全部任务与执行波次**（ERR-P5-1 裁定 2）。Plan §14 默认模型列（Plan:594-605：T01/T07 → GFlash，T02 → QMax，T03-T06/T08-T10 → Q27）为无人工覆写时的后备值，本期不执行。
- **作者**：qiyuan-self（qwen3.8-27b），P5 设计文档（W1 交付物）。
- **日期**：2026-08-30（冻结 HEAD `e5c4db4`，分支 `architecture-v2`）。
- **下一步**：W1 启动（`content/schemas.py` + `test_schemas.py`，T02a；路由 = qiyuan-self/qwen3.8-27b，ERR-P5-1）→ W2-W5 并行 → W6 末段串行（validator/cli/fixtures/gate/锚点同步）→ G5 门禁运行序 ①-⑥（§3.12）→ gate 报告（Plan §21 格式，`docs/v2/gates/G5-gate-report.md`，默认禁止 CONDITIONAL PASS）。
