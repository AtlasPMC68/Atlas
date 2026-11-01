import {
  ValidationStatus,
  type Coordinate,
  type Feature,
} from "../typescript/feature";
import {
  applyWordStyleToFeature,
  getWordTypeForFeature,
  isTextFeature,
} from "./mapLabelUtils";

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
  wordType?: string;
}

/** Check if a feature is an unrecognized OCR text candidate for validation. */
export function isUnrecognizedTextFeature(feature: Feature, mapId?: string | null): boolean {
  const matchesMap = !mapId || feature.mapId === mapId || !feature.mapId;
  const status = feature.properties?.validationStatus ?? feature.properties?.validation_status;
  if (status === ValidationStatus.ACCEPTED) {
    return false;
  }
  const isCandidate =
    status === ValidationStatus.MANUAL_REVIEW ||
    status === ValidationStatus.REJECTED ||
    (!feature.properties?.recognized && feature.properties?.show === false);
  return matchesMap && isCandidate && isTextFeature(feature);
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

  const wordType = getWordTypeForFeature(feature);

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
    wordType,
  };
}

/** Update the validation lifecycle state of a feature (show, recognized, validationStatus, coords). */
export function applyValidationStateToFeature(
  feature: Feature,
  isAccepted: boolean,
  coordinates?: Coordinate,
): Feature {
  const validationStatus = isAccepted ? ValidationStatus.ACCEPTED : ValidationStatus.REJECTED;
  const updatedGeometry = coordinates
    ? { ...feature.geometry, type: "Point" as const, coordinates }
    : feature.geometry;

  return {
    ...feature,
    geometry: updatedGeometry,
    properties: {
      ...feature.properties,
      show: isAccepted,
      recognized: isAccepted,
      userSelected: isAccepted,
      validationStatus,
      validation_status: validationStatus,
    },
  };
}

/** Apply user validation choices to a feature by composing word styling and validation state. */
export function applyValidationToFeature(
  feature: Feature,
  entry: TextValidationEntry,
): Feature {
  const isSelected = Boolean(entry.selected);
  const wordType = entry.wordType || "city";

  // 1. Formatting & Visual styling
  const styledFeature = applyWordStyleToFeature(feature, wordType, entry.text);

  // 2. Coordinates
  const coordinates: Coordinate | undefined = isSelected
    ? entry.useSuggestedCity && entry.suggestedCoords
      ? entry.suggestedCoords
      : ((entry.coordinates || feature.geometry?.coordinates) as Coordinate)
    : undefined;

  // 3. Validation lifecycle state
  return applyValidationStateToFeature(styledFeature, isSelected, coordinates);
}
