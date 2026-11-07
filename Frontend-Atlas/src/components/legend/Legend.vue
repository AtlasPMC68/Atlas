<template>
  <div class="card bg-base-100 shadow-md p-3">
    <div
      class="card-body p-0"
      @mousedown.stop
      @click.stop
      @dblclick.stop
      @wheel.stop
    >
      <h2 class="card-title m-0 px-1 pb-1 text-base flex items-center">
        Légende
        <button
          class="btn btn-ghost btn-xs ml-auto"
          @click="toggleLegend"
          :title="isLegendVisible ? 'Masquer la légende' : 'Afficher la légende'"
        >
          <EyeIcon v-if="isLegendVisible" class="w-4 h-4" />
          <EyeSlashIcon v-else class="w-4 h-4" />
        </button>
      </h2>
      <template v-if="isLegendVisible">
        <p v-if="visibleZoneFeatures.length === 0" class="text-xs text-base-content/60 px-1 py-1">
          Aucune zone
        </p>
        <ul
          v-else
          class="space-y-1 max-h-[vh] min-w-[12rem] max-w-xs overflow-y-auto p-1"
        >
          <li
            v-for="feature in visibleZoneFeatures"
            :key="feature.id ?? feature.properties?.name"
            class="flex items-center gap-2 rounded-md px-2 py-1.5 cursor-pointer border transition-all"
            :class="[
              selectedFeatureId === String(feature.id)
                ? 'border-primary ring-1 ring-primary bg-primary/10 font-semibold'
                : 'border-transparent hover:bg-base-200/60',
            ]"
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
