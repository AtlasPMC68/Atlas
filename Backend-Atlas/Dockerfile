# Backend Atlas API Service Container Image
FROM python:3.13.16-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libpq-dev \
    libgeos-dev \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# PaddleX pulls opencv-contrib-python, whose cv2 overwrites ours: put the pinned one back
RUN pip install --no-cache-dir --no-deps --force-reinstall \
    "$(grep -i '^opencv-python-headless' requirements.txt)"

# PaddleOCR models, downloaded at build time so the OCR never waits on the network
ENV PADDLE_PDX_CACHE_HOME=/app/models/paddlex \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    OCR_DET_MODEL=PP-OCRv5_server_det \
    OCR_REC_MODEL=latin_PP-OCRv5_mobile_rec
RUN python -c "import os; from paddleocr import TextDetection; TextDetection(model_name=os.environ['OCR_DET_MODEL'])"
RUN python -c "import os; from paddleocr import TextRecognition; TextRecognition(model_name=os.environ['OCR_REC_MODEL'])"

COPY app ./app
COPY tests ./tests
COPY pytest.ini ./pytest.ini
COPY scripts ./scripts

# Unprivileged user, used in production (docker-compose.prod.yml sets `user: app`).
# Dev keeps root so bind-mounted source stays writable on any host.
# /data is the ocr-data volume shared with florence-worker (same uid 1000).
# /app/media is the media-data volume (reference images), created here so the
# fresh volume is owned by app and stays writable.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data /app/media \
    && chown -R app:app /app /data

# No .env.dev in the image: configuration comes from env_file at run time
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]