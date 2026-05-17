"""
Job Templates API — pre-built task prompts grouped by category.

Templates are static and hardcoded here (no DB).  Each template has:
  id:          unique slug
  category:    display group
  title:       short name shown in the card grid
  description: one-line summary shown under the title
  prompt:      the full prompt injected into the job
  tags:        searchable labels
  icon:        single ASCII/Unicode char for the card icon
"""

from fastapi import APIRouter

router = APIRouter(tags=["templates"])

_TEMPLATES = [
    # ── Research ─────────────────────────────────────────────────────────────
    {
        "id": "deep-research",
        "category": "Research",
        "title": "Deep Research Report",
        "description": "Comprehensive multi-source research with citations and summary",
        "icon": "◈",
        "tags": ["research", "report", "web"],
        "prompt": (
            "Conduct deep research on the following topic: [TOPIC]\n\n"
            "Requirements:\n"
            "1. Search multiple authoritative sources\n"
            "2. Synthesize findings into a structured report\n"
            "3. Include key statistics, dates, and named sources\n"
            "4. Identify consensus views AND notable disagreements\n"
            "5. End with a concise executive summary (under 200 words)\n\n"
            "Deliver a well-organized Markdown document with sections: "
            "Overview, Key Findings, Evidence, Counterpoints, Summary."
        ),
    },
    {
        "id": "competitive-analysis",
        "category": "Research",
        "title": "Competitive Analysis",
        "description": "Compare products, companies, or approaches side-by-side",
        "icon": "⊞",
        "tags": ["research", "comparison", "market"],
        "prompt": (
            "Perform a competitive analysis comparing: [SUBJECTS]\n\n"
            "For each subject cover:\n"
            "- Core strengths and unique advantages\n"
            "- Weaknesses and gaps\n"
            "- Target audience and positioning\n"
            "- Pricing / cost model (if applicable)\n"
            "- Recent notable developments\n\n"
            "Conclude with a ranked recommendation matrix and a clear winner "
            "for each use-case scenario."
        ),
    },

    # ── Code ─────────────────────────────────────────────────────────────────
    {
        "id": "code-feature",
        "category": "Code",
        "title": "Build a Feature",
        "description": "Design, implement, test, and document a new feature end-to-end",
        "icon": "⟨/⟩",
        "tags": ["code", "feature", "tests"],
        "prompt": (
            "Implement the following feature: [FEATURE DESCRIPTION]\n\n"
            "Language / framework: [STACK]\n"
            "Existing codebase context: [BRIEF DESCRIPTION OR PASTE KEY FILES]\n\n"
            "Deliverables:\n"
            "1. Implementation with clean, production-ready code\n"
            "2. Unit tests covering happy path and edge cases\n"
            "3. Inline comments for non-obvious logic\n"
            "4. Short integration guide (how to wire it in)\n\n"
            "Prioritise correctness, then readability, then performance."
        ),
    },
    {
        "id": "code-review",
        "category": "Code",
        "title": "Code Review",
        "description": "Audit code for bugs, security issues, and style violations",
        "icon": "⌥",
        "tags": ["code", "review", "security"],
        "prompt": (
            "Review the following code thoroughly:\n\n"
            "```\n[PASTE CODE HERE]\n```\n\n"
            "Check for:\n"
            "- Bugs and logic errors\n"
            "- Security vulnerabilities (OWASP Top 10, injection, auth issues)\n"
            "- Performance bottlenecks\n"
            "- Code style and readability\n"
            "- Missing error handling\n"
            "- Test coverage gaps\n\n"
            "Format findings as a prioritised list: CRITICAL → HIGH → MEDIUM → LOW. "
            "For each issue, include: location, description, severity, and a concrete fix."
        ),
    },
    {
        "id": "refactor",
        "category": "Code",
        "title": "Refactor & Modernise",
        "description": "Clean up legacy code while preserving all behaviour",
        "icon": "⟳",
        "tags": ["code", "refactor", "cleanup"],
        "prompt": (
            "Refactor the following code: [DESCRIPTION OR PASTE]\n\n"
            "Goals:\n"
            "- Eliminate dead code and duplication\n"
            "- Improve naming and structure\n"
            "- Apply idiomatic patterns for the language\n"
            "- Do NOT change external behaviour or public API\n"
            "- Add or update docstrings/comments where logic is non-obvious\n\n"
            "Provide the refactored version with a diff summary explaining "
            "what changed and why."
        ),
    },
    {
        "id": "debug",
        "category": "Code",
        "title": "Debug & Root Cause",
        "description": "Investigate a bug and produce a verified fix",
        "icon": "⚡",
        "tags": ["code", "debug", "bug"],
        "prompt": (
            "Debug the following issue:\n\n"
            "Problem description: [DESCRIBE BUG]\n"
            "Error message / stack trace:\n```\n[PASTE ERROR]\n```\n"
            "Relevant code:\n```\n[PASTE CODE]\n```\n\n"
            "Steps:\n"
            "1. Identify the root cause (not just the symptom)\n"
            "2. Explain why it happens\n"
            "3. Provide a minimal, targeted fix\n"
            "4. Suggest a test that would catch this regression\n"
            "5. Note any related issues to watch for"
        ),
    },

    # ── Data Analysis ─────────────────────────────────────────────────────────
    {
        "id": "data-summary",
        "category": "Data",
        "title": "Data Analysis & Summary",
        "description": "Parse, analyse, and extract insights from structured data",
        "icon": "▦",
        "tags": ["data", "analysis", "insights"],
        "prompt": (
            "Analyse the following dataset:\n\n"
            "[PASTE DATA OR DESCRIBE SCHEMA]\n\n"
            "Provide:\n"
            "1. Dataset overview (rows, columns, types, nulls)\n"
            "2. Descriptive statistics for numeric fields\n"
            "3. Top patterns, trends, and anomalies\n"
            "4. Correlation highlights (if applicable)\n"
            "5. 3-5 actionable insights with supporting evidence\n"
            "6. Recommended next analysis steps\n\n"
            "Format output with clear section headings and a one-paragraph "
            "executive summary at the top."
        ),
    },
    {
        "id": "sql-query",
        "category": "Data",
        "title": "SQL Query Builder",
        "description": "Write optimised SQL for complex data retrieval tasks",
        "icon": "⊂",
        "tags": ["data", "sql", "database"],
        "prompt": (
            "Write SQL to answer the following business question:\n\n"
            "Question: [YOUR QUESTION]\n"
            "Database schema:\n```sql\n[PASTE SCHEMA]\n```\n"
            "Database engine: [PostgreSQL / MySQL / SQLite / etc.]\n\n"
            "Deliver:\n"
            "1. The complete, runnable query with clear aliases\n"
            "2. A plain-English walkthrough of the query logic\n"
            "3. Any indexes that would improve performance\n"
            "4. Edge cases the query handles (nulls, duplicates, etc.)"
        ),
    },

    # ── Writing ───────────────────────────────────────────────────────────────
    {
        "id": "technical-doc",
        "category": "Writing",
        "title": "Technical Documentation",
        "description": "Write clear, structured docs for APIs, tools, or systems",
        "icon": "◻",
        "tags": ["writing", "docs", "technical"],
        "prompt": (
            "Write technical documentation for: [SUBJECT]\n\n"
            "Audience: [DEVELOPERS / END USERS / ADMINS]\n"
            "Context: [BRIEF DESCRIPTION OF THE SYSTEM]\n\n"
            "Include:\n"
            "- Overview and purpose\n"
            "- Prerequisites / requirements\n"
            "- Step-by-step setup or usage guide\n"
            "- Reference section (parameters, options, return values)\n"
            "- At least 2 worked examples\n"
            "- Common errors and how to resolve them\n\n"
            "Tone: precise, concise, no jargon unless necessary."
        ),
    },
    {
        "id": "executive-brief",
        "category": "Writing",
        "title": "Executive Brief",
        "description": "Distil complex information into a decision-ready summary",
        "icon": "▸",
        "tags": ["writing", "summary", "executive"],
        "prompt": (
            "Write an executive brief on: [TOPIC]\n\n"
            "Source material: [PASTE OR DESCRIBE]\n"
            "Audience: [ROLE / LEVEL]\n\n"
            "Format:\n"
            "1. Situation (2-3 sentences)\n"
            "2. Key findings (3-5 bullet points)\n"
            "3. Options considered (brief)\n"
            "4. Recommendation with rationale\n"
            "5. Risks and mitigations\n"
            "6. Next steps with owners and dates\n\n"
            "Total length: under 400 words. No filler. Every sentence earns its place."
        ),
    },

    # ── Review / QA ──────────────────────────────────────────────────────────
    {
        "id": "test-plan",
        "category": "Review",
        "title": "Test Plan",
        "description": "Generate a thorough test plan for a feature or system",
        "icon": "✓",
        "tags": ["review", "testing", "qa"],
        "prompt": (
            "Create a test plan for: [FEATURE / SYSTEM]\n\n"
            "Stack: [LANGUAGE + FRAMEWORK]\n"
            "Context: [HOW IT WORKS]\n\n"
            "Include:\n"
            "1. Test objectives and scope\n"
            "2. Unit tests (function-level, with specific scenarios)\n"
            "3. Integration tests (cross-component flows)\n"
            "4. Edge cases and negative tests\n"
            "5. Performance/load considerations\n"
            "6. Security tests (if applicable)\n"
            "7. Acceptance criteria checklist\n\n"
            "For each test: provide the scenario, input, expected output, and priority."
        ),
    },
    {
        "id": "security-audit",
        "category": "Review",
        "title": "Security Audit",
        "description": "Audit a system or codebase for security vulnerabilities",
        "icon": "⊗",
        "tags": ["review", "security", "audit"],
        "prompt": (
            "Perform a security audit on: [SYSTEM / CODE]\n\n"
            "Context: [DESCRIBE WHAT IT DOES AND WHO USES IT]\n\n"
            "Audit against:\n"
            "- OWASP Top 10 (injection, auth, XSS, IDOR, misconfiguration, etc.)\n"
            "- Input validation and sanitisation\n"
            "- Authentication and authorisation logic\n"
            "- Secrets management (env vars, hardcoded keys)\n"
            "- Dependency vulnerabilities\n"
            "- Data exposure risks\n"
            "- Logging and audit trail completeness\n\n"
            "Output: prioritised findings table (CRITICAL / HIGH / MEDIUM / LOW) "
            "with CVE references where applicable and concrete remediation steps."
        ),
    },

    # ── Automation ────────────────────────────────────────────────────────────
    {
        "id": "automation-script",
        "category": "Automation",
        "title": "Automation Script",
        "description": "Write a script to automate a repetitive workflow",
        "icon": "⊙",
        "tags": ["automation", "script", "workflow"],
        "prompt": (
            "Write a script to automate: [TASK DESCRIPTION]\n\n"
            "Language: [Python / Bash / PowerShell / etc.]\n"
            "Runs on: [OS]\n"
            "Inputs: [WHAT THE SCRIPT RECEIVES]\n"
            "Output: [WHAT IT PRODUCES]\n\n"
            "Requirements:\n"
            "1. Idempotent — safe to run multiple times\n"
            "2. Clear logging of each step\n"
            "3. Graceful error handling with useful messages\n"
            "4. Usage/help text\n"
            "5. Dry-run mode (show what would happen without doing it)\n\n"
            "Include a brief README block at the top of the file."
        ),
    },
    {
        "id": "pipeline-design",
        "category": "Automation",
        "title": "Pipeline Design",
        "description": "Design a CI/CD or data pipeline with stages and failure handling",
        "icon": "⋯",
        "tags": ["automation", "pipeline", "cicd", "devops"],
        "prompt": (
            "Design a pipeline for: [GOAL]\n\n"
            "Technology stack: [TOOLS / PLATFORM]\n"
            "Constraints: [TIMING, BUDGET, TEAM SIZE, etc.]\n\n"
            "Deliver:\n"
            "1. Stage-by-stage pipeline diagram (ASCII or Mermaid)\n"
            "2. Purpose and owner of each stage\n"
            "3. Failure handling and rollback strategy\n"
            "4. Monitoring and alerting hooks\n"
            "5. Configuration-as-code skeleton (YAML / Dockerfile / etc.)\n"
            "6. Estimated run-time and resource requirements"
        ),
    },
]

# Build lookup index
_BY_ID = {t["id"]: t for t in _TEMPLATES}
_CATEGORIES = sorted({t["category"] for t in _TEMPLATES})


@router.get("/api/templates")
async def list_templates(category: str = ""):
    """
    Return all job templates, optionally filtered by category.

    Query params:
        category  — filter to a specific category (case-insensitive)

    Response:
        categories: list of available category names
        templates:  list of template objects
    """
    templates = _TEMPLATES
    if category:
        templates = [t for t in templates if t["category"].lower() == category.lower()]
    return {
        "categories": _CATEGORIES,
        "count": len(templates),
        "templates": templates,
    }


@router.get("/api/templates/{template_id}")
async def get_template(template_id: str):
    """Return a single template by ID."""
    t = _BY_ID.get(template_id)
    if t is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return t
