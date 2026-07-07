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

def extract_ui_element_colors(soup: BeautifulSoup) -> dict[str, list[dict]]:
    """
    Extract colors from UI semantic elements with type metadata.
    Returns dict: {element_type: [{"color": "#HEX", "element_type": "type"}]}
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
        colors = _extract_colors_from_style(style)
        for color in colors:
            ui_colors["navigation"].append({"color": color, "element_type": "navigation"})

    # ── Button colors (button, input[type=button], .btn) ──────
    for btn in soup.find_all(["button", "a"]) + soup.find_all(attrs={"class": re.compile(r"btn|button")}):
        style = btn.get("style", "")
        colors = _extract_colors_from_style(style)
        for color in colors:
            ui_colors["buttons"].append({"color": color, "element_type": "buttons"})

    # ── Link colors (a, .link) ────────────────────────────────
    for link in soup.find_all("a", href=True):
        style = link.get("style", "")
        colors = _extract_colors_from_style(style)
        for color in colors:
            ui_colors["links"].append({"color": color, "element_type": "links"})

    # ── Form element colors (input, select, textarea) ────────
    for form_elem in soup.find_all(["input", "select", "textarea"]):
        style = form_elem.get("style", "")
        colors = _extract_colors_from_style(style)
        for color in colors:
            ui_colors["forms"].append({"color": color, "element_type": "forms"})

    # ── Background colors (divs, sections, containers) ────────
    for container in soup.find_all(["div", "section", "main", "article"]):
        style = container.get("style", "")
        classes = " ".join(container.get("class", []))

        # Skip image/video containers
        if any(x in classes.lower() for x in ["image", "video", "picture", "gallery", "carousel"]):
            continue

        colors = _extract_colors_from_style(style)
        for color in colors:
            ui_colors["backgrounds"].append({"color": color, "element_type": "backgrounds"})

    # ── Text colors (span, p, h1-h6 with style) ────────────────
    for text_elem in soup.find_all(["span", "p", "h1", "h2", "h3", "h4", "h5", "h6"]):
        style = text_elem.get("style", "")
        if "color" in style.lower():
            colors = _extract_colors_from_style(style)
            for color in colors:
                ui_colors["text"].append({"color": color, "element_type": "text"})

    # ── Badge/accent colors (span.badge, em, strong) ────────
    for accent in soup.find_all(["span", "em", "strong", "mark"]):
        style = accent.get("style", "")
        classes = " ".join(accent.get("class", []))
        if "badge" in classes or "accent" in classes or "tag" in classes:
            colors = _extract_colors_from_style(style)
            for color in colors:
                ui_colors["accents"].append({"color": color, "element_type": "accents"})

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


def fetch_page_colors(url: str, request_id: str) -> tuple[list[str], dict[str, dict] | None, str | None]:
    """
    Full scrape pipeline – UI elements only (no images/videos).
    Returns (color_list, coverage_dict, error_string).

    coverage_dict maps each color to {element_type, coverage, semantic_weight}
    for v7.0 semantic weighting in accessibility analysis.
    """
    html, err = fetch_html(url, request_id)
    if err:
        return [], None, err

    soup = BeautifulSoup(html, "html.parser")

    # Extract colors from UI elements with semantic type
    ui_colors = extract_ui_element_colors(soup)

    # Flatten by priority: buttons → links → nav → forms → bg → text → accents
    priority_order = ["buttons", "links", "navigation", "forms", "backgrounds", "text", "accents"]
    ui_merged = []
    element_map = {}  # Track element_type for each color
    ui_count = {}

    for element_type in priority_order:
        color_objects = ui_colors.get(element_type, [])
        for obj in color_objects:
            hex_color = obj["color"]
            ui_merged.append(hex_color)
            element_map[hex_color] = element_type
        ui_count[element_type] = len(color_objects)

    # Remove duplicates (keep first occurrence's element_type)
    seen = set()
    ui_unique = []
    for color in ui_merged:
        if color not in seen:
            ui_unique.append(color)
            seen.add(color)

    # Fallback: extract hex from HTML if UI extraction < 3 colors
    html_hex_colors = []
    if len(ui_unique) < 3:
        html_hex_colors = extract_hex_from_html(html)
        for color in html_hex_colors:
            if color not in element_map:
                element_map[color] = "backgrounds"  # Default UI elements to backgrounds

    # Combine: UI first, then HTML hex
    merged = ui_unique + html_hex_colors
    # Final dedup
    final_colors = []
    seen.clear()
    for color in merged:
        if color not in seen:
            final_colors.append(color)
            seen.add(color)

    # Build coverage dict with semantic metadata
    coverage = {
        color: {
            "element_type": element_map.get(color, "backgrounds"),
            "coverage": 50.0,  # Default coverage (could be enhanced with actual pixel analysis)
            "semantic_weight": 1.0  # Frontend will override based on SEMANTIC_WEIGHTS
        }
        for color in final_colors
    }

    logger.info(
        "[%s] Extracted UI: buttons=%d, links=%d, nav=%d, forms=%d, bg=%d, text=%d, accents=%d → %d unique + %d HTML hex → %d final",
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
        len(final_colors)
    )
    return final_colors[:12], coverage, None
