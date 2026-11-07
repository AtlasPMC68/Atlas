import {
  type SuggestedPlace,
  ValidationStatus,
  type Coordinate,
  type Feature,
} from "../typescript/feature";
import type { CustomLabelStyle } from "./labelPresentation";
import type { WordType } from "./wordStyles";
import {
  applyWordStyleToFeature,
  getWordTypeForFeature,
  isTextFeature,
} from "./wordStyles";
import { applyCustomLabelStyleToFeature } from "./featureTextEditing";
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
  originalCoordinates?: [number, number];
  suggestedPlace?: SuggestedPlace;
  useSuggestedPlace?: boolean;
  wordType?: WordType;
  labelStyleSelection?: string;
  customLabelStyleId?: string | null;
  customLabelStyle?: CustomLabelStyle | null;
}

/**
 * Return true if a suggestion originates from geographic_entities.json
 * (provinces, states, lakes, rivers, oceans, countries, etc.), rather than a city (from GeoNames)
 * or a local radius proximity suggestion.
 */
export function isJsonSuggestion(item: TextValidationEntry): boolean {
  if (!item.suggestedPlace) return false;
  if (item.suggestedPlace.source === "json") return true;
  if (item.suggestedPlace.source === "nearby" || item.suggestedPlace.source === "geonames") {
    return false;
  }
  const type = item.suggestedPlace.type;
  return Boolean(type && type !== "city");
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
    originalCoordinates: coordinates ? [coordinates[0], coordinates[1]] : undefined,
    suggestedPlace: feature.properties?.suggestedPlace,
    wordType,
    labelStyleSelection: feature.properties?.customLabelStyleId
      ? `custom:${feature.properties.customLabelStyleId}`
      : wordType,
    customLabelStyleId: feature.properties?.customLabelStyleId,
    customLabelStyle: feature.properties?.customLabelStyle,
  };
}

/** Apply a validation decision, selected word type, and coordinates atomically. */
export function applyValidationToFeature(
  feature: Feature,
  entry: TextValidationEntry,
): Feature {
  const isSelected = Boolean(entry.selected);
  const wordType = entry.wordType || "city";
  const styledFeature =
    entry.customLabelStyleId && entry.customLabelStyle
      ? applyCustomLabelStyleToFeature(
          feature,
          entry.customLabelStyle,
          wordType,
          entry.text,
          entry.text,
        )
      : applyWordStyleToFeature(feature, wordType, entry.text);
  const shouldUseSuggestedCoords =
    entry.useSuggestedPlace &&
    entry.suggestedPlace &&
    !isJsonSuggestion(entry);

  const coordinates: Coordinate | undefined = isSelected
    ? shouldUseSuggestedCoords
      ? entry.suggestedPlace!.coordinates
      : ((entry.coordinates || feature.geometry?.coordinates) as Coordinate)
    : undefined;
  const validationStatus = isSelected
    ? ValidationStatus.ACCEPTED
    : ValidationStatus.REJECTED;
  const styledProperties = { ...styledFeature.properties };
  if (!entry.customLabelStyleId || !entry.customLabelStyle) {
    delete styledProperties.customLabelStyleId;
    delete styledProperties.customLabelStyle;
    delete styledProperties.customLabelStyleFallbackWordType;
  }
  const properties = synchronizeValidationState(
    {
      ...styledProperties,
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
