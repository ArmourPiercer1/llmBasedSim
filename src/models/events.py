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
    interpreted_intent: str = Field(default="", description="必填。你对玩家真实意图的解释，一句话概括。")
    subconscious_adjustment: str | None = Field(default=None, description="潜意识或人设造成的修正；无修正时填null。")
    action_type: Literal["move", "interact", "speak", "use_item", "wait", "observe"] = Field(default="observe", description="必填。行动类型。")
    action_description: str = Field(default="", description="必填。玩家实际尝试做出的行动，生动自然的描述。")
    speech_content: str | None = Field(default=None, description="若action_type为speak则必填玩家实际说出口的话；非说话行为填null。")
    target_object_id: str | None = Field(default=None, description="若行动涉及物体则必填物体ID。若玩家提到'那个花瓶''桌上的杯子'等，必须从场景物体中匹配最可能的一个。无匹配目标时填null。")
    target_character_id: str | None = Field(default=None, description="若行动涉及其他角色则必填角色ID。若玩家提到'他''那个人''管家'等，必须从场景角色中匹配最可能的一个。无匹配目标时填null。")
    target_position: Position | None = Field(default=None, description="若行动涉及移动到特定位置则必填坐标。若玩家想去'出口''花园''书房'等，必须从场景地点中匹配对应坐标；若无精确匹配则选最接近意图的位置。完全无移动目标时填null。")
    emotion: str = Field(default="neutral", description="必填。玩家行动时的情绪。")
    feasibility: Literal["allowed", "blocked", "uncertain"] | None = Field(default=None, description="留给可行性处理器判断，此处不填。")
    feasibility_reason: str | None = Field(default=None, description="留给可行性处理器判断，此处不填。")
    success_probability: float | None = Field(default=None, description="留给可行性处理器判断，此处不填。")
    requires_roll: bool = Field(default=False, description="留给可行性处理器判断，此处不填。")
    confidence: float = Field(default=1.0, description="必填。你对此次解析的置信度（0.0-1.0）。")
    notes: str = Field(default="", description="调试说明，不展示给玩家。")
    duration_minutes: float = Field(default=0.0, ge=0.0, description="必填。行动预计时长（分钟）。短行动填0。搜查/搜索/行走/讲述等长行动估算分钟数。")
    continue_until: Literal["", "done", "blocked", "goal"] = Field(default="", description="必填。多步行动标志。空字符串=单步行动即可完成。blocked=持续直到被物理或NPC阻止。done=持续直到玩家手动停止。goal=持续直到目标达成。")


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
