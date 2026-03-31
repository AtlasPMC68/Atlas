import type {
  Feature,
  FeatureProperties,
  MapElementType,
} from "../typescript/feature";

export function getMapElementType(
  featureOrProperties: Pick<Feature, "properties" | "geometry"> | FeatureProperties,
): MapElementType | null {
  const hasProperties = "properties" in featureOrProperties;
  const properties = hasProperties
    ? featureOrProperties.properties
    : featureOrProperties;

  const geometry = hasProperties ? featureOrProperties.geometry : undefined;
  const rawType = properties?.mapElementType;

  if (rawType) {
    return rawType;
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
