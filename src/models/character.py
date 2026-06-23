from typing import Any

from pydantic import BaseModel, Field

from src.models.common import Position


class Personality(BaseModel):
    traits: list[str] = Field(default_factory=list)
    motivations: list[str] = Field(default_factory=list)
    speech_style: str = "casual"
    background: str = ""


class CharacterState(BaseModel):
    character_id: str
    name: str
    personality: Personality = Field(default_factory=Personality)
    position: Position = Field(default_factory=Position)
    inventory: list[str] = Field(default_factory=list)
    status_effects: dict[str, Any] = Field(default_factory=dict)
    current_action: str | None = None
    memory: list[str] = Field(default_factory=list)
    relationships: dict[str, float] = Field(default_factory=dict)
    speech_examples: list[str] = Field(default_factory=list)
