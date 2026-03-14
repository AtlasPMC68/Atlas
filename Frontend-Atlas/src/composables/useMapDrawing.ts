import { ref } from "vue";
import L from "leaflet";
import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";

type DrawingMode =
  | "marker"
  | "polyline"
  | "polygon"
  | "rectangle"
  | "circle"
  | "freehand"
  | null;
type EmitFn = (event: string, ...args: any[]) => void;

type Feature = {
  id?: string | number;
  type: string;
  geometry: {
    type: string;
    coordinates: any;
  };
  color?: string;
  opacity?: number;
  stroke_width?: number;
  properties?: Record<string, any>;
};

const DRAWING_MODES = {
  marker: "marker",
  polyline: "polyline",
  polygon: "polygon",
  rectangle: "rectangle",
  circle: "circle",
  freehand: "freehand",
} as const;

const FREEHAND_CONTROL_NAME = "drawFreehand";
const LASSO_DELETE_OPTIONS = {
  mode: "RESET",
  selectMode: "CONTAIN",
  lassoDrawOptions: {
    color: "#ef4444",
    weight: 2,
    dashArray: "6 6",
    fillColor: "#ef4444",
    fillOpacity: 0.12,
    dasharray: "6 6",
  },
} as const;

/**
 * Composable for handling map drawing with Leaflet.pm
 */
export function useMapDrawing(emit: EmitFn) {
  const activeDrawingMode = ref<DrawingMode>(null);
  const drawnItems = ref<L.FeatureGroup | null>(null);
  let pmMapInstance: any = null;
  let freehandActive = false;
  let freehandListeners: any = {};
  let removalLassoEnabled = false;
  let fallbackRemovalSelectionEnabled = false;
  let fallbackSelectionRectangle: L.Rectangle | null = null;
  let fallbackSelectionStart: L.LatLng | null = null;
  let fallbackSelectionDragging = false;
  let fallbackRemovalListeners: {
    onMouseDown?: (e: L.LeafletMouseEvent) => void;
    onMouseMove?: (e: L.LeafletMouseEvent) => void;
    onMouseUp?: () => void;
  } = {};

  /**
   * Initialize the drawing control
   */
  function initializeDrawing(map: L.Map) {
    if (!map.pm) {
      console.warn("Leaflet.pm not properly initialized");
      return;
    }

    pmMapInstance = map;
    drawnItems.value = new L.FeatureGroup();
    map.addLayer(drawnItems.value as any);

    // Initialize Leaflet.pm controls (standard tools)
    map.pm.addControls({
      position: "topleft",
      drawMarker: true,
      drawPolyline: true,
      drawPolygon: true,
      drawCircle: true,
      drawRectangle: true,
      drawCircleMarker: true,
      drawText: true,
      editMode: true,
      dragMode: true,
      rotateMode: true,
      cutPolygon: true,
      removalMode: true,
    });

    // Add freehand button to the toolbar
    addFreehandButton(map);

    // Setup event listeners for Leaflet.pm
    setupDrawingListeners(map);
  }

  /**
   * Add freehand button to the Leaflet.pm toolbar
   */
  function addFreehandButton(map: L.Map) {
    const toolbar = (map.pm as any)?.Toolbar;
    if (
      !toolbar?.createCustomControl ||
      toolbar.controlExists?.(FREEHAND_CONTROL_NAME)
    ) {
      return;
    }

    toolbar.createCustomControl({
      name: FREEHAND_CONTROL_NAME,
      block: "draw",
      title: "Draw Freehand Line",
      className: "leaflet-pm-icon-freehand",
      toggle: true,
      disableOtherButtons: true,
      disableByOtherButtons: true,
      actions: ["cancel"],
      onClick: () => {},
      afterClick: (_event: unknown, context: any) => {
        if (context.button.toggled()) {
          setDrawingMode("freehand");
          return;
        }

        setDrawingMode(null);
      },
    });

    toolbar.changeControlOrder?.();
  }

  /**
   * Start freehand drawing mode
   */
  function startFreehandDrawing(map: L.Map) {
    if (freehandActive) return;

    freehandActive = true;
    let isDrawing = false;
    let points: L.LatLng[] = [];
    let polyline: L.Polyline | null = null;

    // Disable map dragging during freehand drawing
    map.dragging.disable();
    map.getContainer().style.userSelect = "none";

    // Set pencil cursor (SVG-based)
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
        drawnItems.value?.addLayer(polyline);
        const feature = layerToFeature(polyline);
        if (feature) {
          (polyline as any).feature = feature;
          emit("feature-created", feature);
        }
      } else {
        map.removeLayer(polyline);
      }

      // Reset for next stroke but keep freehand mode active
      polyline = null;
      points = [];
    };

    freehandListeners = { onMouseDown, onMouseMove, onMouseUp };
    map.pm.disableDraw();

    map.on("mousedown", onMouseDown);
    map.on("mousemove", onMouseMove);
    map.on("mouseup", onMouseUp);
  }

  /**
   * Stop freehand drawing mode
   */
  function stopFreehandDrawing(map: L.Map) {
    if (!freehandActive) return;

    freehandActive = false;

    map.off("mousedown", freehandListeners.onMouseDown);
    map.off("mousemove", freehandListeners.onMouseMove);
    map.off("mouseup", freehandListeners.onMouseUp);

    map.dragging.enable();
    map.getContainer().style.cursor = "";
    map.getContainer().style.userSelect = "";
  }

  function enableRemovalLasso(map: L.Map) {
    if (removalLassoEnabled) {
      return;
    }

    if (map.pm?.enableGlobalLassoMode) {
      map.pm.enableGlobalLassoMode(LASSO_DELETE_OPTIONS);
      removalLassoEnabled = true;
      return;
    }

    enableFallbackRemovalSelection(map);
    removalLassoEnabled = true;
  }

  function disableRemovalLasso(map: L.Map) {
    if (!removalLassoEnabled) {
      return;
    }

    if (map.pm?.disableGlobalLassoMode) {
      map.pm.disableGlobalLassoMode();
    }

    disableFallbackRemovalSelection(map);
    removalLassoEnabled = false;
  }

  function getLayersInsideBounds(
    map: L.Map,
    bounds: L.LatLngBounds,
  ): L.Layer[] {
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

      if (!candidate.pm || candidate._pmTempLayer) {
        return;
      }

      if (candidate.pm.options?.allowRemoval === false) {
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

  function enableFallbackRemovalSelection(map: L.Map) {
    if (fallbackRemovalSelectionEnabled) {
      return;
    }

    const onMouseDown = (e: L.LeafletMouseEvent) => {
      if (!e.originalEvent?.shiftKey || !map.pm?.globalRemovalModeEnabled?.()) {
        return;
      }

      fallbackSelectionDragging = true;
      fallbackSelectionStart = e.latlng;
      map.dragging.disable();

      fallbackSelectionRectangle?.remove();
      const initialBounds = L.latLngBounds(e.latlng, e.latlng);
      fallbackSelectionRectangle = L.rectangle(initialBounds, {
        color: "#ef4444",
        weight: 2,
        fillColor: "#ef4444",
        fillOpacity: 0.12,
        dashArray: "6 6",
        interactive: false,
      }).addTo(map);
    };

    const onMouseMove = (e: L.LeafletMouseEvent) => {
      if (
        !fallbackSelectionDragging ||
        !fallbackSelectionStart ||
        !fallbackSelectionRectangle
      ) {
        return;
      }

      fallbackSelectionRectangle.setBounds(
        L.latLngBounds(fallbackSelectionStart, e.latlng),
      );
    };

    const onMouseUp = () => {
      if (!fallbackSelectionDragging || !fallbackSelectionRectangle) {
        return;
      }

      const bounds = fallbackSelectionRectangle.getBounds();
      fallbackSelectionRectangle.remove();
      fallbackSelectionRectangle = null;
      fallbackSelectionDragging = false;
      fallbackSelectionStart = null;
      map.dragging.enable();

      if (!map.pm?.globalRemovalModeEnabled?.()) {
        return;
      }

      const selectedLayers = getLayersInsideBounds(map, bounds);
      deleteLassoSelectedLayers(selectedLayers);
    };

    fallbackRemovalListeners = { onMouseDown, onMouseMove, onMouseUp };
    map.on("mousedown", onMouseDown);
    map.on("mousemove", onMouseMove);
    map.on("mouseup", onMouseUp);
    fallbackRemovalSelectionEnabled = true;
  }

  function disableFallbackRemovalSelection(map: L.Map) {
    if (!fallbackRemovalSelectionEnabled) {
      return;
    }

    if (fallbackRemovalListeners.onMouseDown) {
      map.off("mousedown", fallbackRemovalListeners.onMouseDown);
    }
    if (fallbackRemovalListeners.onMouseMove) {
      map.off("mousemove", fallbackRemovalListeners.onMouseMove);
    }
    if (fallbackRemovalListeners.onMouseUp) {
      map.off("mouseup", fallbackRemovalListeners.onMouseUp);
    }

    fallbackRemovalListeners = {};
    fallbackSelectionRectangle?.remove();
    fallbackSelectionRectangle = null;
    fallbackSelectionDragging = false;
    fallbackSelectionStart = null;
    map.dragging.enable();
    fallbackRemovalSelectionEnabled = false;
  }

  function deleteLassoSelectedLayers(layers: L.Layer[]) {
    layers.forEach((layer) => {
      const removableLayer = layer as L.Layer & {
        pm?: { remove?: () => void };
      };

      removableLayer.pm?.remove?.();
    });
  }

  /**
   * Setup listeners for drawing events
   */
  function setupDrawingListeners(map: L.Map) {
    // When a shape is created
    map.on("pm:create", (e) => {
      const layer = e.layer as any;
      const feature = layerToFeature(layer);

      if (feature) {
        // @ts-ignore - Layer type doesn't have feature property by default
        layer.feature = feature; // Attach feature to layer for later reference
        drawnItems.value?.addLayer(layer);
        emit("feature-created", feature);
      }
    });

    // When a shape is edited
    map.on("pm:edit", (e) => {
      const layer = e.layer as any;
      const feature = layerToFeature(layer);

      if (feature && (layer.feature as any)?.id) {
        feature.id = layer.feature.id;
        feature.properties = {
          ...(layer.feature?.properties || {}),
          ...(feature.properties || {}),
        };
        // @ts-ignore
        layer.feature = feature;
        emit("feature-updated", feature);
      }
    });

    // When a polygon is cut into one or more parts
    map.on("pm:cut", (e) => {
      const originalLayer = (e as any).originalLayer as any;
      const newLayer = (e as any).layer as any;

      if (originalLayer) {
        const updatedOriginal = layerToFeature(originalLayer);
        if (updatedOriginal && (originalLayer.feature as any)?.id) {
          updatedOriginal.id = originalLayer.feature.id;
          updatedOriginal.properties = {
            ...(originalLayer.feature?.properties || {}),
            ...(updatedOriginal.properties || {}),
          };
          // @ts-ignore
          originalLayer.feature = updatedOriginal;
          emit("feature-updated", updatedOriginal);
        }
      }

      if (newLayer) {
        const createdFeature = layerToFeature(newLayer);
        if (createdFeature) {
          const originalProps = originalLayer?.feature || {};
          createdFeature.color = originalProps.color ?? createdFeature.color;
          createdFeature.opacity =
            originalProps.opacity ?? createdFeature.opacity;
          createdFeature.stroke_width =
            originalProps.stroke_width ?? createdFeature.stroke_width;
          createdFeature.properties = {
            ...(originalProps.properties || {}),
            ...(createdFeature.properties || {}),
          };
          // @ts-ignore
          newLayer.feature = createdFeature;
          drawnItems.value?.addLayer(newLayer);
          emit("feature-created", createdFeature);
        }
      }
    });

    // When a shape is deleted
    map.on("pm:remove", (e) => {
      const layer = e.layer as any;
      const featureId = layer.feature?.id;

      if (featureId) {
        emit("feature-deleted", featureId);
      }
    });

    map.on("pm:globalremovalmodetoggled", (e: { enabled: boolean }) => {
      if (e.enabled) {
        if (freehandActive) {
          stopFreehandDrawing(map);
        }

        enableRemovalLasso(map);
        return;
      }

      disableRemovalLasso(map);
    });

    map.on("pm:lasso-select", (e: { selectedLayers: L.Layer[] }) => {
      if (!map.pm?.globalRemovalModeEnabled?.()) {
        return;
      }

      deleteLassoSelectedLayers(e.selectedLayers || []);
    });

    // When drawing starts
    map.on("pm:drawstart", (e) => {
      if (freehandActive) {
        stopFreehandDrawing(map);
      }
      activeDrawingMode.value = e.shape as DrawingMode;
      // Disable map dragging during drawing
      map.dragging.disable();
    });

    // When drawing ends
    map.on("pm:drawend", () => {
      // Re-enable map dragging
      map.dragging.enable();
      // Keep the mode active unless explicitly disabled
    });
  }

  /**
   * Convert a Leaflet layer to a GeoJSON Feature
   */
  function layerToFeature(layer: any): Feature | null {
    let geometry = null;
    let type = "polygon";

    // Determine shape type and extract coordinates
    if (layer instanceof L.CircleMarker && !(layer instanceof L.Circle)) {
      // Point/Marker
      const latlng = layer.getLatLng();
      geometry = {
        type: "Point",
        coordinates: [latlng.lng, latlng.lat],
      };
      type = "point";
    } else if (layer instanceof L.Circle) {
      // Circle - store as polygon approximation
      const center = layer.getLatLng();
      const radius = layer.getRadius();
      geometry = circleToPolygon(center, radius);
      type = "zone";
    } else if (layer instanceof L.Polyline && !(layer instanceof L.Polygon)) {
      // Polyline/Line
      const latlngs = layer.getLatLngs();
      geometry = {
        type: "LineString",
        coordinates: (latlngs as L.LatLng[]).map((ll) => [ll.lng, ll.lat]),
      };
      type = "polyline";
    } else if (layer instanceof L.Polygon || layer instanceof L.Rectangle) {
      // Polygon or Rectangle
      const latlngs = layer.getLatLngs() as any[];

      if (Array.isArray(latlngs) && latlngs.length > 0) {
        let ring = latlngs[0];

        // Handle nested arrays (multi-polygon case)
        if (Array.isArray(ring) && ring.length > 0 && "lat" in ring[0]) {
          ring = latlngs;
        }

        const coords = (ring as any as L.LatLng[]).map((ll) => [
          ll.lng,
          ll.lat,
        ]);

        // Close ring if not already closed
        if (coords.length > 0) {
          const first = coords[0];
          const last = coords[coords.length - 1];
          if (first[0] !== last[0] || first[1] !== last[1]) {
            coords.push(first);
          }
        }

        geometry = {
          type: "Polygon",
          coordinates: [coords],
        };
        type = "zone";
      }
    }

    if (!geometry) return null;

    return {
      type,
      geometry,
      color: "#000000",
      opacity: 0.5,
      stroke_width: 2,
      properties: {
        mapElementType: type,
      },
    };
  }

  /**
   * Convert a circle to polygon approximation
   */
  function circleToPolygon(
    center: L.LatLng,
    radiusMeters: number,
    steps: number = 32,
  ) {
    const coords: number[][] = [];
    const radiusLat = radiusMeters / 111320; // 1 degree latitude ≈ 111.32 km
    const radiusLng =
      radiusMeters / (111320 * Math.cos((center.lat * Math.PI) / 180));

    for (let i = 0; i < steps; i++) {
      const angle = (i / steps) * 2 * Math.PI;
      const lat = center.lat + radiusLat * Math.sin(angle);
      const lng = center.lng + radiusLng * Math.cos(angle);
      coords.push([lng, lat]);
    }

    // Close ring
    coords.push(coords[0]);

    return {
      type: "Polygon",
      coordinates: [coords],
    };
  }

  /**
   * Enable/disable a drawing mode
   */
  function setDrawingMode(mode: DrawingMode) {
    if (!pmMapInstance) return;

    // Stop freehand drawing if active
    if (freehandActive) {
      stopFreehandDrawing(pmMapInstance);
    }

    // Disable all modes first
    pmMapInstance.pm.disableDraw();

    if (mode === null) {
      activeDrawingMode.value = null;
      // Re-enable map dragging when exiting draw mode
      pmMapInstance.dragging.enable();
      disableRemovalLasso(pmMapInstance);
      return;
    }

    // Enable freehand mode
    if (mode === "freehand") {
      activeDrawingMode.value = mode;
      startFreehandDrawing(pmMapInstance);
      return;
    }

    // Enable the selected mode for Leaflet.pm
    const modeMap: Record<string, string> = {
      marker: "Marker",
      polyline: "Polyline",
      polygon: "Polygon",
      rectangle: "Rectangle",
      circle: "Circle",
    };

    pmMapInstance.pm.enableDraw(modeMap[mode], {
      snappingOrder: ["vertex", "edge", "middleLatLng"],
    });

    activeDrawingMode.value = mode;
  }

  /**
   * Load existing features to the map
   */
  function loadFeaturesForEditing(features: Feature[]) {
    if (!drawnItems.value) return;

    features.forEach((feature) => {
      const layer = featureToLayer(feature);
      if (layer) {
        // @ts-ignore - Layer type doesn't have feature property by default
        layer.feature = feature;
        drawnItems.value?.addLayer(layer);
      }
    });
  }

  /**
   * Convert a GeoJSON Feature to a Leaflet layer
   */
  function featureToLayer(feature: Feature): L.Layer | null {
    const geom = feature.geometry;

    if (!geom) return null;

    const style = {
      color: feature.color || "#000000",
      weight: feature.stroke_width || 2,
      fillColor: feature.color || "#cccccc",
      fillOpacity: feature.opacity || 0.5,
    };

    switch (geom.type) {
      case "Point": {
        const [lng, lat] = geom.coordinates;
        const marker = L.circleMarker([lat, lng], {
          ...style,
          radius: 6,
        });
        return marker;
      }

      case "LineString": {
        const latlngs = geom.coordinates.map(([lng, lat]: [number, number]) => [
          lat,
          lng,
        ]);
        return L.polyline(latlngs, style);
      }

      case "Polygon": {
        const coords = geom.coordinates[0];
        const latlngs = coords.map(([lng, lat]: [number, number]) => [
          lat,
          lng,
        ]);
        return L.polygon(latlngs, style);
      }

      default:
        return null;
    }
  }

  /**
   * Clear all drawn items
   */
  function clearDrawnItems() {
    if (drawnItems.value) {
      drawnItems.value.clearLayers();
    }
  }

  /**
   * Get all drawn features
   */
  function getDrawnFeatures(): Feature[] {
    const features: Feature[] = [];

    if (drawnItems.value) {
      drawnItems.value.eachLayer((layer: any) => {
        if (layer.feature) {
          features.push(layer.feature);
        }
      });
    }

    return features;
  }

  return {
    // State
    activeDrawingMode,
    drawnItems,

    // Methods
    initializeDrawing,
    setDrawingMode,
    loadFeaturesForEditing,
    clearDrawnItems,
    getDrawnFeatures,
    featureToLayer,
    layerToFeature,
    startFreehandDrawing,
    stopFreehandDrawing,

    // Constants
    DRAWING_MODES,
  };
}
