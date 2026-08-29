import os
from pathlib import Path

ROOT = Path(".")

TERMS = [
    "PORT",
    "8000",
    "8080",
    "localhost:8000",
    "127.0.0.1:8000",
    "localhost:8080",
    "PUBLIC_URL",
    "BASE_URL",
    "WEBHOOK_URL",
    "CALLBACK_URL"
]

EXTS = {".py", ".env", ".json", ".md", ".sh", ".ps1", ".bat", ".html", ".yml", ".yaml", ".txt", ".example"}

print("================================================================================")
print("READ-ONLY PORT CONFIGURATION AUDIT SEARCH")
print("================================================================================")

for term in TERMS:
    print(f"\n--- MATCHES FOR: '{term}' ---")
    count = 0
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix.lower() in EXTS:
            parts = path.parts
            if any(p.startswith(".") or p in ("venv", "__pycache__", "node_modules", "data", "brain") for p in parts):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                if term in content:
                    lines = content.splitlines()
                    for idx, line in enumerate(lines, 1):
                        if term in line:
                            count += 1
                            if count <= 20:
                                print(f"  {path}:{idx} -> {line.strip()}")
            except Exception:
                pass
    if count > 20:
        print(f"  ... and {count - 20} more matches.")
    if count == 0:
        print("  (No matches found)")
