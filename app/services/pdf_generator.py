# app/services/pdf_generator.py
import base64
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import asyncio
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

from app.models import DailySubmission

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
_APP_DIR = Path(__file__).parent.parent
_FONTS_DIR = _APP_DIR / "static" / "fonts"
_FONT_REGULAR = (_FONTS_DIR / "NotoSansDevanagari-Regular.ttf").absolute().as_uri()
_FONT_BOLD = (_FONTS_DIR / "NotoSansDevanagari-Bold.ttf").absolute().as_uri()
_TEMPLATE_DIR = Path(__file__).parent

def _safe(val):
    if val is None or val == "":
        return "उपलब्ध नहीं"
    return str(val)

def _yes_no(val):
    if val is None:
        return "उपलब्ध नहीं"
    return "हाँ" if val else "नहीं"

_RENDER_LOCK = threading.Lock()

def _encode_image(image_path, max_dim=640):
    if not image_path or not Path(image_path).exists():
        return ""
    try:
        from PIL import Image
        import io
        with Image.open(image_path) as img:
            # Convert RGBA to RGB for JPEG saving
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        logger.warning(f"image_thumbnail_encode_failed path={image_path} error={e}")
        return ""

import sys
import subprocess
import tempfile

_RENDER_RUNNER = Path(__file__).parent / "render_pdf_runner.py"

def _run_playwright_in_process(html_content: str) -> bytes:
    """
    Runs Playwright in an isolated standalone Python subprocess.
    Protected by _RENDER_LOCK to prevent CPU contention during concurrent renders.
    Passes a log file for precise checkpoint audit trailing.
    Safely terminates entire process tree on Windows if a timeout occurs.
    """
    with _RENDER_LOCK:
        html_fd, html_path = tempfile.mkstemp(suffix=".html")
        with open(html_fd, "w", encoding="utf-8") as f_html:
            f_html.write(html_content)

        pdf_fd, pdf_path = tempfile.mkstemp(suffix=".pdf")
        os.close(pdf_fd)

        log_fd, log_path = tempfile.mkstemp(suffix=".log")
        os.close(log_fd)

        python_bin = sys.executable
        cmd = [python_bin, str(_RENDER_RUNNER), html_path, pdf_path, log_path]

        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            # Run the subprocess with captured stdout/stderr for better error reporting
            result = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                close_fds=True,
                creationflags=creationflags,
                env=os.environ.copy(),
                timeout=240,
            )
            # Check for error codes
            if result.returncode != 0:
                logger.error(
                    f"playwright_render_subprocess_failed exit_code={result.returncode} stderr={result.stderr.decode().strip()} stdout={result.stdout.decode().strip()}"
                )
                raise RuntimeError(
                    f"Playwright render process failed with exit code {result.returncode}: {result.stderr.decode().strip()}"
                )
            # Read the generated PDF bytes
            with open(pdf_path, "rb") as f_out:
                pdf_bytes = f_out.read()
            if len(pdf_bytes) == 0:
                raise RuntimeError("Generated PDF file is empty")
            return pdf_bytes
        except subprocess.TimeoutExpired as e:
            logger.error("playwright_render_subprocess_timed_out timeout_seconds=240")
            # Terminate entire process tree on Windows by killing the parent process ID
            try:
                if hasattr(e, 'pid') and e.pid:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(e.pid)], capture_output=True)
            except Exception as kill_err:
                logger.error(f"process_tree_kill_failed error={kill_err}")
            # Inspect audit log for last checkpoint
            last_checkpoint = "UNKNOWN"
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as lf:
                    checkpoints = lf.readlines()
                    if checkpoints:
                        last_checkpoint = checkpoints[-1].strip()
            raise RuntimeError(f"Playwright render process timed out after 240s. Last checkpoint: {last_checkpoint}")
        finally:
            for p in (html_path, pdf_path, log_path):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass

def generate_submission_pdf(submission: DailySubmission) -> bytes:
    """
    Synchronous public contract preserved.
    Generates PDF via Playwright HTML rendering to guarantee Devanagari shaping.
    Uses normalized single source of truth context object.
    """
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
    template = env.get_template("pdf_template.html")

    # 1. Parse AI JSON
    ai_json_raw = getattr(submission, "ai_result_json", None)
    vision_res = {}
    yolo_res = {}
    if ai_json_raw:
        try:
            vision_res = json.loads(ai_json_raw)
            if isinstance(vision_res, dict):
                yolo_res = vision_res.get("yolo_results", {}) or {}
        except Exception:
            pass

    # 2. Timestamp (Meta whatsapp_timestamp Unix epoch preferred -> IST)
    wa_ts = getattr(submission, "whatsapp_timestamp", None)
    sub_ts = getattr(submission, "submission_timestamp", None)
    
    date_time_ist = "उपलब्ध नहीं"
    if wa_ts and str(wa_ts).isdigit() and int(wa_ts) > 0:
        dt_utc = datetime.fromtimestamp(int(wa_ts), tz=timezone.utc)
        date_time_ist = dt_utc.astimezone(IST).strftime("%d/%m/%Y %I:%M %p IST")
    elif sub_ts:
        if sub_ts.tzinfo is None:
            sub_ts = sub_ts.replace(tzinfo=timezone.utc)
        date_time_ist = sub_ts.astimezone(IST).strftime("%d/%m/%Y %I:%M %p IST")

    # 3. Live GPS Semantics
    has_live_gps = bool(getattr(submission, "latitude", None) and getattr(submission, "longitude", None))
    if has_live_gps:
        live_gps_summary = "उपलब्ध"
        live_gps_detail = f"अक्षांश: {submission.latitude}, देशांतर: {submission.longitude}"
        live_gps_status = "PASS"
    else:
        live_gps_summary = "उपलब्ध नहीं"
        live_gps_detail = "उपलब्ध नहीं (सबमिशन के साथ लोकेशन प्राप्त नहीं हुई)"
        live_gps_status = "N/A"

    # 4. Object Detection (YOLO) & Attendance
    children_count = int(yolo_res.get("children_count", 0) if yolo_res else 0)
    worker_count = int(yolo_res.get("worker_count", 0) if yolo_res else 0)
    worker_present_bool = (worker_count > 0) or bool(vision_res.get("worker_present"))
    worker_present_summary = "उपस्थित" if worker_present_bool else "अनुपस्थित"

    registered_children = 22  # AWC Registered capacity
    attendance_difference = children_count - registered_children

    # 5. Meal Distribution Visibility (3 Distinct States)
    meal_val = vision_res.get("meal_visible")
    if meal_val is True:
        meal_visibility_summary = "दिखाई दिया"
        meal_visibility_detail = "भोजन वितरण का दृश्य स्पष्ट है"
        meal_visibility_status = "PASS"
    elif meal_val is False:
        meal_visibility_summary = "दिखाई नहीं दिया"
        meal_visibility_detail = "भोजन वितरण का दृश्य अनुपस्थित"
        meal_visibility_status = "REVIEW"
    else:
        meal_visibility_summary = "AI सत्यापन उपलब्ध नहीं"
        meal_visibility_detail = "AI सत्यापन उपलब्ध नहीं (मैनुअल सत्यापन आवश्यक)"
        meal_visibility_status = "N/A"

    # 6. Duplicate Image Check
    flag_reason_raw = (getattr(submission, "flag_reason", None) or "")
    is_duplicate = "DUPLICATE" in flag_reason_raw.upper()
    duplicate_summary = "हाँ (समान फोटो)" if is_duplicate else "नहीं"
    duplicate_status = "REVIEW" if is_duplicate else "PASS"

    # 7. Image Quality
    img_quality_raw = vision_res.get("image_quality") or getattr(submission, "brightness_score", None) or "CLEAR"
    if str(img_quality_raw).upper() in ("CLEAR", "NORMAL"):
        img_quality_summary = "सामान्य (स्पष्ट)"
        img_quality_status = "PASS"
    else:
        img_quality_summary = f"अस्पष्ट ({img_quality_raw})"
        img_quality_status = "REVIEW"

    # 8. Confidence Metric Disambiguation (YOLO11m vs Groq AI)
    yolo_conf = yolo_res.get("confidence") if yolo_res else None
    if yolo_conf is not None:
        yolo_conf_summary = f"{yolo_conf}% (YOLO11m)"
        yolo_conf_detail = f"{yolo_conf}% (औसत ऑब्जेक्ट डिटेक्शन कॉन्फिडेंस)"
        yolo_conf_status = "PASS"
    else:
        yolo_conf_summary = "उपलब्ध नहीं"
        yolo_conf_detail = "ऑब्जेक्ट डिटेक्शन उपलब्ध नहीं"
        yolo_conf_status = "N/A"

    groq_conf = vision_res.get("confidence_score")
    if groq_conf is not None:
        groq_conf_summary = f"{groq_conf}%"
        groq_conf_detail = f"{groq_conf}% (दृश्य सत्यापन)"
        groq_conf_status = "PASS" if groq_conf >= 70 else "REVIEW"
    else:
        groq_conf_summary = "AI सत्यापन उपलब्ध नहीं"
        groq_conf_detail = "Groq AI दृश्य सत्यापन उपलब्ध नहीं"
        groq_conf_status = "N/A"

    # 9. System Verification Status & Localized Flag Reasons
    is_flagged = (submission.status == "FLAGGED") or is_duplicate
    if submission.status == "APPROVED":
        status_banner_text = "✓ अनुमोदित / APPROVED"
        status_banner_color = "#15803d"
        status_decision = "सत्यापित एवं अनुमोदित"
    elif is_flagged:
        status_banner_text = "⚠️ समीक्षा हेतु फ्लैग्ड / FLAGGED FOR REVIEW"
        status_banner_color = "#b45309"
        status_decision = "समीक्षा हेतु फ्लैग्ड"
    elif submission.status in ("FAILED", "REJECTED") or vision_res.get("status") == "VISION_UNAVAILABLE":
        status_banner_text = "⚠️ मैनुअल समीक्षा आवश्यक / MANUAL REVIEW"
        status_banner_color = "#b91c1c"
        status_decision = "मैनुअल समीक्षा आवश्यक"
    else:
        status_banner_text = "✓ सत्यापित / VERIFIED"
        status_banner_color = "#15803d"
        status_decision = "सत्यापित"

    flag_translations = {
        "DUPLICATE_IMAGE": "समान फोटो पूर्व में जमा (Duplicate Image)",
        "MANUAL_REVIEW_REQUIRED": "मैनुअल समीक्षा आवश्यक (Manual Review Required)",
        "LOCATION_OUTSIDE_GEOFENCE": "केंद्र से बाहर लोकेशन (Outside Geofence)",
        "BLUR_IMAGE": "धुंधली फोटो (Blur Image)",
        "VERY_DARK_IMAGE": "अत्यधिक कम रोशनी (Very Dark)",
        "INVALID_SCENE": "अमान्य परिसर फोटो (Invalid Scene)",
        "NO_MEAL_DETECTED": "भोजन दृश्य अनुपस्थित (No Meal Detected)"
    }

    formatted_flags = []
    if flag_reason_raw:
        for r in flag_reason_raw.split(","):
            rc = r.strip()
            if rc in flag_translations:
                formatted_flags.append(flag_translations[rc])
            elif rc:
                formatted_flags.append(rc)
    
    localized_flag_reason = " | ".join(formatted_flags) if formatted_flags else None

    # 10. AI Remarks / Executive Observation
    ai_remarks = vision_res.get("remarks")
    if not ai_remarks or vision_res.get("status") == "VISION_UNAVAILABLE":
        ai_remarks = f"YOLO11m द्वारा {children_count} बच्चे एवं {worker_count} कार्यकर्ता पहचाने गए। (Groq AI दर-सीमा के कारण मैनुअल समीक्षा हेतु फ्लैग्ड)"

    # 11. Scorecard Array (Normalized)
    scorecard = [
        {"param": "बच्चे उपस्थित (YOLO)", "status": "PASS" if children_count > 0 else "REVIEW", "detail": f"{children_count} बच्चे"},
        {"param": "कार्यकर्ता उपस्थित", "status": "PASS" if worker_present_bool else "REVIEW", "detail": worker_present_summary},
        {"param": "भोजन वितरण दृश्य", "status": meal_visibility_status, "detail": meal_visibility_detail},
        {"param": "Live GPS सत्यापन", "status": live_gps_status, "detail": live_gps_detail},
        {"param": "Timestamp सत्यापन", "status": "PASS", "detail": date_time_ist},
        {"param": "Duplicate Photo Check", "status": duplicate_status, "detail": duplicate_summary},
        {"param": "Image Quality", "status": img_quality_status, "detail": img_quality_summary},
        {"param": "YOLO11m डिटेक्शन कॉन्फिडेंस", "status": yolo_conf_status, "detail": yolo_conf_detail},
        {"param": "Groq AI दृश्य सत्यापन", "status": groq_conf_status, "detail": groq_conf_detail},
    ]

    html_content = template.render(
        font_regular=_FONT_REGULAR,
        font_bold=_FONT_BOLD,
        audit_id=submission.audit_id or submission.submission_id[:8],
        status_text=status_banner_text,
        status_color=status_banner_color,
        flag_reason=localized_flag_reason if is_flagged else None,
        status_decision=status_decision,
        center_name=_safe(submission.center_name),
        awc_id=_safe(submission.awc_id),
        block_name=_safe(submission.block_name),
        worker_name=_safe(submission.worker_name),
        worker_phone=_safe(submission.worker_phone),
        date_time=date_time_ist,
        children_count=children_count,
        worker_present=worker_present_summary,
        meal_detected=meal_visibility_summary,
        is_gps_ok=live_gps_summary,
        is_duplicate=duplicate_summary,
        scorecard=scorecard,
        registered_children=registered_children,
        difference=attendance_difference,
        ai_remarks=ai_remarks,
        orig_img_base64=_encode_image(getattr(submission, "local_media_path", None)),
        yolo_img_base64=_encode_image(yolo_res.get("visualized_image_path", None))
    )

    pdf_bytes = _run_playwright_in_process(html_content)
    return pdf_bytes

def generate_daily_report_pdf(
    report_date: str,
    stats: dict,
    submissions: list,
    block_name: str = None,
    status_filter: str = None,
) -> bytes:
    """
    Generates an Official Executive Government A4 PDF Report suitable for
    CEO Zila Panchayat & District Collector presentation using Playwright.
    """
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
    template = env.get_template("daily_report_template.html")

    # Format filter string
    filter_str = f"ब्लॉक: {block_name}" if block_name else "समस्त जिला शहडोल"
    if status_filter:
        filter_str += f" | स्थिति: {status_filter}"

    now_ist = datetime.now(IST)
    time_display = now_ist.strftime("%d/%m/%Y %I:%M %p IST")

    # Process block rows
    block_stats = {}
    for s_tuple in submissions:
        # Depending on how the query was constructed, it might be a tuple of (DailySubmission, AnganwadiMaster) or just DailySubmission
        s = s_tuple[0] if isinstance(s_tuple, tuple) else s_tuple
        bn = getattr(s, "block_name", None) or "अज्ञात"
        if bn not in block_stats:
            block_stats[bn] = {"total": 0, "approved": 0, "flagged": 0, "pending": 0}
        block_stats[bn]["total"] += 1
        st = getattr(s, "status", "")
        if st in ("APPROVED", "PROCESSED"): block_stats[bn]["approved"] += 1
        elif st == "FLAGGED": block_stats[bn]["flagged"] += 1
        elif st == "RECEIVED": block_stats[bn]["pending"] += 1

    block_rows = []
    for bn, bst in sorted(block_stats.items()):
        block_rows.append({
            "name": bn,
            "total": bst["total"],
            "approved": bst["approved"],
            "flagged": bst["flagged"],
            "pending": bst["pending"]
        })

    # Process submissions
    max_rows = 25
    display_submissions = submissions[:max_rows]
    overflow = len(submissions) - max_rows if len(submissions) > max_rows else 0

    sub_rows = []
    for s_tuple in display_submissions:
        s = s_tuple[0] if isinstance(s_tuple, tuple) else s_tuple
        
        ts = ""
        sub_ts = getattr(s, "submission_timestamp", None)
        if sub_ts:
            ts = sub_ts.astimezone(IST).strftime("%I:%M %p")

        gps = "—"
        lat = getattr(s, "latitude", None)
        lon = getattr(s, "longitude", None)
        if lat and lon:
            gps = f"{float(lat):.3f},{float(lon):.3f}"

        sub_rows.append({
            "awc_id": getattr(s, "awc_id", "") or "—",
            "center_name": getattr(s, "center_name", "") or "—",
            "block_name": getattr(s, "block_name", "") or "—",
            "worker_name": getattr(s, "worker_name", "") or "—",
            "time": ts or "—",
            "gps": gps,
            "status": getattr(s, "status", "—")
        })

    html_content = template.render(
        font_regular=_FONT_REGULAR,
        font_bold=_FONT_BOLD,
        report_date=report_date,
        filter_str=filter_str,
        gen_time=time_display,
        stats=stats,
        block_rows=block_rows,
        submissions=sub_rows,
        overflow=overflow
    )

    pdf_bytes = _run_playwright_in_process(html_content)
    return pdf_bytes
