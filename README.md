# Atlas

Historical map processing and feature extraction web platform.

## 🚀 Quick Start (Docker)

```sh
# Start all services (Backend, Frontend, Workers, PostgreSQL, Redis)
docker compose up -d

# Check service health
curl http://localhost:8000/ping
```

### Services

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **Celery Monitoring (Flower)**: http://localhost:5555
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

---

## 🧪 Testing

All tests must run inside Docker:

```sh
# Run all backend tests
docker compose exec test-backend pytest -q

# Run specific backend test file
docker compose exec test-backend pytest tests/test_extraction_text.py -q

# Run frontend tests
docker compose exec frontend npm run test -- --run
```

---

## 🔀 Git & Pull Request Conventions

- **Branch Naming**: `ATLAS-[issue-number]-[short-description]` (e.g. `ATLAS-123-add-login`)
- **PR Title**: `ATLAS-[issue-number]: [type]-[short-description]` (types: `feature`, `bugfix`)
- **Target Branch**: Open Pull Requests targeting `dev` branch. Direct pushes to `main` are blocked.
