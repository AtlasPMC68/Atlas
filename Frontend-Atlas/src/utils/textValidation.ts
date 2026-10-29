import type { Coordinate, Feature } from "../typescript/feature";
import { WORD_TYPE_STYLES } from "./mapLabelUtils";

export interface TextValidationEntry {
  id: string;
  text: string;
  originalText: string;
  selected: boolean;
  coordinates?: [number, number];
  suggestedCity?: string;
  suggestedCoords?: [number, number];
  useSuggestedCity?: boolean;
  wordType?: string;
}

/** Check if a feature is an unrecognized OCR text candidate for validation. */
export function isUnrecognizedTextFeature(feature: Feature, mapId?: string | null): boolean {
  const matchesMap = !mapId || feature.mapId === mapId || !feature.mapId;
  const isRejected = !feature.properties?.recognized;
  const isText =
    Boolean(feature.properties?.isOcrText) ||
    feature.properties?.labelText !== undefined ||
    feature.geometry?.type === "Point";
  return matchesMap && isRejected && isText;
}

/** Convert a GeoJSON feature into a text validation entry. */
export function featureToValidationEntry(
  feature: Feature,
  defaultSelected = true,
): TextValidationEntry {
  const text = feature.properties?.labelText || feature.properties?.name || feature.name || "";
  const originalText = feature.properties?.originalText || text;

  const isUnrecognized = Boolean(feature.properties?.isOcrText && !feature.properties?.recognized);
  const selected = isUnrecognized
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
  const coordinates: Coordinate =
    entry.useSuggestedCity && entry.suggestedCoords
      ? entry.suggestedCoords
      : ((entry.coordinates || feature.geometry?.coordinates) as Coordinate);

  const wordType = entry.wordType || "city";
  const wordStyle = WORD_TYPE_STYLES[wordType] || WORD_TYPE_STYLES.city;
  const transformedText = wordStyle.transform ? wordStyle.transform(entry.text) : entry.text;

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
    },
  };
}
