# ============================================================
# config.py  –  All configuration from environment variables
# Deployment Readiness: never hard-code secrets or settings
# ============================================================
import os

class Config:
    # ── Server ───────────────────────────────────────────────
    PORT        = int(os.getenv("PORT", 5000))
    DEBUG       = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL   = os.getenv("LOG_LEVEL", "INFO")

    # ── HTTP client limits (Security Hardening) ───────────────
    REQUEST_TIMEOUT_SECONDS  = int(os.getenv("REQUEST_TIMEOUT", 10))
    MAX_RESPONSE_BYTES        = int(os.getenv("MAX_RESPONSE_MB", 5)) * 1024 * 1024
    MAX_IMAGE_BYTES           = int(os.getenv("MAX_IMAGE_MB", 2)) * 1024 * 1024
    MAX_IMAGES_PER_PAGE       = int(os.getenv("MAX_IMAGES", 5))

    # ── Cache ─────────────────────────────────────────────────
    CACHE_MAX_SIZE  = int(os.getenv("CACHE_MAX_SIZE", 128))   # LRU entries
    CACHE_TTL_SECS  = int(os.getenv("CACHE_TTL", 300))        # 5 minutes

    # ── SSRF block-list (Security Hardening) ──────────────────
    # Private/loopback ranges that must never be fetched
    BLOCKED_IP_PREFIXES = [
        "127.", "10.", "192.168.", "169.254.",   # loopback + private
        "::1", "fc", "fd",                       # IPv6 private
    ]
    BLOCKED_HOSTNAMES = {
        "localhost", "metadata.google.internal",  # cloud metadata
        "169.254.169.254",                        # AWS/GCP IMDS
    }
