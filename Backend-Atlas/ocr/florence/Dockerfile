FROM ocr-base

# Florence-2 requires transformers==4.43.0
RUN pip install --no-cache-dir transformers==4.43.0 opencv-python-headless timm einops \
    && mkdir -p /usr/local/lib/python3.12/site-packages/flash_attn \
    && touch /usr/local/lib/python3.12/site-packages/flash_attn/__init__.py

RUN python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='microsoft/Florence-2-large', cache_dir='/app/models')"

COPY --chown=appuser:appuser . /app/florence/


USER appuser

WORKDIR /app/florence

CMD bash -c "\
    python3 -u -m celery -A worker worker --loglevel=info --concurrency=1 --queues=florence -n florence@%h \
    "