import logging

import requests

from agents.tools.cdse_auth import get_token
from agents.tools.geojson_utils import extract_geometry
from agents.tools.retry import with_retry

_log = logging.getLogger(__name__)

PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"


def _post_process(payload: dict) -> bytes:
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}

    def _post() -> requests.Response:
        r = requests.post(PROCESS_URL, headers=headers, json=payload, timeout=120)
        r.raise_for_status()
        return r

    resp = with_retry(_post)
    return resp.content


def process_png_truecolor(
    aoi_geojson: dict,
    date_from: str,
    date_to: str,
    size_px: int = 512,
    max_cloud_coverage: int | None = 90,
) -> bytes:
    evalscript = """
//VERSION=3
function setup() {
  return { input: ["B02","B03","B04","dataMask"], output: { bands: 4 } };
}
function clip(x) { return Math.max(0, Math.min(1, x)); }
function evaluatePixel(s) {
  if (s.dataMask === 0) return [0,0,0,0];
  return [clip(4.5*s.B04), clip(4.5*s.B03), clip(4.5*s.B02), 1];
}
"""
    data_filter: dict = {
        "timeRange": {"from": f"{date_from}T00:00:00Z", "to": f"{date_to}T23:59:59Z"},
        "mosaickingOrder": "leastCC",
    }
    if max_cloud_coverage is not None:
        data_filter["maxCloudCoverage"] = int(max_cloud_coverage)

    payload = {
        "input": {
            "bounds": {"geometry": extract_geometry(aoi_geojson)},
            "data": [{"type": "sentinel-2-l2a", "dataFilter": data_filter}],
        },
        "output": {
            "width": int(size_px),
            "height": int(size_px),
            "responses": [{"identifier": "default", "format": {"type": "image/png"}}],
        },
        "evalscript": evalscript,
    }
    _log.debug("Fetching truecolor PNG %s–%s size=%d", date_from, date_to, size_px)
    return _post_process(payload)


def process_png_scl(
    aoi_geojson: dict,
    date_from: str,
    date_to: str,
    size_px: int = 128,
    max_cloud_coverage: int | None = 90,
) -> bytes:
    evalscript = """
//VERSION=3
function setup() {
  return { input: ["SCL", "dataMask"], output: { bands: 2 } };
}
function evaluatePixel(s) {
  if (s.dataMask === 0) return [0, 0];
  return [s.SCL / 11.0, 1];
}
"""
    data_filter: dict = {
        "timeRange": {"from": f"{date_from}T00:00:00Z", "to": f"{date_to}T23:59:59Z"},
        "mosaickingOrder": "leastCC",
    }
    if max_cloud_coverage is not None:
        data_filter["maxCloudCoverage"] = int(max_cloud_coverage)

    payload = {
        "input": {
            "bounds": {"geometry": extract_geometry(aoi_geojson)},
            "data": [{"type": "sentinel-2-l2a", "dataFilter": data_filter}],
        },
        "output": {
            "width": int(size_px),
            "height": int(size_px),
            "responses": [{"identifier": "default", "format": {"type": "image/png"}}],
        },
        "evalscript": evalscript,
    }
    return _post_process(payload)


def process_png_ndvi(
    aoi_geojson: dict,
    date_from: str,
    date_to: str,
    size_px: int = 512,
) -> bytes:
    evalscript = """
//VERSION=3
function setup() {
  return { input: ["B04","B08","dataMask"], output: { bands: 4 } };
}
function evaluatePixel(s) {
  if (s.dataMask === 0) return [0,0,0,0];
  let ndvi = (s.B08 - s.B04) / (s.B08 + s.B04);
  let v = (ndvi + 1) / 2;
  return [v, v, v, 1];
}
"""
    payload = {
        "input": {
            "bounds": {"geometry": extract_geometry(aoi_geojson)},
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {"from": f"{date_from}T00:00:00Z", "to": f"{date_to}T23:59:59Z"},
                    "mosaickingOrder": "leastCC",
                    "maxCloudCoverage": 90,
                },
            }],
        },
        "output": {
            "width": int(size_px),
            "height": int(size_px),
            "responses": [{"identifier": "default", "format": {"type": "image/png"}}],
        },
        "evalscript": evalscript,
    }
    return _post_process(payload)


def process_png_false_color_swir(
    aoi_geojson: dict,
    date_from: str,
    date_to: str,
    size_px: int = 512,
    max_cloud_coverage: int | None = 90,
) -> bytes:
    evalscript = """
//VERSION=3
function setup() {
  return { input: ["B11", "B08", "B04", "dataMask"], output: { bands: 4 } };
}
function clip(x) { return Math.max(0, Math.min(1, x)); }
function evaluatePixel(s) {
  if (s.dataMask === 0) return [0,0,0,0];
  return [clip(2.5*s.B11), clip(2.0*s.B08), clip(2.5*s.B04), 1];
}
"""
    data_filter: dict = {
        "timeRange": {"from": f"{date_from}T00:00:00Z", "to": f"{date_to}T23:59:59Z"},
        "mosaickingOrder": "leastCC",
    }
    if max_cloud_coverage is not None:
        data_filter["maxCloudCoverage"] = int(max_cloud_coverage)

    payload = {
        "input": {
            "bounds": {"geometry": extract_geometry(aoi_geojson)},
            "data": [{"type": "sentinel-2-l2a", "dataFilter": data_filter}],
        },
        "output": {
            "width": int(size_px),
            "height": int(size_px),
            "responses": [{"identifier": "default", "format": {"type": "image/png"}}],
        },
        "evalscript": evalscript,
    }
    _log.debug("Fetching SWIR PNG %s–%s size=%d", date_from, date_to, size_px)
    return _post_process(payload)
