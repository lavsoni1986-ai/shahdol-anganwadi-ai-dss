import sqlite3
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

cur.execute("""
    SELECT submission_id, audit_id, worker_phone, worker_name, awc_id, center_name,
           status, is_authorized, rejection_reason, raw_media_id, local_media_path,
           media_sha256, created_at, updated_at, ack_sent, ack_sent_at, pdf_path,
           flag_reason, ai_score
    FROM daily_submissions
    ORDER BY created_at DESC
    LIMIT 10
""")
submissions = cur.fetchall()

print("=" * 80)
print("DAILY SUBMISSIONS LOG")
print("=" * 80)
for s in submissions:
    d = dict(s)
    print(f"Submission ID : {sanitize(d.get('submission_id'))}")
    print(f"Audit ID      : {sanitize(d.get('audit_id'))}")
    print(f"Status        : {sanitize(d.get('status'))}")
    print(f"Media ID      : {sanitize(d.get('raw_media_id'))}")
    print(f"Local Path    : {sanitize(d.get('local_media_path'))}")
    print(f"SHA-256       : {sanitize(d.get('media_sha256'))}")
    print(f"PDF Path      : {sanitize(d.get('pdf_path'))}")
    print(f"Flag Reason   : {sanitize(d.get('flag_reason'))}")
    print(f"Created At    : {sanitize(d.get('created_at'))}")
    print(f"Updated At    : {sanitize(d.get('updated_at'))}")
    print("-" * 60)

cur.execute("""
    SELECT id, received_at, source_ip, processing_error
    FROM webhook_logs
    ORDER BY id DESC
    LIMIT 15
""")
webhook_logs = cur.fetchall()

print("\n=" * 80)
print("WEBHOOK LOGS")
print("=" * 80)
for wl in webhook_logs:
    d = dict(wl)
    print(f"Log ID      : {sanitize(d.get('id'))}")
    print(f"Received At : {sanitize(d.get('received_at'))}")
    print(f"Source IP   : {sanitize(d.get('source_ip'))}")
    print(f"Proc Error  : {sanitize(d.get('processing_error'))}")
    print("-" * 60)

conn.close()
