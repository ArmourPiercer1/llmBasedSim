"""llmBasedSim Architecture v2 引擎根包（P0-T05 骨架，仅占位）。

本包是 v2 引擎的顶层命名空间，按 Spec §44「推荐源码目录」组织，
当前仅建立目录骨架，不实现任何功能、不 import 任何重型依赖。

冻结规则（详见 src/engine_v2/README.md）：
- 不得 import v1 模块（src/graph、src/game、src/agents、src/web、src/llm、
  src/prompts、src/config、src/models、src/ui）；
- 不得被 v1 入口（src/main.py、public_start/、web/）引用；
- LangGraph / OpenAI 依赖不得进入 engine_v2.core（G1 门禁：Core import
  不需要 LangGraph / OpenAI）。

后续 Phase 填充计划见 Spec §46（MVP 范围）与 §47（第一期开发顺序）。
"""
