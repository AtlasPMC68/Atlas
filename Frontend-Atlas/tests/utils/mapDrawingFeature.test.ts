import { describe, it, expect } from "vitest";
import L from "leaflet";
import { circleToPolygon, layerToFeature } from "../../src/utils/mapDrawingFeature";

describe("mapDrawingFeature - circleToPolygon", () => {
  it("converts a circle into a closed polygon ring with the specified steps", () => {
    const center = L.latLng(45.0, 10.0);
    const radiusMeters = 50000;
    const poly = circleToPolygon(center, radiusMeters, 64);

    expect(poly.type).toBe("Polygon");
    expect(poly.coordinates[0].length).toBe(65); // 64 steps + closing point
    expect(poly.coordinates[0][0]).toEqual(poly.coordinates[0][64]);
  });

  it("produces a visually conformal circle on Web Mercator (equal projected width and height)", () => {
    const center = L.latLng(50.0, 2.0); // France / Europe
    const radiusMeters = 100000;
    const poly = circleToPolygon(center, radiusMeters, 128);

    const ring = poly.coordinates[0];
    const R = 6378137;

    // Convert ring points to projected Mercator meters (EPSG:3857)
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;

    for (const [lng, lat] of ring) {
      const x = (lng * Math.PI * R) / 180;
      const latRad = (lat * Math.PI) / 180;
      const y = R * Math.log(Math.tan(Math.PI / 4 + latRad / 2));

      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
    }

    const projectedWidth = maxX - minX;
    const projectedHeight = maxY - minY;

    // Width and height in Mercator projection space must be equal (true circle)
    expect(projectedWidth / projectedHeight).toBeCloseTo(1.0, 2);
  });

  it("assigns shapeKind: 'circle' in layerToFeature when layer is an L.Circle", () => {
    const circle = L.circle([46.8, -71.2], { radius: 1500 });
    const feature = layerToFeature(circle, 1608, "project-123");

    expect(feature).not.toBeNull();
    expect(feature?.properties.mapElementType).toBe("shape");
    expect(feature?.properties.shapeKind).toBe("circle");
    expect(feature?.geometry.type).toBe("Polygon");
  });
});
