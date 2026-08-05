import httpx
from app.config import settings

def test():
    filename = "AWC_Report_SHD-20260731-000004.pdf"
    path = "app/static/reports/" + filename
    url = f"{settings.whatsapp_api_base_url}/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/media"
    
    print(f"Uploading to {url}...")
    try:
        with open(path, "rb") as f:
            res = httpx.post(
                url,
                data={"messaging_product": "whatsapp"},
                files={"file": (filename, f, "application/pdf")},
                headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"},
                timeout=30.0
            )
            print("Upload Status:", res.status_code)
            print("Upload Response:", res.text)
            
            if res.status_code == 200:
                media_id = res.json().get("id")
                print(f"Media ID: {media_id}")
                
                payload = {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": "919753239303",
                    "type": "document",
                    "document": {
                        "id": media_id,
                        "filename": filename,
                        "caption": "Test from media ID"
                    }
                }
                send_url = f"{settings.whatsapp_api_base_url}/{settings.whatsapp_api_version}/{settings.whatsapp_phone_number_id}/messages"
                sres = httpx.post(send_url, json=payload, headers={"Authorization": f"Bearer {settings.whatsapp_access_token}"}, timeout=30.0)
                print("Send Status:", sres.status_code)
                print("Send Response:", sres.text)
    except Exception as e:
        print("Exception:", e)

if __name__ == "__main__":
    test()
