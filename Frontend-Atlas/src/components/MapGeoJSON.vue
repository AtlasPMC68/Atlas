<template>
  <div class="relative h-full w-full z-0">
    <div id="map" style="height: 80vh; width: 100%"></div>
    <TimelineSlider v-model:year="selectedYear" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch, ref, computed } from "vue";
import L from "leaflet";
import "leaflet-geometryutil";
import "leaflet-arrowheads";
import TimelineSlider from "../components/TimelineSlider.vue";
import { useMapDrawing } from "../composables/useMapDrawing";
import { colorRgbToCss, getMapElementType } from "../utils/featureHelpers";
import {
  extractFeatureFromLayer,
  syncFeaturesFromLayerMap,
} from "../utils/mapDrawingFeature";
import {
  attachFeatureToLayer,
  bindRenderedFeatureEvents,
} from "../utils/mapLayersFeature";
import { toArray, toImageSrc } from "../utils/utils";
import type {
  Coordinate,
  Feature,
  Geometry,
  FeatureId,
} from "../typescript/feature";
import type { AtlasRuntimeLayer } from "../typescript/mapLayers";
import type { MapWithPm, PmIgnoreOptions } from "../typescript/mapDrawing";

interface GeoJsonFeatureWithGeometry {
  geometry: Geometry;
  [key: string]: unknown;
}

interface GeoJsonFeatureCollectionWithGeometry {
  features: GeoJsonFeatureWithGeometry[];
  [key: string]: unknown;
}

const props = defineProps<{
  features: Feature[];
  featureVisibility: Map<string, boolean>;
}>();

const emit = defineEmits<{
  (e: "features-loaded", features: Feature[]): void;
  (e: "draw-create", features: Feature[]): void;
  (e: "draw-update", features: Feature[]): void;
  (e: "draw-delete", features: Feature[]): void; // Delete the Leaflet layer (unsaved feature)
  (e: "draw-delete-id", featureId: string): void; // Delete the db feature (saved feature with id)
  (e: "map-ready", map: L.Map): void;
}>();

const selectedYear = ref(1740);
const previousFeatureIds = ref(new Set<FeatureId>());
const localFeaturesSnapshot = ref<Feature[]>([]);

function getYearSafeUTC(dateText: string): number {
  return new Date(dateText).getUTCFullYear();
}

const filteredFeatures = computed(() => {
  return localFeaturesSnapshot.value.filter(
    (feature: Feature) =>
      getYearSafeUTC(feature.properties.startDate) <= selectedYear.value &&
      (!feature.properties.endDate ||
        getYearSafeUTC(feature.properties.endDate) >= selectedYear.value),
  );
});

let map: L.Map | null = null;
let vectorRenderer: L.Canvas | null = null;
let suppressNextPropsRender = false;
let blockNextMapClick = false;
let selectedLayerOriginalColor: string | undefined = undefined;
let escapeKeyHandler: ((e: KeyboardEvent) => void) | null = null;

const selectedFeatureId = ref<string | null>(null);

const featureLayerManager = {
  layers: new Map<FeatureId, L.Layer>(),

  addFeatureLayer(featureId: string | number, layer: L.Layer) {
    const id = String(featureId);
    if (!map) return;

    if (this.layers.has(id)) {
      map.removeLayer(this.layers.get(id)!);
    }
    this.layers.set(id, layer);

    layer.on("click", (e: L.LeafletEvent) => {
      (e as L.LeafletMouseEvent).originalEvent?.stopPropagation();
      // In canvas mode, Leaflet fires the layer click AND the map click as two
      // separate events from the same mouse event. Without this flag, the map
      // click handler would immediately deselect what we just selected.
      blockNextMapClick = true;
      selectedFeatureId.value = id;
    });

    const isVisible = props.featureVisibility.get(id) ?? true;
    if (isVisible) {
      map.addLayer(layer);
    }
  },

  toggleFeature(featureId: string | number, visible: boolean) {
    const id = String(featureId);
    const layer = this.layers.get(id);
    if (!layer || !map) return;

    if (visible) {
      // If any global edit mode is active, geoman's layeradd listener would
      // immediately enable that mode on this layer. Which is not good
      // for feature specific edit modes like edit layers and rotate
      // so we temporarily set pmIgnore to true on this layer (and all its children)
      // before adding it to the map, then restore pmIgnore to its original value.
      const pm = (map as MapWithPm).pm;
      const anyModeActive =
        pm?.globalEditModeEnabled?.() ||
        pm?.globalRotateModeEnabled?.();

      const setIgnoreDeep = (l: L.Layer, value: boolean | undefined) => {
        const opts = l.options as PmIgnoreOptions;
        if (value === undefined) delete opts.pmIgnore;
        else opts.pmIgnore = value;
        if (l instanceof L.LayerGroup) {
          (l as L.LayerGroup).eachLayer((child) => setIgnoreDeep(child, value));
        }
      };

      if (anyModeActive) setIgnoreDeep(layer, true);
      map.addLayer(layer);
      if (anyModeActive) setIgnoreDeep(layer, undefined);
    } else {
      map.removeLayer(layer);
    }
  },

  clearAllFeatures() {
    if (!map) return;
    this.layers.forEach((layer) => map!.removeLayer(layer));
    this.layers.clear();
  },
};

function upsertFeature(features: Feature[], feature: Feature): Feature[] {
  const targetId = feature.id;
  const next = [...features];
  const index = next.findIndex((f) => f.id === targetId);

  if (index >= 0) {
    next[index] = feature;
    return next;
  }

  next.push(feature);
  return next;
}

function applyLayerUpdate(layer: L.Layer) {
  const runtimeLayer = layer as AtlasRuntimeLayer;

  if (runtimeLayer.__atlasApplyingSync) return;
  runtimeLayer.__atlasApplyingSync = true;

  try {
    const extracted = extractFeatureFromLayer(layer, selectedYear.value);
    if (!extracted) return;

    attachFeatureToLayer(layer, extracted);

    const next = upsertFeature(localFeaturesSnapshot.value, extracted);
    localFeaturesSnapshot.value = next;
    suppressNextPropsRender = true;
    emit("draw-update", next);
  } finally {
    runtimeLayer.__atlasApplyingSync = false;
  }
}

function syncFeaturesFromMapLayers(): Feature[] {
  const mergedById = new Map<string, Feature>();

  const renderedFeatures = syncFeaturesFromLayerMap(
    featureLayerManager.layers,
    localFeaturesSnapshot.value,
    selectedYear.value,
  );

  renderedFeatures.forEach((feature) => {
    mergedById.set(String(feature.id), feature);
  });

  drawing.drawnItems.value?.eachLayer((layer) => {
    const extracted = extractFeatureFromLayer(layer, selectedYear.value);
    if (!extracted?.id) return;
    mergedById.set(String(extracted.id), extracted);
  });

  return Array.from(mergedById.values());
}

function clearDraftLayers() {
  drawing.clearDrawnItems();
}

defineExpose({
  syncFeaturesFromMapLayers,
  clearDraftLayers,
});

const drawing = useMapDrawing((event, ...args) => {
  const current = localFeaturesSnapshot.value;

  if (event === "feature-created") {
    const payload = args[0] as Feature;
    const next = upsertFeature(current, payload);
    localFeaturesSnapshot.value = next;
    emit("draw-create", next);
    return;
  }

  if (event === "feature-updated") {
    const payload = args[0] as Feature;
    const next = upsertFeature(current, payload);
    localFeaturesSnapshot.value = next;
    suppressNextPropsRender = true;
    emit("draw-update", next);
    return;
  }

  if (event === "feature-deleted") {
    const deletedId = String(args[0]);
    const next = current.filter(
      (feature) => String(feature.id) !== deletedId,
    );
    localFeaturesSnapshot.value = next;
    emit("draw-delete", next);
    emit("draw-delete-id", deletedId);
    return;
  }
});

function renderCities(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || feature.geometry.type !== "Point") return;

    const [lng, lat] = feature.geometry.coordinates;
    const coord: L.LatLngTuple = [lat, lng];

    const fillColor = colorRgbToCss(feature.properties.colorRgb) || "#000000";
    const strokeColor = colorRgbToCss(feature.properties.strokeColor) || fillColor;

    const point = L.circleMarker(coord, {
      radius: 6,
      fillColor: fillColor,
      color: strokeColor,
      weight: feature.properties.strokeWidth ?? 1,
      opacity: feature.properties.strokeOpacity ?? 1,
      fillOpacity: feature.properties.opacity ?? 0.5,
    });

    const featureProperties = feature.properties;
    const label = L.marker(coord, {
      icon: L.divIcon({
        className: "city-label-text",
        html: featureProperties.name || feature.name || "",
        iconSize: [100, 20],
        iconAnchor: [-8, 15],
      }),
      interactive: false,
    });

    attachFeatureToLayer(point, feature);
    bindRenderedFeatureEvents(point, applyLayerUpdate);

    attachFeatureToLayer(label, feature);

    const layerGroup = L.layerGroup([point, label]);
    attachFeatureToLayer(layerGroup, feature);
    featureLayerManager.addFeatureLayer(feature.id, layerGroup);
  });
}

function renderLabels(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || feature.geometry.type !== "Point") return;

    const [lng, lat] = feature.geometry.coordinates;
    const coord: L.LatLngTuple = [lat, lng];

    const labelText = feature.properties.labelText || "";

    const label = L.marker(coord, {
      icon: L.divIcon({
        className: "city-label-text geoman-text-label",
        html: labelText,
        iconSize: [120, 20],
        iconAnchor: [0, 10],
      }),
    });

    const textMarker = label as L.Marker & {
      options: L.MarkerOptions & { text: string; textMarker?: boolean };
    };
    textMarker.options.text = labelText;
    textMarker.options.textMarker = true;

    attachFeatureToLayer(label, feature);
    bindRenderedFeatureEvents(label, applyLayerUpdate);
    featureLayerManager.addFeatureLayer(feature.id, label);
  });
}

function transformCoord(
  coord: Coordinate,
  anchorLat: number,
  anchorLng: number,
  sizeMeters: number,
): Coordinate {
  const [x, y] = coord;
  const crs = L.CRS.EPSG3857;
  const center = crs.project(L.latLng(anchorLat, anchorLng));
  const halfSize = sizeMeters / 2;

  const nx = x - 0.5;
  const ny = y - 0.5;

  const mx = center.x + nx * 2 * halfSize;
  const my = center.y - ny * 2 * halfSize;

  const latLng = crs.unproject(L.point(mx, my));
  return [latLng.lng, latLng.lat];
}

function transformCoordinates(
  coordinates: Geometry["coordinates"],
  anchorLat: number,
  anchorLng: number,
  sizeMeters: number,
): Geometry["coordinates"] {
  if (!Array.isArray(coordinates)) return coordinates;

  if (
    coordinates.length > 0 &&
    typeof coordinates[0] === "number" &&
    typeof coordinates[1] === "number"
  ) {
    return transformCoord(
      coordinates as Coordinate,
      anchorLat,
      anchorLng,
      sizeMeters,
    );
  }

  return (coordinates as Array<Geometry["coordinates"]>).map((nested) =>
    transformCoordinates(nested, anchorLat, anchorLng, sizeMeters),
  ) as Geometry["coordinates"];
}

function renderZones(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map) return;
    if (
      feature.geometry.type !== "Polygon" &&
      feature.geometry.type !== "MultiPolygon"
    ) {
      return;
    }

    const featureProperties = feature.properties;
    const fillColor = colorRgbToCss(feature.properties.colorRgb) || "#000000";
    const strokeColor = colorRgbToCss(feature.properties.strokeColor) || fillColor;

    const layer = L.geoJSON(feature.geometry, {
      style: {
        renderer: vectorRenderer ?? undefined,
        fillColor,
        fillOpacity: 0.5,
        color: strokeColor || fillColor,
        weight: featureProperties.strokeWidth || 1,
        opacity: featureProperties.strokeOpacity ?? 1,
      },
    });

    attachFeatureToLayer(layer, feature);
    bindRenderedFeatureEvents(layer, applyLayerUpdate);

    const name = featureProperties.name || feature.name;
    if (name) {
      layer.bindPopup(name);
    }

    featureLayerManager.addFeatureLayer(feature.id, layer);
  });
}

function renderArrows(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || feature.geometry.type !== "LineString") return;

    const latLngs = feature.geometry.coordinates.map(
      ([lng, lat]) => [lat, lng] as L.LatLngTuple,
    );

    const fillColor = colorRgbToCss(feature.properties.colorRgb) || "#000000";
    const strokeColor = colorRgbToCss(feature.properties.strokeColor) || fillColor;

    const line = L.polyline(latLngs, {
      renderer: vectorRenderer ?? undefined,
      color: strokeColor,
      weight: feature.properties.strokeWidth ?? 2,
      opacity: feature.properties.strokeOpacity ?? 1,
    });

    attachFeatureToLayer(line, feature);
    bindRenderedFeatureEvents(line, applyLayerUpdate);

    line.addTo(map);
    line.arrowheads({
      size: "10px",
      frequency: "endonly",
      fill: true,
    });

    const featureProperties = feature.properties;
    const name = featureProperties.name || feature.name;
    if (name) {
      line.bindPopup(name);
    }

    featureLayerManager.addFeatureLayer(feature.id, line);
  });
}

function renderPolylines(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || feature.geometry.type !== "LineString") return;

    const latLngs = feature.geometry.coordinates.map(
      ([lng, lat]) => [lat, lng] as L.LatLngTuple,
    );

    const fillColor = colorRgbToCss(feature.properties.colorRgb) || "#000000";
    const strokeColor = colorRgbToCss(feature.properties.strokeColor) || fillColor;

    const line = L.polyline(latLngs, {
      color: strokeColor,
      weight: feature.properties.strokeWidth ?? 2,
      opacity: feature.properties.strokeOpacity ?? 1,
    });

    attachFeatureToLayer(line, feature);
    bindRenderedFeatureEvents(line, applyLayerUpdate);

    const featureProperties = feature.properties;
    const name = featureProperties.name || feature.name;
    if (name) {
      line.bindPopup(name);
    }

    featureLayerManager.addFeatureLayer(feature.id, line);
  });
}

function renderShapes(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map) return;
    if (
      feature.geometry.type !== "Polygon" &&
      feature.geometry.type !== "MultiPolygon"
    ) {
      return;
    }

    const featureProperties = feature.properties;
    const fillColor = colorRgbToCss(feature.properties.colorRgb) || "#000000";
    const strokeColor = colorRgbToCss(feature.properties.strokeColor) || fillColor;


    const layer = L.geoJSON(feature.geometry, {
      style: {
        renderer: vectorRenderer ?? undefined,
        fillColor: fillColor,
        opacity: feature.properties.strokeOpacity ?? 1,
        fillOpacity: feature.properties.strokeOpacity ?? 1,
        color: strokeColor,
        weight: feature.properties.strokeWidth || 1,
      },
    });

    attachFeatureToLayer(layer, feature);
    bindRenderedFeatureEvents(layer, applyLayerUpdate);

    const name = featureProperties.name || feature.name || "Detected shape";
    if (name) {
      layer.bindPopup(name);
    }

    featureLayerManager.addFeatureLayer(feature.id, layer);
  });
}

function renderImages(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || !feature.image) return;

    const bounds = feature.properties?.bounds as [[0, 0], [0, 0]] | undefined;

    if (!bounds) return;

    const src = toImageSrc(feature.image);
    const overlay = L.imageOverlay(src, bounds, {
      opacity: feature.properties.opacity ?? 1,
      interactive: true,
    });

    attachFeatureToLayer(overlay, feature);
    featureLayerManager.addFeatureLayer(feature.id, overlay);
  });
}

function renderAllFeatures() {
  if (!map) return;

  const currentFeatures = filteredFeatures.value;
  const currentIds = new Set(currentFeatures.map((f) => String(f.id)));
  const previousIds = previousFeatureIds.value;

  previousIds.forEach((oldId) => {
    if (!currentIds.has(oldId)) {
      const layer = featureLayerManager.layers.get(oldId);
      if (layer) {
        map!.removeLayer(layer);
        featureLayerManager.layers.delete(oldId);
      }
    }
  });

  const featuresByType = {
    point: currentFeatures.filter((f) => getMapElementType(f) === "point"),
    zone: currentFeatures.filter((f) => getMapElementType(f) === "zone"),
    arrow: currentFeatures.filter((f) => getMapElementType(f) === "arrow"),
    shape: currentFeatures.filter((f) => getMapElementType(f) === "shape"),
    label: currentFeatures.filter((f) => getMapElementType(f) === "label"),
    polyline: currentFeatures.filter(
      (f) => getMapElementType(f) === "polyline",
    ),
    image: currentFeatures.filter((f) => getMapElementType(f) === "image"),
  };

  renderCities(featuresByType.point);
  renderLabels(featuresByType.label);
  renderZones(featuresByType.zone);
  renderArrows(featuresByType.arrow);
  renderPolylines(featuresByType.polyline);
  renderShapes(featuresByType.shape);
  renderImages(featuresByType.image);

  previousFeatureIds.value = currentIds;
  emit("features-loaded", currentFeatures);
}

function applyStyleToLayer(layer: L.Layer, style: L.PathOptions) {
  if (layer instanceof L.LayerGroup) {
    layer.eachLayer((child) => applyStyleToLayer(child, style));
  } else if (layer instanceof L.Path) {
    layer.setStyle(style);
  }
}

function getLayerStrokeColor(layer: L.Layer): string | undefined {
  if (layer instanceof L.LayerGroup) {
    let color: string | undefined;
    layer.eachLayer((child) => { color ??= getLayerStrokeColor(child); });
    return color;
  } else if (layer instanceof L.Path) {
    return layer.options.color;
  }
  return undefined;
}

onMounted(() => {
  map = L.map("map", { zoomControl: false, preferCanvas: true, doubleClickZoom: false }).setView(
    [52.9399, -73.5491],
    5,
  );
  vectorRenderer = L.canvas({ padding: 0.5 });
  // Make all path layers (including geoman's temp drawing layers) use the
  // same canvas renderer. Without this, geoman creates a second <canvas>
  // element that sits on top of vectorRenderer's canvas in the DOM, causing
  // it to capture all mouse events and breaking hover/click on our features.
  (map.options as Record<string, unknown>).renderer = vectorRenderer;

  L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
    {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 19,
    },
  ).addTo(map);

  drawing.initializeDrawing(map);
  drawing.setToolbarMode("global");
  
  // pmIgnore values saved before edit/rotate mode is enabled, restored after.
  // This makes geoman only process the selected feature (O(1)) instead of every layer.
  const savedPmIgnore = new Map<L.Layer, boolean | undefined>();

  const restorePmIgnore = () => {
    savedPmIgnore.forEach((original, layer) => {
      const opts = layer.options as PmIgnoreOptions;
      if (original === undefined) {
        delete opts.pmIgnore;
      } else {
        opts.pmIgnore = original;
      }
    });
    savedPmIgnore.clear();
  };

  map.on("pm:buttonclick", (e) => {
    const { btnName } = e as unknown as { btnName: string };
    const pm = (map as MapWithPm).pm;

    // Only intercept the turn-ON click for edit and rotate modes.
    if (btnName === "editMode" && pm?.globalEditModeEnabled?.()) return;
    if (btnName === "rotateMode" && pm?.globalRotateModeEnabled?.()) return;
    if (btnName !== "editMode" && btnName !== "rotateMode") return;
    if (!selectedFeatureId.value) return;

    const selectedLayer = featureLayerManager.layers.get(selectedFeatureId.value);
    const selectedLayers = new Set<L.Layer>();
    const addLayersDeep = (l: L.Layer) => {
      selectedLayers.add(l);
      if (l instanceof L.LayerGroup) {
        (l as L.LayerGroup).eachLayer(addLayersDeep);
      }
    };
    if (selectedLayer) addLayersDeep(selectedLayer);

    // Set pmIgnore on every non-selected layer so geoman's findLayers()
    // skips them when enabling the mode.
    savedPmIgnore.clear();
    map!.eachLayer((l) => {
      if (selectedLayers.has(l)) return;
      const opts = l.options as PmIgnoreOptions;
      savedPmIgnore.set(l, opts.pmIgnore);
      opts.pmIgnore = true;
    });
  });

  map.on("pm:globaleditmodetoggled", restorePmIgnore);
  map.on("pm:globalrotatemodetoggled", restorePmIgnore);

  map.on("click", () => {
    if (blockNextMapClick) {
      blockNextMapClick = false;
      return;
    }
    selectedFeatureId.value = null;
  });

  L.control
    .scale({ position: "bottomright", metric: true, imperial: false })
    .addTo(map);

  L.control.zoom({ position: "topleft" }).addTo(map);

  drawing.setSelectedYear(selectedYear.value);
  emit("map-ready", map);
  renderAllFeatures();

  escapeKeyHandler = (e: KeyboardEvent) => {
    if (e.key !== "Escape" || !map) return;
    const pm = (map as MapWithPm).pm;
    // Cancel active freehand drawing — also untoggle the custom toolbar button
    if (drawing.activeDrawingMode.value === "freehand") {
      drawing.stopFreehandDrawing(map);
      drawing.activeDrawingMode.value = null;
      pm?.Toolbar?.toggleButton?.("drawFreehand", false);
      return;
    }
    // Cancel active regular draw mode
    if (drawing.activeDrawingMode.value !== null) {
      pm?.disableDraw();
      return;
    }
    // Cancel active global removal mode
    if (pm?.globalRemovalModeEnabled?.()) { pm.disableGlobalRemovalMode?.(); return; }
    // Cancel active global edit/rotate/drag mode
    if (pm?.globalEditModeEnabled?.()) { pm.disableGlobalEditMode?.(); return; }
    if (pm?.globalRotateModeEnabled?.()) { pm.disableGlobalRotateMode?.(); return; }
    if (pm?.globalDragModeEnabled?.()) { pm.disableGlobalDragMode?.(); return; }
  };
  document.addEventListener("keydown", escapeKeyHandler);
});

onBeforeUnmount(() => {
  if (escapeKeyHandler) {
    document.removeEventListener("keydown", escapeKeyHandler);
    escapeKeyHandler = null;
  }
  if (map) {
    featureLayerManager.clearAllFeatures();
    map.remove();
    map = null;
  }
});

watch(selectedYear, (newYear) => {
  drawing.setSelectedYear(newYear);
  void newYear;
  if (!map) return;
  renderAllFeatures();
});

watch(
  () => props.features,
  (newFeatures) => {
    localFeaturesSnapshot.value = [...newFeatures];
    if (suppressNextPropsRender) {
      suppressNextPropsRender = false;
      return;
    }
    if (!map) return;
    renderAllFeatures();
  },
  { deep: true },
);

localFeaturesSnapshot.value = [...props.features];

watch(selectedFeatureId, (id, oldId) => {
  // Restore the original stroke color on the previously selected layer
  if (oldId != null) {
    const oldLayer = featureLayerManager.layers.get(String(oldId));
    if (oldLayer !== undefined && selectedLayerOriginalColor !== undefined) {
      applyStyleToLayer(oldLayer, { color: selectedLayerOriginalColor });
    }
    selectedLayerOriginalColor = undefined;
  }

  drawing.setToolbarMode(id ? "feature" : "global");

  if (id != null) {
    const layer = featureLayerManager.layers.get(String(id));
    if (layer) {
      selectedLayerOriginalColor = getLayerStrokeColor(layer);
      applyStyleToLayer(layer, { color: "#000000" });
    }
  }

  if (!id && map) {
    const pm = (map as MapWithPm).pm;
    if (pm?.globalEditModeEnabled?.()) pm.disableGlobalEditMode?.();
    if (pm?.globalRotateModeEnabled?.()) pm.disableGlobalRotateMode?.();
    if (pm?.globalDragModeEnabled?.()) pm.disableGlobalDragMode?.();
  }
});

watch(
  () => props.featureVisibility,
  (newVisibility) => {
    newVisibility.forEach((visible, featureId) => {
      featureLayerManager.toggleFeature(featureId, visible);
    });
  },
  { deep: true },
);
</script>

<style>
.city-label-text {
  font-size: 12px;
  font-weight: bold;
  color: black;
  background: transparent;
  padding: 2px 4px;
  border-radius: 3px;
  border: transparent;
}

.arrow-head {
  font-size: 20px;
  color: black;
  transform: rotate(0deg);
}
</style>
