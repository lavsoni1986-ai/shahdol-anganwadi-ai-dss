import time
import cv2
import json
from ultralytics import YOLO

def calculate_adult_probability(box, img_h, img_w):
    x1, y1, x2, y2 = box.xyxy[0]
    box_h = y2 - y1
    box_w = x2 - x1
    
    score = 0.0
    
    height_ratio = box_h / img_h
    if height_ratio > 0.4:
        score += 0.5
    elif height_ratio > 0.3:
        score += 0.3
    elif height_ratio > 0.2:
        score += 0.1
        
    aspect_ratio = box_h / box_w
    if aspect_ratio > 2.0:
        score += 0.2
    elif aspect_ratio > 1.5:
        score += 0.1
        
    area = (box_w * box_h) / (img_w * img_h)
    if area > 0.15:
        score += 0.3
    elif area > 0.05:
        score += 0.1
        
    return min(score, 0.99)

def benchmark():
    image_path = r"data/uploads/2ffe02b1-4014-4eb3-9de5-718714480ddf.jpg"
    models = ["yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11l.pt"]
    
    results = {}
    
    for model_name in models:
        print(f"Benchmarking {model_name}...")
        try:
            model = YOLO(model_name)
        except Exception as e:
            print(f"Failed to load {model_name}: {e}")
            continue
            
        # Warmup
        img = cv2.imread(image_path)
        if img is None:
            print("Failed to read image")
            return
            
        model(img, verbose=False)
        
        # Actual run
        start_time = time.time()
        res = model(img, verbose=False)
        end_time = time.time()
        
        process_time_ms = int((end_time - start_time) * 1000)
        result = res[0]
        
        img_h, img_w = img.shape[:2]
        
        persons = []
        for box in result.boxes:
            cls_id = int(box.cls[0].item())
            if cls_id == 0:
                conf = float(box.conf[0].item())
                adult_prob = calculate_adult_probability(box, img_h, img_w)
                persons.append({
                    "box": box,
                    "conf": conf,
                    "adult_prob": adult_prob,
                    "coords": box.xyxy[0].tolist()
                })
                
        worker_idx = -1
        max_prob = 0.5
        for i, p in enumerate(persons):
            if p["adult_prob"] > max_prob:
                max_prob = p["adult_prob"]
                worker_idx = i
                
        worker_count = 0
        children_count = 0
        total_conf = 0
        
        annotated_img = img.copy()
        
        for i, p in enumerate(persons):
            x1, y1, x2, y2 = map(int, p["coords"])
            conf = p["conf"]
            total_conf += conf
            
            if i == worker_idx:
                worker_count += 1
                label = f"Worker {conf:.2f}"
                color = (0, 255, 0)
            else:
                children_count += 1
                label = f"Child {conf:.2f}"
                color = (0, 165, 255)
                
            cv2.rectangle(annotated_img, (x1, y1), (x2, y2), color, 2)
            cv2.putText(annotated_img, label, (x1, max(y1-5, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            
        avg_conf = (total_conf / len(persons)) * 100 if persons else 0
        
        save_path = f"data/processed/pongri_{model_name.replace('.pt', '')}.jpg"
        cv2.imwrite(save_path, annotated_img)
        
        results[model_name] = {
            "persons": len(persons),
            "worker": worker_count,
            "children": children_count,
            "confidence": f"{avg_conf:.1f}%",
            "time_ms": process_time_ms,
            "image": save_path
        }
        
    print("\nBENCHMARK RESULTS JSON:")
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    benchmark()
