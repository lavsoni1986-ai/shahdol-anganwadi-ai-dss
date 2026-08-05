import sys
import subprocess
import os

html_path = "test_sample.html"
pdf_path = "test_sample.pdf"

with open(html_path, "w", encoding="utf-8") as f:
    f.write("<html><body><h1>Hello World Devanagari test: आंगनवाड़ी</h1></body></html>")

runner = os.path.abspath("app/services/render_pdf_runner.py")
cmd = [sys.executable, runner, os.path.abspath(html_path), os.path.abspath(pdf_path)]

print("Running command with stdin=DEVNULL:", cmd)
res = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
print("Return code:", res.returncode)
print("Stdout:", res.stdout)
print("Stderr:", res.stderr)
if os.path.exists(pdf_path):
    print("PDF File Size:", os.path.getsize(pdf_path))
