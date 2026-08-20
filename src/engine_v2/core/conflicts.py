"""engine_v2 core 层 Conflict Resolution（P2 设计规范 §5；P2-T05 实现载体）。

**导入面占位骨架（P2-T01 交付）**：本文件仅为模块落位形态，服务于
D-P2-19 的 19 模块清单同步（``test_closeout.py`` / ``test_import_boundary.py``
的 13 → 19 机械修订）——清单与文件集合断言要求全部 19 个 core 子模块
**存在且可导入**。行为主体（``ConflictKey`` 锁推导、``detect_conflicts``
连通分量分组、``ConflictStrategy`` 协议、默认四策
``AuthorityPriorityStrategy`` / ``TimestampStrategy`` /
``ProducerPriorityStrategy`` / ``EntityFifoStrategy`` 与
``DefaultConflictResolver``、``TIMESTAMP_METADATA_KEY`` 等）由 **P2-T05**
在本文件实现，届时按 §10.2/§10.3 补全本模块 ``__all__`` 与
``core/__init__.py`` re-export 块。此前本模块无公开导出。

Import 边界（P1 设计 §0.3 继承）：只允许 stdlib + pydantic + 同包
``src.engine_v2``。
"""

__all__: list[str] = []
