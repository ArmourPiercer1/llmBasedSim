# Contributing

本文档面向参与本项目开发的协作者，说明如何配置环境、运行项目、理解模块边界，以及提交改动前应做哪些检查。

## 项目协作目标

本项目当前目标是把 LLM Agent 互动模拟游戏从可运行原型推进到稳定、可测试、可扩展的开发框架。

协作开发时请优先关注：

1. 保持模块边界清晰；
2. 优先修复会影响主循环稳定性的 bug；
3. 对 Prompt、状态结构、图流程的修改要尽量小步提交；
4. 不要把真实 API Key 提交到仓库。

## 本地开发环境

要求：

- Python >= 3.12
- uv
- DeepSeek API Key

安装依赖：

```bash
uv pip install -e .
```

复制环境变量示例：

```bash
copy .env.example .env
```

然后在 `.env` 中填入：

```env
DEEPSEEK_API_KEY=sk-...
```

## 运行项目

```bash
python -m src.main
```

## 推荐开发流程

1. 先阅读 `README.md` 的架构说明；
2. 确认要修改的模块边界；
3. 小步修改；
4. 本地运行 `python -m src.main` 验证主流程；
5. 如果修改了模型、状态应用或解析逻辑，应补充或更新测试；
6. 提交前确认没有提交 `.env`、日志或本地缓存。

## 代码结构约定

- `src/main.py`：只负责入口、主循环和服务装配；
- `src/graph/game_graph.py`：负责 tick 管道和节点逻辑；
- `src/graph/game_state.py`：负责全局状态 schema；
- `src/models/`：只放数据模型，不放业务流程；
- `src/agents/`：放 Agent 初始化或可复用 Agent 逻辑；
- `src/llm/parser.py`：集中处理 LLM JSON 结构化输出；
- `prompts/`：只放 prompt 模板；
- `config/`：只放可编辑配置。

## Prompt 修改约定

修改 prompt 时请注意：

1. 保持中文输出；
2. 明确 JSON 输出要求；
3. 不要在 prompt 中引入与 Pydantic schema 不一致的字段；
4. 如果修改了输出结构，需要同步修改 `src/models/`；
5. 修改角色、物理、感官 prompt 后，至少手动跑一轮游戏验证。

## 接口文档维护约定

[`docs/game-flow-interfaces.md`](docs/game-flow-interfaces.md) 记录游戏主流程的状态、节点、Prompt、配置和存档接口。涉及以下修改时，必须同步更新该文档：

- `GameState` 字段；
- LangGraph 节点输入/输出；
- Prompt JSON 输出结构；
- `src/models/events.py` 中的事件/行动模型；
- YAML 配置 schema；
- 存档格式。

`CONTRIBUTING.md` 只记录协作规则；具体接口细节以 `docs/game-flow-interfaces.md` 为准。

## 测试与验证

当前测试体系尚未补齐。临时验证方式：

```bash
python -m src.main
```

建议后续逐步补充：

- `generate_structured()` 单元测试；
- `_config_to_game_state()` 单元测试；
- `state_apply()` 单元测试；
- mock LLM 的完整 tick 集成测试。

## 提交前检查清单

提交前请确认：

- [ ] 没有提交 `.env` 或真实 API Key；
- [ ] 主入口 `python -m src.main` 可以启动；
- [ ] 修改 Prompt 后至少手动验证一轮；
- [ ] 修改模型后检查相关解析逻辑；
- [ ] 修改状态结构后检查 `GameState`、`state_apply()` 和 UI 渲染；
- [ ] 不把本地日志、缓存、虚拟环境提交到仓库。

## 当前优先任务

近期优先任务：

1. 玩家动作结构化为 `PlayerAction`；
2. 增强 `state_apply()`；
3. 增加 debug 输出开关；
4. 补齐基础测试；
5. 支持从 YAML 直接开局；
6. 在稳定前提下优化角色决策并发。
