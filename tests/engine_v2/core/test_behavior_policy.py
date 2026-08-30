"""P4-T10（Wave D）behavior_policy.py 模块单测（设计文档 §3.9 全量 + 单测口径 L583 + §6.1 行 L1656）。

依据 ``docs/v2/contracts/P4-actor-context-space-mode-design.md``：

- **§3.9（L541-584，权威）**：被测模块 ``src/engine_v2/core/behavior_policy.py``
  4 导出——:class:`BehaviorPolicy`（Protocol；B-CON-1~5 逐条）/
  :class:`PlayerPolicy`（纯标记 + ``bound_input_source`` 不透明标签）/
  :func:`run_policy_decide`（策略执行门面，唯一执行点）/
  :class:`PolicyActorMismatchError`（ValueError 族）+ 门面次序钉死
  （decide → None → actor_id 强制 → 返回；异常原样传播；不预检 base）；
- **单测口径行 L583**：B-CON-1~5 机械断言（合规类通过 + 异步 decide 拒绝 +
  双参数签名拒绝 + actor 错配拒绝 + None 合法）；``run_policy_decide`` 异常
  传播（policy 抛 ValueError → 门面不包装、原样上抛）；base 漂移不拦
  （构造 stale base 提案 → 门面放行——REJECT 归 revalidation，与 A7b 呼应）；
- **§6.1 表格行 L1656（全量）**：B-CON-1~5（同步签名机械断言、None 合法、
  actor 匹配唯一强制、异常穿透、无 base 预检——stale base 过缝由 A7b 流水线
  层面拒绝）；PlayerPolicy 子型（D-P4-02）；``run_policy_decide`` 抛
  PolicyActorMismatchError 的路径；
- **D-P4-01**（decide 同步化，偏离 D1；None = 合法 no-op）/ **D-P4-02**
  （PlayerPolicy 纯标记 + bound_input_source 不透明标签，K4：输入策略归属
  呈现层配置）/ **D-P4-03**（缝只强制 actor_id；base 漂移不预检——REJECT 归
  revalidation scheduler.py:1661-1663，KBC-3 双份事实源反模式）/ **D-P4-08**
  （capability ⊥ authority——缝不门控写授权）/ **D-P4-17**（错误两族：
  PolicyActorMismatchError 属 ValueError 族）。

**口径说明（设计口径）**：B-CON-1~5 全部为**测试侧机械断言**——协议本身不做
运行期拦截：BehaviorPolicy / PlayerPolicy 非 ``@runtime_checkable``（无
isinstance 面），``run_policy_decide`` 亦不做结构符合性检查（仅执行 B-CON-5
的 actor_id 强制 + 异常原样传播）。本文件"拒绝"措辞 = 不合规类**会被机械
检测口径检出**（``inspect.iscoroutinefunction`` / 签名参数数）——即机械检测
口径成立的断言，不是运行期拦截路径的断言。

覆盖项（每项独立 test_ 函数）：

1. B-CON-1 机械断言（D-P4-01 同步化）：合规类（decide 同步）→
   ``inspect.iscoroutinefunction(policy.decide) is False``；异步 decide 类 →
   ``iscoroutinefunction is True``（机械检测成立口径）；
2. B-CON-2 机械断言：合规类绑定方法 ``inspect.signature`` 恰 1 参数
   （context）；双参数签名类 → 参数数 != 1（机械检测成立口径）；
3. B-CON-3：返回 ActionProposal 的合规策略 → ``run_policy_decide`` 返回该
   提案（identity）；返回 None 的策略 → 门面返回 None（None 合法，D-P4-01）；
4. B-CON-4 机械断言：对样例合规策略类做类体 / 模块 import 面静态扫描
   （方法见扫描函数注释：``inspect.getsource`` + ``ast`` 类体 import / 名字
   引用面 + ``inspect.getmodule`` 模块顶层 import 面）——样例策略不持有
   random / 时钟 / 网络面（扫描 0 命中）；
5. B-CON-5：decide 返回 actor_id 与 context.actor_id 不同的提案 →
   ``run_policy_decide`` 抛 PolicyActorMismatchError（消息含两侧 actor 标识）；
   基类断言 ``issubclass(PolicyActorMismatchError, ValueError)``
   （D-P4-17 ValueError 族）；
6. 异常穿透：policy.decide 抛 ValueError → 门面不包装、原样上抛（同类型、
   同消息）；
7. base 漂移不拦：构造 stale base 提案（base_world_revision 与 context 不同）
   → 门面放行返回（stale 判定唯一属 revalidation，A7b 流水线层面拒绝——
   D-P4-03 / KBC-3）；
8. PlayerPolicy 子型（D-P4-02）：含 decide + bound_input_source 属性的类经
   ``run_policy_decide`` 正常工作；bound_input_source 取 None 与 str 两态；
   门面不读取 / 不断言该标签内容（不透明，K4）。

import 纪律（§3.4 黑名单镜像）：本文件仅 import ``ast`` / ``inspect`` /
``pytest`` + 被测模块与其契约数据类型（actions / context_provider / entity /
ids / provenance / revision）；不 import random / datetime / time / asyncio /
网络栈（测试自身确定性——无随机、无真实时钟、无网络、无 LLM）。
"""

from __future__ import annotations

import ast
import inspect

import pytest

from src.engine_v2.core.actions import ActionProposal, ActionTypeId
from src.engine_v2.core.behavior_policy import (
    BehaviorPolicy,
    PolicyActorMismatchError,
    PlayerPolicy,
    run_policy_decide,
)
from src.engine_v2.core.context_provider import ActorDecisionContext
from src.engine_v2.core.entity import EntityView
from src.engine_v2.core.ids import ActionInstanceId, EntityId, ProducerId
from src.engine_v2.core.provenance import OriginKind, Provenance
from src.engine_v2.core.revision import Revision

# —— 确定性构造常量（无随机 / 无真实时钟 / 无网络）——

_ALICE = EntityId("ent_alice")
_BOB = EntityId("ent_bob")
_BASE_REV = Revision(7)
_STALE_REV = Revision(999)
_PRODUCER = ProducerId("policy.probe")
_RAISE_MARKER = "boom-marker-42"


def _self_view(actor_id: EntityId, revision: Revision) -> EntityView:
    """构造合法 EntityView（frozen dataclass；不持有 WorldState 引用）。"""
    return EntityView(entity_id=actor_id, entity_class="npc", tags=(), revision=revision)


def _context(actor_id: EntityId = _ALICE, base: Revision = _BASE_REV) -> ActorDecisionContext:
    """构造合法 ActorDecisionContext（13 字段显式给全，无缺省可赖——漏字段构造
    响亮失败）。"""
    return ActorDecisionContext(
        actor_id=actor_id,
        tick=3,
        base_world_revision=base,
        wake_reason=None,
        self_view=_self_view(actor_id, base),
        visible_entities=frozenset({actor_id}),
        local_entity_views={},
        global_entity_views=None,
        observations=(),
        knowledge=None,
        memory=(),
        candidate_actions=(ActionTypeId("move_to"),),
        granted_capabilities=frozenset(),
    )


def _proposal(actor_id: EntityId, base: Revision) -> ActionProposal:
    """构造合法 ActionProposal（base_world_revision 必填，决策 D-13；provenance
    必填，K6）。"""
    return ActionProposal(
        proposal_id=ActionInstanceId("act_probe"),
        actor_id=actor_id,
        action_id=ActionTypeId("move_to"),
        base_world_revision=base,
        provenance=Provenance(producer_id=_PRODUCER, origin=OriginKind.BEHAVIOR_POLICY),
    )


# —— 样例策略（对 BehaviorPolicy 协议 duck-typed；协议不做运行期拦截）——


class SyncProposalPolicy:
    """B-CON-1~4 样例合规策略：同步单参 decide（B-CON-1/2），返回同一固定提案
    实例（B-CON-3 identity 断言目标）；类体与模块 import 面不持有 random /
    时钟 / 网络面（B-CON-4 静态扫描目标）。"""

    def __init__(self) -> None:
        self.proposal: ActionProposal = _proposal(_ALICE, _BASE_REV)

    def decide(self, context: ActorDecisionContext) -> ActionProposal:
        return self.proposal


class NoopPolicy:
    """B-CON-3：返回 None（本 tick 不提案，合法 no-op，D-P4-01）。"""

    def decide(self, context: ActorDecisionContext) -> ActionProposal | None:
        return None


class AsyncSamplePolicy:
    """B-CON-1 机械检测成立口径：异步 decide 类（仅作机械检测面，不经门面
    执行）。"""

    async def decide(self, context: ActorDecisionContext) -> ActionProposal | None:
        return _proposal(context.actor_id, context.base_world_revision)


class TwoParamPolicy:
    """B-CON-2 机械检测成立口径：双参数签名类（仅作机械检测面，不经门面
    执行）。"""

    def decide(self, context: ActorDecisionContext, hint: int) -> ActionProposal | None:
        return _proposal(context.actor_id, context.base_world_revision)


class OtherActorPolicy:
    """B-CON-5：返回代言非上下文 actor（_BOB）的提案。"""

    def decide(self, context: ActorDecisionContext) -> ActionProposal:
        return _proposal(_BOB, context.base_world_revision)


class RaisingPolicy:
    """覆盖项 6：decide 抛 ValueError（门面不包装、原样上抛）。"""

    def decide(self, context: ActorDecisionContext) -> ActionProposal:
        raise ValueError(_RAISE_MARKER)


class StaleBasePolicy:
    """覆盖项 7：返回 stale base 提案（base != context.base_world_revision）。

    D-P4-03 / KBC-3：缝不预检 base 漂移——stale 判定唯一属 revalidation
    （scheduler.py:1661-1663），A7b 流水线层面拒绝（F2-05）；门面预检 =
    双份事实源。"""

    def __init__(self) -> None:
        self.proposal: ActionProposal = _proposal(_ALICE, _STALE_REV)

    def decide(self, context: ActorDecisionContext) -> ActionProposal:
        return self.proposal


class PlayerSamplePolicy:
    """D-P4-02：decide + bound_input_source（不透明标签，None / str 两态）。

    decide 从不读取标签（K4：输入策略归属呈现层配置，策略不自我声明）。
    """

    def __init__(self, bound_input_source: str | None) -> None:
        self.bound_input_source = bound_input_source

    def decide(self, context: ActorDecisionContext) -> ActionProposal:
        return _proposal(context.actor_id, context.base_world_revision)


class OpaqueLabelPolicy:
    """D-P4-02 不透明标签机械证明：门面若读取 bound_input_source，该 property
    抛出使测试失败——通过 = 门面不读取 / 不断言标签内容。"""

    def decide(self, context: ActorDecisionContext) -> ActionProposal:
        return _proposal(context.actor_id, context.base_world_revision)

    @property
    def bound_input_source(self) -> str | None:
        raise RuntimeError("facade read bound_input_source (opaque label, D-P4-02/K4)")


# —— B-CON-4 静态扫描（机械断言面）——

#: 禁入面集合：随机（random）/ 时钟（time/datetime/asyncio）/ 网络
#: （socket/urllib/http/requests/aiohttp）——§3.4 黑名单口径镜像。
_FORBIDDEN_SURFACES: frozenset[str] = frozenset(
    {
        "random",
        "time",
        "datetime",
        "asyncio",
        "socket",
        "urllib",
        "http",
        "requests",
        "aiohttp",
    }
)


def _class_body_surface(cls: type) -> set[str]:
    """类体面（B-CON-4 扫描方法 ①）：``inspect.getsource`` + ``ast.parse``——
    类体内 import 的模块根名 + ``ast.Name`` 引用 id + ``ast.Attribute`` 链最左
    根名（覆盖 ``random.random()`` 类引用）。字符串字面量（含 docstring）为
    ``ast.Constant``，不计入名字引用面。"""
    tree = ast.parse(inspect.getsource(cls))
    class_def = tree.body[0]
    assert isinstance(class_def, ast.ClassDef)
    surface: set[str] = set()
    for node in ast.walk(class_def):
        if isinstance(node, ast.Import):
            surface.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                surface.add(node.module.split(".")[0])
        elif isinstance(node, ast.Name):
            surface.add(node.id)
        elif isinstance(node, ast.Attribute):
            root: ast.expr = node
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                surface.add(root.id)
    return surface


def _module_import_surface(cls: type) -> set[str]:
    """模块 import 面（B-CON-4 扫描方法 ②）：``inspect.getmodule`` 定位类所在
    模块，仅扫模块顶层 import 的模块根名（import 面，非模块体全部名字引用）。
    """
    module = inspect.getmodule(cls)
    assert module is not None
    tree = ast.parse(inspect.getsource(module))
    surface: set[str] = set()
    for node in tree.body:  # 仅顶层语句
        if isinstance(node, ast.Import):
            surface.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                surface.add(node.module.split(".")[0])
    return surface


# —— 覆盖项 1：B-CON-1 机械断言（decide 同步化，D-P4-01）——


def test_bcon1_sync_decide_is_not_coroutine_function() -> None:
    # 合规类（decide 同步）：机械检测为非协程函数
    assert inspect.iscoroutinefunction(SyncProposalPolicy().decide) is False


def test_bcon1_async_decide_is_coroutine_function() -> None:
    # 异步 decide 类：机械检测口径成立（检出为协程函数）
    assert inspect.iscoroutinefunction(AsyncSamplePolicy().decide) is True


# —— 覆盖项 2：B-CON-2 机械断言（签名 = 单参数 context）——


def test_bcon2_compliant_decide_has_single_context_param() -> None:
    # 合规类绑定方法：inspect.signature 恰 1 参数（context）
    params = inspect.signature(SyncProposalPolicy().decide).parameters
    assert len(params) == 1
    assert list(params) == ["context"]


def test_bcon2_two_param_signature_is_mechanically_detected() -> None:
    # 双参数签名类：机械检测口径成立（参数数 != 1）
    params = inspect.signature(TwoParamPolicy().decide).parameters
    assert len(params) != 1
    assert list(params) == ["context", "hint"]


# —— 覆盖项 3：B-CON-3（返回 ActionProposal | None；None 合法，D-P4-01）——


def test_bcon3_facade_returns_the_same_proposal_instance() -> None:
    policy = SyncProposalPolicy()
    context = _context()
    # 门面返回策略返回的同一提案实例（identity，非拷贝）
    assert run_policy_decide(policy, context) is policy.proposal


def test_bcon3_none_return_is_legal_noop() -> None:
    # D-P4-01：None = 本 tick 不提案（不进流水线、不产 trace 失败记录）
    assert run_policy_decide(NoopPolicy(), _context()) is None


# —— 覆盖项 4：B-CON-4 机械断言（不持有 random/时钟/网络面）——


def test_bcon4_sample_policy_holds_no_forbidden_surface() -> None:
    # 类体面：0 命中
    body_hits = _class_body_surface(SyncProposalPolicy) & _FORBIDDEN_SURFACES
    assert body_hits == frozenset()
    # 模块 import 面：0 命中
    module_hits = _module_import_surface(SyncProposalPolicy) & _FORBIDDEN_SURFACES
    assert module_hits == frozenset()


# —— 覆盖项 5：B-CON-5（actor 匹配唯一强制；ValueError 族，D-P4-17）——


def test_bcon5_actor_mismatch_raises_with_both_ids_in_message() -> None:
    context = _context(_ALICE)
    with pytest.raises(PolicyActorMismatchError) as excinfo:
        run_policy_decide(OtherActorPolicy(), context)
    message = str(excinfo.value)
    # 消息含两侧 actor 标识（提案侧 _BOB + 上下文侧 _ALICE）
    assert str(_BOB) in message
    assert str(_ALICE) in message


def test_bcon5_error_is_value_error_family() -> None:
    # D-P4-17：错误分类两族——PolicyActorMismatchError 属 ValueError 族
    # （沿用 P1/P2/P3 既有二族风格，非 RuntimeError 族）
    assert issubclass(PolicyActorMismatchError, ValueError) is True


# —— 覆盖项 6：异常穿透（门面不包装、原样上抛）——


def test_facade_propagates_policy_value_error_unwrapped() -> None:
    with pytest.raises(ValueError) as excinfo:
        run_policy_decide(RaisingPolicy(), _context())
    # 同类型：精确型 ValueError（未包装为他型异常，亦未落入
    # PolicyActorMismatchError 子类）+ 同消息
    assert type(excinfo.value) is ValueError
    assert str(excinfo.value) == _RAISE_MARKER


# —— 覆盖项 7：base 漂移不拦（D-P4-03 / KBC-3；REJECT 归 revalidation/A7b）——


def test_base_drift_is_not_prechecked_by_facade() -> None:
    # D-P4-03：缝只强制 actor_id——base_world_revision 漂移不预检（stale 判定
    # 唯一属 revalidation 门 scheduler.py:1661-1663，A7b 流水线层面拒绝；门面
    # 预检 = 双份事实源，KBC-3 反模式）。故门面必须放行 stale base 提案。
    context = _context(_ALICE, base=_BASE_REV)
    policy = StaleBasePolicy()
    result = run_policy_decide(policy, context)
    assert result is policy.proposal
    assert result.base_world_revision == _STALE_REV
    assert result.base_world_revision != context.base_world_revision


# —— 覆盖项 8：PlayerPolicy 子型（D-P4-02 纯标记 + 不透明标签）——


def test_player_policy_is_behavior_policy_subtype() -> None:
    # 结构锚：PlayerPolicy 经 MRO 承继 BehaviorPolicy（纯标记，不新增必选
    # 方法）；bound_input_source 以注解形态出现（不透明标签，非方法）
    assert BehaviorPolicy in PlayerPolicy.__mro__
    assert "bound_input_source" in PlayerPolicy.__annotations__
    assert callable(getattr(PlayerPolicy, "decide", None))


@pytest.mark.parametrize("bound_input_source", [None, "usb://gamepad-0"], ids=["none", "str"])
def test_player_policy_works_through_facade(bound_input_source: str | None) -> None:
    # 标签取 None / str 两态：门面两态均正常工作，标签值不被消费 / 修改
    policy = PlayerSamplePolicy(bound_input_source=bound_input_source)
    context = _context()
    result = run_policy_decide(policy, context)
    assert result is not None
    assert result.actor_id == context.actor_id
    assert policy.bound_input_source == bound_input_source


def test_player_policy_label_is_opaque_to_facade() -> None:
    # 门面不读取 / 不断言标签内容（不透明，K4）：OpaqueLabelPolicy 的
    # bound_input_source 为抛出 property——门面若读取即抛；通过 = 门面只调
    # decide
    context = _context()
    result = run_policy_decide(OpaqueLabelPolicy(), context)
    assert result is not None
    assert result.actor_id == context.actor_id
