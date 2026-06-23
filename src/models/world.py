from typing import Any, Literal

from pydantic import BaseModel, Field

from src.models.common import Position


class Environment(BaseModel):
    time_of_day: str = "morning"
    weather: str = "clear"
    temperature_c: float = 20.0


class Location(BaseModel):
    location_id: str
    name: str
    description: str
    connections: dict[str, str] = Field(default_factory=dict)
    objects: list[str] = Field(default_factory=list)
    ambient_light: str = "bright"
    ambient_sound: str = "quiet"


class WorldObject(BaseModel):
    object_id: str
    object_type: Literal[
        "furniture", "container", "decoration", "tool", "food", "weapon",
        "character_equipment", "device", "document", "clothing", "misc",
    ]
    name: str
    description: str
    position: Position = Field(default_factory=Position)
    state: dict[str, Any] = Field(default_factory=dict)
    properties: dict[str, Any] = Field(default_factory=dict)


class WorldState(BaseModel):
    name: str = ""
    description: str = ""
    locations: dict[str, Location] = Field(default_factory=dict)
    objects: dict[str, WorldObject] = Field(default_factory=dict)
    character_positions: dict[str, Position] = Field(default_factory=dict)
    environment: Environment = Field(default_factory=Environment)
