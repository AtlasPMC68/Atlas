CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS "users" (
  "id" UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  "username" TEXT UNIQUE NOT NULL,
  "email" TEXT UNIQUE NOT NULL,
  "created_at" TIMESTAMP DEFAULT (now())
);

CREATE TABLE IF NOT EXISTS "maps" (
  "id" UUID PRIMARY KEY,
  "user_id" UUID REFERENCES "users"("id") ON DELETE CASCADE,
  "title" TEXT NOT NULL,
  "description" TEXT,
  "is_private" BOOLEAN DEFAULT TRUE,
  "start_date" DATE, -- TODO : Take decision with this
  "end_date" DATE, -- TODO : Take decision with this
  "created_at" TIMESTAMP DEFAULT (now()),
  "updated_at" TIMESTAMP DEFAULT (now())
);

CREATE TABLE IF NOT EXISTS "features" (
  "id" UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  "map_id" UUID REFERENCES "maps"("id") ON DELETE CASCADE,
  "is_feature_collection" BOOLEAN DEFAULT FALSE,
  "data" JSONB NOT NULL,
  "created_at" TIMESTAMP DEFAULT (now()),
  "updated_at" TIMESTAMP DEFAULT (now())
);
