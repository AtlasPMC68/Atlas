<template>
  <div class="relative h-full w-full z-0">
    <div id="map" style="height: 80vh; width: 100%"></div>
    <TimelineSlider v-model:year="timeline.selectedYear.value" />

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
import { onMounted, watch, computed, onBeforeUnmount } from "vue";
import L from "leaflet";
import "leaflet-geometryutil";
import "leaflet-arrowheads";
import TimelineSlider from "../components/TimelineSlider.vue";

import { useMapLayers } from "../composables/useMapLayers.js";
import { useMapEditing } from "../composables/useMapEditing.js";
import { useMapEvents } from "../composables/useMapEvents.js";
import { useMapTimeline } from "../composables/useMapTimeline.js";
import { useMapInit } from "../composables/useMapInit.js";

const props = defineProps({
  mapId: String,
  features: Array,
  featureVisibility: Map,
  editMode: { type: Boolean, default: false },
  activeEditMode: { type: String, default: null },
  selectedShape: { type: String, default: null },

  resizeFeatureId: { type: [String, Number], default: null },
  resizeWidthMeters: { type: Number, default: null },
  resizeHeightMeters: { type: Number, default: null },

  rotateAngleDeg: { type: Number, default: null },
});

const emit = defineEmits(["features-loaded", "mode-change", "resize-selection"]);

const editing = useMapEditing(props, emit);
const layers = useMapLayers(props, emit, editing);
const events = useMapEvents(props, emit, layers, editing);
const timeline = useMapTimeline();
const init = useMapInit(props, emit, layers, events, editing);

let map = null;

let resizeCommitTimer = null;
let rotateCommitTimer = null;

const filteredFeatures = computed(() => {
  return props.features.filter(
    (feature) =>
      new Date(feature.start_date).getFullYear() <= timeline.selectedYear.value &&
      (!feature.end_date || new Date(feature.end_date).getFullYear() >= timeline.selectedYear.value),
  );
});

function clearResizeCommitTimer() {
  if (resizeCommitTimer) {
    clearTimeout(resizeCommitTimer);
    resizeCommitTimer = null;
  }
}

function clearRotateCommitTimer() {
  if (rotateCommitTimer) {
    clearTimeout(rotateCommitTimer);
    rotateCommitTimer = null;
  }
}

function getLayerById(fid) {
  return layers.featureLayerManager.layers.get(String(fid)) || null;
}

function normalizeAngleDeg(a) {
  let x = Number(a) || 0;
  x = ((x % 360) + 360) % 360;
  return x;
}

function getFeatureAngleDeg(featureId, layer) {
  const fid = String(featureId);

  const featureFromProps =
    props.features?.find((f) => String(f.id) === fid) || null;

  const feature = layer?.feature || featureFromProps || null;
  const p = feature?.properties || {};

  const raw = p.rotationDeg ?? p.angleDeg ?? p.angle ?? p.rotation ?? 0;
  return normalizeAngleDeg(raw);
}

function getLayerDimsMeters(fid) {
  const layer = getLayerById(fid);
  if (!layer || !map) return { w: null, h: null };

  if (typeof layer.getRadius === "function") {
    const d = 2 * layer.getRadius();
    return { w: d, h: d };
  }

  if (typeof layer.getLatLngs === "function" && typeof layer.getBounds === "function") {
    const angleDeg = getFeatureAngleDeg(fid, layer);
    const angleRad = (angleDeg * Math.PI) / 180;

    const bounds = layer.getBounds();
    if (!bounds?.isValid?.()) return { w: null, h: null };

    const centerLL = bounds.getCenter();
    const centerPt = map.latLngToLayerPoint(centerLL);

    const latlngs = layer.getLatLngs();
    const toPts = (x) => (Array.isArray(x) ? x.map(toPts) : map.latLngToLayerPoint(x));
    const pts = toPts(latlngs);

    const rotPt = (p, rad) => {
      const dx = p.x - centerPt.x;
      const dy = p.y - centerPt.y;
      const c = Math.cos(rad);
      const s = Math.sin(rad);
      return L.point(centerPt.x + dx * c - dy * s, centerPt.y + dx * s + dy * c);
    };
    const rotAll = (x, rad) => (Array.isArray(x) ? x.map((y) => rotAll(y, rad)) : rotPt(x, rad));
    const pts0 = Math.abs(angleRad) > 1e-9 ? rotAll(pts, -angleRad) : pts;

    const flat = [];
    const flatten = (x) => (Array.isArray(x) ? x.forEach(flatten) : flat.push(x));
    flatten(pts0);

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const p of flat) {
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    }
    if (!Number.isFinite(minX) || !Number.isFinite(maxX)) return { w: null, h: null };

    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;

    const west0 = L.point(minX, cy);
    const east0 = L.point(maxX, cy);
    const north0 = L.point(cx, minY);
    const south0 = L.point(cx, maxY);

    const back = (p) => (Math.abs(angleRad) > 1e-9 ? rotPt(p, angleRad) : p);

    const westLL = map.layerPointToLatLng(back(west0));
    const eastLL = map.layerPointToLatLng(back(east0));
    const northLL = map.layerPointToLatLng(back(north0));
    const southLL = map.layerPointToLatLng(back(south0));

    const w = map.distance(westLL, eastLL);
    const h = map.distance(northLL, southLL);

    return {
      w: Number.isFinite(w) ? w : null,
      h: Number.isFinite(h) ? h : null,
    };
  }

  if (typeof layer.getBounds === "function") {
    const b = layer.getBounds();
    if (!b?.isValid?.()) return { w: null, h: null };
    const c = b.getCenter();
    const w = map.distance([c.lat, b.getWest()], [c.lat, b.getEast()]);
    const h = map.distance([b.getSouth(), c.lng], [b.getNorth(), c.lng]);
    return { w, h };
  }

  return { w: null, h: null };
}

function handleFeatureClickLocal(featureId, isCtrlPressed) {
  if (!props.editMode || !map) return;

  if (props.activeEditMode === "RESIZE_SHAPE") {
    if (events.suppressNextFeatureClick?.value) return;

    events.applySelectionClick(String(featureId), isCtrlPressed, map);
    return;
  }

  init.handleFeatureClick(String(featureId), isCtrlPressed, map);
}

function toggleDeleteMode() {
  if (props.activeEditMode === "DELETE_FEATURE") emit("mode-change", null);
  else emit("mode-change", "DELETE_FEATURE");
}

function renderAllAndRebind() {
  if (!map) return;

  layers.renderAllFeatures(filteredFeatures.value, map);

  if (props.editMode) {
    init.makeFeaturesClickable(map);

    if (props.activeEditMode === "RESIZE_SHAPE" && events.selectedFeatures?.value?.size) {
      events.syncSelectionOverlays(map);
    }
  }
}

onMounted(() => {
  map = L.map("map").setView([52.9399, -73.5491], 5);

  layers.initializeBaseLayers(map);
  timeline.loadRegionsForYear(timeline.selectedYear.value, map, true);

  map.on("zoomend", () => layers.updateCircleSizes(map));

  if (props.editMode) {
    init.initializeEditControls(map);
    layers.featureLayerManager.setClickHandler((featureId, isCtrlPressed) => {
      handleFeatureClickLocal(featureId, isCtrlPressed);
    });
  }

  renderAllAndRebind();
});

onBeforeUnmount(() => {
  clearResizeCommitTimer();
  clearRotateCommitTimer();

  if (map) {
    init.cleanupEditMode(map);
    layers.clearAllLayers(map);
    map.remove();
    map = null;
  }
});

// Edit mode toggle
watch(
  () => props.editMode,
  (newEditMode) => {
    if (!map) return;

    if (newEditMode) {
      if (!layers.drawnItems.value) layers.initializeBaseLayers(map);

      init.initializeEditControls(map);
      layers.featureLayerManager.setClickHandler((featureId, isCtrlPressed) => {
        handleFeatureClickLocal(featureId, isCtrlPressed);
      });

      renderAllAndRebind();
    } else {
      init.cleanupEditMode(map);

      try {
        layers.featureLayerManager.setClickHandler(null);
      } catch (e) {
        layers.featureLayerManager.setClickHandler(() => {});
      }
    }

    init.updateMapCursor(map);
  },
);

// Delete mode mapping
watch(
  () => props.activeEditMode,
  (newMode) => {
    editing.isDeleteMode.value = newMode === "DELETE_FEATURE";
  },
  { immediate: true },
);

// Active mode transitions
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
      events.clearSelectionBBoxes?.(map);
      events.clearSelectionAnchors?.(map);

      emit("resize-selection", { featureId: null, widthMeters: null, heightMeters: null, angleDeg: null });

      clearResizeCommitTimer();
      clearRotateCommitTimer();
    }
  },
);

// Timeline year changes
watch(
  () => timeline.selectedYear.value,
  (newYear) => {
    if (!map) return;
    timeline.loadRegionsForYear(newYear, map);
    renderAllAndRebind();
  },
);

// Features rerender (guard while dragging in RESIZE_SHAPE)
watch(
  () => props.features,
  () => {
    if (!map) return;

    if (props.editMode && props.activeEditMode === "RESIZE_SHAPE" && events.isDraggingFeatures?.value) {
      return;
    }

    renderAllAndRebind();
  },
);

// Visibility toggle
watch(
  () => props.featureVisibility,
  (newVisibility) => {
    newVisibility.forEach((visible, featureId) => {
      layers.featureLayerManager.toggleFeature(featureId, visible);
    });
  },
  { deep: true },
);

// APPLY RESIZE FROM INPUTS
watch(
  () => [props.activeEditMode, props.resizeFeatureId, props.resizeWidthMeters, props.resizeHeightMeters],
  ([mode, fid, w, h]) => {
    if (!map) return;
    if (!props.editMode) return;
    if (mode !== "RESIZE_SHAPE") return;
    if (!fid) return;

    clearResizeCommitTimer();
    resizeCommitTimer = setTimeout(async () => {
      const cur = getLayerDimsMeters(fid);
      const tol = 25;

      const wOk = cur.w == null || w == null ? true : Math.abs(cur.w - w) > tol;
      const hOk = cur.h == null || h == null ? true : Math.abs(cur.h - h) > tol;

      if (!wOk && !hOk) {
        resizeCommitTimer = null;
        return;
      }

      await editing.applyResizeFromDims(String(fid), w, h, map, layers.featureLayerManager, emit);

      events.upsertSelectionBBox?.(String(fid), map, layers.featureLayerManager);
      events.upsertSelectionAnchors?.(String(fid), map, layers.featureLayerManager);

      resizeCommitTimer = null;
    }, 150);
  },
);

// APPLY ROTATION FROM INPUT
watch(
  () => [props.activeEditMode, props.resizeFeatureId, props.rotateAngleDeg],
  ([mode, fid, angleDeg]) => {
    if (!map) return;
    if (!props.editMode) return;
    if (mode !== "RESIZE_SHAPE") return;
    if (!fid) return;
    if (angleDeg == null) return;

    clearRotateCommitTimer();
    rotateCommitTimer = setTimeout(async () => {
      const layer = getLayerById(fid);
      if (!layer) {
        rotateCommitTimer = null;
        return;
      }

      const curA = getFeatureAngleDeg(fid, layer);
      const nextA = normalizeAngleDeg(angleDeg);

      const diff = Math.abs(nextA - curA);
      const wrappedDiff = Math.min(diff, 360 - diff);
      if (wrappedDiff < 0.25) {
        rotateCommitTimer = null;
        return;
      }

      await editing.applyRotateFromAngle(String(fid), nextA, map, layers.featureLayerManager, emit);

      events.upsertSelectionBBox?.(String(fid), map, layers.featureLayerManager);
      events.upsertSelectionAnchors?.(String(fid), map, layers.featureLayerManager);

      rotateCommitTimer = null;
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
