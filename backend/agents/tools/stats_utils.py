from typing import Any, cast


def safe_extract_stats(raw: Any) -> dict[Any, Any] | None:
    """Try multiple known response shapes from the Statistics API."""
    if not raw or not isinstance(raw, dict):
        return None
    try:
        result = raw["data"][0]["outputs"]["data"]["bands"]["B0"]["stats"]
        return cast(dict[Any, Any], result)
    except (KeyError, IndexError, TypeError):
        pass
    try:
        result = raw["data"][0]["outputs"]["data"]["bands"]["data"]["stats"]
        return cast(dict[Any, Any], result)
    except (KeyError, IndexError, TypeError):
        pass
    try:
        result = raw["data"][0]["outputs"]["NDVI"]["bands"]["NDVI"]["stats"]
        return cast(dict[Any, Any], result)
    except (KeyError, IndexError, TypeError):
        pass
    try:
        if "mean" in raw:
            return cast(dict[Any, Any], raw)
    except (KeyError, TypeError):
        pass
    try:
        data = raw.get("data", [])
        if data:
            outputs = data[0].get("outputs", {})
            for band_key in outputs:
                bands = outputs[band_key].get("bands", {})
                for b in bands:
                    stats = bands[b].get("stats")
                    if stats:
                        return cast(dict[Any, Any], stats)
    except Exception:
        pass
    return None
