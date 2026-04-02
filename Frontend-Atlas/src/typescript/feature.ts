export type FeatureId = string;

export interface Feature {
  type: "Feature";
  id: string;
  mapId: string;
  geometry: Geometry;
  properties: FeatureProperties;
  createdAt: string;
  updatedAt: string;
  name: string;
  image?: string;
}

export type MapElementType =
  | "point"
  | "zone"
  | "polyline"
  | "arrow"
  | "shape"
  | "label"
  | "image";

export type FeatureVisibilityGroupType =
  | Exclude<MapElementType, "label" | "polyline" | "arrow">
  | "other";

export type FeatureVisibilityGroup = {
  type: FeatureVisibilityGroupType;
  label: string;
  features: Feature[];
};

export type ShapeKind = "square" | "rectangle" | "circle" | "triangle";

export interface FeatureProperties {
  name: string;
  labelText?: string;
  colorName: string;
  colorRgb: [number, number, number]; // RGB values [0-255, 0-255, 0-255]
  opacity: number;
  strokeColor?: [number, number, number];
  strokeWidth: number;
  strokeOpacity: number;
  mapElementType: MapElementType;
  shapeKind?: ShapeKind;
  mimeType?: string;
  bounds?: [Coordinate, Coordinate];
  startDate: string; // Format: "YYYY-MM-DD"
  endDate: string; // Format: "YYYY-MM-DD"
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

export type PointFeature = Feature & {
  geometry: PointGeometry;
};

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
