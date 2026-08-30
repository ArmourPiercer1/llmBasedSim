"""P5 W4 Rule module：v1 condition/rule DSL 的语义等价两阶段重写。

Source of truth (SOT): ``docs/v2/contracts/P5-project-format-module-plugin-dsl-design.md``
§3.5（L353-417 模块规格）；§3.2（L120 导入纪律：零 ``random`` import，随机面 =
注入 :class:`DslRng`）；D-P5-09 / D-P5-10 / D-P5-15；§5.2 断言 #11/#12；
§6.1-6.2（66 例 parity + v2 面测试）；§8.2（43 导出台账，下方 ``__all__``
逐字按序）；§8.4 偏差登记。

两阶段 DSL
----------
``parse_dsl`` —— 纯结构解析：全部 if 分支与 outcome 无条件完整解析，
无上下文依赖（validate 期可跑）。**永不抛**：结构错误一律以
``LLMSIM_DSL_PARSE`` 诊断返回（``severity=ERROR``、``path=path_label``）。

``evaluate_condition`` —— 对已解析 AST 急进 first-match 遍历；**仅**对
钉死语义错误抛 ``DslEvalError``（未知变量、除零、``in``/``not in`` 右值
类型、``contains``/``len()`` 左值类型、集合运算 ``_to_set`` 类型、字符串
比较 op、未注入 RNG 时调用 rand 族）。evaluate 层不吞。

``check_action_feasibility`` —— 永不抛：规则条件失效（结构或语义）→
模块 logger 告警 + 跳过该条（默认静默；本层不产 Diagnostic）。

转录口径（v1 @ f0a1052：``src/game/condition_eval.py`` + ``src/game/rules.py``）
--------------------------------------------------------------------------------
- 分词正则、文法产生式、错误消息文本、求值顺序（急进求值：左操作数先行、
  右操作数无条件求值——v1 parse+eval 融合，左操作数先行异常序）、内置规则
  阈值与 reason 文案均 v1 逐字对齐。
- D-P5-DEV-3：v1 运行时在分支命中后急进跳过剩余分支（``_skip_until_if_end``）；
  v2 parse 期解析全部分支 → v1 容忍的「命中分支后垃圾」在 v2 = 结构错误。
- D-P5-DEV-6：分支后无 ``;``/尾 outcome（如 ``if(c, o)``）在 v2 无条件为
  结构错误（v1 仅在该分支为假时报「if(...) 缺少 else 输出」）。
- D-P5-DEV-7：``uncertain:`` 概率槽 parse 生产 = 数字字面唯一（v1 允许任意
  算术表达式）。
- 裸 ``uncertain`` 节点 ``probability=None``，DSL 层缺省 0.5 在 evaluate 期
  施加（SOT §3.5；v1 condition_eval.py:294 同观测值）。
- D-P5-DEV-9：裸 ``player``/``target``（无点号）在 v2 = 未知变量
  （v1 经扁平 context dict 解析为 dict 不抛错）；66 例集 0 命中。
- rand 族：v1 模块级 ``random`` 全局替换为注入 :class:`DslRng`；``rng`` 为
  None 时调用 rand 族 → ``DslEvalError``（SOT §3.5 L391 钉 evaluate_condition
  的 rng 为必填非 None 参数；唯一可产 None 的调用方 = check_action_feasibility
  默认参（SOT L404），实现侧保守 fail-fast）。
- v1 player 查找的非 dict guard 在类型化 ``DslContext.player`` 下不可达
  （SOT §3.5，无对应分支）；target 侧保留（None 属非 dict →
  「无法读取 target.X」）。
- ``BUILTIN_RULE_IDS`` 保持 v1 disable 整数 1..5 的 tuple 位置（D-P5-10）。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Annotated, Any, Final, Literal, Protocol, Union, runtime_checkable

from pydantic import Field

from src.engine_v2.content.schemas import (
    Diagnostic,
    DiagnosticSeverity,
    RuleSpec,
    _ContractModel,
)

__all__ = [
    "DslRng",
    "DslToken",
    "tokenize_dsl",
    "DslNode",
    "DSL_NODE_KINDS",
    "IfChainNode",
    "ComparisonNode",
    "InTestNode",
    "NotInTestNode",
    "ContainsNode",
    "SubsetNode",
    "SupersetNode",
    "IntersectsNode",
    "DisjointNode",
    "TruthyNode",
    "AddNode",
    "SubNode",
    "MulNode",
    "DivNode",
    "NegNode",
    "NumberNode",
    "StringNode",
    "VariableNode",
    "FunctionCallNode",
    "FeasibilityNode",
    "AndNode",
    "OrNode",
    "NotNode",
    "DslParseResult",
    "DslEvalError",
    "Feasibility",
    "ConditionOutcome",
    "DslContext",
    "resolve_variable",
    "parse_dsl",
    "evaluate_condition",
    "ActionInput",
    "action_text",
    "resolve_target",
    "TargetRef",
    "FeasibilityResult",
    "check_action_feasibility",
    "BUILTIN_RULE_IDS",
]

logger = logging.getLogger(__name__)

# 正则逐字对齐 v1 condition_eval.py:25-30（_TOKEN_RE）。
_TOKEN_RE = re.compile(
    r'\s*(?:(?P<number>\d+(?:\.\d+)?)'
    r'|(?P<string>"[^"]*")'
    r'|(?P<name>[A-Za-z_][A-Za-z0-9_\.]*|[一-鿿][一-鿿A-Za-z0-9_\.]*)'
    r'|(?P<op><=|>=|!=|[+\-*/<>=(),;:]))'
)

_VALID_OUTCOMES = frozenset({"allowed", "blocked", "uncertain"})
_COMPARATORS = frozenset({"<", ">", "=", "<=", ">=", "!="})
_SET_KEYWORDS = frozenset({"subset", "superset", "intersects", "disjoint"})
_CONDITION_KEYWORDS = frozenset({"and", "or", "not", "in", "contains"}) | _SET_KEYWORDS

# 别名表逐字对齐 v1 condition_eval.py:430-433（target 宽度/重量别名）。
_TARGET_WIDTH_ALIASES = {
    "weight": ("weight_kg", "weight"),
    "width": ("effective_width_cm", "width_cm", "width"),
}

# v1 rules.py:9 STRENGTH_TO_KG_FACTOR。
_STRENGTH_TO_KG_FACTOR: Final[float] = 50.0


class DslEvalError(ValueError):
    """解析 + 求值语义错误统一族（v1 ``ConditionEvalError`` 等价物）。"""


class Feasibility(str, Enum):
    """可行性三值（v1 ``_VALID_OUTCOMES`` condition_eval.py:31 同集）。"""

    ALLOWED = "allowed"
    BLOCKED = "blocked"
    UNCERTAIN = "uncertain"


@runtime_checkable
class DslRng(Protocol):
    """注入随机源（v1 模块级 ``random`` 全局的替换面，D-P5-09/D-P5-15）。"""

    def rand(self) -> float:
        """返回 [0, 1) 均匀浮点。"""

    def uniform(self, lo: float, hi: float) -> float:
        """返回 [lo, hi) 均匀浮点（对齐 v1 ``_random.uniform`` 口径）。"""

    def randint(self, lo: int, hi: int) -> int:
        """返回 [lo, hi] 闭区间整数（对齐 v1 condition_eval.py:254-259）。"""


class DslToken(_ContractModel):
    """词法 token：kind ∈ {number, string, name, op}。"""

    kind: str
    value: str


# ── AST 节点（23 种，kind 首字段，frozen）──────────────────────────────


class IfChainNode(_ContractModel):
    """if 链：branches = (条件, outcome) 对；trailing = 尾 outcome。

    outcome 槽 parse 期约束 kind ∈ {feasibility, if_chain}（v1 :281-283
    嵌套 if 递归口径；其余 21 种落 outcome 位 = parse 错误）。
    """

    kind: Literal["if_chain"]
    branches: tuple[tuple[DslNode, DslNode], ...]
    trailing: DslNode


class ComparisonNode(_ContractModel):
    """数值/字符串比较（v1 :119-143：任一侧 str → 仅 =/!=）。"""

    kind: Literal["comparison"]
    op: Literal["<", ">", "=", "<=", ">=", "!="]
    left: DslNode
    right: DslNode


class InTestNode(_ContractModel):
    """``in`` 成员（v1 :147-156：右可为字符串或列表）。"""

    kind: Literal["in"]
    left: DslNode
    right: DslNode


class NotInTestNode(_ContractModel):
    """``not in`` 成员（v1 :157-168）。"""

    kind: Literal["not_in"]
    left: DslNode
    right: DslNode


class ContainsNode(_ContractModel):
    """``contains`` 容器包含（v1 :169-180）。

    right 槽 parse 生产 = 裸 name 字面 → StringNode 字面值（非变量解析）。
    """

    kind: Literal["contains"]
    left: DslNode
    right: DslNode


class SubsetNode(_ContractModel):
    """``subset`` 子集（v1 :181-193，``_SET_KEYWORDS`` :62）。"""

    kind: Literal["subset"]
    left: DslNode
    right: DslNode


class SupersetNode(_ContractModel):
    """``superset`` 超集（v1 :181-193）。"""

    kind: Literal["superset"]
    left: DslNode
    right: DslNode


class IntersectsNode(_ContractModel):
    """``intersects`` 相交（v1 :181-193）。"""

    kind: Literal["intersects"]
    left: DslNode
    right: DslNode


class DisjointNode(_ContractModel):
    """``disjoint`` 不相交（v1 :181-193）。"""

    kind: Literal["disjoint"]
    left: DslNode
    right: DslNode


class TruthyNode(_ContractModel):
    """裸值条件（v1 :195 truthy single-value 包装）。"""

    kind: Literal["truthy"]
    value: DslNode


class AddNode(_ContractModel):
    """加法（parse_add_sub v1 :199-207）。"""

    kind: Literal["add"]
    left: DslNode
    right: DslNode


class SubNode(_ContractModel):
    """减法（parse_add_sub v1 :199-207）。"""

    kind: Literal["sub"]
    left: DslNode
    right: DslNode


class MulNode(_ContractModel):
    """乘法（parse_mul_div v1 :212-218）。"""

    kind: Literal["mul"]
    left: DslNode
    right: DslNode


class DivNode(_ContractModel):
    """除法（parse_mul_div v1 :212-218；除零 :216-217 → DslEvalError）。"""

    kind: Literal["div"]
    left: DslNode
    right: DslNode


class NegNode(_ContractModel):
    """一元负（v1 :222-224）。"""

    kind: Literal["neg"]
    operand: DslNode


class NumberNode(_ContractModel):
    """数字字面（tokenizer number 组，float 化）。"""

    kind: Literal["number"]
    value: float


class StringNode(_ContractModel):
    """字符串字面（tokenizer string 组，去引号）。"""

    kind: Literal["string"]
    value: str


class VariableNode(_ContractModel):
    """变量名（v1 :343-351 resolve_variable）。"""

    kind: Literal["variable"]
    name: str


class FunctionCallNode(_ContractModel):
    """函数调用（v1 :243-273；parse 期 arity 校验）。

    rand 0 或 2 参；randint/min/max 2 参；len 1 参。
    """

    kind: Literal["function_call"]
    name: Literal["rand", "randint", "min", "max", "len"]
    args: tuple[DslNode, ...]


class FeasibilityNode(_ContractModel):
    """outcome 三值（v1 _parse_outcome :279-299）。

    probability 仅 uncertain 可带；parse 期校验 0<p<1；概率槽 parse 生产 =
    NumberNode 数字字面唯一（D-P5-DEV-7）。裸 uncertain → None（evaluate
    期 DSL 层缺省 0.5）。
    """

    kind: Literal["feasibility"]
    feasibility: Feasibility
    probability: float | None = None


class AndNode(_ContractModel):
    """``and`` 布尔合取（急进求值：右操作数无条件求值、异常上抛（v1 :100-112））。"""

    kind: Literal["and"]
    left: DslNode
    right: DslNode


class OrNode(_ContractModel):
    """``or`` 布尔析取（急进求值：右操作数无条件求值、异常上抛（v1 :100-112））。"""

    kind: Literal["or"]
    left: DslNode
    right: DslNode


class NotNode(_ContractModel):
    """``not`` 布尔取反（v1 :114-117）。"""

    kind: Literal["not"]
    operand: DslNode


# ── 判别联合（kind 判别；23 种闭集）────────────────────────────────────

DslNode = Annotated[
    Union[
        IfChainNode,
        ComparisonNode,
        InTestNode,
        NotInTestNode,
        ContainsNode,
        SubsetNode,
        SupersetNode,
        IntersectsNode,
        DisjointNode,
        TruthyNode,
        AddNode,
        SubNode,
        MulNode,
        DivNode,
        NegNode,
        NumberNode,
        StringNode,
        VariableNode,
        FunctionCallNode,
        FeasibilityNode,
        AndNode,
        OrNode,
        NotNode,
    ],
    Field(discriminator="kind"),
]

# 23 枚节点 kind 闭集（SOT §3.5 DSL_NODE_KINDS；断言 #12 AST 闭合面）。
DSL_NODE_KINDS: Final[frozenset[str]] = frozenset(
    {
        "if_chain",
        "comparison",
        "in",
        "not_in",
        "contains",
        "subset",
        "superset",
        "intersects",
        "disjoint",
        "truthy",
        "add",
        "sub",
        "mul",
        "div",
        "neg",
        "number",
        "string",
        "variable",
        "function_call",
        "feasibility",
        "and",
        "or",
        "not",
    }
)


class DslParseResult(_ContractModel):
    """parse_dsl 返回：ast 或 LLMSIM_DSL_PARSE 诊断（永不抛）。"""

    ast: DslNode | None = None
    diagnostics: tuple[Diagnostic, ...] = ()


class ConditionOutcome(_ContractModel):
    """条件求值结果（v1 condition_eval.py:13-16 同形）。"""

    feasibility: Feasibility
    probability: float | None = None


class DslContext(_ContractModel):
    """求值上下文（v1 自定义规则上下文 = {player, target, action}，
    rules.py:98-101 → v2 variables={"action": …} 映射）。"""

    player: dict[str, Any] = Field(default_factory=dict)
    target: dict[str, Any] | None = None
    variables: dict[str, Any] = Field(default_factory=dict)


class ActionInput(_ContractModel):
    """行动输入（v1 player_action dict 键封闭集，rules.py:33-38/41-53/164）。"""

    raw_input: str = ""
    interpreted_intent: str = ""
    action_description: str = ""
    speech_content: str = ""
    target_object_id: str | None = None
    action_type: str | None = None


class TargetRef(_ContractModel):
    """目标解析结果：object 本体 + 宽度（对象优先，location 回退）。

    source = 宽度出处：``object:<id>`` | ``location:<id>`` | None。
    """

    object: dict[str, Any] | None = None
    width_cm: float | None = None
    source: str | None = None


class FeasibilityResult(_ContractModel):
    """规则预判结果（v1 结果 dict 五键全映射，rules.py:85-91）。"""

    feasibility: Feasibility
    reason: str
    matched_rule: str
    success_probability: float | None = None
    requires_roll: bool = False


for _model in (
    IfChainNode,
    ComparisonNode,
    InTestNode,
    NotInTestNode,
    ContainsNode,
    SubsetNode,
    SupersetNode,
    IntersectsNode,
    DisjointNode,
    TruthyNode,
    AddNode,
    SubNode,
    MulNode,
    DivNode,
    NegNode,
    NumberNode,
    StringNode,
    VariableNode,
    FunctionCallNode,
    FeasibilityNode,
    AndNode,
    OrNode,
    NotNode,
    DslParseResult,
    ConditionOutcome,
    FeasibilityResult,
):
    _model.model_rebuild(force=True)

del _model

# v1 disable 整数 1..5 → tuple 位置（D-P5-10：v1 整数位 = 位置 + 1）。
BUILTIN_RULE_IDS: Final[tuple[str, ...]] = (
    "blocked_common",
    "extraordinary",
    "strength_vs_weight",
    "skill_vs_lock",
    "body_width_vs_passage",
)


# ── 词法 ───────────────────────────────────────────────────────────────


def tokenize_dsl(expression: str) -> list[DslToken]:
    """分词（正则逐字对齐 v1 condition_eval.py:25-30；:45-57 循环口径）。

    不可解析片段 → ``DslEvalError``（消息含片段前 20 字符，对齐 v1 :48）。
    """
    tokens: list[DslToken] = []
    pos = 0
    while pos < len(expression):
        match = _TOKEN_RE.match(expression, pos)
        if match is None:
            raise DslEvalError(f"无法解析条件表达式片段: {expression[pos:pos + 20]!r}")
        pos = match.end()
        if match.lastgroup == "number":
            tokens.append(DslToken(kind="number", value=match.group(match.lastgroup)))
        elif match.lastgroup == "string":
            tokens.append(DslToken(kind="string", value=match.group(match.lastgroup)[1:-1]))
        elif match.lastgroup == "name":
            tokens.append(DslToken(kind="name", value=match.group(match.lastgroup)))
        elif match.lastgroup == "op":
            tokens.append(DslToken(kind="op", value=match.group(match.lastgroup)))
    return tokens


# ── 结构解析（v1 _Parser 产生式逐字对应，产出 AST 而非即时求值）────────


class _DslParser:
    """结构解析器（v1 ``_Parser`` 的两阶段拆分：只产节点，不求值）。"""

    def __init__(self, tokens: list[DslToken]) -> None:
        self.tokens = tokens
        self.pos = 0

    # ── 顶层 if(…) 入口（v1 parse_if :72-93；根产生式）──────────────

    def parse_if(self) -> IfChainNode:
        name = self._consume_name()
        if name != "if":
            raise DslEvalError("条件表达式必须以 if(...) 开始")
        self._consume_op("(")

        branches: list[tuple[DslNode, DslNode]] = []
        while True:
            if self._looks_like_condition():
                condition = self._parse_condition()
                self._consume_op(",")
                outcome = self._parse_outcome()
                branches.append((condition, outcome))
                if self._match_op(";"):
                    continue
                self._consume_op(")")
                raise DslEvalError("if(...) 缺少 else 输出")

            trailing = self._parse_outcome()
            self._consume_op(")")
            return IfChainNode(kind="if_chain", branches=tuple(branches), trailing=trailing)

    # ── 布尔条件（v1 :100-117）──────────────────────────────────────

    def _parse_condition(self) -> DslNode:
        return self._parse_or()

    def _parse_or(self) -> DslNode:
        left = self._parse_and()
        while self._match_name("or"):
            right = self._parse_and()
            left = OrNode(kind="or", left=left, right=right)
        return left

    def _parse_and(self) -> DslNode:
        left = self._parse_not()
        while self._match_name("and"):
            right = self._parse_not()
            left = AndNode(kind="and", left=left, right=right)
        return left

    def _parse_not(self) -> DslNode:
        if self._match_name("not"):
            return NotNode(kind="not", operand=self._parse_not())
        return self._parse_comparison()

    def _parse_comparison(self) -> DslNode:
        left = self.parse_add_sub()
        token = self._peek()
        if token is None:
            return TruthyNode(kind="truthy", value=left)

        if token.kind == "op" and token.value in _COMPARATORS:
            op = self._advance().value
            right = self.parse_add_sub()
            return ComparisonNode(kind="comparison", op=op, left=left, right=right)

        if token.kind == "name":
            if token.value == "in":
                self._advance()
                right = self.parse_add_sub()
                return InTestNode(kind="in", left=left, right=right)
            if token.value == "not":
                nxt = self._peek(1)
                if nxt is not None and nxt.kind == "name" and nxt.value == "in":
                    self._advance()
                    self._advance()
                    right = self.parse_add_sub()
                    return NotInTestNode(kind="not_in", left=left, right=right)
            if token.value == "contains":
                self._advance()
                right_name = self._consume_name()
                return ContainsNode(kind="contains", left=left, right=StringNode(kind="string", value=right_name))
            if token.value in _SET_KEYWORDS:
                keyword = self._advance().value
                right = self.parse_add_sub()
                node_cls = {
                    "subset": SubsetNode,
                    "superset": SupersetNode,
                    "intersects": IntersectsNode,
                    "disjoint": DisjointNode,
                }[keyword]
                return node_cls(kind=keyword, left=left, right=right)

        return TruthyNode(kind="truthy", value=left)

    # ── 算术（v1 :199-220）──────────────────────────────────────────

    def parse_add_sub(self) -> DslNode:
        value = self.parse_mul_div()
        while True:
            if self._match_op("+"):
                value = AddNode(kind="add", left=value, right=self.parse_mul_div())
            elif self._match_op("-"):
                value = SubNode(kind="sub", left=value, right=self.parse_mul_div())
            else:
                return value

    def parse_mul_div(self) -> DslNode:
        value = self.parse_primary()
        while True:
            if self._match_op("*"):
                value = MulNode(kind="mul", left=value, right=self.parse_primary())
            elif self._match_op("/"):
                value = DivNode(kind="div", left=value, right=self.parse_primary())
            else:
                return value

    def parse_primary(self) -> DslNode:
        if self._match_op("-"):
            return NegNode(kind="neg", operand=self.parse_primary())
        if self._match_op("("):
            # 布尔分组（含比较 / and / or / not / 集合运算）→ 条件节点直通
            if self._looks_like_condition():
                value = self._parse_or()
                self._consume_op(")")
                return value
            # 算术分组
            value = self.parse_add_sub()
            self._consume_op(")")
            return value

        token = self._advance()
        if token.kind == "number":
            return NumberNode(kind="number", value=float(token.value))
        if token.kind == "string":
            return StringNode(kind="string", value=token.value)
        if token.kind == "name":
            if token.value in ("rand", "randint", "min", "max", "len") and self._match_op(
                "("
            ):
                func_name = token.value
                if func_name == "rand":
                    if self._match_op(")"):
                        return FunctionCallNode(kind="function_call", name="rand", args=())
                    lo = self.parse_add_sub()
                    self._consume_op(",")
                    hi = self.parse_add_sub()
                    self._consume_op(")")
                    return FunctionCallNode(kind="function_call", name="rand", args=(lo, hi))
                if func_name == "randint":
                    lo = self.parse_add_sub()
                    self._consume_op(",")
                    hi = self.parse_add_sub()
                    self._consume_op(")")
                    return FunctionCallNode(kind="function_call", name="randint", args=(lo, hi))
                if func_name == "len":
                    arg = self.parse_add_sub()
                    self._consume_op(")")
                    return FunctionCallNode(kind="function_call", name="len", args=(arg,))
                first = self.parse_add_sub()
                self._consume_op(",")
                second = self.parse_add_sub()
                self._consume_op(")")
                return FunctionCallNode(kind="function_call", name=func_name, args=(first, second))
            return VariableNode(kind="variable", name=token.value)
        raise DslEvalError(f"条件表达式中不应出现 {token.value!r}")

    # ── Outcome 解析（v1 :279-299；嵌套 if 递归）────────────────────

    def _parse_outcome(self) -> DslNode:
        token = self._peek()
        if token is not None and token.kind == "name" and token.value == "if":
            return self.parse_if()

        token = self._advance()
        if token.kind != "name":
            raise DslEvalError("输出必须是 allowed、blocked 或 uncertain")
        feasibility = token.value.lower()
        if feasibility not in _VALID_OUTCOMES:
            raise DslEvalError(f"非法输出 {token.value!r}")

        probability: float | None = None
        if feasibility == "uncertain" and self._match_op(":"):
            prob_token = self._advance()
            if prob_token.kind != "number":
                raise DslEvalError("uncertain 概率必须是数字字面")
            probability = float(prob_token.value)
            if not 0 < probability < 1:
                raise DslEvalError("uncertain 概率必须在 0 和 1 之间")
        return FeasibilityNode(kind="feasibility", feasibility=Feasibility(feasibility), probability=probability)

    # ── 辅助（v1 :303-351 逐字口径）─────────────────────────────────

    def expect_end(self) -> None:
        if self._peek() is not None:
            raise DslEvalError(f"条件表达式末尾存在多余内容: {self._peek().value!r}")

    def _looks_like_condition(self) -> bool:
        depth = 0
        i = self.pos
        while i < len(self.tokens):
            token = self.tokens[i]
            if token.kind == "op":
                if token.value == "(":
                    depth += 1
                elif token.value == ")":
                    if depth == 0:
                        return False
                    depth -= 1
                elif depth == 0:
                    if token.value in _COMPARATORS:
                        return True
                    if token.value == ",":
                        return True
                    if token.value == ";":
                        return False
            elif token.kind == "name" and depth == 0:
                if token.value in _CONDITION_KEYWORDS:
                    return True
            i += 1
        return False

    def _peek(self, offset: int = 0) -> DslToken | None:
        idx = self.pos + offset
        return self.tokens[idx] if idx < len(self.tokens) else None

    def _advance(self) -> DslToken:
        token = self._peek()
        if token is None:
            raise DslEvalError("条件表达式意外结束")
        self.pos += 1
        return token

    def _match_op(self, value: str) -> bool:
        token = self._peek()
        if token is not None and token.kind == "op" and token.value == value:
            self.pos += 1
            return True
        return False

    def _match_name(self, value: str) -> bool:
        token = self._peek()
        if token is not None and token.kind == "name" and token.value == value:
            self.pos += 1
            return True
        return False

    def _consume_op(self, value: str) -> None:
        if not self._match_op(value):
            found = self._peek().value if self._peek() else "表达式结束"
            raise DslEvalError(f"预期 {value!r}，但得到 {found!r}")

    def _consume_name(self) -> str:
        token = self._advance()
        if token.kind != "name":
            raise DslEvalError(f"预期名称，但得到 {token.value!r}")
        return token.value


def parse_dsl(expression: str, path_label: str) -> DslParseResult:
    """结构解析（永不抛）：tokenize → 全分支文法树 → expect_end。

    结构检查面 = v1 parser parse 时检查全集（if 形状、比较/集合 op 存在性、
    函数名/arity、outcome 关键字与 uncertain 概率范围、末尾多余 token）；
    根产生式必须为 if 链。任何结构错误 → 单条 ``LLMSIM_DSL_PARSE`` 诊断
    （severity=ERROR，path=path_label），ast=None。
    """
    try:
        tokens = tokenize_dsl(expression)
        parser = _DslParser(tokens)
        ast = parser.parse_if()
        parser.expect_end()
    except DslEvalError as exc:
        diagnostic = Diagnostic(
            code="LLMSIM_DSL_PARSE",
            severity=DiagnosticSeverity.ERROR,
            path=path_label,
            message=str(exc),
        )
        return DslParseResult(ast=None, diagnostics=(diagnostic,))
    return DslParseResult(ast=ast, diagnostics=())


# ── 变量解析（查找序逐字对齐 v1 condition_eval.py:343-451）─────────────


def resolve_variable(name: str, context: DslContext) -> Any:
    """变量解析：player.X / target.X / 自由名（显式 None = 缺失）。"""
    if name.startswith("player."):
        return _lookup_player(name[7:], context.player)
    if name.startswith("target."):
        return _lookup_target(name[7:], context.target)
    if name not in context.variables or context.variables[name] is None:
        raise DslEvalError(f"未知变量 {name!r}")
    return context.variables[name]


def _lookup_player(name: str, player: dict[str, Any]) -> Any:
    # v1 :398-421 口径（非 dict guard 在类型化 DslContext.player 下不可达，
    # SOT §3.5：无对应分支）。
    attrs = player.get("attributes")
    if isinstance(attrs, dict) and name in attrs:
        item = attrs[name]
        if isinstance(item, dict) and "value" in item:
            return item["value"]

    physical = player.get("physical_profile")
    if isinstance(physical, dict) and name in physical:
        return physical[name]

    capabilities = player.get("capabilities")
    if isinstance(capabilities, dict):
        skills = capabilities.get("skill_levels")
        if isinstance(skills, dict) and name in skills:
            return skills[name]

    if name in player:
        return player[name]

    raise DslEvalError(f"未知变量 player.{name}")


def _lookup_target(name: str, target: Any) -> Any:
    # v1 :424-441 口径（None 属非 dict → 前置 guard 触发）。
    if not isinstance(target, dict):
        raise DslEvalError(f"无法读取 target.{name}")

    props = target.get("properties")
    if isinstance(props, dict):
        aliases = _TARGET_WIDTH_ALIASES.get(name, (name,))
        for key in aliases:
            if key in props:
                return props[key]

    if name in target:
        return target[name]

    raise DslEvalError(f"未知变量 target.{name}")


def _to_set(value: Any, keyword: str) -> set:
    # v1 :353-359 口径。
    if isinstance(value, (list, tuple, set)):
        return set(value)
    raise DslEvalError(f"{keyword} 运算需要列表类型，实际类型为 {type(value).__name__}")


# ── 求值（急进 first-match；仅钉死语义错误抛 DslEvalError）─────────────


def evaluate_condition(ast: DslNode, context: DslContext, rng: DslRng) -> ConditionOutcome:
    """急进遍历 AST：if 链逐分支——求值条件，真/假均对分支 outcome 求值，
    真 → 立即返回（其后分支不求值），假 → 下一分支，全假 → trailing。

    仅钉死语义错误抛 ``DslEvalError``（不吞）；根节点必须为 if_chain。
    """
    if not isinstance(ast, IfChainNode):
        raise DslEvalError("evaluate_condition 根节点必须为 if_chain")
    return _eval_if_chain(ast, context, rng)


def _eval_if_chain(node: IfChainNode, context: DslContext, rng: DslRng | None) -> ConditionOutcome:
    for condition, outcome in node.branches:
        matched = bool(_eval_value(condition, context, rng))
        branch_outcome = _eval_outcome(outcome, context, rng)
        if matched:
            return branch_outcome
    return _eval_outcome(node.trailing, context, rng)


def _eval_outcome(node: DslNode, context: DslContext, rng: DslRng | None) -> ConditionOutcome:
    if isinstance(node, FeasibilityNode):
        probability = node.probability
        if node.feasibility is Feasibility.UNCERTAIN and probability is None:
            probability = 0.5
        return ConditionOutcome(feasibility=node.feasibility, probability=probability)
    if isinstance(node, IfChainNode):
        return _eval_if_chain(node, context, rng)
    raise DslEvalError(f"结果槽节点类型非法: {node.kind!r}")


def _eval_value(node: DslNode, context: DslContext, rng: DslRng | None) -> Any:
    if isinstance(node, NumberNode):
        return node.value
    if isinstance(node, StringNode):
        return node.value
    if isinstance(node, VariableNode):
        return resolve_variable(node.name, context)
    if isinstance(node, NegNode):
        return -_eval_value(node.operand, context, rng)
    if isinstance(node, AddNode):
        return _eval_value(node.left, context, rng) + _eval_value(node.right, context, rng)
    if isinstance(node, SubNode):
        return _eval_value(node.left, context, rng) - _eval_value(node.right, context, rng)
    if isinstance(node, MulNode):
        return _eval_value(node.left, context, rng) * _eval_value(node.right, context, rng)
    if isinstance(node, DivNode):
        left = _eval_value(node.left, context, rng)
        divisor = _eval_value(node.right, context, rng)
        if divisor == 0:
            raise DslEvalError("条件表达式中出现除零")
        return left / divisor
    if isinstance(node, ComparisonNode):
        left = _eval_value(node.left, context, rng)
        right = _eval_value(node.right, context, rng)
        # 任一侧 str → 仅 =/!=（v1 :127-133 口径）
        if isinstance(left, str) or isinstance(right, str):
            left_s = str(left)
            right_s = str(right)
            if node.op == "=" or node.op == "==":
                return left_s == right_s
            if node.op == "!=":
                return left_s != right_s
            raise DslEvalError(f"字符串不支持 {node.op!r} 比较")
        if node.op == "<":
            return left < right
        if node.op == ">":
            return left > right
        if node.op == "=" or node.op == "==":
            return left == right
        if node.op == "<=":
            return left <= right
        if node.op == ">=":
            return left >= right
        return left != right
    if isinstance(node, InTestNode):
        left = _eval_value(node.left, context, rng)
        right = _eval_value(node.right, context, rng)
        if isinstance(right, str):
            return str(left) in right
        if isinstance(right, (list, tuple, set)):
            return left in set(right)
        raise DslEvalError(f"in 右边必须是列表或字符串，实际类型为 {type(right).__name__}")
    if isinstance(node, NotInTestNode):
        left = _eval_value(node.left, context, rng)
        right = _eval_value(node.right, context, rng)
        if isinstance(right, str):
            return str(left) not in right
        if isinstance(right, (list, tuple, set)):
            return left not in set(right)
        raise DslEvalError(f"not in 右边必须是列表或字符串，实际类型为 {type(right).__name__}")
    if isinstance(node, ContainsNode):
        left = _eval_value(node.left, context, rng)
        right_name = node.right.value
        if isinstance(left, dict):
            return right_name in left
        if isinstance(left, (list, tuple, set)):
            return any(str(v) == right_name or v == right_name for v in left)
        if isinstance(left, str):
            return right_name in left
        raise DslEvalError(
            f"contains 左边必须是 dict、列表或字符串，实际类型为 {type(left).__name__}"
        )
    if isinstance(node, SubsetNode):
        left = _eval_value(node.left, context, rng)
        right = _eval_value(node.right, context, rng)
        return _to_set(left, "subset").issubset(_to_set(right, "subset"))
    if isinstance(node, SupersetNode):
        left = _eval_value(node.left, context, rng)
        right = _eval_value(node.right, context, rng)
        return _to_set(left, "superset").issuperset(_to_set(right, "superset"))
    if isinstance(node, IntersectsNode):
        left = _eval_value(node.left, context, rng)
        right = _eval_value(node.right, context, rng)
        return not _to_set(left, "intersects").isdisjoint(_to_set(right, "intersects"))
    if isinstance(node, DisjointNode):
        left = _eval_value(node.left, context, rng)
        right = _eval_value(node.right, context, rng)
        return _to_set(left, "disjoint").isdisjoint(_to_set(right, "disjoint"))
    if isinstance(node, AndNode):
        left = _eval_value(node.left, context, rng)
        right = _eval_value(node.right, context, rng)
        return bool(left) and bool(right)
    if isinstance(node, OrNode):
        left = _eval_value(node.left, context, rng)
        right = _eval_value(node.right, context, rng)
        return bool(left) or bool(right)
    if isinstance(node, NotNode):
        return not bool(_eval_value(node.operand, context, rng))
    if isinstance(node, TruthyNode):
        return _eval_value(node.value, context, rng)
    if isinstance(node, FunctionCallNode):
        return _eval_function_call(node, context, rng)
    raise DslEvalError(f"值节点类型非法: {node.kind!r}")


def _eval_function_call(node: FunctionCallNode, context: DslContext, rng: DslRng | None) -> Any:
    name = node.name
    if name == "rand":
        if rng is None:
            raise DslEvalError("rand 族函数需要注入 DslRng（rng 为 None）")
        if not node.args:
            return rng.rand()
        lo = _eval_value(node.args[0], context, rng)
        hi = _eval_value(node.args[1], context, rng)
        return rng.uniform(lo, hi)
    if name == "randint":
        if rng is None:
            raise DslEvalError("rand 族函数需要注入 DslRng（rng 为 None）")
        lo = int(_eval_value(node.args[0], context, rng))
        hi = int(_eval_value(node.args[1], context, rng))
        return rng.randint(lo, hi)
    if name == "len":
        arg = _eval_value(node.args[0], context, rng)
        if isinstance(arg, (list, tuple, set, str)):
            return len(arg)
        raise DslEvalError(f"len() 需要列表或字符串，实际类型为 {type(arg).__name__}")
    first = _eval_value(node.args[0], context, rng)
    second = _eval_value(node.args[1], context, rng)
    return min(first, second) if name == "min" else max(first, second)


# ── 行动面（v1 rules.py 逐字等价）──────────────────────────────────────


def action_text(action: ActionInput) -> str:
    """四键非空值以换行连接（v1 _action_text rules.py:33-38）。"""
    return "\n".join(
        part
        for part in (
            action.raw_input,
            action.interpreted_intent,
            action.action_description,
            action.speech_content,
        )
        if part
    )


def resolve_target(
    action: ActionInput,
    objects: Mapping[str, Any],
    locations: Mapping[str, Any],
) -> TargetRef:
    """目标解析（v1 _target_object rules.py:41-53 + _target_width :56-75
    合并等价物）：id 直查 → 文本含 name/object_id 首命中（objects 序）；
    宽度 = 对象 properties（effective_width_cm 优先 width_cm）→ location
    同法回退；source 标记宽度出处。"""
    text = action_text(action)

    target: dict[str, Any] | None = None
    target_key: str | None = None
    obj_id = action.target_object_id
    if obj_id and obj_id in objects:
        value = objects[obj_id]
        if isinstance(value, dict):
            target = value
            target_key = obj_id
    if target is None:
        for key, obj in objects.items():
            if not isinstance(obj, dict):
                continue
            name = obj.get("name", "")
            object_id = obj.get("object_id") or obj.get("id", "")
            if (name and name in text) or (object_id and object_id in text):
                target = obj
                target_key = key
                break

    width_cm: float | None = None
    source: str | None = None
    if target is not None:
        props = target.get("properties", {})
        width = props.get("effective_width_cm", props.get("width_cm")) if isinstance(
            props, dict
        ) else None
        if width is not None:
            width_cm = float(width)
            source = f"object:{target_key}"

    if width_cm is None:
        for loc in locations.values():
            if not isinstance(loc, dict):
                continue
            loc_id = loc.get("id", "")
            loc_name = loc.get("name", "")
            if (loc_id and loc_id in text) or (loc_name and loc_name in text):
                props = loc.get("properties", {})
                width = (
                    props.get("effective_width_cm", props.get("width_cm"))
                    if isinstance(props, dict)
                    else None
                )
                if width is not None:
                    width_cm = float(width)
                    source = f"location:{loc_id}"
                    break

    return TargetRef(object=target, width_cm=width_cm, source=source)


def _text_matches_rule(text: str, rule: str) -> bool:
    """文本-规则匹配（v1 rules.py:13-30 逐字：全串 ⊂ / 逗号切分 / 15 关键词）。"""
    if not text or not rule:
        return False
    normalized_text = text.lower()
    normalized_rule = rule.lower()
    if normalized_rule in normalized_text:
        return True
    parts = [
        part.strip()
        for part in normalized_rule.replace("，", ",").replace("、", ",").split(",")
    ]
    if any(part and part in normalized_text for part in parts):
        return True
    keywords = [
        token
        for token in (
            "道歉", "感谢", "不会跳舞", "秘密通道", "暗门", "命令", "仆人",
            "开锁", "门锁", "撬锁", "推", "搬", "拿起", "穿过", "通过",
        )
        if token in normalized_rule
    ]
    return bool(keywords) and any(token in normalized_text for token in keywords)


def check_action_feasibility(
    rules: Sequence[RuleSpec],
    action: ActionInput,
    context: DslContext,
    objects: Mapping[str, Any],
    locations: Mapping[str, Any],
    disabled: frozenset[str] = frozenset(),
    rng: DslRng | None = None,
) -> FeasibilityResult | None:
    """规则预判（永不抛；v1 check_action_feasibility rules.py:122-225 等价）。

    顺序：项目规则（过滤 disabled，按 (priority, id.casefold()) 排序；
    match 正则命中 ∧ condition 命中才出结果；失效条件 warn+skip）→ 内置
    1..5（BUILTIN_RULE_IDS 序，``disabled`` 按 ID 门禁）→ 全 miss = None。
    """
    text = action_text(action)
    target_ref = resolve_target(action, objects, locations)
    player = context.player
    capabilities = player.get("capabilities", {}) if isinstance(player, dict) else {}

    # ── 项目规则（v1 deterministic 自定义规则族；rules.py:137-145 口径）──
    active = sorted(
        (rule for rule in rules if not rule.disabled),
        key=lambda rule: (rule.priority, rule.id.casefold()),
    )
    for rule in active:
        if rule.match:
            try:
                pattern = re.compile(rule.match, re.IGNORECASE)
            except re.error:
                continue
            if not pattern.search(text):
                continue
        if rule.condition:
            parsed = parse_dsl(rule.condition, rule.id)
            if parsed.ast is None:
                logger.warning(
                    "deterministic rule %r condition failed: %s",
                    rule.id,
                    parsed.diagnostics[0].message,
                )
                continue
            try:
                outcome = evaluate_condition(parsed.ast, context, rng)
            except DslEvalError as exc:
                logger.warning("deterministic rule %r condition failed: %s", rule.id, exc)
                continue
            return FeasibilityResult(
                feasibility=outcome.feasibility,
                reason=f"系统规则预判（{rule.id}）：{rule.description}",
                matched_rule=f"custom:{rule.id}",
                success_probability=outcome.probability,
                requires_roll=outcome.feasibility is Feasibility.UNCERTAIN,
            )
        return FeasibilityResult(
            feasibility=Feasibility(rule.feasibility or "allowed"),
            reason=f"系统规则预判（{rule.id}）：{rule.description}",
            matched_rule=f"custom:{rule.id}",
            success_probability=rule.probability,
            requires_roll=rule.feasibility == "uncertain",
        )

    # ── 内置规则 1：blocked_common（v1 rules.py:150-158）─────────────
    if BUILTIN_RULE_IDS[0] not in disabled:
        for rule in capabilities.get("blocked_common_actions", []) or []:
            if _text_matches_rule(text, str(rule)):
                return FeasibilityResult(
                    feasibility=Feasibility.BLOCKED,
                    reason=f"系统规则预判：玩家人设限制不允许执行该行动（{rule}）。",
                    matched_rule=BUILTIN_RULE_IDS[0],
                )

    # ── 内置规则 2：extraordinary（v1 rules.py:160-168）──────────────
    if BUILTIN_RULE_IDS[1] not in disabled:
        for rule in capabilities.get("allowed_extraordinary_actions", []) or []:
            if _text_matches_rule(text, str(rule)):
                return FeasibilityResult(
                    feasibility=Feasibility.ALLOWED,
                    reason=f"系统规则预判：玩家具备可执行该行动的特殊能力（{rule}）。",
                    matched_rule=BUILTIN_RULE_IDS[1],
                )

    action_type = action.action_type

    # ── 内置规则 3+4：strength_vs_weight / skill_vs_lock（:170-206）──
    if action_type == "interact" and target_ref.object is not None:
        props = target_ref.object.get("properties", {})
        weight = props.get("weight_kg")
        if weight is not None and BUILTIN_RULE_IDS[2] not in disabled:
            strength = (context.player.get("physical_profile", {}) or {}).get("strength")
            if strength is not None:
                capacity = float(strength) * _STRENGTH_TO_KG_FACTOR
                weight_value = float(weight)
                if capacity < weight_value:
                    return FeasibilityResult(
                        feasibility=Feasibility.BLOCKED,
                        reason=(
                            f"系统规则预判：玩家力量约可移动 {capacity:.1f}kg，"
                            f"但目标物体重约 {weight_value:.1f}kg。"
                        ),
                        matched_rule=BUILTIN_RULE_IDS[2],
                    )
                if capacity < weight_value * 1.5:
                    return FeasibilityResult(
                        feasibility=Feasibility.UNCERTAIN,
                        reason="系统规则预判：玩家力量接近目标物体重量，行动可能成功但不稳定。",
                        matched_rule=BUILTIN_RULE_IDS[2],
                        success_probability=max(0.1, min(0.9, capacity / (weight_value * 1.5))),
                        requires_roll=True,
                    )

        lock_difficulty = props.get("lock_difficulty")
        if lock_difficulty is not None and BUILTIN_RULE_IDS[3] not in disabled:
            skill = float((capabilities.get("skill_levels", {}) or {}).get("lockpicking", 0.0))
            difficulty = float(lock_difficulty)
            if skill < difficulty:
                probability = max(0.05, min(0.95, skill / difficulty if difficulty else 0.05))
                return FeasibilityResult(
                    feasibility=Feasibility.UNCERTAIN,
                    reason=f"系统规则预判：开锁技能 {skill:.2f} 低于锁难度 {difficulty:.2f}。",
                    matched_rule=BUILTIN_RULE_IDS[3],
                    success_probability=probability,
                    requires_roll=True,
                )
            return FeasibilityResult(
                feasibility=Feasibility.ALLOWED,
                reason=f"系统规则预判：开锁技能 {skill:.2f} 不低于锁难度 {difficulty:.2f}。",
                matched_rule=BUILTIN_RULE_IDS[3],
            )

    # ── 内置规则 5：body_width_vs_passage（v1 rules.py:208-223）──────
    if action_type == "move" and BUILTIN_RULE_IDS[4] not in disabled:
        width = target_ref.width_cm
        body_width = (context.player.get("physical_profile", {}) or {}).get("body_width_cm")
        if width is not None and body_width is not None:
            body_width_value = float(body_width)
            if body_width_value > width:
                return FeasibilityResult(
                    feasibility=Feasibility.BLOCKED,
                    reason=f"系统规则预判：玩家身体宽度 {body_width_value:.1f}cm 大于通道宽度 {width:.1f}cm。",
                    matched_rule=BUILTIN_RULE_IDS[4],
                )
            return FeasibilityResult(
                feasibility=Feasibility.ALLOWED,
                reason=f"系统规则预判：玩家身体宽度 {body_width_value:.1f}cm 可以通过宽度 {width:.1f}cm 的空间。",
                matched_rule=BUILTIN_RULE_IDS[4],
            )

    return None
