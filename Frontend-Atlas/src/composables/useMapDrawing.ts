import { ref } from "vue";
import L from "leaflet";
import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import "leaflet-draw";
import "leaflet-draw/dist/leaflet.draw.css";

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

/**
 * Composable for handling map drawing with Leaflet.pm
 */
export function useMapDrawing(emit: EmitFn) {
  const activeDrawingMode = ref<DrawingMode>(null);
  const drawnItems = ref<L.FeatureGroup | null>(null);
  let pmMapInstance: any = null;

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

    // Add Leaflet.Draw control for freehand drawing
    const drawControl = new L.Control.Draw({
      position: "topleft",
      draw: {
        polyline: false,
        polygon: false,
        circle: false,
        rectangle: false,
        marker: false,
        circlemarker: false,
      },
      edit: {
        featureGroup: drawnItems.value as L.FeatureGroup,
        edit: false,
        remove: false,
      },
    });

    // Manually add freehand button
    addFreehandButton(map);

    // Setup event listeners for both libraries
    setupDrawingListeners(map);
    setupLeafletDrawListeners(map);
  }

  /**
   * Add custom freehand drawing button
   */
  function addFreehandButton(map: L.Map) {
    const FreehandControl = L.Control.extend({
      options: {
        position: "topleft",
      },
      onAdd: function () {
        const container = L.DomUtil.create(
          "div",
          "leaflet-bar leaflet-control",
        );
        const button = L.DomUtil.create(
          "a",
          "leaflet-draw-freehand",
          container,
        );
        button.href = "#";
        button.title = "Draw Freehand Line";
        button.style.display = "flex";
        button.style.alignItems = "center";
        button.style.justifyContent = "center";

        // Add SVG icon - pencil for freehand drawing
        button.innerHTML = `
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25Z"/>
            <path d="M20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83Z"/>
          </svg>
        `;

        L.DomEvent.on(button, "click", (e) => {
          L.DomEvent.stopPropagation(e);
          L.DomEvent.preventDefault(e);
          startFreehandDrawing(map);
        });

        return container;
      },
    });

    map.addControl(new FreehandControl());
  }

  /**
   * Start freehand drawing mode
   */
  function startFreehandDrawing(map: L.Map) {
    let isDrawing = false;
    let points: L.LatLng[] = [];
    let polyline: L.Polyline | null = null;

    // Disable map dragging during freehand drawing
    map.dragging.disable();

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

      // Keep as polyline (continuous line with start and end)
      if (points.length > 1) {
        // Keep the polyline as is - don't convert to polygon
        drawnItems.value?.addLayer(polyline);

        const feature = layerToFeature(polyline);
        if (feature) {
          (polyline as any).feature = feature;
          emit("feature-created", feature);
        }
      } else {
        // Remove if not enough points
        map.removeLayer(polyline);
      }

      // Clean up listeners
      map.off("mousedown", onMouseDown);
      map.off("mousemove", onMouseMove);
      map.off("mouseup", onMouseUp);
      map.getContainer().style.cursor = "";

      // Re-enable map dragging
      map.dragging.enable();
    };

    // Disable pm to avoid conflicts
    map.pm.disableDraw();

    // Set cursor
    map.getContainer().style.cursor = "crosshair";

    // Attach listeners
    map.on("mousedown", onMouseDown);
    map.on("mousemove", onMouseMove);
    map.on("mouseup", onMouseUp);
  }

  /**
   * Setup listeners for Leaflet.Draw events
   */
  function setupLeafletDrawListeners(map: L.Map) {
    map.on(L.Draw.Event.CREATED, (e: any) => {
      const layer = e.layer;
      const feature = layerToFeature(layer);

      if (feature) {
        (layer as any).feature = feature;
        drawnItems.value?.addLayer(layer);
        emit("feature-created", feature);
      }
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

    // When drawing starts
    map.on("pm:drawstart", (e) => {
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

    // Disable all modes first
    pmMapInstance.pm.disableDraw();

    if (mode === null) {
      activeDrawingMode.value = null;
      // Re-enable map dragging when exiting draw mode
      pmMapInstance.dragging.enable();
      return;
    }

    // Enable the selected mode
    const modeMap: Record<string, string> = {
      marker: "Marker",
      polyline: "Polyline",
      polygon: "Polygon",
      rectangle: "Rectangle",
      circle: "Circle",
      freehand: "Freehand",
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

    // Constants
    DRAWING_MODES,
  };
}
