# ============================================================
# color_analysis.py  –  Advanced Color Theory + WCAG Accessibility
#
# Version 5.0 – Intelligent Color Weighting & Analysis
# Improvements:
#   • Color coverage/frequency weighting
#   • Ignore insignificant colors (<5% coverage)
#   • Perceptual (HSL) color similarity
#   • Hue clustering for scheme detection
#   • Enhanced harmony scoring (color theory)
#   • Clearer API field naming
#   • Actionable recommendations
#   • Refined score labels
# ============================================================

from __future__ import annotations
import math


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


# ══════════════════════════════════════════════════════════════
# PERCEPTUAL COLOR DISTANCE (HSL-based)
# ══════════════════════════════════════════════════════════════

def _perceptual_color_distance(hex1: str, hex2: str) -> float:
    """
    Perceptual distance in HSL space (more accurate than RGB).
    Accounts for hue, saturation, lightness weighted by human perception.
    """
    try:
        h1, s1, l1 = rgb_to_hsl(hex_to_rgb(hex1))
        h2, s2, l2 = rgb_to_hsl(hex_to_rgb(hex2))
    except ValueError:
        return float('inf')

    # Hue difference (circular, 0-180)
    hue_diff = abs(h1 - h2) % 360
    if hue_diff > 180:
        hue_diff = 360 - hue_diff

    # Weighted perceptual distance
    # Hue: max 180, Saturation: max 1, Lightness: max 1
    distance = math.sqrt(
        (hue_diff / 180) ** 2 * 0.5 +  # Hue weight: 50%
        ((s1 - s2) ** 2) * 0.25 +       # Saturation weight: 25%
        ((l1 - l2) ** 2) * 0.25         # Lightness weight: 25%
    ) * 100

    return distance


def deduplicate_colors(
    hex_colors: list[str],
    coverage: dict[str, float] | None = None,
    threshold: float = 8.0
) -> list[str]:
    """
    Remove perceptually similar colors.
    If coverage provided, keep highest-coverage color when merging.

    Args:
        hex_colors: List of hex colors
        coverage: Dict mapping hex → percentage (0-100)
        threshold: Perceptual distance threshold
    """
    if not hex_colors:
        return []

    unique = []
    for color in hex_colors:
        is_duplicate = False
        for i, existing in enumerate(unique):
            if _perceptual_color_distance(color, existing) < threshold:
                # If coverage provided, keep the more prevalent color
                if coverage:
                    existing_cov = coverage.get(existing, 0)
                    color_cov = coverage.get(color, 0)
                    if color_cov > existing_cov:
                        unique[i] = color  # Replace with more prevalent
                is_duplicate = True
                break
        if not is_duplicate:
            unique.append(color)

    return unique


# ══════════════════════════════════════════════════════════════
# COLOR THEORY – SCHEME DETECTION WITH CLUSTERING
# ══════════════════════════════════════════════════════════════

def _chromatic_hues(hex_colors: list[str], min_coverage: float = 5.0, coverage: dict[str, float] | None = None) -> list[tuple[float, float]]:
    """
    Extract hues from chromatic colors.
    Returns (hue, coverage_weight) tuples.
    Ignores colors with <min_coverage% (default 5%).
    """
    hues = []
    for c in hex_colors[:12]:
        try:
            h, s, l = rgb_to_hsl(hex_to_rgb(c))
            # Chromatic: saturation > 12%, not extreme lightness
            if s >= 0.12 and 0.12 <= l <= 0.88:
                # Check coverage
                cov_weight = 1.0
                if coverage:
                    cov = coverage.get(c, min_coverage)
                    if cov < min_coverage:
                        continue  # Ignore insignificant colors
                    cov_weight = cov / 100.0

                hues.append((h, cov_weight))
        except ValueError:
            continue
    return hues


def _hue_clustering(hues: list[tuple[float, float]], cluster_radius: float = 25.0) -> list[tuple[float, float]]:
    """
    Group similar hues into clusters. Returns (cluster_center_hue, total_weight).
    """
    if not hues:
        return []

    sorted_hues = sorted(hues, key=lambda x: x[0])
    clusters = []
    current_cluster_hues = [sorted_hues[0][0]]
    current_weight = sorted_hues[0][1]

    for hue, weight in sorted_hues[1:]:
        # Check if hue belongs to current cluster
        min_hue = min(current_cluster_hues)
        max_hue = max(current_cluster_hues)
        hue_range = (max_hue - min_hue) % 360

        if hue_range <= cluster_radius:
            current_cluster_hues.append(hue)
            current_weight += weight
        else:
            # Start new cluster
            cluster_center = sum(current_cluster_hues) / len(current_cluster_hues)
            clusters.append((cluster_center, current_weight))
            current_cluster_hues = [hue]
            current_weight = weight

    # Final cluster
    if current_cluster_hues:
        cluster_center = sum(current_cluster_hues) / len(current_cluster_hues)
        clusters.append((cluster_center, current_weight))

    return clusters


def detect_color_scheme(
    hex_colors: list[str],
    coverage: dict[str, float] | None = None
) -> dict:
    """
    Improved scheme detection using hue clustering and weighted analysis.
    Ignores colors with <5% coverage.
    """
    hues = _chromatic_hues(hex_colors, min_coverage=5.0, coverage=coverage)

    if len(hues) == 0:
        return {
            "scheme": "Achromatic",
            "description": "Only greys, blacks, or whites detected.",
            "hues_used": [],
            "harmony_score": 100.0,
            "max_hue_distance_deg": 0.0,
            "avg_hue_distance_deg": 0.0,
            "num_color_clusters": 0,
        }

    if len(hues) == 1:
        return {
            "scheme": "Monochromatic",
            "description": "A single hue at different lightness/saturation levels.",
            "hues_used": [round(hues[0][0], 1)],
            "harmony_score": 100.0,
            "max_hue_distance_deg": 0.0,
            "avg_hue_distance_deg": 0.0,
            "num_color_clusters": 1,
        }

    # Cluster hues
    clusters = _hue_clustering([(h, w) for h, w in hues])
    cluster_hues = [c[0] for c in clusters]

    # Hue distances
    def _min_dist(h1, h2):
        diff = abs(h1 - h2) % 360
        return min(diff, 360 - diff)

    distances = [
        _min_dist(cluster_hues[i], cluster_hues[j])
        for i in range(len(cluster_hues))
        for j in range(i + 1, len(cluster_hues))
    ]

    if distances:
        max_dist = max(distances)
        avg_dist = sum(distances) / len(distances)
    else:
        max_dist = 0.0
        avg_dist = 0.0

    # Harmony: weighted by cluster balance
    # Penalize unbalanced clusters
    cluster_weights = [c[1] for c in clusters]
    total_weight = sum(cluster_weights)
    weight_variance = sum((w - total_weight / len(cluster_weights)) ** 2 for w in cluster_weights) / len(cluster_weights)
    balance_penalty = min(30, weight_variance * 10)

    harmony_score = round(max(0, 100 - (avg_dist / 180) * 80 - balance_penalty), 1)

    # Scheme classification
    if max_dist < 30:
        scheme = "Monochromatic"
        desc = "Colors share the same hue, varying in lightness/saturation."
    elif max_dist < 60:
        scheme = "Analogous"
        desc = "Adjacent hues on color wheel—harmonious and natural."
    elif 150 <= max_dist <= 210:
        scheme = "Complementary"
        desc = "Opposite hues—high contrast and vibrant."
    elif 120 <= max_dist < 150 and len(cluster_hues) >= 3:
        scheme = "Split-Complementary"
        desc = "Base color paired with two adjacent complement hues."
    elif 100 <= max_dist < 140 and len(cluster_hues) >= 3:
        scheme = "Triadic"
        desc = "Three hues ~120° apart—balanced and colorful."
    elif len(cluster_hues) >= 4 and max_dist >= 80:
        scheme = "Tetradic"
        desc = "Four hues forming two complementary pairs."
    else:
        scheme = "Custom / Mixed"
        desc = "No standard color-theory relationship."

    return {
        "scheme": scheme,
        "description": desc,
        "hues_used": [round(h, 1) for h in cluster_hues],
        "max_hue_distance_deg": round(max_dist, 1),
        "avg_hue_distance_deg": round(avg_dist, 1),
        "harmony_score": harmony_score,
        "num_color_clusters": len(clusters),
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


def _accessibility_score_for_ratio(ratio: float) -> float:
    """Gradual scoring scale."""
    if ratio < 3.0:
        return min(25, (ratio / 3.0) * 25)
    elif ratio < 4.5:
        return 25 + ((ratio - 3.0) / 1.5) * 50
    elif ratio < 7.0:
        return 75 + ((ratio - 4.5) / 2.5) * 20
    else:
        return min(100, 95 + ((ratio - 7.0) / 14) * 5)


def evaluate_color_accessibility(colors: list[str], coverage: dict[str, float] | None = None) -> dict:
    """
    Evaluate each color individually with optional coverage weighting.
    Ignores colors with <5% coverage.
    """
    unique_colors = deduplicate_colors(colors, coverage=coverage, threshold=8.0)

    # Filter by coverage
    if coverage:
        unique_colors = [c for c in unique_colors if coverage.get(c, 5.0) >= 5.0]

    pairs = []
    scores = []
    weights = []

    for color in unique_colors:
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

            score = _accessibility_score_for_ratio(best_ratio)
            scores.append(score)

            # Weight by coverage
            weight = coverage.get(color, 1.0) / 100.0 if coverage else 1.0
            weights.append(weight)

        except ValueError as exc:
            pairs.append({
                "color_1": color,
                "color_2": "N/A",
                "error": str(exc),
            })

    # Weighted average score
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
        "pairs": pairs,
        "total_pairs": len([p for p in pairs if "error" not in p]),
        "aa_passing_pairs": aa_passes,
        "aaa_passing_pairs": aaa_passes,
        "accessibility_score": accessibility_score,
        "score_label": _score_label(accessibility_score),
    }


def _score_label(score: float) -> str:
    """Refined labels with actionability."""
    if score >= 95:
        return "Excellent – Fully accessible to all users"
    elif score >= 80:
        return "Good – Accessible with minor improvements possible"
    elif score >= 65:
        return "Fair – Needs attention for some color pairs"
    elif score >= 50:
        return "Poor – Multiple critical accessibility issues"
    elif score >= 25:
        return "Very Poor – Significant barriers for colorblind users"
    else:
        return "Critical – Unusable for many users; redesign required"


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
    """Backward compatibility."""
    return evaluate_color_accessibility(colors)


def suggest_palette(hex_colors: list[str]) -> list[dict]:
    """Return best text color for each palette color."""
    suggestions = []
    for c in hex_colors[:8]:
        result = evaluate_against_black_and_white(c)
        if "error" not in result:
            suggestions.append(result)
    return suggestions
