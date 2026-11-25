<template>
  <svg
    class="shrink-0 overflow-hidden"
    :width="size"
    :height="size"
    :viewBox="`0 0 ${size} ${size}`"
    :title="title"
  >
    <circle
      :cx="size / 2"
      :cy="size / 2"
      :r="size / 2 - 2"
      :fill="fill"
      :fill-opacity="fillOpacity"
      :stroke="stroke"
      :stroke-width="strokeWidth"
      :stroke-opacity="strokeOpacity"
    />
  </svg>
</template>

<script setup lang="ts">
import { STYLE_POINT_SWATCH_PX } from "../utils/labelPresentation";

withDefaults(
  defineProps<{
    fill?: string;
    fillOpacity?: number;
    stroke?: string;
    strokeWidth?: number;
    strokeOpacity?: number;
    size?: number;
    title?: string;
  }>(),
  {
    fill: "#000000",
    fillOpacity: 1,
    stroke: "none",
    strokeWidth: 0,
    strokeOpacity: 1,
    size: STYLE_POINT_SWATCH_PX,
    title: undefined,
  },
);
</script>
