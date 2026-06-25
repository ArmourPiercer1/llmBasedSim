from typing import Any, Literal

from pydantic import BaseModel, Field

from src.models.common import Position
from src.models.world import WorldState, Environment
from src.models.character import CharacterState
from src.models.player import PlayerState


class ActionIntent(BaseModel):
    character_id: str
    action_type: Literal["move", "interact", "speak", "use_item", "wait", "observe"]
    action_description: str = ""
    target_object_id: str | None = None
    target_character_id: str | None = None
    target_position: Position | None = None
    intensity: float = 1.0
    emotion: str = "neutral"


class PhysicsOutcome(BaseModel):
    outcome_type: Literal["movement", "collision", "sound", "destruction", "state_change"]
    description: str = ""
    subject_object_id: str | None = None
    cause_character_id: str | None = None
    position_delta: Position | None = None
    sound_description: str | None = None
    new_state: dict[str, Any] | None = None
    affected_characters: list[str] = Field(default_factory=list)


class PhysicsResolution(BaseModel):
    outcomes: list[PhysicsOutcome] = Field(default_factory=list)
    reasoning: str = ""


class SenseDetail(BaseModel):
    sense: Literal["sight", "sound", "smell", "touch"]
    description: str = ""
    source_object_id: str | None = None
    source_position: Position | None = None
    confidence: float = 1.0


class PlayerPercept(BaseModel):
    senses: list[SenseDetail] = Field(default_factory=list)
    summary: str = ""
    hidden_event_count: int = 0
    self_action_summary: str = ""


class PlayerAction(BaseModel):
    raw_input: str = ""
    interpreted_intent: str = ""
    subconscious_adjustment: str | None = None
    action_type: Literal["move", "interact", "speak", "use_item", "wait", "observe"] = "observe"
    action_description: str = ""
    speech_content: str | None = None
    target_object_id: str | None = None
    target_character_id: str | None = None
    target_position: Position | None = None
    emotion: str = "neutral"
    feasibility: Literal["allowed", "blocked", "uncertain"] | None = None
    feasibility_reason: str | None = None
    success_probability: float | None = None
    requires_roll: bool = False
    confidence: float = 1.0
    notes: str = ""
    duration_minutes: float | None = None
    continue_until: Literal["done", "blocked", "goal"] | None = None


class InitialWorldConfig(BaseModel):
    name: str = ""
    description: str = ""
    locations: dict[str, Any] = Field(default_factory=dict)
    objects: dict[str, Any] = Field(default_factory=dict)
    environment: Environment = Field(default_factory=Environment)


class InitialGameConfig(BaseModel):
    world: InitialWorldConfig = Field(default_factory=InitialWorldConfig)
    characters: list[CharacterState] = Field(default_factory=list)
    player: PlayerState = Field(default_factory=PlayerState)
    starting_scene_description: str = ""
