<template>
  <div
    ref="container"
    class="relative w-full h-full bg-base-200 overflow-hidden"
    :class="containerCursorClass"
    @mousedown.left="onPointerDown"
    @mousemove="onPointerMove"
    @mouseup.left="onPointerUp"
    @mouseleave="onPointerLeave"
    @wheel.prevent="onWheel"
  >
    <div class="absolute top-2 right-2 z-10 flex items-center gap-2">
      <span class="text-xs text-base-content/60 whitespace-nowrap">
        {{ Math.round(zoom * 100) }}%
      </span>
      <button
        class="btn btn-xs"
        type="button"
        :disabled="zoom <= ZOOM_MIN"
        @mousedown.stop
        @click.stop="zoomOut"
      >
        −
      </button>
      <button
        class="btn btn-xs"
        type="button"
        :disabled="zoom === 1"
        @mousedown.stop
        @click.stop="resetZoom"
      >
        100%
      </button>
      <button
        class="btn btn-xs"
        type="button"
        :disabled="zoom >= ZOOM_MAX"
        @mousedown.stop
        @click.stop="zoomIn"
      >
        +
      </button>
    </div>

    <div v-if="imageUrl" class="absolute" :style="stageStyle">
      <img
        ref="imageEl"
        :src="imageUrl"
        class="w-full h-full object-contain select-none pointer-events-none"
        @load="onImageLoad"
      />

      <svg
        v-if="baseStage && matchedPoints.length"
        class="absolute inset-0"
        :viewBox="`0 0 ${baseStage.naturalW} ${baseStage.naturalH}`"
        preserveAspectRatio="none"
      >
        <polygon
          v-for="m in matchedPoints"
          :key="`matched-${m.index}`"
          :points="trianglePoints(m)"
          :fill="m.color"
          :stroke="m.color"
          style="cursor: pointer;"
          @mousedown.stop.prevent="onTriangleClick(m.index)"
          opacity="0.95"
        />
      </svg>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { useZoomableStage } from "../../composables/useZoomableStage";
import type { XYTuple, MatchedImagePoint } from "../../typescript/georef";

type PointTuple = XYTuple;
type MatchedPoint = MatchedImagePoint;

const props = withDefaults(
  defineProps<{
    point: PointTuple | null;
    imageUrl: string;
    // Matched control points passed from parent (for SIFT modal)
    // [{ index, x, y, color }]
    matchedPoints: MatchedPoint[];
  }>(),
  {
    point: null,
    matchedPoints: () => [],
  },
);

const emit = defineEmits<{
  (e: "update:point", value: PointTuple): void;
  (e: "select-match", index: number): void;
}>();

const container = ref<HTMLDivElement | null>(null);
const imageEl = ref<HTMLImageElement | null>(null);

const {
  baseStage,
  stageStyle,
  stagePxPerImagePx,
  zoom,
  panX,
  panY,
  zoomMin: ZOOM_MIN,
  zoomMax: ZOOM_MAX,
  updateBaseStage,
  clampPan,
  getLocalPointer,
  getStagePositionFromEvent,
  onWheel,
  zoomIn,
  zoomOut,
  resetView,
} = useZoomableStage({
  containerRef: container,
  imageRef: imageEl,
  zoomMin: 1,
  zoomMax: 5,
  zoomStepFactor: 1.25,
});

function resetZoom() {
  resetView();
}

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

onMounted(() => {
  updateBaseStage();
});

watch(
  () => props.imageUrl,
  () => {
    updateBaseStage();
  },
);

function onImageLoad() {
  updateBaseStage();
}

function onPointerDown(event: MouseEvent): void {
  if (event.button !== 0) return;
  isPointerDown.value = true;
  hasDragged.value = false;
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
  if (!hasDragged.value && (Math.abs(dx) > 3 || Math.abs(dy) > 3)) {
    hasDragged.value = true;
  }
  if (!hasDragged.value) return;

  const clamped = clampPan(panStart.value.x + dx, panStart.value.y + dy);
  panX.value = clamped.x;
  panY.value = clamped.y;
}

function onPointerUp(event: MouseEvent): void {
  if (!isPointerDown.value) return;
  isPointerDown.value = false;
  if (hasDragged.value) return;
  setPointFromEvent(event);
}

function onPointerLeave(): void {
  isPointerDown.value = false;
}

function onTriangleClick(index: number): void {
  // Notify parent that an existing matched point was selected
  emit("select-match", index);
}

function trianglePoints(m: MatchedPoint): string {
  // Build an upright triangle centered on the image point.
  // Keep its apparent size roughly constant on screen by
  // compensating for both the base image fit (baseScale)
  // and the interactive zoom (scale).
  // Desired triangle height in on-screen pixels.
  // svg is scaled by (baseStage fit) * zoom, so compensate by both.
  const desiredScreenSize = 6; // px
  const size = desiredScreenSize / (stagePxPerImagePx.value * Math.max(1, zoom.value));
  const x = m.x;
  const y = m.y;

  const x1 = x;
  const y1 = y - size; // top
  const x2 = x - size * 0.8;
  const y2 = y + size * 0.6;
  const x3 = x + size * 0.8;
  const y3 = y + size * 0.6;

  return `${x1},${y1} ${x2},${y2} ${x3},${y3}`;
}

function setPointFromEvent(event: MouseEvent): void {
  if (!baseStage.value) return;
  const pos = getStagePositionFromEvent(event);
  if (!pos) return;

  // Convert stage coords (in rendered pixels) back to image pixel space.
  const xPx = (pos.stage.x / Math.max(1, baseStage.value.renderedW)) * baseStage.value.naturalW;
  const yPx = (pos.stage.y / Math.max(1, baseStage.value.renderedH)) * baseStage.value.naturalH;
  emit("update:point", [xPx, yPx]);
}

defineExpose({
  // Kept for backward compatibility: click is always enabled now.
  focusClickMode() {
    isPointerDown.value = false;
    hasDragged.value = false;
  },
});

</script>
