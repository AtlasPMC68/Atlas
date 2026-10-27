# Backend Atlas API Service Container Image
FROM python:3.13-slim

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

COPY .env.dev /app/app/.env.dev

EXPOSE 8000

# TODO OWASP A02:2025 [MOYENNE] - Vérifier qu'un serveur de production sans reload et avec une configuration dédiée est utilisé hors développement.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]