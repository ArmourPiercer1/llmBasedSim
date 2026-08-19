"""P1-T01 单元测试：Revision 原语与陈旧性纯函数（设计文档 §7.1 R5–R6）。

覆盖：

- R5 Revision 语义：``INITIAL_WORLD_REVISION == 0``；``next_revision(r) == r + 1``；
  JSON 中为纯整数；
- R6 staleness：``is_stale(base=812, current=813)`` 为真；``base == current`` 为假；
  ``valid_until`` 边界（``current == valid_until`` 不陈旧，``current > valid_until``
  陈旧）；
- typed int 子类类型保持（决策 D-2 + 设计文档 §2.1 风险项）与 JSON round-trip；
- ``RevalidationOutcome`` 词表（ACCEPT/REBASE/REPAIR/REJECT；决策 D-13：
  P1 只落数据词表，判定行为属 P2）。

全部用例无网络、无 LLM、无 API key（Spec §47 Phase 1 验收）。
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from src.engine_v2.core.revision import (
    INITIAL_WORLD_REVISION,
    RevalidationOutcome,
    Revision,
    is_stale,
    next_revision,
)


class _RevisionEnvelope(BaseModel):
    """测试专用信封模型：验证 Revision 字段/list/dict 键的类型保持与 JSON round-trip。

    T06（P1-T06）将以完整契约模型固化同款断言（设计文档 §8.1）。
    """

    world_revision: Revision
    base_world_revision: Revision | None = None
    revisions: list[Revision] = []
    label_by_revision: dict[Revision, str] = {}


class TestR5RevisionSemantics:
    """R5：INITIAL_WORLD_REVISION / next / next_revision 语义与 JSON 纯整数。"""

    def test_initial_world_revision_is_zero(self) -> None:
        assert INITIAL_WORLD_REVISION == 0
        assert int(INITIAL_WORLD_REVISION) == 0
        assert type(INITIAL_WORLD_REVISION) is Revision

    @pytest.mark.parametrize("base", (0, 1, 812, 10**18))
    def test_next_revision_increments_by_one(self, base: int) -> None:
        result = next_revision(Revision(base))
        assert result == base + 1
        assert type(result) is Revision
        assert result is not next_revision(Revision(base))  # 每次调用产生新对象

    def test_next_method_matches_next_revision(self) -> None:
        for base in (0, 812):
            assert Revision(base).next() == next_revision(Revision(base))
            assert type(Revision(base).next()) is Revision

    def test_revision_is_int_subclass_with_arithmetic_and_comparison(self) -> None:
        rev = Revision(812)
        assert isinstance(rev, int)
        assert rev + 1 == 813
        assert rev < Revision(813)
        assert rev == 812

    def test_json_roundtrip_pure_int_and_type_preserved(self) -> None:
        env = _RevisionEnvelope(
            world_revision=Revision(812),
            base_world_revision=Revision(811),
            revisions=[Revision(0), Revision(1), Revision(812)],
            label_by_revision={Revision(0): "init", Revision(812): "current"},
        )
        dumped = env.model_dump(mode="json")
        # §0.2 JSON-friendly 铁律 2：Revision 序列化为纯整数（无对象包装）
        assert type(dumped["world_revision"]) is int
        assert dumped["world_revision"] == 812
        assert dumped["base_world_revision"] == 811
        assert dumped["revisions"] == [0, 1, 812]
        # JSON dict 键必须是 str（序列化层）
        assert all(type(k) is str for k in dumped["label_by_revision"])

        # round-trip 判据（§0.2 规则 5）+ 类型保持（§2.1 / R5）
        reloaded = _RevisionEnvelope.model_validate(dumped)
        assert reloaded == env, "round-trip 后值必须相等"
        assert type(reloaded.world_revision) is Revision
        assert type(reloaded.base_world_revision) is Revision
        assert all(type(r) is Revision for r in reloaded.revisions)
        # dict 键类型重建为 Revision
        assert all(type(k) is Revision for k in reloaded.label_by_revision)
        assert reloaded.label_by_revision == env.label_by_revision

    def test_json_text_roundtrip(self) -> None:
        """JSON 文本级 round-trip：model_dump_json → model_validate_json。"""
        env = _RevisionEnvelope(world_revision=Revision(812), base_world_revision=Revision(811))
        text = env.model_dump_json()
        reloaded = _RevisionEnvelope.model_validate_json(text)
        assert reloaded == env
        assert type(reloaded.world_revision) is Revision
        assert type(reloaded.base_world_revision) is Revision

    def test_optional_revision_none_preserved(self) -> None:
        """严格 Optional 语义（设计文档 §9 KBC-7 防线）：None 不得被改写。"""
        env = _RevisionEnvelope(world_revision=Revision(0))
        dumped = env.model_dump(mode="json")
        assert dumped["base_world_revision"] is None
        reloaded = _RevisionEnvelope.model_validate(dumped)
        assert reloaded.base_world_revision is None


class TestR6Staleness:
    """R6：is_stale 陈旧性判定（Spec §9），含 valid_until 边界。"""

    @pytest.mark.parametrize(
        ("base", "current", "valid_until", "expected"),
        [
            (812, 813, None, True),  # 设计文档 §7.1 R6 示例：base < current → 陈旧
            (812, 812, None, False),  # base == current → 不陈旧
            (813, 812, None, False),  # base > current → 不陈旧
            (812, 814, 813, True),  # base < current 且 current > valid_until
            (812, 812, 812, False),  # 边界：current == valid_until → 不陈旧
            (812, 812, 811, True),  # 边界：current > valid_until → 陈旧
            (0, 1, None, True),  # 初始状态 → +1 即陈旧
            (0, 0, 0, False),
        ],
    )
    def test_is_stale(self, base: int, current: int, valid_until: int | None, expected: bool) -> None:
        vu = None if valid_until is None else Revision(valid_until)
        assert is_stale(Revision(base), Revision(current), vu) is expected

    def test_is_stale_accepts_plain_ints_per_design_table(self) -> None:
        """设计文档 §7.1 R6 字面口径 ``is_stale(base=812, current=813)``（Revision 即 int 子类）。"""
        assert is_stale(base=812, current=813) is True  # type: ignore[arg-type]
        assert is_stale(base=812, current=812) is False  # type: ignore[arg-type]
        assert is_stale(base=812, current=812, valid_until=811) is True  # type: ignore[arg-type]

    def test_is_stale_is_pure(self) -> None:
        """纯函数：重复调用结果确定，不改动任何模块级状态（设计文档 §2.3）。"""
        assert is_stale(Revision(1), Revision(2)) is True
        assert is_stale(Revision(1), Revision(2)) is True
        assert INITIAL_WORLD_REVISION == 0  # 常量未被调用改写


class TestRevalidationOutcome:
    """RevalidationOutcome 词表（设计文档 §1.1 / §5.1 决策 D-13 / Spec §9）。"""

    def test_vocab_members(self) -> None:
        assert {m.name for m in RevalidationOutcome} == {"ACCEPT", "REBASE", "REPAIR", "REJECT"}

    def test_str_enum_json_literals(self) -> None:
        """枚举一律 ``class Xxx(str, Enum)``，JSON 值为字符串字面量（设计文档 §0.1）。"""
        assert isinstance(RevalidationOutcome.ACCEPT, str)
        assert RevalidationOutcome.ACCEPT == "accept"
        assert RevalidationOutcome.REBASE == "rebase"
        assert RevalidationOutcome.REPAIR == "repair"
        assert RevalidationOutcome.REJECT == "reject"

    def test_json_roundtrip(self) -> None:
        class _OutcomeEnvelope(BaseModel):
            outcome: RevalidationOutcome

        model = _OutcomeEnvelope.model_validate({"outcome": "rebase"})
        assert model.outcome is RevalidationOutcome.REBASE
        assert model.model_dump(mode="json") == {"outcome": "rebase"}
        with pytest.raises(ValueError):
            _OutcomeEnvelope.model_validate({"outcome": "unknown"})
