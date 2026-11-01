import { describe, it, expect } from "vitest";

import type { Feature } from "../../src/typescript/feature";
import {
  featureToValidationEntry,
  applyValidationToFeature,
  isUnrecognizedTextFeature,
  type TextValidationEntry,
} from "../../src/utils/textValidation";

describe("textValidation utility functions", () => {
  const baseFeature: Feature = {
    type: "Feature",
    id: "feat-1",
    projectId: "proj-1",
    mapId: "map-1",
    name: "Québec",
    createdAt: "2026-01-01",
    updatedAt: "2026-01-01",
    geometry: {
      type: "Point",
      coordinates: [-71.2, 46.8],
    },
    properties: {
      name: "Québec",
      mapElementType: "point",
      isOcrText: true,
      recognized: false,
      show: false,
      validationStatus: "manual_review",
    },
  };

  describe("isUnrecognizedTextFeature", () => {
    it("returns true for features needing manual review", () => {
      expect(isUnrecognizedTextFeature(baseFeature, "map-1")).toBe(true);
    });

    it("returns false for accepted features", () => {
      const accepted: Feature = {
        ...baseFeature,
        properties: {
          ...baseFeature.properties,
          recognized: true,
          show: true,
          validationStatus: "accepted",
        },
      };
      expect(isUnrecognizedTextFeature(accepted, "map-1")).toBe(false);
    });

    it("returns false for rejected features so they do not reappear after reload", () => {
      const rejected: Feature = {
        ...baseFeature,
        properties: {
          ...baseFeature.properties,
          recognized: false,
          show: false,
          validationStatus: "rejected",
        },
      };
      expect(isUnrecognizedTextFeature(rejected, "map-1")).toBe(false);
    });

    it("handles legacy features without explicit validationStatus", () => {
      const legacyUnrec: Feature = {
        ...baseFeature,
        properties: {
          ...baseFeature.properties,
          recognized: false,
          show: false,
          validationStatus: undefined,
        },
      };
      expect(isUnrecognizedTextFeature(legacyUnrec, "map-1")).toBe(true);
    });

    it("filters by mapId", () => {
      expect(isUnrecognizedTextFeature(baseFeature, "map-2")).toBe(false);
      expect(isUnrecognizedTextFeature(baseFeature, null)).toBe(true);
    });
  });

  describe("featureToValidationEntry", () => {
    it("converts a manual_review feature correctly", () => {
      const entry = featureToValidationEntry(baseFeature, true);
      expect(entry.id).toBe("feat-1");
      expect(entry.text).toBe("Québec");
      expect(entry.selected).toBe(true);
      expect(entry.validationStatus).toBe("manual_review");
    });

    it("defaults unrecognized OCR features to selected: true (show by default)", () => {
      const rawOcrFeature: Feature = {
        id: "feat-ocr-1",
        projectId: "proj-1",
        mapId: "map-1",
        type: "Feature",
        name: "QUEBEC",
        createdAt: "2026-01-01",
        updatedAt: "2026-01-01",
        geometry: { type: "Point", coordinates: [-71.2, 46.8] },
        properties: {
          name: "QUEBEC",
          mapElementType: "point",
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
        projectId: "proj-1",
        mapId: "map-1",
        type: "Feature",
        name: "ONTARIO",
        createdAt: "2026-01-01",
        updatedAt: "2026-01-01",
        geometry: { type: "Point", coordinates: [-79.3, 43.6] },
        properties: {
          name: "ONTARIO",
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

    it("preserves rejected status if already rejected", () => {
      const rejectedFeature: Feature = {
        ...baseFeature,
        properties: {
          ...baseFeature.properties,
          validationStatus: "rejected",
        },
      };
      const entry = featureToValidationEntry(rejectedFeature, true);
      expect(entry.selected).toBe(false);
      expect(entry.validationStatus).toBe("rejected");
    });

    it("preserves accepted status if already accepted", () => {
      const acceptedFeature: Feature = {
        ...baseFeature,
        properties: {
          ...baseFeature.properties,
          validationStatus: "accepted",
        },
      };
      const entry = featureToValidationEntry(acceptedFeature, false);
      expect(entry.selected).toBe(true);
      expect(entry.validationStatus).toBe("accepted");
    });
  });

  describe("applyValidationToFeature", () => {
    it("persists rejected status with show=false, recognized=false and validationStatus='rejected'", () => {
      const entry: TextValidationEntry = {
        id: "feat-1",
        text: "Bruit OCR",
        originalText: "Bruit OCR",
        selected: false,
      };

      const result = applyValidationToFeature(baseFeature, entry);
      expect(result.properties.show).toBe(false);
      expect(result.properties.recognized).toBe(false);
      expect(result.properties.userSelected).toBe(false);
      expect(result.properties.validationStatus).toBe("rejected");
      expect(isUnrecognizedTextFeature(result)).toBe(false);
    });

    it("persists accepted status with show=true, recognized=true and validationStatus='accepted'", () => {
      const entry: TextValidationEntry = {
        id: "feat-1",
        text: "Québec Confirmé",
        originalText: "Québec",
        selected: true,
      };

      const result = applyValidationToFeature(baseFeature, entry);
      expect(result.name).toBe("Québec confirmé");
      expect(result.properties.show).toBe(true);
      expect(result.properties.recognized).toBe(true);
      expect(result.properties.userSelected).toBe(true);
      expect(result.properties.validationStatus).toBe("accepted");
      expect(isUnrecognizedTextFeature(result)).toBe(false);
    });

    it("applies selected=true validation with province word style", () => {
      const feature: Feature = {
        id: "feat-1",
        projectId: "proj-1",
        mapId: "map-1",
        type: "Feature",
        name: "quebec",
        createdAt: "2026-01-01",
        updatedAt: "2026-01-01",
        geometry: { type: "Point", coordinates: [-71.2, 46.8] },
        properties: {
          name: "quebec",
          mapElementType: "point",
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
      expect(isUnrecognizedTextFeature(validated)).toBe(false);
    });

    it("applies selected=false validation with rejected status and word styles", () => {
      const feature: Feature = {
        id: "feat-2",
        projectId: "proj-1",
        mapId: "map-1",
        type: "Feature",
        name: "LOUISIANE",
        createdAt: "2026-01-01",
        updatedAt: "2026-01-01",
        geometry: { type: "Point", coordinates: [-91.1, 30.4] },
        properties: {
          name: "LOUISIANE",
          mapElementType: "point",
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

      expect(validated.properties.recognized).toBe(false);
      expect(validated.properties.show).toBe(false);
      expect(validated.properties.userSelected).toBe(false);
      expect(validated.properties.validationStatus).toBe("rejected");
      expect(validated.properties.name).toBe("LOUISIANE");
      expect(validated.properties.mapElementType).toBe("label");
      expect(validated.properties.rawType).toBe("state");
      expect(isUnrecognizedTextFeature(validated)).toBe(false);
    });

    it("converts uppercase text to capitalized when choosing city word type", () => {
      const feature: Feature = {
        id: "feat-3",
        projectId: "proj-1",
        mapId: "map-1",
        type: "Feature",
        name: "SASKATCHEWAN",
        createdAt: "2026-01-01",
        updatedAt: "2026-01-01",
        geometry: { type: "Point", coordinates: [-106.6, 52.1] },
        properties: {
          name: "SASKATCHEWAN",
          mapElementType: "point",
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

    it("applies suggestedCoords when useSuggestedCity is true", () => {
      const entry: TextValidationEntry = {
        id: "feat-1",
        text: "Montréal",
        originalText: "Montrel",
        selected: true,
        useSuggestedCity: true,
        suggestedCoords: [-73.5673, 45.5017],
      };

      const result = applyValidationToFeature(baseFeature, entry);
      expect(result.geometry.coordinates).toEqual([-73.5673, 45.5017]);
      expect(result.properties.show).toBe(true);
      expect(result.properties.recognized).toBe(true);
      expect(result.properties.userSelected).toBe(true);
      expect(result.properties.validationStatus).toBe("accepted");
    });
  });
});
