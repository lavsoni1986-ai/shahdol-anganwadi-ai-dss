import os
import shutil
import json
from app.services.yolo_detector import yolo_detector

def verify_yolo11m():
    image_path = r"data/uploads/2ffe02b1-4014-4eb3-9de5-718714480ddf.jpg"
    
    print("Testing YoloDetectorService Singleton...")
    result = yolo_detector.detect_objects(image_path)
    
    if result:
        print("\n--- INFERENCE SUCCESS ---")
        print(f"Persons Detected: {result['persons_detected']}")
        print(f"Children Count: {result['children_count']}")
        print(f"Worker Count: {result['worker_count']}")
        print(f"Average Confidence: {result['confidence']}%")
        print(f"Inference Time: {result['processing_time_ms']} ms")
        
        # Rename the output file
        old_path = result['visualized_image_path']
        new_path = "data/processed/pongri_yolo11m_final.jpg"
        if os.path.exists(old_path):
            shutil.copy(old_path, new_path)
            print(f"Annotated Image Path: {new_path}")
        else:
            print("Annotated image not found!")
    else:
        print("\n--- INFERENCE FAILED ---")

if __name__ == "__main__":
    verify_yolo11m()
