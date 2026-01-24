import L from 'leaflet';
import { MAP_CONFIG } from '../composables/useMapConfig.js';

// Utility functions for geographic calculations and transformations

/**
 * Smooth free line points by removing points that are too close together
 * @param {Array} points - Array of LatLng points
 * @returns {Array} Smoothed array of points
 */
export function smoothFreeLinePoints(points) {
  if (points.length < 2) return points;

  const smoothed = [points[0]]; // Keep the first point

  for (let i = 1; i < points.length; i++) {
    const lastPoint = smoothed[smoothed.length - 1];
    const currentPoint = points[i];

    // Calculate simple geographic distance (degrees)
    const latDiff = currentPoint.lat - lastPoint.lat;
    const lngDiff = currentPoint.lng - lastPoint.lng;
    const distance = Math.sqrt(latDiff * latDiff + lngDiff * lngDiff);

    // Add the point only if it's far enough from the previous one
    // Using a very small threshold (0.0001 degrees ≈ 11 meters at equator)
    if (distance >= 0.00001) {
      smoothed.push(currentPoint);
    }
  }

  return smoothed;
}

/**
 * Calculate radius for zoom level
 * @param {number} currentZoom - Current map zoom level
 * @returns {number} Radius in pixels
 */
export function getRadiusForZoom(currentZoom) {
  const zoomDiff = currentZoom - MAP_CONFIG.BASE_ZOOM;
  return Math.max(MAP_CONFIG.BASE_RADIUS, MAP_CONFIG.BASE_RADIUS * Math.pow(MAP_CONFIG.ZOOM_FACTOR, zoomDiff));
}

/**
 * Transform normalized coordinates to world coordinates
 * @param {Object} geojson - GeoJSON feature collection
 * @param {number} anchorLat - Anchor latitude
 * @param {number} anchorLng - Anchor longitude
 * @param {number} sizeMeters - Size in meters
 * @returns {Object} Transformed GeoJSON
 */
export function transformNormalizedToWorld(geojson, anchorLat, anchorLng, sizeMeters) {
  // Use the same projected CRS as the basemap (Web Mercator)
  const crs = L.CRS.EPSG3857;
  const center = crs.project(L.latLng(anchorLat, anchorLng)); // { x, y } in meters
  const halfSize = sizeMeters / 2;

  // Transform a single coordinate [x, y] in [0,1]×[0,1] into [lng, lat]
  const transformCoord = ([x, y]) => {
    // Center the shape around (0,0) in its local space
    const nx = x - 0.5;
    const ny = y - 0.5;

    // Work in projected meters with a uniform scale so aspect ratio is preserved
    const mx = center.x + nx * 2 * halfSize;
    const my = center.y - ny * 2 * halfSize; // minus because y grows downward

    const latlng = crs.unproject(L.point(mx, my));
    return [latlng.lng, latlng.lat]; // GeoJSON order = [lng, lat]
  };

  const transformCoords = (coords) => {
    if (typeof coords[0] === "number") {
      // [x, y]
      return transformCoord(coords);
    }
    return coords.map(transformCoords);
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
export function toArray(maybeArray) {
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
export function debounce(fn, delay) {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), delay);
  };
}

/**
 * Get the closest available year that is less than or equal to the requested year
 * @param {number} year - Requested year
 * @returns {number} Closest available year
 */
export function getClosestAvailableYear(year) {
  const sorted = [...MAP_CONFIG.AVAILABLE_YEARS].sort((a, b) => a - b);
  for (let i = sorted.length - 1; i >= 0; i--) {
    if (year >= sorted[i]) return sorted[i];
  }
  return sorted[0]; // default to the earliest year
}

/**
 * Calculate distance between two points in pixels on screen
 * @param {Object} map - Leaflet map instance
 * @param {L.LatLng} point1 - First point
 * @param {L.LatLng} point2 - Second point
 * @returns {number} Distance in pixels
 */
export function getPixelDistance(map, point1, point2) {
  const p1 = map.latLngToContainerPoint(point1);
  const p2 = map.latLngToContainerPoint(point2);
  return p1.distanceTo(p2);
}

/**
 * Convert degrees to radians
 * @param {number} degrees - Angle in degrees
 * @returns {number} Angle in radians
 */
export function degreesToRadians(degrees) {
  return degrees * (Math.PI / 180);
}

/**
 * Convert radians to degrees
 * @param {number} radians - Angle in radians
 * @returns {number} Angle in degrees
 */
export function radiansToDegrees(radians) {
  return radians * (180 / Math.PI);
}