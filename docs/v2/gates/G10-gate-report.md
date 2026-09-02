# G10 Gate Report — Phase 10 Presentation / Web Realtime Image（终版）

按 `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md`
§19、§21、§24 编制。
W0 设计 SOT 冻结 + W1–W5 全部实现波次盲审收敛（逐轮记录见 §5），
门④ 六步全绿（3205/0），本报告为 G10 最终交付点记录。

---

## 0. 基础信息

- **Gate**: G10（Phase 10 — Presentation 与 Web 实时图像 门禁）
- **Commit SHA**: `0dd032eff1adeeae8fa2812cd672ab6a567ce4df`（代码面）；
  docs 闭合链至本报告提交
- **分支**: `architecture-v2`
- **审查基准**: `99455650f964aa0aee5416a70a1a655135077419`（G9 收口，
  套件 3142）.. `0dd032e`（代码面）；SOT =
  `docs/v2/contracts/P10-presentation-web-realtime-image-design.md`
  （~1500 行；ERR-P10-01..15 全链在位，§9）
- **测试基线**: 全量 **3205 passed / 0 failed**（gate ③ 真实输出，
  16.62s）；P10 全程 +63 = 3205 − 3142：W1 +7 / W2 +10 / W3 +11 /
  W4 +11 / W5 +18 平铺 + 6 边界方法（§8.3 恒等式
  3142 + 63 = 3205 对账一致）
- **审查执行**: W0 设计盲评 R1–R3 三轮收敛（R1 2 补 + 2 通 →
  R2 1 补 + 3 通 → R3 4×通过）+ 实现波次 W1–W5 各 R1 单轮 4×通过
  （零修正波）+ 门禁阶段 R1 × 4 名独立盲审，四裁决协议
  （通过/投机通过/补充内容/阻塞）

## 1. §21 字段（Plan §21 模板逐字）

```text
Gate: G10
Commit SHA: 0dd032eff1adeeae8fa2812cd672ab6a567ce4df
Tasks completed: P10-T01 ~ P10-T08（全部；明细见下）
Tasks waived: （无）
Tests: 3205 passed / 0 failed（gate ③ 真实输出；§8.3 恒等式
       3142 + 63 = 3205 对账一致）
Known failures: （无）
Architecture deviations: D-P10-01..12 决策登记（SOT §4，12 条全
       批准）+ DEV-P10-01..05 偏差登记（§8.4，DEV-P10-01 闭合 /
       DEV-P10-05 = uuid4 身份标签例外）
Open risks: （§7 风险登记册 SOT §0.6 R1–R5 闭合状态；R4 机械面
       已承接 = face t6，前端构建栈 = 非范围标志位）
Human review required: S11 三人工判据挂起面（G10-5 GUI 信息层次
       可读 / G10-6 实时图像不错场 / G10-7 Galgame 场景视觉连续性
       可接受）——判定人 = 用户（人），Leader 不自裁；记录格式 =
       SOT §10.2 注记钉（判定人 / 时间 / G10 三人工判据逐条结论
       （G10-5/6/7）/ 截图或文本证据路径）；机械面（本 gate）不
       替代人工判定。Plan §24 S4（引入新的重大依赖 / License 风险）
       同面核验：JS/Node 工具链 = 非范围，face t6 零构建产物（§8）
Decision: PASS（SOT §8.3 门面条数 7 = 自动 4 + 人工 3：自动
       G10-1..4 全绿 + 结构面 face t1–t6 全绿；人工 G10-5..7 =
       S11 延期挂起，非 FAIL）
```

### 1.1 Tasks completed 明细

- **T01** = W1：`presentation/view.py`（5 导出：PresentationError /
  VIEW_SCHEMA_VERSION / SceneView / scene_id_of / derive_scene_view；
  SceneView 10 键 + tactical_domain_id 参数缺省 None 钉）+
  presentation 测试包件 + conftest（4 fixture + autouse 隔离屏障，
  §6.4 跨波冻结）+ test_view 7（W1，3149）；
- **T02** = W2：`presentation/text/{__init__,narrator}.py`（5 导出；
  NARRATOR_LOGICAL_ROLE / TEXT_SOURCES 钉元组（K8 唯一允许命中，
  ERR-P10-10）/ TextArtifact / NarratorPresentationBackend /
  narrate_scene；backend 注入面 = K5 零真实 LLM）+ test_narrator 5；
- **T03** = W2：`presentation/image/{__init__,contract,director}.py`
  （6+3 导出；apply_image_result 8 分支 + ImageStalePolicy 枚举
  `is` 身份 + future-revision docstring 钉；VisualDirector /
  derive_render_intent）+ test_render_intent 5（W2，3159）；
- **T04** = W3：`presentation/image/backend.py`（5 导出；PPM P3
  确定性字节 = f(intent)，6144 组件；width/height ≤0 / 非 int /
  bool → ValueError；artifact_id = "art:"+sha256[:16]）+
  `presentation/tactical/{__init__,layout.py}`（3 导出；TacticalLayout
  TypedDict 7 键；几何事实宿主镜像 = world_variables 保留键
  "spatial_domains" 经 core G-INV/S-INV 校验；`_TacticalLayoutError`
  ValueError 族私有类（ERR-P10-13））+ view.py tactical 填充
  （ERR-P10-11，4 hunk）+ test_image_backend 8 + test_tactical_
  layout 3（W3，3170）；
- **T05** = W4：`adapters/web/{__init__,session,api,views,server}.py`
  + static 3（session：SESSION_COMMANDS 8 名闭集（/c 不承接）/
  TickDriver / TemplatePlayerPolicy / WebSession / SessionManager /
  SessionNotFoundError；注入式多会话容器零模块级实例；SESSION_
  SNAPSHOT_KEYS 24 键 JSON-clean；session_id 缺省 uuid4().hex 单点
  = DEV-P10-05 身份标签例外（P10 唯一非确定性默认；测试显式传参）；
  api：WEB_ROUTES 9 行闭集（/api/inspector、/api/workbench = W5
  数据面保留行）/ WebApiError status {400,404,409,500} / WebResponse
  frozen / handle_web_request 纯函数（相对 manager）/ resolve_
  static_name；错误信封恰 3 键；views：PAGE_NAMES 3 页 + string.
  Template 零 Jinja2 + html.escape 单点转义；server：create_web_
  server / run_web_server stdlib 薄壳，测试零调用；static：
  index.html / app.js（190 ≤ 200 行，零 import/require/document.
  write/innerHTML）/ styles.css）+ web 测试包件 + conftest（4
  fixture + HostTickDriver + W1 冻结 fixture re-export）+
  test_session_manager 6 + test_web_api 5（W4，3181）；
- **T06** = W5：`adapters/web/inspector.py`（3 导出：INSPECTOR_
  SECTIONS 12 节 Spec §37 逐字序 / build_inspector_view 纯投影 12 节 /
  inspect_event = TraceQuery.causal_chain → CausalChain.to_dict()
  全量六字段；链全经 TraceQuery + 世界只读投影 + 零 core.entity/
  core.components 直读 import（P10-INV-5））+ test_inspector 4；
- **T07** = W5：`adapters/web/workbench.py`（3 导出：WORKBENCH_
  SECTIONS 8 节 / build_workbench_view / prompt_history；ERR-P10-15
  calls pairs 签名；token_usage None 显式保留；critic_repair 非范围
  标志）+ test_workbench 4；
- **T08** = W3 机械面（stale 策略三钉）+ W5 收口：test_g10_gate 4
  （G10-1..4 每面恰 1 函数）+ test_p10_face 6（结构面 t1–t6）+
  TestP10Boundary 6 方法（锚文件 EOF 纯追加；m5 = 96 项 v1 清单 +
  m6 冻结面清单 = @9945565 构建期 sha 字面量，测试运行时零
  git/subprocess）（W5，3205）。

## 2. 门禁判据验证（SOT §5 G10-1..7 + 双重证据）

| 判据 | 口径 | 机械验证面 | 结果 |
|---|---|---|---|
| G10-1（A1） | stale 图像不错误覆盖当前 view | test_g10_gate_t1（DISCARD 零覆盖 + DISPLAY stale 标记且槽 revision 钉）+ W3 test_image_backend t6–t8（apply_image_result 策略三面；SOT §5.2 A1 辅助面） | 绿 |
| G10-2（A2） | 双 backend 结构化 view 独立 | test_g10_gate_t2（同 SceneView → narrate_scene + derive_render_intent 独立消费）+ 特例钉 text ↔ image 零互 import（face t4 同源） | 绿 |
| G10-3（A3） | Web 无 module-level singleton World | test_g10_gate_t3（AST 扫 adapters/web + presentation 全树 19 文件：零模块级 WorldState()/SessionManager()/WebSession()/Scheduler()/LogicalClock() 实例化 + 零模块级 session 全局） | 绿 |
| G10-4（A4） | inspector 定位 event → transaction → effect → producer | test_g10_gate_t4 + test_inspector_t2（inspect_event = TraceQuery.causal_chain（trace_query.py:199）→ CausalChain.to_dict()（:75）端到端；六字段全量投影；事件缺席 TraceQueryError 透传 404 面） | 绿 |
| G10-5（人工①） | GUI 信息层次可读 | 服务端渲染三页（index/inspector/workbench，§3.12）承载面在位（机械）；**判定 = S11 人工延期（判定人 = 用户）** | 挂起 |
| G10-6（人工②） | 实时图像不错场 | stale 标记面（slot.stale，§3.3）+ scene 敏感面（A10/t3 + view t5）支撑面在位（机械）；**判定 = S11 人工延期（判定人 = 用户）** | 挂起 |
| G10-7（人工③） | Galgame 场景视觉连续性可接受 | scene_id 确定性派生（§3.1）+ continuity_refs（§3.4）+ P9 galgame 样例（只读）世界源在位（机械）；**判定 = S11 人工延期（判定人 = 用户）** | 挂起 |

## 3. 门④ 六步执行（SOT §10.2，2026 收口时点实测）

- **①** `git rev-parse HEAD` = `0dd032eff1adeeae8fa2812cd672ab6a567ce4df`
  —— 晚于 G9 收口 `99455650f964aa0aee5416a70a1a655135077419`
  （`git merge-base --is-ancestor` = 0，ancestor 确认）；architecture-
  v2 分支。
- **②** `git diff --name-status 9945565..HEAD -- src tests scripts`
  = **37 唯一路径**（19 src A + 16 tests A + 2 M）——与 §11 白名单
  38 行逐路径 A/M 模式匹配（表外零路径；行 1 / 行 38 同路径
  view.py：diff 行 = A〔行 1 模式〕，行 38 M 面 = 文件内 W3 修改
  面描述，非独立 diff 行——ERR-P10-14 口径）；v1 路径集与 P9 树
  零行（D-P10-08 / P10-INV-9）。明细见 §4。
- **③** 全量 `pytest -q` = **3205 passed / 0 failed**（16.62s）=
  G9_final + 63 = 3142 + 63 = 3205（§8.3 恒等式，实测重算完成）；
  failed/error/skipped = 0。
- **④** TestP10Boundary 6 方法全绿（锚文件定向 44 passed，含
  TestP9Boundary / TestP8Boundary / TestP7Boundary / TestP6Boundary
  既有块——冻结面自证）。
- **⑤** 宽度 + 控制字节：P10 src 19 文件（含 static 3）行宽 ≤100
  零超限；零裸 0x5C 0x62（锚文件 23 处既有命中全在冻结 L1–2625
  P4–P8 块 L552–L1944〕，非 P10 面）。
- **⑥** 台账与链更新：§8.2 导出台账 12 模块 49 名冻结（face t2
  逐字核）；§8.4 偏差链 DEV-P10-01..05 齐（零更新）；§9 勘误链 =
  **15 行**（ERR-P10-01..15——本步补录 ERR-P10-08 行（F2 core
  坑；W1 裁决「W5 门④⑥ 步落 SOT §9」执行；view.py:16 docstring
  引用编号闭合））。

## 4. 白名单 diff（gate ②，封闭集 38 行 / 37 唯一路径）

**src（行 1–19，18 A + 1 M〔行 1 = W3 tactical 填充面，见行 38；
ERR-P10-11〕；diff 面 = 19 A）**

| # | 路径 | diff 模式 |
|---|---|---|
| 1 | `src/engine_v2/presentation/view.py` | A（+ 行 38 M 面） |
| 2 | `src/engine_v2/presentation/text/__init__.py` | A |
| 3 | `src/engine_v2/presentation/text/narrator.py` | A |
| 4 | `src/engine_v2/presentation/image/__init__.py` | A |
| 5 | `src/engine_v2/presentation/image/contract.py` | A |
| 6 | `src/engine_v2/presentation/image/director.py` | A |
| 7 | `src/engine_v2/presentation/image/backend.py` | A |
| 8 | `src/engine_v2/presentation/tactical/__init__.py` | A |
| 9 | `src/engine_v2/presentation/tactical/layout.py` | A |
| 10 | `src/engine_v2/adapters/web/__init__.py` | A |
| 11 | `src/engine_v2/adapters/web/session.py` | A |
| 12 | `src/engine_v2/adapters/web/api.py` | A |
| 13 | `src/engine_v2/adapters/web/inspector.py` | A |
| 14 | `src/engine_v2/adapters/web/workbench.py` | A |
| 15 | `src/engine_v2/adapters/web/views.py` | A |
| 16 | `src/engine_v2/adapters/web/server.py` | A |
| 17 | `src/engine_v2/adapters/web/static/index.html` | A |
| 18 | `src/engine_v2/adapters/web/static/app.js` | A |
| 19 | `src/engine_v2/adapters/web/static/styles.css` | A |

**tests（行 20–35，16 A；diff 面 = 16 A）**

| # | 路径 | diff 模式 |
|---|---|---|
| 20 | `tests/engine_v2/presentation/__init__.py` | A |
| 21 | `tests/engine_v2/presentation/conftest.py` | A |
| 22 | `tests/engine_v2/presentation/test_view.py` | A |
| 23 | `tests/engine_v2/presentation/test_narrator.py` | A |
| 24 | `tests/engine_v2/presentation/test_render_intent.py` | A |
| 25 | `tests/engine_v2/presentation/test_image_backend.py` | A |
| 26 | `tests/engine_v2/presentation/test_tactical_layout.py` | A |
| 27 | `tests/engine_v2/adapters/__init__.py` | A |
| 28 | `tests/engine_v2/adapters/web/__init__.py` | A |
| 29 | `tests/engine_v2/adapters/web/conftest.py` | A |
| 30 | `tests/engine_v2/adapters/web/test_session_manager.py` | A |
| 31 | `tests/engine_v2/adapters/web/test_web_api.py` | A |
| 32 | `tests/engine_v2/adapters/web/test_inspector.py` | A |
| 33 | `tests/engine_v2/adapters/web/test_workbench.py` | A |
| 34 | `tests/engine_v2/adapters/web/test_g10_gate.py` | A |
| 35 | `tests/engine_v2/adapters/web/test_p10_face.py` | A |

**既有文件修改（行 36–38，diff 面 = 2 M）**

| # | 路径 | diff 模式 | 修改面 |
|---|---|---|---|
| 36 | `tests/engine_v2/core/test_import_boundary.py` | M | P10 块 EOF 纯追加（W2–W4 清单刷新 3 条 + W5 TestP10Boundary 6 方法；L1–2625 逐字节不变，head-2071 sha = 26fc0528…dbc9202 / head-2625 sha = 76e8cfc9… 双钉） |
| 37 | `tests/test_engine_v2_skeleton.py` | M | SUBPACKAGES 13→17（+presentation.text/.image/.tactical/.adapters.web 4 子包）+ 计数文案 13→17 + 检查逻辑字节不变 |
| 38 | `src/engine_v2/presentation/view.py` | M（同路径合并于行 1 A） | W3 tactical 填充 4 hunk（ERR-P10-11；closure += tactical.layout 单向零环） |

## 5. 审查记录（逐轮；JSON 全文在 .review-drafts/，gate 闭合后
按 P8 先例保留不入库）

| 轮 | 范围 | 结果 | 处置 |
|---|---|---|---|
| W0 R1–R3 | 设计 SOT 4 盲 | R1 2 补 + 2 通 → R2 1 补 + 3 通 → **R3 4×通过**（0 SUPPLEMENT / 0 BLOCK；2 DOC 预提交修正） | 勘误链 ERR-P10-01..07 落 §9；SOT 冻结提交 388ea8f |
| W1 R1 | T01（7 函数） | **4×通过**（单轮收敛；F2 core 坑 2 评审独立复现 + 规避验证） | 3 处 docstring 预提交修正；ERR-P10-08 登记（本 gate ⑥ 落行）；提交 4e092a5（3149） |
| W2 R1 | T02+T03（10 函数） | **4×通过**（单轮收敛） | ERR-P10-09/10/11/12 四条落 §9 + test_narrator t1 docstring 预提交修正；提交 989e088（3159） |
| W3 R1 | T04+tactical（11 函数） | **4×通过**（单轮收敛；F-W3-01 dev 停手报裁） | ERR-P10-13 一条落 §9 + layout.py 2 处 docstring 预提交修正；提交 aa52614（3170） |
| W4 R1 | T05（11 函数） | **4×通过**（单轮收敛） | ERR-P10-14/15 两条落 §9 + session/views 未使用 import 2 行预提交修正；提交 07cc557（3181） |
| W5 R1 | T06+T07+T08（18 平铺 + 6 边界） | **4×通过**（单轮收敛；INFO ×16 去重 6 面留档） | 零修正；提交 0dd032e（3205） |
| Gate R1 | 门④ 六步 + 本报告 | 4 名独立盲审：1 SUPPLEMENT（×3 人）+ 1 SPECULATIVE_PASS；G1–G4/G6 全 met（六步独立重跑全绿）；G5 报告面错配 ×5（§7 风险表 R1–R8 误标〔SOT §0.6 实为 R1–R5〕/ §6.1 决策行 D-P10-04/11 内容错位 / §5 ERR-P10-11 轮次归属 / §8 未锚 Plan §24 逐字定义 / §1 分母措辞） | 全部报告面更正（纯 docs，零机械面重跑）→ R2 复核 |
| Gate R2 | 更正复核 + 终核 | 4 名独立盲审：1 PASS + 3 SUPPLEMENT（low/DOC）；G1–G4/G6 全 met（六步独立重跑全绿；R1 五项更正 5/5 落位零回归）；R2 新发现 6 处报告面单行失准（§2 G10-1 波次标签 / §6.1 D-P10-04 第三导出名 / §8 S3 文件名 / §3⑤ 区域口径 / §7 R4/R5 措辞） | 6 处单行更正（byte-verify 闭合：t6–t8 策略三面 / TACTICAL_LAYOUT_SCHEMA_VERSION / scripts/v2_migrate_v1.py / P4–P8 块 L552–L1944 / A7/t6 5 键钉）→ R3 终核 |
| Gate R3 | 更正面核验 + 零回归 | 4 名独立盲审：1 PASS + 3 SUPPLEMENT（low/DOC）；G1–G4/G6 全 met（六步独立重跑全绿；R2 六更正 6/6 落位零回归）；R3 新发现 4 处单行失准（§8 S5 t3→t4 / §7 R5 t1/t3→t4 / 报告头 Plan §17→§19〔G10 相章 = Plan §19 L817，G9 头同型笔误〕/ §3⑤ 游离括号） | 4 处单行更正 byte-verify 闭合（test_session_manager_t4 往返钉 / test_view_t4 10 键闭集 / Plan §19 = G10 定义章 / 括号配平）；评审人明示「更正后闭合（R2 先例）」→ G10 门闭合 |

## 6. 偏差登记

### 6.1 决策登记（D-P10-01..12，SOT §4 五段；12 条全批准）

- D-P10-01 View 与 P9 NarrativeView 关系：SceneView.narrative =
  与 P9 NarrativeView **5 键同名兼容**的 dict（tick / scene_text /
  frames / actors_visible / clock）；值 = P10 自派生投影（零 P9
  函数调用、零 engine_v2.modules import——形状复用、函数不消费）；
  P9 模块零改动；
- D-P10-02 image backend 参考实现：DeterministicImageBackend =
  stdlib PPM P3 伪图像面（零 PIL/Pillow；确定性字节 = f(intent)）；
- D-P10-03 Web 服务框架：api.py::handle_web_request(method, path,
  body, *, manager) 无状态纯函数（相对 manager）+ stdlib
  http.server 薄壳（零模块级状态；测试零调用）；
- D-P10-04 Tactical presentation 最小面：tactical/layout.py 3 导出
  （TACTICAL_LAYOUT_SCHEMA_VERSION / TacticalLayout TypedDict 7 键 /
  build_tactical_layout；decode_spaces 消费面；零 core 修改）；
- D-P10-05 SessionManager 语义：Session =（WorldState 实例 + 注入
  TickDriver 宿主 + 注入 policy）注入式多会话容器（零模块级实例；
  /save = 注入 save_sink 经 P8 dump）；
- D-P10-06 P10 包落位与文件布局：§3.0 包树（src 19 新文件：
  presentation 9 + adapters/web 7 + static 3）；含包级 view.py
  （Spec §44 树仅列 3 子包 → 本 SOT 增包级公共文件，披露——与
  DEV-P10-04 同面）；
- D-P10-07 HTML 渲染：stdlib string.Template（views.py =
  Template.safe_substitute + 值全量 html.escape；零 Jinja2）；
- D-P10-08 v1 web/ui 文件保持冻结（43.2-8 移除 = v2 不存在，非
  删除）：P10-INV-9 零修改零删除 + 3 web 子树哈希钉（边界 m5
  反例锚面）；
- D-P10-09 波次划分 W1–W5：W1 = T01；W2 = T02+T03；W3 =
  T04+tactical；W4 = T05；W5 = T06+T07+T08 收口 + 边界块；波内序
  = 契约 → 消费；
- D-P10-10 计数恒等式（门④期望）：G9_final + 63（63 = 57 平铺 +
  6 边界；G9_final = 3142 → 3205）；
- D-P10-11 image stale 默认策略 = DISCARD（apply_image_result 与
  WebSession 缺省；策略可注入——DISPLAY stale 标记面）；
- D-P10-12 scene_id 派生规则：scene_id_of(scene_key) =
  "scene:" + sha256("|".join(元素)) 截断（确定性派生；同输入同
  输出，零随机）。

### 6.2 偏差登记（DEV-P10-01..05，SOT §8.4）

- DEV-P10-01（闭合）：P9 W6/W7 交付物 W0 初稿时点口径 → G9 收口
  回填完成；
- DEV-P10-02：T01 双名口径（ViewState 泛称 vs SceneView 具体类）
  → 本 SOT 钉 SceneView；
- DEV-P10-03：G10-1 语义 vs Spec §32.3 三策略 → 缺省 DISCARD +
  策略可注入（DISPLAY stale 标记面）；
- DEV-P10-04：Spec §44 树未列包级文件 → 本 SOT 增包级 view.py
  （披露）；
- DEV-P10-05：session_id 缺省 uuid4().hex = P10 唯一非确定性默认
  （身份标签例外；测试显式传参纪律；session.py:676 单点）。

### 6.3 各波自裁披露面（零偏差 + 解释性披露）

- W1：findings F1–F7（F2 = core 坑 → ERR-P10-08；其余 docstring
  措辞/口径注记）；
- W2：12 项解释性披露（SOT 未钉死面合法设计裁量，docstring 自
  披露）；
- W3：D-W3-01/02 设计落点（几何事实宿主镜像 / camera 不入字节
  派生）+ F-W3-01（→ ERR-P10-13）；
- W4：12 项解释性披露（宿主世界槽重读面 / WEB_ERROR_CODES 7 名 /
  /save 内存 sink 等，docstring 自披露）；
- W5：conftest 跨树 fixture 不解析 → 测试函数内局部构造（合法面
  11）+ workbench docstring K8 措辞自纠。

## 7. 风险登记册（SOT §0.6 R1–R5 1:1；G10 闭合状态）

| # | 风险（SOT §0.6） | 等级 | SOT 缓解面 | G10 闭合状态 |
|---|---|---|---|---|
| R1 | G9 收口漂移：P9 W5 未提交 / W6–W7 未落盘 → P10 消费面锚点漂移（narration 5 键、space 4 名、边界锚行号） | 高 | W0 终审 Q7 裁定「W1 等 G9 收口」（W1 派发前 §0.3.1 回填完成）+ 消费锚实测落值（W0 SOT） | 闭合（W1–W5 消费面零漂移；5 波 4 盲全通过） |
| R2 | web handler 层「顺手」长成有状态常驻服务（模块级 session / 全局 world） | 中 | D-P10-03（无状态 handler + 注入 SessionManager）+ P10-INV-4 + g10_gate_t3（A3 AST 19 文件） | 闭合 |
| R3 | image backend「顺手」引图像库（PIL/Pillow 等） | 中 | D-P10-02（stdlib PPM P3 伪图像面）+ D4 闭集 + 边界方法 4 + S4 触发面 | 闭合（face t4 import 闭集 + face t6 零构建产物 + 边界 m4） |
| R4 | JS 静态面膨胀为前端构建栈（package.json / bundler 出现） | 中 | face t6（零构建产物 AST/文件检查）+ 边界方法 1/2 | 机械面闭合（app.js ≤200 行 + 零 import/require/innerHTML + face t6）；人工面 = S11 挂起（Plan §24 S4 机械面未触发，§8） |
| R5 | SceneView 与 P9 NarrativeView 兼容面漂移（P9 W6 实现若改 5 键名） | 低 | A7/t6 键名钉 + D-P10-01 形状复用（非函数依赖） | 闭合（view t4 10 键闭集 + t6 5 键同名兼容钉〔A7/t6〕+ P9 树零 diff〔m5/m6 哈希钉〕） |

## 8. HARD STOP 逐条核验（Plan §24 逐字定义 + P10 相位证据）

- **S1 — 需要改变 Architecture Kernel invariant**：未触发——P10
  零 kernel 修改（m6(c) 冻结子树哈希钉；F2 core 坑 = 仅登记
  ERR-P10-08，core 侧修复 = 非 P10 范围，零 core 改动）；
- **S2 — Public Contract 存在两种同样合理但不兼容的设计**：未
  触发——P10 SOT = 单一契约（12 决策全部 Leader 终审判批；
  ERR-P10-01..15 全链 = 单侧勘误裁定，零「两设计悬置」项）；
- **S3 — 为通过测试需要 destructive migration**：未触发——零 v1
  数据迁移面（P10 不触碰 v1 数据；scripts/v2_migrate_v1.py = P9 冻结面）；
- **S4 — 引入新的重大依赖 / License 风险**：未触发——pyproject.toml
  字节冻结（m6(a) 钉；零新增第三方依赖；JS/Node 工具链 = 非范围，
  face t6 零构建产物）；
- **S5 — Backend 无法满足 replay/checkpoint Contract**：未触发——
  /save = P8 冻结 dump codec（W4 t4 round-trip 钉）；WebSession 零
  新增 checkpoint 语义；
- **S6 — 同一任务经过能力升级仍连续失败**：未触发——W0–W5 全部
  单轮（设计 3 轮）收敛，零返工波；
- **S7 — 测试通过但语义明显违背设计**：未触发——G10-1..4 机械面
  + face t1–t6 + 5 波 × 4 盲（SOT 逐字判据 vs byte-truth 双重
  证据；W1–W5 各波钉面逐一核）；
- **S8 — 发现 baseline 本身与 Architecture 目标冲突，但兼容意图
  不清楚**：未触发——G9_final = 3142/0 基线 = G9 门禁闭合；P10
  消费面 = G9 冻结面（零兼容意图模糊；D-P10-01 5 键同名兼容 =
  显式裁定）；
- **S9 — 并发 / 异步导致无法解释的 state corruption**：未触发——
  P10 零并发面（web handler = 同步纯函数 + 单线程 stdlib 薄壳，
  测试零调用；D6 零 wall-clock）；
- **S10 — 性能目标需要架构级 tradeoff**：未触发——P10 零性能
  判据面（K5 假 backend；性能面 = 非 P10 范围）；
- **S11 — 多模态主观验收无法确定**：挂起（非触发非闭合）——
  G10-5/6/7 三人工判据 = 本条对象；判定人 = 用户（Leader 不自
  裁）；记录格式 = SOT §10.2 注记钉（判定人 / 时间 / G10-5/6/7
  逐条结论 / 截图或文本证据路径）；
- **S12 — Agent 想重构超出工作包边界**：未触发——门④② 37 唯一
  路径封闭集 + 白名单外零写盘（表外零路径；P10-INV-8/9 冻结面
  哈希钉）。

## 9. 结论

**G10 = PASS（机械面）**：门④ 六步全绿（① 0dd032e ≥ 9945565 /
② 37 唯一路径 == 白名单封闭集 / ③ 3205/0 == 3142+63 / ④ 边界块
44 绿（含 P6–P9 冻结自证）/ ⑤ 宽度 + 控制字节零违例 / ⑥ 台账 +
DEV 链 + §9 15 行勘误链更新完成）。T01–T08 全部交付；D1–D8 纪律
全程在位；P10-INV-1..10 全链机械面闭合。

**人工面（S11）挂起**：G10-5（GUI 信息层次）/ G10-6（实时图像
不错场）/ G10-7（Galgame 视觉连续性）三判据判定人 = 用户；Leader
以 galgame 样例世界源驱动 web 会话的验收方案 = gate 时点人工执行
（Plan §21 L901 记录格式）。本 gate 机械面不替代人工判定。

P10 收口。后续波次（P11+：adapters/{cli,dsh} 面 / core F2 修复
承接〔ERR-P10-08〕/ S11 人工面执行）不在本阶段范围。
