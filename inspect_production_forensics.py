import sqlite3
import json
import hashlib
from pathlib import Path

DB_PATH = "shahdol_anganwadi.db"

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 80)
print("FORENSIC DATABASE QUERY — SUBMISSIONS AND WEBHOOK LOGS")
print("=" * 80)

# 1. Query daily_submissions
cur.execute("""
    SELECT submission_id, audit_id, worker_phone, status, verification_status,
           raw_media_id, local_media_path, media_sha256, created_at, updated_at,
           pdf_path, flag_reason, ai_result_json
    FROM daily_submissions
    ORDER BY created_at DESC
    LIMIT 10
""")
submissions = cur.fetchall()

print("\n--- DAILY SUBMISSIONS (LATEST 10) ---")
for s in submissions:
    d = dict(s)
    print(f"Submission ID : {d.get('submission_id')}")
    print(f"Audit ID      : {d.get('audit_id')}")
    print(f"Status        : {d.get('status')}")
    print(f"Media ID      : {d.get('raw_media_id')}")
    print(f"Local Path    : {d.get('local_media_path')}")
    print(f"SHA-256       : {d.get('media_sha256')}")
    print(f"PDF Path      : {d.get('pdf_path')}")
    print(f"Flag Reason   : {d.get('flag_reason')}")
    print(f"Created At    : {d.get('created_at')}")
    print(f"Updated At    : {d.get('updated_at')}")
    ai_json = d.get('ai_result_json') or ""
    print(f"AI JSON Snippet: {ai_json[:250] if ai_json else 'None'}")
    print("-" * 50)

# 2. Query webhook_logs
cur.execute("""
    SELECT id, received_at, source_ip, processing_error, payload
    FROM webhook_logs
    ORDER BY id DESC
    LIMIT 15
""")
webhook_logs = cur.fetchall()

print("\n--- WEBHOOK LOGS (LATEST 15) ---")
for wl in webhook_logs:
    d = dict(wl)
    payload_str = d.get('payload') or ""
    print(f"Log ID        : {d.get('id')}")
    print(f"Received At   : {d.get('received_at')}")
    print(f"Source IP     : {d.get('source_ip')}")
    print(f"Proc Error    : {d.get('processing_error')}")
    print(f"Payload Snippet: {payload_str[:150]}...")
    print("-" * 50)

conn.close()

print("\n=" * 80)
print("DATA INTEGRITY FILE SYSTEM CHECK (data/uploads/)")
print("=" * 80)

uploads_dir = Path("data/uploads")
if uploads_dir.exists():
    files = sorted(list(uploads_dir.glob("*")), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        if f.is_file():
            stat = f.stat()
            content = f.read_bytes()
            sha256 = hashlib.sha256(content).hexdigest()
            print(f"File Name: {f.name}")
            print(f"  Abs Path: {f.absolute()}")
            print(f"  Size    : {stat.st_size} bytes")
            print(f"  Created : {stat.st_ctime}")
            print(f"  Modified: {stat.st_mtime}")
            print(f"  SHA-256 : {sha256}")
            print("-" * 50)

