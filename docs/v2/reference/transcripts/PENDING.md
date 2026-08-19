# Transcripts 待执行标记（PENDING）

**状态：transcript 实际执行待 API key（2026-08-20 起）**

## 原因

任务包 P0-T04 要求：若仓库根 `.env` 中 `DEEPSEEK_API_KEY` 仍为占位符（`sk-your-...`）
或为空，则**不得运行真实对局**，交付物为 fixtures + 脚本 + 本待执行标记。

- 检查时间：2026-08-20
- 检查结果：`DEEPSEEK_API_KEY` 已设置但为占位符（以 `sk-your` 开头，长度 29），
  判定为 **placeholder**（不记录 key 内容）。
- 因此 `whisperheads.json` / `murder.json` / `test_empty.json` 三个 transcript
  **尚未生成**；`saves/` 下暂无存档产物。

## 如何执行

1. 在仓库根 `.env` 填入真实 DeepSeek API key；
2. 在仓库根目录运行（只允许 `.venv/bin/python`）：

   ```bash
   .venv/bin/python docs/v2/reference/record_transcript.py --all
   ```

   或单场景：

   ```bash
   .venv/bin/python docs/v2/reference/record_transcript.py --scenario whisperheads
   .venv/bin/python docs/v2/reference/record_transcript.py --scenario murder
   .venv/bin/python docs/v2/reference/record_transcript.py --scenario test_empty
   ```

3. 成功后本目录将生成：
   - `whisperheads.json`、`murder.json`、`test_empty.json`（逐 tick transcript）；
   - `saves/whisperheads__ref04_whisperheads_end.json`、
     `saves/test_empty__ref04_test_empty_end.json`（v1 存档格式，
     与 `saves/<name>.json` 相同的 `strip_transient_state` 输出）。
4. 用 `.venv/bin/python -m json.tool <file>` 验证 JSON 可解析（G0 要求）。

## 门禁影响

- G0 条目「旧 v1 能用至少 2 个 reference project 启动」的 **transcript 实证部分暂挂**，
  待 key 就绪后执行；
- 脚本与 fixtures 的静态验证（`--selfcheck`：模块导入、config 加载、3 个 init 文件
  经 `load_init_file`/`init_file_to_game_state` 成功构建初始 GameState）已通过，
  说明 v1 的加载/构图路径对 3 个 reference project 均可用（不依赖 LLM 的部分）。
