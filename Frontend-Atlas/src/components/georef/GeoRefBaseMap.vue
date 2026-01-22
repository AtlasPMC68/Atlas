<template>
  <div class="relative w-full h-full">
    <div ref="mapContainer" class="w-full h-full"></div>

    <button
      type="button"
      class="btn btn-xs md:btn-sm btn-outline absolute top-2 right-2 z-[1000]"
      @click="toggleDrawingMode"
    >
      {{ isDrawingMode ? "Mode déplacement" : "Mode dessin" }}
    </button>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from "vue";
import L from "leaflet";

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => [], // [ [lat,lng], ... ]
  },
});

const emit = defineEmits(["update:modelValue"]);

const mapContainer = ref(null);
const isDrawingMode = ref(false);
let isDrawingActive = false;
let map = null;
let polylineLayer = null;
const localPoints = ref([]); // internal copy of the polyline

onMounted(() => {
  map = L.map(mapContainer.value).setView([20, 0], 2);

  L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
    {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 19,
    },
  ).addTo(map);

  localPoints.value = props.modelValue ? [...props.modelValue] : [];
  if (localPoints.value.length > 0) {
    redrawPolyline(localPoints.value);
  }

  map.on("mousedown", onMapMouseDown);
  map.on("mousemove", onMapMouseMove);
  map.on("mouseup", onMapMouseUp);
  map.on("mouseout", onMapMouseUp);
});

onBeforeUnmount(() => {
  if (map) {
    map.off("mousedown", onMapMouseDown);
    map.off("mousemove", onMapMouseMove);
    map.off("mouseup", onMapMouseUp);
    map.off("mouseout", onMapMouseUp);
    map.remove();
    map = null;
  }
});

function toggleDrawingMode() {
  isDrawingMode.value = !isDrawingMode.value;
  isDrawingActive = false;
  if (map) {
    // In drawing mode, completely freeze map interactions (no pan/zoom)
    if (isDrawingMode.value) {
      map.dragging.disable();
      map.scrollWheelZoom.disable();
      map.doubleClickZoom.disable();
      map.boxZoom.disable();
      map.keyboard.disable();
    } else {
      map.dragging.enable();
      map.scrollWheelZoom.enable();
      map.doubleClickZoom.enable();
      map.boxZoom.enable();
      map.keyboard.enable();
    }
  }
}

function onMapMouseDown(e) {
  if (!isDrawingMode.value) return;
  isDrawingActive = true;
  addPoint(e.latlng);
}

function onMapMouseMove(e) {
  if (!isDrawingMode.value || !isDrawingActive) return;
  addPoint(e.latlng);
}

function onMapMouseUp() {
  isDrawingActive = false;
}

function addPoint(latlng) {
  const next = [...localPoints.value, [latlng.lat, latlng.lng]];
  localPoints.value = next;
  emit("update:modelValue", next);
  redrawPolyline(next, false);
}

function redrawPolyline(points, shouldFit = true) {
  if (!map) return;
  if (polylineLayer) {
    map.removeLayer(polylineLayer);
  }
  if (!points || points.length === 0) return;

  polylineLayer = L.polyline(points, { color: "#2563eb", weight: 3 });
  polylineLayer.addTo(map);
  // Do not auto-fit while drawing; keep the current view stable.
  if (shouldFit) {
    // If you ever need an initial fit, you can call with shouldFit=true
    // from outside, but we keep it false during freehand drawing.
    // map.fitBounds(polylineLayer.getBounds(), { padding: [20, 20] });
  }
}

watch(
  () => props.modelValue,
  (val) => {
    localPoints.value = val ? [...val] : [];
    // Redraw without changing zoom/center to avoid jumping while drawing
    redrawPolyline(localPoints.value, false);
  },
);
</script>
