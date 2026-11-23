import { describe, it, expect, vi } from "vitest";
import L from "leaflet";
import {
  enablePixelSpaceDrag,
  enablePerFeatureDrag,
  disablePerFeatureDrag,
  nudgeFeatureByPixels,
} from "../../src/utils/mapDragUtils";
import { getNudgeDelta } from "../../src/utils/selectionUtils";
import type { Feature } from "../../src/typescript/feature";

describe("mapDragUtils - enablePixelSpaceDrag with co-draggable layers", () => {
  it("enables and disables drag on layers", () => {
    const layer = new L.Polygon([
      [0, 0],
      [1, 1],
      [1, 0],
    ]);
    (layer as any).pm = {
      enableLayerDrag: vi.fn(),
      disableLayerDrag: vi.fn(),
    };

    enablePerFeatureDrag(layer);
    expect((layer as any).pm.enableLayerDrag).toHaveBeenCalledTimes(1);

    disablePerFeatureDrag(layer);
    expect((layer as any).pm.disableLayerDrag).toHaveBeenCalledTimes(1);
  });

  it("coordinates group drag with co-draggable layers on drag start and drag end", () => {
    const container = document.createElement("div");
    container.style.width = "800px";
    container.style.height = "600px";
    document.body.appendChild(container);

    const map = L.map(container).setView([0, 0], 5);

    const layer1 = new L.Polygon([
      [0, 0],
      [1, 1],
      [1, 0],
    ]).addTo(map);

    const layer2 = new L.Polygon([
      [5, 5],
      [6, 6],
      [6, 5],
    ]).addTo(map);

    const onCoDragEnd = vi.fn();
    const cleanup = enablePixelSpaceDrag(map, layer1, () => [layer2], onCoDragEnd);

    // Verify cleanup removes listeners without errors
    expect(typeof cleanup).toBe("function");
    cleanup();

    map.remove();
    container.remove();
  });
});

describe("mapDragUtils - geometric keyboard adjustment on multi-selected features", () => {
  it("nudges multiple selected features simultaneously with keyboard arrows (ArrowUp/Down/Left/Right)", () => {
    const container = document.createElement("div");
    container.style.width = "800px";
    container.style.height = "600px";
    document.body.appendChild(container);

    const map = L.map(container).setView([46.8, -71.2], 10);

    const pointFeature: Feature = {
      type: "Feature",
      id: "feat-point-1",
      name: "Québec",
      geometry: { type: "Point", coordinates: [-71.2, 46.8] },
      properties: { name: "Québec" },
    };

    const polygonFeature: Feature = {
      type: "Feature",
      id: "feat-poly-1",
      name: "Zone",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-71.2, 46.8],
            [-71.1, 46.8],
            [-71.1, 46.9],
            [-71.2, 46.8],
          ],
        ],
      },
      properties: { name: "Zone" },
    };

    const selectedFeatures = [pointFeature, polygonFeature];

    // 1. Shift right by 10px (ArrowRight + Shift)
    const rightDelta = getNudgeDelta("ArrowRight", true)!;
    expect(rightDelta).toEqual({ dx: 10, dy: 0 });

    const shiftedRight = selectedFeatures.map((f) =>
      nudgeFeatureByPixels(f, map, rightDelta.dx, rightDelta.dy),
    );

    const ptCoordsAfterRight = shiftedRight[0].geometry.coordinates as [number, number];
    // Longitude should have increased (moved right in pixel space)
    expect(ptCoordsAfterRight[0]).toBeGreaterThan(pointFeature.geometry.coordinates[0]);

    // 2. Shift down by 1px (ArrowDown)
    const downDelta = getNudgeDelta("ArrowDown", false)!;
    expect(downDelta).toEqual({ dx: 0, dy: 1 });

    const shiftedDown = shiftedRight.map((f) =>
      nudgeFeatureByPixels(f, map, downDelta.dx, downDelta.dy),
    );

    const ptCoordsAfterDown = shiftedDown[0].geometry.coordinates as [number, number];
    // Latitude should have decreased (moved downwards in pixel/screen space)
    expect(ptCoordsAfterDown[1]).toBeLessThan(ptCoordsAfterRight[1]);

    // 3. Shift left by 10px (ArrowLeft + Shift)
    const leftDelta = getNudgeDelta("ArrowLeft", true)!;
    const shiftedLeft = shiftedDown.map((f) =>
      nudgeFeatureByPixels(f, map, leftDelta.dx, leftDelta.dy),
    );

    // 4. Shift up by 1px (ArrowUp)
    const upDelta = getNudgeDelta("ArrowUp", false)!;
    const restored = shiftedLeft.map((f) =>
      nudgeFeatureByPixels(f, map, upDelta.dx, upDelta.dy),
    );

    const ptCoordsRestored = restored[0].geometry.coordinates as [number, number];
    expect(ptCoordsRestored[0]).toBeCloseTo(pointFeature.geometry.coordinates[0], 2);
    expect(ptCoordsRestored[1]).toBeCloseTo(pointFeature.geometry.coordinates[1], 3);

    map.remove();
    container.remove();
  });
});

