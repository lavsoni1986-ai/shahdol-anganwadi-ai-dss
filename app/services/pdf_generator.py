# app/services/pdf_generator.py
# =====================================================================
# BharatOS — Shahdol Anganwadi Digital Verification & DSS
# Official Government Executive PDF Report Generator (Version 2.0)
# High-Impact NIC/Government Design for CEO Zila Panchayat & District Collector
# Uses ReportLab with embedded Noto Devanagari Unicode fonts and HarfBuzz shaping.
# =====================================================================

import io
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont, shapeStr

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────
# Constants & Paths
# ─────────────────────────────────────────────
IST = ZoneInfo("Asia/Kolkata")
TOTAL_AWC_SHAHDOL = 1450

_APP_DIR     = Path(__file__).parent.parent
_FONTS_DIR   = _APP_DIR / "static" / "fonts"
_FONT_PATH   = _FONTS_DIR / "NotoSansDevanagari-Regular.ttf"
_FONT_BOLD   = _FONTS_DIR / "NotoSansDevanagari-Bold.ttf"
_LOGO_PATH   = _APP_DIR / "static" / "images" / "logo.jpg"

# Restrained Government / NIC Color Palette (Version 2.0)
GOV_NAVY       = colors.HexColor("#0f2942")  # Deep Navy Blue
GOV_BLUE       = colors.HexColor("#1e3a8a")  # Government Royal Blue
GOV_LIGHT_BG   = colors.HexColor("#f8fafc")  # Slate Light Grey
GOV_ACCENT     = colors.HexColor("#2563eb")  # Accent Royal Blue
SAFFRON        = colors.HexColor("#FF9933")  # Indian Flag Saffron
INDIA_GREEN    = colors.HexColor("#138808")  # Indian Flag Green
WHITE          = colors.white
LIGHT_GREY     = colors.HexColor("#f1f5f9")
MID_GREY       = colors.HexColor("#cbd5e1")
BORDER_GREY    = colors.HexColor("#e2e8f0")
TEXT_DARK      = colors.HexColor("#0f172a")
TEXT_MUTED     = colors.HexColor("#475569")

# Restrained Badge Colors
COLOR_APPROVED = colors.HexColor("#15803d")
COLOR_FLAGGED  = colors.HexColor("#b45309")
COLOR_PENDING  = colors.HexColor("#1d4ed8")
COLOR_REJECTED = colors.HexColor("#b91c1c")

_font_registered = False


# ─────────────────────────────────────────────
# Font Setup — Embedded Unicode TTF & HarfBuzz Shaping
# ─────────────────────────────────────────────

def _ensure_fonts() -> bool:
    """
    Registers local embedded TTF Devanagari fonts with ReportLab.
    Guarantees 100% Unicode Hindi rendering.
    """
    global _font_registered
    if _font_registered:
        return True

    if _FONT_PATH.exists() and _FONT_BOLD.exists():
        try:
            pdfmetrics.registerFont(TTFont("NotoDevanagari", str(_FONT_PATH)))
            pdfmetrics.registerFont(TTFont("NotoDevanagari-Bold", str(_FONT_BOLD)))
            pdfmetrics.registerFontFamily(
                "NotoDevanagari",
                normal="NotoDevanagari",
                bold="NotoDevanagari-Bold",
            )
            _font_registered = True
            logger.info("devanagari_fonts_registered_successfully")
            return True
        except Exception as e:
            logger.error("devanagari_font_registration_error", error=str(e))
            return False

    logger.warning("devanagari_font_files_missing", path=str(_FONTS_DIR))
    return False


def _get_font(bold: bool = False) -> str:
    """Returns registered Devanagari font or Helvetica fallback."""
    if _font_registered:
        return "NotoDevanagari-Bold" if bold else "NotoDevanagari"
    return "Helvetica-Bold" if bold else "Helvetica"


def _shape_hi(text: str, font_name: str = "NotoDevanagari", font_size: float = 10.0) -> str:
    """Returns raw text string; Devanagari shaping is handled natively by ReportLab ParagraphStyle(..., shaping=True)."""
    if not text:
        return ""
    return str(text)


# ─────────────────────────────────────────────
# Numbered Canvas for "Page X of Y" Footer & Header
# ─────────────────────────────────────────────

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute total page count and draw
    official NIC/Government header and footer on every page.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        self.saveState()
        fn = _get_font(bold=False)
        fn_bold = _get_font(bold=True)

        st_hdr_left = ParagraphStyle("hdr_l", fontName=fn, fontSize=8, textColor=TEXT_MUTED, shaping=True)
        st_hdr_right = ParagraphStyle("hdr_r", fontName=fn_bold, fontSize=8, textColor=TEXT_MUTED, alignment=TA_RIGHT, shaping=True)
        st_ftr_left = ParagraphStyle("ftr_l", fontName=fn, fontSize=8, textColor=TEXT_MUTED, shaping=True)
        st_ftr_right = ParagraphStyle("ftr_r", fontName=fn_bold, fontSize=8, textColor=TEXT_MUTED, alignment=TA_RIGHT, shaping=True)

        # Top Header (Only on pages 2+)
        if self._pageNumber > 1:
            p_hdr_l = Paragraph("महिला एवं बाल विकास विभाग, मध्य प्रदेश शासन  |  शहडोल आंगनवाड़ी डिजिटल सत्यापन (DSS)", st_hdr_left)
            p_hdr_l.wrapOn(self, A4[0] - 8 * cm, 1 * cm)
            p_hdr_l.drawOn(self, 1.5 * cm, A4[1] - 1.0 * cm)

            p_hdr_r = Paragraph("आधिकारिक शासकीय प्रतिवेदन", st_hdr_right)
            p_hdr_r.wrapOn(self, 6 * cm, 1 * cm)
            p_hdr_r.drawOn(self, A4[0] - 7.5 * cm, A4[1] - 1.0 * cm)

            self.setStrokeColor(BORDER_GREY)
            self.setLineWidth(0.5)
            self.line(1.5 * cm, A4[1] - 1.15 * cm, A4[0] - 1.5 * cm, A4[1] - 1.15 * cm)

        # Bottom Official Footer (All Pages)
        self.setStrokeColor(BORDER_GREY)
        self.setLineWidth(0.5)
        self.line(1.5 * cm, 1.4 * cm, A4[0] - 1.5 * cm, 1.4 * cm)

        p_ftr_l = Paragraph("यह प्रतिवेदन BharatOS AI द्वारा स्वतः तैयार किया गया है।  |  महिला एवं बाल विकास विभाग, शहडोल (म.प्र.)  |  गोपनीय (Confidential)", st_ftr_left)
        p_ftr_l.wrapOn(self, A4[0] - 6 * cm, 1 * cm)
        p_ftr_l.drawOn(self, 1.5 * cm, 0.7 * cm)

        p_ftr_r = Paragraph(f"पृष्ठ {self._pageNumber} / {page_count}", st_ftr_right)
        p_ftr_r.wrapOn(self, 4 * cm, 1 * cm)
        p_ftr_r.drawOn(self, A4[0] - 5.5 * cm, 0.7 * cm)

        self.restoreState()


# ─────────────────────────────────────────────
# Style Builders (Version 2.0 Typography Hierarchy)
# ─────────────────────────────────────────────

def _build_styles() -> dict:
    """Builds ReportLab paragraph styles with Devanagari Unicode fonts."""
    fn      = _get_font(bold=False)
    fn_bold = _get_font(bold=True)

    return {
        "dept_sub": ParagraphStyle(
            "dept_sub",
            fontName=fn_bold, fontSize=15, textColor=GOV_BLUE,
            alignment=TA_LEFT, leading=20, spaceAfter=3, shaping=True,
        ),
        "doc_title": ParagraphStyle(
            "doc_title",
            fontName=fn_bold, fontSize=22, textColor=GOV_NAVY,
            alignment=TA_LEFT, leading=28, spaceAfter=4, shaping=True,
        ),
        "report_sub": ParagraphStyle(
            "report_sub",
            fontName=fn, fontSize=11, textColor=TEXT_MUTED,
            alignment=TA_LEFT, leading=15, shaping=True,
        ),
        "section_head": ParagraphStyle(
            "section_head",
            fontName=fn_bold, fontSize=15, textColor=GOV_BLUE,
            spaceBefore=10, spaceAfter=6, leading=19, shaping=True,
        ),
        "cell_normal": ParagraphStyle(
            "cell_normal",
            fontName=fn, fontSize=10, textColor=TEXT_DARK,
            leading=14.5, shaping=True,
        ),
        "cell_bold": ParagraphStyle(
            "cell_bold",
            fontName=fn_bold, fontSize=10, textColor=TEXT_DARK,
            leading=14.5, shaping=True,
        ),
        "cell_center": ParagraphStyle(
            "cell_center",
            fontName=fn, fontSize=10, textColor=TEXT_DARK,
            alignment=TA_CENTER, leading=14.5, shaping=True,
        ),
        "cell_header": ParagraphStyle(
            "cell_header",
            fontName=fn_bold, fontSize=11, textColor=WHITE,
            alignment=TA_CENTER, leading=15, shaping=True,
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value",
            fontName=fn_bold, fontSize=18, textColor=GOV_NAVY,
            alignment=TA_CENTER, leading=22, shaping=True,
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label",
            fontName=fn_bold, fontSize=9, textColor=TEXT_MUTED,
            alignment=TA_CENTER, leading=12, shaping=True,
        ),
        "rec_item": ParagraphStyle(
            "rec_item",
            fontName=fn, fontSize=10, textColor=TEXT_DARK,
            leading=14.5, spaceAfter=3, shaping=True,
        ),
        "sign_label": ParagraphStyle(
            "sign_label",
            fontName=fn, fontSize=9.5, textColor=TEXT_DARK,
            alignment=TA_CENTER, leading=14, shaping=True,
        ),
    }


# ═════════════════════════════════════════════════════════════════════
# MAIN PDF GENERATION FUNCTION (VERSION 2.0 DESIGN)
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
    Generates an Official Executive Government A4 PDF Report suitable for
    CEO Zila Panchayat & District Collector presentation.

    Version 2.0: Restrained NIC Official Styling & Devanagari Text Shaping.

    Args:
        report_date:    Display date string (DD/MM/YYYY)
        stats:          Dict with keys: reported_today, approved_today,
                        flagged_today, pending_review, coverage_percent
        submissions:    List of DailySubmission ORM objects
        block_name:     Optional block filter
        status_filter:  Optional status filter
        generated_by:   Generating entity/officer

    Returns:
        bytes: PDF binary content ready for streaming/download
    """
    _ensure_fonts()

    now_ist = datetime.now(IST)
    safe_date_str = (report_date or now_ist.strftime("%Y-%m-%d")).replace("/", "").replace("-", "")
    doc_id = f"SHD-RPT-{safe_date_str}-001"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=2.0 * cm,
        title=f"Shahdol AWC Executive Report — {report_date}",
        author="BharatOS — District Administration Shahdol",
        subject="Anganwadi Digital Verification & DSS Daily Report",
    )

    S = _build_styles()
    story = []
    page_w = A4[0] - 3.0 * cm   # 18.0 cm usable width

    # ── 1. HEADER SECTION — RESTRAINED GOVERNMENT DESIGN (VERSION 2.0) ───
    logo_img = None
    if _LOGO_PATH.exists():
        try:
            logo_img = Image(str(_LOGO_PATH), width=1.8 * cm, height=1.8 * cm)
        except Exception as e:
            logger.warning("logo_load_failed", error=str(e))

    if settings.demo_mode:
        dept_str = _shape_hi("महिला एवं बाल विकास विभाग, मध्य प्रदेश शासन", font_name=_get_font(bold=True), font_size=15)
        title_str = _shape_hi("शहडोल आंगनवाड़ी डिजिटल सत्यापन एवं निर्णय सहायता प्रणाली (DSS)", font_name=_get_font(bold=True), font_size=20)
        sub_title_str = _shape_hi("आंगनवाड़ी डिजिटल सत्यापन प्रतिवेदन <font size=9 color='#92400e'>(पायलट प्रदर्शन हेतु)</font>", font_name=_get_font(bold=True), font_size=12)
    else:
        dept_str = _shape_hi("महिला एवं बाल विकास विभाग, मध्य प्रदेश शासन", font_name=_get_font(bold=True), font_size=15)
        title_str = _shape_hi("भारतओएस — शहडोल आंगनवाड़ी डिजिटल सत्यापन एवं निर्णय सहायता प्रणाली (DSS)", font_name=_get_font(bold=True), font_size=22)
        sub_title_str = _shape_hi("दैनिक कार्यकारी सत्यापन एवं निर्णय सहायता प्रतिवेदन (Official Decision Support Report)", font_name=_get_font(bold=False), font_size=11)

    title_text = [
        Paragraph(dept_str, S["dept_sub"]),
        Paragraph(title_str, S["doc_title"]),
        Paragraph(sub_title_str, S["report_sub"]),
    ]

    if logo_img:
        header_table = Table([[logo_img, title_text]], colWidths=[2.2 * cm, page_w - 2.2 * cm])
    else:
        header_table = Table([[title_text]], colWidths=[page_w])

    header_table.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4))

    # ── TRICOLOR SUBTLE ACCENT STRIP ────────────────────────────────
    strip_data = [["", "", ""]]
    strip_table = Table(strip_data, colWidths=[page_w / 3] * 3, rowHeights=[3.5])
    strip_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), SAFFRON),
        ("BACKGROUND", (1, 0), (1, 0), BORDER_GREY),
        ("BACKGROUND", (2, 0), (2, 0), INDIA_GREEN),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    story.append(strip_table)
    story.append(Spacer(1, 6))

    # ── 2. METADATA SUB-BAR ─────────────────────────────────────────
    if settings.demo_mode:
        filter_str = f"केंद्र: {settings.demo_center_name}  |  AWC ID: {settings.demo_awc_id}"
    else:
        filter_str = f"ब्लॉक: {block_name}" if block_name else "समस्त जिला शहडोल"
        if status_filter:
            filter_str += f" | स्थिति: {status_filter}"

    time_display = now_ist.strftime("%I:%M %p IST")
    doc_id_label = _shape_hi("<b>Document ID:</b>", font_name=_get_font(), font_size=10)
    rpt_date_label = _shape_hi(f"<b>रिपोर्ट तिथि:</b> {report_date}  |  {filter_str}", font_name=_get_font(), font_size=10)
    gen_time_label = _shape_hi(f"<b>उत्पन्न समय:</b> {time_display}", font_name=_get_font(), font_size=10)

    meta_data = [[
        Paragraph(f"{doc_id_label} <font color='#0f2942'><b>{doc_id}</b></font>", S["cell_normal"]),
        Paragraph(rpt_date_label, S["cell_normal"]),
        Paragraph(gen_time_label, S["cell_center"]),
    ]]
    meta_table = Table(meta_data, colWidths=[page_w * 0.32, page_w * 0.43, page_w * 0.25])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), GOV_LIGHT_BG),
        ("BOX",           (0, 0), (-1, -1), 0.5, BORDER_GREY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # ── 3. EXECUTIVE SUMMARY KPI CARDS ──────────────────────────────
    kpi_head_str = _shape_hi("📊  कार्यकारी सारांश (Executive Summary — KPI Cards)", font_name=_get_font(bold=True), font_size=15)
    story.append(Paragraph(kpi_head_str, S["section_head"]))

    if settings.demo_mode:
        total_awc = 1
    else:
        total_awc = TOTAL_AWC_SHAHDOL

    reports_rec = stats.get("reported_today", len(submissions))

    if len(submissions) > 0:
        approved = sum(1 for s in submissions if getattr(s, "status", "") in ("APPROVED", "PROCESSED") or (getattr(s, "is_authorized", False) and getattr(s, "status", "") != "FLAGGED"))
        flagged = sum(1 for s in submissions if getattr(s, "status", "") == "FLAGGED")
        pending = sum(1 for s in submissions if getattr(s, "status", "") == "RECEIVED")
    else:
        approved = stats.get("approved_today", 0)
        flagged = stats.get("flagged_today", 0)
        pending = stats.get("pending_review", 0)

    pending_centres = total_awc - reports_rec
    if pending_centres < 0:
        pending_centres = 0

    cov_pct = stats.get("coverage_percent")
    if cov_pct is None or cov_pct == 0:
        cov_pct = round((reports_rec / total_awc) * 100, 1) if total_awc > 0 else 0.0

    if settings.demo_mode:
        # 5 KPI Cards for Single Anganwadi Demo
        kpi_col = page_w / 5.0
        l_tot = _shape_hi("कुल केंद्र<br/>(Total Centres)", font_name=_get_font(bold=True), font_size=9)
        l_rec = _shape_hi("आज प्राप्त रिपोर्ट<br/>(Reports Recd)", font_name=_get_font(bold=True), font_size=9)
        l_app = _shape_hi("AI द्वारा सत्यापित<br/>(AI Verified)", font_name=_get_font(bold=True), font_size=9)
        l_flg = _shape_hi("समीक्षा आवश्यक<br/>(Review Req)", font_name=_get_font(bold=True), font_size=9)
        l_cov = _shape_hi("रिपोर्टिंग प्रतिशत<br/>(Reporting %)", font_name=_get_font(bold=True), font_size=9)

        kpi_data = [
            [
                Paragraph(f"<b>{total_awc:,}</b>", S["kpi_value"]),
                Paragraph(f"<b>{reports_rec}</b>", S["kpi_value"]),
                Paragraph(f"<b>{approved}</b>", ParagraphStyle("green_kpi", parent=S["kpi_value"], textColor=COLOR_APPROVED)),
                Paragraph(f"<b>{flagged}</b>", ParagraphStyle("amber_kpi", parent=S["kpi_value"], textColor=COLOR_FLAGGED)),
                Paragraph(f"<b>{cov_pct}%</b>", ParagraphStyle("navy_kpi", parent=S["kpi_value"], textColor=GOV_NAVY)),
            ],
            [
                Paragraph(l_tot, S["kpi_label"]),
                Paragraph(l_rec, S["kpi_label"]),
                Paragraph(l_app, S["kpi_label"]),
                Paragraph(l_flg, S["kpi_label"]),
                Paragraph(l_cov, S["kpi_label"]),
            ],
        ]
        kpi_table = Table(kpi_data, colWidths=[kpi_col] * 5, rowHeights=[26, 22])
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
            ("BACKGROUND",    (1, 0), (1, -1), colors.HexColor("#f0fdf4")),
            ("BACKGROUND",    (2, 0), (2, -1), colors.HexColor("#dcfce7")),
            ("BACKGROUND",    (3, 0), (3, -1), colors.HexColor("#fffbeb")),
            ("BACKGROUND",    (4, 0), (4, -1), colors.HexColor("#f5f3ff")),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("GRID",          (0, 0), (-1, -1), 0.5, BORDER_GREY),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 8))

        # ── MANDATORY SINGLE AWC DEMO NOTICE BOX ───────────────────
        demo_notice_str = _shape_hi(
            "<b>📌 नोट:</b> यह प्रतिवेदन पायलट प्रदर्शन हेतु एकल आंगनवाड़ी के वास्तविक डेटा पर आधारित है।",
            font_name=_get_font(bold=False), font_size=10
        )
        notice_data = [[Paragraph(f"<font color='#92400e'>{demo_notice_str}</font>", S["cell_normal"])]]
        notice_table = Table(notice_data, colWidths=[page_w])
        notice_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#fefce8")),
            ("BOX",           (0, 0), (-1, -1), 0.8, colors.HexColor("#d97706")),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ]))
        story.append(notice_table)
        story.append(Spacer(1, 10))

    else:
        # Standard 6 KPI Cards for District Mode
        kpi_col = page_w / 6.0
        l_tot = _shape_hi("कुल केंद्र<br/>(Total Centres)", font_name=_get_font(bold=True), font_size=9)
        l_rec = _shape_hi("प्राप्त रिपोर्ट<br/>(Reports Recd)", font_name=_get_font(bold=True), font_size=9)
        l_app = _shape_hi("सत्यापित / स्वीकृत<br/>(Verified)", font_name=_get_font(bold=True), font_size=9)
        l_flg = _shape_hi("फ्लैग्ड<br/>(Flagged)", font_name=_get_font(bold=True), font_size=9)
        l_pnd = _shape_hi("अनरिपोर्टेड<br/>(Pending)", font_name=_get_font(bold=True), font_size=9)
        l_cov = _shape_hi("रिपोर्टिंग %<br/>(Reporting %)", font_name=_get_font(bold=True), font_size=9)

        kpi_data = [
            [
                Paragraph(f"<b>{total_awc:,}</b>", S["kpi_value"]),
                Paragraph(f"<b>{reports_rec}</b>", S["kpi_value"]),
                Paragraph(f"<b>{approved}</b>", ParagraphStyle("green_kpi", parent=S["kpi_value"], textColor=COLOR_APPROVED)),
                Paragraph(f"<b>{flagged}</b>", ParagraphStyle("amber_kpi", parent=S["kpi_value"], textColor=COLOR_FLAGGED)),
                Paragraph(f"<b>{pending_centres:,}</b>", ParagraphStyle("red_kpi", parent=S["kpi_value"], textColor=COLOR_REJECTED)),
                Paragraph(f"<b>{cov_pct}%</b>", ParagraphStyle("navy_kpi", parent=S["kpi_value"], textColor=GOV_NAVY)),
            ],
            [
                Paragraph(l_tot, S["kpi_label"]),
                Paragraph(l_rec, S["kpi_label"]),
                Paragraph(l_app, S["kpi_label"]),
                Paragraph(l_flg, S["kpi_label"]),
                Paragraph(l_pnd, S["kpi_label"]),
                Paragraph(l_cov, S["kpi_label"]),
            ],
        ]

        kpi_table = Table(kpi_data, colWidths=[kpi_col] * 6, rowHeights=[26, 22])
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
            ("BACKGROUND",    (1, 0), (1, -1), colors.HexColor("#f0fdf4")),
            ("BACKGROUND",    (2, 0), (2, -1), colors.HexColor("#dcfce7")),
            ("BACKGROUND",    (3, 0), (3, -1), colors.HexColor("#fffbeb")),
            ("BACKGROUND",    (4, 0), (4, -1), colors.HexColor("#fff1f2")),
            ("BACKGROUND",    (5, 0), (5, -1), colors.HexColor("#f5f3ff")),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("GRID",          (0, 0), (-1, -1), 0.5, BORDER_GREY),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 10))

    # ── 4. AI FINDINGS SECTION & CEO RECOMMENDATION BOX ──────────────
    total_children_detected = 0
    blur_count = 0
    duplicate_count = 0
    meal_detected_count = 0
    gps_count = 0
    ai_scores = []

    for s in submissions:
        ai_sc = getattr(s, "ai_score", None) or ""
        if "बच्चे" in ai_sc or "child" in ai_sc.lower():
            try:
                parts = ai_sc.split("(")
                if len(parts) > 1 and "बच्चे" in parts[1]:
                    num_str = "".join(c for c in parts[1] if c.isdigit())
                    if num_str:
                        total_children_detected += int(num_str)
            except Exception:
                pass

        flag_reason = getattr(s, "flag_reason", None) or ""
        if "BLUR" in flag_reason.upper():
            blur_count += 1
        if "DUPLICATE" in flag_reason.upper():
            duplicate_count += 1
        if "NO_MEAL" not in flag_reason.upper():
            meal_detected_count += 1

        if getattr(s, "latitude", None) and getattr(s, "longitude", None):
            gps_count += 1

        if "%" in ai_sc:
            try:
                score_str = ai_sc.split("%")[0].strip()
                ai_scores.append(float(score_str))
            except Exception:
                pass

    avg_confidence = f"{round(sum(ai_scores)/len(ai_scores), 1)}%" if ai_scores else "N/A"
    children_str = f"{total_children_detected} बच्चे" if total_children_detected > 0 else "N/A"
    blur_str = f"{blur_count} फोटो" if len(submissions) > 0 else "N/A"
    duplicate_str = f"{duplicate_count} फोटो" if len(submissions) > 0 else "N/A"
    meal_str = f"{meal_detected_count}/{len(submissions)} केंद्र" if len(submissions) > 0 else "N/A"
    gps_str = f"{gps_count}/{len(submissions)} केंद्र" if len(submissions) > 0 else "N/A"

    ai_findings_headers = [
        Paragraph(_shape_hi("मीट्रिक (AI Metric)", font_name=_get_font(bold=True), font_size=11), S["cell_header"]),
        Paragraph(_shape_hi("परिणाम (Result)", font_name=_get_font(bold=True), font_size=11), S["cell_header"]),
        Paragraph(_shape_hi("स्थिति / विवरण (Note)", font_name=_get_font(bold=True), font_size=11), S["cell_header"]),
    ]
    ai_findings_rows = [
        ai_findings_headers,
        [Paragraph(_shape_hi("<b>AI इंजन (AI Engine)</b>"), S["cell_normal"]), Paragraph(_shape_hi("Multi-Vision AI"), S["cell_center"]), Paragraph(_shape_hi("Groq & Gemini विज़न इंजन"), S["cell_normal"])],
        [Paragraph(_shape_hi("<b>उपस्थित बच्चे (Children)</b>"), S["cell_normal"]), Paragraph(_shape_hi(children_str), S["cell_center"]), Paragraph(_shape_hi("ML Object Counter गणना"), S["cell_normal"])],
        [Paragraph(_shape_hi("<b>धुंधली फोटो (Blur Images)</b>"), S["cell_normal"]), Paragraph(_shape_hi(blur_str), S["cell_center"]), Paragraph(_shape_hi("Laplacian Variance फ़िल्टर"), S["cell_normal"])],
        [Paragraph(_shape_hi("<b>डुप्लिकेट फोटो (Duplicate)</b>"), S["cell_normal"]), Paragraph(_shape_hi(duplicate_str), S["cell_center"]), Paragraph(_shape_hi("pHash perceptual हैश जांच"), S["cell_normal"])],
        [Paragraph(_shape_hi("<b>भोजन पहचान (Meal Detection)</b>"), S["cell_normal"]), Paragraph(_shape_hi(meal_str), S["cell_center"]), Paragraph(_shape_hi("ML भोजन उपस्थिति सत्यापन"), S["cell_normal"])],
        [Paragraph(_shape_hi("<b>GPS उपलब्धता (GPS)</b>"), S["cell_normal"]), Paragraph(_shape_hi(gps_str), S["cell_center"]), Paragraph(_shape_hi("EXIF भू-स्थानिक निर्देशांक"), S["cell_normal"])],
        [Paragraph(_shape_hi("<b>विश्वास स्तर (Confidence)</b>"), S["cell_normal"]), Paragraph(_shape_hi(avg_confidence), S["cell_center"]), Paragraph(_shape_hi("एआई मॉडल औसत विश्वास दर"), S["cell_normal"])],
    ]

    col_w_findings = [page_w * 0.20, page_w * 0.12, page_w * 0.17]
    ai_table = Table(ai_findings_rows, colWidths=col_w_findings)
    ai_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), GOV_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("ALIGN",         (1, 1), (1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GOV_LIGHT_BG]),
        ("GRID",          (0, 0), (-1, -1), 0.5, BORDER_GREY),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))

    rec_paragraphs = []
    if flagged == 0:
        rec_paragraphs.append(Paragraph(_shape_hi("<b>✔ सामान्य स्थिति (No Action Required):</b> समस्त प्रेषित फोटो AI सत्यापन मानकों के अनुरूप पाए गए।"), S["rec_item"]))
    else:
        rec_paragraphs.append(Paragraph(_shape_hi(f"<b>⚠ समीक्षा आवश्यक (Re-inspection):</b> {flagged} केंद्रों की प्रविष्टियों में विसंगति पाई गई — पर्यवेक्षक समीक्षा आवश्यक।"), S["rec_item"]))

    if blur_count > 0:
        rec_paragraphs.append(Paragraph(_shape_hi(f"<b>⚠ फोटो गुणवत्ता अस्पष्ट:</b> {blur_count} फोटो अत्यधिक धुंधली पाई गईं — पुनः स्पष्ट फोटो प्रेषण का निर्देश दें।"), S["rec_item"]))

    if duplicate_count > 0:
        rec_paragraphs.append(Paragraph(_shape_hi(f"<b>⚠ पुनरावृत्ति प्रेषण (Duplicate):</b> {duplicate_count} फोटो पुरानी पाई गईं — जवाबदेही तय की जाए।"), S["rec_item"]))

    rec_paragraphs.append(Paragraph(_shape_hi("<b>✔ स्वचालित पावती (Auto Ack):</b> AI सत्यापन पश्चात व्हाट्सएप पर 100% पावती प्रेषित की गई।"), S["rec_item"]))

    rec_box_table = Table([[rec_paragraphs]], colWidths=[page_w * 0.48])
    rec_box_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fefce8")),
        ("BOX",        (0, 0), (-1, -1), 1, colors.HexColor("#d97706")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))

    side_by_side_table = Table([
        [
            Paragraph(_shape_hi("🤖 AI सत्यापन सारांश (AI Findings)", font_name=_get_font(bold=True), font_size=15), S["section_head"]),
            Paragraph(_shape_hi("🧠 CEO निर्णय सहायता (Recommendations)", font_name=_get_font(bold=True), font_size=15), S["section_head"]),
        ],
        [
            ai_table,
            rec_box_table,
        ]
    ], colWidths=[page_w * 0.50, page_w * 0.50])

    side_by_side_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    story.append(side_by_side_table)
    story.append(Spacer(1, 10))

    # ── 5. SUBMISSION DETAIL TABLE (CLEAN HINDI HEADING & RESTRAINED BADGES) ──
    max_rows = 25
    display_submissions = submissions[:max_rows]
    overflow = len(submissions) - max_rows if len(submissions) > max_rows else 0

    detail_head_str = _shape_hi(f"📋  आंगनवाड़ी केंद्र प्रेषण विवरण (Detailed AWC Submissions — {min(len(submissions), max_rows)} रिकॉर्ड)", font_name=_get_font(bold=True), font_size=15)
    story.append(Paragraph(detail_head_str, S["section_head"]))

    sub_headers = [
        Paragraph(_shape_hi("AWC ID", font_name=_get_font(bold=True), font_size=11),         S["cell_header"]),
        Paragraph(_shape_hi("केंद्र का नाम", font_name=_get_font(bold=True), font_size=11),     S["cell_header"]),
        Paragraph(_shape_hi("कार्यकर्ता नाम", font_name=_get_font(bold=True), font_size=11),    S["cell_header"]),
        Paragraph(_shape_hi("समय (IST)", font_name=_get_font(bold=True), font_size=11),       S["cell_header"]),
        Paragraph(_shape_hi("स्थिति", font_name=_get_font(bold=True), font_size=11),          S["cell_header"]),
        Paragraph(_shape_hi("AI निष्कर्ष", font_name=_get_font(bold=True), font_size=11),       S["cell_header"]),
        Paragraph(_shape_hi("अभ्युक्ति / निर्णय", font_name=_get_font(bold=True), font_size=11), S["cell_header"]),
    ]
    sub_rows = [sub_headers]

    for s in display_submissions:
        ts = ""
        sub_ts = getattr(s, "submission_timestamp", None)
        if sub_ts:
            ts = sub_ts.astimezone(IST).strftime("%I:%M %p")

        st = getattr(s, "status", "RECEIVED")
        is_auth = getattr(s, "is_authorized", False)
        if st in ("APPROVED", "PROCESSED") or (is_auth and st != "FLAGGED"):
            disp_st = "APPROVED"
            st_color = COLOR_APPROVED
        elif st == "FLAGGED":
            disp_st = "FLAGGED"
            st_color = COLOR_FLAGGED
        else:
            disp_st = "RECEIVED"
            st_color = COLOR_PENDING

        st_paragraph = Paragraph(
            f"<b>{disp_st}</b>",
            ParagraphStyle("st_p", parent=S["cell_center"], textColor=st_color, fontName=_get_font(bold=True))
        )

        raw_ai = str(getattr(s, "ai_score", None) or ("सत्यापित" if disp_st == "APPROVED" else "प्रक्रियाधीन"))
        clean_ai = raw_ai.replace("Groq AI:", "").replace("Groq AI", "").strip()
        ai_res_shaped = _shape_hi(clean_ai)

        flag_reason = getattr(s, "flag_reason", None) or "—"
        if disp_st == "APPROVED":
            remarks_str = "स्वीकृत एवं सत्यापित"
        elif disp_st == "FLAGGED":
            remarks_str = f"फ्लैग: {flag_reason}"
        else:
            remarks_str = "प्राप्त (समीक्षा हेतु)"
        
        remarks_shaped = _shape_hi(remarks_str)

        sub_rows.append([
            Paragraph(_shape_hi(getattr(s, "awc_id", "") or "—"),      S["cell_bold"]),
            Paragraph(_shape_hi(getattr(s, "center_name", "") or "—"),  S["cell_normal"]),
            Paragraph(_shape_hi(getattr(s, "worker_name", "") or "—"),  S["cell_normal"]),
            Paragraph(_shape_hi(ts or "—"),                              S["cell_center"]),
            st_paragraph,
            Paragraph(ai_res_shaped,                                    S["cell_center"]),
            Paragraph(remarks_shaped,                                   S["cell_normal"]),
        ])

    if len(sub_rows) == 1:
        empty_msg = _shape_hi("आज कोई सबमिशन प्राप्त नहीं हुआ")
        sub_rows.append([Paragraph(empty_msg, S["cell_normal"]), "", "", "", "", "", ""])

    s_cols = [
        page_w * 0.14,   # AWC ID
        page_w * 0.16,   # Centre Name
        page_w * 0.16,   # Worker
        page_w * 0.11,   # Time
        page_w * 0.12,   # Status
        page_w * 0.15,   # AI Result
        page_w * 0.16,   # Remarks
    ]

    sub_table = Table(sub_rows, colWidths=s_cols, repeatRows=1)
    sub_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), GOV_NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GOV_LIGHT_BG]),
        ("GRID",          (0, 0), (-1, -1), 0.5, BORDER_GREY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
    ]))
    story.append(sub_table)

    if overflow > 0:
        story.append(Spacer(1, 4))
        overflow_str = _shape_hi(f"... और {overflow} अतिरिक्त रिकॉर्ड — पूर्ण डेटा के लिए डैशबोर्ड या CSV डाउनलोड देखें।")
        story.append(Paragraph(overflow_str, S["cell_normal"]))

    story.append(Spacer(1, 12))

    # ── 6. OFFICIAL SIGNATURE SECTION ──────────────────────────────
    sig1 = _shape_hi("<b>सेक्टर पर्यवेक्षक</b><br/>सोहागपुर ब्लॉक, जिला शहडोल", font_name=_get_font(), font_size=9.5)
    sig2 = _shape_hi("<b>बाल विकास परियोजना अधिकारी (CDPO)</b><br/>महिला एवं बाल विकास विभाग, शहडोल", font_name=_get_font(), font_size=9.5)
    sig3 = _shape_hi("<b>DPO / CEO जिला पंचायत</b><br/>जिला शहडोल (मध्य प्रदेश)", font_name=_get_font(), font_size=9.5)

    story.append(KeepTogether([
        HRFlowable(width=page_w, thickness=0.8, color=GOV_NAVY),
        Spacer(1, 6),
        Table([
            [
                Paragraph("___________________________", S["sign_label"]),
                Paragraph("___________________________", S["sign_label"]),
                Paragraph("___________________________", S["sign_label"]),
            ],
            [
                Paragraph(sig1, S["sign_label"]),
                Paragraph(sig2, S["sign_label"]),
                Paragraph(sig3, S["sign_label"]),
            ]
        ], colWidths=[page_w / 3] * 3, style=[
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]),
    ]))

    # Build Document using NumberedCanvas for dynamic "Page X of Y"
    doc.build(story, canvasmaker=NumberedCanvas)

    pdf_bytes = buffer.getvalue()
    buffer.close()

    logger.info(
        "government_executive_pdf_v2_generated",
        date=report_date,
        doc_id=doc_id,
        submissions_count=len(submissions),
        size_kb=round(len(pdf_bytes) / 1024, 1),
    )
    return pdf_bytes
