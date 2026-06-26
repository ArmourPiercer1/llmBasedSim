from io import StringIO

from rich.console import Console

from src.ui import renderer


def _capture_console(monkeypatch) -> StringIO:
    stream = StringIO()
    monkeypatch.setattr(renderer, "console", Console(file=stream, force_terminal=False, color_system=None, width=120))
    return stream


def test_render_status_displays_player_attributes(monkeypatch):
    stream = _capture_console(monkeypatch)
    state = {
        "player": {
            "name": "艾琳",
            "attributes": {
                "stamina": {"name": "体力", "value": 70, "max": 100},
                "secret": {"name": "秘密", "value": 1, "hidden": True},
            },
        }
    }

    renderer.render_status(state)

    output = stream.getvalue()
    assert "艾琳的数值状态" in output
    assert "体力" in output
    assert "70/100" in output
    # /status should show hidden attributes too
    assert "秘密" in output
    assert "(hidden)" in output


def test_render_attribute_debug_displays_player_and_npc_attributes(monkeypatch):
    stream = _capture_console(monkeypatch)
    state = {
        "player": {
            "name": "艾琳",
            "attributes": {"stamina": {"name": "体力", "value": 70, "max": 100}},
        },
        "characters": {
            "knight_rain": {
                "name": "雷恩",
                "attributes": {"composure": {"name": "镇定", "value": 40, "max": 100}},
            }
        },
    }

    renderer.render_attribute_debug(state)

    output = stream.getvalue()
    assert "数值状态（调试）" in output
    assert "艾琳" in output
    assert "体力" in output
    assert "雷恩" in output
    assert "镇定" in output


def test_render_percept_uses_narrative_when_available(monkeypatch):
    stream = _capture_console(monkeypatch)
    percept = {
        "self_action_summary": "你走向门口",
        "narrative": "暮色如血，染红了庄园的每一扇窗。你踏过吱嘎作响的木地板，向那扇沉重的橡木门走去。",
        "senses": [{"sense": "sight", "description": "一扇橡木门"}],
        "summary": "你看到一扇门",
        "player_attributes": {},
    }
    renderer.render_percept(percept)
    output = stream.getvalue()
    assert "暮色如血" in output
    # Self-action panel should NOT be rendered by default
    assert "你做了什么" not in output
    # Narrative should be shown instead of raw sense list
    assert "[看]" not in output


def test_render_percept_falls_back_to_senses_when_no_narrative(monkeypatch):
    stream = _capture_console(monkeypatch)
    percept = {
        "senses": [{"sense": "sight", "description": "一扇木门"}],
        "summary": "你看到一扇门",
        "player_attributes": {},
    }
    renderer.render_percept(percept)
    output = stream.getvalue()
    assert "[看] 一扇木门" in output


def test_render_sense_category_filters_by_type(monkeypatch):
    stream = _capture_console(monkeypatch)
    percept = {
        "senses": [
            {"sense": "sight", "description": "石桥横跨深渊"},
            {"sense": "sound", "description": "寒风呼啸"},
            {"sense": "touch", "description": "冰凉的金属扶手"},
        ],
    }
    renderer.render_sense_category(percept, "sound")
    output = stream.getvalue()
    assert "寒风呼啸" in output
    assert "石桥横跨深渊" not in output
    assert "冰凉的金属扶手" not in output
    assert "你听到的" in output


def test_render_sense_category_shows_empty_when_no_match(monkeypatch):
    stream = _capture_console(monkeypatch)
    percept = {"senses": [{"sense": "sight", "description": "石桥"}]}
    renderer.render_sense_category(percept, "sound")
    output = stream.getvalue()
    assert "你没有听到" in output


def test_render_sense_category_handles_none_percept(monkeypatch):
    stream = _capture_console(monkeypatch)
    renderer.render_sense_category(None, "sight")
    output = stream.getvalue()
    assert "你什么也没有感知到" in output


def test_render_self_action_displays_content(monkeypatch):
    stream = _capture_console(monkeypatch)
    percept = {"self_action_summary": "你推开沉重的橡木门，走进了昏暗的书房。"}
    renderer.render_self_action(percept)
    output = stream.getvalue()
    assert "你做了什么" in output
    assert "你推开沉重的橡木门" in output


def test_render_self_action_shows_empty_when_no_action(monkeypatch):
    stream = _capture_console(monkeypatch)
    renderer.render_self_action({"self_action_summary": ""})
    output = stream.getvalue()
    assert "没有特别的行为" in output


def test_render_self_action_handles_none_percept(monkeypatch):
    stream = _capture_console(monkeypatch)
    renderer.render_self_action(None)
    output = stream.getvalue()
    assert "你什么也没有做" in output
