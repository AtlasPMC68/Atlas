# Backend - Maps Processing API

## Installation & Local Setup

1. Create a virtual environment:
   ```sh
   python -m venv .venv
   ```

2. Activate the virtual environment:
   - **Windows:**
     ```powershell
     .venv\Scripts\activate
     ```
   - **macOS / Linux:**
     ```sh
     source .venv/bin/activate
     ```

3. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```

4. Start the development server:
   ```sh
   uvicorn app.main:app --reload
   ```

## Health Checks

In another terminal, test the API status:

```sh
curl http://localhost:8000/ping
```
Expected response:
```json
"pong"
```

### Database Connection Test

```sh
curl http://localhost:8000/db-test
```
Expected response:
```json
{"db_status": "connected", "result": [1]}
```

## Georeferencing Tests

The testing tool (regression and exploration) is described in [`dev-docs/dev-test-tool.md`](../dev-docs/dev-test-tool.md).
To intentionally replace the best result (`best`) of a test case with its latest run (even if lower scoring), see section 5: `scripts/force_promote_georef_best.py`.

## Geographic Entities Dataset Generation

To update or regenerate the offline gazetteer dataset (`app/data/geographic_entities.json`) using `geonamescache` and Natural Earth GeoJSON layers:

- **Windows (PowerShell):**
  ```powershell
  Get-Content scripts\update_geographic_entities.py | docker exec -i atlas-backend python -
  ```

- **macOS / Linux:**
  ```sh
  docker exec -i atlas-backend python < scripts/update_geographic_entities.py
  ```
