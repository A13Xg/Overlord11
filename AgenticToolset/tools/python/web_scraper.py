"""
AgenticToolset - Advanced Web Scraper
======================================
Comprehensive web scraping tool for static and dynamic content.
Extracts text, downloads images, analyzes page structure, and generates summaries.

Features:
- Static HTML parsing with BeautifulSoup
- Dynamic JS-rendered content with Selenium (optional)
- Image downloading and organization
- Text cleaning and boilerplate removal
- Page structure analysis
- Content summarization
- Error handling and graceful degradation
- Organized output directory with metadata

Usage:
    python web_scraper.py --action scrape_full --url "https://example.com"
    python web_scraper.py --action scrape_full --url "https://example.com" --output_dir ./data/example
    python web_scraper.py --action extract_text --url "https://example.com"
    python web_scraper.py --action download_images --url "https://example.com"
    python web_scraper.py --action analyze_structure --url "https://example.com"
    python web_scraper.py --action summarize --url "https://example.com"
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from log_manager import log_tool_invocation, log_error

# Try to import optional dependencies
try:
    from bs4 import BeautifulSoup
    HAS_BEAUTIFULSOUP = True
except ImportError:
    HAS_BEAUTIFULSOUP = False

try:
    from PIL import Image
    from io import BytesIO
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False

# --- Constants ---

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 15
MAX_CONTENT_SIZE = 10_000_000  # 10 MB
DEFAULT_SUMMARY_LENGTH = 500

# Boilerplate patterns to remove
BOILERPLATE_PATTERNS = [
    r'cookie.*policy.*',
    r'advertisement',
    r'subscribe.*now',
    r'newsletter.*signup',
    r'social.*share',
    r'related.*articles',
    r'comments.*section',
]


# --- Utility Functions ---

def _create_ssl_context():
    """Create an SSL context that works across platforms."""
    try:
        import ssl
        return ssl.create_default_context()
    except Exception:
        return None


def _fetch_page(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Fetch raw HTML from URL with proper headers."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT},
            method="GET"
        )

        ssl_context = _create_ssl_context()

        if ssl_context:
            with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as response:
                content = response.read(MAX_CONTENT_SIZE)
        else:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                content = response.read(MAX_CONTENT_SIZE)

        return content.decode('utf-8', errors='ignore')
    except urllib.error.URLError as e:
        raise Exception(f"Failed to fetch URL: {e}")
    except Exception as e:
        raise Exception(f"Unexpected error fetching URL: {e}")


def _fetch_page_with_selenium(url: str, timeout: int = 10) -> str:
    """Fetch page content using Selenium to render JavaScript."""
    if not HAS_SELENIUM:
        raise Exception("Selenium not installed. Install with: pip install selenium")

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"user-agent={USER_AGENT}")

    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(timeout)
        driver.get(url)

        # Wait for common dynamic content to load
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_all_elements_located((By.TAG_NAME, "body"))
            )
        except Exception:
            pass  # Timeout is OK, we got what we could

        time.sleep(2)  # Allow for AJAX/JS to settle
        html = driver.page_source
        return html
    except Exception as e:
        raise Exception(f"Selenium rendering failed: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def _clean_text(text: str) -> str:
    """Clean and normalize text content."""
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()

    # Remove URLs
    text = re.sub(r'http\S+|www\.\S+', '', text)

    # Remove email addresses
    text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '', text)

    # Remove special characters but keep basic punctuation
    text = re.sub(r'[^\w\s\.\,\!\?\-\']', '', text)

    return text


def _extract_text_beautifulsoup(html: str, clean: bool = True) -> dict:
    """Extract text using BeautifulSoup."""
    if not HAS_BEAUTIFULSOUP:
        raise Exception("BeautifulSoup not installed. Install with: pip install beautifulsoup4")

    soup = BeautifulSoup(html, 'html.parser')

    # Remove script and style elements
    for script in soup(["script", "style", "nav", "footer"]):
        script.decompose()

    # Extract main content areas
    main_text = ""
    for tag in ['article', 'main', '[role="main"]']:
        element = soup.find(tag if tag.startswith('[') else tag)
        if element:
            main_text = element.get_text()
            break

    if not main_text:
        main_text = soup.get_text()

    text = _clean_text(main_text) if clean else main_text.strip()

    # Extract headings
    headings = [h.get_text().strip() for h in soup.find_all(['h1', 'h2', 'h3'])]

    # Extract paragraphs
    paragraphs = [p.get_text().strip() for p in soup.find_all('p')]

    return {
        "full_text": text,
        "headings": headings,
        "paragraphs": paragraphs,
        "word_count": len(text.split())
    }


def _extract_text_basic(html: str, clean: bool = True) -> dict:
    """Extract text using basic HTML parsing (no BeautifulSoup)."""
    # Remove script and style content
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)

    # Remove tags
    text = re.sub(r'<[^>]+>', '', html)

    # Clean the text
    text = _clean_text(text) if clean else text.strip()

    return {
        "full_text": text,
        "headings": [],
        "paragraphs": [],
        "word_count": len(text.split())
    }


def _extract_images(html: str, url: str, max_count: int = 50) -> list:
    """Extract image URLs from HTML."""
    images = []

    # Find all img tags
    img_pattern = r'<img[^>]+src=["\'](.*?)["\']'
    matches = re.findall(img_pattern, html, re.IGNORECASE)

    for img_src in matches[:max_count]:
        if not img_src:
            continue

        # Handle relative URLs
        if img_src.startswith(('http://', 'https://', '//', 'data:')):
            abs_url = img_src
        else:
            abs_url = urljoin(url, img_src)

        images.append({
            "url": abs_url,
            "source": img_src
        })

    return images


def _download_image(img_url: str, output_dir: Path, index: int) -> dict:
    """Download a single image and return metadata."""
    try:
        req = urllib.request.Request(
            img_url,
            headers={"User-Agent": USER_AGENT},
            method="GET"
        )

        ssl_context = _create_ssl_context()

        if ssl_context:
            with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
                img_data = response.read(5_000_000)  # 5MB limit per image
        else:
            with urllib.request.urlopen(req, timeout=10) as response:
                img_data = response.read(5_000_000)

        # Determine file extension
        content_type = response.headers.get('Content-Type', 'image/jpeg')
        ext = '.jpg'
        if 'png' in content_type:
            ext = '.png'
        elif 'gif' in content_type:
            ext = '.gif'
        elif 'webp' in content_type:
            ext = '.webp'

        # Save image
        filename = f"image_{index:03d}{ext}"
        filepath = output_dir / "images" / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, 'wb') as f:
            f.write(img_data)

        return {
            "success": True,
            "url": img_url,
            "filename": filename,
            "path": str(filepath),
            "size_bytes": len(img_data)
        }
    except Exception as e:
        return {
            "success": False,
            "url": img_url,
            "error": str(e)
        }


def _extract_metadata(html: str, url: str) -> dict:
    """Extract page metadata (title, description, author, etc.)."""
    metadata = {
        "url": url,
        "title": "",
        "description": "",
        "author": "",
        "keywords": "",
        "og_title": "",
        "og_description": "",
        "og_image": ""
    }

    # Extract title
    title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
    if title_match:
        metadata["title"] = title_match.group(1).strip()

    # Extract meta tags
    meta_patterns = {
        "description": r'<meta\s+name="description"\s+content="([^"]+)"',
        "author": r'<meta\s+name="author"\s+content="([^"]+)"',
        "keywords": r'<meta\s+name="keywords"\s+content="([^"]+)"',
        "og_title": r'<meta\s+property="og:title"\s+content="([^"]+)"',
        "og_description": r'<meta\s+property="og:description"\s+content="([^"]+)"',
        "og_image": r'<meta\s+property="og:image"\s+content="([^"]+)"'
    }

    for key, pattern in meta_patterns.items():
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            metadata[key] = match.group(1).strip()

    return metadata


def _extract_tables(html: str) -> list:
    """Extract tables from HTML."""
    if not HAS_BEAUTIFULSOUP:
        return []

    try:
        soup = BeautifulSoup(html, 'html.parser')
        tables = []

        for table in soup.find_all('table'):
            rows = []
            for tr in table.find_all('tr'):
                cells = [td.get_text().strip() for td in tr.find_all(['td', 'th'])]
                if cells:
                    rows.append(cells)

            if rows:
                tables.append({"rows": rows, "row_count": len(rows)})

        return tables
    except Exception:
        return []


def _analyze_structure(html: str) -> dict:
    """Analyze page structure and layout."""
    structure = {
        "headings": defaultdict(int),
        "lists": 0,
        "tables": 0,
        "forms": 0,
        "images": 0,
        "links": 0,
        "videos": 0,
        "code_blocks": 0
    }

    # Count headings
    for level in range(1, 7):
        count = len(re.findall(f'<h{level}[^>]*>', html, re.IGNORECASE))
        if count > 0:
            structure["headings"][f"h{level}"] = count

    structure["lists"] = len(re.findall(r'<[ou]l[^>]*>', html, re.IGNORECASE))
    structure["tables"] = len(re.findall(r'<table[^>]*>', html, re.IGNORECASE))
    structure["forms"] = len(re.findall(r'<form[^>]*>', html, re.IGNORECASE))
    structure["images"] = len(re.findall(r'<img[^>]*>', html, re.IGNORECASE))
    structure["links"] = len(re.findall(r'<a[^>]*href', html, re.IGNORECASE))
    structure["videos"] = len(re.findall(r'<video[^>]*>|youtube\.com|vimeo\.com', html, re.IGNORECASE))
    structure["code_blocks"] = len(re.findall(r'<code[^>]*>|<pre[^>]*>', html, re.IGNORECASE))

    structure["headings"] = dict(structure["headings"])

    return structure


def _summarize_text(text: str, max_length: int = DEFAULT_SUMMARY_LENGTH) -> str:
    """Generate a basic summary by extracting key sentences."""
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    if not sentences:
        return text[:max_length * 5]

    # Select sentences that are not too short and contain meaningful content
    key_sentences = []
    for sentence in sentences:
        words = sentence.split()
        # Skip very short sentences or those with common boilerplate
        if len(words) < 5:
            continue
        if any(pattern in sentence.lower() for pattern in ['click', 'subscribe', 'email']):
            continue
        key_sentences.append(sentence)

    # Build summary up to max_length words
    summary = ""
    word_count = 0
    for sentence in key_sentences[:len(sentences)//2 + 1]:
        words_in_sentence = len(sentence.split())
        if word_count + words_in_sentence > max_length:
            break
        summary += sentence.strip() + ". "
        word_count += words_in_sentence

    return summary.strip()


def _validate_url(url: str) -> tuple[bool, str]:
    """Validate and normalize URL."""
    try:
        result = urlparse(url)
        if not result.scheme:
            url = f"https://{url}"
            result = urlparse(url)

        if not result.netloc:
            return False, "Invalid URL format"

        return True, url
    except Exception as e:
        return False, str(e)


def _save_results(data: dict, output_dir: Path, filename: str = "result.json"):
    """Save results to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / filename

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return str(filepath)


# --- Main Actions ---

def scrape_full(url: str, output_dir: str = None, wait_for_js: bool = True,
                wait_timeout: int = 10, download_images: bool = True,
                max_images: int = 50, extract_tables: bool = True,
                include_metadata: bool = True, clean_text: bool = True,
                summarize: bool = True, max_summary_length: int = DEFAULT_SUMMARY_LENGTH) -> dict:
    """Perform full page scrape with all features."""

    # Validate URL
    is_valid, url = _validate_url(url)
    if not is_valid:
        raise Exception(f"Invalid URL: {url}")

    # Create output directory
    if not output_dir:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"workspace/scrape_{timestamp}"

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result = {
        "status": "running",
        "url": url,
        "timestamp": datetime.now().isoformat(),
        "output_dir": str(output_path),
        "steps_completed": []
    }

    try:
        # Step 1: Fetch HTML
        print(f"Fetching page: {url}")
        if wait_for_js and HAS_SELENIUM:
            html = _fetch_page_with_selenium(url, wait_timeout)
            result["steps_completed"].append("page_fetch_with_js")
        else:
            html = _fetch_page(url)
            result["steps_completed"].append("page_fetch_static")

        # Step 2: Extract metadata
        if include_metadata:
            print("Extracting metadata...")
            metadata = _extract_metadata(html, url)
            result["metadata"] = metadata
            result["steps_completed"].append("metadata_extracted")

        # Step 3: Analyze structure
        print("Analyzing page structure...")
        structure = _analyze_structure(html)
        result["structure"] = structure
        result["steps_completed"].append("structure_analyzed")

        # Step 4: Extract text
        print("Extracting text content...")
        if HAS_BEAUTIFULSOUP:
            text_data = _extract_text_beautifulsoup(html, clean_text)
        else:
            text_data = _extract_text_basic(html, clean_text)
        result["text"] = text_data
        result["steps_completed"].append("text_extracted")

        # Save text to file
        text_file = _save_results({"content": text_data["full_text"]}, output_path, "text_content.json")
        result["text_file"] = text_file

        # Step 5: Generate summary
        if summarize:
            print("Generating summary...")
            summary = _summarize_text(text_data["full_text"], max_summary_length)
            result["summary"] = summary
            result["steps_completed"].append("summary_generated")

            # Save summary to file
            summary_file = _save_results({"summary": summary}, output_path, "summary.json")
            result["summary_file"] = summary_file

        # Step 6: Extract and download images
        if download_images:
            print("Extracting images...")
            images = _extract_images(html, url, max_images)
            result["images_found"] = len(images)

            if images:
                print(f"Downloading {len(images)} images...")
                downloaded = []
                for idx, img in enumerate(images):
                    download_result = _download_image(img["url"], output_path, idx)
                    if download_result["success"]:
                        downloaded.append(download_result)

                result["images_downloaded"] = len(downloaded)
                result["images"] = downloaded
                result["steps_completed"].append("images_downloaded")

            # Save image metadata
            if images:
                images_file = _save_results({"images": result.get("images", [])}, output_path, "images_manifest.json")
                result["images_manifest"] = images_file

        # Step 7: Extract tables
        if extract_tables:
            print("Extracting tables...")
            tables = _extract_tables(html)
            if tables:
                result["tables"] = tables
                result["tables_found"] = len(tables)
                result["steps_completed"].append("tables_extracted")

                # Save tables
                tables_file = _save_results({"tables": tables}, output_path, "tables.json")
                result["tables_file"] = tables_file

        # Save raw HTML for reference
        html_file = output_path / "raw_content.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html)
        result["raw_html_file"] = str(html_file)

        # Save complete result
        result["status"] = "completed"
        result_file = _save_results(result, output_path, "scrape_result.json")
        result["result_file"] = result_file

        print(f"Scrape completed. Results saved to: {output_path}")

        return result

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        result["error_file"] = _save_results(result, output_path, "scrape_error.json")
        raise


def extract_text(url: str, output_dir: str = None, wait_for_js: bool = True,
                 wait_timeout: int = 10, clean_text: bool = True) -> dict:
    """Extract only text content from a page."""

    is_valid, url = _validate_url(url)
    if not is_valid:
        raise Exception(f"Invalid URL: {url}")

    if not output_dir:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"workspace/text_extract_{timestamp}"

    output_path = Path(output_dir)

    try:
        if wait_for_js and HAS_SELENIUM:
            html = _fetch_page_with_selenium(url, wait_timeout)
        else:
            html = _fetch_page(url)

        if HAS_BEAUTIFULSOUP:
            text_data = _extract_text_beautifulsoup(html, clean_text)
        else:
            text_data = _extract_text_basic(html, clean_text)

        result = {
            "status": "completed",
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "text_data": text_data
        }

        _save_results(result, output_path)
        return result

    except Exception as e:
        return {"status": "error", "url": url, "error": str(e)}


def download_images(url: str, output_dir: str = None, max_images: int = 50) -> dict:
    """Download all images from a page."""

    is_valid, url = _validate_url(url)
    if not is_valid:
        raise Exception(f"Invalid URL: {url}")

    if not output_dir:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"workspace/images_{timestamp}"

    output_path = Path(output_dir)

    try:
        html = _fetch_page(url)
        images = _extract_images(html, url, max_images)

        downloaded = []
        for idx, img in enumerate(images):
            result = _download_image(img["url"], output_path, idx)
            if result["success"]:
                downloaded.append(result)

        result = {
            "status": "completed",
            "url": url,
            "images_found": len(images),
            "images_downloaded": len(downloaded),
            "images": downloaded,
            "output_dir": str(output_path)
        }

        _save_results(result, output_path, "download_manifest.json")
        return result

    except Exception as e:
        return {"status": "error", "url": url, "error": str(e)}


def analyze_structure(url: str, output_dir: str = None) -> dict:
    """Analyze page structure without downloading content."""

    is_valid, url = _validate_url(url)
    if not is_valid:
        raise Exception(f"Invalid URL: {url}")

    try:
        html = _fetch_page(url)

        structure = _analyze_structure(html)
        metadata = _extract_metadata(html, url)

        result = {
            "status": "completed",
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata,
            "structure": structure
        }

        if output_dir:
            _save_results(result, Path(output_dir))

        return result

    except Exception as e:
        return {"status": "error", "url": url, "error": str(e)}


def summarize(url: str, output_dir: str = None, max_length: int = DEFAULT_SUMMARY_LENGTH,
              wait_for_js: bool = True, wait_timeout: int = 10) -> dict:
    """Generate summary of page content."""

    is_valid, url = _validate_url(url)
    if not is_valid:
        raise Exception(f"Invalid URL: {url}")

    try:
        if wait_for_js and HAS_SELENIUM:
            html = _fetch_page_with_selenium(url, wait_timeout)
        else:
            html = _fetch_page(url)

        if HAS_BEAUTIFULSOUP:
            text_data = _extract_text_beautifulsoup(html, clean=True)
        else:
            text_data = _extract_text_basic(html, clean=True)

        summary = _summarize_text(text_data["full_text"], max_length)

        result = {
            "status": "completed",
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "original_word_count": text_data["word_count"],
            "summary_word_count": len(summary.split())
        }

        if output_dir:
            _save_results(result, Path(output_dir))

        return result

    except Exception as e:
        return {"status": "error", "url": url, "error": str(e)}


def validate_url(url: str) -> dict:
    """Validate URL format."""
    is_valid, normalized_url = _validate_url(url)

    return {
        "status": "completed",
        "url": url,
        "valid": is_valid,
        "normalized_url": normalized_url if is_valid else None,
        "error": None if is_valid else normalized_url
    }


# --- Web Search Functions ---

def search(query: str, max_results: int = 10, output_dir: str = None) -> dict:
    """Search the web using DuckDuckGo or fallback method."""

    if not query:
        raise Exception("Query is required for search")

    try:
        # Try using duckduckgo-search if available
        try:
            from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                for result in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": result.get("title", ""),
                        "url": result.get("href", ""),
                        "description": result.get("body", ""),
                        "source": "duckduckgo"
                    })

            result_dict = {
                "status": "completed",
                "query": query,
                "timestamp": datetime.now().isoformat(),
                "results_found": len(results),
                "results": results
            }

        except ImportError:
            # Fallback to basic search using urllib
            results = _search_fallback(query, max_results)
            result_dict = {
                "status": "completed",
                "query": query,
                "timestamp": datetime.now().isoformat(),
                "results_found": len(results),
                "results": results,
                "note": "Using fallback search method (duckduckgo-search not installed)"
            }

        if output_dir:
            _save_results(result_dict, Path(output_dir), "search_results.json")

        return result_dict

    except Exception as e:
        return {"status": "error", "query": query, "error": str(e)}


def _search_fallback(query: str, max_results: int = 10) -> list:
    """Fallback search using basic URL encoding (limited functionality)."""
    # This is a very basic fallback that just returns URL structure
    # In production, you'd want to use a library or API
    search_url = f"https://duckduckgo.com/search?q={urllib.parse.quote(query)}"

    return [{
        "title": f"Search results for '{query}'",
        "url": search_url,
        "description": "Please install 'duckduckgo-search' for actual search results: pip install duckduckgo-search",
        "source": "fallback"
    }]


def find_feeds(url: str, output_dir: str = None) -> dict:
    """Find RSS/Atom feeds on a website."""

    is_valid, url = _validate_url(url)
    if not is_valid:
        raise Exception(f"Invalid URL: {url}")

    try:
        html = _fetch_page(url)

        feeds = []

        # Look for feed links in <link> tags
        feed_patterns = [
            r'<link[^>]*rel="alternate"[^>]*type="application/rss\+xml"[^>]*href="([^"]+)"',
            r'<link[^>]*rel="alternate"[^>]*type="application/atom\+xml"[^>]*href="([^"]+)"',
            r'<link[^>]*rel="alternate"[^>]*type="application/feed\+json"[^>]*href="([^"]+)"',
            r'<link[^>]*href="([^"]*(?:feed|rss|atom)[^"]*)"\s*(?:type|rel)',
        ]

        for pattern in feed_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                feed_url = urljoin(url, match)
                if feed_url not in [f["url"] for f in feeds]:
                    feeds.append({
                        "url": feed_url,
                        "type": "RSS/Atom",
                        "discovered_from": url
                    })

        # Also check common feed locations
        common_feeds = ["/feed/", "/feed.xml", "/rss.xml", "/atom.xml", "/feed.json"]
        base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

        for feed_path in common_feeds:
            feed_url = base_url + feed_path
            try:
                req = urllib.request.Request(feed_url, headers={"User-Agent": USER_AGENT})
                ssl_context = _create_ssl_context()
                if ssl_context:
                    with urllib.request.urlopen(req, timeout=5, context=ssl_context) as response:
                        if response.status == 200:
                            if feed_url not in [f["url"] for f in feeds]:
                                feeds.append({
                                    "url": feed_url,
                                    "type": "RSS/Atom",
                                    "discovered_from": url
                                })
            except Exception:
                pass

        result_dict = {
            "status": "completed",
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "feeds_found": len(feeds),
            "feeds": feeds
        }

        if output_dir:
            _save_results(result_dict, Path(output_dir), "feeds_found.json")

        return result_dict

    except Exception as e:
        return {"status": "error", "url": url, "error": str(e)}


def parse_feed(url: str, max_entries: int = 20, output_dir: str = None) -> dict:
    """Parse RSS/Atom feed and extract entries."""

    is_valid, url = _validate_url(url)
    if not is_valid:
        raise Exception(f"Invalid URL: {url}")

    try:
        feed_content = _fetch_page(url)

        # Parse XML feed
        try:
            root = ET.fromstring(feed_content)
        except ET.ParseError:
            return {"status": "error", "url": url, "error": "Invalid XML/Feed format"}

        entries = []

        # Handle RSS format
        items = root.findall('.//item')
        if items:
            for item in items[:max_entries]:
                title = item.findtext('title', 'Untitled')
                link = item.findtext('link', '')
                description = item.findtext('description', '')
                pub_date = item.findtext('pubDate', '')

                entries.append({
                    "title": title,
                    "link": link,
                    "description": description,
                    "pub_date": pub_date,
                    "type": "RSS"
                })

        # Handle Atom format
        if not items:
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            entries_atom = root.findall('.//atom:entry', ns)

            for entry in entries_atom[:max_entries]:
                title = entry.findtext('atom:title', '', ns)
                link_elem = entry.find('atom:link', ns)
                link = link_elem.get('href', '') if link_elem is not None else ''
                summary = entry.findtext('atom:summary', '', ns)
                published = entry.findtext('atom:published', '', ns)

                entries.append({
                    "title": title,
                    "link": link,
                    "description": summary,
                    "pub_date": published,
                    "type": "Atom"
                })

        result_dict = {
            "status": "completed",
            "url": url,
            "timestamp": datetime.now().isoformat(),
            "entries_found": len(entries),
            "entries": entries
        }

        if output_dir:
            _save_results(result_dict, Path(output_dir), "feed_entries.json")

        return result_dict

    except Exception as e:
        return {"status": "error", "url": url, "error": str(e)}


# --- CLI Interface ---

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Advanced Web Scraper Tool with Search & RSS")
    parser.add_argument("--action", required=True,
                       choices=["scrape_full", "extract_text", "download_images",
                               "analyze_structure", "summarize", "validate_url",
                               "search", "find_feeds", "parse_feed"],
                       help="Action to perform")
    parser.add_argument("--url", help="Target URL")
    parser.add_argument("--query", help="Search query (for search action)")
    parser.add_argument("--output_dir", help="Output directory for results")
    parser.add_argument("--session_id", help="Session ID for logging")
    parser.add_argument("--wait_for_js", type=bool, default=True,
                       help="Wait for JavaScript rendering")
    parser.add_argument("--wait_timeout", type=int, default=10,
                       help="Timeout for JS rendering")
    parser.add_argument("--download_images", type=bool, default=True,
                       help="Download images from page")
    parser.add_argument("--max_images", type=int, default=50,
                       help="Maximum images to download")
    parser.add_argument("--max_results", type=int, default=10,
                       help="Maximum search results to return")
    parser.add_argument("--max_entries", type=int, default=20,
                       help="Maximum feed entries to return")
    parser.add_argument("--clean_text", type=bool, default=True,
                       help="Clean text content")
    parser.add_argument("--summarize", type=bool, default=True,
                       help="Generate summary")
    parser.add_argument("--max_summary_length", type=int, default=DEFAULT_SUMMARY_LENGTH,
                       help="Maximum summary length in words")
    parser.add_argument("--output", help="Optional JSON output file")

    args = parser.parse_args()

    try:
        if args.action == "scrape_full":
            result = scrape_full(
                url=args.url,
                output_dir=args.output_dir,
                wait_for_js=args.wait_for_js,
                wait_timeout=args.wait_timeout,
                download_images=args.download_images,
                max_images=args.max_images,
                clean_text=args.clean_text,
                summarize=args.summarize,
                max_summary_length=args.max_summary_length
            )
        elif args.action == "extract_text":
            result = extract_text(
                url=args.url,
                output_dir=args.output_dir,
                wait_for_js=args.wait_for_js,
                clean_text=args.clean_text
            )
        elif args.action == "download_images":
            result = download_images(
                url=args.url,
                output_dir=args.output_dir,
                max_images=args.max_images
            )
        elif args.action == "analyze_structure":
            result = analyze_structure(
                url=args.url,
                output_dir=args.output_dir
            )
        elif args.action == "summarize":
            result = summarize(
                url=args.url,
                output_dir=args.output_dir,
                max_length=args.max_summary_length,
                wait_for_js=args.wait_for_js
            )
        elif args.action == "validate_url":
            result = validate_url(args.url)
        elif args.action == "search":
            result = search(
                query=args.query,
                max_results=args.max_results,
                output_dir=args.output_dir
            )
        elif args.action == "find_feeds":
            result = find_feeds(
                url=args.url,
                output_dir=args.output_dir
            )
        elif args.action == "parse_feed":
            result = parse_feed(
                url=args.url,
                max_entries=args.max_entries,
                output_dir=args.output_dir
            )

        # Log tool invocation
        if args.session_id:
            log_tool_invocation(
                session_id=args.session_id,
                tool_name="web_scraper",
                params=vars(args),
                result=result
            )

        # Save to output file if requested
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2)

        # Print result
        print(json.dumps(result, indent=2, ensure_ascii=False))

    except Exception as e:
        error_result = {
            "status": "error",
            "action": args.action,
            "error": str(e)
        }

        if args.session_id:
            log_error(args.session_id, "web_scraper", str(e))

        print(json.dumps(error_result, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
