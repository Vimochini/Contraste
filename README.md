# Color Analyzer API v2 – Production-Hardened

## Project Structure
```
color_analyzer_v2/
├── app.py              # Flask app, routes, error handlers
├── color_analysis.py   # Color theory + WCAG accessibility logic
├── scraper.py          # Web scraping, image selection, ColorThief
├── utils.py            # Validation, SSRF protection, logging, cache
├── config.py           # All settings via environment variables
├── requirements.txt
├── Dockerfile
└── tests/
    └── test_color_analysis.py   # Unit + integration tests
```

---

## What Was Improved (v1 → v2)

| Area | v1 | v2 |
|------|----|----|
| URL validation | Basic startswith check | Regex + SSRF hostname/IP block |
| Security | None | SSRF protection, size limits, timeouts |
| HTTP client | New connection each call | `requests.Session` (reused) |
| Image selection | First `<img>` tag | Prefer `og:image` → `twitter:image` → `<img>` |
| Tiny images | Not filtered | Skipped if < 100×100 px |
| Color scheme | Basic hue diff | Full HSL analysis with descriptions |
| Accessibility | ratio/7 × 100 | AA/AAA pass-rate scoring |
| Text contrast | White or black | Both checked; best recommended |
| Error handling | Bare `except:` | Specific exceptions + logged |
| Logging | None | Structured log with request IDs + timing |
| Caching | None | In-memory LRU cache (TTL configurable) |
| Config | Hard-coded | Environment variables via `config.py` |
| Tests | None | 40+ unit + integration tests |
| Deployment | Flask dev server | Gunicorn + Docker |

---

## How to Run

### Option A – Local (Development)

```bash
# 1. Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python app.py
# → http://127.0.0.1:5000
```

### Option B – Docker (Production)

```bash
# Build the image
docker build -t color-analyzer .

# Run with custom settings
docker run -p 5000:5000 \
  -e DEBUG=false \
  -e LOG_LEVEL=INFO \
  -e CACHE_TTL=600 \
  color-analyzer
```

### Option C – Gunicorn directly (no Docker)

```bash
pip install -r requirements.txt
gunicorn --workers 4 --bind 0.0.0.0:5000 app:app
```

---

## Run Tests

```bash
# Install pytest (already in requirements.txt)
python -m pytest tests/ -v

# Run a single test class
python -m pytest tests/ -v -k "TestContrastRatio"
```

Expected output:
```
tests/test_color_analysis.py::TestHexToRgb::test_white PASSED
tests/test_color_analysis.py::TestContrastRatio::test_black_on_white_is_21 PASSED
... (40+ tests)
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5000` | Port to listen on |
| `DEBUG` | `false` | Flask debug mode |
| `LOG_LEVEL` | `INFO` | Logging level |
| `REQUEST_TIMEOUT` | `10` | HTTP timeout (seconds) |
| `MAX_RESPONSE_MB` | `5` | Max page size to download |
| `MAX_IMAGE_MB` | `2` | Max image size |
| `MAX_IMAGES` | `5` | Max images per page |
| `CACHE_TTL` | `300` | Cache time-to-live (seconds) |
| `CACHE_MAX_SIZE` | `128` | Max cached URLs |

---

## API Endpoints

### POST /analyze  ← Main endpoint
```json
Request:  { "url": "https://example.com" }
Response:
{
  "url": "https://example.com",
  "request_id": "a1b2c3d4",
  "extracted_colors": ["#4A90D9", "#FFFFFF", "#1A1A2E"],
  "color_scheme": {
    "scheme": "Complementary",
    "description": "Colors roughly opposite on the wheel.",
    "hues_used": [207.5, 28.3],
    "max_hue_distance_deg": 179.2
  },
  "accessibility": {
    "pairs": [
      {
        "color_1": "#4A90D9",
        "color_2": "#FFFFFF",
        "contrast_ratio": 3.45,
        "aa_normal": false,
        "aa_large": true,
        "aaa_normal": false,
        "label": "AA-Large"
      }
    ],
    "accessibility_score": 33.3,
    "score_label": "Fair – improvements needed"
  },
  "palette_suggestions": [
    {
      "color": "#4A90D9",
      "recommended_text": "#000000",
      "best_ratio": 5.1,
      "best_wcag": "AA"
    }
  ]
}
```

### POST /accessibility  ← Test your own colors
```json
Request:  { "colors": ["#FF5733", "#FFFFFF", "#000000"] }
```

### POST /colors  ← Extraction only
```json
Request:  { "url": "https://example.com" }
```

### GET /health  ← Load-balancer probe

---

## GitHub Version Control

```bash
git init
git add .
git commit -m "feat: Color Analyzer API v2 – hardened & tested"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/color-analyzer-api.git
git push -u origin main
```
