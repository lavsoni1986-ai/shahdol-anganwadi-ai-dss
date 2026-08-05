"""
BharatOS Shahdol Anganwadi — YOLO + Claude Sonnet 4.5 Hybrid Child Counter
================================================================================
Isolated experimental benchmark combining YOLO11m person localization with
Claude Sonnet 4.5 visual reasoning for crowded Anganwadi child counting.

Target Images:
- CEO-F01.jpeg
- CEO-F03.jpeg
- CEO-F04.jpeg

DO NOT MODIFY PRODUCTION CODE.
"""

import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import cv2
import httpx
import numpy as np
from dotenv import load_dotenv

# Ensure local imports resolve
BENCHMARK_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = BENCHMARK_DIR.parent.resolve()
sys.path.insert(0, str(BENCHMARK_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from utils import load_prompt, compute_sha256, utc_timestamp
except ModuleNotFoundError:
    from benchmark.utils import load_prompt, compute_sha256, utc_timestamp

load_dotenv()

# Configuration
YOLO_MODEL_PATH = PROJECT_ROOT / "yolo11m.pt"
SONNET_MODEL_ID = "anthropic/claude-sonnet-4.5"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
PROMPT_VERSION = "yolo_sonnet_child_count_v1"
MAX_TOKENS = 512

RESULTS_HYBRID_DIR = BENCHMARK_DIR / "results" / "hybrid"
RESULTS_DEBUG_DIR = BENCHMARK_DIR / "results" / "yolo_sonnet_debug"

TARGET_IMAGES = ["CEO-F01", "CEO-F03", "CEO-F04"]


def encode_image_to_base64(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def run_yolo_detection(image_path: Path) -> tuple[np.ndarray, List[Dict[str, Any]], float]:
    """
    Runs pretrained YOLO11m person detection (COCO class 0).
    Returns (annotated_cv2_image, list_of_detections, yolo_latency).
    """
    from ultralytics import YOLO

    if not YOLO_MODEL_PATH.exists():
        raise FileNotFoundError(f"Existing YOLO model file not found at: {YOLO_MODEL_PATH}")

    model = YOLO(str(YOLO_MODEL_PATH))
    
    start_time = time.perf_counter()
    results = model.predict(source=str(image_path), classes=[0], conf=0.25, verbose=False)
    end_time = time.perf_counter()
    yolo_latency = round(end_time - start_time, 4)

    img_cv2 = cv2.imread(str(image_path))
    annotated_img = img_cv2.copy()

    detections = []
    boxes = results[0].boxes

    for idx, box in enumerate(boxes, 1):
        label_id = f"P{idx:02d}"
        confidence = float(box.conf[0])
        xyxy = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
        x1, y1, x2, y2 = map(int, xyxy)

        detections.append({
            "id": label_id,
            "confidence": round(confidence, 3),
            "bbox": [x1, y1, x2, y2]
        })

        # Draw box and ID label on annotated image copy
        cv2.rectangle(annotated_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            annotated_img,
            label_id,
            (x1, max(y1 - 5, 15)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

    return annotated_img, detections, yolo_latency


def run_yolo_sonnet_hybrid_benchmark():
    RESULTS_HYBRID_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY missing in .env")
        return

    # Load registered prompt
    prompt_text, prompt_sha256 = load_prompt(PROMPT_VERSION, BENCHMARK_DIR)

    print("\n" + "=" * 80)
    print("YOLO + CLAUDE SONNET 4.5 HYBRID CHILD COUNT BENCHMARK")
    print(f"SONNET MODEL: {SONNET_MODEL_ID}")
    print(f"YOLO MODEL  : {YOLO_MODEL_PATH.name}")
    print("=" * 80)

    for img_id in TARGET_IMAGES:
        target_json_path = RESULTS_HYBRID_DIR / f"{img_id}_yolo_sonnet.json"

        # FIRST-RUN OVERWRITE PROTECTION
        if target_json_path.exists():
            print(f"\n[OVERWRITE PROTECTION] Hybrid result already exists: {target_json_path}")
            print("Skipping execution to preserve first-run empirical integrity.")
            continue

        image_path = BENCHMARK_DIR / f"{img_id}.jpeg"
        if not image_path.exists():
            image_path = BENCHMARK_DIR / f"{img_id}.jpg"

        if not image_path.exists():
            print(f"\nERROR: Image file not found for {img_id} at {image_path}")
            continue

        print(f"\nProcessing {img_id} ({image_path.name})...")
        image_sha256 = compute_sha256(image_path)

        # 1. Run YOLO Person Localization
        try:
            annotated_cv2, detections, latency_yolo = run_yolo_detection(image_path)
            yolo_person_count = len(detections)
            print(f"  [YOLO] Detected {yolo_person_count} person boxes (Latency: {latency_yolo}s)")

            # Save annotated debug image
            debug_img_path = RESULTS_DEBUG_DIR / f"{img_id}_yolo_annotated.jpg"
            cv2.imwrite(str(debug_img_path), annotated_cv2)
            print(f"  [DEBUG IMAGE] Saved annotated copy to: {debug_img_path}")

        except Exception as e:
            print(f"  [ERROR] YOLO detection failed on {img_id}: {e}")
            continue

        # Prepare images for Sonnet
        with open(image_path, "rb") as f:
            orig_bytes = f.read()
        orig_base64_url = encode_image_to_base64(orig_bytes, "image/jpeg")

        _, anim_encoded = cv2.imencode(".jpg", annotated_cv2)
        annotated_bytes = anim_encoded.tobytes()
        annotated_base64_url = encode_image_to_base64(annotated_bytes, "image/jpeg")

        # 2. Invoke Claude Sonnet 4.5 with Dual Images
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://bharatos.gov.in",
            "X-Title": f"Shahdol Anganwadi YOLO-Sonnet Hybrid ({img_id})",
        }

        payload = {
            "model": SONNET_MODEL_ID,
            "max_tokens": MAX_TOKENS,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": orig_base64_url}},
                        {"type": "image_url", "image_url": {"url": annotated_base64_url}},
                    ],
                }
            ],
        }

        print(f"  [SONNET] Sending dual-image request to OpenRouter ({SONNET_MODEL_ID})...")
        start_sonnet = time.perf_counter()

        try:
            response = httpx.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=60.0,
            )
            end_sonnet = time.perf_counter()
            latency_sonnet = round(end_sonnet - start_sonnet, 4)
            latency_total = round(latency_yolo + latency_sonnet, 4)

            if response.status_code != 200:
                print(f"  [SONNET API ERROR] (HTTP {response.status_code}): {response.text}")
                continue

            res_json = response.json()
            raw_sonnet_response = ""
            if "choices" in res_json and len(res_json["choices"]) > 0:
                raw_sonnet_response = res_json["choices"][0].get("message", {}).get("content", "").strip()

            # Parse Sonnet final child count
            final_child_count = None
            try:
                cleaned_raw = raw_sonnet_response
                if "```json" in cleaned_raw:
                    cleaned_raw = cleaned_raw.split("```json")[1].split("```")[0].strip()
                elif "```" in cleaned_raw:
                    cleaned_raw = cleaned_raw.split("```")[1].split("```")[0].strip()

                parsed = json.loads(cleaned_raw)
                if "child_count" in parsed:
                    final_child_count = int(parsed["child_count"])
            except Exception as pe:
                print(f"  [PARSE ERROR] Could not parse JSON from Sonnet: {pe}")

            print(f"  [HYBRID RESULT] {img_id} -> YOLO Boxes: {yolo_person_count} | Sonnet Final Child Count: {final_child_count} (Sonnet Latency: {latency_sonnet}s)")

            # 3. Save Standard Hybrid Result Record
            result_record = {
                "image_id": img_id,
                "image_sha256": image_sha256,
                "yolo_model": YOLO_MODEL_PATH.name,
                "yolo_person_count": yolo_person_count,
                "yolo_detections": detections,
                "sonnet_model": SONNET_MODEL_ID,
                "prompt_version": PROMPT_VERSION,
                "prompt_sha256": prompt_sha256,
                "final_child_count": final_child_count,
                "latency_yolo": latency_yolo,
                "latency_sonnet": latency_sonnet,
                "latency_total": latency_total,
                "raw_sonnet_response": raw_sonnet_response,
                "timestamp": utc_timestamp(),
            }

            with open(target_json_path, "w", encoding="utf-8") as f_json:
                json.dump(result_record, f_json, indent=2, ensure_ascii=False)

            print(f"  [RESULT SAVED] Written to: {target_json_path}")

        except Exception as exc:
            print(f"  [EXCEPTION] Failed processing {img_id}: {exc}")


if __name__ == "__main__":
    run_yolo_sonnet_hybrid_benchmark()
