import math


def extract_geometry(aoi_geojson: dict) -> dict:
    """
    Normalize any GeoJSON input to a raw Geometry object.
    Handles: Geometry | Feature | FeatureCollection.
    Safe to call multiple times (idempotent).
    """
    if aoi_geojson is None:
        raise ValueError("AOI is None — draw a polygon on the map first.")

    geo_type = aoi_geojson.get("type", "")

    if geo_type == "FeatureCollection":
        features = aoi_geojson.get("features", [])
        if not features:
            raise ValueError("FeatureCollection has no features — draw a polygon first.")
        geom = features[0].get("geometry")
        if not geom:
            raise ValueError("FeatureCollection first feature has no geometry.")
        return geom

    elif geo_type == "Feature":
        geom = aoi_geojson.get("geometry")
        if not geom:
            raise ValueError("Feature has no geometry.")
        return geom

    elif geo_type in ("Polygon", "MultiPolygon"):
        return aoi_geojson

    elif geo_type in ("Point", "LineString", "MultiLineString", "MultiPoint"):
        raise ValueError(
            f"AOI must be a Polygon or MultiPolygon — got {geo_type!r}. "
            "Please draw a closed polygon on the map."
        )

    else:
        raise ValueError(
            f"Unrecognised GeoJSON type: {geo_type!r}. Expected Polygon, Feature, or FeatureCollection."
        )


def _shoelace_area_deg2(ring: list[list[float]]) -> float:
    """Signed area of a coordinate ring in degrees² using the Shoelace formula."""
    n = len(ring)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += ring[i][0] * ring[j][1]
        area -= ring[j][0] * ring[i][1]
    return abs(area) / 2.0


def estimate_area_km2(geom: dict) -> float:
    """
    Rough AOI area in km² using the Shoelace formula scaled by a mid-latitude factor.
    Accurate to ±5 % for small polygons; good enough for validation.
    """
    coords = geom.get("coordinates", [[]])[0]
    if not coords or len(coords) < 3:
        return 0.0

    lats = [c[1] for c in coords]
    [c[0] for c in coords]
    center_lat = (min(lats) + max(lats)) / 2.0

    area_deg2 = _shoelace_area_deg2(coords)
    km_per_deg_lat = 111.32
    km_per_deg_lon = 111.32 * math.cos(math.radians(center_lat))
    return area_deg2 * km_per_deg_lat * km_per_deg_lon


def validate_aoi(aoi_geojson: dict) -> dict:
    """
    Extract and validate an AOI geometry.

    Raises ValueError with a specific user-facing message if:
    - Coordinates are outside WGS84 bounds
    - AOI is too small (< 0.01 km²) — likely a mis-click
    - AOI is too large (> 50 000 km²) — would exceed API limits

    Returns the raw Geometry dict on success.
    """
    geom = extract_geometry(aoi_geojson)

    # Validate coordinate ranges
    coords = geom.get("coordinates", [[]])
    ring = coords[0] if coords else []
    for pt in ring:
        lon, lat = pt[0], pt[1]
        if not (-180.0 <= lon <= 180.0):
            raise ValueError(
                f"Longitude {lon:.4f} is out of range (−180 … 180). "
                "Re-draw the polygon within valid map bounds."
            )
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(
                f"Latitude {lat:.4f} is out of range (−90 … 90). Re-draw the polygon within valid map bounds."
            )

    # Validate area
    area = estimate_area_km2(geom)
    if area < 0.01:
        raise ValueError(
            f"AOI is too small ({area:.4f} km²). "
            "The polygon must cover at least 0.01 km² (≈ 1 hectare) "
            "for Sentinel-2 to return meaningful data. "
            "Try zooming in and drawing a larger polygon."
        )
    if area > 50_000:
        raise ValueError(
            f"AOI is too large ({area:,.0f} km²). "
            "Please limit your area of interest to 50 000 km² or less "
            "to stay within Sentinel Hub API limits."
        )

    return geom
