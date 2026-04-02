<template>
  <div class="card bg-base-100">
    <div
      class="card-body"
      @mousedown.stop
      @click.stop
      @dblclick.stop
      @wheel.stop
    >
      <h2 class="card-title">Légende</h2>
      <p v-if="props.zoneFeatures.length === 0">Aucune zone</p>
      <ul v-else class="space-y-2">
        <li
          v-for="feature in props.zoneFeatures"
          :key="feature.id ?? feature.properties?.name"
          class="flex items-center gap-2"
        >
          <span
            class="inline-block h-4 w-4 rounded-sm border border-base-300 shrink-0"
            :style="{
              backgroundColor: getLegendFeatureColor(feature),
            }"
          />
          <span class="text-sm leading-tight">
            {{ feature.properties?.name || "Élément sans nom" }}
          </span>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Feature } from "../../typescript/feature";
import { getFeatureRgbColor } from "../../utils/featureHelpers";

const props = withDefaults(
  defineProps<{
    zoneFeatures: Feature[];
  }>(),
  {
    zoneFeatures: () => [],
  },
);

function getLegendFeatureColor(feature: Feature): string {
  return getFeatureRgbColor(feature) ?? "transparent";
}
</script>
