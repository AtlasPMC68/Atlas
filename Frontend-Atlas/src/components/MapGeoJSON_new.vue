<template>
  <div class="relative h-full w-full z-0">
    <div id="map" style="height: 80vh; width: 100%"></div>
    <TimelineSlider v-model:year="timeline.selectedYear" />

    <!-- Bouton de suppression visible seulement en mode édition -->
    <div v-if="editMode" class="absolute top-4 right-4 z-10">
      <button
        @click="editing.toggleDeleteMode()"
        :class="[
          'px-4 py-2 rounded-lg font-medium transition-colors duration-200 active:bg-red-800',
          editing.isDeleteMode.value
            ? 'bg-red-600 text-white hover:bg-red-700'
            : 'bg-gray-600 text-white hover:bg-gray-700',
        ]"
      >
        {{ editing.isDeleteMode.value ? "Mode Suppression" : "Supprimer" }}
        <span class="ml-2 text-xs text-black">{{ editing.isDeleteMode.value }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch, computed } from "vue";
import L from "leaflet";
import "leaflet-geometryutil"; // ← requis pour que arrowheads fonctionne
import "leaflet-arrowheads"; // ← ajoute la méthode `arrowheads` aux polylines
import TimelineSlider from "../components/TimelineSlider.vue";

// Composables
import { useMapLayers } from '../composables/useMapLayers.js';
import { useMapTimeline } from '../composables/useMapTimeline.js';
import { useMapEditing } from '../composables/useMapEditing.js';
import { useMapEvents } from '../composables/useMapEvents.js';

// Props reçues de la vue parent
const props = defineProps({
  mapId: String,
  features: Array,
  featureVisibility: Map,
  editMode: {
    type: Boolean,
    default: false,
  },
  activeEditMode: {
    type: String,
    default: null,
  },
  selectedShape: {
    type: String,
    default: null,
  },
});

// Émissions vers la vue parent
const emit = defineEmits(["features-loaded", "mode-change"]);

let map = null;

// Initialize composables
const layers = useMapLayers(props, emit);
const timeline = useMapTimeline();
const editing = useMapEditing(props, emit);
const events = useMapEvents(props, emit, layers, editing);

// Computed properties
const filteredFeatures = computed(() => {
  return props.features.filter(
    (feature) =>
      new Date(feature.start_date).getFullYear() <= timeline.selectedYear.value &&
      (!feature.end_date ||
        new Date(feature.end_date).getFullYear() >= timeline.selectedYear.value)
  );
});

// Main rendering functions

// Render all features based on current filters
function renderAllFeatures() {
  const currentFeatures = filteredFeatures.value;
  const currentIds = new Set(currentFeatures.map((f) => f.id));
  const previousIds = new Set(); // We'll track this differently

  // Clear features that are no longer visible
  layers.featureLayerManager.layers.forEach((layer, featureId) => {
    if (!currentIds.has(featureId)) {
      map.removeLayer(layer);
      layers.featureLayerManager.layers.delete(featureId);
    }
  });

  const newFeatures = currentFeatures.filter((f) => !previousIds.has(f.id));
  const featuresByType = {
    point: newFeatures.filter((f) => f.type === "point"),
    polygon: newFeatures.filter((f) => f.type === "zone"),
    arrow: newFeatures.filter((f) => f.type === "arrow"),
    square: newFeatures.filter((f) => f.type === "square"),
    rectangle: newFeatures.filter((f) => f.type === "rectangle"),
    circle: newFeatures.filter((f) => f.type === "circle"),
    triangle: newFeatures.filter((f) => f.type === "triangle"),
    oval: newFeatures.filter((f) => f.type === "oval"),
  };

  // Render features using layer composable
  layers.renderCities(featuresByType.point, map);
  layers.renderZones(featuresByType.polygon, map);
  layers.renderArrows(featuresByType.arrow, map);
  layers.renderShapes(featuresByType.square, map);
  layers.renderShapes(featuresByType.rectangle, map);
  layers.renderShapes(featuresByType.circle, map);
  layers.renderShapes(featuresByType.triangle, map);
  layers.renderShapes(featuresByType.oval, map);

  emit("features-loaded", currentFeatures);
}

// Initialize map and layers
function initializeMap() {
  map = L.map("map").setView([52.9399, -73.5491], 5);

  // Initialize base layers
  layers.initializeBaseLayers(map);

  // Load initial regions
  timeline.loadRegionsForYear(timeline.selectedYear.value, map, true);

  // Initialize edit controls if needed
  if (props.editMode) {
    initializeEditControls();
  }
}

// Initialize edit controls
function initializeEditControls() {
  if (!props.editMode) return;

  console.log("Initializing edit controls:", {
    editMode: props.editMode,
    activeEditMode: props.activeEditMode,
    selectedShape: props.selectedShape,
  });

  // Layer for drawn items
  layers.drawnItems = new L.FeatureGroup();
  map.addLayer(layers.drawnItems);

  // Update cursor according to edit mode
  updateMapCursor();

  // Listen to events according to active mode
  console.log("🎛️ Initializing edit controls:", {
    editMode: props.editMode,
    activeEditMode: props.activeEditMode,
    selectedShape: props.selectedShape,
  });

  // Selection/move events always available in edit mode
  if (props.editMode) {
    console.log("🎯 Setting up selection and move events");
    map.on("mousedown", events.handleMoveMouseDown);
    map.on("mousemove", events.handleMoveMouseMove);
    map.on("mouseup", events.handleMoveMouseUp);
    map.on("keydown", events.handleKeyDown);
    // Make existing shapes clickable
    makeFeaturesClickable();
  }

  // Set up specific events based on active mode
  if (props.activeEditMode === "CREATE_LINE" || props.activeEditMode === "CREATE_FREE_LINE") {
    console.log("📏 Setting up line drawing events");
    map.on("mousedown", events.handleMouseDown);
    map.on("mousemove", events.handleMouseMove);
    map.on("mouseup", events.handleMouseUp);
  } else if (props.activeEditMode === "CREATE_SHAPES") {
    console.log("🔷 Setting up shape drawing events");
    map.on("mousedown", events.handleShapeMouseDown);
    map.on("mousemove", events.handleShapeMouseMove);
    map.on("mouseup", events.handleShapeMouseUp);
    map.on("dragstart", events.preventDragDuringShapeDrawing);
  } else if (props.activeEditMode === "CREATE_POLYGON") {
    console.log("⬡ Setting up polygon drawing events");
    map.on("contextmenu", events.handleRightClick); // Right click to finish polygon
  }

  // Listen to map clicks according to mode
  map.on("click", events.handleMapClick);
  map.on("dblclick", events.handleMapDoubleClick);
}

// Update map cursor according to edit mode
function updateMapCursor() {
  if (!map) return;

  const mapContainer = map.getContainer();

  if (props.editMode && props.activeEditMode) {
    // In edit mode with active mode, use crosshair cursor
    mapContainer.style.cursor = "crosshair";
  } else if (props.editMode) {
    // In edit mode but not active mode (selection/move), normal cursor
    mapContainer.style.cursor = "";
  } else {
    // Not in edit mode, normal cursor
    mapContainer.style.cursor = "";
  }
}

// Make existing shapes clickable for selection
function makeFeaturesClickable() {
  console.log("🎯 Making features clickable for selection - Total layers:", layers.featureLayerManager.layers.size);

  // For each existing layer in featureLayerManager, make it clickable
  layers.featureLayerManager.layers.forEach((layer, featureId) => {
    layers.featureLayerManager.makeLayerClickable(featureId, layer);
    console.log("✅ Made feature layer clickable:", featureId, layer.constructor.name);
  });

  // Also make drawn items clickable
  if (layers.drawnItems) {
    layers.drawnItems.eachLayer((layer) => {
      // For temporary layers, use temporary ID
      const tempId = "temp_" + Math.random();
      layers.featureLayerManager.makeLayerClickable(tempId, layer);
      console.log("✅ Made drawn layer clickable:", tempId, layer.constructor.name);
    });
  }
}

// Handle feature click for selection/deletion or movement
function handleFeatureClick(featureId, isCtrlPressed) {
  console.log("🎯 FEATURE CLICK HANDLER CALLED:", featureId, "CTRL:", isCtrlPressed, "Delete mode:", editing.isDeleteMode.value, "Current selection:", Array.from(events.selectedFeatures));

  // If in delete mode, delete clicked item
  console.log("🗑️ Checking delete mode - isDeleteMode:", editing.isDeleteMode.value);
  if (editing.isDeleteMode.value) {
    console.log("🗑️ Delete mode active, deleting feature:", featureId);
    editing.deleteSelectedFeatures([featureId], layers.featureLayerManager, map, emit);
    return;
  }

  // If we just finished a drag, ignore this click to avoid accidental deselection
  if (events.justFinishedDrag) {
    console.log("🚫 Ignoring click after drag to prevent accidental deselection");
    events.justFinishedDrag = false;
    return;
  }

  if (isCtrlPressed) {
    // Multi-selection: toggle selection
    if (events.selectedFeatures.has(featureId)) {
      events.selectedFeatures.delete(featureId);
      console.log("❌ Deselected feature:", featureId);
    } else {
      events.selectedFeatures.add(featureId);
      console.log("✅ Selected feature:", featureId);
    }
  } else {
    // Single click: logic according to number of selected items
    if (events.selectedFeatures.size === 1 && events.selectedFeatures.has(featureId)) {
      // Single selected item and it's this one: deselect it
      events.selectedFeatures.clear();
      console.log("❌ Deselected single feature:", featureId);
    } else {
      // Multiple items selected OR click on unselected item:
      // Deselect all and select only this item
      events.selectedFeatures.clear();
      events.selectedFeatures.add(featureId);
      console.log("🔄 Single selection (cleared others):", featureId);
    }
  }

  console.log("📊 New selection:", Array.from(events.selectedFeatures));
  editing.updateFeatureSelectionVisual(map);
}

// ===== LIFECYCLE AND WATCHERS =====

// Display the map
onMounted(() => {
  initializeMap();
});

// Watchers
watch(timeline.selectedYear, (newYear) => {
  timeline.debouncedUpdate(newYear, map, emit, layers);
});

watch(
  () => props.features,
  () => {
    renderAllFeatures();
  },
  { deep: true }
);

watch(
  () => props.featureVisibility,
  (newVisibility) => {
    newVisibility.forEach((visible, featureId) => {
      layers.featureLayerManager.toggleFeature(featureId, visible);
    });
  },
  { deep: true }
);

// Watcher for edit mode
watch(
  () => props.editMode,
  (newEditMode) => {
    // If leaving edit mode and there's an ongoing polygon, finish it
    if (
      !newEditMode &&
      props.activeEditMode === "CREATE_POLYGON" &&
      events.currentPolygonPoints.length >= 3
    ) {
      console.log("🔺 Auto-finishing polygon when leaving edit mode");
      events.finishPolygon(map, emit);
    }

    if (newEditMode) {
      initializeEditControls();
      // Reload features when entering edit mode
      timeline.debouncedUpdate(timeline.selectedYear.value, map, emit, layers);
    } else {
      cleanupEditMode();
    }

    // Update cursor
    updateMapCursor();
  }
);

// Watcher for delete mode
watch(
  () => props.activeEditMode,
  (newMode) => {
    editing.isDeleteMode.value = newMode === "DELETE_FEATURE";
    console.log("🔄 isDeleteMode updated to:", editing.isDeleteMode.value, "from mode:", newMode);
  },
  { immediate: true } // Execute immediately on mount
);

// Watcher for changing edit mode
watch(
  () => props.activeEditMode,
  (newMode, oldMode) => {
    console.log("🔄 Edit mode changed:", { oldMode, newMode });

    // If leaving CREATE_POLYGON mode, automatically finish polygon
    if (
      oldMode === "CREATE_POLYGON" &&
      newMode !== "CREATE_POLYGON" &&
      events.currentPolygonPoints.length >= 3
    ) {
      console.log("🔺 Auto-finishing polygon when leaving CREATE_POLYGON mode");
      events.finishPolygon(map, emit);
    }

    // Clean up previous state
    if (oldMode) {
      cleanupCurrentDrawing();
    }

    // Clean up all edit events
    map.off("mousedown", events.handleMouseDown);
    map.off("mousemove", events.handleMouseMove);
    map.off("mouseup", events.handleMouseUp);
    map.off("contextmenu", events.handleRightClick);
    map.off("mousedown", events.handleShapeMouseDown);
    map.off("mousemove", events.handleShapeMouseMove);
    map.off("mouseup", events.handleShapeMouseUp);
    map.off("dragstart", events.preventDragDuringShapeDrawing);
    map.off("mousedown", events.handleMoveMouseDown);
    map.off("mousemove", events.handleMoveMouseMove);
    map.off("mouseup", events.handleMoveMouseUp);
    map.off("keydown", events.handleKeyDown);

    // Reattach events according to new mode
    if (newMode === "CREATE_LINE" || newMode === "CREATE_FREE_LINE") {
      console.log("📏 Reattaching line drawing events");
      map.on("mousedown", events.handleMouseDown);
      map.on("mousemove", events.handleMouseMove);
      map.on("mouseup", events.handleMouseUp);
    } else if (newMode === "CREATE_SHAPES") {
      console.log("🔷 Reattaching shape drawing events");
      map.on("mousedown", events.handleShapeMouseDown);
      map.on("mousemove", events.handleShapeMouseMove);
      map.on("mouseup", events.handleShapeMouseUp);
      map.on("dragstart", events.preventDragDuringShapeDrawing);
    } else if (newMode === "CREATE_POLYGON") {
      console.log("⬡ Reattaching polygon drawing events");
      map.on("contextmenu", events.handleRightClick);
    } else {
      // Selection/movement mode (no active mode or default mode)
      console.log("🎯 Reattaching selection and move events for default mode");
      map.on("mousedown", events.handleMoveMouseDown);
      map.on("mousemove", events.handleMoveMouseMove);
      map.on("mouseup", events.handleMoveMouseUp);
    }

    // ALWAYS attach handleKeyDown in edit mode to allow deletion
    if (props.editMode) {
      console.log("🔄 Attaching keydown event for delete functionality");
      map.on("keydown", events.handleKeyDown);
    }

    // Update cursor
    updateMapCursor();
  }
);

// Watcher for selected shape
watch(
  () => props.selectedShape,
  (newShape, oldShape) => {
    console.log("Shape changed:", { oldShape, newShape });
  }
);

// Cleanup current drawing
function cleanupCurrentDrawing() {
  events.freeLinePoints = [];
  events.isDrawingFree = false;
  if (events.tempFreeLine) {
    layers.drawnItems.removeLayer(events.tempFreeLine);
    events.tempFreeLine = null;
  }
}

// Cleanup edit mode
function cleanupEditMode() {
  if (layers.drawnItems) {
    // Clean circles from drawnItems collection
    layers.drawnItems.eachLayer((layer) => {
      if (layer instanceof L.CircleMarker) {
        layers.allCircles.value.delete(layer);
      }
    });
    map.removeLayer(layers.drawnItems);
    layers.drawnItems = null;
  }

  // Clean up all events
  map.off("mousedown", events.handleMouseDown);
  map.off("mousemove", events.handleMouseMove);
  map.off("mouseup", events.handleMouseUp);
  map.off("contextmenu", events.handleRightClick);
  map.off("click", events.handleMapClick);
  map.off("dblclick", events.handleMapDoubleClick);

  // Clean up shape events
  map.off("mousedown", events.handleShapeMouseDown);
  map.off("mousemove", events.handleShapeMouseMove);
  map.off("mouseup", events.handleShapeMouseUp);
  map.off("dragstart", events.preventDragDuringShapeDrawing);

  // Clean up movement events (only if leaving edit mode)
  if (!props.editMode) {
    map.off("mousedown", events.handleMoveMouseDown);
    map.off("mousemove", events.handleMoveMouseMove);
    map.off("mouseup", events.handleMoveMouseUp);
    map.off("keydown", events.handleKeyDown);
  }

  // Clean up state variables
  events.currentPolygonPoints = [];
  events.cleanupTempLine();
  events.cleanupTempShape();

  // Clean up selection and movement
  events.selectedFeatures.clear();
  events.isDraggingFeatures = false;
  events.dragStartPoint = null;
  events.originalPositions.clear();
  events.justFinishedDrag = false;

  // Update cursor
  updateMapCursor();

  // Reload all features when leaving edit mode
  setTimeout(() => {
    timeline.debouncedUpdate(timeline.selectedYear.value, map, emit, layers);
  }, 100);
}
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
  transform: rotate(0deg); /* statique pour l'instant */
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