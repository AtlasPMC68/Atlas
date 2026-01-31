<template>
  <div class="relative h-full w-full z-0">
    <div id="map" style="height: 80vh; width: 100%"></div>
    <TimelineSlider v-model:year="timeline.selectedYear.value" />

    <!-- Bouton de suppression visible seulement en mode édition -->
    <div v-if="editMode" class="absolute top-4 right-4 z-10">
      <button
        @click="toggleDeleteMode()"
        :class="[
          'px-4 py-2 rounded-lg font-medium transition-colors duration-200 active:bg-red-800',
          editing.isDeleteMode.value
            ? 'bg-red-600 text-white hover:bg-red-700'
            : 'bg-gray-600 text-white hover:bg-gray-700',
        ]"
      >
        {{ editing.isDeleteMode.value ? "Mode Suppression" : "Supprimer" }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch, computed, onBeforeUnmount } from "vue";
import L from "leaflet";
import "leaflet-geometryutil";
import "leaflet-arrowheads";
import TimelineSlider from "../components/TimelineSlider.vue";

// ========================================
// COMPOSABLES
// ========================================
import { useMapLayers } from "../composables/useMapLayers.js";
import { useMapEditing } from "../composables/useMapEditing.js";
import { useMapEvents } from "../composables/useMapEvents.js";
import { useMapTimeline } from "../composables/useMapTimeline.js";
import { useMapInit } from "../composables/useMapInit.js";

// Props reçues de la vue parent
const props = defineProps({
  mapId: String,
  features: Array,
  featureVisibility: Map,
  editMode: { type: Boolean, default: false },
  activeEditMode: { type: String, default: null },
  selectedShape: { type: String, default: null },

  // === Resize manuel (inputs dans Map.vue) ===
  resizeFeatureId: { type: [String, Number], default: null },
  resizeWidthMeters: { type: Number, default: null },
  resizeHeightMeters: { type: Number, default: null },
});

// Émissions vers la vue parent
const emit = defineEmits(["features-loaded", "mode-change", "resize-selection"]);

// ========================================
// INIT COMPOSABLES
// ========================================
const layers = useMapLayers(props, emit);
const editing = useMapEditing(props, emit);
const events = useMapEvents(props, emit, layers, editing);
const timeline = useMapTimeline();
const init = useMapInit(props, emit, layers, events, editing, timeline);

// ========================================
// LOCALS
// ========================================
let map = null;
let baseTileLayer = null;

// Debounce resize “auto-apply”
let resizeCommitTimer = null;

// ========================================
// COMPUTED
// ========================================
const filteredFeatures = computed(() => {
  return props.features.filter(
    (feature) =>
      new Date(feature.start_date).getFullYear() <= timeline.selectedYear.value &&
      (!feature.end_date || new Date(feature.end_date).getFullYear() >= timeline.selectedYear.value),
  );
});

// ========================================
// HELPERS RESIZE (dimensions <-> sizePoint)
// ========================================
function getFeatureById(fid) {
  const id = String(fid);
  return props.features.find((f) => String(f.id) === id) || null;
}

function isResizableFeature(feature) {
  return !!feature?.properties?.resizable && !!feature?.properties?.shapeType && !!feature?.properties?.center;
}

// Retourne { widthMeters, heightMeters } à afficher dans les inputs
function getDimsMetersFromFeature(feature) {
  const shapeType = feature.properties.shapeType;
  const R = Number(feature.properties.size);
  if (!Number.isFinite(R) || R <= 0) return { widthMeters: null, heightMeters: null };

  switch (shapeType) {
    case "square": {
      const side = Math.SQRT2 * R;
      return { widthMeters: side, heightMeters: side };
    }
    case "circle": {
      const d = 2 * R;
      return { widthMeters: d, heightMeters: d };
    }
    case "triangle": {
      const w = Math.sqrt(3) * R;
      const h = 1.5 * R;
      return { widthMeters: w, heightMeters: h };
    }
    default:
      return { widthMeters: null, heightMeters: null };
  }
}

function sizePointFromDims(feature, widthMeters, heightMeters) {
  const { shapeType, center } = feature.properties;
  const c = L.latLng(center.lat, center.lng);

  const w = Number.isFinite(widthMeters) && widthMeters > 0 ? widthMeters : null;
  const h = Number.isFinite(heightMeters) && heightMeters > 0 ? heightMeters : null;

  let R = null;

  if (shapeType === "circle") {
    const d = w ?? h;
    if (d == null) return null;
    R = d / 2;
  } else if (shapeType === "square") {
    const side = w ?? h;
    if (side == null) return null;
    R = side / Math.SQRT2;
  } else if (shapeType === "triangle") {
    const candidates = [];
    if (w != null) candidates.push(w / Math.sqrt(3));
    if (h != null) candidates.push(h / 1.5);
    if (candidates.length === 0) return null;
    R = candidates.reduce((a, b) => a + b, 0) / candidates.length;
  } else {
    return null;
  }

  if (!Number.isFinite(R) || R <= 0) return null;

  const dLat = R / 111320;
  return L.latLng(c.lat + dLat, c.lng);
}

function clearResizeCommitTimer() {
  if (resizeCommitTimer) {
    clearTimeout(resizeCommitTimer);
    resizeCommitTimer = null;
  }
}

function getLayerById(fid) {
  return layers.featureLayerManager.layers.get(String(fid)) || null;
}

function getCenterFromLayer(layer) {
  if (layer.getLatLng && !layer.getLatLngs) return layer.getLatLng(); // marker-like
  if (layer.getBounds) return layer.getBounds().getCenter();
  return null;
}

// width = distance Ouest-Est à la latitude du centre
// height = distance Sud-Nord à la longitude du centre
function getDimsMetersFromLayer(layer) {
  if (!layer || !layer.getBounds || !map) return { widthMeters: null, heightMeters: null };

  const b = layer.getBounds();
  const c = b.getCenter();

  const widthMeters = map.distance([c.lat, b.getWest()], [c.lat, b.getEast()]);
  const heightMeters = map.distance([b.getSouth(), c.lng], [b.getNorth(), c.lng]);

  return {
    widthMeters: Number.isFinite(widthMeters) ? widthMeters : null,
    heightMeters: Number.isFinite(heightMeters) ? heightMeters : null,
  };
}

// ========================================
// MAP INIT
// ========================================
onMounted(() => {
  map = L.map("map").setView([52.9399, -73.5491], 5);

  baseTileLayer = L.tileLayer("https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
    subdomains: "abcd",
    maxZoom: 19,
  }).addTo(map);

  layers.initializeBaseLayers(map);
  timeline.loadRegionsForYear(timeline.selectedYear.value, map, true);

  map.on("zoomend", () => layers.updateCircleSizes(map));

  if (props.editMode) {
    init.initializeEditControls(map);

    layers.featureLayerManager.setClickHandler((featureId, isCtrlPressed) => {
      handleFeatureClickLocal(featureId, isCtrlPressed);
    });
  }
});

onBeforeUnmount(() => {
  clearResizeCommitTimer();
  if (map) {
    init.cleanupEditMode(map);
    layers.clearAllLayers(map);
    map.remove();
    map = null;
  }
});

// ========================================
// FEATURE CLICK LOCAL (INTERCEPT RESIZE MODE)
// ========================================
function handleFeatureClickLocal(featureId, isCtrlPressed) {
  if (!props.editMode || !map) return;

  // NEW: if selection was already handled via move mouseup (RESIZE_SHAPE reliability fix)
  if (events.suppressNextFeatureClick?.value) {
    events.suppressNextFeatureClick.value = false;
    return;
  }

  if (props.activeEditMode === "RESIZE_SHAPE") {
    events.applySelectionClick(String(featureId), isCtrlPressed, map);
    return;
  }

  init.handleFeatureClick(String(featureId), isCtrlPressed, map);
}

// ========================================
// SUPPRESSION
// ========================================
function toggleDeleteMode() {
  if (props.activeEditMode === "DELETE_FEATURE") emit("mode-change", null);
  else emit("mode-change", "DELETE_FEATURE");
}

// ========================================
// WATCHERS
// ========================================
watch(
  () => props.editMode,
  (newEditMode) => {
    if (newEditMode) {
      if (!layers.drawnItems.value) layers.initializeBaseLayers(map);

      init.initializeEditControls(map);
      layers.featureLayerManager.setClickHandler((featureId, isCtrlPressed) => {
        handleFeatureClickLocal(featureId, isCtrlPressed);
      });

      layers.renderAllFeatures(filteredFeatures.value, map);
    } else {
      init.cleanupEditMode(map);
    }

    init.updateMapCursor(map);
  },
);

// delete mode sync
watch(
  () => props.activeEditMode,
  (newMode) => {
    editing.isDeleteMode.value = newMode === "DELETE_FEATURE";
  },
  { immediate: true },
);

// mode change attach/detach handlers
watch(
  () => props.activeEditMode,
  (newMode, oldMode) => {
    if (!map) return;

    if (oldMode) events.cleanupCurrentDrawing();

    init.detachEditEventHandlers(map);
    init.attachEditEventHandlers(map);
    init.updateMapCursor(map);

    if (oldMode === "RESIZE_SHAPE" && newMode !== "RESIZE_SHAPE") {
      events.selectedFeatures.value.clear();
      editing.updateFeatureSelectionVisual(map, layers.featureLayerManager, events.selectedFeatures.value);
      emit("resize-selection", { featureId: null, widthMeters: null, heightMeters: null });

      if (editing.isResizeMode?.value && editing.resizingShape?.value) {
        editing.cancelResizeShape(map, layers);
      }
      clearResizeCommitTimer();
    }
  },
);

// year change
watch(
  () => timeline.selectedYear.value,
  (newYear) => {
    if (!map) return;
    timeline.loadRegionsForYear(newYear, map);
    layers.renderAllFeatures(filteredFeatures.value, map);
  },
);

// features change
watch(
  () => props.features,
  () => {
    if (!map) return;
    layers.renderAllFeatures(filteredFeatures.value, map);
  },
  { deep: true },
);

// visibility change
watch(
  () => props.featureVisibility,
  (newVisibility) => {
    newVisibility.forEach((visible, featureId) => {
      layers.featureLayerManager.toggleFeature(featureId, visible);
    });
  },
  { deep: true },
);

// ========================================
// APPLY RESIZE FROM INPUTS (NO DRAG)
// ========================================
watch(
  () => [props.activeEditMode, props.resizeFeatureId, props.resizeWidthMeters, props.resizeHeightMeters],
  ([mode, fid, w, h]) => {
    if (!map) return;
    if (!props.editMode) return;
    if (mode !== "RESIZE_SHAPE") return;
    if (!fid) return;

    clearResizeCommitTimer();
    resizeCommitTimer = setTimeout(() => {
      editing.applyResizeFromDims(String(fid), w, h, map, layers.featureLayerManager, emit);
      resizeCommitTimer = null;
    }, 150);
  },
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

.temp-marker {
  background: none !important;
  border: none !important;
}

.line-start-marker {
  background: none !important;
  border: none !important;
}

.polygon-marker {
  background: white;
  border: 2px solid #000;
  border-radius: 50%;
  text-align: center;
  font-weight: bold;
  color: #000;
}
</style>
