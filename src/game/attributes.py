from __future__ import annotations

import re as _re
import random as _random
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


def _clamp(value: float, attr: dict[str, Any]) -> float:
    minimum = attr.get("min")
    maximum = attr.get("max")
    if minimum is not None:
        value = max(float(minimum), value)
    if maximum is not None:
        value = min(float(maximum), value)
    return value


def _attribute_name(key: str, attr: dict[str, Any]) -> str:
    return str(attr.get("name") or key)


def _apply_delta(attr: dict[str, Any], delta: float) -> tuple[dict[str, Any], float, float] | None:
    if attr.get("locked"):
        return None
    try:
        current = float(attr.get("value", 0.0))
    except (TypeError, ValueError):
        return None
    updated = _clamp(current + delta, attr)
    new_attr = {**attr, "value": updated}
    return new_attr, current, updated


def _apply_new_value(attr: dict[str, Any], new_value: Any) -> tuple[dict[str, Any], object, object] | None:
    if attr.get("locked"):
        return None
    old = attr.get("value")
    return {**attr, "value": new_value}, old, new_value


def _normalize_attributes(entity: dict[str, Any]) -> dict[str, dict[str, Any]]:
    attrs = entity.get("attributes", {}) if isinstance(entity, dict) else {}
    if not isinstance(attrs, dict):
        return {}
    normalized = {}
    for key, value in attrs.items():
        if isinstance(value, dict):
            normalized[str(key)] = {**value}
        else:
            try:
                normalized[str(key)] = {"name": str(key), "value": float(value)}
            except (TypeError, ValueError):
                normalized[str(key)] = {"name": str(key), "value": value}
    return normalized


def compute_attribute_deltas_diff(
    before_player: dict[str, Any],
    before_characters: dict[str, dict[str, Any]],
    after_player: dict[str, Any],
    after_characters: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compare pre-delta vs post-delta attribute values; return structured diffs."""
    deltas: list[dict[str, Any]] = []

    def _diff_entity(
        before: dict[str, Any],
        after: dict[str, Any],
        entity_type: str,
        entity_id: str,
        entity_name: str,
    ) -> None:
        before_attrs = _normalize_attributes(before)
        after_attrs = _normalize_attributes(after)
        for key, after_attr in after_attrs.items():
            before_attr = before_attrs.get(key, {})
            old_val = before_attr.get("value")
            new_val = after_attr.get("value")
            if old_val == new_val:
                continue
            try:
                numeric_delta = float(new_val) - float(old_val)
            except (TypeError, ValueError):
                numeric_delta = 0.0
            deltas.append({
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": entity_name,
                "attribute_key": key,
                "attribute_name": after_attr.get("name") or key,
                "old_value": old_val,
                "new_value": new_val,
                "delta": numeric_delta,
                "hidden": bool(after_attr.get("hidden", False)),
                "unit": after_attr.get("unit"),
            })

    pid = str(before_player.get("player_id", "player_1"))
    pname = str(before_player.get("name", "玩家"))
    _diff_entity(before_player, after_player, "player", pid, pname)

    for cid, before_char in before_characters.items():
        after_char = after_characters.get(cid)
        if isinstance(before_char, dict) and isinstance(after_char, dict):
            _diff_entity(before_char, after_char, "character", cid,
                         str(before_char.get("name", cid)))

    return deltas


def apply_natural_attribute_deltas(
    player: dict[str, Any],
    characters: dict[str, dict[str, Any]],
    tick_duration_minutes: float = 5.0,
    defer_post: bool = False,
    deferred: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    """Apply per-minute natural attribute deltas.

    If *defer_post* is True, attributes with ``update_position: "post_narrative"``
    are skipped and their descriptors appended to *deferred* (in-place).
    """
    new_player = deepcopy(player)
    new_characters = deepcopy(characters)
    events: list[str] = []
    deferred = deferred if deferred is not None else []

    def apply_for_entity(entity: dict[str, Any], label: str,
                         entity_type: str, entity_id: str) -> None:
        attrs = _normalize_attributes(entity)
        for key, attr in attrs.items():
            delta = float(attr.get("natural_delta_per_minute") or 0.0) * tick_duration_minutes
            if delta == 0.0:
                continue
            if defer_post and attr.get("update_position") == "post_narrative":
                deferred.append({
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "attribute_key": key,
                })
                continue
            applied = _apply_delta(attr, delta)
            if not applied:
                continue
            new_attr, old, new = applied
            attrs[key] = new_attr
            if old != new:
                events.append(f"[属性] {label}的{_attribute_name(key, attr)}自然变化 {old:g} → {new:g}")
        entity["attributes"] = attrs

    pid = str(player.get("player_id", "player_1"))
    apply_for_entity(new_player, new_player.get("name", "玩家"), "player", pid)
    for cid, char in new_characters.items():
        if isinstance(char, dict):
            apply_for_entity(char, char.get("name", cid), "character", cid)

    return new_player, new_characters, events


# ── Locked-attribute condition evaluator ──

_LC_TOKEN_RE = _re.compile(
    r'\s*(?:(?P<number>\d+(?:\.\d+)?)|(?P<string>"[^"]*")|(?P<name>[A-Za-z_][A-Za-z0-9_]*)|(?P<op>==|<=|>=|!=|[+\-*/<>=(),;\[\]]))'
)
_LC_COMPARATORS = frozenset({"<", ">", "<=", ">=", "==", "!=", "="})


class _LockedConditionError(ValueError):
    pass


@dataclass(frozen=True)
class _LCToken:
    kind: str  # number, string, name, op
    value: str


def _lc_tokenize(expression: str) -> list[_LCToken]:
    tokens: list[_LCToken] = []
    pos = 0
    while pos < len(expression):
        match = _LC_TOKEN_RE.match(expression, pos)
        if not match:
            raise _LockedConditionError(f"无法解析条件表达式片段: {expression[pos:pos+20]!r}")
        pos = match.end()
        if match.lastgroup == "number":
            tokens.append(_LCToken("number", match.group("number")))
        elif match.lastgroup == "string":
            s = match.group("string")
            tokens.append(_LCToken("string", s[1:-1]))
        elif match.lastgroup == "name":
            tokens.append(_LCToken("name", match.group("name")))
        elif match.lastgroup == "op":
            tokens.append(_LCToken("op", match.group("op")))
    return tokens


class _LCParser:
    """Recursive-descent parser for locked-attribute condition expressions.

    Grammar:
      or_expr   = and_expr ("or" and_expr)*
      and_expr  = comp ("and" comp)*
      comp      = arith (COMPARATOR arith
                   | "in" arith
                   | "not" "in" arith
                   | "subset"|"superset"|"intersects"|"disjoint" arith)?
      arith     = term (("+"|"-") term)*
      term      = primary (("*"|"/") primary)*
      primary   = "not" primary | "-" primary | "len" "(" arith ")"
                | NAME "(" arith ")"
                | "(" or_expr ")" | NUMBER | STRING | NAME

    NAME tokens resolve to entity attribute values via _normalize_attributes().
    Special names: "true"→True, "false"→False, "null"→None, "abs"→abs().
    Set keywords: "in", "not in", "subset", "superset", "intersects", "disjoint".
    """

    def __init__(self, tokens: list[_LCToken], attrs: dict[str, dict[str, Any]]):
        self.tokens = tokens
        self.attrs = attrs
        self.pos = 0

    def parse(self) -> bool:
        result = self._parse_or()
        if self._peek() is not None:
            raise _LockedConditionError(f"表达式末尾存在多余内容: {self._peek().value!r}")
        return bool(result)

    def _parse_or(self) -> Any:
        left = self._parse_and()
        while self._match_name("or"):
            right = self._parse_and()
            left = bool(left) or bool(right)
        return left

    def _parse_and(self) -> Any:
        left = self._parse_comp()
        while self._match_name("and"):
            right = self._parse_comp()
            left = bool(left) and bool(right)
        return left

    _SET_KEYWORDS = frozenset({"subset", "superset", "intersects", "disjoint"})

    def _parse_comp(self) -> Any:
        left = self._parse_arith()
        token = self._peek()
        if token is None:
            return left  # truthy single-value

        # Numeric/string comparison: < > <= >= == !=
        if token.kind == "op" and token.value in _LC_COMPARATORS:
            op = self._advance().value
            right = self._parse_arith()
            if op == "<":   return left < right
            if op == ">":   return left > right
            if op == "<=":  return left <= right
            if op == ">=":  return left >= right
            if op in ("=", "=="):  return left == right
            if op == "!=":  return left != right

        # element in list / element not in list
        if token.kind == "name":
            if token.value == "in":
                self._advance()
                right = self._parse_arith()
                if isinstance(right, str):
                    return str(left) in right
                if isinstance(right, (list, tuple, set)):
                    return left in set(right)
                raise _LockedConditionError(
                    f"in 右边必须是列表或字符串，实际类型为 {type(right).__name__}"
                )
            if token.value == "not":
                # Lookahead: "not in" vs unary "not"
                if self._peek(1) and self._peek(1).kind == "name" and self._peek(1).value == "in":
                    self._advance()  # consume "not"
                    self._advance()  # consume "in"
                    right = self._parse_arith()
                    if isinstance(right, str):
                        return str(left) not in right
                    if isinstance(right, (list, tuple, set)):
                        return left not in set(right)
                    raise _LockedConditionError(
                        f"not in 右边必须是列表或字符串，实际类型为 {type(right).__name__}"
                    )
                # unary "not" is handled in _parse_primary; reaching here means
                # "not" follows a value without "in" → truthy fallback
            if token.value in self._SET_KEYWORDS:
                keyword = self._advance().value
                right = self._parse_arith()
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

    def _parse_arith(self) -> Any:
        value = self._parse_term()
        while True:
            if self._match_op("+"):
                value = value + self._parse_term()
            elif self._match_op("-"):
                value = value - self._parse_term()
            else:
                return value

    def _parse_term(self) -> Any:
        value = self._parse_primary()
        while True:
            if self._match_op("*"):
                value = value * self._parse_primary()
            elif self._match_op("/"):
                divisor = self._parse_primary()
                if divisor == 0:
                    raise _LockedConditionError("条件表达式中出现除零")
                value = value / divisor
            else:
                return value

    def _parse_primary(self) -> Any:
        # Boolean NOT (unary prefix). Must be checked first since "not" is a name token,
        # not an op. The "not in" case is already handled in _parse_comp before
        # _parse_primary is called for the RHS, so "not" here is always boolean NOT.
        if self._match_name("not"):
            return not bool(self._parse_primary())

        if self._match_op("-"):
            return -self._parse_primary()

        # Function call: NAME "(" ... ")"
        token = self._peek()
        if token and token.kind == "name":
            next_token = self.tokens[self.pos + 1] if self.pos + 1 < len(self.tokens) else None
            if next_token and next_token.kind == "op" and next_token.value == "(":
                func_name = self._advance().value
                self._consume_op("(")
                if func_name == "rand":
                    if self._match_op(")"):
                        return _random.random()
                    lo = self._parse_arith()
                    self._consume_op(",")
                    hi = self._parse_arith()
                    self._consume_op(")")
                    return _random.uniform(lo, hi)
                if func_name == "randint":
                    lo = int(self._parse_arith())
                    self._consume_op(",")
                    hi = int(self._parse_arith())
                    self._consume_op(")")
                    return _random.randint(lo, hi)
                arg = self._parse_arith()
                self._consume_op(")")
                if func_name == "abs":
                    return abs(arg)
                if func_name == "len":
                    if isinstance(arg, (list, tuple, set, str)):
                        return len(arg)
                    raise _LockedConditionError(
                        f"len() 需要列表或字符串，实际类型为 {type(arg).__name__}"
                    )
                raise _LockedConditionError(f"未知函数 {func_name!r}")

        if self._match_op("("):
            value = self._parse_or()
            self._consume_op(")")
            return value

        token = self._advance()
        if token.kind == "number":
            return float(token.value)
        if token.kind == "string":
            return token.value
        if token.kind == "name":
            return self._resolve_name(token.value)
        raise _LockedConditionError(f"条件表达式中不应出现 {token.value!r}")

    def _resolve_name(self, name: str) -> Any:
        if name == "true":
            return True
        if name == "false":
            return False
        if name == "null":
            return None
        attr = self.attrs.get(name)
        if isinstance(attr, dict):
            return attr.get("value")
        raise _LockedConditionError(f"未知属性 {name!r}")

    def _peek(self, offset: int = 0) -> _LCToken | None:
        idx = self.pos + offset
        return self.tokens[idx] if idx < len(self.tokens) else None

    def _advance(self) -> _LCToken:
        token = self._peek()
        if token is None:
            raise _LockedConditionError("条件表达式意外结束")
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
            raise _LockedConditionError(f"预期 {value!r}，但得到 {found!r}")

    @staticmethod
    def _to_set(value: Any, keyword: str) -> set:
        """Convert value to set for set operations; raise on non-list types."""
        if isinstance(value, (list, tuple, set)):
            return set(value)
        raise _LockedConditionError(
            f"{keyword} 运算需要列表类型，实际类型为 {type(value).__name__}"
        )


# ── Compute expression parser (if(condition, value; ...; default)) ──

class _ComputeEvalError(ValueError):
    pass


class _ComputeParser:
    """Recursive-descent parser for compute if() expressions.

    Grammar:
      if_expr   = "if" "(" (condition "," value ";")* value ")"
      condition = <delegated to _eval_locked_condition, extracted as raw substring>
      value     = "if" "(" ... ")" | arith
      arith     = term (("+"|"-") term)*
      term      = primary (("*"|"/") primary)*
      primary   = "-" primary | NAME "(" arith ("," arith)? ")"
                | "[" (arith ("," arith)*)? "]"
                | "(" arith ")" | NUMBER | STRING | NAME
    """

    _COMPARATORS = frozenset({"<", ">", "=", "<=", ">=", "!="})

    def __init__(self, tokens: list[_LCToken], attrs: dict[str, dict[str, Any]]):
        self.tokens = tokens
        self.attrs = attrs
        self.pos = 0

    def parse(self) -> Any:
        result = self._parse_if()
        if self._peek() is not None:
            raise _ComputeEvalError(f"表达式末尾存在多余内容: {self._peek().value!r}")
        return result

    def _parse_if(self) -> Any:
        name = self._consume_name()
        if name != "if":
            raise _ComputeEvalError("compute 表达式必须以 if(...) 开始")
        self._consume_op("(")

        while True:
            if self._looks_like_condition():
                condition_expr = self._extract_condition()
                matched = _eval_locked_condition(condition_expr, self.attrs)
                self._consume_op(",")
                value = self._parse_value()
                if matched:
                    self._skip_until_if_end()
                    return value
                if self._match_op(";"):
                    continue
                self._consume_op(")")
                raise _ComputeEvalError("if(...) 缺少 else 输出")

            value = self._parse_value()
            self._consume_op(")")
            return value

    # ── Value expression parsing ──

    def _parse_value(self) -> Any:
        token = self._peek()
        if token and token.kind == "name" and token.value == "if":
            return self._parse_if()
        return self._parse_arith()

    def _parse_arith(self) -> Any:
        value = self._parse_term()
        while True:
            if self._match_op("+"):
                value = value + self._parse_term()
            elif self._match_op("-"):
                value = value - self._parse_term()
            else:
                return value

    def _parse_term(self) -> Any:
        value = self._parse_primary()
        while True:
            if self._match_op("*"):
                value = value * self._parse_primary()
            elif self._match_op("/"):
                divisor = self._parse_primary()
                if divisor == 0:
                    raise _ComputeEvalError("条件表达式中出现除零")
                value = value / divisor
            else:
                return value

    def _parse_primary(self) -> Any:
        if self._match_op("-"):
            return -self._parse_primary()

        token = self._peek()
        if token is None:
            raise _ComputeEvalError("表达式意外结束")

        # Function call: NAME "(" ... ")"
        if token.kind == "name":
            next_token = self._peek(1)
            if next_token and next_token.kind == "op" and next_token.value == "(":
                func_name = self._advance().value
                self._consume_op("(")
                if func_name == "rand":
                    if self._match_op(")"):
                        return _random.random()
                    # rand(min, max) — random float in [min, max)
                    lo = self._parse_arith()
                    self._consume_op(",")
                    hi = self._parse_arith()
                    self._consume_op(")")
                    return _random.uniform(lo, hi)
                if func_name == "randint":
                    lo = int(self._parse_arith())
                    self._consume_op(",")
                    hi = int(self._parse_arith())
                    self._consume_op(")")
                    return _random.randint(lo, hi)
                if func_name == "len":
                    arg = self._parse_arith()
                    self._consume_op(")")
                    if isinstance(arg, (list, tuple, set, str)):
                        return len(arg)
                    raise _ComputeEvalError(
                        f"len() 需要列表或字符串，实际类型为 {type(arg).__name__}"
                    )
                # min, max, abs — single arg or two args
                first = self._parse_arith()
                if self._match_op(","):
                    second = self._parse_arith()
                    self._consume_op(")")
                    if func_name == "min":
                        return min(first, second)
                    if func_name == "max":
                        return max(first, second)
                    raise _ComputeEvalError(f"未知函数 {func_name!r}")
                self._consume_op(")")
                if func_name == "abs":
                    return abs(first)
                raise _ComputeEvalError(f"未知函数 {func_name!r}")

        # List literal: "[" ... "]"
        if token.kind == "op" and token.value == "[":
            self._advance()  # consume "["
            items: list[Any] = []
            if not (self._peek() and self._peek().kind == "op" and self._peek().value == "]"):
                items.append(self._parse_arith())
                while self._match_op(","):
                    items.append(self._parse_arith())
            self._consume_op("]")
            return items

        # Parenthesized expression
        if self._match_op("("):
            value = self._parse_arith()
            self._consume_op(")")
            return value

        token = self._advance()
        if token.kind == "number":
            return float(token.value)
        if token.kind == "string":
            return token.value
        if token.kind == "name":
            return self._resolve_name(token.value)
        raise _ComputeEvalError(f"表达式中不应出现 {token.value!r}")

    # ── Condition extraction ──

    def _looks_like_condition(self) -> bool:
        """Heuristic: is current position a condition branch or a default value?"""
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
                    if t.value in self._COMPARATORS:
                        return True
                    if t.value == ",":
                        return True
                    if t.value == ";":
                        return False
            elif t.kind == "name" and depth == 0:
                if t.value in ("and", "or", "not", "in", "contains", "subset",
                               "superset", "intersects", "disjoint"):
                    return True
            i += 1
        return False

    def _extract_condition(self) -> str:
        """Collect tokens from current position to the next ',' or ';' at depth 0,
        skipping nested parentheses and nested if()."""
        depth = 0
        parts: list[str] = []
        while self.pos < len(self.tokens):
            t = self.tokens[self.pos]
            if t.kind == "op":
                if t.value == "(":
                    depth += 1
                elif t.value == ")":
                    if depth == 0:
                        break
                    depth -= 1
                elif depth == 0 and t.value in {",", ";"}:
                    break
            elif t.kind == "name" and t.value == "if" and depth == 0:
                # Nested if() — skip the entire nested expression
                self.pos += 1  # skip "if"
                if self.pos < len(self.tokens) and self.tokens[self.pos].value == "(":
                    self.pos += 1
                    nested_depth = 1
                    while self.pos < len(self.tokens) and nested_depth > 0:
                        nt = self.tokens[self.pos]
                        if nt.kind == "op" and nt.value == "(":
                            nested_depth += 1
                        elif nt.kind == "op" and nt.value == ")":
                            nested_depth -= 1
                        self.pos += 1
                continue
            # Reconstruct the token text
            if t.kind == "string":
                parts.append('"' + t.value + '"')
            else:
                parts.append(t.value)
            self.pos += 1
        return " ".join(parts)

    # ── Variable resolution ──

    def _resolve_name(self, name: str) -> Any:
        if name == "true":
            return True
        if name == "false":
            return False
        if name == "null":
            return None
        attr = self.attrs.get(name)
        if isinstance(attr, dict):
            return attr.get("value")
        raise _ComputeEvalError(f"未知属性 {name!r}")

    # ── Skip to end of if() ──

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

    # ── Token helpers ──

    def _peek(self, offset: int = 0) -> _LCToken | None:
        idx = self.pos + offset
        return self.tokens[idx] if idx < len(self.tokens) else None

    def _advance(self) -> _LCToken:
        token = self._peek()
        if token is None:
            raise _ComputeEvalError("表达式意外结束")
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
            raise _ComputeEvalError(f"预期 {value!r}，但得到 {found!r}")

    def _consume_name(self) -> str:
        token = self._advance()
        if token.kind != "name":
            raise _ComputeEvalError(f"预期名称，但得到 {token.value!r}")
        return token.value


def _eval_compute_expression(expression: str, attrs: dict[str, dict[str, Any]]) -> Any:
    """Evaluate a compute if() expression against entity attributes.

    Returns the computed value (number, string, bool, list, or nested if result).
    Delegates condition sub-expressions to ``_eval_locked_condition``.
    """
    tokens = _lc_tokenize(expression)
    parser = _ComputeParser(tokens, attrs)
    return parser.parse()


def _eval_locked_condition(expression: str, attrs: dict[str, dict[str, Any]]) -> bool:
    """Evaluate a locked-attribute condition expression against entity attributes.

    All identifiers in *expression* resolve to ``attrs[key]["value"]`` (after
    ``_normalize_attributes``).  Special names: ``true``, ``false``, ``null``,
    ``abs``, ``len``, ``not``.

    Supports numeric/string comparisons, arithmetic, boolean logic (and/or/not),
    set operations (in/not in/subset/superset/intersects/disjoint), and len().
    """
    tokens = _lc_tokenize(expression)
    parser = _LCParser(tokens, attrs)
    return parser.parse()


def _crossed_threshold(old: float, new: float, threshold: float) -> bool:
    return old < threshold <= new


# ── Rule-driven deterministic attribute computation ──

def _exec_timer(
    entity: dict[str, Any], attrs: dict[str, dict[str, Any]],
    rule: dict[str, Any], tick_dur: float, label: str,
) -> list[str]:
    """Execute a `timer` rule: accumulate tick_dur when condition is true, else reset."""
    timer_key = str(rule.get("timer_key", ""))
    condition = str(rule.get("condition", ""))
    thresholds: list[float] = [float(t) for t in rule.get("thresholds", []) or []]
    warning_tpl = str(rule.get("warning", ""))

    if timer_key not in attrs or not condition:
        return []

    old_val = float(attrs[timer_key].get("value", 0.0) or 0.0)
    try:
        triggered = _eval_locked_condition(condition, attrs)
    except _LockedConditionError:
        return []

    if triggered:
        new_val = old_val + tick_dur
    else:
        new_val = 0.0

    attrs[timer_key]["value"] = new_val
    entity["attributes"] = attrs

    events: list[str] = []
    for threshold in sorted(thresholds):
        if _crossed_threshold(old_val, new_val, threshold):
            events.append(f"[属性] {label}: {warning_tpl.format(threshold=threshold)}")
    return events


def _exec_stage(
    entity: dict[str, Any], attrs: dict[str, dict[str, Any]],
    rule: dict[str, Any], _tick_dur: float, label: str,
) -> list[str]:
    """Execute a `stage` rule: priority-ordered conditions → monotonic string progression."""
    stage_key = str(rule.get("stage_key", ""))
    stages: list[str] = [str(s) for s in rule.get("stages", []) or []]
    stage_rules: list[dict[str, Any]] = rule.get("rules", []) or []

    if stage_key not in attrs or not stages or not stage_rules:
        return []

    stage_order = {name: idx for idx, name in enumerate(stages)}

    current_stage = attrs[stage_key].get("value")
    current_rank = stage_order.get(current_stage, -1)

    candidate = None
    for sr in stage_rules:
        cond = str(sr.get("condition", ""))
        target = str(sr.get("stage", ""))
        if cond:
            try:
                if _eval_locked_condition(cond, attrs):
                    candidate = target
                    break
            except _LockedConditionError:
                continue
        else:
            # Fallback rule — always matches
            candidate = target
            break

    if candidate is None:
        return []

    candidate_rank = stage_order.get(candidate, -1)
    if candidate_rank < current_rank or candidate == current_stage:
        return []

    attrs[stage_key]["value"] = candidate
    entity["attributes"] = attrs
    return [f"[属性] {label}: {stage_key} {current_stage} → {candidate}"]


def _exec_snapshot(
    entity: dict[str, Any], attrs: dict[str, dict[str, Any]],
    rule: dict[str, Any], _tick_dur: float = 0, _label: str = "",
) -> list[str]:
    """Execute a `snapshot` rule: copy source_key value to snapshot_key."""
    source_key = str(rule.get("source_key", ""))
    snapshot_key = str(rule.get("snapshot_key", ""))

    if source_key not in attrs or not snapshot_key:
        return []

    val = attrs[source_key].get("value")
    if snapshot_key in attrs:
        attrs[snapshot_key]["value"] = val
    else:
        attrs[snapshot_key] = {"name": snapshot_key, "value": val, "hidden": True, "locked": True}
    entity["attributes"] = attrs
    return []


def _exec_list_constraint(
    entity: dict[str, Any], attrs: dict[str, dict[str, Any]],
    rule: dict[str, Any], _tick_dur: float, label: str,
) -> list[str]:
    """Execute a `list_constraint` rule: append value to list if condition holds."""
    list_key = str(rule.get("list_key", ""))
    condition = str(rule.get("condition", ""))
    value = rule.get("value")

    if list_key not in attrs or not condition or value is None:
        return []

    lst = attrs[list_key].get("value")
    if not isinstance(lst, list):
        return []

    try:
        if not _eval_locked_condition(condition, attrs):
            return []
    except _LockedConditionError:
        return []

    if value in lst:
        return []

    lst.append(value)
    attrs[list_key]["value"] = lst
    entity["attributes"] = attrs
    return [f"[属性] {label}: {list_key} 已追加 {value!r}。"]


def _exec_compute(
    entity: dict[str, Any], attrs: dict[str, dict[str, Any]],
    rule: dict[str, Any], _tick_dur: float, label: str,
) -> list[str]:
    """Execute a `compute` rule: evaluate if() expression and assign result."""
    target_key = str(rule.get("target_key", ""))
    expression = str(rule.get("expression", ""))

    if target_key not in attrs or not expression:
        return []

    try:
        result = _eval_compute_expression(expression, attrs)
    except (_ComputeEvalError, _LockedConditionError) as exc:
        return [f"[警告] {label}: compute 表达式求值失败 — {exc}"]

    old_val = attrs[target_key].get("value")
    if old_val == result:
        return []

    attrs[target_key]["value"] = result
    entity["attributes"] = attrs
    return [f"[属性] {label}的{attrs[target_key].get('name', target_key)}: {old_val!r} → {result!r}（compute）"]


_DISPATCH = {
    "timer": _exec_timer,
    "stage": _exec_stage,
    "snapshot": _exec_snapshot,
    "list_constraint": _exec_list_constraint,
    "compute": _exec_compute,
}


def apply_deterministic_attributes(
    player: dict[str, Any],
    characters: dict[str, dict[str, Any]],
    *,
    tick_duration_minutes: float = 1.0,
    rules: list[dict[str, Any]] | None = None,
    defer_post: bool = False,
    deferred: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    """Apply system-calculated updates to locked attributes (bypasses locked check).

    Rules are read from *rules*, a list of dicts each with a ``type`` field.
    Supported types: ``timer``, ``stage``, ``snapshot``, ``list_constraint``, ``compute``.
    Rules execute in declaration order; rules referencing snapshot values must
    appear after the corresponding ``snapshot`` rule.

    If *defer_post* is True, rules with ``update_position: "post_narrative"``
    are skipped and appended to *deferred* (in-place).

    If *rules* is empty or None this function is a no-op.
    """
    rule_list = rules or []
    if not rule_list:
        return player, characters, []

    deferred = deferred if deferred is not None else []
    pre_rules: list[dict[str, Any]] = []
    for rule in rule_list:
        if isinstance(rule, dict) and defer_post and rule.get("update_position") == "post_narrative":
            deferred.append(rule)
        else:
            pre_rules.append(rule)

    if not pre_rules:
        return player, characters, []

    new_player = deepcopy(player)
    new_characters = deepcopy(characters)
    events: list[str] = []

    def _handle_entity(entity: dict[str, Any], label: str) -> None:
        attrs = _normalize_attributes(entity)
        for rule in pre_rules:
            if not isinstance(rule, dict):
                continue
            rule_type = str(rule.get("type", ""))
            executor = _DISPATCH.get(rule_type)
            if executor is None:
                continue
            try:
                new_events = executor(entity, attrs, rule, tick_duration_minutes, label)
            except Exception:
                new_events = []
            events.extend(new_events)

    _handle_entity(new_player, new_player.get("name", "玩家"))
    for cid, char in new_characters.items():
        if isinstance(char, dict):
            _handle_entity(char, char.get("name", cid))

    return new_player, new_characters, events


def apply_attribute_changes(
    player: dict[str, Any],
    characters: dict[str, dict[str, Any]],
    changes: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[str]]:
    new_player = deepcopy(player)
    new_characters = deepcopy(characters)
    events: list[str] = []

    for change in changes:
        entity_type = change.get("entity_type")
        entity_id = str(change.get("entity_id") or "")
        attr_key = str(change.get("attribute_key") or "")
        if not attr_key:
            continue

        if entity_type == "player":
            entity = new_player
            label = new_player.get("name", "玩家")
        elif entity_type == "character" and entity_id in new_characters:
            entity = new_characters[entity_id]
            label = entity.get("name", entity_id)
        else:
            continue

        attrs = _normalize_attributes(entity)
        if attr_key not in attrs:
            events.append(f"[警告] 属性更新忽略了不存在的属性：{entity_id or entity_type}.{attr_key}")
            entity["attributes"] = attrs
            continue

        attr = attrs[attr_key]
        nv = change.get("new_value")
        if nv is not None:
            applied = _apply_new_value(attr, nv)
            if not applied:
                entity["attributes"] = attrs
                continue
            new_attr, old, new = applied
            attrs[attr_key] = new_attr
            entity["attributes"] = attrs
            if old != new:
                reason = str(change.get("reason") or "属性事件")
                events.append(f"[属性] {label}的{_attribute_name(attr_key, attr)}: {old} → {new}（{reason}）")
        else:
            applied = _apply_delta(attr, float(change.get("delta") or 0.0))
            if not applied:
                entity["attributes"] = attrs
                continue
            new_attr, old, new = applied
            attrs[attr_key] = new_attr
            entity["attributes"] = attrs
            if old != new:
                reason = str(change.get("reason") or "属性事件")
                events.append(f"[属性] {label}的{_attribute_name(attr_key, attr)} {old:g} → {new:g}（{reason}）")

    return new_player, new_characters, events


def summarize_attributes_for_prompt(
    player: dict[str, Any],
    characters: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    def summarize_entity(entity: dict[str, Any]) -> dict[str, Any]:
        attrs = _normalize_attributes(entity)
        result = {}
        for key, attr in attrs.items():
            result[key] = {
                "name": attr.get("name") or key,
                "value": attr.get("value", 0.0),
                "min": attr.get("min"),
                "max": attr.get("max"),
                "natural_delta_per_minute": attr.get("natural_delta_per_minute", 0.0),
                "description": attr.get("description", ""),
                "hidden": bool(attr.get("hidden", False)),
            }
        return result

    return {
        "player": {
            "entity_id": str(player.get("player_id", "player_1")),
            "name": player.get("name", "玩家"),
            "attributes": summarize_entity(player),
        },
        "characters": {
            cid: {
                "entity_id": cid,
                "name": char.get("name", cid),
                "attributes": summarize_entity(char),
            }
            for cid, char in characters.items()
            if isinstance(char, dict)
        },
    }


def visible_player_attributes(player: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        key: attr
        for key, attr in _normalize_attributes(player).items()
        if not attr.get("hidden")
    }
