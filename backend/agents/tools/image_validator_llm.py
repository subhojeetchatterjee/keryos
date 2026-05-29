import json
import logging
import os
import re
import time

import requests

_log = logging.getLogger(__name__)

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_VALIDATOR_PROMPT = """\
You are a Sentinel-2 satellite image quality analyst for crop insurance verification.
Assess this true-colour RGB composite (20 m/pixel) for usability.

INVALID (is_valid: false):
- More than 70% black, uniform grey, or no-data
- Opaque cloud cover obscuring ground in more than 70% of the image
- Scan-line errors, severe banding, or tile artefacts
- Thick haze making surface patterns indistinguishable

VALID (is_valid: true):
- Ground surface clearly visible in at least 40% of the image
- Colour and texture variation present and interpretable
- Sufficient quality for spectral vegetation analysis

In "observed_features", describe specific visual features you actually see — colours,
textures, spatial patterns. Do not write generic statements.

Respond ONLY with valid JSON:
{
  "is_valid": true or false,
  "reason": "brief explanation referencing specific visual features",
  "confidence": 0.0 to 1.0,
  "observed_features": "1-3 sentences describing specific visual features in the image",
  "cloud_fraction_visual": 0.0 to 1.0
}\
"""


def validate_image_with_vertex_ai(image_b64: str, date: str) -> dict:
    """
    Validate a Sentinel-2 image using Gemini REST API (AI Studio key).
    Fails open — always returns a usable dict.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    # Fallback chain — tries each model in order on 429/503
    override = os.environ.get("GEMINI_VALIDATOR_MODEL_ID")
    models = (
        [override]
        if override
        else [
            "gemini-3.1-flash-lite",  # 500 RPD — most headroom
            "gemini-3.5-flash",  # 20 RPD
            "gemini-2.5-flash",  # 20 RPD
            "gemini-3-flash",  # 20 RPD
            "gemini-2.5-flash-lite",  # 20 RPD — last resort
        ]
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"inline_data": {"mime_type": "image/png", "data": image_b64}},
                    {"text": _VALIDATOR_PROMPT},
                ]
            }
        ],
        "generationConfig": {"maxOutputTokens": 300, "temperature": 0.1},
    }

    try:
        r = None
        for model in models:
            url = _GEMINI_URL.format(model=model)
            r = requests.post(url, params={"key": api_key}, json=payload, timeout=60)
            if r.status_code not in (429, 503):
                break
            _log.warning("Gemini validator %d on %s for %s, trying next model", r.status_code, model, date)
            time.sleep(2)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        _log.debug("Gemini validator response for %s: %s", date, text[:120])

        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            result: dict = json.loads(match.group())
            result.setdefault("is_valid", True)
            result.setdefault("reason", "Parsed from validator response")
            result.setdefault("confidence", 0.7)
            result.setdefault("observed_features", "")
            result.setdefault("cloud_fraction_visual", None)
            return result

        _log.warning("Gemini validator response for %s not parseable as JSON", date)

    except Exception as exc:
        _log.warning("Gemini validation error for %s: %s", date, exc)

    return {
        "is_valid": True,
        "reason": "Validation service unavailable — image accepted by default",
        "confidence": 0.5,
        "observed_features": "",
        "cloud_fraction_visual": None,
    }
