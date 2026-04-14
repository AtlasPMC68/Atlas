import L from "leaflet";
import type { Feature } from "../typescript/feature";
import type { AtlasRuntimeLayer } from "../typescript/mapLayers";

export const DEFAULT_SYNC_EVENTS = [
  "pm:dragend",
  "pm:markerdragend",
  "pm:vertexadded",
  "pm:vertexremoved",
  "pm:centerplaced",
  "pm:rotateend",
  "pm:scaleend",
  "pm:textblur",
] as const;

export function isAxisAlignedRectangle(
  latLngs: L.LatLngTuple[],
  tolerance = 1e-6,
) {
  if (!Array.isArray(latLngs) || latLngs.length < 4) return false;

  const normalized = latLngs.slice();
  const first = normalized[0];
  const last = normalized[normalized.length - 1];

  if (
    first &&
    last &&
    Math.abs(first[0] - last[0]) <= tolerance &&
    Math.abs(first[1] - last[1]) <= tolerance
  ) {
    normalized.pop();
  }

  if (normalized.length !== 4) return false;

  const roundToTolerance = (v: number) => Math.round(v / tolerance);
  const lats = new Set(normalized.map((p) => roundToTolerance(p[0])));
  const lngs = new Set(normalized.map((p) => roundToTolerance(p[1])));

  return lats.size === 2 && lngs.size === 2;
}

export function rectangleFromLatLngs(
  latLngs: L.LatLngTuple[],
  options: L.PathOptions,
) {
  const lats = latLngs.map((p) => p[0]);
  const lngs = latLngs.map((p) => p[1]);

  const bounds = L.latLngBounds(
    [Math.min(...lats), Math.min(...lngs)],
    [Math.max(...lats), Math.max(...lngs)],
  );

  return L.rectangle(bounds, options);
}

export function setFeatureOnLayer(layer: L.Layer, feature: Feature) {
  Reflect.set(layer, "feature", feature);
}

export function forEachChildLayer(
  layer: L.Layer,
  callback: (childLayer: L.Layer) => void,
) {
  const eachLayer = Reflect.get(layer, "eachLayer");
  if (typeof eachLayer !== "function") return;
  eachLayer.call(layer, callback);
}

export function attachFeatureToLayer(layer: L.Layer, feature: Feature) {
  setFeatureOnLayer(layer, feature);

  forEachChildLayer(layer, (childLayer) => {
    setFeatureOnLayer(childLayer, feature);
  });
}

export function bindLayerEventsOnce(
  layer: L.Layer,
  events: readonly string[],
  handler: () => void,
) {
  const runtimeLayer = layer as AtlasRuntimeLayer;

  if (runtimeLayer.__atlasFeatureEventsBound) return;
  runtimeLayer.__atlasFeatureEventsBound = true;

  events.forEach((eventName) => {
    layer.on(eventName, handler);
  });
}

export function bindRenderedFeatureEvents(
  layer: L.Layer,
  onSync: (layer: L.Layer) => void,
  events: readonly string[] = DEFAULT_SYNC_EVENTS,
) {
  let hasChildren = false;

  forEachChildLayer(layer, (childLayer) => {
    hasChildren = true;
    bindLayerEventsOnce(childLayer, events, () => onSync(childLayer));
  });

  if (!hasChildren) {
    bindLayerEventsOnce(layer, events, () => onSync(layer));
  }
}

export function applyStyleToLayer(layer: L.Layer, style: L.PathOptions) {
  if (layer instanceof L.LayerGroup) {
    layer.eachLayer((child) => applyStyleToLayer(child, style));
  } else if (layer instanceof L.Path) {
    layer.setStyle(style);
  }
}

export function getLayerStrokeColor(layer: L.Layer): string | undefined {
  if (layer instanceof L.LayerGroup) {
    let color: string | undefined;
    layer.eachLayer((child) => { color ??= getLayerStrokeColor(child); });
    return color;
  } else if (layer instanceof L.Path) {
    return layer.options.color;
  }
  return undefined;
}