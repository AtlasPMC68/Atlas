<template>
  <div class="relative h-full w-full z-0">
    <div id="map" style="height: 100vh; width: 100%"></div>
    <TimelineSlider v-model:year="timeline.selectedYear.value" />
  </div>
</template>

<script setup>
import { ref, onMounted, watch, computed, onBeforeUnmount } from "vue";
import L from "leaflet";
import "leaflet-geometryutil";
import "leaflet-arrowheads";
import TimelineSlider from "../components/TimelineSlider.vue";

import { useMapLayers } from "../composables/useMapLayers.ts";
import { useMapTimeline } from "../composables/useMapTimeline.ts";
import { useMapDrawing } from "../composables/useMapDrawing.ts";

const props = defineProps({
  mapId: String,
  features: Array,
  featureVisibility: Map,
  editMode: { type: Boolean, default: false },
  activeEditMode: { type: String, default: null },
  selectedShape: { type: String, default: null },
});

const emit = defineEmits([
  "features-loaded",
  "mode-change",
  "feature-created",
  "feature-updated",
  "feature-deleted",
]);

// Simple wrapper for drawing events
const drawing = useMapDrawing((event, ...args) => {
  emit(event, args[0]);
});

// Create a minimal editing composable wrapper (just for layers, no custom handlers)
const editing = {
  isDeleteMode: ref(false),
};

const layers = useMapLayers({ editMode: props.editMode }, emit, editing);
const timeline = useMapTimeline();

let map = null;

const filteredFeatures = computed(() => {
  return props.features.filter(
    (feature) =>
      new Date(feature.start_date).getFullYear() <=
        timeline.selectedYear.value &&
      (!feature.end_date ||
        new Date(feature.end_date).getFullYear() >=
          timeline.selectedYear.value),
  );
});

function renderAllAndRebind() {
  if (!map) return;
  layers.renderAllFeatures(filteredFeatures.value, map);
}

onMounted(() => {
  map = L.map("map").setView([52.9399, -73.5491], 5);
  layers.initializeBaseLayers(map);
  timeline.loadRegionsForYear(timeline.selectedYear.value, map, true);
  drawing.initializeDrawing(map);
  renderAllAndRebind();
});

onBeforeUnmount(() => {
  if (map) {
    layers.clearAllLayers(map);
    map.remove();
    map = null;
  }
});

// Timeline year changes
watch(
  () => timeline.selectedYear.value,
  (newYear) => {
    if (!map) return;
    timeline.loadRegionsForYear(newYear, map);
    renderAllAndRebind();
  },
);

// Features rerender
watch(
  () => props.features,
  () => {
    if (!map) return;
    renderAllAndRebind();
  },
);

// Visibility toggle
watch(
  () => props.featureVisibility,
  (newVisibility) => {
    if (!newVisibility) return;
    newVisibility.forEach((visible, featureId) => {
      layers.featureLayerManager.toggleFeature(featureId, visible);
    });
  },
  { deep: true },
);
</script>

<style>
.city-label-text {
  font-size: 12px;
  font-weight: bold;
  color: black;
  background: transparent;
  padding: 2px 4px;
  border-radius: 3px;
  border: transparent;
}

.arrow-head {
  font-size: 20px;
  color: black;
  transform: rotate(0deg);
}

.temp-marker {
  background: none !important;
  border: none !important;
}

.line-start-marker {
  background: none !important;
  border: none !important;
}

.polygon-marker {
  background: white;
  border: 2px solid #000;
  border-radius: 50%;
  text-align: center;
  font-weight: bold;
  color: #000;
}
</style>
