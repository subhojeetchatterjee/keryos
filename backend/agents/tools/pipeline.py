# agents/tools/pipeline.py
from __future__ import annotations

from typing import Any

from agents.tools.best_images import get_best3_truecolor_auto
from agents.tools.sentinelhub_stats import ndvi_stats_for_day


def get_report_bundle(aoi_geojson: dict, date_from: str, date_to: str) -> dict[str, Any]:
    """
    Single backend function that returns everything the UI/agent needs:
    - best date + best truecolor png (b64)
    - 2 alternative images (b64)
    - NDVI stats JSON for the best day (Statistical API)
    """
    images = get_best3_truecolor_auto(aoi_geojson, date_from, date_to)

    best = images[0]
    best_day = best["date"]

    stats = ndvi_stats_for_day(aoi_geojson, best_day)

    return {
        "date_from": date_from,
        "date_to": date_to,
        "best_date": best_day,
        "best_image": best,               # includes png_b64, cloud_score, etc.
        "alternatives": images[1:],        # 2 alternatives
        "ndvi_stats": stats,
    }
