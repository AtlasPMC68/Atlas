<template>
  <div id="map" style="height: 80vh; width: 100%;"></div>
</template>

<script setup>
import { onMounted } from 'vue';
import L from 'leaflet';

onMounted(() => {
  const map = L.map('map').setView([52.9399, -73.5491], 5);

  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
    attribution: '&copy; Esri &mdash; Esri, DeLorme, NAVTEQ',
  }).addTo(map);

  /*L.gridLayer({
    createTile: function () {
      const tile = document.createElement('canvas');
      tile.width = 256;
      tile.height = 256;
      const ctx = tile.getContext('2d');
      ctx.fillStyle = '#ffffff'; // ou transparent si tu préfères
      ctx.fillRect(0, 0, 256, 256);
      return tile;
    }
  }).addTo(map);*/

  let currentBordersLayer = null;

  function loadBordersForYear(year) {
    if (currentBordersLayer) {
      map.removeLayer(currentBordersLayer);
    }

    fetch('/geojson/borders.geojson')
      .then(res => res.json())
      .then(data => {
        currentBordersLayer = L.geoJSON(data, {
          filter: feature => {
            const start = feature.properties.start_year;
            const end = feature.properties.end_year;
            return year >= start && year <= end;
          },
          style: {
            color: '#444',
            weight: 1,
            fill: false
          },
          onEachFeature: (feature, layer) => {
            layer.bindPopup(`${feature.properties.name} (${feature.properties.start_year}–${feature.properties.end_year})`);
          }
        }).addTo(map);
      });
  }

  loadBordersForYear(1700);

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
