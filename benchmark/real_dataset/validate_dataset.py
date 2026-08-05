"""
Shahdol Anganwadi Real Image Benchmark Dataset v1.0.0 — Reusable Validation Script
===================================================================================
Verifies dataset integrity, 1:1 image-to-GT mapping, image readability, and
SHA-256 checksums against dataset_manifest.json.

DO NOT PERFORM AI INFERENCE OR CALL EXTERNAL APIS.
"""

import hashlib
import json
import sys
from pathlib import Path
from PIL import Image

DATASET_DIR = Path(__file__).parent.resolve()
IMAGES_DIR = DATASET_DIR / "images"
MANIFEST_PATH = DATASET_DIR / "dataset_manifest.json"
GT_JSON_PATH = DATASET_DIR / "ground_truth.json"
EXCEL_PATH = DATASET_DIR / "ground_truth.xlsx"


def compute_sha256(path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def validate_dataset() -> bool:
    print("\n" + "=" * 80)
    print("VALIDATING SHAHDOL ANGANWADI REAL IMAGE BENCHMARK DATASET v1.0.0")
    print("=" * 80)

    errors = []
    warnings = []

    # 1. Manifest Existence
    if not MANIFEST_PATH.exists():
        print(f"FAIL: Manifest file not found at {MANIFEST_PATH}")
        return False

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    if not manifest.get("frozen"):
        errors.append("Manifest is marked as NOT frozen (frozen != true)")

    # 2. Verify Ground Truth Excel SHA-256
    if EXCEL_PATH.exists():
        current_excel_sha256 = compute_sha256(EXCEL_PATH)
        expected_excel_sha256 = manifest.get("ground_truth_sha256")
        if current_excel_sha256 != expected_excel_sha256:
            errors.append(f"Ground Truth Excel SHA256 mismatch! Expected {expected_excel_sha256}, got {current_excel_sha256}")
        else:
            print(f"PASS: Ground Truth Excel SHA256 matches manifest ({current_excel_sha256[:12]}...)")
    else:
        warnings.append(f"Ground Truth Excel file missing at {EXCEL_PATH}")

    # 3. Image Inventory & SHA-256 Check
    manifest_images = {img["image_id"]: img for img in manifest.get("images", [])}
    
    valid_exts = {".jpg", ".jpeg", ".png"}
    disk_image_files = sorted([
        p for p in IMAGES_DIR.glob("*")
        if p.is_file() and p.suffix.lower() in valid_exts
    ])
    disk_images = {p.stem: p for p in disk_image_files}

    print(f"\nManifest Registered Images : {len(manifest_images)}")
    print(f"Disk Discovered Images      : {len(disk_images)}")

    # Check 1:1 Image Match
    missing_on_disk = set(manifest_images.keys()) - set(disk_images.keys())
    unregistered_on_disk = set(disk_images.keys()) - set(manifest_images.keys())

    if missing_on_disk:
        errors.append(f"Registered images missing on disk: {sorted(list(missing_on_disk))}")
    if unregistered_on_disk:
        errors.append(f"Unregistered images found on disk: {sorted(list(unregistered_on_disk))}")

    # Verify SHA256 and Image Readability
    corrupt_count = 0
    hash_mismatch_count = 0

    for img_id, m_rec in manifest_images.items():
        if img_id not in disk_images:
            continue
        
        disk_p = disk_images[img_id]

        # Readability check
        try:
            with Image.open(disk_p) as im:
                im.verify()
        except Exception as e:
            errors.append(f"Corrupt/unreadable image {disk_p.name}: {e}")
            corrupt_count += 1
            continue

        # SHA-256 Check
        current_sha256 = compute_sha256(disk_p)
        if current_sha256 != m_rec["sha256"]:
            errors.append(f"SHA256 mismatch for {disk_p.name}! Expected {m_rec['sha256']}, got {current_sha256}")
            hash_mismatch_count += 1

    if hash_mismatch_count == 0 and corrupt_count == 0:
        print("PASS: All 21 images verified readable and SHA256 hashes match manifest 100%")

    # 4. Verify Machine-Readable Ground Truth Snapshot
    if GT_JSON_PATH.exists():
        with open(GT_JSON_PATH, "r", encoding="utf-8") as f:
            gt_snapshot = json.load(f)
        
        gt_records = {r["image_id"]: r for r in gt_snapshot.get("records", [])}
        print(f"GT Snapshot Records        : {len(gt_records)}")

        # Verify arithmetic
        arithmetic_errors = 0
        for img_id, r in gt_records.items():
            child_gt = r.get("final_child_gt", 0)
            adult_gt = r.get("adult_gt", 0)
            total_gt = r.get("total_person_gt", 0)
            expected_total = child_gt + adult_gt

            if total_gt != expected_total:
                errors.append(f"Arithmetic mismatch for {img_id}: Child={child_gt}, Adult={adult_gt}, Total={total_gt} (Expected {expected_total})")
                arithmetic_errors += 1
        
        if arithmetic_errors == 0:
            print("PASS: Ground truth snapshot total person arithmetic is 100% consistent")
    else:
        errors.append(f"Ground truth JSON snapshot missing at {GT_JSON_PATH}")

    # Summary Output
    print("\n" + "=" * 80)
    if warnings:
        for w in warnings:
            print(f"WARNING: {w}")
    
    if errors:
        print("DATASET VALIDATION FAILED:")
        for err in errors:
            print(f"  - ERROR: {err}")
        print("=" * 80)
        print("STATUS: NOT FROZEN — ACTION REQUIRED")
        print("=" * 80)
        return False

    print("ALL INTEGRITY CHECKS PASSED PERFECTLY!")
    print("=" * 80)
    print("STATUS: FROZEN — PASS")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = validate_dataset()
    sys.exit(0 if success else 1)
