import os
import re
from pathlib import Path

ROOT = Path("d:/District Shahdol Anganwadi Digital Verification & Decision Support System/shahdol-anganwadi-mvp")

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

results = {term: [] for term in TERMS}

for p in ROOT.rglob("*"):
    if p.is_file() and not any(part.startswith(".") or part in ("venv", "__pycache__", "node_modules", "data") for part in p.parts):
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            for term in TERMS:
                if term in content:
                    lines = content.splitlines()
                    for idx, line in enumerate(lines, 1):
                        if term in line:
                            rel = p.relative_to(ROOT)
                            results[term].append(f"{rel}:{idx} -> {line.strip()}")
        except Exception as e:
            pass

print("=" * 80)
print("PORT SEARCH RESULTS")
print("=" * 80)
for term, matches in results.items():
    print(f"\n--- TERM: '{term}' ({len(matches)} matches) ---")
    for m in matches[:30]:
        print(f"  {m}")
    if len(matches) > 30:
        print(f"  ... and {len(matches) - 30} more matches.")
print("=" * 80)
