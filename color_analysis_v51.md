# Color Analysis v5.1 Roadmap

## 7 Critical Improvements

### 1. Improve Color Extraction Quality
- Validate extracted colors aren't pure noise
- Filter out colors outside HSL confidence ranges
- Weight colors by extraction confidence
- Penalize low-quality extractions

**Implementation:**
```
quality_score(color) = saturation_confidence * lightness_confidence * extraction_confidence
```

### 2. Detect Real Foreground/Background Pairs
- Track color frequency from DOM/CSS vs images
- Identify likely background colors (common, large areas)
- Identify likely foreground/text colors (high contrast, positioned)
- Evaluate only meaningful pairs (not all combinations)

**Data needed from scraper:**
- Color frequency (pixel percentage)
- Color source (CSS, DOM, image)
- Spatial context (background vs accent)

### 3. Treat Neutral Colors Separately
- Separate achromatic colors (greys, blacks, whites)
- Don't include in hue clustering
- Evaluate separately for text accessibility
- Calculate harmony only from chromatic colors

**Implementation:**
```
achromatic_colors = [c for c in colors if saturation < 0.05]
chromatic_colors = [c for c in colors if saturation >= 0.05]
harmony = analyze_chromatic_only(chromatic_colors)
accessibility = evaluate_all(all_colors)
```

### 4. Merge Duplicates + Preserve Combined Coverage
- When merging similar colors, add coverage percentages
- Example: #FFFFFF (30%) + #FEFEFE (8%) = #FFFFFF (38%)
- Use combined coverage for weighting
- Track merge history for transparency

**Implementation:**
```
merged = {
    color: sum_of_coverage_for_similar_colors,
    source_colors: [original_colors_that_merged],
    count: number_of_colors_merged
}
```

### 5. Perceptually Weighted Scoring
- Replace linear scale with S-curve (more generous at edges)
- Weight by WCAG standard difficulty
- AA harder than Large → higher reward
- Factor in color importance (rare = less impact)

**Weighting:**
- AA Normal: 100% weight (most important)
- AA Large: 70% weight (less stringent)
- AAA Normal: 130% weight (premium credit)
- Critical colors: 2x multiplier
- Rare colors: 0.5x multiplier

### 6. Actionable Accessibility Recommendations
- Map scores to specific fixes, not just verdicts
- Examples:
  - "Darken #FC0404 to #C20000 for AA compliance"
  - "Replace #BBB2B2 with #808080 for better contrast"
  - "Add #FFFFFF text alternative for colorblind users"
  - "Separate accent colors: use distinct hues instead of shades"

**Implementation:**
- Suggest specific color adjustments
- Recommend luminosity changes
- Identify pairs that need swapping
- Propose alternative color schemes

### 7. Validate & Calibrate Thresholds

**Benchmark websites:**
- High accessibility (GitHub, W3C): target 85+
- Medium (Most SaaS): target 65-75
- Low (Neglected sites): < 45
- Known colorblind-friendly: 90+

**Calibration tests:**
- Test on 5 benchmark sites
- Verify harmony_score matches human perception
- Tune cluster_radius (currently 25°)
- Tune dedup threshold (currently 8.0)
- Validate ignore_coverage (5%)

**Thresholds to calibrate:**
```
CLUSTER_RADIUS = 25.0        # Group similar hues
DEDUP_THRESHOLD = 8.0        # Color similarity
MIN_COVERAGE = 5.0           # Ignore tiny colors
SATURATION_MIN = 0.12        # Chromatic detection
LIGHTNESS_MIN = 0.12         # Not pure black
LIGHTNESS_MAX = 0.88         # Not pure white
ACHROMATIC_SAT = 0.05        # Neutral colors
```

## Implementation Order

1. Add quality_score() for extracted colors
2. Enhance deduplication with coverage preservation
3. Split chromatic/achromatic analysis
4. Implement S-curve scoring
5. Add recommendation generation
6. Create benchmark validation suite
7. Calibrate thresholds against benchmarks

## Testing Strategy

```python
benchmark_sites = {
    "github.com": {"expected_score": 85, "level": "high"},
    "w3.org": {"expected_score": 90, "level": "high"},
    "stripe.com": {"expected_score": 72, "level": "medium"},
    "example.com": {"expected_score": 55, "level": "low"},
}

for site, target in benchmark_sites.items():
    score = analyze(site)
    error = abs(score - target["expected"])
    print(f"{site}: {score} (target {target['expected']}, error {error}%)")
```
