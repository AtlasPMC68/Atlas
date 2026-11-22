<template>
  <ZoomableImageContainer
    data-validation-viewer="true"
    :header-text="headerText"
    :zoom="zoom"
    :zoom-min="zoomMin"
    :zoom-max="zoomMax"
    :disabled="!displayImageUrl"
    @zoom-in="zoomIn"
    @zoom-out="zoomOut"
    @reset-zoom="resetView"
  >
    <template #actions>
      <label
        v-if="hasRegions"
        class="label cursor-pointer gap-1.5 py-0 text-xs text-base-content/80"
        title="Afficher sur l'image les cadres des textes détectés"
      >
        <input
          v-model="showRegions"
          type="checkbox"
          class="checkbox checkbox-xs checkbox-primary"
          data-testid="toggle-text-regions"
        />
        Cadres
      </label>
      <label
        class="btn btn-xs"
        :class="{ 'btn-disabled': isUpdatingReferenceImage }"
        title="Charger une autre image de référence"
      >
        <ArrowUpTrayIcon class="w-3.5 h-3.5" />
        <span class="hidden sm:inline">Changer</span>
        <input
          type="file"
          :accept="ACCEPTED_IMAGE_TYPES"
          class="hidden"
          :disabled="isUpdatingReferenceImage"
          @change="emit('select-image', $event)"
        />
      </label>
      <button
        v-if="displayImageUrl"
        type="button"
        class="btn btn-xs btn-square"
        :disabled="isUpdatingReferenceImage"
        title="Supprimer l'image de référence associée à cette carte"
        aria-label="Supprimer l'image de référence"
        @click="emit('remove-image')"
      >
        <XMarkIcon class="w-4 h-4" />
      </button>
    </template>

    <div
      ref="container"
      class="relative flex-1 min-h-0 bg-base-200 select-none overflow-hidden flex items-center justify-center"
      :class="cursorClass"
      @mousedown.left="onPointerDown"
      @mousemove="onPointerMove"
      @mouseup.left="onPointerUp"
      @mouseleave="onPointerLeave"
      @wheel.prevent="onWheel"
    >
      <template v-if="displayImageUrl">
        <div class="absolute" :style="stageStyle">
          <img
            ref="imageEl"
            :src="displayImageUrl"
            alt="Image de la carte pour visualisation"
            class="w-full h-full object-contain select-none pointer-events-none"
            @load="onImageLoad"
          />
        </div>

        <!-- Where each text was read on the image, and what was read there -->
        <button
          v-for="box in regionBoxes"
          :key="box.id"
          type="button"
          class="absolute rounded-sm border-2 transition-colors"
          :class="box.id === highlightedId
            ? 'border-primary-600 bg-primary-500/25 ring-2 ring-white z-10'
            : 'border-primary-600 bg-primary-500/5 ring-1 ring-white hover:bg-primary-500/20'"
          :style="box.style"
          :title="`Texte détecté : ${box.label}`"
          :aria-label="`Texte détecté : ${box.label}`"
          :aria-pressed="box.id === highlightedId"
          data-testid="text-region"
          @click.stop="emit('select-region', box.id)"
        >
          <span
            v-if="box.id === highlightedId"
            class="badge badge-primary badge-sm absolute left-1/2 -translate-x-1/2 whitespace-nowrap shadow"
            :class="box.labelBelow ? 'top-full mt-1' : 'bottom-full mb-1'"
          >
            {{ box.label }}
          </span>
        </button>
      </template>

      <div v-else class="flex flex-col items-center justify-center p-6 text-center gap-3 max-w-sm">
        <PhotoIcon class="w-12 h-12 text-base-content/30" />
        <div class="flex flex-col gap-1">
          <p class="text-sm font-semibold">
            Aucune image originale disponible pour cette carte.
          </p>
          <p class="text-xs text-base-content/60">
            Vous pouvez importer une image depuis votre ordinateur pour vous repérer pendant la validation.
          </p>
        </div>
        <label
          class="btn btn-primary btn-sm"
          :class="{ 'btn-disabled': isUpdatingReferenceImage }"
        >
          <ArrowUpTrayIcon class="w-4 h-4" />
          <span>Importer une image pour visualiser</span>
          <input
            type="file"
            :accept="ACCEPTED_IMAGE_TYPES"
            class="hidden"
            :disabled="isUpdatingReferenceImage"
            @change="emit('select-image', $event)"
          />
        </label>
      </div>
    </div>
  </ZoomableImageContainer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type { CSSProperties } from "vue";
import { PhotoIcon, ArrowUpTrayIcon, XMarkIcon } from "@heroicons/vue/24/outline";
import ZoomableImageContainer from "./ZoomableImageContainer.vue";
import { useZoomableStage } from "../../composables/useZoomableStage";
import type { TextRegion } from "../../utils/textValidation";

const ACCEPTED_IMAGE_TYPES = "image/avif,image/gif,image/jpeg,image/png,image/webp";
// Padding around a detected text, in screen pixels, so the frame does not
// touch the letters.
const REGION_PADDING_PX = 3;
// A quad may overshoot the image by this share of its size before the regions
// are taken to belong to another image.
const REGION_OVERFLOW_TOLERANCE = 0.02;
// Below this distance from the top of the viewer the label goes under its frame.
const LABEL_HEIGHT_PX = 28;

const props = withDefaults(
  defineProps<{
    displayImageUrl?: string | null;
    isUpdatingReferenceImage?: boolean;
    // Texts detected on the image, in the image's own pixel coordinates.
    regions?: TextRegion[];
    highlightedId?: string | null;
  }>(),
  {
    displayImageUrl: null,
    isUpdatingReferenceImage: false,
    regions: () => [],
    highlightedId: null,
  },
);

const emit = defineEmits<{
  (e: "select-image", event: Event): void;
  (e: "remove-image"): void;
  (e: "select-region", id: string): void;
}>();

const container = ref<HTMLDivElement | null>(null);
const imageEl = ref<HTMLImageElement | null>(null);
const showRegions = ref(true);

const {
  baseStage,
  stagePxPerImagePx,
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

// The regions were measured on the image the texts were extracted from. A
// reference image the user swapped in has other dimensions, and the frames
// would point at the wrong places: they are dropped when they do not fit.
const regionsFitImage = computed(() => {
  const stage = baseStage.value;
  if (!stage) return false;
  const maxX = stage.naturalW * (1 + REGION_OVERFLOW_TOLERANCE);
  const maxY = stage.naturalH * (1 + REGION_OVERFLOW_TOLERANCE);
  return props.regions.every((region: TextRegion) =>
    region.quad.every(([x, y]: [number, number]) => x >= 0 && y >= 0 && x <= maxX && y <= maxY),
  );
});

const hasRegions = computed(
  () => Boolean(props.displayImageUrl) && props.regions.length > 0 && regionsFitImage.value,
);

const headerText = computed(() =>
  hasRegions.value && showRegions.value
    ? "Image de référence — cliquez sur un cadre pour retrouver son texte"
    : "Image de référence",
);

const regionBoxes = computed(() => {
  const stage = baseStage.value;
  if (!stage || !hasRegions.value || !showRegions.value) return [];

  const scale = stagePxPerImagePx.value * zoom.value;
  const originX = stage.offsetX + panX.value;
  const originY = stage.offsetY + panY.value;

  return props.regions.map((region: TextRegion) => {
    const xs = region.quad.map((point: [number, number]) => point[0]);
    const ys = region.quad.map((point: [number, number]) => point[1]);
    const left = originX + Math.min(...xs) * scale - REGION_PADDING_PX;
    const top = originY + Math.min(...ys) * scale - REGION_PADDING_PX;
    const style: CSSProperties = {
      left: `${left}px`,
      top: `${top}px`,
      width: `${(Math.max(...xs) - Math.min(...xs)) * scale + REGION_PADDING_PX * 2}px`,
      height: `${(Math.max(...ys) - Math.min(...ys)) * scale + REGION_PADDING_PX * 2}px`,
    };
    return {
      id: region.id,
      label: region.label,
      style,
      labelBelow: top < LABEL_HEIGHT_PX,
    };
  });
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
    baseStage.value = null;
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
