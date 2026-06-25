from src.config.loader import ConfigLoader


class TestConfigLoader:
    @classmethod
    def setup_class(cls):
        cls.loader = ConfigLoader("config")

    def test_load_simulation(self):
        cfg = self.loader.load_simulation()
        assert cfg.llm.model == "deepseek-chat"
        assert cfg.simulation.max_ticks == 100

    def test_load_world(self):
        cfg = self.loader.load_world()
        assert cfg.world.name
        assert len(cfg.world.locations) > 0
        assert len(cfg.world.objects) > 0

    def test_load_player(self):
        cfg = self.loader.load_player()
        assert cfg.player.name
        assert cfg.player.persona

    def test_load_all_characters(self):
        chars = self.loader.load_all_characters()
        assert len(chars) > 0
        for c in chars:
            assert c.character.id
            assert c.character.name
