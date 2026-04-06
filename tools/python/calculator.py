"""
Overlord11 - Calculator Tool
================================
Evaluate mathematical expressions safely. Supports arithmetic, algebra,
trigonometry, statistics, and variable substitution.

Usage:
    python calculator.py --expression "sqrt(144)"
    python calculator.py --expression "mean([1,2,3,4,5])" --precision 4
    python calculator.py --expression "x ** 2 + y" --variables '{"x": 3, "y": 7}'
"""

import json
import math
import statistics
import sys
from typing import Dict, Optional


# Restricted namespace for safe eval
_SAFE_NS: dict = {
    "__builtins__": {},
    # Constants
    "pi": math.pi,
    "e": math.e,
    "inf": math.inf,
    "nan": math.nan,
    # Math functions
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "pow": math.pow,
    "sqrt": math.sqrt,
    "cbrt": lambda x: math.copysign(abs(x) ** (1 / 3), x),
    "exp": math.exp,
    "log": math.log,
    "log2": math.log2,
    "log10": math.log10,
    "floor": math.floor,
    "ceil": math.ceil,
    "factorial": math.factorial,
    "gcd": math.gcd,
    # Trig (radians)
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "degrees": math.degrees,
    "radians": math.radians,
    # Hyperbolic
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    # Statistics (accepts list)
    "mean": statistics.mean,
    "median": statistics.median,
    "mode": statistics.mode,
    "std": statistics.stdev,
    "variance": statistics.variance,
}


def calculator(
    expression: str,
    precision: int = 6,
    variables: Optional[Dict[str, float]] = None,
) -> dict:
    """
    Evaluate a mathematical expression and return the result.

    Args:
        expression: The mathematical expression to evaluate.
                    Examples: '2 + 2', 'sqrt(144)', 'mean([1, 2, 3])',
                    '(100 * 1.08) ** 3', 'log(1000, 10)', 'sin(radians(30))'.
        precision:  Number of decimal places in the result. Defaults to 6.
        variables:  Optional variable bindings used in the expression
                    (e.g., {"x": 5, "y": 10}).

    Returns:
        dict with keys:
            expression  – the original expression
            result      – the computed value (rounded to precision)
            raw         – the unrounded result
            status      – "success" or "error"
            error       – error message if status is "error"
    """
    ns = dict(_SAFE_NS)
    if variables:
        for k, v in variables.items():
            if not isinstance(k, str) or not k.isidentifier():
                return {
                    "expression": expression,
                    "status": "error",
                    "error": f"Invalid variable name: {k!r}",
                }
            ns[k] = float(v)

    try:
        raw = eval(expression, ns)  # noqa: S307
    except ZeroDivisionError:
        return {"expression": expression, "status": "error", "error": "Division by zero."}
    except Exception as exc:
        return {"expression": expression, "status": "error", "error": str(exc)}

    if isinstance(raw, (int, float)):
        result = round(float(raw), precision)
    elif isinstance(raw, complex):
        return {
            "expression": expression,
            "status": "error",
            "error": "Result is complex; only real numbers are supported.",
        }
    else:
        result = raw  # e.g. list returned by a stats function used oddly

    return {
        "expression": expression,
        "result": result,
        "raw": float(raw) if isinstance(raw, (int, float)) else raw,
        "precision": precision,
        "status": "success",
    }


def main():
    import argparse
    import io

    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Overlord11 Calculator Tool")
    parser.add_argument("--expression", required=True, help="Mathematical expression to evaluate")
    parser.add_argument("--precision", type=int, default=6, help="Decimal places (default 6)")
    parser.add_argument("--variables", default="{}", help='JSON object of variable bindings, e.g. \'{"x": 5}\'')

    args = parser.parse_args()

    try:
        variables = json.loads(args.variables) if args.variables.strip() != "{}" else None
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "error": f"Invalid --variables JSON: {exc}"}))
        sys.exit(1)

    result = calculator(
        expression=args.expression,
        precision=args.precision,
        variables=variables,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
