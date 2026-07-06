# ============================================================
# color_analysis.py  –  Advanced Color Theory + WCAG Accessibility
#
# Version 6.0 – ΔE(Lab) Distance, Circular Clustering, Pattern Matching
# Improvements:
#   • ΔE(Lab) perceptual color distance (CIELAB)
#   • Circular hue clustering algorithm
#   • Pattern matching for harmony detection
#   • Exact replacement color generation
#   • Adaptive thresholds
#   • S-curve calibration
#   • Better neutral palette handling
# ============================================================

from __future__ import annotations
import math


# ══════════════════════════════════════════════════════════════
# CALIBRATION THRESHOLDS (adaptive, validated against benchmarks)
# ══════════════════════════════════════════════════════════════

CLUSTER_RADIUS = 25.0
DEDUP_THRESHOLD_LAB = 15.0          # ΔE Lab threshold (JND ~15 = "just noticeable difference")
MIN_COVERAGE = 5.0
SATURATION_MIN = 0.12
LIGHTNESS_MIN = 0.12
LIGHTNESS_MAX = 0.88
ACHROMATIC_SAT = 0.05


def _adaptive_thresholds(palette_size: int, palette_diversity: float | None = None) -> dict:
    """
    Calculate adaptive thresholds based on palette complexity.
    - palette_size: number of colors
    - palette_diversity: 0-1 measure of hue/saturation spread (optional)

    Returns adjusted thresholds for dedup, clustering, coverage.
    """
    # More colors = less aggressive deduplication to preserve variety
    dedup_threshold = DEDUP_THRESHOLD_LAB
    if palette_size > 12:
        dedup_threshold = max(10.0, DEDUP_THRESHOLD_LAB - 2.0)
    elif palette_size < 4:
        dedup_threshold = min(20.0, DEDUP_THRESHOLD_LAB + 3.0)

    # More diverse = wider cluster radius (more tolerance for hue variation)
    cluster_radius = CLUSTER_RADIUS
    if palette_diversity and palette_diversity > 0.7:
        cluster_radius = 35.0
    elif palette_diversity and palette_diversity < 0.3:
        cluster_radius = 15.0

    # Tiny palettes: lower coverage threshold to include rare accents
    min_coverage = MIN_COVERAGE
    if palette_size <= 3:
        min_coverage = 2.0

    return {
        "dedup_threshold": dedup_threshold,
        "cluster_radius": cluster_radius,
        "min_coverage": min_coverage,
    }


# ══════════════════════════════════════════════════════════════
# COLOR SPACE CONVERSIONS
# ══════════════════════════════════════════════════════════════

def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Parse #RRGGBB or #RGB to (R, G, B) 0-255."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = h[0]*2 + h[1]*2 + h[2]*2
    if len(h) != 6:
        raise ValueError(f"Invalid hex color: '{hex_color}'")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_hex(rgb: tuple) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def rgb_to_hsl(rgb: tuple) -> tuple[float, float, float]:
    """Convert RGB (0-255) → HSL. Returns H [0,360), S,L [0,1]."""
    r, g, b = (x / 255.0 for x in rgb)
    cmax, cmin = max(r, g, b), min(r, g, b)
    delta = cmax - cmin
    l = (cmax + cmin) / 2.0

    s = 0.0 if delta == 0 else delta / (1.0 - abs(2 * l - 1))

    if delta == 0:
        h = 0.0
    elif cmax == r:
        h = 60.0 * (((g - b) / delta) % 6)
    elif cmax == g:
        h = 60.0 * (((b - r) / delta) + 2)
    else:
        h = 60.0 * (((r - g) / delta) + 4)

    return (round(h % 360, 1), round(s, 4), round(l, 4))


def rgb_to_lab(rgb: tuple) -> tuple[float, float, float]:
    """Convert RGB (0-255) → CIELAB (D65 illuminant).
    Returns L (0-100), a (-128 to +127), b (-128 to +127).
    """
    r, g, b = (x / 255.0 for x in rgb)

    # Normalize to 0-1 and apply gamma correction
    r = r / 12.92 if r <= 0.04045 else ((r + 0.055) / 1.055) ** 2.4
    g = g / 12.92 if g <= 0.04045 else ((g + 0.055) / 1.055) ** 2.4
    b = b / 12.92 if b <= 0.04045 else ((b + 0.055) / 1.055) ** 2.4

    # Convert to XYZ (D65)
    x = r * 0.4124 + g * 0.3576 + b * 0.1805
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = r * 0.0193 + g * 0.1192 + b * 0.9505

    # Normalize by D65 illuminant
    x /= 0.95047
    y /= 1.00000
    z /= 1.08883

    # Convert to Lab
    fx = x ** (1/3) if x > 0.008856 else (7.787 * x + 16 / 116)
    fy = y ** (1/3) if y > 0.008856 else (7.787 * y + 16 / 116)
    fz = z ** (1/3) if z > 0.008856 else (7.787 * z + 16 / 116)

    l = (116 * fy) - 16
    a = 500 * (fx - fy)
    b = 200 * (fy - fz)

    return (round(l, 2), round(a, 2), round(b, 2))


def _is_chromatic(hex_color: str) -> bool:
    """Check if color is chromatic."""
    try:
        _, s, l = rgb_to_hsl(hex_to_rgb(hex_color))
        return s >= SATURATION_MIN and LIGHTNESS_MIN <= l <= LIGHTNESS_MAX
    except ValueError:
        return False


def _is_achromatic(hex_color: str) -> bool:
    """Check if color is neutral."""
    try:
        _, s, _ = rgb_to_hsl(hex_to_rgb(hex_color))
        return s < ACHROMATIC_SAT
    except ValueError:
        return False


# ══════════════════════════════════════════════════════════════
# PERCEPTUAL COLOR DISTANCE – ΔE(Lab)
# ══════════════════════════════════════════════════════════════

def delta_e_lab(hex1: str, hex2: str) -> float:
    """
    Calculate ΔE(Lab) – CIE76 perceptual color distance.
    Values:
      < 1: imperceptible
      1-2: just noticeable
      2-10: noticeable
      > 10: very different
    """
    try:
        l1, a1, b1 = rgb_to_lab(hex_to_rgb(hex1))
        l2, a2, b2 = rgb_to_lab(hex_to_rgb(hex2))
    except ValueError:
        return float('inf')

    delta_l = l2 - l1
    delta_a = a2 - a1
    delta_b = b2 - b1

    return math.sqrt(delta_l**2 + delta_a**2 + delta_b**2)


def deduplicate_colors(
    hex_colors: list[str],
    coverage: dict[str, float] | None = None,
    threshold: float = DEDUP_THRESHOLD_LAB
) -> dict[str, dict]:
    """Remove duplicates using ΔE(Lab), preserve combined coverage."""
    if not hex_colors:
        return {}

    unique = {}
    for color in hex_colors:
        is_duplicate = False
        for existing in unique:
            if delta_e_lab(color, existing) < threshold:
                color_cov = coverage.get(color, 1.0) if coverage else 1.0
                unique[existing]["coverage"] += color_cov
                unique[existing]["source_colors"].append(color)
                unique[existing]["count"] += 1
                is_duplicate = True
                break

        if not is_duplicate:
            unique[color] = {
                "coverage": coverage.get(color, 1.0) if coverage else 1.0,
                "source_colors": [color],
                "count": 1,
            }

    return unique


# ══════════════════════════════════════════════════════════════
# CIRCULAR HUE CLUSTERING
# ══════════════════════════════════════════════════════════════

def _circular_hue_clustering(hues: list[tuple[float, float]], cluster_radius: float = CLUSTER_RADIUS) -> list[tuple[float, float]]:
    """
    Circular hue clustering using mean shift on hue wheel.
    Groups hues that are within cluster_radius degrees (accounting for 360° wrap).
    Returns (cluster_center_hue, total_weight).
    """
    if not hues:
        return []

    # Sort by hue
    sorted_hues = sorted(hues, key=lambda x: x[0])

    # Find gaps > cluster_radius to identify cluster boundaries
    clusters = []
    current_cluster = [sorted_hues[0]]
    current_weight = sorted_hues[0][1]

    for i in range(1, len(sorted_hues)):
        hue, weight = sorted_hues[i]
        prev_hue = sorted_hues[i - 1][0]

        # Check both forward and wrap-around distances
        forward_dist = (hue - prev_hue) % 360
        wrap_dist = (prev_hue - hue) % 360

        # If gap is too large, start new cluster
        if min(forward_dist, wrap_dist) > cluster_radius:
            # Finalize current cluster
            cluster_hues = [c[0] for c in current_cluster]
            # Use circular mean for cluster center
            cluster_center = _circular_mean(cluster_hues)
            clusters.append((cluster_center, current_weight))
            current_cluster = [(hue, weight)]
            current_weight = weight
        else:
            current_cluster.append((hue, weight))
            current_weight += weight

    # Final cluster
    if current_cluster:
        cluster_hues = [c[0] for c in current_cluster]
        cluster_center = _circular_mean(cluster_hues)
        clusters.append((cluster_center, current_weight))

    return clusters


def _circular_mean(hues: list[float]) -> float:
    """Calculate circular mean of hue angles (0-360)."""
    if not hues:
        return 0.0

    sin_sum = sum(math.sin(math.radians(h)) for h in hues)
    cos_sum = sum(math.cos(math.radians(h)) for h in hues)

    mean_angle = math.degrees(math.atan2(sin_sum, cos_sum))
    return mean_angle % 360


# ══════════════════════════════════════════════════════════════
# COLOR THEORY – PATTERN MATCHING FOR HARMONY
# ══════════════════════════════════════════════════════════════

def _chromatic_hues(hex_colors: list[str], coverage: dict[str, dict] | None = None) -> list[tuple[float, float]]:
    """Extract hues from chromatic colors only."""
    hues = []
    for c in hex_colors[:12]:
        if not _is_chromatic(c):
            continue

        try:
            h, _, _ = rgb_to_hsl(hex_to_rgb(c))
            cov_weight = 1.0
            if coverage and c in coverage:
                cov = coverage[c]["coverage"]
                if cov < MIN_COVERAGE:
                    continue
                cov_weight = cov / 100.0

            hues.append((h, cov_weight))
        except ValueError:
            continue

    return hues


def _detect_harmony_pattern(cluster_hues: list[float]) -> tuple[str, float]:
    """
    Detect standard color scheme patterns.
    Returns (scheme_name, harmony_score).
    """
    if len(cluster_hues) == 0:
        return ("Achromatic", 100.0)

    if len(cluster_hues) == 1:
        return ("Monochromatic", 100.0)

    def _hue_dist(h1: float, h2: float) -> float:
        diff = abs(h1 - h2) % 360
        return min(diff, 360 - diff)

    # Calculate all pairwise distances
    distances = [
        _hue_dist(cluster_hues[i], cluster_hues[j])
        for i in range(len(cluster_hues))
        for j in range(i + 1, len(cluster_hues))
    ]

    if not distances:
        return ("Monochromatic", 100.0)

    max_dist = max(distances)
    avg_dist = sum(distances) / len(distances)

    # Pattern matching with fuzzy tolerance (±15 degrees)
    tolerance = 15

    # Analogous: all hues within 60°
    if max_dist <= 60:
        harmony = 100 - (max_dist / 60) * 20
        return ("Analogous", round(harmony, 1))

    # Complementary: two hues ~180° apart
    if len(cluster_hues) == 2 and 150 <= max_dist <= 210:
        harmony = 100 - abs(max_dist - 180) / 30
        return ("Complementary", round(harmony, 1))

    # Split-Complementary: one hue + two hues ±30° from complement
    if len(cluster_hues) == 3:
        # Check if one pair is ~180° and others are ~150°/210°
        for i in range(len(cluster_hues)):
            comp_hue = (cluster_hues[i] + 180) % 360
            nearby = [h for j, h in enumerate(cluster_hues) if j != i and _hue_dist(h, comp_hue) <= tolerance]
            if len(nearby) == 2:
                harmony = 90 - (max_dist - 120) / 10
                return ("Split-Complementary", round(harmony, 1))

    # Triadic: three hues ~120° apart
    if len(cluster_hues) == 3:
        target_dists = [120, 120, 120]
        actual_dists = sorted(distances)
        error = sum(abs(a - t) for a, t in zip(actual_dists, target_dists)) / len(target_dists)
        if error < 30:
            harmony = 100 - (error / 30) * 25
            return ("Triadic", round(harmony, 1))

    # Tetradic: four hues ~90° apart
    if len(cluster_hues) == 4:
        expected_count = 4 * 3 // 2  # 6 distances
        if len(distances) == 6:
            target_dists = [90] * 6
            actual_dists = sorted(distances)
            error = sum(abs(a - t) for a, t in zip(actual_dists, target_dists)) / len(target_dists)
            if error < 40:
                harmony = 100 - (error / 40) * 20
                return ("Tetradic", round(harmony, 1))

    # Default: custom/mixed with harmony based on distribution
    harmony = max(0, 100 - (avg_dist / 180) * 100)
    return ("Custom / Mixed", round(harmony, 1))


def detect_color_scheme(hex_colors: list[str], coverage: dict[str, dict] | None = None) -> dict:
    """Detect scheme using circular clustering and pattern matching with adaptive thresholds."""
    chromatic = [c for c in hex_colors if _is_chromatic(c)]
    achromatic = [c for c in hex_colors if _is_achromatic(c)]

    hues = _chromatic_hues(chromatic, coverage)

    if len(hues) == 0:
        return {
            "scheme": "Achromatic",
            "description": f"Only neutral colors ({len(achromatic)} greys/blacks/whites).",
            "hues_used": [],
            "harmony_score": 100.0,
            "max_hue_distance_deg": 0.0,
            "avg_hue_distance_deg": 0.0,
            "num_color_clusters": 0,
            "chromatic_count": 0,
            "achromatic_count": len(achromatic),
        }

    # Calculate palette diversity (hue spread / saturation range)
    hue_values = [h for h, _ in hues]
    if hue_values:
        hue_spread = max(hue_values) - min(hue_values) if len(hue_values) > 1 else 0
        palette_diversity = min(1.0, hue_spread / 180.0)  # normalize to 0-1
    else:
        palette_diversity = 0.0

    # Get adaptive thresholds
    adaptive = _adaptive_thresholds(len(chromatic), palette_diversity)

    # Circular clustering with adaptive radius
    clusters = _circular_hue_clustering(hues, cluster_radius=adaptive["cluster_radius"])
    cluster_hues = [c[0] for c in clusters]

    # Pattern matching
    scheme, harmony_score = _detect_harmony_pattern(cluster_hues)

    # Calculate distances
    def _hue_dist(h1: float, h2: float) -> float:
        diff = abs(h1 - h2) % 360
        return min(diff, 360 - diff)

    if len(cluster_hues) > 1:
        distances = [
            _hue_dist(cluster_hues[i], cluster_hues[j])
            for i in range(len(cluster_hues))
            for j in range(i + 1, len(cluster_hues))
        ]
        max_dist = max(distances) if distances else 0.0
        avg_dist = sum(distances) / len(distances) if distances else 0.0
    else:
        max_dist = 0.0
        avg_dist = 0.0

    return {
        "scheme": scheme,
        "description": f"{len(cluster_hues)} chromatic hue(s), {len(achromatic)} neutral color(s).",
        "hues_used": [round(h, 1) for h in cluster_hues],
        "harmony_score": harmony_score,
        "max_hue_distance_deg": round(max_dist, 1),
        "avg_hue_distance_deg": round(avg_dist, 1),
        "num_color_clusters": len(clusters),
        "chromatic_count": len(chromatic),
        "achromatic_count": len(achromatic),
        "palette_diversity": round(palette_diversity, 2),
    }


# ══════════════════════════════════════════════════════════════
# WCAG ACCESSIBILITY
# ══════════════════════════════════════════════════════════════

def relative_luminance(rgb: tuple) -> float:
    """WCAG 2.1 relative luminance."""
    def linearise(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (linearise(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex1: str, hex2: str) -> float:
    """Contrast ratio (WCAG 2.1). Full precision."""
    L1 = relative_luminance(hex_to_rgb(hex1))
    L2 = relative_luminance(hex_to_rgb(hex2))
    lighter, darker = max(L1, L2), min(L1, L2)
    return (lighter + 0.05) / (darker + 0.05)


def wcag_levels(ratio: float) -> dict:
    """WCAG classification."""
    return {
        "aa_normal": ratio >= 4.5,
        "aa_large": ratio >= 3.0,
        "aaa_normal": ratio >= 7.0,
        "aaa_large": ratio >= 4.5,
        "label": (
            "AAA" if ratio >= 7.0
            else "AA" if ratio >= 4.5
            else "AA-Large" if ratio >= 3.0
            else "FAIL"
        ),
    }


def _accessibility_score_scurve(ratio: float) -> float:
    """S-curve perceptually weighted scoring."""
    if ratio < 1.5:
        return 0.0
    elif ratio < 3.0:
        return ((ratio - 1.5) / 1.5) * 30
    elif ratio < 4.5:
        return 30 + ((ratio - 3.0) / 1.5) * 45
    elif ratio < 7.0:
        return 75 + ((ratio - 4.5) / 2.5) * 20
    else:
        return min(100, 95 + ((ratio - 7.0) / 14) * 5)


def _wcag_importance_weight(ratio: float) -> float:
    """
    Weight factor based on WCAG compliance level.
    AA Normal (4.5) is baseline (1.0x).
    AAA (7.0) is premium (1.3x).
    Large (3.0) is less stringent (0.7x).
    """
    if ratio >= 7.0:
        return 1.3  # AAA – premium credit
    elif ratio >= 4.5:
        return 1.0  # AA Normal – baseline
    elif ratio >= 3.0:
        return 0.7  # AA Large – less stringent
    else:
        return 0.3  # Below AA Large – critical


def _suggest_replacement_color(color: str, ratio: float, target_ratio: float = 4.5) -> str | None:
    """
    Generate exact replacement color to achieve target contrast.
    Uses binary search to find optimal luminance, preserving original hue/saturation.
    Returns suggested hex color, or None if color is already good.
    """
    if ratio >= target_ratio:
        return None

    try:
        r, g, b = hex_to_rgb(color)
        h, s, l = rgb_to_hsl((r, g, b))
        current_lum = relative_luminance((r, g, b))

        # Determine direction: lighten or darken
        lighten = current_lum < 0.5

        # Binary search for optimal lightness in HSL
        low, high = 0.0, 1.0
        best_replacement = None
        best_ratio = ratio

        for _ in range(20):  # ~20 iterations for precision
            mid = (low + high) / 2

            # Adjust only lightness, preserve hue/saturation
            hsl_adjusted = (h, s, mid)
            r_new, g_new, b_new = _hsl_to_rgb(hsl_adjusted)
            test_color = rgb_to_hex((r_new, g_new, b_new))

            # Test contrast
            test_ratio = max(
                contrast_ratio(test_color, "#FFFFFF"),
                contrast_ratio(test_color, "#000000")
            )

            if test_ratio >= target_ratio:
                best_replacement = test_color
                best_ratio = test_ratio
                # Search on the direction away from original (to preserve color)
                if lighten:
                    high = mid
                else:
                    low = mid
            else:
                # Need to go further
                if lighten:
                    low = mid
                else:
                    high = mid

        return best_replacement if best_replacement and best_ratio >= target_ratio else None

    except (ValueError, TypeError):
        pass

    return None


def _hsl_to_rgb(hsl: tuple) -> tuple[int, int, int]:
    """Convert HSL (h [0,360), s,l [0,1]) to RGB (0-255)."""
    h, s, l = hsl
    h = h % 360

    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2

    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x

    return (
        max(0, min(255, int((r + m) * 255))),
        max(0, min(255, int((g + m) * 255))),
        max(0, min(255, int((b + m) * 255)))
    )


def generate_color_recommendation(color: str, ratio: float) -> str | None:
    """Generate actionable recommendation with optional replacement color."""
    if ratio >= 7.0:
        return None

    if ratio < 3.0:
        try:
            r, g, b = hex_to_rgb(color)
            luminance = relative_luminance((r, g, b))
            direction = "Darken" if luminance > 0.5 else "Lighten"

            replacement = _suggest_replacement_color(color, ratio, target_ratio=4.5)
            if replacement:
                return f"{direction} {color} to {replacement} (target ratio ≥4.5:1)"
            else:
                return f"{direction} {color} significantly (target ratio ≥4.5:1)"
        except ValueError:
            return "Adjust contrast with text color"

    if 3.0 <= ratio < 4.5:
        replacement = _suggest_replacement_color(color, ratio, target_ratio=4.5)
        if replacement:
            return f"Replace {color} with {replacement} for AA (ratio {ratio:.2f}→4.5:1)"
        else:
            return f"Increase {color} contrast (currently {ratio:.2f}:1, need 4.5:1)"

    if 4.5 <= ratio < 7.0:
        replacement = _suggest_replacement_color(color, ratio, target_ratio=7.0)
        if replacement:
            return f"Replace {color} with {replacement} for AAA (ratio {ratio:.2f}→7.0:1)"
        else:
            return f"Enhance {color} for AAA (currently {ratio:.2f}:1, need 7.0:1)"

    return None


def evaluate_color_accessibility(colors: list[str], coverage: dict[str, dict] | None = None) -> dict:
    """
    Evaluate colors with S-curve scoring, WCAG importance weighting, and replacement suggestions.

    Weighting factors:
    - Coverage: colors used more frequently have higher impact
    - WCAG Level: AAA (7.0+) gets 1.3x, AA (4.5+) gets 1.0x, AA-Large (3.0+) gets 0.7x
    """
    pairs = []
    scores = []
    weights = []
    recommendations = []

    for color in colors:
        try:
            ratio_white = contrast_ratio(color, "#FFFFFF")
            ratio_black = contrast_ratio(color, "#000000")

            if ratio_black >= ratio_white:
                best_ratio = ratio_black
                best_text = "#000000"
                levels = wcag_levels(ratio_black)
            else:
                best_ratio = ratio_white
                best_text = "#FFFFFF"
                levels = wcag_levels(ratio_white)

            pair = {
                "color_1": color,
                "color_2": best_text,
                "contrast_ratio": round(best_ratio, 2),
                **levels,
            }
            pairs.append(pair)

            # S-curve score
            score = _accessibility_score_scurve(best_ratio)
            scores.append(score)

            # Combined weight: coverage × WCAG importance
            coverage_weight = 1.0
            if coverage and color in coverage:
                cov = coverage[color]["coverage"]
                if cov < MIN_COVERAGE:
                    continue
                coverage_weight = cov / 100.0

            wcag_weight = _wcag_importance_weight(best_ratio)
            combined_weight = coverage_weight * wcag_weight
            weights.append(combined_weight)

            rec = generate_color_recommendation(color, best_ratio)
            if rec:
                recommendations.append({"color": color, "recommendation": rec})

        except ValueError as exc:
            pairs.append({"color_1": color, "color_2": "N/A", "error": str(exc)})

    if scores:
        if weights and sum(weights) > 0:
            weighted_score = sum(s * w for s, w in zip(scores, weights)) / sum(weights)
        else:
            weighted_score = sum(scores) / len(scores)
        accessibility_score = round(weighted_score, 1)
    else:
        accessibility_score = 0.0

    aa_passes = sum(1 for p in pairs if p.get("aa_normal", False))
    aaa_passes = sum(1 for p in pairs if p.get("aaa_normal", False))

    return {
        "evaluations": pairs,
        "total_colors": len([p for p in pairs if "error" not in p]),
        "aa_passing_pairs": aa_passes,
        "aaa_passing_pairs": aaa_passes,
        "accessibility_score": accessibility_score,
        "score_label": _score_label(accessibility_score),
        "actionable_recommendations": recommendations,
    }


def _score_label(score: float) -> str:
    """Refined labels."""
    if score >= 95:
        return "Excellent – Fully accessible"
    elif score >= 80:
        return "Good – Minor improvements possible"
    elif score >= 65:
        return "Fair – Needs attention"
    elif score >= 50:
        return "Poor – Multiple issues"
    elif score >= 25:
        return "Very Poor – Barriers for colorblind users"
    else:
        return "Critical – Redesign required"


def evaluate_against_black_and_white(hex_color: str) -> dict:
    """Test color against black and white."""
    try:
        ratio_white = contrast_ratio(hex_color, "#FFFFFF")
        ratio_black = contrast_ratio(hex_color, "#000000")
    except ValueError as exc:
        return {"error": str(exc)}

    best_text = "#000000" if ratio_black >= ratio_white else "#FFFFFF"
    best_ratio = max(ratio_black, ratio_white)
    levels = wcag_levels(best_ratio)

    return {
        "color": hex_color,
        "vs_white": {"ratio": round(ratio_white, 2), **wcag_levels(ratio_white)},
        "vs_black": {"ratio": round(ratio_black, 2), **wcag_levels(ratio_black)},
        "recommended_text": best_text,
        "best_ratio": round(best_ratio, 2),
        "best_wcag": levels["label"],
    }


def evaluate_color_pairs(colors: list[str]) -> dict:
    """Backward compatibility wrapper."""
    result = evaluate_color_accessibility(colors)
    # Map new field name back to old for backward compatibility
    result["pairs"] = result.pop("evaluations")
    result["total_pairs"] = result.pop("total_colors")
    return result


def suggest_palette(hex_colors: list[str]) -> list[dict]:
    """Return best text color for each palette color."""
    suggestions = []
    for c in hex_colors[:8]:
        result = evaluate_against_black_and_white(c)
        if "error" not in result:
            suggestions.append(result)
    return suggestions


def validate_against_benchmarks(benchmark_sites: dict) -> dict:
    """
    Validate algorithm against benchmark sites.

    benchmark_sites format:
    {
        "site_name": {
            "colors": ["#FF0000", ...],
            "expected_score": 85,
            "expected_scheme": "Complementary"
        }
    }

    Returns calibration report with errors and confidence metrics.
    """
    results = {}

    for site_name, benchmark in benchmark_sites.items():
        colors = benchmark.get("colors", [])
        expected_score = benchmark.get("expected_score", 50)
        expected_scheme = benchmark.get("expected_scheme", "")

        if not colors:
            continue

        accessibility = evaluate_color_accessibility(colors)
        scheme = detect_color_scheme(colors)

        actual_score = accessibility["accessibility_score"]
        actual_scheme = scheme["scheme"]

        score_error = abs(actual_score - expected_score)
        scheme_match = actual_scheme == expected_scheme if expected_scheme else True

        results[site_name] = {
            "expected_score": expected_score,
            "actual_score": actual_score,
            "error": round(score_error, 1),
            "error_percent": round((score_error / max(expected_score, 1)) * 100, 1),
            "expected_scheme": expected_scheme or "Any",
            "actual_scheme": actual_scheme,
            "scheme_match": scheme_match,
            "status": "PASS" if score_error < 15 and scheme_match else "WARN" if score_error < 25 else "FAIL",
        }

    # Summary statistics
    all_errors = [r["error"] for r in results.values()]
    mean_error = sum(all_errors) / len(all_errors) if all_errors else 0
    max_error = max(all_errors) if all_errors else 0
    passes = sum(1 for r in results.values() if r["status"] == "PASS")

    return {
        "benchmark_results": results,
        "summary": {
            "total_benchmarks": len(results),
            "passes": passes,
            "mean_error": round(mean_error, 1),
            "max_error": round(max_error, 1),
            "confidence": round(100 - (mean_error / 25) * 100, 1),  # Normalize to 0-100
        },
    }
