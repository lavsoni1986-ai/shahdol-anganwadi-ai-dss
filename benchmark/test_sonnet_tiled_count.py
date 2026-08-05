"""
BharatOS Shahdol Anganwadi — Tiled / Region-Based Claude Sonnet 4.5 Child Counter
================================================================================
Isolated experimental benchmark using 2x3 overlapping geometry-based image
tiling (15% overlap) followed by Claude Sonnet 4.5 global reconciliation.

Target Image: CEO-REAL-01.jpeg

DO NOT MODIFY PRODUCTION CODE.
"""

import base64
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import cv2
import httpx
import numpy as np
from dotenv import load_dotenv

# Ensure local benchmark imports resolve
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
MODEL_ID = "anthropic/claude-sonnet-4.5"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_TOKENS = 1024

IMAGE_ID = "CEO-REAL-01"
TILED_RESULTS_DIR = BENCHMARK_DIR / "results" / "tiled"
TILED_DEBUG_DIR = BENCHMARK_DIR / "results" / "tiled_debug"

TILE_ENUMERATION_PROMPT_VERSION = "sonnet_tile_enumeration_v1"
RECONCILIATION_PROMPT_VERSION = "sonnet_tiled_reconciliation_v1"


def encode_bytes_to_base64_url(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def resolve_test_image(image_id: str) -> Path:
    for ext in [".jpeg", ".jpg", ".png"]:
        path = BENCHMARK_DIR / f"{image_id}{ext}"
        if path.exists():
            return path.resolve()
    return (BENCHMARK_DIR / f"{image_id}.jpeg").resolve()


def generate_deterministic_2x3_tiles(
    image_path: Path, overlap_percent: float = 0.15
) -> tuple[np.ndarray, List[Dict[str, Any]], List[bytes]]:
    """
    Stage 1: Generates a deterministic 2 rows x 3 columns grid of overlapping tiles.
    Returns (full_cv2_image, list_of_tile_metadata, list_of_tile_jpeg_bytes).
    """
    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"Could not load image file at: {image_path}")

    height, width = img.shape[:2]

    # Calculate tile dimensions for 2x3 grid with ~15% overlap
    tile_w = int(round(width / (1 + 2 * (1.0 - overlap_percent))))
    tile_h = int(round(height / (1 + 1 * (1.0 - overlap_percent))))

    step_x = int(round(tile_w * (1.0 - overlap_percent)))
    step_y = int(round(tile_h * (1.0 - overlap_percent)))

    tile_metas: List[Dict[str, Any]] = []
    tile_bytes_list: List[bytes] = []

    tile_idx = 1
    for r in range(2):
        for c in range(3):
            tile_id = f"T{tile_idx:02d}"

            if c == 0:
                x1 = 0
                x2 = tile_w
            elif c == 1:
                x1 = step_x
                x2 = min(x1 + tile_w, width)
            else:
                x2 = width
                x1 = width - tile_w

            if r == 0:
                y1 = 0
                y2 = tile_h
            else:
                y2 = height
                y1 = height - tile_h

            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(width, x2), min(height, y2)

            crop = img[y1:y2, x1:x2]
            _, jpeg_buf = cv2.imencode(".jpg", crop, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            crop_bytes = jpeg_buf.tobytes()

            tile_metas.append({
                "tile_id": tile_id,
                "row": r,
                "col": c,
                "bbox": [x1, y1, x2, y2],
                "width": x2 - x1,
                "height": y2 - y1,
            })
            tile_bytes_list.append(crop_bytes)

            tile_idx += 1

    return img, tile_metas, tile_bytes_list


def parse_robust_json(text: str, target_key: str = "child_count") -> Tuple[Optional[Any], str]:
    """
    Robust multi-stage parser for model JSON responses.
    Extracts dictionary containing target_key regardless of formatting.
    """
    if not text:
        return None, "Empty response"

    cleaned = text.strip()

    # 1. Direct JSON parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and target_key in data:
            return data[target_key], "Success (Direct JSON)"
    except Exception:
        pass

    # 2. Code block extraction (```json ... ```)
    if "```" in cleaned:
        blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        for b in blocks:
            try:
                data = json.loads(b.strip())
                if isinstance(data, dict) and target_key in data:
                    return data[target_key], "Success (Fenced JSON)"
            except Exception:
                pass

    # 3. Regex extraction for target key
    regex_pattern = rf'\{{\s*"[^{{}}]*{target_key}"\s*:\s*([^,\}}]+)[^{{}}]*\}}'
    match = re.search(regex_pattern, cleaned)
    if match:
        raw_val = match.group(1).strip()
        try:
            val = json.loads(raw_val)
            return val, "Success (Regex Extracted)"
        except Exception:
            if raw_val.isdigit():
                return int(raw_val), "Success (Regex Int Extracted)"

    return None, f"Failed to parse JSON target key '{target_key}'"


def run_sonnet_tiled_benchmark(reconcile_only: bool = False):
    TILED_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    TILED_DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    target_result_path = TILED_RESULTS_DIR / f"{IMAGE_ID}_sonnet_tiled.json"

    existing_record: Optional[Dict[str, Any]] = None
    if target_result_path.exists():
        try:
            with open(target_result_path, "r", encoding="utf-8") as f:
                existing_record = json.load(f)
        except Exception:
            existing_record = None

    # Check first-run overwrite protection unless running reconcile-only
    if not reconcile_only and existing_record and existing_record.get("final_child_count") is not None:
        print(f"\n==================================================", flush=True)
        print(f"TILED BENCHMARK ALREADY EXISTS & COMPLETED: {target_result_path}", flush=True)
        print("Skipping execution to preserve first-run empirical integrity.", flush=True)
        print("==================================================", flush=True)
        return

    image_path = resolve_test_image(IMAGE_ID)
    if not image_path.exists():
        print(f"ERROR: Target image not found at resolved path: {image_path}", flush=True)
        print("Benchmark stopped prior to API call.", flush=True)
        return

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY missing in .env", flush=True)
        return

    # Load prompt templates
    tile_prompt_template, tile_prompt_sha256 = load_prompt(TILE_ENUMERATION_PROMPT_VERSION, BENCHMARK_DIR)
    recon_prompt_template, recon_prompt_sha256 = load_prompt(RECONCILIATION_PROMPT_VERSION, BENCHMARK_DIR)
    image_sha256 = compute_sha256(image_path)

    # Load full image
    full_cv2_img, tile_metas, tile_bytes_list = generate_deterministic_2x3_tiles(image_path, overlap_percent=0.15)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://bharatos.gov.in",
        "X-Title": f"Shahdol Anganwadi Tiled Benchmark ({IMAGE_ID})",
    }

    tile_predictions: List[Dict[str, Any]] = []
    raw_tile_responses: List[str] = []
    tile_api_latency_seconds: float = 0.0

    # ── RESUME MODE (--reconcile-only) vs FULL RUN ──
    if reconcile_only or (existing_record and "tile_predictions" in existing_record and len(existing_record["tile_predictions"]) == 6):
        print(f"\n==================================================", flush=True)
        print(f"RESUME MODE (--reconcile-only): REUSING STAGE-2 TILE RESULTS", flush=True)
        print(f"MAKING ZERO STAGE-2 API CALLS", flush=True)
        print("==================================================", flush=True)

        if not existing_record or "tile_predictions" not in existing_record:
            print(f"ERROR: Cannot run --reconcile-only. No valid tile predictions found in {target_result_path}", flush=True)
            return

        tile_predictions = existing_record["tile_predictions"]
        raw_tile_responses = existing_record.get("raw_tile_responses", [])
        tile_api_latency_seconds = existing_record.get("tile_api_latency_seconds", 0.0)

        for tp in tile_predictions:
            t_id = tp.get("tile_id", "?")
            t_cnt = tp.get("tile_child_count", 0)
            t_lat = tp.get("latency", 0.0)
            print(f"  [{t_id}] Count: {t_cnt} (Loaded from saved Stage-2 record | Latency: {t_lat}s)", flush=True)

    else:
        # ── STAGE 1: Generate & Save Debug Tiles ──
        print(f"\n==================================================", flush=True)
        print(f"STAGE 1: GENERATING 2x3 OVERLAPPING TILES (~15% OVERLAP)", flush=True)
        print(f"IMAGE: {image_path}", flush=True)
        print("==================================================", flush=True)

        for meta, crop_bytes in zip(tile_metas, tile_bytes_list):
            t_id = meta["tile_id"]
            debug_path = TILED_DEBUG_DIR / f"{IMAGE_ID}_{t_id}.jpg"
            with open(debug_path, "wb") as f:
                f.write(crop_bytes)
            print(f"  [DEBUG TILE] Saved {t_id} crop ({meta['width']}x{meta['height']} px) -> {debug_path}", flush=True)

        # ── STAGE 2: Local Tile Enumeration (6 Tile Requests) ──
        print(f"\n==================================================", flush=True)
        print(f"STAGE 2: SONNET LOCAL TILE ENUMERATION (6 TILES)", flush=True)
        print("==================================================", flush=True)

        start_tile_api = time.perf_counter()

        for meta, crop_bytes in zip(tile_metas, tile_bytes_list):
            t_id = meta["tile_id"]
            tile_prompt_text = tile_prompt_template.replace("<TILE_ID>", t_id)
            tile_base64_url = encode_bytes_to_base64_url(crop_bytes, "image/jpeg")

            payload = {
                "model": MODEL_ID,
                "max_tokens": MAX_TOKENS,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": tile_prompt_text},
                            {"type": "image_url", "image_url": {"url": tile_base64_url}},
                        ],
                    }
                ],
            }

            t_start = time.perf_counter()
            try:
                res = httpx.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=60.0)
                t_end = time.perf_counter()
                t_lat = round(t_end - t_start, 4)

                if res.status_code != 200:
                    print(f"  [{t_id}] API ERROR (HTTP {res.status_code}): {res.text}", flush=True)
                    raw_tile_responses.append(f"HTTP {res.status_code}: {res.text}")
                    tile_predictions.append({"tile_id": t_id, "tile_child_count": 0, "children": [], "latency": t_lat, "error": True})
                    continue

                res_json = res.json()
                raw_text = res_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                raw_tile_responses.append(raw_text)

                t_count, parse_msg = parse_robust_json(raw_text, target_key="tile_child_count")
                t_count_val = int(t_count) if isinstance(t_count, (int, float)) else 0

                tile_predictions.append({
                    "tile_id": t_id,
                    "tile_child_count": t_count_val,
                    "bbox": meta["bbox"],
                    "latency": t_lat,
                    "raw_parse_status": parse_msg
                })
                print(f"  [{t_id}] Count: {t_count_val} (Latency: {t_lat}s)", flush=True)

            except Exception as ex:
                t_end = time.perf_counter()
                t_lat = round(t_end - t_start, 4)
                print(f"  [{t_id}] EXCEPTION: {ex}", flush=True)
                raw_tile_responses.append(f"Exception: {ex}")
                tile_predictions.append({"tile_id": t_id, "tile_child_count": 0, "latency": t_lat, "error": True})

        end_tile_api = time.perf_counter()
        tile_api_latency_seconds = round(end_tile_api - start_tile_api, 4)

    naive_tile_sum = sum(tp.get("tile_child_count", 0) for tp in tile_predictions)
    print(f"\n  [DIAGNOSTIC] NAIVE TILE SUM: {naive_tile_sum} (Total Tile Latency: {tile_api_latency_seconds}s)", flush=True)

    # ── STAGE 3: Global Reconciliation (COMPACT SINGLE-IMAGE PAYLOAD) ──
    print(f"\n==================================================", flush=True)
    print(f"STAGE 3: SONNET GLOBAL RECONCILIATION (COMPACT SINGLE-IMAGE PAYLOAD)", flush=True)
    print("==================================================", flush=True)

    with open(image_path, "rb") as f:
        full_orig_bytes = f.read()
    full_orig_base64_url = encode_bytes_to_base64_url(full_orig_bytes, "image/jpeg")

    # Build COMPACT structured JSON (No raw Sonnet responses, No tile images in payload)
    compact_tile_data = {
        "tiles": [
            {
                "id": meta["tile_id"],
                "bbox": meta["bbox"],
                "count": tp.get("tile_child_count", 0),
            }
            for meta, tp in zip(tile_metas, tile_predictions)
        ]
    }

    recon_context_str = (
        f"FULL IMAGE DIMENSIONS: {full_cv2_img.shape[1]}x{full_cv2_img.shape[0]} px\n"
        f"TILE OVERLAP: ~15%\n\n"
        f"STRUCTURED TILE OBSERVATIONS (JSON):\n"
        f"{json.dumps(compact_tile_data, indent=2)}\n"
    )

    full_recon_prompt_text = f"{recon_prompt_template}\n\n{recon_context_str}"

    # Stage 3 payload sends ONLY 1 image: the original full-resolution image
    recon_content_array: List[Dict[str, Any]] = [
        {"type": "text", "text": full_recon_prompt_text},
        {"type": "image_url", "image_url": {"url": full_orig_base64_url}},
    ]

    recon_payload = {
        "model": MODEL_ID,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": recon_content_array}],
    }

    start_recon = time.perf_counter()
    raw_reconciliation_response = ""
    final_child_count = None

    try:
        print("  [STAGE 3] Sending single-image compact reconciliation request to OpenRouter...", flush=True)
        recon_res = httpx.post(OPENROUTER_API_URL, headers=headers, json=recon_payload, timeout=90.0)
        end_recon = time.perf_counter()
        reconciliation_latency_seconds = round(end_recon - start_recon, 4)

        if recon_res.status_code != 200:
            print(f"  [RECON ERROR] API HTTP {recon_res.status_code}: {recon_res.text}", flush=True)
            raw_reconciliation_response = f"HTTP {recon_res.status_code}: {recon_res.text}"
        else:
            recon_json = recon_res.json()
            raw_reconciliation_response = recon_json.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

            parsed_count, parse_status = parse_robust_json(raw_reconciliation_response, target_key="child_count")
            if isinstance(parsed_count, (int, float)):
                final_child_count = int(parsed_count)
            print(f"  [STAGE 3 COMPLETE] Final Reconciled Count: {final_child_count} (Parse Status: {parse_status} | Latency: {reconciliation_latency_seconds}s)", flush=True)

    except Exception as ex:
        end_recon = time.perf_counter()
        reconciliation_latency_seconds = round(end_recon - start_recon, 4)
        print(f"  [RECON EXCEPTION]: {ex}", flush=True)
        raw_reconciliation_response = f"Exception: {ex}"

    total_latency_seconds = round(tile_api_latency_seconds + reconciliation_latency_seconds, 4)

    # ── CONSOLE OUTPUT SUMMARY ──
    print("\n==================================================", flush=True)
    print("SONNET 4.5 TILED CHILD COUNT BENCHMARK", flush=True)
    print("==================================================", flush=True)
    print(f"IMAGE: {IMAGE_ID} ({image_path.name})", flush=True)
    print(f"MODEL: {MODEL_ID}", flush=True)
    print("", flush=True)

    for tp in tile_predictions:
        print(f"{tp['tile_id']} count: {tp.get('tile_child_count', 0)}", flush=True)

    print("", flush=True)
    print(f"NAIVE TILE SUM: {naive_tile_sum}", flush=True)
    print(f"FINAL RECONCILED CHILD COUNT: {final_child_count}", flush=True)
    print("", flush=True)
    print(f"TILE API LATENCY        : {tile_api_latency_seconds}s", flush=True)
    print(f"RECONCILIATION LATENCY  : {reconciliation_latency_seconds}s", flush=True)
    print(f"TOTAL LATENCY           : {total_latency_seconds}s", flush=True)
    print("", flush=True)

    # ── SAVE / UPDATE RESULT JSON RECORD ──
    previous_failed_stage3 = existing_record.get("raw_reconciliation_response") if existing_record else None

    result_record = {
        "image_id": IMAGE_ID,
        "image_sha256": image_sha256,
        "model": MODEL_ID,
        "method": "2x3_overlapping_tiles_global_reconciliation",
        "tile_overlap_percent": 15.0,
        "tiles": tile_metas,
        "tile_predictions": tile_predictions,
        "naive_tile_sum": naive_tile_sum,
        "final_child_count": final_child_count,
        "tile_api_latency_seconds": tile_api_latency_seconds,
        "reconciliation_latency_seconds": reconciliation_latency_seconds,
        "total_latency_seconds": total_latency_seconds,
        "raw_tile_responses": raw_tile_responses,
        "raw_reconciliation_response": raw_reconciliation_response,
        "audit_previous_failed_stage3_response": previous_failed_stage3,
        "timestamp": utc_timestamp(),
    }

    with open(target_result_path, "w", encoding="utf-8") as f:
        json.dump(result_record, f, indent=2, ensure_ascii=False)

    print(f"RESULT FILE: {target_result_path}", flush=True)
    print("==================================================\n", flush=True)


if __name__ == "__main__":
    reconcile_only_flag = "--reconcile-only" in sys.argv
    run_sonnet_tiled_benchmark(reconcile_only=reconcile_only_flag)
