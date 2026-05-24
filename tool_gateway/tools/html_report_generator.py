"""
HTML Report Generator tool — produce styled, self-contained HTML reports
from markdown or plain text, using the project's UI/UX design system.
"""
from __future__ import annotations

import json
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .base import BaseTool
from .web_common import resolve_workspace_path, workspace_root

# ---------------------------------------------------------------------------
# Locate design system assets
# ---------------------------------------------------------------------------

_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "agents" / "skills" / "uiux"


def _load_palettes() -> list[dict]:
    p = _SKILLS_DIR / "palettes.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return []


def _load_styles() -> list[dict]:
    p = _SKILLS_DIR / "styles.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return []


# ---------------------------------------------------------------------------
# Minimal Markdown → HTML converter (no external deps)
# ---------------------------------------------------------------------------

def _md_to_html(md: str) -> tuple[str, list[dict[str, str]]]:
    """
    Converts a subset of Markdown to HTML.
    Returns (html_body, toc_items) where toc_items = [{id, level, text}, ...].
    """
    lines = md.splitlines()
    out: list[str] = []
    toc: list[dict[str, str]] = []
    in_code = False
    in_ul = False
    in_ol = False
    in_table = False
    slug_counts: dict[str, int] = {}

    def close_list():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def close_table():
        nonlocal in_table
        if in_table:
            out.append("</tbody></table>")
            in_table = False

    def make_slug(text: str) -> str:
        base = re.sub(r"[^\w\s-]", "", text.lower()).strip()
        slug = re.sub(r"[\s]+", "-", base)
        n = slug_counts.get(slug, 0)
        slug_counts[slug] = n + 1
        return slug if n == 0 else f"{slug}-{n}"

    def inline(text: str) -> str:
        # Bold **text** or __text__
        text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", text)
        # Italic *text* or _text_
        text = re.sub(r"\*(.+?)\*|_(.+?)_", lambda m: f"<em>{m.group(1) or m.group(2)}</em>", text)
        # Inline code `code`
        text = re.sub(r"`(.+?)`", lambda m: f'<code>{_escape(m.group(1))}</code>', text)
        # Links [text](url)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
        return text

    def _escape(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    table_header_row = True

    for line in lines:
        stripped = line.rstrip()

        # Fenced code blocks
        if stripped.startswith("```"):
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                close_list()
                close_table()
                lang = stripped[3:].strip()
                lang_attr = f' class="language-{_escape(lang)}"' if lang else ""
                out.append(f"<pre><code{lang_attr}>")
                in_code = True
            continue
        if in_code:
            out.append(_escape(stripped))
            continue

        # Headings
        m = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if m:
            close_list()
            close_table()
            level = len(m.group(1))
            text = inline(m.group(2).strip())
            slug = make_slug(re.sub(r"<[^>]+>", "", text))
            toc.append({"id": slug, "level": str(level), "text": re.sub(r"<[^>]+>", "", text)})
            out.append(f'<h{level} id="{slug}">{text}</h{level}>')
            continue

        # Horizontal rule
        if re.match(r"^[-*_]{3,}\s*$", stripped):
            close_list()
            close_table()
            out.append("<hr>")
            continue

        # Blockquote
        if stripped.startswith("> "):
            close_list()
            close_table()
            out.append(f'<blockquote>{inline(stripped[2:])}</blockquote>')
            continue

        # Tables (simple | col | col | syntax)
        if "|" in stripped and not stripped.startswith("|-"):
            cols = [c.strip() for c in stripped.strip("|").split("|")]
            if not in_table:
                close_list()
                out.append('<table><thead><tr>' + "".join(f"<th>{inline(c)}</th>" for c in cols) + '</tr></thead><tbody>')
                in_table = True
                table_header_row = False
            else:
                out.append('<tr>' + "".join(f"<td>{inline(c)}</td>" for c in cols) + '</tr>')
            continue
        elif in_table and stripped.startswith("|-"):
            # Skip separator row
            continue
        else:
            close_table()

        # Unordered list
        if re.match(r"^[-*+]\s+", stripped):
            if not in_ul:
                close_table()
                out.append("<ul>")
                in_ul = True
            out.append(f'<li>{inline(stripped[2:].strip())}</li>')
            continue

        # Ordered list
        if re.match(r"^\d+\.\s+", stripped):
            if not in_ol:
                close_table()
                out.append("<ol>")
                in_ol = True
            ordered_text = re.sub(r"^\d+\.\s+", "", stripped)
            out.append(f'<li>{inline(ordered_text)}</li>')
            continue

        # Blank line
        if not stripped:
            close_list()
            close_table()
            out.append("")
            continue

        # Paragraph
        close_list()
        out.append(f"<p>{inline(stripped)}</p>")

    close_list()
    close_table()
    if in_code:
        out.append("</code></pre>")

    return "\n".join(out), toc


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class HtmlReportSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    content: str

class HtmlReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)

    title: str = Field(..., min_length=1, description="Report title")
    content: str = Field("", description="Main Markdown content for the report body")
    output_path: str | None = Field(None, description="Workspace-relative path to write the HTML file")
    theme: Literal["dark", "light", "auto"] = Field("dark", description="Color theme: dark, light, or auto (follows system preference)")
    palette_id: str | None = Field(None, description="Specific palette ID from palettes.json (e.g. 'midnight-ink', 'chalk-board')")
    style_id: str | None = Field(None, description="Specific style ID from styles.json (e.g. 'glassmorphism', 'brutalist')")
    include_toc: bool = Field(True, description="Generate a table of contents from headings")
    sections: list[HtmlReportSection] | None = Field(None, description="Optional extra named sections appended after main content")


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class HtmlReportGeneratorTool(BaseTool):
    name = "html_report_generator"
    description = (
        "Generate a self-contained, styled HTML report from Markdown content. "
        "Uses the project's UI/UX design system (palettes and style guides) to produce "
        "professional-quality output. Supports dark/light/auto themes, table of contents, "
        "and optional additional named sections."
    )
    risk_level = "low"
    destructive = False
    supports_dry_run = False
    input_model = HtmlReportInput
    examples = [
        {"tool_name": "html_report_generator", "arguments": {
            "title": "Weekly Research Summary",
            "content": "## Overview\nThis week we investigated...",
            "output_path": "artifacts/reports/weekly.html",
            "theme": "dark",
        }},
    ]

    def execute(self, args: HtmlReportInput) -> dict[str, Any]:
        warnings: list[str] = []
        palettes = _load_palettes()
        styles = _load_styles()

        # Pick palette
        palette = self._pick_palette(palettes, args.palette_id, args.theme, warnings)
        # Pick style
        style = self._pick_style(styles, args.style_id, warnings)

        # Build content
        full_md = args.content
        if args.sections:
            for sec in args.sections:
                full_md += f"\n\n## {sec.title}\n\n{sec.content}"

        body_html, toc = _md_to_html(full_md)

        toc_html = ""
        if args.include_toc and toc:
            toc_items = "\n".join(
                f'<li class="toc-level-{item["level"]}"><a href="#{item["id"]}">{item["text"]}</a></li>'
                for item in toc
            )
            toc_html = f'<nav class="toc"><h2>Contents</h2><ul>{toc_items}</ul></nav>'

        css = self._build_css(palette, style)
        html = self._render_html(args.title, css, toc_html, body_html, args.theme)

        # Write file if requested
        out_path_str: str | None = None
        if args.output_path:
            try:
                dest = resolve_workspace_path(args.output_path)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(html, encoding="utf-8")
                out_path_str = args.output_path
            except Exception as exc:
                warnings.append(f"Could not write file: {exc}")

        return {
            "output_path": out_path_str,
            "html": html,
            "size_bytes": len(html.encode("utf-8")),
            "palette_used": palette.get("id"),
            "style_used": style.get("id") if style else None,
            "toc_entries": len(toc),
            "_warnings": warnings,
        }

    # ------------------------------------------------------------------

    def _pick_palette(self, palettes: list, palette_id: str | None, theme: str, warnings: list) -> dict:
        if palette_id:
            for p in palettes:
                if p.get("id") == palette_id:
                    return p
            warnings.append(f"Palette '{palette_id}' not found; using default")
        # Pick first matching mode
        mode_map = {"dark": "dark", "light": "light", "auto": "dark"}
        target_mode = mode_map.get(theme, "dark")
        for p in palettes:
            if p.get("mode") == target_mode:
                return p
        # Fallback: embedded minimal dark palette
        return {
            "id": "default-dark",
            "tokens": {
                "background": "#0d1117",
                "surface": "#161b22",
                "surface-raised": "#1c2128",
                "text": "#e6edf3",
                "text-muted": "#7d8590",
                "border": "#30363d",
                "primary": "#2f81f7",
                "primary-foreground": "#ffffff",
                "accent": "#58a6ff",
                "danger": "#f85149",
                "success": "#3fb950",
                "warning": "#d29922",
            },
        }

    def _pick_style(self, styles: list, style_id: str | None, warnings: list) -> dict | None:
        if style_id:
            for s in styles:
                if s.get("id") == style_id:
                    return s
            warnings.append(f"Style '{style_id}' not found; using default")
        # Default: pick 'neo-minimal' or first available
        for s in styles:
            if s.get("id") in {"neo-minimal", "glassmorphism"}:
                return s
        return styles[0] if styles else None

    def _build_css(self, palette: dict, style: dict | None) -> str:
        t = palette.get("tokens", {})
        typo = (style or {}).get("typography", {})
        shape = (style or {}).get("shape", {})
        font_cat = typo.get("font_category", "")
        # Map font category hint to a safe web font stack
        if "mono" in font_cat:
            font_stack = "'JetBrains Mono', 'Fira Code', 'Courier New', monospace"
        elif "serif" in font_cat:
            font_stack = "Georgia, 'Times New Roman', serif"
        else:
            font_stack = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
        radius = shape.get("radius", "6px") if shape else "6px"
        if radius == "0px" or radius == 0:
            radius = "0"

        return textwrap.dedent(f"""
            :root {{
                --bg:        {t.get('background', '#0d1117')};
                --surface:   {t.get('surface', '#161b22')};
                --surface-raised: {t.get('surface-raised', '#1c2128')};
                --text:      {t.get('text', '#e6edf3')};
                --text-muted:{t.get('text-muted', '#7d8590')};
                --border:    {t.get('border', '#30363d')};
                --primary:   {t.get('primary', '#2f81f7')};
                --primary-fg:{t.get('primary-foreground', '#ffffff')};
                --accent:    {t.get('accent', '#58a6ff')};
                --danger:    {t.get('danger', '#f85149')};
                --success:   {t.get('success', '#3fb950')};
                --warning:   {t.get('warning', '#d29922')};
                --radius:    {radius};
                --font:      {font_stack};
            }}
            *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
            html {{ scroll-behavior: smooth; }}
            body {{
                background: var(--bg);
                color: var(--text);
                font-family: var(--font);
                font-size: 16px;
                line-height: 1.6;
                padding: 0;
            }}
            .page-wrapper {{
                max-width: 860px;
                margin: 0 auto;
                padding: 2rem 1.5rem 4rem;
            }}
            header {{
                border-bottom: 1px solid var(--border);
                padding-bottom: 1.5rem;
                margin-bottom: 2rem;
            }}
            header h1 {{
                font-size: 2rem;
                color: var(--text);
                line-height: 1.2;
            }}
            header .subtitle {{
                color: var(--text-muted);
                font-size: 0.9rem;
                margin-top: 0.4rem;
            }}
            nav.toc {{
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: var(--radius);
                padding: 1.25rem 1.5rem;
                margin-bottom: 2.5rem;
            }}
            nav.toc h2 {{
                font-size: 0.8rem;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                color: var(--text-muted);
                margin-bottom: 0.75rem;
            }}
            nav.toc ul {{ list-style: none; padding: 0; }}
            nav.toc li {{ padding: 0.2rem 0; }}
            nav.toc li.toc-level-1 {{ padding-left: 0; }}
            nav.toc li.toc-level-2 {{ padding-left: 1rem; }}
            nav.toc li.toc-level-3 {{ padding-left: 2rem; }}
            nav.toc li.toc-level-4, nav.toc li.toc-level-5, nav.toc li.toc-level-6 {{ padding-left: 3rem; }}
            nav.toc a {{ color: var(--accent); text-decoration: none; font-size: 0.9rem; }}
            nav.toc a:hover {{ text-decoration: underline; }}
            .content h1, .content h2, .content h3, .content h4, .content h5, .content h6 {{
                color: var(--text);
                line-height: 1.3;
                margin: 1.8rem 0 0.6rem;
            }}
            .content h1 {{ font-size: 1.75rem; }}
            .content h2 {{ font-size: 1.4rem; border-bottom: 1px solid var(--border); padding-bottom: 0.3rem; }}
            .content h3 {{ font-size: 1.15rem; }}
            .content p {{ margin: 0.75rem 0; }}
            .content a {{ color: var(--accent); }}
            .content a:hover {{ text-decoration: underline; }}
            .content code {{
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: 4px;
                padding: 0.1em 0.4em;
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 0.875em;
            }}
            .content pre {{
                background: var(--surface);
                border: 1px solid var(--border);
                border-radius: var(--radius);
                padding: 1rem 1.25rem;
                overflow-x: auto;
                margin: 1rem 0;
            }}
            .content pre code {{
                background: transparent;
                border: none;
                padding: 0;
                font-size: 0.875rem;
                line-height: 1.5;
            }}
            .content blockquote {{
                border-left: 3px solid var(--primary);
                padding: 0.5rem 1rem;
                margin: 1rem 0;
                color: var(--text-muted);
                background: var(--surface);
            }}
            .content ul, .content ol {{
                padding-left: 1.5rem;
                margin: 0.75rem 0;
            }}
            .content li {{ margin: 0.3rem 0; }}
            .content hr {{
                border: none;
                border-top: 1px solid var(--border);
                margin: 2rem 0;
            }}
            .content table {{
                border-collapse: collapse;
                width: 100%;
                margin: 1rem 0;
                font-size: 0.9rem;
            }}
            .content th, .content td {{
                border: 1px solid var(--border);
                padding: 0.5rem 0.75rem;
                text-align: left;
            }}
            .content th {{
                background: var(--surface);
                color: var(--text-muted);
                font-weight: 600;
                text-transform: uppercase;
                font-size: 0.75rem;
                letter-spacing: 0.05em;
            }}
            .content tr:nth-child(even) td {{ background: var(--surface); }}
            footer {{
                border-top: 1px solid var(--border);
                padding-top: 1rem;
                margin-top: 3rem;
                color: var(--text-muted);
                font-size: 0.8rem;
                text-align: center;
            }}
            @media (max-width: 600px) {{
                .page-wrapper {{ padding: 1rem 0.75rem 3rem; }}
                header h1 {{ font-size: 1.5rem; }}
            }}
        """).strip()

    def _render_html(self, title: str, css: str, toc_html: str, body_html: str, theme: str) -> str:
        color_scheme = "dark" if theme == "dark" else "light" if theme == "light" else "light dark"
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        escaped_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"""<!DOCTYPE html>
<html lang="en" style="color-scheme: {color_scheme};">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escaped_title}</title>
  <style>
{css}
  </style>
</head>
<body>
<div class="page-wrapper">
  <header>
    <h1>{escaped_title}</h1>
    <p class="subtitle">Generated {generated_at}</p>
  </header>
  {toc_html}
  <main class="content">
{body_html}
  </main>
  <footer>
    <p>Generated by Overlord11 HTML Report Generator</p>
  </footer>
</div>
</body>
</html>"""
