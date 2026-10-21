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

COPY app ./app
COPY tests ./tests
COPY pytest.ini ./pytest.ini
COPY scripts ./scripts

# Unprivileged user, used in production (docker-compose.prod.yml sets `user: app`).
# Dev keeps root so bind-mounted source stays writable on any host.
# /data is the ocr-data volume shared with florence-worker (same uid 1000).
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data \
    && chown -R app:app /app /data

# No .env.dev in the image: configuration comes from env_file at run time
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]