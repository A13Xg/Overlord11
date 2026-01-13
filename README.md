# Overlord11

> A multi-agent AI orchestration framework with specialized sub-systems for research, analysis, writing, and code generation.

## Overview

Overlord11 is a comprehensive AI agent framework featuring four specialized sub-agent workflows, each designed for specific tasks. All systems support multiple AI providers (Anthropic Claude and Google Gemini) and follow a hierarchical orchestration pattern with quality assurance checkpoints.

## Features

- **Multi-Agent Workflows** - Four specialized systems for different tasks
- **Dual Model Support** - Switch between Anthropic Claude and Google Gemini
- **Hierarchical Orchestration** - Lead orchestrators coordinate specialized agents
- **Quality Assurance** - Built-in validation and review phases
- **Extensible Architecture** - JSON-based tool definitions and markdown agent roles
- **Interactive CLI** - Full interactive mode for Code-ProjectGen

## Quick Start

### Prerequisites

- Python 3.11+
- API keys for Anthropic and/or Google Gemini

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/Overlord11.git
   cd Overlord11
   ```

2. Install dependencies:
   ```bash
   pip install anthropic google-generativeai python-dotenv pyyaml
   ```

3. Configure environment:
   ```bash
   cp .env.example .env
   ```

4. Edit `.env` with your API keys:
   ```env
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   GOOGLE_GEMINI_API_KEY=your_google_gemini_api_key_here
   ```

## Directory Structure

```
Overlord11/
├── .env.example              # Environment template
├── .gitignore                # Git ignore rules
├── README.md                 # This documentation
├── pre_commit_clean.py       # Housekeeping utility
├── Consciousness.md          # AI framework documentation
├── Overlord11_sysprompt.md   # System prompt reference
├── Planned_Improvements.md   # Roadmap
│
├── Analysis-Summarize/       # Analysis & output generation
│   ├── config.json
│   ├── agents/
│   ├── tools/
│   └── python/run.py
│
├── Research-InfoGather/      # Research orchestration
│   ├── config.json
│   ├── agents/
│   ├── tools/
│   └── python/run.py
│
├── Writing-Literature/       # Content writing system
│   ├── config.json
│   ├── agents/
│   ├── tools/
│   └── python/run.py
│
├── Code-ProjectGen/          # Code generation system
│   ├── config.json
│   ├── agents/
│   ├── tools/
│   ├── python/run.py
│   ├── workspace/
│   └── output/
│
└── Model_Specific/           # Model-specific resources
```

---

## Sub-Agent Workflows

### 1. Analysis-Summarize (AS)

Multi-agent analysis and output generation system supporting diverse formats from text summaries to visual reports.

**Workflow Phases:** `INGEST → ANALYZE → FORMAT → RENDER → VALIDATE`

**Agents:**
| Agent | ID | Role |
|-------|-----|------|
| Lead Orchestrator | AS_DIR_01 | Manages workflow phases and state |
| Data Analyzer | AS_ANL_02 | Performs text, numerical, comparative analysis |
| Output Formatter | AS_FMT_03 | Transforms data into format-specific structures |
| Visual Renderer | AS_RND_04 | Creates visualizations and documents |
| Quality Validator | AS_VAL_05 | Ensures output quality and compliance |

**Capabilities:**
- Text analysis (summarization, entity extraction, sentiment, keywords)
- Numerical analysis (statistics, trends, correlations, outliers)
- Output formats: PDF, HTML, Markdown, CSV, JSON, charts, infographics

**Usage:**
```python
from Analysis_Summarize.python.run import AnalysisSystem

system = AnalysisSystem()
result = system.run_mission(
    input_data="Your data here...",
    output_specs={"format": "pdf_report", "analysis": "summarize"}
)
```

---

### 2. Research-InfoGather (DS)

Multi-agent research orchestration for automated information gathering, synthesis, and report generation.

**Workflow:** Hierarchical with approval checkpoints

**Agents:**
| Agent | ID | Role |
|-------|-----|------|
| Lead Orchestrator | DS_DIR_01 | Decomposes requests, manages state |
| Senior Web Researcher | DS_RES_02 | Gathers data from web sources |
| Data Synthesizer | DS_AGG_03 | Merges research into unified knowledge |
| Document Specialist | DS_FMT_04 | Transforms to requested style |
| Proofreader | DS_REV_05 | Quality assurance and validation |

**Styles Supported:**
- Formal: MLA, APA, Chicago, Harvard
- Informal: Scientific, Persuasive, Narrative

**Research Constraints:**
- Min/max sources per topic: 3-6
- Blacklisted domains: Wikipedia, social media
- Preferred sources: arxiv.org, .gov, .edu, reuters.com

**Usage:**
```python
from Research_InfoGather.python.run import ResearchSystem

system = ResearchSystem()
result = system.run_mission("Research quantum computing advances in 2025")
```

---

### 3. Writing-Literature (WL)

Multi-agent writing system for content transformation through compression, expansion, and refinement.

**Workflow Phases:** `INGEST → COMPRESS → EXPAND → REVIEW`

**Agents:**
| Agent | ID | Role |
|-------|-----|------|
| Lead Orchestrator | WL_DIR_01 | Manages writing workflow |
| Content Summarizer | WL_SUM_02 | Distills and compresses content |
| Content Writer | WL_WRT_03 | Transforms into polished writing |
| QA Proofreader | WL_REV_04 | Final quality assurance |

**Writing Styles:**
- Academic, Professional, Creative, Technical, Casual

**Quality Standards:**
- Minimum quality score: 7/10
- Grammar, tone, readability, and style checks

**Usage:**
```python
from Writing_Literature.python.run import WritingSystem

system = WritingSystem()
result = system.run_mission(
    user_content="Raw content to transform...",
    writing_params={"style": "professional", "length": 500}
)
```

---

### 4. Code-ProjectGen (CG)

AI-powered code generation system with project scaffolding, testing, and review capabilities.

**Workflow Phases:** `PLAN → ARCHITECT → IMPLEMENT → TEST → REVIEW`

**Agents:**
| Agent | ID | Role |
|-------|-----|------|
| Lead Orchestrator | CG_DIR_01 | Coordinates code generation |
| Software Architect | CG_ARC_02 | Designs project structure |
| Code Implementer | CG_COD_03 | Writes production code |
| Test Engineer | CG_TST_04 | Creates and runs tests |
| Code Reviewer | CG_REV_05 | Reviews code quality |

**Supported Languages:**
- Python, JavaScript, TypeScript, Go, Rust, Java, C#

**Project Templates:**
| Template | Description |
|----------|-------------|
| `python_cli` | Command-line application with argparse |
| `python_api` | FastAPI REST API service |
| `python_package` | Installable Python package |
| `node_api` | Express.js REST API |
| `react_app` | React frontend application |
| `fullstack` | Full-stack with backend + frontend |
| `custom` | User-defined structure |

**Tools:**
- `file_management` - Read, write, list, delete files
- `code_execution` - Run Python, shell, tests
- `project_scaffold` - Create project from template
- `code_analysis` - Lint, type check, security scan
- `dependency_management` - Package management

#### Interactive Mode

Run with full interactive prompts:
```bash
cd Code-ProjectGen/python
python run.py -i
```

**Interactive Flow:**
1. **Workspace Selection**
   - Built-in Agent Sandbox (default)
   - Specify existing directory
   - Create new directory

2. **Project Description**
   - Describe what you want to build

3. **Language Selection**
   - Choose from supported languages

4. **Template Selection**
   - Pick compatible template

5. **Features** (optional)
   - Add required features

6. **Confirmation**
   - Review and confirm settings

#### CLI Options

```bash
# Full interactive mode
python run.py -i

# Quick with description only
python run.py -d "Build a REST API for user management"

# Specify all options
python run.py \
  --workspace /path/to/project \
  --description "Create a CLI tool" \
  --language python \
  --template python_cli \
  --features "logging" "config file support"

# Skip prompts
python run.py -d "Build API" --use-sandbox --no-confirm
```

**All CLI Arguments:**
| Argument | Short | Description |
|----------|-------|-------------|
| `--workspace` | `-w` | Custom workspace directory |
| `--output-dir` | `-o` | Custom output for summaries |
| `--description` | `-d` | Project description |
| `--language` | `-l` | Programming language |
| `--template` | `-t` | Project template |
| `--features` | `-f` | Required features list |
| `--include-tests` | | Include test files (default: True) |
| `--include-docker` | | Include Docker config |
| `--interactive` | `-i` | Full interactive mode |
| `--use-sandbox` | | Skip workspace prompt |
| `--no-confirm` | | Skip confirmation |

---

## Model Configuration

All sub-agent systems support both Anthropic Claude and Google Gemini. Configuration is done in each system's `config.json`:

```json
{
  "model_config": {
    "provider": "anthropic",
    "models": {
      "anthropic": {
        "model_name": "claude-3-5-sonnet-20241022",
        "max_tokens": 8000,
        "env_var": "ANTHROPIC_API_KEY"
      },
      "gemini": {
        "model_name": "gemini-1.5-pro",
        "max_tokens": 8000,
        "env_var": "GOOGLE_GEMINI_API_KEY"
      }
    }
  }
}
```

**To switch providers**, change `"provider": "anthropic"` to `"provider": "gemini"`.

---

## Pre-Commit Housekeeping

The `pre_commit_clean.py` script handles temporary file cleanup and housekeeping tasks.

### Usage

```bash
# Run all tasks (clean + checks)
python pre_commit_clean.py

# Preview what would be deleted
python pre_commit_clean.py --dry-run

# Detailed output
python pre_commit_clean.py --verbose

# Clean only (skip checks/tests)
python pre_commit_clean.py --clean-only

# Clean all temp files (not just tmpclaude)
python pre_commit_clean.py --all

# Specify different root directory
python pre_commit_clean.py --root /path/to/dir
```

### Cleaned Patterns

| Pattern | Description |
|---------|-------------|
| `tmpclaude-*` | Claude temporary files |
| `*-cwd` | Working directory temp files |
| `*.tmp` | Generic temp files |
| `*.pyc` | Python bytecode |
| `__pycache__` | Python cache directories |
| `.pytest_cache` | Pytest cache |
| `.mypy_cache` | Mypy cache |
| `.ruff_cache` | Ruff cache |

### Skipped Directories

- `.git`
- `node_modules`
- `.venv`, `venv`, `env`

---

## Environment Variables

### Required

```env
# At least one of these is required
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_GEMINI_API_KEY=...
```

### Optional

```env
# Model configuration
MODEL_PROVIDER=anthropic  # or: gemini
MODEL_NAME=claude-3-5-sonnet-20241022
TEMPERATURE=0.7
MAX_TOKENS=2048

# Application settings
DEBUG=false
LOG_LEVEL=info

# External APIs (for Analysis-Summarize)
QUICKCHART_API_KEY=...
CLOUDCONVERT_API_KEY=...
```

---

## Architecture

### Common Patterns

All sub-agent systems follow these patterns:

1. **Hierarchical Orchestration**
   - Lead Orchestrator manages workflow
   - Delegates to specialized agents
   - Routes failed work back for correction

2. **Phase-Based Workflow**
   - Clear phases with defined inputs/outputs
   - Approval checkpoints between phases
   - Loop limits prevent infinite cycles

3. **Tool Registry**
   - JSON-defined tool specifications
   - Consistent parameter schemas
   - Error handling and result formatting

4. **Quality Gates**
   - Minimum quality scores
   - Validation checklists
   - Review and approval steps

### Agent Definition Structure

Agents are defined in markdown files (`agents/*.md`):
```markdown
# Agent Name (AGENT_ID)

## Identity
Role description...

## Primary Responsibilities
1. Responsibility one
2. Responsibility two

## Output Format
Expected output structure...

## Quality Checklist
- [ ] Check item one
- [ ] Check item two
```

### Tool Definition Structure

Tools are defined in JSON files (`tools/*.json`):
```json
{
  "name": "tool_name",
  "description": "What the tool does",
  "parameters": {
    "type": "object",
    "properties": {
      "param_name": {
        "type": "string",
        "description": "Parameter description"
      }
    },
    "required": ["param_name"]
  }
}
```

---

## Extending the Framework

### Adding a New Agent

1. Create markdown file in `agents/` directory
2. Define identity, responsibilities, and output format
3. Update orchestrator to delegate to new agent

### Adding a New Tool

1. Create JSON definition in `tools/` directory
2. Implement handler in `run.py`:
   ```python
   def _handle_new_tool(self, params):
       # Implementation
       return json.dumps({"status": "success", ...})
   ```
3. Add to `_execute_tool()` dispatch

### Creating a New Sub-System

1. Create new directory with structure:
   ```
   New-System/
   ├── config.json
   ├── agents/
   │   └── orchestrator.md
   ├── tools/
   └── python/
       └── run.py
   ```
2. Copy and adapt `run.py` from existing system
3. Define agents and tools for your workflow

---

## Security

- Never commit API keys or credentials
- Use `.env` files (git-ignored)
- Code execution is sandboxed with timeouts
- File operations are restricted to workspace
- Directory traversal is prevented

---

## Contributing

1. Follow existing organizational structure
2. Document new features and agents
3. Test with both Anthropic and Gemini providers
4. Run `pre_commit_clean.py` before committing

---

## License

See repository for license information.

---

## Support

For questions or issues, open an issue in this repository.
