-- Postgres runs this folder only on a fresh volume. On an existing database:
--   docker compose exec db psql -U postgres -d atlas -f /docker-entrypoint-initdb.d/03_add_project_label_styles.sql
ALTER TABLE projects
ADD COLUMN IF NOT EXISTS label_styles JSONB NOT NULL DEFAULT '[]'::jsonb;
