import sys
import os
import subprocess
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

html_path = Path("temp_test.html")
pdf_path = Path("temp_test.pdf")

html_path.write_text("<html><body><h1>Digital Verification Report Test</h1></body></html>", encoding="utf-8")

runner_script = Path("app/services/render_pdf_runner.py").absolute()
python_bin = sys.executable

cmd = [python_bin, str(runner_script), str(html_path.absolute()), str(pdf_path.absolute())]

print("=" * 60)
print("RUNNING SUBPROCESS DIRECT TEST")
print("=" * 60)
print("CMD:", cmd)

t0 = time.time()
res = subprocess.run(cmd, capture_output=True, text=True)
elapsed = round(time.time() - t0, 2)

print(f"Elapsed: {elapsed}s")
print("Exit Code:", res.returncode)
print("STDOUT:\n", res.stdout)
print("STDERR:\n", res.stderr)

if pdf_path.exists():
    print(f"PDF Generated! Size: {pdf_path.stat().st_size} bytes")
    pdf_path.unlink(missing_ok=True)

html_path.unlink(missing_ok=True)
