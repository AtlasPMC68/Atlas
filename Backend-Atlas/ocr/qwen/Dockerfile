# Qwen 3.5 Celery Worker Container Image
FROM ocr-base

USER root

RUN pip install --no-cache-dir "transformers==5.5.3" opencv-python-headless

USER appuser

RUN python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Qwen/Qwen3.5-2B', cache_dir='/app/models')"

COPY --chown=appuser:appuser . /app/qwen/
WORKDIR /app/qwen

CMD ["python", "-m", "celery", "-A", "worker", "worker", "--loglevel=warning", "--concurrency=1", "--queues=qwen", "-n", "qwen@%h"]
