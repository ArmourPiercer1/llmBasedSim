# v2 引擎 Quickstart

> 目标：从零到「浏览器里跑一个 v2 会话」+「跑完整测试套件」。
> 全部命令在仓库根 `/home/armourpiercer/projects/llmBasedSim` 执行。

## 1. 环境准备

- Python >= 3.12（本仓库 `.venv` 为 3.12.14）；
- 仓库已存在 `.venv`（含 langchain / pydantic / pytest 等）——
  v2 引擎本体**不需要任何 API Key 即可运行**（见 §3 说明）；
- 可选：`pip install -e .`（在 `.venv` 内）——获得
  `llmsim` console script（project-authoring.md 用到）；不装也
  可以用 §4 的 `python -m` 等价形式。

```bash
cd /home/armourpiercer/projects/llmBasedSim
# 如 .venv 缺失：
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e . --extra-index-url '' 2>/dev/null || true
```

## 2. 跑 v2 Web 演示（当前唯一的开箱入口）

当前可运行的 v2 入口是 **Web 演示驱动**（P10 交付面 + G10 验收
驱动同一装配）：加载 P9 galgame 样例项目（「教室」世界：转学生 +
莉娜·索蕾尔 + 雪村由纪），用**确定性宿主**（HostTickDriver +
TemplatePlayerPolicy + DeterministicImageBackend）起会话服务。

```bash
PYTHONPATH=. .venv/bin/python scripts/v2_g10_acceptance.py --port 8000
# 输出两行：
#   SESSION_ID=<32 位 hex>
#   open http://127.0.0.1:8000/ （会话 ID 填入页面输入框）
```

参数：`--host 127.0.0.1`（缺省）、`--port 8000`（缺省）。Ctrl-C 停。

> **为什么没有 LLM 也能跑**：v2 的 K5 不变量 = Agent 是 Policy 不
> 是 Engine。演示宿主全部用确定性 policy / backend（零真实 LLM /
> 零真实图像 backend），所以**离线、免费、可复现**。真实 LLM 接入
> 面已建（`engine_v2/llm/` + deployment 配置），但「开箱即玩的真
> LLM 装配」属 P11+ 承接面（见 §6）。

### WebUI 操作

1. 浏览器打开 `http://127.0.0.1:8000/`——页面 3 段壳：
   **play**（会话输入 + 状态框 + 动作框 + 图像槽）/ **inspector**
   （12 节折叠区）/ **workbench**（prompt 史段）；
2. play 段填会话 ID（启动日志里的 `SESSION_ID=`）→ 点「连接」——
   状态框每 2 秒刷新 24 键快照 JSON（`world_name` / `player` /
   `npc_dynamics` / `narrative` / `scene_id` / `tick` /
   `view_revision` / `image_slot` …，键闭集 = SOT §3.7
   `SESSION_SNAPSHOT_KEYS`）；
3. 动作框输入自由文本（如「和身边的角色打个招呼」）→「发送」——
   `tick` +1、`view_revision` 递增、图像槽出现 64×32 PPM 图像
   （canvas 渲染）+ 注记 `artifact <id> rev <n> bytes <m>`；
4. inspector / workbench 按钮当前返回 404 保留面（页面把错误信封
   的 `error_message` 透传显示）——数据面已实现（`inspector.py` /
   `workbench.py`），页面路由属 P11+ 承接；
5. 刷新页面重连同一会话 ID——快照连续（会话由服务端持有）。

### 会话 HTTP API（9 路由闭集）

| 路由 | 语义 |
|---|---|
| `GET /` | index 页 |
| `GET /api/sessions` | 会话列表 |
| `POST /api/sessions` | 建会话（body `{"world": <WorldState JSON>, "session_id"?}`；world 缺失/非对象 → 400） |
| `GET /api/sessions/{id}/state` | 24 键快照 |
| `POST /api/sessions/{id}/action` | 提交动作（`{"text": ...}`；坏体 → 400） |
| `GET /api/sessions/{id}/image` | 当前图像槽（`image/x-ppm`，PPM P3 64×32） |
| `GET /api/inspector/{id}` | **404 保留面**（W5 数据面已备；路由待 P11+） |
| `GET /api/workbench/{id}` | **404 保留面**（同上） |
| `GET /static/{name}` | 静态 3 名闭集：`index.html` / `app.js` / `styles.css`（越界/穿越 → 400） |

错误信封 = `{"ok": false, "error_code", "error_message"}`；成功
信封 = `{"ok": true, ...}`（确定性序列化）。

## 3. 一键验收（机械面 + HTTP + UI 自动化）

```bash
bash acceptance/run.sh            # 缺省端口 8000；约 2–3 分钟
```

序列：preflight（环境 + 全量 3205 + 定向 57 + 边界 44 + 行宽/控制
字节/K8 扫描）→ 起演示服务 → HTTP 面 18 项（真实 socket）→
Playwright UI 面 6 项（headless 自动操作 + 8 张截图存证
`docs/v2/gates/evidence-g10/ui-*.png`）→ 打印人工面提示。
收尾 `bash acceptance/stop.sh`。

报告 = `acceptance/{preflight,http,ui}-report.json`（运行时产物，
不入库）。人工面（G10-5/6/7 三项主观判定）的步骤与记录格式见
`docs/v2/gates/G10-test-acceptance-plan.md` Step 3。

## 4. 测试套件

```bash
# 全量（G10 收口基线 = 3205 passed / 0 failed，~17s）
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q -p no:cacheprovider

# 单面（示例）
PYTHONPATH=. .venv/bin/python -m pytest tests/engine_v2/core -q -p no:cacheprovider
PYTHONPATH=. .venv/bin/python -m pytest tests/engine_v2/adapters -q -p no:cacheprovider
PYTHONPATH=. .venv/bin/python -m pytest tests/engine_v2/modules -q -p no:cacheprovider
```

套件构成（G10 恒等式 3205 = 3142 + 57 + 6）：

| 块 | 数量 | 位置 |
|---|---|---|
| G9 基线（P1–P9 全部面） | 3142 | `tests/engine_v2/` 各子包 |
| P10 平铺（view/narrator/intent/image/tactical/session/api/inspector/workbench/gate/face） | 57 | `tests/engine_v2/{presentation,adapters,modules}/` |
| P10 边界方法 | 6 | `tests/engine_v2/core/test_import_boundary.py` `TestP10Boundary` |

## 5. 校验你自己的项目

写了 v2 项目（project-authoring.md）后先校验：

```bash
# 装了 console script：
.venv/bin/llmsim validate path/to/project
# 未装（等价）：
PYTHONPATH=. .venv/bin/python -m src.engine_v2.content.cli validate path/to/project
# 机器可读（4 键封闭 JSON envelope）：
PYTHONPATH=. .venv/bin/python -m src.engine_v2.content.cli validate path/to/project --json
```

退出码：0 = 无 error；1 = 有 error 级诊断；2 = 用法错。样例项目
`tests/fixtures/v2_project_galgame`（0 error / 0 warning 可复现）。

## 6. 「真 LLM 开局」现在能做到什么程度（边界说明）

| 面 | 状态 |
|---|---|
| LLM 抽象层（structured inference / InferenceProfile / router / providers） | **已建**（P6；provider-neutral；K8 部署分离） |
| deployment.yaml 声明面（models / inference_profiles） | **已建**（样例 `tests/fixtures/v2_deployment/deployment.yaml`） |
| 项目声明推理 capability（game.yaml） | **已建**（P5；Spec §5.5） |
| 真实 provider 接线 + 开箱即玩装配 | **未建**（P11+ 承接；当前演示 = 确定性宿主，K5 合规） |
| 真实图像生成 backend | **未建**（S4 人工面；当前 = PPM 哈希投影确定性参考面） |
| CLI 适配器 / DSH 适配器 | **未建**（P11） |

也就是说：v2 现在是**引擎 + 数据面 + 开发面全绿、表现面就绪**，
「接上真 LLM 玩一局」是 P11 的活；在那之前，Web 演示（§2）就是
体验 v2 会话循环的官方入口。
