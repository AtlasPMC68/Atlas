<template>
  <BasePickerModal
    :is-open="isOpen"
    title="Délimiter la légende"
    description="Tracez un rectangle sur l'image pour indiquer la zone de légende. Vous pouvez sauter cette étape si la carte n'a pas de légende."
    confirm-label="Confirmer la légende"
    :is-confirm-disabled="!legendBounds"
    show-skip
    @close="emit('close')"
    @skip="onSkip"
    @confirm="onConfirm"
  >
    <template #image-area>
      <h3 class="px-3 py-2 text-sm font-medium bg-base-200 border-b">
        Carte importée (sélection de la légende)
      </h3>
      <div
        ref="container"
        class="relative h-[28rem] bg-base-200 select-none"
        @mousedown="onMouseDown"
        @mousemove="onMouseMove"
        @mouseup="onMouseUp"
        @mouseleave="onMouseUp"
      >
        <img
          v-if="imageUrl"
          ref="imageEl"
          :src="imageUrl"
          class="w-full h-full object-contain pointer-events-none"
          alt="Carte importée"
          @load="onImageLoad"
        />

        <div
          v-if="selectionStyle"
          class="absolute border-2 border-[#2563eb] bg-[#2563eb]/15 pointer-events-none"
          :style="selectionStyle"
        />
      </div>
    </template>
  </BasePickerModal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import BasePickerModal from "../import/BasePickerModal.vue";
import type { LegendBounds } from "../../typescript/legend";

const props = withDefaults(
  defineProps<{
    isOpen: boolean;
    imageUrl: string;
    initialBounds: LegendBounds | null;
  }>(),
  {
    isOpen: false,
    initialBounds: null,
  },
);

const emit = defineEmits<{
  (e: "close"): void;
  (e: "skip"): void;
  (e: "confirmed", payload: LegendBounds): void;
}>();

const container = ref<HTMLDivElement | null>(null);
const imageEl = ref<HTMLImageElement | null>(null);

const imageNaturalWidth = ref<number>(0);
const imageNaturalHeight = ref<number>(0);

const isDrawing = ref<boolean>(false);
const dragStart = ref<{ x: number; y: number } | null>(null);
const legendBounds = ref<LegendBounds | null>(props.initialBounds);

watch(
  () => props.initialBounds,
  (value) => {
    legendBounds.value = value;
  },
);

watch(
  () => props.isOpen,
  (opened) => {
    if (opened) {
      legendBounds.value = props.initialBounds;
    }
  },
  { immediate: true },
);

const displayRect = computed(() => {
  if (
    !container.value ||
    !imageNaturalWidth.value ||
    !imageNaturalHeight.value
  ) {
    return null;
  }

  const rect = container.value.getBoundingClientRect();
  const cw = rect.width;
  const ch = rect.height;

  const baseScale = Math.min(
    cw / imageNaturalWidth.value,
    ch / imageNaturalHeight.value,
  );
  const displayW = imageNaturalWidth.value * baseScale;
  const displayH = imageNaturalHeight.value * baseScale;
  const offsetX = (cw - displayW) / 2;
  const offsetY = (ch - displayH) / 2;

  return {
    offsetX,
    offsetY,
    displayW,
    displayH,
    baseScale,
  };
});

const selectionStyle = computed(() => {
  if (!legendBounds.value || !displayRect.value) return null;

  const { offsetX, offsetY, baseScale } = displayRect.value;

  return {
    left: `${offsetX + legendBounds.value.x * baseScale}px`,
    top: `${offsetY + legendBounds.value.y * baseScale}px`,
    width: `${legendBounds.value.width * baseScale}px`,
    height: `${legendBounds.value.height * baseScale}px`,
  };
});

function onImageLoad(): void {
  if (!imageEl.value) return;
  imageNaturalWidth.value = imageEl.value.naturalWidth || 0;
  imageNaturalHeight.value = imageEl.value.naturalHeight || 0;
}

function getImageLocalPoint(
  event: MouseEvent,
): { x: number; y: number } | null {
  if (!container.value || !displayRect.value) return null;

  const containerRect = container.value.getBoundingClientRect();
  const px = event.clientX - containerRect.left;
  const py = event.clientY - containerRect.top;

  const { offsetX, offsetY, displayW, displayH, baseScale } = displayRect.value;
  const ix = px - offsetX;
  const iy = py - offsetY;

  if (ix < 0 || iy < 0 || ix > displayW || iy > displayH) {
    return null;
  }

  return {
    x: ix / baseScale,
    y: iy / baseScale,
  };
}

function onMouseDown(event: MouseEvent): void {
  const point = getImageLocalPoint(event);
  if (!point) return;

  isDrawing.value = true;
  dragStart.value = point;
  legendBounds.value = {
    x: point.x,
    y: point.y,
    width: 0,
    height: 0,
  };
}

function onMouseMove(event: MouseEvent): void {
  if (!isDrawing.value || !dragStart.value) return;

  const point = getImageLocalPoint(event);
  if (!point) return;

  const x1 = Math.min(dragStart.value.x, point.x);
  const y1 = Math.min(dragStart.value.y, point.y);
  const x2 = Math.max(dragStart.value.x, point.x);
  const y2 = Math.max(dragStart.value.y, point.y);

  legendBounds.value = {
    x: x1,
    y: y1,
    width: x2 - x1,
    height: y2 - y1,
  };
}

function onMouseUp(): void {
  isDrawing.value = false;
  dragStart.value = null;

  if (!legendBounds.value) return;
  if (legendBounds.value.width < 2 || legendBounds.value.height < 2) {
    legendBounds.value = null;
  }
}

function onSkip(): void {
  legendBounds.value = null;
  emit("skip");
}

function onConfirm(): void {
  if (!legendBounds.value) return;
  emit("confirmed", legendBounds.value);
}
</script>
