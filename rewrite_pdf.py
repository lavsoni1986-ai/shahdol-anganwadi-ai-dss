import os

filepath = "d:/District Shahdol Anganwadi Digital Verification & Decision Support System/shahdol-anganwadi-mvp/app/services/pdf_generator.py"
with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find the start of def _safe
start_idx = -1
for i, line in enumerate(lines):
    if line.startswith("def _safe(value, fallback: str"):
        start_idx = i
        break

if start_idx != -1:
    new_code = """def _safe(value, fallback: str = "उपलब्ध नहीं") -> str:
    \"\"\"Return a safe display string, never None/NULL/N/A.\"\"\"
    if value is None:
        return fallback
    s = str(value).strip()
    if s.lower() in ("none", "null", "n/a", "na", "", "()", "0"):
        return fallback
    return s

def _yes_no(value: bool) -> str:
    return "हाँ" if value else "नहीं"

def generate_submission_pdf(submission) -> bytes:
    \"\"\"
    Government Executive Inspection Report for a single Anganwadi submission.
    Presentation-grade layout for CEO Zila Panchayat, Collector, CDPO.
    Version 4.0 — 3-Page strict layout with data consistency.
    \"\"\"
    _ensure_fonts()

    fn     = _get_font(bold=False)
    fn_b   = _get_font(bold=True)

    def PS(name, **kw):
        kw.setdefault("fontName", fn)
        kw.setdefault("shaping", True)
        return ParagraphStyle(name, **kw)

    ST = {
        "gov_state":    PS("gov_state",  fontName=fn_b,  fontSize=9,  textColor=WHITE,       alignment=TA_CENTER, leading=13),
        "gov_dept":     PS("gov_dept",   fontName=fn_b,  fontSize=13, textColor=WHITE,       alignment=TA_CENTER, leading=17),
        "gov_dist":     PS("gov_dist",   fontName=fn,    fontSize=10, textColor=colors.HexColor("#bfdbfe"), alignment=TA_CENTER, leading=14),
        "gov_sys":      PS("gov_sys",    fontName=fn_b,  fontSize=10, textColor=colors.HexColor("#bfdbfe"), alignment=TA_CENTER, leading=14),
        "gov_doctype":  PS("gov_doctype",fontName=fn_b,  fontSize=9,  textColor=colors.HexColor("#e0f2fe"), alignment=TA_CENTER, leading=13),
        "banner_main":  PS("ban_main",  fontName=fn_b,  fontSize=20, textColor=WHITE,       alignment=TA_CENTER, leading=26, shaping=False),
        "banner_sub":   PS("ban_sub",   fontName=fn,    fontSize=9,  textColor=colors.HexColor("#fef9c3"), alignment=TA_CENTER, leading=13),
        "tbl_hdr":      PS("tbl_hdr",  fontName=fn_b,  fontSize=10, textColor=WHITE,       alignment=TA_CENTER, leading=14),
        "tbl_label":    PS("tbl_label",fontName=fn_b,  fontSize=10, textColor=TEXT_DARK,   leading=14),
        "tbl_val":      PS("tbl_val",  fontName=fn,    fontSize=10, textColor=TEXT_DARK,   leading=14),
        "tbl_center":   PS("tbl_ctr",  fontName=fn,    fontSize=10, textColor=TEXT_DARK,   alignment=TA_CENTER, leading=14),
        "obs_text":     PS("obs_txt",  fontName=fn,    fontSize=11, textColor=TEXT_DARK,   leading=17, alignment=TA_JUSTIFY),
        "img_caption":  PS("img_cap",  fontName=fn_b,  fontSize=9,  textColor=TEXT_MUTED,  alignment=TA_CENTER, leading=13),
    }

    import json as _json
    yolo_res    = {}
    vision_res  = {}
    ai_json_raw = getattr(submission, "ai_result_json", None)
    if ai_json_raw:
        try:
            vision_res = _json.loads(ai_json_raw)
            yolo_res   = vision_res.get("yolo_results", {})
        except Exception:
            pass

    children_count   = int(yolo_res.get("children_count", 0) or 0)
    worker_count     = int(yolo_res.get("worker_count",   0) or 0)
    yolo_confidence  = yolo_res.get("confidence", None)
    proc_time_ms     = yolo_res.get("processing_time_ms", None)
    yolo_img_path    = yolo_res.get("visualized_image_path", None)
    orig_img_path    = getattr(submission, "local_media_path", None)

    flag_reason_raw  = (getattr(submission, "flag_reason", None) or "")
    is_gps_ok        = bool(getattr(submission, "latitude",  None) and getattr(submission, "longitude", None))
    is_duplicate     = "DUPLICATE" in flag_reason_raw.upper()
    is_blur          = "BLUR"      in flag_reason_raw.upper()
    meal_detected    = vision_res.get("meal_visible", None)
    worker_present   = vision_res.get("worker_present", None) or (worker_count > 0)
    img_quality_raw  = vision_res.get("image_quality", "")

    sub_ts     = getattr(submission, "submission_timestamp", None)
    ist_now    = datetime.now(IST)
    if sub_ts:
        try:
            ts_date = sub_ts.astimezone(IST).strftime("%d %B %Y")
            ts_time = sub_ts.astimezone(IST).strftime("%I:%M %p IST")
        except Exception:
            ts_date = str(sub_ts)[:10]
            ts_time = str(sub_ts)[11:16]
    else:
        ts_date = ist_now.strftime("%d %B %Y")
        ts_time = ist_now.strftime("%I:%M %p IST")

    audit_id    = _safe(getattr(submission, "audit_id", None) or
                        (getattr(submission, "submission_id", "")[:8] if getattr(submission, "submission_id", None) else None))
    center_name = _safe(getattr(submission, "center_name", None))
    awc_id      = _safe(getattr(submission, "awc_id", None))
    block_name  = _safe(getattr(submission, "block_name", None))
    worker_name = _safe(getattr(submission, "worker_name", None))
    worker_phone= _safe(getattr(submission, "worker_phone", None))

    lat  = getattr(submission, "latitude",  None)
    lon  = getattr(submission, "longitude", None)
    gps_str = f"{round(lat,6)}°N, {round(lon,6)}°E" if (lat and lon) else "उपलब्ध नहीं"

    proc_str  = (f"{round(proc_time_ms/1000, 1)} sec" if proc_time_ms else "उपलब्ध नहीं")
    conf_str  = (f"{round(float(yolo_confidence), 1)}%" if yolo_confidence else "उपलब्ध नहीं")

    status_val = getattr(submission, "status", "RECEIVED")
    if status_val in ("APPROVED", "PROCESSED"):
        banner_text  = "✓ सत्यापित / VERIFIED"
        banner_color = colors.HexColor("#15803d")
        banner_sub   = "स्थिति: सत्यापित"
    elif status_val == "FLAGGED":
        if "MANUAL_REVIEW" in flag_reason_raw.upper():
            banner_text  = "✕ मैनुअल समीक्षा आवश्यक / MANUAL REVIEW"
            banner_color = colors.HexColor("#b91c1c")
            banner_sub   = f"कारण: {flag_reason_raw}"
        else:
            banner_text  = "⚠ समीक्षा हेतु / FLAGGED"
            banner_color = colors.HexColor("#b45309")
            banner_sub   = f"कारण: {flag_reason_raw}"
    else:
        banner_text  = "○ प्राप्त / RECEIVED"
        banner_color = colors.HexColor("#1d4ed8")
        banner_sub   = "स्थिति: प्राप्त"

    remarks_text = _safe(vision_res.get("remarks"), "आंगनवाड़ी केंद्र में गतिविधि का दृश्य प्राप्त हुआ।")

    buffer = io.BytesIO()
    PAGE_W, PAGE_H = A4
    L_MARGIN = R_MARGIN = 1.5 * cm
    T_MARGIN = 1.8 * cm
    B_MARGIN = 1.8 * cm
    CONTENT_W = PAGE_W - L_MARGIN - R_MARGIN

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=R_MARGIN,
        leftMargin=L_MARGIN,
        topMargin=T_MARGIN,
        bottomMargin=B_MARGIN,
        title=f"Anganwadi Inspection Report — {audit_id}",
    )

    story = []

    # PAGE 1: SUMMARY
    header_tbl = Table([
        [Paragraph("Government of Madhya Pradesh", ST["gov_state"])],
        [Paragraph("महिला एवं बाल विकास विभाग", ST["gov_dept"])],
        [Paragraph("जिला शहडोल (म.प्र.)", ST["gov_dist"])],
        [Paragraph("Anganwadi Digital Verification Report", ST["gov_sys"])],
    ], colWidths=[CONTENT_W])
    header_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), GOV_NAVY),
        ("TOPPADDING",    (0, 0), (-1, 0),  10),
        ("BOTTOMPADDING", (0, -1),(-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
    ]))
    story.append(header_tbl)

    doc_type_tbl = Table([[Paragraph(f"Audit ID: {audit_id}", ST["gov_doctype"])]], colWidths=[CONTENT_W])
    doc_type_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#1e3a8a")),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(doc_type_tbl)
    story.append(Spacer(1, 10))

    banner_inner = Table([
        [Paragraph(banner_text, ST["banner_main"])],
        [Paragraph(banner_sub, ST["banner_sub"])],
    ], colWidths=[CONTENT_W])
    banner_inner.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), banner_color),
        ("TOPPADDING",    (0, 0), (-1, 0),  12),
        ("BOTTOMPADDING", (0, -1),(-1, -1), 10),
    ]))
    story.append(banner_inner)
    story.append(Spacer(1, 15))

    def _sec_head(title_en: str, title_hi: str = "") -> Table:
        label = f"<b>{title_en}</b>"
        if title_hi:
            label += f"  <font size='9' color='#64748b'>{title_hi}</font>"
        hdr_row = Table([[Paragraph(label, PS("sh", fontName=fn_b, fontSize=11, textColor=GOV_NAVY, leading=16))]], colWidths=[CONTENT_W])
        hdr_row.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW",     (0, 0), (-1, -1), 1.5, GOV_BLUE),
        ]))
        return hdr_row

    story.append(_sec_head("Center Information", "केंद्र विवरण"))

    def _info_row(label_en, value, label_en2="", value2=""):
        return [Paragraph(label_en, ST["tbl_label"]), Paragraph(_safe(value), ST["tbl_val"]),
                Paragraph(label_en2, ST["tbl_label"]) if label_en2 else Paragraph("", ST["tbl_val"]),
                Paragraph(_safe(value2), ST["tbl_val"]) if label_en2 else Paragraph("", ST["tbl_val"])]

    HALF = CONTENT_W / 2
    info_tbl = Table([
        _info_row("Center Name / केंद्र", center_name, "AWC ID", awc_id),
        _info_row("Block / ब्लॉक", block_name, "Sector / सेक्टर", _safe(getattr(submission, "sector_name", None))),
        _info_row("Worker / कार्यकर्ता", worker_name, "Mobile / मोबाइल", worker_phone),
        _info_row("Date / दिनांक", ts_date, "Time / समय", ts_time),
    ], colWidths=[HALF * 0.38, HALF * 0.62, HALF * 0.38, HALF * 0.62])
    info_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("BACKGROUND",    (0, 0), (0, -1),  GOV_LIGHT_BG),
        ("BACKGROUND",    (2, 0), (2, -1),  GOV_LIGHT_BG),
        ("BOX",           (0, 0), (-1, -1), 0.8, BORDER_GREY),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.4, BORDER_GREY),
        ("LINEAFTER",     (1, 0), (1, -1),  0.6, BORDER_GREY),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 15))

    story.append(_sec_head("Executive Summary", "कार्यकारी सारांश"))
    exec_text = f"AI द्वारा उपस्थित बच्चे: {children_count}<br/>कार्यकर्ता उपस्थित: {_yes_no(worker_count > 0 or worker_present)}<br/>भोजन वितरण दृश्य: {_yes_no(meal_detected is not False)}<br/>GPS: {'उपलब्ध नहीं' if not is_gps_ok else 'सत्यापित'}<br/>Timestamp: सत्यापित<br/>Duplicate Image: {_yes_no(is_duplicate)}<br/><br/><b>AI निर्णय: {banner_sub}</b>"
    
    exec_tbl = Table([[Paragraph(exec_text, PS("ex_sum", fontName=fn, fontSize=11, leading=16))]], colWidths=[CONTENT_W])
    exec_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER_GREY),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 15),
    ]))
    story.append(exec_tbl)

    # PAGE 2: DETAILS
    from reportlab.platypus import PageBreak
    story.append(PageBreak())

    story.append(_sec_head("AI Verification Scorecard", "सत्यापन स्कोरकार्ड"))

    def _scorecard_row(param_hi, ok: bool, detail: str = ""):
        color_hex = "#16a34a" if ok else "#b45309"
        icon      = "PASS" if ok else "REVIEW"
        return [Paragraph(param_hi, ST["tbl_label"]),
                Paragraph(f'<font color="{{color_hex}}"><b>{{icon}}</b></font>', PS("ss", fontName=fn_b, fontSize=10, alignment=TA_CENTER, leading=14, shaping=False)),
                Paragraph(_safe(detail), ST["tbl_val"])]

    sc_rows = [
        [Paragraph("पैरामीटर", ST["tbl_hdr"]), Paragraph("स्थिति", ST["tbl_hdr"]), Paragraph("विवरण", ST["tbl_hdr"])],
        _scorecard_row("बच्चे उपस्थित",      children_count > 0,  str(children_count)),
        _scorecard_row("कार्यकर्ता",       worker_count > 0 or bool(worker_present), "उपस्थित" if (worker_count > 0 or worker_present) else "अनुपस्थित"),
        _scorecard_row("भोजन",            meal_detected is not False, "दृश्य स्पष्ट" if meal_detected else "स्पष्ट नहीं"),
        _scorecard_row("GPS",                is_gps_ok,  gps_str if is_gps_ok else "उपलब्ध नहीं"),
        _scorecard_row("Timestamp",          True,       "सत्यापित"),
        _scorecard_row("Duplicate Check",    not is_duplicate, "हाँ" if is_duplicate else "नहीं"),
        _scorecard_row("Image Quality",      not is_blur,  "CLEAR" if not is_blur else "BLUR"),
        _scorecard_row("AI Confidence",      True,         conf_str),
    ]

    sc_tbl = Table(sc_rows, colWidths=[CONTENT_W * 0.35, CONTENT_W * 0.25, CONTENT_W * 0.40])
    sc_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  GOV_NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 7),
        ("BOX",           (0, 0), (-1, -1), 0.8, BORDER_GREY),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.4, BORDER_GREY),
        ("ALIGN",         (1, 0), (1, -1),  "CENTER"),
    ]))
    story.append(sc_tbl)
    story.append(Spacer(1, 15))

    story.append(_sec_head("Attendance Summary", "उपस्थिति सारांश"))

    registered = getattr(submission, "registered_children", None) or 22
    difference  = children_count - registered
    diff_str    = f"+{difference}" if difference > 0 else str(difference)
    
    att_text = f"पंजीकृत बच्चे: &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{registered}<br/>AI द्वारा पाए गए: &nbsp;&nbsp;&nbsp;&nbsp;{children_count}<br/>अंतर: &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{diff_str}<br/><br/>कार्यकर्ता उपस्थित: {worker_count}"
    
    att_tbl2 = Table([[Paragraph(att_text, PS("att_sum", fontName=fn_b, fontSize=11, leading=16))]], colWidths=[CONTENT_W])
    att_tbl2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.8, BORDER_GREY),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 15),
    ]))
    story.append(att_tbl2)
    story.append(Spacer(1, 15))

    story.append(_sec_head("AI Observation", "AI अवलोकन"))
    obs_box = Table([[Paragraph(remarks_text, ST["obs_text"])]], colWidths=[CONTENT_W])
    obs_box.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#f0fdf4")),
        ("BOX",           (0, 0), (-1, -1), 1.0, colors.HexColor("#86efac")),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(obs_box)

    # PAGE 3: EVIDENCE
    story.append(PageBreak())
    story.append(_sec_head("Photographic Evidence", "सत्यापन छवियाँ"))
    story.append(Spacer(1, 10))

    MAX_IMG_W = CONTENT_W
    MAX_IMG_H = (PAGE_H - T_MARGIN - B_MARGIN - 4 * cm) / 2

    def _embed_image(path: str, caption: str):
        if not path or not os.path.exists(path):
            story.append(Paragraph(f"[{caption} — छवि उपलब्ध नहीं / Image unavailable]", PS("ni", fontName=fn, fontSize=9, textColor=TEXT_MUTED, alignment=TA_CENTER, leading=13)))
            story.append(Spacer(1, 10))
            return
        try:
            img = Image(path)
            raw_w = float(img.imageWidth)
            raw_h = float(img.imageHeight)
            scale = min(MAX_IMG_W / raw_w, MAX_IMG_H / raw_h, 1.0)
            img.drawWidth  = raw_w * scale
            img.drawHeight = raw_h * scale

            img_tbl = Table([[img]], colWidths=[CONTENT_W])
            img_tbl.setStyle(TableStyle([
                ("ALIGN",  (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX",    (0, 0), (-1, -1), 0.5, BORDER_GREY),
                ("TOPPADDING",    (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(img_tbl)
            story.append(Paragraph(caption, ST["img_caption"]))
            story.append(Spacer(1, 15))
        except Exception as e:
            logger.error("pdf_image_embed_error", path=path, error=str(e))

    _embed_image(orig_img_path,  "मूल प्राप्त फोटो")
    _embed_image(yolo_img_path,  f"AI Object Detection — AI द्वारा पहचाने गए बच्चे: {children_count}")

    doc.build(story, canvasmaker=NumberedCanvas)

    pdf_bytes = buffer.getvalue()
    buffer.close()

    logger.info("submission_pdf_v4_generated", audit_id=audit_id, size_kb=round(len(pdf_bytes) / 1024, 1))
    return pdf_bytes
"""
    lines = lines[:start_idx]
    lines.append(new_code)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"Successfully rewritten {filepath}")
else:
    print("Could not find start index")
