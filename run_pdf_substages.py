import os
import sys
import time
import pathlib
import psutil

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from app.services.pdf_generator import _encode_image, Environment, FileSystemLoader, _TEMPLATE_DIR
from playwright.sync_api import sync_playwright

REAL_IMAGE_PATH = pathlib.Path("data/uploads/1bc48092-816d-4c6b-8291-10963a758c36.jpg")
process = psutil.Process(os.getpid())

def get_sys_metrics():
    return {
        "cpu": psutil.cpu_percent(interval=None),
        "rss_mb": round(process.memory_info().rss / 1024 / 1024, 2)
    }

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

print("\n" + "=" * 85)
print("PDF SUB-STAGES PROFILING RESULT")
print("=" * 85)
print(f"{'PDF Sub-Stage':<48} | {'Duration (ms)':<14} | {'CPU %':<8} | {'RAM (MB)':<10}")
print("-" * 85)
for name, data in pdf_sub.items():
    print(f"{name:<48} | {data['ms']:11.2f} ms | {data['cpu']:6.1f}% | {data['rss_mb']:8.1f} MB")
print("-" * 85)
