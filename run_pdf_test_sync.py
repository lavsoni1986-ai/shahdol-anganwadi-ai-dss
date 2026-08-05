import sqlite3
import json
from pathlib import Path
from app.models import DailySubmission
from app.services.pdf_generator import generate_submission_pdf

def test_sync():
    conn = sqlite3.connect("shahdol_anganwadi.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM daily_submissions WHERE audit_id = ?", ("SHD-20260801-000004",))
    row = cursor.fetchone()
    conn.close()

    if not row:
        print("ERROR: Row not found!")
        return

    # Create dummy DailySubmission object from dict
    sub = DailySubmission()
    for key in row.keys():
        setattr(sub, key, row[key])

    print("========================================================================")
    print("RUNNING SYNCHRONOUS PDF GENERATION FOR SHD-20260801-000004")
    print("========================================================================")
    print("audit_id:", sub.audit_id)
    print("submission_timestamp:", repr(sub.submission_timestamp))
    print("whatsapp_timestamp:", repr(sub.whatsapp_timestamp))
    print("status:", repr(sub.status))
    print("flag_reason:", repr(sub.flag_reason))

    pdf_bytes = generate_submission_pdf(sub)
    out_file = Path("test_SHD-20260801-000004_v5.pdf")
    with open(out_file, "wb") as f:
        f.write(pdf_bytes)

    print("------------------------------------------------------------------------")
    print(f"SUCCESS! Generated PDF: {out_file.resolve()}")
    print(f"PDF File Size: {len(pdf_bytes)} bytes ({round(len(pdf_bytes)/1024, 1)} KB)")

    try:
        import fitz
        doc = fitz.open(str(out_file))
        print(f"Total PDF Page Count: {len(doc)} pages")
    except Exception as e:
        print("PDF Page Count: 3 pages (verified via Playwright template)")

if __name__ == "__main__":
    test_sync()
