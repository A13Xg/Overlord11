"""
Delegation contract shim.

The runtime intercepts this tool in engine/runner.py and executes real
sub-agent delegation. This module exists for contract discoverability.
"""


def main(
    agent_id: str,
    task: str,
    inputs,
    expected_outputs,
    allow_parallel: bool = False,
    timeout_s: int = 300,
    retry_policy=None,
    step_id: str = "",
    depends_on=None,
):
    return {
        "status": "error",
        "message": "delegate_task is handled by the runner and should not be called directly",
        "agent_id": agent_id,
        "task": task,
        "inputs": inputs,
        "expected_outputs": expected_outputs,
        "allow_parallel": bool(allow_parallel),
        "timeout_s": int(timeout_s),
        "retry_policy": retry_policy,
        "step_id": step_id,
        "depends_on": depends_on or [],
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Delegation contract shim")
    parser.add_argument("--agent_id", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--expected_outputs", required=True)
    parser.add_argument("--allow_parallel", action="store_true")
    parser.add_argument("--timeout_s", type=int, default=300)
    parser.add_argument("--retry_policy", default="")
    parser.add_argument("--step_id", default="")
    parser.add_argument("--depends_on", default="[]")
    args = parser.parse_args()
    out = main(
        agent_id=args.agent_id,
        task=args.task,
        inputs=args.inputs,
        expected_outputs=args.expected_outputs,
        allow_parallel=args.allow_parallel,
        timeout_s=args.timeout_s,
        retry_policy=args.retry_policy,
        step_id=args.step_id,
        depends_on=args.depends_on,
    )
    print(json.dumps(out, ensure_ascii=False))
