# P0-T03 Characterization 测试报告 — game_graph.py 11 节点流程行为基线

- **任务 ID**: P0-T03
- **Phase**: Phase 0（冻结 v1 & 基线）
- **分支**: `architecture-v2`
- **日期**: 2026-08-20
- **环境**: Python 3.12.14（`.venv/bin/python`），Ubuntu 26.04（WSL2）
- **纪律声明**: 未修改任何 `src/`、`prompts/`、`config/`、`web/`、`public_start/` 及既有测试文件；仅新增 `tests/` 下 3 个文件与本报告；未执行任何 git 写操作；未安装依赖。所有测试无网络、无 API key、无真实 LLM。

---

## 1. 交付物概览

| 文件 | 性质 | 用例数 | 内容 |
|---|---|---|---|
| `tests/char_helpers.py` | 新增（共享工具） | — | FakeLLM、canned JSON 构造器、状态工厂、节点提取器 |
| `tests/test_char_nodes.py` | 新增（节点级） | **60** | 11 个节点的隔离 characterization：I/O 契约、确定性行为、降级、F821 |
| `tests/test_char_graph.py` | 新增（图级） | **17** | 全图端到端、Fan-out 合并、reducer 累加/压缩、长行动延续、多回合 |
| `docs/v2/reports/P0-T03-characterization-report.md` | 新增（本报告） | — | 覆盖矩阵、Fake LLM 设计、known-bug-candidate 清单 |

新增用例合计 **77**，全部通过；既有 368 个 v1 用例保持全部通过（见 §6 复现命令）。

> **基线说明**：P0-T02 报告的基线为 368 passed。执行本任务时工作区已含并行任务 P0-T05 合入的
> `tests/test_engine_v2_skeleton.py`（6 个用例，针对 `src/engine_v2/` 骨架），故"既有用例"实测为
> 368 + 6 = 374。两套口径均已在 §6 给出真实命令输出。

---

## 2. Fake LLM 设计说明

设计目标：在**不 monkeypatch `generate_structured`** 的前提下驱动图执行，使
`src/llm/parser.py::generate_structured` 的 JSON 提取、Pydantic 校验、解析失败重试
（`max_retries=2`，共 3 次尝试）逻辑全部被真实执行。

- **调用约定**：`FakeLLM.ainvoke(messages) -> AIMessage(content=<JSON 字符串>)`，与
  `ChatOpenAI` 的异步接口一致；`generate_structured` 只依赖 `response.content`。
- **路由机制**：按 `messages[0]`（SystemMessage）内容匹配。每个图节点使用不同 system
  模板，渲染结果含唯一开头句（如 `你是玩家输入处理器`、`你是一个确定性物理模拟引擎`）；
  `character_system.j2` 还含 `- 名字：{{ name }}`，可按 NPC 名字精确路由。标记常量见
  `char_helpers.py`（`M_INTENT`/`M_RESOLVE`/`M_CHAR`/`M_PHYSICS`/`M_ATTR`/`M_SENSORY`/`M_NARRATIVE`）。
  dict 保序，按插入顺序取第一个命中。
- **响应队列**：每条路由是一个列表，按调用次序消费，耗尽后**重复最后一个响应**（sticky），
  支持"前 N 次垃圾后恢复""永远失败"等场景。响应可以是：JSON 字符串、Exception 实例/类
  （模拟 API 失败）、或 `callable(messages, call_index)`。
- **垃圾响应**：常量 `GARBAGE`（无花括号的中文文本）使 `_extract_json` 回退原文、
  Pydantic 校验失败，用于刻画重试与耗尽路径。
- **观测**：`calls`/`call_count(marker)`/`user_prompt_of(marker, i)` 支持调用账目与
  prompt 内容断言（如视野半径过滤、前回合叙事注入）。
- **真实 PromptLoader**：测试用 `PromptLoader("prompts")` 渲染真实 Jinja2 模板——模板
  渲染失败本身也是 v1 节点降级行为的一部分（见 KBC-3/KBC-8），属于被刻画行为。
- **节点提取**：隔离测试通过 `graph.nodes[name].bound.func/.afunc` 提取编译图内的节点
  原始闭包，不需要也不允许修改 `src/`（F821 路径即依赖该手段）。

---

## 3. 覆盖矩阵（节点 × 场景）

图例：✅ = 已覆盖（括号内为代表性测试）；➖ = 不适用；❌ = 未覆盖（原因见 §5）。

### 3.1 LLM 节点

| 节点 | E2E happy | I/O 契约 | 降级（LLM 抛异常） | 降级（垃圾 JSON/重试） | 特殊行为 |
|---|---|---|---|---|---|
| player_intent_process | ✅ `e2e_full_flow` | ✅ 无输入返回无 event_log 键 | ✅ 节点级+E2E | ✅ 垃圾×3 耗尽降级；垃圾×2+合法恢复（节点级与 E2E） | ✅ /c、/stop、新输入打断、raw_input 覆写 |
| player_action_resolve | ✅ | ✅ 无行动返回 `{}` | ✅ 节点级+E2E（保留原始行动） | ❌（重试语义已在 intent 节点刻画，见 §5） | ✅ 字段保留、规则回填、多步强制 allowed、超长移动回退**恒崩**（KBC-5） |
| characters_all_decide | ✅ | ✅ 无角色返回空列表 | ✅ 单 NPC 失败不影响他人（节点级+E2E） | ❌（同上） | ✅ character_id 强制覆写；邻近 NPC 缺 position 键整体降级（KBC-3） |
| physics_resolve | ✅（恒降级，见 KBC-1） | ✅ | ➖（F821 使 LLM 路径不可达） | ➖ | ✅ F821 有/无 tick_duration_minutes 两种 state 均恒降级、LLM 零调用 |
| attribute_update | ✅ | ✅ 无属性跳过且不调 LLM（节点级+E2E） | ✅ 节点级+E2E | ❌（同上） | ✅ delta/new_value 两种变更、未知 key [警告] |
| sensory_filter | ✅ | ✅ 成功路径不写 event_log | ✅ 节点级+E2E（默认感知） | ❌（同上） | ✅ self_action_summary 组装（blocked/speech/内心）、视野半径过滤、hidden 属性过滤 |
| narrative_stylize | ✅ | ✅ 空 percept 返回 `{}` 且不调 LLM | ✅ 节点级+E2E（summary 回填+历史） | ❌（同上） | ✅ 历史条目结构、前回合叙事注入 prompt（多回合测试） |

### 3.2 确定性节点（无 LLM）

| 节点 | E2E happy | I/O 契约 | 精确行为刻画 |
|---|---|---|---|
| tick_speed_resolve | ✅（E2E + world_rules 表达式 E2E） | ✅ 5 字段输出契约 | ✅ fallback=1/max(tpgm,0.01)、min(npc)、player_duration、min/max clamp、if 表达式、表达式错误→default、玩家截断+continuation、无 continue_until 不产生 continuation、speak/wait/observe 豁免、NPC 截断 |
| state_apply | ✅ | ✅ 9 字段输出契约 | ✅ 物理结果（movement/state_change/destruction）、玩家 move/blocked/uncertain 掷骰双分支（monkeypatch random）、NPC speak/move、memory 追加与上限 50、compaction 摘要追加、tick+1、player_input 清空、game_time 推进与 **day 丢弃**（KBC-4）、tick_dur 缺失回退 |
| natural_attribute_delta | ✅（fanout 测试） | ✅ 6 字段输出契约 | ✅ 按 tick 时长缩放、locked 跳过、post_narrative 延迟、attribute_deltas diff（含 hidden）、locked_attributes 规则 pre/post 拆分 |
| post_narrative_update | ✅（fanout 测试） | ✅ 无 deferred 返回 `{}` | ✅ 延迟自然增减（player/character）、延迟 locked 规则、事件标签 `[属性](叙事后)`、deferred 清空 |

### 3.3 跨节点/图级场景

| 场景 | 覆盖 | 代表测试 |
|---|---|---|
| a. 全图端到端（输入→11 节点→percept/narrative，关键 state 字段） | ✅ | `test_e2e_full_flow_characterization`（含逐条 event_log、LLM 调用账目、memory、好感度、坐标） |
| d. Fan-out 双分支都执行且结果合并 | ✅ | `test_e2e_fanout_both_branches_merge_deterministically`（重复 3 次验证确定性） |
| h. event_log reducer 累加（初始保留+节点顺序） | ✅ | `test_e2e_full_flow...`（精确全列表） |
| h. event_log 压缩（>100 追加摘要行，原文保留） | ✅ | 节点级 + `test_e2e_event_log_compaction_appends_summary` |
| action_intents reducer **重复累加**（KBC-2） | ✅ | `test_e2e_action_intents_reducer_duplication_single_npc` + full_flow |
| narrative_history reducer 累加（单回合+跨回合） | ✅ | full_flow + `test_e2e_multi_turn_...` |
| g. action_continuation 延续（/c + tick 截断剩余时长） | ✅ | `test_e2e_c_command_continues_and_tick_truncates_with_remainder` |
| g. action_continuation 终止（/stop）与打断（新输入） | ✅ | `test_e2e_stop_command_clears_continuation`、`test_e2e_new_input_interrupts_continuation` |
| 多回合（main.py 模式：每回合新 thread_id + reset_tick_transients） | ✅ | `test_e2e_multi_turn_narrative_history_and_event_log_continuity` |
| 图拓扑（恰好 11 个具名节点） | ✅ | `test_graph_contains_exactly_11_nodes` |

---

## 4. Known-bug-candidate 清单（记录现状，未修复；由 H1 决定是否作为兼容契约）

| # | 位置 | 现象（实测） | 影响 | 刻画测试 |
|---|---|---|---|---|
| **KBC-1** | `game_graph.py:475`（F821） | `state.get("tick_duration_minutes", fallback)` 中 `fallback` 未定义；Python **先求值默认参数**，故无论该键是否存在都抛 NameError，被节点 try/except 吞掉 | **physics_resolve 恒降级**：`physics_outcomes` 永远为 `[]`，物理 LLM 从不被调用（所有 E2E 均复现；call_count==0 断言） | `test_physics_f821_degrades_*`（2 个）+ 全部 E2E |
| **KBC-2** | `tick_speed_resolve` → reducer | `action_intents` 是 `operator.add` 通道，tick_speed_resolve 把截断后的**完整列表**再次写入 → 原始与截断副本并存（每 intent ×2） | state_apply 对每个 NPC 行动执行两次：移动日志重复、好感度 delta 翻倍（实测 0.10 而非 0.05）；pickup 有幂等防护但交互类副作用可叠加 | `test_e2e_action_intents_reducer_duplication_single_npc`、`test_e2e_full_flow...` |
| **KBC-3** | `_find_nearby_chars` + `character_user.j2`/`sensory_user.j2` | 模板直接访问 `char.position.x`，而 `_find_nearby_chars` 返回的是 character dict：NPC 移动后只更新 `character_positions`，dict 内 position **永不更新**（陈旧坐标进入 NPC/感官 prompt）；若 dict 根本没有 position 键，邻近（≤20m）NPC 的模板渲染崩溃 → 决策/感知降级 | NPC 认知与玩家感知中的坐标陈旧；非剧本构造的 state 下 NPC 决策整体失效 | `test_chars_missing_position_key_degrades`、full_flow 中陈旧坐标断言 |
| **KBC-4** | `advance_game_time`（game_state.py:110） | 只返回 `{hour, minute}`；state_apply 用其覆盖 game_time → **day 键在首个回合即丢失**，跨日不进位（实测 `{day:1,hour:8}` → `{hour:8,minute:1}`；23:59+2min → `{hour:0,minute:1}`） | 剧本 `game_time.day` 信息丢失，长周期剧本日期失真 | `test_state_apply_tick_fields_and_game_time_day_drop`、full_flow |
| **KBC-5** | `game_graph.py:257-275` | 超长移动确定性回退中 `resolved.target_position` 是 Pydantic `Position`，无 `.get` → AttributeError → 节点整体降级 | 所有"move + 无时长 + 目标>30 单位"的行动都走降级路径（保留原行动+错误事件），"超长移动"估算与 `continue_until=blocked` **从不可达** | `test_resolve_long_move_fallback_is_broken_degrades` |
| **KBC-6** | `state_apply` + `compact_event_log` | event_log 是 append-only reducer 通道，压缩只能**追加**摘要行（`[摘要] 前 N 条事件：...`），原事件无法移除 | event_log 只增不减，压缩名不副实 | `test_state_apply_compaction_appends_summary_line`、`test_e2e_event_log_compaction_appends_summary` |
| **KBC-7** | `tick_speed_resolve` 对空行动的改写 | intent 失败或 /stop 后 `player_action=None`，但 tick_speed 以 `state.get("player_action") or {}` 重写 → **最终 state 中 player_action 为 `{}` 而非 None** | 下游/WebUI 若以 `is None` 判断"无行动"会误判 | `test_e2e_intent_failure_degrades_and_flow_continues`、`test_e2e_stop_command_clears_continuation` |
| **KBC-8** | `narrative_user.j2` 等模板 | 无防护访问 `s.confidence`（sensory 产出的 senses 经 model_dump 恒含该字段，真实管线不触发，但隔离构造的缺字段 percept 会令叙事降级） | 模板脆弱点；v2 提示词重构需注意 | `test_narrative_success_enriches_percept_and_appends_history`（注释） |

### Fan-out 合并语义（非 bug，但 v2 必须知道的兼容契约）

实测（含对 attribute_update 注入 0/50ms 延迟、各重复 3 次，结果一致）：LangGraph 超步
（superstep）语义下，`attribute_update` 与 `sensory_filter` 同超步并发，分支 B 的后续节点
（`narrative_stylize`/`post_narrative_update`）在更晚超步执行、**读取状态已包含分支 A 的写入**；
最终 `player`/`characters` 通道值来自 `post_narrative_update` 的写入（其读取时已含 LLM 属性
变更）→ **两分支的属性变更都保留**，行为确定。事件提交顺序固定：pre 自然增减 → 分支 A 属性
事件 → 分支 B（叙事后）事件。

---

## 5. 未覆盖项及原因

| 未覆盖项 | 原因 |
|---|---|
| 真实 LLM / 真实网络调用 | 任务要求无网络、无 API key；FakeLLM 即为替代（设计使然） |
| 除 intent 外各 LLM 节点的"垃圾 JSON 重试"细分 | 重试/耗尽语义属于 `generate_structured`（parser 层），已在 intent 节点完整刻画（3 次耗尽降级、2 次失败后恢复），且 `tests/test_parser.py` 既有 13 例覆盖 parser 本身；其余节点以"抛异常→降级"覆盖其失败分支，避免重复堆砌 |
| physics_resolve 的"正常 LLM 路径" | 因 KBC-1 该路径在 v1 中不可达，无法在不修改 src/ 的前提下刻画（canned 物理 JSON 因此不会被消费） |
| checkpointer 同 thread_id 跨 ainvoke 累积 | v1 真实运行路径（main.py / web/app.py）每回合使用**新 thread_id**，该场景不属于 v1 行为；多回合测试按 main.py 模式刻画 |
| StatusReporter（TurnStatus/WebTurnStatus）文案序列 | UI 层行为，不属于图状态契约；测试以 `status=None` 构建 |
| use_item/consumable、uncertain 无 roll（待定）等 state_apply 细分支 | 既有 `tests/test_state_apply.py`（17 例）已单元覆盖；新套件聚焦图节点契约，仅抽样保留掷骰双分支 |
| tick 表达式随机/集合语法全集 | 既有 `tests/test_tick_eval.py`（51 例）已覆盖；新套件刻画图内表达式接入（if 包裹、错误→default） |
| N>2 NPC 的并发调度顺序 | `asyncio.gather` 调度依赖真实异步等待，FakeLLM 同步响应下无额外信息量；2 NPC 已覆盖"部分失败隔离" |
| WebUI/CLI 入口集成 | 超出 P0-T03 范围（属 T01 报告 §5.1 所列独立缺口） |

---

## 6. 复现命令与真实输出

```bash
cd /home/armourpiercer/projects/llmBasedSim
.venv/bin/python --version                        # Python 3.12.14
```

### 6.1 全量测试（既有用例 + 新增用例）

```
$ .venv/bin/python -m pytest tests/ -q
........................................................................ [ 95%]
...................                                                      [100%]
451 passed in 2.79s
```

451 = 368（v1 既有，T02 基线）+ 6（P0-T05 骨架）+ **77（本任务新增）**。

### 6.2 既有用例不回归验证（排除新增文件）

```
$ .venv/bin/python -m pytest tests/ -q --ignore=tests/test_char_graph.py --ignore=tests/test_char_nodes.py
374 passed in 0.85s
```

（374 = 368 v1 + 6 P0-T05；与执行本任务前工作区状态一致，零回归。）

### 6.3 新增 characterization 用例单独运行

```
$ .venv/bin/python -m pytest tests/test_char_graph.py tests/test_char_nodes.py -q
77 passed in 2.54s        # 重复运行 3 次结果一致（含 -p no:randomly 一次），确定性成立
```

用例数：`tests/test_char_graph.py` **17**，`tests/test_char_nodes.py` **60**（`--collect-only` 核实）。

### 6.4 新增文件 lint

```
$ .venv/bin/python -m ruff check tests/char_helpers.py tests/test_char_graph.py tests/test_char_nodes.py
All checks passed!        # 退出码 0；不改变 P0-T02 的 30 条 v1 lint 基线
```

---

## 7. 与权威输入文档的出入（以源码/实测为准）

1. **F821 触发条件**：P0-T02 §5.2 与 T01 附注描述为"state 缺 `tick_duration_minutes` 时触发"。
   实测：`.get` 的默认参数恒被求值，**该路径每次 physics_resolve 都触发**，物理 LLM 调用从不发生
   （KBC-1）。影响面大于报告描述。
2. **physics_resolve 降级策略**：T01 §3 描述正确（空 outcomes + 错误日志），但 v1 中它不是
   "失败时"的降级，而是**常态**。
3. **player_action_resolve 降级**：T01 §3 描述正确；实测发现"超长移动"输入类**必然**触发该
   降级（KBC-5），属报告未提及的额外路径。
4. **world_rules 键名**：与 T01 Leader 核对附注一致（`disable`/`append`）；`locked_attributes`
   规则字段为 `type`（与 InitFileGuide.md 一致，T01 §6.2 的 `rule_type` 表述不准确）。
5. **event_log 压缩**：T01 §4.3 描述 state_apply "按需执行滑动窗口压缩"；实测受 reducer 语义
   限制只能追加摘要行（KBC-6）。
6. **tick_speed 默认策略**：T01 §3 未细化；实测默认策略为 `min(npc_durations)`，其次
   `player_duration`，最后 `default`；`default` 仅在无任何行动耗时时生效。

---

## 8. 对 v2 迁移的提示

1. KBC-1/KBC-2/KBC-5 表明 v1 的"物理结算"与"长行动估算"在真实运行中从未按设计工作；v2 重写时
   不应把这些行为当作需要保留的契约（由 H1 决策），但**事件日志文本**（如
   `[错误] 物理模拟失败，本轮跳过物理结果。`）若被前端/剧本依赖，需要兼容评估。
2. Fan-out 合并语义（§4 末）是 LangGraph 超步调度的涌现行为；v2 若改变调度模型，需显式定义
   "语义属性更新"与"叙事后更新"的权威合并顺序。
3. reducer 通道（event_log/action_intents/narrative_history）的累加语义被 main.py/WebUI 依赖，
   v2 状态容器迁移时需保留等价语义或提供迁移层。
4. 本报告的全部测试可作为 v2 引擎的回归参照：凡被 H1 认定为"兼容契约"的断言，v2 实现应使其
   继续通过；认定为 bug 的，可在 v2 中修复并同步修订对应测试。

---

*报告完。下游任务包 P0-T04（Reference Transcripts）可直接复用 `tests/char_helpers.py` 的
FakeLLM 与状态工厂生成确定性运行轨迹。*
