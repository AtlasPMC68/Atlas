<template>
  <div class="feature-controls">
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
                  @change="$emit('toggle-feature', feature.id, $event.target.checked)"
                  class="checkbox checkbox-sm checkbox-primary"
                />
                <span class="label-text text-sm">
                  {{ feature.properties?.name || feature.name || "Unnamed Feature" }}
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

<script setup>
import { computed } from "vue";

const props = defineProps({
  features: { type: Array, default: () => [] },
  featureVisibility: { type: Map, required: true },
});

const emit = defineEmits(["toggle-feature"]);

const featureGroups = computed(() => {
  const groups = [
    { type: "point", label: "Villes", features: [] },
    { type: "zone", label: "Zones", features: [] },
    { type: "polyline", label: "Lignes", features: [] },
    { type: "arrow", label: "Flèches", features: [] },
    { type: "shape", label: "Formes", features: [] },
  ];

  for (const feature of props.features) {
    const rawType =
      feature?.properties?.mapElementType ||
      feature?.type ||
      "";

    const isShapeKind = ["square", "rectangle", "circle", "triangle", "oval"].includes(rawType);
    const elementType = isShapeKind ? "shape" : rawType;

    const group = groups.find((g) => g.type === elementType);
    if (group) group.features.push(feature);
  }

  return groups.filter((g) => g.features.length > 0);
});

function toggleAll(visible) {
  for (const feature of props.features) {
    emit("toggle-feature", feature.id, visible);
  }
}
</script>
