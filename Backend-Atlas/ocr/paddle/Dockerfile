FROM ocr-base

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir paddlepaddle>=3.0.0b1 paddleocr

COPY . /app/paddle
WORKDIR /app/paddle

USER appuser

CMD ["celery", "-A", "worker", "worker", "--loglevel=info", "--concurrency=1", "--queues=paddle"]

