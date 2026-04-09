FROM ocr-base

# git is required to pip-install transformers from source
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Qwen3.5 requires transformers from git main (needs 4.57.0.dev0+)
RUN pip install --no-cache-dir "git+https://github.com/huggingface/transformers.git@main" opencv-python-headless

COPY --chown=appuser:appuser . /app/qwen/


USER appuser

WORKDIR /app/qwen

CMD ["python", "-m", "celery", "-A", "worker", "worker", "--loglevel=info", "--concurrency=1", "--queues=qwen"]
