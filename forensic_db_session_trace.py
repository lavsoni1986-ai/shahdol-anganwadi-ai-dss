import re
from pathlib import Path

app_dir = Path("app")

print("=" * 80)
print("FORENSIC SEARCH: DB SESSIONS AND TRANSACTIONS")
print("=" * 80)

for p in sorted(app_dir.rglob("*.py")):
    content = p.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()
    matches = []
    for idx, line in enumerate(lines, 1):
        if any(term in line for term in ["AsyncSessionLocal", "get_db", "async_session", "session", "db.commit", "db.rollback", "WebhookLog"]):
            matches.append((idx, line.strip()))
    if matches:
        print(f"\n--- {p} ({len(matches)} matches) ---")
        for idx, line in matches[:40]:
            print(f"  Line {idx:4d}: {line}")
        if len(matches) > 40:
            print(f"  ... and {len(matches) - 40} more matches.")
