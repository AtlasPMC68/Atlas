import { describe, it, expect } from "vitest";

import type { Feature } from "../../src/typescript/feature";
import {
  featureToValidationEntry,
  applyValidationToFeature,
  isUnrecognizedTextFeature,
  ValidationStatus,
  type TextValidationEntry,
} from "../../src/utils/textValidation";
import { prepareFeaturesForSave, camelToSnake, snakeToCamel } from "../../src/utils/utils";

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

    it("returns true for rejected features so they can be re-examined unless deleted", () => {
      const rejected: Feature = {
        ...baseFeature,
        properties: {
          ...baseFeature.properties,
          recognized: false,
          show: false,
          validationStatus: "rejected",
        },
      };
      expect(isUnrecognizedTextFeature(rejected, "map-1")).toBe(true);
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
      expect(isUnrecognizedTextFeature(result)).toBe(true);
    });

    it("persists accepted status with show=true, recognized=true and validationStatus='accepted'", () => {
      const entry: TextValidationEntry = {
        id: "feat-1",
        text: "Québec Confirmé",
        originalText: "Québec",
        selected: true,
      };

      const result = applyValidationToFeature(baseFeature, entry);
      expect(result.name).toBe("Québec Confirmé");
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
      expect(isUnrecognizedTextFeature(validated)).toBe(true);
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

  describe("OCR validation end-to-end integration flow", () => {
    it("manages the complete lifecycle: recognized city, manual review, user accepted, and user rejected", () => {
      // 1. Initial features as returned after OCR and backend extraction:
      // - Feature 1: City recognized automatically (Québec)
      // - Feature 2: Unrecognized text pending manual review (Légende)
      // - Feature 3: Unrecognized text that user will validate & keep (Chicoutimi)
      // - Feature 4: Unrecognized text that user will explicitly reject (Échelle 1:10000)
      const initialFeatures: Feature[] = [
        {
          type: "Feature",
          id: "city-1",
          projectId: "proj-1",
          mapId: "map-1",
          name: "Québec",
          createdAt: "2026-01-01",
          updatedAt: "2026-01-01",
          geometry: { type: "Point", coordinates: [-71.208, 46.8139] },
          properties: {
            name: "Québec",
            mapElementType: "point",
            isOcrText: true,
            recognized: true,
            show: true,
            validationStatus: "accepted",
          },
        },
        {
          type: "Feature",
          id: "text-pending",
          projectId: "proj-1",
          mapId: "map-1",
          name: "Légende",
          createdAt: "2026-01-01",
          updatedAt: "2026-01-01",
          geometry: { type: "Point", coordinates: [-71.3, 46.9] },
          properties: {
            name: "Légende",
            mapElementType: "point",
            isOcrText: true,
            recognized: false,
            show: false,
            validationStatus: "manual_review",
          },
        },
        {
          type: "Feature",
          id: "text-to-accept",
          projectId: "proj-1",
          mapId: "map-1",
          name: "Chicoutmi",
          createdAt: "2026-01-01",
          updatedAt: "2026-01-01",
          geometry: { type: "Point", coordinates: [-71.05, 48.42] },
          properties: {
            name: "Chicoutmi",
            mapElementType: "point",
            isOcrText: true,
            recognized: false,
            show: false,
            validationStatus: "manual_review",
            suggestedCity: "Chicoutimi",
            suggestedCoords: [-71.06, 48.43],
          },
        },
        {
          type: "Feature",
          id: "text-to-reject",
          projectId: "proj-1",
          mapId: "map-1",
          name: "Échelle 1:10000",
          createdAt: "2026-01-01",
          updatedAt: "2026-01-01",
          geometry: { type: "Point", coordinates: [-71.1, 46.7] },
          properties: {
            name: "Échelle 1:10000",
            mapElementType: "point",
            isOcrText: true,
            recognized: false,
            show: false,
            validationStatus: "manual_review",
          },
        },
      ];

      // 2. Identify candidates for validation modal
      // city-1 (accepted) MUST NOT be in the modal
      expect(isUnrecognizedTextFeature(initialFeatures[0])).toBe(false);
      // All manual_review features MUST be in the modal
      expect(isUnrecognizedTextFeature(initialFeatures[1])).toBe(true);
      expect(isUnrecognizedTextFeature(initialFeatures[2])).toBe(true);
      expect(isUnrecognizedTextFeature(initialFeatures[3])).toBe(true);

      // Convert candidates into modal validation entries
      const modalEntries = [initialFeatures[1], initialFeatures[2], initialFeatures[3]].map((f) =>
        featureToValidationEntry(f, true),
      );

      // 3. User interaction simulation:
      // - text-pending is left untouched in manual_review
      // - text-to-accept is accepted by user (adopted suggestion)
      // - text-to-reject is explicitly rejected (selected = false)
      const userValidatedEntries: TextValidationEntry[] = [
        {
          ...modalEntries[1], // text-to-accept
          text: "Chicoutimi",
          selected: true,
          useSuggestedCity: true,
        },
        {
          ...modalEntries[2], // text-to-reject
          selected: false,
        },
      ];

      // 4. Apply validation to features
      const entriesMap = new Map(userValidatedEntries.map((e) => [e.id, e]));
      const updatedFeatures = initialFeatures.map((f) => {
        const entry = entriesMap.get(f.id);
        return entry ? applyValidationToFeature(f, entry) : f;
      });

      // Assert post-validation states:
      const rec = updatedFeatures.find((f) => f.id === "city-1")!;
      const pending = updatedFeatures.find((f) => f.id === "text-pending")!;
      const accepted = updatedFeatures.find((f) => f.id === "text-to-accept")!;
      const rejected = updatedFeatures.find((f) => f.id === "text-to-reject")!;

      // Case 1: Recognized positive city
      expect(rec.properties.validationStatus).toBe("accepted");
      expect(rec.properties.recognized).toBe(true);
      expect(rec.properties.show).toBe(true);

      // Case 2: Unrecognized invalid label in manual review
      expect(pending.properties.validationStatus).toBe("manual_review");
      expect(pending.properties.recognized).toBe(false);
      expect(pending.properties.show).toBe(false);

      // Case 3: Unrecognized text validated & kept
      expect(accepted.properties.validationStatus).toBe("accepted");
      expect(accepted.properties.recognized).toBe(true);
      expect(accepted.properties.show).toBe(true);
      expect(accepted.name).toBe("Chicoutimi");
      expect(accepted.geometry.coordinates).toEqual([-71.06, 48.43]);

      // Case 4: Text explicitly rejected by user
      expect(rejected.properties.validationStatus).toBe("rejected");
      expect(rejected.properties.recognized).toBe(false);
      expect(rejected.properties.show).toBe(false);

      // 5. Verify persistence payload sent to backend via PUT /projects/:id/features
      const featuresToPersist = [accepted, rejected];
      const payload = camelToSnake(prepareFeaturesForSave(featuresToPersist)) as Array<Record<string, any>>;

      expect(payload).toHaveLength(2);
      expect(payload[0].properties.validation_status).toBe("accepted");
      expect(payload[0].properties.show).toBe(true);
      expect(payload[0].properties.recognized).toBe(true);
      expect(payload[0].created_at).toBeUndefined(); // stripped by prepareFeaturesForSave

      expect(payload[1].properties.validation_status).toBe("rejected");
      expect(payload[1].properties.show).toBe(false);
      expect(payload[1].properties.recognized).toBe(false);

      // 6. Verify subsequent reload: rejected items remain in modal until deleted, while accepted do not
      expect(isUnrecognizedTextFeature(rec)).toBe(false);
      expect(isUnrecognizedTextFeature(accepted)).toBe(false);
      expect(isUnrecognizedTextFeature(rejected)).toBe(true);
      expect(isUnrecognizedTextFeature(pending)).toBe(true);
    });

    it("verifies exact API payload serialization and ensures validated features do not return to manual_review on reload", () => {
      // Feature as produced by OCR extraction tasks (contains both snake_case and camelCase keys)
      const ocrExtractedFeature: Feature = {
        type: "Feature",
        id: "feat-ocr-42",
        projectId: "proj-123",
        mapId: "map-456",
        name: "Trois-Rivires",
        createdAt: "2026-03-01T10:00:00Z",
        updatedAt: "2026-03-01T10:00:00Z",
        geometry: {
          type: "Point",
          coordinates: [-72.54, 46.34],
        },
        properties: {
          name: "Trois-Rivires",
          originalText: "Trois-Rivires",
          mapElementType: "point",
          colorName: "black",
          colorRgb: [0, 0, 0],
          isOcrText: true,
          recognized: false,
          show: false,
          validationStatus: "manual_review",
          validation_status: "manual_review",
          confidence: 0.72,
          suggestedCity: "Trois-Rivières",
          suggestedCoords: [-72.55, 46.35],
        },
      };

      // 1. Initial state: correctly recognized as needing manual review
      expect(isUnrecognizedTextFeature(ocrExtractedFeature)).toBe(true);

      // 2. Open modal and convert to TextValidationEntry
      const modalEntry = featureToValidationEntry(ocrExtractedFeature, true);
      expect(modalEntry.validationStatus).toBe("manual_review");
      expect(modalEntry.text).toBe("Trois-Rivires");

      // 3. User accepts suggestion: updates text to "Trois-Rivières", selected = true, useSuggestedCity = true
      const userChoice: TextValidationEntry = {
        ...modalEntry,
        text: "Trois-Rivières",
        selected: true,
        useSuggestedCity: true,
      };

      // 4. Apply validation to feature
      const validatedFeature = applyValidationToFeature(ocrExtractedFeature, userChoice);

      expect(validatedFeature.name).toBe("Trois-Rivières");
      expect(validatedFeature.properties.validationStatus).toBe("accepted");
      expect(validatedFeature.properties.validation_status).toBe("accepted");
      expect(validatedFeature.properties.show).toBe(true);
      expect(validatedFeature.properties.recognized).toBe(true);
      expect(validatedFeature.geometry.coordinates).toEqual([-72.55, 46.35]);

      // 5. Exact Map.vue serialization flow: prepareFeaturesForSave -> camelToSnake
      const prepared = prepareFeaturesForSave([validatedFeature]);
      const exactPayload = camelToSnake(prepared) as Array<Record<string, any>>;

      // Exact API payload assertions
      expect(exactPayload).toHaveLength(1);
      const apiItem = exactPayload[0];
      expect(apiItem.id).toBe("feat-ocr-42");
      expect(apiItem.project_id).toBe("proj-123");
      expect(apiItem.name).toBe("Trois-Rivières");
      expect(apiItem.created_at).toBeUndefined(); // stripped for API PUT
      expect(apiItem.updated_at).toBeUndefined();

      // Properties in exact API payload:
      expect(apiItem.properties.validation_status).toBe("accepted");
      expect(apiItem.properties.show).toBe(true);
      expect(apiItem.properties.recognized).toBe(true);
      expect(apiItem.properties.is_ocr_text).toBe(true);

      // 6. Simulate API round-trip: JSON stringify -> backend response -> snakeToCamel in loadInitialFeatures()
      const rawApiResponse = JSON.parse(JSON.stringify(exactPayload));
      const reloadedFeatures = snakeToCamel(rawApiResponse) as Feature[];
      const reloadedFeature = reloadedFeatures[0];

      // 7. Verify reloaded feature properties and state
      expect(reloadedFeature.properties.validationStatus).toBe("accepted");
      expect(reloadedFeature.properties.show).toBe(true);
      expect(reloadedFeature.properties.recognized).toBe(true);

      // 8. Crucial check: MUST NOT revert to manual_review or reappear in modal
      expect(isUnrecognizedTextFeature(reloadedFeature)).toBe(false);
    });

    it("handles legacy/mixed features where only validation_status or only validationStatus exists", () => {
      const featureWithSnakeOnly: Feature = {
        type: "Feature",
        id: "feat-snake-1",
        projectId: "p1",
        geometry: { type: "Point", coordinates: [0, 0] },
        createdAt: "2026-01-01",
        updatedAt: "2026-01-01",
        name: "Item",
        properties: {
          name: "Item",
          isOcrText: true,
          recognized: false,
          show: false,
          validation_status: "manual_review",
          mapElementType: "point"
        },
      };

      expect(isUnrecognizedTextFeature(featureWithSnakeOnly)).toBe(true);
      const entry = featureToValidationEntry(featureWithSnakeOnly, true);
      expect(entry.validationStatus).toBe("manual_review");

      // Validate as accepted
      const validated = applyValidationToFeature(featureWithSnakeOnly, { ...entry, selected: true });
      expect(validated.properties.validationStatus).toBe("accepted");
      expect(validated.properties.validation_status).toBe("accepted");

      const payload = camelToSnake(prepareFeaturesForSave([validated])) as Array<Record<string, any>>;
      expect(payload[0].properties.validation_status).toBe("accepted");
      expect(payload[0].properties.show).toBe(true);
      expect(payload[0].properties.recognized).toBe(true);

      const reloaded = (snakeToCamel(payload) as Feature[])[0];
      expect(isUnrecognizedTextFeature(reloaded)).toBe(false);
    });

    it("supports ValidationStatus enum members directly in feature properties and comparisons", () => {
      expect(ValidationStatus.ACCEPTED).toBe("accepted");
      expect(ValidationStatus.REJECTED).toBe("rejected");
      expect(ValidationStatus.MANUAL_REVIEW).toBe("manual_review");

      const featureWithEnum: Feature = {
        type: "Feature",
        id: "feat-enum-1",
        projectId: "p1",
        geometry: { type: "Point", coordinates: [0, 0] },
        createdAt: "2026-01-01",
        updatedAt: "2026-01-01",
        name: "EnumItem",
        properties: {
          name: "EnumItem",
          isOcrText: true,
          recognized: false,
          show: false,
          validationStatus: ValidationStatus.MANUAL_REVIEW,
          validation_status: ValidationStatus.MANUAL_REVIEW,
          mapElementType: "point"
        },
      };

      expect(isUnrecognizedTextFeature(featureWithEnum)).toBe(true);

      const entry = featureToValidationEntry(featureWithEnum, true);
      expect(entry.validationStatus).toBe(ValidationStatus.MANUAL_REVIEW);

      const validated = applyValidationToFeature(featureWithEnum, {
        ...entry,
        selected: true,
      });
      expect(validated.properties.validationStatus).toBe(ValidationStatus.ACCEPTED);
      expect(validated.properties.validation_status).toBe(ValidationStatus.ACCEPTED);
      expect(validated.properties.show).toBe(true);
      expect(validated.properties.recognized).toBe(true);
    });

    it("applies validation state, selected word style, and coordinates in one operation", () => {
      const rawFeature: Feature = {
        type: "Feature",
        id: "feat-pure-state",
        name: "Test Place",
        geometry: { type: "Point", coordinates: [-70, 45] },
        properties: {
          name: "Test Place",
          sizePx: 14,
          fontStyle: "uppercase",
          mapElementType: "label",
        },
        createdAt: "2026-01-01",
        updatedAt: "2026-01-01",
      };

      const accepted = applyValidationToFeature(rawFeature, {
        id: rawFeature.id,
        text: "Test Place",
        originalText: "Test Place",
        selected: true,
        wordType: "province",
        coordinates: [-71, 46],
      });
      expect(accepted.properties.show).toBe(true);
      expect(accepted.properties.recognized).toBe(true);
      expect(accepted.properties.validationStatus).toBe(ValidationStatus.ACCEPTED);
      expect(accepted.geometry.coordinates).toEqual([-71, 46]);
      expect(accepted.properties.rawType).toBe("province");
      expect(accepted.properties.mapElementType).toBe("label");
      expect(accepted.properties.sizePx).toBe(14);
      expect(accepted.properties.fontStyle).toBe("uppercase");

      const rejected = applyValidationToFeature(rawFeature, {
        id: rawFeature.id,
        text: "Test Place",
        originalText: "Test Place",
        selected: false,
        wordType: "city",
      });
      expect(rejected.properties.show).toBe(false);
      expect(rejected.properties.recognized).toBe(false);
      expect(rejected.properties.validationStatus).toBe(ValidationStatus.REJECTED);
    });
  });
});
