"""Bounded arithmetic evaluation for the fast local math path."""

from __future__ import annotations

import ast
import operator
import re
from decimal import Decimal, InvalidOperation, localcontext

_PREFIX = re.compile(
    r"^(?:(?:please\s+)?(?:what\s+is|what's|calculate|compute|evaluate)\s+)",
    re.IGNORECASE,
)
_ALLOWED_CHARACTERS = re.compile(r"^[0-9.+\-*/()\s]+$")
_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_MAX_EXPRESSION_LENGTH = 160
_MAX_AST_NODES = 64
_MAX_ABSOLUTE_VALUE = Decimal("1e18")
_MAX_EXPONENT = 12


class CalculationError(ValueError):
    """A calculation is invalid or exceeds safe limits."""


def extract_arithmetic(query: str) -> str | None:
    """Return a simple arithmetic expression, if the full query contains one."""
    candidate = query.strip().removesuffix("?").strip()
    candidate = _PREFIX.sub("", candidate, count=1)
    candidate = candidate.replace("×", "*").replace("÷", "/")
    candidate = candidate.replace("−", "-").replace("^", "**")
    if not candidate or len(candidate) > _MAX_EXPRESSION_LENGTH:
        return None
    if not _ALLOWED_CHARACTERS.fullmatch(candidate):
        return None
    # A plain number is better treated as a general question.
    if not any(symbol in candidate for symbol in "+-*/"):
        return None
    try:
        tree = ast.parse(candidate, mode="eval")
    except (SyntaxError, ValueError):
        return None
    if sum(1 for _ in ast.walk(tree)) > _MAX_AST_NODES:
        return None
    return candidate


def calculate(query: str) -> str:
    """Evaluate only approved arithmetic nodes, with resource bounds."""
    expression = extract_arithmetic(query)
    if expression is None:
        raise CalculationError("This is not a supported arithmetic expression.")
    try:
        tree = ast.parse(expression, mode="eval")
        with localcontext() as context:
            context.prec = 28
            answer = _evaluate(tree.body, depth=0)
    except (InvalidOperation, OverflowError, RecursionError) as exc:
        raise CalculationError("The calculation exceeds safe limits.") from exc
    if not answer.is_finite() or abs(answer) > _MAX_ABSOLUTE_VALUE:
        raise CalculationError("The calculation exceeds safe limits.")
    rendered = format(answer.normalize(), "f")
    return "0" if rendered == "-0" else rendered


def _evaluate(node: ast.AST, depth: int) -> Decimal:
    if depth > 20:
        raise CalculationError("The calculation is too deeply nested.")
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        value = Decimal(str(node.value))
        if not value.is_finite() or abs(value) > _MAX_ABSOLUTE_VALUE:
            raise CalculationError("The calculation exceeds safe limits.")
        return value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _bounded(_UNARY_OPERATORS[type(node.op)](_evaluate(node.operand, depth + 1)))
    if isinstance(node, ast.BinOp):
        left = _evaluate(node.left, depth + 1)
        right = _evaluate(node.right, depth + 1)
        if isinstance(node.op, ast.Pow):
            if right != right.to_integral_value() or abs(right) > _MAX_EXPONENT:
                raise CalculationError("The exponent exceeds safe limits.")
            try:
                return _bounded(left ** int(right))
            except (InvalidOperation, ZeroDivisionError) as exc:
                raise CalculationError("The calculation is undefined.") from exc
        operation = _BINARY_OPERATORS.get(type(node.op))
        if operation is not None:
            if isinstance(node.op, ast.Div) and right == 0:
                raise CalculationError("Division by zero is undefined.")
            return _bounded(operation(left, right))
    raise CalculationError("Only basic arithmetic is supported.")


def _bounded(value: Decimal) -> Decimal:
    if not value.is_finite() or abs(value) > _MAX_ABSOLUTE_VALUE:
        raise CalculationError("The calculation exceeds safe limits.")
    return value
