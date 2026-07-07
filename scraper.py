# ============================================================
# scraper.py  –  Web scraping & UI color extraction
#
# v2.0 – UI Elements Only (No Images/Videos)
#   • Extract from CSS backgrounds, text, buttons, links
#   • Focus on form elements, navigation, interactive UI
#   • Skip images, videos, and visual media
#   • Reuse HTTP connections with requests.Session
#   • Strict response-size limit
# ============================================================

import re
import logging
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup

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
# UI ELEMENT COLOR EXTRACTION
# ══════════════════════════════════════════════════════════════

def extract_ui_element_colors(soup: BeautifulSoup) -> dict[str, list[str]]:
    """
    Extract colors from UI semantic elements.
    Returns dict: {element_type: [colors]}
    """
    ui_colors = {
        "backgrounds": [],
        "text": [],
        "buttons": [],
        "links": [],
        "forms": [],
        "navigation": [],
        "accents": [],
    }

    # ── Navigation colors (nav, header, menu) ──────────────────
    for nav in soup.find_all(["nav", "header"]):
        style = nav.get("style", "")
        classes = " ".join(nav.get("class", []))
        colors = _extract_colors_from_style(style)
        ui_colors["navigation"].extend(colors)

    # ── Button colors (button, input[type=button], .btn) ──────
    for btn in soup.find_all(["button", "a"]) + soup.find_all(attrs={"class": re.compile(r"btn|button")}):
        style = btn.get("style", "")
        colors = _extract_colors_from_style(style)
        ui_colors["buttons"].extend(colors)

    # ── Link colors (a, .link) ────────────────────────────────
    for link in soup.find_all("a", href=True):
        style = link.get("style", "")
        colors = _extract_colors_from_style(style)
        if colors:
            ui_colors["links"].extend(colors)

    # ── Form element colors (input, select, textarea) ────────
    for form_elem in soup.find_all(["input", "select", "textarea"]):
        style = form_elem.get("style", "")
        colors = _extract_colors_from_style(style)
        ui_colors["forms"].extend(colors)

    # ── Background colors (divs, sections, containers) ────────
    for container in soup.find_all(["div", "section", "main", "article"]):
        style = container.get("style", "")
        classes = " ".join(container.get("class", []))

        # Skip image/video containers
        if any(x in classes.lower() for x in ["image", "video", "picture", "gallery", "carousel"]):
            continue

        colors = _extract_colors_from_style(style)
        if colors:
            ui_colors["backgrounds"].extend(colors)

    # ── Text colors (span, p, h1-h6 with style) ────────────────
    for text_elem in soup.find_all(["span", "p", "h1", "h2", "h3", "h4", "h5", "h6"]):
        style = text_elem.get("style", "")
        colors = _extract_colors_from_style(style)
        if colors and "color" in style.lower():
            ui_colors["text"].extend(colors)

    # ── Badge/accent colors (span.badge, em, strong) ────────
    for accent in soup.find_all(["span", "em", "strong", "mark"]):
        style = accent.get("style", "")
        classes = " ".join(accent.get("class", []))
        if "badge" in classes or "accent" in classes or "tag" in classes:
            colors = _extract_colors_from_style(style)
            ui_colors["accents"].extend(colors)

    return ui_colors


def _extract_colors_from_style(style_str: str) -> list[str]:
    """Extract hex colors from a CSS style attribute."""
    if not style_str:
        return []
    colors = _HEX_PATTERN.findall(style_str)
    result = []
    for c in colors:
        c = c.upper()
        if len(c) == 4:
            c = "#" + c[1]*2 + c[2]*2 + c[3]*2
        if c not in _NOISE and c not in result:
            result.append(c)
    return result


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
    Full scrape pipeline – UI elements only (no images/videos).
    Priority: explicit UI element colors > HTML hex patterns
    Returns (color_list, error_string). error_string is None on success.
    """
    html, err = fetch_html(url, request_id)
    if err:
        return [], err

    soup = BeautifulSoup(html, "html.parser")

    # Extract colors from UI elements (buttons, links, nav, forms, etc.)
    ui_colors = extract_ui_element_colors(soup)

    # Flatten UI colors by priority: buttons → links → nav → forms → backgrounds → text → accents
    priority_order = ["buttons", "links", "navigation", "forms", "backgrounds", "text", "accents"]
    ui_merged = []
    ui_count = {}
    for element_type in priority_order:
        colors = ui_colors.get(element_type, [])
        ui_merged.extend(colors)
        ui_count[element_type] = len(colors)

    # Remove duplicates while preserving order
    ui_unique = list(dict.fromkeys(ui_merged))

    # Fallback: extract hex colors from HTML if UI extraction yielded nothing
    html_hex_colors = []
    if len(ui_unique) < 3:
        html_hex_colors = extract_hex_from_html(html)

    # Combine: UI colors first, then HTML hex patterns
    merged = list(dict.fromkeys(ui_unique + html_hex_colors))

    logger.info(
        "[%s] Extracted UI: buttons=%d, links=%d, nav=%d, forms=%d, bg=%d, text=%d, accents=%d (total %d) + %d HTML hex → %d unique",
        request_id,
        ui_count.get("buttons", 0),
        ui_count.get("links", 0),
        ui_count.get("navigation", 0),
        ui_count.get("forms", 0),
        ui_count.get("backgrounds", 0),
        ui_count.get("text", 0),
        ui_count.get("accents", 0),
        len(ui_unique),
        len(html_hex_colors),
        len(merged)
    )
    return merged[:12], None
