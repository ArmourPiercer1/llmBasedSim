# G5 Gate Report — Phase 5 Project Format / Module / Plugin / DSL（终版）

按 `docs/plans/llmBasedSim_Architecture_v2_Refactor_Development_Plan.md` §14、§21、§25 编制。
G5-R1 盲审 4/4 通过、0 补充、0 阻塞、0 执行失败（六条准则 4 名 reviewer 独立核验全部 met），
本报告为 G5 最终交付点记录。

---

## 0. 基础信息

- **Gate**: G5（Phase 5 — Project Format / Module / Plugin / DSL 门禁）
- **Commit SHA**: `c72b3ad`（HEAD，Phase 5 最终交付点）；文档提交 `0deb3ef`（ERR-P5-16，W6 闭合勘误）
- **分支**: `architecture-v2`
- **审查基准**: `e5c4db4`（G4 门禁闭合 PASS，pre-P5 冻结基线，套件 2399）.. `c72b3ad`（W6，G5-R1 审查点）；
  P5 设计文档（SOT）= W0 交付物 + 勘误链 ERR-P5-1..16（§9 L939-972，文档 997 行）
- **测试基线**: 全量 **2669 passed / 0 failed**（gate ① 真实输出，`.venv/bin/python -m pytest tests/ -x -q`，
  12.99s；P5 全程 +270 = 2669 − 2399，其中 W6 贡献 89（dev：test_validator 48 / test_cli 9 /
  gate 20 / adversarial 7 / integration 5）+ 5（Leader `TestP5Boundary` 方法））；
  gate ② `ruff check src/engine_v2/content src/engine_v2/plugins tests/engine_v2` → `All checks passed!`
- **审查执行**: 全部 `qiyuan-self / qwen3.8-27b`（2026-08-20 人工路由覆盖）；设计阶段 10 轮盲审
  （R1–R10 全闭合，S2 = flat 16-section typed IR 终审，ERR-P5-1；设计冻结）+ 波次审查
  （W1-R1 / W2-R1 / W3-R1..R3 / W5-R1..R3 / W4-R1..R4 / W6-R1，全闭合）+ 门禁阶段
  **1 轮 × 4 名独立盲审（G5-R1，全新一轮全新盲）**，四裁决协议（通过/投机通过/补充内容/阻塞）

---

## 1. §21 字段

```text
Gate: G5
Commit SHA: c72b3ad
Tasks completed: P5-T01 ~ P5-T10（全部）：
                 T01 = W0 设计期全仓 schema survey；
                 T02a/T02b = W1 schemas + W2 project_ir（ProjectIR 16 节 flat typed）；
                 T03 = W2 loader（LAYOUT 封闭 + load_project 6 步 + v1 形状检测）；
                 T04 = W3 module_graph（11 导出，never-raise 纯串版本比较）；
                 T05/T06 = W5 plugins manifest/registry（LOCAL_MANIFEST + entry-point
                 双路 metadata-only 发现，api Protocol 缝）；
                 T07 = W4 rule_module（43 导出，66 例 v1 parity 1:1 转录）；
                 T08 = W2 loader 测试 + W6 round-trip-safe（gate 断言 #20）；
                 T09 = W6 cli（llmsim validate [--json]，4 键封闭 envelope）；
                 T10 = W6 zero-Python reference project（fixture #30-34）；
                 + 锚点同步（test_import_boundary.py P5 块，Leader 执行，白名单 #29）
                 + G5 文档级闭合（ERR-P5-16：3 处开发前原位修正 + 3 处 R1 轮后 DOC 修正）
Tasks waived: 无
Tests: 2669 passed / 0 failed（真实输出，.venv python，-x -q）
Known failures: 0
Architecture deviations: 见 §6 偏差登记（D-P5-DEV-1..10 + W6 D-01..D-07，全部已披露/已登记）
Open risks: 见 §7 风险登记册（gate ⑥ 降级披露等，低）
Human review required: 否（HARD STOP S1-S5 未触发，逐条核验见 §8；门禁实质轮 0/3 在预算内，
                       按 2026-08-20 协议无需人工批准）
Decision: PASS
```

---

## 2. 门禁判据验证（Plan §14「G5」L607-614 六条，逐字 + 双重证据）

| # | 准则（Plan L607-614 逐字） | 实现面 | 测试面 | 实测证据（G5-R1 四 reviewer 独立复跑确认 met） |
|---|---|---|---|---|
| 1 | 零 Python 项目可以 load + validate | `loader.py` LAYOUT_REQUIRED/OPTIONAL 封闭 9 模板（目录缺席 = 合法空零诊断）+ `validate_project` 全链 never-raise | fixture #30-34 + gate 断言 #1/#2/#3/#16 + `test_loader` + `test_p5_integration::test_e2e_zero_python_clean_chain` | clean 项目：human rc 0 且 stdout = 恰 1 摘要行；`--json` ok=true / exit_code=0 / 4 键封闭；诊断集 = 空 |
| 2 | Python plugin 必须显式注册 | `registry.py` 双路发现（LOCAL_MANIFEST / entry-point）metadata-only + `validate_plugins` 诊断面 | fixture #35-37 + 断言 #4/#5/#8 + `test_manifest` / `test_registry` | 声明未注册插件 id（ghost_plugin）→ 恰 1 条 LLMSIM_PLUGIN_ENTRY_UNRESOLVED warning；pyproject 缺席 → LLMSIM_PLUGIN_NO_PYPROJECT |
| 3 | 不允许目录自动扫描执行任意 Python | P5 永不 import 插件代码（零动态模块加载）；发现面无目录扫描执行 | 断言 #6/#7 + A11 + `TestP5Boundary`（封闭模式 import_module/__import__/spec_from_file_location/module_from_spec/entry.load() = 0 命中）+ 12 名自扫描 | rogue .py（无 manifest）→ 零诊断、零注册、sys.modules 无该模块（A11 实测） |
| 4 | module dependency cycle 可诊断 | `find_cycles` SCC + `validate_project` LLMSIM_MODULE_CYCLE（每环一条，path=min(node)，refs=节点序） | A5 + 断言 #9/#10 + `test_module_graph` SCC 面 | 合成 3 环探针 → 恰 1 条 LLMSIM_MODULE_CYCLE，path/refs 形核验一致 |
| 5 | DSL 继续支持已有简单规则，但没有引入 loop/function-definition 等"重新发明 Python"的能力 | `parse_dsl` 23 种类 AST 封闭；def/while/lambda → LLMSIM_DSL_PARSE | A13 + 断言 #12 + `test_rule_dsl_parity` 66 例 1:1 + `test_rule_module` | 66 例全绿（seeded 精确值）；四排除形 66 例集 0 命中机械核验（§8.4 DEV 披露面） |
| 6 | validator 返回 machine-readable diagnostics | Diagnostic 18 码闭集 + 4 键 JSON envelope `{ok, project, diagnostics, exit_code}` + `sort_diagnostics` 稳定排序 | 断言 #13/#14/#17 + `test_cli` + `test_validator` 18 码矩阵 | `--json` stdout 可 json.loads、键集封闭、双跑字节相等；broken 项目全诊断形状核验（码 ∈ 18 ∧ severity 合法 ∧ path/message 非空） |

---

## 3. gate 运行序（SOT §3.12 L569 逐字命令，实测）

| 步 | 命令（SOT 逐字） | 结果 |
|---|---|---|
| ① | `.venv/bin/python -m pytest tests/ -x -q` | **2669 passed / 0 failed**（12.99s） |
| ② | `.venv/bin/python -m ruff check src/engine_v2/content src/engine_v2/plugins tests/engine_v2` | **All checks passed!**（line-length 100 口径；SOT 引注 pyproject:27 为基线行号，终态 L30，+3 偏移 = 白名单 #11 hunk，G5R1-1-01 备案） |
| ③ | `git diff --name-only e5c4db4..HEAD -- src tests pyproject.toml` | **恰好 39 文件** = §3.12 白名单封闭集（多一少一 = 门禁失败；实测 39，逐行对账一致：#1-7 content src、#8-10 plugins src、#11 pyproject、#12-24 content 测试包、#25-28 plugins 测试包、#29 边界文件、#30-39 fixtures） |
| ④ | `TestP5Boundary` 全组 | **5/5 PASSED**（file_set / 12_name_blacklist（split-string 豁免有效，29 文件 0 命中）/ forbidden_roots / ast_nondeterminism / no_v1_imports） |
| ⑤ | `TestB1StaticScan` / `TestB3OfflineRunnable` / `TestP4Boundary` / skeleton 全组 | **12/12 PASSED**（零修改锚点回归；T06 含 P5 受控豁免后绿） |
| ⑥ | `llmsim validate` 三态冒烟（clean=0 / broken=1 / usage=2） | **0 / 1 / 2 全验证**——降级面执行（见下披露） |

**⑥ 降级披露（SOT §6.5 预批条款）**：本环境 venv 无 pip（`.venv/bin/python -m pip` →
`No module named pip`），`llmsim` console script 未装配 → 按 SOT §6.5 降级条款以
`python -m src.engine_v2.content.cli` 面执行。该面 = 同一 `__main__` 守卫 → `main()` 路径
（console script 与 -m 面共享全部行为）；实测：clean human = 仅 1 摘要行 rc 0；clean
`--json` = 4 键封闭 envelope（json.loads 通过、sort_keys/indent=2/ensure_ascii=False/尾部换行）
rc 0；broken = 4× LLMSIM_DEPLOYMENT_FIELD（K8 探针 P1-P3 + openai 词）+ DUPLICATE_ID +
UNRESOLVED_REF（error）与 1× PLUGIN_ENTRY_UNRESOLVED（warning），排序后序 + 摘要行，rc 1；
无参 / 未知子命令 = rc 2 且 stderr 单行 `llmsim: usage error:` 前缀；零其他 stdout。
G5-R1（G5R1-4-1）独立复核：降级不构成 Decision=PASS 的障碍。

---

## 4. 任务完成情况（Tasks completed）

| 任务 | 波次 | 交付文件（白名单行） | 状态 |
|---|---|---|---|
| P5-T01 | W0（设计期） | SOT 文档（docs 面，非代码白名单） | 完成（设计冻结，ERR-P5-1 S2 终审） |
| P5-T02a | W1 | `content/schemas.py` + `test_schemas.py`（#1/#9） | 完成 |
| P5-T02b | W2 | `content/project_ir.py` + `tests/engine_v2/content/{__init__,conftest}.py` + `test_project_ir.py`（#2/#12/#13/#15） | 完成 |
| P5-T03 | W2 | `content/loader.py` + `test_loader.py`（#3/#16） | 完成 |
| P5-T04 | W3 | `content/module_graph.py` + `test_module_graph.py`（#4/#17） | 完成 |
| P5-T05/T06 | W5 | `plugins/{manifest,api,registry}.py` + `tests/engine_v2/plugins/{__init__,conftest,test_manifest,test_registry}.py`（#8-10/#25-28） | 完成 |
| P5-T07 | W4 | `content/rule_module.py` + `test_rule_dsl_parity.py` + `test_rule_module.py`（#5/#19/#20） | 完成 |
| P5-T08 | W2/W6 | loader 测试面 + round-trip-safe（gate 断言 #20，`test_p5_integration`） | 完成 |
| P5-T09 | W6 | `content/cli.py` + `test_cli.py` + pyproject `[project.scripts]`（#6/#22/#11） | 完成 |
| P5-T10 | W6 | fixture #30-39（zero_python 5 文件 + plugin_local 3 文件 + broken 2 文件）+ `test_validator.py` / `test_p5_gate_scenario.py` / `test_p5_adversarial.py` / `test_p5_integration.py`（#21-24/#30-39）+ 边界文件 P5 块（#29） | 完成 |

Tasks waived: 无。

---

## 5. 审查历史（对抗式独立盲审，全部 qiyuan-self / qwen3.8-27b）

| 阶段 | 轮次 | 结果 | 处置 |
|---|---|---|---|
| 设计 | R1–R10（10 轮） | 全闭合；S2 = flat 16-section typed IR 终审 | ERR-P5-1；设计冻结 |
| W1 | R1 | 4/4 闭合 | — |
| W2 | R1 | 4/4 通过，6 DOC | 5 文档修正 + 1 代码侧测试修正 → ERR-P5-13（Fixer M） |
| W3 | R1–R3 | 闭合 | 10 处文档原位修正 → ERR-P5-14 |
| W5 | R1–R3 | 闭合（4 SUPP 同根） | 4 处同根修正 → ERR-P5-14 |
| W4 | R1–R4 | R4 终审 4/4 通过 0 SUPP | R1 实质 1/3（eager And/Or 修正）；R2 Fixer S；R3 零代码裁定（L390 path_label 契约钉死）；R4 轮后 2 DOC 免费修正 → ERR-P5-15 |
| W6 | R1 | **4/4 通过，0 SUPP，0 BLOCK**，3 DOC + 5 INFO | 3 DOC 轮后免费修正（cli.py L454 引注 / SOT L450 括注澄清 / 白名单 #29 措辞）→ ERR-P5-16；实质轮 0/3 |
| G5 | R1 | **4/4 通过，0 SUPP，0 BLOCK，0 DOC，6 INFO**；六条准则 4/4 reviewer 全部 met=true；①-⑥ 全步独立复跑对账一致 | 无修复需要；6 INFO 全部备案（本文件 §3/§7） |

实质补充轮预算（每阶段 3 轮上限，文档级修复免费——2026-08-20 协议）：W4 1/3、W6 0/3、
G5 0/3，全部在预算内。

---

## 6. 偏差登记（Architecture deviations，全部已披露）

**设计期（SOT §8.4，10 项，66 例集 0 命中机械核验，无门禁影响）**：D-P5-DEV-1..10
（v1/v2 行为面差异：uncertain 概率字面面 / 单分支 trailing 面 / 裸 player/target 面 /
空串 match 面等，逐条见 SOT §8.4 表）。

**W6 开发期（dev 报告 + ERR-P5-16(e)，7 项，全部规格沉默最保守读法或 SOT 测试列字面落点，G5-R1 逐条复核）**：

| 偏差 | 位置 | 裁定 |
|---|---|---|
| D-01 | fixture #30-34 镜像省略 v1 无 v2 对应键（world.objects / narrative_style 压平 / characters 单角色替代） | A9 预裁定口径，无其他选项空间 |
| D-02 | cli `--help` → stdout 帮助 + rc 0 | SOT 沉默，argparse 标准面（最保守） |
| D-03 | usage 错 stderr 文本 = `llmsim: usage error: {message}` 单行前缀 | SOT 沉默，机器可解析前缀（最保守） |
| D-04 | 116 导出唯一性断言内置 test_assert_17 函数体 | A7 恰 20 函数约束优先，门禁强度不削弱 |
| D-05 | T06 全树 subprocess 黑名单 vs §6.5 字面 subprocess 冒烟 | **Leader 裁定**：SOT 优先；T06 范围豁免最小化（单文件、仅 网络/进程 IO 类别、provider/v1 零容忍保持）；§3.11 纯追加纪律受控偏离已记入代码注释 + 白名单 #29 行 + ERR-P5-16 |
| D-06 | §6.3 A7 用例落点 = test_validator（build_ir 步 2 面） | SOT 测试列字面落点 |
| D-07 | gate ⑥ = -m 降级面 | SOT §6.5 预批降级条款（本环境无 pip），披露于本文件 §3 |

**Leader 裁定（G5 阶段累计）**：测试侧 `importlib.import_module` 许可（test_assert_17 以
固定 10 路径元组枚举 `__all__`——SOT 机械面仅覆盖 10 src 模块，测试侧各扫描面均不禁止
importlib，零动态加载风险；G5-R1 复核确认）。

---

## 7. 风险登记册（Open risks — G5-R1 已核实，供后续 bug 排查参考）

1. **console script 未装配**（venv 无 pip）：gate ⑥ 经 -m 降级面执行（SOT 预批条款，G5-R1
   核实不阻碍 PASS）。残留：有 pip 环境 `pip install -e .` 后 `llmsim` 入口点可另行冒烟
   （P6+ 或人工），行为面与 -m 面同一 `main()` 路径。
2. **P5 registry/api = Protocol 缝**：插件执行面归 P6+（P5 永不 import 插件代码——K8/D-P5-13
   口径）；P6 消费 `EntryPointSpec` / `InferenceCapabilityProfile`（K8 字段封闭集）/
   `PromptPolicy`（K4 无 authority 字段）。
3. **SOT 基线行号惯例**：锚点引注（如 gate ② pyproject:27）指 pre-#11 hunk 基线，终态 +3 偏移
   （G5R1-1-01 备案；沿 §3.11 锚点台账同一惯例）。
4. **措辞同形异文（INFO）**：SOT L417 与 D-P5-DEV-3 对同一 DSL 排除形措辞不一致（「未达分支含
   垃圾」vs「matched 分支后尾随垃圾」）——语义同一、66 例集 0 命中机械核验（G5R1-2-1）。
5. **human 面重复行（INFO）**：broken 项目 4 条 LLMSIM_DEPLOYMENT_FIELD human 渲染逐字相同
   （探针名仅存 refs，--json 面完整）——每 (文件,名) 去重设计的确定产物（G5R1-3-1）。

---

## 8. HARD STOP 核验（Plan §24，逐条）

| 场景 | P5 交付面 | 结论 |
|---|---|---|
| S1 Kernel invariant 变更 | 无——K1-K8 全部保持（G5-R1 逐条核验）；core 32 模块 / 308 导出名零变更（D-P5-01） | 未触发 |
| S2 Public Contract 二义自选 | 无——ProjectIR 形态 = S2 设计冻结裁决（ERR-P5-1，10 轮设计盲审闭合）；W6 各 A 裁定 = Leader 预裁定先行 | 未触发 |
| S3 destructive migration | 无——v1 内容零改动（只读镜像参照 public_start/test_empty.yaml） | 未触发 |
| S4 新重大依赖 | 无——pyproject 仅 +`[project.scripts]` 3 行，依赖列表零变更；P5 导入面 = pydantic/pyyaml/re/argparse/sys 既有依赖 | 未触发 |
| S5 Backend 违约 | 无——P5 无 backend 面（K7 JSON-clean 由 assert_json_clean 机械核验） | 未触发 |

---

## 9. 移交 P6 的接口与约束（Handoff Notes）

- **P5 冻结面**：10 模块 116 导出（25+6+6+11+43+8+4+3+3+7，§8.2 台账逐名逐序）；18 诊断码闭集；
  ProjectIR 16 节 flat typed（S2 冻结）；canonical_yaml round-trip（断言 #20）；
  `llmsim validate [--json]` CLI（4 键封闭 envelope，stdout 纪律 D-P5-12）；
  插件 registry（LOCAL_MANIFEST + entry-point 双路，metadata-only）；
  DSL 23 种类封闭 + 66 parity 例（v1 行为基线，seeded 精确值）。
- **P6 消费点**：`InferenceCapabilityProfile`（K8：字段集内省无 provider/model/endpoint/credential
  形态）；`PromptPolicy`（K4：字段封闭集无 authority/permission）；`plugins.api`
  EntryPointSpec Protocol 缝（执行归 P6）；`ProjectIR`（只读消费）。
- **约束**：K1-K8 不变量；core 32/308 冻结（P5 不入 core 先例延续）；K8 12 名纪律
  （P5 .py 0 命中，测试探针串拼接构造）；66 parity 例 = v1 行为等价基线（P6+ DSL 扩展不得破坏）。

---

## 10. 决策

**Decision: PASS**

- 六条 G5 准则 6/6 met（4 名独立盲审 reviewer 各自完整核验 + 独立复跑 ①-⑥ 全步对账一致）；
- gate 运行序 ①-⑥ 全绿（⑥ 降级条款披露，SOT 预批，G5-R1 核实不阻碍 PASS）；
- 白名单 diff = 39（封闭集，多一少一 = 门禁失败，实测恰好 39）；
- G5-R1：4/4 通过、0 补充、0 阻塞、0 执行失败；G5 实质轮 0/3；
- HARD STOP S1-S5 未触发（§8 逐条核验）；
- 未使用 CONDITIONAL PASS（Plan §21 默认禁止）。

**下一阶段**：P6（LLM Runtime / Prompt / Capability Routing，Plan §15）；HARD STOP 清单
（Plan §24 S1-S5）持续适用。
