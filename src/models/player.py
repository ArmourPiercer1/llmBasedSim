from typing import Any

from pydantic import BaseModel, Field

from src.models.common import Position


class PhysicalProfile(BaseModel):
    height_cm: float | None = None
    weight_kg: float | None = None
    body_width_cm: float | None = None
    movement_mode: str = "walk"
    strength: float | None = None


class PlayerCapabilities(BaseModel):
    sight_range_m: float = 50.0
    hearing_range_m: float = 100.0
    field_of_view_degrees: float = 120.0
    special_senses: list[str] = Field(default_factory=list)
    allowed_extraordinary_actions: list[str] = Field(default_factory=list)
    blocked_common_actions: list[str] = Field(default_factory=list)
    skill_levels: dict[str, float] = Field(default_factory=dict)


class PlayerKnowledge(BaseModel):
    known_locations: dict[str, str] = Field(default_factory=dict)
    known_characters: dict[str, str] = Field(default_factory=dict)
    known_object_positions: dict[str, Position] = Field(default_factory=dict)
    rumors: list[str] = Field(default_factory=list)


class PlayerState(BaseModel):
    player_id: str = "player_1"
    name: str = "玩家"
    persona: str = ""
    position: Position | None = None
    capabilities: PlayerCapabilities = Field(default_factory=PlayerCapabilities)
    physical_profile: PhysicalProfile = Field(default_factory=PhysicalProfile)
    knowledge: PlayerKnowledge = Field(default_factory=PlayerKnowledge)
    inventory: list[str] = Field(default_factory=list)
    status_effects: dict[str, Any] = Field(default_factory=dict)
    subconscious_rules: list[str] = Field(default_factory=list)
    subconscious_memory: list[str] = Field(default_factory=list)
    speech_examples: list[str] = Field(default_factory=list)
