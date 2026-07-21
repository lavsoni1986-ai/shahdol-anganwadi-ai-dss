# app/services/pdf_generator.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP — Day 3
# Official Government PDF Report Generator
# Uses ReportLab with Noto Devanagari Unicode font for Hindi support.
# Auto-downloads font on first use; falls back to transliterated labels.
# =====================================================================

import io
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────
# Constants & Paths
# ─────────────────────────────────────────────
IST = ZoneInfo("Asia/Kolkata")

_APP_DIR     = Path(__file__).parent.parent
_FONTS_DIR   = _APP_DIR / "static" / "fonts"
_FONT_PATH   = _FONTS_DIR / "NotoSansDevanagari-Regular.ttf"
_FONT_BOLD   = _FONTS_DIR / "NotoSansDevanagari-Bold.ttf"

# Google Fonts CDN — Noto Sans Devanagari (SIL Open Font License)
_FONT_URL_REGULAR = (
    "https://fonts.gstatic.com/s/notosansdevanagari/v25/"
    "TuGKUUVzXI5FBtUq5a8bjKYTZjtgoo_BxVfmrReSPPSuYr0.ttf"
)
_FONT_URL_BOLD = (
    "https://fonts.gstatic.com/s/notosansdevanagari/v25/"
    "TuGKUUVzXI5FBtUq5a8bjKYTZjtgoo_BVcroReSPPSuYr0.ttf"
)

# Government Color Palette
GOV_NAVY    = colors.HexColor("#1e3a8a")
GOV_DARK    = colors.HexColor("#0f1f42")
GOV_LIGHT   = colors.HexColor("#dbeafe")
GOV_ACCENT  = colors.HexColor("#1a56db")
SAFFRON     = colors.HexColor("#FF9933")
INDIA_GREEN = colors.HexColor("#138808")
WHITE       = colors.white
LIGHT_GREY  = colors.HexColor("#f8fafc")
MID_GREY    = colors.HexColor("#e2e8f0")
TEXT_DARK   = colors.HexColor("#1e293b")
TEXT_MUTED  = colors.HexColor("#64748b")

_font_registered = False


# ─────────────────────────────────────────────
# Font Setup — Download & Register
# ─────────────────────────────────────────────

def _ensure_fonts() -> bool:
    """
    Ensures Noto Sans Devanagari TTF fonts are present.
    Downloads from Google Fonts CDN on first call (one-time ~400KB).
    Returns True if Hindi font is available, False if using fallback.
    """
    global _font_registered
    if _font_registered:
        return True

    _FONTS_DIR.mkdir(parents=True, exist_ok=True)

    # Download Regular
    if not _FONT_PATH.exists():
        try:
            logger.info("downloading_devanagari_font", url=_FONT_URL_REGULAR)
            urllib.request.urlretrieve(_FONT_URL_REGULAR, str(_FONT_PATH))
            logger.info("font_downloaded", path=str(_FONT_PATH))
        except Exception as e:
            logger.warning("font_download_failed_regular", error=str(e))
            return False

    # Download Bold
    if not _FONT_BOLD.exists():
        try:
            urllib.request.urlretrieve(_FONT_URL_BOLD, str(_FONT_BOLD))
        except Exception as e:
            logger.warning("font_download_failed_bold", error=str(e))
            # Bold not critical — use regular as fallback for bold
            import shutil
            shutil.copy(str(_FONT_PATH), str(_FONT_BOLD))

    # Register with ReportLab
    try:
        pdfmetrics.registerFont(TTFont("NotoDevanagari", str(_FONT_PATH)))
        pdfmetrics.registerFont(TTFont("NotoDevanagari-Bold", str(_FONT_BOLD)))
        pdfmetrics.registerFontFamily(
            "NotoDevanagari",
            normal="NotoDevanagari",
            bold="NotoDevanagari-Bold",
        )
        _font_registered = True
        logger.info("devanagari_font_registered")
        return True
    except Exception as e:
        logger.error("font_registration_failed", error=str(e))
        return False


def _get_font(bold: bool = False) -> str:
    """Returns font name — Devanagari if available, Helvetica fallback."""
    if _font_registered:
        return "NotoDevanagari-Bold" if bold else "NotoDevanagari"
    return "Helvetica-Bold" if bold else "Helvetica"


# ─────────────────────────────────────────────
# Style Builders
# ─────────────────────────────────────────────

def _build_styles(hindi_available: bool) -> dict:
    """Builds ReportLab paragraph styles with Devanagari or fallback fonts."""
    fn       = _get_font(bold=False)
    fn_bold  = _get_font(bold=True)

    return {
        "title": ParagraphStyle(
            "title",
            fontName=fn_bold, fontSize=15, textColor=WHITE,
            alignment=TA_CENTER, leading=20, spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            fontName=fn, fontSize=10, textColor=colors.HexColor("#bfdbfe"),
            alignment=TA_CENTER, leading=14,
        ),
        "section_head": ParagraphStyle(
            "section_head",
            fontName=fn_bold, fontSize=10, textColor=GOV_NAVY,
            spaceBefore=10, spaceAfter=4, leading=14,
        ),
        "cell_normal": ParagraphStyle(
            "cell_normal",
            fontName=fn, fontSize=8.5, textColor=TEXT_DARK,
            leading=12,
        ),
        "cell_bold": ParagraphStyle(
            "cell_bold",
            fontName=fn_bold, fontSize=8.5, textColor=TEXT_DARK,
            leading=12,
        ),
        "cell_center": ParagraphStyle(
            "cell_center",
            fontName=fn, fontSize=8.5, textColor=TEXT_DARK,
            alignment=TA_CENTER, leading=12,
        ),
        "footer": ParagraphStyle(
            "footer",
            fontName=fn, fontSize=7.5, textColor=TEXT_MUTED,
            alignment=TA_CENTER, leading=10,
        ),
        "meta": ParagraphStyle(
            "meta",
            fontName=fn, fontSize=8, textColor=TEXT_MUTED,
            alignment=TA_RIGHT, leading=11,
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value",
            fontName=fn_bold, fontSize=22, textColor=GOV_NAVY,
            alignment=TA_CENTER, leading=26,
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label",
            fontName=fn, fontSize=7.5, textColor=TEXT_MUTED,
            alignment=TA_CENTER, leading=10,
        ),
        "watermark": ParagraphStyle(
            "watermark",
            fontName=fn_bold, fontSize=9, textColor=GOV_NAVY,
            alignment=TA_CENTER,
        ),
        "sign_label": ParagraphStyle(
            "sign_label",
            fontName=fn, fontSize=8, textColor=TEXT_DARK,
            alignment=TA_CENTER, leading=11,
        ),
    }


# ─────────────────────────────────────────────
# Table Style Builders
# ─────────────────────────────────────────────

def _kpi_table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GOV_NAVY),
        ("TEXTCOLOR",  (0, 0), (-1, 0), WHITE),
        ("FONTNAME",   (0, 0), (-1, 0), _get_font(bold=True)),
        ("FONTSIZE",   (0, 0), (-1, 0), 8),
        ("ALIGN",      (0, 0), (-1, 0), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ("ALIGN",      (1, 1), (-1, -1), "CENTER"),
        ("FONTNAME",   (1, 1), (-1, -1), _get_font()),
        ("FONTSIZE",   (1, 1), (-1, -1), 8.5),
        ("FONTNAME",   (0, 1), (0, -1), _get_font(bold=True)),
        ("GRID",       (0, 0), (-1, -1), 0.5, MID_GREY),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ])


def _submissions_table_style(row_count: int) -> TableStyle:
    styles = [
        ("BACKGROUND",    (0, 0), (-1, 0), GOV_NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), _get_font(bold=True)),
        ("FONTSIZE",      (0, 0), (-1, 0), 7),
        ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
        ("FONTNAME",      (0, 1), (-1, -1), _get_font()),
        ("FONTSIZE",      (0, 1), (-1, -1), 7),
        ("GRID",          (0, 0), (-1, -1), 0.4, MID_GREY),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
    ]
    return TableStyle(styles)


def _block_table_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), colors.HexColor("#1e40af")),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), _get_font(bold=True)),
        ("FONTSIZE",      (0, 0), (-1, 0), 8),
        ("ALIGN",         (1, 0), (-1, -1), "CENTER"),
        ("FONTNAME",      (0, 1), (-1, -1), _get_font()),
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ("GRID",          (0, 0), (-1, -1), 0.5, MID_GREY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        # Highlight approved row cells
        ("TEXTCOLOR",     (2, 1), (2, -1), colors.HexColor("#166534")),
        ("TEXTCOLOR",     (3, 1), (3, -1), colors.HexColor("#92400e")),
    ])


# ─────────────────────────────────────────────
# Colour-coded status badge (text)
# ─────────────────────────────────────────────

def _status_color(status: str) -> colors.Color:
    mapping = {
        "APPROVED": colors.HexColor("#166534"),
        "FLAGGED":  colors.HexColor("#92400e"),
        "RECEIVED": colors.HexColor("#1e40af"),
        "REJECTED": colors.HexColor("#991b1b"),
    }
    return mapping.get(status, TEXT_DARK)


# ═════════════════════════════════════════════════════════════════════
# MAIN PDF GENERATION FUNCTION
# ═════════════════════════════════════════════════════════════════════

def generate_daily_report_pdf(
    report_date: str,
    stats: dict,
    submissions: list,
    block_name: Optional[str] = None,
    status_filter: Optional[str] = None,
    generated_by: str = "BharatOS System",
) -> bytes:
    """
    Generates an official Government-style A4 PDF Daily Report.

    Args:
        report_date:    Date string (DD/MM/YYYY) for the report header
        stats:          Dict with keys: reported_today, approved_today,
                        flagged_today, pending_review, coverage_percent
        submissions:    List of DailySubmission ORM objects for the detail table
        block_name:     Optional block filter applied
        status_filter:  Optional status filter applied
        generated_by:   Officer/system that generated this report

    Returns:
        bytes: PDF file content as bytes (ready for HTTP streaming)
    """
    hindi_ok = _ensure_fonts()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=2.0 * cm,
        title=f"Shahdol AWC Daily Report — {report_date}",
        author="BharatOS — District Administration Shahdol",
        subject="Anganwadi Digital Verification Daily Report",
    )

    S = _build_styles(hindi_ok)
    story = []
    page_w = A4[0] - 3 * cm   # usable width

    # ── TRICOLOR TOP STRIP ─────────────────────────────────────────
    strip_data = [["", "", ""]]
    strip_table = Table(strip_data, colWidths=[page_w / 3] * 3, rowHeights=[5])
    strip_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), SAFFRON),
        ("BACKGROUND", (1, 0), (1, 0), WHITE),
        ("BACKGROUND", (2, 0), (2, 0), INDIA_GREEN),
        ("LINEBELOW",  (0, 0), (-1, 0), 0.5, MID_GREY),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    story.append(strip_table)
    story.append(Spacer(1, 4))

    # ── NAVY HEADER BLOCK ──────────────────────────────────────────
    header_data = [[
        Paragraph("🇮🇳  जिला प्रशासन शहडोल", S["title"]),
    ], [
        Paragraph("महिला एवं बाल विकास विभाग — आंगनवाड़ी डिजिटल सत्यापन प्रणाली", S["subtitle"]),
    ], [
        Paragraph("BharatOS | Madhya Pradesh | Pilot: Sohagpur Block", S["subtitle"]),
    ]]
    header_table = Table(header_data, colWidths=[page_w])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), GOV_NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 6))

    # ── REPORT METADATA ROW ────────────────────────────────────────
    now_ist = datetime.now(IST)
    filter_desc = []
    if block_name:
        filter_desc.append(f"ब्लॉक: {block_name}")
    if status_filter:
        filter_desc.append(f"स्थिति: {status_filter}")
    filter_str = "  |  ".join(filter_desc) if filter_desc else "सभी केंद्र"

    meta_data = [[
        Paragraph(f"<b>रिपोर्ट दिनांक:</b> {report_date}", S["cell_normal"]),
        Paragraph(f"<b>फ़िल्टर:</b> {filter_str}", S["cell_normal"]),
        Paragraph(
            f"<b>उत्पन्न समय:</b> {now_ist.strftime('%d/%m/%Y %I:%M %p IST')}",
            S["meta"]
        ),
    ]]
    meta_table = Table(meta_data, colWidths=[page_w * 0.33] * 3)
    meta_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), LIGHT_GREY),
        ("LINEABOVE",     (0, 0), (-1, 0), 0.5, GOV_NAVY),
        ("LINEBELOW",     (0, -1), (-1, -1), 0.5, GOV_NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # ── SECTION 1: KPI SUMMARY CARDS ──────────────────────────────
    story.append(Paragraph("■  कार्यकारी सारांश (Executive Summary)", S["section_head"]))

    kpi_data = [
        [
            Paragraph(str(stats.get("reported_today", 0)), S["kpi_value"]),
            Paragraph(str(stats.get("approved_today", 0)), S["kpi_value"]),
            Paragraph(str(stats.get("flagged_today", 0)),  S["kpi_value"]),
            Paragraph(str(stats.get("pending_review", 0)), S["kpi_value"]),
            Paragraph(f"{stats.get('coverage_percent', 0)}%", S["kpi_value"]),
        ],
        [
            Paragraph("आज प्रेषित", S["kpi_label"]),
            Paragraph("सत्यापित", S["kpi_label"]),
            Paragraph("फ्लैग्ड", S["kpi_label"]),
            Paragraph("लंबित समीक्षा", S["kpi_label"]),
            Paragraph("कवरेज", S["kpi_label"]),
        ],
    ]
    kpi_col = page_w / 5
    kpi_table = Table(kpi_data, colWidths=[kpi_col] * 5, rowHeights=[30, 20])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), colors.HexColor("#eff6ff")),
        ("BACKGROUND",    (1, 0), (1, -1), colors.HexColor("#f0fdf4")),
        ("BACKGROUND",    (2, 0), (2, -1), colors.HexColor("#fefce8")),
        ("BACKGROUND",    (3, 0), (3, -1), colors.HexColor("#fff7ed")),
        ("BACKGROUND",    (4, 0), (4, -1), colors.HexColor("#f5f3ff")),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",          (0, 0), (-1, -1), 0.5, MID_GREY),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TEXTCOLOR",     (1, 0), (1, 0), colors.HexColor("#166534")),
        ("TEXTCOLOR",     (2, 0), (2, 0), colors.HexColor("#92400e")),
        ("TEXTCOLOR",     (3, 0), (3, 0), colors.HexColor("#9a3412")),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 12))

    # ── SECTION 2: BLOCK-WISE BREAKDOWN ───────────────────────────
    story.append(Paragraph("■  ब्लॉक-वार विवरण (Block-wise Breakdown)", S["section_head"]))

    block_stats: dict[str, dict] = {}
    for s in submissions:
        bn = getattr(s, "block_name", None) or "अज्ञात"
        if bn not in block_stats:
            block_stats[bn] = {"total": 0, "approved": 0, "flagged": 0, "pending": 0}
        block_stats[bn]["total"] += 1
        st = getattr(s, "status", "")
        if st == "APPROVED": block_stats[bn]["approved"] += 1
        elif st == "FLAGGED": block_stats[bn]["flagged"] += 1
        elif st == "RECEIVED": block_stats[bn]["pending"] += 1

    block_rows = [[
        Paragraph("ब्लॉक नाम", S["cell_bold"]),
        Paragraph("कुल", S["cell_bold"]),
        Paragraph("✓ सत्यापित", S["cell_bold"]),
        Paragraph("⚑ फ्लैग्ड", S["cell_bold"]),
        Paragraph("◎ लंबित", S["cell_bold"]),
    ]]
    for bn, bst in sorted(block_stats.items()):
        block_rows.append([
            Paragraph(bn, S["cell_normal"]),
            Paragraph(str(bst["total"]),    S["cell_center"]),
            Paragraph(str(bst["approved"]), S["cell_center"]),
            Paragraph(str(bst["flagged"]),  S["cell_center"]),
            Paragraph(str(bst["pending"]),  S["cell_center"]),
        ])

    if len(block_rows) == 1:
        block_rows.append([Paragraph("डेटा उपलब्ध नहीं", S["cell_normal"]), "", "", "", ""])

    b_col = [page_w * 0.35, page_w * 0.15, page_w * 0.17, page_w * 0.17, page_w * 0.16]
    block_table = Table(block_rows, colWidths=b_col)
    block_table.setStyle(_block_table_style())
    story.append(block_table)
    story.append(Spacer(1, 12))

    # ── SECTION 3: SUBMISSION DETAIL TABLE ────────────────────────
    max_rows = 25
    display_submissions = submissions[:max_rows]
    overflow = len(submissions) - max_rows if len(submissions) > max_rows else 0

    story.append(Paragraph(
        f"■  प्रेषण विवरण — शीर्ष {min(len(submissions), max_rows)} रिकॉर्ड",
        S["section_head"]
    ))

    sub_headers = [
        Paragraph("#",              S["cell_bold"]),
        Paragraph("AWC ID",         S["cell_bold"]),
        Paragraph("केंद्र नाम",      S["cell_bold"]),
        Paragraph("ब्लॉक",           S["cell_bold"]),
        Paragraph("कार्यकर्ता",       S["cell_bold"]),
        Paragraph("समय (IST)",       S["cell_bold"]),
        Paragraph("GPS",            S["cell_bold"]),
        Paragraph("स्थिति",          S["cell_bold"]),
    ]
    sub_rows = [sub_headers]

    for idx, s in enumerate(display_submissions, 1):
        ts = ""
        sub_ts = getattr(s, "submission_timestamp", None)
        if sub_ts:
            ts = sub_ts.astimezone(IST).strftime("%d/%m %I:%M%p")

        gps = "—"
        lat = getattr(s, "latitude", None)
        lon = getattr(s, "longitude", None)
        if lat and lon:
            gps = f"{float(lat):.3f},{float(lon):.3f}"

        st = getattr(s, "status", "—")
        st_style = ParagraphStyle(
            "st", parent=S["cell_center"],
            textColor=_status_color(st),
            fontName=_get_font(bold=True),
        )

        sub_rows.append([
            Paragraph(str(idx), S["cell_center"]),
            Paragraph(getattr(s, "awc_id", "") or "—",      S["cell_normal"]),
            Paragraph(getattr(s, "center_name", "") or "—",  S["cell_normal"]),
            Paragraph(getattr(s, "block_name", "") or "—",   S["cell_normal"]),
            Paragraph(getattr(s, "worker_name", "") or "—",  S["cell_normal"]),
            Paragraph(ts or "—",                              S["cell_center"]),
            Paragraph(gps,                                    S["cell_center"]),
            Paragraph(st,                                     st_style),
        ])

    s_cols = [
        page_w * 0.04,   # #
        page_w * 0.12,   # AWC ID
        page_w * 0.16,   # center
        page_w * 0.13,   # block
        page_w * 0.17,   # worker
        page_w * 0.12,   # time
        page_w * 0.14,   # gps
        page_w * 0.12,   # status
    ]
    sub_table = Table(sub_rows, colWidths=s_cols, repeatRows=1)
    sub_table.setStyle(_submissions_table_style(len(sub_rows)))
    story.append(sub_table)

    if overflow > 0:
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f"... और {overflow} अतिरिक्त रिकॉर्ड — पूर्ण डेटा के लिए CSV डाउनलोड करें।",
            S["meta"]
        ))

    story.append(Spacer(1, 14))

    # ── SECTION 4: OFFICIAL SIGN-OFF ──────────────────────────────
    story.append(HRFlowable(width=page_w, thickness=0.8, color=GOV_NAVY))
    story.append(Spacer(1, 10))

    sign_col = page_w / 3
    sign_data = [[
        Paragraph("___________________________", S["sign_label"]),
        Paragraph("___________________________", S["sign_label"]),
        Paragraph("___________________________", S["sign_label"]),
    ], [
        Paragraph("सेक्टर सुपरवाइजर\nसोहागपुर ब्लॉक", S["sign_label"]),
        Paragraph("CDPO शहडोल\nमहिला एवं बाल विकास", S["sign_label"]),
        Paragraph("DPO / CEO\nजिला शहडोल", S["sign_label"]),
    ]]
    sign_table = Table(sign_data, colWidths=[sign_col] * 3)
    sign_table.setStyle(TableStyle([
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTNAME",      (0, 1), (-1, 1), _get_font()),
        ("FONTSIZE",      (0, 1), (-1, 1), 7.5),
        ("TEXTCOLOR",     (0, 1), (-1, 1), TEXT_MUTED),
    ]))
    story.append(sign_table)
    story.append(Spacer(1, 8))

    # ── FOOTER ────────────────────────────────────────────────────
    story.append(HRFlowable(width=page_w, thickness=0.4, color=MID_GREY))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"यह रिपोर्ट BharatOS डिजिटल सत्यापन प्रणाली द्वारा स्वचालित रूप से उत्पन्न की गई है।  "
        f"उत्पन्न: {now_ist.strftime('%d/%m/%Y %I:%M %p IST')}  |  "
        f"संस्करण: 3.0  |  जिला शहडोल — मध्यप्रदेश  |  "
        f"यह दस्तावेज़ आधिकारिक उपयोग के लिए है।",
        S["footer"]
    ))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    logger.info(
        "pdf_report_generated",
        date=report_date,
        submissions_count=len(submissions),
        size_kb=round(len(pdf_bytes) / 1024, 1),
    )
    return pdf_bytes
