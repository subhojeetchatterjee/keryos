import json
import logging
import os
import re

import anthropic

_log = logging.getLogger(__name__)

_VALIDATOR_SYSTEM = """\
You are a Sentinel-2 satellite image quality analyst for crop insurance verification.
You assess true-colour RGB composites (bands B04/B03/B02, 20 m/pixel) for usability.

CRITICAL: Base your assessment only on what you actually observe in the image.
Never produce a generic response — describe specific visual features you see.\
"""

_VALIDATOR_PROMPT = """\
Assess this Sentinel-2 true-colour image for crop insurance analysis.

INVALID image criteria (is_valid: false):
- More than 70% of the image is black, uniform grey, or no-data
- Opaque cloud cover obscures ground features in more than 70% of the image
- Scan-line errors, data corruption, severe banding, or tile artefacts
- Thick aerosol or smoke haze making surface patterns indistinguishable

VALID image criteria (is_valid: true):
- Ground surface (soil, vegetation, water, built-up) is clearly visible in at least 40% of the image
- Colour and texture variation is present and interpretable
- Image quality is sufficient for spectral vegetation analysis

REQUIRED: In "observed_features", describe what you actually see in this specific image.
For example: "Predominantly brown-grey bare soil with dark moist patches in the lower third.
Scattered light-green vegetation along field boundaries. Partial cloud obscures the northern edge."
Do not write generic statements — reference actual colours and spatial patterns you observe.

Respond ONLY with valid JSON:
{
  "is_valid": true or false,
  "reason": "brief explanation referencing specific visual features you observed",
  "confidence": 0.0 to 1.0,
  "observed_features": "1-3 sentence description of specific visual features visible in the image",
  "cloud_fraction_visual": 0.0 to 1.0
}\
"""


def _vertex_client() -> anthropic.AnthropicVertex:
    return anthropic.AnthropicVertex(
        region=os.environ.get("CLOUD_ML_REGION", "us-east5"),
        project_id=os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID", ""),
    )


def _validator_model() -> str:
    return os.environ.get("VERTEX_VALIDATOR_MODEL_ID", "claude-3-haiku@20240307")


def validate_image_with_vertex_ai(image_b64: str, date: str) -> dict:
    """
    Validate a Sentinel-2 image for insurance-grade crop analysis.

    Returns:
      is_valid           — bool: image is usable for spectral analysis
      reason             — str: explanation referencing observed visual features
      confidence         — float 0–1: validator confidence in the assessment
      observed_features  — str: description of what is visually present in the image
      cloud_fraction_visual — float|None: estimated visual cloud fraction
    """
    try:
        response = _vertex_client().messages.create(
            model=_validator_model(),
            max_tokens=250,
            system=_VALIDATOR_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
                        },
                        {"type": "text", "text": _VALIDATOR_PROMPT},
                    ],
                }
            ],
        )
        text = response.content[0].text.strip()
        _log.debug("Validator raw response for %s: %s", date, text[:120])

        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            result: dict = json.loads(match.group())
            result.setdefault("is_valid", True)
            result.setdefault("reason", "Parsed from validator response")
            result.setdefault("confidence", 0.7)
            result.setdefault("observed_features", "")
            result.setdefault("cloud_fraction_visual", None)
            return result

        _log.warning("Validator response for %s could not be parsed as JSON", date)
        return {
            "is_valid": True,
            "reason": "Could not parse validator response — defaulting to valid",
            "confidence": 0.5,
            "observed_features": "",
            "cloud_fraction_visual": None,
        }

    except Exception as exc:
        _log.warning("Vertex AI validation error for %s: %s", date, exc)
        return {
            "is_valid": True,
            "reason": f"Validation service unavailable ({exc}) — image accepted by default",
            "confidence": 0.5,
            "observed_features": "",
            "cloud_fraction_visual": None,
        }
