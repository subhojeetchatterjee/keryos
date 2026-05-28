import json
import logging
import os
import re

import anthropic

_log = logging.getLogger(__name__)

# ── System prompt — defines the AI's role, constraints, and grounding rules ───
_ANALYST_SYSTEM = """\
You are a satellite-based agricultural intelligence analyst specialising in crop insurance verification.
You analyse geospatial and spectral evidence and produce grounded, concise assessments.

NON-NEGOTIABLE RULES:
1. Only make claims directly supported by the numerical metrics in the provided evidence pack.
2. Quote specific NDVI values (e.g. "composite mean NDVI of 0.18") in every section that discusses vegetation.
3. Never speculate about causes (weather, floods, pests) unless explicitly stated in the evidence pack.
4. If data quality is low (high cloud score or few satellite passes), state this as a limitation.
5. The confidence level is pre-computed — explain it; do not recalculate or contradict it.
6. Caveats must be grounded: only list limitations that are directly relevant to the provided data values.
7. Never use weasel language that obscures an evidence-based conclusion.
8. You are a precision analyst — terse, factual, evidence-referenced. Never write like a chatbot.\
"""


def _vertex_client() -> anthropic.AnthropicVertex:
    return anthropic.AnthropicVertex(
        region=os.environ.get("CLOUD_ML_REGION", "us-east5"),
        project_id=os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID", ""),
    )


def _narrative_model() -> str:
    return os.environ.get("VERTEX_NARRATIVE_MODEL_ID", "claude-3-5-sonnet@20241022")


def _fmt(v: object, decimals: int = 3) -> str:
    """Format a numeric value for the evidence block; return 'N/A' if unusable."""
    try:
        return f"{float(v):.{decimals}f}"  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "N/A"


def _build_evidence_block(
    ndvi_stats: dict,
    best_date: str,
    cloud_score: float,
    cloud_cover: float | None,
    pooled_stats: dict | None,
    ndvi_interpretation: dict | None,
    confidence: dict | None,
    aoi_metadata: dict | None,
    crop_type: str,
    date_from: str,
    date_to: str,
    acquisition_dates: list[str] | None,
    ai_validated: bool | None,
) -> str:
    """Build the deterministic evidence block injected verbatim into the AI prompt."""
    pct = ndvi_stats.get("percentiles") or {}
    pooled = pooled_stats or {}
    interp = ndvi_interpretation or {}
    conf = confidence or {}
    aoi = aoi_metadata or {}
    centroid = aoi.get("centroid") or {}
    dates_str = ", ".join(acquisition_dates) if acquisition_dates else best_date

    ai_val_str = (
        "Validated (Claude 3 Haiku)"
        if ai_validated is True
        else "Flagged by AI validator"
        if ai_validated is False
        else "AI validation not enabled"
    )

    total_pixels = pooled.get("totalPixels", "N/A")
    try:
        total_pixels = f"{int(total_pixels):,}"
    except (TypeError, ValueError):
        total_pixels = "N/A"

    return f"""\
SATELLITE EVIDENCE PACK
========================
Analysis Context
  Crop type:            {crop_type.title()}
  Claim period:         {date_from} to {date_to}
  Best acquisition:     {best_date}
  All dates evaluated:  {dates_str}

Area of Interest
  Area:     {aoi.get("area_km2", "N/A")} km²  ({aoi.get("area_ha", "N/A")} ha)
  Centroid: {centroid.get("lat", "N/A")}°N,  {centroid.get("lon", "N/A")}°E
  AOI ref:  {aoi.get("aoi_hash", "N/A")}

Scene Quality  ({best_date})
  Cloud score (SCL-derived):  {cloud_score:.1%}
  Catalog cloud cover:        {cloud_cover if cloud_cover is not None else "N/A"}
  Image validation status:    {ai_val_str}

Per-Date NDVI Statistics  ({best_date}, 20 m/pixel, cloud-masked)
  Mean NDVI:         {_fmt(ndvi_stats.get("mean"))}
  Median NDVI (P50): {_fmt(pct.get("50.0"))}
  Std deviation:     {_fmt(ndvi_stats.get("stDev", ndvi_stats.get("std")))}
  P25 – P75:         {_fmt(pct.get("25.0"))} – {_fmt(pct.get("75.0"))}

Temporal Composite  ({date_from} to {date_to})
  Composite mean NDVI: {_fmt(pooled.get("mean"))}
  Pooled std dev:      {_fmt(pooled.get("stDev"))}
  Valid passes:        {pooled.get("passes", "N/A")}
  Total valid pixels:  {total_pixels}
  (Weighted pooling across all cloud-free passes; SCL classes 1,3,8,9,10 excluded)

Deterministic Vegetation Assessment
  Health class:   {interp.get("health_class", "N/A")}  ({interp.get("health_label", "N/A")})
  NDVI thresholds: ≥ 0.40 → Healthy Vegetation
                   0.20–0.39 → Moderate Stress / Sparse Cover
                   < 0.20 → Severe Stress / Bare Soil
  Composite {_fmt(pooled.get("mean"))} → class: {interp.get("health_class", "N/A")}
  Claim signal: {interp.get("claim_signal", "N/A")}

Pre-Computed Confidence  (do not recalculate or contradict)
  Overall:              {conf.get("label", "N/A")}  ({conf.get("overall", 0):.0%})
  Cloud clarity factor: {conf.get("cloud_clarity", 0):.0%}   (55% weight)
  Temporal coverage:    {conf.get("temporal_coverage", 0):.0%}   (35% weight, {conf.get("passes", 0)} passes)
  AI validation:        10% weight\
"""


_OUTPUT_SCHEMA = """\
{
  "executive_summary": "2-3 sentence plain-language summary for a non-technical reader. Must cite the composite mean NDVI value by number.",
  "technical_analysis": "3-4 sentences of NDVI-referenced technical analysis. Must quote specific numeric values. Must explain what the standard deviation indicates about field homogeneity.",
  "insurance_interpretation": "2-3 sentences in claim-adjudication language. Explicitly state whether satellite evidence SUPPORTS, CONTRADICTS, or is INCONCLUSIVE for the prevented-sowing claim. Must reference the confidence level.",
  "confidence_explanation": "1-2 sentences explaining why the confidence is the stated level. Must reference cloud score and satellite pass count by number.",
  "caveats": ["array of specific data-grounded limitations — each caveat must reference an actual value from the evidence pack"],
  "grounding_flags": ["array naming every metric you cited, e.g. 'composite_mean_ndvi', 'cloud_score', 'pass_count', 'pooled_std_dev'"]
}\
"""


def _parse_response(text: str) -> dict | None:
    """Attempt to extract a JSON object from raw model text."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return None


def _deterministic_fallback(
    ndvi_stats: dict,
    best_date: str,
    cloud_score: float,
    pooled_stats: dict | None,
    ndvi_interpretation: dict | None,
    confidence: dict | None,
    crop_type: str,
) -> dict:
    """
    Produces a fully deterministic assessment from computed metrics when AI is
    unavailable.  Every sentence is constructed from actual data values — no
    hallucination possible.
    """
    interp = ndvi_interpretation or {}
    conf = confidence or {}
    pooled = pooled_stats or {}

    mean_val = pooled.get("mean")
    passes = pooled.get("passes", 0)
    conf_label = conf.get("label", "Low")
    health_label = interp.get("health_label", "Unknown")
    claim_signal = interp.get("claim_signal", "")
    recommendation = interp.get("recommendation", "Field verification required.")

    mean_str = f"{float(mean_val):.3f}" if mean_val is not None else "unavailable"
    passes_str = f"{passes} satellite pass{'es' if passes != 1 else ''}"
    cloud_str = f"{cloud_score:.1%}"
    std_str = _fmt(pooled.get("stDev"))

    caveats: list[str] = ["AI narrative generation was unavailable; this assessment is fully deterministic."]
    if passes < 3:
        caveats.append(f"Only {passes_str} contributed to the composite — temporal reliability is limited.")
    if cloud_score > 0.30:
        caveats.append(f"Best scene cloud score of {cloud_str} may reduce spatial coverage of valid pixels.")
    if mean_val is None:
        caveats.append("Composite NDVI statistics unavailable for this date range.")

    return {
        "executive_summary": (
            f"Satellite analysis of the {crop_type} field for the period ending {best_date} "
            f"indicates {health_label.lower()} conditions (composite mean NDVI: {mean_str}). "
            f"This value was derived from {passes_str} at 20 m/pixel resolution with "
            f"cloud-masked pixels excluded."
        ),
        "technical_analysis": (
            f"Composite mean NDVI of {mean_str} (pooled std dev: {std_str}) "
            f"was computed across {passes_str} spanning the claim period. "
            f"Best-scene cloud score on {best_date} was {cloud_str}. "
            f"NDVI classification threshold: ≥ 0.40 healthy, 0.20–0.39 moderate, "
            f"< 0.20 stressed/bare. Composite {mean_str} → {health_label}."
        ),
        "insurance_interpretation": (
            f"{claim_signal} {recommendation} "
            f"Overall evidence confidence: {conf_label} "
            f"(cloud clarity: {conf.get('cloud_clarity', 0):.0%}, "
            f"temporal coverage: {conf.get('temporal_coverage', 0):.0%})."
        ),
        "confidence_explanation": (
            f"Confidence is {conf_label} based on a cloud clarity factor of "
            f"{conf.get('cloud_clarity', 0):.0%} and temporal coverage of "
            f"{conf.get('temporal_coverage', 0):.0%} across {passes_str}."
        ),
        "caveats": caveats,
        "grounding_flags": ["composite_mean_ndvi", "cloud_score", "pass_count", "pooled_std_dev"],
        "fallback": True,
    }


def generate_claim_narrative(
    image_b64: str,
    ndvi_stats: dict,
    best_date: str,
    cloud_score: float,
    *,
    pooled_stats: dict | None = None,
    ndvi_interpretation: dict | None = None,
    confidence: dict | None = None,
    aoi_metadata: dict | None = None,
    crop_type: str = "paddy",
    date_from: str = "",
    date_to: str = "",
    acquisition_dates: list[str] | None = None,
    cloud_cover: float | None = None,
    ai_validated: bool | None = None,
) -> dict:
    """
    Generate a grounded, evidence-based AI assessment for a prevented-sowing claim.

    Returns a structured dict:
      executive_summary       — plain-language 2-3 sentence summary
      technical_analysis      — NDVI-referenced technical explanation
      insurance_interpretation — claim-adjudication language
      confidence_explanation  — why confidence is high/medium/low
      caveats                 — list of specific data-grounded caveats
      grounding_flags         — metrics cited in the analysis
      fallback                — True if deterministic fallback was used

    Fails open: always returns a usable dict, never raises.
    """
    evidence_block = _build_evidence_block(
        ndvi_stats=ndvi_stats,
        best_date=best_date,
        cloud_score=cloud_score,
        cloud_cover=cloud_cover,
        pooled_stats=pooled_stats,
        ndvi_interpretation=ndvi_interpretation,
        confidence=confidence,
        aoi_metadata=aoi_metadata,
        crop_type=crop_type,
        date_from=date_from,
        date_to=date_to,
        acquisition_dates=acquisition_dates,
        ai_validated=ai_validated,
    )

    prompt = (
        f"{evidence_block}\n\n"
        "Based solely on the evidence pack above, produce your analysis.\n"
        "Quote specific numerical values from the evidence pack in every section that discusses metrics.\n"
        "Do not introduce any information not present in the evidence pack.\n\n"
        f"Respond ONLY with valid JSON matching this exact schema:\n{_OUTPUT_SCHEMA}"
    )

    content: list[dict] = []
    if image_b64:
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
            }
        )
    content.append({"type": "text", "text": prompt})

    try:
        response = _vertex_client().messages.create(
            model=_narrative_model(),
            max_tokens=800,
            system=_ANALYST_SYSTEM,
            messages=[{"role": "user", "content": content}],
        )
        raw = response.content[0].text.strip()
        _log.debug("AI narrative response: %d chars", len(raw))

        parsed = _parse_response(raw)
        if parsed and isinstance(parsed, dict):
            required = {
                "executive_summary",
                "technical_analysis",
                "insurance_interpretation",
                "confidence_explanation",
                "caveats",
                "grounding_flags",
            }
            if required.issubset(parsed.keys()):
                parsed["fallback"] = False
                return parsed
            _log.warning("AI response missing keys %s; using fallback", required - parsed.keys())
        else:
            _log.warning("AI response not parseable as JSON; using fallback")

    except Exception as exc:
        _log.warning("Narrative generation error: %s", exc)

    return _deterministic_fallback(
        ndvi_stats=ndvi_stats,
        best_date=best_date,
        cloud_score=cloud_score,
        pooled_stats=pooled_stats,
        ndvi_interpretation=ndvi_interpretation,
        confidence=confidence,
        crop_type=crop_type,
    )
