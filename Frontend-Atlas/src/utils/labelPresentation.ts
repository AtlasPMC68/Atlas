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
}

export type CustomLabelStyle = LabelStyle;

export type NewCustomLabelStyle = Omit<CustomLabelStyle, "id">;

export const MAX_PREVIEW_FONT_SIZE_PX = 18;
export const MIN_TEXT_SIZE_PX = 6;
export const MAX_TEXT_SIZE_PX = 96;

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
    color: style.color || "inherit",
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

export function formatCustomStyleOptionLabel(
  style: CustomLabelStyle,
  verbose = true,
): string {
  if (!verbose) {
    return style.name;
  }

  const parts: string[] = [];

  if (style.color) {
    parts.push(style.color);
  }

  const isBold = style.fontWeight === "bold" || Boolean(style.bold);
  const isItalic = style.fontStyle === "italic";
  const isUppercase = style.textTransform === "uppercase";

  if (isBold) {
    parts.push("gras");
  }
  if (isItalic) {
    parts.push("italique");
  }
  if (isUppercase) {
    parts.push("majuscules");
  }

  if (parts.length === 0) {
    return `${style.name} (personnalisé)`;
  }

  return `${style.name} (${parts.join(", ")})`;
}

export function getWordTypeOptionStyle(typeKey: string): CSSProperties {
  const norm = normalizeWordType(typeKey);
  const tax = WORD_TYPE_TAXONOMY[norm];
  if (!tax) return {};
  return {
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
  const colorCss =
    customStyle?.color ||
    colorRgbToCss(props.textColorRgb) ||
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
  const mapElementType = customStyle?.mapElementType ?? taxonomy.mapElementType;

  const inlineStyles: string[] = [];
  if (typo.isItalic) inlineStyles.push("font-style: italic");
  inlineStyles.push(`font-weight: ${typo.isBold ? "bold" : "normal"}`);
  if (typo.isUppercase) inlineStyles.push("text-transform: uppercase");

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
    priority: customStyle?.priority ?? taxonomy.priority,
    minZoom: customStyle?.minZoom ?? taxonomy.minZoom,
    color: typo.color,
    colorCss: typo.color,
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
} | null {
  if (!value || typeof value !== "object") return null;
  const style = value as Record<string, unknown>;
  if (
    typeof style.sizePx !== "number" ||
    !Number.isFinite(style.sizePx) ||
    (style.fontStyle !== "normal" && style.fontStyle !== "italic") ||
    (style.textTransform !== "none" && style.textTransform !== "uppercase") ||
    typeof style.color !== "string" ||
    !/^#[0-9a-f]{6}$/i.test(style.color)
  ) {
    return null;
  }
  const isBold =
    style.fontWeight === "bold" ||
    Boolean(style.bold) ||
    (style.fontWeight !== "normal" && style.bold === true);
  const mapElementType =
    style.mapElementType === "point" || style.mapElementType === "label"
      ? style.mapElementType
      : undefined;
  return {
    id: typeof style.id === "string" ? style.id : undefined,
    name: typeof style.name === "string" ? style.name : undefined,
    sizePx: style.sizePx,
    fontStyle: style.fontStyle,
    fontWeight: isBold ? "bold" : "normal",
    textTransform: style.textTransform,
    color: style.color,
    priority: typeof style.priority === "number" ? style.priority : 30,
    minZoom: typeof style.minZoom === "number" ? style.minZoom : 1,
    mapElementType,
  };
}
