import reportlab
import reportlab.rl_config
reportlab.rl_config.use_harfbuzz = True
try:
    import uharfbuzz
    print("uharfbuzz is installed")
except ImportError:
    print("uharfbuzz is NOT installed")
