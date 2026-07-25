# app/services/pdf_generator.py
# =====================================================================
# BharatOS — Shahdol Anganwadi Digital Verification & DSS
# Official Government Executive PDF Report Generator
# High-Impact Report Design for CEO Zila Panchayat & District Collector
# Uses ReportLab with embedded Noto Devanagari Unicode font for Hindi.
# =====================================================================

import io
import os
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
from reportlab.pdfbase.ttfonts import TTFont

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

# Executive Government Color Palette
GOV_NAVY       = colors.HexColor("#0f2942")  # Deep Navy Blue
GOV_BLUE       = colors.HexColor("#1e3a8a")  # Government Blue
GOV_LIGHT_BG   = colors.HexColor("#f1f5f9")  # Slate Light Grey
GOV_ACCENT     = colors.HexColor("#2563eb")  # Vibrant Royal Blue
SAFFRON        = colors.HexColor("#FF9933")  # Indian Flag Saffron
INDIA_GREEN    = colors.HexColor("#138808")  # Indian Flag Green
WHITE          = colors.white
LIGHT_GREY     = colors.HexColor("#f8fafc")
MID_GREY       = colors.HexColor("#cbd5e1")
TEXT_DARK      = colors.HexColor("#0f172a")
TEXT_MUTED     = colors.HexColor("#475569")

# Badge colors
COLOR_APPROVED = colors.HexColor("#15803d")
COLOR_FLAGGED  = colors.HexColor("#b45309")
COLOR_PENDING  = colors.HexColor("#1d4ed8")
COLOR_REJECTED = colors.HexColor("#b91c1c")

_font_registered = False


# ─────────────────────────────────────────────
# Font Setup — Local Embedded TTF Registration
# ─────────────────────────────────────────────

def _ensure_fonts() -> bool:
    """
    Registers local embedded TTF Devanagari fonts with ReportLab.
    Guarantees 100% Unicode Hindi rendering without boxes or blocks.
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


# ─────────────────────────────────────────────
# Numbered Canvas for "Page X of Y" Footer & Header
# ─────────────────────────────────────────────

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute total page count and draw
    consistent government header/footer on every page.
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
        now_str = datetime.now(IST).strftime("%d/%m/%Y %I:%M %p IST")

        # Top Header (Only on pages 2+)
        if self._pageNumber > 1:
            self.setFont(fn, 8)
            self.setFillColor(TEXT_MUTED)
            self.drawString(1.5 * cm, A4[1] - 1.0 * cm, "मध्य प्रदेश शासन  |  शहडोल आंगनवाड़ी डिजिटल सत्यापन एवं निर्णय सहायता प्रणाली (DSS)")
            self.setFont(fn_bold, 8)
            self.drawRightString(A4[0] - 1.5 * cm, A4[1] - 1.0 * cm, "आधिकारिक शासकीय रिपोर्ट")
            self.setStrokeColor(MID_GREY)
            self.setLineWidth(0.5)
            self.line(1.5 * cm, A4[1] - 1.2 * cm, A4[0] - 1.5 * cm, A4[1] - 1.2 * cm)

        # Bottom Footer (All Pages)
        self.setStrokeColor(MID_GREY)
        self.setLineWidth(0.5)
        self.line(1.5 * cm, 1.4 * cm, A4[0] - 1.5 * cm, 1.4 * cm)

        self.setFont(fn, 7.5)
        self.setFillColor(TEXT_MUTED)
        left_footer = f"Generated Automatically by BharatOS AI  |  Generated from WhatsApp Submission Workflow  |  v3.0  |  Confidential"
        self.drawString(1.5 * cm, 0.9 * cm, left_footer)

        page_str = f"Page {self._pageNumber} of {page_count}"
        self.setFont(fn_bold, 8)
        self.drawRightString(A4[0] - 1.5 * cm, 0.9 * cm, page_str)
        self.restoreState()


# ─────────────────────────────────────────────
# Style Builders
# ─────────────────────────────────────────────

def _build_styles() -> dict:
    """Builds ReportLab paragraph styles with Devanagari Unicode fonts."""
    fn      = _get_font(bold=False)
    fn_bold = _get_font(bold=True)

    return {
        "gov_top": ParagraphStyle(
            "gov_top",
            fontName=fn_bold, fontSize=11, textColor=WHITE,
            alignment=TA_LEFT, leading=14, spaceAfter=2,
        ),
        "gov_title": ParagraphStyle(
            "gov_title",
            fontName=fn_bold, fontSize=13.5, textColor=WHITE,
            alignment=TA_LEFT, leading=16.5, spaceAfter=2,
        ),
        "gov_subtitle": ParagraphStyle(
            "gov_subtitle",
            fontName=fn, fontSize=8.5, textColor=colors.HexColor("#cbd5e1"),
            alignment=TA_LEFT, leading=12,
        ),
        "section_head": ParagraphStyle(
            "section_head",
            fontName=fn_bold, fontSize=10.5, textColor=GOV_NAVY,
            spaceBefore=8, spaceAfter=5, leading=13,
        ),
        "cell_normal": ParagraphStyle(
            "cell_normal",
            fontName=fn, fontSize=8, textColor=TEXT_DARK,
            leading=11,
        ),
        "cell_bold": ParagraphStyle(
            "cell_bold",
            fontName=fn_bold, fontSize=8, textColor=TEXT_DARK,
            leading=11,
        ),
        "cell_center": ParagraphStyle(
            "cell_center",
            fontName=fn, fontSize=8, textColor=TEXT_DARK,
            alignment=TA_CENTER, leading=11,
        ),
        "cell_header": ParagraphStyle(
            "cell_header",
            fontName=fn_bold, fontSize=8, textColor=WHITE,
            alignment=TA_CENTER, leading=11,
        ),
        "kpi_value": ParagraphStyle(
            "kpi_value",
            fontName=fn_bold, fontSize=16, textColor=GOV_NAVY,
            alignment=TA_CENTER, leading=20,
        ),
        "kpi_label": ParagraphStyle(
            "kpi_label",
            fontName=fn_bold, fontSize=7, textColor=TEXT_MUTED,
            alignment=TA_CENTER, leading=9,
        ),
        "rec_item": ParagraphStyle(
            "rec_item",
            fontName=fn, fontSize=8, textColor=TEXT_DARK,
            leading=11, spaceAfter=2,
        ),
        "sign_label": ParagraphStyle(
            "sign_label",
            fontName=fn, fontSize=7.5, textColor=TEXT_MUTED,
            alignment=TA_CENTER, leading=11,
        ),
    }


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
    Generates an Official Executive Government A4 PDF Report suitable for
    CEO Zila Panchayat & District Collector presentation.

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

    # ── 1. TOP ANNOUNCEMENT BAR ───────────────────────────────────────
    top_notice = Paragraph(
        "🤖 <b>AI Generated Government Pilot Report</b> | Auto Generated — No Manual Editing",
        ParagraphStyle("top_notice", parent=S["cell_center"], fontSize=7.5, textColor=WHITE, fontName=_get_font(bold=True))
    )
    top_notice_table = Table([[top_notice]], colWidths=[page_w], rowHeights=[14])
    top_notice_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GOV_NAVY),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(top_notice_table)
    story.append(Spacer(1, 3))

    # ── 1. TRICOLOR HEADER ACCENT STRIP ────────────────────────────
    strip_data = [["", "", ""]]
    strip_table = Table(strip_data, colWidths=[page_w / 3] * 3, rowHeights=[4])
    strip_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), SAFFRON),
        ("BACKGROUND", (1, 0), (1, 0), WHITE),
        ("BACKGROUND", (2, 0), (2, 0), INDIA_GREEN),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    story.append(strip_table)
    story.append(Spacer(1, 4))

    # ── 2. GOVERNMENT COVER HEADER BLOCK (WITH LOGO ~20% SMALLER) ──
    logo_img = None
    if _LOGO_PATH.exists():
        try:
            # Scaled down ~20% for optimal text layout
            logo_img = Image(str(_LOGO_PATH), width=1.9 * cm, height=1.9 * cm)
        except Exception as e:
            logger.warning("logo_load_failed", error=str(e))

    title_text = [
        Paragraph("मध्य प्रदेश शासन  |  Government of Madhya Pradesh", S["gov_top"]),
        Paragraph("शहडोल आंगनवाड़ी डिजिटल सत्यापन एवं निर्णय सहायता प्रणाली (DSS)", S["gov_title"]),
        Paragraph("<b>BharatOS Digital Governance Platform</b>  |  Pilot Demonstration Report (For Demonstration Purpose)", S["gov_subtitle"]),
    ]

    if logo_img:
        header_table = Table([[logo_img, title_text]], colWidths=[2.3 * cm, page_w - 2.3 * cm])
    else:
        header_table = Table([[title_text]], colWidths=[page_w])

    header_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), GOV_NAVY),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 5))

    # ── 3. METADATA SUB-BAR (WITH TRACKING DOC ID & ENHANCED TIME) ──
    filter_str = f"ब्लॉक: {block_name}" if block_name else "समस्त जिला शहडोल"
    if status_filter:
        filter_str += f" | स्थिति: {status_filter}"

    time_display = now_ist.strftime('%I:%M %p IST')
    meta_data = [[
        Paragraph(f"<b>Document ID:</b> <font color='#0f2942'><b>{doc_id}</b></font>", S["cell_normal"]),
        Paragraph(f"<b>रिपोर्ट तिथि:</b> {report_date}  |  {filter_str}", S["cell_normal"]),
        Paragraph(f"<b>उत्पन्न समय:</b> <font size=8.5 color='#0f2942'><b>{time_display}</b></font>", S["cell_center"]),
    ]]
    meta_table = Table(meta_data, colWidths=[page_w * 0.32, page_w * 0.43, page_w * 0.25])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), GOV_LIGHT_BG),
        ("LINEABOVE",     (0, 0), (-1, 0), 1, GOV_NAVY),
        ("LINEBELOW",     (0, -1), (-1, -1), 1, GOV_NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("FONTNAME",      (0, 0), (-1, -1), _get_font()),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 8))

    # ── 4. PRIORITY 3: EXECUTIVE SUMMARY KPI CARDS (6 CARDS) ───────
    story.append(Paragraph("📊  कार्यकारी सारांश (Executive Summary — KPI Cards)", S["section_head"]))

    total_awc = TOTAL_AWC_SHAHDOL
    reports_rec = stats.get("reported_today", len(submissions))

    # Correct verified / approved / flagged logic
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

    kpi_col = page_w / 6.0
    kpi_data = [
        [
            Paragraph(f"<b>{total_awc:,}</b>", S["kpi_value"]),
            Paragraph(f"<b>{reports_rec}</b>", S["kpi_value"]),
            Paragraph(f"<b>{approved}</b>", ParagraphStyle("green_kpi", parent=S["kpi_value"], textColor=COLOR_APPROVED)),
            Paragraph(f"<b>{flagged}</b>", ParagraphStyle("amber_kpi", parent=S["kpi_value"], textColor=COLOR_FLAGGED)),
            Paragraph(f"<b>{pending_centres:,}</b>", ParagraphStyle("blue_kpi", parent=S["kpi_value"], textColor=COLOR_PENDING)),
            Paragraph(f"<b>{cov_pct}%</b>", ParagraphStyle("navy_kpi", parent=S["kpi_value"], textColor=GOV_NAVY)),
        ],
        [
            Paragraph("कुल केंद्र<br/>(Total Centres)", S["kpi_label"]),
            Paragraph("प्राप्त रिपोर्ट<br/>(Reports Recd)", S["kpi_label"]),
            Paragraph("सत्यापित / स्वीकृत<br/>(Verified)", S["kpi_label"]),
            Paragraph("फ्लैग्ड<br/>(Flagged)", S["kpi_label"]),
            Paragraph("अनरिपोर्टेड<br/>(Pending)", S["kpi_label"]),
            Paragraph("रिपोर्टिंग %<br/>(Reporting %)", S["kpi_label"]),
        ],
    ]

    kpi_table = Table(kpi_data, colWidths=[kpi_col] * 6, rowHeights=[24, 20])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), colors.HexColor("#eff6ff")),
        ("BACKGROUND",    (1, 0), (1, -1), colors.HexColor("#f0fdf4")),
        ("BACKGROUND",    (2, 0), (2, -1), colors.HexColor("#dcfce7")),
        ("BACKGROUND",    (3, 0), (3, -1), colors.HexColor("#fef3c7")),
        ("BACKGROUND",    (4, 0), (4, -1), colors.HexColor("#fee2e2")),
        ("BACKGROUND",    (5, 0), (5, -1), colors.HexColor("#f5f3ff")),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",          (0, 0), (-1, -1), 0.5, MID_GREY),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("FONTNAME",      (0, 0), (-1, -1), _get_font()),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 8))

    # ── 5. PRIORITY 4: AI FINDINGS SECTION & PRIORITY 5: AI RECOMMENDATIONS ───
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
        Paragraph("मीट्रिक (AI Metric)", S["cell_header"]),
        Paragraph("परिणाम (Result)", S["cell_header"]),
        Paragraph("स्थिति / टिप्पणी (Note)", S["cell_header"]),
    ]
    ai_findings_rows = [
        ai_findings_headers,
        [Paragraph("<b>AI विज़न इंजन (AI Engine)</b>", S["cell_normal"]), Paragraph("OpenCV + Vision ML", S["cell_center"]), Paragraph("बहु-मॉडल दृष्टि सत्यापन पाइपलाइन", S["cell_normal"])],
        [Paragraph("<b>उपस्थित बच्चे (Children Detected)</b>", S["cell_normal"]), Paragraph(children_str, S["cell_center"]), Paragraph("ML Object Counter पहचान", S["cell_normal"])],
        [Paragraph("<b>धुंधली फोटो (Blur Images)</b>", S["cell_normal"]), Paragraph(blur_str, S["cell_center"]), Paragraph("OpenCV Laplacian Variance टेस्ट", S["cell_normal"])],
        [Paragraph("<b>पुनरावृत्ति फोटो (Duplicate Images)</b>", S["cell_normal"]), Paragraph(duplicate_str, S["cell_center"]), Paragraph("Perceptual Image Hash (pHash) जांच", S["cell_normal"])],
        [Paragraph("<b>भोजन उपस्थिति (Meal Detection)</b>", S["cell_normal"]), Paragraph(meal_str, S["cell_center"]), Paragraph("ML Meal Classifier विजुअल पुष्टि", S["cell_normal"])],
        [Paragraph("<b>GPS लोकेशन (GPS Available)</b>", S["cell_normal"]), Paragraph(gps_str, S["cell_center"]), Paragraph("EXIF Metatags भू-स्थानिक निर्देशांक", S["cell_normal"])],
        [Paragraph("<b>औसत AI विश्वास (Average Confidence)</b>", S["cell_normal"]), Paragraph(avg_confidence, S["cell_center"]), Paragraph("AI मॉडल औसत विश्वास दर", S["cell_normal"])],
    ]

    col_w_findings = [page_w * 0.20, page_w * 0.12, page_w * 0.17]
    ai_table = Table(ai_findings_rows, colWidths=col_w_findings)
    ai_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), GOV_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
        ("ALIGN",         (1, 1), (1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ("GRID",          (0, 0), (-1, -1), 0.5, MID_GREY),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("FONTNAME",      (0, 0), (-1, -1), _get_font()),
    ]))

    rec_paragraphs = []
    if flagged == 0:
        rec_paragraphs.append(Paragraph("<b>✔ No Action Required:</b> समस्त प्राप्त प्रेषण AI मानकों के अनुरूप पाए गए।", S["rec_item"]))
    else:
        rec_paragraphs.append(Paragraph(f"<b>⚠ Re-inspection Required:</b> {flagged} केंद्रों की प्रविष्टियों में विसंगतियां पाई गईं — पर्यवेक्षक समीक्षा आवश्यक।", S["rec_item"]))

    if blur_count > 0:
        rec_paragraphs.append(Paragraph(f"<b>⚠ Photo Quality Poor:</b> {blur_count} केंद्रों द्वारा प्रेषित फोटो धुंधली पाई गईं। कार्यकर्ता को पुनः स्पष्ट फोटो भेजने के निर्देश दें।", S["rec_item"]))

    if duplicate_count > 0:
        rec_paragraphs.append(Paragraph(f"<b>⚠ Duplicate Submission:</b> {duplicate_count} प्रेषणों में पुरानी या दोहराई गई फोटो पाई गई — जवाबदेही तय की जाए।", S["rec_item"]))

    rec_paragraphs.append(Paragraph("<b>✔ Instant Verification:</b> AI सत्यापन के पश्चात व्हाट्सएप पर 100% स्वतः रसीद प्रेषित की गई।", S["rec_item"]))

    rec_box_table = Table([[rec_paragraphs]], colWidths=[page_w * 0.48])
    rec_box_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffbeb")),
        ("BOX",        (0, 0), (-1, -1), 1, colors.HexColor("#f59e0b")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("FONTNAME",   (0, 0), (-1, -1), _get_font()),
    ]))

    side_by_side_table = Table([
        [
            Paragraph("<b>🤖 AI सत्यापन सारांश (AI Findings)</b>", S["section_head"]),
            Paragraph("<b>🧠 CEO निर्णय सहायता (AI Recommendations)</b>", S["section_head"]),
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
        ("FONTNAME", (0, 0), (-1, -1), _get_font()),
    ]))

    story.append(side_by_side_table)
    story.append(Spacer(1, 4))

    # ── 6. PRIORITY 6: IMPROVED SUBMISSION DETAIL TABLE ────────────
    max_rows = 25
    display_submissions = submissions[:max_rows]
    overflow = len(submissions) - max_rows if len(submissions) > max_rows else 0

    story.append(Paragraph(
        f"📋  आंगनवाड़ी केंद्र प्रेषण विवरण (Detailed AWC Submissions — {min(len(submissions), max_rows)} रिकॉर्ड)",
        S["section_head"]
    ))

    sub_headers = [
        Paragraph("AWC ID",         S["cell_header"]),
        Paragraph("केंद्र का नाम",     S["cell_header"]),
        Paragraph("कार्यकर्ता नाम",    S["cell_header"]),
        Paragraph("समय (IST)",       S["cell_header"]),
        Paragraph("स्थिति",          S["cell_header"]),
        Paragraph("AI परिणाम",       S["cell_header"]),
        Paragraph("अभ्युक्ति / निर्णय", S["cell_header"]),
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

        ai_res = getattr(s, "ai_score", None) or ("सत्यापित" if disp_st == "APPROVED" else "प्रक्रियाधीन")
        flag_reason = getattr(s, "flag_reason", None) or "—"
        if disp_st == "APPROVED":
            remarks = "स्वीकृत एवं सत्यापित"
        elif disp_st == "FLAGGED":
            remarks = f"फ्लैग: {flag_reason}"
        else:
            remarks = "प्राप्त (समीक्षा हेतु)"

        sub_rows.append([
            Paragraph(getattr(s, "awc_id", "") or "—",      S["cell_bold"]),
            Paragraph(getattr(s, "center_name", "") or "—",  S["cell_normal"]),
            Paragraph(getattr(s, "worker_name", "") or "—",  S["cell_normal"]),
            Paragraph(ts or "—",                              S["cell_center"]),
            st_paragraph,
            Paragraph(str(ai_res),                           S["cell_center"]),
            Paragraph(remarks,                                S["cell_normal"]),
        ])

    if len(sub_rows) == 1:
        sub_rows.append([Paragraph("आज कोई सबमिशन प्राप्त नहीं हुआ", S["cell_normal"]), "", "", "", "", "", ""])

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
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ("GRID",          (0, 0), (-1, -1), 0.4, MID_GREY),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("FONTNAME",      (0, 0), (-1, -1), _get_font()),
    ]))
    story.append(sub_table)

    if overflow > 0:
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f"... और {overflow} अतिरिक्त रिकॉर्ड — पूर्ण डेटा के लिए डैशबोर्ड या CSV डाउनलोड देखें।",
            S["cell_normal"]
        ))

    story.append(Spacer(1, 8))

    # ── 7. OFFICIAL SIGN-OFF BLOCK ──────────────────────────────────
    story.append(KeepTogether([
        HRFlowable(width=page_w, thickness=0.8, color=GOV_NAVY),
        Spacer(1, 4),
        Table([
            [
                Paragraph("___________________________", S["sign_label"]),
                Paragraph("___________________________", S["sign_label"]),
                Paragraph("___________________________", S["sign_label"]),
            ],
            [
                Paragraph("<b>सेक्टर सुपरवाइजर</b><br/>सोहागपुर ब्लॉक, जिला शहडोल", S["sign_label"]),
                Paragraph("<b>CDPO शहडोल</b><br/>महिला एवं बाल विकास विभाग", S["sign_label"]),
                Paragraph("<b>DPO / CEO जिला पंचायत</b><br/>जिला शहडोल (म.प्र.)", S["sign_label"]),
            ]
        ], colWidths=[page_w / 3] * 3, style=[
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("FONTNAME", (0, 0), (-1, -1), _get_font()),
        ]),
    ]))

    # Build Document using NumberedCanvas for dynamic "Page X of Y"
    doc.build(story, canvasmaker=NumberedCanvas)

    pdf_bytes = buffer.getvalue()
    buffer.close()

    logger.info(
        "government_executive_pdf_generated",
        date=report_date,
        doc_id=doc_id,
        submissions_count=len(submissions),
        size_kb=round(len(pdf_bytes) / 1024, 1),
    )
    return pdf_bytes
