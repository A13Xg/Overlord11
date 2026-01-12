# Analysis-Summarize

> A multi-agent analysis and output generation system supporting diverse formats from text summaries to visual reports

## 🔷 Overview

Analysis-Summarize is a versatile orchestration system that ingests various data types, performs comprehensive analysis, and generates outputs in multiple formats. From simple text summaries and CSV exports to professional PDF reports, interactive charts, and infographics, the system adapts to your needs while maintaining quality and accuracy.

## 🔶 Features

- 🟢 **Multi-Format Output** - Generate text, data, visual, and document outputs
- 🔵 **Flexible Analysis** - Text, numerical, comparative, and structural analysis capabilities
- 🟡 **Internal & External Rendering** - Works standalone or with enhanced external APIs
- 🟣 **Quality Assurance** - Automated validation for format compliance and data integrity
- 🟠 **Intelligent Fallbacks** - Graceful degradation when external services unavailable

## 🔷 Agent Roles

The system employs five specialized agents in a sequential pipeline:

1. **Lead Orchestrator (AS_DIR_01)** - Manages workflow, routing, state, and error recovery
2. **Data Analyzer (AS_ANL_02)** - Extracts insights, patterns, and structured information
3. **Output Formatter (AS_FMT_03)** - Transforms data into format-specific structures
4. **Visual Renderer (AS_RND_04)** - Creates visualizations and rendered documents
5. **Quality Validator (AS_VAL_05)** - Ensures output quality and compliance

## 🔶 Workflow Pipeline

```
INGEST → ANALYZE → FORMAT → RENDER → VALIDATE
   ↓        ↓          ↓        ↓         ↓
 Data   Insights  Structured Visual    Final
Input   Extract   Format   Output   Approval
```

### Phase 1: INGEST
- Accept data from files, text, URLs, APIs, or databases
- Validate and prepare data for analysis
- Support multiple formats: CSV, JSON, XML, text, markdown

### Phase 2: ANALYZE
- **Text Analysis:** Summarization, entity extraction, sentiment, keywords
- **Numerical Analysis:** Statistics, trends, correlations, outlier detection
- **Comparative Analysis:** Comparisons, change detection, benchmarking
- **Structural Analysis:** Hierarchies, networks, timelines, classification

### Phase 3: FORMAT
- Transform analysis into target format structure
- Apply style guidelines and formatting rules
- Prepare data for visualization or export
- Validate format syntax

### Phase 4: RENDER
- Generate visual outputs (charts, graphs, infographics)
- Create formatted documents (PDF, HTML, Markdown)
- Export data files (CSV, JSON, XML, Excel)
- Use internal libraries or external APIs based on configuration

### Phase 5: VALIDATE
- Verify data integrity and accuracy
- Check format compliance
- Assess visual quality
- Test file readability
- Provide quality score (1-10)

## 🔷 Supported Output Formats

### Text-Based
- **Summary** - Brief, moderate, or detailed text summaries
- **Quotes** - Extracted quotes with citations and sources
- **Report** - Structured reports with sections and findings
- **Bullets** - Organized bullet-point lists

### Data-Based
- **CSV** - Comma-separated values with customizable delimiters
- **JSON** - Structured data with indentation options
- **XML** - Hierarchical data with schema support
- **Excel** - Tab-separated values compatible with spreadsheet software

### Visual
- **Charts** - Line, bar, pie, scatter, histogram, heatmap
- **Infographics** - Professional visual designs
- **Timeline** - Chronological event visualization
- **Network** - Relationship and network diagrams

### Documents
- **PDF** - Professional reports with templates (academic, technical, creative)
- **HTML** - Web-viewable documents with styling
- **Markdown** - Portable formatted text (GitHub, CommonMark flavors)

## 🔶 Getting Started

### Prerequisites

- Python 3.8+
- Anthropic API key
- Required Python packages (see `requirements.txt`)
- Optional: External API keys for enhanced rendering

### Installation

1. Configure your Anthropic API key in the parent `.env` file:
   ```bash
   ANTHROPIC_API_KEY=your_key_here
   ```

2. Install dependencies:
   ```bash
   cd Analysis-Summarize/python
   pip install -r requirements.txt
   ```

3. (Optional) Configure external APIs in `.env`:
   ```bash
   QUICKCHART_API_KEY=your_key_here
   CLOUDCONVERT_API_KEY=your_key_here
   ```

4. Review and customize `config.json` for your needs

### Usage

#### Chat Mode (Manual)

Follow instructions in `ChatOnboarding.md` to use the system interactively with simulated agent coordination.

#### Python Mode (Automated)

```python
from python.run import AnalysisSystem

system = AnalysisSystem()

# Your data to analyze
data = """
Sales Performance Q4 2025:
Revenue: $2.1M (up 15% from Q3)
New customers: 340
Customer retention: 94%
Top products: Widget Pro (40%), Service Plus (30%)
"""

# Specify desired output
specs = {
    "format": "pdf_report",
    "type": "professional",
    "analysis": ["summarize", "extract_entities", "statistics"],
    "options": {
        "include_charts": True,
        "include_toc": True,
        "template": "professional"
    }
}

# Run the analysis
result = system.run_mission(data, specs)
print(result)
```

## 🔷 Configuration

The `config.json` file controls system behavior:

### Output Formats

Four main categories with detailed options:
- **Text-based:** Summaries, quotes, reports, bullets
- **Data-based:** CSV, JSON, XML, Excel
- **Visual:** Charts, infographics, timelines, networks
- **Document:** PDF, HTML, Markdown

### Analysis Capabilities

- **Text Analysis:** 6 types (summarization, entities, sentiment, keywords, topics, citations)
- **Numerical Analysis:** 5 types (statistics, trends, correlations, outliers, distributions)
- **Comparative Analysis:** 4 types (comparisons, change detection, benchmarking, gaps)
- **Structural Analysis:** 4 types (hierarchies, networks, timelines, classification)

### Rendering Modes

**Internal Mode (Default):**
- Uses Python libraries only: matplotlib, seaborn, reportlab, pandas
- No external dependencies or API costs
- Suitable for basic to intermediate outputs

**External Mode (Optional):**
- QuickChart API: Professional chart rendering
- CloudConvert API: Advanced document processing
- Enhanced quality and additional features
- Requires API keys and configuration

## 🔶 Directory Structure

```
Analysis-Summarize/
├── README.md                 # This file
├── ChatOnboarding.md         # Manual chat mode instructions
├── config.json               # System configuration
├── agents/                   # Agent role definitions
│   ├── orchestrator.md       # Workflow coordinator
│   ├── analyzer.md           # Data analysis engine
│   ├── formatter.md          # Format transformer
│   ├── renderer.md           # Visual generator
│   └── validator.md          # Quality assurance
├── python/                   # Python implementation
│   ├── run.py                # Main execution script
│   ├── requirements.txt      # Python dependencies
│   └── utils/
│       ├── analyzers.py      # Analysis utilities
│       ├── visualizations.py # Chart/graph generation
│       └── renderers.py      # Document rendering
├── tools/                    # Tool definitions
│   ├── data_ingestion_tool.json
│   ├── analysis_engine_tool.json
│   ├── format_converter_tool.json
│   ├── visualization_tool.json
│   ├── document_renderer_tool.json
│   └── file_tool.json
├── input/                    # Input data directory
├── output/                   # Generated outputs
└── temp/                     # Temporary files
```

## 🔷 Common Use Cases

### Business Intelligence
- Input: Sales data, customer metrics
- Analysis: Statistics, trends, comparisons
- Output: PDF report with charts and insights

### Research Analysis
- Input: Research papers, study data
- Analysis: Summarization, entity extraction, citation tracking
- Output: Structured summary with references

### Data Visualization
- Input: Numerical datasets
- Analysis: Statistical analysis, trend detection
- Output: Interactive charts (HTML) or static images (PNG/PDF)

### Content Summarization
- Input: Long documents, articles, reports
- Analysis: Text summarization, keyword extraction
- Output: Brief/moderate/detailed text summary

### Comparative Analysis
- Input: Multiple datasets or versions
- Analysis: Change detection, benchmarking
- Output: Side-by-side comparison report

## 🔶 Quality Standards

The system enforces strict quality requirements:

- **Minimum Quality Score:** 7/10
- **Data Integrity:** No information loss during transformation
- **Format Compliance:** Valid syntax for all output formats
- **Visual Quality:** Clear, readable charts and documents
- **File Readability:** Output files must open correctly in standard software

## 🔷 Rendering Capabilities

### Internal (Python Libraries)

**Visualization:**
- matplotlib: Line, bar, scatter, pie charts
- seaborn: Statistical visualizations, heatmaps
- plotly: Interactive charts (HTML export)

**Documents:**
- reportlab: PDF generation with layout control
- weasyprint: HTML to PDF conversion
- markdown2: Markdown processing

**Data Processing:**
- pandas: Data manipulation and export
- csv/json: Built-in Python libraries

### External (Optional APIs)

**Enhanced Capabilities:**
- QuickChart: Professional chart rendering with custom styling
- CloudConvert: Advanced document conversion and processing
- Higher resolution outputs
- Additional format options

## 🔶 Error Handling

The system gracefully handles various failure scenarios:

- **Insufficient Data:** Requests additional input from user
- **Format Unsupported:** Suggests alternatives or API enablement
- **Rendering Error:** Falls back to simpler format automatically
- **API Unavailable:** Switches to internal capabilities seamlessly
- **Loop Limit:** Delivers partial output after 12 iterations with warning

## 🔷 Customization

Extend the system for specific needs:

1. **Add Output Formats:** Extend `output_formats` in `config.json`
2. **New Analysis Types:** Add capabilities to analyzer agent and utilities
3. **Custom Templates:** Create document templates in renderers.py
4. **External APIs:** Add new API integrations to config
5. **Visualization Types:** Extend visualizations.py with new chart types

## 🔶 Best Practices

- **Input Quality:** Provide clean, structured data for best results
- **Format Selection:** Choose formats appropriate for your data type
- **API Configuration:** Enable external APIs for production-quality outputs
- **Validation:** Review quality scores and validation feedback
- **Iteration:** Use rejection feedback to refine analysis parameters

## 🔷 Limitations

- Maximum 12 iteration loops to prevent infinite cycles
- Chart quality depends on data structure and completeness
- PDF generation quality varies by rendering method
- External API dependencies may introduce latency
- Complex infographics require manual design input

## 🔶 Advanced Features

### Multi-Source Ingestion
Process data from multiple sources simultaneously:
```python
data = {
    "sources": [
        {"type": "file", "path": "data.csv"},
        {"type": "text", "content": "Additional context..."},
        {"type": "url", "path": "https://api.example.com/data"}
    ]
}
```

### Batch Processing
Generate multiple output formats in one workflow:
```python
specs = {
    "formats": ["summary", "csv", "chart", "pdf_report"],
    "analysis": "comprehensive"
}
```

### Custom Styling
Apply custom styles to visualizations and documents:
```python
options = {
    "color_scheme": "corporate",
    "font_family": "Arial",
    "template": "custom",
    "branding": {"logo": "logo.png", "colors": ["#003366", "#66ccff"]}
}
```

## 🔷 Performance Optimization

- **Internal Mode:** Faster, no network latency
- **External Mode:** Better quality, higher resource requirements
- **Caching:** Reuse analysis results for multiple outputs
- **Parallel Processing:** Generate multiple charts simultaneously
- **Output Compression:** Optimize file sizes for distribution

## 🔶 Integration

This subsystem integrates seamlessly with the Overlord11 ecosystem:

- Receives research data from Research-InfoGather
- Provides analyzed content to Writing-Literature
- Shares configuration and authentication
- Compatible output formats across all subsystems

## 🔷 Troubleshooting

### Common Issues

**Issue:** Charts are low quality
- **Solution:** Enable external APIs or increase DPI in matplotlib settings

**Issue:** PDF generation fails
- **Solution:** Install weasyprint or pdfkit, or fall back to reportlab

**Issue:** External API errors
- **Solution:** Check API keys, verify internet connection, use internal mode

**Issue:** Analysis results incomplete
- **Solution:** Provide more structured input data, increase analysis depth

**Issue:** Format conversion errors
- **Solution:** Verify input format, check syntax, use format_hint parameter

## 🔶 Future Enhancements

- Real-time data streaming and live dashboards
- Machine learning-based analysis (anomaly detection, predictions)
- Natural language query interface
- Collaborative multi-user analysis sessions
- Cloud storage integration (S3, Google Drive, Dropbox)
- API endpoint for programmatic access
- Mobile app support

## 🔷 Support

For questions about this subsystem:
- Review agent documentation in `/agents/`
- Check configuration examples in `config.json`
- Examine tool definitions in `/tools/`
- Consult utility functions in `/python/utils/`
- Refer to workflow phases in `ChatOnboarding.md`

---

**Version:** 1.0.0  
**Last Updated:** January 2026  
**Maintained by:** Overlord11 Project
