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
  <div class="flex h-screen-minus-header min-h-0 flex-col">
    <div class="tabs tabs-boxed bg-base-200 gap-2 p-2">
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

    <!-- Liste des éléments avec contrôle de visibilité -->

    <div class="p-4 pt-0 flex flex-1 flex-col min-h-0">
      <div
        class="card flex flex-1 flex-col gap-4 min-h-0 overflow-y-auto scroll-stable"
      >
        <div class="text-sm font-bold">
          {{ activeGroup.label }}
        </div>
        <div class="flex flex-col gap-2">
          <div
            v-if="activeGroup.features.length > 0"
            v-for="feature in activeGroup.features"
            :key="feature.id"
            class="flex w-full flex-row items-center justify-between gap-2"
          >
            <label
              class="label cursor-pointer justify-start gap-2 flex-1 min-w-0"
            >
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
              <span class="label-text text-sm truncate">
                {{ feature.properties?.name || "Élément sans nom" }}
              </span>
            </label>
            <div class="flex h-8 w-8 items-center gap-1 mr-1">
              <button>
                <PencilSquareIcon
                  class="w-5 h-5 text-gray-500 hover:text-gray-800"
                />
              </button>
              <button>
                <TrashIcon class="w-5 h-5 text-red-500 hover:text-red-800" />
              </button>
            </div>
          </div>
          <div v-else class="flex text-sm opacity-60">
            Aucun élément à afficher
          </div>
        </div>
      </div>
    </div>

    <div class="px-4 py-2">
      <div class="divider m-0"></div>
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
  PencilSquareIcon,
  PhotoIcon,
  Square2StackIcon,
  TrashIcon,
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
