"""
ui_design_system.py — Overlord11 UI/UX Design System Generator
===============================================================
Generates a consolidated design system by combining a UI style (from
skills/uiux/styles.json) with a color palette (from skills/uiux/palettes.json).

Outputs a complete design specification with token tables, layout rules,
typography guidance, component shape rules, interaction/motion guidance,
do/don't checklists, stack-specific implementation hints, and a
Reviewer checklist.

When persist=True, writes:
  design-system/MASTER.md          (always)
  design-system/pages/<page>.md    (only when page is provided)
"""

import argparse
import hashlib
import io
import json
import os
import sys
from pathlib import Path

def safe_str(val, max_len: int = 200) -> str:
    """Encoding-safe string conversion. Prevents UnicodeEncodeError on cp1252/cp437 terminals.

    Args:
        val:     Value to convert. None returns '(none)'.
        max_len: Maximum output length in characters. Longer strings are truncated with '...'.

    Returns:
        A string safe to print on any terminal encoding, with non-representable characters
        replaced by backslash-escape sequences.
    """
    if val is None:
        return "(none)"
    s = str(val)
    if s and len(s) > max_len:
        s = s[:max_len] + "..."
    try:
        s.encode(sys.stdout.encoding or "utf-8")
        return s
    except (UnicodeEncodeError, LookupError):
        return s.encode("ascii", errors="backslashreplace").decode("ascii")


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    """Return the Overlord11 project root (two levels up from this file)."""
    return Path(__file__).resolve().parent.parent.parent


def _load_json(rel_path: str) -> list:
    """Load a JSON file relative to the project root. Returns parsed object."""
    full_path = _project_root() / rel_path
    with open(full_path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Default selection (deterministic based on project_name hash)
# ---------------------------------------------------------------------------

_STYLE_IDS = [
    "brutalist", "glassmorphism", "neobrutalism", "editorial", "minimal-zen",
    "data-dense", "soft-ui", "retro-terminal", "biomimetic", "aurora-gradient",
]

_PALETTE_IDS = [
    "midnight-ink", "chalk-board", "neon-city", "nordic-frost", "terracotta-sun",
    "deep-forest", "sakura-bloom", "volcanic-night", "arctic-monochrome", "ultraviolet",
]

# Curated style→palette affinity pairs — used to guide the default palette
# when no palette is explicitly chosen.
_STYLE_PALETTE_AFFINITY: dict[str, list[str]] = {
    "brutalist":       ["arctic-monochrome", "volcanic-night", "chalk-board"],
    "glassmorphism":   ["midnight-ink", "ultraviolet", "neon-city"],
    "neobrutalism":    ["chalk-board", "terracotta-sun", "nordic-frost"],
    "editorial":       ["chalk-board", "arctic-monochrome", "nordic-frost"],
    "minimal-zen":     ["nordic-frost", "arctic-monochrome", "sakura-bloom"],
    "data-dense":      ["midnight-ink", "nordic-frost", "arctic-monochrome"],
    "soft-ui":         ["sakura-bloom", "chalk-board", "terracotta-sun"],
    "retro-terminal":  ["neon-city", "volcanic-night", "midnight-ink"],
    "biomimetic":      ["deep-forest", "terracotta-sun", "chalk-board"],
    "aurora-gradient": ["ultraviolet", "neon-city", "midnight-ink"],
}


def _default_style(project_name: str) -> str:
    """Pick a style deterministically from the project name hash."""
    h = int(hashlib.md5(project_name.encode("utf-8")).hexdigest(), 16)
    return _STYLE_IDS[h % len(_STYLE_IDS)]


def _default_palette(style_id: str, project_name: str) -> str:
    """Pick a palette deterministically, preferring style-affinity choices."""
    candidates = _STYLE_PALETTE_AFFINITY.get(style_id, _PALETTE_IDS)
    h = int(hashlib.md5(f"{style_id}:{project_name}".encode("utf-8")).hexdigest(), 16)
    return candidates[h % len(candidates)]


# ---------------------------------------------------------------------------
# Stack-specific implementation hints
# ---------------------------------------------------------------------------

def _stack_hints(style: dict, palette: dict, stack: str) -> str:
    """Return stack-specific implementation notes for the chosen style + palette."""
    tokens = palette.get("tokens", {})
    lines = []

    if stack == "html-tailwind":
        lines.append("### Tailwind CSS Implementation\n")
        lines.append("Add to `tailwind.config.js` → `theme.extend.colors`:\n")
        lines.append("```js")
        lines.append("colors: {")
        for k, v in tokens.items():
            js_key = k.replace("-", "_")
            lines.append(f"  '{k}': '{v}',       // {js_key}")
        lines.append("}")
        lines.append("```\n")
        lines.append("Use tokens as Tailwind classes: `bg-[var(--color-background)]` or add CSS vars to `@layer base`.\n")

    elif stack == "html-css":
        lines.append("### CSS Custom Properties\n")
        lines.append("Add to `:root` in your base stylesheet:\n")
        lines.append("```css")
        lines.append(":root {")
        for k, v in tokens.items():
            lines.append(f"  --color-{k}: {v};")
        lines.append("}")
        lines.append("```\n")
        lines.append("Use as: `color: var(--color-text);` `background: var(--color-background);`\n")

    elif stack in ("react", "nextjs"):
        lines.append(f"### {'Next.js' if stack == 'nextjs' else 'React'} Implementation\n")
        lines.append("Create `styles/tokens.ts` or `lib/design-tokens.ts`:\n")
        lines.append("```ts")
        lines.append("export const tokens = {")
        lines.append("  colors: {")
        for k, v in tokens.items():
            ts_key = k.replace("-", "_")
            lines.append(f"    {ts_key}: '{v}',")
        lines.append("  },")
        lines.append("} as const;")
        lines.append("```\n")
        lines.append("Import and use with CSS Modules, Tailwind, or inline styles. Never hardcode hex values in components.\n")

    elif stack == "vue":
        lines.append("### Vue / Nuxt Implementation\n")
        lines.append("Add CSS variables to `assets/css/tokens.css` and import globally:\n")
        lines.append("```css")
        lines.append(":root {")
        for k, v in tokens.items():
            lines.append(f"  --color-{k}: {v};")
        lines.append("}")
        lines.append("```\n")
        lines.append("Access in `<style>` blocks with `var(--color-primary)` etc.\n")

    elif stack == "svelte":
        lines.append("### Svelte Implementation\n")
        lines.append("In `app.css` (global styles):\n")
        lines.append("```css")
        lines.append(":root {")
        for k, v in tokens.items():
            lines.append(f"  --color-{k}: {v};")
        lines.append("}")
        lines.append("```\n")
        lines.append("Reference in component `<style>` blocks with `var(--color-primary)` etc.\n")

    else:
        lines.append(f"### Implementation ({stack})\n")
        lines.append("Define color tokens as CSS custom properties or framework-specific variables.\n")

    # Shape radius hint
    radius = style.get("shape", {}).get("radius", "4px")
    lines.append(f"**Border-radius convention**: `{radius}` — apply this to all interactive components.\n")

    # Motion hint
    motion = style.get("interaction", {}).get("motion", "200ms ease")
    lines.append(f"**Transition convention**: `{motion}` — use for all state transitions.\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown output builder
# ---------------------------------------------------------------------------

def _build_md(style: dict, palette: dict, stack: str, project_name: str, page: str | None) -> str:
    """Build a complete Markdown design system specification."""
    lines: list[str] = []
    t = palette.get("tokens", {})

    # Header
    lines.append(f"# Design System — {project_name}")
    if page:
        lines.append(f"\n> **Page Override**: `{page}` — supplements `MASTER.md` for this page only.")
    lines.append(f"\n**Style**: `{style['id']}` — {style['name']}")
    lines.append(f"**Palette**: `{palette['id']}` — {palette['name']} ({palette.get('mode', 'light')} mode)")
    lines.append(f"**Stack**: `{stack}`")
    lines.append(f"\n_{style['description']}_\n")
    lines.append("---\n")

    # Color Tokens
    lines.append("## Color Tokens\n")
    lines.append("| Token | Hex | Role |")
    lines.append("|-------|-----|------|")
    token_roles = {
        "background":          "Page/app background",
        "surface":             "Card, panel, modal background",
        "surface-raised":      "Elevated surface (dropdowns, tooltips)",
        "text":                "Primary body text",
        "text-muted":          "Secondary/placeholder text",
        "border":              "Default border/divider color",
        "primary":             "Primary action (buttons, links)",
        "primary-foreground":  "Text on primary background",
        "secondary":           "Secondary surface / alternate fills",
        "secondary-foreground":"Text on secondary background",
        "accent":              "Highlight / hover / focus ring",
        "danger":              "Error states, destructive actions",
        "success":             "Confirmation, success states",
        "warning":             "Caution, warning states",
    }
    for key, hex_val in t.items():
        role = token_roles.get(key, "")
        lines.append(f"| `{key}` | `{hex_val}` | {role} |")
    lines.append(f"\n**Contrast Notes**: {palette.get('contrast_notes', 'See palette definition.')}\n")
    lines.append("---\n")

    # Layout
    layout = style.get("layout", {})
    lines.append("## Layout Rules\n")
    lines.append(f"- **Grid**: {layout.get('grid', '')}")
    lines.append(f"- **Stack direction**: {layout.get('stack', '')}")
    lines.append(f"- **Content density**: {layout.get('density', '')}")
    lines.append(f"- **Whitespace approach**: {layout.get('whitespace', '')}\n")
    lines.append("---\n")

    # Typography
    typo = style.get("typography", {})
    lines.append("## Typography\n")
    lines.append(f"- **Font category**: {typo.get('font_category', '')}")
    lines.append(f"- **Type scale**: {typo.get('scale', '')}")
    lines.append(f"- **Weight range**: {typo.get('weight', '')}")
    lines.append(f"- **Transform rules**: {typo.get('transform', '')}")
    lines.append(f"- **Line height**: {typo.get('line_height', '')}\n")
    lines.append("---\n")

    # Shape & Borders
    shape = style.get("shape", {})
    lines.append("## Component Shape\n")
    lines.append(f"- **Border radius**: {shape.get('radius', '')}")
    lines.append(f"- **Borders**: {shape.get('borders', '')}")
    lines.append(f"- **Shadows**: {shape.get('shadows', '')}\n")
    lines.append("---\n")

    # Interaction & Motion
    interaction = style.get("interaction", {})
    lines.append("## Interaction & Motion\n")
    lines.append(f"- **Hover state**: {interaction.get('hover', '')}")
    lines.append(f"- **Focus state**: {interaction.get('focus', '')}")
    lines.append(f"- **Motion/easing**: {interaction.get('motion', '')}")
    lines.append(f"- **Animation guidance**: {interaction.get('animation', '')}\n")
    lines.append("---\n")

    # Do / Don't
    lines.append("## Do / Don't Checklist\n")
    lines.append("### ✅ Do\n")
    for item in style.get("dos", []):
        lines.append(f"- {item}")
    lines.append("\n### ❌ Don't\n")
    for item in style.get("donts", []):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("---\n")

    # Stack implementation
    lines.append("## Stack Implementation\n")
    lines.append(_stack_hints(style, palette, stack))
    lines.append("---\n")

    # Reviewer checklist
    lines.append("## Reviewer Validation Checklist\n")
    lines.append("> Use this checklist when reviewing any UI output against this design system.\n")
    lines.append("- [ ] All colors reference design system tokens — no raw hex values in component code")
    lines.append("- [ ] Font family and weight match the typography rules above")
    lines.append("- [ ] Border-radius matches the shape specification")
    lines.append("- [ ] Hover and focus states implemented and keyboard-accessible")
    lines.append(f"- [ ] Color contrast ≥ 4.5:1 for normal text against `background` ({t.get('background', '?')})")
    lines.append(f"- [ ] Color contrast ≥ 3:1 for large text (18px bold / 24px regular)")
    lines.append("- [ ] `danger` token used for all error/destructive states")
    lines.append("- [ ] `success` token used for all confirmation/positive states")
    lines.append("- [ ] `warning` token used for all caution states")
    lines.append("- [ ] No inline color styles that bypass the token system")
    lines.append("- [ ] Whitespace and density follow the layout rules")
    lines.append("- [ ] Do/Don't checklist reviewed and none of the anti-patterns are present")
    lines.append("- [ ] Transitions/animations follow the motion guidance")
    if page:
        lines.append(f"- [ ] Page-specific overrides for `{page}` respected in addition to MASTER rules")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON output builder
# ---------------------------------------------------------------------------

def _build_json(style: dict, palette: dict, stack: str, project_name: str, page: str | None) -> dict:
    """Build a structured dictionary representation of the design system."""
    return {
        "project": project_name,
        "page": page,
        "style": {
            "id": style["id"],
            "name": style["name"],
            "description": style["description"],
            "layout": style.get("layout", {}),
            "typography": style.get("typography", {}),
            "shape": style.get("shape", {}),
            "interaction": style.get("interaction", {}),
            "dos": style.get("dos", []),
            "donts": style.get("donts", []),
        },
        "palette": {
            "id": palette["id"],
            "name": palette["name"],
            "mode": palette.get("mode", "light"),
            "description": palette.get("description", ""),
            "tokens": palette.get("tokens", {}),
            "contrast_notes": palette.get("contrast_notes", ""),
        },
        "stack": stack,
    }


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def ui_design_system(
    style_id: str | None = None,
    palette_id: str | None = None,
    stack: str = "html-tailwind",
    page: str | None = None,
    project_name: str = "My Project",
    output_format: str = "md",
    persist: bool = False,
) -> str:
    """
    Generate a consolidated UI/UX design system for a project.

    Combines a UI style (layout/typography/shape/motion rules) with a color
    palette (semantic tokens) and returns a complete design specification.
    Optionally persists to design-system/MASTER.md and/or a per-page file.

    Args:
        style_id:      ID from skills/uiux/styles.json. Defaults to deterministic selection.
        palette_id:    ID from skills/uiux/palettes.json. Defaults to deterministic selection.
        stack:         Front-end stack for implementation hints (html-tailwind, html-css, react,
                       nextjs, vue, svelte).
        page:          Optional page name for a per-page override (e.g. 'landing').
        project_name:  Project name used in headers and for default selection.
        output_format: 'md' for Markdown (default) or 'json' for structured JSON.
        persist:       If True, write MASTER.md (and pages/<page>.md) to design-system/.

    Returns:
        The generated design system as a Markdown string or JSON string.
    """
    # Load datasets
    try:
        styles = _load_json("skills/uiux/styles.json")
        palettes = _load_json("skills/uiux/palettes.json")
    except FileNotFoundError as exc:
        return f"Error: Could not load design system data — {safe_str(exc)}. Ensure skills/uiux/ exists."
    except json.JSONDecodeError as exc:
        return f"Error: Malformed JSON in design system data — {safe_str(exc)}"

    styles_by_id = {s["id"]: s for s in styles}
    palettes_by_id = {p["id"]: p for p in palettes}

    # Resolve style
    resolved_style_id = style_id or _default_style(project_name)
    style = styles_by_id.get(resolved_style_id)
    if style is None:
        available = ", ".join(styles_by_id.keys())
        return f"Error: Unknown style_id '{safe_str(resolved_style_id)}'. Available: {available}"

    # Resolve palette
    resolved_palette_id = palette_id or _default_palette(resolved_style_id, project_name)
    palette = palettes_by_id.get(resolved_palette_id)
    if palette is None:
        available = ", ".join(palettes_by_id.keys())
        return f"Error: Unknown palette_id '{safe_str(resolved_palette_id)}'. Available: {available}"

    # Validate stack
    valid_stacks = {"html-tailwind", "html-css", "react", "nextjs", "vue", "svelte"}
    if stack not in valid_stacks:
        stack = "html-tailwind"

    # Build output
    if output_format == "json":
        data = _build_json(style, palette, stack, project_name, page)
        output = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        output = _build_md(style, palette, stack, project_name, page)

    # Persist if requested
    if persist:
        _persist_design_system(output, output_format, page)

    return output


def _persist_design_system(content: str, output_format: str, page: str | None) -> None:
    """Write the design system content to design-system/ directory."""
    root = _project_root()
    ext = "json" if output_format == "json" else "md"
    master_path = root / "design-system" / f"MASTER.{ext}"
    master_path.parent.mkdir(parents=True, exist_ok=True)
    master_path.write_text(content, encoding="utf-8")

    if page:
        page_safe = page.lower().replace(" ", "-")
        page_path = root / "design-system" / "pages" / f"{page_safe}.{ext}"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Generate a UI/UX design system")
    p.add_argument("--style_id", default=None,
                   help="UI style ID (e.g. minimal-zen)")
    p.add_argument("--palette_id", default=None,
                   help="Color palette ID (e.g. nordic-frost)")
    p.add_argument("--stack", default="html-tailwind",
                   choices=["html-tailwind", "html-css", "react", "nextjs", "vue", "svelte"],
                   help="Front-end stack for implementation hints")
    p.add_argument("--page", default=None,
                   help="Page name for per-page override (e.g. landing)")
    p.add_argument("--project_name", default="My Project",
                   help="Project name (used in headers and default selection)")
    p.add_argument("--output_format", default="md", choices=["md", "json"],
                   help="Output format: md (default) or json")
    p.add_argument("--persist", action="store_true",
                   help="Persist to design-system/MASTER.md (and pages/<page>.md if --page set)")
    args = p.parse_args()

    result = ui_design_system(
        style_id=args.style_id,
        palette_id=args.palette_id,
        stack=args.stack,
        page=args.page,
        project_name=args.project_name,
        output_format=args.output_format,
        persist=args.persist,
    )
    print(safe_str(result, max_len=100000))
    sys.exit(0)
