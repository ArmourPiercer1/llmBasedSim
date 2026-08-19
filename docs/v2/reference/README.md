# v1 Reference Transcripts（任务包 P0-T04）

Phase 0「冻结 v1 & 基线」交付物：3 个 v1 reference project 的
**开局文件 + 脚本化玩家输入序列 + 记录脚本**，用于
G0 门禁「旧 v1 能用至少 2 个 reference project 启动」的实证，
以及后续 v1/v2 行为差异比较的参照语料。

- 分支：`architecture-v2`
- 生成日期：2026-08-20
- 环境：Python 3.12.14（`.venv/bin/python`）
- 权威输入：`docs/v2/reports/P0-T01-repo-inventory.md` §6（init YAML schema、存档格式）、
  `public_start/*.yaml`、`src/main.py`、`src/agents/init.py`

## 1. Reference Project 清单

| 场景 | init 文件 | 世界 / 玩家 | 规模（selfcheck 实测） | 输入序列 | 条目数（行动 tick / 命令） |
|---|---|---|---|---|---|
| whisperheads（耳语山） | `public_start/whisperheads.yaml` | 耳语山 / 加维尔·洛肯 | 7 地点、9 物体、7 NPC、max_ticks=60 | `inputs/whisperheads.json` | 8（6 / 2） |
| murder（谋杀星） | `public_start/murder.yaml` | 谋杀星 / 扫罗·塔尔维茨 | 11 地点、12 物体、5 NPC、max_ticks=75 | `inputs/murder.json` | 8（7 / 1） |
| test_empty（测试房间） | `public_start/test_empty.yaml` | 测试房间 / 测试者 | 3 地点、4 物体、0 NPC、max_ticks=20 | `inputs/test_empty.json` | 8（6 / 2） |

选取理由：
- **whisperheads**：最复杂剧本（战锤 40K 克苏鲁风），7 个 NPC、隐藏属性
  （`corruption_resistance`/`corruption_level` 等）、`world_rules.physics/attribute`
  自定义规则、`ticks_per_game_minute=0.5`，适合检验 v1 全链路（含长任务、
  多 NPC 并发决策、属性 DSL）。
- **murder**：中型剧本（军事科幻恐怖），5 个 NPC、多地点连通图
  （11 地点）、自定义物理/属性规则、`ticks_per_game_minute=0.5`，
  检验跨地点推进与长行动评估。
- **test_empty**：最小场景（无 NPC、`ticks_per_game_minute=1`），
  用于隔离验证 v1 核心循环（意图解析→可行性→tick 计算→物理→状态→
  属性→感官→叙事）在空世界下的基线行为。

## 2. 输入序列设计意图

每个序列 8 条（满足 5–10 条要求），内容贴合场景设定，类别覆盖如下：

| 类别 | whisperheads | murder | test_empty | 设计意图 |
|---|---|---|---|---|
| observe（观察） | 条目 1、6 | 条目 1、8 | 条目 1、4 | 建立感知基线；whisperheads 条目 6 用特殊感官侦听 Vox 低语，牵引 `vox_integrity`；murder 条目 8 观察棘刺树尸体，铺垫 `gene_seed_samples` |
| talk（对话） | 条目 2（维普斯）、5（朱巴尔） | 条目 2（卢修斯）、6（布勒） | —（无 NPC 场景，不适用） | 检验 NPC 决策与对话事件；whisperheads 条目 5 安抚朱巴尔牵引 `resentment`/`sanity`/`corruption_level` 主线；murder 条目 2 触发“纯洁 vs 优越”人设冲突（`corruption_risk`），条目 6 牵引 `squad_cohesion`/`grudging_respect_tarvitz` |
| interact（交互） | 条目 3（风暴鸟货舱） | 条目 3（爆破装药箱）、5（空降舱通讯） | 条目 2（发光水晶）、6（旧羊皮纸卷） | 检验物体 `state` 读取与 interact 可行性判定；murder 条目 5 为长行动，检验 `duration_minutes`/`action_continuation` |
| move（移动） | 条目 7（推进石桥） | 条目 7（向东至棘刺树） | 条目 3（石室→走廊）、5（走廊→储藏室） | 检验移动坐标解析、地点连接关系与 tick 耗时计算；whisperheads 条目 7 附带部队指挥与冰层承重（自定义物理规则 15） |
| /status | 条目 4 | 条目 4 | 条目 7 | v1 CLI 命令（不触发图 tick），验证状态渲染数据（tick、游戏时间、位置、属性） |
| /save | 条目 8 | —（由 whisperheads/test_empty 承担） | 条目 8 | v1 存档路径验证：`strip_transient_state` 落盘，格式与 v1 `saves/<name>.json` 一致 |

**命令语义与 v1 完全一致**（`src/main.py::collect_next_player_input`）：
`/status`、`/save <name>`、`/see`、`/hear`、`/feel`、`/idid`、`/help`、
`/quit` 由主循环外壳处理，**不消耗 tick**；在 transcript 中记为
`kind: "command"` 条目并附对应载荷。`/save` 的存档文件被本脚本重定向写入
`transcripts/saves/<scenario>__<name>.json`（任务只允许写
`docs/v2/reference/**`，仓库 `saves/` 目录不被触碰），内容与 v1 格式逐字节同源
（同一 `strip_transient_state` 输出，`ensure_ascii=False, indent=2`）。

## 3. Transcript 格式说明

输出：`transcripts/<scenario>.json`（UTF-8，`ensure_ascii=False, indent=2`）。

```jsonc
{
  "transcript_version": 1,
  "scenario": "whisperheads",
  "init_file": "public_start/whisperheads.yaml",       // 相对仓库根
  "inputs_file": "docs/v2/reference/inputs/whisperheads.json",
  "world_name": "耳语山",
  "player_name": "加维尔·洛肯",
  "recorded_at": "2026-08-20T02:30:00Z",
  "runtime": {
    "python": "3.12.14",
    "repo_root": "/home/armourpiercer/projects/llmBasedSim",
    "branch_note": "architecture-v2（禁止 git 命令，不记录 commit hash）",
    "v1_loading_path": "load_init_file -> init_file_to_game_state; build_game_graph; graph.ainvoke(thread_id=tick_N)——与 src/main.py 相同"
  },
  "llm": {
    "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com",
    "temperature": 0.7,
    "max_tokens": 16384,
    "api_key": "REDACTED（按任务纪律不写入任何交付文件）"
  },
  "tick_count": 6,            // 实际执行的动作 tick 数
  "command_count": 2,         // CLI 命令条目数
  "status": "completed",      // 或 "interrupted:<原因>"
  "entries": [ /* 按输入顺序的逐条记录，见下 */ ]
}
```

**动作 tick 条目**（`kind: "action"`）：

```jsonc
{
  "index": 1, "tick": 0, "kind": "action", "category": "observe",
  "input": "环顾四周，……",
  "player_action": {           // 意图解析 + 可行性判定结果（result["player_action"]）
    "interpreted_intent": "……", "action_type": "observe",
    "action_description": "……", "speech_content": null,
    "target_character_id": null, "target_object_id": null, "target_position": null,
    "feasibility": "allowed", "feasibility_reason": "……",
    "success_probability": null, "confidence": 0.95,
    "duration_minutes": 0.0, "continue_until": ""
  },
  "percept_summary": {          // player_percept 摘要
    "summary": "……",
    "self_action_summary": "……",
    "hidden_event_count": 0,
    "senses": [ { "sense": "sight", "description": "……", "source_object_id": null, "confidence": 1.0 } ],
    "player_attributes": { "stamina": 95 }
  },
  "event_log_delta": [ "[玩家意图] ……", "[物理] ……" ],  // 本 tick 新增的 event_log 行
  "event_log_compacted": false,     // true = 日志被 compact_event_log 压缩，delta 为完整尾部
  "state_diff": {                 // 关键 state diff（before → after）
    "player_position": { "before": {"x":0,"y":0,"z":0}, "after": {"x":0,"y":0,"z":0}, "changed": false },
    "character_positions_moved": { "<cid>": { "before": {...}, "after": {...} } },
    "game_time": { "before": {"hour":5,"minute":15}, "after": {"hour":5,"minute":20} },
    "tick_duration_minutes": 10.0,
    "player_attributes_changed": { "vox_integrity": { "before": 60, "after": 59.2 } },
    "character_attributes_changed": { "<cid>": { "<attr>": { "before": 30, "after": 30.6 } } },
    "inventory": { "added": [], "removed": [] },
    "object_state_changed": { "<oid>": { "before": {...}, "after": {...} } },
    "action_continuation": null
  },
  "narrative_appended": [ { /* narrative_history 新增条目 */ } ],
  "game_phase": "running",
  "elapsed_s": 42.3
}
```

**命令条目**（`kind: "command"`）：

```jsonc
{
  "index": 4, "tick_at_command": 2, "kind": "command",
  "command": "/status", "input": "/status",
  "payload": { /* /status: 完整状态快照（build_status_payload）；
                 /save: { save_file, json_bytes, tick, game_time, world_name, top_level_keys }；
                 /see|/hear|/feel: 对应感官类别的 senses；/idid: self_action_summary */ },
  "note": "v1 CLI 命令：由主循环外壳处理，不触发图 tick"
}
```

**event_log 增量计算**：以 tick 前状态 `event_log` 为基线，若 tick 后列表
以前者为前缀，delta 为后缀新增部分；若被 `compact_event_log`（阈值 100 条，
保留近 50 条）压缩/重写，则 `event_log_compacted: true` 且 delta 为完整尾部。

## 4. 记录脚本与复现命令

脚本：`docs/v2/reference/record_transcript.py`（纯标准库 + 仓库依赖，
与 `src/main.py` 相同的加载/构图路径：`ConfigLoader -> ChatOpenAI ->
PromptLoader -> load_init_file / init_file_to_game_state -> build_game_graph ->
graph.ainvoke`；每个场景独立构图、`thread_id=tick_N`，等价于对 `main.py`
起独立进程）。

```bash
# 在仓库根目录，只允许 .venv/bin/python
cd /home/armourpiercer/projects/llmBasedSim

# 自检（不需要 API key，不调用 LLM）：模块导入 + config 加载 +
# 3 个输入序列/init 文件校验 + key 状态报告
.venv/bin/python docs/v2/reference/record_transcript.py --selfcheck

# 实际记录（需要 .env 中的真实 DEEPSEEK_API_KEY）
.venv/bin/python docs/v2/reference/record_transcript.py --all
.venv/bin/python docs/v2/reference/record_transcript.py --scenario whisperheads
.venv/bin/python docs/v2/reference/record_transcript.py --scenario murder
.venv/bin/python docs/v2/reference/record_transcript.py --scenario test_empty

# 验证产物 JSON 可解析（G0 要求）
.venv/bin/python -m json.tool docs/v2/reference/transcripts/whisperheads.json > /dev/null && echo OK
```

**退出码**：`0` 成功/自检通过；`1` 运行时错误；`2` 参数错误；
`3` `DEEPSEEK_API_KEY` 缺失或仍为占位符（`sk-your-...`，脚本会打印明确提示
并以该专用码结束，绝不回显 key 内容）。

可选参数：`--out-dir <dir>`（默认 `docs/v2/reference/transcripts`）、
`--timeout-per-tick <秒>`（默认 600，单 tick 超时后 transcript 以
`interrupted` 状态落盘）。

## 5. 当前状态（重要）

- 2026-08-20 检查：`.env` 中 `DEEPSEEK_API_KEY` 为**占位符**（`sk-your-...`）。
  按任务纪律**未运行真实对局**，`transcripts/` 下暂无 transcript 与 saves 产物，
  仅有 `transcripts/PENDING.md` 待执行标记。
- 静态验证已通过（selfcheck PASSED）：3 个 init 文件均可经 v1 相同加载路径
  构建初始 GameState，输入序列语法与条目数校验全部通过。
- **门禁影响**：G0「旧 v1 能用至少 2 个 reference project 启动」的
  transcript 实证条目**暂挂**，待 key 就绪后执行 `--all` 即完成（脚本与
  fixtures 已就绪，预计每场景 8 条输入约 6–8 次 LLM 密集 tick）。
- 无 key 情形的 Required tests 均已执行并通过：
  - `--help`（exit 0）：证明脚本可导入（含全部 `src.*` 顶层导入）、参数解析正常；
  - `--selfcheck`（exit 0）：证明加载/构图路径对 3 个 reference project 可用；
  - `--all`（exit 3）：证明无 key 提示正确且以专用退出码结束。

## 6. 文件清单

```
docs/v2/reference/
├── README.md                      # 本文件
├── record_transcript.py           # 记录脚本（selfcheck / --all / --scenario）
├── inputs/
│   ├── whisperheads.json          # 8 条输入序列（6 行动 + /status + /save）
│   ├── murder.json                # 8 条输入序列（7 行动 + /status）
│   └── test_empty.json            # 8 条输入序列（6 行动 + /status + /save）
└── transcripts/
    ├── PENDING.md                 # 待执行标记（API key 为占位符）
    ├── saves/                     # /save 命令产物目录（.gitkeep 占位）
    ├── whisperheads.json          # （待执行后生成）
    ├── murder.json                # （待执行后生成）
    └── test_empty.json            # （待执行后生成）
```
