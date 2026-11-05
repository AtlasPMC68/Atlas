<template>
  <div class="card bg-base-100 py-3">
    <div
      class="card-body p-0"
      @mousedown.stop
      @click.stop
      @dblclick.stop
      @wheel.stop
    >
      <h2 class="card-title m-0 p-0 flex items-center">
        Légende
        <button class="btn btn-ghost btn-sm ml-auto" @click="toggleLegend">
          <EyeIcon v-if="isLegendVisible" class="w-5 h-5" />
          <EyeSlashIcon v-else class="w-5 h-5" />
        </button>
      </h2>
      <template v-if="isLegendVisible">
        <p v-if="visibleZoneFeatures.length === 0">Aucune zone</p>
        <ul
          v-else
          class="space-y-2 max-h-[25vh] max-w-[20vh] overflow-y-auto pr-2"
        >
          <li
            v-for="feature in visibleZoneFeatures"
            :key="feature.id ?? feature.properties?.name"
            class="flex items-center gap-2 rounded px-1 py-0.5 cursor-pointer"
            :class="selectedFeatureId === String(feature.id) ? 'ring-2 ring-primary bg-primary/10' : 'hover:bg-base-200/60'"
            @click="selectFeature(feature)"
            @dblclick.prevent.stop="editFeature(feature)"
          >
            <span
              class="inline-block h-5 w-5 rounded-sm shrink-0 border-2"
              :style="{
                backgroundColor: rgbToRgba(
                  feature.properties?.colorRgb,
                  feature.properties?.fillOpacity ?? 0.5,
                ),
                borderColor: rgbToRgba(
                  feature.properties?.strokeColor ??
                    feature.properties?.colorRgb,
                  feature.properties?.strokeOpacity ?? 1.0,
                ),
                backgroundClip: 'padding-box',
              }"
            />
            <span
              class="text-sm leading-tight truncate min-w-0 flex-1"
              :title="feature.properties?.name || '! Nom manquant'"
            >
              {{ feature.properties?.name || "! Nom manquant" }}
            </span>
          </li>
        </ul>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { Feature } from "../../typescript/feature";
import { rgbToRgba } from "../../utils/utils";
import { EyeIcon, EyeSlashIcon } from "@heroicons/vue/24/outline";

const props = withDefaults(
  defineProps<{
    zoneFeatures: Feature[];
    featureVisibility: Map<string, boolean>;
    selectedFeatureId?: string | null;
  }>(),
  {
    zoneFeatures: () => [],
  },
);

const emit = defineEmits<{
  (event: "select-feature", featureId: string): void;
  (event: "edit-feature", feature: Feature): void;
}>();

const isLegendVisible = ref(true);

function selectFeature(feature: Feature) {
  if (feature.id != null) emit("select-feature", String(feature.id));
}

function editFeature(feature: Feature) {
  selectFeature(feature);
  emit("edit-feature", feature);
}

function toggleLegend() {
  isLegendVisible.value = !isLegendVisible.value;
}

const visibleZoneFeatures = computed(() =>
  props.zoneFeatures.filter((feature) => {
    const id = feature?.id;
    if (id == null) return true;
    return props.featureVisibility.get(id) !== false;
  }),
);
</script>
