# Gate Report: G0 (Phase 0 基线与隔离骨架)

- **Gate**: G0
- **Commit SHA**: `4a21a10b5787a29521f04cb5c6393d309f5e5066`
- **Date**: 2026-08-20 (Phase 0 Integration；Leader 勘误：原稿误写 2025-05-18)
- **Integration Agent**: P0-INTEGRATION

---

## 1. Tasks Summary

### Tasks Completed (6/6)
- **P0-T01 (Repo Inventory)**: `DONE`
  - 产出 `docs/v2/reports/P0-T01-repo-inventory.md`（含 Leader 核对附注）。全面梳理全部源码模块、调用拓扑、17 个测试文件（368 例基线，见 P0-T02）、config 与 15 个提示词模板。
- **P0-T02 (Baseline Report)**: `DONE`
  - 产出 `docs/v2/reports/P0-T02-baseline-report.md`。记录测试 baseline（374 passed）与 lint baseline（30 条 known-v1-failure 语法/导入/未用变量违规），明确归类为既有设计已知问题。
- **P0-T03 (Characterization Tests)**: `DONE`
  - 产出 `tests/char_helpers.py`、`tests/test_char_nodes.py`、`tests/test_char_graph.py` 与 `docs/v2/reports/P0-T03-characterization-report.md`。新增 77 例刻画测试（全部无网络/无外部 LLM 运行），深入刻画 11 节点行为，记录 8 项 known-bug-candidate（KBC-1 ~ KBC-8）与 fan-out 调度语义。
- **P0-T04 (Reference Transcripts & Fixtures)**: `IMPLEMENTED_UNVERIFIED`
  - 产出 `docs/v2/reference/` 目录、3 个标准输入序列（murder/whisperheads/test_empty）、`record_transcript.py`（含 CLI 与 `--selfcheck` 模式）。
  - **未验证原因**：本地环境 `.env` 中 `DEEPSEEK_API_KEY` 为占位符，缺少真实 API key 导致 live transcript 无法录制。已通过 `--selfcheck` 完成静态与状态构建验证（3 个 init 文件均可经 v1 加载路径成功构建初始 GameState）。
- **P0-T05 (Engine v2 Skeleton)**: `DONE`
  - 产出 `src/engine_v2/` 14 个子包骨架、`README.md` 与 `tests/test_engine_v2_skeleton.py`（6 例测试）。验证纯模块占位、无 v1 依赖、无外部重型依赖侵入，严格隔离。
- **P0-T06 (Architecture Docs 入库)**: `DONE`
  - 产出 `docs/architecture/README.md`、ADR-000 ~ ADR-006、`docs/architecture/migration-constraints.md` 与 `docs/plans/model-routing-providers.md`。核心架构决策与迁移约束全部持久化入库。

### Tasks Waived (0)
- 无任务放弃。

---

## 2. Tests & Linters Verification

### Tests
- **命令**: `.venv/bin/python -m pytest tests/ -q`
- **执行结果**: `451 passed in 3.03s`
  - 既有测试 baseline: 374 passed
  - P0-T03 刻画测试: 77 passed (60 node-level + 17 graph-level)
  - P0-T05 骨架测试: 6 passed (含 import 冒烟/Docstring 纪律/LangGraph-OpenAI 隔离/v1 零引用断言)
  - 合计通过数: 374 + 77 = 451 passed（骨架测试被集成在 pytest 统一发现范围内）

### Linters
- **Phase 0 新增/修改文件 lint**:
  - **命令**: `.venv/bin/python -m ruff check src/engine_v2 tests/char_helpers.py tests/test_char_graph.py tests/test_char_nodes.py tests/test_engine_v2_skeleton.py`
  - **结果**: `All checks passed!`（0 errors, 0 warnings）
- **全量仓库 lint**:
  - **命令**: `.venv/bin/python -m ruff check .`
  - **结果**: 30 errors（完全等于 T02 报告记录的 30 条 `known-v1-failure`，无新增回归）

---

## 3. Integration & Boundary Inspection

1. **Diff 与改动边界核对**:
   - `git diff --stat ad9847d..HEAD` 检查确认改动仅限于：`docs/architecture/`, `docs/plans/`, `docs/v2/`, `src/engine_v2/`, `tests/char_helpers.py`, `tests/test_char_*.py`, `tests/test_engine_v2_skeleton.py`。
   - `src/`（除 `engine_v2/`）、既有 `tests/`、`prompts/`、`config/`、`web/`、`public_start/` 实现了 **零改动**。
2. **Contract 漂移与骨架实现检查**:
   - `src/engine_v2` 及其 13 个子包 `__init__.py` 仅包含 module docstrings 与架构元数据，无任何 public contract 数据模型定义，无执行逻辑，无任何 v1 模块与 LangGraph/OpenAI 引用。符合 P0 不产生 v2 runtime/contract 代码的纪律。
3. **重复实现与临时 Hack 检查**:
   - 全库检索 `TODO|HACK|FIXME`，新增测试与代码中为 0 处。
   - 刻画测试通过 `char_helpers.py` 封装 FakeLLM 与 Graph Builder，未侵入或重复实现既有单元测试逻辑。
4. **术语与命名一致性检查**:
   - `engine_v2` 包名、8 项 `KBC-1` ~ `KBC-8` 编号、ADR-000 ~ ADR-006 编号、locked_attributes 5 种规则类型等术语在各报告与实现中完全一致。

---

## 4. G0 Gate Checklist (Plan §9)

| G0 门禁条款 | 检查依据与事实 | 状态 |
|---|---|---|
| 1. 当前已有测试全部运行并记录 | T02 报告记录 368 例 v1 基线（+T05 骨架 6 例 = 374）；本次全量回归 451 passed。 | **PASS** |
| 2. baseline 失败明确分类 | ruff 30 条错误全部为 v1 遗留已知缺陷（11 条 E701, 3 条 F541, 1 条 F821, 7 条 E402, 1 条 F841, 7 条 F401），已列入 `known-v1-failure`。 | **PASS** |
| 3. 旧 v1 能用至少 2 个 reference project 启动 | `docs/v2/reference/record_transcript.py --selfcheck` 成功验证 whisperheads/murder/test_empty 3 个 init 文件经 v1 路径构建 GameState；因无 API key，实跑暂挂。 | **CONDITIONAL (待 API key 实证)** |
| 4. `game_graph.py` 主要 I/O 行为有 characterization coverage | T03 完成 11 节点覆盖与图级 E2E，共 77 例测试，覆盖降级、重试、分支与 KBC 缺陷。 | **PASS** |
| 5. 新 v2 目录可以 import，但没有替换 v1 | `src/engine_v2` 14 个包可独立 import，完全不引用 v1，且未被 v1 引用。 | **PASS** |
| 6. Architecture 文档进入 repo | ADR-000~006、`migration-constraints.md`、`model-routing-providers.md` 及导航 README 均已合入。 | **PASS** |

---

## 5. Architecture Deviations
- **无**（Zero architectural deviations）。
- 未引入任何违反 ADR-000 ~ ADR-006 或 Spec 规范的结构。

---

## 6. Known Failures
- 既有 v1 代码中存在的 30 处 ruff 违规（保持未修复以维持 v1 行为冻结，归类为 `known-v1-failure`）。
- v1 中发现的 8 项已刻画 bug candidate（KBC-1 ~ KBC-8）：
  - KBC-1: `game_graph.py:475` F821 fallback 未定义导致 `physics_resolve` 恒降级；
  - KBC-2: `action_intents` reducer 重复累加导致 NPC 意图执行双份；
  - KBC-3: NPC 移动后陈旧坐标导致 prompt 坐标失真或缺 key 降级；
  - KBC-4: `advance_game_time` 丢弃 `day` 键；
  - KBC-5: 超长移动回退中 Position 对象无 `.get` 恒降级；
  - KBC-6: `compact_event_log` 仅追加摘要行，原日志未缩减；
  - KBC-7: `tick_speed_resolve` 对空行动改写为 `{}` 导致 None 判断失效；
  - KBC-8: 叙事模板强依赖 `s.confidence`。

---

## 7. Open Risks

1. **8 项 KBC 待人工 H1 裁决风险**：
   - 影响：在 Phase 1~3 开始前，需要人工确认哪些 bug 应在 v2 中修复（如 KBC-1/2/4/5），哪些行为应保留或演化。
   - 缓解：P1 仅定义底层核心数据契约（EntityId, Component, Revision, WorldState/RuntimeState），不涉及游戏动力学逻辑与图节点执行，不阻塞 P1。
2. **API Key 未就绪导致 v1 真实对局与 transcript 未能 live 运行**：
   - 影响：T04 目前处于 `IMPLEMENTED_UNVERIFIED` 状态。
   - 缓解：静态自检已确保 init 文件有效与状态解析通畅。P1 为纯内存数据结构与 schema 测试（完全无 LLM 依赖），具备推进前置条件。
3. **T03 LangGraph 版本敏感断言风险**：
   - 影响：T03 刻画测试包含对 LangGraph 内部节点调度与 reducer 行为的断言，若升级 LangGraph 版本可能出现波动。
   - 缓解：v2 架构核心 Kernel 已在 ADR-002 中解耦 LangGraph，后续 v2 测试不依赖 LangGraph 机制。

---

## 8. Human Review Required
- **是 (YES)**：
  - 本次为里程碑 M0 (G0) 门禁评审。
  - 需要架构负责人确认：
    1. G0 门禁达成与 Phase 1 准入；
    2. H1 人工行为基线与 KBC-1 ~ KBC-8 裁决（可在 P1 进行期间并行审阅）。

---

## 9. Decision

### **CONDITIONAL PASS**

### 准出与准入说明（Conditions）
1. **条件项 1 (T04 待实证)**: T04 transcript 录制待提供 `DEEPSEEK_API_KEY` 后补跑 live 对局。因 Phase 1 目标为定义 Core Data Contracts（纯 Pydantic/Python 数据模型、ID 机制、序列化与 Revision，纯单测、无网络、无 LLM），**完全不依赖 API key**，故此条件不阻塞 Phase 1 开展。
2. **条件项 2 (KBC 人工裁决)**: 8 项 KBC 记录为已知设计参考，供 Phase 2 (Kernel) 与 Phase 7 (Dynamics) 实现时参考，**不影响 Phase 1 数据层抽象**。

综上，Phase 0 所有代码与文档交付完整，无边界越界与 Contract 漂移，测试全部通过，批准进入 **Phase 1 (Core Data Contracts)**。

---

## 10. Human Review Record（M0，2026-08-20）

人工（架构负责人）已完成 M0 评审，裁定如下：

1. **G0 门禁**：批准 **CONDITIONAL PASS**，准入 Phase 1。条件项维持：
   - T04 transcript 实跑待 `DEEPSEEK_API_KEY`（人工确认当前尚无 key，继续挂起，不阻塞 P1）；
   - G0 第 3 条"v1 实跑启动"随之继续挂起。
2. **H1 行为基线 KBC 裁决**（采纳 Leader 建议）：
   - **KBC-1、KBC-2、KBC-3、KBC-4、KBC-5、KBC-7、KBC-8 判定为 known bug**：v2 无兼容义务，v2 修复这些行为不构成对 v1 的回归；characterization 测试按现状锁定 v1 行为仅作迁移参照。
   - **KBC-6（event_log 压缩名不副实）判定为设计取舍**：源于 append-only reducer 通道，v2 事件模型（DomainEvent + Trace）将天然重设计，不要求行为兼容。
   - fan-out 超步合并语义记录为 v1 兼容契约，v2 以事件驱动调度有意取代。
3. 上述裁决对 Phase 1（纯数据契约）无阻塞；供 Phase 2/7/9 实现与验收时引用。
