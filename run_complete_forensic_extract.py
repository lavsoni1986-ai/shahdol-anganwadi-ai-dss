import sqlite3
import json
import hashlib
from pathlib import Path

DB_PATH = "shahdol_anganwadi.db"

def sanitize(val):
    if val is None:
        return "None"
    s = str(val)
    return s.encode("ascii", errors="replace").decode("ascii")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 80)
print("COMPLETE FORENSIC DATABASE EXTRACT")
print("=" * 80)

# 1. Query daily_submissions for #000019 and #000020 and all recent
cur.execute("""
    SELECT submission_id, audit_id, worker_phone, worker_name, awc_id, center_name,
           status, is_authorized, rejection_reason, raw_media_id, local_media_path,
           media_sha256, created_at, updated_at, ack_sent, ack_sent_at, pdf_path,
           flag_reason, ai_score, ai_result_json
    FROM daily_submissions
    ORDER BY created_at DESC
    LIMIT 10
""")
submissions = cur.fetchall()

print("\n--- DAILY SUBMISSIONS ---")
for s in submissions:
    d = dict(s)
    print(f"Submission ID : {sanitize(d.get('submission_id'))}")
    print(f"Audit ID      : {sanitize(d.get('audit_id'))}")
    print(f"Worker Phone  : {sanitize(d.get('worker_phone'))} | Name: {sanitize(d.get('worker_name'))}")
    print(f"Center        : {sanitize(d.get('center_name'))} | AWC: {sanitize(d.get('awc_id'))}")
    print(f"Status        : {sanitize(d.get('status'))}")
    print(f"Media ID      : {sanitize(d.get('raw_media_id'))}")
    print(f"Local Path    : {sanitize(d.get('local_media_path'))}")
    print(f"SHA-256       : {sanitize(d.get('media_sha256'))}")
    print(f"PDF Path      : {sanitize(d.get('pdf_path'))}")
    print(f"Flag Reason   : {sanitize(d.get('flag_reason'))}")
    print(f"AI Score      : {sanitize(d.get('ai_score'))}")
    print(f"Created At    : {sanitize(d.get('created_at'))}")
    print(f"Updated At    : {sanitize(d.get('updated_at'))}")
    print(f"Ack Sent At   : {sanitize(d.get('ack_sent_at'))}")
    ai_json = sanitize(d.get('ai_result_json'))
    print(f"AI JSON Snippet: {ai_json[:300]}")
    print("-" * 60)

# 2. Query webhook_logs
cur.execute("""
    SELECT id, received_at, source_ip, processing_error, payload
    FROM webhook_logs
    ORDER BY id DESC
    LIMIT 20
""")
webhook_logs = cur.fetchall()

print("\n--- WEBHOOK LOGS (LATEST 20) ---")
for wl in webhook_logs:
    d = dict(wl)
    payload_str = sanitize(d.get('payload'))
    print(f"Log ID        : {sanitize(d.get('id'))}")
    print(f"Received At   : {sanitize(d.get('received_at'))}")
    print(f"Source IP     : {sanitize(d.get('source_ip'))}")
    print(f"Proc Error    : {sanitize(d.get('processing_error'))}")
    print(f"Payload Snippet: {payload_str[:200]}...")
    print("-" * 60)

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
            print(f"File Name: {sanitize(f.name)}")
            print(f"  Abs Path: {sanitize(f.absolute())}")
            print(f"  Size    : {stat.st_size} bytes")
            print(f"  Created : {stat.st_ctime}")
            print(f"  Modified: {stat.st_mtime}")
            print(f"  SHA-256 : {sha256}")
            print("-" * 60)

