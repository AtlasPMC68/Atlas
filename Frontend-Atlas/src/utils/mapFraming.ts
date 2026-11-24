import L from "leaflet";

export interface SmartFramingOptions {
  mapLevelZoom?: number;
  animate?: boolean;
  multi?: boolean;
}

export type FramingResult = "in-view" | "panned" | "view-set" | "bounds-fitted";

/**
 * Frames targetBounds smartly according to current viewport and zoom level:
 * - If targetBounds is already visible in viewport (intersects or contains center), does nothing ("in-view").
 * - If targetBounds is outside viewport and user is zoomed in (currentZoom > mapLevelZoom), pans to center keeping zoom ("panned").
 * - If targetBounds is outside viewport at overview zoom, zooms/centers to mapLevelZoom ("view-set" or "bounds-fitted").
 */
export function applySmartFeatureFraming(
  map: L.Map,
  targetBounds: L.LatLngBounds,
  options: SmartFramingOptions = {},
): FramingResult {
  if (!map || !targetBounds.isValid()) return "in-view";

  const currentViewBounds = map.getBounds();
  const currentZoom = map.getZoom();
  const mapLevelZoom = options.mapLevelZoom ?? Math.min(currentZoom, 5);
  const animate = options.animate ?? false;

  const isInsideFieldOfView =
    currentViewBounds.contains(targetBounds.getCenter()) ||
    currentViewBounds.intersects(targetBounds);

  if (isInsideFieldOfView) {
    // Feature is already visible in viewport - do not move or pan the map at all
    return "in-view";
  }

  // Feature is outside viewport:
  // If user is already zoomed in deeper than overview level, keep current zoom and pan to target
  if (currentZoom > mapLevelZoom) {
    map.panTo(targetBounds.getCenter(), { animate });
    return "panned";
  }

  if (options.multi) {
    map.fitBounds(targetBounds, { padding: [80, 80], maxZoom: mapLevelZoom, animate });
    return "bounds-fitted";
  } else {
    map.setView(targetBounds.getCenter(), mapLevelZoom, { animate });
    return "view-set";
  }
}
