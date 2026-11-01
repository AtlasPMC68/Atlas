import {
  ValidationStatus,
  type Coordinate,
  type Feature,
} from "../typescript/feature";
import { WORD_TYPE_STYLES } from "./mapLabelUtils";

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

  const rawType = (
    feature.properties?.rawType ||
    feature.properties?.type ||
    ""
  ).toLowerCase();
  const elemType = feature.properties?.mapElementType;
  const wordType = rawType && WORD_TYPE_STYLES[rawType]
    ? rawType
    : elemType === "label"
      ? "province"
      : "city";

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

/** Apply user validation choices to a feature. */
export function applyValidationToFeature(
  feature: Feature,
  entry: TextValidationEntry,
): Feature {
  const isSelected = Boolean(entry.selected);
  const validationStatus: ValidationStatus = isSelected
    ? ValidationStatus.ACCEPTED
    : ValidationStatus.REJECTED;

  const wordType = entry.wordType || "city";
  const wordStyle = WORD_TYPE_STYLES[wordType] || WORD_TYPE_STYLES.city;
  const transformedText = wordStyle.transform ? wordStyle.transform(entry.text) : entry.text;

  if (!isSelected || validationStatus === ValidationStatus.REJECTED) {
    return {
      ...feature,
      name: transformedText || feature.properties?.name || feature.name,
      properties: {
        ...feature.properties,
        name: transformedText || feature.properties?.name || feature.name,
        rawType: wordType,
        mapElementType: wordStyle.mapElementType,
        show: false,
        recognized: false,
        userSelected: false,
        validationStatus,
        validation_status: validationStatus,
      },
    };
  }

  const coordinates: Coordinate =
    entry.useSuggestedCity && entry.suggestedCoords
      ? entry.suggestedCoords
      : ((entry.coordinates || feature.geometry?.coordinates) as Coordinate);

  const isAccepted = Boolean(entry.selected);

  return {
    ...feature,
    name: transformedText,
    geometry: {
      type: "Point",
      coordinates,
    },
    properties: {
      ...feature.properties,
      name: transformedText,
      labelText: transformedText,
      mapElementType: wordStyle.mapElementType,
      sizePx: wordStyle.sizePx,
      fontStyle: wordStyle.fontStyle,
      rawType: wordType,
      type: wordType,
      show: isAccepted,
      recognized: isAccepted,
      userSelected: isAccepted,
      validationStatus,
      validation_status: validationStatus,
    },
  };
}
