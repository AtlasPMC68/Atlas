import type { Coordinate, Feature, ValidationStatus } from "../typescript/feature";

export type { ValidationStatus };

export interface TextValidationEntry {
  id: string;
  text: string;
  originalText: string;
  selected: boolean;
  validationStatus?: ValidationStatus;
  coordinates?: [number, number];
  suggestedCity?: string;
  suggestedCoords?: [number, number];
  useSuggestedCity?: boolean;
}

/** Check if a feature is an unrecognized OCR text candidate for validation. */
export function isUnrecognizedTextFeature(feature: Feature, mapId?: string | null): boolean {
  const matchesMap = !mapId || feature.mapId === mapId || !feature.mapId;
  const status = feature.properties?.validationStatus;
  if (status === "accepted" || status === "rejected") {
    return false;
  }
  const isCandidate =
    status === "manual_review" ||
    (!feature.properties?.recognized && feature.properties?.show === false);
  const isText =
    Boolean(feature.properties?.isOcrText) ||
    feature.properties?.labelText !== undefined ||
    feature.geometry?.type === "Point";
  return matchesMap && isCandidate && isText;
}

/** Convert a GeoJSON feature into a text validation entry. */
export function featureToValidationEntry(
  feature: Feature,
  defaultSelected = true,
): TextValidationEntry {
  const text = feature.properties?.labelText || feature.properties?.name || feature.name || "";
  const originalText = feature.properties?.originalText || text;

  const status = feature.properties?.validationStatus;
  const isUnrecognized = Boolean(feature.properties?.isOcrText && !feature.properties?.recognized);
  const selected =
    status === "accepted"
      ? true
      : status === "rejected"
      ? false
      : isUnrecognized
      ? (feature.properties?.userSelected !== undefined
          ? Boolean(feature.properties.userSelected)
          : defaultSelected)
      : (feature.properties?.show !== undefined
          ? Boolean(feature.properties.show)
          : defaultSelected);

  const coordinates =
    feature.geometry?.type === "Point" && Array.isArray(feature.geometry.coordinates)
      ? (feature.geometry.coordinates as [number, number])
      : undefined;

  return {
    id: feature.id,
    text,
    originalText,
    selected,
    validationStatus:
      status ?? (selected ? "accepted" : isUnrecognized ? "manual_review" : "rejected"),
    coordinates,
    suggestedCity: feature.properties?.suggestedCity,
    suggestedCoords: feature.properties?.suggestedCoords,
  };
}

/** Apply user validation choices to a feature. */
export function applyValidationToFeature(
  feature: Feature,
  entry: TextValidationEntry,
): Feature {
  const isSelected = Boolean(entry.selected);
  const validationStatus: ValidationStatus = isSelected ? "accepted" : "rejected";

  if (!isSelected) {
    return {
      ...feature,
      properties: {
        ...feature.properties,
        show: false,
        recognized: false,
        validationStatus,
      },
    };
  }

  const coordinates: Coordinate =
    entry.useSuggestedCity && entry.suggestedCoords
      ? entry.suggestedCoords
      : ((entry.coordinates || feature.geometry?.coordinates) as Coordinate);

  return {
    ...feature,
    name: entry.text,
    geometry: {
      type: "Point",
      coordinates,
    },
    properties: {
      ...feature.properties,
      name: entry.text,
      ...(feature.properties?.labelText !== undefined ? { labelText: entry.text } : {}),
      show: true,
      recognized: true,
      validationStatus,
    },
  };
}
