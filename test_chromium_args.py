import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from playwright.sync_api import sync_playwright

print("=" * 60)
print("TESTING CHROMIUM LAUNCH ARGS (--no-sandbox --disable-gpu)")
print("=" * 60)

t0 = time.time()
with sync_playwright() as p:
    print(f"[{int((time.time()-t0)*1000)} ms] Launching chromium with args...")
    browser = p.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
    )
    print(f"[{int((time.time()-t0)*1000)} ms] Browser launched!")
    context = browser.new_context()
    print(f"[{int((time.time()-t0)*1000)} ms] Context created!")
    page = context.new_page()
    print(f"[{int((time.time()-t0)*1000)} ms] Page created!")
    page.set_content("<html><body><h1>Test PDF</h1></body></html>")
    print(f"[{int((time.time()-t0)*1000)} ms] Content set!")
    pdf_bytes = page.pdf(format="A4")
    print(f"[{int((time.time()-t0)*1000)} ms] PDF rendered ({len(pdf_bytes)} bytes)!")
    browser.close()
    print(f"[{int((time.time()-t0)*1000)} ms] Done!")
