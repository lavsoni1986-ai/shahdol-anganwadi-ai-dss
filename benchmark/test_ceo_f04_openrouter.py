import base64
import json
import os
import sys
import time
from pathlib import Path
import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.utils import load_prompt
from benchmark.result_writer import save_result

# Load environment variables from .env file
load_dotenv()

# Configuration
BENCHMARK_DIR = Path(__file__).parent
IMAGE_PATH = (BENCHMARK_DIR / "CEO-F04.jpeg").resolve()
IMAGE_ID = "CEO-F04"
ENGINE_ID = "gemini_flash"
MODEL_ID = "google/gemini-2.5-flash"
MAX_TOKENS = 512
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
PROMPT_VERSION = "child_count_v1"

# Load registered prompt text and prompt SHA256 from prompt registry
EXACT_PROMPT, PROMPT_SHA256 = load_prompt(PROMPT_VERSION, BENCHMARK_DIR)


def encode_image_to_base64(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Image not found at path: {path.absolute()}")
    
    ext = path.suffix.lower()
    mime_type = "image/png" if ext == ".png" else "image/jpeg"

    with open(path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
    
    return f"data:{mime_type};base64,{encoded_string}"


def run_benchmark():
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not found in environment or .env file.")
        return

    if not IMAGE_PATH.exists():
        print(f"ERROR: Local image file does not exist at: {IMAGE_PATH}")
        print("Benchmark stopped prior to API request.")
        return

    print(f"Loading image from: {IMAGE_PATH}")
    try:
        base64_url = encode_image_to_base64(IMAGE_PATH)
    except Exception as e:
        print(f"ERROR loading image: {e}")
        return

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://bharatos.gov.in",
        "X-Title": "Shahdol Anganwadi CEO-F04 Child Count Benchmark",
    }

    payload = {
        "model": MODEL_ID,
        "max_tokens": MAX_TOKENS,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": EXACT_PROMPT},
                    {"type": "image_url", "image_url": {"url": base64_url}},
                ],
            }
        ],
    }

    print(f"Sending request to OpenRouter ({MODEL_ID})...")
    start_time = time.perf_counter()

    try:
        response = httpx.post(
            OPENROUTER_API_URL,
            headers=headers,
            json=payload,
            timeout=60.0,
        )
        end_time = time.perf_counter()
        latency = round(end_time - start_time, 4)

        if response.status_code != 200:
            print("\n==================================================")
            print(f"OPENROUTER API ERROR (HTTP {response.status_code})")
            print("==================================================")
            print(response.text)
            return

        res_json = response.json()
        raw_response = ""
        prompt_tokens = "N/A"
        completion_tokens = "N/A"
        total_tokens = "N/A"
        cost = res_json.get("usage", {}).get("total_cost") or res_json.get("cost")

        if "choices" in res_json and len(res_json["choices"]) > 0:
            raw_response = res_json["choices"][0].get("message", {}).get("content", "").strip()

        usage = res_json.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", "N/A")
        completion_tokens = usage.get("completion_tokens", "N/A")
        total_tokens = usage.get("total_tokens", "N/A")

        # Parse child count safely from model JSON response
        parsed_prediction = None
        child_count_display = "Parsing Error"
        try:
            cleaned_raw = raw_response
            if "```json" in cleaned_raw:
                cleaned_raw = cleaned_raw.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned_raw:
                cleaned_raw = cleaned_raw.split("```")[1].split("```")[0].strip()
            
            parsed_data = json.loads(cleaned_raw)
            if "child_count" in parsed_data:
                parsed_prediction = int(parsed_data["child_count"])
                child_count_display = str(parsed_prediction)
        except Exception as parse_err:
            child_count_display = f"Parsing Error ({parse_err}) - Raw Response: {raw_response}"

        print("\n==================================================")
        print("CEO-F04 GEMINI 2.5 FLASH BENCHMARK")
        print("==================================================")
        print(f"MODEL            : {MODEL_ID}")
        print(f"IMAGE            : {IMAGE_PATH}")
        print(f"RAW RESPONSE     : {raw_response}")
        print(f"CHILD COUNT      : {child_count_display}")
        print(f"LATENCY          : {latency} seconds")
        print(f"PROMPT TOKENS    : {prompt_tokens}")
        print(f"COMPLETION TOKENS: {completion_tokens}")
        print(f"TOTAL TOKENS     : {total_tokens}")
        print(f"COST             : {cost if cost is not None else 'N/A'}")
        print("==================================================")

        # Save result JSON automatically (with first-run overwrite protection)
        saved, saved_path = save_result(
            engine=ENGINE_ID,
            model=MODEL_ID,
            image_id=IMAGE_ID,
            image_path=IMAGE_PATH,
            prompt_version=PROMPT_VERSION,
            prompt_sha256=PROMPT_SHA256,
            prediction=parsed_prediction,
            latency=latency,
            cost=cost,
            notes=f"Tokens: P={prompt_tokens}, C={completion_tokens}, T={total_tokens}",
            raw_response=raw_response,
            first_run=True,
        )

    except Exception as e:
        print(f"HTTP REQUEST EXCEPTION: {e}")


if __name__ == "__main__":
    run_benchmark()
