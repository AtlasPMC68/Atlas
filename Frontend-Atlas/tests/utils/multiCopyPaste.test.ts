import { describe, it, expect } from "vitest";
import { cloneFeatureWithOffset } from "../../src/utils/featureHelpers";
import type { Feature } from "../../src/typescript/feature";

describe("Multi-element copy and offset paste", () => {
  const feat1: Feature = {
    type: "Feature",
    id: "uuid-1",
    name: "Zone Nord",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [10, 20],
          [15, 20],
          [15, 25],
          [10, 20],
        ],
      ],
    },
    properties: { mapElementType: "zone" },
  };

  const feat2: Feature = {
    type: "Feature",
    id: "uuid-2",
    name: "Ville Sud",
    geometry: {
      type: "Point",
      coordinates: [12, 18],
    },
    properties: { mapElementType: "point", labelText: "Ville Sud" },
  };

  it("duplicates all selected features with an offset and unique IDs", () => {
    const selectedFeatures = [feat1, feat2];
    const deltaLng = 0.5;
    const deltaLat = -0.5;

    const duplicated = selectedFeatures.map((f) =>
      cloneFeatureWithOffset(f, deltaLng, deltaLat)
    );

    expect(duplicated).toHaveLength(2);
    expect(duplicated[0].id).not.toBe(feat1.id);
    expect(duplicated[1].id).not.toBe(feat2.id);

    // Verify point geometry offset
    expect(duplicated[1].geometry.coordinates).toEqual([12.5, 17.5]);

    // Verify polygon coordinates offset
    const polyCoords = (duplicated[0].geometry as any).coordinates[0];
    expect(polyCoords[0]).toEqual([10.5, 19.5]);
    expect(polyCoords[1]).toEqual([15.5, 19.5]);
  });
});
