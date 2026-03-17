<template>
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
        <input type="checkbox" :checked="true" />
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
</template>

<script setup lang="ts">
import { computed } from "vue";
import { Feature } from "../typescript/feature";
import type { FeatureGroup } from "../typescript/featureVisibility";

const props = defineProps<{
  features: Feature[];
  featureVisibility: Map<string, boolean>;
}>();

const emit = defineEmits(["toggle-feature"]);

const featureGroups = computed(() => {
  const groups: FeatureGroup[] = [
    { type: "point", label: "Villes", features: [] as Feature[] },
    { type: "zone", label: "Zones", features: [] as Feature[] },
    { type: "arrow", label: "Flèches", features: [] as Feature[] },
    {
      type: "shape",
      label: "Formes",
      aliases: ["square", "rectangle", "circle", "triangle"],
      features: [] as Feature[],
    },
  ];

  props.features.forEach((feature: Feature) => {
    const featureType = feature?.type || "";

    const targetGroup = groups.find(
      (currentGroup) =>
        currentGroup.type === featureType ||
        currentGroup.aliases?.includes(featureType),
    );

    if (targetGroup) targetGroup.features.push(feature);
  });

  return groups.filter((g) => g.features.length > 0);
});

function toggleAll(visible: boolean) {
  props.features.forEach((feature) => {
    emit("toggle-feature", feature.id, visible);
  });
}
</script>
