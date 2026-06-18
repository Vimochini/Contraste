# ============================================================
# Dockerfile  –  Deployment Readiness
# Runs the API behind Gunicorn (production WSGI server)
# Build:  docker build -t color-analyzer .
# Run:    docker run -p 5000:5000 color-analyzer
# ============================================================

FROM python:3.11-slim

# ── System dependencies (Pillow needs these) ─────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo-dev \
    zlib1g-dev \
 && rm -rf /var/lib/apt/lists/*

# ── Non-root user for security ────────────────────────────────
RUN useradd --create-home appuser
WORKDIR /home/appuser/app

# ── Python dependencies ───────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code ──────────────────────────────────────────
COPY . .
RUN chown -R appuser:appuser /home/appuser/app
USER appuser

# ── Runtime config (override with -e flags) ───────────────────
ENV PORT=5000
ENV DEBUG=false
ENV LOG_LEVEL=INFO

EXPOSE 5000

# ── Start with Gunicorn (NOT Flask dev server) ────────────────
# 4 worker processes, 30s timeout, bind to all interfaces
CMD ["gunicorn", \
     "--workers", "4", \
     "--timeout", "30", \
     "--bind",    "0.0.0.0:5000", \
     "--access-logfile", "-", \
     "--error-logfile",  "-", \
     "app:app"]
