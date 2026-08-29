import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional, Tuple
import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from utils import load_prompt, compute_sha256, utc_timestamp
except ModuleNotFoundError:
    from benchmark.utils import load_prompt, compute_sha256, utc_timestamp

# Load environment variables from .env
load_dotenv()

BENCHMARK_DIR = Path(__file__).parent.resolve()
GATE_RESULTS_DIR = BENCHMARK_DIR / "results" / "gate"
IMAGE_PATH = (BENCHMARK_DIR / "GATE-TEST-01.png").resolve()
if not IMAGE_PATH.exists():
    IMAGE_PATH = (BENCHMARK_DIR / "GATE-TEST-01.jpeg").resolve()
if not IMAGE_PATH.exists():
    IMAGE_PATH = (BENCHMARK_DIR / "GATE-TEST-01.jpg").resolve()
IMAGE_ID = "GATE-TEST-01"
PROMPT_VERSION = "anganwadi_gate_v1"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


def encode_image_to_base64(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Gate test image not found at: {path.absolute()}")
    
    ext = path.suffix.lower()
    mime_type = "image/png" if ext == ".png" else "image/jpeg"

    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def run_gate_model_benchmark(engine_id: str, model_id: str, max_tokens: int = 512) -> None:
    GATE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    target_json_path = GATE_RESULTS_DIR / f"{IMAGE_ID}_{engine_id}.json"

    # FIRST-RUN OVERWRITE PROTECTION
    if target_json_path.exists():
        print(f"\n==================================================")
        print(f"GATE BENCHMARK ALREADY EXISTS: {target_json_path}")
        print("Skipping execution to preserve first-run empirical integrity.")
        print("==================================================")
        return

    if not IMAGE_PATH.exists():
        print(f"ERROR: Gate test image not found at: {IMAGE_PATH}")
        print("Benchmark stopped prior to API call.")
        return

    # Load shared prompt
    prompt_text, prompt_sha256 = load_prompt(PROMPT_VERSION, BENCHMARK_DIR)
    image_sha256 = compute_sha256(IMAGE_PATH)

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY missing in .env")
        return

    base64_url = encode_image_to_base64(IMAGE_PATH)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://bharatos.gov.in",
        "X-Title": f"Shahdol Anganwadi Gate-0 Benchmark ({engine_id})",
    }

    payload = {
        "model": model_id,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": base64_url}},
                ],
            }
        ],
    }

    print(f"\n==================================================", flush=True)
    print(f"RUNNING GATE-0 BENCHMARK ({engine_id.upper()})", flush=True)
    print(f"MODEL: {model_id}", flush=True)
    print(f"IMAGE: {IMAGE_PATH}", flush=True)
    print("==================================================", flush=True)

    start_time = time.perf_counter()
    raw_response = ""
    valid_anganwadi_image = False
    child_count: Optional[int] = None
    reason = "API_ERROR"
    final_decision = "API_ERROR"
    cost = None

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
            print(f"API ERROR (HTTP {response.status_code}): {response.text}")
            final_decision = "API_ERROR"
            reason = f"HTTP {response.status_code}: {response.text[:100]}"
        else:
            res_json = response.json()
            cost = res_json.get("usage", {}).get("total_cost") or res_json.get("cost")
            if "choices" in res_json and len(res_json["choices"]) > 0:
                raw_response = res_json["choices"][0].get("message", {}).get("content", "").strip()

            # Parse JSON
            try:
                cleaned_raw = raw_response
                if "```json" in cleaned_raw:
                    cleaned_raw = cleaned_raw.split("```json")[1].split("```")[0].strip()
                elif "```" in cleaned_raw:
                    cleaned_raw = cleaned_raw.split("```")[1].split("```")[0].strip()

                parsed = json.loads(cleaned_raw)
                valid_anganwadi_image = bool(parsed.get("valid_anganwadi_image"))
                raw_count = parsed.get("child_count")
                reason = str(parsed.get("reason", ""))

                # Python Contract Enforcement Logic
                if valid_anganwadi_image:
                    if isinstance(raw_count, (int, float)):
                        child_count = int(raw_count)
                        final_decision = "ACCEPT_AND_COUNT"
                    else:
                        final_decision = "INVALID_MODEL_RESPONSE"
                        reason += " [Error: Accepted image but child_count was not an integer]"
                else:
                    # Invariant Enforcement: valid == false => child_count must be null
                    if raw_count is not None:
                        final_decision = "INVALID_MODEL_RESPONSE"
                        child_count = None  # Enforce null invariant
                        reason += " [Contract Violation: Model supplied child_count for rejected image]"
                    else:
                        child_count = None
                        final_decision = "REJECT_IMAGE"

            except Exception as parse_err:
                final_decision = "INVALID_MODEL_RESPONSE"
                reason = f"JSON Parse Error: {parse_err}"

    except Exception as exc:
        end_time = time.perf_counter()
        latency = round(end_time - start_time, 4)
        print(f"HTTP REQUEST EXCEPTION: {exc}")
        final_decision = "API_ERROR"
        reason = f"Exception: {exc}"

    # Print summary
    print("\n--------------------------------------------------")
    print(f"FINAL DECISION       : {final_decision}")
    print(f"VALID ANGANWADI IMAGE: {valid_anganwadi_image}")
    print(f"CHILD COUNT          : {child_count}")
    print(f"REASON               : {reason}")
    print(f"LATENCY              : {latency}s")
    print("--------------------------------------------------")

    # Save Gate Result Record
    record = {
        "image_id": IMAGE_ID,
        "image_sha256": image_sha256,
        "engine": engine_id,
        "model": model_id,
        "gate_prompt_version": PROMPT_VERSION,
        "prompt_sha256": prompt_sha256,
        "valid_anganwadi_image": valid_anganwadi_image,
        "child_count": child_count,
        "reason": reason,
        "final_decision": final_decision,
        "latency": latency,
        "cost": cost,
        "raw_response": raw_response,
        "timestamp": utc_timestamp(),
    }

    with open(target_json_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    print(f"[RESULT SAVED] Gate benchmark output written to: {target_json_path}\n")
