-- The inputs a map was georeferenced from: the control points (each with its
-- source, and a city's GeoNames id), the framing box, the legend answer and the
-- pipette picks. Written when an import's extraction saves its features (see
-- app/utils/georeferencing/inputs.py for the format).
--
-- Why keep them: the fitted transform is cheap to recompute, the clicks are
-- not. With these, a map can be re-georeferenced when the algorithm improves
-- without asking the user to click every point again. Nothing reads them yet.
--
-- Postgres runs this folder only on a fresh volume. On an existing database:
--   docker compose exec db psql -U postgres -d atlas -f /docker-entrypoint-initdb.d/04_add_georef_inputs_to_maps.sql
ALTER TABLE maps
  ADD COLUMN IF NOT EXISTS georef_inputs JSONB;
