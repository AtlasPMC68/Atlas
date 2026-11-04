import type { Feature } from "../typescript/feature";
import type { CustomLabelStyle } from "./labelPresentation";
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
  labelStyleSelection?: string;
  customLabelStyleId?: string;
  customLabelStyle?: CustomLabelStyle;
}

export function applyCustomLabelStyleToFeature(
  feature: Feature,
  style: CustomLabelStyle,
  wordType: WordType,
  name: string,
  labelText: string,
): Feature {
  const formattedText =
    style.textTransform === "uppercase" ? labelText.toUpperCase() : labelText;
  const styledFeature = applyWordStyleToFeature(
    feature,
    wordType,
    name,
    formattedText,
  );
  const isBold = Boolean(style.bold || style.fontWeight === "bold");
  const targetElementType =
    style.mapElementType ?? styledFeature.properties.mapElementType ?? "point";
  return {
    ...styledFeature,
    name,
    properties: {
      ...styledFeature.properties,
      name,
      labelText: formattedText,
      mapElementType: targetElementType,
      rawType: "custom",
      type: "custom",
      customLabelStyleId: style.id,
      customLabelStyle: style,
      customLabelStyleFallbackWordType: wordType,
      sizePx: style.sizePx,
      fontStyle: style.fontStyle || "normal",
      fontWeight: isBold ? "bold" : "normal",
      bold: isBold,
      colorRgb: hexToRgb(style.color),
      strokeColor: targetElementType === "label" ? undefined : styledFeature.properties.strokeColor,
      fillOpacity: targetElementType === "label" ? undefined : styledFeature.properties.fillOpacity,
      strokeOpacity: targetElementType === "label" ? undefined : styledFeature.properties.strokeOpacity,
      strokeWidth: targetElementType === "label" ? undefined : styledFeature.properties.strokeWidth,
    },
  };
}

export function removeCustomLabelStyleFromFeature(feature: Feature): Feature {
  const fallbackWordType =
    typeof feature.properties.customLabelStyleFallbackWordType === "string"
      ? normalizeWordType(feature.properties.customLabelStyleFallbackWordType)
      : getMapElementType(feature) === "label"
        ? "province"
        : "city";
  const restored = applyWordStyleToFeature(
    feature,
    fallbackWordType,
    feature.properties.name,
    feature.properties.labelText ?? feature.properties.name,
  );
  const properties = { ...restored.properties };
  properties.customLabelStyleId = null as any;
  properties.customLabelStyle = null as any;
  (properties as Record<string, unknown>).custom_label_style_id = null;
  delete properties.customLabelStyleFallbackWordType;
  return { ...restored, properties };
}

export function prepareFeatureForEdit(feature: Feature): FeatureEditState {
  const isText = isTextFeature(feature);
  const wordType = feature.properties.customLabelStyleFallbackWordType
    ? normalizeWordType(feature.properties.customLabelStyleFallbackWordType)
    : getWordTypeForFeature(feature);
  const elementType = getMapElementType(feature);
  const rawLabel =
    feature.properties.labelText ?? (isText ? feature.properties.name : undefined);

  return {
    feature,
    draft: {
      name: feature.properties.name,
      labelText: rawLabel,
      wordType,
      labelStyleSelection: feature.properties.customLabelStyleId
        ? `custom:${feature.properties.customLabelStyleId}`
        : wordType,
      customLabelStyleId: feature.properties.customLabelStyleId,
      customLabelStyle: feature.properties.customLabelStyle,
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
  if (payload.customLabelStyleId && payload.customLabelStyle) {
    return applyCustomLabelStyleToFeature(
      originalFeature,
      payload.customLabelStyle,
      payload.wordType,
      payload.name,
      payload.labelText ?? payload.name,
    );
  }
  const isLabel = styledFeature.properties.mapElementType === "label";

  return {
    ...styledFeature,
    properties: {
      ...styledFeature.properties,
      customLabelStyleId: null as any,
      customLabelStyle: null as any,
      custom_label_style_id: null,
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
