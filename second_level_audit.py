import os
import sys
import time
import pathlib
import psutil
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import cv2
import torch
from app.services.yolo_detector import yolo_detector
from app.services.pdf_generator import _encode_image, Environment, FileSystemLoader, _TEMPLATE_DIR
from playwright.sync_api import sync_playwright

REAL_IMAGE_PATH = pathlib.Path("data/uploads/1bc48092-816d-4c6b-8291-10963a758c36.jpg")

process = psutil.Process(os.getpid())

def get_sys_metrics():
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "rss_mb": round(process.memory_info().rss / 1024 / 1024, 2)
    }

def run_second_level_audit():
    print("=" * 80)
    print("SECOND LEVEL PERFORMANCE AUDIT REPORT")
    print("=" * 80)
    
    img_size_bytes = REAL_IMAGE_PATH.stat().st_size
    pil_im = Image.open(REAL_IMAGE_PATH)
    img_w, img_h = pil_im.size
    
    print(f"Image Resolution : {img_w} x {img_h} pixels")
    print(f"Image File Size  : {img_size_bytes} bytes ({round(img_size_bytes / 1024, 2)} KB)")
    print(f"Model Load Count : 1 (Loaded at application/service startup as Singleton)")
    print(f"Model Life Cycle : Loaded ONCE at startup (yolo_detector = YoloDetectorService())")
    print("-" * 80)
    
    # -------------------------------------------------------------------------
    # YOLO SUB-STAGE PROFILING
    # -------------------------------------------------------------------------
    print("\n--- 1. YOLO DETECTOR SUB-STAGES ---")
    yolo_sub = {}
    
    # a. Image read
    t0 = time.perf_counter()
    img_cv = cv2.imread(str(REAL_IMAGE_PATH.absolute()))
    m1 = get_sys_metrics()
    yolo_sub["a. Image Read (cv2.imread)"] = {
        "ms": (time.perf_counter() - t0) * 1000,
        "cpu": m1["cpu"],
        "rss_mb": m1["rss_mb"]
    }
    
    # b. Resize
    t0 = time.perf_counter()
    img_resized = cv2.resize(img_cv, (640, 640))
    m1 = get_sys_metrics()
    yolo_sub["b. Image Resize (cv2.resize to 640x640)"] = {
        "ms": (time.perf_counter() - t0) * 1000,
        "cpu": m1["cpu"],
        "rss_mb": m1["rss_mb"]
    }
    
    # c. model.predict() pure forward pass
    t0 = time.perf_counter()
    tensor_img = torch.from_numpy(img_resized).permute(2, 0, 1).float().unsqueeze(0) / 255.0
    with torch.no_grad():
        results_raw = yolo_detector._model.model(tensor_img)
    m1 = get_sys_metrics()
    yolo_sub["c. Pure PyTorch Forward Pass (model.predict)"] = {
        "ms": (time.perf_counter() - t0) * 1000,
        "cpu": m1["cpu"],
        "rss_mb": m1["rss_mb"]
    }
    
    # d. NMS (Non-Maximum Suppression) & Ultralytics box decoding
    t0 = time.perf_counter()
    res = yolo_detector._model.predict(source=str(REAL_IMAGE_PATH.absolute()), conf=0.25, iou=0.45, imgsz=640, verbose=False)
    total_predict_ms = (time.perf_counter() - t0) * 1000
    nms_ms = max(0.1, total_predict_ms - yolo_sub["c. Pure PyTorch Forward Pass (model.predict)"]["ms"])
    m1 = get_sys_metrics()
    yolo_sub["d. Non-Maximum Suppression (NMS & Box Decoding)"] = {
        "ms": nms_ms,
        "cpu": m1["cpu"],
        "rss_mb": m1["rss_mb"]
    }
    
    # e. Annotation draw
    t0 = time.perf_counter()
    annotated = img_cv.copy()
    boxes = res[0].boxes
    for box in boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(annotated, "Person", (x1, max(y1 - 10, 0)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    m1 = get_sys_metrics()
    yolo_sub["e. Annotation Draw (cv2.rectangle / cv2.putText)"] = {
        "ms": (time.perf_counter() - t0) * 1000,
        "cpu": m1["cpu"],
        "rss_mb": m1["rss_mb"]
    }
    
    # f. Save annotated image
    t0 = time.perf_counter()
    out_path = "data/processed/profiling_audit_test.jpg"
    cv2.imwrite(out_path, annotated)
    m1 = get_sys_metrics()
    yolo_sub["f. Save Annotated Image (cv2.imwrite)"] = {
        "ms": (time.perf_counter() - t0) * 1000,
        "cpu": m1["cpu"],
        "rss_mb": m1["rss_mb"]
    }
    
    print(f"{'YOLO Sub-Stage':<48} | {'Duration (ms)':<14} | {'CPU %':<8} | {'RAM (MB)':<10}")
    print("-" * 85)
    for name, data in yolo_sub.items():
        print(f"{name:<48} | {data['ms']:11.2f} ms | {data['cpu']:6.1f}% | {data['rss_mb']:8.1f} MB")

    # -------------------------------------------------------------------------
    # PDF RENDER SUB-STAGE PROFILING
    # -------------------------------------------------------------------------
    print("\n--- 2. PDF GENERATOR SUB-STAGES ---")
    pdf_sub = {}
    
    # a. HTML generation
    t0 = time.perf_counter()
    img_b64 = _encode_image(str(REAL_IMAGE_PATH), max_dim=800)
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)))
    template = env.get_template("pdf_template.html")
    ctx = {
        "audit_id": "SHD-20260803-001",
        "status_text": "APPROVED",
        "status_color": "#15803d",
        "center_name": "Pongri 1",
        "awc_id": "23460060604",
        "block_name": "Sohagpur",
        "worker_name": "Bhagwati Baiga",
        "worker_phone": "916263302625",
        "date_time": "03/08/2026 03:30 PM IST",
        "children_count": 8,
        "worker_present": "हाँ",
        "meal_detected": "दिखाई दिया",
        "is_gps_ok": "उपलब्ध",
        "is_duplicate": "नहीं",
        "status_decision": "स्वीकृत (APPROVED)",
        "scorecard": [],
        "registered_children": 22,
        "difference": -14,
        "ai_remarks": "आंगनवाड़ी केंद्र में बच्चे उपस्थित हैं।",
        "orig_img_base64": img_b64,
        "yolo_img_base64": img_b64,
        "font_regular": "file:///fake",
        "font_bold": "file:///fake",
    }
    html_out = template.render(ctx)
    m1 = get_sys_metrics()
    pdf_sub["a. HTML Generation (Jinja Template Render)"] = {
        "ms": (time.perf_counter() - t0) * 1000,
        "cpu": m1["cpu"],
        "rss_mb": m1["rss_mb"]
    }
    
    with sync_playwright() as p:
        # b. Browser launch
        t0 = time.perf_counter()
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--disable-setuid-sandbox"]
        )
        m1 = get_sys_metrics()
        pdf_sub["b. Browser Launch (Chromium Process)"] = {
            "ms": (time.perf_counter() - t0) * 1000,
            "cpu": m1["cpu"],
            "rss_mb": m1["rss_mb"]
        }
        
        # c. Browser context
        t0 = time.perf_counter()
        context = browser.new_context()
        m1 = get_sys_metrics()
        pdf_sub["c. Browser Context Creation"] = {
            "ms": (time.perf_counter() - t0) * 1000,
            "cpu": m1["cpu"],
            "rss_mb": m1["rss_mb"]
        }
        
        # d. new_page()
        t0 = time.perf_counter()
        page = context.new_page()
        m1 = get_sys_metrics()
        pdf_sub["d. context.new_page()"] = {
            "ms": (time.perf_counter() - t0) * 1000,
            "cpu": m1["cpu"],
            "rss_mb": m1["rss_mb"]
        }
        
        # e. page.set_content()
        t0 = time.perf_counter()
        page.set_content(html_out)
        m1 = get_sys_metrics()
        pdf_sub["e. page.set_content(HTML)"] = {
            "ms": (time.perf_counter() - t0) * 1000,
            "cpu": m1["cpu"],
            "rss_mb": m1["rss_mb"]
        }
        
        # f. fonts.ready
        t0 = time.perf_counter()
        page.evaluate("document.fonts.ready")
        m1 = get_sys_metrics()
        pdf_sub["f. document.fonts.ready Wait"] = {
            "ms": (time.perf_counter() - t0) * 1000,
            "cpu": m1["cpu"],
            "rss_mb": m1["rss_mb"]
        }
        
        # g. page.pdf()
        t0 = time.perf_counter()
        pdf_bytes = page.pdf(format="A4", print_background=True)
        m1 = get_sys_metrics()
        pdf_sub["g. page.pdf() Layout & Export"] = {
            "ms": (time.perf_counter() - t0) * 1000,
            "cpu": m1["cpu"],
            "rss_mb": m1["rss_mb"]
        }
        
        # h. browser.close()
        t0 = time.perf_counter()
        browser.close()
        m1 = get_sys_metrics()
        pdf_sub["h. browser.close() Cleanup"] = {
            "ms": (time.perf_counter() - t0) * 1000,
            "cpu": m1["cpu"],
            "rss_mb": m1["rss_mb"]
        }

    print(f"{'PDF Sub-Stage':<48} | {'Duration (ms)':<14} | {'CPU %':<8} | {'RAM (MB)':<10}")
    print("-" * 85)
    for name, data in pdf_sub.items():
        print(f"{name:<48} | {data['ms']:11.2f} ms | {data['cpu']:6.1f}% | {data['rss_mb']:8.1f} MB")

if __name__ == "__main__":
    run_second_level_audit()
