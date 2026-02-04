<template>
  <div class="relative w-full h-full">
    <div ref="mapContainer" class="w-full h-full bg-[#cfe8ff]"></div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from "vue";
import L from "leaflet";

const props = defineProps({
  worldBounds: {
    type: Object,
    default: null, // { west, south, east, north }
  },
  keypoints: {
    type: Array,
    default: () => [], // [{ id, pixel: {x,y}, geo: {lat,lng}, response }]
  },
  activeIndex: {
    type: Number,
    default: 0,
  },
});

const emit = defineEmits(["select-keypoint"]);

const mapContainer = ref(null);
let map = null;
let landLayer = null;
let markers = [];

function clearMarkers() {
  if (!map || !markers.length) return;
  markers.forEach((m) => map.removeLayer(m));
  markers = [];
}

function styleForIndex(index, isActive) {
  if (isActive) {
    return {
      radius: 7,
      fillColor: "#dc2626",
      color: "#b91c1c",
      weight: 2,
      opacity: 1,
      fillOpacity: 0.9,
    };
  }
  return {
    radius: 4,
    fillColor: "#2563eb",
    color: "#1d4ed8",
    weight: 1,
    opacity: 0.9,
    fillOpacity: 0.8,
  };
}

function renderKeypoints() {
  if (!map) return;
  clearMarkers();

  props.keypoints.forEach((kp, index) => {
    const lat = kp.geo?.lat;
    const lng = kp.geo?.lng;
    if (typeof lat !== "number" || typeof lng !== "number") return;

    const isActive = index === props.activeIndex;
    const marker = L.circleMarker([lat, lng], styleForIndex(index, isActive));

    // Allow user to choose the current point by clicking a marker
    marker.on("click", () => {
      emit("select-keypoint", index);
    });

    marker.addTo(map);
    markers.push(marker);
  });
}

function updateActiveMarker() {
  if (!map || !markers.length) return;
  markers.forEach((marker, index) => {
    const isActive = index === props.activeIndex;
    marker.setStyle(styleForIndex(index, isActive));
  });
}

async function initMap() {
  if (!mapContainer.value || map) return;

  map = L.map(mapContainer.value, {
    maxBoundsViscosity: 1.0,
  }).setView([20, 0], 2);

  try {
    const res = await fetch("/geojson/ne_coastline.geojson");
    if (!res.ok) throw new Error(`Failed to load ne_coastline.geojson: ${res.status}`);
    const geojson = await res.json();

    landLayer = L.geoJSON(geojson, {
      style: {
        fillColor: "#e5e7eb",
        fillOpacity: 0.9,
        color: "#9ca3af",
        weight: 1,
        opacity: 1,
      },
    }).addTo(map);

    const bounds = landLayer.getBounds();
    if (bounds.isValid()) {
      const padded = bounds.pad(0.05);
      map.setMaxBounds(padded);
    }
  } catch (e) {
    console.error("Failed to load Natural Earth land basemap", e);
  }

  if (props.worldBounds) {
    const { west, south, east, north } = props.worldBounds;
    const b = L.latLngBounds([south, west], [north, east]);
    if (b.isValid()) {
      const padded = b.pad(0.05);
      map.fitBounds(padded, { padding: [10, 10] });
      map.setMaxBounds(padded);
    }
  }

  renderKeypoints();
}

onMounted(async () => {
  await initMap();
});

onBeforeUnmount(() => {
  if (map) {
    clearMarkers();
    if (landLayer) {
      map.removeLayer(landLayer);
      landLayer = null;
    }
    map.remove();
    map = null;
  }
});

watch(
  () => props.keypoints,
  () => {
    renderKeypoints();
  },
  { deep: true },
);

watch(
  () => props.activeIndex,
  () => {
    updateActiveMarker();
  },
);

watch(
  () => props.worldBounds,
  (bounds) => {
    if (!map || !bounds) return;
    const { west, south, east, north } = bounds;
    const b = L.latLngBounds([south, west], [north, east]);
    if (b.isValid()) {
      const padded = b.pad(0.05);
      map.fitBounds(padded, { padding: [10, 10] });
      map.setMaxBounds(padded);
    }
  },
  { deep: true },
);
</script>
