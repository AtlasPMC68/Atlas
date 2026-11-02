import type { Feature } from "../typescript/feature";
import { colorRgbToCss } from "./featureHelpers";
import {
  formatWordText,
  getWordTypeForFeature,
  getWordTypeStyle,
} from "./wordStyles";

export interface LabelFontStyle {
  fontStyle: "normal" | "italic";
  textTransform: "uppercase" | "none";
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

export function formatLabelHtml(formattedText: unknown): string {
  if (formattedText === null || formattedText === undefined) return "";
  const text = String(formattedText).trim();
  if (!text) return "";

  return text
    .split("\n")
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed) return "";
      return splitBalancedLine(trimmed);
    })
    .join("<br>");
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
  const taxonomy = getWordTypeStyle(wordType);
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
  const formattedText = formatWordText(
    rawText,
    wordType,
    isUppercase ? "uppercase" : explicitFontStyle ? "none" : undefined,
  );
  const html = formatLabelHtml(formattedText);
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
    colorCss,
    styleAttribute: inlineStyles.length
      ? ` style="${inlineStyles.join("; ")}"`
      : "",
  };
}
