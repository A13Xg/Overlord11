# UI/UX Design System Skill

## Overview

Overlord11's built-in UI/UX design system skill gives every agent a consistent, reusable source of truth for visual design decisions. Instead of inventing colors, fonts, and spacing rules from scratch on each task, the Coder generates (or reads) a complete design specification before writing any UI code. The Reviewer then validates the output against that same specification.

The skill is implemented as a first-class Overlord11 tool (`ui_design_system`) backed by curated datasets in `skills/uiux/`.

---

## What Is a Design System (in this context)?

A design system is a compact, machine-readable specification combining:

- **A UI Style** — layout rules, typography guidance, component shape/radius, interaction/motion patterns, and an explicit Do/Don't list.
- **A Color Palette** — semantic hex tokens (background, text, primary, danger, success, etc.) with contrast notes.

The two are combined into a single Markdown or JSON document that agents can read and strictly follow.

---

## Dataset: Styles (`skills/uiux/styles.json`)

Ten vastly different UI styles are included. Each covers layout, typography, shape, interaction, and anti-patterns:

| ID | Name | Character |
|----|------|-----------|
| `brutalist` | Brutalist | Raw, sharp, high-contrast, zero-radius, instant interactions |
| `glassmorphism` | Glassmorphism | Frosted glass panels, blur effects, translucent depth |
| `neobrutalism` | Neo-Brutalism | Bold flat colors, chunky borders, hard offset shadows |
| `editorial` | Editorial | Print-inspired, typographic-first, baseline grid, serif + sans |
| `minimal-zen` | Minimal Zen | Ultra-clean, extreme whitespace, single accent, restrained |
| `data-dense` | Data Dense | Compact tables, sidebar nav, monospace data values, analyst UX |
| `soft-ui` | Soft UI (Neumorphism) | Tactile shadows, extruded/inset surfaces, monochromatic |
| `retro-terminal` | Retro Terminal | CRT aesthetic, phosphor glow, monospace, scanlines |
| `biomimetic` | Biomimetic | Organic blobs, flowing curves, nature-inspired, earthy |
| `aurora-gradient` | Aurora Gradient | Multi-stop gradients, cinematic depth, neon accents |

Each style entry includes:
- `layout` — grid type, stack direction, density, whitespace approach
- `typography` — font category (with examples), type scale, weight, transform, line-height
- `shape` — border-radius, border rules, shadow style
- `interaction` — hover behavior, focus state, motion/easing, animation guidance
- `dos` / `donts` — explicit anti-pattern checklists

---

## Dataset: Palettes (`skills/uiux/palettes.json`)

Ten color palettes, each available in light or dark mode with full semantic token coverage:

| ID | Name | Mode | Character |
|----|------|------|-----------|
| `midnight-ink` | Midnight Ink | dark | Deep navy, cool blue-white, professional |
| `chalk-board` | Chalk Board | light | Warm cream, terracotta accents, handwritten warmth |
| `neon-city` | Neon City | dark | Cyberpunk magenta + cyan on near-black |
| `nordic-frost` | Nordic Frost | light | Desaturated Arctic blues, Scandinavian precision |
| `terracotta-sun` | Terracotta Sun | light | Mediterranean warmth, clay reds, sandy yellows |
| `deep-forest` | Deep Forest | dark | Forest greens, earthy golds, organic luxury |
| `sakura-bloom` | Sakura Bloom | light | Cherry blossom pinks, ivory, graceful |
| `volcanic-night` | Volcanic Night | dark | Smoldering crimson + ember orange on charcoal |
| `arctic-monochrome` | Arctic Monochrome | light | Pure grayscale + single steel blue accent |
| `ultraviolet` | Ultraviolet | dark | Deep purple + electric lavender, AI/premium |

Each palette entry includes:
- `mode` — `light` or `dark`
- `tokens` — 14 semantic hex values: `background`, `surface`, `surface-raised`, `text`, `text-muted`, `border`, `primary`, `primary-foreground`, `secondary`, `secondary-foreground`, `accent`, `danger`, `success`, `warning`
- `contrast_notes` — human-readable WCAG contrast ratios for the key token pairs

---

## The `ui_design_system` Tool

### Tool Reference

**File**: `tools/defs/ui_design_system.json` / `tools/python/ui_design_system.py`

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `style_id` | string | auto | Style ID from `skills/uiux/styles.json`. If omitted, selected deterministically by `project_name` hash. |
| `palette_id` | string | auto | Palette ID from `skills/uiux/palettes.json`. If omitted, selected by style affinity + `project_name` hash. |
| `stack` | string | `html-tailwind` | Front-end stack: `html-tailwind`, `html-css`, `react`, `nextjs`, `vue`, `svelte`. |
| `page` | string | none | Optional page name for a per-page override (e.g. `landing`, `dashboard`). |
| `project_name` | string | `My Project` | Used in headers and for deterministic default selection. |
| `output_format` | string | `md` | `md` for Markdown or `json` for structured JSON. |
| `persist` | bool | `false` | If `true`, writes to `design-system/MASTER.md` (and `design-system/pages/<page>.md` when `page` is set). |

### Output

The tool produces a consolidated design system document containing:
1. Color token table with hex values and semantic roles
2. WCAG contrast notes
3. Layout rules (grid, density, whitespace)
4. Typography guidance (fonts, scale, weight, line-height)
5. Component shape rules (radius, borders, shadows)
6. Interaction & motion guidance (hover, focus, animation)
7. Do / Don't checklist (explicit anti-patterns)
8. Stack-specific implementation code (CSS variables, Tailwind config, TypeScript tokens)
9. Reviewer validation checklist

---

## How to Use: Generating a Design System

### Option 1 — CLI (direct invocation)

```bash
# Generate and display (no file written)
python tools/python/ui_design_system.py \
  --style_id minimal-zen \
  --palette_id nordic-frost \
  --stack nextjs \
  --project_name "My SaaS App"

# Generate with auto-selected style+palette (deterministic)
python tools/python/ui_design_system.py --project_name "Acme Dashboard"

# Generate and persist to design-system/MASTER.md
python tools/python/ui_design_system.py \
  --style_id data-dense \
  --palette_id midnight-ink \
  --stack react \
  --project_name "Analytics Platform" \
  --persist

# Generate a page override (adds design-system/pages/landing.md)
python tools/python/ui_design_system.py \
  --style_id aurora-gradient \
  --palette_id ultraviolet \
  --stack html-tailwind \
  --project_name "Creative Agency" \
  --page landing \
  --persist

# JSON output for programmatic use
python tools/python/ui_design_system.py \
  --style_id brutalist \
  --palette_id volcanic-night \
  --output_format json
```

### Option 2 — Via Overlord11 Agent (Coder workflow)

The Coder agent automatically calls this tool when:
1. The task involves UI implementation, AND
2. `design-system/MASTER.md` does not yet exist in the project

The agent calls:
```
ui_design_system(style_id="...", palette_id="...", stack="...", project_name="...", persist=True)
```

If `design-system/MASTER.md` already exists (e.g., from a previous session), the Coder reads it instead of re-generating, ensuring cross-session consistency.

---

## How to Persist and Reuse Design Specs

When `persist=True`, the tool writes:

```
design-system/
  MASTER.md            ← Always written — the canonical spec for the whole project
  pages/
    landing.md         ← Written only when --page is specified
    dashboard.md       ← Additional page overrides
```

### Persistence rules

- **`MASTER.md`** is the single source of truth. It overrides any agent's instinct to invent styles.
- **Page overrides** (`pages/<page>.md`) extend the master spec for a specific page. They contain the same full spec, but may use a different style/palette combination if the page has a distinct purpose (e.g., a dark `data-dense` dashboard vs a light `minimal-zen` landing page).
- Once persisted, **all future sessions** reference `design-system/MASTER.md` without re-running the tool (the Coder reads it at the start of UI tasks).
- To **change the design system**, re-run with new parameters and `--persist` to overwrite.

---

## How Agents Use the Design System

### Orchestrator

When the Orchestrator classifies an incoming request as UI/UX work, it includes this instruction in the delegation to the Coder:

> "Before implementing any UI, check whether `design-system/MASTER.md` exists. If yes, read it. If no, call `ui_design_system` with `persist=true` to generate it. Use only the tokens and rules from the design system in your implementation."

### Coder

The Coder's workflow includes a mandatory UI check step (step 3):

1. Check if `design-system/MASTER.md` exists
2. If yes → read it; treat as the binding spec
3. If no → call `ui_design_system` with `persist=true`; use the generated spec
4. Write all UI code strictly following: color tokens (no raw hex), typography rules, border-radius, interaction patterns, and Do/Don't list

### Reviewer

The Reviewer's workflow includes a UI Design System Audit step:

1. Check if `design-system/MASTER.md` exists (flag as MAJOR if missing for a UI task)
2. Cross-reference all UI files against the spec
3. Flag any raw hex values, wrong border-radii, missing focus states, or violated anti-patterns
4. Use the "Reviewer Validation Checklist" section of `MASTER.md` as the acceptance criteria

---

## Combining Styles and Palettes

All 10 styles × 10 palettes = **100 valid combinations**. Not all combinations are equally sensible — the tool uses affinity tables to guide the default selection. Common pairings:

| Style | Good Palettes | Avoid |
|-------|--------------|-------|
| `brutalist` | `arctic-monochrome`, `volcanic-night`, `chalk-board` | `sakura-bloom`, `glassmorphism` |
| `glassmorphism` | `midnight-ink`, `ultraviolet`, `neon-city` | `chalk-board`, `soft-ui` |
| `minimal-zen` | `nordic-frost`, `arctic-monochrome`, `sakura-bloom` | `neon-city`, `volcanic-night` |
| `data-dense` | `midnight-ink`, `nordic-frost`, `arctic-monochrome` | `biomimetic`, `aurora-gradient` |
| `retro-terminal` | `neon-city`, `volcanic-night`, `midnight-ink` | `sakura-bloom`, `chalk-board` |
| `biomimetic` | `deep-forest`, `terracotta-sun`, `chalk-board` | `neon-city`, `ultraviolet` |
| `aurora-gradient` | `ultraviolet`, `neon-city`, `midnight-ink` | `chalk-board`, `nordic-frost` |

When you omit both `style_id` and `palette_id`, the tool selects a combination from the affinity table deterministically using the `project_name` hash — the same project name always produces the same combination.

---

## Extending the Skill

### Adding a new style

Add an entry to `skills/uiux/styles.json` following the existing schema:
- Required fields: `id`, `name`, `description`, `layout`, `typography`, `shape`, `interaction`, `dos`, `donts`
- Add the new `id` to `_STYLE_IDS` in `tools/python/ui_design_system.py`
- Optionally add affinity palette mappings to `_STYLE_PALETTE_AFFINITY`

### Adding a new palette

Add an entry to `skills/uiux/palettes.json` following the existing schema:
- Required fields: `id`, `name`, `mode`, `description`, `tokens` (all 14 token keys), `contrast_notes`
- Add the new `id` to `_PALETTE_IDS` in `tools/python/ui_design_system.py`

---

## Troubleshooting

**"Could not load design system data"** — The `skills/uiux/` directory is missing or the JSON files are corrupted. Ensure you are running from the Overlord11 project root.

**"Unknown style_id"** — The provided `style_id` does not match any entry in `styles.json`. Run `python tools/python/ui_design_system.py --list` (or check `skills/uiux/styles.json`) for valid IDs.

**Reviewer flags raw hex values in UI code** — The Coder did not read `design-system/MASTER.md` before implementing. Re-run with the design system consulted, replace all raw hex literals with token references.

**Design system changes between sessions** — If `persist=false` was used, the spec was not saved. Re-run with `--persist` and commit `design-system/MASTER.md` to source control to ensure cross-session stability.
