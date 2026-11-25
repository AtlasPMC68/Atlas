import { describe, it, expect } from "vitest";
import {
  capitalizeWords,
  toUpperCaseTransform,
  LOWERCASE_PARTICLES,
  getWordTypeStyle,
  WORD_TYPE_STYLES,
  formatWordText,
  isTextFeature,
  getWordTypeForFeature,
  applyWordStyleToFeature,
  WORD_TYPE_TAXONOMY,
} from "../../src/utils/wordStyles";
import {
  getLabelPresentation,
  getWordTypeOptionStyle,
  getCustomStyleObject,
  mapPointSwatchSvg,
  resolvePointFillHex,
  resolvePointStrokeHex,
  type CustomLabelStyle,
} from "../../src/utils/labelPresentation";
import { getMapElementType } from "../../src/utils/featureHelpers";
import {
  prepareFeatureForEdit,
  coerceEditedFeature,
  getWordTypePreviewStyle,
} from "../../src/utils/featureTextEditing";
import wordStyleConfig from "../../../shared/word-taxonomy.json";
import type { Feature } from "../../src/typescript/feature";

describe("shared word styles and label presentation", () => {
  it("uses the shared formatting examples for every frontend word style", () => {
    for (const example of wordStyleConfig.formattingExamples) {
      expect(formatWordText(example.input, example.type)).toBe(example.expected);
    }

    expect(Object.keys(WORD_TYPE_TAXONOMY).sort()).toEqual(
      Object.keys(wordStyleConfig.types).sort(),
    );
  });

  it("defines expected font styles, sizes, and element types for word categories", () => {
    // City / Ville -> point, 12px, normal
    expect(WORD_TYPE_STYLES.city).toBeDefined();
    expect(WORD_TYPE_STYLES.city.mapElementType).toBe("point");
    expect(WORD_TYPE_STYLES.city.sizePx).toBe(12);
    expect(WORD_TYPE_STYLES.city.fontStyle).toBe("normal");
    expect(WORD_TYPE_STYLES.city.priority).toBe(30);

    // Province -> label, 14px, uppercase
    expect(WORD_TYPE_STYLES.province).toBeDefined();
    expect(WORD_TYPE_STYLES.province.mapElementType).toBe("label");
    expect(WORD_TYPE_STYLES.province.sizePx).toBe(14);
    expect(WORD_TYPE_STYLES.province.cssFontStyle).toBe("uppercase");

    // Country / Pays -> label, 16px, uppercase
    expect(WORD_TYPE_STYLES.country).toBeDefined();
    expect(WORD_TYPE_STYLES.country.mapElementType).toBe("label");
    expect(WORD_TYPE_STYLES.country.sizePx).toBe(16);
    expect(WORD_TYPE_STYLES.country.cssFontStyle).toBe("uppercase");

    // Lake / Lac -> label, 12px, italic
    expect(WORD_TYPE_STYLES.lake).toBeDefined();
    expect(WORD_TYPE_STYLES.lake.mapElementType).toBe("label");
    expect(WORD_TYPE_STYLES.lake.sizePx).toBe(12);
    expect(WORD_TYPE_STYLES.lake.cssFontStyle).toBe("italic");

    // River / Rivière -> label, 10px, italic
    expect(WORD_TYPE_STYLES.river).toBeDefined();
    expect(WORD_TYPE_STYLES.river.sizePx).toBe(10);
    expect(WORD_TYPE_STYLES.river.cssFontStyle).toBe("italic");
  });

  it("capitalizeWords formats text with initial capitals on hyphenated and spaced names, preserving particles", () => {
    expect(capitalizeWords("QUÉBEC")).toBe("Québec");
    expect(capitalizeWords("COLOMBIE-BRITANNIQUE")).toBe("Colombie-Britannique");
    expect(capitalizeWords("NOUVELLE ÉCOSSE")).toBe("Nouvelle Écosse");
    expect(capitalizeWords("new york city")).toBe("New York City");
    expect(capitalizeWords("saint-pierre")).toBe("Saint-Pierre");
    expect(capitalizeWords("golfe du mexique")).toBe("Golfe du Mexique");
    expect(capitalizeWords("mer du labrador")).toBe("Mer du Labrador");
    expect(capitalizeWords("lac supérieur")).toBe("Lac Supérieur");
    expect(capitalizeWords("baie d'hudson")).toBe("Baie d'Hudson");
    expect(toUpperCaseTransform("saint-pierre")).toBe("SAINT-PIERRE");
    expect(LOWERCASE_PARTICLES.has("du")).toBe(true);
  });

  it("transforms text to uppercase for province, country, continent and state", () => {
    expect(WORD_TYPE_STYLES.province.transform("Québec")).toBe("QUÉBEC");
    expect(WORD_TYPE_STYLES.country.transform("Canada")).toBe("CANADA");
    expect(WORD_TYPE_STYLES.city.transform("QUÉBEC")).toBe("Québec");
    expect(WORD_TYPE_STYLES.ocean.transform("ocean atlantique")).toBe("OCEAN ATLANTIQUE");
  });

  it("getWordTypeStyle resolves correctly with fallback to city", () => {
    expect(getWordTypeStyle("province").label).toBe("Province");
    expect(getWordTypeStyle("CITY").label).toBe("Ville");
    expect(getWordTypeStyle("unknown_xyz").label).toBe("Ville");
  });

  it("previews the configured font size for the selected word type", () => {
    expect(getWordTypePreviewStyle("city").fontSize).toBe("12px");
    expect(getWordTypePreviewStyle("province").fontSize).toBe("14px");
    expect(getWordTypePreviewStyle("country").fontSize).toBe("16px");
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
      properties: { name: "canada", mapElementType: "label" },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      projectId: ""
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

  it("getLabelPresentation returns complete unified presentation model", () => {
    const rawFeature: Feature = {
      type: "Feature",
      id: "feat-pres",
      name: "baie d'hudson",
      geometry: { type: "Point", coordinates: [-85, 60] },
      properties: {
        name: "baie d'hudson",
        rawType: "sea",
        mapElementType: "label",
      } satisfies Feature["properties"],
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      projectId: ""
    };

    const pres = getLabelPresentation(rawFeature);
    expect(pres.text).toBe("baie d'hudson");
    expect(pres.formattedText).toBe("Baie d'Hudson");
    expect(pres.wordType).toBe("sea");
    expect(pres.mapElementType).toBe("label");
    expect(pres.sizePx).toBe(16);
    expect(pres.fontStyle).toBe("italic");
    expect(pres.isItalic).toBe(true);
    expect(pres.fontWeight).toBe("bold");
    expect(pres.isBold).toBe(true);
    expect(pres.priority).toBe(16);
    expect(pres.minZoom).toBe(2.0);
    expect(pres.html).toContain("Baie d'Hudson");
  });

  it("prefers hex pointColor over a stale colorRgb for the symbol", () => {
    const feature: Feature = {
      type: "Feature",
      id: "feat-stale-rgb",
      name: "Québec",
      geometry: { type: "Point", coordinates: [-71, 46] },
      properties: {
        name: "Québec",
        rawType: "city",
        mapElementType: "point",
        pointColor: "#dc2626",
        colorRgb: [0, 0, 255],
        pointStrokeColor: "#111111",
        strokeColor: [255, 255, 0],
      },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      projectId: "",
    };
    const props = feature.properties as Record<string, unknown>;
    expect(resolvePointFillHex(props, null)).toBe("#dc2626");
    expect(resolvePointStrokeHex(props, null)).toBe("#111111");
    const pres = getLabelPresentation(feature);
    expect(pres.pointColor).toBe("#dc2626");
    expect(pres.pointStrokeColor).toBe("#111111");
  });

  it("uses this word's own size as collision priority, not its type", () => {
    const feature: Feature = {
      type: "Feature",
      id: "feat-city-from-sea",
      name: "Mer du Labrador",
      geometry: { type: "Point", coordinates: [-60, 55] },
      properties: {
        name: "Mer du Labrador",
        rawType: "city",
        mapElementType: "point",
        textSizePx: 20,
      },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      projectId: "",
    };

    const presentation = getLabelPresentation(feature);
    expect(presentation.wordType).toBe("city");
    expect(presentation.mapElementType).toBe("point");
    expect(presentation.sizePx).toBe(20);
    expect(presentation.priority).toBe(20);
  });

  it("applies custom label style bold/fontWeight correctly to presentation model", () => {
    const featureWithCustomNormal: Feature = {
      type: "Feature",
      id: "feat-custom-normal",
      name: "Terre de Rupert",
      geometry: { type: "Point", coordinates: [-75, 52] },
      properties: {
        name: "Terre de Rupert",
        customLabelStyle: {
          id: "style-1",
          name: "Fort",
          sizePx: 14,
          fontStyle: "normal",
          fontWeight: "normal",
          bold: false,
          textTransform: "none",
          color: "#ff0000",
          priority: 40,
          minZoom: 1,
        },
      },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      projectId: "",
    };

    const presNormal = getLabelPresentation(featureWithCustomNormal);
    expect(presNormal.fontWeight).toBe("normal");
    expect(presNormal.isBold).toBe(false);
    expect(presNormal.styleAttribute).toContain("font-weight: normal");

    const featureWithCustomBold: Feature = {
      ...featureWithCustomNormal,
      properties: {
        ...featureWithCustomNormal.properties,
        customLabelStyle: {
          ...featureWithCustomNormal.properties.customLabelStyle!,
          fontWeight: "bold",
          bold: true,
        },
      },
    };

    const presBold = getLabelPresentation(featureWithCustomBold);
    expect(presBold.fontWeight).toBe("bold");
    expect(presBold.isBold).toBe(true);
    expect(presBold.styleAttribute).toContain("font-weight: bold");
  });

  it("still applies a custom style when sizePx is a numeric string and color is missing", () => {
    const feature: Feature = {
      type: "Feature",
      id: "feat-custom-lenient",
      name: "Fort",
      geometry: { type: "Point", coordinates: [-75, 52] },
      properties: {
        name: "Fort",
        customLabelStyle: {
          id: "style-lenient",
          name: "Fort",
          sizePx: "16" as unknown as number,
          fontStyle: "italic",
          textTransform: "uppercase",
          priority: 40,
          minZoom: 1,
        },
      },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      projectId: "",
    };

    const presentation = getLabelPresentation(feature);
    expect(presentation.isCustom).toBe(true);
    expect(presentation.sizePx).toBe(16);
    expect(presentation.fontStyle).toBe("italic");
    expect(presentation.color).toBe("#000000");
    expect(presentation.formattedText).toBe("FORT");
  });

  it("uses taxonomy as the sole source for label style despite stale feature properties", () => {
    const feature: Feature = {
      type: "Feature",
      id: "feat-stale-style",
      name: "montreal",
      geometry: { type: "Point", coordinates: [-73.5, 45.5] },
      properties: {
        name: "montreal",
        rawType: "city",
        mapElementType: "label",
        sizePx: 99,
        fontStyle: "uppercase italic",
      },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      projectId: "",
    };

    const presentation = getLabelPresentation(feature);
    expect(presentation.mapElementType).toBe("point");
    expect(presentation.sizePx).toBe(12);
    expect(presentation.fontStyle).toBe("normal");
    expect(presentation.textTransform).toBe("none");
    expect(presentation.formattedText).toBe("Montreal");
  });

  it("prepareFeatureForEdit and coerceEditedFeature handle form roundtrips", () => {
    const feature: Feature = {
      type: "Feature",
      id: "feat-edit",
      name: "montreal",
      geometry: { type: "Point", coordinates: [-73.5, 45.5] },
      properties: { name: "montreal", rawType: "city", mapElementType: "point", colorRgb: [0, 0, 0] },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      projectId: ""
    };

    const state = prepareFeatureForEdit(feature);
    expect(state.draft.name).toBe("montreal");
    expect(state.draft.wordType).toBe("city");

    const updated = coerceEditedFeature(feature, {
      name: "MONTREAL",
      wordType: "province",
      colorHex: "#ff0000",
    });

    expect(updated.properties.rawType).toBe("province");
    expect(updated.properties.mapElementType).toBe("label");
    expect(updated.properties.sizePx).toBe(14);
    expect(updated.properties.fontStyle).toBe("uppercase");
    expect(updated.properties.labelText).toBe("MONTREAL");
    expect(updated.properties.colorRgb).toEqual([255, 0, 0]);
  });

  it("uses taxonomy to resolve conflicting persisted map element types", () => {
    const cityWithStaleLabelType = {
      geometry: { type: "Point", coordinates: [0, 0] },
      properties: {
        rawType: "city",
        mapElementType: "label",
        labelText: "Montréal",
      },
    } as Feature;
    const provinceWithStalePointType = {
      geometry: { type: "Point", coordinates: [0, 0] },
      properties: {
        rawType: "province",
        mapElementType: "point",
        labelText: "Québec",
      },
    } as Feature;

    expect(getMapElementType(cityWithStaleLabelType)).toBe("point");
    expect(getMapElementType(provinceWithStalePointType)).toBe("label");
  });

  it("applies textColorRgb directly in styleAttribute and colorCss in getLabelPresentation", () => {
    const feature: Feature = {
      type: "Feature",
      id: "feat-custom-color",
      name: "ÉTATS-UNIS",
      geometry: { type: "Point", coordinates: [-95.7, 37.0] },
      properties: {
        name: "ÉTATS-UNIS",
        rawType: "country",
        mapElementType: "label",
        textColorRgb: [0, 255, 136],
      },
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      projectId: "",
    };

    const presentation = getLabelPresentation(feature);
    expect(presentation.colorCss).toBe("rgb(0, 255, 136)");
    expect(presentation.styleAttribute).toContain("color: rgb(0, 255, 136)");
  });

  it("ensures getWordTypeOptionStyle and getCustomStyleObject define explicit text colors", () => {
    const cityOptionStyle = getWordTypeOptionStyle("city");
    expect(cityOptionStyle.color).toBe("#000000");

    const riverOptionStyle = getWordTypeOptionStyle("river");
    expect(riverOptionStyle.color).toBe("#000000");

    const customWithColor: CustomLabelStyle = {
      id: "c-1",
      name: "Fort",
      sizePx: 14,
      fontStyle: "normal",
      textTransform: "none",
      color: "#10b981",
      priority: 50,
      minZoom: 1,
    };
    expect(getCustomStyleObject(customWithColor).color).toBe("#10b981");

    const customWithoutColor: CustomLabelStyle = {
      id: "c-2",
      name: "Sans couleur",
      sizePx: 14,
      fontStyle: "normal",
      textTransform: "none",
      priority: 50,
      minZoom: 1,
    };
    expect(getCustomStyleObject(customWithoutColor).color).toBe("#000000");

    const customWithPoint: CustomLabelStyle = {
      ...customWithColor,
      id: "c-point",
      hasPoint: true,
      pointColor: "#dc2626",
    };
    expect(getCustomStyleObject(customWithPoint).color).toBe("#10b981");
  });

  it("rejects non-hex fill/stroke and clamps opacities in the map point SVG", () => {
    const svg = mapPointSwatchSvg({
      fill: '#00ff00" onclick="alert(1)',
      stroke: "red",
      fillOpacity: 4,
      strokeOpacity: Number.NaN,
    });
    expect(svg).toContain('fill="#000000"');
    expect(svg).toContain('stroke="#000000"');
    expect(svg).toContain('fill-opacity="1"');
    expect(svg).toContain('stroke-opacity="1"');
    expect(svg).not.toContain("onclick");
  });
});
