"""
Satellite image scoring and quality analysis for Sentinel-2 L2A scenes.

Two layers:
  1. Cloud fraction from SCL PNG  (used in the lightweight probe phase)
  2. Full image quality analysis  (used after full-res fetch in Phase 2)
"""

from io import BytesIO

import numpy as np
from PIL import Image

# ── SCL cloud classes (probe phase) ───────────────────────────────────────────
# 1=saturated/defective  3=cloud shadow  8=cloud (med)  9=cloud (hi)  10=thin cirrus
CLOUD_SCL = {1, 3, 8, 9, 10}


def cloud_fraction_from_scl_png(png_bytes: bytes) -> float:
    """
    Expects PNG from process_png_scl: red channel stores SCL/11.
    Returns fraction of valid pixels classified as cloud-related.
    """
    img = Image.open(BytesIO(png_bytes)).convert("RGBA")
    px = img.getdata()

    cloudy = 0
    total = 0
    for r, _g, _b, a in px:
        if a == 0:
            continue
        total += 1
        scl = int(round((r / 255.0) * 11))
        if scl in CLOUD_SCL:
            cloudy += 1

    return cloudy / max(total, 1)


# ── Full image quality analysis ────────────────────────────────────────────────


def _empty_quality() -> dict:
    return {
        "mean_brightness": 0.0,
        "contrast": 0.0,
        "dark_fraction": 1.0,
        "saturation_fraction": 0.0,
        "veg_index_mean": 0.0,
        "veg_fraction": 0.0,
        "spatial_entropy": 0.0,
        "valid_fraction": 0.0,
    }


def analyse_truecolor_quality(png_bytes: bytes) -> dict:
    """
    Analyse a Sentinel-2 true-colour RGB PNG for spatial and spectral quality.

    Input: PNG bytes from process_png_truecolor (RGBA, gain-adjusted B04/B03/B02).

    Returns dict:
      mean_brightness    float  0–255   mean luminance of valid pixels
      contrast           float  0–255   luminance std dev (spatial detail indicator)
      dark_fraction      float  0–1     fraction of valid pixels with luminance < 15
                                        (no-data tiles, deep shadow)
      saturation_fraction float  0–1   fraction of valid pixels that are near-white
                                        (cloud, snow, severe haze)
      veg_index_mean     float  −1–1   mean Green-Red Index across non-extreme pixels
                                        GRI = (G−R) / (G+R+1)
      veg_fraction       float  0–1    fraction of analysable pixels with GRI > 0.05
      spatial_entropy    float  0–6    Shannon entropy of the 64-bin luminance histogram
                                        (higher = more spatial detail)
      valid_fraction     float  0–1    fraction of image with non-transparent pixels
    """
    try:
        img = Image.open(BytesIO(png_bytes)).convert("RGBA")
        w, h = img.size
        arr = np.array(img, dtype=np.float32)

        alpha = arr[:, :, 3]
        valid_mask = alpha > 0
        valid_frac = float(valid_mask.sum()) / max(w * h, 1)

        if valid_frac < 0.05:
            return _empty_quality()

        r = arr[:, :, 0]
        g = arr[:, :, 1]
        b = arr[:, :, 2]

        # Luminance (BT.601 luma)
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        lum_valid = lum[valid_mask]

        mean_brightness = float(lum_valid.mean())
        contrast = float(lum_valid.std())

        # Dark fraction: nearly-black pixels (data gaps, heavy cloud shadow)
        dark_frac = float((lum_valid < 15.0).sum()) / max(len(lum_valid), 1)

        # Saturation fraction: near-white with low colour variance (cloud, snow, haze)
        rgb_mean = (r + g + b) / 3.0
        rgb_std = np.sqrt(((r - rgb_mean) ** 2 + (g - rgb_mean) ** 2 + (b - rgb_mean) ** 2) / 3.0)
        sat_mask = (rgb_mean[valid_mask] > 210.0) & (rgb_std[valid_mask] < 25.0)
        sat_frac = float(sat_mask.sum()) / max(len(lum_valid), 1)

        # Vegetation proxy via Green-Red Index
        # Exclude near-dark (no-data) and near-saturated (cloud) pixels from estimation
        analytic_mask = valid_mask & (lum > 15.0) & (lum < 235.0)
        if analytic_mask.sum() > 0:
            r_a = r[analytic_mask]
            g_a = g[analytic_mask]
            gri = (g_a - r_a) / (g_a + r_a + 1.0)
            veg_index_mean = float(gri.mean())
            veg_frac = float((gri > 0.05).sum()) / max(int(analytic_mask.sum()), 1)
        else:
            veg_index_mean = 0.0
            veg_frac = 0.0

        # Shannon entropy of luminance histogram (64 bins)
        hist, _ = np.histogram(lum_valid, bins=64, range=(0.0, 256.0))
        total_hist = int(hist.sum())
        if total_hist > 0:
            p = hist[hist > 0].astype(np.float64) / total_hist
            entropy = float(-np.sum(p * np.log2(p)))
        else:
            entropy = 0.0

        return {
            "mean_brightness": round(mean_brightness, 2),
            "contrast": round(contrast, 2),
            "dark_fraction": round(dark_frac, 4),
            "saturation_fraction": round(sat_frac, 4),
            "veg_index_mean": round(veg_index_mean, 4),
            "veg_fraction": round(veg_frac, 4),
            "spatial_entropy": round(entropy, 4),
            "valid_fraction": round(valid_frac, 4),
        }

    except Exception:
        return _empty_quality()


def score_scene_quality(cloud_fraction: float, image_quality: dict) -> dict:
    """
    Compute a composite scene quality score from SCL cloud fraction and image metrics.

    Scoring weights (sum to 1.0):
      cloud_clarity   40%  — scene usability after cloud masking
      contrast        25%  — spatial detail (texture / field edges)
      brightness      15%  — luminance in the usable range
      vegetation      20%  — estimated vegetation presence

    Hard-reject criteria (composite_score = 0, usable = False):
      cloud_fraction > 0.85   — too cloudy for any analysis
      mean_brightness < 10    — image is essentially black / no-data
      dark_fraction > 0.70    — majority of pixels are no-data or deep shadow
      saturation_fraction > 0.75 — blown-out (cloud top / snow)
      valid_fraction < 0.10   — less than 10% of the image has data

    Quality grades:
      A: composite ≥ 0.75   B: ≥ 0.55   C: ≥ 0.35   D: ≥ 0.20   F: < 0.20

    Returns dict:
      composite_score   float 0–1   primary ranking criterion (higher = better)
      quality_grade     str         A / B / C / D / F
      cloud_clarity     float       1 − cloud_fraction
      brightness_score  float
      contrast_score    float
      vegetation_score  float
      usable            bool
      rejection_reason  str | None
    """
    mb = float(image_quality.get("mean_brightness", 0.0))
    ct = float(image_quality.get("contrast", 0.0))
    dk = float(image_quality.get("dark_fraction", 0.0))
    sat = float(image_quality.get("saturation_fraction", 0.0))
    veg = float(image_quality.get("veg_fraction", 0.0))
    valid = float(image_quality.get("valid_fraction", 0.0))
    cf = float(cloud_fraction)

    # ── Hard rejection ────────────────────────────────────────────────────────
    rejection_reason: str | None = None
    if valid < 0.10:
        rejection_reason = f"Insufficient data ({valid:.0%} valid pixels)"
    elif mb < 10.0:
        rejection_reason = f"Image too dark (brightness {mb:.1f})"
    elif dk > 0.70:
        rejection_reason = f"Excessive no-data pixels ({dk:.0%} dark)"
    elif sat > 0.75:
        rejection_reason = f"Image overexposed/cloud-blown ({sat:.0%} saturated)"
    elif cf > 0.85:
        rejection_reason = f"Excessive cloud cover ({cf:.0%})"

    if rejection_reason:
        return {
            "composite_score": 0.0,
            "quality_grade": "F",
            "cloud_clarity": round(max(0.0, 1.0 - cf), 4),
            "brightness_score": 0.0,
            "contrast_score": 0.0,
            "vegetation_score": 0.0,
            "usable": False,
            "rejection_reason": rejection_reason,
        }

    # ── Normalised component scores (each 0–1) ────────────────────────────────
    cloud_clarity = max(0.0, 1.0 - cf)

    # Brightness: optimal 80–160; penalise very dark and very bright
    if mb < 15.0:
        brightness_score = 0.0
    elif mb < 80.0:
        brightness_score = (mb - 15.0) / 65.0
    elif mb < 160.0:
        brightness_score = 1.0
    elif mb < 230.0:
        brightness_score = 1.0 - (mb - 160.0) / 70.0
    else:
        brightness_score = 0.0

    # Contrast: spatial detail; low = featureless (cloud slab or bare soil)
    # Sweet spot starts at 30; cap at 1.0 above 70
    contrast_score = min(1.0, max(0.0, (ct - 5.0) / 65.0))

    # Vegetation: scale up (healthy agricultural scene often has veg_frac ~ 0.3-0.7)
    vegetation_score = min(1.0, veg * 1.5)

    composite = (
        cloud_clarity * 0.40 + brightness_score * 0.15 + contrast_score * 0.25 + vegetation_score * 0.20
    )
    composite = round(min(1.0, max(0.0, composite)), 4)

    grade = (
        "A"
        if composite >= 0.75
        else "B"
        if composite >= 0.55
        else "C"
        if composite >= 0.35
        else "D"
        if composite >= 0.20
        else "F"
    )

    return {
        "composite_score": composite,
        "quality_grade": grade,
        "cloud_clarity": round(cloud_clarity, 4),
        "brightness_score": round(brightness_score, 4),
        "contrast_score": round(contrast_score, 4),
        "vegetation_score": round(vegetation_score, 4),
        "usable": True,
        "rejection_reason": None,
    }
