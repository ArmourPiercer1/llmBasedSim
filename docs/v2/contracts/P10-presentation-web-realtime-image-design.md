# P10 Presentation / Web / Realtime Image — W0 设计 SOT（冻结版）

| 项 | 值 |
|---|---|
| 阶段 | Phase 10（Plan §19 L817–850）：建立 Text / Image / Tactical presentation 平行结构 |
| 基线 commit | `9945565`（G9 收口 docs commit = `99455650f964aa0aee5416a70a1a655135077419`；代码面收口 = `d9d2cc4ff77432b572b21b5e94db6c1ce41b444f`；初稿时点参照 `6fdfdcf` 保留注记，§0.3.2 仅参照） |
| 分支 | `architecture-v2` |
| 本文件角色 | P10 W0 设计 SOT **冻结版**（初稿 + Leader 终审裁定并入，`.p10/p10-w0-leader-adjudication.md`）。实现波次以本文件为唯一依据（冻结版 4 盲设计评审按 Leader 后续动作序进行，勘误链续编收敛） |
| 结构口径 | 骨架纪律借 `docs/v2/contracts/P9-official-modules-migration-design.md`（1868 行 @ 918480d，ERR-P9-01..16 全链；只借结构不抄内容）；节序按 `.p9/p10-w0-design-brief.md` §7 大纲（§0–§11） |
| 允许写盘 | W0 阶段零代码/测试/git 写（仅本文件 + `.p10/`）；实现波次白名单 = §11（38 行） |
| 任务书 | `.p9/p10-w0-design-brief.md`（148 行）+ `.p9/p10-design-inputs.md`（62 行）；冲突处以本文件为准并登记 §8.4 / §9 |
| 状态 | **已终审**（`.p10/p10-w0-leader-adjudication.md` 裁定并入：12 决策全批 / Q1–Q10 裁定 / SceneView 10 键全批 / DEV-P10-05 登记）——§4 决策 12 条、§5 A 判据 12 条、§10 波次、§11 白名单全部冻结 |

> **字节真值优先（D1）**：本文件所有 `file:line` 锚点均 `sed -n` / `awk` /
> AST / `wc -l` 逐字节核验；初稿时点锚点于 W0 初稿时点工作树（HEAD
> `6fdfdcf`）核验；P9 消费面锚点（narration/space `__all__` + 5 键 /
> register_standard_space 签名 / 边界锚行数）于 G9 收口点（`9945565`）
> `sed -n` 复测后落值，值旁注 file:line 锚（§0.3.3/§2.4/§2.7）。
> **例外披露闭合（DEV-P10-01 闭合）**：初稿时点 P9 W6/W7 交付物未落盘（G9
> 未收口），P9 消费面锚点引用 P9 SOT 冻结设计值并逐处标「待复测」→ G9 收口点
> 复测回填完成：4 名 / 5 键 / 签名（ERR-P9-10 勘误后 entries 形）/ 2625 行
> 均与 P9 SOT 冻结（勘误后）值一致；零漂移，§9 本次零新增勘误。

---

## §0 定位与基线

### 0.1 范围（Plan §19 L817–850 逐项对齐 + P10 落位映射）

| ID | 任务 | 属性 | 难度 | 能力 | 上下文 | 默认模型 | P10 落位（本 SOT 章节） | 波次（D-P10-09） |
|---|---|---|---|---|---|---|---|---|
| P10-T01 | ViewState / SceneView derivation | 开发 | 较高难度 | 纯coding | 1M | QMax | `presentation/view.py`（§3.1）；G10-2「结构化 View」唯一来源 | W1 |
| P10-T02 | Narrator presentation backend | 开发 | 少量思考 | 纯coding | 256K | Q27 | `presentation/text/narrator.py`（§3.2） | W2 |
| P10-T03 | VisualDirector + RenderIntent contract | 开发 | 较高难度 | 纯coding | 1M | QMax | `presentation/image/contract.py` + `image/director.py`（§3.3/§3.4） | W2 |
| P10-T04 | image backend adapter + revision/scene stale handling | 开发 | 较高难度 | 纯coding | 1M | QMax | `presentation/image/backend.py` + contract 过期面（§3.3/§3.5） | W3 |
| P10-T05 | Web singleton → EngineInstance / SessionManager | 开发 | 较高难度 | 纯coding | 1M | QMax | `adapters/web/{session,api,views,server}.py` + static（§3.7–§3.9/§3.12）；43.2-8 移除落点 + G10-3 | W4 |
| P10-T06 | Runtime Inspector minimal web view | 开发 | 较高难度 | 多模态 | 1M | Mimo | `adapters/web/inspector.py`（§3.10）+ views/static；Spec §37 12 面最小化 | W5 |
| P10-T07 | LLM Workbench minimal prompt/trace view | 开发 | 较高难度 | 多模态 | 1M | Mimo | `adapters/web/workbench.py`（§3.11）+ views/static；Spec §38 最小面 | W5 |
| P10-T08 | stale-image / scene-continuity visual test | 测试 | 少量思考 | 多模态 | 1M | Mimo | 机械面 = `test_image_backend.py` t6–t8 + `test_g10_gate.py` t1 + `test_view.py` t5 + `test_render_intent.py` t4（continuity_refs 传递）+ AD-P10-3（stale 连发）〔§3.14 全量〕；多模态人工判定 = S11 挂起面（§0.2 G10-6/7） | W3/W5 |

**G10 条款计数口径**：自动 4 + 人工 3 = **7 个门面条**。自动 → A1–A4（§5.2，
1:1 平铺函数）；人工 3 = S11 人工验收挂起面（gate 报告「Human review
required」字段登记，Plan §21 九字段模板 L892–903）。

### 0.2 Gate G10 逐字回应（Plan L836–850 原文 + 逐条回应）

Plan 原文（L836–850 逐字；L838「自动：」、L845「人工：」为分组行）：

```text
自动：

- Image A 属于 `view_revision=83`，当前已到 87 → 不错误覆盖当前 view；
- Narrator 与 VisualDirector 均读取结构化 View，而非 image 强制依赖 prose；
- Web 不存在 module-level singleton World；
- inspector 能定位 event → transaction → effect → producer。

人工：

- GUI 信息层次可读；
- 实时图像不会明显错场；
- Galgame 场景视觉连续性达到可接受水平。
```

逐条回应（自动 = 机制 + A 判据 + 1:1 平铺函数；人工 = 挂起面 + 支撑机制）：

| # | 条款 | 机制（本 SOT 章节） | A 判据 | 平铺函数（§6.1） |
|---|---|---|---|---|
| G10-1 | 自动①：stale image 不错误覆盖 | `apply_image_result`（§3.3）：artifact 携 `view_revision`（Spec §32.3 必带）；`core::is_stale`（revision.py:78）判定；默认策略 = DISCARD（D-P10-11） | A1 | `test_g10_gate.py::test_g10_gate_t1_stale_image_no_overwrite` |
| G10-2 | 自动②：双 backend 读结构化 View | Narrator（§3.2）与 VisualDirector（§3.4）签名输入 = `SceneView`（§3.1）唯一；`text/` ↔ `image/` 零互 import（§3.0 特例钉，AST） | A2 | `test_g10_gate.py::test_g10_gate_t2_dual_backend_structured_view` |
| G10-3 | 自动③：Web 无 module-level singleton World | `SessionManager` 显式注入（§3.7，零模块级实例）；AST 扫 `adapters/web/` + `presentation/` 全树：零模块级 `WorldState()`/`SessionManager()`/`WebSession()`/`Scheduler()`/`LogicalClock()` 实例化 + 零模块级 session 全局绑定；v1 反例锚 = app.py:221 | A3 | `test_g10_gate.py::test_g10_gate_t3_no_module_singleton_world` |
| G10-4 | 自动④：inspector 定位 event → transaction → effect → producer | `inspect_event`（§3.10）= `TraceQuery.causal_chain`（trace_query.py:199）端到端；`CausalChain` 六字段（:51–73：event/transaction/effects/producers/action_refs/intervention_refs）；零旁路直读 WorldState 内部（P10-INV-5） | A4 | `test_g10_gate.py::test_g10_gate_t4_inspector_chain_locator` |
| G10-5 | 人工①：GUI 信息层次可读 | 服务端渲染三页（index/inspector/workbench，§3.12）；S11 挂起面 | —（S11） | —（gate 报告登记） |
| G10-6 | 人工②：实时图像不错场 | stale 标记面（slot.stale，§3.3）+ scene 敏感面（A10/t3）支撑人工判定 | —（S11） | —（gate 报告登记） |
| G10-7 | 人工③：Galgame 场景视觉连续性可接受 | `scene_id` 确定性派生（§3.1/D-P10-12）+ `continuity_refs`（§3.4）+ P9 galgame 样例（只读）世界源 | —（S11） | —（gate 报告登记） |

### 0.3 基线表

#### 0.3.1 G9 终态（**已回填**——G9 收口实测；DEV-P10-01 闭合）

| 项 | 期望值（P9 SOT 冻结口径） | 实测值（G9 收口回填） |
|---|---|---|
| 套件基线 | 3142 passed / 0 failed（P9 SOT §8.3 恒等式：3054 + 82 平铺 + 6 边界） | **3142 passed / 0 failed**（实测；G9 门级 R1 4 盲 + W7 R4 4 盲共 8 次独立复跑一致；恒等式 3054+82+6 对账一致） |
| G9 收口 commit | — | **`99455650f964aa0aee5416a70a1a655135077419`**（docs 提交；代码面收口 = `d9d2cc4ff77432b572b21b5e94db6c1ce41b444f`） |
| P9 冻结面清单 | 15 模块文件 71 名（P9 SOT §8.2）+ 15 测试文件 82 平铺 + 3 样例项目 15 文件（§3.16）+ 边界锚 P9 块（§3.20 6 方法，+350–450 行估算） | **对照 P9 SOT §3.19/§8.2 落 47 行白名单摘要**：15 src 模块（71 导出名，§8.2 台账）+ 1 script（`scripts/v2_migrate_v1.py`）+ 13 平铺测试文件（82 函数）+ `tests/engine_v2/modules/{__init__,conftest}`（2 文件）+ 3 样例项目 15 yaml + 边界锚 M（P9 块 = L2072–2625，锚文件现 2625 行，L1–2071 sha256 = `26fc0528459e658f126c9b13bbc284344e553b2918eeee85e8b08dbf3dbc9202`，复测） |
| G9 门禁报告 | `.p9/` 内（本初稿禁读面） | `docs/v2/gates/G9-gate-report.md`（门 = PASS；16 条款 + 门③①–⑥ 全绿；门级 R1 4×通过，0 SUPPLEMENT / 0 BLOCK；3142/0） |

#### 0.3.2 W0 初稿时点实测参照（@ `6fdfdcf`，全部复测；**仅参照，非基线**）

| 项 | 实测值 | 核验命令 |
|---|---|---|
| HEAD | `6fdfdcf`（P9 W4 波提交，提交信息尾注「3097/0」） | `git rev-parse HEAD` |
| P9 W5 状态 | **未提交**：3 个未跟踪文件（`scripts/v2_migrate_v1.py` / `src/engine_v2/modules/v1_migration.py` / `tests/engine_v2/modules/test_v1_migration.py`） | `git status --porcelain` |
| P9 W6/W7 状态 | **未落盘**：`modules/{narration,space,dialogue,tactical,dynamics}.py` 缺席；`test_g9_*.py` / `test_p9_differential.py` / `test_module_face.py` 缺席；`tests/fixtures/v2_project_{galgame,sandbox,tactical}/` 缺席；边界锚 P9 块未追加 | `ls` |
| 套件 | **3104 passed in 17.68s**（= 3054 基线 + P9 W1–W5 50 平铺，与 P9 SOT §3.18 波表累计 16+10+7+10+7 = 50 吻合；W6/W7 22 平铺 + 6 边界未计入） | `PYTHONPATH=. .venv/bin/python -m pytest -q -p no:cacheprovider` |
| 行宽纪律 | `pyproject.toml:31` line-length = 100 | `sed -n '31p'` |
| Python 环境 | `.venv/bin/python` + `PYTHONPATH=.`；P10 import 闭集 = stdlib + pydantic（§3.0） | — |

#### 0.3.3 P10 直接消费的冻结面锚点表（W0 初稿时点 sed 实测 @ `6fdfdcf`）

| 面 | 锚点（file:line，实测） | 核验 | P10 用途 |
|---|---|---|---|
| P8 TraceQuery | `devtools/trace_query.py`（273 行）：`__all__`:36 = ("TraceQuery","CausalChain","TraceQueryError")；TraceQueryError:39；CausalChain:51（event:68 / transaction:69 / effects:70 / producers:71 / action_refs:72 / intervention_refs:73；to_dict:75）；TraceQuery:91（by_producer:120 / domain_events:126 / transactions:132 / committed_transactions:138 / authority_decisions:147 / revision_timeline:164 / intervention_history:193 / causal_chain:199） | ✓ | Inspector 数据源（G10-4；P10-INV-5） |
| P8 快照面 | `persistence/snapshot.py`（206 行）：`__all__`:43（5 名）；PersistenceSnapshot:52 / to_persistence_snapshot:104 / dump_persistence_snapshot:133 / load_persistence_snapshot:143 / check_persistence_versions:176 | ✓ | WebSession 载入/导出（A12/t4） |
| P6 推理缝 | `llm/adapter.py`：InferenceRequest:98（11 字段：messages/model/base_url/api_key_env/temperature/max_tokens/timeout_seconds/logical_role/profile/base_revision/prompt_metadata_ref）；InferenceResponse:132（text/model/latency_ms/input_tokens/output_tokens）；InferenceBackend:150（Protocol）；**FakeInferenceBackend:296**（`script: dict[tuple[str, Revision, int], str]`；查找键 = (logical_role, base_revision, seq)，seq 1-based 本实例计数；未命中落 default_text；calls:326 只读调用史；generate:330）；MonotonicClock:47 / FixedMonotonicClock:71 | ✓ | Narrator/VisualDirector K5 脚本面（P10-INV-6）+ Workbench prompt 史（T07） |
| core revision | `core/revision.py`：Revision:43 / next_revision:73 / **is_stale:78**（base < current 即陈旧；valid_until 非 None 时 current > valid_until 亦陈旧；纯函数） | ✓ | view_revision 投影 + 过期判定（P10-INV-2；G10-1） |
| core state | `core/state.py`：WorldState:246（world_revision:276）；EntityView 视图携构造时 world_revision 有效性判据（:303–310，KBC-3 先例）；ScenarioState:102 / RuntimeState:192 | ✓ | SceneView 派生源 + 视图-revision 判据先例 |
| core 事件/事务 | `core/events.py`：DomainEvent:111（event_id / event_type / world_revision 必填 / logical_tick 可空 / transaction_id 可空 / payload / cause_ids / source_system 必填 / provenance 必填 / cascade / wall_time）；`core/transaction.py`：Transaction:62（transaction_id / status / base_revision / commit_revision / logical_tick / effects / event_ids / cascade / provenance / abort_reason，10 字段穷举）；`core/trace.py`：TraceKind:91（12 值枚举）/ TraceRecord:113（record_id / kind / world_revision / logical_tick / wall_time / producer_id / transaction_id / cascade_id / payload，9 字段穷举） | ✓ | Inspector 链（G10-4）+ conftest trace 夹具（§6.2） |
| P8 devtools CLI | `devtools/cli.py`：`__all__`:46（5 名）；CLI_COMMANDS:56 = ("inspect","trace","replay","branch","test")；build_cli_envelope / run_devcontrol_cli:309（信封 = ok / error_code / error_message 形状） | ✓ | Inspector/Workbench JSON 信封形状参照（P10 不 import，形状对齐） |
| v1 web 冻结参照 | `src/web/app.py`（596 行）：GameSession:106（id/state/graph/llm/prompt_loader/tick_thread/lock/status/busy）；**`session = GameSession()`:221 = 模块级单例（43.2-8 移除对象反例锚）**；路由 GET /:230 /api/state:232 /api/progress:234 /api/saves:236 /api/init-files:238 /static/*:240，POST /api/start:254 /api/action:256 /api/save:258；handle_command:~178–200（/help /status /idid /see /hear /feel /save <name>；help 文案另列 /c /stop）；snapshot():442（~24 展示键：started/world_name/tick/game_phase/narrative/senses/player_attributes/recent_events/narrative_history/can_continue/has_long_task…）；create_server:319 / run:323；**app.py:18 `from langchain_openai import ChatOpenAI`（v1 LangChain 消费面）** | ✓ | T05 语义参照（只读；冻结）；A3 反例锚 |
| v1 web 入口 | `src/web/main.py`（124 行）：IP 探测 + `run()` 调用（app.run 面） | ✓ | server.py 薄壳参照（IP 探测 = 非范围） |
| v1 静态先例 | `web/index.html` + `web/static/app.js`（770 行，零构建 vanilla JS）+ `web/static/styles.css` | ✓ | S4 预裁决先例（静态 HTML + 零依赖 JS，简报 §6） |
| v1 UI 参照 | `src/ui/cli.py`（54 行）/ `src/ui/renderer.py`（237 行；`console = Console()`:7 = v1 第二处模块级单例面）/ `src/ui/status.py`（32 行） | ✓ | text 模板面风格参照；A3 反例锚（v1 侧，冻结不改） |
| v1 测试 | `tests/test_webui.py`（185 行，13 个 test 函数；snapshot/命令面/路径安全钉） | ✓ | 冻结（计入基线；语义参照） |
| 占位二件套 | `src/engine_v2/presentation/__init__.py`（8 行「占位，Phase 10 填充」）/ `src/engine_v2/adapters/__init__.py`（8 行「占位，Phase 8/10/11 填充」） | ✓ | 字节冻结（§2.6） |
| 边界锚文件 | `tests/engine_v2/core/test_import_boundary.py`（**现 2625 行**（G9 收口实测；P9 块 = L2072–2625，+554 行，TestP9Boundary 6 方法）；L1–2071 sha256 = `26fc0528459e658f126c9b13bbc284344e553b2918eeee85e8b08dbf3dbc9202`（复测）；P10 块 = L2625 后 EOF 纯追加） | ✓（G9 收口点复测） | §7 / P9 SOT §3.20 先例延续 |
| P9 消费面（narration/space） | **G9 收口复测完成**（DEV-P10-01 闭合，sed -n 复测）：`modules/space.py`（235 行）`__all__`（:62–67）4 名逐字 = HexGrid（:86）/ hex_adjacency（:140）/ distance_between（:188）/ register_standard_space（:200，ERR-P9-10 勘误后 entries 形签名 :200–204）；`modules/narration.py`（133 行）`__all__`（:40–45）4 名逐字 = NarrativeFrame（:55）/ NarrativeStyle（:65）/ NarrativeView（:73，TypedDict total=False 5 键实测序 = tick :81 / scene_text :82 / frames :83 / actors_visible :84 / clock :85）/ render_narrative_view（:88） | ✓（G9 收口点复测） | SceneView.narrative 5 键兼容钉（A7/t6）；tactical conftest hex 面 |

### 0.4 非范围（P10 明确不做，归后续阶段 / 门）

| 非范围项 | 归属 | 依据 |
|---|---|---|
| 真实图像生成 backend（扩散 / 向量引擎 / 外部 API） | P11+ 或 S4 人工裁决 | D-P10-02；简报 §6 S4 预裁决；Spec §46 推迟面 |
| Multiplayer authoritative server / distributed simulation / full GUI / full local dev service / complete branch debugger UI | 推迟（Spec §46 L2300–2310 第 1/2/3/8/9 项；ERR-P10-06：原上界 L2309 差 1 行，第 9 项实测 L2310） | P10 web = minimal view（§3.10/§3.11/§3.12） |
| `adapters/cli/` / `adapters/dsh/` | P11（Spec §44 L2193–2196；Plan §20） | 本阶段只建 `adapters/web/` |
| P9 模块任何修改（含 narration/space） | D5 / P10-INV-9 | G9 收口冻结 |
| v1 文件删除（含 `src/web/`、`src/ui/`、`web/`） | D-P10-08 | 43.2-8 = v2 侧不存在，非文件删除（P10-INV-9） |
| 新 Python 依赖 / JS/Node 前端构建栈（package.json / npm / bundler） | S4（零新依赖） | D4 / P10-INV-8；简报 §6 预裁决 |
| Replay / branch 完整调试 UI | Spec §46-9 推迟 | Inspector 只给 save 列表 + replay 可用性标志（§3.10） |
| 玩家自由文本 → LLM 决策（真实 LLM player policy） | K5 / P10-INV-6 | TemplatePlayerPolicy = 确定性模板（§3.7）；LLM 面仅脚本注入 |
| CLI agent workflow / DSH adapter | P11（Plan §20） | Spec §35 thin adapter |

### 0.5 纪律（D1–D8）

- **D1 字节真值优先**：一切 `file:line` 锚点先 `sed -n` / `awk` / AST 逐字节
  核验后写入；P9 W6/W7 未落盘面引用 P9 SOT 冻结值并标「待复测」（DEV-P10-01）
  → G9 收口点复测回填**完成（DEV-P10-01 闭合）**，偏差入 §9（本次零新增勘误）。
- **D2 行宽**：P10 全部产物（落盘 src/tests/static）≤ 100 字符/行
  （`pyproject.toml:31`；`LC_ALL=C.UTF-8 awk 'length($0)>100'` 零命中，门④⑤）；
  本 SOT = 非表格行零命中（markdown 表格行豁免，P9 SOT 先例）。
- **D3 控制字节纪律**：P10 全部文本/docstring/JS/HTML 参数零裸反
  斜杠+b 序列（连续字节 0x5C 0x62；ERR-P7-14 先例；`test_p10_face_t5`
  钉）。
- **D4 依赖闭集**：P10 代码仅 stdlib + pydantic（uv.lock 既有）；
  `pyproject.toml` 字节冻结；零新增依赖（S4）。HTML 渲染 = stdlib
  `string.Template` + `html.escape`（D-P10-07，零 Jinja2）。
- **D5 冻结面零修改**：core/content/llm/prompts/dynamics/persistence/
  plugins/devtools + P9 15 模块及其测试目录 + v1 路径集 + 占位二件套 +
  边界锚 L1–2625（G9 收口实测行数；L1–2071 sha256 = `26fc0528…`
  复测自证，§0.3.1）字节不变；唯一修改模式 =
  边界锚文件 EOF 纯追加（P10 块 = L2625 后，P9 先例延续）。
- **D6 确定性**：P10 全部公开函数纯函数或显式注入状态；时钟 = 注入
  （core `LogicalClock` / P6 `FixedMonotonicClock`）；零 wall-clock、零
  模块级全局 RNG；图像字节 = f(intent) 纯函数（A10 双跑字节相等）。
- **D7 K8 词表闭集**：P10 src 字符串字面量（含 docstring）× 12 名：
  唯一允许命中 = narrator.py `TEXT_SOURCES` 钉元组（"llm" = 脚本命中
  推理路径标签，类别标签非供应商名；SOT §3.2/§5.2/§6.1 三处钉面；
  ERR-P10-10），其余字面量 × 12 名零命中
  （openai / anthropic / langchain / litellm / ollama / gemini / gpt /
  claude / llm / provider / api_key / base_url；P4 §3.4 12 名闭集）+
  engine_v2 全树 import 零 langgraph/langchain。测试侧模型名用
  `fake-model-1` 形态（A 判据 t2 钉）。
- **D8 勘误链纪律**：§9 唯一规范记录；历史条目不追改；实现波次勘误按
  ERR-P10-NN 续编（ERR-P9-01..08 先例）。

### 0.6 风险登记册

| # | 风险 | 等级 | 缓解（SOT 面） |
|---|---|---|---|
| R1 | G9 收口漂移：P9 W5 未提交 / W6–W7 未落盘 → P10 消费面锚点漂移（narration 5 键、space 4 名、边界锚行号） | 高 | 基线表 §0.3.1 + DEV-P10-01 + G9 收口点 Leader `sed` 复测回填（**已闭合：实测零漂移**，§0.3.1/§2.4/§2.7 回填）+ 边界哈希清单于 P10 W5 自 G9 收口树计算（§7 实现注记） |
| R2 | web handler 层「顺手」长成有状态常驻服务（模块级 session / 全局 world） | 中 | D-P10-03（无状态 handler + 注入 SessionManager）+ A3 AST 双钉 + SC-P10-1 |
| R3 | image backend「顺手」引图像库（PIL/Pillow 等） | 中 | D-P10-02（stdlib PPM P3 伪图像面）+ D4 闭集 + 边界方法 4 + S4 触发面 |
| R4 | JS 静态面膨胀为前端构建栈（package.json / bundler 出现） | 中 | face t6（零构建产物 AST/文件检查）+ 边界方法 1/2 + S4 预裁决（简报 §6） |
| R5 | SceneView 与 P9 NarrativeView 兼容面漂移（P9 W6 实现若改 5 键名） | 低 | A7/t6 键名钉 + D-P10-01 形状复用（非函数依赖，零 import）+ G9 收口复测（**已完成：5 键名一致**，§2.4） |

### 0.7 S1–S5 预检（Plan §24 逐条）

- **S1（改变 Kernel invariant）— 未触发**：P10 零 kernel 修改；View /
  ImageSlot / RenderIntent = 派生数据（P10-INV-1，Spec §8.5 L626–638
  「ViewState MUST NOT 成为 authoritative world」）；presentation 零直写
  （K2）；Session/World 零合并。
- **S2（Public Contract 两种合理不兼容设计）— 未触发**：RenderIntent =
  Spec §32.2 字段逐字（单一设计）；SceneView / ImageSlot / TacticalLayout =
  presentation 内部契约，非跨阶段 public contract。
- **S3（destructive migration）— 未触发**：零迁移（v1 文件只读参照，
  D-P10-08）。
- **S4（新重大依赖 / License）— 预裁决未触发**：零新依赖（D4 /
  P10-INV-8）；触发面 = JS/Node 构建栈引入——预裁决方向 = 静态 HTML +
  零依赖 JS（v1 先例 web/static/app.js 770 行 vanilla），若需构建栈 →
  停报人工（简报 §6 预登记）。
- **S5（Backend 无法满足 replay/checkpoint）— 未触发**：零新数值 backend；
  DeterministicImageBackend = 确定性伪图像参考面（D6 双跑字节相等，无
  replay 需求）；会话载入 = P8 冻结快照面（A12/t4）。

---

## §1 不变量（P10-INV-1..10）

> 前 5 条 = 简报 §2 草案原序承接（编号不变）；6–10 为初稿扩展。

| ID | 不变量 | 机械验证面 |
|---|---|---|
| P10-INV-1 | View = WorldState + DomainEvents 的纯派生：零反作用（修改 view 世界哈希不变）；同输入同 View（确定性）（Spec §8.5；G10-2 前提） | A5（t1/t3：双跑相等 + 世界哈希不变） |
| P10-INV-2 | view_revision 单调 = world revision 投影；stale image 携旧 revision → 拒绝覆盖当前 view（Spec §32.3；G10-1） | A1/A6 + t6/t7/t8（策略三面）+ D6 双跑 |
| P10-INV-3 | Narrator 与 VisualDirector 输入 = 结构化 View（SceneView 唯一）；零 prose 互依赖（Spec §32.1；G10-2） | A2（AST 互 import 零 + 签名面 §3.2/§3.4） |
| P10-INV-4 | Web 层零 module-level singleton World（43.2-8 L2081 移除落点；G10-3）；会话 = SessionManager 显式实例，零模块级全局 session 绑定 | A3（AST 全树零模块级实例化 + v1 反例锚 app.py:221） |
| P10-INV-5 | Inspector 数据源 = P8 冻结 trace 面（TraceQuery/CausalChain）+ 快照面；零旁路直读 WorldState 内部构建因果链（G10-4） | A4 + 边界方法 4（inspector/workbench import 闭集 §3.0） |
| P10-INV-6 | K5 零真实 LLM：Narrator / VisualDirector 的 LLM 面 = 显式注入 InferenceBackend（测试 = FakeInferenceBackend 脚本，键 (logical_role, base_revision, seq)）；零网络 / 零 API key / 零 provider | A8 + 边界方法 4（llm 消费仅 adapter 冻结面）+ t1（template 零调用） |
| P10-INV-7 | K8 零推词：P10 src（含 static JS/HTML/CSS 字符串字面量与 docstring）12 名闭集零命中；engine_v2 全树 import 零 langgraph/langchain | face t3 + 边界方法 3/4 |
| P10-INV-8 | 零新第三方依赖：`pyproject.toml` 字节冻结、uv.lock 零变更；import 闭集 = stdlib + pydantic + engine_v2 冻结根（§3.0）（S4） | face t4/t6 + 边界方法 4/6 + 门④ diff |
| P10-INV-9 | v1 冻结面（含 `src/web/` `src/ui/` `web/` 根）与 P9 冻结面（15 模块 + 15 测试 + 3 样例 + 占位二件套）字节不变；边界锚唯一修改模式 = EOF 纯追加；唯一例外 = `tests/test_engine_v2_skeleton.py` 计数面扩展（ERR-P10-09） | 边界方法 5/6（sha256 清单）+ 门④② diff |
| P10-INV-10 | JSON-clean：P10 全部对外输出面（SceneView / RenderIntent / ImageSlot / TacticalLayout / state_snapshot / inspector / workbench 视图）`json.dumps` 零失败 | 各 A 的 json.dumps 断言（t4 族）+ face 面 |

---

## §2 冻结缝表

> 本节为 P10 消费的**全部**冻结面清单；实现波次只允许引用本节列名（+ 其
> submodule 内 `__all__` 既有成员）。锚点行号均 W0 初稿时点 `6fdfdcf`
> 复测；P9 消费面（P9 W6/W7 交付物）已 G9 收口点复测落值（§2.4）。

### 2.1 core 消费子集（`src/engine_v2/core/`，P10 面）

| 文件 | 消费名（file:line，实测） | P10 用途 |
|---|---|---|
| revision.py | Revision:43 / next_revision:73 / is_stale:78 | view_revision 投影 + 过期判定（P10-INV-2；G10-1） |
| state.py | WorldState:246（world_revision:276）/ ScenarioState:102 / RuntimeState:192 | SceneView 派生源（§3.1）；conftest 世界构建 |
| events.py | DomainEvent:111（字段 §0.3.3） | Inspector 事件链（G10-4）；conftest 事件夹具 |
| transaction.py | Transaction:62 / TransactionStatus:51 | Inspector 事务链（effects/event_ids 面） |
| trace.py | TraceKind:91（12 值）/ TraceRecord:113 | conftest trace 记录流（TraceQuery 输入） |
| ids.py | EventId / TransactionId / TraceRecordId / ProducerId（既有 `__all__`） | conftest 构造 |
| space.py | SpatialDomain:112 / SpaceRegistry:175 / GraphSpace:256 / GridSpace:350 / SPACES_COMPONENT:447 / decode_spaces:492 / entity_domain_positions:505 | tactical layout 几何源（§3.6，只读组件面） |
| behavior_policy.py | PlayerPolicy:70 / run_policy_decide:83 | TemplatePlayerPolicy（§3.7）实现面 |
| actions.py | ActionProposal:145 / ActionTypeId:71 | WebSession.step 玩家提案（talk） |
| scheduler.py | Scheduler:550 / start_action:468 | conftest TickDriver 宿主循环（P1 面先例：宿主 = 测试侧） |
| clock.py | LogicalClock:77 / set_logical_tick:117 | conftest 注入时钟；SceneView.clock 面 |
| effects.py | ProposedEffect:197 / CommittedEffect:229 | conftest 宿主应用面（K2：宿主经 kernel 落位） |
| components.py / entity.py | 既有 `__all__`（ComponentSchema / Entity 族） | conftest 世界构建 |

> core 其余导出（authority/cascade/conflicts/interrupt/provenance/
> serialization/transaction 应用器等）P10 **不消费**——边界方法 4 import
> 闭包以本表 + 各文件 `__all__` 为闭集。

### 2.2 P8 persistence / devtools 消费（冻结）

| 文件 | 消费名（file:line，实测） | P10 用途 |
|---|---|---|
| persistence/snapshot.py | PersistenceSnapshot:52 / to_persistence_snapshot:104 / dump_persistence_snapshot:133 / load_persistence_snapshot:143 / check_persistence_versions:176 | WebSession 会话载入（load:143）+ 状态导出（dump:133）（A12/t4） |
| devtools/trace_query.py | TraceQuery:91（causal_chain:199 / domain_events:126 / transactions:132 / committed_transactions:138 / authority_decisions:147 / revision_timeline:164 / intervention_history:193 / by_producer:120 / records:112 / by_kind:116）/ CausalChain:51（to_dict:75）/ TraceQueryError:39 | **Inspector 唯一数据源**（P10-INV-5；G10-4）；Spec §37 12 面中 7 面直接投影（§3.10） |
| devtools/cli.py | build_cli_envelope / CLI_COMMANDS:56（`__all__`:46，5 名） | JSON 信封形状参照（ok / error_code / error_message；P10 不 import） |

### 2.3 P6 llm 消费（冻结）

| 文件 | 消费名（file:line，实测） | P10 用途 |
|---|---|---|
| llm/adapter.py | InferenceRequest:98（11 字段 §0.3.3）/ InferenceResponse:132 / InferenceBackend:150 / FakeInferenceBackend:296（script 键 (logical_role, base_revision, seq)，seq 1-based；calls:326；generate:330）/ MonotonicClock:47 / FixedMonotonicClock:71 | Narrator / VisualDirector LLM 面注入（P10-INV-6）；Workbench prompt 史（T07：calls → (seq, logical_role, base_revision, model, prompt_metadata_ref, response_text) 6 键投影，§3.11 逐字；ERR-P10-05：原 5 字段摘要漏 prompt_metadata_ref 且 text 应为 response_text） |

> P6 deployment/prompts 冻结面 P10 **不消费**（P10 零部署解析——模型名
> 由调用方经 InferenceRequest.model 面给出；测试 = `fake-model-1`）。

### 2.4 P9 消费（冻结设计面；**G9 收口复测完成，按磁盘实测落值**——DEV-P10-01 闭合）

| 面 | 锚（G9 收口点磁盘实测，file:line；G9 收口 commit `9945565`） | P10 用途 |
|---|---|---|
| modules/narration.py（133 行；P9 SOT §3.14，4 名） | `__all__`（:40–45）逐字序 = NarrativeFrame（:55）/ NarrativeStyle（:65）/ NarrativeView（:73）/ render_narrative_view（:88）；NarrativeView = TypedDict(total=False) 5 键实测序 = tick（:81）/ scene_text（:82）/ frames（:83）/ actors_visible（:84）/ clock（:85） | **形状复用、函数不消费**：SceneView.narrative = 同 5 键 dict（A7/t6 键名钉）；P10 src 零 `engine_v2.modules` import（§3.0） |
| modules/space.py（235 行；P9 SOT §3.11，4 名） | `__all__`（:62–67）逐字序 = HexGrid（:86）/ hex_adjacency（:140）/ distance_between（:188）/ register_standard_space（:200）；register_standard_space 实际签名（ERR-P9-10 勘误后 entries 形，:200–204）= `(entries: dict[str, tuple[SpatialDomain, SpaceBackend]], domain: str, backend: SpaceBackend) -> None` | **仅测试侧**：conftest 构建 hex 世界（GraphSpace 注册，P9 A12 钉值 16 无向边参照）；P10 src 零 import |
| P9 3 样例项目（P9 SOT §3.16，15 文件 = 3×5 yaml） | tests/fixtures/v2_project_{galgame,sandbox,tactical}/（G9 收口落盘，§0.3.1） | S11 人工面世界源（gate 时点 Leader 驱动 web 会话验收）；机械面零消费（零 fixture import） |
| P9 15 模块 71 名台账（P9 SOT §8.2） | 71 名（G9 门③⑥步 AST 逐字全等） | P10-INV-9 冻结对象 + 边界方法 6 哈希清单（W5 自 G9 收口树计算） |
| 边界锚文件 | `tests/engine_v2/core/test_import_boundary.py` **现 2625 行**（P9 块 = L2072–2625，+554 行，TestP9Boundary 6 方法）；L1–2071 sha256 = `26fc0528…`（§0.3.1 全值，复测自证）；**P10 追加起点 = L2625 后 EOF** | §7 / §2.7 纯追加纪律（D5 / P10-INV-9） |

### 2.5 v1 冻结缝映射（43.2-8 / 43.3-9 落位；语义参照只读）

> v1 锚点行号 @ `6fdfdcf` 工作树（== v1 最后变更点 f0a1052 之后无变更，
> P9-INV-1 延续）。P10 对 v1 **零修改零删除**（D-P10-08）。

| v1 文件（行数） | 三态 | P10 落位 |
|---|---|---|
| `src/web/app.py`（596；GameSession:106 / **单例 session:221** / 路由 :230–258 / handle_command:~178–200 / snapshot():442 / create_server:319 / run:323 / langchain_openai import:18） | 移除（43.2-8「Web singleton session」L2081）+ 重写（43.3 第 9 项「web session lifecycle」L2095） | `adapters/web/session.py`（多会话 SessionManager，零单例，A3 以 :221 为反例锚）+ `api.py`（路由表，§3.8）+ state_snapshot（§3.7，snapshot():442 ~24 键语义参照）；:18 LangChain import = v1 残留面（P10 零对应，P10-INV-7） |
| `src/web/main.py`（124；IP 探测 + run） | 重写（web session lifecycle 入口面） | `adapters/web/server.py`（薄壳；IP 探测 = 非范围 §0.4） |
| `web/index.html` + `web/static/app.js`（770）+ `web/static/styles.css` | 保留思想（43.1-11 CLI/Web adapter separation + 零构建静态先例） | `adapters/web/static/{index.html, app.js, styles.css}`（新 3 文件，最小集，S4 先例）；v1 原件冻结 |
| `src/ui/{cli.py 54, renderer.py 237, status.py 32}`（renderer `console = Console()`:7 = v1 第二处模块级单例面） | 移除（43.2-8 同族思想）+ 保留思想（narrative renderer 43.1-10 的展示风格） | text 模板面风格参照（§3.2 模板文风）；P10 不建 CLI adapter（P11）；v1 原件冻结 |
| `tests/test_webui.py`（185；13 函数：snapshot 键面 / 命令面 / 路径安全 / 单例会话面） | 冻结（计入基线） | 语义参照（state_snapshot 键面 + 命令闭集参照）；零修改 |

**43.2-8 / 43.3-9 落位核对**：「Web singleton session」（43.2-8 L2081）
移除落点 = P10-INV-4 + A3（v2 侧 AST 零单例，v1 侧冻结为反例锚）；
「web session lifecycle」（43.3 L2095）重写落点 = `adapters/web/session.py`
（§3.7）+ `api.py`（§3.8）+ `server.py`（§3.12）。

### 2.6 占位文件（字节冻结二件套）

| 文件 | 行数 | docstring | P10 处置 |
|---|---|---|---|
| `src/engine_v2/presentation/__init__.py` | 8 | 「占位，Phase 10 填充」 | 字节冻结（P8/P9 先例：填充包后占位 docstring 不更新）；P10 新子包 `__init__.py` = 新文件（白名单 A），docstring-only，零 re-export（P9 `modules/__init__.py` 9 行先例） |
| `src/engine_v2/adapters/__init__.py` | 8 | 「占位，Phase 8/10/11 填充」 | 同上（P10 面 = `adapters/web/` 子包） |

### 2.7 边界锚文件（唯一可修改的既有测试文件）

- 文件：`tests/engine_v2/core/test_import_boundary.py`，**现 2625 行**
  （G9 收口实测；P9 块 = L2072–2625，+554 行，TestP9Boundary
  6 方法块，P9 SOT §3.20）。
- L1–2071 sha256 = 26fc0528459e658f126c9b13bbc284344e553b2918eeee85e8b08dbf3dbc9202
  （G9 收口点复测，自证）；**P10 块 = L2625 后，EOF 纯追加**
  （D5 / P10-INV-9）。
- P10 块自含：复用既有 `P4_LLM_PROVIDER_BLACKLIST`（12 名，:225–240，
  L1–2071 冻结段）与既有常量，零重复定义；`TestP10Boundary` 6 方法表 = §7。

### 2.8 冻结测试侧缝

- `tests/engine_v2/{core,content,llm,prompts,dynamics,persistence,plugins,
  modules}/` 全部文件字节不变（P10-INV-9）；唯一例外 = §2.7 锚文件
  EOF 纯追加。
- v1 测试目录（`tests/test_*.py` 等）字节不变（P10-INV-9）。
- `tests/fixtures/` 既有 7 项目 + P9 新增 3 项目（G9 收口后）字节不变；
  **P10 零新增 fixture 文件**（D-P10-06；世界源 = conftest 内存构建 §6.2）。

---

## §3 模块设计

### 3.0 包树与导入闭集

```text
src/engine_v2/presentation/
├── __init__.py          # 既有 8 行占位，字节冻结（§2.6）；不 re-export
├── view.py              # T01（§3.1）ViewState / SceneView 派生
├── text/
│   ├── __init__.py      # 新建（docstring-only；白名单行 2）
│   └── narrator.py      # T02（§3.2）Narrator presentation backend
├── image/
│   ├── __init__.py      # 新建（docstring-only；白名单行 4）
│   ├── contract.py      # T03（§3.3）RenderIntent / ImageArtifact / 过期策略
│   ├── director.py      # T03（§3.4）VisualDirector
│   └── backend.py       # T04（§3.5）ImageBackend + 参考/伪实现
└── tactical/
    ├── __init__.py      # 新建（docstring-only；白名单行 8）
    └── layout.py        # T04 波（§3.6）Tactical 最小面

src/engine_v2/adapters/
├── __init__.py          # 既有 8 行占位，字节冻结（§2.6）；不 re-export
└── web/
    ├── __init__.py      # 新建（docstring-only；白名单行 10）
    ├── session.py       # T05（§3.7）SessionManager / WebSession
    ├── api.py           # T05/T06/T07（§3.8）无状态请求 handler 层
    ├── inspector.py     # T06（§3.10）Runtime Inspector 数据面
    ├── workbench.py     # T07（§3.11）LLM Workbench 数据面
    ├── views.py         # T06/T07（§3.12）服务端 HTML 渲染
    ├── server.py        # T05（§3.12）stdlib http.server 薄壳
    └── static/
        ├── index.html   # T06/T07（§3.12；白名单行 17）
        ├── app.js       # T06/T07（§3.12；白名单行 18；零构建 vanilla）
        └── styles.css   # T06/T07（§3.12；白名单行 19）
```

**导入闭集**（边界方法 4 AST 检查基准；`face t4` 同源）：

```text
presentation/view.py:
    stdlib + engine_v2.core（§2.1 面）
                    + engine_v2.presentation.tactical.layout（tactical 填充
                      分支；ERR-P10-11：原闭集漏行与 §3.1「tactical_domain_id
                      非 None 时填 tactical_overlay」语义面矛盾——ERR-P10-02
                      同类；单向依赖零环）
presentation/text/*:
    stdlib + pydantic + engine_v2.core + engine_v2.llm.adapter
                    + engine_v2.presentation.view（narrator SceneView 签名；
                      ERR-P10-02：原漏行与 §3.2 render/narrate_scene 签名矛盾）
presentation/image/*:
    stdlib + pydantic + engine_v2.core + engine_v2.llm.adapter
                    + engine_v2.presentation.view（contract/director/backend）
presentation/tactical/*:
    stdlib + engine_v2.core（space 组件面）
adapters/web/*:
    stdlib + pydantic + engine_v2.core + engine_v2.llm.adapter
                    + engine_v2.persistence.snapshot
                    + engine_v2.devtools.trace_query
                    + engine_v2.presentation.*（view/text/image/tactical）
                    + engine_v2.adapters.web
禁止 = engine_v2.{modules, content, prompts, dynamics, plugins, runtime,
        context} + src.*（v1 树）+ langgraph + langchain + 12 名推词（D7）
        + random / time / datetime / timeit（D6 零 wall-clock / 零随机；
          ERR-P10-07：原闭集 stdlib 开根未显式排除，机械面补入边界方法 4）
        + 任何其它路径
特例钉（A2）= presentation/text/ ↔ presentation/image/ 零互 import
特例钉（P10-INV-5）= adapters/web/{inspector,workbench}.py 零
        engine_v2.core.entity / core.components 直读 import（链只经
        TraceQuery + session 面）
```

> Spec §44 L2198–2201 树 = presentation/{text,image,tactical} 三子包；
> 本 SOT 另列包级 `view.py`（T01 落位，Spec §8.5/§32 公共派生面，非独立
> 子包——DEV-P10-04 披露）。`adapters/{cli,dsh}` = P11 面，本阶段不建
> （§0.4）。

### 3.1 公共派生面（`presentation/view.py`；T01；导出 5 名）

**来源**：Spec §8.5（L626–638，ViewState = derived data / MUST NOT
authoritative）+ §32.1（L1680–1696，View/Scene Context → Narrator +
VisualDirector 平行结构）+ §45 主流程末端（L2257–2268，View derivation
分叉）；G10-2「结构化 View」唯一来源。

#### `__all__`（逐字按序）

```python
__all__ = [
    "PresentationError",
    "VIEW_SCHEMA_VERSION",
    "SceneView",
    "scene_id_of",
    "derive_scene_view",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `PresentationError` | `Exception` 子类（`__init__(message, *, code: str = "presentation_invalid")`） | presentation + adapters/web 单一错误族（P8 `PersistenceError` 先例）；code 闭集 = {"presentation_invalid", "scene_key_invalid", "intent_schema_invalid", "image_backend_error"}（私有常量 `PRESENTATION_ERROR_CODES` 钉） |
| `VIEW_SCHEMA_VERSION` | `Final[int] = 1` | SceneView.schema 面值 |
| `SceneView` | `TypedDict(total=False)`，10 键（下） | **P10 结构化 ViewState**（JSON-clean 纯 dict，P10-INV-10） |
| `scene_id_of` | `(scene_key: tuple[str, ...]) -> str` | 纯函数：`"scene:" + sha256("|".join(scene_key)).hexdigest()[:12]`；空 key → `PresentationError(code="scene_key_invalid")`（D-P10-12） |
| `derive_scene_view` | `(world: WorldState, *, tactical_domain_id: str \| None = None) -> SceneView` | **纯派生**：WorldState 只读 → view；零反作用（P10-INV-1；A5/t3 世界哈希不变）；零 clock/RNG 参数（tick 取自 world 组件面，D6）；tactical_domain_id 非 None 时填 tactical_overlay（§3.6），否则 None |

**SceneView 10 键（逐字，JSON-clean）**：

| 键 | 型 | 语义 |
|---|---|---|
| `schema` | int | `VIEW_SCHEMA_VERSION` |
| `view_revision` | int | = `world.world_revision`（P10-INV-2 投影；EntityView 先例 state.py:303–310） |
| `scene_id` | str | `scene_id_of(scene_key)`；scene_key = (世界/场景标识, 可见 actor id 排序元组)（D-P10-12；T08 连续性面） |
| `tick` | int | 当前逻辑刻（world 组件面投影） |
| `narrative` | dict | **P9 NarrativeView 5 键兼容面**（tick / scene_text / frames / actors_visible / clock；A7/t6 键名钉）；值 = P10 自派生投影（零 P9 函数调用，D-P10-01） |
| `actors` | list[dict] | 可见 actor 面：`{"id", "name", "position", "mood", "tags"}`（position 按空间域投影；Narrator 与 VisualDirector 的 subjects 共同源） |
| `environment` | dict | 环境描述面：`{"location", "description", "time_of_day", "weather"}`（v1 snapshot():442 环境键语义参照） |
| `tactical_overlay` | dict \| None | §3.6 TacticalLayout dict 或 None |
| `image_slot` | dict \| None | §3.3 ImageSlot；`derive_scene_view` 返回 = None（纯函数，A5 双跑不依赖槽时序）；回投 = 会话层 `apply_image_result` 后单点（W4 实现时 docstring 钉「回投 = 槽唯一写入点」，Leader 终审 Q3 裁定） |
| `clock` | dict | `{"logical_tick", "game_time"}`（P9 NarrativeView.clock 同形） |

> **Leader 终审（SceneView 10 键）**：10 键**全批**。注记：顶层
> `clock` 与 `narrative.clock` 双存合法（后者 = P9 5 键逐字兼容面 A7/t6 钉，
> 前者 = P10 顶层面；非冗余）。

### 3.2 Narrator presentation backend（`presentation/text/narrator.py`；T02；导出 5 名）

**来源**：Spec §32.1（Narrator 支）+ §45 主流程（Narrator → Text）；
输入 = SceneView 唯一（P10-INV-3，G10-2）；LLM 润色 = 可选注入面
（K5 / P10-INV-6）；模板文风参照 v1 `narrative_stylize` 思想（43.1-10，
P9 narration 已承接 text 侧派生——P10 为 presentation 层 backend，
与 P9 模块零耦合）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "NARRATOR_LOGICAL_ROLE",
    "TEXT_SOURCES",
    "TextArtifact",
    "NarratorPresentationBackend",
    "narrate_scene",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `NARRATOR_LOGICAL_ROLE` | `Final[str] = "narrator"` | FakeInferenceBackend 脚本键 logical_role 面值（K8-safe 名） |
| `TEXT_SOURCES` | `Final[tuple[str, ...]] = ("template", "llm")` | artifact.source 闭集 |
| `TextArtifact` | frozen dataclass：`text: str` / `frames: tuple[dict, ...]` / `view_revision: int` / `scene_id: str` / `source: str` | 文本产物；view_revision/scene_id = 派生时 view 面值（§32.3 标签纪律的 text 侧对应）；`to_dict() -> dict`（JSON-clean） |
| `NarratorPresentationBackend` | class：`__init__(self, *, backend: InferenceBackend \| None = None, style: dict \| None = None) -> None`；`render(self, view: SceneView) -> TextArtifact` | 显式注入（零模块级实例）；template 路径 = 确定性模板（scene_text + frames 拼接，零 backend 调用）；llm 路径（backend 非 None）= `generate(InferenceRequest(logical_role=NARRATOR_LOGICAL_ROLE, base_revision=Revision(view["view_revision"]), ...))` 脚本命中 → 文本润色；未命中/坏 JSON → template 面回落（零异常逃逸） |
| `narrate_scene` | `(view: SceneView, *, backend: InferenceBackend \| None = None, style: dict \| None = None) -> TextArtifact` | 模块函数入口（P9 平铺先例）；构造 NarratorPresentationBackend 委托 |

**纯函数面钉（P10-INV-1/3/6）**：签名输入 = `SceneView` 唯一（零
RenderIntent / 零 prose 参数——SC-P10-2 机械面）；`text/` 文件 import
零 `presentation.image.*`（A2 AST）；backend 注入点唯一 = constructor。

### 3.3 RenderIntent / 图像契约（`presentation/image/contract.py`；T03；导出 6 名）

**来源**：Spec §32.2（L1698–1713，RenderIntent 8 字段建议面——本 SOT
逐字采纳为规范）+ §32.3（L1715–1732，图片结果必带 scene_id +
view_revision；过期三策略 display/discard/archive 由 presentation policy
决定）；G10-1 核心面。

#### `__all__`（逐字按序）

```python
__all__ = [
    "RENDER_INTENT_SCHEMA_VERSION",
    "ImageStalePolicy",
    "RenderIntent",
    "ImageArtifact",
    "ImageSlot",
    "apply_image_result",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `RENDER_INTENT_SCHEMA_VERSION` | `Final[int] = 1` | RenderIntent schema 面值 |
| `ImageStalePolicy` | `str` Enum，3 值闭集：`DISPLAY = "display"` / `DISCARD = "discard"` / `ARCHIVE = "archive"` | Spec §32.3 三策略逐字；**默认策略 = DISCARD**（D-P10-11 安全默认） |
| `RenderIntent` | frozen dataclass，8 字段 = Spec §32.2 逐字：`scene_id: str` / `view_revision: int` / `subjects: tuple[dict, ...]` / `environment: dict` / `camera: dict` / `mood: str` / `continuity_refs: tuple[str, ...]` / `style_refs: tuple[str, ...]`；`to_dict() -> dict`（JSON-clean，A9/t5） | 渲染意图（§32.2 规范面）；subjects = view.actors 投影；camera = 确定性缺省面（模板路径 `{"type": "fixed", "framing": "medium"}`，LLM 路径可覆盖——脚本化） |
| `ImageArtifact` | frozen dataclass：`artifact_id: str` / `scene_id: str` / `view_revision: int` / `media_type: str` / `payload: bytes` / `continuity_refs: tuple[str, ...]` / `style_refs: tuple[str, ...]` | **§32.3 必带标签面**：scene_id + view_revision（= 请求刻 intent 面值，P10-INV-2 载体）；media_type 闭集 = {"image/x-ppm"} 单值（参考面；私有常量 `IMAGE_MEDIA_TYPES` 钉；Leader 终审 Q8 裁定：x- 前缀 = RFC 6838 实验类型惯例，与伪图像参考面语义一致，零新依赖） |
| `ImageSlot` | `TypedDict`：`artifact_id: str` / `scene_id: str` / `view_revision: int` / `stale: bool` / `archived: bool` / `media_type: str` / `byte_length: int` | **SceneView.image_slot 形状**；`view_revision` = 显示时当前 view 面值（槽恒随当前 view，**绝不等于过期 artifact 的旧值**——G10-1「不错误覆盖」的槽面表达）；bytes 不入槽（JSON-clean，INV-10；字节存会话层 current_image） |
| `apply_image_result` | `(current_slot: ImageSlot \| None, artifact: ImageArtifact, current_view: SceneView, *, policy: ImageStalePolicy = ImageStalePolicy.DISCARD) -> ImageSlot \| None` | **纯函数**（D6）；新鲜判定 = `artifact.view_revision == current_view["view_revision"] and artifact.scene_id == current_view["scene_id"]`；新鲜 → 槽（stale=False, archived=False, view_revision=当前）；过期（core `is_stale`(revision.py:78) 或 scene 不符）→ 按 policy：DISCARD = 返回 current_slot 原样（无槽则 None，**零覆盖**）；DISPLAY = 新槽（stale=True, archived=False, view_revision=当前）；ARCHIVE = 新槽（stale=True, archived=True, view_revision=当前） |

### 3.4 VisualDirector（`presentation/image/director.py`；T03；导出 3 名）

**来源**：Spec §32.1（VisualDirector 支）+ §32.2（意图契约消费）+
§45 主流程（VisualDirector → Image）；输入 = SceneView 唯一
（P10-INV-3，G10-2）；LLM 面 = 注入脚本（K5）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "VISUAL_DIRECTOR_LOGICAL_ROLE",
    "VisualDirector",
    "derive_render_intent",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `VISUAL_DIRECTOR_LOGICAL_ROLE` | `Final[str] = "visual_director"` | 脚本键 logical_role 面值（K8-safe 名） |
| `VisualDirector` | class：`__init__(self, *, backend: InferenceBackend \| None = None, style_refs: tuple[str, ...] = ()) -> None`；`plan(self, view: SceneView, *, continuity: Sequence[RenderIntent] = ()) -> RenderIntent` | 显式注入（零模块级实例）；模板路径 = 纯投影（subjects/environment 自 view；mood = 末帧 frame.mood 非空取之，否则 "calm"；camera 缺位面）；llm 路径 = 脚本命中 JSON → 8 字段校验（违例 → `PresentationError(code="intent_schema_invalid")`）；`continuity_refs` = continuity 尾 ≤3 条的 scene_id 序（T08 连续性面） |
| `derive_render_intent` | `(view: SceneView, *, backend: InferenceBackend \| None = None, style_refs: tuple[str, ...] = (), continuity: Sequence[RenderIntent] = ()) -> RenderIntent` | 模块函数入口；构造 VisualDirector 委托 |

**纯函数面钉**：签名输入 = SceneView 唯一（P10-INV-3；SC-P10-2）；
`image/` 文件 import 零 `presentation.text.*`（A2 AST）；零 wall-clock。

### 3.5 image backend（`presentation/image/backend.py`；T04；导出 5 名）

**来源**：Spec §32.2–32.3（backend 消费 RenderIntent、产出携标签
artifact）；零真实图像依赖（S4 预裁决，D-P10-02）——参考 backend =
stdlib 确定性伪图像（PPM P3 纯文本面）+ 测试 fake；真实生成 = P11+。

#### `__all__`（逐字按序）

```python
__all__ = [
    "IMAGE_BACKEND_KINDS",
    "ImageBackend",
    "DeterministicImageBackend",
    "FakeImageBackend",
    "render_intent_to_ppm",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `IMAGE_BACKEND_KINDS` | `Final[tuple[str, ...]] = ("deterministic", "fake")` | P10 参考 backend 闭集（真实 backend = P11+，S4 人工面） |
| `ImageBackend` | Protocol：`render(self, intent: RenderIntent) -> ImageArtifact`（同步面；「异步过期」= 会话层在 artifact 到达刻对当前 view 调 apply_image_result（§3.3），backend 自身无时钟状态） | backend 契约（注入面；零全局实例） |
| `DeterministicImageBackend` | class：`__init__(self, *, width: int = 64, height: int = 32) -> None`（width/height ≤ 0 → ValueError）；`render(self, intent: RenderIntent) -> ImageArtifact` | **stdlib 伪图像参考面**：PPM P3（`"P3\n{w} {h}\n255\n"` + w×h×3 十进制分量）；背景色 = environment 哈希映射、每 subject 一矩形 = subject id 哈希映射、mood = 边框色——全部 = 确定性哈希投影（D6：同 intent 同字节，A10/t2）；artifact 标签 = intent 面值（§32.3）；零第三方 import（face t4 钉） |
| `FakeImageBackend` | class：`__init__(self) -> None`；`render(self, intent: RenderIntent) -> ImageArtifact`；`intents` property（只读调用史） | 测试面（P6 FakeInferenceBackend 先例对称）：payload = `scene_id.encode() + b"\x00" + str(view_revision).encode()`（回显钉，t4）；`intents` 供断言（零像素逻辑） |
| `render_intent_to_ppm` | `(intent: RenderIntent, *, width: int = 64, height: int = 32) -> bytes` | 纯函数（DeterministicImageBackend 的核心投影，独立导出供 face/AD 对抗面直接钉） |

### 3.6 Tactical 最小面（`presentation/tactical/layout.py`；T04 波；导出 3 名）

**来源**：Plan §19 目标「Text / Image / Tactical presentation 平行结构」
+ Spec §44 L2201（presentation/tactical/）；**G10 无 tactical 专属自动
判据**（简报 §8.4）→ 最小面 = 结构化布局 dict（JSON-clean，无渲染）
（D-P10-04）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "TACTICAL_LAYOUT_SCHEMA_VERSION",
    "TacticalLayout",
    "build_tactical_layout",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `TACTICAL_LAYOUT_SCHEMA_VERSION` | `Final[int] = 1` | layout.schema 面值 |
| `TacticalLayout` | `TypedDict`：`schema: int` / `view_revision: int` / `domain_id: str` / `grid: dict \| None` / `cells: list[dict]` / `actors: list[dict]` / `mode: dict \| None` | JSON-clean 布局面：grid = 域网格参数（GridSpace 域 = {"cols","rows"}；GraphSpace 域 = {"nodes","edges"} 摘要）；cells = 占据单元格；actors = 域内 actor 位置面；mode = 当前 GameplayMode overlay id 面（core gameplay_mode 组件只读投影，缺失 → None） |
| `build_tactical_layout` | `(world: WorldState, *, domain_id: str = "default") -> TacticalLayout` | 纯函数：读 core space 组件面（SPACES_COMPONENT:447 / decode_spaces:492 / GraphSpace:256 / GridSpace:350——§2.1；`entity_domain_positions`:505 = F2 冻结面坑〔G10 勘误链〕，消费经 W1 规避模式：components 原始字段面 + decode_spaces）；域缺席 → ValueError 族错误（layout.py 私有具名类，`code == "scene_key_invalid"` 钉值；ERR-P10-13：原钉 `PresentationError` 与 §3.0 闭集 + ERR-P10-11 零环裁定构成 view↔tactical 顶层互 import 环，双 import 序运行时 ImportError，dev 实测）；零反作用（A11/t3）；**零 modules/space.py import**（hex 几何 = 域内 GraphSpace 既有边表，P9 已映射） |

### 3.7 Web 会话层（`adapters/web/session.py`；T05；导出 6 名）

**来源**：43.2-8「Web singleton session」移除（L2081）+ 43.3「web
session lifecycle」重写（L2095）+ G10-3（Plan L842）；v1 语义参照 =
GameSession（app.py:106）/ handle_command（~178–200）/ snapshot():442。
**EngineInstance 语义落点**：每会话持一个 WorldState 实例 + 注入宿主
驱动（D-P10-05）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "SESSION_COMMANDS",
    "TickDriver",
    "TemplatePlayerPolicy",
    "WebSession",
    "SessionManager",
    "SessionNotFoundError",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `SESSION_COMMANDS` | `Final[tuple[str, ...]] = ("/help", "/status", "/idid", "/see", "/hear", "/feel", "/save", "/stop")` | 命令闭集 8 名（v1 handle_command 语义参照 + v1 help 文案 /stop 面；v1 help 文案 /c 别名**不承接**——v1 文案/代码不一致披露〔Leader 终审 Q5 裁定：不承接〕，P10 闭集 8 名钉，t6） |
| `TickDriver` | Protocol：`advance(self, world: WorldState) -> None` | 宿主循环注入点（**P10 只 Protocol + conftest 最小宿主**〔Leader 终审 Q6 裁定〕；生产 = P1 runtime 面（未来）；测试 = conftest 最小宿主，§6.2）；P10 零宿主循环实现（§0.4 非范围） |
| `TemplatePlayerPolicy` | class：`__init__(self) -> None`；`decide(self, *, world: WorldState, text: str) -> ActionProposal` | 实现 core PlayerPolicy 面（behavior_policy.py:70）的**确定性模板**：自由文本 → talk ActionProposal（参数含原文本；零 LLM，K5）；命令文本不经过 policy（§3.8 先分流） |
| `WebSession` | class：`__init__(self, session_id: str, world: WorldState, driver: TickDriver, *, player_policy: PlayerPolicy \| None = None, image_backend: ImageBackend \| None = None, stale_policy: ImageStalePolicy = ImageStalePolicy.DISCARD, trace_records: Sequence[TraceRecord] = (), save_sink: object \| None = None) -> None`；方法 `state_snapshot() -> dict[str, object]` / `step(player_input: str) -> dict[str, object]` / `image() -> ImageArtifact \| None` / `view() -> SceneView` / `close() -> None` | 一会话 = (WorldState 实例 + 注入驱动 + presentation 状态：SceneView 缓存 / RenderIntent 史（continuity 源）/ current_image + ImageSlot / TraceQuery / 存档名表)；**零模块级实例**（P10-INV-4）；`step` = 命令闭集分流（/save = P8 dump:133 经注入 save_sink 落位——sink 缺省 = 内存 dict，零默认磁盘写）｜自由文本 = TemplatePlayerPolicy → driver.advance → 重派生 view +（image_backend 非 None 时）derive_render_intent → render → apply_image_result（§3.3 默认 DISCARD）→ 新 state_snapshot；`state_snapshot` = JSON-clean（INV-10）~24 键面（v1 snapshot():442 语义参照：started / tick / view_revision / scene_id / narrative / player 面 / recent_events（event 投影 ≤8 条）/ can_continue / has_long_image_task（v1 残留 `has_long_task` v2 改名 = P10 长任务 = 图像生成任务，语义对齐）…；键名闭集 = 私有常量 `SESSION_SNAPSHOT_KEYS`（t3 断言键集 == 常量，不硬编码列表）；~24 键具体清单于 W4 dev brief 由 session.py docstring 逐键钉（同 P9 模块常量钉机制；Leader 终审 Q4 裁定） |
| `SessionManager` | class：`__init__(self, *, driver_factory: Callable[[], TickDriver] \| None = None, image_backend_factory: Callable[[], ImageBackend] \| None = None) -> None`；方法 `create_session(self, world: WorldState, *, session_id: str \| None = None, **kwargs: object) -> str` / `load_session(self, session_id: str, payload: str \| bytes) -> str` / `get(self, session_id: str) -> WebSession` / `list_sessions(self) -> tuple[str, ...]` / `close(self, session_id: str) -> None` | **多会话容器**（P10-INV-4 正面：显式实例，由 api 层/宿主注入——零模块级 `session = SessionManager()`）；会话隔离 = 独立 dict 槽（零跨会话共享可变状态，A12/t2）；`load_session` = P8 `load_persistence_snapshot`（:143）+ 版本检查（:176）→ 新会话（world 重建自快照）；session_id 缺省 = uuid4().hex（stdlib；**身份标签例外**——P10 唯一非确定性默认，测试必须显式传 session_id〔DEV-P10-05，Leader 终审 §4，§8.4 登记〕） |
| `SessionNotFoundError` | `Exception`（`__init__(session_id: str) -> None`） | 错误族成员（映射 API 404 面，§3.8） |

### 3.8 无状态请求 handler 层（`adapters/web/api.py`；T05/T06/T07；导出 5 名）

**来源**：v1 路由面（app.py:230–258）语义参照 + D-P10-03（协议无关
handler = 纯函数，socket/线程零进入测试）；G10-3 行为宿主面。

#### `__all__`（逐字按序）

```python
__all__ = [
    "WEB_ROUTES",
    "WebApiError",
    "WebResponse",
    "handle_web_request",
    "resolve_static_name",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `WEB_ROUTES` | `Final[tuple[tuple[str, str], ...]]`，9 行：`("GET","/")` / `("GET","/api/sessions")` / `("POST","/api/sessions")` / `("GET","/api/sessions/{id}/state")` / `("POST","/api/sessions/{id}/action")` / `("GET","/api/sessions/{id}/image")` / `("GET","/api/inspector/{id}")` / `("GET","/api/workbench/{id}")` / `("GET","/static/{name}")` | 路由闭集（t1 钉）；`{id}` = session_id 段；`{name}` = 静态文件名（仅静态 3 名，resolve_static_name 钉） |
| `WebApiError` | `Exception`（`status_code: int` / `detail: str`；v1 WebUIError:38 先例） | API 层单一错误族；status 闭集 = {400, 404, 409, 500}（私有常量 `WEB_ERROR_STATUSES` 钉，AD-P10-1 面） |
| `WebResponse` | frozen dataclass：`status: int` / `content_type: str` / `payload: str \| bytes` | 响应载体（content_type ∈ {"application/json", "text/html; charset=utf-8", "image/x-ppm", "text/plain; charset=utf-8", "text/css"}） |
| `handle_web_request` | `(method: str, path: str, body: object, *, manager: SessionManager) -> WebResponse` | **纯函数（相对 manager）**：路由匹配 → 会话操作（manager 注入，P10-INV-4）→ WebResponse；JSON 面 = 信封 `{"ok": bool, ...}`（P8 CLI 信封形状参照）；未知路由 → 404 信封；坏 body（非 dict / 键缺）→ 400 信封；SessionNotFoundError → 404 信封；session 暂停中 step → 409 信封（AD-P10-1 面）；**零模块级状态**（t3/gate t3 AST 钉） |
| `resolve_static_name` | `(name: str) -> str` | 静态名 → 闭集 3 名（index.html / app.js / styles.css）；越界/路径穿越 → WebApiError(400)（v1 `_safe_*_path` 路径安全思想承接，app.py 私有面先例） |

### 3.9 静态前端面（`adapters/web/static/`；T06/T07；3 文件，白名单行 17–19）

- `index.html`：三页导航壳（play / inspector / workbench）；零外部资源
  （无 CDN / 无字体 / 无 npm）；`<script src="app.js">` 唯一引用。
- `app.js`：vanilla JS（v1 app.js 770 行零构建先例）；fetch 轮询
  `/api/sessions/{id}/state`（play 页）+ 一次性 GET inspector/workbench
  JSON → `document` 渲染（`textContent` 优先，`innerHTML` 零使用——
  注入面收敛）；≤ 200 行；D2 行宽；D3 零 0x5C 0x62。
- `styles.css`：最小样式（信息层次 = G10-5 人工面支撑：标题/区块/表格
  层级）；≤ 100 行。
- **行数硬上限（Leader 终审 Q10 裁定）**：`app.js` ≤ 200 行 /
  `styles.css` ≤ 100 行；超限 = 该波 BLOCK 候选；确不足先登记
  DEV-P10-NN 并经 Leader 终审放宽（零静默超限）。
- **机械钉（face t6）**：`src/` 全树零 `package.json` /
  `package-lock.json` / `bun.lockb` / `vite.config.*` / `webpack*`；
  static 文件集 == 3 名闭集；app.js 零 `import` / `require` /
  `document.write` 语法（AST-lite 行扫描）。

### 3.10 Runtime Inspector 数据面（`adapters/web/inspector.py`；T06；导出 3 名）

**来源**：Spec §37（L1869–1884，12 项 SHOULD——本 SOT 全 12 项最小化
承接）；数据源 = P8 冻结 trace 面唯一（P10-INV-5；G10-4）；§37 与
TraceQuery 方法对应：Effect chain → committed_transactions / Event chain
→ domain_events / authority decision → authority_decisions / producer →
by_producer / causal root → causal_chain / revision timeline →
revision_timeline / development intervention history →
intervention_history（P8 trace_query 模块 docstring「Spec §37 七项具体
方法」先例）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "INSPECTOR_SECTIONS",
    "build_inspector_view",
    "inspect_event",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `INSPECTOR_SECTIONS` | `Final[tuple[str, ...]]`，12 名（Spec §37 逐字序）：`world_state` / `runtime_state` / `scheduler` / `active_action` / `effect_chain` / `event_chain` / `authority_decision` / `producer` / `causal_root` / `revision_timeline` / `branch_replay` / `intervention_history` | 12 节闭集（t1 钉：视图键集 == 12 名） |
| `build_inspector_view` | `(session: WebSession) -> dict[str, object]` | 纯投影：world_state = state_snapshot 子面 / runtime_state + scheduler + active_action = world 组件面只读投影（RuntimeState:192 / Scheduler 状态 / ActiveAction 面）/ effect_chain = committed_transactions 投影 / event_chain = domain_events 投影 / authority_decision = authority_decisions 投影 / producer = by_producer 键集 / causal_root = 最近事件 causal_chain 摘要 / revision_timeline = revision_timeline 投影（单调钉 t3）/ branch_replay = save 名表 + replay 可用性标志（Spec §46-9 完整 UI = 非范围）/ intervention_history = intervention_history 投影；**零直读 WorldState 内部构链**（INV-5；链全经 TraceQuery） |
| `inspect_event` | `(session: WebSession, event_id: str) -> dict[str, object]` | **G10-4 核心面**：`TraceQuery.causal_chain(event_id)`（trace_query.py:199）→ `CausalChain.to_dict()`（:75）全量投影（event / transaction / effects / producers / action_refs / intervention_refs）；事件缺席 → TraceQueryError 透传映射 404 信封（AD-P10-1 面） |

### 3.11 LLM Workbench 数据面（`adapters/web/workbench.py`；T07；导出 3 名）

**来源**：Spec §38（L1888–1901，10 项 SHOULD——本 SOT 最小化承接：
prompt 面 + logical profile + model + token + structured output 面；
critic/repair、replay with different model、A/B = 非范围标志位 false）；
数据源 = backend 调用史 (request, response) 对（测试经
`backend.generate` 显式收集 pairs；FakeInferenceBackend.calls =
请求史只读面，K5 脚本面；W4 web 会话无 LLM 面——§3.7 权威签名
零推理参数，ERR-P10-15）。

#### `__all__`（逐字按序）

```python
__all__ = [
    "WORKBENCH_SECTIONS",
    "build_workbench_view",
    "prompt_history",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `WORKBENCH_SECTIONS` | `Final[tuple[str, ...]]`，8 名：`assembled_prompt` / `prompt_layers` / `context_provenance` / `token_usage` / `logical_profile` / `resolved_model` / `structured_output` / `critic_repair` | 8 节闭集（t 钉）；Spec §38 之 replay / A/B 2 项 = 非范围（§0.4） |
| `build_workbench_view` | `(calls: Sequence[tuple[InferenceRequest, InferenceResponse]]) -> dict[str, object]` | 纯投影：assembled_prompt = 最近 InferenceRequest.messages 投影 / prompt_layers = messages 层序 / context_provenance = base_revision + prompt_metadata_ref（InferenceRequest:98 11 字段面）/ token_usage = 最近 InferenceResponse.input_tokens/output_tokens（None 显式保留：FakeInferenceBackend 未测 = None，None = 「未测量」≠ 0（零估值捏造），KBC-7 语义；Leader 终审 Q9 裁定）/ logical_profile = logical_role / resolved_model = request.model（K8：测试值 `fake-model-1`，t2 钉零推词）/ structured_output = response.text（解析失败原样保留）/ critic_repair = {"supported": false}（非范围标志）〔签名重钉 ERR-P10-15：calls pairs 面，非 session〕 |
| `prompt_history` | `(calls: Sequence[tuple[InferenceRequest, InferenceResponse]]) -> tuple[dict, ...]` | 调用史投影：每条 = `{"seq", "logical_role", "base_revision", "model", "prompt_metadata_ref", "response_text"}`（seq = calls 序 1-based，与 FakeInferenceBackend 脚本键同址——T07 核心钉 t1）〔签名重钉 ERR-P10-15：calls pairs 面，非 session；response_text = response.text〕 |

### 3.12 服务端渲染 + 薄壳服务（`adapters/web/views.py` + `server.py`；T06/T07/T05；导出 3 + 2 名）

**来源**：D-P10-07（stdlib `string.Template`，零 Jinja2）+ D-P10-03
（薄壳 = stdlib `http.server.ThreadingHTTPServer`，v1 create_server:319
先例）；G10-5 人工面（GUI 信息层次）承载。

`views.py` `__all__`（逐字按序）：

```python
__all__ = [
    "PAGE_NAMES",
    "PAGE_TEMPLATES",
    "render_page",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `PAGE_NAMES` | `Final[tuple[str, ...]] = ("index", "inspector", "workbench")` | 页面闭集（D-P10-03：3 页） |
| `PAGE_TEMPLATES` | `Final[dict[str, str]]`：3 个 `string.Template` 源（play 页 = 状态表 + 输入框 + 图像位；inspector 页 = 12 节折叠区；workbench 页 = prompt 史表） | 模板源（服务端持有；D2 行宽；D3 零 0x5C 0x62） |
| `render_page` | `(page: str, **context: object) -> str` | `Template.safe_substitute` + 全部值经 `html.escape`（注入面收敛）；page 越界 → `PresentationError` |

`server.py` `__all__`（逐字按序）：

```python
__all__ = [
    "create_web_server",
    "run_web_server",
]
```

| 名 | 形 | 语义 |
|---|---|---|
| `create_web_server` | `(manager: SessionManager, *, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer` | stdlib 薄壳（v1 create_server:319 先例）：handler 内 = `handle_web_request` 委托（§3.8）；**manager 注入，零模块级服务/会话**（P10-INV-4）；测试零调用（零 socket 面，D-P10-03） |
| `run_web_server` | `(manager: SessionManager, *, host: str = "127.0.0.1", port: int = 8000) -> None` | 进程入口（薄壳 `serve_forever`）；零 IP 探测（v1 main.py 面 = 非范围） |

### 3.13 世界源与夹具（零新增 fixture 文件）

- **机械面世界源 = conftest 内存构建**（§6.2）：2 actor（player + npc）+
  1 location + hex 域 3×3（GraphSpace 注册，P9 A12 钉值 16 无向边参照）
  + 方格域对照 + 已知事件序列（3 次 commit：talk 提案 → 效果 → 事件；
  move → 事件；属性变更 → 事件）→ trace_records（TraceRecord 直构，
  core trace.py:113 面）+ 注入 FakeInferenceBackend 脚本。
- **P9 3 样例项目 = 只读参照**（S11 人工面世界源：gate 时点 Leader 以
  galgame 样例驱动 web 会话验收 G10-5/6/7）；机械面零 import / 零
  消费（P10-INV-9 冻结对象）。
- **零新增 YAML fixture**（D-P10-06；白名单无 fixture 行）。

### 3.14 T08 stale-image / scene-continuity 视觉测试落位

- 机械面（自动）：`test_image_backend.py` t6–t8（策略三面）+
  `test_view.py` t5（scene_id 稳定性：同 location 同 actor 集 → 同
  scene_id；actor 集/location 变更 → 异 id）+ `test_render_intent.py`
  t4（continuity_refs 传递）+ AD-P10-3（stale 连发）。
- 多模态人工面（S11）：gate 时点 Leader 驱动 web 会话（galgame 样例
  世界源）截图/目视判定 G10-6/7；判定记录入 gate 报告
  「Human review required」（Plan §21 L901）。

---

## §4 决策登记（D-P10-01..12；五段：问题/备选/选择/理由/机械验证面；**12 条全批准**）

> **状态**：12 条全批准（Leader 终审并入；D-P10-05 附 DEV-P10-05 / D-P10-10 待 G10 实测重算）。

### D-P10-01 View 与 P9 NarrativeView 关系（简报 §8.1）

- **问题**：P10 SceneView 是否复用/扩展 `modules/narration.py::
  NarrativeView`（P9 已冻结非权威派生面）？
- **备选**：(a) 修改/扩展 P9 模块（否决：D5 冻结 + G9 收口时点风险）；
  (b) 不复用、并行第二套 ViewState（否决：双源分裂，G10-2「结构化
  View 唯一」语义弱化）；(c) **形状复用、函数不消费**（采纳）。
- **选择**：SceneView.narrative = 与 P9 NarrativeView **5 键同名兼容**
  的 dict（tick / scene_text / frames / actors_visible / clock）；值 =
  P10 自派生投影（零 P9 函数调用、零 `engine_v2.modules` import）；
  P9 模块零改动。
- **Leader 终审**：批准（备注：形状复用、函数不消费；前置 = G9 收口复测 5 键名〔DEV-P10-01 既有；已闭合，§2.4〕）。
- **理由**：P9 4 导出 = G9 冻结非权威面（P9-INV-8 同族）；键名兼容 =
  Narrator 消费面与 P9 样例叙事面可互换阅读；零 import = 解耦
  （P9 W6 实现细节漂移不传导，R5）。
- **机械验证面**：A7/t6（键名钉）+ 边界方法 4（modules 零 import）+
  G9 收口复测（DEV-P10-01）。

### D-P10-02 image backend 参考实现（简报 §8.2）

- **问题**：零真实图像生成依赖（S4 预裁决）下，参考 backend = 什么？
- **备选**：(a) SVG（文本面，但 XML 转义面大、无固定像素钉面）；
  (b) PNG bytes（stdlib zlib 可造，但 chunk/CRC 部件多）；
  (c) **PPM P3 纯文本伪图像**（采纳）；(d) 纯 dict 伪图像（无字节面，
  T08「视觉」连续性与图像端点面缺失）。
- **选择**：DeterministicImageBackend = stdlib PPM P3（头部
  `"P3\n{w} {h}\n255\n"` + 十进制分量），颜色 = intent 字段确定性哈希
  投影（背景/subject 矩形/mood 边框）；FakeImageBackend = 回显 payload
  + intents 调用史；真实生成 backend = P11+ / S4 人工面。
- **Leader 终审**：批准（备注：PPM P3 伪图像面；S4 触发面保留〔SC-P10-3〕）。
- **理由**：PPM P3 = 最简固定文法（零转义面）、纯文本可 grep 可钉
  （A10/t1 头部钉）、字节确定性可双跑（D6）、零依赖（S4）。
- **机械验证面**：A10（t1 头部钉 / t2 双跑 / t3 scene 敏感）+ face t4
  （图像库 import 零）+ S4 触发面（SC-P10-3）。

### D-P10-03 Web 服务框架（简报 §8.3）

- **问题**：零新依赖（S4）下 web 面服务形态？
- **备选**：(a) FastAPI/Flask（否决：S4 新依赖）；(b) 纯 JSON 文件交换
  （否决：T06/T07 = web view，G10 人工判据需可浏览面）；(c)
  **协议无关 handler 层（纯函数）+ stdlib http.server 薄壳（可选常驻）**
  （采纳）；(d) handler 内嵌 server 模块（否决：测试需 socket/线程）。
- **选择**：`api.py::handle_web_request(method, path, body, *, manager)`
  = 纯函数（零 socket / 零线程 / 零模块级状态）；`server.py` =
  stdlib ThreadingHTTPServer 薄壳（manager 注入，人用可选面，测试零
  调用）；前端 = 静态 3 文件（§3.9）。
- **Leader 终审**：批准（备注：无状态 handler 纯函数 + stdlib 薄壳〔测试零调用〕）。
- **理由**：测试面 = 直接函数调用（K5 同纪律：零 I/O 零网络）；
  G10-3 单例检查落 handler 层 AST 即完整；薄壳 = v1 create_server:319
  先例（stdlib 已在 v1 使用，零新依赖）。
- **机械验证面**：A3（AST 零模块级实例化）+ face t4（http.server 仅
  server.py 消费）+ 路由闭集 t1。

### D-P10-04 Tactical presentation 最小面（简报 §8.4）

- **问题**：G10 无 tactical 专属自动判据 → tactical/ 建到什么深度？
- **备选**：(a) 零 tactical 包（否决：Plan §19 目标「Text / Image /
  Tactical 平行结构」显式 + Spec §44 L2201 列名）；(b) tactical SVG
  渲染（否决：渲染 = image 面越界，且无 G10 锚的渲染面 = 无判据表面）；
  (c) **结构化布局 dict（JSON-clean，无渲染）**（采纳）。
- **选择**：`tactical/layout.py` 3 导出（§3.6）：TacticalLayout TypedDict
  + build_tactical_layout 纯函数 + schema 版本；几何源 = core space
  组件面只读（零 P9 modules import）。
- **Leader 终审**：批准（备注：结构化布局 dict、零渲染；无判据不造面）。
- **理由**：满足平行结构目标 + 可被 inspector/web 消费（A11 JSON-clean
  钉）；深度克制 = 无判据不造面（SC 纪律）。
- **机械验证面**：A11（t1 hex / t2 grid / t3 零反作用）+ 边界方法 4。

### D-P10-05 SessionManager 语义（简报 §8.5）

- **问题**：会话 = 什么？多会话如何隔离？
- **备选**：(a) 会话 = 仅 WorldState（否决：T06/T07 需 runtime/scheduler
  投影面 + presentation 缓存，过薄）；(b) 全局 SessionManager 单例
  （否决：P10-INV-4 违反——单例上移一层）；(c) **注入式多会话容器**
  （采纳）。
- **选择**：Session = (WorldState 实例 + 注入 TickDriver 宿主 + 注入
  presentation 组件（image_backend / stale_policy）+ presentation 状态
  （view 缓存 / intent 史 / current_image + slot / TraceQuery）+ 命令
  闭集处理）；SessionManager = 显式实例（create/load/get/list/close），
  由 api 层/宿主/测试注入；零跨会话共享可变状态；「EngineInstance」
  语义 = 每会话一个 WorldState 实例（Spec §45 主流程宿主面，P1 runtime
  未来承接 TickDriver 生产实现）。
- **Leader 终审**：批准（备注：注入式多会话容器；session_id 缺省 uuid4 例外见
  §8.4 DEV-P10-05〔身份标签例外，P10 唯一非确定性默认；测试必须显式传
  session_id〕）。
- **理由**：43.2-8 移除对象 = 「singleton session」，正面 = 显式多会话
  容器；注入纪律 = D6 确定性 + A12 隔离双跑。
- **机械验证面**：A3（AST）+ A12（t2 隔离 / t3 JSON-clean / t4 P8
  载入）+ AD-P10-1。

### D-P10-06 P10 包落位与文件布局

- **问题**：presentation / adapters-web 文件级落位？
- **备选**：(a) presentation 每子包多文件膨胀（否决：T02–T04 各 1 文件
  即可，过度结构）；(b) **包级 view.py + 三子包平铺单文件**（采纳）。
- **选择**：§3.0 包树（src 19 新文件：presentation 9 + adapters/web 7 +
  static 3）；测试 16 新文件 + 2 M（边界锚 + skeleton 计数面；§11 白名单
  38 行；ERR-P10-04：原「15」= ERR-P10-03 同类误计残留，§11 行 20–35
  实测 16 个 tests A；ERR-P10-09/10/11 勘误增量）；零 fixture
  文件（§3.13）。
- **Leader 终审**：批准（备注：包级 view.py 披露〔DEV-P10-04 既有〕）。
- **理由**：与 P9 单包平铺纪律（D-P9-01）同构；Spec §44 树逐字对齐
  （+ 包级 view.py 披露，DEV-P10-04）；白名单可控（38 行 vs P9 47 行
  同量级）。
- **机械验证面**：face t1/t2 + 边界方法 1/2 + 门④② diff。

### D-P10-07 HTML 渲染 = stdlib string.Template（零 Jinja2）

- **问题**：服务端 HTML 渲染用什么？
- **备选**：(a) Jinja2（v1 冻结依赖，可用但引入模板语法面 + 消费面
  扩集）；(b) **stdlib `string.Template` + `html.escape`**（采纳）；
  (c) f-string 拼接（否决：转义/注入面纪律弱，不可闭集钉）。
- **选择**：views.py = Template.safe_substitute + 值全量 html.escape；
  模板源 3 个（PAGE_TEMPLATES）；零 Jinja2 import（import 闭集 §3.0
  不列 jinja2）。
- **Leader 终审**：批准（备注：string.Template + html.escape 单点转义）。
- **理由**：import 闭集保持 stdlib + pydantic（D4 最窄面）；转义面 =
  escape 单点（注入面收敛，app.js 侧 innerHTML 零使用对钉）。
- **机械验证面**：face t4（jinja2 import 零）+ render_page 行宽/D3 钉
  （门④⑤）。

### D-P10-08 v1 web/ui 文件保持冻结（43.2-8 移除 = v2 不存在，非删除）

- **问题**：P10 是否删除 `src/web/`（v1 singleton 宿主）？
- **备选**：(a) 删除 v1 web 文件（否决：v1 树 = Phase 0 冻结参照 +
  P9-INV-1 v1 路径集延续；删除 = 破坏 v1 测试 13 函数宿主 + 3054 基线
  漂移）；(b) **v1 全冻结，43.2-8 移除语义 = v2 侧不存在**（采纳）。
- **选择**：v1 文件零修改零删除（P10-INV-9）；G10-3「Web 不存在
  module-level singleton World」检查域 = `src/engine_v2/adapters/web/`
  + `src/engine_v2/presentation/`（v2 web 面）；v1 app.py:221 /
  renderer.py:7 单例 = 冻结反例锚（A3 docstring 引用）。
- **Leader 终审**：批准（备注：v1 全冻结；检查域 = v2 web/presentation 树）。
- **理由**：冻结纪律延续（P9-INV-1 先例）；移除面 = 架构假设移除
  （Spec §43.2 = 「应移除的核心假设」，非文件清单）；v1 树自含可运行
  （其测试独立在基线内）。
- **机械验证面**：A3（v2 域 AST）+ 边界方法 5（v1 哈希清单含 src/web /
  src/ui / web/）+ 门④②（v1 路径零 diff 行）。

### D-P10-09 波次划分 W1–W5（简报 §1 预分定稿）

- **问题**：8 任务包 → 5 波怎么切？
- **备选**：(a) 简报 §1 预分原样（采纳）；(b) T01 独立 W0 实现波
  （否决：W0 = 设计波，纪律先例 P9 无 W0 实现）。
- **选择**：W1 = T01（view 核心契约）；W2 = T02 + T03（text 面 + image
  契约/导演）；W3 = T04 + tactical 面（backend + stale + layout）；
  W4 = T05（web 会话/API/渲染/薄壳 + static）；W5 = T06 + T07 + T08
  机械面 + TestP10Boundary 6 方法（锚文件 EOF 纯追加）。波内序 =
  契约 → 消费（W5 内：inspector → workbench → g10 gate → face →
  边界块）。
- **Leader 终审**：批准（备注：波次 7+10+11+11+18 = 57）。
- **理由**：依赖序（view 先于双 backend；contract 先于 backend；
  session 先于 inspector/workbench）；每波结束套件全绿 + 白名单增量 =
  该波文件（P9 §3.18 纪律）。
- **机械验证面**：§10 波次表累计恒等式（7+10+11+11+18 = 57）。

### D-P10-10 计数恒等式（门④期望）

- **问题**：门④ passed 期望 = ？
- **备选**：—（自裁，无设计选择面）。
- **选择**：`G9_final + 63`（63 = 57 平铺 + 6 边界）；G9_final = 3142
  （G9 收口实测，§0.3.1 已回填）→ **3142 + 63 = 3205**（实测重算完成）。
- **Leader 终审**：批准（备注：门④ = G9_final + 63；G9 收口后以实测重算——已重算 = 3205，G10 门③步实测确认）。
- **理由**：P9 门③恒等式同构（基线 + 本阶段新增，各项机械可复数）。
- **机械验证面**：§8.3 恒等式 + 门④③。

### D-P10-11 image stale 默认策略 = DISCARD

- **问题**：Spec §32.3 三策略（display/discard/archive）缺省取哪个？
- **备选**：(a) DISPLAY（展示过期图 + 标记——v1 无对应先例，错场风险
  面大）；(b) ARCHIVE（默认归档——语义重，无消费面）；(c) **DISCARD**
  （采纳）。
- **选择**：`apply_image_result` 与 `WebSession` 缺省
  `policy = ImageStalePolicy.DISCARD`（过期 artifact 零覆盖、零槽）；
  策略可经 SessionManager 工厂面注入切换（三面行为由 t6/t7/t8 钉）。
- **Leader 终审**：批准（备注：DISCARD 安全默认；三面行为 t6/t7/t8 钉）。
- **理由**：G10-1「不错误覆盖当前 view」= 安全默认语义；Spec §32.3
  「由 presentation policy 决定」= 三选保留、缺省收紧。
- **机械验证面**：A1（gate t1 双策略断言）+ t6/t7/t8 + AD-P10-3。

### D-P10-12 scene_id 派生规则

- **问题**：scene_id（§32.2/§32.3 必带 + T08 连续性）如何确定性派生？
- **备选**：(a) 时间戳/UUID（否决：D6 确定性破坏 + 连续性语义缺失）；
  (b) 场景内容哈希 = **scene_key = (世界/场景标识, 可见 actor id 排序
  元组) → sha256 前 12 hex**（采纳）；(c) scenario 声明 scene 表
  （否决：P5 冻结 schema 无 scene 表面，加键 = 越界）。
- **选择**：`scene_id_of(scene_key)` = `"scene:" + sha256("|".join(
  scene_key)).hexdigest()[:12]`；scene_key 组成 = (scenario 世界标识
  投影, tuple(sorted(可见 actor id)))——同 location 同 actor 集 → 同
  scene_id（连续性）；任一变化 → 异 id（错场敏感）。
- **Leader 终审**：批准（备注：sha256 前 12 hex；空 key → PresentationError）。
- **理由**：确定性（D6）+ 零新 schema 面（P5 冻结）+ 敏感性可钉
  （t5 双面：不变同 id / 变化异 id）。
- **机械验证面**：A5/t5 + A10/t3（scene 敏感字节面）+ G10-7 人工面
  支撑（continuity 可追溯）。

## §5 验收面

### 5.1 SC 场景（失败想象 → 机械面）

- **SC-P10-1 Web 层持全局 session**：若实现「顺手」写
  `session = SessionManager()` 或模块级 `world = WorldState(...)`
  → A3（gate t3，AST 模块级实例化/全局绑定扫描）红 → G10-3 FAIL。
- **SC-P10-2 Narrator 吃 prose**：若 text/「顺手」import image/ 或
  `narrate_scene` 签名扩出 RenderIntent/prose 参数
  → A2（gate t2，AST 互 import + 签名面）红；§3.2/§3.4 签名 = SceneView
  唯一（SC 面 = 签名级钉）。
- **SC-P10-3 image backend 引图像库**：若 backend「顺手」import
  PIL/Pillow/其它图像依赖 → 边界方法 4 import 闭集红 + S4 触发
  （停报人工）；face t4 同源。
- **SC-P10-4 stale 覆盖当前槽**：若 `apply_image_result` 漏
  revision 比较（过期 artifact 直接覆盖 slot）→ A1（gate t1 + t6/t7）
  红——DISCARD 面 slot 不变 / DISPLAY 面 slot.view_revision = 当前值
  双面钉死。
- **SC-P10-5 Inspector 旁路直读**：若 inspector「顺手」从
  WorldState 实体内部手搓因果链（绕 TraceQuery）→ P10-INV-5 +
  边界方法 4（inspector/workbench import 特例钉：零 core.entity /
  core.components 直读 import）+ A4（链 = CausalChain.to_dict 形状钉）
  三面红。

### 5.2 A 判据表（12 条：A1–A4 门面条 + A5–A12 辅助面）

> **命名口径**：机械验证面列用短名形 `file.py::tN_<语义>`；规范
> pytest 收集名以 §5.3 1:1 清单为准（12 行一一对应；函数命名规则
> 见 §6.1 引言——`test_<短名>_tN_<语义>`）。
> **结构面说明**：P9 先例将树/台账/K8/闭集结构面编为 A18–A24；冻结版
> 口径 = A 仅 12（门面条 4 + 辅助 8），结构面由
> `test_p10_face.py` t1–t6 + TestP10Boundary 1–4 双钉（无独立 A id），
> 已有独立回归红信号面。
> **Leader 终审（Q1）**：不扩编，保持 12 条——扩编 A id 将破坏 §5.3
> 「每 A 恰 1 函数」1:1 纪律且无新增门面条。

| ID | 可验证陈述 | 机械验证面 |
|---|---|---|
| A1 | G10-1：当前 view_revision=87 时，携 view_revision=83 的 artifact 到达 → 默认策略 DISCARD：当前槽不变（无槽则 None，零覆盖）；DISPLAY 策略：槽 view_revision == 87 且 stale == True（绝不以 83 覆盖） | `test_g10_gate.py::t1_stale_image_no_overwrite`（辅助：`test_image_backend.py` t6/t7） |
| A2 | G10-2：同一 SceneView 输入下 Narrator 与 VisualDirector 各自独立产出（TextArtifact / RenderIntent，双 JSON-clean）；`text/` ↔ `image/` 零互 import（AST） | `test_g10_gate.py::t2_dual_backend_structured_view`（辅助：t5/t3 单元面） |
| A3 | G10-3：`adapters/web/` + `presentation/` 全树 AST：零模块级 `WorldState()` / `SessionManager()` / `WebSession()` / `Scheduler()` / `LogicalClock()` 实例化 + 零模块级 session 全局绑定；检查域 = `src/engine_v2/adapters/web/` + `src/engine_v2/presentation/` 全树 AST，tests/（含 conftest）不入检查域（宿主侧合法构造面；Leader 终审 Q2 裁定）；v1 反例锚 app.py:221 / renderer.py:7 不入检查域 | `test_g10_gate.py::t3_no_module_singleton_world`（行为辅助：t2 多会话隔离） |
| A4 | G10-4：fixture 世界 + 已知事件序列 → `inspect_event(event_id)` 返回链：event 非空 + transaction 非 None + effects ≥1 + producers 非空 + action_refs 非空；数据源 = `TraceQuery.causal_chain`（零旁路） | `test_g10_gate.py::t4_inspector_chain_locator`（辅助：`test_inspector.py` t2） |
| A5 | SceneView = 纯派生：同 WorldState 双跑 → SceneView `json.dumps` 字符串相等；修改 view（含嵌套 dict）后 WorldState 哈希不变 | `test_view.py::t1_deterministic_derive`（辅助 t3） |
| A6 | view_revision 单调投影：view.view_revision == world.world_revision；tick 推进 → 严格递增；`is_stale(Revision(83), Revision(87))` == True、同刻 == False | `test_view.py::t2_view_revision_projection`（辅助 t7） |
| A7 | SceneView JSON-clean（10 键在位，`json.dumps` 零失败）+ `narrative` 键集 == P9 NarrativeView 5 键（tick/scene_text/frames/actors_visible/clock） | `test_view.py::t6_narrative_surface_compat`（辅助 t4） |
| A8 | Narrator K5：template 路径 `FakeInferenceBackend.calls` == ()（零推理调用）；llm 路径脚本命中 (narrator, rev, 1) → artifact.text 含命中文本且 source == "llm" | `test_narrator.py::t2_scripted_llm_path`（辅助 t1） |
| A9 | RenderIntent = Spec §32.2 8 字段逐字（scene_id/view_revision/subjects/environment/camera/mood/continuity_refs/style_refs）+ `to_dict()` JSON-clean | `test_render_intent.py::t1_eight_fields_spec`（辅助 t5） |
| A10 | DeterministicImageBackend 确定性：同 intent 双跑 bytes 相等；PPM P3 头部钉（`"P3\n64 32\n255\n"` 缺省 64×32）；scene 敏感（同 intent 异 scene_id → bytes 异） | `test_image_backend.py::t2_determinism_rerun`（辅助 t1/t3） |
| A11 | tactical layout：hex 域（GraphSpace 3×3，16 无向边参照）与 grid 域（GridSpace）双面产出 JSON-clean layout；修改 layout 后 WorldState 哈希不变 | `test_tactical_layout.py::t1_hex_layout`（辅助 t2/t3） |
| A12 | SessionManager：双会话隔离（A 会话 tick 推进 → B 会话 state 逐键不变）；`state_snapshot` JSON-clean（键闭集钉）；P8 快照 dump→load round-trip（world_revision/tick 相等 + 零版本冲突） | `test_session_manager.py::t2_multi_session_isolation`（辅助 t3/t4） |

### 5.3 A ↔ 平铺函数 1:1 映射（12 行；每 A 恰 1 函数，每门面条函数恰 1 A）

| A | 测试文件::函数（规范收集名） |
|---|---|
| A1 | `test_g10_gate.py::test_g10_gate_t1_stale_image_no_overwrite` |
| A2 | `test_g10_gate.py::test_g10_gate_t2_dual_backend_structured_view` |
| A3 | `test_g10_gate.py::test_g10_gate_t3_no_module_singleton_world` |
| A4 | `test_g10_gate.py::test_g10_gate_t4_inspector_chain_locator` |
| A5 | `test_view.py::test_view_t1_deterministic_derive` |
| A6 | `test_view.py::test_view_t2_view_revision_projection` |
| A7 | `test_view.py::test_view_t6_narrative_surface_compat` |
| A8 | `test_narrator.py::test_narrator_t2_scripted_llm_path` |
| A9 | `test_render_intent.py::test_render_intent_t1_eight_fields_spec` |
| A10 | `test_image_backend.py::test_image_backend_t2_determinism_rerun` |
| A11 | `test_tactical_layout.py::test_tactical_layout_t1_hex_layout` |
| A12 | `test_session_manager.py::test_session_manager_t2_multi_session_isolation` |

> 非 A 平铺函数（57 − 12 = 45）= 模块单元面 + 结构面（face t1–t6）+
> 策略/错误信封辅助面（§6.1 逐表列明，不挂 A 但计入 57）。

---

## §6 测试设计

### 6.1 平铺函数清单（11 文件 × t# 表；合计 **57**）

> 函数名 = `test_<短名>_tN_<语义>`；A 面函数名与 §5.3 逐字一致；
> 布局 = 11 个测试文件（`tests/engine_v2/presentation/` 5 +
> `tests/engine_v2/adapters/web/` 6）+ 3 包 `__init__`（零函数）+
> 2 conftest（零函数）= 16 测试侧文件（白名单行 20–35）。

**`test_view.py`（7）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_view_t1_deterministic_derive` | 同世界双跑 → SceneView json.dumps 字符串相等（A5） |
| 2 | `test_view_t2_view_revision_projection` | view.view_revision == world.world_revision；tick 推进严格递增（A6） |
| 3 | `test_view_t3_zero_reverse_action` | 修改 view 嵌套 dict → WorldState 哈希不变（P10-INV-1） |
| 4 | `test_view_t4_json_clean` | 10 键在位 + json.dumps 零失败（INV-10） |
| 5 | `test_view_t5_scene_id_stability` | 同 location 同 actor 集 → 同 scene_id；actor 集变化 / location 变化 → 异 id（T08 连续性面；D-P10-12） |
| 6 | `test_view_t6_narrative_surface_compat` | view["narrative"] 键集 == P9 NarrativeView 5 键逐字（A7） |
| 7 | `test_view_t7_stale_projection` | is_stale(83, 87) == True / is_stale(87, 87) == False / 87→83 反向 False（A6 辅助） |

**`test_narrator.py`（5）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_narrator_t1_template_zero_backend` | template 路径（backend=None，§3.2 路径选择）：探针 backend（脚本预置命中键、未注入）calls == ()；source == template（A8 辅助；K5；ERR-P10-12 钉文自洽） |
| 2 | `test_narrator_t2_scripted_llm_path` | 脚本 (narrator, rev, 1) 命中 → text 含命中文本 + source == "llm"（A8） |
| 3 | `test_narrator_t3_artifact_tagged` | artifact.view_revision / scene_id == view 面值；to_dict JSON-clean |
| 4 | `test_narrator_t4_determinism_rerun` | 同 view 双跑 → TextArtifact 字段相等 + json.dumps 相等（D6） |
| 5 | `test_narrator_t5_no_image_import` | AST：text/ 文件 import 零 `presentation.image.*`（A2 单元面） |

**`test_render_intent.py`（5）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_render_intent_t1_eight_fields_spec` | 8 字段 == Spec §32.2 逐字（A9） |
| 2 | `test_render_intent_t2_determinism_rerun` | 同 view 双跑 → intent 相等（D6） |
| 3 | `test_render_intent_t3_scripted_llm_path` | 脚本 JSON 命中 → 8 字段落位；坏 JSON → PresentationError（code="intent_schema_invalid"） |
| 4 | `test_render_intent_t4_continuity_refs` | 传 3 条历史 intent → continuity_refs == 尾 3 scene_id 序（T08） |
| 5 | `test_render_intent_t5_json_clean` | to_dict json.dumps 零失败（A9 辅助） |

**`test_image_backend.py`（8）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_image_backend_t1_ppm_header_pin` | 缺省 64×32 字节起首 `"P3\n64 32\n255\n"` + 分量计数 == 64*32*3（A10 辅助） |
| 2 | `test_image_backend_t2_determinism_rerun` | 同 intent 双跑 bytes 相等（A10） |
| 3 | `test_image_backend_t3_scene_sensitivity` | 同 intent 异 scene_id → bytes 异（T08 错场敏感面） |
| 4 | `test_image_backend_t4_fake_echo` | FakeImageBackend payload 回显钉 + intents 调用史 == 提交序 |
| 5 | `test_image_backend_t5_fresh_slot` | 新鲜 artifact → 槽 stale==False / archived==False / view_revision==当前 |
| 6 | `test_image_backend_t6_stale_discard_no_overwrite` | 83→87 DISCARD：无槽 → None；有槽 → 原槽逐键不变（A1 单元面） |
| 7 | `test_image_backend_t7_stale_display_flagged` | 83→87 DISPLAY：槽 view_revision==87 + stale==True（A1 单元面） |
| 8 | `test_image_backend_t8_stale_archive` | 83→87 ARCHIVE：stale==True + archived==True（INV-2） |

**`test_tactical_layout.py`（3）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_tactical_layout_t1_hex_layout` | hex GraphSpace 3×3 域 → grid.nodes/edges 摘要 + cells + actors 钉 + JSON-clean（A11） |
| 2 | `test_tactical_layout_t2_grid_layout` | GridSpace 域 → grid = {"cols","rows"} + 位置钉（A11 辅助） |
| 3 | `test_tactical_layout_t3_zero_reverse_action` | 修改 layout → WorldState 哈希不变（A11 辅助 / INV-1） |

**`test_session_manager.py`（6）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_session_manager_t1_lifecycle` | create → get → list → close；close 后 get → SessionNotFoundError |
| 2 | `test_session_manager_t2_multi_session_isolation` | 双会话：A step 推进 tick → B state_snapshot 逐键不变（A12；G10-3 行为面） |
| 3 | `test_session_manager_t3_snapshot_json_clean` | state_snapshot json.dumps 零失败 + 键闭集 == SESSION_SNAPSHOT_KEYS（~24 键，v1 snapshot():442 语义参照）（A12 辅助） |
| 4 | `test_session_manager_t4_load_from_p8_snapshot` | dump_persistence_snapshot → load_session round-trip：world_revision/tick 相等 + check_persistence_versions 零冲突（A12 辅助） |
| 5 | `test_session_manager_t5_not_found` | get("missing") → SessionNotFoundError（AD-P10-1 面） |
| 6 | `test_session_manager_t6_commands_closed` | SESSION_COMMANDS == 8 名闭集逐字；/status → 数值 modal 面；/stop → paused；paused 中 step → 409 信封（AD-P10-1 面） |

**`test_web_api.py`（5）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_web_api_t1_routes_closed` | WEB_ROUTES == 9 行闭集逐字（method + path pattern） |
| 2 | `test_web_api_t2_action_advances_tick` | POST /api/sessions/{id}/action（自由文本）→ 响应 tick == 前值 + 1 + view_revision 递增 |
| 3 | `test_web_api_t3_image_endpoint` | GET image：200 + content-type image/x-ppm + payload 长 == slot.byte_length；无图 → 404 信封 |
| 4 | `test_web_api_t4_unknown_route_404` | 未知 path → 404 + ok==false 信封（code 闭集） |
| 5 | `test_web_api_t5_error_envelope` | WebApiError 面 → (status ∈ {400,404,409,500}, {"ok": false, "error_code", "error_message"}) 形状钉（AD-P10-1） |

**`test_inspector.py`（4）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_inspector_t1_twelve_sections` | build_inspector_view 键集 == INSPECTOR_SECTIONS 12 名逐字（Spec §37） |
| 2 | `test_inspector_t2_causal_chain_end_to_end` | fixture 已知事件 → 链 transaction 非 None + effects ≥1 + producers 非空 + action_refs 非空（A4 单元面） |
| 3 | `test_inspector_t3_revision_timeline_monotonic` | revision_timeline view_revision 严格单调递增 |
| 4 | `test_inspector_t4_authority_decisions_present` | authority_decision 节 ≥1 条 + producer 非空（K6 面） |

**`test_workbench.py`（4）**

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_workbench_t1_prompt_history` | 脚本 2 调用 → prompt_history == [(seq, logical_role, base_revision, model, prompt_metadata_ref, response_text)] 逐条钉（T07 核心） |
| 2 | `test_workbench_t2_logical_profile_model` | logical_profile == "narrator" + resolved_model == "fake-model-1"（K8：模型名零推词） |
| 3 | `test_workbench_t3_k8_clean_view` | build_workbench_view 全量字符串化 × 12 名黑名单零命中（K8） |
| 4 | `test_workbench_t4_json_clean` | json.dumps 零失败（INV-10） |

**`test_g10_gate.py`（4）**——G10 门面条，每面恰 1 函数（§5.3 逐字）

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_g10_gate_t1_stale_image_no_overwrite` | G10-1 双面（A1）：DISCARD 零覆盖 + DISPLAY stale 标记且槽 revision = 当前 |
| 2 | `test_g10_gate_t2_dual_backend_structured_view` | G10-2（A2）：同 SceneView → narrate_scene + derive_render_intent 独立产出 + text/↔image/ 零互 import（AST 全文件面） |
| 3 | `test_g10_gate_t3_no_module_singleton_world` | G10-3（A3）：AST 扫 adapters/web + presentation 全树（19 文件）：零模块级 WorldState()/SessionManager()/WebSession()/Scheduler()/LogicalClock() 实例化 + 零模块级 session 全局绑定 |
| 4 | `test_g10_gate_t4_inspector_chain_locator` | G10-4（A4）：fixture 世界 + 已知事件序列 → inspect_event 端到端链非空（经 TraceQuery.causal_chain） |

**`test_p10_face.py`（6）**——结构面（无 A id；§5.2 结构面说明）

| t# | 函数名 | 钉面 |
|---|---|---|
| 1 | `test_p10_face_t1_src_tree_closed` | `src/engine_v2/presentation/` + `src/engine_v2/adapters/web/` 文件集 == 白名单行 1–19（static 3 文件含） |
| 2 | `test_p10_face_t2_export_ledger` | 12 模块 `__all__` 计数/名 == §8.2 台账（49 名）逐字 |
| 3 | `test_p10_face_t3_k8_literals` | 19 src 文件全部字符串字面量（含 docstring）× 12 名黑名单：唯一允许命中 = narrator.py `TEXT_SOURCES` 钉元组 `llm`（ERR-P10-10），其余零命中（大小写不敏感） |
| 4 | `test_p10_face_t4_import_closure` | AST：P10 src import 根闭集 ⊆ §3.0（含 http.server 仅 server.py、jinja2 零、图像库零、v1 src.* 零）+ text/↔image/ 零互 + engine_v2 全树零 langgraph/langchain |
| 5 | `test_p10_face_t5_no_control_bytes` | 19 src 文件零裸 0x5C 0x62 序列（D3） |
| 6 | `test_p10_face_t6_no_frontend_build_artifacts` | src/ 全树零 package.json / package-lock.json / bun.lockb / vite.config.* / webpack*；static == 3 文件闭集；app.js 零 import/require/document.write |

**合计**：7+5+5+8+3+6+5+4+4+4+6 = **57**（+ TestP10Boundary 6 方法
= 63；§8.3 恒等式）。

### 6.2 conftest（2 文件；零测试函数）

- `tests/engine_v2/presentation/conftest.py`：
  - `fixture_world`：core 面构建 WorldState——2 actor（player/npc 实体 +
    组件）+ 1 location（scenario 世界标识投影面）+ hex 域 3×3
    （GraphSpace 注册：节点 `hex_<c>_<r>` + 16 无向边，P9 A12 钉值
    参照）+ 方格域（GridSpace(3,3) 对照）+ LogicalClock 注入；
  - `known_event_sequence`：3 次 commit 驱动（talk 提案 → 效果 →
    事件；move → 事件；属性变更 → 事件）→ world + trace_records
    （TraceRecord 直构：kind = ACTION_PROPOSAL / PROPOSED_EFFECT /
    TRANSACTION / DOMAIN_EVENT / AUTHORITY_DECISION 面，producer /
    transaction_id / world_revision 对齐）；
  - `script_backend`：FakeInferenceBackend（narrator/visual_director
    脚本键预置，§6.4 脚本钉）；
  - `scene_view`：derive_scene_view(fixture_world) 投影。
- `tests/engine_v2/adapters/web/conftest.py`：
  - `driver`：TickDriver 最小宿主实现（P9 样例宿主先例——conftest 侧
    宿主循环：clock.set_logical_tick + scheduler 相位 + 效果经 kernel
    应用面落位；P1 runtime 未来承接生产实现，§0.4）；
  - `manager` / `session`：SessionManager + create_session（注入
    driver + DeterministicImageBackend；W4 会话无 LLM 面——§3.7
    权威签名零推理参数，ERR-P10-15）；
  - `script_backend`：W1 冻结 fixture re-export（W5 workbench 测试
    直消费 pairs 收集面；不注入会话——ERR-P10-15）；
  - `trace_manager_session`：known_event_sequence 世界 + trace_records
    注入的会话（inspector/workbench 数据源）。

### 6.3 AD 对抗族（AD-P10-1..3；并入 §6.1 相应 t#，不单列函数）

- **AD-P10-1（Web API 对抗输入）**：坏 JSON body（非 dict）/ 未知路由 /
  缺席 session id / paused 会话 step / 路径穿越静态名（`../x`）→
  错误信封闭集（status ∈ {400,404,409,500}；ok==false；code 闭集）。
  并入：`test_web_api` t4/t5 + `test_session_manager` t5/t6。
- **AD-P10-2（adversarial RenderIntent）**：空 subjects / 超长 unicode
  mood / 异常 camera dict（嵌套非 JSON-clean 值拒绝）→
  `render_intent_to_ppm` 产合法 PPM（头部 + w×h×3 分量可解析）或
  PresentationError（code 闭集）——零异常逃逸、零非 JSON-clean 落位。
  并入：`test_image_backend` t1 扩展断言 + t3。
- **AD-P10-3（stale 连发）**：当前 87→88→89 推进中重复提交 revision 83
  artifact（DISCARD 默认）→ slot 恒 None / 有槽时恒原样（view_revision
  恒 == 当前，INV-2 连续钉）。并入：`test_image_backend` t6 扩展循环。

### 6.4 fixture 钉（fixture pin）

- conftest 世界/事件/脚本一经落盘**跨波不改**（P9 §6.4 纪律）；
  修改 = 勘误登记 + 白名单复核。
- 脚本键钉（FakeInferenceBackend）：narrator =
  `{("narrator", Revision(2), 1): "<润色文本钉>"}`；visual_director =
  `{("visual_director", Revision(2), 1): "<intent JSON 钉>"}`（base_revision
  = 会话 step 后 world_revision，实现波次 conftest 内以常量锚定）。
- P9 3 样例项目（G9 收口后）= 只读（S11 人工面世界源；零机械消费）。

---

## §7 边界方法（TestP10Boundary 6 方法；锚文件 EOF 纯追加先例）

> 锚文件 = `tests/engine_v2/core/test_import_boundary.py`（2071 行 @
> `6fdfdcf`；G9 收口后 = 2071 + N）。P10 块 = **G9 收口点后的 EOF 纯
> 追加**（D5 / P10-INV-9）；白名单行 36（M 模式，L1–收口点行逐字节
> 不变，方法 6 自证）。方法 5/6 哈希清单 = W5 实现者**自 G9 收口工作树**
> 一次性计算的 sha256 字面量（非运行时 git 调用；P9 §3.20 实现注记同）。

| # | 方法名 | 检查内容 | 失败语义 |
|---|---|---|---|
| 1 | `test_p10_src_tree_closed` | `src/engine_v2/presentation/` + `src/engine_v2/adapters/web/` 文件集 == 白名单行 1–19（19 项，含 static 3 + 4 子包 `__init__` + 既有占位二件套不计——二件套属冻结面，由方法 6 哈希钉） | 白名单外新文件 / 缺失文件 |
| 2 | `test_p10_test_tree_closed` | `tests/engine_v2/presentation/` 文件集 == 白名单行 20–26（7 项：`__init__` + conftest + 5 测试文件）；`tests/engine_v2/adapters/` 文件集 == 白名单行 27–35（9 项：2 包件 + conftest + 6 测试文件） | 同上 |
| 3 | `test_p10_string_literal_k8` | AST 遍历 P10 src 19 文件全部字符串字面量（含 docstring）× 12 名黑名单（复用既有 `P4_LLM_PROVIDER_BLACKLIST`，:225–240 @ 2071 行时点）：唯一允许命中 = narrator.py `TEXT_SOURCES` 钉元组 `llm`（SOT §3.2/§5.2/§6.1 三处钉面；ERR-P10-10），其余零命中；大小写不敏感子串面 | K8 词泄漏（P10-INV-7） |
| 4 | `test_p10_import_closure` | AST 遍历 P10 src 19 文件全部 import：根闭集 ⊆ §3.0（stdlib / pydantic / engine_v2.core / llm.adapter / persistence.snapshot / devtools.trace_query / presentation.* / adapters.web；http.server 仅 server.py；零 jinja2 / 零图像库 / 零 v1 `src.*`）+ P10 src 19 文件零 `random` / `time` / `datetime` / `timeit` 模块 import（D6 零 wall-clock / 零随机机械面；ERR-P10-07）+ text/ ↔ image/ 零互 import + inspector/workbench 零 core.entity/core.components 直读 + **engine_v2 全树**（含 P1–P9 冻结面 + P10 面）import 零 `langgraph` / `langchain` | 边界越权 / 互依赖 / 旁路直读 / LangGraph 依赖回归 / D6 随机源回归（P10-INV-3/5/7/8 + D6） |
| 5 | `test_v1_p10_frozen_hashes` | v1 路径集（P9-INV-1 口径：`src/**` 除 `src/engine_v2/**` + `public_start/**` + `config/**` + `tests/**` 除 `tests/engine_v2/**` + `pyproject.toml`）sha256 == 嵌入清单（W5 自 G9 收口工作树计算；含 `src/web/` `src/ui/` `web/` 三 web 子树——D-P10-08 反例锚面） | v1 冻结面被修改（P10-INV-9） |
| 6 | `test_p10_frozen_surfaces_untouched` | (a) `pyproject.toml` sha256 不变（P10-INV-8）；(b) 占位二件套（§2.6）sha256 不变；(c) `src/engine_v2/{core,content,llm,prompts,dynamics,persistence,plugins,devtools,modules}` + `tests/engine_v2/{core,content,llm,prompts,dynamics,persistence,plugins,modules}` 子树哈希不变（含 P9 15 模块 + P9 测试 + P9 3 样例——G9 收口后冻结面；**锚文件自身**以「至 G9 收口点行 sha256 == 基线值」特判，排除 P10 纯追加段）；(d) `tests/fixtures/` 既有 7 + P9 3 项目目录哈希不变 | kernel / P9 冻结面被修改（P10-INV-8/9） |

**估算**：P10 块 +300–400 行（P9 块估算 +350–450 同量级；方法 5/6
清单字面量占大头）。

## §8 台账与计数

### 8.1 K1–K8 × P10 面矩阵

| Kernel 不变量 | P10 消费/接触面 | P10 机械验证面 |
|---|---|---|
| K1 WorldState 唯一状态权威 | SceneView / ImageSlot / RenderIntent / TacticalLayout = 派生数据（Spec §8.5 L626–638）；view 零反作用 | P10-INV-1 + A5（t1/t3 世界哈希不变） |
| K2 producer 不直写 WorldState | presentation / adapters-web 全部纯派生或注入式容器；状态推进仅经 conftest 宿主（kernel 应用面） | P10-INV-1 + 边界方法 4（AST 零可变写模式）+ A5/A11 行为面 |
| K3 Authority 裁决效果 | P10 零 authority 实现；inspector 只读 authority_decisions 投影（T06） | `test_inspector` t4 + 边界方法 4（零 authority 新语义 import） |
| K4 Prompt 不能定义世界权限（Spec L295–303） | 玩家输入经 TemplatePlayerPolicy → ActionProposal（kernel 裁决）；prompt 面零 authority 声明 | 边界方法 4 + step 语义钉（`test_web_api` t2） |
| K5 kernel 不假设全员 NPC 决策（本阶段 = 测试零真实 LLM 纪律） | Narrator / VisualDirector LLM 面 = 注入 InferenceBackend；测试 = FakeInferenceBackend 脚本（键 (logical_role, base_revision, seq)）；零网络 / 零 key | P10-INV-6 + A8（t1 零调用 / t2 脚本面） |
| K6 Event 必须可追踪来源（Spec L315–324） | Inspector 链 = DomainEvent.provenance + CausalChain（producers/action_refs）消费面 | A4 + `test_inspector` t2/t4 |
| K7 Runtime 关键调度状态必须可检查（Spec L326–328） | Inspector 12 节（Spec §37）= runtime / scheduler / active_action 投影；Presentation/web 零隐藏模块级状态 | `test_inspector` t1 + A3（AST 零模块级状态） |
| K8 部署与项目分离 | P10 src 12 名推词零命中（含 static）；模型名 = 调用方面（测试 `fake-model-1`）；零部署解析（P6 deployment 不消费） | P10-INV-7 + face t3 + `test_workbench` t2/t3 + 边界方法 3 |
| D6 确定性双跑（P10 纪律，非 Spec K 项） | 注入纪律：LogicalClock / FixedMonotonicClock / 脚本 backend / 注入 driver 全注入；零 wall-clock / 零全局 RNG；图像字节 = f(intent) | A5/A10 双跑面 + AD-P10-3 连发面 |

### 8.2 P10 导出台账（P10_EXPORT_LEDGER；12 模块 49 名；`__all__` 逐字按序 = §3 各节代码块）

| # | 文件 | 导出数 | 导出名（`__all__` 序） |
|---|---|---|---|
| 1 | `presentation/view.py` | 5 | PresentationError / VIEW_SCHEMA_VERSION / SceneView / scene_id_of / derive_scene_view |
| 2 | `presentation/text/narrator.py` | 5 | NARRATOR_LOGICAL_ROLE / TEXT_SOURCES / TextArtifact / NarratorPresentationBackend / narrate_scene |
| 3 | `presentation/image/contract.py` | 6 | RENDER_INTENT_SCHEMA_VERSION / ImageStalePolicy / RenderIntent / ImageArtifact / ImageSlot / apply_image_result |
| 4 | `presentation/image/director.py` | 3 | VISUAL_DIRECTOR_LOGICAL_ROLE / VisualDirector / derive_render_intent |
| 5 | `presentation/image/backend.py` | 5 | IMAGE_BACKEND_KINDS / ImageBackend / DeterministicImageBackend / FakeImageBackend / render_intent_to_ppm |
| 6 | `presentation/tactical/layout.py` | 3 | TACTICAL_LAYOUT_SCHEMA_VERSION / TacticalLayout / build_tactical_layout |
| 7 | `adapters/web/session.py` | 6 | SESSION_COMMANDS / TickDriver / TemplatePlayerPolicy / WebSession / SessionManager / SessionNotFoundError |
| 8 | `adapters/web/api.py` | 5 | WEB_ROUTES / WebApiError / WebResponse / handle_web_request / resolve_static_name |
| 9 | `adapters/web/inspector.py` | 3 | INSPECTOR_SECTIONS / build_inspector_view / inspect_event |
| 10 | `adapters/web/workbench.py` | 3 | WORKBENCH_SECTIONS / build_workbench_view / prompt_history |
| 11 | `adapters/web/views.py` | 3 | PAGE_NAMES / PAGE_TEMPLATES / render_page |
| 12 | `adapters/web/server.py` | 2 | create_web_server / run_web_server |
| — | **合计** | **49** | （5+5+6+3+5+3+6+5+3+3+3+2 = 49） |

> 4 个新子包 `__init__.py`（text / image / tactical / web，白名单行
> 2/4/8/10）= docstring-only，零导出（P9 `modules/__init__.py` 先例）；
> 既有占位二件套（§2.6）字节冻结零 re-export。私有常量（
> PRESENTATION_ERROR_CODES / IMAGE_MEDIA_TYPES / SESSION_SNAPSHOT_KEYS /
> WEB_ERROR_STATUSES 等）不入 `__all__`（P9 MAPPING_RULES 先例），
> 由相应 t# 行为钉。

### 8.3 计数恒等式（门④期望 passed = **G9_final + 63** = **3142 + 63 = 3205**；D-P10-10 实测重算完成）

```text
G9 终态（§0.3.1 已回填实测 = 3142 = 3054 + 82 + 6；
G9 门级 R1 4 盲 + W7 R4 4 盲共 8 次独立复跑一致）
+ P10 平铺函数（§6.1 逐表）                57
    test_view 7 + test_narrator 5 + test_render_intent 5
    + test_image_backend 8 + test_tactical_layout 3
    + test_session_manager 6 + test_web_api 5
    + test_inspector 4 + test_workbench 4
    + test_g10_gate 4 + test_p10_face 6 = 57
+ TestP10Boundary 方法（§7，锚文件 EOF 纯追加） 6
──────────────────────────────────────────
= 门④ 期望 passed = G9_final + 63 = 3142 + 63 = 3205
    （D-P10-10 实测重算完成；G10 门③步实测确认）
```

交叉恒等式（自检项，门④逐条复算）：

- 波表累计：7+10+11+11+18 = 57（§10）== §6.1 合计 57；
- 白名单 38 行 = 19 src（18 A + 1 M：view.py tactical 填充 ERR-P10-11）
  + 18 tests（16 A + 2 M：边界锚纯追加 + skeleton 计数面 ERR-P10-09；
  ERR-P10-03：原公式 19+16=35 误计）（§11）；
- 导出 49（§8.2）= face t2 台账核对基准；
- A 判据 12 = 4 门面条（A1–A4，G10-1..4 1:1）+ 8 辅助（A5–A12）；
  12 函数 ⊆ 57 平铺（§5.3 1:1）；
- G10 门面条 7 = 自动 4（→A1–A4）+ 人工 3（→S11 挂起，gate 报告
  「Human review required」）；
- SceneView 10 键（§3.1）/ RenderIntent 8 字段（§3.3，Spec §32.2）/
  ImageSlot 7 键 / TacticalLayout 7 键 / INSPECTOR_SECTIONS 12 名 /
  WORKBENCH_SECTIONS 8 名 / SESSION_COMMANDS 8 名 / WEB_ROUTES 9 行 /
  PAGE_NAMES 3 名 / static 3 文件——各闭集计数 = 对应 t# 钉面值。

### 8.4 偏差登记（DEV-P10-01..05；DEV-P10-01 闭合（G9 收口回填完成）；DEV-P10-05 = Leader 终审新登记；其余 W0 初稿时点已有处置）

| ID | 问题 | 处置 |
|---|---|---|
| DEV-P10-01 | P9 W6/W7 交付物（narration/space/dialogue/tactical/dynamics 模块 + 5 测试文件 + 3 样例 + 边界块）W0 初稿时点未落盘（G9 未收口）→ P10 的 P9 消费锚（narration 5 键 / space 4 名 / 边界锚行数）无字节可核 | 初稿时点 = 锚点引用 P9 SOT 冻结设计值并标「待复测」（§0.3.3 末行 + §2.4）→ **G9 收口点复测完成（已闭合）**：§0.3.1 回填实测值；§0.3.3/§2.4 P9 消费锚按磁盘实测落值（值旁注 file:line：space 4 名 / narration 4 名 + 5 键 / register_standard_space entries 形签名（ERR-P9-10 勘误后值）/ 边界锚 2625 行）；复测零漂移（均与 P9 SOT 冻结（勘误后）值一致，§9 零新增勘误）；边界哈希清单 W5 自 G9 收口树计算（§7 实现注记） |
| DEV-P10-02 | Plan T01 任务名「ViewState / SceneView」双名 vs Spec §8.5 ViewState = 泛称（derived data 类）vs P9 NarrativeView = 叙事子视图 | 本 SOT 定名：P10 顶层结构化视图 = `SceneView`（§3.1）；ViewState = Spec 泛称不落地为类名；NarrativeView 形状 = SceneView.narrative 5 键兼容面（D-P10-01）；G10-2「结构化 View」= SceneView 唯一 |
| DEV-P10-03 | G10-1「不错误覆盖当前 view」语义 vs Spec §32.3 三策略（policy 可展示过期图） | 缺省策略 = DISCARD（D-P10-11）：缺省下过期 artifact 零覆盖；DISPLAY/ARCHIVE = 策略注入面（t7/t8 钉「展示但槽 revision = 当前 + stale 标记」——「不错误覆盖」在三策略下均成立，语义 = 槽 view_revision 恒随当前 view） |
| DEV-P10-04 | Spec §44 L2198–2201 presentation/ 树仅列 3 子包（text/image/tactical），未列包级公共文件 | 本 SOT 增包级 `view.py`（T01 落位；§8.5/§32 公共派生面，非独立子包）——Spec 树按不完整对待（P9 ERR-P9-03 同型先例：树 ≠ 权威闭集，白名单 = 权威） |
| DEV-P10-05 | `SessionManager.create_session` 缺省路径内部生成 `uuid4().hex` = 公开函数内非确定性默认（与 §0.5 D6「全部公开函数纯函数或显式注入状态」字面张力；SOT 锚 = §3.7 SessionManager 行） | 允许但钉死 = **身份标签例外**（Leader 终审 §4 裁定）：session_id 属容器身份面（非模拟状态、非 view/snapshot/任何确定性派生面输入）；P10 唯一非确定性默认；**测试必须显式传 session_id**（A12/t2 隔离双跑显式钉 id，零缺省依赖）→ 套件确定性不受影响（D6 语义面保持）。备选（否）：session_id 必填参数（G10 人工面/宿主流程负担，v1 无对应面先例）；模块级计数器（模块级可变状态，P10-INV-4 面违规） |

---

## §9 勘误（errata；预留）

> 纪律（D8）：本节为 P10 行锚/口径勘误**唯一规范记录**；历史条目不追改；
> 实现波次勘误按 ERR-P10-NN 续编（ERR-P9-01..08 先例）。
> W0 初稿种子条目：

| ID | 类型 | 勘误 | 更正 | 状态 |
|---|---|---|---|---|
| ERR-P10-01 | 口径 | W0 初稿时点 G9 未收口（P9 W5 未提交 / W6–W7 未落盘）——任务书与简报的「G9 冻结消费面」在初稿时点仅部分可字节核验 | 基线表 G9 终态 = 占位节（§0.3.1，Leader 收口后填实测值：3142/0 期望 + G9 commit + P9 冻结面清单）；初稿时点参照值 = 3104/0 @ `6fdfdcf`（§0.3.2，仅参照）；P9 消费锚引用 P9 SOT 冻结设计值 + 「待复测」标记（DEV-P10-01）；门④期望 = G9_final + 63（§8.3） | W0 定案（§0.3/§2.4/§8.3 已按此落表；G9 收口点复测回填） |
| ERR-P10-02 | 闭集遗漏 | P10 W0 R1 评审 #1 发现（F-P10-1；评审 #3 独立复证）：§3.0 导入闭集 `presentation/text/*` 行原漏 `engine_v2.presentation.view` 依赖，与 §3.2 narrator `render(view: SceneView)` / `narrate_scene(view: SceneView, …)` 签名（SceneView 定义于 presentation/view.py）文面矛盾——按原闭集 import 即触 face t4 / 边界方法 4 红，不 import 则签名名不可解析（对照 `image/*` 行显式含该依赖，疑漏一行坐实） | §3.0 text/* 行补 `+ engine_v2.presentation.view`（narrator SceneView 签名）；W2 dev 前闭合；实现面（narrator.py 必 import view）按更正值落码 | P10 W0 R1 裁决定案（Leader byte-verify：text/* 行 vs image/* 行对照 + §3.2 L453/455 签名面实测） |
| ERR-P10-03 | 口径误计 | P10 W0 R1 评审 #3 发现（F-03；#1/#2/#4 独立复证 4/4）：§8.3 / §11 自检公式「36 行 = 19 src + 16 tests（15 A + 1 M）」算术矛盾（19+16=35≠36）且与 SOT 自身规范表矛盾（行 1–19 = 19A src + 行 20–35 = 16A tests + 行 36 = 1M）；byte-truth = 35A + 1M = 36 | §8.3 / §11 两处自检公式改「19 src（全 A）+ 17 tests（16 A + 1 M）」；门④② 判定基准 = §11 表本体（逐行 A/M 模式）零影响；R1 brief C7 同式串扰随 R2 brief 更正 | P10 W0 R1 裁决定案（Leader byte-verify：§11 表行 1–19/20–35/36 模式逐行复算 = 19A+16A+1M） |
| ERR-P10-04 | 口径误计 | P10 W0 R2 评审 #3 发现（F-P10-R2-3-1）：§4 D-P10-06 选择段「测试 15 新文件 + 1 边界 M（§11 白名单 36 行）」算术矛盾（19+15+1=35≠36）——ERR-P10-03 同类误计在 §4 的残留实例（R1 更正仅覆盖 §8.3/§11 两处自检公式，此叙述句遗漏） | §4 D-P10-06 叙述句「15」改「16」（§11 行 20–35 实测 16 个 tests A）；门④② 基准（§11 表本体）零影响 | P10 W0 R2 裁决定案（Leader byte-verify：§11 行 20–35 模式逐行复算） |
| ERR-P10-05 | 摘要失准 | P10 W0 R2 评审 #1 发现（F-R2-01）：§2.3 llm/adapter 行用途列「Workbench prompt 史（T07：calls → (seq, logical_role, base_revision, model, text) 投影）」5 字段摘要与 §3.11 `prompt_history` 规范（6 键：seq / logical_role / base_revision / model / prompt_metadata_ref / response_text）不符——漏 prompt_metadata_ref 且 text 应为 response_text（规范面 §3.11/§6.1 t1 自洽，仅 §2.3 摘要面失准） | §2.3 用途列改 6 键逐字投影（与 §3.11 同文）；实现面按 §3.11 规范零影响 | P10 W0 R2 裁决定案（Leader byte-verify：§3.11 表行 6 键实测） |
| ERR-P10-06 | 行锚尾差 | P10 W0 R2 评审 #3（F-P10-R2-3-3）/ #4（F-R4-01）独立同证：§0.4 非范围表引「Spec §46 L2300–2309 第 1/2/3/8/9 项」，磁盘实测第 9 项（complete branch debugger UI）= Spec L2310（上界差 1 行，项号/项名/内容全对） | §0.4 引文上界改 L2300–2310；零设计影响 | P10 W0 R2 裁决定案（Leader byte-verify：Spec §46 第 8/9/10 项行号实测） |
| ERR-P10-07 | 机械面补强 | P10 W0 R2 评审 #3 发现（F-P10-R2-3-2，DOC 级纪律闭合项）：§3.0 导入闭集 stdlib 开根未显式排除 `random` / `time` / `datetime` / `timeit` 模块——`random` import 不触 face t4 / 边界方法 4，D6 零随机机械面原靠双跑测试（语义面）+ 每模块零随机声明覆盖不均（显式仅 §3.1/3.4/3.5/3.7） | §3.0 禁止清单显式补 4 模块 + §7 边界方法 4 AST 检查域补「P10 src 19 文件零 4 模块 import」（机械面补强，非断言放宽；双跑测试保留）；方法数 6 / 平铺名 57 零变化 | P10 W0 R2 裁决定案（Leader 采纳评审建议；D6 纪律面补强） |
| ERR-P10-08 | core 冻结面潜在坑（F2 登记） | P10 W1 dev 发现（F2；W1 R1 2 评审独立复现 + 规避行为学验证）：`WorldState.entity_view()`（`EntityView._from_record` 深冻结路径）将组件载荷嵌套 dict 冻结为 `MappingProxyType`；`decode_spaces`（space.py:492）的 pydantic `JsonValue` 复校验拒绝 `MappingProxyType`（`invalid-json-value`）→ `entity_domain_positions(EntityView)`（space.py:505）对 grid（dict）域位置抛 ValidationError；P9 纯 hex（str 位置）世界掩盖此坑，P10 SOT 钉双域世界（hex + grid）后首次暴露 | core 冻结面零修改（P10-INV-9 / §2）；P10 规避 = view.py 经冻结 codec `decode_spaces`（space.py:492）消费 `WorldState.entities[...].components` 原始字段面（P9 conftest 同模式，tests/engine_v2/modules/conftest.py:607；§3.0 core 闭集内；W1 4 评审验证规避正确）；core 侧修复建议（`decode_spaces` 接受 Mapping 输入，或深冻结保留 JSON-clean 容器）= 非 P10 范围（不入白名单），G10 报告「后续波次承接」面登记 | P10 W1 收口裁决（W1 R1 4×通过；本行 = W1 裁决「W5 门④⑥ 步落 SOT §9」执行，G10 门④⑥ 步补录；view.py:16 docstring 引用编号闭合） |
| ERR-P10-09 | 盲点遗漏 | P10 W2 dev 发现（F-W2-01，dev 停手报裁；Leader byte-verify）：SOT 全文零引用 `tests/test_engine_v2_skeleton.py`（v1 路径集成员，ERR-P9-05(1) 口径）——其 `test_engine_v2_init_files_are_docstring_only`（:145–153）钉 `src/engine_v2/` 下 `__init__.py` 总数 = SUBPACKAGES（13 直接子包）+ 1 根包（rglob 递归计数）；SOT 白名单行 2/4/8/10 自身要求 4 个新嵌套子包包件（text/image/tactical/web）→ 计数断言 W2（16≠14）/ W3（17）/ W4（18）结构性红，G10 3205/0 不可达；该文件不在白名单 → 波次纪律内无修复路径。**二次发现（Leader 实跑）**：该文件 sha256 另被 P9 边界 `TestP9Boundary._V1_FROZEN_MANIFEST`（锚文件 L2292，P9 块冻结区 L2127–2625 内）钉死 → 修改即触发 `test_v1_frozen_hashes` 红；P9 块字面量不可改（行 36 M 模式 L1–2625 逐字节不变 + L1–2071 sha 自证） | §11 增行 37 M（`tests/test_engine_v2_skeleton.py`；修改面 = SUBPACKAGES 列表 + 计数文案仅：W2 +2 / W3 +1 / W4 +1 每波机械追加；docstring-only 检查逻辑字节不变——新包件入冻结纪律检查域）；**行 36 P10 块（EOF 纯追加区）含 v1 清单刷新语句 = 每波一行字面量 `TestP9Boundary._V1_FROZEN_MANIFEST["tests/test_engine_v2_skeleton.py"] = <sha256>`（最后赋值生效；P9 块 L2127–2625 字面量零修改）——双钉（skeleton 计数 + P9 哈希）唯一自洽闭合**；P10-INV-9 加唯一例外条款；门④② 基准 36→37 行；§8.3 自检公式同步；套件测试函数数零变化（3205 恒等式不变） | P10 W2 裁决定案（Leader byte-verify：skeleton test :27–40/:54/:145–153 实测 + G9 3142 绿 = 14 计数基线复测 + P9 清单 L2292 条目实测 + 差集 = 唯一条目复现 + SOT 白名单行 2/4/8/10 vs rglob 计数结构性矛盾成立；D8 勘误 = 唯一自洽解） |
| ERR-P10-10 | 内部矛盾 | P10 W2 dev 发现（F-W2-02；dev 按钉面值落码）：SOT 自相矛盾——§7 方法 3 / face t3 / D7 = 19 src 文件全部字符串字面量（含 docstring）× 12 名黑名单（含 "llm"）零命中，而 §3.2 / §5.2 A8 / §6.1 t2 三处逐字钉 `TEXT_SOURCES = ("template", "llm")` + `source == "llm"`（artifact.source 闭集之 "llm" = 脚本命中推理路径标签）→ W5 face t3 / 方法 3 于 narrator.py 钉元组结构性红，G10 3205/0 不可达 | D7 / §7 方法 3 / face t3 改「唯一允许命中 = narrator.py `TEXT_SOURCES` 钉元组 `llm`，其余字面量 × 12 名零命中」（三处钉面 > 通则；W2 落码实测 src 全树恰 1 命中 = 该钉元组行，已核唯一）；扫描实现 = 排除钉元组字面量后 × 12 名零命中 + 其余 11 名全量零命中 | P10 W2 裁决定案（Leader byte-verify：test_import_boundary.py:225–240 12 名清单实测（含 "llm"）+ SOT §3.2/§5.2 A8/§6.1 t2 三处钉面实测 + dev 1 命中唯一性复测） |
| ERR-P10-11 | 内部矛盾（闭集漏行） | P10 W2 收口期 Leader 预读 W3 面发现（W3 dev 派发前拦截）：§3.1 derive_scene_view 语义列「tactical_domain_id 非 None 时填 tactical_overlay（§3.6）」vs §3.0 导入闭集 `presentation/view.py: stdlib + engine_v2.core`（无 presentation.tactical）→ 填充分支在闭集内不可实现；W1 落码 = None 占位 + seam 注记（合法面 2，dev 从闭集）；ERR-P10-02 同类（闭集漏行与签名/语义面矛盾）。裁决域排除项：image_slot 先例是「view 返 None + 会话层回投」，tactical 参数设计（derive 内传 domain_id）与之刻意不同 = 填充意在 derive 内 | §3.0 闭集 view.py 行增 `+ engine_v2.presentation.tactical.layout`（单向依赖：tactical/* = stdlib + core，零环；A2 互禁不受影响）；§11 增行 38 M（view.py 仅 tactical 填充分支：W3 期 `del tactical_domain_id` + `tactical_overlay=None` → 非 None 时 build_tactical_layout 填充；其余逻辑/`__all__` 零改）；§10.1 W3 波行文件列 = 行 7–9 + 行 38 M；W1 t4 L106「默认调用 overlay is None」钉面零影响（参数 None 分支不变）；门④② 基准 37→38 行；§8.3 公式同步；套件函数数零变化（3205 不变） | P10 W2 收口裁决定案（Leader byte-verify：§3.1 L414 语义面 vs §3.0 闭集行实测矛盾成立 + W1 view.py L293–302/341 seam 落码实测 + test_view L106 默认 None 钉实测 + tactical 闭集无 view 依赖 = 零环复算） |
| ERR-P10-12 | 内部矛盾（钉文自反） | P10 W2 R1 评审 #1（F-R1-01）/ #4（F-R1-01 DOC）独立同证：§6.1 t1 钉文「template 路径：注入 backend.calls == ()」vs §3.2 路径选择语义「template 路径 = 确定性模板（零 backend 调用）；llm 路径（backend 非 None）」——按钉文注入命中键 backend 必走 llm 路径（calls 必非空），钉文在 §3.2 语义下不可实现；W2 落码 = narrate_scene 零注入（backend=None）+ 探针构造不注入 = §3.2 唯一自洽实现（2 评审裁定非违例） | §6.1 t1 钉文改「template 路径（backend=None，§3.2 路径选择）：探针 backend（脚本预置命中键、未注入）calls == ()；source == template」（规范语义面 §3.2 为准；W2 落码零返工——代码与更后钉文一致）；W2 docstring 预提交修正（「注入的」→ 探针未注入表述） | P10 W2 R1 裁决定案（Leader byte-verify：§3.2 行 26 路径选择语义实测 + §6.1 t1 钉文实测矛盾成立 + W2 test_narrator.py t1 落码（narrate_scene 零注入 + fake.calls == () 断言在位）实测） |
| ERR-P10-13 | 内部矛盾（错误类落位环） | P10 W3 dev 发现（F-W3-01，dev 按闭集落码并报裁；Leader byte-verify）：§3.6 钉「域缺席 → `PresentationError(code="scene_key_invalid")`」vs §3.0 闭集 `tactical/*: stdlib + engine_v2.core` + ERR-P10-11 零环裁定（view → tactical.layout 单向）——PresentationError 唯一定义于 view.py，layout 顶层 import 之 = view↔tactical 顶层互 import 环（Python 模块循环；dev 双 import 序运行时实测均 ImportError，证据在 dev 报告 §3.7）→ 钉面在闭集内不可实现 | §3.6 钉文改「域缺席 → ValueError 族错误（layout.py 私有具名类，`code == "scene_key_invalid"` 钉值保留）」（W3 落码 = 该选择，零返工；钉值面 = code 属性，消费方按 code 判别不按类名）；错误类不入 `__all__`（私有，与 W1 PRESENTATION_ERROR_CODES 私有先例同形）；无专属测试函数——域缺席行为钉在 t1 内（pytest.raises 私有类 + code 断言，超集合法；§6.1 3 函数钉面零变化，3170 恒等式不变）；session 层（W4）按 code 面消费错误 | P10 W3 裁决定案（Leader byte-verify：§3.6 L572 原钉文实测 + §3.0 闭集行 + ERR-P10-11 零环裁定实测 + layout.py import 面（core only 零 view）实测 + dev 双序 ImportError 证据在案） |
| ERR-P10-14 | 口径误计（门④② 行数） | P10 W4 收口期 Leader 门④② 预演发现（W5 派发前拦截）：ERR-P10-11 增行 38 M（view.py）后，§11 表 = 38 行但 view.py 双列（行 1 A + 行 38 M）——`git diff --name-status`（9945565..HEAD）对同一文件仅出一行（view.py 相对 G9 = 新增 A；W3 填充分支 = 文件内修改，不产生独立 diff 行）→ 门④②「非空行集 38 行逐行相等」严格双射结构不可达（diff 恒 37 唯一路径：19 src A + 16 tests A + 2 M）；ERR-P10-03/04 同类计数面（行数 vs 路径数） | 门④② + §11 判定规则改「非空行（37 唯一路径）与白名单路径集逐路径 A/M 模式匹配（行 1/行 38 同路径：diff 行 = A〔行 1 模式〕，行 38 M 面 = 文件内 W3 修改面描述，非独立 diff 行；表外路径 = FAIL）」；§11 表本体 38 行不变（行计数 = 表行数口径，§8.3 公式零变化）；3205 恒等式零影响 | P10 W4 收口裁决定案（Leader byte-verify：git diff --name-status 9945565 实测 37 唯一路径复算 + §11 表 38 行逐行实测 view.py 双列 + ERR-P10-11 行 38 语义面核） |
| ERR-P10-15 | 签名矛盾（§3.11/§6.2 vs §3.7 冻结签名） | P10 W4 R1 盲评 #4 上报（Leader 独立复现：§3.11「数据源 = 注入 backend 的调用史」+ §6.2「create_session 注入 script_backend」vs §3.7 WebSession.__init__ 权威签名（session_id/world/driver/player_policy/image_backend/stale_policy/trace_records/save_sink——零推理参数）+ SessionManager 双工厂签名（driver_factory/image_backend_factory——零推理工厂）；W4 dev 从 §3.7 落码（byte-truth 权威）= 会话无推理 backend 槽 → §3.11 build_workbench_view/prompt_history 的 `(session: WebSession)` 签名对 W4 冻结会话无推理史可读（机械不可达）；ERR-P10-12 同类（SOT 内部矛盾，落码从权威签名面） | §3.11 签名重钉 = `build_workbench_view(calls: Sequence[tuple[InferenceRequest, InferenceResponse]])` / `prompt_history(calls: …)`——数据源 = 测试经 `backend.generate` 显式收集的调用对（FakeInferenceBackend.calls = 请求史只读面 + 确定性 response 规则：text = script[(logical_role, base_revision, seq)] 缺省 default_text / model = request.model / token = None 显式保留；llm.adapter 闭集合法）；§6.2 web conftest = create_session 注入面去 script_backend + script_backend 行改 W1 re-export（W5 直消费面）；W4 落码零返工（§3.7 签名面原样合法）；test_workbench t1–t4 函数名 + 钉面值不变（「脚本 2 调用」= 测试驱动 2 次 generate 收集 pairs）；inspector 零影响（§3.10 签名不变：世界组件只读投影经会话同包私有面 + 链全经 TraceQuery = INV-5 合规） | P10 W4 收口裁决定案（Leader byte-verify：§3.7 签名行 + §3.11/§6.2 原钉文实测 + W4 落码 session.py 属性面 grep 复现 + FakeInferenceBackend.generate/calls 落码面实测） |

（后续实现波次勘误按 ERR-P10-NN 续编；行锚漂移以 `sed -n` 复测为准，
登记时附复测命令与输出摘要。）

---

## §10 波次表（W1–W5）+ 门④（G10 六步）

### 10.1 波次表（每波结束套件全绿 + 白名单增量 = 该波列明文件）

> 累计列 = G9_final（3142 实测，§0.3.1）+ 该波前累计新增（D-P10-10
> 实测重算完成）。波内序 = 契约 → 消费（D-P10-09）。Leader 终审 Q7 裁定
> 「W1 等 G9 收口」条件已满足（收口完成，§0.3.1），W1 可派发。

| 波 | 任务 | src 新增（白名单行） | test 新增（白名单行） | 新增平铺函数 | 波后累计（3142 口径） |
|---|---|---|---|---|---|
| W1 | T01 | 行 1（view.py） | 行 20–22（包件 + conftest + test_view） | 7 | 3149 |
| W2 | T02 + T03 | 行 2–6（text 包件 + narrator + image 包件 + contract + director，共 5 文件） | 行 23–24（test_narrator + test_render_intent） | 5 + 5 = 10 | 3159 |
| W3 | T04 + tactical 面（T08 机械面先行） | 行 7–9 + 行 38 M（view.py tactical 填充，ERR-P10-11） | 行 25–26（test_image_backend + test_tactical_layout） | 8 + 3 = 11 | 3170 |
| W4 | T05 | 行 10–12、15–19（web 包件 + session + api + views + server + static 3，共 8 文件） | 行 27–31（adapters 包件 + web 包件 + conftest + test_session_manager + test_web_api） | 6 + 5 = 11 | 3181 |
| W5 | T06 + T07 + T08 收口（+ 边界块） | 行 13–14（inspector + workbench） | 行 32–35（test_inspector + test_workbench + test_g10_gate + test_p10_face）+ **行 36 M（TestP10Boundary 6 方法，锚文件 EOF 纯追加）** | 4 + 4 + 4 + 6 = 18（+ 边界方法 6） | **3205 = 门④期望**（3142 + 57 + 6） |

波间纪律（P9 §3.18 同）：每波结束 `pytest -q` 全绿；白名单外零写盘；
conftest 一经落盘跨波不改（§6.4）；W5 波内序 = inspector → workbench
→ g10 gate → face → 边界块（face 依赖 12 模块齐备；边界块依赖全部
白名单落盘）。

### 10.2 门④ 六步文本块（实现波次 W5 收口逐字执行）

```text
① cd /home/armourpiercer/projects/llmBasedSim && git rev-parse HEAD
   → 记录门④ HEAD；确认晚于 G9 收口 commit
     `99455650f964aa0aee5416a70a1a655135077419`（architecture-v2 分支；§0.3.1 回填值）。
② git diff --name-status 99455650f964aa0aee5416a70a1a655135077419..HEAD -- src tests scripts
   → 非空行集（37 唯一路径）与 §11 白名单路径集逐路径 A/M 模式
     匹配（表外路径 = FAIL；行 1 / 行 38 同路径 view.py：diff 行 =
     A〔行 1 模式〕，行 38 M 面 = 文件内 W3 修改面描述，非独立
     diff 行——ERR-P10-14；v1 路径集与 P9 树零行——D-P10-08 /
     P10-INV-9）；
③ PYTHONPATH=. .venv/bin/python -m pytest -q
   → passed 计数 == G9_final + 63 = 3142 + 63 = 3205（§8.3
     恒等式，实测重算完成）；failed/error/skipped == 0。
④ TestP10Boundary 6 方法全绿（③ 之内含）+ TestP9Boundary /
   TestP8Boundary / TestP7Boundary / TestP6Boundary 既有块全绿
   （冻结面自证）。
⑤ LC_ALL=C.UTF-8 awk 'length($0)>100' <P10 全部落盘文件（src +
   static + tests）> | wc -l == 0（行宽 D2）；grep -rn 裸反斜杠-b
   序列（0x5C 0x62）于 P10 src = 0 命中（D3，face t5 同源）。
⑥ 本 SOT §8.2 台账逐模块 `__all__` 实数核对（python -c import 面）
   + §8.4 偏差登记闭合（全部 DEV-P10-NN 有处置）+ §9 勘误链更新
   + G10 四自动判据复测（test_g10_gate 4/4）+ 人工挂起面 3 项
   （G10-5/6/7）经 S11 流程判定并登记 gate 报告「Human review
   required」（Plan §21 九字段：Gate / Commit SHA / Tasks completed /
   Tasks waived / Tests / Known failures / Architecture deviations /
   Open risks / Human review required / Decision）。
```

> **S11 人工面执行注记（人工延期，不自裁；Leader 终审 §5.6 裁定）**：
> G10-5/6/7 判定人 = 用户（人）；G10 门④时点由人完成执行（Leader 驱动 web
> 会话（galgame 样例世界源，§3.13）+ 目视/截图支撑）；记录格式 = 判定人 /
> 时间 / G10 三人工判据（G10-5/6/7）逐条结论 / 截图或文本证据路径（此处钉；
> W0 裁定原文「六判据」为笔误，Leader 更正如 Plan §19 G10 人工面 3 项）；
> 判定不可靠时转人工
> 裁决（简报 §6 S11 预登记）。gate 报告默认禁止 CONDITIONAL PASS
> （Plan §21 L905–907）。

---

## §11 白名单（门④ diff 判定基准；38 行，**冻结定稿**（行号 = 冻结版行号自定））

> 判定规则：门④② `git diff --name-status 99455650f964aa0aee5416a70a1a655135077419..
> HEAD -- src tests scripts` 的非空行（37 唯一路径）与本表逐路径 A/M 模式
> 匹配（行 1 / 行 38 同路径 view.py 双列 = A 新增面 + W3 填充分支 M 面，
> diff 仅出一行 A——ERR-P10-14）；表外任何路径（含 docs/ 以外文件、
> `.git*`）出现 = FAIL。
> **冻结定稿**（行号 = 冻结版行号自定；实现波次不得提前落盘表外文件）。

**src（行 1–19，18 A + 1 M〔行 1 = W3 tactical 填充面，见行 38；
ERR-P10-11〕）**

| # | 路径 | 章节 |
|---|---|---|
| 1 | `src/engine_v2/presentation/view.py` | §3.1 |
| 2 | `src/engine_v2/presentation/text/__init__.py` | §3.0（docstring-only） |
| 3 | `src/engine_v2/presentation/text/narrator.py` | §3.2 |
| 4 | `src/engine_v2/presentation/image/__init__.py` | §3.0（docstring-only） |
| 5 | `src/engine_v2/presentation/image/contract.py` | §3.3 |
| 6 | `src/engine_v2/presentation/image/director.py` | §3.4 |
| 7 | `src/engine_v2/presentation/image/backend.py` | §3.5 |
| 8 | `src/engine_v2/presentation/tactical/__init__.py` | §3.0（docstring-only） |
| 9 | `src/engine_v2/presentation/tactical/layout.py` | §3.6 |
| 10 | `src/engine_v2/adapters/web/__init__.py` | §3.0（docstring-only） |
| 11 | `src/engine_v2/adapters/web/session.py` | §3.7 |
| 12 | `src/engine_v2/adapters/web/api.py` | §3.8 |
| 13 | `src/engine_v2/adapters/web/inspector.py` | §3.10 |
| 14 | `src/engine_v2/adapters/web/workbench.py` | §3.11 |
| 15 | `src/engine_v2/adapters/web/views.py` | §3.12 |
| 16 | `src/engine_v2/adapters/web/server.py` | §3.12 |
| 17 | `src/engine_v2/adapters/web/static/index.html` | §3.9 |
| 18 | `src/engine_v2/adapters/web/static/app.js` | §3.9 |
| 19 | `src/engine_v2/adapters/web/static/styles.css` | §3.9 |

**tests（行 20–35，全部 A）**

| # | 路径 | 章节 |
|---|---|---|
| 20 | `tests/engine_v2/presentation/__init__.py` | §6.1（0 函数） |
| 21 | `tests/engine_v2/presentation/conftest.py` | §6.2（0 函数） |
| 22 | `tests/engine_v2/presentation/test_view.py` | §6.1（7） |
| 23 | `tests/engine_v2/presentation/test_narrator.py` | §6.1（5） |
| 24 | `tests/engine_v2/presentation/test_render_intent.py` | §6.1（5） |
| 25 | `tests/engine_v2/presentation/test_image_backend.py` | §6.1（8） |
| 26 | `tests/engine_v2/presentation/test_tactical_layout.py` | §6.1（3） |
| 27 | `tests/engine_v2/adapters/__init__.py` | §6.1（0 函数） |
| 28 | `tests/engine_v2/adapters/web/__init__.py` | §6.1（0 函数） |
| 29 | `tests/engine_v2/adapters/web/conftest.py` | §6.2（0 函数） |
| 30 | `tests/engine_v2/adapters/web/test_session_manager.py` | §6.1（6） |
| 31 | `tests/engine_v2/adapters/web/test_web_api.py` | §6.1（5） |
| 32 | `tests/engine_v2/adapters/web/test_inspector.py` | §6.1（4） |
| 33 | `tests/engine_v2/adapters/web/test_workbench.py` | §6.1（4） |
| 34 | `tests/engine_v2/adapters/web/test_g10_gate.py` | §6.1（4） |
| 35 | `tests/engine_v2/adapters/web/test_p10_face.py` | §6.1（6） |

**既有文件修改（行 36–38，M = EOF 纯追加 / 计数面扩展 / tactical 填充）**

| # | 路径 | 模式 | 章节 |
|---|---|---|---|
| 36 | `tests/engine_v2/core/test_import_boundary.py` | **M（L2625 后 EOF 纯追加；L1–2625 逐字节不变，边界方法 6 自证：L1–2071 sha256 = 26fc0528… §0.3.1）** | §7 |
| 37 | `tests/test_engine_v2_skeleton.py` | **M（ERR-P10-09：仅 SUBPACKAGES 列表 + 计数文案——W2 +2〔presentation/text, presentation/image〕/ W3 +1〔presentation/tactical〕/ W4 +1〔adapters/web〕，每波机械追加一条；docstring-only 检查逻辑字节不变，新包件入冻结纪律检查域；P10-INV-9 唯一例外）** | §9 ERR-P10-09 |
| 38 | `src/engine_v2/presentation/view.py` | **M（ERR-P10-11：仅 tactical 填充分支——W3 期 `del tactical_domain_id` + `tactical_overlay=None` → 非 None 时经 build_tactical_layout（§3.6）填充；§3.0 闭集增行配套；其余逻辑 / `__all__` 零改）** | §3.1/§3.6 |

**自检项**：白名单 38 行 = 19 src（18 A + 1 M）+ 18 tests（16 A + 2 M；ERR-P10-03/09/11）；
§10.1 波表行号引用与本表逐字一致；fixture 行 = 0（D-P10-06 / §3.13）。

---

## 附：Leader 终审清单（冻结版状态 = `.p10/p10-w0-leader-adjudication.md` 裁定并入）

1. **G9 收口回填**（§0.3.1 占位）：**已闭合**——G9 收口 docs commit
   `99455650f964aa0aee5416a70a1a655135077419`（代码面收口 `d9d2cc4ff77432b572b21b5e94db6c1ce41b444f`）/
   3142 passed 0 failed（8 次独立复跑一致）/ P9 冻结面清单 = 47 行白名单
   摘要（§0.3.1）/ P9 消费锚 `sed` 复测完成（narration 4 名 + 5 键 / space
   4 名 + register 签名 / 边界锚 2625 行；§0.3.3/§2.4/§2.7，值旁注 file:line）；
2. **§4 决策 12 条**：**已裁定**（全批；D-P10-05 附 DEV-P10-05，D-P10-10
   期望 3205 实测重算完成——§4 各条「Leader 终审」行 / §8.3）；
3. **A 判据口径**：**已裁定**（Q1：不扩编，保持 12 条——§5.2 结构面说明）；
4. **SceneView 10 键 / state_snapshot ~24 键 / 各闭集面值**：**已裁定**
   （SceneView 10 键全批〔顶层 clock 与 narrative.clock 双存合法，§3.1 注记〕；
   SESSION_SNAPSHOT_KEYS 私有常量 + has_long_image_task 改名；SESSION_COMMANDS
   8 名闭集；IMAGE_MEDIA_TYPES 单值——§3.1/§3.3/§3.7）；
5. **波次/白名单冻结**：**已定稿**（§10.1 / §11；36 行；行号 = 冻结版
   行号；Q7 裁定「W1 等 G9 收口」条件已满足，W1 派发）；
6. **S11 人工面执行方案**：**人工延期（预登记面，不自裁）**——G10-5/6/7
   判定人 = 用户（人）；记录格式 = §10.2 注记钉（判定人 / 时间 /
   G10 三人工判据逐条结论（G10-5/6/7） / 截图或文本证据路径）；冻结版保留人工面标记，执行在
   G10 门④时点由人完成。

*—— P10 W0 设计 SOT 冻结版终；本文件 = 初稿 + Leader 终审裁定并入（唯一实现
依据），冻结版 4 盲设计评审按 Leader 后续动作序进行，门④六步（§10.2）收口。 ——*
