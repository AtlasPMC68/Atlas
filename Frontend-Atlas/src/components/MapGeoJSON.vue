<template>
  <div>
    <TimelineSlider v-model:year="selectedYear" />
    <div id="map" style="height: 80vh; width: 100%"></div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import L from "leaflet";
import TimelineSlider from "../components/TimelineSlider.vue";

const selectedYear = ref(1740); // année initiale affichée

// Liste des années disponibles
const availableYears = [
  1400, 1500, 1530, 1600, 1650, 1700, 1715, 1783, 1800, 1815, 1880, 1900, 1914,
  1920, 1930, 1938, 1945, 1960, 1994, 2000, 2010,
];

let map = null;
let currentGeoJsonLayer = null;
let baseTileLayer = null;
let labelLayer = null;

onMounted(() => {
  map = L.map("map").setView([52.9399, -73.5491], 5);

  // Map en background
  baseTileLayer = L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
    {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 19,
    }
  ).addTo(map);

  // Appel la fonction avec l'année 1740 (phase de test sans timeline)
  loadGeoJSONForYear(selectedYear.value);
});

// Retourne la plus grande année disponible selon l'année demandée
function getClosestAvailableYear(year) {
  const sorted = [...availableYears].sort((a, b) => a - b);
  for (let i = sorted.length - 1; i >= 0; i--) {
    if (year >= sorted[i]) return sorted[i];
  }
  return sorted[0]; // par défaut, retourne la plus ancienne
}

let lastRequestedYear = null;

// Cherche le geojson qui s'appel world_(year) et affiche son contenu sur la carte
function loadGeoJSONForYear(year) {
  removeGeoJSONLayers();

  const closestYear = getClosestAvailableYear(year);
  lastRequestedYear = closestYear;

  // Supprime l'ancien layer immédiatement
  /*if (currentGeoJsonLayer) {
    map.removeLayer(currentGeoJsonLayer);
    currentGeoJsonLayer = null;
  }*/

  const filename = `/geojson/world_${closestYear}.geojson`;

  fetch(filename)
    .then((res) => {
      if (!res.ok) throw new Error("Fichier non trouvé : " + filename);
      return res.json();
    })
    .then((data) => {
      // Vérifie si cette réponse est encore pertinente
      if (lastRequestedYear !== closestYear) {
        // La réponse est obsolète, on ne l'ajoute pas
        return;
      }

      currentGeoJsonLayer = L.geoJSON(data, {
        style: {
          color: "#444",
          weight: 2,
          fill: false,
        },
        onEachFeature: (feature, layer) => {
          layer.bindPopup(feature.properties.name || "Sans nom");
        },
      }).addTo(map);
    })
    .catch((err) => {
      console.warn(err.message);
    });
}

function removeGeoJSONLayers() {
  map.eachLayer((layer) => {
    if (
      layer !== baseTileLayer && // ne supprime pas la couche de fond
      layer !== labelLayer && // ne supprime pas le layer de labels
      layer instanceof L.GeoJSON // supprime les autres GeoJSON
    ) {
      map.removeLayer(layer);
    }
  });
}

function loadAllLayersForYear(year) {
  loadGeoJSONForYear(year);
  //loadCitiesForYear(year);
}

function debounce(fn, delay) {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), delay);
  };
}

const debouncedUpdate = debounce((year) => {
  loadAllLayersForYear(year);
}, 300); // attend 300ms sans nouveau changement

watch(selectedYear, (year) => {
  debouncedUpdate(year);
});
</script>
