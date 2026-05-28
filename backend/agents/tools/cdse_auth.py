import logging
import os
import time

import requests

from agents.tools.retry import with_retry

_log = logging.getLogger(__name__)

_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
_CACHE: dict[str, object] = {"token": None, "exp": 0}


def get_token(max_retries: int = 3) -> str:
    now = int(time.time())
    cached_token = _CACHE.get("token")
    cached_exp = _CACHE.get("exp", 0)
    if cached_token and now < int(float(cached_exp)) - 30:
        return str(cached_token)

    client_id = os.environ.get("SH_CLIENT_ID", "")
    client_secret = os.environ.get("SH_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise OSError("SH_CLIENT_ID and SH_CLIENT_SECRET must be set to authenticate with Sentinel Hub.")

    payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }

    def _do_request() -> requests.Response:
        return requests.post(
            _TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=payload,
            timeout=60,
        )

    try:
        r = with_retry(_do_request, max_retries=max_retries)
        r.raise_for_status()
        j = r.json()
        _CACHE["token"] = j["access_token"]
        _CACHE["exp"] = now + int(j.get("expires_in", 600))
        _log.debug(f"Acquired new Sentinel Hub token (expires in {j.get('expires_in', 600)}s)")
        return str(_CACHE["token"])
    except requests.exceptions.Timeout as err:
        raise RuntimeError(
            "Sentinel Hub authentication timed out after multiple attempts. "
            "Check your internet connection or try again in a moment."
        ) from err
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Sentinel Hub authentication failed: {exc}") from exc
