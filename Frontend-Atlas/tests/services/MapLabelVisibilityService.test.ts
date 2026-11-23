import { describe, it, expect, beforeEach } from "vitest";
import L from "leaflet";
import { updateMapLabelVisibility } from "../../src/services/MapLabelVisibilityService";

describe("MapLabelVisibilityService", () => {
  let map: L.Map;
  let container: HTMLDivElement;

  beforeEach(() => {
    container = document.createElement("div");
    container.id = "map-test-container";
    container.style.width = "800px";
    container.style.height = "600px";
    document.body.appendChild(container);

    map = L.map(container).setView([50, 10], 10);
  });

  it("keeps a selected feature label visible even when other labels are evaluated", () => {
    const label1 = document.createElement("div");
    label1.className = "city-label-text";
    label1.dataset.featureId = "label-1";
    label1.dataset.priority = "1";
    label1.dataset.minZoom = "12";
    label1.textContent = "Label One";
    container.appendChild(label1);

    const label2 = document.createElement("div");
    label2.className = "city-label-text";
    label2.dataset.featureId = "label-2";
    label2.dataset.priority = "1";
    label2.dataset.minZoom = "12";
    label2.textContent = "Label Two";
    container.appendChild(label2);

    const layers = new Map<string, L.Layer>();
    updateMapLabelVisibility(map, "label-2", layers);

    expect(label2.style.visibility).toBe("");
    expect(label2.style.pointerEvents).toBe("");
  });

  it("keeps label visible when it has label-selected class", () => {
    const label = document.createElement("div");
    label.className = "city-label-text label-selected";
    label.dataset.featureId = "label-selected-test";
    label.dataset.priority = "0";
    label.dataset.minZoom = "15";
    label.textContent = "Selected Label";
    container.appendChild(label);

    const layers = new Map<string, L.Layer>();
    updateMapLabelVisibility(map, null, layers);

    expect(label.style.visibility).toBe("");
    expect(label.style.pointerEvents).toBe("");
  });
});
