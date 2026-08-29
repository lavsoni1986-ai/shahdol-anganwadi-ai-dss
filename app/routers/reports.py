# app/routers/reports.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP — Day 3
# Report Generation Router
# Endpoints:
#   GET /api/v1/reports/pdf    → Official Government PDF Report
#   GET /api/v1/reports/excel  → UTF-8 CSV / Excel Download
# =====================================================================

import csv
import io
import json
from datetime import datetime, date, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import DailySubmission, SubmissionStatus
from app.services.firebase_auth import get_current_officer, require_admin
from app.services.pdf_generator import generate_daily_report_pdf
from app.services.whatsapp import send_whatsapp_document
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])

IST = ZoneInfo("Asia/Kolkata")

# Shahdol district blocks for reference
SHAHDOL_BLOCKS = [
    "सोहागपुर", "ब्योहारी", "जयसिंहनगर", "बुढार", "गोहपारू",
    "शहडोल", "अनूपपुर", "पुष्पराजगढ़",
]




# ─────────────────────────────────────────────
# Shared: Build date-range filter
# ─────────────────────────────────────────────

def _parse_date_filter(date_str: Optional[str]):
    """
    Given 'YYYY-MM-DD' string (or None = today), returns (start_utc, end_utc)
    covering that full IST calendar day.
    """
    try:
        if date_str:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            d = datetime.now(IST).date()
    except ValueError:
        d = datetime.now(IST).date()

    # Midnight IST → convert to UTC
    from datetime import timedelta
    ist_offset = timedelta(hours=5, minutes=30)
    day_start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=IST)
    day_end   = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=IST)
    return day_start.astimezone(timezone.utc), day_end.astimezone(timezone.utc)


def _display_date(date_str: Optional[str]) -> str:
    """Returns DD/MM/YYYY string for given YYYY-MM-DD, or today."""
    try:
        if date_str:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            d = datetime.now(IST).date()
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return datetime.now(IST).strftime("%d/%m/%Y")


async def _fetch_submissions(
    db: AsyncSession,
    date_str: Optional[str],
    block_name: Optional[str],
    status_filter: Optional[str],
) -> list:
    """Fetches filtered submissions from the database."""
    start_utc, end_utc = _parse_date_filter(date_str)

    filters = [
        DailySubmission.is_authorized == True,
        DailySubmission.submission_timestamp >= start_utc,
        DailySubmission.submission_timestamp <= end_utc,
    ]
    if block_name:
        filters.append(DailySubmission.block_name.ilike(f"%{block_name}%"))
    if status_filter:
        filters.append(DailySubmission.status == status_filter.upper())

    from app.models import AnganwadiMaster
    result = await db.execute(
        select(DailySubmission, AnganwadiMaster)
        .outerjoin(AnganwadiMaster, DailySubmission.awc_id == AnganwadiMaster.awc_code)
        .where(and_(*filters))
        .order_by(DailySubmission.submission_timestamp.asc())
        .limit(500)   # Safety cap — PDF/Excel can't render 10k rows
    )
    return list(result.all())


async def _compute_stats(db: AsyncSession, rows: list, date_str: Optional[str]) -> dict:
    """Computes KPI stats from a list of submission ORM objects."""
    total     = len(rows)
    approved  = sum(1 for s, awc in rows if s.status == SubmissionStatus.APPROVED)
    flagged   = sum(1 for s, awc in rows if s.status == SubmissionStatus.FLAGGED)
    pending   = sum(1 for s, awc in rows if s.status == SubmissionStatus.RECEIVED)
    
    from app.models import AnganwadiMaster
    from sqlalchemy import func
    total_awc_result = await db.execute(select(func.count(AnganwadiMaster.id)))
    total_awc = total_awc_result.scalar_one() or 0
    coverage  = round((total / total_awc) * 100, 1) if total_awc > 0 else 0.0

    return {
        "reported_today":    total,
        "approved_today":    approved,
        "flagged_today":     flagged,
        "pending_review":    pending,
        "coverage_percent":  coverage,
        "total_awc_centres": total_awc,
    }


# ═════════════════════════════════════════════════════════════════════
# ENDPOINT 1 — PDF Report
# GET /api/v1/reports/pdf
# ═════════════════════════════════════════════════════════════════════

@router.get(
    "/pdf",
    summary="Generate Official Government PDF Report",
    description=(
        "Generates a government-style A4 PDF daily report for district officers. "
        "Includes Hindi headers, KPI summary, block-wise table, submissions detail, "
        "and official sign-off section. Supports date, block, and status filters."
    ),
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF file stream — open inline or download as attachment",
        }
    },
)
async def download_pdf_report(
    db: AsyncSession = Depends(get_db),
    officer: dict = Depends(get_current_officer),
    report_date: Optional[str] = Query(
        None,
        alias="date",
        description="Report date in YYYY-MM-DD format. Defaults to today (IST).",
        example="2026-07-21",
    ),
    block_name: Optional[str] = Query(
        None,
        description="Filter by block name (partial match). E.g. सोहागपुर",
    ),
    status: Optional[str] = Query(
        None,
        description="Filter by status: RECEIVED, APPROVED, FLAGGED",
    ),
    inline: bool = Query(
        False,
        description="If true, opens PDF in browser. If false, forces download.",
    ),
):
    """
    Generates and streams an official government PDF daily report.

    The PDF includes:
    - India tricolor stripe header
    - Government navy header with department name in Hindi
    - Executive KPI summary cards (5 metrics)
    - Block-wise breakdown table
    - Submission detail table (up to 25 rows)
    - Official sign-off section with 3 authority lines
    - Official footer with generation timestamp
    """
    logger.info(
        "pdf_report_requested",
        date=report_date,
        block=block_name,
        status=status,
    )

    # Fetch data
    rows = await _fetch_submissions(db, report_date, block_name, status)
    stats       = await _compute_stats(db, rows, report_date)
    display_date = _display_date(report_date)

    # Generate PDF
    try:
        pdf_bytes = generate_daily_report_pdf(
            report_date=display_date,
            stats=stats,
            submissions=rows,
            block_name=block_name,
            status_filter=status,
        )
    except Exception as e:
        logger.error("pdf_generation_failed", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF generation failed: {str(e)}",
        )

    # Build filename
    safe_date = (report_date or datetime.now(IST).strftime("%Y-%m-%d")).replace("-", "")
    block_slug = f"_{block_name.replace(' ', '_')}" if block_name else ""
    filename = f"Shahdol_AWC_Report_{safe_date}{block_slug}.pdf"

    disposition = "inline" if inline else f'attachment; filename="{filename}"'

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": disposition,
            "Content-Length": str(len(pdf_bytes)),
            "X-Report-Date": display_date,
            "X-Submissions-Count": str(len(rows)),
        },
    )


# ═════════════════════════════════════════════════════════════════════
# ENDPOINT 2 — CSV / Excel Download
# GET /api/v1/reports/excel
# ═════════════════════════════════════════════════════════════════════

@router.get(
    "/excel",
    summary="Download Submissions as CSV (Excel-compatible)",
    description=(
        "Generates a UTF-8 with BOM CSV download of all filtered submissions. "
        "Opens correctly in Excel with Hindi column headers preserved. "
        "Supports the same date, block, and status filters as the PDF endpoint."
    ),
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "UTF-8 BOM CSV file — opens directly in Microsoft Excel",
        }
    },
)
async def download_excel_report(
    db: AsyncSession = Depends(get_db),
    officer: dict = Depends(get_current_officer),
    report_date: Optional[str] = Query(
        None,
        alias="date",
        description="Report date YYYY-MM-DD. Defaults to today (IST).",
    ),
    block_name: Optional[str] = Query(
        None,
        description="Filter by block name (partial match)",
    ),
    status: Optional[str] = Query(
        None,
        description="Filter by status: RECEIVED, APPROVED, FLAGGED",
    ),
):
    """
    Returns a UTF-8 BOM CSV with Hindi headers that opens cleanly in Excel.

    Columns:
    क्र.सं., सबमिशन ID, AWC ID, केंद्र नाम, ब्लॉक, जिला,
    कार्यकर्ता नाम, मोबाइल नंबर, प्रेषण समय (IST), संदेश प्रकार,
    मीडिया उपलब्ध, GPS अक्षांश, GPS देशांतर, स्थिति,
    समीक्षाकर्ता, फ्लैग कारण, टिप्पणी, ACK भेजा, एआई स्कोर
    """
    logger.info(
        "csv_report_requested",
        date=report_date,
        block=block_name,
        status=status,
    )

    submissions = await _fetch_submissions(db, report_date, block_name, status)
    display_date = _display_date(report_date)

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row (Hindi)
    writer.writerow([
        "क्र.सं.",
        "जिला (District)",
        "ब्लॉक (Block)",
        "सेक्टर (Sector)",
        "पर्यवेक्षक (Supervisor)",
        "आंगनवाड़ी (AWC Name)",
        "AWC ID",
        "कार्यकर्ता नाम (Worker Name)",
        "पंजीकृत बच्चे (Registered Children)",
        "उपस्थित बच्चे (Visible Children - AI)",
        "अंतर (Difference)",
        "भोजन स्थिति (Meal Status)",
        "GPS अक्षांश (Lat)",
        "GPS देशांतर (Lon)",
        "प्रेषण समय (IST)",
        "सत्यापन स्थिति (Status)",
        "फ्लैग कारण / टिप्पणी",
    ])

    for idx, (s, awc) in enumerate(submissions, 1):
        # Format IST timestamp
        ts_date = ts_time = ""
        if s.submission_timestamp:
            ist_ts = s.submission_timestamp.astimezone(IST)
            ts_date = ist_ts.strftime("%d/%m/%Y")
            ts_time = ist_ts.strftime("%I:%M:%S %p")
            
        def parse_ai_children(ai_sc: str) -> Optional[int]:
            if not ai_sc: return None
            if "बच्चे" in ai_sc or "child" in ai_sc.lower():
                try:
                    parts = ai_sc.split("(")
                    if len(parts) > 1 and "बच्चे" in parts[1]:
                        num_str = "".join(c for c in parts[1] if c.isdigit())
                        if num_str:
                            return int(num_str)
                except Exception:
                    pass
            return None

        def parse_meal_status(flag_reason: str, ai_score: str) -> str:
            if flag_reason and "NO_MEAL" in flag_reason.upper():
                return "भोजन नहीं"
            return "भोजन उपस्थित" if ai_score else "N/A"

        registered = awc.registered_children if awc and awc.registered_children else 0
        visible = parse_ai_children(s.ai_score) or 0
        diff = (registered - visible) if visible > 0 else 0
        meal_status = parse_meal_status(s.flag_reason, s.ai_score)

        writer.writerow([
            idx,
            awc.district if awc else s.district,
            awc.block_name if awc else s.block_name,
            awc.sector if awc else "",
            awc.supervisor_name if awc else "",
            s.center_name or "",
            s.awc_id or "",
            s.worker_name or "",
            registered,
            visible,
            diff,
            meal_status,
            s.latitude or "",
            s.longitude or "",
            f"{ts_date} {ts_time}",
            s.status or "RECEIVED",
            s.flag_reason or "",
        ])

    csv_str = output.getvalue()
    output.close()

    # UTF-8 BOM prefix for proper Excel rendering of Hindi text
    csv_bytes = b"\xef\xbb\xbf" + csv_str.encode("utf-8")

    safe_date = (report_date or datetime.now(IST).strftime("%Y-%m-%d")).replace("-", "")
    block_slug = f"_{block_name.replace(' ', '_')}" if block_name else ""
    filename = f"Shahdol_AWC_Data_{safe_date}{block_slug}.csv"

    logger.info(
        "csv_report_generated",
        date=display_date,
        rows=len(submissions),
        size_kb=round(len(csv_bytes) / 1024, 1),
    )

    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(csv_bytes)),
            "X-Report-Date": display_date,
            "X-Row-Count": str(len(submissions)),
        },
    )


# ═════════════════════════════════════════════════════════════════════
# ENDPOINT 3 — Send PDF Report to WhatsApp Phone Number
# POST /api/v1/reports/send-whatsapp
# ═════════════════════════════════════════════════════════════════════

@router.post(
    "/send-whatsapp",
    summary="Dispatch Daily PDF Report to WhatsApp Recipient",
    description="Generates the official daily PDF report and dispatches it via WhatsApp Meta Cloud API to the specified phone number.",
)
async def send_whatsapp_pdf_report(
    to_phone: str = Query(..., description="Recipient phone number with country code, e.g. 919753239303"),
    report_date: Optional[str] = Query(None, alias="date", description="Report date YYYY-MM-DD. Defaults to today."),
    db: AsyncSession = Depends(get_db),
    officer: dict = Depends(require_admin),
):
    """
    Generates and dispatches PDF report to a WhatsApp phone number.
    """
    submissions = await _fetch_submissions(db, report_date, None, None)
    stats       = await _compute_stats(db, submissions, report_date)
    display_date = _display_date(report_date)

    # Save PDF temporarily to disk in static/reports for public link
    pdf_bytes = generate_daily_report_pdf(
        report_date=display_date,
        stats=stats,
        submissions=submissions,
        block_name=None,
        status_filter=None,
    )

    safe_date = (report_date or datetime.now(IST).strftime("%Y-%m-%d")).replace("-", "")
    filename = f"Shahdol_AWC_Daily_Report_{safe_date}.pdf"

    # Build public URL for Meta API document delivery
    base_url = settings.app_public_url or "https://api.bharatosdemo24.com"
    pdf_url = f"{base_url.rstrip('/')}/api/v1/reports/pdf?date={report_date or ''}"

    res = await send_whatsapp_document(
        to_phone=to_phone,
        document_url=pdf_url,
        filename=filename,
        caption=f"📄 *शहडोल जिला — दैनिक आंगनवाड़ी पोषण आहार रिपोर्ट*\n📅 दिनांक: {display_date}\n📊 कुल केंद्र: {stats['total_awc_centres']} | रिपोर्ट प्राप्त: {len(submissions)}",
    )

    return {
        "status": "success" if res.get("success") else "failed",
        "to_phone": to_phone,
        "report_date": display_date,
        "filename": filename,
        "whatsapp_response": res,
    }

