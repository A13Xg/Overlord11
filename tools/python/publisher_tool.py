"""
Overlord11 - Publisher Tool v2.0
=================================
Generates fully self-contained styled HTML reports from structured content.

Automatically selects a visual theme based on subject matter and produces
a single .html file with all CSS and optional inline JS included.

Theme priority order (preferred first):
  Premium:  ultraviolet, aurora, neobrutalism
  Standard: techno, modern, editorial, tactical, contemporary, abstract
  Basic:    classic, informative, colorful

Usage:
    python publisher_tool.py --title "Q1 Analysis" --content report.md --theme aurora
    python publisher_tool.py --title "Security Audit" --content data.txt --theme tactical --output report.html
    python publisher_tool.py --help
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    from log_manager import log_tool_invocation, log_error
    HAS_LOG = True
except ImportError:
    HAS_LOG = False

# Maximum characters for a filename slug derived from the report title
MAX_SLUG_LENGTH = 40

# Inline SVG data URI for the hero background pattern (subtle dot grid)
_HERO_PATTERN_URI = (
    "url(\"data:image/svg+xml,"
    "%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E"
    "%3Cg fill='none' fill-rule='evenodd'%3E"
    "%3Cg fill='%23ffffff' fill-opacity='0.04'%3E"
    "%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4z"
    "M6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E"
    "%3C/g%3E%3C/g%3E%3C/svg%3E\")"
)


# ---------------------------------------------------------------------------
# Theme definitions
# ---------------------------------------------------------------------------

THEMES = {
    "techno": {
        "bg": "#0d1117",
        "surface": "#161b22",
        "surface2": "#21262d",
        "primary": "#00d4aa",
        "secondary": "#58a6ff",
        "accent": "#f78166",
        "text": "#e6edf3",
        "text_muted": "#8b949e",
        "border": "#30363d",
        "heading_font": "'Courier New', 'Consolas', monospace",
        "body_font": "'Segoe UI', 'Helvetica Neue', sans-serif",
        "hero_gradient": "linear-gradient(135deg, #0d1117 0%, #1a2332 100%)",
        "metric_bg": "#21262d",
        "metric_accent": "#00d4aa",
        "tag": "TECHNICAL",
    },
    "classic": {
        "bg": "#fafafa",
        "surface": "#ffffff",
        "surface2": "#f5f5f0",
        "primary": "#1a1a2e",
        "secondary": "#16213e",
        "accent": "#c0392b",
        "text": "#2c2c2c",
        "text_muted": "#6b6b6b",
        "border": "#ddd",
        "heading_font": "'Georgia', 'Times New Roman', serif",
        "body_font": "'Palatino Linotype', 'Georgia', serif",
        "hero_gradient": "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)",
        "metric_bg": "#f0ede6",
        "metric_accent": "#c0392b",
        "tag": "REPORT",
    },
    "informative": {
        "bg": "#f8f9fa",
        "surface": "#ffffff",
        "surface2": "#e9ecef",
        "primary": "#1565c0",
        "secondary": "#0d47a1",
        "accent": "#f57c00",
        "text": "#212529",
        "text_muted": "#6c757d",
        "border": "#dee2e6",
        "heading_font": "'Source Serif Pro', Georgia, serif",
        "body_font": "'Source Sans Pro', 'Helvetica Neue', sans-serif",
        "hero_gradient": "linear-gradient(135deg, #1565c0 0%, #0d47a1 100%)",
        "metric_bg": "#e3f2fd",
        "metric_accent": "#1565c0",
        "tag": "RESEARCH",
    },
    "contemporary": {
        "bg": "#f0faf4",
        "surface": "#ffffff",
        "surface2": "#e8f5e9",
        "primary": "#00695c",
        "secondary": "#00796b",
        "accent": "#ff6f00",
        "text": "#1b2e2a",
        "text_muted": "#607d8b",
        "border": "#b2dfdb",
        "heading_font": "'Nunito', 'Helvetica Neue', sans-serif",
        "body_font": "'Open Sans', 'Helvetica Neue', sans-serif",
        "hero_gradient": "linear-gradient(135deg, #00695c 0%, #26a69a 100%)",
        "metric_bg": "#e0f2f1",
        "metric_accent": "#00695c",
        "tag": "ANALYSIS",
    },
    "abstract": {
        "bg": "#0f0f23",
        "surface": "#1a1a3e",
        "surface2": "#252545",
        "primary": "#ff6b6b",
        "secondary": "#ffd166",
        "accent": "#06d6a0",
        "text": "#eeeeff",
        "text_muted": "#aaaacc",
        "border": "#3a3a6e",
        "heading_font": "'Impact', 'Arial Black', sans-serif",
        "body_font": "'Trebuchet MS', 'Helvetica Neue', sans-serif",
        "hero_gradient": "linear-gradient(135deg, #ff6b6b 0%, #ffd166 50%, #06d6a0 100%)",
        "metric_bg": "#252545",
        "metric_accent": "#ffd166",
        "tag": "CREATIVE",
    },
    "modern": {
        "bg": "#f8f8ff",
        "surface": "#ffffff",
        "surface2": "#f0f0ff",
        "primary": "#6c63ff",
        "secondary": "#5a52cc",
        "accent": "#ff6584",
        "text": "#2d2d3a",
        "text_muted": "#7a7a8c",
        "border": "#e0e0ff",
        "heading_font": "'Inter', 'SF Pro Display', 'Helvetica Neue', sans-serif",
        "body_font": "'Inter', 'SF Pro Text', 'Helvetica Neue', sans-serif",
        "hero_gradient": "linear-gradient(135deg, #6c63ff 0%, #a78bfa 100%)",
        "metric_bg": "#f0f0ff",
        "metric_accent": "#6c63ff",
        "tag": "INSIGHTS",
    },
    "colorful": {
        "bg": "#fff9f0",
        "surface": "#ffffff",
        "surface2": "#fff3e0",
        "primary": "#e64980",
        "secondary": "#f59f00",
        "accent": "#20c997",
        "text": "#1a1a2e",
        "text_muted": "#666",
        "border": "#ffd6a5",
        "heading_font": "'Fredoka One', 'Comic Sans MS', 'Helvetica Neue', cursive",
        "body_font": "'Nunito', 'Helvetica Neue', sans-serif",
        "hero_gradient": "linear-gradient(135deg, #e64980 0%, #f59f00 50%, #20c997 100%)",
        "metric_bg": "#fff0f6",
        "metric_accent": "#e64980",
        "tag": "FUN",
    },
    "tactical": {
        "bg": "#0a0a0a",
        "surface": "#111111",
        "surface2": "#1a1a1a",
        "primary": "#cc0000",
        "secondary": "#ff3333",
        "accent": "#ff9500",
        "text": "#dddddd",
        "text_muted": "#888888",
        "border": "#333333",
        "heading_font": "'Arial Black', 'Impact', sans-serif",
        "body_font": "'Courier New', monospace",
        "hero_gradient": "linear-gradient(135deg, #1a0000 0%, #0a0a0a 100%)",
        "metric_bg": "#1a1a1a",
        "metric_accent": "#cc0000",
        "tag": "INTEL",
    },
    "editorial": {
        "bg": "#fdf6e3",
        "surface": "#fdf6e3",
        "surface2": "#f5ead0",
        "primary": "#2c1a00",
        "secondary": "#5c3a00",
        "accent": "#c0392b",
        "text": "#2c1a00",
        "text_muted": "#8b7355",
        "border": "#d4b896",
        "heading_font": "'Playfair Display', 'Georgia', 'Times New Roman', serif",
        "body_font": "'Lora', 'Georgia', serif",
        "hero_gradient": "linear-gradient(135deg, #2c1a00 0%, #5c3a00 100%)",
        "metric_bg": "#f5ead0",
        "metric_accent": "#c0392b",
        "tag": "EDITORIAL",
    },
    # ── Premium themes (from design system skills/uiux) ──────────────────────
    "ultraviolet": {
        "bg": "#0e0a1a",
        "surface": "#150e28",
        "surface2": "#1e1538",
        "primary": "#a855f7",
        "secondary": "#7c3aed",
        "accent": "#c084fc",
        "text": "#e8e0f8",
        "text_muted": "#8070a8",
        "border": "#2e2050",
        "heading_font": "'Segoe UI', 'DM Sans', system-ui, sans-serif",
        "body_font": "'Segoe UI', 'DM Sans', system-ui, sans-serif",
        "hero_gradient": "linear-gradient(135deg, #0e0a1a 0%, #1e1040 50%, #150e28 100%)",
        "metric_bg": "#1e1538",
        "metric_accent": "#a855f7",
        "tag": "AI",
    },
    "aurora": {
        "bg": "#060b14",
        "surface": "#0d1626",
        "surface2": "#142038",
        "primary": "#38bdf8",
        "secondary": "#818cf8",
        "accent": "#34d399",
        "text": "#e2e8f0",
        "text_muted": "#64748b",
        "border": "#1e3a5f",
        "heading_font": "'Segoe UI', system-ui, sans-serif",
        "body_font": "'Segoe UI', system-ui, sans-serif",
        "hero_gradient": "linear-gradient(135deg, #060b14 0%, #0a1628 40%, #0d2040 100%)",
        "metric_bg": "#0d1e38",
        "metric_accent": "#38bdf8",
        "tag": "LIVE",
    },
    "neobrutalism": {
        "bg": "#fffbf5",
        "surface": "#ffffff",
        "surface2": "#fef3e2",
        "primary": "#b84a0c",
        "secondary": "#d4860a",
        "accent": "#1a7a4a",
        "text": "#2d1f0e",
        "text_muted": "#7a5c3a",
        "border": "#2d1f0e",
        "heading_font": "'Arial Black', 'Impact', system-ui, sans-serif",
        "body_font": "'Segoe UI', system-ui, sans-serif",
        "hero_gradient": "linear-gradient(135deg, #b84a0c 0%, #d4860a 100%)",
        "metric_bg": "#fef3e2",
        "metric_accent": "#b84a0c",
        "tag": "BOLD",
        "neobrutalism": True,
    },
}


# ---------------------------------------------------------------------------
# Theme auto-detection
# ---------------------------------------------------------------------------

_THEME_KEYWORDS = {
    # ── Premium themes (preferred in auto-detection) ──────────────────────────
    "ultraviolet": [
        "ai", "artificial intelligence", "machine learning", "llm", "neural",
        "agent", "automation", "saas", "platform", "cloud", "api", "tool",
        "assistant", "copilot", "model", "inference", "generative",
    ],
    "aurora": [
        "dashboard", "analytics", "metrics", "monitoring", "telemetry", "log",
        "real-time", "live", "stream", "pipeline", "workflow", "orchestration",
        "ops", "devops", "infrastructure", "observability", "alert", "chart",
    ],
    "neobrutalism": [
        "startup", "product", "launch", "brand", "marketing", "landing",
        "campaign", "pitch", "deck", "manifesto", "vision", "strategy",
        "growth", "traction", "mvp", "founder", "venture",
    ],
    # ── Standard themes ───────────────────────────────────────────────────────
    "techno": [
        "code", "software", "programming", "algorithm", "docker", "kubernetes",
        "python", "javascript", "typescript", "rust", "golang", "linux", "server",
        "database", "sql", "git", "ci/cd", "microservice", "architecture",
        "engineering", "framework", "library", "terminal", "cli", "debug", "compiler",
    ],
    "classic": [
        "business", "finance", "revenue", "profit", "investment", "strategy", "executive",
        "quarterly", "annual", "board", "corporate", "legal", "compliance", "audit",
        "policy", "regulation", "contract", "proposal", "shareholder",
    ],
    "informative": [
        "research", "study", "analysis", "data", "statistics", "methodology", "findings",
        "academic", "paper", "journal", "hypothesis", "experiment", "survey", "sample",
        "correlation", "regression", "peer review", "citation", "bibliography",
    ],
    "contemporary": [
        "health", "wellness", "environment", "sustainability", "climate", "science",
        "medicine", "biology", "ecology", "nutrition", "fitness", "mental health",
        "green", "renewable", "nature", "ecosystem",
    ],
    "abstract": [
        "art", "design", "creative", "culture", "music", "film", "photography",
        "fashion", "aesthetic", "avant-garde", "conceptual", "artistic", "visual",
        "gallery", "exhibition", "portfolio",
    ],
    "modern": [
        "innovation", "user", "ux", "ui", "mobile", "consumer",
        "engagement", "conversion", "funnel", "product design",
    ],
    "colorful": [
        "education", "kids", "children", "school", "learning", "fun", "game",
        "toy", "cartoon", "playful", "youth", "student", "teacher", "class",
        "tutorial", "lesson",
    ],
    "tactical": [
        "security", "threat", "vulnerability", "attack", "defense", "breach",
        "incident", "malware", "ransomware", "penetration", "cyber", "risk",
        "intelligence", "infrastructure", "military", "operations",
    ],
    "editorial": [
        "news", "journalism", "story", "narrative", "history", "politics",
        "interview", "feature", "opinion", "editorial", "report", "chronicle",
        "investigation", "documentary",
    ],
}


def _detect_theme(title: str, content: str) -> str:
    """Auto-detect the best theme, preferring premium themes over basic ones.

    Premium themes (ultraviolet, aurora, neobrutalism) receive a 2× score
    multiplier. When scores tie, the first premium theme wins.  When no
    keywords match at all, falls back to 'aurora' (visually strong default).
    """
    _PREMIUM = {"ultraviolet", "aurora", "neobrutalism"}
    combined = (title + " " + content).lower()
    scores = {theme: 0 for theme in _THEME_KEYWORDS}
    for theme, keywords in _THEME_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                # Premium themes get double weight
                scores[theme] += 2 if theme in _PREMIUM else 1
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "aurora"  # visually impressive default
    return best


# ---------------------------------------------------------------------------
# Markdown → HTML conversion (lightweight, no deps)
# ---------------------------------------------------------------------------

def _md_to_html(text: str) -> str:
    """Convert basic Markdown to HTML. No external dependencies."""
    # Code blocks (``` ... ```)
    text = re.sub(
        r"```(\w*)\n(.*?)```",
        lambda m: f'<pre><code class="lang-{m.group(1)}">{_escape_html(m.group(2))}</code></pre>',
        text, flags=re.DOTALL
    )
    # Inline code
    text = re.sub(r"`([^`]+)`", lambda m: f'<code>{_escape_html(m.group(1))}</code>', text)
    # Headers
    text = re.sub(r"^# (.+)$", r"<h1>\1</h1>", text, flags=re.MULTILINE)
    text = re.sub(r"^## (.+)$", r"<h2>\1</h2>", text, flags=re.MULTILINE)
    text = re.sub(r"^### (.+)$", r"<h3>\1</h3>", text, flags=re.MULTILINE)
    text = re.sub(r"^#### (.+)$", r"<h4>\1</h4>", text, flags=re.MULTILINE)
    # Bold and italic
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"_(.+?)_", r"<em>\1</em>", text)
    # Tables
    text = _convert_tables(text)
    # Unordered lists
    text = re.sub(
        r"((?:^[-*+] .+\n?)+)",
        lambda m: "<ul>" + re.sub(r"^[-*+] (.+)$", r"<li>\1</li>", m.group(0), flags=re.MULTILINE) + "</ul>",
        text, flags=re.MULTILINE
    )
    # Ordered lists
    text = re.sub(
        r"((?:^\d+\. .+\n?)+)",
        lambda m: "<ol>" + re.sub(r"^\d+\. (.+)$", r"<li>\1</li>", m.group(0), flags=re.MULTILINE) + "</ol>",
        text, flags=re.MULTILINE
    )
    # Blockquotes
    text = re.sub(r"^> (.+)$", r"<blockquote>\1</blockquote>", text, flags=re.MULTILINE)
    # Horizontal rules
    text = re.sub(r"^---+$", "<hr>", text, flags=re.MULTILINE)
    # Links
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    # Paragraphs — wrap consecutive non-tag lines
    lines = text.split("\n")
    result = []
    para_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if para_lines:
                result.append("<p>" + " ".join(para_lines) + "</p>")
                para_lines = []
        elif stripped.startswith("<"):
            if para_lines:
                result.append("<p>" + " ".join(para_lines) + "</p>")
                para_lines = []
            result.append(stripped)
        else:
            para_lines.append(stripped)
    if para_lines:
        result.append("<p>" + " ".join(para_lines) + "</p>")
    return "\n".join(result)


def _escape_html(text: str) -> str:
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))


def _convert_tables(text: str) -> str:
    """Convert Markdown tables to HTML tables."""
    table_pattern = re.compile(
        r"((?:^\|.+\|\n)+)",
        re.MULTILINE
    )
    def _table_replace(m):
        rows = [r.strip() for r in m.group(1).strip().split("\n")]
        if len(rows) < 2:
            return m.group(0)
        html = ['<div class="table-wrap"><table>']
        for i, row in enumerate(rows):
            if re.match(r"^\|[-:| ]+\|$", row):
                continue
            cells = [c.strip() for c in row.strip("|").split("|")]
            if i == 0:
                html.append("<thead><tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr></thead><tbody>")
            else:
                html.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
        html.append("</tbody></table></div>")
        return "\n".join(html)
    return table_pattern.sub(_table_replace, text)


# ---------------------------------------------------------------------------
# CSS generation per theme
# ---------------------------------------------------------------------------

def _build_css(t: dict) -> str:
    # Extra CSS injected for the neobrutalism premium theme
    neobrutalism_extra = ""
    if t.get("neobrutalism"):
        neobrutalism_extra = """
/* ── Neo-Brutalism overrides ── */
.section, .card, .exec-summary {
  border: 2px solid var(--color-border);
  box-shadow: 5px 5px 0 var(--color-border);
  border-radius: 4px;
}
.section:hover, .card:hover {
  transform: translate(-2px, -2px);
  box-shadow: 7px 7px 0 var(--color-border);
}
.btn, button { border: 2px solid var(--color-border); box-shadow: 3px 3px 0 var(--color-border); }
.btn:hover, button:hover { transform: translate(-1px,-1px); box-shadow: 4px 4px 0 var(--color-border); }
h1, h2 { text-transform: uppercase; letter-spacing: .04em; }
"""
    return f"""
:root {{
  --color-bg:        {t['bg']};
  --color-surface:   {t['surface']};
  --color-surface2:  {t['surface2']};
  --color-primary:   {t['primary']};
  --color-secondary: {t['secondary']};
  --color-accent:    {t['accent']};
  --color-text:      {t['text']};
  --color-muted:     {t['text_muted']};
  --color-border:    {t['border']};
  --color-metric-bg: {t['metric_bg']};
  --color-metric:    {t['metric_accent']};
  --font-heading:    {t['heading_font']};
  --font-body:       {t['body_font']};
}}
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ font-size: 16px; scroll-behavior: smooth; }}
body {{
  background: var(--color-bg);
  color: var(--color-text);
  font-family: var(--font-body);
  line-height: 1.7;
  min-height: 100vh;
}}
a {{ color: var(--color-primary); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}

/* ── Typography ── */
h1, h2, h3, h4, h5 {{
  font-family: var(--font-heading);
  color: var(--color-primary);
  line-height: 1.25;
  margin-bottom: 0.5em;
}}
h1 {{ font-size: 2.4rem; }}
h2 {{ font-size: 1.7rem; margin-top: 2rem; padding-bottom: 0.3rem; border-bottom: 2px solid var(--color-border); }}
h3 {{ font-size: 1.25rem; margin-top: 1.5rem; color: var(--color-secondary); }}
h4 {{ font-size: 1rem; color: var(--color-muted); text-transform: uppercase; letter-spacing: .08em; }}
p {{ margin-bottom: 1rem; max-width: 72ch; }}
code {{
  background: var(--color-surface2);
  color: var(--color-accent);
  padding: 0.15em 0.4em;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 0.88em;
}}
pre {{
  background: var(--color-surface2);
  border-left: 4px solid var(--color-primary);
  padding: 1rem 1.25rem;
  overflow-x: auto;
  border-radius: 6px;
  margin: 1.25rem 0;
}}
pre code {{ background: none; padding: 0; color: var(--color-text); font-size: 0.85rem; }}
blockquote {{
  border-left: 4px solid var(--color-primary);
  padding: 0.75rem 1.25rem;
  margin: 1.25rem 0;
  background: var(--color-surface2);
  border-radius: 0 6px 6px 0;
  color: var(--color-muted);
  font-style: italic;
}}
ul, ol {{ padding-left: 1.5rem; margin-bottom: 1rem; }}
li {{ margin-bottom: 0.3rem; }}
hr {{ border: none; border-top: 1px solid var(--color-border); margin: 2rem 0; }}
strong {{ color: var(--color-text); }}

/* ── Layout ── */
.container {{ max-width: 1100px; margin: 0 auto; padding: 0 1.5rem; }}

/* ── Hero ── */
.hero {{
  background: {t['hero_gradient']};
  color: #fff;
  padding: 4rem 2rem;
  text-align: center;
  position: relative;
  overflow: hidden;
}}
.hero::before {{
  content: '';
  position: absolute;
  inset: 0;
  background: {_HERO_PATTERN_URI};
  opacity: 0.5;
}}
.hero-inner {{ position: relative; z-index: 1; }}
.hero h1 {{ color: #fff; font-size: 2.8rem; text-shadow: 0 2px 8px rgba(0,0,0,0.4); }}
.hero .subtitle {{ font-size: 1.15rem; opacity: 0.88; margin-top: 0.75rem; max-width: 65ch; margin-left: auto; margin-right: auto; }}
.hero-meta {{ margin-top: 1.25rem; opacity: 0.7; font-size: 0.85rem; display: flex; gap: 1.5rem; justify-content: center; flex-wrap: wrap; }}
.badge {{
  display: inline-block;
  background: rgba(255,255,255,0.15);
  border: 1px solid rgba(255,255,255,0.3);
  padding: 0.25rem 0.75rem;
  border-radius: 100px;
  font-size: 0.75rem;
  letter-spacing: .1em;
  text-transform: uppercase;
  font-weight: 700;
  color: #fff;
  margin-bottom: 1rem;
}}

/* ── Metrics Bar ── */
.metrics-bar {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
  padding: 1.5rem;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
}}
.metric-item {{
  text-align: center;
  background: var(--color-metric-bg);
  border-radius: 10px;
  padding: 1rem;
  border: 1px solid var(--color-border);
}}
.metric-value {{
  font-family: var(--font-heading);
  font-size: 2rem;
  font-weight: 700;
  color: var(--color-metric);
  line-height: 1;
}}
.metric-unit {{ font-size: 0.85rem; color: var(--color-muted); }}
.metric-label {{ font-size: 0.78rem; text-transform: uppercase; letter-spacing: .08em; color: var(--color-muted); margin-top: 0.4rem; }}

/* ── Main Content ── */
.content {{
  padding: 2.5rem 0;
}}
.section {{
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 2rem;
  margin-bottom: 1.75rem;
}}

/* ── Executive Summary ── */
.exec-summary {{
  background: var(--color-surface);
  border-left: 5px solid var(--color-primary);
  padding: 1.5rem 2rem;
  margin-bottom: 2rem;
  border-radius: 0 10px 10px 0;
}}
.exec-summary h2 {{ border: none; margin-top: 0; }}
.exec-summary p {{ font-size: 1.05rem; max-width: 100%; }}

/* ── Tables ── */
.table-wrap {{ overflow-x: auto; margin: 1.25rem 0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; }}
thead {{ background: var(--color-primary); color: #fff; }}
th {{ padding: 0.75rem 1rem; text-align: left; font-family: var(--font-heading); font-size: 0.82rem; text-transform: uppercase; letter-spacing: .06em; }}
td {{ padding: 0.65rem 1rem; border-bottom: 1px solid var(--color-border); }}
tr:last-child td {{ border-bottom: none; }}
tr:hover td {{ background: var(--color-surface2); }}

/* ── CSS Bar Charts ── */
.chart-container {{ margin: 1.5rem 0; }}
.chart-row {{
  display: grid;
  grid-template-columns: 180px 1fr 60px;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.6rem;
}}
.chart-label {{ font-size: 0.85rem; color: var(--color-muted); text-align: right; }}
.chart-track {{
  background: var(--color-surface2);
  border-radius: 100px;
  height: 18px;
  overflow: hidden;
  position: relative;
}}
.chart-fill {{
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary), var(--color-secondary));
  border-radius: 100px;
  transition: width 0.6s ease;
}}
.chart-val {{ font-size: 0.85rem; font-weight: 700; color: var(--color-primary); }}

/* ── Callout ── */
.callout {{
  background: var(--color-surface2);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 1rem 1.25rem;
  margin: 1.25rem 0;
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
}}
.callout-icon {{ font-size: 1.25rem; flex-shrink: 0; }}
.callout-body {{ font-size: 0.95rem; }}

/* ── Card Grid ── */
.card-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 1.25rem;
  margin: 1.25rem 0;
}}
.card {{
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 1.25rem;
  transition: box-shadow 0.2s;
}}
.card:hover {{ box-shadow: 0 4px 20px rgba(0,0,0,0.12); }}
.card h4 {{ margin-bottom: 0.5rem; color: var(--color-primary); font-size: 0.95rem; }}

/* ── Timeline ── */
.timeline {{ margin: 1.25rem 0; position: relative; padding-left: 2rem; }}
.timeline::before {{ content: ''; position: absolute; left: 7px; top: 0; bottom: 0; width: 2px; background: var(--color-border); }}
.timeline-item {{ position: relative; margin-bottom: 1.5rem; }}
.timeline-item::before {{
  content: '';
  position: absolute;
  left: -1.75rem;
  top: 0.35rem;
  width: 12px;
  height: 12px;
  background: var(--color-primary);
  border-radius: 50%;
  border: 2px solid var(--color-bg);
}}
.timeline-date {{ font-size: 0.78rem; text-transform: uppercase; letter-spacing: .08em; color: var(--color-muted); margin-bottom: 0.25rem; }}
.timeline-content {{ font-size: 0.95rem; }}

/* ── Footer ── */
.footer {{
  background: var(--color-surface2);
  border-top: 1px solid var(--color-border);
  padding: 2rem;
  margin-top: 3rem;
  font-size: 0.82rem;
  color: var(--color-muted);
}}
.footer a {{ color: var(--color-muted); }}
.footer-inner {{ max-width: 1100px; margin: 0 auto; display: flex; flex-wrap: wrap; justify-content: space-between; gap: 1rem; }}
.sources-list {{ list-style: none; padding: 0; }}
.sources-list li {{ margin-bottom: 0.3rem; }}
.sources-list a {{ word-break: break-all; }}
.footer-brand {{ font-weight: 700; color: var(--color-primary); }}

/* ── Print ── */
@media print {{
  .hero {{ background: var(--color-primary); -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  .section {{ break-inside: avoid; box-shadow: none; border: 1px solid #ccc; }}
  body {{ background: white; color: black; }}
}}

/* ── Responsive ── */
@media (max-width: 640px) {{
  .hero {{ padding: 2.5rem 1rem; }}
  .hero h1 {{ font-size: 1.8rem; }}
  .metrics-bar {{ grid-template-columns: repeat(2, 1fr); }}
  .chart-row {{ grid-template-columns: 100px 1fr 50px; }}
  h1 {{ font-size: 1.8rem; }}
  h2 {{ font-size: 1.35rem; }}
}}
{neobrutalism_extra}
"""


# ---------------------------------------------------------------------------
# HTML assembly
# ---------------------------------------------------------------------------

def _build_html(
    title: str,
    subtitle: str,
    content_html: str,
    theme_name: str,
    theme: dict,
    metrics: list,
    sources: list,
    author: str,
    generated_at: str,
) -> str:
    """Assemble the full self-contained HTML document."""
    css = _build_css(theme)

    # Metrics bar
    metrics_html = ""
    if metrics:
        items = ""
        for m in metrics:
            unit = m.get("unit", "")
            items += f"""
        <div class="metric-item">
          <div class="metric-value">{m['value']}<span class="metric-unit">{unit}</span></div>
          <div class="metric-label">{m['label']}</div>
        </div>"""
        metrics_html = f'<div class="container"><div class="metrics-bar">{items}\n      </div></div>'

    # Sources footer section
    sources_html = ""
    if sources:
        items = "".join(
            f'<li><a href="{s}" target="_blank">{s}</a></li>' if s.startswith("http")
            else f"<li>{s}</li>"
            for s in sources
        )
        sources_html = f"""
      <div>
        <strong>Sources</strong>
        <ul class="sources-list">{items}</ul>
      </div>"""

    author_str = f"<span>By {author}</span>" if author else ""
    subtitle_str = f'<p class="subtitle">{subtitle}</p>' if subtitle else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_escape_html(title)}</title>
  <style>{css}</style>
</head>
<body>

<header class="hero">
  <div class="hero-inner container">
    <div class="badge">{theme['tag']}</div>
    <h1>{_escape_html(title)}</h1>
    {subtitle_str}
    <div class="hero-meta">
      {author_str}
      <span>Generated {generated_at}</span>
      <span>Theme: {theme_name.title()}</span>
    </div>
  </div>
</header>

{metrics_html}

<main class="container content">
{content_html}
</main>

<footer class="footer">
  <div class="footer-inner">
    {sources_html}
    <div>
      <div class="footer-brand">Overlord11</div>
      <div>Generated {generated_at}</div>
    </div>
  </div>
</footer>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Content → structured HTML sections
# ---------------------------------------------------------------------------

def _content_to_html(content: str, sections: list) -> str:
    """Convert content + optional section overrides to HTML body."""
    html_parts = []

    if sections:
        # Fine-grained section control
        for sec in sections:
            heading = sec.get("heading", "")
            body = sec.get("body", "")
            sec_type = sec.get("type", "prose")

            if heading.lower() in ("executive summary", "summary", "overview") or sec_type == "callout":
                html_parts.append(
                    f'<div class="exec-summary">\n'
                    f'<h2>{_escape_html(heading)}</h2>\n'
                    f'{_md_to_html(body)}\n</div>'
                )
            else:
                body_html = _md_to_html(body)
                html_parts.append(
                    f'<section class="section">\n'
                    f'<h2>{_escape_html(heading)}</h2>\n'
                    f'{body_html}\n</section>'
                )
    else:
        # Auto-parse content — split on h2 boundaries
        # First, extract executive summary if present
        exec_match = re.search(
            r"(?:^|\n)#{1,2}\s*(?:executive summary|summary|overview)\s*\n+(.*?)(?=\n#|\Z)",
            content, re.I | re.DOTALL
        )
        if exec_match:
            exec_body = exec_match.group(1).strip()
            html_parts.append(
                f'<div class="exec-summary">\n'
                f'<h2>Executive Summary</h2>\n'
                f'{_md_to_html(exec_body)}\n</div>'
            )
            # Remove from content
            content = content[:exec_match.start()] + content[exec_match.end():]

        # Split remaining content into sections at h2 boundaries
        chunks = re.split(r"\n(?=## )", content.strip())
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            h2_match = re.match(r"## (.+)\n", chunk)
            if h2_match:
                sec_title = h2_match.group(1).strip()
                sec_body = chunk[h2_match.end():].strip()
                html_parts.append(
                    f'<section class="section">\n'
                    f'<h2>{_escape_html(sec_title)}</h2>\n'
                    f'{_md_to_html(sec_body)}\n</section>'
                )
            else:
                html_parts.append(
                    f'<section class="section">\n'
                    f'{_md_to_html(chunk)}\n</section>'
                )

    return "\n\n".join(html_parts)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_report(
    title: str,
    content: str,
    subtitle: str = "",
    theme: str = "auto",
    sections: list = None,
    metrics: list = None,
    sources: list = None,
    output_path: str = "",
    author: str = "",
    session_id: str = "",
) -> dict:
    """Generate a styled self-contained HTML report.

    Returns dict with keys: success, file_path, theme_used, sections_count, file_size_bytes, error
    """
    try:
        # Resolve theme
        if theme == "auto" or theme not in THEMES:
            theme_name = _detect_theme(title, content)
        else:
            theme_name = theme
        theme_def = THEMES[theme_name]

        # Build content HTML
        content_html = _content_to_html(content, sections or [])

        # Timestamps
        now = datetime.now()
        generated_at = now.strftime("%B %d, %Y at %H:%M")
        ts = now.strftime("%Y%m%d_%H%M%S")

        # Slug for filename (length capped to keep paths readable)
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower())[:MAX_SLUG_LENGTH].strip("_")

        # Output path
        if not output_path:
            reports_dir = Path("workspace") / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(reports_dir / f"{ts}_{slug}.html")
        else:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Build HTML
        html = _build_html(
            title=title,
            subtitle=subtitle,
            content_html=content_html,
            theme_name=theme_name,
            theme=theme_def,
            metrics=metrics or [],
            sources=sources or [],
            author=author,
            generated_at=generated_at,
        )

        # Write file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        file_size = os.path.getsize(output_path)
        sections_count = content_html.count("<section") + content_html.count("exec-summary")

        result = {
            "success": True,
            "file_path": output_path,
            "theme_used": theme_name,
            "sections_count": sections_count,
            "file_size_bytes": file_size,
            "generated_at": generated_at,
        }

        if HAS_LOG and session_id:
            log_tool_invocation(
                session_id=session_id,
                tool_name="publisher_tool",
                params={"title": title, "theme": theme, "output_path": output_path},
                result=result,
            )

        return result

    except Exception as exc:
        error_result = {"success": False, "error": str(exc)}
        if HAS_LOG and session_id:
            log_error(session_id=session_id, source="publisher_tool", error=str(exc))
        return error_result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args():
    p = argparse.ArgumentParser(
        description="Generate a styled self-contained HTML report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--title", required=True, help="Report title")
    p.add_argument("--content", required=True,
                   help="Content as a string, or a file path ending in .md/.txt")
    p.add_argument("--subtitle", default="", help="Optional subtitle")
    p.add_argument("--theme", default="auto",
                   choices=["auto"] + list(THEMES.keys()),
                   help="Visual theme (default: auto-detect)")
    p.add_argument("--output", default="", help="Output file path (default: workspace/reports/...)")
    p.add_argument("--author", default="", help="Author name")
    p.add_argument("--sources", nargs="*", default=[], help="Source URLs or references")
    p.add_argument("--metrics", nargs="*", default=[],
                   help='Key metrics as JSON strings: \'{"label":"Users","value":"1,234"}\'')
    p.add_argument("--session_id", default="", help="Session ID for logging")
    return p.parse_args()


def main():
    args = _parse_args()

    # Load content from file or use inline string
    content = args.content
    if content.endswith((".md", ".txt")) and os.path.isfile(content):
        with open(content, "r", encoding="utf-8") as f:
            content = f.read()

    # Parse metrics JSON strings
    metrics = []
    for m_str in (args.metrics or []):
        try:
            metrics.append(json.loads(m_str))
        except json.JSONDecodeError:
            pass  # skip malformed

    result = generate_report(
        title=args.title,
        content=content,
        subtitle=args.subtitle,
        theme=args.theme,
        metrics=metrics,
        sources=args.sources or [],
        output_path=args.output,
        author=args.author,
        session_id=args.session_id,
    )

    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
