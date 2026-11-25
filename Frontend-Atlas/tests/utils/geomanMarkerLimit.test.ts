import { afterEach, beforeEach, describe, expect, it } from "vitest";
import L from "leaflet";
import "@geoman-io/leaflet-geoman-free";
import { anchorMarkerLimitToCursor } from "../../src/utils/geomanMarkerLimit";

if (typeof PointerEvent === "undefined") {
  class PointerEventPolyfill extends MouseEvent {
    constructor(type: string, init?: MouseEventInit) {
      super(type, init);
    }
  }
  Object.defineProperty(globalThis, "PointerEvent", {
    value: PointerEventPolyfill,
    writable: true,
    configurable: true,
  });
}

type PmLayer = L.Polygon & {
  pm: {
    enable: (options: Record<string, unknown>) => void;
    disable: () => void;
    _markerGroup: L.FeatureGroup;
    _markers: L.Marker[][];
  };
};

// A ring of 200 vertices far from lat/lng 0,0 (around the Sahara).
function denseRing(): L.LatLng[] {
  return Array.from({ length: 200 }, (_, i) => {
    const a = (i / 200) * Math.PI * 2;
    return L.latLng(22 + 8 * Math.sin(a), 5 + 15 * Math.cos(a));
  });
}

function shownVertices(layer: PmLayer): L.Marker[] {
  const shown = new Set(layer.pm._markerGroup.getLayers());
  return layer.pm._markers.flat().filter((m) => shown.has(m));
}

describe("anchorMarkerLimitToCursor", () => {
  let container: HTMLDivElement;
  let map: L.Map;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    map = L.map(container, { renderer: L.svg() }).setView([22, 5], 4);
    anchorMarkerLimitToCursor(map);
  });

  afterEach(() => {
    map.remove();
    container.remove();
  });

  it("keeps the handles around the pointer when Leaflet mousemove does not fire", () => {
    const layer = L.polygon(denseRing()).addTo(map) as PmLayer;
    const start = L.latLng(22, -10);
    map.fire("mousemove", { latlng: start });
    layer.pm.enable({ limitMarkersToCount: 10 });

    const end = L.latLng(22, 20);
    const container = map.getContainer();
    const point = map.latLngToContainerPoint(end);
    const rect = container.getBoundingClientRect();
    container.dispatchEvent(
      new PointerEvent("pointermove", {
        clientX: rect.left + point.x,
        clientY: rect.top + point.y,
        bubbles: true,
      }),
    );
    (layer.pm as unknown as { applyLimitFilters: (args: object) => void }).applyLimitFilters(
      {},
    );

    const shown = shownVertices(layer);
    expect(shown.length).toBeGreaterThan(0);
    for (const marker of shown) {
      expect(marker.getLatLng().distanceTo(end)).toBeLessThan(1_000_000);
    }
    layer.pm.disable();
  });

  it("keeps the handles around the cursor after a vertex is removed", () => {
    const layer = L.polygon(denseRing()).addTo(map) as PmLayer;
    // The western tip of the ring, where the user is working.
    const cursor = L.latLng(22, -10);
    map.fire("mousemove", { latlng: cursor });
    layer.pm.enable({ limitMarkersToCount: 10 });

    const target = shownVertices(layer)[0];
    target.fire("contextmenu", { latlng: target.getLatLng() });

    const shown = shownVertices(layer);
    expect(shown.length).toBeGreaterThan(0);
    for (const marker of shown) {
      expect(marker.getLatLng().distanceTo(cursor)).toBeLessThan(1_000_000);
    }
    layer.pm.disable();
  });
});
