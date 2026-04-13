"""
data_visualizer — Generate interactive, self-contained HTML chart visualizations.

Supported chart types (action parameter):
  bar       — vertical bar chart, single or multi-series
  line      — line chart with optional area fill, single or multi-series
  pie       — pie / donut chart
  scatter   — x/y scatter plot
  heatmap   — color-coded grid matrix
  timeline  — horizontal Gantt-style timeline
  dashboard — multi-chart layout (takes an array of chart specs)

Data input (one of 'data' or 'data_file' required):
  data      — JSON string
  data_file — path to a .json or .csv file

Accepted data shapes per chart type:
  bar / line:
    Records:      [{"label": "Jan", "value": 50}, ...]
    Multi-series: [{"label": "Jan", "sales": 50, "costs": 30}, ...]
    Series dict:  {"labels": ["Jan"], "datasets": [{"name": "Sales", "values": [50]}]}

  pie:
    Records:      [{"label": "A", "value": 40}, ...]
    Simple dict:  {"A": 40, "B": 60}

  scatter:
    Records:      [{"x": 1.5, "y": 2.3}, ...]
    Auto-field:   [{"weight": 70, "height": 175, "name": "Alice"}, ...] + x_field/y_field

  heatmap:
    Matrix:       {"rows": ["A","B"], "cols": ["X","Y"], "values": [[1,2],[3,4]]}
    Flat records: [{"row": "A", "col": "X", "value": 1}, ...]

  timeline:
    Records:      [{"task": "Design", "start": "2024-01-01", "end": "2024-01-15"}, ...]
                  Optionally add "status" field ("done"|"active"|"pending").

  dashboard:
    {"charts": [{"type": "bar", "title": "Revenue", "data": {...}}, ...]}

Output:
  A single self-contained .html file — all CSS and JS are embedded inline.
  No external dependencies; works offline.

Return dict:
  {
    "status": "success",
    "action": <chart_type>,
    "file": "/absolute/path/to/chart.html",
    "file_name": "chart.html",
    "size_bytes": 45678,
    "chart_type": <chart_type>,
    "series_count": 2,
    "data_points": 12,
  }
"""

import csv
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("overlord11.data_visualizer")

# ---------------------------------------------------------------------------
# Color palettes
# ---------------------------------------------------------------------------

_PALETTES: dict[str, dict] = {
    "tactical": {
        "bg":        "#090c09",
        "surface":   "#0e1410",
        "border":    "#1a3520",
        "text":      "#c8ffc8",
        "text2":     "#7aad7a",
        "text3":     "#3d6b3d",
        "heading":   "#00ff41",
        "colors": [
            "#00ff41", "#00e5cc", "#ffb000",
            "#ff6b35", "#c084fc", "#60a5fa",
            "#f472b6", "#a3e635",
        ],
        "heatmap_low":  "#0e1410",
        "heatmap_high": "#00ff41",
    },
    "dark": {
        "bg":        "#0d0d1a",
        "surface":   "#13132b",
        "border":    "#2a2a5a",
        "text":      "#e0e0ff",
        "text2":     "#9090cc",
        "text3":     "#4a4a8a",
        "heading":   "#818cf8",
        "colors": [
            "#818cf8", "#34d399", "#fb923c",
            "#f472b6", "#60a5fa", "#facc15",
            "#a78bfa", "#4ade80",
        ],
        "heatmap_low":  "#13132b",
        "heatmap_high": "#818cf8",
    },
    "vibrant": {
        "bg":        "#111111",
        "surface":   "#1a1a1a",
        "border":    "#333333",
        "text":      "#ffffff",
        "text2":     "#cccccc",
        "text3":     "#888888",
        "heading":   "#ff4081",
        "colors": [
            "#ff4081", "#00bcd4", "#ffeb3b",
            "#4caf50", "#ff5722", "#9c27b0",
            "#03a9f4", "#8bc34a",
        ],
        "heatmap_low":  "#1a1a1a",
        "heatmap_high": "#ff4081",
    },
    "light": {
        "bg":        "#f8fafc",
        "surface":   "#ffffff",
        "border":    "#e2e8f0",
        "text":      "#1e293b",
        "text2":     "#475569",
        "text3":     "#94a3b8",
        "heading":   "#1e293b",
        "colors": [
            "#3b82f6", "#10b981", "#f59e0b",
            "#ef4444", "#8b5cf6", "#06b6d4",
            "#ec4899", "#84cc16",
        ],
        "heatmap_low":  "#eff6ff",
        "heatmap_high": "#1d4ed8",
    },
}


# ---------------------------------------------------------------------------
# Data loading and normalization
# ---------------------------------------------------------------------------

def _load_data(data: Optional[str], data_file: Optional[str]) -> Any:
    """Load data from inline JSON string or file path (.json or .csv)."""
    if data_file:
        path = Path(data_file)
        if not path.exists():
            raise FileNotFoundError(f"data_file not found: {data_file}")
        if path.suffix.lower() == ".csv":
            with open(path, newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)
            # Auto-convert numeric strings to float where possible
            parsed = []
            for row in rows:
                out = {}
                for k, v in row.items():
                    try:
                        out[k] = float(v)
                    except (ValueError, TypeError):
                        out[k] = v
                parsed.append(out)
            return parsed
        else:
            return json.loads(path.read_text(encoding="utf-8"))
    elif data:
        return json.loads(data)
    else:
        raise ValueError("Either 'data' (JSON string) or 'data_file' (path) is required.")


def _detect_xy_fields(records: list[dict], x_field: Optional[str], y_field: Optional[str]):
    """
    Given a list of dicts, infer x and y field names when not specified.
    - x_field: first string-valued field (or field named 'label'/'name'/'x')
    - y_field: first numeric field (or field named 'value'/'y'/'count')
    Returns (x_field, [y_field, ...])
    """
    if not records:
        return x_field or "label", [y_field or "value"]

    sample = records[0]
    keys = list(sample.keys())

    # Detect x_field
    if not x_field:
        preferred_x = {"label", "name", "category", "x", "date", "key", "group"}
        x_field = next((k for k in keys if k.lower() in preferred_x), None)
        if not x_field:
            # First string-valued field
            x_field = next((k for k in keys if isinstance(sample.get(k), str)), keys[0])

    # Detect y_field(s)
    y_fields_list: list[str]
    if y_field:
        y_fields_list = [f.strip() for f in y_field.split(",")]
    else:
        preferred_y = {"value", "y", "count", "total", "amount", "score"}
        y_fields_list = [k for k in keys if k.lower() in preferred_y]
        if not y_fields_list:
            # All numeric fields that aren't x_field
            y_fields_list = [k for k in keys if k != x_field and isinstance(sample.get(k), (int, float))]
        if not y_fields_list:
            y_fields_list = [keys[1]] if len(keys) > 1 else [keys[0]]

    return x_field, y_fields_list


def _normalize_bar_line(raw: Any, x_field: Optional[str], y_field: Optional[str]) -> dict:
    """
    Normalize bar/line data into:
    {"labels": [...], "datasets": [{"name": str, "values": [...]}, ...]}
    """
    # Already in series format
    if isinstance(raw, dict) and "labels" in raw and "datasets" in raw:
        return raw

    # Simple dict {"Jan": 50, "Feb": 75}
    if isinstance(raw, dict):
        return {
            "labels": list(raw.keys()),
            "datasets": [{"name": "Value", "values": list(raw.values())}],
        }

    # List of records
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        xf, yfs = _detect_xy_fields(raw, x_field, y_field)
        labels = [str(r.get(xf, i)) for i, r in enumerate(raw)]
        datasets = []
        for yf in yfs:
            datasets.append({
                "name": yf,
                "values": [float(r.get(yf, 0)) for r in raw],
            })
        return {"labels": labels, "datasets": datasets}

    raise ValueError(f"Cannot normalize data for bar/line chart: unsupported shape {type(raw)}")


def _normalize_pie(raw: Any, x_field: Optional[str], y_field: Optional[str]) -> dict:
    """Normalize pie data into {"labels": [...], "values": [...]}"""
    if isinstance(raw, dict) and "labels" in raw and "values" in raw:
        return raw
    if isinstance(raw, dict):
        return {"labels": list(raw.keys()), "values": [float(v) for v in raw.values()]}
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        xf, yfs = _detect_xy_fields(raw, x_field, y_field)
        yf = yfs[0]
        return {
            "labels": [str(r.get(xf, i)) for i, r in enumerate(raw)],
            "values": [float(r.get(yf, 0)) for r in raw],
        }
    raise ValueError("Cannot normalize data for pie chart.")


def _normalize_scatter(raw: Any, x_field: Optional[str], y_field: Optional[str]) -> dict:
    """Normalize scatter data into {"points": [{"x": ..., "y": ..., "label": ...}, ...]}"""
    if isinstance(raw, dict) and "points" in raw:
        return raw
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        xf = x_field or ("x" if "x" in raw[0] else list(raw[0].keys())[0])
        yf = (y_field.split(",")[0].strip() if y_field else None) or ("y" if "y" in raw[0] else list(raw[0].keys())[1])
        label_field = next((k for k in raw[0] if k not in (xf, yf) and isinstance(raw[0][k], str)), None)
        points = []
        for i, r in enumerate(raw):
            pt = {"x": float(r.get(xf, 0)), "y": float(r.get(yf, 0))}
            if label_field:
                pt["label"] = str(r[label_field])
            else:
                pt["label"] = str(i)
            points.append(pt)
        return {"points": points, "x_label": xf, "y_label": yf}
    raise ValueError("Cannot normalize data for scatter chart.")


def _normalize_heatmap(raw: Any) -> dict:
    """Normalize heatmap data into {"rows": [...], "cols": [...], "values": [[...]]}"""
    if isinstance(raw, dict) and "rows" in raw and "cols" in raw and "values" in raw:
        return raw
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        # Flat records: [{row, col, value}]
        row_field = next((k for k in raw[0] if k.lower() in ("row", "y", "category")), list(raw[0].keys())[0])
        col_field = next((k for k in raw[0] if k.lower() in ("col", "column", "x")), list(raw[0].keys())[1])
        val_field = next((k for k in raw[0] if k.lower() in ("value", "v", "count", "z")), list(raw[0].keys())[2])
        rows = list(dict.fromkeys(r[row_field] for r in raw))
        cols = list(dict.fromkeys(r[col_field] for r in raw))
        lookup = {(r[row_field], r[col_field]): float(r.get(val_field, 0)) for r in raw}
        values = [[lookup.get((row, col), 0) for col in cols] for row in rows]
        return {"rows": rows, "cols": cols, "values": values}
    raise ValueError("Cannot normalize heatmap data.")


def _normalize_timeline(raw: Any) -> dict:
    """Normalize timeline data into {"tasks": [{"task", "start", "end", "status"}, ...]}"""
    if isinstance(raw, dict) and "tasks" in raw:
        return raw
    if isinstance(raw, list):
        return {"tasks": raw}
    raise ValueError("Cannot normalize timeline data.")


# ---------------------------------------------------------------------------
# HTML / JS generation
# ---------------------------------------------------------------------------

_HTML_WRAPPER = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{
  height: 100%;
  background: {bg};
  color: {text};
  font-family: 'Courier New', Courier, monospace;
  font-size: 13px;
}}
#chart-wrap {{
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 28px 20px 20px;
  min-height: 100vh;
}}
h1 {{
  font-size: 18px;
  letter-spacing: .2em;
  color: {heading};
  text-align: center;
  margin-bottom: 6px;
  text-shadow: 0 0 12px {heading}55;
}}
.meta {{
  font-size: 10px;
  letter-spacing: .15em;
  color: {text3};
  margin-bottom: 22px;
}}
.chart-container {{
  position: relative;
  width: 100%;
  max-width: 900px;
  background: {surface};
  border: 1px solid {border};
  padding: 16px;
}}
canvas {{
  display: block;
  width: 100%;
}}
#tooltip {{
  position: fixed;
  padding: 6px 10px;
  background: {surface};
  border: 1px solid {border};
  color: {text};
  font-family: 'Courier New', Courier, monospace;
  font-size: 11px;
  pointer-events: none;
  display: none;
  z-index: 100;
  white-space: nowrap;
  letter-spacing: .05em;
}}
.legend {{
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: center;
  margin-top: 14px;
  font-size: 11px;
  letter-spacing: .1em;
  color: {text2};
}}
.legend-item {{
  display: flex;
  align-items: center;
  gap: 6px;
}}
.legend-dot {{
  width: 10px; height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}}
</style>
</head>
<body>
<div id="chart-wrap">
  <h1>{title}</h1>
  <div class="meta">{subtitle}</div>
  <div class="chart-container">
    <canvas id="chart"></canvas>
  </div>
  <div class="legend" id="legend"></div>
</div>
<div id="tooltip"></div>
<script>
// ── Injected data and config ─────────────────────────────────
const CHART_DATA   = {data_json};
const CHART_CONFIG = {config_json};

// ── Palette ──────────────────────────────────────────────────
const P = {{
  colors:       {colors_json},
  heatLow:      {heat_low_json},
  heatHigh:     {heat_high_json},
  bg:           {bg_json},
  surface:      {surface_json},
  border:       {border_json},
  text:         {text_json},
  text2:        {text2_json},
  text3:        {text3_json},
}};

// ── Utility functions ────────────────────────────────────────
function hexToRgb(hex) {{
  const r = parseInt(hex.slice(1,3),16);
  const g = parseInt(hex.slice(3,5),16);
  const b = parseInt(hex.slice(5,7),16);
  return [r,g,b];
}}
function lerpColor(a, b, t) {{
  const [ar,ag,ab] = hexToRgb(a);
  const [br,bg,bb] = hexToRgb(b);
  const r = Math.round(ar + (br-ar)*t);
  const g = Math.round(ag + (bg-ag)*t);
  const bv= Math.round(ab + (bb-ab)*t);
  return `rgb(${{r}},${{g}},${{bv}})`;
}}
function niceNum(v, loose=false) {{
  const exp = Math.floor(Math.log10(v));
  const f = v / Math.pow(10, exp);
  let nf;
  if (loose) {{
    if      (f < 1.5) nf = 1;
    else if (f < 3)   nf = 2;
    else if (f < 7)   nf = 5;
    else              nf = 10;
  }} else {{
    if      (f <= 1)  nf = 1;
    else if (f <= 2)  nf = 2;
    else if (f <= 5)  nf = 5;
    else              nf = 10;
  }}
  return nf * Math.pow(10, exp);
}}
function niceTicks(min, max, target=5) {{
  const range = niceNum(max - min, true);
  const step  = niceNum(range / (target - 1), false);
  const lo    = Math.floor(min / step) * step;
  const hi    = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step * 0.5; v += step) ticks.push(parseFloat(v.toPrecision(10)));
  return ticks;
}}
function fmtNum(v) {{
  if (Math.abs(v) >= 1e6)  return (v/1e6).toFixed(1)  + 'M';
  if (Math.abs(v) >= 1e3)  return (v/1e3).toFixed(1)  + 'K';
  if (Number.isInteger(v)) return String(v);
  return v.toPrecision(4).replace(/\\.?0+$/, '');
}}

// ── Text helpers ─────────────────────────────────────────────
function measureText(ctx, text, font) {{
  ctx.save();
  if (font) ctx.font = font;
  const w = ctx.measureText(text).width;
  ctx.restore();
  return w;
}}
function drawText(ctx, text, x, y, {{color=P.text, font='11px monospace', align='left', baseline='alphabetic'}}={{}}) {{
  ctx.save();
  ctx.fillStyle = color;
  ctx.font = font;
  ctx.textAlign = align;
  ctx.textBaseline = baseline;
  ctx.fillText(text, x, y);
  ctx.restore();
}}

// ── Tooltip ──────────────────────────────────────────────────
const ttEl = document.getElementById('tooltip');
function showTooltip(e, html) {{
  ttEl.innerHTML  = html;
  ttEl.style.display = 'block';
  positionTooltip(e);
}}
function positionTooltip(e) {{
  if (ttEl.style.display === 'none') return;
  let x = e.clientX + 14, y = e.clientY - 10;
  const w = ttEl.offsetWidth, h = ttEl.offsetHeight;
  if (x + w > window.innerWidth)  x = e.clientX - w - 14;
  if (y + h > window.innerHeight) y = e.clientY - h - 10;
  ttEl.style.left = x + 'px';
  ttEl.style.top  = y + 'px';
}}
function hideTooltip() {{ ttEl.style.display = 'none'; }}

// ── Legend ───────────────────────────────────────────────────
function buildLegend(items) {{
  const el = document.getElementById('legend');
  el.innerHTML = '';
  items.forEach(({{label, color}}) => {{
    const div = document.createElement('div');
    div.className = 'legend-item';
    div.innerHTML = `<span class="legend-dot" style="background:${{color}}"></span><span>${{label}}</span>`;
    el.appendChild(div);
  }});
}}

// ── Axis helpers ─────────────────────────────────────────────
function drawGrid(ctx, bounds, ticks, axis, {{color='rgba(255,255,255,0.05)'}}={{}}) {{
  const {{x, y, w, h}} = bounds;
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth   = 1;
  ctx.setLineDash([3, 4]);
  ticks.forEach(t => {{
    if (axis === 'y') {{
      const gy = y + h - (t - ticks[0]) / (ticks[ticks.length-1] - ticks[0]) * h;
      ctx.beginPath(); ctx.moveTo(x, gy); ctx.lineTo(x+w, gy); ctx.stroke();
    }} else {{
      const gx = x + t * w;
      ctx.beginPath(); ctx.moveTo(gx, y); ctx.lineTo(gx, y+h); ctx.stroke();
    }}
  }});
  ctx.setLineDash([]);
  ctx.restore();
}}

// ═══════════════════════════════════════════════════════════
// BAR CHART
// ═══════════════════════════════════════════════════════════
function renderBar(ctx, canvas, data) {{
  const {{labels, datasets}} = data;
  const n      = labels.length;
  const ns     = datasets.length;
  const margin = {{top:20, right:20, bottom:60, left:60}};
  const W = canvas.width,  H = canvas.height;
  const bx = margin.left, by = margin.top;
  const bw = W - margin.left - margin.right;
  const bh = H - margin.top  - margin.bottom;

  // y-range
  const allVals = datasets.flatMap(d => d.values);
  const yMin = 0, yMax = Math.max(...allVals) * 1.1 || 10;
  const ticks = niceTicks(yMin, yMax);
  const tMin = ticks[0], tMax = ticks[ticks.length-1];

  function yPos(v) {{ return by + bh - (v - tMin) / (tMax - tMin) * bh; }}

  // grid
  const gridColor = P.border + '88';
  ticks.forEach(t => {{
    const gy = yPos(t);
    ctx.save(); ctx.strokeStyle = gridColor; ctx.lineWidth = 1; ctx.setLineDash([3,4]);
    ctx.beginPath(); ctx.moveTo(bx, gy); ctx.lineTo(bx+bw, gy); ctx.stroke();
    ctx.restore();
    drawText(ctx, fmtNum(t), bx-8, gy, {{color:P.text3, align:'right', baseline:'middle'}});
  }});

  // bars
  const groupW   = bw / n;
  const barPad   = groupW * 0.15;
  const barW     = (groupW - 2*barPad) / ns;
  const hitmap   = [];

  datasets.forEach((ds, si) => {{
    const color = P.colors[si % P.colors.length];
    ds.values.forEach((v, i) => {{
      const x  = bx + i * groupW + barPad + si * barW;
      const y0 = yPos(0);
      const y1 = yPos(v);
      const bh2 = Math.abs(y0 - y1);
      ctx.fillStyle = color;
      ctx.fillRect(x, Math.min(y0, y1), barW - 1, bh2);
      hitmap.push({{x, y: Math.min(y0,y1), w: barW-1, h: bh2,
                    label: labels[i], series: ds.name, value: v, color}});
    }});
  }});

  // x-axis labels
  for (let i = 0; i < n; i++) {{
    const lx = bx + i * groupW + groupW/2;
    drawText(ctx, labels[i], lx, by+bh+14, {{color:P.text2, align:'center', baseline:'top'}});
  }}

  // axes
  ctx.strokeStyle = P.border; ctx.lineWidth = 1;
  ctx.strokeRect(bx, by, bw, bh);

  // tooltip
  canvas.onmousemove = e => {{
    const r = canvas.getBoundingClientRect();
    const mx = (e.clientX - r.left) * (canvas.width  / r.width);
    const my = (e.clientY - r.top)  * (canvas.height / r.height);
    const hit = hitmap.find(h => mx >= h.x && mx <= h.x+h.w && my >= h.y && my <= h.y+h.h);
    if (hit) {{
      showTooltip(e, `<b style="color:${{hit.color}}">${{hit.series}}</b><br>${{hit.label}}: ${{fmtNum(hit.value)}}`);
    }} else hideTooltip();
  }};
  canvas.onmouseleave = hideTooltip;
  canvas.onmousemove.toString(); // keep ref

  buildLegend(datasets.map((d,i) => ({{label:d.name, color:P.colors[i%P.colors.length]}})));
}}

// ═══════════════════════════════════════════════════════════
// LINE CHART
// ═══════════════════════════════════════════════════════════
function renderLine(ctx, canvas, data) {{
  const {{labels, datasets}} = data;
  const n      = labels.length;
  const margin = {{top:20, right:20, bottom:60, left:60}};
  const W = canvas.width, H = canvas.height;
  const bx = margin.left, by = margin.top;
  const bw = W - margin.left - margin.right;
  const bh = H - margin.top  - margin.bottom;

  const allVals = datasets.flatMap(d => d.values);
  const yMin = 0, yMax = Math.max(...allVals) * 1.1 || 10;
  const ticks = niceTicks(yMin, yMax);
  const tMin = ticks[0], tMax = ticks[ticks.length-1];

  function xPos(i) {{ return bx + (i / (n-1 || 1)) * bw; }}
  function yPos(v) {{ return by + bh - (v - tMin) / (tMax - tMin) * bh; }}

  // grid
  ticks.forEach(t => {{
    const gy = yPos(t);
    ctx.save(); ctx.strokeStyle = P.border + '66'; ctx.lineWidth=1; ctx.setLineDash([3,4]);
    ctx.beginPath(); ctx.moveTo(bx,gy); ctx.lineTo(bx+bw,gy); ctx.stroke(); ctx.restore();
    drawText(ctx, fmtNum(t), bx-8, gy, {{color:P.text3, align:'right', baseline:'middle'}});
  }});

  const hitmap = [];

  datasets.forEach((ds, si) => {{
    const color = P.colors[si % P.colors.length];
    const pts = ds.values.map((v, i) => ({{x: xPos(i), y: yPos(v), v}}));

    // area fill
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(pts[0].x, by+bh);
    pts.forEach(p => ctx.lineTo(p.x, p.y));
    ctx.lineTo(pts[pts.length-1].x, by+bh);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, by, 0, by+bh);
    grad.addColorStop(0, color + '33');
    grad.addColorStop(1, color + '00');
    ctx.fillStyle = grad;
    ctx.fill();
    ctx.restore();

    // line
    ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = 2;
    ctx.beginPath();
    pts.forEach((p,i) => i===0 ? ctx.moveTo(p.x,p.y) : ctx.lineTo(p.x,p.y));
    ctx.stroke(); ctx.restore();

    // dots
    pts.forEach((p, i) => {{
      ctx.save();
      ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI*2); ctx.fill();
      ctx.strokeStyle = P.bg; ctx.lineWidth = 1.5;
      ctx.stroke(); ctx.restore();
      hitmap.push({{x:p.x, y:p.y, r:10, label:labels[i], series:ds.name, value:p.v, color}});
    }});
  }});

  // x labels
  for (let i = 0; i < n; i++) {{
    drawText(ctx, labels[i], xPos(i), by+bh+14, {{color:P.text2, align:'center', baseline:'top'}});
  }}
  ctx.strokeStyle = P.border; ctx.lineWidth=1; ctx.strokeRect(bx,by,bw,bh);

  canvas.onmousemove = e => {{
    const r = canvas.getBoundingClientRect();
    const mx = (e.clientX-r.left)*(canvas.width/r.width);
    const my = (e.clientY-r.top)*(canvas.height/r.height);
    const hit = hitmap.find(h => Math.hypot(mx-h.x, my-h.y) < h.r);
    if (hit) showTooltip(e, `<b style="color:${{hit.color}}">${{hit.series}}</b><br>${{hit.label}}: ${{fmtNum(hit.value)}}`);
    else hideTooltip();
  }};
  canvas.onmouseleave = hideTooltip;

  buildLegend(datasets.map((d,i) => ({{label:d.name, color:P.colors[i%P.colors.length]}})));
}}

// ═══════════════════════════════════════════════════════════
// PIE CHART
// ═══════════════════════════════════════════════════════════
function renderPie(ctx, canvas, data) {{
  const {{labels, values}} = data;
  const total = values.reduce((a,b)=>a+b, 0) || 1;
  const W = canvas.width, H = canvas.height;
  const cx = W/2, cy = H/2;
  const r = Math.min(W, H) * 0.38;
  const donut = r * 0.5;  // inner radius for donut hole

  const slices = labels.map((l, i) => ({{
    label: l, value: values[i],
    pct: values[i] / total,
    color: P.colors[i % P.colors.length],
  }}));

  let start = -Math.PI / 2;
  const arcs = [];
  slices.forEach(s => {{
    const end = start + s.pct * Math.PI * 2;
    ctx.save();
    ctx.fillStyle = s.color;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, r, start, end);
    ctx.closePath();
    ctx.fill();
    // subtle border
    ctx.strokeStyle = P.bg; ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.restore();
    arcs.push({{start, end, color: s.color, label: s.label, value: s.value, pct: s.pct}});
    start = end;
  }});

  // donut hole
  ctx.save();
  ctx.fillStyle = P.surface;
  ctx.beginPath(); ctx.arc(cx, cy, donut, 0, Math.PI*2); ctx.fill();
  ctx.strokeStyle = P.border; ctx.lineWidth=1; ctx.stroke();
  ctx.restore();

  // center text
  drawText(ctx, fmtNum(total), cx, cy-6, {{color:P.text, font:'bold 18px monospace', align:'center', baseline:'bottom'}});
  drawText(ctx, 'TOTAL', cx, cy+8, {{color:P.text3, font:'10px monospace', align:'center', baseline:'top'}});

  // tooltip
  canvas.onmousemove = e => {{
    const rect = canvas.getBoundingClientRect();
    const mx = (e.clientX-rect.left)*(canvas.width/rect.width) - cx;
    const my = (e.clientY-rect.top)*(canvas.height/rect.height) - cy;
    const dist = Math.hypot(mx, my);
    if (dist < donut || dist > r) {{ hideTooltip(); return; }}
    const angle = (Math.atan2(my, mx) + Math.PI*2 + Math.PI/2) % (Math.PI*2);
    const hit = arcs.find(a => {{
      const s = (a.start + Math.PI*2 + Math.PI/2) % (Math.PI*2);
      const en = (a.end   + Math.PI*2 + Math.PI/2) % (Math.PI*2);
      return en > s ? angle >= s && angle <= en : angle >= s || angle <= en;
    }});
    if (hit) showTooltip(e, `<b style="color:${{hit.color}}">${{hit.label}}</b><br>${{fmtNum(hit.value)}} (${{(hit.pct*100).toFixed(1)}}%)`);
    else hideTooltip();
  }};
  canvas.onmouseleave = hideTooltip;

  buildLegend(slices.map(s => ({{label: `${{s.label}} (${{(s.pct*100).toFixed(1)}}%)`, color: s.color}})));
}}

// ═══════════════════════════════════════════════════════════
// SCATTER PLOT
// ═══════════════════════════════════════════════════════════
function renderScatter(ctx, canvas, data) {{
  const {{points, x_label='X', y_label='Y'}} = data;
  const margin = {{top:20, right:20, bottom:60, left:65}};
  const W = canvas.width, H = canvas.height;
  const bx = margin.left, by = margin.top;
  const bw = W - margin.left - margin.right;
  const bh = H - margin.top  - margin.bottom;

  const xs = points.map(p=>p.x), ys = points.map(p=>p.y);
  const xTicks = niceTicks(Math.min(...xs), Math.max(...xs));
  const yTicks = niceTicks(Math.min(...ys), Math.max(...ys));
  const xMin = xTicks[0], xMax = xTicks[xTicks.length-1];
  const yMin = yTicks[0], yMax = yTicks[yTicks.length-1];

  function px(v) {{ return bx + (v-xMin)/(xMax-xMin)*bw; }}
  function py(v) {{ return by + bh - (v-yMin)/(yMax-yMin)*bh; }}

  // grid
  yTicks.forEach(t => {{
    const gy=py(t); ctx.save(); ctx.strokeStyle=P.border+'66'; ctx.lineWidth=1; ctx.setLineDash([3,4]);
    ctx.beginPath(); ctx.moveTo(bx,gy); ctx.lineTo(bx+bw,gy); ctx.stroke(); ctx.restore();
    drawText(ctx,fmtNum(t),bx-8,gy,{{color:P.text3,align:'right',baseline:'middle'}});
  }});
  xTicks.forEach(t => {{
    const gx=px(t); ctx.save(); ctx.strokeStyle=P.border+'66'; ctx.lineWidth=1; ctx.setLineDash([3,4]);
    ctx.beginPath(); ctx.moveTo(gx,by); ctx.lineTo(gx,by+bh); ctx.stroke(); ctx.restore();
    drawText(ctx,fmtNum(t),gx,by+bh+14,{{color:P.text2,align:'center',baseline:'top'}});
  }});

  // axis labels
  drawText(ctx, x_label, bx+bw/2, by+bh+40, {{color:P.text2, align:'center'}});
  ctx.save(); ctx.translate(bx-45, by+bh/2); ctx.rotate(-Math.PI/2);
  drawText(ctx, y_label, 0, 0, {{color:P.text2, align:'center'}});
  ctx.restore();

  // points
  points.forEach(p => {{
    const x=px(p.x), y=py(p.y);
    ctx.save();
    ctx.fillStyle = P.colors[0];
    ctx.beginPath(); ctx.arc(x,y,5,0,Math.PI*2); ctx.fill();
    ctx.strokeStyle=P.bg; ctx.lineWidth=1; ctx.stroke();
    ctx.restore();
  }});

  ctx.strokeStyle=P.border; ctx.lineWidth=1; ctx.strokeRect(bx,by,bw,bh);

  canvas.onmousemove = e => {{
    const r=canvas.getBoundingClientRect();
    const mx=(e.clientX-r.left)*(canvas.width/r.width);
    const my=(e.clientY-r.top)*(canvas.height/r.height);
    const hit = points.find(p => Math.hypot(mx-px(p.x), my-py(p.y)) < 9);
    if (hit) showTooltip(e, `${{hit.label||''}}<br>${{x_label}}: ${{fmtNum(hit.x)}} | ${{y_label}}: ${{fmtNum(hit.y)}}`);
    else hideTooltip();
  }};
  canvas.onmouseleave = hideTooltip;
}}

// ═══════════════════════════════════════════════════════════
// HEATMAP
// ═══════════════════════════════════════════════════════════
function renderHeatmap(ctx, canvas, data) {{
  const {{rows, cols, values}} = data;
  const nr=rows.length, nc=cols.length;
  const margin = {{top:20, right:20, bottom:80, left:80}};
  const W=canvas.width, H=canvas.height;
  const bx=margin.left, by=margin.top;
  const bw=W-margin.left-margin.right;
  const bh=H-margin.top-margin.bottom;
  const cw=bw/nc, ch=bh/nr;

  const flat = values.flat();
  const vMin = Math.min(...flat), vMax = Math.max(...flat) || 1;

  values.forEach((row, ri) => {{
    row.forEach((v, ci) => {{
      const t = (v-vMin)/(vMax-vMin);
      ctx.fillStyle = lerpColor(P.heatLow, P.heatHigh, t);
      ctx.fillRect(bx+ci*cw, by+ri*ch, cw-1, ch-1);
    }});
  }});

  // labels
  cols.forEach((c,ci) => drawText(ctx,c, bx+ci*cw+cw/2, by+bh+14, {{color:P.text2,align:'center',baseline:'top'}}));
  rows.forEach((r,ri) => drawText(ctx,r, bx-8, by+ri*ch+ch/2, {{color:P.text2,align:'right',baseline:'middle'}}));

  ctx.strokeStyle=P.border; ctx.lineWidth=1; ctx.strokeRect(bx,by,bw,bh);

  canvas.onmousemove = e => {{
    const rect=canvas.getBoundingClientRect();
    const mx=(e.clientX-rect.left)*(canvas.width/rect.width)-bx;
    const my=(e.clientY-rect.top)*(canvas.height/rect.height)-by;
    if (mx<0||my<0||mx>bw||my>bh) {{ hideTooltip(); return; }}
    const ci=Math.floor(mx/cw), ri=Math.floor(my/ch);
    if (ri<nr && ci<nc) showTooltip(e,`${{rows[ri]}} × ${{cols[ci]}}<br>${{fmtNum(values[ri][ci])}}`);
    else hideTooltip();
  }};
  canvas.onmouseleave=hideTooltip;

  // color scale bar
  const scW=160, scH=10, scX=bx+bw-scW, scY=by+bh+55;
  const grad=ctx.createLinearGradient(scX,0,scX+scW,0);
  grad.addColorStop(0,P.heatLow);
  grad.addColorStop(1,P.heatHigh);
  ctx.fillStyle=grad; ctx.fillRect(scX,scY,scW,scH);
  drawText(ctx,fmtNum(vMin),scX-4,scY+5,{{color:P.text3,align:'right',baseline:'middle'}});
  drawText(ctx,fmtNum(vMax),scX+scW+4,scY+5,{{color:P.text3,align:'left',baseline:'middle'}});
}}

// ═══════════════════════════════════════════════════════════
// TIMELINE (Gantt)
// ═══════════════════════════════════════════════════════════
function renderTimeline(ctx, canvas, data) {{
  const tasks = data.tasks || [];
  const statusColors = {{
    done:    P.colors[0],
    active:  P.colors[1],
    pending: P.text3,
    default: P.colors[2],
  }};

  // Parse dates or numeric offsets
  function parseTime(v) {{
    if (typeof v === 'number') return v;
    const d = new Date(v);
    return isNaN(d) ? parseFloat(v) : d.getTime();
  }}
  const starts = tasks.map(t => parseTime(t.start));
  const ends   = tasks.map(t => parseTime(t.end));
  const tMin   = Math.min(...starts), tMax = Math.max(...ends);
  const tRange = tMax - tMin || 1;

  const margin = {{top:20, right:20, bottom:40, left:120}};
  const W=canvas.width, H=canvas.height;
  const bx=margin.left, by=margin.top;
  const bw=W-margin.left-margin.right;
  const bh=H-margin.top-margin.bottom;
  const rowH = Math.min(36, bh/tasks.length);

  function tx(t) {{ return bx + (parseTime(t)-tMin)/tRange*bw; }}

  // gridlines (5 ticks)
  for (let i=0; i<=4; i++) {{
    const gx = bx + (i/4)*bw;
    ctx.save(); ctx.strokeStyle=P.border+'66'; ctx.lineWidth=1; ctx.setLineDash([3,4]);
    ctx.beginPath(); ctx.moveTo(gx,by); ctx.lineTo(gx,by+bh); ctx.stroke(); ctx.restore();
  }}

  tasks.forEach((t, ri) => {{
    const y = by + ri * rowH;
    const sx = tx(t.start), ex = tx(t.end);
    const barW = Math.max(ex-sx, 4);
    const barH = rowH * 0.55;
    const barY = y + rowH * 0.2;
    const color = statusColors[t.status] || statusColors.default;

    ctx.fillStyle = color + '33';
    ctx.fillRect(sx, barY, barW, barH);
    ctx.fillStyle = color;
    ctx.fillRect(sx, barY, 3, barH);

    drawText(ctx, t.task || `Task ${{ri+1}}`, bx-8, y+rowH/2,
             {{color:P.text2, align:'right', baseline:'middle'}});
    if (barW > 40) {{
      drawText(ctx, t.status || '', sx+6, barY+barH/2,
               {{color, align:'left', baseline:'middle', font:'10px monospace'}});
    }}
  }});

  ctx.strokeStyle=P.border; ctx.lineWidth=1; ctx.strokeRect(bx,by,bw,bh);

  canvas.onmousemove = e => {{
    const rect=canvas.getBoundingClientRect();
    const mx=(e.clientX-rect.left)*(canvas.width/rect.width);
    const my=(e.clientY-rect.top)*(canvas.height/rect.height)-by;
    const ri=Math.floor(my/rowH);
    if (ri>=0 && ri<tasks.length && mx>=bx && mx<=bx+bw) {{
      const t=tasks[ri];
      showTooltip(e,`<b>${{t.task}}</b><br>Start: ${{t.start}}<br>End: ${{t.end}}${{t.status?'<br>Status: '+t.status:''}}`);
    }} else hideTooltip();
  }};
  canvas.onmouseleave=hideTooltip;

  buildLegend(Object.entries(statusColors).map(([k,c])=>({{label:k.toUpperCase(),color:c}})));
}}

// ═══════════════════════════════════════════════════════════
// DASHBOARD (multi-chart)
// ═══════════════════════════════════════════════════════════
function renderDashboard(canvasEl, charts) {{
  // Render each sub-chart into its own off-screen canvas, then tile them
  const wrap = document.getElementById('chart-wrap');
  canvasEl.style.display = 'none'; // hide the main canvas

  const container = document.createElement('div');
  container.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:16px;width:100%;max-width:1200px;margin-top:8px';

  charts.forEach(spec => {{
    const div = document.createElement('div');
    div.style.cssText = `background:${{P.surface}};border:1px solid ${{P.border}};padding:12px`;
    const h = document.createElement('h3');
    h.style.cssText = `font-size:12px;letter-spacing:.15em;color:${{P.text2}};margin-bottom:10px;text-transform:uppercase`;
    h.textContent = spec.title || spec.type;
    div.appendChild(h);

    const cv = document.createElement('canvas');
    cv.width = 500; cv.height = 280;
    div.appendChild(cv);
    const ctx2 = cv.getContext('2d');
    ctx2.fillStyle = P.surface;
    ctx2.fillRect(0,0,cv.width,cv.height);

    const legend = document.createElement('div');
    legend.className = 'legend';
    div.appendChild(legend);

    // Temporarily override buildLegend to target this legend element
    const origBL = buildLegend;
    window.buildLegend = items => {{
      legend.innerHTML = '';
      items.forEach(({{label,color}}) => {{
        const li = document.createElement('div');
        li.className = 'legend-item';
        li.innerHTML = `<span class="legend-dot" style="background:${{color}}"></span><span>${{label}}</span>`;
        legend.appendChild(li);
      }});
    }};

    dispatchRender(ctx2, cv, spec.type, spec.data);
    window.buildLegend = origBL;

    container.appendChild(div);
  }});

  wrap.appendChild(container);
}}

// ═══════════════════════════════════════════════════════════
// DISPATCH
// ═══════════════════════════════════════════════════════════
function dispatchRender(ctx, canvas, type, data) {{
  ctx.fillStyle = P.surface;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  switch(type) {{
    case 'bar':      renderBar(ctx, canvas, data);       break;
    case 'line':     renderLine(ctx, canvas, data);      break;
    case 'pie':      renderPie(ctx, canvas, data);       break;
    case 'scatter':  renderScatter(ctx, canvas, data);   break;
    case 'heatmap':  renderHeatmap(ctx, canvas, data);   break;
    case 'timeline': renderTimeline(ctx, canvas, data);  break;
    default:
      ctx.fillStyle = '#ff2a2a';
      ctx.fillText('Unknown chart type: ' + type, 20, 40);
  }}
}}

// ── Bootstrap ────────────────────────────────────────────────
window.addEventListener('load', () => {{
  const canvas = document.getElementById('chart');
  if (CHART_CONFIG.type === 'dashboard') {{
    renderDashboard(canvas, CHART_DATA.charts || []);
    return;
  }}
  // Size canvas for DPR sharpness
  const wrap   = canvas.parentElement;
  const dpr    = window.devicePixelRatio || 1;
  const cssW   = wrap.clientWidth  - 32;
  const cssH   = Math.max(360, Math.round(cssW * 0.56));
  canvas.width  = cssW  * dpr;
  canvas.height = cssH  * dpr;
  canvas.style.width  = cssW  + 'px';
  canvas.style.height = cssH  + 'px';
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  dispatchRender(ctx, {{width:cssW, height:cssH,
                        onmousemove: null, onmouseleave: null,
                        _real: canvas}}, CHART_CONFIG.type, CHART_DATA);
  // wire real canvas events if dispatchRender set them
  if (canvas._handler) {{
    canvas.onmousemove  = canvas._handler.move;
    canvas.onmouseleave = canvas._handler.leave;
  }}
  // Fixup: canvas passed to renderers is logical-px sized object; re-wire events directly
  // (renderers set .onmousemove on the passed object — we use the real canvas)
  document.getElementById('chart').addEventListener('mousemove', e => {{
    const h = document.getElementById('chart').onmousemove;
    if (h) h(e);
  }});
  document.getElementById('chart').addEventListener('mouseleave', () => hideTooltip());
}});
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _render_single(
    action: str,
    normalized_data: Any,
    title: str,
    palette: dict,
    output_path: Path,
) -> Path:
    """Render a single-chart HTML file and write to output_path. Returns the path."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    subtitle = f"{action.upper()} CHART  ·  GENERATED {now}"

    def _jq(v) -> str:
        """JSON-encode a value for safe embedding in JavaScript."""
        return json.dumps(v)

    html = _HTML_WRAPPER.format(
        title=title,
        subtitle=subtitle,
        bg=palette["bg"],
        surface=palette["surface"],
        border=palette["border"],
        text=palette["text"],
        text2=palette["text2"],
        text3=palette["text3"],
        heading=palette["heading"],
        data_json=json.dumps(normalized_data, ensure_ascii=False),
        config_json=json.dumps({"type": action}),
        colors_json=json.dumps(palette["colors"]),
        heat_low_json=_jq(palette["heatmap_low"]),
        heat_high_json=_jq(palette["heatmap_high"]),
        bg_json=_jq(palette["bg"]),
        surface_json=_jq(palette["surface"]),
        border_json=_jq(palette["border"]),
        text_json=_jq(palette["text"]),
        text2_json=_jq(palette["text2"]),
        text3_json=_jq(palette["text3"]),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def _count_series_and_points(action: str, normalized: Any) -> tuple[int, int]:
    """Return (series_count, data_points) for the normalized data structure."""
    if action in ("bar", "line"):
        ds = normalized.get("datasets", [])
        pts = len(normalized.get("labels", []))
        return len(ds), pts
    if action == "pie":
        n = len(normalized.get("labels", []))
        return 1, n
    if action == "scatter":
        pts = len(normalized.get("points", []))
        return 1, pts
    if action == "heatmap":
        rows = normalized.get("rows", [])
        cols = normalized.get("cols", [])
        return len(rows), len(rows) * len(cols)
    if action == "timeline":
        tasks = normalized.get("tasks", [])
        return 1, len(tasks)
    if action == "dashboard":
        charts = normalized.get("charts", [])
        return len(charts), sum(
            len(c.get("data", {}).get("labels", c.get("data", {}).get("points", []))) for c in charts
        )
    return 1, 0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def data_visualizer(
    action: str,
    data: Optional[str] = None,
    data_file: Optional[str] = None,
    title: str = "Visualization",
    x_field: Optional[str] = None,
    y_field: Optional[str] = None,
    color_scheme: str = "tactical",
    output_path: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """
    Generate an interactive, self-contained HTML visualization.

    Args:
        action:        Chart type — bar | line | pie | scatter | heatmap | timeline | dashboard
        data:          JSON string with the chart data (see module docstring for shapes).
        data_file:     Path to a .json or .csv file (alternative to 'data').
        title:         Chart title displayed at the top.
        x_field:       Field name for X axis / labels (auto-detected if omitted).
        y_field:       Field name(s) for Y values, comma-separated (auto-detected if omitted).
        color_scheme:  'tactical' | 'dark' | 'vibrant' | 'light'.
        output_path:   Where to write the .html file (defaults to CWD).
        session_id:    Optional log_manager session ID.

    Returns:
        dict with status, file path, size_bytes, chart_type, series_count, data_points.
    """
    # ── Validate action ──────────────────────────────────────────────────────
    VALID_ACTIONS = {"bar", "line", "pie", "scatter", "heatmap", "timeline", "dashboard"}
    if action not in VALID_ACTIONS:
        return {
            "status": "error",
            "action": action,
            "error": f"Unknown action '{action}'. Valid: {sorted(VALID_ACTIONS)}",
            "hint": "Use one of: bar, line, pie, scatter, heatmap, timeline, dashboard",
        }

    # ── Load palette ─────────────────────────────────────────────────────────
    palette = _PALETTES.get(color_scheme, _PALETTES["tactical"])

    # ── Load raw data ────────────────────────────────────────────────────────
    try:
        # Dashboard can operate without data if charts already contain embedded data
        if action == "dashboard" and not data and not data_file:
            raw = {"charts": []}
        else:
            raw = _load_data(data, data_file)
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as exc:
        return {
            "status": "error",
            "action": action,
            "error": str(exc),
            "hint": "Provide 'data' as a JSON string or 'data_file' as a path to a .json/.csv file.",
        }

    # ── Normalize ────────────────────────────────────────────────────────────
    try:
        if action in ("bar", "line"):
            normalized = _normalize_bar_line(raw, x_field, y_field)
        elif action == "pie":
            normalized = _normalize_pie(raw, x_field, y_field)
        elif action == "scatter":
            normalized = _normalize_scatter(raw, x_field, y_field)
        elif action == "heatmap":
            normalized = _normalize_heatmap(raw)
        elif action == "timeline":
            normalized = _normalize_timeline(raw)
        elif action == "dashboard":
            # raw should be {"charts": [{type, title, data}, ...]} or a list
            if isinstance(raw, list):
                normalized = {"charts": raw}
            elif isinstance(raw, dict) and "charts" in raw:
                normalized = raw
            else:
                return {
                    "status": "error",
                    "action": action,
                    "error": "Dashboard data must be {\"charts\": [{\"type\", \"title\", \"data\"}, ...]}",
                    "hint": "Each item in 'charts' needs a 'type' and 'data' key.",
                }
    except (ValueError, KeyError, IndexError) as exc:
        return {
            "status": "error",
            "action": action,
            "error": f"Data normalization failed: {exc}",
            "hint": "Check that your data matches the expected shape for this chart type.",
        }

    # ── Resolve output path ──────────────────────────────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = title.replace(" ", "_")[:40]
    file_name = f"{ts}_{safe_title}_{action}.html"

    if output_path:
        out = Path(output_path)
        # If caller passed a directory, append the filename
        if out.is_dir() or not out.suffix:
            out = out / file_name
    else:
        out = Path.cwd() / file_name

    # ── Render HTML ──────────────────────────────────────────────────────────
    try:
        _render_single(action, normalized, title, palette, out)
    except OSError as exc:
        return {
            "status": "error",
            "action": action,
            "error": f"Failed to write output file: {exc}",
            "hint": f"Check that the directory exists and is writable: {out.parent}",
        }

    series_count, data_points = _count_series_and_points(action, normalized)
    size_bytes = out.stat().st_size
    log.info(
        "data_visualizer: wrote %s chart to %s (%d bytes, %d series, %d points)",
        action, out, size_bytes, series_count, data_points,
    )

    return {
        "status": "success",
        "action": action,
        "chart_type": action,
        "file": str(out.resolve()),
        "file_name": out.name,
        "size_bytes": size_bytes,
        "series_count": series_count,
        "data_points": data_points,
        "color_scheme": color_scheme,
        "title": title,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse

    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Generate data visualizations as self-contained HTML.")
    parser.add_argument("--action",     required=True, help="Chart type: bar|line|pie|scatter|heatmap|timeline|dashboard")
    parser.add_argument("--data",       help="JSON string of chart data")
    parser.add_argument("--data_file",  help="Path to .json or .csv file")
    parser.add_argument("--title",      default="Visualization", help="Chart title")
    parser.add_argument("--x_field",    help="X-axis field name")
    parser.add_argument("--y_field",    help="Y-axis field name(s), comma-separated")
    parser.add_argument("--color_scheme", default="tactical", help="tactical|dark|vibrant|light")
    parser.add_argument("--output_path", help="Output directory or file path")
    parser.add_argument("--session_id", help="Session ID for logging")
    args = parser.parse_args()

    result = data_visualizer(
        action=args.action,
        data=args.data,
        data_file=args.data_file,
        title=args.title,
        x_field=args.x_field,
        y_field=args.y_field,
        color_scheme=args.color_scheme,
        output_path=args.output_path,
        session_id=args.session_id,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
