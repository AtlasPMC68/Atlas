import wordStyleConfig from "../../../shared/word-taxonomy.json";
import type { Feature } from "../typescript/feature";
import { getMapElementType } from "./featureHelpers";

type WordStyleConfig = {
  capitalization: {
    lowercaseParticles: string[];
    apostrophePrefixes: string[];
  };
  types: Record<
    string,
    {
      label: string;
      mapElementType: "point" | "label";
      sizePx: number;
      fontStyle: "normal" | "italic";
      textTransform: "uppercase" | "none";
      priority: number;
      minZoom: number;
      category: string;
    }
  >;
};

const config = wordStyleConfig as WordStyleConfig;

export type WordType = keyof typeof wordStyleConfig.types;

export interface WordTypeTaxonomyEntry {
  id: WordType;
  label: string;
  mapElementType: "point" | "label";
  sizePx: number;
  fontStyle: "normal" | "italic";
  textTransform: "uppercase" | "none";
  priority: number;
  minZoom: number;
  category: string;
}

export interface WordTypeStyle {
  label: string;
  mapElementType: "point" | "label";
  sizePx: number;
  fontStyle: string;
  transform: (text: string) => string;
}

export const LOWERCASE_PARTICLES = new Set(
  config.capitalization.lowercaseParticles,
);
const APOSTROPHE_PREFIXES = new Set(config.capitalization.apostrophePrefixes);
const APOSTROPHE_PREFIX_PATTERN = new RegExp(
  `^([${[...APOSTROPHE_PREFIXES].map((prefix) => prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("")}]['’])(.*)$`,
  "i",
);

export const WORD_TYPE_TAXONOMY = Object.fromEntries(
  Object.entries(config.types).map(([id, entry]) => [
    id,
    { id, ...entry },
  ]),
) as Record<WordType, WordTypeTaxonomyEntry>;

export const toUpperCaseTransform = (text: string): string =>
  text ? text.toUpperCase() : text;

export function capitalizeSegment(segment: string): string {
  if (!segment) return segment;
  return segment.charAt(0).toUpperCase() + segment.slice(1).toLowerCase();
}

export function capitalizeFirstOnly(text: string): string {
  return capitalizeSegment(text);
}

export function capitalizeWords(text: string): string {
  if (!text) return text;
  return text
    .split(/([\s-]+)/)
    .map((part, index) => {
      if (!part || /^[\s-]+$/.test(part)) return part;

      const apostropheMatch = part.match(APOSTROPHE_PREFIX_PATTERN);
      if (
        apostropheMatch &&
        APOSTROPHE_PREFIXES.has(apostropheMatch[1][0].toLowerCase())
      ) {
        const prefix = apostropheMatch[1].slice(0, -1).toLowerCase();
        const apostrophe = apostropheMatch[1].slice(-1);
        return `${prefix}${apostrophe}${capitalizeSegment(apostropheMatch[2])}`;
      }

      const lower = part.toLowerCase();
      if (index > 0 && LOWERCASE_PARTICLES.has(lower)) return lower;
      return capitalizeSegment(part);
    })
    .join("");
}

export function normalizeWordType(type?: string): WordType {
  const key = (type || "").toLowerCase();
  return Object.prototype.hasOwnProperty.call(WORD_TYPE_TAXONOMY, key)
    ? (key as WordType)
    : "city";
}

export const WORD_TYPE_STYLES: Record<WordType, WordTypeStyle> = Object.fromEntries(
  Object.entries(WORD_TYPE_TAXONOMY).map(([key, entry]) => [
    key,
    {
      label: entry.label,
      mapElementType: entry.mapElementType,
      sizePx: entry.sizePx,
      fontStyle: [
        entry.fontStyle === "italic" ? "italic" : "",
        entry.textTransform === "uppercase" ? "uppercase" : "",
      ]
        .filter(Boolean)
        .join(" ") || "normal",
      transform:
        entry.textTransform === "uppercase" ? toUpperCaseTransform : capitalizeWords,
    },
  ]),
) as Record<WordType, WordTypeStyle>;

export function getWordTypeStyle(type?: string): WordTypeStyle {
  return WORD_TYPE_STYLES[normalizeWordType(type)];
}

export function formatWordText(text: string, wordType?: string): string {
  if (!text) return text;
  return getWordTypeStyle(wordType).transform(text);
}

export function isTextFeature(
  feature?: Feature | Record<string, unknown> | null,
): boolean {
  if (!feature) return false;
  const props = (feature.properties || {}) as Record<string, unknown>;
  const elemType = getMapElementType(feature as Feature);
  return (
    elemType === "label" ||
    elemType === "point" ||
    Boolean(props.isOcrText) ||
    props.labelText !== undefined ||
    props.rawType !== undefined ||
    (feature as Feature).geometry?.type === "Point"
  );
}

export function getWordTypeForFeature(
  feature?: Feature | Record<string, unknown> | null,
): WordType {
  if (!feature) return "city";
  const props = (feature.properties || {}) as Record<string, unknown>;
  const rawType = String(props.rawType || props.type || "").toLowerCase();
  if (Object.prototype.hasOwnProperty.call(WORD_TYPE_TAXONOMY, rawType)) {
    return normalizeWordType(rawType);
  }
  return getMapElementType(feature as Feature) === "label" ? "province" : "city";
}

export function applyWordStyleToFeature(
  feature: Feature,
  wordType: WordType,
  newText?: string,
): Feature {
  const canonicalType = normalizeWordType(wordType);
  const style = getWordTypeStyle(canonicalType);
  const currentText =
    newText !== undefined
      ? newText
      : feature.properties?.labelText ?? feature.properties?.name ?? feature.name ?? "";
  const transformedText = formatWordText(currentText, canonicalType);

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
      rawType: canonicalType,
      type: canonicalType,
    },
  };
}
