# BharatOS Shahdol Anganwadi DSS MVP - Recovery Audit

## 1. Current Project Architecture
- **Framework**: FastAPI (Python 3.10+) serving HTTP API and Webhook endpoints.
- **Database**: SQLite (Async via aiosqlite) mapped using SQLAlchemy 2.0 ORM.
- **WhatsApp Integration**: Meta Cloud API for sending/receiving messages (via httpx).
- **Background Processing**: FastAPI `BackgroundTasks` for AI evaluation.
- **AI Validation**: OpenCV and PIL (pHash, Laplacian variance).
- **Reporting**: ReportLab for Hindi PDF generation.
- **Frontend Dashboard**: Jinja2 Templates + Vanilla JS + TailwindCSS (Served statically).

## 2. Folder Structure
```text
e:\shahdol-anganwadi-dss-mvp\
├── app/
│   ├── routers/        (dashboard.py, reports.py)
│   ├── services/       (ai_vision.py, pdf_generator.py, whatsapp.py, worker_auth.py)
│   ├── templates/      (HTML files)
│   ├── utils/          (logger.py)
│   ├── config.py       (Environment variables)
│   ├── database.py     (DB engine & session)
│   ├── main.py         (FastAPI app & webhook)
│   ├── models.py       (SQLAlchemy models)
│   └── schemas.py      (Pydantic models)
├── data/               (mock_workers.json)
├── venv/
├── shahdol_anganwadi.db
├── README.md
├── requirements.txt
└── .env
```

## 3. Database Schema
Defined in `app/models.py`.
- **`daily_submissions`**: Stores incoming WhatsApp submissions, processing status, media hashes, worker info, AI score, and timestamps.
- **`webhook_logs`**: Audit table storing raw JSON webhook payloads with source IP and receive time.

## 4. Existing API Routes
Defined in `app/main.py`.
- `GET /` : Root/System Info.
- `GET /health` : Detailed Health Check.
- `GET /webhook` : Meta Webhook Verification.
- `POST /webhook` : Incoming WhatsApp Message Handler.
- `GET /dashboard` : Web Review Panel (HTML).

## 5. Existing WhatsApp Integration
- Supported by `app/services/whatsapp.py` and the `/webhook` route.
- Handles webhook verification challenge.
- Sends auto-acknowledgements to authorized workers.
- Sends rejection messages to unauthorized numbers.

## 6. Existing AI Modules
- Located in `app/services/ai_vision.py`.
- **Blur Detection**: Implemented using OpenCV Laplacian Variance.
- **Duplicate Detection**: Implemented using perceptual hash (`imagehash.phash`).
- **Object Detection**: Currently mocked/simulated (`estimate_child_count_and_meal`).

## 7. Existing PDF Generation
- Located in `app/services/pdf_generator.py`.
- Uses ReportLab to generate A4 Government-style reports.
- Automatically downloads and registers Noto Sans Devanagari font for Hindi text.

## 8. Existing Logging
- Located in `app/utils/logger.py`.
- Uses `structlog` for structured, JSON-friendly console logging with HTTP request tracking.

## 9. Existing Security Features
- **Webhook Verification**: Validates `hub.verify_token`.
- **Worker Auth**: Validates incoming phone numbers against an in-memory master list (loaded from `mock_workers.json`).

## 10. Missing Features compared with the final Government Pilot MVP
The current repository is missing real media processing logic (media is currently mocked), file limits, deep inspection (EXIF), and some advanced operational tools (Broadcast).

### Audit Checklist

| Module | Exists | Missing | Needs Update |
| --- | --- | --- | --- |
| WhatsApp Cloud API | Yes | | |
| Webhook | Yes | | |
| Media Download | | Yes | |
| Local Image Storage | | Yes | |
| SHA-256 Hash | Yes | | |
| pHash Duplicate Detection | Yes | | |
| Blur Detection | Yes | | |
| Brightness Detection | | Yes | |
| EXIF Extraction | | Yes | |
| Audit ID | | | Yes |
| Government PDF | Yes | | |
| Structured Logging | Yes | | |
| Background Tasks | Yes | | |
| Virtual Broadcast | | Yes | |
| MIME Validation | | | Yes |
| 5 MB Limit | | Yes | |
| PIL Image Verify | | Yes | |
| Database Indexes | Yes | | |
| Error Handling | Yes | | |
| AI Fallback | Yes | | |
| Performance Metrics | Yes | | |
| Production Report | Yes | | |
