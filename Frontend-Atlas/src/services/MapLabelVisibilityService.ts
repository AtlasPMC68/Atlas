import L from "leaflet";
import type { Feature } from "../typescript/feature";
import { forEachLeafLayer } from "../utils/mapDragUtils";
import { getElementCategoryInfo } from "../utils/labelPresentation";
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
    label.style.top = "0px";
    if (label.style.display === "none") label.style.display = "";
    label.style.visibility = "";
    label.style.pointerEvents = "";
  });

  const candidates = labels
    .map((label) => {
      const { priority, minZoom } = getElementCategoryInfo(label);
      return {
        id: label.dataset.featureId || "",
        text: label.textContent || "",
        priority,
        minZoom,
        rectangle: label.getBoundingClientRect(),
      };
    })
    .filter((candidate) => candidate.id.length > 0);

  const visibleIds = selectVisibleLabels(
    candidates,
    bounds,
    map.getZoom(),
    selectedFeatureId,
  );

  labels.forEach((label) => {
    const featureId = label.dataset.featureId;
    if (!featureId) return;

    const layer = layers.get(featureId);
    let circlePoint: L.CircleMarker | null = null;
    if (layer) {
      forEachLeafLayer(layer, (leaf) => {
        if (leaf instanceof L.CircleMarker) circlePoint = leaf;
      });
    }

    const isVisible = visibleIds.has(featureId);
    label.style.visibility = isVisible ? "" : "hidden";
    label.style.pointerEvents = isVisible ? "" : "none";
    updatePointVisibility(circlePoint, isVisible);
  });
}
