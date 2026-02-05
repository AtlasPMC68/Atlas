export interface Feature {
  id: string;
  mapId: string;
  geometry: Geometry;
  properties: FeatureProperties;
  createdAt: string;
  updatedAt: string;
}

export type MapElementType = "point" | "zone" | "arrow" | "shape";

export interface FeatureProperties {
  name: string;
  color_name: string;
  color_rgb: [number, number, number]; // RGB values [0-255, 0-255, 0-255]
  mapElementType: MapElementType;
  start_date: string; // Format: "YYYY-MM-DD"
  end_date: string; // Format: "YYYY-MM-DD"
}

// Geometry types
export type Coordinate = [number, number];

export interface PointGeometry {
  type: "Point";
  coordinates: Coordinate;
}

export interface LineStringGeometry {
  type: "LineString";
  coordinates: Coordinate[];
}

export interface PolygonGeometry {
  type: "Polygon";
  coordinates: Coordinate[][];
}

export interface MultiPointGeometry {
  type: "MultiPoint";
  coordinates: Coordinate[];
}

export interface MultiLineStringGeometry {
  type: "MultiLineString";
  coordinates: Coordinate[][];
}

export interface MultiPolygonGeometry {
  type: "MultiPolygon";
  coordinates: Coordinate[][][];
}

export type Geometry =
  | PointGeometry
  | LineStringGeometry
  | PolygonGeometry
  | MultiPointGeometry
  | MultiLineStringGeometry
  | MultiPolygonGeometry;
