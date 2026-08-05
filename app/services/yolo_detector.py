import time
import os
import pathlib
import uuid
from typing import Optional, Dict, Any, List
import cv2
import urllib.request
import logging

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Constants
MODEL_FILENAME = "yolo11m.pt"
MODEL_URL = f"https://github.com/ultralytics/assets/releases/download/v8.3.0/{MODEL_FILENAME}"
MODEL_DIR = pathlib.Path("app/models")
PROCESSED_DIR = pathlib.Path("data/processed")

# Ensure directories exist
MODEL_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

class YoloDetectorService:
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(YoloDetectorService, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initializes the YOLO model as a singleton."""
        if YOLO is None:
            logger.warning("ultralytics_not_installed", msg="YOLO11 is not available.")
            return

        model_path = MODEL_DIR / MODEL_FILENAME
        
        # Download model if not exists
        if not model_path.exists():
            logger.info("downloading_yolo_model", url=MODEL_URL, path=str(model_path))
            try:
                urllib.request.urlretrieve(MODEL_URL, str(model_path))
                logger.info("yolo_model_downloaded_successfully")
            except Exception as e:
                logger.error("yolo_model_download_failed", error=str(e))
                return

        logger.info("yolo_model_loading", model_path=str(model_path))
        start_time = time.time()
        try:
            import torch
            if hasattr(torch, "set_num_threads"):
                torch.set_num_threads(min(4, os.cpu_count() or 4))
            self._model = YOLO(str(model_path))
            logger.info("yolo_model_loaded", processing_time_ms=int((time.time() - start_time) * 1000))
        except Exception as e:
            logger.error("yolo_model_load_failed", error=str(e))
            self._model = None

    def _calculate_adult_probability(self, box, img_height, img_width):
        """
        Heuristic to estimate if a person is an adult (worker) or child.
        Based on: height, position, posture (aspect ratio).
        Returns a score from 0.0 to 1.0.
        """
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        width = x2 - x1
        height = y2 - y1
        
        rel_height = height / img_height
        aspect_ratio = height / (width + 1e-6) # > 1.0 usually means standing
        
        score = 0.0
        
        # Height rule: Adults take up more vertical space
        if rel_height > 0.4:
            score += 0.4
        elif rel_height > 0.25:
            score += 0.2
            
        # Posture rule: Standing (taller than wide) is more likely adult
        if aspect_ratio > 1.5:
            score += 0.3
        elif aspect_ratio > 1.0:
            score += 0.1
            
        # Overall area
        area = (width * height) / (img_width * img_height)
        if area > 0.15:
            score += 0.3
        elif area > 0.05:
            score += 0.1
            
        return min(score, 0.99)

    def detect_objects(self, image_path: str) -> Optional[Dict[str, Any]]:
        """
        Runs YOLO inference on the image and uses Person Analyzer logic.
        """
        if not self._model:
            logger.error("yolo_model_unavailable")
            return None
            
        if not os.path.exists(image_path):
            logger.error("image_not_found_for_yolo", path=image_path)
            return None

        logger.info("yolo_inference_started", image_path=image_path)
        start_time = time.time()
        
        try:
            # Read image to get dimensions
            img = cv2.imread(image_path)
            if img is None:
                return None
            img_h, img_w = img.shape[:2]
            
            # Run inference
            results = self._model(img, verbose=False)
            result = results[0]
            
            # Find all persons (class 0 in COCO)
            persons = []
            boxes = result.boxes
            for box in boxes:
                cls_id = int(box.cls[0].item())
                if cls_id == 0:  # person
                    conf = float(box.conf[0].item())
                    adult_prob = self._calculate_adult_probability(box, img_h, img_w)
                    persons.append({
                        "box": box,
                        "conf": conf,
                        "adult_prob": adult_prob,
                        "coords": box.xyxy[0].tolist()
                    })

            # Person Analyzer: Highest adult probability > 0.35 becomes worker
            worker_idx = -1
            max_prob = 0.35 # Threshold
            
            for i, p in enumerate(persons):
                if p["adult_prob"] > max_prob:
                    max_prob = p["adult_prob"]
                    worker_idx = i
                    
            worker_count = 0
            children_count = 0
            
            # Assign classes and draw visualization
            annotated_img = img.copy()
            
            for i, p in enumerate(persons):
                x1, y1, x2, y2 = map(int, p["coords"])
                conf = p["conf"]
                
                if i == worker_idx:
                    worker_count += 1
                    label = f"Worker {conf:.2f}"
                    color = (0, 255, 0) # Green for worker
                    logger.info("worker_detected", conf=conf)
                else:
                    children_count += 1
                    label = f"Child {conf:.2f}"
                    color = (255, 0, 0) # Blue for child
                    logger.info("children_detected", index=children_count, conf=conf)
                    
                cv2.rectangle(annotated_img, (x1, y1), (x2, y2), color, 2)
                cv2.putText(annotated_img, label, (x1, max(y1 - 10, 0)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            # Save visualized image
            processed_filename = f"{uuid.uuid4().hex[:8]}_detected.jpg"
            processed_path = PROCESSED_DIR / processed_filename
            cv2.imwrite(str(processed_path), annotated_img)
            
            # Confidence (average of persons, or 0 if none)
            avg_conf = sum(p["conf"] for p in persons) / len(persons) if persons else 0.0
            
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.info("yolo_inference_completed", processing_time_ms=processing_time_ms, children=children_count, worker=worker_count)
            
            return {
                "children_count": children_count,
                "worker_count": worker_count,
                "plate_count": None, # Do not fake plate detection
                "confidence": round(avg_conf * 100, 1),
                "processing_time_ms": processing_time_ms,
                "visualized_image_path": str(processed_path),
                "persons_detected": len(persons)
            }
            
        except Exception as e:
            logger.error("yolo_inference_exception", error=str(e))
            return None

# Singleton instance
yolo_detector = YoloDetectorService()
