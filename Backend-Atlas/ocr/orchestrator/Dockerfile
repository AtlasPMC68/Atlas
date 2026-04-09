FROM ocr-base

RUN pip install --no-cache-dir fastapi uvicorn

COPY --chown=appuser:appuser worker.py http_server.py /app/
USER appuser
WORKDIR /app

# Start celery task queue and FastAPI server
CMD bash -c "\
    python3 -u -m celery -A worker worker --loglevel=info --concurrency=1 --queues=ocr & \
    python3 -u -m uvicorn http_server:app --host 0.0.0.0 --port 8080 \
    "
    