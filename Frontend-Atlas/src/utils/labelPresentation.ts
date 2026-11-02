import type { Feature } from "../typescript/feature";
import { colorRgbToCss } from "./featureHelpers";
import {
  capitalizeWords,
  formatWordText,
  getWordTypeForFeature,
  WORD_TYPE_TAXONOMY,
} from "./wordStyles";

export interface LabelFontStyle {
  fontStyle: "normal" | "italic";
  textTransform: "uppercase" | "none";
}

export interface LabelCategoryInfo {
  priority: number;
  minZoom: number;
  category: string;
}

export function parseLabelFontStyle(rawStyle?: unknown): LabelFontStyle {
  const styleStr = typeof rawStyle === "string" ? rawStyle.toLowerCase() : "";
  return {
    fontStyle:
      styleStr.includes("italic") || styleStr.includes("oblique")
        ? "italic"
        : "normal",
    textTransform: styleStr.includes("uppercase") ? "uppercase" : "none",
  };
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

export function formatLabelHtml(rawText: unknown, isUppercase = false): string {
  if (rawText === null || rawText === undefined) return "";
  const text = String(rawText).trim();
  if (!text) return "";

  return text
    .split("\n")
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) return "";
      return splitBalancedLine(
        isUppercase ? trimmed.toUpperCase() : capitalizeWords(trimmed),
      );
    })
    .join("<br>");
}

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
  feature: Feature | Record<string, unknown>,
): LabelCategoryInfo {
  const props = ((feature as Feature).properties || {}) as Record<string, unknown>;
  const rawType = String(
    props.rawType || props.entityType || props.mapElementType || "",
  ).toLowerCase();
  const fontStyle = String(props.fontStyle || "").toLowerCase();
  const key = resolveCategoryKey(
    rawType,
    Number(props.sizePx ?? 12),
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
  const priority = Number.parseFloat(el.dataset.priority || "");
  const minZoom = Number.parseFloat(el.dataset.minZoom || "");
  if (Number.isFinite(priority) && Number.isFinite(minZoom)) {
    return { priority, minZoom };
  }

  const size = Number.parseFloat(el.style.getPropertyValue("--label-size") || "12") || 12;
  const isUpper = el.style.getPropertyValue("--label-transform").includes("uppercase");
  const isItalic = el.style.getPropertyValue("--label-style").includes("italic");
  const key = resolveCategoryKey(el.dataset.category || "", size, isUpper, isItalic);
  const [fallbackPriority, fallbackMinZoom] = LABEL_CATEGORY_RULES[key] || [30, 2.5];
  return { priority: fallbackPriority, minZoom: fallbackMinZoom };
}

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
  feature: Feature | Record<string, unknown>,
  customText?: string,
): LabelPresentationModel {
  const typedFeature = feature as Feature;
  const props = (typedFeature.properties || {}) as Record<string, unknown>;
  const wordType = getWordTypeForFeature(feature);
  const taxonomy = WORD_TYPE_TAXONOMY[wordType];
  const rawText =
    customText ??
    String(props.labelText ?? props.name ?? typedFeature.name ?? "");
  const explicitFontStyle = props.fontStyle
    ? parseLabelFontStyle(props.fontStyle)
    : null;
  const isUppercase = explicitFontStyle
    ? explicitFontStyle.textTransform === "uppercase"
    : taxonomy.textTransform === "uppercase";
  const isItalic = explicitFontStyle
    ? explicitFontStyle.fontStyle === "italic"
    : taxonomy.fontStyle === "italic";
  const formattedText = formatWordText(rawText, wordType);
  const html = formatLabelHtml(rawText, isUppercase);
  const sizePx = Number(props.sizePx ?? taxonomy.sizePx);
  const mapElementType =
    props.mapElementType === "point" || props.mapElementType === "label"
      ? props.mapElementType
      : taxonomy.mapElementType;
  const colorCss =
    colorRgbToCss(props.colorRgb) ||
    (typeof props.color === "string" ? props.color : "#000000");
  const inlineStyles: string[] = [];
  if (isItalic) inlineStyles.push("font-style: italic");
  if (isUppercase) inlineStyles.push("text-transform: uppercase");

  return {
    text: rawText,
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
    styleAttribute: inlineStyles.length
      ? ` style="${inlineStyles.join("; ")}"`
      : "",
  };
}
