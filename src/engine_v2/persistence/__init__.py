"""v2 持久化 / 存档 / 回放（占位，Phase 8 填充）。

职责：Snapshot / Checkpoint / Replay——事件级回放、revision 对齐、
replay 后端抽象，支撑「snapshot + event-level replay」MVP 能力。

对应 Spec 章节：§30 Persistence / Save / Replay、§9 Revision Model、
§46 MVP 第 21 条（snapshot + event-level replay）。
"""
