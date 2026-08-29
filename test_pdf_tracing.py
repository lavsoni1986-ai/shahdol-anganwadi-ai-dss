import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.services.pdf_generator import _run_playwright_in_process

print("=" * 60)
print("PDF PLAYWRIGHT CHECKPOINT TRACE TEST")
print("=" * 60)

test_html = """<!DOCTYPE html>
<html>
<head>
<style>
@font-face {
    font-family: 'NotoSansDevanagari';
    src: url('file:///d:/District%20Shahdol%20Anganwadi%20Digital%20Verification%20&%20Decision%20Support%20System/shahdol-anganwadi-mvp/app/static/fonts/NotoSansDevanagari-Regular.ttf') format('truetype');
}
body { font-family: 'NotoSansDevanagari', sans-serif; }
</style>
</head>
<body>
<h1>आंगनवाड़ी सत्यापन प्रतिवेदन</h1>
</body>
</html>"""

t0 = time.time()
try:
    pdf_bytes = _run_playwright_in_process(test_html)
    elapsed = round(time.time() - t0, 2)
    print(f"SUCCESS: Generated PDF ({len(pdf_bytes)} bytes) in {elapsed}s")
except Exception as e:
    elapsed = round(time.time() - t0, 2)
    print(f"ERROR after {elapsed}s: {e}")
