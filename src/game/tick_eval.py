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
                matched = self._eval_condition()
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

    # -- condition evaluation (returns bool) --------------------------------

    def _eval_condition(self) -> bool:
        """Handle a condition branch — contains, string comparison, or numeric."""
        # Look-ahead for "X contains Y" pattern
        saved = self.pos
        first_name = self._peek()
        if first_name and first_name.kind == "name":
            second = self._peek(1)
            if second and second.kind == "name" and second.value == "contains":
                return self._eval_contains()

        # String comparison: dotted_path = bare_name (e.g. player_action.action_type = move)
        self.pos = saved
        left_tok = self._peek()
        if left_tok and left_tok.kind == "name" and "." in left_tok.value:
            op_tok = self._peek(1)
            if op_tok and op_tok.kind == "op" and op_tok.value in ("=", "!="):
                right_tok = self._peek(2)
                if right_tok and right_tok.kind == "name":
                    left_val = _resolve_path(left_tok.value, self.context)
                    if isinstance(left_val, str):
                        self.pos += 3
                        op = op_tok.value
                        return (left_val == right_tok.value) if op == "=" else (left_val != right_tok.value)

        # Numeric comparison
        self.pos = saved
        left = self.parse_add_sub()
        token = self._advance()
        if token.kind != "op" or token.value not in _COMPARATORS:
            raise TickEvalError(
                f"Expected comparison operator, got {token.value!r}"
            )
        op = token.value
        right = self.parse_add_sub()
        return _compare(left, op, right)

    def _eval_contains(self) -> bool:
        """Evaluate ``player.status_effects contains fighting`` style."""
        left_path = self._advance().value  # e.g. "player.status_effects"
        self._advance()  # consume "contains" token
        right_name = self._advance().value  # e.g. "fighting"
        # NOTE: comma after condition is consumed by parse_if, not here
        # Look up left side in context
        left_val = _resolve_path(left_path, self.context)
        # Check containment
        if isinstance(left_val, dict):
            return right_name in left_val
        if isinstance(left_val, (list, tuple, set)):
            return any(str(v) == right_name or v == right_name for v in left_val)
        if isinstance(left_val, str):
            return right_name in left_val
        raise TickEvalError(
            f"Cannot check contains on {type(left_val).__name__}: {left_path!r}"
        )

    # -- numeric expression parsing -----------------------------------------

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
                    raise TickEvalError("Division by zero")
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

        if token.kind != "name":
            raise TickEvalError(f"Unexpected token: {token.value!r}")

        name = token.value

        # Function calls: min(x, y) or min(list_name)
        if name in ("min", "max", "avg") and self._match_op("("):
            return self._eval_aggregate(name)

        # Variable resolution
        return _resolve_value(name, self.context)

    # -- aggregate function evaluation --------------------------------------

    def _eval_aggregate(self, func_name: str) -> float:
        """Evaluate ``min(npc_time)``, ``max(npc_time)``, ``avg(npc_time)``,
        or ``min(a, b)`` / ``max(a, b)`` (two-arg scalar)."""
        first = self.parse_add_sub()

        if self._match_op(","):
            # Two-argument form: min(a, b)
            second = self.parse_add_sub()
            self._consume_op(")")
            if func_name == "min":
                return min(first, second)
            if func_name == "max":
                return max(first, second)
            raise TickEvalError(f"avg() requires a single list argument")

        self._consume_op(")")

        # Single-argument form — 'first' was the list variable value
        return _aggregate_list(func_name, first)

    # -- value parsing (the value after a condition comma) -------------------

    def parse_value(self) -> float:
        """Parse the value portion of a tick-speed branch (a float expression)."""
        return self.parse_add_sub()

    # -- helpers ------------------------------------------------------------

    def _looks_like_condition(self) -> bool:
        """Heuristic: if there is a comparison operator or ``contains``
        before a comma or semicolon at the current nesting, treat as condition."""
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
                    if t.value in {",", ";"}:
                        return False
            elif t.kind == "name" and t.value == "contains" and depth == 0:
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


def _resolve_value(name: str, context: dict[str, Any]) -> float:
    """Resolve a name to a numeric value from the evaluation context.

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
        # Return a sentinel-like proxy — the caller must handle it
        return _ListProxy(val)

    # Special scalars
    if name == "player_duration":
        return _numeric(context.get("player_duration", 0.0), name)
    if name == "default":
        return _numeric(context.get("default", 5.0), name)

    # Dotted path: player.xxx, player_action.xxx
    if "." in name:
        val = _resolve_path(name, context)
        if isinstance(val, str):
            return val  # String values handled by _eval_condition
        return _numeric(val, name)

    # Fallback: direct context key
    if name in context:
        return _numeric(context[name], name)

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
