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

### ✅ Commit Message Convention

All commit messages must follow this format:

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

---

### 📌 Additional Notes

- Use the "Create branch" button directly in Jira when possible — it helps auto-fill the correct format.
- Always open Pull Requests into the `dev` branch unless otherwise instructed.
- Avoid pushing directly to `main` or `dev`.
- Keep commit history clean and readable.

