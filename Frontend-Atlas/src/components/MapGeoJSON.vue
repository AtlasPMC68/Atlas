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

interface ImageInteractionState {
  overlay: L.ImageOverlay;
  featureId: string;
  resizeMarker: L.Marker;
  aspectRatio: number; // pixel width / pixel height at attach time
}
let imageInteraction: ImageInteractionState | null = null;

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
      pane: 'imagePane',
    });

    attachFeatureToLayer(overlay, feature);
    featureLayerManager.addFeatureLayer(feature.id, overlay);
    overlay.getElement()?.setAttribute('draggable', 'false');
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

  // Re-attach image interaction if the selected feature was re-rendered
  if (selectedFeatureId.value) {
    const selectedFeature = currentFeatures.find(
      (f) => String(f.id) === selectedFeatureId.value,
    );
    if (selectedFeature && getMapElementType(selectedFeature) === "image") {
      attachImageInteraction(selectedFeatureId.value);
    }
  }

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

// --- per-feature drag ---

type PmDraggableLayer = L.Layer & { pm?: { enableLayerDrag?: () => void; disableLayerDrag?: () => void } };

function forEachLeafLayer(layer: L.Layer, fn: (l: L.Layer) => void) {
  if (layer instanceof L.LayerGroup) {
    (layer as L.LayerGroup).eachLayer((child) => forEachLeafLayer(child, fn));
  } else {
    fn(layer);
  }
}

function enablePerFeatureDrag(layer: L.Layer) {
  forEachLeafLayer(layer, (leaf) => {
    (leaf as PmDraggableLayer).pm?.enableLayerDrag?.();
  });
}

function disablePerFeatureDrag(layer: L.Layer) {
  forEachLeafLayer(layer, (leaf) => {
    (leaf as PmDraggableLayer).pm?.disableLayerDrag?.();
  });
}

// --- image overlay: move & resize ---

function updateImageFeatureBounds(featureId: string, bounds: L.LatLngBounds) {
  const sw = bounds.getSouthWest();
  const ne = bounds.getNorthEast();
  const boundsArray: [[number, number], [number, number]] = [
    [sw.lat, sw.lng],
    [ne.lat, ne.lng],
  ];
  const idx = localFeaturesSnapshot.value.findIndex(
    (f) => String(f.id) === featureId,
  );
  if (idx === -1) return;
  const next = [...localFeaturesSnapshot.value];
  next[idx] = {
    ...next[idx],
    properties: { ...next[idx].properties, bounds: boundsArray },
  };
  localFeaturesSnapshot.value = next;

  // Also update the feature stored on the layer itself so that
  // extractFeatureFromLayer returns the updated bounds during save.
  const layer = featureLayerManager.layers.get(featureId);
  if (layer) {
    const layerWithFeature = layer as L.Layer & { feature?: (typeof next)[0] };
    if (layerWithFeature.feature) {
      layerWithFeature.feature = next[idx];
    }
  }

  suppressNextPropsRender = true;
  emit("draw-update", next);
}

function detachImageInteraction() {
  if (!imageInteraction) return;
  imageInteraction.resizeMarker.remove();
  (imageInteraction as ImageInteractionState & { cleanupDrag?: () => void }).cleanupDrag?.();
  imageInteraction = null;
}

function attachImageInteraction(featureId: string) {
  detachImageInteraction();
  if (!map) return;
  const layer = featureLayerManager.layers.get(featureId);
  if (!(layer instanceof L.ImageOverlay)) return;

  const bounds = layer.getBounds();

  // Pixel aspect ratio (width/height) at current zoom — preserved during resize
  const nwPx = map.latLngToContainerPoint(bounds.getNorthWest());
  const sePx = map.latLngToContainerPoint(bounds.getSouthEast());
  const aspectRatio = Math.abs(sePx.x - nwPx.x) / Math.abs(sePx.y - nwPx.y);

  // SE corner drag handle
  const resizeMarker = L.marker(bounds.getSouthEast(), {
    icon: L.divIcon({
      className: "image-resize-handle",
      iconSize: [10, 10],
      iconAnchor: [5, 5],
    }),
    draggable: true,
    zIndexOffset: 1000,
  });
  (resizeMarker.options as PmIgnoreOptions).pmIgnore = true;
  resizeMarker.addTo(map);

  resizeMarker.on("drag", () => {
    if (!imageInteraction || !map) return;
    const nw = imageInteraction.overlay.getBounds().getNorthWest();
    const nwPx = map.latLngToContainerPoint(nw);
    const rawSePx = map.latLngToContainerPoint(resizeMarker.getLatLng());
    // Constrain to aspect ratio: fix width, derive height
    const w = Math.max(rawSePx.x - nwPx.x, 10);
    const h = w / imageInteraction.aspectRatio;
    const constrainedSe = map.containerPointToLatLng(
      L.point(nwPx.x + w, nwPx.y + h),
    );
    imageInteraction.overlay.setBounds(L.latLngBounds(nw, constrainedSe));
    resizeMarker.setLatLng(constrainedSe);
  });

  resizeMarker.on("dragend", () => {
    if (!imageInteraction) return;
    updateImageFeatureBounds(
      imageInteraction.featureId,
      imageInteraction.overlay.getBounds(),
    );
  });

  imageInteraction = { overlay: layer, featureId, resizeMarker, aspectRatio };

  // The image is in its own pane above the canvas so it receives native pointer
  // events — we can use overlay.on("mousedown") directly here.
  let isDragging = false;
  let startLatLng: L.LatLng | null = null;
  let startBounds: L.LatLngBounds | null = null;

  const onOverlayMouseDown = (e: L.LeafletMouseEvent) => {
    if (!imageInteraction) return;
    L.DomEvent.stopPropagation(e);
    isDragging = true;
    startLatLng = e.latlng;
    startBounds = imageInteraction.overlay.getBounds();
    map!.dragging.disable();
  };

  const onMapMouseMove = (e: L.LeafletMouseEvent) => {
    if (!isDragging || !startLatLng || !startBounds || !map || !imageInteraction) return;
    const startPx = map.latLngToContainerPoint(startLatLng);
    const nowPx = map.latLngToContainerPoint(e.latlng);
    const dx = nowPx.x - startPx.x;
    const dy = nowPx.y - startPx.y;
    const swPx = map.latLngToContainerPoint(startBounds.getSouthWest());
    const nePx = map.latLngToContainerPoint(startBounds.getNorthEast());
    const newBounds = L.latLngBounds(
      map.containerPointToLatLng(L.point(swPx.x + dx, swPx.y + dy)),
      map.containerPointToLatLng(L.point(nePx.x + dx, nePx.y + dy)),
    );
    imageInteraction.overlay.setBounds(newBounds);
    imageInteraction.resizeMarker.setLatLng(newBounds.getSouthEast());
  };

  const onMapMouseUp = () => {
    if (!isDragging) return;
    isDragging = false;
    map!.dragging.enable();
    if (imageInteraction) {
      updateImageFeatureBounds(imageInteraction.featureId, imageInteraction.overlay.getBounds());
    }
    startLatLng = null;
    startBounds = null;
  };

  layer.on("mousedown", onOverlayMouseDown);
  map.on("mousemove", onMapMouseMove);
  map.on("mouseup", onMapMouseUp);

  const cleanupDrag = () => {
    layer.off("mousedown", onOverlayMouseDown);
    map?.off("mousemove", onMapMouseMove);
    map?.off("mouseup", onMapMouseUp);
    map?.dragging.enable();
  };

  (imageInteraction as ImageInteractionState & { cleanupDrag?: () => void }).cleanupDrag = cleanupDrag;
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

  // Put image overlays in a pane above the canvas (overlayPane z-index 400)
  // so they natively receive pointer events without the canvas intercepting them.
  const imagePane = map.createPane('imagePane');
  imagePane.style.zIndex = '410';

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
    // Cancel active global edit/rotate mode
    if (pm?.globalEditModeEnabled?.()) { pm.disableGlobalEditMode?.(); return; }
    if (pm?.globalRotateModeEnabled?.()) { pm.disableGlobalRotateMode?.(); return; }
  };
  document.addEventListener("keydown", escapeKeyHandler);
});

onBeforeUnmount(() => {
  if (escapeKeyHandler) {
    document.removeEventListener("keydown", escapeKeyHandler);
    escapeKeyHandler = null;
  }
  detachImageInteraction();
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
    if (oldLayer instanceof L.ImageOverlay) {
      oldLayer.getElement()?.classList.remove("image-overlay-selected");
    } else if (oldLayer !== undefined) {
      disablePerFeatureDrag(oldLayer);
      if (selectedLayerOriginalColor !== undefined) {
        applyStyleToLayer(oldLayer, { color: selectedLayerOriginalColor });
      }
    }
    selectedLayerOriginalColor = undefined;
  }

  if (id != null) {
    const layer = featureLayerManager.layers.get(String(id));
    if (layer instanceof L.ImageOverlay) {
      drawing.setToolbarMode("global");
      layer.getElement()?.classList.add("image-overlay-selected");
    } else if (layer) {
      drawing.setToolbarMode("feature");
      enablePerFeatureDrag(layer);
      selectedLayerOriginalColor = getLayerStrokeColor(layer);
      applyStyleToLayer(layer, { color: "#000000" });
    } else {
      drawing.setToolbarMode("global");
    }
  } else {
    drawing.setToolbarMode("global");
  }

  if (!id && map) {
    const pm = (map as MapWithPm).pm;
    if (pm?.globalEditModeEnabled?.()) pm.disableGlobalEditMode?.();
    if (pm?.globalRotateModeEnabled?.()) pm.disableGlobalRotateMode?.();
  }

  // Attach/detach image overlay move+resize interaction
  detachImageInteraction();
  if (id != null) {
    const selectedFeature = localFeaturesSnapshot.value.find(
      (f) => String(f.id) === id,
    );
    if (selectedFeature && getMapElementType(selectedFeature) === "image") {
      attachImageInteraction(id);
    }
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
