<template>
  <BasePickerModal
    :is-open="isOpen"
    title="Sélectionner les formes à extraire"
    description="Cliquez sur les formes que vous souhaitez extraire. Chaque clic marque une forme — la couleur au point cliqué servira à délimiter la région par remplissage (flood fill)."
    :confirm-label="`Confirmer les formes (${pickedShapes.length})`"
    :is-confirm-disabled="pickedShapes.length === 0"
    show-skip
    @close="emit('close')"
    @skip="emit('skip')"
    @confirm="onConfirm"
    @opened="onModalOpened"
  >
    <template #image-area>
      <ZoomableImageContainer
        header-text="Carte importée — cliquez sur une forme pour la sélectionner"
        :zoom="zoom"
        :zoom-min="ZOOM_MIN"
        :zoom-max="ZOOM_MAX"
        @zoom-in="zoomIn"
        @zoom-out="zoomOut"
        @reset-zoom="resetZoom"
      >
        <div
          ref="container"
          class="relative h-[28rem] bg-base-200 select-none overflow-hidden"
          :class="containerCursorClass"
          @mousedown.left="onPointerDown"
          @mousemove="onPointerMove"
          @mouseup.left="onPointerUp"
          @mouseleave="onPointerLeave"
          @wheel.prevent="onWheel"
        >
          <div v-if="imageUrl" class="absolute" :style="stageStyle">
            <img
              ref="imageEl"
              :src="imageUrl"
              class="w-full h-full object-contain pointer-events-none select-none"
              alt="Carte importée"
              @load="onImageLoad"
            />
          </div>

          <!-- Shape markers -->
          <template v-if="baseStage">
            <div
              v-for="(shape, index) in pickedShapes"
              :key="`marker-${index}`"
              class="absolute pointer-events-none"
              :style="{
                left: `${stageToContainerX(shape.stageX)}px`,
                top: `${stageToContainerY(shape.stageY)}px`,
                transform: 'translate(-50%, -50%)',
              }"
            >
              <!-- Outer ring -->
              <div
                class="absolute rounded-full border-2 border-white shadow flex items-center justify-center"
                :style="{
                  width: `${MARKER_SIZE_PX}px`,
                  height: `${MARKER_SIZE_PX}px`,
                  backgroundColor: '#6366f1',
                  transform: 'translate(-50%, -50%)',
                }"
              >
                <span class="text-white font-bold text-xs leading-none">
                  {{ index + 1 }}
                </span>
              </div>
            </div>
          </template>
        </div>
      </ZoomableImageContainer>
    </template>

    <template #list-area>
      <div v-if="pickedShapes.length > 0" class="flex flex-col gap-2 min-h-0">
        <span class="text-sm font-medium">Formes sélectionnées :</span>
        <div class="flex flex-col gap-2 max-h-40 overflow-y-auto pr-1">
          <div
            v-for="(shape, index) in pickedShapes"
            :key="`row-${index}`"
            class="flex items-center gap-3 bg-base-200 rounded-lg px-3 py-2"
          >
            <!-- Number badge -->
            <div
              class="w-7 h-7 rounded-full bg-indigo-500 flex items-center justify-center shrink-0"
            >
              <span class="text-white text-xs font-bold">{{ index + 1 }}</span>
            </div>
            <!-- Coords -->
            <span class="text-xs font-mono text-base-content/50 w-32 shrink-0">
              x={{ (shape.normalizedX * 100).toFixed(1) }}%
              y={{ (shape.normalizedY * 100).toFixed(1) }}%
            </span>
            <!-- Editable name -->
            <input
              v-model="shape.name"
              type="text"
              class="input input-sm input-bordered flex-1 min-w-0"
              placeholder="Nom de la forme…"
            />
            <!-- Remove -->
            <button
              class="btn btn-sm btn-ghost btn-circle shrink-0"
              type="button"
              @click="removeShape(index)"
            >
              ✕
            </button>
          </div>
        </div>
      </div>

      <p v-else class="text-sm text-base-content/50 italic">
        Aucune forme sélectionnée — cliquez sur la carte pour ajouter des formes.
      </p>
    </template>
  </BasePickerModal>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from "vue";
import BasePickerModal from "./BasePickerModal.vue";
import ZoomableImageContainer from "./ZoomableImageContainer.vue";
import { useZoomableStage } from "../../composables/useZoomableStage";

const MARKER_SIZE_PX = 22;

interface PickedShape {
  stageX: number;
  stageY: number;
  normalizedX: number;
  normalizedY: number;
  name: string;
}

const props = withDefaults(
  defineProps<{
    isOpen: boolean;
    imageUrl: string;
  }>(),
  { isOpen: false },
);

const emit = defineEmits<{
  (e: "close"): void;
  (e: "skip"): void;
  (e: "confirmed", shapes: { x: number; y: number; name: string }[]): void;
}>();

const container = ref<HTMLDivElement | null>(null);
const imageEl = ref<HTMLImageElement | null>(null);

const {
  baseStage,
  stageStyle,
  zoom,
  panX,
  panY,
  zoomMin: ZOOM_MIN,
  zoomMax: ZOOM_MAX,
  updateBaseStage,
  clampPan,
  getLocalPointer,
  getStagePositionFromEvent,
  zoomIn,
  zoomOut,
  resetView,
  onWheel,
} = useZoomableStage({
  containerRef: container,
  imageRef: imageEl,
  zoomMin: 1,
  zoomMax: 8,
  zoomStepFactor: 1.25,
});

const pickedShapes = ref<PickedShape[]>([]);

const isPointerDown = ref(false);
const hasDragged = ref(false);
const pointerStart = ref({ x: 0, y: 0 });
const panStart = ref({ x: 0, y: 0 });

const containerCursorClass = computed(() => {
  if (zoom.value > 1) {
    return isPointerDown.value ? "cursor-grabbing" : "cursor-grab";
  }
  return "cursor-crosshair";
});

function stageToContainerX(stageX: number) {
  if (!baseStage.value) return 0;
  return baseStage.value.offsetX + panX.value + stageX * zoom.value;
}

function stageToContainerY(stageY: number) {
  if (!baseStage.value) return 0;
  return baseStage.value.offsetY + panY.value + stageY * zoom.value;
}

function onModalOpened() {
  pickedShapes.value = [];
  resetView();
  nextTick(() => updateBaseStage());
}

function onImageLoad() {
  updateBaseStage();
}

function resetZoom() {
  resetView();
}

function onPointerDown(event: MouseEvent) {
  if (event.button !== 0) return;
  isPointerDown.value = true;
  hasDragged.value = false;
  const local = getLocalPointer(event);
  if (!local) return;
  pointerStart.value = local;
  panStart.value = { x: panX.value, y: panY.value };
}

function onPointerMove(event: MouseEvent) {
  if (!isPointerDown.value) return;
  if (zoom.value <= 1) return;
  const local = getLocalPointer(event);
  if (!local) return;

  const dx = local.x - pointerStart.value.x;
  const dy = local.y - pointerStart.value.y;
  if (!hasDragged.value && (Math.abs(dx) > 3 || Math.abs(dy) > 3)) {
    hasDragged.value = true;
  }

  if (!hasDragged.value) return;

  const clamped = clampPan(panStart.value.x + dx, panStart.value.y + dy);
  panX.value = clamped.x;
  panY.value = clamped.y;
}

function onPointerUp(event: MouseEvent) {
  if (!isPointerDown.value) return;
  isPointerDown.value = false;
  if (hasDragged.value) return;
  placeMarkerAtEvent(event);
}

function onPointerLeave() {
  isPointerDown.value = false;
}

function placeMarkerAtEvent(event: MouseEvent) {
  const pos = getStagePositionFromEvent(event);
  if (!pos) return;
  pickedShapes.value.push({
    stageX: pos.stage.x,
    stageY: pos.stage.y,
    normalizedX: pos.normalized.x,
    normalizedY: pos.normalized.y,
    name: `Forme ${pickedShapes.value.length + 1}`,
  });
}

function removeShape(index: number) {
  pickedShapes.value.splice(index, 1);
}

function onConfirm() {
  if (pickedShapes.value.length === 0) return;
  emit(
    "confirmed",
    pickedShapes.value.map((s) => ({
      x: s.normalizedX,
      y: s.normalizedY,
      name: s.name,
    })),
  );
}
</script>
