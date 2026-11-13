import { describe, it, expect } from "vitest";
import {
  isCopyableFeature,
  getGeometryAnchor,
  offsetGeometry,
  cloneFeatureWithOffset,
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
    it("creates a new feature with new ID and translated geometry", () => {
      const newId = "new-uuid-999";
      const now = "2026-05-01T12:00:00Z";
      const clone = cloneFeatureWithOffset(zoneFeature, 0.5, 1.0, newId, now);

      expect(clone.id).toBe(newId);
      expect(clone.createdAt).toBe(now);
      expect(clone.updatedAt).toBe(now);
      expect(clone.name).toBe("Zone 1");
      expect(clone.properties.colorRgb).toEqual([255, 0, 0]);
      // Zones must always be added to general elements (mapId: null)
      expect(clone.mapId).toBeNull();
      expect(clone.properties.mapId).toBeNull();

      if (clone.geometry.type === "Polygon") {
        expect(clone.geometry.coordinates[0][0][0]).toBeCloseTo(-70.5);
        expect(clone.geometry.coordinates[0][0][1]).toBeCloseTo(47.0);
      }
    });

    it("translates properties.bounds for image features", () => {
      const clone = cloneFeatureWithOffset(imageFeature, 0.5, 1.0, "new-img", "2026-05-01T12:00:00Z");

      expect(clone.image).toBe("data:image/png;base64,abc");
      expect(clone.properties.bounds).toBeDefined();
      const bounds = clone.properties.bounds!;
      // south, west
      expect(bounds[0][0]).toBeCloseTo(47.0); // 46.0 + 1.0
      expect(bounds[0][1]).toBeCloseTo(-71.5); // -72.0 + 0.5
      // north, east
      expect(bounds[1][0]).toBeCloseTo(48.0); // 47.0 + 1.0
      expect(bounds[1][1]).toBeCloseTo(-69.5); // -70.0 + 0.5
    });

    it("assigns mapId: null to cloned zones to add them to general elements, while preserving mapId for others", () => {
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
      expect(clonedLine.mapId).toBe("map-quebec-1900");
    });
  });
});
