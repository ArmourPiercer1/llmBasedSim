"""P4 Wave D 模块单测：``space.py``（设计文档 §3.7 全量 + 单测口径行 L443 + §6.1 L1654 行）。

依据 ``docs/v2/contracts/P4-actor-context-space-mode-design.md``（下称"设计文档"）：

- **§3.7 代码块（L333-439）**：18 导出（上半 10 + 下半 8）；构造期不变量
  **S-INV-1**（domain_id 匹配 ``^[a-z][a-z0-9_]*$``，pydantic pattern）/
  **S-INV-2**（backend_kind ∈ SPATIAL_BACKEND_KINDS，Spec:1354-1361 六类词表）；
  **G-INV**（节点 id 非空串 / 自环边 a==b 拒绝 / 重复无向边 (a,b)≡(b,a) 拒绝 /
  边端点未声明拒绝）；**S-INV-3**（一实体同一域至多一个映射）/ **S-INV-4**
  （registry 键 == domain.domain_id）/ **S-INV-5**（backend_kind ↔ backend
  isinstance 核对：graph→GraphSpace / grid→GridSpace）；
- **单测口径行（L443）**：SpatialDomain 两 INV 构造拒绝（大写 id / 词表外
  kind）；GraphSpace 自环/重复边/未知端点拒绝 + BFS 三态（同节点 0.0、两跳
  2.0、不可达 INF）+ 邻接排序；GridSpace 越界 w/h 拒绝 + 四邻序与出界裁剪 +
  曼哈顿 + 行主序 + 位置校验五拒绝（缺键/多键/浮点/负值/越界）；S-INV-3/4/5
  三拒绝；make_backend 六 kind 分派（graph/grid 成功 + 四 reserved 拒绝）；
  spaces 编解码 roundtrip + 重复 domain 拒绝 + entity_domain_positions
  缺失/在位；
- **§6.1 模块单测表（L1654 行）**：S-INV-1~5 / G-INV（BFS float；INF
  不可达）/ Grid（w×h>0；4-邻 up/right/down/left；越界拒绝；Manhattan）/
  make_backend reserved → UnknownBackendError / entity_domain_positions 域过滤；
- **D-P4-10（position = 不透明 JsonValue，backend 自校验）**：P4 无全局位置
  校验器，合法性由各 backend ``validate_position`` 判定，非法 →
  InvalidPositionError（graph = 已声明节点 id；grid = 恰含 x/y 两键 int 且
  界内）；
- **D-P4-11（backend 只读配置 / INV-P4-3）**：无公开变更 API，GraphSpace /
  GridSpace / SpaceRegistry 全部几何构造期注入，四方法全纯，运行期零状态
  变更（本文件不构造任何变更面断言，构造后只读）；
- **D-P4-12（距离语义）**：graph = BFS 跳数（float 返回），grid = 曼哈顿；
  4-邻 = 上/右/下/左固定序（出界裁剪）；``INF_DISTANCE = float("inf")`` 是
  纯函数返回值，**永不**写入任何组件/事件（JSON 无法表达 inf；spaces codec
  只编码位置映射、不编码距离）——测试中禁止对其 dump_json，只做值断言
  （isinf）；
- **D-P4-13（空间映射 = spaces 组件，域内唯一）**：载荷形状
  ``{"mappings": [{domain_id, position, entered_tick}, ...]}``（载荷序）；
  一实体同一域至多一个映射（S-INV-3，重复 → SpaceInvariantError），可映射
  多个域；
- **D-P4-17（错误分类两族）**：LookupError 族 = UnknownDomainError /
  UnknownBackendError；ValueError 族 = InvalidPositionError /
  SpaceInvariantError；测试按族断言基类。

覆盖项（逐项独立命名，对应 test_ 函数）：

1. SpatialDomain 两 INV 构造拒绝：
   - ``test_spatial_domain_s_inv_1_rejects_invalid_domain_id``：大写
     domain_id（及首位数字 / 首位下划线 / 连字符）→ pydantic ValidationError
     （S-INV-1 模式 ``^[a-z][a-z0-9_]*$``）；小写+数字+下划线对照构造成功；
   - ``test_spatial_domain_s_inv_2_rejects_unknown_backend_kind``：词表外
     backend_kind → 具名 SpaceInvariantError（直接构造路径还原，消息含
     S-INV-2 标记，D-P4-17 ValueError 族）；六类词表内 kind 构造通过对照；
2. GraphSpace G-INV 拒绝 + BFS 三态 + 邻接排序：
   - ``test_graph_space_g_inv_rejects_self_loop``：自环边（a==b）→
     SpaceInvariantError（消息含 G-INV 标记）；
   - ``test_graph_space_g_inv_rejects_duplicate_edge``：重复无向边
     （(a,b)≡(b,a) 与同向重复）→ SpaceInvariantError；无重复对照成功；
   - ``test_graph_space_g_inv_rejects_undeclared_endpoint``：边端点未声明
     → SpaceInvariantError；
   - ``test_graph_space_bfs_distance_three_states``：同节点 0.0 / 两跳 2.0
     （float 返回口径，一跳对照 1.0）/ 不可达 INF_DISTANCE（math.isinf；
     D-P4-12：INF 永不入 JSON，测试只做值断言、禁止 dump_json）；
   - ``test_graph_space_neighbors_casefold_sorted_tuple``：neighbors /
     positions 返回 tuple（非 list）且节点序 = casefold 排序（与 ASCII 序
     可区分的节点集）；未声明位置 → InvalidPositionError（D-P4-10 自校验）；
3. GridSpace：
   - ``test_grid_space_rejects_invalid_dimensions``：w/h ≤ 0 与非 int
     （含 bool / float，逐维参数化）→ SpaceInvariantError；合法正 int 对照；
   - ``test_grid_space_neighbors_up_right_down_left_clipped``：四邻固定序
     上/右/下/左 + 出界裁剪（中心全四邻 / 角点裁两邻 / 1×1 空邻）；
   - ``test_grid_space_manhattan_distance``：|dx|+|dy|（float 返回）；同位置
     0.0；
   - ``test_grid_space_positions_row_major``：positions() = 行主序（y 外层
     0..h-1，x 内层 0..w-1）全枚举（tuple）；
   - ``test_grid_space_validate_position_five_rejections``：位置校验五拒绝
     （缺键 / 多键 / 浮点 / 负值 / 越界）+ 非 Mapping 输入 →
     InvalidPositionError（D-P4-10；D-P4-17 ValueError 族）；合法位置通过；
4. S-INV-3/4/5 三拒绝：
   - ``test_s_inv_3_duplicate_domain_rejected_named_error``：mappings 重复
     domain（S-INV-3，D-P4-13 域内唯一）→ 具名还原 SpaceInvariantError
     （house 模式：解码信封 model_validator 抛带 S-INV-3 标记 ValueError →
     decode_spaces 还原具名类型，与 SpatialDomain.__init__ 同纪律），消息含
     S-INV-3 标记，非裸 pydantic ValidationError；
   - ``test_s_inv_4_registry_key_must_match_domain_id``：registry 键 !=
     domain.domain_id → SpaceInvariantError；合法双域注册表对照（domain /
     backend 查找 + domain_ids() 排序元组 + 未注册查找 →
     UnknownDomainError，LookupError 族查找点抛出）；
   - ``test_s_inv_5_backend_kind_must_match_backend_class``：backend_kind
     'graph' 配非 GraphSpace / 'grid' 配非 GridSpace → SpaceInvariantError
     （isinstance 核对双向）；
5. make_backend 六 kind 分派：
   - ``test_make_backend_graph_and_grid_dispatch``：graph / grid 构造成功，
     断言返回类型（GraphSpace / GridSpace）+ 行为抽查；SPATIAL_BACKEND_KINDS
     与 Spec:1354-1361 六类词表（小写 token 化）逐值相等；
   - ``test_make_backend_reserved_kinds_rejected``：四 reserved kind（hex /
     continuous2d / continuous3d / custom）→ UnknownBackendError（显式拒绝，
     不静默降级；D-P4-17 LookupError 族）；
6. spaces 编解码 + entity_domain_positions：
   - ``test_spaces_encode_decode_roundtrip``：encode_spaces →
     decode_spaces 与原 tuple 相等（载荷序保持）；D-P4-13 载荷形状逐字断言
     （entered_tick 缺省 0 参与编码）；畸形载荷（多余键，extra="forbid"）→
     pydantic ValidationError 原样透传（不吞、不具名还原）；
   - ``test_decode_spaces_rejects_duplicate_domain``：codec 重复 domain 拒绝
     （覆盖项 4 S-INV-3 同一拒绝面的行为面：同域不同 position 重复 / 同
     position 重复均拒绝——唯一性按 domain_id 判，不按位置值）；双域对照
     通过；
   - ``test_entity_domain_positions_missing_component``：无 spaces 组件 →
     {}（组件缺失非错误）；
   - ``test_entity_domain_positions_present_domain_filter``：组件在位 →
     {domain_id: position}（载荷序）；域过滤口径（§6.1 L1654 / 设计文档
     L512）：输出恰为组件所载域集合——不在组件中的域无映射、不出现、不
     崩溃，函数只读组件、不经 registry。

布局：``tests/engine_v2/core/``；直接从子模块 import，不经包级导出；全部用例
无网络、无 LLM、无 API key；确定性构造（EntityId / Revision 构造函数不做
词法校验，设计文档 §2.2 通用规则）。
"""

from __future__ import annotations

import math

import pytest
from pydantic import JsonValue, ValidationError

from src.engine_v2.core.entity import EntityView
from src.engine_v2.core.ids import EntityId
from src.engine_v2.core.revision import Revision
from src.engine_v2.core.space import (
    INF_DISTANCE,
    GraphSpace,
    GridSpace,
    InvalidPositionError,
    SPACES_COMPONENT,
    SPATIAL_BACKEND_KINDS,
    SpaceInvariantError,
    SpaceMapping,
    SpaceRegistry,
    SpatialDomain,
    UnknownBackendError,
    UnknownDomainError,
    decode_spaces,
    entity_domain_positions,
    encode_spaces,
    make_backend,
)

# —— 样本工厂（自包含、确定性构造）——


def _overworld_mappings() -> tuple[SpaceMapping, ...]:
    """双域映射样本（overworld grid 坐标 + tactical 图节点，G4-3 双映射像）。"""
    return (
        SpaceMapping(domain_id="overworld", position={"x": 0, "y": 0}, entered_tick=3),
        SpaceMapping(domain_id="tactical", position="t0"),  # entered_tick 缺省 0
    )


def _view_with_spaces(payload: dict[str, JsonValue] | None) -> EntityView:
    """构造仅带（或不带）spaces 组件的 EntityView。"""
    components = {SPACES_COMPONENT: payload} if payload is not None else {}
    return EntityView(
        entity_id=EntityId("ent_alice"),
        entity_class=None,
        tags=(),
        revision=Revision(0),
        components=components,
    )


# —— 覆盖项 1：SpatialDomain 两 INV 构造拒绝（S-INV-1 / S-INV-2）——


def test_spatial_domain_s_inv_1_rejects_invalid_domain_id() -> None:
    """覆盖项 1a：S-INV-1 —— domain_id 必须匹配 ``^[a-z][a-z0-9_]*$``（构造期
    拒绝，pydantic pattern → ValidationError）。"""
    for bad_id in ("Overworld", "9lives", "_city", "over-world"):
        with pytest.raises(ValidationError):
            SpatialDomain(domain_id=bad_id, backend_kind="grid")
    # 对照：小写首 + 数字 + 下划线合法
    domain = SpatialDomain(domain_id="overworld_2", backend_kind="grid")
    assert domain.domain_id == "overworld_2"
    assert domain.backend_kind == "grid"
    assert domain.parameters == {}


def test_spatial_domain_s_inv_2_rejects_unknown_backend_kind() -> None:
    """覆盖项 1b：S-INV-2 —— backend_kind 词表外（Spec:1354-1361 六类之外）→
    具名 SpaceInvariantError（直接构造路径；D-P4-17 ValueError 族）。"""
    with pytest.raises(SpaceInvariantError) as excinfo:
        SpatialDomain(domain_id="overworld", backend_kind="cylindrical")
    assert "S-INV-2" in str(excinfo.value)
    # 具名还原（house 模式）：不是裸 pydantic ValidationError
    assert type(excinfo.value) is SpaceInvariantError
    assert isinstance(excinfo.value, ValueError)
    # 对照：六类词表内 kind 构造全部通过（词表本体检断在覆盖项 5）
    for kind in sorted(SPATIAL_BACKEND_KINDS):
        assert SpatialDomain(domain_id="d", backend_kind=kind).backend_kind == kind


# —— 覆盖项 2：GraphSpace G-INV 拒绝 + BFS 三态 + 邻接排序 ——


def test_graph_space_g_inv_rejects_self_loop() -> None:
    """覆盖项 2a：G-INV —— 自环边（a==b）构造期拒绝。"""
    with pytest.raises(SpaceInvariantError) as excinfo:
        GraphSpace(nodes=["a", "b"], edges=[("a", "a")])
    assert "G-INV" in str(excinfo.value)
    assert "自环" in str(excinfo.value)
    assert isinstance(excinfo.value, ValueError)  # D-P4-17 族


def test_graph_space_g_inv_rejects_duplicate_edge() -> None:
    """覆盖项 2b：G-INV —— 重复无向边（(a,b)≡(b,a)）构造期拒绝。"""
    with pytest.raises(SpaceInvariantError):
        GraphSpace(nodes=["a", "b"], edges=[("a", "b"), ("b", "a")])
    with pytest.raises(SpaceInvariantError):
        GraphSpace(nodes=["a", "b"], edges=[("a", "b"), ("a", "b")])
    # 对照：无重复边构造成功
    space = GraphSpace(nodes=["a", "b", "c"], edges=[("a", "b"), ("b", "c")])
    assert space.positions() == ("a", "b", "c")


def test_graph_space_g_inv_rejects_undeclared_endpoint() -> None:
    """覆盖项 2c：G-INV —— 边端点未在 nodes 声明构造期拒绝。"""
    with pytest.raises(SpaceInvariantError) as excinfo:
        GraphSpace(nodes=["a", "b"], edges=[("a", "z")])
    assert "G-INV" in str(excinfo.value)
    assert "未声明" in str(excinfo.value)


def test_graph_space_bfs_distance_three_states() -> None:
    """覆盖项 2d：BFS 三态（D-P4-12 距离语义）。

    同节点 0.0 / 两跳 2.0（float 返回口径）/ 不可达 → ``INF_DISTANCE``
    （``float("inf")``）。**D-P4-12**：INF_DISTANCE 是纯函数返回值，永不写入
    任何组件/事件（JSON 无法表达 inf；spaces codec 只编码位置映射、不编码
    距离）——故本测试只做值断言（isinf），禁止对其 dump_json。
    """
    space = GraphSpace(nodes=["a", "b", "c", "z"], edges=[("a", "b"), ("b", "c")])
    # 同节点
    assert space.distance("a", "a") == 0.0
    # 两跳（a→b→c），float 返回口径
    assert space.distance("a", "c") == 2.0
    assert isinstance(space.distance("a", "c"), float)
    # 一跳对照
    assert space.distance("a", "b") == 1.0
    # 不可达：z 为孤立节点 → INF_DISTANCE（永不入 JSON，只做值断言）
    assert space.distance("a", "z") == INF_DISTANCE
    assert math.isinf(space.distance("a", "z"))
    assert INF_DISTANCE == float("inf")


def test_graph_space_neighbors_casefold_sorted_tuple() -> None:
    """覆盖项 2e：neighbors / positions 返回 tuple（非 list）且节点序 =
    casefold 排序（D-P4-12 确定性序）。

    节点集 ``{"a", "b", "C"}``：casefold 序 a<b<c → ("a", "b", "C")；ASCII 序
    将得 ("C", "a", "b")——两序可区分，断言即钉死 casefold 而非默认排序。
    """
    space = GraphSpace(nodes=["a", "b", "C"], edges=[("a", "b"), ("a", "C")])
    # positions()：casefold 排序 tuple
    assert space.positions() == ("a", "b", "C")
    assert isinstance(space.positions(), tuple)
    # neighbors("a") = {"b", "C"}：casefold 序 ("b", "C")（ASCII 序将得 ("C", "b")）
    neighbors = space.neighbors("a")
    assert neighbors == ("b", "C")
    assert isinstance(neighbors, tuple) and not isinstance(neighbors, list)
    assert space.neighbors("b") == ("a",)
    assert space.neighbors("C") == ("a",)
    # D-P4-10：未声明节点 id 位置自校验拒绝
    with pytest.raises(InvalidPositionError):
        space.neighbors("z")
    with pytest.raises(InvalidPositionError):
        space.distance("a", "z")


# —— 覆盖项 3：GridSpace ——


@pytest.mark.parametrize(
    ("width", "height"),
    [
        (0, 3),  # w ≤ 0
        (3, 0),  # h ≤ 0
        (-2, 3),  # 负值
        (True, 3),  # bool 拒绝
        (3.0, 3),  # float 拒绝
        (3, True),  # bool 拒绝
        (3, 2.5),  # float 拒绝
    ],
)
def test_grid_space_rejects_invalid_dimensions(width: object, height: object) -> None:
    """覆盖项 3a：w/h ≤ 0 或非 int（含 bool / float）→ SpaceInvariantError
    （Leader 裁定：确定性不静默）。"""
    with pytest.raises(SpaceInvariantError):
        GridSpace(width=width, height=height)
    # 对照：合法正 int
    assert GridSpace(width=1, height=1).positions() == ({"x": 0, "y": 0},)


def test_grid_space_neighbors_up_right_down_left_clipped() -> None:
    """覆盖项 3b：四邻固定序 上/右/下/左 + 出界裁剪（D-P4-12）。"""
    grid = GridSpace(width=3, height=3)
    # 中心点：四邻全在，序 = 上/右/下/左
    assert grid.neighbors({"x": 1, "y": 1}) == (
        {"x": 1, "y": 0},  # 上
        {"x": 2, "y": 1},  # 右
        {"x": 1, "y": 2},  # 下
        {"x": 0, "y": 1},  # 左
    )
    # 角点：上/左出界裁剪，剩余序仍 右→下
    assert grid.neighbors({"x": 0, "y": 0}) == ({"x": 1, "y": 0}, {"x": 0, "y": 1})
    # 1×1 网格：四邻全出界 → 空
    assert GridSpace(width=1, height=1).neighbors({"x": 0, "y": 0}) == ()
    # 返回 tuple（非 list）
    assert isinstance(grid.neighbors({"x": 1, "y": 1}), tuple)


def test_grid_space_manhattan_distance() -> None:
    """覆盖项 3c：distance = 曼哈顿 |dx|+|dy|（float 返回；网格全可达，
    INF_DISTANCE 永不出现）。"""
    grid = GridSpace(width=4, height=3)
    assert grid.distance({"x": 0, "y": 0}, {"x": 2, "y": 1}) == 3.0
    assert isinstance(grid.distance({"x": 0, "y": 0}, {"x": 2, "y": 1}), float)
    assert grid.distance({"x": 3, "y": 2}, {"x": 3, "y": 2}) == 0.0


def test_grid_space_positions_row_major() -> None:
    """覆盖项 3d：positions() = 行主序全枚举（y 外层 0..h-1，x 内层
    0..w-1），tuple 返回。"""
    grid = GridSpace(width=3, height=2)
    assert grid.positions() == (
        {"x": 0, "y": 0},
        {"x": 1, "y": 0},
        {"x": 2, "y": 0},
        {"x": 0, "y": 1},
        {"x": 1, "y": 1},
        {"x": 2, "y": 1},
    )
    assert isinstance(grid.positions(), tuple)


def test_grid_space_validate_position_five_rejections() -> None:
    """覆盖项 3e：位置校验五拒绝（缺键 / 多键 / 浮点 / 负值 / 越界，D-P4-10
    backend 自校验）→ InvalidPositionError；非 Mapping 输入同拒；合法位置
    通过。"""
    grid = GridSpace(width=3, height=2)
    bad_positions: tuple[object, ...] = (
        {"x": 0},  # 缺键（缺 y）
        {"y": 0},  # 缺键（缺 x）
        {"x": 0, "y": 0, "z": 0},  # 多键
        {"x": 0.0, "y": 0},  # 浮点值
        {"x": 0, "y": 0.5},  # 浮点值
        {"x": -1, "y": 0},  # 负值
        {"x": 0, "y": -2},  # 负值
        {"x": 3, "y": 0},  # 越界（x == width）
        {"x": 0, "y": 2},  # 越界（y == height）
        "0,0",  # 非 Mapping
    )
    for bad in bad_positions:
        with pytest.raises(InvalidPositionError):
            grid.validate_position(bad)
    # D-P4-17：InvalidPositionError 归 ValueError 族
    with pytest.raises(ValueError):
        grid.validate_position({"x": 3, "y": 0})
    # 对照：合法位置通过校验（不抛）
    grid.validate_position({"x": 2, "y": 1})


# —— 覆盖项 4：S-INV-3/4/5 三拒绝 ——


def test_s_inv_3_duplicate_domain_rejected_named_error() -> None:
    """覆盖项 4a：S-INV-3（域内唯一，D-P4-13）——mappings 重复 domain → 具名
    还原 SpaceInvariantError。

    house 模式（源码 L478-489 解码信封 model_validator 抛带 S-INV-3 标记的
    ValueError → 源码 L498-501 decode_spaces 还原为具名类型，与
    SpatialDomain.__init__ + _s_inv_2_message 同纪律）：断言非裸 pydantic
    ValidationError，消息含 S-INV-3 标记，D-P4-17 按族断言 ValueError 基类。
    """
    payload = {
        "mappings": [
            {"domain_id": "overworld", "position": {"x": 0, "y": 0}, "entered_tick": 0},
            {"domain_id": "overworld", "position": {"x": 1, "y": 1}, "entered_tick": 1},
        ]
    }
    with pytest.raises(SpaceInvariantError) as excinfo:
        decode_spaces(payload)
    assert "S-INV-3" in str(excinfo.value)
    assert type(excinfo.value) is SpaceInvariantError
    assert isinstance(excinfo.value, ValueError)


def test_s_inv_4_registry_key_must_match_domain_id() -> None:
    """覆盖项 4b：S-INV-4 —— registry 键必须 == domain.domain_id，否则
    SpaceInvariantError。

    对照（合法双域注册表，INV-P4-3 只读）：domain / backend 查找 +
    domain_ids() 排序元组 + 未注册查找 → UnknownDomainError（LookupError
    族，查找点抛出，D-P3-16 双轨同纪律）。
    """
    city = SpatialDomain(domain_id="city", backend_kind="grid")
    with pytest.raises(SpaceInvariantError) as excinfo:
        SpaceRegistry({"overworld": (city, GridSpace(width=2, height=2))})
    assert "S-INV-4" in str(excinfo.value)
    assert "overworld" in str(excinfo.value)

    # 对照：键 == domain_id 的双域注册表
    overworld = SpatialDomain(domain_id="overworld", backend_kind="graph")
    overworld_backend = GraphSpace(nodes=["a", "b"], edges=[("a", "b")])
    registry = SpaceRegistry(
        {
            "city": (city, GridSpace(width=2, height=2)),
            "overworld": (overworld, overworld_backend),
        }
    )
    assert registry.domain("city").domain_id == "city"
    assert registry.backend("overworld") is overworld_backend
    assert registry.domain_ids() == ("city", "overworld")  # 排序元组
    assert issubclass(UnknownDomainError, LookupError)  # D-P4-17 族
    with pytest.raises(UnknownDomainError):
        registry.domain("tavern")
    with pytest.raises(UnknownDomainError):
        registry.backend("tavern")


def test_s_inv_5_backend_kind_must_match_backend_class() -> None:
    """覆盖项 4c：S-INV-5 —— backend_kind ↔ backend isinstance 核对
    （graph→GraphSpace / grid→GridSpace），不一致 → SpaceInvariantError
    （双向：graph 配 GridSpace / grid 配 GraphSpace）。"""
    graph_domain = SpatialDomain(domain_id="d_graph", backend_kind="graph")
    with pytest.raises(SpaceInvariantError) as excinfo:
        SpaceRegistry({"d_graph": (graph_domain, GridSpace(width=2, height=2))})
    assert "S-INV-5" in str(excinfo.value)
    assert "GridSpace" in str(excinfo.value)

    grid_domain = SpatialDomain(domain_id="d_grid", backend_kind="grid")
    with pytest.raises(SpaceInvariantError) as excinfo:
        SpaceRegistry(
            {"d_grid": (grid_domain, GraphSpace(nodes=["a", "b"], edges=[("a", "b")]))}
        )
    assert "S-INV-5" in str(excinfo.value)
    assert "GraphSpace" in str(excinfo.value)


# —— 覆盖项 5：make_backend 六 kind 分派 ——


def test_make_backend_graph_and_grid_dispatch() -> None:
    """覆盖项 5a：graph / grid 构造成功（断言返回类型 + 行为抽查）；
    SPATIAL_BACKEND_KINDS 与 Spec:1354-1361 六类词表（小写 token 化）逐值
    相等。"""
    assert SPATIAL_BACKEND_KINDS == frozenset(
        {"graph", "grid", "hex", "continuous2d", "continuous3d", "custom"}
    )

    graph_backend = make_backend(
        "graph", {"nodes": ["a", "b", "c"], "edges": [["a", "b"], ["b", "c"]]}
    )
    assert isinstance(graph_backend, GraphSpace)
    assert graph_backend.positions() == ("a", "b", "c")
    assert graph_backend.distance("a", "c") == 2.0

    grid_backend = make_backend("grid", {"width": 3, "height": 2})
    assert isinstance(grid_backend, GridSpace)
    assert len(grid_backend.positions()) == 6


@pytest.mark.parametrize("kind", ["hex", "continuous2d", "continuous3d", "custom"])
def test_make_backend_reserved_kinds_rejected(kind: str) -> None:
    """覆盖项 5b：四 reserved kind → UnknownBackendError（reserved 显式拒绝，
    不静默降级；D-P4-17 LookupError 族）。"""
    assert issubclass(UnknownBackendError, LookupError)
    with pytest.raises(UnknownBackendError):
        make_backend(kind, {})


# —— 覆盖项 6：spaces 编解码 + entity_domain_positions ——


def test_spaces_encode_decode_roundtrip() -> None:
    """覆盖项 6a：encode_spaces → decode_spaces 与原 tuple 相等（载荷序保持）；
    D-P4-13 载荷形状逐字断言（entered_tick 缺省 0 参与编码）。

    畸形载荷（多余键，ContractModel extra="forbid"）→ pydantic
    ValidationError 原样透传（不吞、不降级、不具名还原——具名还原只给
    S-INV-3 标记错误）。
    """
    mappings = _overworld_mappings()
    payload = encode_spaces(mappings)
    assert payload == {
        "mappings": [
            {"domain_id": "overworld", "position": {"x": 0, "y": 0}, "entered_tick": 3},
            {"domain_id": "tactical", "position": "t0", "entered_tick": 0},
        ]
    }
    # roundtrip：解码产物与原 tuple 相等
    assert decode_spaces(payload) == mappings
    # 畸形载荷：多余键 → ValidationError 原样透传
    with pytest.raises(ValidationError):
        decode_spaces({**payload, "unexpected": 1})


def test_decode_spaces_rejects_duplicate_domain() -> None:
    """覆盖项 6b：codec 重复 domain 拒绝（覆盖项 4 S-INV-3 同一拒绝面的行为
    面：一 domain 一 position，D-P4-13）。

    同域不同 position 重复 / 同 position 重复均拒绝——唯一性按 domain_id
    判，不按位置值判；双域对照不构成违反。
    """
    base = {"domain_id": "overworld", "position": {"x": 0, "y": 0}, "entered_tick": 0}
    for dup in (
        {**base, "position": {"x": 1, "y": 1}, "entered_tick": 1},  # 不同 position 重复
        base,  # 同 position 重复
    ):
        with pytest.raises(SpaceInvariantError):
            decode_spaces({"mappings": [base, dup]})
    # 对照：两个不同域不构成违反（可映射多个域）
    other = {"domain_id": "tactical", "position": "t0", "entered_tick": 0}
    assert len(decode_spaces({"mappings": [base, other]})) == 2


def test_entity_domain_positions_missing_component() -> None:
    """覆盖项 6c：无 spaces 组件 → {}（组件缺失非错误，不抛）。"""
    assert entity_domain_positions(_view_with_spaces(None)) == {}


def test_entity_domain_positions_present_domain_filter() -> None:
    """覆盖项 6d：组件在位 → {domain_id: position}（载荷序）。

    域过滤口径（§6.1 L1654 / 设计文档 L512）：输出恰为组件所载域集合——
    实体在不在组件中的域无 mapping（无该域键）→ 该域不出现、不崩溃；
    函数只读组件、不经 registry（registry 上其余注册域不贡献）。
    """
    payload = {
        "mappings": [
            {"domain_id": "overworld", "position": {"x": 0, "y": 0}, "entered_tick": 3},
            {"domain_id": "tactical", "position": "t0", "entered_tick": 0},
        ]
    }
    positions = entity_domain_positions(_view_with_spaces(payload))
    assert positions == {"overworld": {"x": 0, "y": 0}, "tactical": "t0"}
    # 载荷序保持
    assert list(positions) == ["overworld", "tactical"]
    # 恰 2 键：组件未载的域（如注册表中的第三域）不出现
    assert set(positions) == {"overworld", "tactical"}
