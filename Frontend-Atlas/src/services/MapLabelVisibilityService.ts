import L from "leaflet";
import type { Feature } from "../typescript/feature";
import { forEachLeafLayer } from "../utils/mapDragUtils";
import { selectVisibleLabels } from "../utils/labelCollision";

type CircleMarkerWithFeature = L.CircleMarker & { feature?: Feature };

function isMapPointMarker(layer: L.Layer): layer is L.Marker {
  if (!(layer instanceof L.Marker) || layer instanceof L.CircleMarker) {
    return false;
  }
  const el = layer.getElement();
  if (el?.classList.contains("map-point-marker")) return true;
  const icon = layer.options.icon;
  return Boolean(
    icon && "options" in icon && icon.options.className === "map-point-marker",
  );
}

function updatePointVisibility(
  point: L.Layer | null,
  visible: boolean,
): void {
  if (!point) return;

  if (point instanceof L.CircleMarker) {
    if (!visible) {
      point.setStyle({ opacity: 0, fillOpacity: 0 });
      return;
    }
    const feature = (point as CircleMarkerWithFeature).feature;
    point.setStyle({
      opacity: feature?.properties.strokeOpacity ?? 1,
      fillOpacity: feature?.properties.fillOpacity ?? 0.5,
    });
    return;
  }

  if (point instanceof L.Marker) {
    point.setOpacity(visible ? 1 : 0);
    const el = point.getElement();
    if (el) el.style.pointerEvents = visible ? "" : "none";
  }
}

function readLabelSizePx(label: HTMLElement): number {
  const fromData = Number.parseFloat(label.dataset.sizePx || "");
  if (Number.isFinite(fromData) && fromData > 0) return fromData;
  const raw =
    label.style.getPropertyValue("--label-size") ||
    getComputedStyle(label).getPropertyValue("--label-size") ||
    getComputedStyle(label).fontSize;
  const fromCss = Number.parseFloat(raw);
  return Number.isFinite(fromCss) && fromCss > 0 ? fromCss : 0;
}

function findPointLayer(layer: L.Layer | undefined): L.Layer | null {
  if (!layer) return null;
  if (layer instanceof L.CircleMarker) return layer;
  if (isMapPointMarker(layer)) return layer;
  let found: L.Layer | null = null;
  forEachLeafLayer(layer, (leaf) => {
    if (found) return;
    if (leaf instanceof L.CircleMarker || isMapPointMarker(leaf)) {
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
    .map((label) => ({
      id: label.dataset.featureId || "",
      text: label.textContent || "",
      sizePx: readLabelSizePx(label),
      rectangle: label.getBoundingClientRect(),
    }))
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
    updatePointVisibility(findPointLayer(layers.get(featureId)), isVisible);
  });
}
