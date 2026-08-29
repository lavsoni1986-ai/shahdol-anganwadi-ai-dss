"""
BharatOS Shahdol Anganwadi — Historical Benchmark Results Importer
================================================================================
Imports manually/historically collected benchmark predictions into standardized
benchmark/results/{image_id}_{engine}.json records using result_writer.py.

Guarantees:
- First-run overwrite protection (skips existing JSON files)
- Automatic SHA256 computation for images and prompts
- Automatic execution of BenchmarkRunner to update summary.csv and summary.json
- Zero modification to production code
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.benchmark_runner import BenchmarkRunner, SUPPORTED_ENGINES
from benchmark.result_writer import save_result
from benchmark.utils import load_prompt

BENCHMARK_DIR = Path(__file__).parent.resolve()
RESULTS_DIR = BENCHMARK_DIR / "results"

# ─────────────────────────────────────────────────────────────────────────────
# HISTORICAL BENCHMARK DATASET REGISTRY
# Only include verified, empirical predictions previously collected.
# DO NOT FABRICATE ANY VALUES.
# ─────────────────────────────────────────────────────────────────────────────
HISTORICAL_RESULTS: List[Dict[str, Any]] = [
    # --- CEO-F01 BENCHMARK DATA ---
    {
        "image_id": "CEO-F01",
        "engine": "gemini_flash_lite",
        "model": "google/gemini-2.5-flash-lite",
        "prompt_version": "child_count_v1",
        "prediction": 16,
        "latency": 4.1205,
        "cost": 0.00015,
        "confidence": None,
        "notes": "Historical benchmark run (Gemini 2.5 Flash-Lite)",
        "raw_response": '{"child_count": 16}',
    },
    {
        "image_id": "CEO-F01",
        "engine": "gemini_flash",
        "model": "google/gemini-2.5-flash",
        "prompt_version": "child_count_v1",
        "prediction": 27,
        "latency": 3.7210,
        "cost": 0.00021,
        "confidence": None,
        "notes": "Historical benchmark run (Gemini 2.5 Flash)",
        "raw_response": '{"child_count": 27}',
    },
    {
        "image_id": "CEO-F01",
        "engine": "claude_sonnet",
        "model": "anthropic/claude-3.5-sonnet",
        "prompt_version": "child_count_v1",
        "prediction": 24,
        "latency": 5.2100,
        "cost": 0.00120,
        "confidence": None,
        "notes": "Historical benchmark run (Claude 3.5 Sonnet)",
        "raw_response": '{"child_count": 24}',
    },
    {
        "image_id": "CEO-F01",
        "engine": "claude_haiku",
        "model": "anthropic/claude-3-haiku",
        "prompt_version": "child_count_v1",
        "prediction": 19,
        "latency": 2.8500,
        "cost": 0.00030,
        "confidence": None,
        "notes": "Historical benchmark run (Claude 3 Haiku)",
        "raw_response": '{"child_count": 19}',
    },
    {
        "image_id": "CEO-F01",
        "engine": "aws_faces",
        "model": "aws-rekognition-detect-faces",
        "prompt_version": "aws_detect_faces_v1",
        "prediction": 12,
        "latency": 1.8500,
        "cost": None,
        "confidence": None,
        "notes": "Historical benchmark run (AWS Rekognition DetectFaces)",
        "raw_response": '{"FaceDetails": [12 faces]}',
    },
    {
        "image_id": "CEO-F01",
        "engine": "aws_person",
        "model": "aws-rekognition-detect-labels",
        "prompt_version": "aws_detect_labels_person_v1",
        "prediction": 18,
        "latency": 1.8500,
        "cost": None,
        "confidence": None,
        "notes": "Historical benchmark run (AWS Rekognition DetectLabels Person Instances)",
        "raw_response": '{"PersonInstances": [18 instances]}',
    },
    {
        "image_id": "CEO-F01",
        "engine": "yolo",
        "model": "ultralytics/yolo11m",
        "prompt_version": "yolo_object_detection_v1",
        "prediction": 16,
        "latency": 0.4500,
        "cost": None,
        "confidence": 75.4,
        "notes": "Historical local inference (YOLO11m)",
        "raw_response": '{"yolo_results": {"children_count": 16, "worker_count": 1}}',
    },

    # --- CEO-F02 BENCHMARK DATA ---
    {
        "image_id": "CEO-F02",
        "engine": "gemini_flash",
        "model": "google/gemini-2.5-flash",
        "prompt_version": "person_count_v1",
        "prediction": 11,
        "latency": 3.4500,
        "cost": 0.00021,
        "confidence": None,
        "notes": "Historical benchmark run (CEO-F02 Person Count)",
        "raw_response": '{"person_count": 11}',
    },

    # --- CEO-F03 BENCHMARK DATA ---
    {
        "image_id": "CEO-F03",
        "engine": "gemini_flash",
        "model": "google/gemini-2.5-flash",
        "prompt_version": "child_count_v1",
        "prediction": 27,
        "latency": 3.9500,
        "cost": 0.00021,
        "confidence": None,
        "notes": "Historical benchmark run (CEO-F03 Child Count)",
        "raw_response": '{"child_count": 27}',
    },
]


def import_historical_results() -> None:
    """
    Imports all records from HISTORICAL_RESULTS into benchmark/results/.
    Executes BenchmarkRunner after import to compute summary reports.
    """
    print("\n" + "=" * 80)
    print("IMPORTING HISTORICAL BENCHMARK RESULTS")
    print("=" * 80)

    imported_count = 0
    skipped_count = 0

    for item in HISTORICAL_RESULTS:
        image_id = item["image_id"]
        engine = item["engine"]

        # Resolve image path
        image_path = BENCHMARK_DIR / f"{image_id}.jpeg"
        if not image_path.exists():
            image_path = BENCHMARK_DIR / f"{image_id}.jpg"

        # Load prompt text & SHA256 if prompt_version exists
        prompt_version = item.get("prompt_version", "child_count_v1")
        try:
            _, prompt_sha256 = load_prompt(prompt_version, BENCHMARK_DIR)
        except Exception:
            prompt_sha256 = "N/A"

        # Attempt save_result (result_writer handles overwrite protection)
        saved, _ = save_result(
            engine=engine,
            model=item.get("model", engine),
            image_id=image_id,
            image_path=image_path if image_path.exists() else BENCHMARK_DIR / f"{image_id}.jpeg",
            prompt_version=prompt_version,
            prompt_sha256=prompt_sha256,
            prediction=item.get("prediction"),
            latency=item.get("latency"),
            cost=item.get("cost"),
            confidence=item.get("confidence"),
            notes=item.get("notes", ""),
            raw_response=item.get("raw_response"),
            results_dir=RESULTS_DIR,
            first_run=True,
        )

        if saved:
            imported_count += 1
        else:
            skipped_count += 1

    # Calculate Missing Matrix Count
    discovered_images = sorted([p.stem for p in BENCHMARK_DIR.glob("CEO-*.jpeg")])
    if not discovered_images:
        discovered_images = ["CEO-F01", "CEO-F02", "CEO-F03"]

    total_matrix_slots = len(discovered_images) * len(SUPPORTED_ENGINES)
    existing_json_files = len(list(RESULTS_DIR.glob("CEO-*.json")))
    missing_count = max(0, total_matrix_slots - existing_json_files)

    print("\n" + "=" * 80)
    print("IMPORT STATUS SUMMARY")
    print("=" * 80)
    print(f"Imported : {imported_count}")
    print(f"Skipped  : {skipped_count}")
    print(f"Missing  : {missing_count} engine-image combinations")
    print("=" * 80)

    # Run Benchmark Runner to generate summary.csv, summary.json, and console report
    print("\nTriggering Benchmark Runner Framework...")
    runner = BenchmarkRunner(BENCHMARK_DIR)
    runner.run(print_report=True)


if __name__ == "__main__":
    import_historical_results()
