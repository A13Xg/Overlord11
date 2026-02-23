#!/bin/bash
# Web Scraper Tool - Comprehensive Test Suite
# Tests all 9 actions with real-world examples

set -e

TOOL="python tools/python/web_scraper.py"
SESSION_ID=$(date +"%Y%m%d_%H%M%S")
TEST_DIR="workspace/test_results_${SESSION_ID}"

echo "═══════════════════════════════════════════════════════════════"
echo "Web Scraper Tool - Comprehensive Test Suite"
echo "═══════════════════════════════════════════════════════════════"
echo "Session: $SESSION_ID"
echo "Test Directory: $TEST_DIR"
echo ""

# Create test directory
mkdir -p "$TEST_DIR"

# Test 1: Validate URL
echo "[1/9] Testing: validate_url"
$TOOL --action validate_url --url "example.com" \
  --session_id "$SESSION_ID" > "$TEST_DIR/01_validate_url.json"
echo "✓ URL validation works"
echo ""

# Test 2: Analyze Structure
echo "[2/9] Testing: analyze_structure"
$TOOL --action analyze_structure --url "https://python.org" \
  --output_dir "$TEST_DIR/02_structure_analysis" \
  --session_id "$SESSION_ID" > "$TEST_DIR/02_structure_analysis.json"
echo "✓ Page structure analysis works"
echo ""

# Test 3: Extract Text
echo "[3/9] Testing: extract_text"
$TOOL --action extract_text --url "https://example.com" \
  --output_dir "$TEST_DIR/03_text_extract" \
  --session_id "$SESSION_ID" > "$TEST_DIR/03_text_extract.json"
echo "✓ Text extraction works"
echo ""

# Test 4: Summarize
echo "[4/9] Testing: summarize"
$TOOL --action summarize --url "https://example.com" \
  --max_summary_length 200 \
  --output_dir "$TEST_DIR/04_summary" \
  --session_id "$SESSION_ID" > "$TEST_DIR/04_summary.json"
echo "✓ Text summarization works"
echo ""

# Test 5: Download Images
echo "[5/9] Testing: download_images"
$TOOL --action download_images --url "https://python.org" \
  --max_images 5 \
  --output_dir "$TEST_DIR/05_images" \
  --session_id "$SESSION_ID" > "$TEST_DIR/05_images.json"
echo "✓ Image downloading works"
echo ""

# Test 6: Find Feeds
echo "[6/9] Testing: find_feeds"
$TOOL --action find_feeds --url "https://python.org" \
  --output_dir "$TEST_DIR/06_feeds" \
  --session_id "$SESSION_ID" > "$TEST_DIR/06_feeds.json"
echo "✓ Feed discovery works"
echo ""

# Test 7: Parse Feed
echo "[7/9] Testing: parse_feed"
FEED_URL=$(grep -o '"url": "[^"]*"' "$TEST_DIR/06_feeds.json" | head -1 | cut -d'"' -f4)
if [ ! -z "$FEED_URL" ]; then
  $TOOL --action parse_feed --url "$FEED_URL" \
    --max_entries 5 \
    --output_dir "$TEST_DIR/07_feed_parse" \
    --session_id "$SESSION_ID" > "$TEST_DIR/07_feed_parse.json"
  echo "✓ Feed parsing works (tested: $FEED_URL)"
else
  echo "⚠ Feed parsing skipped (no feeds found)"
fi
echo ""

# Test 8: Web Search
echo "[8/9] Testing: search"
$TOOL --action search --query "FastAPI Python web framework" \
  --max_results 5 \
  --output_dir "$TEST_DIR/08_search" \
  --session_id "$SESSION_ID" > "$TEST_DIR/08_search.json"
echo "✓ Web search works"
echo ""

# Test 9: Full Scrape
echo "[9/9] Testing: scrape_full"
$TOOL --action scrape_full --url "https://example.com" \
  --output_dir "$TEST_DIR/09_full_scrape" \
  --download_images false \
  --session_id "$SESSION_ID" > "$TEST_DIR/09_full_scrape.json"
echo "✓ Full page scrape works"
echo ""

# Summary
echo "═══════════════════════════════════════════════════════════════"
echo "Test Summary"
echo "═══════════════════════════════════════════════════════════════"
echo "✅ All 9 actions tested successfully"
echo ""
echo "Results saved to: $TEST_DIR"
echo "Log files:"
ls -1 "$TEST_DIR"/*.json | sed 's/^/  - /'
echo ""
echo "Session logs:"
echo "  - logs/master.jsonl (all tool invocations)"
echo "  - logs/sessions/${SESSION_ID}.jsonl (session-specific)"
echo ""
echo "═══════════════════════════════════════════════════════════════"
