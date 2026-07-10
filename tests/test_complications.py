from src.game.attributes import (
    apply_deterministic_attributes,
)


# --- New complication rules ---

def test_cervical_lip_compute_detects():
    """_cervical_lip_present computes to 1 when dilation >= 8, station >= 0, stagnation > 30."""
    player = {
        "name": "测试",
        "attributes": {
            "cervical_dilation": {"name": "宫颈扩张", "value": 9},
            "fetal_station": {"name": "胎头位置", "value": 0},
            "time_without_station_progress": {"name": "停滞时间", "value": 35},
            "_cervical_lip_present": {"name": "_cervical_lip_present", "value": 0},
            "maternal_special_conditions": {"name": "特殊状态", "value": []},
        },
    }
    rules = [
        {"type": "compute", "target_key": "_cervical_lip_present",
         "expression": "if(cervical_dilation >= 8 and fetal_station >= 0 and time_without_station_progress > 30, 1; 0)"},
        {"type": "list_constraint", "list_key": "maternal_special_conditions",
         "condition": "_cervical_lip_present == 1 and cervical_dilation >= 8 and cervical_dilation < 10",
         "value": "cervical_lip"},
    ]
    new_player, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["_cervical_lip_present"]["value"] == 1
    assert "cervical_lip" in new_player["attributes"]["maternal_special_conditions"]["value"]


def test_cervical_lip_not_detected_when_progressing():
    """No cervical lip when station is still advancing."""
    player = {
        "name": "测试",
        "attributes": {
            "cervical_dilation": {"name": "宫颈扩张", "value": 9},
            "fetal_station": {"name": "胎头位置", "value": 0},
            "time_without_station_progress": {"name": "停滞时间", "value": 10},
            "_cervical_lip_present": {"name": "_cervical_lip_present", "value": 0},
        },
    }
    rules = [{"type": "compute", "target_key": "_cervical_lip_present",
              "expression": "if(cervical_dilation >= 8 and fetal_station >= 0 and time_without_station_progress > 30, 1; 0)"}]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["_cervical_lip_present"]["value"] == 0


def test_compound_presentation_list_constraint():
    """compound_presentation=true adds to maternal_special_conditions."""
    player = {
        "name": "测试",
        "attributes": {
            "compound_presentation": {"name": "复合先露", "value": True},
            "maternal_special_conditions": {"name": "特殊状态", "value": []},
        },
    }
    rules = [{"type": "list_constraint", "list_key": "maternal_special_conditions",
              "condition": "compound_presentation == true", "value": "compound_presentation"}]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert "compound_presentation" in new_player["attributes"]["maternal_special_conditions"]["value"]


def test_meconium_fluid_list_constraint():
    """Meconium added to conditions when fluid != none and membranes ruptured."""
    player = {
        "name": "测试",
        "attributes": {
            "meconium_fluid": {"name": "胎粪", "value": "light"},
            "amniotic_fluid_status": {"name": "羊膜", "value": 0},
            "maternal_special_conditions": {"name": "特殊状态", "value": []},
        },
    }
    rules = [{"type": "list_constraint", "list_key": "maternal_special_conditions",
              "condition": 'meconium_fluid != "none" and amniotic_fluid_status <= 0',
              "value": "meconium_fluid"}]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert "meconium_fluid" in new_player["attributes"]["maternal_special_conditions"]["value"]


def test_meconium_not_added_when_clean():
    """No meconium flag when fluid is none."""
    player = {
        "name": "测试",
        "attributes": {
            "meconium_fluid": {"name": "胎粪", "value": "none"},
            "amniotic_fluid_status": {"name": "羊膜", "value": 0},
            "maternal_special_conditions": {"name": "特殊状态", "value": []},
        },
    }
    rules = [{"type": "list_constraint", "list_key": "maternal_special_conditions",
              "condition": 'meconium_fluid != "none" and amniotic_fluid_status <= 0',
              "value": "meconium_fluid"}]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert "meconium_fluid" not in new_player["attributes"]["maternal_special_conditions"]["value"]


def test_has_urge_to_push_compute():
    """has_urge_to_push = true when station >= 2 and dilation >= 10."""
    player = {
        "name": "测试",
        "attributes": {
            "fetal_station": {"name": "胎头位置", "value": 2},
            "cervical_dilation": {"name": "宫颈扩张", "value": 10},
            "has_urge_to_push": {"name": "用力冲动", "value": False},
        },
    }
    rules = [{"type": "compute", "target_key": "has_urge_to_push",
              "expression": "if(fetal_station >= 2 and cervical_dilation >= 10, true; cervical_dilation < 10, false; has_urge_to_push)"}]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["has_urge_to_push"]["value"] is True


def test_has_urge_to_push_false_before_full_dilation():
    """has_urge_to_push stays false when cervix not fully dilated."""
    player = {
        "name": "测试",
        "attributes": {
            "fetal_station": {"name": "胎头位置", "value": 2},
            "cervical_dilation": {"name": "宫颈扩张", "value": 8},
            "has_urge_to_push": {"name": "用力冲动", "value": False},
        },
    }
    rules = [{"type": "compute", "target_key": "has_urge_to_push",
              "expression": "if(fetal_station >= 2 and cervical_dilation >= 10, true; cervical_dilation < 10, false; has_urge_to_push)"}]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["has_urge_to_push"]["value"] is False


def test_no_urge_to_push_list_constraint():
    """no_urge_to_push added when fully dilated, no urge, and station stagnating."""
    player = {
        "name": "测试",
        "attributes": {
            "cervical_dilation": {"name": "宫颈扩张", "value": 10},
            "has_urge_to_push": {"name": "用力冲动", "value": False},
            "time_without_station_progress": {"name": "停滞时间", "value": 35},
            "maternal_special_conditions": {"name": "特殊状态", "value": []},
        },
    }
    rules = [{"type": "list_constraint", "list_key": "maternal_special_conditions",
              "condition": "cervical_dilation >= 10 and has_urge_to_push == false and time_without_station_progress > 30",
              "value": "no_urge_to_push"}]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert "no_urge_to_push" in new_player["attributes"]["maternal_special_conditions"]["value"]


def test_nuchal_cord_list_constraint():
    """nuchal_cord='tight' adds nuchal_cord_tight to maternal_special_conditions."""
    player = {
        "name": "测试",
        "attributes": {
            "nuchal_cord": {"name": "脐带绕颈", "value": "tight"},
            "maternal_special_conditions": {"name": "特殊状态", "value": []},
        },
    }
    rules = [{"type": "list_constraint", "list_key": "maternal_special_conditions",
              "condition": 'nuchal_cord == "tight"', "value": "nuchal_cord_tight"}]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert "nuchal_cord_tight" in new_player["attributes"]["maternal_special_conditions"]["value"]


def test_nuchal_cord_not_added_when_loose():
    """loose nuchal cord does not add to conditions."""
    player = {
        "name": "测试",
        "attributes": {
            "nuchal_cord": {"name": "脐带绕颈", "value": "loose"},
            "maternal_special_conditions": {"name": "特殊状态", "value": []},
        },
    }
    rules = [{"type": "list_constraint", "list_key": "maternal_special_conditions",
              "condition": 'nuchal_cord == "tight"', "value": "nuchal_cord_tight"}]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert "nuchal_cord_tight" not in new_player["attributes"]["maternal_special_conditions"]["value"]


def test_retained_placenta_after_60_minutes():
    """retained_placenta added to maternal_special_conditions after 60 min postpartum."""
    player = {
        "name": "测试",
        "attributes": {
            "fetus_delivered": {"name": "胎儿娩出", "value": True},
            "placenta_delivered": {"name": "胎盘娩出", "value": False},
            "_time_since_fetus_delivered": {"name": "产后时间", "value": 65},
            "maternal_special_conditions": {"name": "特殊状态", "value": []},
        },
    }
    rules = [{"type": "list_constraint", "list_key": "maternal_special_conditions",
              "condition": "fetus_delivered == true and placenta_delivered == false and _time_since_fetus_delivered > 60",
              "value": "retained_placenta"}]
    new_player, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert "retained_placenta" in new_player["attributes"]["maternal_special_conditions"]["value"]


def test_retained_placenta_not_before_60_minutes():
    """No retained_placenta before 60 minutes threshold."""
    player = {
        "name": "测试",
        "attributes": {
            "fetus_delivered": {"name": "胎儿娩出", "value": True},
            "placenta_delivered": {"name": "胎盘娩出", "value": False},
            "_time_since_fetus_delivered": {"name": "产后时间", "value": 45},
            "maternal_special_conditions": {"name": "特殊状态", "value": []},
        },
    }
    rules = [{"type": "list_constraint", "list_key": "maternal_special_conditions",
              "condition": "fetus_delivered == true and placenta_delivered == false and _time_since_fetus_delivered > 60",
              "value": "retained_placenta"}]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert "retained_placenta" not in new_player["attributes"]["maternal_special_conditions"]["value"]


def test_prodromal_to_latent_transition():
    """Prodromal transitions to latent when dilation >= 3 or interval <= 300."""
    player = {
        "name": "测试",
        "attributes": {
            "labor_stage": {"name": "产程阶段", "value": "prodromal"},
            "cervical_dilation": {"name": "宫颈扩张", "value": 3},
            "contraction_interval": {"name": "宫缩间隔", "value": 400},
        },
    }
    rules = [{
        "type": "stage",
        "stage_key": "labor_stage",
        "stages": ["prodromal", "latent", "active", "transition", "pushing", "crowned", "third_stage", "postpartum"],
        "rules": [
            {"condition": "cervical_dilation >= 3 or contraction_interval <= 300", "stage": "latent"},
            {"stage": "prodromal"},
        ],
    }]
    new_player, _, events = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["labor_stage"]["value"] == "latent"


def test_prodromal_to_latent_by_interval():
    """Prodromal transitions to latent via contraction_interval condition."""
    player = {
        "name": "测试",
        "attributes": {
            "labor_stage": {"name": "产程阶段", "value": "prodromal"},
            "cervical_dilation": {"name": "宫颈扩张", "value": 2},
            "contraction_interval": {"name": "宫缩间隔", "value": 280},
        },
    }
    rules = [{
        "type": "stage",
        "stage_key": "labor_stage",
        "stages": ["prodromal", "latent", "active", "transition", "pushing", "crowned", "third_stage", "postpartum"],
        "rules": [
            {"condition": "cervical_dilation >= 3 or contraction_interval <= 300", "stage": "latent"},
            {"stage": "prodromal"},
        ],
    }]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["labor_stage"]["value"] == "latent"


def test_prodromal_stays_when_conditions_not_met():
    """Prodromal persists when dilation < 3 and interval > 300."""
    player = {
        "name": "测试",
        "attributes": {
            "labor_stage": {"name": "产程阶段", "value": "prodromal"},
            "cervical_dilation": {"name": "宫颈扩张", "value": 2},
            "contraction_interval": {"name": "宫缩间隔", "value": 400},
        },
    }
    rules = [{
        "type": "stage",
        "stage_key": "labor_stage",
        "stages": ["prodromal", "latent", "active", "transition", "pushing", "crowned", "third_stage", "postpartum"],
        "rules": [
            {"condition": "cervical_dilation >= 3 or contraction_interval <= 300", "stage": "latent"},
            {"stage": "prodromal"},
        ],
    }]
    new_player, _, _ = apply_deterministic_attributes(player, {}, tick_duration_minutes=5.0, rules=rules)
    assert new_player["attributes"]["labor_stage"]["value"] == "prodromal"
