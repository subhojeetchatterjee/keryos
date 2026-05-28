"""Reusable Streamlit UI render functions, separated from main app logic."""
import base64

import streamlit as st

from agents.tools.stats_utils import safe_extract_stats
from utils.messages import (
    COMPOSITE_UNAVAILABLE,
    NDVI_API_ERROR,
    NDVI_NO_PIXELS,
    NDVI_UNAVAILABLE,
)

# ── Theme / CSS ────────────────────────────────────────────────────────────────
_THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Titillium+Web:ital,wght@0,300;0,400;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg-0:       #060a14;
  --bg-1:       #0c1220;
  --bg-2:       #111827;
  --bg-glass:   rgba(11, 17, 31, 0.88);
  --border:     rgba(0, 214, 143, 0.09);
  --border-hi:  rgba(0, 214, 143, 0.28);
  --accent-g:   #00d68f;
  --accent-b:   #38bdf8;
  --accent-a:   #fbbf24;
  --accent-r:   #f87171;
  --text-1:     #f0f4f8;
  --text-2:     #94a3b8;
  --text-3:     #475569;
  --r:          8px;
  --r-lg:       14px;
}

/* ── Base ─────────────────────────────────────────────── */
html, body, [data-testid="stApp"] {
  font-family: 'Titillium Web', sans-serif !important;
  background: var(--bg-0) !important;
  color: var(--text-1) !important;
}
[data-testid="stDecoration"] { display: none !important; }
[data-testid="stHeader"] {
  background: rgba(6,10,20,0.96) !important;
  backdrop-filter: blur(16px);
  border-bottom: 1px solid var(--border);
}

/* ── Main ─────────────────────────────────────────────── */
[data-testid="stMain"] { background: var(--bg-0) !important; }
.block-container {
  padding: 1.5rem 2rem 3rem !important;
  max-width: 1200px !important;
}

/* ── Sidebar ──────────────────────────────────────────── */
[data-testid="stSidebar"] {
  background: var(--bg-1) !important;
  border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] > div { padding: 0 !important; }
[data-testid="stSidebarContent"] { padding: 1.25rem 1rem 2rem !important; }

/* ── Metrics ──────────────────────────────────────────── */
[data-testid="stMetric"] {
  background: var(--bg-glass) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--r) !important;
  padding: 0.8rem 1rem !important;
  backdrop-filter: blur(8px);
  transition: border-color 0.2s;
}
[data-testid="stMetric"]:hover { border-color: var(--border-hi) !important; }
[data-testid="stMetricLabel"] {
  color: var(--text-2) !important;
  font-family: 'Titillium Web', sans-serif !important;
  font-size: 0.68rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.10em !important;
  text-transform: uppercase !important;
}
[data-testid="stMetricValue"] {
  color: var(--text-1) !important;
  font-family: 'JetBrains Mono', monospace !important;
  font-size: 1.3rem !important;
  font-weight: 500 !important;
}

/* ── Buttons ──────────────────────────────────────────── */
.stButton > button {
  font-family: 'Titillium Web', sans-serif !important;
  font-weight: 700 !important;
  font-size: 0.82rem !important;
  letter-spacing: 0.07em !important;
  text-transform: uppercase !important;
  border-radius: var(--r) !important;
  min-height: 2.75rem !important;
  padding: 0.45rem 1.5rem !important;
  transition: all 0.18s ease !important;
}
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, #00d68f 0%, #00b87a 100%) !important;
  border: none !important;
  color: #060a14 !important;
  box-shadow: 0 0 22px rgba(0,214,143,0.22) !important;
}
.stButton > button[kind="primary"]:hover {
  box-shadow: 0 0 36px rgba(0,214,143,0.42) !important;
  transform: translateY(-1px) !important;
}
.stButton > button:not([kind="primary"]) {
  background: var(--bg-2) !important;
  border: 1px solid var(--border-hi) !important;
  color: var(--accent-g) !important;
}
.stButton > button:not([kind="primary"]):hover {
  background: rgba(0,214,143,0.07) !important;
  border-color: var(--accent-g) !important;
}
[data-testid="stDownloadButton"] > button {
  background: rgba(0,214,143,0.07) !important;
  border: 1px solid var(--accent-g) !important;
  color: var(--accent-g) !important;
  font-family: 'Titillium Web', sans-serif !important;
  font-weight: 700 !important;
  font-size: 0.82rem !important;
  letter-spacing: 0.05em !important;
  border-radius: var(--r) !important;
}

/* ── Inputs ───────────────────────────────────────────── */
.stSelectbox > div > div,
.stDateInput > div > div > input,
.stTextInput > div > div > input {
  background: var(--bg-2) !important;
  border: 1px solid var(--border) !important;
  color: var(--text-1) !important;
  border-radius: var(--r) !important;
  font-family: 'Titillium Web', sans-serif !important;
}
.stSelectbox > div > div:focus-within,
.stDateInput > div > div > input:focus {
  border-color: var(--accent-g) !important;
}
.stCheckbox label { color: var(--text-1) !important; }
.stCheckbox label p { color: var(--text-1) !important; }

/* ── Alerts ───────────────────────────────────────────── */
[data-testid="stAlert"] {
  border-radius: var(--r) !important;
  border-width: 1px !important;
}

/* ── Expanders ────────────────────────────────────────── */
[data-testid="stExpander"] {
  border: 1px solid var(--border) !important;
  border-radius: var(--r) !important;
  background: var(--bg-glass) !important;
  backdrop-filter: blur(8px) !important;
}
[data-testid="stExpander"]:hover { border-color: var(--border-hi) !important; }

/* ── Status widget ────────────────────────────────────── */
[data-testid="stStatusWidget"] {
  background: var(--bg-glass) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--r-lg) !important;
}

/* ── Misc ─────────────────────────────────────────────── */
hr { border-color: var(--border) !important; margin: 1.5rem 0 !important; }
.stCaption, [data-testid="stCaptionContainer"] {
  color: var(--text-2) !important; font-size: 0.8rem !important;
}
[data-testid="stImage"] img {
  border-radius: var(--r) !important;
  border: 1px solid var(--border) !important;
}
button:focus-visible, [role="button"]:focus-visible, a:focus-visible {
  outline: 2px solid var(--accent-g) !important;
  outline-offset: 2px !important;
}

/* ── Tables ───────────────────────────────────────────── */
[data-testid="stTable"] table {
  font-family: 'JetBrains Mono', monospace !important;
  font-size: 0.82rem !important;
}
[data-testid="stTable"] th {
  background: var(--bg-2) !important;
  color: var(--text-2) !important;
  font-size: 0.67rem !important;
  letter-spacing: 0.07em !important;
  text-transform: uppercase !important;
  border-bottom: 1px solid var(--border) !important;
}
[data-testid="stTable"] td {
  color: var(--text-1) !important;
  border-bottom: 1px solid var(--border) !important;
}

/* ── Scrollbar ────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--bg-0); }
::-webkit-scrollbar-thumb { background: var(--border-hi); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--accent-g); }

/* ═══════════════════════════════════════════════════════
   Custom components
   ═══════════════════════════════════════════════════════ */

/* Hero */
.k-hero {
  background: linear-gradient(135deg, rgba(0,214,143,0.04) 0%, transparent 55%),
              linear-gradient(to bottom, var(--bg-1), var(--bg-0));
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 2rem 2.5rem 1.75rem;
  margin-bottom: 1.25rem;
  position: relative;
  overflow: hidden;
}
.k-hero::after {
  content: '';
  position: absolute;
  top: -40px; right: -40px;
  width: 260px; height: 260px;
  background: radial-gradient(circle, rgba(0,214,143,0.07) 0%, transparent 70%);
  pointer-events: none;
}
.k-hero-wordmark {
  font-family: 'Titillium Web', sans-serif;
  font-size: 2.2rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: var(--text-1);
  margin: 0 0 0.2rem;
  line-height: 1;
}
.k-hero-wordmark em { color: var(--accent-g); font-style: normal; }
.k-hero-sub {
  font-size: 0.9rem;
  color: var(--text-2);
  margin: 0 0 1.1rem;
  font-weight: 300;
  letter-spacing: 0.03em;
}
.k-tags { display: flex; gap: 0.45rem; flex-wrap: wrap; }
.k-tag {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.66rem;
  letter-spacing: 0.04em;
  padding: 0.17rem 0.62rem;
  border-radius: 20px;
  font-weight: 500;
}
.k-tag-g { background: rgba(0,214,143,0.10); color: var(--accent-g); border: 1px solid rgba(0,214,143,0.22); }
.k-tag-b { background: rgba(56,189,248,0.10); color: var(--accent-b); border: 1px solid rgba(56,189,248,0.22); }
.k-tag-a { background: rgba(251,191,36,0.10);  color: var(--accent-a); border: 1px solid rgba(251,191,36,0.22); }

/* Status bar */
.k-statusbar { display: flex; gap: 0.6rem; flex-wrap: wrap; align-items: center; margin-bottom: 1.5rem; }
.k-chip {
  display: inline-flex; align-items: center; gap: 0.38rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.69rem;
  padding: 0.26rem 0.72rem;
  border-radius: 20px;
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.k-chip-on  { background: rgba(0,214,143,0.08);  color: var(--accent-g); border: 1px solid rgba(0,214,143,0.18); }
.k-chip-off { background: rgba(71,85,105,0.15);   color: var(--text-3);   border: 1px solid rgba(71,85,105,0.25); }
.k-dot {
  width: 5px; height: 5px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}
.k-chip-on .k-dot { box-shadow: 0 0 5px currentColor; animation: blink 2.4s ease-in-out infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.35} }

/* Section heading */
.k-head {
  font-family: 'Titillium Web', sans-serif;
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--accent-g);
  margin: 0 0 0.8rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--border);
}

/* Glass card */
.k-card {
  background: var(--bg-glass);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  padding: 1.25rem 1.5rem;
  backdrop-filter: blur(10px);
  margin-bottom: 0.75rem;
  transition: border-color 0.18s;
}
.k-card:hover { border-color: var(--border-hi); }

/* NDVI health bar */
.ndvi-wrap { margin: 0.6rem 0 1rem; }
.ndvi-bar {
  height: 7px;
  border-radius: 4px;
  background: linear-gradient(to right,
    #0f2d4a 0%, #14532d 30%, #166534 50%, #15803d 70%, #00d68f 85%, #86efac 100%);
  position: relative;
}
.ndvi-pin {
  position: absolute;
  top: -5px;
  width: 3px; height: 17px;
  background: #fff;
  border-radius: 2px;
  box-shadow: 0 0 8px rgba(255,255,255,0.7);
  transform: translateX(-50%);
}
.ndvi-axis {
  display: flex; justify-content: space-between;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.63rem; color: var(--text-3);
  margin-top: 0.28rem;
}
.ndvi-badge {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.77rem; font-weight: 500;
  padding: 0.18rem 0.65rem;
  border-radius: 4px;
  display: inline-block;
  margin-top: 0.45rem;
}
.ndvi-healthy  { background: rgba(0,214,143,0.10); color: var(--accent-g); border: 1px solid rgba(0,214,143,0.22); }
.ndvi-moderate { background: rgba(251,191,36,0.10); color: var(--accent-a); border: 1px solid rgba(251,191,36,0.22); }
.ndvi-stressed { background: rgba(248,113,113,0.10); color: var(--accent-r); border: 1px solid rgba(248,113,113,0.22); }

/* AI badge */
.ai-badge {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.63rem;
  letter-spacing: 0.04em;
  padding: 0.13rem 0.52rem;
  border-radius: 3px;
  background: rgba(56,189,248,0.12);
  color: var(--accent-b);
  border: 1px solid rgba(56,189,248,0.25);
  display: inline-block;
  margin-left: 0.4rem;
  vertical-align: middle;
}

/* AOI status */
.aoi-card {
  background: var(--bg-glass);
  border: 1px solid var(--border);
  border-radius: var(--r);
  padding: 0.55rem 0.85rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.76rem;
  color: var(--accent-g);
  display: flex; align-items: center; gap: 0.5rem;
  margin-top: 0.7rem;
  backdrop-filter: blur(6px);
}
.aoi-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--accent-g); box-shadow: 0 0 6px var(--accent-g); flex-shrink: 0; }
.aoi-sub { color: var(--text-3); font-size: 0.68rem; }

/* Sidebar section label */
.sb-label {
  font-family: 'Titillium Web', sans-serif;
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.13em;
  text-transform: uppercase;
  color: var(--text-3);
  margin: 1.4rem 0 0.4rem;
  display: block;
}
</style>
"""


def inject_accessibility_css() -> None:
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


# ── Hero & Status ──────────────────────────────────────────────────────────────

def render_hero_header() -> None:
    st.markdown("""
<div class="k-hero">
  <div class="k-hero-wordmark">KERY<em>OS</em></div>
  <p class="k-hero-sub">Satellite Crop Verification Engine &nbsp;·&nbsp; Prevented-Sowing Claim Analysis</p>
  <div class="k-tags">
    <span class="k-tag k-tag-g">Sentinel-2 L2A</span>
    <span class="k-tag k-tag-b">Copernicus CDSE</span>
    <span class="k-tag k-tag-g">NDVI Analysis</span>
    <span class="k-tag k-tag-a">Insurance Grade</span>
    <span class="k-tag k-tag-b">Cloud Masking</span>
  </div>
</div>
""", unsafe_allow_html=True)


def render_system_status(enable_llm: bool = False, enable_narrative: bool = False) -> None:
    llm_cls  = "k-chip-on" if enable_llm       else "k-chip-off"
    llm_lbl  = "AI Validation  ON"  if enable_llm       else "AI Validation  OFF"
    nar_cls  = "k-chip-on" if enable_narrative  else "k-chip-off"
    nar_lbl  = "AI Narrative  ON"   if enable_narrative  else "AI Narrative  OFF"
    st.markdown(f"""
<div class="k-statusbar">
  <div class="k-chip k-chip-on"><span class="k-dot"></span>Sentinel Hub API</div>
  <div class="k-chip k-chip-on"><span class="k-dot"></span>Sentinel-2 L2A</div>
  <div class="k-chip {llm_cls}"><span class="k-dot"></span>{llm_lbl}</div>
  <div class="k-chip {nar_cls}"><span class="k-dot"></span>{nar_lbl}</div>
</div>
""", unsafe_allow_html=True)


# ── Results sections ───────────────────────────────────────────────────────────

def render_best_scene(report: dict) -> None:
    col1, col2 = st.columns([3, 2])
    with col1:
        st.markdown('<p class="k-head">Best Scene</p>', unsafe_allow_html=True)
        img_data = base64.b64decode(report["best_image"]["png_b64"])
        st.image(
            img_data,
            caption=f"True Colour RGB · {report['best_date']} · © Copernicus Sentinel-2",
            use_container_width=True,
        )
    with col2:
        st.markdown('<p class="k-head">Scene Metrics</p>', unsafe_allow_html=True)
        st.metric("Acquisition Date", report["best_date"])
        cloud_score = report["best_image"]["cloud_score"]
        cloud_cover = report["best_image"].get("cloud_cover")
        st.metric("Cloud Score", f"{cloud_score:.1%}")
        st.metric("Cloud Coverage", f"{cloud_cover:.1%}" if cloud_cover is not None else "—")

        llm_val = report["best_image"].get("llm_validation")
        if llm_val:
            conf     = llm_val.get("confidence", 0)
            observed = llm_val.get("observed_features", "")
            if llm_val.get("is_valid", True):
                st.markdown(
                    f'<div style="margin-top:0.85rem;padding:0.8rem;'
                    f'background:rgba(0,214,143,0.05);border:1px solid rgba(0,214,143,0.18);'
                    f'border-radius:8px;">'
                    f'<div style="display:flex;align-items:center;gap:0.4rem;margin-bottom:0.35rem;">'
                    f'<span style="width:5px;height:5px;border-radius:50%;background:#00d68f;'
                    f'box-shadow:0 0 5px #00d68f;display:inline-block;flex-shrink:0;"></span>'
                    f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.72rem;'
                    f'color:#00d68f;">AI Validated</span>'
                    f'<span class="ai-badge">Claude 3 Haiku</span></div>'
                    f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.77rem;'
                    f'color:#94a3b8;">Confidence&nbsp;<strong style="color:#00d68f;">'
                    f'{conf:.0%}</strong></span>'
                    + (
                        f'<p style="margin:0.45rem 0 0;font-size:0.78rem;color:#94a3b8;'
                        f'line-height:1.5;font-style:italic;">{observed}</p>'
                        if observed else ""
                    )
                    + '</div>',
                    unsafe_allow_html=True,
                )
            else:
                reason   = llm_val.get("reason", "Unknown issue")
                st.warning(f"AI flagged: {reason}")
                if observed:
                    st.caption(f"Observed: {observed}")

        # ── Quality card (shown only when quality metrics are present) ────────
        quality = report["best_image"].get("quality")
        if quality and quality.get("composite_score") is not None:
            _render_quality_card(quality)


def _render_quality_card(quality: dict) -> None:
    """Compact quality scorecard shown inside the scene metrics column."""
    grade     = quality.get("quality_grade", "?")
    composite = quality.get("composite_score", 0.0)
    mb        = quality.get("mean_brightness", 0.0)
    ct        = quality.get("contrast", 0.0)
    veg       = quality.get("veg_fraction", 0.0)
    clarity   = quality.get("cloud_clarity", 0.0)
    entropy   = quality.get("spatial_entropy", 0.0)

    grade_hex = {
        "A": "#00d68f", "B": "#38bdf8", "C": "#fbbf24",
        "D": "#f87171", "F": "#ef4444",
    }.get(grade, "#94a3b8")

    rejection = quality.get("rejection_reason")
    if rejection:
        st.markdown(
            f'<div style="margin-top:0.85rem;padding:0.7rem 0.85rem;'
            f'background:rgba(248,113,113,0.07);border:1px solid rgba(248,113,113,0.22);'
            f'border-radius:8px;">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.68rem;'
            f'color:#f87171;text-transform:uppercase;letter-spacing:0.05em;">Rejected</span>'
            f'<p style="margin:0.3rem 0 0;font-size:0.75rem;color:#94a3b8;">{rejection}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    # Build per-component mini bars (width as % of 80px)
    def _bar(score: float, color: str) -> str:
        w = max(2, int(score * 80))
        return (
            f'<div style="height:4px;border-radius:2px;background:rgba(255,255,255,0.08);'
            f'width:80px;overflow:hidden;display:inline-block;vertical-align:middle;">'
            f'<div style="height:100%;width:{w}px;background:{color};border-radius:2px;"></div>'
            f'</div>'
        )

    b_score  = quality.get("brightness_score", 0.0)
    ct_score = quality.get("contrast_score", 0.0)
    vg_score = quality.get("vegetation_score", 0.0)

    st.markdown(
        f'<div style="margin-top:0.85rem;padding:0.8rem;'
        f'background:rgba(0,0,0,0.18);border:1px solid var(--border);border-radius:8px;">'
        # Header: grade badge + composite %
        f'<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.6rem;">'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.63rem;'
        f'letter-spacing:0.08em;text-transform:uppercase;color:var(--text-2);">Scene Quality</span>'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:1.05rem;'
        f'font-weight:700;color:{grade_hex};">{grade}</span>'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.78rem;'
        f'color:{grade_hex};">{composite:.0%}</span>'
        f'</div>'
        # Component rows
        f'<div style="display:flex;flex-direction:column;gap:0.3rem;">'
        f'<div style="display:flex;align-items:center;justify-content:space-between;">'
        f'<span style="font-size:0.71rem;color:var(--text-2);min-width:80px;">Cloud clarity</span>'
        f'{_bar(clarity, "#00d68f")}'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.68rem;'
        f'color:var(--text-1);min-width:36px;text-align:right;">{clarity:.0%}</span>'
        f'</div>'
        f'<div style="display:flex;align-items:center;justify-content:space-between;">'
        f'<span style="font-size:0.71rem;color:var(--text-2);min-width:80px;">Spatial detail</span>'
        f'{_bar(ct_score, "#38bdf8")}'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.68rem;'
        f'color:var(--text-1);min-width:36px;text-align:right;">{ct:.0f}</span>'
        f'</div>'
        f'<div style="display:flex;align-items:center;justify-content:space-between;">'
        f'<span style="font-size:0.71rem;color:var(--text-2);min-width:80px;">Brightness</span>'
        f'{_bar(b_score, "#fbbf24")}'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.68rem;'
        f'color:var(--text-1);min-width:36px;text-align:right;">{mb:.0f}</span>'
        f'</div>'
        f'<div style="display:flex;align-items:center;justify-content:space-between;">'
        f'<span style="font-size:0.71rem;color:var(--text-2);min-width:80px;">Vegetation</span>'
        f'{_bar(vg_score, "#4ade80")}'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.68rem;'
        f'color:var(--text-1);min-width:36px;text-align:right;">{veg:.0%}</span>'
        f'</div>'
        f'<div style="display:flex;align-items:center;justify-content:space-between;">'
        f'<span style="font-size:0.71rem;color:var(--text-2);min-width:80px;">Entropy</span>'
        f'{_bar(min(1.0, entropy / 5.5), "#a78bfa")}'
        f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.68rem;'
        f'color:var(--text-1);min-width:36px;text-align:right;">{entropy:.2f}</span>'
        f'</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )


def _ndvi_health(mean: float) -> tuple[str, str]:
    if mean >= 0.4:
        return "Healthy Vegetation", "ndvi-healthy"
    if mean >= 0.2:
        return "Moderate Stress", "ndvi-moderate"
    return "Severe Stress / Bare Soil", "ndvi-stressed"


def render_ndvi_section(report: dict) -> None:
    st.markdown('<p class="k-head">NDVI Analysis</p>', unsafe_allow_html=True)

    pooled = report.get("pooled_stats")
    if pooled:
        mean_val = pooled["mean"]
        health_label, health_cls = _ndvi_health(mean_val)
        pct = max(0.0, min(1.0, (mean_val + 1) / 2)) * 100

        c1, c2, c3 = st.columns(3)
        c1.metric("Composite Mean NDVI", f"{mean_val:.3f}")
        c2.metric("Satellite Passes", str(pooled["passes"]))
        c3.metric("Pooled Std Dev", f"{pooled['stDev']:.3f}")

        st.markdown(f"""
<div class="ndvi-wrap">
  <div class="ndvi-bar">
    <div class="ndvi-pin" style="left:{pct:.1f}%;"></div>
  </div>
  <div class="ndvi-axis"><span>−1  bare soil</span><span>0</span><span>+1  dense vegetation</span></div>
  <span class="ndvi-badge {health_cls}">{health_label}</span>
  <span style="font-family:'JetBrains Mono',monospace;font-size:0.68rem;color:#475569;margin-left:0.8rem;">
    {pooled['totalPixels']:,} valid pixels &nbsp;·&nbsp; {pooled['passes']} passes
  </span>
</div>
""", unsafe_allow_html=True)
    else:
        st.warning(COMPOSITE_UNAVAILABLE)

    st.markdown("---")
    st.markdown(
        '<p style="font-size:0.78rem;color:#94a3b8;margin:0 0 0.6rem;">'
        'Per-date snapshot '
        '<span style="color:#475569;">'
        '— single scene; see composite above for field-level statistics'
        '</span></p>',
        unsafe_allow_html=True,
    )

    ndvi_stats = report.get("ndvi_stats")
    if ndvi_stats:
        stats_data = safe_extract_stats(ndvi_stats)
        if stats_data is None:
            ndvi_raw = ndvi_stats if isinstance(ndvi_stats, dict) else {}
            if "error" in ndvi_raw:
                st.warning(NDVI_API_ERROR.format(
                    status=ndvi_raw.get("status", "?"),
                    detail=str(ndvi_raw.get("error", "unknown"))[:300],
                ))
            elif ndvi_raw.get("data") == []:
                st.info(f"ℹ️ {NDVI_NO_PIXELS}")
            else:
                st.warning(NDVI_UNAVAILABLE)
        else:
            col1, col2, col3 = st.columns(3)
            col1.metric("Mean NDVI", f"{float(stats_data['mean']):.3f}")
            pct_data = stats_data.get("percentiles") or {}
            p50 = pct_data.get("50.0")
            col2.metric("Median NDVI", f"{float(p50):.3f}" if p50 is not None else "—")
            _std = stats_data.get("stDev", stats_data.get("std"))
            col3.metric("Std Dev", f"{float(_std):.3f}" if _std is not None else "—")

            if pct_data:
                with st.expander("NDVI Percentile Breakdown"):
                    st.table({
                        "Percentile": ["25th", "50th (Median)", "75th"],
                        "NDVI Value": [
                            f"{float(pct_data.get('25.0', 0)):.3f}",
                            f"{float(pct_data.get('50.0', 0)):.3f}",
                            f"{float(pct_data.get('75.0', 0)):.3f}",
                        ],
                    })


def render_alternatives(report: dict) -> None:
    alts = report.get("alternatives") or []
    if not alts:
        return
    with st.expander(f"Alternative Scenes  ({len(alts)} available)"):
        st.markdown('<p class="k-head">Alternative Acquisitions</p>', unsafe_allow_html=True)
        for idx, alt in enumerate(alts, 1):
            col1, col2 = st.columns([3, 2])
            with col1:
                alt_img = base64.b64decode(alt["png_b64"])
                st.image(
                    alt_img,
                    caption=f"Scene {idx} · {alt['date']} · © Copernicus Sentinel-2",
                    use_container_width=True,
                )
            with col2:
                st.metric("Date", alt["date"])
                st.metric("Cloud Score", f"{alt['cloud_score']:.1%}")
            if idx < len(alts):
                st.markdown("---")


def render_ai_narrative(report: dict) -> None:
    assessment = report.get("ai_assessment")
    legacy_text = report.get("ai_narrative", "")

    if not assessment and not legacy_text:
        return

    st.markdown('<p class="k-head">AI Geospatial Assessment</p>', unsafe_allow_html=True)

    if assessment:
        is_fallback = assessment.get("fallback", False)
        model_lbl = "Deterministic fallback" if is_fallback else "Claude 3.5 Sonnet · Vertex AI"
        fallback_badge = (
            '<span class="k-chip k-chip-off" style="font-size:0.62rem;padding:0.13rem 0.5rem;">'
            'Fallback</span>'
            if is_fallback else ""
        )

        st.markdown(
            f'<div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.75rem;">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.65rem;'
            f'letter-spacing:0.06em;color:var(--text-2);text-transform:uppercase;">'
            f'AI Assessment</span>'
            f'<span class="ai-badge">{model_lbl}</span>{fallback_badge}</div>',
            unsafe_allow_html=True,
        )

        # ── Executive summary ─────────────────────────────────────────────────
        exec_s = assessment.get("executive_summary", "")
        if exec_s:
            st.markdown(
                f'<div class="k-card" style="border-left:3px solid var(--accent-g);">'
                f'<div style="font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;'
                f'color:var(--text-2);margin-bottom:0.45rem;font-family:\'JetBrains Mono\',monospace;">'
                f'Executive Summary</div>'
                f'<p style="margin:0;font-size:0.95rem;line-height:1.7;color:var(--text-1);">'
                f'{exec_s}</p></div>',
                unsafe_allow_html=True,
            )

        # ── Technical + Insurance columns ─────────────────────────────────────
        col_t, col_i = st.columns(2)
        with col_t:
            tech = assessment.get("technical_analysis", "")
            if tech:
                st.markdown(
                    f'<div class="k-card">'
                    f'<div style="font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;'
                    f'color:var(--accent-b);margin-bottom:0.4rem;'
                    f'font-family:\'JetBrains Mono\',monospace;">Technical Analysis</div>'
                    f'<p style="margin:0;font-size:0.84rem;line-height:1.65;color:var(--text-1);">'
                    f'{tech}</p></div>',
                    unsafe_allow_html=True,
                )
        with col_i:
            ins = assessment.get("insurance_interpretation", "")
            if ins:
                st.markdown(
                    f'<div class="k-card">'
                    f'<div style="font-size:0.62rem;letter-spacing:0.08em;text-transform:uppercase;'
                    f'color:var(--accent-a);margin-bottom:0.4rem;'
                    f'font-family:\'JetBrains Mono\',monospace;">Insurance Interpretation</div>'
                    f'<p style="margin:0;font-size:0.84rem;line-height:1.65;color:var(--text-1);">'
                    f'{ins}</p></div>',
                    unsafe_allow_html=True,
                )

        # ── Confidence explanation bar ────────────────────────────────────────
        conf_exp = assessment.get("confidence_explanation", "")
        if conf_exp:
            st.markdown(
                f'<div style="padding:0.5rem 0.85rem;background:rgba(0,214,143,0.04);'
                f'border:1px solid var(--border);border-radius:var(--r);margin:0.5rem 0;">'
                f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.63rem;'
                f'letter-spacing:0.06em;color:var(--accent-g);text-transform:uppercase;'
                f'margin-right:0.5rem;">Confidence Basis</span>'
                f'<span style="font-size:0.83rem;color:var(--text-2);">{conf_exp}</span></div>',
                unsafe_allow_html=True,
            )

        # ── Caveats + grounding flags in expanders ────────────────────────────
        caveats = assessment.get("caveats") or []
        flags   = assessment.get("grounding_flags") or []

        if caveats or flags:
            with st.expander("Caveats & Evidence Trail"):
                if caveats:
                    st.markdown(
                        '<p style="font-size:0.65rem;letter-spacing:0.08em;text-transform:uppercase;'
                        'color:var(--text-3);margin:0 0 0.4rem;'
                        'font-family:\'JetBrains Mono\',monospace;">Caveats</p>',
                        unsafe_allow_html=True,
                    )
                    for cav in caveats:
                        st.markdown(
                            f'<p style="font-size:0.82rem;color:var(--text-2);margin:0.1rem 0;">• {cav}</p>',
                            unsafe_allow_html=True,
                        )
                if flags and not is_fallback:
                    st.markdown(
                        '<p style="font-size:0.65rem;letter-spacing:0.08em;text-transform:uppercase;'
                        'color:var(--text-3);margin:0.75rem 0 0.4rem;'
                        'font-family:\'JetBrains Mono\',monospace;">Metrics cited</p>',
                        unsafe_allow_html=True,
                    )
                    flags_html = "".join(
                        f'<span class="k-tag k-tag-b" style="font-size:0.6rem;">{f}</span>'
                        for f in flags
                    )
                    st.markdown(
                        f'<div style="display:flex;gap:0.3rem;flex-wrap:wrap;">{flags_html}</div>',
                        unsafe_allow_html=True,
                    )
    else:
        # Legacy plain-string path
        st.markdown(
            f'<div class="k-card">'
            f'<div style="margin-bottom:0.5rem;display:flex;align-items:center;gap:0.4rem;">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.65rem;'
            f'letter-spacing:0.06em;color:var(--text-2);text-transform:uppercase;">'
            f'Assessment</span><span class="ai-badge">Claude 3.5 Sonnet · Vertex AI</span></div>'
            f'<p style="margin:0;font-size:0.95rem;line-height:1.7;color:var(--text-1);">'
            f'{legacy_text}</p></div>',
            unsafe_allow_html=True,
        )


def render_latency(elapsed_seconds: float) -> None:
    with st.expander("Performance Diagnostics"):
        st.markdown('<p class="k-head">Pipeline Metrics</p>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        c1.metric("Total Pipeline Time", f"{elapsed_seconds:.1f} s")
        c2.metric("Status", "Complete")
        if elapsed_seconds > 60:
            st.caption("Tip: large AOIs or wide date ranges increase processing time.")


def render_pdf_buttons(report: dict, aoi_geojson: dict | None) -> None:
    from utils.pdf_generator import (
        generate_appendix_pdf,
        generate_summary_pdf,
        generate_verification_pdf,
    )

    st.markdown("---")
    st.markdown('<p class="k-head">Export Report</p>', unsafe_allow_html=True)
    col_full, col_summary, col_appendix = st.columns(3)

    with col_full:
        if st.button("Generate Full PDF Report"):
            with st.spinner("Compiling full report…"):
                try:
                    pdf_bytes = generate_verification_pdf(report, aoi_geojson)
                    st.download_button(
                        label="⬇  Download Full Report",
                        data=pdf_bytes,
                        file_name=f"keryos_full_{report['best_date']}.pdf",
                        mime="application/pdf",
                    )
                    st.success("Full PDF ready for download.")
                except Exception as exc:
                    st.error(f"PDF generation failed: {exc}")

    with col_summary:
        if st.button("Generate 1-Page Summary"):
            with st.spinner("Compiling summary…"):
                try:
                    summary_bytes = generate_summary_pdf(report)
                    st.download_button(
                        label="⬇  Download Summary",
                        data=summary_bytes,
                        file_name=f"keryos_summary_{report['best_date']}.pdf",
                        mime="application/pdf",
                    )
                    st.success("Summary PDF ready.")
                except Exception as exc:
                    st.error(f"Summary generation failed: {exc}")

    with col_appendix:
        if st.button("Technical Appendix"):
            with st.spinner("Compiling technical appendix…"):
                try:
                    appendix_bytes = generate_appendix_pdf(report)
                    st.download_button(
                        label="⬇  Download Appendix",
                        data=appendix_bytes,
                        file_name=f"keryos_appendix_{report.get('best_date', 'report')}.pdf",
                        mime="application/pdf",
                    )
                    st.success("Technical appendix ready.")
                except Exception as exc:
                    st.error(f"Appendix generation failed: {exc}")


def render_faq() -> None:
    with st.expander("Help & FAQ"):
        st.markdown("""
**What is AOI (Area of Interest)?**
Draw a polygon on the map enclosing the farm field you want to verify.
The polygon must cover at least 1 hectare and no more than 50 000 km².

**What is NDVI?**
Normalised Difference Vegetation Index — a measure of plant greenness derived
from Sentinel-2 bands. Values range from −1 (water / bare soil) to +1 (dense
healthy vegetation). For Kharif paddy at transplanting stage, healthy crops
typically show NDVI > 0.4.

**Why does the sowing window matter?**
Sentinel Hub returns imagery from within your chosen date range. A wider window
increases the chance of finding a cloud-free scene, but use at most the actual
sowing season (typically 30–90 days) for accurate results.

**What are the AI features?**
*AI Image Validation* uses Claude 3 Haiku to check that the satellite image is
usable (not mostly cloud or black). *AI Narrative* uses Claude 3.5 Sonnet to
generate a professional 2–3 sentence assessment. Both require GCP Vertex AI
credentials and are disabled by default.

**What does Composite Mean NDVI mean?**
A weighted average of NDVI across all valid satellite passes in your date window,
pooling thousands of pixels. More reliable than a single-date snapshot because
individual scenes may be partially clouded.

**Why is Pooled Std Dev more useful than per-date Std Dev?**
Each daily scene may have very few clear pixels (sampleCount = 1) after cloud
masking, making its std dev meaningless. The pooled value combines variance
across all passes, giving a true picture of within-field variability.
        """)


# ═══════════════════════════════════════════════════════════════════════════════
#  Academic / Methodology tab functions
# ═══════════════════════════════════════════════════════════════════════════════

def _md_section(title: str, body: str) -> None:
    """Render a styled section heading and markdown body."""
    st.markdown(
        f'<p class="k-head">{title}</p>',
        unsafe_allow_html=True,
    )
    st.markdown(body)


def render_methodology_tab() -> None:
    """Full methodology documentation panel for the Methodology tab."""
    from utils.academic_content import (
        CONFIDENCE_METHODOLOGY,
        NDVI_THEORY,
        PROBLEM_STATEMENT,
        PROJECT_SUBTITLE,
        QUALITY_SCORING_METHODOLOGY,
        SENTINEL2_RATIONALE,
    )

    st.markdown(
        f'<p style="font-size:0.88rem;color:var(--text-2);margin-bottom:1.2rem;">'
        f'{PROJECT_SUBTITLE}</p>',
        unsafe_allow_html=True,
    )

    # Problem statement
    with st.expander("Research Context & Problem Statement", expanded=True):
        st.markdown(PROBLEM_STATEMENT)

    # Sentinel-2 rationale
    with st.expander("Data Source: Why Sentinel-2?", expanded=False):
        st.markdown(SENTINEL2_RATIONALE)
        _render_band_table()

    # NDVI theory
    with st.expander("Vegetation Index: NDVI — Theory & Interpretation", expanded=False):
        st.markdown(NDVI_THEORY)
        _render_ndvi_reference_card()

    # Quality scoring
    with st.expander("Image Quality Scoring Methodology", expanded=False):
        st.markdown(QUALITY_SCORING_METHODOLOGY)

    # Confidence methodology
    with st.expander("Confidence Score Methodology", expanded=False):
        st.markdown(CONFIDENCE_METHODOLOGY)


def _render_band_table() -> None:
    from utils.academic_content import SENTINEL2_BANDS
    st.markdown('<p class="k-head" style="margin-top:0.75rem;">Sentinel-2 Bands Used in Keryos</p>',
                unsafe_allow_html=True)
    rows = "".join(
        f'<tr>'
        f'<td style="font-family:\'JetBrains Mono\',monospace;color:#38bdf8;">{band}</td>'
        f'<td style="color:var(--text-2);">{info["name"]}</td>'
        f'<td style="font-family:\'JetBrains Mono\',monospace;color:var(--text-1);">'
        f'{info["wavelength_nm"]} nm</td>'
        f'<td style="font-family:\'JetBrains Mono\',monospace;color:#00d68f;">'
        f'{info["resolution_m"]} m</td>'
        f'</tr>'
        for band, info in SENTINEL2_BANDS.items()
    )
    st.markdown(
        f'<table style="width:100%;border-collapse:collapse;font-size:0.82rem;">'
        f'<thead><tr style="background:rgba(0,0,0,0.3);">'
        f'<th style="padding:0.4rem 0.6rem;text-align:left;color:var(--text-2);">Band</th>'
        f'<th style="padding:0.4rem 0.6rem;text-align:left;color:var(--text-2);">Name</th>'
        f'<th style="padding:0.4rem 0.6rem;text-align:left;color:var(--text-2);">Wavelength</th>'
        f'<th style="padding:0.4rem 0.6rem;text-align:left;color:var(--text-2);">Resolution</th>'
        f'</tr></thead>'
        f'<tbody>{rows}</tbody></table>',
        unsafe_allow_html=True,
    )


def _render_ndvi_reference_card() -> None:
    """Compact NDVI interpretation scale."""
    st.markdown('<p class="k-head" style="margin-top:0.75rem;">NDVI Interpretation Scale</p>',
                unsafe_allow_html=True)
    rows_data = [
        ("-1.0 to 0.0", "Water, deep shadow", "#38bdf8", "0%"),
        ("0.0 to 0.1",  "Bare rock, sand, snow", "#94a3b8", "5%"),
        ("0.1 to 0.2",  "Sparse / degraded vegetation", "#fbbf24", "15%"),
        ("0.2 to 0.4",  "Moderate stress — early crop or sparse cover", "#f97316", "30%"),
        ("0.4 to 0.6",  "Moderate–good crop cover — paddy tillering", "#4ade80", "65%"),
        ("0.6 to 1.0",  "Dense healthy vegetation", "#00d68f", "100%"),
    ]
    rows_html = ""
    for rng, interp, color, bar_w in rows_data:
        rows_html += (
            f'<tr>'
            f'<td style="font-family:\'JetBrains Mono\',monospace;color:{color};'
            f'padding:0.3rem 0.6rem;">{rng}</td>'
            f'<td style="color:var(--text-1);padding:0.3rem 0.6rem;">{interp}</td>'
            f'<td style="padding:0.3rem 0.6rem;">'
            f'<div style="height:6px;border-radius:3px;background:rgba(255,255,255,0.08);width:120px;">'
            f'<div style="height:100%;width:{bar_w};background:{color};border-radius:3px;"></div>'
            f'</div></td>'
            f'</tr>'
        )
    st.markdown(
        f'<table style="width:100%;border-collapse:collapse;font-size:0.82rem;">'
        f'<thead><tr style="background:rgba(0,0,0,0.3);">'
        f'<th style="padding:0.4rem 0.6rem;text-align:left;color:var(--text-2);">NDVI Range</th>'
        f'<th style="padding:0.4rem 0.6rem;text-align:left;color:var(--text-2);">Interpretation</th>'
        f'<th style="padding:0.4rem 0.6rem;text-align:left;color:var(--text-2);">Level</th>'
        f'</tr></thead><tbody>{rows_html}</tbody></table>',
        unsafe_allow_html=True,
    )


def render_pipeline_diagram() -> None:
    """Render the ASCII processing pipeline diagram."""
    from utils.academic_content import PIPELINE_DIAGRAM
    st.markdown('<p class="k-head">Processing Pipeline</p>', unsafe_allow_html=True)
    st.code(PIPELINE_DIAGRAM, language=None)


def render_architecture_tab() -> None:
    """System architecture and software engineering notes."""
    from utils.academic_content import (
        ARCHITECTURE_OVERVIEW,
        SOFTWARE_ENGINEERING_NOTES,
    )
    with st.expander("System Architecture", expanded=True):
        st.markdown(ARCHITECTURE_OVERVIEW)
    with st.expander("Software Engineering Practices", expanded=False):
        st.markdown(SOFTWARE_ENGINEERING_NOTES)


def render_limitations_tab() -> None:
    """Remote sensing and AI limitations panel."""
    from utils.academic_content import AI_LIMITATIONS, REMOTE_SENSING_LIMITATIONS

    with st.expander("Remote Sensing Limitations", expanded=True):
        st.markdown(REMOTE_SENSING_LIMITATIONS)

    with st.expander("AI Reasoning Layer — Limitations", expanded=False):
        st.markdown(AI_LIMITATIONS)


def render_future_work_tab() -> None:
    """Future scalability and research directions."""
    from utils.academic_content import FUTURE_WORK
    with st.expander("Future Scalability & Research Directions", expanded=True):
        st.markdown(FUTURE_WORK)


def render_references_tab() -> None:
    """Academic references panel."""
    from utils.academic_content import REFERENCES
    st.markdown('<p class="k-head">Academic References</p>', unsafe_allow_html=True)
    for ref in REFERENCES:
        st.markdown(
            f'<div style="padding:0.55rem 0.85rem;border:1px solid var(--border);'
            f'border-radius:var(--r);margin-bottom:0.5rem;background:var(--bg-glass);">'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.65rem;'
            f'color:var(--accent-b);margin-bottom:0.2rem;">[{ref["key"]}]</div>'
            f'<p style="margin:0 0 0.2rem;font-size:0.82rem;color:var(--text-1);">'
            f'{ref["citation"]}</p>'
            f'<span style="font-size:0.72rem;color:var(--text-3);">{ref["relevance"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


def render_reproducibility_panel(report: dict) -> None:
    """
    Full reproducibility panel: all pipeline parameters, thresholds, and
    scoring weights embedded in the report.  Makes the analysis reproducible.
    """
    proc = report.get("processing_metadata") or {}
    params = proc.get("pipeline_parameters") or {}
    thresholds = proc.get("quality_thresholds") or {}
    weights = proc.get("scoring_weights") or {}
    ndvi_class = proc.get("ndvi_classification") or {}

    st.markdown('<p class="k-head">Reproducibility Record</p>', unsafe_allow_html=True)
    st.caption(
        "All parameters that determine the output of this analysis. "
        "Reproducing an identical run requires the same AOI, date range, crop type, "
        "and these parameter values."
    )

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Pipeline Parameters**")
        if params:
            for k, v in params.items():
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;'
                    f'padding:0.2rem 0;border-bottom:1px solid var(--border);">'
                    f'<span style="font-size:0.78rem;color:var(--text-2);">{k}</span>'
                    f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.78rem;'
                    f'color:var(--text-1);">{v}</span></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("Parameters not available in this report version.")

        st.markdown("**Quality Thresholds**")
        if thresholds:
            for k, v in thresholds.items():
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;'
                    f'padding:0.2rem 0;border-bottom:1px solid var(--border);">'
                    f'<span style="font-size:0.78rem;color:var(--text-2);">{k}</span>'
                    f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.78rem;'
                    f'color:#fbbf24;">{v}</span></div>',
                    unsafe_allow_html=True,
                )

    with c2:
        st.markdown("**Scoring Weights**")
        if weights:
            for k, v in weights.items():
                pct = f"{float(v):.0%}" if isinstance(v, (int, float)) else str(v)
                bar_w = int(float(v) * 120) if isinstance(v, (int, float)) else 0
                st.markdown(
                    f'<div style="margin-bottom:0.4rem;">'
                    f'<div style="display:flex;justify-content:space-between;margin-bottom:0.15rem;">'
                    f'<span style="font-size:0.78rem;color:var(--text-2);">{k}</span>'
                    f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.78rem;'
                    f'color:#00d68f;">{pct}</span></div>'
                    f'<div style="height:4px;border-radius:2px;background:rgba(255,255,255,0.06);'
                    f'width:100%;overflow:hidden;">'
                    f'<div style="height:100%;width:{bar_w}px;background:#00d68f;'
                    f'border-radius:2px;"></div></div></div>',
                    unsafe_allow_html=True,
                )

        st.markdown("**NDVI Classification**")
        if ndvi_class:
            for k, v in ndvi_class.items():
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;'
                    f'padding:0.2rem 0;border-bottom:1px solid var(--border);">'
                    f'<span style="font-size:0.78rem;color:var(--text-2);">{k}</span>'
                    f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.75rem;'
                    f'color:var(--text-1);">{v}</span></div>',
                    unsafe_allow_html=True,
                )

    # Processing steps log
    steps = proc.get("pipeline_steps") or []
    if steps:
        st.markdown("**Pipeline Steps Executed**")
        for i, step in enumerate(steps, 1):
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:0.5rem;'
                f'padding:0.2rem 0;border-bottom:1px solid var(--border);">'
                f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.65rem;'
                f'color:#00d68f;min-width:20px;">{i:02d}</span>'
                f'<span style="font-size:0.78rem;color:var(--text-2);">{step}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ── New academic render functions ──────────────────────────────────────────────

def render_research_questions() -> None:
    """Display the four research questions with motivation and approach."""
    from utils.academic_content import RESEARCH_QUESTIONS

    st.markdown('<p class="k-head">Research Questions</p>', unsafe_allow_html=True)
    st.caption(
        "These questions frame the academic contribution of the project "
        "and guide the design of each system component."
    )

    for rq in RESEARCH_QUESTIONS:
        num   = rq["number"]
        q     = rq["question"]
        motiv = rq["motivation"]
        appr  = rq["approach"]

        st.markdown(
            f'<div class="k-card" style="margin-bottom:0.75rem;">'
            f'<div style="display:flex;align-items:flex-start;gap:0.65rem;">'
            f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.9rem;'
            f'font-weight:700;color:#00d68f;flex-shrink:0;padding-top:0.05rem;">{num}</span>'
            f'<div>'
            f'<p style="margin:0 0 0.45rem;font-size:0.93rem;font-weight:600;'
            f'color:var(--text-1);line-height:1.5;">{q}</p>'
            f'<p style="margin:0 0 0.25rem;font-size:0.8rem;color:var(--text-2);">'
            f'<strong style="color:#38bdf8;">Motivation:</strong> {motiv}</p>'
            f'<p style="margin:0;font-size:0.8rem;color:var(--text-2);">'
            f'<strong style="color:#4ade80;">Approach:</strong> {appr}</p>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )


def render_visual_pipeline() -> None:
    """
    Visual step-by-step pipeline diagram using Streamlit components.
    Replaces the ASCII-only view with an interactive card layout.
    """
    st.markdown('<p class="k-head">Processing Pipeline — Visual View</p>',
                unsafe_allow_html=True)

    phases = [
        {
            "num": "01", "name": "Input Validation",
            "color": "#38bdf8",
            "steps": ["WGS84 coordinate bounds check", "Area: 0.01–50,000 km²",
                      "Date range: 5–365 days, no future dates"],
            "params": "validate_aoi() · geojson_utils.py",
        },
        {
            "num": "02", "name": "Scene Discovery",
            "color": "#00d68f",
            "steps": ["Sentinel Hub Catalog API query",
                      "Filter: eo:cloud_cover < 90%",
                      "De-duplicate by calendar date",
                      "Sort by catalog cloud cover ascending"],
            "params": "catalog_limit=100 · max_cloud=90%",
        },
        {
            "num": "03", "name": "Phase 1: SCL Probe  (parallel)",
            "color": "#00d68f",
            "steps": ["Fetch 128×128 SCL thumbnail per candidate",
                      "Decode: class = round(red_channel / 255 × 11)",
                      "Cloud fraction from classes {1, 3, 8, 9, 10}",
                      "Sort by cloud_score ascending"],
            "params": "probe_px=128 · 6 workers · top 12 candidates",
        },
        {
            "num": "04", "name": "Phase 2: Full-Res Fetch  (parallel)",
            "color": "#00d68f",
            "steps": ["Fetch 512×512 true-colour PNG",
                      "Brightness gate: mean luminance ≥ 10",
                      "Image quality analysis (8 metrics)",
                      "Composite scoring (cloud 40% + contrast 25% + brightness 15% + veg 20%)",
                      "Hard-reject filter",
                      "[Optional] Claude 3 Haiku validation",
                      "Fetch 512×512 SWIR PNG"],
            "params": "full_px=512 · 4 workers · top 6 probed",
        },
        {
            "num": "05", "name": "NDVI Statistics",
            "color": "#a78bfa",
            "steps": ["Statistics API: per-day NDVI (best date)",
                      "Statistics API: range NDVI (full window, P1D intervals)",
                      "Cloud mask: SCL classes 8, 9, 10 excluded",
                      "Percentiles: P10, P25, P50, P75, P90"],
            "params": "resx=20 m · resy=20 m · evalscript NDVI_SCL_MASK",
        },
        {
            "num": "06", "name": "Pooled Composite",
            "color": "#a78bfa",
            "steps": ["Weighted mean: Σ(mᵢ·nᵢ) / Σnᵢ",
                      "Pooled variance: Σ((σᵢ²+mᵢ²)·nᵢ)/Σnᵢ − μ²",
                      "Skip NaN or zero-count intervals",
                      "Record passes count + total pixels"],
            "params": "weight = sampleCount per interval",
        },
        {
            "num": "07", "name": "Deterministic Interpretation",
            "color": "#fbbf24",
            "steps": ["NDVI health class (≥ 0.40 / 0.20–0.39 / < 0.20)",
                      "Confidence score (cloud 55% + temporal 35% + AI 10%)",
                      "Claim signal + recommendation generation",
                      "AOI metadata (area, centroid, hash)"],
            "params": "thresholds: 0.40 healthy · 0.20 moderate",
        },
        {
            "num": "08", "name": "[Optional] AI Narrative",
            "color": "#f87171",
            "steps": ["Evidence pack injected verbatim into prompt",
                      "System prompt: 8 grounding rules enforced",
                      "Structured JSON output (6 sections)",
                      "Deterministic fallback on any failure"],
            "params": "Claude 3.5 Sonnet · Vertex AI · max_tokens=800",
        },
        {
            "num": "09", "name": "Report Assembly",
            "color": "#38bdf8",
            "steps": ["All deterministic + AI fields merged",
                      "Reproducibility parameters embedded",
                      "Integrity hash (SHA-256) computed",
                      "UI render · PDF export · JSON metadata"],
            "params": "report_bundle.py → UI / PDF generator",
        },
    ]

    for phase in phases:
        steps_html = "".join(
            f'<li style="font-size:0.78rem;color:var(--text-2);margin:0.1rem 0;">{s}</li>'
            for s in phase["steps"]
        )
        st.markdown(
            f'<div style="display:flex;gap:0.75rem;margin-bottom:0.6rem;">'
            f'<div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0;">'
            f'<div style="width:34px;height:34px;border-radius:50%;background:{phase["color"]}20;'
            f'border:2px solid {phase["color"]};display:flex;align-items:center;'
            f'justify-content:center;font-family:\'JetBrains Mono\',monospace;'
            f'font-size:0.65rem;font-weight:700;color:{phase["color"]};">{phase["num"]}</div>'
            f'<div style="width:2px;flex:1;background:rgba(255,255,255,0.05);'
            f'margin:0.2rem 0;min-height:10px;"></div></div>'
            f'<div style="flex:1;background:var(--bg-glass);border:1px solid var(--border);'
            f'border-left:3px solid {phase["color"]};border-radius:var(--r);'
            f'padding:0.65rem 0.9rem;margin-bottom:0;">'
            f'<div style="font-weight:700;font-size:0.88rem;color:var(--text-1);'
            f'margin-bottom:0.3rem;">{phase["name"]}</div>'
            f'<ul style="margin:0 0 0.35rem 1rem;padding:0;">{steps_html}</ul>'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:0.65rem;'
            f'color:{phase["color"]};opacity:0.7;">{phase["params"]}</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )


def render_evaluation_framework() -> None:
    """Evaluation design and validation methodology."""
    from utils.academic_content import EVALUATION_FRAMEWORK

    st.markdown('<p class="k-head">Evaluation Framework</p>', unsafe_allow_html=True)
    st.info(
        "This section describes how the system *would* be evaluated "
        "with a labelled ground-truth dataset.  Formal validation is proposed "
        "as future work requiring industry data partnerships."
    )
    st.markdown(EVALUATION_FRAMEWORK)


def render_design_decisions() -> None:
    """Technology design decisions log."""
    from utils.academic_content import DESIGN_DECISIONS

    st.markdown('<p class="k-head">Design Decisions</p>', unsafe_allow_html=True)
    st.caption(
        "Each decision below was made deliberately. Being able to articulate "
        "trade-offs is a key marker of engineering maturity."
    )

    for dd in DESIGN_DECISIONS:
        with st.expander(dd["decision"]):
            st.markdown(
                f'<p style="font-size:0.85rem;color:var(--text-1);margin-bottom:0.5rem;">'
                f'{dd["rationale"]}</p>'
                f'<div style="padding:0.45rem 0.75rem;background:rgba(251,191,36,0.06);'
                f'border-left:3px solid #fbbf24;border-radius:4px;'
                f'font-size:0.78rem;color:#fbbf24;">'
                f'<strong>Trade-off:</strong> {dd["trade_off"]}</div>',
                unsafe_allow_html=True,
            )


def render_comparison_table() -> None:
    """Comparison with alternative remote sensing data sources."""
    from utils.academic_content import COMPARISON_WITH_ALTERNATIVES

    st.markdown('<p class="k-head">Comparison with Alternative Approaches</p>',
                unsafe_allow_html=True)

    header_cols = ["Approach", "Resolution", "Revisit", "Cost", "Cloud-immune", "Scalability", "Objectivity"]
    col_keys    = ["approach", "spatial_res", "temporal_res", "cost", "cloud_immunity", "scalability", "objectivity"]

    header_html = "".join(
        f'<th style="padding:0.4rem 0.6rem;text-align:left;color:var(--text-2);'
        f'font-size:0.72rem;letter-spacing:0.05em;text-transform:uppercase;'
        f'background:var(--bg-2);">{h}</th>'
        for h in header_cols
    )

    rows_html = ""
    for row in COMPARISON_WITH_ALTERNATIVES:
        is_selected = row["approach"].startswith("Sentinel-2")
        bg = "rgba(0,214,143,0.05)" if is_selected else "transparent"
        border_left = "border-left:3px solid #00d68f;" if is_selected else ""
        cells = "".join(
            f'<td style="padding:0.35rem 0.6rem;font-size:0.78rem;'
            f'color:{"#00d68f" if is_selected else "var(--text-1)"};">'
            f'{row.get(k, "")}</td>'
            for k in col_keys
        )
        rows_html += (
            f'<tr style="background:{bg};{border_left}">'
            f'{cells}'
            f'<td style="padding:0.35rem 0.6rem;font-size:0.72rem;'
            f'color:var(--text-3);font-style:italic;">'
            f'{row.get("why_not", "")}</td></tr>'
        )

    # Add "Reason" header
    header_html += (
        f'<th style="padding:0.4rem 0.6rem;text-align:left;color:var(--text-2);'
        f'font-size:0.72rem;letter-spacing:0.05em;text-transform:uppercase;'
        f'background:var(--bg-2);">Decision</th>'
    )

    st.markdown(
        f'<div style="overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:0.82rem;">'
        f'<thead><tr>{header_html}</tr></thead>'
        f'<tbody>{rows_html}</tbody></table></div>',
        unsafe_allow_html=True,
    )
