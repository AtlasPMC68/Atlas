<template>
  <div id="map" style="height: 80vh; width: 100%;"></div>
</template>

<script setup>
import { onMounted } from 'vue';
import L from 'leaflet';

onMounted(() => {
  const map = L.map('map').setView([52.9399, -73.5491], 5);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors'
  }).addTo(map);

  const geojson = {
    type: "Feature",
    geometry: {
      type: "Polygon",
      coordinates: [[
        [-75, 50],
        [-72, 50],
        [-72, 52],
        [-75, 52],
        [-75, 50]
      ]]
    },
    properties: {
      name: "Zone Test Québec"
    }
  };

  L.geoJSON(geojson).addTo(map);
});
</script>
