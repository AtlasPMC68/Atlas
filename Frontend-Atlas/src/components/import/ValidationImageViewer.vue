<template>
  <div
    class="flex flex-col bg-gray-900 min-h-0 relative overflow-hidden"
    :class="width !== undefined ? 'shrink-0' : 'flex-1 min-w-0'"
    :style="width !== undefined ? { width: `${width}px` } : undefined"
  >
    <div class="px-3 py-2 bg-gray-800 text-white font-semibold flex items-center justify-between shrink-0 text-sm z-10">
      <span class="flex items-center gap-1.5">
        <PhotoIcon class="w-4 h-4 text-gray-400" />
        Image de référence
      </span>
      <div class="flex items-center gap-1">
        <template v-if="displayImageUrl">
          <button
            type="button"
            class="btn btn-xs btn-ghost text-white px-1.5 min-h-0 h-6 text-xs"
            title="Dézoomer"
            :disabled="zoom <= zoomMin"
            @click="zoomOut"
          >
            −
          </button>
          <button
            type="button"
            class="btn btn-xs btn-ghost text-white px-2 min-h-0 h-6 text-xs"
            title="Réinitialiser le zoom et le cadrage"
            @click="resetView"
          >
            {{ Math.round(zoom * 100) }}%
          </button>
          <button
            type="button"
            class="btn btn-xs btn-ghost text-white px-1.5 min-h-0 h-6 text-xs"
            title="Zoomer"
            :disabled="zoom >= zoomMax"
            @click="zoomIn"
          >
            +
          </button>
        </template>

        <label
          class="btn btn-xs btn-ghost text-white px-1.5 min-h-0 h-6 text-xs cursor-pointer"
          title="Charger une image pour visualiser"
        >
          <ArrowUpTrayIcon class="w-3.5 h-3.5" />
          <span class="hidden sm:inline">Changer</span>
          <input
            type="file"
            accept="image/avif,image/gif,image/jpeg,image/png,image/webp"
            class="hidden"
            :disabled="isUpdatingReferenceImage"
            @change="emit('select-image', $event)"
          />
        </label>
        <button
          v-if="displayImageUrl"
          type="button"
          class="btn btn-xs btn-ghost btn-square text-white hover:bg-error/80 px-1 min-h-0 h-6"
          title="Supprimer l'image de référence associée à cette carte"
          aria-label="Supprimer l'image de référence"
          @click="emit('remove-image')"
        >
          <XMarkIcon class="w-4 h-4" />
        </button>
      </div>
    </div>

    <div
      ref="container"
      class="flex-1 min-h-0 overflow-hidden relative flex items-center justify-center bg-gray-950 select-none"
      :class="cursorClass"
      @mousedown.left="onPointerDown"
      @mousemove="onPointerMove"
      @mouseup.left="onPointerUp"
      @mouseleave="onPointerLeave"
      @wheel.prevent="onWheel"
    >
      <div v-if="displayImageUrl" class="absolute" :style="stageStyle">
        <img
          ref="imageEl"
          :src="displayImageUrl"
          alt="Image de la carte pour visualisation"
          class="w-full h-full object-contain select-none pointer-events-none will-change-transform"
          @load="onImageLoad"
        />
      </div>
      <div v-else class="flex flex-col items-center justify-center p-6 text-center gap-3 max-w-sm">
        <PhotoIcon class="w-12 h-12 text-gray-500" />
        <div class="flex flex-col gap-1">
          <p class="text-sm text-gray-200 font-semibold">
            Aucune image originale disponible pour cette carte.
          </p>
          <p class="text-xs text-gray-400">
            Vous pouvez importer une image depuis votre ordinateur pour vous repérer pendant la validation.
          </p>
        </div>
        <label class="btn btn-primary btn-sm text-white cursor-pointer gap-1.5 font-medium shadow-xs mt-1">
          <ArrowUpTrayIcon class="w-3.5 h-3.5" />
          <span>Importer une image pour visualiser</span>
          <input
            type="file"
            accept="image/avif,image/gif,image/jpeg,image/png,image/webp"
            class="hidden"
            :disabled="isUpdatingReferenceImage"
            @change="emit('select-image', $event)"
          />
        </label>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { PhotoIcon, ArrowUpTrayIcon, XMarkIcon } from "@heroicons/vue/24/outline";
import { useZoomableStage } from "../../composables/useZoomableStage";

const props = defineProps<{
  width?: number;
  displayImageUrl?: string | null;
  imgZoom?: number;
  isUpdatingReferenceImage?: boolean;
}>();

const emit = defineEmits<{
  (e: "select-image", event: Event): void;
  (e: "remove-image"): void;
}>();

const container = ref<HTMLDivElement | null>(null);
const imageEl = ref<HTMLImageElement | null>(null);

const {
  stageStyle,
  zoom,
  panX,
  panY,
  zoomMin,
  zoomMax,
  updateBaseStage,
  clampPan,
  getLocalPointer,
  onWheel,
  zoomIn,
  zoomOut,
  resetView,
} = useZoomableStage({
  containerRef: container,
  imageRef: imageEl,
  zoomMin: 1,
  zoomMax: 6,
  zoomStepFactor: 1.25,
});

const isPointerDown = ref(false);
const pointerStart = ref({ x: 0, y: 0 });
const panStart = ref({ x: 0, y: 0 });

const cursorClass = computed(() => {
  if (zoom.value > 1) {
    return isPointerDown.value ? "cursor-grabbing" : "cursor-grab";
  }
  return "cursor-default";
});

function onImageLoad(): void {
  updateBaseStage();
}

watch(
  () => props.displayImageUrl,
  () => {
    resetView();
    updateBaseStage();
  },
);

function onPointerDown(event: MouseEvent): void {
  if (event.button !== 0) return;
  isPointerDown.value = true;
  const local = getLocalPointer(event);
  if (!local) return;
  pointerStart.value = local;
  panStart.value = { x: panX.value, y: panY.value };
}

function onPointerMove(event: MouseEvent): void {
  if (!isPointerDown.value) return;
  if (zoom.value <= 1) return;
  const local = getLocalPointer(event);
  if (!local) return;

  const dx = local.x - pointerStart.value.x;
  const dy = local.y - pointerStart.value.y;
  const clamped = clampPan(panStart.value.x + dx, panStart.value.y + dy);
  panX.value = clamped.x;
  panY.value = clamped.y;
}

function onPointerUp(): void {
  isPointerDown.value = false;
}

function onPointerLeave(): void {
  isPointerDown.value = false;
}
</script>
