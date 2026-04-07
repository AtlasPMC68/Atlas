import { ref } from "vue";
import L from "leaflet";
import { featureToLayer, layerToFeature, isPointFeature } from "../utils/mapDrawingFeature";
import type { Feature, PointFeature } from "../typescript/feature";
import { drawingModes } from "../typescript/mapDrawing";
import type {
  DrawingMode,
  EmitFn,
  FeatureBearingLayer,
  MapWithPm,
  MouseDrawListeners,
  PmCutEvent,
  PmDrawStartEvent,
  PmLassoSelectEvent,
  PmLayerEvent,
  PmRemovalToggleEvent,
} from "../typescript/mapDrawing";

const freehandControlName = "drawFreehand";
const addCityControlName = "addCity";
const removalSelectionStyle: L.PathOptions = {
  color: "#ef4444",
  weight: 2,
  dashArray: "6 6",
  fillColor: "#ef4444",
  fillOpacity: 0.12,
};

const lassoDeleteOptions = {
  mode: "RESET",
  selectMode: "CONTAIN",
  lassoDrawOptions: {
    ...removalSelectionStyle,
  },
} as const;

export class MapDrawingService {
  public activeDrawingMode = ref<DrawingMode>(null);
  public drawnItems = ref<L.FeatureGroup | null>(null);
  public selectedYear = 1740;
  private pmMapInstance: MapWithPm | null = null;
  private freehandActive = false;
  private freehandListeners: MouseDrawListeners = {};
  private removalLassoEnabled = false;
  private fallbackRemovalSelectionEnabled = false;
  private fallbackSelectionRectangle: L.Rectangle | null = null;
  private fallbackSelectionStart: L.LatLng | null = null;
  private fallbackSelectionDragging = false;
  private fallbackRemovalListeners: MouseDrawListeners = {};
  // True from pm:drawstart (shape=Cut) until the deferred setTimeout in
  // pm:drawend fires. Used only to know whether to emit cut-complete after the
  // synchronous cut cycle (pm:cut / pm:remove) has fully processed.
  private isCuttingActive = false;

  constructor(private emit: EmitFn) {}

  private finalizedTextLayers = new WeakSet<L.Layer>();

  private isTextLayer(layer: L.Layer): boolean {
    const marker = layer as L.Marker & {
      options?: L.MarkerOptions & {
        text?: string;
        textMarker?: boolean;
      };
      pm?: {
        getText?: () => string;
      };
    };

    return Boolean(
      marker instanceof L.Marker &&
        (marker.options?.textMarker === true ||
          typeof marker.pm?.getText === "function"),
    );
  }

  private finalizeTextLayer(map: L.Map, layer: FeatureBearingLayer) {
    if (this.finalizedTextLayers.has(layer)) {
      return;
    }

    const textLayer = layer as L.Marker & FeatureBearingLayer & {
      options?: L.MarkerOptions & {
        text?: string;
        textMarker?: boolean;
      };
      pm?: {
        getText?: () => string;
      };
    };

    const rawText =
      textLayer.pm?.getText?.() ?? textLayer.options?.text ?? "";
    const labelText = rawText.trim();

    if (!labelText) {
      return;
    }

    const feature = layerToFeature(textLayer, this.selectedYear);
    if (!feature || !isPointFeature(feature)) {
      return;
    }

    const pointFeature: PointFeature = {
      ...feature,
      geometry: feature.geometry,
      name: labelText,
      updatedAt: new Date().toISOString(),
      properties: {
        ...feature.properties,
        name: labelText,
        labelText,
        mapElementType: "label",
      },
    };

    (textLayer as L.Marker & { feature?: PointFeature }).feature = pointFeature;

    this.finalizedTextLayers.add(layer);
    this.emit("feature-created", pointFeature);

    setTimeout(() => {
      this.drawnItems.value?.removeLayer(layer);
      if (map.hasLayer(layer)) {
        map.removeLayer(layer);
      }
    }, 0);
  }

  private attachFeatureAndEmit(
    layer: FeatureBearingLayer,
    feature: Feature | null,
    eventName: "feature-created" | "feature-updated",
  ) {
    if (!feature) return;
    layer.feature = feature;
    this.emit(eventName, feature);
  }

  private isMapLayerRemovable(
    layer: L.Layer & {
      pm?: {
        options?: { allowRemoval?: boolean };
        remove?: () => void;
      };
      _pmTempLayer?: boolean;
    },
  ) {
    if (!layer.pm || layer._pmTempLayer) return false;
    return layer.pm.options?.allowRemoval !== false;
  }

  initializeDrawing(map: L.Map) {
    const mapWithPm = map as MapWithPm;
    if (!mapWithPm.pm) {
      console.warn("Leaflet.pm not properly initialized");
      return;
    }

    this.pmMapInstance = mapWithPm;
    this.drawnItems.value = new L.FeatureGroup();
    map.addLayer(this.drawnItems.value as unknown as L.Layer);

    mapWithPm.pm.addControls({
      position: "topright",
      continueDrawing: false,
      drawMarker: false,
      drawPolyline: true,
      drawPolygon: true,
      drawCircle: true,
      drawRectangle: true,
      drawCircleMarker: false,
      drawText: true,
      editMode: true,
      dragMode: true,
      rotateMode: true,
      cutPolygon: true,
      removalMode: true,
    });

    // 'fr' locale is missing drawTextButton — merge it in by passing 'fr' as both lang and fallback
    mapWithPm.pm.setLang?.('fr', { buttonTitles: { drawTextButton: 'Insérer du texte' } } as unknown as Record<string, unknown>, 'fr');
    this.addFreehandButton(map);
    this.addCityButton(map);
    this.setupDrawingListeners(map);
  }

  private addFreehandButton(map: L.Map) {
    const toolbar = (map as MapWithPm).pm?.Toolbar;
    if (
      !toolbar?.createCustomControl ||
      toolbar.controlExists?.(freehandControlName)
    ) {
      return;
    }

    toolbar.createCustomControl({
      name: freehandControlName,
      block: "draw",
      title: "Dessiner ligne à main levée",
      className: "leaflet-pm-icon-freehand",
      toggle: true,
      disableOtherButtons: true,
      disableByOtherButtons: true,
      actions: ["cancel"],
      onClick: () => {},
      afterClick: (
        _event: unknown,
        context: { button: { toggled: () => boolean } },
      ) => {
        if (context.button.toggled()) {
          this.setDrawingMode("freehand");
          return;
        }
        this.setDrawingMode(null);
      },
    });

    toolbar.changeControlOrder?.();
  }

  private addCityButton(map: L.Map) {
    const toolbar = (map as MapWithPm).pm?.Toolbar;
    if (
      !toolbar?.createCustomControl ||
      toolbar.controlExists?.(addCityControlName)
    ) {
      return;
    }

    toolbar.createCustomControl({
      name: addCityControlName,
      block: "draw",
      title: "Ajouter une ville",
      className: "leaflet-pm-icon-add-city",
      toggle: true,
      disableOtherButtons: true,
      disableByOtherButtons: true,
      actions: ["cancel"],
      onClick: () => {},
      afterClick: () => {},
    });

    toolbar.changeControlOrder?.();
  }

  startFreehandDrawing(map: L.Map) {
    if (this.freehandActive) return;

    this.freehandActive = true;
    let isDrawing = false;
    let points: L.LatLng[] = [];
    let polyline: L.Polyline | null = null;

    map.dragging.disable();
    map.getContainer().style.userSelect = "none";

    const pencilCursor = `url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="%23000" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"></path></svg>') 4 20, auto`;
    map.getContainer().style.cursor = pencilCursor;

    const onMouseDown = (e: L.LeafletMouseEvent) => {
      isDrawing = true;
      points = [e.latlng];
      polyline = L.polyline(points, {
        color: "#000000",
        weight: 2,
        opacity: 0.8,
      }).addTo(map);
    };

    const onMouseMove = (e: L.LeafletMouseEvent) => {
      if (!isDrawing || !polyline) return;
      points.push(e.latlng);
      polyline.setLatLngs(points);
    };

    const onMouseUp = () => {
      if (!isDrawing || !polyline) return;
      isDrawing = false;

      if (points.length > 1) {
        this.drawnItems.value?.addLayer(polyline);
        const feature = layerToFeature(polyline, this.selectedYear);
        if (feature) {
          (polyline as FeatureBearingLayer).feature = feature;
          this.emit("feature-created", feature);
        }
        const drawnLine = polyline;
        setTimeout(() => {
          this.drawnItems.value?.removeLayer(drawnLine);
          if (map.hasLayer(drawnLine)) {
            map.removeLayer(drawnLine);
          }
        }, 0);
      } else {
        map.removeLayer(polyline);
      }

      polyline = null;
      points = [];
      this.stopFreehandDrawing(map);
    };

    this.freehandListeners = { onMouseDown, onMouseMove, onMouseUp };
    (map as MapWithPm).pm?.disableDraw();

    map.on("mousedown", onMouseDown);
    map.on("mousemove", onMouseMove);
    map.on("mouseup", onMouseUp);
  }

  stopFreehandDrawing(map: L.Map) {
    if (!this.freehandActive) return;

    this.freehandActive = false;

    map.off("mousedown", this.freehandListeners.onMouseDown);
    map.off("mousemove", this.freehandListeners.onMouseMove);
    map.off("mouseup", this.freehandListeners.onMouseUp);

    map.dragging.enable();
    map.getContainer().style.cursor = "";
    map.getContainer().style.userSelect = "";
  }

  private enableRemovalLasso(map: L.Map) {
    const mapWithPm = map as MapWithPm;
    if (this.removalLassoEnabled) return;

    if (mapWithPm.pm?.enableGlobalLassoMode) {
      mapWithPm.pm.enableGlobalLassoMode(lassoDeleteOptions);
      this.removalLassoEnabled = true;
      return;
    }

    this.enableFallbackRemovalSelection(map);
    this.removalLassoEnabled = true;
  }

  private disableRemovalLasso(map: L.Map) {
    const mapWithPm = map as MapWithPm;
    if (!this.removalLassoEnabled) return;

    if (mapWithPm.pm?.disableGlobalLassoMode) {
      mapWithPm.pm.disableGlobalLassoMode();
    }

    this.disableFallbackRemovalSelection(map);
    this.removalLassoEnabled = false;
  }

  private getLayersInsideBounds(map: L.Map, bounds: L.LatLngBounds): L.Layer[] {
    const selected: L.Layer[] = [];

    map.eachLayer((layer) => {
      const candidate = layer as L.Layer & {
        pm?: {
          options?: { allowRemoval?: boolean };
          remove?: () => void;
        };
        _pmTempLayer?: boolean;
        getLatLng?: () => L.LatLng;
        getBounds?: () => L.LatLngBounds;
      };

      if (!this.isMapLayerRemovable(candidate)) {
        return;
      }

      if (
        layer instanceof L.Marker ||
        layer instanceof L.CircleMarker ||
        layer instanceof L.Circle
      ) {
        const latLng = candidate.getLatLng?.();
        if (latLng && bounds.contains(latLng)) {
          selected.push(layer);
        }
        return;
      }

      if (
        layer instanceof L.Polyline ||
        layer instanceof L.Polygon ||
        layer instanceof L.Rectangle
      ) {
        const layerBounds = candidate.getBounds?.();
        if (layerBounds && bounds.contains(layerBounds)) {
          selected.push(layer);
        }
      }
    });

    return selected;
  }

  private enableFallbackRemovalSelection(map: L.Map) {
    const mapWithPm = map as MapWithPm;
    if (this.fallbackRemovalSelectionEnabled) return;

    const onMouseDown = (e: L.LeafletMouseEvent) => {
      if (!e.originalEvent?.shiftKey || !mapWithPm.pm?.globalRemovalModeEnabled?.()) {
        return;
      }

      this.fallbackSelectionDragging = true;
      this.fallbackSelectionStart = e.latlng;
      map.dragging.disable();

      this.fallbackSelectionRectangle?.remove();
      const initialBounds = L.latLngBounds(e.latlng, e.latlng);
      this.fallbackSelectionRectangle = L.rectangle(initialBounds, {
        ...removalSelectionStyle,
        interactive: false,
      }).addTo(map);
    };

    const onMouseMove = (e: L.LeafletMouseEvent) => {
      if (
        !this.fallbackSelectionDragging ||
        !this.fallbackSelectionStart ||
        !this.fallbackSelectionRectangle
      ) {
        return;
      }

      this.fallbackSelectionRectangle.setBounds(
        L.latLngBounds(this.fallbackSelectionStart, e.latlng),
      );
    };

    const onMouseUp = () => {
      if (!this.fallbackSelectionDragging || !this.fallbackSelectionRectangle) {
        return;
      }

      const bounds = this.fallbackSelectionRectangle.getBounds();
      this.fallbackSelectionRectangle.remove();
      this.fallbackSelectionRectangle = null;
      this.fallbackSelectionDragging = false;
      this.fallbackSelectionStart = null;
      map.dragging.enable();

      if (!mapWithPm.pm?.globalRemovalModeEnabled?.()) {
        return;
      }

      const selectedLayers = this.getLayersInsideBounds(map, bounds);
      this.deleteLassoSelectedLayers(selectedLayers);
    };

    this.fallbackRemovalListeners = { onMouseDown, onMouseMove, onMouseUp };
    map.on("mousedown", onMouseDown);
    map.on("mousemove", onMouseMove);
    map.on("mouseup", onMouseUp);
    this.fallbackRemovalSelectionEnabled = true;
  }

  private disableFallbackRemovalSelection(map: L.Map) {
    if (!this.fallbackRemovalSelectionEnabled) return;

    const { onMouseDown, onMouseMove, onMouseUp } =
      this.fallbackRemovalListeners;
    if (onMouseDown) map.off("mousedown", onMouseDown);
    if (onMouseMove) map.off("mousemove", onMouseMove);
    if (onMouseUp) map.off("mouseup", onMouseUp);

    this.fallbackRemovalListeners = {};
    this.fallbackSelectionRectangle?.remove();
    this.fallbackSelectionRectangle = null;
    this.fallbackSelectionDragging = false;
    this.fallbackSelectionStart = null;
    map.dragging.enable();
    this.fallbackRemovalSelectionEnabled = false;
  }

  private deleteLassoSelectedLayers(layers: L.Layer[]) {
    const uniqueLayers = Array.from(new Set(layers));
    uniqueLayers.forEach((layer) => {
      const removableLayer = layer as L.Layer & {
        pm?: { remove?: () => void };
      };
      removableLayer.pm?.remove?.();
    });
  }

  private setBoxZoomForRemovalMode(map: L.Map, isRemovalModeEnabled: boolean) {
    if (!map.boxZoom) return;
    if (isRemovalModeEnabled) {
      map.boxZoom.disable();
      return;
    }
    map.boxZoom.enable();
  }

  private setupDrawingListeners(map: L.Map) {
    map.on("pm:create", (e) => {
      const layer = (e as PmLayerEvent).layer as FeatureBearingLayer;
      const shape = (e as PmLayerEvent).shape;

      // Geoman fires pm:create for the cut polygon itself. Treat it as internal
      // — the actual result is handled via pm:cut events on the affected layers.
      if (shape === "Cut") return;

      if (shape === "text" || this.isTextLayer(layer)) {
        layer.once("pm:textblur", () => {
          this.finalizeTextLayer(map, layer);
        });

        return;
      }

      const feature = layerToFeature(layer, this.selectedYear);
      this.attachFeatureAndEmit(layer, feature, "feature-created");

      setTimeout(() => {
        this.drawnItems.value?.removeLayer(layer);
        if (map.hasLayer(layer)) {
          map.removeLayer(layer);
        }
      }, 0);
    });

    map.on("pm:cut", (e) => {
      const { originalLayer, layer } = e as PmCutEvent;
      const sourceLayer = originalLayer as FeatureBearingLayer | undefined;
      const resultLayer = layer as FeatureBearingLayer | undefined;

      if (!sourceLayer?.feature || !resultLayer) {
        return;
      }

      const updatedFeature = layerToFeature(resultLayer, this.selectedYear);
      if (!updatedFeature) {
        return;
      }

      updatedFeature.id = sourceLayer.feature.id;
      updatedFeature.mapId = sourceLayer.feature.mapId;
      updatedFeature.type = sourceLayer.feature.type;
      updatedFeature.name = sourceLayer.feature.name;
      updatedFeature.createdAt = sourceLayer.feature.createdAt;
      updatedFeature.updatedAt = new Date().toISOString();
      updatedFeature.properties.opacity = sourceLayer.feature.properties.opacity ?? updatedFeature.properties.opacity;
      updatedFeature.properties.name = sourceLayer.feature.properties.name;
      updatedFeature.properties.labelText = sourceLayer.feature.properties.labelText;
      updatedFeature.properties.colorName = sourceLayer.feature.properties.colorName;
      updatedFeature.properties.colorRgb = sourceLayer.feature.properties.colorRgb;
      updatedFeature.properties.strokeColor = sourceLayer.feature.properties.strokeColor;
      updatedFeature.properties.strokeWidth = sourceLayer.feature.properties.strokeWidth;
      updatedFeature.properties.strokeOpacity = sourceLayer.feature.properties.strokeOpacity;
      updatedFeature.properties.mapElementType = sourceLayer.feature.properties.mapElementType;
      updatedFeature.properties.shapeKind = sourceLayer.feature.properties.shapeKind;
      updatedFeature.properties.startDate = sourceLayer.feature.properties.startDate;
      updatedFeature.properties.endDate = sourceLayer.feature.properties.endDate;

      resultLayer.feature = updatedFeature;
      this.emit("feature-updated", updatedFeature);

      setTimeout(() => {
        this.drawnItems.value?.removeLayer(resultLayer);

        if (map.hasLayer(resultLayer)) {
          map.removeLayer(resultLayer);
        }

        if (sourceLayer && map.hasLayer(sourceLayer)) {
          map.removeLayer(sourceLayer);
        }
      }, 0);
    });

    map.on("pm:remove", (e) => {
      const layer = (e as PmLayerEvent).layer as FeatureBearingLayer;
      const featureId = layer.feature?.id;

      if (featureId) {
        this.emit("feature-deleted", featureId);
      }
    });

    map.on("pm:globalremovalmodetoggled", (e) => {
      const removalEvent = e as unknown as PmRemovalToggleEvent;
      this.setBoxZoomForRemovalMode(map, removalEvent.enabled);

      if (removalEvent.enabled) {
        if (this.freehandActive) {
          this.stopFreehandDrawing(map);
        }

        this.enableRemovalLasso(map);
        return;
      }

      this.disableRemovalLasso(map);
    });

    this.setBoxZoomForRemovalMode(
      map,
      Boolean((map as MapWithPm).pm?.globalRemovalModeEnabled?.()),
    );

    map.on("pm:lasso-select", (e) => {
      if (!(map as MapWithPm).pm?.globalRemovalModeEnabled?.()) {
        return;
      }

      const lassoEvent = e as PmLassoSelectEvent;
      this.deleteLassoSelectedLayers(lassoEvent.selectedLayers || []);
    });

    map.on("pm:drawstart", (e) => {
      if (this.freehandActive) {
        this.stopFreehandDrawing(map);
      }
      const shape = (e as unknown as PmDrawStartEvent).shape;
      if (shape === "Cut") {
        this.isCuttingActive = true;
        this.emit("cut-started");
      }
      this.activeDrawingMode.value = shape as DrawingMode;
      map.dragging.disable();
    });

    map.on("pm:drawend", () => {
      map.dragging.enable();
      this.activeDrawingMode.value = null;
      // Defer the reset so that synchronous cut processing (pm:cut / pm:remove)
      // which fires inside pm:create after pm:drawend has a chance to complete
      // before we clear the flag.
      if (this.isCuttingActive) {
        setTimeout(() => {
          this.isCuttingActive = false;
          // Signal MapGeoJSON to finalise the cut: detect any zones that geoman
          // silently removed from the map (fully enclosed by the cut polygon)
          // and delete them, then re-render intersected zones with their new
          // geometry. Deferred so the Vue watcher echo cycle (suppressNextPropsRender)
          // has already flushed before we call renderAllFeatures.
          this.emit("cut-complete");
        }, 0);
      }
    });
  }

  setDrawingMode(mode: DrawingMode) {
    if (!this.pmMapInstance) return;

    if (this.freehandActive) {
      this.stopFreehandDrawing(this.pmMapInstance);
    }

    this.pmMapInstance.pm?.disableDraw();

    if (mode === null) {
      this.activeDrawingMode.value = null;
      this.pmMapInstance.dragging.enable();
      this.disableRemovalLasso(this.pmMapInstance);
      return;
    }

    if (mode === "freehand") {
      this.activeDrawingMode.value = mode;
      this.startFreehandDrawing(this.pmMapInstance);
      return;
    }

    const modeMap: Record<string, string> = {
      marker: "Marker",
      polyline: "Polyline",
      polygon: "Polygon",
      rectangle: "Rectangle",
      circle: "Circle",
    };

    this.pmMapInstance.pm?.enableDraw(modeMap[mode], {
      snappingOrder: ["vertex", "edge", "middleLatLng"],
    });

    this.activeDrawingMode.value = mode;
  }

  loadFeaturesForEditing(features: Feature[]) {
    if (!this.drawnItems.value) return;

    features.forEach((feature) => {
      const layer = featureToLayer(feature);
      if (layer) {
        (layer as FeatureBearingLayer).feature = feature;
        this.drawnItems.value?.addLayer(layer);
      }
    });
  }

  clearDrawnItems() {
    if (this.drawnItems.value) {
      this.drawnItems.value.clearLayers();
    }
  }

  setSelectedYear(selectedYear: number) {
    this.selectedYear = selectedYear;
  }

  setToolbarMode(mode: "global" | "feature") {
    if (!this.pmMapInstance?.pm) return;

    const pm = this.pmMapInstance.pm;
    const isFeatureMode = mode === "feature";

    pm.addControls({
      drawMarker: false,
      drawPolyline: !isFeatureMode,
      drawPolygon: !isFeatureMode,
      drawCircle: !isFeatureMode,
      drawRectangle: !isFeatureMode,
      drawCircleMarker: false,
      drawText: !isFeatureMode,
      editMode: isFeatureMode,
      dragMode: false,
      rotateMode: isFeatureMode,
      cutPolygon: !isFeatureMode,
      removalMode: !isFeatureMode,
      [freehandControlName]: !isFeatureMode,
      [addCityControlName]: !isFeatureMode,
    });

    if (isFeatureMode) {
      if (this.freehandActive) {
        this.stopFreehandDrawing(this.pmMapInstance);
      }
      pm.disableDraw();
    }
  } 

  getDrawnFeatures(): Feature[] {
    const features: Feature[] = [];

    if (this.drawnItems.value) {
      this.drawnItems.value.eachLayer((layer) => {
        const featureLayer = layer as FeatureBearingLayer;
        if (featureLayer.feature) {
          features.push(featureLayer.feature);
        }
      });
    }

    return features;
  }

  createDrawingTools() {
    return {
      activeDrawingMode: this.activeDrawingMode,
      drawnItems: this.drawnItems,
      initializeDrawing: this.initializeDrawing.bind(this),
      setDrawingMode: this.setDrawingMode.bind(this),
      loadFeaturesForEditing: this.loadFeaturesForEditing.bind(this),
      clearDrawnItems: this.clearDrawnItems.bind(this),
      setSelectedYear: this.setSelectedYear.bind(this),
      setToolbarMode: this.setToolbarMode.bind(this),
      getDrawnFeatures: this.getDrawnFeatures.bind(this),
      startFreehandDrawing: this.startFreehandDrawing.bind(this),
      stopFreehandDrawing: this.stopFreehandDrawing.bind(this),
      drawingModes,
    };
  }
}
