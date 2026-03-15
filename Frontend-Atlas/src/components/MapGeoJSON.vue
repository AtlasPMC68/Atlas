<template>
  <div class="relative h-full w-full z-0">
    <div id="map" style="height: 100vh; width: 100%"></div>
    <TimelineSlider v-model:year="selectedYearModel" />
  </div>
</template>

<script setup>
import { onMounted, watch, computed, onBeforeUnmount } from "vue";
import L from "leaflet";
import "leaflet-geometryutil";
import "leaflet-arrowheads";
import TimelineSlider from "../components/TimelineSlider.vue";

import { useMapLayers } from "../composables/useMapLayers.ts";
import { useMapTimeline } from "../composables/useMapTimeline.ts";
import { useMapDrawing } from "../composables/useMapDrawing.ts";

const props = defineProps({
  features: Array,
  featureVisibility: Map,
});

const drawing = useMapDrawing(() => {});
const layers = useMapLayers({ featureVisibility: props.featureVisibility });
const timeline = useMapTimeline();
const selectedYearModel = computed({
  get: () => timeline.selectedYear.value,
  set: (year) => {
    timeline.selectedYear.value = year;
  },
});

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
  map = L.map("map", {
    boxZoom: false,
  }).setView([52.9399, -73.5491], 5);
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
