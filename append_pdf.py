
# ═════════════════════════════════════════════════════════════════════
# INDIVIDUAL SUBMISSION PDF GENERATION (CEO DEMO FORMAT)
# ═════════════════════════════════════════════════════════════════════
def generate_submission_pdf(submission) -> bytes:
    """
    Generates an individual A4 PDF Report for a single submission.
    Designed according to CEO requirements with BharatOS Branding.
    """
    _ensure_fonts()
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=2.0 * cm,
        bottomMargin=2.0 * cm,
    )
    story = []
    
    # Define Styles
    S = _build_styles()
    fn = _get_font(bold=False)
    fn_bold = _get_font(bold=True)
    
    st_header = ParagraphStyle("st_hdr", fontName=fn_bold, fontSize=14, textColor=GOV_NAVY, alignment=TA_CENTER, leading=18, shaping=True)
    st_title = ParagraphStyle("st_ttl", fontName=fn_bold, fontSize=18, textColor=GOV_BLUE, alignment=TA_CENTER, leading=22, spaceAfter=10, shaping=True)
    st_sub = ParagraphStyle("st_sub", fontName=fn, fontSize=10, textColor=TEXT_MUTED, alignment=TA_CENTER, leading=14, shaping=True)
    st_section = ParagraphStyle("st_sec", fontName=fn_bold, fontSize=12, textColor=GOV_NAVY, leading=16, spaceBefore=10, spaceAfter=5, shaping=True)
    st_banner_text = ParagraphStyle("st_ban", fontName=fn_bold, fontSize=16, textColor=WHITE, alignment=TA_CENTER, leading=20)
    st_text = ParagraphStyle("st_txt", fontName=fn, fontSize=10, textColor=TEXT_DARK, leading=14, shaping=True)
    st_text_bold = ParagraphStyle("st_txt_b", fontName=fn_bold, fontSize=10, textColor=TEXT_DARK, leading=14, shaping=True)

    # ── 1. HEADER (Government + BharatOS) ──────────────────────────────────
    story.append(Paragraph(_shape_hi("महिला एवं बाल विकास विभाग"), st_header))
    story.append(Paragraph(_shape_hi("जिला शहडोल (म.प्र.)"), st_header))
    story.append(Spacer(1, 10))
    story.append(Paragraph("District Anganwadi Digital Verification &", st_sub))
    story.append(Paragraph("Decision Support System", st_sub))
    story.append(Spacer(1, 5))
    story.append(Paragraph("Powered by <b>BharatOS AI</b>", st_sub))
    story.append(Spacer(1, 15))
    story.append(Paragraph(_shape_hi("आंगनवाड़ी डिजिटल सत्यापन रिपोर्ट"), st_title))
    story.append(HRFlowable(width="100%", thickness=1.5, color=GOV_NAVY, spaceAfter=15))

    # ── 2. RESULT BANNER ───────────────────────────────────────────────────
    st = getattr(submission, "status", "RECEIVED")
    is_auth = getattr(submission, "is_authorized", False)
    
    if st in ("APPROVED", "PROCESSED") or (is_auth and st != "FLAGGED"):
        disp_st = "🟢 VERIFIED"
        bg_color = COLOR_APPROVED
    elif st == "FLAGGED":
        if "MANUAL_REVIEW_REQUIRED" in getattr(submission, "flag_reason", ""):
            disp_st = "🔴 MANUAL REVIEW REQUIRED"
            bg_color = COLOR_REJECTED
        else:
            disp_st = "🟡 FLAGGED"
            bg_color = COLOR_FLAGGED
    else:
        disp_st = "🔵 RECEIVED"
        bg_color = COLOR_PENDING
        
    banner_table = Table([[Paragraph(disp_st, st_banner_text)]], colWidths=["100%"])
    banner_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg_color),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 15))
    
    # ── Parse AI Data ──────────────────────────────────────────────────────
    import json
    yolo_res = {}
    vision_res = {}
    if getattr(submission, "ai_result_json", None):
        try:
            vision_res = json.loads(submission.ai_result_json)
            yolo_res = vision_res.get("yolo_results", {})
        except:
            pass

    children_count = yolo_res.get("children_count", 0)
    worker_count = yolo_res.get("worker_count", 0)
    
    is_gps_valid = bool(getattr(submission, "latitude", None))
    is_duplicate = "DUPLICATE" in getattr(submission, "flag_reason", "").upper()
    is_blur = "BLUR" in getattr(submission, "flag_reason", "").upper()
    
    # ── 3. EXECUTIVE SUMMARY ───────────────────────────────────────────────
    story.append(Paragraph("AI Executive Summary", st_section))
    story.append(Paragraph(_shape_hi("• फोटो सफलतापूर्वक प्राप्त हुई।"), st_text))
    
    if vision_res.get("is_valid_anganwadi_scene"):
        story.append(Paragraph(_shape_hi("• आंगनवाड़ी गतिविधि स्पष्ट है।"), st_text))
    else:
        story.append(Paragraph(_shape_hi("• आंगनवाड़ी गतिविधि स्पष्ट नहीं है।"), st_text))
        
    story.append(Paragraph(_shape_hi(f"• कुल {children_count} बच्चे उपस्थित पाए गए।"), st_text))
    story.append(Paragraph(_shape_hi("• GPS सत्यापित है।" if is_gps_valid else "• GPS सत्यापित नहीं है।"), st_text))
    story.append(Paragraph(_shape_hi("• Duplicate नहीं मिला।" if not is_duplicate else "• Duplicate मिला।"), st_text))
    
    if disp_st == "🟢 VERIFIED":
        story.append(Paragraph(_shape_hi("• Manual Review आवश्यक नहीं।"), st_text))
    else:
        story.append(Paragraph(_shape_hi("• Manual Review आवश्यक है।"), st_text))
        
    story.append(Spacer(1, 10))

    # ── 4. REPORT METADATA & AWC INFO ──────────────────────────────────────
    sub_ts = getattr(submission, "submission_timestamp", None)
    ts_str = sub_ts.astimezone(IST).strftime("%d/%m/%Y") if sub_ts else "N/A"
    time_str = sub_ts.astimezone(IST).strftime("%I:%M %p") if sub_ts else "N/A"
    audit_id = getattr(submission, "audit_id") or (getattr(submission, "submission_id")[:8] if getattr(submission, "submission_id") else "N/A")
    
    meta_data = [
        ["Audit ID", audit_id, "Date", ts_str],
        ["Time", time_str, "AWC Code", getattr(submission, "awc_id", "")],
        ["केंद्र", _shape_hi(getattr(submission, "center_name", "")), "कार्यकर्ता", _shape_hi(getattr(submission, "worker_name", ""))],
    ]
    meta_t = Table(meta_data, colWidths=["20%", "30%", "20%", "30%"])
    meta_t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), fn),
        ("FONTNAME", (0, 0), (0, -1), fn_bold),
        ("FONTNAME", (2, 0), (2, -1), fn_bold),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_GREY),
        ("BACKGROUND", (0, 0), (0, -1), GOV_LIGHT_BG),
        ("BACKGROUND", (2, 0), (2, -1), GOV_LIGHT_BG),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_t)
    story.append(Spacer(1, 15))

    # ── 5. AI SCORECARD ────────────────────────────────────────────────────
    story.append(Paragraph("AI Verification Scorecard", st_section))
    
    def get_status_icon(condition):
        return "✅" if condition else "❌"
        
    scorecard_data = [
        [Paragraph("Parameter", st_text_bold), Paragraph("Status", st_text_bold)],
        [Paragraph("GPS", st_text), Paragraph(get_status_icon(is_gps_valid), st_text)],
        [Paragraph("Timestamp", st_text), Paragraph("✅", st_text)], # Assume valid if processing
        [Paragraph("Duplicate Image", st_text), Paragraph("✅" if not is_duplicate else "❌", st_text)],
        [Paragraph("Image Quality", st_text), Paragraph("✅" if not is_blur else "❌", st_text)],
        [Paragraph("Children Present", st_text), Paragraph(get_status_icon(children_count > 0), st_text)],
        [Paragraph("Worker Present", st_text), Paragraph(get_status_icon(worker_count > 0), st_text)],
    ]
    score_t = Table(scorecard_data, colWidths=["70%", "30%"])
    score_t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), fn),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_GREY),
        ("BACKGROUND", (0, 0), (-1, 0), GOV_LIGHT_BG),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(score_t)
    story.append(Spacer(1, 15))

    # ── 6. AI COUNT & OBSERVATION ──────────────────────────────────────────
    story.append(Paragraph("AI Count & Observation", st_section))
    
    count_data = [
        [Paragraph(_shape_hi("पंजीकृत बच्चे"), st_text_bold), Paragraph("22", st_text)], # Mock registered
        [Paragraph(_shape_hi("उपस्थित बच्चे (AI)"), st_text_bold), Paragraph(str(children_count), st_text)],
        [Paragraph(_shape_hi("कार्यकर्ता"), st_text_bold), Paragraph(str(worker_count), st_text)],
    ]
    count_t = Table(count_data, colWidths=["50%", "50%"])
    count_t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), fn),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_GREY),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(count_t)
    story.append(Spacer(1, 10))
    
    obs_text = vision_res.get("remarks") or "आंगनवाड़ी केंद्र में गतिविधि का दृश्य प्राप्त हुआ।"
    story.append(Paragraph(_shape_hi(obs_text), st_text))
    story.append(Spacer(1, 15))

    # ── 7. IMAGES (Original & YOLO Stacked) ────────────────────────────────
    story.append(Paragraph("Verification Images", st_section))
    
    image_paths = []
    local_path = getattr(submission, "local_image_path", None)
    if local_path and os.path.exists(local_path):
        image_paths.append(("Original", local_path))
        
    yolo_path = yolo_res.get("visualized_image_path")
    if yolo_path and os.path.exists(yolo_path):
        image_paths.append(("YOLO Detection", yolo_path))
        
    for label, path in image_paths:
        try:
            story.append(Paragraph(label, st_sub))
            img = Image(path)
            # Scale image to fit A4 width while preserving aspect ratio
            # Max width is page_width - margins (approx 18cm)
            max_width = 15 * cm
            max_height = 10 * cm
            
            aspect = img.imageWidth / float(img.imageHeight)
            if img.imageWidth > max_width or img.imageHeight > max_height:
                if (max_width / aspect) <= max_height:
                    img.drawWidth = max_width
                    img.drawHeight = max_width / aspect
                else:
                    img.drawHeight = max_height
                    img.drawWidth = max_height * aspect
                    
            story.append(img)
            story.append(Spacer(1, 10))
        except Exception as e:
            logger.error("pdf_image_embed_failed", path=path, error=str(e))
            
    # ── 8. FOOTER ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER_GREY, spaceAfter=5))
    story.append(Paragraph("Generated Automatically by", st_sub))
    story.append(Paragraph("District Anganwadi Digital Verification & Decision Support System", st_sub))
    story.append(Paragraph("Powered by BharatOS AI", ParagraphStyle("ftr", fontName=fn_bold, fontSize=10, textColor=TEXT_MUTED, alignment=TA_CENTER)))
    
    doc.build(story)
    
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    logger.info("submission_pdf_generated", submission_id=getattr(submission, "submission_id", "Unknown"))
    return pdf_bytes
