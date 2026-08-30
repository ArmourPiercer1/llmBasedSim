"""P5-T04（W3）单元测试：模块依赖图 + 确定性拓扑/环/冲突/版本/缺依赖诊断
（设计文档 §3.4 / §6.1）。

覆盖 §6.1 ``content/test_module_graph.py`` 用例族（12 项编号与 12 个测试
函数 docstring 的「用例 N」一一对应）：

1. ``__all__`` 11 名逐名逐序（§8.2 导出台账）+ ENGINE_VERSION 单点权威
   （D-P5-08）+ 模型面（frozen / extra=forbid / str-Enum，§3.4）;
2. ``parse_requirement`` 合法全族（裸 id → 空串；id >= V → 归一形 >=V，
   §3.4 / §6.1 / D-P5-06）;
3. ``parse_requirement`` 非法全族（含无空白族、仅左侧空白族；→
   LLMSIM_MODULE_VERSION path=owner_id refs=(entry,)，error 级）;
4. ``build_module_graph``（nodes 值同一性纯转换；边构造序 = 节点 casefold
   升序 × requires 先 optional 后 × 声明序；(source, target, kind) 去重）;
5. 钻石图拓扑精确序列 [a, b, c, d]（§5.2 断言 #10 / §6.1 同源数据）;
6. 环图 topological_order → ``[]``（§5.2 断言 #9 / D-P5-06，**不 raise**；
   自环同族）;
7. ``find_cycles``（§5.2 断言 #9）：size>1 SCC 或自环各一；SCC 输出 = 节点
   casefold 排序列表；外层字典序升序；无环 → ``[]``（LLMSIM_MODULE_CYCLE
   诊断由 validate_project（W6，§3.6）对每 SCC 产一条）;
8. requires 缺失 → LLMSIM_MODULE_REQUIRES_MISSING（断言 #18；防御性去重
   首次保留）;
9. 版本比较矩阵（``>=2`` vs 2 / 2.0 / 2.1 / 2.1.0 / 3 / 1.9）+ 超长
   （5000 位）版本串零异常（ERR-P5-14）+ 前导零组件 + 解析复扫面（非法
   声明串 → 恰好 1 条；合法不满足 → 仅边面，无双报）;
10. 节点 ``engine_version`` 面（``>=`` 与 exact 两形 → LLMSIM_ENGINE_VERSION）
    + 边面 / 节点面输出序;
11. conflicts 双向命中 1 条（无序对语义）+ 对称去重 + 多对首现序;
12. 边面 version_range 恢复口径（约束自 source 节点声明串恢复，去重首次
    出现保留同源）。

全部用例 hermetic（内存构造，零文件系统、零网络）；诊断断言以
(code, path, refs) 精确序列为主（message = 实现侧确定性文本，不逐字锁定，
W2 conftest make_diagnostic 口径）。
"""

from __future__ import annotations

from enum import Enum

import pytest
from pydantic import ValidationError

from src.engine_v2.content import module_graph
from src.engine_v2.content.module_graph import (
    ModuleEdge,
    ModuleGraph,
    Requirement,
    RequirementKind,
    build_module_graph,
    check_module_versions,
    check_unsatisfied_requires,
    detect_conflicts,
    find_cycles,
    parse_requirement,
    topological_order,
)
from src.engine_v2.content.schemas import _ContractModel, DiagnosticSeverity
from tests.engine_v2.content.conftest import make_ir, make_module_node

#: 11 导出，设计文档 §8.2 导出台账逐名逐序（用例 1 台账基线）。
EXPECTED_ALL: tuple[str, ...] = (
    "Requirement",
    "RequirementKind",
    "ModuleEdge",
    "ModuleGraph",
    "parse_requirement",
    "build_module_graph",
    "topological_order",
    "find_cycles",
    "check_unsatisfied_requires",
    "check_module_versions",
    "detect_conflicts",
)


def _edge(source: str, target: str, kind: RequirementKind = RequirementKind.REQUIRED) -> ModuleEdge:
    """ModuleEdge 构造 helper（直接构造边的用例用）。"""
    return ModuleEdge(source=source, target=target, kind=kind)


def test_all_eleven_names_in_ledger_order_and_model_shapes() -> None:
    """用例 1：__all__ 11 名逐名逐序（§8.2 导出台账）+ ENGINE_VERSION 单点
    权威（D-P5-08：自 schemas 导入、本模块不另定义、不入 __all__）+ 模型面
    （§3.4：_ContractModel 子类 frozen + extra=forbid；RequirementKind =
    (str, Enum) 值即两个英文词）。"""
    assert module_graph.__all__ == list(EXPECTED_ALL)
    assert module_graph.ENGINE_VERSION == "0.5.0"
    assert "ENGINE_VERSION" not in module_graph.__all__
    for model in (Requirement, ModuleEdge, ModuleGraph):
        assert issubclass(model, _ContractModel)
    # frozen：字段赋值构造期拒绝（pydantic 错误族）
    req = Requirement(module_id="alpha")
    with pytest.raises(ValidationError):
        req.module_id = "beta"  # type: ignore[misc]
    # extra=forbid：未知键构造期拒绝
    with pytest.raises(ValidationError):
        Requirement(module_id="alpha", bogus="x")  # pyright: ignore[call-arg]
    # 默认面（§3.4 L342-344）：version_range 默认空串；ModuleGraph 空图可构造
    assert req.version_range == ""
    assert ModuleGraph().nodes == {}
    assert ModuleGraph().edges == ()
    # RequirementKind = (str, Enum)，值即两个英文词（§3.4）
    assert issubclass(RequirementKind, str)
    assert issubclass(RequirementKind, Enum)
    assert RequirementKind.REQUIRED == "required"
    assert RequirementKind.OPTIONAL == "optional"


def test_parse_requirement_valid_bare_id_and_versioned_family() -> None:
    """用例 2：parse_requirement 合法全族（§3.4 文法 / §6.1 / D-P5-06）：
    裸 id（含点分族.模块、首尾空白去净）→ (Requirement(id, 空串), None)；
    id >= V（含多空白、Spec §41:1980 例形、多分量版本）→ 归一形 >=V。"""
    bare = [
        "alpha",
        "a",
        "standard.attributes",
        "family_mod.module_2",
        "  alpha  ",
        "\tstandard.attributes\n",
    ]
    for entry in bare:
        req, diag = parse_requirement(entry, owner_id="alpha")
        assert diag is None
        assert req == Requirement(module_id=entry.strip(), version_range="")
    versioned = [
        ("alpha >= 2", "alpha", ">=2"),
        ("standard.attributes >= 2", "standard.attributes", ">=2"),
        ("alpha   >=   2", "alpha", ">=2"),
        ("a >= 10.20.30", "a", ">=10.20.30"),
    ]
    for entry, expected_id, expected_range in versioned:
        req, diag = parse_requirement(entry, owner_id="alpha")
        assert diag is None
        assert req == Requirement(module_id=expected_id, version_range=expected_range)


def test_parse_requirement_invalid_family_reports_version_diagnostic() -> None:
    """用例 3：parse_requirement 非法全族（§3.4 / §6.1 文法负例面）：
    非法 → (Requirement(module_id=entry 原样【不去空白】, version_range=空串),
    LLMSIM_MODULE_VERSION path=owner_id refs=(entry,))，error 级；含
    无空白族（id 直接接 >=）与仅左侧空白族（>= 前空白、后无空白）。"""
    invalid = [
        "",
        "Alpha",
        "1abc",
        "a..b",
        ".alpha",
        "alpha >",
        "alpha >=",
        "alpha >= x",
        "alpha >= 2.0.x",
        "alpha >= 2.",
        ">= 2",
        "alpha > 2",
        "alpha == 2",
        "alpha >= 2 extra",
        " alpha >= 2 extra",
        "alpha>=2",
        "alpha >=2",
    ]
    for entry in invalid:
        req, diag = parse_requirement(entry, owner_id="owner.mod")
        assert req == Requirement(module_id=entry, version_range="")
        assert diag is not None
        assert (diag.code, diag.path, diag.refs) == (
            "LLMSIM_MODULE_VERSION",
            "owner.mod",
            (entry,),
        )
        assert diag.severity == DiagnosticSeverity.ERROR


def test_build_module_graph_nodes_edge_construction_order_and_dedup() -> None:
    """用例 4：build_module_graph（§3.4 / D-P5-06）：nodes = {n.id: n}（值同一
    性 = 纯转换不复制）；边构造序 = 节点 casefold 升序 ×（requires 先
    optional 后）× 声明序；解析失败 entry → 边 target = entry 原样且 build
    保持纯转换（无诊断面，D-P5-06）；同一 (source, target, kind) 去重首次
    出现保留。"""
    n_alpha = make_module_node(id="alpha.mod", version="1.0.0", requires=("gamma.missing",))
    n_bad = make_module_node(id="bad.mod", version="1.0.0", requires=("Bad Entry!",))
    n_beta = make_module_node(
        id="beta.mod", version="1.0.0", requires=("zeta.mod >= 1.2", "zeta.mod")
    )
    n_zeta = make_module_node(
        id="zeta.mod", version="1.0.0", requires=("alpha.mod",), optional=("beta.mod",)
    )
    graph = build_module_graph(make_ir(modules=(n_zeta, n_bad, n_alpha, n_beta)))
    # nodes 面：{n.id: n for n in ir.modules}（插入序 = modules 声明序，§3.4 L346
    # 字面），值 = IR 节点对象同一性
    assert list(graph.nodes) == ["zeta.mod", "bad.mod", "alpha.mod", "beta.mod"]
    assert graph.nodes["alpha.mod"] is n_alpha
    assert graph.nodes["bad.mod"] is n_bad
    assert graph.nodes["beta.mod"] is n_beta
    assert graph.nodes["zeta.mod"] is n_zeta
    # 边构造序 + 去重（beta.mod 的 "zeta.mod" 重复项被首现保留去重）
    assert graph.edges == (
        _edge("alpha.mod", "gamma.missing"),
        _edge("bad.mod", "Bad Entry!"),
        _edge("beta.mod", "zeta.mod"),
        _edge("zeta.mod", "alpha.mod"),
        _edge("zeta.mod", "beta.mod", RequirementKind.OPTIONAL),
    )


def test_topological_order_diamond_exact_sequence() -> None:
    """用例 5：钻石图拓扑精确序列（§5.2 断言 #10 / §6.1 同源数据）：
    a→b, a→c, b→d, c→d 全 requires → topological_order = [a, b, c, d] 逐位
    相等（casefold 平手 b 先于 c，D-P5-06 唯一确定序）。"""
    n_a = make_module_node(id="a", version="1.0.0", requires=("b", "c"))
    n_b = make_module_node(id="b", version="1.0.0", requires=("d",))
    n_c = make_module_node(id="c", version="1.0.0", requires=("d",))
    n_d = make_module_node(id="d", version="1.0.0")
    graph = build_module_graph(make_ir(modules=(n_a, n_b, n_c, n_d)))
    assert topological_order(graph) == ["a", "b", "c", "d"]


def test_topological_order_cycle_returns_empty_list() -> None:
    """用例 6：环图 topological_order → []（§5.2 断言 #9 / D-P5-06：环 = 空
    列表，**不 raise**）：a→b→c→a 全 requires；自环（a→a）同族。"""
    n_a = make_module_node(id="a", version="1.0.0", requires=("b",))
    n_b = make_module_node(id="b", version="1.0.0", requires=("c",))
    n_c = make_module_node(id="c", version="1.0.0", requires=("a",))
    graph = build_module_graph(make_ir(modules=(n_a, n_b, n_c)))
    assert topological_order(graph) == []
    # 自环同族
    n_solo = make_module_node(id="solo", version="1.0.0", requires=("solo",))
    assert topological_order(build_module_graph(make_ir(modules=(n_solo,)))) == []
    # 空图 → []（零 raise 面）
    assert topological_order(ModuleGraph()) == []


def test_find_cycles_scc_output_family() -> None:
    """用例 7：find_cycles（§5.2 断言 #9 / D-P5-06）：size>1 的 SCC 或自环
    （a→a 边）各一；SCC 输出 = 节点 casefold 排序列表（旋转归一，断言不依赖
    入边起点）；外层 = 各 SCC 列表字典序升序；无环（含空图）→ []。
    LLMSIM_MODULE_CYCLE 诊断由 validate_project（W6，§3.6）对本输出每 SCC
    产一条——W3 单元断言 SCC 列表本身（§3.4 签名钉死 list[list[str]]）。"""
    n_a = make_module_node(id="a", version="1.0.0", requires=("b",))
    n_b = make_module_node(id="b", version="1.0.0", requires=("c",))
    n_c = make_module_node(id="c", version="1.0.0", requires=("a",))
    graph = build_module_graph(make_ir(modules=(n_a, n_b, n_c)))
    # 3 环 → 恰好 1 个 SCC，casefold 排序 [a, b, c]
    assert find_cycles(graph) == [["a", "b", "c"]]
    # 轮换归一：同一环的两种边序（直接构造，模拟不同声明起点）输出逐位相等
    nodes = {n.id: n for n in (n_a, n_b, n_c)}
    g1 = ModuleGraph(nodes=nodes, edges=(_edge("a", "b"), _edge("b", "c"), _edge("c", "a")))
    g2 = ModuleGraph(nodes=nodes, edges=(_edge("c", "a"), _edge("a", "b"), _edge("b", "c")))
    assert find_cycles(g1) == find_cycles(g2) == [["a", "b", "c"]]
    # 无环（含空图 / 钻石）→ []
    assert find_cycles(ModuleGraph()) == []
    n_da = make_module_node(id="a", version="1.0.0", requires=("b", "c"))
    n_db = make_module_node(id="b", version="1.0.0", requires=("d",))
    n_dc = make_module_node(id="c", version="1.0.0", requires=("d",))
    n_dd = make_module_node(id="d", version="1.0.0")
    diamond = build_module_graph(make_ir(modules=(n_da, n_db, n_dc, n_dd)))
    assert find_cycles(diamond) == []
    # 自环 → [["solo"]]
    n_solo = make_module_node(id="solo", version="1.0.0", requires=("solo",))
    assert find_cycles(build_module_graph(make_ir(modules=(n_solo,)))) == [["solo"]]
    # 环 + 尾巴（e→a）：仅环上 SCC 上报，尾巴不入
    n_e = make_module_node(id="e", version="1.0.0", requires=("a",))
    tail = build_module_graph(make_ir(modules=(n_a, n_b, n_c, n_e)))
    assert find_cycles(tail) == [["a", "b", "c"]]
    # 双独立 2 环 → 外层字典序升序
    n_ab = make_module_node(id="a", version="1.0.0", requires=("c",))
    n_cb = make_module_node(id="c", version="1.0.0", requires=("a",))
    n_db = make_module_node(id="b", version="1.0.0", requires=("d",))
    n_dd = make_module_node(id="d", version="1.0.0", requires=("b",))
    dual = build_module_graph(make_ir(modules=(n_ab, n_cb, n_db, n_dd)))
    assert find_cycles(dual) == [["a", "c"], ["b", "d"]]


def test_check_unsatisfied_requires_missing_target() -> None:
    """用例 8：requires 缺失（§5.2 断言 #18 / §6.1）：B requires A 但 A 未
    声明 → 恰好 1 条 LLMSIM_MODULE_REQUIRES_MISSING（path = 需求方 B 的模块
    id，refs = (缺失模块名,)）；OPTIONAL 缺失 = 合法（零诊断）；同一
    (source, target) 防御性去重首次保留。"""
    n_b = make_module_node(id="b", version="1.0.0", requires=("a",), optional=("ghost_opt",))
    n_c = make_module_node(id="c", version="1.0.0", requires=("a",))
    graph = build_module_graph(make_ir(modules=(n_b, n_c)))
    assert [(d.code, d.path, d.refs) for d in check_unsatisfied_requires(graph)] == [
        ("LLMSIM_MODULE_REQUIRES_MISSING", "b", ("a",)),
        ("LLMSIM_MODULE_REQUIRES_MISSING", "c", ("a",)),
    ]
    # 目标全部命中 → 零诊断
    n_a = make_module_node(id="a", version="1.0.0")
    ok = build_module_graph(make_ir(modules=(n_a, n_b, n_c)))
    assert check_unsatisfied_requires(ok) == []
    # 防御性去重：直接构造重复 (source, target) 边 → 恰好 1 条
    dup = ModuleGraph(
        nodes={},
        edges=(_edge("b", "a"), _edge("b", "a"), _edge("b", "a", RequirementKind.OPTIONAL)),
    )
    assert [(d.code, d.path, d.refs) for d in check_unsatisfied_requires(dup)] == [
        ("LLMSIM_MODULE_REQUIRES_MISSING", "b", ("a",)),
    ]


def test_check_module_versions_edge_matrix() -> None:
    """用例 9：版本比较矩阵（§6.1 / D-P5-06）：requirement >=2 对目标版本
    2 / 2.0 / 2.1 / 2.1.0 / 3 全满足（点分逐位、短者补 0 口径）；1.9 不满足
    → 恰好 1 条 LLMSIM_MODULE_VERSION（path=source，refs = (f"{target}:>=2",
    f"have 1.9")）；version_range 空串 = 任意（不检查）；target 缺失 → 边面
    跳过（归 check_unsatisfied_requires 报，防双报）；超长（5000 位）版本串
    零异常（ERR-P5-14 纯字符串比较机制）+ 前导零组件（02 = 2、10 > 9）；
    解析复扫面（ERR-P5-14）：非法 requires / optional 声明串 → 恰好 1 条
    （path=节点 id，refs=(entry,)）；合法但不满足 → 仅边面 1 条（无双报）。"""
    targets: dict[str, str] = {
        "t2": "2",
        "t20": "2.0",
        "t21": "2.1",
        "t210": "2.1.0",
        "t3": "3",
        "t19": "1.9",
    }
    n_src = make_module_node(
        id="src.mod",
        version="1.0.0",
        requires=tuple(f"{tid} >= 2" for tid in targets) + ("tany", "ghost >= 2"),
    )
    nodes = (n_src, make_module_node(id="tany", version="0.1")) + tuple(
        make_module_node(id=tid, version=ver) for tid, ver in targets.items()
    )
    graph = build_module_graph(make_ir(modules=nodes))
    # 边面：恰好 1 条（t19）
    assert [(d.code, d.path, d.refs) for d in check_module_versions(graph)] == [
        ("LLMSIM_MODULE_VERSION", "src.mod", ("t19:>=2", "have 1.9")),
    ]
    # 防双报分工：ghost >= 2 → 版本检查零条、缺依赖检查恰好 1 条
    assert [(d.code, d.path, d.refs) for d in check_unsatisfied_requires(graph)] == [
        ("LLMSIM_MODULE_REQUIRES_MISSING", "src.mod", ("ghost",)),
    ]
    # 超长版本串（5000 位数字）零异常（ERR-P5-14：CPython 3.12 整数串位数
    # 上限，版本比较纯字符串机制、口径等价）：目标版本 "1" 对 >=2 不满足
    # 恰好 1 条；超长串本身对 >=1 满足（零条）
    n_one = make_module_node(id="t_one", version="1")
    n_long = make_module_node(id="t_long", version="1" * 5000)
    n_long_src = make_module_node(
        id="src_long", version="1.0.0", requires=("t_one >= 2", "t_long >= 1")
    )
    g_long = build_module_graph(make_ir(modules=(n_long_src, n_one, n_long)))
    assert [(d.code, d.path, d.refs) for d in check_module_versions(g_long)] == [
        ("LLMSIM_MODULE_VERSION", "src_long", ("t_one:>=2", "have 1")),
    ]
    # 前导零组件（02 = 2 满足 >=2；2.10 对 >=2.9，10 > 9 满足）→ 零诊断
    n_02 = make_module_node(id="t_02", version="02")
    n_210 = make_module_node(id="t_210", version="2.10")
    n_lz_src = make_module_node(
        id="src_lz", version="1.0.0", requires=("t_02 >= 2", "t_210 >= 2.9")
    )
    g_lz = build_module_graph(make_ir(modules=(n_lz_src, n_02, n_210)))
    assert check_module_versions(g_lz) == []
    # 解析复扫面（ERR-P5-14）：requires 含非法声明串 → 恰好 1 条
    # LLMSIM_MODULE_VERSION（path=节点 id，refs=(entry,)）；边面复解析得
    # 空约束自动跳过，零双报
    n_badreq = make_module_node(
        id="badreq.mod", version="1.0.0", requires=("beta 大于等于 latest",)
    )
    g_badreq = build_module_graph(make_ir(modules=(n_badreq,)))
    assert [(d.code, d.path, d.refs) for d in check_module_versions(g_badreq)] == [
        ("LLMSIM_MODULE_VERSION", "badreq.mod", ("beta 大于等于 latest",)),
    ]
    # optional 含非法声明串 → 同上恰好 1 条
    n_badopt = make_module_node(
        id="badopt.mod", version="1.0.0", optional=("gamma 大于等于 latest",)
    )
    g_badopt = build_module_graph(make_ir(modules=(n_badopt,)))
    assert [(d.code, d.path, d.refs) for d in check_module_versions(g_badopt)] == [
        ("LLMSIM_MODULE_VERSION", "badopt.mod", ("gamma 大于等于 latest",)),
    ]
    # 合法但约束不满足的声明串 → 仅边面 1 条（refs 含 have），复扫面
    # 零条（无双报）
    n_legal = make_module_node(id="legal.src", version="1.0.0", requires=("low_t >= 2",))
    n_low_t = make_module_node(id="low_t", version="1")
    g_legal = build_module_graph(make_ir(modules=(n_legal, n_low_t)))
    assert [(d.code, d.path, d.refs) for d in check_module_versions(g_legal)] == [
        ("LLMSIM_MODULE_VERSION", "legal.src", ("low_t:>=2", "have 1")),
    ]


def test_check_module_versions_node_engine_version_side() -> None:
    """用例 10：节点 engine_version 面（§6.1 / D-P5-06 / D-P5-08）：比较目标
    = ENGINE_VERSION（0.5.0）——>=0.5.0 满足 / 0.5.0 精确满足；>=0.6.0 不满足
    / 0.4.0 精确不满足 → 各 1 条 LLMSIM_ENGINE_VERSION（path=node.id，refs =
    (声明值, "0.5.0")）；空串 = 任意；节点面诊断排在全部边面诊断之后，节点
    面内部 = casefold 升序。"""
    n_ok_ge = make_module_node(id="ok_ge", engine_version=">=0.5.0")
    n_bad_ge = make_module_node(id="bad_ge", engine_version=">=0.6.0")
    n_ok_exact = make_module_node(id="ok_exact", engine_version="0.5.0")
    n_bad_exact = make_module_node(id="bad_exact", engine_version="0.4.0")
    n_empty = make_module_node(id="empty_ev", engine_version="")
    graph = build_module_graph(
        make_ir(modules=(n_bad_ge, n_ok_ge, n_bad_exact, n_ok_exact, n_empty))
    )
    assert [(d.code, d.path, d.refs) for d in check_module_versions(graph)] == [
        ("LLMSIM_ENGINE_VERSION", "bad_exact", ("0.4.0", "0.5.0")),
        ("LLMSIM_ENGINE_VERSION", "bad_ge", (">=0.6.0", "0.5.0")),
    ]
    # 边面 + 节点面混合：边面诊断全部在前（§3.4 L350 ERR-P5-14 输出序钉死）
    n_src = make_module_node(id="a_src", version="1.0.0", requires=("low_t >= 2",))
    n_low = make_module_node(id="low_t", version="1.0")
    n_ev = make_module_node(id="b_ev", version="1.0.0", engine_version=">=9.9.9")
    mixed = build_module_graph(make_ir(modules=(n_ev, n_src, n_low)))
    assert [(d.code, d.path, d.refs) for d in check_module_versions(mixed)] == [
        ("LLMSIM_MODULE_VERSION", "a_src", ("low_t:>=2", "have 1.0")),
        ("LLMSIM_ENGINE_VERSION", "b_ev", (">=9.9.9", "0.5.0")),
    ]


def test_detect_conflicts_symmetric_pairs_single_diagnostic() -> None:
    """用例 11：conflicts 双向命中 1 条（§6.1 / D-P5-06）：A.conflicts 含 c
    且 c ∈ nodes → 无序对 {A, c} 恰好 1 条 LLMSIM_MODULE_CONFLICT（path =
    casefold 较小者，refs = casefold 升序对子）；对称去重（A 列 c 与 c 列 A
    只出 1 条）；单向声明同 path/refs（无序对语义）；冲突目标缺失 = 零诊断；
    多对按节点 casefold 序 × 声明序首现。"""
    n_a = make_module_node(id="a", version="1.0.0", conflicts=("b",))
    n_b = make_module_node(id="b", version="1.0.0", conflicts=("a",))
    graph = build_module_graph(make_ir(modules=(n_a, n_b)))
    assert [(d.code, d.path, d.refs) for d in detect_conflicts(graph)] == [
        ("LLMSIM_MODULE_CONFLICT", "a", ("a", "b")),
    ]
    # 单向声明（仅 b 列 a）→ 同 path/refs
    n_a_plain = make_module_node(id="a", version="1.0.0")
    graph2 = build_module_graph(make_ir(modules=(n_a_plain, n_b)))
    assert [(d.code, d.path, d.refs) for d in detect_conflicts(graph2)] == [
        ("LLMSIM_MODULE_CONFLICT", "a", ("a", "b")),
    ]
    # 冲突目标缺失 → 零诊断
    n_ghost = make_module_node(id="a", version="1.0.0", conflicts=("ghost",))
    assert detect_conflicts(build_module_graph(make_ir(modules=(n_ghost,)))) == []
    # 多对首现序：a 声明 (c, b) → (a,c) 先 (a,b) 后；b 的 (a,) 去重；c 全去重
    n_a4 = make_module_node(id="a", version="1.0.0", conflicts=("c", "b"))
    n_b4 = make_module_node(id="b", version="1.0.0", conflicts=("a",))
    n_c4 = make_module_node(id="c", version="1.0.0", conflicts=("a", "b"))
    graph4 = build_module_graph(make_ir(modules=(n_a4, n_b4, n_c4)))
    assert [(d.code, d.path, d.refs) for d in detect_conflicts(graph4)] == [
        ("LLMSIM_MODULE_CONFLICT", "a", ("a", "c")),
        ("LLMSIM_MODULE_CONFLICT", "a", ("a", "b")),
        ("LLMSIM_MODULE_CONFLICT", "b", ("b", "c")),
    ]


def test_edge_constraint_recovery_first_declaration_wins() -> None:
    """用例 12：边面 version_range 恢复口径（§3.4 check_module_versions 条款
    最保守读法——ModuleEdge 三字段面不含 version_range，约束自 source 节点
    声明串恢复，与 build 去重「首次出现保留」同源）：requires
    ("t >= 1", "t >= 2") 去重首次出现保留 → 边面按首个声明 ">=1" 检查：
    目标版本 1.5 满足（0 诊断——若误用 ">=2" 将误报）；0.9 对 ">=1" 不满足
    → 恰好 1 条（refs 用首个声明形）。"""
    n_src = make_module_node(id="src.mod", version="1.0.0", requires=("t >= 1", "t >= 2"))
    n_t = make_module_node(id="t", version="1.5")
    graph = build_module_graph(make_ir(modules=(n_src, n_t)))
    # 去重：恰好 1 条 (src.mod, t, REQUIRED) 边
    assert graph.edges == (_edge("src.mod", "t"),)
    assert check_module_versions(graph) == []
    # 反向证明：0.9 对首个声明 ">=1" 不满足 → 恰好 1 条
    n_t_low = make_module_node(id="t", version="0.9")
    graph_low = build_module_graph(make_ir(modules=(n_src, n_t_low)))
    assert [(d.code, d.path, d.refs) for d in check_module_versions(graph_low)] == [
        ("LLMSIM_MODULE_VERSION", "src.mod", ("t:>=1", "have 0.9")),
    ]
