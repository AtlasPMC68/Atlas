import type { Feature } from "../typescript/feature";
import { colorRgbToCss } from "./featureHelpers";
import {
  formatWordText,
  getWordTypeForFeature,
  getWordTypeStyle,
} from "./wordStyles";

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
      return splitBalancedLine(trimmed)
        .split("<br>")
        .map((segment) => escapeHtml(segment))
        .join("<br>");
    })
    .join("<br>");
}
// Security Improvement: Added HTML escaping (escapeHtml) to the label formatting pipeline. 
// This neutralizes special characters (&, <, >, ", ') across line segments 
// to prevent potential XSS vulnerabilities or unintended HTML rendering from raw OCR text inputs.
function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (character) => {
    const entities: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[character];
  });
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
  const customStyle = parseCustomStyle(props.customLabelStyle);
  const rawText =
    customText ??
    String(props.labelText ?? props.name ?? typedFeature.name ?? "");
  const isUppercase = (customStyle?.textTransform ?? taxonomy.textTransform) === "uppercase";
  const isItalic = (customStyle?.fontStyle ?? taxonomy.fontStyle) === "italic";
  const formattedText = customStyle
    ? isUppercase
      ? rawText.toUpperCase()
      : rawText
    : formatWordText(rawText, wordType, isUppercase ? "uppercase" : "none");
  const html = formatLabelHtml(formattedText);
  const sizePx = customStyle?.sizePx ?? taxonomy.sizePx;
  const mapElementType = customStyle ? "label" : taxonomy.mapElementType;
  const colorCss =
    customStyle?.color ||
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
    priority: customStyle?.priority ?? taxonomy.priority,
    minZoom: customStyle?.minZoom ?? taxonomy.minZoom,
    colorCss,
    styleAttribute: inlineStyles.length
      ? ` style="${inlineStyles.join("; ")}"`
      : "",
  };
}

function parseCustomStyle(value: unknown): {
  sizePx: number;
  fontStyle: "normal" | "italic";
  textTransform: "none" | "uppercase";
  color: string;
  priority: number;
  minZoom: number;
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
  return {
    sizePx: style.sizePx,
    fontStyle: style.fontStyle,
    textTransform: style.textTransform,
    color: style.color,
    priority: typeof style.priority === "number" ? style.priority : 30,
    minZoom: typeof style.minZoom === "number" ? style.minZoom : 1,
  };
}
