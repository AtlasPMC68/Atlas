import { describe, it, expect } from "vitest";
import {
  isCopyableFeature,
  getGeometryAnchor,
  offsetGeometry,
  cloneFeatureWithOffset,
  hasFeatureCustomDate,
  getFeatureMapId,
  getFeatureMapIds,
} from "../../src/utils/featureHelpers";
import type { Feature } from "../../src/typescript/feature";

describe("featureHelpers - copy / paste functionality", () => {
  const textFeature: Feature = {
    type: "Feature",
    id: "text-1",
    projectId: "p1",
    name: "Québec",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    geometry: { type: "Point", coordinates: [-71.2, 46.8] },
    properties: {
      name: "Québec",
      labelText: "Québec",
      mapElementType: "label",
    },
  };

  const zoneFeature: Feature = {
    type: "Feature",
    id: "zone-1",
    projectId: "p1",
    name: "Zone 1",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [-71.0, 46.0],
          [-70.0, 46.0],
          [-70.0, 47.0],
          [-71.0, 47.0],
          [-71.0, 46.0],
        ],
      ],
    },
    properties: {
      name: "Zone 1",
      mapElementType: "zone",
      colorRgb: [255, 0, 0],
    },
  };

  const lineFeature: Feature = {
    type: "Feature",
    id: "line-1",
    projectId: "p1",
    name: "Ligne 1",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    geometry: {
      type: "LineString",
      coordinates: [
        [-71.5, 46.5],
        [-70.5, 47.5],
      ],
    },
    properties: {
      name: "Ligne 1",
      mapElementType: "polyline",
    },
  };

  const imageFeature: Feature = {
    type: "Feature",
    id: "img-1",
    projectId: "p1",
    name: "carte.png",
    image: "data:image/png;base64,abc",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    geometry: { type: "Point", coordinates: [-71.0, 46.5] },
    properties: {
      name: "carte.png",
      mapElementType: "image",
      bounds: [
        [46.0, -72.0],
        [47.0, -70.0],
      ],
    },
  };

  describe("isCopyableFeature", () => {
    it("returns true for point, zone, line, and image features", () => {
      expect(isCopyableFeature(textFeature)).toBe(true);
      expect(isCopyableFeature(zoneFeature)).toBe(true);
      expect(isCopyableFeature(lineFeature)).toBe(true);
      expect(isCopyableFeature(imageFeature)).toBe(true);
    });

    it("returns false for null, undefined, or missing geometry", () => {
      expect(isCopyableFeature(null)).toBe(false);
      expect(isCopyableFeature(undefined)).toBe(false);
      expect(isCopyableFeature({} as unknown as Feature)).toBe(false);
      expect(isCopyableFeature({ properties: {} } as unknown as Feature)).toBe(false);
    });

    it("returns false for legend features", () => {
      const legendMapElem: Feature = {
        ...textFeature,
        properties: { ...textFeature.properties, mapElementType: "legend" as any },
      };
      const legendType: Feature = {
        ...textFeature,
        properties: { ...textFeature.properties, type: "legend" },
      };
      const legendFlag: Feature = {
        ...textFeature,
        properties: { ...textFeature.properties, isLegend: true },
      };

      expect(isCopyableFeature(legendMapElem)).toBe(false);
      expect(isCopyableFeature(legendType)).toBe(false);
      expect(isCopyableFeature(legendFlag)).toBe(false);
    });
  });

  describe("getGeometryAnchor", () => {
    it("returns reference point for Point", () => {
      expect(getGeometryAnchor(textFeature.geometry)).toEqual([-71.2, 46.8]);
    });

    it("returns first coordinate for LineString", () => {
      expect(getGeometryAnchor(lineFeature.geometry)).toEqual([-71.5, 46.5]);
    });

    it("returns first ring first vertex for Polygon", () => {
      expect(getGeometryAnchor(zoneFeature.geometry)).toEqual([-71.0, 46.0]);
    });
  });

  describe("offsetGeometry", () => {
    it("translates Point coordinates", () => {
      const result = offsetGeometry(textFeature.geometry, 0.5, 1.0);
      expect(result.type).toBe("Point");
      if (result.type === "Point") {
        expect(result.coordinates[0]).toBeCloseTo(-70.7);
        expect(result.coordinates[1]).toBeCloseTo(47.8);
      }
    });

    it("translates Polygon coordinates", () => {
      const result = offsetGeometry(zoneFeature.geometry, 0.5, 1.0);
      expect(result.type).toBe("Polygon");
      if (result.type === "Polygon") {
        expect(result.coordinates[0][0][0]).toBeCloseTo(-70.5);
        expect(result.coordinates[0][0][1]).toBeCloseTo(47.0);
      }
    });

    it("translates LineString coordinates", () => {
      const result = offsetGeometry(lineFeature.geometry, 0.5, 1.0);
      expect(result.type).toBe("LineString");
      if (result.type === "LineString") {
        expect(result.coordinates[0][0]).toBeCloseTo(-71.0);
        expect(result.coordinates[0][1]).toBeCloseTo(47.5);
        expect(result.coordinates[1][0]).toBeCloseTo(-70.0);
        expect(result.coordinates[1][1]).toBeCloseTo(48.5);
      }
    });
  });

  describe("cloneFeatureWithOffset", () => {
    it("creates a new feature with new ID, empty name, no custom dates, and translated geometry", () => {
      const newId = "new-uuid-999";
      const now = "2026-05-01T12:00:00Z";
      const sourceWithDates: Feature = {
        ...zoneFeature,
        properties: {
          ...zoneFeature.properties,
          startYear: 1608,
          endYear: 1650,
          startDate: "1608-01-01",
          endDate: "1650-12-31",
          exactDate: true,
        },
      };
      const clone = cloneFeatureWithOffset(sourceWithDates, 0.5, 1.0, newId, now);

      expect(clone.id).toBe(newId);
      expect(clone.createdAt).toBe(now);
      expect(clone.updatedAt).toBe(now);
      // No default name
      expect(clone.name).toBe("");
      expect(clone.properties.name).toBe("");
      // Preserves element type
      expect(clone.properties.mapElementType).toBe("zone");
      // Preserves styles
      expect(clone.properties.colorRgb).toEqual([255, 0, 0]);
      // No associated map
      expect(clone.mapId).toBeNull();
      expect(clone.properties.mapId).toBeNull();
      // No custom dates
      expect(clone.properties.startYear).toBeNull();
      expect(clone.properties.endYear).toBeNull();
      expect(clone.properties.startDate).toBeNull();
      expect(clone.properties.endDate).toBeNull();
      expect(clone.properties.exactDate).toBe(false);

      if (clone.geometry.type === "Polygon") {
        expect(clone.geometry.coordinates[0][0][0]).toBeCloseTo(-70.5);
        expect(clone.geometry.coordinates[0][0][1]).toBeCloseTo(47.0);
      }
    });

    it("translates properties.bounds for image features while preserving image type and clearing mapId", () => {
      const clone = cloneFeatureWithOffset(imageFeature, 0.5, 1.0, "new-img", "2026-05-01T12:00:00Z");

      expect(clone.image).toBe("data:image/png;base64,abc");
      expect(clone.properties.mapElementType).toBe("image");
      expect(clone.mapId).toBeNull();
      expect(clone.name).toBe("");
      expect(clone.properties.bounds).toBeDefined();
      const bounds = clone.properties.bounds!;
      // south, west
      expect(bounds[0][0]).toBeCloseTo(47.0); // 46.0 + 1.0
      expect(bounds[0][1]).toBeCloseTo(-71.5); // -72.0 + 0.5
      // north, east
      expect(bounds[1][0]).toBeCloseTo(48.0); // 47.0 + 1.0
      expect(bounds[1][1]).toBeCloseTo(-69.5); // -70.0 + 0.5
    });

    it("preserves label/text element type with empty labelText and mapId null", () => {
      const textFeature: Feature = {
        id: "text-1",
        type: "Feature",
        name: "Nouvelle-France",
        mapId: "map-123",
        geometry: {
          type: "Point",
          coordinates: [-71.2, 46.8],
        },
        properties: {
          name: "Nouvelle-France",
          labelText: "Nouvelle-France",
          mapElementType: "label",
          sizePx: 16,
          colorRgb: [0, 0, 0],
        },
      };

      const clonedText = cloneFeatureWithOffset(textFeature, 0.1, 0.1);
      expect(clonedText.name).toBe("Nouvelle-France");
      expect(clonedText.properties.name).toBe("Nouvelle-France");
      expect(clonedText.properties.labelText).toBe("Nouvelle-France");
      expect(clonedText.properties.mapElementType).toBe("label");
      expect(clonedText.properties.sizePx).toBe(16);
      expect(clonedText.mapId).toBeNull();
      expect(clonedText.properties.mapId).toBeNull();
    });

    it("assigns mapId: null to all cloned elements (zones, lines, shapes)", () => {
      const sourceZoneWithMap: Feature = {
        ...zoneFeature,
        mapId: "map-quebec-1900",
        properties: {
          ...zoneFeature.properties,
          mapId: "map-quebec-1900",
          mapTitle: "Québec",
        },
      };

      const clonedZone = cloneFeatureWithOffset(sourceZoneWithMap, 0.1, 0.1);
      expect(clonedZone.mapId).toBeNull();
      expect(clonedZone.properties.mapId).toBeNull();
      expect(clonedZone.properties.mapTitle).toBeUndefined();

      const sourceLineWithMap: Feature = {
        ...lineFeature,
        mapId: "map-quebec-1900",
      };
      const clonedLine = cloneFeatureWithOffset(sourceLineWithMap, 0.1, 0.1);
      expect(clonedLine.mapId).toBeNull();
      expect(clonedLine.properties.mapId).toBeNull();
      expect(clonedLine.properties.mapElementType).toBe("polyline");
    });
    it("clears mapIds array when source feature belongs to multiple maps", () => {
      const multiMapFeature: Feature = {
        ...zoneFeature,
        mapId: "map-1",
        mapIds: ["map-1", "map-2", "map-3"],
        properties: {
          ...zoneFeature.properties,
          mapId: "map-1",
          mapIds: ["map-1", "map-2", "map-3"],
        },
      };

      const cloned = cloneFeatureWithOffset(multiMapFeature, 0.1, 0.1);
      expect(cloned.mapId).toBeNull();
      expect(cloned.properties.mapId).toBeNull();
      expect(cloned.properties.mapIds).toEqual([]);
    });
  });

  describe("hasFeatureCustomDate, getFeatureMapId and getFeatureMapIds", () => {
    it("identifies custom date when startYear or endYear is present", () => {
      const feat: Feature = {
        ...textFeature,
        properties: {
          ...textFeature.properties,
          startYear: 1678,
          endYear: 1678,
          mapId: "carte-2",
        },
      };
      expect(hasFeatureCustomDate(feat)).toBe(true);
      expect(getFeatureMapId(feat)).toBe("carte-2");
      expect(getFeatureMapIds(feat)).toEqual(["carte-2"]);
    });

    it("identifies custom date when startDate or endDate string is present", () => {
      const feat: Feature = {
        ...zoneFeature,
        mapId: "carte-2",
        properties: {
          ...zoneFeature.properties,
          startDate: "1650-01-01",
          mapId: "carte-2",
          mapTitle: "Carte 2",
        },
      };
      expect(hasFeatureCustomDate(feat)).toBe(true);
      expect(getFeatureMapId(feat)).toBe("carte-2");
      expect(getFeatureMapIds(feat)).toEqual(["carte-2"]);
    });

    it("returns correct mapId and mapIds when feature has NO custom date", () => {
      const feat: Feature = {
        ...zoneFeature,
        mapId: "carte-1",
        mapIds: ["carte-1", "carte-2"],
        properties: {
          ...zoneFeature.properties,
          mapId: "carte-1",
          mapIds: ["carte-1", "carte-2"],
        },
      };
      expect(hasFeatureCustomDate(feat)).toBe(false);
      expect(getFeatureMapId(feat)).toBe("carte-1");
      expect(getFeatureMapIds(feat)).toEqual(["carte-1", "carte-2"]);
    });
  });
});
