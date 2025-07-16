-- Exemple d'utilisateur (owner)
INSERT INTO users (
  id, email, username, icone, "DOB", emplacement
) VALUES (
  '00000000-0000-0000-0000-000000000001',
  'admin@example.com',
  'admin',
  'basic_icone.png',
  '1990-01-01',
  'Québec'
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