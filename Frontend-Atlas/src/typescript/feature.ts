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
  | "point"
  | "zone"
  | "shape"
  | "image"
  | "drawing";

export type FeatureVisibilityGroup = {
  type: FeatureVisibilityGroupType;
  label: string;
  features: Feature[];
};

export type ShapeKind = "square" | "rectangle" | "circle" | "triangle";

export enum ValidationStatus {
  ACCEPTED = "accepted",
  REJECTED = "rejected",
  MANUAL_REVIEW = "manual_review",
}

export type ValidationStatusValue =
  | ValidationStatus
  | "accepted"
  | "rejected"
  | "manual_review";

export interface SuggestedPlace {
  name: string;
  coordinates: Coordinate;
  type?: string;
  source?: "json" | "nearby" | string;
}

export interface FeatureProperties {
  name: string;
  isVisible?: boolean;
  show?: boolean; // set by the backend extraction (tasks.py); false hides the feature initially
  labelText?: string;
  sizePx?: number;
  rawType?: string;
  colorName?: string;
  colorRgb?: [number, number, number]; // RGB values [0-255, 0-255, 0-255]
  // Label text colour, when it differs from colorRgb (the point symbol's fill).
  textColorRgb?: [number, number, number];
  // Label size override; the word type's (or custom style's) size applies without it.
  textSizePx?: number;
  strokeColor?: [number, number, number];
  fillOpacity?: number;
  strokeOpacity?: number;
  strokeWidth?: number;
  mapElementType?: MapElementType;
  shapeKind?: ShapeKind;
  mimeType?: string;
  bounds?: [Coordinate, Coordinate];
  layer?: number;
  rotation?: number;
  opacity?: number;
  image?: string;
  isOcrText?: boolean;
  recognized?: boolean;
  originalText?: string;
  matchedCity?: string;
  country?: string;
  population?: number;
  confidence?: number;
  validationStatus?: ValidationStatus | `${ValidationStatus}`;
  validation_status?: ValidationStatus | `${ValidationStatus}`;
  suggestedPlace?: SuggestedPlace;
  customLabelStyleId?: string | null;
  customLabelStyle?: any;
  customLabelStyleFallbackWordType?: string;
  [key: string]: any;
  fontStyle?: "normal" | "italic" |"uppercase"| string;
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

export type FeatureSnapshot = Feature[];
export type FeatureHistoryStack = FeatureSnapshot[];

export type FeatureTrackingCallback<T> = () => T;
