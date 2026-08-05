import reportlab
import sys

with open('rl_info.txt', 'w') as f:
    f.write(f"reportlab version: {reportlab.Version}\n")
    try:
        import uharfbuzz
        f.write(f"uharfbuzz version: {uharfbuzz.__version__}\n")
    except ImportError:
        f.write("uharfbuzz NOT available\n")
