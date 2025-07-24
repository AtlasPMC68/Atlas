-- Exemple d'utilisateur (owner)
INSERT INTO users (
  id, username, email, password
) VALUES (
  '00000000-0000-0000-0000-000000000001',
  'AtlasAdmin',
  'admin@atlas.ca',
  '$2b$12$ExZzCfrn8.YJ4b0dOx4Y1OGx8Uyi15oigTeViTJ612kuYVjh.ljh.'
);

-- Exemple de base_layer
INSERT INTO base_layers (
  id, name, tile_url
) VALUES (
  '00000000-0000-0000-0000-000000000100',
  'Carto Light',
  'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'
);

-- Insertion d'une carte
INSERT INTO maps (
  id, owner_id, base_layer_id, title, description, access_level,
  start_date, end_date, precision
) VALUES (
  '11111111-1111-1111-1111-111111111111',
  '00000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000000100',
  'Carte historique du Québec',
  'Carte illustrant l’évolution du territoire québécois.',
  'public',
  '1600-01-01',
  '1900-01-01',
  'approximate'
);


-- data qui suce pour liv tripper pas
INSERT INTO features (
  id, map_id, name, type, geometry,
  start_date, end_date, precision, color, stroke_width,
  icon, tags, source, opacity, z_index
) VALUES (
  '22222222-2222-2222-2222-222222222222',
  '11111111-1111-1111-1111-111111111111', -- map_id existant
  'Ville de Québec',
  'point',
  ST_SetSRID(ST_Point(-71.2080, 46.8139), 4326), -- latitude/longitude
  '1608-01-01',
  '2025-01-01',
  'exact',
  '#0000FF', -- couleur bleue
  2,
  'city-icon.png',
  '{"category": "ville", "population": "moyenne"}',
  'source historique',
  1.0,
  2
);

INSERT INTO features (
  id, map_id, name, type, geometry,
  start_date, end_date, precision, color, stroke_width,
  icon, tags, source, opacity, z_index
) VALUES (
  '33333333-3333-3333-3333-333333333333',
  '11111111-1111-1111-1111-111111111111',
  'Zone de Montréal',
  'zone',
  ST_SetSRID(
    ST_GeomFromText(
      'POLYGON((-73.6 45.5, -73.6 45.6, -73.5 45.6, -73.5 45.5, -73.6 45.5))'
    ), 4326
  ),
  '1700-01-01',
  '2025-01-01',
  'estimated',
  '#00FF00',
  1,
  'zone-icon.png',
  '{"category": "zone", "note": "centre urbain"}',
  'cartographie ancienne',
  0.8,
  1
);

INSERT INTO features (
  id, map_id, name, type, geometry,
  start_date, end_date, precision, color, stroke_width,
  icon, tags, source, opacity, z_index
) VALUES (
  '44444444-4444-4444-4444-444444444444',
  '11111111-1111-1111-1111-111111111111',
  'Flèche Montréal → Québec',
  'arrow',
  ST_SetSRID(
    ST_MakeLine(
      ST_Point(-73.5673, 45.5017),  -- Montréal
      ST_Point(-71.2080, 46.8139)   -- Québec
    ), 4326
  ),
  '1800-01-01',
  '2025-01-01',
  'approximate',
  '#FF0000',
  3,
  'arrow-icon.png',
  '{"direction": "Montréal à Québec"}',
  'source militaire',
  1.0,
  3
);