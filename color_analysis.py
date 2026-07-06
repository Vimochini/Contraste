# ============================================================
# color_analysis.py  –  Color Theory + WCAG Accessibility
#
# Version 4.0 – Practical Color Evaluation
# Improvements:
#   • Evaluate colors individually (not all pairwise)
#   • Gradual accessibility scoring (not binary pass/fail)
#   • Deduplicate near-identical colors
#   • Full precision for WCAG calculations
#   • Improved color scheme detection with avg hue distance
# ============================================================

from __future__ import annotations


# ══════════════════════════════════════════════════════════════
# COLOR SPACE CONVERSIONS
# ══════════════════════════════════════════════════════════════

def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Parse a #RRGGBB or #RGB string into (R, G, B) 0-255 integers."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = h[0]*2 + h[1]*2 + h[2]*2
    if len(h) != 6:
        raise ValueError(f"Invalid hex color: '{hex_color}'")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_hex(rgb: tuple) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def rgb_to_hsl(rgb: tuple) -> tuple[float, float, float]:
    """
    Convert RGB (0-255) → HSL.
    Returns H in [0, 360), S and L in [0, 1].
    """
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
# COLOR DEDUPLICATION
# ══════════════════════════════════════════════════════════════

def _color_distance(hex1: str, hex2: str) -> float:
    """Euclidean distance in RGB space."""
    r1, g1, b1 = hex_to_rgb(hex1)
    r2, g2, b2 = hex_to_rgb(hex2)
    return ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5


def deduplicate_colors(hex_colors: list[str], threshold: int = 15) -> list[str]:
    """
    Remove near-duplicate colors (e.g., #FFFFFF, #FEFEFE).
    Threshold: RGB distance. 15 = perceptually similar.
    """
    if not hex_colors:
        return []

    unique = []
    for color in hex_colors:
        is_duplicate = any(
            _color_distance(color, existing) < threshold
            for existing in unique
        )
        if not is_duplicate:
            unique.append(color)

    return unique


# ══════════════════════════════════════════════════════════════
# COLOR THEORY – SCHEME DETECTION
# ══════════════════════════════════════════════════════════════

def _chromatic_hues(hex_colors: list[str]) -> list[float]:
    """Extract hues from truly chromatic colors (skip greys/blacks/whites)."""
    hues = []
    for c in hex_colors[:12]:
        try:
            h, s, l = rgb_to_hsl(hex_to_rgb(c))
            if s >= 0.12 and 0.12 <= l <= 0.88:
                hues.append(h)
        except ValueError:
            continue
    return hues


def _min_hue_distance(h1: float, h2: float) -> float:
    """Smallest angular distance on the 360° hue wheel."""
    diff = abs(h1 - h2) % 360
    return min(diff, 360 - diff)


def detect_color_scheme(hex_colors: list[str]) -> dict:
    """
    Improved color scheme detection using average hue distance (not just max).
    Returns harmony_score based on overall hue distribution balance.
    """
    hues = _chromatic_hues(hex_colors)

    if len(hues) == 0:
        return {
            "scheme": "Achromatic",
            "description": "Only greys, blacks, or whites detected.",
            "hues_used": [],
            "harmony_score": 100.0,
            "max_hue_distance_deg": 0.0,
            "avg_hue_distance_deg": 0.0,
        }

    if len(hues) == 1:
        return {
            "scheme": "Monochromatic",
            "description": "A single hue at different lightness/saturation levels.",
            "hues_used": hues,
            "harmony_score": 100.0,
            "max_hue_distance_deg": 0.0,
            "avg_hue_distance_deg": 0.0,
        }

    # Compute hue distances
    distances = [
        _min_hue_distance(hues[i], hues[j])
        for i in range(len(hues))
        for j in range(i + 1, len(hues))
    ]
    max_dist = max(distances)
    avg_dist = sum(distances) / len(distances)

    # Harmony based on average distance (more stable than max)
    harmony_score = round(max(0, 100 - (avg_dist / 180) * 100), 1)

    # Scheme classification
    if max_dist < 30:
        scheme = "Monochromatic"
        desc = "Colors share the same hue family, varying only in shade or tint."
    elif max_dist < 60:
        scheme = "Analogous"
        desc = "Colors sit adjacent on the color wheel—harmonious and natural."
    elif 150 <= max_dist <= 210:
        scheme = "Complementary"
        desc = "Colors are roughly opposite on the wheel—high contrast and vibrant."
    elif 120 <= max_dist < 150 and len(hues) >= 3:
        scheme = "Split-Complementary"
        desc = "A base color paired with two colors adjacent to its complement."
    elif 100 <= max_dist < 140 and len(hues) >= 3:
        scheme = "Triadic"
        desc = "Three colors spaced ~120° apart—balanced and colorful."
    elif len(hues) >= 4 and max_dist >= 80:
        scheme = "Tetradic"
        desc = "Four colors forming two complementary pairs—rich but complex."
    else:
        scheme = "Custom / Mixed"
        desc = "No standard color-theory relationship detected."

    return {
        "scheme": scheme,
        "description": desc,
        "hues_used": [round(h, 1) for h in hues],
        "max_hue_distance_deg": round(max_dist, 1),
        "avg_hue_distance_deg": round(avg_dist, 1),
        "harmony_score": harmony_score,
    }


# ══════════════════════════════════════════════════════════════
# WCAG ACCESSIBILITY (PRACTICAL APPROACH)
# ══════════════════════════════════════════════════════════════

def relative_luminance(rgb: tuple) -> float:
    """WCAG 2.1 relative luminance formula."""
    def linearise(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (linearise(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex1: str, hex2: str) -> float:
    """
    Contrast Ratio (WCAG 2.1).
    Returns full precision (unrounded) for accurate pass/fail logic.
    """
    L1 = relative_luminance(hex_to_rgb(hex1))
    L2 = relative_luminance(hex_to_rgb(hex2))
    lighter, darker = max(L1, L2), min(L1, L2)
    return (lighter + 0.05) / (darker + 0.05)


def wcag_levels(ratio: float) -> dict:
    """
    WCAG classification using unrounded ratio.
    """
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
    """
    Gradual accessibility scoring (not binary).

    Scale:
      < 3.0 → Poor (0-25)
      3.0-4.5 → Moderate (25-75)
      4.5-7.0 → Good (75-95)
      7.0+ → Excellent (95-100)
    """
    if ratio < 3.0:
        return min(25, (ratio / 3.0) * 25)
    elif ratio < 4.5:
        return 25 + ((ratio - 3.0) / 1.5) * 50
    elif ratio < 7.0:
        return 75 + ((ratio - 4.5) / 2.5) * 20
    else:
        return min(100, 95 + ((ratio - 7.0) / 14) * 5)


def evaluate_color_accessibility(colors: list[str]) -> dict:
    """
    NEW: Evaluate each color individually (practical accessibility).

    Instead of comparing all color pairs:
      • Test each color against black and white text
      • Report the better contrast (real-world usage)
      • Score based on continuous scale, not binary pass/fail
    """
    # Deduplicate first
    unique_colors = deduplicate_colors(colors, threshold=15)

    pairs = []
    scores = []

    for color in unique_colors:
        try:
            # Get unrounded ratios
            ratio_white = contrast_ratio(color, "#FFFFFF")
            ratio_black = contrast_ratio(color, "#000000")

            # Best text option
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

            # Score this color
            score = _accessibility_score_for_ratio(best_ratio)
            scores.append(score)

        except ValueError as exc:
            pairs.append({
                "color_1": color,
                "color_2": "N/A",
                "error": str(exc),
            })

    # Overall score: average across all colors
    if scores:
        accessibility_score = round(sum(scores) / len(scores), 1)
    else:
        accessibility_score = 0.0

    # Count passes
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
    """Convert score to human-readable label."""
    if score >= 95:
        return "Excellent – highly accessible"
    elif score >= 75:
        return "Good – mostly accessible"
    elif score >= 50:
        return "Fair – improvements needed"
    elif score >= 25:
        return "Poor – significant accessibility issues"
    else:
        return "Critical – urgent redesign needed"


def evaluate_against_black_and_white(hex_color: str) -> dict:
    """Test a single color against black and white text."""
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
    """Backward compatibility wrapper. Calls improved function."""
    return evaluate_color_accessibility(colors)


def suggest_palette(hex_colors: list[str]) -> list[dict]:
    """Return best text color for each palette color."""
    suggestions = []
    for c in hex_colors[:8]:
        result = evaluate_against_black_and_white(c)
        if "error" not in result:
            suggestions.append(result)
    return suggestions
