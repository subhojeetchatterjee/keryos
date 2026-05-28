import logging

import requests

from agents.tools.api_cache import ttl_cached
from agents.tools.cdse_auth import get_token
from agents.tools.geojson_utils import extract_geometry
from agents.tools.retry import with_retry

_log = logging.getLogger(__name__)

CATALOG_URL = "https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/search"


@ttl_cached(ttl_seconds=300)
def find_candidates_s2l2a(
    aoi_geojson: dict,
    date_from: str,
    date_to: str,
    max_cloud: int = 90,
    limit: int = 100,
) -> list[dict]:
    token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "datetime": f"{date_from}T00:00:00Z/{date_to}T23:59:59Z",
        "collections": ["sentinel-2-l2a"],
        "intersects": extract_geometry(aoi_geojson),
        "limit": int(limit),
        "filter": f"eo:cloud_cover < {int(max_cloud)}",
    }

    def _post() -> requests.Response:
        return requests.post(CATALOG_URL, headers=headers, json=payload, timeout=60)

    r = with_retry(_post)
    if r.status_code != 200:
        raise RuntimeError(f"Catalog error {r.status_code}: {r.text}")

    feats: list[dict] = r.json().get("features", [])
    feats.sort(key=lambda f: (f.get("properties") or {}).get("eo:cloud_cover", 9999))

    out: list[dict] = []
    seen: set[str] = set()
    for f in feats:
        props: dict = f.get("properties") or {}
        day: str = (props.get("datetime") or "")[:10]
        if not day or day in seen or not (date_from <= day <= date_to):
            continue
        seen.add(day)
        out.append({"date": day, "cloud_cover": props.get("eo:cloud_cover")})

    _log.debug("Catalog returned %d unique days for %s–%s", len(out), date_from, date_to)
    return out
