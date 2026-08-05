import glob
import os
import tempfile

def check():
    temp_dir = tempfile.gettempdir()
    logs = glob.glob(os.path.join(temp_dir, "*.log"))
    logs.sort(key=os.path.getmtime, reverse=True)
    print(f"Found {len(logs)} log files in {temp_dir}")
    for log_path in logs[:3]:
        print("------------------------------------------")
        print("Log File:", log_path)
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
                print("Content:\n", content)
        except Exception as e:
            print("Error reading:", e)

if __name__ == "__main__":
    check()
