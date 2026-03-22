import type { Ref } from "vue";
import L from "leaflet";
import type { Feature } from "../typescript/feature";
import type {
  FeatureLayer,
  LeafletPointerEvent,
  MapLayersProps,
  MapWithPm,
  RadiusAdjustable,
} from "../typescript/mapLayers";

export class FeatureLayerManager {
  public layers = new Map<string, FeatureLayer>();
  private map: L.Map | null = null;

  constructor(
    private mapLayersProps: MapLayersProps,
    private allCircles: Ref<Set<RadiusAdjustable>>,
  ) {}

  setMap(map: L.Map) {
    this.map = map;
    map.on("popupopen", () => {
      if (this.shouldBlockLeafletEvents()) {
        map.closePopup();
      }
    });
  }

  private shouldBlockLeafletEvents() {
    const pm = (this.map as MapWithPm | null)?.pm;
    if (!pm) return false;

    const isEditActive =
      typeof pm.globalEditModeEnabled === "function"
        ? pm.globalEditModeEnabled()
        : false;
    const isDragActive =
      typeof pm.globalDragModeEnabled === "function"
        ? pm.globalDragModeEnabled()
        : false;
    const isRemovalActive =
      typeof pm.globalRemovalModeEnabled === "function"
        ? pm.globalRemovalModeEnabled()
        : false;

    return Boolean(isEditActive || isDragActive || isRemovalActive);
  }

  addFeatureLayer(
    featureId: string | number,
    layer: FeatureLayer,
    _feature: Feature,
  ) {
    const featureIdAsString = String(featureId);

    if (this.layers.has(featureIdAsString)) {
      const oldLayer = this.layers.get(featureIdAsString);
      if (oldLayer instanceof L.CircleMarker) {
        this.allCircles.value.delete(oldLayer);
      }
      if (this.map && oldLayer && this.map.hasLayer(oldLayer)) {
        this.map.removeLayer(oldLayer);
      }
    }

    this.layers.set(featureIdAsString, layer);

    if (layer instanceof L.CircleMarker) {
      this.allCircles.value.add(layer);
    }

    this.makeLayerClickable(layer);

    const visibilityMap = this.mapLayersProps.featureVisibility.value;
    const visible =
      visibilityMap.get(featureIdAsString) ?? visibilityMap.get(featureId);
    const shouldShow = visible === undefined ? true : Boolean(visible);

    if (shouldShow && this.map && !this.map.hasLayer(layer)) {
      this.map.addLayer(layer);
    }
    if (!shouldShow && this.map && this.map.hasLayer(layer)) {
      this.map.removeLayer(layer);
    }
  }

  makeLayerClickable(layer: FeatureLayer) {
    if (layer.options) {
      layer.options.interactive = true;
      layer.options.bubblingMouseEvents = true;
    }

    if (layer.__atlasOnDown) layer.off("mousedown", layer.__atlasOnDown);
    if (layer.__atlasOnClick) layer.off("click", layer.__atlasOnClick);
    if (layer.__atlasOnPointerDown)
      layer.off("pointerdown", layer.__atlasOnPointerDown);

    layer.__atlasOnDown = (e) => {
      if (this.shouldBlockLeafletEvents()) {
        const originalEvent = (e as LeafletPointerEvent).originalEvent;
        originalEvent?.stopPropagation();
        if (originalEvent && "stopImmediatePropagation" in originalEvent) {
          (
            originalEvent as Event & { stopImmediatePropagation: () => void }
          ).stopImmediatePropagation();
        }
      }
    };

    layer.__atlasOnPointerDown = (e) => {
      if (this.shouldBlockLeafletEvents()) {
        const originalEvent = (e as LeafletPointerEvent).originalEvent;
        originalEvent?.stopPropagation();
        if (originalEvent && "stopImmediatePropagation" in originalEvent) {
          (
            originalEvent as Event & { stopImmediatePropagation: () => void }
          ).stopImmediatePropagation();
        }
      }
    };

    layer.__atlasOnClick = (e) => {
      (e as LeafletPointerEvent).originalEvent?.stopPropagation();
    };

    layer.on("mousedown", layer.__atlasOnDown);
    layer.on("pointerdown", layer.__atlasOnPointerDown);
    layer.on("click", layer.__atlasOnClick);
  }

  toggleFeature(featureId: string | number, visible: boolean) {
    const featureIdAsString = String(featureId);
    const layer = this.layers.get(featureIdAsString);
    if (!layer || !this.map) return;

    if (visible) {
      if (!this.map.hasLayer(layer)) this.map.addLayer(layer);
    } else {
      if (this.map.hasLayer(layer)) this.map.removeLayer(layer);
    }
  }

  removeFeature(featureId: string | number, map: L.Map | null = this.map) {
    const featureIdAsString = String(featureId);
    const layer = this.layers.get(featureIdAsString);
    if (!layer) return;

    if (layer instanceof L.CircleMarker) {
      this.allCircles.value.delete(layer);
    }

    if (map && map.hasLayer(layer)) {
      map.removeLayer(layer);
    }

    this.layers.delete(featureIdAsString);
  }

  clearAllFeatures(map: L.Map | null) {
    this.layers.forEach((layer) => {
      if (layer instanceof L.CircleMarker) {
        this.allCircles.value.delete(layer);
      }
      if (map && map.hasLayer(layer)) {
        map.removeLayer(layer);
      }
    });
    this.layers.clear();
  }
}
