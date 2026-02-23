# Web Scraper Tool v2.0 - Usage Guide

**Agent**: AGNT_WSC_09 (Web Scraper Specialist)
**Tool**: `web_scraper` | **Agent Prompt**: `agents/web_scraper_specialist.md`

---

## Quick Reference

```bash
TOOL="python tools/python/web_scraper.py"

# 1. DETECT what a page is before scraping
$TOOL --action detect_type --url "https://example.com"

# 2. FULL SCRAPE with auto-detection
$TOOL --action scrape_full --url "https://example.com" --extract_mode auto

# 3. ARTICLE extraction (reader mode)
$TOOL --action extract_article --url "https://blog.example.com/post"

# 4. TEXT only
$TOOL --action extract_text --url "https://example.com"

# 5. IMAGES only
$TOOL --action download_images --url "https://example.com" --max_images 20

# 6. STRUCTURE analysis
$TOOL --action analyze_structure --url "https://example.com"

# 7. SUMMARIZE
$TOOL --action summarize --url "https://example.com"

# 8. WEB SEARCH
$TOOL --action search --query "topic" --max_results 10

# 9. FIND RSS FEEDS
$TOOL --action find_feeds --url "https://example.com"

# 10. PARSE FEED entries
$TOOL --action parse_feed --url "https://example.com/feed.xml" --max_entries 20

# 11. VALIDATE URL
$TOOL --action validate_url --url "example.com"
```

---

## How the Agent Should Use This Tool

### The Detect-Then-Extract Pattern

This is the core workflow. **Always detect before scraping an unknown URL:**

```
Step 1: detect_type → returns content type + confidence + recommendation
Step 2: Agent reviews the result
Step 3: Agent picks the best extract_mode (or follows recommendation)
Step 4: scrape_full / extract_article / extract_text / etc.
```

**Example agent reasoning:**
```
Agent receives: "Scrape this URL: https://news-site.com/article/123"
Agent runs: detect_type → {type: "article", confidence: 0.8, mode: "article"}
Agent decides: confidence is high, use extract_article
Agent runs: extract_article → clean article text with title/author/date
```

**When confidence is low:**
```
Agent receives: "Scrape this URL: https://weird-site.com/page"
Agent runs: detect_type → {type: "generic", confidence: 0.3, note: "LOW CONFIDENCE..."}
Agent reasons: metadata shows images=30, code_blocks=0, lists=2
Agent decides: looks like a media gallery, try images_only
Agent runs: scrape_full --extract_mode images_only
```

---

## Extract Modes Explained

### `auto` (default)
Runs content detection internally and routes to the best mode. Use this when the agent doesn't want to do manual detection first. Note: `auto` picks ONE mode (article OR structured OR raw, etc.) — it does not run them all.

### `full`
**Maximum data extraction.** Runs EVERY extractor simultaneously:
- Reader-mode article metadata (title, author, date, body)
- Clean text extraction
- Structured data (tables with headers/rows, links with text/href)
- Image downloading (always enabled)
- Summary generation

Use `full` when you want everything from a page regardless of type, or when `auto` picked the wrong mode and you don't want to guess. This is the "give me absolutely everything" option.

**`full` vs `auto`:** `auto` picks one strategy. `full` runs them all.
**`full` vs `raw`:** `full` runs every smart extractor. `raw` skips smart extraction and just dumps text.

### `article`
**Reader mode.** Strips all noise (nav, sidebar, ads, comments, related posts) and isolates the main content body. Extracts article metadata (title, author, publish date, featured image). Best for news, blogs, essays, and any page with a single main article.

### `structured`
Extracts text AND structured data: tables (with headers + rows), links (with text + href), heading hierarchy. Best for documentation, API references, product specs, comparison pages.

### `images_only`
Skips text extraction entirely, focuses on finding and downloading images. Filters out tracking pixels, spacers, and tiny icons automatically. Best for galleries, product photo pages.

### `raw`
Extracts text with minimal filtering. No noise removal, no reader mode, no structured data parsing. Use this as a **last resort fallback** when `full` or other modes break on unusual page structures (forums, SPAs, heavily interactive sites).

---

## Cascading Fallbacks

The tool never gives up on a single failure. Every layer has a backup:

```
FETCH:
  Selenium (JS rendered) → urllib (static HTML) → requests library

TEXT EXTRACTION:
  BeautifulSoup (accurate) → Regex parsing (basic)

READER MODE:
  Content-score algorithm (BS4) → Regex noise-strip (basic)

IMAGES:
  Download each → skip failures → report what worked + what didn't

CONTENT DETECTION:
  15 heuristic rules → fallback to "generic" → agent overrides

ENCODING:
  Unicode NFC normalize → smart replacement map → ensure_ascii fallback
```

---

## Content Type Detection Heuristics

The `detect_type` action checks 15 signals:

| Signal | What It Detects | Types It Scores |
|--------|----------------|-----------------|
| `<article>` tag | Article structure | article +4 |
| Byline/author class | Attribution | article +3 |
| Publish date patterns | Temporal content | article +2 |
| `og:type="article"` | Social meta | article +3 |
| Schema.org Article | Structured data | article +4 |
| Schema.org Product | Structured data | product +5 |
| Price / add-to-cart | Commerce signals | product +3 |
| Code blocks (5+) | Technical content | documentation +4 |
| docs/reference URL | Documentation URLs | documentation +4 |
| Doc-nav classes | Navigation structure | documentation +3 |
| Thread/forum classes | Community content | forum +4 |
| High image ratio | Image-heavy pages | media_gallery +4 |
| Gallery/carousel class | Gallery UX | media_gallery +3 |
| CTA/hero elements | Marketing pages | landing_page +3 |
| RSS/Atom feed links | News capability | news +1 |

---

## Dependencies

### Required: None (works with Python stdlib only)

### Recommended (install for full capability):
```bash
pip install beautifulsoup4    # Better text extraction + reader mode
pip install selenium          # JavaScript-rendered pages
pip install duckduckgo-search # Web search
pip install requests          # Fallback HTTP client
pip install Pillow            # Image dimension validation
```

The tool reports available capabilities in every `detect_type` response:
```json
"capabilities": {
  "bs4": true,
  "selenium": true,
  "requests": true,
  "pil": true
}
```

---

## Output Examples

### detect_type
```json
{
  "detection": {
    "detected_type": "documentation",
    "confidence": 1.0,
    "signals": [
      {"signal": "code_blocks_19", "score": 4},
      {"signal": "docs_url_pattern", "score": 4},
      {"signal": "docs_nav_class", "score": 3}
    ],
    "recommended_extract_mode": "structured",
    "agent_note": "HIGH CONFIDENCE: ..."
  },
  "metadata": {"title": "Python Tutorial", ...},
  "structure": {"headings": {"h1": 1, "h2": 8}, "code_blocks": 19, ...}
}
```

### extract_article
```json
{
  "article": {
    "title": "Article Title",
    "author": "Author Name",
    "publish_date": "2026-02-22",
    "featured_image": "https://...",
    "body_text": "Clean article text...",
    "word_count": 2500,
    "extraction_method": "reader_mode_scored"
  }
}
```

### scrape_full (with detection)
```json
{
  "status": "completed",
  "fetch_method": "urllib",
  "extract_mode": "structured",
  "detection": {"detected_type": "documentation", "confidence": 1.0},
  "text": {"full_text": "...", "word_count": 5887},
  "tables": [{"headers": [...], "rows": [...]}],
  "links_found": 92,
  "images_downloaded": 3,
  "summary": "...",
  "warnings": []
}
```

---

## Common Patterns for AI Agents

### "Get me the latest news from this site"
```bash
$TOOL --action find_feeds --url "https://news-site.com"
$TOOL --action parse_feed --url "DISCOVERED_FEED_URL" --max_entries 10
# For each interesting entry:
$TOOL --action extract_article --url "ENTRY_LINK"
```

### "Grab all the images from this page"
```bash
$TOOL --action download_images --url "https://example.com" --max_images 50
```

### "Summarize this article for me"
```bash
$TOOL --action summarize --url "https://example.com/article" --max_summary_length 300
```

### "What kind of page is this?"
```bash
$TOOL --action detect_type --url "https://unknown-site.com/page"
```

### "Scrape this documentation page with all its code examples and tables"
```bash
$TOOL --action scrape_full --url "https://docs.example.com/api" --extract_mode structured
```

### "Get everything from this page, I'm not sure what's on it"
```bash
$TOOL --action scrape_full --url "https://example.com" --extract_mode full
```

---

## Files Reference

| File | Purpose |
|------|---------|
| `tools/python/web_scraper.py` | Implementation (~750 lines) |
| `tools/defs/web_scraper.json` | Tool schema (parameters + actions) |
| `agents/web_scraper_specialist.md` | Agent prompt + workflow guide |
| `WEB_SCRAPER_README.md` | This usage document |

---

**Last Updated**: February 22, 2026 | **Version**: 2.0
