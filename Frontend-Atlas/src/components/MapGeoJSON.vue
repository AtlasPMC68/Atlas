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
let currentRegionsLayer = null;
let currentCitiesLayer = null;
let baseTileLayer = null;
let labelLayer = null;

// Fonction de display de la carte
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

  loadAllLayersForYear(selectedYear.value);
});

// Retourne la plus grande année disponible selon l'année demandée
function getClosestAvailableYear(year) {
  const sorted = [...availableYears].sort((a, b) => a - b);
  for (let i = sorted.length - 1; i >= 0; i--) {
    if (year >= sorted[i]) return sorted[i];
  }
  return sorted[0]; // par défaut, retourne la plus ancienne
}

// Cherche le geojson qui s'appel world_(year) et affiche son contenu sur la carte
function loadRegionsForYear(year) {
  const closestYear = getClosestAvailableYear(year);

  const filename = `/geojson/world_${closestYear}.geojson`;

  fetch(filename)
    .then((res) => {
      if (!res.ok) throw new Error("Fichier non trouvé : " + filename);
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
          layer.bindPopup(feature.properties.name || "Sans nom");
        },
      }).addTo(map);
    })
    .catch((err) => {
      console.warn(err.message);
    });
}

// Cherche le geojson qui s'appel cities et affiche sur la carte les villes fondée avant ou à la même année que celle sélectionnée
function loadCitiesForYear(year) {
  fetch(`/geojson/cities.geojson`)
    .then((res) => {
      if (!res.ok)
        throw new Error("Fichier /geojson/cities.geojson introuvable");
      return res.json();
    })
    .then((data) => {
      // Filtrer les villes selon foundation_year
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
        ]; // Leaflet veut [lat, lng]

        // Cercle noir (point)
        const circleMarker = L.circleMarker(coords, {
          radius: 6,
          fillColor: "#000",
          color: "#000",
          weight: 1,
          opacity: 1,
          fillOpacity: 1,
        });

        // Texte comme DivIcon
        const label = L.marker(coords, {
          icon: L.divIcon({
            className: "city-label-text",
            html: feature.properties.name,
            iconSize: [100, 20], // largeur/hauteur approximative
            iconAnchor: [-8, 15], // décale le texte pour être au-dessus du point
          }),
          interactive: false, // évite d’interférer avec la carte
        });

        // Groupe pour point + label
        return L.layerGroup([circleMarker, label]);
      });

      currentCitiesLayer = L.layerGroup(cityMarkers).addTo(map);
    })
    .catch((err) => {
      console.warn(err.message);
    });
}

// Retire toutes les couches sauf la couche de base contenant la carte de référence
function removeGeoJSONLayers() {
  map.eachLayer((layer) => {
    if (layer !== baseTileLayer) {
      map.removeLayer(layer);
    }
  });

  // Réinitialise les références
  currentRegionsLayer = null;
  currentCitiesLayer = null;
}

// Load tous les layers nécessaires
function loadAllLayersForYear(year) {
  removeGeoJSONLayers();
  loadRegionsForYear(year);
  loadCitiesForYear(year);
}

// Crée un délai entre les mise à jour de la carte pour éviter des erreurs causer par un changement rapide des années
function debounce(fn, delay) {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), delay);
  };
}

// Appel le debounce pour charger les geoJSON
const debouncedUpdate = debounce((year) => {
  loadAllLayersForYear(year);
}, 300); // attend 300ms sans nouveau changement

// Retransmet l'année sélectionnée dans le slider
watch(selectedYear, (year) => {
  debouncedUpdate(year);
});
</script>
