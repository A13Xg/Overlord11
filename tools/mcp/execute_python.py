
import json
import subprocess
from typing import Any, Dict, List

from ._common import fail, ok
from .app import mcp


@mcp.tool(
    name="execute_python",
    description="Execute Python code and return stdout/stderr/return_value/timed_out in `data`. Use this for controlled Python evaluation rather than shell command execution.",
)
def execute_python(
    code: str,
    packages: List[str] = [],
    timeout_seconds: int = 30,
    capture_return: bool = True,
) -> Dict[str, Any]:
    """Execute Python source code.

    Args:
        code: Python source code to execute.
        packages: Pip packages to install before execution.
        timeout_seconds: Max execution time in seconds.
        capture_return: Whether to capture the value of the final expression.
    """
    try:
        for package in packages:
            install = subprocess.run(
                ["python", "-m", "pip", "install", package],
                capture_output=True,
                text=True,
            )
            if install.returncode != 0:
                return fail(
                    f"Failed to install package '{package}': {install.stderr.strip()}"
                )

        runner = f"""
import ast, contextlib, io, json
ns = {{}}
stdout_buffer = io.StringIO()
stderr_buffer = io.StringIO()
return_value = None
source = {code!r}
capture_return = {capture_return!r}
tree = ast.parse(source, mode='exec')
body = tree.body
last_expr = None
if capture_return and body and isinstance(body[-1], ast.Expr):
    last_expr = ast.Expression(body.pop().value)
main = ast.Module(body=body, type_ignores=[])
with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
    exec(compile(main, '<execute_python>', 'exec'), ns, ns)
    if last_expr is not None:
        return_value = eval(compile(last_expr, '<execute_python_last>', 'eval'), ns, ns)
print(json.dumps({{'stdout': stdout_buffer.getvalue(), 'stderr': stderr_buffer.getvalue(), 'return_value': return_value}}, default=str))
"""
        try:
            proc = subprocess.run(
                ["python", "-c", runner],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return ok(
                {
                    "stdout": "",
                    "stderr": "Execution timed out.",
                    "return_value": None,
                    "timed_out": True,
                }
            )

        if proc.returncode != 0:
            return fail(f"Python execution failed: {proc.stderr.strip()}")
        payload: Dict[str, Any] = json.loads(proc.stdout.strip() or "{}")
        return ok(
            {
                "stdout": payload.get("stdout", ""),
                "stderr": payload.get("stderr", ""),
                "return_value": payload.get("return_value"),
                "timed_out": False,
            }
        )
    except Exception as exc:
        return fail(f"Failed to execute python code: {exc}")

