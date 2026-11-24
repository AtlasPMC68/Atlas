import L from "leaflet";
import type { Feature } from "../typescript/feature";
import { forEachLeafLayer } from "../utils/mapDragUtils";
import { selectVisibleLabels } from "../utils/labelCollision";

type CircleMarkerWithFeature = L.CircleMarker & { feature?: Feature };

function updatePointVisibility(
  circle: L.CircleMarker | null,
  visible: boolean,
): void {
  if (!circle) return;
  if (!visible) {
    circle.setStyle({ opacity: 0, fillOpacity: 0 });
    return;
  }

  const feature = (circle as CircleMarkerWithFeature).feature;
  circle.setStyle({
    opacity: feature?.properties.strokeOpacity ?? 1,
    fillOpacity: feature?.properties.fillOpacity ?? 0.5,
  });
}

function findCircleMarker(layer: L.Layer | undefined): L.CircleMarker | null {
  if (!layer) return null;
  if (layer instanceof L.CircleMarker) return layer;
  let found: L.CircleMarker | null = null;
  forEachLeafLayer(layer, (leaf) => {
    if (!found && leaf instanceof L.CircleMarker) {
      found = leaf;
    }
  });
  return found;
}

export function updateMapLabelVisibility(
  map: L.Map,
  selectedFeatureId: string | null,
  layers: ReadonlyMap<string, L.Layer>,
): void {
  const container = map.getContainer();
  const bounds = container.getBoundingClientRect();
  const labels: HTMLElement[] = Array.from(
    container.querySelectorAll<HTMLElement>(".city-label-text"),
  );
  if (labels.length === 0) return;

  labels.forEach((label) => {
    if (label.style.display === "none") label.style.display = "";
    label.style.visibility = "";
    label.style.pointerEvents = "";
  });

  const candidates = labels
    .map((label) => {
      const sizeFromData = Number.parseFloat(
        label.dataset.sizePx || label.dataset.priority || "",
      );
      const sizeFromCss = Number.parseFloat(label.style.getPropertyValue("--label-size"));
      const sizePx = Number.isFinite(sizeFromData)
        ? sizeFromData
        : Number.isFinite(sizeFromCss)
          ? sizeFromCss
          : 0;
      return {
        id: label.dataset.featureId || "",
        text: label.textContent || "",
        sizePx,
        rectangle: label.getBoundingClientRect(),
      };
    })
    .filter((candidate) => candidate.id.length > 0);

  const visibleIds = selectVisibleLabels(
    candidates,
    bounds,
    selectedFeatureId,
  );

  labels.forEach((label) => {
    const featureId = label.dataset.featureId;
    if (!featureId) return;

    const isVisible =
      visibleIds.has(featureId) ||
      (selectedFeatureId != null && featureId === selectedFeatureId) ||
      label.classList.contains("label-selected");
    label.style.visibility = isVisible ? "" : "hidden";
    label.style.pointerEvents = isVisible ? "" : "none";
    const circle = findCircleMarker(layers.get(featureId));
    updatePointVisibility(circle, isVisible);
  });
}
