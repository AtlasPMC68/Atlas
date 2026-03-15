import { MAP_CONFIG as MAP_CONFIG_RAW } from "../composables/useMapConfig.js";

type MapConfig = {
  BASE_ZOOM: number;
  BASE_RADIUS: number;
  ZOOM_FACTOR: number;
};

const MAP_CONFIG = MAP_CONFIG_RAW as MapConfig;

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
 * Convert value to array if not already an array
 * @param {*} maybeArray - Value to convert
 * @returns {Array} Array representation
 */
export function toArray<T>(maybeArray: T | T[] | null | undefined): T[] {
  if (Array.isArray(maybeArray)) return maybeArray;
  if (maybeArray == null) return []; // null or undefined
  return [maybeArray]; // wrap single object
}
