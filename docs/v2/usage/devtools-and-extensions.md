# v2 开发控制平面（devtools）与扩展点

> 对应 Spec §3.2「Development Control Plane」+ §22 / §30 / §33 / §37。
> 工具链：`llmsim-devcontrol`（存档检视 / 追踪查询 / 重放 / 分支 /
> 一致性检查）；概念：存档布局、回放语义、持久化；扩展：模块 /
> 插件 / LLM / dynamics / 表现层。

## 1. `llmsim-devcontrol` 命令

入口 = 薄壳脚本 `scripts/v2_devcontrol.py`（逻辑面
`src/engine_v2/devtools/cli.py`）：

```bash
PYTHONPATH=. .venv/bin/python scripts/v2_devcontrol.py <command> <save_id> [选项]
```

| 命令 | 语义 |
|---|---|
| `inspect <save_id>` | 快照派生 4 项：`world_state` / `runtime_state` / `backend_refs` / `persistence_versions`（Spec §37 快照派生面） |
| `trace <save_id> [--kind K]` | 查询 trace 记录流（可按 kind 过滤，`--kind` ∈ §1.1 闭集） |
| `replay <save_id>` | 自快照 revision 起重放**最长连续已提交事务前缀**（连续性语义：每笔 `txn.base_revision == 当前状态 revision`） |
| `branch <save_id> --new-id <id>` | 自存档派生新实例（分支 = 新 WorldInstance，原档不变） |
| `test <save_id>` | 跑一致性检查报告（快照 vs trace 对齐等） |

**输出纪律**：每命令 stdout = 且仅 = 一行 JSON 信封（6 键封闭：
`tool` / `schema_version` / `command` / `ok` / `data` / `error`；
`--json` 显式开启 JSON 模式，缺省 human 面）。退出码：0 = ok；
1 = 业务失败（error_code ∈ `P8_ERROR_CODES` 闭集）；2 = 用法错。

### 1.1 TraceKind 闭集（12 值）

`command` / `action_proposal` / `proposed_effect` /
`authority_decision` / `validation_decision` / `conflict_resolution`
/ `transaction`（含 ABORTED，审计原子失败）/ `domain_event` /
`llm_call`（P6 起）/ `prompt_assembly` / `dev_intervention` /
`system`。

每条 `TraceRecord` = 单一信封 + kind 判别 + 开放 payload；权威
排序坐标 = `world_revision + logical_tick`（`wall_time` 仅诊断，
永不用于排序）。

### 1.2 存档布局（filesystem backend）

```text
saves_root/                      # 缺省 = <cwd>/saves_root（W4 约定）
└── <save_id>/
    ├── index.json               # {"persistence_format_version": 1, …}
    ├── snapshot.json            # PersistenceSnapshot 全文（存档时刻终态）
    ├── checkpoints/
    │   └── <backend_id>.json    # 每 backend 一个 checkpoint（JSON-clean）
    └── trace.jsonl              # 每行一条 TraceRecord（保序）
```

注意（回放语义边界，P8 裁决 DEV-W4-2）：存档格式只持久化**存档
时刻的终态快照**，不含 trace 基线态；因此「运行结束时刻存档」的
全史重放不可行，`replay` 的语义 = 自快照 revision 起的最长连续
已提交前缀。要全史重放 → 在运行中途 checkpoint（含基线态）。

## 2. 持久化 / 回放 / 分支（P8 概念面）

| 概念 | 说明 | 代码面 |
|---|---|---|
| **Snapshot** | 五态分离中的 WorldState/RuntimeState/BackendState/TraceState 投影（Spec §8） | `persistence/snapshot.py` |
| **Checkpoint** | 运行中的中间点（每 backend 独立） | `persistence/checkpoint.py` |
| **Replay** | 事件级回放：按 trace 逐笔重放已提交事务，逐笔复检 base_revision 连续性；断裂 → 停在最长前缀 | `persistence/replay.py` |
| **Branch** | 自存档派生新实例（世界状态分叉；K1 权威态不共享） | `persistence/branch.py` |
| **Backend** | `FilesystemPersistenceBackend`（缺省）+ 抽象接口（可换存储） | `persistence/filesystem.py` / `base.py` |
| **Dev intervention** | 开发期干预（trace kind `dev_intervention`，Spec §22） | `devtools/intervention.py` |
| **Trace query** | trace 流的查询 API（inspector 数据面消费） | `devtools/trace_query.py` |

**不变量**：回放 / 分支 / 检视全部**只读消费**存档，且回放结果
必须与在线执行逐字节一致（D6 确定性；由测试钉：双跑相等）。

## 3. 扩展点（P11+ 之前可做的）

### 3.1 模块（modules，P9 官方 9 模块已建）

官方模块（`src/engine_v2/modules/`）：

| 模块 | 职责 |
|---|---|
| `attributes` | 数值属性系统（value/min/max/自然 delta/锁定规则） |
| `inventory` | 物品 / 持有 / 使用 |
| `character` | 角色模型（personality / relationships / speech） |
| `knowledge` | 知识 / 记忆 |
| `perception` | 感知过滤（世界态 → 玩家可感知面） |
| `relationships` | 关系数值演化 |
| `space` | 空间域（Grid / Hex 双域位置 + 连通） |
| `tactical` | 战术面（动作集 / 掩体 / 威胁） |
| `scenario` | 场景推进 |

+ 基础设施模块：`actions`（动作注册表执行器）/ `dialogue` /
`dynamics` / `narration`（叙事编排）/ `v1_migration`。

模块 = 组件 schema 声明 + Effect Producer + Authority 声明 +
（可选）执行器；项目侧经 `game.yaml modules:` 节声明启用
（`ModuleGraphNode`：requires / optional / conflicts / version）。
插件（`plugins/`）= 同 API 的外部包形态（`PluginDescriptor`：
local 目录或 `module:Attribute` entrypoint；registry 做发现 +
装载；`v2_plugin_local` 样例见 `tests/fixtures/`）。

### 3.2 LLM Runtime（P6，provider-neutral）

代码面 `src/engine_v2/llm/`：`structured.py`（结构化推理）/
`profiles.py`（InferenceProfile）/ `router.py`（capability →
profile 路由）/ `deployment.py`（deployment.yaml 装配）/
`adapter.py`（llm 模块适配器）/ `critic.py`（输出检查）/
`staleness.py`（revision 过期判定）。

纪律（K4/K5/K8）：LLM 输出 = **提议**（经 authority 裁决才
Commit）；prompt 不携带权限；项目只声明 capability 画像，
provider/model/base_url 全在 deployment.yaml；`llm_call` /
`prompt_assembly` trace 全程留痕。当前未接真实 provider
（P11+ 承接）；测试面用 FakeInferenceBackend（确定性脚本响应）。

### 3.3 WorldDynamics（P7）

`src/engine_v2/dynamics/`：`WorldDynamicsBackend` 协议 + 合法
实现族（rule / llm / composite，Spec §15）。世界动态变化
（环境演化、非角色过程）走这一层；与模块的 Effect Producer
分层（dynamics 产环境级 Effect，模块产实体级 Effect）。

### 3.4 表现层（P10）

`src/engine_v2/presentation/`：

| 面 | 说明 |
|---|---|
| `view.py` | ViewState 投影（WorldState → SceneView：actors / 主 location / narrative / 环境 / mood） |
| `text/narrator.py` | 叙事文本（template / llm 双源，`TEXT_SOURCES`；当前 template 确定性） |
| `image/backend.py` + `director.py` | RenderIntent（8 字段）+ 图像 backend 抽象；当前 = `DeterministicImageBackend`（PPM 哈希投影参考面） |
| `tactical/layout.py` | 战术视图布局 |

换真实图像 backend = 实现 backend 协议（输入 RenderIntent →
图像字节 + 槽元数据）+ 装配时注入 `SessionManager(
image_backend_factory=…)`；换真 LLM 叙事 = narrator 的 llm 源
接 P6 推理面。图像确定性（同 intent 同字节）是机械面钉值，
真实 backend 也需遵守「可复现或显式声明非确定」。

### 3.5 Web 适配器（P10）

`src/engine_v2/adapters/web/`：`server.py`（ThreadingHTTPServer
薄壳）/ `api.py`（9 路由闭集 + 信封）/ `session.py`
（SessionManager + 24 键快照）/ `views.py`（页面模板）/
`inspector.py`（12 节数据面）/ `workbench.py`（prompt 史数据面）。
inspector / workbench 的**数据面已建**（模块函数直调可消费），
HTTP 页面路由 = P11+ 落点（当前 404 保留面）。

## 4. 设计文档导航（按「我要做 X」找）

| 我要… | 读 |
|---|---|
| 理解整体架构 / 不变量 | `docs/plans/llmBasedSim_Engine_Architecture_v2_Spec.md`（§1–§3 定位、§4–§11 core、§12–§14 actor/context/prompt、§15–§17 dynamics/effect/authority、§18–§21 kernel、§22 dev 平面、§23–§25 scheduler/space/mode、§28–§30 模块/插件/持久化、§31–§33 LLM/prompt/devtools、§35–§37 适配器/inspector、§40–§41 官方模块、§44–§47 目录/MVP/开发顺序） |
| 理解某 Phase 的冻结设计 | `docs/v2/contracts/P<n>-*.md`（每个含 §9 勘误链 = 实现期全部裁决记录） |
| 看某 Phase 的收口证据 | `docs/v2/gates/G<n>-gate-report.md` |
| 查 v1 行为（迁移对照） | `docs/v2/reference/`（v1 reference transcripts 计划）+ `docs/game-flow-interfaces.md`（v1 接口规范） |
| 查任务级交付细节 | `docs/v2/reports/` |
| G10 验收（人工面） | `docs/v2/gates/G10-test-acceptance-plan.md` |

## 5. 当前边界速查（别踩空）

| 面 | 状态 |
|---|---|
| `adapters/cli/`（终端游戏） | 未建（P11；Spec §35） |
| `adapters/dsh/` | 未建（P11） |
| 真实 LLM provider 接线 | 未建（抽象 + deployment 面已备） |
| 真实图像 backend | 未建（抽象 + 确定性参考面已备） |
| inspector / workbench HTTP 页面路由 | 未建（数据面已备；404 保留） |
| 官方装配 API（项目 → 可玩会话，不经 tests-tree 助手） | P11+（当前装配 = 验收驱动同款宿主侧链，见 project-authoring §6） |
