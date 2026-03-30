<template>
  <!--
  <div>
    <h2 class="text-lg font-semibold mb-4 text-base-content">
      Contrôles des couches
    </h2>

    <div class="space-y-4">
      <div
        v-for="group in featureGroups"
        :key="group.type"
        class="collapse collapse-arrow bg-base-100"
      >
        <input type="checkbox" :checked="false" />
        <div class="collapse-title text-sm font-medium">
          {{ group.label }} ({{ group.features.length }})
        </div>
        <div class="collapse-content">
          <div class="space-y-2">
            <div
              v-for="feature in group.features"
              :key="feature.id"
              class="form-control"
            >
              <label class="label cursor-pointer justify-start gap-3">
                <input
                  type="checkbox"
                  :checked="featureVisibility.get(feature.id) !== false"
                  @change="
                    $emit(
                      'toggle-feature',
                      feature.id,
                      ($event.target as HTMLInputElement).checked,
                    )
                  "
                  class="checkbox checkbox-sm checkbox-primary"
                />
                <span class="label-text text-sm">
                  {{ feature.properties?.name || "Élément sans nom" }}
                </span>
              </label>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="divider"></div>
    <div class="flex gap-2">
      <button @click="toggleAll(true)" class="btn btn-xs btn-primary flex-1">
        Tout afficher
      </button>
      <button @click="toggleAll(false)" class="btn btn-xs btn-outline flex-1">
        Tout masquer
      </button>
    </div>
  </div>
  -->
  <div class="flex h-full min-h-0 flex-col gap-0">
    <div class="tabs tabs-boxed mb-3 bg-base-200 gap-2">
      <button
        v-for="group in featureGroups"
        :key="group.type"
        type="button"
        role="tab"
        class="tab flex-1 p-0"
        :title="`${group.label}`"
        @click="activeGroupType = group.type"
      >
        <component
          :is="getGroupIcon(group.type)"
          class="h-5 w-5 text-primary-500"
        />
      </button>
    </div>

    <div class="flex flex-1 flex-col gap-4">
      <div class="text-sm font-bold">
        {{ activeGroup.label }}
      </div>

      <div class="space-y-2">
        <div
          v-if="activeGroup.features.length > 0"
          v-for="feature in activeGroup.features"
          :key="feature.id"
          class="form-control"
        >
          <label class="label cursor-pointer justify-start gap-3">
            <input
              type="checkbox"
              :checked="featureVisibility.get(feature.id) !== false"
              @change="
                $emit(
                  'toggle-feature',
                  feature.id,
                  ($event.target as HTMLInputElement).checked,
                )
              "
              class="checkbox checkbox-sm checkbox-primary"
            />
            <span class="label-text text-sm">
              {{ feature.properties?.name || "Élément sans nom" }}
            </span>
          </label>
        </div>
        <div v-else class="flex text-sm opacity-60">
          Aucun élément à afficher
        </div>
      </div>
    </div>

    <div class="pt-2">
      <div class="divider my-2"></div>
      <div class="flex gap-2 items-center">
        <button
          @click="toggleAll(true)"
          class="btn btn-sm btn-primary flex-1 w-full h-10 font-bold"
        >
          Tout afficher
        </button>
        <button
          @click="toggleAll(false)"
          class="btn btn-sm btn-outline flex-1 w-full h-10 font-bold"
        >
          Tout masquer
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { Component } from "vue";
import {
  EllipsisHorizontalIcon,
  MapIcon,
  MapPinIcon,
  PhotoIcon,
  Square2StackIcon,
} from "@heroicons/vue/24/outline";
import type {
  Feature,
  FeatureVisibilityGroup,
  MapElementType,
} from "../typescript/feature";
import { getMapElementType } from "../utils/featureHelpers";

const props = defineProps<{
  features: Feature[];
  featureVisibility: Map<string, boolean>;
}>();

const emit = defineEmits(["toggle-feature"]);

const groupIcons: Record<MapElementType, Component> = {
  point: MapPinIcon,
  zone: MapIcon,
  shape: Square2StackIcon,
  other: EllipsisHorizontalIcon,
  image: PhotoIcon,
};

const featureGroups = computed(() => {
  const groups: FeatureVisibilityGroup[] = [
    { type: "point", label: "Ville(s)", features: [] as Feature[] },
    { type: "zone", label: "Zone(s)", features: [] as Feature[] },
    { type: "shape", label: "Forme(s)", features: [] as Feature[] },
    { type: "image", label: "Image(s)", features: [] as Feature[] },
    { type: "other", label: "Autre(s)", features: [] as Feature[] },
  ];

  props.features.forEach((feature: Feature) => {
    const featureType = getMapElementType(feature);
    if (!featureType) return;

    const targetGroup = groups.find(
      (currentGroup) => currentGroup.type === featureType,
    );

    if (targetGroup) targetGroup.features.push(feature);
  });

  return groups;
});

const activeGroupType = ref<MapElementType | null>(null);

const activeGroup = computed(() => {
  if (!activeGroupType.value) return featureGroups.value[0] ?? null;

  return (
    featureGroups.value.find((group) => group.type === activeGroupType.value) ??
    featureGroups.value[0] ??
    null
  );
});

watch(
  featureGroups,
  (groups) => {
    if (groups.length === 0) {
      activeGroupType.value = null;
      return;
    }

    const hasActiveGroup = groups.some(
      (group) => group.type === activeGroupType.value,
    );

    if (!hasActiveGroup) {
      activeGroupType.value = groups[0].type;
    }
  },
  { immediate: true },
);

function getGroupIcon(type: MapElementType): Component {
  return groupIcons[type];
}

function toggleAll(visible: boolean) {
  props.features.forEach((feature) => {
    emit("toggle-feature", feature.id, visible);
  });
}
</script>
