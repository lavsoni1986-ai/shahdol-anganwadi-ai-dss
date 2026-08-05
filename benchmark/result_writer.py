import json
from pathlib import Path
from typing import Any, Optional, Union
from benchmark.utils import compute_sha256, generate_run_id, utc_timestamp


def save_result(
    engine: str,
    model: str,
    image_id: str,
    image_path: Union[Path, str],
    prompt_version: str,
    prompt_sha256: str,
    prediction: Optional[int],
    latency: Optional[float],
    cost: Optional[float] = None,
    confidence: Optional[Any] = None,
    notes: str = "",
    raw_response: Any = None,
    results_dir: Optional[Union[Path, str]] = None,
    first_run: bool = True,
    benchmark_version: str = "1.0.0",
) -> tuple[bool, Path]:
    """
    Saves standardized benchmark result JSON to benchmark/results/{image_id}_{engine}.json.
    
    FIRST-RUN OVERWRITE PROTECTION:
    If the target JSON file already exists on disk, the write is aborted and False is returned.
    This preserves the empirical integrity of the first blind execution.
    """
    if results_dir is None:
        target_dir = (Path(__file__).parent / "results").resolve()
    else:
        target_dir = Path(results_dir).resolve()

    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{image_id}_{engine}.json"
    target_path = target_dir / filename

    # FIRST-RUN OVERWRITE PROTECTION
    if target_path.exists():
        print(f"\n[OVERWRITE PROTECTION] Benchmark result already exists: {target_path}")
        print("Skipping write to preserve first-run empirical integrity.")
        return False, target_path

    # Compute Image SHA256
    image_sha256 = compute_sha256(image_path)

    # Format raw_response as string or dict
    if isinstance(raw_response, (dict, list)):
        raw_resp_str = json.dumps(raw_response, ensure_ascii=False)
    elif raw_response is not None:
        raw_resp_str = str(raw_response)
    else:
        raw_resp_str = ""

    result_data = {
        "benchmark_version": benchmark_version,
        "engine": engine,
        "model": model,
        "image_id": image_id,
        "image_sha256": image_sha256,
        "prompt_version": prompt_version,
        "prompt_sha256": prompt_sha256,
        "run_id": generate_run_id(),
        "first_run": first_run,
        "prediction": prediction,
        "latency": round(latency, 4) if latency is not None else None,
        "cost": cost,
        "confidence": confidence,
        "notes": notes,
        "raw_response": raw_resp_str,
        "timestamp": utc_timestamp(),
    }

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, indent=2, ensure_ascii=False)

    print(f"\n[RESULT WRITTEN] Saved benchmark result to: {target_path}")
    return True, target_path
