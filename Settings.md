# Settings

> AI behavior configuration for this project. Human+AI readable.
> Format: `option = value` with allowed values listed.
> Agents: read this file at session start and respect all settings.

---

## Agent Behavior

```ini
# --- Thinking & Reasoning ---
# How deeply the AI should analyze before acting
thinking_depth = moderate
# Allowed: minimal | moderate | thorough | exhaustive

# How verbose AI responses should be after completing tasks
response_verbosity = concise
# Allowed: minimal | concise | detailed | comprehensive

# Whether to explain reasoning or just show results
show_reasoning = true
# Allowed: true | false

# --- Verification & Testing ---
# How much effort to spend verifying and testing work
verification_level = standard
# Allowed: skip | quick | standard | thorough | exhaustive

# Run tests automatically after code changes
auto_run_tests = true
# Allowed: true | false

# Run static analysis (code_analyzer) after code changes
auto_static_analysis = true
# Allowed: true | false

# --- Error Handling ---
# What to do when a task fails
error_response = try_fix_then_ask
# Allowed: try_fix_self | try_fix_then_ask | suggest_and_wait | halt_and_wait | error_workflow

# Maximum retry attempts before escalating
max_retry_loops = 3
# Allowed: 1-10 (integer)

# When error_response = error_workflow, run this sequence:
# 1. Log to ErrorLog.md
# 2. Analyze error and generate ranked solutions
# 3. Attempt solutions in order (up to max_retry_loops)
# 4. If all fail, halt and report to human
error_workflow_enabled = true
# Allowed: true | false

# --- Task Management ---
# Automatically update TaskingLog.md when starting/completing tasks
auto_update_tasking_log = true
# Allowed: true | false

# Automatically update AInotes.md with significant findings
auto_update_ai_notes = true
# Allowed: true | false

# Check TaskingLog.md before starting work to avoid duplicates
check_for_duplicates = true
# Allowed: true | false

# --- Code Style ---
# Add docstrings to new functions/classes
require_docstrings = true
# Allowed: true | false

# Add type hints to function signatures (Python)
require_type_hints = true
# Allowed: true | false

# Maximum function complexity (cyclomatic) before suggesting refactor
max_function_complexity = 10
# Allowed: 5-25 (integer)

# --- Safety ---
# Run cleanup_tool scan before any deployment/push
pre_deploy_scan = true
# Allowed: true | false

# Block commits containing detected secrets
block_secrets_in_commits = true
# Allowed: true | false

# --- Output ---
# Default output tier (can be overridden per task)
default_output_tier = 1
# Allowed: 0 | 1 | 2

# Where to save generated output files
output_dir = output/
# Allowed: any valid relative path
```

---

## Project-Specific Overrides

> Add any project-specific setting overrides below.
> These take precedence over the defaults above.

```ini
# (add overrides here)
```

---

*Last updated: 2026-04-06 18:59*
