export type FeatureId = string;

export interface Feature {
  type: "Feature";
  id: string;
  projectId: string;
  mapId?: string | null;
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
  sizePx?: number;
  colorName?: string;
  colorRgb?: [number, number, number]; // RGB values [0-255, 0-255, 0-255]
  strokeColor?: [number, number, number];
  fillOpacity?: number;
  strokeOpacity?: number;
  strokeWidth?: number;
  mapElementType: MapElementType;
  shapeKind?: ShapeKind;
  mimeType?: string;
  bounds?: [Coordinate, Coordinate];
}

export type FeatureForSave = Omit<Feature, "mapId" | "createdAt" | "updatedAt">;

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
