# Overlord11 Chat-Based Agent Orchestration

## Quick Start

To begin a session, instruct Claude to:
> "Read `Overlord11_Onboarding.md` and assume the Orchestrator role. I want to [describe your task]."

---

## System Overview

**Overlord11/Code-ProjectGen** is a multi-agent code generation system. The programmatic version (`python/run.py`) uses API keys to automate the workflow. This document describes how to run the same system **interactively through Claude Code chat** without API keys.

### Key Difference: Programmatic vs Chat Mode

| Aspect | Programmatic (`run.py`) | Chat Mode (This) |
|--------|-------------------------|------------------|
| Execution | Automated API calls | Interactive conversation |
| Agent Switching | Internal tool use | Claude spawns Task agents with injected prompts |
| Workspace | Session-based sandbox | User-specified directory |
| Tools | Custom JSON tool definitions | Claude Code native tools (Bash, Read, Write, Edit, etc.) |
| Feedback Loop | Automated retries | Human-in-the-loop decisions |

---

## Agent Inventory

Located in `/agents/` directory:

| Agent | ID | Role | Prompt File |
|-------|-----|------|-------------|
| **Orchestrator** | CG_DIR_01 | Lead coordinator, workflow management | `orchestrator.md` |
| **Architect** | CG_ARC_02 | Design project structure, patterns, dependencies | `architect.md` |
| **Coder** | CG_COD_03 | Write clean, documented, production-ready code | `coder.md` |
| **Tester** | CG_TST_04 | Create test suites, validate functionality | `tester.md` |
| **Reviewer** | CG_REV_05 | Quality assessment, issue identification, approval | `reviewer.md` |

---

## Workflow Phases

The generation pipeline follows: **PLAN → ARCHITECT → IMPLEMENT → TEST → REVIEW**

```
┌─────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                              │
│                     (Coordinates All)                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────┐   ┌───────────┐   ┌──────────┐   ┌──────────┐   │
│   │   PLAN   │ → │ ARCHITECT │ → │ IMPLEMENT│ → │   TEST   │   │
│   │          │   │           │   │          │   │          │   │
│   │ Analyze  │   │  Design   │   │  Write   │   │  Create  │   │
│   │ request  │   │ structure │   │  code    │   │  tests   │   │
│   └──────────┘   └───────────┘   └──────────┘   └──────────┘   │
│                                                       │          │
│                                                       ▼          │
│                                              ┌──────────┐        │
│                                              │  REVIEW  │        │
│                                              │          │        │
│                                              │ Validate │        │
│                                              │ quality  │        │
│                                              └──────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

---

## How to Spawn Sub-Agents

When the Orchestrator needs specialized work, spawn a Task agent with the agent's markdown file injected as a system prompt.

### Pattern for Spawning

```
Task(
  subagent_type: "general-purpose",
  prompt: """
  [INJECT: Contents of agents/<agent>.md]

  CONTEXT FROM ORCHESTRATOR:
  - Project: [description]
  - Language: [language]
  - Template: [template]
  - Current Phase: [phase]
  - Workspace: [path]

  TASK:
  [Specific instructions for this agent]

  DELIVERABLES:
  [Expected outputs]
  """
)
```

### Example: Spawning the Architect Agent

```
Task(
  subagent_type: "general-purpose",
  prompt: """
  # Software Architect Agent (CG_ARC_02)
  [... full contents of architect.md ...]

  CONTEXT:
  - Project: REST API for user management
  - Language: Python
  - Template: python_api
  - Workspace: C:\Projects\user-api

  TASK:
  Design the complete project structure for a FastAPI user management API with:
  - User CRUD operations
  - JWT authentication
  - PostgreSQL database

  DELIVERABLES:
  1. Directory structure tree
  2. File manifest with descriptions
  3. Dependency list (requirements.txt contents)
  4. Component relationship diagram
  """
)
```

---

## Available Tools (Chat Mode)

In chat mode, use Claude Code's native tools instead of the JSON tool definitions:

| Programmatic Tool | Chat Mode Equivalent |
|-------------------|---------------------|
| `file_management` (read/write/list) | `Read`, `Write`, `Edit`, `Glob` |
| `code_execution` (run_python/shell) | `Bash` |
| `project_scaffold` | `Write` + `Bash` (mkdir) |
| `code_analysis` | `Grep`, `Read` + analysis |
| `dependency_management` | `Bash` (pip, npm) |

---

## Configuration Reference

From `config.json`:

### Supported Languages
- **Primary**: Python, JavaScript, TypeScript, Go, Rust, Java, C#
- **Scripting**: Bash, PowerShell
- **Markup**: HTML, CSS, Markdown, JSON, YAML, XML

### Project Templates
| Template | Description |
|----------|-------------|
| `python_cli` | Command-line application with argparse |
| `python_api` | FastAPI REST API service |
| `python_package` | Installable Python package |
| `node_api` | Express.js REST API |
| `react_app` | React frontend application |
| `fullstack` | Backend + frontend + Docker |

### Quality Standards
- Minimum quality score: 7/10
- Type hints required
- Docstrings required
- Error handling required
- Max function length: 50 lines
- Max file length: 500 lines

---

## Session Workflow

### 1. User Initiates Request
```
User: "Create a Python CLI tool for managing TODO lists with SQLite storage"
```

### 2. Orchestrator Activates (PLAN Phase)
- Parse request for language, template, features
- Identify scope and deliverables
- Create generation plan

### 3. Spawn Architect Agent (ARCHITECT Phase)
```
[Orchestrator spawns Task with architect.md injected]
→ Returns: Directory structure, file manifest, dependencies
```

### 4. Spawn Coder Agent (IMPLEMENT Phase)
```
[Orchestrator spawns Task with coder.md injected + architect output]
→ Returns: Complete code files
```

### 5. Spawn Tester Agent (TEST Phase)
```
[Orchestrator spawns Task with tester.md injected + code files]
→ Returns: Test files, execution results
```

### 6. Spawn Reviewer Agent (REVIEW Phase)
```
[Orchestrator spawns Task with reviewer.md injected + all outputs]
→ Returns: Quality report, approval status
```

### 7. Deliver Final Output
- Write all files to workspace
- Provide summary documentation
- Report any issues or recommendations

---

## Decision Framework

### Proceed When:
- Phase deliverables meet quality standards
- No blocking issues identified
- User requirements satisfied

### Iterate When:
- Quality score below 7/10
- Missing required components
- Test failures detected
- Code standards violations

### Ask User When:
- Requirements are ambiguous
- Multiple valid approaches exist
- Technical constraints need decisions

---

## Command Reference

### Starting a Session
```
"Assume Orchestrator role from /agents/orchestrator.md and help me build [project description]"
```

### Specifying Workspace
```
"Use workspace: C:\Projects\my-project"
```

### Requesting Specific Template
```
"Use the python_api template"
```

### Adding Features
```
"Include: authentication, database integration, logging, Docker support"
```

### Quality Control
```
"Ensure all code passes review with score >= 8"
```

---

## Error Handling

| Situation | Orchestrator Action |
|-----------|---------------------|
| Ambiguous requirements | Ask user for clarification |
| Generation errors | Try alternative approaches |
| Test failures | Route back to Coder for fixes |
| Quality issues < 7 | Route to Reviewer for improvements |
| Loop limit (15) reached | Deliver partial output with status |

---

## Files Reference

```
Code-ProjectGen/
├── Overlord11_Onboarding.md    ← This file (chat onboarding)
├── config.json                  ← System configuration
├── SETUP.md                     ← Programmatic setup guide
├── agents/
│   ├── orchestrator.md          ← Lead coordinator
│   ├── architect.md             ← Structure designer
│   ├── coder.md                 ← Code writer
│   ├── tester.md                ← Test creator
│   └── reviewer.md              ← Quality assessor
├── tools/                       ← JSON tool definitions (for run.py)
│   ├── file_tool.json
│   ├── code_execution_tool.json
│   ├── project_scaffold_tool.json
│   ├── code_analysis_tool.json
│   └── dependency_tool.json
├── python/
│   ├── run.py                   ← Programmatic runner
│   └── requirements.txt
├── workspace/                   ← Default output location
└── output/                      ← Session summaries
```

---

## Example Full Session

### User Request:
> "Create a Python CLI calculator with add, subtract, multiply, divide operations. Include tests."

### Orchestrator Response:

**PLAN Phase Analysis:**
- Language: Python
- Template: python_cli
- Features: arithmetic operations, CLI interface, tests
- Workspace: workspace/session_[timestamp]/

**Spawning Architect...**
[Task agent returns structure design]

**Spawning Coder...**
[Task agent returns implementation]

**Spawning Tester...**
[Task agent returns test suite]

**Spawning Reviewer...**
[Task agent returns quality assessment: 8.5/10, APPROVED]

**Final Delivery:**
- 4 files created
- All tests passing
- Documentation complete
- Ready for use

---

## Tips for Effective Use

1. **Be Specific**: Clear requirements lead to better outputs
2. **Specify Workspace**: Tell the orchestrator where to write files
3. **Review Incrementally**: Check each phase output before proceeding
4. **Use Templates**: Leverage pre-defined structures when applicable
5. **Request Iteration**: Ask for improvements if quality is insufficient

---

## Version

- System: Code-ProjectGen v1.0.0
- Onboarding Doc: v1.0.0
- Last Updated: 2025
