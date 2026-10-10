import { describe, it, expect, vi, beforeEach } from "vitest";
import { ref } from "vue";
import L from "leaflet";
import { ShapeScalingService } from "../../src/services/ShapeScalingService";
import type { Feature } from "../../src/typescript/feature";

describe("ShapeScalingService", () => {
  let map: L.Map;
  let polygon: L.Polygon;
  let service: ShapeScalingService;
  const localFeatures = ref<Feature[]>([]);
  const onBeforeEmit = vi.fn();
  const onUpdate = vi.fn();

  beforeEach(() => {
    // Setup a dummy DOM container for Leaflet map
    const mapDiv = document.createElement("div");
    mapDiv.id = "map";
    mapDiv.style.width = "800px";
    mapDiv.style.height = "600px";
    document.body.appendChild(mapDiv);

    map = L.map(mapDiv).setView([50, 10], 10);

    // Create a polygon layer
    polygon = L.polygon([
      [50, 10],
      [50, 12],
      [49, 12],
      [49, 10],
    ]).addTo(map);

    localFeatures.value = [
      {
        id: "feat-1",
        type: "Feature",
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [10, 50],
              [12, 50],
              [12, 49],
              [10, 49],
              [10, 50],
            ],
          ],
        },
        properties: {},
      } as unknown as Feature,
    ];

    service = new ShapeScalingService(
      () => map,
      (id: string) => (id === "feat-1" ? polygon : undefined),
      localFeatures,
      () => "proj-1",
      () => 2026,
      onBeforeEmit,
      onUpdate,
    );
  });

  it("attaches 8 handles with proper sizes and anchors", () => {
    service.attach("feat-1");
    const interaction = (service as any).interaction;
    expect(interaction).not.toBeNull();
    expect(interaction.handles).toHaveLength(8);

    const cornerHandles = interaction.handles.filter((h: any) =>
      h.def.cls.includes("shape-resize-handle--corner"),
    );
    expect(cornerHandles).toHaveLength(4);
    cornerHandles.forEach((h: any) => {
      expect(h.def.iconSize).toEqual([10, 10]);
      expect(h.def.iconAnchor).toEqual([5, 5]);
    });

    const edgeHandles = interaction.handles.filter((h: any) =>
      h.def.cls.includes("shape-resize-handle--edge"),
    );
    expect(edgeHandles).toHaveLength(4);
    edgeHandles.forEach((h: any) => {
      expect(h.def.iconSize).toEqual([8, 8]);
      expect(h.def.iconAnchor).toEqual([4, 4]);
    });

    service.detach();
    expect((service as any).interaction).toBeNull();
  });

  it("updates handle positions and bounding line on map zoomend", () => {
    service.attach("feat-1");
    const interaction = (service as any).interaction;
    const initialNW = interaction.handles[0].marker.getLatLng();

    // Fire zoomend event
    map.fire("zoomend");

    // Overlay is re-computed and aligned
    expect(interaction.handles[0].marker.getLatLng().lat).toBeCloseTo(initialNW.lat, 4);
    expect(interaction.handles[0].marker.getLatLng().lng).toBeCloseTo(initialNW.lng, 4);

    service.detach();
  });

  it("cleans up map event listeners on detach", () => {
    const offSpy = vi.spyOn(map, "off");
    service.attach("feat-1");
    service.detach();

    expect(offSpy).toHaveBeenCalledWith("zoomend", expect.any(Function));
    expect(offSpy).toHaveBeenCalledWith("viewreset", expect.any(Function));
  });
});
