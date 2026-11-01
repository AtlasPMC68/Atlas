import { describe, it, expect } from "vitest";
import {
  isUnrecognizedTextFeature,
  featureToValidationEntry,
  applyValidationToFeature,
  type TextValidationEntry,
} from "../../src/utils/textValidation";
import type { Feature } from "../../src/typescript/feature";
import { prepareFeaturesForSave, camelToSnake } from "../../src/utils/utils";

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
      expect(result.properties.validationStatus).toBe("rejected");
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
      expect(result.properties.validationStatus).toBe("accepted");
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

      // 6. Verify subsequent reload: rejected and accepted items never re-appear in modal
      expect(isUnrecognizedTextFeature(rec)).toBe(false);
      expect(isUnrecognizedTextFeature(accepted)).toBe(false);
      expect(isUnrecognizedTextFeature(rejected)).toBe(false);
      expect(isUnrecognizedTextFeature(pending)).toBe(true);
    });
  });
});

