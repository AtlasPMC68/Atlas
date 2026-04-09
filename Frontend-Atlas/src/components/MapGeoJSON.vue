<template>
  <div class="relative h-full w-full z-0">
    <div id="map" class="h-full w-full"></div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch, ref, nextTick } from "vue";
import L from "leaflet";
import "leaflet-geometryutil";
import "leaflet-arrowheads";
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
import type { MapWithPm } from "../typescript/mapDrawing";

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
  projectId: string;
  selectedYear: number;
  canUndo: boolean;
  canRedo: boolean;
}>();

const emit = defineEmits<{
  (e: "draw-create", features: Feature[]): void;
  (e: "draw-update", features: Feature[]): void;
  (e: "draw-delete", features: Feature[]): void; // Delete the Leaflet layer (unsaved feature)
  (e: "map-ready", map: L.Map): void;
  (e: "undo"): void;
  (e: "redo"): void;
}>();

const previousFeatureIds = ref(new Set<FeatureId>());
const localFeaturesSnapshot = ref<Feature[]>([]);

let map: L.Map | null = null;
let vectorRenderer: L.Canvas | null = null;

const undoControlName = "atlasUndo";
const redoControlName = "atlasRedo";
const undoControlClass = "leaflet-pm-icon-atlas-undo";
const redoControlClass = "leaflet-pm-icon-atlas-redo";

function setToolbarButtonEnabled(className: string, enabled: boolean) {
  document.querySelectorAll<HTMLElement>(`.${className}`).forEach((el) => {
    el.classList.toggle("leaflet-pm-control-disabled", !enabled);
    el.setAttribute("aria-disabled", String(!enabled));
    el.tabIndex = enabled ? 0 : -1;
  });
}

function updateHistoryToolbarState() {
  setToolbarButtonEnabled(undoControlClass, props.canUndo);
  setToolbarButtonEnabled(redoControlClass, props.canRedo);
}

function addUndoRedoControls(mapInstance: L.Map) {
  const toolbar = (mapInstance as MapWithPm).pm?.Toolbar;

  if (!toolbar?.createCustomControl) {
    return;
  }

  if (!toolbar.controlExists?.(undoControlName)) {
    toolbar.createCustomControl({
      name: undoControlName,
      block: "custom",
      title: "Annuler",
      className: undoControlClass,
      toggle: false,
      onClick: () => {
        if (!props.canUndo) return;
        emit("undo");
      },
    });
  }

  if (!toolbar.controlExists?.(redoControlName)) {
    toolbar.createCustomControl({
      name: redoControlName,
      block: "custom",
      title: "Rétablir",
      className: redoControlClass,
      toggle: false,
      onClick: () => {
        if (!props.canRedo) return;
        emit("redo");
      },
    });
  }

  toolbar.setBlockPosition?.("custom", "topleft");
  toolbar.changeControlOrder?.([undoControlName, redoControlName]);

  updateHistoryToolbarState();
}

const featureLayerManager = {
  layers: new Map<FeatureId, L.Layer>(),

  addFeatureLayer(featureId: string | number, layer: L.Layer) {
    const id = String(featureId);
    if (!map) return;

    if (this.layers.has(id)) {
      map.removeLayer(this.layers.get(id)!);
    }
    this.layers.set(id, layer);

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
      map.addLayer(layer);
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
    const extracted = extractFeatureFromLayer(
      layer,
      props.selectedYear,
      props.projectId,
    );
    if (!extracted) return;

    attachFeatureToLayer(layer, extracted);

    const next = upsertFeature(localFeaturesSnapshot.value, extracted);
    localFeaturesSnapshot.value = next;
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
    props.selectedYear,
    props.projectId,
  );

  renderedFeatures.forEach((feature) => {
    mergedById.set(String(feature.id), feature);
  });

  drawing.drawnItems.value?.eachLayer((layer) => {
    const extracted = extractFeatureFromLayer(
      layer,
      props.selectedYear,
      props.projectId,
    );
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

const drawing = useMapDrawing(
  (event, ...args) => {
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
      return;
    }
  },
  () => props.projectId,
);

function renderCities(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || feature.geometry.type !== "Point") return;

    const [lng, lat] = feature.geometry.coordinates;
    const coord: L.LatLngTuple = [lat, lng];

    const fillColor = colorRgbToCss(feature.properties.colorRgb) || "#000000";
    const strokeColor =
      colorRgbToCss(feature.properties.strokeColor) || fillColor;

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

function applyLabelStyle(marker: L.Marker, feature: Feature) {
  const el = marker.getElement() as HTMLElement | null;
  if (!el) return;

  const color = colorRgbToCss(feature.properties.colorRgb) || "#000000";
  const sizePx = feature.properties.textSize ?? 12;

  el.style.setProperty("--label-color", color);
  el.style.setProperty("--label-size", `${sizePx}px`);
}

function renderLabels(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || feature.geometry.type !== "Point") return;

    const [lng, lat] = feature.geometry.coordinates;
    const coord: L.LatLngTuple = [lat, lng];

    const label = L.marker(coord, {
      icon: L.divIcon({
        className: "city-label-text geoman-text-label",
        html: feature.properties.labelText || "",
        iconSize: [120, 20],
        iconAnchor: [0, 10],
      }),
    });

    label.on("add", () => applyLabelStyle(label, feature));

    const textMarker = label as L.Marker & {
      options: L.MarkerOptions & { text: string; textMarker?: boolean };
    };
    textMarker.options.text = feature.properties.labelText || "";
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

function normalizeGeometryToWorld(
  geometry: Geometry,
  sizeMeters: number,
): Geometry {
  const anchorLat = -80 + Math.random() * 160;
  const anchorLng = -170 + Math.random() * 340;

  return {
    ...geometry,
    coordinates: transformCoordinates(
      geometry.coordinates,
      anchorLat,
      anchorLng,
      sizeMeters,
    ),
  } as Geometry;
}

function transformNormalizedToWorld(
  geojson: GeoJsonFeatureCollectionWithGeometry,
  anchorLat: number,
  anchorLng: number,
  sizeMeters: number,
): GeoJsonFeatureCollectionWithGeometry {
  // Use the same projected CRS as the basemap (Web Mercator).
  const crs = L.CRS.EPSG3857;
  const center = crs.project(L.latLng(anchorLat, anchorLng));
  const halfSize = sizeMeters / 2;

  // Transform a single coordinate [x, y] in [0,1]x[0,1] into [lng, lat]
  const transformCoord = (coord: Coordinate): Coordinate => {
    const [x, y] = coord;

    // Center the shape around (0,0) in its local space
    const nx = x - 0.5;
    const ny = y - 0.5;

    // Work in projected meters with a uniform scale so aspect ratio is preserved
    const mx = center.x + nx * 2 * halfSize;
    const my = center.y - ny * 2 * halfSize;

    const latlng = crs.unproject(L.point(mx, my));
    return [latlng.lng, latlng.lat];
  };

  const transformCoords = (
    coords: Geometry["coordinates"],
  ): Geometry["coordinates"] => {
    if (!Array.isArray(coords)) return coords;

    if (typeof coords[0] === "number") {
      return transformCoord(coords as Coordinate);
    }

    return (coords as Array<Geometry["coordinates"]>).map(
      transformCoords,
    ) as Geometry["coordinates"];
  };

  return {
    ...geojson,
    features: geojson.features.map((feature) => ({
      ...feature,
      geometry: {
        ...feature.geometry,
        coordinates: transformCoords(feature.geometry.coordinates),
      } as Geometry,
    })),
  };
}

void normalizeGeometryToWorld;
void transformNormalizedToWorld;

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
    const strokeColor =
      colorRgbToCss(feature.properties.strokeColor) || fillColor;

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
    const strokeColor =
      colorRgbToCss(feature.properties.strokeColor) || fillColor;

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
    const strokeColor =
      colorRgbToCss(feature.properties.strokeColor) || fillColor;

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
    const strokeColor =
      colorRgbToCss(feature.properties.strokeColor) || fillColor;

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

function renderAllFeaturesSafely() {
  if (!map) return;

  const pm = (map as MapWithPm).pm;
  const wasGlobalRotateEnabled = pm?.globalRotateModeEnabled?.() ?? false;

  if (wasGlobalRotateEnabled) {
    pm?.disableGlobalRotateMode?.();
  }

  try {
    renderAllFeatures();
  } finally {
    if (wasGlobalRotateEnabled) {
      pm?.enableGlobalRotateMode?.();
    }
  }
}

function renderAllFeatures() {
  if (!map) return;

  const currentFeatures = props.features;
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
    shape: currentFeatures.filter((f) => getMapElementType(f) === "shape"),
    label: currentFeatures.filter((f) => getMapElementType(f) === "label"),
    polyline: currentFeatures.filter(
      (f) => getMapElementType(f) === "polyline",
    ),
    arrow: currentFeatures.filter((f) => getMapElementType(f) === "arrow"),
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
}

onMounted(() => {
  map = L.map("map", { zoomControl: false, preferCanvas: true }).setView(
    [52.9399, -73.5491],
    5,
  );
  vectorRenderer = L.canvas({ padding: 0.5 });

  L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
    {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 19,
    },
  ).addTo(map);

  drawing.initializeDrawing(map);

  L.control.zoom({ position: "topleft" }).addTo(map);
  addUndoRedoControls(map);

  L.control
    .scale({ position: "bottomright", metric: true, imperial: false })
    .addTo(map);

  drawing.setSelectedYear(props.selectedYear);
  emit("map-ready", map);
  renderAllFeaturesSafely();
});

onBeforeUnmount(() => {
  if (map) {
    featureLayerManager.clearAllFeatures();
    map.remove();
    map = null;
  }
});

watch(
  () => props.selectedYear,
  (val) => {
    drawing.setSelectedYear(val);
  },
);

watch(
  () => props.features,
  (newFeatures) => {
    localFeaturesSnapshot.value = [...newFeatures];
    if (!map) return;
    renderAllFeaturesSafely();
  },
  { deep: true },
);

localFeaturesSnapshot.value = [...props.features];

watch(
  () => props.featureVisibility,
  (newVisibility) => {
    newVisibility.forEach((visible, featureId) => {
      featureLayerManager.toggleFeature(featureId, visible);
    });
  },
  { deep: true },
);

watch(
  () => [props.canUndo, props.canRedo],
  async () => {
    await nextTick();
    updateHistoryToolbarState();
  },
  { immediate: true },
);
</script>

<style>
.city-label-text {
  font-size: var(--label-size, 12px);
  font-weight: bold;
  color: var(--label-color, #000);
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
