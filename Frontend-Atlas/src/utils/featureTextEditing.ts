import type { Feature } from "../typescript/feature";
import { getMapElementType } from "./featureHelpers";
import { hexToRgb, rgbToHex } from "./utils";
import {
  applyWordStyleToFeature,
  getWordTypeForFeature,
  isTextFeature,
  normalizeWordType,
  WORD_TYPE_TAXONOMY,
  type WordType,
} from "./wordStyles";

export interface FeatureEditState {
  feature: Feature;
  draft: FeatureEditSubmitPayload;
}

export interface FeatureEditSubmitPayload {
  name: string;
  labelText?: string;
  wordType: WordType;
  colorHex?: string;
  strokeColorHex?: string;
  fillOpacity?: number;
  strokeOpacity?: number;
  strokeWidth?: number;
}

export function prepareFeatureForEdit(feature: Feature): FeatureEditState {
  const isText = isTextFeature(feature);
  const wordType = getWordTypeForFeature(feature);
  const elementType = getMapElementType(feature);
  const rawLabel =
    feature.properties.labelText ?? (isText ? feature.properties.name : undefined);

  return {
    feature,
    draft: {
      name: feature.properties.name,
      labelText: rawLabel,
      wordType,
      colorHex:
        rgbToHex(feature.properties.colorRgb) ??
        (elementType === "label" || elementType === "point"
          ? "#000000"
          : undefined),
      strokeColorHex: rgbToHex(feature.properties.strokeColor),
      fillOpacity: feature.properties.fillOpacity,
      strokeOpacity: feature.properties.strokeOpacity,
      strokeWidth: feature.properties.strokeWidth,
    },
  };
}

export function coerceEditedFeature(
  originalFeature: Feature,
  payload: FeatureEditSubmitPayload,
): Feature {
  if (!isTextFeature(originalFeature)) {
    return {
      ...originalFeature,
      name: payload.name,
      properties: {
        ...originalFeature.properties,
        name: payload.name,
        colorRgb: hexToRgb(payload.colorHex),
        strokeColor: hexToRgb(payload.strokeColorHex),
        fillOpacity: payload.fillOpacity,
        strokeOpacity: payload.strokeOpacity,
        strokeWidth: payload.strokeWidth,
      },
    };
  }

  const styledFeature = applyWordStyleToFeature(
    originalFeature,
    payload.wordType,
    payload.name,
    payload.labelText ?? payload.name,
  );
  const isLabel = styledFeature.properties.mapElementType === "label";

  return {
    ...styledFeature,
    properties: {
      ...styledFeature.properties,
      colorRgb: hexToRgb(payload.colorHex),
      strokeColor: isLabel ? undefined : hexToRgb(payload.strokeColorHex),
      fillOpacity: isLabel ? undefined : payload.fillOpacity,
      strokeOpacity: isLabel ? undefined : payload.strokeOpacity,
      strokeWidth: isLabel ? undefined : payload.strokeWidth,
    },
  };
}

export function getWordTypePreviewStyle(
  wordType: string,
  colorHex?: string,
): {
  fontStyle?: "normal" | "italic";
  textTransform?: "uppercase";
  color?: string;
  fontSize: string;
} {
  const taxonomy = WORD_TYPE_TAXONOMY[normalizeWordType(wordType)];
  return {
    fontStyle: taxonomy.fontStyle !== "normal" ? taxonomy.fontStyle : undefined,
    textTransform:
      taxonomy.textTransform === "uppercase" ? "uppercase" : undefined,
    color: colorHex || undefined,
    fontSize: `${taxonomy.sizePx}px`,
  };
}
