import os
from pathlib import Path
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

SCRIPT_DIR = Path(__file__).parent
IMAGE_PATH = (SCRIPT_DIR / "CEO-F01.jpeg").resolve()


def run_aws_connection_test():
    aws_access_key = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    credentials_loaded = bool(aws_access_key and aws_secret_key)
    print(f"AWS Credentials Loaded: {credentials_loaded}")
    print(f"AWS Region: {aws_region}")

    if not credentials_loaded:
        print("ERROR: AWS credentials (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY) missing in .env")
        return

    if not IMAGE_PATH.exists():
        print(f"ERROR: Image not found at: {IMAGE_PATH}")
        return

    client_created = False
    try:
        client = boto3.client(
            "rekognition",
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region,
        )
        client_created = True
        print(f"Rekognition Client Created: {client_created}")
    except Exception as e:
        print(f"ERROR creating Rekognition client: {e}")
        return

    try:
        with open(IMAGE_PATH, "rb") as img_file:
            image_bytes = img_file.read()

        response = client.detect_labels(
            Image={"Bytes": image_bytes},
            MaxLabels=5,
            MinConfidence=50,
        )

        labels = response.get("Labels", [])
        top_labels = [f"{l['Name']} ({l['Confidence']:.1f}%)" for l in labels]

        print("\n==================================")
        print("AWS CONNECTION TEST")
        print("==================================")
        print("STATUS: SUCCESS")
        print(f"REGION: {aws_region}")
        print(f"LABELS RETURNED: {len(labels)}")
        print(f"TOP LABELS: {', '.join(top_labels)}")
        print("==================================")

    except ClientError as ce:
        error_code = ce.response.get("Error", {}).get("Code", "UnknownCode")
        error_message = ce.response.get("Error", {}).get("Message", str(ce))
        print("\n==================================")
        print("AWS CONNECTION TEST")
        print("==================================")
        print("STATUS: FAILED (ClientError)")
        print(f"REGION: {aws_region}")
        print(f"ERROR CODE: {error_code}")
        print(f"ERROR MESSAGE: {error_message}")
        print(f"FULL EXCEPTION: {ce}")
        print("==================================")

    except BotoCoreError as bce:
        print("\n==================================")
        print("AWS CONNECTION TEST")
        print("==================================")
        print("STATUS: FAILED (BotoCoreError)")
        print(f"REGION: {aws_region}")
        print(f"FULL EXCEPTION: {bce}")
        print("==================================")

    except Exception as ex:
        print("\n==================================")
        print("AWS CONNECTION TEST")
        print("==================================")
        print("STATUS: FAILED (Unexpected Exception)")
        print(f"REGION: {aws_region}")
        print(f"FULL EXCEPTION: {ex}")
        print("==================================")


if __name__ == "__main__":
    run_aws_connection_test()
