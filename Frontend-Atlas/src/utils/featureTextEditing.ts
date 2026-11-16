import type { Feature } from "../typescript/feature";
import { normalizeTextSizePx, type CustomLabelStyle } from "./labelPresentation";
import { getFeatureMapId, getMapElementType } from "./featureHelpers";
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
  /** Label text colour of a point element, set apart from its symbol's colour. */
  textColorHex?: string;
  /** Label size in px; the word type's size when left untouched. */
  textSizePx?: number;
  strokeColorHex?: string;
  fillOpacity?: number;
  strokeOpacity?: number;
  strokeWidth?: number;
  labelStyleSelection?: string;
  customLabelStyleId?: string | null;
  customLabelStyle?: CustomLabelStyle | null;
  selectedMapIds?: string[];
}

export const MAX_STROKE_WIDTH_PX = 50;
export const DEFAULT_POINT_STROKE_OPACITY = 1;

/**
 * An opacity as Leaflet expects it, in [0, 1]. Number inputs hand back strings
 * and accept anything typed, so the form value is not trusted as is.
 */
export function normalizeOpacity(value: unknown): number | undefined {
  if (value === null || value === undefined || value === "") return undefined;
  const opacity = Number(value);
  if (!Number.isFinite(opacity)) return undefined;
  return Math.max(0, Math.min(1, opacity));
}

export function normalizeStrokeWidth(value: unknown): number | undefined {
  if (value === null || value === undefined || value === "") return undefined;
  const width = Number(value);
  if (!Number.isFinite(width)) return undefined;
  return Math.max(0, Math.min(MAX_STROKE_WIDTH_PX, width));
}

export function getDefaultTextSizePx(wordType: string | undefined): number {
  return WORD_TYPE_TAXONOMY[normalizeWordType(wordType)].sizePx;
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
  properties.customLabelStyleId = null;
  properties.customLabelStyle = null;
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

  const mapId = getFeatureMapId(feature);
  const initialMapIds = mapId ? [mapId] : [];
  const colorHex =
    rgbToHex(feature.properties.colorRgb) ??
    (elementType === "label" || elementType === "point" ? "#000000" : undefined);

  return {
    feature,
    draft: {
      name: feature.properties.name,
      labelText: rawLabel,
      wordType,
      selectedMapIds: initialMapIds,
      labelStyleSelection: feature.properties.customLabelStyleId
        ? `custom:${feature.properties.customLabelStyleId}`
        : wordType,
      customLabelStyleId: feature.properties.customLabelStyleId,
      customLabelStyle: feature.properties.customLabelStyle,
      colorHex,
      textColorHex: rgbToHex(feature.properties.textColorRgb) ?? colorHex,
      textSizePx: isText
        ? normalizeTextSizePx(feature.properties.textSizePx) ??
          getDefaultTextSizePx(wordType)
        : undefined,
      strokeColorHex: rgbToHex(feature.properties.strokeColor),
      fillOpacity: normalizeOpacity(feature.properties.fillOpacity),
      // A point's outline is drawn opaque unless told otherwise; show that
      // value rather than an empty field.
      strokeOpacity:
        normalizeOpacity(feature.properties.strokeOpacity) ??
        (elementType === "point" ? DEFAULT_POINT_STROKE_OPACITY : undefined),
      strokeWidth: normalizeStrokeWidth(feature.properties.strokeWidth),
    },
  };
}

export function coerceEditedFeature(
  originalFeature: Feature,
  payload: FeatureEditSubmitPayload,
): Feature {
  const chosenMapId =
    payload.selectedMapIds && payload.selectedMapIds.length > 0
      ? payload.selectedMapIds[0]
      : null;

  if (!isTextFeature(originalFeature)) {
    return {
      ...originalFeature,
      mapId: chosenMapId,
      name: payload.name,
      properties: {
        ...originalFeature.properties,
        mapId: chosenMapId,
        name: payload.name,
        colorRgb: hexToRgb(payload.colorHex),
        strokeColor: hexToRgb(payload.strokeColorHex),
        fillOpacity: normalizeOpacity(payload.fillOpacity),
        strokeOpacity: normalizeOpacity(payload.strokeOpacity),
        strokeWidth: normalizeStrokeWidth(payload.strokeWidth),
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
    const custom = applyCustomLabelStyleToFeature(
      originalFeature,
      payload.customLabelStyle,
      payload.wordType,
      payload.name,
      payload.labelText ?? payload.name,
    );
    return {
      ...custom,
      mapId: chosenMapId,
      properties: {
        ...custom.properties,
        mapId: chosenMapId,
      },
    };
  }
  const isLabel = styledFeature.properties.mapElementType === "label";
  // A label has no symbol, so its one colour is the text colour. A point keeps
  // a text colour only when it differs from the symbol's.
  const textColorHex =
    !isLabel && payload.textColorHex && payload.textColorHex !== payload.colorHex
      ? payload.textColorHex
      : undefined;
  // Only a size the user moved away from the word type's is stored, so the
  // element keeps following its type otherwise.
  const textSizePx = normalizeTextSizePx(payload.textSizePx);
  const customTextSizePx =
    textSizePx !== undefined && textSizePx !== getDefaultTextSizePx(payload.wordType)
      ? textSizePx
      : undefined;

  return {
    ...styledFeature,
    mapId: chosenMapId,
    properties: {
      ...styledFeature.properties,
      mapId: chosenMapId,
      customLabelStyleId: null,
      customLabelStyle: null,
      custom_label_style_id: null,
      colorRgb: hexToRgb(payload.colorHex),
      textColorRgb: hexToRgb(textColorHex),
      textSizePx: customTextSizePx,
      strokeColor: isLabel ? undefined : hexToRgb(payload.strokeColorHex),
      fillOpacity: isLabel ? undefined : normalizeOpacity(payload.fillOpacity),
      strokeOpacity: isLabel ? undefined : normalizeOpacity(payload.strokeOpacity),
      strokeWidth: isLabel ? undefined : normalizeStrokeWidth(payload.strokeWidth),
    },
  };
}

/**
 * When multiple maps are selected, clones the feature for each additional map
 * with a new unique ID and the respective mapId.
 */
export function createFeaturesForSelectedMaps(
  baseEditedFeature: Feature,
  selectedMapIds?: string[],
): Feature[] {
  if (!selectedMapIds || selectedMapIds.length <= 1) {
    return [baseEditedFeature];
  }

  const results: Feature[] = [
    {
      ...baseEditedFeature,
      mapId: selectedMapIds[0],
      properties: {
        ...baseEditedFeature.properties,
        mapId: selectedMapIds[0],
      },
    },
  ];

  for (let i = 1; i < selectedMapIds.length; i++) {
    const targetMapId = selectedMapIds[i];
    let cloned: Feature;
    if (typeof structuredClone === "function") {
      try {
        cloned = structuredClone(baseEditedFeature);
      } catch {
        cloned = JSON.parse(JSON.stringify(baseEditedFeature)) as Feature;
      }
    } else {
      cloned = JSON.parse(JSON.stringify(baseEditedFeature)) as Feature;
    }
    cloned.id = crypto.randomUUID();
    cloned.mapId = targetMapId;
    if (cloned.properties) {
      cloned.properties.mapId = targetMapId;
    }
    results.push(cloned);
  }

  return results;
}

export function getWordTypePreviewStyle(
  wordType: string,
  colorHex?: string,
  sizePx?: number,
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
    fontSize: `${sizePx ?? taxonomy.sizePx}px`,
  };
}
