from pathlib import Path

app_dir = Path("app")

print("--- SEARCH FOR np.random.randint ---")
for p in app_dir.rglob("*.py"):
    content = p.read_text(encoding="utf-8", errors="ignore")
    if "np.random.randint" in content:
        for idx, line in enumerate(content.splitlines(), 1):
            if "np.random.randint" in line:
                print(f"  {p}:{idx} -> {line.strip()}")

print("\n--- SEARCH FOR _download_or_mock_image ---")
for p in app_dir.rglob("*.py"):
    content = p.read_text(encoding="utf-8", errors="ignore")
    if "_download_or_mock_image" in content:
        for idx, line in enumerate(content.splitlines(), 1):
            if "_download_or_mock_image" in line:
                print(f"  {p}:{idx} -> {line.strip()}")

print("\n--- SEARCH FOR .limit(20) ---")
for p in app_dir.rglob("*.py"):
    content = p.read_text(encoding="utf-8", errors="ignore")
    if ".limit(20)" in content:
        for idx, line in enumerate(content.splitlines(), 1):
            if ".limit(20)" in line:
                print(f"  {p}:{idx} -> {line.strip()}")
