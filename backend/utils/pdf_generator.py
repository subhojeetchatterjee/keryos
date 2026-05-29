import base64
import hashlib
import io
import json
import logging
from datetime import datetime
from typing import Any, cast

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from agents.tools.stats_utils import safe_extract_stats

_log = logging.getLogger(__name__)

# ── Color palette ──────────────────────────────────────────────────────────────
_NAVY = HexColor("#0d2137")
_NAVY_DEEP = HexColor("#080f1c")  # cover background
_TEAL = HexColor("#0e6e70")
_TEAL_BRIGHT = HexColor("#0d9488")  # section header accent
_TEAL_L = HexColor("#e0f5f5")
_LIGHT_BLUE = HexColor("#eff6ff")  # section header bg
_GRAY_L = HexColor("#f8fafc")
_GRAY_M = HexColor("#e2e8f0")
_GRAY_D = HexColor("#94a3b8")
_TEXT = HexColor("#1e293b")
_MUTED = HexColor("#64748b")
_GREEN = HexColor("#15803d")
_GREEN_L = HexColor("#dcfce7")
_GREEN_D = HexColor("#065f46")  # verdict dark green
_AMBER = HexColor("#b45309")
_AMBER_L = HexColor("#fef9c3")
_AMBER_D = HexColor("#92400e")  # verdict dark amber
_RED = HexColor("#b91c1c")
_RED_L = HexColor("#fee2e2")
_RED_D = HexColor("#7f1d1d")  # verdict dark red
_WHITE = colors.white
_BLACK = colors.black

# NDVI spectrum colours (6 bands from -1 to +1)
_NDVI_BANDS = [
    (-1.0, -0.1, HexColor("#1e3a5f"), "Water"),
    (-0.1, 0.1, HexColor("#78350f"), "Bare Soil"),
    (0.1, 0.2, HexColor("#b45309"), "Sparse"),
    (0.2, 0.4, HexColor("#65a30d"), "Moderate"),
    (0.4, 0.6, HexColor("#15803d"), "Healthy"),
    (0.6, 1.1, HexColor("#064e3b"), "Dense"),
]

# 1×1 transparent PNG placeholder
_PLACEHOLDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _report_integrity_hash(report: dict) -> str:
    """SHA-256 of key report fields — used as a tamper-detection token in footers."""
    payload = {
        "best_date": report.get("best_date"),
        "date_from": report.get("date_from"),
        "date_to": report.get("date_to"),
        "crop_type": report.get("crop_type"),
        "pooled_stats": report.get("pooled_stats"),
        "cloud_score": report.get("best_image", {}).get("cloud_score"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _safe_img(b64: str | None, width: float = 240, height: float = 180) -> Image:
    data = base64.b64decode(b64) if b64 else _PLACEHOLDER_PNG
    return Image(io.BytesIO(data), width=width, height=height)


def _styles() -> dict:
    """Build and return all custom paragraph styles."""
    s = {}

    s["title"] = ParagraphStyle(
        "k_title",
        fontName="Helvetica-Bold",
        fontSize=17,
        textColor=_NAVY,
        spaceBefore=0,
        spaceAfter=3,
        leading=20,
    )
    s["subtitle"] = ParagraphStyle(
        "k_subtitle",
        fontName="Helvetica",
        fontSize=10,
        textColor=_MUTED,
        spaceBefore=0,
        spaceAfter=4,
        leading=14,
    )
    s["ref"] = ParagraphStyle(
        "k_ref",
        fontName="Courier",
        fontSize=8.5,
        textColor=_TEAL,
        spaceBefore=0,
        spaceAfter=2,
    )
    s["section"] = ParagraphStyle(
        "k_section",
        fontName="Helvetica-Bold",
        fontSize=9.5,
        textColor=_NAVY,
        spaceBefore=14,
        spaceAfter=5,
        borderPadding=(0, 0, 3, 0),
    )
    s["body"] = ParagraphStyle(
        "k_body",
        fontName="Helvetica",
        fontSize=9,
        textColor=_TEXT,
        spaceBefore=2,
        spaceAfter=3,
        leading=13,
    )
    s["body_bold"] = ParagraphStyle(
        "k_body_bold",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=_TEXT,
        spaceBefore=2,
        spaceAfter=3,
        leading=13,
    )
    s["caption"] = ParagraphStyle(
        "k_caption",
        fontName="Helvetica-Oblique",
        fontSize=7.5,
        textColor=_MUTED,
        spaceBefore=2,
        spaceAfter=6,
        leading=11,
    )
    s["bullet"] = ParagraphStyle(
        "k_bullet",
        fontName="Helvetica",
        fontSize=8.5,
        textColor=_TEXT,
        spaceBefore=1,
        spaceAfter=2,
        leftIndent=10,
        leading=12,
    )
    s["note"] = ParagraphStyle(
        "k_note",
        fontName="Helvetica-Oblique",
        fontSize=8,
        textColor=_MUTED,
        spaceBefore=2,
        spaceAfter=3,
        leading=11,
    )
    s["mono"] = ParagraphStyle(
        "k_mono",
        fontName="Courier",
        fontSize=7.5,
        textColor=_MUTED,
        spaceBefore=1,
        spaceAfter=1,
    )
    s["callout_status"] = ParagraphStyle(
        "k_cs",
        fontName="Helvetica-Bold",
        fontSize=10,
        spaceBefore=0,
        spaceAfter=3,
        leading=13,
    )
    s["callout_body"] = ParagraphStyle(
        "k_cb",
        fontName="Helvetica",
        fontSize=8.5,
        textColor=_TEXT,
        spaceBefore=1,
        spaceAfter=2,
        leading=12,
    )
    # ── New styles for enterprise redesign ──────────────────────────────────────
    s["cover_title"] = ParagraphStyle(
        "k_ct",
        fontName="Helvetica-Bold",
        fontSize=28,
        textColor=_WHITE,
        spaceBefore=0,
        spaceAfter=4,
        leading=32,
    )
    s["cover_sub"] = ParagraphStyle(
        "k_cs2",
        fontName="Helvetica",
        fontSize=11,
        textColor=_GRAY_D,
        spaceBefore=0,
        spaceAfter=0,
        leading=15,
    )
    s["section_num"] = ParagraphStyle(
        "k_sn",
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=_TEAL_BRIGHT,
        spaceBefore=0,
        spaceAfter=0,
    )
    s["section_title"] = ParagraphStyle(
        "k_st",
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=_NAVY,
        spaceBefore=0,
        spaceAfter=0,
    )
    s["kpi_val"] = ParagraphStyle(
        "k_kv",
        fontName="Helvetica-Bold",
        fontSize=18,
        textColor=_NAVY,
        spaceBefore=0,
        spaceAfter=1,
        leading=20,
    )
    s["kpi_lbl"] = ParagraphStyle(
        "k_kl",
        fontName="Helvetica-Bold",
        fontSize=7,
        textColor=_MUTED,
        spaceBefore=0,
        spaceAfter=2,
    )
    s["kpi_sub"] = ParagraphStyle(
        "k_ks",
        fontName="Helvetica",
        fontSize=7.5,
        textColor=_MUTED,
        spaceBefore=0,
        spaceAfter=0,
        leading=10,
    )
    s["exec_summary"] = ParagraphStyle(
        "k_ex",
        fontName="Helvetica",
        fontSize=9.5,
        textColor=_TEXT,
        spaceBefore=2,
        spaceAfter=4,
        leading=14,
    )
    s["img_label"] = ParagraphStyle(
        "k_il",
        fontName="Helvetica-Bold",
        fontSize=7.5,
        textColor=_WHITE,
        spaceBefore=0,
        spaceAfter=0,
    )
    s["img_caption"] = ParagraphStyle(
        "k_ic",
        fontName="Helvetica-Oblique",
        fontSize=7,
        textColor=_MUTED,
        spaceBefore=0,
        spaceAfter=0,
        leading=10,
    )
    return s


def _tbl_style(header_bg=None, row_heights: bool = True) -> TableStyle:
    """Standard table style: navy/teal header, alternating rows, clean grid."""
    hbg = header_bg or _NAVY
    cmds = [
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), hbg),
        ("TEXTCOLOR", (0, 0), (-1, 0), _WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, _TEAL),
        # Data rows
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _GRAY_L]),
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.3, _GRAY_M),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, _GRAY_M),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, _GRAY_M),
        # Padding
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    return TableStyle(cmds)


def _section_block(number: str, title: str, st: dict) -> list:
    """Section header: thin rule + bold numbered title."""
    return [
        HRFlowable(width="100%", thickness=0.5, color=_GRAY_M, spaceBefore=10, spaceAfter=4),
        Paragraph(
            f'<font color="#0e6e70"><b>{number} &nbsp;</b></font><font color="#0d2137"><b>{title}</b></font>',
            st["section"],
        ),
    ]


def _callout_box(
    status_text: str,
    signal: str,
    recommendation: str,
    bg: HexColor,
    accent: HexColor,
    st: dict,
) -> Table:
    """A colored callout box with left-border accent, status title, and body text."""
    inner = [
        Paragraph(
            f'<font color="#{accent.hexval()}"><b>{status_text}</b></font>',
            st["callout_status"],
        ),
        Spacer(1, 3),
        Paragraph(f"<b>Evidence signal:</b> {signal}", st["callout_body"]),
        Paragraph(f"<b>Recommendation:</b> {recommendation}", st["callout_body"]),
    ]
    tbl = Table([[inner]], colWidths=[None])
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("LINEBEFORE", (0, 0), (0, -1), 4, accent),
                ("LINEAFTER", (-1, 0), (-1, -1), 0.3, _GRAY_M),
                ("LINEABOVE", (0, 0), (-1, 0), 0.3, _GRAY_M),
                ("LINEBELOW", (0, -1), (-1, -1), 0.3, _GRAY_M),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return tbl


def _health_callout(ndvi_interp: dict, st: dict) -> Table | None:
    if not ndvi_interp:
        return None
    health_class = ndvi_interp.get("health_class", "moderate")
    color_map = {
        "healthy": (_GREEN_L, _GREEN, "VEGETATION DETECTED — CLAIM NOT SUPPORTED"),
        "moderate": (_AMBER_L, _AMBER, "INCONCLUSIVE — FIELD VERIFICATION REQUIRED"),
        "stressed": (_RED_L, _RED, "NO CROP EMERGENCE — CLAIM SUPPORTED BY EVIDENCE"),
    }
    bg, accent, status_text = color_map.get(health_class, (_TEAL_L, _TEAL, "NDVI ASSESSMENT"))
    return _callout_box(
        status_text,
        ndvi_interp.get("claim_signal", ""),
        ndvi_interp.get("recommendation", ""),
        bg,
        accent,
        st,
    )


# ── Enterprise design helpers ─────────────────────────────────────────────────

_CW = 6.77 * inch  # content width (A4 minus 0.75" margins each side)


def _section_header_v2(number: str, title: str, st: dict) -> list:
    """Tinted section header with teal bottom line — enterprise visual hierarchy."""
    hdr = Table(
        [
            [
                Paragraph(number, st["section_num"]),
                Paragraph(title, st["section_title"]),
            ]
        ],
        colWidths=[0.42 * inch, None],
    )
    hdr.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _LIGHT_BLUE),
                ("LINEBELOW", (0, 0), (-1, 0), 2.0, _TEAL_BRIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return [Spacer(1, 10), hdr, Spacer(1, 6)]


def _kpi_row(metrics: list[tuple], width: float = _CW) -> Table:
    """
    A horizontal row of KPI metric boxes.
    metrics: list of (label, value, sub_text, accent_HexColor)
    """
    n = len(metrics)
    cell_w = width / n
    row = []
    accent_cmds = []
    for i, (label, value, sub, accent) in enumerate(metrics):
        row.append(
            [
                Paragraph(
                    label.upper(),
                    ParagraphStyle(
                        f"kl{i}",
                        fontName="Helvetica-Bold",
                        fontSize=7,
                        textColor=accent,
                        spaceAfter=2,
                    ),
                ),
                Paragraph(
                    f"<b>{value}</b>",
                    ParagraphStyle(
                        f"kv{i}",
                        fontName="Helvetica-Bold",
                        fontSize=18,
                        textColor=_NAVY,
                        spaceAfter=1,
                        leading=20,
                    ),
                ),
                Paragraph(
                    sub,
                    ParagraphStyle(
                        f"ks{i}",
                        fontName="Helvetica",
                        fontSize=7.5,
                        textColor=_MUTED,
                        leading=10,
                    ),
                ),
            ]
        )
        accent_cmds.append(("LINEABOVE", (i, 0), (i, 0), 3, accent))

    cmds = [
        ("BACKGROUND", (0, 0), (-1, -1), _GRAY_L),
        ("BOX", (0, 0), (-1, -1), 0.5, _GRAY_M),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, _GRAY_M),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ] + accent_cmds
    tbl = Table([row], colWidths=[cell_w] * n)
    tbl.setStyle(TableStyle(cmds))
    return tbl


def _ndvi_spectrum_bar(mean_ndvi: float, width: float = _CW) -> list:
    """
    A colour-gradient NDVI spectrum bar with a value marker in the active band.
    Returns a list of flowables (bar table + label row).
    """
    total_range = 2.0  # −1 to +1
    widths = [(hi - lo) / total_range * width for lo, hi, _, _ in _NDVI_BANDS]

    # Determine active band
    active = len(_NDVI_BANDS) - 1
    for i, (lo, hi, _, _) in enumerate(_NDVI_BANDS):
        if lo <= mean_ndvi < hi:
            active = i
            break

    # Row 1: colour cells with marker in active band
    bar_row = []
    for i, (_, _, _color, _) in enumerate(_NDVI_BANDS):
        txt = "▼" if i == active else ""
        bar_row.append(
            Paragraph(
                txt,
                ParagraphStyle(
                    f"bm{i}",
                    fontName="Helvetica-Bold",
                    fontSize=8,
                    textColor=_WHITE,
                    alignment=1,
                ),
            )
        )

    # Row 2: band labels
    lbl_row = [
        Paragraph(
            label,
            ParagraphStyle(
                f"bl{i}",
                fontName="Helvetica",
                fontSize=6,
                textColor=_MUTED,
                alignment=1,
            ),
        )
        for i, (_, _, _, label) in enumerate(_NDVI_BANDS)
    ]

    bar_cmds: list = [
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ]
    for i, (_, _, color, _) in enumerate(_NDVI_BANDS):
        bar_cmds.append(("BACKGROUND", (i, 0), (i, 0), color))
    if active < len(_NDVI_BANDS):
        bar_cmds.append(("LINEBELOW", (active, 0), (active, 0), 2, _WHITE))

    bar_tbl = Table([bar_row, lbl_row], colWidths=widths)
    bar_tbl.setStyle(TableStyle(bar_cmds))

    # Value annotation
    lo, hi, _, band_name = _NDVI_BANDS[active]
    value_para = Paragraph(
        f"Measured value: <b>{mean_ndvi:.3f}</b>  ·  Classification: <b>{band_name}</b>  "
        f"·  Range of active band: [{lo:.1f}, {hi:.1f})",
        ParagraphStyle("bv", fontName="Helvetica", fontSize=7.5, textColor=_MUTED),
    )
    return [bar_tbl, Spacer(1, 3), value_para]


def _image_card(b64: str | None, label: str, caption: str, img_w: float, img_h: float, st: dict) -> Table:
    """Satellite image inside a branded card (dark header + caption strip)."""
    img = _safe_img(b64, width=img_w, height=img_h)
    card = Table(
        [
            [Paragraph(label, st["img_label"])],
            [img],
            [Paragraph(caption, st["img_caption"])],
        ],
        colWidths=[img_w],
    )
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), _NAVY),
                ("BACKGROUND", (0, 1), (0, 1), _WHITE),
                ("BACKGROUND", (0, 2), (0, 2), _GRAY_L),
                ("BOX", (0, 0), (-1, -1), 0.5, _GRAY_M),
                ("TOPPADDING", (0, 0), (0, 0), 5),
                ("BOTTOMPADDING", (0, 0), (0, 0), 5),
                ("LEFTPADDING", (0, 0), (0, 0), 8),
                ("TOPPADDING", (0, 1), (0, 1), 4),
                ("BOTTOMPADDING", (0, 1), (0, 1), 4),
                ("LEFTPADDING", (0, 1), (0, 1), 4),
                ("RIGHTPADDING", (0, 1), (0, 1), 4),
                ("ALIGN", (0, 1), (0, 1), "CENTER"),
                ("TOPPADDING", (0, 2), (0, 2), 4),
                ("BOTTOMPADDING", (0, 2), (0, 2), 4),
                ("LEFTPADDING", (0, 2), (0, 2), 8),
            ]
        )
    )
    return card


def _ai_section_blocks(ai_assessment: dict, ai_narrative: str, st: dict) -> list:
    """
    Render the structured AI assessment (or plain narrative) as PDF flowables.
    Shows executive summary prominently, then insurance interpretation, then caveats.
    """
    items: list = []
    is_struct = bool(ai_assessment) and isinstance(ai_assessment, dict)
    is_fallback = ai_assessment.get("fallback", True) if is_struct else True
    model_txt = (
        "Deterministic baseline  (AI narrative not enabled)"
        if is_fallback
        else "Gemini  ·  Google AI Studio"
    )

    exec_sum = (ai_assessment.get("executive_summary") if is_struct else None) or ai_narrative
    ins_int = ai_assessment.get("insurance_interpretation") if is_struct else None
    tech_anal = ai_assessment.get("technical_analysis") if is_struct else None
    conf_exp = ai_assessment.get("confidence_explanation") if is_struct else None
    caveats = (ai_assessment.get("caveats") or []) if is_struct else []

    if not exec_sum:
        return items

    # ── Model attribution header ───────────────────────────────────────────────
    attr_tbl = Table(
        [
            [
                Paragraph(
                    "AI-ASSISTED ASSESSMENT",
                    ParagraphStyle(
                        "ai_hd",
                        fontName="Helvetica-Bold",
                        fontSize=9,
                        textColor=_WHITE,
                        spaceAfter=0,
                    ),
                ),
                Paragraph(
                    model_txt,
                    ParagraphStyle(
                        "ai_md",
                        fontName="Helvetica",
                        fontSize=7.5,
                        textColor=HexColor("#cffafe"),
                        spaceAfter=0,
                    ),
                ),
            ]
        ],
        colWidths=[2.2 * inch, None],
    )
    attr_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _NAVY),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    items.append(attr_tbl)

    # ── Executive summary ──────────────────────────────────────────────────────
    exec_box = Table(
        [
            [
                Paragraph(
                    "EXECUTIVE SUMMARY",
                    ParagraphStyle(
                        "ai_el",
                        fontName="Helvetica-Bold",
                        fontSize=7,
                        textColor=_TEAL_BRIGHT,
                        spaceAfter=3,
                    ),
                )
            ],
            [Paragraph(exec_sum, st["exec_summary"])],
        ],
        colWidths=[None],
    )
    exec_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _TEAL_L),
                ("LINEBEFORE", (0, 0), (0, -1), 3, _TEAL_BRIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    items.append(exec_box)

    # ── Technical + Insurance two-column ──────────────────────────────────────
    if ins_int or tech_anal:
        left_body: list = []
        right_body: list = []
        if tech_anal:
            left_body.append(
                Paragraph(
                    "TECHNICAL ANALYSIS",
                    ParagraphStyle(
                        "ai_tl",
                        fontName="Helvetica-Bold",
                        fontSize=7,
                        textColor=_MUTED,
                        spaceAfter=3,
                    ),
                )
            )
            left_body.append(Paragraph(tech_anal, st["body"]))
        if ins_int:
            right_body.append(
                Paragraph(
                    "INSURANCE INTERPRETATION",
                    ParagraphStyle(
                        "ai_il",
                        fontName="Helvetica-Bold",
                        fontSize=7,
                        textColor=_AMBER,
                        spaceAfter=3,
                    ),
                )
            )
            right_body.append(Paragraph(ins_int, st["body"]))

        if left_body or right_body:
            two_col = Table(
                [[left_body or [""], right_body or [""]]],
                colWidths=[_CW / 2 - 0.1 * inch, _CW / 2 - 0.1 * inch],
            )
            two_col.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), _GRAY_L),
                        ("INNERGRID", (0, 0), (-1, -1), 0.3, _GRAY_M),
                        ("BOX", (0, 0), (-1, -1), 0.3, _GRAY_M),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            items.append(two_col)

    # ── Confidence explanation ─────────────────────────────────────────────────
    if conf_exp:
        items.append(
            Paragraph(
                f"<b>Confidence basis:</b>  {conf_exp}",
                st["note"],
            )
        )

    # ── Caveats ────────────────────────────────────────────────────────────────
    if caveats:
        items.append(Paragraph("<b>Caveats:</b>", st["body_bold"]))
        for cav in caveats:
            items.append(Paragraph(f"•  {cav}", st["bullet"]))

    return items


def _draw_cover_page(report: dict, ref_id: str, gen_display: str):
    """
    Return an onFirstPage canvas callback that paints the full cover.
    Uses a closure to capture report data without altering the callback signature.
    """
    ndvi_interp = report.get("ndvi_interpretation") or {}
    pooled = report.get("pooled_stats") or {}
    confidence = report.get("confidence") or {}

    def _cb(canvas, doc) -> None:
        canvas.saveState()
        w, h = doc.pagesize

        # ── Full dark background ───────────────────────────────────────────────
        canvas.setFillColor(_NAVY_DEEP)
        canvas.rect(0, 0, w, h, fill=1, stroke=0)

        # ── Top teal accent bar ────────────────────────────────────────────────
        canvas.setFillColor(_TEAL)
        canvas.rect(0, h - 0.38 * inch, w, 0.38 * inch, fill=1, stroke=0)

        # Wordmark and tagline inside accent bar
        canvas.setFillColor(_WHITE)
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawString(0.75 * inch, h - 0.25 * inch, "KERYOS")
        canvas.setFillColor(HexColor("#cffafe"))
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(w - 0.75 * inch, h - 0.25 * inch, "Satellite Claim Verification Intelligence")

        # ── Faint "K" watermark ────────────────────────────────────────────────
        canvas.setFillColor(HexColor("#0a1a2e"))
        canvas.setFont("Helvetica-Bold", 200)
        canvas.drawCentredString(w / 2, h * 0.14, "K")

        # ── Main title block ──────────────────────────────────────────────────
        ty = h * 0.70
        canvas.setFillColor(_WHITE)
        canvas.setFont("Helvetica-Bold", 30)
        canvas.drawString(0.75 * inch, ty, "SATELLITE CLAIM")
        canvas.drawString(0.75 * inch, ty - 0.48 * inch, "VERIFICATION REPORT")

        canvas.setFont("Helvetica", 11)
        canvas.setFillColor(_GRAY_D)
        canvas.drawString(0.75 * inch, ty - 0.88 * inch, "Prevented-Sowing Agricultural Insurance Assessment")

        # Separator line
        canvas.setStrokeColor(_TEAL)
        canvas.setLineWidth(1)
        canvas.line(0.75 * inch, ty - 1.08 * inch, w - 0.75 * inch, ty - 1.08 * inch)

        # ── Verdict badge ─────────────────────────────────────────────────────
        health_class = ndvi_interp.get("health_class", "moderate")
        verdict_map = {
            "healthy": ("VEGETATION DETECTED", "CLAIM NOT SUPPORTED BY EVIDENCE", _GREEN_D, _GREEN_L),
            "moderate": ("BORDERLINE SIGNAL", "FIELD VERIFICATION REQUIRED", _AMBER_D, _AMBER_L),
            "stressed": ("NO CROP EMERGENCE", "CLAIM SUPPORTED BY SATELLITE EVIDENCE", _RED_D, _RED_L),
        }
        v_title, v_sub, v_fg, v_bg = verdict_map.get(
            health_class, ("ASSESSMENT", "RESULT AVAILABLE", _MUTED, _GRAY_L)
        )

        vx = 0.75 * inch
        vy = ty - 2.22 * inch
        vw = w - 1.5 * inch
        vh = 0.90 * inch

        canvas.setFillColor(v_bg)
        canvas.rect(vx, vy, vw, vh, fill=1, stroke=0)
        canvas.setFillColor(v_fg)
        canvas.rect(vx, vy, 0.065 * inch, vh, fill=1, stroke=0)

        canvas.setFillColor(v_fg)
        canvas.setFont("Helvetica-Bold", 13)
        canvas.drawString(vx + 0.16 * inch, vy + 0.58 * inch, v_title)
        canvas.setFont("Helvetica", 9.5)
        canvas.drawString(vx + 0.16 * inch, vy + 0.37 * inch, v_sub)

        mean_val = pooled.get("mean")
        health_label = ndvi_interp.get("health_label", "")
        ndvi_line = (
            f"Composite NDVI: {mean_val:.3f}  ·  {health_label}" if mean_val is not None else health_label
        )
        canvas.setFillColor(HexColor("#374151"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(vx + 0.16 * inch, vy + 0.14 * inch, ndvi_line)

        # ── 4-column metadata grid ────────────────────────────────────────────
        conf_label = confidence.get("label", "N/A")
        conf_pct = confidence.get("overall", 0)
        meta_items = [
            ("Report Reference", ref_id),
            ("Crop Type", report.get("crop_type", "N/A").title()),
            ("Claim Period", f"{report.get('date_from', '?')} – {report.get('date_to', '?')}"),
            ("Confidence", f"{conf_label}  {conf_pct:.0%}"),
        ]
        mx = 0.75 * inch
        my = vy - 0.25 * inch - 0.85 * inch
        mw_each = (w - 1.5 * inch) / 4
        mh = 0.85 * inch

        for i, (lbl, val) in enumerate(meta_items):
            bx = mx + i * mw_each
            by = my
            bg = HexColor("#0c1f33") if i % 2 == 0 else HexColor("#0a1929")
            canvas.setFillColor(bg)
            canvas.rect(bx, by, mw_each, mh, fill=1, stroke=0)
            # Teal top accent
            canvas.setFillColor(_TEAL)
            canvas.rect(bx, by + mh - 0.03 * inch, mw_each, 0.03 * inch, fill=1, stroke=0)
            # Label
            canvas.setFillColor(_GRAY_D)
            canvas.setFont("Helvetica", 6.5)
            canvas.drawString(bx + 0.12 * inch, by + mh - 0.22 * inch, lbl.upper())
            # Value
            canvas.setFillColor(_WHITE)
            canvas.setFont("Helvetica-Bold", 9)
            canvas.drawString(bx + 0.12 * inch, by + 0.26 * inch, str(val))

        # ── Bottom footer ─────────────────────────────────────────────────────
        canvas.setFillColor(HexColor("#050c14"))
        canvas.rect(0, 0, w, 0.52 * inch, fill=1, stroke=0)
        canvas.setFillColor(_GRAY_D)
        canvas.setFont("Helvetica", 6.5)
        canvas.drawString(
            0.75 * inch,
            0.19 * inch,
            "Keryos Satellite Intelligence Engine  ·  Copernicus Sentinel-2 L2A  ·  Keryos v0.1",
        )
        canvas.drawRightString(w - 0.75 * inch, 0.19 * inch, gen_display)

        canvas.restoreState()

    return _cb


# ── Page chrome (header + footer on every page) ───────────────────────────────


def _draw_chrome_full(canvas, doc) -> None:
    """Painted header band + footer band for the full verification report."""
    canvas.saveState()
    w, h = doc.pagesize

    # Header band
    canvas.setFillColor(_NAVY)
    canvas.rect(0, h - 0.58 * inch, w, 0.58 * inch, fill=1, stroke=0)
    # Teal accent strip
    canvas.setFillColor(_TEAL)
    canvas.rect(0, h - 0.62 * inch, w, 0.04 * inch, fill=1, stroke=0)

    canvas.setFillColor(_WHITE)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(0.70 * inch, h - 0.36 * inch, "KERYOS")
    canvas.setFillColor(_GRAY_D)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(1.55 * inch, h - 0.36 * inch, "Satellite Crop Verification Intelligence")
    canvas.setFillColor(_GRAY_M)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawRightString(w - 0.70 * inch, h - 0.36 * inch, f"Page {doc.page}")

    # Footer band
    canvas.setFillColor(_NAVY)
    canvas.rect(0, 0, w, 0.44 * inch, fill=1, stroke=0)
    canvas.setFillColor(_GRAY_D)
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(0.70 * inch, 0.16 * inch, "CONFIDENTIAL  ·  Crop Insurance Intelligence Report")
    canvas.drawRightString(w - 0.70 * inch, 0.16 * inch, "Data: Copernicus Sentinel-2 L2A  ·  Keryos v0.1")

    canvas.restoreState()


def _draw_chrome_summary(canvas, doc) -> None:
    """Lighter chrome for the 1-page summary."""
    canvas.saveState()
    w, h = doc.pagesize

    canvas.setFillColor(_NAVY)
    canvas.rect(0, h - 0.48 * inch, w, 0.48 * inch, fill=1, stroke=0)
    canvas.setFillColor(_TEAL)
    canvas.rect(0, h - 0.52 * inch, w, 0.04 * inch, fill=1, stroke=0)

    canvas.setFillColor(_WHITE)
    canvas.setFont("Helvetica-Bold", 9.5)
    canvas.drawString(0.6 * inch, h - 0.31 * inch, "KERYOS")
    canvas.setFillColor(_GRAY_D)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(1.45 * inch, h - 0.31 * inch, "Prevented-Sowing Claim Summary")
    canvas.setFillColor(_GRAY_M)
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(w - 0.6 * inch, h - 0.31 * inch, "CONFIDENTIAL")

    canvas.setFillColor(_NAVY)
    canvas.rect(0, 0, w, 0.38 * inch, fill=1, stroke=0)
    canvas.setFillColor(_GRAY_D)
    canvas.setFont("Helvetica", 6)
    canvas.drawString(0.6 * inch, 0.14 * inch, "Copernicus Sentinel-2 L2A  ·  Keryos v0.1")
    canvas.drawRightString(w - 0.6 * inch, 0.14 * inch, datetime.now().strftime("%Y-%m-%d %H:%M UTC"))

    canvas.restoreState()


# ── Full verification PDF ──────────────────────────────────────────────────────


def generate_verification_pdf(report: dict, polygon_coords: dict | None) -> bytes:  # noqa: ARG001
    """
    Enterprise-grade multi-page insurance verification pack.

    Page 1  — Full-canvas cover (navy background, verdict badge, metadata grid).
    Page 2+ — Executive summary KPIs + 8 numbered sections with styled headers,
               NDVI spectrum bar, image cards, structured AI assessment.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.82 * inch,
        bottomMargin=0.65 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )
    st = _styles()

    # ── Lookups ───────────────────────────────────────────────────────────────
    best = report.get("best_image", {})
    pooled = report.get("pooled_stats") or {}
    aoi_meta = report.get("aoi_metadata") or {}
    ndvi_interp = report.get("ndvi_interpretation") or {}
    confidence = report.get("confidence") or {}
    tech = report.get("technical_summary") or {}
    proc = report.get("processing_metadata") or {}
    ai_assess = report.get("ai_assessment") or {}
    integrity = _report_integrity_hash(report)
    ref_id = f"KRY-{integrity[:8].upper()}"
    gen_ts = report.get("generated_at") or datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    gen_display = gen_ts[:19].replace("T", " ") + " UTC"
    conf_label = confidence.get("label", "N/A")
    overall = confidence.get("overall", 0)

    cover_cb = _draw_cover_page(report, ref_id, gen_display)

    story: list = [PageBreak()]  # Page 1 = cover canvas; content starts on page 2

    # ── Executive summary: KPI metric row ─────────────────────────────────────
    pooled_mean = pooled.get("mean")
    ndvi_kpi = f"{pooled_mean:.3f}" if pooled_mean is not None else "N/A"
    cloud_kpi = f"{best.get('cloud_score', 0):.1%}"
    passes_kpi = str(pooled.get("passes", "N/A"))
    conf_kpi = f"{conf_label}  {overall:.0%}"

    story.append(Spacer(1, 4))
    story.append(
        _kpi_row(
            [
                ("Composite NDVI", ndvi_kpi, ndvi_interp.get("health_label", ""), _TEAL_BRIGHT),
                ("Cloud Score", cloud_kpi, "Best scene clarity", HexColor("#2563eb")),
                (
                    "Confidence",
                    conf_kpi,
                    "Data quality assessment",
                    {"High": _GREEN, "Medium": _AMBER, "Low": _RED}.get(conf_label, _MUTED),
                ),
                (
                    "Sat. Passes",
                    passes_kpi,
                    f"{pooled.get('totalPixels', 0):,} valid pixels",
                    HexColor("#7c3aed"),
                ),
            ]
        )
    )
    story.append(Spacer(1, 8))

    # Verdict summary (compact — full verdict is on the cover)
    if ndvi_interp:
        story.append(_health_callout(ndvi_interp, st))
        story.append(Spacer(1, 6))

    # ── Section 01: Field & Claim Details ─────────────────────────────────────
    story.extend(_section_header_v2("01", "FIELD & CLAIM DETAILS", st))

    area_km2 = aoi_meta.get("area_km2")
    area_ha = aoi_meta.get("area_ha")
    area_str = f"{area_km2:.4f} km²  ({area_ha:.1f} ha)" if area_km2 else "N/A"
    centroid = aoi_meta.get("centroid") or {}
    centroid_str = f"{centroid['lat']:.5f}° N, {centroid['lon']:.5f}° E" if centroid else "N/A"
    acq_dates = ", ".join(report.get("acquisition_dates") or [report.get("best_date", "N/A")])

    details_data = [
        ["Parameter", "Value"],
        ["Crop Type", report.get("crop_type", "N/A").title()],
        ["Sowing Window (Claim Period)", f"{report.get('date_from')} to {report.get('date_to')}"],
        ["Best Clear-Sky Acquisition", report.get("best_date", "N/A")],
        ["All Dates Evaluated", acq_dates],
        ["AOI Area", area_str],
        ["AOI Centroid (approx.)", centroid_str],
        ["AOI Vertex Count", str(aoi_meta.get("vertex_count") or "N/A")],
        ["AOI Reference Hash", aoi_meta.get("aoi_hash", "N/A")],
    ]
    dtbl = Table(details_data, colWidths=[2.4 * inch, None])
    dtbl.setStyle(_tbl_style(header_bg=_TEAL))
    story.append(dtbl)

    # ── Section 02: Satellite Evidence ────────────────────────────────────────
    story.extend(_section_header_v2("02", "SATELLITE EVIDENCE", st))
    story.append(
        Paragraph(
            f"Best cloud-free scene: <b>{report.get('best_date')}</b>  ·  "
            f"SCL cloud score: <b>{best.get('cloud_score', 0):.1%}</b>  ·  "
            f"Catalog cloud cover: <b>{best.get('cloud_cover', 'N/A')}</b>",
            st["body"],
        )
    )
    story.append(Spacer(1, 6))

    img_w, img_h = 3.1 * inch, 2.35 * inch
    gap = _CW - 2 * img_w
    tc_card = _image_card(
        best.get("png_b64"),
        "TRUE COLOUR  RGB",
        f"Sentinel-2 B04/B03/B02 · {report.get('best_date')}",
        img_w,
        img_h,
        st,
    )
    swir_card = _image_card(
        best.get("swir_png_b64"),
        "FALSE COLOUR  SWIR",
        f"Sentinel-2 B11/B08/B04 · {report.get('best_date')}",
        img_w,
        img_h,
        st,
    )
    img_layout = Table([[tc_card, Spacer(gap, 1), swir_card]], colWidths=[img_w, gap, img_w])
    img_layout.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(img_layout)
    story.append(
        Paragraph(
            "© Copernicus Sentinel-2 L2A. Scene rendered via Sentinel Hub Process API at 20 m/pixel.",
            st["caption"],
        )
    )
    if report.get("alternatives"):
        story.append(
            Paragraph(
                f"<b>{len(report['alternatives'])} alternative scene(s)</b> were evaluated "
                "and are available in the digital report.",
                st["note"],
            )
        )

    # ── Section 03: NDVI Vegetation Analysis ─────────────────────────────────
    story.extend(_section_header_v2("03", "NDVI VEGETATION ANALYSIS", st))

    stats_data = safe_extract_stats(report.get("ndvi_stats"))
    if stats_data is not None:
        _std = stats_data.get("stDev", stats_data.get("std"))
        _pct = stats_data.get("percentiles") or {}
        _mean, _p50 = stats_data.get("mean"), _pct.get("50.0")
        _p25, _p75 = _pct.get("25.0"), _pct.get("75.0")
        ndvi_rows = [
            ["Metric", "Value", "Interpretation"],
            [
                "Mean NDVI",
                f"{float(_mean):.3f}" if _mean is not None else "N/A",
                "< 0.2 bare/stressed  ·  0.2–0.4 sparse  ·  > 0.4 healthy",
            ],
            [
                "Median NDVI (P50)",
                f"{float(_p50):.3f}" if _p50 is not None else "N/A",
                "Robust central value, less sensitive to cloud-shadow outliers",
            ],
            [
                "Standard Deviation",
                f"{float(_std):.3f}" if _std is not None else "N/A",
                "Within-field spectral variability",
            ],
            [
                "IQR (P25–P75)",
                f"{float(_p25):.3f} – {float(_p75):.3f}" if _p25 is not None and _p75 is not None else "N/A",
                "Middle 50% of pixel distribution",
            ],
        ]
        story.append(
            Table(ndvi_rows, colWidths=[1.5 * inch, 0.9 * inch, None], style=_tbl_style(header_bg=_TEAL))
        )
        story.append(Spacer(1, 6))
    else:
        story.append(Paragraph("Per-date NDVI statistics unavailable.", st["note"]))

    # NDVI spectrum bar (only if we have a value)
    if pooled_mean is not None:
        story.extend(_ndvi_spectrum_bar(pooled_mean))
    if ndvi_interp:
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(
                f"<b>Health Assessment:</b>  {ndvi_interp.get('health_label', '')}  ·  "
                f"{ndvi_interp.get('claim_signal', '')}",
                st["body_bold"],
            )
        )

    # ── Section 04: Temporal Composite Analysis ───────────────────────────────
    story.extend(_section_header_v2("04", "TEMPORAL COMPOSITE ANALYSIS", st))
    story.append(
        Paragraph(
            f"Cloud-robust weighted composite across all valid daily intervals "
            f"({report.get('date_from')} – {report.get('date_to')}). "
            "SCL cloud classes 8, 9, 10 excluded from statistics.",
            st["body"],
        )
    )
    story.append(Spacer(1, 4))

    if pooled:
        comp_rows = [
            ["Composite Metric", "Value", "Notes"],
            ["Composite Mean NDVI", f"{pooled['mean']:.3f}", "Weighted average — all valid passes"],
            [
                "Pooled Standard Deviation",
                f"{pooled['stDev']:.3f}",
                "Cross-temporal within-field variability",
            ],
            ["Valid Satellite Passes", str(pooled["passes"]), "Distinct cloud-free acquisition epochs"],
            ["Total Valid Pixels", f"{pooled['totalPixels']:,}", "Clear-sky pixels in composite"],
        ]
        story.append(
            Table(comp_rows, colWidths=[2.0 * inch, 1.0 * inch, None], style=_tbl_style(header_bg=_NAVY))
        )
    else:
        story.append(Paragraph("Composite statistics not available.", st["note"]))

    # ── Section 05: AI-Assisted Assessment ────────────────────────────────────
    if report.get("ai_narrative") or ai_assess:
        story.extend(_section_header_v2("05", "AI-ASSISTED ASSESSMENT", st))
        story.extend(_ai_section_blocks(ai_assess, report.get("ai_narrative", ""), st))
        story.append(Spacer(1, 4))

    # ── Section 06: Confidence Assessment ────────────────────────────────────
    story.extend(_section_header_v2("06", "CONFIDENCE ASSESSMENT", st))
    conf_color = {"High": _GREEN, "Medium": _AMBER, "Low": _RED}.get(conf_label, _MUTED)
    story.append(
        Paragraph(
            f'Overall Confidence: <font color="#{conf_color.hexval()}">'
            f"<b>{conf_label}  ({overall:.0%})</b></font>",
            st["body"],
        )
    )
    story.append(Spacer(1, 4))

    ai_val_str = (
        ("Validated" if confidence.get("ai_validated") else "Flagged")
        if confidence.get("ai_validated") is not None
        else "Not enabled"
    )
    ai_conf_str = (
        f"{confidence['ai_confidence']:.0%}" if confidence.get("ai_confidence") is not None else "N/A"
    )

    conf_rows = [
        ["Factor", "Value", "Weight & Role"],
        [
            "Cloud Scene Clarity",
            f"{confidence.get('cloud_clarity', 0):.0%}",
            "55% — clear-sky spectral fidelity of primary scene",
        ],
        [
            "Temporal Coverage",
            f"{confidence.get('temporal_coverage', 0):.0%}  ({confidence.get('passes', 0)} passes)",
            "35% — multi-pass composite reliability",
        ],
        ["AI Image Validation", ai_val_str, "10% — Gemini automated quality assessment"],
        ["AI Validation Confidence", ai_conf_str, "Sub-score from AI validator"],
        ["Overall", f"{conf_label}  ({overall:.0%})", "Composite score"],
    ]
    story.append(
        Table(conf_rows, colWidths=[2.0 * inch, 1.3 * inch, None], style=_tbl_style(header_bg=_NAVY))
    )
    story.append(
        Paragraph(
            "High ≥ 70%  ·  Medium 40–70%  ·  Low < 40%.  "
            "Confidence reflects satellite data quality — not legal claim validity.",
            st["note"],
        )
    )

    # ── Section 07: Technical Evidence ────────────────────────────────────────
    story.extend(_section_header_v2("07", "TECHNICAL EVIDENCE SUMMARY", st))
    tech_rows = [
        ["Parameter", "Value"],
        ("Data Source", tech.get("data_source", "Copernicus Sentinel-2 L2A")),
        ("Statistics Method", tech.get("statistics_method", "Weighted pooled mean")),
        ("Spatial Resolution", f"{tech.get('spatial_resolution_m', 20)} m/pixel"),
        ("Band Formula", tech.get("band_formula", "NDVI = (NIR−RED)/(NIR+RED)")),
        ("Cloud Masking", tech.get("cloud_masking", "SCL classes 1,3,8,9,10")),
        ("Image Validation", tech.get("image_validation", "Brightness + quality score")),
        ("Scenes Evaluated", str(tech.get("scenes_evaluated", len(report.get("alternatives", [])) + 1))),
        ("Best Scene Cloud Score", f"{best.get('cloud_score', 0):.2%}"),
        ("Catalog Cloud Cover", str(best.get("cloud_cover") or "N/A")),
    ]
    story.append(Table(tech_rows, colWidths=[2.2 * inch, None], style=_tbl_style(header_bg=_TEAL)))
    story.append(Spacer(1, 4))

    steps = proc.get("pipeline_steps", [])
    if steps:
        story.append(Paragraph("<b>Processing Pipeline Steps:</b>", st["body_bold"]))
        for i, step in enumerate(steps, 1):
            story.append(Paragraph(f"&nbsp;&nbsp;{i:02d}.&nbsp; {step}", st["bullet"]))
    story.append(Spacer(1, 4))

    # ── Section 08: Limitations ────────────────────────────────────────────────
    story.extend(_section_header_v2("08", "LIMITATIONS & CAVEATS", st))
    for lim in [
        "Satellite NDVI is an indicator of vegetation cover — not direct proof of sowing status.",
        "Cloud masking may exclude valid observations; composite covers only cloud-free epochs.",
        "NDVI thresholds are empirical guidelines for Kharif paddy; regional and soil variation applies.",
        "This report is supporting evidence only.  Claim adjudication requires field verification "
        "and compliance with applicable insurance policy terms.",
        "AI-generated narrative (if present) is advisory.  It does not constitute a formal assessment.",
    ]:
        story.append(Paragraph(f"•  {lim}", st["bullet"]))
    story.append(Spacer(1, 10))

    # ── Integrity footer ──────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GRAY_M, spaceBefore=6, spaceAfter=4))
    story.append(
        Paragraph(
            f"Integrity token: <b>{integrity}</b>  ·  Reference: <b>{ref_id}</b>  ·  "
            f"Generated: {gen_display}",
            st["mono"],
        )
    )
    story.append(
        Paragraph(
            "Generated by Keryos v0.1 using Copernicus Sentinel-2 open data.  "
            "Does not constitute legal, financial, or regulatory advice.",
            st["note"],
        )
    )

    doc.build(story, onFirstPage=cover_cb, onLaterPages=_draw_chrome_full)
    return buffer.getvalue()


# ── 1-Page summary PDF ─────────────────────────────────────────────────────────


def generate_summary_pdf(report: dict) -> bytes:
    """
    Compact 1-page executive summary for claim submission.
    Enterprise layout: header chrome + verdict banner + KPI row + facts table
    + thumbnail + AI summary block + integrity footer.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.65 * inch,
        bottomMargin=0.55 * inch,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
    )
    st = _styles()
    story: list = []

    best = report.get("best_image", {})
    pooled = report.get("pooled_stats") or {}
    aoi_meta = report.get("aoi_metadata") or {}
    ndvi_interp = report.get("ndvi_interpretation") or {}
    confidence = report.get("confidence") or {}
    ai_assess = report.get("ai_assessment") or {}
    integrity = _report_integrity_hash(report)
    ref_id = f"KRY-{integrity[:8].upper()}"
    gen_ts = report.get("generated_at") or datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    gen_display = gen_ts[:19].replace("T", " ") + " UTC"

    # Letter content width = 8.5" − 1.3" margins = 7.2"
    cw_letter = 7.2 * inch

    # ── Title block ───────────────────────────────────────────────────────────
    story.append(Spacer(1, 2))
    story.append(Paragraph("PREVENTED-SOWING CLAIM SUMMARY", st["title"]))
    story.append(
        Paragraph(
            f"Reference <b>{ref_id}</b>  ·  Generated {gen_display}",
            st["ref"],
        )
    )
    story.append(Spacer(1, 8))

    # ── Verdict banner (full-width, color-coded) ──────────────────────────────
    if ndvi_interp:
        health_class = ndvi_interp.get("health_class", "moderate")
        verdict_map = {
            "healthy": (
                _GREEN_L,
                _GREEN_D,
                "CLAIM NOT SUPPORTED",
                "Vegetation detected within sowing window",
            ),
            "moderate": (_AMBER_L, _AMBER_D, "INCONCLUSIVE — FIELD VERIFICATION", "Borderline NDVI signal"),
            "stressed": (
                _RED_L,
                _RED_D,
                "CLAIM SUPPORTED BY SATELLITE EVIDENCE",
                "No crop emergence detected",
            ),
        }
        bg, fg, verdict_text, verdict_sub = verdict_map.get(health_class, (_GRAY_L, _NAVY, "ASSESSMENT", ""))
        verdict_tbl = Table(
            [
                [
                    [
                        Paragraph(
                            "<b>VERDICT</b>",
                            ParagraphStyle(
                                "vl",
                                fontName="Helvetica-Bold",
                                fontSize=7,
                                textColor=fg,
                                spaceAfter=2,
                            ),
                        ),
                        Paragraph(
                            f"<b>{verdict_text}</b>",
                            ParagraphStyle(
                                "vt",
                                fontName="Helvetica-Bold",
                                fontSize=12,
                                textColor=fg,
                                spaceAfter=1,
                            ),
                        ),
                        Paragraph(
                            verdict_sub,
                            ParagraphStyle(
                                "vs",
                                fontName="Helvetica",
                                fontSize=8.5,
                                textColor=_TEXT,
                            ),
                        ),
                    ],
                ]
            ],
            colWidths=[None],
        )
        verdict_tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), bg),
                    ("LINEBEFORE", (0, 0), (0, -1), 4, fg),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("LEFTPADDING", (0, 0), (-1, -1), 14),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ]
            )
        )
        story.append(verdict_tbl)
        story.append(Spacer(1, 8))

    # ── KPI row ───────────────────────────────────────────────────────────────
    pooled_mean = pooled.get("mean")
    ndvi_kpi = f"{pooled_mean:.3f}" if pooled_mean is not None else "N/A"
    cloud_kpi = f"{best.get('cloud_score', 0):.1%}"
    passes_kpi = str(pooled.get("passes", "N/A"))
    conf_label = confidence.get("label", "N/A")
    overall = confidence.get("overall", 0)
    conf_kpi = f"{conf_label}  {overall:.0%}"

    story.append(
        _kpi_row(
            [
                ("Composite NDVI", ndvi_kpi, ndvi_interp.get("health_label", ""), _TEAL_BRIGHT),
                ("Cloud Score", cloud_kpi, "Best scene clarity", HexColor("#2563eb")),
                (
                    "Confidence",
                    conf_kpi,
                    "Data quality",
                    {"High": _GREEN, "Medium": _AMBER, "Low": _RED}.get(conf_label, _MUTED),
                ),
                ("Sat. Passes", passes_kpi, f"{pooled.get('totalPixels', 0):,} px", HexColor("#7c3aed")),
            ],
            width=cw_letter,
        )
    )
    story.append(Spacer(1, 8))

    # ── Key facts (left) + scene thumbnail card (right) ───────────────────────
    area_km2 = aoi_meta.get("area_km2")
    area_ha = aoi_meta.get("area_ha")
    area_str = f"{area_km2:.2f} km² ({area_ha:.0f} ha)" if area_km2 else "N/A"
    facts = [
        ["Parameter", "Value"],
        ["Crop Type", report.get("crop_type", "N/A").title()],
        ["Claim Period", f"{report.get('date_from')} – {report.get('date_to')}"],
        ["Best Clear-Sky Scene", report.get("best_date", "N/A")],
        ["AOI Area", area_str],
        ["Composite Mean NDVI", f"{pooled['mean']:.3f}" if pooled.get("mean") is not None else "N/A"],
        ["Vegetation Class", ndvi_interp.get("health_label", "N/A")],
        ["Valid Pixels", f"{pooled['totalPixels']:,}" if pooled.get("totalPixels") else "N/A"],
    ]
    facts_tbl = Table(facts, colWidths=[1.6 * inch, 2.3 * inch], style=_tbl_style(header_bg=_NAVY))

    thumb_card = _image_card(
        best.get("png_b64"),
        "TRUE COLOUR  RGB",
        f"Sentinel-2 · {report.get('best_date')}",
        2.6 * inch,
        1.95 * inch,
        st,
    )

    layout_tbl = Table(
        [[facts_tbl, Spacer(0.2 * inch, 1), thumb_card]],
        colWidths=[3.9 * inch, 0.1 * inch, 3.2 * inch],
    )
    layout_tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(layout_tbl)
    story.append(Spacer(1, 8))

    # ── NDVI spectrum bar ─────────────────────────────────────────────────────
    if pooled_mean is not None:
        story.extend(_ndvi_spectrum_bar(pooled_mean, width=cw_letter))
        story.append(Spacer(1, 6))

    # ── AI summary block (executive sentence only — keep it tight) ─────────────
    exec_text = (ai_assess.get("executive_summary") if isinstance(ai_assess, dict) else None) or report.get(
        "ai_narrative", ""
    )
    if exec_text:
        is_fallback = ai_assess.get("fallback", True) if isinstance(ai_assess, dict) else True
        model_lbl = "Deterministic baseline" if is_fallback else "Gemini · Google AI Studio"
        ai_box = Table(
            [
                [
                    Paragraph(
                        f'<font color="#0d9488"><b>AI ASSESSMENT</b></font>'
                        f'<font color="#64748b">  &nbsp;·&nbsp;  {model_lbl}</font>',
                        ParagraphStyle(
                            "ahb", fontName="Helvetica-Bold", fontSize=8.5, textColor=_NAVY, spaceAfter=4
                        ),
                    )
                ],
                [Paragraph(exec_text, st["body"])],
            ],
            colWidths=[None],
        )
        ai_box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _TEAL_L),
                    ("LINEBEFORE", (0, 0), (0, -1), 3, _TEAL_BRIGHT),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ]
            )
        )
        story.append(ai_box)

    # ── Integrity footer ──────────────────────────────────────────────────────
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GRAY_M, spaceAfter=3))
    story.append(
        Paragraph(
            f"Integrity token: <b>{integrity}</b>  ·  Ref: <b>{ref_id}</b>  ·  "
            "Keryos v0.1  ·  Copernicus Sentinel-2 L2A",
            st["mono"],
        )
    )

    doc.build(story, onFirstPage=_draw_chrome_summary, onLaterPages=_draw_chrome_summary)
    return buffer.getvalue()


# ── Technical appendix PDF ─────────────────────────────────────────────────────


def _draw_chrome_appendix(canvas, doc) -> None:
    """Page chrome for the technical appendix."""
    canvas.saveState()
    w, h = doc.pagesize

    canvas.setFillColor(_NAVY)
    canvas.rect(0, h - 0.52 * inch, w, 0.52 * inch, fill=1, stroke=0)
    canvas.setFillColor(_TEAL)
    canvas.rect(0, h - 0.56 * inch, w, 0.04 * inch, fill=1, stroke=0)

    canvas.setFillColor(_WHITE)
    canvas.setFont("Helvetica-Bold", 9.5)
    canvas.drawString(0.7 * inch, h - 0.33 * inch, "KERYOS")
    canvas.setFillColor(_GRAY_D)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(1.5 * inch, h - 0.33 * inch, "Technical Appendix — Methodology & Reproducibility")
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(_GRAY_M)
    canvas.drawRightString(w - 0.7 * inch, h - 0.33 * inch, f"Page {doc.page}")

    canvas.setFillColor(_NAVY)
    canvas.rect(0, 0, w, 0.38 * inch, fill=1, stroke=0)
    canvas.setFillColor(_GRAY_D)
    canvas.setFont("Helvetica", 6)
    canvas.drawString(0.7 * inch, 0.14 * inch, "For academic / evaluation purposes — Keryos v0.1")
    canvas.drawRightString(w - 0.7 * inch, 0.14 * inch, datetime.now().strftime("%Y-%m-%d %H:%M UTC"))
    canvas.restoreState()


def generate_appendix_pdf(report: dict) -> bytes:
    """
    Technical appendix: methodology, reproducibility parameters, architecture,
    limitations, and academic references.  Suitable for academic evaluation.
    """
    from utils.academic_content import (
        AI_LIMITATIONS,
        ARCHITECTURE_OVERVIEW,
        CLOUD_CLASSES_MASKED,
        COMPARISON_WITH_ALTERNATIVES,
        CONFIDENCE_METHODOLOGY,
        DESIGN_DECISIONS,
        EVALUATION_FRAMEWORK,
        FUTURE_WORK,
        NDVI_THEORY,
        PIPELINE_DIAGRAM,
        PROBLEM_STATEMENT,
        PROJECT_SUBTITLE,
        PROJECT_TITLE,
        QUALITY_SCORING_METHODOLOGY,
        REFERENCES,
        REMOTE_SENSING_LIMITATIONS,
        RESEARCH_QUESTIONS,
        SCORING_WEIGHTS,
        SENTINEL2_BANDS,
        SENTINEL2_RATIONALE,
        SOFTWARE_ENGINEERING_NOTES,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.75 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )
    st = _styles()
    story: list = []

    proc = report.get("processing_metadata") or {}
    integrity = _report_integrity_hash(report)
    ref_id = f"KRY-{integrity[:8].upper()}"
    gen_ts = report.get("generated_at") or datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    gen_display = gen_ts[:19].replace("T", " ") + " UTC"

    def _h(num: str, title: str) -> None:
        story.extend(_section_block(num, title, st))

    def _body(text: str) -> None:
        # Split on double-newlines to get paragraphs; render each as a Paragraph
        for para in text.strip().split("\n\n"):
            para = para.strip()
            if not para:
                continue
            # Minimal markdown-to-reportlab: bold, code blocks, table headers → plain text
            para = para.replace("**", "")
            para = para.replace("`", "")
            if para.startswith("#"):
                para = para.lstrip("#").strip()
                story.append(Paragraph(f"<b>{para}</b>", st["body_bold"]))
            elif para.startswith("|"):
                pass  # skip markdown tables in the text — we render separate tables
            else:
                story.append(Paragraph(para, st["body"]))
        story.append(Spacer(1, 4))

    # ── Cover ─────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 8))
    story.append(Paragraph("TECHNICAL APPENDIX", st["title"]))
    story.append(Paragraph(PROJECT_TITLE, st["subtitle"]))
    story.append(Paragraph(PROJECT_SUBTITLE, st["note"]))
    story.append(Spacer(1, 6))
    cover_rows = [
        ["Report Reference", ref_id, "Generated", gen_display],
        ["Best Acquisition", report.get("best_date", "N/A"), "Crop", report.get("crop_type", "N/A").title()],
        [
            "Claim Period",
            f"{report.get('date_from')} – {report.get('date_to')}",
            "Keryos Version",
            proc.get("keryos_version", "0.1"),
        ],
    ]
    cv_tbl = Table(cover_rows, colWidths=[1.2 * inch, 2.15 * inch, 1.2 * inch, 2.15 * inch])
    cv_tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (0, -1), _MUTED),
                ("TEXTCOLOR", (2, 0), (2, -1), _MUTED),
                ("BACKGROUND", (0, 0), (-1, -1), _GRAY_L),
                ("GRID", (0, 0), (-1, -1), 0.3, _GRAY_M),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(cv_tbl)
    story.append(Spacer(1, 10))

    # ── Section 01: Problem Statement ─────────────────────────────────────────
    _h("01", "PROBLEM STATEMENT")
    _body(PROBLEM_STATEMENT)

    # ── Section 02: Data Source ────────────────────────────────────────────────
    _h("02", "DATA SOURCE — SENTINEL-2 L2A")
    _body(SENTINEL2_RATIONALE)

    # Band table
    story.append(Paragraph("<b>Sentinel-2 Bands Used in This Analysis</b>", st["body_bold"]))
    band_rows = [["Band", "Name", "Wavelength (nm)", "Resolution (m)", "Usage in Keryos"]]
    usage_map = {
        "B02": "True-colour blue channel",
        "B03": "True-colour green; GRI vegetation proxy",
        "B04": "True-colour red; NDVI denominator",
        "B08": "NIR; NDVI numerator",
        "B11": "SWIR false-colour composite",
        "B12": "SWIR false-colour composite",
        "SCL": "Cloud masking (per-pixel classification)",
    }
    for band, info in SENTINEL2_BANDS.items():
        info_dict = cast(dict[str, Any], info)
        band_rows.append(
            [
                band,
                info_dict["name"],
                str(info_dict["wavelength_nm"]) if info_dict["wavelength_nm"] else "—",
                str(info_dict["resolution_m"]),
                usage_map.get(band, ""),
            ]
        )
    band_tbl = Table(band_rows, colWidths=[0.55 * inch, 1.1 * inch, 1.1 * inch, 1.0 * inch, None])
    band_tbl.setStyle(_tbl_style(header_bg=_TEAL))
    story.append(band_tbl)
    story.append(Spacer(1, 6))

    # Cloud classes
    story.append(Paragraph("<b>SCL Cloud Mask Classes Used</b>", st["body_bold"]))
    scl_rows = [["SCL Class", "Label"]] + [[str(k), v] for k, v in CLOUD_CLASSES_MASKED.items()]
    scl_tbl = Table(scl_rows, colWidths=[0.9 * inch, None])
    scl_tbl.setStyle(_tbl_style(header_bg=_NAVY))
    story.append(scl_tbl)
    story.append(Spacer(1, 6))

    # ── Section 03: NDVI Theory ────────────────────────────────────────────────
    _h("03", "VEGETATION INDEX — NDVI")
    _body(NDVI_THEORY)

    # ── Section 04: Processing Pipeline ───────────────────────────────────────
    _h("04", "PROCESSING PIPELINE")
    story.append(
        Paragraph(
            "The pipeline below describes every computational step from user input "
            "to report output.  Each step is independently testable and the parameters "
            "are recorded in the reproducibility section.",
            st["body"],
        )
    )
    story.append(Spacer(1, 4))
    # Render pipeline as a code-style table
    for line in PIPELINE_DIAGRAM.split("\n"):
        story.append(Paragraph(line if line.strip() else "&nbsp;", st["mono"]))
    story.append(Spacer(1, 6))

    # ── Section 05: Quality Scoring ───────────────────────────────────────────
    _h("05", "IMAGE QUALITY SCORING METHODOLOGY")
    _body(QUALITY_SCORING_METHODOLOGY)

    scoring_rows = [["Component", "Weight", "Measurement"]]
    weight_labels = {
        "cloud_clarity": ("Cloud Clarity", "1 − SCL cloud fraction"),
        "spatial_contrast": ("Spatial Contrast", "Luminance std dev, normalised [5, 70]"),
        "brightness": ("Brightness", "Piecewise linear, optimal 80–160 luminance"),
        "vegetation_proxy": ("Vegetation Proxy", "GRI fraction (pixels with (G−R)/(G+R+1) > 0.05)"),
    }
    for key, weight in SCORING_WEIGHTS.items():
        lbl, measurement = weight_labels.get(key, (key, ""))
        scoring_rows.append([lbl, f"{weight:.0%}", measurement])
    sw_tbl = Table(scoring_rows, colWidths=[1.5 * inch, 0.7 * inch, None])
    sw_tbl.setStyle(_tbl_style(header_bg=_NAVY))
    story.append(sw_tbl)
    story.append(Spacer(1, 6))

    # ── Section 06: Confidence Methodology ────────────────────────────────────
    _h("06", "CONFIDENCE SCORE METHODOLOGY")
    _body(CONFIDENCE_METHODOLOGY)

    # ── Section 07: Reproducibility Record ────────────────────────────────────
    _h("07", "REPRODUCIBILITY RECORD")
    story.append(
        Paragraph(
            "All parameters below were used in generating this specific report. "
            "Providing the same AOI, date range, crop type, and these parameters "
            "to Keryos v" + proc.get("keryos_version", "0.1") + " will reproduce an identical analysis.",
            st["body"],
        )
    )
    story.append(Spacer(1, 4))

    params = proc.get("pipeline_parameters") or {}
    thresh = proc.get("quality_thresholds") or {}
    ndvi_c = proc.get("ndvi_classification") or {}

    if params or thresh or ndvi_c:
        merged_rows = [["Parameter Group", "Key", "Value"]]
        for k, v in params.items():
            merged_rows.append(["Pipeline", k, str(v)])
        for k, v in thresh.items():
            merged_rows.append(["Quality Threshold", k, str(v)])
        for k, v in ndvi_c.items():
            merged_rows.append(["NDVI Classification", k, str(v)])
        r_tbl = Table(merged_rows, colWidths=[1.5 * inch, 2.1 * inch, None])
        r_tbl.setStyle(_tbl_style(header_bg=_TEAL))
        story.append(r_tbl)
    else:
        story.append(
            Paragraph(
                "Detailed parameters not available — report was generated by an older version of Keryos.",
                st["note"],
            )
        )
    story.append(Spacer(1, 6))

    # Pipeline steps
    steps = proc.get("pipeline_steps") or []
    if steps:
        story.append(Paragraph("<b>Pipeline Steps Executed</b>", st["body_bold"]))
        for i, step in enumerate(steps, 1):
            story.append(Paragraph(f"{i:02d}. {step}", st["bullet"]))
        story.append(Spacer(1, 6))

    # ── Section 08: System Architecture ───────────────────────────────────────
    _h("08", "SYSTEM ARCHITECTURE")
    _body(ARCHITECTURE_OVERVIEW)

    # ── Section 09: Software Engineering ──────────────────────────────────────
    _h("09", "SOFTWARE ENGINEERING PRACTICES")
    _body(SOFTWARE_ENGINEERING_NOTES)

    # ── Section 10: Limitations ────────────────────────────────────────────────
    _h("10", "LIMITATIONS")
    story.append(Paragraph("<b>Remote Sensing Limitations</b>", st["body_bold"]))
    _body(REMOTE_SENSING_LIMITATIONS)
    story.append(Paragraph("<b>AI Reasoning Layer — Limitations</b>", st["body_bold"]))
    _body(AI_LIMITATIONS)

    # ── Section 11: Research Questions ────────────────────────────────────────
    _h("11", "RESEARCH QUESTIONS")
    story.append(
        Paragraph(
            "The following research questions guided the design of each system component "
            "and constitute the academic framing of the project.",
            st["body"],
        )
    )
    story.append(Spacer(1, 4))
    for rq in RESEARCH_QUESTIONS:
        rq_inner = [
            Paragraph(f"<b>{rq['question']}</b>", st["body_bold"]),
            Paragraph(f"<i>Motivation:</i> {rq['motivation']}", st["body"]),
            Paragraph(f"<i>Approach:</i> {rq['approach']}", st["body"]),
        ]
        rq_box = Table(
            [[Paragraph(f'<b><font color="#0e6e70">{rq["number"]}</font></b>', st["body"]), rq_inner]],
            colWidths=[0.55 * inch, None],
        )
        rq_box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _GRAY_L),
                    ("LINEBEFORE", (0, 0), (0, -1), 3, _TEAL),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(rq_box)
        story.append(Spacer(1, 4))

    # ── Section 12: Evaluation Framework ──────────────────────────────────────
    _h("12", "EVALUATION FRAMEWORK")
    _body(EVALUATION_FRAMEWORK)

    # ── Section 13: Design Decisions ──────────────────────────────────────────
    _h("13", "TECHNOLOGY DESIGN DECISIONS")
    dd_rows = [["Decision", "Rationale (summary)", "Trade-off"]]
    for dd in DESIGN_DECISIONS:
        rationale_short = dd["rationale"].split(".")[0] + "."
        dd_rows.append([dd["decision"], rationale_short, dd["trade_off"]])
    dd_tbl = Table(dd_rows, colWidths=[1.5 * inch, None, 1.6 * inch])
    dd_tbl.setStyle(_tbl_style(header_bg=_TEAL))
    story.append(dd_tbl)
    story.append(Spacer(1, 6))

    # ── Section 14: Comparison with Alternatives ──────────────────────────────
    _h("14", "COMPARISON WITH ALTERNATIVE DATA SOURCES")
    alt_rows = [["Approach", "Res.", "Revisit", "Cost", "All-weather", "Decision"]]
    for alt in COMPARISON_WITH_ALTERNATIVES:
        alt_rows.append(
            [
                alt["approach"],
                alt["spatial_res"],
                alt["temporal_res"],
                alt["cost"].split(" (")[0],
                alt["cloud_immunity"],
                alt["why_not"],
            ]
        )
    alt_tbl = Table(
        alt_rows, colWidths=[1.5 * inch, 0.55 * inch, 0.65 * inch, 0.65 * inch, 0.65 * inch, None]
    )
    alt_tbl.setStyle(_tbl_style(header_bg=_NAVY))
    story.append(alt_tbl)
    story.append(Spacer(1, 6))

    # ── Section 15: Future Work ────────────────────────────────────────────────
    _h("15", "FUTURE SCALABILITY & RESEARCH DIRECTIONS")
    _body(FUTURE_WORK)

    # ── Section 16: References ─────────────────────────────────────────────────
    _h("16", "ACADEMIC REFERENCES")
    for ref in REFERENCES:
        story.append(
            Paragraph(
                f"[{ref['key']}] {ref['citation']}",
                st["bullet"],
            )
        )
        story.append(
            Paragraph(
                f"Relevance: {ref['relevance']}",
                st["note"],
            )
        )
        story.append(Spacer(1, 3))

    # ── Integrity footer ───────────────────────────────────────────────────────
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_GRAY_M, spaceAfter=3))
    story.append(
        Paragraph(
            f"Report reference: <b>{ref_id}</b> &nbsp;·&nbsp; "
            f"Integrity token: <b>{integrity}</b> &nbsp;·&nbsp; "
            f"Keryos v{proc.get('keryos_version', '0.1')} &nbsp;·&nbsp; "
            "Data: Copernicus Sentinel-2 L2A",
            st["mono"],
        )
    )
    story.append(
        Paragraph(
            "This appendix is generated automatically from the same data pipeline "
            "that produced the main verification report.  All figures are deterministic "
            "and reproducible from the parameters listed in Section 07.",
            st["note"],
        )
    )

    doc.build(story, onFirstPage=_draw_chrome_appendix, onLaterPages=_draw_chrome_appendix)
    return buffer.getvalue()
