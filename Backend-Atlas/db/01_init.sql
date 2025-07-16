CREATE EXTENSION IF NOT EXISTS postgis;

-- Exemple de table de test
CREATE TABLE IF NOT EXISTS lieux (
  id SERIAL PRIMARY KEY,
  nom TEXT NOT NULL,
  geom GEOMETRY(Point, 4326)
);

CREATE TABLE IF NOT EXISTS "users" (
  "id" UUID PRIMARY KEY,
  "email" TEXT UNIQUE NOT NULL,
  "username" TEXT UNIQUE NOT NULL,
  "icone" TEXT NOT NULL DEFAULT 'basic_icone.png',
  "post" TEXT DEFAULT null,
  "organisation" TEXT DEFAULT null,
  "tag_line" TEXT DEFAULT null,
  "bio" TEXT DEFAULT null,
  "language" TEXT DEFAULT 'fr',
  "theme" TEXT DEFAULT 'light',
  "notification_prefs" JSONB,
  "DOB" date NOT NULL,
  "emplacement" TEXT NOT NULL,
  "last_login_at" TIMESTAMP,
  "followers_count" int,
  "maps_created" int,
  "created_at" TIMESTAMP DEFAULT (now())
);

CREATE TABLE IF NOT EXISTS "base_layers" (
  "id" UUID PRIMARY KEY,
  "name" TEXT NOT NULL,
  "tile_url" TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS "maps" (
  "id" UUID PRIMARY KEY,
  "owner_id" UUID,
  "base_layer_id" UUID,
  "style_id" TEXT DEFAULT 'light',
  "parent_map_id" UUID,
  "title" TEXT NOT NULL,
  "description" TEXT,
  "access_level" TEXT DEFAULT 'private',
  "start_date" DATE,
  "end_date" DATE,
  "precision" TEXT,
  "created_at" TIMESTAMP DEFAULT (now())
);

CREATE TABLE IF NOT EXISTS "features" (
  "id" UUID PRIMARY KEY,
  "map_id" UUID,
  "name" TEXT,
  "type" TEXT,
  "geometry" GEOMETRY(GEOMETRY,4326),
  "start_date" TIMESTAMP,
  "end_date" TIMESTAMP,
  "precision" TEXT,
  "color" TEXT,
  "stroke_width" INT,
  "icon" TEXT,
  "tags" JSONB,
  "source" TEXT,
  "opacity" float DEFAULT 1,
  "z_index" int DEFAULT 1,
  "created_at" TIMESTAMP DEFAULT (now())
);

CREATE TABLE IF NOT EXISTS "map_collaborators" (
  "map_id" UUID,
  "user_id" UUID,
  "role" TEXT,
  "added_at" TIMESTAMP DEFAULT (now()),
  PRIMARY KEY ("map_id", "user_id")
);

ALTER TABLE "maps" ADD FOREIGN KEY ("owner_id") REFERENCES "users" ("id") ON DELETE CASCADE;

ALTER TABLE "maps" ADD FOREIGN KEY ("base_layer_id") REFERENCES "base_layers" ("id");

ALTER TABLE "maps" ADD FOREIGN KEY ("parent_map_id") REFERENCES "maps" ("id");

ALTER TABLE "features" ADD FOREIGN KEY ("map_id") REFERENCES "maps" ("id") ON DELETE CASCADE;

ALTER TABLE "map_collaborators" ADD FOREIGN KEY ("map_id") REFERENCES "maps" ("id") ON DELETE CASCADE;

ALTER TABLE "map_collaborators" ADD FOREIGN KEY ("user_id") REFERENCES "users" ("id") ON DELETE CASCADE;
