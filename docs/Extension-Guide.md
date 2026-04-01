# Extension Guide

How to add new agents, tools, and LLM providers to Overlord11 without breaking existing functionality.

---

## Adding a New Agent

### Step 1 — Create the Agent System Prompt

Create `agents/my_agent.md` using the standard template:

```markdown
# My Agent (OVR_XXX_09)

## Identity
[One paragraph describing the agent's role and purpose]

## Primary Responsibilities
1. [Primary task]
2. [Secondary task]
...

## When to Invoke
- [Condition 1]
- [Condition 2]

## Workflow
1. **Step Name** — description
2. **Step Name** — description
...

## Output Format
[Describe what this agent produces]

## Quality Checklist
- [ ] Criterion 1
- [ ] Criterion 2
...
```

### Step 2 — Register in `config.json`

Add the agent entry under `"agents"`:

```json
"my_agent": {
  "id": "OVR_XXX_09",
  "name": "My Agent",
  "file": "agents/my_agent.md",
  "description": "One-line description of what this agent does",
  "entry_point": false,
  "tools": ["read_file", "write_file", "run_shell_command"]
}
```

Choose an ID in the format `OVR_XXX_NN` where `NN` is the next available number (currently 9+).

### Step 3 — Update the Orchestrator

Edit `agents/orchestrator.md` to add the new agent to the Delegation Patterns section and update its `can_delegate_to` list in `config.json`:

```json
"orchestrator": {
  "can_delegate_to": ["researcher", "coder", "analyst", "writer", "reviewer", "publisher", "my_agent"]
}
```

Also add a delegation pattern in the Orchestrator's agent file so it knows when to invoke your agent.

### Step 4 — Add to Consciousness.md Agent Registry

Add a row to the Agent Registry table in `Consciousness.md`:

```markdown
| OVR_XXX_09 | My Agent | Brief role description | `agents/my_agent.md` | Available |
```

### Step 5 — Update Documentation

Add your agent to:
- `docs/Agents-Reference.md` — full identity, workflow, and quality checklist
- `README.md` agents table — one-line summary row

---

## Adding a New Tool

### Step 1 — Create the JSON Schema

Create `tools/defs/my_tool.json`:

```json
{
  "name": "my_tool",
  "description": "One-sentence description of what this tool does and when to use it.",
  "parameters": {
    "type": "object",
    "properties": {
      "required_param": {
        "type": "string",
        "description": "Description of this required parameter."
      },
      "optional_param": {
        "type": "integer",
        "description": "Description of this optional parameter.",
        "default": 10
      }
    },
    "required": ["required_param"]
  }
}
```

**JSON Schema best practices:**
- Use descriptive `description` fields — these are what agents read to understand parameters
- Mark only truly required parameters in `required`
- Provide sensible `default` values for optional parameters
- Use `enum` arrays for parameters with a fixed set of valid values

### Step 2 — Implement in Python

Create `tools/python/my_tool.py`:

```python
"""
Overlord11 - My Tool
====================
Brief description of what this tool does.

Usage:
    python my_tool.py --required_param value
    python my_tool.py --required_param value --optional_param 20
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from log_manager import log_tool_invocation, log_error


def my_tool(required_param: str, optional_param: int = 10) -> dict:
    """
    Main implementation function.

    Args:
        required_param: Description
        optional_param: Description (default: 10)

    Returns:
        dict with keys: 'result', 'status', and optionally 'error'
    """
    try:
        # Your implementation here
        result = f"Processed: {required_param} with {optional_param}"
        return {"status": "success", "result": result}
    except Exception as e:
        log_error("system", "my_tool", str(e))
        return {"status": "error", "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Overlord11 - My Tool")
    parser.add_argument("--required_param", required=True, help="Required parameter")
    parser.add_argument("--optional_param", type=int, default=10, help="Optional parameter")
    args = parser.parse_args()

    start = time.time()
    result = my_tool(args.required_param, args.optional_param)
    duration_ms = (time.time() - start) * 1000

    log_tool_invocation(
        session_id="system",
        tool_name="my_tool",
        params={"required_param": args.required_param},
        result={"status": result.get("status")},
        duration_ms=duration_ms
    )

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

**Implementation best practices:**
- Import `log_manager` for consistent logging
- Return a dict with `"status": "success"` or `"status": "error"`
- Catch all exceptions and return error dicts rather than raising
- Include a `main()` with an argparse CLI for direct invocation
- Add a module docstring with usage examples

### Step 3 — Register in `config.json`

Add to the `"tools"` section:

```json
"my_tool": {
  "def": "tools/defs/my_tool.json",
  "impl": "tools/python/my_tool.py"
}
```

### Step 4 — Add to Agent Tool Lists

Update the `"tools"` array for any agents that should have access:

```json
"coder": {
  "tools": ["read_file", "write_file", "my_tool", ...]
}
```

Also update the corresponding agent `.md` file to include the tool in its workflow.

### Step 5 — Write Tests

Add a test group to `tests/test.py` following the existing pattern:

```python
run_tests("my_tool", [
    {
        "name": "Basic usage",
        "fn": lambda: my_tool_mod.my_tool("hello"),
        "check": lambda r: r.get("status") == "success",
        "expect": "Returns success",
    },
    {
        "name": "Error handling",
        "fn": lambda: my_tool_mod.my_tool(""),
        "check": lambda r: "error" in r or r.get("status") == "error",
        "expect": "Handles empty input gracefully",
    },
])
```

### Step 6 — Update Documentation

Add your tool to:
- `docs/Tools-Reference.md` — full parameter table and CLI examples
- `README.md` tools table — one-line summary row

---

## Adding a New LLM Provider

### Step 1 — Add to `config.json`

```json
"providers": {
  "my_provider": {
    "model": "my-default-model",
    "available_models": {
      "my-default-model": "Most capable model",
      "my-fast-model": "Faster, cheaper model"
    },
    "api_key_env": "MY_PROVIDER_API_KEY",
    "max_tokens": 8192,
    "temperature": 0.7,
    "top_p": 1.0,
    "api_base": "https://api.myprovider.com/v1"
  }
}
```

### Step 2 — Add the API Key Variable

Add to `.env.example`:

```bash
# My Provider API Key
# Get your key from: https://myprovider.com/api-keys
MY_PROVIDER_API_KEY=your_key_here
```

### Step 3 — Implement the Provider Adapter

In your LLM runner (the code that actually calls the API), add a case for the new provider:

```python
def call_llm(provider: str, model: str, system: str, messages: list, max_tokens: int) -> str:
    if provider == "anthropic":
        # ... existing Anthropic code ...
    elif provider == "gemini":
        # ... existing Gemini code ...
    elif provider == "openai":
        # ... existing OpenAI code ...
    elif provider == "my_provider":
        # Implement your provider's API call here
        response = my_provider_client.chat(
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens
        )
        return response.text
    else:
        raise ValueError(f"Unknown provider: {provider}")
```

### Step 4 — Update Fallback Order

Add the new provider to the fallback chain in `config.json` if desired:

```json
"orchestration": {
  "fallback_provider_order": ["gemini", "openai", "anthropic", "my_provider"]
}
```

### Step 5 — Update Documentation

Add your provider to:
- `docs/Providers.md` — model table, API key instructions, provider notes
- `README.md` provider configuration section

---

## Versioning

When making changes, update the `version` field in `config.json` following [semantic versioning](https://semver.org/):

- **Patch** (x.x.1): Bug fixes, documentation updates, minor config changes
- **Minor** (x.1.0): New tools, new agents, new provider support
- **Major** (2.0.0): Breaking changes to agent interfaces, config structure, or tool schemas
