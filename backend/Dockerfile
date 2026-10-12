# Detecto backend: FastAPI + YOLOv8 (CPU).
# Build from the project root:  docker build -f backend/Dockerfile -t detecto-backend .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Ultralytics writes its settings file here (the app user can't write to $HOME defaults)
    YOLO_CONFIG_DIR=/tmp/ultralytics \
    # Runtime data (SQLite history + enrolled faces, log, temporary video uploads) lives on a volume
    DETECTO_DB_PATH=/data/detecto.db \
    DETECTO_LOG_FILE=/data/detecto.log

# Apply OS security updates (the base image can lag behind), then the shared
# libraries OpenCV needs even for headless use
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) CPU-only PyTorch first: the default Linux wheels bundle CUDA (~2.5 GB extra).
#    requirements.txt then sees torch/torchvision as already satisfied.
COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.14" "torchvision>=0.29" \
    && pip install -r requirements.txt

# 2) Model weights baked into the image (works offline, no download on first start).
#    Local copies from backend/weights/ are used when present (fast, no network);
#    only missing files are downloaded. Copied before the code so code changes
#    don't invalidate this layer and rebuilds stay fast.
COPY backend/__init__.py backend/config.py ./backend/
COPY backend/weights/ ./backend/weights/
COPY scripts/download_face_models.py ./scripts/download_face_models.py
RUN python -c "from ultralytics import YOLO; YOLO('backend/weights/yolov8n.pt')" \
    && python scripts/download_face_models.py

# 3) Application code
COPY backend ./backend

# Run as an unprivileged user; /data is the only writable app directory
RUN useradd --create-home --uid 10001 detecto \
    && mkdir -p /data /tmp/ultralytics \
    && chown -R detecto:detecto /data /tmp/ultralytics
USER detecto
VOLUME ["/data"]

EXPOSE 8000

# Healthy once the API answers (the model is loaded before the server starts accepting requests)
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# One worker: tracking sessions and video jobs are kept in this process's memory
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
