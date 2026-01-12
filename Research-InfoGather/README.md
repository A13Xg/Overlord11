# Research-InfoGather

> A multi-agent research orchestration system for automated information gathering, synthesis, and report generation

## 🔷 Overview

Research-InfoGather is a hierarchical agent system designed to automate the research process from query decomposition to final report generation. It uses a multi-agent architecture with specialized roles to gather, validate, synthesize, and format research content according to configurable standards and style guides.

## 🔶 Features

- 🟢 **Multi-Agent Architecture** - Coordinated workflow with specialized agents for different tasks
- 🔵 **Quality Control** - Built-in validation, proofreading, and conflict resolution mechanisms
- 🟡 **Flexible Styling** - Support for academic (MLA, APA, Chicago, Harvard) and custom formats
- 🟣 **Source Management** - Domain filtering with blacklists and preferred source prioritization
- 🟠 **Python Integration** - Automated execution via Anthropic Claude API

## 🔷 Agent Roles

The system employs five specialized agents:

1. **Lead Orchestrator (DS_DIR_01)** - Decomposes requests, manages state, and coordinates workflow
2. **Senior Web Researcher (DS_RES_02)** - Gathers raw data while enforcing source quality standards
3. **Data Synthesizer (DS_AGG_03)** - Merges research packets and resolves conflicts between sources
4. **Technical Document Specialist (DS_FMT_04)** - Formats output according to specified style guides
5. **Quality Assurance Critic (DS_REV_05)** - Final validation of links, tone, and compliance

## 🔶 Getting Started

### Prerequisites

- Python 3.8+
- Anthropic API key
- Required Python packages (see `requirements.txt`)

### Configuration

1. Ensure your Anthropic API key is set in the parent `.env` file:
   ```bash
   ANTHROPIC_API_KEY=your_key_here
   ```

2. Review and customize `config.json` settings:
   - Source constraints (min/max sources per topic)
   - Domain blacklist and preferred sources
   - Style definitions and feature flags
   - Orchestration parameters

### Usage

#### Chat Mode (Manual)

Follow the instructions in `ChatOnboarding.md` to use the system in a chat interface. The system simulates agent handoffs and tool usage.

#### Python Mode (Automated)

```python
from python.run import ResearchSystem

system = ResearchSystem()
result = system.run_mission("Research the latest developments in quantum computing")
print(result)
```

## 🔷 Configuration

The `config.json` file controls system behavior:

### Style Definitions
- **Formal:** MLA, APA, CHICAGO, HARVARD
- **Informal:** Scientific_Descriptive, Persuasive, Narrative

### Research Constraints
- Minimum sources per topic: 3
- Maximum sources per topic: 6
- Blacklisted domains: Wikipedia, social media platforms
- Preferred sources: Academic journals, government sites, educational institutions

### Orchestration Logic
- Mode: Hierarchical
- Maximum loops: 12
- Halt on low confidence: enabled
- Approval checkpoints: After planning and before final output

## 🔶 Tools

The system includes three primary tools:

1. **web_search** - Performs searches while respecting domain blacklists
2. **file_management** - Handles reading and writing of research outputs
3. **link_validator** - Verifies URL validity and checks against blacklist

## 🔷 Directory Structure

```
Research-InfoGather/
├── README.md                 # This file
├── ChatOnboarding.md         # Manual chat mode instructions
├── config.json               # System configuration
├── agents/                   # Agent role definitions
│   ├── orchestrator.md       # Lead coordinator
│   ├── researcher.md         # Data gatherer
│   ├── aggregator.md         # Data synthesizer
│   ├── formatter.md          # Style formatter
│   └── proofreader.md        # Quality assurance
├── python/                   # Python implementation
│   ├── run.py                # Main execution script
│   ├── requirements.txt      # Python dependencies
│   └── utils/
│       └── validators.py     # URL validation utilities
└── tools/                    # Tool definitions
    ├── search_tool.json      # Web search tool
    ├── file_tool.json        # File management tool
    └── validator_tool.json   # Link validator tool
```

## 🔶 Workflow

1. **Planning Phase** - Orchestrator decomposes user request into sub-queries
2. **Research Phase** - Researcher gathers data from approved sources
3. **Synthesis Phase** - Aggregator merges findings and resolves conflicts
4. **Formatting Phase** - Formatter applies requested style guide
5. **Review Phase** - Proofreader validates quality and compliance
6. **Delivery** - Final report returned or iteration triggered if rejected

## 🔷 Failure Modes

The system handles edge cases gracefully:

- **EMPTY_RESEARCH:** Broadens search terms automatically, requests permission for broader sources
- **LOOP_LIMIT:** Delivers partial report with warning after 12 iterations
- **CONFLICT_REPORTING:** Flags disagreements between high-quality sources

## 🔶 Customization

To adapt the system for your needs:

1. **Add Style Guides:** Extend `style_definitions` in `config.json`
2. **Modify Source Rules:** Update blacklist and preferred sources
3. **Adjust Agent Behavior:** Edit agent markdown files in `/agents/`
4. **Create Custom Tools:** Add new tool definitions to `/tools/`

## 🔷 Best Practices

- Use specific, focused research queries for better results
- Review blacklist settings to ensure appropriate sources
- Set realistic source count ranges (3-6 recommended)
- Enable conflict reporting for controversial topics
- Use formal styles for academic work, informal for exploratory research

## 🔶 Limitations

- Requires active internet connection for web research
- Tool execution is simulated in chat mode
- Maximum 12 iteration loops to prevent infinite cycles
- Blacklist enforcement depends on URL pattern matching

## 🔷 Future Enhancements

- Real-time collaborative research sessions
- Citation graph visualization
- Automated fact-checking integration
- Multi-language support
- Export to multiple document formats

## 🔶 Support

For questions about this subsystem, refer to agent documentation in `/agents/` or review the configuration examples in `config.json`.
