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
      <p v-if="zoneFeatures.length === 0">Aucune zone</p>
      <ul v-else class="space-y-2">
        <li
          v-for="feature in zoneFeatures"
          :key="feature.id ?? feature.properties?.name"
          class="flex items-center gap-2"
        >
          <span
            class="inline-block h-4 w-4 rounded-sm border border-base-300 shrink-0"
            :style="{
              backgroundColor: toCssColor(feature.properties?.colorRgb),
            }"
          />
          <span class="text-sm leading-tight">
            {{ feature.properties?.name || "Sans nom" }}
          </span>
        </li>
      </ul>
    </div>
  </div>
</template>

<script>
export default {
  name: "Legend",
  props: {
    zoneFeatures: {
      type: Array,
      default: () => [],
    },
  },
  methods: {
    toCssColor(colorRgb) {
      if (!colorRgb) return "transparent";

      if (Array.isArray(colorRgb)) {
        const [r = 0, g = 0, b = 0] = colorRgb;
        return `rgb(${r}, ${g}, ${b})`;
      }

      const value = String(colorRgb).trim();

      if (value.startsWith("rgb(") || value.startsWith("#")) {
        return value;
      }

      return `rgb(${value})`;
    },
  },
};
</script>
