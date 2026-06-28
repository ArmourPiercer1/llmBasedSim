from typing import Any

from pydantic import BaseModel, Field


class Position(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class CharacterAttribute(BaseModel):
    name: str = ""
    value: Any = 0.0
    min: float | None = None
    max: float | None = None
    natural_delta_per_minute: float = 0.0
    description: str = ""
    hidden: bool = False
    tags: list[str] = Field(default_factory=list)
    unit: str = ""
    locked: bool = False
