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

    // Initialize pm - with editMode, dragMode disabled at start
    // to prevent conflicts with layers. Users can enable via toolbar buttons.
    map.pm.addControls({
      position: "topleft",
      drawMarker: true,
      drawPolyline: true,
      drawPolygon: true,
      drawCircle: true,
      drawRectangle: true,
      drawFreehand: true,
      editMode: true,
      dragMode: true,
      rotateMode: true,
      cutPolygon: false,
      removalMode: true,
    });

    // Setup event listeners
    setupDrawingListeners(map);
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
        // @ts-ignore
        layer.feature = feature;
        emit("feature-updated", feature);
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
    });

    // When drawing ends
    map.on("pm:drawend", () => {
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
