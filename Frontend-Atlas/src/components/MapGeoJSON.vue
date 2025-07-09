<template>
  <div id="map" style="height: 80vh; width: 100%"></div>
</template>

<script setup>
import { onMounted } from "vue";
import L from "leaflet";

// Liste des années disponibles
const availableYears = [
  1400, 1500, 1530, 1600, 1650, 1700, 1715, 1783, 1800, 1815, 1880, 1900, 1914,
  1920, 1930, 1938, 1945, 1960, 1994, 2000, 2010,
];

onMounted(() => {
  const map = L.map("map").setView([52.9399, -73.5491], 5);

  // Map en background
  L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
    {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 19,
    }
  ).addTo(map);

  let currentGeoJsonLayer = null;

  // Retourne la plus grande année disponible selon l'année demandée
  function getClosestAvailableYear(year) {
    const sorted = [...availableYears].sort((a, b) => a - b);
    for (let i = sorted.length - 1; i >= 0; i--) {
      if (year >= sorted[i]) return sorted[i];
    }
    return sorted[0]; // par défaut, retourne la plus ancienne
  }

  // Cherche le geojson qui s'appel world_(year) et affiche son contenu sur la carte
  function loadGeoJSONForYear(year) {
    const closestYear = getClosestAvailableYear(year);

    // Retir le layer du précédent geojson si nécessaire
    if (currentGeoJsonLayer) {
      map.removeLayer(currentGeoJsonLayer);
    }

    const filename = `/geojson/world_${closestYear}.geojson`;

    fetch(filename)
      .then((res) => {
        if (!res.ok) throw new Error("Fichier non trouvé : " + filename);
        return res.json();
      })
      .then((data) => {
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

  // Appel la fonction avec l'année 1740 (phase de test sans timeline)
  loadGeoJSONForYear(1740);
});
</script>
