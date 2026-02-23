# Web Scraper Tool - Complete Reference

**Agent**: AGNT_WSC_10 (Web Scraper Specialist)
**Tool**: `web_scraper` (unified web operations tool)
**Version**: 1.0.0
**Status**: Production Ready (Baseline)

---

## Overview

The Web Scraper tool is a comprehensive, production-grade solution for all web-based operations:
- **Web Search**: Find information across the internet
- **Feed Discovery & Parsing**: Monitor RSS/Atom feeds for updates
- **Content Scraping**: Extract text, images, metadata, and structure from any website
- **Dynamic Rendering**: Handle JavaScript-rendered content
- **Intelligent Cleanup**: Remove boilerplate and focus on meaningful content
- **Error Resilience**: Graceful degradation when features unavailable

---

## Installation & Dependencies

### Core (Built-in)
The tool works with Python standard library only:
- `urllib` - HTTP requests
- `xml.etree.ElementTree` - XML/RSS parsing
- `re` - Text parsing
- `json` - Output formatting

### Optional (Highly Recommended)
For enhanced functionality, install:

```bash
# For better HTML parsing and text extraction
pip install beautifulsoup4

# For JavaScript rendering (dynamic content)
pip install selenium webdriver-manager

# For web search (instead of fallback)
pip install duckduckgo-search
```

---

## Quick Start Examples

### 1. Search for Information
```bash
python tools/python/web_scraper.py \
  --action search \
  --query "FastAPI tutorial 2026" \
  --max_results 10
```

### 2. Find RSS Feeds on a Website
```bash
python tools/python/web_scraper.py \
  --action find_feeds \
  --url "https://blog.example.com"
```

### 3. Get Latest Feed Entries
```bash
python tools/python/web_scraper.py \
  --action parse_feed \
  --url "https://blog.example.com/feed.xml" \
  --max_entries 20
```

### 4. Extract Text from a Page
```bash
python tools/python/web_scraper.py \
  --action extract_text \
  --url "https://example.com/article" \
  --output_dir ./articles/example
```

### 5. Full Page Scrape with Images
```bash
python tools/python/web_scraper.py \
  --action scrape_full \
  --url "https://example.com/product" \
  --output_dir ./products/example \
  --download_images true \
  --max_images 30
```

### 6. Analyze Page Structure
```bash
python tools/python/web_scraper.py \
  --action analyze_structure \
  --url "https://example.com" \
  --output_dir ./analysis
```

---

## All Actions Reference

### Search Actions

#### `search` - Web Search
Find information across the web using DuckDuckGo.

**Parameters:**
- `--query` (required) - Search query string
- `--max_results` - Max results to return (default: 10)
- `--output_dir` - Optional directory to save results
- `--session_id` - Optional session ID for logging

**Output:**
```json
{
  "status": "completed",
  "query": "your search",
  "results_found": 10,
  "results": [
    {
      "title": "Result Title",
      "url": "https://example.com",
      "description": "Result snippet...",
      "source": "duckduckgo"
    }
  ]
}
```

#### `find_feeds` - Discover Feeds
Discover RSS/Atom feeds on a website.

**Parameters:**
- `--url` (required) - Website URL
- `--output_dir` - Optional directory to save results
- `--session_id` - Optional session ID for logging

**Output:**
```json
{
  "status": "completed",
  "url": "https://example.com",
  "feeds_found": 5,
  "feeds": [
    {
      "url": "https://example.com/feed.xml",
      "type": "RSS/Atom",
      "discovered_from": "https://example.com"
    }
  ]
}
```

#### `parse_feed` - Parse Feed Entries
Extract entries from an RSS/Atom feed.

**Parameters:**
- `--url` (required) - Feed URL (RSS/Atom XML)
- `--max_entries` - Max entries to return (default: 20)
- `--output_dir` - Optional directory to save results
- `--session_id` - Optional session ID for logging

**Output:**
```json
{
  "status": "completed",
  "url": "https://example.com/feed.xml",
  "entries_found": 20,
  "entries": [
    {
      "title": "Entry Title",
      "link": "https://example.com/entry",
      "description": "Entry summary...",
      "pub_date": "Wed, 22 Feb 2026 12:00:00 +0000",
      "type": "RSS"
    }
  ]
}
```

### Scraping Actions

#### `scrape_full` - Complete Page Extraction
Extract everything from a page: text, metadata, images, structure, summary.

**Parameters:**
- `--url` (required) - Target URL
- `--output_dir` - Optional output directory (auto-generated if not provided)
- `--wait_for_js` - Wait for JavaScript rendering (default: true)
- `--wait_timeout` - JS rendering timeout in seconds (default: 10)
- `--download_images` - Download images from page (default: true)
- `--max_images` - Max images to download (default: 50)
- `--clean_text` - Remove boilerplate from text (default: true)
- `--summarize` - Generate summary (default: true)
- `--max_summary_length` - Summary length in words (default: 500)
- `--extract_tables` - Extract tables as structured data (default: true)
- `--include_metadata` - Extract metadata like title, author (default: true)
- `--session_id` - Optional session ID for logging

**Output Structure:**
```
output_dir/
├── scrape_result.json         # Complete result summary
├── text_content.json          # Extracted text
├── summary.json               # Generated summary
├── images_manifest.json       # Image metadata
├── tables.json                # Extracted tables (if found)
├── raw_content.html           # Original HTML
└── images/                    # Downloaded images
    ├── image_001.jpg
    ├── image_002.png
    └── ...
```

#### `extract_text` - Text Only Extraction
Fast extraction of text content without images or downloads.

**Parameters:**
- `--url` (required) - Target URL
- `--output_dir` - Optional output directory
- `--wait_for_js` - Wait for JavaScript rendering (default: true)
- `--clean_text` - Remove boilerplate (default: true)
- `--session_id` - Optional session ID for logging

#### `download_images` - Image Download Only
Download all images from a page.

**Parameters:**
- `--url` (required) - Target URL
- `--output_dir` - Optional output directory
- `--max_images` - Max images to download (default: 50)
- `--session_id` - Optional session ID for logging

#### `analyze_structure` - Structure Analysis
Understand page layout without downloading content.

**Parameters:**
- `--url` (required) - Target URL
- `--output_dir` - Optional output directory
- `--session_id` - Optional session ID for logging

**Output:**
```json
{
  "status": "completed",
  "url": "https://example.com",
  "metadata": {
    "title": "Page Title",
    "description": "...",
    "author": "...",
    "og_image": "..."
  },
  "structure": {
    "headings": {"h1": 5, "h2": 12, "h3": 8},
    "lists": 4,
    "tables": 2,
    "forms": 1,
    "images": 15,
    "links": 42,
    "videos": 0,
    "code_blocks": 3
  }
}
```

#### `summarize` - Content Summarization
Generate a text summary from page content.

**Parameters:**
- `--url` (required) - Target URL
- `--output_dir` - Optional output directory
- `--max_summary_length` - Summary length in words (default: 500)
- `--wait_for_js` - Wait for JavaScript (default: true)
- `--session_id` - Optional session ID for logging

### Utility Actions

#### `validate_url` - URL Validation
Verify and normalize a URL.

**Parameters:**
- `--url` (required) - URL to validate
- `--session_id` - Optional session ID for logging

**Output:**
```json
{
  "status": "completed",
  "url": "example.com",
  "valid": true,
  "normalized_url": "https://example.com",
  "error": null
}
```

---

## Real-World Usage Patterns

### Pattern 1: Research & Aggregation
1. Search for a topic: `search --query "topic"`
2. For each promising result, extract text: `extract_text --url "..."`
3. Aggregate findings in a document
4. Optional: Generate summaries for each page

### Pattern 2: Content Monitoring
1. Find feeds on sites of interest: `find_feeds --url "..."`
2. Set up a cron job to periodically: `parse_feed --url "..."`
3. Aggregate new entries
4. Alert on topics of interest

### Pattern 3: Data Collection
1. Find pages with relevant data: `search --query "..."`
2. For each page, run full scrape: `scrape_full --url "..."`
3. Extract tables with `--extract_tables true`
4. Organize outputs by category
5. Post-process for analysis

### Pattern 4: Documentation Review
1. Identify documentation sites
2. Find feeds for updates: `find_feeds --url "..."`
3. Periodically scrape key pages: `scrape_full --url "..."`
4. Maintain archive of versions
5. Track changes over time

### Pattern 5: Product/Competitor Analysis
1. Search for competitors: `search --query "..."`
2. Full scrape each product page: `scrape_full --url "..." --download_images true`
3. Extract product info, images, specifications
4. Organize by product
5. Compare features and pricing

---

## Error Handling & Degradation

The tool gracefully handles failures:

| Scenario | Behavior | Recovery |
|----------|----------|----------|
| JavaScript rendering unavailable | Falls back to static HTML | Content extraction still works |
| BeautifulSoup not installed | Uses basic HTML parsing | Less accurate structure detection |
| DuckDuckGo unavailable | Shows fallback search URL | User can search manually |
| Image download fails | Continues with remaining images | Saves metadata for failed images |
| Feed XML invalid | Returns error with details | User can try raw HTML scrape |
| URL unreachable | Returns error status | User can retry or validate URL |
| Timeout on slow site | Partial results returned | User can increase wait_timeout |

---

## Performance Notes

- **Static page extraction**: 1-3 seconds
- **Dynamic content with JS**: 5-15 seconds (depends on page complexity)
- **Image downloading**: 1-2 seconds per image (parallel downloads recommended)
- **Full page scrape**: 10-30 seconds depending on page size and options

---

## Environment Variables

- `ANTHROPIC_API_KEY` - Optional, for integration with logging agent
- `GOOGLE_GEMINI_API_KEY` - Optional, for Gemini provider integration

---

## Integration with AgenticToolset

The tool logs all operations via `log_manager`:
- All tool invocations recorded
- Session tracking for audit trails
- Error logging for debugging
- Performance metrics collected

**Logging with session:**
```bash
python tools/python/web_scraper.py \
  --action scrape_full \
  --url "https://example.com" \
  --session_id 20260222_120000
```

Results are logged to:
- `logs/master.jsonl` - All tool operations
- `logs/sessions/20260222_120000.jsonl` - Session-specific log

---

## Improvements & Future Work

### Completed (v1.0 Baseline)
✅ Static HTML scraping
✅ Dynamic JS rendering with Selenium
✅ Image downloading and organization
✅ Text cleaning and summarization
✅ Feed discovery and parsing
✅ Web search integration
✅ Error handling and graceful degradation
✅ Comprehensive logging

### Planned Improvements
- [ ] Multi-page crawling with site mapping
- [ ] Proxy rotation for rate limiting
- [ ] PDF extraction support
- [ ] OCR for image-based text
- [ ] Browser automation for complex interactions
- [ ] Content caching to reduce duplicate fetches
- [ ] Performance metrics and optimization
- [ ] Custom headers/authentication support
- [ ] JavaScript injection for dynamic content
- [ ] Machine learning for content classification
- [ ] Video transcript extraction
- [ ] Database export (CSV, JSON-LD, etc.)

---

## Troubleshooting

### "Selenium not installed"
Solution: `pip install selenium webdriver-manager`
Fallback: Tool uses static HTML parsing, dynamic content may be incomplete

### "BeautifulSoup not installed"
Solution: `pip install beautifulsoup4`
Fallback: Tool uses basic regex parsing, less accurate for nested structures

### "duckduckgo-search not installed"
Solution: `pip install duckduckgo-search`
Fallback: Tool shows search URL, requires manual search

### Images not downloading
- Check target image server accessibility
- Verify `--max_images` isn't too restrictive
- Check file system permissions for output directory
- Review error details in images_manifest.json

### Empty text content
- Page likely uses heavy JavaScript
- Try with `--wait_for_js true` (requires Selenium)
- Check if content is behind authentication/paywalls
- Verify site doesn't block scraping via robots.txt

### Timeout errors
- Increase `--wait_timeout` value
- Try without JS rendering for faster fallback
- Check target site status
- Verify network connectivity

---

## License & Compliance

- Respect robots.txt and site terms of service
- Don't overload servers (add delays between requests if bulk scraping)
- Identify yourself with proper User-Agent
- Respect copyright and attribution requirements
- Check legal requirements for content use in your jurisdiction

---

## Support & Feedback

For issues, improvements, or questions:
1. Check existing agent documentation in `agents/web_scraper_specialist.md`
2. Review error logs in `logs/`
3. Check tool definition in `tools/defs/web_scraper.json`
4. Report issues with session logs for reproducibility

---

## Appendix: Example Workflows

### Complete Content Collection Workflow
```bash
# Step 1: Discover content
python tools/python/web_scraper.py \
  --action search \
  --query "machine learning best practices" \
  --max_results 5 \
  --session_id $SESSION_ID

# Step 2: For each result, analyze structure
for url in <search results>; do
  python tools/python/web_scraper.py \
    --action analyze_structure \
    --url "$url" \
    --output_dir "./analysis/$url" \
    --session_id $SESSION_ID
done

# Step 3: Full scrape promising results
python tools/python/web_scraper.py \
  --action scrape_full \
  --url "<best result>" \
  --output_dir "./content/best_result" \
  --download_images true \
  --session_id $SESSION_ID
```

### Feed Monitoring Workflow
```bash
# Setup once
python tools/python/web_scraper.py \
  --action find_feeds \
  --url "https://technical.blog.com" \
  --output_dir "./setup/feeds" \
  --session_id $SESSION_ID

# Run periodically (cron)
for feed_url in <discovered feeds>; do
  python tools/python/web_scraper.py \
    --action parse_feed \
    --url "$feed_url" \
    --max_entries 20 \
    --output_dir "./updates/$(date +%Y%m%d)" \
    --session_id $SESSION_ID
done
```

---

**Last Updated**: February 22, 2026
**Status**: Production Ready Baseline (Haiku optimized)
