from src.models.common import Position
from src.models.character import CharacterState, Personality
from src.models.player import PlayerState, PlayerCapabilities, PhysicalProfile, PlayerKnowledge
from src.models.world import WorldObject, Location, Environment, WorldState
from src.models.events import PlayerAction, ActionIntent, PhysicsOutcome, PhysicsResolution, PlayerPercept, SenseDetail


class TestPosition:
    def test_defaults(self):
        p = Position()
        assert p.x == 0.0
        assert p.y == 0.0
        assert p.z == 0.0

    def test_model_dump(self):
        p = Position(x=1.5, y=2.5, z=3.5)
        d = p.model_dump()
        assert d == {"x": 1.5, "y": 2.5, "z": 3.5}


class TestPlayerAction:
    def test_defaults(self):
        a = PlayerAction()
        assert a.action_type == "observe"
        assert a.emotion == "neutral"
        assert a.requires_roll is False
        assert a.duration_minutes == 0.0
        assert a.continue_until == ""

    def test_valid_action_types(self):
        for at in ("move", "interact", "speak", "use_item", "wait", "observe"):
            a = PlayerAction(action_type=at)  # type: ignore[arg-type]
            assert a.action_type == at


class TestActionIntent:
    def test_defaults(self):
        ai = ActionIntent(character_id="test_char", action_type="wait")
        assert ai.action_type == "wait"
        assert ai.emotion == "neutral"
        assert ai.intensity == 1.0
        assert ai.action_description == ""


class TestPlayerState:
    def test_defaults(self):
        ps = PlayerState()
        assert ps.player_id == "player_1"
        assert ps.inventory == []
        assert ps.subconscious_rules == []

    def test_capabilities_defaults(self):
        caps = PlayerCapabilities()
        assert caps.sight_range_m == 50.0
        assert caps.hearing_range_m == 100.0
        assert caps.special_senses == []

    def test_physical_profile_defaults(self):
        pp = PhysicalProfile()
        assert pp.movement_mode == "walk"
        assert pp.height_cm is None


class TestCharacterState:
    def test_defaults(self):
        cs = CharacterState(character_id="ch1", name="Test")
        assert cs.inventory == []
        assert cs.memory == []
        assert cs.relationships == {}

    def test_personality_defaults(self):
        p = Personality()
        assert p.traits == []
        assert p.motivations == []


class TestWorldModels:
    def test_location_defaults(self):
        loc = Location(location_id="loc1", name="Test", description="Desc")
        assert loc.ambient_light == "bright"
        assert loc.ambient_sound == "quiet"

    def test_world_object_valid_types(self):
        valid_types = [
            "furniture", "container", "decoration", "tool", "food", "weapon",
            "character_equipment", "device", "document", "clothing", "misc",
        ]
        for ot in valid_types:
            obj = WorldObject(object_id="o1", object_type=ot, name="Test", description="Desc")  # type: ignore[arg-type]
            assert obj.object_type == ot

    def test_environment_defaults(self):
        env = Environment()
        assert env.time_of_day == "morning"
        assert env.temperature_c == 20.0


class TestPhysicsModels:
    def test_physics_outcome_defaults(self):
        po = PhysicsOutcome(outcome_type="movement")
        assert po.outcome_type == "movement"
        assert po.description == ""

    def test_physics_resolution_defaults(self):
        pr = PhysicsResolution()
        assert pr.outcomes == []


class TestPlayerPercept:
    def test_defaults(self):
        pp = PlayerPercept()
        assert pp.senses == []
        assert pp.hidden_event_count == 0

    def test_sense_detail(self):
        sd = SenseDetail(sense="sight", description="看到一扇门")
        assert sd.confidence == 1.0
