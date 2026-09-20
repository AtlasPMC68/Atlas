-- The inputs a map was georeferenced from: control points (with source and
-- sigma), the framing box, and the pipette picks. Stored so a map can be
-- re-georeferenced later without the user re-clicking every point.
ALTER TABLE maps
  ADD COLUMN IF NOT EXISTS georef_inputs JSONB;
