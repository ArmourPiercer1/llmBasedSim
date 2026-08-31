"""P6-W4 ``prompts/assembler.py`` 单测（SOT §3.10 + §6.1 L817，恰 12 个平铺函数）。

覆盖项（按 §6.1 L817 行逐项 1:1）：

1. ``test_context_variables_closed_set``：CONTEXT_VARIABLES == 13 字段名精确集
   （frozenset 相等 + 逐名成员断言 + 计数）；
2. ``test_context_value_unauthorized_null``：global_entity_views=None（未授权）
   → ``"null"`` 字符串（不泄漏）；
3. ``test_context_value_serialization_caliber``：dict 字段 → sort_keys + 紧凑
   separators 字节级字符串比较（与 core serialization 同族口径）；
4. ``test_context_value_unsupported``：13 名外 → None（调用方发 UNSUPPORTED）；
5. ``test_l0_nonempty_zero_names``：L0 非空 + 12 名双词边界零命中；
6. ``test_l1_render_surface``：game_policy 文档渲染进 L1 段（overridable=True、
   source=policy_id）；
7. ``test_l2_first_id_same_scope``：character_scene 渲染 + 同 scope 两条
   casefold 字典序首 id 胜；
8. ``test_l3_full_13_block``：L3 全量 13 名块（全在、sorted 序、未授权
   global_entity_views → ``"null"`` 字符串值）；
9. ``test_l4_empty_segment``：L4 空段（layer=L4_UNTRUSTED、text=""、
   overridable=False、source="runtime"）；
10. ``test_flatten_order_markers``：压平序 + 分隔标记公式字节级（L0 居首、
    L1-L4 各前置本层标记，5 段序 L0→L4）+ prompt_metadata_ref；
11. ``test_error_diagnostic_package_none``：L1 模板未声明变量 → package None
    + error 级诊断；
12. ``test_token_estimate_caliber``：divisor=4.0 → max(0, ceil(len/4)) 数值
    断言 + divisor=0.4 → ValueError + package.token_estimate 自洽。

纪律（SOT §6.1/§6.2 + AD-8）：平铺函数、自足无 conftest、零真实网络、确定性
（双跑字节相等）。
"""

from __future__ import annotations

import json
import re

from src.engine_v2.content.schemas import PromptPolicy
from src.engine_v2.core.context_provider import ActorDecisionContext
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.revision import Revision
from src.engine_v2.prompts.assembler import (
    CONTEXT_VARIABLES,
    L0_CONTRACT_TEMPLATE,
    CharDivisorTokenEstimator,
    PromptLayer,
    assemble_prompt,
    context_variable_value,
)
from src.engine_v2.prompts.registry import TemplateStore

# —— 12 名 K8 自扫描（拼接构造，文件自身扫描零命中）——
_K8_NAMES: tuple[str, ...] = (
    "ope" + "nai",  # 供应商侧通用 wire 形状
    "anthro" + "pic",
    "lang" + "chain",
    "lite" + "ll" + "m",
    "olla" + "ma",
    "gem" + "ini",
    "g" + "pt",
    "clau" + "de",
    "ll" + "m",
    "pro" + "vider",
    "api" + "_key",
    "base" + "_url",
)

_EXPECTED_CONTEXT_VARS: frozenset[str] = frozenset(
    {
        "actor_id",
        "tick",
        "base_world_revision",
        "wake_reason",
        "self_view",
        "visible_entities",
        "local_entity_views",
        "global_entity_views",
        "observations",
        "knowledge",
        "memory",
        "candidate_actions",
        "granted_capabilities",
    }
)


def _k8_hits(text: str) -> list[str]:
    """casefold + 双词边界 12 名自扫描，返回命中的名单（应为空）。"""
    folded = text.casefold()
    return [n for n in _K8_NAMES if re.search(r"\b" + re.escape(n) + r"\b", folded)]


def _make_context(*, tick: int = 7, base: int = 3, global_views: object = None) -> ActorDecisionContext:
    """JSON-clean 13 字段 context（全字段可 JSON 序列化，供 L3 全量块）。"""
    return ActorDecisionContext(
        actor_id=EntityId("ent_alice"),
        tick=tick,
        base_world_revision=Revision(base),
        wake_reason="wake_test",
        self_view={"hp": 10, "name": "alice"},
        visible_entities=("ent_bob",),
        local_entity_views={},
        global_entity_views=global_views,  # type: ignore[arg-type]
        observations=(),
        knowledge=None,
        memory=("m1",),
        candidate_actions=("attack",),
        granted_capabilities=("cap.attack",),
    )


def _make_store(tmp_path, files: dict[str, str], policies: tuple[PromptPolicy, ...]) -> TemplateStore:
    """建临时项目 prompts/ 目录 + 写模板文件 + 装载 TemplateStore。"""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (prompts_dir / name).write_text(content, encoding="utf-8")
    return TemplateStore(project_root=tmp_path, policies=policies)


def test_context_variables_closed_set() -> None:
    """1) CONTEXT_VARIABLES == 13 字段名精确集（K4 天花板封闭供给集）。"""
    assert CONTEXT_VARIABLES == _EXPECTED_CONTEXT_VARS
    assert len(CONTEXT_VARIABLES) == 13
    for name in _EXPECTED_CONTEXT_VARS:
        assert name in CONTEXT_VARIABLES


def test_context_value_unauthorized_null() -> None:
    """2) global_entity_views 未授权（None）→ ``"null"`` 字符串（不泄漏）。"""
    ctx = _make_context(global_views=None)
    assert context_variable_value(ctx, "global_entity_views") == "null"


def test_context_value_serialization_caliber() -> None:
    """3) 序列化口径：dict 字段 → sort_keys + 紧凑 separators 字节级相等。"""
    ctx = _make_context()
    expected = json.dumps({"hp": 10, "name": "alice"}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert expected == '{"hp":10,"name":"alice"}'
    assert context_variable_value(ctx, "self_view") == expected
    # 标量字段口径
    assert context_variable_value(ctx, "tick") == "7"
    assert context_variable_value(ctx, "knowledge") == "null"


def test_context_value_unsupported() -> None:
    """4) 13 名外变量 → None（调用方发 VARIABLE_UNSUPPORTED，显式拒绝）。"""
    ctx = _make_context()
    assert context_variable_value(ctx, "not_a_variable") is None
    assert context_variable_value(ctx, "global_entity_viewz") is None


def test_l0_nonempty_zero_names() -> None:
    """5) L0 契约层模板：非空 + 12 名双词边界零命中。"""
    assert L0_CONTRACT_TEMPLATE.strip() != ""
    assert _k8_hits(L0_CONTRACT_TEMPLATE) == []


def test_l1_render_surface(tmp_path) -> None:
    """6) L1 渲染面：game_policy 文档渲染进 L1 段（overridable、source）。"""
    store = _make_store(
        tmp_path,
        files={"game.md": "the tick is {{tick}}"},
        policies=(PromptPolicy(id="pol_game", scope="game_policy", template_ref="prompts/game.md", variables=("tick",)),),
    )
    result = assemble_prompt(_make_context(), store, CharDivisorTokenEstimator(), capability="cap.attack")
    assert result.package is not None
    pkg = result.package
    # L0 段
    l0 = pkg.layers[0]
    assert l0.layer is PromptLayer.L0_ENGINE_CONTRACT
    assert l0.source == "engine"
    assert l0.overridable is False
    assert l0.text == L0_CONTRACT_TEMPLATE
    # L1 段
    l1 = pkg.layers[1]
    assert l1.layer is PromptLayer.L1_GAME_POLICY
    assert l1.source == "pol_game"
    assert l1.overridable is True
    assert l1.text == "the tick is 7"


def test_l2_first_id_same_scope(tmp_path) -> None:
    """7) L2 渲染面 + 同 scope 两条 casefold 字典序首 id 胜（无诊断）。"""
    store = _make_store(
        tmp_path,
        files={"zeta.md": "zeta {{tick}}", "alpha.md": "alpha {{tick}}"},
        policies=(
            PromptPolicy(id="zeta_scene", scope="character_scene", template_ref="prompts/zeta.md", variables=("tick",)),
            PromptPolicy(id="alpha_scene", scope="character_scene", template_ref="prompts/alpha.md", variables=("tick",)),
        ),
    )
    result = assemble_prompt(_make_context(), store, CharDivisorTokenEstimator(), capability="cap.attack")
    assert result.package is not None
    l2 = result.package.layers[2]
    assert l2.layer is PromptLayer.L2_CHARACTER_SCENE
    assert l2.source == "alpha_scene"  # casefold 字典序首
    assert l2.overridable is True
    assert l2.text == "alpha 7"
    # 同 scope 多条 = 无诊断（确定性兜底）
    assert result.diagnostics == ()


def test_l3_full_13_block(tmp_path) -> None:
    """8) L3 全量 13 名块：全在、sorted 序、未授权 global_entity_views → "null"。"""
    store = _make_store(tmp_path, files={}, policies=())
    result = assemble_prompt(_make_context(global_views=None), store, CharDivisorTokenEstimator(), capability="cap.attack")
    assert result.package is not None
    l3 = result.package.layers[3]
    assert l3.layer is PromptLayer.L3_RUNTIME_CONTEXT
    assert l3.source == "runtime"
    assert l3.overridable is False
    block_text = l3.text[l3.text.index("{") :]  # 去掉标题行，取 JSON 块
    block = json.loads(block_text)
    assert set(block.keys()) == CONTEXT_VARIABLES
    assert list(block.keys()) == sorted(CONTEXT_VARIABLES)
    assert block["global_entity_views"] == "null"  # 未授权 → "null" 字符串值
    assert block["tick"] == "7"


def test_l4_empty_segment(tmp_path) -> None:
    """9) L4 空段：layer=L4_UNTRUSTED、text=""、overridable=False、source="runtime"。"""
    store = _make_store(tmp_path, files={}, policies=())
    result = assemble_prompt(_make_context(), store, CharDivisorTokenEstimator(), capability="cap.attack")
    assert result.package is not None
    l4 = result.package.layers[4]
    assert l4.layer is PromptLayer.L4_UNTRUSTED
    assert l4.text == ""
    assert l4.overridable is False
    assert l4.source == "runtime"


def test_flatten_order_markers(tmp_path) -> None:
    """10) 压平序 + 分隔标记公式字节级（L0 居首，L1-L4 各前置本层标记）。"""
    store = _make_store(
        tmp_path,
        files={"game.md": "G{{tick}}", "scene.md": "S{{tick}}"},
        policies=(
            PromptPolicy(id="pol_g", scope="game_policy", template_ref="prompts/game.md", variables=("tick",)),
            PromptPolicy(id="pol_s", scope="character_scene", template_ref="prompts/scene.md", variables=("tick",)),
        ),
    )
    result = assemble_prompt(_make_context(), store, CharDivisorTokenEstimator(), capability="cap.attack")
    assert result.package is not None
    pkg = result.package
    assert len(pkg.layers) == 5
    assert [s.layer for s in pkg.layers] == [
        PromptLayer.L0_ENGINE_CONTRACT,
        PromptLayer.L1_GAME_POLICY,
        PromptLayer.L2_CHARACTER_SCENE,
        PromptLayer.L3_RUNTIME_CONTEXT,
        PromptLayer.L4_UNTRUSTED,
    ]
    expected = L0_CONTRACT_TEMPLATE
    for seg in pkg.layers[1:]:
        expected += "\n\n<!-- LAYER:" + seg.layer.name + " -->\n" + seg.text
    assert pkg.text == expected
    assert pkg.prompt_metadata_ref == "prompt://ent_alice:7:3"
    assert pkg.actor_id == "ent_alice"
    assert pkg.logical_role == "cap.attack"
    assert pkg.base_revision == Revision(3)


def test_error_diagnostic_package_none(tmp_path) -> None:
    """11) error 级诊断 → package None（L1 模板未声明变量，显式失败）。"""
    store = _make_store(
        tmp_path,
        files={"bad.md": "x {{ghost}} y"},
        policies=(PromptPolicy(id="pol_bad", scope="game_policy", template_ref="prompts/bad.md", variables=()),),
    )
    result = assemble_prompt(_make_context(), store, CharDivisorTokenEstimator(), capability="cap.attack")
    assert result.package is None
    codes = [d.code for d in result.diagnostics]
    assert "LLMSIM_PROMPT_UNDECLARED_VARIABLE" in codes
    assert any(d.severity.value == "error" for d in result.diagnostics)


def test_token_estimate_caliber(tmp_path) -> None:
    """12) token_estimate 口径：ceil(len/4) + divisor<0.5 → ValueError。"""
    est = CharDivisorTokenEstimator(divisor=4.0)
    assert est.estimate("a" * 10) == 3  # ceil(10/4)=3
    assert est.estimate("a" * 8) == 2
    assert est.estimate("") == 0
    assert CharDivisorTokenEstimator().divisor == 4.0
    try:
        CharDivisorTokenEstimator(divisor=0.4)
        assert False, "divisor<0.5 必须 ValueError"
    except ValueError:
        pass
    # package.token_estimate 自洽
    store = _make_store(tmp_path, files={}, policies=())
    result = assemble_prompt(_make_context(), store, est, capability="cap.attack")
    assert result.package is not None
    assert result.package.token_estimate == est.estimate(result.package.text)
