// Shared georeferencing-related types

// Geographic bounds for a rectangular region
export interface WorldBounds {
  west: number;
  south: number;
  east: number;
  north: number;
}

// Latitude/longitude tuple
export type LatLngTuple = [number, number];

// Image-space coordinate tuple (x, y)
export type XYTuple = [number, number];

// Keypoint on the coastline map returned by the backend
export interface CoastlineKeypoint {
  geo: {
    lat: number;
    lng: number;
  };
  // Allow any additional backend-provided fields
  [key: string]: unknown;
}

// Full match between a world keypoint and an image point
export interface GeorefMatch {
  index: number;
  world: LatLngTuple;
  image: XYTuple;
  color: string;
}

// Minimal info needed to render matched points on the world map
export interface MatchedWorldPointSummary {
  index: number;
  color: string;
}

// Minimal info needed to render matched points on the image map
export interface MatchedImagePoint {
  index: number;
  x: number;
  y: number;
  color: string;
}

// Result of selecting a world area (used by picker modal + import view)
export interface WorldAreaSelection {
  bounds: WorldBounds;
  zoom: number;
}
