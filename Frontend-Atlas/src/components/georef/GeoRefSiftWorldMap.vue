<template>
  <div class="relative w-full h-full">
    <div ref="mapContainer" class="w-full h-full bg-[#cfe8ff]"></div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from "vue";
import L from "leaflet";
import type {
  WorldBounds,
  CoastlineKeypoint,
  MatchedWorldPointSummary,
} from "../../typescript/georef";

const props = withDefaults(
  defineProps<{
    worldBounds: WorldBounds | null;
    keypoints: CoastlineKeypoint[];
    activeIndex: number;
    // Matched control points coming from the modal
    // [{ index, color }]
    matchedPoints: MatchedWorldPointSummary[];
  }>(),
  {
    worldBounds: null,
    keypoints: () => [],
    activeIndex: 0,
    matchedPoints: () => [],
  },
);

const emit = defineEmits<{
  (e: "select-keypoint", index: number): void;
}>();

const mapContainer = ref<HTMLDivElement | null>(null);
let map: L.Map | null = null;
let landLayer: L.GeoJSON | null = null;
let markers: L.Layer[] = [];

function clearMarkers(): void {
  if (!map || !markers.length) return;
  const currentMap = map;
  markers.forEach((m) => currentMap.removeLayer(m));
  markers = [];
}

function styleForIndex(isActive: boolean): L.CircleMarkerOptions {
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

function renderKeypoints(): void {
  if (!map) return;
  const currentMap = map;
  clearMarkers();

  props.keypoints.forEach((kp, index) => {
    const lat = kp.geo?.lat;
    const lng = kp.geo?.lng;
    if (typeof lat !== "number" || typeof lng !== "number") return;

    const isActive = index === props.activeIndex;

    const match = props.matchedPoints.find((m) => m.index === index);
    let marker: L.Marker | L.CircleMarker;

    if (match) {
      // Render matched points as triangles with a stable color using a divIcon
      const size = isActive ? 18 : 14;
      const half = size / 2;
      const color = match.color || "#dc2626";
      const html = `<div style="width:0;height:0;border-left:${half}px solid transparent;border-right:${half}px solid transparent;border-bottom:${size}px solid ${color};"></div>`;

      marker = L.marker([lat, lng], {
        icon: L.divIcon({
          className: "",
          html,
          iconSize: [size, size],
          iconAnchor: [half, size],
        }),
      });
    } else {
      // Unmatched points are plain circle markers
      marker = L.circleMarker([lat, lng], styleForIndex(isActive));
    }

    // Allow user to choose the current point by clicking a marker
    marker.on("click", () => {
      emit("select-keypoint", index);
    });

    marker.addTo(currentMap);
    markers.push(marker);
  });
}

function updateActiveMarker(): void {
  // Re-render everything so both matched triangles and circles
  // reflect the current active index.
  renderKeypoints();
}

async function initMap(): Promise<void> {
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
  () => props.matchedPoints,
  () => {
    renderKeypoints();
  },
  { deep: true },
);

watch(
  () => props.worldBounds,
  (bounds: WorldBounds | null) => {
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
