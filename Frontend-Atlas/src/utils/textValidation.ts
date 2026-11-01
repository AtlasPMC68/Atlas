import { ValidationStatus, type Coordinate, type Feature } from "../typescript/feature";

export { ValidationStatus };

export interface TextValidationEntry {
  id: string;
  text: string;
  originalText: string;
  selected: boolean;
  validationStatus?: ValidationStatus | `${ValidationStatus}`;
  coordinates?: [number, number];
  suggestedCity?: string;
  suggestedCoords?: [number, number];
  useSuggestedCity?: boolean;
}

/** Check if a feature is an unrecognized OCR text candidate for validation. */
export function isUnrecognizedTextFeature(feature: Feature, mapId?: string | null): boolean {
  const matchesMap = !mapId || feature.mapId === mapId || !feature.mapId;
  const status = feature.properties?.validationStatus ?? feature.properties?.validation_status;
  if (status === ValidationStatus.ACCEPTED || status === ValidationStatus.REJECTED) {
    return false;
  }
  const isCandidate =
    status === ValidationStatus.MANUAL_REVIEW ||
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

  const status = feature.properties?.validationStatus ?? feature.properties?.validation_status;
  const isUnrecognized = Boolean(feature.properties?.isOcrText && !feature.properties?.recognized);
  const selected =
    status === ValidationStatus.ACCEPTED
      ? true
      : status === ValidationStatus.REJECTED
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
      status ??
      (selected
        ? ValidationStatus.ACCEPTED
        : isUnrecognized
        ? ValidationStatus.MANUAL_REVIEW
        : ValidationStatus.REJECTED),
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
  const validationStatus: ValidationStatus = isSelected
    ? ValidationStatus.ACCEPTED
    : ValidationStatus.REJECTED;

  if (!isSelected) {
    return {
      ...feature,
      properties: {
        ...feature.properties,
        show: false,
        recognized: false,
        validationStatus,
        validation_status: validationStatus,
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
      validation_status: validationStatus,
    },
  };
}
