"""P1-T01 单元测试：ID 原语（设计文档 §7.1 R1–R4 + §2.1 类型保持 / round-trip）。

覆盖：

- R1 ID 生成唯一性（每种 ``new_*_id()`` 连续 ≥10⁴ 个，无碰撞）与前缀/词法正则匹配；
- R2 ID 稳定性：round-trip 前后 ID 值逐字相等；类型保持（typed str 子类，
  设计文档 §2.1 风险项——pydantic 类型保持兜底已由本任务实现，并在此验证）；
- R3 ``parse_id`` 合法/非法（错误前缀、空串、大写、非法字符）分别通过与抛
  ``ValueError``；
- R4 ``ProducerId`` 词法：名字型语法校验，authority 配置示例
  （``interaction.lock_system`` 等，Spec §17.1 / 决策 D-4）可通过；
- JSON round-trip：typed ID 序列化为纯字符串（§0.2 铁律）、dict 键类型重建
  （设计文档 §6.1 规则 3）。

全部用例无网络、无 LLM、无 API key（Spec §47 Phase 1 验收）。
"""

from __future__ import annotations

from typing import Annotated, Any, Callable

import pytest
from pydantic import BaseModel, BeforeValidator

import src.engine_v2.core.ids as ids_module
from src.engine_v2.core.ids import (
    FACTORY_BODY_PATTERN,
    PREFIX_BODY_PATTERN,
    PREFIX_TO_KIND,
    PRODUCER_ID_PATTERN,
    ActionInstanceId,
    CascadeId,
    EffectId,
    EntityId,
    EventId,
    ObservationId,
    ProducerId,
    ScheduledEntryId,
    TraceRecordId,
    TransactionId,
    new_action_instance_id,
    new_cascade_id,
    new_effect_id,
    new_entity_id,
    new_event_id,
    new_observation_id,
    new_scheduled_entry_id,
    new_trace_record_id,
    new_transaction_id,
    parse_id,
)

# (类型类, 前缀, 工厂) —— 以设计文档 §2.2 表为准。
ID_SPECS: tuple[tuple[type, str, Callable[[], str]], ...] = (
    (EntityId, "ent_", new_entity_id),
    (EffectId, "eff_", new_effect_id),
    (EventId, "evt_", new_event_id),
    (TransactionId, "txn_", new_transaction_id),
    (CascadeId, "csc_", new_cascade_id),
    (ObservationId, "obs_", new_observation_id),
    (ActionInstanceId, "act_", new_action_instance_id),
    (ScheduledEntryId, "sch_", new_scheduled_entry_id),
    (TraceRecordId, "trc_", new_trace_record_id),
)
ID_SPEC_IDS = [cls.__name__ for cls, _, _ in ID_SPECS]


class _IdEnvelope(BaseModel):
    """测试专用信封模型：验证 ID 字段的类型保持与 JSON round-trip。

    T06（P1-T06）将以完整契约模型固化同款断言（设计文档 §8.1），此处为 T01
    自测口径，仅依赖 pydantic 公共 API。
    """

    entity_id: EntityId
    effect_id: EffectId
    event_id: EventId
    transaction_id: TransactionId
    cascade_id: CascadeId
    observation_id: ObservationId
    action_instance_id: ActionInstanceId
    scheduled_entry_id: ScheduledEntryId
    trace_record_id: TraceRecordId
    producer_id: ProducerId
    ids_by_entity: dict[EntityId, int] = {}


_ID_FIELD_ORDER: tuple[tuple[str, type], ...] = (
    ("entity_id", EntityId),
    ("effect_id", EffectId),
    ("event_id", EventId),
    ("transaction_id", TransactionId),
    ("cascade_id", CascadeId),
    ("observation_id", ObservationId),
    ("action_instance_id", ActionInstanceId),
    ("scheduled_entry_id", ScheduledEntryId),
    ("trace_record_id", TraceRecordId),
    ("producer_id", ProducerId),
)


class TestR1Generation:
    """R1：ID 生成唯一性（≥10⁴ 无碰撞）、前缀与词法正则匹配。"""

    @pytest.mark.parametrize(("cls", "prefix", "factory"), ID_SPECS, ids=ID_SPEC_IDS)
    def test_generation_unique_prefix_and_lexicon(self, cls: type, prefix: str, factory: Callable[[], str]) -> None:
        generated = {factory() for _ in range(10_000)}
        assert len(generated) == 10_000, f"{cls.__name__}：连续生成 10⁴ 个出现碰撞"
        for value in generated:
            assert type(value) is cls, f"{cls.__name__}：工厂必须返回精确类型"
            assert value.startswith(prefix)
            body = value[len(prefix):]
            assert FACTORY_BODY_PATTERN.fullmatch(body), (
                f"{cls.__name__}：工厂正文须为 32 位小写 hex，得到 {body!r}"
            )
            assert PREFIX_BODY_PATTERN.fullmatch(body)

    def test_prefixes_match_design_table(self) -> None:
        """ID 前缀属 public contract（G1），与设计文档 §2.2 表逐一对应。"""
        for cls, expected_prefix, _ in ID_SPECS:
            assert cls.PREFIX == expected_prefix
        assert set(PREFIX_TO_KIND) == {prefix for _, prefix, _ in ID_SPECS}
        assert set(PREFIX_TO_KIND.values()) == {cls.__name__ for cls, _, _ in ID_SPECS}
        # 前缀互斥（无一个前缀是另一个的前缀），保证 parse_id 匹配无歧义
        prefixes = list(PREFIX_TO_KIND)
        for a in prefixes:
            for b in prefixes:
                if a != b:
                    assert not b.startswith(a)

    def test_producer_id_has_no_random_prefix(self) -> None:
        """决策 D-4：ProducerId 为名字型，无随机段/随机前缀。"""
        assert ProducerId.PREFIX == ""


class TestR2StabilityAndTypePreservation:
    """R2：ID 稳定性（round-trip 值逐字相等）+ 类型保持（设计文档 §2.1）。"""

    @staticmethod
    def _sample() -> _IdEnvelope:
        return _IdEnvelope(
            entity_id=new_entity_id(),
            effect_id=new_effect_id(),
            event_id=new_event_id(),
            transaction_id=new_transaction_id(),
            cascade_id=new_cascade_id(),
            # Spec §9 / 设计文档 §2.2 示例值：确定性构造合法
            observation_id=ObservationId("obs_991"),
            action_instance_id=new_action_instance_id(),
            scheduled_entry_id=new_scheduled_entry_id(),
            trace_record_id=new_trace_record_id(),
            # Spec §17.1 / 决策 D-4：名字型 producer
            producer_id=ProducerId("policy.alice"),
            ids_by_entity={new_entity_id(): 1, new_entity_id(): 2},
        )

    def test_roundtrip_value_equal_and_type_preserved(self) -> None:
        env = self._sample()
        dumped = env.model_dump(mode="json")

        # §0.2 JSON-friendly 铁律 2：typed ID 序列化为纯字符串（带前缀，无对象包装）
        for field_name, _ in _ID_FIELD_ORDER:
            assert type(dumped[field_name]) is str, (
                f"{field_name}：JSON 序列化必须是纯 str，得到 {type(dumped[field_name])}"
            )
        assert dumped["producer_id"] == "policy.alice"
        # dict 键序列化为纯字符串（设计文档 §6.1 规则 3）
        assert all(type(k) is str for k in dumped["ids_by_entity"])

        # round-trip 判据（§0.2 规则 5）+ 类型保持（§2.1 / R2）
        reloaded = _IdEnvelope.model_validate(dumped)
        assert reloaded == env, "round-trip 后值必须相等"
        for field_name, cls in _ID_FIELD_ORDER:
            assert type(getattr(reloaded, field_name)) is cls, (
                f"{field_name}：model_validate 后类型未保持（期望 {cls.__name__}，"
                f"得到 {type(getattr(reloaded, field_name)).__name__}）"
            )
        # 逐字相等（G1 "public IDs stable"：round-trip 不得改写）
        for field_name, _ in _ID_FIELD_ORDER:
            assert str(getattr(reloaded, field_name)) == str(getattr(env, field_name))
        assert str(reloaded.observation_id) == "obs_991"
        # dict 键类型重建为 EntityId（§6.1 规则 3 / §2.1）
        assert all(type(k) is EntityId for k in reloaded.ids_by_entity)
        assert reloaded.ids_by_entity == env.ids_by_entity

    def test_json_text_roundtrip(self) -> None:
        """JSON 文本级 round-trip：model_dump_json → model_validate_json。"""
        env = self._sample()
        text = env.model_dump_json(ensure_ascii=False)
        reloaded = _IdEnvelope.model_validate_json(text)
        assert reloaded == env
        assert type(reloaded.entity_id) is EntityId
        assert type(reloaded.producer_id) is ProducerId

    def test_deterministic_construction_allowed(self) -> None:
        """设计文档 §2.2 通用规则：测试可用确定性构造（直接 EntityId("ent_test_1")）。"""
        eid = EntityId("ent_test_1")
        assert type(eid) is EntityId
        assert isinstance(eid, str)
        assert eid == "ent_test_1"
        oid = ObservationId("obs_991")  # Spec §9 示例值
        assert type(oid) is ObservationId

    def test_fallback_annotated_before_validator_pattern(self) -> None:
        """设计文档 §2.1 字面兜底形态 ``Annotated[EntityId, BeforeValidator(...)]`` 可用。

        本仓 pydantic 2.13 对裸 str 子类注解不再生成 schema，T01 的类型保持
        兜底实现为 ``__get_pydantic_core_schema__``（校验链末端重建）；本用例
        验证设计文档的字面形态在该兜底之上同样可用且契约语义不变
        （接受原生 str、重建子类实例、JSON 纯字符串）。
        """

        class _FallbackModel(BaseModel):
            eid: Annotated[
                EntityId,
                BeforeValidator(
                    lambda value: value if isinstance(value, EntityId) else EntityId(value)
                ),
            ]

        model = _FallbackModel.model_validate({"eid": "ent_fb"})
        assert type(model.eid) is EntityId
        assert model.model_dump(mode="json") == {"eid": "ent_fb"}
        reloaded = _FallbackModel.model_validate(model.model_dump(mode="json"))
        assert type(reloaded.eid) is EntityId
        assert reloaded.eid == model.eid


class TestR3ParseId:
    """R3：parse_id 合法通过与非法抛 ValueError（错误前缀、空串、大写、非法字符）。"""

    @pytest.mark.parametrize(
        ("text", "expected_kind"),
        [
            ("ent_test_1", "EntityId"),
            ("ent_authoring_alice", "EntityId"),  # 确定性命名 ID（P5 loader 保证不冲突）
            ("eff_" + "0" * 32, "EffectId"),
            ("evt_" + "f" * 32, "EventId"),
            ("txn_" + "1234567890abcdef" * 2, "TransactionId"),
            ("csc_" + "a" * 32, "CascadeId"),
            ("obs_991", "ObservationId"),  # Spec §9 示例
            ("act_" + "b" * 32, "ActionInstanceId"),
            ("sch_" + "c" * 32, "ScheduledEntryId"),
            ("trc_" + "d" * 32, "TraceRecordId"),
            ("policy.alice", "ProducerId"),
            ("dynamics.rigid_body", "ProducerId"),
            ("rule.lock_system", "ProducerId"),
            ("dev.console", "ProducerId"),
        ],
    )
    def test_valid(self, text: str, expected_kind: str) -> None:
        assert parse_id(text) == (expected_kind, text)

    @pytest.mark.parametrize(
        "text",
        [
            "",  # 空串
            "ent_",  # 前缀后空正文
            "ENT_abc",  # 大写前缀
            "ent_ABC",  # 大写正文
            "ent_ab-c",  # 非法字符 '-'
            "ent_ab.c",  # 前缀型 ID 不允许点（点仅限 ProducerId）
            "obs_991!",  # 非法字符 '!'
            "trc_x y",  # 非法字符空格
            "a..b",  # 名字型连续点
            ".abc",  # 名字型前导点
            "abc.",  # 名字型尾点
        ],
    )
    def test_invalid(self, text: str) -> None:
        with pytest.raises(ValueError):
            parse_id(text)

    def test_non_string_input_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_id(123)  # type: ignore[arg-type]

    @pytest.mark.parametrize(("cls", "prefix", "factory"), ID_SPECS, ids=ID_SPEC_IDS)
    def test_factory_output_roundtrips_through_parse(self, cls: type, prefix: str, factory: Callable[[], str]) -> None:
        value = factory()
        assert parse_id(str(value)) == (cls.__name__, str(value))

    def test_prefix_takes_precedence_over_producer_name(self) -> None:
        """以已知前缀开头的字符串按前缀型 ID 判定（即使它同时是合法 ProducerId 名字）。"""
        kind, value = parse_id("act_deadbeefdeadbeefdeadbeefdeadbeef")
        assert kind == "ActionInstanceId"
        assert value == "act_deadbeefdeadbeefdeadbeefdeadbeef"


class TestR4ProducerIdLexicon:
    """R4：ProducerId 词法——名字型语法校验 + authority 配置示例（Spec §17.1）。"""

    @pytest.mark.parametrize(
        "name",
        [
            # 设计文档 §2.2 / 决策 D-4 示例
            "policy.alice",
            "dynamics.rigid_body",
            "rule.lock_system",
            "dev.console",
            # Spec §17.1 authority 配置 writer 名字示例
            "interaction.lock_system",
            "llm_world_dynamics",
            # 边界词法
            "a",
            "a1_b2",
            "a.b.c.d",
        ],
    )
    def test_valid_names(self, name: str) -> None:
        assert PRODUCER_ID_PATTERN.fullmatch(name)
        assert parse_id(name) == ("ProducerId", name)
        instance = ProducerId(name)
        assert type(instance) is ProducerId
        assert isinstance(instance, str)
        assert instance == name

    @pytest.mark.parametrize(
        "name",
        [
            "Policy.alice",  # 大写首段
            "policy.Alice",  # 大写段
            "policy..alice",  # 连续点
            ".policy",  # 前导点
            "policy.",  # 尾点
            "policy alice",  # 空格
            "policy-alice",  # 连字符
            "",  # 空
            "policy.alice.",  # 尾点（多段）
        ],
    )
    def test_invalid_names(self, name: str) -> None:
        assert not PRODUCER_ID_PATTERN.fullmatch(name)
        with pytest.raises(ValueError):
            parse_id(name)


class TestImportBoundaryAndBasics:
    """基础结构守卫：typed str 子类形态（决策 D-1）与白名单 import。"""

    def test_ids_are_typed_str_subclasses(self) -> None:
        for cls, prefix, _ in ID_SPECS:
            assert issubclass(cls, str)
            instance: Any = cls(prefix + "x" * 32)
            assert isinstance(instance, str)
            # str 语义保持（可拼接、可哈希、dict 可用）
            assert (instance + "_suffix") == f"{prefix}{'x' * 32}_suffix"
            assert {instance: 1}
        assert issubclass(ProducerId, str)

    def test_only_stdlib_and_pydantic_imported(self) -> None:
        """§0.3 import 边界：ids.py 只 import 标准库与 pydantic（AST 静态检查）。"""
        import ast
        from pathlib import Path

        path = Path(ids_module.__file__)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
        stdlib = {"__future__", "re", "uuid", "typing"}
        assert roots <= stdlib | {"pydantic"}, f"发现白名单外 import：{roots}"
