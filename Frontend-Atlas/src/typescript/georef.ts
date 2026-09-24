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

// Pixel-space representation of a coastline keypoint
export interface CoastlineKeypointPixel {
  x: number;
  y: number;
}

// Geographic representation of a coastline keypoint
export interface CoastlineKeypointGeo {
  lat: number;
  lng: number;
}

// Keypoint on the coastline map returned by the backend
export interface CoastlineKeypoint {
  id: number;
  pixel: CoastlineKeypointPixel;
  geo: CoastlineKeypointGeo;
  response: number;
  // Allow any additional backend-provided fields
  [key: string]: unknown;
}

// A pipette pick. Zone fill and water are pipetted separately because they are
// routinely the same hue -- colour alone cannot disambiguate them, and the user
// can in one click.
export type ImposedColorKind = "zone" | "water";

// A confirmed pipette pick: normalised position, sampling radius, and the hex
// the preview sampled (for swatches; extraction re-samples the pick).
export interface ImposedColor {
  x: number;
  y: number;
  name: string;
  radius: number;
  kind: ImposedColorKind;
  hex: string;
}

// Where a control point came from. "sift": a suggested coastline keypoint the
// user matched on their map. "city": a gazetteer city the user named and
// located on their map.
export type GcpSource = "sift" | "city";

// The gazetteer city a city control point was matched to (GeoNames id + name).
export interface CityRef {
  id: number;
  name: string;
}

interface ControlPointBase {
  pixel: { x: number; y: number };
  geo: { lon: number; lat: number };
}

// One control point, exactly as the backend reads it (ControlPoint.from_dict).
// A discriminated union: a city point always carries its city, a SIFT point
// never does.
export type ControlPointInput =
  | (ControlPointBase & { source: "sift" })
  | (ControlPointBase & { source: "city"; city: CityRef });

// Response entry from POST /projects/city-candidates
export interface CityCandidate {
  id: number;
  name: string;
  lat: number;
  lon: number;
  country: string;
  population: number;
  // The name that matched, possibly an alternate one ("Kebek" for Québec)
  matchedName: string;
  match: "exact" | "prefix" | "fuzzy";
}

// A point drawn on the reference world map, optionally labelled
export interface WorldMapPoint {
  lat: number;
  lng: number;
  label?: string;
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

// Response from POST /projects/coastline-keypoints
export interface CoastlineKeypointsResponse {
  status: "success";
  keypoints: CoastlineKeypoint[];
  total: number;
  bounds: WorldBounds;
  used_lakes: boolean; // Whether lakes were added to find enough keypoints
}
