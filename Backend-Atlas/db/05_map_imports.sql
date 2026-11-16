-- An import in progress: the image, what the user has entered so far, and the
-- state of the two background tasks (OCR, then extraction). The row exists only
-- while the import does: it is deleted in the same transaction that saves the
-- extracted features. Deleting the map deletes it.
CREATE TABLE IF NOT EXISTS "map_imports" (
  "map_id" UUID PRIMARY KEY REFERENCES "maps"("id") ON DELETE CASCADE,
  "image" BYTEA NOT NULL,
  "filename" TEXT NOT NULL,
  -- frameBounds, legend, controlPoints, colors, options (see app/services/imports.py)
  "inputs" JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- pending | running | done | failed
  "ocr_state" TEXT NOT NULL DEFAULT 'pending',
  "ocr_task_id" TEXT,
  "ocr_result" JSONB,
  -- idle | waiting_for_text | queued | running | cancelling | cancelled | failed
  "extraction_state" TEXT NOT NULL DEFAULT 'idle',
  "extraction_task_id" TEXT,
  "extraction_error" TEXT,
  "created_at" TIMESTAMP DEFAULT (now()),
  "updated_at" TIMESTAMP DEFAULT (now())
);
