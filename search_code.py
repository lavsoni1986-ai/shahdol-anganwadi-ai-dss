import os
from pathlib import Path

target_files = [
    ".env",
    ".env.example",
    "app/config.py",
    "app/main.py",
    "app/services/whatsapp.py",
    "app/services/pdf_generator.py",
    "run.py",
    "main.py",
]

# Add any python files in app/
app_dir = Path("app")
if app_dir.exists():
    for p in app_dir.rglob("*.py"):
        target_files.append(str(p))

# Unique target files
target_files = sorted(list(set(target_files)))

TERMS = ["PORT", "8000", "8080", "PUBLIC_URL", "BASE_URL", "WEBHOOK_URL", "CALLBACK_URL"]

print("================================================================================")
print("TARGETED CODE SEARCH FOR PORT CONFIGURATIONS")
print("================================================================================")

for file_path in target_files:
    p = Path(file_path)
    if p.exists() and p.is_file():
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            matches = []
            lines = content.splitlines()
            for idx, line in enumerate(lines, 1):
                if any(term in line for term in TERMS):
                    matches.append(f"Line {idx:3d}: {line.strip()}")
            if matches:
                print(f"\n--- FILE: {file_path} ---")
                for m in matches:
                    print(f"  {m}")
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

print("================================================================================")
