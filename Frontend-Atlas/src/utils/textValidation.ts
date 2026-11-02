import {
  ValidationStatus,
  type Coordinate,
  type Feature,
} from "../typescript/feature";
import type { WordType } from "./wordStyles";
import {
  applyWordStyleToFeature,
  getWordTypeForFeature,
  isTextFeature,
} from "./wordStyles";
import {
  getFeatureReviewState,
  getFeatureValidationStatus,
  isFeatureSelectedForValidation,
  isTextValidationReviewCandidate,
  synchronizeValidationState,
} from "./featureValidationState";

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
  wordType?: WordType;
}

/** Check if a feature is an unrecognized OCR text candidate for validation. */
export function isUnrecognizedTextFeature(feature: Feature, mapId?: string | null): boolean {
  const matchesMap = !mapId || feature.mapId === mapId || !feature.mapId;
  return (
    matchesMap &&
    isTextValidationReviewCandidate(feature) &&
    isTextFeature(feature)
  );
}

/** Convert a GeoJSON feature into a text validation entry. */
export function featureToValidationEntry(
  feature: Feature,
  defaultSelected = true,
): TextValidationEntry {
  const text = feature.properties?.labelText || feature.properties?.name || feature.name || "";
  const originalText = feature.properties?.originalText || text;

  const status = getFeatureValidationStatus(feature);
  const reviewState = getFeatureReviewState(feature);
  const selected = isFeatureSelectedForValidation(feature, defaultSelected);

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
        : reviewState === ValidationStatus.MANUAL_REVIEW
        ? ValidationStatus.MANUAL_REVIEW
        : ValidationStatus.REJECTED),
    coordinates,
    suggestedCity: feature.properties?.suggestedCity,
    suggestedCoords: feature.properties?.suggestedCoords,
    wordType,
  };
}

/** Apply a validation decision, selected word type, and coordinates atomically. */
export function applyValidationToFeature(
  feature: Feature,
  entry: TextValidationEntry,
): Feature {
  const isSelected = Boolean(entry.selected);
  const wordType = entry.wordType || "city";
  const styledFeature = applyWordStyleToFeature(feature, wordType, entry.text);
  const coordinates: Coordinate | undefined = isSelected
    ? entry.useSuggestedCity && entry.suggestedCoords
      ? entry.suggestedCoords
      : ((entry.coordinates || feature.geometry?.coordinates) as Coordinate)
    : undefined;
  const validationStatus = isSelected
    ? ValidationStatus.ACCEPTED
    : ValidationStatus.REJECTED;
  const properties = synchronizeValidationState(
    {
      ...styledFeature.properties,
      userSelected: isSelected,
    },
    validationStatus,
  );

  return {
    ...styledFeature,
    geometry: coordinates
      ? { ...styledFeature.geometry, type: "Point", coordinates }
      : styledFeature.geometry,
    properties,
  };
}
