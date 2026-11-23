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
  startYear?: number | null;
  endYear?: number | null;
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

  const pointColor = style.pointColor || style.color;
  const pointStroke = style.pointStrokeColor || pointColor;

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
      colorRgb: targetElementType === "point" ? hexToRgb(pointColor) : hexToRgb(style.color),
      strokeColor: targetElementType === "point" ? hexToRgb(pointStroke) : undefined,
      fillOpacity: targetElementType === "point" ? (style.pointFillOpacity ?? 0.5) : undefined,
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

  const hasCustomYears =
    feature.properties?.startYear != null || feature.properties?.endYear != null;
  const initialMapIds = hasCustomYears ? [] : getFeatureMapIds(feature);
  const colorHex =
    rgbToHex(feature.properties.colorRgb) ??
    (elementType === "label" || elementType === "point" ? "#000000" : undefined);

  return {
    feature,
    draft: {
      name: feature.properties?.name || feature.name || "",
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
      startYear: feature.properties.startYear ?? null,
      endYear: feature.properties.endYear ?? null,
    },
  };
}

export function coerceEditedFeature(
  originalFeature: Feature,
  payload: FeatureEditSubmitPayload,
): Feature {
  const hasCustomDate = payload.startYear != null || payload.endYear != null;
  const chosenMapIds = hasCustomDate
    ? []
    : (payload.selectedMapIds && payload.selectedMapIds.length > 0
        ? [...payload.selectedMapIds]
        : []);
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
        mapTitle: hasCustomDate ? null : (cleanedProps.mapTitle ?? null),
        name: payload.name,
        colorRgb: hexToRgb(payload.colorHex),
        strokeColor: hexToRgb(payload.strokeColorHex),
        fillOpacity: normalizeOpacity(payload.fillOpacity),
        strokeOpacity: normalizeOpacity(payload.strokeOpacity),
        strokeWidth: normalizeStrokeWidth(payload.strokeWidth),
        startYear: payload.startYear ?? null,
        endYear: payload.endYear ?? null,
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
      mapIds: chosenMapIds,
      map_id: chosenMapId,
      properties: {
        ...custom.properties,
        mapId: chosenMapId,
        mapIds: chosenMapIds,
        map_id: chosenMapId,
        mapTitle: hasCustomDate ? null : (custom.properties.mapTitle ?? null),
        startYear: payload.startYear ?? null,
        endYear: payload.endYear ?? null,
      },
    };
  }
  const isLabel = styledFeature.properties.mapElementType === "label";
  // For a label (no point), the chosen text color is stored as both colorRgb and textColorRgb.
  // For a point, colorHex is the symbol's fill, and textColorHex is the text label's color.
  const effectiveColorHex = isLabel ? (payload.textColorHex ?? payload.colorHex) : payload.colorHex;
  const textColorHex = isLabel
    ? (payload.textColorHex ?? payload.colorHex)
    : payload.textColorHex;
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
      mapTitle: hasCustomDate ? null : (styledFeature.properties.mapTitle ?? null),
      customLabelStyleId: null,
      customLabelStyle: null,
      custom_label_style_id: null,
      colorRgb: hexToRgb(effectiveColorHex),
      textColorRgb: hexToRgb(textColorHex),
      textSizePx: customTextSizePx,
      strokeColor: isLabel ? undefined : hexToRgb(payload.strokeColorHex),
      fillOpacity: isLabel ? undefined : normalizeOpacity(payload.fillOpacity),
      strokeOpacity: isLabel ? undefined : normalizeOpacity(payload.strokeOpacity),
      strokeWidth: isLabel ? undefined : normalizeStrokeWidth(payload.strokeWidth),
      startYear: payload.startYear ?? null,
      endYear: payload.endYear ?? null,
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
  const hasCustomDate =
    baseEditedFeature.properties?.startYear != null ||
    baseEditedFeature.properties?.endYear != null;

  if (hasCustomDate) {
    return [
      {
        ...baseEditedFeature,
        mapId: null,
        mapIds: [],
        map_id: null,
        properties: {
          ...baseEditedFeature.properties,
          mapId: null,
          mapIds: [],
          map_id: null,
          mapTitle: null,
        },
      },
    ];
  }

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
