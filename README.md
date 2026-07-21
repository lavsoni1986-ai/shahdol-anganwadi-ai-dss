# BharatOS — Shahdol Anganwadi Digital Verification & Decision Support System

> **District:** Shahdol, Madhya Pradesh, India  
> **MVP Version:** Day 1 — Data Ingestion & WhatsApp Auto-Acknowledgement  
> **Tech Stack:** Python · FastAPI · SQLAlchemy · SQLite (MVP) → PostgreSQL (Prod) · Meta WhatsApp Cloud API

---

## 🎯 Project Overview

This system enables Anganwadi workers (AWC) in District Shahdol to submit daily attendance and meal distribution reports via a simple WhatsApp photo message. The backend:

1. **Receives** WhatsApp photo submissions via Meta Webhook
2. **Authenticates** the worker using their registered phone number
3. **Persists** the submission to a database
4. **Acknowledges** the worker instantly with a Hindi confirmation message

### Day 1 Pilot Centre
- **AWC ID:** AWC-SHA-1042
- **Centre Name:** रामपुर
- **Block:** सोहागपुर

---

## 🗂 Project Structure

```
shahdol-anganwadi-mvp/
├── .env.example              # Environment variable template
├── .env                      # Your actual secrets (DO NOT COMMIT)
├── README.md
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI App + Webhook Endpoints
│   ├── config.py             # Pydantic Settings from .env
│   ├── database.py           # SQLAlchemy Async Engine + Session
│   ├── models.py             # Database Table Definitions (ORM Models)
│   ├── schemas.py            # Pydantic Request/Response Schemas
│   ├── services/
│   │   ├── __init__.py
│   │   ├── whatsapp.py       # Meta WhatsApp API Client
│   │   └── worker_auth.py    # Worker Phone Lookup Service
│   └── utils/
│       ├── __init__.py
│       └── logger.py         # Structured Logging
└── data/
    └── mock_workers.json     # Pilot Worker Master Data
```

---

## 🚀 Setup & Run — Step by Step

### Step 1: Navigate to Project Folder
```bash
cd shahdol-anganwadi-mvp
```

### Step 2: Create and Activate Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
```bash
# Copy the template
cp .env.example .env

# Edit .env and fill in:
# - WHATSAPP_VERIFY_TOKEN  → your custom verification token
# - WHATSAPP_ACCESS_TOKEN  → from Meta Developer Console
# - WHATSAPP_PHONE_NUMBER_ID → your WhatsApp Business Phone Number ID
```

### Step 5: Initialize Database
The database and tables are created automatically on first startup.

### Step 6: Start the Development Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 7: Expose to Meta Webhooks (Development)
Use [ngrok](https://ngrok.com/) to expose your local server:
```bash
ngrok http 8000
```
Copy the `https://xxxx.ngrok.io` URL and configure it in Meta Developer Console:
- **Webhook URL:** `https://xxxx.ngrok.io/webhook`
- **Verify Token:** (same as `WHATSAPP_VERIFY_TOKEN` in your `.env`)

---

## 📡 API Endpoints

| Method | Endpoint    | Description                              |
|--------|-------------|------------------------------------------|
| `GET`  | `/`         | Health check & system info               |
| `GET`  | `/health`   | Detailed health status (DB + API)        |
| `GET`  | `/webhook`  | Meta webhook verification challenge      |
| `POST` | `/webhook`  | Incoming WhatsApp message handler        |
| `GET`  | `/docs`     | Swagger UI (auto-generated API docs)     |
| `GET`  | `/redoc`    | ReDoc API documentation                  |

---

## 🔄 Data Flow (Day 1)

```
AWC Worker sends WhatsApp Photo
         │
         ▼
Meta WhatsApp Cloud API
         │  (HTTPS POST)
         ▼
/webhook endpoint (FastAPI)
         │
         ├─► Worker Authentication (mock_workers.json)
         │         │
         │         ├─ AUTHORIZED → fetch AWC details
         │         └─ UNAUTHORIZED → send Hindi error reply
         │
         ├─► Save to `daily_submissions` table (SQLite/PostgreSQL)
         │
         └─► Send Auto-Acknowledgement WhatsApp Reply (Hindi)
```

---

## 🛡 Environment Variables Reference

| Variable                  | Required | Description                              |
|---------------------------|----------|------------------------------------------|
| `WHATSAPP_VERIFY_TOKEN`   | ✅ Yes   | Your custom token for webhook verification |
| `WHATSAPP_ACCESS_TOKEN`   | ✅ Yes   | Meta permanent system user access token  |
| `WHATSAPP_PHONE_NUMBER_ID`| ✅ Yes   | Your WhatsApp Business phone number ID   |
| `DATABASE_URL`            | ✅ Yes   | SQLite or PostgreSQL connection string   |
| `DEBUG`                   | No       | `True` for dev, `False` for production   |
| `LOG_LEVEL`               | No       | `INFO` / `DEBUG` / `WARNING`             |

---

## 📊 Database Schema (Day 1)

### `daily_submissions` Table
| Column               | Type        | Description                        |
|----------------------|-------------|------------------------------------|
| `id`                 | Integer (PK)| Auto-increment primary key         |
| `submission_id`      | UUID (str)  | Unique submission identifier       |
| `awc_id`             | String      | AWC centre identifier              |
| `worker_phone`       | String      | Sender's WhatsApp phone number     |
| `worker_name`        | String      | Worker name from master data       |
| `center_name`        | String      | AWC centre name (Hindi)            |
| `block_name`         | String      | Block name                         |
| `submission_timestamp`| DateTime  | Time of submission (IST)           |
| `raw_media_id`       | String      | Media ID from Meta API             |
| `message_id`         | String      | WhatsApp Message ID                |
| `status`             | String      | `RECEIVED` / `PROCESSED` / `ERROR` |
| `raw_payload`        | Text (JSON) | Full raw webhook payload           |
| `created_at`         | DateTime    | Database record creation time      |

---

## 🏗 Production Deployment Notes

1. **Database:** Switch `DATABASE_URL` to PostgreSQL (`asyncpg` driver)
2. **Security:** Set `DEBUG=False`, rotate `SECRET_KEY`
3. **Process Manager:** Use `gunicorn` with `uvicorn` workers
4. **Reverse Proxy:** Deploy behind Nginx with SSL termination
5. **Logging:** Forward logs to a centralized system (e.g., ELK Stack)

---

## 📞 Support

For technical issues, contact the BharatOS technical team.  
**Pilot District:** Shahdol, Madhya Pradesh  
**System Version:** MVP Day 1 — July 2026
