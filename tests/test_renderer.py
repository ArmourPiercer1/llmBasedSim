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
    assert "秘密" not in output


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
