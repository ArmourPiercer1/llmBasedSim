"""P6-W4 ``prompts/registry.py`` 单测（SOT §3.9 + §6.1 L815，恰 13 个平铺函数）。

覆盖项（按 §6.1 L815 行逐项 1:1）：

1. ``test_normal_load``：正常装载（两 scope 各一 policy，by_id 两入、诊断空、
   TemplateDocument 六字段逐词断言）；
2. ``test_duplicate_policy_id``：重复 id（casefold 撞 by_id）→ DUPLICATE_POLICY
   error + 先入者胜；
3. ``test_path_escape_dotdot``：``..`` 越界 → PATH_ESCAPE error（path=template_ref）；
4. ``test_path_escape_absolute``：绝对路径 → PATH_ESCAPE error；
5. ``test_symlink_escape``：符号链接指向 project/prompts 之外 → PATH_ESCAPE
   （AD-5 探针：escape 判定含 symlink）；
6. ``test_template_missing``：文件缺失 → TEMPLATE_MISSING error；
7. ``test_template_empty``：空文件 → TEMPLATE_EMPTY warning + by_id 无入；
8. ``test_undeclared_variable``：未声明变量 → UNDECLARED_VARIABLE error
   refs=(tok,) + 原文 ``{{tok}}`` 保留；
9. ``test_variable_missing``：声明但缺值 → VARIABLE_MISSING error + 替换空串；
10. ``test_render_single_linear_pass``：线性单遍（同 token 多处全替换、替换值
    不再二次扫描）；
11. ``test_diagnostic_deterministic_order``：多诊断 → (code, path, refs) 排序；
12. ``test_utf8_read``：非 ASCII 模板文本字节级读出断言；
13. ``test_scope_unknown``：scope 非二值闭集 → SCOPE_UNKNOWN warning + by_id 无入。

纪律（SOT §6.1/§6.2 + AD-8）：平铺函数、自足无 conftest、零真实网络、确定性；
os 仅用于符号链接（test 5）。
"""

from __future__ import annotations

import os
from pathlib import Path

from src.engine_v2.content.schemas import DiagnosticSeverity, PromptPolicy
from src.engine_v2.prompts.registry import (
    TemplateDocument,
    TemplateStore,
    render_template,
)

_UNDECLARED = "LLMSIM_PROMPT_UNDECLARED_VARIABLE"
_VARIABLE_MISSING = "LLMSIM_PROMPT_VARIABLE_MISSING"
_DUPLICATE = "LLMSIM_PROMPT_DUPLICATE_POLICY"
_SCOPE_UNKNOWN = "LLMSIM_PROMPT_SCOPE_UNKNOWN"
_PATH_ESCAPE = "LLMSIM_PROMPT_PATH_ESCAPE"
_MISSING = "LLMSIM_PROMPT_TEMPLATE_MISSING"
_EMPTY = "LLMSIM_PROMPT_TEMPLATE_EMPTY"


def _write(tmp_path: Path, rel: str, text: str) -> None:
    """写临时项目 prompts/ 下模板文件（UTF-8）。"""
    target = tmp_path / "prompts" / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _store(tmp_path: Path, *policies: PromptPolicy) -> TemplateStore:
    return TemplateStore(project_root=tmp_path, policies=policies)


def _doc(text: str, variables: tuple[str, ...] = ()) -> TemplateDocument:
    return TemplateDocument(
        policy_id="p1",
        scope="game_policy",
        template_ref="prompts/p1.md",
        variables=variables,
        text=text,
        path="/abs/prompts/p1.md",
    )


def test_normal_load(tmp_path: Path) -> None:
    """1) 正常装载：by_id 两入、诊断空、六字段逐词断言。"""
    _write(tmp_path, "game.md", "game 规则 {{actor_id}}")
    _write(tmp_path, "scene.md", "角色场景 {{tick}}")
    store = _store(
        tmp_path,
        PromptPolicy(id="game_a", scope="game_policy", template_ref="prompts/game.md", variables=("actor_id",)),
        PromptPolicy(id="scene_b", scope="character_scene", template_ref="prompts/scene.md", variables=("tick",)),
    )
    assert store.diagnostics == ()
    assert set(store.by_id) == {"game_a", "scene_b"}
    doc = store.by_id["game_a"]
    assert doc.policy_id == "game_a"
    assert doc.scope == "game_policy"
    assert doc.template_ref == "prompts/game.md"
    assert doc.variables == ("actor_id",)
    assert doc.text == "game 规则 {{actor_id}}"
    assert doc.path == str((tmp_path / "prompts" / "game.md").resolve())
    doc2 = store.by_id["scene_b"]
    assert doc2.text == "角色场景 {{tick}}"
    assert doc2.variables == ("tick",)


def test_duplicate_policy_id(tmp_path: Path) -> None:
    """2) 重复 id（casefold）→ DUPLICATE_POLICY error + 先入者胜。"""
    _write(tmp_path, "a.md", "first text")
    _write(tmp_path, "b.md", "second text")
    store = _store(
        tmp_path,
        PromptPolicy(id="Game_A", scope="game_policy", template_ref="prompts/a.md", variables=()),
        PromptPolicy(id="game_a", scope="game_policy", template_ref="prompts/b.md", variables=()),
    )
    assert set(store.by_id) == {"Game_A"}
    assert store.by_id["Game_A"].text == "first text"
    assert len(store.diagnostics) == 1
    d = store.diagnostics[0]
    assert d.code == _DUPLICATE
    assert d.severity is DiagnosticSeverity.ERROR
    assert d.path == "Game_A"
    assert d.refs == ("game_a",)


def test_path_escape_dotdot(tmp_path: Path) -> None:
    """3) ``..`` 越界引用 → PATH_ESCAPE error（path=template_ref）。"""
    _write(tmp_path, "ok.md", "ok")
    store = _store(
        tmp_path,
        PromptPolicy(id="p_esc", scope="game_policy", template_ref="prompts/../outside.md", variables=()),
    )
    assert store.by_id == {}
    assert len(store.diagnostics) == 1
    d = store.diagnostics[0]
    assert d.code == _PATH_ESCAPE
    assert d.severity is DiagnosticSeverity.ERROR
    assert d.path == "prompts/../outside.md"
    assert d.refs == ()


def test_path_escape_absolute(tmp_path: Path) -> None:
    """4) 绝对路径引用 → PATH_ESCAPE error。"""
    store = _store(
        tmp_path,
        PromptPolicy(id="p_abs", scope="game_policy", template_ref="/etc/passwd", variables=()),
    )
    assert store.by_id == {}
    assert len(store.diagnostics) == 1
    d = store.diagnostics[0]
    assert d.code == _PATH_ESCAPE
    assert d.path == "/etc/passwd"
    assert d.refs == ()


def test_symlink_escape(tmp_path: Path) -> None:
    """5) 符号链接越界（AD-5 探针）→ PATH_ESCAPE error。"""
    _write(tmp_path, "ok.md", "ok")
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    os.symlink(outside, tmp_path / "prompts" / "link.md")
    store = _store(
        tmp_path,
        PromptPolicy(id="p_link", scope="game_policy", template_ref="prompts/link.md", variables=()),
    )
    assert store.by_id == {}
    assert len(store.diagnostics) == 1
    d = store.diagnostics[0]
    assert d.code == _PATH_ESCAPE
    assert d.severity is DiagnosticSeverity.ERROR
    assert d.path == "prompts/link.md"
    assert d.refs == ()


def test_template_missing(tmp_path: Path) -> None:
    """6) 模板文件缺失 → TEMPLATE_MISSING error。"""
    _write(tmp_path, "ok.md", "ok")
    store = _store(
        tmp_path,
        PromptPolicy(id="p_miss", scope="game_policy", template_ref="prompts/absent.md", variables=()),
    )
    assert store.by_id == {}
    assert len(store.diagnostics) == 1
    d = store.diagnostics[0]
    assert d.code == _MISSING
    assert d.severity is DiagnosticSeverity.ERROR
    assert d.path == "prompts/absent.md"
    assert d.refs == ()


def test_template_empty(tmp_path: Path) -> None:
    """7) 空文件 → TEMPLATE_EMPTY warning + by_id 无入。"""
    _write(tmp_path, "empty.md", "   \n\t  ")
    store = _store(
        tmp_path,
        PromptPolicy(id="p_empty", scope="game_policy", template_ref="prompts/empty.md", variables=()),
    )
    assert store.by_id == {}
    assert len(store.diagnostics) == 1
    d = store.diagnostics[0]
    assert d.code == _EMPTY
    assert d.severity is DiagnosticSeverity.WARNING
    assert d.path == "prompts/empty.md"
    assert d.refs == ()


def test_undeclared_variable() -> None:
    """8) 未声明变量 → UNDECLARED_VARIABLE error refs=(tok,) + 原文保留。"""
    doc = _doc("hello {{actor_id}} and {{ghost}}", variables=("actor_id",))
    result = render_template(doc, {"actor_id": "ent_x"})
    assert result.text == "hello ent_x and {{ghost}}"
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert d.code == _UNDECLARED
    assert d.severity is DiagnosticSeverity.ERROR
    assert d.path == "prompts/p1.md"
    assert d.refs == ("ghost",)


def test_variable_missing() -> None:
    """9) 声明变量缺值 → VARIABLE_MISSING error + 替换空串。"""
    doc = _doc("value={{actor_id}};end", variables=("actor_id",))
    result = render_template(doc, {})
    assert result.text == "value=;end"
    assert len(result.diagnostics) == 1
    d = result.diagnostics[0]
    assert d.code == _VARIABLE_MISSING
    assert d.severity is DiagnosticSeverity.ERROR
    assert d.refs == ("actor_id",)


def test_render_single_linear_pass() -> None:
    """10) 线性单遍：多处同 token 全替换；替换值含 ``{{v}}`` 不再二次扫描。"""
    doc = _doc("a {{v}} b {{v}} c", variables=("v",))
    result = render_template(doc, {"v": "X"})
    assert result.text == "a X b X c"
    assert result.diagnostics == ()
    result2 = render_template(doc, {"v": "{{v}}"})
    assert result2.text == "a {{v}} b {{v}} c"
    assert result2.diagnostics == ()


def test_diagnostic_deterministic_order(tmp_path: Path) -> None:
    """11) 多诊断确定性序：(code, path, refs) 三元组升序。"""
    _write(tmp_path, "ok.md", "ok 内容")
    store = _store(
        tmp_path,
        PromptPolicy(id="z_ok", scope="game_policy", template_ref="prompts/ok.md", variables=()),
        PromptPolicy(id="a_unknown", scope="narrative", template_ref="prompts/ok.md", variables=()),
        PromptPolicy(id="m_missing", scope="game_policy", template_ref="prompts/absent.md", variables=()),
        PromptPolicy(id="p_escape", scope="game_policy", template_ref="/abs/esc.md", variables=()),
    )
    assert set(store.by_id) == {"z_ok"}
    triples = [(d.code, d.path, d.refs) for d in store.diagnostics]
    assert triples == [
        (_PATH_ESCAPE, "/abs/esc.md", ()),
        (_SCOPE_UNKNOWN, "a_unknown", ("narrative",)),
        (_MISSING, "prompts/absent.md", ()),
    ]
    assert triples == sorted(triples)


def test_utf8_read(tmp_path: Path) -> None:
    """12) UTF-8 字节级读出：非 ASCII 模板文本与磁盘字节相等。"""
    content = "规则：{{actor_id}} 行动\n第二行：世界是确定性的"
    _write(tmp_path, "utf8.md", content)
    store = _store(
        tmp_path,
        PromptPolicy(id="p_utf", scope="game_policy", template_ref="prompts/utf8.md", variables=("actor_id",)),
    )
    doc = store.by_id["p_utf"]
    assert doc.text == content
    assert doc.text.encode("utf-8") == Path(doc.path).read_bytes()


def test_scope_unknown(tmp_path: Path) -> None:
    """13) scope 非二值闭集 → SCOPE_UNKNOWN warning + by_id 无入。"""
    _write(tmp_path, "n.md", "n 内容")
    store = _store(
        tmp_path,
        PromptPolicy(id="n1", scope="Narrative", template_ref="prompts/n.md", variables=()),
    )
    assert store.by_id == {}
    assert len(store.diagnostics) == 1
    d = store.diagnostics[0]
    assert d.code == _SCOPE_UNKNOWN
    assert d.severity is DiagnosticSeverity.WARNING
    assert d.path == "n1"
    assert d.refs == ("Narrative",)
