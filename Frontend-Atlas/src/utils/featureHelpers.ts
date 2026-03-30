import type {
  MapElementType,
} from "../typescript/feature";

export function getMapElementType(feature: {
  properties?: { mapElementType?: MapElementType };
}): MapElementType | null {
  return feature.properties?.mapElementType ?? null;
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
