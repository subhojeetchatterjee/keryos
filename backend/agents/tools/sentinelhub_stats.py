import logging

import requests

from agents.tools.api_cache import ttl_cached
from agents.tools.cdse_auth import get_token
from agents.tools.geojson_utils import extract_geometry
from agents.tools.retry import with_retry

_log = logging.getLogger(__name__)

STATS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"

EVALSCRIPT_NDVI_SCL_MASK = r"""
//VERSION=3
function setup() {
  return {
    input: [{ bands: ["B04", "B08", "SCL", "dataMask"] }],
    output: [
      { id: "data", bands: 1, sampleType: "FLOAT32" },
      { id: "dataMask", bands: 1 }
    ]
  };
}
function evaluatePixel(s) {
  let valid = (s.dataMask === 1 && s.SCL !== 8 && s.SCL !== 9 && s.SCL !== 10);
  if (!valid || (s.B08 + s.B04) === 0) { return { data: [0], dataMask: [0] }; }
  let ndvi = (s.B08 - s.B04) / (s.B08 + s.B04);
  return { data: [ndvi], dataMask: [1] };
}
"""

_STATS_PAYLOAD_BASE: dict = {
    "calculations": {"default": {"statistics": {"default": {"percentiles": {"k": [10, 25, 50, 75, 90]}}}}}
}


def _stats_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


@ttl_cached(ttl_seconds=600)
def ndvi_stats_for_day(aoi_geojson: dict, day: str) -> dict:
    """
    NDVI stats (cloud-masked) for one day over the AOI.
    day: 'YYYY-MM-DD'. Uses 20 m/px (Sentinel-2 native resolution).
    """
    token = get_token()
    payload = {
        "input": {
            "bounds": {"geometry": extract_geometry(aoi_geojson)},
            "data": [{"type": "sentinel-2-l2a", "dataFilter": {"mosaickingOrder": "leastCC"}}],
        },
        "aggregation": {
            "timeRange": {"from": f"{day}T00:00:00Z", "to": f"{day}T23:59:59Z"},
            "aggregationInterval": {"of": "P1D"},
            "evalscript": EVALSCRIPT_NDVI_SCL_MASK,
            "resx": 20,
            "resy": 20,
        },
        **_STATS_PAYLOAD_BASE,
    }

    def _post() -> requests.Response:
        return requests.post(STATS_URL, headers=_stats_headers(token), json=payload, timeout=180)

    r = with_retry(_post)
    if r.status_code != 200:
        raise RuntimeError(f"Statistics error {r.status_code}: {r.text}")

    result: dict = r.json()
    _log.debug("Single-day stats: %d intervals returned for %s", len(result.get("data", [])), day)
    return result


@ttl_cached(ttl_seconds=600)
def ndvi_stats_range(aoi_geojson: dict, date_from: str, date_to: str) -> dict:
    """
    NDVI stats (cloud-masked) for each day in the date range.
    Uses 20 m/px (Sentinel-2 native resolution).
    Returns {"error": ..., "status": N} on non-200 (soft fail).
    """
    token = get_token()
    payload = {
        "input": {
            "bounds": {"geometry": extract_geometry(aoi_geojson)},
            "data": [{"type": "sentinel-2-l2a", "dataFilter": {"mosaickingOrder": "leastCC"}}],
        },
        "aggregation": {
            "timeRange": {"from": f"{date_from}T00:00:00Z", "to": f"{date_to}T23:59:59Z"},
            "aggregationInterval": {"of": "P1D"},
            "evalscript": EVALSCRIPT_NDVI_SCL_MASK,
            "resx": 20,
            "resy": 20,
        },
        **_STATS_PAYLOAD_BASE,
    }

    def _post() -> requests.Response:
        return requests.post(STATS_URL, headers=_stats_headers(token), json=payload, timeout=180)

    try:
        r = with_retry(_post)
    except Exception as exc:
        _log.warning("Stats range request failed: %s", exc)
        return {"error": str(exc), "status": 0}

    if r.status_code != 200:
        _log.warning("Stats range non-200: %d", r.status_code)
        return {"error": r.text, "status": r.status_code}

    result: dict = r.json()
    _log.debug(
        "Range stats: %d intervals returned for %s–%s", len(result.get("data", [])), date_from, date_to
    )
    return result
