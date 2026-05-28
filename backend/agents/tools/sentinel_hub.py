import json
import logging
import os
import time
from datetime import datetime, timedelta

import requests
from sentinelhub import (
    CRS,
    BBox,
    DataCollection,
    SentinelHubCatalog,
    SHConfig,
)

from agents.tools.geojson_utils import extract_geometry

_log = logging.getLogger(__name__)


def sh_request_with_retry(method: str, url: str, max_retries: int = 3, **kwargs):
    """Wrapper for all Sentinel Hub API calls with timeout + retry."""
    kwargs.setdefault("timeout", 60)
    for attempt in range(max_retries):
        try:
            resp = requests.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                _log.warning("SH API timeout (attempt %d/%d), retrying in %ds…", attempt + 1, max_retries, wait)
                time.sleep(wait)
            else:
                raise
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in (429, 503) and attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                _log.warning("SH API rate limit/503 (attempt %d), retrying in %ds…", attempt + 1, wait)
                time.sleep(wait)
            else:
                raise


def _config_cdse() -> SHConfig:
    cfg = SHConfig(use_defaults=True)
    cfg.sh_client_id = os.getenv("SH_CLIENT_ID", "")
    cfg.sh_client_secret = os.getenv("SH_CLIENT_SECRET", "")
    cfg.sh_base_url = "https://sh.dataspace.copernicus.eu"
    cfg.sh_token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    return cfg


def _bbox_from_geojson(aoi_geojson: dict) -> BBox:
    geom = extract_geometry(aoi_geojson)
    coords = geom["coordinates"][0]
    lons = [pt[0] for pt in coords]
    lats = [pt[1] for pt in coords]
    return BBox(bbox=[min(lons), min(lats), max(lons), max(lats)], crs=CRS.WGS84)


def _parse_dt_to_date(dt_str: str) -> str:
    if not dt_str:
        return ""
    return dt_str[:10]


def scene_search_s2_l2a(
    aoi_geojson: dict,
    date_start: str,
    date_end: str,
    max_cloud_pct: float = 20.0,
    limit: int = 12,
    relax_cloud_pcts: list[float] | None = None,
    min_scenes: int = 12,
    search_padding_days: int = 0,
    catalog_limit: int = 200,
) -> str:
    cfg = _config_cdse()
    catalog = SentinelHubCatalog(config=cfg)
    bbox = _bbox_from_geojson(aoi_geojson)

    start_dt = datetime.fromisoformat(date_start)
    end_dt = datetime.fromisoformat(date_end)
    if search_padding_days > 0:
        start_dt = start_dt - timedelta(days=search_padding_days)
        end_dt = end_dt + timedelta(days=search_padding_days)
    time_interval = (start_dt.date().isoformat(), end_dt.date().isoformat())

    if relax_cloud_pcts is None:
        relax_cloud_pcts = [max_cloud_pct, 35.0, 55.0, 75.0, 90.0, 100.0]

    thresholds = []
    for v in relax_cloud_pcts:
        if v is None:
            continue
        v = max(0.0, min(100.0, float(v)))
        if v not in thresholds:
            thresholds.append(v)

    used_threshold = None
    results = []

    for thr in thresholds:
        search_iterator = catalog.search(
            DataCollection.SENTINEL2_L2A,
            bbox=bbox,
            time=time_interval,
            filter=f"eo:cloud_cover < {thr}",
            fields={"include": ["id", "properties.datetime", "properties.eo:cloud_cover"], "exclude": []},
            limit=catalog_limit,
        )
        results = list(search_iterator)
        if len(results) >= min_scenes:
            used_threshold = thr
            break

    if used_threshold is None and thresholds:
        used_threshold = thresholds[-1]

    results.sort(key=lambda x: (x.get("properties", {}) or {}).get("datetime", ""))

    scenes = []
    for item in results[:limit]:
        props = item.get("properties", {}) or {}
        scenes.append({
            "source": "SENTINEL2_L2A_CATALOG",
            "scene_id": item.get("id", ""),
            "date": _parse_dt_to_date(props.get("datetime", "")),
            "cloud_pct": props.get("eo:cloud_cover", None),
        })

    geodata = {
        "selected_scenes": scenes,
        "clipped_assets": [{
            "type": "sentinelhub_processapi_bbox_crop",
            "uri": "sentinelhub://process-api/sentinel-2-l2a",
            "bands": ["B02(Blue)", "B03(Green)", "B04(Red)", "B08(NIR)", "B11(SWIR)"],
            "gsd_m": 10,
        }],
        "notes": (
            f"Catalog search over {time_interval} (user window {date_start}..{date_end}); "
            f"relaxed clouds {thresholds}; used_threshold={used_threshold}; returned={len(scenes)}."
        ),
    }
    return json.dumps(geodata)
