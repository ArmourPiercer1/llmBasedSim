"""P10 Web 会话层：SessionManager / WebSession（T05；SOT §3.7；导出 6 名）。

来源 = Spec §45 主流程（宿主面 EngineInstance）+ §35 web adapter（协议
翻译）+ Plan §19（EngineInstance / SessionManager）；43.2-8「Web
singleton session」移除落点 = 零单例 / 零模块级实例（P10-INV-4，A3
AST，v1 src/web/app.py:221 单例反例锚）；43.3-9「web session
lifecycle」重写落点 = 本模块。

冻结消费面（只读）：core ``state``（``WorldState`` / ``RuntimeState``）
/ core ``snapshot``（``snapshot`` / ``restore_snapshot``）/ core
``actions``（``ActionProposal``）/ core ``behavior_policy``（
``PlayerPolicy`` 标记面，behavior_policy.py:70）/ core ``provenance``
（``Provenance`` / ``OriginKind``）/ P8 ``persistence.snapshot``（
``to_persistence_snapshot`` / ``dump_persistence_snapshot`` /
``load_persistence_snapshot`` / ``check_persistence_versions``）/ P10
W1 ``presentation.view``（``derive_scene_view``）/ W2
``presentation.image.contract``（``ImageArtifact`` / ``ImageSlot`` /
``ImageStalePolicy`` / ``apply_image_result``）/ W2
``presentation.image.director``（``derive_render_intent``）/ W3
``presentation.image.backend``（``ImageBackend`` Protocol）/ P8 邻接
``devtools.trace_query``（``TraceQuery``，会话注入 trace_records →
只读查询视图，W5 inspector/workbench 数据源）。

纪律（P10-INV-1/2/4/10，D6，K5/K8）：

- Session = (WorldState 实例 + 注入宿主驱动 + presentation 组件
  （image_backend / stale_policy）+ presentation 状态（view 缓存 /
  intent 史 / current_image + ImageSlot / TraceQuery / save 名列表）
  + 命令闭集处理)（D-P10-05）；
- SessionManager = 显式实例（create/load/get/list/close），由 api 层 /
  宿主 / 测试注入；**零模块级实例**（A3 AST）；会话隔离 = 独立 dict
  槽（A12/t2 零跨会话共享可变状态）；
- **session_id 缺省 uuid4().hex = 身份标签例外（DEV-P10-05，P10 唯一
  非确定性默认；Leader 终审 §4 裁定）**：session_id 属容器身份面（非
  模拟状态、非 view/snapshot/任何确定性派生面输入）；全部测试必须显式
  传 session_id（A12/t2 隔离双跑显式钉 id，零缺省依赖）；
- 自由文本 = TemplatePlayerPolicy（确定性模板，零真实推理，K5）→
  driver.advance → 重派生 view +（image_backend 非 None 时）
  derive_render_intent → render → apply_image_result（§3.3 缺省
  DISCARD，D-P10-11）→ 新 state_snapshot；命令文本不经 policy
  （命令分派先行，闭集 8 名，Leader 终审 Q5 裁定：v1 help 文案 /c
  别名不承接）；
- state_snapshot = JSON-clean（P10-INV-10）**24 键**面（v1
  snapshot():442 语义参照；键名闭集 = 私有常量
  :data:`SESSION_SNAPSHOT_KEYS`，t3 断言键集 == 常量、零硬编码清单；
  24 键逐字钉于 :meth:`WebSession.state_snapshot` docstring，Leader
  终审 Q4 裁定）。
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from typing import Final, Protocol

from src.engine_v2.core.actions import (
    ActionInstanceId,
    ActionProposal,
    ActionTypeId,
)
from src.engine_v2.core.behavior_policy import PlayerPolicy
from src.engine_v2.core.components import ComponentTypeId
from src.engine_v2.core.ids import EntityId, ProducerId
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.snapshot import restore_snapshot, snapshot
from src.engine_v2.core.state import RuntimeState, WorldState
from src.engine_v2.core.trace import TraceRecord
from src.engine_v2.devtools.trace_query import TraceQuery
from src.engine_v2.persistence.snapshot import (
    check_persistence_versions,
    dump_persistence_snapshot,
    load_persistence_snapshot,
    to_persistence_snapshot,
)
from src.engine_v2.presentation.image.backend import ImageBackend
from src.engine_v2.presentation.image.contract import (
    ImageArtifact,
    ImageSlot,
    ImageStalePolicy,
    apply_image_result,
)
from src.engine_v2.presentation.image.director import derive_render_intent
from src.engine_v2.presentation.view import SceneView, derive_scene_view

__all__ = [
    "SESSION_COMMANDS",
    "TickDriver",
    "TemplatePlayerPolicy",
    "WebSession",
    "SessionManager",
    "SessionNotFoundError",
]

#: 命令闭集 8 名（SOT §3.7 逐字；v1 handle_command 语义参照 + v1 help
#: 文案 /stop 面；v1 help 文案 /c 别名不承接——Leader 终审 Q5 裁定；
#: t6 逐字钉）。
SESSION_COMMANDS: Final[tuple[str, ...]] = (
    "/help",
    "/status",
    "/idid",
    "/see",
    "/hear",
    "/feel",
    "/save",
    "/stop",
)

#: state_snapshot 键名闭集（私有常量；24 键，~24 键面 Leader 终审 Q4
#: 裁定；t3 断言键集 == 本常量，零硬编码清单）。
SESSION_SNAPSHOT_KEYS: Final[tuple[str, ...]] = (
    "started",
    "world_name",
    "world_description",
    "tick",
    "view_revision",
    "scene_id",
    "game_phase",
    "game_time",
    "time_of_day",
    "weather",
    "narrative",
    "summary",
    "senses",
    "self_action_summary",
    "hidden_event_count",
    "player",
    "player_attributes",
    "npc_dynamics",
    "recent_events",
    "narrative_history",
    "can_continue",
    "tick_duration_minutes",
    "has_long_image_task",
    "image_slot",
)

#: 玩家 / actor 面（世界实体 class / tag 词表，W1 view.py 同串约定）。
_PLAYER_CLASS: Final[str] = "player"
_ACTOR_TAG: Final[str] = "actor"

#: 数值表组件（fixture 世界 attributes 组件载荷键 = ``attributes``）。
_ATTRIBUTES_COMPONENT: Final[ComponentTypeId] = ComponentTypeId("attributes")

#: 确定性常量（P10 零 uuid4 纪律：本模块唯一 uuid4 = create_session
#: 缺省路径，DEV-P10-05）。
_WEB_PRODUCER: Final[ProducerId] = ProducerId("web.player")
_TALK_ACTION_ID: Final[ActionTypeId] = ActionTypeId("talk")
_WORLD_INSTANCE_ID: Final[str] = "wsi_p10_web"
_PROPOSAL_ID_PREFIX: Final[str] = "act_web_talk_"
_PROPOSAL_ID_DIGEST_LEN: Final[int] = 12

#: 命令 / 快照面确定性文案（v1 handle_command / snapshot 语义参照）。
_HELP_TEXT: Final[str] = "命令: /help, /status, /idid, /see, /hear, /feel, /save <name>, /stop"
_NO_ACTION_TEXT: Final[str] = "你本回合没有特别的行为。"
_STATUS_MODAL_TITLE: Final[str] = "数值状态"
_SENSE_MODAL_TITLES: Final[dict[str, str]] = {
    "/idid": "你做了什么",
    "/see": "你看到的",
    "/hear": "你听到的",
    "/feel": "你感觉到的",
}
_SAVE_COMMAND: Final[str] = "/save"

#: 界限量（recent_events / narrative_history 面，确定性截断）。
_RECENT_EVENTS_LIMIT: Final[int] = 8
_NARRATIVE_HISTORY_LIMIT: Final[int] = 8


class SessionNotFoundError(Exception):
    """会话缺失（api 404 面；AD-P10-1 错误信封族）。

    ``get`` / 操作目标会话已 close（manager 已移除）→ 本错误族；
    ``session_id`` 属性 = 缺失会话标签（稳定面）。
    """

    def __init__(self, session_id: str) -> None:
        super().__init__(f"session {session_id!r} not found")
        self.session_id = session_id


class SessionExistsError(Exception):
    """会话 id 已存在（api 409 面；私有具名错误族，不进 __all__，
    P9 layout.py 私有错误先例 + ERR-P10-13「按 code 区分」裁定）。"""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"session {session_id!r} already exists")
        self.session_id = session_id


class SessionPausedError(Exception):
    """会话已暂停（/stop 后；api 409 面；私有具名错误族，不进
    __all__）。paused = 命令面状态位，非容器移除（close 才移除）。"""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"session {session_id!r} is paused")
        self.session_id = session_id


class CommandError(Exception):
    """命令面违例（api 400 面；私有具名错误族，不进 __all__）。

    - 未知命令（``/`` 前缀但不在 :data:`SESSION_COMMANDS` 闭集——/c
      不承接，Leader 终审 Q5 裁定）；
    - ``/save`` 缺名 / 空名（语法 = ``/save <name>``）。
    """

    def __init__(self, command: str, detail: str) -> None:
        super().__init__(f"{command}: {detail}")
        self.command = command
        self.detail = detail


class TickDriver(Protocol):
    """宿主循环注入点（SOT §3.7 逐字面：``advance(world) -> None``）。

    宿主循环契约（Leader 终审 Q6 裁定：P10 Protocol only + conftest
    最小宿主；生产 = P1 runtime 面（未来），§0.4 非范围——P10 零宿主
    循环实现）：宿主持有权威世界引用——``advance`` 后宿主的 ``world``
    槽 = 推进后世界（宿主相位可为整体替换，如逻辑刻推进 + 事务 commit
    +1 revision；WorldState = frozen 模型，revision 面不可原地推进，
    整体替换 = 唯一合法面，core state.py:333–367 私有缝隙同族）。
    会话层在每次 ``advance`` 后单点重读宿主 ``world`` 槽（私有
    ``_host_world`` 面）；宿主无 ``world`` 槽属性时回落 = 传入世界
    （原地变更宿主面，v1 语义参照）。
    """

    def advance(self, world: WorldState) -> None: ...


def _host_world(driver: TickDriver, world: WorldState) -> WorldState:
    """宿主世界槽重读面（conftest 最小宿主 ``world`` 槽属性；缺失 →
    fallback = 传入世界，即原地变更宿主面）。"""
    slot = getattr(driver, "world", None)
    return slot if isinstance(slot, WorldState) else world


def _player_actor_id(world: WorldState) -> str | None:
    """玩家 actor 判定（确定性）：``entity_class == "player"`` 排序最
    小 id；缺省 → 首个 actor-tag 实体（排序）；皆无 → None（模板
    policy 面 → ValueError fail-loud；投影面 → 空面）。"""
    player_ids = sorted(
        str(entity_id)
        for entity_id, record in world.entities.items()
        if record.entity_class == _PLAYER_CLASS
    )
    if player_ids:
        return player_ids[0]
    actor_ids = sorted(
        str(entity_id)
        for entity_id, record in world.entities.items()
        if _ACTOR_TAG in record.tags
    )
    return actor_ids[0] if actor_ids else None


class TemplatePlayerPolicy:
    """确定性模板玩家策略（SOT §3.7；K5 零真实推理）。

    - 自由文本 → talk ActionProposal（arguments 含原文；零网络 / 零
      推理调用）；命令文本不经 policy（命令分派先行，SOT §3.7/§3.8
      闭集）；
    - 实现 core ``PlayerPolicy`` 标记面（behavior_policy.py:70：
      ``bound_input_source`` 不透明标签，D-P4-02）；调用面 = SOT §3.7
      裁定签名 ``decide(*, world, text) -> ActionProposal``（确定性
      模板签名，区别于 core BehaviorPolicy 的 context 签名——注入
      policy 须同面，SOT §3.7 表）；
    - 确定性：proposal_id = ``act_web_talk_<revision>_<text sha256
      前 12 位 hex>``（零 uuid4）；actor = :func:`_player_actor_id`
      面；provenance = web.player / behavior_policy（Spec §16.2
      writer 家族）。
    """

    def __init__(self) -> None:
        self.bound_input_source: str | None = None

    def decide(self, *, world: WorldState, text: str) -> ActionProposal:
        """自由文本 → talk ActionProposal（纯函数面；同输入恒同输出，
        D6）。"""
        actor_id = _player_actor_id(world)
        if actor_id is None:
            raise ValueError("世界无 player/actor 实体，无法生成 talk 提案")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return ActionProposal(
            proposal_id=ActionInstanceId(
                _PROPOSAL_ID_PREFIX
                + str(int(world.world_revision))
                + "_"
                + digest[:_PROPOSAL_ID_DIGEST_LEN]
            ),
            actor_id=EntityId(actor_id),
            action_id=_TALK_ACTION_ID,
            arguments={"text": text},
            intent=text,
            base_world_revision=world.world_revision,
            provenance=Provenance(
                producer_id=_WEB_PRODUCER, origin=OriginKind.BEHAVIOR_POLICY
            ),
        )


class WebSession:
    """单个 web 会话（SOT §3.7；D-P10-05 注入式多会话容器成员）。

    会话 = (WorldState 实例 + 注入宿主驱动 + presentation 组件
    （image_backend / stale_policy）+ presentation 状态（SceneView
    缓存 / RenderIntent 史（continuity 源）/ current_image +
    ImageSlot / TraceQuery / save 名列表）+ 命令闭集处理)。

    自由文本流（step）：TemplatePlayerPolicy（注入 player_policy 同
    面优先）→ ``driver.advance``（宿主相位）→ 重派生 view（缓存替换，
    P10-INV-1 零反作用）→（image_backend 非 None）
    ``derive_render_intent``（continuity = intent 全史，导演取尾 ≤3）
    → ``render`` → ``apply_image_result``（§3.3 缺省 DISCARD）→ 新
    state_snapshot。图像槽回投 = 本会话 apply_image_result 后单点
    （W2 contract docstring 钉的 W4 落点；字节存 current_image，
    槽面 JSON-clean 零 bytes，P10-INV-10）。

    命令闭集（step 前缀分派；:data:`SESSION_COMMANDS` 8 名）：
    /help → message 面；/status → 数值 modal 面；/idid → 本回合行为
    modal 面；/see /hear /feel → 感知 modal 面（v2 无感知子系统 →
    items 空面，v1 title 逐字）；/save <name> → P8 dump 链经注入
    save_sink（缺省 = 会话内 memory dict，零缺省磁盘写）；/stop →
    暂停位（后续 step → SessionPausedError，api 409 面）。

    零模块级实例（P10-INV-4）；会话间零共享可变状态（A12/t2）。
    """

    def __init__(
        self,
        session_id: str,
        world: WorldState,
        driver: TickDriver,
        *,
        player_policy: PlayerPolicy | None = None,
        image_backend: ImageBackend | None = None,
        stale_policy: ImageStalePolicy = ImageStalePolicy.DISCARD,
        trace_records: Sequence[TraceRecord] = (),
        save_sink: object | None = None,
    ) -> None:
        self._session_id = session_id
        self._driver = driver
        self._player_policy = player_policy
        self._image_backend = image_backend
        self._stale_policy = stale_policy
        self._trace_query = TraceQuery(tuple(trace_records))
        self._save_sink: MutableMapping[str, str] = (
            save_sink if isinstance(save_sink, MutableMapping) else {}
        )
        self._world = _host_world(driver, world)
        self._view = derive_scene_view(self._world)
        self._intents: list[object] = []
        self._image_slot: ImageSlot | None = None
        self._current_image: ImageArtifact | None = None
        self._narrative_history: list[str] = [str(self._view["narrative"]["scene_text"])]
        self._last_action_text = ""
        self._save_names: list[str] = []
        self._paused = False
        self._closed = False

    # —— 身份 / 只读投影面 ——

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def save_names(self) -> tuple[str, ...]:
        """save 名列表（只读投影；W5 inspector branch_replay 消费面）。"""
        return tuple(self._save_names)

    def view(self) -> SceneView:
        """当前 SceneView 缓存（重派生 = step 后单点；零重计算）。"""
        return self._view

    def image(self) -> ImageArtifact | None:
        """current_image（bytes + 标签；槽面 = state_snapshot image_slot
        键；无图 → None，api 404 面）。"""
        return self._current_image

    def close(self) -> None:
        """关闭会话（manager.close 调用后移除出容器；close 后 get →
        SessionNotFoundError）。"""
        self._closed = True

    # —— 命令 / 自由文本分派 ——

    def step(self, player_input: str) -> dict[str, object]:
        """一步宿主推进（SOT §3.7）：命令文本 → 命令面；自由文本 →
        policy → 宿主相位 → 重派生 view → 图像流 → 新 state_snapshot。

        空 / 纯空白输入 → 零推进 no-op（返回当前 state_snapshot；
        api 层已钉 text 非空，本面 = 直调稳健面）。
        """
        self._ensure_live()
        text = player_input.strip()
        if not text:
            return self.state_snapshot()
        command = text.lower()
        if command == "/help":
            return self._command_result(message=_HELP_TEXT)
        if command == "/status":
            return self._command_result(modal=self._status_modal())
        if command == "/idid":
            return self._command_result(
                modal=self._sense_modal(
                    _SENSE_MODAL_TITLES["/idid"],
                    (self._last_action_text or _NO_ACTION_TEXT,),
                )
            )
        if command in ("/see", "/hear", "/feel"):
            return self._command_result(
                modal=self._sense_modal(_SENSE_MODAL_TITLES[command])
            )
        if command == "/stop":
            self._paused = True
            return self.state_snapshot()
        if command == _SAVE_COMMAND:
            raise CommandError(command, "需要名字（语法 /save <name>）")
        if command.startswith(_SAVE_COMMAND + " "):
            name = text[len(_SAVE_COMMAND + " "):].strip()
            if not name:
                raise CommandError(command, "名字必须非空")
            self._save(name)
            return self._command_result(message=f"已保存到 {name}")
        if command.startswith("/"):
            raise CommandError(
                command,
                f"未知命令（闭集 = SESSION_COMMANDS 8 名；/c 不承接）",
            )
        return self._advance_free_text(text)

    def _ensure_live(self) -> None:
        """存活门禁：closed → SessionNotFoundError（manager 已移除，
        直调同族）；paused → SessionPausedError（api 409 面）。"""
        if self._closed:
            raise SessionNotFoundError(self._session_id)
        if self._paused:
            raise SessionPausedError(self._session_id)

    def _command_result(
        self, *, message: str | None = None, modal: dict[str, object] | None = None
    ) -> dict[str, object]:
        """命令结果 = state_snapshot + 附加面（message / modal，v1
        handle_command 同形）。"""
        result: dict[str, object] = self.state_snapshot()
        if message is not None:
            result["message"] = message
        if modal is not None:
            result["modal"] = modal
        return result

    def _sense_modal(self, title: str, items: tuple[str, ...] = ()) -> dict[str, object]:
        """感知 / 行为 modal 面（v1 title 逐字；v2 无感知子系统 → items
        缺省空面）。"""
        return {"title": title, "items": list(items)}

    def _status_modal(self) -> dict[str, object]:
        """数值 modal 面（/status；items = 玩家 attributes 数值表，
        key 排序确定性）。"""
        items = [
            {"key": key, "value": value}
            for key, value in sorted(self._player_attributes().items())
        ]
        return {"title": _STATUS_MODAL_TITLE, "items": items}

    def _advance_free_text(self, text: str) -> dict[str, object]:
        """自由文本推进（SOT §3.7 逐字流）：policy → driver.advance →
        重派生 view →（image_backend 非 None）intent → render →
        apply_image_result → narrative 史 → 新 state_snapshot。"""
        policy = self._player_policy or TemplatePlayerPolicy()
        proposal = policy.decide(world=self._world, text=text)
        text_arg = proposal.arguments.get("text")
        self._last_action_text = text_arg if isinstance(text_arg, str) else text
        self._driver.advance(self._world)
        self._world = _host_world(self._driver, self._world)
        self._view = derive_scene_view(self._world)
        if self._image_backend is not None:
            intent = derive_render_intent(
                self._view, continuity=tuple(self._intents)
            )
            self._intents.append(intent)
            artifact = self._image_backend.render(intent)
            self._image_slot = apply_image_result(
                self._image_slot, artifact, self._view, policy=self._stale_policy
            )
            if self._image_slot is not None:
                self._current_image = artifact
        self._narrative_history.append(str(self._view["narrative"]["scene_text"]))
        if len(self._narrative_history) > _NARRATIVE_HISTORY_LIMIT:
            self._narrative_history = self._narrative_history[
                -_NARRATIVE_HISTORY_LIMIT:
            ]
        return self.state_snapshot()

    # —— state_snapshot 24 键面 ——

    def state_snapshot(self) -> dict[str, object]:
        """JSON-clean（P10-INV-10）24 键面（v1 snapshot():442 语义
        参照；键名闭集 = :data:`SESSION_SNAPSHOT_KEYS`；24 键逐字钉，
        Leader 终审 Q4 裁定）：

        - ``started``：bool——会话持世界且未 close（v1 = bool(state)；
          v2 create/load 皆持世界，close 会话经 manager 移除不出现在
          快照面 → 活会话恒 True）；
        - ``world_name`` / ``world_description``：主 location 展示面
          （view environment 投影，v1 world_name / world_description）；
        - ``tick``：世界侧逻辑刻（view 投影，v1 tick）；
        - ``view_revision``：world.world_revision 投影（v2 新增，
          P10-INV-2 会话面）；
        - ``scene_id``：view scene_id（v2 新增，D-P10-12 会话面）；
        - ``game_phase``：scenario_state.stage 或 ""（v1 game_phase
          语义对齐，v2 无 ended 判定面）；
        - ``game_time``：view clock.game_time 或 {}（v1 语义对齐）；
        - ``time_of_day`` / ``weather``：view environment 投影（v1
          语义对齐）；
        - ``narrative`` / ``summary``：view narrative scene_text
          （v1 narrative / summary 语义对齐，v2 同源）；
        - ``senses``：list——[]（v1 感知投影面；v2 无感知子系统 →
          确定性空面）；
        - ``self_action_summary``：最近一次自由文本（v1 语义对齐；
          无 → ""）；
        - ``hidden_event_count``：int——0（v1 语义对齐；v2 无隐藏
          事件子系统 → 确定性 0）；
        - ``player``：玩家 actor 投影 dict（view actors 面：id /
          name / position / mood；无玩家 → {}，v1 player 语义对齐）；
        - ``player_attributes``：玩家 attributes 组件数值表（v1
          player_attributes 语义对齐；无 → {}）；
        - ``npc_dynamics``：非玩家 actor 投影 list（id / name /
          mood；v1 npc_dynamics action 键语义 = mood 面对齐，v2 无
          action 子系统）；
        - ``recent_events``：注入 trace 流 domain_events 尾 ≤8 投影
          （event_id / event_type / world_revision / source_system；
          SOT §3.7「事件投影 ≤8」；无 → []）；
        - ``narrative_history``：narrative 史尾 ≤8（构造刻 scene_text
          为首条；v1 语义对齐 + 界限量确定性截断）；
        - ``can_continue``：bool——未暂停（v1 = phase/刻界判定；v2
          会话无界 → 暂停位为唯一终止面）；
        - ``tick_duration_minutes``：float——0.0（v1 确定性 0.0 对齐）；
        - ``has_long_image_task``：bool——False（v1 残留 has_long_task
          改名，SOT §3.7 逐字：v2 = 图像生成任务面；W4 同步 step 模型
          零在途任务 → 确定性 False，异步长任务 = P11+ 面）；
        - ``image_slot``：ImageSlot 7 键投影（v2 新增；无图 → None；
          bytes 不入面，P10-INV-10）。
        """
        view = self._view
        environment = view["environment"]
        clock = view["clock"]
        game_time = clock["game_time"]
        player_id = _player_actor_id(self._world)
        player = next(
            (actor for actor in view["actors"] if actor["id"] == player_id), {}
        )
        return {
            "started": not self._closed,
            "world_name": environment["location"],
            "world_description": environment["description"],
            "tick": view["tick"],
            "view_revision": view["view_revision"],
            "scene_id": view["scene_id"],
            "game_phase": self._world.scenario_state.stage or "",
            "game_time": dict(game_time) if isinstance(game_time, Mapping) else {},
            "time_of_day": environment["time_of_day"],
            "weather": environment["weather"],
            "narrative": view["narrative"]["scene_text"],
            "summary": view["narrative"]["scene_text"],
            "senses": [],
            "self_action_summary": self._last_action_text,
            "hidden_event_count": 0,
            "player": dict(player),
            "player_attributes": self._player_attributes(),
            "npc_dynamics": [
                {
                    "id": actor["id"],
                    "name": actor["name"],
                    "mood": actor["mood"],
                }
                for actor in view["actors"]
                if actor["id"] != player_id
            ],
            "recent_events": self._recent_events(),
            "narrative_history": list(self._narrative_history),
            "can_continue": not self._paused,
            "tick_duration_minutes": 0.0,
            "has_long_image_task": False,
            "image_slot": dict(self._image_slot)
            if self._image_slot is not None
            else None,
        }

    def _player_attributes(self) -> dict[str, object]:
        """玩家 attributes 数值表（组件载荷 ``attributes`` 键；无 →
        {}）。"""
        player_id = _player_actor_id(self._world)
        if player_id is None:
            return {}
        payload = self._world.component_view(player_id, _ATTRIBUTES_COMPONENT)
        if payload is None:
            return {}
        value = payload.get("attributes")
        return dict(value) if isinstance(value, Mapping) else {}

    def _recent_events(self) -> list[dict[str, object]]:
        """注入 trace 流 domain_events 尾 ≤8 投影（SOT §3.7 事件投影
        面；确定性输入序）。"""
        events = self._trace_query.domain_events()
        tail = events[-_RECENT_EVENTS_LIMIT:]
        return [
            {
                "event_id": str(event.event_id),
                "event_type": str(event.event_type),
                "world_revision": int(event.world_revision),
                "source_system": str(event.source_system),
            }
            for event in tail
        ]

    # —— /save 面（P8 dump 链）——

    def _save(self, name: str) -> None:
        """/save：core snapshot → P8 信封 → dump 文本 → save_sink（缺省
        = 会话内 memory dict，零缺省磁盘写，SOT §3.7）。

        runtime 面 = 世界侧逻辑刻投影重建（P1 D-6 单一单调计数镜像；
        权威 tick 宿主面，会话层零时钟状态）；world_instance_id =
        :data:`_WORLD_INSTANCE_ID` 确定性常量（D-9 信封层身份）。
        """
        core_snapshot = snapshot(self._world, self._runtime(), _WORLD_INSTANCE_ID)
        envelope = to_persistence_snapshot(core_snapshot)
        payload = dump_persistence_snapshot(envelope)
        self._save_sink[name] = payload
        self._save_names.append(name)

    def _runtime(self) -> RuntimeState:
        """会话 runtime 投影面（P1 D-6；save 链消费，零时钟状态）。"""
        return RuntimeState(logical_tick=int(self._view["tick"]))


class SessionManager:
    """注入式多会话容器（SOT §3.7；D-P10-05；零模块级实例，A3 AST）。

    - ``create_session(world, *, session_id=None, **kwargs)``：新会话；
      session_id 缺省 = uuid4().hex（DEV-P10-05 身份标签例外，P10
      唯一非确定性默认）；重复 id → SessionExistsError（api 409 面）；
      driver / image_backend = kwargs 显式注入优先 → 工厂 → 皆无 →
      ValueError（fail-loud）；kwargs 余面 = WebSession 可选面
      （player_policy / stale_policy / trace_records / save_sink）；
    - ``load_session(session_id, payload)``：P8
      ``load_persistence_snapshot``（fail-loud 四道门）+ 版本检查
      （``check_persistence_versions``；非空 → ValueError）→ 新会话
      （world 自快照重建，SOT §3.7 逐字）；
    - ``get(session_id)``：缺失 / 已 close → SessionNotFoundError
      （api 404 面）；
    - ``list_sessions()``：排序面（确定性）；
    - ``close(session_id)``：会话 close + 容器移除（close 后 get →
      SessionNotFoundError）；
    - 会话隔离 = 独立 dict 槽（A12/t2）；零跨会话共享可变状态
      （P10-INV-4）。
    """

    def __init__(
        self,
        *,
        driver_factory: Callable[[], TickDriver] | None = None,
        image_backend_factory: Callable[[], ImageBackend] | None = None,
    ) -> None:
        self._sessions: dict[str, WebSession] = {}
        self._driver_factory = driver_factory
        self._image_backend_factory = image_backend_factory

    def create_session(
        self, world: WorldState, *, session_id: str | None = None, **kwargs: object
    ) -> str:
        """新会话（SOT §3.7 签名逐字）；返回 session_id。"""
        if session_id is None:
            session_id = uuid.uuid4().hex
        if session_id in self._sessions:
            raise SessionExistsError(session_id)
        driver: object = kwargs.pop("driver", None)
        if driver is None and self._driver_factory is not None:
            driver = self._driver_factory()
        if driver is None:
            raise ValueError("create_session 需要 driver（kwargs）或 driver_factory")
        image_backend: object = kwargs.pop("image_backend", None)
        if image_backend is None and self._image_backend_factory is not None:
            image_backend = self._image_backend_factory()
        session = WebSession(
            session_id,
            world,
            driver,  # type: ignore[arg-type]
            image_backend=image_backend,  # type: ignore[arg-type]
            **kwargs,  # type: ignore[arg-type]
        )
        self._sessions[session_id] = session
        return session_id

    def load_session(self, session_id: str, payload: str | bytes) -> str:
        """P8 快照 → 新会话（SOT §3.7：load + 版本检查 → 新会话，
        world 自快照重建）。"""
        if session_id in self._sessions:
            raise SessionExistsError(session_id)
        envelope = load_persistence_snapshot(payload)
        issues = check_persistence_versions(envelope)
        if issues:
            raise ValueError("P8 版本检查非空：" + "；".join(issues))
        if self._driver_factory is None:
            raise ValueError("load_session 需要 driver_factory")
        world, _runtime = restore_snapshot(envelope.snapshot)
        image_backend = (
            self._image_backend_factory()
            if self._image_backend_factory is not None
            else None
        )
        session = WebSession(
            session_id, world, self._driver_factory(), image_backend=image_backend
        )
        self._sessions[session_id] = session
        return session_id

    def get(self, session_id: str) -> WebSession:
        """按 id 取会话；缺失 → SessionNotFoundError（api 404 面）。"""
        try:
            return self._sessions[session_id]
        except KeyError:
            raise SessionNotFoundError(session_id) from None

    def list_sessions(self) -> tuple[str, ...]:
        """会话 id 元组（排序面，确定性）。"""
        return tuple(sorted(self._sessions))

    def close(self, session_id: str) -> None:
        """关闭并移除会话（close 后 get → SessionNotFoundError）。"""
        session = self.get(session_id)
        session.close()
        del self._sessions[session_id]
