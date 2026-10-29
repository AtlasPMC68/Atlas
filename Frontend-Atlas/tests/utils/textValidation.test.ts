import { describe, it, expect } from "vitest";
import type { Feature } from "../../src/typescript/feature";
import {
  featureToValidationEntry,
  applyValidationToFeature,
  isUnrecognizedTextFeature,
} from "../../src/utils/textValidation";

describe("textValidation utils", () => {
  it("defaults unrecognized OCR features to selected: true (show by default)", () => {
    const rawOcrFeature: Feature = {
      id: "feat-ocr-1",
      mapId: "map-1",
      name: "QUEBEC",
      geometry: { type: "Point", coordinates: [-71.2, 46.8] },
      properties: {
        isOcrText: true,
        recognized: false,
        show: false,
      },
    };

    const entry = featureToValidationEntry(rawOcrFeature);
    expect(entry.selected).toBe(true);
    expect(entry.text).toBe("QUEBEC");
    expect(entry.wordType).toBe("city");
  });

  it("recognizes existing rawType or label element type when converting feature", () => {
    const provinceFeature: Feature = {
      id: "feat-prov-1",
      mapId: "map-1",
      name: "ONTARIO",
      geometry: { type: "Point", coordinates: [-79.3, 43.6] },
      properties: {
        isOcrText: true,
        recognized: false,
        show: false,
        rawType: "province",
        mapElementType: "label",
      },
    };

    const entry = featureToValidationEntry(provinceFeature);
    expect(entry.wordType).toBe("province");
  });

  it("applies selected=true validation with province word style", () => {
    const feature: Feature = {
      id: "feat-1",
      mapId: "map-1",
      name: "quebec",
      geometry: { type: "Point", coordinates: [-71.2, 46.8] },
      properties: {
        isOcrText: true,
        recognized: false,
        show: false,
      },
    };

    const validated = applyValidationToFeature(feature, {
      id: "feat-1",
      text: "quebec",
      originalText: "quebec",
      selected: true,
      wordType: "province",
      coordinates: [-71.2, 46.8],
    });

    expect(validated.name).toBe("QUEBEC");
    expect(validated.properties.name).toBe("QUEBEC");
    expect(validated.properties.labelText).toBe("QUEBEC");
    expect(validated.properties.recognized).toBe(true);
    expect(validated.properties.show).toBe(true);
    expect(validated.properties.userSelected).toBe(true);
    expect(validated.properties.mapElementType).toBe("label");
    expect(validated.properties.fontStyle).toBe("uppercase");
    expect(validated.properties.sizePx).toBe(14);
    expect(validated.properties.rawType).toBe("province");
    // Accepted texts are no longer unrecognized candidates
    expect(isUnrecognizedTextFeature(validated)).toBe(false);
  });

  it("applies selected=false validation keeping recognized: false so it is NOT listed in the page and remains in the unrecognized window", () => {
    const feature: Feature = {
      id: "feat-2",
      mapId: "map-1",
      name: "LOUISIANE",
      geometry: { type: "Point", coordinates: [-91.1, 30.4] },
      properties: {
        isOcrText: true,
        recognized: false,
        show: false,
      },
    };

    const validated = applyValidationToFeature(feature, {
      id: "feat-2",
      text: "LOUISIANE",
      originalText: "LOUISIANE",
      selected: false,
      wordType: "state",
      coordinates: [-91.1, 30.4],
    });

    // Unaccepted texts stay recognized: false and show: false (not listed in page, remains in validation modal)
    expect(validated.properties.recognized).toBe(false);
    expect(validated.properties.show).toBe(false);
    expect(validated.properties.userSelected).toBe(false);
    expect(validated.properties.name).toBe("LOUISIANE");
    expect(validated.properties.mapElementType).toBe("label");
    expect(validated.properties.rawType).toBe("state");
    expect(isUnrecognizedTextFeature(validated)).toBe(true);
  });

  it("converts uppercase text to capitalized when choosing city word type", () => {
    const feature: Feature = {
      id: "feat-3",
      mapId: "map-1",
      name: "SASKATCHEWAN",
      geometry: { type: "Point", coordinates: [-106.6, 52.1] },
      properties: {
        isOcrText: true,
        recognized: false,
        show: false,
      },
    };

    const validated = applyValidationToFeature(feature, {
      id: "feat-3",
      text: "SASKATCHEWAN",
      originalText: "SASKATCHEWAN",
      selected: true,
      wordType: "city",
      coordinates: [-106.6, 52.1],
    });

    expect(validated.name).toBe("Saskatchewan");
    expect(validated.properties.name).toBe("Saskatchewan");
    expect(validated.properties.mapElementType).toBe("point");
    expect(validated.properties.fontStyle).toBe("normal");
    expect(validated.properties.sizePx).toBe(12);
  });
});
