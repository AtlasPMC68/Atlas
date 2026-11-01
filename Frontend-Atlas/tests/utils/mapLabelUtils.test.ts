import { describe, it, expect } from "vitest";
import {
  capitalizeFirstOnly,
  capitalizeWords,
  getWordTypeStyle,
  WORD_TYPE_STYLES,
  parseLabelFontStyle,
  formatWordText,
  isTextFeature,
  getWordTypeForFeature,
  applyWordStyleToFeature,
} from "../../src/utils/mapLabelUtils";
import type { Feature } from "../../src/typescript/feature";

describe("mapLabelUtils - Word Type Styles and Police", () => {
  it("defines expected font styles, sizes, and element types for word categories", () => {
    // City / Ville -> point, 12px, normal
    expect(WORD_TYPE_STYLES.city).toBeDefined();
    expect(WORD_TYPE_STYLES.city.mapElementType).toBe("point");
    expect(WORD_TYPE_STYLES.city.sizePx).toBe(12);
    expect(WORD_TYPE_STYLES.city.fontStyle).toBe("normal");

    // Province -> label, 14px, uppercase
    expect(WORD_TYPE_STYLES.province).toBeDefined();
    expect(WORD_TYPE_STYLES.province.mapElementType).toBe("label");
    expect(WORD_TYPE_STYLES.province.sizePx).toBe(14);
    expect(WORD_TYPE_STYLES.province.fontStyle).toBe("uppercase");

    // Country / Pays -> label, 16px, uppercase
    expect(WORD_TYPE_STYLES.country).toBeDefined();
    expect(WORD_TYPE_STYLES.country.mapElementType).toBe("label");
    expect(WORD_TYPE_STYLES.country.sizePx).toBe(16);
    expect(WORD_TYPE_STYLES.country.fontStyle).toBe("uppercase");

    // Lake / Lac -> label, 12px, italic
    expect(WORD_TYPE_STYLES.lake).toBeDefined();
    expect(WORD_TYPE_STYLES.lake.mapElementType).toBe("label");
    expect(WORD_TYPE_STYLES.lake.sizePx).toBe(12);
    expect(WORD_TYPE_STYLES.lake.fontStyle).toBe("italic");

    // River / Rivière -> label, 10px, italic
    expect(WORD_TYPE_STYLES.river).toBeDefined();
    expect(WORD_TYPE_STYLES.river.sizePx).toBe(10);
    expect(WORD_TYPE_STYLES.river.fontStyle).toBe("italic");
  });

  it("capitalizeFirstOnly capitalizes ONLY the very first letter and lowers the rest", () => {
    expect(capitalizeFirstOnly("SASKATCHEWAN")).toBe("Saskatchewan");
    expect(capitalizeFirstOnly("QUÉBEC")).toBe("Québec");
    expect(capitalizeFirstOnly("ONTARIO")).toBe("Ontario");
  });

  it("capitalizeWords formats text with initial capitals on hyphenated and spaced names", () => {
    expect(capitalizeWords("QUÉBEC")).toBe("Québec");
    expect(capitalizeWords("COLOMBIE-BRITANNIQUE")).toBe("Colombie-Britannique");
    expect(capitalizeWords("NOUVELLE ÉCOSSE")).toBe("Nouvelle Écosse");
  });

  it("transforms text to uppercase for province, country, continent and state", () => {
    expect(WORD_TYPE_STYLES.province.transform("Québec")).toBe("QUÉBEC");
    expect(WORD_TYPE_STYLES.country.transform("Canada")).toBe("CANADA");
    expect(WORD_TYPE_STYLES.city.transform("QUÉBEC")).toBe("Québec");
  });

  it("getWordTypeStyle resolves correctly with fallback to city", () => {
    expect(getWordTypeStyle("province").label).toBe("Province");
    expect(getWordTypeStyle("CITY").label).toBe("Ville");
    expect(getWordTypeStyle("unknown_xyz").label).toBe("Ville");
  });

  it("parseLabelFontStyle parses uppercase and italic correctly", () => {
    const provinceStyle = parseLabelFontStyle(WORD_TYPE_STYLES.province.fontStyle);
    expect(provinceStyle.textTransform).toBe("uppercase");
    expect(provinceStyle.fontStyle).toBe("normal");

    const lakeStyle = parseLabelFontStyle(WORD_TYPE_STYLES.lake.fontStyle);
    expect(lakeStyle.textTransform).toBe("none");
    expect(lakeStyle.fontStyle).toBe("italic");

    const cityStyle = parseLabelFontStyle(WORD_TYPE_STYLES.city.fontStyle);
    expect(cityStyle.textTransform).toBe("none");
    expect(cityStyle.fontStyle).toBe("normal");
  });

  it("isTextFeature accurately identifies text and label features", () => {
    expect(isTextFeature(null)).toBe(false);
    expect(isTextFeature(undefined)).toBe(false);

    const pointFeature = {
      type: "Feature",
      id: "f-1",
      geometry: { type: "Point", coordinates: [0, 0] },
      properties: { name: "City" },
    } as Feature;
    expect(isTextFeature(pointFeature)).toBe(true);

    const zoneFeature = {
      type: "Feature",
      id: "f-2",
      geometry: { type: "Polygon", coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] },
      properties: { name: "Zone", mapElementType: "zone" },
    } as Feature;
    expect(isTextFeature(zoneFeature)).toBe(false);

    const labelFeature = {
      type: "Feature",
      id: "f-3",
      geometry: { type: "Point", coordinates: [0, 0] },
      properties: { name: "Province", mapElementType: "label" },
    } as Feature;
    expect(isTextFeature(labelFeature)).toBe(true);
  });

  it("getWordTypeForFeature extracts word type with correct fallbacks", () => {
    expect(getWordTypeForFeature(null)).toBe("city");

    const provFeature = {
      properties: { rawType: "province" },
    } as any;
    expect(getWordTypeForFeature(provFeature)).toBe("province");

    const labelWithoutRawType = {
      properties: { mapElementType: "label" },
    } as any;
    expect(getWordTypeForFeature(labelWithoutRawType)).toBe("province");

    const pointWithoutRawType = {
      properties: { mapElementType: "point" },
    } as any;
    expect(getWordTypeForFeature(pointWithoutRawType)).toBe("city");
  });

  it("formatWordText transforms text according to word type", () => {
    expect(formatWordText("montreal", "city")).toBe("Montreal");
    expect(formatWordText("quebec", "province")).toBe("QUEBEC");
    expect(formatWordText("ontario", "lake")).toBe("Ontario");
  });

  it("applyWordStyleToFeature returns a consistently styled feature", () => {
    const rawFeature: Feature = {
      type: "Feature",
      id: "feat-test",
      name: "canada",
      geometry: { type: "Point", coordinates: [-75, 45] },
      properties: { name: "canada" },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
    };

    const styled = applyWordStyleToFeature(rawFeature, "country");
    expect(styled.name).toBe("CANADA");
    expect(styled.properties.name).toBe("CANADA");
    expect(styled.properties.labelText).toBe("CANADA");
    expect(styled.properties.mapElementType).toBe("label");
    expect(styled.properties.sizePx).toBe(16);
    expect(styled.properties.fontStyle).toBe("uppercase");
    expect(styled.properties.rawType).toBe("country");
    expect(styled.properties.type).toBe("country");
  });
});

