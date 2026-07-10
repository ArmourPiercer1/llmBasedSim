"""Tick speed expression evaluator for dynamic tick advancement.

Syntax is consistent with src/game/condition_eval.py (same if/else chain,
comparison/arithmetic operators, min/max functions, player.attr variable
access pattern), but outputs float (minutes) instead of ConditionOutcome.

Examples:
    if(player.status_effects contains fighting, min(npc_time); 5.0)
    if(player_action.action_type = move, max(player_time, min(npc_time)); default)
    if(player.duration < 2.0, 1.0; player.duration < 10.0, 5.0; 10.0)
"""

from __future__ import annotations

import re
import random as _random
from dataclasses import dataclass
from typing import Any


class TickEvalError(ValueError):
    """Raised on expression syntax or resolution errors."""


@dataclass(frozen=True)
class Token:
    kind: str  # "number", "name", "op"
    value: str


_TOKEN_RE = re.compile(
    r"\s*(?:(?P<number>\d+(?:\.\d+)?)"
    r"|(?P<string>\"[^\"]*\")"
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_.]*|[一-鿿][一-鿿A-Za-z0-9_.]*)"
    r"|(?P<op><=|>=|!=|[+\-*/<>=(),;:]))"
)
_COMPARATORS = {"<", ">", "=", "<=", ">=", "!="}


def _tokenize(expression: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(expression):
        m = _TOKEN_RE.match(expression, pos)
        if not m:
            raise TickEvalError(f"Cannot parse: {expression[pos:pos+20]!r}")
        pos = m.end()
        if m.lastgroup == "number":
            tokens.append(Token("number", m.group(m.lastgroup)))
        elif m.lastgroup == "string":
            tokens.append(Token("string", m.group(m.lastgroup)[1:-1]))
        elif m.lastgroup == "name":
            tokens.append(Token("name", m.group(m.lastgroup)))
        elif m.lastgroup == "op":
            tokens.append(Token("op", m.group(m.lastgroup)))
    return tokens


def evaluate_tick_expression(expression: str, context: dict[str, Any]) -> float:
    """Evaluate a tick speed expression returning game-minutes as float."""
    parser = _Parser(_tokenize(expression), context)
    result = parser.parse_if()
    parser.expect_end()
    return result


# ---------------------------------------------------------------------------
# Internal parser (recursive descent, mirrors condition_eval structure)
# ---------------------------------------------------------------------------

class _Parser:
    _SET_KEYWORDS = frozenset({"subset", "superset", "intersects", "disjoint"})
    _CONDITION_KEYWORDS = frozenset({"and", "or", "not", "in", "contains"}).union(_SET_KEYWORDS)

    def __init__(self, tokens: list[Token], context: dict[str, Any]) -> None:
        self.tokens = tokens
        self.context = context
        self.pos = 0

    # -- public entry points ------------------------------------------------

    def parse_if(self) -> float:
        name = self._consume_name()
        if name != "if":
            raise TickEvalError("Expression must start with if(...)")
        self._consume_op("(")

        while True:
            if self._looks_like_condition():
                matched = self._parse_condition()
                self._consume_op(",")
                value = self.parse_value()
                if matched:
                    self._skip_until_if_end()
                    return value
                if self._match_op(";"):
                    continue
                self._consume_op(")")
                raise TickEvalError("if(...) missing else value")
            # default (else) value
            value = self.parse_value()
            self._consume_op(")")
            return value

    def expect_end(self) -> None:
        if self._peek() is not None:
            raise TickEvalError(
                f"Unexpected trailing content: {self._peek().value!r}"
            )

    # -- Boolean condition parsing ------------------------------------------

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
            if isinstance(left, str) or isinstance(right, str):
                left_s = str(left)
                right_s = str(right)
                if op in ("=", "=="):
                    return left_s == right_s
                if op == "!=":
                    return left_s != right_s
                raise TickEvalError(f"String does not support {op!r} comparison")
            return _compare(left, op, right)

        # Set / collection / contains operations
        if token.kind == "name":
            if token.value == "in":
                self._advance()
                right = self.parse_add_sub()
                if isinstance(right, str):
                    return str(left) in right
                if isinstance(right, (list, tuple, set)):
                    return left in set(right)
                raise TickEvalError(
                    f"in right-hand side must be list or string, got {type(right).__name__}"
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
                    raise TickEvalError(
                        f"not in right-hand side must be list or string, got {type(right).__name__}"
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
                raise TickEvalError(
                    f"contains left-hand side must be dict, list, or string, got {type(left).__name__}"
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

    # -- numeric / scalar expression parsing --------------------------------

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
                    raise TickEvalError("Division by zero")
                value = value / divisor
            else:
                return value

    def parse_primary(self) -> Any:
        if self._match_op("-"):
            return -self.parse_primary()
        if self._match_op("("):
            if self._looks_like_condition():
                value = self._parse_or()
                self._consume_op(")")
                return bool(value)
            value = self.parse_add_sub()
            self._consume_op(")")
            return value

        token = self._advance()
        if token.kind == "number":
            return float(token.value)
        if token.kind == "string":
            return token.value

        if token.kind != "name":
            raise TickEvalError(f"Unexpected token: {token.value!r}")

        name = token.value

        # Function calls
        if name == "rand" and self._match_op("("):
            if self._match_op(")"):
                return _random.random()
            lo = self.parse_add_sub()
            self._consume_op(",")
            hi = self.parse_add_sub()
            self._consume_op(")")
            return _random.uniform(lo, hi)
        if name == "randint" and self._match_op("("):
            lo = int(self.parse_add_sub())
            self._consume_op(",")
            hi = int(self.parse_add_sub())
            self._consume_op(")")
            return float(_random.randint(lo, hi))
        if name in ("min", "max", "avg") and self._match_op("("):
            return self._eval_aggregate(name)
        if name == "len" and self._match_op("("):
            arg = self.parse_add_sub()
            self._consume_op(")")
            if isinstance(arg, (list, tuple, set, str)):
                return len(arg)
            raise TickEvalError(
                f"len() requires list or string, got {type(arg).__name__}"
            )

        # Variable resolution
        return _resolve_value(name, self.context)

    # -- aggregate function evaluation --------------------------------------

    def _eval_aggregate(self, func_name: str) -> float:
        """Evaluate min(npc_time), max(npc_time), avg(npc_time),
        or min(a, b) / max(a, b) (two-arg scalar)."""
        first = self.parse_add_sub()

        if self._match_op(","):
            second = self.parse_add_sub()
            self._consume_op(")")
            if func_name == "min":
                return min(first, second)
            if func_name == "max":
                return max(first, second)
            raise TickEvalError(f"avg() requires a single list argument")

        self._consume_op(")")
        return _aggregate_list(func_name, first)

    # -- value parsing -------------------------------------------------------

    def parse_value(self) -> float:
        """Parse the value portion of a tick-speed branch. Supports nested if()."""
        token = self._peek()
        if token and token.kind == "name" and token.value == "if":
            return self.parse_if()
        return self.parse_add_sub()

    # -- helpers ------------------------------------------------------------

    def _looks_like_condition(self) -> bool:
        depth = 0
        i = self.pos
        while i < len(self.tokens):
            t = self.tokens[i]
            if t.kind == "op":
                if t.value == "(":
                    depth += 1
                elif t.value == ")":
                    if depth == 0:
                        return False
                    depth -= 1
                elif depth == 0:
                    if t.value in _COMPARATORS:
                        return True
                    if t.value == ",":
                        return True
                    if t.value == ";":
                        return False
            elif t.kind == "name" and depth == 0:
                if t.value in self._CONDITION_KEYWORDS:
                    return True
            i += 1
        return False

    def _skip_until_if_end(self) -> None:
        depth = 0
        while self._peek() is not None:
            t = self._advance()
            if t.kind == "op":
                if t.value == "(":
                    depth += 1
                elif t.value == ")":
                    if depth == 0:
                        return
                    depth -= 1

    @staticmethod
    def _to_set(value: Any, keyword: str) -> set:
        if isinstance(value, (list, tuple, set)):
            return set(value)
        raise TickEvalError(
            f"{keyword} requires list type, got {type(value).__name__}"
        )

    def _peek(self, offset: int = 0) -> Token | None:
        idx = self.pos + offset
        return self.tokens[idx] if idx < len(self.tokens) else None

    def _advance(self) -> Token:
        t = self._peek()
        if t is None:
            raise TickEvalError("Unexpected end of expression")
        self.pos += 1
        return t

    def _match_op(self, value: str) -> bool:
        t = self._peek()
        if t and t.kind == "op" and t.value == value:
            self.pos += 1
            return True
        return False

    def _match_name(self, value: str) -> bool:
        t = self._peek()
        if t and t.kind == "name" and t.value == value:
            self.pos += 1
            return True
        return False

    def _consume_op(self, value: str) -> None:
        if not self._match_op(value):
            found = self._peek().value if self._peek() else "end"
            raise TickEvalError(f"Expected {value!r}, got {found!r}")

    def _consume_name(self) -> str:
        t = self._advance()
        if t.kind != "name":
            raise TickEvalError(f"Expected name, got {t.value!r}")
        return t.value


# ---------------------------------------------------------------------------
# Variable / value resolution helpers
# ---------------------------------------------------------------------------

def _resolve_path(path: str, context: dict[str, Any]) -> Any:
    """Resolve a dotted path like ``player.status_effects`` in context."""
    parts = path.split(".")
    current: Any = context
    for part in parts:
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                raise TickEvalError(f"Cannot resolve path {path!r}: {part!r} not found")
        else:
            raise TickEvalError(
                f"Cannot resolve path {path!r}: {type(current).__name__} has no key {part!r}"
            )
    return current


def _resolve_value(name: str, context: dict[str, Any]) -> Any:
    """Resolve a name to a value from the evaluation context.

    Special context keys handled here:
      - ``npc_durations`` → list[float] (for use in aggregate functions)
      - ``player_duration`` → float
      - ``default`` → float
      - ``player.<attr>`` / ``player_action.<field>`` → nested path
    """
    # Special list variable (used only by aggregate functions)
    if name == "npc_durations":
        val = context.get("npc_durations", [])
        if not isinstance(val, (list, tuple)):
            raise TickEvalError("npc_durations is not a list")
        return _ListProxy(val)

    # Special scalars
    if name == "player_duration":
        return _numeric(context.get("player_duration", 0.0), name)
    if name == "default":
        return _numeric(context.get("default", 5.0), name)

    # Dotted path: player.xxx, player_action.xxx
    if "." in name:
        return _resolve_path(name, context)

    # Fallback: direct context key
    if name in context:
        val = context[name]
        if isinstance(val, (list, tuple)):
            return _ListProxy(val)
        return val

    # Undotted bare name not in context → treat as string literal
    # (e.g. "move" in `player_action.action_type = move`)
    if "." not in name:
        return name

    raise TickEvalError(f"Unknown variable {name!r}")


class _ListProxy:
    """Thin wrapper so list variables can flow through the arithmetic parser
    into aggregate functions without raising type errors."""

    __slots__ = ("items",)

    def __init__(self, items: list[float]) -> None:
        self.items = items

    def __float__(self) -> float:
        # Fallback: return min of list if used as scalar
        return min(self.items) if self.items else 0.0

    def __repr__(self) -> str:
        return f"<ListProxy: {self.items!r}>"


def _aggregate_list(func: str, value: float) -> float:
    """Evaluate an aggregate function on a list. ``value`` is expected
    to be a ``_ListProxy`` obtained from resolving a list variable name."""
    if not isinstance(value, _ListProxy):
        raise TickEvalError(f"{func}() requires a list variable")
    items = value.items
    if not items:
        raise TickEvalError(f"{func}() on empty list")
    if func == "min":
        return min(items)
    if func == "max":
        return max(items)
    # func == "avg" — guaranteed by _eval_aggregate
    return sum(items) / len(items)


def _numeric(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise TickEvalError(f"Variable {name!r} is not numeric")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise TickEvalError(f"Variable {name!r} is not numeric") from exc


def _compare(left: float, op: str, right: float) -> bool:
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
    # op == "!=" or "!"
    return left != right
