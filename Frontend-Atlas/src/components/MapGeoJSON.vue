<template>
  <div>
    <TimelineSlider v-model:year="selectedYear" />
    <div id="map" style="height: 80vh; width: 100%"></div>
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
  selectedYear: Number
});

// Émissions vers la vue parent
const emit = defineEmits(['features-loaded']);

const selectedYear = ref(1740); // initial displayed year

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

const mockedZonesFromBackend = [
  {
    id: "zone-1",
    name: "Canada",
    fillColor: "#3366ff",
    year: 1750,
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [-71.2, 46.8],
          [-71.3, 47.1],
          [-70.9, 47.2],
          [-70.8, 46.9],
          [-71.2, 46.8]
        ]
      ]
    }
  },
  {
    id: "zone-2",
    name: "British Colonies",
    fillColor: "#ff3333",
    year: 1750,
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [-76.0, 39.0],
          [-75.5, 39.5],
          [-75.0, 39.0],
          [-75.5, 38.5],
          [-76.0, 39.0]
        ]
      ]
    }
  }
];
let zonesLayer = null;

const mockedArrows = [
  {
    id: "arrow-1",
    name: "Déplacement militaire",
    from: { lat: 46.8139, lng: -71.2082 }, // Québec
    to: { lat: 45.5017, lng: -73.5673 },   // Montréal
    color: "#000",
    year: 1750
  },
  {
    id: "arrow-2",
    name: "Migration",
    from: { lat: 45.5017, lng: -73.5673 },
    to: { lat: 47.5, lng: -70.0 },
    color: "#ff0000",
    year: 1750
  }
];
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

  loadAllLayersForYear(selectedYear.value);
});

async function fetchFeaturesAndRender(map, year) {
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

    renderCities(map, cities);
    renderZones(map, zones);
    renderArrows(map, arrows);

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

// Loads the GeoJSON file named world_(year) and displays its content on the map
function loadRegionsForYear(year) {
  const closestYear = getClosestAvailableYear(year);

  const filename = `/geojson/world_${closestYear}.geojson`;

  fetch(filename)
    .then((res) => {
      if (!res.ok) throw new Error("File not found: " + filename);
      return res.json();
    })
    .then((data) => {
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

function renderCities(map, cities) {
  if (citiesLayer) {
    map.removeLayer(citiesLayer);
  }

  const cityGroups = cities.map(city => {
    const [lng, lat] = city.geometry.coordinates;
    const coord = [lat, lng];

    const point = L.circleMarker(coord, {
      radius: 6,
      fillColor: city.color || "#000",
      color: city.color || "#000",
      weight: 1,
      opacity: city.opacity ?? 1,
      fillOpacity: city.opacity ?? 1,
    });

    const label = L.marker(coord, {
      icon: L.divIcon({
        className: "city-label-text",
        html: city.name,
        iconSize: [100, 20],
        iconAnchor: [-8, 15],
      }),
      interactive: false,
    });

    return L.layerGroup([point, label]);
  });

  citiesLayer = L.layerGroup(cityGroups).addTo(map);
}

function renderZones(map, zones) {
  if (zonesLayer) {
    map.removeLayer(zonesLayer);
  }

  const features = zones.map(zone => ({
    type: "Feature",
    geometry: zone.geometry,
    properties: {
      name: zone.name,
      fillColor: zone.color || "#ccc",
    }
  }));

  zonesLayer = L.geoJSON({ type: "FeatureCollection", features }, {
    style: feature => ({
      fillColor: feature.properties.fillColor,
      fillOpacity: 0.5,
      color: "#333",
      weight: 1
    }),
    onEachFeature: (feature, layer) => {
      if (feature.properties?.name) {
        layer.bindPopup(feature.properties.name);
      }
    }
  }).addTo(map);
}

function renderArrows(map, arrows) {
  if (arrowsLayer) {
    map.removeLayer(arrowsLayer);
  }

  const arrowLines = arrows.map(arrow => {
    const coords = arrow.geometry.coordinates.map(([lng, lat]) => [lat, lng]);

    const line = L.polyline(coords, {
      color: arrow.color || "#000",
      weight: arrow.stroke_width ?? 2,
      opacity: arrow.opacity ?? 1
    }).addTo(map);

    line.arrowheads({
      size: '10px',
      frequency: 'endonly',
      fill: true
    });

    line.bindPopup(arrow.name);
    return line;
  });

  arrowsLayer = L.layerGroup(arrowLines).addTo(map);
}

function removeGeoJSONLayers() {
  map.eachLayer((layer) => {
    if (layer !== baseTileLayer) {
      map.removeLayer(layer);
    }
  });
  currentRegionsLayer = null;
}

// Loads all necessary layers for the given year
let isLoading = false;

async function loadAllLayersForYear(year) {
  if (isLoading) return;
  isLoading = true;

  try {
    removeGeoJSONLayers();
    loadRegionsForYear(year);
    await fetchFeaturesAndRender(map, year);
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

// Uses debounce to load GeoJSON layers
const debouncedUpdate = debounce((year) => {
  loadAllLayersForYear(year);
}, 300); // wait 300ms without changes

// Watches the selected year and updates the map accordingly
watch(selectedYear, (year) => {
  debouncedUpdate(year);
});
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
