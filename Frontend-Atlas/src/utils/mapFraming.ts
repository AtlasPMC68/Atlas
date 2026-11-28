import L from "leaflet";

export interface SmartFramingOptions {
  mapLevelZoom?: number;
  animate?: boolean;
  multi?: boolean;
}

export type FramingResult = "in-view" | "panned" | "view-set" | "bounds-fitted";

/**
 * Frames targetBounds according to the current viewport:
 * - Fully inside pad(-0.05) → "in-view" (no camera move).
 * - Intersects or center in view but clipped → panTo ("panned").
 * - Outside view, zoomed in past mapLevelZoom → panTo keeping zoom ("panned").
 * - Outside view at overview zoom → setView or fitBounds ("view-set" / "bounds-fitted").
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

  const fullyInside = currentViewBounds.pad(-0.05).contains(targetBounds);
  if (fullyInside) {
    return "in-view";
  }

  if (
    currentViewBounds.contains(targetBounds.getCenter()) ||
    currentViewBounds.intersects(targetBounds)
  ) {
    map.panTo(targetBounds.getCenter(), { animate });
    return "panned";
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
