from typing import Literal

from pydantic import BaseModel, Field

from src.models.common import Position
from src.models.character import Personality


class LLMConfigModel(BaseModel):
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    api_key_env: str = "DEEPSEEK_API_KEY"
    base_url: str = "https://api.deepseek.com"
    temperature: float = 0.7
    max_tokens: int = 4096


class AgentCharacterConfig(BaseModel):
    memory_size: int = 50
    concurrent: bool = True


class AgentPhysicsConfig(BaseModel):
    chain_reaction_depth: int = 3


class AgentSensoryConfig(BaseModel):
    default_sight_range_m: float = 50.0
    default_hearing_range_m: float = 100.0


class AgentsConfig(BaseModel):
    character: AgentCharacterConfig = Field(default_factory=AgentCharacterConfig)
    physics: AgentPhysicsConfig = Field(default_factory=AgentPhysicsConfig)
    sensory: AgentSensoryConfig = Field(default_factory=AgentSensoryConfig)


class SimulationConfigData(BaseModel):
    max_ticks: int = 100
    tick_delay_ms: int = 100
    log_level: str = "INFO"
    debug: bool = False


class SimulationConfig(BaseModel):
    simulation: SimulationConfigData = Field(default_factory=SimulationConfigData)
    llm: LLMConfigModel = Field(default_factory=LLMConfigModel)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)


class WorldLocationConfig(BaseModel):
    id: str
    name: str
    description: str
    connections: dict[str, str] = Field(default_factory=dict)
    ambient_light: str = "bright"
    ambient_sound: str = "quiet"


class WorldObjectConfig(BaseModel):
    id: str
    object_type: Literal[
        "furniture", "container", "decoration", "tool", "food", "weapon",
        "character_equipment", "device", "document", "clothing", "misc",
    ]
    name: str
    description: str
    position: Position = Field(default_factory=Position)
    state: dict = Field(default_factory=dict)
    properties: dict = Field(default_factory=dict)


class WorldEnvironmentConfig(BaseModel):
    time_of_day: str = "morning"
    weather: str = "clear"
    temperature_c: float = 20.0


class WorldConfigData(BaseModel):
    name: str = ""
    description: str = ""
    environment: WorldEnvironmentConfig = Field(default_factory=WorldEnvironmentConfig)
    locations: list[WorldLocationConfig] = Field(default_factory=list)
    objects: list[WorldObjectConfig] = Field(default_factory=list)


class WorldConfig(BaseModel):
    world: WorldConfigData = Field(default_factory=WorldConfigData)


class PlayerCapabilitiesConfig(BaseModel):
    sight_range_m: float = 50.0
    hearing_range_m: float = 100.0
    field_of_view_degrees: float = 120.0
    special_senses: list[str] = Field(default_factory=list)
    allowed_extraordinary_actions: list[str] = Field(default_factory=list)
    blocked_common_actions: list[str] = Field(default_factory=list)
    skill_levels: dict[str, float] = Field(default_factory=dict)


class PhysicalProfileConfig(BaseModel):
    height_cm: float | None = None
    weight_kg: float | None = None
    body_width_cm: float | None = None
    movement_mode: str = "walk"
    strength: float | None = None


class PlayerConfigModel(BaseModel):
    name: str = "玩家"
    persona: str = ""
    starting_position: Position | None = None
    capabilities: PlayerCapabilitiesConfig = Field(default_factory=PlayerCapabilitiesConfig)
    physical_profile: PhysicalProfileConfig = Field(default_factory=PhysicalProfileConfig)
    starting_inventory: list[str] = Field(default_factory=list)
    subconscious_rules: list[str] = Field(default_factory=list)
    subconscious_memory: list[str] = Field(default_factory=list)
    speech_examples: list[str] = Field(default_factory=list)


class CharacterConfigModel(BaseModel):
    id: str
    name: str
    personality: Personality = Field(default_factory=Personality)
    starting_position: Position = Field(default_factory=Position)
    starting_inventory: list[str] = Field(default_factory=list)
    relationships: dict[str, float] = Field(default_factory=dict)
    speech_examples: list[str] = Field(default_factory=list)


class PlayerConfig(BaseModel):
    player: PlayerConfigModel = Field(default_factory=PlayerConfigModel)


class CharacterConfig(BaseModel):
    character: CharacterConfigModel
