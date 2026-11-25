import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import L from "leaflet";
import { applySmartFeatureFraming } from "../../src/utils/mapFraming";

describe("mapFraming - applySmartFeatureFraming", () => {
  let container: HTMLDivElement;
  let map: L.Map;

  beforeEach(() => {
    container = document.createElement("div");
    container.style.width = "800px";
    container.style.height = "600px";
    document.body.appendChild(container);
    map = L.map(container).setView([46.8, -71.2], 10);
  });

  afterEach(() => {
    map.remove();
    container.remove();
  });

  it("returns 'in-view' and does nothing if target bounds are invalid or map is null", () => {
    const invalidBounds = L.latLngBounds([]);
    const panToSpy = vi.spyOn(map, "panTo");
    const setViewSpy = vi.spyOn(map, "setView");
    const fitBoundsSpy = vi.spyOn(map, "fitBounds");

    const result = applySmartFeatureFraming(map, invalidBounds);
    expect(result).toBe("in-view");
    expect(panToSpy).not.toHaveBeenCalled();
    expect(setViewSpy).not.toHaveBeenCalled();
    expect(fitBoundsSpy).not.toHaveBeenCalled();
  });

  it("does NOT move or pan map when element is fully inside the padded viewport", () => {
    vi.spyOn(map, "getBounds").mockReturnValue(
      L.latLngBounds([
        [40, -80],
        [52, -60],
      ]),
    );
    const targetInView = L.latLngBounds([
      [45, -72],
      [46, -70],
    ]);

    const panToSpy = vi.spyOn(map, "panTo");
    const setViewSpy = vi.spyOn(map, "setView");
    const fitBoundsSpy = vi.spyOn(map, "fitBounds");

    const result = applySmartFeatureFraming(map, targetInView, {
      mapLevelZoom: 5,
      animate: true,
    });

    expect(result).toBe("in-view");
    expect(panToSpy).not.toHaveBeenCalled();
    expect(setViewSpy).not.toHaveBeenCalled();
    expect(fitBoundsSpy).not.toHaveBeenCalled();
  });

  it("pans when the element intersects the viewport but is clipped", () => {
    const viewBounds = map.getBounds();
    const targetIntersecting = L.latLngBounds([
      [viewBounds.getNorth(), viewBounds.getWest()],
      [viewBounds.getNorth() + 1, viewBounds.getWest() - 1],
    ]);

    const panToSpy = vi.spyOn(map, "panTo");
    const setViewSpy = vi.spyOn(map, "setView");
    const fitBoundsSpy = vi.spyOn(map, "fitBounds");

    const result = applySmartFeatureFraming(map, targetIntersecting, {
      mapLevelZoom: 5,
      animate: true,
    });

    expect(result).toBe("panned");
    expect(panToSpy).toHaveBeenCalled();
    expect(fitBoundsSpy).not.toHaveBeenCalled();
  });

  it("pans to element without resetting zoom when element is outside viewport and user is zoomed in", () => {
    // Map is at zoom 10, overview level is 5
    // Target is far away (e.g. Paris [48.85, 2.35])
    const targetOutside = L.latLngBounds([
      [48.8, 2.3],
      [48.9, 2.4],
    ]);

    const panToSpy = vi.spyOn(map, "panTo");
    const fitBoundsSpy = vi.spyOn(map, "fitBounds");

    const result = applySmartFeatureFraming(map, targetOutside, {
      mapLevelZoom: 5,
      animate: true,
    });

    expect(result).toBe("panned");
    expect(panToSpy).toHaveBeenCalledTimes(1);
    expect(panToSpy).toHaveBeenCalledWith(targetOutside.getCenter(), { animate: true });
    // User's current zoom level 10 was preserved (not reset to 5)
    expect(map.getZoom()).toBe(10);
    expect(fitBoundsSpy).not.toHaveBeenCalled();
  });

  it("sets view to mapLevelZoom when element is outside viewport and user is at or below overview zoom", () => {
    // Set map to overview zoom level 4
    map.setView([46.8, -71.2], 4);

    const targetOutside = L.latLngBounds([
      [10.0, 10.0],
      [11.0, 11.0],
    ]);

    const panToSpy = vi.spyOn(map, "panTo");
    const setViewSpy = vi.spyOn(map, "setView");
    const fitBoundsSpy = vi.spyOn(map, "fitBounds");

    const result = applySmartFeatureFraming(map, targetOutside, {
      mapLevelZoom: 5,
      animate: true,
      multi: false,
    });

    expect(result).toBe("view-set");
    expect(panToSpy).not.toHaveBeenCalled();
    expect(setViewSpy).toHaveBeenCalledWith(
      targetOutside.getCenter(),
      5,
      expect.objectContaining({ animate: true }),
    );
    expect(fitBoundsSpy).not.toHaveBeenCalled();
  });

  it("fits bounds with padding when multiple elements are outside viewport at overview zoom", () => {
    map.setView([46.8, -71.2], 4);

    const targetOutside = L.latLngBounds([
      [10.0, 10.0],
      [15.0, 15.0],
    ]);

    const panToSpy = vi.spyOn(map, "panTo");
    const fitBoundsSpy = vi.spyOn(map, "fitBounds");

    const result = applySmartFeatureFraming(map, targetOutside, {
      mapLevelZoom: 5,
      animate: true,
      multi: true,
    });

    expect(result).toBe("bounds-fitted");
    expect(panToSpy).not.toHaveBeenCalled();
    expect(fitBoundsSpy).toHaveBeenCalledWith(
      targetOutside,
      expect.objectContaining({
        padding: [80, 80],
        maxZoom: 5,
        animate: true,
      }),
    );
  });
});
