# app/routers/dashboard.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP — Day 2
# Admin Dashboard API Router
# Endpoints for District Officers: Sector Supervisors, CDPO, DPO, CEO, Collector
#
# Endpoints:
#   GET  /api/v1/dashboard/stats
#   GET  /api/v1/dashboard/submissions
#   POST /api/v1/dashboard/submissions/{submission_id}/review
#   GET  /dashboard  (HTML panel — served via Jinja2)
# =====================================================================

from datetime import datetime, date, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy import func, select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import DailySubmission, SubmissionStatus
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])

# Jinja2 templates directory (for serving the HTML panel)
import pathlib
_TEMPLATES_DIR = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Total registered AWC centres in Shahdol district (official count)
TOTAL_AWC_CENTRES = 1450


# ─────────────────────────────────────────────
# Pydantic Schemas (Dashboard-specific)
# ─────────────────────────────────────────────

class DashboardStats(BaseModel):
    """KPI statistics for the dashboard summary cards."""
    total_awc_centres: int = Field(..., description="Total registered AWC centres in Shahdol")
    reported_today: int = Field(..., description="Authorized submissions received today")
    approved_today: int = Field(..., description="Submissions approved by supervisors today")
    flagged_today: int = Field(..., description="Submissions flagged for exceptions today")
    pending_review: int = Field(..., description="Submissions received but not yet reviewed")
    coverage_percent: float = Field(..., description="Reporting coverage % today")
    as_of: str = Field(..., description="Data freshness timestamp (IST)")


class SubmissionListItem(BaseModel):
    """Single row in the dashboard submissions table."""
    id: int
    submission_id: str
    awc_id: Optional[str]
    center_name: Optional[str]
    block_name: Optional[str]
    worker_name: Optional[str]
    worker_phone: str
    submission_timestamp: datetime
    message_type: Optional[str]
    has_media: bool
    latitude: Optional[str]
    longitude: Optional[str]
    status: str
    is_authorized: bool
    ai_score: Optional[str]
    review_action: Optional[str]
    flag_reason: Optional[str]
    reviewer_name: Optional[str]
    reviewed_at: Optional[datetime]
    ack_sent: bool

    class Config:
        from_attributes = True


class SubmissionListResponse(BaseModel):
    """Paginated response for the submissions table."""
    items: List[SubmissionListItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    filters_applied: dict


class ReviewRequest(BaseModel):
    """Request body for supervisor review action."""
    action: Literal["APPROVED", "FLAGGED"] = Field(
        ..., description="Review decision: APPROVED or FLAGGED"
    )
    flag_reason: Optional[str] = Field(
        None,
        max_length=200,
        description="Short reason for flagging (e.g. 'Blur Image', 'Outside Geofence', 'Wrong Center')",
    )
    remarks: Optional[str] = Field(
        None,
        max_length=1000,
        description="Optional long-form administrative remarks",
    )
    reviewer_id: Optional[str] = Field(
        default="dashboard_officer",
        max_length=50,
        description="Reviewer's officer ID or login",
    )
    reviewer_name: Optional[str] = Field(
        default="District Officer",
        max_length=100,
        description="Reviewer's full name",
    )


class ReviewResponse(BaseModel):
    """Response after a supervisor review action."""
    success: bool
    submission_id: str
    previous_status: str
    new_status: str
    action: str
    reviewed_by: Optional[str]
    reviewed_at: str
    message: str


# ─────────────────────────────────────────────
# Helper: today's date range (IST → UTC)
# ─────────────────────────────────────────────

def _date_utc_range(date_str: Optional[str] = None):
    """
    Returns (start_of_day_utc, end_of_day_utc) for a given date 'YYYY-MM-DD'.
    If not provided, uses IST today.
    """
    from zoneinfo import ZoneInfo
    ist = ZoneInfo("Asia/Kolkata")
    
    try:
        if date_str and isinstance(date_str, str):
            now_ist = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=ist)
        else:
            now_ist = datetime.now(ist)
    except (ValueError, TypeError):
        now_ist = datetime.now(ist)

    start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    end_ist = now_ist.replace(hour=23, minute=59, second=59, microsecond=999999)

    return (
        start_ist.astimezone(timezone.utc),
        end_ist.astimezone(timezone.utc),
    )


# ═════════════════════════════════════════════════════════════════════
# ENDPOINT 1: Dashboard KPI Stats
# GET /api/v1/dashboard/stats
# ═════════════════════════════════════════════════════════════════════

@router.get(
    "/stats",
    response_model=DashboardStats,
    summary="Dashboard KPI Statistics",
    description=(
        "Returns aggregated KPI counts for today: total authorized submissions, "
        "approved count, flagged count, and pending review count. "
        "Used to populate the summary cards at the top of the dashboard."
    ),
)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    date: Optional[str] = Query(None, description="Date filter YYYY-MM-DD"),
    block_name: Optional[str] = Query(None, description="Block name filter"),
) -> DashboardStats:
    """
    Aggregates submission statistics from the database based on date and block filters.
    All counts are filtered to IST midnight to midnight.
    """
    from zoneinfo import ZoneInfo
    ist = ZoneInfo("Asia/Kolkata")
    start_utc, end_utc = _date_utc_range(date)

    logger.info("dashboard_stats_requested", start_utc=str(start_utc), end_utc=str(end_utc), block=block_name)

    # Base filter: date range + authorized workers only
    base_filters = [
        DailySubmission.submission_timestamp >= start_utc,
        DailySubmission.submission_timestamp <= end_utc,
        DailySubmission.is_authorized == True,
    ]
    
    # Version 3.0: CEO Demo Mode automatic filter
    if settings.demo_mode:
        base_filters.append(DailySubmission.awc_id == settings.demo_awc_id)

    if block_name and not settings.demo_mode:
        base_filters.append(DailySubmission.block_name.ilike(f"%{block_name}%"))
        
    today_filter = and_(*base_filters)

    # Total authorized submissions today
    total_result = await db.execute(
        select(func.count(DailySubmission.id)).where(today_filter)
    )
    reported_today: int = total_result.scalar_one() or 0

    # Approved today
    approved_result = await db.execute(
        select(func.count(DailySubmission.id)).where(
            and_(today_filter, DailySubmission.status == SubmissionStatus.APPROVED)
        )
    )
    approved_today: int = approved_result.scalar_one() or 0

    # Flagged today
    flagged_result = await db.execute(
        select(func.count(DailySubmission.id)).where(
            and_(today_filter, DailySubmission.status == SubmissionStatus.FLAGGED)
        )
    )
    flagged_today: int = flagged_result.scalar_one() or 0

    # Pending review = RECEIVED (not yet reviewed by any officer)
    pending_result = await db.execute(
        select(func.count(DailySubmission.id)).where(
            and_(today_filter, DailySubmission.status == SubmissionStatus.RECEIVED)
        )
    )
    pending_review: int = pending_result.scalar_one() or 0

    # Coverage percentage & Total Centres calculation
    if settings.demo_mode:
        total_awc_centres = 1
        coverage = 100.0 if reported_today > 0 else 0.0
    else:
        total_awc_centres = TOTAL_AWC_CENTRES
        coverage = round((reported_today / TOTAL_AWC_CENTRES) * 100, 1) if reported_today else 0.0

    now_ist = datetime.now(ist)

    logger.info(
        "dashboard_stats_computed",
        demo_mode=settings.demo_mode,
        demo_awc_id=settings.demo_awc_id if settings.demo_mode else None,
        reported_today=reported_today,
        approved_today=approved_today,
        flagged_today=flagged_today,
        pending_review=pending_review,
        coverage_percent=coverage,
    )

    return DashboardStats(
        total_awc_centres=total_awc_centres,
        reported_today=reported_today,
        approved_today=approved_today,
        flagged_today=flagged_today,
        pending_review=pending_review,
        coverage_percent=coverage,
        as_of=now_ist.strftime("%d/%m/%Y %I:%M %p IST"),
    )


# ═════════════════════════════════════════════════════════════════════
# ENDPOINT 2: Paginated Submissions List
# GET /api/v1/dashboard/submissions
# ═════════════════════════════════════════════════════════════════════

@router.get(
    "/submissions",
    response_model=SubmissionListResponse,
    summary="List Submissions with Filters & Pagination",
    description=(
        "Returns a paginated, searchable list of daily submissions. "
        "Filterable by center_name, block_name, status, and date range. "
        "Ordered by submission_timestamp descending (most recent first)."
    ),
)
async def list_submissions(
    db: AsyncSession = Depends(get_db),
    # --- Pagination ---
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Records per page (max 100)"),
    # --- Filters ---
    search: Optional[str] = Query(None, description="Search in center_name, block_name, AWC ID, worker name"),
    awc_id: Optional[str] = Query(None, description="Filter by AWC centre ID (partial match)"),
    center_name: Optional[str] = Query(None, description="Filter by centre name (partial match)"),
    block_name: Optional[str] = Query(None, description="Filter by block name (partial match)"),
    status: Optional[str] = Query(None, description="Filter by status: RECEIVED, APPROVED, FLAGGED, REJECTED"),
    today_only: bool = Query(True, description="Show only today's submissions (IST)"),
    date: Optional[str] = Query(None, description="Date filter YYYY-MM-DD"),
) -> SubmissionListResponse:
    """
    Returns a paginated list of submissions for the dashboard data table.
    Supports multi-field search and status filtering.
    """
    # Build the base query
    filters = [DailySubmission.is_authorized == True]

    # Version 3.0: CEO Demo Mode automatic filter
    if settings.demo_mode:
        filters.append(DailySubmission.awc_id == settings.demo_awc_id)

    # Date filter
    if today_only and not date:
        start_utc, end_utc = _date_utc_range(None)
    else:
        start_utc, end_utc = _date_utc_range(date)
        
    filters.append(DailySubmission.submission_timestamp >= start_utc)
    filters.append(DailySubmission.submission_timestamp <= end_utc)

    # Status filter
    if status and isinstance(status, str):
        status_upper = status.upper()
        filters.append(DailySubmission.status == status_upper)

    # AWC ID filter
    if awc_id and isinstance(awc_id, str):
        filters.append(DailySubmission.awc_id.ilike(f"%{awc_id}%"))

    # Center name filter
    if center_name and isinstance(center_name, str):
        filters.append(DailySubmission.center_name.ilike(f"%{center_name}%"))

    # Block name filter
    if block_name and isinstance(block_name, str):
        filters.append(DailySubmission.block_name.ilike(f"%{block_name}%"))

    # Global search across multiple fields
    if search and isinstance(search, str):
        search_term = f"%{search}%"
        filters.append(
            or_(
                DailySubmission.center_name.ilike(search_term),
                DailySubmission.block_name.ilike(search_term),
                DailySubmission.awc_id.ilike(search_term),
                DailySubmission.worker_name.ilike(search_term),
                DailySubmission.worker_phone.ilike(search_term),
            )
        )

    # Count total matching records
    count_query = select(func.count(DailySubmission.id)).where(and_(*filters))
    total_result = await db.execute(count_query)
    total: int = total_result.scalar_one() or 0

    # Paginated data query
    offset = (page - 1) * page_size
    data_query = (
        select(DailySubmission)
        .where(and_(*filters))
        .order_by(DailySubmission.submission_timestamp.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(data_query)
    submissions = result.scalars().all()

    # Map ORM objects to response schema
    items = [
        SubmissionListItem(
            id=s.id,
            submission_id=s.submission_id,
            awc_id=s.awc_id,
            center_name=s.center_name,
            block_name=s.block_name,
            worker_name=s.worker_name,
            worker_phone=s.worker_phone,
            submission_timestamp=s.submission_timestamp,
            message_type=s.message_type,
            has_media=bool(s.raw_media_id),
            latitude=s.latitude,
            longitude=s.longitude,
            status=s.status,
            is_authorized=s.is_authorized,
            ai_score=s.ai_score,
            review_action=s.review_action,
            flag_reason=s.flag_reason,
            reviewer_name=s.reviewer_name,
            reviewed_at=s.reviewed_at,
            ack_sent=s.ack_sent,
        )
        for s in submissions
    ]

    total_pages = max(1, -(-total // page_size))  # Ceiling division

    logger.info(
        "submissions_listed",
        total=total,
        page=page,
        page_size=page_size,
        filters={"search": search, "status": status, "today_only": today_only},
    )

    return SubmissionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        filters_applied={
            "search": search,
            "center_name": center_name,
            "block_name": block_name,
            "status": status,
            "today_only": today_only,
            "awc_id": awc_id,
        },
    )


# ═════════════════════════════════════════════════════════════════════
# ENDPOINT 3: Supervisor Review Action
# POST /api/v1/dashboard/submissions/{submission_id}/review
# ═════════════════════════════════════════════════════════════════════

@router.post(
    "/submissions/{submission_id}/review",
    response_model=ReviewResponse,
    summary="Supervisor Review: Approve or Flag a Submission",
    description=(
        "Allows district officers to APPROVE or FLAG a submission. "
        "Records the reviewer identity, timestamp, flag reason, and remarks "
        "for a complete audit trail. Accepts either the integer DB ID or "
        "the UUID submission_id string."
    ),
)
async def review_submission(
    submission_id: str,
    review: ReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> ReviewResponse:
    """
    Supervisor review action endpoint.

    Looks up the submission by its UUID or integer ID,
    validates it is in a reviewable state, applies the review action,
    and persists the full audit trail.

    Args:
        submission_id: UUID string or integer ID of the submission
        review: ReviewRequest body with action, flag_reason, remarks, reviewer info

    Returns:
        ReviewResponse with previous/new status and audit metadata
    """
    reviewed_at = datetime.now(timezone.utc)

    # ── Lookup: support both UUID string and integer ID ──────────────
    submission: Optional[DailySubmission] = None

    # Try integer ID first
    if submission_id.isdigit():
        result = await db.execute(
            select(DailySubmission).where(DailySubmission.id == int(submission_id))
        )
        submission = result.scalar_one_or_none()
    else:
        # Try UUID string
        result = await db.execute(
            select(DailySubmission).where(DailySubmission.submission_id == submission_id)
        )
        submission = result.scalar_one_or_none()

    if submission is None:
        logger.warning("review_submission_not_found", submission_id=submission_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Submission '{submission_id}' not found.",
        )

    # ── Guard: only authorized submissions can be reviewed ───────────
    if not submission.is_authorized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot review an unauthorized/rejected submission.",
        )

    # ── Guard: prevent re-reviewing the same record by the same action ─
    if submission.review_action == review.action:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Submission is already marked as {review.action}.",
        )

    # ── Validate flag_reason is provided when action = FLAGGED ───────
    if review.action == "FLAGGED" and not review.flag_reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="flag_reason is required when action is FLAGGED.",
        )

    previous_status = submission.status

    # ── Apply review ─────────────────────────────────────────────────
    submission.status = review.action          # APPROVED or FLAGGED
    submission.review_action = review.action
    submission.reviewed_at = reviewed_at
    submission.reviewer_id = review.reviewer_id or "dashboard_officer"
    submission.reviewer_name = review.reviewer_name or "District Officer"
    submission.flag_reason = review.flag_reason
    submission.reviewer_remarks = review.remarks
    submission.updated_at = reviewed_at

    await db.commit()

    from zoneinfo import ZoneInfo
    ist = ZoneInfo("Asia/Kolkata")
    reviewed_at_ist = reviewed_at.astimezone(ist).strftime("%d/%m/%Y %I:%M %p IST")

    logger.info(
        "submission_reviewed",
        submission_id=submission.submission_id,
        action=review.action,
        previous_status=previous_status,
        new_status=submission.status,
        reviewer=submission.reviewer_name,
        flag_reason=review.flag_reason,
    )

    action_label = "अनुमोदित" if review.action == "APPROVED" else "फ्लैग किया"

    return ReviewResponse(
        success=True,
        submission_id=submission.submission_id,
        previous_status=previous_status,
        new_status=submission.status,
        action=review.action,
        reviewed_by=submission.reviewer_name,
        reviewed_at=reviewed_at_ist,
        message=f"रिपोर्ट सफलतापूर्वक {action_label} गई।",
    )


# ═════════════════════════════════════════════════════════════════════
# HTML Dashboard Panel Route
# GET /dashboard  (served from app/main.py after mounting templates)
# ═════════════════════════════════════════════════════════════════════
# Note: The HTML route is registered in main.py (not here) so it can
# access the Jinja2Templates instance mounted on the FastAPI app level.
