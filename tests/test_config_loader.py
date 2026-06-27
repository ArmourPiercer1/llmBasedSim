from pathlib import Path

from src.config.loader import ConfigLoader


def _write_config_tree(root: Path) -> None:
    (root / "characters").mkdir()
    (root / "simulation.yaml").write_text(
        """
simulation:
  max_ticks: 100
llm:
  model: deepseek-chat
""".strip(),
        encoding="utf-8",
    )
    (root / "world.yaml").write_text(
        """
world:
  name: 测试世界
  locations:
    - id: hall
      name: 大厅
      description: 明亮的大厅
  objects:
    - id: table
      object_type: furniture
      name: 桌子
      description: 一张桌子
""".strip(),
        encoding="utf-8",
    )
    (root / "player.yaml").write_text(
        """
player:
  name: 艾琳
  persona: 测试角色
""".strip(),
        encoding="utf-8",
    )
    (root / "characters" / "rain.yaml").write_text(
        """
character:
  id: rain
  name: 雷恩
""".strip(),
        encoding="utf-8",
    )


class TestConfigLoader:
    def test_load_simulation(self, tmp_path):
        _write_config_tree(tmp_path)
        cfg = ConfigLoader(str(tmp_path)).load_simulation()
        assert cfg.llm.model == "deepseek-chat"
        assert cfg.simulation.max_ticks == 100

    def test_load_world(self, tmp_path):
        _write_config_tree(tmp_path)
        cfg = ConfigLoader(str(tmp_path)).load_world()
        assert cfg.world.name == "测试世界"
        assert len(cfg.world.locations) > 0
        assert len(cfg.world.objects) > 0

    def test_load_player(self, tmp_path):
        _write_config_tree(tmp_path)
        cfg = ConfigLoader(str(tmp_path)).load_player()
        assert cfg.player.name == "艾琳"
        assert cfg.player.persona == "测试角色"

    def test_load_all_characters(self, tmp_path):
        _write_config_tree(tmp_path)
        chars = ConfigLoader(str(tmp_path)).load_all_characters()
        assert len(chars) == 1
        assert chars[0].character.id == "rain"
        assert chars[0].character.name == "雷恩"
