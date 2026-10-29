import { describe, it, expect } from "vitest";
import {
  capitalizeFirstOnly,
  capitalizeWords,
  getWordTypeStyle,
  WORD_TYPE_STYLES,
  parseLabelFontStyle,
} from "../../src/utils/mapLabelUtils";

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
});

