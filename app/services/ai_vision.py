# app/services/ai_vision.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP — Day 4
# Computer Vision & AI Validation Pipeline
# =====================================================================

import asyncio
import io
import random
from typing import Optional

import cv2
import imagehash
import numpy as np
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session_maker
from app.models import DailySubmission, SubmissionStatus
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Constants
BLUR_THRESHOLD = 50.0
HASH_HAMMING_DISTANCE_THRESHOLD = 5


def _download_or_mock_image(media_id: Optional[str]) -> Image.Image:
    """
    In production, this would download the image using the WhatsApp Cloud API.
    For this MVP/Pilot, we mock a valid PIL image if media_id is provided,
    or generate a noisy image to test blur detection.
    """
    # Create a dummy image (e.g., 640x480)
    img_array = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    
    # If media_id starts with 'blur', artificially blur it to test the pipeline
    if media_id and media_id.startswith("blur"):
        img_array = cv2.GaussianBlur(img_array, (15, 15), 0)
        
    # If media_id starts with 'dup', use a fixed seed to generate the exact same image
    if media_id and media_id.startswith("dup"):
        np.random.seed(42)
        img_array = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        np.random.seed(None)

    return Image.fromarray(img_array)


def check_image_blur(pil_img: Image.Image) -> tuple[bool, float]:
    """
    Computes Laplacian Variance of the image to detect blur.
    Returns (is_blur, variance_score)
    """
    # Convert PIL Image to OpenCV format (numpy array)
    open_cv_image = np.array(pil_img)
    # Convert RGB to BGR (OpenCV format)
    open_cv_image = open_cv_image[:, :, ::-1].copy()

    gray = cv2.cvtColor(open_cv_image, cv2.COLOR_BGR2GRAY)
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()

    is_blur = variance < BLUR_THRESHOLD
    return is_blur, variance


async def check_duplicate_hash(
    db: AsyncSession, 
    pil_img: Image.Image, 
    awc_id: str, 
    current_submission_id: str
) -> tuple[bool, str]:
    """
    Computes Perceptual Hash (pHash) and compares against past submissions 
    for the same AWC.
    Returns (is_duplicate, computed_hash)
    """
    # Compute perceptual hash
    computed_hash = str(imagehash.phash(pil_img))

    if not awc_id:
        return False, computed_hash

    # Fetch recent hashes for this AWC (e.g., past 7 days, but here we just check recent ones)
    result = await db.execute(
        select(DailySubmission.image_hash)
        .where(
            DailySubmission.awc_id == awc_id,
            DailySubmission.submission_id != current_submission_id,
            DailySubmission.image_hash.is_not(None)
        )
        .order_by(DailySubmission.created_at.desc())
        .limit(20)
    )
    past_hashes = result.scalars().all()

    current_hash_obj = imagehash.hex_to_hash(computed_hash)

    for past_hash_str in past_hashes:
        try:
            past_hash_obj = imagehash.hex_to_hash(past_hash_str)
            distance = current_hash_obj - past_hash_obj
            if distance <= HASH_HAMMING_DISTANCE_THRESHOLD:
                return True, computed_hash
        except Exception as e:
            logger.warning("hash_compare_error", error=str(e), hash=past_hash_str)

    return False, computed_hash


def estimate_child_count_and_meal(pil_img: Image.Image) -> tuple[int, bool, float]:
    """
    Placeholder for actual ML object detection (e.g., YOLO/MobileNet).
    For MVP, uses heuristics or random sampling to simulate AI results.
    """
    # Mocking detection results
    estimated_child_count = random.randint(12, 35)
    meal_detected = random.choice([True, True, True, False]) # 75% chance meal detected
    confidence_score = round(random.uniform(85.0, 98.5), 1)

    return estimated_child_count, meal_detected, confidence_score


async def process_image_ai_pipeline(submission_id: str):
    """
    Unified AI Pipeline triggered as a background task.
    Fetches the submission, downloads/mocks image, runs ML checks, 
    and updates DB status.
    NON-BLOCKING: Will not fail the HTTP request if it crashes.
    """
    logger.info("ai_pipeline_started", submission_id=submission_id)
    
    # Run in a new DB session since this is a background task detached from the request cycle
    async with async_session_maker() as db:
        try:
            # 1. Fetch submission
            result = await db.execute(
                select(DailySubmission).where(DailySubmission.submission_id == submission_id)
            )
            submission = result.scalar_one_or_none()
            if not submission:
                logger.error("ai_pipeline_error", msg="Submission not found", submission_id=submission_id)
                return

            if submission.status != SubmissionStatus.RECEIVED:
                logger.info("ai_pipeline_skipped", msg="Already processed", submission_id=submission_id)
                return

            submission.status = SubmissionStatus.PROCESSING
            await db.commit()

            # 2. Get Image
            # Using raw_media_id for mock testing, fallback to generic random image
            pil_img = _download_or_mock_image(submission.raw_media_id)

            # 3. Blur Detection
            is_blur, blur_variance = check_image_blur(pil_img)
            
            # 4. Duplicate Detection (pHash)
            awc_id = submission.awc_id or "UNKNOWN"
            is_duplicate, computed_hash = await check_duplicate_hash(db, pil_img, awc_id, submission_id)
            submission.image_hash = computed_hash

            # 5. Object Detection (Child/Meal)
            child_count, meal_detected, confidence = estimate_child_count_and_meal(pil_img)

            # 6. Synthesize AI Result
            flag_reasons = []
            if is_blur:
                flag_reasons.append("BLUR_IMAGE")
            if is_duplicate:
                flag_reasons.append("DUPLICATE_IMAGE")
            if not meal_detected:
                flag_reasons.append("NO_MEAL_DETECTED")

            # Update DB Model
            if flag_reasons:
                submission.status = SubmissionStatus.FLAGGED
                submission.flag_reason = ", ".join(flag_reasons)
                logger.info("ai_pipeline_flagged", submission_id=submission_id, reasons=submission.flag_reason)
            else:
                submission.status = SubmissionStatus.PROCESSED
                logger.info("ai_pipeline_success", submission_id=submission_id)

            # Format AI Score Pill (e.g. "92% (18 बच्चे)")
            submission.ai_score = f"{confidence}% ({child_count} बच्चे)"

            await db.commit()
            logger.info(
                "ai_pipeline_completed", 
                submission_id=submission_id, 
                status=submission.status,
                blur_var=round(blur_variance, 2),
                children=child_count
            )

        except Exception as e:
            logger.error("ai_pipeline_crashed", submission_id=submission_id, error=str(e), exc_info=True)
            # Revert to RECEIVED on crash so it can be re-tried or manually reviewed
            await db.rollback()
            try:
                result = await db.execute(select(DailySubmission).where(DailySubmission.submission_id == submission_id))
                sub = result.scalar_one_or_none()
                if sub:
                    sub.status = SubmissionStatus.RECEIVED
                    await db.commit()
            except:
                pass
