import os
import sys
import time
from pathlib import Path
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.utils import load_prompt, compute_text_sha256
from benchmark.result_writer import save_result

# Load environment variables from .env file
load_dotenv()

SCRIPT_DIR = Path(__file__).parent

TARGET_IMAGES = sorted([p.name for p in SCRIPT_DIR.glob("CEO-*.jpeg")])
if not TARGET_IMAGES:
    TARGET_IMAGES = ["CEO-F01.jpeg", "CEO-F02.jpeg", "CEO-F03.jpeg", "CEO-F04.jpeg"]


def run_aws_people_counter_benchmark():
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    if not (aws_access_key and aws_secret_key):
        print("ERROR: AWS credentials (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY) missing in .env")
        return

    try:
        client = boto3.client(
            "rekognition",
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region,
        )
    except Exception as e:
        print(f"ERROR creating Rekognition client: {e}")
        return

    summary_results = {}

    for img_filename in TARGET_IMAGES:
        img_path = (SCRIPT_DIR / img_filename).resolve()
        image_key = img_filename.split(".")[0]

        if not img_path.exists():
            print(f"\nERROR: Image file not found: {img_path}")
            summary_results[image_key] = {"faces": "ERROR (File Missing)", "instances": "N/A", "latency": "N/A"}
            continue

        try:
            with open(img_path, "rb") as img_file:
                image_bytes = img_file.read()

            start_time = time.perf_counter()

            # STEP 1: DetectFaces
            faces_response = client.detect_faces(
                Image={"Bytes": image_bytes},
                Attributes=["DEFAULT"],
            )

            # STEP 2: DetectLabels
            labels_response = client.detect_labels(
                Image={"Bytes": image_bytes},
                MaxLabels=50,
                MinConfidence=50,
            )

            end_time = time.perf_counter()
            latency = round(end_time - start_time, 4)

            # Process DetectFaces
            face_details = faces_response.get("FaceDetails", [])
            face_count = len(face_details)
            face_confidences = [round(f["Confidence"], 1) for f in face_details]

            # Process DetectLabels for "Person"
            labels = labels_response.get("Labels", [])
            person_label_found = False
            person_instance_count = 0
            person_confidences = []

            for label in labels:
                if label.get("Name") == "Person":
                    person_label_found = True
                    instances = label.get("Instances", [])
                    person_instance_count = len(instances)
                    person_confidences = [round(inst["Confidence"], 1) for inst in instances]
                    break

            # Print detailed per-image report
            print("\n==================================================")
            print("AWS REKOGNITION BENCHMARK")
            print("==================================================")
            print(f"IMAGE                : {img_filename} ({img_path})")
            print(f"FACE COUNT           : {face_count}")
            print(f"PERSON INSTANCE COUNT: {person_instance_count}")
            print(f"PERSON LABEL FOUND   : {person_label_found}")
            print(f"FACE CONFIDENCES     : {face_confidences}")
            print(f"PERSON CONFIDENCES   : {person_confidences}")
            print(f"LATENCY              : {latency} seconds")
            print("==================================================")

            summary_results[image_key] = {
                "faces": face_count,
                "instances": person_instance_count,
                "latency": f"{latency}s",
            }

            # Save result JSONs automatically (with first-run overwrite protection)
            aws_prompt_sha256 = compute_text_sha256("AWS_REKOGNITION_NATIVE_API_CALL")

            # 1. AWS Faces Result
            save_result(
                engine="aws_faces",
                model="aws-rekognition-detect-faces",
                image_id=image_key,
                image_path=img_path,
                prompt_version="aws_detect_faces_v1",
                prompt_sha256=aws_prompt_sha256,
                prediction=face_count,
                latency=latency,
                confidence=face_confidences,
                notes=f"Faces detected: {face_count}",
                raw_response=faces_response,
                first_run=True,
            )

            # 2. AWS Person Instances Result
            save_result(
                engine="aws_person",
                model="aws-rekognition-detect-labels",
                image_id=image_key,
                image_path=img_path,
                prompt_version="aws_detect_labels_person_v1",
                prompt_sha256=aws_prompt_sha256,
                prediction=person_instance_count,
                latency=latency,
                confidence=person_confidences,
                notes=f"Person instances detected: {person_instance_count}, Label Found: {person_label_found}",
                raw_response=labels_response,
                first_run=True,
            )

        except ClientError as ce:
            error_code = ce.response.get("Error", {}).get("Code", "UnknownCode")
            error_message = ce.response.get("Error", {}).get("Message", str(ce))
            print("\n==================================================")
            print(f"AWS EXCEPTION ON {img_filename}")
            print("==================================================")
            print(f"ERROR CODE    : {error_code}")
            print(f"ERROR MESSAGE : {error_message}")
            print(f"FULL EXCEPTION: {ce}")
            print("==================================================")
            summary_results[image_key] = {"faces": "ERROR (ClientError)", "instances": error_code, "latency": "N/A"}

        except BotoCoreError as bce:
            print("\n==================================================")
            print(f"AWS BOTOCORE EXCEPTION ON {img_filename}")
            print("==================================================")
            print(f"FULL EXCEPTION: {bce}")
            print("==================================================")
            summary_results[image_key] = {"faces": "ERROR (BotoCoreError)", "instances": "N/A", "latency": "N/A"}

        except Exception as ex:
            print("\n==================================================")
            print(f"UNEXPECTED EXCEPTION ON {img_filename}")
            print("==================================================")
            print(f"FULL EXCEPTION: {ex}")
            print("==================================================")
            summary_results[image_key] = {"faces": "ERROR (Unexpected)", "instances": "N/A", "latency": "N/A"}

    # Print Final Summary Table
    print("\n==================================================")
    print("SUMMARY")
    print("==================================================")
    for img_key in summary_results.keys():
        res = summary_results[img_key]
        print(f"{img_key}")
        print(f"Faces: {res['faces']}")
        print(f"Person Instances: {res['instances']}")
        print(f"Latency: {res['latency']}")
        print("---------------------")
    print("==================================================")


if __name__ == "__main__":
    run_aws_people_counter_benchmark()
