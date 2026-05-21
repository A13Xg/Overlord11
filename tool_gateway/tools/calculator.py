"""
Calculator tool — safe arithmetic/expression evaluator using Python's `ast` module.
No eval() is used; only numeric operations are permitted.
"""
from __future__ import annotations

import ast
import math
import operator
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseTool

# ---------------------------------------------------------------------------
# Safe AST evaluator
# ---------------------------------------------------------------------------

_SAFE_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_SAFE_FUNCS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "ceil": math.ceil,
    "floor": math.floor,
    "exp": math.exp,
    "factorial": math.factorial,
    "gcd": math.gcd,
    "hypot": math.hypot,
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "inf": math.inf,
}


def _safe_eval(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")
    if isinstance(node, ast.Name):
        if node.id in _SAFE_FUNCS:
            val = _SAFE_FUNCS[node.id]
            if isinstance(val, (int, float)):
                return val
        raise ValueError(f"Unknown name: '{node.id}'")
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        return _SAFE_OPS[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        return _SAFE_OPS[op_type](_safe_eval(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only simple function calls are allowed")
        fname = node.func.id
        if fname not in _SAFE_FUNCS or not callable(_SAFE_FUNCS[fname]):
            raise ValueError(f"Unknown or non-callable function: '{fname}'")
        args = [_safe_eval(a) for a in node.args]
        if node.keywords:
            raise ValueError("Keyword arguments not supported in expressions")
        return _SAFE_FUNCS[fname](*args)
    raise ValueError(f"Unsupported AST node type: {type(node).__name__}")


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class CalculatorInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)

    expression: str = Field(..., description="Arithmetic expression to evaluate, e.g. '2 + 2', 'sqrt(16) * pi'")
    precision: int = Field(6, ge=0, le=15, description="Decimal places to round the result to")
    scientific_notation: bool = Field(False, description="Format result in scientific notation")


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class CalculatorTool(BaseTool):
    name = "calculator"
    description = (
        "Safely evaluate arithmetic and mathematical expressions. "
        "Supports standard operators (+, -, *, /, **, %, //), "
        "common math functions (sqrt, sin, cos, log, etc.), and constants (pi, e, tau)."
    )
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    input_model = CalculatorInput
    examples = [
        {"tool_name": "calculator", "arguments": {"expression": "2 + 2"}},
        {"tool_name": "calculator", "arguments": {"expression": "sqrt(144) * pi", "precision": 4}},
        {"tool_name": "calculator", "arguments": {"expression": "2 ** 32", "scientific_notation": True}},
    ]

    def execute(self, args: CalculatorInput) -> dict[str, Any]:
        expr = args.expression.strip()
        if not expr:
            raise ValueError("Expression must not be empty")

        try:
            tree = ast.parse(expr, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"Invalid expression syntax: {exc}") from exc

        try:
            raw_result = _safe_eval(tree)
        except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
            raise ValueError(str(exc)) from exc

        # Determine type label
        if isinstance(raw_result, float) and raw_result == int(raw_result) and not math.isinf(raw_result):
            result_type = "integer-valued float"
        elif isinstance(raw_result, int):
            result_type = "integer"
        else:
            result_type = "float"

        rounded = round(float(raw_result), args.precision) if not math.isinf(raw_result) and not math.isnan(raw_result) else raw_result

        if args.scientific_notation:
            formatted = f"{rounded:.{args.precision}e}"
        else:
            # Strip trailing zeros for cleaner output
            formatted = f"{rounded:.{args.precision}f}".rstrip("0").rstrip(".")

        return {
            "expression": expr,
            "result": rounded,
            "formatted_result": formatted,
            "type": result_type,
            "precision": args.precision,
        }
