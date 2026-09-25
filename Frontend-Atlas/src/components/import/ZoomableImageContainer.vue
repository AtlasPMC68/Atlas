<template>
  <div class="flex flex-col h-full w-full">
    <div class="px-3 py-2 text-xs font-medium bg-base-200 border-b flex items-center justify-between gap-3 shrink-0">
      <span class="text-xs text-base-content/80">
        {{ headerText }}
      </span>
      <div class="flex items-center gap-2">
        <span class="text-xs text-base-content/60 whitespace-nowrap">
          {{ Math.round(zoom * 100) }}%
        </span>
        <button
          class="btn btn-xs"
          type="button"
          :disabled="zoom <= zoomMin || disabled"
          @click="$emit('zoom-out')"
        >
          −
        </button>
        <button
          class="btn btn-xs"
          type="button"
          :disabled="zoom === 1 || disabled"
          @click="$emit('reset-zoom')"
        >
          100%
        </button>
        <button
          class="btn btn-xs"
          type="button"
          :disabled="zoom >= zoomMax || disabled"
          @click="$emit('zoom-in')"
        >
          +
        </button>
      </div>
    </div>
    <slot></slot>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  headerText: string;
  zoom: number;
  zoomMin: number;
  zoomMax: number;
  disabled?: boolean;
}>();

defineEmits<{
  (e: "zoom-in"): void;
  (e: "zoom-out"): void;
  (e: "reset-zoom"): void;
}>();
</script>
