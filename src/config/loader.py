from pathlib import Path
from typing import TypeVar

import yaml

from src.models.config import (
    SimulationConfig,
    WorldConfig,
    PlayerConfig,
    CharacterConfig,
)

T = TypeVar("T")


class ConfigLoader:
    def __init__(self, config_root: str = "config"):
        self._root = Path(config_root)

    def load_simulation(self) -> SimulationConfig:
        return self._load_yaml("simulation.yaml", SimulationConfig)

    def load_world(self) -> WorldConfig:
        return self._load_yaml("world.yaml", WorldConfig)

    def load_player(self) -> PlayerConfig:
        return self._load_yaml("player.yaml", PlayerConfig)

    def load_all_characters(self) -> list[CharacterConfig]:
        chars_dir = self._root / "characters"
        configs: list[CharacterConfig] = []
        for filepath in sorted(chars_dir.glob("*.yaml")):
            configs.append(self._load_yaml(str(filepath.relative_to(self._root)), CharacterConfig))
        return configs

    def _load_yaml(self, relative_path: str, model_cls: type[T]) -> T:
        filepath = self._root / relative_path
        with open(filepath, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return model_cls.model_validate(raw)
