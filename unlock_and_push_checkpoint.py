import os
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()
LOCK_FILE = PROJECT_DIR / ".git" / "index.lock"

if LOCK_FILE.exists():
    try:
        os.remove(LOCK_FILE)
        print(f"Removed stale lock file: {LOCK_FILE}")
    except Exception as e:
        print(f"Lock file remove error: {e}")

def run_git(cmd):
    print(f"\n[RUN]: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(PROJECT_DIR), capture_output=True, text=True)
    if res.stdout:
        print(f"STDOUT: {res.stdout.strip()}")
    if res.stderr:
        print(f"STDERR: {res.stderr.strip()}")
    print(f"EXIT CODE: {res.returncode}")

run_git(["git", "status"])
run_git(["git", "add", "."])
run_git(["git", "commit", "-m", "Freeze after CEO demo - Stable WhatsApp/PDF pipeline"])
run_git(["git", "push"])
