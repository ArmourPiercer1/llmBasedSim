"""engine_v2 content 层 P5 模块依赖图：确定性拓扑 + 环/冲突/版本/缺依赖诊断
（P5-T04 / W3，设计文档 §3.4）。

依据 ``docs/v2/contracts/P5-project-format-module-plugin-dsl-design.md``（下称
"设计文档"，P5-DESIGN 冻结态）§3.4 字段级规格（11 导出）：

- **定位**：模块清单（Spec §28.3 requires/optional/conflicts/engine_version）
  → 有向图 + 确定性拓扑 + 环/冲突/版本/缺依赖诊断。导入面 = ``schemas`` +
  仅 stdlib（§3.4 定位条款；content/* 模块间零互导，本模块只导 schemas）；
- **ENGINE_VERSION**：自 ``content/schemas`` 导入（单点权威 =
  ``schemas.ENGINE_VERSION``，值 "0.5.0"，D-P5-08 / ERR-P5-3 S-A）——本模块
  不另定义、不入 ``__all__``；``check_module_versions`` 节点面比较目标 = 该
  常量；
- **never-raise**：7 个公共函数绝不抛出（定义域 = 内容流图：边端点为声明
  节点 id 的 ``build_module_graph`` 产物；域披露见各函数 docstring）——
  需求串文法错 → 诊断（``parse_requirement``）；环 → 空列表
  （``topological_order``）；环 → SCC 列表（诊断由 W6 validate_project 产，
  §3.6）；缺依赖 / 版本 / 冲突 → 诊断列表；
- **D-P5-06 / D-P5-15 确定性纪律**：Kahn 平手 = casefold 序（堆式口径，唯一
  确定序）；Tarjan SCC 初始节点序 = casefold 升序、邻接序 = 边构造序；诊断
  按显式步序追加；零时间戳 / 零指针 / 零随机；
- **边面约束恢复**（ERR-P5-14 钉死口径）：``ModuleEdge`` 字段面 =
  (source, target, kind) 三字段（§3.4 L343），边模型无
  version_range 字段——约束 = source 节点对应 kind 声明串首个解析至本边
  target 元素恢复（归一形，与 build 的 (source, target, kind) 去重
  「首次出现保留」同源）；边构造序遍历；无匹配或源缺席（直接构造边）→
  ""（空串，不检查）。

``__all__`` 11 名按设计文档 §8.2 导出台账逐名逐序。
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Final

from src.engine_v2.content.schemas import (
    ENGINE_VERSION,
    _ContractModel,
    Diagnostic,
    DiagnosticSeverity,
    ModuleGraphNode,
    ProjectIR,
)

__all__ = [
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
]

# —— 词法 / 文法（设计文档 §3.4 parse_requirement 条款 + D-P5-06 版本文法）——

#: 需求串文法（§3.4 L345 / D-P5-06 L605-610 钉死）：entry 去首尾空白后匹配
#: ``id`` | ``id >= V``；id = 点分词法（族.模块，§3.4 原文 pattern），
#: V = 点分数字串 1+ 分量（D-P5-06）；id 与 >= 之间、>= 与 V 之间允许一个
#: 或多个空白。
_REQUIREMENT_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<id>[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*)"
    r"(?:\s+>=\s+(?P<version>\d+(?:\.\d+)*))?$"
)

#: 裸版本文法（D-P5-06）：点分数字串 1+ 分量。
_VERSION_RE: Final[re.Pattern[str]] = re.compile(r"^\d+(?:\.\d+)*$")


# —— 数据模型（§3.4 字段面，L341-344）——


class RequirementKind(str, Enum):
    """边种类词表（设计文档 §3.4：``REQUIRED="required"`` /
    ``OPTIONAL="optional"``；str-Enum 保证 JSON/比较透明）。"""

    REQUIRED = "required"
    OPTIONAL = "optional"


class Requirement(_ContractModel):
    """解析后的模块需求（设计文档 §3.4：frozen + extra=forbid 基类模型）。

    ``version_range`` = ``""``（任意版本）或 ``">=V"``（归一形，无内部空白）；
    裸 V 形不可由 ``parse_requirement`` 产生（exact 形为节点 / manifest
    ``engine_version`` 字段专属，§3.4）。
    """

    module_id: str
    version_range: str = ""


class ModuleEdge(_ContractModel):
    """模块图有向边（设计文档 §3.4：frozen + extra=forbid 基类模型；
    三字段面不含 version_range，见模块头「边面约束恢复」披露）。"""

    source: str
    target: str
    kind: RequirementKind


class ModuleGraph(_ContractModel):
    """模块依赖有向图（设计文档 §3.4：frozen + extra=forbid 基类模型）。

    ``edges`` 构造序 = 节点 casefold 升序 ×（requires 先 optional 后）× 声明序
    （``build_module_graph`` 产物，确定性；直接构造时 = 给定序）。
    """

    nodes: dict[str, ModuleGraphNode] = {}
    edges: tuple[ModuleEdge, ...] = ()


# —— 私有版本比较面（D-P5-06 比较裁定：点分逐位、短者补 0）——


def _version_components(value: str) -> tuple[str, ...]:
    """版本文法字符串（裸 V）→ 点分组件串元组（纯字符串，零 int() 调用）。"""
    return tuple(value.split("."))


def _version_cmp(a: str, b: str) -> int:
    """点分版本纯字符串比较（-1 / 0 / 1）。

    机制（ERR-P5-14：CPython 3.12 int() 受 4300 位数字串上限约束，击穿
    never-raise 纪律，版本路径零 int() 调用）：两串按点分拆组件、组件数对齐
    （缺者补 "0"）；每组件去前导 0（去空则 "0"）；逐组件先比组件串长度（长
    者大）、再比字典序。口径等价性声明：结果与「数值补 0 逐位比较」
    （D-P5-06 口径）逐位一致——前导 0 不改变数值大小，等长纯数字串的字典
    序 = 数值序。
    """
    left = _version_components(a)
    right = _version_components(b)
    size = max(len(left), len(right))
    left = left + ("0",) * (size - len(left))
    right = right + ("0",) * (size - len(right))
    for la, ra in zip(left, right):
        la = la.lstrip("0") or "0"
        ra = ra.lstrip("0") or "0"
        if len(la) != len(ra):
            return -1 if len(la) < len(ra) else 1
        if la < ra:
            return -1
        if la > ra:
            return 1
    return 0


def _version_satisfied(have: str, constraint: str) -> bool:
    """约束满足判定（D-P5-06 比较裁定，节点面 / 边面共用）。

    文法（§3.4 L350 / D-P5-06 L605-610）：空串 = 任意；``>=V`` = 不小于（补 0 逐位）；
    裸 V = 精确（补 0 后元组相等）；文法外非空约束 = False（约束不满足面，
    诊断码语义含「版本语法非法」，§3.1 码表）。
    """
    if constraint == "":
        return True
    if constraint.startswith(">="):
        target = constraint[2:]
        if not _VERSION_RE.match(target):
            return False
        return _version_cmp(have, target) >= 0
    if _VERSION_RE.match(constraint):
        return _version_cmp(have, constraint) == 0
    return False


def _edge_constraint(graph: ModuleGraph, edge: ModuleEdge) -> str:
    """边 → version_range 恢复口径（ERR-P5-14 钉死口径，§3.4 L350）。

    ModuleEdge 三字段面（§3.4 L343）不含 version_range——约束存于
    source 节点的声明串（requires / optional 元素 = ``"id"`` 或
    ``"id >= V"``）。恢复口径：取 source 节点对应 kind 声明串中**首个**解析
    至本边 target 的元素的 version_range（与 build 去重「首次出现保留」同源）；
    source 节点缺席（直接构造边）或声明串无匹配元素 → ``""``（不检查）。
    复解析的 owner_id 取节点自身 id（点分词法保证非空，域内确定性）。
    """
    node = graph.nodes.get(edge.source)
    if node is None:
        return ""
    entries = node.requires if edge.kind == RequirementKind.REQUIRED else node.optional
    for entry in entries:
        requirement, _ = parse_requirement(entry, node.id)
        if requirement.module_id == edge.target:
            return requirement.version_range
    return ""


# —— 公共函数（§3.4 逐条；never-raise）——


def parse_requirement(entry: str, owner_id: str) -> tuple[Requirement, Diagnostic | None]:
    """需求串解析（设计文档 §3.4 L345 / D-P5-06 L605-610）。

    - 文法 = 去首尾空白后 ``id`` | ``id >= V``（id 点分词法，V 点分数字串）；
    - 合法裸 id → ``(Requirement(module_id=id, version_range=""), None)``；
    - 合法 ``id >= V`` → ``(Requirement(module_id=id, version_range=">=V"),
      None)``（归一形，无内部空白）；
    - 非法 → ``(Requirement(module_id=entry 原样, version_range=""),
      LLMSIM_MODULE_VERSION（path=owner_id，refs=(entry,)）)``。

    never-raise：任何输入仅产出 (Requirement, 诊断|None)，绝不抛出。
    域披露：``owner_id`` = 需求声明方节点 id（``ModuleGraphNode.id`` 点分
    词法保证非空，Diagnostic path 非空约束的域内前提）。
    """
    match = _REQUIREMENT_RE.match(entry.strip())
    if match is None:
        return (
            Requirement(module_id=entry, version_range=""),
            Diagnostic(
                code="LLMSIM_MODULE_VERSION",
                severity=DiagnosticSeverity.ERROR,
                path=owner_id,
                message=f"需求串文法非法（合法形 = id | id >= V）: {entry}",
                refs=(entry,),
            ),
        )
    version = match.group("version")
    version_range = f">={version}" if version is not None else ""
    return Requirement(module_id=match.group("id"), version_range=version_range), None


def build_module_graph(ir: ProjectIR) -> ModuleGraph:
    """IR 模块清单 → ModuleGraph（设计文档 §3.4 L346 / D-P5-06 L605-610）。

    - nodes = ``{n.id: n for n in ir.modules}``（模块 id 全小写词法，casefold
      恒等；重复 id 后者覆盖——重复诊断归 ``check_duplicate_ids``（W6），
      本函数保持纯转换）；
    - edges：节点按 id casefold 升序遍历，每节点先 requires 元素
      （kind=REQUIRED）后 optional 元素（kind=OPTIONAL），各自声明序；每串
      经 ``parse_requirement``（解析诊断**不**在此报——validator 复扫并报，
      build 保持纯转换，D-P5-06）；边 target = 解析结果的
      Requirement.module_id（解析失败时 = entry 原样）；
    - 同一 (source, target, kind) 三元组去重、首次出现保留（此处披露）。
    """
    nodes = {node.id: node for node in ir.modules}
    edges: list[ModuleEdge] = []
    seen: set[tuple[str, str, RequirementKind]] = set()
    for node_id in sorted(nodes, key=lambda nid: (nid.casefold(), nid)):
        node = nodes[node_id]
        for kind, entries in (
            (RequirementKind.REQUIRED, node.requires),
            (RequirementKind.OPTIONAL, node.optional),
        ):
            for entry in entries:
                requirement, _ = parse_requirement(entry, node_id)
                key = (node_id, requirement.module_id, kind)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(
                    ModuleEdge(source=node_id, target=requirement.module_id, kind=kind)
                )
    return ModuleGraph(nodes=nodes, edges=tuple(edges))


def topological_order(graph: ModuleGraph) -> list[str]:
    """Kahn 入度拓扑序（设计文档 §3.4 L347 / D-P5-06 L605-610）。

    - 全部边（REQUIRED + OPTIONAL）参与入度计算（图级、kind 无关）；
    - 平手 = casefold 序：每步取当前入度 0 集合中 casefold 最小者出队
      （堆式口径；次键 = id 原串——模块 id 全小写词法下 casefold 恒等，次键
      仅钉死 casefold 碰撞角例的唯一序，与 project_ir.flatten_entities 的 (casefold, id) 序同口径，
      正常流永不触发）；
    - 存在环（processed 数 < 节点数）→ 返回 ``[]``（**不 raise**，G5-4）；
    - 边端点不在 nodes（缺失目标 / 来源）→ 该边不参与入度（缺失诊断归
      ``check_unsatisfied_requires``，防双报）。
    """
    nodes = graph.nodes
    indegree: dict[str, int] = {nid: 0 for nid in nodes}
    adjacency: dict[str, list[str]] = {nid: [] for nid in nodes}
    for edge in graph.edges:
        if edge.source in nodes and edge.target in nodes:
            adjacency[edge.source].append(edge.target)
            indegree[edge.target] += 1
    ready = [nid for nid in nodes if indegree[nid] == 0]
    order: list[str] = []
    while ready:
        node_id = min(ready, key=lambda nid: (nid.casefold(), nid))
        ready.remove(node_id)
        order.append(node_id)
        for nxt in adjacency[node_id]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
    if len(order) != len(nodes):
        return []
    return order


def find_cycles(graph: ModuleGraph) -> list[list[str]]:
    """Tarjan SCC 环提取（设计文档 §3.4 L348 / D-P5-06 L605-610）。

    - size>1 的 SCC 或自环（a→a 边）各一；每个 SCC 输出 = 其节点 casefold
      排序列表（旋转归一化的确定性形态，信息无损，断言不依赖入边起点）；
    - 外层输出序 = 各 SCC 的 casefold 排序节点列表按字典序升序（实现侧确定性
      钉死：SOT 仅逐 SCC 钉内层序，方向与 D-P5-15 零非确定根源纪律一致）；
    - 遍历序钉死：初始节点序 = casefold 升序、邻接序 = 边构造序（D-P5-15）；
    - LLMSIM_MODULE_CYCLE 诊断由 ``validate_project``（W6，§3.6）对本输出
      每 SCC 产一条——本函数只产 SCC 列表（§3.4 签名钉死，never-raise）。
    """
    nodes = graph.nodes
    adjacency: dict[str, list[str]] = {nid: [] for nid in nodes}
    for edge in graph.edges:
        if edge.source in nodes and edge.target in nodes:
            adjacency[edge.source].append(edge.target)
    has_self_loop = {
        edge.source for edge in graph.edges if edge.source == edge.target and edge.source in nodes
    }

    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    sccs: list[list[str]] = []
    counter = 0

    for root in sorted(nodes, key=lambda nid: (nid.casefold(), nid)):
        if root in index:
            continue
        counter += 1
        index[root] = counter
        lowlink[root] = counter
        stack.append(root)
        on_stack[root] = True
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, i = work[-1]
            if i < len(adjacency[node]):
                work[-1] = (node, i + 1)
                nxt = adjacency[node][i]
                if nxt not in index:
                    counter += 1
                    index[nxt] = counter
                    lowlink[nxt] = counter
                    stack.append(nxt)
                    on_stack[nxt] = True
                    work.append((nxt, 0))
                elif on_stack.get(nxt):
                    lowlink[node] = min(lowlink[node], index[nxt])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])
                if lowlink[node] == index[node]:
                    scc: list[str] = []
                    while True:
                        member = stack.pop()
                        on_stack[member] = False
                        scc.append(member)
                        if member == node:
                            break
                    sccs.append(scc)

    reported = [scc for scc in sccs if len(scc) > 1 or scc[0] in has_self_loop]
    normalized = [sorted(scc, key=lambda nid: (nid.casefold(), nid)) for scc in reported]
    normalized.sort(key=lambda lst: (tuple(nid.casefold() for nid in lst), tuple(lst)))
    return normalized


def check_unsatisfied_requires(graph: ModuleGraph) -> list[Diagnostic]:
    """REQUIRED 边目标缺失诊断（设计文档 §3.4 L349 / 断言 #18）。

    graph.edges 构造序遍历；仅 REQUIRED 边且 target ∉ nodes → 一条
    ``LLMSIM_MODULE_REQUIRES_MISSING``（path=source 需求方 id，refs=(target,)）；
    同一 (source, target) 去重首次保留（build 已去重，此处防御性再保）；
    OPTIONAL 缺失 = 合法（无诊断）。never-raise。
    """
    diags: list[Diagnostic] = []
    seen: set[tuple[str, str]] = set()
    for edge in graph.edges:
        if edge.kind != RequirementKind.REQUIRED:
            continue
        if edge.target in graph.nodes:
            continue
        if (edge.source, edge.target) in seen:
            continue
        seen.add((edge.source, edge.target))
        diags.append(
            Diagnostic(
                code="LLMSIM_MODULE_REQUIRES_MISSING",
                severity=DiagnosticSeverity.ERROR,
                path=edge.source,
                message=f"必需依赖模块未声明: {edge.target}",
                refs=(edge.target,),
            )
        )
    return diags


def check_module_versions(graph: ModuleGraph) -> list[Diagnostic]:
    """版本约束诊断：解析复扫面 + 边面 + 节点 engine_version 面（§3.4 L350 /
    D-P5-06 L605-610 / ERR-P5-14）。

    解析复扫面（节点 casefold 序 × requires/optional 声明序；SOT §3.4
    L346「复扫并报」执行条款，ERR-P5-14 钉死）：每声明串经
    ``parse_requirement``，解析错误 → ``LLMSIM_MODULE_VERSION``
    （path=node.id，refs=(entry,)），同一 (path, refs) 去重首次保留；
    非法声明串在边面经 ``_edge_constraint`` 复解析得 version_range =
    空串 → 边面自动跳过，零双报。

    边面（graph.edges 构造序遍历）：仅 version_range 非空的边（约束恢复口径
    见 ``_edge_constraint`` 与模块头披露）；target ∉ nodes → 跳过（归
    ``check_unsatisfied_requires`` 报，防双报）；∈ nodes：比较裁定 = 点分数字
    逐位、短者补 0（D-P5-06）——``>=V`` 不满足 →
    ``LLMSIM_MODULE_VERSION``（path=source，refs=(f"{target}:{version_range}",
    f"have {node.version}")）；version_range = "" = 任意（不检查）。裸 V / 文法外
    形 = 共用比较面语义（_version_satisfied 照搬）：边面约束经 parse_requirement
    仅产 "" / ``>=V``，exact 形在边面不可达（为节点/manifest engine_version
    字段专属，SOT L350）。

    节点面（engine_version 非空节点，casefold 升序）：空串 = 任意；``>=V`` =
    不小于 ENGINE_VERSION；裸 V = 精确（补 0 后元组相等）；比较目标 =
    ``ENGINE_VERSION``（单点权威，自 schemas 导入，D-P5-08 / ERR-P5-3 S-A）；
    不满足 → ``LLMSIM_ENGINE_VERSION``（path=node.id，refs=(声明值,
    ENGINE_VERSION)）。

    输出序 = 全部解析复扫面诊断在前、全部边面诊断居中、全部节点面诊断在
    后（ERR-P5-14 / §3.4 L350 钉死）。never-raise。
    """
    parse_diags: list[Diagnostic] = []
    seen_parse: set[tuple[str, tuple[str, ...]]] = set()
    for node_id in sorted(graph.nodes, key=lambda nid: (nid.casefold(), nid)):
        node = graph.nodes[node_id]
        for entry in (*node.requires, *node.optional):
            _, parse_diag = parse_requirement(entry, node_id)
            if parse_diag is None:
                continue
            key = (parse_diag.path, parse_diag.refs)
            if key in seen_parse:
                continue
            seen_parse.add(key)
            parse_diags.append(parse_diag)
    edge_diags: list[Diagnostic] = []
    for edge in graph.edges:
        constraint = _edge_constraint(graph, edge)
        if constraint == "":
            continue
        target_node = graph.nodes.get(edge.target)
        if target_node is None:
            continue
        if not _version_satisfied(target_node.version, constraint):
            edge_diags.append(
                Diagnostic(
                    code="LLMSIM_MODULE_VERSION",
                    severity=DiagnosticSeverity.ERROR,
                    path=edge.source,
                    message=f"版本约束不满足: {constraint}",
                    refs=(f"{edge.target}:{constraint}", f"have {target_node.version}"),
                )
            )
    node_diags: list[Diagnostic] = []
    for node_id in sorted(graph.nodes, key=lambda nid: (nid.casefold(), nid)):
        declared = graph.nodes[node_id].engine_version
        if declared == "":
            continue
        if not _version_satisfied(ENGINE_VERSION, declared):
            node_diags.append(
                Diagnostic(
                    code="LLMSIM_ENGINE_VERSION",
                    severity=DiagnosticSeverity.ERROR,
                    path=node_id,
                    message=f"engine_version 约束不满足: {declared}",
                    refs=(declared, ENGINE_VERSION),
                )
            )
    return parse_diags + edge_diags + node_diags


def detect_conflicts(graph: ModuleGraph) -> list[Diagnostic]:
    """模块 conflicts 声明命中诊断（设计文档 §3.4 L351）。

    节点 A 按 casefold 升序；A.conflicts 含 c 且 c ∈ nodes → 无序对 {A, c}
    一条 ``LLMSIM_MODULE_CONFLICT``（path = A.id 与 c 中 casefold 较小者，
    refs = (A.id, c) 按 casefold 升序排列）；对称去重——A 列 c 与 c 列 A 只
    出 1 条（去重键 = 对子 casefold 排序元组）；冲突目标缺失 = 零诊断。
    诊断序 = 节点 casefold 升序 × conflicts 声明序的首现对子序。
    自指角例（A.conflicts 含 A 自身）按同一无序对规则统一处置（{A, A} 一条）。
    never-raise。
    """
    diags: list[Diagnostic] = []
    seen: set[tuple[str, str]] = set()
    for node_id in sorted(graph.nodes, key=lambda nid: (nid.casefold(), nid)):
        node = graph.nodes[node_id]
        for target in node.conflicts:
            if target not in graph.nodes:
                continue
            pair = tuple(sorted((node_id, target), key=lambda nid: (nid.casefold(), nid)))
            if pair in seen:
                continue
            seen.add(pair)
            diags.append(
                Diagnostic(
                    code="LLMSIM_MODULE_CONFLICT",
                    severity=DiagnosticSeverity.ERROR,
                    path=pair[0],
                    message=f"模块冲突声明命中: {pair[0]} 与 {pair[1]}",
                    refs=pair,
                )
            )
    return diags
