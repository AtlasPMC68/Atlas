FROM ocr-base

RUN python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='Qwen/Qwen3.5-2B', cache_dir='/app/models')"

RUN pip install --no-cache-dir "transformers==5.5.3" opencv-python-headless

COPY --chown=appuser:appuser . /app/qwen/
USER appuser
WORKDIR /app/qwen

CMD ["python", "-m", "celery", "-A", "worker", "worker", "--loglevel=warning", "--concurrency=1", "--queues=qwen", "-n", "qwen@%h"]
