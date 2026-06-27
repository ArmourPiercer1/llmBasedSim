from __future__ import annotations

import re
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
    r"\s*(?:(?P<number>\d+(?:\.\d+)?)|(?P<name>[A-Za-z_][A-Za-z0-9_\.]*|[一-鿿][一-鿿A-Za-z0-9_\.]*)|(?P<op><=|>=|!=|[+\-*/<>=(),;:]))"
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
        elif match.lastgroup == "name":
            tokens.append(Token("name", match.group(match.lastgroup)))
        elif match.lastgroup == "op":
            tokens.append(Token("op", match.group(match.lastgroup)))
    return tokens


class _Parser:
    def __init__(self, tokens: list[Token], context: dict[str, Any]) -> None:
        self.tokens = tokens
        self.context = context
        self.pos = 0

    def parse_if(self) -> ConditionOutcome:
        name = self._consume_name()
        if name != "if":
            raise ConditionEvalError("条件表达式必须以 if(...) 开始")
        self._consume_op("(")

        while True:
            if self._looks_like_condition():
                matched = self.parse_comparison()
                self._consume_op(",")
                outcome = self.parse_outcome()
                if matched:
                    self._skip_until_if_end()
                    return outcome
                if self._match_op(";"):
                    continue
                self._consume_op(")")
                raise ConditionEvalError("if(...) 缺少 else 输出")

            outcome = self.parse_outcome()
            self._consume_op(")")
            return outcome

    def parse_comparison(self) -> bool:
        left = self.parse_add_sub()
        token = self._peek()
        if token is None or token.kind != "op" or token.value not in _COMPARATORS:
            raise ConditionEvalError("条件分支必须包含比较运算符")
        op = self._advance().value
        right = self.parse_add_sub()
        if op == "<":
            return left < right
        if op == ">":
            return left > right
        if op == "=":
            return left == right
        if op == "<=":
            return left <= right
        if op == ">=":
            return left >= right
        return left != right

    def parse_add_sub(self) -> float:
        value = self.parse_mul_div()
        while True:
            if self._match_op("+"):
                value += self.parse_mul_div()
            elif self._match_op("-"):
                value -= self.parse_mul_div()
            else:
                return value

    def parse_mul_div(self) -> float:
        value = self.parse_primary()
        while True:
            if self._match_op("*"):
                value *= self.parse_primary()
            elif self._match_op("/"):
                divisor = self.parse_primary()
                if divisor == 0:
                    raise ConditionEvalError("条件表达式中出现除零")
                value /= divisor
            else:
                return value

    def parse_primary(self) -> float:
        if self._match_op("-"):
            return -self.parse_primary()
        if self._match_op("("):
            value = self.parse_add_sub()
            self._consume_op(")")
            return value

        token = self._advance()
        if token.kind == "number":
            return float(token.value)
        if token.kind == "name":
            if token.value in ("min", "max") and self._match_op("("):
                first = self.parse_add_sub()
                self._consume_op(",")
                second = self.parse_add_sub()
                self._consume_op(")")
                return min(first, second) if token.value == "min" else max(first, second)
            return self._resolve_variable(token.value)
        raise ConditionEvalError(f"条件表达式中不应出现 {token.value!r}")

    def parse_outcome(self) -> ConditionOutcome:
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
                    if token.value in {",", ";"}:
                        return False
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

    def _resolve_variable(self, name: str) -> float:
        if name.startswith("player."):
            return _numeric(_lookup_player(name[7:], self.context.get("player", {})), name)
        if name.startswith("target."):
            return _numeric(_lookup_target(name[7:], self.context.get("target", {})), name)
        value = self.context.get(name)
        if value is None:
            raise ConditionEvalError(f"未知变量 {name!r}")
        return _numeric(value, name)

    def _peek(self) -> Token | None:
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

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
