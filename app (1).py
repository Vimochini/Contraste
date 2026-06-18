# ============================================================
# app.py  –  Website Color Theory & Accessibility Analyzer API
#            Version 3.0 – All security libraries integrated
#
# Libraries used here:
#   Flask-Talisman  – secure HTTP headers + HTTPS enforcement
#   Flask-Limiter   – rate limiting (prevent abuse)
#   Flask-Smorest   – OpenAPI/Swagger docs auto-generated
# ============================================================

from flask import Flask, request, jsonify, g
from flask_smorest import Api, Blueprint
import marshmallow as ma
import time
import logging
import os

from config  import Config
from utils   import (
    parse_analyze_request, parse_accessibility_request,
    check_ssrf, sanitize_text,
    new_request_id, Timer, cache_get, cache_set, logger,
)
from scraper import fetch_page_colors
from color_analysis import (
    detect_color_scheme, evaluate_color_pairs,
    evaluate_against_black_and_white, suggest_palette,
)

# ── Flask App ─────────────────────────────────────────────────
app = Flask(__name__)
app.config["JSON_SORT_KEYS"]     = False
app.config["API_TITLE"]          = "Color Analyzer API"
app.config["API_VERSION"]        = "v3"
app.config["OPENAPI_VERSION"]    = "3.0.3"
app.config["OPENAPI_URL_PREFIX"] = "/"
app.config["OPENAPI_SWAGGER_UI_PATH"] = "/docs"
app.config["OPENAPI_SWAGGER_UI_URL"]  = \
    "https://cdn.jsdelivr.net/npm/swagger-ui-dist/"

# ══════════════════════════════════════════════════════════════
# FLASK-TALISMAN – Secure HTTP headers + HTTPS enforcement
# Forces: HSTS, X-Content-Type-Options, X-Frame-Options, CSP
# ══════════════════════════════════════════════════════════════
from flask_talisman import Talisman

# In development (DEBUG=true) we disable force_https so plain
# http://localhost still works. In production it forces HTTPS.
Talisman(
    app,
    force_https=not Config.DEBUG,          # True in production
    strict_transport_security=True,        # HSTS header
    session_cookie_secure=not Config.DEBUG,
    content_security_policy={
        "default-src": "'self'",
        "script-src":  "'self' cdn.jsdelivr.net",  # allow Swagger UI
        "style-src":   "'self' cdn.jsdelivr.net 'unsafe-inline'",
    },
)

# ══════════════════════════════════════════════════════════════
# FLASK-LIMITER – Rate limiting (prevent abuse)
# Default: 60 requests/minute per IP across all endpoints
# ══════════════════════════════════════════════════════════════
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,       # limit per client IP
    default_limits=["60 per minute"],  # global default
    storage_uri="memory://",           # in-memory (use Redis in prod)
)

# ══════════════════════════════════════════════════════════════
# FLASK-SMOREST – OpenAPI docs (visit /docs when running)
# ══════════════════════════════════════════════════════════════
smorest_api = Api(app)

# Marshmallow schemas used by Flask-Smorest for docs & validation
class AnalyzeSchema(ma.Schema):
    url = ma.fields.Url(required=True, metadata={"example": "https://example.com"})

class ColorsListSchema(ma.Schema):
    colors = ma.fields.List(
        ma.fields.Str(),
        required=True,
        metadata={"example": ["#FF5733", "#FFFFFF", "#333333"]},
    )

blp = Blueprint(
    "color_analyzer", "color_analyzer",
    url_prefix="",
    description="Analyze website color palettes and WCAG accessibility",
)


# ══════════════════════════════════════════════════════════════
# REQUEST LIFECYCLE
# ══════════════════════════════════════════════════════════════

@app.before_request
def _attach_request_id():
    g.request_id = new_request_id()
    g.start_time = time.perf_counter()
    logger.info("[%s] %s %s", g.request_id, request.method, request.path)


@app.after_request
def _log_response(response):
    ms = (time.perf_counter() - g.start_time) * 1000
    logger.info("[%s] → %d (%.1f ms)", g.request_id, response.status_code, ms)
    response.headers["X-Request-ID"] = g.request_id
    return response


# ══════════════════════════════════════════════════════════════
# ERROR HELPER
# ══════════════════════════════════════════════════════════════

def err(message: str, status: int = 400):
    logger.warning("[%s] Error %d: %s", g.request_id, status, message)
    return jsonify({"error": message, "request_id": g.request_id, "status": status}), status


# ══════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "api":     "Website Color Theory & Accessibility Analyzer",
        "version": "3.0.0",
        "status":  "running",
        "docs":    "/docs  ← Interactive Swagger UI",
        "endpoints": {
            "GET  /health":        "Health check",
            "POST /analyze":       "Full pipeline",
            "POST /colors":        "Color extraction only",
            "POST /accessibility": "WCAG check on your color list",
        },
        "security": {
            "rate_limit":    "60 requests/minute per IP",
            "https":         "enforced in production (Flask-Talisman)",
            "headers":       "HSTS, CSP, X-Frame-Options applied",
            "ssrf":          "private IPs and localhost blocked",
            "input":         "Pydantic validation on all inputs",
            "sanitization":  "Bleach strips HTML from text fields",
        },
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "request_id": g.request_id})


# ── POST /analyze ─────────────────────────────────────────────
@app.route("/analyze", methods=["POST"])
@limiter.limit("20 per minute")      # stricter limit for expensive endpoint
def analyze():
    body = request.get_json(silent=True)
    if not body:
        return err("Request body must be JSON with a 'url' field")

    # Sanitize raw text input with Bleach before validation
    if "url" in body and isinstance(body["url"], str):
        body["url"] = sanitize_text(body["url"])

    # Pydantic validation
    url, val_err = parse_analyze_request(body)
    if val_err:
        return err(val_err)

    # SSRF check
    ssrf_err = check_ssrf(url)
    if ssrf_err:
        return err(ssrf_err, 403)

    # Cache
    cached = cache_get(url)
    if cached:
        logger.info("[%s] Cache hit for %s", g.request_id, url)
        cached.update({"cached": True, "request_id": g.request_id})
        return jsonify(cached)

    # Scrape
    with Timer("color extraction", g.request_id):
        colors, scrape_err = fetch_page_colors(url, g.request_id)
    if scrape_err:
        return err(scrape_err, 502)
    if not colors:
        return err("No colors could be extracted from that page", 404)

    scheme        = detect_color_scheme(colors)
    accessibility = evaluate_color_pairs(colors)
    suggestions   = suggest_palette(colors)

    result = {
        "url":                 url,
        "request_id":          g.request_id,
        "extracted_colors":    colors,
        "total_colors_found":  len(colors),
        "color_scheme":        scheme,
        "accessibility":       accessibility,
        "palette_suggestions": suggestions,
        "tip":  "Aim for contrast ratio ≥ 4.5 (WCAG AA) for normal text.",
        "cached": False,
    }
    cache_set(url, result)
    return jsonify(result)


# ── POST /colors ──────────────────────────────────────────────
@app.route("/colors", methods=["POST"])
@limiter.limit("30 per minute")
def colors_only():
    body = request.get_json(silent=True)
    if not body:
        return err("Request body must be JSON with a 'url' field")

    if "url" in body and isinstance(body["url"], str):
        body["url"] = sanitize_text(body["url"])

    url, val_err = parse_analyze_request(body)
    if val_err:
        return err(val_err)

    ssrf_err = check_ssrf(url)
    if ssrf_err:
        return err(ssrf_err, 403)

    colors, scrape_err = fetch_page_colors(url, g.request_id)
    if scrape_err:
        return err(scrape_err, 502)
    if not colors:
        return err("No colors extracted", 404)

    return jsonify({
        "url":          url,
        "request_id":   g.request_id,
        "colors":       colors,
        "color_scheme": detect_color_scheme(colors),
    })


# ── POST /accessibility ───────────────────────────────────────
@app.route("/accessibility", methods=["POST"])
@limiter.limit("60 per minute")
def accessibility_only():
    body = request.get_json(silent=True)
    if not body:
        return err("Request body must be JSON with a 'colors' array")

    colors, val_err = parse_accessibility_request(body)
    if val_err:
        return err(val_err)

    result      = evaluate_color_pairs(colors)
    bw_checks   = [evaluate_against_black_and_white(c) for c in colors]
    suggestions = suggest_palette(colors)

    return jsonify({
        "request_id":           g.request_id,
        "colors_checked":       colors,
        "accessibility":        result,
        "black_white_analysis": bw_checks,
        "suggestions":          suggestions,
    })


# ══════════════════════════════════════════════════════════════
# GLOBAL ERROR HANDLERS
# ══════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(_e):
    return err("Endpoint not found. See GET / for routes.", 404)

@app.errorhandler(405)
def method_not_allowed(_e):
    return err(f"Method '{request.method}' not allowed here.", 405)

@app.errorhandler(429)
def rate_limited(_e):
    # Flask-Limiter triggers this when limit is exceeded
    return err("Rate limit exceeded. Max 60 requests/minute.", 429)

@app.errorhandler(500)
def internal_error(_e):
    logger.exception("[%s] Unhandled exception", getattr(g, "request_id", "?"))
    return err("Internal server error. Check server logs.", 500)


# ══════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("  Color Analyzer API v3  –  http://127.0.0.1:5000")
    print("  Swagger UI docs:          http://127.0.0.1:5000/docs")
    print("  (Development mode – use Gunicorn for production)")
    print("=" * 60)
    app.run(debug=Config.DEBUG, port=Config.PORT)
