import type {
  Coordinate,
  Feature,
  FeatureProperties,
  Geometry,
  MapElementType,
} from "../typescript/feature";
import wordTaxonomy from "../../../shared/word-taxonomy.json";

export function upsertFeature(features: Feature[], feature: Feature): Feature[] {
  const next = [...features];
  const index = next.findIndex((f) => f.id === feature.id);
  if (index >= 0) {
    next[index] = feature;
    return next;
  }
  next.push(feature);
  return next;
}

export function getMapElementType(
  featureOrProperties: Pick<Feature, "properties" | "geometry"> | FeatureProperties,
): MapElementType | null {
  const hasProperties = "properties" in featureOrProperties;
  const properties = hasProperties
    ? featureOrProperties.properties
    : featureOrProperties;

  const geometry = hasProperties ? featureOrProperties.geometry : undefined;
  const rawMapElementType = properties?.mapElementType;
  const rawWordType = String(properties?.rawType || properties?.type || "")
    .toLowerCase();
  const isTextElement =
    geometry?.type === "Point" ||
    rawMapElementType === "label" ||
    rawMapElementType === "point";
  const taxonomyEntry = Object.prototype.hasOwnProperty.call(
    wordTaxonomy.types,
    rawWordType,
  )
    ? wordTaxonomy.types[rawWordType as keyof typeof wordTaxonomy.types]
    : undefined;

  if (isTextElement && taxonomyEntry) {
    return taxonomyEntry.mapElementType === "point" ? "point" : "label";
  }

  if (
    rawMapElementType === "point" ||
    rawMapElementType === "zone" ||
    rawMapElementType === "polyline" ||
    rawMapElementType === "arrow" ||
    rawMapElementType === "shape" ||
    rawMapElementType === "label" ||
    rawMapElementType === "image"
  ) {
    return rawMapElementType;
  }

  if (geometry?.type === "LineString") {
    return "polyline";
  }

  if (geometry?.type === "Point") {
    return properties?.labelText ? "label" : "point";
  }

  if (geometry?.type === "Polygon" || geometry?.type === "MultiPolygon") {
    return properties?.shapeKind ? "shape" : "zone";
  }

  return null;
}

function isValidRgbTuple(value: unknown): value is [number, number, number] {
  return (
    Array.isArray(value) &&
    value.length === 3 &&
    value.every((channel) => typeof channel === "number")
  );
}

export function colorRgbToCss(rgb: unknown): string | null {
  if (!isValidRgbTuple(rgb)) return null;
  return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}

export function getDefaultLayer(type: MapElementType | string | null): number {
  switch (type) {
    case "zone": return 0;
    case "shape": return 1;
    case "polyline": return 2;
    case "arrow": return 3;
    case "point": return 4;
    case "label": return 5;
    // custom image isn't working with layer, it's working with z-index
    // so it will always be on top of the canvas.
    case "image": return 99;
    default: return 6;
  }
}

/**
 * Checks if a feature can be copied and pasted on the map.
 * All standard map elements (texts, points, zones, lines, shapes, images) are copyable,
 * except legend features or invalid geometries.
 */
export function isCopyableFeature(
  feature: Feature | null | undefined,
): feature is Feature {
  if (!feature || !feature.geometry) return false;
  const props = feature.properties;
  if (
    props?.mapElementType === "legend" ||
    props?.type === "legend" ||
    Boolean(props?.isLegend)
  ) {
    return false;
  }
  return true;
}

/**
 * Returns a reference anchor coordinate [lng, lat] from a geometry.
 */
export function getGeometryAnchor(geometry: Geometry): Coordinate | null {
  switch (geometry.type) {
    case "Point":
      return geometry.coordinates;
    case "MultiPoint":
      return geometry.coordinates[0] ?? null;
    case "LineString":
      return geometry.coordinates[0] ?? null;
    case "MultiLineString":
      return geometry.coordinates[0]?.[0] ?? null;
    case "Polygon":
      return geometry.coordinates[0]?.[0] ?? null;
    case "MultiPolygon":
      return geometry.coordinates[0]?.[0]?.[0] ?? null;
    default:
      return null;
  }
}

/**
 * Offsets all coordinates in a geometry by [deltaLng, deltaLat].
 */
export function offsetGeometry(
  geometry: Geometry,
  deltaLng: number,
  deltaLat: number,
): Geometry {
  switch (geometry.type) {
    case "Point":
      return {
        type: "Point",
        coordinates: [
          geometry.coordinates[0] + deltaLng,
          geometry.coordinates[1] + deltaLat,
        ],
      };
    case "MultiPoint":
      return {
        type: "MultiPoint",
        coordinates: geometry.coordinates.map(([lng, lat]) => [
          lng + deltaLng,
          lat + deltaLat,
        ]),
      };
    case "LineString":
      return {
        type: "LineString",
        coordinates: geometry.coordinates.map(([lng, lat]) => [
          lng + deltaLng,
          lat + deltaLat,
        ]),
      };
    case "MultiLineString":
      return {
        type: "MultiLineString",
        coordinates: geometry.coordinates.map((line) =>
          line.map(([lng, lat]) => [lng + deltaLng, lat + deltaLat]),
        ),
      };
    case "Polygon":
      return {
        type: "Polygon",
        coordinates: geometry.coordinates.map((ring) =>
          ring.map(([lng, lat]) => [lng + deltaLng, lat + deltaLat]),
        ),
      };
    case "MultiPolygon":
      return {
        type: "MultiPolygon",
        coordinates: geometry.coordinates.map((polygon) =>
          polygon.map((ring) =>
            ring.map(([lng, lat]) => [lng + deltaLng, lat + deltaLat]),
          ),
        ),
      };
    default:
      return geometry;
  }
}

/**
 * Deep clones a feature with a translated geometry and properties offset,
 * a fresh UUID, and current timestamps.
 */
export function cloneFeatureWithOffset(
  source: Feature,
  deltaLng: number,
  deltaLat: number,
  newId: string = crypto.randomUUID(),
  now: string = new Date().toISOString(),
): Feature {
  const clonedProps = JSON.parse(JSON.stringify(source.properties || {}));

  // Also offset bounds if present (e.g. for image or shape bounds [[south, west], [north, east]])
  if (Array.isArray(clonedProps.bounds) && clonedProps.bounds.length === 2) {
    const [b1, b2] = clonedProps.bounds;
    if (
      Array.isArray(b1) &&
      Array.isArray(b2) &&
      b1.length === 2 &&
      b2.length === 2
    ) {
      clonedProps.bounds = [
        [b1[0] + deltaLat, b1[1] + deltaLng],
        [b2[0] + deltaLat, b2[1] + deltaLng],
      ];
    }
  }

  const newGeometry = offsetGeometry(source.geometry, deltaLng, deltaLat);
  const label =
    source.properties?.labelText || source.properties?.name || source.name;

  const isZone =
    getMapElementType(source) === "zone" ||
    source.properties?.mapElementType === "zone";

  const targetMapId = isZone ? null : (source.mapId ?? null);

  if (isZone) {
    clonedProps.mapId = null;
    clonedProps.map_id = null;
    delete clonedProps.mapTitle;
  }

  return {
    ...source,
    id: newId,
    mapId: targetMapId,
    ...(isZone ? { map_id: null } : {}),
    name: label,
    geometry: newGeometry,
    properties: {
      ...clonedProps,
      name: label,
      ...(source.properties?.labelText ? { labelText: label } : {}),
    },
    createdAt: now,
    updatedAt: now,
    ...(source.image ? { image: source.image } : {}),
  };
}
