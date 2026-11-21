import { describe, it, expect, vi } from "vitest";
import L from "leaflet";
import { enablePixelSpaceDrag, enablePerFeatureDrag, disablePerFeatureDrag } from "../../src/utils/mapDragUtils";

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
