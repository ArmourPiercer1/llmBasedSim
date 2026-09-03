# G10 测试验收方案（逐项核对 + step-by-step）

编制 = Plan §19（P10 任务包 T01–T08 + G10 判据 4 自动 + 3 人工）
× SOT（P10-presentation-web-realtime-image-design.md，§5 验收面 /
§6.1 平铺 57 + 边界 6）× 磁盘 byte-truth（HEAD =
`0dd032e…` 代码面 + `d1f72a0` docs 面）。
判定口径：byte-truth > SOT > 报告 > 本文。

## 第一部分 逐项核对（计划功能要求 × 实现 × 证据）

| 计划要求（Plan §19） | 实现落位（src，冻结 @ 0dd032e） | 验收面（测试） | 核对结果 |
|---|---|---|---|
| **T01** ViewState / SceneView derivation | `presentation/view.py`：SceneView 10 键 + narrative = P9 NarrativeView 5 键同名兼容（值自派生，零 P9 函数依赖）+ scene_id 确定性派生（D-P10-12）+ view_revision 投影 | `test_view.py` 7 函数（t1 双跑确定性 / t2 revision 投影 / t3 零反作用 / t4 10 键 json-clean / t5 scene_id 稳定 / t6 narrative 5 键逐字 / t7 stale 投影） | ✅ |
| **T02** Narrator presentation backend | `presentation/text/narrator.py`：template / llm 双路径（backend 注入选择）；llm = K5 脚本面（FakeInferenceBackend）；TextArtifact 携 view_revision + scene_id 标签 | `test_narrator.py` 5（t1 template 零 backend 调用 / t2 脚本命中 + source 钉 / t3 artifact 标签 / t4 确定性双跑 / t5 零 image import AST） | ✅ |
| **T03** VisualDirector + RenderIntent contract | `presentation/image/contract.py`（RenderIntent 8 字段 = Spec §32.2 逐字）+ `image/director.py`（derive_render_intent；continuity_refs = 尾 3 scene_id 序） | `test_render_intent.py` 5（t1 8 字段钉 / t2 双跑 / t3 脚本 JSON + 坏 JSON → PresentationError / t4 continuity_refs / t5 json-clean） | ✅ |
| **T04** image backend adapter + revision/scene stale handling | `presentation/image/backend.py`：DeterministicImageBackend（stdlib PPM P3，零图像库）+ FakeImageBackend + `apply_image_result`（stale 三策略 DISCARD/DISPLAY/ARCHIVE；缺省 = DISCARD，D-P10-11）+ core `is_stale`（revision.py:78）判定 | `test_image_backend.py` 8（t1 PPM 头钉 / t2 双跑 / t3 异 scene_id → 字节异 / t4 fake 回显 / t5 新鲜槽 / t6–t8 = stale 三策略单元面） | ✅ |
| **T05** Web singleton → SessionManager | `adapters/web/session.py`（SessionManager 注入式多会话；SESSION_COMMANDS 8 名闭集；state_snapshot 24 键；/save = P8 dump；load = P8 round-trip）+ `api.py`（handle_web_request 纯函数；WEB_ROUTES 9 行闭集；400/404/409/500 信封）+ `views.py`（3 页 string.Template）+ `server.py`（stdlib 薄壳，零测试调用） | `test_session_manager.py` 6（t1 生命周期 / t2 双会话隔离 / t3 快照 24 键 / t4 P8 round-trip / t5 404 面 / t6 命令闭集 + 409 面）+ `test_web_api.py` 5（t1 路由闭集 / t2 action 推进 tick / t3 image 端点 / t4 未知路由 / t5 错误信封）+ G10-3 AST（gate t3） | ✅（module-level singleton World = 零，A3 AST 全树钉） |
| **T06** Runtime Inspector minimal web view | `adapters/web/inspector.py`：build_inspector_view 12 节（Spec §37 逐字序）+ `inspect_event` = `TraceQuery.causal_chain`（trace_query.py:199）→ CausalChain 六字段端到端（P10-INV-5 零旁路） | `test_inspector.py` 4（t1 12 节键集 / t2 链端到端 / t3 revision 单调 / t4 authority 面）+ G10-4（gate t4） | ✅ 函数级交付；API 路由 `/api/inspector/{id}` = **404 保留数据面**（S4/S11 人工面 pending，SOT §3.8 披露面——见 Part 2 Step 4.7） |
| **T07** LLM Workbench minimal prompt/trace view | `adapters/web/workbench.py`：build_workbench_view 8 节 + prompt_history（calls pairs 6 字段行；ERR-P10-15 签名面）+ K8 零推词（全量字符串化零命中） | `test_workbench.py` 4（t1 prompt 史逐条钉 / t2 profile + fake 模型名 / t3 K8 clean / t4 json-clean） | ✅ 函数级交付；API 路由 = 404 保留数据面（同上） |
| **T08** stale-image / scene-continuity visual test | 机械面：gate t1（G10-1 双面）+ view t5（scene_id 稳定/变化）+ render_intent t4（continuity）+ image_backend t3/t6–t8（错场敏感 + stale 三策略）；**视觉判定 = 人工面** | `test_g10_gate.py::t1` + 上述单元面 | ✅ 机械面；⏸ 视觉判定 = S11 挂起 |
| （T04 邻接 / T08 机械面先行）tactical 布局 | `presentation/tactical/layout.py`：3 导出（TACTICAL_LAYOUT_SCHEMA_VERSION / TacticalLayout 7 键 / build_tactical_layout；hex + grid 双面） | `test_tactical_layout.py` 3（t1 hex / t2 grid / t3 零反作用） | ✅ |
| **G10 自动①** stale image 不错误覆盖当前 view | apply_image_result + is_stale + 缺省 DISCARD | `test_g10_gate_t1`（DISCARD 零覆盖 + DISPLAY stale 标记） | ✅ |
| **G10 自动②** 双 backend 读结构化 View | Narrator / VisualDirector 签名 = SceneView 唯一；text/↔image/ 零互 import | `test_g10_gate_t2`（AST 全文件面） | ✅ |
| **G10 自动③** Web 无 module-level singleton World | SessionManager 显式注入；A3 AST 扫 19 文件 | `test_g10_gate_t3` | ✅ |
| **G10 自动④** inspector 定位 event→transaction→effect→producer | inspect_event 端到端（六字段） | `test_g10_gate_t4` + `test_inspector_t2` | ✅ |
| **G10 人工①** GUI 信息层次可读 | 服务端渲染三页 + index 页 3 段导航壳（play/inspector/workbench）+ 状态表 + 图像槽 + 错误信封 | —（S11 挂起） | ⏸ 判定人 = 用户（Step 4.4） |
| **G10 人工②** 实时图像不会明显错场 | stale 标记面 + scene 敏感面（A10/t3）支撑 | —（S11 挂起） | ⏸ 判定人 = 用户（Step 4.5） |
| **G10 人工③** Galgame 场景视觉连续性可接受 | scene_id 确定性 + continuity_refs + P9 galgame 样例世界源（只读） | —（S11 挂起） | ⏸ 判定人 = 用户（Step 4.6） |
| 结构闭集面（K5/K8/D1/D6/P10-INV） | 19 src + 16 tests 白名单封闭集 | `test_p10_face.py` 6 + `TestP10Boundary` 6 方法 | ✅ |

**汇总**：T01–T08 全部实现落盘；G10 自动 4/4 机械面绿；G10 人工
3/3 = S11 挂起（判定人 = 用户，本文第二部分 Step 4）。套件恒等式
= 3142（G9 基线）+ 57 平铺 + 6 边界 = **3205**。

已知交付边界（SOT 钉，验收时点核对项而非缺陷）：

1. inspector / workbench **API 路由 = 404 保留数据面**（view 构造
   函数 + 页面模板已交付且测试绿；页面路由 = S4/S11 人工面
   pending，api.py docstring 披露）；
2. 图像 = **确定性伪图像参考面**（PPM P3 哈希投影；真实生成
   backend = P11+ / S4 人工面，SOT L545/L792）；
3. 会话推进 = **K5 模板/脚本面**（零真实 LLM；player_policy 缺省
   TemplatePlayerPolicy）。

## 第二部分 step-by-step 测试验收方案（自动化口径）

> 全部步骤在仓库根 `/home/armourpiercer/projects/llmBasedSim`、
> branch `architecture-v2` 执行。**步骤 1 = 机械面 + HTTP 面 +
> UI 机械面（全自动）；步骤 3 = 人工面（S11，判定人 = 用户）**。
>
> | 脚本 | 解释器 | 核验面 |
> |---|---|---|
> | `acceptance/run.sh` | bash | 一键编排（preflight → 起服 → HTTP → UI → 人工面提示；服务保持运行） |
> | `acceptance/preflight.py` | 主 `.venv` | 环境 + 3205 套件 + 定向 57 + 边界 44 + 行宽/控制字节/K8（官方 face t3 同口径） |
> | `scripts/v2_g10_acceptance.py` | 主 `.venv` | 验收服务驱动（galgame 样例 + 宿主侧 P10 面增强；`SESSION_ID=<hex>` 机器可读行） |
> | `acceptance/http_check.py` | 主 `.venv`（stdlib） | 路由闭集 / 信封 / 推进 / 图像确定性 / 静态引用可解析（18 项，真实 socket） |
> | `acceptance/ui_check.py` | `.venv-acceptance`（Playwright + 既有 Chromium） | 页面 3 段壳 / 连接 / 动作推进 / canvas 出图 / 错误面 / 保留面披露 + 截图存证（6 项） |
> | `acceptance/stop.sh` | bash | 停验收服务 |
>
> 报告 = `acceptance/{preflight,http,ui}-report.json`（运行时
> 产物，不入库）；截图存证 = `docs/v2/gates/evidence-g10/ui-*.png`
> （8 张，不入库，人工面闭合时随记录一并提交）。
>
> **沙箱网络对策**：本环境 chromium 直连 localhost 被拦截（curl
> 可达而浏览器不可达）——`ui_check.py` 采用 **Playwright route
> 拦截 + stdlib urllib 供给**：浏览器零真实网络连接，页面 JS
> （app.js 轮询 / fetch / PPM→canvas 解码）完整执行；HTTP 面本体
> 由 `http_check.py` 真实 socket 核验（18 项全绿），UI 层只核
> 逻辑 / 渲染 / 存证。真实浏览器中无此隔离层，行为只更直接。

### 验收前置已发现的交付缺陷（ERR-P10-16；已修复）

自动化端到端页面加载（Playwright 请求日志）发现：**index 页静态
引用 = 相对形式**（`href="styles.css"` / `src="app.js"`），`GET /`
路由把该页挂在 `/` → 相对解析落 `/styles.css` / `/app.js`（不在
WEB_ROUTES 9 行闭集）→ 404 → **页面 JS 在真实浏览器永不加载**
（`GET /` 面不可用；57 平铺 + 6 边界零覆盖，因 G10-5 人工面挂起
未暴露）。页面双源同改：`views.py` 页头/页尾源（`GET /` 路由面）
+ `static/index.html`（`/static/index.html` 面）→ 绝对引用
`/static/*`（v1 先例 web/index.html L7/L152 同形）。SOT §3.9 钉面
同步 + §9 增 ERR-P10-16 行。修复后全量 **3205/0** 复测绿；机械
回归钉 = `http_check.py` 的 `page_refs_resolvable` 双 URL 检查。

### Step 1 一键自动化

```bash
bash acceptance/run.sh            # 缺省端口 8000
```

内部序列（preflight 红 → 停；http / ui 红 → 报项继续）：

1. **preflight**：git 树/HEAD/分支 + 全量 **3205/0**（恒等式
   3142+57+6）+ 定向 11 组（view 7 / narrator 5 / intent 5 /
   image 8 / tactical 3 / session+api 11 / inspector 4 /
   workbench 4 / gate 4 / face 6 / 边界 44）+ 行宽 ≤100 零 /
   裸 0x5C 0x62 零 / K8 12 名（`test_p10_face_t3` 同口径）恰 1
   命中（narrator.py `TEXT_SOURCES` 钉元组）；
2. **起验收服务**（galgame 样例世界源；打印 `SESSION_ID=<hex>`）；
3. **HTTP 面（18 项）**：index 3 段壳 / 双 URL 静态引用可解析 /
   建会缺 world 400 / 会话列表 / state 24 键闭集（=
   `SESSION_SNAPSHOT_KEYS` session.py:111 逐字）/ action 推进
   （tick +1 + rev 递增）/ 坏体 400 / 图像端点（200 +
   image/x-ppm + `P3\n64 32\n255\n` 头钉 + 字节长 = 槽
   byte_length）/ 同图重取字节相等（D6）/ inspector·workbench
   404 保留面 + 未知路由 404 信封 / 静态 3 名 200 / 静态穿越
   400 / 缺失会话 404；
4. **UI 面（6 项，Playwright headless 自动操作 + 8 张截图）**：
   index 3 段壳 + app.js 加载 → 连接会话（state-box 出 24 键
   JSON）→ 动作 ×3（tick/rev 单调 + 图像槽注记 + canvas 出图）
   → 不存在会话「错误：」透传 → inspector / workbench 按钮
   「错误：」披露（404 保留面）。

**判据**：三报告 `all_ok = true`（已预跑全绿：3205/0 + 18/18 +
6/6；截图见 `docs/v2/gates/evidence-g10/`）。

### Step 2 验收世界说明（人工面看什么）

驱动 = P9 galgame 样例（`tests/fixtures/v2_project_galgame/`：
世界「教室」/ 玩家「转学生」/ 角色 莉娜·索蕾尔、雪村由纪）
经 P9 宿主侧装配 + 宿主侧 P10 面增强（actor 标签 + display 展示
组件 + location 实体 + game_time/weather 世界变量；全部走 core
合法接缝，零 src 改动）。会话推进 = K5 最小宿主
（HostTickDriver：tick/revision 递增；世界内容不变 = 场景稳定
面）+ TemplatePlayerPolicy（零真实 LLM）+
DeterministicImageBackend（PPM 哈希投影伪图像参考面；真实
backend = P11+）。

因此人工面可观测面：**同场景图像稳定、rev 单调、narrative
刷新**（= 不错场 / 连续性的当前宿主形态）；「场景切换 → 图像
变化」面由机械面钉（image_backend t3 异 scene_id 异字节 /
view t5 scene_id 稳定 / intent t4 continuity），人工面核当前
宿主观感即可。

### Step 3 人工面验收（G10-5/6/7；判定人 = 你）

`run.sh` 跑完会打印地址与会话 ID，**服务保持运行**：

```text
浏览器打开:  http://127.0.0.1:8000/
会话 ID:     <32 位 hex>
```

#### 3.1 浏览器操作（~2 分钟）

1. 打开地址——3 段壳（play / inspector / workbench）+ 会话
   输入框 + 状态框 + 动作输入 + 图像槽（canvas）；
2. 会话输入框填会话 ID → 点「连接」——状态框每 2s 出 24 键
   快照 JSON（`world_name` = 教室 / `player` = 转学生 /
   `npc_dynamics` = 莉娜·索蕾尔、雪村由纪 / `narrative` =
   教室（上午，晴朗）…）；图像槽初始 = 「无图像」注记；
3. 动作框输入文本（如「和身边的角色打个招呼」）→ 发送——
   `tick` +1、`view_revision` 递增、图像槽出现 canvas 图
   （64×32；背景 = environment 哈希色、每 subject 一矩形、
   mood = 边框色）+ 注记 `artifact <id> rev <n> bytes …`；
4. 再发 2–3 次动作——观察图像 / 注记 rev / narrative；
5. 刷新页面 → 重连——快照连续（会话服务端持有）；
6. （可选）故意输一个不存在会话 ID 点连接——状态框 =
   `错误：会话缺失：…`（404 信封透传）；点「取检查器数据」/
   「取工作台数据」——`错误：…`（404 保留面披露）。

自动截图已覆盖 1–6 的机械断言（`evidence-g10/ui-*.png`）；
你的人工面 = **观感判定**（下列三条），截图可作对照证据。

#### 3.2 G10-5 判定：GUI 信息层次可读

- 3 段壳分区是否清晰（play / inspector / workbench 边界）；
- 状态框 JSON 层次：24 键是否分组可读（世界面 / 叙事面 /
  玩家面 / 会话面），滚动长度是否可接受；
- 图像槽注记（artifact id / rev / stale 标记 / bytes）与图像
  本体的相对位置是否清楚；
- 错误面可读性（不存在会话 / 保留面按钮的「错误：」提示是否
  清楚，非空白 / 非 JS 报错）；
- inspector 12 节折叠区 / workbench 段的待办披露是否可读
  （S4/S11 pending 属预期披露面）。

**结论记法**：可读 / 部分可读（列具体项）/ 不可读（列具体项）。

#### 3.3 G10-6 判定：实时图像不会明显错场

- 每次动作后图像是否**与当前 scene 对应**（当前宿主 = 同
  场景 → 图像稳定不漂移；scene_id 不变 = 场景未切换，图
  像不变 = 不错场）；
- 图像注记 `rev` 是否随 `view_revision` 单调推进（无跳回）；
- 是否出现「旧场景图配新场景文」的明显错场（预期 = 不出
  现；stale 缺省 DISCARD = 过期图不覆盖当前槽，机械面已钉）；
- 刷新 / 重连后图像与文本是否一致。

**结论记法**：不错场 / 有错场（列出现场：动作文本 + 前后
scene_id + 截图）。

#### 3.4 G10-7 判定：Galgame 场景视觉连续性可接受

- 同一场景连续动作：背景色是否稳定（environment 哈希不变 →
  同背景）、subject 矩形是否连续存在（角色在场不闪断）；
- narrative `scene_text` 与图像是否同场景语境（「教室」+
  转学生 / 莉娜 / 由纪 的在场面）；
- 连续性「可接受水平」= 你的主观判定面（确定性伪图像参考
  面；真实生成 backend = P11+ / S4 人工面，SOT 钉）；
- 确定性佐证（已自动核）：同图重取字节相等（http 报告
  `image_determinism`）。

**结论记法**：可接受 / 不可接受（列具体观感 + 截图）。

#### 3.5 收尾 + 记录（SOT §10.2 格式）

1. `bash acceptance/stop.sh` 停服务；
2. 按格式记录并回贴（判定人 = 你；Leader 不自裁）：

```text
G10 人工面记录（S11）：
判定人：<用户>
时间：<YYYY-MM-DD HH:MM>
G10-5 GUI 信息层次：<可读 / 部分可读 / 不可读 + 逐条结论>
G10-6 实时图像不错场：<不错场 / 有错场 + 证据>
G10-7 Galgame 视觉连续性：<可接受 / 不可接受 + 逐条结论>
证据路径：docs/v2/gates/evidence-g10/（ui-*.png 自动截图 +
          三份 JSON 报告 + 本记录）
```

3. 记录交付 Leader 后：并入 `docs/v2/gates/G10-gate-report.md`
   「Human review required」段（挂起态 → 闭合态）并补提交
   （docs 面，含证据截图）；**在此之前 G10 决策保持「PASS
   （机械面；人工 3 挂起）」，不翻转为全量 PASS**。

### Step 4 验收结论汇总（判定矩阵）

| 面 | 判定来源 | PASS 条件 |
|---|---|---|
| 机械（G10-1..4 + 结构面） | Step 1 自动（preflight 报告） | 3205/0 + 定向 57 + 边界 44 + 纪律零违例 |
| HTTP + UI 机械面 | Step 1 自动（http / ui 报告） | 18/18 + 6/6（`all_ok = true`） |
| 人工 G10-5 | 3.2 用户判定 | 信息层次可读 |
| 人工 G10-6 | 3.3 用户判定 | 无明显错场 |
| 人工 G10-7 | 3.4 用户判定 | 连续性可接受 |

- 机械红：停，报 Leader（不自裁修复冻结面）；
- 人工任一「不可接受」：**不自裁**——登记 S11 人工面 issue，
  走 Plan §24 人工裁决（Public Contract / 主观验收分歧 = 人
  工介入面），机械面结论不变；
- 全绿 + 人工三可接受 → G10 人工段闭合 → P10 全量收口（P11+
  承接面 = 报告 §9 登记：adapters/{cli,dsh} / core F2 修复
  〔ERR-P10-08〕/ 真实图像 backend〔S4〕/ inspector-workbench
  页面路由〔S4/S11〕）。
