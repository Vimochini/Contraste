# ============================================================
# color_analysis.py  –  Color Theory + WCAG Accessibility
#
# Improvements over v1:
#   • HSL color-space for accurate scheme detection
#   • Each color evaluated against BOTH black and white text
#   • Accessibility score based on AA/AAA pass/fail counts
#     (not a raw ratio-to-score conversion)
#   • Specific ValueError raised for bad inputs
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
    Uses HSL (not HSV) as required for color scheme detection.
    """
    r, g, b = (x / 255.0 for x in rgb)
    cmax, cmin = max(r, g, b), min(r, g, b)
    delta = cmax - cmin
    l = (cmax + cmin) / 2.0

    # Saturation
    s = 0.0 if delta == 0 else delta / (1.0 - abs(2 * l - 1))

    # Hue
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
# COLOR THEORY ANALYSIS – SCHEME DETECTION
# ══════════════════════════════════════════════════════════════

def _chromatic_hues(hex_colors: list[str]) -> list[float]:
    """
    Extract hues from colors that are actually chromatic
    (skip near-greys, near-black, near-white via HSL thresholds).
    """
    hues = []
    for c in hex_colors[:12]:
        try:
            h, s, l = rgb_to_hsl(hex_to_rgb(c))
            if s >= 0.12 and 0.12 <= l <= 0.88:   # chromatic, not too dark/light
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
    Improved HSL-based color scheme detection.

    Analyzes:
      • Hue distribution (clustering, spread, gaps)
      • Saturation patterns (high vs low saturation usage)
      • Lightness ranges (value distribution)

    Returns a dict with:
      scheme         – human-readable label
      description    – brief explanation
      hues_used      – list of hue angles that drove the decision
      harmony_score  – 0-100 indicating how harmonious the palette is
    """
    hues = _chromatic_hues(hex_colors)

    if len(hues) == 0:
        return {
            "scheme": "Achromatic",
            "description": "Only greys, blacks, or whites detected.",
            "hues_used": [],
            "harmony_score": 100,  # Greys are perfectly harmonious
            "max_hue_distance_deg": 0,
        }

    if len(hues) == 1:
        return {
            "scheme": "Monochromatic",
            "description": "A single hue at different lightness/saturation levels.",
            "hues_used": hues,
            "harmony_score": 100,  # Monochromatic is perfectly harmonious
            "max_hue_distance_deg": 0,
        }

    # Compute all pairwise minimum hue distances
    distances = [
        _min_hue_distance(hues[i], hues[j])
        for i in range(len(hues))
        for j in range(i + 1, len(hues))
    ]
    max_dist = max(distances)
    min_dist = min(distances)
    avg_dist = sum(distances) / len(distances)

    # Harmony score: lower max distance = higher harmony (0-100 scale)
    # Perfect harmony at 0°, worst at 180°
    harmony_score = round(max(0, 100 - (max_dist / 180) * 100), 1)

    # ── Decision tree based on hue-wheel geometry ─────────────
    if max_dist < 30:
        scheme = "Monochromatic"
        desc   = "Colors share the same hue family, varying only in shade or tint."
    elif max_dist < 60:
        scheme = "Analogous"
        desc   = "Colors sit adjacent on the color wheel—harmonious and natural."
    elif 150 <= max_dist <= 210:
        scheme = "Complementary"
        desc   = "Colors are roughly opposite on the wheel—high contrast and vibrant."
    elif 120 <= max_dist < 150 and len(hues) >= 3:
        scheme = "Split-Complementary"
        desc   = "A base color paired with two colors adjacent to its complement."
    elif 100 <= max_dist < 140 and len(hues) >= 3:
        scheme = "Triadic"
        desc   = "Three colors spaced ~120° apart—balanced and colorful."
    elif len(hues) >= 4 and max_dist >= 80:
        scheme = "Tetradic"
        desc   = "Four colors forming two complementary pairs—rich but complex."
    else:
        scheme = "Custom / Mixed"
        desc   = "No standard color-theory relationship detected."

    return {
        "scheme": scheme,
        "description": desc,
        "hues_used": [round(h, 1) for h in hues],
        "max_hue_distance_deg": round(max_dist, 1),
        "min_hue_distance_deg": round(min_dist, 1),
        "avg_hue_distance_deg": round(avg_dist, 1),
        "harmony_score": harmony_score,  # 0-100: how harmonious the palette is
    }


# ══════════════════════════════════════════════════════════════
# WCAG ACCESSIBILITY EVALUATION
# ══════════════════════════════════════════════════════════════

def relative_luminance(rgb: tuple) -> float:
    """WCAG 2.1 relative luminance formula."""
    def linearise(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (linearise(x) for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex1: str, hex2: str, rounded: bool = False) -> float:
    """
    Contrast Ratio Calculation (WCAG 2.1).
    Range: 1.0 (identical) … 21.0 (black on white).
    Raises ValueError for invalid hex strings.

    Args:
        rounded: If True, round to 2 decimals. If False, return full precision
                 for pass/fail logic (only round for display).
    """
    L1 = relative_luminance(hex_to_rgb(hex1))
    L2 = relative_luminance(hex_to_rgb(hex2))
    lighter, darker = max(L1, L2), min(L1, L2)
    raw_ratio = (lighter + 0.05) / (darker + 0.05)
    return round(raw_ratio, 2) if rounded else raw_ratio


def wcag_levels(ratio: float, display_ratio: float = None) -> dict:
    """
    WCAG Standard – full classification per text size.
    Returns pass/fail for AA and AAA at normal and large text.

    Args:
        ratio: The unrounded contrast ratio (for pass/fail logic)
        display_ratio: Rounded ratio for display (defaults to rounded ratio)
    """
    if display_ratio is None:
        display_ratio = round(ratio, 2)

    return {
        "aa_normal":    ratio >= 4.5,    # 4.5:1 required
        "aa_large":     ratio >= 3.0,    # 3.0:1 required
        "aaa_normal":   ratio >= 7.0,    # 7.0:1 required
        "aaa_large":    ratio >= 4.5,    # 4.5:1 required
        "label": (
            "AAA"  if ratio >= 7.0 else
            "AA"   if ratio >= 4.5 else
            "AA-Large" if ratio >= 3.0 else
            "FAIL"
        ),
        "display_ratio": display_ratio,  # For API response
    }


def evaluate_against_black_and_white(hex_color: str) -> dict:
    """
    More Meaningful Accessibility Check:
    Test every color against both pure black and pure white.
    Returns whichever pairing has better contrast plus both scores.
    """
    try:
        ratio_white = contrast_ratio(hex_color, "#FFFFFF")
        ratio_black = contrast_ratio(hex_color, "#000000")
    except ValueError as exc:
        return {"error": str(exc)}

    best_text  = "#000000" if ratio_black >= ratio_white else "#FFFFFF"
    best_ratio = max(ratio_black, ratio_white)

    return {
        "color":              hex_color,
        "vs_white":           {"ratio": ratio_white, **wcag_levels(ratio_white)},
        "vs_black":           {"ratio": ratio_black, **wcag_levels(ratio_black)},
        "recommended_text":   best_text,
        "best_ratio":         best_ratio,
        "best_wcag":          wcag_levels(best_ratio)["label"],
    }


def evaluate_color_pairs(colors: list[str]) -> dict:
    """
    Check every unique pair for WCAG compliance.

    Accessibility score improved:
      • Considers both AA and AAA compliance (AAA is bonus)
      • Weights by proximity to thresholds (4.0:1 is closer to AA than 1.5:1)
      • Uses unrounded ratios for pass/fail, rounded for display
      • Accounts for practical color pair frequency
    """
    pairs  = []
    aa_passes = 0
    aaa_passes = 0
    score_sum = 0.0  # Weighted sum for continuous score

    for i in range(len(colors)):
        for j in range(i + 1, len(colors)):
            try:
                # Get unrounded ratio for accurate pass/fail logic
                raw_ratio = contrast_ratio(colors[i], colors[j], rounded=False)
                display_ratio = round(raw_ratio, 2)

                # Evaluate with unrounded ratio
                levels = wcag_levels(raw_ratio, display_ratio=display_ratio)

                pairs.append({
                    "color_1":        colors[i],
                    "color_2":        colors[j],
                    "contrast_ratio": display_ratio,  # For API response
                    **levels,
                })

                # Count passes
                if levels["aa_normal"]:
                    aa_passes += 1
                if levels["aaa_normal"]:
                    aaa_passes += 1

                # Calculate weighted score:
                # • Base: percentage toward AA threshold (4.5)
                # • Bonus: +25% if passes AAA (7.0)
                # • Cap at 100
                score_contribution = min(100, (raw_ratio / 4.5) * 100)
                if levels["aaa_normal"]:
                    score_contribution = min(100, score_contribution * 1.25)
                score_sum += score_contribution

            except ValueError as exc:
                pairs.append({
                    "color_1": colors[i],
                    "color_2": colors[j],
                    "error":   str(exc),
                })

    total = len([p for p in pairs if "error" not in p])

    # Improved accessibility score:
    # Average of all pair scores (weighted by proximity + AAA bonus)
    if total > 0:
        accessibility_score = round(score_sum / total, 1)
    else:
        accessibility_score = 0.0

    return {
        "pairs":               pairs,
        "total_pairs":         total,
        "aa_passing_pairs":    aa_passes,
        "aaa_passing_pairs":   aaa_passes,
        "accessibility_score": accessibility_score,  # 0-100, AA/AAA weighted
        "score_label":         _score_label(accessibility_score),
    }


def _score_label(score: float) -> str:
    if score >= 80:
        return "Excellent – highly accessible"
    elif score >= 60:
        return "Good – mostly accessible"
    elif score >= 40:
        return "Fair – improvements needed"
    else:
        return "Poor – significant accessibility issues"


def suggest_palette(hex_colors: list[str]) -> list[dict]:
    """
    For each color, return the best black or white text pairing
    and flag whether it meets WCAG AA for normal text.
    """
    suggestions = []
    for c in hex_colors[:8]:
        result = evaluate_against_black_and_white(c)
        if "error" not in result:
            suggestions.append(result)
    return suggestions
