"""Centralised user-facing error and status message strings."""

# --- Input validation ---
NO_AOI = "Please draw an AOI polygon on the map before generating a report."
NO_DATES = "Please select both a start date and an end date."
DATE_ORDER = "End date must be after start date."
DATE_FUTURE = "Date range cannot be in the future. Sentinel-2 data is only available for past dates."
DATE_RANGE_TOO_LONG = "Date range exceeds 365 days. Please narrow your sowing window."
DATE_RANGE_TOO_SHORT = "Date range must be at least 5 days to capture a Sentinel-2 overpass."

# --- AOI geometry errors ---
AOI_TOO_SMALL = (
    "AOI polygon is too small (< 0.01 km²). "
    "Zoom in on the map and draw a larger polygon covering at least 1 hectare."
)
AOI_TOO_LARGE = (
    "AOI polygon is too large (> 50 000 km²). "
    "Draw a smaller polygon focused on the specific field or farm block."
)
AOI_NOT_POLYGON = (
    "Please draw a closed polygon — not a point or line. "
    "Use the polygon tool in the top-left corner of the map."
)
AOI_INVALID_COORDS = (
    "Polygon coordinates are outside valid map bounds. Re-draw the polygon within the map area."
)

# --- API / network errors ---
TIMEOUT = "Sentinel Hub timed out — their servers are busy right now. Please wait 30 seconds and try again."
AUTH_FAILED = (
    "Authentication failed — check that SH_CLIENT_ID and SH_CLIENT_SECRET "
    "are set correctly in your environment."
)
INVALID_AOI = (
    "The API rejected the polygon geometry (HTTP 400). "
    "Try redrawing it slightly larger, avoiding self-intersections, "
    "or choosing a different location."
)
NO_SCENES = (
    "No cloud-free satellite scenes found for this AOI and date window. "
    "Try widening the date range, increasing the cloud-cover tolerance, "
    "or selecting a different season."
)
RATE_LIMITED = "Please wait {seconds}s before submitting another request."
GENERIC_ERROR = "An unexpected error occurred: {detail}"

# --- Stats / NDVI ---
NDVI_UNAVAILABLE = "NDVI statistics unavailable for this date."
NDVI_NO_PIXELS = (
    "No valid pixels for this date/location. "
    "The field may be water-covered, heavily cloud-shadowed, or outside the satellite swath."
)
NDVI_API_ERROR = "NDVI API error {status}: {detail}"
COMPOSITE_UNAVAILABLE = "Could not compute composite statistics for the requested date range."

# --- Pipeline phases shown during generation ---
PHASE_CATALOG = "🔍 Searching Sentinel-2 catalog for cloud-free scenes…"
PHASE_IMAGES = "📡 Fetching best satellite imagery (this may take 30–60 s)…"
PHASE_STATS = "📊 Computing NDVI statistics across all passes…"
PHASE_DONE = "✅ Report ready!"
