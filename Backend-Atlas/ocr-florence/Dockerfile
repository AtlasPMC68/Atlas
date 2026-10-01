# Florence-2 OCR worker image (formerly built FROM the shared ocr-base image;
# inlined here since florence is now the only consumer of that base layer)
FROM python:3.12-slim

# Creating a user
ARG UID=1000
RUN useradd -m -u ${UID} appuser

WORKDIR /app

# Heavy modal dependencies. Keep high to prevent 
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu torch torchvision

# General dependencies required to work in tandem with the project
RUN pip install --no-cache-dir \
    Pillow \
    numpy \
    accelerate \
    celery \
    redis \
    scikit-image

# Florence-2 specific dependencies
RUN pip install --no-cache-dir transformers==4.43.0 \
    opencv-python-headless \
    timm \
    einops \
    shapely \
    # Pulling the Florence2 model require the flash_attn package, which cannot be
    # downloaded without CUDA. Therefore we create a blank package to bypass this
    # requirement as we only use the model is CPU mode without CUDA.
    && mkdir -p /usr/local/lib/python3.12/site-packages/flash_attn \
    && touch /usr/local/lib/python3.12/site-packages/flash_attn/__init__.py

ENV HF_HOME=/app/models
RUN mkdir -p /app/models/hub /app/models /data && \
    chown -R appuser:appuser /app/models /data && \
    chmod -R 777 /data

# Everything on runtime is ran as a normal user
USER appuser

ENV FLORENCE_REPO_ID=microsoft/Florence-2-base \
    FLORENCE_COMMIT_ID=5ca5edf5bd017b9919c05d08aebef5e4c7ac3bac
# ENV FLORENCE_REPO_ID=microsoft/Florence-2-large \
#     FLORENCE_COMMIT_ID=21a599d414c4d928c9032694c424fb94458e3594

RUN python -c "import os; from huggingface_hub import snapshot_download; snapshot_download(repo_id=os.environ['FLORENCE_REPO_ID'], revision=os.environ['FLORENCE_COMMIT_ID'], cache_dir=os.environ['HF_HOME'])"
COPY --chown=appuser:appuser . /app/ocr-florence/
WORKDIR /app/ocr-florence

CMD ["bash", "-c", "python3 -u -m celery -A worker worker --loglevel=${LOG_LEVEL:-warning} --concurrency=1 --queues=florence --hostname=florence@%h"]
