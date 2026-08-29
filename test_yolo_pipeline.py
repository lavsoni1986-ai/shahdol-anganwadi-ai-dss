import sys
import time
import glob
from app.services.yolo_detector import yolo_detector
from app.utils.logger import get_logger

logger = get_logger(__name__)

def test_pipeline():
    images = glob.glob("data/uploads/*.jpg")
    if not images:
        print("No images found in data/uploads")
        return
        
    test_images = images
    print(f"Testing on {len(test_images)} images...\n")
    
    total_time = 0
    total_conf = 0
    success_count = 0
    
    for i, img_path in enumerate(test_images):
        print(f"--- Image {i+1}: {img_path} ---")
        start = time.time()
        res = yolo_detector.detect_objects(img_path)
        
        if res:
            success_count += 1
            print(f"Persons: {res['persons_detected']}")
            print(f"Children: {res['children_count']}")
            print(f"Worker: {res['worker_count']}")
            print(f"Confidence: {res['confidence']}%")
            print(f"Processing Time: {res['processing_time_ms']}ms")
            print(f"Saved Annotated: {res['visualized_image_path']}")
            
            total_time += res['processing_time_ms']
            total_conf += res['confidence']
        else:
            print("YOLO failed to process image.")
            
        print()
        
    if success_count > 0:
        avg_time = total_time / success_count
        avg_conf = total_conf / success_count
        print("=== Final Average ===")
        print(f"Average Accuracy/Confidence: {avg_conf:.1f}%")
        print(f"Average Processing Time: {avg_time:.1f}ms")
    else:
        print("All tests failed.")

if __name__ == "__main__":
    test_pipeline()
