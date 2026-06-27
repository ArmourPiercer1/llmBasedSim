from src.agents.init import config_loader_to_game_state, init_file_to_game_state, load_init_file, load_init_file_set
from src.config.loader import ConfigLoader
from src.graph.game_state import normalize_state, strip_transient_state


def _raw_scene():
    return {
        "world": {
            "name": "蔷薇庄园",
            "description": "测试庄园",
            "locations": [
                {"id": "hall", "name": "大厅", "description": "明亮的大厅"},
            ],
            "objects": [
                {"id": "table", "object_type": "furniture", "name": "桌子", "description": "一张桌子"},
            ],
        },
        "player": {
            "name": "艾琳",
            "starting_position": {"x": 0, "y": 0, "z": 0, "location_id": "hall"},
            "attributes": {"stamina": {"name": "体力", "value": 70, "max": 100}},
            "subconscious_rules": ["规则1", "规则2", "规则3", "规则4"],
        },
        "characters": [
            {
                "id": "knight_rain",
                "name": "雷恩",
                "starting_position": {"x": 1, "y": 0, "z": 0, "location_id": "hall"},
                "attributes": {"composure": {"name": "镇定", "value": 40, "max": 100}},
            }
        ],
        "starting_scene_description": "开场",
    }


def test_init_file_loads_full_test_scene():
    state = init_file_to_game_state(_raw_scene())

    assert state["world_name"] == "蔷薇庄园"
    assert len(state["locations"]) == 1
    assert len(state["objects"]) == 1
    assert len(state["characters"]) == 1
    assert state["player"]["position"] is not None
    assert "stamina" in state["player"]["attributes"]
    assert "composure" in state["characters"]["knight_rain"]["attributes"]
    assert len(state["player"]["subconscious_rules"]) == 4


def test_split_config_loads_state_with_position(tmp_path):
    (tmp_path / "characters").mkdir()
    (tmp_path / "simulation.yaml").write_text("simulation:\n  max_ticks: 100\n", encoding="utf-8")
    (tmp_path / "world.yaml").write_text(
        """
world:
  name: 测试世界
  locations:
    - id: hall
      name: 大厅
      description: 明亮的大厅
  objects: []
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "player.yaml").write_text(
        """
player:
  name: 艾琳
  starting_position:
    x: 0
    y: 0
    z: 0
    location_id: hall
  attributes:
    stamina:
      name: 体力
      value: 70
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "characters" / "alice.yaml").write_text(
        """
character:
  id: alice
  name: 爱丽丝
  attributes:
    mood:
      name: 心情
      value: 50
""".strip(),
        encoding="utf-8",
    )

    state = config_loader_to_game_state(ConfigLoader(str(tmp_path)))

    assert state["world_name"] == "测试世界"
    assert state["player"]["position"] is not None
    assert state["characters"]
    assert "stamina" in state["player"]["attributes"]
    assert "mood" in state["characters"]["alice"]["attributes"]


def test_strip_transient_state_round_trip_preserves_attributes():
    state = init_file_to_game_state(_raw_scene())
    state["player_input"] = "test"
    state["player_action"] = {"raw_input": "test"}
    state["action_intents"] = [{"character_id": "x"}]
    state["physics_outcomes"] = [{"outcome_type": "sound"}]
    state["player_percept"] = {"summary": "test"}

    saved = strip_transient_state(state)
    for key in ("player_input", "player_action", "action_intents", "physics_outcomes"):
        assert key not in saved
    assert saved["player_percept"] == {"summary": "test"}

    loaded = normalize_state(saved)
    assert loaded["world_name"] == state["world_name"]
    assert loaded["player"]["attributes"]["stamina"]["value"] == 70
    assert loaded["characters"]["knight_rain"]["attributes"]["composure"]["value"] == 40
    assert loaded["player_input"] is None
    assert loaded["player_action"] is None
    assert loaded["action_intents"] == []


def test_init_file_preserves_world_rules():
    state = init_file_to_game_state(load_init_file("public_start/whisperheads.yaml"))
    assert "physics" in state["world_rules"]
    assert "attribute" in state["world_rules"]


def test_world_rules_survive_save_load_round_trip():
    raw = {
        "world": {"name": "T", "description": "T", "locations": [], "objects": []},
        "player": {"name": "T"},
        "characters": [],
        "starting_scene_description": "S",
        "world_rules": {
            "physics": {"disable": [3, 8], "append": ["11. 自定义规则"]},
            "attribute": {"disable": [2]},
            "deterministic": {
                "disable": [3],
                "append": [{"id": "x", "description": "x", "condition": "if(player.sanity < 1, blocked; allowed)"}],
            },
        },
    }
    state = init_file_to_game_state(raw)
    assert state["world_rules"]["physics"]["disable"] == [3, 8]
    assert state["world_rules"]["attribute"]["disable"] == [2]
    assert state["world_rules"]["deterministic"]["disable"] == [3]
    assert any("自定义规则" in r for r in state["world_rules"]["physics"]["append"])

    saved = strip_transient_state(state)
    reloaded = normalize_state(saved)
    assert reloaded["world_rules"]["physics"]["disable"] == [3, 8]
    assert reloaded["world_rules"]["attribute"]["disable"] == [2]
    assert reloaded["world_rules"]["deterministic"]["disable"] == [3]


def test_narrative_style_survive_save_load_round_trip():
    raw = {
        "world": {"name": "T", "description": "T", "locations": [], "objects": []},
        "player": {"name": "T"},
        "characters": [],
        "starting_scene_description": "S",
        "narrative_style": {
            "style_description": "哥特式军事科幻",
            "style_example": "寒风如刀...",
        },
    }
    state = init_file_to_game_state(raw)
    assert state["narrative_style"]["style_description"] == "哥特式军事科幻"
    assert state["narrative_style"]["style_example"] == "寒风如刀..."

    saved = strip_transient_state(state)
    reloaded = normalize_state(saved)
    assert reloaded["narrative_style"]["style_description"] == "哥特式军事科幻"
    assert reloaded["narrative_style"]["style_example"] == "寒风如刀..."

    raw_no_style = {
        "world": {"name": "T", "description": "T", "locations": [], "objects": []},
        "player": {"name": "T"},
        "characters": [],
        "starting_scene_description": "S",
    }
    state2 = init_file_to_game_state(raw_no_style)
    assert state2["narrative_style"] == {}


def test_load_init_file_set_from_dir(tmp_path):
    (tmp_path / "world.yaml").write_text(
        """
world:
  name: 测试场景
  description: 拆分配置测试
  locations:
    - id: plaza
      name: 广场
      description: 中央广场
  objects: []
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "player.yaml").write_text(
        """
player:
  name: 测试玩家
  persona: 测试角色
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "characters").mkdir()
    (tmp_path / "characters" / "guard.yaml").write_text(
        """
character:
  id: guard
  name: 守卫
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "settings.yaml").write_text(
        """
world_rules:
  physics:
    disable: [1]
narrative_style:
  style_description: 测试文风
max_ticks: 50
game_time:
  hour: 6
  minute: 30
ticks_per_game_minute: 0.5
""".strip(),
        encoding="utf-8",
    )

    state = load_init_file_set(str(tmp_path))

    assert state["world_name"] == "测试场景"
    assert state["world_description"] == "拆分配置测试"
    assert len(state["locations"]) == 1
    assert state["player"]["name"] == "测试玩家"
    assert "guard" in state["characters"]
    assert state["world_rules"]["physics"]["disable"] == [1]
    assert state["narrative_style"]["style_description"] == "测试文风"
    assert state["max_ticks"] == 50
    assert state["game_time"]["hour"] == 6
    assert state["ticks_per_game_minute"] == 0.5


def test_load_init_file_set_minimal_world_only(tmp_path):
    (tmp_path / "world.yaml").write_text(
        """
world:
  name: 最小场景
  description: 仅世界文件
  locations: []
  objects: []
""".strip(),
        encoding="utf-8",
    )

    state = load_init_file_set(str(tmp_path))

    assert state["world_name"] == "最小场景"
    assert state["player"]["name"]  # default from ConfigLoader
    assert state["world_rules"] == {}
