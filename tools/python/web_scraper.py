"""
Overlord11 - Advanced Web Scraper v2.0
==========================================
Comprehensive web scraping tool with intelligent content detection, cascading
fetch pipeline, reader-mode extraction, and robust fallback chains.

Architecture:
  1. DETECT  - Heuristic content-type classification (article/news/docs/product/etc)
  2. FETCH   - Cascading pipeline: Selenium JS → urllib static → requests fallback
  3. EXTRACT - Mode-driven extraction: auto | article | images_only | structured | raw
  4. OUTPUT  - Organized directory with JSON manifests and downloaded assets

The detect_type action returns a lightweight analysis the calling LLM agent can
review before choosing the best extraction approach.  When confidence is low the
tool says so explicitly so the agent can apply its own judgement.

Usage:
    python web_scraper.py --action detect_type    --url "https://example.com"
    python web_scraper.py --action scrape_full    --url "https://example.com" --extract_mode auto
    python web_scraper.py --action extract_article --url "https://example.com/blog/post"
    python web_scraper.py --action download_images --url "https://example.com" --min_image_size 100
    python web_scraper.py --action search          --query "topic" --max_results 10
    python web_scraper.py --action find_feeds       --url "https://example.com"
    python web_scraper.py --action parse_feed       --url "https://example.com/rss.xml"
"""

import gzip
import json
import os
import re
import sys
import ssl
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from log_manager import log_tool_invocation, log_error
from task_workspace import ensure_env_task_layout

# ---------------------------------------------------------------------------
# Optional dependency probes
# ---------------------------------------------------------------------------
try:
    from bs4 import BeautifulSoup, Comment
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    from PIL import Image as PILImage
    from io import BytesIO
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False

try:
    import requests as req_lib
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 15
MAX_CONTENT_SIZE = 10_000_000   # 10 MB
DEFAULT_SUMMARY_LEN = 500
MIN_IMAGE_BYTES = 5_000         # skip images < 5 KB (icons/spacers/badges)
MIN_IMAGE_DIM_HTML = 50         # skip images with declared HTML attrs < 50 px (true tiny icons)
MIN_IMAGE_DIM_ACTUAL = 150      # skip downloaded images < 150 px on either axis (PIL check)
MAX_IMAGE_ASPECT = 4.0          # skip images with aspect ratio > 4:1 (banners/ribbons)

# URL patterns that indicate junk images (logos, icons, badges, tracking)
JUNK_IMAGE_URL_RE = re.compile(
    r"logo|icon|favicon|badge|sprite|brand|button|arrow|"
    r"spinner|loader|placeholder|spacer|pixel|tracking|beacon|"
    r"ad[_-]?banner|social[_-]|share[_-]|app[_-]?store|"
    r"google[_-]?play|get[_-]?ios|get[_-]?android",
    re.I,
)

# Parent elements that almost never contain content images
JUNK_IMAGE_PARENTS = {"nav", "footer", "header", "aside"}

# Tags/classes/roles that are almost always boilerplate
STRIP_TAGS = ["script", "style", "noscript", "svg", "iframe"]
STRIP_ROLES = ["navigation", "banner", "complementary", "contentinfo"]
STRIP_CLASSES_RE = re.compile(
    r"sidebar|widget|advert|promo|popup|modal|cookie|consent|share|social|"
    r"related|comment|footer|nav|menu|breadcrumb|pagination|signup|newsletter",
    re.I,
)

# ---------------------------------------------------------------------------
# SSL helper
# ---------------------------------------------------------------------------
def _ssl_ctx():
    try:
        return ssl.create_default_context()
    except Exception:
        return None


# =========================================================================
#  FETCH PIPELINE  (Task #2)
# =========================================================================
def _decompress(raw: bytes, headers: dict) -> str:
    """Decompress gzip/deflate response bodies."""
    encoding = headers.get("content-encoding", "").lower()
    try:
        if encoding == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        elif encoding == "deflate":
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
        elif encoding == "br":
            try:
                import brotli
                raw = brotli.decompress(raw)
            except ImportError:
                pass
    except Exception:
        pass  # fall through with raw bytes
    return raw.decode("utf-8", errors="ignore")


def _fetch_with_urllib(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple:
    """Return (html_str, response_headers_dict, 'urllib')."""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    ctx = _ssl_ctx()
    kw = {"timeout": timeout}
    if ctx:
        kw["context"] = ctx
    with urllib.request.urlopen(req, **kw) as resp:
        raw = resp.read(MAX_CONTENT_SIZE)
        hdrs = {k.lower(): v for k, v in resp.headers.items()}
    return _decompress(raw, hdrs), hdrs, "urllib"


def _fetch_with_requests(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple:
    """Return (html_str, response_headers_dict, 'requests')."""
    if not HAS_REQUESTS:
        raise ImportError("requests not installed")
    resp = req_lib.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    hdrs = {k.lower(): v for k, v in resp.headers.items()}
    return resp.text, hdrs, "requests"  # requests handles decompression


def _fetch_with_selenium(url: str, timeout: int = 12) -> tuple:
    """Return (html_str, {}, 'selenium')."""
    if not HAS_SELENIUM:
        raise ImportError("selenium not installed")
    opts = ChromeOptions()
    for flag in ["--headless", "--no-sandbox", "--disable-dev-shm-usage",
                 "--disable-gpu", f"user-agent={USER_AGENT}"]:
        opts.add_argument(flag)
    driver = webdriver.Chrome(options=opts)
    try:
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(2)
        return driver.page_source, {}, "selenium"
    finally:
        driver.quit()


def fetch_page(url: str, want_js: bool = True, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Cascading fetch: Selenium → urllib → requests.

    Returns dict with keys: html, headers, method, errors (list of failed attempts).
    """
    attempts = []

    # Layer 1 – JS rendering (if requested and available)
    if want_js and HAS_SELENIUM:
        try:
            html, hdrs, method = _fetch_with_selenium(url, timeout)
            return {"html": html, "headers": hdrs, "method": method, "attempts": attempts}
        except Exception as exc:
            attempts.append({"method": "selenium", "error": str(exc)})

    # Layer 2 – stdlib urllib
    try:
        html, hdrs, method = _fetch_with_urllib(url, timeout)
        return {"html": html, "headers": hdrs, "method": method, "attempts": attempts}
    except Exception as exc:
        attempts.append({"method": "urllib", "error": str(exc)})

    # Layer 3 – requests library
    if HAS_REQUESTS:
        try:
            html, hdrs, method = _fetch_with_requests(url, timeout)
            return {"html": html, "headers": hdrs, "method": method, "attempts": attempts}
        except Exception as exc:
            attempts.append({"method": "requests", "error": str(exc)})

    raise ConnectionError(
        f"All fetch methods failed for {url}. Attempts: {json.dumps(attempts)}"
    )


# =========================================================================
#  CONTENT-TYPE DETECTION ENGINE  (Task #1)
# =========================================================================

# Each heuristic returns (score_delta, signal_label)
_HEURISTIC_RULES: list = []  # populated below


def _h_article_tag(html, url, meta, struct):
    if re.search(r"<article[\s>]", html, re.I):
        return ("article", 4, "has_article_tag")
    return None

def _h_byline(html, url, meta, struct):
    if re.search(r'class="[^"]*(?:byline|author|writer)[^"]*"', html, re.I):
        return ("article", 3, "has_byline_class")
    if meta.get("author"):
        return ("article", 2, "has_author_meta")
    return None

def _h_publish_date(html, url, meta, struct):
    if re.search(r'(?:datePublished|publish[_-]?date|posted[_-]?on|datetime)', html, re.I):
        return ("article", 2, "has_publish_date")
    return None

def _h_news_keywords(html, url, meta, struct):
    if re.search(r'<meta[^>]+name="news_keywords"', html, re.I):
        return ("news", 4, "has_news_keywords_meta")
    return None

def _h_og_type_article(html, url, meta, struct):
    if re.search(r'og:type"?\s+content="article"', html, re.I):
        return ("article", 3, "og_type_article")
    return None

def _h_schema_article(html, url, meta, struct):
    if re.search(r'"@type"\s*:\s*"(?:News|Blog|)Article"', html, re.I):
        return ("article", 4, "schema_article_type")
    return None

def _h_schema_product(html, url, meta, struct):
    if re.search(r'"@type"\s*:\s*"Product"', html, re.I):
        return ("product", 5, "schema_product_type")
    return None

def _h_price(html, url, meta, struct):
    if re.search(r'(?:price|cost)["\s:]*\$?\d+[\.,]\d{2}', html, re.I):
        return ("product", 3, "has_price_pattern")
    if re.search(r'add[_\-\s]?to[_\-\s]?cart', html, re.I):
        return ("product", 3, "has_add_to_cart")
    return None

def _h_code_heavy(html, url, meta, struct):
    blocks = struct.get("code_blocks", 0)
    if blocks >= 5:
        return ("documentation", 4, f"code_blocks_{blocks}")
    if blocks >= 2:
        return ("documentation", 2, f"code_blocks_{blocks}")
    return None

def _h_docs_url(html, url, meta, struct):
    if re.search(r"docs?\.|documentation|/api/|/reference/|readthedocs", url, re.I):
        return ("documentation", 4, "docs_url_pattern")
    return None

def _h_docs_nav(html, url, meta, struct):
    if re.search(r'class="[^"]*(?:toctree|doc-?nav|api-?nav|sidebar-?nav)[^"]*"', html, re.I):
        return ("documentation", 3, "docs_nav_class")
    return None

def _h_forum(html, url, meta, struct):
    if re.search(r'class="[^"]*(?:thread|reply|post-?count|forum)[^"]*"', html, re.I):
        return ("forum", 4, "forum_class_pattern")
    if re.search(r"forum|discuss|community", url, re.I):
        return ("forum", 2, "forum_url_pattern")
    return None

def _h_media_gallery(html, url, meta, struct):
    img_count = struct.get("images", 0)
    word_count = struct.get("_word_count", 500)
    if img_count > 10 and word_count < 300:
        return ("media_gallery", 4, f"high_image_ratio_{img_count}_imgs")
    if re.search(r'class="[^"]*(?:gallery|carousel|lightbox)[^"]*"', html, re.I):
        return ("media_gallery", 3, "gallery_class")
    return None

def _h_landing(html, url, meta, struct):
    cta = len(re.findall(r'class="[^"]*(?:cta|hero|call-to-action)[^"]*"', html, re.I))
    forms = struct.get("forms", 0)
    if cta >= 2 or (forms >= 2 and struct.get("links", 0) < 30):
        return ("landing_page", 3, f"cta_{cta}_forms_{forms}")
    return None

def _h_feed_link(html, url, meta, struct):
    if re.search(r'type="application/(?:rss|atom)\+xml"', html, re.I):
        return ("news", 1, "has_feed_link")
    return None

_HEURISTIC_RULES = [
    _h_article_tag, _h_byline, _h_publish_date, _h_news_keywords,
    _h_og_type_article, _h_schema_article, _h_schema_product, _h_price,
    _h_code_heavy, _h_docs_url, _h_docs_nav, _h_forum,
    _h_media_gallery, _h_landing, _h_feed_link,
]

CONTENT_TYPES = [
    "article", "news", "documentation", "product",
    "forum", "media_gallery", "landing_page", "generic",
]

_MODE_MAP = {
    "article":       "article",
    "news":          "article",
    "documentation": "structured",
    "product":       "structured",
    "forum":         "raw",
    "media_gallery": "images_only",
    "landing_page":  "raw",
    "generic":       "auto",
}

_ACTION_MAP = {
    "article":       ["extract_article", "summarize"],
    "news":          ["extract_article", "find_feeds", "summarize"],
    "documentation": ["extract_text --clean_text true", "analyze_structure"],
    "product":       ["scrape_full --extract_mode structured", "download_images"],
    "forum":         ["extract_text --clean_text true"],
    "media_gallery": ["download_images"],
    "landing_page":  ["analyze_structure", "extract_text"],
    "generic":       ["scrape_full --extract_mode auto"],
}


def _detect_content_type(html: str, url: str, metadata: dict, structure: dict) -> dict:
    """Run all heuristic rules and return scored detection result."""
    scores = {t: 0 for t in CONTENT_TYPES}
    signals = []

    # Rough word count for ratio heuristics
    text_only = re.sub(r"<[^>]+>", " ", html)
    word_count = len(text_only.split())
    structure["_word_count"] = word_count

    for rule_fn in _HEURISTIC_RULES:
        try:
            result = rule_fn(html, url, metadata, structure)
            if result:
                ctype, delta, label = result
                scores[ctype] = scores.get(ctype, 0) + delta
                signals.append({"type": ctype, "score": delta, "signal": label})
        except Exception:
            pass

    # Ensure generic has a baseline so there's always a winner
    if all(v == 0 for v in scores.values()):
        scores["generic"] = 1

    total = max(sum(scores.values()), 1)
    best = max(scores, key=scores.get)
    confidence = round(scores[best] / total, 3)

    # Determine if agent should override
    if confidence < 0.35:
        agent_note = (
            "LOW CONFIDENCE: Heuristics could not determine content type with "
            "certainty. Review the signals and page metadata below, then choose "
            "the extract_mode that best fits the content you see."
        )
    elif confidence < 0.55:
        agent_note = (
            "MODERATE CONFIDENCE: The detected type is a reasonable guess. "
            "Verify by checking metadata and structure before proceeding."
        )
    else:
        agent_note = (
            "HIGH CONFIDENCE: Heuristic signals strongly indicate this content "
            "type. Proceed with the recommended extraction mode."
        )

    return {
        "detected_type": best,
        "confidence": confidence,
        "scores": {k: v for k, v in sorted(scores.items(), key=lambda x: -x[1]) if v > 0},
        "signals": signals,
        "recommended_extract_mode": _MODE_MAP.get(best, "auto"),
        "recommended_actions": _ACTION_MAP.get(best, ["scrape_full"]),
        "agent_note": agent_note,
    }


# =========================================================================
#  READER-MODE EXTRACTION  (Task #3)
# =========================================================================

# Noise tags to strip completely
_NOISE_TAGS = [
    "script", "style", "noscript", "svg", "iframe", "nav", "footer",
    "header", "aside",
]
_NOISE_CLASSES = re.compile(
    r"sidebar|widget|advert|ad-|promo|popup|modal|cookie|consent|share|"
    r"social|related|comment|footer|nav|menu|breadcrumb|pagination|"
    r"signup|newsletter|banner|masthead|toolbar|search-form",
    re.I,
)
_NOISE_IDS = re.compile(
    r"sidebar|footer|nav|menu|comment|ad|banner|header|search", re.I
)


def _score_block(tag) -> float:
    """Score a BS4 tag for content-ness. Higher = more likely main content."""
    text = tag.get_text(strip=True)
    if not text:
        return -1

    text_len = len(text)
    words = text.split()
    word_count = len(words)

    # Very short blocks are noise
    if word_count < 10:
        return -1

    # Link density: ratio of link-text to total text
    link_text_len = sum(len(a.get_text(strip=True)) for a in tag.find_all("a"))
    link_density = link_text_len / max(text_len, 1)

    # High link density = navigation, not content
    if link_density > 0.5:
        return -1

    score = word_count * (1.0 - link_density)

    # Bonuses
    p_count = len(tag.find_all("p"))
    score += p_count * 3

    # Tag-type bonuses
    tag_name = tag.name or ""
    if tag_name == "article":
        score += 50
    elif tag_name == "main":
        score += 30
    elif tag_name in ("section", "div"):
        score += 0

    # Class/id penalty for known noise
    cls = " ".join(tag.get("class", []))
    tid = tag.get("id", "")
    if _NOISE_CLASSES.search(cls) or _NOISE_IDS.search(tid):
        score -= 100

    return score


def _extract_reader_mode(html: str, url: str) -> dict:
    """Extract article-style content using content-scoring algorithm.

    Returns dict with: title, author, publish_date, body_text, body_html,
    featured_image, word_count.
    Falls back to basic text extraction if scoring fails.
    """
    if not HAS_BS4:
        # Fallback: basic regex extraction
        return _extract_reader_mode_basic(html, url)

    soup = BeautifulSoup(html, "html.parser")

    # --- Extract article metadata first ---
    title = ""
    # Try og:title → h1 → <title>
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og["content"].strip()
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
    if not title:
        t = soup.find("title")
        if t:
            title = t.get_text(strip=True)

    author = ""
    # Try schema → meta → byline class
    for a_meta in soup.find_all("meta", attrs={"name": re.compile(r"author", re.I)}):
        if a_meta.get("content"):
            author = a_meta["content"].strip()
            break
    if not author:
        byline = soup.find(class_=re.compile(r"byline|author", re.I))
        if byline:
            author = byline.get_text(strip=True)

    publish_date = ""
    time_tag = soup.find("time", attrs={"datetime": True})
    if time_tag:
        publish_date = time_tag["datetime"]
    else:
        for m in soup.find_all("meta"):
            prop = m.get("property", "") + m.get("name", "")
            if re.search(r"published|date|time", prop, re.I) and m.get("content"):
                publish_date = m["content"]
                break

    featured_image = ""
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        featured_image = og_img["content"]

    # --- Strip noise ---
    for tag_name in _NOISE_TAGS:
        for el in soup.find_all(tag_name):
            el.decompose()

    # Remove HTML comments
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    # Remove elements with noise classes/ids — but preserve content-heavy blocks
    to_remove = []
    for el in soup.find_all(True):
        if el.attrs is None:
            continue
        cls = " ".join(el.get("class", []))
        eid = el.get("id", "")
        role = el.get("role", "")
        if (_NOISE_CLASSES.search(cls) or _NOISE_IDS.search(eid)
                or role in STRIP_ROLES):
            # Safety: don't remove blocks with substantial content
            el_text = el.get_text(strip=True)
            if len(el_text.split()) > 100:
                continue  # too much content to be pure noise
            to_remove.append(el)
    for el in to_remove:
        try:
            el.decompose()
        except Exception:
            pass

    # --- Score remaining blocks to find the main content ---
    candidates = []
    for tag in soup.find_all(["article", "main", "section", "div"]):
        s = _score_block(tag)
        if s > 0:
            candidates.append((s, tag))

    candidates.sort(key=lambda x: -x[0])

    if candidates:
        best_block = candidates[0][1]
    else:
        # fallback to body
        best_block = soup.find("body") or soup

    # --- Extract clean text from best block ---
    # Preserve paragraph structure
    paragraphs = []
    for p in best_block.find_all(["p", "li", "blockquote", "h2", "h3", "h4"]):
        text = p.get_text(strip=True)
        if text and len(text.split()) >= 3:
            prefix = ""
            if p.name and p.name.startswith("h"):
                prefix = "## " if p.name == "h2" else "### "
            paragraphs.append(prefix + text)

    # If paragraph extraction yielded very little, fall back to full text
    body_text = "\n\n".join(paragraphs)
    if len(body_text.split()) < 30:
        body_text = best_block.get_text(separator="\n", strip=True)

    # Sanitize all text outputs
    body_text = _sanitize_unicode(body_text)
    title = _sanitize_unicode(title)
    author = _sanitize_unicode(author)

    return {
        "title": title,
        "author": author,
        "publish_date": publish_date,
        "featured_image": featured_image,
        "body_text": body_text,
        "word_count": len(body_text.split()),
        "extraction_method": "reader_mode_scored",
    }


def _extract_reader_mode_basic(html: str, url: str) -> dict:
    """Regex-only fallback for reader mode when BS4 is unavailable."""
    # Strip script/style
    clean = re.sub(r"<script[^>]*>.*?</script[^>]*>", "", html, flags=re.DOTALL | re.I)
    clean = re.sub(r"<style[^>]*>.*?</style[^>]*>", "", clean, flags=re.DOTALL | re.I)
    clean = re.sub(r"<nav[^>]*>.*?</nav>", "", clean, flags=re.DOTALL | re.I)
    clean = re.sub(r"<footer[^>]*>.*?</footer>", "", clean, flags=re.DOTALL | re.I)
    clean = re.sub(r"<header[^>]*>.*?</header>", "", clean, flags=re.DOTALL | re.I)
    clean = re.sub(r"<aside[^>]*>.*?</aside>", "", clean, flags=re.DOTALL | re.I)

    title = ""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", clean, re.I | re.DOTALL)
    if m:
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.DOTALL)
        if m:
            title = m.group(1).strip()

    text = re.sub(r"<[^>]+>", " ", clean)
    text = re.sub(r"\s+", " ", text).strip()

    return {
        "title": title,
        "author": "",
        "publish_date": "",
        "featured_image": "",
        "body_text": text,
        "word_count": len(text.split()),
        "extraction_method": "reader_mode_basic_regex",
    }


# =========================================================================
#  TEXT EXTRACTION  (existing, improved)
# =========================================================================

def _extract_text_bs4(html: str, clean: bool = True) -> dict:
    if not HAS_BS4:
        raise ImportError("bs4 not available")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(STRIP_TAGS):
        tag.decompose()

    main_el = (soup.find("article") or soup.find("main")
               or soup.find(attrs={"role": "main"}) or soup)
    raw = main_el.get_text(separator="\n", strip=True)
    text = _clean_text(raw) if clean else raw

    headings = [h.get_text(strip=True) for h in soup.find_all(["h1","h2","h3"])]
    paragraphs = [p.get_text(strip=True) for p in soup.find_all("p")
                  if len(p.get_text(strip=True).split()) >= 3]
    return {"full_text": text, "headings": headings,
            "paragraphs": paragraphs, "word_count": len(text.split())}


def _extract_text_regex(html: str, clean: bool = True) -> dict:
    for tag in STRIP_TAGS:
        html = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", html, flags=re.DOTALL|re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = _clean_text(text) if clean else re.sub(r"\s+", " ", text).strip()
    return {"full_text": text, "headings": [], "paragraphs": [],
            "word_count": len(text.split())}


def extract_text_robust(html: str, clean: bool = True) -> dict:
    """Try BS4 then fall back to regex. Never raises."""
    if HAS_BS4:
        try:
            return _extract_text_bs4(html, clean)
        except Exception:
            pass
    return _extract_text_regex(html, clean)


def _sanitize_unicode(text: str) -> str:
    """Normalize Unicode and replace problematic characters with safe equivalents."""
    import unicodedata
    # Normalize to NFC form first
    text = unicodedata.normalize("NFC", text)
    # Replace common problematic Unicode with ASCII equivalents
    replacements = {
        "\u2011": "-",   # non-breaking hyphen
        "\u2013": "-",   # en dash
        "\u2014": "--",  # em dash
        "\u2018": "'",   # left single quote
        "\u2019": "'",   # right single quote
        "\u201c": '"',   # left double quote
        "\u201d": '"',   # right double quote
        "\u2026": "...", # ellipsis
        "\u00a0": " ",   # non-breaking space
        "\u200b": "",    # zero-width space
        "\u200c": "",    # zero-width non-joiner
        "\u200d": "",    # zero-width joiner
        "\ufeff": "",    # BOM
        "\u00ad": "",    # soft hyphen
        "\u2028": "\n",  # line separator
        "\u2029": "\n",  # paragraph separator
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    # Replace any remaining non-encodable chars with closest ASCII or ?
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        text = text.encode("utf-8", errors="replace").decode("utf-8")
    return text


def _clean_text(text: str) -> str:
    text = _sanitize_unicode(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# =========================================================================
#  IMAGE EXTRACTION  (Task #5 - improved)
# =========================================================================

_JUNK_IMAGE_ANCESTOR_CLASS_RE = re.compile(
    r"^(?:sidebar|widget|advert|promo|cookie|consent|signup|newsletter)$"
    r"|(?:^ad-|^ad_|^social-|^share-|^footer-|^nav-|^menu-)",
    re.I,
)

def _is_junk_ancestor(tag) -> bool:
    """Check if an img tag lives inside a nav/footer/header/aside or an explicitly junk container.
    Uses structural tags (nav/footer/header/aside) + a tight class list that won't
    false-positive on content containers like 'infinite-pagination' or 'related-articles'."""
    for parent in tag.parents:
        if parent.name in JUNK_IMAGE_PARENTS:
            return True
        # Only check immediate-ish ancestors (up to 4 levels) for junk classes
        # to avoid matching broad layout wrappers
        parent_classes = parent.get("class", [])
        for cls in parent_classes:
            if _JUNK_IMAGE_ANCESTOR_CLASS_RE.search(cls):
                return True
    return False


def _extract_images_from_html(html: str, url: str, max_count: int = 50,
                              include_svg: bool = False) -> list:
    """Extract image metadata with alt text, srcset, and multi-layer noise filtering."""
    images = []
    seen_urls = set()

    if HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        for img in soup.find_all("img"):
            src = img.get("src", "")
            srcset = img.get("srcset", "")
            alt = img.get("alt", "")
            width = img.get("width", "")
            height = img.get("height", "")

            # Pick best source from srcset if available
            best_src = src
            if srcset:
                parts = [p.strip().split() for p in srcset.split(",") if p.strip()]
                if parts:
                    best_src = parts[-1][0]  # last entry is typically largest

            if not best_src or best_src.startswith("data:image/gif"):
                continue  # skip 1x1 tracking pixels

            abs_url = urljoin(url, best_src) if not best_src.startswith("http") else best_src

            # Skip SVGs (almost always icons/logos) unless explicitly requested
            if not include_svg and (abs_url.endswith(".svg") or "svg" in abs_url.split("?")[0][-6:]):
                continue

            # Skip URLs matching junk image patterns (logos, icons, badges, etc.)
            if JUNK_IMAGE_URL_RE.search(abs_url):
                continue

            # Skip images inside nav/footer/header/aside or noise-class containers
            if _is_junk_ancestor(img):
                continue

            # Filter small images by declared dimensions (EITHER axis too small = skip)
            try:
                if width and int(width) < MIN_IMAGE_DIM_HTML:
                    continue
                if height and int(height) < MIN_IMAGE_DIM_HTML:
                    continue
            except (ValueError, TypeError):
                pass

            if abs_url in seen_urls:
                continue
            seen_urls.add(abs_url)

            images.append({
                "url": abs_url,
                "alt": alt,
                "width": width,
                "height": height,
                "has_srcset": bool(srcset),
            })
            if len(images) >= max_count:
                break

        # Also check <picture> elements
        for pic in soup.find_all("picture"):
            # Skip pictures in junk ancestors
            if _is_junk_ancestor(pic):
                continue
            sources = pic.find_all("source")
            for source in sources:
                srcset = source.get("srcset", "")
                if srcset:
                    parts = [p.strip().split() for p in srcset.split(",") if p.strip()]
                    if parts:
                        pic_url = urljoin(url, parts[-1][0])
                        if not include_svg and pic_url.endswith(".svg"):
                            continue
                        if JUNK_IMAGE_URL_RE.search(pic_url):
                            continue
                        if pic_url not in seen_urls:
                            seen_urls.add(pic_url)
                            images.append({
                                "url": pic_url, "alt": "", "width": "", "height": "",
                                "has_srcset": True,
                            })
                            if len(images) >= max_count:
                                break
    else:
        # Regex fallback
        for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I):
            src = m.group(1)
            if src.startswith("data:image/gif"):
                continue
            abs_url = urljoin(url, src) if not src.startswith("http") else src
            # Skip SVGs and junk URL patterns in regex fallback too
            if not include_svg and abs_url.endswith(".svg"):
                continue
            if JUNK_IMAGE_URL_RE.search(abs_url):
                continue
            if abs_url in seen_urls:
                continue
            seen_urls.add(abs_url)
            # Try to get alt text
            alt_m = re.search(r'alt=["\']([^"\']*)["\']', m.group(0), re.I)
            images.append({
                "url": abs_url,
                "alt": alt_m.group(1) if alt_m else "",
                "width": "", "height": "", "has_srcset": False,
            })
            if len(images) >= max_count:
                break

    return images


def _download_image(img_url: str, output_dir: Path, index: int) -> dict:
    """Download a single image. Skip if too small, bad aspect ratio, or junk URL."""
    if img_url.startswith("data:"):
        return {"success": False, "url": img_url, "error": "data_uri_skipped"}
    # Double-check junk URL patterns at download time (safety net)
    if JUNK_IMAGE_URL_RE.search(img_url):
        return {"success": False, "url": img_url, "error": "junk_url_pattern"}
    try:
        req = urllib.request.Request(img_url, headers={"User-Agent": USER_AGENT})
        ctx = _ssl_ctx()
        kw = {"timeout": 10}
        if ctx:
            kw["context"] = ctx
        with urllib.request.urlopen(req, **kw) as resp:
            data = resp.read(5_000_000)
            ctype = resp.headers.get("Content-Type", "image/jpeg")

        if len(data) < MIN_IMAGE_BYTES:
            return {"success": False, "url": img_url, "error": "too_small",
                    "size_bytes": len(data)}

        # Determine extension
        ext_map = {"png": ".png", "gif": ".gif", "webp": ".webp",
                   "svg": ".svg", "bmp": ".bmp", "jpeg": ".jpg", "jpg": ".jpg"}
        ext = ".jpg"
        for key, val in ext_map.items():
            if key in ctype.lower():
                ext = val
                break

        # Validate dimensions and aspect ratio with PIL
        img_width, img_height = 0, 0
        if HAS_PIL and ext not in (".svg",):
            try:
                pil_img = PILImage.open(BytesIO(data))
                img_width, img_height = pil_img.size
                # Skip if EITHER axis is too small
                if img_width < MIN_IMAGE_DIM_ACTUAL or img_height < MIN_IMAGE_DIM_ACTUAL:
                    return {"success": False, "url": img_url, "error": "dimensions_too_small",
                            "width": img_width, "height": img_height}
                # Skip extreme aspect ratios (banners, ribbons, separator lines)
                aspect = max(img_width, img_height) / max(min(img_width, img_height), 1)
                if aspect > MAX_IMAGE_ASPECT:
                    return {"success": False, "url": img_url, "error": "extreme_aspect_ratio",
                            "width": img_width, "height": img_height,
                            "aspect_ratio": round(aspect, 1)}
            except Exception:
                pass

        filename = f"image_{index:03d}{ext}"
        filepath = output_dir / "images" / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(data)

        return {
            "success": True, "url": img_url, "filename": filename,
            "path": str(filepath), "size_bytes": len(data),
            "width": img_width, "height": img_height,
        }
    except Exception as exc:
        return {"success": False, "url": img_url, "error": str(exc)}


# =========================================================================
#  METADATA & STRUCTURE
# =========================================================================

def _extract_metadata(html: str, url: str) -> dict:
    meta = {
        "url": url, "title": "", "description": "", "author": "",
        "keywords": "", "og_title": "", "og_description": "", "og_image": "",
        "og_type": "", "canonical": "",
    }
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    if m:
        meta["title"] = m.group(1).strip()

    patterns = {
        "description":    r'<meta\s+[^>]*name="description"[^>]*content="([^"]+)"',
        "author":         r'<meta\s+[^>]*name="author"[^>]*content="([^"]+)"',
        "keywords":       r'<meta\s+[^>]*name="keywords"[^>]*content="([^"]+)"',
        "og_title":       r'<meta\s+[^>]*property="og:title"[^>]*content="([^"]+)"',
        "og_description": r'<meta\s+[^>]*property="og:description"[^>]*content="([^"]+)"',
        "og_image":       r'<meta\s+[^>]*property="og:image"[^>]*content="([^"]+)"',
        "og_type":        r'<meta\s+[^>]*property="og:type"[^>]*content="([^"]+)"',
        "canonical":      r'<link\s+[^>]*rel="canonical"[^>]*href="([^"]+)"',
    }
    for key, pat in patterns.items():
        match = re.search(pat, html, re.I)
        if not match:
            # Try reversed attribute order (content before name/property)
            alt = pat.replace('name=', 'XNAME=').replace('property=', 'XPROP=')
            alt = re.sub(r'content="([^"]*)"(.*?)X(NAME|PROP)',
                         lambda _m: f'X{_m.group(3)}', pat)
            # Simpler: just look for the content near the property
            match = re.search(
                rf'<meta[^>]*(?:name|property)="{key.replace("og_","og:")}"[^>]*content="([^"]+)"',
                html, re.I
            )
        if match:
            meta[key] = match.group(1).strip()
    return meta


def _analyze_structure(html: str) -> dict:
    s = {"headings": {}, "lists": 0, "tables": 0, "forms": 0,
         "images": 0, "links": 0, "videos": 0, "code_blocks": 0, "iframes": 0}
    for lvl in range(1, 7):
        c = len(re.findall(rf"<h{lvl}[\s>]", html, re.I))
        if c:
            s["headings"][f"h{lvl}"] = c
    s["lists"]       = len(re.findall(r"<[ou]l[\s>]", html, re.I))
    s["tables"]      = len(re.findall(r"<table[\s>]", html, re.I))
    s["forms"]       = len(re.findall(r"<form[\s>]", html, re.I))
    s["images"]      = len(re.findall(r"<img[\s>]", html, re.I))
    s["links"]       = len(re.findall(r"<a[^>]+href", html, re.I))
    s["videos"]      = len(re.findall(r"<video[\s>]|youtube\.com|vimeo\.com", html, re.I))
    s["code_blocks"] = len(re.findall(r"<(?:code|pre)[\s>]", html, re.I))
    s["iframes"]     = len(re.findall(r"<iframe[\s>]", html, re.I))
    return s


def _extract_tables(html: str) -> list:
    if not HAS_BS4:
        return []
    try:
        soup = BeautifulSoup(html, "html.parser")
        tables = []
        for tbl in soup.find_all("table"):
            headers = []
            rows = []
            for tr in tbl.find_all("tr"):
                ths = [th.get_text(strip=True) for th in tr.find_all("th")]
                if ths:
                    headers = ths
                    continue
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if cells:
                    rows.append(cells)
            if headers or rows:
                tables.append({"headers": headers, "rows": rows, "row_count": len(rows)})
        return tables
    except Exception:
        return []


def _extract_links(html: str, url: str) -> list:
    """Extract all links with text and href."""
    if not HAS_BS4:
        return []
    try:
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            abs_href = urljoin(url, href) if not href.startswith(("http", "mailto", "#")) else href
            if text and not href.startswith("#"):
                links.append({"text": text, "url": abs_href})
        return links
    except Exception:
        return []


# =========================================================================
#  SUMMARIZATION
# =========================================================================

def _summarize_text(text: str, max_words: int = DEFAULT_SUMMARY_LEN) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    key = [s.strip() for s in sentences
           if len(s.split()) >= 5
           and not re.search(r"click|subscribe|sign.up|cookie", s, re.I)]
    if not key:
        return text[:max_words * 6]
    out, wc = [], 0
    for s in key:
        sw = len(s.split())
        if wc + sw > max_words:
            break
        out.append(s)
        wc += sw
    return " ".join(out)


# =========================================================================
#  URL VALIDATION
# =========================================================================

def _validate_url(url: str) -> tuple:
    try:
        r = urlparse(url)
        if not r.scheme:
            url = f"https://{url}"
            r = urlparse(url)
        if not r.netloc:
            return False, "Invalid URL format"
        return True, url
    except Exception as e:
        return False, str(e)


def _save_results(data: dict, output_dir: Path, filename: str = "result.json") -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    fp = output_dir / filename
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    return str(fp)


# =========================================================================
#  INTELLIGENT IMAGE SCORING  (enhanced)
# =========================================================================

# Patterns in alt text / filename that suggest content value
_CONTENT_ALT_RE = re.compile(
    r"chart|graph|diagram|figure|infographic|screenshot|photo|image|illustration|"
    r"map|table|visualization|dashboard|result|output|example|sample|preview",
    re.I,
)
_NOISE_IMG_RE = re.compile(
    r"logo|icon|avatar|badge|button|arrow|sprite|pixel|tracking|spacer|"
    r"banner|ad|advertisement|promo|social|share|close|search|menu|nav",
    re.I,
)
_NEWS_IMG_RE = re.compile(
    r"cdn|images|media|static|assets|uploads|content|articles|news|photos",
    re.I,
)


def _score_image(img: dict, page_content_type: str = "generic") -> float:
    """Score an image 0.0–1.0 for likely content relevance.

    Criteria:
    - Alt text signals meaningful content (+) or noise (-)
    - URL path signals content storage location
    - Declared dimensions (large = content, small = icon)
    - Content type context (product page = images likely relevant)
    """
    score = 0.5  # neutral baseline

    url = img.get("url", "")
    alt = img.get("alt", "")
    width = img.get("width", "")
    height = img.get("height", "")

    # Alt text scoring
    if alt:
        if _CONTENT_ALT_RE.search(alt):
            score += 0.25
        if _NOISE_IMG_RE.search(alt):
            score -= 0.3
        if len(alt) > 10:
            score += 0.1  # descriptive alt = content image
    else:
        score -= 0.05  # missing alt = slightly less likely to be meaningful

    # URL path scoring
    url_lower = url.lower()
    if _NOISE_IMG_RE.search(url_lower):
        score -= 0.2
    if _NEWS_IMG_RE.search(url_lower):
        score += 0.1
    if re.search(r"\d{4,}", url_lower):  # numeric path component (e.g. year, ID) = likely content image
        score += 0.05

    # Dimension scoring
    try:
        w = int(width) if width else 0
        h = int(height) if height else 0
        if w > 0 and h > 0:
            area = w * h
            if area > 40000:    # > 200x200 = likely real content
                score += 0.2
            elif area > 10000:  # 100x100 range
                score += 0.1
            elif area < 5000:   # < ~70x70 = icon territory
                score -= 0.25
        elif w > 400 or h > 300:
            score += 0.15       # large declared dimension
    except (ValueError, TypeError):
        pass

    # Content type context
    if page_content_type in ("product",):
        score += 0.15   # product images are almost always relevant
    elif page_content_type in ("media_gallery",):
        score += 0.2
    elif page_content_type in ("documentation",):
        score += 0.1    # screenshots, diagrams

    # SVG / data URI penalty
    if url.endswith(".svg") or url.startswith("data:"):
        score -= 0.15

    # Srcset bonus (responsive = real content image)
    if img.get("has_srcset"):
        score += 0.1

    return max(0.0, min(1.0, score))


def _filter_images_by_score(
    images: list,
    page_content_type: str = "generic",
    min_score: float = 0.4,
    max_images: int = 20,
) -> list:
    """Return images sorted by relevance score, filtered by min_score."""
    scored = []
    for img in images:
        s = _score_image(img, page_content_type)
        if s >= min_score:
            scored.append({**img, "relevance_score": round(s, 3)})
    scored.sort(key=lambda x: -x["relevance_score"])
    return scored[:max_images]


# =========================================================================
#  LLM ANALYSIS PACKAGE  (new)
# =========================================================================

# Maximum characters of body text to include in LLM context.
# 12 000 chars ≈ ~3 000 tokens at average 4 chars/token — comfortably fits
# within the context window of all supported providers while preserving most
# article-length content. Increase if your provider supports a larger window.
_LLM_MAX_BODY_CHARS = 12_000
# Summary capped at ~750 tokens to keep the header section concise.
_LLM_MAX_SUMMARY_CHARS = 3_000


def _build_llm_context_package(scrape_result: dict, analysis_goal: str = "") -> dict:
    """Transform a scrape result into a clean, structured context package
    ready for the calling LLM agent to use directly.

    Returns:
        {
            "analysis_goal": str,
            "page_title": str,
            "page_url": str,
            "content_type": str,
            "word_count": int,
            "summary": str,
            "full_text": str (truncated to _LLM_MAX_BODY_CHARS),
            "metadata": dict,
            "tables": list,
            "key_images": list (scored, top 10),
            "headings": list,
            "llm_prompt": str  (ready-to-use prompt string)
        }
    """
    article = scrape_result.get("article", {})
    text_block = scrape_result.get("text", {})
    metadata = scrape_result.get("metadata", {})
    detection = scrape_result.get("detection", {})
    tables = scrape_result.get("tables", [])
    images = scrape_result.get("images", [])

    title = (
        article.get("title")
        or metadata.get("og_title")
        or metadata.get("title")
        or "Untitled"
    )
    url = scrape_result.get("url", "")
    content_type = detection.get("detected_type", "generic")

    # Best available body text
    body = (
        article.get("body_text")
        or text_block.get("full_text")
        or ""
    )
    word_count = len(body.split())

    # Truncate for LLM context
    body_truncated = body[:_LLM_MAX_BODY_CHARS]
    if len(body) > _LLM_MAX_BODY_CHARS:
        body_truncated += "\n\n[... content truncated for context window ...]"

    # Summary
    summary = scrape_result.get("summary", "")
    if not summary and body:
        summary = _summarize_text(body, 150)
    summary = summary[:_LLM_MAX_SUMMARY_CHARS]

    # Headings from text block or article
    headings = text_block.get("headings", [])

    # Top scored images
    all_imgs = images if images else scrape_result.get("images_metadata", [])
    key_images = []
    if all_imgs:
        for img in all_imgs[:30]:
            s = _score_image(img, content_type)
            if s >= 0.35:
                key_images.append({
                    "url": img.get("url", ""),
                    "alt": img.get("alt", ""),
                    "relevance_score": round(s, 3),
                })
        key_images.sort(key=lambda x: -x["relevance_score"])
        key_images = key_images[:10]

    # Build the ready-to-use LLM prompt
    goal_line = f"**Analysis Goal**: {analysis_goal}\n\n" if analysis_goal else ""
    table_summary = ""
    if tables:
        table_summary = f"\n\n**Tables found**: {len(tables)}\n"
        for i, t in enumerate(tables[:3]):
            headers = ", ".join(t.get("headers", []))
            if headers:
                table_summary += f"- Table {i+1}: {headers} ({t.get('row_count', 0)} rows)\n"

    image_summary = ""
    if key_images:
        image_summary = f"\n\n**Key Images** (top {len(key_images)} by relevance):\n"
        for img in key_images[:5]:
            image_summary += f"- {img['alt'] or 'No alt'} → {img['url']}\n"

    llm_prompt = (
        f"{goal_line}"
        f"## Web Page: {title}\n"
        f"**URL**: {url}\n"
        f"**Type**: {content_type} | **Words**: {word_count:,}\n"
        f"**Description**: {metadata.get('description', '') or metadata.get('og_description', '')}\n"
        f"{table_summary}"
        f"{image_summary}"
        f"\n---\n\n"
        f"## Page Content\n\n{body_truncated}"
    )

    return {
        "analysis_goal": analysis_goal,
        "page_title": title,
        "page_url": url,
        "content_type": content_type,
        "word_count": word_count,
        "summary": summary,
        "full_text": body_truncated,
        "metadata": metadata,
        "tables": tables[:5],  # cap for JSON size
        "key_images": key_images,
        "headings": headings[:20],
        "llm_prompt": llm_prompt,
    }


# =========================================================================
#  ACTIONS  (public API called by CLI)
# =========================================================================

def act_detect_type(url: str, output_dir: str = None, **kw) -> dict:
    """Lightweight precursory check. Returns content-type analysis for the LLM."""
    ok, url = _validate_url(url)
    if not ok:
        return {"status": "error", "error": f"Invalid URL: {url}"}

    fp = fetch_page(url, want_js=False, timeout=8)
    html = fp["html"]
    metadata = _extract_metadata(html, url)
    structure = _analyze_structure(html)
    detection = _detect_content_type(html, url, metadata, structure)

    result = {
        "status": "completed",
        "url": url,
        "timestamp": datetime.now().isoformat(),
        "fetch_method": fp["method"],
        "detection": detection,
        "metadata": metadata,
        "structure": structure,
        "capabilities": {
            "bs4": HAS_BS4, "selenium": HAS_SELENIUM,
            "requests": HAS_REQUESTS, "pil": HAS_PIL,
        },
    }
    if output_dir:
        _save_results(result, Path(output_dir), "detection.json")
    return result


def act_extract_article(url: str, output_dir: str = None,
                        wait_for_js: bool = True, wait_timeout: int = 10,
                        **kw) -> dict:
    """Reader-mode article extraction."""
    ok, url = _validate_url(url)
    if not ok:
        return {"status": "error", "error": f"Invalid URL: {url}"}

    fp = fetch_page(url, want_js=wait_for_js, timeout=wait_timeout)
    article = _extract_reader_mode(fp["html"], url)

    result = {
        "status": "completed",
        "url": url,
        "timestamp": datetime.now().isoformat(),
        "fetch_method": fp["method"],
        "article": article,
    }

    if output_dir:
        odir = Path(output_dir)
        _save_results(result, odir, "article.json")
        # Also save body text as plain .txt for easy consumption
        (odir / "article_body.txt").write_text(article["body_text"], encoding="utf-8")
        result["text_file"] = str(odir / "article_body.txt")

    return result


def act_scrape_full(url: str, output_dir: str = None,
                    extract_mode: str = "auto",
                    wait_for_js: bool = True, wait_timeout: int = 10,
                    download_imgs: bool = True, max_images: int = 50,
                    clean_text: bool = True, do_summarize: bool = True,
                    max_summary_length: int = DEFAULT_SUMMARY_LEN,
                    include_svg: bool = False,
                    **kw) -> dict:
    """Full page scrape with extract_mode routing."""
    ok, url = _validate_url(url)
    if not ok:
        raise Exception(f"Invalid URL: {url}")

    if not output_dir:
        layout = ensure_env_task_layout()
        if layout:
            output_dir = str(layout["tools_web"] / f"scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        else:
            output_dir = f"workspace/scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    odir = Path(output_dir)
    odir.mkdir(parents=True, exist_ok=True)

    result = {
        "status": "running", "url": url,
        "timestamp": datetime.now().isoformat(),
        "output_dir": str(odir), "steps": [], "warnings": [],
    }

    # --- Fetch ---
    fp = fetch_page(url, want_js=wait_for_js, timeout=wait_timeout)
    html = fp["html"]
    result["fetch_method"] = fp["method"]
    if fp["attempts"]:
        result["warnings"].extend(
            [f"fetch fallback: {a['method']} failed ({a['error'][:80]})" for a in fp["attempts"]]
        )
    result["steps"].append("fetched")

    # --- Metadata ---
    metadata = _extract_metadata(html, url)
    result["metadata"] = metadata
    result["steps"].append("metadata_extracted")

    # --- Structure ---
    structure = _analyze_structure(html)
    result["structure"] = structure
    result["steps"].append("structure_analyzed")

    # --- Content detection (for auto mode) ---
    detection = _detect_content_type(html, url, metadata, structure)
    result["detection"] = detection
    result["steps"].append("content_type_detected")

    # Resolve effective mode
    if extract_mode == "auto":
        extract_mode = detection["recommended_extract_mode"]
    result["extract_mode"] = extract_mode

    # --- Extraction by mode ---
    if extract_mode == "full":
        # FULL: run every extractor — article metadata + structured data + text
        article = _extract_reader_mode(html, url)
        result["article"] = article
        text_data = extract_text_robust(html, clean_text)
        result["text"] = text_data
        tables = _extract_tables(html)
        if tables:
            result["tables"] = tables
            result["tables_found"] = len(tables)
        links = _extract_links(html, url)
        if links:
            result["links_found"] = len(links)
            result["links"] = links[:100]
        download_imgs = True  # always grab images in full mode
        result["steps"].append("full_extraction")
    elif extract_mode == "article":
        article = _extract_reader_mode(html, url)
        result["article"] = article
        result["text"] = {
            "full_text": article["body_text"],
            "headings": [], "paragraphs": [],
            "word_count": article["word_count"],
        }
        result["steps"].append("reader_mode_extracted")
    elif extract_mode == "images_only":
        result["text"] = {"full_text": "", "headings": [], "paragraphs": [], "word_count": 0}
        download_imgs = True
        result["steps"].append("images_only_mode")
    elif extract_mode == "structured":
        text_data = extract_text_robust(html, clean_text)
        result["text"] = text_data
        tables = _extract_tables(html)
        if tables:
            result["tables"] = tables
            result["tables_found"] = len(tables)
        links = _extract_links(html, url)
        if links:
            result["links_found"] = len(links)
            result["links"] = links[:100]
        result["steps"].append("structured_extracted")
    else:  # raw / fallback
        text_data = extract_text_robust(html, clean_text)
        result["text"] = text_data
        result["steps"].append("text_extracted")

    # Save text
    if result.get("text", {}).get("full_text"):
        _save_results({"content": result["text"]["full_text"]}, odir, "text_content.json")

    # --- Summary ---
    if do_summarize and result.get("text", {}).get("full_text"):
        src = result.get("article", {}).get("body_text") or result["text"]["full_text"]
        result["summary"] = _summarize_text(src, max_summary_length)
        _save_results({"summary": result["summary"]}, odir, "summary.json")
        result["steps"].append("summarized")

    # --- Images ---
    if download_imgs:
        imgs = _extract_images_from_html(html, url, max_images, include_svg=include_svg)
        result["images_found"] = len(imgs)
        if imgs:
            downloaded = []
            for idx, img in enumerate(imgs):
                dl = _download_image(img["url"], odir, idx)
                if dl["success"]:
                    dl["alt"] = img.get("alt", "")
                    downloaded.append(dl)
            result["images_downloaded"] = len(downloaded)
            result["images"] = downloaded
            _save_results({"images": downloaded}, odir, "images_manifest.json")
            result["steps"].append("images_downloaded")

    # --- Tables (if not already done) ---
    if extract_mode not in ("structured", "images_only") and "tables" not in result:
        tables = _extract_tables(html)
        if tables:
            result["tables"] = tables
            result["tables_found"] = len(tables)
            _save_results({"tables": tables}, odir, "tables.json")
            result["steps"].append("tables_extracted")

    # --- Save raw HTML ---
    raw_path = odir / "raw_content.html"
    raw_path.write_text(html, encoding="utf-8")
    result["raw_html_file"] = str(raw_path)

    # --- Finalize ---
    result["status"] = "completed"
    _save_results(result, odir, "scrape_result.json")
    return result


def act_extract_text(url: str, output_dir: str = None,
                     wait_for_js: bool = True, wait_timeout: int = 10,
                     clean_text: bool = True, **kw) -> dict:
    ok, url = _validate_url(url)
    if not ok:
        return {"status": "error", "error": f"Invalid URL: {url}"}
    fp = fetch_page(url, want_js=wait_for_js, timeout=wait_timeout)
    text_data = extract_text_robust(fp["html"], clean_text)
    result = {"status": "completed", "url": url,
              "timestamp": datetime.now().isoformat(),
              "fetch_method": fp["method"], "text_data": text_data}
    if output_dir:
        _save_results(result, Path(output_dir))
    return result


def act_download_images(url: str, output_dir: str = None,
                        max_images: int = 50, wait_for_js: bool = False,
                        min_size: int = MIN_IMAGE_BYTES,
                        smart: bool = False,
                        min_score: float = 0.4,
                        **kw) -> dict:
    ok, url = _validate_url(url)
    if not ok:
        return {"status": "error", "error": f"Invalid URL: {url}"}
    if not output_dir:
        layout = ensure_env_task_layout()
        if layout:
            output_dir = str(layout["tools_web"] / f"images_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        else:
            output_dir = f"workspace/images_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    odir = Path(output_dir)
    fp = fetch_page(url, want_js=wait_for_js)
    # Extract more candidates than needed so the scorer has a large pool
    # to filter down to `max_images` high-quality results.
    imgs = _extract_images_from_html(fp["html"], url, max_images * 3 if smart else max_images)

    # Apply intelligent scoring filter when smart mode is on
    if smart:
        metadata = _extract_metadata(fp["html"], url)
        structure = _analyze_structure(fp["html"])
        detection = _detect_content_type(fp["html"], url, metadata, structure)
        content_type = detection.get("detected_type", "generic")
        imgs = _filter_images_by_score(imgs, content_type, min_score, max_images)

    downloaded, skipped = [], []
    for idx, img in enumerate(imgs):
        dl = _download_image(img["url"], odir, idx)
        dl["alt"] = img.get("alt", "")
        if smart:
            dl["relevance_score"] = img.get("relevance_score", 0)
        if dl["success"]:
            downloaded.append(dl)
        else:
            skipped.append(dl)
    result = {
        "status": "completed", "url": url,
        "images_found": len(imgs), "images_downloaded": len(downloaded),
        "images_skipped": len(skipped), "smart_mode": smart,
        "images": downloaded, "skipped": skipped,
        "output_dir": str(odir),
    }
    _save_results(result, odir, "download_manifest.json")
    return result


def act_analyze_structure(url: str, output_dir: str = None, **kw) -> dict:
    ok, url = _validate_url(url)
    if not ok:
        return {"status": "error", "error": f"Invalid URL: {url}"}
    fp = fetch_page(url, want_js=False)
    html = fp["html"]
    result = {
        "status": "completed", "url": url,
        "timestamp": datetime.now().isoformat(),
        "fetch_method": fp["method"],
        "metadata": _extract_metadata(html, url),
        "structure": _analyze_structure(html),
        "detection": _detect_content_type(html, url,
                                          _extract_metadata(html, url),
                                          _analyze_structure(html)),
    }
    if output_dir:
        _save_results(result, Path(output_dir))
    return result


def act_summarize(url: str, output_dir: str = None,
                  max_summary_length: int = DEFAULT_SUMMARY_LEN,
                  wait_for_js: bool = True, wait_timeout: int = 10, **kw) -> dict:
    ok, url = _validate_url(url)
    if not ok:
        return {"status": "error", "error": f"Invalid URL: {url}"}
    fp = fetch_page(url, want_js=wait_for_js, timeout=wait_timeout)
    text_data = extract_text_robust(fp["html"], clean=True)
    summary = _summarize_text(text_data["full_text"], max_summary_length)
    result = {
        "status": "completed", "url": url,
        "timestamp": datetime.now().isoformat(),
        "summary": summary,
        "original_word_count": text_data["word_count"],
        "summary_word_count": len(summary.split()),
    }
    if output_dir:
        _save_results(result, Path(output_dir))
    return result


def act_validate_url(url: str, **kw) -> dict:
    ok, norm = _validate_url(url)
    return {"status": "completed", "url": url, "valid": ok,
            "normalized_url": norm if ok else None,
            "error": None if ok else norm}


def act_analyze_content(url: str, analysis_goal: str = "",
                        output_dir: str = None,
                        wait_for_js: bool = True,
                        wait_timeout: int = 15,
                        **kw) -> dict:
    """Scrape a URL and return a structured LLM-ready context package.

    This action combines fetch + extract + structure into a single clean
    payload that an LLM agent can directly use for analysis or Q&A.
    The returned `llm_prompt` field is a ready-to-use prompt string
    combining the analysis goal with the full page content.
    """
    ok, url = _validate_url(url)
    if not ok:
        return {"status": "error", "error": f"Invalid URL: {url}"}

    # Full scrape without downloading images (keep it fast)
    try:
        scrape = act_scrape_full(
            url=url,
            extract_mode="auto",
            wait_for_js=wait_for_js,
            wait_timeout=wait_timeout,
            download_imgs=False,
            do_summarize=True,
            output_dir=output_dir,
        )
    except Exception as e:
        return {"status": "error", "url": url, "error": str(e)}

    # Also extract image metadata (no download) for scoring
    try:
        fp_html = scrape.get("raw_html_file")
        if fp_html and Path(fp_html).exists():
            html_for_imgs = Path(fp_html).read_text(encoding="utf-8", errors="ignore")
        else:
            html_for_imgs = ""
        if html_for_imgs:
            raw_imgs = _extract_images_from_html(html_for_imgs, url, 60)
            content_type = scrape.get("detection", {}).get("detected_type", "generic")
            scored_imgs = _filter_images_by_score(raw_imgs, content_type, 0.3, 15)
            scrape["images"] = scored_imgs
    except Exception:
        pass  # image scoring is best-effort

    # Build context package
    pkg = _build_llm_context_package(scrape, analysis_goal)

    result = {
        "status": "completed",
        "url": url,
        "timestamp": datetime.now().isoformat(),
        "analysis_package": pkg,
    }

    if output_dir:
        odir = Path(output_dir)
        _save_results(result, odir, "llm_context.json")
        # Also write the llm_prompt as a plain .txt file for easy consumption
        prompt_path = odir / "llm_prompt.txt"
        try:
            prompt_path.write_text(pkg["llm_prompt"], encoding="utf-8")
            result["llm_prompt_file"] = str(prompt_path)
        except OSError as exc:
            result["llm_prompt_file_error"] = str(exc)

    return result


# =========================================================================
#  SEARCH & FEED ACTIONS
# =========================================================================

def act_search(query: str, max_results: int = 10, output_dir: str = None, **kw) -> dict:
    if not query:
        return {"status": "error", "error": "query is required"}
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({"title": r.get("title",""), "url": r.get("href",""),
                                "description": r.get("body",""), "source": "duckduckgo"})
        res = {"status": "completed", "query": query,
               "timestamp": datetime.now().isoformat(),
               "results_found": len(results), "results": results}
    except ImportError:
        res = {"status": "completed", "query": query,
               "timestamp": datetime.now().isoformat(),
               "results_found": 0, "results": [],
               "note": "Install ddgs for web search: pip install ddgs"}
    except Exception as e:
        res = {"status": "error", "query": query, "error": str(e)}
    if output_dir and res.get("status") == "completed":
        _save_results(res, Path(output_dir), "search_results.json")
    return res


def act_find_feeds(url: str, output_dir: str = None, **kw) -> dict:
    ok, url = _validate_url(url)
    if not ok:
        return {"status": "error", "error": f"Invalid URL: {url}"}
    try:
        fp = fetch_page(url, want_js=False, timeout=8)
        html = fp["html"]
        feeds, seen = [], set()

        patterns = [
            r'<link[^>]*type="application/rss\+xml"[^>]*href="([^"]+)"',
            r'<link[^>]*type="application/atom\+xml"[^>]*href="([^"]+)"',
            r'<link[^>]*type="application/feed\+json"[^>]*href="([^"]+)"',
            r'<link[^>]*href="([^"]*(?:feed|rss|atom)[^"]*)"[^>]*(?:type|rel)',
        ]
        for pat in patterns:
            for m in re.findall(pat, html, re.I):
                fu = urljoin(url, m)
                if fu not in seen:
                    seen.add(fu)
                    feeds.append({"url": fu, "type": "RSS/Atom", "source": url})

        # Probe common feed paths
        base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        for path in ["/feed/","/feed.xml","/rss.xml","/atom.xml","/feed.json","/rss","/index.xml"]:
            fu = base + path
            if fu in seen:
                continue
            try:
                req = urllib.request.Request(fu, headers={"User-Agent": USER_AGENT}, method="HEAD")
                ctx = _ssl_ctx()
                kw2 = {"timeout": 4}
                if ctx:
                    kw2["context"] = ctx
                with urllib.request.urlopen(req, **kw2) as r:
                    if r.status == 200:
                        seen.add(fu)
                        feeds.append({"url": fu, "type": "RSS/Atom", "source": url})
            except Exception:
                pass

        result = {"status": "completed", "url": url,
                  "timestamp": datetime.now().isoformat(),
                  "feeds_found": len(feeds), "feeds": feeds}
        if output_dir:
            _save_results(result, Path(output_dir), "feeds_found.json")
        return result
    except Exception as e:
        return {"status": "error", "url": url, "error": str(e)}


def act_parse_feed(url: str, max_entries: int = 20, output_dir: str = None, **kw) -> dict:
    ok, url = _validate_url(url)
    if not ok:
        return {"status": "error", "error": f"Invalid URL: {url}"}
    try:
        fp = fetch_page(url, want_js=False, timeout=10)
        try:
            root = ET.fromstring(fp["html"])
        except ET.ParseError:
            return {"status": "error", "url": url, "error": "Invalid XML/feed format"}

        entries = []
        # RSS
        for item in root.findall(".//item")[:max_entries]:
            entries.append({
                "title": item.findtext("title", "Untitled"),
                "link": item.findtext("link", ""),
                "description": item.findtext("description", ""),
                "pub_date": item.findtext("pubDate", ""),
                "type": "RSS",
            })
        # Atom
        if not entries:
            ns = {"a": "http://www.w3.org/2005/Atom"}
            for entry in root.findall(".//a:entry", ns)[:max_entries]:
                link_el = entry.find("a:link", ns)
                entries.append({
                    "title": entry.findtext("a:title", "", ns),
                    "link": link_el.get("href","") if link_el is not None else "",
                    "description": entry.findtext("a:summary", "", ns),
                    "pub_date": entry.findtext("a:published", "", ns),
                    "type": "Atom",
                })

        result = {"status": "completed", "url": url,
                  "timestamp": datetime.now().isoformat(),
                  "entries_found": len(entries), "entries": entries}
        if output_dir:
            _save_results(result, Path(output_dir), "feed_entries.json")
        return result
    except Exception as e:
        return {"status": "error", "url": url, "error": str(e)}


# =========================================================================
#  CLI
# =========================================================================

ALL_ACTIONS = [
    "detect_type", "scrape_full", "extract_article", "extract_text",
    "download_images", "analyze_structure", "summarize", "validate_url",
    "analyze_content", "search", "find_feeds", "parse_feed",
]


def _safe_print_json(data: dict):
    """Print JSON safely on Windows (handles Unicode)."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    except UnicodeEncodeError:
        print(json.dumps(data, indent=2, ensure_ascii=True, default=str))

ACTION_DISPATCH = {
    "detect_type":       act_detect_type,
    "scrape_full":       act_scrape_full,
    "extract_article":   act_extract_article,
    "extract_text":      act_extract_text,
    "download_images":   act_download_images,
    "analyze_structure": act_analyze_structure,
    "summarize":         act_summarize,
    "validate_url":      act_validate_url,
    "analyze_content":   act_analyze_content,
    "search":            act_search,
    "find_feeds":        act_find_feeds,
    "parse_feed":        act_parse_feed,
}


def main():
    import argparse
    p = argparse.ArgumentParser(description="Advanced Web Scraper v2.0")
    p.add_argument("--action", required=True, choices=ALL_ACTIONS)
    p.add_argument("--url")
    p.add_argument("--query")
    p.add_argument("--analysis_goal", default="",
                   help="Analysis goal for analyze_content action")
    p.add_argument("--output_dir")
    p.add_argument("--session_id")
    p.add_argument("--extract_mode", default="auto",
                   choices=["auto","full","article","images_only","structured","raw"])
    p.add_argument("--wait_for_js", default="true")
    p.add_argument("--wait_timeout", type=int, default=15)
    p.add_argument("--download_images", default="true")
    p.add_argument("--max_images", type=int, default=20)
    p.add_argument("--max_results", type=int, default=10)
    p.add_argument("--max_entries", type=int, default=20)
    p.add_argument("--clean_text", default="true")
    p.add_argument("--summarize", default="true")
    p.add_argument("--max_summary_length", type=int, default=DEFAULT_SUMMARY_LEN)
    p.add_argument("--min_image_size", type=int, default=MIN_IMAGE_BYTES)
    p.add_argument("--smart_images", default="false",
                   help="Enable intelligent image scoring/filtering (true/false)")
    p.add_argument("--min_image_score", type=float, default=0.4,
                   help="Minimum relevance score for smart image filtering (0.0-1.0)")
    p.add_argument("--output")
    args = p.parse_args()

    # Parse boolean flags properly (argparse type=bool is broken)
    def str2bool(v):
        return v.lower() in ("true", "1", "yes")

    try:
        fn = ACTION_DISPATCH[args.action]
        kwargs = {
            "url": args.url, "query": args.query,
            "output_dir": args.output_dir,
            "extract_mode": args.extract_mode,
            "wait_for_js": str2bool(args.wait_for_js),
            "wait_timeout": args.wait_timeout,
            "download_imgs": str2bool(args.download_images),
            "max_images": args.max_images,
            "max_results": args.max_results,
            "max_entries": args.max_entries,
            "clean_text": str2bool(args.clean_text),
            "do_summarize": str2bool(args.summarize),
            "max_summary_length": args.max_summary_length,
            "min_size": args.min_image_size,
            "smart": str2bool(args.smart_images),
            "min_score": args.min_image_score,
            "analysis_goal": args.analysis_goal,
        }
        # Remove None values so functions use their defaults
        kwargs = {k: v for k, v in kwargs.items() if v is not None}

        result = fn(**kwargs)

        if args.session_id:
            log_tool_invocation(args.session_id, "web_scraper", vars(args), result)
        if args.output:
            Path(args.output).write_text(
                json.dumps(result, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8")
        _safe_print_json(result)

    except Exception as exc:
        err = {"status": "error", "action": args.action,
               "error": str(exc), "traceback": traceback.format_exc()}
        if args.session_id:
            log_error(args.session_id, "web_scraper", str(exc))
        _safe_print_json(err)
        sys.exit(1)


if __name__ == "__main__":
    main()
