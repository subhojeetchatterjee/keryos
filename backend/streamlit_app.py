import hashlib
import json
import logging
import logging.config
import os
import time
import traceback
from datetime import date, datetime, timedelta

import folium
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium

from agents.tools.geojson_utils import validate_aoi
from agents.tools.report_bundle import get_report_bundle_for_ui
from utils.messages import (
    AOI_INVALID_COORDS,
    AOI_NOT_POLYGON,
    AOI_TOO_LARGE,
    AOI_TOO_SMALL,
    AUTH_FAILED,
    DATE_FUTURE,
    DATE_ORDER,
    DATE_RANGE_TOO_LONG,
    DATE_RANGE_TOO_SHORT,
    INVALID_AOI,
    NO_AOI,
    NO_DATES,
    PHASE_CATALOG,
    PHASE_DONE,
    PHASE_IMAGES,
    PHASE_STATS,
    RATE_LIMITED,
    TIMEOUT,
)
from utils.ui_components import (
    inject_accessibility_css,
    render_ai_narrative,
    render_alternatives,
    render_architecture_tab,
    render_best_scene,
    render_comparison_table,
    render_design_decisions,
    render_evaluation_framework,
    render_faq,
    render_future_work_tab,
    render_hero_header,
    render_latency,
    render_limitations_tab,
    render_methodology_tab,
    render_ndvi_section,
    render_pdf_buttons,
    render_pipeline_diagram,
    render_references_tab,
    render_reproducibility_panel,
    render_research_questions,
    render_system_status,
    render_visual_pipeline,
)

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("DEBUG", "false").lower() == "true" else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
_log = logging.getLogger(__name__)

_RATE_LIMIT_SECONDS = 10


def _validate_dates(date_from: date, date_to: date) -> str | None:
    """Return an error string if the date range is invalid, else None."""
    today = date.today()
    if date_from > date_to:
        return DATE_ORDER
    if date_from > today:
        return DATE_FUTURE
    if (date_to - date_from).days < 5:
        return DATE_RANGE_TOO_SHORT
    if (date_to - date_from).days > 365:
        return DATE_RANGE_TOO_LONG
    return None


def _classify_error(err: str) -> str:
    """Map a backend exception message to a user-facing error string."""
    el = err.lower()
    if "timed out" in el or "timeout" in el:
        return f"⏱️ {TIMEOUT}"
    if "401" in err or "auth" in el or "credentials" in el:
        return f"🔑 {AUTH_FAILED}"
    if "too small" in el:
        return f"📐 {AOI_TOO_SMALL}"
    if "too large" in el:
        return f"📐 {AOI_TOO_LARGE}"
    if "polygon" in el or "linestring" in el or "point" in el:
        return f"📐 {AOI_NOT_POLYGON}"
    if "longitude" in el or "latitude" in el or "out of range" in el:
        return f"🗺️ {AOI_INVALID_COORDS}"
    if "400" in err or "invalid aoi" in el:
        return f"📐 {INVALID_AOI}"
    return f"❌ Error generating report: {err}"


def main() -> None:
    # --- Session state initialisation ---
    for key, default in [("report", None), ("aoi_geojson", None), ("last_submit_time", 0.0)]:
        if key not in st.session_state:
            st.session_state[key] = default

    st.set_page_config(page_title="Keryos — Crop Verification", layout="wide", page_icon="🛰️")
    inject_accessibility_css()
    render_hero_header()

    # Initialise LLM flags before sidebar so render_system_status can read them
    enable_llm = False
    enable_narrative = False

    # --- Sidebar ---
    with st.sidebar:
        st.markdown('<span class="sb-label">Mission Parameters</span>', unsafe_allow_html=True)
        crop_type = st.selectbox("Crop Type", ["Paddy", "Wheat", "Cotton"])
        date_from = st.date_input("Sowing Window Start", value=datetime(2023, 7, 1))
        date_to = st.date_input("Sowing Window End", value=datetime(2023, 7, 31))

        st.markdown('<hr style="border-color:rgba(0,214,143,0.09);margin:1rem 0;">', unsafe_allow_html=True)
        st.markdown('<span class="sb-label">AI Features</span>', unsafe_allow_html=True)

        enable_llm = st.checkbox(
            "AI Image Validation",
            value=False,
            help="Uses Claude 3 Haiku via Vertex AI to validate image quality",
        )
        enable_narrative = st.checkbox(
            "AI Narrative",
            value=False,
            help="Uses Claude 3.5 Sonnet via Vertex AI to write a professional assessment",
        )

        os.environ["ENABLE_LLM_VALIDATION"] = "true" if enable_llm else "false"
        os.environ["ENABLE_AI_NARRATIVE"] = "true" if enable_narrative else "false"

        if enable_llm or enable_narrative:
            st.info("Requires ANTHROPIC_VERTEX_PROJECT_ID and CLOUD_ML_REGION.")

        st.markdown('<hr style="border-color:rgba(0,214,143,0.09);margin:1rem 0;">', unsafe_allow_html=True)
        render_faq()

    render_system_status(enable_llm, enable_narrative)

    # --- Tabs ---
    tab_analysis, tab_methodology, tab_about = st.tabs(
        ["Analysis", "Methodology", "About"]
    )

    with tab_analysis:
        _run_analysis_tab(enable_llm, enable_narrative, crop_type, date_from, date_to)

    with tab_methodology:
        _run_methodology_tab()

    with tab_about:
        _run_about_tab()


def _run_analysis_tab(
    enable_llm: bool,
    enable_narrative: bool,
    crop_type: str,
    date_from: "date",
    date_to: "date",
) -> None:
    """All existing analysis logic — map, generate, results."""
    import streamlit as st  # already imported at module level; re-bind for clarity

    # --- Map ---
    st.markdown('<p class="k-head">Area of Interest</p>', unsafe_allow_html=True)
    st.caption(
        "Draw a polygon using the toolbar (top-left of the map). "
        "Minimum 1 hectare · Maximum 50 000 km²."
    )
    m = folium.Map(location=[22.9, 88.3], zoom_start=10)
    Draw(
        export=True,
        draw_options={
            "polygon": True,
            "rectangle": True,
            "circle": False,
            "circlemarker": False,
            "marker": False,
            "polyline": False,
        },
    ).add_to(m)
    map_data = st_folium(m, width=725, height=500, key="map")

    # Update AOI from last drawn shape
    aoi_geojson = None
    if map_data and map_data.get("last_active_drawing"):
        new_geom = map_data["last_active_drawing"].get("geometry")
        if new_geom:
            new_aoi = {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "geometry": new_geom, "properties": {}}],
            }
            if new_aoi != st.session_state.get("aoi_geojson"):
                st.session_state["aoi_geojson"] = new_aoi
                st.session_state["report"] = None
    aoi_geojson = st.session_state.get("aoi_geojson")

    # AOI indicator
    if aoi_geojson:
        raw_coords = aoi_geojson["features"][0]["geometry"].get("coordinates", [[]])
        coords = raw_coords[0] if raw_coords and isinstance(raw_coords[0], list) else raw_coords
        n_verts = (
            (len(coords) - 1)
            if isinstance(coords, list) and coords and isinstance(coords[0], (list, tuple))
            else "?"
        )
        aoi_hash = hashlib.md5(json.dumps(aoi_geojson, sort_keys=True).encode()).hexdigest()[:8]
        st.markdown(
            f'<div class="aoi-card">'
            f'<span class="aoi-dot"></span>'
            f'AOI Active &nbsp;<span class="aoi-sub">· {n_verts} vertices · hash {aoi_hash[:6]}'
            f' · draw a new polygon to replace</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.warning("No AOI selected — draw a polygon on the map first.")

    # --- Generate button ---
    if st.button("🚀 Generate Verification Report", type="primary"):
        safe_aoi = st.session_state.get("aoi_geojson") or aoi_geojson

        # Rate limiting
        now = time.time()
        since_last = now - float(st.session_state.get("last_submit_time", 0))
        if since_last < _RATE_LIMIT_SECONDS:
            remaining = int(_RATE_LIMIT_SECONDS - since_last) + 1
            st.warning(f"⏳ {RATE_LIMITED.format(seconds=remaining)}")
            st.stop()

        # Input validation
        if not safe_aoi:
            st.error(f"❌ {NO_AOI}")
            st.stop()
        if not date_from or not date_to:
            st.error(f"❌ {NO_DATES}")
            st.stop()
        date_err = _validate_dates(date_from, date_to)
        if date_err:
            st.error(f"📅 {date_err}")
            st.stop()

        # AOI geometry validation (coordinate range + area check)
        try:
            validate_aoi(safe_aoi)
        except ValueError as ve:
            st.error(f"📐 {ve}")
            st.stop()

        st.session_state["last_submit_time"] = now

        # Pipeline with multi-step progress
        try:
            with st.status("🛰️ Generating verification report…", expanded=True) as status:
                st.write(PHASE_CATALOG)
                st.write(PHASE_IMAGES)
                st.write(PHASE_STATS)

                t_start = time.time()
                report = get_report_bundle_for_ui(
                    aoi_geojson=safe_aoi,
                    date_from=date_from.strftime("%Y-%m-%d"),
                    date_to=date_to.strftime("%Y-%m-%d"),
                    crop_type=crop_type,
                )
                elapsed = time.time() - t_start
                report["_elapsed_seconds"] = elapsed

                status.update(label=PHASE_DONE, state="complete", expanded=False)

            st.session_state["report"] = report
            st.success(f"✅ Report generated in {elapsed:.0f} s!")

        except Exception as exc:
            err = str(exc)
            _log.exception("Report generation failed")
            st.error(_classify_error(err))
            with st.expander("Debug Info"):
                st.code(traceback.format_exc())

    # --- Results display ---
    if st.session_state.get("report"):
        report = st.session_state["report"]

        st.markdown("---")
        st.markdown('<p class="k-head">Verification Results</p>', unsafe_allow_html=True)

        render_best_scene(report)
        render_ndvi_section(report)
        render_ai_narrative(report)
        render_alternatives(report)

        elapsed = report.get("_elapsed_seconds")
        if elapsed:
            render_latency(elapsed)

        render_pdf_buttons(report, st.session_state.get("aoi_geojson"))


def _run_methodology_tab() -> None:
    """Methodology & Documentation tab."""
    import streamlit as st

    tab_rq, tab_m, tab_pipe, tab_eval, tab_dd, tab_lim, tab_future, tab_refs = st.tabs([
        "Research Questions",
        "Methodology",
        "Pipeline",
        "Evaluation",
        "Design Decisions",
        "Limitations",
        "Future Work",
        "References",
    ])

    with tab_rq:
        render_research_questions()

    with tab_m:
        render_methodology_tab()
        st.markdown("---")
        render_comparison_table()

    with tab_pipe:
        render_visual_pipeline()
        st.markdown("---")
        with st.expander("Text / ASCII version (for copy-paste into documents)"):
            render_pipeline_diagram()

    with tab_eval:
        render_evaluation_framework()

    with tab_dd:
        render_design_decisions()

    with tab_lim:
        render_limitations_tab()

    with tab_future:
        render_future_work_tab()

    with tab_refs:
        render_references_tab()


def _run_about_tab() -> None:
    """About / Architecture tab."""
    import streamlit as st

    render_architecture_tab()
    st.markdown("---")

    if st.session_state.get("report"):
        render_reproducibility_panel(st.session_state["report"])
    else:
        st.info(
            "Generate a report from the Analysis tab to see the full reproducibility "
            "record (all pipeline parameters and thresholds) for that specific run."
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        st.error(f"Application error: {exc}")
        with st.expander("Debug Info"):
            st.code(traceback.format_exc())
