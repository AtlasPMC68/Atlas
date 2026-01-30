<template>
  <div class="relative w-full h-full">
    <div ref="mapContainer" class="w-full h-full bg-[#cfe8ff]"></div>

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
  point: {
    type: Array,
    default: null, // [lat, lng] or null
  },
  drawingMode: {
    type: String,
    default: "polyline", // 'polyline' or 'point'
  },
});

const emit = defineEmits(["update:modelValue", "update:point"]);

const mapContainer = ref(null);
const isDrawingMode = ref(false);
let isDrawingActive = false;
let map = null;
let landLayer = null;
let polylineLayer = null;
let pointMarker = null;
const localPoints = ref([]); // internal copy of the polyline

onMounted(async () => {
  map = L.map(mapContainer.value, {
    // Prevents "throwing" the map outside bounds when max bounds are set.
    maxBoundsViscosity: 1.0,
  }).setView([20, 0], 2);

  // "Continents only" basemap using local Natural Earth land polygons (no rivers/roads/labels).
  // Served from Frontend-Atlas/public/geojson/ne_land.geojson
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

    // Fit to land bounds and prevent panning/zooming outside that extent.
    const bounds = landLayer.getBounds();
    if (bounds.isValid()) {
      const padded = bounds.pad(0.05);

      // Limit panning so the user can't drag away from the continents.
      map.setMaxBounds(padded);

      // Fit to the layer once, then lock minZoom to that fitted zoom
      // so you can't zoom out further.
      map.fitBounds(padded, { padding: [10, 10] });
      map.setMinZoom(map.getZoom());
    }
  } catch (e) {
    console.error("Failed to load Natural Earth land basemap", e);
  }

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

    if (landLayer) {
      map.removeLayer(landLayer);
      landLayer = null;
    }

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
  
  if (props.drawingMode === "point") {
    // Point mode: single click to place a point
    setPoint(e.latlng);
  } else {
    // Polyline mode: hold and drag to draw
    isDrawingActive = true;
    addPoint(e.latlng);
  }
}

function onMapMouseMove(e) {
  if (!isDrawingMode.value || !isDrawingActive) return;
  if (props.drawingMode === "polyline") {
    addPoint(e.latlng);
  }
}

function onMapMouseUp() {
  isDrawingActive = false;
}

function setPoint(latlng) {
  const point = [latlng.lat, latlng.lng];
  emit("update:point", point);
  
  // Draw a marker for the point
  if (pointMarker) {
    map.removeLayer(pointMarker);
  }
  pointMarker = L.circleMarker(latlng, {
    radius: 6,
    fillColor: "#dc2626",
    color: "#dc2626",
    weight: 2,
    opacity: 1,
    fillOpacity: 0.8,
  });
  pointMarker.addTo(map)
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
