"""
Academic content module for Keryos.

All methodology text, architectural descriptions, pipeline diagrams, limitations,
and references are centralised here.  The rendering layer (ui_components.py,
pdf_generator.py) consumes these constants — never inlines them.
"""

# ── Project identity ───────────────────────────────────────────────────────────

PROJECT_TITLE = "Keryos: Satellite-Based Prevented-Sowing Claim Verification"
PROJECT_SUBTITLE = (
    "An automated geospatial intelligence system for agricultural insurance "
    "using Sentinel-2 multispectral imagery, cloud-masked NDVI analytics, "
    "and large-language-model-assisted evidence reasoning."
)
STUDENT_CONTEXT = (
    "Final-year college project demonstrating applied geospatial data science, "
    "cloud-native API integration, AI system design, and software engineering."
)

# ── Problem statement ──────────────────────────────────────────────────────────

PROBLEM_STATEMENT = """
**Prevented-sowing** is an agricultural insurance claim type where a farmer asserts
that adverse conditions (waterlogging, drought, delayed monsoon) prevented the sowing
of a crop within the scheduled window. Traditional claim verification relies on field
inspectors, which is:

- **Slow**: manual visits take days to weeks per claim
- **Expensive**: inspector cost scales linearly with claim volume
- **Inconsistent**: subjective assessments vary by inspector and region
- **Lagged**: by the time an inspector visits, ground conditions may have changed

**Keryos** addresses this by using freely available Copernicus Sentinel-2 satellite
imagery to produce an objective, time-stamped, spectral evidence record of the field
at the time of the claimed sowing window.  The system is not a replacement for field
verification — it is a first-pass evidence filter that flags claims that are clearly
consistent with, or inconsistent with, the alleged circumstances.
"""

# ── Why Sentinel-2 ────────────────────────────────────────────────────────────

SENTINEL2_RATIONALE = """
**Sentinel-2** is a twin-satellite constellation (S2A launched 2015, S2B 2017)
operated by the European Space Agency (ESA) as part of the Copernicus Earth
Observation Programme.  It was selected for this project for the following reasons:

**Spectral coverage:**  Sentinel-2 carries a MultiSpectral Instrument (MSI) with
13 spectral bands spanning 440–2200 nm.  Crucially, it captures the red band
(B04, 665 nm) and near-infrared band (B08, 842 nm) needed for NDVI computation
at 10 m spatial resolution, and SWIR bands (B11, 1610 nm; B12, 2190 nm) at 20 m
for soil moisture and vegetation water stress analysis.

**Spatial resolution:**  10 m (visible/NIR) and 20 m (red-edge/SWIR) per pixel —
sufficient to detect field-level vegetation patterns in agricultural parcels
(typical Indian fields: 0.5–5 ha).

**Temporal resolution:**  Combined 5-day revisit cycle (with both satellites),
with a minimum of 2–3 cloud-free overpasses expected in any 30-day sowing window,
depending on monsoon cloud cover.

**Data access:**  Copernicus Data Space Ecosystem (CDSE) provides free,
unrestricted access to the full archive under the Copernicus Data Policy
(similar to Creative Commons).  The Sentinel Hub API provides on-demand
processing, eliminating the need to store raw satellite data.

**Level-2A product:**  Keryos uses the L2A product, which has undergone
atmospheric correction using the Sen2Cor processor, converting top-of-atmosphere
reflectance to bottom-of-atmosphere (surface) reflectance.  This removes
atmospheric scattering and absorption effects, giving more physically meaningful
surface reflectance values for NDVI computation.

**Scene Classification Layer (SCL):**  L2A includes an automated per-pixel
scene classification (cloud, cloud shadow, vegetation, bare soil, water, etc.)
used for cloud masking in this system.

**Alternatives considered:**  Landsat 8/9 (NASA/USGS) offers 30 m resolution
and 16-day revisit — insufficient temporal density for sowing-window analysis.
Planet Labs provides daily 3 m imagery but requires a commercial license.
MODIS provides daily coverage at 250–500 m, too coarse for field-level analysis.
"""

# ── NDVI theory ────────────────────────────────────────────────────────────────

NDVI_THEORY = """
**The Normalised Difference Vegetation Index (NDVI)** was first proposed by
Tucker (1979) to detect and monitor vegetation using satellite data.  It
exploits the contrast between two spectral reflectance bands:

```
         NIR − RED
NDVI = ─────────────
         NIR + RED
```

Where:
- **RED** = reflectance in the red band (~665 nm, Band 4 on Sentinel-2)
- **NIR** = reflectance in the near-infrared band (~842 nm, Band 8 on Sentinel-2)

**Physical basis:**  Green plants contain chlorophyll, which absorbs red light
strongly for photosynthesis.  Leaf cell mesophyll strongly scatters and reflects
near-infrared radiation.  A healthy vegetated surface therefore shows low RED
reflectance and high NIR reflectance, yielding a high positive NDVI.  Bare soil
reflects both bands similarly (NDVI ≈ 0.1–0.2).  Water absorbs NIR strongly
(NDVI < 0).  Dense clouds reflect both bands equally (NDVI ≈ 0).

**Interpretation scale (Sentinel-2 L2A, agricultural context):**

| NDVI Range | Interpretation |
|---|---|
| −1.0 to 0.0 | Water, deep shadow, anomaly |
| 0.0 to 0.1 | Bare rock, sand, snow |
| 0.1 to 0.2 | Sparse/degraded vegetation, highly stressed bare soil |
| 0.2 to 0.4 | Moderate stress, early crop growth or sparse cover |
| 0.4 to 0.6 | Moderate to good crop cover — typical paddy tillering stage |
| 0.6 to 1.0 | Dense healthy vegetation, well-irrigated crops or forests |

**For Kharif paddy (the primary crop in this system):**
- At transplanting stage (10–15 days after transplanting): NDVI ≈ 0.25–0.40
- At tillering stage (30–45 days): NDVI ≈ 0.50–0.70
- If sowing was prevented: NDVI ≈ 0.05–0.20 (bare/flooded/fallow)

**Why NDVI specifically:**  NDVI is interpretable, well-validated over 40+ years
of literature, computationally simple, and directly computable from Sentinel-2
Band 4 and Band 8 without additional calibration.  More complex indices
(EVI, SAVI, MSAVI) correct for soil brightness and atmospheric effects but
require additional calibration constants and increase model opacity for a
college-level project with a limited scope.

**Composite statistics:**  A single-date NDVI value may be corrupted by residual
cloud, atmospheric haze, or thin cirrus.  This system computes a weighted pooled
composite across all valid satellite passes in the sowing window, weighted by
pixel count per pass.  This reduces noise from single-scene artefacts and
provides a more robust field-level estimate.

**Standard deviation interpretation:**  A low pooled standard deviation (< 0.05)
indicates a spatially homogeneous field — consistent with either uniformly bare
or uniformly vegetated land.  A high standard deviation (> 0.15) indicates
within-field heterogeneity, which may reflect partial sowing, mixed land use,
or cloud-shadow contamination in some passes.
"""

# ── Pipeline diagram ───────────────────────────────────────────────────────────

PIPELINE_DIAGRAM = """\
User Input
  AOI polygon (GeoJSON) · Date range · Crop type
  │
  ▼
┌──────────────────────────────────────────────────┐
│  INPUT VALIDATION                                │
│  • WGS84 coordinate bounds check                 │
│  • Area: 0.01 km² – 50,000 km²                  │
│  • Date range: 5 days – 365 days, no future      │
└─────────────────────┬────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────┐
│  SENTINEL HUB CATALOG API                        │
│  • Query S2 L2A scenes (eo:cloud_cover < 90%)   │
│  • De-duplicate by calendar date                 │
│  • Sort by catalog cloud cover ascending         │
│  • Limit: up to 100 candidates, top 12 probed   │
└─────────────────────┬────────────────────────────┘
                      │ ≤12 candidates
                      ▼
┌──────────────────────────────────────────────────┐
│  PHASE 1: PARALLEL SCL PROBE  (6 threads)        │
│  • Fetch 128×128 px SCL thumbnail per candidate  │
│  • Decode SCL red channel: class = round(R/255×11)│
│  • Cloud fraction from classes {1,3,8,9,10}      │
│  • Sort by cloud_score ascending                 │
└─────────────────────┬────────────────────────────┘
                      │ Top 6 candidates
                      ▼
┌──────────────────────────────────────────────────┐
│  PHASE 2: PARALLEL FULL-RES FETCH  (4 threads)   │
│                                                  │
│  For each candidate:                             │
│  ① Fetch 512×512 px true-colour PNG (B04/B03/B02)│
│  ② Brightness gate: mean luminance ≥ 10          │
│  ③ Image quality analysis:                       │
│     • mean_brightness, contrast, dark_fraction   │
│     • saturation_fraction, veg_fraction (GRI)    │
│     • spatial_entropy (Shannon, 64-bin histogram)│
│  ④ Composite quality scoring:                    │
│     score = 0.40×cloud_clarity + 0.25×contrast  │
│           + 0.15×brightness + 0.20×vegetation    │
│  ⑤ Hard-reject check (cloud, dark, sat, nodata) │
│  ⑥ [Optional] Claude 3 Haiku image validation   │
│  ⑦ Fetch 512×512 px SWIR false-colour PNG        │
│                                                  │
│  Output: ≤3 scenes ranked by composite_score    │
└─────────────────────┬────────────────────────────┘
                      │ Best scene date
                      ▼
┌──────────────────────────────────────────────────┐
│  SENTINEL HUB STATISTICS API                     │
│  • Per-day NDVI (best scene date)                │
│  • Range NDVI (full sowing window, P1D intervals)│
│  • Resolution: 20 m/pixel (Sentinel-2 native)   │
│  • Cloud mask: SCL classes 8,9,10 excluded       │
│  • Percentiles: P10, P25, P50, P75, P90          │
└─────────────────────┬────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────┐
│  POOLED COMPOSITE STATISTICS                     │
│  • Weighted mean NDVI: Σ(mᵢ·nᵢ) / Σnᵢ           │
│  • Pooled variance: Σ((σᵢ²+mᵢ²)·nᵢ)/Σnᵢ − μ²   │
│  • Passes: count of valid (non-NaN) intervals    │
│  • Weight = pixel count per interval             │
└─────────────────────┬────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────┐
│  DETERMINISTIC INTERPRETATION                    │
│  • NDVI health classification (0.20 / 0.40 gates)│
│  • Confidence scoring (cloud × passes × AI)      │
│  • Claim signal + recommendation generation      │
└─────────────────────┬────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────┐
│  [OPTIONAL] AI REASONING  (feature-flagged)      │
│  Claude 3.5 Sonnet via Google Cloud Vertex AI    │
│  • Evidence pack injected verbatim               │
│  • Grounding rules enforced via system prompt    │
│  • Structured JSON output (6 sections)           │
│  • Deterministic fallback on any failure         │
└─────────────────────┬────────────────────────────┘
                      │
                      ▼
               Report Bundle
      UI display · PDF export · JSON metadata\
"""

# ── System architecture ────────────────────────────────────────────────────────

ARCHITECTURE_OVERVIEW = """
Keryos follows a layered architecture that separates concerns cleanly
and enables components to be replaced or extended independently.

**Frontend Layer:**
- `streamlit_app.py` — thin orchestrator; handles session state, input
  validation, rate limiting, and result rendering.  No business logic.
- `utils/ui_components.py` — all Streamlit render functions, isolated from
  application logic.  Each function is independently testable.
- `utils/academic_content.py` — methodology text, diagrams, and references
  as module-level constants.  Never inline academic content in render code.

**Orchestration Layer:**
- `agents/tools/report_bundle.py` — the pipeline orchestrator.  Coordinates
  all backend calls in the correct order and assembles the final report dict.
- `agents/agent.py` — Google ADK SequentialAgent for the optional LLM-heavy
  pipeline (intake → geodata → analytics → report → verifier).  Not used
  by the Streamlit UI path.

**Data Access Layer:**
- `agents/tools/sentinelhub_catalog.py` — scene discovery via STAC Catalog API
- `agents/tools/sentinelhub_process.py` — image rendering via Process API
- `agents/tools/sentinelhub_stats.py` — NDVI statistics via Statistics API
- `agents/tools/cdse_auth.py` — OAuth2 token management with in-memory caching
- `agents/tools/api_cache.py` — TTL-based in-memory cache (5–10 min) for all
  Sentinel Hub responses; prevents redundant API calls within a session.
- `agents/tools/retry.py` — exponential back-off with full jitter for all HTTP calls.

**Intelligence Layer:**
- `agents/tools/image_score.py` — SCL cloud scoring and full image quality analysis
- `agents/tools/best_images.py` — two-phase parallel scene selection pipeline
- `agents/tools/image_validator_llm.py` — Claude 3 Haiku image quality validation
- `agents/tools/llm_narrative.py` — Claude 3.5 Sonnet evidence-grounded narrative
- `agents/tools/report_bundle.py` — deterministic NDVI interpretation and confidence scoring

**Output Layer:**
- `utils/pdf_generator.py` — ReportLab PDF: full verification pack, 1-page summary,
  and technical appendix
- `utils/messages.py` — all user-facing strings centralised (never inlined)

**Cross-cutting concerns:**
- All external HTTP calls go through `with_retry()` — no bare `requests.get()` in the codebase
- All API results are `@ttl_cached()` to prevent redundant calls in a session
- LLM features are feature-flagged via env vars; the app runs without any AI credentials
- `safe_extract_stats()` is the single source of truth for Statistics API response parsing
"""

# ── Confidence scoring methodology ────────────────────────────────────────────

CONFIDENCE_METHODOLOGY = """
**Overall confidence** is a composite score (0–1) computed deterministically
from three factors:

| Factor | Weight | Source |
|---|---|---|
| Cloud scene clarity  (1 − cloud_score) | 55% | SCL-derived cloud fraction |
| Temporal coverage (passes / 5, capped at 1.0) | 35% | Number of valid NDVI passes |
| AI image validation | 10% | Claude 3 Haiku assessment (if enabled) |

If AI validation is not enabled, the remaining 10% weight is redistributed
(overall = cloud × 0.55 + temporal × 0.35, normalised).

**Interpretation:**
- High (≥ 70%): cloud-clear scene + ≥ 3 satellite passes in window
- Medium (40–70%): partial cloud or limited temporal coverage
- Low (< 40%): heavy cloud contamination or single-pass window

**Limitations:**  This confidence score reflects data quality, not claim validity.
A high-confidence low-NDVI result strongly supports a prevented-sowing claim;
a low-confidence result (due to cloud cover) is inconclusive regardless of NDVI value.
"""

# ── Image quality scoring ──────────────────────────────────────────────────────

QUALITY_SCORING_METHODOLOGY = """
**Image quality scoring** produces a composite 0–1 score used to rank scenes
returned by the Phase 2 full-resolution fetch.  This replaces simple cloud-score
ranking, which can select technically cloud-free but informationally poor images
(e.g., uniform haze, data gaps, overexposed snow).

**Component scores (all normalised 0–1):**

| Component | Weight | Measurement |
|---|---|---|
| Cloud clarity | 40% | 1 − SCL-derived cloud fraction |
| Spatial contrast | 25% | Luminance std dev, normalised in [5, 70] |
| Brightness | 15% | Mean luminance, piecewise linear: optimal 80–160, penalised above/below |
| Vegetation proxy | 20% | Fraction of pixels with GRI > 0.05, where GRI = (G−R)/(G+R+1) |

**Hard-reject criteria** (scene discarded before scoring):
- Cloud fraction > 85%
- Mean brightness < 10 (no-data / black image)
- Dark fraction > 70% (mostly sensor no-data tiles)
- Saturation fraction > 75% (cloud-top white-out / snow)
- Valid pixel fraction < 10% (insufficient data coverage)

**Quality grades:**  A (≥ 0.75), B (≥ 0.55), C (≥ 0.35), D (≥ 0.20), F (< 0.20)

**Spatial entropy** (Shannon entropy of 64-bin luminance histogram) is tracked
as a supplementary metric and reported in the UI but not included in the scoring
formula to keep the scoring model simple and interpretable.
"""

# ── Remote sensing limitations ─────────────────────────────────────────────────

REMOTE_SENSING_LIMITATIONS = """
**Sentinel-2 and remote sensing have inherent limitations that affect the
reliability of satellite-based claim verification:**

**Cloud cover (primary limitation in monsoon-season claims):**
The Indian Kharif sowing season (June–September) coincides with the South-West
Monsoon, when cloud cover can exceed 90% for weeks at a time.  Sentinel-2 cannot
penetrate clouds; this system relies on finding cloud-free or cloud-minimal
scenes within the claimed sowing window.  If no usable scenes exist, the claim
cannot be verified from satellite data alone.  SAR (Synthetic Aperture Radar)
imagery — such as Sentinel-1 — can penetrate clouds but requires different
analysis methods not implemented in this version.

**Spatial resolution:**
At 10–20 m/pixel, Sentinel-2 cannot resolve individual plants or sub-metre
field features.  Each pixel represents a mixed signal from vegetation, soil,
water, and other surface elements at that location.  Small fields (< 1 ha)
may be dominated by boundary effects from adjacent land use.

**Temporal resolution:**
The 5-day revisit cycle means that rapid changes (e.g., crop emergence over
7 days) may be missed between overpasses.  Cloud cover further reduces the
effective revisit frequency.  A 30-day sowing window may yield only 1–2 usable
scenes.

**Atmospheric correction residuals:**
While Sentinel-2 L2A applies atmospheric correction, residual aerosol, thin
cloud, and haze can still bias NDVI values downward, potentially causing
false negatives (low NDVI despite actual crop cover).

**NDVI limitations:**
- NDVI saturates at values > 0.8 for very dense vegetation
- Bright bare soil can produce NDVI ≈ 0.1–0.2, overlapping with early crop stages
- Standing water (flooding) produces low NDVI, similar to bare/fallow land —
  which means this system cannot distinguish between prevented-sowing-due-to-flood
  and actual sowing that was subsequently flooded
- NDVI is sensitive to phenological stage; the same field at different growth
  stages produces very different NDVI values

**This system is evidence-gathering, not adjudication:**
Satellite analysis provides supporting evidence, not legal proof.  Claims should
not be approved or denied solely on this analysis; field verification remains
essential for borderline or high-value claims.
"""

# ── AI limitations ─────────────────────────────────────────────────────────────

AI_LIMITATIONS = """
**The AI components in Keryos have important limitations that affect how their
outputs should be interpreted:**

**Claude 3.5 Sonnet (narrative generation):**
- The model generates text grounded in the evidence pack injected into the prompt.
  It cannot access field knowledge, local weather records, or crop calendars
  beyond what is provided.
- The model cannot distinguish between visually similar spectral signatures
  (e.g., flooded bare soil vs. dry bare soil from an RGB image alone).
- The model's training data has a knowledge cutoff; it may not reflect the
  latest developments in agricultural remote sensing practice.
- The 800-token limit constrains the depth of analysis; complex multi-temporal
  patterns may not be fully described.
- **Hallucination risk:** The system prompt and output schema enforce
  evidence-grounding, and a deterministic fallback activates if the response
  fails validation.  However, subtle hallucinations (e.g., slightly incorrect
  metric values) cannot be fully excluded without manual verification.

**Claude 3 Haiku (image validation):**
- The model assesses broad image usability (is the image valid for analysis?),
  not fine-grained vegetation characteristics.
- It may occasionally flag valid scenes as invalid (false negatives) if the
  image has unusual spectral characteristics unfamiliar from training.
- The model's visual descriptions ("observed_features") are interpretations of
  the RGB composite, not the full multispectral signal.

**Vertex AI dependency:**
- Both LLM features require active GCP credentials and Vertex AI API access.
  All LLM calls fail open — if the API is unavailable, the pipeline continues
  with deterministic outputs.
- API latency (typically 2–8 seconds per call) adds to total pipeline runtime.

**The deterministic baseline is the primary evidence source:**
All claim signals, confidence scores, and NDVI classifications are computed
entirely without AI.  The AI narrative is a supplementary interpretation layer.
The system is designed so that disabling all AI features produces a fully valid
and defensible insurance assessment.
"""

# ── Future scalability ─────────────────────────────────────────────────────────

FUTURE_WORK = """
**Potential enhancements that would extend Keryos from a college prototype
to a production-grade system:**

**Sentinel-1 SAR integration:**
Synthetic Aperture Radar (SAR) can penetrate clouds and operates day/night.
Combining Sentinel-2 NDVI with Sentinel-1 C-band backscatter would enable
verification even during continuous monsoon cloud cover, the primary limitation
of the current system.

**Multi-temporal NDVI time series:**
Instead of a single composite value, computing an NDVI time series for the
full growing season (using dense temporal stacks) would enable detection of
transplanting onset, peak greenness, and senescence — providing much stronger
evidence of whether sowing occurred and at what stage it was interrupted.

**Reference field comparison:**
Comparing the claimed field's NDVI against neighbouring fields or a
regional baseline for the same crop and date would distinguish field-specific
issues (localised flooding, pest outbreak) from regional crop failure events.

**Geofenced farmer verification:**
Integrating GPS-tagged field boundary data from farmer portals would enable
sub-parcel analysis, eliminating boundary contamination from adjacent land use.

**Batch processing API:**
A FastAPI backend (currently scaffolded in `pyproject.toml` dependencies)
would enable processing of 100s of claims per hour, enabling use by insurance
companies at scale.

**Model fine-tuning:**
Fine-tuning Claude or an open-source VLM on a labelled dataset of
(satellite image, NDVI, claim outcome) triples could substantially improve
the AI reasoning layer's accuracy and reduce hallucination risk.

**Explainability dashboard:**
A SHAP or LIME-style explanation of how each factor contributed to the
confidence score would make the system more interpretable for regulators and
auditors.

**Offline/edge deployment:**
A lighter model (e.g., Llama 3 or Phi-3 running locally) combined with
a cached Sentinel-2 archive for common districts could enable operation
without cloud API dependencies, reducing data sovereignty concerns.
"""

# ── Software engineering notes ─────────────────────────────────────────────────

SOFTWARE_ENGINEERING_NOTES = """
**Design decisions and software engineering practices demonstrated:**

**Separation of concerns:**
- UI rendering (ui_components.py), application logic (streamlit_app.py), and
  business logic (report_bundle.py) are fully decoupled.
- Academic content (academic_content.py) is separated from rendering code,
  allowing content updates without touching render logic.
- User-facing strings are centralised in messages.py — never inlined.

**Fail-open design:**
- All LLM calls have deterministic fallbacks.  The pipeline never fails because
  of an AI API outage.
- Error classification (classify_error) maps technical exceptions to specific
  user-facing messages without exposing stack traces.

**Parallelism:**
- Phase 1 (SCL probe) and Phase 2 (full-res fetch) use ThreadPoolExecutor with
  configurable worker counts.  The Phase 2 executor cancels futures once 3
  valid scenes are found, preventing unnecessary API calls.

**Caching and rate limiting:**
- All Sentinel Hub API responses are cached in-process with a 5–10 minute TTL,
  preventing redundant calls when the same AOI is re-queried.
- A 10-second rate limit prevents rapid re-submission from the UI.

**Type annotations:**
- All public functions have return-type annotations.
- The report dict structure is documented as inline comments rather than a
  TypedDict (kept simple for a college project scope).

**Observability:**
- All modules use `logging.getLogger(__name__)`.  No `print()` calls.
- AOI coordinates are never logged; only the MD5 hash is used.
- The DEBUG env flag enables verbose logging without code changes.

**Reproducibility:**
- All pipeline parameters (resolution, cloud thresholds, scoring weights,
  NDVI thresholds) are stored in the report's `processing_metadata` field.
- The report integrity hash (SHA-256 of key fields) enables tamper detection.
- `generated_at` and all thresholds are embedded in the PDF footer.
"""

# ── Academic references ────────────────────────────────────────────────────────

REFERENCES = [
    {
        "key": "Tucker1979",
        "citation": (
            "Tucker, C.J. (1979). Red and photographic infrared linear "
            "combinations for monitoring vegetation. "
            "Remote Sensing of Environment, 8(2), 127–150."
        ),
        "relevance": "Original NDVI formulation",
    },
    {
        "key": "Drusch2012",
        "citation": (
            "Drusch, M., Del Bello, U., Carlier, S., et al. (2012). "
            "Sentinel-2: ESA's Optical High-Resolution Mission for GMES "
            "Operational Services. Remote Sensing of Environment, 120, 25–36."
        ),
        "relevance": "Sentinel-2 mission specification",
    },
    {
        "key": "Main2011",
        "citation": (
            "Main, R., Cho, M.A., Mathieu, R., et al. (2011). "
            "An investigation into robust spectral indices for leaf chlorophyll "
            "estimation. ISPRS Journal of Photogrammetry and Remote Sensing, 66(6), 751–761."
        ),
        "relevance": "Vegetation index robustness and NDVI saturation",
    },
    {
        "key": "Defourny2019",
        "citation": (
            "Defourny, P., Bontemps, S., Bellemans, N., et al. (2019). "
            "Near real-time agriculture monitoring at national scale at parcel "
            "resolution: Performance assessment of the Sen2-Agri automated system "
            "in various cropping systems around the world. "
            "Remote Sensing of Environment, 221, 551–568."
        ),
        "relevance": "Sentinel-2 for agricultural monitoring at field scale",
        },
    {
        "key": "Zhu2015",
        "citation": (
            "Zhu, Z., Wang, S., & Woodcock, C.E. (2015). Improvement and "
            "expansion of the Fmask algorithm: cloud, cloud shadow, and snow "
            "detection for Landsats 4–7, 8, and Sentinel 2 images. "
            "Remote Sensing of Environment, 159, 269–277."
        ),
        "relevance": "Cloud masking algorithms for Sentinel-2",
    },
    {
        "key": "Copernicus2023",
        "citation": (
            "European Space Agency / Copernicus (2023). "
            "Sentinel-2 User Handbook. ESA Standard Document, Issue 2. "
            "https://sentinels.copernicus.eu/documents/247904/685211/Sentinel-2_User_Handbook"
        ),
        "relevance": "Sentinel-2 technical reference",
    },
    {
        "key": "Anthropic2024",
        "citation": (
            "Anthropic (2024). Claude 3 Model Card. "
            "https://www.anthropic.com/claude-3-model-card"
        ),
        "relevance": "AI model used for image validation and narrative generation",
    },
]

# ── Scoring weights (mirror image_score.py — kept in sync manually) ────────────

SCORING_WEIGHTS = {
    "cloud_clarity":       0.40,
    "spatial_contrast":    0.25,
    "brightness":          0.15,
    "vegetation_proxy":    0.20,
}

NDVI_THRESHOLDS = {
    "healthy":  0.40,
    "moderate": 0.20,
}

CLOUD_CLASSES_MASKED = {
    1:  "Saturated or defective",
    3:  "Cloud shadow",
    8:  "Cloud medium probability",
    9:  "Cloud high probability",
    10: "Thin cirrus",
}

# ── Research questions ────────────────────────────────────────────────────────

RESEARCH_QUESTIONS = [
    {
        "number": "RQ1",
        "question": (
            "Can satellite-derived NDVI reliably detect the absence of crop emergence "
            "within a claimed Kharif sowing window using freely available Sentinel-2 data?"
        ),
        "motivation": (
            "Prevented-sowing claims hinge on whether a crop was sown.  "
            "NDVI is the standard proxy for vegetation presence, but its reliability "
            "at field scale during a monsoon-clouded sowing window is not guaranteed."
        ),
        "approach": (
            "Compare composite NDVI values computed from all cloud-free scenes within "
            "the sowing window against validated thresholds (≥ 0.4 = healthy, "
            "< 0.2 = bare/stressed), using cloud-masked Sentinel-2 L2A data."
        ),
    },
    {
        "number": "RQ2",
        "question": (
            "What combination of image quality metrics produces the most reliable "
            "scene ranking for agricultural NDVI analysis?"
        ),
        "motivation": (
            "Cloud cover alone is an insufficient proxy for image usability.  "
            "A scene with 5% cloud cover but dominated by haze, saturated "
            "pixels, or data gaps may yield unreliable NDVI values."
        ),
        "approach": (
            "Design a composite quality score (cloud clarity 40%, spatial contrast 25%, "
            "brightness 15%, vegetation proxy 20%) and compare rankings against "
            "cloud-cover-only ranking on known-quality test scenes."
        ),
    },
    {
        "number": "RQ3",
        "question": (
            "Can a large language model provide explainable, grounded insurance assessments "
            "from satellite evidence without introducing hallucinated claims?"
        ),
        "motivation": (
            "LLMs are capable of nuanced text generation but tend to confabulate "
            "details.  Insurance assessments require strict factual grounding — "
            "any invented metric could invalidate a claim decision."
        ),
        "approach": (
            "Design a structured evidence-injection prompt with an explicit "
            "anti-hallucination system prompt, JSON output schema, and "
            "deterministic fallback.  Validate that all numeric values in the "
            "AI output appear verbatim in the injected evidence pack."
        ),
    },
    {
        "number": "RQ4",
        "question": (
            "Can a fully deterministic pipeline (no AI) produce defensible "
            "prevented-sowing evidence that satisfies insurance industry standards?"
        ),
        "motivation": (
            "AI availability, latency, and cost are variable.  If the "
            "deterministic baseline is defensible on its own, the system can "
            "be deployed without Vertex AI credentials — increasing accessibility."
        ),
        "approach": (
            "Run the pipeline with all AI flags disabled.  Evaluate whether the "
            "NDVI composite + confidence score + health classification provide "
            "sufficient evidence for a first-pass claim filter."
        ),
    },
]

# ── Evaluation framework ───────────────────────────────────────────────────────

EVALUATION_FRAMEWORK = """
**A proper evaluation of Keryos would require the following:**

**Ground truth dataset:**
A labelled dataset of (satellite AOI, date range, crop type) → (field-inspected outcome)
pairs, where outcome ∈ {SOWING_CONFIRMED, SOWING_PREVENTED, PARTIAL_SOWING, INCONCLUSIVE}.
This dataset does not currently exist in public form; it would require collaboration
with an agricultural insurance company or the Pradhan Mantri Fasal Bima Yojana (PMFBY)
scheme to access historical inspector reports matched to geo-referenced field boundaries.

**Metrics:**

| Metric | Definition | Target |
|---|---|---|
| Precision (claim supported) | TP / (TP + FP) — of claims flagged as supported, fraction that are genuinely prevented | > 0.85 |
| Recall (claim supported) | TP / (TP + FN) — of genuinely prevented claims, fraction correctly identified | > 0.75 |
| Specificity | TN / (TN + FP) — of genuine sowings, fraction not wrongly flagged | > 0.90 |
| Inter-rater agreement | Cohen's κ between system verdict and field inspector verdict | > 0.60 |
| Temporal consistency | Agreement across scenes from different passes within same window | > 0.80 |

**Threshold sensitivity analysis:**
The current NDVI thresholds (0.40 healthy, 0.20 moderate) are literature-derived.
A proper evaluation would sweep thresholds from 0.10 to 0.60 and compute
precision-recall curves to find the optimal operating point for the specific
crop-region combination.

**Cloud cover sensitivity analysis:**
Evaluate how system accuracy degrades as a function of maximum cloud fraction
(10%, 30%, 50%, 70%) in the composite.  This is critical for monsoon-season
deployment where cloud cover can be persistent.

**Temporal window sensitivity analysis:**
Evaluate how composite NDVI accuracy varies with window length (7, 14, 30, 60 days),
identifying the minimum window needed for a reliable field assessment.

**Current project status:**
This project is a prototype demonstrating the system architecture, data pipeline,
and AI reasoning layer.  A formal accuracy evaluation requires a labelled
ground-truth dataset that is beyond the scope of a college project.  The
methodology above constitutes a proposed validation study for future work.
"""

# ── Technology design decisions ────────────────────────────────────────────────

DESIGN_DECISIONS = [
    {
        "decision": "Python as the primary language",
        "rationale": (
            "Python has the dominant ecosystem for geospatial data science "
            "(NumPy, Pillow, Shapely), AI SDK integration (Anthropic, Google ADK), "
            "and rapid prototyping (Streamlit).  R offers strong statistical "
            "libraries but lacks web deployment options.  Java offers better "
            "performance but significantly longer development cycles for a college project."
        ),
        "trade_off": "Runtime performance vs. development speed; Python chosen for speed.",
    },
    {
        "decision": "Streamlit for the frontend",
        "rationale": (
            "Streamlit converts Python functions directly into interactive web UI "
            "with no JavaScript required.  For a geospatial data science project, "
            "this eliminates a full React/Vue frontend stack while still enabling "
            "map interaction (via streamlit-folium), PDF download, and real-time "
            "status updates.  Flask/Django would require separate frontend development."
        ),
        "trade_off": "Limited styling control vs. zero JS overhead; Streamlit chosen for scope fit.",
    },
    {
        "decision": "Sentinel Hub API over direct Copernicus download",
        "rationale": (
            "Sentinel Hub provides on-demand processing via evalscripts — the server "
            "computes NDVI, cloud masks, and true-colour composites and returns only "
            "the pixels needed.  Direct download from CDSE would require handling "
            "10-100 GB .SAFE archives per scene, running Sen2Cor locally for "
            "atmospheric correction, and storing processed data.  For a prototype "
            "with variable AOI and date ranges, on-demand processing is far superior."
        ),
        "trade_off": "API cost and rate limits vs. storage/compute overhead; API chosen.",
    },
    {
        "decision": "ReportLab for PDF generation",
        "rationale": (
            "ReportLab generates PDFs purely in Python with fine-grained layout control "
            "and no browser/HTML dependencies.  WeasyPrint and pdfkit require a "
            "headless browser or wkhtmltopdf binary.  For a server-side application "
            "generating professional insurance documents, ReportLab's reliability and "
            "portability outweigh its verbose API."
        ),
        "trade_off": "Verbose code vs. dependency simplicity; ReportLab chosen.",
    },
    {
        "decision": "Weighted pooled composite over single-scene NDVI",
        "rationale": (
            "A single satellite pass may have cloud shadow on part of the field, "
            "data gaps, or atmospheric residuals.  Pooling NDVI across all valid "
            "passes in the sowing window, weighted by pixel count, reduces noise "
            "and produces a more representative field-level estimate.  The pooled "
            "standard deviation also captures within-field variability across time, "
            "which is valuable for distinguishing partial from complete sowing."
        ),
        "trade_off": "More computation vs. reliability improvement; pooling chosen.",
    },
    {
        "decision": "Fail-open AI design (LLM as optional layer)",
        "rationale": (
            "Insurance claim processing cannot depend on a third-party API being "
            "available.  If Vertex AI is unreachable, the claim still needs an "
            "assessment.  By designing the deterministic NDVI pipeline as the "
            "primary evidence source and AI as a supplementary layer, the system "
            "remains fully functional without LLM credentials."
        ),
        "trade_off": "AI unavailable during outages, but baseline always works.",
    },
    {
        "decision": "Two-phase parallel image selection (probe + full fetch)",
        "rationale": (
            "Fetching full-resolution images for all catalog candidates would "
            "require 10–20 API calls of 512×512 px each.  The SCL probe phase "
            "fetches 128×128 px thumbnails (16× cheaper) to compute cloud fractions "
            "first, then only fetches full-resolution images for the top N candidates. "
            "This reduces API cost and latency by approximately 60–70%."
        ),
        "trade_off": "Extra code complexity vs. 60-70% reduction in API calls.",
    },
    {
        "decision": "TTL-based in-memory caching for all API responses",
        "rationale": (
            "The Streamlit reruns the entire script on every user interaction. "
            "Without caching, every map interaction or widget change would re-query "
            "the Sentinel Hub API, incurring latency and cost.  A 5–10 minute TTL "
            "cache ensures that repeated queries for the same AOI/date return instantly."
        ),
        "trade_off": "Stale data risk (5 min) vs. significantly improved interactivity.",
    },
]

# ── Comparison with alternative approaches ────────────────────────────────────

COMPARISON_WITH_ALTERNATIVES = [
    {
        "approach": "Manual field inspection (current practice)",
        "spatial_res": "Ground truth",
        "temporal_res": "One-time",
        "cost": "High (inspector salary + travel)",
        "cloud_immunity": "Yes",
        "scalability": "Poor — linear with claim volume",
        "objectivity": "Low — subjective, inspector-dependent",
        "why_not": "The baseline problem this system replaces",
    },
    {
        "approach": "Sentinel-2 L2A (this project)",
        "spatial_res": "10–20 m",
        "temporal_res": "5-day revisit",
        "cost": "Free (Copernicus Open Data)",
        "cloud_immunity": "No",
        "scalability": "High — API-based, parallel",
        "objectivity": "High — deterministic spectral analysis",
        "why_not": "Selected",
    },
    {
        "approach": "Landsat 8 / 9 (NASA/USGS)",
        "spatial_res": "30 m",
        "temporal_res": "16-day revisit",
        "cost": "Free",
        "cloud_immunity": "No",
        "scalability": "High",
        "objectivity": "High",
        "why_not": "30 m too coarse for small fields; 16-day revisit insufficient for 30-day window",
    },
    {
        "approach": "MODIS (Terra/Aqua)",
        "spatial_res": "250–500 m",
        "temporal_res": "1–2 days",
        "cost": "Free",
        "cloud_immunity": "No",
        "scalability": "High",
        "objectivity": "High",
        "why_not": "250 m pixels cover entire fields — cannot analyse individual parcels",
    },
    {
        "approach": "Planet Labs (PlanetScope)",
        "spatial_res": "3–5 m",
        "temporal_res": "Daily",
        "cost": "Commercial (expensive)",
        "cloud_immunity": "No",
        "scalability": "High",
        "objectivity": "High",
        "why_not": "Commercial license required; not accessible for college project or small insurers",
    },
    {
        "approach": "Sentinel-1 SAR",
        "spatial_res": "10–20 m",
        "temporal_res": "6-day revisit",
        "cost": "Free",
        "cloud_immunity": "Yes",
        "scalability": "High",
        "objectivity": "High",
        "why_not": "SAR backscatter analysis requires different algorithms; not as interpretable as NDVI for crop presence. Proposed as future enhancement.",
    },
]

# Sentinel-2 band reference used in this project
SENTINEL2_BANDS = {
    "B02": {"wavelength_nm": 490,  "resolution_m": 10,  "name": "Blue"},
    "B03": {"wavelength_nm": 560,  "resolution_m": 10,  "name": "Green"},
    "B04": {"wavelength_nm": 665,  "resolution_m": 10,  "name": "Red"},
    "B08": {"wavelength_nm": 842,  "resolution_m": 10,  "name": "NIR (broad)"},
    "B11": {"wavelength_nm": 1610, "resolution_m": 20,  "name": "SWIR-1"},
    "B12": {"wavelength_nm": 2190, "resolution_m": 20,  "name": "SWIR-2"},
    "SCL": {"wavelength_nm": None, "resolution_m": 20,  "name": "Scene Classification"},
}
