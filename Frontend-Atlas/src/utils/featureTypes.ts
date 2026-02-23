/**
 * Canonical “domain type” for Atlas features.
 * We store it in feature.properties.mapElementType to avoid clashing with GeoJSON's `type`.
 *
 * Supported values (frontend):
 *  - point
 *  - zone
 *  - polyline
 *  - arrow
 *  - shape   (with feature.properties.shapeKind: square|rectangle|circle|triangle|oval)
 */
export function getMapElementType(feature: any) {
  return feature?.properties?.mapElementType ?? null;
}

const SHAPE_KINDS = new Set([
  "square",
  "rectangle",
  "circle",
  "triangle",
  "oval",
]);

export function normalizeFeatureType(feature: any) {
  if (!feature || typeof feature !== "object") return feature;

  const f = feature;

  if (!f.properties || typeof f.properties !== "object") {
    f.properties = {};
  }

  const current = f.properties.mapElementType;

  if (typeof current === "string" && current.length > 0) {
    if (SHAPE_KINDS.has(current)) {
      f.properties.mapElementType = "shape";
      if (!f.properties.shapeKind) f.properties.shapeKind = current;
    }
    return f;
  }

  const legacy = typeof f.type === "string" ? f.type : null;

  if (legacy) {
    if (SHAPE_KINDS.has(legacy)) {
      f.properties.mapElementType = "shape";
      if (!f.properties.shapeKind) f.properties.shapeKind = legacy;
    } else if (legacy === "polygon") {
      f.properties.mapElementType = "zone";
    } else {
      f.properties.mapElementType = legacy;
    }
    return f;
  }

  const gtype = f.geometry?.type;
  if (gtype === "Point") f.properties.mapElementType = "point";
  else if (gtype === "LineString") f.properties.mapElementType = "polyline";
  else if (gtype === "Polygon" || gtype === "MultiPolygon")
    f.properties.mapElementType = "zone";

  return f;
}

export function normalizeFeatures(features: any) {
  if (!Array.isArray(features)) return features;
  return features.map((f) => normalizeFeatureType(f));
}
