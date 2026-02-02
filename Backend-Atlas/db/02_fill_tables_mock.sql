INSERT INTO users (
  id, username, email
) VALUES (
  '00000000-0000-0000-0000-000000000001',
  'AtlasAdmin',
  'admin@atlas.ca'
);

INSERT INTO base_layers (
  id, name, tile_url
) VALUES (
  '00000000-0000-0000-0000-000000000100',
  'Carto Light',
  'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png'
);

INSERT INTO maps (
  id, user_id, base_layer_id, title, description, is_private,
  start_date, end_date
) VALUES (
  '11111111-1111-1111-1111-111111111111',
  '00000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000000100',
  'Carte historique du Québec',
  'Carte illustrant l''évolution du territoire québécois.',
  false,
  '1600-01-01',
  '1900-01-01'
);
 
INSERT INTO features (id, map_id, geometry, properties) VALUES (
  '33333333-3333-3333-3333-333333333333',
  '11111111-1111-1111-1111-111111111111',
  ST_GeomFromText('POLYGON((-73.6 45.5, -73.6 45.6, -73.5 45.6, -73.5 45.5, -73.6 45.5))', 4326),
  '{
    "name": "Zone de Montréal",
    "color": "#00ff00",
    "stroke_width": 2,
    "opacity": 0.6,
    "start_date": "1700-01-01",
    "end_date": "2025-01-01"
  }'::json
);

INSERT INTO features (id, map_id, geometry, properties) VALUES (
  '44444444-4444-4444-4444-444444444444',
  '11111111-1111-1111-1111-111111111111',
  ST_GeomFromText('LINESTRING(-73.5673 45.5017, -71.2080 46.8139)', 4326),
  '{
    "name": "Flèche Montréal → Québec",
    "color": "#ff0000",
    "stroke_width": 2,
    "opacity": 0.8,
    "start_date": "1800-01-01",
    "end_date": "2025-01-01"
  }'::json
);

INSERT INTO features (map_id, geometry, properties) VALUES (
  '11111111-1111-1111-1111-111111111111',
  ST_GeomFromText('POINT(-71.2080 46.8139)', 4326),
  '{
    "name": "Ville de Québec",
    "color": "#ff5733",
    "stroke_width": 3,
    "opacity": 0.8,
    "start_date": "1608-01-01",
    "end_date": "1760-01-01"
  }'::json
);