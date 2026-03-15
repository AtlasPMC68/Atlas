<template>
  <div class="relative h-full w-full z-0">
    <div id="map" style="height: 100%; width: 100%"></div>
    <TimelineSlider v-model:year="selectedYearModel" />
  </div>
</template>

<script setup>
import { onMounted, watch, computed, onBeforeUnmount, ref } from "vue";
import L from "leaflet";
import "leaflet-geometryutil";
import "leaflet-arrowheads";
import TimelineSlider from "../components/TimelineSlider.vue";

import { useMapLayers } from "../composables/useMapLayers.ts";
import { useMapDrawing } from "../composables/useMapDrawing.ts";

const props = defineProps({
  features: Array,
  featureVisibility: Map,
});

const emit = defineEmits(["create", "edit", "remove"]);
const drawing = useMapDrawing(emit);
const layers = useMapLayers({ featureVisibility: props.featureVisibility });
const selectedYear = ref(1740);
const selectedYearModel = computed({
  get: () => selectedYear.value,
  set: (year) => {
    selectedYear.value = year;
  },
});

let map = null;

const filteredFeatures = computed(() => {
  return props.features.filter(
    (feature) =>
      new Date(feature.start_date).getFullYear() <=
        selectedYear.value &&
      (!feature.end_date ||
        new Date(feature.end_date).getFullYear() >=
          selectedYear.value),
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
  () => selectedYear.value,
  () => {
    if (!map) return;
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
