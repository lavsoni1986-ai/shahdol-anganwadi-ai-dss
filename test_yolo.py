import os
import time
from ultralytics import YOLO
import urllib.request

# Download a sample image
url = "https://ultralytics.com/images/zidane.jpg"
image_path = "sample_image.jpg"
urllib.request.urlretrieve(url, image_path)

print(f"Downloaded sample image to {image_path}")

# Load model (will download yolo11n.pt if missing)
model_name = "yolo11n.pt"
print(f"Loading YOLO model: {model_name}")
model = YOLO(model_name)

# Run inference
print("Running inference...")
start_time = time.time()
results = model(image_path)
end_time = time.time()

print("="*40)
print("YOLO Inference Results")
print("="*40)
print(f"Model Name: {model_name}")
print(f"Inference Time: {(end_time - start_time) * 1000:.2f} ms")

for r in results:
    boxes = r.boxes
    print(f"Detected {len(boxes)} objects:")
    for i, box in enumerate(boxes):
        cls_id = int(box.cls[0])
        cls_name = model.names[cls_id]
        conf = float(box.conf[0])
        print(f"  - [{i+1}] {cls_name}: {conf:.2f} confidence")

print("="*40)
