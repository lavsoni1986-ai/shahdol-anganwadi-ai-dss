# =====================================================================
# Dockerfile — Shahdol Anganwadi AI DSS (Ideathon)
# Base: mcr.microsoft.com/playwright/python:v1.62.0-noble
#   - Python 3.x + Playwright system deps + Chromium browser included
#   - Playwright Python package must match the browser version (pinned 1.62.0)
# =====================================================================

FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

LABEL org.opencontainers.image.source="https://github.com/lavsoni1986-ai/shahdol-anganwadi-ai-dss"
LABEL description="Shahdol Anganwadi AI DSS — Ideathon container"

# ── System dependencies (beyond what the Playwright base provides) ──
RUN apt-get update --quiet && apt-get install --no-install-recommends --quiet -y \
    # Required for OpenCV / Pillow / PDF fonts
    libgl1 \
    libglib2.0-0 \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# ── Application directory ──
WORKDIR /app

# ── Copy & install Python dependencies ──
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy application source code ──
COPY app/ ./app/
COPY docker/entrypoint.sh ./docker/entrypoint.sh

# ── Copy YOLO model (baked into image; 38.8 MB) ──

# ── Copy Firebase / Firestore config files (rules, not secrets) ──
COPY firestore.rules firebase.json firestore.indexes.json .env.example ./

# ── Make entrypoint executable ──
RUN chmod +x ./docker/entrypoint.sh

# ── Create required runtime directories ──
RUN mkdir -p /app/data/uploads /app/data/processed /app/app/static/reports

# ── Non-root user (Playwright Chromium needs --no-sandbox, already in launch args) ──
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# ── Runtime defaults ──
ENV PORT=8080 \
    YOLO_MODEL_PATH=/app/app/models/yolo11m.pt \
    PYTHONUNBUFFERED=1

# ── Healthcheck ──
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + ('${PORT:-8080}') + '/health', timeout=5).read()" || exit 1

# ── Start ──
EXPOSE 8080
ENTRYPOINT ["./docker/entrypoint.sh"]
