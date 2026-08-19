# P0-T02 基线测试 / Lint 报告（Baseline Test/Lint Report）

- **任务 ID**：P0-T02（Phase 0 — 冻结 v1 & 基线；属性：测试 / 纯执行）
- **分支 / 提交**：`architecture-v2` @ `ad9847d`（2026-08-20 01:39:33 +0800）
- **工作区**：`/home/armourpiercer/projects/llmBasedSim`
- **执行时间**：2026-08-20 02:15–02:21 CST
- **纪律声明**：本任务为纯执行。未修改任何代码、测试、配置；未安装 / 升级任何依赖；未执行任何 git 写操作（仅只读 `git branch --show-current` 与 `git log -1`）。

---

## 1. 运行环境

| 项 | 值 |
|---|---|
| OS | Ubuntu 26.04 LTS（WSL2，kernel `6.6.87.2-microsoft-standard-WSL2`，x86_64） |
| Python 解释器 | `3.12.14`（`.venv/bin/python`，来自 `.venv/bin/python --version` 真实输出 `Python 3.12.14`） |
| 包管理 | 依赖由 `uv` 管理（`pyproject.toml` 依赖声明 + `uv.lock`）；`uv` 本身不在 PATH 中，本项目按要求仅使用 `.venv/bin/python` 执行 |
| 虚拟环境 | 仓库内 `.venv/`（Python 3.12.14，依赖已同步） |

## 2. 命令及真实输出

### 2.1 解释器版本

```
$ .venv/bin/python --version
Python 3.12.14
```

### 2.2 全量 pytest

命令：`.venv/bin/python -m pytest -q`

真实输出（完整，未截断）：

```
........................................................................ [ 19%]
........................................................................ [ 39%]
........................................................................ [ 58%]
........................................................................ [ 78%]
........................................................................ [ 97%]
........                                                                 [100%]
368 passed in 0.88s
```

退出码：**0**。pytest 配置见 `pyproject.toml`：`asyncio_mode = "auto"`，`testpaths = ["tests"]`。

### 2.3 ruff 版本与检查

```
$ .venv/bin/python -m ruff --version
ruff 0.15.18
```

命令：`.venv/bin/python -m ruff check src tests`

- 退出码：**1**（存在 lint 问题，如实记录）
- 汇总（真实输出末行）：`Found 30 errors.` / `[*] 10 fixable with the --fix option (1 hidden fix can be enabled with the --unsafe-fixes option).`
- 规则配置：`pyproject.toml` 仅有 `[tool.ruff]`（`line-length = 100`，`target-version = "py312"`），**无 `[tool.ruff.lint]` 自定义规则集**，因此命中规则来自 ruff 默认集（E4、E7、E9、F）。

## 3. 测试结果汇总

| 指标 | 值 |
|---|---|
| total（collected） | 368 |
| passed | 368 |
| failed | 0 |
| errors | 0 |
| skipped | 0 |
| 耗时 | 0.88 s |
| 退出码 | 0 |

## 4. 失败分类（测试）

**无任何测试失败**（0 failed / 0 errors / 0 skipped），因此无需进行 `known-v1-failure` / `environment-failure` / `real-regression` 分类。

## 5. Ruff 问题分类

共 **30** 个问题。全部位于**冻结的 v1 既有代码 / 测试**中（`src/`、`tests/`），当前分支上尚无任何 v2 新增代码，环境本身（解释器、依赖、OS）不产生任何 lint 问题，且这些问题与近期改动无关（均为 v1 遗留风格/死代码问题）。**全部 30 条分类为 `known-v1-failure`（v1 基线 lint 债务）**。逐条清单与判断依据如下。

### 5.1 按规则分类

| 规则 | 数量 | 含义 | 分布 |
|---|---|---|---|
| E701 | 11 | 一行内多条语句（冒号） | `src/game/attributes.py`（6）、`src/game/condition_eval.py`（5） |
| E402 | 7 | 模块级 import 不在文件顶部 | `src/main.py:20–26` |
| F401 | 7 | 导入后未使用 | `src/`（4）、`tests/`（3） |
| F541 | 3 | f-string 无占位符 | `src/game/rules.py:183`、`src/game/tick_eval.py:298`、`src/graph/game_graph.py:336` |
| F821 | 1 | 未定义名称 `fallback` | `src/graph/game_graph.py:475` |
| F841 | 1 | 局部变量赋值后未使用 | `src/main.py:33`（`debug_events`） |

### 5.2 逐条位置清单

| # | 位置 | 规则 | 说明 | 分类 |
|---|---|---|---|---|
| 1–6 | `src/game/attributes.py:258–263` | E701 | 比较运算符分支压缩为单行 | known-v1-failure |
| 7–11 | `src/game/condition_eval.py:138–142` | E701 | 比较运算符分支压缩为单行 | known-v1-failure |
| 12 | `src/game/rules.py:183` | F541 | 无占位符 f-string（中文文案） | known-v1-failure |
| 13 | `src/game/tick_eval.py:298` | F541 | 无占位符 f-string（异常消息） | known-v1-failure |
| 14 | `src/graph/game_graph.py:336` | F541 | 无占位符 f-string（状态文案） | known-v1-failure |
| 15 | `src/graph/game_graph.py:475` | F821 | `state.get("tick_duration_minutes", fallback)` 中 `fallback` 未定义，属 v1 潜在运行时缺陷（仅在 state 缺该键时触发，且该节点整体包在 `try/except Exception` 中，故未反映到 368 个通过的测试中） | known-v1-failure |
| 16–22 | `src/main.py:20–26` | E402 | `load_dotenv()` 必须在导入 src 模块前执行，import 后置为 v1 有意设计 | known-v1-failure |
| 23 | `src/main.py:33` | F841 | `debug_events` 赋值未使用（调试残留） | known-v1-failure |
| 24 | `src/models/events.py:6` | F401 | `WorldState` 未使用 | known-v1-failure |
| 25 | `src/prompts/loader.py:1` | F401 | `Path` 未使用 | known-v1-failure |
| 26 | `src/ui/cli.py:8` | F401 | `Panel` 未使用 | known-v1-failure |
| 27 | `src/ui/renderer.py:5` | F401 | `Text` 未使用 | known-v1-failure |
| 28 | `tests/test_init_extra.py:3` | F401 | `load_init_file` 未使用 | known-v1-failure |
| 29 | `tests/test_models.py:3` | F401 | `PlayerKnowledge` 未使用 | known-v1-failure |
| 30 | `tests/test_models.py:4` | F401 | `WorldState` 未使用 | known-v1-failure |

**判断依据说明**：
- 非 `environment-failure`：问题全部是代码文本本身被 ruff 规则命中，与 OS / 解释器 / 依赖版本无关；换环境重跑结果一致。
- 非 `real-regression`：`architecture-v2` 分支上尚未提交任何 v2 代码，命中文件全部属于 v1 冻结基线；无证据表明是 v2 工作引入。
- `known-v1-failure` 含义：v1 冻结时即已存在的基线 lint 债务。后续 Phase 若 ruff 问题数 / 规则构成发生变化，应以本报告（30 条）为比较基准。

## 6. 关键依赖版本

通过 `.venv/bin/python` + `importlib.metadata.version()` 从 `.venv` 实际读取：

| 包 | 版本 |
|---|---|
| langchain | 1.3.10 |
| langchain-openai | 1.3.2 |
| langgraph | 1.2.6 |
| pydantic | 2.13.4 |
| pytest | 9.1.1 |
| pytest-asyncio | 1.4.0 |
| rich | 15.0.0 |
| pyyaml | 6.0.3 |
| jinja2 | 3.1.6 |

## 7. 基线结论

1. **测试基线**：`368 passed / 0 failed / 0 skipped，0.88 s，退出码 0`。全部命令成功执行，结果可复现（命令见 §2，环境固定于 `.venv` Python 3.12.14）。
2. **Lint 基线**：`ruff 0.15.18` 对 `src tests` 检出 **30 个错误（退出码 1）**，规则构成为 E701×11、E402×7、F401×7、F541×3、F821×1、F841×1，全部归类为 `known-v1-failure`（§5）。`ruff check` 非 0 退出码是 v1 冻结基线的既有状态，不是本任务引入或可忽略的异常。
3. **作为 G0 测试基线的判定**：
   - G0 门禁中"**当前已有测试全部运行并记录**"与"**若 baseline 自身有失败，明确分类**"两项已由本任务满足：测试全部通过（无需失败分类），lint 问题已逐条分类且可解释（无"无法解释的失败"，不触发计划 §9 "若当前 baseline 存在无法解释的失败，停止后续 Phase" 条款）。
   - 因此**本基线可以作为 G0 的测试 / lint 基线**：后续任何 Phase 可用同一组命令（§2）复跑，并与本报告的 368 passed / 30 ruff errors（按规则与位置）直接比较回归。
   - G0 的其余门禁项（2 个 reference project 启动、`game_graph.py` characterization coverage、v2 目录可 import、架构文档入 repo）分别属于 P0-T03 / P0-T04 / P0-T05 / P0-T06，不在本任务范围内，需由 Leader 汇总判定 G0 整体是否放行。
4. **风险与后续关注点**：
   - `src/graph/game_graph.py:475` 的 F821（未定义名称 `fallback`）是 v1 真实潜在缺陷，P0-T03 为 `physics_resolve` 节点补 characterization test 时应覆盖 `state` 缺少 `tick_duration_minutes` 的路径，确认实际行为并固化到基线。
   - 后续 v2 迁移若改动 `src/main.py` 的 `load_dotenv` 顺序、`attributes.py` / `condition_eval.py` 的表达式解析风格，lint 基线数字将随之变化，属预期 diff，需与功能回归分开解释。

## 附：复现命令（基线重放）

```bash
cd /home/armourpiercer/projects/llmBasedSim
.venv/bin/python --version                                  # 期望：Python 3.12.14
.venv/bin/python -m pytest -q                               # 期望：368 passed in <~1 s>，退出码 0
.venv/bin/python -m ruff --version                          # 期望：ruff 0.15.18
.venv/bin/python -m ruff check src tests                    # 期望：Found 30 errors.，退出码 1
```
