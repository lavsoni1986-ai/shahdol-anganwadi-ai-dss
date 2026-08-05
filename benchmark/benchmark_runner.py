"""
BharatOS Shahdol Anganwadi — Vision Benchmark Framework
================================================================================
Production-quality offline benchmark runner and metrics analyzer.

Architecture:
- GroundTruthLoader: Loads optional ground truth annotations (benchmark/ground_truth.json).
- ResultFileLoader: Discovers and parses per-model result JSON files from benchmark/results/.
- MetricsCalculator: Computes MAE, RMSE, Exact Accuracy, ±1 Accuracy, Mean Latency.
- ReportGenerator: Renders console summaries and exports CSV / JSON reports.
- BenchmarkRunner: Orchestrator managing image discovery, model evaluation, and reporting.

DO NOT MODIFY PRODUCTION CODE. THIS IS AN OFFLINE BENCHMARK UTILITY.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
import csv
import json
import math
from pathlib import Path
from typing import Any, Optional

# Supported Engine Identifiers (Extensible for future engines)
SUPPORTED_ENGINES = [
    "yolo",
    "aws_faces",
    "aws_person",
    "gemini_flash_lite",
    "gemini_flash",
    "claude_sonnet",
    "claude_haiku",
]

# Future Extensible Engines (Defined for seamless registry expansion)
FUTURE_EXTENSIBLE_ENGINES = [
    "google_vision",
    "azure_vision",
    "openai_vision",
    "grounding_dino",
    "rt_detr",
    "count_gd",
]


@dataclass
class ModelResult:
    """Standardized record for an individual model's evaluation on a single image."""
    prediction: Optional[int] = None
    latency: Optional[float] = None
    cost: Optional[float] = None
    confidence: Optional[Any] = None
    notes: Optional[str] = None
    raw_response: Optional[Any] = None
    timestamp: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelResult":
        return cls(
            prediction=data.get("prediction") or data.get("child_count") or data.get("person_count") or data.get("count"),
            latency=data.get("latency"),
            cost=data.get("cost"),
            confidence=data.get("confidence"),
            notes=data.get("notes"),
            raw_response=data.get("raw_response"),
            timestamp=data.get("timestamp"),
        )


@dataclass
class ImageBenchmarkRecord:
    """Master benchmark record for a single image across all engines."""
    image_id: str
    image_path: Path
    ground_truth: Optional[int] = None
    models: dict[str, Optional[ModelResult]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_id": self.image_id,
            "ground_truth": self.ground_truth,
            "models": {
                engine_id: (asdict(res) if res else None)
                for engine_id, res in self.models.items()
            },
        }


@dataclass
class EngineMetrics:
    """Aggregated statistical performance metrics for a single engine."""
    engine_id: str
    total_images: int = 0
    evaluated_count: int = 0
    gt_evaluated_count: int = 0
    mae: Optional[float] = None
    rmse: Optional[float] = None
    exact_accuracy: Optional[float] = None
    pm1_accuracy: Optional[float] = None
    avg_latency: Optional[float] = None


class GroundTruthLoader:
    """Loads ground truth count annotations from benchmark/ground_truth.json if present."""

    @staticmethod
    def load_ground_truth(base_dir: Path) -> dict[str, int]:
        gt_file = base_dir / "ground_truth.json"
        if not gt_file.exists():
            return {}
        try:
            with open(gt_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {str(k): int(v) for k, v in data.items() if v is not None}
        except Exception:
            return {}


class ResultFileLoader:
    """
    Parses result JSON files in benchmark/results/.
    Supports both individual per-model files (e.g., CEO-F01_gemini_flash.json, CEO-F01_aws.json)
    and combined multi-model result JSONs.
    """

    @staticmethod
    def load_image_results(results_dir: Path, image_id: str, available_engines: list[str]) -> dict[str, Optional[ModelResult]]:
        model_results: dict[str, Optional[ModelResult]] = {eng: None for eng in available_engines}

        if not results_dir.exists():
            return model_results

        # 1. Search for specific files matching image_id (e.g. CEO-F01_*.json)
        for json_path in results_dir.glob(f"{image_id}_*.json"):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Check if it's AWS combined result
                if "aws" in json_path.name.lower():
                    if "faces" in data:
                        model_results["aws_faces"] = ModelResult.from_dict(data["faces"])
                    if "person" in data:
                        model_results["aws_person"] = ModelResult.from_dict(data["person"])
                    continue

                # Generic single engine result
                for eng_id in available_engines:
                    if eng_id in json_path.name.lower():
                        model_results[eng_id] = ModelResult.from_dict(data)
                        break
            except Exception:
                pass

        # 2. Check for combined master file (e.g., CEO-F01.json or results.json)
        master_path = results_dir / f"{image_id}.json"
        if master_path.exists():
            try:
                with open(master_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                models_dict = data.get("models", {})
                for eng_id, m_data in models_dict.items():
                    if m_data and eng_id in model_results:
                        model_results[eng_id] = ModelResult.from_dict(m_data)
            except Exception:
                pass

        return model_results


class MetricsCalculator:
    """Computes statistical accuracy and latency metrics across benchmark records."""

    @staticmethod
    def compute_engine_metrics(records: list[ImageBenchmarkRecord], engine_id: str) -> EngineMetrics:
        metrics = EngineMetrics(engine_id=engine_id, total_images=len(records))

        predictions: list[int] = []
        ground_truths: list[int] = []
        latencies: list[float] = []

        for r in records:
            res = r.models.get(engine_id)
            if res and res.prediction is not None:
                metrics.evaluated_count += 1
                if res.latency is not None:
                    latencies.append(res.latency)

                if r.ground_truth is not None:
                    metrics.gt_evaluated_count += 1
                    predictions.append(res.prediction)
                    ground_truths.append(r.ground_truth)

        # Average Latency
        if latencies:
            metrics.avg_latency = round(sum(latencies) / len(latencies), 4)

        # Accuracy & Error Metrics (Requires Ground Truth)
        if predictions and len(predictions) == len(ground_truths):
            n = len(predictions)
            abs_errors = [abs(p - gt) for p, gt in zip(predictions, ground_truths)]
            sq_errors = [(p - gt) ** 2 for p, gt in zip(predictions, ground_truths)]
            exact_matches = [1 if p == gt else 0 for p, gt in zip(predictions, ground_truths)]
            pm1_matches = [1 if abs(p - gt) <= 1 else 0 for p, gt in zip(predictions, ground_truths)]

            metrics.mae = round(sum(abs_errors) / n, 2)
            metrics.rmse = round(math.sqrt(sum(sq_errors) / n), 2)
            metrics.exact_accuracy = round((sum(exact_matches) / n) * 100, 1)
            metrics.pm1_accuracy = round((sum(pm1_matches) / n) * 100, 1)

        return metrics


class ReportGenerator:
    """Generates console table reports, CSV summary, and JSON summary outputs."""

    @staticmethod
    def render_console_report(
        records: list[ImageBenchmarkRecord],
        engine_metrics: list[EngineMetrics],
        engines: list[str],
    ) -> None:
        print("\n" + "=" * 110)
        print("BHARATOS SHAHDOL ANGANWADI VISION BENCHMARK FRAMEWORK REPORT")
        print("=" * 110)

        # 1. Per-Image Predictions Table
        header_cols = ["IMAGE", "GT"] + [eng.upper().replace("_", " ") for eng in engines]
        header_str = f"{header_cols[0]:<12} | {header_cols[1]:<6} | " + " | ".join(f"{h:<14}" for h in header_cols[2:])
        print(header_str)
        print("-" * len(header_str))

        for r in records:
            gt_str = str(r.ground_truth) if r.ground_truth is not None else "N/A"
            row_cells = [f"{r.image_id:<12}", f"{gt_str:<6}"]
            for eng in engines:
                res = r.models.get(eng)
                if res and res.prediction is not None:
                    val_str = str(res.prediction)
                    if res.latency is not None:
                        val_str += f" ({res.latency:.1f}s)"
                else:
                    val_str = "MISSING"
                row_cells.append(f"{val_str:<14}")
            print(" | ".join(row_cells))

        print("=" * 110)
        print("AGGREGATED BENCHMARK METRICS SUMMARY")
        print("=" * 110)
        summary_header = f"{'ENGINE':<20} | {'EVAL':<6} | {'MAE':<6} | {'RMSE':<6} | {'EXACT ACC %':<12} | {'±1 ACC %':<10} | {'AVG LATENCY':<12}"
        print(summary_header)
        print("-" * len(summary_header))

        for m in engine_metrics:
            eval_str = f"{m.evaluated_count}/{m.total_images}"
            mae_str = f"{m.mae:.2f}" if m.mae is not None else "N/A"
            rmse_str = f"{m.rmse:.2f}" if m.rmse is not None else "N/A"
            exact_str = f"{m.exact_accuracy:.1f}%" if m.exact_accuracy is not None else "N/A"
            pm1_str = f"{m.pm1_accuracy:.1f}%" if m.pm1_accuracy is not None else "N/A"
            lat_str = f"{m.avg_latency:.3f}s" if m.avg_latency is not None else "N/A"

            print(f"{m.engine_id:<20} | {eval_str:<6} | {mae_str:<6} | {rmse_str:<6} | {exact_str:<12} | {pm1_str:<10} | {lat_str:<12}")

        print("=" * 110 + "\n")

    @staticmethod
    def export_reports(
        results_dir: Path,
        records: list[ImageBenchmarkRecord],
        engine_metrics: list[EngineMetrics],
        engines: list[str],
    ) -> tuple[Path, Path]:
        results_dir.mkdir(parents=True, exist_ok=True)
        csv_path = results_dir / "summary.csv"
        json_path = results_dir / "summary.json"

        # 1. Export CSV
        with open(csv_path, "w", newline="", encoding="utf-8") as f_csv:
            writer = csv.writer(f_csv)
            headers = ["image_id", "ground_truth"]
            for eng in engines:
                headers.extend([f"{eng}_pred", f"{eng}_latency", f"{eng}_cost"])
            writer.writerow(headers)

            for r in records:
                row = [r.image_id, r.ground_truth if r.ground_truth is not None else ""]
                for eng in engines:
                    res = r.models.get(eng)
                    if res:
                        row.extend([res.prediction if res.prediction is not None else "", res.latency or "", res.cost or ""])
                    else:
                        row.extend(["MISSING", "", ""])
                writer.writerow(row)

        # 2. Export JSON
        summary_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "engines_supported": engines,
            "image_count": len(records),
            "records": [r.to_dict() for r in records],
            "metrics": [asdict(m) for m in engine_metrics],
        }

        with open(json_path, "w", encoding="utf-8") as f_json:
            json.dump(summary_data, f_json, indent=2)

        return csv_path, json_path


class BenchmarkRunner:
    """
    Core orchestrator that discovers input images, loads offline results,
    computes evaluation metrics, and triggers report exports.
    """

    def __init__(self, benchmark_dir: Optional[Path] = None):
        self.benchmark_dir = (benchmark_dir or Path(__file__).parent).resolve()
        self.results_dir = self.benchmark_dir / "results"
        self.engines = SUPPORTED_ENGINES

    def discover_images(self) -> list[Path]:
        """Discovers all CEO-*.jpeg benchmark images sorted alphabetically."""
        images = sorted(list(self.benchmark_dir.glob("CEO-*.jpeg")))
        if not images:
            images = sorted(list(self.benchmark_dir.glob("CEO-*.jpg")))
        return images

    def run(self, print_report: bool = True) -> tuple[list[ImageBenchmarkRecord], list[EngineMetrics]]:
        image_files = self.discover_images()
        gt_map = GroundTruthLoader.load_ground_truth(self.benchmark_dir)

        records: list[ImageBenchmarkRecord] = []
        for img_path in image_files:
            img_id = img_path.stem  # e.g., CEO-F01
            gt = gt_map.get(img_id)
            model_results = ResultFileLoader.load_image_results(self.results_dir, img_id, self.engines)
            record = ImageBenchmarkRecord(
                image_id=img_id,
                image_path=img_path,
                ground_truth=gt,
                models=model_results,
            )
            records.append(record)

        # Compute Engine Metrics
        metrics_list: list[EngineMetrics] = [
            MetricsCalculator.compute_engine_metrics(records, eng_id)
            for eng_id in self.engines
        ]

        if print_report:
            ReportGenerator.render_console_report(records, metrics_list, self.engines)

        # Export Reports
        ReportGenerator.export_reports(self.results_dir, records, metrics_list, self.engines)

        return records, metrics_list


if __name__ == "__main__":
    runner = BenchmarkRunner()
    # Execute runner to render report from existing offline JSON files
    runner.run(print_report=True)
