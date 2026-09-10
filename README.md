# Atlas

This is our PMC for university : Atlas

## 📚 Git & Jira Naming Conventions

To ensure clarity and traceability across branches and commits, all contributors must follow the naming conventions outlined below.

---

### 🔀 Branch Naming Convention

All branches must follow the format:

ATLAS-[issue-number]: [short-description]

Where:

- `ATLAS-` is the **Jira project key**
- `<issue-number>` is the **Jira ticket number** (e.g., `123`)
- `<short-description>` is a **1–3 word summary** of the purpose (lowercase, hyphen-separated)

✅ **Example**:
ATLAS-123-add-login-feature

---

### ✅ Pull Request Message Convention

All pull request messages must follow this format:

ATLAS-[issue-number]: [type]-[short-description]

Where:

- `ATLAS-<issue-number>` refers to the corresponding Jira ticket (e.g., `ATLAS-123`)
- `<type>` must be either:
  - `feature`
  - `bugfix`
- `<short-description>` is a concise, lowercase, hyphen-separated summary (1–3 words)

✅ **Examples**:
ATLAS-123: feature-add-login
ATLAS-210: bugfix-fix-auth-error

### 📌 Additional Notes

- Use the "Create branch" button directly in Jira when possible — it helps auto-fill the correct format.
- Always open Pull Requests into the `dev` branch unless otherwise instructed.
- Avoid pushing directly to `main` or `dev`.
- Keep commit history clean and readable.
- Local pushes to `main` are blocked by a Git hook to prevent accidental changes.  
  Always work on feature branches and create a Pull Request to merge into `main`.

---

### 🐳 Running the Project with Docker Compose

To run the project using Docker Compose, follow these steps:

1. **Install Docker Desktop**
   - Download and install Docker Desktop from [https://www.docker.com/products/docker-desktop/](https://www.docker.com/products/docker-desktop/).
   - Start Docker Desktop and wait until it is fully running (the whale icon should appear in your system tray).

2. **Build the Docker images (first time or after changes to dependencies):**

   ```sh
   docker-compose build
   ```

3. **Start the services:**

   ```sh
   docker-compose up
   ```

   - This will start the backend service (http://localhost:8000) and the frontend (http://localhost:3000).
   - Redis (localhost:6379)
   - PostgreSQL : localhost:5432
   - Flower (Celery Monitoring): http://localhost:5555

4. **Test the backend:**
   - In a new terminal, run:
     ```sh
     curl http://localhost:8000/ping
     ```
   - You should receive a response like `{ "message": "pong" }`.

5. **Test the frontend:**
   - Open your browser and go to [http://localhost:3000]
   - You should see the Atlas web application.

6. **Test db:**
   - In a terminal, run:

   ```sh
   curl http://localhost:8000/db-test
   ```

   - You should receive a response like `{"db_status":"connected","result":[1]}`

7. **Test Celery and Redis:**
   - In terminal, run:

   ```sh
      curl -X POST "http://localhost:8000/test/simple"
   ```

   - You should receive: `{"task_id": random Id,"status":"Task started","message":"Task launched for World"}`

8. **Live Reload (Development):**
   - **Backend:** With Docker volumes and live reload enabled, any changes you make to the backend code will automatically restart the server inside the container.
   - **Frontend:** The frontend uses the Vite dev server with hot reload. Any changes to files will instantly reload the app in your browser.

9. **Stopping the services:**
   - Press `Ctrl+C` in the terminal running Docker Compose, or run:
     ```sh
     docker-compose down
     ```

---

### 🧪 Tester le projet

Pour ce projet, les tests doivent être lancés dans Docker. C’est la méthode supportée et fiable pour valider le backend et le frontend.

#### Démarrer le projet

```sh
docker compose up -d
```

#### Lancer tous les tests backend

```sh
docker compose exec test-backend pytest -q
```

#### Lancer un fichier de test précis

```sh
docker compose exec test-backend pytest tests/test_extraction_text.py -q
```

#### Lancer un test avec plus de détails

```sh
docker compose exec test-backend pytest tests/test_extraction_text.py -q -vv
```

#### Lancer les tests frontend

```sh
docker compose exec frontend npm run test -- --run
```

#### Voir les logs d’un test

```sh
docker compose logs -f test-backend
```

#### Exemple de résultat

```sh
..ssssssss [100%]
2 passed, 8 skipped in 20.13s
```

Cela signifie :
- `..` = 2 tests ont réussi
- `ssssssss` = 8 tests ont été ignorés
- la suite s’est terminée correctement

#### Erreurs fréquentes

```sh
service "test-backend" is not running
```

Solution :

```sh
docker compose up -d
```

Puis relancer le test.

#### Règle importante

Ne pas lancer pytest directement sur la machine locale pour valider le projet. La méthode correcte est de passer par Docker, où l’environnement du projet est bien configuré.

Cela évite les erreurs de dépendances Python et les imports cassés qui n’ont rien à voir avec le code testé.

---

### ⚙️ CI/CD Pipeline & Tests

To ensure reliability and consistency across the project, a Continuous Integration (CI) pipeline is configured to automatically run tests on every pull request to main.

### 🧪 When Are Tests Run?

**Tests are automatically triggered when:**

- You open a Pull Request targeting the main branch
- You manually re-run GitHub Actions from the Actions tab

### 📦 What Does the CI/CD Pipeline Do?

1. **Builds Docker images for frontend and backend**

2. **Runs unit and integration tests inside containers:**
   - Backend: Python tests using pytest
   - Frontend: TypeScript tests using vitest

3. **Fails the PR if any test fails**

**You will see the test results directly in the Pull Request interface on GitHub under the “Checks” tab.**
✅ If all tests pass, your PR can be reviewed and merged
❌ If a test fails, the PR is blocked until the issue is resolved

### 🧰 How to Add New Tests

### ✅ Backend (Python – FastAPI)

1. **Create a new test file in the Backend-Atlas/tests/ folder.**
   Example: Backend-Atlas/tests/test_example.py

2. **Use the pytest framework:**
   def test_addition():
   assert 2 + 2 == 4

3. **Run locally inside the backend container:**
   docker compose run backend pytest

### ✅ Frontend (TypeScript – Vue + Vite + Vitest)

1. **Create a new file like ComponentName.test.ts inside Frontend-Atlas/tests/**

2. **Write your test using vitest:**
   import { describe, it, expect } from 'vitest'

   describe('math test', () => {
   it('adds numbers correctly', () => {
   expect(2 + 2).toBe(4)
   })
   })

3. **Run locally inside the frontend container:**
   docker compose run frontend npm run test

### Make sure vitest is installed. It’s already configured in the Dockerfile.

### ✅ Add Test-Only Dependencies

**If you need new dev tools or testing libraries:**

- Backend: add to requirements.txt
- Frontend: add to package.json as devDependencies

**Then rebuild containers:**
docker compose build

### 📌 Notes

- The CI/CD configuration is managed in .github/workflows/ci.yml
- Docker images used for testing are the same as in production to ensure reliability
- Test feedback will show directly in your PR — no manual test launching needed
