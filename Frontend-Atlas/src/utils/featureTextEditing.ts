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
  customLabelStyleId?: string | null;
  customLabelStyle?: CustomLabelStyle | null;
  selectedMapIds?: string[];
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

  const rawMapId =
    feature.mapId ??
    (feature as any).map_id ??
    (feature.properties as any)?.mapId ??
    (feature.properties as any)?.map_id ??
    null;
  const initialMapIds = rawMapId ? [String(rawMapId)] : [];

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
      strokeColor: isLabel ? undefined : hexToRgb(payload.strokeColorHex),
      fillOpacity: isLabel ? undefined : payload.fillOpacity,
      strokeOpacity: isLabel ? undefined : payload.strokeOpacity,
      strokeWidth: isLabel ? undefined : payload.strokeWidth,
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
