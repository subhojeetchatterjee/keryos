"""
Satellite image selection pipeline for Sentinel-2 L2A scenes.

Two-phase parallel pipeline:
  Phase 1 — SCL probe: fetch low-res SCL thumbnails in parallel, compute cloud fraction,
             sort candidates by cloud score.
  Phase 2 — Full fetch: for the top-N probed candidates, fetch full-resolution
             true-colour + SWIR PNGs in parallel.  Each scene is evaluated through
             a quality scoring pipeline (brightness gate → image quality analysis →
             composite scoring → optional LLM validation).  Scenes are ranked by
             composite_score and the best 3 are returned.

Public API:
  is_image_valid()         — unchanged brightness gate (backward compatible)
  get_best3_truecolor_auto() — unchanged signature, richer returned scene dicts
"""

import base64
import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import numpy as np
from PIL import Image

from agents.tools.image_score import (
    analyse_truecolor_quality,
    cloud_fraction_from_scl_png,
    score_scene_quality,
)
from agents.tools.sentinelhub_catalog import find_candidates_s2l2a
from agents.tools.sentinelhub_process import (
    process_png_false_color_swir,
    process_png_scl,
    process_png_truecolor,
)

_log = logging.getLogger(__name__)


# ── Public helpers ─────────────────────────────────────────────────────────────


def is_image_valid(png_bytes: bytes, min_brightness: float = 10.0) -> bool:
    """
    Return False if the image is mostly black / empty (mean luminance below threshold).
    Used as a fast early-exit gate before the heavier quality analysis.
    """
    try:
        img = Image.open(io.BytesIO(png_bytes))
        arr = np.array(img.convert("L"))
        valid = float(arr.mean()) >= min_brightness
        del arr
        return valid
    except Exception:
        return False


# ── Internal pipeline stages ───────────────────────────────────────────────────


def _probe_candidate(
    aoi_geojson: dict,
    candidate: dict,
    probe_px: int,
    max_cloud: int,
) -> dict:
    """
    Phase 1: fetch a low-resolution SCL thumbnail and compute cloud fraction.
    Cheap — no full image download, no quality analysis.
    """
    dt = candidate["date"]
    scl_png = process_png_scl(aoi_geojson, dt, dt, size_px=probe_px, max_cloud_coverage=max_cloud)
    cloud_score = cloud_fraction_from_scl_png(scl_png)
    return {
        "date": dt,
        "cloud_cover": candidate.get("cloud_cover"),
        "cloud_score": cloud_score,
    }


def _fetch_full_scene(
    aoi_geojson: dict,
    item: dict,
    full_px: int,
    max_cloud: int,
    llm_validator: Any | None,
) -> dict | None:
    """
    Phase 2: fetch full-resolution true-colour + SWIR for one candidate.

    Quality pipeline:
      1. Brightness gate  — fast discard of black/no-data images
      2. Truecolor analysis — mean brightness, contrast, dark/sat fractions,
                              vegetation proxy, spatial entropy
      3. Composite scoring — cloud clarity (40%), contrast (25%),
                             brightness (15%), vegetation (20%)
      4. Hard-reject check — discard scenes that fail minimum quality thresholds
      5. LLM validation    — optional Vertex AI image check (only on passing scenes)
      6. SWIR fetch        — only for scenes that passed all gates

    Returns a scene dict with a `quality` key, or None if the scene is rejected.
    """
    dt = item["date"]
    try:
        # ── Step 1: fetch truecolor ───────────────────────────────────────────
        full_png = process_png_truecolor(aoi_geojson, dt, dt, size_px=full_px, max_cloud_coverage=max_cloud)

        # ── Step 2: fast brightness gate (keep existing threshold) ────────────
        if not is_image_valid(full_png, min_brightness=10.0):
            _log.info("Skipping %s: brightness gate failed", dt)
            return None

        # ── Step 3: detailed quality analysis ────────────────────────────────
        img_quality = analyse_truecolor_quality(full_png)
        scene_quality = score_scene_quality(item["cloud_score"], img_quality)

        if not scene_quality["usable"]:
            _log.info(
                "Skipping %s: quality rejection — %s",
                dt,
                scene_quality["rejection_reason"],
            )
            return None

        _log.debug(
            "Scene %s quality: grade=%s composite=%.2f  cloud=%.0f%%  "
            "brightness=%.0f  contrast=%.1f  veg=%.0f%%",
            dt,
            scene_quality["quality_grade"],
            scene_quality["composite_score"],
            (1.0 - scene_quality["cloud_clarity"]) * 100,
            img_quality["mean_brightness"],
            img_quality["contrast"],
            img_quality["veg_fraction"] * 100,
        )

        png_b64 = base64.b64encode(full_png).decode("ascii")
        del full_png

        # ── Step 4: optional LLM validation (only on quality-passing scenes) ──
        llm_check: dict[str, Any] = {
            "is_valid": True,
            "reason": "LLM validation disabled",
            "confidence": 1.0,
            "observed_features": "",
            "cloud_fraction_visual": None,
        }
        if llm_validator is not None:
            llm_check = llm_validator(png_b64, dt)
            if not llm_check.get("is_valid", True):
                _log.info("Skipping %s (LLM): %s", dt, llm_check.get("reason", ""))
                return None

        # ── Step 5: fetch SWIR (only for accepted scenes) ─────────────────────
        swir_png = process_png_false_color_swir(
            aoi_geojson, dt, dt, size_px=full_px, max_cloud_coverage=max_cloud
        )
        swir_b64 = base64.b64encode(swir_png).decode("ascii")
        del swir_png

        # Merge image_quality + scene_quality into a single quality dict
        quality: dict[str, Any] = {**img_quality, **scene_quality}

        return {
            "date": dt,
            "cloud_cover": item["cloud_cover"],
            "cloud_score": item["cloud_score"],
            "png_b64": png_b64,
            "swir_png_b64": swir_b64,
            "llm_validation": llm_check,
            "quality": quality,
        }

    except Exception as exc:
        _log.warning("Skipping %s: %s", dt, exc)
        return None


# ── Public entry point ─────────────────────────────────────────────────────────


def get_best3_truecolor_auto(
    aoi_geojson: dict,
    date_from: str,
    date_to: str,
    *,
    max_cloud: int = 90,
    catalog_limit: int = 100,
    probe_px: int = 128,
    full_px: int = 512,
    probe_top_n: int = 12,
    enable_llm_validation: bool = False,
) -> list[dict]:
    """
    Select up to 3 scenes ranked by composite quality score.

    Phase 1 — parallel SCL probe:
      Fetch low-res SCL thumbnails for the top probe_top_n catalog candidates.
      Sort by cloud fraction ascending (cloud-clear first).

    Phase 2 — parallel full-res fetch:
      Fetch full-resolution true-colour + SWIR for the top fetch_n probed scenes.
      Each scene passes through the quality pipeline; scenes are ranked by
      composite_score (cloud clarity 40% + contrast 25% + brightness 15%
      + vegetation 20%).

    Returns a list of 1–3 scene dicts, best first.  Each dict contains:
      date, cloud_cover, cloud_score, png_b64, swir_png_b64, llm_validation,
      quality  (composite_score, quality_grade, brightness, contrast, veg_fraction, …)
    """
    candidates = find_candidates_s2l2a(
        aoi_geojson, date_from, date_to, max_cloud=max_cloud, limit=catalog_limit
    )
    if not candidates:
        raise RuntimeError("No candidates from Catalog API. Widen date range or increase max_cloud.")

    llm_validator = None
    if enable_llm_validation:
        try:
            from agents.tools.image_validator_llm import validate_image_with_vertex_ai

            llm_validator = validate_image_with_vertex_ai
        except ImportError:
            _log.warning("LLM validation not available (missing dependencies)")

    top_candidates = candidates[:probe_top_n]
    probe_workers = min(len(top_candidates), int(os.environ.get("SH_PROBE_WORKERS", "6")))

    # ── Phase 1: parallel SCL probe ───────────────────────────────────────────
    probed: list[dict] = []
    with ThreadPoolExecutor(max_workers=probe_workers) as pool:
        futures = {
            pool.submit(_probe_candidate, aoi_geojson, c, probe_px, max_cloud): c for c in top_candidates
        }
        for future in as_completed(futures):
            try:
                probed.append(future.result())
            except Exception as exc:
                _log.warning("Probe failed for a candidate: %s", exc)

    probed.sort(key=lambda x: x["cloud_score"])
    _log.debug(
        "Phase 1 complete: %d/%d candidates probed, best cloud=%.0f%%",
        len(probed),
        len(top_candidates),
        (probed[0]["cloud_score"] * 100) if probed else 0,
    )

    # ── Phase 2: parallel full-res fetch ──────────────────────────────────────
    # Fetch a few extra candidates to compensate for quality rejections
    fetch_n = min(len(probed), max(6, probe_top_n // 2))
    fetch_workers = min(fetch_n, 4)
    out: list[dict] = []

    with ThreadPoolExecutor(max_workers=fetch_workers) as pool:
        ordered_futures = [
            pool.submit(_fetch_full_scene, aoi_geojson, item, full_px, max_cloud, llm_validator)
            for item in probed[:fetch_n]
        ]
        for future in ordered_futures:
            if len(out) >= 3:
                future.cancel()
                continue
            try:
                result = future.result()
                if result is not None:
                    out.append(result)
            except Exception as exc:
                _log.warning("Full-res fetch error: %s", exc)

    if not out:
        raise RuntimeError(
            "All selected scenes failed quality checks. "
            "Try widening the date range or selecting a different AOI."
        )

    # ── Final ranking: composite_score descending (best scene first) ──────────
    out.sort(
        key=lambda x: x.get("quality", {}).get("composite_score", 0.0),
        reverse=True,
    )
    out = out[:3]

    best = out[0]
    best_q = best.get("quality", {})
    _log.info(
        "Pipeline complete: returning %d scene(s) | best=%s grade=%s "
        "composite=%.2f cloud=%.0f%% brightness=%.0f contrast=%.1f veg=%.0f%%",
        len(out),
        best["date"],
        best_q.get("quality_grade", "?"),
        best_q.get("composite_score", 0.0),
        (1.0 - best_q.get("cloud_clarity", 0.0)) * 100,
        best_q.get("mean_brightness", 0.0),
        best_q.get("contrast", 0.0),
        best_q.get("veg_fraction", 0.0) * 100,
    )
    return out
