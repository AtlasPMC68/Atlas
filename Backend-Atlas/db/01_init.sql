CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS "users" (
  "id" UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  "username" TEXT UNIQUE NOT NULL,
  "email" TEXT UNIQUE NOT NULL,
  "created_at" TIMESTAMP DEFAULT (now())
);

CREATE TABLE IF NOT EXISTS "projects" (
  "id" UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  "user_id" UUID REFERENCES "users"("id") ON DELETE CASCADE,
  "title" TEXT NOT NULL,
  "description" TEXT,
  "is_private" BOOLEAN DEFAULT TRUE,
  "created_at" TIMESTAMP DEFAULT (now()),
  "updated_at" TIMESTAMP DEFAULT (now())
);

CREATE TABLE IF NOT EXISTS "maps" (
  "id" UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  "project_id" UUID REFERENCES "projects"("id") ON DELETE CASCADE,
  "title" TEXT NOT NULL,
  "date" DATE, -- if date is null will show regardless of what is selected on timeline
  "created_at" TIMESTAMP DEFAULT (now()),
  "updated_at" TIMESTAMP DEFAULT (now())
);

CREATE TABLE IF NOT EXISTS "features" (
  "id" UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  "map_id" UUID REFERENCES "maps"("id") ON DELETE CASCADE,
  "data" JSONB NOT NULL,
  "created_at" TIMESTAMP DEFAULT (now()),
  "updated_at" TIMESTAMP DEFAULT (now())
);
