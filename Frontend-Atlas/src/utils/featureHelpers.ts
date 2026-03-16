import type { MapElementType } from "../typescript/feature";

export function getMapElementType(feature: {
  properties?: { mapElementType?: MapElementType };
}): MapElementType | null {
  return feature.properties?.mapElementType ?? null;
}
