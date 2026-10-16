# One image for production: builds the app, then serves it and the API from one address.
# Used by render.yaml; works on any host that runs Docker (Fly.io, Railway, a VPS...).

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements-whisper.txt backend/requirements-download.txt ./
# Local speech-to-text needs ~1 GB of memory; small servers use a hosted service instead
# (TRANSCRIBE_API_KEY). The video downloader (yt-dlp) is small and on by default.
ARG WITH_WHISPER=false
ARG WITH_DOWNLOAD=true
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ "$WITH_WHISPER" = "true" ]; then pip install --no-cache-dir -r requirements-whisper.txt; fi \
 && if [ "$WITH_DOWNLOAD" = "true" ]; then pip install --no-cache-dir -U -r requirements-download.txt; fi
COPY backend/app ./app
COPY backend/worker.py .
COPY --from=web /web/dist ./static
RUN useradd --create-home appuser && mkdir -p /data/uploads && chown -R appuser /data
USER appuser
ENV STATIC_DIR=/app/static UPLOAD_DIR=/data/uploads PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
