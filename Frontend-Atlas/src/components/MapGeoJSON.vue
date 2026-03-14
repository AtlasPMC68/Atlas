<template>
  <div class="relative h-full w-full z-0">
    <div id="map" style="height: 100vh; width: 100%"></div>
    <TimelineSlider v-model:year="timeline.selectedYear.value" />

    <!-- Multi-selection indicator -->
    <div
      v-if="multiSelect.hasSelection.value"
      class="absolute top-4 right-4 bg-base-100 shadow-lg rounded-lg p-4 z-10 border-2 border-cyan-400"
    >
      <div class="flex items-center gap-2">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="h-5 w-5 text-cyan-500"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
          <path
            fill-rule="evenodd"
            d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm3 4a1 1 0 000 2h.01a1 1 0 100-2H7zm3 0a1 1 0 000 2h3a1 1 0 100-2h-3zm-3 4a1 1 0 100 2h.01a1 1 0 100-2H7zm3 0a1 1 0 100 2h3a1 1 0 100-2h-3z"
            clip-rule="evenodd"
          />
        </svg>
        <div>
          <div class="font-bold text-sm">
            {{ multiSelect.selectionCount.value }} élément(s) sélectionné(s)
          </div>
          <div class="text-xs text-gray-500">
            CTRL+clic pour sélectionner/désélectionner
          </div>
        </div>
        <button
          @click="multiSelect.clearSelection()"
          class="btn btn-xs btn-ghost ml-2"
          title="Désélectionner tout"
        >
          ✕
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, computed, onBeforeUnmount } from "vue";
import L from "leaflet";
import "leaflet-geometryutil";
import "leaflet-arrowheads";
import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import TimelineSlider from "../components/TimelineSlider.vue";

import { useMapLayers } from "../composables/useMapLayers.ts";
import { useMapTimeline } from "../composables/useMapTimeline.ts";
import { useMapDrawing } from "../composables/useMapDrawing.ts";
import { useMultiSelect } from "../composables/useMultiSelect.ts";

const props = defineProps({
  mapId: String,
  features: Array,
  featureVisibility: Map,
  editMode: { type: Boolean, default: false },
  activeEditMode: { type: String, default: null },
  selectedShape: { type: String, default: null },
});

const emit = defineEmits([
  "features-loaded",
  "mode-change",
  "feature-created",
  "feature-updated",
  "feature-deleted",
]);

// Multi-selection support
const multiSelect = useMultiSelect();

// Simple wrapper for drawing events
const drawing = useMapDrawing((event, ...args) => {
  emit(event, args[0]);
});

// Create a minimal editing composable wrapper (just for layers, no custom handlers)
const editing = {
  isDeleteMode: ref(false),
};

const layers = useMapLayers({ editMode: props.editMode }, emit, editing);
const timeline = useMapTimeline();

let map = null;

const filteredFeatures = computed(() => {
  return props.features.filter(
    (feature) =>
      new Date(feature.start_date).getFullYear() <=
        timeline.selectedYear.value &&
      (!feature.end_date ||
        new Date(feature.end_date).getFullYear() >=
          timeline.selectedYear.value),
  );
});

function renderAllAndRebind() {
  if (!map) return;
  layers.renderAllFeatures(filteredFeatures.value, map);

  // Register all layers for multi-selection and setup sync dragging
  layers.featureLayerManager.layers.forEach((layer, featureId) => {
    multiSelect.registerLayer(featureId, layer);
    setupSyncDrag(featureId, layer);
  });
}

// Track drag state for synchronized dragging
let dragStartPositions = new Map();
let isDragging = false;
let draggedFeatureId = null;

function setupSyncDrag(featureId, layer) {
  // Remove old listeners if they exist
  if (layer.__syncDragListeners) {
    layer.off("pm:dragstart", layer.__syncDragListeners.dragstart);
    layer.off("pm:drag", layer.__syncDragListeners.drag);
    layer.off("pm:dragend", layer.__syncDragListeners.dragend);
  }

  const dragstartHandler = (e) => {
    if (!multiSelect.isSelected(featureId)) return;

    isDragging = true;
    draggedFeatureId = featureId;
    dragStartPositions.clear();

    // Store initial position of the dragged layer
    const draggedLayer = e.layer;
    if (
      draggedLayer instanceof L.Marker ||
      draggedLayer instanceof L.CircleMarker ||
      draggedLayer instanceof L.Circle
    ) {
      dragStartPositions.set(featureId, draggedLayer.getLatLng());
    } else if (
      draggedLayer instanceof L.Polyline ||
      draggedLayer instanceof L.Polygon
    ) {
      dragStartPositions.set(featureId, draggedLayer.getLatLngs());
    }

    // Store initial positions of all other selected layers
    multiSelect.getSelectedIds().forEach((id) => {
      if (id === featureId) return; // Skip the dragged layer

      const selectedLayer = layers.featureLayerManager.layers.get(id);
      if (!selectedLayer) return;

      if (
        selectedLayer instanceof L.Marker ||
        selectedLayer instanceof L.CircleMarker ||
        selectedLayer instanceof L.Circle
      ) {
        dragStartPositions.set(id, selectedLayer.getLatLng());
      } else if (
        selectedLayer instanceof L.Polyline ||
        selectedLayer instanceof L.Polygon
      ) {
        dragStartPositions.set(id, selectedLayer.getLatLngs());
      }
    });
  };

  const dragHandler = (e) => {
    if (!isDragging || draggedFeatureId !== featureId) return;
    if (!multiSelect.isSelected(featureId)) return;

    const currentLayer = e.layer;
    let currentPos;

    // Get current position of dragged layer
    if (
      currentLayer instanceof L.Marker ||
      currentLayer instanceof L.CircleMarker ||
      currentLayer instanceof L.Circle
    ) {
      currentPos = currentLayer.getLatLng();
    } else if (
      currentLayer instanceof L.Polyline ||
      currentLayer instanceof L.Polygon
    ) {
      const bounds = currentLayer.getBounds();
      currentPos = bounds.getCenter();
    }

    if (!currentPos) return;

    // Calculate delta from initial position stored in dragStartPositions
    const initialData = dragStartPositions.get(featureId);
    let initialPos;

    if (
      currentLayer instanceof L.Marker ||
      currentLayer instanceof L.CircleMarker ||
      currentLayer instanceof L.Circle
    ) {
      initialPos = initialData;
    } else if (
      currentLayer instanceof L.Polyline ||
      currentLayer instanceof L.Polygon
    ) {
      if (initialData) {
        // Compute center from initial latlngs
        initialPos = L.polygon(
          Array.isArray(initialData[0]) ? initialData[0] : initialData,
        )
          .getBounds()
          .getCenter();
      }
    }

    if (!initialPos) return;

    const deltaLat = currentPos.lat - initialPos.lat;
    const deltaLng = currentPos.lng - initialPos.lng;

    // Move all other selected layers by the same delta
    dragStartPositions.forEach((startPos, id) => {
      if (id === featureId) return; // Skip the dragged layer itself

      const selectedLayer = layers.featureLayerManager.layers.get(id);
      if (!selectedLayer) return;

      if (
        selectedLayer instanceof L.Marker ||
        selectedLayer instanceof L.CircleMarker ||
        selectedLayer instanceof L.Circle
      ) {
        selectedLayer.setLatLng([
          startPos.lat + deltaLat,
          startPos.lng + deltaLng,
        ]);
      } else if (
        selectedLayer instanceof L.Polyline ||
        selectedLayer instanceof L.Polygon
      ) {
        const shiftedLatLngs = shiftLatLngsRecursive(
          startPos,
          deltaLat,
          deltaLng,
        );
        selectedLayer.setLatLngs(shiftedLatLngs);
      }
    });

    // Update decorators to follow layers during drag
    multiSelect.updateDecorators();
  };

  const dragendHandler = (e) => {
    if (draggedFeatureId === featureId) {
      isDragging = false;
      draggedFeatureId = null;
      dragStartPositions.clear();

      // Emit update events for all moved layers
      if (multiSelect.hasSelection.value) {
        multiSelect.getSelectedIds().forEach((id) => {
          const movedLayer = layers.featureLayerManager.layers.get(id);
          if (movedLayer) {
            emit("feature-updated", { id });
          }
        });
      }
    }
  };

  // Attach listeners
  layer.on("pm:dragstart", dragstartHandler);
  layer.on("pm:drag", dragHandler);
  layer.on("pm:dragend", dragendHandler);

  // Store references for cleanup
  layer.__syncDragListeners = {
    dragstart: dragstartHandler,
    drag: dragHandler,
    dragend: dragendHandler,
  };
}

function shiftLatLngsRecursive(latlngs, deltaLat, deltaLng) {
  if (Array.isArray(latlngs)) {
    return latlngs.map((item) => {
      if (item && typeof item === "object" && "lat" in item && "lng" in item) {
        return L.latLng(item.lat + deltaLat, item.lng + deltaLng);
      } else if (Array.isArray(item)) {
        return shiftLatLngsRecursive(item, deltaLat, deltaLng);
      }
      return item;
    });
  }
  return latlngs;
}

onMounted(() => {
  map = L.map("map", {
    boxZoom: false,
  }).setView([52.9399, -73.5491], 5);
  layers.initializeBaseLayers(map);
  timeline.loadRegionsForYear(timeline.selectedYear.value, map, true);
  drawing.initializeDrawing(map);

  // Setup click handler for multi-selection
  layers.featureLayerManager.setClickHandler((featureId, isCtrlPressed) => {
    multiSelect.handleFeatureClick(featureId, isCtrlPressed);
  });

  // Listen for newly created features from Leaflet.pm and register them for multi-selection
  let drawCounter = 0;
  map.on("pm:create", (e) => {
    const layer = e.layer;
    const featureId = `drawn-${Date.now()}-${drawCounter++}`;

    // Register for multi-selection
    multiSelect.registerLayer(featureId, layer);

    // Make it clickable
    layer.on("click", (clickEvent) => {
      clickEvent.originalEvent?.stopPropagation();
      const isCtrlPressed =
        clickEvent.originalEvent?.ctrlKey || clickEvent.originalEvent?.metaKey;
      multiSelect.handleFeatureClick(featureId, isCtrlPressed);
    });

    // Setup sync drag for this new layer
    setupSyncDrag(featureId, layer);
  });

  // Listen for removed features
  map.on("pm:remove", (e) => {
    const layer = e.layer;
    // Find and unregister the layer
    const featureId = multiSelect.getFeatureIdFromLayer(layer);
    if (featureId) {
      multiSelect.unregisterLayer(featureId);
    }
  });

  // Click on map background to deselect all
  map.on("click", (e) => {
    // Deselect only if not clicking on a feature (no Ctrl key)
    // The click handler on features will be called first and stop propagation
    const target = e.originalEvent?.target;
    const isFeatureClick =
      target?.classList?.contains("leaflet-interactive") ||
      target?.closest?.(".leaflet-interactive");

    if (!isFeatureClick) {
      multiSelect.clearSelection();
    }
  });

  // Deselect when drag mode is toggled off
  map.on("pm:globaldragmodetoggled", (e) => {
    if (!e.enabled) {
      multiSelect.clearSelection();
    }
  });

  renderAllAndRebind();
});

onBeforeUnmount(() => {
  if (map) {
    layers.clearAllLayers(map);
    map.remove();
    map = null;
  }
});

// Timeline year changes
watch(
  () => timeline.selectedYear.value,
  (newYear) => {
    if (!map) return;
    timeline.loadRegionsForYear(newYear, map);
    renderAllAndRebind();
  },
);

// Features rerender
watch(
  () => props.features,
  () => {
    if (!map) return;
    renderAllAndRebind();
  },
);

// Visibility toggle
watch(
  () => props.featureVisibility,
  (newVisibility) => {
    if (!newVisibility) return;
    newVisibility.forEach((visible, featureId) => {
      layers.featureLayerManager.toggleFeature(featureId, visible);
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
