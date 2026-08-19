"""engine_v2 core 层 Revision 原语与陈旧性纯函数（P1-T01）。

依据 ``docs/v2/contracts/P1-core-data-contracts.md`` §2.3（下称"设计文档"）：

- 决策 D-2：``Revision`` 采用 **typed ``int`` 子类**——revision 需要算术
  （commit +1，Spec §9）与比较（staleness 判定），JSON 中必须是数字
  （§0.2 JSON-friendly 铁律 2）；
- ``world_revision`` **只**因 COMMITTED transaction 递增（Spec §9、
  §20.1 "produce one world revision"）；调度簿记、trace 追加、view 派生
  **不**推进它（决策 D-5，设计文档 §4.2）；
- 一切异步结果必须能携带 ``base_world_revision``（ActionProposal /
  ProposedEffect 的必填字段，设计文档 §6.1/§6.3）——字段落位在 T02/T04，
  本模块只提供 ``Revision`` 类型、常量与纯函数；
- revalidation 四种结果 :class:`RevalidationOutcome`（ACCEPT/REBASE/
  REPAIR/REJECT，Spec §9）的数据词表落位于此（决策 D-13，设计文档 §5.1）；
  其**判定行为**属 P2（Plan P2-T04），P1 只落数据词表。

Pydantic 兼容性（设计文档 §2.1 风险项）：本仓 pydantic 2.13 对裸 int 子类
注解不再生成 core schema，故 ``Revision`` 提供与 ID 族同构的
``__get_pydantic_core_schema__`` 兜底：接受原生 ``int`` 值，校验链末端
重建为 ``Revision`` 实例——``model_validate`` 后 ``type(x) is Revision``
保持，JSON 序列化为纯整数。

本模块只 import 标准库与 pydantic（§0.3 import 边界白名单），不触碰 v1。
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Final

from pydantic import AfterValidator

__all__ = [
    "Revision",
    "INITIAL_WORLD_REVISION",
    "next_revision",
    "is_stale",
    "RevalidationOutcome",
]


class Revision(int):
    """WorldState 权威版本号：每次 transaction commit 成功 +1（Spec §9）。

    typed ``int`` 子类（决策 D-2）：支持算术与比较，JSON 中为纯整数。
    ``world_revision`` 只随 COMMITTED transaction 递增（决策 D-5）；
    本类型本身是无状态值类型，不持有任何世界引用。
    """

    __slots__ = ()

    def next(self) -> "Revision":
        """返回 self + 1 的新 ``Revision``（Spec §9：一次 COMMITTED 恰好 +1）。"""
        return Revision(self + 1)

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        """Pydantic v2 集成：接受原生 int 值，校验链末端重建为 ``Revision`` 实例。

        内层 ``int`` schema 完成数值校验，``AfterValidator(cls)`` 在校验
        完成后重建为 ``cls`` 实例——``model_validate`` 后（含 dict 键、
        list 元素）保持 ``type(x) is cls``，JSON 序列化为纯整数（设计文档
        §0.2 / §2.1，测试口径 R2/R5）。仅依赖 pydantic 公共 API。
        """
        return handler(Annotated[int, AfterValidator(cls)])


#: 初始世界 revision（Spec §9；WorldState 未提交任何事务时的版本）。
INITIAL_WORLD_REVISION: Final[Revision] = Revision(0)


def next_revision(rev: Revision) -> Revision:
    """rev + 1（Spec §9：world_revision 只随 COMMITTED transaction 递增）。"""
    return Revision(rev + 1)


def is_stale(base: Revision, current: Revision, valid_until: "Revision | None" = None) -> bool:
    """陈旧性判定（Spec §9）。

    ``base < current`` 即陈旧；``valid_until`` 非 None 时
    ``current > valid_until`` 亦陈旧（``current == valid_until`` 不陈旧）。
    纯函数，不做任何状态访问；revalidation 决策（ACCEPT/REBASE/REPAIR/
    REJECT）属 P2 行为。
    """
    if base < current:
        return True
    return valid_until is not None and current > valid_until


class RevalidationOutcome(str, Enum):
    """Spec §9 revalidation 决策词表（数据层落位，决策 D-13）。

    判定行为属 P2（Plan P2-T04）；P1 只落数据词表。枚举一律
    ``class Xxx(str, Enum)``，JSON 值为字符串字面量（设计文档 §0.1）。
    """

    ACCEPT = "accept"
    REBASE = "rebase"
    REPAIR = "repair"
    REJECT = "reject"
