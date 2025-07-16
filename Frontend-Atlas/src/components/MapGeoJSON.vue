<template>
  <div>
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
  featureVisibility: Map
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


// Function to display the map
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
});

// Gestionnaire de layers par feature
const featureLayerManager = {
  layers: new Map(),

  addFeatureLayer(featureId, layer) {
    if (this.layers.has(featureId)) {
      map.removeLayer(this.layers.get(featureId));
    }
    this.layers.set(featureId, layer);

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
    this.layers.forEach(layer => map.removeLayer(layer));
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
    console.log("is first time called mounting your mom");
  } else {
    if (lastCurrentYear == closestYear) {
      console.log("returning because same year");
      return;
    }
  }
  console.log("not returning because not the same year last \ncurrentyear: " + lastCurrentYear + " \nclosest year: " + closestYear);
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

  safeFeatures.forEach(feature => {
    // Defensive check
    if (!feature.geometry || !Array.isArray(feature.geometry.coordinates)) {
      return;
    }

    const [lng, lat] = feature.geometry.coordinates;
    const coord = [lat, lng];

    const point = L.circleMarker(coord, {
      radius: 6,
      fillColor: feature.color || "#000",
      color: feature.color || "#000",
      weight: 1,
      opacity: feature.opacity ?? 1,
      fillOpacity: feature.opacity ?? 1,
    });

    const label = L.marker(coord, {
      icon: L.divIcon({
        className: "city-label-text",
        html: feature.name,
        iconSize: [100, 20],
        iconAnchor: [-8, 15],
      }),
      interactive: false,
    });

    const layerGroup = L.layerGroup([point, label]);
    featureLayerManager.addFeatureLayer(feature.id, layerGroup);
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

 

function renderAllFeatures() {
  featureLayerManager.clearAllFeatures();

  const featuresByType = {
    point: filteredFeatures.value.filter(f => f.type === 'point'),
    polygon: filteredFeatures.value.filter(f => f.type === 'zone'),
    arrow: filteredFeatures.value.filter(f => f.type === 'arrow')
  };

  renderCities(featuresByType.point);
  renderZones(featuresByType.polygon);
  renderArrows(featuresByType.arrow);

  emit('features-loaded', filteredFeatures.value);
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
  transform: rotate(0deg); /* statique pour l’instant */
}

</style>
