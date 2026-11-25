import type { CSSProperties } from "vue";
import type { Feature } from "../typescript/feature";
import { colorRgbToCss } from "./featureHelpers";
import {
  formatWordText,
  getWordTypeForFeature,
  getWordTypeStyle,
  normalizeWordType,
  WORD_TYPE_TAXONOMY,
} from "./wordStyles";

export interface LabelStyle {
  id: string;
  name: string;
  sizePx: number;
  fontStyle: "normal" | "italic";
  fontWeight?: "normal" | "bold";
  bold?: boolean;
  textTransform: "none" | "uppercase";
  color?: string;
  priority: number;
  minZoom: number;
  mapElementType?: "point" | "label";
  isCustom?: boolean;
  hasPoint?: boolean;
  pointColor?: string;
  pointStrokeColor?: string;
  pointFillOpacity?: number;
  pointStrokeOpacity?: number;
  pointStrokeWidth?: number;
}

export type CustomLabelStyle = LabelStyle;

export type NewCustomLabelStyle = Omit<CustomLabelStyle, "id">;

export const MAX_PREVIEW_FONT_SIZE_PX = 18;
export const MIN_TEXT_SIZE_PX = 6;
export const MAX_TEXT_SIZE_PX = 96;
/** Map / preview city marker: not tied to the label font size. */
export const STYLE_POINT_SWATCH_PX = 12;
/** Half the swatch: map marker and dropdown stay the same on-screen size. */
export const MAP_POINT_MARKER_RADIUS_PX = STYLE_POINT_SWATCH_PX / 2;

function svgColor(value: string): string {
  const trimmed = value.trim();
  return /^#[0-9a-f]{3,8}$/i.test(trimmed) ? trimmed : "#000000";
}

function svgNumber(value: unknown, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function mapPointSwatchSvg(options: {
  fill: string;
  stroke: string;
  fillOpacity?: number;
  strokeOpacity?: number;
  strokeWidth?: number;
  size?: number;
}): string {
  const size = Math.max(STYLE_POINT_SWATCH_PX, Math.round(options.size ?? STYLE_POINT_SWATCH_PX));
  const strokeWidth = Math.min(Math.max(svgNumber(options.strokeWidth, 1), 0), size / 2);
  const radius = Math.max(1, size / 2 - 2 - strokeWidth / 2);
  const fillOpacity = Math.max(0, Math.min(1, svgNumber(options.fillOpacity, 1)));
  const strokeOpacity = Math.max(0, Math.min(1, svgNumber(options.strokeOpacity, 1)));
  return (
    `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">` +
    `<circle cx="${size / 2}" cy="${size / 2}" r="${radius}"` +
    ` fill="${svgColor(options.fill)}"` +
    ` fill-opacity="${fillOpacity}"` +
    ` stroke="${svgColor(options.stroke)}"` +
    ` stroke-width="${strokeWidth}"` +
    ` stroke-opacity="${strokeOpacity}" />` +
    `</svg>`
  );
}

/** A usable label size from user input or stored data, or undefined when there is none. */
export function normalizeTextSizePx(value: unknown): number | undefined {
  if (value === null || value === undefined || value === "") return undefined;
  const size = Number(value);
  if (!Number.isFinite(size)) return undefined;
  return Math.max(MIN_TEXT_SIZE_PX, Math.min(MAX_TEXT_SIZE_PX, Math.round(size)));
}

export function getCustomStyleObject(style: CustomLabelStyle): CSSProperties {
  const isBold = style.fontWeight === "bold" || Boolean(style.bold);

  return {
    color: style.color || "#000000",
    fontWeight: isBold ? "bold" : "normal",
    fontStyle: style.fontStyle || "normal",
    textTransform: style.textTransform || "none",
  };
}

export function getLabelStylePreviewCss(
  style: CustomLabelStyle | Partial<LabelStyle>,
  options?: {
    limitSize?: boolean;
    maxPx?: number;
    includeSize?: boolean;
    textOnly?: boolean;
  },
): CSSProperties {
  const isBold = style.fontWeight === "bold" || Boolean(style.bold);
  const css: CSSProperties = {
    fontStyle: style.fontStyle || "normal",
    fontWeight: isBold ? "bold" : "normal",
    textTransform: style.textTransform || "none",
  };

  if (!options?.textOnly && style.color) {
    css.color = style.color;
  }

  if (options?.includeSize !== false && typeof style.sizePx === "number") {
    const size = options?.limitSize
      ? Math.min(style.sizePx, options.maxPx ?? MAX_PREVIEW_FONT_SIZE_PX)
      : style.sizePx;
    css.fontSize = `${size}px`;
  }

  return css;
}

export function hasCustomStylePoint(
  style: CustomLabelStyle | Partial<LabelStyle> | undefined | null,
): boolean {
  if (!style) return false;
  return Boolean(style.hasPoint || style.mapElementType === "point");
}

export function getCustomStyleOptionLabel(style: CustomLabelStyle): string {
  const name = style.name?.startsWith("• ") ? style.name.slice(2) : (style.name || "");
  if (style.textTransform === "uppercase") {
    return name.toUpperCase();
  }
  return name;
}

export function getWordTypeOptionStyle(typeKey: string): CSSProperties {
  const norm = normalizeWordType(typeKey);
  const tax = WORD_TYPE_TAXONOMY[norm];
  if (!tax) return { color: "#000000" };
  return {
    color: "#000000",
    fontStyle: tax.fontStyle,
    fontWeight: "bold",
    textTransform: tax.textTransform,
  };
}

export function getWordTypeOptionLabel(typeKey: string): string {
  const norm = normalizeWordType(typeKey);
  const tax = WORD_TYPE_TAXONOMY[norm];
  if (!tax) return typeKey;
  return tax.textTransform === "uppercase" ? tax.label.toUpperCase() : tax.label;
}

export function splitBalancedLine(text: string, maxLen = 13): string {
  if (text.length <= maxLen) return text;

  const candidates: { index: number; after: boolean }[] = [];
  for (let i = 0; i < text.length; i++) {
    if (text[i] === " ") candidates.push({ index: i, after: false });
    else if (text[i] === "-") candidates.push({ index: i + 1, after: true });
  }

  if (candidates.length === 0) {
    if (text.length >= 16) {
      const mid = Math.floor(text.length / 2);
      return `${text.slice(0, mid)}-<br>${text.slice(mid)}`;
    }
    return text;
  }

  const mid = text.length / 2;
  const best = candidates.reduce((chosen, candidate) => {
    const candidatePosition = candidate.after ? candidate.index : candidate.index + 0.5;
    const chosenPosition = chosen.after ? chosen.index : chosen.index + 0.5;
    return Math.abs(candidatePosition - mid) < Math.abs(chosenPosition - mid)
      ? candidate
      : chosen;
  });

  return best.after
    ? `${text.slice(0, best.index).trim()}<br>${text.slice(best.index).trim()}`
    : `${text.slice(0, best.index).trim()}<br>${text.slice(best.index + 1).trim()}`;
}

export function formatLabelHtml(formattedText: unknown): string {
  if (formattedText === null || formattedText === undefined) return "";
  const text = String(formattedText).trim();
  if (!text) return "";

  const lines = text.split("\n");
  // Line breaks the author typed are the layout: only a single-line label is
  // balanced over two lines automatically.
  const hasAuthoredBreaks = lines.length > 1;

  return lines
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) return "";
      if (hasAuthoredBreaks) return escapeHtml(trimmed);
      return splitBalancedLine(trimmed)
        .split("<br>")
        .map((segment) => escapeHtml(segment))
        .join("<br>");
    })
    .join("<br>");
}

const HTML_ENTITIES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
};

function escapeHtml(text: string): string {
  return text.replace(/[&<>"]/g, (character) => HTML_ENTITIES[character]);
}

export interface LabelPresentationModel extends LabelStyle {
  text: string;
  formattedText: string;
  html: string;
  wordType: string;
  mapElementType: "point" | "label";
  sizePx: number;
  fontStyle: "normal" | "italic";
  fontWeight: "normal" | "bold";
  textTransform: "uppercase" | "none";
  isUppercase: boolean;
  isItalic: boolean;
  isBold: boolean;
  priority: number;
  minZoom: number;
  colorCss: string;
  styleAttribute: string;
}

export interface DerivedLabelTypography {
  isUppercase: boolean;
  isItalic: boolean;
  isBold: boolean;
  color: string;
  sizePx: number;
  textTransform: "uppercase" | "none";
  fontStyle: "italic" | "normal";
  fontWeight: "bold" | "normal";
}

export function resolveLabelTypography(options: {
  wordType?: string | null;
  customLabelStyle?: CustomLabelStyle | Partial<LabelStyle> | null;
  color?: string | null;
  /** Per-element size override; a custom style's own size still wins. */
  sizePx?: number | null;
  defaultSizePx?: number;
}): DerivedLabelTypography {
  const norm = normalizeWordType(options.wordType ?? undefined);
  const taxonomy = WORD_TYPE_TAXONOMY[norm];
  const custom = options.customLabelStyle;

  const isUppercase = (custom?.textTransform ?? taxonomy?.textTransform) === "uppercase";
  const isItalic = (custom?.fontStyle ?? taxonomy?.fontStyle) === "italic";
  const isBold = custom
    ? custom.fontWeight === "bold" || Boolean(custom.bold)
    : true;
  const color = custom?.color || options.color || "#000000";
  const sizePx =
    custom?.sizePx ??
    options.sizePx ??
    taxonomy?.sizePx ??
    options.defaultSizePx ??
    12;

  return {
    isUppercase,
    isItalic,
    isBold,
    color,
    sizePx,
    textTransform: isUppercase ? "uppercase" : "none",
    fontStyle: isItalic ? "italic" : "normal",
    fontWeight: isBold ? "bold" : "normal",
  };
}

export function getEntryTypography(entry: {
  wordType?: string;
  customLabelStyle?: CustomLabelStyle | Partial<LabelStyle> | null;
  color?: string | null;
}): DerivedLabelTypography {
  return resolveLabelTypography({
    wordType: entry.wordType,
    customLabelStyle: entry.customLabelStyle,
    color: entry.color,
  });
}

function hexColor(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return /^#[0-9a-f]{3,8}$/i.test(trimmed) ? trimmed : undefined;
}

/** Canonical point fill: hex fields first, then RGB leftover from older saves. */
export function resolvePointFillHex(
  props: Record<string, unknown>,
  customStyle: CustomLabelStyle | null,
): string {
  return (
    hexColor(customStyle?.pointColor) ||
    (customStyle?.hasPoint ? hexColor(customStyle.color) : undefined) ||
    hexColor(props.pointColor) ||
    hexColor(props.color) ||
    colorRgbToCss(props.colorRgb) ||
    "#000000"
  );
}

/** Canonical point stroke: hex first, then RGB leftover from older saves. */
export function resolvePointStrokeHex(
  props: Record<string, unknown>,
  customStyle: CustomLabelStyle | null,
): string {
  return (
    hexColor(customStyle?.pointStrokeColor) ||
    hexColor(props.pointStrokeColor) ||
    colorRgbToCss(props.strokeColor) ||
    hexColor(props.strokeColor) ||
    "#000000"
  );
}

export function getLabelPresentation(
  feature: Feature | Record<string, unknown>,
  customText?: string,
): LabelPresentationModel {
  const typedFeature = feature as Feature;
  const props = (typedFeature.properties || {}) as Record<string, unknown>;
  const wordType = getWordTypeForFeature(feature);
  const taxonomy = getWordTypeStyle(wordType);
  const customStyle = parseCustomStyle(props.customLabelStyle);
  const rawText =
    customText ??
    String(props.labelText ?? props.name ?? typedFeature.name ?? "");

  // The text has its own colour when one was set; otherwise it follows the
  // element colour, which is also the point symbol's fill.
  const mapElementType =
    customStyle?.mapElementType ??
    (customStyle?.hasPoint ? "point" : undefined) ??
    taxonomy.mapElementType;
  const hasPoint = mapElementType === "point";
  const pointColor = resolvePointFillHex(props, customStyle);
  const colorCss =
    customStyle?.color ||
    colorRgbToCss(props.textColorRgb) ||
    (hasPoint ? pointColor : undefined) ||
    colorRgbToCss(props.colorRgb) ||
    (typeof props.color === "string" ? props.color : "#000000");

  const typo = resolveLabelTypography({
    wordType,
    customLabelStyle: customStyle as CustomLabelStyle,
    color: colorCss,
    sizePx: normalizeTextSizePx(props.textSizePx),
  });

  const formattedText = customStyle
    ? typo.isUppercase
      ? rawText.toUpperCase()
      : rawText
    : formatWordText(rawText, wordType, typo.textTransform);
  const html = formatLabelHtml(formattedText);

  const inlineStyles: string[] = [];
  if (typo.isItalic) inlineStyles.push("font-style: italic");
  inlineStyles.push(`font-weight: ${typo.isBold ? "bold" : "normal"}`);
  if (typo.isUppercase) inlineStyles.push("text-transform: uppercase");
  if (typo.color) inlineStyles.push(`color: ${typo.color}`);

  const pointStrokeColor = resolvePointStrokeHex(props, customStyle);

  const pointFillOpacity =
    customStyle?.pointFillOpacity ??
    (typeof props.pointFillOpacity === "number"
      ? props.pointFillOpacity
      : typeof props.fillOpacity === "number"
        ? props.fillOpacity
        : 1);

  const pointStrokeOpacity =
    customStyle?.pointStrokeOpacity ??
    (typeof props.pointStrokeOpacity === "number"
      ? props.pointStrokeOpacity
      : typeof props.strokeOpacity === "number"
        ? props.strokeOpacity
        : 1);

  const pointStrokeWidth =
    customStyle?.pointStrokeWidth ??
    (typeof props.pointStrokeWidth === "number"
      ? props.pointStrokeWidth
      : typeof props.strokeWidth === "number"
        ? props.strokeWidth
        : 1);

  return {
    id: customStyle?.id ?? wordType,
    name: customStyle?.name ?? taxonomy.label,
    text: rawText,
    formattedText,
    html,
    wordType,
    mapElementType,
    sizePx: typo.sizePx,
    fontStyle: typo.fontStyle,
    fontWeight: typo.fontWeight,
    bold: typo.isBold,
    textTransform: typo.textTransform,
    isUppercase: typo.isUppercase,
    isItalic: typo.isItalic,
    isBold: typo.isBold,
    // Collision rank follows on-screen type size, not a separate style.priority.
    priority: typo.sizePx,
    minZoom:
      customStyle?.minZoom ??
      (typeof props.minZoom === "number" ? props.minZoom : taxonomy.minZoom),
    color: typo.color,
    colorCss: typo.color,
    hasPoint,
    pointColor,
    pointStrokeColor,
    pointFillOpacity,
    pointStrokeOpacity,
    pointStrokeWidth,
    styleAttribute: inlineStyles.length
      ? ` style="${inlineStyles.join("; ")}"`
      : "",
    isCustom: Boolean(customStyle),
  };
}

function parseCustomStyle(value: unknown): {
  id?: string;
  name?: string;
  sizePx: number;
  fontStyle: "normal" | "italic";
  fontWeight: "normal" | "bold";
  textTransform: "none" | "uppercase";
  color: string;
  priority: number;
  minZoom: number;
  mapElementType?: "point" | "label";
  hasPoint?: boolean;
  pointColor?: string;
  pointStrokeColor?: string;
  pointFillOpacity?: number;
  pointStrokeOpacity?: number;
  pointStrokeWidth?: number;
} | null {
  if (!value || typeof value !== "object") return null;
  const style = value as Record<string, unknown>;
  const sizePx = Number(style.sizePx);
  const fontStyle = style.fontStyle === "italic" ? "italic" : "normal";
  const textTransform = style.textTransform === "uppercase" ? "uppercase" : "none";
  const rawColor = typeof style.color === "string" ? style.color.trim() : "";
  const color = /^#[0-9a-f]{6}$/i.test(rawColor) ? rawColor : "#000000";
  if (!Number.isFinite(sizePx) || sizePx <= 0) {
    return null;
  }
  const isBold =
    style.fontWeight === "bold" ||
    Boolean(style.bold) ||
    (style.fontWeight !== "normal" && style.bold === true);
  const hasPoint = Boolean(style.hasPoint);
  const mapElementType =
    style.mapElementType === "point" || style.mapElementType === "label"
      ? style.mapElementType
      : hasPoint
        ? "point"
        : style.hasPoint === false
          ? "label"
          : undefined;
  return {
    id: typeof style.id === "string" ? style.id : undefined,
    name: typeof style.name === "string" ? style.name : undefined,
    sizePx,
    fontStyle,
    fontWeight: isBold ? "bold" : "normal",
    textTransform,
    color,
    priority: typeof style.priority === "number" ? style.priority : 30,
    minZoom: typeof style.minZoom === "number" ? style.minZoom : 1,
    mapElementType,
    hasPoint,
    pointColor: typeof style.pointColor === "string" ? style.pointColor : undefined,
    pointStrokeColor: typeof style.pointStrokeColor === "string" ? style.pointStrokeColor : undefined,
    pointFillOpacity: typeof style.pointFillOpacity === "number" ? style.pointFillOpacity : undefined,
    pointStrokeOpacity: typeof style.pointStrokeOpacity === "number" ? style.pointStrokeOpacity : undefined,
    pointStrokeWidth: typeof style.pointStrokeWidth === "number" ? style.pointStrokeWidth : undefined,
  };
}
