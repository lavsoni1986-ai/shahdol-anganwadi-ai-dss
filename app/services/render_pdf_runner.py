# app/services/render_pdf_runner.py
import sys
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

start_time = time.time()
log_file_path = None

def checkpoint(name: str):
    elapsed_ms = int((time.time() - start_time) * 1000)
    msg = f"[CHECKPOINT] [{elapsed_ms:6d} ms] {name}"
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()
    if log_file_path:
        try:
            with open(log_file_path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass

def main():
    global log_file_path
    checkpoint("RUNNER_STARTED")

    if len(sys.argv) < 3:
        checkpoint("ERROR_INVALID_ARGS")
        sys.stderr.write("Usage: render_pdf_runner.py <input_html_path> <output_pdf_path> [log_file_path]\n")
        sys.exit(1)

    html_path = sys.argv[1]
    pdf_path = sys.argv[2]
    if len(sys.argv) >= 4:
        log_file_path = sys.argv[3]

    if not os.path.exists(html_path):
        checkpoint("ERROR_HTML_NOT_FOUND")
        sys.stderr.write(f"Error: HTML input file not found: {html_path}\n")
        sys.exit(1)

    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        checkpoint("PLAYWRIGHT_STARTED")
        with sync_playwright() as p:
            checkpoint("CHROMIUM_LAUNCH_START")
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox",
                    "--allow-file-access-from-files",
                ]
            )
            checkpoint("BROWSER_LAUNCHED")

            context = browser.new_context()
            checkpoint("CONTEXT_CREATED")

            page = context.new_page()
            checkpoint("PAGE_CREATED")

            checkpoint("HTML_LOAD_START")
            checkpoint("HTML_LOADED")

            checkpoint("SET_CONTENT_START")
            file_url = Path(html_path).absolute().as_uri()
            page.goto(file_url, wait_until="domcontentloaded")
            checkpoint("SET_CONTENT_FINISHED")

            checkpoint("WAIT_FOR_LOAD_STATE_STARTED")
            page.wait_for_load_state("domcontentloaded")
            checkpoint("WAIT_FOR_LOAD_STATE_FINISHED")

            # Check Devanagari font readiness
            try:
                page.evaluate("document.fonts.ready")
                checkpoint("FONTS_READY")
            except Exception as font_ex:
                checkpoint(f"FONTS_WARNING_{font_ex}")

            checkpoint("PDF_RENDERING_STARTED")
            page.pdf(
                path=pdf_path,
                format="A4",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"}
            )
            checkpoint("PDF_RENDERING_FINISHED")

            checkpoint("BROWSER_CLOSE_START")
            browser.close()
            checkpoint("BROWSER_CLOSED")

    except Exception as ex:
        checkpoint(f"RUNNER_EXCEPTION_{type(ex).__name__}_{str(ex)}")
        sys.stderr.write(f"Exception inside render_pdf_runner: {ex}\n")
        sys.exit(1)

    checkpoint("RUNNER_EXIT")
    sys.exit(0)

if __name__ == "__main__":
    main()
