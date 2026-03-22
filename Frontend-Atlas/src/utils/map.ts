import { MAP_CONFIG } from "../composables/useMapConfig";

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
