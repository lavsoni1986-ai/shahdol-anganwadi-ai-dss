"""
Anganwadi Gate-0 Benchmark — Google Gemini 2.5 Flash-Lite
================================================================================
Evaluates whether GATE-TEST-01.jpeg is a valid Anganwadi context image using
Google Gemini 2.5 Flash-Lite (google/gemini-2.5-flash-lite).

DO NOT MODIFY PRODUCTION CODE.
"""

from gate_runner_utils import run_gate_model_benchmark

ENGINE_ID = "gemini_flash_lite"
MODEL_ID = "google/gemini-2.5-flash-lite"

if __name__ == "__main__":
    run_gate_model_benchmark(engine_id=ENGINE_ID, model_id=MODEL_ID)
