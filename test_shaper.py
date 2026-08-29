import sys
try:
    from reportlab.platypus.paragraph import get_shaper
    shaper = get_shaper()
    print("Shaper class:", shaper)
except Exception as e:
    print("Error:", e)
