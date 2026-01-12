<template>
  <div class="relative h-full w-full z-0">
    <div id="map" style="height: 80vh; width: 100%"></div>
    <TimelineSlider v-model:year="selectedYear" />
  </div>
</template>

<script setup>
import { onMounted, ref, watch, computed } from "vue";
import L from "leaflet";
import "leaflet-geometryutil"; // ← requis pour que arrowheads fonctionne
import "leaflet-arrowheads";   // ← ajoute la méthode `arrowheads` aux polylines
import TimelineSlider from "../components/TimelineSlider.vue";

// Props reçues de la vue parent
const props = defineProps({
  mapId: String,
  features: Array,
  featureVisibility: Map,
  editMode: {
    type: Boolean,
    default: false
  },
  activeEditMode: {
    type: String,
    default: null
  },
  selectedShape: {
    type: String,
    default: null
  }
});

// Émissions vers la vue parent
const emit = defineEmits(['features-loaded']);

const selectedYear = ref(1740); // initial displayed year
const previousFeatureIds = ref(new Set());

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
  { name: "Trois-Rivières", lat: 46.343, lng: -72.5406, foundation_year: 1634 }
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
    const pixelDistance = map.latLngToContainerPoint(lastPoint).distanceTo(
      map.latLngToContainerPoint(currentPoint)
    );

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
  allCircles.forEach(circle => {
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

    // Ajouter seulement si visible
    if (props.featureVisibility.get(featureId)) {
      map.addLayer(layer);
    }
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
    this.layers.forEach(layer => {
      // Retirer les cercles de la collection
      if (layer instanceof L.CircleMarker) {
        allCircles.delete(layer);
      }
      map.removeLayer(layer);
    });
    this.layers.clear();
  }
};

const filteredFeatures = computed(() => {
  return props.features.filter(feature => 
    new Date(feature.start_date).getFullYear() <= selectedYear.value &&
    (!feature.end_date || new Date(feature.end_date).getFullYear() >= selectedYear.value)
  );
});

async function fetchFeaturesAndRender(year) {
  const mapId = "11111111-1111-1111-1111-111111111111";

  try {
    const res = await fetch(`http://localhost:8000/maps/features/${mapId}`);
    if (!res.ok) throw new Error("Failed to fetch features");

    const allFeatures = await res.json();

    // Mettre à jour les features dans le parent
    emit('features-loaded', allFeatures);

    // Filtrer par année
    const features = allFeatures.filter(f =>
      new Date(f.start_date).getFullYear() <= year
    );

    // Dispatcher selon le type
    const cities = features.filter(f => f.type === "point");
    const zones = features.filter(f => f.type === "zone");
    const arrows = features.filter(f => f.type === "arrow");

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
    .then(res => {
      if (!res.ok) throw new Error("File not found: " + filename);
      return res.json();
    })
    .then(data => {
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
    .catch(err => {
      console.warn(err.message);
    });
}

function renderCities(features) {
  const safeFeatures = toArray(features);
  const currentZoom = map.getZoom();
  const radius = getRadiusForZoom(currentZoom);

  safeFeatures.forEach(feature => {
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
        direction: 'top',
        offset: [0, -5]
      });
    }

    featureLayerManager.addFeatureLayer(feature.id, circle);
  });
}

function renderZones(features) {
  const safeFeatures = toArray(features);


  safeFeatures.forEach(feature => {

    if (!feature.geometry || !Array.isArray(feature.geometry.coordinates)) {
      return;
    }

    const layer = L.geoJSON(feature.geometry, {
      style: {
        fillColor: feature.color || "#ccc",
        fillOpacity: 0.5,
        color: "#333",
        weight: 1
      }
    });

    if (feature.name) {
      layer.bindPopup(feature.name);
    }

    featureLayerManager.addFeatureLayer(feature.id, layer);
  });
}

function renderArrows(features) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach(feature => {

    if (!feature.geometry || !Array.isArray(feature.geometry.coordinates)) {
      return;
    }
    // Convert GeoJSON [lng, lat] → Leaflet [lat, lng]
    const latLngs = feature.geometry.coordinates.map(
      ([lng, lat]) => [lat, lng]
    );

    const line = L.polyline(latLngs, {
      color: feature.color || "#000",
      weight: feature.stroke_width ?? 2,
      opacity: feature.opacity ?? 1
    });

    line.addTo(map);

    // Apply arrowheads (after addTo(map))
    line.arrowheads({
      size: '10px',
      frequency: 'endonly',
      fill: true
    });

    if (feature.name) {
      line.bindPopup(feature.name);
    }

    featureLayerManager.addFeatureLayer(feature.id, line);
  });
}

function renderShapes(features) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach(feature => {
    if (!feature.geometry || !Array.isArray(feature.geometry.coordinates) || !feature.geometry.coordinates[0]) {
      return;
    }

    // Convertir les coordonnées GeoJSON en LatLng
    const latLngs = feature.geometry.coordinates[0].map(coord => [coord[1], coord[0]]);

    const square = L.polygon(latLngs, {
      color: feature.color || "#000000",
      weight: 2,
      fillColor: feature.color || "#cccccc",
      fillOpacity: feature.opacity ?? 0.5
    });

    if (feature.name) {
      square.bindPopup(feature.name);
    }

    featureLayerManager.addFeatureLayer(feature.id, square);
  });
}

 
function renderAllFeatures() {
  const currentFeatures = filteredFeatures.value;
  const currentIds = new Set(currentFeatures.map(f => f.id));
  const previousIds = previousFeatureIds.value;

  previousIds.forEach(oldId => {
    if (!currentIds.has(oldId)) {
      const layer = featureLayerManager.layers.get(oldId);
      if (layer) {
        map.removeLayer(layer);
        featureLayerManager.layers.delete(oldId);
      }
    }
  });

  const newFeatures = currentFeatures.filter(f => !previousIds.has(f.id));
  const featuresByType = {
    point: newFeatures.filter(f => f.type === 'point'),
    polygon: newFeatures.filter(f => f.type === 'zone'),
    arrow: newFeatures.filter(f => f.type === 'arrow'),
    square: newFeatures.filter(f => f.type === 'square'),
    rectangle: newFeatures.filter(f => f.type === 'rectangle'),
    circle: newFeatures.filter(f => f.type === 'circle'),
    triangle: newFeatures.filter(f => f.type === 'triangle'),
    oval: newFeatures.filter(f => f.type === 'oval')
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

  emit('features-loaded', currentFeatures);
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
    await loadRegionsForYear(year);  // <-- ici on attend le chargement complet
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
  map.on('zoomend', updateCircleSizes);
  
  // Initialiser l'édition si nécessaire
  if (props.editMode) {
    initializeEditControls();
  }
});

// NOUVELLES FONCTIONS POUR L'ÉDITION

// Initialiser les contrôles d'édition
function initializeEditControls() {
  if (!props.editMode) return;

  console.log('Initializing edit controls:', { editMode: props.editMode, activeEditMode: props.activeEditMode, selectedShape: props.selectedShape });

  // Layer pour les éléments dessinés
  drawnItems = new L.FeatureGroup();
  map.addLayer(drawnItems);

  // Écouter les événements selon le mode actif
  console.log('🎛️ Initializing edit controls:', {
    editMode: props.editMode,
    activeEditMode: props.activeEditMode,
    selectedShape: props.selectedShape
  });

  if (props.activeEditMode === 'CREATE_LINE' || props.activeEditMode === 'CREATE_FREE_LINE') {
    console.log('📏 Setting up line drawing events');
    // Événements pour le tracé de ligne
    map.on('mousedown', handleMouseDown);
    map.on('mousemove', handleMouseMove);
    map.on('mouseup', handleMouseUp);
  } else if (props.activeEditMode === 'CREATE_SHAPES') {
    console.log('🔷 Setting up shape drawing events');
    // Événements pour les formes
    map.on('mousedown', handleShapeMouseDown);
    map.on('mousemove', handleShapeMouseMove);
    map.on('mouseup', handleShapeMouseUp);
    map.on('dragstart', preventDragDuringShapeDrawing);
  } else if (props.activeEditMode === 'CREATE_POLYGON') {
    console.log('⬡ Setting up polygon drawing events');
    // Événements pour les polygones
    map.on('contextmenu', handleRightClick); // Clic droit pour finir le polygone
  }

  // Écouter les clics sur la carte selon le mode
  map.on('click', handleMapClick);
  map.on('dblclick', handleMapDoubleClick);
}

// Gestion des événements de souris pour le tracé
function handleMouseDown(e) {
  console.log('General mouse down triggered:', { editMode: props.editMode, activeEditMode: props.activeEditMode, selectedShape: props.selectedShape });
  if (!props.editMode) return;

  if (props.activeEditMode === 'CREATE_LINE') {
    isDrawingLine = true;
    lineStartPoint = e.latlng;

    // Désactiver le dragging de la carte pendant le tracé
    map.dragging.disable();

    // Créer la ligne temporaire (invisible au départ)
    tempLine = L.polyline([lineStartPoint, lineStartPoint], {
      color: '#000000',
      weight: 2,
      opacity: 0.7
    });
    drawnItems.addLayer(tempLine);
  }
  else if (props.activeEditMode === 'CREATE_FREE_LINE') {
    isDrawingFree = true;
    freeLinePoints = [e.latlng];

    // Désactiver le dragging de la carte pendant le tracé
    map.dragging.disable();

    // Créer la ligne libre temporaire
    tempFreeLine = L.polyline([e.latlng], {
      color: '#000000',
      weight: 2,
      opacity: 0.7
    });
    drawnItems.addLayer(tempFreeLine);
  }
}

function handleMouseMove(e) {
  if (isDrawingLine && lineStartPoint && tempLine) {
    // Mettre à jour les coordonnées de la ligne droite temporaire
    tempLine.setLatLngs([lineStartPoint, e.latlng]);
  }
  else if (isDrawingFree && tempFreeLine) {
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
  console.log('Map click triggered:', { editMode: props.editMode, activeEditMode: props.activeEditMode, selectedShape: props.selectedShape });

  if (!props.editMode || !props.activeEditMode) return;

  switch (props.activeEditMode) {
    case 'CREATE_POINT':
      createPointAt(e.latlng);
      break;
    case 'CREATE_POLYGON':
      handlePolygonClick(e.latlng);
      break;
    case 'CREATE_SHAPES':
      // Les formes sont gérées par les événements souris mousedown/mousemove/mouseup
      break;
  }
}

// Gérer les événements souris pour les formes (comme pour les lignes)
function handleShapeMouseDown(e) {
  console.log('🔽 Shape mouse down triggered:', {
    selectedShape: props.selectedShape,
    activeEditMode: props.activeEditMode,
    editMode: props.editMode,
    shapeState: shapeState,
    latlng: e.latlng
  });

  if (props.activeEditMode !== 'CREATE_SHAPES' || !props.selectedShape) {
    console.log('❌ Shape drawing not allowed - returning', {
      activeEditMode: props.activeEditMode,
      selectedShape: props.selectedShape,
      expectedMode: 'CREATE_SHAPES'
    });
    return;
  }

  console.log('✅ Shape drawing allowed - starting', props.selectedShape);

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
    case 'square':
      // Approche : centre + taille (comme le cercle, mais carré parfait)
      shapeState = 'drawing';
      shapeStartPoint = e.latlng;
      // On créera la forme temporaire au mouvement de souris
      console.log('Started drawing square center at:', e.latlng);
      break;

    case 'rectangle':
      // Approche : deux coins opposés
      shapeState = 'drawing';
      shapeStartPoint = e.latlng;
      tempShape = L.rectangle([
        [shapeStartPoint.lat, shapeStartPoint.lng],
        [shapeStartPoint.lat, shapeStartPoint.lng]
      ], {
        color: '#000000',
        weight: 2,
        fillColor: '#cccccc',
        fillOpacity: 0.5
      });
      drawnItems.addLayer(tempShape);
      console.log('Started drawing rectangle at:', e.latlng);
      break;

    case 'circle':
    case 'triangle':
      // Approche : centre + taille
      shapeState = 'drawing';
      shapeStartPoint = e.latlng;
      // On créera la forme temporaire au mouvement de souris
      console.log('Started drawing', shapeType, 'center at:', e.latlng);
      break;

    case 'oval':
      // Approche : centre + hauteur d'abord, puis largeur
      if (shapeState === null) {
        // Première étape : définir le centre
        shapeState = 'adjusting_height';
        shapeStartPoint = e.latlng;
        console.log('Started drawing oval center at:', e.latlng);
      }
      break;

    default:
      console.log('❌ Unknown shape type:', shapeType);
      isDrawingShape = false;
      map.dragging.enable();
      return;
  }
}

function handleShapeMouseUp(e) {
  console.log('🔺 Shape mouse up triggered:', {
    shapeState,
    selectedShape: props.selectedShape,
    hasStartPoint: !!shapeStartPoint,
    distance: shapeStartPoint ? map.distance(shapeStartPoint, e.latlng) : null
  });

  if (!shapeStartPoint || !props.selectedShape) {
    console.log('❌ No start point or shape selected');
    return;
  }

  const shapeType = props.selectedShape;

  switch (shapeType) {
    case 'square':
      if (shapeState === 'drawing') {
        isDrawingShape = false;
        map.dragging.enable();

        const distance = map.distance(shapeStartPoint, e.latlng);
        if (distance < 5) {
          cleanupTempShape();
          return;
        }

        console.log('✅ Creating final square');
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

    case 'rectangle':
      if (shapeState === 'drawing') {
        isDrawingShape = false;
        map.dragging.enable();

        const distance = map.distance(shapeStartPoint, e.latlng);
        if (distance < 5) {
          cleanupTempShape();
          return;
        }

        console.log('✅ Creating final rectangle');
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

    case 'circle':
      if (shapeState === 'drawing') {
        // Pour le cercle, mouseup finalise la forme (pas comme les autres)
        isDrawingShape = false;
        map.dragging.enable();

        const distance = map.distance(shapeStartPoint, e.latlng);
        if (distance < 5) {
          cleanupTempShape();
          return;
        }

        console.log('✅ Creating final circle');
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

    case 'triangle':
      if (shapeState === 'drawing') {
        isDrawingShape = false;
        map.dragging.enable();

        const distance = map.distance(shapeStartPoint, e.latlng);
        if (distance < 5) {
          cleanupTempShape();
          return;
        }

        console.log('✅ Creating final triangle');
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

    case 'oval':
      if (shapeState === 'adjusting_height') {
        // Première étape terminée : hauteur définie, passer à la largeur
        shapeState = 'adjusting_width';
        shapeEndPoint = e.latlng;
        console.log('✅ Oval height set, now adjusting width');
      } else if (shapeState === 'adjusting_width') {
        // Deuxième étape terminée : créer l'ovale final
        isDrawingShape = false;
        map.dragging.enable();

        console.log('✅ Creating final oval');
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
  const topLeftPixel = L.point(centerPixel.x - halfSidePixels, centerPixel.y - halfSidePixels);
  const bottomRightPixel = L.point(centerPixel.x + halfSidePixels, centerPixel.y + halfSidePixels);

  // Convertir en coordonnées géographiques
  const topLeft = map.containerPointToLatLng(topLeftPixel);
  const bottomRight = map.containerPointToLatLng(bottomRightPixel);

  const square = L.rectangle([
    [topLeft.lat, topLeft.lng],
    [bottomRight.lat, bottomRight.lng]
  ], {
    color: '#000000',
    weight: 2,
    fillColor: '#cccccc',
    fillOpacity: 0.5
  });

  drawnItems.addLayer(square);

  // Créer et sauvegarder automatiquement la feature
  const feature = squareToFeatureFromCenter(center, sizePoint);

  saveFeature(feature);
}

// Créer un rectangle entre deux coins opposés
function createRectangle(startCorner, endCorner) {
  // Même logique que le carré
  const minLat = Math.min(startCorner.lat, endCorner.lat);
  const maxLat = Math.max(startCorner.lat, endCorner.lat);
  const minLng = Math.min(startCorner.lng, endCorner.lng);
  const maxLng = Math.max(startCorner.lng, endCorner.lng);

  const rectangle = L.rectangle([
    [minLat, minLng],
    [maxLat, maxLng]
  ], {
    color: '#000000',
    weight: 2,
    fillColor: '#cccccc',
    fillOpacity: 0.5
  });

  drawnItems.addLayer(rectangle);

  const feature = rectangleToFeatureFromCorners(startCorner, endCorner);
  saveFeature(feature);
}

// Créer un cercle avec centre et rayon
function createCircle(center, edgePoint) {
  const radius = map.distance(center, edgePoint);

  const circle = L.circle(center, {
    radius: radius,
    color: '#000000',
    weight: 2,
    fillColor: '#cccccc',
    fillOpacity: 0.5
  });

  drawnItems.addLayer(circle);

  const feature = circleToFeatureFromCenter(center, edgePoint);
  saveFeature(feature);
}

// Créer un triangle avec centre et taille
function createTriangle(center, sizePoint) {
  const distance = map.distance(center, sizePoint);

  const points = [];
  for (let i = 0; i < 3; i++) {
    const angle = (i * 120 + 90) * Math.PI / 180; // Triangle pointant vers le haut
    const lat = center.lat + (distance / 111320) * Math.sin(angle);
    const lng = center.lng + (distance / 111320) * Math.cos(angle) / Math.cos(center.lat * Math.PI / 180);
    points.push([lat, lng]);
  }

  const triangle = L.polygon(points, {
    color: '#000000',
    weight: 2,
    fillColor: '#cccccc',
    fillOpacity: 0.5
  });

  drawnItems.addLayer(triangle);

  const feature = triangleToFeatureFromCenter(center, sizePoint);
  saveFeature(feature);
}

// Créer un ovale avec centre, hauteur et largeur
function createOval(center, heightPoint, widthPoint) {
  const heightRadius = Math.abs(center.lat - heightPoint.lat) * 111320;
  const widthRadius = Math.abs(center.lng - widthPoint.lng) * 111320 * Math.cos(center.lat * Math.PI / 180);

  const points = [];
  const steps = 32;
  for (let i = 0; i < steps; i++) {
    const angle = (i / steps) * 2 * Math.PI;
    const lat = center.lat + (heightRadius / 111320) * Math.sin(angle);
    const lng = center.lng + (widthRadius / 111320) * Math.cos(angle) / Math.cos(center.lat * Math.PI / 180);
    points.push([lat, lng]);
  }

  const oval = L.polygon(points, {
    color: '#000000',
    weight: 2,
    fillColor: '#cccccc',
    fillOpacity: 0.5
  });

  drawnItems.addLayer(oval);

  const feature = ovalToFeatureFromCenter(center, heightPoint, widthPoint);
  saveFeature(feature);
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
  const topLeftPixel = L.point(centerPixel.x - halfSidePixels, centerPixel.y - halfSidePixels);
  const bottomRightPixel = L.point(centerPixel.x + halfSidePixels, centerPixel.y + halfSidePixels);

  // Convertir les coordonnées pixels en coordonnées géographiques
  const topLeft = map.containerPointToLatLng(topLeftPixel);
  const bottomRight = map.containerPointToLatLng(bottomRightPixel);

  // Créer les coins du carré
  const bounds = [
    [topLeft.lat, topLeft.lng],
    [bottomRight.lat, bottomRight.lng]
  ];

  tempShape = L.rectangle(bounds, {
    color: '#000000',
    weight: 2,
    fillColor: '#cccccc',
    fillOpacity: 0.5
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
    [maxLat, maxLng]
  ];

  tempShape = L.rectangle(bounds, {
    color: '#000000',
    weight: 2,
    fillColor: '#cccccc',
    fillOpacity: 0.5
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
    color: '#000000',
    weight: 2,
    fillColor: '#cccccc',
    fillOpacity: 0.5
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
    const angle = (i * 120 + 90) * Math.PI / 180; // Commencer par le point du haut (90°)
    const lat = center.lat + (distance / 111320) * Math.sin(angle); // Approximation en degrés
    const lng = center.lng + (distance / 111320) * Math.cos(angle) / Math.cos(center.lat * Math.PI / 180);
    points.push([lat, lng]);
  }

  tempShape = L.polygon(points, {
    color: '#000000',
    weight: 2,
    fillColor: '#cccccc',
    fillOpacity: 0.5
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
    color: '#000000',
    weight: 2,
    fillColor: '#cccccc',
    fillOpacity: 0.5
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
  const widthRadius = Math.abs(center.lng - widthPoint.lng) * 111320 * Math.cos(center.lat * Math.PI / 180);

  // Créer une ellipse approximative avec un polygone
  const points = [];
  const steps = 32;
  for (let i = 0; i < steps; i++) {
    const angle = (i / steps) * 2 * Math.PI;
    const lat = center.lat + (heightRadius / 111320) * Math.sin(angle);
    const lng = center.lng + (widthRadius / 111320) * Math.cos(angle) / Math.cos(center.lat * Math.PI / 180);
    points.push([lat, lng]);
  }

  tempShape = L.polygon(points, {
    color: '#000000',
    weight: 2,
    fillColor: '#cccccc',
    fillOpacity: 0.5
  });

  drawnItems.addLayer(tempShape);
}

// Convertir un carré défini par centre et taille en feature GeoJSON
function squareToFeatureFromCenter(center, sizePoint) {
  const distance = map.distance(center, sizePoint);
  const halfSide = distance / Math.sqrt(2);

  // Convertir en degrés
  const latOffset = halfSide / 111320;
  const lngOffset = halfSide / (111320 * Math.cos(center.lat * Math.PI / 180));

  // Créer les coordonnées du carré (sens horaire)
  const geometry = {
    type: 'Polygon',
    coordinates: [[
      [center.lng - lngOffset, center.lat + latOffset], // Coin nord-ouest
      [center.lng + lngOffset, center.lat + latOffset], // Coin nord-est
      [center.lng + lngOffset, center.lat - latOffset], // Coin sud-est
      [center.lng - lngOffset, center.lat - latOffset], // Coin sud-ouest
      [center.lng - lngOffset, center.lat + latOffset]  // Retour au point de départ
    ]]
  };

  return {
    map_id: props.mapId,
    type: 'square',
    geometry: geometry,
    color: '#cccccc',
    opacity: 0.5,
    z_index: 1
  };
}

// Convertir un rectangle défini par deux coins opposés en feature GeoJSON
function rectangleToFeatureFromCorners(startCorner, endCorner) {
  const minLat = Math.min(startCorner.lat, endCorner.lat);
  const maxLat = Math.max(startCorner.lat, endCorner.lat);
  const minLng = Math.min(startCorner.lng, endCorner.lng);
  const maxLng = Math.max(startCorner.lng, endCorner.lng);

  const geometry = {
    type: 'Polygon',
    coordinates: [[
      [minLng, maxLat], // Coin nord-ouest
      [maxLng, maxLat], // Coin nord-est
      [maxLng, minLat], // Coin sud-est
      [minLng, minLat], // Coin sud-ouest
      [minLng, maxLat]  // Retour au point de départ
    ]]
  };

  return {
    map_id: props.mapId,
    type: 'rectangle',
    geometry: geometry,
    color: '#cccccc',
    opacity: 0.5,
    z_index: 1
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
    const lng = center.lng + (radius / 111320) * Math.cos(angle) / Math.cos(center.lat * Math.PI / 180);
    points.push([lng, lat]); // GeoJSON format [lng, lat]
  }
  points.push(points[0]); // Fermer le polygone

  const geometry = {
    type: 'Polygon',
    coordinates: [points]
  };

  return {
    map_id: props.mapId,
    type: 'circle',
    geometry: geometry,
    color: '#cccccc',
    opacity: 0.5,
    z_index: 1
  };
}

// Convertir un triangle défini par centre et taille en feature GeoJSON
function triangleToFeatureFromCenter(center, sizePoint) {
  const distance = map.distance(center, sizePoint);

  const points = [];
  for (let i = 0; i < 3; i++) {
    const angle = (i * 120 + 90) * Math.PI / 180; // Triangle pointant vers le haut
    const lat = center.lat + (distance / 111320) * Math.sin(angle);
    const lng = center.lng + (distance / 111320) * Math.cos(angle) / Math.cos(center.lat * Math.PI / 180);
    points.push([lng, lat]); // GeoJSON format [lng, lat]
  }
  points.push(points[0]); // Fermer le polygone

  const geometry = {
    type: 'Polygon',
    coordinates: [points]
  };

  return {
    map_id: props.mapId,
    type: 'triangle',
    geometry: geometry,
    color: '#cccccc',
    opacity: 0.5,
    z_index: 1
  };
}

// Convertir un ovale défini par centre, hauteur et largeur en feature GeoJSON
function ovalToFeatureFromCenter(center, heightPoint, widthPoint) {
  const heightRadius = Math.abs(center.lat - heightPoint.lat) * 111320;
  const widthRadius = Math.abs(center.lng - widthPoint.lng) * 111320 * Math.cos(center.lat * Math.PI / 180);

  const points = [];
  const steps = 32;
  for (let i = 0; i < steps; i++) {
    const angle = (i / steps) * 2 * Math.PI;
    const lat = center.lat + (heightRadius / 111320) * Math.sin(angle);
    const lng = center.lng + (widthRadius / 111320) * Math.cos(angle) / Math.cos(center.lat * Math.PI / 180);
    points.push([lng, lat]); // GeoJSON format [lng, lat]
  }
  points.push(points[0]); // Fermer le polygone

  const geometry = {
    type: 'Polygon',
    coordinates: [points]
  };

  return {
    map_id: props.mapId,
    type: 'oval',
    geometry: geometry,
    color: '#cccccc',
    opacity: 0.5,
    z_index: 1
  };
}

// Gérer le mouvement de la souris pour ajuster la forme
function handleShapeMouseMove(e) {
  lastMousePos = e.latlng; // Stocker la dernière position

  if (!props.activeEditMode === 'CREATE_SHAPES' || !props.selectedShape) return;

  const shapeType = props.selectedShape;

  switch (shapeType) {
    case 'square':
      if (shapeState === 'drawing' && shapeStartPoint) {
        console.log('🔄 Updating square center', shapeStartPoint, 'size to', e.latlng);
        updateTempSquareFromCenter(shapeStartPoint, e.latlng);
      }
      break;

    case 'rectangle':
      if (shapeState === 'drawing' && shapeStartPoint) {
        console.log('🔄 Updating rectangle from', shapeStartPoint, 'to', e.latlng);
        updateTempRectangleFromCorners(shapeStartPoint, e.latlng);
      }
      break;

    case 'circle':
      if (shapeState === 'drawing' && shapeStartPoint) {
        console.log('🔄 Updating circle center', shapeStartPoint, 'radius to', e.latlng);
        updateTempCircleFromCenter(shapeStartPoint, e.latlng);
      }
      break;

    case 'triangle':
      if (shapeState === 'drawing' && shapeStartPoint) {
        console.log('🔄 Updating triangle center', shapeStartPoint, 'size to', e.latlng);
        updateTempTriangleFromCenter(shapeStartPoint, e.latlng);
      }
      break;

    case 'oval':
      if (shapeState === 'adjusting_height' && shapeStartPoint) {
        console.log('🔄 Adjusting oval height from', shapeStartPoint, 'to', e.latlng);
        updateTempOvalHeight(shapeStartPoint, e.latlng);
      } else if (shapeState === 'adjusting_width' && shapeStartPoint && shapeEndPoint) {
        console.log('🔄 Adjusting oval width from', shapeStartPoint, 'to', e.latlng);
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
    color: '#000000',
    weight: 2,
    opacity: 1.0
  });

  drawnItems.addLayer(freeLine);

  // Créer et sauvegarder automatiquement la feature
  const feature = {
    map_id: props.mapId,
    type: 'polyline',
    geometry: {
      type: 'LineString',
      coordinates: smoothedPoints.map(point => [point.lng, point.lat])
    },
    color: '#000000',
    stroke_width: 2,
    opacity: 1.0,
    z_index: 1
  };

  saveFeature(feature);
}

// Gérer les clics droits pour finir les polygones
function handleRightClick(e) {
  if (!props.editMode || props.activeEditMode !== 'CREATE_POLYGON') return;

  // Empêcher le menu contextuel par défaut
  e.originalEvent.preventDefault();

  if (currentPolygonPoints.length >= 3) {
    finishPolygon();
  }
}

// Gérer les double-clics pour finir les polygones (gardé en fallback)
function handleMapDoubleClick(e) {
  if (!props.editMode || props.activeEditMode !== 'CREATE_POLYGON') return;

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
    fillColor: '#000000',
    color: '#333333',
    weight: 1,
    opacity: 0.8,
    fillOpacity: 0.8,
    draggable: true
  });

  // Ajouter à la collection des cercles
  allCircles.add(circle);

  drawnItems.addLayer(circle);

  // Créer et sauvegarder automatiquement la feature
  const feature = {
    map_id: props.mapId,
    type: 'point',
    geometry: {
      type: 'Point',
      coordinates: [latlng.lng, latlng.lat]
    },
    color: '#000000',
    opacity: 0.8,
    z_index: 1
  };

  saveFeature(feature);
}


// Créer une ligne entre deux points
function createLine(startLatLng, endLatLng) {
  const line = L.polyline([startLatLng, endLatLng], {
    color: '#000000',
    weight: 2,
    opacity: 1.0
  });
  
  drawnItems.addLayer(line);
  
  // Créer et sauvegarder automatiquement la feature
  const feature = {
    map_id: props.mapId,
    type: 'polyline',
    geometry: {
      type: 'LineString',
      coordinates: [
        [startLatLng.lng, startLatLng.lat],
        [endLatLng.lng, endLatLng.lat]
      ]
    },
    color: '#000000',
    stroke_width: 2,
    opacity: 1.0,
    z_index: 1
  };
  
  saveFeature(feature);
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
    lines.push(currentPolygonPoints[currentPolygonPoints.length - 1], currentPolygonPoints[0]);
  }

  // Créer une polyligne avec tous les segments
  if (lines.length > 0) {
    tempPolygon = L.polyline(lines, {
      color: '#000000',
      weight: 2,
      opacity: 1.0
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
    color: '#000000',
    weight: 2,
    fillColor: '#cccccc',
    fillOpacity: 0.5
  });

  drawnItems.addLayer(polygon);

  // Créer et sauvegarder automatiquement la feature
  const feature = {
    map_id: props.mapId,
    type: 'polygon',
    geometry: {
      type: 'Polygon',
      coordinates: [points.map(p => [p.lng, p.lat])]
    },
    color: '#cccccc',
    opacity: 0.5,
    z_index: 1
  };

  saveFeature(feature);

  // RÉINITIALISER pour permettre un nouveau polygone
  currentPolygonPoints = [];
}

// Fonction pour sauvegarder automatiquement une feature
async function saveFeature(featureData) {
  try {
    const response = await fetch('http://localhost:8000/maps/features', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(featureData)
    });
    
    if (!response.ok) {
      throw new Error('Failed to save feature');
    }
    
    const savedFeature = await response.json();
    console.log('Feature saved:', savedFeature);
    
    // Ajouter immédiatement la feature sauvegardée aux features actuelles
    // pour qu'elle soit visible même en mode édition
    const updatedFeatures = [...props.features, savedFeature];
    
    // Mettre à jour l'affichage selon le type de feature
    switch (savedFeature.type) {
      case 'point':
        renderCities([savedFeature]);
        break;
      case 'polyline':
        renderArrows([savedFeature]);
        break;
      case 'polygon':
        renderZones([savedFeature]);
        break;
      case 'square':
      case 'rectangle':
      case 'circle':
      case 'triangle':
      case 'oval':
        renderShapes([savedFeature]);
        break;
    }
    
    // Notifier le parent pour mettre à jour la liste complète
    emit('features-loaded', updatedFeatures);
    
  } catch (error) {
    console.error('Erreur lors de la sauvegarde automatique:', error);
  }
}

// Nettoyer le mode édition
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
  map.off('mousedown', handleMouseDown);
  map.off('mousemove', handleMouseMove);
  map.off('mouseup', handleMouseUp);
  map.off('contextmenu', handleRightClick);
  map.off('click', handleMapClick);
  map.off('dblclick', handleMapDoubleClick);
  map.off('zoomend', updateCircleSizes);

  // Nettoyer les événements des formes
  map.off('mousedown', handleShapeMouseDown);
  map.off('mousemove', handleShapeMouseMove);
  map.off('mouseup', handleShapeMouseUp);
  map.off('dragstart', preventDragDuringShapeDrawing);

  // Nettoyer les événements des formes
  map.off('mousedown', handleShapeMouseDown);
  map.off('mousemove', handleShapeMouseMove);
  map.off('mouseup', handleShapeMouseUp);
  map.off('dragstart', preventDragDuringShapeDrawing);

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

  // Recharger toutes les features quand on quitte le mode édition
  setTimeout(() => {
    fetchFeaturesAndRender(selectedYear.value);
  }, 100);
}

// Watcher pour le mode édition
watch(() => props.editMode, (newEditMode) => {
  if (newEditMode) {
    initializeEditControls();
    // Recharger les features quand on entre en mode édition
    fetchFeaturesAndRender(selectedYear.value);
  } else {
    cleanupEditMode();
  }
});

// Watcher pour changer de mode d'édition
watch(() => props.activeEditMode, (newMode, oldMode) => {
  console.log('🔄 Edit mode changed:', { oldMode, newMode });

  // Nettoyer l'état précédent
  if (oldMode) {
    cleanupCurrentDrawing();
  }

  // Nettoyer tous les événements d'édition
  map.off('mousedown', handleMouseDown);
  map.off('mousemove', handleMouseMove);
  map.off('mouseup', handleMouseUp);
  map.off('contextmenu', handleRightClick);
  map.off('mousedown', handleShapeMouseDown);
  map.off('mousemove', handleShapeMouseMove);
  map.off('mouseup', handleShapeMouseUp);
  map.off('dragstart', preventDragDuringShapeDrawing);

  // Réattacher les événements selon le nouveau mode
  if (newMode === 'CREATE_LINE' || newMode === 'CREATE_FREE_LINE') {
    console.log('📏 Reattaching line drawing events');
    map.on('mousedown', handleMouseDown);
    map.on('mousemove', handleMouseMove);
    map.on('mouseup', handleMouseUp);
  } else if (newMode === 'CREATE_SHAPES') {
    console.log('🔷 Reattaching shape drawing events');
    map.on('mousedown', handleShapeMouseDown);
    map.on('mousemove', handleShapeMouseMove);
    map.on('mouseup', handleShapeMouseUp);
    map.on('dragstart', preventDragDuringShapeDrawing);
  } else if (newMode === 'CREATE_POLYGON') {
    console.log('⬡ Reattaching polygon drawing events');
    map.on('contextmenu', handleRightClick);
  }
});

// Watcher pour la forme sélectionnée
watch(() => props.selectedShape, (newShape, oldShape) => {
  console.log('Shape changed:', { oldShape, newShape });
});

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

watch(() => props.features, () => {
  renderAllFeatures();
}, { deep: true });

watch(() => props.featureVisibility, (newVisibility) => {
  newVisibility.forEach((visible, featureId) => {
    featureLayerManager.toggleFeature(featureId, visible);
  });
}, { deep: true });
 

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