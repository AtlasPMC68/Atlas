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
      curl -X POST "http://localhost:8000/test/simple"
   - You should receive: {"task_id": random Id,"status":"Task started","message":"Task launched for World"}

8. **Live Reload (Development):**
   - **Backend:** With Docker volumes and live reload enabled, any changes you make to the backend code will automatically restart the server inside the container.
   - **Frontend:** The frontend uses the Vite dev server with hot reload. Any changes to files will instantly reload the app in your browser.

9. **Stopping the services:**
   - Press `Ctrl+C` in the terminal running Docker Compose, or run:
     ```sh
     docker-compose down
     ```

---
