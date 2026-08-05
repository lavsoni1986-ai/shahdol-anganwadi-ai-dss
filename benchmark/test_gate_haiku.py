"""
Anganwadi Gate-0 Benchmark — Claude 3 Haiku
================================================================================
Evaluates whether GATE-TEST-01.jpeg is a valid Anganwadi context image using
Claude 3 Haiku (anthropic/claude-3-haiku).

DO NOT MODIFY PRODUCTION CODE.
"""

from gate_runner_utils import run_gate_model_benchmark

ENGINE_ID = "claude_haiku"
MODEL_ID = "anthropic/claude-haiku-4.5"

if __name__ == "__main__":
    run_gate_model_benchmark(engine_id=ENGINE_ID, model_id=MODEL_ID)
