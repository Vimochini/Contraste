# ============================================================
# scraper.py  –  Web scraping & color extraction
#
# Improvements over v1:
#   • Reuse HTTP connections with requests.Session
#   • Prefer og:image / twitter:image before first <img>
#   • Skip tiny images (< 100×100 px) and tracking pixels
#   • Strict response-size limit (no giant HTML downloads)
#   • Specific exception handling – no bare except:
# ============================================================

import io
import re
import logging
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from PIL import Image
from colorthief import ColorThief

from config import Config
from utils import logger

# ── Reuse TCP connections: Performance Optimization ───────────
_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (ColorAnalyzerBot/2.0)"})


# ══════════════════════════════════════════════════════════════
# PAGE FETCH
# ══════════════════════════════════════════════════════════════

def fetch_html(url: str, request_id: str) -> tuple[str | None, str | None]:
    """
    Download page HTML.
    Returns (html_text, error_string). One of the two will be None.
    """
    try:
        resp = _session.get(
            url,
            timeout=Config.REQUEST_TIMEOUT_SECONDS,
            stream=True,          # stream so we can enforce size limit
            allow_redirects=True,
        )
        resp.raise_for_status()

        # ── Response size limit (Security Hardening) ──────────
        chunks = []
        total = 0
        for chunk in resp.iter_content(chunk_size=8192):
            total += len(chunk)
            if total > Config.MAX_RESPONSE_BYTES:
                logger.warning("[%s] Response too large for %s", request_id, url)
                return None, "Response exceeds size limit"
            chunks.append(chunk)

        return b"".join(chunks).decode("utf-8", errors="replace"), None

    except requests.exceptions.Timeout:
        return None, f"Request timed out after {Config.REQUEST_TIMEOUT_SECONDS}s"
    except requests.exceptions.TooManyRedirects:
        return None, "Too many redirects"
    except requests.exceptions.SSLError as exc:
        return None, f"SSL error: {exc}"
    except requests.exceptions.ConnectionError as exc:
        return None, f"Connection error: {exc}"
    except requests.exceptions.HTTPError as exc:
        return None, f"HTTP {exc.response.status_code}: {exc.response.reason}"


# ══════════════════════════════════════════════════════════════
# IMAGE SELECTION  (Prefer og:image, skip tiny/tracking images)
# ══════════════════════════════════════════════════════════════

def select_images(soup: BeautifulSoup, base_url: str) -> list[str]:
    """
    Return a ranked list of image URLs to analyse:
      1. og:image meta tag
      2. twitter:image meta tag
      3. <img> tags with width/height > 100px (skip icons & pixels)
    """
    image_urls = []

    # ── Priority 1: Open Graph image ──────────────────────────
    og = soup.find("meta", property="og:image") or \
         soup.find("meta", attrs={"name": "og:image"})
    if og and og.get("content"):
        image_urls.append(urljoin(base_url, og["content"]))

    # ── Priority 2: Twitter card image ────────────────────────
    tw = soup.find("meta", attrs={"name": "twitter:image"}) or \
         soup.find("meta", attrs={"name": "twitter:image:src"})
    if tw and tw.get("content"):
        candidate = urljoin(base_url, tw["content"])
        if candidate not in image_urls:
            image_urls.append(candidate)

    # ── Priority 3: <img> tags – skip tiny ones ───────────────
    for img in soup.find_all("img", src=True):
        src = img.get("src", "").strip()
        if not src or src.startswith("data:"):
            continue

        # Heuristic: skip images declared < 100px in either dimension
        try:
            w = int(img.get("width", 0))
            h = int(img.get("height", 0))
            if (w and w < 100) or (h and h < 100):
                continue
        except (ValueError, TypeError):
            pass

        # Skip common tracking pixel paths
        lower = src.lower()
        if any(tok in lower for tok in ("pixel", "track", "beacon", "1x1", "spacer")):
            continue

        full = urljoin(base_url, src)
        if full not in image_urls:
            image_urls.append(full)

        if len(image_urls) >= Config.MAX_IMAGES_PER_PAGE + 2:   # gather a few extras
            break

    return image_urls[:Config.MAX_IMAGES_PER_PAGE + 2]


# ══════════════════════════════════════════════════════════════
# COLOR EXTRACTION FROM IMAGES  (ColorThief + PIL size check)
# ══════════════════════════════════════════════════════════════

def extract_colors_from_image_url(
    img_url: str, request_id: str
) -> list[tuple[int, int, int]]:
    """
    Download one image, verify it's not tiny, run ColorThief.
    Returns a list of (R, G, B) tuples (up to 5 dominant colors).
    Raises no exceptions – all failures are logged and return [].
    """
    try:
        resp = _session.get(
            img_url,
            timeout=Config.REQUEST_TIMEOUT_SECONDS,
            stream=True,
        )
        resp.raise_for_status()

        # Size limit for images
        data = b""
        for chunk in resp.iter_content(8192):
            data += chunk
            if len(data) > Config.MAX_IMAGE_BYTES:
                logger.debug("[%s] Image too large, skipping: %s", request_id, img_url)
                return []

        buf = io.BytesIO(data)

        # ── Skip truly tiny images (tracking pixels etc.) ─────
        try:
            with Image.open(io.BytesIO(data)) as im:
                w, h = im.size
                if w < 100 or h < 100:
                    logger.debug("[%s] Image too small (%dx%d), skipping", request_id, w, h)
                    return []
        except Exception:
            return []   # not a valid image

        # ── ColorThief: extract multiple dominant colors ───────
        thief = ColorThief(buf)
        palette = thief.get_palette(color_count=5, quality=5)
        return palette

    except requests.exceptions.Timeout:
        logger.debug("[%s] Image fetch timed out: %s", request_id, img_url)
        return []
    except requests.exceptions.RequestException as exc:
        logger.debug("[%s] Image fetch failed (%s): %s", request_id, exc, img_url)
        return []
    except Exception as exc:
        logger.debug("[%s] ColorThief error: %s", request_id, exc)
        return []


# ══════════════════════════════════════════════════════════════
# HTML COLOR EXTRACTION  (regex over inline CSS / style attrs)
# ══════════════════════════════════════════════════════════════

_HEX_PATTERN = re.compile(r'#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b')
_NOISE = {"#FFFFFF", "#000000", "#FFFFFE", "#FEFEFE", "#010101"}


def extract_hex_from_html(html: str) -> list[str]:
    """
    Regex-scan HTML/CSS text for hex color literals.
    Normalises #rgb → #rrggbb and filters near-black/white noise.
    """
    found = _HEX_PATTERN.findall(html)
    seen = set()
    result = []
    for c in found:
        c = c.upper()
        if len(c) == 4:   # expand #RGB
            c = "#" + c[1]*2 + c[2]*2 + c[3]*2
        if c in _NOISE or c in seen:
            continue
        seen.add(c)
        result.append(c)
        if len(result) >= 15:
            break
    return result


# ══════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════

def rgb_to_hex(rgb: tuple) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def fetch_page_colors(url: str, request_id: str) -> tuple[list[str], str | None]:
    """
    Full scrape pipeline.
    Returns (color_list, error_string). error_string is None on success.
    """
    html, err = fetch_html(url, request_id)
    if err:
        return [], err

    soup = BeautifulSoup(html, "html.parser")

    # HTML color literals
    html_colors = extract_hex_from_html(html)

    # Image palette colors
    image_urls = select_images(soup, url)
    image_colors: list[str] = []
    for img_url in image_urls:
        for rgb in extract_colors_from_image_url(img_url, request_id):
            h = rgb_to_hex(rgb)
            if h not in _NOISE:
                image_colors.append(h)

    # Merge: image colors first (richer signal), then HTML literals
    merged = list(dict.fromkeys(image_colors + html_colors))
    logger.info(
        "[%s] Extracted %d image colors + %d HTML colors → %d unique",
        request_id, len(image_colors), len(html_colors), len(merged)
    )
    return merged[:12], None
