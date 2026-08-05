import os
from pathlib import Path

root = Path(".")
TERMS = ["8080", "8000", "uvicorn", "PORT", "ngrok", "cloudflared"]

print("================================================================================")
print("STARTUP SCRIPT AND CONFIG FILE SEARCH")
print("================================================================================")

for p in root.glob("*"):
    if p.is_file():
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            for term in TERMS:
                if term in content:
                    lines = content.splitlines()
                    for idx, line in enumerate(lines, 1):
                        if term in line:
                            print(f"{p.name}:{idx} -> {line.strip()}")
        except Exception:
            pass

print("================================================================================")
