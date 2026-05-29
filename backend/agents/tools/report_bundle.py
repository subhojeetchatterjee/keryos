import hashlib
import json
import logging
import math
import os
from datetime import UTC, datetime
from typing import Any, cast

from agents.tools.best_images import get_best3_truecolor_auto
from agents.tools.sentinelhub_stats import ndvi_stats_for_day, ndvi_stats_range
from agents.tools.stats_utils import safe_extract_stats

_log = logging.getLogger(__name__)

_KERYOS_VERSION = "0.1"


# ── Internal helpers ───────────────────────────────────────────────────────────


def _compute_pooled_stats(aggregated_stats: dict) -> dict[Any, Any] | None:
    """
    Weighted mean and pooled stDev across all valid daily intervals.
    Skips intervals where mean is NaN, None, or sampleCount == 0.
    Returns {"mean", "stDev", "passes", "totalPixels"} or None.
    """

    def _extract(interval: dict) -> dict[Any, Any] | None:
        try:
            result = interval["outputs"]["data"]["bands"]["B0"]["stats"]
            return cast(dict[Any, Any], result)
        except (KeyError, TypeError):
            pass
        try:
            for _bk, bv in (interval.get("outputs") or {}).items():
                for _b, sv in (bv.get("bands") or {}).items():
                    stats = sv.get("stats")
                    if stats:
                        return cast(dict[Any, Any], stats)
        except Exception:
            pass
        return None

    w_means: list[tuple[float, float]] = []
    w_vars: list[tuple[float, float]] = []
    for interval in aggregated_stats.get("data", []):
        s = _extract(interval)
        if s is None:
            continue
        try:
            n = float(s.get("sampleCount", 0))
            m_raw = s.get("mean", "nan")
            m = float(m_raw) if m_raw is not None else float("nan")
            if math.isnan(m) or n <= 0:
                continue
            sd_raw = s.get("stDev", s.get("std", 0))
            sd = float(sd_raw) if sd_raw is not None else 0.0
            if math.isnan(sd):
                sd = 0.0
            w_means.append((m, n))
            w_vars.append((sd**2 + m**2, n))
        except (TypeError, ValueError, KeyError):
            continue

    if not w_means:
        return None

    N = sum(n for _, n in w_means)
    wt_mean = sum(m * n for m, n in w_means) / N
    wt_second = sum(v * n for v, n in w_vars) / N
    wt_std = math.sqrt(max(0.0, wt_second - wt_mean**2))
    return {
        "mean": round(wt_mean, 4),
        "stDev": round(wt_std, 4),
        "passes": len(w_means),
        "totalPixels": int(N),
    }


def _aoi_metadata(aoi_geojson: dict, aoi_hash: str) -> dict:
    """Extract area, centroid, and vertex count from an AOI GeoJSON."""
    try:
        from agents.tools.geojson_utils import estimate_area_km2, extract_geometry

        geom = extract_geometry(aoi_geojson)
        area_km2 = estimate_area_km2(geom)
        coords = geom.get("coordinates", [[]])[0]
        vertex_count = max(0, len(coords) - 1)
        lats = [c[1] for c in coords if len(c) >= 2]
        lons = [c[0] for c in coords if len(c) >= 2]
        centroid = {
            "lat": round((min(lats) + max(lats)) / 2, 5),
            "lon": round((min(lons) + max(lons)) / 2, 5),
        }
        return {
            "area_km2": round(area_km2, 4),
            "area_ha": round(area_km2 * 100, 2),
            "vertex_count": vertex_count,
            "centroid": centroid,
            "aoi_hash": aoi_hash,
        }
    except Exception as exc:
        _log.debug("AOI metadata extraction failed: %s", exc)
        return {
            "area_km2": None,
            "area_ha": None,
            "vertex_count": None,
            "centroid": None,
            "aoi_hash": aoi_hash,
        }


def _interpret_ndvi(mean: float) -> dict:
    """Map a composite NDVI mean to a health label, class, claim signal, and recommendation."""
    if mean >= 0.4:
        return {
            "health_label": "Healthy Vegetation",
            "health_class": "healthy",
            "claim_signal": "Crop emergence evident — active vegetation growth detected in spectral data",
            "recommendation": (
                "Satellite evidence does not support a prevented-sowing claim. "
                "Field verification is recommended to confirm crop status."
            ),
        }
    if mean >= 0.2:
        return {
            "health_label": "Moderate Stress / Sparse Cover",
            "health_class": "moderate",
            "claim_signal": "Borderline vegetation signal — partial or stressed crop cover detected",
            "recommendation": (
                "Inconclusive spectral evidence. Field verification is required to "
                "determine actual sowing outcome before claim adjudication."
            ),
        }
    return {
        "health_label": "Severe Stress / Bare Soil",
        "health_class": "stressed",
        "claim_signal": "No crop emergence detected — bare or heavily stressed land surface",
        "recommendation": (
            "Satellite evidence is consistent with a prevented-sowing scenario. "
            "Claim is supported by spectral analysis subject to field confirmation."
        ),
    }


def _compute_confidence(best: dict, pooled_stats: dict | None, enable_llm: bool) -> dict:
    """
    Compute an overall confidence score from cloud clarity, temporal coverage,
    and optional AI validation.
    """
    cloud_score = best.get("cloud_score", 1.0)
    cloud_clarity = round(max(0.0, 1.0 - cloud_score), 3)

    passes = pooled_stats["passes"] if pooled_stats else 0
    total_pixels = pooled_stats["totalPixels"] if pooled_stats else 0
    temporal_coverage = round(min(1.0, passes / 5.0), 3)

    llm_val = best.get("llm_validation") or {}
    ai_validated: bool | None = llm_val.get("is_valid") if enable_llm else None
    ai_confidence_raw = llm_val.get("confidence") if enable_llm else None
    ai_confidence = round(float(ai_confidence_raw), 3) if ai_confidence_raw is not None else None

    overall = cloud_clarity * 0.55 + temporal_coverage * 0.35
    if ai_validated is not None:
        overall = overall * 0.9 + (0.1 if ai_validated else 0.0)
    overall = round(min(1.0, max(0.0, overall)), 3)

    if overall >= 0.70:
        label = "High"
    elif overall >= 0.40:
        label = "Medium"
    else:
        label = "Low"

    return {
        "overall": overall,
        "label": label,
        "cloud_clarity": cloud_clarity,
        "temporal_coverage": temporal_coverage,
        "passes": passes,
        "total_pixels": total_pixels,
        "ai_validated": ai_validated,
        "ai_confidence": ai_confidence,
    }


# ── Public API ─────────────────────────────────────────────────────────────────


def get_report_bundle_for_ui(
    aoi_geojson: dict,
    date_from: str,
    date_to: str,
    crop_type: str = "paddy",
) -> dict:
    """
    Full pipeline with optional LLM enhancements (feature-flagged).

    Returns a structured report dict containing:
    - All original fields (best_date, best_image, alternatives, ndvi_stats,
      aggregated_stats, pooled_stats, ai_narrative) — unchanged for UI compatibility
    - New structured fields: aoi_metadata, ndvi_interpretation, confidence,
      technical_summary, processing_metadata, generated_at
    """
    enable_llm = os.environ.get("ENABLE_LLM_VALIDATION", "false").lower() == "true"
    enable_narrative = os.environ.get("ENABLE_AI_NARRATIVE", "false").lower() == "true"

    generated_at = datetime.now(UTC).isoformat()
    aoi_hash = hashlib.md5(json.dumps(aoi_geojson, sort_keys=True).encode()).hexdigest()[:8]
    _log.info(
        "Pipeline start | AOI hash=%s date=%s–%s crop=%s llm=%s narrative=%s",
        aoi_hash,
        date_from,
        date_to,
        crop_type,
        enable_llm,
        enable_narrative,
    )

    # ── 1. Scene discovery & image ranking ────────────────────────────────────
    images = get_best3_truecolor_auto(
        aoi_geojson=aoi_geojson,
        date_from=date_from,
        date_to=date_to,
        max_cloud=90,
        catalog_limit=100,
        probe_px=128,
        full_px=512,
        probe_top_n=12,
        enable_llm_validation=enable_llm,
    )

    if not images:
        raise RuntimeError("No satellite scenes found. Widen date range or increase cloud tolerance.")

    best = images[0]
    _log.info("Best scene: %s cloud_score=%.1f%%", best["date"], best["cloud_score"] * 100)

    # ── 2. NDVI computation ────────────────────────────────────────────────────
    aggregated_stats = ndvi_stats_range(aoi_geojson, date_from, date_to)

    stats: dict | None = None
    for interval_data in aggregated_stats.get("data", []):
        if interval_data.get("interval", {}).get("from", "").startswith(best["date"]):
            stats = {"data": [interval_data], "status": "OK"}
            break
    if stats is None:
        _log.debug("Best date %s not in aggregated range; fetching per-day stats", best["date"])
        stats = ndvi_stats_for_day(aoi_geojson, best["date"])

    # ── 3. Report assembly — compute all deterministic fields first ───────────
    pooled_stats = _compute_pooled_stats(aggregated_stats)
    _log.info("Pooled stats: %s", pooled_stats)

    aoi_meta = _aoi_metadata(aoi_geojson, aoi_hash)
    acquisition_dates = [img["date"] for img in images]

    ndvi_interp: dict = {}
    if pooled_stats and pooled_stats.get("mean") is not None:
        ndvi_interp = _interpret_ndvi(pooled_stats["mean"])
    elif (sd := safe_extract_stats(stats)) and sd.get("mean") is not None:
        ndvi_interp = _interpret_ndvi(float(sd["mean"]))

    confidence = _compute_confidence(best, pooled_stats, enable_llm)

    # ── 4. AI narrative (optional) — called last so it has full context ───────
    ai_assessment: dict = {}
    ai_narrative = ""
    if enable_narrative:
        try:
            from agents.tools.llm_narrative import generate_claim_narrative

            stats_data = safe_extract_stats(stats) or {}
            extra_imgs = [img["png_b64"] for img in images[1:] if img.get("png_b64")]
            ai_assessment = generate_claim_narrative(
                best["png_b64"],
                stats_data,
                best["date"],
                best["cloud_score"],
                extra_images_b64=extra_imgs,
                pooled_stats=pooled_stats,
                ndvi_interpretation=ndvi_interp,
                confidence=confidence,
                aoi_metadata=aoi_meta,
                crop_type=crop_type,
                date_from=date_from,
                date_to=date_to,
                acquisition_dates=acquisition_dates,
                cloud_cover=best.get("cloud_cover"),
                ai_validated=(best.get("llm_validation", {}).get("is_valid") if enable_llm else None),
            )
            ai_narrative = ai_assessment.get("executive_summary", "")
        except Exception as exc:
            _log.warning("Narrative generation failed: %s", exc)

    return {
        # ── Existing fields (UI-compatible, unchanged) ──────────────────────
        "date_from": date_from,
        "date_to": date_to,
        "crop_type": crop_type,
        "best_date": best["date"],
        "best_image": best,
        "alternatives": images[1:] if len(images) > 1 else [],
        "ndvi_stats": stats,
        "aggregated_stats": aggregated_stats,
        "pooled_stats": pooled_stats,
        "ai_narrative": ai_narrative,
        "ai_assessment": ai_assessment,
        # ── New structured fields ────────────────────────────────────────────
        "generated_at": generated_at,
        "aoi_metadata": aoi_meta,
        "acquisition_dates": acquisition_dates,
        "ndvi_interpretation": ndvi_interp,
        "confidence": confidence,
        "technical_summary": {
            "data_source": "Copernicus Sentinel-2 L2A (processed via Sentinel Hub)",
            "statistics_method": "Weighted pooled mean + pooled stDev across all valid daily intervals",
            "spatial_resolution_m": 20,
            "band_formula": "NDVI = (NIR − RED) / (NIR + RED)",
            "cloud_masking": "Scene Classification Layer (SCL) — classes 1,3,8,9,10 excluded",
            "image_validation": "Brightness threshold + optional Gemini (Vertex AI)",
            "scenes_evaluated": len(images),
            "best_scene_cloud_score": round(best["cloud_score"], 4),
            "best_scene_cloud_cover": best.get("cloud_cover"),
        },
        "processing_metadata": {
            "keryos_version": _KERYOS_VERSION,
            "generated_at": generated_at,
            "enable_llm_validation": enable_llm,
            "enable_ai_narrative": enable_narrative,
            "aoi_hash": aoi_hash,
            # ── Reproducibility: all parameters that determine this output ──
            "pipeline_parameters": {
                "catalog_max_cloud_pct": 90,
                "catalog_limit": 100,
                "probe_px": 128,
                "full_px": 512,
                "probe_top_n": 12,
                "ndvi_resx_m": 20,
                "ndvi_resy_m": 20,
                "ndvi_percentiles": [10, 25, 50, 75, 90],
                "probe_workers": int(os.environ.get("SH_PROBE_WORKERS", "6")),
                "full_fetch_workers": 4,
            },
            "quality_thresholds": {
                "min_brightness": 10.0,
                "max_cloud_hard_reject": 0.85,
                "max_dark_fraction": 0.70,
                "max_saturation_fraction": 0.75,
                "min_valid_fraction": 0.10,
            },
            "scoring_weights": {
                "cloud_clarity": 0.40,
                "spatial_contrast": 0.25,
                "brightness": 0.15,
                "vegetation_proxy": 0.20,
            },
            "ndvi_classification": {
                "healthy_threshold": 0.40,
                "moderate_threshold": 0.20,
                "formula": "NDVI = (B08 − B04) / (B08 + B04)",
                "cloud_mask_scl_classes": [1, 3, 8, 9, 10],
                "statistics_api_resolution_m": 20,
            },
            "pipeline_steps": [
                "AOI validation (coordinate bounds + area check)",
                "Scene discovery (Sentinel Hub Catalog API, max_cloud < 90%)",
                "SCL cloud scoring — parallel probe phase (128×128 px, 6 workers)",
                "Sort candidates by cloud_score ascending",
                "Full-resolution truecolour fetch (512×512 px, 4 workers)",
                "Brightness gate (mean luminance ≥ 10)",
                "Image quality analysis (brightness, contrast, saturation, GRI, entropy)",
                "Composite quality scoring (cloud 40% + contrast 25% + brightness 15% + veg 20%)",
                "Hard-reject filter (cloud/dark/sat/nodata thresholds)",
                *(["Gemini image validation (Vertex AI)"] if enable_llm else []),
                "SWIR false-colour fetch (512×512 px)",
                "Sort scenes by composite_score descending",
                "NDVI statistics — daily range (Statistics API, 20 m/px, P1D intervals)",
                "Per-date NDVI extraction for best scene",
                "Pooled composite statistics (weighted mean + pooled stDev)",
                "NDVI health classification (thresholds: 0.40 / 0.20)",
                "Confidence scoring (cloud 55% + temporal 35% + AI 10%)",
                *(["Claude 3.5 Sonnet narrative generation (Vertex AI)"] if enable_narrative else []),
                "Report assembly + metadata embedding",
            ],
        },
    }
