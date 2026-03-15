import L from "leaflet";
import { MAP_CONFIG as MAP_CONFIG_RAW } from "../composables/useMapConfig.js";

type MapConfig = {
  BASE_ZOOM: number;
  BASE_RADIUS: number;
  ZOOM_FACTOR: number;
  AVAILABLE_YEARS: number[];
};

type Coord = [number, number];
type NestedCoords = Coord | Coord[] | Coord[][] | Coord[][][];

const MAP_CONFIG = MAP_CONFIG_RAW as MapConfig;

/**
 * Smooth free line points by removing points that are too close together
 * @param {Array} points - Array of LatLng points
 * @returns {Array} Smoothed array of points
 */
export function smoothFreeLinePoints(points: L.LatLng[]): L.LatLng[] {
  if (points.length < 2) return points;

  const smoothed = [points[0]];

  for (let i = 1; i < points.length; i++) {
    const lastPoint = smoothed[smoothed.length - 1];
    const currentPoint = points[i];

    const latDiff = currentPoint.lat - lastPoint.lat;
    const lngDiff = currentPoint.lng - lastPoint.lng;
    const distance = Math.sqrt(latDiff * latDiff + lngDiff * lngDiff);

    if (distance >= 0.00001) {
      smoothed.push(currentPoint);
    }
  }

  return smoothed;
}

/**
 * Calculate radius for zoom level
 * @param {number} currentZoom
 * @returns {number}
 */
export function getRadiusForZoom(currentZoom: number): number {
  const zoomDiff = currentZoom - MAP_CONFIG.BASE_ZOOM;
  return Math.max(
    MAP_CONFIG.BASE_RADIUS,
    MAP_CONFIG.BASE_RADIUS * Math.pow(MAP_CONFIG.ZOOM_FACTOR, zoomDiff),
  );
}

/**
 * Transform normalized coordinates to world coordinates
 * @param {Object} geojson - GeoJSON feature collection
 * @param {number} anchorLat - Anchor latitude
 * @param {number} anchorLng - Anchor longitude
 * @param {number} sizeMeters - Size in meters
 * @returns {Object} Transformed GeoJSON
 */
export function transformNormalizedToWorld(
  geojson: {
    type: "FeatureCollection";
    features: Array<{
      geometry: { coordinates: NestedCoords };
      [key: string]: unknown;
    }>;
    [key: string]: unknown;
  },
  anchorLat: number,
  anchorLng: number,
  sizeMeters: number,
) {
  const crs = L.CRS.EPSG3857;
  const center = crs.project(L.latLng(anchorLat, anchorLng));
  const halfSize = sizeMeters / 2;

  const transformCoord = ([x, y]: Coord): Coord => {
    const nx = x - 0.5;
    const ny = y - 0.5;

    const mx = center.x + nx * 2 * halfSize;
    const my = center.y - ny * 2 * halfSize;

    const latlng = crs.unproject(L.point(mx, my));
    return [latlng.lng, latlng.lat]; // GeoJSON order = [lng, lat]
  };

  const transformCoords = (coords: NestedCoords): NestedCoords => {
    if (typeof coords[0] === "number") {
      return transformCoord(coords as Coord);
    }
    return (coords as NestedCoords[]).map(transformCoords) as NestedCoords;
  };

  return {
    ...geojson,
    features: geojson.features.map((f) => ({
      ...f,
      geometry: {
        ...f.geometry,
        coordinates: transformCoords(f.geometry.coordinates),
      },
    })),
  };
}

/**
 * Convert value to array if not already an array
 * @param {*} maybeArray - Value to convert
 * @returns {Array} Array representation
 */
export function toArray<T>(maybeArray: T | T[] | null | undefined): T[] {
  if (Array.isArray(maybeArray)) return maybeArray;
  if (maybeArray == null) return []; // null or undefined
  return [maybeArray]; // wrap single object
}

/**
 * Debounce function calls
 * @param {Function} fn - Function to debounce
 * @param {number} delay - Delay in milliseconds
 * @returns {Function} Debounced function
 */
export function debounce<T extends unknown[]>(
  fn: (...args: T) => void,
  delay: number,
): (...args: T) => void {
  let timeout: ReturnType<typeof setTimeout> | undefined;
  return (...args: T) => {
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), delay);
  };
}

/**
 * Get the closest available year that is less than or equal to the requested year
 * @param {number} year - Requested year
 * @returns {number} Closest available year
 */
export function getClosestAvailableYear(year: number): number {
  const sorted = [...MAP_CONFIG.AVAILABLE_YEARS].sort((a, b) => a - b);
  for (let i = sorted.length - 1; i >= 0; i--) {
    if (year >= sorted[i]) return sorted[i];
  }
  return sorted[0];
}

/**
 * Calculate distance between two points in pixels on screen
 * @param {Object} map - Leaflet map instance
 * @param {L.LatLng} point1 - First point
 * @param {L.LatLng} point2 - Second point
 * @returns {number} Distance in pixels
 */
export function getPixelDistance(
  map: L.Map,
  point1: L.LatLng,
  point2: L.LatLng,
): number {
  const p1 = map.latLngToContainerPoint(point1);
  const p2 = map.latLngToContainerPoint(point2);
  return p1.distanceTo(p2);
}
