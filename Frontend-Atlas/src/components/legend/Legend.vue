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
        <ul v-else class="space-y-2 max-h-[25vh] overflow-y-auto">
          <li
            v-for="feature in visibleZoneFeatures"
            :key="feature.id ?? feature.properties?.name"
            class="flex items-center gap-2"
          >
            <span
              class="inline-block h-4 w-4 rounded-sm shrink-0 border-2"
              :style="{
                backgroundColor: rgbToHex(feature.properties?.colorRgb),
                borderColor: rgbToHex(feature.properties?.strokeColor),
                opacity: feature.properties?.opacity ?? 0.5,
              }"
            />
            <span class="text-sm leading-tight">
              {{ feature.properties?.name || "Élément sans nom" }}
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
import { rgbToHex } from "../../utils/utils";
import { EyeIcon, EyeSlashIcon } from "@heroicons/vue/24/outline";

const props = withDefaults(
  defineProps<{
    zoneFeatures: Feature[];
    featureVisibility: Map<string, boolean>;
  }>(),
  {
    zoneFeatures: () => [],
  },
);

const isLegendVisible = ref(true);

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
