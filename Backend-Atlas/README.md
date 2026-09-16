# Backend Atlas - Map Processing API

FastAPI backend and OCR task pipeline for historical map extraction.

## 🚀 Quick Start (Docker)

```sh
# Start backend and OCR worker services
docker compose up -d backend florence-worker qwen-worker
```

## 🧪 Testing

```sh
# Run backend test suite in Docker
docker compose exec test-backend pytest -q
```
