import type { Geometry } from "geojson";

export interface Feature {
  id: string;
  mapId: string;
  geometry: Geometry;
  properties?: FeatureProperties;
  createdAt: string;
  updatedAt: string;
}

export interface FeatureProperties {
  name?: string;
  color?: string;
  visible?: boolean;
  [key: string]: any;
}
