-- Persist one user-selected reference image per map.
-- Postgres runs this folder only on a fresh volume. On an existing database:
--   docker compose exec db psql -U postgres -d atlas -f /docker-entrypoint-initdb.d/06_map_reference_images.sql
ALTER TABLE maps
  ADD COLUMN IF NOT EXISTS reference_image BYTEA,
  ADD COLUMN IF NOT EXISTS reference_image_content_type TEXT;
