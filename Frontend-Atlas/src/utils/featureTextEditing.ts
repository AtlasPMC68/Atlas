import type { Feature } from "../typescript/feature";
import { normalizeTextSizePx, type CustomLabelStyle } from "./labelPresentation";
import { getFeatureMapIds, getMapElementType } from "./featureHelpers";
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
export const MAX_POINT_STROKE_WIDTH_PX = 12;
export const MAX_PREVIEW_POINT_STROKE_WIDTH_PX = 6;
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

export function normalizePointStrokeWidth(value: unknown): number | undefined {
  if (value === null || value === undefined || value === "") return undefined;
  const width = Number(value);
  if (!Number.isFinite(width)) return undefined;
  return Math.max(0, Math.min(MAX_POINT_STROKE_WIDTH_PX, width));
}

export function getDefaultTextSizePx(wordType: string | undefined): number {
  return WORD_TYPE_TAXONOMY[normalizeWordType(wordType)].sizePx;
}

function resolveEditCustomStyle(
  originalFeature: Feature,
  payload: FeatureEditSubmitPayload,
): CustomLabelStyle | null {
  if (payload.customLabelStyle) return payload.customLabelStyle;
  if (!payload.customLabelStyleId) return null;
  const embedded = originalFeature.properties.customLabelStyle as CustomLabelStyle | null | undefined;
  return embedded ?? null;
}

export function applyCustomLabelStyleToFeature(
  feature: Feature,
  style: CustomLabelStyle,
  wordType: WordType = "city",
  name?: string,
  labelText?: string,
): Feature {
  const resolvedName =
    name && name.trim().length > 0
      ? name
      : (feature.properties.name && feature.properties.name.trim().length > 0
        ? feature.properties.name
        : (labelText ?? feature.properties.labelText ?? ""));
  const resolvedLabelText =
    labelText ?? feature.properties.labelText ?? resolvedName;
  const formattedText =
    style.textTransform === "uppercase"
      ? (resolvedLabelText || "").toUpperCase()
      : (resolvedLabelText || "");
  const styledFeature = applyWordStyleToFeature(
    feature,
    wordType,
    resolvedName,
    formattedText,
  );
  const isBold = Boolean(style.bold || style.fontWeight === "bold");
  const targetElementType =
    style.mapElementType === "point" || style.hasPoint === true
      ? "point"
      : style.mapElementType === "label" || style.hasPoint === false
        ? "label"
        : (styledFeature.properties.mapElementType ?? "point");

  const pointColor = style.pointColor || style.color || "#000000";
  const pointStroke = style.pointStrokeColor || "#000000";

  return {
    ...styledFeature,
    name: resolvedName,
    properties: {
      ...styledFeature.properties,
      name: resolvedName,
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
      color: targetElementType === "point" ? pointColor : style.color,
      colorRgb: targetElementType === "point" ? hexToRgb(pointColor) : hexToRgb(style.color),
      textColorRgb: hexToRgb(style.color),
      pointColor: targetElementType === "point" ? pointColor : undefined,
      pointStrokeColor: targetElementType === "point" ? pointStroke : undefined,
      strokeColor: targetElementType === "point" ? hexToRgb(pointStroke) : undefined,
      fillOpacity: targetElementType === "point" ? (style.pointFillOpacity ?? 1) : undefined,
      strokeOpacity: targetElementType === "point" ? (style.pointStrokeOpacity ?? 1) : undefined,
      strokeWidth: targetElementType === "point" ? (style.pointStrokeWidth ?? 1) : undefined,
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

  const initialMapIds = getFeatureMapIds(feature);
  const customStyle = feature.properties.customLabelStyle;
  const customStyleId =
    feature.properties.customLabelStyleId ||
    (customStyle && typeof customStyle.id === "string" ? customStyle.id : undefined);
  const hasCustomStyle = Boolean(customStyleId || customStyle);

  const rawColorHex =
    (typeof feature.properties.pointColor === "string" ? feature.properties.pointColor : undefined) ||
    rgbToHex(feature.properties.colorRgb) ||
    (typeof feature.properties.color === "string" ? feature.properties.color : undefined);
  const rawTextColorHex = rgbToHex(feature.properties.textColorRgb);
  const rawStrokeColorHex =
    (typeof feature.properties.pointStrokeColor === "string" ? feature.properties.pointStrokeColor : undefined) ||
    rgbToHex(feature.properties.strokeColor);

  let colorHex: string | undefined;
  let textColorHex: string | undefined;
  let strokeColorHex: string | undefined;

  if (hasCustomStyle && customStyle) {
    colorHex = customStyle.pointColor || customStyle.color || rawColorHex || "#000000";
    textColorHex = customStyle.color || rawTextColorHex || "#000000";
    strokeColorHex = customStyle.pointStrokeColor || rawStrokeColorHex || "#000000";
  } else {
    colorHex =
      rawColorHex ??
      (elementType === "label" || elementType === "point" ? "#000000" : undefined);
    textColorHex =
      rawTextColorHex ??
      (elementType === "label" || elementType === "point" ? (colorHex || "#000000") : "#000000");
    strokeColorHex =
      rawStrokeColorHex ??
      (elementType === "point" ? "#000000" : undefined);
  }

  return {
    feature,
    draft: {
      name: feature.properties?.name || feature.name || "",
      labelText: rawLabel,
      wordType,
      selectedMapIds: initialMapIds,
      labelStyleSelection: customStyleId ? `custom:${customStyleId}` : wordType,
      customLabelStyleId: customStyleId,
      customLabelStyle: customStyle,
      colorHex,
      textColorHex,
      textSizePx: isText
        ? normalizeTextSizePx(feature.properties.textSizePx) ??
          getDefaultTextSizePx(wordType)
        : undefined,
      strokeColorHex,
      fillOpacity:
        normalizeOpacity(feature.properties.fillOpacity) ??
        (elementType === "point" ? 1 : undefined),
      // A point's outline is drawn opaque unless told otherwise; show that
      // value rather than an empty field.
      strokeOpacity:
        normalizeOpacity(feature.properties.strokeOpacity) ??
        (elementType === "point" ? DEFAULT_POINT_STROKE_OPACITY : undefined),
      strokeWidth:
        normalizeStrokeWidth(feature.properties.strokeWidth) ??
        (elementType === "point" ? 1 : undefined),
    },
  };
}

export function coerceEditedFeature(
  originalFeature: Feature,
  payload: FeatureEditSubmitPayload,
): Feature {
  const chosenMapIds =
    payload.selectedMapIds && payload.selectedMapIds.length > 0
      ? [...payload.selectedMapIds]
      : [];
  const chosenMapId = chosenMapIds.length > 0 ? chosenMapIds[0] : null;

  if (!isTextFeature(originalFeature)) {
    const cleanedProps = { ...originalFeature.properties };
    delete cleanedProps.labelText;
    delete cleanedProps.wordType;
    delete cleanedProps.rawType;
    if (cleanedProps.mapElementType === "point" || cleanedProps.mapElementType === "label") {
      cleanedProps.mapElementType = "shape";
    }

    return {
      ...originalFeature,
      mapId: chosenMapId,
      mapIds: chosenMapIds,
      map_id: chosenMapId,
      name: payload.name,
      properties: {
        ...cleanedProps,
        mapId: chosenMapId,
        mapIds: chosenMapIds,
        map_id: chosenMapId,
        mapTitle: cleanedProps.mapTitle ?? null,
        name: payload.name,
        colorRgb: hexToRgb(payload.colorHex),
        strokeColor: hexToRgb(payload.strokeColorHex),
        fillOpacity: normalizeOpacity(payload.fillOpacity),
        strokeOpacity: normalizeOpacity(payload.strokeOpacity),
        strokeWidth: normalizeStrokeWidth(payload.strokeWidth),
        mapElementType: cleanedProps.mapElementType || "shape",
      },
    };
  }

  const styledFeature = applyWordStyleToFeature(
    originalFeature,
    payload.wordType,
    payload.name,
    payload.labelText ?? payload.name,
  );
  const resolvedCustomStyle = resolveEditCustomStyle(originalFeature, payload);
  const customStyleId = payload.customLabelStyleId || resolvedCustomStyle?.id;
  if (customStyleId) {
    if (resolvedCustomStyle) {
      const custom = applyCustomLabelStyleToFeature(
        originalFeature,
        { ...resolvedCustomStyle, id: customStyleId },
        payload.wordType,
        payload.name,
        payload.labelText ?? payload.name,
      );
      return {
        ...custom,
        mapId: chosenMapId,
        mapIds: chosenMapIds,
        map_id: chosenMapId,
        properties: {
          ...custom.properties,
          mapId: chosenMapId,
          mapIds: chosenMapIds,
          map_id: chosenMapId,
          mapTitle: custom.properties.mapTitle ?? null,
        },
      };
    }
    return {
      ...originalFeature,
      name: payload.name,
      mapId: chosenMapId,
      mapIds: chosenMapIds,
      map_id: chosenMapId,
      properties: {
        ...originalFeature.properties,
        name: payload.name,
        labelText: payload.labelText ?? originalFeature.properties.labelText ?? payload.name,
        mapId: chosenMapId,
        mapIds: chosenMapIds,
        map_id: chosenMapId,
        customLabelStyleId: customStyleId,
      },
    };
  }
  const isLabel = styledFeature.properties.mapElementType === "label";
  const isPoint = styledFeature.properties.mapElementType === "point";
  const pointFillColor = payload.colorHex || "#000000";
  const pointStrokeColor = payload.strokeColorHex || "#000000";
  const labelColorHex = payload.colorHex ?? payload.textColorHex;
  // A label has no symbol, so its one colour is its text colour (stored in colorRgb, without redundant textColorRgb).
  // A point keeps a separate text colour only when it differs from the symbol's.
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
    mapIds: chosenMapIds,
    map_id: chosenMapId,
    properties: {
      ...styledFeature.properties,
      mapId: chosenMapId,
      mapIds: chosenMapIds,
      map_id: chosenMapId,
      mapTitle: styledFeature.properties.mapTitle ?? null,
      customLabelStyleId: null,
      customLabelStyle: null,
      custom_label_style_id: null,
      customLabelStyleFallbackWordType: undefined,
      color: isLabel ? labelColorHex : pointFillColor,
      colorRgb: hexToRgb(isLabel ? labelColorHex : pointFillColor),
      textColorRgb: hexToRgb(textColorHex),
      textSizePx: customTextSizePx,
      pointColor: isPoint ? pointFillColor : undefined,
      pointStrokeColor: isPoint ? pointStrokeColor : undefined,
      strokeColor: isLabel
        ? undefined
        : hexToRgb(pointStrokeColor),
      fillOpacity: isLabel
        ? undefined
        : (normalizeOpacity(payload.fillOpacity) ?? (isPoint ? 1 : undefined)),
      strokeOpacity: isLabel
        ? undefined
        : (normalizeOpacity(payload.strokeOpacity) ?? (isPoint ? 1 : undefined)),
      strokeWidth: isLabel
        ? undefined
        : (normalizeStrokeWidth(payload.strokeWidth) ?? (isPoint ? 1 : undefined)),
    },
  };
}

/**
 * Associates the edited feature with the chosen maps on the same feature entity
 * without creating duplicate IDs.
 */
export function createFeaturesForSelectedMaps(
  baseEditedFeature: Feature,
  selectedMapIds?: string[],
): Feature[] {
  if (!selectedMapIds || selectedMapIds.length === 0) {
    return [baseEditedFeature];
  }
  if (
    selectedMapIds.length === 1 &&
    selectedMapIds[0] === baseEditedFeature.mapId &&
    (!baseEditedFeature.mapIds ||
      (baseEditedFeature.mapIds.length === 1 && baseEditedFeature.mapIds[0] === selectedMapIds[0]))
  ) {
    return [baseEditedFeature];
  }

  const chosenMapIds = [...selectedMapIds];
  const chosenMapId = chosenMapIds.length > 0 ? chosenMapIds[0] : null;

  return [
    {
      ...baseEditedFeature,
      mapId: chosenMapId,
      mapIds: chosenMapIds,
      map_id: chosenMapId,
      properties: {
        ...baseEditedFeature.properties,
        mapId: chosenMapId,
        mapIds: chosenMapIds,
        map_id: chosenMapId,
      },
    },
  ];
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
