# P0-T05 报告：src/engine_v2 骨架（Skeleton）

- **任务 ID**: P0-T05（Phase 0 — 冻结 v1 & 基线；属性：开发 / 纯执行）
- **分支**: `architecture-v2`
- **工作区**: `/home/armourpiercer/projects/llmBasedSim`
- **环境**: Python 3.12.14（`.venv/bin/python`，未安装 / 升级任何依赖）
- **纪律声明**: 未执行任何 git 写操作（仅只读 `git status` / `git diff` 核对改动范围）；未修改 `src/` 下 engine_v2 以外的任何文件、tests/ 既有文件、prompts/、config/、web/；骨架未实现任何功能，未接入或引用 v1 旧 Runtime。

---

## 1. 交付物清单（共 15 个新文件）

| 路径 | 说明 |
|---|---|
| `src/engine_v2/__init__.py` | 根包：仅 docstring，声明冻结规则，引用 Spec §44/§46/§47 |
| `src/engine_v2/core/__init__.py` | Kernel 核心契约占位（Spec §4/§8/§9/§10/§11/§16–§21） |
| `src/engine_v2/runtime/__init__.py` | Engine 宿主占位（Spec §7/§23/§25/§45） |
| `src/engine_v2/persistence/__init__.py` | Snapshot/Checkpoint/Replay 占位（Spec §30/§9） |
| `src/engine_v2/plugins/__init__.py` | Plugin API/Registry/Manifest 占位（Spec §28/§29） |
| `src/engine_v2/context/__init__.py` | ContextProvider/Capability 占位（Spec §13） |
| `src/engine_v2/modules/__init__.py` | 标准游戏模块占位（Spec §40/§41） |
| `src/engine_v2/dynamics/__init__.py` | WorldDynamicsBackend 占位（Spec §15） |
| `src/engine_v2/llm/__init__.py` | Provider-neutral LLM Runtime 占位（Spec §5.5/§31） |
| `src/engine_v2/prompts/__init__.py` | Prompt 架构占位（Spec §14） |
| `src/engine_v2/content/__init__.py` | ProjectIR/内容加载占位（Spec §5/§6） |
| `src/engine_v2/devtools/__init__.py` | 开发控制平面占位（Spec §22/§33/§37） |
| `src/engine_v2/adapters/__init__.py` | cli/web/dsh 适配层占位（Spec §35） |
| `src/engine_v2/presentation/__init__.py` | text/image/tactical 表现层占位（Spec §8.5/§32） |
| `src/engine_v2/README.md` | 目录布局表、v2 冻结规则、后续 Phase 填充索引 |

另有 `tests/test_engine_v2_skeleton.py`（6 个测试，见 §3）。

## 2. 布局决策（对应 Spec §44 的裁剪说明）

1. **平级模块目录放入 `src/engine_v2/` 内部**（`modules/`、`dynamics/`、`llm/`、
   `prompts/`、`content/`、`devtools/`、`adapters/`、`presentation/`）。
   理由：Spec §44 把它们画在 `src/` 顶层，但 v1 已占用 `src/llm/`、`src/prompts/`、
   `src/agents/` 等顶层命名空间，直接建会冲突；任务包亦明确建议「首期」将其放入
   `engine_v2` 内部（最小化原则）。后续 Phase 如需顶层重命名，属破坏性结构调整，
   应走 Gate review。
2. **未建 `agents/`**：Spec §44 含 `src/agents/`（policies/critic/repair/narrator），
   但任务包 P0-T05 的最小化清单未列入；且 v1 已有冻结的 `src/agents/`（LangGraph
   实现）。v2 的 BehaviorPolicy 归属待 Phase 3/4 按 Spec §12 定名落位。
   以上两点已写入 `src/engine_v2/README.md`。

## 3. 测试（真实命令输出）

### 3.1 骨架测试（Required）

```
$ .venv/bin/python -m pytest tests/test_engine_v2_skeleton.py -q
......                                                                   [100%]
6 passed in 0.02s
```

覆盖：
- a. `import src.engine_v2` 及 13 个子包全部成功，且均为包（`test_engine_v2_and_subpackages_import`）；
- 骨架纪律：每个 `__init__.py` AST body 仅含模块 docstring（`test_engine_v2_init_files_are_docstring_only`，并校验子包数量 = 13）；
- b. 静态 AST 扫描全树无 `langgraph` / `langchain_openai` / `langchain_core` / `langchain` / `openai` 系 import（`test_engine_v2_static_scan_has_no_forbidden_imports`）；
- b. fresh import（先删 sys.modules 缓存再重导入）后，新增 sys.modules 中无禁止依赖（`test_engine_v2_import_pulls_in_no_forbidden_modules_sysmodules`）；
- c. `src/` 下除 engine_v2 外所有 .py 源码无 "engine_v2" 字符串引用（`test_v1_code_does_not_reference_engine_v2`）；
- README 存在且含「目录布局」「v2 冻结规则」章节（`test_engine_v2_readme_documents_freeze_rules`）。

### 3.2 全量测试（Required）

```
$ .venv/bin/python -m pytest tests/ -q
374 passed in 1.08s
```

374 = 既有 368（与 P0-T02 基线一致）+ 新增 6，0 失败，无 flaky。

### 3.3 Lint 卫生

```
$ .venv/bin/python -m ruff check src/engine_v2 tests/test_engine_v2_skeleton.py
All checks passed!   （退出码 0）
```

（基线 30 个 ruff 错误均在 v1 既有文件中，本次未新增任何 lint 问题。）

## 4. G0 门禁对应

- 「新 v2 目录可以 import，但没有替换 v1」：**满足**——
  14 个包全部可 import；v1 代码零引用 engine_v2；v1 入口未改动；全量 368 项 v1 测试保持通过。
- 本任务未触碰 G0 其余条目（基线、characterization、reference transcript、文档入库由 T02/T03/T04/T06 负责）。

## 5. 改动范围核验（只读 `git status --porcelain`）

```
M docs/v2/reports/P0-T01-repo-inventory.md   ← 非本任务改动（Leader 核对附注，本任务开始前已存在，未触碰）
?? src/engine_v2/
?? tests/test_engine_v2_skeleton.py
```

## 6. 风险与遗留

- 本报告文件 `docs/v2/reports/P0-T05-skeleton-report.md` 位于任务包「允许写入」
  清单（src/engine_v2/**、tests/test_engine_v2_skeleton.py）之外，系遵循 P0-T01/T02
  既有报告落位惯例（docs/v2/reports/）与任务环境「交付报告 + 工作区相对路径」要求；
  如 Leader 认为越界，可删除或移入 engine_v2/README.md，不影响任何代码与测试。
- `__pycache__/` 为 import 产生的标准副产物（v1 目录同样存在），未纳入 git 管理范围。
- 骨架 docstring 中对各 Phase 填充位置的引用来自 Spec §47；若后续 Phase 顺序调整，
  需同步更新 `src/engine_v2/README.md` 的填充索引。
