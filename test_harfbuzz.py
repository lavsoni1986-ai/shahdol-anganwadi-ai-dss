import reportlab
import reportlab.rl_config
reportlab.rl_config.use_harfbuzz = True

from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate
from reportlab.lib.styles import ParagraphStyle

pdfmetrics.registerFont(TTFont("NotoSansDevanagari", "app/static/fonts/NotoSansDevanagari-Regular.ttf"))

doc = SimpleDocTemplate("test_harfbuzz.pdf")
style = ParagraphStyle("Test", fontName="NotoSansDevanagari", fontSize=14)
# Try wordAxes as well
style2 = ParagraphStyle("Test2", fontName="NotoSansDevanagari", fontSize=14, wordAxes=1, shaping=True)

story = [
    Paragraph("महिला एवं बाल विकास विभाग", style),
    Paragraph("महिला एवं बाल विकास विभाग (shaping=True)", style2),
]
doc.build(story)
