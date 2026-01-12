# Writing-Literature

> A multi-agent writing system for content transformation: ingestion, compression, expansion, and refinement

## 🔷 Overview

Writing-Literature is a hierarchical agent orchestration system designed to transform raw content into polished, styled written work. The system ingests user-supplied materials, compresses them into structured summaries, expands them according to specific parameters, and ensures quality through automated proofreading.

## 🔶 Features

- 🟢 **Content Ingestion** - Accept text, files, or multiple documents as input
- 🔵 **Intelligent Compression** - Extract core ideas while preserving critical details
- 🟡 **Style-Aware Expansion** - Transform summaries into full-form content with configurable styles
- 🟣 **Quality Assurance** - Automated proofreading with compliance validation
- 🟠 **Flexible Parameters** - Control length, style, tone, and format precisely

## 🔷 Agent Roles

The system employs four specialized agents in a sequential workflow:

1. **Lead Orchestrator (WL_DIR_01)** - Manages workflow, tracks state, handles routing and error recovery
2. **Content Summarizer (WL_SUM_02)** - Distills raw content into structured, actionable summaries
3. **Content Writer (WL_WRT_03)** - Expands summaries into polished content matching user specifications
4. **Quality Assurance Proofreader (WL_REV_04)** - Validates quality, style compliance, and technical accuracy

## 🔶 Workflow Phases

```
INGEST → COMPRESS → EXPAND → REVIEW
   ↓         ↓          ↓         ↓
Content  Summary   Draft    Final Output
         (20-50%)  (Target)  (Approved)
```

### Phase 1: INGEST
- Accept user content from various sources
- Validate input length (50-50,000 words)
- Prepare content for compression

### Phase 2: COMPRESS
- Extract core themes and arguments
- Remove redundancy and filler
- Achieve target compression ratio (20-50% of original)
- Preserve critical context for expansion

### Phase 3: EXPAND
- Apply user-specified style guide
- Meet target word count (±10% tolerance)
- Build logical flow and transitions
- Enhance with appropriate detail and structure

### Phase 4: REVIEW
- Check grammar, spelling, and punctuation
- Verify style and tone compliance
- Validate length parameters
- Assess overall quality (minimum score: 7/10)

## 🔷 Getting Started

### Prerequisites

- Python 3.8+
- Anthropic API key
- Required Python packages (see `requirements.txt`)

### Installation

1. Ensure your Anthropic API key is configured in the parent `.env` file:
   ```bash
   ANTHROPIC_API_KEY=your_key_here
   ```

2. Install dependencies:
   ```bash
   cd Writing-Literature/python
   pip install -r requirements.txt
   ```

3. Review and customize `config.json` for your needs

### Usage

#### Chat Mode (Manual)

Follow the instructions in `ChatOnboarding.md` to use the system in a chat interface with simulated agent handoffs.

#### Python Mode (Automated)

```python
from python.run import WritingSystem

system = WritingSystem()

# Your raw content
content = """
[Your source material here - notes, research, drafts, etc.]
"""

# Specify parameters
params = {
    "style": "professional",      # academic, professional, creative, technical, casual
    "length": 800,                # Target word count
    "tone": "informative",        # formal, neutral, persuasive, informative
    "format": "article with introduction and conclusion"
}

# Run the workflow
result = system.run_mission(content, params)
print(result)
```

## 🔶 Configuration

The `config.json` file controls system behavior:

### Style Definitions

Five pre-configured styles with distinct characteristics:

- **Academic** - Formal, structured, citation-ready for scholarly work
- **Professional** - Business-appropriate, clear, and actionable
- **Creative** - Narrative-driven, engaging, descriptive storytelling
- **Technical** - Precise, detailed, specification-oriented documentation
- **Casual** - Conversational, accessible, and friendly communication

### Writing Constraints

- **Input Length:** 50-50,000 words
- **Length Tolerance:** ±10% of target word count
- **Compression Ratios:**
  - Verbose input (>5000 words): 25% retention
  - Moderate input (1000-5000 words): 35% retention
  - Concise input (<1000 words): 50% retention

### Quality Standards

- Minimum quality score: 7/10
- Grammar and spelling validation
- Tone consistency checking
- Style compliance verification
- Readability assessment

## 🔷 Available Tools

The system includes four specialized tools:

1. **content_ingestion** - Loads content from files, text, or URLs with metadata support
2. **word_counter** - Analyzes text statistics (words, characters, reading time, sentences)
3. **style_validator** - Validates content against style guides with compliance scoring
4. **file_management** - Handles reading and writing of drafts and outputs

## 🔶 Directory Structure

```
Writing-Literature/
├── README.md                 # This file
├── ChatOnboarding.md         # Manual chat mode instructions
├── config.json               # System configuration
├── agents/                   # Agent role definitions
│   ├── orchestrator.md       # Workflow coordinator
│   ├── summarizer.md         # Content compressor
│   ├── writer.md             # Content expander
│   └── proofreader.md        # Quality validator
├── python/                   # Python implementation
│   ├── run.py                # Main execution script
│   ├── requirements.txt      # Python dependencies
│   └── utils/
│       └── text_analysis.py  # Text analysis utilities
└── tools/                    # Tool definitions
    ├── content_ingestion_tool.json
    ├── word_counter_tool.json
    ├── style_validator_tool.json
    └── file_tool.json
```

## 🔷 Common Use Cases

### Academic Paper Transformation
- Input: Research notes and references
- Style: Academic
- Length: 2000-3000 words
- Output: Structured scholarly article

### Business Report Generation
- Input: Data analysis and findings
- Style: Professional
- Length: 1000-1500 words
- Output: Executive-ready business report

### Blog Post Creation
- Input: Rough ideas and bullet points
- Style: Casual or Creative
- Length: 600-1000 words
- Output: Engaging blog post

### Technical Documentation
- Input: Product specifications and notes
- Style: Technical
- Length: Variable
- Output: Clear technical documentation

## 🔶 Error Handling

The system gracefully handles edge cases:

- **INSUFFICIENT_CONTENT:** Requests additional material if input < 50 words
- **PARAMETER_MISSING:** Asks for clarification on style, length, or tone
- **LOOP_LIMIT:** Delivers draft with warning after 10 iterations
- **LENGTH_VIOLATION:** Triggers recompression if output exceeds target by >20%

## 🔷 Customization

Extend the system for your specific needs:

1. **Add Style Guides:** Extend `style_definitions` in `config.json` with custom styles
2. **Modify Compression Ratios:** Adjust `compression_ratios` for different content types
3. **Update Agent Behavior:** Edit agent markdown files in `/agents/` to refine instructions
4. **Create Custom Tools:** Add new tool definitions to `/tools/` directory
5. **Adjust Quality Thresholds:** Modify `quality_standards` for stricter/looser validation

## 🔶 Best Practices

- **Input Quality:** Provide clear, organized source material for best results
- **Specific Parameters:** Be explicit about desired style, length, and audience
- **Iterative Refinement:** Use rejection feedback to improve subsequent attempts
- **Length Targets:** Set realistic word counts based on content complexity
- **Style Selection:** Choose styles appropriate for your audience and purpose

## 🔷 Limitations

- Maximum 10 iteration loops to prevent infinite cycles
- Input length capped at 50,000 words
- Length tolerance of ±10% may not suit all use cases
- Style validation is heuristic-based, not perfect
- Requires active Anthropic API access

## 🔶 Advanced Features

### Multi-Document Ingestion
Process multiple source documents simultaneously:
```python
content = {
    "source_type": "file",
    "files": ["draft1.txt", "notes.md", "research.pdf"]
}
```

### Output Format Options
Choose from multiple output formats:
- Markdown (default)
- Plain text
- HTML
- Structured JSON

### Reading Time Estimates
Automatically includes estimated reading time based on average reading speed (200 WPM).

### Style Compliance Scoring
Provides detailed compliance scores for:
- Formality level
- Tone consistency
- Readability metrics
- Technical accuracy

## 🔷 Future Enhancements

- Multi-language support for international content
- Citation management and bibliography generation
- SEO optimization for web content
- Voice and brand consistency checking
- Integration with popular writing platforms
- Real-time collaborative editing

## 🔶 Troubleshooting

### Common Issues

**Issue:** Output too short/long
- **Solution:** Adjust length tolerance in config or provide clearer length requirements

**Issue:** Style mismatch
- **Solution:** Review style definitions and ensure parameters match desired output

**Issue:** Quality rejections
- **Solution:** Examine proofreader feedback and refine source content or parameters

**Issue:** Compression too aggressive
- **Solution:** Modify compression ratios in config for your content type

## 🔷 Support

For questions about this subsystem:
- Review agent documentation in `/agents/`
- Check configuration examples in `config.json`
- Refer to workflow phases in `ChatOnboarding.md`
- Examine tool definitions in `/tools/`

## 🔶 Integration

This subsystem integrates with the broader Overlord11 ecosystem:
- Shares environment configuration with parent project
- Can receive input from Research-InfoGather subsystem
- Outputs compatible with other analysis tools
- Uses common authentication and API management

---

**Version:** 1.0.0  
**Last Updated:** January 2026  
**Maintained by:** Overlord11 Project
