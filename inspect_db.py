import sqlite3

conn = sqlite3.connect('shahdol_anganwadi.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("--- RECENT SUBMISSIONS ---")
cur.execute("SELECT id, submission_id, audit_id, status, pdf_path, created_at, updated_at FROM daily_submissions ORDER BY id DESC LIMIT 15")
rows = cur.fetchall()
for r in rows:
    print(dict(r))

print("\n--- SEARCHING FOR 000013 / 000014 ---")
cur.execute("SELECT id, submission_id, audit_id, status, pdf_path, created_at, updated_at FROM daily_submissions WHERE audit_id LIKE '%000013%' OR audit_id LIKE '%000014%' OR submission_id LIKE '%000013%' OR submission_id LIKE '%000014%'")
rows = cur.fetchall()
for r in rows:
    print(dict(r))

conn.close()
