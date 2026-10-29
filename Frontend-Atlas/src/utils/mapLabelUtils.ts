import type { Feature } from "../typescript/feature";

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

export function capitalizeFirstOnly(text: string): string {
  if (!text) return text;
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}

export function capitalizeWords(text: string): string {
  if (!text) return text;
  return text
    .toLowerCase()
    .split(/([\s-]+)/)
    .map((part) => (part.length > 0 ? part.charAt(0).toUpperCase() + part.slice(1) : part))
    .join("");
}

export const WORD_TYPE_STYLES: Record<string, WordTypeStyle> = {
  city: {
    label: "Ville",
    mapElementType: "point",
    sizePx: 12,
    fontStyle: "normal",
    transform: capitalizeFirstOnly,
  },
  province: {
    label: "Province",
    mapElementType: "label",
    sizePx: 14,
    fontStyle: "uppercase",
    transform: (t: string) => (t ? t.toUpperCase() : t),
  },
  state: {
    label: "État",
    mapElementType: "label",
    sizePx: 14,
    fontStyle: "uppercase",
    transform: (t: string) => (t ? t.toUpperCase() : t),
  },
  country: {
    label: "Pays",
    mapElementType: "label",
    sizePx: 16,
    fontStyle: "uppercase",
    transform: (t: string) => (t ? t.toUpperCase() : t),
  },
  continent: {
    label: "Continent",
    mapElementType: "label",
    sizePx: 18,
    fontStyle: "uppercase",
    transform: (t: string) => (t ? t.toUpperCase() : t),
  },
  ocean: {
    label: "Océan",
    mapElementType: "label",
    sizePx: 18,
    fontStyle: "italic",
    transform: (t: string) => (t ? t.toUpperCase() : t),
  },
  sea: {
    label: "Mer",
    mapElementType: "label",
    sizePx: 16,
    fontStyle: "italic",
    transform: capitalizeWords,
  },
  fleuve: {
    label: "Fleuve",
    mapElementType: "label",
    sizePx: 14,
    fontStyle: "italic",
    transform: capitalizeWords,
  },
  lake: {
    label: "Lac",
    mapElementType: "label",
    sizePx: 12,
    fontStyle: "italic",
    transform: capitalizeWords,
  },
  river: {
    label: "Rivière",
    mapElementType: "label",
    sizePx: 10,
    fontStyle: "italic",
    transform: capitalizeWords,
  },
  territory: {
    label: "Territoire",
    mapElementType: "label",
    sizePx: 14,
    fontStyle: "uppercase",
    transform: (t: string) => (t ? t.toUpperCase() : t),
  },
};

export function getWordTypeStyle(type?: string): WordTypeStyle {
  const key = (type || "").toLowerCase();
  return WORD_TYPE_STYLES[key] || WORD_TYPE_STYLES.city;
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
      : capitalizeFirstOnly(trimmed);
    return splitBalancedLine(cased);
  });

  return formatted.join("<br>");
}

// Category visual hierarchy rules: [priority, minZoom, categoryName]
export const LABEL_CATEGORY_RULES: Record<string, [number, number, string]> = {
  continent: [90, 1.0, "continent"],
  ocean:     [80, 1.0, "ocean"],
  country:   [70, 1.5, "country"],
  sea:       [60, 2.0, "sea"],
  state:     [50, 2.5, "state"],
  province:  [50, 2.5, "state"],
  territory: [50, 2.5, "state"],
  fleuve:    [40, 2.25, "fleuve"],
  lake:      [20, 2.75, "lake"],
  city:      [30, 4.0, "city"],
  point:     [30, 4.0, "city"],
  river:     [10, 4.5, "river"],
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

