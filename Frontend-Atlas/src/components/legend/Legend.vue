<template>
  <div
    class="card bg-base-100 shadow-md p-3 overflow-hidden max-w-md max-h-[60vh]"
    :class="isLegendVisible ? 'min-w-[12rem] min-h-[5rem]' : 'min-w-0 min-h-0 w-auto h-auto'"
  >
    <div
      class="card-body p-0"
      @mousedown.stop
      @click.stop
      @dblclick.stop
      @wheel.stop
    >
      <h2 class="card-title m-0 px-1 text-base flex items-center" :class="{ 'pb-1': isLegendVisible }">
        Légende
      </h2>
      <template v-if="isLegendVisible">
        <p v-if="visibleZoneFeatures.length === 0" class="text-xs text-base-content/60 px-1 py-1">
          Aucune zone
        </p>
        <ul
          v-else
          class="space-y-1 max-h-[25vh] min-w-[12rem] max-w-xs overflow-y-auto p-1"
        >
          <li
            v-for="feature in visibleZoneFeatures"
            :key="feature.id ?? feature.properties?.name"
            class="flex items-center gap-2 rounded-md px-2 py-1.5 cursor-pointer border transition-all select-none"
            :class="[
              isFeatureSelected(feature.id)
                ? 'border-primary ring-1 ring-inset ring-primary bg-primary/10 font-semibold'
                : 'border-transparent hover:bg-base-200/60',
            ]"
            @click="onFeatureClick(feature, $event)"
            @dblclick.prevent.stop="onFeatureDblClick(feature, $event)"
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
              {{ feature.properties?.name || "Nom manquant" }}
            </span>
          </li>
        </ul>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { Feature } from "../../typescript/feature";
import { rgbToRgba } from "../../utils/utils";
import { createFeatureDoubleClickHandler } from "../../utils/featureInteraction";
import {
  applySelectionModifier,
  getContinuousRangeSelection,
} from "../../utils/selectionUtils";

const props = withDefaults(
  defineProps<{
    zoneFeatures: Feature[];
    featureVisibility: Map<string, boolean>;
    selectedFeatureId?: string | null;
    multiSelectedFeatureIds?: string[];
  }>(),
  {
    zoneFeatures: () => [],
  },
);

const emit = defineEmits<{
  (event: "select-feature", featureId: string | null): void;
  (event: "select-features", featureIds: string[]): void;
  (event: "edit-feature", feature: Feature): void;
}>();

const isLegendVisible = ref(true);

const lastSelectedAnchorId = ref<string | null>(props.selectedFeatureId ?? null);

watch(
  () => props.selectedFeatureId,
  (newId) => {
    if (newId) lastSelectedAnchorId.value = String(newId);
  },
);

function isFeatureSelected(id: string | number | undefined): boolean {
  if (id == null) return false;
  const strId = String(id);
  if (props.selectedFeatureId && String(props.selectedFeatureId) === strId) return true;
  if (
    props.multiSelectedFeatureIds &&
    props.multiSelectedFeatureIds.some((i) => String(i) === strId)
  )
    return true;
  return false;
}

const { handleClick: onFeatureClick, handleDblClick: onFeatureDblClick } =
  createFeatureDoubleClickHandler<Feature>({
    onSelect: (feature: Feature, event?: unknown) => {
      if (feature.id == null) return;
      const featureId = String(feature.id);
      const mouseEv = event as MouseEvent | undefined;
      const isCtrl = Boolean(mouseEv?.ctrlKey || mouseEv?.metaKey);
      const isShift = Boolean(mouseEv?.shiftKey);

      if (isCtrl || isShift) {
        const result = applySelectionModifier(featureId, isCtrl, isShift, {
          selectedId: props.selectedFeatureId,
          multiSelectedIds: props.multiSelectedFeatureIds ?? [],
          lastAnchorId: lastSelectedAnchorId.value,
          orderedIds: visibleZoneFeatures.value.map((f: Feature) => String(f.id)),
        });
        lastSelectedAnchorId.value = result.newAnchorId;
        emit("select-feature", result.selectedId);
        emit("select-features", result.multiSelectedIds);
        return;
      }

      lastSelectedAnchorId.value = featureId;
      emit("select-features", []);
      emit("select-feature", featureId);
    },
    onEdit: (feature: Feature) => {
      if (feature.id != null) {
        lastSelectedAnchorId.value = String(feature.id);
        emit("select-feature", String(feature.id));
      }
      emit("edit-feature", feature);
    },
    getId: (feature: Feature) => feature.id ?? feature.properties?.name,
  });

const visibleZoneFeatures = computed(() =>
  props.zoneFeatures.filter((feature: Feature) => {
    const id = feature?.id;
    if (id == null) return true;
    return props.featureVisibility.get(id) !== false;
  }),
);
</script>
