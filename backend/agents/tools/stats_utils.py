def safe_extract_stats(raw: dict) -> dict | None:
    """Try multiple known response shapes from the Statistics API."""
    if not raw or not isinstance(raw, dict):
        return None
    try:
        return raw['data'][0]['outputs']['data']['bands']['B0']['stats']
    except (KeyError, IndexError, TypeError):
        pass
    try:
        return raw['data'][0]['outputs']['data']['bands']['data']['stats']
    except (KeyError, IndexError, TypeError):
        pass
    try:
        return raw['data'][0]['outputs']['NDVI']['bands']['NDVI']['stats']
    except (KeyError, IndexError, TypeError):
        pass
    try:
        if 'mean' in raw:
            return raw
    except (KeyError, TypeError):
        pass
    try:
        data = raw.get('data', [])
        if data:
            outputs = data[0].get('outputs', {})
            for band_key in outputs:
                bands = outputs[band_key].get('bands', {})
                for b in bands:
                    stats = bands[b].get('stats')
                    if stats:
                        return stats
    except Exception:
        pass
    return None
