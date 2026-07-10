from __future__ import annotations

import re
import random as _random
from dataclasses import dataclass
from typing import Any


class ConditionEvalError(ValueError):
    pass


@dataclass(frozen=True)
class ConditionOutcome:
    feasibility: str
    probability: float | None = None


@dataclass(frozen=True)
class Token:
    kind: str
    value: str


_TOKEN_RE = re.compile(
    r'\s*(?:(?P<number>\d+(?:\.\d+)?)'
    r'|(?P<string>"[^"]*")'
    r'|(?P<name>[A-Za-z_][A-Za-z0-9_\.]*|[一-鿿][一-鿿A-Za-z0-9_\.]*)'
    r'|(?P<op><=|>=|!=|[+\-*/<>=(),;:]))'
)
_VALID_OUTCOMES = {"allowed", "blocked", "uncertain"}
_COMPARATORS = {"<", ">", "=", "<=", ">=", "!="}


def evaluate_condition(expression: str, context: dict[str, Any]) -> ConditionOutcome:
    parser = _Parser(_tokenize(expression), context)
    outcome = parser.parse_if()
    parser.expect_end()
    return outcome


def _tokenize(expression: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(expression):
        match = _TOKEN_RE.match(expression, pos)
        if not match:
            raise ConditionEvalError(f"无法解析条件表达式片段: {expression[pos:pos + 20]!r}")
        pos = match.end()
        if match.lastgroup == "number":
            tokens.append(Token("number", match.group(match.lastgroup)))
        elif match.lastgroup == "string":
            tokens.append(Token("string", match.group(match.lastgroup)[1:-1]))
        elif match.lastgroup == "name":
            tokens.append(Token("name", match.group(match.lastgroup)))
        elif match.lastgroup == "op":
            tokens.append(Token("op", match.group(match.lastgroup)))
    return tokens


class _Parser:
    _SET_KEYWORDS = frozenset({"subset", "superset", "intersects", "disjoint"})
    _CONDITION_KEYWORDS = frozenset({"and", "or", "not", "in", "contains"}).union(_SET_KEYWORDS)

    def __init__(self, tokens: list[Token], context: dict[str, Any]) -> None:
        self.tokens = tokens
        self.context = context
        self.pos = 0

    # ── Top-level if(…) entry ──

    def parse_if(self) -> ConditionOutcome:
        name = self._consume_name()
        if name != "if":
            raise ConditionEvalError("条件表达式必须以 if(...) 开始")
        self._consume_op("(")

        while True:
            if self._looks_like_condition():
                matched = self._parse_condition()
                self._consume_op(",")
                outcome = self._parse_outcome()
                if matched:
                    self._skip_until_if_end()
                    return outcome
                if self._match_op(";"):
                    continue
                self._consume_op(")")
                raise ConditionEvalError("if(...) 缺少 else 输出")

            outcome = self._parse_outcome()
            self._consume_op(")")
            return outcome

    # ── Boolean condition parsing ──

    def _parse_condition(self) -> bool:
        return bool(self._parse_or())

    def _parse_or(self) -> Any:
        left = self._parse_and()
        while self._match_name("or"):
            right = self._parse_and()
            left = bool(left) or bool(right)
        return left

    def _parse_and(self) -> Any:
        left = self._parse_not()
        while self._match_name("and"):
            right = self._parse_not()
            left = bool(left) and bool(right)
        return left

    def _parse_not(self) -> Any:
        if self._match_name("not"):
            return not bool(self._parse_not())
        return self._parse_comparison()

    def _parse_comparison(self) -> Any:
        left = self.parse_add_sub()
        token = self._peek()
        if token is None:
            return left  # truthy single-value

        # Numeric/string comparison: < > = <= >= !=
        if token.kind == "op" and token.value in _COMPARATORS:
            op = self._advance().value
            right = self.parse_add_sub()
            # String comparison when either side is a string
            if isinstance(left, str) or isinstance(right, str):
                left_s = str(left)
                right_s = str(right)
                if op == "=" or op == "==":
                    return left_s == right_s
                if op == "!=":
                    return left_s != right_s
                raise ConditionEvalError(f"字符串不支持 {op!r} 比较")
            if op == "<":   return left < right
            if op == ">":   return left > right
            if op == "=" or op == "==":  return left == right
            if op == "<=":  return left <= right
            if op == ">=":  return left >= right
            return left != right

        # Set / collection operations (name tokens)
        if token.kind == "name":
            if token.value == "in":
                self._advance()
                right = self.parse_add_sub()
                if isinstance(right, str):
                    return str(left) in right
                if isinstance(right, (list, tuple, set)):
                    return left in set(right)
                raise ConditionEvalError(
                    f"in 右边必须是列表或字符串，实际类型为 {type(right).__name__}"
                )
            if token.value == "not":
                if self._peek(1) and self._peek(1).kind == "name" and self._peek(1).value == "in":
                    self._advance()
                    self._advance()
                    right = self.parse_add_sub()
                    if isinstance(right, str):
                        return str(left) not in right
                    if isinstance(right, (list, tuple, set)):
                        return left not in set(right)
                    raise ConditionEvalError(
                        f"not in 右边必须是列表或字符串，实际类型为 {type(right).__name__}"
                    )
            if token.value == "contains":
                self._advance()
                right_name = self._consume_name()
                if isinstance(left, dict):
                    return right_name in left
                if isinstance(left, (list, tuple, set)):
                    return any(str(v) == right_name or v == right_name for v in left)
                if isinstance(left, str):
                    return right_name in left
                raise ConditionEvalError(
                    f"contains 左边必须是 dict、列表或字符串，实际类型为 {type(left).__name__}"
                )
            if token.value in self._SET_KEYWORDS:
                keyword = self._advance().value
                right = self.parse_add_sub()
                left_set = self._to_set(left, keyword)
                right_set = self._to_set(right, keyword)
                if keyword == "subset":
                    return left_set.issubset(right_set)
                if keyword == "superset":
                    return left_set.issuperset(right_set)
                if keyword == "intersects":
                    return not left_set.isdisjoint(right_set)
                if keyword == "disjoint":
                    return left_set.isdisjoint(right_set)

        return left  # truthy single-value

    # ── Arithmetic ──

    def parse_add_sub(self) -> Any:
        value = self.parse_mul_div()
        while True:
            if self._match_op("+"):
                value = value + self.parse_mul_div()
            elif self._match_op("-"):
                value = value - self.parse_mul_div()
            else:
                return value

    def parse_mul_div(self) -> Any:
        value = self.parse_primary()
        while True:
            if self._match_op("*"):
                value = value * self.parse_primary()
            elif self._match_op("/"):
                divisor = self.parse_primary()
                if divisor == 0:
                    raise ConditionEvalError("条件表达式中出现除零")
                value = value / divisor
            else:
                return value

    def parse_primary(self) -> Any:
        if self._match_op("-"):
            return -self.parse_primary()
        if self._match_op("("):
            # Boolean grouping (contains comparisons / and / or / not / set ops)
            if self._looks_like_condition():
                value = self._parse_or()
                self._consume_op(")")
                return bool(value)
            # Arithmetic grouping
            value = self.parse_add_sub()
            self._consume_op(")")
            return value

        token = self._advance()
        if token.kind == "number":
            return float(token.value)
        if token.kind == "string":
            return token.value
        if token.kind == "name":
            # Function calls: rand(), rand(a,b), randint(a,b), min(a,b), max(a,b), len(expr)
            if token.value in ("rand", "randint", "min", "max", "len") and self._match_op("("):
                func_name = token.value
                if func_name == "rand":
                    if self._match_op(")"):
                        return _random.random()
                    # rand(min, max)
                    lo = self.parse_add_sub()
                    self._consume_op(",")
                    hi = self.parse_add_sub()
                    self._consume_op(")")
                    return _random.uniform(lo, hi)
                if func_name == "randint":
                    lo = int(self.parse_add_sub())
                    self._consume_op(",")
                    hi = int(self.parse_add_sub())
                    self._consume_op(")")
                    return _random.randint(lo, hi)
                if func_name == "len":
                    arg = self.parse_add_sub()
                    self._consume_op(")")
                    if isinstance(arg, (list, tuple, set, str)):
                        return len(arg)
                    raise ConditionEvalError(
                        f"len() 需要列表或字符串，实际类型为 {type(arg).__name__}"
                    )
                # min / max
                first = self.parse_add_sub()
                self._consume_op(",")
                second = self.parse_add_sub()
                self._consume_op(")")
                return min(first, second) if func_name == "min" else max(first, second)
            return self._resolve_variable(token.value)
        raise ConditionEvalError(f"条件表达式中不应出现 {token.value!r}")

    # ── Outcome parsing ──

    def _parse_outcome(self) -> ConditionOutcome:
        # Nested if()
        token = self._peek()
        if token and token.kind == "name" and token.value == "if":
            return self.parse_if()

        token = self._advance()
        if token.kind != "name":
            raise ConditionEvalError("输出必须是 allowed、blocked 或 uncertain")
        feasibility = token.value.lower()
        if feasibility not in _VALID_OUTCOMES:
            raise ConditionEvalError(f"非法输出 {token.value!r}")

        probability = None
        if feasibility == "uncertain":
            probability = 0.5
            if self._match_op(":"):
                probability = self.parse_add_sub()
                if not 0 < probability < 1:
                    raise ConditionEvalError("uncertain 概率必须在 0 和 1 之间")
        return ConditionOutcome(feasibility, probability)

    # ── Helpers ──

    def expect_end(self) -> None:
        if self._peek() is not None:
            raise ConditionEvalError(f"条件表达式末尾存在多余内容: {self._peek().value!r}")

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
                if token.value in self._CONDITION_KEYWORDS:
                    return True
            i += 1
        return False

    def _skip_until_if_end(self) -> None:
        depth = 0
        while self._peek() is not None:
            token = self._advance()
            if token.kind == "op" and token.value == "(":
                depth += 1
            elif token.kind == "op" and token.value == ")":
                if depth == 0:
                    return
                depth -= 1

    def _resolve_variable(self, name: str) -> Any:
        if name.startswith("player."):
            return _lookup_player(name[7:], self.context.get("player", {}))
        if name.startswith("target."):
            return _lookup_target(name[7:], self.context.get("target", {}))
        value = self.context.get(name)
        if value is None:
            raise ConditionEvalError(f"未知变量 {name!r}")
        return value

    @staticmethod
    def _to_set(value: Any, keyword: str) -> set:
        if isinstance(value, (list, tuple, set)):
            return set(value)
        raise ConditionEvalError(
            f"{keyword} 运算需要列表类型，实际类型为 {type(value).__name__}"
        )

    def _peek(self, offset: int = 0) -> Token | None:
        idx = self.pos + offset
        return self.tokens[idx] if idx < len(self.tokens) else None

    def _advance(self) -> Token:
        token = self._peek()
        if token is None:
            raise ConditionEvalError("条件表达式意外结束")
        self.pos += 1
        return token

    def _match_op(self, value: str) -> bool:
        token = self._peek()
        if token and token.kind == "op" and token.value == value:
            self.pos += 1
            return True
        return False

    def _match_name(self, value: str) -> bool:
        token = self._peek()
        if token and token.kind == "name" and token.value == value:
            self.pos += 1
            return True
        return False

    def _consume_op(self, value: str) -> None:
        if not self._match_op(value):
            found = self._peek().value if self._peek() else "表达式结束"
            raise ConditionEvalError(f"预期 {value!r}，但得到 {found!r}")

    def _consume_name(self) -> str:
        token = self._advance()
        if token.kind != "name":
            raise ConditionEvalError(f"预期名称，但得到 {token.value!r}")
        return token.value


def _lookup_player(name: str, player: Any) -> Any:
    if not isinstance(player, dict):
        raise ConditionEvalError(f"无法读取 player.{name}")

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

    raise ConditionEvalError(f"未知变量 player.{name}")


def _lookup_target(name: str, target: Any) -> Any:
    if not isinstance(target, dict):
        raise ConditionEvalError(f"无法读取 target.{name}")

    props = target.get("properties")
    if isinstance(props, dict):
        aliases = {
            "weight": ("weight_kg", "weight"),
            "width": ("effective_width_cm", "width_cm", "width"),
        }.get(name, (name,))
        for key in aliases:
            if key in props:
                return props[key]

    if name in target:
        return target[name]

    raise ConditionEvalError(f"未知变量 target.{name}")


def _numeric(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ConditionEvalError(f"变量 {name} 不是数值")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConditionEvalError(f"变量 {name} 不是数值") from exc
