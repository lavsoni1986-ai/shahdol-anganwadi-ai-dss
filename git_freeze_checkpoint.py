import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()

def run_git_cmd(cmd_list):
    cmd_str = " ".join(cmd_list)
    print(f"\n[RUNNING]: {cmd_str}", flush=True)
    res = subprocess.run(cmd_list, cwd=str(PROJECT_DIR), capture_output=True, text=True)
    if res.stdout:
        print(f"[STDOUT]:\n{res.stdout.strip()}", flush=True)
    if res.stderr:
        print(f"[STDERR]:\n{res.stderr.strip()}", flush=True)
    print(f"[EXIT CODE]: {res.returncode}", flush=True)
    return res.returncode

def main():
    print("=" * 80, flush=True)
    print("GIT PROJECT FREEZE CHECKPOINT", flush=True)
    print("=" * 80, flush=True)

    # 1. Git Status
    run_git_cmd(["git", "status"])

    # 2. Git Add
    run_git_cmd(["git", "add", "."])

    # 3. Git Commit
    commit_msg = "Freeze after CEO demo - Stable WhatsApp/PDF pipeline"
    run_git_cmd(["git", "commit", "-m", commit_msg])

    # 4. Git Push
    run_git_cmd(["git", "push"])

    print("\n" + "=" * 80, flush=True)
    print("PROJECT FREEZE CHECKPOINT COMPLETE", flush=True)
    print("=" * 80, flush=True)

if __name__ == "__main__":
    main()
