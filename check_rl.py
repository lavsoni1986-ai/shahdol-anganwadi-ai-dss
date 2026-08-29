import reportlab
print("reportlab version:", reportlab.Version)
try:
    import uharfbuzz
    print("uharfbuzz version:", uharfbuzz.__version__)
    print("uharfbuzz is available")
except ImportError:
    print("uharfbuzz is NOT available")
