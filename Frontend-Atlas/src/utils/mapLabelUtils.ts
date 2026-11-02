import type { Feature } from "../typescript/feature";
import { getMapElementType, colorRgbToCss } from "./featureHelpers";
import { hexToRgb, rgbToHex } from "./utils";

export interface LabelFontStyle {
  fontStyle: "normal" | "italic";
  textTransform: "uppercase" | "none";
}

export interface WordTypeStyle {
  label: string;
  mapElementType: "point" | "label";
  sizePx: number;
  fontStyle: "normal" | "uppercase" | "italic" | string;
  transform: (text: string) => string;
}

export interface WordTypeTaxonomyEntry {
  id: string;
  label: string;
  mapElementType: "point" | "label";
  sizePx: number;
  fontStyle: "normal" | "italic";
  textTransform: "uppercase" | "none";
  priority: number;
  minZoom: number;
  category: string;
}

export const toUpperCaseTransform = (text: string): string => (text ? text.toUpperCase() : text);

export const LOWERCASE_PARTICLES = new Set(["de", "du", "des", "d'", "l'", "la", "le", "et"]);

/**
 * Format a single word or name segment with initial capital and lowered tail.
 */
export function capitalizeSegment(segment: string): string {
  if (!segment) return segment;
  return segment.charAt(0).toUpperCase() + segment.slice(1).toLowerCase();
}

/**
 * Capitalizes ONLY the very first letter of the text and lowers the rest.
 */
export function capitalizeFirstOnly(text: string): string {
  return capitalizeSegment(text);
}

/**
 * Capitalize each word/term in a place name, preserving hyphens and French particles.
 */
export function capitalizeWords(text: string): string {
  if (!text) return text;
  return text
    .split(/([\s-]+)/)
    .map((part, index) => {
      if (!part || /^[\s-]+$/.test(part)) return part;

      const apostropheMatch = part.match(/^([dlDL]['’])(.*)$/);
      if (apostropheMatch) {
        const pfx = apostropheMatch[1].toLowerCase();
        const rest = apostropheMatch[2];
        return `${pfx}${capitalizeSegment(rest)}`;
      }

      const lower = part.toLowerCase();
      if (index > 0 && LOWERCASE_PARTICLES.has(lower)) {
        return lower;
      }

      return capitalizeSegment(part);
    })
    .join("");
}

// Canonical taxonomy shared across backend and frontend visual systems
export const WORD_TYPE_TAXONOMY: Record<string, WordTypeTaxonomyEntry> = {
  continent: { id: "continent", label: "Continent", mapElementType: "label", sizePx: 18, fontStyle: "normal", textTransform: "uppercase", priority: 90, minZoom: 1.0, category: "continent" },
  ocean:     { id: "ocean",     label: "Océan",     mapElementType: "label", sizePx: 18, fontStyle: "italic", textTransform: "uppercase", priority: 80, minZoom: 1.0, category: "ocean" },
  country:   { id: "country",   label: "Pays",      mapElementType: "label", sizePx: 16, fontStyle: "normal", textTransform: "uppercase", priority: 70, minZoom: 1.5, category: "country" },
  sea:       { id: "sea",       label: "Mer",       mapElementType: "label", sizePx: 16, fontStyle: "italic", textTransform: "none",      priority: 60, minZoom: 2.0, category: "sea" },
  state:     { id: "state",     label: "État",      mapElementType: "label", sizePx: 14, fontStyle: "normal", textTransform: "uppercase", priority: 50, minZoom: 2.5, category: "state" },
  province:  { id: "province",  label: "Province",  mapElementType: "label", sizePx: 14, fontStyle: "normal", textTransform: "uppercase", priority: 50, minZoom: 2.5, category: "state" },
  territory: { id: "territory", label: "Territoire",mapElementType: "label", sizePx: 14, fontStyle: "normal", textTransform: "uppercase", priority: 50, minZoom: 2.5, category: "state" },
  fleuve:    { id: "fleuve",    label: "Fleuve",    mapElementType: "label", sizePx: 14, fontStyle: "italic", textTransform: "none",      priority: 40, minZoom: 2.25, category: "fleuve" },
  city:      { id: "city",      label: "Ville",     mapElementType: "point", sizePx: 12, fontStyle: "normal", textTransform: "none",      priority: 30, minZoom: 4.0, category: "city" },
  lake:      { id: "lake",      label: "Lac",       mapElementType: "label", sizePx: 12, fontStyle: "italic", textTransform: "none",      priority: 20, minZoom: 2.75, category: "lake" },
  river:     { id: "river",     label: "Rivière",   mapElementType: "label", sizePx: 10, fontStyle: "italic", textTransform: "none",      priority: 10, minZoom: 4.5, category: "river" },
};

export const WORD_TYPE_STYLES: Record<string, WordTypeStyle> = Object.fromEntries(
  Object.entries(WORD_TYPE_TAXONOMY).map(([key, entry]) => [
    key,
    {
      label: entry.label,
      mapElementType: entry.mapElementType,
      sizePx: entry.sizePx,
      fontStyle:
        entry.fontStyle === "italic" && entry.textTransform === "uppercase"
          ? "italic uppercase"
          : entry.fontStyle === "italic"
          ? "italic"
          : entry.textTransform === "uppercase"
          ? "uppercase"
          : "normal",
      transform: entry.textTransform === "uppercase" ? toUpperCaseTransform : capitalizeWords,
    },
  ]),
);

export function getWordTypeStyle(type?: string): WordTypeStyle {
  const key = (type || "").toLowerCase();
  return WORD_TYPE_STYLES[key] || WORD_TYPE_STYLES.city;
}

export function formatWordText(text: string, wordType?: string): string {
  if (!text) return text;
  const style = getWordTypeStyle(wordType);
  return style.transform ? style.transform(text) : text;
}

export function isTextFeature(feature?: Feature | Record<string, any> | null): boolean {
  if (!feature) return false;
  const props = (feature.properties || {}) as Record<string, any>;
  const elemType = getMapElementType(feature as Feature);
  return (
    elemType === "label" ||
    elemType === "point" ||
    Boolean(props.isOcrText) ||
    props.labelText !== undefined ||
    props.rawType !== undefined ||
    feature.geometry?.type === "Point"
  );
}

export function getWordTypeForFeature(feature?: Feature | Record<string, any> | null): string {
  if (!feature) return "city";
  const props = (feature.properties || {}) as Record<string, any>;
  const rawType = String(props.rawType || props.type || "").toLowerCase();
  if (rawType && WORD_TYPE_TAXONOMY[rawType]) {
    return rawType;
  }
  const elemType = getMapElementType(feature as Feature);
  return elemType === "label" ? "province" : "city";
}

export function applyWordStyleToFeature(
  feature: Feature,
  wordType: string,
  newText?: string,
): Feature {
  const style = getWordTypeStyle(wordType);
  const currentText =
    newText !== undefined
      ? newText
      : feature.properties?.labelText ?? feature.properties?.name ?? feature.name ?? "";
  const transformedText = formatWordText(currentText, wordType);

  return {
    ...feature,
    name: transformedText,
    properties: {
      ...feature.properties,
      name: transformedText,
      labelText: transformedText,
      mapElementType: style.mapElementType,
      sizePx: style.sizePx,
      fontStyle: style.fontStyle,
      rawType: wordType,
      type: wordType,
    },
  };
}

export interface LabelCategoryInfo {
  priority: number;
  minZoom: number;
  category: string;
}

export function parseLabelFontStyle(rawStyle?: unknown): LabelFontStyle {
  const styleStr = typeof rawStyle === "string" ? rawStyle.toLowerCase() : "";
  const isUppercase = styleStr.includes("uppercase");
  const isItalic = styleStr.includes("italic") || styleStr.includes("oblique");

  return {
    fontStyle: isItalic ? "italic" : "normal",
    textTransform: isUppercase ? "uppercase" : "none",
  };
}

export function splitBalancedLine(text: string, maxLen = 13): string {
  if (text.length <= maxLen) return text;

  // Find candidate break points (spaces and hyphens)
  const candidates: { index: number; after: boolean }[] = [];
  for (let i = 0; i < text.length; i++) {
    if (text[i] === " ") {
      candidates.push({ index: i, after: false });
    } else if (text[i] === "-") {
      candidates.push({ index: i + 1, after: true }); // break after hyphen, keeping hyphen
    }
  }

  if (candidates.length === 0) {
    if (text.length >= 16) {
      const mid = Math.floor(text.length / 2);
      return `${text.slice(0, mid)}-<br>${text.slice(mid)}`;
    }
    return text;
  }

  const mid = text.length / 2;
  let best = candidates[0];
  let bestDiff = Math.abs((best.after ? best.index : best.index + 0.5) - mid);

  for (let k = 1; k < candidates.length; k++) {
    const cand = candidates[k];
    const pos = cand.after ? cand.index : cand.index + 0.5;
    const diff = Math.abs(pos - mid);
    if (diff < bestDiff) {
      bestDiff = diff;
      best = cand;
    }
  }

  if (best.after) {
    return `${text.slice(0, best.index).trim()}<br>${text.slice(best.index).trim()}`;
  }
  return `${text.slice(0, best.index).trim()}<br>${text.slice(best.index + 1).trim()}`;
}

export function formatLabelHtml(rawText: unknown, isUppercase: boolean = false): string {
  if (rawText === null || rawText === undefined) return "";
  const str = String(rawText).trim();
  if (!str) return "";

  const lines = str.split("\n");
  const formatted = lines.map((line) => {
    const trimmed = line.trim();
    if (!trimmed) return "";
    const cased = isUppercase
      ? trimmed.toUpperCase()
      : capitalizeWords(trimmed);
    return splitBalancedLine(cased);
  });

  return formatted.join("<br>");
}

// Category visual hierarchy rules: [priority, minZoom, categoryName]
export const LABEL_CATEGORY_RULES: Record<string, [number, number, string]> = {
  ...Object.fromEntries(
    Object.entries(WORD_TYPE_TAXONOMY).map(([key, entry]) => [
      key,
      [entry.priority, entry.minZoom, entry.category] as [number, number, string],
    ]),
  ),
  point: [30, 4.0, "city"],
};

export function resolveCategoryKey(
  rawType: string,
  sizePx: number,
  isUpper: boolean,
  isItalic: boolean,
): string {
  if (rawType && LABEL_CATEGORY_RULES[rawType]) return rawType;
  if (sizePx >= 18) return isUpper ? "continent" : "ocean";
  if (sizePx >= 16) return isUpper ? "country" : "sea";
  if (sizePx >= 14) return isUpper ? "state" : "fleuve";
  if (sizePx >= 12) return isItalic ? "lake" : "city";
  return "river";
}

export function getLabelCategoryInfo(
  feature: Feature | Record<string, any>,
): LabelCategoryInfo {
  const props = feature.properties || {};
  const rawType = String(
    props.rawType || (props as any).entityType || props.mapElementType || "",
  ).toLowerCase();
  const fontStyle = String((props as any).fontStyle || "").toLowerCase();
  const key = resolveCategoryKey(
    rawType,
    props.sizePx ?? 12,
    fontStyle.includes("uppercase"),
    fontStyle.includes("italic"),
  );

  const [priority, minZoom, category] = LABEL_CATEGORY_RULES[key] || [
    30,
    2.5,
    "custom",
  ];
  return { priority, minZoom, category };
}

export function getElementCategoryInfo(el: HTMLElement): {
  priority: number;
  minZoom: number;
} {
  const p = parseFloat(el.dataset.priority || "");
  const mz = parseFloat(el.dataset.minZoom || "");
  if (!isNaN(p) && !isNaN(mz)) return { priority: p, minZoom: mz };

  const size =
    parseFloat(el.style.getPropertyValue("--label-size") || "12") || 12;
  const isUpper = (
    el.style.getPropertyValue("--label-transform") || ""
  ).includes("uppercase");
  const isItalic = (
    el.style.getPropertyValue("--label-style") || ""
  ).includes("italic");
  const key = resolveCategoryKey(
    el.dataset.category || "",
    size,
    isUpper,
    isItalic,
  );
  const [priority, minZoom] = LABEL_CATEGORY_RULES[key] || [30, 2.5];
  return { priority, minZoom };
}

/**
 * Unified presentation model for map text and labels.
 * Encapsulates formatted text, HTML, size, font styling, visual hierarchy, and colors.
 */
export interface LabelPresentationModel {
  text: string;
  formattedText: string;
  html: string;
  wordType: string;
  mapElementType: "point" | "label";
  sizePx: number;
  fontStyle: "normal" | "italic";
  textTransform: "uppercase" | "none";
  isUppercase: boolean;
  isItalic: boolean;
  priority: number;
  minZoom: number;
  category: string;
  colorCss: string;
  styleAttribute: string;
}

export function getLabelPresentation(
  feature: Feature | Record<string, any>,
  customText?: string,
): LabelPresentationModel {
  const props = (feature.properties || {}) as Record<string, any>;
  const wordType = getWordTypeForFeature(feature);
  const taxonomy = WORD_TYPE_TAXONOMY[wordType] || WORD_TYPE_TAXONOMY.city;

  const rawText =
    customText !== undefined
      ? customText
      : props.labelText ?? props.name ?? (feature as any).name ?? "";

  const explicitFontStyle = props.fontStyle ? parseLabelFontStyle(props.fontStyle) : null;
  const isUppercase = explicitFontStyle
    ? explicitFontStyle.textTransform === "uppercase"
    : taxonomy.textTransform === "uppercase";
  const isItalic = explicitFontStyle
    ? explicitFontStyle.fontStyle === "italic"
    : taxonomy.fontStyle === "italic";

  const formattedText = formatWordText(String(rawText), wordType);
  const html = formatLabelHtml(rawText, isUppercase);

  const sizePx = props.sizePx ?? taxonomy.sizePx;
  const mapElementType = (props.mapElementType || taxonomy.mapElementType) as "point" | "label";

  const colorCss =
    colorRgbToCss(props.colorRgb) || props.color || "#000000";

  const inlineStyles: string[] = [];
  if (isItalic) inlineStyles.push("font-style: italic");
  if (isUppercase) inlineStyles.push("text-transform: uppercase");
  const styleAttribute = inlineStyles.length ? ` style="${inlineStyles.join("; ")}"` : "";

  return {
    text: String(rawText),
    formattedText,
    html,
    wordType,
    mapElementType,
    sizePx,
    fontStyle: isItalic ? "italic" : "normal",
    textTransform: isUppercase ? "uppercase" : "none",
    isUppercase,
    isItalic,
    priority: taxonomy.priority,
    minZoom: taxonomy.minZoom,
    category: taxonomy.category,
    colorCss,
    styleAttribute,
  };
}

/**
 * Feature editing state and coercion helpers
 * to centralize form state and updatedFeature construction.
 */
export interface FeatureEditState {
  feature: Feature;
  name: string;
  labelText?: string;
  wordType: string;
  isText: boolean;
  colorHex?: string;
  strokeColorHex?: string;
  fillOpacity?: number;
  strokeOpacity?: number;
  strokeWidth?: number;
}

export function prepareFeatureForEdit(feature: Feature): FeatureEditState {
  const isText = isTextFeature(feature);
  const wordType = getWordTypeForFeature(feature);
  const elemType = getMapElementType(feature);

  const rawLabel =
    feature.properties.labelText ?? (isText ? feature.properties.name : undefined);
  const labelText = isText && rawLabel ? formatWordText(rawLabel, wordType) : rawLabel;
  const name = isText && feature.properties.name
    ? formatWordText(feature.properties.name, wordType)
    : feature.properties.name;

  return {
    feature,
    name,
    labelText,
    wordType,
    isText,
    colorHex:
      rgbToHex(feature.properties.colorRgb) ??
      (elemType === "label" || elemType === "point" ? "#000000" : undefined),
    strokeColorHex: rgbToHex(feature.properties.strokeColor),
    fillOpacity: feature.properties.fillOpacity,
    strokeOpacity: feature.properties.strokeOpacity,
    strokeWidth: feature.properties.strokeWidth,
  };
}

export interface FeatureEditSubmitPayload {
  name: string;
  labelText?: string;
  wordType: string;
  colorHex?: string;
  strokeColorHex?: string;
  fillOpacity?: number;
  strokeOpacity?: number;
  strokeWidth?: number;
}

export function coerceEditedFeature(
  originalFeature: Feature,
  payload: FeatureEditSubmitPayload,
): Feature {
  const isText = isTextFeature(originalFeature);

  if (isText) {
    const styled = applyWordStyleToFeature(
      originalFeature,
      payload.wordType,
      payload.name,
    );
    const isLabel = styled.properties.mapElementType === "label";
    const customLabelText =
      payload.labelText !== undefined
        ? formatWordText(payload.labelText, payload.wordType)
        : styled.properties.labelText;

    return {
      ...styled,
      properties: {
        ...styled.properties,
        labelText: customLabelText,
        colorRgb: hexToRgb(payload.colorHex),
        strokeColor: isLabel ? undefined : hexToRgb(payload.strokeColorHex),
        fillOpacity: isLabel ? undefined : payload.fillOpacity,
        strokeOpacity: isLabel ? undefined : payload.strokeOpacity,
        strokeWidth: isLabel ? undefined : payload.strokeWidth,
      },
    };
  }

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

export function getWordTypePreviewStyle(
  wordType: string,
  colorHex?: string,
): {
  fontStyle?: "normal" | "italic";
  textTransform?: "uppercase";
  color?: string;
} {
  const taxonomy = WORD_TYPE_TAXONOMY[wordType] || WORD_TYPE_TAXONOMY.city;
  return {
    fontStyle: taxonomy.fontStyle !== "normal" ? taxonomy.fontStyle : undefined,
    textTransform: taxonomy.textTransform === "uppercase" ? "uppercase" : undefined,
    color: colorHex || undefined,
  };
}
