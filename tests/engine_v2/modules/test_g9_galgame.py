"""P9 W6 g9 galgame 样例切片测试（SOT §6.1 / §3.16.1；A1–A5 + A 前件）。

样例面（SOT §3.19 白名单行 31–35）：``tests/fixtures/
v2_project_galgame/``（game.yaml / world / characters×2 / items；
1 地点 + 2 角色 + 1 物品；零 prompts 节——模板由宿主经 ``prompt_root``
参数落盘，W1 先例形状）。

宿主协议面（SOT §3.16.1；conftest ``p9_host`` 工厂，本包追加面）：
加载（零 ERROR 前件）→ 世界构建（grid 域 ``world``）→ 模块面注册 →
``host.tick(n)`` 相位循环（wakeup → policy 决策 → 执行器 → K2 应用）。

实体 ID 词表：世界实体 / 效果 target / 上下文 actor_id = 规范型
``ent_authoring_<slug>``（conftest 追加面常量钉）；宿主方法面入参与
组件 payload = authoring slug 词表。

断言面 = SOT §8.2：A1（对话回合 + 同源 delta）/ A2（wakeup → policy
提案 talk）/ A3（关系落位组件面 + 分支钉值）/ A4（感知记录 ≥2 sight，
零 event-text 面）/ A5（叙事视图 JSON-clean + 世界哈希不变，P9-INV-8）
/ A 前件（零 ERROR 加载）。
"""

from __future__ import annotations

import json

from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.content.loader import load_project
from src.engine_v2.content.project_ir import build_ir
from src.engine_v2.content.validator import validate_project
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.revision import Revision
from src.engine_v2.modules import dialogue, narration
from src.engine_v2.modules.dialogue import (
    DialogueResult,
    dialogue_relationship_delta,
    run_dialogue,
)
from src.engine_v2.modules.narration import (
    NarrativeFrame,
    NarrativeStyle,
    render_narrative_view,
)
from src.engine_v2.modules.perception import (
    ObservationSource,
    PerceptionRange,
    build_observations,
)
from src.engine_v2.modules.relationships import adjust_relationship

_GALGAME = "tests/fixtures/v2_project_galgame"
_PLAYER = "ent_authoring_player_1"
_YUKI = "ent_authoring_yuki"
_LENA = "ent_authoring_lena"
#: A1/A3 对话钉面（DEV-W6-1 正分支：utterance 谢谢 ×1 → +0.05；
#: response 零标记 → 净 +0.05）。
_utterance = "谢谢你昨天帮我找资料。"
_response = "不客气，这是我应该做的。"


def test_g9_galgame_t1_dialogue(p9_host) -> None:
    """A1：player talk → ``run_dialogue``（脚本化回应）→
    ``DialogueResult`` 含回应文本；delta = 同源函数钉值。"""
    host = p9_host(
        _GALGAME,
        backend_script={("npc_dialogue", Revision(0), 1): _response},
    )
    result = run_dialogue(
        host.world,
        _PLAYER,
        _YUKI,
        _utterance,
        host.backend,
        host.policies[_YUKI],
        tick=1,
    )
    assert isinstance(result, DialogueResult)
    assert result.speaker_id == _PLAYER
    assert result.respondent_id == _YUKI
    assert result.utterance == _utterance
    assert result.response == _response
    assert result.tick == 1
    # 同源断言（SOT §8.2 A1）：结果 delta == 同源自函数
    assert result.relationship_delta == dialogue_relationship_delta(
        result.utterance, result.response
    )
    # DEV-W6-1 钉值：谢谢 ×1（+0.05），response 零标记
    assert result.relationship_delta == 0.05
    # 推理调用面（脚本 backend 恰 1 次；logical_role 钉面）
    assert len(host.backend.calls) == 1
    assert host.backend.calls[0].logical_role == "npc_dialogue"
    # K2 零世界写：对话回合不进 world（revision 恒 0）
    assert host.world.world_revision == Revision(0)


def test_g9_galgame_t2_character_policy(p9_host, tmp_path) -> None:
    """A2：``enqueue_actor_wakeup(yuki)`` → 宿主驱动
    ``run_policy_decide``（脚本 backend）→ yuki 提案 ``talk``（参数含
    player 引用）；backend 恰 1 次调用。"""
    script = (
        '{"action_id": "talk", "arguments": {"target": "player_1"},'
        ' "intent": "greet", "confidence": 0.9}'
    )
    host = p9_host(
        _GALGAME,
        backend_script={("npc_policy", Revision(0), 1): script},
        prompt_root=tmp_path,
    )
    assert host.backend.calls == ()
    host.enqueue_wakeup("yuki", 1, "scene")
    host.tick(1)
    assert len(host.proposals) == 1
    proposal = host.proposals[0]
    assert str(proposal.actor_id) == _YUKI
    assert str(proposal.action_id) == "talk"
    assert proposal.arguments["target"] == "player_1"
    assert str(proposal.proposal_id) == "act_ent_authoring_yuki_1"
    assert len(host.backend.calls) == 1
    assert host.backend.calls[0].logical_role == "npc_policy"


def test_g9_galgame_t3_relationship_update(p9_host) -> None:
    """A3：对话结果 → ``adjust_relationship`` 落位 → yuki→player
    affinity 变化 = ``dialogue_relationship_delta`` 钉值，事件在组件面
    可见（K2 管道 ``core.set_component`` → 组件面）。"""
    host = p9_host(
        _GALGAME,
        backend_script={("npc_dialogue", Revision(0), 1): _response},
    )
    result = run_dialogue(
        host.world,
        _PLAYER,
        _YUKI,
        _utterance,
        host.backend,
        host.policies[_YUKI],
        tick=1,
    )
    delta = result.relationship_delta
    assert delta == dialogue_relationship_delta(_utterance, _response)
    assert delta == 0.05

    # W2 落位（初始 0.5 → 0.5 + delta；同浮点算术，无近似）
    initial = host.relationships["yuki"][0].affinity
    assert initial == 0.5
    new_states, event = adjust_relationship(
        host.relationships["yuki"], "yuki", "player_1", delta, "dialogue", 1
    )
    assert event.old == 0.5
    assert event.new == initial + delta
    assert event.target_id == "player_1"
    host.place_relationships("yuki", new_states)

    # 组件面可见（A3 断言面；K2 提交 → revision 推进）
    component = host.world.entities[EntityId(_YUKI)].components[
        ComponentTypeId("p9.relationships")
    ]
    assert component["holder_id"] == "yuki"
    assert component["entries"][0]["target_id"] == "player_1"
    assert component["entries"][0]["affinity"] == initial + delta
    assert host.world.world_revision == Revision(1)
    assert len(host.effects) == 1

    # 分支钉值（DEV-W6-1）：负分支（威胁类）×1 → -0.10；零分支 → 0.0
    assert dialogue_relationship_delta("我要警告你。", "哼。") == -0.10
    assert dialogue_relationship_delta("嗯。", "好的。") == 0.0


def test_g9_galgame_t4_observation(p9_host) -> None:
    """A4：player 于教室 → ``build_observations`` 产出 yuki/lena 的
    ``ObservationRecord``（sight，≥2 条）；记录零 event-text 面
    （P9-INV-7 最小 JSON 载荷）。"""
    host = p9_host(_GALGAME)
    positions = host.world_positions("world")
    assert positions[_PLAYER] == {"x": 1, "y": 1}
    assert positions[_YUKI] == {"x": 2, "y": 1}
    assert positions[_LENA] == {"x": 0, "y": 2}

    # 感知半径 = fixture PlayerSpec.capabilities 投影（宿主职责面）
    source = ObservationSource(observer_id=_PLAYER, domain="world", tick=1)
    result = build_observations(
        positions,
        {_PLAYER: PerceptionRange(sight_m=8.0, hearing_m=12.0)},
        {_YUKI: {"name": "雪见"}, _LENA: {"name": "蕾娜·索蕾尔"}},
        source,
    )
    observed = {
        (record.payload["entity_id"], record.payload["kind"])
        for record in result.records
    }
    assert (_YUKI, "sight") in observed
    assert (_LENA, "sight") in observed
    assert len(result.records) >= 2
    for record in result.records:
        # 记录载荷 = 最小 JSON 面（零 event-text 字段，P9-INV-7）
        assert set(record.payload) == {"kind", "entity_id", "distance_m"}
        assert record.actor_id == _PLAYER
        assert record.tick == 1
        assert record.cause_event_id is None
    # 曼哈顿距离钉（grid 域语义）
    distances = {
        record.payload["entity_id"]: record.payload["distance_m"]
        for record in result.records
    }
    assert distances == {_YUKI: 1, _LENA: 2}


def test_g9_galgame_t5_narrative_view(p9_host) -> None:
    """A5：``render_narrative_view`` → ``NarrativeView``（JSON-clean；
    含 tick/frames/actors_visible）；修改 view dict 后 WorldState 哈希
    不变（P9-INV-8；DEV-W6-7 哈希面）。"""
    host = p9_host(_GALGAME)
    frames = (
        NarrativeFrame(
            tick=1,
            speaker_id=_PLAYER,
            text="谢谢你昨天帮我找资料。",
            mood="grateful",
        ),
        NarrativeFrame(tick=2, speaker_id=_YUKI, text="不客气，这是我应该做的。"),
    )
    style = NarrativeStyle(
        style_description="温暖克制的轻叙事",
        style_example="午后，教室的窗光很轻。",
    )
    view = render_narrative_view(host.world, frames, style, tick=2)

    # 键面 + 内容钉
    assert set(view) == {"tick", "scene_text", "frames", "actors_visible", "clock"}
    assert view["tick"] == 2
    assert view["clock"] == {"tick": 2}
    assert [entry["speaker_id"] for entry in view["frames"]] == [_PLAYER, _YUKI]
    assert view["frames"][0]["mood"] == "grateful"
    assert "mood" not in view["frames"][1]
    assert view["actors_visible"] == [_PLAYER, _YUKI]
    assert "（例：" in view["scene_text"]
    assert "[tick=1]" in view["scene_text"]

    # JSON-clean（P9-INV-8：round-trip 相等）
    encoded = json.dumps(view, ensure_ascii=False, sort_keys=True)
    assert json.loads(encoded) == view

    # 修改 view dict（删 1 键 + 改 1 值）→ 世界哈希不变
    baseline = host.world_hash()
    del view["clock"]
    view["tick"] = 999
    view["frames"].append({"tick": 9, "speaker_id": _LENA, "text": "……"})
    assert host.world_hash() == baseline


def test_g9_galgame_t6_project_loads() -> None:
    """A 前件：项目加载（``load_project`` → ``build_ir`` →
    ``validate_project`` 零 ERROR）+ 内容面钉。"""
    result = load_project(_GALGAME)
    assert result.raw is not None
    assert [d for d in result.diagnostics if d.severity.value == "ERROR"] == []
    ir_result = build_ir(result.raw)
    assert ir_result.ir is not None
    validation = validate_project(ir_result.ir, result.raw)
    assert validation.ok
    assert [
        d for d in validation.diagnostics if d.severity.value == "ERROR"
    ] == []
    # 内容面钉（SOT §3.19 galgame 样例形状）
    ir = ir_result.ir
    assert [c.id for c in ir.characters] == ["lena", "yuki"]
    assert ir.player.player_id == "player_1"
    assert ir.manifest.project_id == "galgame"
    assert ir.scenario.id == "scenario_galgame"
    # 波内身份点钉（R1 补充 F1-1；A18/A21 波内点面；15 文件台账钉 =
    # W7 test_module_face t2/t5）：
    assert tuple(dialogue.__all__) == (
        "DialogueResult", "dialogue_relationship_delta", "run_dialogue"
    )
    assert (
        dialogue.IDENTITY.module_id,
        dialogue.IDENTITY.version,
        dialogue.IDENTITY.requires,
    ) == (
        "llmsim-standard-dialogue",
        "1",
        ("llmsim-standard-character", "llmsim-standard-relationships"),
    )
    assert tuple(narration.__all__) == (
        "NarrativeFrame", "NarrativeStyle", "NarrativeView",
        "render_narrative_view",
    )
    assert (
        narration.IDENTITY.module_id,
        narration.IDENTITY.version,
        narration.IDENTITY.requires,
    ) == ("llmsim-standard-narration", "1", ())
