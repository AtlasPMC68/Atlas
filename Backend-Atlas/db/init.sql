CREATE EXTENSION IF NOT EXISTS postgis;

-- Exemple de table de test
CREATE TABLE IF NOT EXISTS lieux (
  id SERIAL PRIMARY KEY,
  nom TEXT NOT NULL,
  geom GEOMETRY(Point, 4326)
);