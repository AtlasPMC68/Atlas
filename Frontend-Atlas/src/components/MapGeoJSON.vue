<template>
  <div class="relative h-full w-full z-0">
    <div id="map" style="height: 80vh; width: 100%"></div>
    <TimelineSlider v-model:year="selectedYear" />
    <div
      v-if="pendingCity"
      class="city-name-input-container"
      :style="{ left: pendingCity.screenPos.x + 'px', top: pendingCity.screenPos.y + 'px' }"
    >
      <input
        ref="cityInput"
        v-model="cityInputName"
        class="city-name-input"
        placeholder="Nom de la ville"
        @keydown.enter.prevent="confirmCity"
        @keydown.escape.prevent="cancelAddCity"
        @blur="confirmCity"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch, ref, computed } from "vue";
import L from "leaflet";
import "leaflet-geometryutil";
import "leaflet-arrowheads";
import TimelineSlider from "../components/TimelineSlider.vue";
import { useMapDrawing } from "../composables/useMapDrawing";
import { useAddCityMode } from "../composables/useAddCityMode";
import { useImageOverlay } from "../composables/useImageOverlay";
import { colorRgbToCss, getMapElementType } from "../utils/featureHelpers";
import {
  extractFeatureFromLayer,
  syncFeaturesFromLayerMap,
} from "../utils/mapDrawingFeature";
import {
  attachFeatureToLayer,
  bindRenderedFeatureEvents,
  applyStyleToLayer,
  getLayerStrokeColor,
} from "../utils/mapLayersFeature";
import {
  forEachLeafLayer,
  enablePerFeatureDrag,
  disablePerFeatureDrag,
  enablePixelSpaceDrag,
} from "../utils/mapDragUtils";
import { toArray, toImageSrc } from "../utils/utils";
import type {
  Feature,
  FeatureId,
} from "../typescript/feature";
import type { AtlasRuntimeLayer } from "../typescript/mapLayers";
import type { MapWithPm, PmIgnoreOptions } from "../typescript/mapDrawing";

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
// When the map itself is the source of a change (drag, edit, image move), we
// emit "draw-update" which propagates back down via props.features. This flag
// tells the props watcher to skip the re-render for that one echo update so we
// don't destroy and re-create the layer the user is actively interacting with.
let suppressNextPropsRender = false;
let blockNextMapClick = false;
let selectedLayerOriginalStyle: L.PathOptions | undefined = undefined;
let selectedCityRing: L.Marker | null = null;
let pixelSpaceDragCleanup: (() => void) | null = null;
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

    layer.on("click", () => {
      // Don't steal clicks from active drawing tools
      if (drawing.activeDrawingMode.value !== null) return;
      // In canvas mode, Leaflet fires the layer click AND the map click as two
      // separate events from the same mouse event. Without this flag, the map
      // click handler would immediately deselect what we just selected.
      blockNextMapClick = true;
      if (addCityMode.value) cityMode.cancel();
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

      const setIgnoreDeep = (l: L.Layer) => {
        (l.options as PmIgnoreOptions).pmIgnore = true;
        if (l instanceof L.LayerGroup) {
          (l as L.LayerGroup).eachLayer(setIgnoreDeep);
        }
      };

      const clearIgnoreDeep = (l: L.Layer) => {
        delete (l.options as PmIgnoreOptions).pmIgnore;
        if (l instanceof L.LayerGroup) {
          (l as L.LayerGroup).eachLayer(clearIgnoreDeep);
        }
      };

      if (anyModeActive) setIgnoreDeep(layer);
      map.addLayer(layer);
      if (anyModeActive) clearIgnoreDeep(layer);
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

function resetSelection() {
  selectedFeatureId.value = null;
}

defineExpose({
  syncFeaturesFromMapLayers,
  clearDraftLayers,
  resetSelection,
});

// Tracks feature IDs that got `feature-updated` during the current cut cycle.
// Used in `cut-complete` to distinguish intersected (updated) zones from
// enclosed (silently removed) zones — geoman does NOT fire pm:remove for the
// latter, so we must detect them by checking which layers disappeared from the
// map but were NOT updated.
let cuttingUpdatedIds: Set<string> | null = null;

const drawing = useMapDrawing((event, ...args) => {
  const current = localFeaturesSnapshot.value;

  if (event === "cut-started") {
    cuttingUpdatedIds = new Set<string>();
    return;
  }

  if (event === "feature-created") {
    const payload = args[0] as Feature;
    const next = upsertFeature(current, payload);
    localFeaturesSnapshot.value = next;
    emit("draw-create", next);
    return;
  }

  if (event === "feature-updated") {
    const payload = args[0] as Feature;
    // Track IDs updated during a cut so cut-complete can identify enclosed zones.
    cuttingUpdatedIds?.add(String(payload.id));
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

  if (event === "cut-complete") {
    // Detect zones that geoman silently removed (fully enclosed by the cut
    // polygon). Geoman calls map.removeLayer() on them directly — pm:remove
    // never fires. They are identified as layers that are no longer on the map
    // but were NOT processed by pm:cut (feature-updated).
    //
    // Zones/shapes are L.GeoJSON (FeatureGroup) containers. Geoman initialises
    // PM on the inner L.Polygon sublayers and removes those, NOT the outer
    // container. map.hasLayer(container) therefore still returns true even
    // after geoman removed the enclosed zone. We must check the children.
    if (map && cuttingUpdatedIds !== null) {
      const isRemovedFromMap = (layer: L.Layer): boolean => {
        if (!map!.hasLayer(layer)) return true;
        const asGroup = layer as unknown as Partial<L.LayerGroup>;
        if (typeof asGroup.getLayers === "function") {
          const children = asGroup.getLayers();
          // All children gone (removed from group entirely, or none left on map)
          if (children.length === 0) return true;
          return children.every((c) => !map!.hasLayer(c));
        }
        return false;
      };

      const removedIds: string[] = [];
      featureLayerManager.layers.forEach((layer, id) => {
        if (isRemovedFromMap(layer) && !cuttingUpdatedIds!.has(id)) {
          removedIds.push(id);
        }
      });
      if (removedIds.length > 0) {
        let next = localFeaturesSnapshot.value;
        for (const deletedId of removedIds) {
          next = next.filter((f) => String(f.id) !== deletedId);
          featureLayerManager.layers.delete(deletedId);
          emit("draw-delete-id", deletedId);
        }
        localFeaturesSnapshot.value = next;
        emit("draw-delete", next);
      }
    }
    cuttingUpdatedIds = null;
    // Re-render so intersected zones get their updated geometry and the
    // enclosed zones (now removed from localFeaturesSnapshot) stay gone.
    renderAllFeatures();
    return;
  }
});

const cityInput = ref<HTMLInputElement | null>(null); // template ref — Vue writes the element
const cityMode = useAddCityMode({
  getMap: () => map,
  selectedYear,
  localFeaturesSnapshot,
  cityInput,
  onCreated: (next) => emit('draw-create', next),
  onAfterCreate: () => renderAllFeatures(),
});
const { addCityMode, pendingCity, cityInputName } = cityMode;
const cancelAddCity = cityMode.cancel;
const confirmCity = cityMode.confirm;

const imageOverlay = useImageOverlay({
  getMap: () => map,
  getLayerById: (id) => featureLayerManager.layers.get(id),
  localFeaturesSnapshot,
  onBeforeEmit: () => { suppressNextPropsRender = true; },
  onUpdate: (next) => emit('draw-update', next),
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

    // Forward clicks from the inner point to the layerGroup so that the
    // standard featureLayerManager selection handler fires (same path as all
    // other feature types), keeping blockNextMapClick behaviour consistent.
    point.on("click", (e: L.LeafletEvent) => {
      layerGroup.fire("click", e);
    });

    point.on("pm:drag", () => {
      label.setLatLng(point.getLatLng());
      if (selectedCityRing) selectedCityRing.setLatLng(point.getLatLng());
    });

    point.on("pm:dragend", () => {
      label.setLatLng(point.getLatLng());
      if (selectedCityRing) selectedCityRing.setLatLng(point.getLatLng());
    });

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

    line.arrowheads({
      size: "10px",
      frequency: "endonly",
      fill: true,
    });

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

    featureLayerManager.addFeatureLayer(feature.id, layer);
  });
}

function renderImages(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || !feature.image) return;

    const bounds = feature.properties?.bounds as [[number, number], [number, number]] | undefined;

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
      imageOverlay.attach(selectedFeatureId.value);
    }
  }

  previousFeatureIds.value = currentIds;
  emit("features-loaded", currentFeatures);
}

// --- per-feature drag ---

onMounted(() => {
  map = L.map("map", {
    zoomControl: false,
    preferCanvas: true,
    doubleClickZoom: false,
    zoomSnap: 0.25,
    maxBounds: [[-90, -180], [90, 180]],
    maxBoundsViscosity: 1.0,
  }).setView(
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
      noWrap: true,
    },
  ).addTo(map);

  // Put image overlays in a pane above the canvas (overlayPane z-index 400)
  // so they natively receive pointer events without the canvas intercepting them.
  const imagePane = map.createPane('imagePane');
  imagePane.style.zIndex = '410';

  // Set minZoom dynamically so the whole world just fits the container (no fixed integer cap).
  // Recompute on resize so it stays correct when the window changes size.
  const updateMinZoom = () => {
    const wz = map!.getBoundsZoom(L.latLngBounds([[-90, -180], [90, 180]]), false);
    map!.setMinZoom(wz);
  };
  map.whenReady(updateMinZoom);
  map.on('resize', updateMinZoom);

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

    if (btnName === "addCity") {
      if (addCityMode.value) {
        cityMode.cancel();
      } else {
        cityMode.start();
        selectedFeatureId.value = null;
      }
      return;
    }

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

  map.on("click", (e) => {
    if (blockNextMapClick) {
      blockNextMapClick = false;
      return;
    }
    if (addCityMode.value) {
      cityMode.handleMapClick((e as L.LeafletMouseEvent).latlng);
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
    // Cancel city placement mode
    if (addCityMode.value) {
      cityMode.cancel();
      return;
    }
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
    // Cancel active global edit/rotate mode (fires even when scoped to a selected feature)
    if (pm?.globalEditModeEnabled?.()) { pm.disableGlobalEditMode?.(); return; }
    if (pm?.globalRotateModeEnabled?.()) { pm.disableGlobalRotateMode?.(); return; }
    // Deselect the currently selected feature if no mode is active
    if (selectedFeatureId.value !== null) {
      selectedFeatureId.value = null;
      return;
    }
  };
  document.addEventListener("keydown", escapeKeyHandler);
});

onBeforeUnmount(() => {
  if (escapeKeyHandler) {
    document.removeEventListener("keydown", escapeKeyHandler);
    escapeKeyHandler = null;
  }
  selectedCityRing?.remove();
  pixelSpaceDragCleanup?.();
  imageOverlay.detach();
  if (map) {
    featureLayerManager.clearAllFeatures();
    map.remove();
    map = null;
  }
});

watch(selectedYear, (newYear) => {
  drawing.setSelectedYear(newYear);
  if (!map) return;
  renderAllFeatures();
});

// While any draw mode is active, disable pointer-events on the canvas so that
// hovering/clicking existing features doesn't override the draw cursor or steal clicks.
watch(drawing.activeDrawingMode, (mode) => {
  if (!map) return;
  map.getContainer().querySelectorAll<HTMLCanvasElement>('canvas').forEach((canvas) => {
    canvas.style.pointerEvents = mode !== null ? 'none' : '';
  });
});

watch(
  () => props.features,
  (newFeatures) => {
    localFeaturesSnapshot.value = [...newFeatures];
    // The map emitted draw-update, which echoed back here via props. Skip the
    // re-render so we don't destroy the layer the user is actively interacting with.
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
  // Always remove the city selection ring on any selection change
  if (selectedCityRing) {
    selectedCityRing.remove();
    selectedCityRing = null;
  }

  // Restore the original stroke color on the previously selected layer
  if (oldId != null) {
    const oldLayer = featureLayerManager.layers.get(String(oldId));
    if (oldLayer instanceof L.ImageOverlay) {
      oldLayer.getElement()?.classList.remove("image-overlay-selected");
    } else if (oldLayer !== undefined) {
      disablePerFeatureDrag(oldLayer);
      pixelSpaceDragCleanup?.();
      pixelSpaceDragCleanup = null;
      if (selectedLayerOriginalStyle !== undefined) {
        applyStyleToLayer(oldLayer, selectedLayerOriginalStyle);
      }
    }
    selectedLayerOriginalStyle = undefined;
  }

  if (id != null) {
    const layer = featureLayerManager.layers.get(String(id));
    const selectedFeature = localFeaturesSnapshot.value.find((f) => String(f.id) === id);
    const elementType = selectedFeature ? getMapElementType(selectedFeature) : null;
    if (layer instanceof L.ImageOverlay) {
      drawing.setToolbarMode("global");
      layer.getElement()?.classList.add("image-overlay-selected");
    } else if (layer && elementType === "point") {
      // Cities: keep global toolbar, just enable drag and show a selection ring
      drawing.setToolbarMode("global");
      enablePerFeatureDrag(layer);
      // Find the circleMarker inside the layerGroup to get its latlng
      let cityLatLng: L.LatLng | null = null;
      forEachLeafLayer(layer, (leaf) => {
        if (!cityLatLng && leaf instanceof L.CircleMarker) {
          cityLatLng = (leaf as L.CircleMarker).getLatLng();
        }
      });
      if (cityLatLng && map) {
        selectedCityRing = L.marker(cityLatLng, {
          icon: L.divIcon({
            className: "city-selection-ring",
            iconSize: [22, 22],
            iconAnchor: [11, 11],
          }),
          interactive: false,
          zIndexOffset: 1000,
        }).addTo(map);
      }
    } else if (layer) {
      drawing.setToolbarMode("feature");
      enablePerFeatureDrag(layer);
      pixelSpaceDragCleanup = enablePixelSpaceDrag(map!, layer);
      const originalColor = getLayerStrokeColor(layer);
      selectedLayerOriginalStyle = originalColor !== undefined ? { color: originalColor } : undefined;
      applyStyleToLayer(layer, { color: "#000000" });
    } else {
      drawing.setToolbarMode("global");
    }

    // Attach/detach image overlay move+resize interaction
    imageOverlay.detach();
    if (selectedFeature && getMapElementType(selectedFeature) === "image") {
      imageOverlay.attach(id);
    }
  } else {
    // Disable any active per-feature edit/rotate mode so geoman stops
    // intercepting canvas clicks and restorePmIgnore() fires via the
    // pm:globaleditmodetoggled / pm:globalrotatemodetoggled events.
    const pm = (map as MapWithPm)?.pm;
    if (pm?.globalEditModeEnabled?.()) pm.disableGlobalEditMode?.();
    if (pm?.globalRotateModeEnabled?.()) pm.disableGlobalRotateMode?.();
    drawing.setToolbarMode("global");
    imageOverlay.detach();
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

.city-selection-ring {
  width: 22px !important;
  height: 22px !important;
  border-radius: 50%;
  border: 2.5px solid #3b82f6;
  background: transparent;
  box-sizing: border-box;
  pointer-events: none;
}

.arrow-head {
  font-size: 20px;
  color: black;
  transform: rotate(0deg);
}
</style>
