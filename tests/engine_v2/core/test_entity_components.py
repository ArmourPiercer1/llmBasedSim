"""P1-T03 单元测试：Entity + typed component 逻辑门面（设计文档 §7.2 E1–E5）。

覆盖（对齐设计文档 §7.2 测试契约）：

- **E1 registry 冲突**：同 component_type 注册不同 schema → 抛
  ``ComponentConflictError``；相同 schema 重复注册幂等；
- **E2 未知组件类型**（决策 D-8）：registry 对未注册类型 get 返回 None、
  ``validate_payload`` 放行；有 schema 时拒绝非法 payload；EntityRecord 侧
  接受未注册组件类型数据（按不透明 JSON dict 存储）；
- **E3 门面只读**：``EntityView.get_component()`` 返回值不可写（赋值抛
  ``TypeError``，嵌套层同样）；frozen 阻断字段再赋值；EntityRecord/EntityView
  无公共写 API（静态断言：无公共 mutator 方法名）；
- **E4 EntityId 唯一**：``_build_entities`` builder 助手对重复 EntityId 显式
  抛错（dict 语义折叠是静默丢失）；``_entity_ids_with_component`` 结果正确；
- **E5 引用完整性**：``EntityRef`` 指向不存在 entity / 未挂载组件：引用为纯
  数据可构造，门面查询返回 None，不抛未定义异常（非法引用"判定"属 P2
  validation，P1 只保证查询安全）；
- **§3.5 reducer-only 纪律**：零公共写 API、入口深拷贝（调用方可变输入不别名
  进状态树）、``_with_*`` 私有构造助手（新实例、零别名、整体替换）；
- **JSON round-trip**（§0.2 铁律 / §6.1）：EntityRecord / EntityRef 值相等 +
  类型保持（EntityId / Revision / ComponentTypeId）、typed 键为纯字符串、
  严格 Optional 语义（None 不改写，KBC-7）、extra=forbid、Unicode 无损。

私有助手（``_build_entities`` / ``_entity_ids_with_component`` /
``_with_components`` / ``_from_record``）是设计文档 §3.5 纪律 3 的"唯一变更
缝隙"，明确"供测试与未来 reducer 使用"，本文件直接调用验证。

全部用例无网络、无 LLM、无 API key（Spec §47 Phase 1 验收）。
"""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

import src.engine_v2.core.components as components_module
import src.engine_v2.core.entity as entity_module
from src.engine_v2.core.components import (
    COMPONENT_TYPE_ID_PATTERN,
    ComponentConflictError,
    ComponentData,
    ComponentRegistry,
    ComponentSchema,
    ComponentTypeId,
    parse_component_type_id,
)
from src.engine_v2.core.entity import (
    ContractModel,
    EntityRecord,
    EntityRef,
    EntityView,
    _build_entities,
    _entity_ids_with_component,
)
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.revision import INITIAL_WORLD_REVISION, Revision


# —— 测试专用 fixture 模型（非契约类型）——


class _PositionModel(BaseModel):
    """E2 用 payload schema：带 extra=forbid，用于校验"有 schema 拒绝非法 payload"。"""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


def _sample_record() -> EntityRecord:
    """完整样本：中文内容、嵌套 JSON、typed 键（JSON round-trip / 深冻结通用）。"""
    return EntityRecord.model_validate(
        {
            "entity_id": "ent_test_alice",
            "entity_class": "npc.villager",
            "tags": ["ally", "村庄守卫"],
            "created_revision": 812,
            "components": {
                "space.position": {"x": 1.5, "y": -2, "grid": [0, 1]},
                "custom.opaque": {"nested": {"deep": True, "nothing": None}, "note": "中文备注"},
            },
        }
    )


def _assert_json_clean(value: Any) -> None:
    """递归断言仅含 JSON 原生类型（§0.2 铁律 1；T05 提供正式工具，此处为 T03 自测口径）。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for item in value:
            _assert_json_clean(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str), f"dict 键必须为 str，得到 {type(key).__name__}"
            _assert_json_clean(item)
        return
    raise AssertionError(f"非 JSON 原生类型：{type(value).__name__}")


class TestComponentTypeIdLexicon:
    """ComponentTypeId 词法（设计文档 §2.2 类型标识符族统一词法）。"""

    @pytest.mark.parametrize(
        "text",
        [
            "space.position",  # 设计文档 §3.3 示例
            "health",  # 单段
            "a",  # 最短
            "a1_b2",  # 数字/下划线
            "a.b.c.d",  # 多段
            "space.x_y.z9",
        ],
    )
    def test_valid_lexicon(self, text: str) -> None:
        assert COMPONENT_TYPE_ID_PATTERN.fullmatch(text)
        result = parse_component_type_id(text)
        assert type(result) is ComponentTypeId
        assert str(result) == text, "词法校验不得改写值（G1 稳定性）"

    @pytest.mark.parametrize(
        "text",
        [
            "",  # 空串
            "Space.position",  # 大写段首
            "space.Position",  # 大写段
            "1abc",  # 段以数字开头
            "a..b",  # 连续点
            ".space",  # 前导点
            "space.",  # 尾随点
            "space-position",  # 非法字符 '-'
            "space position",  # 非法字符空格
            "空间.position",  # 非 ASCII 段首
        ],
    )
    def test_invalid_lexicon(self, text: str) -> None:
        assert not COMPONENT_TYPE_ID_PATTERN.fullmatch(text)
        with pytest.raises(ValueError):
            parse_component_type_id(text)

    def test_non_string_input_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_component_type_id(123)  # type: ignore[arg-type]

    def test_typed_str_subclass_semantics(self) -> None:
        """决策 D-1 模式推广：typed str 子类——isinstance str、可哈希、str 语义保持。"""
        ct = ComponentTypeId("space.position")
        assert issubclass(ComponentTypeId, str)
        assert isinstance(ct, str)
        assert ct == "space.position"
        assert {ct: 1}  # dict 可用
        assert ct + "2" == "space.position2"


class TestComponentTypeIdPydantic:
    """ComponentTypeId 的 pydantic 类型保持（设计文档 §2.1 风险项兜底，与 T01 同根因）。"""

    class _CtEnvelope(BaseModel):
        ct: ComponentTypeId
        ct_opt: ComponentTypeId | None = None
        cts: list[ComponentTypeId] = []
        data_by_ct: dict[ComponentTypeId, int] = {}

    def test_accepts_plain_str_rebuilds_subclass(self) -> None:
        model = self._CtEnvelope.model_validate(
            {"ct": "space.position", "cts": ["a", "b.c"], "data_by_ct": {"x.y": 1}}
        )
        assert type(model.ct) is ComponentTypeId
        assert all(type(ct) is ComponentTypeId for ct in model.cts)
        assert all(type(k) is ComponentTypeId for k in model.data_by_ct)
        assert model.ct_opt is None

    def test_roundtrip_value_equal_and_type_preserved(self) -> None:
        model = self._CtEnvelope(
            ct=ComponentTypeId("space.position"),
            cts=[ComponentTypeId("a"), ComponentTypeId("b.c.d")],
            data_by_ct={ComponentTypeId("x.y"): 1},
        )
        dumped = model.model_dump(mode="json")
        # §0.2 铁律 2：typed 标识序列化为纯字符串（dict 键同样，§6.1 规则 3）
        assert type(dumped["ct"]) is str
        assert all(type(ct) is str for ct in dumped["cts"])
        assert all(type(k) is str for k in dumped["data_by_ct"])
        reloaded = self._CtEnvelope.model_validate(dumped)
        assert reloaded == model
        assert type(reloaded.ct) is ComponentTypeId
        assert all(type(ct) is ComponentTypeId for ct in reloaded.cts)
        assert all(type(k) is ComponentTypeId for k in reloaded.data_by_ct)

    def test_json_text_roundtrip(self) -> None:
        model = self._CtEnvelope(ct=ComponentTypeId("space.position"))
        text = model.model_dump_json(ensure_ascii=False)
        reloaded = self._CtEnvelope.model_validate_json(text)
        assert reloaded == model
        assert type(reloaded.ct) is ComponentTypeId


class TestE1RegistryConflict:
    """E1：registry 冲突——同 component_type 不同 schema 抛错；相同 schema 幂等。"""

    def test_idempotent_identical_schema(self) -> None:
        reg = ComponentRegistry()
        schema = ComponentSchema(component_type=ComponentTypeId("space.position"), version=2)
        reg.register(schema)
        reg.register(ComponentSchema(component_type=ComponentTypeId("space.position"), version=2))
        assert reg.get(ComponentTypeId("space.position")) == schema

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda s: ComponentSchema(component_type=s.component_type, version=s.version + 1),
            lambda s: ComponentSchema(component_type=s.component_type, description="不同描述"),
            lambda s: ComponentSchema(
                component_type=s.component_type, payload_model=_PositionModel
            ),
            lambda s: ComponentSchema(component_type=s.component_type, authority_domain="world"),
        ],
        ids=["version", "description", "payload_model", "authority_domain"],
    )
    def test_conflict_on_different_schema(self, mutate: Any) -> None:
        reg = ComponentRegistry()
        base = ComponentSchema(component_type=ComponentTypeId("space.position"))
        reg.register(base)
        with pytest.raises(ComponentConflictError):
            reg.register(mutate(base))

    def test_conflict_is_value_error_and_registry_unchanged(self) -> None:
        reg = ComponentRegistry()
        base = ComponentSchema(component_type=ComponentTypeId("space.position"), version=1)
        reg.register(base)
        with pytest.raises(ValueError):  # ComponentConflictError ⊂ ValueError
            reg.register(ComponentSchema(component_type=ComponentTypeId("space.position"), version=2))
        assert reg.get(ComponentTypeId("space.position")) == base, "冲突后注册表不得被污染"

    def test_get_returns_none_for_unregistered(self) -> None:
        reg = ComponentRegistry()
        assert reg.get(ComponentTypeId("never.registered")) is None


class TestE2UnknownComponentAndValidation:
    """E2：未知组件类型（D-8）与 validate_payload 的 schema 校验。"""

    def test_validate_payload_unregistered_passes(self) -> None:
        """D-8：未注册组件类型 ≠ 错误——validate_payload 放行任意不透明 JSON dict。"""
        reg = ComponentRegistry()
        reg.validate_payload(ComponentTypeId("unknown.module.ct"), {"任意": [1, 2, {"深": None}]})

    def test_validate_payload_registered_without_model_passes(self) -> None:
        """D-8：已注册但 payload_model is None = 不透明 JSON dict 存储，放行。"""
        reg = ComponentRegistry()
        reg.register(ComponentSchema(component_type=ComponentTypeId("opaque.ct")))
        reg.validate_payload(ComponentTypeId("opaque.ct"), {"a": "b"})

    def test_validate_payload_valid_data_ok(self) -> None:
        reg = ComponentRegistry()
        reg.register(
            ComponentSchema(
                component_type=ComponentTypeId("space.position"), payload_model=_PositionModel
            )
        )
        reg.validate_payload(ComponentTypeId("space.position"), {"x": 1.5, "y": -2})

    @pytest.mark.parametrize(
        "bad_data",
        [
            {"x": 1.5},  # 缺必填 y
            {"x": "不是数字", "y": 2},  # 类型错误
            {"x": 1, "y": 2, "z": 3},  # 未知字段（payload model extra=forbid）
        ],
        ids=["missing_required", "wrong_type", "extra_field"],
    )
    def test_validate_payload_rejects_invalid(self, bad_data: ComponentData) -> None:
        """E2"有 schema 时拒绝非法 payload"：ValidationError 原样传播。"""
        reg = ComponentRegistry()
        reg.register(
            ComponentSchema(
                component_type=ComponentTypeId("space.position"), payload_model=_PositionModel
            )
        )
        with pytest.raises(ValidationError):
            reg.validate_payload(ComponentTypeId("space.position"), bad_data)

    def test_entity_record_accepts_unregistered_component_type(self) -> None:
        """D-8 数据侧：EntityRecord 不持有 registry 引用——未注册组件类型数据可直接存储。"""
        rec = EntityRecord(
            entity_id=EntityId("ent_d8"),
            components={"completely.unregistered.ct": {"opaque": [1, 2, 3]}},
        )
        assert ComponentTypeId("completely.unregistered.ct") in rec.components


class TestE3FacadeReadonly:
    """E3：门面只读——深冻结视图不可写 + frozen 模型 + 无公共写 API（静态断言）。"""

    _MUTATOR_PREFIXES = (
        "set_",
        "add_",
        "append_",
        "insert_",
        "remove_",
        "update_",
        "replace_",
        "mutate_",
        "clear_",
        "del_",
    )

    def test_get_component_return_value_not_writable(self) -> None:
        view = EntityView._from_record(_sample_record(), Revision(812))
        comp = view.get_component(ComponentTypeId("space.position"))
        assert type(comp) is type(__import__("types").MappingProxyType({})), "必须返回 MappingProxyType 深冻结视图"
        with pytest.raises(TypeError):
            comp["x"] = 999  # type: ignore[index]

    def test_get_component_nested_readonly(self) -> None:
        view = EntityView._from_record(_sample_record(), Revision(812))
        comp = view.get_component(ComponentTypeId("custom.opaque"))
        assert comp is not None
        with pytest.raises(TypeError):
            comp["nested"]["deep"] = False  # type: ignore[index]
        # 组件数据里的 list 值被深冻结为 tuple（D-15：dict→proxy、list→tuple）
        grid = view.get_component(ComponentTypeId("space.position"))["grid"]
        assert type(grid) is tuple
        with pytest.raises(TypeError):
            grid[0] = 1  # type: ignore[index]

    def test_entity_view_frozen_blocks_assignment(self) -> None:
        view = EntityView._from_record(_sample_record(), Revision(812))
        with pytest.raises(FrozenInstanceError):
            view.entity_id = EntityId("ent_other")  # type: ignore[misc]

    def test_entity_record_frozen_blocks_assignment(self) -> None:
        rec = _sample_record()
        with pytest.raises((ValidationError, TypeError)):
            rec.entity_id = EntityId("ent_other")  # type: ignore[misc]
        with pytest.raises((ValidationError, TypeError)):
            rec.components = {}  # type: ignore[assignment]

    def test_no_public_mutator_api(self) -> None:
        """E3 静态断言：EntityRecord / EntityView 无公共 mutator 方法名。

        只扫描类**自身**声明的公共属性（``vars(cls)``）——继承自 pydantic 的
        schema API（如 ``update_forward_refs``）不属于状态写方法。WorldState 属
        T02（state.py），其同款断言由 T06 固化（设计文档 §7.2 E3）；此处覆盖
        T03 拥有的两个类型。
        """

        def public_mutators(cls: type) -> list[str]:
            return [
                name
                for name in vars(cls)
                if not name.startswith("_") and name.startswith(self._MUTATOR_PREFIXES)
            ]

        assert public_mutators(EntityRecord) == []
        assert public_mutators(EntityView) == []
        # ContractModel 的 frozen/extra 配置是"零公共写 API"的数据层基础（§0.1/§3.5）
        assert issubclass(EntityRecord, ContractModel)
        assert issubclass(EntityRef, ContractModel)
        assert ContractModel.model_config["frozen"] is True
        assert ContractModel.model_config["extra"] == "forbid"
        assert EntityRecord.model_config["frozen"] is True
        assert EntityRecord.model_config["extra"] == "forbid"
        assert EntityRef.model_config["frozen"] is True

    def test_entity_view_public_surface_is_identity_plus_two_queries(self) -> None:
        """门面公共面 = §3.2 字段 + component_types/get_component 两个只读方法。"""
        public_methods = {name for name in vars(EntityView) if not name.startswith("_")}
        assert public_methods == {"component_types", "get_component"}
        assert set(EntityView.__dataclass_fields__) == {
            "entity_id",
            "entity_class",
            "tags",
            "revision",
            "components",
        }

    def test_view_value_equality_and_unhashable_documented(self) -> None:
        """frozen dataclass 按值相等；含 MappingProxyType 成员 → 不可哈希（与含 dict
        的值对象同语义，docstring 已声明）。"""
        rec = _sample_record()
        view_a = EntityView._from_record(rec, Revision(812))
        view_b = EntityView._from_record(rec, Revision(812))
        assert view_a == view_b
        with pytest.raises(TypeError):
            hash(view_a)


class TestE4EntityIdUniqueness:
    """E4：EntityId 唯一——builder 助手显式拒绝重复 id；组件扫描结果正确。"""

    def test_build_entities_duplicate_id_raises(self) -> None:
        rec_a = EntityRecord(entity_id=EntityId("ent_dup"))
        rec_b = EntityRecord(entity_id=EntityId("ent_dup"))
        with pytest.raises(ValueError, match="重复 EntityId"):
            _build_entities([rec_a, rec_b])

    def test_build_entities_unique_ok(self) -> None:
        rec_a = EntityRecord(entity_id=EntityId("ent_a"))
        rec_b = EntityRecord(entity_id=EntityId("ent_b"))
        entities = _build_entities([rec_a, rec_b])
        assert list(entities) == [EntityId("ent_a"), EntityId("ent_b")]  # 插入顺序保持
        assert all(type(k) is EntityId for k in entities)

    def test_build_entities_empty(self) -> None:
        assert _build_entities([]) == {}

    def test_entity_ids_with_component_empty_mapping(self) -> None:
        assert _entity_ids_with_component({}, ComponentTypeId("space.position")) == ()

    def test_entity_ids_with_component_no_match(self) -> None:
        entities = _build_entities(
            [
                EntityRecord(entity_id=EntityId("ent_a"), components={"health.hp": {"hp": 3}}),
            ]
        )
        assert _entity_ids_with_component(entities, ComponentTypeId("space.position")) == ()

    def test_entity_ids_with_component_correct(self) -> None:
        entities = _build_entities(
            [
                EntityRecord(entity_id=EntityId("ent_a"), components={"space.position": {}}),
                EntityRecord(entity_id=EntityId("ent_b")),
                EntityRecord(entity_id=EntityId("ent_c"), components={"space.position": {}}),
            ]
        )
        assert _entity_ids_with_component(entities, ComponentTypeId("space.position")) == (
            EntityId("ent_a"),
            EntityId("ent_c"),
        )


class TestE5ReferenceIntegrity:
    """E5：引用完整性——EntityRef 是纯引用数据；缺失目标查询安全返回 None。

    "EntityRef 指向不存在 entity" 的 WorldState 级断言（``entity_view()`` 返回
    None）属 T02/T06 范围；此处固化 T03 侧：引用可无存在性校验地构造、视图
    查询对未挂载组件返回 None 而不抛未定义异常。
    """

    def test_entity_ref_is_pure_data_no_existence_check(self) -> None:
        ref = EntityRef(entity_id=EntityId("ent_missing"))
        assert ref.component_type is None
        assert ref.field_path is None
        ref2 = EntityRef(
            entity_id=EntityId("ent_missing"),
            component_type=ComponentTypeId("space.position"),
            field_path="x",
        )
        assert ref2.component_type == ComponentTypeId("space.position")
        assert ref2.field_path == "x"

    def test_view_get_component_missing_returns_none(self) -> None:
        rec = EntityRecord(entity_id=EntityId("ent_only_health"), components={"health.hp": {"hp": 3}})
        view = EntityView._from_record(rec, INITIAL_WORLD_REVISION)
        assert view.get_component(ComponentTypeId("space.position")) is None
        assert view.component_types() == (ComponentTypeId("health.hp"),)

    def test_view_of_empty_entity(self) -> None:
        view = EntityView._from_record(EntityRecord(entity_id=EntityId("ent_empty")), Revision(1))
        assert view.component_types() == ()
        assert view.get_component(ComponentTypeId("any.ct")) is None
        assert view.tags == ()
        assert view.entity_class is None

    def test_ref_component_type_strict_optional(self) -> None:
        """严格 Optional 语义（KBC-7 防线）：None 不得被改写为缺省/空值。"""
        ref = EntityRef(entity_id=EntityId("ent_ref"))
        dumped = ref.model_dump(mode="json")
        assert dumped["component_type"] is None
        assert dumped["field_path"] is None
        reloaded = EntityRef.model_validate(dumped)
        assert reloaded.component_type is None
        assert reloaded.field_path is None


class TestReducerOnlyDiscipline:
    """§3.5 纪律：零公共写 API（见 E3）+ 入口深拷贝 + _with_* 私有构造缝隙。"""

    def test_with_components_returns_new_instance(self) -> None:
        rec = _sample_record()
        rec2 = rec._with_components({"fresh.ct": {"a": 1}})
        assert rec2 is not rec
        assert rec2.components == {"fresh.ct": {"a": 1}}
        # self 不变
        assert set(rec.components) == {
            ComponentTypeId("space.position"),
            ComponentTypeId("custom.opaque"),
        }

    def test_with_components_preserves_identity_fields(self) -> None:
        rec = _sample_record()
        rec2 = rec._with_components({})
        assert rec2.entity_id == rec.entity_id
        assert type(rec2.entity_id) is EntityId
        assert rec2.entity_class == rec.entity_class
        assert rec2.tags == rec.tags
        assert rec2.created_revision == rec.created_revision
        assert type(rec2.created_revision) is Revision

    def test_with_components_entry_deep_copy(self) -> None:
        """纪律 2：调用方持有的可变 Mapping 不得别名进新记录（顶层与嵌套都重建）。"""
        rec = _sample_record()
        incoming: dict[str, Any] = {"space.position": {"x": 5, "inner": {"z": 3}}, "fresh.ct": {"a": [1, 2]}}
        rec2 = rec._with_components(incoming)  # type: ignore[arg-type]
        assert rec2.components[ComponentTypeId("space.position")] is not incoming["space.position"]
        incoming["space.position"]["x"] = 999
        incoming["space.position"]["inner"]["z"] = 42
        incoming["fresh.ct"]["a"].append(9)
        comp = rec2.components[ComponentTypeId("space.position")]
        assert comp["x"] == 5
        assert comp["inner"]["z"] == 3
        assert list(rec2.components[ComponentTypeId("fresh.ct")]["a"]) == [1, 2]

    def test_with_components_whole_replacement_not_partial_override(self) -> None:
        """KBC-4 防线：整体替换——旧组件不残留（不提供部分覆写）。"""
        rec = _sample_record()
        rec2 = rec._with_components({"only.new": {}})
        assert set(rec2.components) == {ComponentTypeId("only.new")}

    def test_with_components_accepts_unregistered_type(self) -> None:
        """D-8：未注册组件类型的数据同样可进入记录（不透明 JSON dict）。"""
        rec = _sample_record()
        rec2 = rec._with_components({"unregistered.ct": {"任意": None}})
        assert ComponentTypeId("unregistered.ct") in rec2.components

    def test_from_record_zero_alias(self) -> None:
        """KBC-3 防线：视图与 record 零别名——构造后 record 侧变化不影响已建视图。"""
        rec = _sample_record()
        view = EntityView._from_record(rec, rec.created_revision)
        rec.components[ComponentTypeId("space.position")]["x"] = 12345  # 浅冻结模型的咨询性可变区
        assert view.get_component(ComponentTypeId("space.position"))["x"] == 1.5
        assert view.revision == rec.created_revision
        assert type(view.revision) is Revision
        assert view.tags == ("ally", "村庄守卫")
        assert type(view.tags) is tuple


class TestJsonRoundtrip:
    """JSON round-trip（设计文档 §0.2 铁律 / §6.1）：值相等 + 类型保持 + JSON 纯净。"""

    def test_entity_record_roundtrip_full(self) -> None:
        rec = _sample_record()
        dumped = rec.model_dump(mode="json")
        _assert_json_clean(dumped)
        # §0.2 铁律 2：Revision 纯整数、typed ID 纯字符串（含 dict 键）
        assert type(dumped["created_revision"]) is int
        assert dumped["created_revision"] == 812
        assert type(dumped["entity_id"]) is str
        assert all(type(k) is str for k in dumped["components"])
        # Unicode 一等公民（§6.1 规则 2）
        assert dumped["tags"][1] == "村庄守卫"
        reloaded = EntityRecord.model_validate(dumped)
        assert reloaded == rec
        assert type(reloaded.entity_id) is EntityId
        assert type(reloaded.created_revision) is Revision
        assert all(type(k) is ComponentTypeId for k in reloaded.components)
        assert reloaded.components == rec.components

    def test_entity_record_json_text_roundtrip(self) -> None:
        rec = _sample_record()
        text = rec.model_dump_json(ensure_ascii=False)
        assert "村庄守卫" in text, "ensure_ascii=False：中文不得被转义"
        reloaded = EntityRecord.model_validate_json(text)
        assert reloaded == rec
        assert type(reloaded.entity_id) is EntityId
        assert type(reloaded.components[ComponentTypeId("space.position")]) is dict

    def test_entity_record_defaults(self) -> None:
        rec = EntityRecord(entity_id=EntityId("ent_min"))
        assert rec.entity_class is None
        assert rec.tags == []
        assert rec.components == {}
        assert rec.created_revision == INITIAL_WORLD_REVISION

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"bogus_field": 1},  # EntityRecord 未知字段
        ],
        ids=["record_unknown_field"],
    )
    def test_entity_record_extra_forbid(self, kwargs: dict[str, Any]) -> None:
        """J2 口径：注入未知字段 → 校验失败（契约冻结的程序化守卫）。"""
        with pytest.raises(ValidationError):
            EntityRecord(entity_id=EntityId("ent_forbid"), **kwargs)  # type: ignore[call-overload]

    def test_entity_record_missing_required(self) -> None:
        with pytest.raises(ValidationError):
            EntityRecord.model_validate({})  # type: ignore[arg-type]

    def test_entry_deep_copy_isolation(self) -> None:
        """J3 口径：构造后修改传入的原始 dict → 记录不受影响（边界深拷贝，纪律 2）。"""
        source: dict[str, Any] = {"x": 1, "y": 2, "nested": {"z": 3}}
        rec = EntityRecord.model_validate(
            {"entity_id": "ent_iso", "components": {"space.position": source}}
        )
        source["x"] = 999
        source["nested"]["z"] = 42
        comp = rec.components[ComponentTypeId("space.position")]
        assert comp["x"] == 1
        assert comp["nested"]["z"] == 3
        assert comp is not source

    def test_entity_ref_roundtrip_full(self) -> None:
        ref = EntityRef(
            entity_id=EntityId("ent_ref"),
            component_type=ComponentTypeId("space.position"),
            field_path="x",
        )
        dumped = ref.model_dump(mode="json")
        _assert_json_clean(dumped)
        assert type(dumped["entity_id"]) is str
        assert type(dumped["component_type"]) is str
        reloaded = EntityRef.model_validate(dumped)
        assert reloaded == ref
        assert type(reloaded.entity_id) is EntityId
        assert type(reloaded.component_type) is ComponentTypeId

    def test_entity_ref_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            EntityRef(entity_id=EntityId("ent_ref"), unknown="x")  # type: ignore[call-overload]

    def test_component_schema_frozen(self) -> None:
        """ComponentSchema 为 frozen dataclass（§0.1）：字段不可再赋值。"""
        schema = ComponentSchema(component_type=ComponentTypeId("space.position"), version=2)
        with pytest.raises(FrozenInstanceError):
            schema.version = 3  # type: ignore[misc]


class TestImportBoundary:
    """§0.3 import 边界：components.py / entity.py 只 import 标准库、pydantic 与同包内 src.engine_v2。"""

    _STDLIB = {
        "__future__",
        "re",
        "dataclasses",
        "types",
        "collections",
        "typing",
        "enum",
        "uuid",
    }

    @pytest.mark.parametrize(
        "module",
        [components_module, entity_module],
        ids=["components", "entity"],
    )
    def test_only_whitelisted_imports(self, module: Any) -> None:
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        violations: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root == "src":
                        assert alias.name.startswith("src.engine_v2"), (
                            f"同包 import 必须指向 src.engine_v2，得到 {alias.name}"
                        )
                    elif root not in self._STDLIB | {"pydantic"}:
                        violations.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                root = node.module.split(".")[0]
                if root == "src":
                    assert node.module.startswith("src.engine_v2"), (
                        f"同包 import 必须指向 src.engine_v2，得到 {node.module}"
                    )
                elif root not in self._STDLIB | {"pydantic"}:
                    violations.add(node.module)
        assert not violations, f"白名单外 import：{violations}"
