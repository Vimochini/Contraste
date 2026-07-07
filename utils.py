# ============================================================
# utils.py  –  Validation, Security, Logging, Cache
#
# Libraries integrated:
#   Pydantic     – URL/JSON input validation & type enforcement
#   Bleach       – HTML sanitization on any user-supplied text
# ============================================================
import re
import uuid
import socket
import logging
import time
from urllib.parse import urlparse

# ── Pydantic: URL/input validation ────────────────────────────
from pydantic import BaseModel, HttpUrl, field_validator, ValidationError
from pydantic import ConfigDict

# ── Bleach: HTML sanitization ─────────────────────────────────
import bleach

from config import Config

# ══════════════════════════════════════════════════════════════
# OBSERVABILITY – Structured logging with request IDs
# ══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("color_analyzer")


def new_request_id() -> str:
    return uuid.uuid4().hex[:8]


class Timer:
    """Context manager: measures and logs elapsed time."""
    def __init__(self, label: str, request_id: str):
        self.label = label
        self.rid   = request_id

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *_):
        ms = (time.perf_counter() - self.start) * 1000
        logger.info("[%s] %s completed in %.1f ms", self.rid, self.label, ms)


# ══════════════════════════════════════════════════════════════
# PYDANTIC MODELS – Input Validation & type enforcement
# ══════════════════════════════════════════════════════════════

class AnalyzeRequest(BaseModel):
    """
    Pydantic model for POST /analyze and POST /colors.
    HttpUrl automatically validates scheme, format, and structure.
    """
    model_config = ConfigDict(str_strip_whitespace=True)
    url: HttpUrl

    @field_validator("url", mode="before")
    @classmethod
    def auto_add_scheme(cls, v):
        """Auto-prepend https:// if scheme is missing."""
        if isinstance(v, str) and not v.startswith(("http://", "https://")):
            return "https://" + v
        return v


class AccessibilityRequest(BaseModel):
    """
    Pydantic model for POST /accessibility.
    Validates that colors is a list of 2–20 hex strings.
    """
    model_config = ConfigDict(str_strip_whitespace=True)
    colors: list[str]

    @field_validator("colors")
    @classmethod
    def validate_colors(cls, v):
        if len(v) < 2:
            raise ValueError("Provide at least 2 colors")
        if len(v) > 20:
            raise ValueError("Maximum 20 colors allowed")
        hex_re = re.compile(r'^#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})$')
        cleaned = []
        for i, c in enumerate(v):
            if not isinstance(c, str):
                raise ValueError(f"Color at index {i} must be a string")
            c = c.strip().upper()
            if not hex_re.match(c):
                raise ValueError(
                    f"'{c}' at index {i} is not a valid hex color — use #RRGGBB"
                )
            cleaned.append(c)
        return cleaned


def parse_analyze_request(body: dict) -> tuple[str | None, str | None]:
    """
    Validate and parse the analyze/colors request body with Pydantic.
    Returns (url_string, error_message).
    """
    try:
        model = AnalyzeRequest(**body)
        url = str(model.url)
        # Strip trailing slash that Pydantic's HttpUrl sometimes adds
        if url.endswith("/") and not body.get("url", "").endswith("/"):
            url = url.rstrip("/")
        return url, None
    except ValidationError as e:
        first_error = e.errors()[0]
        return None, f"Validation error: {first_error['msg']}"
    except Exception as e:
        return None, f"Invalid request: {str(e)}"


def parse_accessibility_request(body: dict) -> tuple[list | None, str | None]:
    """
    Validate the accessibility request body with Pydantic.
    Returns (colors_list, error_message).
    """
    try:
        model = AccessibilityRequest(**body)
        return model.colors, None
    except ValidationError as e:
        first_error = e.errors()[0]
        return None, f"Validation error: {first_error['msg']}"
    except Exception as e:
        return None, f"Invalid request: {str(e)}"


# ══════════════════════════════════════════════════════════════
# SSRF PROTECTION  (manual IP-block after Pydantic URL parse)
# ══════════════════════════════════════════════════════════════

def check_ssrf(url: str) -> str | None:
    """
    SSRF protection: block private IPs, localhost, cloud metadata.
    Returns an error string if blocked, None if safe.
    Pydantic validates the URL format; this validates the destination.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if host.lower() in Config.BLOCKED_HOSTNAMES:
        return f"SSRF protection: hostname '{host}' is not allowed"

    for prefix in Config.BLOCKED_IP_PREFIXES:
        if host.startswith(prefix):
            return f"SSRF protection: IP range '{prefix}*' is blocked"

    try:
        ip = socket.gethostbyname(host)
        for prefix in Config.BLOCKED_IP_PREFIXES:
            if ip.startswith(prefix):
                return f"SSRF protection: '{host}' resolves to private IP {ip}"
    except socket.gaierror:
        return f"Cannot resolve hostname: '{host}'"

    return None


# ══════════════════════════════════════════════════════════════
# BLEACH – HTML Sanitization
# ══════════════════════════════════════════════════════════════

def sanitize_text(raw: str) -> str:
    """
    Bleach: strip all HTML tags from any user-supplied text field.
    Prevents XSS if user input is ever reflected back in responses.
    """
    return bleach.clean(raw, tags=[], attributes={}, strip=True)


# ══════════════════════════════════════════════════════════════
# SIMPLE HEX VALIDATION  (kept for internal use by color_analysis)
# ══════════════════════════════════════════════════════════════

_HEX_RE = re.compile(r'^#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})$')


def validate_url(url: str) -> tuple[str | None, str | None]:
    """
    Validate and normalize URL, with SSRF protection.
    Returns (normalized_url, error_string). One will be None.
    """
    # Format validation
    parsed_url, parse_err = parse_analyze_request({"url": url})
    if parse_err:
        return None, parse_err

    # SSRF protection
    ssrf_err = check_ssrf(parsed_url)
    if ssrf_err:
        return None, ssrf_err

    return parsed_url, None


def validate_colors_list(colors) -> tuple[list | None, str | None]:
    """
    Validate list of hex colors.
    Returns (colors, error_string). One will be None.
    """
    return parse_accessibility_request({"colors": colors})


def validate_hex_color(color: str) -> bool:
    return bool(_HEX_RE.match(color.strip())) if isinstance(color, str) else False


# ══════════════════════════════════════════════════════════════
# IN-MEMORY LRU CACHE  (Performance Optimization)
# ══════════════════════════════════════════════════════════════

_cache: dict = {}


def cache_get(url: str):
    entry = _cache.get(url)
    if entry:
        ts, data = entry
        if time.time() - ts < Config.CACHE_TTL_SECS:
            return data
        del _cache[url]
    return None


def cache_set(url: str, data: dict):
    if len(_cache) >= Config.CACHE_MAX_SIZE:
        oldest = min(_cache, key=lambda k: _cache[k][0])
        del _cache[oldest]
    _cache[url] = (time.time(), data)
