-- Exemple d'utilisateur (owner)
INSERT INTO users (
  id, username, email
) VALUES (
  '00000000-0000-0000-0000-000000000001',
  'AtlasAdmin',
  'admin@atlas.ca'
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


-- Ville de Québec (point)
INSERT INTO features (id, map_id, is_feature_collection, data)
VALUES (
  '22222222-2222-2222-2222-222222222222',
  '11111111-1111-1111-1111-111111111111',
  FALSE,
  '{
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "properties": {
          "name": "Ville de Québec",
          "mapElementType": "point", 
          "color_name": "blue",
          "color_rgb": [0, 0, 255],
          "start_date": "1608-01-01",
          "end_date": "2025-01-01"
        },
        "geometry": {
          "type": "Point",
          "coordinates": [-71.2080, 46.8139]
        }
      }
    ]
  }'
);
 
-- Zone de Montréal (polygon)
INSERT INTO features (id, map_id, is_feature_collection, data)
VALUES (
  '33333333-3333-3333-3333-333333333333',
  '11111111-1111-1111-1111-111111111111',
  FALSE,
  '{
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "properties": {
          "name": "Zone de Montréal",
          "mapElementType": "zone",
          "color_name": "green",
          "color_rgb": [0, 255, 0],
          "start_date": "1700-01-01",
          "end_date": "2025-01-01",
          "rotation_deg": 0
        },
        "geometry": {
          "type": "Polygon",
          "coordinates": [
            [
              [-73.6, 45.5],
              [-73.6, 45.6],
              [-73.5, 45.6],
              [-73.5, 45.5],
              [-73.6, 45.5]
            ]
          ]
        }
      }
    ]
  }'
);

-- Flèche Montréal → Québec (arrow)
INSERT INTO features (id, map_id, is_feature_collection, data)
VALUES (
  '44444444-4444-4444-4444-444444444444',
  '11111111-1111-1111-1111-111111111111',
  FALSE,
  '{
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "properties": {
          "name": "Flèche Montréal → Québec",
          "mapElementType": "arrow",
          "color_name": "red",
          "color_rgb": [255, 0, 0],
          "start_date": "1800-01-01",
          "end_date": "2025-01-01"
        },
        "geometry": {
          "type": "LineString",
          "coordinates": [
            [-73.5673, 45.5017],
            [-71.2080, 46.8139]
          ]
        }
      }
    ]
  }'
);