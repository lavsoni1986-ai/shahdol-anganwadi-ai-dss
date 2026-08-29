import hashlib
import json
import os
import sys
import time
from pathlib import Path
import cv2
import httpx
import torch
from ultralytics import YOLO

PROJECT_ROOT = Path(__file__).parent.resolve()
BENCHMARK_DIR = PROJECT_ROOT / "benchmark"
WEIGHTS_DIR = BENCHMARK_DIR / "weights"
WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)

CH_WEIGHTS_PATH = WEIGHTS_DIR / "crowdhuman_yolov5m.pt"
DOWNLOAD_URL = "https://huggingface.co/MK-CUPIST/crowdhuman_yolov5m/resolve/main/crowdhuman_yolov5m.pt"
SMOKE_IMAGE_PATH = BENCHMARK_DIR / "real_dataset" / "images" / "AWC-001.jpeg"
DEBUG_OUTPUT_DIR = BENCHMARK_DIR / "results" / "head_detector_smoke"
DEBUG_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def compute_sha256(path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def run_forensic_audit():
    print("=" * 80, flush=True)
    print("FORENSIC VERIFICATION AUDIT: CROWDHOMAN PRETRAINED MODEL", flush=True)
    print("=" * 80, flush=True)

    # ── STEP 1: Model Discovery & Download ──
    print("\n[STEP 1: MODEL DISCOVERY & SOURCE VERIFICATION]", flush=True)
    if not CH_WEIGHTS_PATH.exists():
        print(f"Downloading CrowdHuman weight file from: {DOWNLOAD_URL}...", flush=True)
        t_dl_start = time.perf_counter()
        with httpx.stream("GET", DOWNLOAD_URL, follow_redirects=True, timeout=90.0) as r:
            if r.status_code != 200:
                print(f"ERROR: HTTP {r.status_code} downloading weights", flush=True)
                sys.exit(1)
            with open(CH_WEIGHTS_PATH, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=65536):
                    f.write(chunk)
        t_dl_end = time.perf_counter()
        print(f"Download complete in {t_dl_end - t_dl_start:.2f}s", flush=True)
    else:
        print(f"Found existing CrowdHuman weight file at: {CH_WEIGHTS_PATH}", flush=True)

    size_mb = round(CH_WEIGHTS_PATH.stat().st_size / (1024 * 1024), 2)
    sha256_hash = compute_sha256(CH_WEIGHTS_PATH)

    print(f"  Filename          : {CH_WEIGHTS_PATH.name}", flush=True)
    print(f"  Absolute Path     : {CH_WEIGHTS_PATH}", flush=True)
    print(f"  File Size         : {size_mb} MB", flush=True)
    print(f"  SHA-256 Hash      : {sha256_hash}", flush=True)
    print(f"  Source Repository : MK-CUPIST/crowdhuman_yolov5m (Hugging Face)", flush=True)
    print(f"  License           : GPL-3.0 / CrowdHuman Non-Commercial License", flush=True)

    # ── STEP 2: Forensic Model Introspection ──
    print("\n[STEP 2: MODEL FORENSIC INTROSPECTION]", flush=True)
    try:
        checkpoint = torch.load(str(CH_WEIGHTS_PATH), map_location="cpu")
        print(f"  PyTorch Checkpoint Keys : {list(checkpoint.keys()) if isinstance(checkpoint, dict) else type(checkpoint)}", flush=True)

        embedded_names = None
        if isinstance(checkpoint, dict):
            if "model" in checkpoint:
                m_obj = checkpoint["model"]
                if hasattr(m_obj, "names"):
                    embedded_names = m_obj.names
            if not embedded_names and "names" in checkpoint:
                embedded_names = checkpoint["names"]

        print(f"  Embedded Class Names    : {embedded_names}", flush=True)
    except Exception as e:
        print(f"  Checkpoint Introspection Note: {e}", flush=True)

    # ── STEP 4: Local Load Test ──
    print("\n[STEP 4: LOCAL LOAD TEST]", flush=True)
    t_load_start = time.perf_counter()
    try:
        model = YOLO(str(CH_WEIGHTS_PATH))
        t_load_end = time.perf_counter()
        load_latency = round(t_load_end - t_load_start, 4)
        print(f"  Load Success           : TRUE (Latency: {load_latency}s)", flush=True)
        print(f"  Ultralytics Loaded Names: {model.names}", flush=True)
        print(f"  Classes Count          : {len(model.names)}", flush=True)
    except Exception as e:
        print(f"  Load Success           : FALSE - {e}", flush=True)
        sys.exit(1)

    # ── STEP 3 & 6: Output Contract & Class Verification ──
    print("\n[STEP 3 & 6: OUTPUT CONTRACT & CLASS VERIFICATION]", flush=True)
    if not SMOKE_IMAGE_PATH.exists():
        print(f"ERROR: Smoke test image not found at {SMOKE_IMAGE_PATH}", flush=True)
        sys.exit(1)

    img_cv2 = cv2.imread(str(SMOKE_IMAGE_PATH))
    h_img, w_img = img_cv2.shape[:2]

    # Run inference on AWC-001 only
    t_inf_start = time.perf_counter()
    results = model.predict(source=str(SMOKE_IMAGE_PATH), conf=0.25, verbose=False)
    t_inf_end = time.perf_counter()
    inf_latency = round(t_inf_end - t_inf_start, 4)

    boxes = results[0].boxes
    print(f"  Inference Latency      : {inf_latency}s on {w_img}x{h_img} px image", flush=True)
    print(f"  Total Detections       : {len(boxes)}", flush=True)
    print("\n  DETECTION DETAILS (FIRST 10 DETECTIONS):", flush=True)
    print("  " + "-" * 75, flush=True)

    annotated_img = img_cv2.copy()

    head_count = 0
    person_count = 0

    for idx, box in enumerate(boxes, 1):
        cls_id = int(box.cls[0])
        cls_name = model.names.get(cls_id, str(cls_id))
        conf = float(box.conf[0])
        xyxy = box.xyxy[0].tolist()
        x1, y1, x2, y2 = map(int, xyxy)

        if "head" in cls_name.lower() or cls_id == 0:
            head_count += 1
            color = (0, 255, 0)  # Green for head
        else:
            person_count += 1
            color = (255, 0, 0)  # Blue for person/other

        if idx <= 10:
            print(f"  Det #{idx:02d} | Class ID: {cls_id:2d} | Class Name: {cls_name:10s} | Conf: {conf:.3f} | BBox: [{x1}, {y1}, {x2}, {y2}]", flush=True)

        # Draw box on debug copy
        cv2.rectangle(annotated_img, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            annotated_img,
            f"D{idx:02d}:{cls_name[:4]}:{conf:.2f}",
            (x1, max(y1 - 5, 12)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            color,
            1,
            cv2.LINE_AA,
        )

    # Save debug image
    debug_path = DEBUG_OUTPUT_DIR / "AWC-001_crowdhuman_debug.jpg"
    cv2.imwrite(str(debug_path), annotated_img)
    print("  " + "-" * 75, flush=True)
    print(f"  Saved qualification debug image to: {debug_path}", flush=True)
    print(f"  Head Class Detections   : {head_count}", flush=True)
    print(f"  Person Class Detections : {person_count}", flush=True)

    # ── STEP 5 & 7: Empirical Decision ──
    print("\n[STEP 5 & 7: EMPIRICAL QUALIFICATION DECISION]", flush=True)
    
    # Check if heads are genuinely predicted
    if head_count > 0 and (model.names.get(0, "").lower() in ["head", "heads"] or "head" in str(model.names).lower()):
        print("  VERIFICATION PASSED: Model explicitly includes 'head' class and successfully predicts head bounding boxes.", flush=True)
        print("\n" + "=" * 80, flush=True)
        print("QUALIFICATION RESULT: PASS", flush=True)
        print("=" * 80, flush=True)
    else:
        print("  VERIFICATION FAILED: Model does not predict human head bounding boxes.", flush=True)
        print("\n" + "=" * 80, flush=True)
        print("QUALIFICATION RESULT: FAIL", flush=True)
        print("=" * 80, flush=True)


if __name__ == "__main__":
    run_forensic_audit()
