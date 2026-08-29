# Shahdol Anganwadi Real Image Benchmark Dataset v1.0.0

## Purpose
This repository contains a controlled, frozen benchmark dataset of real Anganwadi field photographs (`AWC-001.jpeg` through `AWC-021.jpeg`) collected in District Shahdol. The dataset is designed for blind evaluation and architectural comparison of computer-vision child-counting pipelines.

## Dataset Structure
- `images/`: Original, un-modified real-field photographs (`AWC-001.jpeg` – `AWC-021.jpeg`).
- `ground_truth.xlsx`: Primary human ground-truth registry containing dual human counts (`Human A`, `Human B`), final verified child count (`Final Child GT`), adult count (`Adult GT`), total person count, and qualitative observations/remarks.
- `dataset_manifest.json`: Cryptographic integrity manifest containing image metadata, pixel dimensions, file sizes, and SHA-256 hashes for all images and the ground-truth registry (`frozen: true`).
- `ground_truth.json`: Machine-readable ground-truth snapshot used exclusively for post-prediction evaluation metrics calculation.
- `validate_dataset.py`: Reusable, zero-dependency validation script for verifying image readability, 1:1 mapping, and SHA-256 hash integrity.

## Strict Experimental Rules
1. **Blind Evaluation Isolation**: Ground-truth values (`ground_truth.xlsx` or `ground_truth.json`) MUST NEVER be exposed to or loaded by AI model inference scripts before or during prediction generation.
2. **Original Image Protection**: Benchmark images in `images/` must remain untouched and un-modified.
3. **Evaluation Protocol**:
   - **Inference Phase**: Image → Vision Pipeline → Prediction Record JSON.
   - **Evaluation Phase**: Prediction Record JSON + `ground_truth.json` → Benchmark Metrics (MAE, RMSE, Exact Match %, ±1 Accuracy %).

## Privacy & Git Notice
This is an internal controlled benchmark dataset. Because photographs contain real children in field Anganwadi centers, raw images (`images/`), Excel registries (`ground_truth.xlsx`), and ground-truth JSON snapshots (`ground_truth.json`) are protected by `.gitignore` rules and must not be committed to public repositories.
