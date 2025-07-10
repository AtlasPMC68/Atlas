<template>
  <div>
    <TimelineSlider v-model:year="selectedYear" />
    <div id="map" class="z-10" style="height: 80vh; width: 100%"></div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import L from "leaflet";
import TimelineSlider from "../components/TimelineSlider.vue";

const selectedYear = ref(1740); // initial displayed year

// List of available years
const availableYears = [
  1400, 1500, 1530, 1600, 1650, 1700, 1715, 1783, 1800, 1815, 1880, 1900, 1914,
  1920, 1930, 1938, 1945, 1960, 1994, 2000, 2010,
];

let map = null;
let currentRegionsLayer = null;
let currentCitiesLayer = null;
let baseTileLayer = null;
let labelLayer = null;

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

// Loads the GeoJSON file called cities and displays only cities founded before or at the selected year
function loadCitiesForYear(year) {
  fetch(`/geojson/cities.geojson`)
    .then((res) => {
      if (!res.ok) throw new Error("File /geojson/cities.geojson not found");
      return res.json();
    })
    .then((data) => {
      // Filter cities based on foundation_year
      const filteredFeatures = data.features.filter(
        (feature) =>
          feature.properties.foundation_year !== undefined &&
          feature.properties.foundation_year <= year
      );

      const filteredGeoJSON = {
        type: "FeatureCollection",
        features: filteredFeatures,
      };

      const cityMarkers = filteredFeatures.map((feature) => {
        const coords = [
          feature.geometry.coordinates[1],
          feature.geometry.coordinates[0],
        ]; // Leaflet requires [lat, lng]

        // Black circle (point)
        const circleMarker = L.circleMarker(coords, {
          radius: 6,
          fillColor: "#000",
          color: "#000",
          weight: 1,
          opacity: 1,
          fillOpacity: 1,
        });

        // Label as DivIcon
        const label = L.marker(coords, {
          icon: L.divIcon({
            className: "city-label-text",
            html: feature.properties.name,
            iconSize: [100, 20], // approximate width/height
            iconAnchor: [-8, 15], // shifts the label above the point
          }),
          interactive: false, // avoids interfering with map interactions
        });

        // Group for point + label
        return L.layerGroup([circleMarker, label]);
      });

      currentCitiesLayer = L.layerGroup(cityMarkers).addTo(map);
    })
    .catch((err) => {
      console.warn(err.message);
    });
}

// Removes all layers except for the base tile layer
function removeGeoJSONLayers() {
  map.eachLayer((layer) => {
    if (layer !== baseTileLayer) {
      map.removeLayer(layer);
    }
  });

  // Reset references
  currentRegionsLayer = null;
  currentCitiesLayer = null;
}

// Loads all necessary layers for the given year
function loadAllLayersForYear(year) {
  removeGeoJSONLayers();
  loadRegionsForYear(year);
  loadCitiesForYear(year);
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
