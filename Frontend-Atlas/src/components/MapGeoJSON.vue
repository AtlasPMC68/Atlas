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
// IMPORTS DES COMPOSABLES
// ========================================
import { useMapLayers } from '../composables/useMapLayers.js';
import { useMapEditing } from '../composables/useMapEditing.js';
import { useMapEvents } from '../composables/useMapEvents.js';
import { useMapTimeline } from '../composables/useMapTimeline.js';
import { useMapInit } from '../composables/useMapInit.js';

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

// ========================================
// INITIALISATION DES COMPOSABLES
// ========================================
const layers = useMapLayers(props, emit);
const editing = useMapEditing(props, emit);
const events = useMapEvents(props, emit, layers, editing);
const timeline = useMapTimeline();
const init = useMapInit(props, emit, layers, events, editing, timeline);

// ========================================
// VARIABLES LOCALES (NÉCESSAIRES)
// ========================================
let map = null;
let baseTileLayer = null;

// /* ========================================
//  * ANCIEN CODE - CONSERVÉ EN COMMENTAIRE
//  * ========================================
// const selectedYear = ref(1740); 
// const previousFeatureIds = ref(new Set());
// const isDeleteMode = ref(false);
// 
// const availableYears = [
//   1400, 1500, 1530, 1600, 1650, 1700, 1715, 1783, 1800, 1815, 1880, 1900, 1914,
//   1920, 1930, 1938, 1945, 1960, 1994, 2000, 2010,
// ];
// 
// let currentRegionsLayer = null;
// let labelLayer = null;
// let citiesLayer = null;
// let zonesLayer = null;
// let arrowsLayer = null;
// let drawnItems = null;
// let currentLinePoints = [];
// let currentPolygonPoints = [];
// let tempLine = null;
// let tempPolygon = null;
// let allCircles = new Set();
// let shapeState = null;
// let shapeStartPoint = null;
// let shapeEndPoint = null;
// let tempShape = null;
// let lastMousePos = null;
// let isDrawingShape = false;
// let selectedFeatures = new Set();
// let isDraggingFeatures = false;
// let dragStartPoint = null;
// let originalPositions = new Map();
// let justFinishedDrag = false;
// let resizeHandles = new Map();
// let isResizing = false;
// let resizeStartPoint = null;
// let resizeHandle = null;
// let originalGeometry = null;
// let originalBounds = null;
// let tempResizeShape = null;
// let isDrawingLine = false;
// let lineStartPoint = null;
// let isDrawingFree = false;
// let freeLinePoints = [];
// let tempFreeLine = null;
// const SMOOTHING_MIN_DISTANCE = 3;
// const BASE_ZOOM = 5;
// const BASE_RADIUS = 3;
// const ZOOM_FACTOR = 1.5;
// 
// function smoothFreeLinePoints(points) { ... }
// function getRadiusForZoom(currentZoom) { ... }
// function updateCircleSizes() { ... }
// 
// const featureLayerManager = {
//   layers: new Map(),
//   addFeatureLayer(featureId, layer) { ... },
//   makeLayerClickable(featureId, layer) { ... },
//   toggleFeature(featureId, visible) { ... },
//   clearAllFeatures() { ... },
// };
// 
// const filteredFeatures = computed(() => { ... });
// async function fetchFeaturesAndRender(year) { ... }
// function getClosestAvailableYear(year) { ... }
// function loadRegionsForYear(year, isFirstTime = false) { ... }
// function renderCities(features) { ... }
// function renderZones(features) { ... }
// function renderArrows(features) { ... }
// function renderShapes(features) { ... }
// function renderAllFeatures() { ... }
// function removeGeoJSONLayers() { ... }
// async function loadAllLayersForYear(year) { ... }
// function debounce(fn, delay) { ... }
// function transformNormalizedToWorld(geojson, anchorLat, anchorLng, sizeMeters) { ... }
// function toArray(maybeArray) { ... }
// const debouncedUpdate = debounce((year) => { ... }, 100);
// */ 

// ========================================
// COMPUTED PROPERTIES (UTILISANT LES COMPOSABLES)
// ========================================
const filteredFeatures = computed(() => {
  return props.features.filter(
    (feature) =>
      new Date(feature.start_date).getFullYear() <= timeline.selectedYear.value &&
      (!feature.end_date ||
        new Date(feature.end_date).getFullYear() >= timeline.selectedYear.value)
  );
});

// ========================================
// FONCTIONS PRINCIPALES
// ========================================

// Display the map
onMounted(() => {
  map = L.map("map").setView([52.9399, -73.5491], 5);

  // Background map
  baseTileLayer = L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
    {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 19,
    }
  ).addTo(map);

  // Initialiser les couches de base
  layers.initializeBaseLayers(map);

  // Charger les régions pour l'année initiale
  timeline.loadRegionsForYear(timeline.selectedYear.value, map, true);

  // Ajouter l'événement zoom pour adapter la taille des cercles
  map.on("zoomend", () => layers.updateCircleSizes(map));

  // Initialiser l'édition si nécessaire
  if (props.editMode) {
    init.initializeEditControls(map);
    // Définir le handler de clic pour les features
    layers.featureLayerManager.setClickHandler((featureId, isCtrlPressed) => {
      init.handleFeatureClick(featureId, isCtrlPressed, map);
    });
  }
});

// Nettoyage à la destruction du composant
onBeforeUnmount(() => {
  if (map) {
    init.cleanupEditMode(map);
    layers.clearAllLayers(map);
    map.remove();
    map = null;
  }
});

// ========================================
// FONCTIONS POUR LA VUE PARENT
// ========================================

// Basculer le mode suppression
function toggleDeleteMode() {
  if (props.activeEditMode === "DELETE_FEATURE") {
    emit("mode-change", null);
  } else {
    emit("mode-change", "DELETE_FEATURE");
  }
}

// /* ========================================
//  * ANCIENNES FONCTIONS - CONSERVÉES EN COMMENTAIRE
//  * ========================================
// 
// function initializeEditControls() { ... }
// function updateMapCursor() { ... }
// function handleMouseDown(e) { ... }
// function handleMouseMove(e) { ... }
// function handleMouseUp(e) { ... }
// function cleanupTempLine() { ... }
// function cleanupTempShape() { ... }
// function preventDragDuringShapeDrawing(e) { ... }
// function handleMapClick(e) { ... }
// function handleShapeMouseDown(e) { ... }
// function handleShapeMouseUp(e) { ... }
// function createSquare(center, sizePoint) { ... }
// function createRectangle(startCorner, endCorner) { ... }
// function createCircle(center, edgePoint) { ... }
// function createTriangle(center, sizePoint) { ... }
// function createOval(center, heightPoint, widthPoint) { ... }
// function updateTempSquareFromCenter(center, sizePoint) { ... }
// function updateTempRectangleFromCorners(startCorner, endCorner) { ... }
// function updateTempCircleFromCenter(center, edgePoint) { ... }
// function updateTempTriangleFromCenter(center, sizePoint) { ... }
// function updateTempOvalHeight(center, heightPoint) { ... }
// function updateTempOvalWidth(center, heightPoint, widthPoint) { ... }
// function squareToFeatureFromCenter(center, sizePoint) { ... }
// function rectangleToFeatureFromCorners(startCorner, endCorner) { ... }
// function circleToFeatureFromCenter(center, edgePoint) { ... }
// function triangleToFeatureFromCenter(center, sizePoint) { ... }
// function ovalToFeatureFromCenter(center, heightPoint, widthPoint) { ... }
// function handleShapeMouseMove(e) { ... }
// function finishFreeLine() { ... }
// function handleRightClick(e) { ... }
// function handleMapDoubleClick(e) { ... }
// function createPointAt(latlng) { ... }
// function createLine(startLatLng, endLatLng) { ... }
// function handlePolygonClick(latlng) { ... }
// function updatePolygonLines() { ... }
// function finishPolygon() { ... }
// async function saveFeature(featureData) { ... }
// function makeFeaturesClickable() { ... }
// function handleFeatureClick(featureId, isCtrlPressed) { ... }
// function updateFeatureSelectionVisual() { ... }
// function handleMoveMouseDown(e) { ... }
// function getFeatureAtPosition(latlng) { ... }
// function handleMoveMouseMove(e) { ... }
// function handleMoveMouseUp(e) { ... }
// function handleKeyDown(e) { ... }
// async function updateFeaturePosition(feature, deltaLat, deltaLng) { ... }
// async function deleteSelectedFeatures() { ... }
// async function deleteFeature(featureId) { ... }
// function updateGeometryCoordinates(geometry, deltaLat, deltaLng) { ... }
// function cleanupEditMode() { ... }
// function cleanupCurrentDrawing() { ... }
// */ 

// ========================================
// WATCHERS
// ========================================

// Watcher pour le mode édition
watch(
  () => props.editMode,
  (newEditMode) => {
    // Si on quitte le mode édition et qu'il y a un polygone en cours, le terminer
    if (
      !newEditMode &&
      props.activeEditMode === "CREATE_POLYGON" &&
      events.currentPolygonPoints.value.length >= 3
    ) {
      editing.finishPolygon(
        events.currentPolygonPoints.value,
        events.tempPolygon.value,
        map,
        layers
      );
    }

    if (newEditMode) {
      // Réinitialiser drawnItems si nécessaire
      if (!layers.drawnItems.value) {
        layers.initializeBaseLayers(map);
      }
      
      init.initializeEditControls(map);
      // Définir le handler de clic
      layers.featureLayerManager.setClickHandler((featureId, isCtrlPressed) => {
        init.handleFeatureClick(featureId, isCtrlPressed, map);
      });
      // Recharger les features quand on entre en mode édition
      layers.renderAllFeatures(filteredFeatures.value, map);
    } else {
      init.cleanupEditMode(map);
    }

    // Mettre à jour le curseur
    init.updateMapCursor(map);
  }
);

// Watcher pour mettre à jour isDeleteMode
watch(
  () => props.activeEditMode,
  (newMode) => {
    editing.isDeleteMode.value = newMode === "DELETE_FEATURE";
  },
  { immediate: true }
);

// Watcher pour changer de mode d'édition
watch(
  () => props.activeEditMode,
  (newMode, oldMode) => {
    // Si on quitte le mode CREATE_POLYGON, terminer automatiquement le polygone
    if (
      oldMode === "CREATE_POLYGON" &&
      newMode !== "CREATE_POLYGON" &&
      events.currentPolygonPoints.value.length >= 3
    ) {
      editing.finishPolygon(
        events.currentPolygonPoints.value,
        events.tempPolygon.value,
        map,
        layers
      );
    }

    // Nettoyer l'état précédent
    if (oldMode) {
      events.cleanupCurrentDrawing();
    }

    // Nettoyer tous les événements d'édition
    init.detachEditEventHandlers(map);

    // Réattacher les événements selon le nouveau mode
    init.attachEditEventHandlers(map);

    // Mettre à jour le curseur
    init.updateMapCursor(map);
  }
);

// Watcher pour la forme sélectionnée
watch(
  () => props.selectedShape,
  (newShape, oldShape) => {
    // Shape selection changed
  }
);

// Watcher pour l'année sélectionnée
watch(
  () => timeline.selectedYear.value,
  (newYear) => {
    timeline.loadRegionsForYear(newYear, map);
    layers.renderAllFeatures(filteredFeatures.value, map);
  }
);

// Watcher pour les features
watch(
  () => props.features,
  () => {
    layers.renderAllFeatures(filteredFeatures.value, map);
  },
  { deep: true }
);

// Watcher pour la visibilité des features
watch(
  () => props.featureVisibility,
  (newVisibility) => {
    newVisibility.forEach((visible, featureId) => {
      layers.featureLayerManager.toggleFeature(featureId, visible);
    });
  },
  { deep: true }
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
