<template>
  <div class="relative h-full w-full z-0">
    <div id="map" style="height: 80vh; width: 100%"></div>
    <TimelineSlider v-model:year="selectedYear" />

    <!-- Bouton de suppression visible seulement en mode édition -->
    <div v-if="editMode" class="absolute top-4 right-4 z-10">
      <button
        @click="toggleDeleteMode()"
        :class="[
          'px-4 py-2 rounded-lg font-medium transition-colors duration-200 active:bg-red-800',
          isDeleteMode.value
            ? 'bg-red-600 text-white hover:bg-red-700'
            : 'bg-gray-600 text-white hover:bg-gray-700',
        ]"
      >
        {{ isDeleteMode.value ? "Mode Suppression" : "Supprimer" }}
        <span class="ml-2 text-xs text-black">{{ isDeleteMode.value }}</span>
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

const selectedYear = ref(1740); // initial displayed year
const previousFeatureIds = ref(new Set());
const isDeleteMode = ref(false); // Si on est en mode suppression

// List of available years
const availableYears = [
  1400, 1500, 1530, 1600, 1650, 1700, 1715, 1783, 1800, 1815, 1880, 1900, 1914,
  1920, 1930, 1938, 1945, 1960, 1994, 2000, 2010,
];

let map = null;
let currentRegionsLayer = null;
let baseTileLayer = null;
let labelLayer = null;
const mockedCities = [
  { name: "Montréal", lat: 45.5017, lng: -73.5673, foundation_year: 1642 },
  { name: "Québec", lat: 46.8139, lng: -71.2082, foundation_year: 1608 },
  { name: "Trois-Rivières", lat: 46.343, lng: -72.5406, foundation_year: 1634 },
];

let citiesLayer = null;
let zonesLayer = null;
let arrowsLayer = null;
let drawnItems = null;

// Variables d'état pour l'édition
let currentLinePoints = [];
let currentPolygonPoints = [];
let tempLine = null;
let tempPolygon = null;
let allCircles = new Set(); // Collection de tous les cercles pour les mettre à jour

// Variables pour les formes prédéfinies
let shapeState = null; // 'drawing' | 'adjusting_height' | 'adjusting_width' | null
let shapeStartPoint = null; // Point de départ (coin du carré ou centre pour cercle/triangle)
let shapeEndPoint = null; // Point d'arrivée (coin opposé ou point pour ajuster taille)
let tempShape = null;
let lastMousePos = null; // Dernière position connue de la souris
let isDrawingShape = false; // Indicateur global pour empêcher le dragging

// Variables pour la sélection et le déplacement de formes
let selectedFeatures = new Set(); // Ensemble des IDs des features sélectionnées
let isDraggingFeatures = false; // Si on est en train de déplacer des formes
let dragStartPoint = null; // Point de départ du drag
let originalPositions = new Map(); // Positions originales des formes avant déplacement
let justFinishedDrag = false; // Flag pour éviter la désélection après un drag

// Variables pour le tracé de ligne
let isDrawingLine = false;
let lineStartPoint = null;

// Variables pour le tracé libre (crayon)
let isDrawingFree = false;
let freeLinePoints = [];
let tempFreeLine = null;

// Configuration du lissage
const SMOOTHING_MIN_DISTANCE = 3; // Distance minimale entre points en pixels

// Fonction pour lisser les points de la ligne libre
function smoothFreeLinePoints(points) {
  if (points.length < 2) return points;

  const smoothed = [points[0]]; // Garder le premier point

  for (let i = 1; i < points.length; i++) {
    const lastPoint = smoothed[smoothed.length - 1];
    const currentPoint = points[i];

    // Calculer la distance en pixels à l'écran
    const pixelDistance = map
      .latLngToContainerPoint(lastPoint)
      .distanceTo(map.latLngToContainerPoint(currentPoint));

    // Ajouter le point seulement s'il est assez éloigné du précédent
    if (pixelDistance >= SMOOTHING_MIN_DISTANCE) {
      smoothed.push(currentPoint);
    }
  }

  return smoothed;
}

// Configuration du zoom-adaptatif pour les cercles
const BASE_ZOOM = 5; // Zoom de départ où le rayon est de 3px
const BASE_RADIUS = 3; // Rayon de base
const ZOOM_FACTOR = 1.5; // Facteur de croissance (1.5 = croissance modérée)

// Calculer le rayon en fonction du zoom actuel
function getRadiusForZoom(currentZoom) {
  const zoomDiff = currentZoom - BASE_ZOOM;
  return Math.max(BASE_RADIUS, BASE_RADIUS * Math.pow(ZOOM_FACTOR, zoomDiff));
}

// Mettre à jour tous les cercles existants lors d'un changement de zoom
function updateCircleSizes() {
  const currentZoom = map.getZoom();
  const newRadius = getRadiusForZoom(currentZoom);

  // Mettre à jour tous les cercles de la collection
  allCircles.forEach((circle) => {
    circle.setRadius(newRadius);
  });
}

// Gestionnaire de layers par feature
const featureLayerManager = {
  layers: new Map(),

  addFeatureLayer(featureId, layer) {
    if (this.layers.has(featureId)) {
      // Si c'était un cercle, le retirer de la collection
      const oldLayer = this.layers.get(featureId);
      if (oldLayer instanceof L.CircleMarker) {
        allCircles.delete(oldLayer);
      }
      map.removeLayer(this.layers.get(featureId));
    }
    this.layers.set(featureId, layer);

    // Ajouter à la collection si c'est un cercle
    if (layer instanceof L.CircleMarker) {
      allCircles.add(layer);
    }

    // Rendre le layer cliquable si on est en mode édition
    if (props.editMode) {
      this.makeLayerClickable(featureId, layer);
    }

    // Ajouter seulement si visible
    if (props.featureVisibility.get(featureId)) {
      map.addLayer(layer);
    }
  },

  makeLayerClickable(featureId, layer) {
    console.log(
      "🔧 Making layer clickable:",
      featureId,
      layer.constructor.name
    );

    // Forcer l'interactivité
    layer.options.interactive = true;

    // Éviter les doublons d'événements
    layer.off("click");
    layer.off("mousedown");
    layer.off("mouseup");

    // Attacher les événements avec priorité
    layer.on("mousedown", (e) => {
      console.log(
        "🖱️ LAYER MOUSEDOWN:",
        featureId,
        "Interactive:",
        layer.options.interactive
      );
      e.originalEvent.stopPropagation();
      e.originalEvent.preventDefault();
      // Marquer que c'est un clic sur une forme
      e.target._isFeatureClick = true;
      e.target._featureId = featureId;
    });

    layer.on("click", (e) => {
      console.log(
        "🖱️ LAYER CLICK EVENT:",
        featureId,
        "CTRL:",
        e.originalEvent.ctrlKey,
        "Layer:",
        layer.constructor.name,
        "Interactive:",
        layer.options.interactive
      );
      e.originalEvent.stopPropagation();
      e.originalEvent.preventDefault();
      handleFeatureClick(featureId, e.originalEvent.ctrlKey);
    });

    console.log("✅ Layer made clickable:", featureId);
  },

  toggleFeature(featureId, visible) {
    const layer = this.layers.get(featureId);
    if (layer) {
      if (visible) {
        map.addLayer(layer);
      } else {
        map.removeLayer(layer);
      }
    }
  },

  clearAllFeatures() {
    this.layers.forEach((layer) => {
      // Retirer les cercles de la collection
      if (layer instanceof L.CircleMarker) {
        allCircles.delete(layer);
      }
      map.removeLayer(layer);
    });
    this.layers.clear();
  },
};

const filteredFeatures = computed(() => {
  return props.features.filter(
    (feature) =>
      new Date(feature.start_date).getFullYear() <= selectedYear.value &&
      (!feature.end_date ||
        new Date(feature.end_date).getFullYear() >= selectedYear.value)
  );
});

async function fetchFeaturesAndRender(year) {
  const mapId = "11111111-1111-1111-1111-111111111111";

  try {
    const res = await fetch(`http://localhost:8000/maps/features/${mapId}`);
    if (!res.ok) throw new Error("Failed to fetch features");

    const allFeatures = await res.json();

    // Mettre à jour les features dans le parent
    emit("features-loaded", allFeatures);

    // Filtrer par année
    const features = allFeatures.filter(
      (f) => new Date(f.start_date).getFullYear() <= year
    );

    // Dispatcher selon le type
    const cities = features.filter((f) => f.type === "point");
    const zones = features.filter((f) => f.type === "zone");
    const arrows = features.filter((f) => f.type === "arrow");

    renderCities(cities);
    renderZones(zones);
    renderArrows(arrows);
  } catch (err) {
    console.warn("Erreur fetch features:", err);
  }
}
// Returns the closest available year that is less than or equal to the requested year
function getClosestAvailableYear(year) {
  const sorted = [...availableYears].sort((a, b) => a - b);
  for (let i = sorted.length - 1; i >= 0; i--) {
    if (year >= sorted[i]) return sorted[i];
  }
  return sorted[0]; // default to the earliest year
}

let lastCurrentYear;
// Loads the GeoJSON file named world_(year) and displays its content on the map
function loadRegionsForYear(year, isFirstTime = false) {
  const closestYear = getClosestAvailableYear(year);

  if (isFirstTime) {
    lastCurrentYear = closestYear;
  } else {
    if (lastCurrentYear == closestYear) {
      return;
    }
  }

  lastCurrentYear = closestYear;
  const filename = `/geojson/world_${closestYear}.geojson`;

  return fetch(filename)
    .then((res) => {
      if (!res.ok) throw new Error("File not found: " + filename);
      return res.json();
    })
    .then((data) => {
      if (currentRegionsLayer) {
        map.removeLayer(currentRegionsLayer);
        currentRegionsLayer = null;
      }
      currentRegionsLayer = L.geoJSON(data, {
        style: {
          color: "#444",
          weight: 2,
          fill: false,
        },
        onEachFeature: (feature, layer) => {
          layer.bindPopup(feature.properties.name || "Unnamed");
        },
      }).addTo(map);
    })
    .catch((err) => {
      console.warn(err.message);
    });
}

function renderCities(features) {
  const safeFeatures = toArray(features);
  const currentZoom = map.getZoom();
  const radius = getRadiusForZoom(currentZoom);

  safeFeatures.forEach((feature) => {
    // Defensive check
    if (!feature.geometry || !Array.isArray(feature.geometry.coordinates)) {
      return;
    }

    const [lng, lat] = feature.geometry.coordinates;
    const coord = [lat, lng];

    // Utiliser circleMarker avec taille adaptative au zoom
    const circle = L.circleMarker(coord, {
      radius: radius, // Taille qui s'adapte au zoom
      fillColor: feature.color || "#000000",
      color: feature.color || "#333333",
      weight: 1,
      opacity: feature.opacity ?? 0.8,
      fillOpacity: feature.opacity ?? 0.8,
    });

    // Ajouter un popup discret au survol si le nom existe
    if (feature.name) {
      circle.bindTooltip(feature.name, {
        permanent: false,
        direction: "top",
        offset: [0, -5],
      });
    }

    featureLayerManager.addFeatureLayer(feature.id, circle);
  });
}

function renderZones(features) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!feature.geometry || !Array.isArray(feature.geometry.coordinates)) {
      return;
    }

    const layer = L.geoJSON(feature.geometry, {
      style: {
        fillColor: feature.color || "#ccc",
        fillOpacity: 0.5,
        color: "#333",
        weight: 1,
      },
    });

    if (feature.name) {
      layer.bindPopup(feature.name);
    }

    featureLayerManager.addFeatureLayer(feature.id, layer);
  });
}

function renderArrows(features) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!feature.geometry || !Array.isArray(feature.geometry.coordinates)) {
      return;
    }
    // Convert GeoJSON [lng, lat] → Leaflet [lat, lng]
    const latLngs = feature.geometry.coordinates.map(([lng, lat]) => [
      lat,
      lng,
    ]);

    const line = L.polyline(latLngs, {
      color: feature.color || "#000",
      weight: feature.stroke_width ?? 2,
      opacity: feature.opacity ?? 1,
    });

    // Apply arrowheads (before addTo)
    line.arrowheads({
      size: "10px",
      frequency: "endonly",
      fill: true,
    });

    if (feature.name) {
      line.bindPopup(feature.name);
    }

    featureLayerManager.addFeatureLayer(feature.id, line);
  });
}

function renderShapes(features) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (
      !feature.geometry ||
      !Array.isArray(feature.geometry.coordinates) ||
      !feature.geometry.coordinates[0]
    ) {
      return;
    }

    // Convertir les coordonnées GeoJSON en LatLng
    const latLngs = feature.geometry.coordinates[0].map((coord) => [
      coord[1],
      coord[0],
    ]);

    const square = L.polygon(latLngs, {
      color: feature.color || "#000000",
      weight: 2,
      fillColor: feature.color || "#cccccc",
      fillOpacity: feature.opacity ?? 0.5,
      interactive: true, // Rendre interactif par défaut
    });

    if (feature.name) {
      square.bindPopup(feature.name);
    }

    featureLayerManager.addFeatureLayer(feature.id, square);
  });
}

function renderAllFeatures() {
  const currentFeatures = filteredFeatures.value;
  const currentIds = new Set(currentFeatures.map((f) => f.id));
  const previousIds = previousFeatureIds.value;

  previousIds.forEach((oldId) => {
    if (!currentIds.has(oldId)) {
      const layer = featureLayerManager.layers.get(oldId);
      if (layer) {
        map.removeLayer(layer);
        featureLayerManager.layers.delete(oldId);
      }
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

  renderCities(featuresByType.point);
  renderZones(featuresByType.polygon);
  renderArrows(featuresByType.arrow);
  renderShapes(featuresByType.square);
  renderShapes(featuresByType.rectangle);
  renderShapes(featuresByType.circle);
  renderShapes(featuresByType.triangle);
  renderShapes(featuresByType.oval);

  previousFeatureIds.value = currentIds;

  emit("features-loaded", currentFeatures);
}

function removeGeoJSONLayers() {
  if (currentRegionsLayer) {
    map.removeLayer(currentRegionsLayer);
    currentRegionsLayer = null;
  }
}

// Loads all necessary layers for the given year
let isLoading = false;

async function loadAllLayersForYear(year) {
  if (isLoading) return;
  isLoading = true;

  try {
    await loadRegionsForYear(year); // <-- ici on attend le chargement complet
    renderAllFeatures();
  } catch (e) {
    console.warn("Error loading layers:", e);
  } finally {
    isLoading = false;
  }
}
// Creates a delay between map updates to prevent issues caused by rapid year changes
function debounce(fn, delay) {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), delay);
  };
}

function toArray(maybeArray) {
  if (Array.isArray(maybeArray)) return maybeArray;
  if (maybeArray == null) return []; // null or undefined
  return [maybeArray]; // wrap single object
}

// Uses debounce to load GeoJSON layers
const debouncedUpdate = debounce((year) => {
  loadAllLayersForYear(year);
}, 100);

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

  loadRegionsForYear(selectedYear.value, true);

  // Ajouter l'événement zoom pour adapter la taille des cercles
  map.on("zoomend", updateCircleSizes);

  // Initialiser l'édition si nécessaire
  if (props.editMode) {
    initializeEditControls();
  }
});

// NOUVELLES FONCTIONS POUR L'ÉDITION

// Mettre à jour le curseur de la carte selon le mode d'édition
function updateMapCursor() {
  if (!map) return;

  const mapContainer = map.getContainer();

  if (props.editMode && props.activeEditMode) {
    // En mode d'édition avec un mode actif, utiliser un curseur en croix
    mapContainer.style.cursor = "crosshair";
  } else if (props.editMode) {
    // En mode d'édition mais pas de mode actif (sélection/déplacement), curseur normal
    mapContainer.style.cursor = "";
  } else {
    // Pas en mode d'édition, curseur normal
    mapContainer.style.cursor = "";
  }
}

// Initialiser les contrôles d'édition
function initializeEditControls() {
  if (!props.editMode) return;

  console.log("Initializing edit controls:", {
    editMode: props.editMode,
    activeEditMode: props.activeEditMode,
    selectedShape: props.selectedShape,
  });

  // Layer pour les éléments dessinés
  drawnItems = new L.FeatureGroup();
  map.addLayer(drawnItems);

  // Changer le curseur selon le mode d'édition
  updateMapCursor();

  // Écouter les événements selon le mode actif
  console.log("🎛️ Initializing edit controls:", {
    editMode: props.editMode,
    activeEditMode: props.activeEditMode,
    selectedShape: props.selectedShape,
  });

  // Événements de sélection/déplacement toujours disponibles en mode édition
  if (props.editMode) {
    console.log("🎯 Setting up selection and move events");
    map.on("mousedown", handleMoveMouseDown);
    map.on("mousemove", handleMoveMouseMove);
    map.on("mouseup", handleMoveMouseUp);
    // Attacher handleKeyDown toujours en mode édition pour permettre la suppression
    map.on("keydown", handleKeyDown);
    // Rendre les formes existantes cliquables
    makeFeaturesClickable();
  }

  if (
    props.activeEditMode === "CREATE_LINE" ||
    props.activeEditMode === "CREATE_FREE_LINE"
  ) {
    console.log("📏 Setting up line drawing events");
    // Événements pour le tracé de ligne
    map.on("mousedown", handleMouseDown);
    map.on("mousemove", handleMouseMove);
    map.on("mouseup", handleMouseUp);
  } else if (props.activeEditMode === "CREATE_SHAPES") {
    console.log("🔷 Setting up shape drawing events");
    // Événements pour les formes
    map.on("mousedown", handleShapeMouseDown);
    map.on("mousemove", handleShapeMouseMove);
    map.on("mouseup", handleShapeMouseUp);
    map.on("dragstart", preventDragDuringShapeDrawing);
  } else if (props.activeEditMode === "CREATE_POLYGON") {
    console.log("⬡ Setting up polygon drawing events");
    // Événements pour les polygones
    map.on("contextmenu", handleRightClick); // Clic droit pour finir le polygone
  }

  // Écouter les clics sur la carte selon le mode
  map.on("click", handleMapClick);
  map.on("dblclick", handleMapDoubleClick);
}

// Gestion des événements de souris pour le tracé
function handleMouseDown(e) {
  console.log("General mouse down triggered:", {
    editMode: props.editMode,
    activeEditMode: props.activeEditMode,
    selectedShape: props.selectedShape,
  });
  if (!props.editMode) return;

  if (props.activeEditMode === "CREATE_LINE") {
    isDrawingLine = true;
    lineStartPoint = e.latlng;

    // Désactiver le dragging de la carte pendant le tracé
    map.dragging.disable();

    // Créer la ligne temporaire (invisible au départ)
    tempLine = L.polyline([lineStartPoint, lineStartPoint], {
      color: "#000000",
      weight: 2,
      opacity: 0.7,
    });
    drawnItems.addLayer(tempLine);
  } else if (props.activeEditMode === "CREATE_FREE_LINE") {
    isDrawingFree = true;
    freeLinePoints = [e.latlng];

    // Désactiver le dragging de la carte pendant le tracé
    map.dragging.disable();

    // Créer la ligne libre temporaire
    tempFreeLine = L.polyline([e.latlng], {
      color: "#000000",
      weight: 2,
      opacity: 0.7,
    });
    drawnItems.addLayer(tempFreeLine);
  }
}

function handleMouseMove(e) {
  if (isDrawingLine && lineStartPoint && tempLine) {
    // Mettre à jour les coordonnées de la ligne droite temporaire
    tempLine.setLatLngs([lineStartPoint, e.latlng]);
  } else if (isDrawingFree && tempFreeLine) {
    // Ajouter le point actuel à la ligne libre
    freeLinePoints.push(e.latlng);

    // Appliquer un lissage léger en temps réel (optionnel, peut être commenté si trop lent)
    const smoothedPoints = smoothFreeLinePoints(freeLinePoints);
    tempFreeLine.setLatLngs(smoothedPoints);
  }
}

function handleMouseUp(e) {
  // Gérer la fin du tracé de ligne droite
  if (isDrawingLine && lineStartPoint) {
    isDrawingLine = false;

    // Réactiver le dragging de la carte
    map.dragging.enable();

    // Calculer la distance entre le point de départ et d'arrivée
    const distance = map.distance(lineStartPoint, e.latlng);

    // Si la distance est trop petite, annuler
    if (distance < 10) {
      cleanupTempLine();
      lineStartPoint = null;
      return;
    }

    // Supprimer la ligne temporaire
    if (tempLine) {
      drawnItems.removeLayer(tempLine);
      tempLine = null;
    }

    // Créer la ligne finale
    createLine(lineStartPoint, e.latlng);

    lineStartPoint = null;
  }

  // Gérer la fin du tracé libre
  else if (isDrawingFree) {
    isDrawingFree = false;

    // Réactiver le dragging de la carte
    map.dragging.enable();

    // Finaliser la ligne libre
    finishFreeLine();

    // Nettoyer
    freeLinePoints = [];
  }
}

function cleanupTempLine() {
  if (tempLine) {
    drawnItems.removeLayer(tempLine);
    tempLine = null;
  }
  isDrawingLine = false;
  lineStartPoint = null;
}

function cleanupTempShape() {
  shapeState = null;
  shapeStartPoint = null;
  lastMousePos = null;
  isDrawingShape = false;
  if (tempShape) {
    drawnItems.removeLayer(tempShape);
    tempShape = null;
  }
}

// Empêcher le dragging de la carte pendant le dessin de formes
function preventDragDuringShapeDrawing(e) {
  if (isDrawingShape) {
    e.preventDefault();
    e.stopPropagation();
    return false;
  }
}

// Gérer les clics sur la carte en mode édition
function handleMapClick(e) {
  console.log("🗺️ MAP CLICK:", {
    editMode: props.editMode,
    activeEditMode: props.activeEditMode,
    selectedShape: props.selectedShape,
    latlng: e.latlng,
    target: e.target,
  });

  if (!props.editMode || !props.activeEditMode) return;

  switch (props.activeEditMode) {
    case "CREATE_POINT":
      createPointAt(e.latlng);
      break;
    case "CREATE_POLYGON":
      handlePolygonClick(e.latlng);
      break;
    case "CREATE_SHAPES":
      // Les formes sont gérées par les événements souris mousedown/mousemove/mouseup
      break;
  }
}

// Gérer les événements souris pour les formes (comme pour les lignes)
function handleShapeMouseDown(e) {
  console.log("🔽 SHAPE MOUSE DOWN:", {
    selectedShape: props.selectedShape,
    activeEditMode: props.activeEditMode,
    editMode: props.editMode,
    shapeState: shapeState,
    latlng: e.latlng,
    target: e.target,
  });

  // Vérifier si c'est un clic sur une forme existante
  if (e.target && e.target._isFeatureClick) {
    console.log("🔽 Click on existing feature, skipping shape creation");
    return;
  }

  if (props.activeEditMode !== "CREATE_SHAPES" || !props.selectedShape) {
    console.log("❌ Shape drawing not allowed - returning", {
      activeEditMode: props.activeEditMode,
      selectedShape: props.selectedShape,
      expectedMode: "CREATE_SHAPES",
    });
    return;
  }

  console.log("✅ Shape drawing allowed - starting", props.selectedShape);

  // Marquer qu'on commence à dessiner
  isDrawingShape = true;

  // Désactiver le dragging de la carte pendant le tracé
  map.dragging.disable();

  // Empêcher complètement le dragging
  e.originalEvent.preventDefault();
  e.originalEvent.stopPropagation();
  e.originalEvent.stopImmediatePropagation();

  const shapeType = props.selectedShape;

  // Logique selon le type de forme
  switch (shapeType) {
    case "square":
      // Approche : centre + taille (comme le cercle, mais carré parfait)
      shapeState = "drawing";
      shapeStartPoint = e.latlng;
      // On créera la forme temporaire au mouvement de souris
      console.log("Started drawing square center at:", e.latlng);
      break;

    case "rectangle":
      // Approche : deux coins opposés
      shapeState = "drawing";
      shapeStartPoint = e.latlng;
      tempShape = L.rectangle(
        [
          [shapeStartPoint.lat, shapeStartPoint.lng],
          [shapeStartPoint.lat, shapeStartPoint.lng],
        ],
        {
          color: "#000000",
          weight: 2,
          fillColor: "#cccccc",
          fillOpacity: 0.5,
        }
      );
      drawnItems.addLayer(tempShape);
      console.log("Started drawing rectangle at:", e.latlng);
      break;

    case "circle":
    case "triangle":
      // Approche : centre + taille
      shapeState = "drawing";
      shapeStartPoint = e.latlng;
      // On créera la forme temporaire au mouvement de souris
      console.log("Started drawing", shapeType, "center at:", e.latlng);
      break;

    case "oval":
      // Approche : centre + hauteur d'abord, puis largeur
      if (shapeState === null) {
        // Première étape : définir le centre
        shapeState = "adjusting_height";
        shapeStartPoint = e.latlng;
        console.log("Started drawing oval center at:", e.latlng);
      }
      break;

    default:
      console.log("❌ Unknown shape type:", shapeType);
      isDrawingShape = false;
      map.dragging.enable();
      return;
  }
}

function handleShapeMouseUp(e) {
  console.log("🔺 Shape mouse up triggered:", {
    shapeState,
    selectedShape: props.selectedShape,
    hasStartPoint: !!shapeStartPoint,
    distance: shapeStartPoint ? map.distance(shapeStartPoint, e.latlng) : null,
  });

  if (!shapeStartPoint || !props.selectedShape) {
    console.log("❌ No start point or shape selected");
    return;
  }

  const shapeType = props.selectedShape;

  switch (shapeType) {
    case "square":
      if (shapeState === "drawing") {
        isDrawingShape = false;
        map.dragging.enable();

        const distance = map.distance(shapeStartPoint, e.latlng);
        if (distance < 5) {
          cleanupTempShape();
          return;
        }

        console.log("✅ Creating final square");
        if (tempShape) {
          drawnItems.removeLayer(tempShape);
          tempShape = null;
        }
        createSquare(shapeStartPoint, e.latlng);

        shapeState = null;
        shapeStartPoint = null;
        lastMousePos = null;
      }
      break;

    case "rectangle":
      if (shapeState === "drawing") {
        isDrawingShape = false;
        map.dragging.enable();

        const distance = map.distance(shapeStartPoint, e.latlng);
        if (distance < 5) {
          cleanupTempShape();
          return;
        }

        console.log("✅ Creating final rectangle");
        if (tempShape) {
          drawnItems.removeLayer(tempShape);
          tempShape = null;
        }
        createRectangle(shapeStartPoint, e.latlng);

        shapeState = null;
        shapeStartPoint = null;
        lastMousePos = null;
      }
      break;

    case "circle":
      if (shapeState === "drawing") {
        // Pour le cercle, mouseup finalise la forme (pas comme les autres)
        isDrawingShape = false;
        map.dragging.enable();

        const distance = map.distance(shapeStartPoint, e.latlng);
        if (distance < 5) {
          cleanupTempShape();
          return;
        }

        console.log("✅ Creating final circle");
        if (tempShape) {
          drawnItems.removeLayer(tempShape);
          tempShape = null;
        }
        createCircle(shapeStartPoint, e.latlng);

        shapeState = null;
        shapeStartPoint = null;
        lastMousePos = null;
      }
      break;

    case "triangle":
      if (shapeState === "drawing") {
        isDrawingShape = false;
        map.dragging.enable();

        const distance = map.distance(shapeStartPoint, e.latlng);
        if (distance < 5) {
          cleanupTempShape();
          return;
        }

        console.log("✅ Creating final triangle");
        if (tempShape) {
          drawnItems.removeLayer(tempShape);
          tempShape = null;
        }
        createTriangle(shapeStartPoint, e.latlng);

        shapeState = null;
        shapeStartPoint = null;
        lastMousePos = null;
      }
      break;

    case "oval":
      if (shapeState === "adjusting_height") {
        // Première étape terminée : hauteur définie, passer à la largeur
        shapeState = "adjusting_width";
        shapeEndPoint = e.latlng;
        console.log("✅ Oval height set, now adjusting width");
      } else if (shapeState === "adjusting_width") {
        // Deuxième étape terminée : créer l'ovale final
        isDrawingShape = false;
        map.dragging.enable();

        console.log("✅ Creating final oval");
        if (tempShape) {
          drawnItems.removeLayer(tempShape);
          tempShape = null;
        }
        createOval(shapeStartPoint, shapeEndPoint, e.latlng);

        shapeState = null;
        shapeStartPoint = null;
        shapeEndPoint = null;
        lastMousePos = null;
      }
      break;
  }
}

// Créer un carré avec centre et taille (comme un cercle)
function createSquare(center, sizePoint) {
  // Utiliser les coordonnées pixels pour un carré parfaitement visuel
  const centerPixel = map.latLngToContainerPoint(center);
  const sizePixel = map.latLngToContainerPoint(sizePoint);

  // Calculer la distance en pixels
  const pixelDistance = centerPixel.distanceTo(sizePixel);
  const halfSidePixels = pixelDistance / Math.sqrt(2);

  // Calculer les coins du carré en pixels
  const topLeftPixel = L.point(
    centerPixel.x - halfSidePixels,
    centerPixel.y - halfSidePixels
  );
  const bottomRightPixel = L.point(
    centerPixel.x + halfSidePixels,
    centerPixel.y + halfSidePixels
  );

  // Convertir en coordonnées géographiques
  const topLeft = map.containerPointToLatLng(topLeftPixel);
  const bottomRight = map.containerPointToLatLng(bottomRightPixel);

  const square = L.rectangle(
    [
      [topLeft.lat, topLeft.lng],
      [bottomRight.lat, bottomRight.lng],
    ],
    {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    }
  );

  drawnItems.addLayer(square);

  // Créer la feature
  const feature = squareToFeatureFromCenter(center, sizePoint);

  // Générer un ID temporaire pour la feature locale
  const tempFeature = {
    ...feature,
    id: `temp_${Date.now()}_${Math.random()}`,
    _isTemporary: true,
  };

  // Ajouter à la liste des features localement (pour l'affichage)
  if (!props.features.some((f) => f.id === tempFeature.id)) {
    const updatedFeatures = [...props.features, tempFeature];
    emit("features-loaded", updatedFeatures);
  }

  // Rendre la forme cliquable immédiatement
  const layerKey = tempFeature.id;
  featureLayerManager.layers.set(layerKey, square);
  featureLayerManager.makeLayerClickable(layerKey, square);

  // Essayer de sauvegarder (mais ne pas bloquer si ça échoue)
  saveFeature(tempFeature).catch(() => {
    console.log("⚠️ Sauvegarde temporaire - l'API n'est pas disponible");
  });
}

// Créer un rectangle entre deux coins opposés
function createRectangle(startCorner, endCorner) {
  // Même logique que le carré
  const minLat = Math.min(startCorner.lat, endCorner.lat);
  const maxLat = Math.max(startCorner.lat, endCorner.lat);
  const minLng = Math.min(startCorner.lng, endCorner.lng);
  const maxLng = Math.max(startCorner.lng, endCorner.lng);

  const rectangle = L.rectangle(
    [
      [minLat, minLng],
      [maxLat, maxLng],
    ],
    {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    }
  );

  drawnItems.addLayer(rectangle);

  const feature = rectangleToFeatureFromCorners(startCorner, endCorner);

  // Générer un ID temporaire pour la feature locale
  const tempFeature = {
    ...feature,
    id: `temp_${Date.now()}_${Math.random()}`,
    _isTemporary: true,
  };

  // Ajouter à la liste des features localement (pour l'affichage)
  if (!props.features.some((f) => f.id === tempFeature.id)) {
    const updatedFeatures = [...props.features, tempFeature];
    emit("features-loaded", updatedFeatures);
  }

  // Rendre la forme cliquable immédiatement
  const layerKey = tempFeature.id;
  featureLayerManager.layers.set(layerKey, rectangle);
  featureLayerManager.makeLayerClickable(layerKey, rectangle);

  // Essayer de sauvegarder (mais ne pas bloquer si ça échoue)
  saveFeature(tempFeature).catch(() => {
    console.log("⚠️ Sauvegarde temporaire - l'API n'est pas disponible");
  });
}

// Créer un cercle avec centre et rayon
function createCircle(center, edgePoint) {
  const radius = map.distance(center, edgePoint);

  const circle = L.circle(center, {
    radius: radius,
    color: "#000000",
    weight: 2,
    fillColor: "#cccccc",
    fillOpacity: 0.5,
  });

  drawnItems.addLayer(circle);

  const feature = circleToFeatureFromCenter(center, edgePoint);

  // Générer un ID temporaire pour la feature locale
  const tempFeature = {
    ...feature,
    id: `temp_${Date.now()}_${Math.random()}`,
    _isTemporary: true,
  };

  // Ajouter à la liste des features localement (pour l'affichage)
  if (!props.features.some((f) => f.id === tempFeature.id)) {
    const updatedFeatures = [...props.features, tempFeature];
    emit("features-loaded", updatedFeatures);
  }

  // Rendre la forme cliquable immédiatement
  const layerKey = tempFeature.id;
  featureLayerManager.layers.set(layerKey, circle);
  featureLayerManager.makeLayerClickable(layerKey, circle);

  // Essayer de sauvegarder (mais ne pas bloquer si ça échoue)
  saveFeature(tempFeature).catch(() => {
    console.log("⚠️ Sauvegarde temporaire - l'API n'est pas disponible");
  });
}

// Créer un triangle avec centre et taille
function createTriangle(center, sizePoint) {
  const distance = map.distance(center, sizePoint);

  const points = [];
  for (let i = 0; i < 3; i++) {
    const angle = ((i * 120 + 90) * Math.PI) / 180; // Triangle pointant vers le haut
    const lat = center.lat + (distance / 111320) * Math.sin(angle);
    const lng =
      center.lng +
      ((distance / 111320) * Math.cos(angle)) /
        Math.cos((center.lat * Math.PI) / 180);
    points.push([lat, lng]);
  }

  const triangle = L.polygon(points, {
    color: "#000000",
    weight: 2,
    fillColor: "#cccccc",
    fillOpacity: 0.5,
  });

  drawnItems.addLayer(triangle);

  const feature = triangleToFeatureFromCenter(center, sizePoint);

  // Générer un ID temporaire pour la feature locale
  const tempFeature = {
    ...feature,
    id: `temp_${Date.now()}_${Math.random()}`,
    _isTemporary: true,
  };

  // Ajouter à la liste des features localement (pour l'affichage)
  if (!props.features.some((f) => f.id === tempFeature.id)) {
    const updatedFeatures = [...props.features, tempFeature];
    emit("features-loaded", updatedFeatures);
  }

  // Rendre la forme cliquable immédiatement
  const layerKey = tempFeature.id;
  featureLayerManager.layers.set(layerKey, triangle);
  featureLayerManager.makeLayerClickable(layerKey, triangle);

  // Essayer de sauvegarder (mais ne pas bloquer si ça échoue)
  saveFeature(tempFeature).catch(() => {
    console.log("⚠️ Sauvegarde temporaire - l'API n'est pas disponible");
  });
}

// Créer un ovale avec centre, hauteur et largeur
function createOval(center, heightPoint, widthPoint) {
  const heightRadius = Math.abs(center.lat - heightPoint.lat) * 111320;
  const widthRadius =
    Math.abs(center.lng - widthPoint.lng) *
    111320 *
    Math.cos((center.lat * Math.PI) / 180);

  const points = [];
  const steps = 32;
  for (let i = 0; i < steps; i++) {
    const angle = (i / steps) * 2 * Math.PI;
    const lat = center.lat + (heightRadius / 111320) * Math.sin(angle);
    const lng =
      center.lng +
      ((widthRadius / 111320) * Math.cos(angle)) /
        Math.cos((center.lat * Math.PI) / 180);
    points.push([lat, lng]);
  }

  const oval = L.polygon(points, {
    color: "#000000",
    weight: 2,
    fillColor: "#cccccc",
    fillOpacity: 0.5,
  });

  drawnItems.addLayer(oval);

  const feature = ovalToFeatureFromCenter(center, heightPoint, widthPoint);

  // Générer un ID temporaire pour la feature locale
  const tempFeature = {
    ...feature,
    id: `temp_${Date.now()}_${Math.random()}`,
    _isTemporary: true,
  };

  // Ajouter à la liste des features localement (pour l'affichage)
  if (!props.features.some((f) => f.id === tempFeature.id)) {
    const updatedFeatures = [...props.features, tempFeature];
    emit("features-loaded", updatedFeatures);
  }

  // Rendre la forme cliquable immédiatement
  const layerKey = tempFeature.id;
  featureLayerManager.layers.set(layerKey, oval);
  featureLayerManager.makeLayerClickable(layerKey, oval);

  // Essayer de sauvegarder (mais ne pas bloquer si ça échoue)
  saveFeature(tempFeature).catch(() => {
    console.log("⚠️ Sauvegarde temporaire - l'API n'est pas disponible");
  });
}

// Mettre à jour le carré temporaire avec centre et taille (comme un cercle)
function updateTempSquareFromCenter(center, sizePoint) {
  // Nettoyer la forme précédente
  if (tempShape) {
    drawnItems.removeLayer(tempShape);
  }

  // Utiliser les coordonnées pixels pour créer un carré parfaitement visuel
  const centerPixel = map.latLngToContainerPoint(center);
  const sizePixel = map.latLngToContainerPoint(sizePoint);

  // Calculer la distance en pixels
  const pixelDistance = centerPixel.distanceTo(sizePixel);

  // Créer un carré parfait en pixels : côté = distance / √2
  const halfSidePixels = pixelDistance / Math.sqrt(2);

  // Calculer les coins du carré en pixels
  const topLeftPixel = L.point(
    centerPixel.x - halfSidePixels,
    centerPixel.y - halfSidePixels
  );
  const bottomRightPixel = L.point(
    centerPixel.x + halfSidePixels,
    centerPixel.y + halfSidePixels
  );

  // Convertir les coordonnées pixels en coordonnées géographiques
  const topLeft = map.containerPointToLatLng(topLeftPixel);
  const bottomRight = map.containerPointToLatLng(bottomRightPixel);

  // Créer les coins du carré
  const bounds = [
    [topLeft.lat, topLeft.lng],
    [bottomRight.lat, bottomRight.lng],
  ];

  tempShape = L.rectangle(bounds, {
    color: "#000000",
    weight: 2,
    fillColor: "#cccccc",
    fillOpacity: 0.5,
  });

  drawnItems.addLayer(tempShape);
}

// Mettre à jour le rectangle temporaire avec deux coins opposés
function updateTempRectangleFromCorners(startCorner, endCorner) {
  // Nettoyer la forme précédente
  if (tempShape) {
    drawnItems.removeLayer(tempShape);
  }

  // Calculer les coordonnées des quatre coins du rectangle
  const minLat = Math.min(startCorner.lat, endCorner.lat);
  const maxLat = Math.max(startCorner.lat, endCorner.lat);
  const minLng = Math.min(startCorner.lng, endCorner.lng);
  const maxLng = Math.max(startCorner.lng, endCorner.lng);

  // Créer un rectangle avec ces limites
  const bounds = [
    [minLat, minLng],
    [maxLat, maxLng],
  ];

  tempShape = L.rectangle(bounds, {
    color: "#000000",
    weight: 2,
    fillColor: "#cccccc",
    fillOpacity: 0.5,
  });

  drawnItems.addLayer(tempShape);
}

// Mettre à jour le cercle temporaire avec centre et point sur le cercle
function updateTempCircleFromCenter(center, edgePoint) {
  // Nettoyer la forme précédente
  if (tempShape) {
    drawnItems.removeLayer(tempShape);
  }

  // Calculer le rayon en mètres
  const radius = map.distance(center, edgePoint);

  tempShape = L.circle(center, {
    radius: radius,
    color: "#000000",
    weight: 2,
    fillColor: "#cccccc",
    fillOpacity: 0.5,
  });

  drawnItems.addLayer(tempShape);
}

// Mettre à jour le triangle temporaire avec centre et taille
function updateTempTriangleFromCenter(center, sizePoint) {
  // Nettoyer la forme précédente
  if (tempShape) {
    drawnItems.removeLayer(tempShape);
  }

  // Calculer la distance depuis le centre
  const distance = map.distance(center, sizePoint);

  // Créer un triangle équilatéral pointant vers le haut
  // Calculer les trois points du triangle
  const points = [];
  for (let i = 0; i < 3; i++) {
    const angle = ((i * 120 + 90) * Math.PI) / 180; // Commencer par le point du haut (90°)
    const lat = center.lat + (distance / 111320) * Math.sin(angle); // Approximation en degrés
    const lng =
      center.lng +
      ((distance / 111320) * Math.cos(angle)) /
        Math.cos((center.lat * Math.PI) / 180);
    points.push([lat, lng]);
  }

  tempShape = L.polygon(points, {
    color: "#000000",
    weight: 2,
    fillColor: "#cccccc",
    fillOpacity: 0.5,
  });

  drawnItems.addLayer(tempShape);
}

// Mettre à jour l'ovale temporaire - hauteur
function updateTempOvalHeight(center, heightPoint) {
  // Nettoyer la forme précédente
  if (tempShape) {
    drawnItems.removeLayer(tempShape);
  }

  // Pour l'instant, créer un cercle temporaire pour visualiser la hauteur
  const radius = Math.abs(center.lat - heightPoint.lat) * 111320; // Distance en mètres

  tempShape = L.circle(center, {
    radius: radius,
    color: "#000000",
    weight: 2,
    fillColor: "#cccccc",
    fillOpacity: 0.5,
  });

  drawnItems.addLayer(tempShape);
}

// Mettre à jour l'ovale temporaire - largeur
function updateTempOvalWidth(center, heightPoint, widthPoint) {
  // Nettoyer la forme précédente
  if (tempShape) {
    drawnItems.removeLayer(tempShape);
  }

  // Calculer les rayons
  const heightRadius = Math.abs(center.lat - heightPoint.lat) * 111320;
  const widthRadius =
    Math.abs(center.lng - widthPoint.lng) *
    111320 *
    Math.cos((center.lat * Math.PI) / 180);

  // Créer une ellipse approximative avec un polygone
  const points = [];
  const steps = 32;
  for (let i = 0; i < steps; i++) {
    const angle = (i / steps) * 2 * Math.PI;
    const lat = center.lat + (heightRadius / 111320) * Math.sin(angle);
    const lng =
      center.lng +
      ((widthRadius / 111320) * Math.cos(angle)) /
        Math.cos((center.lat * Math.PI) / 180);
    points.push([lat, lng]);
  }

  tempShape = L.polygon(points, {
    color: "#000000",
    weight: 2,
    fillColor: "#cccccc",
    fillOpacity: 0.5,
  });

  drawnItems.addLayer(tempShape);
}

// Convertir un carré défini par centre et taille en feature GeoJSON
function squareToFeatureFromCenter(center, sizePoint) {
  const distance = map.distance(center, sizePoint);
  const halfSide = distance / Math.sqrt(2);

  // Convertir en degrés
  const latOffset = halfSide / 111320;
  const lngOffset =
    halfSide / (111320 * Math.cos((center.lat * Math.PI) / 180));

  // Créer les coordonnées du carré (sens horaire)
  const geometry = {
    type: "Polygon",
    coordinates: [
      [
        [center.lng - lngOffset, center.lat + latOffset], // Coin nord-ouest
        [center.lng + lngOffset, center.lat + latOffset], // Coin nord-est
        [center.lng + lngOffset, center.lat - latOffset], // Coin sud-est
        [center.lng - lngOffset, center.lat - latOffset], // Coin sud-ouest
        [center.lng - lngOffset, center.lat + latOffset], // Retour au point de départ
      ],
    ],
  };

  return {
    map_id: props.mapId,
    type: "square",
    geometry: geometry,
    color: "#cccccc",
    opacity: 0.5,
    z_index: 1,
  };
}

// Convertir un rectangle défini par deux coins opposés en feature GeoJSON
function rectangleToFeatureFromCorners(startCorner, endCorner) {
  const minLat = Math.min(startCorner.lat, endCorner.lat);
  const maxLat = Math.max(startCorner.lat, endCorner.lat);
  const minLng = Math.min(startCorner.lng, endCorner.lng);
  const maxLng = Math.max(startCorner.lng, endCorner.lng);

  const geometry = {
    type: "Polygon",
    coordinates: [
      [
        [minLng, maxLat], // Coin nord-ouest
        [maxLng, maxLat], // Coin nord-est
        [maxLng, minLat], // Coin sud-est
        [minLng, minLat], // Coin sud-ouest
        [minLng, maxLat], // Retour au point de départ
      ],
    ],
  };

  return {
    map_id: props.mapId,
    type: "rectangle",
    geometry: geometry,
    color: "#cccccc",
    opacity: 0.5,
    z_index: 1,
  };
}

// Convertir un cercle défini par centre et point sur le cercle en feature GeoJSON
function circleToFeatureFromCenter(center, edgePoint) {
  const radius = map.distance(center, edgePoint);

  // Créer un polygone approximant le cercle
  const points = [];
  const steps = 32;
  for (let i = 0; i < steps; i++) {
    const angle = (i / steps) * 2 * Math.PI;
    const lat = center.lat + (radius / 111320) * Math.sin(angle);
    const lng =
      center.lng +
      ((radius / 111320) * Math.cos(angle)) /
        Math.cos((center.lat * Math.PI) / 180);
    points.push([lng, lat]); // GeoJSON format [lng, lat]
  }
  points.push(points[0]); // Fermer le polygone

  const geometry = {
    type: "Polygon",
    coordinates: [points],
  };

  return {
    map_id: props.mapId,
    type: "circle",
    geometry: geometry,
    color: "#cccccc",
    opacity: 0.5,
    z_index: 1,
  };
}

// Convertir un triangle défini par centre et taille en feature GeoJSON
function triangleToFeatureFromCenter(center, sizePoint) {
  const distance = map.distance(center, sizePoint);

  const points = [];
  for (let i = 0; i < 3; i++) {
    const angle = ((i * 120 + 90) * Math.PI) / 180; // Triangle pointant vers le haut
    const lat = center.lat + (distance / 111320) * Math.sin(angle);
    const lng =
      center.lng +
      ((distance / 111320) * Math.cos(angle)) /
        Math.cos((center.lat * Math.PI) / 180);
    points.push([lng, lat]); // GeoJSON format [lng, lat]
  }
  points.push(points[0]); // Fermer le polygone

  const geometry = {
    type: "Polygon",
    coordinates: [points],
  };

  return {
    map_id: props.mapId,
    type: "triangle",
    geometry: geometry,
    color: "#cccccc",
    opacity: 0.5,
    z_index: 1,
  };
}

// Convertir un ovale défini par centre, hauteur et largeur en feature GeoJSON
function ovalToFeatureFromCenter(center, heightPoint, widthPoint) {
  const heightRadius = Math.abs(center.lat - heightPoint.lat) * 111320;
  const widthRadius =
    Math.abs(center.lng - widthPoint.lng) *
    111320 *
    Math.cos((center.lat * Math.PI) / 180);

  const points = [];
  const steps = 32;
  for (let i = 0; i < steps; i++) {
    const angle = (i / steps) * 2 * Math.PI;
    const lat = center.lat + (heightRadius / 111320) * Math.sin(angle);
    const lng =
      center.lng +
      ((widthRadius / 111320) * Math.cos(angle)) /
        Math.cos((center.lat * Math.PI) / 180);
    points.push([lng, lat]); // GeoJSON format [lng, lat]
  }
  points.push(points[0]); // Fermer le polygone

  const geometry = {
    type: "Polygon",
    coordinates: [points],
  };

  return {
    map_id: props.mapId,
    type: "oval",
    geometry: geometry,
    color: "#cccccc",
    opacity: 0.5,
    z_index: 1,
  };
}

// Gérer le mouvement de la souris pour ajuster la forme
function handleShapeMouseMove(e) {
  lastMousePos = e.latlng; // Stocker la dernière position

  if (!props.activeEditMode === "CREATE_SHAPES" || !props.selectedShape) return;

  const shapeType = props.selectedShape;

  switch (shapeType) {
    case "square":
      if (shapeState === "drawing" && shapeStartPoint) {
        console.log(
          "🔄 Updating square center",
          shapeStartPoint,
          "size to",
          e.latlng
        );
        updateTempSquareFromCenter(shapeStartPoint, e.latlng);
      }
      break;

    case "rectangle":
      if (shapeState === "drawing" && shapeStartPoint) {
        console.log(
          "🔄 Updating rectangle from",
          shapeStartPoint,
          "to",
          e.latlng
        );
        updateTempRectangleFromCorners(shapeStartPoint, e.latlng);
      }
      break;

    case "circle":
      if (shapeState === "drawing" && shapeStartPoint) {
        console.log(
          "🔄 Updating circle center",
          shapeStartPoint,
          "radius to",
          e.latlng
        );
        updateTempCircleFromCenter(shapeStartPoint, e.latlng);
      }
      break;

    case "triangle":
      if (shapeState === "drawing" && shapeStartPoint) {
        console.log(
          "🔄 Updating triangle center",
          shapeStartPoint,
          "size to",
          e.latlng
        );
        updateTempTriangleFromCenter(shapeStartPoint, e.latlng);
      }
      break;

    case "oval":
      if (shapeState === "adjusting_height" && shapeStartPoint) {
        console.log(
          "🔄 Adjusting oval height from",
          shapeStartPoint,
          "to",
          e.latlng
        );
        updateTempOvalHeight(shapeStartPoint, e.latlng);
      } else if (
        shapeState === "adjusting_width" &&
        shapeStartPoint &&
        shapeEndPoint
      ) {
        console.log(
          "🔄 Adjusting oval width from",
          shapeStartPoint,
          "to",
          e.latlng
        );
        updateTempOvalWidth(shapeStartPoint, shapeEndPoint, e.latlng);
      }
      break;
  }
}

// Finaliser le tracé libre
function finishFreeLine() {
  if (freeLinePoints.length < 2) return;

  // Appliquer le lissage final
  const smoothedPoints = smoothFreeLinePoints(freeLinePoints);

  // Supprimer la ligne temporaire
  if (tempFreeLine) {
    drawnItems.removeLayer(tempFreeLine);
    tempFreeLine = null;
  }

  // Créer la ligne finale lissée
  const freeLine = L.polyline(smoothedPoints, {
    color: "#000000",
    weight: 2,
    opacity: 1.0,
  });

  drawnItems.addLayer(freeLine);

  // Créer et sauvegarder automatiquement la feature
  const feature = {
    map_id: props.mapId,
    type: "polyline",
    geometry: {
      type: "LineString",
      coordinates: smoothedPoints.map((point) => [point.lng, point.lat]),
    },
    color: "#000000",
    stroke_width: 2,
    opacity: 1.0,
    z_index: 1,
  };

  // Générer un ID temporaire pour rendre la ligne cliquable immédiatement
  const tempId = `temp_freeline_${Date.now()}_${Math.random()}`;
  featureLayerManager.layers.set(tempId, freeLine);
  if (props.editMode) {
    featureLayerManager.makeLayerClickable(tempId, freeLine);
  }

  saveFeature(feature);
}

// Gérer les clics droits pour finir les polygones
function handleRightClick(e) {
  if (!props.editMode || props.activeEditMode !== "CREATE_POLYGON") return;

  // Empêcher le menu contextuel par défaut
  e.originalEvent.preventDefault();

  if (currentPolygonPoints.length >= 3) {
    finishPolygon();
  }
}

// Gérer les double-clics pour finir les polygones (gardé en fallback)
function handleMapDoubleClick(e) {
  if (!props.editMode || props.activeEditMode !== "CREATE_POLYGON") return;

  if (currentPolygonPoints.length >= 3) {
    finishPolygon();
  }
}

// Créer un point à une position donnée
function createPointAt(latlng) {
  const currentZoom = map.getZoom();
  const radius = getRadiusForZoom(currentZoom);

  // Utiliser un circleMarker avec taille adaptative au zoom
  const circle = L.circleMarker(latlng, {
    radius: radius, // Taille qui s'adapte au zoom
    fillColor: "#000000",
    color: "#333333",
    weight: 1,
    opacity: 0.8,
    fillOpacity: 0.8,
    draggable: true,
  });

  // Ajouter à la collection des cercles
  allCircles.add(circle);

  drawnItems.addLayer(circle);

  // Créer la feature
  const feature = {
    map_id: props.mapId,
    type: "point",
    geometry: {
      type: "Point",
      coordinates: [latlng.lng, latlng.lat],
    },
    color: "#000000",
    opacity: 0.8,
    z_index: 1,
  };

  // Générer un ID temporaire pour la feature locale
  const tempFeature = {
    ...feature,
    id: `temp_${Date.now()}_${Math.random()}`,
    _isTemporary: true,
  };

  // Ajouter à la liste des features localement (pour l'affichage)
  if (!props.features.some((f) => f.id === tempFeature.id)) {
    const updatedFeatures = [...props.features, tempFeature];
    emit("features-loaded", updatedFeatures);
  }

  // Rendre la forme cliquable immédiatement
  const layerKey = tempFeature.id;
  featureLayerManager.layers.set(layerKey, circle);
  featureLayerManager.makeLayerClickable(layerKey, circle);

  // Essayer de sauvegarder (mais ne pas bloquer si ça échoue)
  saveFeature(tempFeature).catch(() => {
    console.log("⚠️ Sauvegarde temporaire - l'API n'est pas disponible");
  });
}

// Créer une ligne entre deux points
function createLine(startLatLng, endLatLng) {
  const line = L.polyline([startLatLng, endLatLng], {
    color: "#000000",
    weight: 2,
    opacity: 1.0,
  });

  drawnItems.addLayer(line);

  // Créer la feature
  const feature = {
    map_id: props.mapId,
    type: "polyline",
    geometry: {
      type: "LineString",
      coordinates: [
        [startLatLng.lng, startLatLng.lat],
        [endLatLng.lng, endLatLng.lat],
      ],
    },
    color: "#000000",
    stroke_width: 2,
    opacity: 1.0,
    z_index: 1,
  };

  // Générer un ID temporaire pour la feature locale
  const tempFeature = {
    ...feature,
    id: `temp_${Date.now()}_${Math.random()}`,
    _isTemporary: true,
  };

  // Ajouter à la liste des features localement (pour l'affichage)
  if (!props.features.some((f) => f.id === tempFeature.id)) {
    const updatedFeatures = [...props.features, tempFeature];
    emit("features-loaded", updatedFeatures);
  }

  // Rendre la forme cliquable immédiatement
  const layerKey = tempFeature.id;
  featureLayerManager.layers.set(layerKey, line);
  featureLayerManager.makeLayerClickable(layerKey, line);

  // Essayer de sauvegarder (mais ne pas bloquer si ça échoue)
  saveFeature(tempFeature).catch(() => {
    console.log("⚠️ Sauvegarde temporaire - l'API n'est pas disponible");
  });
}

// Gérer les clics pour créer un polygone
function handlePolygonClick(latlng) {
  currentPolygonPoints.push(latlng);

  // Mettre à jour les lignes du polygone (sans marqueurs de points)
  updatePolygonLines();
}

// Mettre à jour toutes les lignes du polygone en cours de création
function updatePolygonLines() {
  // Supprimer les lignes temporaires existantes
  if (tempPolygon) {
    drawnItems.removeLayer(tempPolygon);
  }

  if (currentPolygonPoints.length < 2) return;

  // Créer les lignes entre les points consécutifs
  const lines = [];

  // Lignes entre points consécutifs
  for (let i = 0; i < currentPolygonPoints.length - 1; i++) {
    lines.push(currentPolygonPoints[i], currentPolygonPoints[i + 1]);
  }

  // Ligne de fermeture temporaire (dernier point vers premier)
  if (currentPolygonPoints.length >= 3) {
    lines.push(
      currentPolygonPoints[currentPolygonPoints.length - 1],
      currentPolygonPoints[0]
    );
  }

  // Créer une polyligne avec tous les segments
  if (lines.length > 0) {
    tempPolygon = L.polyline(lines, {
      color: "#000000",
      weight: 2,
      opacity: 1.0,
    });
    drawnItems.addLayer(tempPolygon);
  }
}

// Finir le polygone
function finishPolygon() {
  if (currentPolygonPoints.length < 3) return;

  // Fermer le polygone
  const points = [...currentPolygonPoints, currentPolygonPoints[0]];

  // Nettoyer UNIQUEMENT les lignes temporaires (garder les polygones précédents)
  if (tempPolygon) {
    drawnItems.removeLayer(tempPolygon);
    tempPolygon = null;
  }

  // Créer le polygone final
  const polygon = L.polygon(points, {
    color: "#000000",
    weight: 2,
    fillColor: "#cccccc",
    fillOpacity: 0.5,
  });

  drawnItems.addLayer(polygon);

  // Créer la feature
  const feature = {
    map_id: props.mapId,
    type: "polygon",
    geometry: {
      type: "Polygon",
      coordinates: [points.map((p) => [p.lng, p.lat])],
    },
    color: "#cccccc",
    opacity: 0.5,
    z_index: 1,
  };

  // Générer un ID temporaire pour la feature locale
  const tempFeature = {
    ...feature,
    id: `temp_${Date.now()}_${Math.random()}`,
    _isTemporary: true,
  };

  // Ajouter à la liste des features localement (pour l'affichage)
  if (!props.features.some((f) => f.id === tempFeature.id)) {
    const updatedFeatures = [...props.features, tempFeature];
    emit("features-loaded", updatedFeatures);
  }

  // Rendre la forme cliquable immédiatement
  const layerKey = tempFeature.id;
  featureLayerManager.layers.set(layerKey, polygon);
  featureLayerManager.makeLayerClickable(layerKey, polygon);

  // Essayer de sauvegarder (mais ne pas bloquer si ça échoue)
  saveFeature(tempFeature).catch(() => {
    console.log("⚠️ Sauvegarde temporaire - l'API n'est pas disponible");
  });

  // RÉINITIALISER pour permettre un nouveau polygone
  currentPolygonPoints = [];
}

// Fonction pour sauvegarder automatiquement une feature
async function saveFeature(featureData) {
  try {
    const response = await fetch("http://localhost:8000/maps/features", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(featureData),
    });

    if (!response.ok) {
      throw new Error("Failed to save feature");
    }

    const savedFeature = await response.json();
    console.log("Feature saved:", savedFeature);

    // Ajouter immédiatement la feature sauvegardée aux features actuelles
    // pour qu'elle soit visible même en mode édition
    const updatedFeatures = [...props.features, savedFeature];

    // Mettre à jour l'affichage selon le type de feature
    switch (savedFeature.type) {
      case "point":
        renderCities([savedFeature]);
        break;
      case "polyline":
        renderArrows([savedFeature]);
        break;
      case "polygon":
        renderZones([savedFeature]);
        break;
      case "square":
      case "rectangle":
      case "circle":
      case "triangle":
      case "oval":
        renderShapes([savedFeature]);
        break;
    }

    // Notifier le parent pour mettre à jour la liste complète
    emit("features-loaded", updatedFeatures);

    // Rendre la nouvelle forme cliquable immédiatement si on est en mode édition
    if (props.editMode) {
      const newLayer = featureLayerManager.layers.get(savedFeature.id);
      console.log(
        "🔍 Looking for layer with ID:",
        savedFeature.id,
        "Found:",
        !!newLayer
      );
      if (newLayer) {
        console.log(
          "🎯 Making layer clickable:",
          savedFeature.id,
          newLayer.constructor.name
        );
        featureLayerManager.makeLayerClickable(savedFeature.id, newLayer);
        console.log("✅ Made newly saved feature clickable:", savedFeature.id);
      } else {
        console.log(
          "❌ Layer not found for ID:",
          savedFeature.id,
          "Available layers:",
          Array.from(featureLayerManager.layers.keys())
        );
      }
    }
  } catch (error) {
    console.error("Erreur lors de la sauvegarde automatique:", error);
  }
}

// Nettoyer le mode édition
// Fonctions pour la sélection et le déplacement de formes

// Rendre les formes existantes cliquables pour la sélection
function makeFeaturesClickable() {
  console.log(
    "🎯 Making features clickable for selection - Total layers:",
    featureLayerManager.layers.size
  );

  // Pour chaque layer existant dans featureLayerManager, le rendre cliquable
  featureLayerManager.layers.forEach((layer, featureId) => {
    featureLayerManager.makeLayerClickable(featureId, layer);
    console.log(
      "✅ Made feature layer clickable:",
      featureId,
      layer.constructor.name
    );
  });

  // Aussi rendre cliquables les layers temporaires dans drawnItems
  if (drawnItems) {
    drawnItems.eachLayer((layer) => {
      // Pour les layers temporaires, on utilise un ID temporaire
      const tempId = "temp_" + Math.random();
      featureLayerManager.makeLayerClickable(tempId, layer);
      console.log(
        "✅ Made drawn layer clickable:",
        tempId,
        layer.constructor.name
      );
    });
  }
}

// Gérer le clic sur une forme pour la sélection/désélection ou suppression
function handleFeatureClick(featureId, isCtrlPressed) {
  console.log(
    "🎯 FEATURE CLICK HANDLER CALLED:",
    featureId,
    "CTRL:",
    isCtrlPressed,
    "Delete mode:",
    isDeleteMode.value,
    "Current selection:",
    Array.from(selectedFeatures),
    "Just finished drag:",
    justFinishedDrag
  );

  // Si on est en mode suppression, supprimer l'élément cliqué
  console.log("🗑️ Checking delete mode - isDeleteMode:", isDeleteMode.value);
  if (isDeleteMode.value) {
    console.log("🗑️ Delete mode active, deleting feature:", featureId);
    deleteFeature(featureId);
    return;
  }

  // Si on vient de terminer un drag, ignorer ce clic pour éviter la désélection accidentelle
  if (justFinishedDrag) {
    console.log(
      "🚫 Ignoring click after drag to prevent accidental deselection"
    );
    justFinishedDrag = false; // Remettre le flag à false
    return;
  }

  if (isCtrlPressed) {
    // Sélection multiple : toggle la sélection
    if (selectedFeatures.has(featureId)) {
      selectedFeatures.delete(featureId);
      console.log("❌ Deselected feature:", featureId);
    } else {
      selectedFeatures.add(featureId);
      console.log("✅ Selected feature:", featureId);
    }
  } else {
    // Clic simple : logique selon le nombre d'éléments sélectionnés
    if (selectedFeatures.size === 1 && selectedFeatures.has(featureId)) {
      // Un seul élément sélectionné et c'est celui-ci : le désélectionner
      selectedFeatures.clear();
      console.log("❌ Deselected single feature:", featureId);
    } else {
      // Plusieurs éléments sélectionnés OU clic sur un élément non sélectionné :
      // Désélectionner tout et sélectionner seulement cet élément
      selectedFeatures.clear();
      selectedFeatures.add(featureId);
      console.log("🔄 Single selection (cleared others):", featureId);
    }
  }

  console.log("📊 New selection:", Array.from(selectedFeatures));
  updateFeatureSelectionVisual();
}

// Mettre à jour l'apparence visuelle des formes sélectionnées
function updateFeatureSelectionVisual() {
  featureLayerManager.layers.forEach((layer, featureId) => {
    if (selectedFeatures.has(featureId)) {
      // Style pour les formes sélectionnées
      if (layer instanceof L.CircleMarker) {
        layer.setStyle({
          color: "#ff6b6b",
          weight: 3,
          fillColor: "#ff6b6b",
          fillOpacity: 0.8,
        });
      } else if (layer instanceof L.Polygon || layer instanceof L.Rectangle) {
        layer.setStyle({
          color: "#ff6b6b",
          weight: 3,
          fillColor: layer.options.fillColor,
          fillOpacity: layer.options.fillOpacity,
        });
      } else if (layer instanceof L.Polyline) {
        layer.setStyle({
          color: "#ff6b6b",
          weight: 4,
        });
      }
    } else {
      // Remettre le style original
      const originalFeature = props.features.find((f) => f.id === featureId);

      // Valeurs par défaut basées sur la création des formes
      const defaultBorderColor = "#000000"; // Noir par défaut
      const defaultFillColor = "#cccccc"; // Gris clair par défaut
      const defaultOpacity = 0.5;
      const defaultStrokeWidth = 2;

      if (layer instanceof L.CircleMarker) {
        layer.setStyle({
          color: originalFeature?.color || defaultBorderColor,
          weight: 1,
          fillColor: originalFeature?.color || defaultBorderColor,
          fillOpacity: originalFeature?.opacity ?? 0.8,
        });
      } else if (layer instanceof L.Polygon || layer instanceof L.Rectangle) {
        layer.setStyle({
          color: originalFeature?.color || defaultBorderColor,
          weight: 2, // Même épaisseur que lors de la création
          fillColor: originalFeature?.color || defaultFillColor,
          fillOpacity: originalFeature?.opacity ?? defaultOpacity,
        });
      } else if (layer instanceof L.Polyline) {
        layer.setStyle({
          color: originalFeature?.color || defaultBorderColor,
          weight: originalFeature?.stroke_width ?? defaultStrokeWidth,
          opacity: originalFeature?.opacity ?? 1,
        });
      }
    }

    // Changer le curseur selon le mode
    if (isDeleteMode.value) {
      layer.getElement()?.style.setProperty("cursor", "crosshair");
    } else {
      layer.getElement()?.style.setProperty("cursor", "");
    }
  });
}

// Gestionnaire pour le mode déplacement - mousedown
function handleMoveMouseDown(e) {
  console.log(
    "🎯 MOVE MOUSE DOWN:",
    e.latlng,
    "Selected features:",
    selectedFeatures.size,
    "Target:",
    e.target,
    "Target type:",
    e.target ? e.target.constructor.name : "null"
  );

  // Remettre le flag de drag terminé à false au début d'une nouvelle action
  justFinishedDrag = false;

  // Vérifier si c'est un clic sur une forme existante (via les événements des layers)
  // Les événements mousedown/click des layers individuels gèrent déjà la sélection
  // Ici on ne gère que les clics dans le vide pour le drag ou la désélection

  // Si on clique dans le vide et qu'on a des formes sélectionnées, préparer le drag
  if (selectedFeatures.size > 0) {
    // Préparer le drag mais ne pas le commencer encore
    // Le drag commencera au mousemove si on bouge assez
    dragStartPoint = e.latlng;
    console.log(
      "🎯 Prepared drag of",
      selectedFeatures.size,
      "features at",
      e.latlng
    );
  } else {
    // Si on clique dans le vide sans sélection, désélectionner tout
    console.log("🗺️ Click on empty space, clearing selection");
    selectedFeatures.clear();
    updateFeatureSelectionVisual();
  }
}

// Fonction pour détecter quelle forme se trouve à une position donnée
function getFeatureAtPosition(latlng) {
  // Vérifier tous les layers pour voir lequel contient le point
  for (const [featureId, layer] of featureLayerManager.layers.entries()) {
    try {
      if (layer instanceof L.CircleMarker) {
        // Pour les cercles, vérifier la distance
        const center = layer.getLatLng();
        const radius = layer.getRadius();
        const distance = map.distance(center, latlng);
        if (distance <= radius) {
          return featureId;
        }
      } else if (layer instanceof L.Polygon || layer instanceof L.Rectangle) {
        // Pour les polygones, vérifier si le point est à l'intérieur ou près des bords
        if (layer.getBounds().contains(latlng)) {
          // Vérification plus précise : le point doit être dans le polygone
          // Pour Leaflet, on peut utiliser une approche simple : vérifier la distance avec les bords
          const bounds = layer.getBounds();
          const northEast = bounds.getNorthEast();
          const southWest = bounds.getSouthWest();

          // Distance maximale depuis les bords pour considérer que c'est un clic sur la forme
          const toleranceLat = (northEast.lat - southWest.lat) * 0.1; // 10% de tolérance
          const toleranceLng = (northEast.lng - southWest.lng) * 0.1;

          // Vérifier si le point est près des bords ou à l'intérieur
          const nearBorder =
            latlng.lat >= southWest.lat - toleranceLat &&
            latlng.lat <= northEast.lat + toleranceLat &&
            latlng.lng >= southWest.lng - toleranceLng &&
            latlng.lng <= northEast.lng + toleranceLng;

          if (nearBorder) {
            return featureId;
          }
        }
      } else if (layer instanceof L.Polyline) {
        // Pour les lignes, vérifier la proximité
        const latlngs = layer.getLatLngs();
        for (let i = 0; i < latlngs.length - 1; i++) {
          const distance = map.distance(latlngs[i], latlng);
          if (distance < 10) {
            // 10 mètres de tolérance
            return featureId;
          }
        }
      }
    } catch (error) {
      console.warn("Error checking feature at position:", error);
    }
  }
  return null;
}

// Gestionnaire pour le mode déplacement - mousemove
function handleMoveMouseMove(e) {
  // Si on n'est pas encore en train de draguer mais qu'on a un point de départ
  if (!isDraggingFeatures && dragStartPoint && selectedFeatures.size > 0) {
    // Vérifier si on a bougé assez pour commencer le drag
    const distance = map.distance(dragStartPoint, e.latlng);
    if (distance > 5) {
      // Seuil de 5 mètres
      console.log("🚀 Starting drag after moving", distance, "meters");

      // Commencer le drag
      isDraggingFeatures = true;

      // Désactiver complètement TOUTES les interactions de la carte
      map.dragging.disable();
      map.doubleClickZoom.disable();
      map.scrollWheelZoom.disable();
      map.keyboard.disable();
      map.touchZoom.disable();
      map.boxZoom.disable();

      // Sauvegarder les positions originales
      originalPositions.clear();
      selectedFeatures.forEach((featureId) => {
        const layer = featureLayerManager.layers.get(featureId);
        if (layer) {
          // Pour les polygones, on sauvegarde les coordonnées
          if (layer instanceof L.Polygon || layer instanceof L.Rectangle) {
            originalPositions.set(featureId, layer.getBounds());
          } else if (layer instanceof L.CircleMarker) {
            originalPositions.set(featureId, layer.getLatLng());
          } else if (layer instanceof L.Polyline) {
            originalPositions.set(featureId, layer.getLatLngs());
          }
        }
      });
    }
  }

  // Si on est en train de draguer
  if (isDraggingFeatures && dragStartPoint) {
    // Calculer le delta de déplacement
    const deltaLat = e.latlng.lat - dragStartPoint.lat;
    const deltaLng = e.latlng.lng - dragStartPoint.lng;

    // Appliquer le déplacement à toutes les formes sélectionnées
    selectedFeatures.forEach((featureId) => {
      const layer = featureLayerManager.layers.get(featureId);
      if (layer && originalPositions.has(featureId)) {
        if (layer instanceof L.Polygon || layer instanceof L.Rectangle) {
          const originalBounds = originalPositions.get(featureId);
          const newBounds = L.latLngBounds([
            [
              originalBounds.getSouthWest().lat + deltaLat,
              originalBounds.getSouthWest().lng + deltaLng,
            ],
            [
              originalBounds.getNorthEast().lat + deltaLat,
              originalBounds.getNorthEast().lng + deltaLng,
            ],
          ]);
          layer.setBounds(newBounds);
        } else if (layer instanceof L.CircleMarker) {
          const originalPos = originalPositions.get(featureId);
          const newPos = L.latLng(
            originalPos.lat + deltaLat,
            originalPos.lng + deltaLng
          );
          layer.setLatLng(newPos);
        } else if (layer instanceof L.Polyline) {
          const originalLatLngs = originalPositions.get(featureId);
          const newLatLngs = originalLatLngs.map((latLng) =>
            L.latLng(latLng.lat + deltaLat, latLng.lng + deltaLng)
          );
          layer.setLatLngs(newLatLngs);
        }
      }
    });
  }
}

// Gestionnaire pour le mode déplacement - mouseup
function handleMoveMouseUp(e) {
  if (isDraggingFeatures && dragStartPoint) {
    console.log("🏁 Drag finished, saving changes");

    // Réactiver TOUTES les interactions de la carte
    map.dragging.enable();
    map.doubleClickZoom.enable();
    map.scrollWheelZoom.enable();
    map.keyboard.enable();
    map.touchZoom.enable();
    map.boxZoom.enable();

    // Calculer le delta final
    const deltaLat = e.latlng.lat - dragStartPoint.lat;
    const deltaLng = e.latlng.lng - dragStartPoint.lng;

    // Sauvegarder les nouvelles positions dans la base de données
    selectedFeatures.forEach((featureId) => {
      const feature = props.features.find((f) => f.id === featureId);
      if (feature) {
        updateFeaturePosition(feature, deltaLat, deltaLng);
      }
    });

    // Réinitialiser l'état
    isDraggingFeatures = false;
    dragStartPoint = null;
    originalPositions.clear();

    // Marquer qu'on vient de terminer un drag pour éviter la désélection
    justFinishedDrag = true;

    // Remettre le flag à false après un court délai
    setTimeout(() => {
      justFinishedDrag = false;
    }, 100);
  } else if (dragStartPoint) {
    // On avait préparé un drag mais on n'a pas bougé assez, juste nettoyer
    console.log("🖱️ Click without drag, cleaning up");
    dragStartPoint = null;
  }
}

// Basculer le mode suppression
function toggleDeleteMode() {
  console.log(
    "🔄 toggleDeleteMode called, current mode:",
    props.activeEditMode
  );

  // Émettre un événement pour changer le mode
  if (props.activeEditMode === "DELETE_FEATURE") {
    emit("mode-change", null); // Revenir au mode par défaut
  } else {
    emit("mode-change", "DELETE_FEATURE"); // Activer le mode suppression
  }
}

// Gestionnaire pour les événements clavier
function handleKeyDown(e) {
  console.log(
    "⌨️ Key pressed:",
    e.originalEvent.key,
    "Selected features:",
    selectedFeatures.size
  );
  if (e.originalEvent.key === "Delete" && selectedFeatures.size > 0) {
    console.log("🗑️ Delete key pressed, deleting selected features");
    deleteSelectedFeatures();
  } else if (e.originalEvent.key === "Escape") {
    console.log("⎋ Escape pressed, clearing selection");
    selectedFeatures.clear();
    updateFeatureSelectionVisual();
  }
}

// Mettre à jour la position d'une feature dans la base de données
async function updateFeaturePosition(feature, deltaLat, deltaLng) {
  console.log(
    "💾 Saving moved feature:",
    feature.id,
    "Delta:",
    deltaLat,
    deltaLng
  );

  try {
    // Créer une copie des nouvelles coordonnées GeoJSON
    const updatedGeometry = updateGeometryCoordinates(
      feature.geometry,
      deltaLat,
      deltaLng
    );

    // Préparer les données pour la requête PUT
    const updateData = {
      geometry: updatedGeometry,
    };

    // Envoyer la requête PUT
    const response = await fetch(
      `http://localhost:8000/maps/features/${feature.id}`,
      {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(updateData),
      }
    );

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const updatedFeature = await response.json();
    console.log("✅ Feature position updated successfully:", updatedFeature.id);

    // Mettre à jour la feature dans la liste locale
    const featureIndex = props.features.findIndex((f) => f.id === feature.id);
    if (featureIndex !== -1) {
      const updatedFeatures = [...props.features];
      updatedFeatures[featureIndex] = updatedFeature;
      emit("features-loaded", updatedFeatures);
    }
  } catch (error) {
    console.error("❌ Error updating feature position:", error);
    // En cas d'erreur, on pourrait vouloir recharger les features depuis le serveur
    // ou afficher un message d'erreur à l'utilisateur
  }
}

// Supprimer les features sélectionnées
async function deleteSelectedFeatures() {
  if (selectedFeatures.size === 0) return;

  console.log("🗑️ Deleting features:", Array.from(selectedFeatures));

  const featuresToDelete = Array.from(selectedFeatures);

  // Supprimer de la carte d'abord
  for (const featureId of featuresToDelete) {
    const layer = featureLayerManager.layers.get(featureId);
    if (layer) {
      // Retirer les cercles de la collection
      if (layer instanceof L.CircleMarker) {
        allCircles.delete(layer);
      }
      map.removeLayer(layer);
      featureLayerManager.layers.delete(featureId);
    }
  }

  // Supprimer de la base de données
  for (const featureId of featuresToDelete) {
    try {
      const response = await fetch(
        `http://localhost:8000/maps/features/${featureId}`,
        {
          method: "DELETE",
        }
      );

      if (!response.ok) {
        console.error(
          `❌ Failed to delete feature ${featureId}:`,
          response.status
        );
      } else {
        console.log(`✅ Successfully deleted feature ${featureId}`);
      }
    } catch (error) {
      console.error(`❌ Error deleting feature ${featureId}:`, error);
    }
  }

  // Mettre à jour la liste des features dans le parent
  const remainingFeatures = props.features.filter(
    (f) => !featuresToDelete.includes(f.id)
  );
  emit("features-loaded", remainingFeatures);

  // Vider la sélection
  selectedFeatures.clear();
  updateFeatureSelectionVisual();
}

// Supprimer une feature spécifique
async function deleteFeature(featureId) {
  console.log("🗑️ Deleting single feature:", featureId);

  // Supprimer de la carte
  const layer = featureLayerManager.layers.get(featureId);
  if (layer) {
    // Retirer les cercles de la collection
    if (layer instanceof L.CircleMarker) {
      allCircles.delete(layer);
    }
    map.removeLayer(layer);
    featureLayerManager.layers.delete(featureId);
  }

  // Supprimer de la base de données
  try {
    const response = await fetch(
      `http://localhost:8000/maps/features/${featureId}`,
      {
        method: "DELETE",
      }
    );

    if (!response.ok) {
      console.error(
        `❌ Failed to delete feature ${featureId}:`,
        response.status
      );
    } else {
      console.log(`✅ Successfully deleted feature ${featureId}`);
    }
  } catch (error) {
    console.error(`❌ Error deleting feature ${featureId}:`, error);
  }

  // Mettre à jour la liste des features dans le parent
  const remainingFeatures = props.features.filter((f) => f.id !== featureId);
  emit("features-loaded", remainingFeatures);
}

// Fonction pour mettre à jour les coordonnées d'une géométrie GeoJSON
function updateGeometryCoordinates(geometry, deltaLat, deltaLng) {
  if (!geometry || !geometry.coordinates) {
    return geometry;
  }

  const updatedGeometry = { ...geometry };

  switch (geometry.type) {
    case "Point":
      // Point: [lng, lat]
      updatedGeometry.coordinates = [
        geometry.coordinates[0] + deltaLng,
        geometry.coordinates[1] + deltaLat,
      ];
      break;

    case "LineString":
      // LineString: [[lng, lat], [lng, lat], ...]
      updatedGeometry.coordinates = geometry.coordinates.map((coord) => [
        coord[0] + deltaLng,
        coord[1] + deltaLat,
      ]);
      break;

    case "Polygon":
      // Polygon: [[[lng, lat], [lng, lat], ...]]
      updatedGeometry.coordinates = geometry.coordinates.map((ring) =>
        ring.map((coord) => [coord[0] + deltaLng, coord[1] + deltaLat])
      );
      break;

    default:
      console.warn(`Unsupported geometry type: ${geometry.type}`);
      return geometry;
  }

  return updatedGeometry;
}

function cleanupEditMode() {
  if (drawnItems) {
    // Nettoyer les cercles de drawnItems de la collection
    drawnItems.eachLayer((layer) => {
      if (layer instanceof L.CircleMarker) {
        allCircles.delete(layer);
      }
    });
    map.removeLayer(drawnItems);
    drawnItems = null;
  }

  // Nettoyer tous les événements
  map.off("mousedown", handleMouseDown);
  map.off("mousemove", handleMouseMove);
  map.off("mouseup", handleMouseUp);
  map.off("contextmenu", handleRightClick);
  map.off("click", handleMapClick);
  map.off("dblclick", handleMapDoubleClick);
  map.off("zoomend", updateCircleSizes);

  // Nettoyer les événements des formes
  map.off("mousedown", handleShapeMouseDown);
  map.off("mousemove", handleShapeMouseMove);
  map.off("mouseup", handleShapeMouseUp);
  map.off("dragstart", preventDragDuringShapeDrawing);

  // Nettoyer les événements de déplacement (seulement si on sort du mode édition)
  if (!props.editMode) {
    map.off("mousedown", handleMoveMouseDown);
    map.off("mousemove", handleMoveMouseMove);
    map.off("mouseup", handleMoveMouseUp);
    map.off("keydown", handleKeyDown);
  }

  // Nettoyer les variables d'état
  currentLinePoints = [];
  currentPolygonPoints = []; // Nettoyer les points du polygone quand on quitte l'édition
  cleanupTempLine();
  if (tempPolygon) {
    drawnItems.removeLayer(tempPolygon);
    tempPolygon = null;
  }
  freeLinePoints = [];
  if (tempFreeLine) {
    drawnItems.removeLayer(tempFreeLine);
    tempFreeLine = null;
  }

  // Nettoyer les états des formes
  shapeState = null;
  shapeStartPoint = null;
  lastMousePos = null;
  if (tempShape) {
    drawnItems.removeLayer(tempShape);
    tempShape = null;
  }

  // Nettoyer la sélection et le déplacement
  selectedFeatures.clear();
  isDraggingFeatures = false;
  dragStartPoint = null;
  originalPositions.clear();
  justFinishedDrag = false;
  updateFeatureSelectionVisual();

  // Mettre à jour le curseur
  updateMapCursor();

  // Recharger toutes les features quand on quitte le mode édition
  setTimeout(() => {
    fetchFeaturesAndRender(selectedYear.value);
  }, 100);
}

// Watcher pour le mode édition
watch(
  () => props.editMode,
  (newEditMode) => {
    // Si on quitte le mode édition et qu'il y a un polygone en cours, le terminer
    if (
      !newEditMode &&
      props.activeEditMode === "CREATE_POLYGON" &&
      currentPolygonPoints.length >= 3
    ) {
      console.log("🔺 Auto-finishing polygon when leaving edit mode");
      finishPolygon();
    }

    if (newEditMode) {
      initializeEditControls();
      // Recharger les features quand on entre en mode édition
      fetchFeaturesAndRender(selectedYear.value);
    } else {
      cleanupEditMode();
    }

    // Mettre à jour le curseur
    updateMapCursor();
  }
);

// Watcher pour mettre à jour isDeleteMode
watch(
  () => props.activeEditMode,
  (newMode) => {
    isDeleteMode.value = newMode === "DELETE_FEATURE";
    console.log(
      "🔄 isDeleteMode updated to:",
      isDeleteMode.value,
      "from mode:",
      newMode
    );
  },
  { immediate: true } // Pour exécuter immédiatement au montage
);

// Watcher pour changer de mode d'édition
watch(
  () => props.activeEditMode,
  (newMode, oldMode) => {
    console.log("🔄 Edit mode changed:", { oldMode, newMode });

    // Si on quitte le mode CREATE_POLYGON, terminer automatiquement le polygone
    if (
      oldMode === "CREATE_POLYGON" &&
      newMode !== "CREATE_POLYGON" &&
      currentPolygonPoints.length >= 3
    ) {
      console.log("🔺 Auto-finishing polygon when leaving CREATE_POLYGON mode");
      finishPolygon();
    }

    // Nettoyer l'état précédent
    if (oldMode) {
      cleanupCurrentDrawing();
    }

    // Nettoyer tous les événements d'édition
    map.off("mousedown", handleMouseDown);
    map.off("mousemove", handleMouseMove);
    map.off("mouseup", handleMouseUp);
    map.off("contextmenu", handleRightClick);
    map.off("mousedown", handleShapeMouseDown);
    map.off("mousemove", handleShapeMouseMove);
    map.off("mouseup", handleShapeMouseUp);
    map.off("dragstart", preventDragDuringShapeDrawing);
    map.off("mousedown", handleMoveMouseDown);
    map.off("mousemove", handleMoveMouseMove);
    map.off("mouseup", handleMoveMouseUp);
    map.off("keydown", handleKeyDown);

    // Réattacher les événements selon le nouveau mode
    if (newMode === "CREATE_LINE" || newMode === "CREATE_FREE_LINE") {
      console.log("📏 Reattaching line drawing events");
      map.on("mousedown", handleMouseDown);
      map.on("mousemove", handleMouseMove);
      map.on("mouseup", handleMouseUp);
    } else if (newMode === "CREATE_SHAPES") {
      console.log("🔷 Reattaching shape drawing events");
      map.on("mousedown", handleShapeMouseDown);
      map.on("mousemove", handleShapeMouseMove);
      map.on("mouseup", handleShapeMouseUp);
      map.on("dragstart", preventDragDuringShapeDrawing);
    } else if (newMode === "CREATE_POLYGON") {
      console.log("⬡ Reattaching polygon drawing events");
      map.on("contextmenu", handleRightClick);
    } else {
      // Mode sélection/déplacement (pas de mode actif ou mode par défaut)
      console.log("🎯 Reattaching selection and move events for default mode");
      map.on("mousedown", handleMoveMouseDown);
      map.on("mousemove", handleMoveMouseMove);
      map.on("mouseup", handleMoveMouseUp);
    }

    // TOUJOURS attacher handleKeyDown en mode édition pour permettre la suppression
    if (props.editMode) {
      console.log("🔄 Attaching keydown event for delete functionality");
      map.on("keydown", handleKeyDown);
    }

    // Mettre à jour le curseur
    updateMapCursor();
  }
);

// Watcher pour la forme sélectionnée
watch(
  () => props.selectedShape,
  (newShape, oldShape) => {
    console.log("Shape changed:", { oldShape, newShape });
  }
);

function cleanupCurrentDrawing() {
  currentLinePoints = [];
  // NE PAS nettoyer currentPolygonPoints et tempPolygon ici
  // pour que les lignes du polygone persistent lors du changement de mode
  if (tempLine) {
    drawnItems.removeLayer(tempLine);
    tempLine = null;
  }
  freeLinePoints = [];
  isDrawingFree = false;
  if (tempFreeLine) {
    drawnItems.removeLayer(tempFreeLine);
    tempFreeLine = null;
  }
}

// Watchers
watch(selectedYear, (newYear) => {
  debouncedUpdate(newYear);
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
      featureLayerManager.toggleFeature(featureId, visible);
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
